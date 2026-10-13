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
from decimal import Decimal, InvalidOperation

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

    if not isinstance(metadata
