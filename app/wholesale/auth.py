"""Wholesale authentication routes. Full implementation in Patch 10.2."""
from flask import render_template, request, redirect, url_for, flash
from app.wholesale import bp


@bp.route("/")
def landing():
    return render_template("wholesale/landing.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    return "Wholesale register — coming in Patch 10.2"


@bp.route("/login", methods=["GET", "POST"])
def login():
    return "Wholesale login — coming in Patch 10.2"


@bp.route("/logout", methods=["POST"])
def logout():
    from app.wholesale.session import logout_wholesale
    logout_wholesale()
    flash("Signed out of partner portal.", "success")
    return redirect(url_for("wholesale.landing"))
