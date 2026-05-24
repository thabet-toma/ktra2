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
    LogisticsExpense,
    LogisticsShipment,
    LogisticsShipmentDeal,
    LogisticsClearance,
)
from accounting.models import JournalHeader, JournalLine

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
            "total_amount", "payment_status", "status", "order_status",
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
    new_status = LogisticsDeal._STATUS_FROM_WORKFLOW.get(sw, deal.status)
    new_order = LogisticsDeal._ORDER_STATUS_FROM_WORKFLOW.get(sw, deal.order_status)

    updates = {}
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

@receiver(post_save, sender=LogisticsExpense)
def automate_expense_accounting(sender, instance, created, **kwargs):
    """
    Automate accounting for LogisticsExpense.
    Debit: Expense Account | Credit: Liability Account
    يعمل فقط عند الإنشاء لأول مرة (created=True) لمنع قيود مكررة عند التعديل.
    """
    if not created:
        return
    if not instance.is_posted and instance.expense_account and instance.payable_account:
        try:
            from decimal import Decimal
            from tenants.models import Currency
            from accounting.services import get_exchange_rate, post_journal

            expense_currency = getattr(instance, 'currency', None)
            base_currency = Currency.objects.filter(IsBaseCurrency=True).first()
            is_foreign = (
                expense_currency and base_currency
                and expense_currency.pk != base_currency.pk
            )

            if is_foreign:
                rate = get_exchange_rate(
                    tenant_id=instance.tenant_id,
                    from_currency_id=expense_currency.pk,
                    to_currency_id=base_currency.pk,
                    effective_date=instance.invoice_date or datetime.date.today(),
                )
            else:
                rate = Decimal('1')

            txn_amount = Decimal(str(instance.amount or 0))
            td = instance.invoice_date or datetime.date.today()

            lines_data = [
                {"account": instance.expense_account_id, "debit": txn_amount, "credit": Decimal("0"), "description": f"مصروف لوجستي: {instance.description}"},
                {"account": instance.payable_account_id, "debit": Decimal("0"), "credit": txn_amount, "description": f"مصروف لوجستي: {instance.description}"},
            ]

            journal = post_journal(
                tenant_id=instance.tenant_id,
                transaction_date=td,
                reference_type='LOGISTICS_EXPENSE',
                reference_id=instance.id,
                description=f"مصروف لوجستي (Auto): {instance.description} ({instance.related_type} #{instance.related_id})",
                lines_data=lines_data,
                currency=expense_currency,
                exchange_rate=rate,
            )

            LogisticsExpense.objects.filter(id=instance.id).update(is_posted=True, journal=journal)
        except (ValidationError, DjangoValidationError, IntegrityError) as e:
            logger.error("Error automating LogisticsExpense %s: %s", instance.id, e)


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


@receiver(post_save, sender=LogisticsShipmentDeal)
def sync_deal_workflow_on_shipment_link(sender, instance, created, **kwargs):
    """ربط الصفقة بشحنة → بانتظار وصول الشحنة."""
    _resync_shipment_totals_from_deals(instance.shipment_id)
    if not created:
        return
    deal = instance.deal
    if deal.shipping_workflow_status == "sw_released":
        return
    LogisticsDeal.objects.filter(pk=deal.pk).exclude(
        shipping_workflow_status="sw_released"
    ).update(shipping_workflow_status="sw_wait_arrival")


@receiver(post_save, sender=LogisticsClearance)
def sync_deal_workflow_on_clearance(sender, instance, created, **kwargs):
    """عند إنشاء سجل تخليص جديد لشحنة → تقديم حالة الصفقات والشحنة إلى مرحلة التخليص."""
    if not created:
        return
    try:
        shipment = instance.shipment
    except Exception:
        return
    deal_ids = list(shipment.deals.values_list("pk", flat=True))
    if not deal_ids:
        return
    LogisticsDeal.objects.filter(pk__in=deal_ids).exclude(
        shipping_workflow_status="sw_released"
    ).update(shipping_workflow_status="sw_wait_clearance")
    LogisticsShipment.objects.filter(pk=shipment.pk).update(
        shipment_route_status="israel_customs_clearance",
        status="Clearing",
    )


@receiver(post_delete, sender=LogisticsShipmentDeal)
def resync_shipment_totals_on_deal_unlink(sender, instance, **kwargs):
    _resync_shipment_totals_from_deals(instance.shipment_id)


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
