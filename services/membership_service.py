"""Manual calendar-month access periods and strict verified-payment handling."""
import calendar
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from sqlalchemy.exc import IntegrityError
from extensions import db
from membership_models import CreatorMembership, MembershipPayment, MembershipSubscriber
from services.creator_monetization import calculate_commission_cents

MIN_CENTS = 3000
MAX_CENTS = 10_000_000


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


def new_pending_payment(creator, email, amount_cents, reference):
    """Create membership and payment. Caller handles rollback on error.

    DB uniqueness protects one email identity and one creator membership.
    """
    subscriber = MembershipSubscriber.query.filter_by(email=email).first()
    if subscriber is None:
        subscriber = MembershipSubscriber(email=email)
        db.session.add(subscriber)
        db.session.flush()
    membership = CreatorMembership.query.filter_by(
        subscriber_id=subscriber.id, creator_account_id=creator.id
    ).first()
    if membership is None:
        membership = CreatorMembership(subscriber_id=subscriber.id,
                                       creator_account_id=creator.id,
                                       monthly_amount_cents=amount_cents)
        db.session.add(membership)
        db.session.flush()
    fee = calculate_commission_cents(creator, amount_cents)
    if type(fee) is not int or not 0 < fee < amount_cents:
        raise ValueError('Invalid platform fee')
    payment = MembershipPayment(membership_id=membership.id,
                                creator_account_id=creator.id,
                                amount_cents=amount_cents,
                                platform_fee_cents=fee,
                                provider_reference=reference)
    db.session.add(payment)
    db.session.commit()
    return payment


def activate_verified_payment(payment, transaction_id):
    """Must be called inside a transaction holding a FOR UPDATE payment row lock.

    The caller must validate Paystack verification data first. Do not call
    this function on a browser callback or unsigned webhook alone.
    """
    if payment.status == 'paid':
        return False
    if payment.status != 'pending':
        raise ValueError('Payment is not pending')
    membership = db.session.query(CreatorMembership).filter_by(id=payment.membership_id).with_for_update().one()
    now = now_utc()
    old_end = as_utc(membership.current_period_end)
    start = max(now, old_end) if old_end else now
    membership.current_period_start = now if not active_membership(membership) else membership.current_period_start
    membership.current_period_end = add_calendar_month(start)
    membership.monthly_amount_cents = payment.amount_cents
    membership.status = 'active'
    payment.provider_transaction_id = str(transaction_id)
    payment.status = 'paid'
    payment.paid_at = now
    return True
