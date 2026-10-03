from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
import sys

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()

LANGUAGES = {
    "en": "English",
    "ar": "العربية",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "ur": "اردو",
    "hi": "हिन्दी",
    "tr": "Türkçe",
}


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///shop.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.route("/set-language/<code>")
    def set_language(code):
        if code in LANGUAGES:
            session["lang"] = code
        return request.referrer or "/"

    @app.context_processor
    def inject_globals():
        return {
            "languages": LANGUAGES,
            "current_lang": session.get("lang", "en"),
        }

    if _is_server_run():
        with app.app_context():
            db.create_all()
            _seed_products()

    return app


def _is_server_run():
    argv = sys.argv
    if "db" in argv:
        return False
    if "shell" in argv:
        return False
    if argv and argv[0].endswith("run.py"):
        return True
    if argv and argv[0].endswith("flask") and "run" in argv:
        return True
    return False


def _seed_products():
    from app.models import Product
    from app.seed_data import PRODUCTS
    if Product.query.count() > 0:
        return
    import re
    def slugify(s):
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    for p in PRODUCTS:
        Product(
            name=p["name"],
            slug=slugify(p["name"]),
            category=p["category"],
            subcategory=p.get("subcategory"),
            origin_country=p.get("origin_country"),
            origin_region=p.get("origin_region"),
            description=p["description"],
            short_desc=p.get("short_desc"),
            price=p["price"],
            weight_grams=p.get("weight_grams", 100),
            image=p["image"],
            featured=p.get("featured", False),
        )
    db.session.commit()
    print(f"✅ Seeded {len(PRODUCTS)} products")
