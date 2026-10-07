# ============================================================
# CREATOR PLATFORM
# SUBSCRIPTION SERVICE
# ============================================================

from datetime import (
    timedelta,
    timezone,
)

from extensions import db

from models import (
    PlatformSubscription,
    PlatformSubscriptionPayment,
    utc_now,
)

from services.plan_service import (
    PLAN_PRICES,
    normalize_plan,
)


# ============================================================
# CONFIGURATION
# ============================================================

GRACE_PERIOD_DAYS = 7
DEFAULT_PERIOD_DAYS = 30


# ============================================================
# VALID SUBSCRIPTION STATES
# ============================================================

SUBSCRIPTION_INACTIVE = "inactive"
SUBSCRIPTION_ACTIVE = "active"
SUBSCRIPTION_PAST_DUE = "past_due"
SUBSCRIPTION_EXPIRED = "expired"
SUBSCRIPTION_CANCELLED = "cancelled"

VALID_SUBSCRIPTION_STATUSES = {
    SUBSCRIPTION_INACTIVE,
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_PAST_DUE,
    SUBSCRIPTION_EXPIRED,
    SUBSCRIPTION_CANCELLED,
}


# ============================================================
# DATETIME HELPERS
# ============================================================

def normalize_datetime_utc(
    value,
):
    """
    Convert a datetime to timezone-aware UTC.

    PostgreSQL may return timezone-aware values while older
    SQLite/local data may contain naive values.

    This helper allows both to be compared safely.
    """

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
# GET CREATOR SUBSCRIPTION
# ============================================================

def get_creator_subscription(
    creator,
    create=False,
):
    """
    Return the creator's PlatformSubscription.

    If create=True and the creator does not yet have a modern
    subscription row, create one from the legacy subscription
    fields stored on CreatorAccount.

    This allows the application to transition gradually from
    legacy subscription fields to PlatformSubscription.
    """

    subscription = (
        PlatformSubscription.query
        .filter_by(
            creator_account_id=creator.id
        )
        .first()
    )

    if subscription or not create:

        return subscription

    # --------------------------------------------------------
    # CREATE FROM LEGACY CREATOR STATE
    # --------------------------------------------------------

    subscription = PlatformSubscription(
        creator_account_id=creator.id,
        plan=normalize_plan(
            creator.plan
        ),
        status=(
            creator.subscription_status
            or SUBSCRIPTION_INACTIVE
        ),
        started_at=(
            creator.subscription_started_at
        ),
        current_period_start=(
            creator.subscription_started_at
        ),
        current_period_end=(
            creator.subscription_expires_at
        ),
    )

    db.session.add(
        subscription
    )

    db.session.flush()

    return subscription


# ============================================================
# LEGACY FIELD SYNCHRONISATION
# ============================================================

def sync_legacy_subscription_fields(
    creator,
    subscription,
):
    """
    Keep CreatorAccount legacy subscription fields in sync
    while the application is transitioning to the dedicated
    PlatformSubscription model.

    These fields can eventually be removed after the entire
    application uses PlatformSubscription directly.
    """

    creator.plan = (
        subscription.plan
    )

    creator.subscription_status = (
        subscription.status
    )

    creator.subscription_started_at = (
        subscription.started_at
    )

    creator.subscription_expires_at = (
        subscription.current_period_end
    )


# ============================================================
# GRACE PERIOD HELPERS
# ============================================================

def get_grace_period_end(
    subscription,
    grace_days=GRACE_PERIOD_DAYS,
):
    """
    Determine when the grace period should end.

    IMPORTANT:

    Grace starts when the paid subscription period ends,
    NOT when the application happens to notice the expiry.

    Example:

        current_period_end:
            31 October

        grace:
            7 days

        grace_period_ends_at:
            7 November

    Even if the creator only returns on 4 November, the grace
    period still ends on 7 November.
    """

    period_end = normalize_datetime_utc(
        subscription.current_period_end
    )

    if period_end is None:

        return None

    return (
        period_end
        + timedelta(
            days=grace_days
        )
    )


def creator_grace_days_remaining(
    creator,
):
    """
    Return the number of whole/partial days remaining in the
    creator's grace period.

    Returns:

        None
            creator is not currently past_due

        0
            grace period has ended

        1..N
            days remaining
    """

    subscription = get_creator_subscription(
        creator,
        create=False,
    )

    if not subscription:

        return None

    if (
        subscription.status
        != SUBSCRIPTION_PAST_DUE
    ):

        return None

    grace_end = normalize_datetime_utc(
        subscription.grace_period_ends_at
    )

    if grace_end is None:

        return 0

    now = utc_now()

    remaining = (
        grace_end - now
    )

    if remaining.total_seconds() <= 0:

        return 0

    # --------------------------------------------------------
    # ROUND UP PARTIAL DAYS
    # --------------------------------------------------------
    #
    # Example:
    #
    # 6 days + 3 hours remaining
    #
    # should display:
    #
    #     7 days remaining
    # --------------------------------------------------------

    total_seconds = (
        remaining.total_seconds()
    )

    seconds_per_day = (
        24 * 60 * 60
    )

    days = int(
        (
            total_seconds
            + seconds_per_day
            - 1
        )
        // seconds_per_day
    )

    return max(
        days,
        0,
    )


# ============================================================
# SUBSCRIPTION LIFECYCLE ENGINE
# ============================================================

def enforce_subscription_lifecycle(
    creator,
    grace_days=GRACE_PERIOD_DAYS,
):
    """
    Evaluate and update the creator's subscription lifecycle.

    Lifecycle:

        active
          ↓
        paid period expires
          ↓
        past_due
          ↓
        7-day grace period
          ↓
        expired


    IMPORTANT:

    This function does NOT commit the database transaction.

    The caller decides when to commit.

    This is important because this service is used from:

        login
        Studio access
        scheduled jobs
        payment processing

    without unexpectedly committing unrelated database work.


    Returns:

        PlatformSubscription | None
    """

    subscription = get_creator_subscription(
        creator,
        create=False,
    )

    # --------------------------------------------------------
    # NO MODERN SUBSCRIPTION
    # --------------------------------------------------------

    if subscription is None:

        return None

    now = utc_now()

    status = (
        str(
            subscription.status
            or SUBSCRIPTION_INACTIVE
        )
        .strip()
        .lower()
    )

    # --------------------------------------------------------
    # CANCELLED / EXPIRED / INACTIVE
    # --------------------------------------------------------
    #
    # These states do not automatically become active.
    #
    # Only payment/approval may activate them.
    # --------------------------------------------------------

    if status in {
        SUBSCRIPTION_CANCELLED,
        SUBSCRIPTION_EXPIRED,
        SUBSCRIPTION_INACTIVE,
    }:

        sync_legacy_subscription_fields(
            creator,
            subscription,
        )

        return subscription

    # ========================================================
    # ACTIVE
    # ========================================================

    if status == SUBSCRIPTION_ACTIVE:

        period_end = normalize_datetime_utc(
            subscription.current_period_end
        )

        # ----------------------------------------------------
        # LEGACY / UNLIMITED ACTIVE SUBSCRIPTION
        # ----------------------------------------------------
        #
        # If no end date exists we cannot automatically
        # expire it.
        # ----------------------------------------------------

        if period_end is None:

            sync_legacy_subscription_fields(
                creator,
                subscription,
            )

            return subscription

        # ----------------------------------------------------
        # STILL INSIDE PAID PERIOD
        # ----------------------------------------------------

        if period_end > now:

            sync_legacy_subscription_fields(
                creator,
                subscription,
            )

            return subscription

        # ----------------------------------------------------
        # PAID PERIOD HAS ENDED
        # ----------------------------------------------------

        grace_end = (
            period_end
            + timedelta(
                days=grace_days
            )
        )

        # ----------------------------------------------------
        # GRACE ALREADY EXPIRED
        # ----------------------------------------------------
        #
        # Example:
        #
        # subscription ended 10 days ago
        # creator returns today
        #
        # We should NOT give them a brand-new 7-day grace
        # period.
        # ----------------------------------------------------

        if grace_end <= now:

            subscription.status = (
                SUBSCRIPTION_EXPIRED
            )

            subscription.grace_period_ends_at = (
                None
            )

            sync_legacy_subscription_fields(
                creator,
                subscription,
            )

            return subscription

        # ----------------------------------------------------
        # ENTER GRACE PERIOD
        # ----------------------------------------------------

        subscription.status = (
            SUBSCRIPTION_PAST_DUE
        )

        subscription.grace_period_ends_at = (
            grace_end
        )

        sync_legacy_subscription_fields(
            creator,
            subscription,
        )

        return subscription

    # ========================================================
    # PAST DUE
    # ========================================================

    if status == SUBSCRIPTION_PAST_DUE:

        grace_end = normalize_datetime_utc(
            subscription.grace_period_ends_at
        )

        # ----------------------------------------------------
        # REBUILD MISSING GRACE DATE
        # ----------------------------------------------------
        #
        # Older records may have past_due status without
        # grace_period_ends_at.
        # ----------------------------------------------------

        if grace_end is None:

            grace_end = get_grace_period_end(
                subscription,
                grace_days=grace_days,
            )

            # ------------------------------------------------
            # NO PERIOD END
            # ------------------------------------------------

            if grace_end is None:

                subscription.status = (
                    SUBSCRIPTION_EXPIRED
                )

                subscription.grace_period_ends_at = (
                    None
                )

                sync_legacy_subscription_fields(
                    creator,
                    subscription,
                )

                return subscription

            subscription.grace_period_ends_at = (
                grace_end
            )

        # ----------------------------------------------------
        # GRACE PERIOD EXPIRED
        # ----------------------------------------------------

        if grace_end <= now:

            subscription.status = (
                SUBSCRIPTION_EXPIRED
            )

            subscription.grace_period_ends_at = (
                None
            )

            sync_legacy_subscription_fields(
                creator,
                subscription,
            )

            return subscription

        # ----------------------------------------------------
        # STILL WITHIN GRACE PERIOD
        # ----------------------------------------------------

        sync_legacy_subscription_fields(
            creator,
            subscription,
        )

        return subscription

    # ========================================================
    # UNKNOWN STATUS
    # ========================================================
    #
    # Do not accidentally grant Studio access for an unknown
    # subscription state.
    # ========================================================

    subscription.status = (
        SUBSCRIPTION_INACTIVE
    )

    subscription.grace_period_ends_at = (
        None
    )

    sync_legacy_subscription_fields(
        creator,
        subscription,
    )

    return subscription


# ============================================================
# SUBSCRIPTION ACCESS CHECK
# ============================================================

def creator_subscription_is_current(
    creator,
):
    """
    Return True when the creator should currently have Studio
    subscription access.

    Access is allowed during:

        active paid period
        past_due grace period

    Access is denied during:

        inactive
        expired
        cancelled

    This function evaluates the lifecycle first.

    IMPORTANT:

    It does NOT commit lifecycle changes.
    """

    subscription = (
        enforce_subscription_lifecycle(
            creator
        )
    )

    now = utc_now()

    # --------------------------------------------------------
    # MODERN SUBSCRIPTION
    # --------------------------------------------------------

    if subscription:

        if (
            subscription.status
            == SUBSCRIPTION_ACTIVE
        ):

            end = normalize_datetime_utc(
                subscription.current_period_end
            )

            return (
                end is None
                or end > now
            )

        if (
            subscription.status
            == SUBSCRIPTION_PAST_DUE
        ):

            grace_end = normalize_datetime_utc(
                subscription.grace_period_ends_at
            )

            return (
                grace_end is not None
                and grace_end > now
            )

        return False

    # --------------------------------------------------------
    # LEGACY FALLBACK
    # --------------------------------------------------------
    #
    # Temporary compatibility for creators who have not yet
    # received a PlatformSubscription row.
    # --------------------------------------------------------

    if (
        creator.subscription_status
        != SUBSCRIPTION_ACTIVE
    ):

        return False

    end = normalize_datetime_utc(
        creator.subscription_expires_at
    )

    return (
        end is None
        or end > now
    )


# ============================================================
# ACTIVATE SUBSCRIPTION
# ============================================================

def activate_creator_subscription(
    creator,
    plan=None,
    days=DEFAULT_PERIOD_DAYS,
    provider="manual",
):
    """
    Activate a creator subscription.

    Used for:

        first admin-approved activation
        manual activation
        payment-driven renewal

    If the creator still has paid time remaining, new time is
    added after the existing paid period.
    """

    now = utc_now()

    plan = normalize_plan(
        plan
        or creator.plan
    )

    subscription = get_creator_subscription(
        creator,
        create=True,
    )

    existing_end = normalize_datetime_utc(
        subscription.current_period_end
    )

    # --------------------------------------------------------
    # DETERMINE START POINT
    # --------------------------------------------------------

    if (
        existing_end
        and existing_end > now
    ):

        start_from = existing_end

    else:

        start_from = now

    # --------------------------------------------------------
    # ORIGINAL SUBSCRIPTION START DATE
    # --------------------------------------------------------

    if not subscription.started_at:

        subscription.started_at = (
            now
        )

    # --------------------------------------------------------
    # ACTIVATE
    # --------------------------------------------------------

    subscription.plan = (
        plan
    )

    subscription.status = (
        SUBSCRIPTION_ACTIVE
    )

    subscription.provider = (
        provider
    )

    subscription.current_period_start = (
        start_from
    )

    subscription.current_period_end = (
        start_from
        + timedelta(
            days=days
        )
    )

    subscription.grace_period_ends_at = (
        None
    )

    subscription.cancelled_at = (
        None
    )

    sync_legacy_subscription_fields(
        creator,
        subscription,
    )

    return subscription


# ============================================================
# RENEW SUBSCRIPTION
# ============================================================

def renew_creator_subscription(
    creator,
    days=DEFAULT_PERIOD_DAYS,
    plan=None,
    provider="manual",
):
    """
    Renew or reactivate a creator subscription.

    Examples:

        active → active + 30 days

        past_due → active + new paid period

        expired → active + new paid period
    """

    return activate_creator_subscription(
        creator,
        plan=plan,
        days=days,
        provider=provider,
    )


# ============================================================
# MARK SUBSCRIPTION PAST DUE
# ============================================================

def mark_subscription_past_due(
    creator,
    grace_days=GRACE_PERIOD_DAYS,
):
    """
    Explicitly mark a subscription past_due.

    Grace is calculated from current_period_end whenever
    possible.

    This prevents creators from receiving a fresh seven-day
    grace period merely because processing happened late.
    """

    now = utc_now()

    subscription = get_creator_subscription(
        creator,
        create=True,
    )

    period_end = normalize_datetime_utc(
        subscription.current_period_end
    )

    if period_end:

        grace_end = (
            period_end
            + timedelta(
                days=grace_days
            )
        )

    else:

        grace_end = (
            now
            + timedelta(
                days=grace_days
            )
        )

    # --------------------------------------------------------
    # GRACE ALREADY OVER
    # --------------------------------------------------------

    if grace_end <= now:

        subscription.status = (
            SUBSCRIPTION_EXPIRED
        )

        subscription.grace_period_ends_at = (
            None
        )

    else:

        subscription.status = (
            SUBSCRIPTION_PAST_DUE
        )

        subscription.grace_period_ends_at = (
            grace_end
        )

    sync_legacy_subscription_fields(
        creator,
        subscription,
    )

    return subscription


# ============================================================
# EXPIRE SUBSCRIPTION
# ============================================================

def expire_creator_subscription(
    creator,
):
    """
    Expire creator Studio access.

    IMPORTANT:

    We intentionally DO NOT replace current_period_end with
    the current time.

    current_period_end represents when the creator's paid
    period actually ended and is useful for billing history
    and auditing.

    Public creator content is not deleted or modified.
    """

    subscription = get_creator_subscription(
        creator,
        create=True,
    )

    subscription.status = (
        SUBSCRIPTION_EXPIRED
    )

    subscription.grace_period_ends_at = (
        None
    )

    sync_legacy_subscription_fields(
        creator,
        subscription,
    )

    return subscription


# ============================================================
# CANCEL SUBSCRIPTION
# ============================================================

def cancel_creator_subscription(
    creator,
):
    """
    Cancel a creator subscription.

    Cancellation does not delete creator content.
    """

    subscription = get_creator_subscription(
        creator,
        create=True,
    )

    subscription.status = (
        SUBSCRIPTION_CANCELLED
    )

    subscription.cancelled_at = (
        utc_now()
    )

    subscription.grace_period_ends_at = (
        None
    )

    sync_legacy_subscription_fields(
        creator,
        subscription,
    )

    return subscription


# ============================================================
# RECORD SUBSCRIPTION PAYMENT
# ============================================================

def record_subscription_payment(
    creator,
    status="paid",
    provider="manual",
    provider_reference=None,
    subscription=None,
    plan=None,
    amount_cents=None,
):
    """
    Create a PlatformSubscriptionPayment record.

    This function does NOT commit.

    The caller controls the transaction.
    """

    plan = normalize_plan(
        plan
        or creator.plan
    )

    # --------------------------------------------------------
    # SERVER-SIDE PLAN PRICE
    # --------------------------------------------------------

    if amount_cents is None:

        amount_cents = int(
            PLAN_PRICES[
                plan
            ] * 100
        )

    # --------------------------------------------------------
    # SUBSCRIPTION RELATION
    # --------------------------------------------------------

    if subscription is None:

        subscription = get_creator_subscription(
            creator,
            create=False,
        )

    # --------------------------------------------------------
    # CREATE PAYMENT
    # --------------------------------------------------------

    payment = PlatformSubscriptionPayment(
        creator_account_id=creator.id,
        subscription_id=(
            subscription.id
            if subscription
            else None
        ),
        plan=plan,
        amount_cents=int(
            amount_cents
        ),
        currency="ZAR",
        provider=provider,
        provider_reference=(
            provider_reference
        ),
        status=status,
        paid_at=(
            utc_now()
            if status == "paid"
            else None
        ),
    )

    db.session.add(
        payment
    )

    return payment
