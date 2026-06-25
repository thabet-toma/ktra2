"""محرّك FIFO لصناديق العملة الأجنبية (مثل صندوق الدولار).

التمويل (إيداع من رأس المال أو تحويل من صندوق الشيقل) ينشئ طبقة بسعر صرفها.
الدفع بالعملة الأجنبية يستهلك الطبقات الأقدم أولاً، والتكلفة بالشيقل بسعر كل طبقة.
رصيد حساب الصندوق في الشجرة محفوظ بالشيقل (القيمة الدفترية = Σ remaining_fc × rate).

فرق الصرف المحقّق يُحتسب عند ربط الاستهلاك بمستند مُسجّل بسعر مختلف (مرحلة لاحقة:
دفعات الصفقات) — هذا المحرّك يوفّر تكلفة الـFIFO بالشيقل التي يُبنى عليها الفرق.
"""
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from django.conf import settings

from .cashbox import get_cash_box_capital_account
from .models import Account, CashBoxFxLot, CashBoxLedgerAccount
from .services import post_journal

logger = logging.getLogger(__name__)

Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")


def _d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def get_realized_fx_account(tenant):
    """حساب أرباح/خسائر فروق العملة المحقّقة — يُحدَّد بـ REALIZED_FX_ACCOUNT_CODE
    (افتراضي 4201) أو يُنشأ تحت جذر الإيرادات. طبيعته «مدين/دائن» (ربح=دائن، خسارة=مدين)."""
    code = str(getattr(settings, "REALIZED_FX_ACCOUNT_CODE", None) or "4201").strip()
    acc = Account.objects.filter(tenant=tenant, code=code).first()
    if acc:
        return acc
    parent = (
        Account.objects.filter(tenant=tenant, account_type="Revenue", code="42").first()
        or Account.objects.filter(tenant=tenant, account_type="Revenue").order_by("code").first()
    )
    return Account.objects.create(
        tenant=tenant, code=code, name="فروق صرف محقّقة (Realized FX Gain/Loss)",
        parent=parent, account_type="Revenue", is_active=True,
    )


def box_fc_balance(box) -> Decimal:
    """الرصيد المتبقي بالعملة الأجنبية."""
    return sum((lot.remaining_fc for lot in box.fx_lots.all()), Decimal("0")).quantize(Q4)


def box_ils_value(box) -> Decimal:
    """القيمة الدفترية بالشيقل (Σ remaining_fc × rate) — تساوي رصيد حساب الصندوق."""
    return sum((lot.remaining_fc * lot.rate for lot in box.fx_lots.all()), Decimal("0")).quantize(Q2)


def _new_lot(box, *, fc, rate, source, date, ref_type, lines_data, description, user):
    """ينشئ طبقة + قيد تمويلها ذرّياً ويربطهما."""
    with transaction.atomic():
        lot = CashBoxFxLot.objects.create(
            tenant=box.tenant, cash_box=box, lot_date=date,
            original_fc=fc, remaining_fc=fc, rate=rate, source=source,
        )
        jh = post_journal(
            tenant_id=box.tenant_id, transaction_date=date,
            reference_type=ref_type, reference_id=lot.id,
            description=description, lines_data=lines_data, user=user,
        )
        lot.journal = jh
        lot.save(update_fields=["journal"])
        logger.info("fx-fifo fund: box=%s lot=%s fc=%s rate=%s source=%s", box.id, lot.id, fc, rate, source)
        return lot


def fund_box_from_capital(box, fc_amount, rate, *, date, user=None) -> CashBoxFxLot:
    """إيداع عملة أجنبية من رأس المال: مدين الصندوق (شيقل) / دائن رأس المال."""
    fc = _d(fc_amount).quantize(Q4)
    r = _d(rate)
    if fc <= 0 or r <= 0:
        raise ValidationError("المبلغ وسعر الصرف يجب أن يكونا موجبين.")
    ils = (fc * r).quantize(Q2)
    capital = get_cash_box_capital_account(box.tenant)
    if not capital:
        raise ValidationError("لا يوجد حساب رأس مال (Equity) للإيداع منه.")
    desc = f"إيداع {fc} {box.currency_code} في {box.name} بسعر {r}"
    return _new_lot(
        box, fc=fc, rate=r, source=CashBoxFxLot.SOURCE_CAPITAL, date=date,
        ref_type="FX_FUND_CAPITAL", description=desc, user=user,
        lines_data=[
            {"account": box.account_id, "debit": ils, "credit": Decimal("0"), "description": desc},
            {"account": capital.id, "debit": Decimal("0"), "credit": ils, "description": desc},
        ],
    )


def transfer_ils_to_fx(box, ils_box, fc_amount, rate, *, date, user=None) -> CashBoxFxLot:
    """تحويل من صندوق الشيقل لصندوق العملة الأجنبية بسعر صرف: مدين الصندوق الأجنبي / دائن صندوق الشيقل."""
    fc = _d(fc_amount).quantize(Q4)
    r = _d(rate)
    if fc <= 0 or r <= 0:
        raise ValidationError("المبلغ وسعر الصرف يجب أن يكونا موجبين.")
    if ils_box is None or not getattr(ils_box, "account_id", None):
        raise ValidationError("صندوق الشيقل المصدر غير صالح.")
    ils = (fc * r).quantize(Q2)
    desc = f"تحويل {fc} {box.currency_code} من {ils_box.name} بسعر {r}"
    return _new_lot(
        box, fc=fc, rate=r, source=CashBoxFxLot.SOURCE_TRANSFER, date=date,
        ref_type="FX_FUND_TRANSFER", description=desc, user=user,
        lines_data=[
            {"account": box.account_id, "debit": ils, "credit": Decimal("0"), "description": desc},
            {"account": ils_box.account_id, "debit": Decimal("0"), "credit": ils, "description": desc},
        ],
    )


def fifo_link_for_box(box_account, tenant):
    """يُرجع ربط صندوق العملة الأجنبية إن كان لحساب الصندوق طبقات FIFO متبقية، وإلا None."""
    link = CashBoxLedgerAccount.objects.filter(tenant=tenant, account=box_account).first()
    if link and link.fx_lots.filter(remaining_fc__gt=0).exists():
        return link
    return None


def build_fx_payment_lines(*, fifo_link, foreign_amount, local_amount, debit_account_id,
                           box_account_id, partner_id, description, tenant):
    """يستهلك FIFO ويبني أسطر قيد دفع بالشيقل + فرق صرف محقّق.

    مدين حساب الذمة (مورد/وكيل/مخلّص) بقيمة الذمة (local_amount بالشيقل)، دائن
    الصندوق بتكلفة FIFO، والفرق ربح (دائن) أو خسارة (مدين). يفترض fifo_link صالحاً.
    """
    fifo_cost, _bd = consume_fifo(fifo_link, foreign_amount)
    local_amount = _d(local_amount).quantize(Q2)
    diff = (local_amount - fifo_cost).quantize(Q2)
    lines = [
        {"account": debit_account_id, "debit": local_amount, "credit": Decimal("0"),
         "partner": partner_id, "description": description},
        {"account": box_account_id, "debit": Decimal("0"), "credit": fifo_cost,
         "partner": partner_id, "description": description},
    ]
    if diff > 0:
        lines.append({"account": get_realized_fx_account(tenant).id, "debit": Decimal("0"),
                      "credit": diff, "description": f"ربح فرق صرف محقّق | {description}"})
    elif diff < 0:
        lines.append({"account": get_realized_fx_account(tenant).id, "debit": -diff,
                      "credit": Decimal("0"), "description": f"خسارة فرق صرف محقّقة | {description}"})
    return lines


def consume_fifo(box, fc_amount):
    """يستهلك العملة الأجنبية FIFO ويُرجع (التكلفة بالشيقل، تفصيل الطبقات).

    يُنقص remaining_fc للطبقات الأقدم أولاً. يرفع ValidationError عند نقص الرصيد.
    تُستخدم لاحقاً في دفعات الصفقات لاحتساب التكلفة وفرق الصرف.
    """
    fc = _d(fc_amount).quantize(Q4)
    if fc <= 0:
        raise ValidationError("مبلغ الدفع يجب أن يكون موجباً.")
    with transaction.atomic():
        lots = list(
            box.fx_lots.select_for_update()
            .filter(remaining_fc__gt=0)
            .order_by("lot_date", "id")
        )
        available = sum((lot.remaining_fc for lot in lots), Decimal("0"))
        if available < fc:
            raise ValidationError(
                f"رصيد {box.name} غير كافٍ بالعملة الأجنبية: متاح {available}، مطلوب {fc}."
            )
        remaining = fc
        ils_cost = Decimal("0")
        breakdown = []
        for lot in lots:
            if remaining <= 0:
                break
            take = min(lot.remaining_fc, remaining)
            ils = (take * lot.rate).quantize(Q2)
            ils_cost += ils
            lot.remaining_fc = (lot.remaining_fc - take).quantize(Q4)
            lot.save(update_fields=["remaining_fc"])
            breakdown.append({"lot_id": lot.id, "fc": take, "rate": lot.rate, "ils": ils})
            remaining -= take
        logger.info("fx-fifo consume: box=%s fc=%s ils_cost=%s lots=%s", box.id, fc, ils_cost, len(breakdown))
        return ils_cost.quantize(Q2), breakdown
