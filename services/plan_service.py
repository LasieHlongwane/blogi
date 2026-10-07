# ============================================================
# CREATOR PLATFORM
# PLAN / FEATURE SERVICE
# ============================================================


# ============================================================
# PLANS
# ============================================================

PLAN_STANDARD = "standard"
PLAN_PREMIUM = "premium"


VALID_PLANS = {
    PLAN_STANDARD,
    PLAN_PREMIUM,
}


# ============================================================
# PLAN PRICES
# ============================================================

PLAN_PRICES = {

    PLAN_STANDARD: 79,

    PLAN_PREMIUM: 149,

}


# ============================================================
# CORE FEATURES
# ============================================================

FEATURE_PUBLISHING = (
    "publishing"
)

FEATURE_NEWSLETTER = (
    "newsletter"
)

FEATURE_BASIC_ANALYTICS = (
    "basic_analytics"
)

FEATURE_ADVANCED_ANALYTICS = (
    "advanced_analytics"
)


# ============================================================
# CONTENT MONETISATION
# ============================================================

FEATURE_EXCLUSIVE_CONTENT = (
    "exclusive_content"
)

FEATURE_PAID_MEMBERSHIPS = (
    "paid_memberships"
)


# ============================================================
# CREATOR EARNINGS
# ============================================================

# Allows the creator to connect the payout account that
# receives fan/support/campaign payments.
#
# This is available to BOTH Standard and Premium creators.
FEATURE_PAYOUT_CONNECTION = (
    "payout_connection"
)


# Voluntary creator support.
#
# Public examples:
#
#   Buy me a coffee
#   Support this creator
#
# This does NOT unlock exclusive content.
#
# Available to BOTH Standard and Premium.
FEATURE_FAN_SUPPORT = (
    "fan_support"
)


# Premium creators can create goal-based fundraising
# campaigns.
#
# Example:
#
#   Help fund my next documentary
#   Goal: R15,000
#   Raised: R8,450
#
# Premium only.
FEATURE_FUNDRAISING = (
    "fundraising"
)


# ============================================================
# CREATOR TOOLS
# ============================================================

FEATURE_SCHEDULED_PUBLISHING = (
    "scheduled_publishing"
)

FEATURE_SUBSCRIBER_EXPORT = (
    "subscriber_export"
)


# ============================================================
# PLAN FEATURES
# ============================================================

PLAN_FEATURES = {

    # --------------------------------------------------------
    # STANDARD
    # R79/month
    #
    # Build your audience + receive voluntary support.
    # --------------------------------------------------------

    PLAN_STANDARD: {

        FEATURE_PUBLISHING,

        FEATURE_NEWSLETTER,

        FEATURE_BASIC_ANALYTICS,

        # Creator monetisation
        FEATURE_PAYOUT_CONNECTION,

        FEATURE_FAN_SUPPORT,

    },


    # --------------------------------------------------------
    # PREMIUM
    # R149/month
    #
    # Everything in Standard plus advanced monetisation
    # and growth tools.
    # --------------------------------------------------------

    PLAN_PREMIUM: {

        # Core
        FEATURE_PUBLISHING,

        FEATURE_NEWSLETTER,

        FEATURE_BASIC_ANALYTICS,


        # Creator earnings
        FEATURE_PAYOUT_CONNECTION,

        FEATURE_FAN_SUPPORT,


        # Premium content monetisation
        FEATURE_EXCLUSIVE_CONTENT,

        FEATURE_PAID_MEMBERSHIPS,

        FEATURE_FUNDRAISING,


        # Premium growth tools
        FEATURE_ADVANCED_ANALYTICS,

        FEATURE_SCHEDULED_PUBLISHING,

        FEATURE_SUBSCRIBER_EXPORT,

    },

}


# ============================================================
# FEATURE LABELS
# ============================================================

FEATURE_LABELS = {

    FEATURE_PUBLISHING:
        "Publishing",

    FEATURE_NEWSLETTER:
        "Newsletter",

    FEATURE_BASIC_ANALYTICS:
        "Basic analytics",

    FEATURE_ADVANCED_ANALYTICS:
        "Advanced analytics",

    FEATURE_EXCLUSIVE_CONTENT:
        "Exclusive content",

    FEATURE_PAID_MEMBERSHIPS:
        "Paid fan memberships",

    FEATURE_PAYOUT_CONNECTION:
        "Payout connection",

    FEATURE_FAN_SUPPORT:
        "Buy me a coffee",

    FEATURE_FUNDRAISING:
        "Fundraising campaigns",

    FEATURE_SCHEDULED_PUBLISHING:
        "Scheduled publishing",

    FEATURE_SUBSCRIBER_EXPORT:
        "Subscriber export",

}


# ============================================================
# FEATURE DESCRIPTIONS
# ============================================================

FEATURE_DESCRIPTIONS = {

    FEATURE_PUBLISHING:
        (
            "Publish stories, reels and vlogs."
        ),

    FEATURE_NEWSLETTER:
        (
            "Collect subscribers and send "
            "new-content notifications."
        ),

    FEATURE_BASIC_ANALYTICS:
        (
            "View basic creator and content analytics."
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
        (
            "Offer recurring paid fan memberships."
        ),

    FEATURE_PAYOUT_CONNECTION:
        (
            "Connect a payout account to receive "
            "creator earnings."
        ),

    FEATURE_FAN_SUPPORT:
        (
            "Receive voluntary support from fans "
            "through Buy me a coffee."
        ),

    FEATURE_FUNDRAISING:
        (
            "Create goal-based fundraising campaigns "
            "for projects and creator initiatives."
        ),

    FEATURE_SCHEDULED_PUBLISHING:
        (
            "Schedule content to publish later."
        ),

    FEATURE_SUBSCRIBER_EXPORT:
        (
            "Export your subscriber list."
        ),

}


# ============================================================
# PREMIUM-ONLY FEATURES
# ============================================================

PREMIUM_ONLY_FEATURES = {

    FEATURE_ADVANCED_ANALYTICS,

    FEATURE_EXCLUSIVE_CONTENT,

    FEATURE_PAID_MEMBERSHIPS,

    FEATURE_FUNDRAISING,

    FEATURE_SCHEDULED_PUBLISHING,

    FEATURE_SUBSCRIBER_EXPORT,

}


# ============================================================
# STANDARD + PREMIUM FEATURES
# ============================================================

ALL_PAID_PLAN_FEATURES = {

    FEATURE_PUBLISHING,

    FEATURE_NEWSLETTER,

    FEATURE_BASIC_ANALYTICS,

    FEATURE_PAYOUT_CONNECTION,

    FEATURE_FAN_SUPPORT,

}


# ============================================================
# NORMALIZE PLAN
# ============================================================

def normalize_plan(
    value,
    default=PLAN_STANDARD,
):
    """
    Convert an incoming plan value into a supported plan key.

    Invalid/missing values fall back to Standard unless a
    different valid default is explicitly supplied.
    """

    value = (
        value
        or ""
    )

    value = (
        value
        .strip()
        .lower()
    )

    if value in VALID_PLANS:

        return value

    if default in VALID_PLANS:

        return default

    return PLAN_STANDARD


# ============================================================
# PLAN PRICE
# ============================================================

def get_plan_price(
    plan,
):
    """
    Return the monthly plan price in South African Rand.
    """

    plan = normalize_plan(
        plan
    )

    return PLAN_PRICES[
        plan
    ]


# ============================================================
# PLAN PRICE IN CENTS
# ============================================================

def get_plan_price_cents(
    plan,
):
    """
    Return the monthly plan price in cents.

    Example:

        Standard -> 7900
        Premium  -> 14900
    """

    return (
        get_plan_price(
            plan
        )
        * 100
    )


# ============================================================
# CREATOR PLAN
# ============================================================

def get_creator_plan(
    creator,
):
    """
    Return the normalized plan for a creator.
    """

    if not creator:

        return PLAN_STANDARD

    return normalize_plan(
        getattr(
            creator,
            "plan",
            None,
        )
    )


# ============================================================
# CREATOR HAS FEATURE
# ============================================================

def creator_has_feature(
    creator,
    feature,
):
    """
    Server-side feature gate.

    Never rely only on hiding buttons in templates.
    """

    if not creator:

        return False

    plan = get_creator_plan(
        creator
    )

    return (
        feature
        in PLAN_FEATURES.get(
            plan,
            set(),
        )
    )


# ============================================================
# FEATURE IS PREMIUM ONLY
# ============================================================

def feature_is_premium_only(
    feature,
):

    return (
        feature
        in PREMIUM_ONLY_FEATURES
    )


# ============================================================
# FEATURE LABEL
# ============================================================

def get_feature_label(
    feature,
):

    return FEATURE_LABELS.get(
        feature,
        "This feature",
    )


# ============================================================
# FEATURE DESCRIPTION
# ============================================================

def get_feature_description(
    feature,
):

    return FEATURE_DESCRIPTIONS.get(
        feature,
        "",
    )


# ============================================================
# MISSING FEATURE MESSAGE
# ============================================================

def creator_missing_feature_message(
    feature,
):
    """
    Produce a user-facing message for a blocked feature.
    """

    label = get_feature_label(
        feature
    )

    if feature_is_premium_only(
        feature
    ):

        return (
            f"{label} is available "
            f"on the Premium plan."
        )

    return (
        f"{label} is not available "
        f"for your current account."
    )


# ============================================================
# CREATOR PLAN SUMMARY
# ============================================================

def creator_plan_summary(
    creator,
):

    plan = get_creator_plan(
        creator
    )

    features = (
        PLAN_FEATURES.get(
            plan,
            set(),
        )
    )

    return {

        "key":
            plan,

        "name":
            (
                "Premium"
                if plan
                == PLAN_PREMIUM
                else "Standard"
            ),

        "price":
            PLAN_PRICES[
                plan
            ],

        "price_cents":
            (
                PLAN_PRICES[
                    plan
                ]
                * 100
            ),

        "features":
            sorted(
                features
            ),

        "is_standard":
            (
                plan
                == PLAN_STANDARD
            ),

        "is_premium":
            (
                plan
                == PLAN_PREMIUM
            ),

        "can_receive_support":
            (
                FEATURE_FAN_SUPPORT
                in features
            ),

        "can_connect_payout":
            (
                FEATURE_PAYOUT_CONNECTION
                in features
            ),

        "can_create_fundraiser":
            (
                FEATURE_FUNDRAISING
                in features
            ),

        "can_publish_exclusive":
            (
                FEATURE_EXCLUSIVE_CONTENT
                in features
            ),

        "can_offer_memberships":
            (
                FEATURE_PAID_MEMBERSHIPS
                in features
            ),

    }
