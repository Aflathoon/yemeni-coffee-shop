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

    return render_template(
        "wholesale/dashboard.html",
        acct=acct,
        total_orders=total_orders,
        total_spend=total_spend,
        recent_orders=recent_orders,
        discount=discount,
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
