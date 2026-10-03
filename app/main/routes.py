from flask import render_template, jsonify, request
from sqlalchemy import distinct, func
from app.main import bp
from app.models import Product
from app.agent import explain_product


@bp.route("/")
def index():
    # Filters from query string
    category = request.args.get("category")
    country = request.args.get("country")
    featured_only = request.args.get("featured") == "1"

    q = Product.query
    if category:
        q = q.filter_by(category=category)
    if country:
        q = q.filter_by(origin_country=country)
    if featured_only:
        q = q.filter_by(featured=True)

    products = q.order_by(Product.created_at.desc()).all()

    # Sidebar data — distinct categories and countries with counts
    categories = db_categories()
    countries = db_countries()
    featured = Product.query.filter_by(featured=True).limit(5).all()

    return render_template(
        "index.html",
        products=products,
        categories=categories,
        countries=countries,
        featured=featured,
        active_category=category,
        active_country=country,
    )


def db_categories():
    from app import db
    rows = (
        db.session.query(Product.category, func.count(Product.id))
        .group_by(Product.category)
        .order_by(Product.category)
        .all()
    )
    return [{"name": c, "count": n} for c, n in rows]


def db_countries():
    from app import db
    rows = (
        db.session.query(Product.origin_country, func.count(Product.id))
        .filter(Product.origin_country.isnot(None))
        .group_by(Product.origin_country)
        .order_by(Product.origin_country)
        .all()
    )
    return [{"name": c, "count": n} for c, n in rows]


@bp.route("/product/<slug>")
def product_detail(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    explanation = explain_product(product.name)
    # Related: same category, different product
    related = (
        Product.query
        .filter(Product.category == product.category, Product.id != product.id)
        .limit(4)
        .all()
    )
    return render_template(
        "product.html",
        product=product,
        explanation=explanation,
        related=related,
    )


@bp.route("/api/explain/<slug>")
def api_explain(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    return jsonify(explain_product(product.name))
