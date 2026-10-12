"""
============================================================
KALXA CREATOR
PLAN SERVICE
============================================================

One-time activation plans and feature entitlements.

PLANS:

FREE
    Activation: R0
    Fan support commission: 23%

STANDARD
    Activation: R100 once-off
    Fan support commission: 3%

PREMIUM
    Activation: R150 once-off
    Fan support commission: 3%

UPGRADE:

Standard -> Premium:
    R50 once-off, provided the previous Standard
    activation was successfully verified.

SECURITY:

- Free creators require an active account.
- Paid creators require an active account and verified
  activation.
- Unknown plans receive no entitlements.
- Selecting a paid plan does not grant paid features.
- Payment verification must happen server-side.
============================================================
"""


# ============================================================
# PLAN CONSTANTS
# ============================================================

PLAN_FREE = "free"
PLAN_STANDARD = "standard"
PLAN_PREMIUM = "premium"


VALID_PLANS = frozenset({
    PLAN_FREE,
    PLAN_STANDARD,
    PLAN_PREMIUM,
})


PAID_PLANS = frozenset({
    PLAN_STANDARD,
    PLAN_PREMIUM,
})


# ============================================================
# PLAN ACTIVATION PRICES
# ============================================================
#
# Prices are in South African rand.
#
# These are ONCE-OFF activation prices.
# They are NOT monthly subscription fees.
# ============================================================

PLAN_PRICES = {
    PLAN_FREE: 0,
    PLAN_STANDARD: 100,
    PLAN_PREMIUM: 150,
}


PLAN_ACTIVATION_PRICES = PLAN_PRICES


# ============================================================
# UPGRADE PRICES
# ============================================================

STANDARD_TO_PREMIUM_UPGRADE_PRICE = 50

STANDARD_TO_PREMIUM_UPGRADE_CENTS = 5000


# ============================================================
# COMMISSION RATES
# ============================================================
#
# Expressed as integer percentages.
#
# Example:
#
# Free creator receives R100:
#     Kalxa commission: R23
#
# Standard/Premium receives R100:
#     Kalxa commission: R3
#
# Actual payment calculations must be performed by the
# payment service using integer cents.
# ============================================================

PLAN_COMMISSION_PERCENTAGES = {
    PLAN_FREE: 23,
    PLAN_STANDARD: 3,
    PLAN_PREMIUM: 3,
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

FEATURE_DONATIONS = "donations"

FEATURE_FUNDRAISING = "fundraising"

FEATURE_SCHEDULED_PUBLISHING = "scheduled_publishing"

FEATURE_SUBSCRIBER_EXPORT = "subscriber_export"


# ============================================================
# WHITE-LABEL FEATURES
# ============================================================

FEATURE_BRANDING = "branding"

FEATURE_SUBDOMAIN = "subdomain"

FEATURE_CUSTOM_DOMAIN = "custom_domain"

FEATURE_ADVANCED_BRANDING = "advanced_branding"


# ============================================================
# FREE FEATURES
# ============================================================

FREE_FEATURES = {
    FEATURE_PUBLISHING,
    FEATURE_NEWSLETTER,
    FEATURE_BASIC_ANALYTICS,
    FEATURE_PAYOUT_CONNECTION,
    FEATURE_FAN_SUPPORT,
}


# ============================================================
# STANDARD FEATURES
# ============================================================

STANDARD_FEATURES = (
    FREE_FEATURES
    | {
        FEATURE_DONATIONS,
        FEATURE_EXCLUSIVE_CONTENT,
        FEATURE_PAID_MEMBERSHIPS,
        FEATURE_BRANDING,
        FEATURE_SUBDOMAIN,
    }
)


# ============================================================
# PREMIUM FEATURES
# ============================================================

PREMIUM_FEATURES = (
    STANDARD_FEATURES
    | {
        FEATURE_ADVANCED_ANALYTICS,
        FEATURE_FUNDRAISING,
        FEATURE_SCHEDULED_PUBLISHING,
        FEATURE_SUBSCRIBER_EXPORT,
        FEATURE_CUSTOM_DOMAIN,
        FEATURE_ADVANCED_BRANDING,
    }
)


# ============================================================
# PLAN FEATURE ENTITLEMENTS
# ============================================================

PLAN_FEATURES = {
    PLAN_FREE: FREE_FEATURES,
    PLAN_STANDARD: STANDARD_FEATURES,
    PLAN_PREMIUM: PREMIUM_FEATURES,
}


# ============================================================
# FEATURE GROUPS
# ============================================================

PREMIUM_ONLY_FEATURES = (
    PLAN_FEATURES[PLAN_PREMIUM]
    - PLAN_FEATURES[PLAN_STANDARD]
)


STANDARD_AND_ABOVE_FEATURES = (
    PLAN_FEATURES[PLAN_STANDARD]
    - PLAN_FEATURES[PLAN_FREE]
)


ALL_PAID_PLAN_FEATURES = (
    PLAN_FEATURES[PLAN_STANDARD]
    | PLAN_FEATURES[PLAN_PREMIUM]
)


# ============================================================
# FEATURE LABELS
# ============================================================

FEATURE_LABELS = {
    FEATURE_PUBLISHING:
        "Content publishing",

    FEATURE_NEWSLETTER:
        "Email newsletters",

    FEATURE_BASIC_ANALYTICS:
        "Basic analytics",

    FEATURE_ADVANCED_ANALYTICS:
        "Advanced analytics",

    FEATURE_EXCLUSIVE_CONTENT:
        "Exclusive content",

    FEATURE_PAID_MEMBERSHIPS:
        "Paid memberships",

    FEATURE_PAYOUT_CONNECTION:
        "Payout account connection",

    FEATURE_FAN_SUPPORT:
        "Buy Me a Coffee",

    FEATURE_DONATIONS:
        "Donations",

    FEATURE_FUNDRAISING:
        "Fundraising campaigns",

    FEATURE_SCHEDULED_PUBLISHING:
        "Scheduled publishing",

    FEATURE_SUBSCRIBER_EXPORT:
        "Subscriber export",

    FEATURE_BRANDING:
        "Creator branding",

    FEATURE_SUBDOMAIN:
        "Kalxa creator subdomain",

    FEATURE_CUSTOM_DOMAIN:
        "Custom domain",

    FEATURE_ADVANCED_BRANDING:
        "Advanced white-label branding",
}


# ============================================================
# FEATURE DESCRIPTIONS
# ============================================================

FEATURE_DESCRIPTIONS = {
    FEATURE_PUBLISHING:
        "Publish stories, reels and vlogs.",

    FEATURE_NEWSLETTER:
        (
            "Collect subscribers and send "
            "new-content notifications."
        ),

    FEATURE_BASIC_ANALYTICS:
        (
            "View basic creator and "
            "content analytics."
        ),

    FEATURE_ADVANCED_ANALYTICS:
        (
            "Access deeper audience and "
            "content performance analytics."
        ),

    FEATURE_EXCLUSIVE_CONTENT:
        (
            "Publish content available only "
            "to eligible supporters or members."
        ),

    FEATURE_PAID_MEMBERSHIPS:
        "Offer recurring paid fan memberships.",

    FEATURE_PAYOUT_CONNECTION:
        (
            "Connect a payout account "
            "to receive creator earnings."
        ),

    FEATURE_FAN_SUPPORT:
        (
            "Receive voluntary Buy Me a Coffee "
            "contributions from fans."
        ),

    FEATURE_DONATIONS:
        (
            "Receive donations through the "
            "separate donations feature."
        ),

    FEATURE_FUNDRAISING:
        (
            "Create goal-based fundraising "
            "campaigns."
        ),

    FEATURE_SCHEDULED_PUBLISHING:
        "Schedule content to publish later.",

    FEATURE_SUBSCRIBER_EXPORT:
        "Export your subscriber list.",

    FEATURE_BRANDING:
        (
            "Customize your creator site's "
            "logo, colors and visual identity."
        ),

    FEATURE_SUBDOMAIN:
        (
            "Publish using a Kalxa "
            "creator subdomain."
        ),

    FEATURE_CUSTOM_DOMAIN:
        (
            "Connect a verified domain "
            "that you own."
        ),

    FEATURE_ADVANCED_BRANDING:
        (
            "Access advanced white-label "
            "visual customization."
        ),
}


# ============================================================
# NORMALIZE PLAN
# ============================================================

def normalize_plan(
    value,
    default=PLAN_FREE,
):
    """
    Normalize a plan identifier.

    Unknown plans default to Free for display purposes.

    IMPORTANT:
    Authorization must still use the creator's actual
    plan and must never upgrade unknown plans.
    """

    value = str(
        value or ""
    ).strip().lower()

    if value in VALID_PLANS:
        return value

    default = str(
        default or ""
    ).strip().lower()

    if default in VALID_PLANS:
        return default

    return PLAN_FREE


# ============================================================
# GET PLAN PRICE
# ============================================================

def get_plan_price(plan):
    """
    Return the once-off activation price in ZAR.
    """

    plan = normalize_plan(
        plan
    )

    return PLAN_PRICES[plan]


# ============================================================
# GET PLAN PRICE IN CENTS
# ============================================================

def get_plan_price_cents(plan):
    """
    Return the once-off activation price in cents.
    """

    return (
        get_plan_price(plan)
        * 100
    )


# ============================================================
# GET CREATOR PLAN
# ============================================================

def get_creator_plan(creator):
    """
    Return the creator's assigned plan.

    Unknown values are preserved as an empty/unknown plan
    for authorization rather than silently granting
    Standard entitlements.
    """

    if creator is None:
        return ""

    plan = str(
        getattr(
            creator,
            "plan",
            "",
        )
        or ""
    ).strip().lower()

    if plan not in VALID_PLANS:
        return ""

    return plan


# ============================================================
# CREATOR ACCOUNT ACTIVE
# ============================================================

def creator_account_is_active(creator):

    if creator is None:
        return False

    return (
        str(
            getattr(
                creator,
                "account_status",
                "",
            )
            or ""
        ).strip().lower()
        == "active"
    )


# ============================================================
# PAID ACTIVATION VERIFIED
# ============================================================

def creator_paid_activation_verified(creator):
    """
    Verify locally recorded activation state.

    The payment service must only set these fields after
    verifying payment with Yoco server-side.

    This function does not contact Yoco.
    """

    if creator is None:
        return False

    payment_status = str(
        getattr(
            creator,
            "payment_status",
            "",
        )
        or ""
    ).strip().lower()

    registration_paid_at = getattr(
        creator,
        "registration_paid_at",
        None,
    )

    return bool(
        payment_status == "paid"
        and registration_paid_at is not None
    )


# ============================================================
# CREATOR STUDIO ACCESS
# ============================================================

def creator_can_enter_studio(creator):
    """
    Determine whether a creator can access Studio.

    Free:
        Active account.

    Standard/Premium:
        Active account and verified activation.
    """

    if not creator_account_is_active(
        creator
    ):
        return False

    plan = get_creator_plan(
        creator
    )

    if plan == PLAN_FREE:
        return True

    if plan in PAID_PLANS:

        return creator_paid_activation_verified(
            creator
        )

    return False


# ============================================================
# FEATURE ACCESS
# ============================================================

def creator_has_feature(
    creator,
    feature,
):
    """
    Check both plan entitlement and account eligibility.

    Free:
        Active account.

    Standard/Premium:
        Active account and verified activation.

    Unknown plans:
        No access.
    """

    if not creator_can_enter_studio(
        creator
    ):
        return False

    plan = get_creator_plan(
        creator
    )

    return feature in PLAN_FEATURES.get(
        plan,
        set(),
    )


# ============================================================
# DOMAIN FEATURES
# ============================================================

def creator_can_use_custom_domain(
    creator
):

    return creator_has_feature(
        creator,
        FEATURE_CUSTOM_DOMAIN,
    )


def creator_can_use_subdomain(
    creator
):

    return creator_has_feature(
        creator,
        FEATURE_SUBDOMAIN,
    )


def creator_can_customize_branding(
    creator
):

    return creator_has_feature(
        creator,
        FEATURE_BRANDING,
    )


def creator_can_use_advanced_branding(
    creator
):

    return creator_has_feature(
        creator,
        FEATURE_ADVANCED_BRANDING,
    )


# ============================================================
# PREMIUM FEATURE CHECK
# ============================================================

def feature_is_premium_only(
    feature
):

    return (
        feature
        in PREMIUM_ONLY_FEATURES
    )


# ============================================================
# FEATURE LABEL
# ============================================================

def get_feature_label(
    feature
):

    return FEATURE_LABELS.get(
        feature,
        "This feature",
    )


# ============================================================
# FEATURE DESCRIPTION
# ============================================================

def get_feature_description(
    feature
):

    return FEATURE_DESCRIPTIONS.get(
        feature,
        "",
    )


# ============================================================
# MISSING FEATURE MESSAGE
# ============================================================

def creator_missing_feature_message(
    feature
):

    label = get_feature_label(
        feature
    )

    if feature in PREMIUM_ONLY_FEATURES:

        return (
            f"{label} is available "
            "on the Premium plan."
        )

    if feature in STANDARD_AND_ABOVE_FEATURES:

        return (
            f"{label} is available "
            "on Standard and Premium plans."
        )

    return (
        f"{label} is not available "
        "for your current account."
    )


# ============================================================
# COMMISSION
# ============================================================

def get_plan_commission_percentage(
    plan
):

    plan = normalize_plan(
        plan
    )

    return PLAN_COMMISSION_PERCENTAGES[
        plan
    ]


def get_creator_commission_percentage(
    creator
):
    """
    Unknown/inactive creators receive the highest
    commission rate as a conservative fallback.

    Payment initiation must separately verify eligibility.
    """

    if not creator_can_enter_studio(
        creator
    ):

        return PLAN_COMMISSION_PERCENTAGES[
            PLAN_FREE
        ]

    plan = get_creator_plan(
        creator
    )

    return PLAN_COMMISSION_PERCENTAGES.get(
        plan,
        PLAN_COMMISSION_PERCENTAGES[
            PLAN_FREE
        ],
    )


# ============================================================
# CREATOR PLAN SUMMARY
# ============================================================

def creator_plan_summary(
    creator
):
    """
    Return plan information for Studio templates.

    Retains existing keys for backwards compatibility.
    """

    plan = get_creator_plan(
        creator
    )

    if not plan:
        plan = PLAN_FREE

    features = (
        PLAN_FEATURES.get(
            plan,
            set(),
        )
        if creator_can_enter_studio(
            creator
        )
        else set()
    )

    name = {
        PLAN_FREE: "Free",
        PLAN_STANDARD: "Standard",
        PLAN_PREMIUM: "Premium",
    }[plan]

    commission_percentage = (
        PLAN_COMMISSION_PERCENTAGES[
            plan
        ]
    )

    return {
        "key": plan,

        "name": name,

        "price": PLAN_PRICES[plan],

        "price_cents": (
            PLAN_PRICES[plan]
            * 100
        ),

        "activation_price": (
            PLAN_PRICES[plan]
        ),

        "activation_price_cents": (
            PLAN_PRICES[plan]
            * 100
        ),

        "billing_type": "once_off",

        "commission_percentage": (
            commission_percentage
        ),

        "features": sorted(
            features
        ),

        "is_free": (
            plan == PLAN_FREE
        ),

        "is_standard": (
            plan == PLAN_STANDARD
        ),

        "is_premium": (
            plan == PLAN_PREMIUM
        ),

        "is_active": (
            creator_can_enter_studio(
                creator
            )
        ),

        # ----------------------------------------------------
        # MONETIZATION
        # ----------------------------------------------------

        "can_receive_support": (
            FEATURE_FAN_SUPPORT
            in features
        ),

        "can_connect_payout": (
            FEATURE_PAYOUT_CONNECTION
            in features
        ),

        "can_receive_donations": (
            FEATURE_DONATIONS
            in features
        ),

        "can_create_fundraiser": (
            FEATURE_FUNDRAISING
            in features
        ),

        "can_publish_exclusive": (
            FEATURE_EXCLUSIVE_CONTENT
            in features
        ),

        "can_offer_memberships": (
            FEATURE_PAID_MEMBERSHIPS
            in features
        ),

        # ----------------------------------------------------
        # WHITE-LABEL
        # ----------------------------------------------------

        "can_customize_branding": (
            FEATURE_BRANDING
            in features
        ),

        "can_use_subdomain": (
            FEATURE_SUBDOMAIN
            in features
        ),

        "can_use_custom_domain": (
            FEATURE_CUSTOM_DOMAIN
            in features
        ),

        "can_use_advanced_branding": (
            FEATURE_ADVANCED_BRANDING
            in features
        ),

        "domain_type": (
            "custom_or_subdomain"
            if plan == PLAN_PREMIUM
            else (
                "subdomain_only"
                if plan == PLAN_STANDARD
                else "platform_profile"
            )
        ),
    }
