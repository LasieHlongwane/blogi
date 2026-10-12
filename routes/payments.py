"""Creator -> Kalxa one-time Yoco plan activation payments.

This module does NOT process fan -> creator Paystack payments.
Replace routes/payments.py with this file, after reviewing the deployment notes.
"""
from decimal import Decimal
from flask import (
    Blueprint, current_app, flash, jsonify, redirect,
    request, session, url_for,
)
from extensions import db
from models import CreatorAccount, PlatformSubscriptionPayment, utc_now
from services.yoco_service import create_checkout, YocoError
from services.yoco_webhook_service import verify_yoco_webhook, YocoWebhookError

payments_bp = Blueprint('payments', __name__, url_prefix='/payments')

PLAN_PRICES_CENTS = {'standard': 10000, 'premium': 15000}
# Upgrade pricing choice: charge the R50 difference, not R150 again.
UPGRADE_STANDARD_TO_PREMIUM_CENTS = 5000


def get_logged_in_creator():
    creator_id = session.get('creator_account_id')
    return db.session.get(CreatorAccount, creator_id) if creator_id else None


def get_site_url():
    site_url = str(current_app.config.get('SITE_URL') or '').rstrip('/')
    if not site_url or not site_url.startswith('https://'):
        raise RuntimeError('SITE_URL must be a configured HTTPS URL.')
    return site_url


def _return_to_account():
    # Keep the existing route as a fallback while templates are updated.
    return redirect(url_for('creator_auth.pending'))


def _is_activated(creator):
    return bool(
        creator.account_status == 'active'
        and creator.plan in PLAN_PRICES_CENTS
        and creator.payment_status == 'paid'
        and creator.registration_paid_at is not None
    )


def _requested_plan():
    # Browser can choose the plan, but NEVER its price.
    plan = str(request.form.get('plan') or '').strip().lower()
    return plan if plan in PLAN_PRICES_CENTS else None


def _amount_due(creator, requested_plan):
    if requested_plan not in PLAN_PRICES_CENTS:
        return None
    if _is_activated(creator):
        if creator.plan == requested_plan:
            return None  # Already owns this plan.
        if creator.plan == 'premium':
            return None  # No downgrade via checkout.
        if creator.plan == 'standard' and requested_plan == 'premium':
            return UPGRADE_STANDARD_TO_PREMIUM_CENTS
        return None
    # Legacy creators marked standard/premium but never activated should
    # not be treated as paid. Their new activation is charged in full.
    return PLAN_PRICES_CENTS[requested_plan]


def _event_type(payload):
    return str(payload.get('type') or payload.get('event_type') or payload.get('eventType') or '').strip().lower()


def _payment_data(payload):
    data = payload.get('payload')
    return data if isinstance(data, dict) else None


def _metadata(data):
    value = data.get('metadata')
    return value if isinstance(value, dict) else {}


def _checkout_id(data):
    value = _metadata(data).get('checkoutId') or _metadata(data).get('checkout_id')
    return str(value).strip() if value is not None and str(value).strip() else None


def _amount(data):
    value = data.get('amount')
    if isinstance(value, dict):
        value = value.get('amount')
    if value is None:
        value = data.get('totalAmount', data.get('total_amount'))
        if isinstance(value, dict):
            value = value.get('amount')
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


@payments_bp.route('/creator/checkout', methods=['POST'])
def creator_checkout():
    creator = get_logged_in_creator()
    if creator is None:
        flash('Please sign in to continue.', 'warning')
        return redirect(url_for('creator_auth.login'))
    if creator.account_status in ('suspended', 'rejected'):
        flash('This account cannot purchase a plan.', 'error')
        return _return_to_account()

    plan = _requested_plan()
    if plan is None:
        flash('Choose Standard or Premium to continue.', 'error')
        return _return_to_account()
    amount_cents = _amount_due(creator, plan)
    if amount_cents is None:
        flash('This plan is already active or cannot be purchased.', 'info')
        return _return_to_account()

    try:
        site_url = get_site_url()
        checkout = create_checkout(
            amount_cents=amount_cents,
            creator=creator,
            plan=plan,
            success_url=f'{site_url}/payments/yoco/success',
            cancel_url=f'{site_url}/payments/yoco/cancel',
            failure_url=f'{site_url}/payments/yoco/failure',
        )
    except (YocoError, RuntimeError):
        current_app.logger.exception('Could not create Yoco checkout for creator %s', creator.id)
        flash('Payments are temporarily unavailable. Please try again.', 'error')
        return _return_to_account()

    if not isinstance(checkout, dict):
        current_app.logger.error('Invalid Yoco checkout response for creator %s', creator.id)
        flash('Payment checkout could not be validated.', 'error')
        return _return_to_account()

    checkout_id = checkout.get('id')
    redirect_url = checkout.get('redirect_url')
    if not isinstance(checkout_id, str) or not checkout_id.strip():
        flash('Yoco did not return a checkout reference.', 'error')
        return _return_to_account()
    if not isinstance(redirect_url, str) or not redirect_url.startswith('https://'):
        flash('Yoco did not return a secure payment link.', 'error')
        return _return_to_account()
    provider_amount = checkout.get('amount')
    if provider_amount is not None and (type(provider_amount) is not int or provider_amount != amount_cents):
        flash('Yoco returned an unexpected amount.', 'error')
        return _return_to_account()
    if checkout.get('currency') and checkout['currency'] != 'ZAR':
        flash('Yoco returned an unexpected currency.', 'error')
        return _return_to_account()

    try:
        db.session.add(PlatformSubscriptionPayment(
            creator_account_id=creator.id,
            plan=plan,
            amount_cents=amount_cents,
            currency='ZAR',
            provider='yoco',
            provider_reference=checkout_id.strip(),
            status='pending',
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Could not persist Yoco checkout %s', checkout_id)
        flash('Could not save your checkout. Please try again.', 'error')
        return _return_to_account()
    return redirect(redirect_url, code=303)


@payments_bp.route('/yoco/webhook', methods=['POST'])
def yoco_webhook():
    raw_body = request.get_data(cache=True, as_text=False)
    try:
        verify_yoco_webhook(
            raw_body=raw_body,
            webhook_id=request.headers.get('webhook-id'),
            webhook_timestamp=request.headers.get('webhook-timestamp'),
            webhook_signature=request.headers.get('webhook-signature'),
        )
    except YocoWebhookError:
        current_app.logger.warning('Rejected Yoco webhook signature')
        return jsonify(ok=False, error='Invalid webhook signature'), 401

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error='Invalid payload'), 400
    event_type = _event_type(payload)
    if event_type not in ('payment.succeeded', 'payment.failed'):
        return jsonify(ok=True, ignored=True, event_type=event_type), 200
    data = _payment_data(payload)
    checkout_id = _checkout_id(data) if data else None
    if not checkout_id:
        return jsonify(ok=False, error='Missing checkout ID'), 400

    try:
        payment = (db.session.query(PlatformSubscriptionPayment)
                   .filter_by(provider='yoco', provider_reference=checkout_id)
                   .with_for_update().first())
        if payment is None:
            db.session.rollback()
            # A webhook may arrive before checkout persistence. Retry later.
            return jsonify(ok=False, error='Unknown checkout'), 503
        if payment.status == 'paid':
            db.session.rollback()
            return jsonify(ok=True, duplicate=True), 200
        if payment.status == 'refunded':
            db.session.rollback()
            return jsonify(ok=True, ignored=True, reason='refunded'), 200
        if event_type == 'payment.failed':
            # Do not allow a late failure to overwrite paid/refunded.
            payment.status = 'failed'
            db.session.commit()
            return jsonify(ok=True, payment_status='failed'), 200

        # Strict amount/currency/plan/creator checks; local payment is the
        # source of truth, including any R50 upgrade discount.
        if _amount(data) != payment.amount_cents or str(data.get('currency', '')).upper() != 'ZAR':
            db.session.rollback()
            return jsonify(ok=False, error='Amount or currency mismatch'), 400
        status = str(data.get('status') or '').strip().lower()
        if status and status not in ('succeeded', 'successful', 'approved', 'completed'):
            db.session.rollback()
            return jsonify(ok=False, error='Provider status mismatch'), 400
        meta = _metadata(data)
        if meta.get('creatorAccountId') is not None and str(meta['creatorAccountId']) != str(payment.creator_account_id):
            db.session.rollback()
            return jsonify(ok=False, error='Creator mismatch'), 400
        if meta.get('plan') is not None and str(meta['plan']).lower() != payment.plan:
            db.session.rollback()
            return jsonify(ok=False, error='Plan mismatch'), 400
        if payment.plan not in PLAN_PRICES_CENTS:
            db.session.rollback()
            return jsonify(ok=False, error='Unknown plan'), 400

        # Lock creator as well to serialize two distinct paid checkouts.
        creator = (db.session.query(CreatorAccount)
                   .filter_by(id=payment.creator_account_id)
                   .with_for_update().first())
        if creator is None:
            db.session.rollback()
            return jsonify(ok=False, error='Creator not found'), 404
        if creator.account_status in ('suspended', 'rejected'):
            # Keep the money in a pending reconciliation state. Do not
            # reactivate suspended/rejected creators via webhook.
            db.session.rollback()
            current_app.logger.error('Paid checkout for restricted creator %s', creator.id)
            return jsonify(ok=False, error='Account requires review'), 409

        # Never downgrade Premium due to out-of-order older webhooks.
        if creator.plan != 'premium' or payment.plan == 'premium':
            creator.plan = payment.plan
        creator.payment_status = 'paid'
        creator.registration_paid_at = creator.registration_paid_at or utc_now()
        # Free signup is active immediately. If a legacy creator still
        # awaits admin approval, do not silently bypass that approval.
        if creator.account_status == 'pending_payment':
            creator.account_status = 'pending_approval'
        # Active remains active, including paid upgrades.
        creator.subscription_status = 'inactive'  # No monthly renewal.
        creator.subscription_expires_at = None
        payment.status = 'paid'
        payment.paid_at = utc_now()
        db.session.commit()
        return jsonify(ok=True, processed=True, payment_status='paid',
                       account_status=creator.account_status, plan=creator.plan), 200
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Yoco webhook processing failed for %s', checkout_id)
        return jsonify(ok=False, error='Payment processing failed'), 500


@payments_bp.route('/yoco/success', methods=['GET'])
def yoco_success():
    if get_logged_in_creator() is None:
        flash('Sign in to check your activation status.', 'info')
        return redirect(url_for('creator_auth.login'))
    flash('Your payment is being verified securely with Yoco.', 'info')
    return _return_to_account()


@payments_bp.route('/yoco/cancel', methods=['GET'])
def yoco_cancel():
    flash('Payment cancelled. Your plan has not changed.', 'warning')
    return _return_to_account() if get_logged_in_creator() else redirect(url_for('creator_auth.login'))


@payments_bp.route('/yoco/failure', methods=['GET'])
def yoco_failure():
    flash('Payment was not completed. Please try again.', 'error')
    return _return_to_account() if get_logged_in_creator() else redirect(url_for('creator_auth.login'))
