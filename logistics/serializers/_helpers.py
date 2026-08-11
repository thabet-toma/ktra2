import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from accounting.models import Account
from sales.models import SupplierPayment, SupplierPaymentAllocation
from sales.serializers import CHEQUE_DUE_DATE_REQUIRED
from core.payments import (
    apply_default_cash_account,
    document_partner_balance_summary,
    document_payment_summary,
)
from core.tenant_utils import get_tenant

from logistics.services import purchase_invoice_payment_summary
from logistics.text_utils import has_arabic as _has_arabic
from logistics.text_utils import (
    is_english_payment_or_legal_boilerplate as _english_payment_boilerplate,
)
















from logistics.models import (
    SupplierQuotation,
    SupplierQuotationLine,
    PurchaseOrder,
    PurchaseOrderLine,
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsShipment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsShipmentDeal,
    LogisticsPayment,
    LogisticsClearancePayment,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseInvoiceFee,
    PurchaseSettings,
    GoodsReceipt,
    GoodsReceiptLine,
    LocalShipment,
    LocalShipmentPayment,
)

from partners.serializers import PartnerSerializer
from inventory.models import Product

logger = logging.getLogger("logistics.serializers")

























# ─── Purchase Invoice Serializers ──────────────────────────────────────────────
















# ── P-H-3: SupplierPayment ──────────────────────────────────────────















def _deal_title_for_list_preview(deal):
    """اسم الصفقة المختصر إن وُجد (T4-03)، وإلا وصف قصير/أول سطر عربي/رقم العرض/رقم الصفقة."""
    # T4-03: explicit short_name is authoritative — it exists precisely so
    # the user can override the description heuristic with a clean name.
    short = (getattr(deal, "short_name", None) or "").strip()
    if short:
        return short[:72]
    d = (getattr(deal, "description", None) or "").strip()
    notes = (getattr(deal, "notes", None) or "").strip()
    if d and _has_arabic(d):
        return d[:72]
    if notes:
        for line in notes.splitlines():
            line = line.strip()
            if line and _has_arabic(line):
                return line[:72]
    ref = (getattr(deal, "ref_number", None) or "").strip()
    offer = (getattr(deal, "original_offer_number", None) or "").strip()
    # بيانات قديمة خزّنت الاسم العربي في «رقم العرض» — يتقدم على الوصف الإنجليزي
    if offer and _has_arabic(offer) and not re.match(r"^d-\d+$", offer, re.I):
        return offer[:72]
    if d and not _english_payment_boilerplate(d):
        return d[:72]
    if offer and offer.lower() != ref.lower():
        if not re.match(r"^d-\d+$", offer, re.I):
            return offer[:72]
    return ref[:72] if ref else ""

def _to_decimal(x, default="0"):
    if x is None:
        return Decimal(default)
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)

def _quantize_decimal_10_3(value) -> Decimal:
    """
    يطابق LogisticsShipment.total_volume / total_weight_kg (max_digits=10, decimal_places=3).
    يمنع رفض الطلب أو خطأ MySQL عند أرقام عشرية طويلة من الجمع أو JSON.
    """
    d = _to_decimal(value)
    d = d.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    vmax = Decimal("9999999.999")
    if d > vmax:
        d = vmax
    if d < 0:
        d = Decimal("0")
    return d

def _apply_lines_subtotal_and_grand_total(instance, lines_subtotal):
    """يطابق DealForm.recalculateTotals (ج8): إجمالي الصفقة الدولية =
    بضاعة − خصم + شحن داخل الصين. **بلا ضريبة** — الضريبة تُدفع بالتخليص ولا
    تدخل إجمالي الصفقة ولا سقف دفعات المورد (قرار المالك Q2).
    """
    instance.subtotal = _to_decimal(lines_subtotal)
    discount = _to_decimal(getattr(instance, "discount_amount", None))
    shipping = (
        Decimal("0")
        if getattr(instance, "is_shipping_included", False)
        else _to_decimal(getattr(instance, "shipping_cost_estimate", None))
    )
    after_discount = instance.subtotal - discount
    if after_discount < 0:
        after_discount = Decimal("0")
    instance.tax_amount = Decimal("0")
    instance.total_amount = (after_discount + shipping).quantize(Decimal("0.01"))

def _coerce_logistics_payment_pk(pay_id_raw):
    """يقبل معرف SQL فقط؛ يتجاهل tmp- و p-0 وغيرها."""
    if pay_id_raw is None or pay_id_raw == "":
        return None
    try:
        return int(pay_id_raw)
    except (TypeError, ValueError):
        return None

def _payments_total_exceeds_shipment(payments_data, shipment_cost) -> bool:
    if not payments_data:
        return False
    try:
        total = float(shipment_cost or 0)
        s = sum(float(p.get("amount") or 0) for p in payments_data)
    except (TypeError, ValueError):
        return True
    eps = max(0.01, abs(total) * 1e-9)
    return s > total + eps

def _sync_shipment_agent_payments(shipment, payments_data):
    """مزامنة دفعات وكيل الشحن (بدون صفقة شراء).

    الدفع الزائد عن تكلفة الشحن مسموح: الفائض دفعة مقدمة لدى الوكيل (يصبح مديناً
    لنا وتُسوّى على شحنة لاحقة). كان الحظر يمنع واقعة محاسبية صحيحة.
    """
    cap = float(shipment.total_shipping_cost_usd or 0)
    if cap > 0 and _payments_total_exceeds_shipment(payments_data, cap):
        paid = sum(float(p.get("amount") or 0) for p in payments_data)
        logger.info(
            'shipment %s agent payments exceed freight → advance: paid=%s cap=%s',
            shipment.pk, paid, cap,
        )
    keep_payments = []
    matched_pks = set()

    for payment_data in payments_data:
        pay_pk = _coerce_logistics_payment_pk(payment_data.get("id"))
        pay_instance = None
        if pay_pk is not None:
            pay_instance = LogisticsPayment.objects.filter(
                id=pay_pk, shipment=shipment
            ).first()

        if pay_instance is None:
            pn = payment_data.get("payment_number")
            try:
                pn_int = int(pn) if pn is not None else None
            except (TypeError, ValueError):
                pn_int = None
            if pn_int is not None:
                candidates = (
                    LogisticsPayment.objects.filter(
                        shipment=shipment, payment_number=pn_int
                    )
                    .exclude(pk__in=matched_pks)
                    .order_by("id")
                )
                pay_instance = candidates.first()

        if pay_instance:
            matched_pks.add(pay_instance.pk)
            for attr, value in payment_data.items():
                if attr in ("id", "deal", "shipment"):
                    continue
                if not pay_instance.is_posted or attr == "notes":
                    setattr(pay_instance, attr, value)
            pay_instance.shipment = shipment
            pay_instance.deal = None
            pay_instance.save()
            keep_payments.append(pay_instance.id)
        else:
            create_data = {
                k: v
                for k, v in payment_data.items()
                if k not in ("id", "deal", "shipment")
            }
            pn_c = create_data.get("payment_number")
            if pn_c is not None:
                if LogisticsPayment.objects.filter(
                    shipment=shipment, payment_number=pn_c
                ).exists():
                    raise serializers.ValidationError(
                        {
                            "payments": (
                                f"يوجد بالفعل دفعة شحن بنفس رقم القسط ({pn_c}). "
                                "حدّث الصفحة (F5) وتجنّب حفظاً مكرراً."
                            )
                        }
                    )
            new_pay = LogisticsPayment.objects.create(
                shipment=shipment, deal=None, **create_data
            )
            logger.info(
                'shipment agent payment created shipment=%s payment=%s amount=%s',
                shipment.pk, new_pay.pk, new_pay.amount,
            )
            keep_payments.append(new_pay.id)

    shipment.agent_payments.filter(is_posted=False).exclude(
        id__in=keep_payments
    ).delete()
