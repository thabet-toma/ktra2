"""جسور `after_sales` إلى `core.hooks` — تُسجَّل عند الإقلاع (`AppConfig.ready`).

- مزوّد فرض الرقم التسلسلي: يُنادى من `inventory.serials` (`effective_serial_mode`، #233).
- امتداد سطر فاتورة الشراء `manufacturer_warranty`: تقرؤه وتكتبه `logistics`
  عبر `core.hooks` دون أن تعرف اسمه (#235).

فحص الترخيص أول سطر في كلٍّ منها: شركةٌ غير مرخّصة للوحدة تخرج بلا أي استعلام
(fail-closed) — على نمط `accountant_portal.guards.tax_period_lock_guard`.
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


def purchase_line_warranty_read(tenant_id, items) -> dict:
    """`{item_id: كفالة السطر}` بنداءٍ واحدٍ للفاتورة — الوحدة المطفأة تقرأ فارغاً."""
    from core.modules import module_enabled

    if not module_enabled(tenant_id, "after_sales"):
        return {}

    from .models import PurchaseLineWarranty

    return {
        row.purchase_item_id: {
            "manufacturer_warrantor": row.manufacturer_warrantor_id,
            "manufacturer_months": row.manufacturer_months,
            "supplier_months": row.supplier_months,
        }
        for row in PurchaseLineWarranty.objects.filter(
            tenant_id=tenant_id, purchase_item_id__in=[item.pk for item in items],
        )
    }


def purchase_line_warranty_write(tenant_id, item, payload, user) -> None:
    """يحفظ كفالة السطر داخل معاملة حفظ الفاتورة؛ الخطأ يُسقط الحفظ كلَّه.

    الوحدة المطفأة تُهمل الحمولة بصمت — لا صفَّ يُكتب في جدولٍ لا تراه الشركة.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError
    from rest_framework import serializers

    from core.modules import module_enabled

    if not module_enabled(tenant_id, "after_sales"):
        return

    from .services import purchase_line_label, save_purchase_line_warranty

    try:
        save_purchase_line_warranty(
            tenant_id, item, payload, user, purchase_line_label(item),
        )
    except DjangoValidationError as error:
        raise serializers.ValidationError({"items": error.messages}) from error


def register_hooks():
    from core.hooks import register_purchase_line_extension, register_serial_requirement

    register_serial_requirement(serial_requirement_provider)
    register_purchase_line_extension(
        "manufacturer_warranty", purchase_line_warranty_read, purchase_line_warranty_write,
    )
