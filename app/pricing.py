"""
Pricing engine — retail, tier-based wholesale, and per-partner overrides.

Order of precedence (highest first):
  1. Per-partner override in WholesalePrice for the given product
  2. Tier discount (standard / bronze / silver / gold)
  3. List price
"""
from app.models import Setting


DEFAULT_DISCOUNTS = {
    "standard": 5.0,
    "bronze":   10.0,
    "silver":   15.0,
    "gold":     20.0,
}


# ---------- Retail side (existing) ----------

def get_discount_percent(tier):
    tier = (tier or "standard").lower()
    key = f"WHOLESALE_DISCOUNT_{tier.upper()}"
    raw = Setting.get(key)
    if raw is not None:
        try:
            return max(0.0, min(90.0, float(raw)))
        except (ValueError, TypeError):
            pass
    return DEFAULT_DISCOUNTS.get(tier, 0.0)


def is_wholesale_user(user):
    """Legacy: retail User flagged as wholesale (kept for compat)."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_wholesale", False)
        and getattr(user, "wholesale_status", "") == "approved"
    )


def price_for(user, product):
    """Retail User + Product → effective price (wholesale-aware via User flags)."""
    base = float(product.price or 0)
    if not is_wholesale_user(user):
        return round(base, 2)
    tier = getattr(user, "wholesale_tier", "standard")
    pct = get_discount_percent(tier)
    return round(base * (1 - pct / 100.0), 2)


def discount_for(user):
    if not is_wholesale_user(user):
        return 0.0
    return get_discount_percent(getattr(user, "wholesale_tier", "standard"))


# ---------- Wholesale account side ----------

def override_for(wholesale_account, product):
    """Return (price, min_quantity, notes) if there's a custom override, else None."""
    if not wholesale_account:
        return None
    from app.models import WholesalePrice
    row = WholesalePrice.query.filter_by(
        wholesale_id=wholesale_account.id,
        product_id=product.id,
    ).first()
    if not row:
        return None
    return {
        "price": float(row.price),
        "min_quantity": int(row.min_quantity or 1),
        "notes": row.notes,
    }


def wholesale_price_for(wholesale_account, product):
    """
    Effective price for a wholesale partner + product.

    Priority (highest first):
      1. Per-product override (WholesalePrice)
      2. Partner's custom blanket discount % (WholesaleAccount.custom_discount_pct)
      3. Tier discount (standard / bronze / silver / gold)
      4. List price

    Returns dict: price, list_price, source ('override' | 'custom' | 'tier' | 'list'),
                  discount_pct, min_quantity, notes.
    """
    base = float(product.price or 0)
    if not wholesale_account:
        return {
            "price": round(base, 2),
            "list_price": round(base, 2),
            "source": "list",
            "discount_pct": 0.0,
            "min_quantity": 1,
            "notes": None,
        }

    # 1. Per-product override
    override = override_for(wholesale_account, product)
    if override:
        return {
            "price": round(override["price"], 2),
            "list_price": round(base, 2),
            "source": "override",
            "discount_pct": round((1 - override["price"] / base) * 100.0, 1) if base > 0 else 0.0,
            "min_quantity": max(1, int(override.get("min_quantity") or get_default_moq() if moq_enforced() else 1)),
            "notes": override["notes"],
        }

    # 2. Partner's blanket custom discount
    custom_pct = getattr(wholesale_account, "custom_discount_pct", None)
    if custom_pct is not None:
        try:
            pct = max(0.0, min(90.0, float(custom_pct)))
            return {
                "price": round(base * (1 - pct / 100.0), 2),
                "list_price": round(base, 2),
                "source": "custom",
                "discount_pct": pct,
                "min_quantity": get_default_moq() if moq_enforced() else 1,
                "notes": None,
            }
        except (ValueError, TypeError):
            pass

    # 3. Tier
    tier = getattr(wholesale_account, "tier", "standard") or "standard"
    pct = get_discount_percent(tier)
    return {
        "price": round(base * (1 - pct / 100.0), 2),
        "list_price": round(base, 2),
        "source": "tier",
        "discount_pct": pct,
        "min_quantity": get_default_moq() if moq_enforced() else 1,
        "notes": None,
    }


# ---------- Wholesale MOQ ----------

def get_default_moq():
    """Global default minimum order quantity for wholesale orders."""
    raw = Setting.get("WHOLESALE_MOQ_DEFAULT")
    try:
        v = int(raw) if raw is not None else 10
        return max(1, v)
    except (ValueError, TypeError):
        return 10


def moq_enforced():
    raw = Setting.get("WHOLESALE_MOQ_ENFORCE")
    if raw is None:
        return True   # enforced by default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def effective_moq(wholesale_account, product):
    """
    Minimum order quantity for a partner buying a product.
    Priority:
      1. Per-product override's min_quantity (if set)
      2. Global default MOQ (if enforcement is on)
      3. 1 (no minimum)
    """
    if not moq_enforced():
        return 1

    override = override_for(wholesale_account, product) if wholesale_account else None
    if override and override.get("min_quantity"):
        return max(1, int(override["min_quantity"]))

    return get_default_moq()
