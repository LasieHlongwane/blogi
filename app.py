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
        initialize_production_identity,
    )

    app.cli.add_command(
        seed_command
    )

    app.cli.add_command(
        create_admin_command
    )

    # ========================================================
    # PRODUCTION BOOTSTRAP
    # ========================================================
    #
    # Render Free does not provide convenient shell access.
    #
    # Therefore the first production administrator and creator
    # profile can be created from environment variables.
    #
    # initialize_production_identity() is idempotent:
    #
    # - Existing admins are NOT recreated.
    # - Existing passwords are NOT reset.
    # - Existing creator profiles are NOT overwritten.
    #
    # The database schema must already exist through Alembic
    # migrations before this executes.
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
            # We log bootstrap problems instead of preventing
            # the entire Flask application from starting.
            #
            # Database/application errors will therefore remain
            # visible in Render logs for diagnosis.
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
