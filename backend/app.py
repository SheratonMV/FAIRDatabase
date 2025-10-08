"""Main application of the Flask API. Registers all blueprints and then
starts the server."""

import os

from flask import Flask, flash, g, json, redirect, url_for
from flask_cors import CORS

from config import Config, get_db, limiter, supabase_extension, teardown_db, validate_config
from src.auth.routes import routes as auth_routes
from src.dashboard.routes import routes as dashboard_routes
from src.data.routes import routes as data_routes
from src.exceptions import GenericExceptionHandler
from src.main.routes import routes as main_routes
from src.privacy.routes import routes as privacy_routes


def create_app(db_name=None, env=None):
    """Construct the core application of Flask. Holds an
    optional argument to override the databse URI, this is used
    for Pytest."""
    app = Flask(
        __name__,
        template_folder=os.path.abspath("../frontend/templates"),
        static_folder=os.path.abspath("../static"),
    )
    app.config.from_object(Config)
    if db_name is not None:
        app.config["POSTGRES_DB_NAME"] = db_name
    if env is not None:
        app.config["ENV"] = env

    # Validate required configuration
    validate_config()

    app.register_blueprint(main_routes, url_prefix="/")
    app.register_blueprint(auth_routes, url_prefix="/auth")
    app.register_blueprint(dashboard_routes, url_prefix="/dashboard")
    app.register_blueprint(data_routes, url_prefix="/data")
    app.register_blueprint(privacy_routes, url_prefix="/privacy")

    if app.config["ENV"] == "development":
        CORS(app, origins="http://localhost:5000", supports_credentials=True)

    if app.config["ENV"] != "testing":
        limiter.init_app(app)

    supabase_extension.init_app(app)

    app.teardown_appcontext(teardown_db)

    @app.before_request
    def before_request():
        """Establish the database connection for the current request."""
        g.db = get_db()

    @app.errorhandler(GenericExceptionHandler)
    def handle_generic_exception(e):
        if hasattr(e, "redirect_to") and e.redirect_to:
            flash(e.message, "danger")
            return redirect(url_for(e.redirect_to))
        return json.jsonify(e.to_dict()), e.status_code

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
