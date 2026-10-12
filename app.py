"""
KALXA CREATOR
Flask Application Factory

Features:
- Creator websites
- Creator authentication
- Creator Studio
- Fan payments
- Yoco plan activation
- Paystack integration
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
    # NEON POSTGRESQL CONNECTION RELIABILITY
    # ========================================================
    #
    # Neon may close idle database connections.
    #
    # Without pool_pre_ping, SQLAlchemy may attempt to
    # reuse a connection that is no longer available.
    #
    # This can produce errors such as:
    #
    # psycopg.OperationalError:
    # SSL connection has been closed unexpectedly
    #
    # These options improve connection reliability.
    #
    # IMPORTANT:
    # Configure the engine before db.init_app(app).
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

    # Preserve other engine options already supplied by Config.
    existing_engine_options.update(connection_options)

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

    import models  # noqa: F401

    # ========================================================
    # IMPORT BLUEPRINTS
    # ========================================================

    from routes.public import public_bp

    from routes.admin import admin_bp

    from routes.creator_auth import creator_auth_bp

    from routes.fan_payments import fan_payments_bp

    from routes.studio import studio_bp

    from routes.payments import payments_bp

    # ========================================================
    # REGISTER BLUEPRINTS
    # ========================================================

    app.register_blueprint(
        public_bp
    )

    app.register_blueprint(
        admin_bp
    )

    app.register_blueprint(
        creator_auth_bp
    )

    app.register_blueprint(
        fan_payments_bp
    )

    app.register_blueprint(
        studio_bp
    )

    app.register_blueprint(
        payments_bp
    )

    # ========================================================
    # INSTALL HOSTNAME RESOLVER
    # ========================================================
    #
    # Must be installed after blueprint registration.
    #
    # Used to resolve creator-specific domains.
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
