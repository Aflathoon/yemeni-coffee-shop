import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app
from flask import render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user, login_user
from app.admin import bp
from app.models import Product, User, Order, Post
from app import db
from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(request.form.get("password")):
            login_user(user)
            return redirect(url_for("admin.dashboard"))
        flash("Invalid credentials")
    return render_template("admin/login.html")

@bp.route("/dashboard")
@admin_required
def dashboard():
    stats = {
        "products": Product.query.count(),
        "orders": Order.query.count(),
        "users": User.query.count(),
        "posts": Post.query.count(),
        "revenue": sum(o.total for o in Order.query.all())
    }
    products = Product.query.order_by(Product.created_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html", stats=stats, products=products)

@bp.route("/post/new", methods=["GET", "POST"])
@admin_required
def new_post():
    if request.method == "POST":
        post = Post(
            title=request.form.get("title"),
            body=request.form.get("body"),
            image=request.form.get("image", "")
        )
        db.session.add(post)
        db.session.commit()
        flash("Post created")
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/editor.html")

@bp.route("/post/<int:id>/publish")
@admin_required
def publish_post(id):
    post = Post.query.get_or_404(id)
    post.published = True
    db.session.commit()
    # In production: call social media APIs here
    flash(f"Post '{post.title}' published (simulated)")
    return redirect(url_for("admin.dashboard"))
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@bp.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    """Upload an image and return its /static/uploads/... path."""
    if request.method == "POST":
        file = request.files.get("file")
        kind = request.form.get("kind", "products")  # products|posts|originals
        if kind not in ("products", "posts", "originals"):
            kind = "products"

        if not file or file.filename == "":
            flash("No file selected")
            return redirect(url_for("admin.upload"))

        if not _allowed_file(file.filename):
            flash("File type not allowed")
            return redirect(url_for("admin.upload"))

        # Unique filename — avoid collisions and path traversal
        ext = file.filename.rsplit(".", 1)[1].lower()
        stem = secure_filename(file.filename.rsplit(".", 1)[0])[:40] or "upload"
        fname = f"{stem}-{uuid.uuid4().hex[:8]}.{ext}"
        folder = os.path.join(current_app.static_folder, "uploads", kind)
        os.makedirs(folder, exist_ok=True)
        file.save(os.path.join(folder, fname))

        rel = f"/static/uploads/{kind}/{fname}"
        flash(f"Uploaded → {rel}")

        # If the caller asked for JSON (AJAX), return it
        if request.args.get("json") == "1":
            return {"path": rel, "filename": fname}

        return redirect(url_for("admin.upload"))

    # GET — show upload form + gallery of existing uploads
    folder = os.path.join(current_app.static_folder, "uploads")
    gallery = {"products": [], "posts": [], "originals": []}
    for k in gallery:
        d = os.path.join(folder, k)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d), reverse=True)[:60]:
                if _allowed_file(f):
                    gallery[k].append(f"/static/uploads/{k}/{f}")

    return render_template("admin/upload.html", gallery=gallery)

