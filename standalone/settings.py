import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBUG = True
SECRET_KEY = "fake-key"
INSTALLED_APPS = [
    "standalone",
    "django.contrib.contenttypes",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "push_notifications",
    "nuntius"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware"
]

ROOT_URLCONF = "standalone.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR + "/nuntius/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {"default": dj_database_url.config(default="sqlite:///db.sqlite3")}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"level": "DEBUG", "class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": True},
        "nuntius": {"handlers": ["console"], "level": "DEBUG", "propagate": True},
    },
}


STATIC_URL = "/static/"

USE_I18N = True
LANGUAGE_CODE = os.environ.get("LANGUAGE_CODE", "en")

NUNTIUS_PUBLIC_URL = os.environ.get("NUNTIUS_PUBLIC_URL", "http://localhost:8000")
NUNTIUS_ENABLED_CAMPAIGN_TYPES = os.environ.get(
    "NUNTIUS_ENABLED_CAMPAIGN_TYPES", "email"
).split(",")
NUNTIUS_DISABLE_DEFAULT_ADMIN = True
NUNTIUS_SEGMENT_MODEL = "standalone.Segment"
NUNTIUS_SUBSCRIBER_MODEL = "standalone.Subscriber"
# Emails
NUNTIUS_DEFAULT_FROM_EMAIL = "test@example.com"
NUNTIUS_DEFAULT_FROM_NAME = "Sender"
NUNTIUS_DEFAULT_REPLY_TO_EMAIL = "replyto@example.com"
NUNTIUS_DEFAULT_REPLY_TO_NAME = "Reply to me"

# Push notifications
import firebase_admin
from firebase_admin import credentials

if os.environ.get("FIREBASE_CERT_PATH") is not None:
    cred = credentials.Certificate(os.environ.get("FIREBASE_CERT_PATH"))
    firebase_app = firebase_admin.initialize_app(cred)
else:
    firebase_app = firebase_admin.initialize_app()

NUNTIUS_PUSH_NOTIFICATION_SETTINGS = {
    "UPDATE_ON_DUPLICATE_REG_ID": True,
    "UNIQUE_REG_ID": True,
    # PLATFORM (required) determines what additional settings are required.
    "PLATFORM": "FCM",
    "FIREBASE_APP": firebase_app,
}

MEDIA_URL = "/media/"
MEDIA_ROOT = "media"

EMAIL_HOST = "localhost"
EMAIL_PORT = "1025"

ANYMAIL_WEBHOOK_SECRET = "test:test"

if "push" in NUNTIUS_ENABLED_CAMPAIGN_TYPES:
    try:
        import push_notifications
    except ModuleNotFoundError:
        raise ImproperlyConfigured(
            'You activated push notifications but did not install optional dependencies. Use poetry install --extras "push"'
        )
    INSTALLED_APPS.append("push_notifications")
