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


# ---------- Wholesale cart ----------

def _ws_cart_items(acct):
    from app.models import CartItem
    return (CartItem.query
            .filter_by(wholesale_id=acct.id)
            .order_by(CartItem.added_at.desc()).all())


def _ws_cart_summary(acct):
    """Return subtotal, shipping, total, and item count for a wholesale cart."""
    from app.pricing import wholesale_price_for, get_discount_percent
    items = _ws_cart_items(acct)
    subtotal = 0.0
    for it in items:
        info = wholesale_price_for(acct, it.product)
        subtotal += info["price"] * it.quantity
    subtotal = round(subtotal, 2)
    shipping = 0.0 if subtotal >= 250 else (15.0 if subtotal > 0 else 0.0)
    total = round(subtotal + shipping, 2)
    count = sum(it.quantity for it in items)
    return {
        "items": items,
        "subtotal": subtotal,
        "shipping": shipping,
        "total": total,
        "count": count,
    }


@bp.route("/cart")
@approved_wholesale_required
def cart_view():
    from app.pricing import wholesale_price_for
    acct = current_wholesale()
    summary = _ws_cart_summary(acct)

    # Pre-compute per-line pricing
    lines = []
    for it in summary["items"]:
        info = wholesale_price_for(acct, it.product)
        lines.append({
            "item": it,
            "info": info,
            "line_total": round(info["price"] * it.quantity, 2),
        })

    return render_template(
        "wholesale/cart.html",
        acct=acct,
        lines=lines,
        subtotal=summary["subtotal"],
        shipping=summary["shipping"],
        total=summary["total"],
        count=summary["count"],
    )


@bp.route("/cart/update/<int:item_id>", methods=["POST"])
@approved_wholesale_required
def cart_update(item_id):
    from app.models import CartItem
    from app.pricing import wholesale_price_for
    acct = current_wholesale()
    item = CartItem.query.get_or_404(item_id)
    if item.wholesale_id != acct.id:
        flash("That item isn't in your cart.", "error")
        return redirect(url_for("wholesale.cart_view"))

    info = wholesale_price_for(acct, item.product)
    moq = max(1, info.get("min_quantity") or 1)

    try:
        qty = int(request.form.get("quantity", str(moq)) or moq)
    except ValueError:
        qty = moq
    if qty < moq:
        qty = moq
        flash(f"Minimum quantity for {item.product.name} is {moq}.", "warning")

    item.quantity = qty
    db.session.commit()
    return redirect(url_for("wholesale.cart_view"))


@bp.route("/cart/remove/<int:item_id>", methods=["POST"])
@approved_wholesale_required
def cart_remove(item_id):
    from app.models import CartItem
    acct = current_wholesale()
    item = CartItem.query.get_or_404(item_id)
    if item.wholesale_id != acct.id:
        flash("That item isn't in your cart.", "error")
        return redirect(url_for("wholesale.cart_view"))
    db.session.delete(item)
    db.session.commit()
    flash("Item removed.", "success")
    return redirect(url_for("wholesale.cart_view"))


@bp.route("/cart/clear", methods=["POST"])
@approved_wholesale_required
def cart_clear():
    from app.models import CartItem
    acct = current_wholesale()
    CartItem.query.filter_by(wholesale_id=acct.id).delete()
    db.session.commit()
    flash("Cart cleared.", "success")
    return redirect(url_for("wholesale.cart_view"))


# ---------- Wholesale checkout ----------

@bp.route("/checkout", methods=["GET", "POST"])
@approved_wholesale_required
def checkout():
    from app.models import Order, OrderItem, CartItem
    from app.pricing import wholesale_price_for
    from datetime import datetime

    acct = current_wholesale()
    summary = _ws_cart_summary(acct)

    if not summary["items"]:
        flash("Your wholesale cart is empty.", "warning")
        return redirect(url_for("wholesale.catalog"))

    if request.method == "POST":
        # Use shipping address from account, but allow override
        address_line = request.form.get("address_line", "").strip() or acct.address_line
        city = request.form.get("city", "").strip() or acct.city
        postal_code = request.form.get("postal_code", "").strip() or acct.postal_code
        country = request.form.get("country", "").strip() or acct.country
        notes = request.form.get("notes", "").strip()
        po_number = request.form.get("po_number", "").strip()

        errors = []
        if not address_line: errors.append("Shipping address is required.")
        if not city: errors.append("City is required.")
        if not country: errors.append("Country is required.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "wholesale/checkout.html",
                acct=acct,
                lines=[],
                subtotal=summary["subtotal"],
                shipping=summary["shipping"],
                total=summary["total"],
                form=request.form,
            )

        # Build the order
        order = Order(
            user_id=None,
            wholesale_id=acct.id,
            email=acct.email,
            full_name=acct.company_name,
            address_line=address_line,
            city=city,
            postal_code=postal_code or "",
            country=country,
            notes=(f"PO: {po_number}\n" if po_number else "") + (notes or ""),
            status="pending",
            subtotal=summary["subtotal"],
            shipping=summary["shipping"],
            total=summary["total"],
        )
        db.session.add(order)
        db.session.flush()

        for it in summary["items"]:
            info = wholesale_price_for(acct, it.product)
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=it.product_id,
                product_name=it.product.name,
                product_price=info["price"],       # snapshot wholesale price
                quantity=it.quantity,
                line_total=round(info["price"] * it.quantity, 2),
            ))
            db.session.delete(it)

        db.session.commit()
        flash(f"Wholesale order #{order.id} placed.", "success")
        return redirect(url_for("wholesale.order_confirmation", order_id=order.id))

    # GET — prefill from account
    form = {
        "address_line": acct.address_line or "",
        "city": acct.city or "",
        "postal_code": acct.postal_code or "",
        "country": acct.country or "",
    }

    lines = []
    for it in summary["items"]:
        info = wholesale_price_for(acct, it.product)
        lines.append({
            "item": it,
            "info": info,
            "line_total": round(info["price"] * it.quantity, 2),
        })

    return render_template(
        "wholesale/checkout.html",
        acct=acct,
        lines=lines,
        subtotal=summary["subtotal"],
        shipping=summary["shipping"],
        total=summary["total"],
        form=form,
    )


@bp.route("/orders/<int:order_id>")
@approved_wholesale_required
def order_confirmation(order_id):
    from app.models import Order
    acct = current_wholesale()
    order = Order.query.get_or_404(order_id)
    if order.wholesale_id != acct.id:
        flash("That order isn't yours.", "error")
        return redirect(url_for("wholesale.orders"))
    return render_template("wholesale/order_confirmation.html", acct=acct, order=order)
