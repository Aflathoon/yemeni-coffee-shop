"""Wholesale dashboard. Full implementation in Patch 10.3."""
from flask import render_template
from app.wholesale import bp
from app.wholesale.session import wholesale_required


@bp.route("/dashboard")
@wholesale_required
def dashboard():
    return "Wholesale dashboard — coming in Patch 10.3"
