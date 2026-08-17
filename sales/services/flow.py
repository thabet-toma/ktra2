"""
ترحيل فواتير المبيعات، حركة المخزون، وتحصيل العملاء.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum

from accounting.models import Account, JournalLine
from accounting.services import (
    convert_amount,
    create_audit_log,
    post_journal,
    resolve_forex_account,
    unpost_document,
    validate_fiscal_period,
    validate_journal_entry,
)
from inventory.models import Product, StockMovement
from inventory.serials import (
    consume_sales_serials,
    release_sales_serials,
    restore_returned_sales_serials,
)
from inventory.services import record_stock_movement
from partners.models import Partner, PartnerGroup
from accounting.api import ensure_partner_account
from tenants.models import Tenant

from sales.models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    DeliveryOrderLine,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)
from django.utils import timezone

logger = logging.getLogger("sales.services")

DEC = Decimal("0.01")



# المرحلة 3: مراجع عبر وحدات الحزمة (نفس الملف سابقاً) — الرسم البياني لا-دوري.
from .foundation import get_or_create_sales_settings
from .numbering import guard_reserved_stock
from .calc import _build_cogs_journal_line_dicts, _build_tax_buckets, _lock_products_for_lines, _partner_open_balance_excluding_invoice, _resolve_ar_account, _revenue_credit_journal_rows, guard_loss_invoice, recalculate_invoice_amounts, resolve_cheques_under_collection_account

def _validate_cheque_payloads(
    cheques: list[dict], *, require_due_date: bool = False
) -> Decimal:
    """يتحقّق من صفوف الشيكات الواردة ويُعيد مجموعها — مصدر فحص واحد.

    `require_due_date` مرفوعة في مسار التحصيل الجديد فقط، مطابقةً لشاشة السندات
    (`_PaymentChequeInputSerializer`): دورة الشيك كلها مبنية على موعده. مسار
    الإرفاق القديم يبقى متساهلاً كما كان فلا ينكسر مُدخِل قديم.
    """
    total = Decimal("0")
    for i, c in enumerate(cheques):
        if not str(c.get("cheque_number", "")).strip():
            raise ValidationError(f"الشيك #{i+1}: رقم الشيك مطلوب.")
        try:
            amt = Decimal(str(c.get("amount", 0)))
        except Exception:
            raise ValidationError(f"الشيك #{i+1}: مبلغ غير صالح.")
        if amt <= 0:
            raise ValidationError(f"الشيك #{i+1}: المبلغ يجب أن يكون أكبر من صفر.")
        if require_due_date and not c.get("due_date"):
            from sales.serializers import CHEQUE_DUE_DATE_REQUIRED

            raise ValidationError(f"الشيك #{i+1}: {CHEQUE_DUE_DATE_REQUIRED}")
        total += amt
    return total.quantize(DEC)


def attach_payment_voucher(
    invoice: SalesInvoice,
    *,
    cash_amount: Decimal | str | float = 0,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    user=None,
) -> SalesInvoice:
    """يربط شيكات الفاتورة قبل الترحيل (تحضيرٌ لا ترحيل).

    - Replace-semantics: each call replaces previously-attached cheques on the
      invoice (no duplicates). Use empty `cheques=[]` to clear.
    - Nothing is posted here. T1: at post time the cheques are swept into a
      real posted `CustomerPayment` (`_settle_attached_cheques`) — they are NOT
      settled inside the invoice's own journal any more.
    - T2: `cash_amount > 0` **مرفوض هنا**. كان يُكتب في `attached_cash_amount`
      ولا يُرحَّل شيئاً إطلاقاً — مالٌ يدخل الصندوق ولا أثر له في الدفاتر. لا
      وعاء للنقد على مسودة، فالنقد يمرّ من `collect_invoice_payment` الذي يُنشئ
      سند قبض حقيقياً. العمودان يبقيان (قراءة قديمة) ويُصفَّران هنا فلا يبقى
      رقمٌ قديم يخدع فحصَ «المرفق لا يتجاوز الإجمالي» عند الترحيل.
    - Idempotency: posting goes through `post_journal()` which deduplicates by
      (reference_type, reference_id). Calling this function multiple times
      pre-post just updates the attachment state.

    cheques: list of dicts with keys:
        cheque_number (str, required)
        amount        (Decimal/str, required)
        bank_name     (str, optional)
        due_date      (date or ISO str, optional)
        issue_date    (date or ISO str, optional)
        payee_name    (str, optional)
        notes         (str, optional)
    """
    from accounting.models import Cheque

    if invoice.status == SalesInvoice.STATUS_POSTED:
        raise ValidationError("لا يمكن تعديل السند بعد ترحيل الفاتورة.")

    cash_amount = Decimal(str(cash_amount or 0)).quantize(DEC)
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")
    if cash_amount > 0:
        raise ValidationError(
            "المبلغ النقدي لا يُحفَظ على المسودة — كان يُسجَّل ولا يُرحَّل. "
            "حصّل الفاتورة بـ«التحصيل» (`invoices/{id}/collect/`) أو أرسل "
            "`post: true` مع السند، فيُنشأ سند قبض حقيقي."
        )

    cheques = cheques or []
    cheques_total = _validate_cheque_payloads(cheques)

    # Compute current invoice total to validate against (without saving)
    if invoice.pk:
        recalculate_invoice_amounts(invoice)
    grand = Decimal(str(invoice.grand_total or 0)).quantize(DEC)
    if cheques_total > grand:
        raise ValidationError(
            f"مجموع شيكات السند ({cheques_total}) يتجاوز مبلغ الفاتورة {grand}."
        )

    with transaction.atomic():
        # 1) T2: لا نقد على المسودة — والعمودان القديمان يُصفَّران مع كل إرفاق.
        invoice.attached_cash_amount = Decimal("0.00")
        invoice.attached_cash_account_id = None
        invoice.save(update_fields=[
            "attached_cash_amount", "attached_cash_account",
        ])

        # 2) Cheques side — REPLACE previously-linked DRAFT cheques only
        # (don't touch cheques already in Under_Collection or beyond).
        Cheque.objects.filter(
            sales_invoice=invoice, status="Draft"
        ).delete()
        for c in cheques:
            Cheque.objects.create(
                tenant_id=invoice.tenant_id,
                sales_invoice=invoice,
                partner=invoice.customer,
                direction="Incoming",
                status="Draft",  # promoted to Under_Collection on invoice post
                cheque_number=str(c.get("cheque_number")).strip(),
                bank_name=(c.get("bank_name") or "")[:100],
                amount=Decimal(str(c.get("amount"))).quantize(DEC),
                currency_id=invoice.currency_id,
                due_date=c.get("due_date") or None,
                issue_date=c.get("issue_date") or None,
                payee_name=(c.get("payee_name") or "")[:150],
                notes=c.get("notes") or "",
                created_by=user if user and not getattr(user, "is_anonymous", False) else None,
            )

    return invoice


def attach_voucher_and_post(
    invoice: SalesInvoice,
    *,
    cash_amount: Decimal | str | float = 0,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    user=None,
) -> SalesInvoice:
    """P-H-5: atomic attach + post — واجهةٌ محفوظة الشكل فوق منسّق التحصيل (T2).

    الشيكات تُربط بالفاتورة أولاً (بدلالة الاستبدال كما كانت)، ثم يتولّى
    `collect_invoice_payment` الترحيلَ والتحصيل داخل نفس المعاملة: يكنس تلك
    الشيكات ويضمّ إليها النقد في **سند قبض واحد** بدل أن يُسجَّل النقد في عمود
    لا يُرحَّل. فإن سقط أيّ جزء ارتدّ الكلّ — نفس ضمان P-H-5 الأصلي.

    بلا نقد: `has_spec` تبقى كاذبة فيمرّ الترحيل بمساره القائم
    (`_settle_attached_cheques`) حرفياً — صفر تغيير على هذه الحالة.
    """
    with transaction.atomic():
        attach_payment_voucher(
            invoice,
            cash_amount=0,
            cash_account_id=None,
            cheques=cheques,
            user=user,
        )
        collect_invoice_payment(
            invoice,
            cash=cash_amount or None,
            cash_account_id=cash_account_id,
            post_invoice=True,
            user=user,
        )
    return invoice


def _auto_settlement_note(invoice: SalesInvoice) -> str:
    """توقيع سند التسوية النقدية التلقائي — يُطابَق عليه في البيانات القديمة."""
    return f"تحصيل نقدي تلقائي — فاتورة {invoice.invoice_number}"


def posted_allocations_total(invoice_id: int) -> Decimal:
    """T-ARINT: مجموع توزيعات السندات **المرحّلة** على فاتورة (بعملة الفاتورة).

    مصدر الحقيقة لما دُفع فعلاً — بخلاف `amount_paid` الذي تُصفّره مسارات إلغاء
    الترحيل من الخارج فيفقد أي قدرة على حراسة الازدواج.
    """
    total = Decimal("0")
    rows = PaymentAllocation.objects.filter(
        invoice_id=invoice_id, payment__is_posted=True,
    ).values_list("amount", "amount_in_invoice_currency")
    for amount, in_inv_currency in rows:
        total += Decimal(str(in_inv_currency if in_inv_currency is not None else amount))
    return total.quantize(DEC)


def guard_invoice_allocation_total(invoice: SalesInvoice, *, incoming: Decimal) -> None:
    """T-ARINT: يمنع تجاوز مجموع التوزيعات المرحّلة إجماليَّ الفاتورة.

    يُستدعى دائماً **داخل معاملة وبعد قفل صفّ الفاتورة** (select_for_update) —
    نفس نمط `post_customer_payment` — فلا يتسلّل سندان متزامنان على نفس الفاتورة.
    """
    grand = Decimal(str(invoice.grand_total or 0)).quantize(DEC)
    total = (posted_allocations_total(invoice.pk) + Decimal(str(incoming))).quantize(DEC)
    if total > grand + DEC:
        raise ValidationError(
            f"مجموع التوزيعات المرحّلة على الفاتورة #{invoice.invoice_number} "
            f"({total}) يتجاوز إجماليها ({grand}). راجع سندات القبض المرتبطة بها."
        )


def invoice_journal_debits_ar(invoice: SalesInvoice) -> bool:
    """هل يحتوي قيد الفاتورة سطراً مديناً على حساب ذمم العميل؟

    فواتير نقدية قديمة رُحّلت بنمط «Dr صندوق / Cr مبيعات» بلا سطر ذمم إطلاقاً؛
    إنشاء سند قبض لها يُدائن ذمماً لم تُمدَّن (ازدواج نقدية + دائن بلا مقابل).
    """
    if not invoice.journal_id:
        return False
    try:
        ar = _resolve_ar_account(invoice)
    except ValidationError:
        return False
    return JournalLine.objects.filter(
        journal_id=invoice.journal_id, account_id=ar.id, debit__gt=0,
    ).exists()


def invoice_journal_settlement_credit(invoice: SalesInvoice) -> Decimal:
    """T3: ما سُوّي **داخل قيد الفاتورة نفسه** — مجموع دائن الذمم فيه.

    قبل T1 كانت الشيكات المرفقة (والنقد قبل ذلك) تُرحَّل سطرين داخل قيد الفاتورة
    — مدين «شيكات برسم التحصيل»/صندوق ÷ دائن ذمم — وتزيد `amount_paid` بلا صفّ
    `PaymentAllocation`. تلك القيود متوازنة وصحيحة: الفرقُ الناتج في `amount_paid`
    أثرٌ تاريخي لا فساد، ولفّه بسند لاحق يُدائن الذمم مرّتين. لذلك يُصنَّف ولا
    يُصلَح — انظر `audit_ar_integrity`.

    البيعُ وحده: مرجع البيع يُدائن الذمم **بحكم تعريفه** لا تسويةً، فلا يُقاس.
    """
    if (invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE) != SalesInvoice.INVOICE_KIND_SALE:
        return Decimal("0")
    if not invoice.journal_id:
        return Decimal("0")
    try:
        ar = _resolve_ar_account(invoice)
    except ValidationError:
        return Decimal("0")
    total = JournalLine.objects.filter(
        journal_id=invoice.journal_id, account_id=ar.id, credit__gt=0,
    ).aggregate(total=Sum("credit"))["total"]
    return Decimal(str(total or 0)).quantize(DEC)


def is_auto_cash_settlement(payment: CustomerPayment, invoice: SalesInvoice) -> bool:
    """هل هذا السند هو تسوية الفاتورة النقدية التلقائية (لا سند مستخدم)؟

    العلامة الصريحة (`auto_settled_invoice`) هي المرجع. البيانات السابقة لها
    تُطابَق بتوقيع صارم: نصّ الملاحظات الذي يولّده الكود + توزيع وحيد على هذه
    الفاتورة نفسها — فلا يُلتقط سند مستخدم بالخطأ.
    """
    if payment.auto_settled_invoice_id == invoice.pk:
        return True
    if (payment.notes or "").strip() != _auto_settlement_note(invoice):
        return False
    allocs = list(payment.allocations.all())
    return len(allocs) == 1 and allocs[0].invoice_id == invoice.pk


def guard_invoice_payments_before_unpost(
    invoice: SalesInvoice, *, action_label: str = "إلغاء ترحيل"
) -> None:
    """T-ARINT: يمنع إلغاء ترحيل فاتورة عليها سندات قبض مرحّلة.

    الجذر المُصلَح: إلغاء الترحيل كان يصفّر `amount_paid` ويحذف قيود الفاتورة
    وحدها، فيبقى سند القبض مرحّلاً وقيده يُدائن ذمم العميل بلا مقابل، ويبقى صفّ
    التوزيع يتيماً يُدفع مرة ثانية عند أي تسوية لاحقة. مرآةُ حارس الاعتمادية
    الموجود في `unpost_document` لحركات المخزون.
    """
    rows = list(
        PaymentAllocation.objects.filter(
            invoice=invoice, payment__is_posted=True,
        ).select_related("payment")
    )
    if not rows:
        return
    listing = "، ".join(
        f"سند #{r.payment_id} ({Decimal(str(r.amount)).quantize(DEC)})" for r in rows
    )
    logger.warning(
        "unpost blocked for invoice %s: %d posted payment allocation(s)",
        invoice.invoice_number, len(rows),
    )
    raise ValidationError(
        f"تعذّر {action_label} الفاتورة {invoice.invoice_number}: توجد سندات قبض "
        f"مرحّلة موزّعة عليها ({listing}). ألغِ ترحيل هذه السندات (أو احذفها) "
        f"أولاً ثم أعد المحاولة."
    )


def release_auto_cash_settlement(invoice: SalesInvoice, *, user=None) -> list[int]:
    """يحرّر سند التسوية النقدية التلقائي قبل إلغاء ترحيل فاتورته.

    هذا السند من إنتاج الترحيل نفسه (`_auto_settle_cash_sale`) لا من إنشاء
    المستخدم، فيُحذف مع قيوده ضمن نفس معاملة إلغاء الترحيل ويُعاد إنشاؤه عند
    إعادة الترحيل — وإلا بقي معلّقاً وتضاعف عند كل إعادة ترحيل. سندات المستخدم
    لا تُمَسّ: يحرسها `guard_invoice_payments_before_unpost`.
    """
    candidates = (
        CustomerPayment.objects.filter(tenant_id=invoice.tenant_id)
        .filter(
            Q(auto_settled_invoice_id=invoice.pk)
            | Q(allocations__invoice_id=invoice.pk)
        )
        .distinct()
        .prefetch_related("allocations")
    )
    released: list[int] = []
    for payment in candidates:
        if not is_auto_cash_settlement(payment, invoice):
            continue
        if payment.is_posted:
            unpost_document(
                tenant_id=payment.tenant_id,
                reference_id=payment.id,
                journal_reference_types=["CUSTOMER_PAYMENT"],
                user=user,
                document_label=f"سند قبض تلقائي #{payment.id}",
            )
        payment_id = payment.id
        payment.delete()  # صفوف التوزيع تُحذف تلقائياً (CASCADE)
        released.append(payment_id)
        logger.info(
            "Released auto cash settlement %s of invoice %s (unpost).",
            payment_id, invoice.invoice_number,
        )
    return released


def unpost_customer_payment(payment: CustomerPayment, *, user=None) -> dict:
    """التراجع عن ترحيل سند قبض: حذف قيوده وإرجاع ما سدّده من الفواتير.

    المخرج الذي تُحيل إليه رسالة `guard_invoice_payments_before_unpost` — وبدونه
    يبقى المستخدم عالقاً بين فاتورة لا تُلغى وسند لا يُتراجع عنه. يعكس أيضاً
    `amount_paid` على كل فاتورة وُزِّع عليها (بعملة الفاتورة) فلا تبقى «مدفوعة»
    بلا تحصيل، ويعيد شيكات السند إلى مسودة كما تفعل الفاتورة.
    """
    if not payment.is_posted:
        raise ValidationError("السند غير مرحّل.")
    with transaction.atomic():
        payment = CustomerPayment.objects.select_for_update().get(pk=payment.pk)
        if not payment.is_posted:
            raise ValidationError("السند غير مرحّل.")
        result = unpost_document(
            tenant_id=payment.tenant_id,
            reference_id=payment.id,
            journal_reference_types=["CUSTOMER_PAYMENT"],
            user=user,
            document_label=f"سند قبض #{payment.id}",
        )
        allocations = list(payment.allocations.all())
        inv_ids = sorted({a.invoice_id for a in allocations})
        locked = {
            inv.pk: inv
            for inv in SalesInvoice.objects.select_for_update().filter(pk__in=inv_ids)
        }
        for alloc in allocations:
            inv = locked.get(alloc.invoice_id)
            if inv is None:
                continue
            back = Decimal(str(
                alloc.amount_in_invoice_currency
                if alloc.amount_in_invoice_currency is not None else alloc.amount
            ))
            inv.amount_paid = max(
                Decimal(str(inv.amount_paid or 0)) - back, Decimal("0")
            ).quantize(DEC)
            inv.save(update_fields=["amount_paid"])
        payment.is_posted = False
        payment.journal = None
        payment.save(update_fields=["is_posted", "journal"])

        from accounting.models import Cheque
        Cheque.objects.filter(
            customer_payment=payment, status="Under_Collection"
        ).update(status="Draft")

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="UNPOST",
            model_name="CustomerPayment",
            object_id=payment.id,
            change_details=(
                f"Unposted customer payment {payment.id}: "
                f"{result['journals_deleted']} journal(s), "
                f"{len(allocations)} allocation(s) reversed"
            ),
        )
    logger.info(
        "Unposted customer payment %s (journals=%s, allocations=%s).",
        payment.id, result["journals_deleted"], len(allocations),
    )
    return result


def _auto_settle_cash_sale(invoice: SalesInvoice, *, user=None) -> None:
    """T-CASH2: البيع النقدي مدفوع فوراً — تسوية تلقائية فور الترحيل.

    يُنشئ ويُرحّل «سند قبض» (CustomerPayment) بكامل المتبقّي على فاتورة بيع
    نقدية، فيُفرّغ ذمم العميل (Dr صندوق / Cr ذمم) ويحوّله من «مدين» إلى «مسدَّد».

    هذا يُكمل تصميم Feature 2 (قيد الفاتورة لا يُسوّي النقدية إطلاقاً؛ التحصيل
    سند مستقل يظهر في كشف حساب العميل) — كانت الأتمتة غير مربوطة سابقاً فبقي
    البيع النقدي مديناً للأبد. لا يلمس قيد الفاتورة، فيبقى اختبار التوجيه الفرعي
    (`test_subledger_routing`) سليماً: التسوية قيد منفصل.

    آمن: يقتصر على فواتير **البيع النقدية** (لا المراجيع/الآجل)، ويقتصر على
    الفواتير التي مُدِّنت ذممها في قيدها فعلاً.

    T-ARINT: المتبقّي (grand − amount_paid) وحده **لا يكفي** حارساً — فـ
    `amount_paid` يُصفَّر من الخارج عند إلغاء الترحيل، فكان كل إعادة ترحيل تُنشئ
    سنداً إضافياً يُدائن الذمم مرّة أخرى. الحارسان الفعليان:
      1. وجود أي توزيع سند **مرحّل** على الفاتورة ⇒ سُوِّيت فعلاً، لا تُسوَّ ثانيةً.
      2. خلوّ قيد الفاتورة من مدين على حساب ذمم العميل (نمط قديم سوّى الصندوق
         داخل قيدها) ⇒ سندٌ هنا يُدائن ذمماً لم تُمدَّن.
    إن غاب حساب الصندوق يُسجَّل تحذير ويُتخطّى دون كسر الترحيل.
    """
    if invoice.invoice_type != SalesInvoice.INVOICE_CASH:
        return
    if (invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE) != SalesInvoice.INVOICE_KIND_SALE:
        return
    settled = posted_allocations_total(invoice.pk)
    if settled > 0:
        logger.info(
            "Cash sale %s already has posted payment allocations (%s) — "
            "auto-settlement skipped.", invoice.invoice_number, settled,
        )
        return
    remaining = (
        Decimal(str(invoice.grand_total or 0)) - Decimal(str(invoice.amount_paid or 0))
    ).quantize(DEC)
    if remaining <= DEC:
        return
    if not invoice_journal_debits_ar(invoice):
        logger.warning(
            "Cash sale %s has no AR debit in its journal (legacy direct-cash "
            "posting) — auto-settlement skipped to avoid crediting untouched AR.",
            invoice.invoice_number,
        )
        return
    cash_account_id = _resolve_settlement_cash_account_id(invoice)
    if not cash_account_id:
        logger.warning(
            "Cash sale %s posted without a cash account — customer left as debtor "
            "(no auto-settlement). Set SalesSettings.default_cash_account.",
            invoice.invoice_number,
        )
        return
    payment = CustomerPayment.objects.create(
        tenant_id=invoice.tenant_id,
        partner_id=invoice.customer_id,
        payment_date=invoice.invoice_date,
        amount=remaining,
        currency_id=invoice.currency_id,
        exchange_rate=invoice.exchange_rate or Decimal("1"),
        cash_or_bank_account_id=cash_account_id,
        # T-ARINT: العلامة تجعل السند مملوكاً للفاتورة — يُحرَّر معها عند إلغاء
        # ترحيلها بدل أن يبقى معلّقاً ويتكرّر عند إعادته.
        auto_settled_invoice=invoice,
        notes=_auto_settlement_note(invoice),
    )
    PaymentAllocation.objects.create(
        tenant_id=invoice.tenant_id,
        payment=payment,
        invoice=invoice,
        amount=remaining,
    )
    post_customer_payment(payment, user=user)
    from core.activity import log_activity
    log_activity(
        action="payment", entity_type="customer_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="سند قبض نقدي تلقائي",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    log_activity(
        action="post", entity_type="customer_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="ترحيل سند قبض نقدي تلقائي",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    logger.info(
        "Auto-settled cash sale %s via customer payment %s (amount %s).",
        invoice.invoice_number, payment.id, remaining,
    )


def _attached_settlement_note(invoice: SalesInvoice) -> str:
    """توقيع سند تحصيل ما وصل مرفقاً مع الفاتورة (شيكات ± نقد)."""
    return f"تحصيل مرفق مع الفاتورة {invoice.invoice_number}"


def _resolve_settlement_cash_account_id(invoice: SalesInvoice) -> int | None:
    """صندوق تسوية الفاتورة: حسابها النقدي ← النقدي المرفق ← افتراضي الشركة."""
    cash_account_id = invoice.cash_or_bank_account_id or invoice.attached_cash_account_id
    if cash_account_id:
        return cash_account_id
    # T-DEFACC: مصدر الصندوق الافتراضي واحد لكل المعاملات.
    from accounting.services import resolve_default_cash_account

    default_cash = resolve_default_cash_account(invoice.tenant_id)
    return default_cash.pk if default_cash else None


def _settle_attached_cheques(invoice: SalesInvoice, *, user=None) -> None:
    """T1: الشيكات المرفقة بالفاتورة تُحصَّل بسند قبض مملوك لها، لا داخل قيدها.

    قبل هذا كانت تُرحَّل سطرين في قيد الفاتورة نفسه (مدين شيكات برسم التحصيل /
    دائن ذمم) وتزيد `amount_paid` بلا صفّ `PaymentAllocation` واحد — فيقول
    الحقل «دُفع» بينما لا توزيع يُثبته: تنكسر حالة الفاتورة المشتقّة، ويسقط
    الحارس الذي يمنع تحصيل المبلغ مرّتين، ولا يظهر التحصيل مستنداً في كشف حساب
    العميل. السند هنا يمرّ من `post_customer_payment` — نفس مسار شاشة السندات —
    فيقسم المدين بين «شيكات برسم التحصيل» والصندوق ويُرقّي الشيكات بنفسه.

    على الفاتورة **النقدية** يغطّي السند نفسه باقي المبلغ نقداً، فيبقى تحصيلها
    مستنداً واحداً ويجد `_auto_settle_cash_sale` بعده الفاتورةَ مسوّاةً فيتخطّاها.

    السند من إنتاج الترحيل لا من إنشاء المستخدم (`auto_settled_invoice`) ⇒
    يُحرَّر مع إلغاء ترحيل الفاتورة (`release_auto_cash_settlement`) وتعود
    شيكاته مسودةً، فلا يبقى دائن ذمم بلا مقابل ولا يتكرّر عند إعادة الترحيل.
    """
    from accounting.models import Cheque

    if (invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE) != SalesInvoice.INVOICE_KIND_SALE:
        # الشيك الوارد لا معنى له على مرجع أو على فاتورة شراء — يُترك مسودةً
        # بلا تسوية بدل أن يُقيَّد بإشارة مقلوبة.
        return
    cheques = list(
        Cheque.objects.filter(
            tenant_id=invoice.tenant_id, sales_invoice=invoice,
            status="Draft", customer_payment__isnull=True,
        )
    )
    cheques_total = sum(
        (Decimal(str(c.amount or 0)) for c in cheques), Decimal("0")
    ).quantize(DEC)
    if cheques_total <= 0:
        return
    if not invoice_journal_debits_ar(invoice):
        logger.warning(
            "Invoice %s has no AR debit in its journal — attached cheques left "
            "as drafts to avoid crediting untouched AR.", invoice.invoice_number,
        )
        return
    settled = posted_allocations_total(invoice.pk)
    remaining = (
        Decimal(str(invoice.grand_total or 0))
        - max(Decimal(str(invoice.amount_paid or 0)), settled)
    ).quantize(DEC)
    if remaining <= 0:
        return
    # البيع النقدي مدفوع فوراً ⇒ يُكمل السندُ نفسه ما لم تغطّه الشيكات نقداً.
    amount = cheques_total
    if invoice.invoice_type == SalesInvoice.INVOICE_CASH and remaining > cheques_total:
        amount = remaining
    cash_account_id = _resolve_settlement_cash_account_id(invoice)
    if not cash_account_id:
        # الصندوق حقل إلزامي على السند. التخطّي هنا يعني إسقاط شيكات مقبوضة
        # بصمت، فالترحيل كلّه يرتدّ ويبقى المستند مسودة مع رسالة تُسمّي الإعداد.
        raise ValidationError(
            f"الفاتورة {invoice.invoice_number} عليها شيكات مرفقة لكن لا يوجد "
            "حساب صندوق/بنك لتحرير سند القبض. عيّن `default_cash_account` في "
            "إعدادات المبيعات أو حدّد حساب الصندوق على الفاتورة."
        )
    payment = CustomerPayment.objects.create(
        tenant_id=invoice.tenant_id,
        partner_id=invoice.customer_id,
        payment_date=invoice.invoice_date,
        amount=amount,
        currency_id=invoice.currency_id,
        exchange_rate=invoice.exchange_rate or Decimal("1"),
        cash_or_bank_account_id=cash_account_id,
        auto_settled_invoice=invoice,
        notes=_attached_settlement_note(invoice),
    )
    Cheque.objects.filter(pk__in=[c.pk for c in cheques]).update(
        customer_payment=payment
    )
    PaymentAllocation.objects.create(
        tenant_id=invoice.tenant_id,
        payment=payment,
        invoice=invoice,
        amount=min(amount, remaining),
    )
    post_customer_payment(payment, user=user)
    from core.activity import log_activity

    log_activity(
        action="payment", entity_type="customer_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="سند قبض شيكات مرفقة",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    log_activity(
        action="post", entity_type="customer_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="ترحيل سند قبض شيكات مرفقة",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    logger.info(
        "Settled attached cheques of invoice %s via customer payment %s "
        "(cheques %s of %s).",
        invoice.invoice_number, payment.id, cheques_total, amount,
    )


def post_sales_invoice(
    invoice: SalesInvoice,
    *,
    user=None,
    suppress_auto_settlement: bool = False,
) -> SalesInvoice:
    """ترحيل فاتورة: قيد محاسبي + (اختياري) خصم مخزون.

    N8-T11: يَدعم الآن 4 أنواع (فاتورة بيع/مرجع بيع/فاتورة شراء/مرجع شراء)
    عبر حقل `invoice_kind`. للمراجيع، تُعكس إشارات القيد والمخزون.

    T1: القيد الناتج **لا يُسوّي شيئاً** — لا نقداً ولا شيكات — ولا يزيد
    `amount_paid`. ما وصل مرفقاً مع الفاتورة يُحصَّل بعد الترحيل وداخل نفس
    المعاملة بسند قبض حقيقي: `_settle_attached_cheques` للشيكات المرفقة (وباقي
    المبلغ نقداً على الفاتورة النقدية)، ثم `_auto_settle_cash_sale` للبيع
    النقدي بلا شيكات (T-CASH2) — فلا يبقى العميل مديناً.

    T2: `suppress_auto_settlement` يكبت **التسويتين معاً** (الشيكات المرفقة ثم
    البيع النقدي) — يستعمله `collect_invoice_payment` وحده حين يحمل المستخدم
    تفصيل تحصيله (نقد/شيكات/رصيد): تحصيلُه الصريح **يحلّ محلّ** التلقائي، وإلّا
    خطفت التسويةُ التلقائية كامل المتبقّي قبل أن يوزّع تقسيمُه، فخرج سندان على
    فاتورة واحدة. الافتراضي `False` ⇒ كل نداء قائم يبقى على سلوكه حرفياً.
    """
    if invoice.status == SalesInvoice.STATUS_POSTED:
        raise ValidationError("الفاتورة مرحّلة مسبقاً.")
    if invoice.status == SalesInvoice.STATUS_CANCELLED:
        raise ValidationError("لا يمكن ترحيل فاتورة ملغاة.")

    # N8-T11: sign multiplier للمراجيع
    kind = invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE
    is_return = kind in (SalesInvoice.INVOICE_KIND_SALE_RETURN, SalesInvoice.INVOICE_KIND_PURCHASE_RETURN)
    sign = -1 if is_return else 1

    lines = list(
        invoice.lines.select_related("product", "tax_rate", "tax_rate__tax_account", "product__tenant")
    )
    if not lines:
        raise ValidationError("الفاتورة بلا بنود.")

    if invoice.customer.tenant_id != invoice.tenant_id:
        raise ValidationError("العميل لا يتبع نفس الشركة (Tenant).")

    recalculate_invoice_amounts(invoice, lines)
    SalesInvoiceLine.objects.bulk_update(
        lines,
        ["line_total_excl_tax", "line_tax_amount"],
    )
    SalesInvoice.objects.filter(pk=invoice.pk).update(
        subtotal_excl_tax=invoice.subtotal_excl_tax,
        tax_amount=invoice.tax_amount,
        grand_total=invoice.grand_total,
    )
    invoice.refresh_from_db()
    lines = list(
        invoice.lines.select_related("product", "tax_rate", "tax_rate__tax_account", "product__tenant")
    )

    validate_fiscal_period(invoice.tenant_id, invoice.invoice_date)

    # المراجيع تُخفّض الذمم لا تزيدها ⇒ لا تُخضَع لفحص حدّ الائتمان.
    if invoice.invoice_type == SalesInvoice.INVOICE_CREDIT and not is_return:
        if invoice.customer.partner_type != "Customer":
            raise ValidationError("الطرف المحدد ليس عميلاً.")
        limit = invoice.customer.credit_limit
        if limit is not None:
            open_bal = _partner_open_balance_excluding_invoice(
                invoice.customer, exclude_invoice_id=invoice.pk
            )
            if open_bal + invoice.grand_total > Decimal(str(limit)) + DEC:
                raise ValidationError(
                    f"تجاوز حد الائتمان. الحد: {limit} — الرصيد المفتوح: {open_bal} — إجمالي الفاتورة: {invoice.grand_total}"
                )

    grand = invoice.grand_total

    with transaction.atomic():
        lines = list(
            invoice.lines.select_related(
                "tax_rate",
                "tax_rate__tax_account",
                "product__tenant",
                "product__category",
                "product__category__revenue_account",
                "product__category__cogs_account",
                "product__category__inventory_account",
            )
        )
        products_by_id = _lock_products_for_lines(lines)
        for line in lines:
            line.product = products_by_id[line.product_id]

        # منع فاتورة الخسارة (إعداد اختياري، على مستوى السطر) — بعد قفل الأصناف والإجماليات.
        guard_loss_invoice(invoice, lines, products_by_id)

        # T-RESERVEGUARD: الكمية المحجوزة لطلبية زبون آخر ليست متاحة للبيع —
        # يُفحص بعد قفل الأصناف كي لا تسبق فاتورتان بعضهما على نفس الحجز.
        guard_reserved_stock(invoice, lines, products_by_id)

        journal_lines: list[dict] = []

        # ── T1: المرفق مع الفاتورة يُفحص هنا ولا يُرحَّل هنا ──────────────────
        # الأصيل يكتب «مدفوع نقدا» و«مدفوع شيكات» على وجه الفاتورة نفسها، وكان
        # هذا القيد يُترجمهما سطوراً مدينة داخله. لم يعد: التحصيل — أياً كان
        # وجهه — سندُ قبض مستقل يُنشأ بعد الترحيل (`_settle_attached_cheques`
        # ثم `_auto_settle_cash_sale`)، فيبقى `amount_paid` مساوياً دائماً
        # لمجموع توزيعات السندات المرحّلة. ما بقي هنا فحصٌ لا ترحيل.
        attached_cash = Decimal(str(invoice.attached_cash_amount or 0)).quantize(DEC)
        # Cheques attached via accounting.Cheque.sales_invoice FK (M2-T3 migration)
        attached_cheques = list(invoice.cheques.all()) if invoice.pk else []
        cheques_total = sum(
            (Decimal(str(c.amount or 0)) for c in attached_cheques),
            Decimal("0.00"),
        ).quantize(DEC)
        attached_total = (attached_cash + cheques_total).quantize(DEC)
        if attached_total > grand:
            raise ValidationError(
                f"مجموع المرفق مع الفاتورة (نقدي {attached_cash} + شيكات "
                f"{cheques_total}) يتجاوز مبلغ الفاتورة {grand}."
            )

        # ── خصم المصدر (يُحسب مبكراً ليُخصم من التحصيل النقدي) ───────────────
        # خصم المصدر = الجزء الذي يحتجزه العميل كاستقطاع ضريبي ضد البائع
        # (Aseel «خصم مصدر»). أولوية: تجاوز الفاتورة (مبلغ ثم نسبة) ← افتراضي
        # العميل (مبلغ ثم نسبة). يُرحَّل سطره وتُخفَّض الذمم في كتلة الـ G6 أدناه.
        src_disc_amt = Decimal("0.00")
        src_disc_pct_used = Decimal("0.00")
        if invoice.source_discount_amount_override is not None:
            src_disc_amt = Decimal(str(invoice.source_discount_amount_override)).quantize(DEC)
        elif invoice.source_discount_percent_override is not None:
            src_disc_pct_used = Decimal(str(invoice.source_discount_percent_override))
            src_disc_amt = (grand * src_disc_pct_used / Decimal("100")).quantize(DEC)
        elif invoice.customer:
            cust_amt = Decimal(str(getattr(invoice.customer, "source_discount_amount", 0) or 0))
            cust_pct = Decimal(str(getattr(invoice.customer, "source_discount_percent", 0) or 0))
            if cust_amt > 0:
                src_disc_amt = cust_amt
            elif cust_pct > 0:
                src_disc_pct_used = cust_pct
                src_disc_amt = (grand * src_disc_pct_used / Decimal("100")).quantize(DEC)
        if src_disc_amt > grand:
            src_disc_amt = grand

        # ── Section B: القيد يمرّ دائماً عبر حساب ذمم العميل ──────────────────
        # حتى البيع النقدي يُقيَّد أولاً على ذمم العميل بكامل القيمة، ثم يُسوَّى
        # التحصيل (نقدي/شيكات) بحركة دائنة على نفس الحساب — كي يعكس كشف حساب
        # العميل والأعمار كل الحركات (المطلب المحاسبي للمالك). journal_lines[0]
        # هو دائماً سطر الذمم بكامل الإجمالي ليبقى مرجع تخفيض خصم المصدر ثابتاً.
        ar = _resolve_ar_account(invoice)
        journal_lines.append(
            {
                "account": ar.id,
                "partner": invoice.customer_id,
                "debit": grand,
                "credit": Decimal("0"),
                "description": f"ذمم — {invoice.invoice_number}",
            }
        )

        # ── Feature 2 + T1: قيد الفاتورة لا يُسوّي شيئاً — لا نقداً ولا شيكات ─
        # قيد الفاتورة (Entry A) يدين ذمم العميل بالكامل ويدائن الإيراد/الضريبة
        # (+COGS/المخزن). التحصيل — نقداً كان أم شيكات، وحتى للبيع النقدي —
        # سندُ قبض مستقل (CustomerPayment، Entry B: مدين النقدية/الشيكات برسم
        # التحصيل / دائن ذمم العميل). كانت الشيكات المرفقة تُسوَّى هنا داخل
        # القيد وتزيد `amount_paid` بلا صفّ توزيع واحد، فينكسر الثابت
        # «المدفوع = مجموع توزيعات السندات المرحّلة» ويصير المبلغ قابلاً
        # للتحصيل مرّتين. لذا لا حركة نقدية ولا شيكات هنا إطلاقاً.

        for acc_id, cred_amt in _revenue_credit_journal_rows(invoice, lines):
            if cred_amt > 0:
                journal_lines.append(
                    {
                        "account": acc_id,
                        "partner": None,
                        "debit": Decimal("0"),
                        "credit": cred_amt,
                        "description": f"مبيعات — {invoice.invoice_number}",
                    }
                )

        tax_buckets = _build_tax_buckets(lines)
        for tax_account_id, amt in tax_buckets.items():
            if amt <= 0:
                continue
            journal_lines.append(
                {
                    "account": tax_account_id,
                    "partner": None,
                    "debit": Decimal("0"),
                    "credit": amt.quantize(DEC),
                    "description": f"ضريبة مخرجات — {invoice.invoice_number}",
                }
            )

        if invoice.stock_on_post:
            journal_lines.extend(_build_cogs_journal_line_dicts(invoice, lines, products_by_id))

        # ── M2-T4 (G6): Source-discount / withholding ──────────────────────
        # Source discount = the slice of the invoice the customer holds back as
        # withholding tax against the seller (Aseel «خصم مصدر»). It is NOT the
        # regular invoice discount (`discount_percent`/`invoice_discount`) which
        # is ALREADY netted into `subtotal_excl_tax`/`grand_total` upstream.
        #
        # Lookup priority (per-invoice override → customer default):
        #   1. invoice.source_discount_amount_override (explicit amount)
        #   2. invoice.source_discount_percent_override (% of grand_total)
        #   3. customer.source_discount_amount  (default amount)
        #   4. customer.source_discount_percent (default % of grand_total)
        # NOTE: `src_disc_amt`/`src_disc_pct_used` are computed earlier (before
        # the AR/cash settlement block) so the cash collection can net the
        # withheld amount. Here we only emit the line + reduce the AR debit.
        if src_disc_amt > 0:
            ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
            disc_acct = None
            # Priority: dedicated SalesSettings setting → COA code 1107 (Asset).
            if ss and ss.default_source_discount_account_id:
                disc_acct = ss.default_source_discount_account
            if not disc_acct:
                disc_acct = Account.objects.filter(
                    tenant_id=invoice.tenant_id,
                    code__startswith="1107",
                    account_type="Asset",
                    is_active=True,
                ).first()
            if not disc_acct:
                raise ValidationError(
                    "خصم المصدر مفعّل (افتراضي العميل أو تجاوز الفاتورة) لكن لا يوجد حساب "
                    "خصم مصدر مهيّأ. عيّن `default_source_discount_account` في إعدادات "
                    "المبيعات، أو أنشئ حساب Asset بكود يبدأ بـ 1107 (خصم مصدر مقدّم)."
                )
            # Add Dr source-discount-receivable for the withheld amount.
            desc_pct = (
                f" ({src_disc_pct_used}%)" if src_disc_pct_used > 0 else ""
            )
            journal_lines.append({
                "account": disc_acct.id,
                # خصم المصدر مطالبة على مصلحة الضرائب لا على العميل — بلا شريك،
                # وإلا أُعيد المبلغُ المخصومُ من سطر الذمم إلى رصيد العميل فضخّمه.
                "partner": None,
                "debit": src_disc_amt,
                "credit": Decimal("0"),
                "description": f"خصم مصدر{desc_pct} — {invoice.invoice_number}",
            })
            # REDUCE the AR debit line by src_disc_amt — customer actually owes
            # `grand − src_disc_amt`; the rest is now a claim on the tax
            # authority. Journal remains balanced because we added a Dr of the
            # same amount on the source-discount account. journal_lines[0] is
            # always the full-grand AR line (built above for every invoice type).
            recv_line = journal_lines[0]
            recv_line["debit"] = (Decimal(str(recv_line["debit"])) - src_disc_amt).quantize(DEC)

        tenant_name = ""
        try:
            tenant_name = (invoice.tenant.CompanyName or "").strip()
        except AttributeError:
            tenant_name = ""
        cust_name = ""
        try:
            cust_name = (invoice.customer.name or "").strip()
        except AttributeError:
            cust_name = ""
        # N8-T11: عكس إشارات القيد للمراجيع
        if is_return:
            kind_label = dict(SalesInvoice.INVOICE_KIND_CHOICES).get(kind, kind)
            for jl in journal_lines:
                jl["debit"], jl["credit"] = jl["credit"], jl["debit"]

        desc_parts = []
        if tenant_name:
            desc_parts.append(f"[{tenant_name}]")
        kind_label = dict(SalesInvoice.INVOICE_KIND_CHOICES).get(kind, "فاتورة")
        desc_parts.append(f"{kind_label} {invoice.invoice_number}")
        if cust_name:
            desc_parts.append(f"— {cust_name}")
        if invoice.notes:
            desc_parts.append(f"· {invoice.notes}")
        final_desc = " ".join(desc_parts)[:500]

        jh = post_journal(
            tenant_id=invoice.tenant_id,
            transaction_date=invoice.invoice_date,
            reference_type="SALES_INVOICE",
            reference_id=invoice.id,
            description=final_desc,
            lines_data=journal_lines,
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate,
            user=user,
            branch_id=invoice.branch_id,
        )

        invoice.journal = jh
        invoice.status = SalesInvoice.STATUS_POSTED
        # T1: الترحيل نفسه لا يمسّ `amount_paid` — كل زيادة عليه تأتي من
        # `post_customer_payment` مقرونةً بصفّ `PaymentAllocation`، فيبقى
        # الثابت «المدفوع = مجموع توزيعات السندات المرحّلة» صحيحاً بالبناء.
        invoice.save(update_fields=["journal", "status"])

        # الشيكات المرفقة تُرقّى إلى «برسم التحصيل» بترحيل سندها لا بترحيل
        # الفاتورة (`post_customer_payment`) — فلا تُرقّى هنا.

        if invoice.stock_on_post:
            if is_return:
                # N8-T11 + P-H-2: stock reconciliation by return direction.
                # sale_return → RETURN_IN  (goods come back from customer)
                # purchase_return → RETURN_OUT (goods leave back to supplier)
                is_purchase_return = kind == SalesInvoice.INVOICE_KIND_PURCHASE_RETURN
                mv_type = "RETURN_OUT" if is_purchase_return else "RETURN_IN"
                for line in lines:
                    if getattr(line.product, "is_service", False):
                        continue
                    record_stock_movement(
                        product=line.product,
                        movement_type=mv_type,
                        quantity=line.quantity,
                        reference_type="SALE",
                        reference_id=invoice.id,
                        partner=invoice.customer,
                        movement_date=invoice.invoice_date,
                        notes=f"مرجع {invoice.invoice_number}",
                        tenant=invoice.tenant,
                        branch=invoice.branch,
                    )
            else:
                _post_stock_out_for_invoice(invoice, lines, user=user)
            # البضاعة خرجت مع الترحيل ⇒ الفاتورة مسلَّمة بالكامل، وتُوثَّق
            # بإرسالية تلقائية بكامل الكمية (مرآة إرسالية الشراء التلقائية).
            for line in lines:
                if getattr(line.product, "is_service", False):
                    continue
                line.delivered_quantity = line.quantity
            SalesInvoiceLine.objects.bulk_update(lines, ["delivered_quantity"])
            _create_auto_delivery_document(invoice, lines)
        sync_invoice_delivery_status(invoice, lines)

        # الوحدة المُرقَّمة تُستهلَك بترحيل فاتورتها لا بخروجها من المستودع: البيع
        # هو ما يُسند الوحدة لزبون، ويبقى السؤال «أي وحدة ذهبت لمن» مُجاباً حتى
        # حين يتأخّر التسليم (`stock_on_post=False`). ومرجع البيع يعكسها: البضاعة
        # رجعت للمخزن (RETURN_IN) فوحداتها تعود «في المخزن» بترتيب استهلاكها.
        if kind == SalesInvoice.INVOICE_KIND_SALE:
            consume_sales_serials(invoice, lines)
            # THA-24: بطاقة الكفالة نسخةٌ تُصرف للوحدة التي ذهبت للزبون، فلا
            # تُنشأ إلا بعد استهلاك الوحدات أعلاه. صفر أثر لشركة غير مرخّصة.
            from after_sales.services import create_auto_warranty_cards

            create_auto_warranty_cards(invoice)
        elif kind == SalesInvoice.INVOICE_KIND_SALE_RETURN:
            restore_returned_sales_serials(invoice, lines)

        create_audit_log(
            tenant=invoice.tenant,
            user=user,
            action="POST",
            model_name="SalesInvoice",
            object_id=invoice.id,
            change_details=f"Posted sales invoice {invoice.invoice_number} journal={jh.id}",
        )

        # T1: الشيكات المرفقة تُحصَّل بسند قبض حقيقي — وعلى الفاتورة النقدية
        # يغطّي السند نفسه باقي المبلغ نقداً، فيبقى تحصيلها مستنداً واحداً.
        # T2: كلتا التسويتين تُكبَتان معاً حين يأتي التحصيل مفصَّلاً من المنسّق.
        if not suppress_auto_settlement:
            _settle_attached_cheques(invoice, user=user)
            # T-CASH2: البيع النقدي = مدفوع فوراً ⇒ سوِّه بسند قبض مستقل داخل نفس
            # المعاملة (ذرّياً مع الترحيل) فلا يبقى العميل مديناً. (يُلغي نفسه إن
            # كان سند الشيكات أعلاه قد غطّى الفاتورة.)
            _auto_settle_cash_sale(invoice, user=user)

    return invoice


def collect_invoice_payment(
    invoice: SalesInvoice,
    *,
    cash: Decimal | str | float | None = None,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    from_on_account: list[dict] | None = None,
    post_invoice: bool = False,
    payment_date=None,
    user=None,
) -> CustomerPayment | None:
    """T2: تحصيل الفاتورة من نقطة واحدة — نقد + شيكات + رصيد العميل، ذرّياً.

    كان «المبلغ نقداً» على الفاتورة حقلاً يُقبل من الـAPI ثم **لا يُرحَّل شيئاً**:
    مالٌ يدخل الصندوق في الواقع ولا أثر له في الدفاتر. هذه الدالة تُنهي ذلك: كل
    وجه من أوجه الدفع يمرّ من مسار السندات القائم نفسه، فلا قاعدة مالية ثانية.

    **صفر منطق ترحيل جديد** — تركيبُ خدمات قائمة داخل `transaction.atomic()` واحد:

    1. المسودة تُرحَّل بـ`post_sales_invoice(suppress_auto_settlement=has_spec)`:
       التحصيل الصريح يحلّ محلّ التسوية التلقائية، وإلّا خطفت كاملَ المتبقّي قبل
       أن يوزّع تقسيمُ المستخدم فخرج سندان.
    2. النقد + الشيكات ⇒ **سند قبض واحد** (`post_customer_payment`) بتوزيع واحد
       مقصوص على المتبقّي؛ ما زاد يُرحَّل «على الحساب» دفعةً مقدَّمة (T-ONACC).
    3. كل صفّ `from_on_account` ⇒ `allocate_customer_payment`: ربطٌ بلا قيد
       جديد — قرار المالك 2026-07-25، إذ خفّض ترحيلُ ذلك السند الذمم أصلاً.
    4. **الفاتورة النقدية مدفوعة فوراً بالتعريف.** نقدٌ لم يُذكر يُكمَّل تلقائياً
       (نفس قاعدة `_settle_attached_cheques`)، ونقصٌ بعد نقدٍ **مذكور** يُرفض
       ويرتدّ كلّ شيء: «اجعلها فاتورة ذمم أو أكمل المبلغ».
    5. بلا تحصيل مذكور أصلاً ⇒ الترحيل وحده، والتسوية التلقائية كما هي اليوم.

    الكلّ أو لا شيء عمداً، بلا `auto_post_error` كما في إنشاء الفاتورة: نقرةٌ
    واحدة لا يجوز أن تترك فاتورةً مرحّلة وسنداً نصفَ مولود لم يره المستخدم.

    from_on_account: `[{"payment_id": <id>, "amount": <Decimal|str>}, ...]`
    """
    from accounting.models import Cheque

    kind = invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE
    cheque_rows = list(cheques or [])
    on_account_rows = list(from_on_account or [])
    # «غير مذكور» ≠ «صفر»: الأول يُكمَّل على الفاتورة النقدية، والثاني إعلانُ
    # نيّةٍ بعدم دفع نقد فيُحاسَب عليه.
    cash_given = cash is not None and str(cash).strip() != ""
    try:
        cash_amount = Decimal(str(cash or 0)).quantize(DEC)
    except Exception:
        raise ValidationError("مبلغ النقدي غير صالح.")
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")
    new_cheques_total = _validate_cheque_payloads(cheque_rows, require_due_date=True)

    on_account_total = Decimal("0")
    for i, row in enumerate(on_account_rows):
        if not row.get("payment_id"):
            raise ValidationError(f"الرصيد #{i+1}: رقم سند القبض مطلوب.")
        try:
            amt = Decimal(str(row.get("amount", 0)))
        except Exception:
            raise ValidationError(f"الرصيد #{i+1}: مبلغ غير صالح.")
        if amt <= 0:
            raise ValidationError(f"الرصيد #{i+1}: المبلغ يجب أن يكون أكبر من صفر.")
        on_account_total += amt

    has_spec = cash_amount > 0 or bool(cheque_rows) or bool(on_account_rows)
    if has_spec and kind != SalesInvoice.INVOICE_KIND_SALE:
        raise ValidationError(
            "سند قبض العميل لا يصحّ إلا على فاتورة بيع — استعمل مستند الجهة "
            "المقابلة لهذا النوع."
        )

    payment: CustomerPayment | None = None
    with transaction.atomic():
        posted_now = False
        if invoice.status == SalesInvoice.STATUS_DRAFT:
            if not post_invoice:
                raise ValidationError(
                    f"الفاتورة {invoice.invoice_number} مسودة — رحّلها أولاً أو "
                    "اطلب الترحيل مع التحصيل."
                )
            post_sales_invoice(
                invoice, user=user, suppress_auto_settlement=has_spec)
            posted_now = True
        elif invoice.status != SalesInvoice.STATUS_POSTED:
            raise ValidationError("لا يمكن التحصيل على فاتورة ملغاة.")

        invoice.refresh_from_db()
        if not has_spec:
            if not posted_now:
                raise ValidationError("لا مبلغ للتحصيل.")
            return None  # الترحيل وحده — والتسوية التلقائية جرت كما اليوم

        remaining = (
            Decimal(str(invoice.grand_total or 0))
            - Decimal(str(invoice.amount_paid or 0))
        ).quantize(DEC)
        # الشيكات المرفقة بالمسودة كانت ستُكنس في `_settle_attached_cheques`
        # لولا الكبت أعلاه — فيكنسها هذا السند بدلاً منه، ويبقى تحصيل الفاتورة
        # مستنداً واحداً مهما تعدّدت أوجه الدفع.
        swept = list(
            Cheque.objects.filter(
                tenant_id=invoice.tenant_id, sales_invoice=invoice,
                status="Draft", customer_payment__isnull=True,
            )
        ) if posted_now else []
        swept_total = sum(
            (Decimal(str(c.amount or 0)) for c in swept), Decimal("0")
        ).quantize(DEC)

        cheques_total = (new_cheques_total + swept_total).quantize(DEC)
        amount = (cash_amount + cheques_total).quantize(DEC)
        # ما يُنتظر من هذا السند تغطيته: المتبقّي ناقص ما سيُخصم من رصيد العميل.
        target = max((remaining - on_account_total).quantize(DEC), Decimal("0"))
        if (
            invoice.invoice_type == SalesInvoice.INVOICE_CASH
            and not cash_given and amount < target
        ):
            cash_amount = (cash_amount + target - amount).quantize(DEC)
            amount = (cash_amount + cheques_total).quantize(DEC)

        if amount > 0:
            if not invoice_journal_debits_ar(invoice):
                # نمط قديم سوّى النقدية داخل قيد الفاتورة بلا سطر ذمم مدين ⇒
                # سندٌ هنا يُدائن ذمماً لم تُمدَّن (ازدواج نقدية).
                raise ValidationError(
                    f"قيد الفاتورة {invoice.invoice_number} لا يُدين ذمم العميل "
                    "(ترحيل نقدي قديم داخل القيد)، فسند القبض عليها يُدائن ذمماً "
                    "لم تُمدَّن. ألغِ ترحيلها وأعِده ثم حصّلها."
                )
            resolved_cash_id = (
                cash_account_id or _resolve_settlement_cash_account_id(invoice)
            )
            if not resolved_cash_id:
                # الصندوق حقل إلزامي على السند — نفس رسالة T1 لا رسالة ثانية.
                raise ValidationError(
                    f"تحصيل الفاتورة {invoice.invoice_number} يحتاج حساب "
                    "صندوق/بنك لتحرير سند القبض. عيّن `default_cash_account` في "
                    "إعدادات المبيعات أو حدّد حساب الصندوق على الفاتورة."
                )
            payment = CustomerPayment.objects.create(
                tenant_id=invoice.tenant_id,
                partner_id=invoice.customer_id,
                payment_date=payment_date or invoice.invoice_date,
                amount=amount,
                currency_id=invoice.currency_id,
                exchange_rate=invoice.exchange_rate or Decimal("1"),
                cash_or_bank_account_id=resolved_cash_id,
                # السند المولود مع الترحيل يملكه الترحيل: يُحرَّر معه عند إلغائه
                # (`release_auto_cash_settlement`) فلا يبقى دائن ذمم بلا مقابل.
                # أمّا التحصيل على فاتورة مرحّلة سلفاً فسند مستخدم مستقلّ يحرسه
                # `guard_invoice_payments_before_unpost`.
                auto_settled_invoice=invoice if posted_now else None,
                notes="تحصيل من داخل الفاتورة",
            )
            for c in cheque_rows:
                Cheque.objects.create(
                    tenant_id=invoice.tenant_id,
                    sales_invoice=invoice,
                    customer_payment=payment,
                    partner=invoice.customer,
                    direction="Incoming",
                    status="Draft",  # يصير «برسم التحصيل» بترحيل السند
                    cheque_number=str(c.get("cheque_number")).strip(),
                    bank_name=(c.get("bank_name") or "")[:100],
                    account_number=(c.get("account_number") or "")[:50],
                    bank_branch=(c.get("bank_branch") or "")[:100],
                    amount=Decimal(str(c.get("amount"))).quantize(DEC),
                    currency_id=invoice.currency_id,
                    due_date=c.get("due_date") or None,
                    issue_date=c.get("issue_date") or None,
                    payee_name=(c.get("payee_name") or "")[:150],
                    notes=c.get("notes") or "",
                    created_by=(
                        user if user and not getattr(user, "is_anonymous", False)
                        else None
                    ),
                )
            if swept:
                Cheque.objects.filter(pk__in=[c.pk for c in swept]).update(
                    customer_payment=payment
                )
            allocated = min(amount, target)
            if allocated > 0:
                PaymentAllocation.objects.create(
                    tenant_id=invoice.tenant_id,
                    payment=payment,
                    invoice=invoice,
                    amount=allocated,
                )
            # ما زاد عن التوزيع يُرحّله `post_customer_payment` «على الحساب».
            post_customer_payment(payment, user=user)
            from core.activity import log_activity

            log_activity(
                action="payment", entity_type="customer_payment",
                entity_id=payment.id, entity_label=f"#{payment.id}",
                description="سند قبض من داخل الفاتورة",
                partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
            )
            log_activity(
                action="post", entity_type="customer_payment",
                entity_id=payment.id, entity_label=f"#{payment.id}",
                description="ترحيل سند قبض من داخل الفاتورة",
                partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
            )

        for row in on_account_rows:
            source = CustomerPayment.objects.filter(
                pk=row["payment_id"], tenant_id=invoice.tenant_id,
            ).first()
            if source is None:
                raise ValidationError(
                    f"سند القبض #{row['payment_id']} غير موجود في هذه الشركة."
                )
            if source.partner_id != invoice.customer_id:
                raise ValidationError(
                    f"سند القبض #{source.pk} لا يخصّ عميل الفاتورة."
                )
            if not source.is_posted:
                raise ValidationError(
                    f"سند القبض #{source.pk} غير مرحّل — لا رصيد منه على الحساب."
                )
            allocate_customer_payment(
                source,
                [{"invoice": invoice.pk, "amount": row["amount"]}],
                user=user,
            )

        invoice.refresh_from_db()
        left = (
            Decimal(str(invoice.grand_total or 0))
            - Decimal(str(invoice.amount_paid or 0))
        ).quantize(DEC)
        if invoice.invoice_type == SalesInvoice.INVOICE_CASH and left > DEC:
            raise ValidationError(
                "الفاتورة نقدية — المدفوع لا يغطي الإجمالي؛ اجعلها فاتورة ذمم "
                "أو أكمل المبلغ."
            )
        logger.info(
            "Collected invoice %s: payment=%s amount=%s on_account=%s left=%s",
            invoice.invoice_number, getattr(payment, "id", None),
            getattr(payment, "amount", 0), on_account_total, left,
        )

    return payment


def _post_stock_out_for_invoice(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine],
    *,
    user=None,
) -> None:
    # Idempotency: skip if stock movement already exists for this invoice
    if StockMovement.objects.filter(
        reference_type="SALE", reference_id=invoice.id
    ).exists():
        return
    for line in lines:
        if getattr(line.product, "is_service", False):
            continue
        if line.product.tenant_id != invoice.tenant_id:
            raise ValidationError(f"الصنف {line.product_id} لا يتبع نفس الشركة.")
        try:
            record_stock_movement(
                product=line.product,
                movement_type="OUT",
                quantity=line.quantity,
                reference_type="SALE",
                reference_id=invoice.id,
                partner=invoice.customer,
                movement_date=invoice.invoice_date,
                notes=f"بيع فاتورة {invoice.invoice_number}",
                tenant=invoice.tenant,
                branch=invoice.branch,
            )
        except ValidationError as e:
            raise ValidationError(f"مخزون الصنف {line.product.sku}: {e}")


def issue_stock_from_invoice(invoice: SalesInvoice, *, user=None):
    """T4-05: إصدار إذن صرف صريح للمبيعات (STOCK_ISSUE).

    Idempotent: إن وُجد StockMovement بـ STOCK_ISSUE لنفس الفاتورة يُرجع مبكراً.
    يُستدعى من frontend_v2 بعد ترحيل الفاتورة وقبل التسليم.
    """
    if StockMovement.objects.filter(
        reference_type="STOCK_ISSUE", reference_id=invoice.id
    ).exists():
        return
    lines = list(invoice.lines.select_related("product"))
    for line in lines:
        if getattr(line.product, "is_service", False):
            continue
        try:
            record_stock_movement(
                product=line.product,
                movement_type="OUT",
                quantity=line.quantity,
                reference_type="STOCK_ISSUE",
                reference_id=invoice.id,
                partner=invoice.customer,
                movement_date=invoice.invoice_date,
                notes=f"إذن صرف من فاتورة {invoice.invoice_number}",
                tenant=invoice.tenant,
                branch=invoice.branch,
            )
        except Exception as e:
            raise ValidationError(f"خطأ في إذن الصرف لصنف {line.product.sku}: {e}")


def _create_auto_delivery_document(
    invoice: SalesInvoice, lines: list[SalesInvoiceLine],
) -> DeliveryOrder | None:
    """إرسالية تلقائية بكامل الكمية للفاتورة التي تخصم المخزون عند الترحيل.

    توثيق فقط — لا حركة مخزون ولا قيد هنا (الترحيل أنجزهما)، فلا ازدواج.
    """
    goods = [l for l in lines if not getattr(l.product, "is_service", False)]
    if not goods:
        return None
    from django.utils import timezone

    delivery = DeliveryOrder.objects.create(
        tenant=invoice.tenant,
        branch=invoice.branch,
        delivery_number=next_delivery_number(invoice.tenant_id, invoice.branch),
        delivery_date=invoice.invoice_date,
        invoice=invoice,
        auto_created=True,
        status=DeliveryOrder.STATUS_DELIVERED,
        delivered_at=timezone.now(),
        notes="إرسالية تلقائية مع ترحيل الفاتورة",
    )
    for line in goods:
        DeliveryOrderLine.objects.create(
            tenant=invoice.tenant,
            delivery=delivery,
            invoice_line=line,
            product=line.product,
            quantity=line.quantity,
        )
    return delivery


def _resolve_delivery_warehouse(tenant_id: int, raw: dict):
    """مستودع سطر الإرسالية — يُتحقَّق من تبعيته للشركة (مرآة استلام الشراء).

    اختياري خلافاً للشراء: حركة الخروج عند ترحيل الفاتورة بلا مستودع أصلاً، وشركة
    بلا مستودعات يجب أن تبقى قادرة على التسليم. المُرسَل يُعتمد ويُثبَّت على السطر.
    """
    from inventory.models import Warehouse

    wh_id = raw.get("warehouse_id")
    if not wh_id:
        return None
    wh = Warehouse.objects.filter(pk=wh_id, tenant_id=tenant_id).first()
    if wh is None:
        raise ValidationError(f"المستودع المحدد ({wh_id}) غير موجود في هذه الشركة.")
    return wh


def _delivery_movement_type(invoice: SalesInvoice) -> str:
    """اتجاه حركة المخزون عند التسليم — نفس قاعدة الترحيل (نوع الفاتورة يحكمه)."""
    kind = invoice.invoice_kind
    if kind == SalesInvoice.INVOICE_KIND_SALE_RETURN:
        return "RETURN_IN"
    if kind == SalesInvoice.INVOICE_KIND_PURCHASE_RETURN:
        return "RETURN_OUT"
    return "OUT"


def sync_invoice_delivery_status(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine] | None = None,
    *,
    save: bool = True,
) -> str:
    """يشتقّ حالة التسليم من الكميات المسلَّمة — مصدر حقيقة واحد لا حقل يدوي.

    بنود الخدمات لا تُسلَّم مادياً فتُستثنى؛ فاتورة خدمات صرفة تُعدّ مسلَّمة.
    """
    if lines is None:
        lines = list(invoice.lines.select_related("product"))
    goods = [l for l in lines if not getattr(l.product, "is_service", False)]
    if not goods:
        new_status = SalesInvoice.DELIVERY_FULL
    elif all(
        Decimal(str(l.delivered_quantity or 0)) >= Decimal(str(l.quantity or 0))
        for l in goods
    ):
        new_status = SalesInvoice.DELIVERY_FULL
    elif any(Decimal(str(l.delivered_quantity or 0)) > 0 for l in goods):
        new_status = SalesInvoice.DELIVERY_PARTIAL
    else:
        new_status = SalesInvoice.DELIVERY_NOT
    if save and invoice.delivery_status != new_status:
        invoice.delivery_status = new_status
        invoice.save(update_fields=["delivery_status"])
    else:
        invoice.delivery_status = new_status
    return new_status


def next_delivery_number(tenant_id: int, branch=None) -> str:
    """رقم إرسالية البيع التالي — عبر دفاتر الترقيم المركزية (DN-0001)."""
    from accounting.services import next_document_number

    seq = next_document_number(
        tenant_id, "delivery_note", branch_id=branch.id if branch else None,
    )
    return f"DN-{seq:04d}"


def deliver_invoice_lines(
    invoice: SalesInvoice,
    *,
    lines,
    user=None,
    notes: str = "",
    delivery: DeliveryOrder | None = None,
    delivery_date=None,
) -> DeliveryOrder:
    """تسليم بنود فاتورة بيع للعميل (إرسالية) — خصم المخزون وقيد التكلفة للمُسلَّم فقط.

    lines: قائمة [{'line_id': int, 'quantity': Decimal, 'warehouse_id': int|None}].
    الكمية أكبر من المتبقي مرفوضة، فإعادة الإرسال لا تُكرّر الخصم. المستودع
    اختياري ويُثبَّت على الحركة والسطر (مرآة استلام الشراء).

    حصري للفواتير المرحّلة التي **لا** تخصم المخزون عند الترحيل — الفاتورة التي
    تخصمه عند الترحيل سُلّمت بالكامل لحظتها (مرآة استلام فاتورة الشراء).

    العملية ذرّية: حركات المخزون + قيد التكلفة + بنود الإرسالية معاً أو لا شيء.
    """
    if invoice.status != SalesInvoice.STATUS_POSTED:
        raise ValidationError("الفاتورة غير مرحّلة.")
    if invoice.stock_on_post:
        raise ValidationError(
            "هذه الفاتورة تخصم المخزون عند الترحيل — بنودها مسلَّمة بالفعل."
        )
    if not lines:
        raise ValidationError("حدّد البنود والكميات المراد تسليمها.")

    mv_type = _delivery_movement_type(invoice)
    is_return = invoice.invoice_kind in (
        SalesInvoice.INVOICE_KIND_SALE_RETURN,
        SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
    )

    with transaction.atomic():
        inv_lines = list(
            invoice.lines.select_related(
                "product",
                "product__category",
                "product__category__cogs_account",
                "product__category__inventory_account",
            )
        )
        products_by_id = _lock_products_for_lines(inv_lines)
        for line in inv_lines:
            line.product = products_by_id[line.product_id]
        lines_by_id = {l.id: l for l in inv_lines}

        delivered_now: dict[int, Decimal] = {}
        warehouse_by_line: dict[int, object] = {}
        for raw in lines:
            line_id = raw.get("line_id")
            line = lines_by_id.get(int(line_id)) if line_id is not None else None
            if not line:
                raise ValidationError(f"البند {line_id} لا ينتمي لهذه الفاتورة.")
            try:
                qty = Decimal(str(raw.get("quantity", 0)))
            except Exception:
                raise ValidationError(f"كمية غير صالحة للبند «{line.product}».")
            if qty <= 0:
                continue
            if getattr(line.product, "is_service", False):
                raise ValidationError(
                    f"البند «{line.product}» خدمة — لا يُسلَّم من المخزن."
                )
            ordered = Decimal(str(line.quantity or 0))
            already = Decimal(str(line.delivered_quantity or 0))
            remaining = ordered - already
            if qty > remaining:
                raise ValidationError(
                    f"البند «{line.product}»: الكمية المطلوب تسليمها ({qty}) "
                    f"تتجاوز المتبقي ({remaining})."
                )
            delivered_now[line.id] = delivered_now.get(line.id, Decimal("0")) + qty
            # سطر مُرسَل مرتين: الكميات تُجمع والمستودع الأخير المحدَّد هو المعتمد.
            warehouse_by_line[line.id] = (
                _resolve_delivery_warehouse(invoice.tenant_id, raw)
                or warehouse_by_line.get(line.id)
            )

        if not delivered_now:
            raise ValidationError("لا يوجد ما يُسلَّم — تحقق من الكميات.")

        if delivery is None:
            delivery = DeliveryOrder.objects.create(
                tenant=invoice.tenant,
                branch=invoice.branch,
                delivery_number=next_delivery_number(invoice.tenant_id, invoice.branch),
                delivery_date=delivery_date or invoice.invoice_date,
                invoice=invoice,
                notes=(notes or "")[:500],
            )
        elif delivery.status == DeliveryOrder.STATUS_DELIVERED:
            raise ValidationError("تم تسليم هذه الإرسالية مسبقاً.")
        elif not delivery.delivery_number:
            # إرسالية قديمة أُنشئت قبل الترقيم — تُرقَّم عند تسليمها.
            delivery.delivery_number = next_delivery_number(
                invoice.tenant_id, invoice.branch,
            )
            delivery.delivery_date = delivery.delivery_date or invoice.invoice_date
            delivery.save(update_fields=["delivery_number", "delivery_date"])

        for line_id, qty in delivered_now.items():
            line = lines_by_id[line_id]
            warehouse = warehouse_by_line.get(line_id)
            try:
                movement = record_stock_movement(
                    product=line.product,
                    movement_type=mv_type,
                    quantity=qty,
                    reference_type="SALE",
                    reference_id=invoice.id,
                    partner=invoice.customer,
                    movement_date=invoice.invoice_date,
                    notes=(
                        f"تسليم إرسالية {delivery.delivery_number or f'#{delivery.id}'} "
                        f"— فاتورة {invoice.invoice_number}"
                    ),
                    tenant=invoice.tenant,
                    branch=invoice.branch,
                    warehouse=warehouse,
                )
            except ValidationError as e:
                raise ValidationError(f"مخزون الصنف {line.product.sku}: {e}")
            DeliveryOrderLine.objects.create(
                tenant=invoice.tenant,
                delivery=delivery,
                invoice_line=line,
                product=line.product,
                warehouse=warehouse,
                quantity=qty,
                movement=movement,
            )
            line.delivered_quantity = (
                Decimal(str(line.delivered_quantity or 0)) + qty
            )
            line.save(update_fields=["delivered_quantity"])

        # قيد تكلفة المبيعات للكمية المسلَّمة في هذه الإرسالية وحدها.
        cogs_rows = _build_cogs_journal_line_dicts(
            invoice, inv_lines, products_by_id, quantities=delivered_now,
        )
        cogs_journal = None
        if cogs_rows:
            if is_return:
                for row in cogs_rows:
                    row["debit"], row["credit"] = row["credit"], row["debit"]
            cogs_journal = post_journal(
                tenant_id=invoice.tenant_id,
                transaction_date=invoice.invoice_date,
                reference_type="SALES_DELIVERY_COGS",
                reference_id=invoice.id,
                description=(
                    f"تكلفة مبيعات عند التسليم — {invoice.invoice_number} "
                    f"(إرسالية {delivery.delivery_number or f'#{delivery.id}'})"
                )[:500],
                lines_data=cogs_rows,
                currency=invoice.currency,
                exchange_rate=invoice.exchange_rate,
                user=user,
                branch_id=invoice.branch_id,
                # كل إرسالية قيد تكلفة مستقل — بلا هذا يُعاد أول قيد للإرسالية الثانية.
                idempotent=False,
            )

        delivery.status = DeliveryOrder.STATUS_DELIVERED
        from django.utils import timezone

        delivery.delivered_at = timezone.now()
        delivery.journal = cogs_journal
        delivery.save(update_fields=["status", "delivered_at", "journal"])

        sync_invoice_delivery_status(invoice, inv_lines)

        create_audit_log(
            tenant=invoice.tenant,
            user=user,
            action="UPDATE",
            model_name="DeliveryOrder",
            object_id=delivery.id,
            change_details=(
                f"Delivered {len(delivered_now)} line(s) for invoice "
                f"{invoice.invoice_number} → {invoice.delivery_status}"
            ),
        )

    logger.info(
        "Sales invoice #%s delivery #%s: %d line(s), delivery_status=%s",
        invoice.id, delivery.id, len(delivered_now), invoice.delivery_status,
    )
    return delivery


def resolve_goods_delivered_unbilled_account(tenant_id: int) -> Account:
    """حساب «بضاعة مسلَّمة لم تُفوتَر» (كود 1108) — مرآة وسيط الاستلام 2106.

    يستقبل تكلفة البضاعة التي خرجت بسند تسليم مستقل قبل فوترتها، فحين تُفوتَر
    لاحقاً يُدائنه قيدُ تكلفة الفاتورة فيُصفَّر. يُنشأ تلقائياً إن لم يوجد.
    """
    acc = Account.objects.filter(tenant_id=tenant_id, code="1108").first()
    if acc:
        return acc
    parent = Account.objects.filter(tenant_id=tenant_id, code="11").first()
    acc, _ = Account.objects.get_or_create(
        tenant_id=tenant_id,
        code="1108",
        defaults={
            "name": "بضاعة مسلَّمة لم تُفوتَر",
            "account_type": "Asset",
            "parent": parent,
            "is_active": True,
        },
    )
    return acc


def create_standalone_delivery_note(
    tenant, *, partner, lines, branch=None, user=None, delivery_date=None,
    notes="", customer_ref="", delivery=None,
):
    """سند تسليم مستقل — بضاعة خرجت قبل فوترتها (مرآة سند الاستلام).

    lines: [{'product_id': int, 'quantity': Decimal, 'warehouse_id': int|None}]
    القيد: مدين «بضاعة مسلَّمة لم تُفوتَر» (1108) / دائن المخزون بمتوسط التكلفة —
    لا إيراد هنا، الإيراد يأتي مع الفاتورة لاحقاً.
    """
    import datetime
    from django.utils import timezone

    if not lines:
        raise ValidationError("حدّد الأصناف والكميات المسلَّمة.")
    if partner is None:
        raise ValidationError("حدّد العميل لسند التسليم المستقل.")

    movement_date = delivery_date or timezone.localdate()
    tenant_id = getattr(tenant, "TenantID", tenant)
    products = {
        p.id: p
        for p in Product.objects.select_for_update()
        .select_related("category", "category__inventory_account")
        .filter(
            tenant_id=tenant_id,
            pk__in=[row.get("product_id") for row in lines if row.get("product_id")],
        )
    }

    planned = []
    for raw in lines:
        product = products.get(int(raw.get("product_id") or 0))
        if product is None:
            raise ValidationError(f"الصنف {raw.get('product_id')} غير موجود في هذه الشركة.")
        if getattr(product, "is_service", False):
            raise ValidationError(f"الصنف «{product}» خدمة — لا يُسلَّم من المخزن.")
        try:
            qty = Decimal(str(raw.get("quantity", 0)))
        except Exception:
            raise ValidationError(f"كمية غير صالحة للصنف «{product}».")
        if qty <= 0:
            continue
        planned.append({
            "product": product,
            "qty": qty,
            "cost": (qty * Decimal(str(product.avg_cost or 0))).quantize(DEC),
            "warehouse": _resolve_delivery_warehouse(tenant_id, raw),
        })

    if not planned:
        raise ValidationError("لا يوجد ما يُسلَّم — تحقق من الكميات.")

    total_cost = sum((p["cost"] for p in planned), Decimal("0"))

    with transaction.atomic():
        doc = delivery
        if doc is None:
            doc = DeliveryOrder.objects.create(
                tenant=tenant,
                branch=branch,
                delivery_number=next_delivery_number(tenant_id, branch),
                delivery_date=movement_date,
                invoice=None,
                partner=partner,
                customer_ref=(customer_ref or "")[:100],
                status=DeliveryOrder.STATUS_DELIVERED,
                delivered_at=timezone.now(),
                notes=(notes or "")[:500],
            )
        else:
            doc.lines.all().delete()
            doc.delivery_date = movement_date
            doc.partner = partner
            doc.customer_ref = (customer_ref or "")[:100]
            doc.notes = (notes or "")[:500]
            doc.save(update_fields=[
                "delivery_date", "partner", "customer_ref", "notes",
            ])

        for p in planned:
            try:
                movement = record_stock_movement(
                    product=p["product"],
                    movement_type="OUT",
                    quantity=p["qty"],
                    reference_type="DELIVERY_NOTE",
                    reference_id=doc.id,
                    partner=partner,
                    movement_date=movement_date,
                    notes=f"سند تسليم {doc.delivery_number}",
                    tenant=tenant,
                    branch=branch,
                    warehouse=p["warehouse"],
                )
            except ValidationError as e:
                raise ValidationError(f"مخزون الصنف {p['product'].sku}: {e}")
            DeliveryOrderLine.objects.create(
                tenant=tenant,
                delivery=doc,
                invoice_line=None,
                product=p["product"],
                warehouse=p["warehouse"],
                quantity=p["qty"],
                movement=movement,
            )

        journal = None
        if total_cost > 0:
            ss = get_or_create_sales_settings(tenant_id)
            clearing = resolve_goods_delivered_unbilled_account(tenant_id)
            rows = []
            for p in planned:
                if p["cost"] <= 0:
                    continue
                cat = p["product"].category
                inv_id = (
                    cat.inventory_account_id
                    if cat and cat.inventory_account_id
                    else ss.default_inventory_account_id
                )
                if not inv_id:
                    raise ValidationError(
                        f"الصنف «{p['product']}»: عيّن حساب المخزون في فئة المنتج "
                        "أو حساباً افتراضياً في إعدادات المبيعات."
                    )
                rows.append({
                    "account": inv_id, "partner": None,
                    "debit": Decimal("0"), "credit": p["cost"],
                    "description": f"تخفيض مخزون — سند تسليم {doc.delivery_number}"[:500],
                })
            rows.insert(0, {
                "account": clearing.id, "partner": None,
                "debit": total_cost, "credit": Decimal("0"),
                "description": f"بضاعة مسلَّمة لم تُفوتَر — {doc.delivery_number}"[:500],
            })
            journal = post_journal(
                tenant_id=tenant_id,
                transaction_date=movement_date,
                reference_type="DELIVERY_NOTE",
                reference_id=doc.id,
                description=f"سند تسليم {doc.delivery_number} | {partner.name}"[:500],
                lines_data=rows,
                user=user,
                branch_id=branch.id if branch else None,
                idempotent=False,
            )
            doc.journal = journal
            doc.save(update_fields=["journal"])

    logger.info(
        "Standalone delivery note %s: %d line(s), cost=%s, journal=%s",
        doc.delivery_number, len(planned), total_cost, journal.id if journal else None,
    )
    return doc


def void_delivery_note(delivery: DeliveryOrder, *, user=None) -> dict:
    """يعكس أثر إرسالية بيع واحدة: حركاتها وقيدها وكمياتها المسلَّمة — دون غيرها.

    التتبّع عبر `DeliveryOrderLine.movement`، فلا تُمسّ إرساليات أخرى لنفس الفاتورة.
    """
    from accounting.models import JournalHeader
    from inventory.services import _recompute_product_stock

    with transaction.atomic():
        lines = list(delivery.lines.select_related("invoice_line", "product", "movement"))
        movement_ids = [l.movement_id for l in lines if l.movement_id]
        products = {l.product_id: l.product for l in lines if l.product_id}

        if movement_ids:
            StockMovement.objects.filter(pk__in=movement_ids).delete()
        if delivery.journal_id:
            JournalHeader.objects.filter(pk=delivery.journal_id).delete()

        invoice = delivery.invoice
        if invoice is not None:
            for line in lines:
                if line.invoice_line_id is None:
                    continue
                inv_line = line.invoice_line
                inv_line.delivered_quantity = max(
                    Decimal("0"),
                    Decimal(str(inv_line.delivered_quantity or 0))
                    - Decimal(str(line.quantity or 0)),
                )
                inv_line.save(update_fields=["delivered_quantity"])

        number = delivery.delivery_number or f"#{delivery.id}"
        delivery.delete()

        for product in products.values():
            _recompute_product_stock(product)

        if invoice is not None:
            sync_invoice_delivery_status(invoice)

    logger.info(
        "Delivery note %s voided: %d movement(s) reversed", number, len(movement_ids),
    )
    return {"movements_reversed": len(movement_ids)}


def remaining_delivery_lines(invoice: SalesInvoice) -> list[dict]:
    """بنود الفاتورة مع (المفوتر · المسلَّم · المتبقي) — يغذّي نافذة التسليم.

    مصدر حقيقة واحد مع حارس التسليم، فلا تعرض الواجهة ما يرفضه الخادم.
    """
    rows: list[dict] = []
    for line in invoice.lines.select_related("product"):
        if getattr(line.product, "is_service", False):
            continue
        ordered = Decimal(str(line.quantity or 0))
        delivered = Decimal(str(line.delivered_quantity or 0))
        rows.append({
            "line_id": line.id,
            "product": line.product_id,
            "product_name": str(line.product),
            "quantity": ordered,
            "delivered_quantity": delivered,
            "remaining_quantity": max(Decimal("0"), ordered - delivered),
        })
    return rows


def deliver_delivery_order(delivery: DeliveryOrder, *, user=None) -> DeliveryOrder:
    """تسليم إرسالية قائمة بكامل المتبقي من بنود فاتورتها (المسار القديم).

    يُفوِّض لـ`deliver_invoice_lines` كي لا يوجد منطق تسليم مكرّر.
    """
    inv = delivery.invoice
    if delivery.status == DeliveryOrder.STATUS_DELIVERED:
        raise ValidationError("تم التسليم مسبقاً.")
    lines = [
        {"line_id": r["line_id"], "quantity": r["remaining_quantity"]}
        for r in remaining_delivery_lines(inv)
        if r["remaining_quantity"] > 0
    ]
    return deliver_invoice_lines(inv, lines=lines, user=user, delivery=delivery)


def _resolve_ar_account_for_partner(partner: Partner) -> Account:
    # T-DEFACC: نفس ترتيب `_resolve_ar_account` — حساب الزبون قبل أب المجموعة.
    partner = ensure_partner_account(partner) or partner
    if partner.linked_account_id:
        return partner.linked_account
    if partner.group_id:
        g = PartnerGroup.objects.filter(pk=partner.group_id).first()
        if g and g.account_receivable_id:
            return g.account_receivable
    # Fallback to sales settings (matches _resolve_ar_account)
    ss = SalesSettings.objects.filter(tenant_id=partner.tenant_id).first()
    if ss and ss.default_ar_account_id:
        return ss.default_ar_account
    raise ValidationError("لا يوجد حساب ذمم للعميل.")


def post_customer_payment(payment: CustomerPayment, *, user=None) -> CustomerPayment:
    """ترحيل دفعة عميل مع دعم كامل لتعدد العملات.

    إذا كانت عملة الدفعة مختلفة عن عملة الفاتورة:
    - يتم تحويل مبلغ التوزيع لعملة الفاتورة باستخدام سعر الصرف
    - يُحدَّث amount_paid بالمبلغ المحوّل (بعملة الفاتورة)
    - يُسجَّل فرق العملة (forex gain/loss) إذا وُجد
    """
    if payment.is_posted:
        raise ValidationError("الدفعة مرحّلة مسبقاً.")

    if payment.partner.tenant_id != payment.tenant_id:
        raise ValidationError("العميل لا يتبع نفس الشركة.")

    validate_fiscal_period(payment.tenant_id, payment.payment_date)

    allocated = (
        PaymentAllocation.objects.filter(payment=payment).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    # T-ONACC: التوزيع اختياري — ما لم يُوزَّع يُرحَّل «على الحساب» (Dr صندوق /
    # Cr ذمم العميل) فيؤثّر على كشف حسابه بلا تسديد أي فاتورة، ويُوزَّع لاحقاً
    # عبر allocate_customer_payment. الممنوع فقط: توزيع يتجاوز مبلغ الدفعة.
    if allocated > payment.amount + DEC:
        raise ValidationError("مجموع التوزيعات لا يجوز أن يتجاوز مبلغ الدفعة.")

    # ── التحقق من التوزيعات + تحويل العملات مسبقاً ──
    payment_currency_id = payment.currency_id
    alloc_conversions: list[tuple[PaymentAllocation, Decimal, Decimal]] = []

    for alloc in payment.allocations.select_related("invoice", "invoice__currency"):
        if alloc.invoice.customer_id != payment.partner_id:
            raise ValidationError("توزيع الدفعة على فاتورة لا تخص نفس العميل.")
        if alloc.invoice.status != SalesInvoice.STATUS_POSTED:
            raise ValidationError(f"الفاتورة #{alloc.invoice.invoice_number} غير مرحّلة.")

        inv = alloc.invoice
        inv_currency_id = inv.currency_id

        # ── تحويل مبلغ التوزيع من عملة الدفعة إلى عملة الفاتورة ──
        if payment_currency_id == inv_currency_id:
            # نفس العملة — لا تحويل
            amount_in_inv_curr = Decimal(str(alloc.amount))
            conv_rate = Decimal("1")
        else:
            amount_in_inv_curr, conv_rate = convert_amount(
                amount=Decimal(str(alloc.amount)),
                from_currency_id=payment_currency_id,
                to_currency_id=inv_currency_id,
                tenant_id=payment.tenant_id,
                effective_date=payment.payment_date,
            )

        # ملاحظة: التحقق من تجاوز المتبقي يتم لاحقاً تحت قفل select_for_update
        # داخل transaction.atomic() لمنع سباق lost-update / الدفع الزائد.
        alloc_conversions.append((alloc, amount_in_inv_curr, conv_rate))

    ar = _resolve_ar_account_for_partner(payment.partner)

    # ── شيكات داخل السند ─────────────────────────────────────────────────
    # مبلغ السند = نقد + شيكات. الجزء المُغطّى بشيكات لا يدخل الصندوق بل
    # «شيكات برسم التحصيل» حتى تُحصَّل. الاستهلاك بالترتيب على قيود السند
    # (قيد لكل فاتورة ثم قيد «على الحساب») كي يبقى كل قيد متوازناً وحده.
    payment_cheques = list(payment.cheques.all()) if payment.pk else []
    cheques_pool = sum(
        (Decimal(str(c.amount or 0)) for c in payment_cheques), Decimal("0")
    ).quantize(DEC)
    if cheques_pool > Decimal(str(payment.amount)) + DEC:
        raise ValidationError(
            f"مجموع الشيكات ({cheques_pool}) يتجاوز مبلغ السند ({payment.amount})."
        )
    uc_account = (
        resolve_cheques_under_collection_account(payment.tenant_id)
        if cheques_pool > 0 else None
    )

    def _debit_lines(amount: Decimal, description: str) -> list[dict]:
        """يقسم الجانب المدين بين الصندوق والشيكات برسم التحصيل."""
        nonlocal cheques_pool
        from_cheques = min(cheques_pool, amount).quantize(DEC)
        cheques_pool = (cheques_pool - from_cheques).quantize(DEC)
        cash_part = (amount - from_cheques).quantize(DEC)
        rows: list[dict] = []
        if cash_part > 0:
            rows.append({
                # T-CASH2: سطر الصندوق لا يَحمل الشريك (لا يُحسب على ذمم العميل).
                "account": payment.cash_or_bank_account_id,
                "partner": None,
                "debit": cash_part,
                "credit": Decimal("0"),
                "description": description,
            })
        if from_cheques > 0:
            rows.append({
                # شيكات برسم التحصيل أصل لا حساب رقابي للذمم — بلا شريك.
                "account": uc_account.id,
                "partner": None,
                "debit": from_cheques,
                "credit": Decimal("0"),
                "description": f"شيكات — {description}",
            })
        return rows

    with transaction.atomic():
        # T-SPLIT: قفل صفّ الدفعة وإعادة فحص الترحيل — إذ نُنشئ قيداً لكل فاتورة
        # بـ idempotent=False (نفس reference_id)، فلا يحمينا فحص post_journal من
        # ترحيل مزدوج متزامن؛ القفل هنا يُسلسِل الطلبات ويمنع تكرار القيود.
        payment = CustomerPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.is_posted:
            raise ValidationError("الدفعة مرحّلة مسبقاً.")

        # قفل الفواتير (select_for_update) ومادّتها فعلياً في dict لمنع
        # سباق lost-update على amount_paid. لا بد من تقييم الـ queryset
        # (التكرار) حتى يصدر SELECT ... FOR UPDATE فعلياً.
        inv_ids = sorted({alloc.invoice_id for alloc, _amt, _rate in alloc_conversions})
        locked_invoices = {
            inv.pk: inv
            for inv in SalesInvoice.objects.select_for_update().filter(pk__in=inv_ids)
        }

        # إجمالي الزيادة لكل فاتورة (قد تتعدّد التوزيعات على نفس الفاتورة)
        increment_by_invoice: dict[int, Decimal] = {}
        for alloc, amount_in_inv_curr, _conv in alloc_conversions:
            increment_by_invoice[alloc.invoice_id] = (
                increment_by_invoice.get(alloc.invoice_id, Decimal("0"))
                + amount_in_inv_curr
            )

        # إعادة التحقق من تجاوز المتبقي على الصفوف المقفلة (القراءة الحديثة)
        for inv_id, total_increment in increment_by_invoice.items():
            inv = locked_invoices[inv_id]
            remaining = inv.grand_total - Decimal(str(inv.amount_paid))
            if total_increment > remaining + DEC:
                raise ValidationError(
                    f"مبلغ التوزيع المحوّل ({total_increment} بعملة الفاتورة) "
                    f"يتجاوز المتبقي على الفاتورة #{inv.invoice_number} ({remaining})."
                )
            # T-ARINT: حارس ثانٍ مستقلّ عن amount_paid (يُصفَّر من الخارج) —
            # مجموع توزيعات السندات المرحّلة نفسه لا يتجاوز إجمالي الفاتورة.
            guard_invoice_allocation_total(inv, incoming=total_increment)

        # ── بناء أسطر القيد المحاسبي ──
        # فرق العملة (I4-03): إذا اختلفت عملة الدفعة عن عملة الفاتورة نحسب
        # المبلغ المعادل بعملة الدفعة ونضبط سطر الذمم + نضيف سطر فروقات عملة.
        # هذا يضمن توازن القيد دائماً:
        #   Dr صندوق/بنك  = payment.amount
        #   Cr ذمم مدينة  = payment.amount - forex_diff  (إن كان ربح) أو payment.amount + abs(forex_diff) (إن كان خسارة)
        #   Cr/Dr فروقات عملة = |forex_diff|
        # المجموع: Dr = Cr = payment.amount (ربح) أو payment.amount + abs(loss) (خسارة)

        total_alloc_in_inv_curr = sum(
            (amt for _alloc, amt, _rate in alloc_conversions), Decimal("0")
        )
        # T-SPLIT: قيد مستقل لكل فاتورة. سند القبض الواحد يُنتج قيداً منفصلاً لكل
        # فاتورة سُدِّدت (Dr صندوق / Cr ذمم العميل [+ فرق عملة إن لزم]) فتظهر كل
        # فاتورة كحركة/قيد مستقل في كشف الحساب ودفتر اليومية. كل القيود بنفس
        # reference_type/reference_id فيُصفّرها التراجع (unpost_document) دفعةً واحدة.
        # لكل فاتورة: cash = ما دُفع فعلاً بعملة الدفعة (مجموعه = مبلغ الدفعة)، و
        # ar = ما يُسدَّد من الذمم (قيمة الفاتورة محوّلة لعملة الدفعة)؛ فرقهما = فرق عملة.
        cash_by_invoice: dict[int, Decimal] = {}
        ar_by_invoice: dict[int, Decimal] = {}
        invoice_order: list[int] = []
        for alloc, amount_in_inv_curr, _rate in alloc_conversions:
            inv_curr_id = alloc.invoice.currency_id
            if payment_currency_id and inv_curr_id and inv_curr_id != payment_currency_id:
                # P-H-8: كل توزيع يُحوَّل من عملة فاتورته إلى عملة الدفعة على حدة.
                ar_amt, _ = convert_amount(
                    amount=amount_in_inv_curr,
                    from_currency_id=inv_curr_id,
                    to_currency_id=payment_currency_id,
                    tenant_id=payment.tenant_id,
                    effective_date=payment.payment_date,
                )
            else:
                ar_amt = Decimal(str(alloc.amount))  # نفس العملة — لا فرق صرف
            if alloc.invoice_id not in cash_by_invoice:
                invoice_order.append(alloc.invoice_id)
                cash_by_invoice[alloc.invoice_id] = Decimal("0")
                ar_by_invoice[alloc.invoice_id] = Decimal("0")
            cash_by_invoice[alloc.invoice_id] += Decimal(str(alloc.amount))
            ar_by_invoice[alloc.invoice_id] += ar_amt

        # حساب فروقات العملة يُطلب مرّة واحدة إن اختلف الصندوق عن تسديد الذمم لأي فاتورة.
        forex_acc = None
        if any(
            abs(cash_by_invoice[i] - ar_by_invoice[i]).quantize(DEC) > DEC
            for i in invoice_order
        ):
            forex_acc = resolve_forex_account(payment.tenant_id)
            if not forex_acc:
                raise ValidationError(
                    "فرق عملة مكتشف لكن لا يوجد حساب فروقات عملة. "
                    "أنشئ حساباً باسم 'فرق عمل' من نوع Expense أو Revenue."
                )

        journals = []
        for inv_id in invoice_order:
            inv = locked_invoices[inv_id]
            cash_amt = cash_by_invoice[inv_id].quantize(DEC)
            ar_amt = ar_by_invoice[inv_id].quantize(DEC)
            forex_diff = (cash_amt - ar_amt).quantize(DEC)  # >0 ربح، <0 خسارة
            inv_lines: list[dict] = _debit_lines(
                cash_amt, f"تحصيل عميل — فاتورة {inv.invoice_number}"
            )
            if forex_acc and abs(forex_diff) > DEC:
                # الذمم تُسدَّد بقيمة الفاتورة المحوّلة، والفرق لحساب فروقات العملة.
                inv_lines.append({
                    "account": ar.id,
                    "partner": payment.partner_id,
                    "debit": Decimal("0"),
                    "credit": ar_amt,
                    "description": f"تسديد ذمم — فاتورة {inv.invoice_number}",
                })
                if forex_diff > 0:
                    inv_lines.append({
                        "account": forex_acc.id, "partner": None,
                        "debit": Decimal("0"), "credit": forex_diff,
                        "description": f"ربح فروق عملة — فاتورة {inv.invoice_number}",
                    })
                else:
                    inv_lines.append({
                        "account": forex_acc.id, "partner": None,
                        "debit": abs(forex_diff), "credit": Decimal("0"),
                        "description": f"خسارة فروق عملة — فاتورة {inv.invoice_number}",
                    })
            else:
                # نفس العملة (الشائع) — الذمم تُسدَّد بمبلغ الصندوق تماماً.
                inv_lines.append({
                    "account": ar.id,
                    "partner": payment.partner_id,
                    "debit": Decimal("0"),
                    "credit": cash_amt,
                    "description": f"تسديد ذمم — فاتورة {inv.invoice_number}",
                })
            jh = post_journal(
                tenant_id=payment.tenant_id,
                transaction_date=payment.payment_date,
                reference_type="CUSTOMER_PAYMENT",
                reference_id=payment.id,
                description=(
                    (payment.notes or f"تحصيل عميل {payment.partner.name}")
                    + f" — فاتورة {inv.invoice_number}"
                )[:500],
                lines_data=inv_lines,
                currency=payment.currency,
                exchange_rate=payment.exchange_rate,
                user=user,
                idempotent=False,  # قيد مستقل لكل فاتورة رغم وحدة reference_id
            )
            journals.append(jh)

        # T-ONACC: الجزء غير الموزَّع (أو كامل المبلغ حين لا توزيع) يُرحَّل بقيد
        # واحد «على الحساب»: Dr صندوق / Cr ذمم العميل — يظهر في كشف الحساب
        # كرصيد لصالح العميل ويُوزَّع على الفواتير لاحقاً بلا قيد إضافي.
        unallocated = (Decimal(str(payment.amount)) - allocated).quantize(DEC)
        if unallocated >= DEC:
            jh = post_journal(
                tenant_id=payment.tenant_id,
                transaction_date=payment.payment_date,
                reference_type="CUSTOMER_PAYMENT",
                reference_id=payment.id,
                description=(
                    (payment.notes or f"تحصيل عميل {payment.partner.name}")
                    + " — على الحساب"
                )[:500],
                lines_data=[
                    *_debit_lines(
                        unallocated, f"تحصيل على الحساب — {payment.partner.name}"
                    ),
                    {
                        "account": ar.id,
                        "partner": payment.partner_id,
                        "debit": Decimal("0"),
                        "credit": unallocated,
                        "description": f"دفعة على الحساب — {payment.partner.name}",
                    },
                ],
                currency=payment.currency,
                exchange_rate=payment.exchange_rate,
                user=user,
                idempotent=False,
            )
            journals.append(jh)
            logger.info(
                "Payment %s posted on-account remainder %s (allocated=%s of %s)",
                payment.id, unallocated, allocated, payment.amount,
            )

        # payment.journal حقل مفرد — نخزّن أول قيد للمرجعية؛ التراجع يعتمد
        # reference_id فيشمل كل القيود.
        payment.journal = journals[0] if journals else None
        payment.is_posted = True
        payment.save(update_fields=["journal", "is_posted"])

        # شيكات السند تنتقل من مسودة إلى «برسم التحصيل» بترحيله (كما في الفاتورة).
        if payment_cheques:
            from accounting.models import Cheque
            Cheque.objects.filter(
                customer_payment=payment, status="Draft"
            ).update(status="Under_Collection")

        # ── حفظ مبلغ/سعر تحويل كل توزيع للمرجعية ──
        for alloc, amount_in_inv_curr, conv_rate in alloc_conversions:
            alloc.amount_in_invoice_currency = amount_in_inv_curr
            alloc.conversion_rate = conv_rate
            alloc.save(update_fields=["amount_in_invoice_currency", "conversion_rate"])
            logger.info(
                "Payment %s alloc → invoice %s: %s (pay currency) → %s (inv currency) @ rate %s",
                payment.id, locked_invoices[alloc.invoice_id].invoice_number,
                alloc.amount, amount_in_inv_curr, conv_rate,
            )

        # ── تحديث amount_paid على الصفوف المقفلة (مرّة واحدة لكل فاتورة) ──
        for inv_id, total_increment in increment_by_invoice.items():
            inv = locked_invoices[inv_id]
            inv.amount_paid = Decimal(str(inv.amount_paid)) + total_increment
            inv.save(update_fields=["amount_paid"])

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="POST",
            model_name="CustomerPayment",
            object_id=payment.id,
            change_details=(
                f"Customer payment posted journal={payment.journal_id} "
                f"currency={payment.currency_id} amount={payment.amount} "
                f"allocated={allocated}"
            ),
        )

    return payment


def allocate_customer_payment(
    payment: CustomerPayment, allocations: list[dict], *, user=None
) -> CustomerPayment:
    """T-ONACC: توزيع سند قبض (كامله أو جزء منه) على فواتير — بعد الترحيل أو قبله.

    قرار المالك: التوزيع اللاحق **ربط فقط بلا قيد جديد** — لأن ترحيل السند خفّض
    ذمم العميل أصلاً (على الحساب)، فالتوزيع لا يغيّر أي رصيد دفتري؛ يُحدِّث
    `amount_paid` على الفاتورة ويربط السند بها فقط. إن لم يكن السند مرحّلاً بعد
    فالصفوف تُنشأ فحسب ويتولّى `post_customer_payment` القيود و`amount_paid`.

    allocations: [{"invoice": <id>, "amount": <Decimal|str>}, ...]
    """
    rows = [
        (int(a["invoice"]), Decimal(str(a.get("amount") or "0")))
        for a in (allocations or [])
    ]
    if not rows:
        raise ValidationError("لا توزيعات مُرسَلة.")
    if any(amt <= 0 for _inv_id, amt in rows):
        raise ValidationError("مبلغ التوزيع يجب أن يكون أكبر من صفر.")

    with transaction.atomic():
        payment = CustomerPayment.objects.select_for_update().get(pk=payment.pk)
        already = (
            PaymentAllocation.objects.filter(payment=payment).aggregate(t=Sum("amount"))["t"]
            or Decimal("0")
        )
        total_new = sum((amt for _inv_id, amt in rows), Decimal("0"))
        if already + total_new > Decimal(str(payment.amount)) + DEC:
            raise ValidationError(
                f"مجموع التوزيعات ({already + total_new}) يتجاوز مبلغ السند "
                f"({payment.amount}). المتاح للتوزيع: {Decimal(str(payment.amount)) - already}."
            )

        invoices = {
            inv.pk: inv
            for inv in SalesInvoice.objects.select_for_update().filter(
                pk__in={inv_id for inv_id, _amt in rows}, tenant_id=payment.tenant_id
            )
        }
        for inv_id, amt in rows:
            inv = invoices.get(inv_id)
            if inv is None:
                raise ValidationError(f"الفاتورة #{inv_id} غير موجودة في هذه الشركة.")
            if inv.customer_id != payment.partner_id:
                raise ValidationError(
                    f"الفاتورة #{inv.invoice_number} لا تخص نفس العميل."
                )
            if inv.status != SalesInvoice.STATUS_POSTED:
                raise ValidationError(f"الفاتورة #{inv.invoice_number} غير مرحّلة.")

            if payment.currency_id == inv.currency_id:
                amount_in_inv_curr, conv_rate = amt, Decimal("1")
            else:
                amount_in_inv_curr, conv_rate = convert_amount(
                    amount=amt,
                    from_currency_id=payment.currency_id,
                    to_currency_id=inv.currency_id,
                    tenant_id=payment.tenant_id,
                    effective_date=payment.payment_date,
                )
            remaining = inv.grand_total - Decimal(str(inv.amount_paid))
            if amount_in_inv_curr > remaining + DEC:
                raise ValidationError(
                    f"مبلغ التوزيع ({amount_in_inv_curr}) يتجاوز المتبقي على "
                    f"الفاتورة #{inv.invoice_number} ({remaining})."
                )
            # T-ARINT: نفس الحارس المستقلّ عن amount_paid المطبَّق في الترحيل.
            # قبل ترحيل السند لا يُحتسب توزيعه بعد — يحرسه `post_customer_payment`.
            if payment.is_posted:
                guard_invoice_allocation_total(inv, incoming=amount_in_inv_curr)

            PaymentAllocation.objects.create(
                tenant_id=payment.tenant_id,
                payment=payment,
                invoice=inv,
                amount=amt,
                amount_in_invoice_currency=amount_in_inv_curr,
                conversion_rate=conv_rate,
            )
            if payment.is_posted:
                inv.amount_paid = Decimal(str(inv.amount_paid)) + amount_in_inv_curr
                inv.save(update_fields=["amount_paid"])
            logger.info(
                "Payment %s allocated %s → invoice %s (posted=%s)",
                payment.id, amt, inv.invoice_number, payment.is_posted,
            )

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="ALLOCATE",
            model_name="CustomerPayment",
            object_id=payment.id,
            change_details=(
                f"Allocated {total_new} to {len(rows)} invoice(s); "
                f"total allocated={already + total_new} of {payment.amount}"
            ),
        )

    return payment


def credit_preview_for_sale(
    *,
    tenant_id: int,
    partner_id: int,
    proposed_total: Decimal,
    exclude_invoice_id: int | None = None,
) -> dict:
    """معاينة حد الائتمان قبل الترحيل (وللمسودة من الواجهة)."""
    partner = Partner.objects.filter(pk=partner_id, tenant_id=tenant_id).first()
    if not partner:
        raise ValidationError("عميل غير موجود.")
    open_bal = _partner_open_balance_excluding_invoice(partner, exclude_invoice_id)
    prop = Decimal(str(proposed_total)).quantize(DEC)
    limit = partner.credit_limit
    projected = open_bal + prop
    would_exceed = limit is not None and projected > Decimal(str(limit)) + DEC
    return {
        "credit_limit": str(limit) if limit is not None else None,
        "open_balance": str(open_bal),
        "proposed_total": str(prop),
        "projected_balance": str(projected),
        "would_exceed": would_exceed,
    }


