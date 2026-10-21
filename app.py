import csv
import io
import json
import math
import os
import re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import quote

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func, or_, text
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import settings

app = Flask(__name__)
app.config.from_object(settings)
app.config.setdefault("WTF_CSRF_FIELD_NAME", "_csrf_token")
app.config.setdefault("UPLOAD_FOLDER", str(settings.BASE_DIR / "static" / "uploads"))
app.config.setdefault("MAX_CONTENT_LENGTH", 8 * 1024 * 1024)
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "account_login"
ORDER_STATUSES = ["new", "confirmed", "shipped", "delivered", "returned", "cancelled"]
STATUS_LABELS = {
    "new": "جديد", "confirmed": "تم التأكيد", "shipped": "تم الشحن",
    "delivered": "تم التسليم", "returned": "راجع", "cancelled": "ملغي",
}
PAYMENT_LABELS = {"cod": "الدفع عند الاستلام", "card": "بطاقة بنكية", "transfer": "تحويل بنكي"}
BEAUTY_TYPES = {
    "skincare": ("سيروم", "كريم", "ترطيب", "serum", "crème", "hydrat"),
    "haircare": ("شعر", "مجفف", "مملس", "sèche-cheveux", "lisseur", "hair"),
    "makeup": ("مكياج", "فرش", "pinceaux", "maquillage", "makeup"),
    "fragrance": ("عطر", "parfum", "fragrance"),
    "bodycare": ("أركان", "argan", "جسم", "body"),
}
TRANSLATIONS = {
    "home": ("الرئيسية", "Accueil"), "search": ("بحث", "Rechercher"),
    "account": ("حسابي", "Mon compte"), "track": ("تتبع طلبي", "Suivre ma commande"),
    "delivery": ("التوصيل إلى جميع أنحاء المغرب", "Livraison partout au Maroc"),
    "trust_refund": ("رضاك مضمون أو استرجع أموالك", "Satisfait ou remboursé"),
    "trust_offers": ("عروض وطنية ودولية", "Offres nationales et internationales"),
    "trust_delivery": ("التوصيل لجميع مدن المغرب", "Livraison partout au Maroc"),
    "hero_eyebrow": ("منتجات مختارة بعناية، تصلك إلى باب منزلك.", "De belles trouvailles, livrées chez vous."),
    "hero_title": ("كل ما تحتاج إليه،", "Tout ce que vous aimez,"),
    "hero_title_em": ("في مكان واحد.", "au même endroit."),
    "hero_copy": ("اكتشف منتجات مختارة بعناية وبأسعار مناسبة، واطلب بسهولة من أي مدينة في المغرب.",
                  "Découvrez une sélection de produits à prix doux, livrés partout au Maroc."),
    "offers": ("اكتشف العروض", "Voir les offres"), "cod": ("الدفع عند الاستلام", "Paiement à la livraison"),
    "free_delivery": ("توصيل لجميع المدن", "Livraison partout au Maroc"),
    "featured": ("عروض مميزة", "Offres à la une"), "most_ordered": ("الأكثر طلباً", "Les plus demandés"),
    "deals": ("عروض مميزة", "Bons plans"), "save": ("وفّر أكثر", "Économisez"),
    "discover": ("اكتشف منتجاتنا", "Découvrir nos produits"),
    "categories": ("تسوق حسب الفئة", "Acheter par catégorie"),
    "search_results": ("نتائج البحث", "Résultats de recherche"),
    "trending": ("الأكثر رواجاً", "Tendances"), "popular": ("اختيارات العملاء", "Choix des clients"),
    "new_arrivals": ("منتجات جديدة", "Nouveautés"), "just_arrived": ("أحدث المنتجات", "Nouveautés"),
    "cart": ("سلة التسوق", "Panier"), "subtotal": ("المجموع الفرعي", "Sous-total"),
    "shipping": ("التوصيل", "Livraison"), "total": ("المجموع", "Total"),
    "apply": ("تطبيق", "Appliquer"), "coupon": ("رمز التخفيض", "Code promo"),
    "checkout": ("إتمام الطلب", "Valider mon panier"),
    "continue_shopping": ("متابعة التسوق", "Continuer mes achats"),
    "delivery_info": ("معلومات التوصيل", "Adresse de livraison"),
    "full_name": ("الاسم الكامل", "Nom complet"), "phone": ("الهاتف", "Téléphone"),
    "city": ("المدينة", "Ville"), "address": ("العنوان بالتفصيل", "Adresse complète"),
    "payment": ("طريقة الأداء", "Mode de paiement"),
    "place_order": ("تأكيد الطلب", "Commander"), "terms": ("أوافق على الشروط والأحكام", "J'accepte les conditions générales"),
    "price": ("الثمن", "Prix"), "stock": ("متوفر", "En stock"),
    "add_cart": ("إضافة إلى السلة", "Ajouter au panier"),
}


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, default="")
    name_ar = db.Column(db.String(120), nullable=False)
    name_fr = db.Column(db.String(120), default="")
    icon = db.Column(db.String(24), default="✦")
    image_url = db.Column(db.String(500), default="/static/placeholder.png")
    sort_order = db.Column(db.Integer, default=0)
    products = db.relationship("Product", backref="category", lazy=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, default="")
    name_fr = db.Column(db.String(180), default="")
    description = db.Column(db.Text, nullable=False)
    description_fr = db.Column(db.Text, default="")
    price = db.Column(db.Float, nullable=False)
    old_price = db.Column(db.Float, default=0)
    stock = db.Column(db.Integer, default=0)
    sku = db.Column(db.String(80), unique=True, default="")
    seller = db.Column(db.String(150), default="")
    image_url = db.Column(db.String(600), nullable=False, default="/static/placeholder.png")
    images_json = db.Column(db.Text, default="[]")
    badge = db.Column(db.String(80), default="")
    rating = db.Column(db.Float, default=4.7)
    reviews = db.Column(db.Integer, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    is_deal = db.Column(db.Boolean, default=False, nullable=False)
    is_trending = db.Column(db.Boolean, default=False, nullable=False)
    is_new = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def images(self):
        try:
            values = json.loads(self.images_json or "[]")
        except (TypeError, json.JSONDecodeError):
            values = []
        return [self.image_url] + [image for image in values if image and image != self.image_url]

    @property
    def discount_percent(self):
        return round((1 - self.price / self.old_price) * 100) if self.old_price and self.old_price > self.price else 0


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    phone = db.Column(db.String(40), default="")
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(80), default="المنزل")
    city = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    phone = db.Column(db.String(40), nullable=False)


class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "product_id"),)


class ProductReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship("User")
    __table_args__ = (db.UniqueConstraint("product_id", "user_id"),)


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(40), default="")
    subject = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="new", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(32), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    full_name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(180), default="")
    phone = db.Column(db.String(40), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    billing_address = db.Column(db.String(300), default="")
    subtotal = db.Column(db.Float, nullable=False)
    shipping_fee = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    coupon_code = db.Column(db.String(80), default="")
    discount = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default="new", nullable=False)
    payment_method = db.Column(db.String(40), default="cod")
    utm_json = db.Column(db.Text, default="{}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    product_name = db.Column(db.String(180), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)


class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    kind = db.Column(db.String(20), default="percent")
    value = db.Column(db.Float, nullable=False)
    min_order = db.Column(db.Float, default=0)
    expires_at = db.Column(db.Date)
    usage_limit = db.Column(db.Integer, default=0)
    uses = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)


class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    subtitle = db.Column(db.String(300), default="")
    image_url = db.Column(db.String(600), default="/static/placeholder.png")
    link_url = db.Column(db.String(500), default="/")
    active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)


class StoreSetting(db.Model):
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, default="")


class StorePage(db.Model):
    slug = db.Column(db.String(80), primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.Text, default="")


def setting(key, default=""):
    item = db.session.get(StoreSetting, key)
    return item.value if item else default


def theme_color(key, default):
    value = setting(key, default)
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else default


def set_setting(key, value):
    item = db.session.get(StoreSetting, key)
    if item is None:
        item = StoreSetting(key=key)
        db.session.add(item)
    item.value = str(value)


def slugify(value):
    value = re.sub(r"[^\w\s-]", "", value.lower(), flags=re.UNICODE)
    return re.sub(r"[-\s]+", "-", value).strip("-") or secrets.token_hex(4)


def migrate_existing_database():
    """Add fields to the original single-file SQLite app without discarding existing products/orders."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return
    with db.engine.begin() as connection:
        columns = {
            "category": [
                ("slug", "VARCHAR(100) NOT NULL DEFAULT ''"), ("name_fr", "VARCHAR(120) DEFAULT ''"),
                ("image_url", "VARCHAR(500) DEFAULT '/static/placeholder.png'"),
                ("sort_order", "INTEGER DEFAULT 0"),
            ],
            "product": [
                ("slug", "VARCHAR(200) NOT NULL DEFAULT ''"), ("description_fr", "TEXT DEFAULT ''"),
                ("sku", "VARCHAR(80) DEFAULT ''"), ("seller", "VARCHAR(150) DEFAULT ''"),
                ("images_json", "TEXT DEFAULT '[]'"), ("is_featured", "BOOLEAN DEFAULT 0"),
                ("is_deal", "BOOLEAN DEFAULT 0"), ("is_trending", "BOOLEAN DEFAULT 0"),
                ("is_new", "BOOLEAN DEFAULT 0"),
            ],
            "order": [
                ("user_id", "INTEGER"), ("billing_address", "VARCHAR(300) DEFAULT ''"),
                ("coupon_code", "VARCHAR(80) DEFAULT ''"), ("discount", "FLOAT DEFAULT 0"),
                ("utm_json", "TEXT DEFAULT '{}'"),
            ],
        }
        for table, fields in columns.items():
            present = {row[1] for row in connection.execute(text(f'PRAGMA table_info("{table}")'))}
            if not present:
                continue
            for name, definition in fields:
                if name not in present:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
        if connection.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='product'")).first():
            connection.execute(text("UPDATE product SET seller = :seller WHERE seller IS NULL OR seller = ''"),
                               {"seller": settings.STORE_NAME})
            connection.execute(text("UPDATE product SET sku = 'VZ-' || id WHERE sku IS NULL OR sku = ''"))
            connection.execute(text("UPDATE product SET slug = 'product-' || id WHERE slug IS NULL OR slug = ''"))
        if connection.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='category'")).first():
            connection.execute(text("UPDATE category SET slug = lower(name) WHERE slug IS NULL OR slug = ''"))
        if connection.execute(text('SELECT 1 FROM sqlite_master WHERE type="table" AND name="order"')).first():
            connection.execute(text(
                'UPDATE "order" SET status = CASE status '
                "WHEN 'جديد' THEN 'new' WHEN 'قيد التأكيد' THEN 'confirmed' "
                "WHEN 'تم الشحن' THEN 'shipped' WHEN 'تم التسليم' THEN 'delivered' "
                "WHEN 'ملغي' THEN 'cancelled' ELSE status END"
            ))


with app.app_context():
    db.create_all()
    migrate_existing_database()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def money(value):
    return f"{(value or 0):,.0f}"


def shipping_for(subtotal, city=""):
    if subtotal >= float(setting("free_delivery_threshold", settings.FREE_SHIPPING_THRESHOLD)):
        return 0
    try:
        fees = json.loads(setting("city_fees", "{}"))
    except json.JSONDecodeError:
        fees = {}
    return float(fees.get(city, setting("shipping_fee", settings.SHIPPING_FEE)))


def get_cart_items():
    data = session.get("cart", {})
    try:
        ids = [int(key) for key in data]
    except (TypeError, ValueError):
        ids = []
    products = Product.query.filter(Product.id.in_(ids), Product.is_active.is_(True)).all() if ids else []
    lookup = {product.id: product for product in products}
    items = []
    for key, raw_quantity in data.items():
        try:
            product = lookup.get(int(key))
            quantity = min(max(1, int(raw_quantity)), product.stock) if product else 0
        except (TypeError, ValueError):
            continue
        if product and quantity:
            items.append({"product": product, "quantity": quantity, "subtotal": product.price * quantity})
    return items


def cart_subtotal(items):
    return sum(item["subtotal"] for item in items)


def whatsapp_url(message):
    phone = re.sub(r"\D", "", setting("whatsapp", settings.WHATSAPP_NUMBER))
    return f"https://wa.me/{phone}?text={quote(message)}"


def csrf_token():
    from flask_wtf.csrf import generate_csrf
    return generate_csrf()


def translate(key):
    arabic, french = TRANSLATIONS.get(key, (key, key))
    return french if session.get("language") == "fr" else arabic


@app.context_processor
def inject_store_context():
    cats = Category.query.order_by(Category.sort_order, Category.id).all()
    return {
        "cart_count": sum(item["quantity"] for item in get_cart_items()),
        "store_name": setting("store_name", settings.STORE_NAME),
        "currency": settings.CURRENCY, "currency_ar": settings.CURRENCY_AR,
        "shipping_fee": setting("shipping_fee", settings.SHIPPING_FEE),
        "free_shipping_threshold": float(setting("free_delivery_threshold", settings.FREE_SHIPPING_THRESHOLD)),
        "categories": cats, "config": app.config, "store_setting": setting,
        "theme_primary": theme_color("primary_color", "#ff9800"),
        "theme_accent": theme_color("accent_color", "#ff9800"),
        "theme_background": theme_color("background_color", "#fffaf4"),
        "csrf_token": csrf_token, "language": session.get("language", "ar"),
        "t": translate,
        "whatsapp": setting("whatsapp", settings.WHATSAPP_NUMBER),
    }


@app.template_filter("money")
def money_filter(value):
    return money(value)


@app.template_filter("status_label")
def status_label(status):
    return STATUS_LABELS.get(status, status)


@app.before_request
def save_utm():
    for key in ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"):
        if request.args.get(key):
            session.setdefault("utm", {})[key] = request.args[key]


@app.route("/language/<lang>")
def language(lang):
    if lang not in {"ar", "fr"}:
        abort(404)
    session["language"] = lang
    return redirect(request.referrer or url_for("index"))


@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    category_slug = request.args.get("category", "").strip()
    beauty_type = request.args.get("beauty_type", "").strip()
    category = Category.query.filter(or_(Category.slug == category_slug, Category.name == category_slug)).first() if category_slug else None
    if beauty_type in BEAUTY_TYPES and not category:
        category = Category.query.filter_by(slug="beauty").first()
    query = Product.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category_id=category.id)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(like), Product.name_fr.ilike(like), Product.description.ilike(like)))
    if beauty_type in BEAUTY_TYPES and category and category.slug == "beauty":
        terms = [f"%{term}%" for term in BEAUTY_TYPES[beauty_type]]
        query = query.filter(or_(*[
            field.ilike(term)
            for field in (Product.name, Product.name_fr, Product.description, Product.description_fr)
            for term in terms
        ]))
    try:
        minimum_price = float(request.args.get("min_price", ""))
        if not math.isfinite(minimum_price) or minimum_price < 0:
            minimum_price = None
    except ValueError:
        minimum_price = None
    try:
        maximum_price = float(request.args.get("max_price", ""))
        if not math.isfinite(maximum_price) or maximum_price < 0:
            maximum_price = None
    except ValueError:
        maximum_price = None
    try:
        minimum_rating = float(request.args.get("min_rating", ""))
        if not math.isfinite(minimum_rating):
            minimum_rating = None
        else:
            minimum_rating = min(max(minimum_rating, 0), 5)
    except ValueError:
        minimum_rating = None
    if minimum_price is not None:
        query = query.filter(Product.price >= minimum_price)
    if maximum_price is not None:
        query = query.filter(Product.price <= maximum_price)
    if minimum_rating is not None:
        query = query.filter(Product.rating >= minimum_rating)
    sort = request.args.get("sort", "newest")
    if sort == "price_low":
        query = query.order_by(Product.price.asc(), Product.id.desc())
    elif sort == "price_high":
        query = query.order_by(Product.price.desc(), Product.id.desc())
    elif sort == "rating":
        query = query.order_by(Product.rating.desc(), Product.reviews.desc())
    else:
        query = query.order_by(Product.created_at.desc())
        sort = "newest"
    products = query.all()
    beauty_catalog = Product.query.join(Category).filter(
        Product.is_active.is_(True), Category.slug == "beauty"
    ).order_by(Product.created_at.desc()).all()
    featured = Product.query.filter_by(is_active=True, is_featured=True).order_by(Product.id.desc()).limit(8).all()
    deals = Product.query.filter_by(is_active=True, is_deal=True).order_by(Product.id.desc()).limit(8).all()
    trending = Product.query.filter_by(is_active=True, is_trending=True).order_by(Product.id.desc()).limit(8).all()
    new_arrivals = Product.query.filter_by(is_active=True, is_new=True).order_by(Product.created_at.desc()).limit(8).all()
    recommended = Product.query.filter_by(is_active=True).order_by(
        Product.rating.desc(), Product.reviews.desc(), Product.id.desc()
    ).limit(8).all()
    banners = Banner.query.filter_by(active=True).order_by(Banner.sort_order, Banner.id).all()
    beauty_category = Category.query.filter_by(slug="beauty").first()
    hero_slugs = {"beauty", "electronics", "home", "clothing"}
    hero_categories = Category.query.filter(Category.slug.in_(hero_slugs)).order_by(
        Category.sort_order, Category.id
    ).all()
    hero_slides = []
    for hero_category in hero_categories:
        hero_product = Product.query.filter_by(
            category_id=hero_category.id, is_active=True
        ).order_by(Product.is_deal.desc(), Product.is_featured.desc(), Product.id.desc()).first()
        hero_slides.append({"category": hero_category, "product": hero_product})
    has_filters = bool(search or category or beauty_type in BEAUTY_TYPES
                      or minimum_price is not None or maximum_price is not None or minimum_rating is not None
                      or request.args.get("sort"))
    return render_template("index.html", products=products, beauty_products=beauty_catalog,
                           beauty_category=beauty_category, featured=featured or beauty_catalog[:8],
                           deals=deals, trending=trending, new_arrivals=new_arrivals,
                           recommended=recommended, hero_slides=hero_slides, banners=banners,
                           search=search, selected_category=category.slug if category else "",
                           beauty_type=beauty_type, minimum_price=minimum_price,
                           maximum_price=maximum_price, minimum_rating=minimum_rating, sort=sort,
                           has_filters=has_filters)


@app.get("/product/<slug>")
def product_detail(slug):
    product = Product.query.filter(or_(Product.slug == slug, Product.id == slug if str(slug).isdigit() else False),
                                   Product.is_active.is_(True)).first_or_404()
    related = Product.query.filter(Product.category_id == product.category_id, Product.id != product.id,
                                   Product.is_active.is_(True)).limit(4).all()
    reviews = ProductReview.query.filter_by(product_id=product.id).order_by(
        ProductReview.created_at.desc()
    ).all()
    can_review = False
    if current_user.is_authenticated:
        can_review = db.session.query(OrderItem.id).join(
            Order, Order.id == OrderItem.order_id
        ).filter(
            Order.user_id == current_user.id,
            Order.status == "delivered",
            OrderItem.product_id == product.id,
        ).first() is not None
    delivery_start = date.today() + timedelta(days=2)
    delivery_end = date.today() + timedelta(days=5)
    return render_template("product.html", product=product, related=related,
                           delivery_start=delivery_start, delivery_end=delivery_end,
                           reviews=reviews, can_review=can_review)


@app.post("/product/<slug>/review")
@login_required
def add_product_review(slug):
    product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()
    purchased = db.session.query(OrderItem.id).join(
        Order, Order.id == OrderItem.order_id
    ).filter(
        Order.user_id == current_user.id,
        Order.status == "delivered",
        OrderItem.product_id == product.id,
    ).first()
    if not purchased:
        flash("يمكن إضافة تقييم بعد استلام المنتج.", "error")
        return redirect(url_for("product_detail", slug=product.slug, _anchor="reviews"))
    try:
        rating = int(request.form.get("rating", ""))
    except ValueError:
        rating = 0
    comment = request.form.get("comment", "").strip()
    if rating not in range(1, 6) or len(comment) < 5 or len(comment) > 2000:
        flash("يرجى اختيار تقييم من نجمة إلى خمس نجوم وكتابة تعليق من 5 إلى 2000 حرف.", "error")
        return redirect(url_for("product_detail", slug=product.slug, _anchor="reviews"))
    review = ProductReview.query.filter_by(product_id=product.id, user_id=current_user.id).first()
    if review:
        review.rating, review.comment, review.created_at = rating, comment, datetime.utcnow()
    else:
        db.session.add(ProductReview(product_id=product.id, user_id=current_user.id,
                                     rating=rating, comment=comment))
    db.session.flush()
    review_rows = ProductReview.query.filter_by(product_id=product.id).all()
    product.rating = sum(item.rating for item in review_rows) / len(review_rows)
    product.reviews = len(review_rows)
    db.session.commit()
    flash("شكراً لك، تم حفظ تقييمك.", "success")
    return redirect(url_for("product_detail", slug=product.slug, _anchor="reviews"))


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()
        if (not name or len(name) > 160 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
                or len(subject) < 3 or len(subject) > 180 or len(message) < 10 or len(message) > 4000):
            flash("يرجى التحقق من الاسم والبريد الإلكتروني والموضوع والرسالة.", "error")
        else:
            db.session.add(ContactMessage(name=name, email=email, phone=phone[:40],
                                          subject=subject, message=message))
            db.session.commit()
            flash("تم استلام رسالتك، وسنتواصل معك قريباً.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html")


@app.get("/search/suggest")
def search_suggest():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return {"products": []}
    like = f"%{query}%"
    products = Product.query.filter(
        Product.is_active.is_(True),
        or_(Product.name.ilike(like), Product.name_fr.ilike(like)),
    ).limit(6).all()
    return {"products": [{"name": product.name, "url": url_for("product_detail", slug=product.slug)}
                         for product in products]}


@app.post("/cart/add/<int:product_id>")
def add_to_cart(product_id):
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    try:
        quantity = max(1, int(request.form.get("quantity", 1)))
    except ValueError:
        quantity = 1
    if not product.stock:
        flash("المنتج غير متوفر حالياً.", "error")
    else:
        cart_data = session.get("cart", {})
        key = str(product.id)
        cart_data[key] = min(int(cart_data.get(key, 0)) + quantity, product.stock)
        session["cart"] = cart_data
        flash("تمت إضافة المنتج إلى سلة التسوق.", "success")
    return redirect(request.referrer or url_for("cart"))


@app.post("/buy-now/<int:product_id>")
def buy_now(product_id):
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    try:
        quantity = max(1, int(request.form.get("quantity", 1)))
    except ValueError:
        quantity = 1
    if quantity > product.stock:
        flash("الكمية المطلوبة غير متوفرة.", "error")
        return redirect(url_for("product_detail", slug=product.slug))
    session["cart"] = {str(product.id): quantity}
    return redirect(url_for("checkout"))


@app.get("/cart")
def cart():
    items = get_cart_items()
    subtotal = cart_subtotal(items)
    coupon, discount = coupon_discount(subtotal)
    shipping = shipping_for(subtotal - discount) if items else 0
    return render_template("cart.html", items=items, subtotal=subtotal, shipping=shipping,
                           discount=discount, coupon=coupon, total=subtotal - discount + shipping)


@app.post("/cart/update")
def update_cart():
    cart_data = session.get("cart", {})
    for key, value in request.form.items():
        if not key.startswith("quantity_"):
            continue
        product_id = key.removeprefix("quantity_")
        try:
            product, quantity = db.session.get(Product, int(product_id)), int(value)
        except (TypeError, ValueError):
            continue
        if not product or quantity <= 0:
            cart_data.pop(product_id, None)
        else:
            cart_data[product_id] = min(quantity, product.stock)
    session["cart"] = cart_data
    return redirect(url_for("cart"))


@app.post("/cart/remove/<int:product_id>")
def remove_from_cart(product_id):
    cart_data = session.get("cart", {})
    cart_data.pop(str(product_id), None)
    session["cart"] = cart_data
    return redirect(url_for("cart"))


@app.post("/cart/coupon")
def apply_coupon():
    code = request.form.get("coupon", "").strip().upper()
    coupon = Coupon.query.filter_by(code=code, active=True).first()
    subtotal = cart_subtotal(get_cart_items())
    if not coupon or (coupon.expires_at and coupon.expires_at < date.today()) or (coupon.usage_limit and coupon.uses >= coupon.usage_limit) or subtotal < coupon.min_order:
        session.pop("coupon", None)
        flash("رمز التخفيض غير صالح أو لا تنطبق شروطه.", "error")
    else:
        session["coupon"] = coupon.code
        flash("تم تطبيق رمز التخفيض.", "success")
    return redirect(url_for("cart"))


def coupon_discount(subtotal):
    coupon = Coupon.query.filter_by(code=session.get("coupon", ""), active=True).first()
    if not coupon or (coupon.usage_limit and coupon.uses >= coupon.usage_limit) or subtotal < coupon.min_order:
        return None, 0
    amount = subtotal * coupon.value / 100 if coupon.kind == "percent" else coupon.value
    return coupon, min(subtotal, amount)


def checkout_fields():
    fields = {key: request.form.get(key, "").strip() for key in ("full_name", "phone", "city", "address")}
    digits = re.sub(r"\D", "", fields["phone"])
    return fields if all(fields.values()) and 9 <= len(digits) <= 15 else None


def create_order(items, fields):
    subtotal = cart_subtotal(items)
    coupon, discount = coupon_discount(subtotal)
    shipping = shipping_for(subtotal - discount, fields["city"])
    available = {"cod": setting("payment_cod", "1") == "1",
                 "card": setting("payment_card", "0") == "1",
                 "transfer": setting("payment_transfer", "0") == "1"}
    enabled_methods = [method for method, enabled in available.items() if enabled]
    if not enabled_methods:
        raise ValueError("لا توجد طريقة أداء مفعّلة. تواصل مع المتجر.")
    payment = request.form.get("payment") or ("cod" if available["cod"] else next(iter(enabled_methods), ""))
    if payment not in available or not available[payment]:
        raise ValueError("طريقة الأداء المختارة غير مفعّلة. حدّث الصفحة واختر طريقة أخرى.")
    order = Order(
        order_number=f"VZ{datetime.utcnow():%y%m%d%H%M%S}{secrets.token_hex(2).upper()}",
        user_id=current_user.id if current_user.is_authenticated else None,
        full_name=fields["full_name"], email=request.form.get("email", "").strip(),
        phone=fields["phone"], city=fields["city"], address=fields["address"],
        billing_address=request.form.get("billing_address", "").strip(),
        subtotal=subtotal, shipping_fee=shipping, discount=discount, total=subtotal - discount + shipping,
        coupon_code=coupon.code if coupon else "", payment_method=payment,
        utm_json=json.dumps(session.get("utm", {})),
    )
    for item in items:
        product = item["product"]
        if product.stock < item["quantity"]:
            raise ValueError(f"المخزون المتوفر من {product.name} هو {product.stock} فقط.")
        product.stock -= item["quantity"]
        order.items.append(OrderItem(product_id=product.id, product_name=product.name,
                                     quantity=item["quantity"], unit_price=product.price))
    if coupon:
        coupon.uses += 1
    db.session.add(order)
    db.session.commit()
    session["cart"] = {}
    session.pop("coupon", None)
    return order


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items = get_cart_items()
    if not items:
        flash("سلة التسوق فارغة.", "info")
        return redirect(url_for("index"))
    subtotal = cart_subtotal(items)
    coupon, discount = coupon_discount(subtotal)
    shipping = shipping_for(subtotal - discount)
    total = subtotal - discount + shipping
    if request.method == "POST":
        fields = checkout_fields()
        if not fields or request.form.get("terms") != "yes":
            flash("يرجى التحقق من بيانات التوصيل والموافقة على الشروط والأحكام.", "error")
        else:
            try:
                order = create_order(items, fields)
                return render_template("checkout_success.html", order=order,
                                       purchase_value=order.total, purchase_currency="MAD")
            except ValueError as error:
                db.session.rollback()
                flash(str(error), "error")
                return redirect(url_for("cart"))
    addresses = Address.query.filter_by(user_id=current_user.id).all() if current_user.is_authenticated else []
    return render_template("checkout.html", items=items, subtotal=subtotal, discount=discount,
                           coupon=coupon, shipping=shipping, total=total, addresses=addresses)


@app.get("/order/track")
def track_order():
    return render_template("track_order.html", order=None)


@app.post("/order/track")
def find_order():
    order = Order.query.filter_by(order_number=request.form.get("order_id", "").strip().upper(),
                                  phone=request.form.get("phone", "").strip()).first()
    if not order:
        flash("لم نعثر على الطلب. يرجى التحقق من رقم الطلب ورقم الهاتف.", "error")
    return render_template("track_order.html", order=order)


@app.get("/product/whatsapp/<int:product_id>")
def product_whatsapp(product_id):
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    quantity = max(1, min(request.args.get("quantity", 1, type=int), max(product.stock, 1)))
    return redirect(whatsapp_url(f"سلام، بغيت نطلب {product.name} × {quantity}"))


@app.route("/register", methods=["GET", "POST"])
def account_register():
    if current_user.is_authenticated:
        return redirect(url_for("account"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        name = request.form.get("full_name", "").strip()
        if name and email and len(password) >= 8 and not User.query.filter_by(email=email).first():
            user = User(full_name=name, email=email, phone=request.form.get("phone", ""),
                        password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for("account"))
        flash("يرجى إدخال الاسم والبريد الإلكتروني الصحيح وكلمة مرور لا تقل عن 8 أحرف.", "error")
    return render_template("account_form.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def account_login():
    if current_user.is_authenticated:
        return redirect(url_for("account"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("account"))
        flash("بيانات الدخول غير صحيحة.", "error")
    return render_template("account_form.html", mode="login")


@app.post("/logout")
@login_required
def account_logout():
    logout_user()
    return redirect(url_for("index"))


@app.get("/account")
@login_required
def account():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    addresses = Address.query.filter_by(user_id=current_user.id).all()
    wishlist = db.session.query(Product).join(Wishlist, Wishlist.product_id == Product.id).filter(Wishlist.user_id == current_user.id).all()
    return render_template("account.html", orders=orders, addresses=addresses, wishlist=wishlist)


@app.post("/account/address")
@login_required
def save_address():
    city = request.form.get("city", "").strip()
    address = request.form.get("address", "").strip()
    phone = request.form.get("phone", "").strip()
    if city and address and phone:
        db.session.add(Address(user_id=current_user.id, title=request.form.get("title", "المنزل"),
                               city=city, address=address, phone=phone))
        db.session.commit()
    return redirect(url_for("account"))


@app.post("/wishlist/<int:product_id>")
@login_required
def toggle_wishlist(product_id):
    product = db.get_or_404(Product, product_id)
    item = Wishlist.query.filter_by(user_id=current_user.id, product_id=product.id).first()
    if item:
        db.session.delete(item)
    else:
        db.session.add(Wishlist(user_id=current_user.id, product_id=product.id))
    db.session.commit()
    return redirect(request.referrer or url_for("account"))


def admin_required(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if session.get("admin_authenticated") is not True:
            return redirect(url_for("admin_login", next=request.path))
        return function(*args, **kwargs)
    return wrapped


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        stored = setting("admin_password_hash", "")
        configured = app.config.get("ADMIN_PASSWORD", "")
        if stored:
            valid = check_password_hash(stored, password)
        elif configured:
            valid = check_password_hash(configured, password) if configured.startswith(("pbkdf2:", "scrypt:")) else secrets.compare_digest(configured, password)
        else:
            valid = False
        if valid:
            session["admin_authenticated"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("كلمة مرور الإدارة غير صحيحة. إذا لم تُنشأ كلمة مرور بعد، نفّذ الأمر flask create-admin.", "error")
    return render_template("admin_login.html")


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin_login"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = now - timedelta(days=7)
    month = now - timedelta(days=30)
    revenue = lambda start: db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(
        Order.created_at >= start, Order.status != "cancelled").scalar()
    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()
    orders_query = Order.query
    if status in ORDER_STATUSES:
        orders_query = orders_query.filter_by(status=status)
    if search:
        like = f"%{search}%"
        orders_query = orders_query.filter(or_(Order.order_number.ilike(like),
                                               Order.full_name.ilike(like), Order.phone.ilike(like)))
    orders = orders_query.order_by(Order.created_at.desc()).limit(100).all()
    products = Product.query.order_by(Product.created_at.desc()).all()
    low_stock = Product.query.filter(Product.stock < 5).order_by(Product.stock).limit(10).all()
    top = db.session.query(OrderItem.product_name, func.sum(OrderItem.quantity).label("units")).group_by(
        OrderItem.product_name).order_by(text("units DESC")).limit(5).all()
    return render_template("admin.html", orders=orders, products=products,
                           categories=Category.query.order_by(Category.sort_order).all(),
                           statuses=ORDER_STATUSES, status_labels=STATUS_LABELS,
                           low_stock=low_stock, top_products=top,
                           sales_today=revenue(today), sales_week=revenue(week), sales_month=revenue(month),
                           search=search, selected_status=status)


@app.post("/admin/product/save")
@admin_required
def admin_product_save():
    product_id = request.form.get("product_id", type=int)
    product = db.session.get(Product, product_id) if product_id else Product()
    try:
        category = db.session.get(Category, int(request.form.get("category_id", "")))
        name, price = request.form.get("name", "").strip(), float(request.form.get("price", ""))
        stock = int(request.form.get("stock", ""))
        old_price = float(request.form.get("old_price") or 0)
        if not category or not name or not math.isfinite(price) or price <= 0 or old_price < 0 or stock < 0:
            raise ValueError("invalid product")
        product.name, product.name_fr = name, request.form.get("name_fr", "").strip()
        product.description = request.form.get("description", "").strip()
        product.description_fr = request.form.get("description_fr", "").strip()
        product.price, product.old_price, product.stock = price, old_price, stock
        product.category_id = category.id
        product.seller = request.form.get("seller", "").strip() or settings.STORE_NAME
        product.sku = request.form.get("sku", "").strip() or f"VZ-{secrets.token_hex(4).upper()}"
        duplicate_sku = Product.query.filter(Product.sku == product.sku, Product.id != product.id).first()
        if duplicate_sku:
            raise ValueError("SKU already exists")
        product.badge = request.form.get("badge", "").strip()
        product.is_active = request.form.get("is_active") == "1"
        product.is_featured = request.form.get("is_featured") == "1"
        product.is_deal = request.form.get("is_deal") == "1"
        product.is_trending = request.form.get("is_trending") == "1"
        product.is_new = request.form.get("is_new") == "1"
        if not product.slug or product.name != request.form.get("original_name", product.name):
            product.slug = f"{slugify(name)}-{secrets.token_hex(2)}"
        image_url = request.form.get("image_url", "").strip()
        images = [value.strip() for value in request.form.get("images", "").splitlines() if value.strip()]
        uploads = request.files.getlist("images_upload")
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        for uploaded in uploads:
            if uploaded and uploaded.filename:
                safe_name = secure_filename(uploaded.filename)
                if not safe_name or os.path.splitext(safe_name)[1].lower() not in {
                    ".png", ".jpg", ".jpeg", ".webp", ".gif",
                }:
                    raise ValueError("invalid image")
                filename = f"{secrets.token_hex(8)}-{safe_name}"
                uploaded.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                images.append(f"/static/uploads/{filename}")
        if image_url and not (image_url == "/static/placeholder.png" and images):
            product.image_url = image_url
        elif images:
            product.image_url = images[0]
        else:
            product.image_url = product.image_url or "/static/placeholder.png"
        product.images_json = json.dumps(images)
        db.session.add(product)
        db.session.commit()
        flash("تم حفظ المنتج.", "success")
    except (TypeError, ValueError) as error:
        db.session.rollback()
        flash("راجع بيانات المنتج والصور.", "error")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/product/<int:product_id>/delete")
@admin_required
def admin_product_delete(product_id):
    product = db.get_or_404(Product, product_id)
    product.is_active = False
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/category")
@admin_required
def admin_category_save():
    category_id = request.form.get("category_id", type=int)
    category = db.session.get(Category, category_id) if category_id else Category()
    name = request.form.get("name", "").strip()
    if name:
        duplicate_name = Category.query.filter(Category.name == name)
        duplicate_slug = Category.query.filter(Category.slug == slugify(name))
        if category:
            duplicate_name = duplicate_name.filter(Category.id != category.id)
            duplicate_slug = duplicate_slug.filter(Category.id != category.id)
        if duplicate_name.first() or duplicate_slug.first():
            flash("اسم الفئة مستخدم بالفعل.", "error")
            return redirect(url_for("admin_dashboard"))
        category.name = name
        category.slug = slugify(name)
        category.name_ar = request.form.get("name_ar", name)
        category.name_fr = request.form.get("name_fr", "")
        category.icon = request.form.get("icon", "✦")
        category.image_url = request.form.get("image_url", "/static/placeholder.png")
        category.sort_order = request.form.get("sort_order", 0, type=int)
        db.session.add(category)
        db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/category/<int:category_id>/delete")
@admin_required
def admin_category_delete(category_id):
    category = db.get_or_404(Category, category_id)
    if category.products:
        flash("انقل المنتجات إلى فئة أخرى قبل حذف هذه الفئة.", "error")
    else:
        db.session.delete(category)
        db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/order/<int:order_id>/status")
@admin_required
def update_order_status(order_id):
    order = db.get_or_404(Order, order_id)
    status = request.form.get("status", "")
    if status not in ORDER_STATUSES:
        abort(400)
    order.status = status
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.get("/admin/orders.csv")
@admin_required
def export_orders():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order", "Date", "Name", "Phone", "City", "Address", "Subtotal", "Shipping", "Discount", "Total", "Payment", "Status", "UTM"])
    for order in Order.query.order_by(Order.created_at.desc()).all():
        writer.writerow([order.order_number, order.created_at.isoformat(), order.full_name, order.phone, order.city,
                         order.address, order.subtotal, order.shipping_fee, order.discount, order.total,
                         order.payment_method, order.status, order.utm_json])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=orders.csv"})


@app.get("/admin/customers")
@admin_required
def admin_customers():
    customers = User.query.order_by(User.created_at.desc()).all()
    guest_orders = Order.query.filter(Order.user_id.is_(None)).order_by(Order.created_at.desc()).limit(100).all()
    return render_template("admin_customers.html", customers=customers, guest_orders=guest_orders)


@app.get("/admin/messages")
@admin_required
def admin_messages():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).limit(250).all()
    return render_template("admin_messages.html", messages=messages)


@app.post("/admin/message/<int:message_id>/status")
@admin_required
def admin_message_status(message_id):
    item = db.get_or_404(ContactMessage, message_id)
    status = request.form.get("status", "")
    if status not in {"new", "read", "resolved"}:
        abort(400)
    item.status = status
    db.session.commit()
    return redirect(url_for("admin_messages"))


@app.get("/admin/order/<int:order_id>/print")
@admin_required
def print_order(order_id):
    order = db.get_or_404(Order, order_id)
    return render_template("print_order.html", order=order)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    if request.method == "POST":
        try:
            fee = float(request.form.get("shipping_fee", ""))
            free_threshold = float(request.form.get("free_delivery_threshold", ""))
            color = request.form.get("primary_color", "")
            accent_color = request.form.get("accent_color", "")
            background_color = request.form.get("background_color", "")
            if not math.isfinite(fee) or not math.isfinite(free_threshold) or fee < 0 or free_threshold < 0:
                raise ValueError
            if any(not re.fullmatch(r"#[0-9a-fA-F]{6}", value)
                   for value in (color, accent_color, background_color)):
                raise ValueError
            city_fees = json.loads(request.form.get("city_fees", "{}") or "{}")
            if not isinstance(city_fees, dict) or any(
                not math.isfinite(float(amount)) or float(amount) < 0 for amount in city_fees.values()
            ):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            flash("يرجى التحقق من رسوم التوصيل وتنسيق رسوم المدن بصيغة JSON.", "error")
            return redirect(url_for("admin_settings"))
        for key in ("store_name", "logo_url", "favicon_url", "phone", "email", "whatsapp", "store_address",
                    "facebook", "instagram", "tiktok", "announcement", "announcement_fr", "shipping_fee",
                    "free_delivery_threshold", "city_fees", "payment_cod", "payment_card",
                    "payment_transfer", "delivery_days", "primary_color", "seo_title", "seo_description",
                    "accent_color", "background_color", "stat_rating", "stat_rating_label",
                    "stat_rating_label_fr", "stat_dispatch", "stat_dispatch_label", "stat_dispatch_label_fr",
                    "stat_customers", "stat_customers_label", "stat_customers_label_fr", "promo_coupon",
                    "promo_cod", "promo_consultation",
                    "facebook_pixel", "tiktok_pixel", "ga_id", "gtm_id"):
            set_setting(key, request.form.get(key, ""))
        new_password = request.form.get("admin_password", "")
        if new_password:
            if len(new_password) < 10:
                flash("كلمة مرور الإدارة يجب أن تكون 10 أحرف على الأقل.", "error")
                return redirect(url_for("admin_settings"))
            set_setting("admin_password_hash", generate_password_hash(new_password))
        db.session.commit()
        flash("تم حفظ الإعدادات.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html")


@app.post("/admin/backup")
@admin_required
def admin_backup():
    source = settings.INSTANCE_DIR / "vezzallo.sqlite3"
    if not source.exists():
        abort(404, "SQLite database not found.")
    import shutil
    destination = settings.INSTANCE_DIR / f"backup-{datetime.utcnow():%Y%m%d-%H%M%S}.sqlite3"
    shutil.copy2(source, destination)
    flash(f"تم إنشاء نسخة احتياطية: {destination.name}", "success")
    return redirect(url_for("admin_settings"))


@app.route("/admin/coupons", methods=["GET", "POST"])
@admin_required
def admin_coupons():
    if request.method == "POST":
        try:
            code = request.form.get("code", "").strip().upper()
            if Coupon.query.filter_by(code=code).first():
                raise ValueError()
            expires = request.form.get("expires_at")
            coupon = Coupon(code=code,
                            kind=request.form.get("kind", "percent"),
                            value=float(request.form.get("value", 0)),
                            min_order=float(request.form.get("min_order", 0)),
                            expires_at=date.fromisoformat(expires) if expires else None,
                            usage_limit=int(request.form.get("usage_limit", 0)))
            if (not coupon.code or coupon.value <= 0
                    or coupon.kind not in {"percent", "fixed"}
                    or (coupon.kind == "percent" and coupon.value > 100)):
                raise ValueError()
            db.session.add(coupon)
            db.session.commit()
        except (TypeError, ValueError):
            db.session.rollback()
            flash("تحقق من بيانات القسيمة.", "error")
        return redirect(url_for("admin_coupons"))
    return render_template("admin_coupons.html", coupons=Coupon.query.order_by(Coupon.id.desc()).all())


@app.post("/admin/coupon/<int:coupon_id>/delete")
@admin_required
def admin_coupon_delete(coupon_id):
    coupon = db.get_or_404(Coupon, coupon_id)
    db.session.delete(coupon)
    db.session.commit()
    return redirect(url_for("admin_coupons"))


@app.route("/admin/content", methods=["GET", "POST"])
@admin_required
def admin_content():
    if request.method == "POST":
        kind = request.form.get("kind")
        if kind == "banner":
            banner = db.session.get(Banner, request.form.get("banner_id", type=int)) or Banner()
            banner.title = request.form.get("title", "")
            banner.subtitle = request.form.get("subtitle", "")
            banner.image_url = request.form.get("image_url", "/static/placeholder.png")
            banner.link_url = request.form.get("link_url", "/")
            banner.active = request.form.get("active") == "1"
            banner.sort_order = request.form.get("sort_order", 0, type=int)
            db.session.add(banner)
        elif kind == "page":
            slug = request.form.get("slug", "")
            page = db.session.get(StorePage, slug) or StorePage(slug=slug, title=request.form.get("title", ""))
            page.title, page.body = request.form.get("title", ""), request.form.get("body", "")
            db.session.add(page)
        db.session.commit()
        return redirect(url_for("admin_content"))
    return render_template("admin_content.html", banners=Banner.query.all(), pages=StorePage.query.all())


@app.get("/p/<slug>")
def page(slug):
    page_data = db.session.get(StorePage, slug)
    if not page_data:
        abort(404)
    return render_template("page.html", page_data=page_data)


@app.get("/robots.txt")
def robots():
    return Response(f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {url_for('sitemap', _external=True)}\n", mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    urls = [url_for("index", _external=True)]
    urls.extend(url_for("product_detail", slug=p.slug, _external=True) for p in Product.query.filter_by(is_active=True).all())
    xml = '<?xml version="1.0" encoding="UTF-8"?>' + "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">" + "".join(f"<url><loc>{url}</loc></url>" for url in urls) + "</urlset>"
    return Response(xml, mimetype="application/xml")


@app.cli.command("create-admin")
def create_admin():
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        password = input("Admin password (10+ characters): ")
    if len(password) < 10:
        raise SystemExit("Admin password must be at least 10 characters.")
    set_setting("admin_password_hash", generate_password_hash(password))
    db.session.commit()
    print("Admin password hash saved.")


@app.cli.command("backup-db")
def backup_db():
    source = settings.INSTANCE_DIR / "vezzallo.sqlite3"
    destination = settings.INSTANCE_DIR / f"backup-{datetime.utcnow():%Y%m%d-%H%M%S}.sqlite3"
    if not source.exists():
        raise SystemExit("SQLite database not found.")
    import shutil
    shutil.copy2(source, destination)
    print(f"Database backup created at {destination}")


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
