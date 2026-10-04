"""Wholesale catalog. Full implementation in Patch 10.4."""
from flask import render_template
from app.wholesale import bp
from app.wholesale.session import approved_wholesale_required


@bp.route("/catalog")
@approved_wholesale_required
def catalog():
    return "Wholesale catalog — coming in Patch 10.4"
