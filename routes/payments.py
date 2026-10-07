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

from services.yoco_api_service import (
    fetch_payment,
    YocoAPIError,
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
    # Never trust an amount submitted by the browser.
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

    checkout_id = str(
        checkout_id
    )

    # --------------------------------------------------------
    # RECORD PENDING PAYMENT
    # --------------------------------------------------------
    #
    # provider_reference stores Yoco's Checkout ID.
    #
    # Later:
    #
    # payment.created
    #       ↓
    # Fetch Payment
    #       ↓
    # checkout_id
    #       ↓
    # provider_reference
    #
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
# YOCO WEBHOOK
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
    # IMPORTANT:
    #
    # Signature verification MUST happen against the exact
    # raw bytes sent by Yoco.
    #
    # Do not reconstruct the JSON before verifying.
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
    # VERIFY YOCO SIGNATURE
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
    # PARSE JSON
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
            "event_type"
        )
        or payload.get(
            "type"
        )
        or payload.get(
            "eventType"
        )
        or ""
    )

    event_type = (
        str(
            event_type
        )
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # ONLY PROCESS PAYMENT.CREATED
    # --------------------------------------------------------
    #
    # This webhook subscription was registered for:
    #
    #     payment.created
    #
    # payment.created itself is NOT proof of successful
    # payment.
    #
    # We fetch the authoritative payment from Yoco below.
    # --------------------------------------------------------

    if event_type != "payment.created":

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
    # PAYMENT ID
    # --------------------------------------------------------

    payment_id = (
        payload.get(
            "payment_id"
        )
        or payload.get(
            "paymentId"
        )
    )

    if not payment_id:

        current_app.logger.error(
            (
                "Yoco payment.created webhook "
                "did not contain payment_id. "
                "webhook_id=%s"
            ),
            webhook_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Missing payment ID."
                ),
            }
        ), 400

    payment_id = str(
        payment_id
    )

    # --------------------------------------------------------
    # FETCH AUTHORITATIVE PAYMENT FROM YOCO
    # --------------------------------------------------------
    #
    # YOCO_API_KEY is used here.
    #
    # This call gives us the authoritative:
    #
    #     status
    #     checkout_id
    #     amount
    #     currency
    #
    # --------------------------------------------------------

    try:

        yoco_payment = fetch_payment(
            payment_id
        )

    except YocoAPIError as exc:

        current_app.logger.error(
            (
                "Unable to verify Yoco payment "
                "%s: %s"
            ),
            payment_id,
            str(exc),
        )

        # A server error tells Yoco that processing was not
        # completed successfully.
        return jsonify(
            {
                "ok": False,
                "error": (
                    "Payment verification unavailable."
                ),
            }
        ), 500

    if not isinstance(
        yoco_payment,
        dict,
    ):

        current_app.logger.error(
            (
                "Yoco returned an invalid payment "
                "object. payment_id=%s"
            ),
            payment_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Invalid payment response."
                ),
            }
        ), 500

    # --------------------------------------------------------
    # AUTHORITATIVE PAYMENT STATUS
    # --------------------------------------------------------

    status = (
        str(
            yoco_payment.get(
                "status",
                "",
            )
        )
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # PAYMENT NOT YET APPROVED
    # --------------------------------------------------------
    #
    # Never grant subscription access for:
    #
    #     pending
    #     failed
    #     cancelled
    #
    # --------------------------------------------------------

    if status != "approved":

        current_app.logger.info(
            (
                "Yoco payment is not approved. "
                "payment_id=%s status=%s"
            ),
            payment_id,
            status,
        )

        return jsonify(
            {
                "ok": True,
                "processed": False,
                "payment_status": status,
            }
        ), 200

    # --------------------------------------------------------
    # CHECKOUT ID
    # --------------------------------------------------------

    checkout_id = (
        yoco_payment.get(
            "checkout_id"
        )
        or yoco_payment.get(
            "checkoutId"
        )
    )

    if not checkout_id:

        current_app.logger.error(
            (
                "Approved Yoco payment has no "
                "checkout ID. payment_id=%s"
            ),
            payment_id,
        )

        return jsonify(
            {
                "ok": False,
                "error": (
                    "Missing checkout ID."
                ),
            }
        ), 400

    checkout_id = str(
        checkout_id
    )

    # --------------------------------------------------------
    # FIND LOCAL PAYMENT
    # --------------------------------------------------------
    #
    # We stored the Checkout ID in provider_reference before
    # redirecting the creator to Yoco.
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
                "Yoco checkout_id=%s."
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
    # Yoco can retry webhook delivery.
    #
    # If we already processed this checkout successfully,
    # acknowledge it without activating/renewing again.
    # --------------------------------------------------------

    if local_payment.status == "paid":

        current_app.logger.info(
            (
                "Duplicate Yoco payment webhook "
                "ignored. checkout_id=%s"
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
    # PLAN
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
    # VERIFY YOCO CURRENCY
    # --------------------------------------------------------

    provider_currency = (
        str(
            yoco_payment.get(
                "currency",
                "",
            )
        )
        .strip()
        .upper()
    )

    if provider_currency != "ZAR":

        current_app.logger.error(
            (
                "Yoco currency mismatch. "
                "payment_id=%s currency=%s"
            ),
            payment_id,
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
    # YOCO AMOUNT
    # --------------------------------------------------------

    total_amount = (
        yoco_payment.get(
            "total_amount"
        )
    )

    provider_amount = None

    if isinstance(
        total_amount,
        dict,
    ):

        provider_amount = (
            total_amount.get(
                "amount"
            )
        )

    elif total_amount is not None:

        provider_amount = (
            total_amount
        )

    # --------------------------------------------------------
    # CAMELCASE FALLBACK
    # --------------------------------------------------------

    if provider_amount is None:

        total_amount = (
            yoco_payment.get(
                "totalAmount"
            )
        )

        if isinstance(
            total_amount,
            dict,
        ):

            provider_amount = (
                total_amount.get(
                    "amount"
                )
            )

        elif total_amount is not None:

            provider_amount = (
                total_amount
            )

    # --------------------------------------------------------
    # NORMALIZE PROVIDER AMOUNT
    # --------------------------------------------------------

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
                "Yoco payment has invalid amount. "
                "payment_id=%s amount=%s"
            ),
            payment_id,
            provider_amount,
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
                "payment_id=%s expected=%s "
                "received=%s"
            ),
            payment_id,
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
    # Payment does NOT automatically approve a brand-new
    # creator.
    #
    # The platform owner must approve the creator.
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
                "creator=%s plan=%s "
                "checkout_id=%s"
            ),
            creator.id,
            payment_plan,
            checkout_id,
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
                "payment_id=%s checkout_id=%s"
            ),
            payment_id,
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
    # We deliberately do not change payment_status here.
    #
    # The signed Yoco webhook + Fetch Payment API is
    # authoritative.
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
