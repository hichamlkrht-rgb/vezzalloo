import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

STORE_NAME = "Vezzallo"
CURRENCY = "DH"
CURRENCY_AR = "درهم"
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "+212600000000")
SHIPPING_FEE = 30
FREE_SHIPPING_THRESHOLD = 500

SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "DATABASE_URL", f"sqlite:///{(INSTANCE_DIR / 'vezzallo.sqlite3').as_posix()}"
)
SQLALCHEMY_TRACK_MODIFICATIONS = False
WTF_CSRF_ENABLED = True
WTF_CSRF_FIELD_NAME = "_csrf_token"
