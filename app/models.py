from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active_account = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)
    language = db.Column(db.String(5), default="en")

    # Customer profile
    full_name = db.Column(db.String(200))
    phone = db.Column(db.String(40))
    address_line = db.Column(db.String(300))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(30))
    country = db.Column(db.String(100))

    # Wholesale / agent
    is_wholesale = db.Column(db.Boolean, default=False, index=True)
    wholesale_status = db.Column(db.String(20), default="none")  # none | pending | approved | rejected
    business_name = db.Column(db.String(200))
    business_type = db.Column(db.String(80))   # shop, cafe, distributor, agent, other
    business_registration = db.Column(db.String(80))
    wholesale_notes = db.Column(db.Text)        # admin-only notes
    wholesale_applied_at = db.Column(db.DateTime)
    wholesale_approved_at = db.Column(db.DateTime)
    wholesale_tier = db.Column(db.String(20), default="standard")  # standard | bronze | silver | gold

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_active(self):
        # Flask-Login calls this; must return True for login to work.
        # is_active_account is our business flag.
        return bool(self.is_active_account)

    @property
    def display_name(self):
        return self.full_name or self.email.split("@")[0]


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class WholesaleAccount(db.Model):
    """Separate account table for B2B / wholesale partners.

    Sessions are custom (session['ws_id']) — not tied to Flask-Login.
    """
    __tablename__ = "wholesale_account"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    # Business identity
    company_name = db.Column(db.String(250), nullable=False)
    business_type = db.Column(db.String(80))              # shop, cafe, distributor, agent, other
    tax_id = db.Column(db.String(80))
    phone = db.Column(db.String(40))

    # Address
    address_line = db.Column(db.String(300))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(30))
    country = db.Column(db.String(100))

    # Application
    status = db.Column(db.String(20), default="pending", index=True)  # pending | approved | rejected | suspended
    tier = db.Column(db.String(20), default="standard")                # standard | bronze | silver | gold
    notes = db.Column(db.Text)                                        # applicant's own notes
    admin_notes = db.Column(db.Text)                                  # internal
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey("user.id"))     # which admin approved
    last_login_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_approved(self):
        return self.status == "approved"

    @property
    def display_name(self):
        return self.company_name or self.email.split("@")[0]


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    subcategory = db.Column(db.String(100))
    origin_country = db.Column(db.String(100), index=True)
    origin_region = db.Column(db.String(200))
    description = db.Column(db.Text, nullable=False)         # short plain-text summary
    long_description = db.Column(db.Text)                    # rich HTML body
    short_desc = db.Column(db.String(300))
    price = db.Column(db.Float, nullable=False)
    compare_at_price = db.Column(db.Float)                   # "was $X" display
    weight_grams = db.Column(db.Integer, default=100)
    unit = db.Column(db.String(10), default="ea")     # g | kg | ea | set | bag
    unit_quantity = db.Column(db.Integer, default=1)  # 100, 250, 1, etc.
    allow_custom_weight = db.Column(db.Boolean, default=False)  # show g/kg selector
    image = db.Column(db.String(200), default="placeholder.jpg")
    gallery = db.Column(db.Text)                             # newline-separated image paths
    stock = db.Column(db.Integer, default=100)
    stock_alert_threshold = db.Column(db.Integer, default=5)
    tags = db.Column(db.String(400))                         # comma-separated
    meta_title = db.Column(db.String(200))
    meta_description = db.Column(db.String(300))
    active = db.Column(db.Boolean, default=True, index=True) # hide without deleting
    featured = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CartItem(db.Model):
    """A line in the cart.

    Belongs to exactly one of:
      - session_id (anonymous retail visitor)
      - user_id    (logged-in retail customer)
      - wholesale_id (logged-in wholesale partner)
    """
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    wholesale_id = db.Column(db.Integer, db.ForeignKey("wholesale_account.id"), index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product")


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    email = db.Column(db.String(120), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    address_line = db.Column(db.String(300), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(30), nullable=False)
    country = db.Column(db.String(100), nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(50), default="pending", index=True)
    subtotal = db.Column(db.Float, default=0.0)
    shipping = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)      # snapshot
    product_price = db.Column(db.Float, nullable=False)            # snapshot
    quantity = db.Column(db.Integer, nullable=False)
    line_total = db.Column(db.Float, nullable=False)

    product = db.relationship("Product")


class Setting(db.Model):
    """Key/value store for runtime-editable settings (Telegram token, channel, etc.)."""
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.get(key)
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        row = cls.query.get(key)
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))
        db.session.commit()

    @classmethod
    def get_all(cls):
        return {r.key: r.value for r in cls.query.all()}


class Article(db.Model):
    """Long-form blog content. Separate from Post (which is short marketing copy)."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    slug = db.Column(db.String(250), unique=True, index=True)
    excerpt = db.Column(db.String(400))
    body = db.Column(db.Text)                 # rich HTML from TinyMCE
    hero_image = db.Column(db.String(300))
    category = db.Column(db.String(60), index=True)   # e.g. "coffee", "recipes", "origins"
    tags = db.Column(db.String(400))
    author_name = db.Column(db.String(120), default="The Spice & Roast Co.")
    reading_minutes = db.Column(db.Integer, default=4)
    published = db.Column(db.Boolean, default=False, index=True)
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # SEO
    meta_title = db.Column(db.String(250))
    meta_description = db.Column(db.String(400))


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    body = db.Column(db.Text)
    image = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    published = db.Column(db.Boolean, default=False)
