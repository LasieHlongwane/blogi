from datetime import timedelta, timezone

from extensions import db
from models import PlatformSubscription, PlatformSubscriptionPayment, utc_now
from services.plan_service import PLAN_PRICES, normalize_plan

GRACE_PERIOD_DAYS = 7
DEFAULT_PERIOD_DAYS = 30


def normalize_datetime_utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_creator_subscription(creator, create=False):
    subscription = PlatformSubscription.query.filter_by(
        creator_account_id=creator.id
    ).first()

    if subscription or not create:
        return subscription

    subscription = PlatformSubscription(
        creator_account_id=creator.id,
        plan=normalize_plan(creator.plan),
        status=creator.subscription_status or "inactive",
        started_at=creator.subscription_started_at,
        current_period_start=creator.subscription_started_at,
        current_period_end=creator.subscription_expires_at,
    )
    db.session.add(subscription)
    db.session.flush()
    return subscription


def sync_legacy_subscription_fields(creator, subscription):
    creator.plan = subscription.plan
    creator.subscription_status = subscription.status
    creator.subscription_started_at = subscription.started_at
    creator.subscription_expires_at = subscription.current_period_end


def creator_subscription_is_current(creator):
    subscription = get_creator_subscription(creator, create=False)
    now = utc_now()

    if subscription:
        if subscription.status == "active":
            end = normalize_datetime_utc(subscription.current_period_end)
            return end is None or end > now

        if subscription.status == "past_due":
            grace = normalize_datetime_utc(subscription.grace_period_ends_at)
            return grace is not None and grace > now

        return False

    if creator.subscription_status != "active":
        return False

    end = normalize_datetime_utc(creator.subscription_expires_at)
    return end is None or end > now


def activate_creator_subscription(
    creator,
    plan=None,
    days=DEFAULT_PERIOD_DAYS,
    provider="manual",
):
    now = utc_now()
    plan = normalize_plan(plan or creator.plan)
    subscription = get_creator_subscription(creator, create=True)

    existing_end = normalize_datetime_utc(subscription.current_period_end)
    start_from = existing_end if existing_end and existing_end > now else now

    if not subscription.started_at:
        subscription.started_at = now

    subscription.plan = plan
    subscription.status = "active"
    subscription.provider = provider
    subscription.current_period_start = start_from
    subscription.current_period_end = start_from + timedelta(days=days)
    subscription.grace_period_ends_at = None
    subscription.cancelled_at = None

    sync_legacy_subscription_fields(creator, subscription)
    return subscription


def renew_creator_subscription(
    creator,
    days=DEFAULT_PERIOD_DAYS,
    plan=None,
    provider="manual",
):
    return activate_creator_subscription(
        creator,
        plan=plan,
        days=days,
        provider=provider,
    )


def mark_subscription_past_due(creator, grace_days=GRACE_PERIOD_DAYS):
    now = utc_now()
    subscription = get_creator_subscription(creator, create=True)
    subscription.status = "past_due"
    subscription.grace_period_ends_at = now + timedelta(days=grace_days)
    sync_legacy_subscription_fields(creator, subscription)
    return subscription


def expire_creator_subscription(creator):
    now = utc_now()
    subscription = get_creator_subscription(creator, create=True)
    subscription.status = "expired"
    subscription.current_period_end = now
    subscription.grace_period_ends_at = None
    sync_legacy_subscription_fields(creator, subscription)
    return subscription


def cancel_creator_subscription(creator):
    subscription = get_creator_subscription(creator, create=True)
    subscription.status = "cancelled"
    subscription.cancelled_at = utc_now()
    subscription.grace_period_ends_at = None
    sync_legacy_subscription_fields(creator, subscription)
    return subscription


def record_subscription_payment(
    creator,
    status="paid",
    provider="manual",
    provider_reference=None,
    subscription=None,
    plan=None,
    amount_cents=None,
):
    plan = normalize_plan(plan or creator.plan)

    if amount_cents is None:
        amount_cents = int(PLAN_PRICES[plan] * 100)

    if subscription is None:
        subscription = get_creator_subscription(creator, create=False)

    payment = PlatformSubscriptionPayment(
        creator_account_id=creator.id,
        subscription_id=subscription.id if subscription else None,
        plan=plan,
        amount_cents=int(amount_cents),
        currency="ZAR",
        provider=provider,
        provider_reference=provider_reference,
        status=status,
        paid_at=utc_now() if status == "paid" else None,
    )
    db.session.add(payment)
    return payment
