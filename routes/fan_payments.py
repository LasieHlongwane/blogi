# ============================================================
# KALXA CREATOR
# FAN PAYMENTS
#
# Free:     23% Kalxa commission
# Standard:  3% Kalxa commission
# Premium:   3% Kalxa commission
#
# PAYMENT PROVIDER: PAYSTACK
#
# IMPORTANT:
#
# FanPayment.platform_fee_cents stores the commission
# calculated when the payment is created.
#
# It must not be recalculated after a creator changes plans.
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
    ROUND_HALF_UP,
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

# This is a configurable application limit, not a statement
# of Paystack's maximum supported transaction amount.

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

    # Reject fractional cents rather than silently
    # changing the amount entered by the supporter.

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

    """
    Calculate Kalxa's commission using the creator's
    verified entitlement at checkout creation.

    Free:     23%
    Standard:  3%
    Premium:   3%

    The calculated fee is persisted on FanPayment.

    It must not change if the creator upgrades later.
    """

    return calculate_commission_cents(
        creator,
        amount_cents,
    )


def creator_receivable_cents(payment):

    """
    Gross contribution less Kalxa's commission.

    This excludes any separate Paystack processing fees.
    """

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

    """
    Create an immutable financial snapshot.

    Important:

    The platform fee is calculated BEFORE the payment
    is sent to Paystack.

    A creator upgrading tomorrow must not change the
    commission on a payment created today.
    """

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

    reference = new_payment_reference()

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

        provider_reference=reference,

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

    """
    Initialize a Paystack transaction.

    REQUIRED PAYSTACK SERVICE CONTRACT:

    initialize_fan_payment must accept:

        platform_fee_cents

    and must arrange the provider-side settlement so that
    Kalxa receives its commission.

    Do not remove this parameter merely to make an older
    paystack_service.py implementation work.

    Paystack's exact split configuration and processing-fee
    bearer must be implemented and verified in that service.
    """

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
    # CREATE LOCAL FINANCIAL RECORD
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
    # START PAYSTACK
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

        # The provider checkout was not successfully
        # initialized. Keep the audit record but mark
        # it failed unless a concurrent webhook already
        # confirmed payment.

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
            supporter=supporter,
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

    if not payment:

        abort(404)

    # Never confirm payment from browser query parameters.

    return render_template(
        "public/payment_result.html",

        payment=payment,

        payment_confirmed=(
            payment.status == "paid"
        ),

        message=(
            "Payment confirmed. Thank you!"
            if payment.status == "paid"
            else "Your payment is being confirmed."
        ),
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
            "Paystack webhook verification error."
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

        return "", 200

    # --------------------------------------------------------
    # LOCK PAYMENT
    # --------------------------------------------------------

    try:

        payment = (
            db.session.query(
                FanPayment
            )
            .filter(
                FanPayment.provider == PAYMENT_PROVIDER,
                FanPayment.provider_reference == reference,
            )
            .with_for_update()
            .first()
        )

        if not payment:

            db.session.rollback()

            current_app.logger.warning(
                "Unknown Paystack reference: %s",
                reference,
            )

            return "", 200

        # ----------------------------------------------------
        # IDEMPOTENCY
        # ----------------------------------------------------

        if payment.status == "paid":

            db.session.rollback()

            return "", 200

        if payment.status == "refunded":

            db.session.rollback()

            current_app.logger.warning(
                "Ignoring charge.success for refunded payment %s",
                payment.id,
            )

            return "", 200

        # ----------------------------------------------------
        # VERIFY DIRECTLY WITH PAYSTACK
        # ----------------------------------------------------

        verified_data = verify_transaction(
            reference
        )

        if not isinstance(verified_data, dict):

            db.session.rollback()

            return "", 500

        provider_status = str(
            verified_data.get("status")
            or ""
        ).strip().lower()

        provider_reference = str(
            verified_data.get("reference")
            or ""
        ).strip()

        provider_currency = str(
            verified_data.get("currency")
            or ""
        ).strip().upper()

        provider_amount = (
            verified_data.get("amount")
        )

        if (
            type(provider_amount) is not int
        ):

            db.session.rollback()

            current_app.logger.error(
                "Invalid Paystack amount for payment %s",
                payment.id,
            )

            return "", 200

        # ----------------------------------------------------
        # FINANCIAL VALIDATION
        # ----------------------------------------------------

        if provider_status != "success":

            db.session.rollback()

            return "", 200

        if provider_reference != payment.provider_reference:

            db.session.rollback()

            current_app.logger.error(
                "Paystack reference mismatch for payment %s",
                payment.id,
            )

            return "", 200

        if provider_currency != PAYMENT_CURRENCY:

            db.session.rollback()

            current_app.logger.error(
                "Paystack currency mismatch for payment %s",
                payment.id,
            )

            return "", 200

        if provider_amount != payment.amount_cents:

            db.session.rollback()

            current_app.logger.error(
                "Paystack amount mismatch for payment %s",
                payment.id,
            )

            return "", 200

        # ----------------------------------------------------
        # VALIDATE STORED COMMISSION
        # ----------------------------------------------------

        if not (
            0
            <= payment.platform_fee_cents
            <= payment.amount_cents
        ):

            db.session.rollback()

            current_app.logger.error(
                "Invalid commission on payment %s",
                payment.id,
            )

            return "", 200

        # ----------------------------------------------------
        # METADATA VALIDATION
        # ----------------------------------------------------

        metadata = get_metadata(
            verified_data
        )

        if (
            str(metadata.get("creator_account_id"))
            != str(payment.creator_account_id)
        ):

            db.session.rollback()

            current_app.logger.error(
                "Creator metadata mismatch: payment %s",
                payment.id,
            )

            return "", 200

        if (
            str(metadata.get("fan_payment_id"))
            != str(payment.id)
        ):

            db.session.rollback()

            current_app.logger.error(
                "Payment metadata mismatch: payment %s",
                payment.id,
            )

            return "", 200

        if (
            metadata.get("payment_type")
            != payment.payment_type
        ):

            db.session.rollback()

            current_app.logger.error(
                "Payment type mismatch: payment %s",
                payment.id,
            )

            return "", 200

        # ----------------------------------------------------
        # COMMISSION METADATA
        # ----------------------------------------------------

        metadata_fee = metadata.get(
            "platform_fee_cents"
        )

        # Legacy payments may not contain this metadata.
        # New payments must include it.

        if metadata_fee is not None:

            if (
                str(metadata_fee)
                != str(payment.platform_fee_cents)
            ):

                db.session.rollback()

                current_app.logger.error(
                    "Commission metadata mismatch: payment %s",
                    payment.id,
                )

                return "", 200

        # ----------------------------------------------------
        # CAMPAIGN INTEGRITY
        # ----------------------------------------------------

        if payment.payment_type == PAYMENT_TYPE_CAMPAIGN:

            if (
                str(metadata.get("campaign_id"))
                != str(payment.campaign_id)
            ):

                db.session.rollback()

                current_app.logger.error(
                    "Campaign metadata mismatch: payment %s",
                    payment.id,
                )

                return "", 200

        # ----------------------------------------------------
        # PROVIDER TRANSACTION ID
        # ----------------------------------------------------

        provider_transaction_id = (
            verified_data.get("id")
        )

        if provider_transaction_id is None:

            db.session.rollback()

            current_app.logger.error(
                "Missing Paystack transaction ID: payment %s",
                payment.id,
            )

            return "", 200

        provider_transaction_id = str(
            provider_transaction_id
        )

        # ----------------------------------------------------
        # PREVENT TRANSACTION REUSE
        # ----------------------------------------------------

        duplicate_transaction = (
            FanPayment.query
            .filter(
                FanPayment.provider_transaction_id
                == provider_transaction_id,

                FanPayment.id != payment.id,
            )
            .first()
        )

        if duplicate_transaction:

            db.session.rollback()

            current_app.logger.error(
                "Paystack transaction ID already used."
            )

            return "", 200

        # ----------------------------------------------------
        # MARK PAID
        # ----------------------------------------------------

        payment.status = "paid"

        payment.provider_transaction_id = (
            provider_transaction_id
        )

        payment.paid_at = utc_now()

        db.session.commit()

        current_app.logger.info(
            (
                "Kalxa fan payment confirmed. "
                "payment_id=%s creator_id=%s "
                "type=%s amount_cents=%s "
                "platform_fee_cents=%s"
            ),
            payment.id,
            payment.creator_account_id,
            payment.payment_type,
            payment.amount_cents,
            payment.platform_fee_cents,
        )

        return "", 200

    except PaystackError:

        db.session.rollback()

        current_app.logger.exception(
            "Paystack verification failed."
        )

        return "", 500

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Unexpected Paystack webhook error."
        )

        return "", 500
