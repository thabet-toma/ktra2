"""تكوين تطبيق عمليات المنصة (platform_ops)."""
from django.apps import AppConfig


class PlatformOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_ops"
    verbose_name = "عمليات المنصة"
