"""Seed the DB and create the admin user. Idempotent — safe to re-run."""
from app import create_app, db
from app.models import User, Product
from app.seed_data import PRODUCTS
import re

app = create_app()
with app.app_context():
    # Create tables if they don't exist (safe if they do)
    db.create_all()

    # Seed products if empty
    if Product.query.count() == 0:
        def slugify(s):
            return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        for p in PRODUCTS:
            db.session.add(Product(
                name=p["name"], slug=slugify(p["name"]),
                category=p["category"], subcategory=p.get("subcategory"),
                origin_country=p.get("origin_country"), origin_region=p.get("origin_region"),
                description=p["description"], short_desc=p.get("short_desc"),
                price=p["price"], weight_grams=p.get("weight_grams", 100),
                image=p["image"], featured=p.get("featured", False),
            ))
        db.session.commit()
        print(f"✅ Seeded {len(PRODUCTS)} products")
    else:
        print(f"ℹ️  Products already present ({Product.query.count()})")

    # Create admin if missing
    if not User.query.filter_by(email="admin@example.com").first():
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("changeme123")
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin created: admin@example.com / changeme123")
    else:
        print("ℹ️  Admin already exists")
