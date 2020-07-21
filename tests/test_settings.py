import os

from django.conf.global_settings import DEFAULT_FILE_STORAGE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBUG = True
SECRET_KEY = "fake-key"
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tests",
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

ROOT_URLCONF = "tests.urls"

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
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(BASE_DIR, "nuntius.sqlite3"),
    }
}

STATIC_URL = "/static/"

USE_I18N = True
LANGUAGE_CODE = os.environ.get("LANGUAGE_CODE", "en")

NUNTIUS_SEGMENT_MODEL = "tests.testsegment"
NUNTIUS_SUBSCRIBER_MODEL = "tests.TestSubscriber"
NUNTIUS_CELERY_BROKER_URL = "redis://"
NUNTIUS_MOSAICO_TEMPLATES = [
    ("/static/mosaico_templates/versafix-2/template-versafix-2.html", "Custom template")
]

MEDIA_URL = "/media/"
MEDIA_ROOT = "media"

EMAIL_HOST = "localhost"
EMAIL_PORT = "1025"

ANYMAIL_WEBHOOK_SECRET = "test:test"

CELERY_BROKER_URL = "redis://"
