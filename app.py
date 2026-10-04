from flask import Flask

from config import Config
from extensions import db, migrate


# ============================================================
# APPLICATION FACTORY
# ============================================================

def create_app():

    app = Flask(__name__)

    # ========================================================
    # CONFIGURATION
    # ========================================================

    app.config.from_object(Config)

    # ========================================================
    # EXTENSIONS
    # ========================================================

    db.init_app(app)

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

    from seed import seed_command

    app.cli.add_command(
        seed_command
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
    
from flask import Flask

from config import Config
from extensions import db, migrate


# ============================================================
# APPLICATION FACTORY
# ============================================================

def create_app():

    app = Flask(__name__)

    # ========================================================
    # CONFIGURATION
    # ========================================================

    app.config.from_object(Config)

    # ========================================================
    # EXTENSIONS
    # ========================================================

    db.init_app(app)

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

    from seed import seed_command

    app.cli.add_command(
        seed_command
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