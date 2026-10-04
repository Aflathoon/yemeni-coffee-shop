from datetime import datetime, timedelta
from functools import wraps

from flask import (
    render_template, request, redirect, url_for, flash, current_app
)
from flask_login import current_user, login_user, logout_user
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app.admin import bp
from app import db
from app.models import Product, User, Order, OrderItem, Post, WholesaleAccount


ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


# ---------- Login / logout ----------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.is_admin:
            login_user(user)
            return redirect(url_for("admin.dashboard"))
        flash("Invalid credentials or not an admin", "error")
    return render_template("admin/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("Signed out", "success")
    return redirect(url_for("admin.login"))


# ---------- Stats helper ----------

def compute_stats():
    now = datetime.utcnow()
    since_7 = now - timedelta(days=7)
    since_14 = now - timedelta(days=14)
    since_30 = now - timedelta(days=30)
    prev_30 = now - timedelta(days=60)

    orders = Order.query.all()

    revenue_total = sum(o.total for o in orders)
    revenue_30 = sum(o.total for o in orders if o.created_at >= since_30)
    revenue_prev_30 = sum(o.total for o in orders if prev_30 <= o.created_at < since_30)
    revenue_7 = sum(o.total for o in orders if o.created_at >= since_7)
    revenue_prev_7 = sum(o.total for o in orders if since_14 <= o.created_at < since_7)

    orders_30 = [o for o in orders if o.created_at >= since_30]
    orders_prev_30 = [o for o in orders if prev_30 <= o.created_at < since_30]

    by_status = {"pending": 0, "paid": 0, "shipped": 0, "delivered": 0, "cancelled": 0}
    for o in orders:
        by_status[o.status] = by_status.get(o.status, 0) + 1

    def pct_delta(new, old):
        if old == 0:
            return None if new == 0 else 100.0
        return round((new - old) / old * 100.0, 1)

    daily = {}
    for i in range(14, -1, -1):
        d = (now - timedelta(days=i)).date()
        daily[d.isoformat()] = 0.0
    for o in orders:
        d = o.created_at.date().isoformat()
        if d in daily:
            daily[d] += o.total

    top = (
        db.session.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("qty"),
            func.sum(OrderItem.line_total).label("rev"),
        )
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.line_total).desc())
        .limit(5).all()
    )

    recent = Order.query.order_by(Order.created_at.desc()).limit(6).all()

    # Wholesale counts (graceful if model missing)
    new_ws = 0
    approved_ws = 0
    try:
        from app.models import WholesaleAccount
        new_ws = WholesaleAccount.query.filter_by(status="pending").count()
        approved_ws = WholesaleAccount.query.filter_by(status="approved").count()
    except Exception:
        pass

    # Campaign counts
    live_campaigns = 0
    scheduled_campaigns = 0
    try:
        from app.models import Campaign
        all_c = Campaign.query.filter_by(published=True).all()
        live_campaigns = sum(1 for c in all_c if c.is_live())
        scheduled_campaigns = sum(1 for c in all_c if c.is_upcoming())
    except Exception:
        pass

    # Wholesale at-risk counts
    partners_at_risk = 0
    try:
        from app.models import WholesaleAccount
        partners_at_risk = (WholesaleAccount.query
                            .filter_by(status="approved")
                            .filter(WholesaleAccount.tier_state.in_(["warn", "grace", "downgrade", "terminate"]))
                            .count())
    except Exception:
        pass

    # Open AI alerts
    open_alerts = 0
    try:
        from app.models import AiAlert
        open_alerts = AiAlert.query.filter_by(resolved=False).filter(
            AiAlert.status.in_(("warn", "fail"))).count()
    except Exception:
        pass

    return {
        "products": Product.query.count(),
        "orders": len(orders),
        "users": User.query.count(),
        "posts": Post.query.count(),
        "new_wholesale_accounts": new_ws,
        "approved_wholesale_accounts": approved_ws,
        "live_campaigns": live_campaigns,
        "scheduled_campaigns": scheduled_campaigns,
        "partners_at_risk": partners_at_risk,
        "open_alerts": open_alerts,
        "revenue": revenue_total,
        "revenue_30": revenue_30,
        "revenue_30_delta": pct_delta(revenue_30, revenue_prev_30),
        "revenue_7": revenue_7,
        "revenue_7_delta": pct_delta(revenue_7, revenue_prev_7),
        "orders_30": len(orders_30),
        "orders_30_delta": pct_delta(len(orders_30), len(orders_prev_30)),
        "orders_7": sum(1 for o in orders if o.created_at >= since_7),
        "by_status": by_status,
        "new_orders": by_status["pending"],
        "daily_labels": list(daily.keys()),
        "daily_values": list(daily.values()),
        "top_products": [
            {"name": n, "qty": int(q or 0), "revenue": float(r or 0)}
            for n, q, r in top
        ],
        "recent_orders": recent,
    }


# ---------- Overview ----------

@bp.route("/dashboard")
@admin_required
def dashboard():
    stats = compute_stats()

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(6).all()

    # Simple task list
    tasks = []
    if stats["new_orders"]:
        tasks.append({"icon": "🛒", "text": f"{stats['new_orders']} new order(s) awaiting fulfilment",
                      "link": url_for("admin.orders"), "cta": "Review"})
    if stats["posts"] == 0:
        tasks.append({"icon": "📝", "text": "No marketing posts yet — write your first one",
                      "link": url_for("admin.new_post"), "cta": "Create"})
    if stats["products"] < 45:
        tasks.append({"icon": "📦", "text": "Add more products to reach 45 SKUs",
                      "link": url_for("admin.products"), "cta": "Products"})
    tasks.append({"icon": "🔗", "text": "Connect Telegram for social posts",
                  "link": url_for("admin.social"), "cta": "Connect"})

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recent_orders=recent_orders,
        tasks=tasks,
    )


# ---------- Orders ----------

@bp.route("/orders")
@admin_required
def orders():
    status_filter = request.args.get("status")
    channel = request.args.get("channel")
    search = request.args.get("q", "").strip()
    q = Order.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    if channel == "wholesale":
        q = q.filter(Order.wholesale_id.isnot(None))
    elif channel == "retail":
        q = q.filter(Order.wholesale_id.is_(None))
    if search:
        # numeric → order id
        like = f"%{search}%"
        conds = [Order.full_name.ilike(like), Order.email.ilike(like),
                 Order.tracking_number.ilike(like), Order.po_number.ilike(like)]
        if search.isdigit():
            conds.append(Order.id == int(search))
        from sqlalchemy import or_
        q = q.filter(or_(*conds))
    all_orders = q.order_by(Order.created_at.desc()).all()
    stats = compute_stats()
    return render_template("admin/orders.html",
                           orders=all_orders, stats=stats,
                           status_filter=status_filter, channel=channel, search=search)


@bp.route("/orders/<int:order_id>")
@admin_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    stats = compute_stats()
    return render_template("admin/order_detail.html", order=order, stats=stats)


@bp.route("/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def order_set_status(order_id):
    """Transition order status with validation + audit log."""
    from app.orders import change_order_status
    order = Order.query.get_or_404(order_id)
    new_status = (request.form.get("status") or "").strip().lower()

    tracking_number = request.form.get("tracking_number", "").strip() or None
    courier = request.form.get("courier", "").strip() or None
    note = request.form.get("note", "").strip() or None
    cancellation_reason = request.form.get("cancellation_reason", "").strip() or None

    ok, err = change_order_status(
        order, new_status,
        actor_email=current_user.email if current_user and current_user.is_authenticated else None,
        actor_role="admin",
        note=note,
        tracking_number=tracking_number,
        courier=courier,
        cancellation_reason=cancellation_reason,
    )
    if not ok:
        flash(err or "Could not update status.", "error")
    else:
        flash(f"Order #{order.id} → {new_status}", "success")

    return redirect(url_for("admin.order_detail", order_id=order.id))


# ---------- Products ----------

@bp.route("/products")
@admin_required
def products():
    from sqlalchemy import func

    # Filters from query string
    category = request.args.get("category", "").strip()
    country = request.args.get("country", "").strip()
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()  # active | inactive | featured | low_stock
    sort = request.args.get("sort", "name")          # name | price_asc | price_desc | stock | newest

    q = Product.query

    if category:
        q = q.filter_by(category=category)
    if country:
        q = q.filter_by(origin_country=country)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (Product.name.ilike(like))
            | (Product.description.ilike(like))
            | (Product.tags.ilike(like))
            | (Product.origin_region.ilike(like))
        )
    if status == "active":
        q = q.filter_by(active=True)
    elif status == "inactive":
        q = q.filter_by(active=False)
    elif status == "featured":
        q = q.filter_by(featured=True)
    elif status == "low_stock":
        q = q.filter(Product.stock <= Product.stock_alert_threshold)

    # Sorting
    if sort == "price_asc":
        q = q.order_by(Product.price.asc())
    elif sort == "price_desc":
        q = q.order_by(Product.price.desc())
    elif sort == "stock":
        q = q.order_by(Product.stock.asc())
    elif sort == "newest":
        q = q.order_by(Product.created_at.desc())
    else:
        q = q.order_by(Product.category.asc(), Product.name.asc())

    all_products = q.all()

    # Category counts (unfiltered by category, but respecting other filters)
    cat_q = db.session.query(Product.category, func.count(Product.id))
    if country:
        cat_q = cat_q.filter_by(origin_country=country)
    if search:
        like = f"%{search}%"
        cat_q = cat_q.filter(
            (Product.name.ilike(like))
            | (Product.description.ilike(like))
            | (Product.tags.ilike(like))
        )
    category_counts = dict(cat_q.group_by(Product.category).all())

    # Country counts
    country_q = db.session.query(Product.origin_country, func.count(Product.id))
    if category:
        country_q = country_q.filter_by(category=category)
    if search:
        like = f"%{search}%"
        country_q = country_q.filter(
            (Product.name.ilike(like)) | (Product.description.ilike(like))
        )
    country_counts = dict(
        country_q.filter(Product.origin_country.isnot(None))
                 .group_by(Product.origin_country)
                 .order_by(Product.origin_country).all()
    )

    stats = compute_stats()
    return render_template("admin/products.html",
                           products=all_products,
                           stats=stats,
                           category_counts=category_counts,
                           country_counts=country_counts,
                           active_category=category,
                           active_country=country,
                           active_status=status,
                           active_sort=sort,
                           search=search)


@bp.route("/products/<int:product_id>/toggle-featured", methods=["POST"])
@admin_required
def product_toggle_featured(product_id):
    p = Product.query.get_or_404(product_id)
    p.featured = not p.featured
    db.session.commit()
    flash(f"{p.name} featured = {p.featured}", "success")
    return redirect(url_for("admin.products"))


# ---------- Products (full CRUD) ----------

def _slugify(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _unique_slug(base, exclude_id=None):
    from app.models import Product as _P
    slug = base
    n = 1
    while True:
        q = _P.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(_P.id != exclude_id)
        if not q.first():
            return slug
        n += 1
        slug = f"{base}-{n}"


@bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_new():
    stats = compute_stats()
    if request.method == "POST":
        product, err = _product_from_form(None)
        if err:
            flash(err, "error")
            return render_template("admin/product_edit.html",
                                   product=None, stats=stats, form=request.form)
        db.session.add(product)
        db.session.commit()
        flash(f"Product '{product.name}' created", "success")
        return redirect(url_for("admin.products"))
    return render_template("admin/product_edit.html", product=None, stats=stats, form={})


@bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    from app.models import Product as _P
    product = _P.query.get_or_404(product_id)
    stats = compute_stats()
    if request.method == "POST":
        _, err = _product_from_form(product)
        if err:
            flash(err, "error")
            return render_template("admin/product_edit.html",
                                   product=product, stats=stats, form=request.form)
        db.session.commit()
        flash(f"Product '{product.name}' updated", "success")
        return redirect(url_for("admin.products"))
    return render_template("admin/product_edit.html", product=product, stats=stats, form=None)


@bp.route("/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def product_delete(product_id):
    from app.models import Product as _P
    product = _P.query.get_or_404(product_id)
    name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f"Deleted '{name}'", "success")
    return redirect(url_for("admin.products"))


@bp.route("/products/<int:product_id>/duplicate", methods=["POST"])
@admin_required
def product_duplicate(product_id):
    from app.models import Product as _P
    src = _P.query.get_or_404(product_id)
    copy = _P(
        name=src.name + " (copy)",
        slug=_unique_slug(_slugify(src.name + " copy")),
        category=src.category, subcategory=src.subcategory,
        origin_country=src.origin_country, origin_region=src.origin_region,
        description=src.description, long_description=src.long_description,
        short_desc=src.short_desc,
        price=src.price, compare_at_price=src.compare_at_price,
        weight_grams=src.weight_grams, image=src.image, gallery=src.gallery,
        stock=src.stock, stock_alert_threshold=src.stock_alert_threshold,
        tags=src.tags, meta_title=src.meta_title, meta_description=src.meta_description,
        active=src.active, featured=False,
    )
    db.session.add(copy)
    db.session.commit()
    flash(f"Duplicated as '{copy.name}'", "success")
    return redirect(url_for("admin.product_edit", product_id=copy.id))


def _product_from_form(product):
    """Populate or create Product from form. Returns (product, error)."""
    from app.models import Product as _P
    name = request.form.get("name", "").strip()
    if not name:
        return None, "Name is required"

    category = request.form.get("category", "").strip()
    if not category:
        return None, "Category is required"

    try:
        price = float(request.form.get("price", "0"))
    except ValueError:
        return None, "Price must be a number"
    if price < 0:
        return None, "Price must be positive"

    compare_at = request.form.get("compare_at_price", "").strip()
    try:
        compare_at = float(compare_at) if compare_at else None
    except ValueError:
        compare_at = None

    try:
        weight = int(request.form.get("weight_grams", "100") or 100)
    except ValueError:
        weight = 100

    try:
        stock = int(request.form.get("stock", "0") or 0)
    except ValueError:
        stock = 0

    try:
        alert = int(request.form.get("stock_alert_threshold", "5") or 5)
    except ValueError:
        alert = 5

    slug_input = request.form.get("slug", "").strip()
    if not slug_input:
        slug_input = _slugify(name)

    is_new = product is None
    if is_new:
        product = _P()

    existing_id = None if is_new else product.id
    product.slug = _unique_slug(slug_input, exclude_id=existing_id)

    product.name = name
    product.category = category
    product.subcategory = request.form.get("subcategory", "").strip() or None
    product.origin_country = request.form.get("origin_country", "").strip() or None
    product.origin_region = request.form.get("origin_region", "").strip() or None
    product.short_desc = request.form.get("short_desc", "").strip() or None
    product.description = request.form.get("description", "").strip() or ""
    product.long_description = request.form.get("long_description", "").strip() or None
    product.price = price
    product.compare_at_price = compare_at

    # Cost price + margin floor
    cost_raw = request.form.get("cost_price", "").strip()
    if cost_raw:
        try:
            product.cost_price = max(0.0, float(cost_raw))
        except ValueError:
            product.cost_price = None
    else:
        product.cost_price = None

    floor_raw = request.form.get("margin_floor_pct", "").strip()
    if floor_raw:
        try:
            product.margin_floor_pct = max(0.0, min(90.0, float(floor_raw)))
        except ValueError:
            product.margin_floor_pct = 15.0
    else:
        product.margin_floor_pct = 15.0

    product.weight_grams = weight
    product.unit = request.form.get("unit", "g").strip() or "g"
    try:
        product.unit_quantity = int(request.form.get("unit_quantity", "1") or 1)
    except ValueError:
        product.unit_quantity = 1
    product.allow_custom_weight = request.form.get("allow_custom_weight") == "1"
    product.stock = stock
    product.stock_alert_threshold = alert
    product.image = request.form.get("image", "").strip() or "placeholder.jpg"
    product.gallery = request.form.get("gallery", "").strip() or None
    product.tags = request.form.get("tags", "").strip() or None
    product.meta_title = request.form.get("meta_title", "").strip() or None
    product.meta_description = request.form.get("meta_description", "").strip() or None
    product.active = request.form.get("active") == "1"
    product.featured = request.form.get("featured") == "1"

    return product, None


# ---------- Customers ----------

@bp.route("/customers")
@admin_required
def customers():
    users = User.query.order_by(User.created_at.desc()).all()
    # Order counts per user
    counts = dict(
        db.session.query(Order.user_id, func.count(Order.id))
        .filter(Order.user_id.isnot(None))
        .group_by(Order.user_id).all()
    )
    stats = compute_stats()
    return render_template("admin/customers.html", users=users, order_counts=counts, stats=stats)


# ---------- Posts ----------

@bp.route("/posts")
@admin_required
def posts():
    all_posts = Post.query.order_by(Post.created_at.desc()).all()
    stats = compute_stats()
    return render_template("admin/posts.html", posts=all_posts, stats=stats)


@bp.route("/post/new", methods=["GET", "POST"])
@admin_required
def new_post():
    if request.method == "POST":
        post = Post(
            title=request.form.get("title", "").strip(),
            body=request.form.get("body", "").strip(),
            image=request.form.get("image", "").strip(),
        )
        db.session.add(post)
        db.session.commit()
        flash("Post created", "success")
        return redirect(url_for("admin.posts"))
    stats = compute_stats()
    return render_template("admin/editor.html", stats=stats, post=None)


@bp.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if request.method == "POST":
        post.title = request.form.get("title", "").strip()
        post.body = request.form.get("body", "").strip()
        post.image = request.form.get("image", "").strip()
        db.session.commit()
        flash("Post updated", "success")
        return redirect(url_for("admin.posts"))
    stats = compute_stats()
    return render_template("admin/editor.html", stats=stats, post=post)


@bp.route("/post/<int:post_id>/publish", methods=["POST"])
@admin_required
def publish_post(post_id):
    post = Post.query.get_or_404(post_id)
    post.published = True
    db.session.commit()
    flash(f"'{post.title}' marked published", "success")
    return redirect(url_for("admin.posts"))


# ---------- Social / Settings ----------

@bp.route("/social")
@admin_required
def social():
    stats = compute_stats()
    return render_template("admin/social.html", stats=stats)


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    from app.models import Setting

    if request.method == "POST":
        fields = [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHANNEL_ID",
            "STORE_NAME",
            "STORE_EMAIL",
            "FREE_SHIPPING_THRESHOLD",
            "SHIPPING_FLAT_RATE",
            "WHOLESALE_DISCOUNT_STANDARD",
            "WHOLESALE_DISCOUNT_BRONZE",
            "WHOLESALE_DISCOUNT_SILVER",
            "WHOLESALE_DISCOUNT_GOLD",
            "WHOLESALE_MOQ_DEFAULT",
            "WHOLESALE_MOQ_ENFORCE",
            "MARGIN_FLOOR_ENFORCE",
            "MARGIN_FLOOR_PCT_DEFAULT",
            "TIER_BRONZE_AMOUNT",
            "TIER_SILVER_AMOUNT",
            "TIER_GOLD_AMOUNT",
            "SMTP_ENABLED",
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_USER",
            "SMTP_PASSWORD",
            "SMTP_USE_TLS",
            "MAIL_FROM",
            "AI_ENABLED",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_MODEL_CHAT",
            "DEEPSEEK_MODEL_REASON",
            "AI_TEMPERATURE",
            "AI_WATCHER_ENABLED",
            "AI_WATCHER_INTERVAL_MIN",
        ]
        for f in fields:
            if f in request.form:
                Setting.set(f, request.form.get(f, "").strip())
        flash("Settings saved", "success")
        return redirect(url_for("admin.settings"))

    settings_map = Setting.get_all()
    stats = compute_stats()
    return render_template("admin/settings.html", stats=stats, settings_map=settings_map)


# ---------- Uploads ----------

import os, uuid


@bp.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    if request.method == "POST":
        files = request.files.getlist("files")
        kind = request.form.get("kind", "products")
        if kind not in ("products", "posts", "originals"):
            kind = "products"

        folder = os.path.join(current_app.static_folder, "uploads", kind)
        os.makedirs(folder, exist_ok=True)

        saved, skipped = 0, 0
        for file in files:
            if not file or not file.filename or not _allowed_file(file.filename):
                skipped += 1
                continue
            ext = file.filename.rsplit(".", 1)[1].lower()
            stem = secure_filename(file.filename.rsplit(".", 1)[0])[:40] or "upload"
            fname = f"{stem}-{uuid.uuid4().hex[:8]}.{ext}"
            file.save(os.path.join(folder, fname))
            saved += 1

        flash(f"Uploaded {saved}, skipped {skipped}", "success")
        return redirect(url_for("admin.upload", kind=kind))

    kind = request.args.get("kind", "products")
    if kind not in ("products", "posts", "originals"):
        kind = "products"
    q = request.args.get("q", "").strip().lower()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 60

    folder = os.path.join(current_app.static_folder, "uploads", kind)
    files = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder), reverse=True):
            if not _allowed_file(f):
                continue
            if q and q not in f.lower():
                continue
            files.append(f"/static/uploads/{kind}/{f}")

    total = len(files)
    start = (page - 1) * per_page
    page_files = files[start:start + per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)

    stats = compute_stats()
    return render_template("admin/upload.html",
                           gallery=page_files, kind=kind, q=q, page=page,
                           total=total, total_pages=total_pages, stats=stats)


@bp.route("/upload/delete", methods=["POST"])
@admin_required
def upload_delete():
    url = request.form.get("url", "")
    kind = request.form.get("kind", "products")
    if kind not in ("products", "posts", "originals"):
        flash("Bad kind", "error")
        return redirect(url_for("admin.upload"))
    prefix = f"/static/uploads/{kind}/"
    if not url.startswith(prefix):
        flash("Refusing: path outside the allowed folder", "error")
        return redirect(url_for("admin.upload", kind=kind))
    fname = os.path.basename(url)
    full = os.path.join(current_app.static_folder, "uploads", kind, fname)
    if os.path.isfile(full):
        os.remove(full)
        flash(f"Deleted {fname}", "success")
    else:
        flash("File not found", "error")
    return redirect(url_for("admin.upload", kind=kind))


# ---------- Uploads API (for picker) ----------

@bp.route("/api/uploads")
@admin_required
def api_uploads():
    """Return list of upload URLs for the image picker."""
    kind = request.args.get("kind", "products")
    if kind not in ("products", "posts", "originals"):
        kind = "products"
    folder = os.path.join(current_app.static_folder, "uploads", kind)
    items = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder), reverse=True):
            if _allowed_file(f):
                items.append({"url": f"/static/uploads/{kind}/{f}", "name": f})
    return {"items": items, "kind": kind}


# ---------- Import from uploads ----------

def _name_from_filename(filename):
    """darjeeling-first-flush-abc123.jpg → 'Darjeeling First Flush'."""
    import re
    stem = filename.rsplit(".", 1)[0]
    # Strip the trailing hash we add on upload (-a1b2c3d4e5f6)
    stem = re.sub(r"-[a-f0-9]{6,16}$", "", stem)
    # Replace separators with spaces
    stem = re.sub(r"[-_]+", " ", stem)
    # Collapse whitespace, title case
    stem = " ".join(w.capitalize() for w in stem.split())
    return stem.strip() or "Untitled"


def _guess_category(name):
    n = name.lower()
    if any(k in n for k in ["coffee", "mokha", "arabica", "espresso", "roast"]):
        return "coffee"
    if any(k in n for k in ["honey", "honeycomb", "sidr"]):
        return "honey"
    if any(k in n for k in ["tea", "rooibos", "darjeeling", "assam", "ceylon"]):
        return "tea"
    if any(k in n for k in ["mint", "lavender", "oregano", "thyme", "rosemary", "herb"]):
        return "herbs"
    return "spices"


def _scan_uploads_for_import():
    """Return list of dicts describing importable images."""
    from app.models import Product as _P
    from app.models import Setting as _S
    folder = os.path.join(current_app.static_folder, "uploads", "products")
    if not os.path.isdir(folder):
        return []

    # Names already used as image in DB — skip those
    existing_images = {p.image for p in _P.query.all() if p.image}

    items = []
    for f in sorted(os.listdir(folder)):
        if not _allowed_file(f):
            continue
        url = f"/static/uploads/products/{f}"
        name = _name_from_filename(f)
        already = url in existing_images
        items.append({
            "filename": f,
            "url": url,
            "suggested_name": name,
            "suggested_slug": _slugify(name),
            "suggested_category": _guess_category(name),
            "already_imported": already,
        })
    return items


@bp.route("/import/uploads")
@admin_required
def import_uploads():
    stats = compute_stats()
    items = _scan_uploads_for_import()
    new_count = sum(1 for i in items if not i["already_imported"])
    return render_template("admin/import_uploads.html", stats=stats, items=items, new_count=new_count)


@bp.route("/import/uploads/create", methods=["POST"])
@admin_required
def import_create_one():
    """Create a single product from the selected upload."""
    from app.models import Product as _P

    filename = request.form.get("filename", "").strip()
    if not filename or "/" in filename or ".." in filename:
        return {"ok": False, "error": "invalid filename"}, 400

    full = os.path.join(current_app.static_folder, "uploads", "products", filename)
    if not os.path.isfile(full):
        return {"ok": False, "error": "file not found"}, 404

    name = request.form.get("name", "").strip() or _name_from_filename(filename)
    category = request.form.get("category", "").strip() or _guess_category(name)
    try:
        price = float(request.form.get("price", "0") or 0)
    except ValueError:
        price = 0.0

    url = f"/static/uploads/products/{filename}"

    # Check duplicate image
    if _P.query.filter_by(image=url).first():
        return {"ok": False, "error": "already imported"}, 409

    product = _P(
        name=name,
        slug=_unique_slug(_slugify(name)),
        category=category,
        description=request.form.get("description", "").strip() or f"A new addition to our {category} collection.",
        short_desc=request.form.get("short_desc", "").strip() or f"New {category} — see full details.",
        price=price,
        weight_grams=100,
        image=url,
        stock=100,
        active=True,
        featured=False,
    )
    db.session.add(product)
    db.session.commit()

    return {
        "ok": True,
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "edit_url": url_for("admin.product_edit", product_id=product.id),
    }


@bp.route("/import/uploads/create-all", methods=["POST"])
@admin_required
def import_create_all():
    """Bulk-create products for every non-imported upload."""
    from app.models import Product as _P

    items = [i for i in _scan_uploads_for_import() if not i["already_imported"]]
    created = 0
    skipped = 0
    for i in items:
        if _P.query.filter_by(image=i["url"]).first():
            skipped += 1
            continue
        product = _P(
            name=i["suggested_name"],
            slug=_unique_slug(i["suggested_slug"]),
            category=i["suggested_category"],
            description=f"A new addition to our {i['suggested_category']} collection.",
            short_desc=f"New {i['suggested_category']} — see full details.",
            price=0.0,
            weight_grams=100,
            image=i["url"],
            stock=100,
            active=False,   # keep inactive until price/description are filled in
            featured=False,
        )
        db.session.add(product)
        created += 1

    db.session.commit()
    flash(f"Created {created} draft product(s), skipped {skipped} existing", "success")
    return redirect(url_for("admin.import_uploads"))


# ---------- Telegram diagnostics ----------

@bp.route("/settings/test-telegram", methods=["POST"])
@admin_required
def settings_test_telegram():
    from app.telegram import test_connection
    result = test_connection()
    if result.get("ok"):
        flash(f"✅ {result.get('description', 'Test sent')}", "success")
    else:
        flash(f"❌ Telegram: {result.get('description', 'Unknown error')}", "error")
    return redirect(url_for("admin.settings"))


@bp.route("/settings/test-chat", methods=["POST"])
@admin_required
def settings_test_chat():
    from app.telegram import test_chat_id
    result = test_chat_id()
    if result.get("ok"):
        flash(f"✅ {result.get('description')}", "success")
    else:
        flash(f"❌ {result.get('description', 'Unknown error')}", "error")
    return redirect(url_for("admin.settings"))


@bp.route("/products/<int:product_id>/share-telegram", methods=["POST"])
@admin_required
def product_share_telegram(product_id):
    from app.models import Product as _P
    from app.telegram import send_product, is_configured
    if not is_configured():
        flash("Telegram not configured — set token and channel in Settings", "error")
        return redirect(url_for("admin.settings"))

    product = _P.query.get_or_404(product_id)
    base_url = request.host_url.rstrip("/")
    result = send_product(product, base_url=base_url)
    if result.get("ok"):
        flash(f"✅ '{product.name}' sent to Telegram", "success")
    else:
        flash(f"❌ Telegram: {result.get('description', 'Unknown error')}", "error")
    return redirect(url_for("admin.product_edit", product_id=product_id))


@bp.route("/post/<int:post_id>/share-telegram", methods=["POST"])
@admin_required
def post_share_telegram(post_id):
    from app.telegram import send_post, is_configured
    if not is_configured():
        flash("Telegram not configured — set token and channel in Settings", "error")
        return redirect(url_for("admin.settings"))

    post = Post.query.get_or_404(post_id)
    base_url = request.host_url.rstrip("/")
    result = send_post(post, base_url=base_url)
    if result.get("ok"):
        flash(f"✅ '{post.title}' sent to Telegram", "success")
    else:
        flash(f"❌ Telegram: {result.get('description', 'Unknown error')}", "error")
    return redirect(url_for("admin.posts"))


# ---------- Articles (blog admin) ----------

@bp.route("/articles")
@admin_required
def articles():
    from app.models import Article
    all_articles = Article.query.order_by(Article.created_at.desc()).all()
    stats = compute_stats()
    return render_template("admin/articles.html", articles=all_articles, stats=stats)


@bp.route("/articles/new", methods=["GET", "POST"])
@admin_required
def article_new():
    from app.models import Article
    stats = compute_stats()
    if request.method == "POST":
        article, err = _article_from_form(None)
        if err:
            flash(err, "error")
            return render_template("admin/article_edit.html", article=None, stats=stats, form=request.form)
        db.session.add(article)
        db.session.commit()
        flash(f"Article '{article.title}' created", "success")
        return redirect(url_for("admin.articles"))
    return render_template("admin/article_edit.html", article=None, stats=stats, form={})


@bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
@admin_required
def article_edit(article_id):
    from app.models import Article
    article = Article.query.get_or_404(article_id)
    stats = compute_stats()
    if request.method == "POST":
        _, err = _article_from_form(article)
        if err:
            flash(err, "error")
            return render_template("admin/article_edit.html", article=article, stats=stats, form=request.form)
        db.session.commit()
        flash(f"Article '{article.title}' updated", "success")
        return redirect(url_for("admin.articles"))
    return render_template("admin/article_edit.html", article=article, stats=stats, form=None)


@bp.route("/articles/<int:article_id>/delete", methods=["POST"])
@admin_required
def article_delete(article_id):
    from app.models import Article
    a = Article.query.get_or_404(article_id)
    title = a.title
    db.session.delete(a)
    db.session.commit()
    flash(f"Deleted '{title}'", "success")
    return redirect(url_for("admin.articles"))


@bp.route("/articles/<int:article_id>/toggle-publish", methods=["POST"])
@admin_required
def article_toggle_publish(article_id):
    from app.models import Article
    a = Article.query.get_or_404(article_id)
    a.published = not a.published
    db.session.commit()
    flash(f"'{a.title}' now {'published' if a.published else 'draft'}", "success")
    return redirect(url_for("admin.articles"))


def _article_from_form(article):
    from app.models import Article
    import re
    title = request.form.get("title", "").strip()
    if not title:
        return None, "Title is required"

    def slugify(s):
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    if article is None:
        article = Article()

    slug_in = request.form.get("slug", "").strip() or slugify(title)

    # Enforce unique slug
    base = slug_in
    n = 1
    while True:
        q = Article.query.filter_by(slug=slug_in)
        if article.id:
            q = q.filter(Article.id != article.id)
        if not q.first():
            break
        n += 1
        slug_in = f"{base}-{n}"

    def _int(v, default):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    article.title = title
    article.slug = slug_in
    article.excerpt = request.form.get("excerpt", "").strip() or None
    article.body = request.form.get("body", "").strip() or None
    article.hero_image = request.form.get("hero_image", "").strip() or None
    article.category = request.form.get("category", "").strip() or None
    article.tags = request.form.get("tags", "").strip() or None
    article.author_name = request.form.get("author_name", "The Spice & Roast Co.").strip()
    article.reading_minutes = _int(request.form.get("reading_minutes", "4"), 4)
    article.meta_title = request.form.get("meta_title", "").strip() or None
    article.meta_description = request.form.get("meta_description", "").strip() or None
    article.published = request.form.get("published") == "1"
    article.featured = request.form.get("featured") == "1"

    return article, None


# ---------- Wholesale applications ----------

@bp.route("/wholesale")
@admin_required
def wholesale_list():
    pending = User.query.filter_by(wholesale_status="pending").order_by(User.wholesale_applied_at.desc()).all()
    approved = User.query.filter_by(wholesale_status="approved").order_by(User.wholesale_approved_at.desc()).all()
    rejected = User.query.filter_by(wholesale_status="rejected").order_by(User.wholesale_applied_at.desc()).all()
    stats = compute_stats()
    return render_template("admin/wholesale_list.html",
                           pending=pending, approved=approved, rejected=rejected, stats=stats)


@bp.route("/wholesale/<int:user_id>/approve", methods=["POST"])
@admin_required
def wholesale_approve(user_id):
    from datetime import datetime
    user = User.query.get_or_404(user_id)
    user.wholesale_status = "approved"
    user.is_wholesale = True
    user.wholesale_approved_at = datetime.utcnow()
    tier = request.form.get("tier", "standard")
    if tier in ("standard", "bronze", "silver", "gold"):
        user.wholesale_tier = tier
    db.session.commit()
    flash(f"{user.email} approved as wholesale — tier: {user.wholesale_tier}", "success")
    return redirect(url_for("admin.wholesale_list"))


@bp.route("/wholesale/<int:user_id>/reject", methods=["POST"])
@admin_required
def wholesale_reject(user_id):
    user = User.query.get_or_404(user_id)
    user.wholesale_status = "rejected"
    user.is_wholesale = False
    db.session.commit()
    flash(f"{user.email} application rejected", "success")
    return redirect(url_for("admin.wholesale_list"))


# ---------- Wholesale accounts (partner program) ----------

@bp.route("/wholesale-accounts")
@admin_required
def wholesale_accounts():
    from app.models import WholesaleAccount
    pending = WholesaleAccount.query.filter_by(status="pending").order_by(WholesaleAccount.applied_at.desc()).all()
    approved = WholesaleAccount.query.filter_by(status="approved").order_by(WholesaleAccount.approved_at.desc()).all()
    rejected = WholesaleAccount.query.filter_by(status="rejected").order_by(WholesaleAccount.applied_at.desc()).all()
    suspended = WholesaleAccount.query.filter_by(status="suspended").order_by(WholesaleAccount.applied_at.desc()).all()
    stats = compute_stats()
    return render_template("admin/wholesale_accounts.html",
                           pending=pending, approved=approved,
                           rejected=rejected, suspended=suspended, stats=stats)


@bp.route("/wholesale-accounts/<int:acct_id>")
@admin_required
def wholesale_account_detail(acct_id):
    from app.models import WholesaleAccount
    acct = WholesaleAccount.query.get_or_404(acct_id)
    stats = compute_stats()
    return render_template("admin/wholesale_account_detail.html", acct=acct, stats=stats)


@bp.route("/wholesale-accounts/<int:acct_id>/status", methods=["POST"])
@admin_required
def wholesale_account_set_status(acct_id):
    from datetime import datetime
    from app.models import WholesaleAccount

    acct = WholesaleAccount.query.get_or_404(acct_id)
    new_status = (request.form.get("status") or "").strip().lower()

    if new_status not in ("pending", "approved", "rejected", "suspended"):
        flash(f"Invalid status: {new_status!r}", "error")
        return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))

    acct.status = new_status
    if new_status == "approved" and not acct.approved_at:
        acct.approved_at = datetime.utcnow()
        acct.approved_by = current_user.id if current_user and current_user.is_authenticated else None
    db.session.commit()

    flash(f"{acct.company_name} → {new_status}", "success")
    return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))


@bp.route("/wholesale-accounts/<int:acct_id>/tier", methods=["POST"])
@admin_required
def wholesale_account_set_tier(acct_id):
    from app.models import WholesaleAccount
    acct = WholesaleAccount.query.get_or_404(acct_id)
    tier = request.form.get("tier", "").strip()
    if tier not in ("standard", "bronze", "silver", "gold"):
        flash("Invalid tier", "error")
        return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))
    acct.tier = tier
    db.session.commit()
    flash(f"{acct.company_name} tier → {tier}", "success")
    return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))


@bp.route("/wholesale-accounts/<int:acct_id>/notes", methods=["POST"])
@admin_required
def wholesale_account_set_notes(acct_id):
    from app.models import WholesaleAccount
    acct = WholesaleAccount.query.get_or_404(acct_id)
    acct.admin_notes = request.form.get("admin_notes", "").strip() or None
    db.session.commit()
    flash("Notes saved", "success")
    return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))


# ---------- Wholesale price overrides ----------

@bp.route("/wholesale-accounts/<int:acct_id>/prices")
@admin_required
def wholesale_account_prices(acct_id):
    from app.models import WholesaleAccount, Product, WholesalePrice
    acct = WholesaleAccount.query.get_or_404(acct_id)
    overrides = WholesalePrice.query.filter_by(wholesale_id=acct.id).all()
    override_map = {o.product_id: o for o in overrides}
    products = Product.query.filter_by(active=True).order_by(Product.category, Product.name).all()
    stats = compute_stats()
    return render_template(
        "admin/wholesale_account_prices.html",
        acct=acct, products=products, override_map=override_map, stats=stats,
    )


@bp.route("/wholesale-accounts/<int:acct_id>/prices/set", methods=["POST"])
@admin_required
def wholesale_account_price_set(acct_id):
    from app.models import WholesaleAccount, Product, WholesalePrice
    acct = WholesaleAccount.query.get_or_404(acct_id)
    product_id = request.form.get("product_id", type=int)
    if not product_id:
        flash("Product required", "error")
        return redirect(url_for("admin.wholesale_account_prices", acct_id=acct.id))

    product = Product.query.get_or_404(product_id)
    raw_price = request.form.get("price", "").strip()

    if not raw_price:
        # Empty = delete the override
        existing = WholesalePrice.query.filter_by(wholesale_id=acct.id, product_id=product_id).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            flash(f"Removed custom price for {product.name}", "success")
        return redirect(url_for("admin.wholesale_account_prices", acct_id=acct.id))

    try:
        price = float(raw_price)
        if price <= 0:
            raise ValueError
    except ValueError:
        flash("Price must be a positive number", "error")
        return redirect(url_for("admin.wholesale_account_prices", acct_id=acct.id))

    try:
        moq = int(request.form.get("min_quantity", "1") or 1)
        if moq < 1:
            moq = 1
    except ValueError:
        moq = 1

    notes = request.form.get("notes", "").strip() or None

    existing = WholesalePrice.query.filter_by(wholesale_id=acct.id, product_id=product_id).first()
    if existing:
        existing.price = price
        existing.min_quantity = moq
        existing.notes = notes
    else:
        db.session.add(WholesalePrice(
            wholesale_id=acct.id, product_id=product_id,
            price=price, min_quantity=moq, notes=notes,
        ))
    db.session.commit()
    flash(f"Saved custom price for {product.name}", "success")
    return redirect(url_for("admin.wholesale_account_prices", acct_id=acct.id))


@bp.route("/wholesale-accounts/<int:acct_id>/prices/clear", methods=["POST"])
@admin_required
def wholesale_account_prices_clear(acct_id):
    from app.models import WholesaleAccount, WholesalePrice
    acct = WholesaleAccount.query.get_or_404(acct_id)
    n = WholesalePrice.query.filter_by(wholesale_id=acct.id).delete()
    db.session.commit()
    flash(f"Cleared {n} custom price(s) — reverting to {acct.tier} tier", "success")
    return redirect(url_for("admin.wholesale_account_prices", acct_id=acct.id))


@bp.route("/wholesale-accounts/<int:acct_id>/custom-discount", methods=["POST"])
@admin_required
def wholesale_account_set_custom_discount(acct_id):
    from app.models import WholesaleAccount
    acct = WholesaleAccount.query.get_or_404(acct_id)
    raw = request.form.get("custom_discount_pct", "").strip()
    if not raw:
        acct.custom_discount_pct = None
        db.session.commit()
        flash("Blanket discount cleared.", "success")
        return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))
    try:
        pct = float(raw)
        if pct < 0 or pct > 90:
            raise ValueError
    except ValueError:
        flash("Discount must be between 0 and 90.", "error")
        return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))
    acct.custom_discount_pct = pct
    db.session.commit()
    flash(f"Blanket discount set to {pct}% off.", "success")
    return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))


@bp.route("/wholesale-accounts/<int:acct_id>/custom-discount/clear", methods=["POST"])
@admin_required
def wholesale_account_clear_custom_discount(acct_id):
    from app.models import WholesaleAccount
    acct = WholesaleAccount.query.get_or_404(acct_id)
    acct.custom_discount_pct = None
    db.session.commit()
    flash("Blanket discount removed.", "success")
    return redirect(url_for("admin.wholesale_account_detail", acct_id=acct.id))


# ---------- Status fix verification ----------

@bp.route("/wholesale-accounts/<int:acct_id>/debug-status")
@admin_required
def wholesale_account_debug_status(acct_id):
    """TEMP route to confirm status updates persist."""
    from app.models import WholesaleAccount
    acct = WholesaleAccount.query.get_or_404(acct_id)
    return {
        "id": acct.id,
        "company_name": acct.company_name,
        "status": acct.status,
        "tier": acct.tier,
        "custom_discount_pct": acct.custom_discount_pct,
        "approved_at": acct.approved_at.isoformat() if acct.approved_at else None,
    }




# ============ CAMPAIGNS ============

def _slugify_campaign(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _unique_campaign_slug(base, exclude_id=None):
    from app.models import Campaign
    slug = base
    n = 1
    while True:
        q = Campaign.query.filter_by(slug=slug)
        if exclude_id:
            q = q.filter(Campaign.id != exclude_id)
        if not q.first():
            return slug
        n += 1
        slug = f"{base}-{n}"


def _campaign_from_form(campaign, form):
    """Populate or create a Campaign from the request form."""
    from datetime import datetime
    from app.models import Campaign, CampaignPartner, CampaignProduct

    name = form.get("name", "").strip()
    if not name:
        return None, "Name is required."

    def parse_dt(field):
        raw = form.get(field, "").strip()
        if not raw:
            return None
        try:
            # HTML datetime-local sends "YYYY-MM-DDTHH:MM"
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    starts_at = parse_dt("starts_at")
    ends_at = parse_dt("ends_at")
    if not starts_at or not ends_at:
        return None, "Start and end dates are required."
    if ends_at <= starts_at:
        return None, "End date must be after start date."

    try:
        discount_value = float(form.get("discount_value", "0") or 0)
    except ValueError:
        discount_value = 0.0
    if discount_value < 0:
        return None, "Discount cannot be negative."

    min_order_value_raw = form.get("min_order_value", "").strip()
    try:
        min_order_value = float(min_order_value_raw) if min_order_value_raw else None
    except ValueError:
        min_order_value = None

    min_order_qty_raw = form.get("min_order_qty", "").strip()
    try:
        min_order_qty = int(min_order_qty_raw) if min_order_qty_raw else None
    except ValueError:
        min_order_qty = None

    # Tier scaling (e.g. bronze=5, silver=10, gold=15) — optional per-tier override
    tier_scaling = {}
    for t in ("bronze", "silver", "gold"):
        v = form.get(f"tier_scaling_{t}", "").strip()
        if v:
            try:
                tier_scaling[t] = float(v)
            except ValueError:
                pass

    # Tiers audience (multi-checkbox: new/bronze/silver/gold)
    tiers = [t for t in ("new", "bronze", "silver", "gold") if form.get(f"audience_tier_{t}")]

    # Scope categories (multi-checkbox)
    scope_categories = [c for c in ("coffee", "tea", "spices", "herbs", "honey", "blends", "accessories")
                        if form.get(f"scope_cat_{c}")]

    # Update or create
    if campaign is None:
        campaign = Campaign()

    campaign.name = name
    campaign.slug = _unique_campaign_slug(
        form.get("slug", "").strip() or _slugify_campaign(name),
        exclude_id=campaign.id,
    )
    campaign.public_description = form.get("public_description", "").strip() or None
    campaign.internal_notes = form.get("internal_notes", "").strip() or None
    campaign.starts_at = starts_at
    campaign.ends_at = ends_at
    campaign.channel = form.get("channel", "wholesale")
    campaign.activity_days = None
    activity_raw = form.get("activity_days", "").strip()
    if activity_raw:
        try:
            campaign.activity_days = max(1, int(activity_raw))
        except ValueError:
            pass
    campaign.scope = form.get("scope", "all")
    campaign.discount_type = form.get("discount_type", "percent")
    campaign.discount_value = discount_value
    campaign.min_order_value = min_order_value
    campaign.min_order_qty = min_order_qty
    campaign.override_pricing = form.get("override_pricing") == "1"
    campaign.respect_floor = form.get("respect_floor", "1") == "1"
    campaign.published = form.get("published") == "1"

    campaign.set_tiers(tiers)
    campaign.set_scope_categories(scope_categories)
    campaign.set_tier_scaling(tier_scaling)

    return campaign, None


def _save_campaign_partners(campaign, partner_ids):
    """Replace the campaign's partner links with the given IDs."""
    from app.models import CampaignPartner
    CampaignPartner.query.filter_by(campaign_id=campaign.id).delete()
    for pid in partner_ids:
        try:
            pid = int(pid)
        except (ValueError, TypeError):
            continue
        db.session.add(CampaignPartner(campaign_id=campaign.id, wholesale_id=pid))


def _save_campaign_products(campaign, product_ids):
    """Replace the campaign's product links with the given IDs."""
    from app.models import CampaignProduct
    CampaignProduct.query.filter_by(campaign_id=campaign.id).delete()
    for pid in product_ids:
        try:
            pid = int(pid)
        except (ValueError, TypeError):
            continue
        db.session.add(CampaignProduct(campaign_id=campaign.id, product_id=pid))


@bp.route("/campaigns")
@admin_required
def campaigns():
    from app.models import Campaign
    all_campaigns = Campaign.query.order_by(Campaign.starts_at.desc()).all()
    # Split by status
    live = [c for c in all_campaigns if c.is_live()]
    scheduled = [c for c in all_campaigns if c.published and c.is_upcoming()]
    drafts = [c for c in all_campaigns if not c.published]
    expired = [c for c in all_campaigns if c.published and c.is_expired()]
    stats = compute_stats()
    return render_template(
        "admin/campaigns.html",
        campaigns=all_campaigns,
        live=live, scheduled=scheduled, drafts=drafts, expired=expired,
        stats=stats,
    )


@bp.route("/campaigns/new", methods=["GET", "POST"])
@admin_required
def campaign_new():
    from app.models import WholesaleAccount, Product
    stats = compute_stats()
    if request.method == "POST":
        campaign, err = _campaign_from_form(None, request.form)
        if err:
            flash(err, "error")
            return render_template(
                "admin/campaign_edit.html",
                campaign=None, stats=stats, form=request.form,
                partners=WholesaleAccount.query.order_by(WholesaleAccount.company_name).all(),
                products=Product.query.filter_by(active=True).order_by(Product.name).all(),
            )
        db.session.add(campaign)
        db.session.flush()
        _save_campaign_partners(campaign, request.form.getlist("partner_ids"))
        _save_campaign_products(campaign, request.form.getlist("product_ids"))
        db.session.commit()
        flash(f"Campaign '{campaign.name}' created", "success")
        return redirect(url_for("admin.campaigns"))
    return render_template(
        "admin/campaign_edit.html",
        campaign=None, stats=stats, form={},
        partners=WholesaleAccount.query.order_by(WholesaleAccount.company_name).all(),
        products=Product.query.filter_by(active=True).order_by(Product.name).all(),
    )


@bp.route("/campaigns/<int:campaign_id>/edit", methods=["GET", "POST"])
@admin_required
def campaign_edit(campaign_id):
    from app.models import Campaign, WholesaleAccount, Product, CampaignPartner, CampaignProduct
    campaign = Campaign.query.get_or_404(campaign_id)
    stats = compute_stats()
    if request.method == "POST":
        _, err = _campaign_from_form(campaign, request.form)
        if err:
            flash(err, "error")
            return render_template(
                "admin/campaign_edit.html",
                campaign=campaign, stats=stats, form=request.form,
                partners=WholesaleAccount.query.order_by(WholesaleAccount.company_name).all(),
                products=Product.query.filter_by(active=True).order_by(Product.name).all(),
            )
        _save_campaign_partners(campaign, request.form.getlist("partner_ids"))
        _save_campaign_products(campaign, request.form.getlist("product_ids"))
        db.session.commit()
        flash(f"Campaign '{campaign.name}' updated", "success")
        return redirect(url_for("admin.campaign_edit", campaign_id=campaign.id))
    return render_template(
        "admin/campaign_edit.html",
        campaign=campaign, stats=stats, form=None,
        partners=WholesaleAccount.query.order_by(WholesaleAccount.company_name).all(),
        products=Product.query.filter_by(active=True).order_by(Product.name).all(),
    )


@bp.route("/campaigns/<int:campaign_id>/toggle-publish", methods=["POST"])
@admin_required
def campaign_toggle_publish(campaign_id):
    from app.models import Campaign
    c = Campaign.query.get_or_404(campaign_id)
    c.published = not c.published
    db.session.commit()
    flash(f"'{c.name}' now {'published' if c.published else 'draft'}", "success")
    return redirect(url_for("admin.campaigns"))


@bp.route("/campaigns/<int:campaign_id>/delete", methods=["POST"])
@admin_required
def campaign_delete(campaign_id):
    from app.models import Campaign
    c = Campaign.query.get_or_404(campaign_id)
    name = c.name
    db.session.delete(c)
    db.session.commit()
    flash(f"Deleted campaign '{name}'", "success")
    return redirect(url_for("admin.campaigns"))


# ============ TIER AUTO-MANAGEMENT ============

@bp.route("/tier-program")
@admin_required
def tier_program():
    from app.tiers import tier_requirements, evaluate_account

    accounts = (WholesaleAccount.query
                .filter_by(status="approved")
                .order_by(WholesaleAccount.company_name).all())

    rows = []
    for acct in accounts:
        eval_result = evaluate_account(acct)
        rows.append({
            "acct": acct,
            "eval": eval_result,
            "trailing_revenue": eval_result["actual_revenue"],
        })

    at_risk = [r for r in rows if r["acct"].tier_state in ("warn", "grace", "downgrade", "terminate")]
    healthy = [r for r in rows if r["acct"].tier_state == "ok"]
    reqs = tier_requirements()
    stats = compute_stats()

    return render_template(
        "admin/tier_program.html",
        rows=rows, at_risk=at_risk, healthy=healthy,
        requirements=reqs, stats=stats,
    )


@bp.route("/tier-program/evaluate", methods=["POST"])
@admin_required
def tier_program_evaluate():
    from app.tiers import evaluate_all
    dry = request.form.get("dry_run") == "1"
    results = evaluate_all(dry_run=dry)
    changed = sum(1 for r in results if not r.get("skipped") and r.get("state_before") != r.get("state_after"))
    skipped = sum(1 for r in results if r.get("skipped"))
    verb = "Simulated" if dry else "Evaluated"
    flash(f"{verb} {len(results)} partner(s): {changed} state change(s), {skipped} locked/skipped.", "success")
    return redirect(url_for("admin.tier_program"))


@bp.route("/tier-program/<int:acct_id>/lock", methods=["POST"])
@admin_required
def tier_program_lock(acct_id):
    acct = WholesaleAccount.query.get_or_404(acct_id)
    acct.tier_locked = True
    acct.tier_locked_reason = request.form.get("reason", "").strip() or "Manual lock by admin"
    db.session.commit()
    flash(f"{acct.company_name} tier locked.", "success")
    return redirect(url_for("admin.tier_program"))


@bp.route("/tier-program/<int:acct_id>/unlock", methods=["POST"])
@admin_required
def tier_program_unlock(acct_id):
    acct = WholesaleAccount.query.get_or_404(acct_id)
    acct.tier_locked = False
    acct.tier_locked_reason = None
    db.session.commit()
    flash(f"{acct.company_name} tier unlocked.", "success")
    return redirect(url_for("admin.tier_program"))


@bp.route("/tier-program/<int:acct_id>/reset-state", methods=["POST"])
@admin_required
def tier_program_reset_state(acct_id):
    acct = WholesaleAccount.query.get_or_404(acct_id)
    acct.tier_state = "ok"
    acct.tier_missed_months = 0
    acct.tier_state_since = None
    db.session.commit()
    flash(f"{acct.company_name} state reset.", "success")
    return redirect(url_for("admin.tier_program"))


# ============ TIER PROGRAM: APPLY DOWNGRADES ============

@bp.route("/tier-program/apply", methods=["POST"])
@admin_required
def tier_program_apply():
    """Actually apply pending tier changes."""
    from app.tiers import apply_downgrade, apply_termination
    from app.models import WholesaleAccount

    to_downgrade = WholesaleAccount.query.filter_by(status="approved", tier_state="downgrade").all()
    to_terminate = WholesaleAccount.query.filter_by(status="approved", tier_state="terminate").all()

    changed = []
    for acct in to_terminate:
        r = apply_termination(acct)
        if r:
            changed.append((acct.company_name, r["from"], r["to"]))
    for acct in to_downgrade:
        r = apply_downgrade(acct)
        if r:
            changed.append((acct.company_name, r["from"], r["to"]))

    if changed:
        names = ", ".join(f"{c[0]} ({c[1]}→{c[2]})" for c in changed)
        flash(f"Applied {len(changed)} tier change(s): {names}", "success")
    else:
        flash("No pending tier changes to apply.", "success")

    return redirect(url_for("admin.tier_program"))


# ============ PARTNER RELATIONSHIP PAGE ============

@bp.route("/wholesale-accounts/<int:acct_id>/relationship")
@admin_required
def partner_relationship(acct_id):
    """Single-partner dossier: orders, revenue, tier history, campaigns, notes."""
    from datetime import datetime, timedelta
    from app.models import WholesaleAccount, Order, Campaign, OrderEvent, WholesalePrice
    from app.tiers import tier_requirements, partner_revenue, partner_revenue_series, evaluate_account
    from app.campaigns import campaigns_for
    from app.models import Product

    acct = WholesaleAccount.query.get_or_404(acct_id)

    # Orders
    orders = (Order.query
              .filter_by(wholesale_id=acct.id)
              .order_by(Order.created_at.desc())
              .all())
    total_orders = len(orders)
    total_spend = round(sum(o.total for o in orders if o.status != "cancelled"), 2)
    avg_order = round(total_spend / total_orders, 2) if total_orders else 0.0
    last_order = orders[0] if orders else None

    # Revenue series (12 months)
    series = partner_revenue_series(acct, months=12)
    max_rev = max((v for _, v in series), default=0) or 1

    # Tier status
    reqs = tier_requirements()
    eval_result = evaluate_account(acct)
    req = reqs.get((acct.tier or "new").lower(), {"months": 1, "amount": 0})
    tier_trailing = partner_revenue(acct, req["months"])

    # Order timeline (recent events)
    recent_events = (OrderEvent.query
                     .join(Order, OrderEvent.order_id == Order.id)
                     .filter(Order.wholesale_id == acct.id)
                     .order_by(OrderEvent.created_at.desc())
                     .limit(10).all())

    # Campaigns matching this partner
    active_matches = {}
    for p in Product.query.filter_by(active=True).limit(50).all():
        for c in campaigns_for(acct, p):
            active_matches[c.id] = c

    # Custom price overrides
    overrides = WholesalePrice.query.filter_by(wholesale_id=acct.id).all()

    stats = compute_stats()

    return render_template(
        "admin/partner_relationship.html",
        acct=acct,
        orders=orders,
        total_orders=total_orders,
        total_spend=total_spend,
        avg_order=avg_order,
        last_order=last_order,
        series=series,
        max_rev=max_rev,
        tier_trailing=tier_trailing,
        tier_req=req,
        eval_result=eval_result,
        recent_events=recent_events,
        active_campaigns=list(active_matches.values()),
        overrides=overrides,
        stats=stats,
    )


# ============ BULK ORDER ACTIONS ============

@bp.route("/orders/bulk", methods=["POST"])
@admin_required
def orders_bulk_action():
    """Apply a status change to multiple orders at once."""
    from app.orders import change_order_status

    order_ids = request.form.getlist("order_ids")
    new_status = (request.form.get("bulk_status") or "").strip().lower()
    note = request.form.get("bulk_note", "").strip() or None

    if not order_ids:
        flash("No orders selected.", "warning")
        return redirect(url_for("admin.orders"))

    if new_status not in ("paid", "shipped", "delivered", "cancelled"):
        flash("Invalid bulk status.", "error")
        return redirect(url_for("admin.orders"))

    applied = 0
    skipped = []

    for oid in order_ids:
        try:
            oid = int(oid)
        except (ValueError, TypeError):
            continue
        order = Order.query.get(oid)
        if not order:
            continue
        ok, err = change_order_status(
            order, new_status,
            actor_email=current_user.email if current_user.is_authenticated else None,
            actor_role="admin",
            note=note,
        )
        if ok:
            applied += 1
        else:
            skipped.append(f"#{order.id}: {err}")

    msg = f"Applied '{new_status}' to {applied} order(s)."
    if skipped:
        msg += f" Skipped {len(skipped)}: {'; '.join(skipped[:3])}{'…' if len(skipped) > 3 else ''}"
    flash(msg, "success" if applied else "warning")
    return redirect(url_for("admin.orders"))


# ---------- AI Assistant diagnostics ----------

@bp.route("/settings/test-ai", methods=["POST"])
@admin_required
def settings_test_ai():
    from app.ai import test_connection, is_configured
    if not is_configured():
        flash("❌ AI not configured — set the API key and click Save first.", "error")
        return redirect(url_for("admin.settings"))
    result = test_connection()
    if result.get("ok"):
        flash(f"✅ {result.get('description', 'Connected')} ({result.get('latency_ms', '?')}ms)", "success")
    else:
        flash(f"❌ AI: {result.get('description', 'Unknown error')}", "error")
    return redirect(url_for("admin.settings"))


# ============ AI ASSISTANT: HEALTH ============

@bp.route("/assistant/health")
@admin_required
def assistant_health():
    """On-demand health check panel."""
    from app.health import run_all_checks, summarize
    from app.models import AiAlert, AiWatcherRun, Setting

    results = run_all_checks()
    summary = summarize(results)

    # Recent alerts (last 30)
    recent_alerts = (AiAlert.query
                     .order_by(AiAlert.created_at.desc())
                     .limit(30).all())

    # Watcher state
    recent_runs = (AiWatcherRun.query
                   .order_by(AiWatcherRun.started_at.desc())
                   .limit(10).all())
    last_run = recent_runs[0] if recent_runs else None
    watcher_enabled = (Setting.get("AI_WATCHER_ENABLED") or "0") == "1"
    watcher_interval = int(Setting.get("AI_WATCHER_INTERVAL_MIN") or 30)

    stats = compute_stats()
    return render_template(
        "admin/assistant_health.html",
        results=results,
        summary=summary,
        recent_alerts=recent_alerts,
        recent_runs=recent_runs,
        last_run=last_run,
        watcher_enabled=watcher_enabled,
        watcher_interval=watcher_interval,
        stats=stats,
    )


@bp.route("/assistant/health/summarize", methods=["POST"])
@admin_required
def assistant_health_summarize():
    """Run all checks and get AI summary."""
    from app.health import run_all_checks
    from app.ai import explain_health, is_configured
    from app.models import AiAlert

    if not is_configured():
        flash("AI not configured — set the API key in Settings.", "error")
        return redirect(url_for("admin.settings"))

    results = run_all_checks()
    summary = explain_health(results)

    if summary.get("ok"):
        # Persist each problem as an alert
        for r in results:
            if r["status"] in ("warn", "fail"):
                # Skip if an unresolved identical alert exists
                existing = (AiAlert.query
                            .filter_by(check_name=r["name"], status=r["status"], resolved=False)
                            .first())
                if existing:
                    existing.message = r["message"]
                    existing.detail = r.get("detail")
                    existing.ai_summary = summary.get("summary")
                else:
                    db.session.add(AiAlert(
                        check_name=r["name"],
                        status=r["status"],
                        title=r["name"].replace("_", " ").title(),
                        message=r["message"],
                        detail=r.get("detail"),
                        ai_summary=summary.get("summary"),
                    ))
        db.session.commit()
        flash("✅ AI summary generated. See below.", "success")
    else:
        flash(f"❌ AI error: {summary.get('error')}", "error")

    return redirect(url_for("admin.assistant_health"))


@bp.route("/assistant/health/alert/<int:alert_id>/resolve", methods=["POST"])
@admin_required
def assistant_health_resolve(alert_id):
    from app.models import AiAlert
    a = AiAlert.query.get_or_404(alert_id)
    a.resolved = True
    a.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(f"Alert '{a.title}' marked resolved.", "success")
    return redirect(url_for("admin.assistant_health"))


# ============ AI ASSISTANT: CONTENT ============

@bp.route("/assistant/content")
@admin_required
def assistant_content():
    """Landing page with three tools."""
    from app.models import Product

    products = Product.query.filter_by(active=True).order_by(Product.name).all()
    stats = compute_stats()
    return render_template(
        "admin/assistant_content.html",
        products=products,
        stats=stats,
        generated=None,
    )


@bp.route("/assistant/content/product", methods=["POST"])
@admin_required
def assistant_content_product():
    """Generate a long_description for a product."""
    from app.models import Product
    from app.ai import chat, is_configured, _system_prompt

    if not is_configured():
        flash("AI not configured — set the API key in Settings.", "error")
        return redirect(url_for("admin.settings"))

    product_id = request.form.get("product_id", type=int)
    tone = request.form.get("tone", "warm")
    length = request.form.get("length", "medium")
    keywords = request.form.get("keywords", "").strip()

    product = Product.query.get_or_404(product_id)

    tone_guide = {
        "warm":    "warm, inviting, sensory — like a good shopkeeper's recommendation",
        "b2b":     "professional, direct, focused on sourcing and consistency",
        "story":   "storytelling, evocative — talks about origins and the people behind it",
        "concise": "short, factual, no fluff — bullet-friendly",
    }.get(tone, "warm, inviting")

    length_guide = {
        "short":  "3–4 sentences (~60 words)",
        "medium": "2 short paragraphs (~120 words)",
        "long":   "3 paragraphs (~220 words), include a 'how to use' note",
    }.get(length, "2 short paragraphs")

    system = _system_prompt(
        "You write product copy for the shop's catalogue. Output clean HTML (use <p>, <strong>, <em>, <ul><li>). "
        "Never include a heading, price, or meta description. Just the body text."
    )

    prompt_lines = [
        f"Write a product description for the following product.",
        "",
        f"Name: {product.name}",
        f"Category: {product.category}",
    ]
    if product.subcategory:
        prompt_lines.append(f"Subcategory: {product.subcategory}")
    if product.origin_country:
        prompt_lines.append(f"Origin: {product.origin_country}{' · ' + product.origin_region if product.origin_region else ''}")
    if product.short_desc:
        prompt_lines.append(f"Existing one-liner: {product.short_desc}")
    if product.description:
        prompt_lines.append(f"Existing summary: {product.description}")
    if keywords:
        prompt_lines.append(f"Try to naturally include these keywords: {keywords}")
    prompt_lines += [
        "",
        f"Tone: {tone_guide}",
        f"Length: {length_guide}",
        "Output: HTML only. No markdown, no code fences, no headings.",
    ]

    r = chat(
        messages=[system, {"role": "user", "content": "\n".join(prompt_lines)}],
        max_tokens=1200,
        temperature=0.7,
    )

    if not r["ok"]:
        flash(f"AI error: {r['error']}", "error")
        return redirect(url_for("admin.assistant_content"))

    return render_template(
        "admin/assistant_content.html",
        products=Product.query.filter_by(active=True).order_by(Product.name).all(),
        stats=compute_stats(),
        generated={
            "tool": "product",
            "product_id": product.id,
            "product_name": product.name,
            "content": r["content"].strip(),
            "tokens": (r.get("usage") or {}).get("total_tokens"),
        },
    )


@bp.route("/assistant/content/product/save", methods=["POST"])
@admin_required
def assistant_content_product_save():
    """Save the AI-generated long_description onto the product."""
    from app.models import Product
    product_id = request.form.get("product_id", type=int)
    content = request.form.get("content", "").strip()

    if not product_id or not content:
        flash("Nothing to save.", "error")
        return redirect(url_for("admin.assistant_content"))

    product = Product.query.get_or_404(product_id)
    product.long_description = content
    db.session.commit()
    flash(f"✅ Saved to {product.name}", "success")
    return redirect(url_for("admin.product_edit", product_id=product.id))


@bp.route("/assistant/content/article", methods=["POST"])
@admin_required
def assistant_content_article():
    """Generate a blog article draft."""
    from app.ai import chat, is_configured, _system_prompt

    if not is_configured():
        flash("AI not configured — set the API key in Settings.", "error")
        return redirect(url_for("admin.settings"))

    topic = request.form.get("topic", "").strip()
    outline = request.form.get("outline", "").strip()
    category = request.form.get("category", "coffee").strip()
    length = request.form.get("length", "medium")
    audience = request.form.get("audience", "enthusiasts").strip()

    if not topic:
        flash("Topic is required.", "error")
        return redirect(url_for("admin.assistant_content"))

    length_guide = {
        "short":  "600–800 words, 3–4 H2 sections",
        "medium": "1000–1400 words, 5–6 H2 sections + intro + conclusion",
        "long":   "1800–2400 words, 7–9 H2 sections with H3s, includes intro, takeaway, conclusion",
    }.get(length, "1000–1400 words, 5–6 H2 sections")

    system = _system_prompt(
        "You write long-form articles for the shop's journal. Output clean HTML "
        "(<p>, <h2>, <h3>, <strong>, <em>, <ul><li>, <blockquote>). "
        "Never include the title tag, meta description, or any wrapper HTML — just the article body. "
        "Use an engaging but grounded voice. No clickbait. No invented claims."
    )

    prompt_lines = [
        f"Write an article for the shop's blog.",
        "",
        f"Topic: {topic}",
        f"Category: {category}",
        f"Audience: {audience}",
    ]
    if outline:
        prompt_lines += ["", "Rough outline to follow:", outline]
    prompt_lines += [
        "",
        f"Length: {length_guide}",
        "Structure: <h2> for main sections, <p> for body, occasional <h3> for sub-points.",
        "No H1 (that's the article title, written separately).",
        "HTML only. No markdown, no code fences.",
    ]

    r = chat(
        messages=[system, {"role": "user", "content": "\n".join(prompt_lines)}],
        max_tokens=3000,
        temperature=0.7,
    )

    if not r["ok"]:
        flash(f"AI error: {r['error']}", "error")
        return redirect(url_for("admin.assistant_content"))

    # Suggest a title and slug
    title_r = chat(
        messages=[
            _system_prompt("You write short, punchy titles. Reply with the title only, no quotes, no markdown."),
            {"role": "user", "content": f"Suggest a title for an article about: {topic}"},
        ],
        max_tokens=60,
        temperature=0.5,
    )
    suggested_title = title_r.get("content", "").strip().splitlines()[0] if title_r.get("ok") else topic

    return render_template(
        "admin/assistant_content.html",
        products=Product.query.filter_by(active=True).order_by(Product.name).all(),
        stats=compute_stats(),
        generated={
            "tool": "article",
            "title": suggested_title[:200],
            "content": r["content"].strip(),
            "tokens": (r.get("usage") or {}).get("total_tokens"),
            "category": category,
        },
    )


@bp.route("/assistant/content/article/save", methods=["POST"])
@admin_required
def assistant_content_article_save():
    """Create a draft Article from the AI output."""
    from app.models import Article
    import re

    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    category = request.form.get("category", "").strip() or None

    if not title or not content:
        flash("Title and content required.", "error")
        return redirect(url_for("admin.assistant_content"))

    def slugify(s):
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    base = slugify(title)
    slug = base
    n = 1
    while Article.query.filter_by(slug=slug).first():
        n += 1
        slug = f"{base}-{n}"

    excerpt_r = content[:300].replace("<p>", "").replace("</p>", " ").strip()[:280]

    article = Article(
        title=title,
        slug=slug,
        body=content,
        excerpt=excerpt_r,
        category=category,
        author_name="The Spice & Roast Co.",
        reading_minutes=max(2, len(content.split()) // 200),
        published=False,
    )
    db.session.add(article)
    db.session.commit()
    flash(f"✅ Draft article '{article.title}' created — review and publish from the Articles page.", "success")
    return redirect(url_for("admin.article_edit", article_id=article.id))


@bp.route("/assistant/content/seo", methods=["POST"])
@admin_required
def assistant_content_seo():
    """Rewrite copy to be SEO-friendly."""
    from app.ai import chat, is_configured, _system_prompt

    if not is_configured():
        flash("AI not configured — set the API key in Settings.", "error")
        return redirect(url_for("admin.settings"))

    original = request.form.get("original", "").strip()
    keyword = request.form.get("keyword", "").strip()
    intent = request.form.get("intent", "informational").strip()

    if not original or not keyword:
        flash("Original text and target keyword are required.", "error")
        return redirect(url_for("admin.assistant_content"))

    system = _system_prompt(
        "You improve existing copy for SEO without making it sound robotic. "
        "Never keyword-stuff. Keep the original meaning and voice. "
        "Output clean HTML (same tags as input)."
    )

    prompt_lines = [
        "Rewrite the following copy for better SEO.",
        "",
        f"Primary keyword: {keyword}",
        f"Search intent: {intent}",
        "",
        "Guidelines:",
        "- Include the primary keyword naturally — 1–3 times per 300 words, not more",
        "- Use semantic variations (related phrases) instead of repeating",
        "- Keep sentences readable. No robot voice.",
        "- Preserve any existing <h2>, <h3> structure",
        "",
        "Original:",
        original,
        "",
        "Output: cleaned HTML version. No wrapper, no explanation.",
    ]

    r = chat(
        messages=[system, {"role": "user", "content": "\n".join(prompt_lines)}],
        max_tokens=2000,
        temperature=0.5,
    )

    if not r["ok"]:
        flash(f"AI error: {r['error']}", "error")
        return redirect(url_for("admin.assistant_content"))

    return render_template(
        "admin/assistant_content.html",
        products=Product.query.filter_by(active=True).order_by(Product.name).all(),
        stats=compute_stats(),
        generated={
            "tool": "seo",
            "keyword": keyword,
            "content": r["content"].strip(),
            "tokens": (r.get("usage") or {}).get("total_tokens"),
        },
    )


# ---------- Product picker data ----------

@bp.route("/api/products-index")
@admin_required
def api_products_index():
    """Lightweight product list for client-side picker/search."""
    from app.models import Product
    rows = (Product.query
            .filter_by(active=True)
            .order_by(Product.name)
            .all())
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category or "",
                "origin": p.origin_country or "",
                "region": p.origin_region or "",
                "tags": p.tags or "",
                "price": round(p.price or 0, 2),
            }
            for p in rows
        ]
    }


# ============ AI ASSISTANT: CODE ============

@bp.route("/assistant/code")
@admin_required
def assistant_code():
    """Code assistant landing page."""
    from app.codebase import list_files
    files = list_files()
    stats = compute_stats()
    return render_template(
        "admin/assistant_code.html",
        files=files,
        stats=stats,
        suggestion=None,
        picked_files=[],
        problem="",
    )


@bp.route("/assistant/code/diagnose", methods=["POST"])
@admin_required
def assistant_code_diagnose():
    """Send problem + selected files to the AI. Returns diagnosis + suggested patch."""
    from app.ai import chat, is_configured
    from app.codebase import read_many, guess_relevant_files, list_files

    if not is_configured():
        flash("AI not configured.", "error")
        return redirect(url_for("admin.settings"))

    problem = request.form.get("problem", "").strip()
    if not problem:
        flash("Describe the problem first.", "error")
        return redirect(url_for("admin.assistant_code"))

    # Which files?
    picked = request.form.getlist("files")
    if not picked:
        picked = guess_relevant_files(problem)
        flash(f"AI selected {len(picked)} file(s) based on your description.", "success")

    # Read them
    contents = read_many(picked)

    if not contents:
        flash("No readable files matched. Try picking files manually.", "warning")
        return redirect(url_for("admin.assistant_code"))

    # Build the context block
    files_block = []
    for path, body in contents.items():
        # Trim very long files, keeping head and tail
        if len(body) > 8000:
            head = body[:5000]
            tail = body[-1500:]
            body = head + "\n\n# ... [truncated] ...\n\n" + tail
        files_block.append(f"### FILE: {path}\n```\n{body}\n```")

    system = {
        "role": "system",
        "content": (
            "You are a senior Python/Flask engineer reviewing a small e-commerce codebase. "
            "Your job: diagnose problems described by the admin, look at the provided files, and propose a precise fix.\n\n"
            "Output format (use these exact section headers):\n\n"
            "DIAGNOSIS:\n"
            "<1-4 sentences explaining what's wrong>\n\n"
            "FILES_TO_CHANGE:\n"
            "<one file path per line — only files that need edits>\n\n"
            "FIX:\n"
            "For each file, output a fenced block:\n"
            "```file:path/to/file.py\n"
            "<the exact lines that must change, shown as a unified diff using --- and +++ and @@ markers>\n"
            "```\n\n"
            "VERIFY:\n"
            "<one-line command to test the fix>\n\n"
            "Rules:\n"
            "- Only propose changes to files you were shown.\n"
            "- Keep diffs minimal — do not rewrite whole files.\n"
            "- Never invent imports or functions that don't exist.\n"
            "- If you're not confident, say so in DIAGNOSIS and give two possible causes."
        ),
    }

    user_block = (
        f"PROBLEM REPORTED BY ADMIN:\n{problem}\n\n"
        f"FILES PROVIDED ({len(contents)} total, {sum(len(v) for v in contents.values())} chars):\n\n"
        + "\n\n".join(files_block)
    )

    r = chat(
        messages=[system, {"role": "user", "content": user_block}],
        model=None,          # use configured chat model
        max_tokens=4000,
        temperature=0.2,     # low temp — we want precise, not creative
    )

    if not r["ok"]:
        flash(f"AI error: {r['error']}", "error")
        return redirect(url_for("admin.assistant_code"))

    # Parse the response into sections
    raw = r["content"]
    parsed = _parse_diagnosis(raw)

    return render_template(
        "admin/assistant_code.html",
        files=list_files(),
        stats=compute_stats(),
        suggestion=parsed,
        raw=raw,
        picked_files=list(contents.keys()),
        problem=problem,
        usage=(r.get("usage") or {}),
    )


def _parse_diagnosis(text):
    """Split the AI response into DIAGNOSIS / FILES_TO_CHANGE / FIX / VERIFY."""
    import re
    out = {"diagnosis": "", "files": [], "diffs": [], "verify": "", "raw": text}

    # DIAGNOSIS
    m = re.search(r"DIAGNOSIS:\s*(.*?)(?=\n\s*FILES_TO_CHANGE:|\Z)", text, re.S | re.I)
    if m:
        out["diagnosis"] = m.group(1).strip()

    # FILES_TO_CHANGE
    m = re.search(r"FILES_TO_CHANGE:\s*(.*?)(?=\n\s*FIX:|\Z)", text, re.S | re.I)
    if m:
        for line in m.group(1).strip().splitlines():
            line = line.strip().lstrip("-*•").strip()
            if line:
                out["files"].append(line)

    # FIX: find ```file:...``` blocks with diff content
    for fm in re.finditer(r"```file:([^\n]+)\n(.*?)```", text, re.S):
        out["diffs"].append({
            "path": fm.group(1).strip(),
            "diff": fm.group(2).strip(),
        })

    # VERIFY
    m = re.search(r"VERIFY:\s*(.*?)(?=\n\n[A-Z_]+:|\Z)", text, re.S | re.I)
    if m:
        out["verify"] = m.group(1).strip()

    return out


@bp.route("/assistant/code/apply", methods=["POST"])
@admin_required
def assistant_code_apply():
    """Apply a proposed diff, verify, rollback on failure."""
    import os
    import shutil
    import subprocess
    import sys
    from datetime import datetime
    from pathlib import Path
    from app.codebase import project_root

    path = request.form.get("path", "").strip()
    diff_text = request.form.get("diff", "").strip()

    if not path or not diff_text:
        flash("Missing path or diff.", "error")
        return redirect(url_for("admin.assistant_code"))

    # Resolve + safe path check
    root = project_root()
    full = (root / path).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        flash("Refused: path outside project.", "error")
        return redirect(url_for("admin.assistant_code"))

    if not full.is_file():
        flash(f"File not found: {path}", "error")
        return redirect(url_for("admin.assistant_code"))

    # Backup
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    bak = full.with_suffix(full.suffix + f".bak.{ts}")
    shutil.copy2(full, bak)

    # Apply via patch
    original = full.read_text(encoding="utf-8", errors="replace")

    # Try `patch` command first (handles proper unified diffs)
    applied = False
    apply_err = ""

    try:
        # Write diff to temp file
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False, encoding="utf-8") as tf:
            # Some models omit the ---/+++ headers, so ensure they're present
            d = diff_text
            if "---" not in d.splitlines()[0] if d.splitlines() else True:
                pass
            tf.write(d)
            diff_file = tf.name

        # `patch -p0` expects a/b paths; try -p1 as fallback
        result = subprocess.run(
            ["patch", "--forward", "-p0", str(full), diff_file],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            applied = True
        else:
            apply_err = result.stderr[:400] or result.stdout[:400]
            # Try -p1
            result2 = subprocess.run(
                ["patch", "--forward", "-p1", "-d", str(root), diff_file],
                capture_output=True, text=True, timeout=15,
            )
            if result2.returncode == 0:
                applied = True
            else:
                apply_err += " | " + (result2.stderr[:300] or result2.stdout[:300])

        os.unlink(diff_file)
    except FileNotFoundError:
        apply_err = "The `patch` utility is not installed. Run: sudo apt install patch"
    except Exception as e:
        apply_err = str(e)

    if not applied:
        # Restore from backup
        shutil.copy2(bak, full)
        flash(f"❌ Could not apply diff: {apply_err}", "error")
        return redirect(url_for("admin.assistant_code"))

    # Verify: does the app still load?
    verify_ok = True
    verify_err = ""
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from app import create_app; create_app(); print('ok')"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 or "ok" not in result.stdout:
            verify_ok = False
            verify_err = (result.stderr or result.stdout)[-600:]
    except Exception as e:
        verify_ok = False
        verify_err = str(e)

    if not verify_ok:
        # Rollback
        shutil.copy2(bak, full)
        flash(f"❌ Change broke the app — auto-rolled back. Error: {verify_err[:300]}", "error")
        return redirect(url_for("admin.assistant_code"))

    flash(f"✅ Applied to {path}. Backup: {bak.name}", "success")
    return redirect(url_for("admin.assistant_code"))


# ============ AI ASSISTANT: HUB ============

@bp.route("/assistant")
@admin_required
def assistant_hub():
    """Central hub for all assistant tools."""
    from app.models import AiAlert, AiWatcherRun, Article, Product

    # Recent AI-related activity
    open_alerts = (AiAlert.query
                   .filter_by(resolved=False)
                   .filter(AiAlert.status.in_(("warn", "fail")))
                   .order_by(AiAlert.created_at.desc())
                   .limit(5).all())

    last_watcher = (AiWatcherRun.query
                    .order_by(AiWatcherRun.started_at.desc())
                    .first())

    # Counts
    recent_articles = Article.query.order_by(Article.created_at.desc()).limit(5).all()
    # Products missing a long_description (candidates for AI writing)
    products_missing_desc = (Product.query
                             .filter_by(active=True)
                             .filter((Product.long_description.is_(None)) | (Product.long_description == ""))
                             .count())

    stats = compute_stats()
    return render_template(
        "admin/assistant_hub.html",
        open_alerts=open_alerts,
        last_watcher=last_watcher,
        recent_articles=recent_articles,
        products_missing_desc=products_missing_desc,
        stats=stats,
    )


@bp.route("/assistant/chat", methods=["POST"])
@admin_required
def assistant_chat():
    """
    Minimal chat endpoint used by the drawer.
    Accepts {message, context} and returns {ok, reply}.
    """
    from app.ai import chat, is_configured

    if not is_configured():
        return {"ok": False, "reply": "AI not configured. Set the API key in Settings."}, 400

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    context = (data.get("context") or "").strip()

    if not message:
        return {"ok": False, "reply": "Empty message."}, 400

    system = {
        "role": "system",
        "content": (
            "You are an assistant embedded in the admin panel of a Flask shop called "
            "The Spice & Roast Co. Be concise — one or two short paragraphs max. "
            "If asked to fix code, tell the admin to use the Code Assistant at /admin/assistant/code. "
            "If asked to write content, direct them to /admin/assistant/content. "
            "If they describe a bug or broken page, tell them to run a health check first at /admin/assistant/health."
        ),
    }

    user_msg = message
    if context:
        user_msg = f"[Context: {context}]\n\n{message}"

    r = chat(
        messages=[system, {"role": "user", "content": user_msg}],
        max_tokens=600,
        temperature=0.5,
    )

    if not r["ok"]:
        return {"ok": False, "reply": f"Error: {r['error']}"}, 500

    return {"ok": True, "reply": r["content"].strip()}



@bp.route("/products/bulk-delete", methods=["POST"])
@admin_required
def products_bulk_delete():
    """Delete multiple products at once. Honors a `next` return URL."""
    ids = request.form.getlist("product_ids")
    next_url = request.form.get("next", "").strip()

    # Safety: only allow redirects back into /admin
    if not next_url.startswith("/admin"):
        next_url = url_for("admin.products")

    if not ids:
        flash("No products selected.", "warning")
        return redirect(next_url)

    deleted = 0
    deleted_names = []
    errors = []
    for pid in ids:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        product = Product.query.get(pid)
        if not product:
            continue
        name = product.name
        try:
            db.session.delete(product)
            deleted += 1
            deleted_names.append(name)
        except Exception as e:
            errors.append(f"#{pid}: {e}")

    db.session.commit()

    if deleted == 1:
        msg = f"Deleted '{deleted_names[0]}'."
    else:
        msg = f"Deleted {deleted} product(s): {', '.join(deleted_names[:3])}" + ("…" if len(deleted_names) > 3 else "")
    if errors:
        msg += f"  Errors: {'; '.join(errors[:3])}"

    flash(msg, "success" if deleted else "warning")
    return redirect(next_url)


# ---------- Duplicates finder ----------

@bp.route("/products/duplicates")
@admin_required
def products_duplicates():
    """Find products that share images or names."""
    from collections import defaultdict

    all_products = Product.query.order_by(Product.category, Product.name).all()

    # Group by image
    by_image = defaultdict(list)
    for p in all_products:
        if p.image:
            by_image[p.image].append(p)

    # Group by lowercase name
    by_name = defaultdict(list)
    for p in all_products:
        if p.name:
            by_name[p.name.strip().lower()].append(p)

    # Only keep groups with 2+ products
    image_dupes = {k: v for k, v in by_image.items() if len(v) > 1}
    name_dupes = {k: v for k, v in by_name.items() if len(v) > 1}

    # Also find orphan images in uploads/products/ that aren't linked to any product
    import os
    from flask import current_app
    uploads_dir = os.path.join(current_app.static_folder, "uploads", "products")
    linked_images = {p.image for p in all_products if p.image}
    orphan_images = []
    if os.path.isdir(uploads_dir):
        for f in sorted(os.listdir(uploads_dir)):
            url = f"/static/uploads/products/{f}"
            if url not in linked_images and f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                path = os.path.join(uploads_dir, f)
                orphan_images.append({
                    "filename": f,
                    "url": url,
                    "size_kb": round(os.path.getsize(path) / 1024, 1),
                })

    # Also find products pointing at non-existent images
    import pathlib
    missing_images = []
    for p in all_products:
        if not p.image:
            continue
        if p.image.startswith("/static/"):
            fs = pathlib.Path(current_app.static_folder).parent / p.image.lstrip("/")
        else:
            fs = pathlib.Path(current_app.static_folder) / "images" / p.image
        # Check the file or its webp variant
        exists = fs.exists() or fs.with_suffix(".webp").exists()
        if not exists:
            missing_images.append(p)

    stats = compute_stats()
    return render_template(
        "admin/products_duplicates.html",
        image_dupes=image_dupes,
        name_dupes=name_dupes,
        orphan_images=orphan_images,
        missing_images=missing_images,
        stats=stats,
        total_products=len(all_products),
    )


@bp.route("/products/duplicates/cleanup-orphans", methods=["POST"])
@admin_required
def products_cleanup_orphans():
    """Delete orphan image files (that no product references)."""
    import os
    from flask import current_app

    uploads_dir = os.path.join(current_app.static_folder, "uploads", "products")
    linked_images = {p.image for p in Product.query.all() if p.image}

    removed = 0
    freed_bytes = 0
    if os.path.isdir(uploads_dir):
        for f in os.listdir(uploads_dir):
            url = f"/static/uploads/products/{f}"
            if url in linked_images:
                continue
            if not f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                continue
            path = os.path.join(uploads_dir, f)
            try:
                freed_bytes += os.path.getsize(path)
                os.remove(path)
                removed += 1
            except Exception:
                pass

    mb = freed_bytes / 1024 / 1024
    flash(f"Removed {removed} orphan image(s) — freed {mb:.1f} MB.", "success")
    return redirect(url_for("admin.products_duplicates"))
