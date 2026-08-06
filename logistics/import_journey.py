"""مرشد رحلة الاستيراد — تجميع وقائع الرحلات النشطة لشركة واحدة.

**قرار معماري:** الخادم هنا لا يقرّر «الخطوة التالية» ولا يكتب نصّ الإرشاد.
منطق المراحل يعيش في مصدر واحد بالواجهة
(`frontend_v2/components/import-flow/importJourneyGuidance.ts`) لأن الشاشات
تستهلكه محلياً أيضاً (شاشة الشحنة تحسبه من بياناتها بلا نداء شبكة). لو تكرّر
القرار هنا لانحرف المرشد العام عن المرشد داخل الشاشة عند أول تعديل.

فوظيفة هذه الوحدة: حقائق خام بأقل عدد استعلامات — عروض بانتظار قرار، صفقات
ودفعاتها، وشحنات مع حالة الشحن والتخليص والنقل المحلي والفواتير.
"""
import logging
from decimal import Decimal

from django.db.models import Count, Q, Sum

from .landed_cost import payment_settled, sum_cost_lines_all_ils
from .models import (
    LocalShipment,
    LogisticsClearance,
    LogisticsDeal,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    SupplierQuotation,
)

logger = logging.getLogger(__name__)

Z = Decimal("0.00")

#: حالات عرض الاستيراد التي ما زالت تنتظر قرار المالك (لم تُقبل ولم تُرفض).
OFFER_AWAITING_STATUSES = (
    SupplierQuotation.STATUS_DRAFT,
    SupplierQuotation.STATUS_SENT,
    SupplierQuotation.STATUS_PENDING_INFO,
    SupplierQuotation.STATUS_UNDER_DISCUSSION,
)

#: الصفقة تغادر الرحلة النشطة بالإفراج (تحوّلت لفاتورة) أو بالإلغاء/الإغلاق.
DEAL_CLOSED_STATUSES = ("Cancelled", "Closed")
DEAL_RELEASED_STAGE = "sw_released"

DEFAULT_ROW_LIMIT = 12


def _money(value) -> Decimal:
    try:
        return (Decimal(str(value or 0))).quantize(Z)
    except Exception:  # pragma: no cover - قيمة تالفة في بيانات قديمة
        return Z


def _offer_counts(tenant) -> dict:
    rows = (
        SupplierQuotation.objects
        .filter(tenant=tenant, scope=SupplierQuotation.SCOPE_IMPORT)
        .values("status")
        .annotate(n=Count("id"))
    )
    by_status = {r["status"]: r["n"] for r in rows}
    return {
        "awaiting_decision": sum(by_status.get(s, 0) for s in OFFER_AWAITING_STATUSES),
        "accepted_not_converted": by_status.get(SupplierQuotation.STATUS_ACCEPTED, 0),
    }


def _deal_rows(tenant, limit: int) -> tuple[list, int]:
    qs = (
        LogisticsDeal.objects
        .filter(tenant=tenant)
        .exclude(status__in=DEAL_CLOSED_STATUSES)
        .exclude(shipping_workflow_status=DEAL_RELEASED_STAGE)
        .select_related("partner", "currency")
        .order_by("-id")
    )
    deals = list(qs[: limit * 4])
    if not deals:
        return [], 0
    deal_ids = [d.pk for d in deals]

    payments_by_deal: dict[int, list] = {}
    for payment in LogisticsPayment.objects.filter(deal_id__in=deal_ids):
        payments_by_deal.setdefault(payment.deal_id, []).append(payment)

    shipment_by_deal = {
        link.deal_id: (link.shipment_id, link.shipment.shipment_number, link.shipment.shipment_name)
        for link in (
            LogisticsShipmentDeal.objects
            .filter(deal_id__in=deal_ids)
            .select_related("shipment")
            .order_by("id")
        )
    }

    rows = []
    for deal in deals:
        payments = payments_by_deal.get(deal.pk, [])
        settled = [p for p in payments if payment_settled(p)]
        paid = sum((_money(p.amount) for p in settled), Z)
        total = _money(deal.total_amount)
        link = shipment_by_deal.get(deal.pk)
        rows.append({
            "id": deal.pk,
            "ref": deal.ref_number or f"#{deal.pk}",
            "title": (deal.short_name or deal.description or "").strip() or None,
            "partner_name": deal.partner.name if deal.partner_id else None,
            "currency_code": deal.currency.Code if deal.currency_id else None,
            "stage": deal.shipping_workflow_status or None,
            "total": str(total),
            "paid": str(paid),
            "remaining": str(max(Z, total - paid)),
            "payments_count": len(payments),
            "pending_payments_count": len(payments) - len(settled),
            "shipment_id": link[0] if link else None,
            "shipment_label": (link[2] or link[1]) if link else None,
        })
    without_shipment = sum(1 for r in rows if r["shipment_id"] is None)
    return rows[:limit], without_shipment


def _shipment_rows(tenant, limit: int) -> list:
    qs = (
        LogisticsShipment.objects
        .filter(tenant=tenant)
        .order_by("-id")
        .annotate(linked_deals=Count("logisticsshipmentdeal", distinct=True))
    )
    shipments = list(qs[: limit * 3])
    if not shipments:
        return []
    ids = [s.pk for s in shipments]

    freight_paid: dict[int, Decimal] = {}
    for payment in LogisticsPayment.objects.filter(shipment_id__in=ids, deal__isnull=True):
        if payment_settled(payment):
            freight_paid[payment.shipment_id] = (
                freight_paid.get(payment.shipment_id, Z) + _money(payment.amount)
            )

    clearances = {
        c.shipment_id: c
        for c in LogisticsClearance.objects
        .filter(shipment_id__in=ids)
        .prefetch_related("lines")
    }

    local_rows: dict[int, dict] = {}
    for local in LocalShipment.objects.filter(shipment_id__in=ids).annotate(
        paid=Sum("payments__amount", filter=Q(payments__is_posted=True)),
    ):
        bucket = local_rows.setdefault(local.shipment_id, {"count": 0, "remaining": Z})
        bucket["count"] += 1
        bucket["remaining"] += max(Z, _money(local.amount) - _money(local.paid))

    invoices: dict[int, dict] = {}
    for invoice in PurchaseInvoice.objects.filter(
        tenant=tenant, shipment_id__in=ids,
    ).values("shipment_id", "id", "deal_id"):
        bucket = invoices.setdefault(invoice["shipment_id"], {"count": 0, "deal_ids": set(), "first": None})
        bucket["count"] += 1
        if invoice["deal_id"]:
            bucket["deal_ids"].add(invoice["deal_id"])
        if bucket["first"] is None:
            bucket["first"] = invoice["id"]

    linked_deal_ids: dict[int, set] = {}
    for link in LogisticsShipmentDeal.objects.filter(shipment_id__in=ids).values("shipment_id", "deal_id"):
        linked_deal_ids.setdefault(link["shipment_id"], set()).add(link["deal_id"])

    rows = []
    for shipment in shipments:
        clearance = clearances.get(shipment.pk)
        local = local_rows.get(shipment.pk, {"count": 0, "remaining": Z})
        invoice = invoices.get(shipment.pk, {"count": 0, "deal_ids": set(), "first": None})
        deal_ids = linked_deal_ids.get(shipment.pk, set())
        remaining_deals = len(deal_ids - invoice["deal_ids"])
        rows.append({
            "id": shipment.pk,
            "number": shipment.shipment_number or f"#{shipment.pk}",
            "name": shipment.shipment_name or None,
            "shipment_type": shipment.shipment_type or "invoice",
            "deals_count": shipment.linked_deals,
            "freight_total_usd": str(_money(shipment.total_shipping_cost_usd)),
            "freight_paid_usd": str(freight_paid.get(shipment.pk, Z)),
            "freight_is_posted": bool(shipment.freight_is_posted),
            "clearance_id": clearance.pk if clearance else None,
            "clearance_cost": str(sum_cost_lines_all_ils(clearance)) if clearance else "0.00",
            "local_count": local["count"],
            "local_remaining": str(local["remaining"]),
            "invoices_count": invoice["count"],
            "invoice_id": invoice["first"],
            "remaining_deals": remaining_deals,
        })

    # الشحنة المكتملة (كل صفقاتها صارت فواتير) تغادر قائمة المرشد — إلا إن لم
    # يبقَ غيرها، فبقاء آخر شحنة يمنح المستخدم مدخلاً بدل لوحة فارغة.
    active = [r for r in rows if not (r["invoices_count"] and r["remaining_deals"] == 0)]
    return (active or rows[:1])[:limit]


def build_import_journey_summary(tenant, *, limit: int = DEFAULT_ROW_LIMIT) -> dict:
    """وقائع رحلات الاستيراد النشطة للشركة — بلا أي قرار مرحلة."""
    if tenant is None:
        return {
            "offers": {"awaiting_decision": 0, "accepted_not_converted": 0},
            "deals": {"rows": [], "without_shipment": 0},
            "shipments": [],
        }
    deal_rows, without_shipment = _deal_rows(tenant, limit)
    summary = {
        "offers": _offer_counts(tenant),
        "deals": {"rows": deal_rows, "without_shipment": without_shipment},
        "shipments": _shipment_rows(tenant, limit),
    }
    logger.info(
        "import_journey.summary tenant=%s offers=%s deals=%s shipments=%s",
        getattr(tenant, "TenantID", tenant),
        summary["offers"]["awaiting_decision"],
        len(deal_rows),
        len(summary["shipments"]),
    )
    return summary
