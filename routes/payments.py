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
)

from services.plan_service import (
    PLAN_STANDARD,
    PLAN_PRICES,
    VALID_PLANS,
    normalize_plan,
)

from services.subscription_service import (
    record_subscription_payment,
    get_creator_subscription,
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
# CHECKOUT EVENT HELPERS
# ============================================================

def _find_value(
    value,
    key,
):

    if isinstance(
        value,
        dict,
    ):

        if (
            key in value
            and value[key] is not None
        ):

            return value[key]

        for child in value.values():

            result = _find_value(
                child,
                key,
            )

            if result is not None:
                return result

    elif isinstance(
        value,
        list,
    ):

        for child in value:

            result = _find_value(
                child,
                key,
            )

            if result is not None:
                return result

    return None


def extract_checkout_id(
    payload,
):

    # Yoco payment events associate the payment with
    # the checkout. We support the expected checkoutId
    # location while keeping extraction tolerant of the
    # surrounding event envelope.

    checkout_id = _find_value(
        payload,
        "checkoutId",
    )

    if checkout_id:
        return str(
            checkout_id
        )

    return None


def extract_amount(
    payload,
):

    amount = _find_value(
        payload,
        "amount",
    )

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


def extract_currency(
    payload,
):

    currency = _find_value(
        payload,
        "currency",
    )

    if not currency:
        return None

    return str(
        currency
    ).upper()


# ============================================================
# CREATOR CHECKOUT
# ============================================================

@payments_bp.route(
    "/creator/checkout",
    methods=["POST"],
)
def creator_checkout():

    creator = (
        get_logged_in_creator()
    )

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

    selected_plan = normalize_plan(
        creator.plan,
        default=PLAN_STANDARD,
    )

    if selected_plan not in VALID_PLANS:

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

    amount_rands = PLAN_PRICES[
        selected_plan
    ]

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
            str(exc),
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

    if (
        provider_amount is not None
        and int(
            provider_amount
        ) != amount_cents
    ):

        current_app.logger.error(
            (
                "Yoco checkout amount mismatch. "
                "creator=%s expected=%s received=%s"
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
    # RECORD PENDING PAYMENT
    # --------------------------------------------------------

    try:

        record_subscription_payment(
            creator=creator,
            status="pending",
            provider="yoco",
            provider_reference=checkout[
                "id"
            ],
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
            checkout.get(
                "id"
            ),
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
# YOCO WEBHOOK
# ============================================================

@payments_bp.route(
    "/yoco/webhook",
    methods=["POST"],
)
def yoco_webhook():

    # --------------------------------------------------------
    # RAW BODY
    # --------------------------------------------------------
    #
    # IMPORTANT:
    # Signature verification must happen against the exact
    # raw request body before we trust the JSON payload.
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
    # VERIFY SIGNATURE
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
            "Rejected Yoco webhook: %s",
            str(exc),
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
    # JSON
    # --------------------------------------------------------

    payload = request.get_json(
        silent=True
    )

    if not isinstance(
        payload,
        dict,
    ):

        current_app.logger.warning(
            "Yoco webhook contained invalid JSON."
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

    event_type = (
        payload.get(
            "type"
        )
        or payload.get(
            "eventType"
        )
        or ""
    )

    event_type = str(
        event_type
    ).strip().lower()

    # --------------------------------------------------------
    # IGNORE EVENTS WE DON'T PROCESS
    # --------------------------------------------------------

    if event_type not in {
        "payment.succeeded",
        "payment.failed",
    }:

        current_app.logger.info(
            "Ignoring Yoco event type=%s",
            event_type,
        )

        return jsonify(
            {
                "ok": True,
                "ignored": True,
            }
        ), 200

    # --------------------------------------------------------
    # CHECKOUT ID
    # --------------------------------------------------------

    checkout_id = extract_checkout_id(
        payload
    )

    if not checkout_id:

        current_app.logger.error(
            (
                "Yoco webhook event %s "
                "did not contain checkoutId."
            ),
            webhook_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Missing checkout reference."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # FIND OUR PENDING PAYMENT
    # --------------------------------------------------------

    payment = (
        PlatformSubscriptionPayment.query
        .filter_by(
            provider="yoco",
            provider_reference=checkout_id,
        )
        .first()
    )

    if not payment:

        current_app.logger.error(
            (
                "No local Yoco payment found "
                "for checkout_id=%s."
            ),
            checkout_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Payment reference not found."
                ),
            }
        ), 404

    # --------------------------------------------------------
    # IDEMPOTENCY
    # --------------------------------------------------------
    #
    # Yoco may retry webhook delivery.
    #
    # If this payment is already paid, return success without
    # activating or renewing the subscription again.
    # --------------------------------------------------------

    if (
        event_type
        == "payment.succeeded"
        and payment.status
        == "paid"
    ):

        current_app.logger.info(
            (
                "Duplicate successful Yoco webhook "
                "ignored for checkout_id=%s."
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
        payment.creator_account_id,
    )

    if not creator:

        current_app.logger.error(
            (
                "Creator not found for Yoco "
                "payment id=%s."
            ),
            payment.id,
        )

        return jsonify(
            {
                "ok": False,
                "error": "Creator not found.",
            }
        ), 404

    # --------------------------------------------------------
    # EXPECTED PLAN / PRICE
    # --------------------------------------------------------

    payment_plan = normalize_plan(
        payment.plan,
        default=PLAN_STANDARD,
    )

    if payment_plan not in VALID_PLANS:

        current_app.logger.error(
            "Invalid plan on payment id=%s.",
            payment.id,
        )

        return jsonify(
            {
                "ok": False,
                "error": "Invalid payment plan.",
            }
        ), 400

    expected_amount = int(
        PLAN_PRICES[
            payment_plan
        ] * 100
    )

    # --------------------------------------------------------
    # VERIFY OUR STORED PAYMENT
    # --------------------------------------------------------

    if int(
        payment.amount_cents
    ) != expected_amount:

        current_app.logger.error(
            (
                "Stored payment amount mismatch "
                "payment_id=%s expected=%s actual=%s"
            ),
            payment.id,
            expected_amount,
            payment.amount_cents,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Stored amount mismatch."
                ),
            }
        ), 400

    if (
        str(
            payment.currency
        ).upper()
        != "ZAR"
    ):

        current_app.logger.error(
            (
                "Stored currency mismatch "
                "payment_id=%s currency=%s"
            ),
            payment.id,
            payment.currency,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Stored currency mismatch."
                ),
            }
        ), 400

    # --------------------------------------------------------
    # VERIFY YOCO AMOUNT / CURRENCY
    # --------------------------------------------------------

    provider_amount = extract_amount(
        payload
    )

    provider_currency = extract_currency(
        payload
    )

    if provider_amount is None:

        current_app.logger.error(
            (
                "Yoco success/failure event did not "
                "contain an amount. checkout_id=%s"
            ),
            checkout_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Missing provider amount."
                ),
            }
        ), 400

    if (
        provider_amount
        != expected_amount
    ):

        current_app.logger.error(
            (
                "Yoco webhook amount mismatch "
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

    if (
        provider_currency
        != "ZAR"
    ):

        current_app.logger.error(
            (
                "Yoco webhook currency mismatch "
                "checkout_id=%s currency=%s"
            ),
            checkout_id,
            provider_currency,
        )

        return jsonify(
            {
                "ok": False,
                "error": "Currency mismatch.",
            }
        ), 400

    # ========================================================
    # PAYMENT FAILED
    # ========================================================

    if (
        event_type
        == "payment.failed"
    ):

        # Do not overwrite an already successful payment.
        if payment.status != "paid":

            payment.status = "failed"

            creator.payment_status = (
                "unpaid"
            )

            try:

                db.session.commit()

            except Exception:

                db.session.rollback()

                current_app.logger.exception(
                    (
                        "Could not save failed Yoco "
                        "payment checkout_id=%s."
                    ),
                    checkout_id,
                )

                return jsonify(
                    {
                        "ok": False,
                        "error": (
                            "Database update failed."
                        ),
                    }
                ), 500

        return jsonify(
            {
                "ok": True,
                "status": "failed",
            }
        ), 200

    # ========================================================
    # PAYMENT SUCCEEDED
    # ========================================================

    # --------------------------------------------------------
    # DETERMINE WHETHER THIS IS FIRST PAYMENT OR RENEWAL
    # --------------------------------------------------------

    subscription = (
        get_creator_subscription(
            creator,
            create=False,
        )
    )

    already_approved = (
        creator.account_status
        == "active"
    )

    # --------------------------------------------------------
    # MARK PAYMENT PAID
    # --------------------------------------------------------

    payment.status = "paid"

    from models import utc_now

    payment.paid_at = utc_now()

    creator.payment_status = (
        "paid"
    )

    # --------------------------------------------------------
    # FIRST CREATOR PAYMENT
    # --------------------------------------------------------
    #
    # Payment does NOT automatically approve a brand-new
    # creator.
    #
    # The platform owner reviews and approves the account.
    # --------------------------------------------------------

    if not already_approved:

        creator.account_status = (
            "pending_approval"
        )

        # Keep the selected paid plan.
        creator.plan = payment_plan

        current_app.logger.info(
            (
                "Creator payment confirmed. "
                "creator_account_id=%s "
                "checkout_id=%s "
                "awaiting admin approval."
            ),
            creator.id,
            checkout_id,
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
                "creator_account_id=%s "
                "checkout_id=%s."
            ),
            creator.id,
            checkout_id,
        )

    # --------------------------------------------------------
    # COMMIT ATOMIC UPDATE
    # --------------------------------------------------------

    try:

        db.session.commit()

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Could not process successful Yoco "
                "payment checkout_id=%s."
            ),
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

    return jsonify(
        {
            "ok": True,
            "status": "paid",
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

    creator = (
        get_logged_in_creator()
    )

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
    # We deliberately do not modify payment_status here.
    #
    # The webhook is authoritative.
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

    creator = (
        get_logged_in_creator()
    )

    if not creator:

        return redirect(
            url_for(
                "creator_auth.login"
            )
        )

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

    creator = (
        get_logged_in_creator()
    )

    if not creator:

        return redirect(
            url_for(
                "creator_auth.login"
            )
        )

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
