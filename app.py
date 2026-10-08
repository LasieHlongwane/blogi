from flask import Flask
from config import Config
from extensions import db, migrate
from services.hostname_resolver import install_hostname_resolver


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    migrate.init_app(app, db)

    import models  # noqa: F401 - registers SQLAlchemy models

    from routes.public import public_bp
    from routes.admin import admin_bp
    from routes.creator_auth import creator_auth_bp
    from routes.fan_payments import fan_payments_bp
    from routes.studio import studio_bp
    from routes.payments import payments_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(creator_auth_bp)
    app.register_blueprint(fan_payments_bp)
    app.register_blueprint(studio_bp)
    app.register_blueprint(payments_bp)

    # Must be registered after blueprint registration; runs before all views.
    install_hostname_resolver(app)

    from seed import seed_command, create_admin_command, initialize_production_identity
    app.cli.add_command(seed_command)
    app.cli.add_command(create_admin_command)

    with app.app_context():
        try:
            result = initialize_production_identity()
            if result.get("admin_created"):
                app.logger.info("Initial production admin created.")
            if result.get("creator_created"):
                app.logger.info("Initial creator profile created.")
        except Exception:
            app.logger.exception("Production identity bootstrap failed.")
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
