"""Kalxa Creator: Paystack fan contributions and fundraising."""

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from flask import (
    Blueprint, abort, current_app, flash, redirect,
    render_template, request, url_for,
)

from extensions import db
from models import (
    CreatorAccount, CreatorProfile, CreatorPayoutAccount,
    FanPayment, FundraisingCampaign,
)
from services.creator_monetization import (
    calculate_commission_cents, can_use_feature,
)
from services.paystack_service import (
    PaystackError, initialize_fan_payment,
    verify_paystack_webhook, verify_transaction,
)

fan_payments_bp = Blueprint("fan_payments", __name__, url_prefix="/support")

PAYMENT_PROVIDER = "paystack"
PAYMENT_CURRENCY = "ZAR"
PAYMENT_TYPE_SUPPORT = "support"
PAYMENT_TYPE_CAMPAIGN = "campaign"
MIN_FAN_PAYMENT_CENTS = 100
MAX_FAN_PAYMENT_CENTS = 10_000_000
FAN_REFERENCE_RE = re.compile(r"KALXA-FAN-[A-F0-9]{32}\Z")


def utc_now():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def creator_by_username_or_404(username):
    return CreatorAccount.query.filter(
        db.func.lower(CreatorAccount.username) == str(username or "").strip().lower(),
        CreatorAccount.account_status == "active",
    ).first_or_404()


def creator_profile_for(creator):
    return CreatorProfile.query.filter_by(creator_account_id=creator.id).first()


def active_payout_account(creator):
    return CreatorPayoutAccount.query.filter_by(
        creator_account_id=creator.id,
        provider=PAYMENT_PROVIDER,
        status="active",
    ).first()


def payout_is_ready(payout_account):
    return bool(payout_account and payout_account.provider_subaccount_code)


def creator_campaign_or_404(creator, slug):
    return FundraisingCampaign.query.filter_by(
        creator_account_id=creator.id, slug=slug
    ).first_or_404()


def creator_can_receive_coffee(creator):
    return can_use_feature(creator, "buy_me_coffee")


def creator_can_fundraise(creator):
    return can_use_feature(creator, "fundraising")


def parse_amount_to_cents(value):
    value = str(value or "").strip().replace(",", "")
    if not value:
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite() or amount <= 0:
        return None
    cents = amount * 100
    if cents != cents.to_integral_value():
        return None
    cents = int(cents)
    return cents if MIN_FAN_PAYMENT_CENTS <= cents <= MAX_FAN_PAYMENT_CENTS else None


def valid_email(value):
    value = str(value or "").strip()
    return bool(
        value and len(value) <= 255
        and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value)
    )


def new_payment_reference():
    return "KALXA-FAN-" + uuid.uuid4().hex.upper()


def get_metadata(data):
    metadata = data.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            return {}
    return metadata if isinstance(metadata, dict) else {}


def calculate_platform_fee(creator, amount_cents):
    return calculate_commission_cents(creator, amount_cents)


def creator_receivable_cents(payment):
    return payment.amount_cents - payment.platform_fee_cents


def get_supporter_details():
    return {
        "email": request.form.get("email", "").strip().lower(),
        "name": request.form.get("name", "").strip()[:120],
        "message": request.form.get("message", "").strip()[:500],
        "is_anonymous": request.form.get("is_anonymous") == "on",
    }


def create_pending_fan_payment(
    *, creator, amount_cents, supporter, payment_type, campaign=None
):
    if payment_type not in (PAYMENT_TYPE_SUPPORT, PAYMENT_TYPE_CAMPAIGN):
        raise ValueError("Unsupported payment type")
    if payment_type == PAYMENT_TYPE_CAMPAIGN:
        if campaign is None or campaign.creator_account_id != creator.id:
            raise ValueError("Campaign must belong to creator")
    elif campaign is not None:
        raise ValueError("Coffee payments cannot belong to campaigns")

    platform_fee_cents = calculate_platform_fee(creator, amount_cents)
    if (
        type(platform_fee_cents) is not int
        or not 0 <= platform_fee_cents <= amount_cents
    ):
        raise ValueError("Invalid platform commission")

    payment = FanPayment(
        creator_account_id=creator.id,
        campaign_id=campaign.id if campaign else None,
        payment_type=payment_type,
        supporter_name=supporter["name"] or None,
        supporter_email=supporter["email"],
        supporter_message=supporter["message"] or None,
        is_anonymous=supporter["is_anonymous"],
        amount_cents=amount_cents,
        currency=PAYMENT_CURRENCY,
        platform_fee_cents=platform_fee_cents,
        provider=PAYMENT_PROVIDER,
        provider_reference=new_payment_reference(),
        status="pending",
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def start_paystack_checkout(*, payment, creator, payout_account):
    if not payout_is_ready(payout_account):
        raise PaystackError("Creator payout account is not ready")

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
        "platform_fee_cents": payment.platform_fee_cents,
        "creator_receivable_cents": creator_receivable_cents(payment),
    }
    if payment.campaign_id is not None:
        metadata["campaign_id"] = payment.campaign_id

    checkout = initialize_fan_payment(
        email=payment.supporter_email,
        amount_cents=payment.amount_cents,
        reference=payment.provider_reference,
        subaccount_code=payout_account.provider_subaccount_code,
        platform_fee_cents=payment.platform_fee_cents,
        callback_url=url_for("fan_payments.payment_return", _external=True),
        metadata=metadata,
    )
    if not isinstance(checkout, dict):
        raise PaystackError("Invalid Paystack checkout response")
    checkout_url = checkout.get("authorization_url")
    if not isinstance(checkout_url, str):
        raise PaystackError("Missing Paystack checkout URL")
    parsed = urlsplit(checkout_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "checkout.paystack.com"
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PaystackError("Unexpected Paystack checkout URL")
    return checkout_url


def _matches_id(actual, expected):
    return actual is not None and not isinstance(actual, bool) and str(actual) == str(expected)


def validate_verified_transaction(payment, verified_data):
    """Return (valid, reason, transaction_id) for verified Paystack transaction data.

    verify_transaction() must return the transaction `data` object, not the
    outer Paystack API envelope.
    """
    if not isinstance(verified_data, dict):
        return False, "invalid_provider_response", None
    if verified_data.get("status") != "success":
        return False, "provider_not_successful", None
    if verified_data.get("reference") != payment.provider_reference:
        return False, "reference_mismatch", None
    if verified_data.get("currency") != PAYMENT_CURRENCY:
        return False, "currency_mismatch", None
    if type(verified_data.get("amount")) is not int:
        return False, "invalid_provider_amount", None
    if verified_data["amount"] != payment.amount_cents:
        return False, "amount_mismatch", None
    if payment.provider != PAYMENT_PROVIDER or payment.currency != PAYMENT_CURRENCY:
        return False, "stored_provider_mismatch", None
    if (
        type(payment.platform_fee_cents) is not int
        or not 0 <= payment.platform_fee_cents <= payment.amount_cents
    ):
        return False, "invalid_stored_commission", None

    metadata = get_metadata(verified_data)
    required_metadata = {
        "fan_payment_id": payment.id,
        "creator_account_id": payment.creator_account_id,
        "payment_type": payment.payment_type,
        "platform_fee_cents": payment.platform_fee_cents,
        "creator_receivable_cents": creator_receivable_cents(payment),
        "product_type": (
            "creator_support"
            if payment.payment_type == PAYMENT_TYPE_SUPPORT
            else "fundraising"
        ),
    }
    for field, expected in required_metadata.items():
        if not _matches_id(metadata.get(field), expected):
            return False, f"{field}_mismatch", None

    if payment.payment_type == PAYMENT_TYPE_CAMPAIGN:
        if not _matches_id(metadata.get("campaign_id"), payment.campaign_id):
            return False, "campaign_id_mismatch", None
    elif payment.payment_type == PAYMENT_TYPE_SUPPORT:
        if payment.campaign_id is not None:
            return False, "unexpected_campaign", None
    else:
        return False, "invalid_payment_type", None

    transaction_id = verified_data.get("id")
    if transaction_id is None or isinstance(transaction_id, bool):
        return False, "missing_transaction_id", None
    transaction_id = str(transaction_id).strip()
    if not transaction_id:
        return False, "missing_transaction_id", None
    return True, "verified", transaction_id


def confirm_fan_payment(reference, *, source):
    """Verify and atomically mark a payment paid; safe for duplicate calls."""
    reference = str(reference or "").strip()
    if not FAN_REFERENCE_RE.fullmatch(reference):
        return False, "invalid_reference"

    try:
        payment = db.session.query(FanPayment).filter(
            FanPayment.provider == PAYMENT_PROVIDER,
            FanPayment.provider_reference == reference,
        ).with_for_update().first()
        if payment is None:
            db.session.rollback()
            return False, "payment_not_found"
        payment_id = payment.id
        if payment.status == "paid":
            db.session.rollback()
            return True, "already_paid"
        if payment.status == "refunded":
            db.session.rollback()
            return False, "payment_refunded"

        verified_data = verify_transaction(reference)
        valid, reason, transaction_id = validate_verified_transaction(
            payment, verified_data
        )
        if not valid:
            db.session.rollback()
            current_app.logger.warning(
                "Fan payment rejected payment_id=%s source=%s reason=%s",
                payment_id, source, reason,
            )
            return False, reason

        duplicate = FanPayment.query.filter(
            FanPayment.provider == PAYMENT_PROVIDER,
            FanPayment.provider_transaction_id == transaction_id,
            FanPayment.id != payment_id,
        ).first()
        if duplicate is not None:
            db.session.rollback()
            current_app.logger.error("Duplicate provider transaction payment_id=%s", payment_id)
            return False, "duplicate_transaction"

        payment.status = "paid"
        payment.provider_transaction_id = transaction_id
        payment.paid_at = utc_now()
        creator_id = payment.creator_account_id
        amount_cents = payment.amount_cents
        fee_cents = payment.platform_fee_cents
        db.session.commit()
        current_app.logger.info(
            "Fan payment confirmed payment_id=%s creator_id=%s source=%s amount_cents=%s fee_cents=%s",
            payment_id, creator_id, source, amount_cents, fee_cents,
        )
        return True, "confirmed"
    except PaystackError:
        db.session.rollback()
        current_app.logger.exception("Paystack verification error source=%s", source)
        return False, "provider_error"
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Fan payment confirmation error source=%s", source)
        return False, "internal_error"


def _begin_payment(*, creator, payout_account, amount_cents, supporter,
                   payment_type, return_url, campaign=None):
    try:
        payment = create_pending_fan_payment(
            creator=creator,
            amount_cents=amount_cents,
            supporter=supporter,
            payment_type=payment_type,
            campaign=campaign,
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to create FanPayment")
        flash("Payment could not be started.", "error")
        return redirect(return_url)

    try:
        checkout_url = start_paystack_checkout(
            payment=payment, creator=creator, payout_account=payout_account
        )
    except (PaystackError, TypeError, ValueError):
        # A network timeout does not prove the transaction wasn't created.
        # Preserve pending so a later verified callback can reconcile it.
        db.session.rollback()
        current_app.logger.exception(
            "Paystack checkout initialization failed payment_id=%s", payment.id
        )
        flash("We could not open the payment page. Please try later.", "error")
        return redirect(return_url)
    return redirect(checkout_url, code=303)


@fan_payments_bp.route("/<username>", methods=["GET"])
def creator_support(username):
    creator = creator_by_username_or_404(username)
    if not creator_can_receive_coffee(creator):
        abort(404)
    return render_template(
        "public/support_creator.html",
        creator_account=creator,
        creator=creator_profile_for(creator),
        payout_ready=payout_is_ready(active_payout_account(creator)),
    )


@fan_payments_bp.route("/<username>/pay", methods=["POST"])
def creator_support_pay(username):
    creator = creator_by_username_or_404(username)
    if not creator_can_receive_coffee(creator):
        abort(404)
    return_url = url_for("fan_payments.creator_support", username=creator.username)
    payout = active_payout_account(creator)
    if not payout_is_ready(payout):
        flash("This creator is not ready to receive payments yet.", "warning")
        return redirect(return_url)
    amount_cents = parse_amount_to_cents(request.form.get("amount"))
    if amount_cents is None:
        flash("Enter a valid support amount.", "error")
        return redirect(return_url)
    supporter = get_supporter_details()
    if not valid_email(supporter["email"]):
        flash("Enter a valid email address.", "error")
        return redirect(return_url)
    return _begin_payment(
        creator=creator, payout_account=payout,
        amount_cents=amount_cents, supporter=supporter,
        payment_type=PAYMENT_TYPE_SUPPORT, return_url=return_url,
    )


@fan_payments_bp.route("/<username>/campaigns/<slug>", methods=["GET"])
def campaign_detail(username, slug):
    creator = creator_by_username_or_404(username)
    if not creator_can_fundraise(creator):
        abort(404)
    campaign = creator_campaign_or_404(creator, slug)
    if campaign.status not in {"active", "completed"}:
        abort(404)
    raised_cents = int(db.session.query(
        db.func.coalesce(db.func.sum(FanPayment.amount_cents), 0)
    ).filter(
        FanPayment.creator_account_id == creator.id,
        FanPayment.campaign_id == campaign.id,
        FanPayment.payment_type == PAYMENT_TYPE_CAMPAIGN,
        FanPayment.status == "paid",
    ).scalar() or 0)
    supporter_count = FanPayment.query.filter_by(
        creator_account_id=creator.id,
        campaign_id=campaign.id,
        payment_type=PAYMENT_TYPE_CAMPAIGN,
        status="paid",
    ).count()
    progress_percent = 0
    if campaign.goal_amount_cents:
        progress_percent = min(
            100, round(raised_cents / campaign.goal_amount_cents * 100, 1)
        )
    return render_template(
        "public/fundraising_campaign.html",
        creator_account=creator,
        creator=creator_profile_for(creator),
        campaign=campaign,
        raised_cents=raised_cents,
        supporter_count=supporter_count,
        progress_percent=progress_percent,
        payout_ready=payout_is_ready(active_payout_account(creator)),
    )


@fan_payments_bp.route("/<username>/campaigns/<slug>/pay", methods=["POST"])
def campaign_pay(username, slug):
    creator = creator_by_username_or_404(username)
    if not creator_can_fundraise(creator):
        abort(404)
    campaign = creator_campaign_or_404(creator, slug)
    return_url = url_for(
        "fan_payments.campaign_detail", username=creator.username, slug=campaign.slug
    )
    if campaign.status != "active":
        flash("This campaign is not accepting contributions.", "warning")
        return redirect(return_url)
    now = utc_now()
    starts_at = as_utc(campaign.starts_at)
    ends_at = as_utc(campaign.ends_at)
    if starts_at and starts_at > now:
        flash("This campaign has not started yet.", "warning")
        return redirect(return_url)
    if ends_at and ends_at < now:
        flash("This campaign has ended.", "warning")
        return redirect(return_url)
    payout = active_payout_account(creator)
    if not payout_is_ready(payout):
        flash("This campaign cannot receive payments yet.", "warning")
        return redirect(return_url)
    amount_cents = parse_amount_to_cents(request.form.get("amount"))
    if amount_cents is None:
        flash("Enter a valid contribution amount.", "error")
        return redirect(return_url)
    supporter = get_supporter_details()
    if not valid_email(supporter["email"]):
        flash("Enter a valid email address.", "error")
        return redirect(return_url)
    return _begin_payment(
        creator=creator, payout_account=payout,
        amount_cents=amount_cents, supporter=supporter,
        payment_type=PAYMENT_TYPE_CAMPAIGN,
        campaign=campaign, return_url=return_url,
    )


@fan_payments_bp.route("/payment/return", methods=["GET"])
def payment_return():
    reference = request.args.get("reference", "").strip()
    if not FAN_REFERENCE_RE.fullmatch(reference):
        return render_template(
            "public/payment_result.html", payment=None,
            payment_confirmed=False,
            message="We could not identify this payment.",
        )
    payment = FanPayment.query.filter_by(
        provider=PAYMENT_PROVIDER, provider_reference=reference
    ).first()
    if payment is None:
        abort(404)
    confirmed, reason = confirm_fan_payment(reference, source="browser_return")
    db.session.expire_all()
    payment = FanPayment.query.filter_by(
        provider=PAYMENT_PROVIDER, provider_reference=reference
    ).first_or_404()
    if payment.status == "paid":
        message = "Payment confirmed. Thank you for your support!"
    elif reason in {"provider_error", "internal_error"}:
        message = "Your payment could not be confirmed right now. Please check again shortly."
    elif reason == "provider_not_successful":
        message = "Your payment has not yet been confirmed by Paystack."
    else:
        message = "Your payment is being verified. Please check again shortly."
    return render_template(
        "public/payment_result.html", payment=payment,
        payment_confirmed=(payment.status == "paid"), message=message,
    )


@fan_payments_bp.route("/paystack/webhook", methods=["POST"])
def paystack_webhook():
    raw_body = request.get_data(cache=True, as_text=False)
    signature = request.headers.get("x-paystack-signature", "")
    try:
        verified = verify_paystack_webhook(raw_body, signature)
    except PaystackError:
        current_app.logger.exception("Paystack webhook signature verification error")
        return "", 500
    if not verified:
        current_app.logger.warning("Rejected invalid Paystack webhook")
        return "", 401
    event = request.get_json(silent=True)
    if not isinstance(event, dict):
        return "", 400
    if event.get("event") != "charge.success":
        return "", 200
    data = event.get("data")
    if not isinstance(data, dict):
        return "", 400
    reference = data.get("reference")
    if not isinstance(reference, str) or not FAN_REFERENCE_RE.fullmatch(reference):
        # This account may also receive other Kalxa products' events.
        return "", 200
    confirmed, reason = confirm_fan_payment(reference, source="webhook")
    if confirmed or reason == "payment_not_found":
        return "", 200
    if reason in {"provider_error", "internal_error"}:
        return "", 500
    current_app.logger.warning("Fan webhook not confirmed reason=%s", reason)
    return "", 200


# Reconciliation: call confirm_fan_payment(reference, source="reconciliation")
# ONLY from an authenticated, CSRF-protected Studio/admin action after
# checking that the payment belongs to the authenticated creator.
# No public reconciliation endpoint is exposed here.
