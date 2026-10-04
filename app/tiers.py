"""
Tier auto-management engine.

Evaluates each wholesale partner's trailing revenue against their tier's requirement
and updates their tier_state. Does NOT auto-downgrade here (that's the apply step).
"""
from datetime import datetime, timedelta
from app import db
from app.models import Order, WholesaleAccount, Setting


# Tier hierarchy from lowest to highest
TIER_ORDER = ["new", "bronze", "silver", "gold"]


# ---------- Config ----------

def tier_requirements():
    def _get(key, default):
        raw = Setting.get(key)
        try:
            return float(raw) if raw is not None else default
        except (ValueError, TypeError):
            return default

    return {
        "new":    {"months": 1,  "amount": 0},
        "bronze": {"months": 3,  "amount": _get("TIER_BRONZE_AMOUNT", 300)},
        "silver": {"months": 6,  "amount": _get("TIER_SILVER_AMOUNT", 1000)},
        "gold":   {"months": 12, "amount": _get("TIER_GOLD_AMOUNT", 2500)},
    }


def tier_order_index(tier):
    tier = (tier or "new").lower()
    return TIER_ORDER.index(tier) if tier in TIER_ORDER else 0


def next_tier_up(tier):
    idx = tier_order_index(tier)
    return TIER_ORDER[idx + 1] if idx + 1 < len(TIER_ORDER) else tier


def next_tier_down(tier):
    idx = tier_order_index(tier)
    return TIER_ORDER[idx - 1] if idx > 0 else tier


# ---------- Revenue math ----------

def partner_revenue(account, months):
    if not months:
        return 0.0
    cutoff = datetime.utcnow() - timedelta(days=months * 30)
    rows = (Order.query
            .filter(Order.wholesale_id == account.id)
            .filter(Order.created_at >= cutoff)
            .filter(Order.status != "cancelled")
            .all())
    return round(sum(o.total for o in rows), 2)


def partner_revenue_series(account, months=12):
    buckets = {}
    now = datetime.utcnow()
    for i in range(months - 1, -1, -1):
        d = now - timedelta(days=i * 30)
        buckets[d.strftime("%Y-%m")] = 0.0
    cutoff = now - timedelta(days=months * 30)
    rows = (Order.query
            .filter(Order.wholesale_id == account.id)
            .filter(Order.created_at >= cutoff)
            .filter(Order.status != "cancelled")
            .all())
    for o in rows:
        k = o.created_at.strftime("%Y-%m")
        if k in buckets:
            buckets[k] += o.total
    return list(buckets.items())


# ---------- Evaluation ----------

def evaluate_account(account):
    reqs = tier_requirements()
    tier = (account.tier or "new").lower()
    req = reqs.get(tier, {"months": 1, "amount": 0})

    if tier == "new" or req["amount"] == 0:
        return {
            "tier": tier,
            "requirement": req,
            "actual_revenue": partner_revenue(account, req["months"]),
            "meets": True,
            "state_before": account.tier_state,
            "state_after": "ok",
            "action": "none",
        }

    actual = partner_revenue(account, req["months"])
    meets = actual >= req["amount"]
    state_before = account.tier_state or "ok"

    if meets:
        state_after = "ok"
        action = "reset" if state_before != "ok" else "none"
    else:
        missed = (account.tier_missed_months or 0) + 1
        if missed >= 6:
            state_after = "terminate"
            action = "terminate_eligible"
        elif missed >= 3:
            state_after = "downgrade"
            action = "downgrade_eligible"
        elif missed == 2:
            state_after = "grace"
            action = "grace"
        else:
            state_after = "warn"
            action = "warn"

    return {
        "tier": tier,
        "requirement": req,
        "actual_revenue": actual,
        "meets": meets,
        "state_before": state_before,
        "state_after": state_after,
        "action": action,
    }


def evaluate_all(dry_run=False):
    accounts = WholesaleAccount.query.filter_by(status="approved").all()
    results = []
    now = datetime.utcnow()

    for acct in accounts:
        if acct.tier_locked:
            results.append({"account": acct, "skipped": True, "reason": "tier_locked"})
            continue

        r = evaluate_account(acct)
        r["account"] = acct
        r["skipped"] = False

        if not dry_run:
            if r["meets"]:
                acct.tier_missed_months = 0
                if acct.tier_state != "ok":
                    acct.tier_state = "ok"
                    acct.tier_state_since = now
            else:
                acct.tier_missed_months = (acct.tier_missed_months or 0) + 1
                if acct.tier_state != r["state_after"]:
                    prev_state = acct.tier_state
                    acct.tier_state = r["state_after"]
                    acct.tier_state_since = now
                    # Notify on state change (only when worsening)
                    try:
                        from app.mail import send_tier_state_change
                        send_tier_state_change(acct, prev_state, r["state_after"])
                    except Exception:
                        pass
            acct.tier_last_evaluated_at = now
        results.append(r)

    if not dry_run:
        db.session.commit()
    return results


# ---------- Apply (used by admin action) ----------

def apply_downgrade(account):
    old_tier = (account.tier or "new").lower()
    new_tier = next_tier_down(old_tier)
    if new_tier == old_tier:
        return None
    account.tier = new_tier
    account.tier_missed_months = 0
    account.tier_state = "ok"
    account.tier_state_since = datetime.utcnow()
    db.session.commit()

    # Notify
    try:
        from app.mail import send_tier_changed
        send_tier_changed(account, old_tier, new_tier)
    except Exception:
        pass

    return {"from": old_tier, "to": new_tier}


def apply_termination(account):
    old_tier = (account.tier or "new").lower()
    if old_tier == "new":
        return None
    account.tier = "new"
    account.tier_missed_months = 0
    account.tier_state = "ok"
    account.tier_state_since = datetime.utcnow()
    db.session.commit()

    try:
        from app.mail import send_tier_changed
        send_tier_changed(account, old_tier, "new")
    except Exception:
        pass

    return {"from": old_tier, "to": "new"}
