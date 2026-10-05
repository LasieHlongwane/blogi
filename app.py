from flask import Flask

from config import Config
from extensions import db, migrate


# ============================================================
# APPLICATION FACTORY
# ============================================================


def create_app():

    app = Flask(
        __name__
    )

    # ========================================================
    # CONFIGURATION
    # ========================================================

    app.config.from_object(
        Config
    )

    # ========================================================
    # EXTENSIONS
    # ========================================================

    db.init_app(
        app
    )

    migrate.init_app(
        app,
        db,
    )

    # ========================================================
    # MODELS
    # ========================================================

    import models

    # ========================================================
    # BLUEPRINTS
    # ========================================================

    from routes.public import public_bp
    from routes.admin import admin_bp

    app.register_blueprint(
        public_bp
    )

    app.register_blueprint(
        admin_bp
    )

    # ========================================================
    # CLI COMMANDS
    # ========================================================

    from seed import (
        seed_command,
        create_admin_command,
        backfill_creator_account_command,
        initialize_production_identity,
    )

    app.cli.add_command(
        seed_command
    )

    app.cli.add_command(
        create_admin_command
    )

    app.cli.add_command(
        backfill_creator_account_command
    )

    # ========================================================
    # PRODUCTION BOOTSTRAP
    # ========================================================
    #
    # The platform administrator and legacy creator profile
    # can still be bootstrapped from environment variables.
    #
    # IMPORTANT:
    #
    # CreatorAccount ownership is NOT automatically backfilled
    # here.
    #
    # That operation is intentionally explicit:
    #
    # python -m flask --app app backfill-creator-account
    #
    # This prevents application startup from unexpectedly
    # changing ownership of production data.
    # ========================================================

    with app.app_context():

        try:

            result = (
                initialize_production_identity()
            )

            if result["admin_created"]:

                app.logger.info(
                    "Initial production admin created."
                )

            if result["creator_created"]:

                app.logger.info(
                    "Initial creator profile created."
                )

        except Exception:

            # =================================================
            # IMPORTANT
            # =================================================
            #
            # Log bootstrap problems instead of preventing
            # the Flask application from starting.
            # =================================================

            app.logger.exception(
                "Production identity bootstrap failed."
            )

    return app


# ============================================================
# APPLICATION
# ============================================================


app = create_app()


# ============================================================
# DEVELOPMENT SERVER
# ============================================================


if __name__ == "__main__":

    app.run(
        debug=True,
    )
