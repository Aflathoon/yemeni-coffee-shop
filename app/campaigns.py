"""
Campaign engine — matching, applying, and effective price calculation.

A campaign is only "live for a partner" if:
  1. It's published
  2. Today is within [starts_at, ends_at]
  3. Channel matches the partner (wholesale)
  4. Tier matches (if tiers_json is set)
  5. Specific partner matches (if any CampaignPartner links exist)
  6. Activity filter passes (if activity_days is set)
  7. Minimum order value/qty passes (if set)

A campaign is only "in scope for a product" if:
  - scope == 'all', OR
  - scope == 'category' AND product.category in scope_categories, OR
  - scope == 'products' AND product is in CampaignProduct links
"""
from datetime import datetime, timedelta
from app.models import Campaign, CampaignPartner, CampaignProduct, Order


# ---------- Fetching ----------

def active_campaigns():
    """All published campaigns currently within their window."""
    now = datetime.utcnow()
    return (Campaign.query
            .filter(Campaign.published == True)
            .filter(Campaign.starts_at <= now)
            .filter(Campaign.ends_at >= now)
            .all())


# ---------- Matching ----------

def _tier_matches(campaign, account):
    """Check tier eligibility."""
    if not campaign.tiers_json:
        return True
    allowed = [t.lower() for t in campaign.get_tiers()]
    if not allowed:
        return True
    return (account.tier or "standard").lower() in allowed


def _partner_matches(campaign, account):
    """Check if partner is on the specific-partner allowlist (if any)."""
    links = CampaignPartner.query.filter_by(campaign_id=campaign.id).all()
    if not links:
        return True   # no allowlist = everyone in the tier set
    return any(l.wholesale_id == account.id for l in links)


def _activity_matches(campaign, account):
    """Check if the partner has ordered recently enough."""
    if not campaign.activity_days:
        return True
    cutoff = datetime.utcnow() - timedelta(days=campaign.activity_days)
    last_order = (Order.query
                  .filter(Order.wholesale_id == account.id)
                  .order_by(Order.created_at.desc())
                  .first())
    if not last_order:
        return False
    return last_order.created_at >= cutoff


def _product_in_scope(campaign, product):
    """Check if a product falls within a campaign's scope."""
    if campaign.scope == "all":
        return True
    if campaign.scope == "category":
        cats = [c.lower() for c in campaign.get_scope_categories()]
        return (product.category or "").lower() in cats
    if campaign.scope == "products":
        return CampaignProduct.query.filter_by(
            campaign_id=campaign.id, product_id=product.id
        ).first() is not None
    return False


def _order_value_matches(campaign, cart_total=None, cart_qty=None):
    """Check min order value/qty. If cart not supplied, assume it passes (single product view)."""
    if campaign.min_order_value and cart_total is not None:
        if cart_total < campaign.min_order_value:
            return False
    if campaign.min_order_qty and cart_qty is not None:
        if cart_qty < campaign.min_order_qty:
            return False
    return True


# ---------- Public API ----------

def campaigns_for(wholesale_account, product, cart_total=None, cart_qty=None):
    """
    Return live campaigns that apply to this partner + product.
    Order: newest first.
    """
    if not wholesale_account:
        return []
    live = active_campaigns()
    matched = []
    for c in live:
        if c.channel == "retail":
            continue
        if c.channel not in ("wholesale", "both"):
            continue
        if not _tier_matches(c, wholesale_account):
            continue
        if not _partner_matches(c, wholesale_account):
            continue
        if not _activity_matches(c, wholesale_account):
            continue
        if not _product_in_scope(c, product):
            continue
        if not _order_value_matches(c, cart_total, cart_qty):
            continue
        matched.append(c)
    matched.sort(key=lambda c: c.starts_at, reverse=True)
    return matched


# ---------- Retail ----------

def retail_campaigns_for(product, cart_total=None, cart_qty=None):
    """
    Return live campaigns that apply to retail visitors for a given product.
    Retail doesn't have tiers/partner targeting — channel is the only filter.
    """
    live = active_campaigns()
    matched = []
    for c in live:
        if c.channel == "wholesale":
            continue
        if c.channel not in ("retail", "both"):
            continue
        if not _product_in_scope(c, product):
            continue
        if not _order_value_matches(c, cart_total, cart_qty):
            continue
        matched.append(c)
    matched.sort(key=lambda c: c.starts_at, reverse=True)
    return matched


def apply_retail_campaigns(base_price, product, cart_total=None, cart_qty=None):
    """
    Apply campaigns to a retail price.
    Returns dict similar to apply_campaigns() but no tier scaling.
    """
    from app.pricing import clamp_to_floor

    matches = retail_campaigns_for(product, cart_total, cart_qty)
    if not matches:
        return {
            "final_price": round(float(base_price), 2),
            "campaign_discount": 0.0,
            "campaigns": [],
            "labels": [],
            "floor_clamped": False,
        }

    override_c = next((c for c in matches if c.override_pricing), None)
    running_price = float(base_price)
    total_discount = 0.0
    labels = []

    if override_c:
        # Retail override: percent/fixed directly
        if override_c.discount_type == "percent":
            amount = running_price * (override_c.discount_value or 0) / 100.0
            running_price -= amount
            total_discount += amount
            labels.append(f"−{override_c.discount_value}% ({override_c.name})")
        elif override_c.discount_type == "fixed":
            amount = min(float(override_c.discount_value or 0), running_price)
            running_price -= amount
            total_discount += amount
            labels.append(f"−${amount:.2f} ({override_c.name})")
        matches = [override_c]
    else:
        for c in matches:
            if c.discount_type == "percent":
                amount = running_price * (c.discount_value or 0) / 100.0
                running_price -= amount
                total_discount += amount
                labels.append(f"−{c.discount_value}% ({c.name})")
            elif c.discount_type == "fixed":
                amount = min(float(c.discount_value or 0), running_price)
                running_price -= amount
                total_discount += amount
                labels.append(f"−${amount:.2f} ({c.name})")

    final_price, clamped = clamp_to_floor(product, running_price)
    actual_discount = round(float(base_price) - final_price, 2) if clamped else round(total_discount, 2)

    return {
        "final_price": round(final_price, 2),
        "campaign_discount": actual_discount,
        "campaigns": matches,
        "labels": labels,
        "floor_clamped": clamped,
    }


def active_retail_campaigns():
    """All live retail-eligible campaigns (regardless of product)."""
    live = active_campaigns()
    return [c for c in live if c.channel in ("retail", "both")]


def campaign_discount_for(campaign, account, base_price):
    """
    Compute the discount amount for a campaign applied to base_price.
    Returns (discount_amount, discount_label).

    Tier scaling: if campaign.tier_scaling_json has an entry for the account's tier,
    that % is used instead of campaign.discount_value (for percent campaigns).
    """
    dtype = campaign.discount_type or "percent"

    if dtype == "freeship":
        return 0.0, "Free shipping"

    if dtype == "percent":
        pct = float(campaign.discount_value or 0)
        scaling = campaign.get_tier_scaling()
        tier_key = (account.tier or "").lower()
        if tier_key and tier_key in scaling:
            pct = float(scaling[tier_key])
        amount = base_price * (pct / 100.0)
        return round(amount, 2), f"−{pct}% ({campaign.name})"

    if dtype == "fixed":
        amount = float(campaign.discount_value or 0)
        # Don't go negative
        amount = min(amount, base_price)
        return round(amount, 2), f"−${amount:.2f} ({campaign.name})"

    return 0.0, ""


def apply_campaigns(base_price, account, product, cart_total=None, cart_qty=None):
    """
    Apply all matching campaigns to a base price.

    Returns dict:
      final_price       — price after campaigns + floor
      campaign_discount — total discount applied by campaigns
      campaigns         — list of matching Campaign objects
      labels            — human-readable discount labels
      floor_clamped     — True if floor bit
    """
    from app.pricing import clamp_to_floor

    matches = campaigns_for(account, product, cart_total, cart_qty)
    if not matches:
        return {
            "final_price": round(float(base_price), 2),
            "campaign_discount": 0.0,
            "campaigns": [],
            "labels": [],
            "floor_clamped": False,
        }

    # If any campaign is override_pricing, use the first such one (newest).
    override_c = next((c for c in matches if c.override_pricing), None)

    running_price = float(base_price)
    total_discount = 0.0
    labels = []

    if override_c:
        # Only apply override campaign — skip the stacked ones
        discount, label = campaign_discount_for(override_c, account, running_price)
        running_price -= discount
        total_discount += discount
        if label:
            labels.append(label)
        matches = [override_c]
    else:
        for c in matches:
            discount, label = campaign_discount_for(c, account, running_price)
            if discount <= 0:
                continue
            running_price -= discount
            total_discount += discount
            if label:
                labels.append(label)

    # Floor
    final_price, clamped = clamp_to_floor(product, running_price)

    # If floor kicked in, the actual discount is less than computed
    if clamped:
        actual_discount = round(float(base_price) - final_price, 2)
    else:
        actual_discount = round(total_discount, 2)

    return {
        "final_price": round(final_price, 2),
        "campaign_discount": actual_discount,
        "campaigns": matches,
        "labels": labels,
        "floor_clamped": clamped,
    }
