   
"""Kalxa Creator SaaS subscription plans and feature entitlements."""

# ============================================================
# PLANS AND PRICES
# ============================================================

PLAN_STANDARD = "standard"
PLAN_PREMIUM = "premium"

VALID_PLANS = {
    PLAN_STANDARD,
    PLAN_PREMIUM,
}

# Monthly subscription prices in South African rand.
PLAN_PRICES = {
    PLAN_STANDARD: 79,
    PLAN_PREMIUM: 149,
}


# ============================================================
# FEATURE CONSTANTS
# ============================================================

FEATURE_PUBLISHING = "publishing"
FEATURE_NEWSLETTER = "newsletter"

FEATURE_BASIC_ANALYTICS = "basic_analytics"
FEATURE_ADVANCED_ANALYTICS = "advanced_analytics"

FEATURE_EXCLUSIVE_CONTENT = "exclusive_content"
FEATURE_PAID_MEMBERSHIPS = "paid_memberships"

FEATURE_PAYOUT_CONNECTION = "payout_connection"
FEATURE_FAN_SUPPORT = "fan_support"
FEATURE_FUNDRAISING = "fundraising"

FEATURE_SCHEDULED_PUBLISHING = "scheduled_publishing"
FEATURE_SUBSCRIBER_EXPORT = "subscriber_export"

# White-label features
FEATURE_BRANDING = "branding"
FEATURE_SUBDOMAIN = "subdomain"
FEATURE_CUSTOM_DOMAIN = "custom_domain"
FEATURE_ADVANCED_BRANDING = "advanced_branding"


# ============================================================
# PLAN FEATURE ENTITLEMENTS
# ============================================================

PLAN_FEATURES = {
    PLAN_STANDARD: {
        FEATURE_PUBLISHING,
        FEATURE_NEWSLETTER,
        FEATURE_BASIC_ANALYTICS,
        FEATURE_PAYOUT_CONNECTION,
        FEATURE_FAN_SUPPORT,
        FEATURE_BRANDING,
        FEATURE_SUBDOMAIN,
    },

    PLAN_PREMIUM: {
        FEATURE_PUBLISHING,
        FEATURE_NEWSLETTER,
        FEATURE_BASIC_ANALYTICS,
        FEATURE_ADVANCED_ANALYTICS,
        FEATURE_EXCLUSIVE_CONTENT,
        FEATURE_PAID_MEMBERSHIPS,
        FEATURE_PAYOUT_CONNECTION,
        FEATURE_FAN_SUPPORT,
        FEATURE_FUNDRAISING,
        FEATURE_SCHEDULED_PUBLISHING,
        FEATURE_SUBSCRIBER_EXPORT,
        FEATURE_BRANDING,
        FEATURE_SUBDOMAIN,
        FEATURE_CUSTOM_DOMAIN,
        FEATURE_ADVANCED_BRANDING,
    },
}


# ============================================================
# FEATURE GROUPS
# ============================================================

PREMIUM_ONLY_FEATURES = (
    PLAN_FEATURES[PLAN_PREMIUM]
    - PLAN_FEATURES[PLAN_STANDARD]
)

ALL_PAID_PLAN_FEATURES = (
    PLAN_FEATURES[PLAN_STANDARD]
    | PLAN_FEATURES[PLAN_PREMIUM]
)


# ============================================================
# FEATURE LABELS
# ============================================================

FEATURE_LABELS = {
    FEATURE_PUBLISHING: "Content publishing",
    FEATURE_NEWSLETTER: "Email newsletters",
    FEATURE_BASIC_ANALYTICS: "Basic analytics",
    FEATURE_ADVANCED_ANALYTICS: "Advanced analytics",
    FEATURE_EXCLUSIVE_CONTENT: "Exclusive content",
    FEATURE_PAID_MEMBERSHIPS: "Paid memberships",
    FEATURE_PAYOUT_CONNECTION: "Payout account connection",
    FEATURE_FAN_SUPPORT: "Buy me a coffee",
    FEATURE_FUNDRAISING: "Fundraising campaigns",
    FEATURE_SCHEDULED_PUBLISHING: "Scheduled publishing",
    FEATURE_SUBSCRIBER_EXPORT: "Subscriber export",
    FEATURE_BRANDING: "Creator branding",
    FEATURE_SUBDOMAIN: "Kalxa creator subdomain",
    FEATURE_CUSTOM_DOMAIN: "Custom domain",
    FEATURE_ADVANCED_BRANDING: "Advanced white-label branding",
}


# ============================================================
# FEATURE DESCRIPTIONS
# ============================================================

FEATURE_DESCRIPTIONS = {
    FEATURE_PUBLISHING:
        "Publish stories, reels and vlogs.",

    FEATURE_NEWSLETTER:
        "Collect subscribers and send new-content notifications.",

    FEATURE_BASIC_ANALYTICS:
        "View basic creator and content analytics.",

    FEATURE_ADVANCED_ANALYTICS:
        "Access deeper audience and content performance analytics.",

    FEATURE_EXCLUSIVE_CONTENT:
        "Publish content available only to eligible supporters or members.",

    FEATURE_PAID_MEMBERSHIPS:
        "Offer recurring paid fan memberships.",

    FEATURE_PAYOUT_CONNECTION:
        "Connect a payout account to receive creator earnings.",

    FEATURE_FAN_SUPPORT:
        "Receive voluntary support from fans through Buy me a coffee.",

    FEATURE_FUNDRAISING:
        "Create goal-based fundraising campaigns for projects and creator initiatives.",

    FEATURE_SCHEDULED_PUBLISHING:
        "Schedule content to publish later.",

    FEATURE_SUBSCRIBER_EXPORT:
        "Export your subscriber list.",

    FEATURE_BRANDING:
        "Customize your creator site's logo, colors and visual identity.",

    FEATURE_SUBDOMAIN:
        "Publish at yourname.creators.kalxa.co.za.",

    FEATURE_CUSTOM_DOMAIN:
        "Connect a verified domain you own, such as www.thandom.co.za.",

    FEATURE_ADVANCED_BRANDING:
        "Access additional white-label visual customization.",
}


# ============================================================
# PLAN HELPERS
# ============================================================

def normalize_plan(value, default=PLAN_STANDARD):
    """Return a supported plan key."""
    value = str(value or "").strip().lower()

    if value in VALID_PLANS:
        return value

    return (
        default
        if default in VALID_PLANS
        else PLAN_STANDARD
    )


def get_plan_price(plan):
    """Return monthly subscription price in ZAR."""
    return PLAN_PRICES[normalize_plan(plan)]


def get_plan_price_cents(plan):
    """Return monthly subscription price in cents."""
    return get_plan_price(plan) * 100


def get_creator_plan(creator):
    """Read the creator's assigned subscription plan."""
    if not creator:
        return PLAN_STANDARD

    return normalize_plan(
        getattr(creator, "plan", None)
    )


# ============================================================
# FEATURE ACCESS
# ============================================================

def creator_has_feature(creator, feature):
    """
    Check plan entitlement only.

    IMPORTANT:
    This does not verify whether the creator's account
    or platform subscription is currently active.

    Protected routes must perform those checks separately.
    """
    if not creator:
        return False

    plan = get_creator_plan(creator)

    return feature in PLAN_FEATURES.get(
        plan,
        set(),
    )


def creator_can_use_custom_domain(creator):
    """Premium plan entitlement for custom domains."""
    return creator_has_feature(
        creator,
        FEATURE_CUSTOM_DOMAIN,
    )


def creator_can_use_subdomain(creator):
    """Plan entitlement for Kalxa creator subdomains."""
    return creator_has_feature(
        creator,
        FEATURE_SUBDOMAIN,
    )


def creator_can_customize_branding(creator):
    """Check basic creator branding entitlement."""
    return creator_has_feature(
        creator,
        FEATURE_BRANDING,
    )


def creator_can_use_advanced_branding(creator):
    """Check Premium white-label branding entitlement."""
    return creator_has_feature(
        creator,
        FEATURE_ADVANCED_BRANDING,
    )


def feature_is_premium_only(feature):
    return feature in PREMIUM_ONLY_FEATURES


def get_feature_label(feature):
    return FEATURE_LABELS.get(
        feature,
        "This feature",
    )


def get_feature_description(feature):
    return FEATURE_DESCRIPTIONS.get(
        feature,
        "",
    )


def creator_missing_feature_message(feature):
    """Generate a user-facing upgrade or access message."""
    label = get_feature_label(feature)

    if feature_is_premium_only(feature):
        return (
            f"{label} is available on the Premium plan."
        )

    return (
        f"{label} is not available for your current account."
    )


# ============================================================
# CREATOR PLAN SUMMARY
# ============================================================

def creator_plan_summary(creator):
    """Return plan details for Studio, pricing and billing pages."""

    plan = get_creator_plan(creator)
    features = PLAN_FEATURES.get(plan, set())

    return {
        "key": plan,

        "name": (
            "Premium"
            if plan == PLAN_PREMIUM
            else "Standard"
        ),

        "price": PLAN_PRICES[plan],
        "price_cents": PLAN_PRICES[plan] * 100,

        "features": sorted(features),

        "is_standard": plan == PLAN_STANDARD,
        "is_premium": plan == PLAN_PREMIUM,

        # Monetization
        "can_receive_support":
            FEATURE_FAN_SUPPORT in features,

        "can_connect_payout":
            FEATURE_PAYOUT_CONNECTION in features,

        "can_create_fundraiser":
            FEATURE_FUNDRAISING in features,

        "can_publish_exclusive":
            FEATURE_EXCLUSIVE_CONTENT in features,

        "can_offer_memberships":
            FEATURE_PAID_MEMBERSHIPS in features,

        # White-label
        "can_customize_branding":
            FEATURE_BRANDING in features,

        "can_use_subdomain":
            FEATURE_SUBDOMAIN in features,

        "can_use_custom_domain":
            FEATURE_CUSTOM_DOMAIN in features,

        "can_use_advanced_branding":
            FEATURE_ADVANCED_BRANDING in features,

        "domain_type": (
            "custom_or_subdomain"
            if plan == PLAN_PREMIUM
            else "subdomain_only"
        ),
    }
