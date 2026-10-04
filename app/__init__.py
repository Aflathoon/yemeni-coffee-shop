from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from flask_babel import Babel, gettext as _gettext, ngettext as _ngettext, lazy_gettext as _lazy
from dotenv import load_dotenv
import os
import sys
import re
from pathlib import Path

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
babel = Babel()

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
    babel.init_app(app, locale_selector=get_locale)

    # ---------- Jinja filters ----------

    @app.template_filter("imgurl")
    def imgurl_filter(value):
        """Resolve an image field to a usable URL, preferring WebP if present."""
        if not value:
            return "/static/images/placeholder.jpg"
        v = str(value)
        if v.startswith("http"):
            return v

        # Bare filename → /static/images/<v>
        if not v.startswith("/") and not v.startswith("static/"):
            fs = Path(app.static_folder) / "images" / v
            webp = fs.with_suffix(".webp")
            if webp.exists():
                return f"/static/images/{webp.name}"
            return f"/static/images/{v}"

        # /static/... path
        if v.startswith("/static/"):
            fs = Path(app.static_folder).parent / v.lstrip("/")
        else:
            fs = Path(app.static_folder).parent / v
        webp = fs.with_suffix(".webp")
        if webp.exists():
            stem = v.rsplit(".", 1)[0]
            return f"{stem}.webp"
        return v

    @app.template_filter("unit_label")
    def unit_label_filter(product):
        """Human label like '250 g', '1 kg', 'set of 4'."""
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
        return f"{qty or 1} g"

    @app.template_filter("retail_price")
    def retail_price_filter(product):
        """Retail price dict after campaigns (safe for anonymous visitors)."""
        from app.pricing import retail_price_for
        return retail_price_for(product)

    @app.template_filter("active_campaigns_for")
    def active_campaigns_for_filter(product, account=None):
        """Return active campaigns that apply to a given product for the current partner."""
        from flask import session
        from app.models import WholesaleAccount
        from app.campaigns import campaigns_for

        # Only wholesale partners for now
        ws_id = session.get("ws_id")
        acct = None
        if ws_id:
            acct = WholesaleAccount.query.get(ws_id)
        if not acct:
            return []
        return campaigns_for(acct, product)

    @app.template_filter("ws_price")
    def ws_price_filter(product):
        """Effective wholesale price dict for the current partner + product."""
        from app.pricing import wholesale_price_for
        from app.wholesale.session import current_wholesale
        return wholesale_price_for(current_wholesale(), product)

    @app.template_filter("price_for")
    def price_for_filter(product):
        """Effective price for the current user (wholesale-aware)."""
        from app.pricing import price_for as _pf
        return _pf(current_user, product)

    # ---------- Blueprints ----------

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.blog import bp as blog_bp
    app.register_blueprint(blog_bp)

    from app.wholesale import bp as wholesale_bp
    app.register_blueprint(wholesale_bp)

    # ---------- i18n helpers exposed to templates ----------
    # `_()` is the standard gettext function; `_l()` lazy-evaluates for module-level strings.
    app.jinja_env.globals["_"] = _gettext
    app.jinja_env.globals["_l"] = _lazy
    app.jinja_env.globals["ngettext"] = _ngettext

    # Expose wholesale session helpers to templates
    from app.wholesale.session import current_wholesale as _current_wholesale
    @app.context_processor
    def inject_wholesale():
        return {
            "current_wholesale": _current_wholesale(),
            "is_wholesale_logged_in": _current_wholesale() is not None,
        }

    # ---------- Language selection ----------

    @app.route("/set-language/<code>")
    def set_language(code):
        from flask import redirect
        if code in LANGUAGES:
            session["lang"] = code

        # Prefer explicit ?next=, then referrer, then home
        target = request.args.get("next", "").strip()
        if not target or not target.startswith("/"):
            ref = request.referrer or ""
            # Only accept same-origin referrers
            if ref:
                from urllib.parse import urlparse
                try:
                    parsed = urlparse(ref)
                    if parsed.hostname in (request.host.split(":")[0], "localhost", "127.0.0.1"):
                        target = parsed.path + ("?" + parsed.query if parsed.query else "")
                except Exception:
                    pass
            if not target:
                target = "/"

        return redirect(target)

    @app.context_processor
    def inject_globals():
        try:
            from app.main.routes import cart_count
            count = cart_count()
        except Exception:
            count = 0

        wd = 0.0
        wu = False
        try:
            from app.pricing import discount_for, is_wholesale_user
            if current_user.is_authenticated:
                wd = discount_for(current_user)
                wu = is_wholesale_user(current_user)
        except Exception:
            pass

        # Active retail campaigns (for banner)
        active_retail = []
        try:
            from app.campaigns import active_retail_campaigns
            active_retail = active_retail_campaigns()
        except Exception:
            pass

        return {
            "languages": LANGUAGES,
            "current_lang": session.get("lang", "en"),
            "cart_count": count,
            "wholesale_discount": wd,
            "is_wholesale": wu,
            "active_retail_campaigns": active_retail,
        }

    # ---------- Seed only when running the server ----------
    if _is_server_run():
        with app.app_context():
            db.create_all()
            _seed_products()

    return app


def get_locale():
    """
    Return the user's preferred locale from the session.
    Falls back to the best match from the Accept-Language header,
    then to English.
    """
    from flask import session, request
    # 1. explicit user choice
    lang = session.get("lang")
    if lang and lang in LANGUAGES:
        return lang
    # 2. browser's Accept-Language
    best = request.accept_languages.best_match(list(LANGUAGES.keys()))
    if best:
        return best
    # 3. fallback
    return "en"


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
            unit=p.get("unit", "g"),
            unit_quantity=p.get("unit_quantity", 1),
            image=p["image"],
            featured=p.get("featured", False),
        )
        db.session.add(product)
        inserted += 1
    db.session.commit()
    print(f"✅ Seeded {inserted} products")
