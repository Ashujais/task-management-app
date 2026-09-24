import logging
import os
from datetime import timedelta

from authlib.integrations.flask_client import OAuth
from flask import Flask, jsonify, request
from flask_cors import CORS

from .database import Database
from .email_service import GmailService
from .routes import api


def create_app(test_config=None, database=None, email_service=None):
    app = Flask(__name__)
    secure_cookie = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "development-only-secret"),
        DATABASE_URL=os.getenv("DATABASE_URL", ""),
        FRONTEND_URL=os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
        GOOGLE_CLIENT_ID=os.getenv("GOOGLE_CLIENT_ID", ""),
        GOOGLE_CLIENT_SECRET=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        GOOGLE_REDIRECT_URI=os.getenv("GOOGLE_REDIRECT_URI", ""),
        GMAIL_SENDER=os.getenv("GMAIL_SENDER", ""),
        GMAIL_REFRESH_TOKEN=os.getenv("GMAIL_REFRESH_TOKEN", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=secure_cookie,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        MAX_CONTENT_LENGTH=32 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    if app.config["SESSION_COOKIE_SECURE"] and app.config["SECRET_KEY"] == "development-only-secret":
        raise RuntimeError("SECRET_KEY must be configured in production")

    logging.basicConfig(level=logging.INFO)
    allowed_origin = app.config["FRONTEND_URL"]
    CORS(app, origins=[allowed_origin], supports_credentials=True)

    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    app.extensions["database"] = database or Database(app.config["DATABASE_URL"])
    app.extensions["email_service"] = email_service or GmailService(
        client_id=app.config["GOOGLE_CLIENT_ID"],
        client_secret=app.config["GOOGLE_CLIENT_SECRET"],
        refresh_token=app.config["GMAIL_REFRESH_TOKEN"],
        sender=app.config["GMAIL_SENDER"],
    )
    app.extensions["google_oauth"] = oauth.google

    @app.before_request
    def protect_mutations_from_cross_site_requests():
        if request.method not in {"POST", "PATCH", "PUT", "DELETE"}:
            return None
        if request.path.startswith("/api/auth/"):
            return None
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != allowed_origin:
            return jsonify({"error": "Request origin is not allowed"}), 403
        if request.mimetype != "application/json":
            return jsonify({"error": "Content-Type must be application/json"}), 415
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.register_blueprint(api)

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "Request body is too large"}), 413

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({"error": "An unexpected server error occurred"}), 500

    return app
