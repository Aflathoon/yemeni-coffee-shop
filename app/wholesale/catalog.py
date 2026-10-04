"""Wholesale catalog — browse + search + add to wholesale cart."""
from flask import (
    render_template, request, redirect, url_for, flash, jsonify
)
from sqlalchemy import func, distinct
from app.wholesale import bp
from app import db
from app.models import Product, CartItem
from app.wholesale.session import approved_wholesale_required, current_wholesale
from app.pricing import wholesale_price_for


@bp.route("/catalog")
@approved_wholesale_required
def catalog():
    acct = current_wholesale()

    category = request.args.get("category", "").strip()
    country = request.args.get("country", "").strip()
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "name")

    q = Product.query.filter_by(active=True)
    if category:
        q = q.filter_by(category=category)
    if country:
        q = q.filter_by(origin_country=country)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (Product.name.ilike(like))
            | (Product.short_desc.ilike(like))
            | (Product.origin_country.ilike(like))
            | (Product.tags.ilike(like))
        )

    if sort == "price_asc":
        q = q.order_by(Product.price.asc())
    elif sort == "price_desc":
        q = q.order_by(Product.price.desc())
    else:
        q = q.order_by(Product.category.asc(), Product.name.asc())

    products = q.all()

    # Compute pricing for each product (cached per request)
    priced = []
    for p in products:
        info = wholesale_price_for(acct, p)
        priced.append({"product": p, "price_info": info})

    # Counts for the sidebar
    cat_q = db.session.query(Product.category, func.count(Product.id)).filter(Product.active == True)
    category_counts = dict(cat_q.group_by(Product.category).all())

    country_q = db.session.query(Product.origin_country, func.count(Product.id)).filter(
        Product.active == True, Product.origin_country.isnot(None)
    )
    country_counts = dict(country_q.group_by(Product.origin_country).order_by(Product.origin_country).all())

    # Wholesale cart size
    cart_count = db.session.query(func.sum(CartItem.quantity)).filter(
        CartItem.wholesale_id == acct.id
    ).scalar() or 0

    return render_template(
        "wholesale/catalog.html",
        acct=acct,
        priced=priced,
        categories=category_counts,
        countries=country_counts,
        active_category=category,
        active_country=country,
        search=search,
        active_sort=sort,
        cart_count=int(cart_count),
    )


@bp.route("/catalog/add/<slug>", methods=["POST"])
@approved_wholesale_required
def catalog_add(slug):
    acct = current_wholesale()
    product = Product.query.filter_by(slug=slug, active=True).first_or_404()

    # MOQ from override if present, else 1
    info = wholesale_price_for(acct, product)
    moq = max(1, info.get("min_quantity") or 1)

    try:
        qty = int(request.form.get("quantity", moq) or moq)
    except ValueError:
        qty = moq
    if qty < moq:
        qty = moq
        flash(f"Minimum quantity for this item is {moq}.", "warning")

    existing = CartItem.query.filter_by(
        wholesale_id=acct.id, product_id=product.id
    ).first()
    if existing:
        existing.quantity += qty
    else:
        db.session.add(CartItem(
            wholesale_id=acct.id,
            product_id=product.id,
            quantity=qty,
        ))
    db.session.commit()
    flash(f"Added {qty} × {product.name} to wholesale cart.", "success")

    # AJAX?
    if request.headers.get("Accept", "").startswith("application/json"):
        new_count = db.session.query(func.sum(CartItem.quantity)).filter(
            CartItem.wholesale_id == acct.id
        ).scalar() or 0
        return jsonify(ok=True, count=int(new_count))

    return redirect(request.referrer or url_for("wholesale.catalog"))


@bp.route("/catalog/product/<slug>")
@approved_wholesale_required
def catalog_product(slug):
    acct = current_wholesale()
    product = Product.query.filter_by(slug=slug, active=True).first_or_404()
    info = wholesale_price_for(acct, product)
    return render_template("wholesale/product.html", acct=acct, product=product, price_info=info)


@bp.route("/cart")
@approved_wholesale_required
def cart_view():
    """Wholesale cart. Full implementation in Patch 10.4."""
    acct = current_wholesale()
    items = (CartItem.query
             .filter_by(wholesale_id=acct.id)
             .order_by(CartItem.added_at.desc()).all())
    return render_template("wholesale/cart.html", acct=acct, items=items, price_info={})
