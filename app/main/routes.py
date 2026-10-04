import secrets
from flask import (
    render_template, jsonify, request, session, redirect,
    url_for, flash
)
from flask_login import current_user
from sqlalchemy import func
from app import db
from app.main import bp
from app.models import Product, CartItem, Order, OrderItem
from app.agent import explain_product


# ---------- Cart helpers ----------

def get_session_id():
    if "cart_sid" not in session:
        session["cart_sid"] = secrets.token_urlsafe(32)
        session.permanent = True
    return session["cart_sid"]


def get_cart_items():
    q = CartItem.query
    if current_user.is_authenticated:
        return q.filter_by(user_id=current_user.id).order_by(CartItem.added_at.desc()).all()
    return q.filter_by(session_id=get_session_id()).order_by(CartItem.added_at.desc()).all()


def cart_count():
    return sum(i.quantity for i in get_cart_items())


def cart_subtotal():
    return round(sum(i.product.price * i.quantity for i in get_cart_items()), 2)


def shipping_for(subtotal):
    return 0.0 if subtotal >= 100.0 else (8.0 if subtotal > 0 else 0.0)


# ---------- Catalog ----------

@bp.route("/")
def index():
    category = request.args.get("category")
    country = request.args.get("country")
    search = request.args.get("q", "").strip()

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
            | (Product.description.ilike(like))
            | (Product.origin_country.ilike(like))
        )
    products = q.order_by(Product.created_at.desc()).all()

    categories = db_categories()
    countries = db_countries()
    featured = Product.query.filter_by(featured=True).limit(5).all()

    return render_template(
        "index.html",
        products=products, categories=categories, countries=countries,
        featured=featured, active_category=category, active_country=country,
    )


def db_categories():
    rows = (
        db.session.query(Product.category, func.count(Product.id))
        .group_by(Product.category).order_by(Product.category).all()
    )
    return [{"name": c, "count": n} for c, n in rows]


def db_countries():
    rows = (
        db.session.query(Product.origin_country, func.count(Product.id))
        .filter(Product.origin_country.isnot(None))
        .group_by(Product.origin_country).order_by(Product.origin_country).all()
    )
    return [{"name": c, "count": n} for c, n in rows]


@bp.route("/product/<slug>")
def product_detail(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    explanation = explain_product(product.name, product.category, product.origin_country)
    related = (
        Product.query
        .filter(Product.category == product.category, Product.id != product.id)
        .limit(4).all()
    )
    return render_template(
        "product.html", product=product, explanation=explanation, related=related
    )


@bp.route("/api/explain/<slug>")
def api_explain(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    return jsonify(explain_product(product.name, product.category, product.origin_country))


@bp.route("/api/cart-count")
def api_cart_count():
    return jsonify(count=cart_count())


# ---------- Cart routes ----------

@bp.route("/cart")
def cart_view():
    items = get_cart_items()
    subtotal = cart_subtotal()
    shipping = shipping_for(subtotal)
    total = round(subtotal + shipping, 2)
    return render_template(
        "cart.html",
        items=items, subtotal=subtotal, shipping=shipping, total=total
    )


@bp.route("/cart/add/<slug>", methods=["POST"])
def cart_add(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()
    qty = max(1, int(request.form.get("quantity", 1)))

    if current_user.is_authenticated:
        item = CartItem.query.filter_by(user_id=current_user.id, product_id=product.id).first()
        if item:
            item.quantity += qty
        else:
            db.session.add(CartItem(user_id=current_user.id, product_id=product.id, quantity=qty))
    else:
        sid = get_session_id()
        item = CartItem.query.filter_by(session_id=sid, product_id=product.id).first()
        if item:
            item.quantity += qty
        else:
            db.session.add(CartItem(session_id=sid, product_id=product.id, quantity=qty))

    db.session.commit()
    flash(f"Added {product.name} to your cart", "success")
    return redirect(request.referrer or url_for("main.cart_view"))


@bp.route("/cart/update/<int:item_id>", methods=["POST"])
def cart_update(item_id):
    item = CartItem.query.get_or_404(item_id)
    if not _owns_item(item):
        return ("Not your cart item", 403)
    item.quantity = max(1, int(request.form.get("quantity", 1)))
    db.session.commit()
    flash("Cart updated", "success")
    return redirect(url_for("main.cart_view"))


@bp.route("/cart/remove/<int:item_id>", methods=["POST"])
def cart_remove(item_id):
    item = CartItem.query.get_or_404(item_id)
    if not _owns_item(item):
        return ("Not your cart item", 403)
    db.session.delete(item)
    db.session.commit()
    flash("Item removed", "success")
    return redirect(url_for("main.cart_view"))


def _owns_item(item):
    if current_user.is_authenticated:
        return item.user_id == current_user.id
    return item.session_id == session.get("cart_sid")


@bp.route("/cart/clear", methods=["POST"])
def cart_clear():
    for item in get_cart_items():
        db.session.delete(item)
    db.session.commit()
    flash("Cart cleared", "success")
    return redirect(url_for("main.cart_view"))


# ---------- Checkout ----------

@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    items = get_cart_items()
    if not items:
        flash("Your cart is empty", "warning")
        return redirect(url_for("main.cart_view"))

    subtotal = cart_subtotal()
    shipping = shipping_for(subtotal)
    total = round(subtotal + shipping, 2)

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        full_name = request.form.get("full_name", "").strip()
        address_line = request.form.get("address_line", "").strip()
        city = request.form.get("city", "").strip()
        postal_code = request.form.get("postal_code", "").strip()
        country = request.form.get("country", "").strip()
        notes = request.form.get("notes", "").strip()

        errors = []
        if not email or "@" not in email:
            errors.append("Valid email is required")
        if not full_name: errors.append("Full name is required")
        if not address_line: errors.append("Address is required")
        if not city: errors.append("City is required")
        if not postal_code: errors.append("Postal code is required")
        if not country: errors.append("Country is required")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "checkout.html",
                items=items, subtotal=subtotal, shipping=shipping, total=total,
                form=request.form
            )

        order = Order(
            user_id=current_user.id if current_user.is_authenticated else None,
            email=email, full_name=full_name,
            address_line=address_line, city=city, postal_code=postal_code,
            country=country, notes=notes,
            subtotal=subtotal, shipping=shipping, total=total,
            status="pending",
        )
        db.session.add(order)
        db.session.flush()

        for item in items:
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                product_name=item.product.name,
                product_price=item.product.price,
                quantity=item.quantity,
                line_total=round(item.product.price * item.quantity, 2),
            ))
            db.session.delete(item)

        db.session.commit()
        flash(f"Order #{order.id} placed — thank you!", "success")
        return redirect(url_for("main.order_confirmation", order_id=order.id))

    form = {}
    if current_user.is_authenticated:
        form["email"] = current_user.email

    return render_template(
        "checkout.html",
        items=items, subtotal=subtotal, shipping=shipping, total=total,
        form=form
    )


@bp.route("/order/<int:order_id>")
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("order_confirmation.html", order=order)
