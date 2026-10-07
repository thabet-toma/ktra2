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
from django.db.models import Q
from django.utils import timezone

from django.conf import settings

from .cashbox import get_cash_box_capital_account
from .models import Account, CashBoxFxConsumption, CashBoxFxLot, CashBoxLedgerAccount
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


def account_base_balance(account_id) -> Decimal:
    """رصيد الحساب بالعملة الأساسية من القيود المرحّلة (مدين − دائن)."""
    from django.db.models import Sum

    from .models import JournalLine

    agg = JournalLine.objects.filter(account_id=account_id, journal__is_posted=True).aggregate(
        d=Sum("base_debit"), c=Sum("base_credit"))
    return (_d(agg["d"]) - _d(agg["c"])).quantize(Q2)


def open_box_with_counted_lot(box, fc_amount, rate, *, date, offset_account, user=None):
    """صندوق عملة أجنبية بلا طبقات ⇒ طبقة افتتاحية بالجرد الفعلي، ورصيد حسابه = fc × rate.

    قيدان ذرّياً، مقابلهما الحساب الذي يختاره المالك: (1) تسوية `FX_BOX_OPENING_ADJUST`
    تُصفّر رصيد الصندوق الدفتري المتراكم (دفعاتٌ خرجت منه ولم يُسجَّل تمويلها)؛
    (2) طبقة `opening` بقيد `FX_BOX_OPENING`: مدين الصندوق fc × rate. فيصير
    `box_ils_value` = رصيد الحساب، وFIFO يبدأ من دولارات موجودة فعلاً.
    يرفض: صندوقٌ له طبقات، أو حركةٌ صافية عليه بعد التاريخ، أو المقابل هو الصندوق نفسه.
    يُرجع (الطبقة، قيد التسوية أو None).
    """
    from .models import JournalLine

    fc = _d(fc_amount).quantize(Q4)
    r = _d(rate)
    if fc <= 0 or r <= 0:
        raise ValidationError("المبلغ وسعر الصرف يجب أن يكونا موجبين.")
    if offset_account.pk == box.account_id or offset_account.tenant_id != box.tenant_id:
        raise ValidationError("حساب المقابل يجب أن يكون حساباً آخر من نفس الشركة.")
    with transaction.atomic():
        CashBoxLedgerAccount.objects.select_for_update().get(pk=box.pk)
        if box.fx_lots.exists():
            raise ValidationError(f"{box.name} له طبقات FIFO أصلاً — الطبقة الافتتاحية لصندوقٍ بلا طبقات.")
        # الصافي لا الوجود: قيدٌ وعكسه بعد التاريخ (تصحيح تاريخ دفعة) لا يغيّران رصيده يومها.
        from django.db.models import Sum
        later = JournalLine.objects.filter(
            account_id=box.account_id, journal__is_posted=True,
            journal__transaction_date__gt=date,
        ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
        if _d(later["d"]) != _d(later["c"]):
            raise ValidationError(f"على {box.name} حركة صافية بعد {date} — اختر تاريخاً لا يسبق آخر حركة.")
        balance = account_base_balance(box.account_id)
        adjust = None
        if balance:
            desc = f"تسوية رصيد {box.name} الدفتري ({balance}) قبل الطبقة الافتتاحية"
            amount = abs(balance)
            box_side = {"debit": amount, "credit": Decimal("0")} if balance < 0 else \
                {"debit": Decimal("0"), "credit": amount}
            adjust = post_journal(
                tenant_id=box.tenant_id, transaction_date=date,
                reference_type="FX_BOX_OPENING_ADJUST", reference_id=box.pk,
                description=desc, user=user, idempotent=False,
                lines_data=[
                    {"account": box.account_id, **box_side, "description": desc},
                    {"account": offset_account.pk, "debit": box_side["credit"],
                     "credit": box_side["debit"], "description": desc},
                ],
            )
        ils = (fc * r).quantize(Q2)
        desc = f"طبقة افتتاحية {fc} {box.currency_code} في {box.name} بسعر {r} (جرد فعلي)"
        lot = _new_lot(
            box, fc=fc, rate=r, source=CashBoxFxLot.SOURCE_OPENING, date=date,
            ref_type="FX_BOX_OPENING", description=desc, user=user,
            lines_data=[
                {"account": box.account_id, "debit": ils, "credit": Decimal("0"), "description": desc},
                {"account": offset_account.pk, "debit": Decimal("0"), "credit": ils, "description": desc},
            ],
        )
        logger.info("fx-fifo opening: box=%s lot=%s fc=%s rate=%s adjust=%s",
                    box.id, lot.id, fc, r, getattr(adjust, "id", None))
        return lot, adjust


def fifo_link_for_box(box_account, tenant):
    """يُرجع ربط صندوق العملة الأجنبية إن كان لحساب الصندوق طبقات FIFO متبقية، وإلا None."""
    link = CashBoxLedgerAccount.objects.filter(tenant=tenant, account=box_account).first()
    if link and link.fx_lots.filter(remaining_fc__gt=0).exists():
        return link
    return None


def build_fx_payment_lines(*, fifo_link, foreign_amount, local_amount, debit_account_id,
                           box_account_id, partner_id, description, tenant,
                           reference_type, reference_id):
    """يستهلك FIFO ويبني أسطر قيد دفع بالشيقل + فرق صرف محقّق.

    مدين حساب الذمة (مورد/وكيل/مخلّص) بقيمة الذمة (local_amount بالشيقل)، دائن
    الصندوق بتكلفة FIFO، والفرق ربح (دائن) أو خسارة (مدين). يفترض fifo_link صالحاً.
    `reference_type`/`reference_id` = مرجع القيد الذي سيُرحَّل (سجل الاستهلاك).
    """
    fifo_cost, _bd = consume_fifo(fifo_link, foreign_amount,
                                  reference_type=reference_type, reference_id=reference_id)
    local_amount = _d(local_amount).quantize(Q2)
    diff = (local_amount - fifo_cost).quantize(Q2)
    lines = [
        {"account": debit_account_id, "debit": local_amount, "credit": Decimal("0"),
         "partner": partner_id, "description": description},
        {"account": box_account_id, "debit": Decimal("0"), "credit": fifo_cost,
         "description": description},
    ]
    if diff > 0:
        lines.append({"account": get_realized_fx_account(tenant).id, "debit": Decimal("0"),
                      "credit": diff, "description": f"ربح فرق صرف محقّق | {description}"})
    elif diff < 0:
        lines.append({"account": get_realized_fx_account(tenant).id, "debit": -diff,
                      "credit": Decimal("0"), "description": f"خسارة فرق صرف محقّقة | {description}"})
    return lines


def consume_fifo(box, fc_amount, *, reference_type, reference_id):
    """يستهلك العملة الأجنبية FIFO ويُرجع (التكلفة بالشيقل، تفصيل الطبقات).

    يُنقص remaining_fc للطبقات الأقدم أولاً، ويكتب لكل طبقة صفّ `CashBoxFxConsumption`
    بمرجع المستند — منه يُرجِع `restore_fifo` عند فكّ الترحيل. يرفع ValidationError
    عند نقص الرصيد.
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
            CashBoxFxConsumption.objects.create(
                tenant_id=box.tenant_id, lot=lot, fc=take, rate=lot.rate,
                reference_type=reference_type, reference_id=reference_id,
            )
            breakdown.append({"lot_id": lot.id, "fc": take, "rate": lot.rate, "ils": ils})
            remaining -= take
        logger.info("fx-fifo consume: box=%s fc=%s ils_cost=%s lots=%s ref=%s/%s",
                    box.id, fc, ils_cost, len(breakdown), reference_type, reference_id)
        return ils_cost.quantize(Q2), breakdown


def restore_fifo(*, tenant_id, reference_type, reference_id) -> Decimal:
    """يردّ استهلاكات مستندٍ الحيّة إلى طبقاتها نفسها ويختمها `restored_at` — لا يحذفها.

    بعكس ترتيب الاستهلاك؛ الطبقة لا تُنشأ من جديد فموقعها في رتل FIFO محفوظ، وإعادة
    الترحيل تستهلك من نفس الطبقات بنفس الترتيب. يُرجع مجموع العملة المُعادة.
    """
    with transaction.atomic():
        rows = list(
            CashBoxFxConsumption.objects.select_for_update().filter(
                tenant_id=tenant_id, reference_type=reference_type, reference_id=reference_id,
                restored_at__isnull=True,
            ).order_by("-id")
        )
        if not rows:
            return Decimal("0")
        lots = {lot.pk: lot for lot in
                CashBoxFxLot.objects.select_for_update().filter(pk__in={r.lot_id for r in rows})}
        total = Decimal("0")
        for r in rows:
            lot = lots[r.lot_id]
            lot.remaining_fc = (lot.remaining_fc + r.fc).quantize(Q4)
            total += r.fc
        for lot in lots.values():
            lot.save(update_fields=["remaining_fc"])
        CashBoxFxConsumption.objects.filter(pk__in=[r.pk for r in rows]).update(
            restored_at=timezone.now())
        logger.info("fx-fifo restore: ref=%s/%s fc=%s rows=%s",
                    reference_type, reference_id, total, len(rows))
        return total.quantize(Q4)


UNTRACKED_CONSUMPTION_MESSAGE = (
    "هذه الدفعة رُحّلت من صندوق عملة أجنبية له طبقات FIFO قبل تسجيل استهلاك الطبقات، "
    "فلا يُعرف من أيّ طبقةٍ أُخذت. فكّ ترحيلها يعكس القيد دون إرجاع الدولارات للطبقات، "
    "فينقص رصيد الصندوق بالعملة الأجنبية عند إعادة ترحيلها. صحّحها بقيد يومية بعد مراجعة المحاسب."
)


def _may_have_untracked_consumption(journal) -> bool:
    """قيدٌ قد استهلك طبقاتٍ قبل وجود السجل: بالعملة الأساسية (مسار FIFO يكتب بالشيقل —
    الدفع بلا طبقات يكتب بعملة الدفعة) ودائنٌ صندوقاً كانت له طبقات قبله. القيود تُرقَّم
    تصاعدياً، فطبقةٌ قيد تمويلها أقدم من القيد كانت موجودة لحظة ترحيله."""
    if journal is None:
        return False
    currency = journal.currency
    if currency is not None and not currency.IsBaseCurrency:
        return False
    box_account_ids = journal.lines.filter(credit__gt=0).values("account_id")
    return CashBoxFxLot.objects.filter(
        cash_box__tenant_id=journal.tenant_id, cash_box__account_id__in=box_account_ids,
    ).filter(Q(journal_id__lt=journal.id) | Q(journal__isnull=True)).exists()


def release_fifo_for_unpost(journal, *, tenant_id, reference_type, reference_id) -> Decimal:
    """حارس فكّ ترحيل دفعةٍ من صندوق FIFO — يُستدعى داخل معاملة العكس/الحذف نفسها.

    له استهلاكٌ مسجَّل ⇒ يُرجَع إلى طبقاته. لا سجلّ والقيد ربما استهلك طبقات (ترحيلٌ
    قبل السجل) ⇒ ValidationError بدل فكٍّ يُنقص رصيد الصندوق بصمت. غير ذلك ⇒ 0.
    """
    restored = restore_fifo(tenant_id=tenant_id, reference_type=reference_type,
                            reference_id=reference_id)
    if restored:
        return restored
    if _may_have_untracked_consumption(journal):
        logger.warning("fx-fifo unpost refused: untracked consumption ref=%s/%s journal=%s",
                       reference_type, reference_id, journal.id)
        raise ValidationError(UNTRACKED_CONSUMPTION_MESSAGE)
    return Decimal("0")
