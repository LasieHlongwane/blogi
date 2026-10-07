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
)

from extensions import db

from models import (
    CreatorAccount,
)

from services.plan_service import (
    PLAN_STANDARD,
    PLAN_PRICES,
    VALID_PLANS,
    normalize_plan,
)

from services.subscription_service import (
    record_subscription_payment,
)

from services.yoco_service import (
    create_checkout,
    YocoError,
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
            "This creator account cannot "
            "make subscription payments.",
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
    # IMPORTANT:
    #
    # We deliberately ignore any price supplied by the
    # browser.
    #
    # The plan stored on CreatorAccount is authoritative.
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
    # PRICE
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
            "Yoco checkout failed for "
            "creator_account_id=%s: %s",
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
    # VALIDATE PROVIDER AMOUNT
    # --------------------------------------------------------
    #
    # Yoco normally echoes the amount and currency.
    # If supplied, verify them before saving the checkout.
    # --------------------------------------------------------

    provider_amount = checkout.get(
        "amount"
    )

    provider_currency = checkout.get(
        "currency"
    )

    if (
        provider_amount is not None
        and int(provider_amount)
        != amount_cents
    ):

        current_app.logger.error(
            "Yoco checkout amount mismatch. "
            "creator=%s expected=%s received=%s",
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
        and provider_currency != "ZAR"
    ):

        current_app.logger.error(
            "Yoco checkout currency mismatch. "
            "creator=%s currency=%s",
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
    #
    # provider_reference stores the Yoco Checkout ID.
    #
    # This gives the future webhook something authoritative
    # to reconcile against.
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
            "Could not save pending Yoco payment "
            "for creator_account_id=%s "
            "checkout_id=%s",
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
# YOCO SUCCESS RETURN
# ============================================================

@payments_bp.route(
    "/yoco/success",
    methods=["GET"],
)
def yoco_success():

    # --------------------------------------------------------
    # IMPORTANT SECURITY RULE
    # --------------------------------------------------------
    #
    # Reaching this URL does NOT mean the payment succeeded.
    #
    # Anyone could manually open this URL.
    #
    # Only the signed Yoco webhook may mark a payment paid.
    # --------------------------------------------------------

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

    flash(
        (
            "Yoco has returned you to Kalxa. "
            "We are waiting for secure payment "
            "confirmation."
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
            "You have not been charged by this "
            "checkout."
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
