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

    from routes.creator_auth import (
        creator_auth_bp,
    )

    from routes.studio import (
        studio_bp,
    )

    from routes.payments import (
        payments_bp,
    )

    # --------------------------------------------------------
    # PUBLIC
    # --------------------------------------------------------

    app.register_blueprint(
        public_bp
    )

    # --------------------------------------------------------
    # PLATFORM ADMIN
    # --------------------------------------------------------

    app.register_blueprint(
        admin_bp
    )

    # --------------------------------------------------------
    # CREATOR AUTHENTICATION
    # --------------------------------------------------------

    app.register_blueprint(
        creator_auth_bp
    )

    # --------------------------------------------------------
    # CREATOR STUDIO
    # --------------------------------------------------------

    app.register_blueprint(
        studio_bp
    )

    # --------------------------------------------------------
    # PLATFORM PAYMENTS
    # --------------------------------------------------------

    app.register_blueprint(
        payments_bp
    )

    # ========================================================
    # CLI
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
