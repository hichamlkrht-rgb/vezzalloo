import os

from werkzeug.security import generate_password_hash

from app import (
    Banner, Category, Product, StorePage, StoreSetting, app, db, migrate_existing_database,
    set_setting, slugify,
)
import settings

CATEGORIES = [
    ("Electronics", "الإلكترونيات", "Électronique", "▣"),
    ("Accessories", "الإكسسوارات", "Accessoires", "✦"),
    ("Clothing", "الملابس", "Vêtements", "◇"),
    ("Beauty", "الجمال والعناية", "Beauté & soin", "♡"),
    ("Home", "المنزل والمطبخ", "Maison & cuisine", "⌂"),
]

CATALOG = {
    "Electronics": [
        ("سماعات أذن لاسلكية", "Écouteurs sans fil", 199),
        ("ساعة ذكية متعددة الوظائف", "Montre intelligente", 349),
        ("بطارية متنقلة 20000mAh", "Batterie externe 20000mAh", 179),
        ("مكبر صوت بلوتوث", "Enceinte Bluetooth", 249),
        ("حلقة إضاءة للتصوير", "Anneau lumineux", 159),
        ("جهاز عرض منزلي صغير", "Mini projecteur", 899),
        ("حامل هاتف للسيارة", "Support téléphone voiture", 99),
        ("شاحن سريع 65W", "Chargeur rapide 65W", 149),
    ],
    "Accessories": [
        ("غطاء هاتف أنيق", "Coque de téléphone", 59),
        ("واقي شاشة مقاوم للخدش", "Protection écran", 39),
        ("حقيبة ظهر عملية", "Sac à dos pratique", 229),
        ("نظارات شمسية UV400", "Lunettes de soleil UV400", 129),
        ("محفظة جلدية", "Portefeuille élégant", 119),
        ("سوار يومي بسيط", "Bracelet quotidien", 69),
        ("سوار ساعة قابل للتبديل", "Bracelet de montre", 49),
        ("منظم للكابلات", "Organisateur de câbles", 35),
    ],
    "Clothing": [
        ("قميص قطني أساسي", "T-shirt en coton", 99),
        ("هودي دافئ", "Sweat à capuche", 249),
        ("طقم رياضي مريح", "Ensemble de jogging", 299),
        ("حذاء رياضي خفيف", "Sneakers légères", 349),
        ("عباية أنيقة", "Abaya élégante", 279),
        ("وشاح ناعم", "Écharpe douce", 89),
        ("سترة يومية", "Veste quotidienne", 319),
        ("جوارب قطنية (3 قطع)", "Chaussettes coton (3 paires)", 49),
    ],
    "Beauty": [
        ("سيروم فيتامين C", "Sérum vitamine C", 129),
        ("كريم ترطيب يومي", "Crème hydratante", 109),
        ("مجفف شعر عملي", "Sèche-cheveux", 299),
        ("آلة تشذيب متعددة الاستخدام", "Tondeuse multifonction", 189),
        ("عطر نسائي أنيق", "Parfum élégant", 199),
        ("زيت أركان طبيعي", "Huile d'argan", 119),
        ("مجموعة فرش مكياج", "Set de pinceaux", 139),
        ("مملس شعر سيراميك", "Lisseur céramique", 249),
    ],
    "Home": [
        ("غلاية ماء كهربائية", "Bouilloire électrique", 179),
        ("خلاط كهربائي متعدد السرعات", "Blender multifonction", 249),
        ("علب تخزين للمطبخ", "Boîtes de rangement", 89),
        ("شريط إضاءة LED", "Bande lumineuse LED", 99),
        ("قلاية هوائية عائلية", "Friteuse sans huile", 799),
        ("قارورة حرارية", "Bouteille isotherme", 119),
        ("ميزان مطبخ رقمي", "Balance de cuisine", 79),
        ("منظم متعدد الاستعمال", "Organisateur polyvalent", 99),
    ],
}


def seed():
    with app.app_context():
        db.create_all()
        migrate_existing_database()
        category_map = {}
        for index, (name, arabic, french, icon) in enumerate(CATEGORIES):
            category = Category.query.filter_by(name=name).first()
            if category is None:
                category = Category(name=name, slug=slugify(name), name_ar=arabic,
                                    name_fr=french, icon=icon, sort_order=index)
                db.session.add(category)
            else:
                category.name_ar, category.name_fr, category.icon = arabic, french, icon
            category_map[name] = category
        db.session.flush()
        legacy_fashion = Category.query.filter_by(name="Fashion").first()
        if legacy_fashion and legacy_fashion.id != category_map["Clothing"].id:
            Product.query.filter_by(category_id=legacy_fashion.id).update(
                {Product.category_id: category_map["Clothing"].id}
            )
            db.session.delete(legacy_fashion)
        for category_name, records in CATALOG.items():
            category = category_map[category_name]
            for index, (arabic, french, price) in enumerate(records):
                sku = f"VZ-{category_name[:3].upper()}-{index + 1:03}"
                product = Product.query.filter_by(sku=sku).first()
                if product is None:
                    product = Product(
                        name=arabic, slug=f"{slugify(french)}-{sku.lower()}",
                        name_fr=french, description=f"{arabic} بجودة مناسبة وتصميم عملي للاستعمال اليومي.",
                        description_fr=f"{french} de qualité, pratique pour un usage quotidien.",
                        price=price, old_price=round(price * 1.25), stock=50, sku=sku,
                        seller=settings.STORE_NAME, image_url="/static/placeholder.png",
                        category_id=category.id, is_active=True, is_featured=index < 2,
                        is_deal=index in (1, 4), is_trending=index in (0, 2),
                        is_new=index >= 6,
                    )
                    db.session.add(product)
        defaults = {
            "store_name": settings.STORE_NAME,
            "announcement": "توصيل مجاني عبر المغرب ابتداءً من 500 DH",
            "announcement_fr": "Livraison gratuite partout au Maroc",
            "shipping_fee": settings.SHIPPING_FEE,
            "free_delivery_threshold": settings.FREE_SHIPPING_THRESHOLD,
            "delivery_days": "2-5 أيام",
            "whatsapp": settings.WHATSAPP_NUMBER,
            "payment_cod": "1", "payment_card": "0", "payment_transfer": "0",
            "primary_color": "#ff9800",
            "accent_color": "#ff9800",
            "background_color": "#fffaf4",
        }
        for key, value in defaults.items():
            if db.session.get(StoreSetting, key) is None:
                set_setting(key, value)
        announcement = db.session.get(StoreSetting, "announcement")
        if announcement and announcement.value == "توصيل مجاني عبر المغرب ابتداءً من 500 DH":
            announcement.value = "توصيل مجاني عبر المغرب"
        if not Banner.query.first():
            db.session.add(Banner(title="اختيارات زوينة لكل نهار", subtitle="تسوق بثقة، والتوصيل حتى لباب دارك",
                                  image_url="/static/placeholder.png", link_url="/"))
        for slug, title in (("about", "من نحن"), ("returns", "الإرجاع والاستبدال"),
                            ("terms", "الشروط والأحكام"), ("privacy", "الخصوصية")):
            if db.session.get(StorePage, slug) is None:
                db.session.add(StorePage(slug=slug, title=title, body="يمكنك تعديل هذه الصفحة من لوحة الإدارة."))
        if db.session.get(StoreSetting, "admin_password_hash") is None:
            password = os.environ.get("ADMIN_PASSWORD", "VezzalloAdmin2026!")
            set_setting("admin_password_hash", generate_password_hash(password))
        db.session.commit()
        seeded_count = Product.query.filter(Product.sku.like("VZ-%-%")).count()
        print(f"Seed complete: {Category.query.count()} categories, {seeded_count} catalog products added by seed.")
        if not os.environ.get("ADMIN_PASSWORD"):
            print("Admin login: /admin/login — password: VezzalloAdmin2026! (change it after login)")


if __name__ == "__main__":
    seed()
