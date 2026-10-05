# ============================================================
# CREATOR PLATFORM
# PLAN / FEATURE SERVICE
# ============================================================

PLAN_STANDARD = "standard"
PLAN_PREMIUM = "premium"
VALID_PLANS = {PLAN_STANDARD, PLAN_PREMIUM}

PLAN_PRICES = {
    PLAN_STANDARD: 79,
    PLAN_PREMIUM: 149,
}

FEATURE_PUBLISHING = "publishing"
FEATURE_NEWSLETTER = "newsletter"
FEATURE_BASIC_ANALYTICS = "basic_analytics"
FEATURE_ADVANCED_ANALYTICS = "advanced_analytics"
FEATURE_EXCLUSIVE_CONTENT = "exclusive_content"
FEATURE_FAN_SUPPORT = "fan_support"
FEATURE_SCHEDULED_PUBLISHING = "scheduled_publishing"
FEATURE_SUBSCRIBER_EXPORT = "subscriber_export"
FEATURE_PAYOUT_CONNECTION = "payout_connection"

PLAN_FEATURES = {
    PLAN_STANDARD: {
        FEATURE_PUBLISHING,
        FEATURE_NEWSLETTER,
        FEATURE_BASIC_ANALYTICS,
    },
    PLAN_PREMIUM: {
        FEATURE_PUBLISHING,
        FEATURE_NEWSLETTER,
        FEATURE_BASIC_ANALYTICS,
        FEATURE_ADVANCED_ANALYTICS,
        FEATURE_EXCLUSIVE_CONTENT,
        FEATURE_FAN_SUPPORT,
        FEATURE_SCHEDULED_PUBLISHING,
        FEATURE_SUBSCRIBER_EXPORT,
        FEATURE_PAYOUT_CONNECTION,
    },
}

FEATURE_LABELS = {
    FEATURE_PUBLISHING: "Publishing",
    FEATURE_NEWSLETTER: "Newsletter",
    FEATURE_BASIC_ANALYTICS: "Basic analytics",
    FEATURE_ADVANCED_ANALYTICS: "Advanced analytics",
    FEATURE_EXCLUSIVE_CONTENT: "Exclusive content",
    FEATURE_FAN_SUPPORT: "Fan support",
    FEATURE_SCHEDULED_PUBLISHING: "Scheduled publishing",
    FEATURE_SUBSCRIBER_EXPORT: "Subscriber export",
    FEATURE_PAYOUT_CONNECTION: "Payout connection",
}


def normalize_plan(value, default=PLAN_STANDARD):
    value = (value or "").strip().lower()
    return value if value in VALID_PLANS else default


def creator_has_feature(creator, feature):
    if not creator:
        return False
    plan = normalize_plan(getattr(creator, "plan", None))
    return feature in PLAN_FEATURES.get(plan, set())


def creator_missing_feature_message(feature):
    label = FEATURE_LABELS.get(feature, "This feature")
    return f"{label} is available on the Premium plan."


def creator_plan_summary(creator):
    plan = normalize_plan(getattr(creator, "plan", None))
    return {
        "key": plan,
        "name": "Premium" if plan == PLAN_PREMIUM else "Standard",
        "price": PLAN_PRICES[plan],
        "features": sorted(PLAN_FEATURES[plan]),
        "is_standard": plan == PLAN_STANDARD,
        "is_premium": plan == PLAN_PREMIUM,
    }
