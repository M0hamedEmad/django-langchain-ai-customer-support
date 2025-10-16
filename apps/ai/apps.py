from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"

    def ready(self):
        # Register deps-cache invalidation signals.
        from apps.ai.services import signals  # noqa: F401
