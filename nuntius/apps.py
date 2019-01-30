from django.apps import AppConfig


class NuntiusConfig(AppConfig):
    name = "nuntius"

    def ready(self):
        from . import signals
