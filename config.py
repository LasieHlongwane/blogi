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
            # Check connections before reusing them.
            "pool_pre_ping": True,

            # Recycle connections older than 5 minutes.
            "pool_recycle": 300,

            # Maximum number of persistent connections
            # maintained per SQLAlchemy engine.
            "pool_size": 3,

            # Allow two additional temporary connections.
            "max_overflow": 2,

            # Wait up to 30 seconds for a connection.
            "pool_timeout": 30,

            # PostgreSQL driver connection settings.
            "connect_args": {
                "connect_timeout": 10,
                "sslmode": "require",
            },
        }

    # SQLite does not use PostgreSQL SSL settings.
    return {
        "pool_pre_ping": True,
    }


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

    CREATOR_SUBSCRIPTION_DAYS = int(
        os.getenv(
            "CREATOR_SUBSCRIPTION_DAYS",
            "30",
        )
    )

    # ========================================================
    # YOCO
    # ========================================================
    #
    # IMPORTANT:
    #
    # YOCO_SECRET_KEY must ONLY exist in the environment.
    #
    # Never commit actual Yoco credentials to GitHub.
    #
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
