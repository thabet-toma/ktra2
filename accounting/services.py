import datetime
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Account, ExchangeRate, JournalHeader, JournalLine, AccountingAuditLog, FiscalPeriod, CostCenter, VoidedJournal
from decimal import Decimal
from partners.models import Partner
from tenants.models import Currency, TenantBook

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  N0-T3: Document Numbering (Canonical)
# ─────────────────────────────────────────────────────────

def next_document_number(
    tenant_id: int,
    document_type: str,
    book_number: int = 0,
    branch_id: int | None = None,
) -> int:
    """يُولّد الرقم التالي لمستند معين عبر TenantBook مع select_for_update.

    هذا هو الـ canonical helper — كل الـ helpers الأخرى (next_invoice_number إلخ)
    تصبح thin wrappers تُمرّر له.

    Args:
        tenant_id: معرف الشركة
        document_type: نوع المستند (sales_invoice, purchase_invoice, deal, ...)
        book_number: رقم الدفتر (0 = الافتراضي)

    Returns:
        الرقم التالي (last_used_number + 1)
    """
    with transaction.atomic():
        book, created = TenantBook.objects.select_for_update().get_or_create(
            tenant_id=tenant_id,
            branch_id=branch_id,
            document_type=document_type,
            book_number=book_number,
            defaults={
                'name': f'{document_type} [{book_number}]',
                'last_used_number': 0,
                'is_active': True,
            },
        )
        if not book.is_active:
            raise ValidationError(f"الدفتر {book_number} لنوع {document_type} غير نشط.")
        next_num = book.last_used_number + 1
        book.last_used_number = next_num
        book.save(update_fields=['last_used_number'])
        return next_num


# ── N8-T5: Thin wrappers للـDeal/Shipment/Clearance ────────────

def next_deal_number(tenant_id: int, book_number: int = 0) -> int:
    return next_document_number(tenant_id, 'deal', book_number=book_number)


def next_shipment_number(tenant_id: int, book_number: int = 0) -> int:
    return next_document_number(tenant_id, 'shipment', book_number=book_number)


def next_clearance_number(tenant_id: int, book_number: int = 0) -> int:
    return next_document_number(tenant_id, 'clearance', book_number=book_number)


# ─────────────────────────────────────────────────────────
#  Currency Conversion Utilities
# ─────────────────────────────────────────────────────────

def get_exchange_rate(
    tenant_id: int,
    from_currency_id: int,
    to_currency_id: int,
    effective_date=None,
) -> Decimal:
    """
    يجلب سعر الصرف من جدول exchange_rates.
    يبحث عن أحدث سعر صرف بتاريخ <= effective_date.
    إذا لم يجد يبحث بالعكس (to→from) ويقلبه.
    يرمي ValidationError إذا لم يجد أي سعر.
    """
    if from_currency_id == to_currency_id:
        return Decimal("1")

    if effective_date is None:
        effective_date = datetime.date.today()
    if isinstance(effective_date, str):
        effective_date = datetime.datetime.strptime(effective_date, "%Y-%m-%d").date()

    # بحث مباشر: from → to
    direct = (
        ExchangeRate.objects.filter(
            tenant_id=tenant_id,
            from_currency_id=from_currency_id,
            to_currency_id=to_currency_id,
            effective_date__lte=effective_date,
        )
        .order_by("-effective_date")
        .values_list("rate", flat=True)
        .first()
    )
    if direct is not None:
        return Decimal(str(direct))

    # بحث عكسي: to → from ثم القلب
    inverse = (
        ExchangeRate.objects.filter(
            tenant_id=tenant_id,
            from_currency_id=to_currency_id,
            to_currency_id=from_currency_id,
            effective_date__lte=effective_date,
        )
        .order_by("-effective_date")
        .values_list("rate", flat=True)
        .first()
    )
    if inverse is not None and Decimal(str(inverse)) != 0:
        return (Decimal("1") / Decimal(str(inverse))).quantize(Decimal("0.000001"))

    raise ValidationError(
        f"لا يوجد سعر صرف مسجّل للتحويل من العملة {from_currency_id} "
        f"إلى العملة {to_currency_id} بتاريخ {effective_date} أو قبله. "
        f"سجّل سعر الصرف في جدول أسعار الصرف أولاً."
    )


def convert_amount(
    amount: Decimal,
    from_currency_id: int,
    to_currency_id: int,
    tenant_id: int,
    effective_date=None,
    explicit_rate: Decimal | None = None,
) -> tuple[Decimal, Decimal]:
    """
    يحوّل مبلغاً من عملة إلى عملة أخرى.
    
    Parameters:
        amount: المبلغ بالعملة المصدر
        from_currency_id: عملة المصدر
        to_currency_id: عملة الهدف
        tenant_id: الشركة
        effective_date: تاريخ السعر
        explicit_rate: سعر صرف صريح (لو المستخدم حدده)
        
    Returns:
        (converted_amount, rate_used)
    """
    if from_currency_id == to_currency_id:
        return amount, Decimal("1")

    if explicit_rate is not None and explicit_rate > 0:
        rate = Decimal(str(explicit_rate))
    else:
        rate = get_exchange_rate(tenant_id, from_currency_id, to_currency_id, effective_date)

    converted = (Decimal(str(amount)) * rate).quantize(Decimal("0.01"))
    return converted, rate


def resolve_forex_account(tenant_id: int) -> Account | None:
    """
    يبحث عن حساب فروقات العملة (Forex Gain/Loss).
    يبحث عن حساب باسم يحتوي 'فرق عمل' أو 'forex' أو 'exchange' ضمن Expense أو Revenue.
    """
    keywords = ["فرق عمل", "فروق عمل", "forex", "exchange diff", "exchange gain"]
    for kw in keywords:
        acc = Account.objects.filter(
            tenant_id=tenant_id,
            is_active=True,
            name__icontains=kw,
        ).first()
        if acc:
            return acc
    return None


def validate_fiscal_period(tenant_id, transaction_date):
    """
    Ensures transaction_date falls within an open fiscal period.
    Raises ValidationError if tenant is missing, date is invalid, or period is closed.
    """
    if tenant_id in (0, None):
        raise ValidationError("لا يمكن التحقق من الفترة المالية: معرف الشركة (tenant_id) غير صالح.")

    if isinstance(transaction_date, str):
        try:
            transaction_date = datetime.datetime.strptime(transaction_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            raise ValidationError(f"تاريخ غير صالح: {transaction_date}. يجب أن يكون بصيغة YYYY-MM-DD.")

    if not isinstance(transaction_date, datetime.date):
        raise ValidationError("تاريخ المعاملة غير صالح.")

    period = FiscalPeriod.objects.filter(
        tenant_id=tenant_id,
        start_date__lte=transaction_date,
        end_date__gte=transaction_date,
        status='Open',
        is_closed=False,
    ).first()

    if period:
        return period

    existing_closed = FiscalPeriod.objects.filter(
        tenant_id=tenant_id,
        start_date__lte=transaction_date,
        end_date__gte=transaction_date,
    ).first()

    if existing_closed:
        raise ValidationError(
            f"الفترة المالية «{existing_closed.name}» مغلقة. "
            f"افتحها من إدارة الفترات المالية قبل ترحيل قيود بتاريخ {transaction_date}."
        )

    raise ValidationError(
        f"لا توجد فترة مالية مفتوحة تغطي التاريخ {transaction_date}. "
        f"أنشئ فترة مالية من صفحة إدارة الفترات المالية."
    )


def create_fiscal_year(tenant, year):
    """
    Creates a calendar-year fiscal period (Jan 1 – Dec 31) if it doesn't exist.
    Returns the existing or newly created FiscalPeriod.
    """
    start = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)
    existing = FiscalPeriod.objects.filter(
        tenant=tenant, start_date=start, end_date=end,
    ).first()
    if existing:
        return existing
    return FiscalPeriod.objects.create(
        tenant=tenant,
        name=f"FY {year}",
        start_date=start,
        end_date=end,
        status='Open',
        is_closed=False,
    )

def validate_journal_entry(header, lines_data):
    """
    Validates a journal entry using snake_case field names.
    Professional Accounting Rules:
    1. Debits == Credits (Strict)
    2. Active Accounts only.
    3. Correct Tenant context.
    4. Fiscal Period is Open.
    5. Valid Partners and Cost Centers if provided.
    """
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    
    header_tenant_id = header.tenant_id if header.tenant_id is not None else 0
    
    # 1. Fiscal Period Validation
    if header.transaction_date:
         validate_fiscal_period(header_tenant_id, header.transaction_date)

    for line in lines_data:
        # 'line' can be a dict (from request) or a JournalLine object (from DB updates)
        # We need to normalize access
        is_object = hasattr(line, 'account_id') or hasattr(line, 'account')
        
        if is_object:
            account_id = line.account_id
            partner_id = line.partner_id
            cost_center_id = line.cost_center_id
            debit = line.debit
            credit = line.credit
        else:
            account_id = line.get('account') 
            partner_id = line.get('partner')
            cost_center_id = line.get('cost_center')
            debit = line.get('debit', 0.00)
            credit = line.get('credit', 0.00)
        
        if not account_id:
            raise ValidationError("One or more lines are missing an account.")
            
        try:
            account = Account.objects.get(id=account_id)
        except Account.DoesNotExist:
            raise ValidationError(f"Account with ID {account_id} does not exist.")
        
        if not account.is_active:
            raise ValidationError(f"Account {account.name} is inactive.")
        
        # Validate Tenant Scope
        account_tenant_id = account.tenant_id if account.tenant_id is not None else 0
        if header_tenant_id != 0 and account_tenant_id != 0 and account_tenant_id != header_tenant_id:
            raise ValidationError(f"Account {account.name} belongs to a different tenant.")
        
        # Validate Partner if Present (scoped to the journal's tenant —
        # referencing another company's partner would leak across tenants)
        if partner_id:
            partner_qs = Partner.objects.filter(id=partner_id)
            if header_tenant_id != 0:
                partner_qs = partner_qs.filter(tenant_id=header_tenant_id)
            if not partner_qs.exists():
                raise ValidationError(f"Partner ID {partner_id} does not exist for this tenant.")

        # Validate Cost Center if Present (same tenant scoping)
        if cost_center_id:
            cc_qs = CostCenter.objects.filter(id=cost_center_id)
            if header_tenant_id != 0:
                cc_qs = cc_qs.filter(tenant_id=header_tenant_id)
            if not cc_qs.exists():
                raise ValidationError(f"Cost Center ID {cost_center_id} does not exist for this tenant.")

        total_debit += Decimal(str(debit))
        total_credit += Decimal(str(credit))
    
    # 2. Strict Double Entry check — exact zero after quantize
    total_debit_q = total_debit.quantize(Decimal('0.01'))
    total_credit_q = total_credit.quantize(Decimal('0.01'))
    if total_debit_q != total_credit_q:
        raise ValidationError(f"Unbalanced entry: Total Debit ({total_debit_q}) != Total Credit ({total_credit_q}). Diff: {total_debit_q - total_credit_q}")
    
    if total_debit == 0:
        raise ValidationError("Journal entry cannot be empty (zero amount).")

def create_audit_log(tenant, user, action, model_name, object_id, change_details):
    try:
        auth_user = user if user and user.is_authenticated else None
        
        # Handle Tenant vs None
        tenant_to_use = tenant
        if not tenant_to_use:
             # Try to find a system tenant or handle optionality
             # Ideally we shouldn't create logs without tenant, but existing logic allows it
             pass 

        # We can't really save without a valid tenant FK if strict, so we assume tenant is provided or we fetch default
        if tenant_to_use:
            AccountingAuditLog.objects.create(
                tenant=tenant_to_use,
                user=auth_user,
                action=action,
                model_name=model_name,
                object_id=object_id,
                change_details=change_details
            )
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("Failed to create accounting audit log: %s", e)

def post_journal_entry(journal_id, user=None):
    import logging as _log
    _logger = _log.getLogger(__name__)
    try:
        with transaction.atomic():
            header = JournalHeader.objects.select_for_update().get(id=journal_id)
            if header.is_posted:
                _logger.warning("Journal %s already posted.", journal_id)
                raise ValidationError("Journal entry is already posted.")

            header_tenant_id = header.tenant_id if header.tenant_id is not None else 0
            if header.transaction_date:
                validate_fiscal_period(header_tenant_id, header.transaction_date)

            # Re-verify balance on actual saved lines before posting
            lines = list(header.lines.all())
            if lines:
                validate_journal_entry(header, lines)

            header.is_posted = True
            header.save(force_update=True)
            _logger.info("Journal %s set to POSTED.", journal_id)

        create_audit_log(
            tenant=header.tenant,
            user=user,
            action='POST',
            model_name='JournalHeader',
            object_id=header.id,
            change_details="Journal entry posted."
        )
        return header
    except JournalHeader.DoesNotExist:
        raise ValidationError(f"Journal with ID {journal_id} does not exist.")


def post_journal(
    *,
    tenant_id: int,
    transaction_date,
    reference_type: str,
    reference_id: int | None,
    description: str,
    lines_data: list[dict],
    currency=None,
    exchange_rate=Decimal("1"),
    user=None,
    idempotent: bool = True,
    branch_id: int | None = None,
) -> JournalHeader:
    """دالة ترحيل مركزية ذرّية — المسار الوحيد لإنشاء + ترحيل أي قيد محاسبي.

    تفرض:
    - فترة مالية مفتوحة
    - توازن دقيق (debit == credit بعد quantize)
    - جميع الأسطر تابعة لنفس tenant
    - idempotency عبر (reference_type, reference_id)
    - select_for_update لمنع السباق

    task11 M4: branch_id يَسِم القيد بفرعه — أساس التقارير المالية المستقلة
    لكل فرع. NULL = قيد على مستوى الشركة/الفرع الرئيسي.

    تُرجع JournalHeader مرحّل (is_posted=True) أو القيد الموجود سابقاً إن كان idempotent.
    """
    _logger = logging.getLogger(__name__)

    # ── 1) Validate fiscal period + journal balance (pre-atomic — fast fail) ──
    validate_fiscal_period(tenant_id, transaction_date)
    mock_hdr = JournalHeader(tenant_id=tenant_id, transaction_date=transaction_date)
    validate_journal_entry(mock_hdr, lines_data)

    # ── 2) Atomic: idempotency (select_for_update) + create + post ──
    with transaction.atomic():
        # الـ select_for_update يقفل أي صف موجود بنفس المفتاح ويمنع السباق:
        # إذا كانت معاملتان متزامنتان تصلان هنا بنفس (reference_type, reference_id)،
        # فالأولى تخلق الصف والثانية ترجع الصف الموجود — لا تكرار.
        if idempotent and reference_type and reference_id is not None:
            existing = (
                JournalHeader.objects.select_for_update()
                .filter(
                    tenant_id=tenant_id,
                    reference_type=reference_type,
                    reference_id=reference_id,
                )
                .first()
            )
            if existing:
                _logger.info(
                    "post_journal idempotent hit: type=%s ref_id=%s → journal %s",
                    reference_type, reference_id, existing.id,
                )
                return existing

        # ── Feature 2: إعادة استخدام رقم القيد المحجوز (recycle bin) ──
        # إن كان لهذا المستند حجز في سلّة المحذوفات (أُلغِيَ ترحيله سابقاً ثم
        # أُعيد الآن)، نُعيد إدراج القيد بنفس رقمه الأصلي بدل تخصيص رقم جديد.
        # الإدراج القسري ذرّي داخل نفس المعاملة؛ أي تعارض (رقم مشغول — غير
        # متوقع عملياً) يسقط بأمان إلى رقم تلقائي جديد مع تحذير.
        reservation = None
        if reference_type and reference_id is not None:
            reservation = (
                VoidedJournal.objects.select_for_update()
                .filter(
                    tenant_id=tenant_id,
                    reference_type=reference_type,
                    reference_id=reference_id,
                )
                .first()
            )

        header_kwargs = dict(
            tenant_id=tenant_id,
            branch_id=branch_id,
            transaction_date=transaction_date,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description[:500],
            is_posted=True,
            currency=currency,
            exchange_rate=exchange_rate,
        )

        jh = None
        if reservation is not None:
            reserved_id = reservation.original_journal_id
            if JournalHeader.objects.filter(pk=reserved_id).exists():
                _logger.warning(
                    "post_journal reuse fallback: reserved journal id=%s already "
                    "occupied (type=%s ref_id=%s) — allocating new number.",
                    reserved_id, reference_type, reference_id,
                )
            else:
                jh = JournalHeader(id=reserved_id, **header_kwargs)
                jh.save(force_insert=True)
                _logger.info(
                    "post_journal reused reserved number: id=%s type=%s ref_id=%s",
                    reserved_id, reference_type, reference_id,
                )
            # الحجز استُهلِك (أُعيد استخدامه أو سقط للبديل) — يُحذف في الحالتين.
            reservation.delete()

        if jh is None:
            jh = JournalHeader.objects.create(**header_kwargs)

        # N8-T6: التحقق من طبيعة الحساب (مدين فقط/دائن فقط)
        account_ids = {r["account"] for r in lines_data}
        nature_map = {
            a.id: a.nature
            for a in Account.objects.filter(id__in=account_ids).only("id", "nature")
        }
        for row in lines_data:
            nature = nature_map.get(row["account"])
            debit = Decimal(str(row.get("debit", 0)))
            credit = Decimal(str(row.get("credit", 0)))
            if nature == Account.NATURE_DEBIT_ONLY and credit > 0:
                raise ValidationError(
                    f"الحساب #{row['account']} طبيعته «مدين فقط» — لا يمكن إضافة مبلغ دائن."
                )
            if nature == Account.NATURE_CREDIT_ONLY and debit > 0:
                raise ValidationError(
                    f"الحساب #{row['account']} طبيعته «دائن فقط» — لا يمكن إضافة مبلغ مدين."
                )

        for row in lines_data:
            JournalLine.objects.create(
                tenant_id=tenant_id,
                journal=jh,
                account_id=row["account"],
                debit=Decimal(str(row.get("debit", 0))),
                credit=Decimal(str(row.get("credit", 0))),
                partner_id=row.get("partner"),
                cost_center_id=row.get("cost_center"),
                description=(row.get("description") or "")[:500],
            )

        _logger.info(
            "post_journal created+posted: type=%s ref_id=%s journal=%s lines=%d",
            reference_type, reference_id, jh.id, len(lines_data),
        )

    create_audit_log(
        tenant=_get_tenant_obj(tenant_id),
        user=user,
        action='POST',
        model_name='JournalHeader',
        object_id=jh.id,
        change_details=f"Centralized post: {reference_type} ref={reference_id}",
    )

    return jh


def unpost_document(
    *,
    tenant_id: int,
    reference_id: int,
    journal_reference_types,
    stock_reference_types=(),
    user=None,
    document_label: str = "",
    recycle: bool = False,
) -> dict:
    """المسار المركزي للتراجع عن ترحيل مستند (إلغاء الترحيل / cascade delete).

    يحذف **كل** قيود اليومية التي ولّدها المستند (full cascade — أسطر القيد
    تُحذف تلقائياً عبر on_delete=CASCADE) ويعيد حركات المخزون التابعة له، في
    معاملة واحدة ذرّية (all-or-nothing) فلا تبقى حالة محاسبية ناقصة.

    النطاق محصور بدقة بقيود هذا المستند وحده:
    (tenant, reference_id, reference_type ∈ journal_reference_types) — فلا
    تُمَسّ أي قيود يتيمة أو غير مرتبطة. بخلاف مسارات «القيد العكسي» القديمة،
    هذا حذف فعلي يُرجِع المستند لحالة مسودة قابلة للتعديل/الحذف.

    recycle=True يحجز رقم القيد الأساسي (المطابق لأول نوع في
    journal_reference_types) في سلّة المحذوفات (VoidedJournal) قبل الحذف، ليُعاد
    استخدامه نصّاً عند إعادة الترحيل. القيود الفرعية (تكلفة المبيعات/الاستلام)
    تُحذف دون حجز لأنها تُولَّد من جديد عند إعادة الترحيل.

    Returns: dict فيه عدد القيود وحركات المخزون المحذوفة.
    """
    from inventory.services import find_stock_dependents, reverse_stock_movements

    journal_reference_types = list(journal_reference_types)
    primary_ref_type = journal_reference_types[0] if journal_reference_types else None
    with transaction.atomic():
        # حارس الاعتمادية: امنع التراجع إن بُنيت عليه مستندات لاحقة (بيع/صرف
        # استهلكت مخزونه وتكلفته)، فحذفه يُيتّم قيود تكلفة المبيعات المبنية عليه.
        # رسالة بقائمة المستندات المتأثّرة كي يتراجع عنها المستخدم أولاً.
        if stock_reference_types:
            dependents = find_stock_dependents(
                tenant_id=tenant_id,
                reference_id=reference_id,
                reference_types=stock_reference_types,
            )
            if dependents:
                listing = "؛ ".join(
                    f"{d['label']} (الأصناف: {'، '.join(d['products'])})"
                    for d in dependents
                )
                logger.warning(
                    "unpost_document blocked: %s ref=%s has %d dependent document(s)",
                    document_label or journal_reference_types, reference_id, len(dependents),
                )
                raise ValidationError(
                    f"تعذّر التراجع عن ترحيل {document_label or 'هذا المستند'}: "
                    f"توجد مستندات لاحقة بُنيت عليه (استهلكت مخزونه/تكلفته). "
                    f"تراجع عن ترحيلها أولاً ثم أعد المحاولة — المتأثّرة: {listing}"
                )
        headers = list(
            JournalHeader.objects.select_for_update().filter(
                tenant_id=tenant_id,
                reference_id=reference_id,
                reference_type__in=journal_reference_types,
            )
        )
        header_ids = [h.id for h in headers]
        lines_deleted = JournalLine.objects.filter(journal_id__in=header_ids).count() if header_ids else 0

        # Feature 2: حجز رقم القيد الأساسي في سلّة المحذوفات قبل الحذف.
        if recycle and primary_ref_type:
            primary = next((h for h in headers if h.reference_type == primary_ref_type), None)
            if primary is not None:
                VoidedJournal.objects.update_or_create(
                    tenant_id=tenant_id,
                    reference_type=primary_ref_type,
                    reference_id=reference_id,
                    defaults={
                        "original_journal_id": primary.id,
                        "transaction_date": primary.transaction_date,
                        "description": primary.description,
                        "voided_by": user if (user and user.is_authenticated) else None,
                    },
                )

        # حذف الترويسة يُسقِط الأسطر تلقائياً (CASCADE)؛ نمرّ على كلٍّ على حدة
        # لأن JournalHeader.save() يحرس التعديل لا الحذف — والحذف مسموح هنا.
        for h in headers:
            h.delete()

        stock_deleted = 0
        if stock_reference_types:
            stock_deleted = reverse_stock_movements(
                tenant_id=tenant_id,
                reference_id=reference_id,
                reference_types=stock_reference_types,
            )

    logger.info(
        "unpost_document: %s ref=%s deleted journals=%d lines=%d stock_movements=%d",
        document_label or journal_reference_types, reference_id,
        len(header_ids), lines_deleted, stock_deleted,
    )
    create_audit_log(
        tenant=_get_tenant_obj(tenant_id),
        user=user,
        action='DELETE',
        model_name='JournalHeader',
        object_id=reference_id,
        change_details=(
            f"Unpost {document_label or ''}: deleted {len(header_ids)} journal(s) "
            f"({journal_reference_types}) + {stock_deleted} stock movement(s)"
        )[:1000],
    )
    return {
        "journals_deleted": len(header_ids),
        "lines_deleted": lines_deleted,
        "stock_movements_deleted": stock_deleted,
    }


def _get_tenant_obj(tenant_id: int):
    """Fetch Tenant model instance from ID, returning None on failure."""
    try:
        from tenants.models import Tenant
        return Tenant.objects.filter(pk=tenant_id).first()
    except Exception:
        return None


def year_end_close(*, tenant_id: int, fiscal_year: int, retained_earnings_account_id: int, user=None) -> dict:
    """روتين إغلاق سنوي: يصفّر حسابات الإيراد والمصروف إلى أرباح محتجزة.

    يُنشأ قيد إغلاق واحد (reference_type='YEAR_END_CLOSE') يرحّل:
    - كل حسابات Revenue (Cr → Dr) بصافي رصيدها
    - كل حسابات Expense (Dr → Cr) بصافي رصيدها
    - الفرق (صافي الربح/الخسارة) إلى حساب retained_earnings

    يُرجع dict يحتوي على journal_id و profit_or_loss و rows_count.
    """
    from django.db.models import Sum
    from .models import Account

    _logger = logging.getLogger(__name__)

    # ── 1) Validate retained earnings account ──
    try:
        re_acc = Account.objects.get(pk=retained_earnings_account_id, tenant_id=tenant_id, is_active=True)
    except Account.DoesNotExist:
        raise ValidationError("حساب الأرباح المحتجزة غير موجود أو غير نشط.")

    # ── 2) Check idempotency ──
    existing = JournalHeader.objects.filter(
        tenant_id=tenant_id,
        reference_type='YEAR_END_CLOSE',
        reference_id=fiscal_year,
    ).first()
    if existing:
        _logger.info("year_end_close idempotent hit: year=%s → journal %s", fiscal_year, existing.id)
        return {"journal_id": existing.id, "profit_or_loss": "0.00", "rows_count": 0, "already_closed": True}

    # ── 3) Compute net balances for P&L accounts ──
    start_date = datetime.date(fiscal_year, 1, 1)
    end_date = datetime.date(fiscal_year, 12, 31)

    lines_data = []
    total_revenue = Decimal("0")
    total_expense = Decimal("0")

    for acc_type in ("Revenue", "Expense"):
        qs = (
            JournalLine.objects
            .filter(
                tenant_id=tenant_id,
                account__account_type=acc_type,
                account__tenant_id=tenant_id,
                journal__is_posted=True,
                journal__transaction_date__gte=start_date,
                journal__transaction_date__lte=end_date,
            )
            .values("account_id", "account__name", "account__code")
            .annotate(dr=Sum("base_debit"), cr=Sum("base_credit"))
        )

        for row in qs:
            dr = Decimal(str(row["dr"] or 0))
            cr = Decimal(str(row["cr"] or 0))
            net = dr - cr  # موجب = مدين (مصروف)، سالب = دائن (إيراد)

            if acc_type == "Revenue":
                # Revenue has credit balance (net negative) → close by debiting
                if cr > dr:
                    close_amt = (cr - dr).quantize(Decimal("0.01"))
                    if close_amt > 0:
                        lines_data.append({
                            "account": row["account_id"],
                            "debit": close_amt,
                            "credit": Decimal("0"),
                            "description": f"إغلاق {acc_type} {row['account__code']} — {row['account__name']}",
                        })
                        total_revenue += close_amt
            else:
                # Expense has debit balance (net positive) → close by crediting
                if dr > cr:
                    close_amt = (dr - cr).quantize(Decimal("0.01"))
                    if close_amt > 0:
                        lines_data.append({
                            "account": row["account_id"],
                            "debit": Decimal("0"),
                            "credit": close_amt,
                            "description": f"إغلاق {acc_type} {row['account__code']} — {row['account__name']}",
                        })
                        total_expense += close_amt

    if not lines_data:
        raise ValidationError(f"لا توجد حركات P&L للسنة {fiscal_year} — لا حاجة للإغلاق.")

    # ── 4) Net profit/loss to retained earnings ──
    profit_or_loss = (total_revenue - total_expense).quantize(Decimal("0.01"))
    if profit_or_loss > 0:
        # Profit → credit retained earnings
        lines_data.append({
            "account": retained_earnings_account_id,
            "debit": Decimal("0"),
            "credit": profit_or_loss,
            "description": f"صافي ربح {fiscal_year} → أرباح محتجزة",
        })
    elif profit_or_loss < 0:
        # Loss → debit retained earnings
        lines_data.append({
            "account": retained_earnings_account_id,
            "debit": abs(profit_or_loss),
            "credit": Decimal("0"),
            "description": f"صافي خسارة {fiscal_year} → أرباح محتجزة",
        })

    # ── 5) Post via centralized function ──
    jh = post_journal(
        tenant_id=tenant_id,
        transaction_date=end_date,
        reference_type="YEAR_END_CLOSE",
        reference_id=fiscal_year,
        description=f"إغلاق سنوي {fiscal_year} — صافي {'ربح' if profit_or_loss >= 0 else 'خسارة'} {abs(profit_or_loss)}",
        lines_data=lines_data,
        user=user,
        idempotent=True,
    )

    _logger.info(
        "year_end_close: year=%s journal=%s revenue=%s expense=%s pnl=%s",
        fiscal_year, jh.id, total_revenue, total_expense, profit_or_loss,
    )

    return {
        "journal_id": jh.id,
        "profit_or_loss": str(profit_or_loss),
        "total_revenue": str(total_revenue),
        "total_expense": str(total_expense),
        "rows_count": len(lines_data),
    }


# ── N8-T14: Cheque movements ─────────────────────────────────

VALID_TRANSITIONS = {
    'Draft':           {'deposit', 'withdraw'},
    'Under_Collection': {'collect', 'bounce'},
    'Collected':        set(),
    'Bounced':          {'return_to_customer', 'settle'},
    'Returned':         set(),
    'Settled':          set(),
}

STATUS_MAP = {
    'deposit':            'Under_Collection',
    'withdraw':           'Collected',
    'collect':            'Collected',
    'bounce':             'Bounced',
    'return_to_customer': 'Returned',
    'settle':             'Settled',
}


def _resolve_cheque_under_collection_account(tenant_id: int):
    """حساب «شيكات برسم التحصيل» — نفس منطق ترحيل الفاتورة (M2-T3).

    task13 M2: البحث القديم بـ code__startswith="1106" كان يلتقط
    «دفعات مقدمة للموردين» في الشجرة المعيارية ⇒ ترحيل خاطئ.
    الآن: إعدادات المبيعات ← الحساب المبذور 1107 ← مطابقة الاسم.
    """
    from django.db.models import Q
    from sales.models import SalesSettings
    ss = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if ss and ss.default_cheques_under_collection_account_id:
        return ss.default_cheques_under_collection_account
    base = Account.objects.filter(tenant_id=tenant_id, account_type="Asset", is_active=True)
    return (
        base.filter(code="1107").first()
        or base.filter(name__icontains="شيكات").first()
    )


def _resolve_cheque_cash_account(tenant_id: int, account_id=None):
    """حساب الصندوق/البنك لوجهة التحصيل — صريح أو افتراضي الإعدادات."""
    from sales.models import SalesSettings
    if account_id:
        acc = Account.objects.filter(pk=account_id, tenant_id=tenant_id, is_active=True).first()
        if not acc:
            raise ValidationError("حساب الصندوق/البنك المحدد غير موجود أو لا يتبع هذه الشركة.")
        return acc
    ss = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if ss and ss.default_cash_account_id:
        return ss.default_cash_account
    raise ValidationError(
        "حدّد حساب الصندوق/البنك للتحويل، أو عيّن default_cash_account في إعدادات المبيعات."
    )


def _resolve_cheque_ar_account(cheque):
    """حساب ذمم العميل لارتداد/تسوية الشيك."""
    from sales.models import SalesSettings
    partner = cheque.partner or (cheque.sales_invoice.customer if cheque.sales_invoice_id else None)
    if partner is None:
        raise ValidationError("الشيك بلا عميل مرتبط — لا يمكن تحديد حساب الذمم.")
    if partner.linked_account_id:
        return partner.linked_account, partner
    if partner.group_id and partner.group.account_receivable_id:
        return partner.group.account_receivable, partner
    ss = SalesSettings.objects.filter(tenant_id=cheque.tenant_id).first()
    if ss and ss.default_ar_account_id:
        return ss.default_ar_account, partner
    raise ValidationError("لا يوجد حساب ذمم للعميل المرتبط بالشيك.")


def transfer_cheque(cheque_id, movement_type, *, user=None, notes='',
                    account_id=None, movement_date=None):
    """task11 R2-A3 — تحويل حالة شيك مع القيد المحاسبي المرافق.

    كانت آلة الحالات بلا قيود محاسبية (والواجهة تتجاوزها أصلاً بـ PATCH خام)
    فتبقى المبالغ في «شيكات برسم التحصيل» للأبد. القيود الآن:
      - collect / withdraw : مدين صندوق/بنك ÷ دائن شيكات برسم التحصيل
      - bounce             : مدين ذمم العميل ÷ دائن شيكات برسم التحصيل
      - settle             : مدين صندوق/بنك ÷ دائن ذمم العميل
      - deposit / return_to_customer : حركة ورقية — بلا قيد
    يُرحَّل القيد فقط إذا كان الشيك داخل الدفاتر أصلاً (مربوط بفاتورة أو
    سند قبض) — الشيكات المستقلة legacy تتحول حالتها فقط مع تحذير في اللوغ.
    Idempotent عبر (CHEQUE_<MOVE>, cheque_id).
    """
    import datetime as _dt
    from .models import Cheque, ChequeMovement

    cheque = Cheque.objects.select_related(
        'tenant', 'partner', 'partner__group', 'sales_invoice', 'currency',
    ).get(pk=cheque_id)
    allowed = VALID_TRANSITIONS.get(cheque.status, set())
    if movement_type not in allowed:
        raise ValidationError(
            f"لا يمكن تنفيذ «{movement_type}» على شيك بحالة «{cheque.status}»."
        )
    next_status = STATUS_MAP[movement_type]
    when = movement_date or _dt.date.today()
    amount = Decimal(str(cheque.amount or 0)).quantize(Decimal("0.01"))

    # GL يخص الشيكات الواردة المسجلة دفترياً فقط
    in_books = bool(cheque.sales_invoice_id or cheque.customer_payment_id)
    needs_gl = (
        movement_type in ('collect', 'withdraw', 'bounce', 'settle')
        and cheque.direction == 'Incoming'
        and amount > 0
    )
    if needs_gl and not in_books:
        logging.getLogger(__name__).warning(
            "transfer_cheque: cheque %s has no invoice/payment link — status-only transfer",
            cheque.pk,
        )
        needs_gl = False

    journal = None
    with transaction.atomic():
        if needs_gl:
            branch_id = cheque.sales_invoice.branch_id if cheque.sales_invoice_id else None
            if movement_type in ('collect', 'withdraw'):
                uc = _resolve_cheque_under_collection_account(cheque.tenant_id)
                if not uc:
                    raise ValidationError("لا يوجد حساب «شيكات برسم التحصيل» (1107).")
                cash = _resolve_cheque_cash_account(cheque.tenant_id, account_id)
                dr, cr = cash, uc
                desc = f"تحصيل شيك {cheque.cheque_number}"
                partner_id = cheque.partner_id
            elif movement_type == 'bounce':
                uc = _resolve_cheque_under_collection_account(cheque.tenant_id)
                if not uc:
                    raise ValidationError("لا يوجد حساب «شيكات برسم التحصيل» (1107).")
                ar, partner = _resolve_cheque_ar_account(cheque)
                dr, cr = ar, uc
                desc = f"ارتداد شيك {cheque.cheque_number} — إعادة الذمم على العميل"
                partner_id = partner.pk
            else:  # settle
                ar, partner = _resolve_cheque_ar_account(cheque)
                cash = _resolve_cheque_cash_account(cheque.tenant_id, account_id)
                dr, cr = cash, ar
                desc = f"تسوية شيك مرتد {cheque.cheque_number}"
                partner_id = partner.pk

            journal = post_journal(
                tenant_id=cheque.tenant_id,
                transaction_date=when,
                reference_type=f"CHEQUE_{movement_type.upper()}",
                reference_id=cheque.pk,
                description=desc,
                lines_data=[
                    {"account": dr.pk, "partner": partner_id,
                     "debit": amount, "credit": Decimal("0"), "description": desc},
                    {"account": cr.pk, "partner": partner_id,
                     "debit": Decimal("0"), "credit": amount, "description": desc},
                ],
                currency=cheque.currency,
                user=user,
                branch_id=branch_id,
            )

        ChequeMovement.objects.create(
            cheque=cheque,
            movement_type=movement_type,
            notes=notes,
            created_by=user,
        )
        cheque.status = next_status
        cheque.save(update_fields=['status'])
        create_audit_log(
            tenant=cheque.tenant,
            user=user,
            action='UPDATE',
            model_name='Cheque',
            object_id=cheque.id,
            change_details=(
                f"Cheque status → {next_status} via {movement_type}"
                + (f" (journal {journal.id})" if journal else "")
            ),
        )
    return cheque


# ─────────────────────────────────────────────────────────
#  task18 DEF-C1: رصيد الشريك من دفتر الأستاذ الفرعي (subledger)
# ─────────────────────────────────────────────────────────

def partner_account_statement(
    *, tenant_id: int, partner_id: int, is_supplier: bool,
    limit: int = 50, offset: int = 0,
) -> dict:
    """FEAT-4: كشف حساب الشريك من أسطر القيود المرحَّلة — مع رصيد جارٍ لكل سطر.

    الرصيد الجاري يُحسب خادمياً بالترتيب الزمني ويُطابق `partner_posted_balance`
    (لا مصدر حقيقة موازٍ — A4). للعميل: مدين−دائن؛ للمورد: دائن−مدين. مُرقَّم.
    """
    base = (
        JournalLine.objects.filter(
            tenant_id=tenant_id, partner_id=partner_id, journal__is_posted=True,
        )
        .order_by("journal__transaction_date", "journal_id", "id")
    )
    # خفيف: عمودان عشريان فقط لحساب الرصيد الجاري بالترتيب (بحدود أسطر الشريك).
    ordered = list(base.values_list("id", "base_debit", "base_credit"))
    total = len(ordered)
    running = Decimal("0")
    running_by_id: dict[int, Decimal] = {}
    for lid, d, c in ordered:
        d = Decimal(str(d or 0))
        c = Decimal(str(c or 0))
        running += (c - d) if is_supplier else (d - c)
        running_by_id[lid] = running
    closing = running

    page_ids = [lid for lid, _d, _c in ordered[offset:offset + limit]]
    page = (
        JournalLine.objects.filter(id__in=page_ids)
        .select_related("journal")
    )
    by_id = {jl.id: jl for jl in page}
    rows = []
    for lid in page_ids:
        jl = by_id.get(lid)
        if jl is None:
            continue
        j = jl.journal
        rows.append({
            "id": jl.id,
            "journal_id": j.id,
            "date": j.transaction_date.isoformat() if j.transaction_date else None,
            "reference_type": j.reference_type,
            "reference_id": j.reference_id,
            "description": jl.description or j.description or "",
            "debit": str(jl.base_debit),
            "credit": str(jl.base_credit),
            "running_balance": str(running_by_id[lid]),
        })
    return {
        "results": rows,
        "count": total,
        "limit": limit,
        "offset": offset,
        "closing_balance": str(closing),
    }


def partner_posted_balance(tenant_id: int, partner_id: int) -> tuple[Decimal, Decimal]:
    """مجموع مدين/دائن أسطر القيود المرحَّلة لهذا الشريك (بالعملة الأساسية).

    يُرجع (debit, credit). تفسير الرصيد متروك للمستدعي حسب نوع الشريك:
    عميل (ذمم مدينة) ⇒ الرصيد = debit − credit؛ مورد (ذمم دائنة) ⇒ credit − debit.
    """
    from django.db.models import Sum
    agg = JournalLine.objects.filter(
        tenant_id=tenant_id,
        partner_id=partner_id,
        journal__is_posted=True,
    ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
    debit = Decimal(str(agg["d"] or 0))
    credit = Decimal(str(agg["c"] or 0))
    return debit, credit

