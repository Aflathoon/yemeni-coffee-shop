from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    language = db.Column(db.String(5), default="en")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    # category ∈ coffee, tea, herbs, spices, honey, blends
    subcategory = db.Column(db.String(100))       # e.g. "ground", "whole", "single-origin"
    origin_country = db.Column(db.String(100), index=True)   # Yemen, India, Pakistan, Brazil...
    origin_region = db.Column(db.String(200))     # "Haraz", "Kerala", "Sidr Valley"
    description = db.Column(db.Text, nullable=False)
    short_desc = db.Column(db.String(300))
    price = db.Column(db.Float, nullable=False)
    weight_grams = db.Column(db.Integer, default=100)
    image = db.Column(db.String(200), default="placeholder.jpg")
    stock = db.Column(db.Integer, default=100)
    featured = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default="pending")
    total = db.Column(db.Float, default=0.0)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    body = db.Column(db.Text)
    image = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published = db.Column(db.Boolean, default=False)
