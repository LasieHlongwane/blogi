# ============================================================
# CREATOR PLATFORM
# PLATFORM PAYMENTS
# ============================================================

from flask import (
    Blueprint,
    redirect,
    url_for,
    flash,
    session,
    current_app,
    request,
    jsonify,
)

from extensions import db

from models import (
    CreatorAccount,
    PlatformSubscriptionPayment,
    utc_now,
)

from services.plan_service import (
    PLAN_STANDARD,
    PLAN_PRICES,
    VALID_PLANS,
    normalize_plan,
)

from services.subscription_service import (
    record_subscription_payment,
    renew_creator_subscription,
)

from services.yoco_service import (
    create_checkout,
    YocoError,
)

from services.yoco_webhook_service import (
    verify_yoco_webhook,
    YocoWebhookError,
)


# ============================================================
# BLUEPRINT
# ============================================================

payments_bp = Blueprint(
    "payments",
    __name__,
    url_prefix="/payments",
)


# ============================================================
# HELPERS
# ============================================================

def get_logged_in_creator():

    creator_id = session.get(
        "creator_account_id"
    )

    if not creator_id:
        return None

    return db.session.get(
        CreatorAccount,
        creator_id,
    )


def get_site_url():

    site_url = (
        current_app.config
        .get(
            "SITE_URL",
            "",
        )
        .rstrip("/")
    )

    if not site_url:

        raise RuntimeError(
            "SITE_URL is not configured."
        )

    return site_url


# ============================================================
# WEBHOOK PAYLOAD HELPERS
# ============================================================

def _get_event_type(
    payload,
):

    event_type = (
        payload.get(
            "type"
        )
        or payload.get(
            "event_type"
        )
        or payload.get(
            "eventType"
        )
        or ""
    )

    return (
        str(
            event_type
        )
        .strip()
        .lower()
    )


def _get_event_data(
    payload,
):
    """
    Return the Yoco Checkout payment object.

    Confirmed Yoco Checkout webhook structure:

        {
            "id": "...",
            "createdDate": "...",
            "type": "payment.succeeded",
            "payload": {
                "id": "...",
                "amount": 7900,
                "currency": "ZAR",
                "status": "...",
                "metadata": {
                    "checkoutId": "..."
                }
            }
        }

    The actual payment object therefore lives at:

        payload["payload"]
    """

    payment_data = payload.get(
        "payload"
    )

    if not isinstance(
        payment_data,
        dict,
    ):

        return None

    return payment_data


def _get_payment_metadata(
    payment_data,
):

    metadata = payment_data.get(
        "metadata"
    )

    if not isinstance(
        metadata,
        dict,
    ):

        return {}

    return metadata


def _get_checkout_id(
    payment_data,
):
    """
    Return the Yoco Checkout ID.

    Confirmed location:

        webhook["payload"]
               ["metadata"]
               ["checkoutId"]
    """

    metadata = _get_payment_metadata(
        payment_data
    )

    checkout_id = (
        metadata.get(
            "checkoutId"
        )
        or metadata.get(
            "checkout_id"
        )
    )

    if checkout_id is None:
        return None

    checkout_id = (
        str(
            checkout_id
        )
        .strip()
    )

    return (
        checkout_id
        or None
    )


def _get_provider_payment_id(
    payment_data,
):

    payment_id = (
        payment_data.get(
            "id"
        )
        or payment_data.get(
            "paymentId"
        )
        or payment_data.get(
            "payment_id"
        )
    )

    if payment_id is None:
        return None

    payment_id = (
        str(
            payment_id
        )
        .strip()
    )

    return (
        payment_id
        or None
    )


def _get_payment_status(
    payment_data,
):

    status = (
        payment_data.get(
            "status"
        )
        or ""
    )

    return (
        str(
            status
        )
        .strip()
        .lower()
    )


def _get_payment_currency(
    payment_data,
):

    currency = (
        payment_data.get(
            "currency"
        )
        or ""
    )

    return (
        str(
            currency
        )
        .strip()
        .upper()
    )


def _get_payment_amount(
    payment_data,
):

    amount = payment_data.get(
        "amount"
    )

    # --------------------------------------------------------
    # DEFENSIVE SUPPORT FOR WRAPPED AMOUNTS
    # --------------------------------------------------------

    if isinstance(
        amount,
        dict,
    ):

        amount = amount.get(
            "amount"
        )

    if amount is None:

        total_amount = (
            payment_data.get(
                "totalAmount"
            )
            or payment_data.get(
                "total_amount"
            )
        )

        if isinstance(
            total_amount,
            dict,
        ):

            amount = total_amount.get(
                "amount"
            )

        elif total_amount is not None:

            amount = total_amount

    if amount is None:
        return None

    try:

        return int(
            amount
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# CREATOR CHECKOUT
# ============================================================

@payments_bp.route(
    "/creator/checkout",
    methods=["POST"],
)
def creator_checkout():

    creator = get_logged_in_creator()

    # --------------------------------------------------------
    # LOGIN REQUIRED
    # --------------------------------------------------------

    if not creator:

        flash(
            "Please sign in to continue.",
            "warning",
        )

        return redirect(
            url_for(
                "creator_auth.login"
            )
        )

    # --------------------------------------------------------
    # ACCOUNT STATE
    # --------------------------------------------------------

    if creator.account_status in {
        "rejected",
        "suspended",
    }:

        flash(
            (
                "This creator account cannot "
                "make subscription payments."
            ),
            "error",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # --------------------------------------------------------
    # PLAN
    # --------------------------------------------------------
    #
    # The creator's stored plan is authoritative.
    #
    # Never trust plan, price, or amount supplied by the
    # browser.
    # --------------------------------------------------------

    selected_plan = normalize_plan(
        creator.plan,
        default=PLAN_STANDARD,
    )

    if selected_plan not in VALID_PLANS:

        current_app.logger.error(
            (
                "Creator has invalid plan. "
                "creator_account_id=%s plan=%s"
            ),
            creator.id,
            creator.plan,
        )

        flash(
            "Your creator plan is invalid.",
            "error",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # --------------------------------------------------------
    # SERVER-SIDE PRICE
    # --------------------------------------------------------

    amount_rands = (
        PLAN_PRICES[
            selected_plan
        ]
    )

    amount_cents = int(
        amount_rands * 100
    )

    # --------------------------------------------------------
    # RETURN URLS
    # --------------------------------------------------------

    try:

        site_url = get_site_url()

    except RuntimeError:

        current_app.logger.exception(
            "SITE_URL is not configured."
        )

        flash(
            "Payments are temporarily unavailable.",
            "error",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    success_url = (
        f"{site_url}"
        "/payments/yoco/success"
    )

    cancel_url = (
        f"{site_url}"
        "/payments/yoco/cancel"
    )

    failure_url = (
        f"{site_url}"
        "/payments/yoco/failure"
    )

    # --------------------------------------------------------
    # CREATE YOCO CHECKOUT
    # --------------------------------------------------------

    try:

        checkout = create_checkout(
            amount_cents=amount_cents,
            creator=creator,
            plan=selected_plan,
            success_url=success_url,
            cancel_url=cancel_url,
            failure_url=failure_url,
        )

    except YocoError as exc:

        current_app.logger.warning(
            (
                "Yoco checkout failed for "
                "creator_account_id=%s: %s"
            ),
            creator.id,
            str(
                exc
            ),
        )

        flash(
            (
                "We could not start your Yoco "
                "payment. Please try again."
            ),
            "error",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # --------------------------------------------------------
    # VALIDATE CHECKOUT RESPONSE
    # --------------------------------------------------------

    provider_amount = checkout.get(
        "amount"
    )

    provider_currency = checkout.get(
        "currency"
    )

    if provider_amount is not None:

        try:

            provider_amount = int(
                provider_amount
            )

        except (
            TypeError,
            ValueError,
        ):

            current_app.logger.error(
                (
                    "Yoco checkout returned invalid "
                    "amount. creator=%s amount=%s"
                ),
                creator.id,
                provider_amount,
            )

            flash(
                "Payment checkout validation failed.",
                "error",
            )

            return redirect(
                url_for(
                    "creator_auth.pending"
                )
            )

        if provider_amount != amount_cents:

            current_app.logger.error(
                (
                    "Yoco checkout amount mismatch. "
                    "creator=%s expected=%s "
                    "received=%s"
                ),
                creator.id,
                amount_cents,
                provider_amount,
            )

            flash(
                "Payment checkout validation failed.",
                "error",
            )

            return redirect(
                url_for(
                    "creator_auth.pending"
                )
            )

    if (
        provider_currency
        and str(
            provider_currency
        ).upper() != "ZAR"
    ):

        current_app.logger.error(
            (
                "Yoco checkout currency mismatch. "
                "creator=%s currency=%s"
            ),
            creator.id,
            provider_currency,
        )

        flash(
            "Payment checkout validation failed.",
            "error",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # --------------------------------------------------------
    # CHECKOUT ID
    # --------------------------------------------------------

    checkout_id = checkout.get(
        "id"
    )

    if not checkout_id:

        current_app.logger.error(
            (
                "Yoco checkout did not return an ID. "
                "creator=%s"
            ),
            creator.id,
        )

        flash(
            "Payment checkout validation failed.",
            "error",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    checkout_id = (
        str(
            checkout_id
        )
        .strip()
    )

    # --------------------------------------------------------
    # RECORD PENDING PAYMENT
    # --------------------------------------------------------
    #
    # provider_reference contains the Yoco Checkout ID.
    #
    # This allows:
    #
    # webhook payload
    #       ↓
    # metadata.checkoutId
    #       ↓
    # PlatformSubscriptionPayment.provider_reference
    # --------------------------------------------------------

    try:

        record_subscription_payment(
            creator=creator,
            status="pending",
            provider="yoco",
            provider_reference=checkout_id,
            plan=selected_plan,
            amount_cents=amount_cents,
        )

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Could not save pending Yoco payment "
                "for creator_account_id=%s "
                "checkout_id=%s"
            ),
            creator.id,
            checkout_id,
        )

        flash(
            "Payment checkout could not be saved.",
            "error",
        )

        return redirect(
            url_for(
                "creator_auth.pending"
            )
        )

    # --------------------------------------------------------
    # REDIRECT TO YOCO
    # --------------------------------------------------------

    return redirect(
        checkout[
            "redirect_url"
        ],
        code=303,
    )


# ============================================================
# YOCO CHECKOUT WEBHOOK
# ============================================================

@payments_bp.route(
    "/yoco/webhook",
    methods=["POST"],
)
def yoco_webhook():

    # --------------------------------------------------------
    # RAW REQUEST BODY
    # --------------------------------------------------------
    #
    # The webhook signature is calculated using the exact
    # request body.
    #
    # Therefore signature verification happens BEFORE we
    # trust the JSON payload.
    # --------------------------------------------------------

    raw_body = request.get_data(
        cache=True,
        as_text=False,
    )

    webhook_id = request.headers.get(
        "webhook-id"
    )

    webhook_timestamp = request.headers.get(
        "webhook-timestamp"
    )

    webhook_signature = request.headers.get(
        "webhook-signature"
    )

    # --------------------------------------------------------
    # VERIFY YOCO / SVIX SIGNATURE
    # --------------------------------------------------------

    try:

        verify_yoco_webhook(
            raw_body=raw_body,
            webhook_id=webhook_id,
            webhook_timestamp=webhook_timestamp,
            webhook_signature=webhook_signature,
        )

    except YocoWebhookError as exc:

        current_app.logger.warning(
            (
                "Rejected Yoco Checkout webhook: %s"
            ),
            str(
                exc
            ),
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Invalid webhook signature."
                ),
            }
        ), 401

    # --------------------------------------------------------
    # PARSE VERIFIED JSON
    # --------------------------------------------------------

    payload = request.get_json(
        silent=True
    )

    if not isinstance(
        payload,
        dict,
    ):

        current_app.logger.warning(
            (
                "Verified Yoco webhook contained "
                "invalid JSON."
            )
        )

        return jsonify(
            {
                "ok": False,
                "error": "Invalid payload.",
            }
        ), 400

    # --------------------------------------------------------
    # EVENT TYPE
    # --------------------------------------------------------

    event_type = _get_event_type(
        payload
    )

    current_app.logger.info(
        (
            "Verified Yoco Checkout webhook received. "
            "webhook_id=%s event_type=%s"
        ),
        webhook_id,
        event_type,
    )

    # --------------------------------------------------------
    # IGNORE EVENTS WE DO NOT USE
    # --------------------------------------------------------

    if event_type not in {
        "payment.succeeded",
        "payment.failed",
    }:

        current_app.logger.info(
            (
                "Ignoring Yoco Checkout event. "
                "webhook_id=%s event_type=%s"
            ),
            webhook_id,
            event_type,
        )

        return jsonify(
            {
                "ok": True,
                "ignored": True,
                "event_type": event_type,
            }
        ), 200

    # --------------------------------------------------------
    # PAYMENT DATA
    # --------------------------------------------------------

    payment_data = _get_event_data(
        payload
    )

    if payment_data is None:

        current_app.logger.error(
            (
                "Yoco Checkout webhook has no "
                "payment payload. webhook_id=%s "
                "event_type=%s"
            ),
            webhook_id,
            event_type,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Missing payment payload."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # CHECKOUT ID
    # --------------------------------------------------------
    #
    # Confirmed Yoco location:
    #
    #     payload.metadata.checkoutId
    # --------------------------------------------------------

    checkout_id = _get_checkout_id(
        payment_data
    )

    if not checkout_id:

        current_app.logger.error(
            (
                "Yoco Checkout webhook has no "
                "checkout ID in metadata. "
                "webhook_id=%s event_type=%s"
            ),
            webhook_id,
            event_type,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Missing checkout ID."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # PAYMENT ID
    # --------------------------------------------------------

    provider_payment_id = (
        _get_provider_payment_id(
            payment_data
        )
    )

    # --------------------------------------------------------
    # FIND LOCAL PAYMENT
    # --------------------------------------------------------

    local_payment = (
        PlatformSubscriptionPayment.query
        .filter_by(
            provider="yoco",
            provider_reference=checkout_id,
        )
        .first()
    )

    if not local_payment:

        current_app.logger.error(
            (
                "No local Kalxa payment matches "
                "Yoco checkout_id=%s "
                "event_type=%s."
            ),
            checkout_id,
            event_type,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Payment reference not found."
                ),
            }
        ), 404

    # ========================================================
    # PAYMENT.FAILED
    # ========================================================

    if event_type == "payment.failed":

        # ----------------------------------------------------
        # NEVER OVERWRITE A CONFIRMED PAID PAYMENT
        # ----------------------------------------------------

        if local_payment.status == "paid":

            current_app.logger.warning(
                (
                    "Ignoring payment.failed for "
                    "already-paid local payment. "
                    "payment_id=%s checkout_id=%s"
                ),
                local_payment.id,
                checkout_id,
            )

            return jsonify(
                {
                    "ok": True,
                    "ignored": True,
                    "reason": (
                        "payment_already_paid"
                    ),
                }
            ), 200

        local_payment.status = (
            "failed"
        )

        try:

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                (
                    "Unable to record failed Yoco "
                    "payment. local_payment_id=%s "
                    "checkout_id=%s"
                ),
                local_payment.id,
                checkout_id,
            )

            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "Payment processing failed."
                    ),
                }
            ), 500

        current_app.logger.info(
            (
                "Yoco payment failed. "
                "local_payment_id=%s "
                "checkout_id=%s "
                "provider_payment_id=%s"
            ),
            local_payment.id,
            checkout_id,
            provider_payment_id,
        )

        return jsonify(
            {
                "ok": True,
                "processed": True,
                "payment_status": "failed",
            }
        ), 200

    # ========================================================
    # PAYMENT.SUCCEEDED
    # ========================================================

    # --------------------------------------------------------
    # IDEMPOTENCY
    # --------------------------------------------------------
    #
    # Yoco/Svix may deliver the same event more than once.
    #
    # Once our local payment has been marked paid, repeated
    # payment.succeeded events must not extend the
    # subscription again.
    # --------------------------------------------------------

    if local_payment.status == "paid":

        current_app.logger.info(
            (
                "Duplicate Yoco payment.succeeded "
                "webhook ignored. "
                "checkout_id=%s"
            ),
            checkout_id,
        )

        return jsonify(
            {
                "ok": True,
                "duplicate": True,
            }
        ), 200

    # --------------------------------------------------------
    # CREATOR
    # --------------------------------------------------------

    creator = db.session.get(
        CreatorAccount,
        local_payment.creator_account_id,
    )

    if not creator:

        current_app.logger.error(
            (
                "Creator missing for local "
                "payment id=%s."
            ),
            local_payment.id,
        )

        return jsonify(
            {
                "ok": False,
                "error": "Creator not found.",
            }
        ), 404

    # --------------------------------------------------------
    # LOCAL PAYMENT PLAN
    # --------------------------------------------------------

    payment_plan = normalize_plan(
        local_payment.plan,
        default=PLAN_STANDARD,
    )

    if payment_plan not in VALID_PLANS:

        current_app.logger.error(
            (
                "Invalid subscription plan on "
                "payment id=%s plan=%s"
            ),
            local_payment.id,
            local_payment.plan,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Invalid subscription plan."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # EXPECTED SERVER-SIDE AMOUNT
    # --------------------------------------------------------

    expected_amount = int(
        PLAN_PRICES[
            payment_plan
        ] * 100
    )

    # --------------------------------------------------------
    # VERIFY LOCAL AMOUNT
    # --------------------------------------------------------

    try:

        local_amount = int(
            local_payment.amount_cents
        )

    except (
        TypeError,
        ValueError,
    ):

        current_app.logger.error(
            (
                "Invalid local payment amount. "
                "payment_id=%s"
            ),
            local_payment.id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Invalid local amount."
                ),
            }
        ), 400

    if local_amount != expected_amount:

        current_app.logger.error(
            (
                "Local subscription amount mismatch. "
                "payment_id=%s expected=%s actual=%s"
            ),
            local_payment.id,
            expected_amount,
            local_amount,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Local amount mismatch."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # VERIFY LOCAL CURRENCY
    # --------------------------------------------------------

    local_currency = (
        str(
            local_payment.currency
            or ""
        )
        .strip()
        .upper()
    )

    if local_currency != "ZAR":

        current_app.logger.error(
            (
                "Local currency mismatch. "
                "payment_id=%s currency=%s"
            ),
            local_payment.id,
            local_currency,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Local currency mismatch."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # PROVIDER STATUS
    # --------------------------------------------------------

    provider_status = (
        _get_payment_status(
            payment_data
        )
    )

    if (
        provider_status
        and provider_status
        not in {
            "succeeded",
            "successful",
            "approved",
            "completed",
        }
    ):

        current_app.logger.error(
            (
                "Yoco payment.succeeded event has "
                "unexpected payment status. "
                "checkout_id=%s status=%s"
            ),
            checkout_id,
            provider_status,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Provider status mismatch."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # PROVIDER CURRENCY
    # --------------------------------------------------------

    provider_currency = (
        _get_payment_currency(
            payment_data
        )
    )

    if provider_currency != "ZAR":

        current_app.logger.error(
            (
                "Yoco currency mismatch. "
                "checkout_id=%s currency=%s"
            ),
            checkout_id,
            provider_currency,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Currency mismatch."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # PROVIDER AMOUNT
    # --------------------------------------------------------

    provider_amount = (
        _get_payment_amount(
            payment_data
        )
    )

    if provider_amount is None:

        current_app.logger.error(
            (
                "Yoco payment.succeeded event has "
                "no valid amount. checkout_id=%s"
            ),
            checkout_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Invalid provider amount."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # VERIFY PROVIDER AMOUNT
    # --------------------------------------------------------

    if provider_amount != expected_amount:

        current_app.logger.error(
            (
                "Yoco amount mismatch. "
                "checkout_id=%s expected=%s "
                "received=%s"
            ),
            checkout_id,
            expected_amount,
            provider_amount,
        )

        return jsonify(
            {
                "ok": False,
                "error": "Amount mismatch.",
            }
        ), 400

    # --------------------------------------------------------
    # OPTIONAL METADATA CROSS-CHECKS
    # --------------------------------------------------------
    #
    # These fields came from metadata we supplied when
    # creating the Yoco Checkout.
    #
    # They are useful as additional consistency checks.
    # The local database remains authoritative for plan and
    # price.
    # --------------------------------------------------------

    metadata = _get_payment_metadata(
        payment_data
    )

    metadata_creator_id = metadata.get(
        "creatorAccountId"
    )

    if metadata_creator_id is not None:

        if (
            str(
                metadata_creator_id
            ).strip()
            != str(
                creator.id
            )
        ):

            current_app.logger.error(
                (
                    "Yoco creator metadata mismatch. "
                    "checkout_id=%s"
                ),
                checkout_id,
            )

            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "Creator metadata mismatch."
                    ),
                }
            ), 400

    metadata_plan = metadata.get(
        "plan"
    )

    if metadata_plan:

        metadata_plan = normalize_plan(
            metadata_plan,
            default="",
        )

        if metadata_plan != payment_plan:

            current_app.logger.error(
                (
                    "Yoco plan metadata mismatch. "
                    "checkout_id=%s "
                    "local_plan=%s "
                    "metadata_plan=%s"
                ),
                checkout_id,
                payment_plan,
                metadata_plan,
            )

            return jsonify(
                {
                    "ok": False,
                    "error": (
                        "Plan metadata mismatch."
                    ),
                }
            ), 400

    # --------------------------------------------------------
    # FIRST PAYMENT OR RENEWAL?
    # --------------------------------------------------------

    already_approved = (
        creator.account_status
        == "active"
    )

    # --------------------------------------------------------
    # MARK LOCAL PAYMENT PAID
    # --------------------------------------------------------

    local_payment.status = (
        "paid"
    )

    local_payment.paid_at = (
        utc_now()
    )

    creator.payment_status = (
        "paid"
    )

    creator.plan = (
        payment_plan
    )

    # --------------------------------------------------------
    # FIRST CREATOR PAYMENT
    # --------------------------------------------------------
    #
    # A successful first payment moves the creator to:
    #
    #     pending_approval
    #
    # The platform administrator still decides whether the
    # creator account becomes active.
    # --------------------------------------------------------

    if not already_approved:

        creator.account_status = (
            "pending_approval"
        )

        current_app.logger.info(
            (
                "Creator subscription payment "
                "confirmed. creator=%s "
                "checkout_id=%s "
                "provider_payment_id=%s "
                "awaiting admin approval."
            ),
            creator.id,
            checkout_id,
            provider_payment_id,
        )

    # --------------------------------------------------------
    # EXISTING APPROVED CREATOR / RENEWAL
    # --------------------------------------------------------

    else:

        renew_creator_subscription(
            creator,
            days=30,
            plan=payment_plan,
            provider="yoco",
        )

        current_app.logger.info(
            (
                "Creator subscription renewed. "
                "creator=%s plan=%s "
                "checkout_id=%s "
                "provider_payment_id=%s"
            ),
            creator.id,
            payment_plan,
            checkout_id,
            provider_payment_id,
        )

    # --------------------------------------------------------
    # COMMIT PAYMENT + ACCOUNT UPDATE
    # --------------------------------------------------------

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unable to commit Yoco payment. "
                "local_payment_id=%s "
                "checkout_id=%s "
                "provider_payment_id=%s"
            ),
            local_payment.id,
            checkout_id,
            provider_payment_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Payment processing failed."
                ),
            }
        ), 500

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    return jsonify(
        {
            "ok": True,
            "processed": True,
            "payment_status": "paid",
            "account_status": (
                creator.account_status
            ),
        }
    ), 200


# ============================================================
# YOCO SUCCESS RETURN
# ============================================================

@payments_bp.route(
    "/yoco/success",
    methods=["GET"],
)
def yoco_success():

    creator = get_logged_in_creator()

    if not creator:

        flash(
            (
                "Your payment is being verified. "
                "Please sign in to view your "
                "account status."
            ),
            "info",
        )

        return redirect(
            url_for(
                "creator_auth.login"
            )
        )

    # --------------------------------------------------------
    # IMPORTANT
    # --------------------------------------------------------
    #
    # Reaching this URL is NOT proof of payment.
    #
    # Only a correctly signed payment.succeeded webhook may
    # mark the local payment as paid.
    # --------------------------------------------------------

    flash(
        (
            "Payment submitted successfully. "
            "We are confirming it securely "
            "with Yoco."
        ),
        "success",
    )

    return redirect(
        url_for(
            "creator_auth.pending"
        )
    )


# ============================================================
# YOCO CANCEL RETURN
# ============================================================

@payments_bp.route(
    "/yoco/cancel",
    methods=["GET"],
)
def yoco_cancel():

    creator = get_logged_in_creator()

    if not creator:

        return redirect(
            url_for(
                "creator_auth.login"
            )
        )

    # --------------------------------------------------------
    # DO NOT MUTATE PAYMENT STATE HERE
    # --------------------------------------------------------

    flash(
        (
            "The Yoco payment was cancelled. "
            "Your subscription has not been activated."
        ),
        "warning",
    )

    return redirect(
        url_for(
            "creator_auth.pending"
        )
    )


# ============================================================
# YOCO FAILURE RETURN
# ============================================================

@payments_bp.route(
    "/yoco/failure",
    methods=["GET"],
)
def yoco_failure():

    creator = get_logged_in_creator()

    if not creator:

        return redirect(
            url_for(
                "creator_auth.login"
            )
        )

    # --------------------------------------------------------
    # DO NOT MUTATE PAYMENT STATE HERE
    # --------------------------------------------------------
    #
    # A verified payment.failed webhook is the authoritative
    # server-to-server failure event.
    # --------------------------------------------------------

    flash(
        (
            "The payment could not be completed. "
            "Please try again."
        ),
        "error",
    )

    return redirect(
        url_for(
            "creator_auth.pending"
        )
    )
