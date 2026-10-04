"""
Wholesale pricing engine.

Approved wholesale users get a tier-based discount applied to every product.
Tier discounts are configured in /admin/settings (or default below).
"""
from app.models import Setting


DEFAULT_DISCOUNTS = {
    "standard": 5.0,
    "bronze":   10.0,
    "silver":   15.0,
    "gold":     20.0,
}


def get_discount_percent(tier):
    """Return the discount % for a tier, from Setting or default."""
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
    """True if the user is approved for wholesale pricing."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_wholesale", False)
        and getattr(user, "wholesale_status", "") == "approved"
    )


def price_for(user, product):
    """
    Return the effective price for a user + product.
    Wholesale users get their tier discount applied.
    """
    base = float(product.price or 0)
    if not is_wholesale_user(user):
        return round(base, 2)
    tier = getattr(user, "wholesale_tier", "standard")
    pct = get_discount_percent(tier)
    return round(base * (1 - pct / 100.0), 2)


def discount_for(user):
    """Return the current user's discount percent (0 if not wholesale)."""
    if not is_wholesale_user(user):
        return 0.0
    return get_discount_percent(getattr(user, "wholesale_tier", "standard"))
