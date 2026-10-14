"""Kalxa Creator: once-off Yoco activation and upgrade payments.

Requires config.py pricing constants, services.yoco_service.create_checkout,
and services.yoco_webhook_service.verify_yoco_webhook.

This module does not process Paystack fan payments.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import (
    Blueprint, current_app, flash, jsonify, redirect, request, session, url_for,
)

from config import PLAN_PRICES_CENTS, STANDARD_TO_PREMIUM_UPGRADE_CENTS
from extensions import db
from models import CreatorAccount, PlatformSubscriptionPayment, utc_now
from services.yoco_service import YocoError, create_checkout
from services.yoco_webhook_service import YocoWebhookError, verify_yoco_webhook


payments_bp = Blueprint("payments", __name__, url_prefix="/payments")
PAID_PLANS = ("standard", "premium")
SUCCESS_STATUSES = ("succeeded", "successful", "approved", "completed")
RESTRICTED_STATUSES = ("suspended", "rejected")


# ---------------------------------------------------------------------------
# Authentication and checkout decisions
# ---------------------------------------------------------------------------

def get_logged_in_creator():
    creator_id = session.get("creator_account_id")
    return db.session.get(CreatorAccount, creator_id) if creator_id else None


def get_site_url():
    site_url = str(current_app.config.get("SITE_URL") or "").rstrip("/")
    parsed = urlparse(site_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("SITE_URL must be a configured HTTPS URL.")
    return site_url


def _return_to_account():
    return redirect(url_for("creator_auth.pending"))


def _requested_plan():
    plan = str(request.form.get("plan") or "").strip().lower()
    return plan if plan in PAID_PLANS else None


def _paid_standard_payment(creator_id, *, before=None):
    """Find a recorded successful Standard activation, including old prices."""
    query = db.session.query(PlatformSubscriptionPayment).filter_by(
        creator_account_id=creator_id,
        plan="standard",
        provider="yoco",
        status="paid",
        currency="ZAR",
    ).filter(PlatformSubscriptionPayment.paid_at.isnot(None))
    if before is not None:
        query = query.filter(PlatformSubscriptionPayment.created_at < before)
    return query.order_by(PlatformSubscriptionPayment.id.asc()).first()


def _paid_plan_payment(creator_id, plan):
    return db.session.query(PlatformSubscriptionPayment).filter_by(
        creator_account_id=creator_id,
        plan=plan,
        provider="yoco",
        status="paid",
        currency="ZAR",
    ).filter(PlatformSubscriptionPayment.paid_at.isnot(None)).first()


def _has_paid_premium(creator_id):
    return _paid_plan_payment(creator_id, "premium") is not None


def _amount_due(creator, plan):
    """Determine new checkout amount from server-side state and paid ledger."""
    if plan not in PAID_PLANS:
        return None
    if creator.account_status in RESTRICTED_STATUSES:
        return None

    # Paid Premium is final; never sell a downgrade or duplicate activation.
    if _has_paid_premium(creator.id):
        return None

    standard_payment = _paid_standard_payment(creator.id)
    if standard_payment is not None:
        if plan == "standard":
            return None
        if creator.plan != "standard":
            # Inconsistent current state needs manual reconciliation.
            return None
        return STANDARD_TO_PREMIUM_UPGRADE_CENTS

    # A claimed paid plan without a matching paid ledger is inconsistent.
    # Do not automatically sell a second plan or grant an upgrade discount.
    if creator.plan in PAID_PLANS and creator.payment_status == "paid":
        return None

    return PLAN_PRICES_CENTS[plan]


# ---------------------------------------------------------------------------
# Signed webhook payload parsing
# ---------------------------------------------------------------------------

def _event_type(payload):
    return str(payload.get("type") or payload.get("event_type") or payload.get("eventType") or "").strip().lower()


def _payment_data(payload):
    value = payload.get("payload")
    return value if isinstance(value, dict) else None


def _metadata(data):
    value = data.get("metadata")
    return value if isinstance(value, dict) else {}


def _checkout_id(data):
    metadata = _metadata(data)
    value = metadata.get("checkoutId") or metadata.get("checkout_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _amount(data):
    value = data.get("amount")
    if isinstance(value, dict):
        value = value.get("amount")
    if value is None:
        value = data.get("totalAmount", data.get("total_amount"))
        if isinstance(value, dict):
            value = value.get("amount")
    return value if type(value) is int else None


def _valid_payment_record(payment):
    return (
        payment.plan in PAID_PLANS
        and type(payment.amount_cents) is int
        and payment.amount_cents > 0
        and payment.currency == "ZAR"
        and payment.provider == "yoco"
        and isinstance(payment.provider_reference, str)
        and bool(payment.provider_reference.strip())
    )


def _validate_signed_event(data, payment, event_type):
    """Return error text or None; signed payload must match stored checkout."""
    if not _valid_payment_record(payment):
        return "Invalid payment record"
    if _amount(data) != payment.amount_cents:
        return "Amount mismatch"
    if str(data.get("currency") or "").upper() != payment.currency:
        return "Currency mismatch"

    status = str(data.get("status") or "").strip().lower()
    if event_type == "payment.succeeded" and status not in SUCCESS_STATUSES:
        return "Provider success status missing or invalid"
    if event_type == "payment.failed" and status in SUCCESS_STATUSES:
        return "Conflicting provider status"

    meta = _metadata(data)
    if meta.get("creatorAccountId") is not None and str(meta["creatorAccountId"]) != str(payment.creator_account_id):
        return "Creator mismatch"
    if meta.get("plan") is not None and str(meta["plan"]).lower() != payment.plan:
        return "Plan mismatch"
    if meta.get("paymentType") is not None:
        expected = (
            "standard_to_premium_upgrade"
            if payment.plan == "premium" and payment.amount_cents == STANDARD_TO_PREMIUM_UPGRADE_CENTS
            else "plan_activation"
        )
        if str(meta["paymentType"]) != expected:
            return "Payment type mismatch"
    return None


def _created_before(payment, other_payment):
    """Compare timestamps without assuming SQLite/Postgres timezone handling."""
    first = payment.created_at
    second = other_payment.created_at
    if first is None or second is None:
        return False
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    if second.tzinfo is None:
        second = second.replace(tzinfo=timezone.utc)
    return first < second


def _upgrade_is_eligible(payment, creator):
    if payment.plan != "premium" or payment.amount_cents != STANDARD_TO_PREMIUM_UPGRADE_CENTS:
        return True
    standard = _paid_standard_payment(creator.id)
    return (
        standard is not None
        and _created_before(standard, payment)
        and creator.plan in ("standard", "premium")
    )


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

@payments_bp.route("/creator/checkout", methods=["POST"])
def creator_checkout():
    creator = get_logged_in_creator()
    if creator is None:
        flash("Please sign in to continue.", "warning")
        return redirect(url_for("creator_auth.login"))
    if creator.account_status in RESTRICTED_STATUSES:
        flash("This account cannot purchase a plan.", "error")
        return _return_to_account()

    plan = _requested_plan()
    if plan is None:
        flash("Choose Standard or Premium to continue.", "error")
        return _return_to_account()

    amount_cents = _amount_due(creator, plan)
    if amount_cents is None:
        flash("This plan is already owned or the account requires payment review.", "info")
        return _return_to_account()

    try:
        site_url = get_site_url()
        checkout = create_checkout(
            amount_cents=amount_cents,
            creator=creator,
            plan=plan,
            success_url=f"{site_url}/payments/yoco/success",
            cancel_url=f"{site_url}/payments/yoco/cancel",
            failure_url=f"{site_url}/payments/yoco/failure",
        )
    except (YocoError, RuntimeError):
        current_app.logger.exception("Yoco checkout creation failed for creator %s", creator.id)
        flash("Payments are temporarily unavailable. Please try again.", "error")
        return _return_to_account()

    if not isinstance(checkout, dict):
        flash("Payment checkout could not be validated.", "error")
        return _return_to_account()

    checkout_id = checkout.get("id")
    redirect_url = checkout.get("redirect_url")
    parsed = urlparse(redirect_url) if isinstance(redirect_url, str) else None
    if not isinstance(checkout_id, str) or not checkout_id.strip():
        flash("Yoco did not return a checkout reference.", "error")
        return _return_to_account()
    if not parsed or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        flash("Yoco did not return a secure payment link.", "error")
        return _return_to_account()
    if checkout.get("amount") is not None and checkout["amount"] != amount_cents:
        flash("Yoco returned an unexpected amount.", "error")
        return _return_to_account()
    if checkout.get("currency") is not None and checkout["currency"] != "ZAR":
        flash("Yoco returned an unexpected currency.", "error")
        return _return_to_account()

    try:
        db.session.add(PlatformSubscriptionPayment(
            creator_account_id=creator.id,
            plan=plan,
            amount_cents=amount_cents,
            currency="ZAR",
            provider="yoco",
            provider_reference=checkout_id.strip(),
            status="pending",
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not save Yoco checkout %s", checkout_id)
        flash("Could not save your checkout. Please try again.", "error")
        return _return_to_account()

    return redirect(redirect_url, code=303)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@payments_bp.route("/yoco/webhook", methods=["POST"])
def yoco_webhook():
    raw_body = request.get_data(cache=True, as_text=False)
    try:
        verify_yoco_webhook(
            raw_body=raw_body,
            webhook_id=request.headers.get("webhook-id"),
            webhook_timestamp=request.headers.get("webhook-timestamp"),
            webhook_signature=request.headers.get("webhook-signature"),
        )
    except YocoWebhookError:
        current_app.logger.warning("Rejected Yoco webhook signature")
        return jsonify(ok=False, error="Invalid webhook signature"), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error="Invalid payload"), 400
    event_type = _event_type(payload)
    if event_type not in ("payment.succeeded", "payment.failed"):
        return jsonify(ok=True, ignored=True, event_type=event_type), 200
    data = _payment_data(payload)
    checkout_id = _checkout_id(data) if data else None
    if not checkout_id:
        return jsonify(ok=False, error="Missing checkout ID"), 400

    try:
        payment = (
            db.session.query(PlatformSubscriptionPayment)
            .filter_by(provider="yoco", provider_reference=checkout_id)
            .with_for_update()
            .first()
        )
        if payment is None:
            db.session.rollback()
            return jsonify(ok=False, error="Unknown checkout"), 503
        if payment.status == "paid":
            db.session.rollback()
            return jsonify(ok=True, duplicate=True), 200
        if payment.status == "refunded":
            db.session.rollback()
            return jsonify(ok=True, ignored=True, reason="refunded"), 200

        error = _validate_signed_event(data, payment, event_type)
        if error:
            db.session.rollback()
            return jsonify(ok=False, error=error), 400

        if event_type == "payment.failed":
            if payment.status == "pending":
                payment.status = "failed"
                db.session.commit()
                return jsonify(ok=True, payment_status="failed"), 200
            db.session.rollback()
            return jsonify(ok=True, ignored=True), 200

        if payment.status not in ("pending", "failed"):
            db.session.rollback()
            return jsonify(ok=False, error="Payment requires review"), 409

        creator = (
            db.session.query(CreatorAccount)
            .filter_by(id=payment.creator_account_id)
            .with_for_update()
            .first()
        )
        if creator is None:
            db.session.rollback()
            return jsonify(ok=False, error="Creator not found"), 404
        if creator.account_status in RESTRICTED_STATUSES:
            db.session.rollback()
            current_app.logger.error("Paid checkout for restricted creator %s", creator.id)
            return jsonify(ok=False, error="Account requires review"), 409

        if not _upgrade_is_eligible(payment, creator):
            db.session.rollback()
            return jsonify(ok=False, error="Upgrade requires a prior paid Standard activation"), 409

        # Preserve the creator's highest already-paid plan.
        premium_paid = _has_paid_premium(creator.id)
        if payment.plan == "standard" and (creator.plan == "premium" or premium_paid):
            payment.status = "paid"
            payment.paid_at = utc_now()
            db.session.commit()
            return jsonify(ok=True, processed=True, plan_unchanged=True), 200

        # A paid Premium activation cannot be used to create a downgrade.
        creator.plan = payment.plan
        creator.payment_status = "paid"
        creator.registration_paid_at = creator.registration_paid_at or utc_now()
        if creator.account_status == "pending_payment":
            creator.account_status = "pending_approval"
        creator.subscription_status = "inactive"
        creator.subscription_expires_at = None
        payment.status = "paid"
        payment.paid_at = utc_now()
        db.session.commit()
        return jsonify(
            ok=True, processed=True, payment_status="paid",
            account_status=creator.account_status, plan=creator.plan,
        ), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Yoco webhook processing failed for checkout %s", checkout_id)
        return jsonify(ok=False, error="Payment processing failed"), 500


# ---------------------------------------------------------------------------
# Browser redirects (never activate plans)
# ---------------------------------------------------------------------------

@payments_bp.route("/yoco/success", methods=["GET"])
def yoco_success():
    if get_logged_in_creator() is None:
        flash("Sign in to check your activation status.", "info")
        return redirect(url_for("creator_auth.login"))
    flash("Your payment is being verified securely with Yoco.", "info")
    return _return_to_account()


@payments_bp.route("/yoco/cancel", methods=["GET"])
def yoco_cancel():
    flash("Payment cancelled. Your plan has not changed.", "warning")
    return _return_to_account() if get_logged_in_creator() else redirect(url_for("creator_auth.login"))


@payments_bp.route("/yoco/failure", methods=["GET"])
def yoco_failure():
    flash("Payment was not completed. Please try again.", "error")
    return _return_to_account() if get_logged_in_creator() else redirect(url_for("creator_auth.login"))
