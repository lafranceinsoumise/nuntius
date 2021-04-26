from django.apps import AppConfig as BaseAppConfig
from django.utils.translation import gettext_lazy as _


class AppConfig(BaseAppConfig):
    name = "standalone"
    verbose_name = _("Nuntius standalone")
