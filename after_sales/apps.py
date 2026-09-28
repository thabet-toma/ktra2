from django.apps import AppConfig


class AfterSalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "after_sales"
    verbose_name = "خدمة ما بعد البيع"

    def ready(self):
        """التحام واحد: تسجيل مزوّد فرض الرقم التسلسلي (#233) — بلا إشارات ولا مهام دورية."""
        from after_sales.hooks import register_hooks

        register_hooks()
