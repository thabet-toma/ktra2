from django.apps import AppConfig


class LogisticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "logistics"

    def ready(self):
        """التحام واحد: مزوّد تكلفة بنود الفاتورة الدولية لـ«تكلفة المنتجات» في inventory."""
        from core.hooks import register_purchase_line_cost_provider
        from logistics.services import posted_goods_line_costs

        register_purchase_line_cost_provider(posted_goods_line_costs)
