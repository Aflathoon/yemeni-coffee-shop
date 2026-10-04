"""
Campaign engine — matching, application, and effective price calculation.

Full implementation lands in Patch 4. This file is a stub for now.
"""
from app.models import Campaign


def active_campaigns():
    """Return all published campaigns that are currently within their window."""
    from datetime import datetime
    now = datetime.utcnow()
    return (Campaign.query
            .filter(Campaign.published == True)
            .filter(Campaign.starts_at <= now)
            .filter(Campaign.ends_at >= now)
            .all())


def campaigns_for(wholesale_account, product):
    """Stub: returns [] until Patch 4 wires up real matching."""
    return []
