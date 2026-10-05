import json

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    request,
    session,
    url_for,
)

from extensions import db
from models import CreatorAccount, PlatformSubscriptionPayment, utc_now
from services.plan_service import PLAN_PRICES, VALID_PLANS, normalize_plan
from services.subscription_service import (
    get_creator_subscription,
    record_subscription_payment,
    renew_creator_subscription,
)
from services.yoco_service import YocoError, create_checkout, verify_webhook

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


def current_creator_account():
    creator_id = session.get("creator_account_id")
    if not creator_id:
        return None
    return db.session.get(CreatorAccount, creator_id)


def expected_amount_cents(plan):
    plan = normalize_plan(plan)
    return int(PLAN_PRICES[plan] * 100)


def _absolute_url(endpoint):
    return url_for(endpoint, _external=True, _scheme="https")


def _apply_successful_payment(payment):
    """Idempotently apply a verified successful Yoco payment."""
    if payment.status == "paid":
        return

    creator = db.session.get(CreatorAccount, payment.creator_account_id)
    if not creator:
        raise ValueError("Creator account does not exist.")

    payment.status = "paid"
    payment.paid_at = utc_now()

    # First creator payment: payment is automatic, platform approval remains manual.
    if creator.account_status in {"pending_payment", "pending_approval"}:
        creator.plan = payment.plan
        creator.payment_status = "paid"
        if not creator.registration_paid_at:
            creator.registration_paid_at = utc_now()
        if creator.account_status == "pending_payment":
            creator.account_status = "pending_approval"

        subscription = get_creator_subscription(creator, create=True)
        subscription.plan = payment.plan
        subscription.provider = "yoco"
        payment.subscription_id = subscription.id
        return

    # Approved creators renew immediately after a verified payment.
    if creator.account_status == "active":
        creator.plan = payment.plan
        subscription = renew_creator_subscription(
            creator,
            days=30,
            plan=payment.plan,
            provider="yoco",
        )
        payment.subscription_id = subscription.id


def _apply_failed_payment(payment):
    if payment.status == "paid":
        return
    payment.status = "failed"


@payments_bp.route("/creator/checkout", methods=["POST"])
def creator_checkout():
    creator = current_creator_account()
    if not creator:
        flash("Please sign in to continue.", "warning")
        return redirect(url_for("creator_auth.login"))

    if creator.account_status in {"rejected", "suspended"}:
        abort(403)

    requested_plan = request.form.get("plan", creator.plan or "standard").strip().lower()
    if requested_plan not in VALID_PLANS:
        abort(400)
    plan = normalize_plan(requested_plan)
    amount_cents = expected_amount_cents(plan)

    metadata = {
        "creator_account_id": creator.id,
        "plan": plan,
        "purpose": "creator_subscription",
    }

    try:
        checkout = create_checkout(
            amount_cents=amount_cents,
            success_url=_absolute_url("payments.creator_payment_success"),
            cancel_url=_absolute_url("payments.creator_payment_cancelled"),
            failure_url=_absolute_url("payments.creator_payment_failed"),
            metadata=metadata,
            description=f"Kalxa Creator {plan.title()} plan",
        )
    except YocoError:
        current_app.logger.exception("Yoco checkout creation failed.")
        flash("We could not start the payment. Please try again.", "error")
        return redirect(url_for("creator_auth.pending"))

    checkout_id = checkout.get("id")
    redirect_url = checkout.get("redirectUrl")
    if not checkout_id or not redirect_url:
        current_app.logger.error("Yoco checkout response missing id/redirectUrl: %r", checkout)
        flash("Payment checkout could not be created.", "error")
        return redirect(url_for("creator_auth.pending"))

    # Unique provider_reference makes webhook processing idempotent.
    existing = PlatformSubscriptionPayment.query.filter_by(
        provider="yoco",
        provider_reference=checkout_id,
    ).first()
    if not existing:
        record_subscription_payment(
            creator,
            status="pending",
            provider="yoco",
            provider_reference=checkout_id,
            subscription=get_creator_subscription(creator, create=True),
            plan=plan,
            amount_cents=amount_cents,
        )
        db.session.commit()

    return redirect(redirect_url, code=303)


@payments_bp.route("/creator/success")
def creator_payment_success():
    flash(
        "Payment submitted. We are confirming it securely with Yoco. "
        "Your account will update automatically once confirmation arrives.",
        "success",
    )
    return redirect(url_for("creator_auth.pending"))


@payments_bp.route("/creator/cancelled")
def creator_payment_cancelled():
    flash("Payment was cancelled. No subscription change was made.", "warning")
    return redirect(url_for("creator_auth.pending"))


@payments_bp.route("/creator/failed")
def creator_payment_failed():
    flash("The payment was not completed. You can try again.", "error")
    return redirect(url_for("creator_auth.pending"))


@payments_bp.route("/yoco/webhook", methods=["POST"])
def yoco_webhook():
    raw_body = request.get_data(cache=False)

    try:
        signature_valid = verify_webhook(raw_body, request.headers)
    except YocoError:
        current_app.logger.exception("Yoco webhook verification configuration error.")
        return "Webhook configuration error", 500

    if not signature_valid:
        current_app.logger.warning("Rejected invalid Yoco webhook signature.")
        return "Invalid signature", 400

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "Invalid JSON", 400

    event_type = event.get("type")
    data = event.get("data") or {}
    checkout_id = data.get("checkoutId") or data.get("checkout_id")

    if not checkout_id:
        # Valid but irrelevant event. Acknowledge so Yoco does not retry forever.
        return "OK", 200

    payment = PlatformSubscriptionPayment.query.filter_by(
        provider="yoco",
        provider_reference=str(checkout_id),
    ).first()

    if not payment:
        current_app.logger.warning("Yoco webhook for unknown checkout %s", checkout_id)
        return "OK", 200

    # Never trust webhook metadata alone. Match the transaction to our DB record.
    try:
        event_amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return "Invalid amount", 400

    event_currency = str(data.get("currency", "")).upper()
    metadata = data.get("metadata") or {}

    if event_amount != payment.amount_cents or event_currency != payment.currency:
        current_app.logger.error("Yoco amount/currency mismatch for checkout %s", checkout_id)
        return "Payment mismatch", 400

    if str(metadata.get("creator_account_id", "")) != str(payment.creator_account_id):
        current_app.logger.error("Yoco creator mismatch for checkout %s", checkout_id)
        return "Payment mismatch", 400

    if normalize_plan(metadata.get("plan")) != normalize_plan(payment.plan):
        current_app.logger.error("Yoco plan mismatch for checkout %s", checkout_id)
        return "Payment mismatch", 400

    if event_type == "payment.succeeded":
        _apply_successful_payment(payment)
        db.session.commit()
        return "OK", 200

    if event_type == "payment.failed":
        _apply_failed_payment(payment)
        db.session.commit()
        return "OK", 200

    return "OK", 200
