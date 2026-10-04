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


@bp.route("/settings")
@admin_required
def settings():
    stats = compute_stats()
    return render_template("admin/settings.html", stats=stats)


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
