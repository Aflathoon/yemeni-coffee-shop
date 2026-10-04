from flask import Blueprint
bp = Blueprint("wholesale", __name__, url_prefix="/wholesale")
from app.wholesale import auth, catalog, dashboard
