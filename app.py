from flask import Flask

from config import Config
from extensions import (
    db,
    migrate,
)


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

    from routes.public import (
        public_bp,
    )

    from routes.admin import (
        admin_bp,
    )

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
        backfill_existing_creator_command,
        initialize_production_identity,
    )

    app.cli.add_command(
        seed_command
    )

    app.cli.add_command(
        create_admin_command
    )

    app.cli.add_command(
        backfill_existing_creator_command
    )

    # ========================================================
    # PRODUCTION BOOTSTRAP
    # ========================================================
    #
    # This bootstrap remains deliberately limited.
    #
    # It can:
    #
    # - Create the initial platform AdminUser.
    # - Preserve/create the legacy CreatorProfile.
    #
    # It does NOT automatically create CreatorAccount records.
    #
    # CreatorAccount backfill is performed explicitly through:
    #
    #     flask backfill-existing-creator
    #
    # New SaaS creators will eventually register through the
    # creator registration flow.
    # ========================================================

    with app.app_context():

        try:

            result = (
                initialize_production_identity()
            )

            if result[
                "admin_created"
            ]:

                app.logger.info(
                    "Initial production admin created."
                )

            if result[
                "creator_created"
            ]:

                app.logger.info(
                    "Initial creator profile created."
                )

        except Exception:

            # =================================================
            # Bootstrap failure should be visible in Render
            # logs without preventing the Flask application
            # itself from starting.
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
