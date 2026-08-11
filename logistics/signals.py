import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.db import transaction, IntegrityError
from django.db.models import Sum
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import (
    LogisticsDeal,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
    LogisticsClearance,
    PurchaseInvoice,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# دالة موحّدة لحساب payment_status — تعتمد حصرياً على is_posted
#
# P-F-4: also re-syncs the legacy status / order_status cache columns from
# shipping_workflow_status, so a single call here keeps all three denormalized
# fields consistent with the canonical sources (workflow + posted payments).
# ---------------------------------------------------------------------------
def recalculate_deal_payment_status(deal_or_pk):
    """
    يعيد حساب payment_status للصفقة بناءً على الدفعات **المرحّلة محاسبياً فقط**
    (is_posted=True). هذا يضمن تناسق الحالة مع دفتر الأستاذ العام.

    P-F-4: يحدّث أيضاً status + order_status من shipping_workflow_status حتى
    تبقى الأعمدة الثلاثة (الكاش) متزامنة مع المصدر القانوني.

    يُستخدم في: post_payment, unpost_payment, remove_payment, signal.
    """
    pk = deal_or_pk if isinstance(deal_or_pk, int) else deal_or_pk.pk
    posted_total = (
        LogisticsPayment.objects.filter(deal_id=pk, is_posted=True)
        .aggregate(t=Sum("amount"))["t"]
    ) or 0

    try:
        deal = LogisticsDeal.objects.only(
            "total_amount", "remaining_amount", "payment_status", "status", "order_status",
            "shipping_workflow_status",
        ).get(pk=pk)
    except LogisticsDeal.DoesNotExist:
        return

    cap = deal.total_amount or 0
    if posted_total >= cap and cap > 0:
        new_ps = "Fully Paid"
    elif posted_total > 0:
        new_ps = "Partially Paid"
    else:
        new_ps = "Unpaid"

    sw = deal.shipping_workflow_status
    new_status = (
        'Cancelled'
        if deal.status == 'Cancelled'
        else LogisticsDeal._STATUS_FROM_WORKFLOW.get(sw, deal.status)
    )
    new_order = LogisticsDeal._ORDER_STATUS_FROM_WORKFLOW.get(sw, deal.order_status)

    updates = {}
    new_remaining = max(Decimal('0'), Decimal(str(cap)) - Decimal(str(posted_total)))
    if deal.remaining_amount != new_remaining:
        updates["remaining_amount"] = new_remaining
    if deal.payment_status != new_ps:
        updates["payment_status"] = new_ps
    if deal.status != new_status:
        updates["status"] = new_status
    if deal.order_status != new_order:
        updates["order_status"] = new_order
    if updates:
        LogisticsDeal.objects.filter(pk=pk).update(**updates)


@receiver(post_save, sender=LogisticsDeal)
def automate_deal_accounting(sender, instance, created, **kwargs):
    """
    لا ترحيل شراء تلقائي عند الصفقة.
    قيد المخزون (مدين مخزون | دائن مورد) يُنشأ عند استلام الفاتورة:
    POST /api/accounting/purchase-receipts/
    """
    return


@receiver(post_save, sender=LogisticsPayment)
def log_payment_save(sender, instance, created, **kwargs):
    """
    تسجيل فقط — لا ترحيل تلقائي.
    الترحيل حصرياً عبر POST .../post_payment/{id}/ (مسار واحد واضح).
    """
    if not getattr(instance, "deal_id", None):
        return
    verb = "إنشاء" if created else "تحديث"
    logger.info(
        "[دفعة %s] %s — deal=%s amount=%s status=%s is_posted=%s",
        instance.id,
        verb,
        instance.deal_id,
        instance.amount,
        instance.status,
        instance.is_posted,
    )

def _quantize_shipment_measure_10_3(val) -> Decimal:
    """مطابقة Decimal(10,3) على الشحنة — بدون float يفسد الدقة أو يتجاوز max_digits."""
    try:
        d = Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        d = Decimal("0")
    d = d.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    vmax = Decimal("9999999.999")
    if d > vmax:
        d = vmax
    if d < 0:
        d = Decimal("0")
    return d


def _resync_shipment_totals_from_deals(shipment_id):
    """مجموع الحجم/الوزن على الشحنة = مجموع صفقاتها (يتزامن مع تعديل الصفقة)."""
    try:
        sid = int(shipment_id)
    except (TypeError, ValueError):
        return
    sh = (
        LogisticsShipment.objects.filter(pk=sid)
        .prefetch_related("deals")
        .first()
    )
    if not sh:
        return
    try:
        deals = list(sh.deals.all())
        vol = sum((Decimal(str(d.total_cbm or 0)) for d in deals), Decimal("0"))
        wgt = sum(
            (
                Decimal(str(d.total_weight_kg or d.total_weight or 0))
                for d in deals
            ),
            Decimal("0"),
        )
        LogisticsShipment.objects.filter(pk=sid).update(
            total_volume=_quantize_shipment_measure_10_3(vol),
            total_weight_kg=_quantize_shipment_measure_10_3(wgt),
        )
    except Exception:
        logger.exception(
            "resync_shipment_totals_from_deals failed shipment_id=%s", shipment_id
        )


@receiver(post_save, sender=LogisticsDeal)
def resync_shipment_totals_on_deal_save(sender, instance, **kwargs):
    for sid in (
        LogisticsShipmentDeal.objects.filter(deal_id=instance.pk)
        .values_list("shipment_id", flat=True)
        .distinct()
    ):
        _resync_shipment_totals_from_deals(sid)


# ── M3: terminal stages the automated advances must not regress ──
_STAGE_TERMINAL = frozenset({
    LogisticsDeal.STAGE_INVOICED,
    LogisticsDeal.STAGE_CLOSED,
    LogisticsDeal.STAGE_CANCELLED,
})


def _advance_deals_through_service(deals, target):
    """M3: route automated stage advances through the ONE guarded service instead
    of bulk .update() (which bypassed the FSM guard — RC-7). Skips deals already at
    a terminal stage so a later clearance/invoice can't drag a released deal back."""
    from logistics.domain.stages import advance_deal_stage, derive_stage
    for deal in deals:
        if derive_stage(deal) in _STAGE_TERMINAL:
            continue
        advance_deal_stage(deal, target, force=True)


@receiver(post_save, sender=LogisticsShipmentDeal)
def sync_deal_workflow_on_shipment_link(sender, instance, created, **kwargs):
    """ربط الصفقة بشحنة → ضمن شحنة (in_shipment) عبر خدمة المراحل المحروسة."""
    _resync_shipment_totals_from_deals(instance.shipment_id)
    if not created:
        return
    _advance_deals_through_service([instance.deal], LogisticsDeal.STAGE_IN_SHIPMENT)


@receiver(post_save, sender=LogisticsClearance)
def sync_deal_workflow_on_clearance(sender, instance, created, **kwargs):
    """إنشاء تخليص لشحنة → تقديم صفقاتها إلى مرحلة التخليص + وسم الشحنة."""
    if not created:
        return
    try:
        shipment = instance.shipment
    except Exception:
        return
    deals = list(shipment.deals.all())
    if not deals:
        return
    _advance_deals_through_service(deals, LogisticsDeal.STAGE_AT_CLEARANCE)
    LogisticsShipment.objects.filter(pk=shipment.pk).update(
        shipment_route_status="israel_customs_clearance",
        status="Clearing",
    )


@receiver(post_delete, sender=LogisticsShipmentDeal)
def resync_shipment_totals_on_deal_unlink(sender, instance, **kwargs):
    _resync_shipment_totals_from_deals(instance.shipment_id)


@receiver(post_save, sender=PurchaseInvoice)
def release_deal_on_purchase_invoice(sender, instance, created, **kwargs):
    """حفظ فاتورة شراء مرتبطة بصفقة → الصفقة «مفرج عنها» (sw_released).

    يكمل وعد الواجهة في DealStageControl — كانت المرحلة النهائية لا تُضبط من
    أي مسار (task12 T12-A3). bulk .update() يتجاوز حارس FSM عمداً مثل بقية
    التقدّم البرمجي، ثم نزامن أعمدة الكاش (status/order_status).
    """
    if not created or not instance.deal_id:
        return
    deal = LogisticsDeal.objects.filter(pk=instance.deal_id).first()
    if not deal:
        return
    from logistics.domain.stages import advance_deal_stage, derive_stage
    if derive_stage(deal) in (LogisticsDeal.STAGE_CLOSED, LogisticsDeal.STAGE_CANCELLED):
        return
    # INVOICED is the release stage; advance_deal_stage also resyncs payment_status.
    advance_deal_stage(deal, LogisticsDeal.STAGE_INVOICED, force=True)


@receiver(post_save, sender=LogisticsShipment)
def auto_receive_stock_on_shipment_cleared(sender, instance, **kwargs):
    """
    عند تغيير حالة الشحنة إلى Cleared → إنشاء حركات استلام مخزون تلقائية
    لكل بنود الصفقات المرتبطة بالشحنة.
    """
    if instance.status != 'Cleared':
        return
    try:
        from inventory.services import receive_shipment_stock
        created = receive_shipment_stock(instance)
        if created:
            logger.info(
                "Auto-received %d stock movements for shipment %s",
                len(created), instance.shipment_number,
            )
    except Exception as e:
        logger.error("Error auto-receiving stock for shipment %s: %s", instance.pk, e)
