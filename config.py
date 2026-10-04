import os

from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


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

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///creator_blog.db",
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

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
      "Creator Blog",
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
    # MEMBERSHIP
    # ========================================================
