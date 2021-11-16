import os

import django.db.models

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
    "nuntius",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "standalone.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.mysql"),
        "NAME": os.environ.get("DB_NAME", "nuntius"),
        "USER": os.environ.get("DB_USER", "nuntius"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "password"),
    }
}
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
NUNTIUS_PUSH_NOTIFICATION_SETTINGS = {
    "UPDATE_ON_DUPLICATE_REG_ID": True,
    "UNIQUE_REG_ID": True,
    "APNS_AUTH_KEY_PATH": os.environ.get(
        "APNS_AUTH_KEY_PATH", os.path.join(os.path.dirname(BASE_DIR), "..", "apns.p8")
    ),
    "APNS_AUTH_KEY_ID": os.environ.get("APNS_AUTH_KEY_ID"),
    "APNS_TEAM_ID": os.environ.get("APNS_TEAM_ID"),
    "APNS_TOPIC": os.environ.get("APNS_TOPIC", "fr.nuntius.ios"),
    "APNS_USE_SANDBOX": os.environ.get("APNS_USE_SANDBOX", "true").lower() == "true",
    "FCM_API_KEY": os.environ.get("FCM_API_KEY", "[your api key]"),
}

MEDIA_URL = "/media/"
MEDIA_ROOT = "media"

EMAIL_HOST = "localhost"
EMAIL_PORT = "1025"

ANYMAIL_WEBHOOK_SECRET = "test:test"

if "push" in NUNTIUS_ENABLED_CAMPAIGN_TYPES:
    INSTALLED_APPS.append("push_notifications")
