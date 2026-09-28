"""مزوّد فرض الرقم التسلسلي — يُسجَّل في `core.hooks` ويُنادى من `inventory.serials`
(`effective_serial_mode`، #233).

فحص الترخيص أول سطر: شركةٌ غير مرخّصة للوحدة تخرج بلا أي استعلام (fail-closed)
— على نمط `accountant_portal.guards.tax_period_lock_guard`.
"""


def serial_requirement_provider(tenant_id, product_ids) -> dict:
    from core.modules import module_enabled

    if not module_enabled(tenant_id, "after_sales"):
        return {}

    from .models import WarrantyPolicy

    return {
        product_id: "المنتج مكفول بسياسة كفالة «برقم تسلسلي» — إدخال الرقم إجباري عند البيع."
        for product_id in WarrantyPolicy.objects.filter(
            tenant_id=tenant_id,
            product_id__in=list(product_ids),
            method=WarrantyPolicy.METHOD_SERIAL,
        ).values_list("product_id", flat=True)
    }


def register_hooks():
    from core.hooks import register_serial_requirement

    register_serial_requirement(serial_requirement_provider)
