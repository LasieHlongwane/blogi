"""Manual Paystack memberships plus creator-scoped passwordless email sign-in.

Important: exclusive Cloudinary media needs authenticated/signed delivery too.
"""
import json
import re
import secrets
import time
import uuid
from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, session, url_for,
)
from extensions import db
from models import CreatorAccount, CreatorProfile, CreatorPayoutAccount
from membership_models import MembershipPayment, MembershipSubscriber, CreatorMembership
from services.creator_monetization import can_use_feature
from services.membership_service import (
    new_pending_payment, parse_amount, activate_verified_payment,
    active_membership, member_has_access, create_magic_link_token,
    consume_magic_link_token,
)
from services.membership_paystack import (
    REFERENCE_RE, initialize_membership_payment, verify_membership_transaction,
)
from services.membership_email import send_membership_login_email
from services.paystack_service import PaystackError, verify_paystack_webhook

membership_bp = Blueprint('membership', __name__, url_prefix='/memberships')
EMAIL_RE = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+\Z')
LOGIN_REQUEST_COOLDOWN = 30  # additional browser-session throttle


def creator_or_404(username):
    if not username or len(username) > 100:
        abort(404)
    return CreatorAccount.query.filter(
        db.func.lower(CreatorAccount.username) == username.strip().lower(),
        CreatorAccount.account_status == 'active',
    ).first_or_404()


def can_offer_memberships(creator):
    # Eligibility does not depend on a potentially stale feature-key mapping.
    return bool(
        creator and (creator.plan or '').lower() in ('standard', 'premium')
        and creator.account_status == 'active'
        and creator.payment_status == 'paid'
        and creator.registration_paid_at is not None
        and creator.monetization_enabled
    )


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
        current_app.logger.info(
            'Membership payment confirmed payment_id=%s source=%s', payment.id, source
        )
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
    return render_template(
        'public/membership_join.html', creator_account=creator,
        creator=profile, payout_ready=bool(payout and payout.provider_subaccount_code),
        selected_amount=request.args.get('amount', '30'),
        member_has_access=bool(
            session.get('membership_email_verified') is True and
            member_has_access(session.get('membership_subscriber_id'), creator.id)
        ),
    )


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
        creator = db.session.get(CreatorAccount, payment.creator_account_id)
        if creator is None:
            abort(404)
        flash('Payment confirmed. Sign in using the email you paid with to unlock content.', 'success')
        return redirect(url_for('membership.sign_in', username=creator.username))
    return ('Your payment could not be confirmed yet. Please contact support if you were charged.', 202)


@membership_bp.route('/<username>/sign-in', methods=['GET', 'POST'])
def sign_in(username):
    creator = creator_or_404(username)
    if not can_offer_memberships(creator):
        abort(404)
    if request.method == 'GET':
        # Inline form avoids assumptions about existing template layout.
        return render_template('public/membership_sign_in.html', creator_account=creator)

    # Session-based throttle is only a first layer; add proxy/Redis IP limits.
    now = time.time()
    last = session.get('membership_login_request_at', 0)
    if isinstance(last, (int, float)) and now - last < LOGIN_REQUEST_COOLDOWN:
        flash('If your membership is active, check your inbox for a sign-in link.', 'info')
        return redirect(url_for('membership.sign_in', username=creator.username))
    session['membership_login_request_at'] = now
    email = str(request.form.get('email') or '').strip().lower()
    if len(email) <= 255 and EMAIL_RE.fullmatch(email):
        subscriber = MembershipSubscriber.query.filter_by(email=email).first()
        if subscriber and member_has_access(subscriber.id, creator.id):
            token = create_magic_link_token(subscriber.id, creator.id)
            if token:
                link = url_for(
                    'membership.verify_login', username=creator.username,
                    token=token, _external=True,
                )
                profile = CreatorProfile.query.filter_by(creator_account_id=creator.id).first()
                name = (profile.display_name if profile else creator.username)
                try:
                    send_membership_login_email(email, name, link)
                except Exception:
                    current_app.logger.exception('Unable to deliver membership login email')
    flash('If your membership is active, check your inbox for a sign-in link.', 'info')
    return redirect(url_for('membership.sign_in', username=creator.username))


@membership_bp.route('/<username>/verify/<token>', methods=['GET', 'POST'])
def verify_login(username, token):
    creator = creator_or_404(username)
    if request.method == 'GET':
        # Email security scanners often prefetch GET links; don't consume on GET.
        nonce = secrets.token_urlsafe(24)
        session['membership_confirm_nonce'] = nonce
        return render_template(
            'public/membership_verify.html', creator_account=creator,
            token=token, confirm_nonce=nonce,
        )
    nonce = session.pop('membership_confirm_nonce', None)
    submitted = request.form.get('confirm_nonce')
    if not nonce or not submitted or not secrets.compare_digest(nonce, submitted):
        abort(400)
    subscriber_id = consume_magic_link_token(token, creator.id)
    if subscriber_id is None:
        flash('This sign-in link is invalid or expired. Request another link.', 'warning')
        return redirect(url_for('membership.sign_in', username=creator.username))
    # Rotate all existing session state, preventing fixation/stale identities.
    session.clear()
    session['membership_subscriber_id'] = subscriber_id
    session['membership_email_verified'] = True
    session.permanent = True
    flash('You are signed in. Your exclusive membership is active.', 'success')
    return redirect(url_for('public.creator_home', username=creator.username))


@membership_bp.post('/<username>/sign-out')
def sign_out(username):
    creator = creator_or_404(username)
    session.pop('membership_subscriber_id', None)
    session.pop('membership_email_verified', None)
    flash('You have signed out of your membership.', 'info')
    return redirect(url_for('public.creator_home', username=creator.username))


@membership_bp.post('/paystack/webhook')
def webhook():
    """Configure this exact endpoint in Paystack or dispatch from shared webhook."""
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
