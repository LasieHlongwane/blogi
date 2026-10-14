
import os

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# DATABASE CONFIGURATION HELPERS
# ============================================================

def get_database_url():
    """
    Return the configured database URL.

    Production:
        Neon PostgreSQL

    Local development:
        SQLite

    Supports common PostgreSQL URL formats used by
    hosting providers.
    """

    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite:///creator_blog.db",
    ).strip()

    # Normalize legacy PostgreSQL URL schemes.
    if database_url.startswith("postgres://"):

        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )

    elif database_url.startswith("postgresql://"):

        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    return database_url


def get_database_engine_options(database_url):
    """
    Configure SQLAlchemy connection handling.

    PostgreSQL:
        - Validate pooled connections.
        - Recycle older connections.
        - Use a small connection pool.
        - Require SSL for Neon.

    SQLite:
        - Preserve local development compatibility.
    """

    url = make_url(database_url)

    if url.get_backend_name() == "postgresql":

        return {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": 3,
            "max_overflow": 2,
            "pool_timeout": 30,

            "connect_args": {
                "connect_timeout": 10,
                "sslmode": "require",
            },
        }

    return {
        "pool_pre_ping": True,
    }


# ============================================================
# KALXA CREATOR — PRICING CONFIGURATION
# ============================================================

# Store monetary values in cents to avoid floating-point
# errors when working with payments.
#
# R1.00 = 100 cents

PLAN_PRICES_CENTS = {
    "free": 0,
    "standard": 30000,
    "premium": 50000,
}

# Commission rates are stored in basis points.
#
# 10000 basis points = 100%
# 2500 basis points = 25%
#  800 basis points = 8%
#  500 basis points = 5%

PLAN_COMMISSION_BPS = {
    "free": 2500,
    "standard": 800,
    "premium": 500,
}

# Standard → Premium upgrade:
# R500 Premium - R300 Standard = R200
#
# Eligibility must be verified using the creator's
# successful Standard activation payment record.

STANDARD_TO_PREMIUM_UPGRADE_CENTS = 20000


def get_plan_price_cents(plan):
    """
    Return the once-off activation price for a plan.
    """

    plan = str(plan).strip().lower()

    if plan not in PLAN_PRICES_CENTS:
        raise ValueError(
            f"Unsupported creator plan: {plan}"
        )

    return PLAN_PRICES_CENTS[plan]


def get_plan_commission_bps(plan):
    """
    Return the Kalxa commission rate in basis points.
    """

    plan = str(plan).strip().lower()

    if plan not in PLAN_COMMISSION_BPS:
        raise ValueError(
            f"Unsupported creator plan: {plan}"
        )

    return PLAN_COMMISSION_BPS[plan]


def calculate_platform_fee_cents(
    amount_cents,
    plan,
):
    """
    Calculate Kalxa's commission on a fan payment.

    Uses integer arithmetic with half-up rounding.

    Payment provider fees are not deducted here.
    """

    if (
        isinstance(amount_cents, bool)
        or not isinstance(amount_cents, int)
        or amount_cents <= 0
    ):
        raise ValueError(
            "Payment amount must be a positive integer "
            "number of cents."
        )

    commission_bps = get_plan_commission_bps(
        plan
    )

    return (
        amount_cents * commission_bps + 5000
    ) // 10000


def calculate_creator_share_cents(
    amount_cents,
    plan,
):
    """
    Return the creator's share after Kalxa commission.

    Payment provider fees are excluded.
    """

    platform_fee_cents = (
        calculate_platform_fee_cents(
            amount_cents,
            plan,
        )
    )

    return (
        amount_cents - platform_fee_cents
    )


# ============================================================
# CONFIG
# ============================================================

class Config:

    # ========================================================
    # FLASK
    # ========================================================

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "development-secret-key",
    )

    # ========================================================
    # DATABASE
    # ========================================================

    SQLALCHEMY_DATABASE_URI = get_database_url()

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SQLALCHEMY_ENGINE_OPTIONS = (
        get_database_engine_options(
            SQLALCHEMY_DATABASE_URI
        )
    )

    # ========================================================
    # UPLOAD LIMIT
    # ========================================================

    MAX_CONTENT_LENGTH = (
        100 * 1024 * 1024
    )

    # ========================================================
    # CLOUDINARY
    # ========================================================

    CLOUDINARY_CLOUD_NAME = os.getenv(
        "CLOUDINARY_CLOUD_NAME"
    )

    CLOUDINARY_API_KEY = os.getenv(
        "CLOUDINARY_API_KEY"
    )

    CLOUDINARY_API_SECRET = os.getenv(
        "CLOUDINARY_API_SECRET"
    )

    CLOUDINARY_FOLDER = os.getenv(
        "CLOUDINARY_FOLDER",
        "creator-blog",
    )

    # ========================================================
    # SMTP
    # ========================================================

    SMTP_HOST = os.getenv(
        "SMTP_HOST"
    )

    SMTP_PORT = int(
        os.getenv(
            "SMTP_PORT",
            "587",
        )
    )

    SMTP_USERNAME = os.getenv(
        "SMTP_USERNAME"
    )

    SMTP_PASSWORD = os.getenv(
        "SMTP_PASSWORD"
    )

    SMTP_FROM_EMAIL = os.getenv(
        "SMTP_FROM_EMAIL"
    )

    SMTP_FROM_NAME = os.getenv(
        "SMTP_FROM_NAME",
        "Creator Platform",
    )

    SMTP_USE_TLS = (
        os.getenv(
            "SMTP_USE_TLS",
            "true",
        )
        .lower()
        == "true"
    )

    # ========================================================
    # WEBSITE
    # ========================================================

    SITE_URL = (
        os.getenv(
            "SITE_URL",
            "http://127.0.0.1:5000",
        )
        .rstrip("/")
    )

    # ========================================================
    # CREATOR SAAS
    # ========================================================

    CREATOR_REGISTRATION_FEE_CENTS = int(
        os.getenv(
            "CREATOR_REGISTRATION_FEE_CENTS",
            "0",
        )
    )

    # Preserved for compatibility with existing features.
    # Creator plan activation fees are once-off, not monthly.
    CREATOR_SUBSCRIPTION_DAYS = int(
        os.getenv(
            "CREATOR_SUBSCRIPTION_DAYS",
            "30",
        )
    )

    # ========================================================
    # CREATOR PRICING
    # ========================================================

    CREATOR_FREE_ACTIVATION_CENTS = (
        PLAN_PRICES_CENTS["free"]
    )

    CREATOR_STANDARD_ACTIVATION_CENTS = (
        PLAN_PRICES_CENTS["standard"]
    )

    CREATOR_PREMIUM_ACTIVATION_CENTS = (
        PLAN_PRICES_CENTS["premium"]
    )

    CREATOR_STANDARD_TO_PREMIUM_UPGRADE_CENTS = (
        STANDARD_TO_PREMIUM_UPGRADE_CENTS
    )

    CREATOR_FREE_COMMISSION_BPS = (
        PLAN_COMMISSION_BPS["free"]
    )

    CREATOR_STANDARD_COMMISSION_BPS = (
        PLAN_COMMISSION_BPS["standard"]
    )

    CREATOR_PREMIUM_COMMISSION_BPS = (
        PLAN_COMMISSION_BPS["premium"]
    )

    CREATOR_PLAN_PRICES_CENTS = (
        PLAN_PRICES_CENTS.copy()
    )

    CREATOR_PLAN_COMMISSION_BPS = (
        PLAN_COMMISSION_BPS.copy()
    )

    # ========================================================
    # YOCO
    # ========================================================
    #
    # Yoco handles once-off creator plan activations.
    #
    # Never commit actual Yoco credentials to GitHub.
    # ========================================================

    YOCO_SECRET_KEY = os.getenv(
        "YOCO_SECRET_KEY"
    )

    YOCO_API_KEY = os.getenv(
        "YOCO_API_KEY"
    )

    YOCO_CHECKOUT_URL = os.getenv(
        "YOCO_CHECKOUT_URL",
        "https://payments.yoco.com/api/checkouts",
    )

    YOCO_WEBHOOK_SECRET = os.getenv(
        "YOCO_WEBHOOK_SECRET"
    )

    # ========================================================
    # PAYSTACK
    # ========================================================
    #
    # Paystack handles eligible fan payments.
    #
    # Commission must be calculated and recorded
    # server-side for each payment.
    #
    # Never expose the secret key in frontend code.
    # ========================================================

    PAYSTACK_SECRET_KEY = os.getenv(
        "PAYSTACK_SECRET_KEY"
    )

    PAYSTACK_PUBLIC_KEY = os.getenv(
        "PAYSTACK_PUBLIC_KEY"
    )

    PAYSTACK_BASE_URL = os.getenv(
        "PAYSTACK_BASE_URL",
        "https://api.paystack.co",
    )
