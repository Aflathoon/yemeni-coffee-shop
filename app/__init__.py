from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
import sys
from pathlib import Path
import re

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

    # --- Jinja filters ---
    @app.template_filter("unit_label")
    def unit_label_filter(product):
        """Return a human label like '250 g', '1 kg', 'set of 4'."""
        unit = getattr(product, "unit", None) or "g"
        qty = getattr(product, "unit_quantity", None)
        if unit == "ea":
            return f"{qty}x" if qty and qty > 1 else "each"
        if unit == "set":
            return f"set of {qty}" if qty and qty > 1 else "set"
        if unit == "bag":
            return f"{qty} bag" if qty else "bag"
        if unit == "kg":
            return f"{qty or 1} kg"
        # default grams
        return f"{qty or 1} g"

    @app.template_filter("imgurl")
    def imgurl_filter(value):
        """Return a usable URL for an image field, preferring WebP if it exists.
        - bare filename → /static/images/<name>
        - /static/... paths pass through but swap .jpg/.jpeg/.png → .webp if a .webp exists
        - http(s) URLs pass through unchanged
        - empty → /static/images/placeholder.jpg
        """
        if not value:
            return "/static/images/placeholder.jpg"
        v = str(value)

        # Resolve to a filesystem path for existence checks
        def to_fs(url):
            if url.startswith("/static/"):
                return Path(app.static_folder).parent / url.lstrip("/")
            if url.startswith("static/"):
                return Path(app.static_folder).parent / url
            return Path(app.static_folder) / "images" / url

        from pathlib import Path as _P

        if v.startswith("http"):
            return v

        # Bare filename → /static/images/<v>
        if not v.startswith("/") and not v.startswith("static/"):
            fs = Path(app.static_folder) / "images" / v
            stem = fs.with_suffix("")
            webp = stem.with_suffix(".webp")
            if webp.exists():
                return f"/static/images/{webp.name}"
            return f"/static/images/{v}"

        # /static/... path — check for WebP twin
        fs = to_fs(v)
        stem = fs.with_suffix("")
        webp = stem.with_suffix(".webp")
        if webp.exists():
            url_stem = v.rsplit(".", 1)[0]
            return f"{url_stem}.webp"
        return v

    # --- Blueprints ---
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.blog import bp as blog_bp
    app.register_blueprint(blog_bp)

    # --- Language selection ---
    @app.route("/set-language/<code>")
    def set_language(code):
        if code in LANGUAGES:
            session["lang"] = code
        return request.referrer or "/"

    
    @app.context_processor
    def inject_globals():
        try:
            from app.main.routes import cart_count
            count = cart_count()
        except Exception:
            count = 0
        return {
            "languages": LANGUAGES,
            "current_lang": session.get("lang", "en"),
            "cart_count": count,
        }
    # --- Seed only when the server actually starts ---
    if _is_server_run():
        with app.app_context():
            db.create_all()
            _seed_products()

    return app


def _is_server_run():
    """True only for `python run.py` or `flask run` — skip on `flask db ...`."""
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

    def slugify(s):
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    inserted = 0
    for p in PRODUCTS:
        product = Product(
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
        db.session.add(product)   # <-- THIS was missing
        inserted += 1

    db.session.commit()
    print(f"✅ Seeded {inserted} products")
