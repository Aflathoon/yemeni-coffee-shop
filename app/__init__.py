from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from dotenv import load_dotenv
import os

load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///shop.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB upload limit

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
        _seed_products()

    return app

def _seed_products():
    """Seed initial products if database is empty."""
    from app.models import Product
    if Product.query.count() == 0:
        products = [
            Product(name="Yemeni Mokha Arabica", category="coffee", 
                    description="Legendary Yemeni coffee from the highlands of Haraz. Wine-like body, chocolate and dried fruit notes.",
                    price=24.99, image="yemeni_coffee_1.jpg"),
            Product(name="Arabica Cherry Roast", category="coffee",
                    description="Medium roast, bright acidity, honey sweetness. Perfect pour-over.",
                    price=18.99, image="arabica_cherry_1.jpg"),
            Product(name="Yemeni Sidr Honey", category="honey",
                    description="Rare honey from Sidr trees in Hadhramaut. Thick, caramel-like, with medicinal depth.",
                    price=89.99, image="honey_jar_1.jpg"),
            Product(name="Raw Honeycomb", category="honey",
                    description="Unfiltered honeycomb straight from the hive. Chew the wax, taste the terroir.",
                    price=34.99, image="honeycomb_1.jpg"),
            Product(name="Cardamom Pods (Green)", category="spices",
                    description="Whole green cardamom. Essential for Yemeni coffee and chai.",
                    price=12.99, image="cardamom_1.jpg"),
            Product(name="Cinnamon Sticks (Ceylon)", category="spices",
                    description="True Ceylon cinnamon, not cassia. Delicate, sweet, floral.",
                    price=9.99, image="cinnamon_1.jpg"),
            Product(name="Saffron Threads", category="spices",
                    description="Premium saffron. A pinch transforms rice, tea, and desserts.",
                    price=19.99, image="saffron_1.jpg"),
            Product(name="Dried Mint", category="herbs",
                    description="Yemeni dried mint. Crush into tea, sprinkle on yogurt.",
                    price=7.99, image="mint_1.jpg"),
            Product(name="Lavender Flowers", category="herbs",
                    description="Culinary lavender. Add to honey, tea, or baked goods.",
                    price=11.99, image="lavender_1.jpg"),
        ]
        db.session.add_all(products)
        db.session.commit()
        print("✅ Seeded product database")
