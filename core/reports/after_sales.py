"""T-REPORTS × THA-24 م5 — تقارير خدمة ما بعد البيع.

ثلاثة أسئلة يسألها التاجر ولا يجيبها أي تقرير قائم:
- ما الكفالات التي توشك أن تنتهي؟ (فرصة تجديد، ومنعُ مطالبةٍ متأخرة)
- ما الأجهزة العالقة عندي الآن، ومنذ متى؟ (العمر هو ما يُغضب الزبون لا العدد)
- كم كلّفتني الكفالة هذه الفترة؟ (مصروف تشغيلي حقيقي كان مخفياً في المخزون)

كلها **مقيّدة بالوحدة المرخّصة** (`module="after_sales"` ⇒ 404 لا 403) وبمفاتيح
صلاحياتها. والثالث يقرأ حركات `SERVICE_ISSUE` وحدها — النوع نفسه الذي يُبقي
مصروف الكفالة خارج تكلفة المبيع، فلا يختلط الرقمان هنا كما لم يختلطا هناك.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from django.utils import timezone

from ._framework import (
    KIND_DATE,
    KIND_INT,
    KIND_MONEY,
    KIND_NUMBER,
    KIND_TEXT,
    DATE_FILTERS,
    ReportColumn,
    ReportFilter,
    ReportSpec,
    _apply_dates,
    _int_param,
    _money,
    _qty,
    register,
)

MODULE = "after_sales"

PERM_WARRANTY_VIEW = "aftersales.warranty.view"
PERM_ORDER_VIEW = "aftersales.order.view"


# ══════════════════════════════════════════════════════════════════════
#  1. كفالات تنتهي قريباً
# ══════════════════════════════════════════════════════════════════════

def _warranties_expiring(tenant_id: int, params: dict) -> list[dict]:
    from after_sales.models import WarrantyCard

    today = timezone.localdate()
    window = _int_param(params, "days")
    if window is None:
        window = 30
    horizon = today + datetime.timedelta(days=window)

    rows = []
    queryset = (
        WarrantyCard.objects
        .filter(tenant_id=tenant_id, end_date__gte=today, end_date__lte=horizon)
        .select_related("product", "partner")
        .order_by("end_date", "id")
    )
    for card in queryset:
        rows.append({
            "serial": card.serial or "",
            "device": str(card.product) if card.product_id else card.device_name,
            "customer": card.partner.name if card.partner_id else card.customer_name,
            "phone": card.customer_phone or "",
            "start_date": card.start_date,
            "end_date": card.end_date,
            # يُحسب مقابل اليوم نفسه الذي فُلتر به — لا يوم ثانٍ يخالفه.
            "days_remaining": card.days_remaining(today),
            "source": card.get_source_display(),
            "supplier_end": card.supplier_warranty_end_date,
        })
    return rows


register(ReportSpec(
    key="after-sales-warranties-expiring",
    title="كفالات تنتهي قريباً",
    category="after_sales",
    description=(
        "بطاقات الكفالة السارية التي تنتهي خلال المدة المحددة — مرتّبة بالأقرب "
        "انتهاءً. المنتهية فعلاً خارجها: هذه نافذة تصرّفٍ لا سجلّ متأخرات."
    ),
    columns=(
        ReportColumn("serial", "الرقم التسلسلي", KIND_TEXT),
        ReportColumn("device", "الجهاز / الصنف", KIND_TEXT),
        ReportColumn("customer", "الزبون", KIND_TEXT),
        ReportColumn("phone", "الهاتف", KIND_TEXT),
        ReportColumn("start_date", "بداية الكفالة", KIND_DATE),
        ReportColumn("end_date", "نهاية الكفالة", KIND_DATE),
        ReportColumn("days_remaining", "الأيام المتبقية", KIND_INT),
        ReportColumn("source", "المصدر", KIND_TEXT),
        ReportColumn("supplier_end", "نهاية كفالة المورد", KIND_DATE),
    ),
    filters=(
        ReportFilter("days", "خلال (يوماً)", "text", default="30"),
    ),
    build=_warranties_expiring,
    permission=PERM_WARRANTY_VIEW,
    module=MODULE,
))


# ══════════════════════════════════════════════════════════════════════
#  2. أوامر صيانة مفتوحة حسب الحالة والعمر
# ══════════════════════════════════════════════════════════════════════

def _open_service_orders(tenant_id: int, params: dict) -> list[dict]:
    from after_sales.models import ServiceOrder, ServiceOrderPart

    today = timezone.localdate()
    queryset = (
        ServiceOrder.objects
        .filter(tenant_id=tenant_id)
        .exclude(status__in=[ServiceOrder.STATUS_DELIVERED, ServiceOrder.STATUS_CANCELLED])
        .select_related("partner", "product", "technician")
        .prefetch_related("parts")
        .order_by("order_date", "id")
    )
    status_filter = (params.get("status") or "").strip()
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    queryset = _apply_dates(queryset, "order_date", params)

    rows = []
    for order in queryset:
        pending = sum(
            1 for part in order.parts.all()
            if part.billing == ServiceOrderPart.BILLING_COVERED and part.materialized_at is None
        )
        rows.append({
            "order_number": order.order_number,
            "order_date": order.order_date,
            # العمر هو ما يقيس التأخير — العدد وحده لا يفرّق بين يومٍ وشهرين.
            "age_days": (today - order.order_date).days,
            "customer": order.partner.name if order.partner_id else order.customer_name,
            "phone": order.customer_phone or "",
            "device": str(order.product) if order.product_id else order.device_description,
            "serial": order.serial or "",
            "status": order.get_status_display(),
            "technician": (
                order.technician.get_full_name() or order.technician.username
                if order.technician_id else ""
            ),
            "covered_pending": pending,
            "billing": (
                f"فاتورة #{order.sales_invoice_id}" if order.sales_invoice_id
                else (order.billing_waived_reason or "لم يُحسم")
            ),
            "id": order.pk,
        })
    return rows


register(ReportSpec(
    key="after-sales-open-orders",
    title="أوامر صيانة مفتوحة حسب الحالة والعمر",
    category="after_sales",
    description=(
        "كل جهاز ما زال عندنا — بعمره بالأيام منذ الاستلام، وحالته، وما ينقص "
        "لإغلاقه (قطع كفالة غير مرحّلة أو فوترة غير محسومة)."
    ),
    columns=(
        ReportColumn("order_number", "رقم الأمر", KIND_TEXT),
        ReportColumn("order_date", "تاريخ الاستلام", KIND_DATE),
        ReportColumn("age_days", "العمر (يوماً)", KIND_INT),
        ReportColumn("customer", "الزبون", KIND_TEXT),
        ReportColumn("phone", "الهاتف", KIND_TEXT),
        ReportColumn("device", "الجهاز", KIND_TEXT),
        ReportColumn("serial", "الرقم التسلسلي", KIND_TEXT),
        ReportColumn("status", "الحالة", KIND_TEXT),
        ReportColumn("technician", "الفني", KIND_TEXT),
        ReportColumn("covered_pending", "قطع كفالة غير مرحّلة", KIND_INT),
        ReportColumn("billing", "الفوترة", KIND_TEXT),
    ),
    filters=(
        *DATE_FILTERS,
        ReportFilter(
            "status", "الحالة", "select",
            options=tuple(
                (key, label)
                for key, label in [
                    ("received", "مُستلَم"),
                    ("in_diagnosis", "قيد التشخيص"),
                    ("awaiting_approval", "بانتظار الموافقة"),
                    ("in_repair", "قيد الإصلاح"),
                    ("ready", "جاهز للتسليم"),
                ]
            ),
        ),
    ),
    build=_open_service_orders,
    permission=PERM_ORDER_VIEW,
    module=MODULE,
    # لا `row_link`: شاشة أوامر الصيانة بلا رابط لكل أمر (المستند يُفتح
    # بحالةٍ لا بمسار)، ورابطٌ ثابت يقود كل الصفوف إلى القائمة نفسها يبدو
    # رابط مستند وليس به — غيابه أصدق من وعدٍ لا يفي.
))


# ══════════════════════════════════════════════════════════════════════
#  3. كلفة قطع الكفالة حسب الفترة
# ══════════════════════════════════════════════════════════════════════

def _warranty_parts_cost(tenant_id: int, params: dict) -> list[dict]:
    """من حركات `SERVICE_ISSUE` وحدها — لا من أسعار البيع ولا من بنود الأمر.

    الحركة تحمل التكلفة التاريخية (`total_cost = qty × avg_cost_before`) لحظة
    الصرف، فالرقم هنا هو ما دخل الدفاتر فعلاً لا ما نُقدّره اليوم. والنوع
    `SERVICE_ISSUE` هو نفسه الذي يُبقي هذا المصروف خارج تكلفة المبيع.
    """
    from after_sales.models import ServiceOrder
    from after_sales.service_orders import STOCK_REF_SERVICE_ISSUE
    from inventory.models import StockMovement

    queryset = (
        StockMovement.objects
        .filter(tenant_id=tenant_id, reference_type=STOCK_REF_SERVICE_ISSUE)
        .select_related("product", "partner")
        .order_by("movement_date", "id")
    )
    queryset = _apply_dates(queryset, "movement_date", params)
    product = _int_param(params, "product")
    if product:
        queryset = queryset.filter(product_id=product)

    movements = list(queryset)
    # أرقام الأوامر باستعلام واحد — لا استعلام داخل الحلقة (درس التقارير).
    order_numbers = dict(
        ServiceOrder.objects
        .filter(tenant_id=tenant_id, pk__in={m.reference_id for m in movements if m.reference_id})
        .values_list("pk", "order_number")
    )

    rows = []
    for movement in movements:
        rows.append({
            "movement_date": movement.movement_date,
            "order_number": order_numbers.get(movement.reference_id, ""),
            "product": str(movement.product) if movement.product_id else "",
            "customer": movement.partner.name if movement.partner_id else "",
            "quantity": _qty(movement.quantity),
            "unit_cost": _money(movement.unit_cost),
            "total_cost": _money(movement.total_cost),
            "id": movement.reference_id,
        })
    return rows


register(ReportSpec(
    key="after-sales-warranty-cost",
    title="كلفة قطع الكفالة حسب الفترة",
    category="after_sales",
    description=(
        "ما صُرف من المخزن على إصلاحات الكفالة — بالتكلفة التاريخية لحظة الصرف. "
        "مصروف تشغيلي لا تكلفة مبيع، فلا يظهر في ربح أي فاتورة."
    ),
    columns=(
        ReportColumn("movement_date", "التاريخ", KIND_DATE),
        ReportColumn("order_number", "أمر الصيانة", KIND_TEXT),
        ReportColumn("product", "الصنف", KIND_TEXT),
        ReportColumn("customer", "الزبون", KIND_TEXT),
        ReportColumn("quantity", "الكمية", KIND_NUMBER, total=True),
        ReportColumn("unit_cost", "تكلفة الوحدة", KIND_MONEY),
        ReportColumn("total_cost", "الكلفة", KIND_MONEY, total=True),
    ),
    filters=(
        *DATE_FILTERS,
        ReportFilter("product", "الصنف", "product"),
    ),
    build=_warranty_parts_cost,
    permission=PERM_ORDER_VIEW,
    module=MODULE,
    # لا `row_link`: شاشة أوامر الصيانة بلا رابط لكل أمر (المستند يُفتح
    # بحالةٍ لا بمسار)، ورابطٌ ثابت يقود كل الصفوف إلى القائمة نفسها يبدو
    # رابط مستند وليس به — غيابه أصدق من وعدٍ لا يفي.
))
