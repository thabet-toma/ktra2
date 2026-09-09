"""تكوين تطبيق عمليات المنصة (platform_ops)."""
from django.apps import AppConfig


class PlatformOpsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "platform_ops"
    verbose_name = "عمليات المنصة"

    def ready(self):
        from core.signals import company_member_changed
        from .receivers import handle_company_member_changed

        company_member_changed.connect(handle_company_member_changed)
