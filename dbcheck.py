#!/usr/bin/env python3
"""Compare model columns vs actual DB columns. Report drift."""
from app import create_app
from app import db as _db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    insp = inspect(_db.engine)
    drift_found = False
    for model_name in ("User", "Product", "Order", "OrderItem", "CartItem", "Post", "Article", "Setting"):
        try:
            model = getattr(__import__("app.models", fromlist=[model_name]), model_name)
        except AttributeError:
            continue
        table = model.__tablename__
        if not insp.has_table(table):
            print(f"❌ table '{table}' missing")
            drift_found = True
            continue
        model_cols = {c.name for c in model.__table__.columns}
        db_cols = {c["name"] for c in insp.get_columns(table)}
        missing_in_db = model_cols - db_cols
        extra_in_db = db_cols - model_cols
        if missing_in_db or extra_in_db:
            drift_found = True
            print(f"⚠ {table}:")
            if missing_in_db: print(f"    missing in DB: {sorted(missing_in_db)}")
            if extra_in_db: print(f"    extra in DB: {sorted(extra_in_db)}")
    if not drift_found:
        print("✅ No schema drift detected")
