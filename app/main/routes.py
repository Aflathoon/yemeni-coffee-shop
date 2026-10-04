import secrets
from flask import (
    render_template, jsonify, request, session, redirect,
    url_for, flash
)
from flask_babel import gettext as _
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
    from app.pricing import price_for
    from flask_login import current_user
    total = 0.0
    for item in get_cart_items():
        unit = price_for(current_user, item.product)
        total += unit * item.quantity
    return round(total, 2)


def shipping_for(subtotal):
    return 0.0 if subtotal >= 100.0 else (8.0 if subtotal > 0 else 0.0)


# ---------- Catalog ----------

@bp.route("/")
def index():
    category = request.args.get("category")
    country = request.args.get("country")
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "newest").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.args.get("per_page", 24))
        if per_page not in (12, 24, 48, 96, 200):
            per_page = 24
    except (ValueError, TypeError):
        per_page = 24

    base_q = Product.query.filter_by(active=True)
    if category:
        base_q = base_q.filter_by(category=category)
    if country:
        base_q = base_q.filter_by(origin_country=country)
    if search:
        like = f"%{search}%"
        base_q = base_q.filter(
            (Product.name.ilike(like))
            | (Product.short_desc.ilike(like))
            | (Product.description.ilike(like))
            | (Product.origin_country.ilike(like))
            | (Product.tags.ilike(like))
        )

    total_count = base_q.count()

    if sort == "price_asc":
        base_q = base_q.order_by(Product.price.asc())
    elif sort == "price_desc":
        base_q = base_q.order_by(Product.price.desc())
    elif sort == "name":
        base_q = base_q.order_by(Product.name.asc())
    elif sort == "featured":
        base_q = base_q.order_by(Product.featured.desc(), Product.created_at.desc())
    else:
        sort = "newest"
        base_q = base_q.order_by(Product.created_at.desc())

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    products = base_q.offset(offset).limit(per_page).all()

    categories = db_categories(country_filter=country)
    countries = db_countries(category_filter=category)
    featured = Product.query.filter_by(featured=True).limit(5).all()

    page_numbers = _build_page_numbers(page, total_pages)
    is_unfiltered = not (category or country or search)

    return render_template(
        "index.html",
        products=products,
        categories=categories,
        countries=countries,
        featured=featured,
        active_category=category,
        active_country=country,
        search=search,
        sort=sort,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
        page_numbers=page_numbers,
        hero_products=hero_products(limit=6) if is_unfiltered and page == 1 else [],
        strip_products=strip_products(per_category=3) if is_unfiltered and page == 1 else [],
    )


def _build_page_numbers(current, total, window=2):
    """Return [1, '…', 4, 5, 6, '…', 124] for a pagination bar."""
    if total <= 1:
        return []
    if total <= 9:
        return list(range(1, total + 1))
    pages = {1, total}
    for p in range(max(2, current - window), min(total, current + window) + 1):
        pages.add(p)
    sorted_pages = sorted(pages)
    out = []
    last = 0
    for p in sorted_pages:
        if last and p - last > 1:
            out.append("…")
        out.append(p)
        last = p
    return out

def db_categories(country_filter=None):
    q = db.session.query(Product.category, func.count(Product.id)).filter(Product.active == True)
    if country_filter:
        q = q.filter(Product.origin_country == country_filter)
    rows = q.group_by(Product.category).order_by(Product.category).all()
    return [{"name": c, "count": n} for c, n in rows]


def db_countries(category_filter=None):
    q = db.session.query(Product.origin_country, func.count(Product.id))
    q = q.filter(Product.origin_country.isnot(None))
    q = q.filter(Product.active == True)
    if category_filter:
        q = q.filter(Product.category == category_filter)
    rows = q.group_by(Product.origin_country).order_by(Product.origin_country).all()
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
    flash(_("Added %(name)s to your cart", name=product.name), "success")
    return redirect(request.referrer or url_for("main.cart_view"))


@bp.route("/cart/update/<int:item_id>", methods=["POST"])
def cart_update(item_id):
    item = CartItem.query.get_or_404(item_id)
    if not _owns_item(item):
        return (_("Not your cart item"), 403)
    item.quantity = max(1, int(request.form.get("quantity", 1)))
    db.session.commit()
    flash(_("Cart updated"), "success")
    return redirect(url_for("main.cart_view"))


@bp.route("/cart/remove/<int:item_id>", methods=["POST"])
def cart_remove(item_id):
    item = CartItem.query.get_or_404(item_id)
    if not _owns_item(item):
        return ("Not your cart item", 403)
    db.session.delete(item)
    db.session.commit()
    flash(_("Item removed"), "success")
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
    flash(_("Cart cleared"), "success")
    return redirect(url_for("main.cart_view"))


# ---------- Checkout ----------

@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    items = get_cart_items()
    if not items:
        flash(_("Your cart is empty"), "warning")
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
            errors.append(_("Valid email is required"))
        if not full_name: errors.append(_("Full name is required"))
        if not address_line: errors.append(_("Address is required"))
        if not city: errors.append(_("City is required"))
        if not postal_code: errors.append(_("Postal code is required"))
        if not country: errors.append(_("Country is required"))

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

        from app.pricing import price_for
        for item in items:
            unit = price_for(current_user, item.product)
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                product_name=item.product.name,
                product_price=unit,                       # snapshot the effective (tier) price
                quantity=item.quantity,
                line_total=round(unit * item.quantity, 2),
            ))
            db.session.delete(item)

        db.session.commit()
        flash(_("Order #%(id)s placed — thank you!", id=order.id), "success")
        return redirect(url_for("main.order_confirmation", order_id=order.id))

    form = {}
    if current_user.is_authenticated:
        form["email"] = current_user.email
        form["full_name"] = current_user.full_name or ""
        form["address_line"] = current_user.address_line or ""
        form["city"] = current_user.city or ""
        form["postal_code"] = current_user.postal_code or ""
        form["country"] = current_user.country or ""

    return render_template(
        "checkout.html",
        items=items, subtotal=subtotal, shipping=shipping, total=total,
        form=form
    )


@bp.route("/order/<int:order_id>")
def order_confirmation(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("order_confirmation.html", order=order)


# ---------- Retail offers page ----------

@bp.route("/offers")
def offers():
    """Public list of active retail campaigns."""
    from app.campaigns import active_retail_campaigns
    from app.models import Product, CampaignProduct

    campaigns = active_retail_campaigns()

    # For each campaign, find a sample of in-scope products (up to 4)
    samples = {}
    for c in campaigns:
        prods = []
        if c.scope == "all":
            prods = Product.query.filter_by(active=True).limit(4).all()
        elif c.scope == "category":
            cats = [x.lower() for x in c.get_scope_categories()]
            prods = (Product.query
                     .filter(Product.active == True)
                     .filter(Product.category.in_(cats))
                     .limit(4).all())
        elif c.scope == "products":
            ids = [cp.product_id for cp in CampaignProduct.query.filter_by(campaign_id=c.id).all()]
            if ids:
                prods = Product.query.filter(Product.id.in_(ids)).limit(4).all()
        samples[c.id] = prods

    return render_template("offers.html", campaigns=campaigns, samples=samples)


# ---------- Hero carousel ----------

def hero_products(limit=6):
    """
    Return a list of products for the homepage hero carousel.

    Priority:
      1. Products marked featured=True (up to limit)
      2. Bestsellers from the last 30 days (by quantity)
      3. Newest active products

    Deduplicated, capped at `limit`.
    """
    from datetime import datetime, timedelta
    from app.models import OrderItem, Order

    chosen = []
    chosen_ids = set()

    # 1. Featured
    featured = Product.query.filter_by(active=True, featured=True).limit(limit).all()
    for p in featured:
        if p.id not in chosen_ids:
            chosen.append(p)
            chosen_ids.add(p.id)

    # 2. Bestsellers (last 30 days)
    if len(chosen) < limit:
        cutoff = datetime.utcnow() - timedelta(days=30)
        rows = (
            db.session.query(
                OrderItem.product_id,
                func.sum(OrderItem.quantity).label("qty"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .filter(Order.created_at >= cutoff)
            .filter(Order.status != "cancelled")
            .group_by(OrderItem.product_id)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit * 2)
            .all()
        )
        for pid, qty in rows:
            if len(chosen) >= limit:
                break
            if pid in chosen_ids:
                continue
            p = Product.query.get(pid)
            if p and p.active:
                chosen.append(p)
                chosen_ids.add(p.id)

    # 3. Newest
    if len(chosen) < limit:
        newest = (Product.query
                  .filter_by(active=True)
                  .order_by(Product.created_at.desc())
                  .limit(limit * 2)
                  .all())
        for p in newest:
            if len(chosen) >= limit:
                break
            if p.id not in chosen_ids:
                chosen.append(p)
                chosen_ids.add(p.id)

    return chosen[:limit]


# ---------- Rolling strip under hero ----------

def strip_products(per_category=3, categories=None):
    """
    Return a spread of products across categories for the rolling marquee.
    Default: 3 per category (coffee, tea, spices, herbs, honey, accessories).
    """
    cats = categories or ["coffee", "tea", "spices", "herbs", "honey", "accessories"]
    out = []
    for c in cats:
        items = (Product.query
                 .filter_by(active=True, category=c)
                 .order_by(Product.featured.desc(), Product.created_at.desc())
                 .limit(per_category)
                 .all())
        out.extend(items)
    return out


# ---------- Dedicated category pages ----------

@bp.route("/shop/<category_slug>")
def category_page(category_slug):
    """Dedicated page for a single category with its own SEO + hero."""
    from app.categories import get_category, all_categories

    cat = get_category(category_slug)
    if not cat:
        from flask import abort
        abort(404)

    slug, meta = cat

    country = request.args.get("country")
    search = request.args.get("q", "").strip()
    sort = request.args.get("sort", "newest").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.args.get("per_page", 24))
        if per_page not in (12, 24, 48, 96, 200):
            per_page = 24
    except (ValueError, TypeError):
        per_page = 24

    base_q = Product.query.filter_by(active=True, category=slug)
    if country:
        base_q = base_q.filter_by(origin_country=country)
    if search:
        like = f"%{search}%"
        base_q = base_q.filter(
            (Product.name.ilike(like))
            | (Product.short_desc.ilike(like))
            | (Product.description.ilike(like))
            | (Product.tags.ilike(like))
        )

    total_count = base_q.count()

    if sort == "price_asc":
        base_q = base_q.order_by(Product.price.asc())
    elif sort == "price_desc":
        base_q = base_q.order_by(Product.price.desc())
    elif sort == "name":
        base_q = base_q.order_by(Product.name.asc())
    elif sort == "featured":
        base_q = base_q.order_by(Product.featured.desc(), Product.created_at.desc())
    else:
        sort = "newest"
        base_q = base_q.order_by(Product.created_at.desc())

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    products = base_q.offset(offset).limit(per_page).all()

    # Category-aware counts (only for this category)
    countries = db_countries(category_filter=slug)
    categories = db_categories()

    featured = Product.query.filter_by(featured=True, category=slug).limit(5).all()
    if not featured:
        featured = Product.query.filter_by(featured=True).limit(5).all()

    page_numbers = _build_page_numbers(page, total_pages)

    return render_template(
        "category.html",
        category_slug=slug,
        category=meta,
        all_categories=all_categories(),
        products=products,
        categories=categories,
        countries=countries,
        featured=featured,
        active_category=slug,
        active_country=country,
        search=search,
        sort=sort,
        page=page,
        per_page=per_page,
        total_count=total_count,
        total_pages=total_pages,
        page_numbers=page_numbers,
    )
