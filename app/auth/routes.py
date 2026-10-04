import re
import time
from datetime import datetime, timedelta
from collections import defaultdict

from flask import (
    render_template, request, redirect, url_for, flash, session
)
from flask_login import (
    current_user, login_user, logout_user, login_required
)

from app.auth import bp
from app import db
from app.models import User, Order, CartItem


# --- Simple in-memory rate limit for login/register ---
_attempts = defaultdict(list)
WINDOW_SECONDS = 900  # 15 minutes
MAX_ATTEMPTS = 5


def _rate_limited(key):
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < WINDOW_SECONDS]
    return len(_attempts[key]) >= MAX_ATTEMPTS


def _record_attempt(key):
    _attempts[key].append(time.time())


def _client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------- Register ----------------

@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account"))

    if request.method == "POST":
        key = f"register:{_client_ip()}"
        if _rate_limited(key):
            flash("Too many attempts. Try again in 15 minutes.", "error")
            return render_template("auth/register.html", form=request.form)

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("password2", "")
        full_name = request.form.get("full_name", "").strip()

        errors = []
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            _record_attempt(key)
            return render_template("auth/register.html", form=request.form)

        user = User(email=email, full_name=full_name or None, is_admin=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        _merge_cart(user)

        flash(f"Welcome, {user.display_name}!", "success")
        return redirect(url_for("auth.account"))

    return render_template("auth/register.html", form={})


# ---------------- Login ----------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account"))

    if request.method == "POST":
        key = f"login:{_client_ip()}"
        if _rate_limited(key):
            flash("Too many attempts. Try again in 15 minutes.", "error")
            return render_template("auth/login.html", form=request.form)

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password) or not user.is_active_account:
            _record_attempt(key)
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", form=request.form)

        login_user(user, remember=True)
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        _merge_cart(user)

        flash(f"Welcome back, {user.display_name}!", "success")
        next_url = request.args.get("next") or url_for("auth.account")
        if not next_url.startswith("/"):
            next_url = url_for("auth.account")
        return redirect(next_url)

    return render_template("auth/login.html", form={})


# ---------------- Logout ----------------

@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("main.index"))


# ---------------- Cart merge ----------------

def _merge_cart(user):
    """Attach any anonymous cart items to the newly logged-in user."""
    sid = session.get("cart_sid")
    if not sid:
        return

    anon_items = CartItem.query.filter_by(session_id=sid, user_id=None).all()
    for anon in anon_items:
        existing = CartItem.query.filter_by(user_id=user.id, product_id=anon.product_id).first()
        if existing:
            existing.quantity += anon.quantity
            db.session.delete(anon)
        else:
            anon.user_id = user.id
            anon.session_id = None
    db.session.commit()


# ---------------- Account ----------------

@bp.route("/account")
@login_required
def account():
    order_count = Order.query.filter_by(user_id=current_user.id).count()
    recent = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(3).all()
    return render_template("auth/account.html", order_count=order_count, recent_orders=recent)


@bp.route("/account/edit", methods=["GET", "POST"])
@login_required
def account_edit():
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip() or None
        current_user.phone = request.form.get("phone", "").strip() or None
        current_user.address_line = request.form.get("address_line", "").strip() or None
        current_user.city = request.form.get("city", "").strip() or None
        current_user.postal_code = request.form.get("postal_code", "").strip() or None
        current_user.country = request.form.get("country", "").strip() or None
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("auth.account"))
    return render_template("auth/account_edit.html")


@bp.route("/account/orders")
@login_required
def account_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("auth/account_orders.html", orders=orders)


@bp.route("/account/orders/<int:order_id>")
@login_required
def account_order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash("That order isn't yours.", "error")
        return redirect(url_for("auth.account_orders"))
    return render_template("auth/account_order_detail.html", order=order)


# ---------------- Change password ----------------

@bp.route("/account/password", methods=["POST"])
@login_required
def account_password():
    current_pw = request.form.get("current_password", "")
    new_pw = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    errors = []
    if not current_user.check_password(current_pw):
        errors.append("Current password is incorrect.")
    if len(new_pw) < 8:
        errors.append("New password must be at least 8 characters.")
    if new_pw != confirm:
        errors.append("New passwords do not match.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("auth.account"))

    current_user.set_password(new_pw)
    db.session.commit()
    flash("Password updated.", "success")
    return redirect(url_for("auth.account"))


# ---------------- Wholesale application ----------------

@bp.route("/wholesale")
def wholesale_landing():
    """Public page explaining the program."""
    from app.models import Setting
    return render_template("auth/wholesale_landing.html")


@bp.route("/wholesale/apply", methods=["GET", "POST"])
@login_required
def wholesale_apply():
    """Submit an application. Requires login (creates lead with contact info)."""
    from datetime import datetime
    if current_user.is_wholesale and current_user.wholesale_status == "approved":
        flash("You're already an approved wholesale partner.", "success")
        return redirect(url_for("auth.account"))

    if request.method == "POST":
        business_name = request.form.get("business_name", "").strip()
        business_type = request.form.get("business_type", "").strip()
        business_registration = request.form.get("business_registration", "").strip()
        phone = request.form.get("phone", "").strip()
        country = request.form.get("country", "").strip()
        city = request.form.get("city", "").strip()
        message = request.form.get("message", "").strip()

        errors = []
        if not business_name:
            errors.append("Business name is required.")
        if not business_type:
            errors.append("Please choose a business type.")
        if not phone:
            errors.append("Contact phone is required.")
        if not country:
            errors.append("Country is required.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/wholesale_apply.html", form=request.form)

        current_user.business_name = business_name
        current_user.business_type = business_type
        current_user.business_registration = business_registration or None
        current_user.phone = phone
        current_user.country = country
        current_user.city = city or current_user.city
        current_user.wholesale_notes = message or current_user.wholesale_notes
        current_user.wholesale_status = "pending"
        current_user.wholesale_applied_at = datetime.utcnow()
        db.session.commit()

        flash("Application submitted. We'll review it within 2 business days.", "success")
        return redirect(url_for("auth.account"))

    return render_template("auth/wholesale_apply.html", form={})
