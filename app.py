"""
KALXA CREATOR
Flask Application Factory

Features:
- Creator websites
- Creator authentication
- Creator Studio
- Fan payments / Buy Me a Coffee
- Exclusive creator memberships
- Email-based membership architecture
- Manual monthly membership renewals
- Paystack split-payment integration
- Yoco plan activation
- Custom-domain resolution
- Neon PostgreSQL
- Flask-Migrate
"""

from flask import Flask

from config import Config

from extensions import db, migrate

from services.hostname_resolver import install_hostname_resolver


# ============================================================
# APPLICATION FACTORY
# ============================================================

def create_app():

    app = Flask(__name__)

    # ========================================================
    # LOAD APPLICATION CONFIGURATION
    # ========================================================

    app.config.from_object(Config)

    # ========================================================
    # EXCLUSIVE MEMBERSHIP CONFIGURATION
    # ========================================================
    #
    # Memberships use manual monthly renewal.
    #
    # Subscribers:
    # - Choose an amount from R30 upwards.
    # - Pay through Paystack.
    # - Do not need traditional customer accounts.
    # - Will authenticate using secure email links.
    #
    # IMPORTANT:
    # These settings do not automatically activate
    # membership access or recurring billing.
    # ========================================================

    app.config.setdefault(
        "MEMBERSHIP_MIN_AMOUNT_CENTS",
        3000,
    )

    app.config.setdefault(
        "MEMBERSHIP_MAX_AMOUNT_CENTS",
        10_000_000,
    )

    app.config.setdefault(
        "MEMBERSHIP_CURRENCY",
        "ZAR",
    )

    app.config.setdefault(
        "MEMBERSHIP_PAYMENT_PROVIDER",
        "paystack",
    )

    app.config.setdefault(
        "MEMBERSHIP_AUTOMATIC_RENEWAL",
        False,
    )

    app.config.setdefault(
        "MEMBERSHIP_RENEWAL_REMINDER_DAYS",
        7,
    )

    # ========================================================
    # NEON POSTGRESQL CONNECTION RELIABILITY
    # ========================================================
    #
    # Neon may close idle database connections.
    #
    # pool_pre_ping checks connections before reuse.
    # pool_recycle avoids excessively old connections.
    #
    # Configure these options before db.init_app(app).
    # ========================================================

    existing_engine_options = dict(
        app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {}
    )

    connection_options = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 30,
    }

    # Preserve other options already supplied by Config.
    existing_engine_options.update(
        connection_options
    )

    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = (
        existing_engine_options
    )

    # ========================================================
    # INITIALIZE DATABASE
    # ========================================================

    db.init_app(app)

    # ========================================================
    # INITIALIZE DATABASE MIGRATIONS
    # ========================================================

    migrate.init_app(
        app,
        db,
    )

    # ========================================================
    # REGISTER SQLALCHEMY MODELS
    # ========================================================
    #
    # Import models before running migrations.
    #
    # Existing application models are defined in models.py.
    #
    # New membership models are defined in
    # membership_models.py.
    #
    # Importing both modules ensures Flask-Migrate
    # can discover the membership tables.
    # ========================================================

    import models  # noqa: F401

    import membership_models  # noqa: F401

    # ========================================================
    # IMPORT BLUEPRINTS
    # ========================================================

    # --------------------------------------------------------
    # PUBLIC CREATOR WEBSITES
    # --------------------------------------------------------

    from routes.public import public_bp

    # --------------------------------------------------------
    # PLATFORM ADMINISTRATION
    # --------------------------------------------------------

    from routes.admin import admin_bp

    # --------------------------------------------------------
    # CREATOR AUTHENTICATION
    # --------------------------------------------------------

    from routes.creator_auth import creator_auth_bp

    # --------------------------------------------------------
    # BUY ME A COFFEE / FUNDRAISING
    # --------------------------------------------------------

    from routes.fan_payments import fan_payments_bp

    # --------------------------------------------------------
    # CREATOR STUDIO
    # --------------------------------------------------------

    from routes.studio import studio_bp

    # --------------------------------------------------------
    # YOCO CREATOR PLAN PAYMENTS
    # --------------------------------------------------------

    from routes.payments import payments_bp

    # --------------------------------------------------------
    # EXCLUSIVE MEMBERSHIPS
    # --------------------------------------------------------
    #
    # Handles:
    #
    # - Public membership checkout
    # - Custom membership contribution amounts
    # - Paystack membership payments
    # - Payment verification
    # - Membership activation
    # - Manual renewal
    #
    # Passwordless email login and protected media
    # will be integrated separately.
    # --------------------------------------------------------

    from routes.membership_routes import membership_bp

    # ========================================================
    # REGISTER BLUEPRINTS
    # ========================================================

    # --------------------------------------------------------
    # PUBLIC
    # --------------------------------------------------------

    app.register_blueprint(
        public_bp
    )

    # --------------------------------------------------------
    # ADMIN
    # --------------------------------------------------------

    app.register_blueprint(
        admin_bp
    )

    # --------------------------------------------------------
    # CREATOR AUTH
    # --------------------------------------------------------

    app.register_blueprint(
        creator_auth_bp
    )

    # --------------------------------------------------------
    # FAN PAYMENTS
    # --------------------------------------------------------

    app.register_blueprint(
        fan_payments_bp
    )

    # --------------------------------------------------------
    # CREATOR STUDIO
    # --------------------------------------------------------

    app.register_blueprint(
        studio_bp
    )

    # --------------------------------------------------------
    # YOCO PAYMENTS
    # --------------------------------------------------------

    app.register_blueprint(
        payments_bp
    )

    # --------------------------------------------------------
    # EXCLUSIVE MEMBERSHIPS
    # --------------------------------------------------------

    app.register_blueprint(
        membership_bp
    )

    # ========================================================
    # INSTALL HOSTNAME RESOLVER
    # ========================================================
    #
    # Must be installed after blueprint registration.
    #
    # Resolves:
    #
    # - Creator-specific websites
    # - Creator subdomains
    # - Custom domains
    #
    # Existing hostname resolution behavior is preserved.
    # ========================================================

    install_hostname_resolver(
        app
    )

    # ========================================================
    # REGISTER CLI COMMANDS
    # ========================================================

    from seed import (
        seed_command,
        create_admin_command,
        initialize_production_identity,
    )

    app.cli.add_command(
        seed_command
    )

    app.cli.add_command(
        create_admin_command
    )

    # ========================================================
    # INITIALIZE PRODUCTION IDENTITY
    # ========================================================
    #
    # Preserve the existing bootstrap behavior.
    #
    # This section may access the database during startup.
    # ========================================================

    with app.app_context():

        try:

            result = initialize_production_identity()

            if result.get("admin_created"):

                app.logger.info(
                    "Initial production admin created."
                )

            if result.get("creator_created"):

                app.logger.info(
                    "Initial creator profile created."
                )

        except Exception:

            app.logger.exception(
                "Production identity bootstrap failed."
            )

            # Clear any failed database transaction.
            db.session.rollback()

    # ========================================================
    # APPLICATION READY
    # ========================================================

    return app


# ============================================================
# APPLICATION INSTANCE
# ============================================================

app = create_app()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
