"""Creator memberships: manual Paystack checkout and verified activation.

Access to exclusive media and magic-link sign-in are NOT implemented here.
Do not expose exclusive media until those controls are implemented.
"""
import json
import re
import uuid
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from extensions import db
from models import CreatorAccount, CreatorProfile, CreatorPayoutAccount
from membership_models import MembershipPayment
from services.creator_monetization import can_use_feature
from services.membership_service import new_pending_payment, parse_amount, activate_verified_payment
from services.membership_paystack import (
    REFERENCE_RE, initialize_membership_payment, verify_membership_transaction,
)
from services.paystack_service import PaystackError, verify_paystack_webhook

membership_bp = Blueprint('membership', __name__, url_prefix='/memberships')
EMAIL_RE = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+\Z')


def creator_or_404(username):
    return CreatorAccount.query.filter(
        db.func.lower(CreatorAccount.username) == username.strip().lower(),
        CreatorAccount.account_status == 'active',
    ).first_or_404()


def can_offer_memberships(creator):
    return bool(creator.plan in ('standard', 'premium') and
                creator.monetization_enabled and
                can_use_feature(creator, 'exclusive_content'))


def payout_for(creator):
    return CreatorPayoutAccount.query.filter_by(
        creator_account_id=creator.id, provider='paystack', status='active'
    ).first()


def metadata_for(payment):
    return {
        'product_type': 'creator_membership',
        'membership_payment_id': payment.id,
        'membership_id': payment.membership_id,
        'creator_account_id': payment.creator_account_id,
        'platform_fee_cents': payment.platform_fee_cents,
        'creator_receivable_cents': payment.amount_cents - payment.platform_fee_cents,
    }


def _metadata(data):
    value = data.get('metadata') or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def _same_id(actual, expected):
    return actual is not None and not isinstance(actual, bool) and str(actual) == str(expected)


def confirm_membership_payment(reference, *, source):
    if not isinstance(reference, str) or not REFERENCE_RE.fullmatch(reference):
        return False, 'invalid_reference'
    try:
        payment = db.session.query(MembershipPayment).filter_by(
            provider_reference=reference, provider='paystack'
        ).with_for_update().first()
        if payment is None:
            db.session.rollback()
            return False, 'not_found'
        if payment.status == 'paid':
            db.session.rollback()
            return True, 'already_paid'
        if payment.status != 'pending':
            db.session.rollback()
            return False, 'not_pending'
        verified = verify_membership_transaction(reference)
        if not isinstance(verified, dict) or verified.get('status') != 'success':
            db.session.rollback()
            return False, 'not_successful'
        if (verified.get('reference') != payment.provider_reference or
                verified.get('currency') != 'ZAR' or
                type(verified.get('amount')) is not int or
                verified['amount'] != payment.amount_cents):
            db.session.rollback()
            return False, 'transaction_mismatch'
        metadata = _metadata(verified)
        for key, expected in metadata_for(payment).items():
            if not _same_id(metadata.get(key), expected):
                db.session.rollback()
                return False, 'metadata_mismatch'
        transaction_id = verified.get('id')
        if transaction_id is None or isinstance(transaction_id, bool):
            db.session.rollback()
            return False, 'missing_transaction_id'
        duplicate = MembershipPayment.query.filter(
            MembershipPayment.provider_transaction_id == str(transaction_id),
            MembershipPayment.id != payment.id,
        ).first()
        if duplicate:
            db.session.rollback()
            return False, 'duplicate_transaction'
        activate_verified_payment(payment, transaction_id)
        db.session.commit()
        current_app.logger.info('Membership payment confirmed payment_id=%s source=%s', payment.id, source)
        return True, 'confirmed'
    except PaystackError:
        db.session.rollback()
        current_app.logger.exception('Membership Paystack verification failed')
        return False, 'provider_error'
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Membership confirmation failed')
        return False, 'internal_error'


@membership_bp.get('/<username>')
def landing(username):
    creator = creator_or_404(username)
    if not can_offer_memberships(creator):
        abort(404)
    payout = payout_for(creator)
    profile = CreatorProfile.query.filter_by(creator_account_id=creator.id).first()
    return render_template('public/membership_join.html', creator_account=creator,
                           creator=profile, payout_ready=bool(payout and payout.provider_subaccount_code))


@membership_bp.post('/<username>/pay')
def pay(username):
    creator = creator_or_404(username)
    if not can_offer_memberships(creator):
        abort(404)
    back = url_for('membership.landing', username=creator.username)
    payout = payout_for(creator)
    if not payout or not payout.provider_subaccount_code:
        flash('Membership payments are not available yet.', 'warning')
        return redirect(back)
    amount_cents = parse_amount(request.form.get('amount'))
    email = str(request.form.get('email') or '').strip().lower()
    if amount_cents is None:
        flash('Enter R30 or more, with up to two decimal places.', 'error')
        return redirect(back)
    if len(email) > 255 or not EMAIL_RE.fullmatch(email):
        flash('Enter a valid email address.', 'error')
        return redirect(back)
    try:
        payment = new_pending_payment(
            creator, email, amount_cents, 'KALXA-MEM-' + uuid.uuid4().hex.upper()
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Unable to create membership payment')
        flash('Could not start your membership payment.', 'error')
        return redirect(back)
    try:
        checkout_url = initialize_membership_payment(
            email=email, amount_cents=payment.amount_cents,
            reference=payment.provider_reference,
            subaccount_code=payout.provider_subaccount_code,
            platform_fee_cents=payment.platform_fee_cents,
            callback_url=url_for('membership.payment_return', _external=True),
            metadata=metadata_for(payment),
        )
    except (PaystackError, ValueError, TypeError):
        db.session.rollback()
        current_app.logger.exception('Membership checkout initialization failed')
        flash('Payment checkout is unavailable. Please try later.', 'error')
        return redirect(back)
    return redirect(checkout_url, code=303)


@membership_bp.get('/payment/return')
def payment_return():
    reference = request.args.get('reference', '')
    if not REFERENCE_RE.fullmatch(reference):
        abort(400)
    payment = MembershipPayment.query.filter_by(provider_reference=reference).first_or_404()
    success, reason = confirm_membership_payment(reference, source='browser_return')
    if success:
        return ('Payment confirmed. Your membership is active. '
                'Email sign-in is being implemented; exclusive access is not yet enabled.', 200)
    return ('Your payment could not be confirmed yet. Please contact support if you were charged.', 202)


@membership_bp.post('/paystack/webhook')
def webhook():
    """Only works if this exact URL is configured in Paystack.

    If Paystack is configured to POST to /support/paystack/webhook instead,
    dispatch membership references there (see README).
    """
    try:
        verified = verify_paystack_webhook(
            request.get_data(cache=True, as_text=False),
            request.headers.get('x-paystack-signature', ''),
        )
    except PaystackError:
        return '', 500
    if not verified:
        return '', 401
    event = request.get_json(silent=True)
    if not isinstance(event, dict) or event.get('event') != 'charge.success':
        return '', 200
    data = event.get('data') or {}
    reference = data.get('reference') if isinstance(data, dict) else None
    if not isinstance(reference, str) or not REFERENCE_RE.fullmatch(reference):
        return '', 200
    success, reason = confirm_membership_payment(reference, source='webhook')
    if reason in ('provider_error', 'internal_error'):
        return '', 500
    return '', 200
