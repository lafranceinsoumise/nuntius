from django.apps import AppConfig


class NuntiusConfig(AppConfig):
    name = "nuntius"

    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from . import signals
