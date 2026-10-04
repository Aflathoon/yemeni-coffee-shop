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
from app.models import Product, User, Order, OrderItem, Post


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

    return {
        "products": Product.query.count(),
        "orders": len(orders),
        "users": User.query.count(),
        "posts": Post.query.count(),
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
    q = Order.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    all_orders = q.order_by(Order.created_at.desc()).all()
    stats = compute_stats()
    return render_template("admin/orders.html",
                           orders=all_orders, stats=stats, status_filter=status_filter)


@bp.route("/orders/<int:order_id>")
@admin_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    stats = compute_stats()
    return render_template("admin/order_detail.html", order=order, stats=stats)


@bp.route("/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def order_set_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status", "").strip()
    if new_status not in ("pending", "paid", "shipped", "delivered", "cancelled"):
        flash("Invalid status", "error")
    else:
        order.status = new_status
        db.session.commit()
        flash(f"Order #{order.id} → {new_status}", "success")
    return redirect(url_for("admin.order_detail", order_id=order.id))


# ---------- Products ----------

@bp.route("/products")
@admin_required
def products():
    all_products = Product.query.order_by(Product.category, Product.name).all()
    stats = compute_stats()
    return render_template("admin/products.html", products=all_products, stats=stats)


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
    product.weight_grams = weight
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
