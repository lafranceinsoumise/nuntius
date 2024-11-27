from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _
from django.conf import settings

CAMPAIGN_TYPE_EMAIL = "email"
CAMPAIGN_TYPE_PUSH = "push"
ENABLED_CAMPAIGN_TYPES = getattr(
    settings, "NUNTIUS_ENABLED_CAMPAIGN_TYPES", [CAMPAIGN_TYPE_EMAIL]
)

# Segment and subscribers models
try:
    NUNTIUS_SEGMENT_MODEL = settings.NUNTIUS_SEGMENT_MODEL
    NUNTIUS_SUBSCRIBER_MODEL = settings.NUNTIUS_SUBSCRIBER_MODEL
except AttributeError:
    raise ImproperlyConfigured(
        "Both NUNTIUS_SEGMENT_MODEL and NUNTIUS_SUBSCRIBER_MODEL must be set to valid and existing models. See documentation for more information."
    )

MOSAICO_TEMPLATES = getattr(
    settings,
    "NUNTIUS_MOSAICO_TEMPLATES",
    [
        (
            f"{settings.STATIC_URL}/nuntius/templates/versafix-1/template-versafix-1.html",
            _("Default template"),
        )
    ],
)

DEFAULT_FROM_EMAIL = getattr(settings, "NUNTIUS_DEFAULT_FROM_EMAIL", "")
DEFAULT_FROM_NAME = getattr(settings, "NUNTIUS_DEFAULT_FROM_NAME", "")
DEFAULT_REPLY_TO_EMAIL = getattr(settings, "NUNTIUS_DEFAULT_REPLY_TO_EMAIL", "")
DEFAULT_REPLY_TO_NAME = getattr(settings, "NUNTIUS_DEFAULT_REPLY_TO_NAME", "")

DISABLE_DEFAULT_ADMIN = getattr(settings, "NUNTIUS_DISABLE_DEFAULT_ADMIN", False)

PUBLIC_URL = getattr(settings, "NUNTIUS_PUBLIC_URL", None)
IMAGES_URL = getattr(settings, "NUNTIUS_IMAGES_URL", PUBLIC_URL)
LINKS_URL = getattr(settings, "NUNTIUS_LINKS_URL", PUBLIC_URL)

BOUNCE_PARAMS = {
    "consecutive": 1,
    "duration": 7,
    "limit": 3,
    **getattr(settings, "NUNTIUS_BOUNCE_PARAMS", {}),
}
EMAIL_BACKEND = getattr(settings, "NUNTIUS_EMAIL_BACKEND", None)

# Maximum rate with which emails may be sent, by number of emails per second
MAX_SENDING_RATE = getattr(settings, "NUNTIUS_MAX_SENDING_RATE", 50)

# Number of concurrent sending processes to send emails
MAX_CONCURRENT_SENDERS = getattr(settings, "NUNTIUS_MAX_CONCURRENT_SENDERS", 4)

# Maximum number of messages that may be sent over a single SMTP connection
MAX_MESSAGES_PER_CONNECTION = getattr(
    settings, "NUNTIUS_MAX_MESSAGES_PER_SMTP_CONNECTION", 500
)

# Interval of time, in seconds, with which the worker must check for campaign status changes
POLLING_INTERVAL = getattr(settings, "NUNTIUS_POLLING_INTERVAL", 2)

if CAMPAIGN_TYPE_PUSH in ENABLED_CAMPAIGN_TYPES:
    try:
        PUSH_NOTIFICATION_SETTINGS = settings.NUNTIUS_PUSH_NOTIFICATION_SETTINGS
    except AttributeError:
        raise ImproperlyConfigured(
            "Push campaigns have been enabled without specifying a configuration. Either remove push from the list of "
            "enabled campaign, or add a valid 'django-push-notification' configuration ("
            "settings.NUNTIUS_PUSH_NOTIFICATION_SETTINGS)."
        )
if not hasattr(settings, "NUNTIUS_PERFORMANCE"):
    settings.NUNTIUS_PERFORMANCE = {}

settings.NUNTIUS_PERFORMANCE = {
    "CAMPAIGN_SENT_EVENT_DISABLE_FULL_PAGINATION": False,
    **settings.NUNTIUS_PERFORMANCE
}
