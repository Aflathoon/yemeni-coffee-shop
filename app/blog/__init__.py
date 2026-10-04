from flask import Blueprint
bp = Blueprint("blog", __name__, url_prefix="/blog")
from app.blog import routes
