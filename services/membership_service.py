"""Membership payment periods, active access checks and magic-link tokens."""
import calendar
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from extensions import db
from membership_models import (
    CreatorMembership, MembershipPayment, MembershipSubscriber, MembershipLoginToken,
)
from services.creator_monetization import calculate_commission_cents

MIN_CENTS = 3000
MAX_CENTS = 10_000_000
MAGIC_LINK_MINUTES = 15
MAGIC_LINK_COOLDOWN_SECONDS = 60
MAGIC_LINK_MAX_PER_HOUR = 5


def now_utc():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def parse_amount(value):
    try:
        amount = Decimal(str(value).strip())
        cents = amount * 100
        if not amount.is_finite() or cents != cents.to_integral_value():
            return None
        cents = int(cents)
        return cents if MIN_CENTS <= cents <= MAX_CENTS else None
    except (ValueError, InvalidOperation, TypeError):
        return None


def add_calendar_month(start):
    month = start.month + 1
    year = start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


def active_membership(membership):
    return bool(membership and membership.status == 'active' and
                as_utc(membership.current_period_end) and
                as_utc(membership.current_period_end) > now_utc())


def member_has_access(subscriber_id, creator_account_id):
    """Always query the database; a signed browser session alone grants nothing."""
    if type(subscriber_id) is not int or type(creator_account_id) is not int:
        return False
    membership = CreatorMembership.query.filter_by(
        subscriber_id=subscriber_id, creator_account_id=creator_account_id
    ).first()
    return active_membership(membership)


def new_pending_payment(creator, email, amount_cents, reference):
    subscriber = MembershipSubscriber.query.filter_by(email=email).first()
    if subscriber is None:
        subscriber = MembershipSubscriber(email=email)
        db.session.add(subscriber)
        db.session.flush()
    membership = CreatorMembership.query.filter_by(
        subscriber_id=subscriber.id, creator_account_id=creator.id
    ).first()
    if membership is None:
        membership = CreatorMembership(
            subscriber_id=subscriber.id, creator_account_id=creator.id,
            monthly_amount_cents=amount_cents,
        )
        db.session.add(membership)
        db.session.flush()
    fee = calculate_commission_cents(creator, amount_cents)
    if type(fee) is not int or not 0 < fee < amount_cents:
        raise ValueError('Invalid platform fee')
    payment = MembershipPayment(
        membership_id=membership.id, creator_account_id=creator.id,
        amount_cents=amount_cents, platform_fee_cents=fee,
        provider_reference=reference,
    )
    db.session.add(payment)
    db.session.commit()
    return payment


def activate_verified_payment(payment, transaction_id):
    """Caller MUST hold payment row lock and verify Paystack transaction."""
    if payment.status == 'paid':
        return False
    if payment.status != 'pending':
        raise ValueError('Payment is not pending')
    membership = db.session.query(CreatorMembership).filter_by(
        id=payment.membership_id
    ).with_for_update().one()
    now = now_utc()
    old_end = as_utc(membership.current_period_end)
    start = max(now, old_end) if old_end else now
    membership.current_period_start = (
        membership.current_period_start if active_membership(membership) else now
    )
    membership.current_period_end = add_calendar_month(start)
    membership.monthly_amount_cents = payment.amount_cents
    membership.status = 'active'
    payment.provider_transaction_id = str(transaction_id)
    payment.status = 'paid'
    payment.paid_at = now
    return True


def create_magic_link_token(subscriber_id, creator_account_id):
    """Returns plaintext token only once. Stores only its SHA-256 digest.

    Caller must send email and commit. A DB-backed per-member rate limit
    avoids duplicate sends across Gunicorn workers.
    """
    now = now_utc()
    recent = MembershipLoginToken.query.filter_by(
        subscriber_id=subscriber_id, creator_account_id=creator_account_id
    ).order_by(MembershipLoginToken.created_at.desc()).first()
    if recent and as_utc(recent.created_at) > now - timedelta(seconds=MAGIC_LINK_COOLDOWN_SECONDS):
        return None
    count = MembershipLoginToken.query.filter(
        MembershipLoginToken.subscriber_id == subscriber_id,
        MembershipLoginToken.creator_account_id == creator_account_id,
        MembershipLoginToken.created_at >= now - timedelta(hours=1),
    ).count()
    if count >= MAGIC_LINK_MAX_PER_HOUR:
        return None
    token = secrets.token_urlsafe(48)
    db.session.add(MembershipLoginToken(
        subscriber_id=subscriber_id,
        creator_account_id=creator_account_id,
        token_hash=hashlib.sha256(token.encode('utf-8')).hexdigest(),
        expires_at=now + timedelta(minutes=MAGIC_LINK_MINUTES),
    ))
    db.session.commit()
    return token


def consume_magic_link_token(raw_token, creator_account_id):
    """Atomically consume token, returning subscriber ID on success.

    Caller commits BEFORE setting authenticated session state.
    """
    if not isinstance(raw_token, str) or not 20 <= len(raw_token) <= 256:
        return None
    digest = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
    token = db.session.query(MembershipLoginToken).filter_by(
        token_hash=digest, creator_account_id=creator_account_id
    ).with_for_update().first()
    if not token or token.consumed_at or as_utc(token.expires_at) <= now_utc():
        db.session.rollback()
        return None
    if not member_has_access(token.subscriber_id, creator_account_id):
        db.session.rollback()
        return None
    token.consumed_at = now_utc()
    # Invalidate other outstanding tokens for the same member and creator.
    MembershipLoginToken.query.filter(
        MembershipLoginToken.subscriber_id == token.subscriber_id,
        MembershipLoginToken.creator_account_id == creator_account_id,
        MembershipLoginToken.id != token.id,
        MembershipLoginToken.consumed_at.is_(None),
    ).update({'consumed_at': now_utc()}, synchronize_session=False)
    subscriber_id = token.subscriber_id
    db.session.commit()
    return subscriber_id
