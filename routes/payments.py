
"""
Kalxa Creator — One-Time Yoco Plan Payments

Handles:
- Free -> Standard: R300
- Free -> Premium: R500
- Standard -> Premium: R200

Fan -> Creator Paystack payments are handled separately.

Security:
- Prices are determined server-side.
- Existing payment amounts are immutable.
- Upgrade eligibility requires a verified paid Standard record.
- Webhooks are signature-verified.
- Creator/payment rows are locked during processing.
- Duplicate and out-of-order webhooks are handled.
"""

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)

from extensions import db

from models import (
    CreatorAccount,
    PlatformSubscriptionPayment,
    utc_now,
)

from config import (
    PLAN_PRICES_CENTS,
    STANDARD_TO_PREMIUM_UPGRADE_CENTS,
)

from services.yoco_service import (
    create_checkout,
    YocoError,
)

from services.yoco_webhook_service import (
    verify_yoco_webhook,
    YocoWebhookError,
)


payments_bp = Blueprint(
    "payments",
    __name__,
    url_prefix="/payments",
)

PAID_PLANS = ("standard", "premium")


# ============================================================
# AUTHENTICATION / REDIRECTS
# ============================================================

def get_logged_in_creator():

    creator_id = session.get("creator_account_id")

    if not creator_id:
        return None

    return db.session.get(
        CreatorAccount,
        creator_id,
    )


def get_site_url():

    site_url = str(
        current_app.config.get("SITE_URL") or ""
    ).rstrip("/")

    if not site_url.startswith("https://"):
        raise RuntimeError(
            "SITE_URL must be a configured HTTPS URL."
        )

    return site_url


def _return_to_account():

    return redirect(
        url_for("creator_auth.pending")
    )


# ============================================================
# PLAN HELPERS
# ============================================================

def _is_activated(creator):
    """
    Check the creator's current paid activation state.

    This is a convenience check, not proof that a
    particular historical payment succeeded.
    """

    return bool(
        creator.account_status == "active"
        and creator.plan in PAID_PLANS
        and creator.payment_status == "paid"
        and creator.registration_paid_at is not None
    )


def _has_paid_standard_activation(creator_id):
    """
    Verify Standard ownership using the payment ledger.

    Do not infer payment from creator.plan alone.

    Historical successful Standard payments remain
    valid even if their original price was different.
    """

    payment = (
        db.session.query(
            PlatformSubscriptionPayment
        )
        .filter_by(
            creator_account_id=creator_id,
            plan="standard",
            provider="yoco",
            status="paid",
        )
        .filter(
            PlatformSubscriptionPayment.paid_at.isnot(None)
        )
        .first()
    )

    return payment is not None


def _requested_plan():

    plan = str(
        request.form.get("plan") or ""
    ).strip().lower()

    return (
        plan
        if plan in PAID_PLANS
        else None
    )


def _amount_due(creator, requested_plan):
    """
    Calculate the price for a NEW checkout.

    Never recalculate historical payment amounts
    using current pricing.
    """

    if requested_plan not in PAID_PLANS:
        return None

    if _is_activated(creator):

        if creator.plan == requested_plan:
            return None

        if creator.plan == "premium":
            return None

        if (
            creator.plan == "standard"
            and requested_plan == "premium"
        ):

            if not _has_paid_standard_activation(
                creator.id
            ):
                return None

            return (
                STANDARD_TO_PREMIUM_UPGRADE_CENTS
            )

        return None

    # Legacy creators marked paid without a verified
    # activation should not receive an upgrade discount.
    return PLAN_PRICES_CENTS[requested_plan]


# ============================================================
# WEBHOOK PAYLOAD HELPERS
# ============================================================

def _event_type(payload):

    return str(
        payload.get("type")
        or payload.get("event_type")
        or payload.get("eventType")
        or ""
    ).strip().lower()


def _payment_data(payload):

    data = payload.get("payload")

    return (
        data
        if isinstance(data, dict)
        else None
    )


def _metadata(data):

    value = data.get("metadata")

    return (
        value
        if isinstance(value, dict)
        else {}
    )


def _checkout_id(data):

    metadata = _metadata(data)

    value = (
        metadata.get("checkoutId")
        or metadata.get("checkout_id")
    )

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def _amount(data):

    value = data.get("amount")

    if isinstance(value, dict):
        value = value.get("amount")

    if value is None:

        value = data.get(
            "totalAmount",
            data.get("total_amount"),
        )

        if isinstance(value, dict):
            value = value.get("amount")

    if type(value) is not int:
        return None

    return value


def _payment_matches_expected_checkout(payment):
    """
    Validate the stored payment against an allowed
    activation amount.

    Historical paid payments are not re-priced.

    For pending transactions, their recorded amount
    remains the checkout amount.
    """

    if payment.plan not in PAID_PLANS:
        return False

    if type(payment.amount_cents) is not int:
        return False

    if payment.amount_cents <= 0:
        return False

    return (
        payment.currency == "ZAR"
        and payment.provider == "yoco"
    )


def _can_apply_paid_plan(creator, payment):
    """
    Prevent invalid or out-of-order plan changes.

    The R200 upgrade requires an independently
    verified paid Standard activation.
    """

    if payment.plan not in PAID_PLANS:
        return False

    if creator.plan == "premium":
        # Never downgrade an existing Premium creator.
        return payment.plan == "premium"

    if (
        payment.plan == "premium"
        and payment.amount_cents
        == STANDARD_TO_PREMIUM_UPGRADE_CENTS
    ):
        return (
            creator.plan == "standard"
            and _has_paid_standard_activation(
                creator.id
            )
        )

    return True


# ============================================================
# CREATE YOCO CHECKOUT
# ============================================================

@payments_bp.route(
    "/creator/checkout",
    methods=["POST"],
)
def creator_checkout():

    creator = get_logged_in_creator()

    if creator is None:

        flash(
            "Please sign in to continue.",
            "warning",
        )

        return redirect(
            url_for("creator_auth.login")
        )

    if creator.account_status in (
        "suspended",
        "rejected",
    ):

        flash(
            "This account cannot purchase a plan.",
            "error",
        )

        return _return_to_account()

    plan = _requested_plan()

    if plan is None:

        flash(
            "Choose Standard or Premium to continue.",
            "error",
        )

        return _return_to_account()

    amount_cents = _amount_due(
        creator,
        plan,
    )

    if amount_cents is None:

        flash(
            "This plan is already active or cannot "
            "be purchased.",
            "info",
        )

        return _return_to_account()

    try:

        site_url = get_site_url()

        checkout = create_checkout(
            amount_cents=amount_cents,
            creator=creator,
            plan=plan,
            success_url=(
                f"{site_url}/payments/yoco/success"
            ),
            cancel_url=(
                f"{site_url}/payments/yoco/cancel"
            ),
            failure_url=(
                f"{site_url}/payments/yoco/failure"
            ),
        )

    except (YocoError, RuntimeError):

        current_app.logger.exception(
            "Could not create Yoco checkout "
            "for creator %s",
            creator.id,
        )

        flash(
            "Payments are temporarily unavailable. "
            "Please try again.",
            "error",
        )

        return _return_to_account()

    if not isinstance(checkout, dict):

        current_app.logger.error(
            "Invalid Yoco checkout response "
            "for creator %s",
            creator.id,
        )

        flash(
            "Payment checkout could not be validated.",
            "error",
        )

        return _return_to_account()

    checkout_id = checkout.get("id")

    redirect_url = checkout.get(
        "redirect_url"
    )

    if (
        not isinstance(checkout_id, str)
        or not checkout_id.strip()
    ):

        flash(
            "Yoco did not return a checkout reference.",
            "error",
        )

        return _return_to_account()

    if (
        not isinstance(redirect_url, str)
        or not redirect_url.startswith("https://")
    ):

        flash(
            "Yoco did not return a secure payment link.",
            "error",
        )

        return _return_to_account()

    provider_amount = checkout.get("amount")

    if (
        provider_amount is not None
        and (
            type(provider_amount) is not int
            or provider_amount != amount_cents
        )
    ):

        flash(
            "Yoco returned an unexpected amount.",
            "error",
        )

        return _return_to_account()

    if (
        checkout.get("currency")
        and checkout["currency"] != "ZAR"
    ):

        flash(
            "Yoco returned an unexpected currency.",
            "error",
        )

        return _return_to_account()

    try:

        payment = PlatformSubscriptionPayment(
            creator_account_id=creator.id,
            plan=plan,
            amount_cents=amount_cents,
            currency="ZAR",
            provider="yoco",
            provider_reference=checkout_id.strip(),
            status="pending",
        )

        db.session.add(payment)
        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Could not persist Yoco checkout %s",
            checkout_id,
        )

        flash(
            "Could not save your checkout. "
            "Please try again.",
            "error",
        )

        return _return_to_account()

    return redirect(
        redirect_url,
        code=303,
    )


# ============================================================
# YOCO WEBHOOK
# ============================================================

@payments_bp.route(
    "/yoco/webhook",
    methods=["POST"],
)
def yoco_webhook():

    raw_body = request.get_data(
        cache=True,
        as_text=False,
    )

    try:

        verify_yoco_webhook(
            raw_body=raw_body,
            webhook_id=request.headers.get(
                "webhook-id"
            ),
            webhook_timestamp=request.headers.get(
                "webhook-timestamp"
            ),
            webhook_signature=request.headers.get(
                "webhook-signature"
            ),
        )

    except YocoWebhookError:

        current_app.logger.warning(
            "Rejected Yoco webhook signature"
        )

        return jsonify(
            ok=False,
            error="Invalid webhook signature",
        ), 401

    payload = request.get_json(
        silent=True
    )

    if not isinstance(payload, dict):

        return jsonify(
            ok=False,
            error="Invalid payload",
        ), 400

    event_type = _event_type(
        payload
    )

    if event_type not in (
        "payment.succeeded",
        "payment.failed",
    ):

        return jsonify(
            ok=True,
            ignored=True,
            event_type=event_type,
        ), 200

    data = _payment_data(
        payload
    )

    checkout_id = (
        _checkout_id(data)
        if data
        else None
    )

    if not checkout_id:

        return jsonify(
            ok=False,
            error="Missing checkout ID",
        ), 400

    try:

        payment = (
            db.session.query(
                PlatformSubscriptionPayment
            )
            .filter_by(
                provider="yoco",
                provider_reference=checkout_id,
            )
            .with_for_update()
            .first()
        )

        if payment is None:

            db.session.rollback()

            return jsonify(
                ok=False,
                error="Unknown checkout",
            ), 503

        if payment.status == "paid":

            db.session.rollback()

            return jsonify(
                ok=True,
                duplicate=True,
            ), 200

        if payment.status == "refunded":

            db.session.rollback()

            return jsonify(
                ok=True,
                ignored=True,
                reason="refunded",
            ), 200

        if event_type == "payment.failed":

            payment.status = "failed"

            db.session.commit()

            return jsonify(
                ok=True,
                payment_status="failed",
            ), 200

        # ----------------------------------------------------
        # VALIDATE PAYMENT AMOUNT / CURRENCY
        # ----------------------------------------------------

        if not _payment_matches_expected_checkout(
            payment
        ):

            db.session.rollback()

            return jsonify(
                ok=False,
                error="Invalid payment record",
            ), 400

        if (
            _amount(data) != payment.amount_cents
            or str(
                data.get("currency", "")
            ).upper() != "ZAR"
        ):

            db.session.rollback()

            return jsonify(
                ok=False,
                error="Amount or currency mismatch",
            ), 400

        status = str(
            data.get("status") or ""
        ).strip().lower()

        if (
            status
            and status not in (
                "succeeded",
                "successful",
                "approved",
                "completed",
            )
        ):

            db.session.rollback()

            return jsonify(
                ok=False,
                error="Provider status mismatch",
            ), 400

        # ----------------------------------------------------
        # METADATA VALIDATION
        # ----------------------------------------------------

        meta = _metadata(data)

        if (
            meta.get("creatorAccountId")
            is not None
            and str(
                meta["creatorAccountId"]
            ) != str(
                payment.creator_account_id
            )
        ):

            db.session.rollback()

            return jsonify(
                ok=False,
                error="Creator mismatch",
            ), 400

        if (
            meta.get("plan") is not None
            and str(
                meta["plan"]
            ).lower() != payment.plan
        ):

            db.session.rollback()

            return jsonify(
                ok=False,
                error="Plan mismatch",
            ), 400

        # ----------------------------------------------------
        # LOCK CREATOR
        # ----------------------------------------------------

        creator = (
            db.session.query(
                CreatorAccount
            )
            .filter_by(
                id=payment.creator_account_id
            )
            .with_for_update()
            .first()
        )

        if creator is None:

            db.session.rollback()

            return jsonify(
                ok=False,
                error="Creator not found",
            ), 404

        if creator.account_status in (
            "suspended",
            "rejected",
        ):

            db.session.rollback()

            current_app.logger.error(
                "Paid checkout for restricted creator %s",
                creator.id,
            )

            return jsonify(
                ok=False,
                error="Account requires review",
            ), 409

        # ----------------------------------------------------
        # VERIFY PLAN TRANSITION
        # ----------------------------------------------------

        if not _can_apply_paid_plan(
            creator,
            payment,
        ):

            db.session.rollback()

            current_app.logger.error(
                "Invalid paid plan transition: "
                "creator=%s payment=%s",
                creator.id,
                payment.id,
            )

            return jsonify(
                ok=False,
                error="Plan transition requires review",
            ), 409

        # ----------------------------------------------------
        # APPLY PLAN
        # ----------------------------------------------------

        creator.plan = payment.plan

        creator.payment_status = "paid"

        creator.registration_paid_at = (
            creator.registration_paid_at
            or utc_now()
        )

        if (
            creator.account_status
            == "pending_payment"
        ):

            creator.account_status = (
                "pending_approval"
            )

        # One-time activation.
        # No monthly renewal.
        creator.subscription_status = (
            "inactive"
        )

        creator.subscription_expires_at = None

        payment.status = "paid"
        payment.paid_at = utc_now()

        db.session.commit()

        return jsonify(
            ok=True,
            processed=True,
            payment_status="paid",
            account_status=creator.account_status,
            plan=creator.plan,
        ), 200

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Yoco webhook processing failed for %s",
            checkout_id,
        )

        return jsonify(
            ok=False,
            error="Payment processing failed",
        ), 500


# ============================================================
# YOCO SUCCESS
# ============================================================

@payments_bp.route(
    "/yoco/success",
    methods=["GET"],
)
def yoco_success():

    if get_logged_in_creator() is None:

        flash(
            "Sign in to check your activation status.",
            "info",
        )

        return redirect(
            url_for("creator_auth.login")
        )

    flash(
        "Your payment is being verified securely "
        "with Yoco.",
        "info",
    )

    return _return_to_account()


# ============================================================
# YOCO CANCEL
# ============================================================

@payments_bp.route(
    "/yoco/cancel",
    methods=["GET"],
)
def yoco_cancel():

    flash(
        "Payment cancelled. "
        "Your plan has not changed.",
        "warning",
    )

    if get_logged_in_creator():

        return _return_to_account()

    return redirect(
        url_for("creator_auth.login")
    )


# ============================================================
# YOCO FAILURE
# ============================================================

@payments_bp.route(
    "/yoco/failure",
    methods=["GET"],
)
def yoco_failure():

    flash(
        "Payment was not completed. "
        "Please try again.",
        "error",
    )

    if get_logged_in_creator():

        return _return_to_account()

    return redirect(
        url_for("creator_auth.login")
    )
