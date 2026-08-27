"""محرّك الكفالة — دورة حياة بطاقة الكفالة التلقائية وفحص التغطية.

نقطتا التحام اثنتان لا ثالثة لهما:

- `create_auto_warranty_cards` بعد استهلاك الوحدات في ترحيل فاتورة البيع.
- `delete_auto_warranty_cards` عند إلغاء الترحيل (حذفٌ لا تعطيل — نمط
  `unpost_document` نفسه)، وإعادة الترحيل تُنشئها من جديد.

**صفر أثر على شركة غير مرخّصة:** الدالتان تخرجان فوراً إن لم تكن الوحدة
مرخّصة، فلا يكتب النظامُ صفاً في جدولٍ لا تراه الشركة أصلاً.
"""
import logging
from datetime import date

from core.modules import module_enabled

from .models import AfterSalesSettings, WarrantyCard, add_months
from django.utils import timezone

logger = logging.getLogger(__name__)

MODULE_KEY = "after_sales"


def get_or_create_after_sales_settings(tenant_id: int) -> AfterSalesSettings:
    settings_row, _ = AfterSalesSettings.objects.get_or_create(tenant_id=tenant_id)
    return settings_row


def _supplier_side(unit, supplier_months: int):
    """(المورد، نهاية كفالته) من نسب الوحدة الشرائي — لا تخمين ولا افتراضي.

    الوحدة تحمل بند فاتورة الشراء الذي أدخلها المخزن؛ منه تاريخ الشراء والمورد.
    وحدة بلا نسب (مخزون سابق للتتبّع) تُعطي بطاقةً بلا جانب مورد، وهذا أصدق من
    اشتقاق تاريخٍ من فاتورة البيع.
    """
    item = unit.purchase_item if unit.purchase_item_id else None
    purchase_invoice = item.invoice if (item and item.invoice_id) else None
    if purchase_invoice is None:
        return None, None

    supplier_id = purchase_invoice.partner_id
    purchase_date = purchase_invoice.invoice_date
    if not supplier_months or purchase_date is None:
        return supplier_id, None
    return supplier_id, add_months(purchase_date, supplier_months)


def create_auto_warranty_cards(invoice) -> int:
    """يُنشئ بطاقة كفالة لكل وحدة متسلسلة استهلكها ترحيل هذه الفاتورة.

    البداية = **تاريخ الفاتورة** لا تاريخ الترحيل ولا التسليم: تاريخ المستند هو
    ما تُقيَّد به الدفاتر كلها، وحالة التسليم مشتقّة وقد تغيب أصلاً.

    غير المتسلسل لا بطاقة تلقائية له: كمية بلا هوية وحدة تجعل البطاقة بلا معنى،
    والتغطية تُفحص عندها من فاتورة الزبون لحظة الاستقبال.
    """
    from inventory.models import ProductSerial

    if not module_enabled(invoice.tenant_id, MODULE_KEY):
        return 0

    units = (
        ProductSerial.objects
        .filter(
            tenant_id=invoice.tenant_id,
            sales_line__invoice=invoice,
            status=ProductSerial.STATUS_SOLD,
        )
        .select_related("product", "purchase_item__invoice")
        .order_by("id")
    )
    units = list(units)
    if not units:
        return 0

    # حصر «بطاقة حيّة واحدة لكل وحدة» في الكود: MySQL لا تدعم فرادةً شرطية،
    # والاستعلام مرة واحدة للدفعة كلها لا مرة لكل وحدة.
    already_carded = set(
        WarrantyCard.objects
        .filter(tenant_id=invoice.tenant_id, product_serial__in=[u.pk for u in units])
        .values_list("product_serial_id", flat=True)
    )

    customer = invoice.customer if invoice.customer_id else None
    created = []
    for unit in units:
        if unit.pk in already_carded:
            continue
        months = int(getattr(unit.product, "warranty_months", 0) or 0)
        if months <= 0:
            continue
        supplier_id, supplier_end = _supplier_side(
            unit, int(getattr(unit.product, "supplier_warranty_months", 0) or 0),
        )
        created.append(WarrantyCard(
            tenant_id=invoice.tenant_id,
            product=unit.product,
            device_name=str(unit.product),
            serial=unit.serial,
            product_serial=unit,
            sales_invoice_line_id=unit.sales_line_id,
            partner_id=invoice.customer_id,
            customer_name=(customer.name if customer else "")[:150],
            customer_phone=(getattr(customer, "phone", "") or "")[:32] if customer else "",
            start_date=invoice.invoice_date,
            duration_months=months,
            end_date=add_months(invoice.invoice_date, months),
            source=WarrantyCard.SOURCE_AUTO_SALE,
            supplier_id=supplier_id,
            supplier_warranty_end_date=supplier_end,
        ))

    if not created:
        return 0
    WarrantyCard.objects.bulk_create(created)
    logger.info(
        "after_sales.warranty_cards_created invoice=%s tenant=%s cards=%d",
        invoice.pk, invoice.tenant_id, len(created),
    )
    return len(created)


def delete_auto_warranty_cards(invoice) -> int:
    """يحذف بطاقات هذه الفاتورة التلقائية وحدها — اليدوية لا تُمَسّ.

    المرساة هي بند الفاتورة (`sales_invoice_line`) لا رابط الوحدة: إلغاء
    الترحيل يُفرِّغ `ProductSerial.sales_line` فيضيع الأثر لو اعتمدنا عليه.
    """
    deleted, _ = (
        WarrantyCard.objects
        .filter(
            tenant_id=invoice.tenant_id,
            source=WarrantyCard.SOURCE_AUTO_SALE,
            sales_invoice_line__invoice=invoice,
        )
        .delete()
    )
    if deleted:
        logger.info(
            "after_sales.warranty_cards_deleted invoice=%s tenant=%s cards=%d",
            invoice.pk, invoice.tenant_id, deleted,
        )
    return deleted


# ══════════════════════════════════════════════════════════════════════════
# فحص التغطية — الجواب الواحد على «هل هذه الوحدة تحت الكفالة؟»
# ══════════════════════════════════════════════════════════════════════════

def _card_summary(card, today: date) -> dict:
    return {
        "id": card.pk,
        "serial": card.serial,
        "product": card.product_id,
        "device_name": card.device_name,
        "start_date": card.start_date,
        "end_date": card.end_date,
        "duration_months": card.duration_months,
        "source": card.source,
        "status": card.status_on(today),
        "days_remaining": card.days_remaining(today),
        "customer_name": card.customer_name,
        "partner": card.partner_id,
        "supplier": card.supplier_id,
        "supplier_warranty_end_date": card.supplier_warranty_end_date,
        "supplier_warranty_active": card.supplier_active_on(today),
    }


def warranty_coverage(tenant_id: int, serial: str, today: date | None = None) -> dict:
    """التغطية بحسب رقم تسلسلي واحد — البطاقة أولاً، ثم نسب الوحدة.

    وحدةٌ بعناها قبل ترخيص الوحدة (أو منتجٌ بلا سياسة كفالة) لا بطاقة لها؛ نردّ
    عندها ما نعرفه عن الوحدة نفسها (منتجها وفاتورتها وزبونها) كي يقرّر موظف
    الاستقبال بدل أن يرى «غير موجود» على وحدةٍ بعناها بأنفسنا.
    """
    from inventory.models import ProductSerial

    today = today or timezone.localdate()
    serial = (serial or "").strip()
    if not serial:
        return {"serial": "", "covered": False, "cards": [], "unit": None}

    cards = list(
        WarrantyCard.objects
        .filter(tenant_id=tenant_id, serial=serial)
        .select_related("product")
        .order_by("-end_date", "-id")
    )
    unit = (
        ProductSerial.objects
        .filter(tenant_id=tenant_id, serial=serial)
        .select_related("product", "sales_line__invoice__customer")
        .order_by("-id")
        .first()
    )

    unit_info = None
    if unit is not None:
        sales_line = unit.sales_line if unit.sales_line_id else None
        sales_invoice = (
            sales_line.invoice if (sales_line and sales_line.invoice_id) else None
        )
        unit_info = {
            "id": unit.pk,
            "serial": unit.serial,
            "status": unit.status,
            "status_display": unit.get_status_display(),
            "product": unit.product_id,
            "product_name": str(unit.product),
            "warranty_months": getattr(unit.product, "warranty_months", None),
            "supplier_warranty_months": getattr(
                unit.product, "supplier_warranty_months", None,
            ),
            "sales_invoice": sales_invoice.pk if sales_invoice else None,
            "sales_invoice_number": (
                sales_invoice.invoice_number if sales_invoice else None
            ),
            "sale_date": sales_invoice.invoice_date if sales_invoice else None,
            "customer_name": (
                sales_invoice.customer.name
                if sales_invoice and sales_invoice.customer_id else None
            ),
        }

    summaries = [_card_summary(c, today) for c in cards]
    return {
        "serial": serial,
        "covered": any(s["status"] == "active" for s in summaries),
        "supplier_covered": any(s["supplier_warranty_active"] for s in summaries),
        "cards": summaries,
        "unit": unit_info,
    }
