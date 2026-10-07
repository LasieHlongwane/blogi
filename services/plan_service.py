    FEATURE_FAN_SUPPORT: "Buy me a coffee",
    FEATURE_FUNDRAISING: "Fundraising campaigns",
    FEATURE_SCHEDULED_PUBLISHING: "Scheduled publishing",
    FEATURE_SUBSCRIBER_EXPORT: "Subscriber export",
    FEATURE_BRANDING: "Creator branding",
    FEATURE_SUBDOMAIN: "Kalxa creator subdomain",
    FEATURE_CUSTOM_DOMAIN: "Custom domain",
    FEATURE_ADVANCED_BRANDING: "Advanced white-label branding",
}

FEATURE_DESCRIPTIONS = {
    FEATURE_PUBLISHING: "Publish stories, reels and vlogs.",
    FEATURE_NEWSLETTER: "Collect subscribers and send new-content notifications.",
    FEATURE_BASIC_ANALYTICS: "View basic creator and content analytics.",
    FEATURE_ADVANCED_ANALYTICS: "Access deeper audience and content performance analytics.",
    FEATURE_EXCLUSIVE_CONTENT: "Publish content available only to eligible supporters or members.",
    FEATURE_PAID_MEMBERSHIPS: "Offer recurring paid fan memberships.",
    FEATURE_PAYOUT_CONNECTION: "Connect a payout account to receive creator earnings.",
    FEATURE_FAN_SUPPORT: "Receive voluntary support from fans through Buy me a coffee.",
    FEATURE_FUNDRAISING: "Create goal-based fundraising campaigns for projects and creator initiatives.",
    FEATURE_SCHEDULED_PUBLISHING: "Schedule content to publish later.",
    FEATURE_SUBSCRIBER_EXPORT: "Export your subscriber list.",
    FEATURE_BRANDING: "Customize your creator site's logo, colors and visual identity.",
    FEATURE_SUBDOMAIN: "Publish at yourname.creators.kalxa.co.za.",
    FEATURE_CUSTOM_DOMAIN: "Connect a verified domain you own, such as www.thandom.co.za.",
    FEATURE_ADVANCED_BRANDING: "Access additional white-label visual customization.",
}


def normalize_plan(value, default=PLAN_STANDARD):
    value = str(value or "").strip().lower()
    if value in VALID_PLANS:
        return value
    return default if default in VALID_PLANS else PLAN_STANDARD


def get_plan_price(plan):
    return PLAN_PRICES[normalize_plan(plan)]


def get_plan_price_cents(plan):
    return get_plan_price(plan) * 100


def get_creator_plan(creator):
    if not creator:
        return PLAN_STANDARD
    return normalize_plan(getattr(creator, "plan", None))


def creator_has_feature(creator, feature):
    """Plan entitlement only; caller must separately verify account/subscription status."""
    if not creator:
        return False
    return feature in PLAN_FEATURES.get(get_creator_plan(creator), set())


def creator_can_use_custom_domain(creator):
    return creator_has_feature(creator, FEATURE_CUSTOM_DOMAIN)


def creator_can_use_subdomain(creator):
    return creator_has_feature(creator, FEATURE_SUBDOMAIN)


def feature_is_premium_only(feature):
    return feature in PREMIUM_ONLY_FEATURES


def get_feature_label(feature):
    return FEATURE_LABELS.get(feature, "This feature")


def get_feature_description(feature):
    return FEATURE_DESCRIPTIONS.get(feature, "")


def creator_missing_feature_message(feature):
    label = get_feature_label(feature)
    if feature_is_premium_only(feature):
        return f"{label} is available on the Premium plan."
    return f"{label} is not available for your current account."


def creator_plan_summary(creator):
    plan = get_creator_plan(creator)
    features = PLAN_FEATURES.get(plan, set())
    return {
        "key": plan,
        "name": "Premium" if plan == PLAN_PREMIUM else "Standard",
        "price": PLAN_PRICES[plan],
        "price_cents": PLAN_PRICES[plan] * 100,
        "features": sorted(features),
        "is_standard": plan == PLAN_STANDARD,
        "is_premium": plan == PLAN_PREMIUM,
        "can_receive_support": FEATURE_FAN_SUPPORT in features,
        "can_connect_payout": FEATURE_PAYOUT_CONNECTION in features,
        "can_create_fundraiser": FEATURE_FUNDRAISING in features,
        "can_publish_exclusive": FEATURE_EXCLUSIVE_CONTENT in features,
        "can_offer_memberships": FEATURE_PAID_MEMBERSHIPS in features,
        "can_customize_branding": FEATURE_BRANDING in features,
        "can_use_subdomain": FEATURE_SUBDOMAIN in features,
        "can_use_custom_domain": FEATURE_CUSTOM_DOMAIN in features,
        "can_use_advanced_branding": FEATURE_ADVANCED_BRANDING in features,
        "domain_type": "custom_or_subdomain" if plan == PLAN_PREMIUM else "subdomain_only",
    }
