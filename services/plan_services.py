# ============================================================
# CREATOR PLATFORM
# PLAN / FEATURE SERVICE
# ============================================================


# ============================================================
# PLAN NAMES
# ============================================================

PLAN_STANDARD = "standard"
PLAN_PREMIUM = "premium"


VALID_PLANS = {
    PLAN_STANDARD,
    PLAN_PREMIUM,
}


# ============================================================
# PRICING
# ============================================================
#
# Amounts are stored in South African Rand.
#
# Payment-provider amounts can later be converted into cents
# when Yoco integration is added.
# ============================================================

PLAN_PRICES = {
    PLAN_STANDARD: 79,
    PLAN_PREMIUM: 149,
}


# ============================================================
# FEATURE NAMES
# ============================================================

FEATURE_PUBLISH_CONTENT = "publish_content"

FEATURE_STORIES = "stories"

FEATURE_REELS = "reels"

FEATURE_VLOGS = "vlogs"

FEATURE_CATEGORIES = "categories"

FEATURE_COMMENTS = "comments"

FEATURE_NEWSLETTER = "newsletter"

FEATURE_BASIC_ANALYTICS = "basic_analytics"

FEATURE_ADVANCED_ANALYTICS = "advanced_analytics"

FEATURE_EXCLUSIVE_CONTENT = "exclusive_content"

FEATURE_SCHEDULED_PUBLISHING = "scheduled_publishing"

FEATURE_SUBSCRIBER_EXPORT = "subscriber_export"

FEATURE_FAN_SUPPORT = "fan_support"

FEATURE_PAYOUT_CONNECTION = "payout_connection"

FEATURE_FAN_MEMBERSHIPS = "fan_memberships"

FEATURE_PRIORITY_SUPPORT = "priority_support"


# ============================================================
# STANDARD FEATURES
# ============================================================

STANDARD_FEATURES = {
    FEATURE_PUBLISH_CONTENT,
    FEATURE_STORIES,
    FEATURE_REELS,
    FEATURE_VLOGS,
    FEATURE_CATEGORIES,
    FEATURE_COMMENTS,
    FEATURE_NEWSLETTER,
    FEATURE_BASIC_ANALYTICS,
}


# ============================================================
# PREMIUM FEATURES
# ============================================================

PREMIUM_FEATURES = (
    STANDARD_FEATURES
    | {
        FEATURE_ADVANCED_ANALYTICS,
        FEATURE_EXCLUSIVE_CONTENT,
        FEATURE_SCHEDULED_PUBLISHING,
        FEATURE_SUBSCRIBER_EXPORT,
        FEATURE_FAN_SUPPORT,
        FEATURE_PAYOUT_CONNECTION,
        FEATURE_FAN_MEMBERSHIPS,
        FEATURE_PRIORITY_SUPPORT,
    }
)


# ============================================================
# PLAN FEATURES
# ============================================================

PLAN_FEATURES = {
    PLAN_STANDARD: STANDARD_FEATURES,
    PLAN_PREMIUM: PREMIUM_FEATURES,
}


# ============================================================
# SUBSCRIBER LIMITS
# ============================================================
#
# None means no application-level limit.
#
# We can change Premium to a hard limit later if desired.
# ============================================================

PLAN_SUBSCRIBER_LIMITS = {
    PLAN_STANDARD: 500,
    PLAN_PREMIUM: 5000,
}


# ============================================================
# PLAN NORMALIZATION
# ============================================================

def normalize_plan(
    plan,
    default=PLAN_STANDARD,
):
    """
    Normalize a creator plan value.
    """

    value = (
        str(plan or "")
        .strip()
        .lower()
    )

    if value in VALID_PLANS:
        return value

    return default


# ============================================================
# VALID PLAN
# ============================================================

def is_valid_plan(
    plan,
):

    return (
        normalize_plan(
            plan,
            default="",
        )
        in VALID_PLANS
    )


# ============================================================
# PLAN DISPLAY NAME
# ============================================================

def plan_display_name(
    plan,
):

    plan = normalize_plan(
        plan
    )

    if plan == PLAN_PREMIUM:
        return "Premium"

    return "Standard"


# ============================================================
# PLAN PRICE
# ============================================================

def plan_price(
    plan,
):

    plan = normalize_plan(
        plan
    )

    return PLAN_PRICES[
        plan
    ]


# ============================================================
# CREATOR PLAN
# ============================================================

def creator_plan(
    creator,
):
    """
    Return a safe normalized creator plan.

    Existing/legacy creator rows that somehow have no plan
    are treated as Premium for compatibility.
    """

    if not creator:
        return PLAN_STANDARD

    raw_plan = getattr(
        creator,
        "plan",
        None,
    )

    if not raw_plan:

        return PLAN_PREMIUM

    return normalize_plan(
        raw_plan,
        default=PLAN_PREMIUM,
    )


# ============================================================
# FEATURE CHECK
# ============================================================

def creator_has_feature(
    creator,
    feature,
):
    """
    Return True when the creator's plan includes a feature.

    This is the central feature gate for the application.
    """

    if not creator:
        return False

    plan = creator_plan(
        creator
    )

    features = PLAN_FEATURES.get(
        plan,
        set(),
    )

    return feature in features


# ============================================================
# REQUIRE FEATURE
# ============================================================

def creator_missing_feature_message(
    feature,
):
    """
    Human-friendly upgrade message for blocked features.
    """

    messages = {
        FEATURE_EXCLUSIVE_CONTENT: (
            "Exclusive content is available on "
            "the Premium plan."
        ),

        FEATURE_ADVANCED_ANALYTICS: (
            "Advanced analytics is available on "
            "the Premium plan."
        ),

        FEATURE_SCHEDULED_PUBLISHING: (
            "Scheduled publishing is available on "
            "the Premium plan."
        ),

        FEATURE_SUBSCRIBER_EXPORT: (
            "Subscriber export is available on "
            "the Premium plan."
        ),

        FEATURE_FAN_SUPPORT: (
            "Fan support is available on "
            "the Premium plan."
        ),

        FEATURE_PAYOUT_CONNECTION: (
            "Creator payouts are available on "
            "the Premium plan."
        ),

        FEATURE_FAN_MEMBERSHIPS: (
            "Fan memberships are available on "
            "the Premium plan."
        ),

        FEATURE_PRIORITY_SUPPORT: (
            "Priority support is available on "
            "the Premium plan."
        ),
    }

    return messages.get(
        feature,
        "This feature is not available on your current plan.",
    )


# ============================================================
# SUBSCRIBER LIMIT
# ============================================================

def creator_subscriber_limit(
    creator,
):

    plan = creator_plan(
        creator
    )

    return PLAN_SUBSCRIBER_LIMITS.get(
        plan
    )


# ============================================================
# SUBSCRIBER CAPACITY
# ============================================================

def creator_can_add_subscriber(
    creator,
    current_count,
):
    """
    Return True if the creator can accept another newsletter
    subscriber under the current plan.
    """

    limit = creator_subscriber_limit(
        creator
    )

    if limit is None:
        return True

    return current_count < limit


# ============================================================
# PLAN SUMMARY
# ============================================================

def creator_plan_summary(
    creator,
):
    """
    Return plan metadata useful for templates.
    """

    plan = creator_plan(
        creator
    )

    return {
        "code": plan,
        "name": plan_display_name(
            plan
        ),
        "price": plan_price(
            plan
        ),
        "subscriber_limit": (
            creator_subscriber_limit(
                creator
            )
        ),
        "features": (
            PLAN_FEATURES.get(
                plan,
                set(),
            )
        ),
    }
