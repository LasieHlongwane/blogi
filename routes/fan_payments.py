# ============================================================
# KALXA CREATOR
# FAN PAYMENTS
#
# Free:      23% Kalxa commission
# Standard:   3% Kalxa commission
# Premium:    3% Kalxa commission
#
# PAYMENT PROVIDER: PAYSTACK
#
# IMPORTANT:
#
# FanPayment.platform_fee_cents stores the commission
# calculated when the payment is created.
#
# It must never be recalculated after a plan change.
#
# Paystack must apply the corresponding settlement split.
#
# ============================================================

import json
import re
import uuid

from datetime import datetime, timezone

from decimal import (
    Decimal,
    InvalidOperation,
)

from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    render_template,
    flash,
    current_app,
    abort,
)

from extensions import db

from models import (
    CreatorAccount,
    CreatorProfile,
    CreatorPayoutAccount,
    FundraisingCampaign,
    FanPayment,
)

from services.creator_monetization import (
    can_use_feature,
    calculate_commission_cents,
)

from services.paystack_service import (
    PaystackError,
    initialize_fan_payment,
    verify_transaction,
    verify_paystack_webhook,
)


# ============================================================
# BLUEPRINT
# ============================================================

fan_payments_bp = Blueprint(
    "fan_payments",
    __name__,
    url_prefix="/support",
)


# ============================================================
# CONSTANTS
# ============================================================

PAYMENT_PROVIDER = "paystack"

PAYMENT_CURRENCY = "ZAR"

PAYMENT_TYPE_SUPPORT = "support"

PAYMENT_TYPE_CAMPAIGN = "campaign"

MAX_FAN_PAYMENT_CENTS = 10_000_000

MIN_FAN_PAYMENT_CENTS = 100


# ============================================================
# TIME HELPERS
# ============================================================

def utc_now():

    return datetime.now(
        timezone.utc
    )


def as_utc(value):

    if value is None:
        return None

    if value.tzinfo is None:

        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


# ============================================================
# CREATOR HELPERS
# ============================================================

def creator_by_username_or_404(username):

    username = (
        str(username or "")
        .strip()
        .lower()
    )

    return (
        CreatorAccount.query
        .filter(
            db.func.lower(
                CreatorAccount.username
            ) == username,

            CreatorAccount.account_status == "active",
        )
        .first_or_404()
    )


def creator_profile_for(creator):

    return (
        CreatorProfile.query
        .filter_by(
            creator_account_id=creator.id
        )
        .first()
    )


def active_payout_account(creator):

    return (
        CreatorPayoutAccount.query
        .filter_by(
            creator_account_id=creator.id,
            provider=PAYMENT_PROVIDER,
            status="active",
        )
        .first()
    )


def payout_is_ready(payout_account):

    return bool(
        payout_account
        and payout_account.provider_subaccount_code
    )


def creator_campaign_or_404(
    creator,
    slug,
):

    return (
        FundraisingCampaign.query
        .filter_by(
            creator_account_id=creator.id,
            slug=slug,
        )
        .first_or_404()
    )


# ============================================================
# FEATURE ACCESS
# ============================================================

def creator_can_receive_coffee(creator):

    return can_use_feature(
        creator,
        "buy_me_coffee",
    )


def creator_can_fundraise(creator):

    return can_use_feature(
        creator,
        "fundraising",
    )


# ============================================================
# AMOUNT VALIDATION
# ============================================================

def parse_amount_to_cents(value):

    value = (
        str(value or "")
        .strip()
        .replace(",", "")
    )

    if not value:
        return None

    try:

        amount = Decimal(value)

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):

        return None

    if not amount.is_finite():
        return None

    if amount <= 0:
        return None

    cents = amount * Decimal("100")

    if cents != cents.to_integral_value():
        return None

    amount_cents = int(cents)

    if not (
        MIN_FAN_PAYMENT_CENTS
        <= amount_cents
        <= MAX_FAN_PAYMENT_CENTS
    ):

        return None

    return amount_cents


# ============================================================
# EMAIL VALIDATION
# ============================================================

def valid_email(value):

    value = (
        str(value or "")
        .strip()
    )

    if not value or len(value) > 255:
        return False

    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            value,
        )
    )


# ============================================================
# PAYMENT REFERENCES
# ============================================================

def new_payment_reference():

    return (
        "KALXA-FAN-"
        + uuid.uuid4().hex.upper()
    )


# ============================================================
# METADATA
# ============================================================

def get_metadata(data):

    metadata = (
        data.get("metadata")
        or {}
    )

    if isinstance(metadata, str):

        try:

            metadata = json.loads(
                metadata
            )

        except (
            TypeError,
            ValueError,
        ):

            metadata = {}

    if not isinstance(metadata, dict):
        return {}

    return metadata


# ============================================================
# COMMISSION
# ============================================================

def calculate_platform_fee(
    creator,
    amount_cents,
):

    return calculate_commission_cents(
        creator,
        amount_cents,
    )


def creator_receivable_cents(payment):

    return (
        payment.amount_cents
        - payment.platform_fee_cents
    )


# ============================================================
# SUPPORTER FORM DATA
# ============================================================

def get_supporter_details():

    email = (
        request.form
        .get("email", "")
        .strip()
        .lower()
    )

    name = (
        request.form
        .get("name", "")
        .strip()
    )[:120]

    message = (
        request.form
        .get("message", "")
        .strip()
    )[:500]

    is_anonymous = (
        request.form.get(
            "is_anonymous"
        ) == "on"
    )

    return {
        "email": email,
        "name": name,
        "message": message,
        "is_anonymous": is_anonymous,
    }


# ============================================================
# CREATE PENDING PAYMENT
# ============================================================

def create_pending_fan_payment(
    *,
    creator,
    amount_cents,
    supporter,
    payment_type,
    campaign=None,
):

    if payment_type not in {
        PAYMENT_TYPE_SUPPORT,
        PAYMENT_TYPE_CAMPAIGN,
    }:

        raise ValueError(
            "Unsupported fan payment type."
        )

    if payment_type == PAYMENT_TYPE_CAMPAIGN:

        if campaign is None:

            raise ValueError(
                "Campaign payment requires a campaign."
            )

        if campaign.creator_account_id != creator.id:

            raise ValueError(
                "Campaign does not belong to creator."
            )

    platform_fee_cents = (
        calculate_platform_fee(
            creator,
            amount_cents,
        )
    )

    if not (
        0 <= platform_fee_cents <= amount_cents
    ):

        raise ValueError(
            "Invalid platform commission."
        )

    payment = FanPayment(
        creator_account_id=creator.id,

        campaign_id=(
            campaign.id
            if campaign
            else None
        ),

        payment_type=payment_type,

        supporter_name=(
            supporter["name"]
            or None
        ),

        supporter_email=(
            supporter["email"]
        ),

        supporter_message=(
            supporter["message"]
            or None
        ),

        is_anonymous=(
            supporter["is_anonymous"]
        ),

        amount_cents=amount_cents,

        currency=PAYMENT_CURRENCY,

        platform_fee_cents=(
            platform_fee_cents
        ),

        provider=PAYMENT_PROVIDER,

        provider_reference=(
            new_payment_reference()
        ),

        status="pending",
    )

    db.session.add(payment)

    db.session.commit()

    return payment


# ============================================================
# INITIALIZE PAYSTACK CHECKOUT
# ============================================================

def start_paystack_checkout(
    *,
    payment,
    creator,
    payout_account,
):

    if not payout_is_ready(payout_account):

        raise PaystackError(
            "Creator payout account is not ready."
        )

    metadata = {
        "product_type": (
            "creator_support"
            if payment.payment_type == PAYMENT_TYPE_SUPPORT
            else "fundraising"
        ),

        "fan_payment_id": payment.id,

        "creator_account_id": creator.id,

        "creator_username": creator.username,

        "payment_type": payment.payment_type,

        "platform_fee_cents": (
            payment.platform_fee_cents
        ),

        "creator_receivable_cents": (
            creator_receivable_cents(payment)
        ),
    }

    if payment.campaign_id:

        metadata["campaign_id"] = (
            payment.campaign_id
        )

    checkout = initialize_fan_payment(
        email=payment.supporter_email,

        amount_cents=payment.amount_cents,

        reference=payment.provider_reference,

        subaccount_code=(
            payout_account.provider_subaccount_code
        ),

        platform_fee_cents=(
            payment.platform_fee_cents
        ),

        callback_url=url_for(
            "fan_payments.payment_return",
            _external=True,
        ),

        metadata=metadata,
    )

    if not isinstance(checkout, dict):

        raise PaystackError(
            "Invalid Paystack checkout response."
        )

    authorization_url = (
        checkout.get(
            "authorization_url"
        )
    )

    if not authorization_url:

        raise PaystackError(
            "Paystack did not return a payment URL."
        )

    return authorization_url


# ============================================================
# PAYSTACK TRANSACTION VALIDATION
# ============================================================

def validate_verified_transaction(
    payment,
    verified_data,
):
    """
    Validate the transaction independently against Paystack.

    Never trust a callback query parameter or webhook payload
    as proof of successful payment.

    Returns:
        (valid, reason, provider_transaction_id)
    """

    if not isinstance(verified_data, dict):

        return (
            False,
            "invalid_provider_response",
            None,
        )

    provider_status = str(
        verified_data.get("status")
        or ""
    ).strip().lower()

    if provider_status != "success":

        return (
            False,
            "provider_not_successful",
            None,
        )

    provider_reference = str(
        verified_data.get("reference")
        or ""
    ).strip()

    if (
        provider_reference
        != payment.provider_reference
    ):

        return (
            False,
            "reference_mismatch",
            None,
        )

    provider_currency = str(
        verified_data.get("currency")
        or ""
    ).strip().upper()

    if (
        provider_currency
        != PAYMENT_CURRENCY
    ):

        return (
            False,
            "currency_mismatch",
            None,
        )

    provider_amount = (
        verified_data.get("amount")
    )

    if type(provider_amount) is not int:

        return (
            False,
            "invalid_provider_amount",
            None,
        )

    if (
        provider_amount
        != payment.amount_cents
    ):

        return (
            False,
            "amount_mismatch",
            None,
        )

    if not (
        0
        <= payment.platform_fee_cents
        <= payment.amount_cents
    ):

        return (
            False,
            "invalid_stored_commission",
            None,
        )

    metadata = get_metadata(
        verified_data
    )

    if (
        str(metadata.get("creator_account_id"))
        != str(payment.creator_account_id)
    ):

        return (
            False,
            "creator_metadata_mismatch",
            None,
        )

    if (
        str(metadata.get("fan_payment_id"))
        != str(payment.id)
    ):

        return (
            False,
            "payment_metadata_mismatch",
            None,
        )

    if (
        metadata.get("payment_type")
        != payment.payment_type
    ):

        return (
            False,
            "payment_type_mismatch",
            None,
        )

    metadata_fee = metadata.get(
        "platform_fee_cents"
    )

    if metadata_fee is not None:

        if (
            str(metadata_fee)
            != str(payment.platform_fee_cents)
        ):

            return (
                False,
                "commission_metadata_mismatch",
                None,
            )

    metadata_receivable = metadata.get(
        "creator_receivable_cents"
    )

    if metadata_receivable is not None:

        if (
            str(metadata_receivable)
            != str(
                creator_receivable_cents(payment)
            )
        ):

            return (
                False,
                "receivable_metadata_mismatch",
                None,
            )

    if (
        payment.payment_type
        == PAYMENT_TYPE_CAMPAIGN
    ):

        if (
            str(metadata.get("campaign_id"))
            != str(payment.campaign_id)
        ):

            return (
                False,
                "campaign_metadata_mismatch",
                None,
            )

    provider_transaction_id = (
        verified_data.get("id")
    )

    if (
        provider_transaction_id is None
        or isinstance(
            provider_transaction_id,
            bool,
        )
    ):

        return (
            False,
            "missing_transaction_id",
            None,
        )

    provider_transaction_id = str(
        provider_transaction_id
    ).strip()

    if not provider_transaction_id:

        return (
            False,
            "empty_transaction_id",
            None,
        )

    return (
        True,
        "verified",
        provider_transaction_id,
    )


# ============================================================
# CONFIRM PAYMENT
# ============================================================

def confirm_fan_payment(
    reference,
    *,
    source,
):
    """
    Independently verify and confirm a Paystack transaction.

    Used by:
        - Paystack webhook
        - Payment return
        - Creator reconciliation

    All three paths use identical financial validation.

    Row locking and status checks make processing idempotent.
    """

    reference = str(
        reference or ""
    ).strip()

    if not reference:

        return (
            False,
            "missing_reference",
        )

    try:

        payment = (
            db.session.query(FanPayment)
            .filter(
                FanPayment.provider == PAYMENT_PROVIDER,
                FanPayment.provider_reference == reference,
            )
            .with_for_update()
            .first()
        )

        if payment is None:

            db.session.rollback()

            return (
                False,
                "payment_not_found",
            )

        payment_id = payment.id

        if payment.status == "paid":

            db.session.rollback()

            return (
                True,
                "already_paid",
            )

        if payment.status == "refunded":

            db.session.rollback()

            return (
                False,
                "payment_refunded",
            )

        # ----------------------------------------------------
        # VERIFY DIRECTLY WITH PAYSTACK
        # ----------------------------------------------------

        verified_data = verify_transaction(
            reference
        )

        valid, reason, transaction_id = (
            validate_verified_transaction(
                payment,
                verified_data,
            )
        )

        if not valid:

            db.session.rollback()

            current_app.logger.warning(
                (
                    "Kalxa fan payment verification rejected. "
                    "payment_id=%s source=%s reason=%s"
                ),
                payment_id,
                source,
                reason,
            )

            return (
                False,
                reason,
            )

        # ----------------------------------------------------
        # PREVENT TRANSACTION REUSE
        # ----------------------------------------------------

        duplicate_transaction = (
            FanPayment.query
            .filter(
                FanPayment.provider == PAYMENT_PROVIDER,
                FanPayment.provider_transaction_id
                == transaction_id,
                FanPayment.id != payment_id,
            )
            .first()
        )

        if duplicate_transaction:

            db.session.rollback()

            current_app.logger.error(
                (
                    "Paystack transaction reuse rejected. "
                    "payment_id=%s source=%s"
                ),
                payment_id,
                source,
            )

            return (
                False,
                "duplicate_transaction",
            )

        # ----------------------------------------------------
        # CONFIRM PAYMENT
        # ----------------------------------------------------

        payment.status = "paid"

        payment.provider_transaction_id = (
            transaction_id
        )

        payment.paid_at = utc_now()

        db.session.commit()

        current_app.logger.info(
            (
                "Kalxa fan payment confirmed. "
                "payment_id=%s creator_id=%s "
                "source=%s type=%s amount_cents=%s "
                "platform_fee_cents=%s"
            ),
            payment_id,
            payment.creator_account_id,
            source,
            payment.payment_type,
            payment.amount_cents,
            payment.platform_fee_cents,
        )

        return (
            True,
            "confirmed",
        )

    except PaystackError:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Paystack verification API failed. "
                "source=%s"
            ),
            source,
        )

        return (
            False,
            "provider_error",
        )

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            (
                "Unexpected fan payment confirmation error. "
                "source=%s"
            ),
            source,
        )

        return (
            False,
            "internal_error",
        )


# ============================================================
# PUBLIC SUPPORT PAGE
# ============================================================

@fan_payments_bp.route(
    "/<username>",
    methods=["GET"],
)
def creator_support(username):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_can_receive_coffee(
        creator
    ):

        abort(404)

    profile = (
        creator_profile_for(
            creator
        )
    )

    payout_account = (
        active_payout_account(
            creator
        )
    )

    return render_template(
        "public/support_creator.html",

        creator_account=creator,

        creator=profile,

        payout_ready=payout_is_ready(
            payout_account
        ),
    )


# ============================================================
# BUY ME A COFFEE PAYMENT
# ============================================================

@fan_payments_bp.route(
    "/<username>/pay",
    methods=["POST"],
)
def creator_support_pay(username):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_can_receive_coffee(
        creator
    ):

        abort(404)

    return_url = url_for(
        "fan_payments.creator_support",
        username=creator.username,
    )

    payout_account = (
        active_payout_account(
            creator
        )
    )

    if not payout_is_ready(
        payout_account
    ):

        flash(
            "This creator is not ready to receive payments yet.",
            "warning",
        )

        return redirect(return_url)

    amount_cents = (
        parse_amount_to_cents(
            request.form.get("amount")
        )
    )

    if amount_cents is None:

        flash(
            "Enter a valid support amount.",
            "error",
        )

        return redirect(return_url)

    supporter = get_supporter_details()

    if not valid_email(
        supporter["email"]
    ):

        flash(
            "Enter a valid email address.",
            "error",
        )

        return redirect(return_url)

    # --------------------------------------------------------
    # CREATE PENDING PAYMENT
    # --------------------------------------------------------

    try:

        payment = create_pending_fan_payment(
            creator=creator,
            amount_cents=amount_cents,
            supporter=supporter,
            payment_type=PAYMENT_TYPE_SUPPORT,
        )

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to create coffee FanPayment."
        )

        flash(
            "Payment could not be started.",
            "error",
        )

        return redirect(return_url)

    # --------------------------------------------------------
    # INITIALIZE PAYSTACK CHECKOUT
    # --------------------------------------------------------

    try:

        authorization_url = (
            start_paystack_checkout(
                payment=payment,
                creator=creator,
                payout_account=payout_account,
            )
        )

    except (
        PaystackError,
        TypeError,
        ValueError,
    ):

        current_app.logger.exception(
            "Paystack coffee checkout failed. payment_id=%s",
            payment.id,
        )

        try:

            locked_payment = (
                db.session.query(FanPayment)
                .filter_by(id=payment.id)
                .with_for_update()
                .first()
            )

            if (
                locked_payment
                and locked_payment.status == "pending"
            ):

                locked_payment.status = "failed"

            db.session.commit()

        except Exception:

            db.session.rollback()

            current_app.logger.exception(
                "Unable to mark failed checkout."
            )

        flash(
            "We could not open the payment page.",
            "error",
        )

        return redirect(return_url)

    return redirect(
        authorization_url,
        code=303,
    )


# ============================================================
# CAMPAIGN PAGE
# ============================================================

@fan_payments_bp.route(
    "/<username>/campaigns/<slug>",
    methods=["GET"],
)
def campaign_detail(
    username,
    slug,
):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_can_fundraise(
        creator
    ):

        abort(404)

    campaign = (
        creator_campaign_or_404(
            creator,
            slug,
        )
    )

    if campaign.status not in {
        "active",
        "completed",
    }:

        abort(404)

    raised_cents = int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    FanPayment.amount_cents
                ),
                0,
            )
        )
        .filter(
            FanPayment.creator_account_id == creator.id,
            FanPayment.campaign_id == campaign.id,
            FanPayment.payment_type == PAYMENT_TYPE_CAMPAIGN,
            FanPayment.status == "paid",
        )
        .scalar()
        or 0
    )

    supporter_count = (
        FanPayment.query
        .filter_by(
            creator_account_id=creator.id,
            campaign_id=campaign.id,
            payment_type=PAYMENT_TYPE_CAMPAIGN,
            status="paid",
        )
        .count()
    )

    progress_percent = 0

    if campaign.goal_amount_cents:

        progress_percent = min(
            100,
            round(
                (
                    raised_cents
                    / campaign.goal_amount_cents
                ) * 100,
                1,
            ),
        )

    payout_account = (
        active_payout_account(
            creator
        )
    )

    return render_template(
        "public/fundraising_campaign.html",

        creator_account=creator,

        creator=creator_profile_for(
            creator
        ),

        campaign=campaign,

        raised_cents=raised_cents,

        supporter_count=supporter_count,

        progress_percent=progress_percent,

        payout_ready=payout_is_ready(
            payout_account
        ),
    )


# ============================================================
# CAMPAIGN PAYMENT
# ============================================================

@fan_payments_bp.route(
    "/<username>/campaigns/<slug>/pay",
    methods=["POST"],
)
def campaign_pay(
    username,
    slug,
):

    creator = (
        creator_by_username_or_404(
            username
        )
    )

    if not creator_can_fundraise(
        creator
    ):

        abort(404)

    campaign = (
        creator_campaign_or_404(
            creator,
            slug,
        )
    )

    return_url = url_for(
        "fan_payments.campaign_detail",
        username=creator.username,
        slug=campaign.slug,
    )

    if campaign.status != "active":

        flash(
            "This campaign is not accepting contributions.",
            "warning",
        )

        return redirect(return_url)

    now = utc_now()

    starts_at = as_utc(
        campaign.starts_at
    )

    ends_at = as_utc(
        campaign.ends_at
    )

    if starts_at and starts_at > now:

        flash(
            "This campaign has not started yet.",
            "warning",
        )

        return redirect(return_url)

    if ends_at and ends_at < now:

        flash(
            "This campaign has ended.",
            "warning",
        )

        return redirect(return_url)

    payout_account = (
        active_payout_account(
            creator
        )
    )

    if not payout_is_ready(
        payout_account
    ):

        flash(
            "This campaign cannot receive payments yet.",
            "warning",
        )

        return redirect(return_url)

    amount_cents = (
        parse_amount_to_cents(
            request.form.get("amount")
        )
    )

    if amount_cents is None:

        flash(
            "Enter a valid contribution amount.",
            "error",
        )

        return redirect(return_url)

    supporter = get_supporter_details()

    if not valid_email(
        supporter["email"]
    ):

        flash(
            "Enter a valid email address.",
            "error",
        )

        return redirect(return_url)

    try:

        payment = create_pending_fan_payment(
            creator=creator,
            amount_cents=amount_cents,
            supporter= support er,
            payment_type=PAYMENT_TYPE_CAMPAIGN,
            campaign=campaign,
        )

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unable to create campaign FanPayment."
        )

        flash(
            "Contribution could not be started.",
            "error",
        )

        return redirect(return_url)

    try:

        authorization_url = (
            start_paystack_checkout(
                payment=payment,
                creator=creator,
                payout_account=payout_account,
            )
        )

    except (
        PaystackError,
        TypeError,
        ValueError,
    ):

        current_app.logger.exception(
            "Paystack campaign checkout failed. payment_id=%s",
            payment.id,
        )

        try:

            locked_payment = (
                db.session.query(FanPayment)
                .filter_by(id=payment.id)
                .with_for_update()
                .first()
            )

            if (
                locked_payment
                and locked_payment.status == "pending"
            ):

                locked_payment.status = "failed"

            db.session.commit()

        except Exception:

            db.session.rollback()

        flash(
            "We could not open the payment page.",
            "error",
        )

        return redirect(return_url)

    return redirect(
        authorization_url,
        code=303,
    )


# ============================================================
# PAYMENT RETURN
# ============================================================

@fan_payments_bp.route(
    "/payment/return",
    methods=["GET"],
)
def payment_return():

    reference = (
        request.args
        .get("reference", "")
        .strip()
    )

    if not reference:

        return render_template(
            "public/payment_result.html",
            payment=None,
            payment_confirmed=False,
            message="We could not identify this payment.",
        )

    payment = (
        FanPayment.query
        .filter_by(
            provider=PAYMENT_PROVIDER,
            provider_reference=reference,
        )
        .first()
    )

    if payment is None:
        abort(404)

    # --------------------------------------------------------
    # VERIFY TRANSACTION ON RETURN
    # --------------------------------------------------------

    confirmed, reason = (
        confirm_fan_payment(
            reference,
            source="browser_return",
        )
    )

    # Refresh after verification.
    db.session.expire_all()

    payment = (
        FanPayment.query
        .filter_by(
            provider=PAYMENT_PROVIDER,
            provider_reference=reference,
        )
        .first()
    )

    if payment.status == "paid":

        return render_template(
            "public/payment_result.html",
            payment=payment,
            payment_confirmed=True,
            message="Payment confirmed. Thank you for your support!",
        )

    if reason in {
        "provider_error",
        "internal_error",
    }:

        message = (
            "Your payment could not be confirmed right now. "
            "Please check again shortly."
        )

    elif reason == "provider_not_successful":

        message = (
            "Your payment has not yet been confirmed by Paystack."
        )

    else:

        message = (
            "Your payment is being verified. "
            "Please check again shortly."
        )

    return render_template(
        "public/payment_result.html",
        payment=payment,
        payment_confirmed=False,
        message=message,
    )


# ============================================================
# PAYSTACK WEBHOOK
# ============================================================

@fan_payments_bp.route(
    "/paystack/webhook",
    methods=["POST"],
)
def paystack_webhook():

    raw_body = request.get_data(
        cache=True,
        as_text=False,
    )

    signature = request.headers.get(
        "x-paystack-signature",
        "",
    )

    # --------------------------------------------------------
    # VERIFY SIGNATURE
    # --------------------------------------------------------

    try:

        verified = verify_paystack_webhook(
            raw_body,
            signature,
        )

    except PaystackError:

        current_app.logger.exception(
            "Paystack webhook signature verification error."
        )

        return "", 500

    if not verified:

        current_app.logger.warning(
            "Rejected invalid Paystack webhook."
        )

        return "", 401

    event = request.get_json(
        silent=True
    )

    if not isinstance(event, dict):

        return "", 400

    if event.get("event") != "charge.success":

        return "", 200

    event_data = (
        event.get("data")
        or {}
    )

    if not isinstance(event_data, dict):

        return "", 400

    reference = str(
        event_data.get("reference")
        or ""
    ).strip()

    if not reference:

        current_app.logger.warning(
            "Paystack webhook missing transaction reference."
        )

        return "", 200

    # --------------------------------------------------------
    # CONFIRM USING SHARED VERIFICATION
    # --------------------------------------------------------

    confirmed, reason = (
        confirm_fan_payment(
            reference,
            source="webhook",
        )
    )

    if confirmed:

        return "", 200

    if reason in {
        "provider_error",
        "internal_error",
    }:

        return "", 500

    current_app.logger.warning(
        (
            "Paystack webhook did not confirm payment. "
            "reason=%s"
        ),
        reason,
    )

    return "", 200


# ============================================================
# CREATOR PAYMENT RECONCILIATION
# ============================================================

@fan_payments_bp.route(
    "/reconcile/<int:payment_id>",
    methods=["POST"],
)
def reconcile_creator_payment(payment_id):
    """
    Reconcile an existing fan payment without creating
    another Paystack charge.

    SECURITY:
    Requires authenticated creator session.
    The payment must belong to that creator.

    IMPORTANT:
    This endpoint must be protected by your existing
    Studio authentication system.
    """

    from routes.studio import (
        current_creator_account,
    )

    account = current_creator_account()

    if account is None:

        abort(403)

    payment = (
        FanPayment.query
        .filter_by(
            id=payment_id,
            creator_account_id=account.id,
            provider=PAYMENT_PROVIDER,
        )
        .first_or_404()
    )

    if payment.status == "refunded":

        flash(
            "Refunded payments cannot be reconciled.",
            "warning",
        )

    elif payment.status == "paid":

        flash(
            "This payment is already confirmed.",
            "success",
        )

    else:

        confirmed, reason = (
            confirm_fan_payment(
                payment.provider_reference,
                source="creator_reconciliation",
            )
        )

        if confirmed:

            flash(
                "Payment successfully verified with Paystack.",
                "success",
            )

        else:

            flash(
                "Payment is not yet confirmed. "
                "Please try again later.",
                "warning",
            )

    return redirect(
        url_for(
            "studio.support_setup"
        )
    )
