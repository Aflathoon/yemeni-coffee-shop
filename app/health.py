"""
Health check battery.

Each check returns:
    {name, status, message, detail, meta}
status ∈ {"ok", "warn", "fail"}
"""
import os
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app
from app import db


# ---------- Individual checks ----------

def check_app_imports():
    """Verify core modules load cleanly."""
    name = "app_imports"
    try:
        # In-process check — we already imported successfully to get here
        from app.models import Product, User, Order, OrderItem, CartItem, Post, Article, Campaign, AiAlert
        from app.main import routes as main_routes
        from app.admin import routes as admin_routes
        from app.auth import routes as auth_routes
        from app.wholesale import auth as ws_auth
        from app.blog import routes as blog_routes
        return {"name": name, "status": "ok", "message": "All modules load", "detail": None}
    except Exception as e:
        return {
            "name": name, "status": "fail",
            "message": f"Import error: {type(e).__name__}",
            "detail": traceback.format_exc(),
        }


def check_db_schema():
    """Compare model columns against actual SQLite schema."""
    name = "db_schema"
    try:
        from sqlalchemy import inspect
        insp = inspect(db.engine)
        models = ["User", "Product", "Order", "OrderItem", "CartItem", "Post",
                  "Article", "Setting", "WholesaleAccount", "WholesalePrice",
                  "Campaign", "CampaignPartner", "CampaignProduct", "AiAlert"]
        import app.models as m
        drift = {}
        for model_name in models:
            model = getattr(m, model_name, None)
            if not model:
                continue
            table = model.__tablename__
            if not insp.has_table(table):
                drift[table] = {"missing_table": True}
                continue
            model_cols = {c.name for c in model.__table__.columns}
            db_cols = {c["name"] for c in insp.get_columns(table)}
            missing = model_cols - db_cols
            if missing:
                drift[table] = {"missing_columns": sorted(missing)}

        if not drift:
            return {"name": name, "status": "ok", "message": "Schema in sync", "detail": None}
        return {
            "name": name, "status": "fail",
            "message": f"{len(drift)} table(s) with drift",
            "detail": "\n".join(f"  {t}: {d}" for t, d in drift.items()),
            "meta": drift,
        }
    except Exception as e:
        return {"name": name, "status": "fail", "message": f"Check errored: {e}", "detail": traceback.format_exc()}


def check_templates_parse():
    """Ensure every Jinja template compiles without syntax error."""
    name = "templates_parse"
    try:
        env = current_app.jinja_env
        # Walk templates dir
        tmpl_dir = Path(current_app.template_folder or "templates")
        if not tmpl_dir.is_absolute():
            tmpl_dir = Path(current_app.root_path) / tmpl_dir
        broken = []
        for f in tmpl_dir.rglob("*.html"):
            rel = f.relative_to(tmpl_dir).as_posix()
            try:
                env.get_template(rel)
            except Exception as e:
                broken.append((rel, str(e)[:200]))

        if not broken:
            return {"name": name, "status": "ok", "message": "All templates parse", "detail": None}
        return {
            "name": name, "status": "fail",
            "message": f"{len(broken)} template(s) with syntax error",
            "detail": "\n".join(f"  {f}: {err}" for f, err in broken[:10]),
            "meta": broken[:10],
        }
    except Exception as e:
        return {"name": name, "status": "fail", "message": f"Check errored: {e}", "detail": traceback.format_exc()}


def check_public_routes():
    """Smoke-test the key public routes."""
    name = "public_routes"
    urls = ["/", "/blog/", "/offers", "/wholesale/"]
    results = []
    worst = "ok"
    try:
        client = current_app.test_client()
        for u in urls:
            t0 = time.time()
            try:
                r = client.get(u, follow_redirects=False)
                ms = int((time.time() - t0) * 1000)
                code = r.status_code
                status = "ok" if code < 400 else ("warn" if code < 500 else "fail")
                results.append({"url": u, "code": code, "ms": ms, "status": status})
                if status == "fail":
                    worst = "fail"
                elif status == "warn" and worst == "ok":
                    worst = "warn"
            except Exception as e:
                results.append({"url": u, "error": str(e)[:200], "status": "fail"})
                worst = "fail"

        if worst == "ok":
            return {"name": name, "status": "ok", "message": f"All {len(urls)} public routes OK", "detail": None, "meta": results}
        failures = [r for r in results if r["status"] == "fail"]
        warns = [r for r in results if r["status"] == "warn"]
        detail_lines = []
        for r in results:
            if r["status"] != "ok":
                detail_lines.append(f"  {r['url']}: {r.get('code', r.get('error', '?'))}")
        return {
            "name": name,
            "status": worst,
            "message": f"{len(failures)} failing · {len(warns)} warning",
            "detail": "\n".join(detail_lines) if detail_lines else None,
            "meta": results,
        }
    except Exception as e:
        return {"name": name, "status": "fail", "message": f"Check errored: {e}", "detail": traceback.format_exc()}


def check_recent_errors():
    """Read the Flask debug log (if present) for recent 500 responses."""
    from app.models import AiAlert

    name = "recent_errors"
    candidates = [
        Path("instance/logs/errors.log"),
        Path("instance/error.log"),
        Path("/tmp/flask-error.log"),
    ]
    log_file = next((p for p in candidates if p.exists()), None)

    # Fallback: query AiAlert history for recent failures
    try:
        since = datetime.utcnow() - timedelta(hours=24)
        recent = AiAlert.query.filter(AiAlert.created_at >= since, AiAlert.status.in_(("warn", "fail"))).count()
        if recent > 0:
            return {
                "name": name, "status": "warn",
                "message": f"{recent} alert(s) logged in the last 24h",
                "detail": "See /admin/assistant for the list.",
            }
        if log_file:
            # Rough 500 count
            text = log_file.read_text(errors="ignore")[-200000:]
            count_500 = text.count(" 500 -")
            if count_500 > 0:
                return {
                    "name": name, "status": "warn" if count_500 < 5 else "fail",
                    "message": f"{count_500} HTTP 500 response(s) in recent log",
                    "detail": f"Source: {log_file}",
                }
        return {"name": name, "status": "ok", "message": "No recent errors", "detail": None}
    except Exception as e:
        return {"name": name, "status": "warn", "message": f"Could not read logs: {e}", "detail": None}


def check_disk_space():
    """Check available disk space and DB size."""
    name = "disk_space"
    try:
        import shutil
        total, used, free = shutil.disk_usage(".")
        free_gb = free / (1024 ** 3)
        used_pct = (used / total) * 100

        # DB size
        db_path = Path("instance/shop.db")
        db_mb = db_path.stat().st_size / (1024 ** 2) if db_path.exists() else 0

        if free_gb < 1:
            status = "fail"
        elif free_gb < 5 or used_pct > 90:
            status = "warn"
        else:
            status = "ok"

        return {
            "name": name, "status": status,
            "message": f"{free_gb:.1f} GB free · DB {db_mb:.1f} MB",
            "detail": None,
            "meta": {"free_gb": round(free_gb, 2), "used_pct": round(used_pct, 1), "db_mb": round(db_mb, 2)},
        }
    except Exception as e:
        return {"name": name, "status": "warn", "message": f"Check errored: {e}", "detail": None}


# ---------- Runner ----------

ALL_CHECKS = [
    check_app_imports,
    check_db_schema,
    check_templates_parse,
    check_public_routes,
    check_recent_errors,
    check_disk_space,
]


def run_all_checks():
    """Run every health check. Returns list of results."""
    out = []
    for fn in ALL_CHECKS:
        try:
            out.append(fn())
        except Exception as e:
            out.append({
                "name": fn.__name__, "status": "fail",
                "message": f"Uncaught: {e}", "detail": traceback.format_exc(),
            })
    return out


def summarize(results):
    """Return a small summary dict."""
    ok = sum(1 for r in results if r["status"] == "ok")
    warn = sum(1 for r in results if r["status"] == "warn")
    fail = sum(1 for r in results if r["status"] == "fail")
    return {"ok": ok, "warn": warn, "fail": fail, "total": len(results)}
