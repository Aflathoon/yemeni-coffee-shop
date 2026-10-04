"""Wholesale authentication: register, login, logout."""
import re
import time
from datetime import datetime
from collections import defaultdict

from flask import (
    render_template, request, redirect, url_for, flash, session, g
)
from app.wholesale import bp
from app import db
from app.models import WholesaleAccount
from app.wholesale.session import login_wholesale, logout_wholesale, current_wholesale


# Simple in-memory rate limit
_attempts = defaultdict(list)
WINDOW_SECONDS = 900
MAX_ATTEMPTS = 5

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _rate_limited(key):
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < WINDOW_SECONDS]
    return len(_attempts[key]) >= MAX_ATTEMPTS


def _record_attempt(key):
    _attempts[key].append(time.time())


def _client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0].strip()


# ---------- Landing ----------

@bp.route("/")
def landing():
    if current_wholesale():
        return redirect(url_for("wholesale.dashboard"))
    return render_template("wholesale/landing.html")


# ---------- Register ----------

@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_wholesale():
        return redirect(url_for("wholesale.dashboard"))

    if request.method == "POST":
        key = f"ws-register:{_client_ip()}"
        if _rate_limited(key):
            flash("Too many attempts. Try again in 15 minutes.", "error")
            return render_template("wholesale/register.html", form=request.form)

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("password2", "")
        company_name = request.form.get("company_name", "").strip()
        business_type = request.form.get("business_type", "").strip()

        errors = []
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if not company_name:
            errors.append("Company name is required.")
        if not business_type:
            errors.append("Please select a business type.")
        if WholesaleAccount.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            _record_attempt(key)
            return render_template("wholesale/register.html", form=request.form)

        acct = WholesaleAccount(
            email=email,
            company_name=company_name,
            business_type=business_type,
            tax_id=request.form.get("tax_id", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            address_line=request.form.get("address_line", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            postal_code=request.form.get("postal_code", "").strip() or None,
            country=request.form.get("country", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
            status="pending",
            tier="standard",
        )
        acct.set_password(password)
        db.session.add(acct)
        db.session.commit()

        login_wholesale(acct)
        flash(f"Welcome, {acct.company_name}. Your account is pending review.", "success")
        return redirect(url_for("wholesale.dashboard"))

    return render_template("wholesale/register.html", form={})


# ---------- Login ----------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_wholesale():
        return redirect(url_for("wholesale.dashboard"))

    if request.method == "POST":
        key = f"ws-login:{_client_ip()}"
        if _rate_limited(key):
            flash("Too many attempts. Try again in 15 minutes.", "error")
            return render_template("wholesale/login.html", form=request.form)

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        acct = WholesaleAccount.query.filter_by(email=email).first()
        if not acct or not acct.check_password(password):
            _record_attempt(key)
            flash("Invalid email or password.", "error")
            return render_template("wholesale/login.html", form=request.form)

        if acct.status == "suspended":
            flash("This account is suspended. Please contact us.", "error")
            return render_template("wholesale/login.html", form=request.form)

        login_wholesale(acct)
        acct.last_login_at = datetime.utcnow()
        db.session.commit()

        flash(f"Welcome back, {acct.company_name}.", "success")
        next_url = request.args.get("next") or url_for("wholesale.dashboard")
        if not next_url.startswith("/wholesale"):
            next_url = url_for("wholesale.dashboard")
        return redirect(next_url)

    return render_template("wholesale/login.html", form={})


# ---------- Logout ----------

@bp.route("/logout", methods=["POST"])
def logout():
    logout_wholesale()
    flash("Signed out of the partner portal.", "success")
    return redirect(url_for("wholesale.landing"))
