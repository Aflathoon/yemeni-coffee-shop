"""Wholesale dashboard: overview for logged-in partners."""
from flask import render_template, redirect, url_for, request, flash
from sqlalchemy import func
from app.wholesale import bp
from app import db
from app.wholesale.session import wholesale_required, current_wholesale


@bp.route("/dashboard")
@wholesale_required
def dashboard():
    acct = current_wholesale()

    # Stats (empty for now — orders come in Patch 10.5)
    # We compute from Order table if any exist with this wholesale_id
    from app.models import Order

    total_orders = Order.query.filter_by(wholesale_id=acct.id).count()
    rows = db.session.query(func.sum(Order.total)).filter(Order.wholesale_id == acct.id).first()
    total_spend = float(rows[0] or 0) if rows else 0.0
    recent_orders = (Order.query.filter_by(wholesale_id=acct.id)
                     .order_by(Order.created_at.desc()).limit(5).all())

    discount = 0.0
    if acct.is_approved:
        from app.pricing import get_discount_percent
        discount = get_discount_percent(acct.tier)

    # Count active campaigns that apply to this partner
    active_campaign_count = 0
    try:
        from app.models import Product
        from app.campaigns import campaigns_for
        seen = set()
        # Sample the first 20 products to see which campaigns match
        for prod in Product.query.filter_by(active=True).limit(20).all():
            for c in campaigns_for(acct, prod):
                seen.add(c.id)
        active_campaign_count = len(seen)
    except Exception:
        pass

    return render_template(
        "wholesale/dashboard.html",
        acct=acct,
        total_orders=total_orders,
        total_spend=total_spend,
        recent_orders=recent_orders,
        discount=discount,
        active_campaign_count=active_campaign_count,
    )


@bp.route("/orders")
@wholesale_required
def orders():
    """Full order history for this partner."""
    from app.models import Order
    acct = current_wholesale()
    if not acct.is_approved:
        flash("Order history is available once your account is approved.", "warning")
        return redirect(url_for("wholesale.dashboard"))
    all_orders = (Order.query
                  .filter_by(wholesale_id=acct.id)
                  .order_by(Order.created_at.desc()).all())
    return render_template("wholesale/orders.html", acct=acct, orders=all_orders)


@bp.route("/orders/<int:order_id>")
@wholesale_required
def order_detail(order_id):
    """Single order view."""
    from app.models import Order
    acct = current_wholesale()
    order = Order.query.get_or_404(order_id)
    if order.wholesale_id != acct.id:
        flash("That order isn't yours.", "error")
        return redirect(url_for("wholesale.orders"))
    return render_template("wholesale/order_detail.html", acct=acct, order=order)


@bp.route("/orders/<int:order_id>/reorder", methods=["POST"])
@wholesale_required
def order_reorder(order_id):
    """Add all items from a past order back to the cart."""
    from app.models import Order, CartItem, Product
    acct = current_wholesale()
    order = Order.query.get_or_404(order_id)
    if order.wholesale_id != acct.id:
        flash("That order isn't yours.", "error")
        return redirect(url_for("wholesale.orders"))

    added = 0
    for item in order.items:
        product = Product.query.get(item.product_id)
        if not product or not product.active:
            continue
        existing = CartItem.query.filter_by(
            wholesale_id=acct.id, product_id=product.id
        ).first()
        if existing:
            existing.quantity += item.quantity
        else:
            db.session.add(CartItem(
                wholesale_id=acct.id,
                product_id=product.id,
                quantity=item.quantity,
            ))
        added += 1
    db.session.commit()
    flash(f"Added {added} item(s) from order #{order.id} to your cart.", "success")
    return redirect(url_for("wholesale.cart_view"))


@bp.route("/price-list")
@wholesale_required
def price_list():
    """CSV download of all products at this account's tier pricing."""
    import csv
    import io
    from flask import Response
    from app.models import Product
    from app.pricing import get_discount_percent

    acct = current_wholesale()
    if not acct.is_approved:
        flash("Price list is available once your account is approved.", "warning")
        return redirect(url_for("wholesale.dashboard"))

    discount = get_discount_percent(acct.tier) / 100.0
    products = Product.query.filter_by(active=True).order_by(Product.category, Product.name).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["SKU", "Name", "Category", "Origin", "Unit",
                "List price (USD)", f"Your price ({acct.tier}, {int(discount*100)}% off)", "Stock"])
    for p in products:
        your_price = round(p.price * (1 - discount), 2)
        w.writerow([
            p.slug, p.name, p.category, p.origin_country or "",
            f"{p.unit_quantity or 1} {p.unit or 'g'}",
            f"{p.price:.2f}", f"{your_price:.2f}", p.stock,
        ])
    csv_data = buf.getvalue()

    filename = f"spice-and-roast-pricelist-{acct.tier}-{acct.id}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.route("/account", methods=["GET", "POST"])
@wholesale_required
def account():
    """View / edit partner account details."""
    acct = current_wholesale()

    if request.method == "POST":
        acct.company_name = request.form.get("company_name", "").strip() or acct.company_name
        acct.business_type = request.form.get("business_type", "").strip() or acct.business_type
        acct.tax_id = request.form.get("tax_id", "").strip() or None
        acct.phone = request.form.get("phone", "").strip() or None
        acct.address_line = request.form.get("address_line", "").strip() or None
        acct.city = request.form.get("city", "").strip() or None
        acct.postal_code = request.form.get("postal_code", "").strip() or None
        acct.country = request.form.get("country", "").strip() or None
        db.session.commit()
        flash("Account updated.", "success")
        return redirect(url_for("wholesale.account"))

    return render_template("wholesale/account.html", acct=acct)


# ---------- Partner-facing campaigns ----------

@bp.route("/campaigns")
@wholesale_required
def campaigns():
    """List active + upcoming campaigns that apply to this partner."""
    from datetime import datetime, timedelta
    from app.models import Campaign, Product, Order
    from app.campaigns import campaigns_for

    acct = current_wholesale()

    # Current campaign window: published, not expired
    now = datetime.utcnow()

    # We can only know if a campaign applies to a partner by evaluating
    # against their products. Since campaigns have scope filters, we look
    # at the whole active catalog and collect distinct campaigns.
    products = Product.query.filter_by(active=True).all()
    seen_ids = set()
    live_list = []
    upcoming_list = []

    for c in Campaign.query.filter_by(published=True).order_by(Campaign.starts_at.desc()).all():
        if c.id in seen_ids:
            continue
        # Does it apply to this partner at all? Test against at least one in-scope product
        applies = False
        for p in products:
            if c in campaigns_for(acct, p):
                applies = True
                break
        if not applies:
            continue
        seen_ids.add(c.id)
        if c.is_live():
            live_list.append(c)
        elif c.is_upcoming():
            upcoming_list.append(c)

    # Sample product for each live campaign (for showing "savings on..." hint)
    def sample_product(c):
        for p in products:
            if c.scope == "all":
                return p
            if c.scope == "category" and (p.category or "").lower() in [x.lower() for x in c.get_scope_categories()]:
                return p
            if c.scope == "products":
                from app.models import CampaignProduct
                if CampaignProduct.query.filter_by(campaign_id=c.id, product_id=p.id).first():
                    return p
        return None

    live_samples = {c.id: sample_product(c) for c in live_list}
    upcoming_samples = {c.id: sample_product(c) for c in upcoming_list}

    # Days remaining for each live campaign
    def days_left(c):
        return max(0, (c.ends_at - now).days)

    return render_template(
        "wholesale/campaigns.html",
        acct=acct,
        live=live_list,
        upcoming=upcoming_list,
        live_samples=live_samples,
        upcoming_samples=upcoming_samples,
        days_left=days_left,
        now=now,
    )
