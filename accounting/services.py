import calendar
import datetime
import logging
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from .models import Account, ExchangeRate, JournalHeader, JournalLine, AccountingAuditLog, FiscalPeriod, CostCenter, VoidedJournal
from decimal import Decimal
from partners.models import Partner
from tenants.models import Currency, TenantBook
from core.hooks import run_tax_period_guards
from django.utils import timezone

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
        effective_date = timezone.localdate()
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


IMPORT_EXPENSE_PARENT_CODE = "53"


def _normalize_account_name(value: str) -> str:
    """اسم مُطبَّع للمقارنة: بلا فراغات زائدة وبلا الجزء الإنجليزي بين قوسين."""
    text = " ".join(str(value or "").split()).strip()
    if "(" in text:
        text = text.split("(", 1)[0].strip() or text
    return text.casefold()


def resolve_import_expense_account(tenant_id: int, name: str):
    """يُرجع (حساب، أُنشئ؟) لمصروف استيراد بالاسم المكتوب تحت شجرة «53».

    إن وُجد حساب بنفس الاسم (تطبيع: فراغات + تجاهل الجزء الإنجليزي) يُعاد كما هو،
    وإلا يُنشأ حساب جديد ابناً مباشراً للبند «53 مصاريف الاستيراد المباشرة».
    يُرجع (None, False) إن لم يكن الاسم صالحاً أو شجرة الاستيراد غير مُهيّأة.
    """
    clean = " ".join(str(name or "").split()).strip()
    if not clean:
        return None, False
    parent = Account.objects.filter(tenant_id=tenant_id, code=IMPORT_EXPENSE_PARENT_CODE).first()
    if parent is None:
        logger.warning("import expense parent 53 missing tenant=%s", tenant_id)
        return None, False

    subtree = list(
        Account.objects.filter(
            tenant_id=tenant_id, code__startswith=IMPORT_EXPENSE_PARENT_CODE,
        ).exclude(code=IMPORT_EXPENSE_PARENT_CODE)
    )
    target = _normalize_account_name(clean)
    for account in subtree:
        if _normalize_account_name(account.name) == target:
            return account, False

    used = set()
    for account in subtree:
        code = str(account.code or "")
        if code.startswith(IMPORT_EXPENSE_PARENT_CODE) and code[2:].isdigit():
            used.add(int(code[2:]))
    # P1-15 (SCALABILITY_AUDIT): كانت حلقةٌ تصل إلى 9000 دورة، كل دورة استعلام
    # `exists()` مستقل — على قاعدة بعيدة هذا آلاف الرحلات لتخصيص رقم واحد. وهي
    # زائدة أصلاً: `subtree` أعلاه يجلب **كل** حسابات «53*»، فمجموعة `used`
    # تعرف المشغول كاملاً بلا استعلام إضافي.
    # ويبقى السباق: طلبان متزامنان يحسبان الرقم نفسه. الحارس الصحيح هو قيد
    # الفريدة (tenant, code) في القاعدة لا الفحص المسبق — فنُعيد المحاولة على
    # IntegrityError بدل أن نراهن على أن أحداً لم يسبقنا بين الفحص والكتابة.
    serial = max(used) + 1 if used else 1
    for _ in range(50):
        candidate = f"{IMPORT_EXPENSE_PARENT_CODE}{serial:02d}"
        try:
            with transaction.atomic():
                account = Account.objects.create(
                    tenant_id=tenant_id,
                    code=candidate,
                    name=clean,
                    parent=parent,
                    account_type="Expense",
                    is_active=True,
                )
            break
        except IntegrityError:
            # سبقنا طلبٌ آخر لهذا الرقم — جرّب التالي.
            serial += 1
    else:  # pragma: no cover - مساحة الترقيم لا تنفد عملياً
        raise ValueError("تعذّر تخصيص رقم حساب جديد تحت «مصاريف الاستيراد».")
    logger.info(
        "import expense account created tenant=%s code=%s name=%s",
        tenant_id, account.code, account.name,
    )
    return account, True


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


GRANULARITY_MONTHLY = 'monthly'
GRANULARITY_YEARLY = 'yearly'
FISCAL_GRANULARITIES = (GRANULARITY_MONTHLY, GRANULARITY_YEARLY)


def assert_no_period_overlap(tenant_id, start_date, end_date, exclude_pk=None):
    """A2/THA-185 — يمنع فترتين ماليتين تتقاطعان لنفس الشركة.

    تداخل الفترات يجعل القفل بلا معنى: `validate_fiscal_period` تلتقط أول فترة
    تغطّي التاريخ، فتكفي فترة مفتوحة متداخلة لتمرير قيد إلى شهر مُقفَل. النطاق
    محصور بالشركة — فترة شركة أخرى ليست تداخلاً.
    """
    if start_date > end_date:
        raise ValidationError(
            f"تاريخ بداية الفترة ({start_date}) يجب ألا يتجاوز تاريخ نهايتها ({end_date})."
        )
    clash = FiscalPeriod.objects.filter(
        tenant_id=tenant_id,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    existing = clash.order_by('start_date').first()
    if existing:
        raise ValidationError(
            f"الفترة المطلوبة ({start_date} — {end_date}) تتداخل مع الفترة "
            f"«{existing.name}» ({existing.start_date} — {existing.end_date}). "
            f"الفترات المالية لا تتقاطع."
        )


def _month_ranges(year):
    """(البداية، النهاية، الاسم) لكل شهر في السنة — النهاية آخر يوم فعلي فيه."""
    for month in range(1, 13):
        start = datetime.date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        yield start, datetime.date(year, month, last_day), f"{year}-{month:02d}"


def create_fiscal_year(tenant, year, granularity=GRANULARITY_MONTHLY):
    """ينشئ فترات السنة المالية — 12 شهراً افتراضياً، أو فترة سنة واحدة.

    الافتراض شهريّ لأن المحاسب يُقفِل شهراً بعد شهر (دفترة · Odoo · Zoho Books
    كلها تُنشئ الأشهر مع السنة)؛ فترةٌ سنوية واحدة تعني أن القفل كل شيء أو لا
    شيء. `granularity='yearly'` تُبقي السلوك القديم (فترة `FY <year>` واحدة).

    idempotent: الفترة الموجودة بنفس المدى تُعاد كما هي؛ أي مدى آخر متداخل
    يُرفض عبر `assert_no_period_overlap`.

    تُرجع دائماً list[FiscalPeriod] مرتّبة بتاريخ البداية.
    """
    if granularity not in FISCAL_GRANULARITIES:
        raise ValidationError(
            f"تفصيل الفترة «{granularity}» غير معروف — المسموح: "
            f"{'، '.join(FISCAL_GRANULARITIES)}."
        )
    if granularity == GRANULARITY_YEARLY:
        ranges = [(datetime.date(year, 1, 1), datetime.date(year, 12, 31), f"FY {year}")]
    else:
        ranges = list(_month_ranges(year))

    periods = []
    with transaction.atomic():
        for start, end, name in ranges:
            existing = FiscalPeriod.objects.filter(
                tenant=tenant, start_date=start, end_date=end,
            ).first()
            if existing:
                periods.append(existing)
                continue
            assert_no_period_overlap(tenant.pk, start, end)
            periods.append(FiscalPeriod.objects.create(
                tenant=tenant,
                name=name,
                start_date=start,
                end_date=end,
                status='Open',
                is_closed=False,
            ))
    return periods

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
        raise ValidationError(
            "القيد غير متوازن: مجموع المدين "
            f"{total_debit_q} ₪ لا يساوي مجموع الدائن {total_credit_q} ₪ "
            f"(الفرق {total_debit_q - total_credit_q} ₪). "
            "لم يُرحَّل شيء. جرّب «إعادة حساب التكلفة» ثم أعد الترحيل، "
            "وإن استمر الفرق فأبلغ الدعم بهذا الرقم."
        )
    
    if total_debit == 0:
        raise ValidationError("Journal entry cannot be empty (zero amount).")

def _truncate_for_field(value, field_name: str):
    """يقصّ النص على طول العمود. MySQL في وضع STRICT يرفض الأطول (خطأ 1406)."""
    if value is None:
        return value
    text = str(value)
    max_length = AccountingAuditLog._meta.get_field(field_name).max_length
    return text[:max_length] if max_length else text


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
            # savepoint مستقل: فشل سطر تدقيق يجب ألا يُسقط عملية المستدعي. بدونه
            # كان خطأ DB هنا (مثل action أطول من varchar(20)) يُبتلع في except
            # أدناه بينما Django قد وسم المعاملة needs_rollback ⇒ يُلغى القيد
            # المحاسبي وحفظ المستند بصمت بينما الواجهة ترى «تم بنجاح».
            with transaction.atomic():
                AccountingAuditLog.objects.create(
                    tenant=tenant_to_use,
                    user=auth_user,
                    action=_truncate_for_field(action, 'action'),
                    model_name=_truncate_for_field(model_name, 'model_name'),
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
    run_tax_period_guards(tenant_id, transaction_date)
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
            # A3: المستخدم كان يصل إلى سطر التدقيق فقط ويسقط عن القيد نفسه —
            # فدفتر اليومية لا يعرف صاحب أي قيد. نفس شرط create_audit_log
            # (مستخدم مجهول/غائب ⇒ NULL) كي لا يختلف المصدران.
            created_by=user if user is not None and getattr(
                user, 'is_authenticated', False) else None,
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


def assert_period_open_for_unpost(tenant_id, transaction_date, document_label=""):
    """A2/THA-184 — إلغاء الترحيل تعديلٌ على الفترة، فيمرّ بحرّاسها نفسهم.

    `post_journal` وحده كان يستدعي `validate_fiscal_period` +
    `run_tax_period_guards`؛ أما `unpost_document` فكان يحذف قيود مستند مؤرَّخ
    داخل شهر مُقفَل ويعيد حركات مخزونه بلا أي حارس — قفلٌ يمنع الإضافة ويسمح
    بالحذف ليس قفلاً. الاستثناء الوحيد مسارٌ مُعلَن: إعادة فتح الفترة بسبب
    مسجَّل (`FiscalPeriodViewSet.reopen_period`) ثم التراجع.
    """
    prefix = f"تعذّر التراجع عن ترحيل {document_label or 'هذا المستند'}: "
    try:
        validate_fiscal_period(tenant_id, transaction_date)
        run_tax_period_guards(tenant_id, transaction_date)
    except ValidationError as exc:
        detail = "؛ ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        raise ValidationError(
            f"{prefix}{detail} أعد فتح الفترة بسبب مسجَّل إن كان التعديل ضرورياً."
        ) from exc


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

    المستندات التي تمرّ من هنا (7): فاتورة بيع · مرجع بيع · فاتورة شراء · مرجع
    شراء · سند قبض · سند صرف · **أمر صيانة** (صرف قطع الكفالة —
    `after_sales.service_orders.unpost_covered_parts`).

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
                    f"{d['label']} (المنتجات: {'، '.join(d['products'])})"
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

        # THA-184: حارس الفترة — تواريخ المستند هي تواريخ ما سيُحذَف فعلاً
        # (القيود، ثم حركات المخزون إن لم يكن للمستند قيد). كلها تُفحص قبل أن
        # يُمَسّ أي صف، فالرفض يُجهض المعاملة كاملة.
        affected_dates = {h.transaction_date for h in headers if h.transaction_date}
        if not affected_dates and stock_reference_types:
            from inventory.models import StockMovement

            affected_dates = set(
                StockMovement.objects.filter(
                    tenant_id=tenant_id,
                    reference_id=reference_id,
                    reference_type__in=list(stock_reference_types),
                ).values_list("movement_date", flat=True)
            )
        for txn_date in sorted(d for d in affected_dates if d):
            assert_period_open_for_unpost(tenant_id, txn_date, document_label)

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

# CHQ-1 — المصدر الواحد لآلة حالات الشيك، جدولٌ لكل اتجاه.
#
# كان جدولاً واحداً مشتركاً، فالصادر يقبل «إيداعاً» بلا معنى، ولا يعرف
# «إلغاء»، ولا يميّز الوارد بين ورقة في اليد وورقة في البنك. وكان بجانبه جدول
# ثانٍ في الموديل يناقضه — حُذف (انظر `accounting/models.py` (`Cheque`)).
#
# قاعدة الـcutover: الحالة نفسها هي المميِّز. الشيك القديم في `Under_Collection`
# (قيد استلامه دائن 1107) يكمل مساره القديم حرفياً؛ الجديد يبدأ `Received`
# (قيد سنده دائن 1109) — لا ترحيل بيانات ولا إعادة كتابة قيد.
INCOMING_TRANSITIONS = {
    'Draft':            {'receive', 'deposit', 'withdraw'},
    'Received':         {'deposit', 'collect', 'endorse', 'return_to_customer'},
    'Under_Collection': {'collect', 'bounce'},
    'Collected':        set(),
    'Bounced':          {'redeposit', 'return_to_customer', 'settle'},
    'Returned':         set(),
    'Settled':          set(),
    # CHQ-4: الورقة المظهَّرة ترتدّ في الواقع — البنك يرفضها بيد المورد، فيعود
    # الدين علينا للمورد ويعود على العميل الساحب. كانت `Endorsed` نهائيةً بلا
    # مخرج، فحدثٌ يقع فعلاً لا سبيل لتسجيله: تظلّ ذمّة المورد منخفضة بورقةٍ لم
    # تُصرف، ويظلّ العميل بريئاً من دينٍ لم يُسدَّد.
    'Endorsed':         {'bounce'},
    'Cancelled':        set(),
}

OUTGOING_TRANSITIONS = {
    # لا `deposit` ولا `endorse` ولا `redeposit` للصادر — ورقةٌ نحن كتبناها.
    'Draft':            {'withdraw'},
    # `Received` حالة وارد لا تُبلَغ من الصادر؛ الصفّ موجود صراحةً كي لا يصير
    # شيكٌ وصلها باستيراد أو بمسار مستقبلي عالقاً بلا مخرج ولا رسالة تفسّر.
    'Received':         set(),
    'Under_Collection': {'collect', 'withdraw', 'bounce', 'cancel'},
    'Collected':        set(),
    'Bounced':          {'return_to_customer', 'settle'},
    'Returned':         set(),
    'Settled':          set(),
    'Endorsed':         set(),
    'Cancelled':        set(),
}


def transitions_for(direction: str) -> dict:
    """جدول انتقالات الاتجاه — المدخل الوحيد للخدمات والواجهة والاختبارات."""
    return OUTGOING_TRANSITIONS if direction == 'Outgoing' else INCOMING_TRANSITIONS


def allowed_movements(cheque) -> set:
    """الحركات المسموحة على هذا الشيك الآن — بحالته واتجاهه."""
    return set(transitions_for(cheque.direction).get(cheque.status, set()))


STATUS_MAP = {
    'receive':            'Received',
    'deposit':            'Under_Collection',
    'redeposit':          'Under_Collection',
    'withdraw':           'Collected',
    'collect':            'Collected',
    'endorse':            'Endorsed',
    'bounce':             'Bounced',
    'return_to_customer': 'Returned',
    'cancel':             'Cancelled',
    'settle':             'Settled',
}


# ── CHQ-3: تسميات الحالات والحركات — بدلالة الاتجاه، ومن الخادم وحده ──────
#
# الواجهة كانت تحمل نسختها من الجدول والتسميات (`CHEQUE_MOVES` و
# `CHEQUE_STATUSES` في `AccountingChequesPage.tsx`)، فحالةٌ جديدة في الخادم لا
# تظهر هناك، وحركةٌ مُنعت هنا تبقى زرّاً يعطي 400. المصدر الآن واحد: هذه
# الجداول تسافر في الـserializer مع كل شيك.
#
# الرمز واحد في القاعدة والدلالة تختلف بالاتجاه: `Collected` للوارد «محصَّل»
# (دخل المال) وللصادر «مصروف» (خرج المال) — والقارئ كان يرى «محصَّل» على ورقة
# تخرج من حسابه.

_STATUS_LABELS_BY_DIRECTION = {
    'Incoming': {
        'Draft':            'مسودة',
        'Received':         'مستلَم — في المحفظة',
        'Under_Collection': 'برسم التحصيل',
        'Collected':        'محصَّل',
        'Bounced':          'مرتدّ',
        'Returned':         'مُعاد للعميل',
        'Settled':          'مسوّى نقداً',
        'Endorsed':         'مظهَّر لطرف ثالث',
        'Cancelled':        'ملغى',
    },
    'Outgoing': {
        'Draft':            'محرَّر',
        'Received':         'مستلَم',
        'Under_Collection': 'مسلَّم — بانتظار الصرف',
        'Collected':        'مصروف',
        'Bounced':          'مرتدّ',
        'Returned':         'مسترجَع من المورد',
        'Settled':          'مسوّى نقداً',
        'Endorsed':         'مظهَّر لطرف ثالث',
        'Cancelled':        'ملغى',
    },
}

#: التسمية المحايدة حين لا يكون للاتجاه دلالة خاصة بالحركة.
_MOVEMENT_LABELS_COMMON = {
    'receive':            'استلام ضمن سند القبض',
    'issue':              'تسليم الشيك للمورد',
    'revert':             'إلغاء ترحيل السند',
    'deposit':            'إيداع',
    'redeposit':          'إعادة إيداع',
    'withdraw':           'صرف',
    'collect':            'تحصيل',
    'endorse':            'تظهير',
    'bounce':             'ارتداد',
    'return_to_customer': 'إرجاع',
    'cancel':             'إلغاء',
    'settle':             'تسوية نقدية',
}

_MOVEMENT_LABELS_BY_DIRECTION = {
    'Incoming': {
        'deposit':            'إيداع للتحصيل (بنك)',
        'redeposit':          'إعادة إيداع بعد الارتداد',
        'withdraw':           'تحصيل مباشر',
        'collect':            'تحصيل — دخل الصندوق/البنك',
        'endorse':            'تظهير لطرف ثالث',
        'bounce':             'ارتداد — إعادة الذمم على العميل',
        'return_to_customer': 'إعادة الورقة للعميل',
        'settle':             'تسوية نقدية من العميل',
    },
    'Outgoing': {
        'withdraw':           'صرف مباشر من حسابنا',
        'collect':            'صُرف من حسابنا — إغلاق الالتزام',
        'bounce':             'ارتداد — عاد الدين على المورد',
        'return_to_customer': 'استرجاع الورقة من المورد',
        'cancel':             'إلغاء الشيك — إيقافه قبل صرفه',
        'settle':             'تسوية نقدية للمورد',
    },
}

#: الحركات التي يحلّ قيدُها طرفاً نقدياً (`_resolve_cheque_cash_account` في
#: `_cheque_movement_gl`) — فالواجهة تسأل عن الحساب البنكي قبل الإرسال بدل أن
#: تكتشفه من رسالة خطأ. تُشتق من القيد نفسه؛ أي تغيير هناك يُصحَّح هنا.
CHEQUE_MOVEMENTS_NEEDING_CASH_ACCOUNT = frozenset({'collect', 'withdraw', 'settle'})

#: CHQ-4: الإيداع يقصد بنكاً بعينه ولو لم يقصد حساباً آخر في القيد. قيده يبقى
#: 1107 ÷ 1109 (حسابٌ واحد للشيكات برسم التحصيل بقرار المالك — نهج Odoo بلا
#: تضخيم الشجرة)، لكن **أي بنك** أُودعت فيه الورقة حقيقةٌ تشغيلية: بدونها لا
#: يُعرف أين يُطالَب بالشيك، ولا يُقترح بنك التحصيل لاحقاً، ولا تُطبع قسيمة
#: إيداع. فالبنك وصفيٌّ على الشيك لا في القيد — ومطلوبٌ متى كان للشركة بنوك.
CHEQUE_MOVEMENTS_NEEDING_BANK_ACCOUNT = frozenset({'deposit'})


def tenant_has_active_bank_accounts(tenant_id: int) -> bool:
    """هل للشركة حساب بنكي نشط؟ — شرط إلزام البنك عند الإيداع.

    شركةٌ لم تسجّل بنوكها بعد تودع «ورقياً» كما كانت؛ إلزامها بحقلٍ لا خيارات
    فيه يوقف عملها. تُحسب مرة واحدة للطلب وتُحقن في السيريالايزر (لا استعلام
    لكل صفّ في القائمة).
    """
    from .models import BankAccount
    return BankAccount.objects.filter(
        tenant_id=tenant_id, is_active=True).exists()

#: ترتيب عرض الحركات — ترتيب دورة حياة الورقة، لا الأبجدية.
_MOVEMENT_ORDER = tuple(STATUS_MAP)


def status_label(direction: str, status: str) -> str:
    """تسمية الحالة بدلالة الاتجاه — مصدر واحد للواجهة والتقارير."""
    table = _STATUS_LABELS_BY_DIRECTION.get(
        direction, _STATUS_LABELS_BY_DIRECTION['Incoming'])
    return table.get(status, status)


def movement_label(direction: str, movement_type: str) -> str:
    """تسمية الحركة بدلالة الاتجاه، وإلا المحايدة، وإلا الرمز نفسه."""
    specific = _MOVEMENT_LABELS_BY_DIRECTION.get(direction, {})
    return (specific.get(movement_type)
            or _MOVEMENT_LABELS_COMMON.get(movement_type)
            or movement_type)


def allowed_movement_options(cheque, *, has_active_bank_accounts=None) -> list:
    """الحركات المتاحة الآن جاهزةً للعرض: الرمز، تسميته، وما يلزمها من مدخلات.

    CHQ-4: ورقةٌ سندُها غير مرحّل لا حركة لها إطلاقاً — `transfer_cheque` يرفضها
    كلها (حارس «رحّل السند أولاً»). كانت تُعرض ثلاث حركات محكومٌ عليها بالـ400،
    فيقف المستخدم أمام قائمة كاذبة بلا مخرج. الجدولان والحارس ينطقان هنا بلسان
    واحد، و`needs_document_post` في السيريالايزر هو الذي يشرح الصمت.
    """
    if cheque_document_is_posted(cheque) is False:
        return []
    moves = allowed_movements(cheque)
    ordered = [m for m in _MOVEMENT_ORDER if m in moves]
    if has_active_bank_accounts is None and (
            CHEQUE_MOVEMENTS_NEEDING_BANK_ACCOUNT & set(ordered)):
        has_active_bank_accounts = tenant_has_active_bank_accounts(cheque.tenant_id)
    return [{
        'value': move,
        'label': movement_label(cheque.direction, move),
        'requires_bank_account': (
            move in CHEQUE_MOVEMENTS_NEEDING_CASH_ACCOUNT
            or (move in CHEQUE_MOVEMENTS_NEEDING_BANK_ACCOUNT
                and bool(has_active_bank_accounts))
        ),
        'requires_endorsee': move == 'endorse',
    } for move in ordered]


# T-DEFACC: أكواد الصندوق/البنك في الشجرة المعيارية — 1101 النقدية، 1102 البنوك،
# 1110 صناديق النقدية. تُستعمل حين تكون الإعدادات فارغة كي لا يبقى أي مستند بلا صندوق.
#
# T-CASHBOX M1 — **هذه عُقَد مجمّعة لا صناديق**: المطابقة هنا تامّة (`code=`)،
# و«1110 صناديق النقدية» أبُ الصناديق لا صندوق؛ الصندوق الفعلي كوده `1110B0001`.
# فبنيوياً لم تكن هذه السلسلة تُعيد صندوقاً حقيقياً أبداً: شركةٌ بعشرة صناديق
# كانت كل سنداتها تقع على «1101 النقدية» العامّ. لذلك تسبقها الآن خطوة الصندوق
# المسجَّل، وبقيت هي آخر شبكة أمان لشجرةٍ بلا صناديق مسجَّلة.
DEFAULT_CASH_ACCOUNT_CODES = ("1101", "1102", "1110")


def _without_partner_accounts(qs, tenant_id: int):
    """يُسقط حسابات الأطراف من مرشّحي الصندوق — الذمّة ليست نقداً.

    المطابقة بالاسم (`صندوق`/`نقد`/`بنك`) هي الخطوة الوحيدة التي **تخمّن**،
    والاسم ليس ملكاً للشركة وحدها: `accounting/api.py` (`sync_partner_accounting`)
    يسمّي حساب الطرف باسم صاحبه ويعيد تسميته معه. فزبونٌ اسمه «صندوق التوفير»
    أو مورّدٌ اسمه «بنك فلسطين» يصنع في الشجرة حساباً يطابق التخمين حرفاً بحرف.
    اختيارهُ صندوقاً يُنتج قيداً يدين ويدائن الحساب نفسه — **متوازناً**، فلا
    ميزانٌ ولا مطابقةٌ تكشفه: مالٌ خاطئ صامت.

    الاستبعاد بمصدرَين لأن أيّاً منهما وحده يثقب: التصنيف المخزَّن (`sub_type`)
    يفوت شجرةً قديمةً لم تُصنَّف، ورابط الطرف يفوت حساباً قُطع رابطه وبقي في
    الشجرة باسم صاحبه.

    دالّةٌ لا سطرٌ مكرَّر لأن لها مستعملَين: هذا السلّم (مسار المال) و
    `core/reports/treasury.py` (`_cash_movements`) (مسار العرض). ونسختان من
    قاعدةٍ واحدة تفترقان عند أول تعديل يُنسى في إحداهما.
    """
    from .account_classification import SUB_TYPE_PAYABLE, SUB_TYPE_RECEIVABLE

    return qs.exclude(
        sub_type__in=(SUB_TYPE_RECEIVABLE, SUB_TYPE_PAYABLE),
    ).exclude(
        id__in=Partner.objects.filter(
            tenant_id=tenant_id, linked_account_id__isnull=False,
        ).values("linked_account_id"),
    )


def _default_cash_box_link(tenant_id: int, *, currency_code: str | None = None):
    """صندوق الشركة الافتراضي: المُعلَن `is_default` ← مطابق العملة ← أوّل نشط."""
    from .models import CashBoxLedgerAccount

    base = (
        CashBoxLedgerAccount.objects
        .filter(tenant_id=tenant_id, is_active=True, account__is_active=True)
        .select_related("account")
    )
    if currency_code:
        matching = base.filter(currency_code__iexact=currency_code)
        return (
            matching.filter(is_default=True).first()
            or matching.order_by("id").first()
            or base.filter(is_default=True).first()
            or base.order_by("id").first()
        )
    return base.filter(is_default=True).first() or base.order_by("id").first()


def resolve_cash_account(tenant_id: int, *, explicit_account_id=None, user=None,
                         currency_code: str | None = None, required: bool = True):
    """سلّم حلّ حساب الصندوق/البنك — **المصدر الواحد لكل المستندات**.

    T-CASHBOX M3: كان في النظام محلّان لا يتحادثان (`resolve_default_cash_account`
    للمستندات، و`accounting/cashbox.py` (`resolve_default_cash_box_account`)
    لدفعات الاستيراد) وثالثٌ ضمنيّ في الواجهة يلتقط «أوّل حساب نقدي في الشجرة».
    الترتيب الآن واحد لا ثالث له:

    الاختيار الصريح ← صندوق المستخدم الافتراضي ← صندوق الشركة الافتراضي ←
    إعدادات المبيعات/الشراء ← الشجرة المعيارية (شبكة أمان) ← خطأ إرشادي.

    و«أوّل حساب نقدي» ليست خطوةً هنا ولا في أي مكان: ترتيبُ الشجرة ليس نيّةَ
    مستخدم، ومنه جاءت شكوى «الدفع دائماً من صندوق الشيقل».
    """
    if explicit_account_id:
        acc = Account.objects.filter(
            pk=explicit_account_id, tenant_id=tenant_id, is_active=True,
        ).first()
        if not acc:
            raise ValidationError(
                "حساب الصندوق/البنك المحدد غير موجود أو لا يتبع هذه الشركة."
            )
        return acc

    if user is not None and getattr(user, "is_authenticated", False):
        from .models import CashBoxUserDefault

        pref = (
            CashBoxUserDefault.objects
            .filter(tenant_id=tenant_id, user=user,
                    cash_box__is_active=True, cash_box__account__is_active=True)
            .select_related("cash_box__account")
            .first()
        )
        # تفضيل المستخدم يُتخطّى إن خالف عملة المستند — صندوقٌ بعملة أخرى
        # اختيارٌ خاطئ صامت، والسلّم يكمل إلى ما يطابق.
        if pref and (
            not currency_code
            or (pref.cash_box.currency_code or "").upper() == currency_code.upper()
        ):
            return pref.cash_box.account

    link = _default_cash_box_link(tenant_id, currency_code=currency_code)
    if link is not None:
        return link.account

    from sales.models import SalesSettings
    from logistics.models import PurchaseSettings

    ss = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if ss and ss.default_cash_account_id:
        return ss.default_cash_account
    ps = PurchaseSettings.objects.filter(tenant_id=tenant_id).first()
    if ps and ps.default_cash_account_id:
        return ps.default_cash_account

    from django.db.models import Q

    base = Account.objects.filter(
        tenant_id=tenant_id, account_type="Asset", is_active=True,
    )
    for code in DEFAULT_CASH_ACCOUNT_CODES:
        hit = base.filter(code=code).first()
        if hit:
            return hit
    # الشبكة الأخيرة تقرأ الاسم — ولا تُقرأ أسماء الأطراف معها
    # (`_without_partner_accounts`).
    fallback = (
        _without_partner_accounts(base, tenant_id)
        .filter(
            Q(name__icontains="صندوق") | Q(name__icontains="نقد") | Q(name__icontains="بنك")
        )
        .order_by("code")
        .first()
    )
    if fallback is None and required:
        raise ValidationError(
            "لا يوجد صندوق أو حساب بنكي في هذه الشركة. أنشئ صندوقاً من شاشة "
            "«صناديق الكاش»، أو عيّن الصندوق الافتراضي في إعدادات المبيعات."
        )
    return fallback


def resolve_default_cash_account(tenant_id: int):
    """حساب الصندوق/البنك الافتراضي للشركة — غلافٌ متوافق فوق `resolve_cash_account`.

    يبقى لأن له مستدعين كثراً يتوقّعون `None` لا استثناءً عند الشجرة الفارغة.
    الكود الجديد ينادي `resolve_cash_account` مباشرةً ليمرّر المستخدم والعملة.
    """
    return resolve_cash_account(tenant_id, required=False)


#: CHQ-1 — كودا حسابَي الشيكات الواردة. 1109 لا 1108: **1108 مأخوذ إنتاجياً**
#: لحساب «بضاعة مسلَّمة لم تُفوتَر» الذي يُنشئه
#: `sales/services/flow.py` (`resolve_goods_delivered_unbilled_account`) تلقائياً
#: لأي شركة سلّمت بضاعة قبل فوترتها.
CHEQUES_UNDER_COLLECTION_CODE = "1107"
CHEQUES_IN_HAND_CODE = "1109"


def _resolve_cheque_under_collection_account(tenant_id: int):
    """حساب «شيكات برسم التحصيل» (1107) — الورقة في البنك بانتظار التحصيل.

    task13 M2: البحث القديم بـ code__startswith="1106" كان يلتقط
    «دفعات مقدمة للموردين» في الشجرة المعيارية ⇒ ترحيل خاطئ.

    CHQ-1: بدخول حساب «شيكات في المحفظة» صار في الشجرة حسابا أصلٍ اسم كليهما
    يحوي «شيكات»، فمطابقةُ الاسم المفتوحة صارت خطراً صامتاً: قيد الإيداع
    (1107 ÷ 1109) قد يقع بطرفيه على الحساب نفسه، **فيتوازن** ولا تكشفه أي
    موازنة ولا أي تأكيد رصيد. لذلك: الإعدادات ← الكود 1107 بالضبط ← مطابقة اسم
    **تستثني حساب المحفظة صراحةً** (للشجرات القديمة غير المعيارية) ← خطأ صريح.
    لا يُعاد None أبداً — المستدعي كان يترجمه إلى رسالة عامة.
    """
    from sales.models import SalesSettings
    ss = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if ss and ss.default_cheques_under_collection_account_id:
        return ss.default_cheques_under_collection_account
    base = Account.objects.filter(tenant_id=tenant_id, account_type="Asset", is_active=True)
    acc = (
        base.filter(code=CHEQUES_UNDER_COLLECTION_CODE).first()
        or base.filter(name__icontains="شيكات")
              .exclude(code=CHEQUES_IN_HAND_CODE)
              .exclude(name__icontains="المحفظة")
              .exclude(name__icontains="in hand")
              .order_by("code").first()
    )
    if acc is None:
        # CHQ-4: تباينٌ كان يوقف المستخدم في منتصف الدورة — مسار ترحيل السند
        # يُنشئ 1107 تلقائياً (`sales/services/calc.py`)، ومسار حركة الشيك كان
        # يرمي. فشركةٌ بلا 1107 تُرحّل سندها بنجاح ثم يفشل أول إيداع بلا مخرج
        # من الشاشة. المسارَان الآن ينشئان الحساب نفسه من الشجرة المعيارية.
        from tenants.models import Tenant
        from tenants.services import ensure_operational_account

        tenant = Tenant.objects.filter(pk=tenant_id).first()
        acc = ensure_operational_account(
            tenant, CHEQUES_UNDER_COLLECTION_CODE) if tenant else None
    if acc is None:
        raise ValidationError(
            "لا يوجد حساب «شيكات برسم التحصيل» (1107) في شجرة هذه الشركة. "
            "أنشئه أو عيّنه في إعدادات المبيعات قبل تحريك الشيك."
        )
    return acc


def _resolve_cheque_in_hand_account(tenant_id: int):
    """حساب «شيكات في المحفظة» (1109) — الورقة في اليد، لم تُودَع بعد.

    CHQ-1: الحاسم الذي يجعل «قيد الإيداع» ممكناً (1107 ÷ 1109) كما في دفترة
    والأصيل. **صريحٌ عمداً**: الإعدادات ← الكود 1109 بالضبط ← إنشاؤه من الشجرة
    المعيارية. لا مطابقة بالاسم إطلاقاً — «شيكات برسم التحصيل» يحوي الكلمة
    نفسها، ومطابقةٌ خاطئة هنا تنتج قيداً متوازناً على حساب واحد لا يكشفه شيء.
    """
    from sales.models import SalesSettings
    from tenants.models import Tenant
    from tenants.services import ensure_operational_account

    ss = SalesSettings.objects.filter(tenant_id=tenant_id).first()
    if ss and ss.default_cheques_in_hand_account_id:
        return ss.default_cheques_in_hand_account
    acc = Account.objects.filter(
        tenant_id=tenant_id, code=CHEQUES_IN_HAND_CODE, is_active=True,
    ).first()
    if acc is None:
        # الشركات المبذورة قبل CHQ-1 لا تحمله — يُنشأ من الشجرة المعيارية بدل
        # ردّ المستخدم وهو يودع شيكاً (نفس نهج 2111 في `resolve_cheques_payable_account`).
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        acc = ensure_operational_account(tenant, CHEQUES_IN_HAND_CODE) if tenant else None
    if acc is None:
        raise ValidationError(
            "تعذّر تحديد حساب «شيكات في المحفظة» (1109) — أنشئه في شجرة "
            "الحسابات أو عيّنه في إعدادات المبيعات."
        )
    return acc


def _resolve_incoming_cheque_asset_account(cheque):
    """أي حساب أصلٍ تجلس عليه هذه الورقة **الآن** — قبل الحركة.

    الحالة هي المميِّز، لا نوع الحركة: `Received` ⇒ المحفظة (1109)، وما عداها
    ⇒ برسم التحصيل (1107). هكذا يكمل الشيك القديم مساره القديم حرفياً بينما
    يمشي الجديد على المسار الجديد، بلا ترحيل بيانات ولا قيد يُعاد كتابته.
    """
    if cheque.status == 'Received':
        return _resolve_cheque_in_hand_account(cheque.tenant_id)
    return _resolve_cheque_under_collection_account(cheque.tenant_id)


def _resolve_cheque_cash_account(tenant_id: int, account_id=None):
    """حساب الصندوق/البنك لوجهة التحصيل — صريح أو افتراضي الإعدادات."""
    if account_id:
        acc = Account.objects.filter(pk=account_id, tenant_id=tenant_id, is_active=True).first()
        if not acc:
            raise ValidationError("حساب الصندوق/البنك المحدد غير موجود أو لا يتبع هذه الشركة.")
        return acc
    acc = resolve_default_cash_account(tenant_id)
    if acc:
        return acc
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


def _resolve_cheque_payable_account(tenant_id: int):
    """T-CHQ2: حساب «شيكات برسم الدفع» — مصدر واحد مع ترحيل سند الصرف."""
    from sales.services import resolve_cheques_payable_account
    return resolve_cheques_payable_account(tenant_id)


def _resolve_cheque_supplier_account(cheque):
    """T-CHQ2: حساب ذمم المورد لارتداد/تسوية شيك صادر — مرآة حساب العميل."""
    from logistics.services import _resolve_ap_account
    partner = cheque.partner or (
        cheque.supplier_payment.partner if cheque.supplier_payment_id else None
    )
    if partner is None:
        raise ValidationError("الشيك الصادر بلا مورد مرتبط — لا يمكن تحديد حساب الذمم.")
    return _resolve_ap_account(partner), partner


def _resolve_cheque_endorsee_account(cheque):
    """CHQ-1: حساب ذمم المستفيد من التظهير — مرآة حساب المورد في السداد النقدي."""
    from logistics.services import _resolve_ap_account
    partner = cheque.endorsed_to
    if partner is None:
        raise ValidationError(
            "التظهير يحتاج الطرف المستفيد — حدّد المورد الذي ظُهِّر له الشيك."
        )
    if partner.tenant_id != cheque.tenant_id:
        raise ValidationError("الطرف المستفيد لا يتبع هذه الشركة.")
    return _resolve_ap_account(partner), partner


def cheque_is_linked_to_document(cheque) -> bool:
    """الشيك داخل الدفاتر عبر سند قبض/صرف أو فاتورة — قيده مُرحَّل من هناك.

    T-CHQ3: لا يوجد مسار ترحيل خاص بالشيك: الورقة تدخل الدفاتر ضمن سندها
    (أو فاتورتها) كما في الأنظمة المهنية، فما يُرحَّل هنا حركاتها لاحقاً فقط.
    """
    if cheque.direction == 'Outgoing':
        return bool(cheque.supplier_payment_id or cheque.purchase_invoice_id)
    return bool(cheque.sales_invoice_id or cheque.customer_payment_id)


def cheque_document_is_posted(cheque):
    """هل رُحِّل المستندُ الذي دخل الشيك الدفاتر ضمنه؟

    CHQ-1: `cheque_is_linked_to_document` يفحص وجود الـFK لا الترحيل، فشيكٌ
    داخل سند **لم يُرحَّل** كان يُحصَّل بقيد يدائن 1107 الذي لم يُدَّن أصلاً ⇒
    الحساب يصير سالباً والعميل يبقى مديناً رغم دخول النقد. يعيد None حين لا
    مستند أصلاً (شيك legacy يتيم — مساره القديم كما هو).
    """
    if cheque.direction == 'Outgoing':
        if cheque.supplier_payment_id:
            return bool(cheque.supplier_payment.is_posted)
        if cheque.purchase_invoice_id:
            return bool(cheque.purchase_invoice.is_posted)
        return None
    if cheque.customer_payment_id:
        return bool(cheque.customer_payment.is_posted)
    if cheque.sales_invoice_id:
        from sales.models import SalesInvoice
        return cheque.sales_invoice.status == SalesInvoice.STATUS_POSTED
    return None


#: المستند الذي دخل الشيك الدفاتر ضمنه، مرتَّباً بأولوية الدقّة لكل اتجاه:
#: السند أدقّ من الفاتورة (الشيك يُسجَّل داخله)، فيتصدّر حين يوجد الاثنان.
_CHEQUE_SOURCE_DOCUMENTS = {
    'Incoming': (
        ('customer_payment', 'سند قبض'),
        ('sales_invoice', 'فاتورة مبيعات'),
    ),
    'Outgoing': (
        ('supplier_payment', 'سند صرف'),
        ('purchase_invoice', 'فاتورة شراء'),
    ),
}


def cheque_source_document(cheque) -> dict | None:
    """CHQ-4: المستند المصدر للشيك — نوعه ومعرّفه ورقمه وهل رُحِّل.

    شاشة الشيكات كانت طريقاً مسدوداً: ورقةٌ سندُها مسودة تُعرض لها حركات يرفضها
    `transfer_cheque` حتماً، ولا شيء في الصفّ يقول أين السند ولا كيف يُرحَّل.
    هذا الحقل هو الخيط الذي يجعل الخروج ممكناً — والشاشة تبني عليه زر «ترحيل
    السند» ورابط المستند. يعيد None لورقةٍ يتيمة (legacy) فيبقى مسارها كما هو.
    """
    for field, label in _CHEQUE_SOURCE_DOCUMENTS.get(cheque.direction, ()):
        if getattr(cheque, f"{field}_id", None) is None:
            continue
        doc = getattr(cheque, field)
        number = (
            getattr(doc, 'invoice_number', None)
            or getattr(doc, 'payment_number', None)
            or f"#{doc.pk}"
        )
        return {
            'type': field,
            'label': label,
            'id': doc.pk,
            'number': number,
            'is_posted': bool(cheque_document_is_posted(cheque)),
        }
    return None


def _cheque_movement_gl(cheque, movement_type, account_id=None):
    """طرفا قيد حركة الشيك ووصفه — مصدر واحد لـ`transfer_cheque` وللترحيل الرجعي.

    يُرجع (مدين، دائن، شريك المدين، شريك الدائن، الوصف).
    الشريك يُحمَّل على سطر الذمم وحده. كان يُحمَّل على السطرين، فسطرا الارتداد
    (ذمم + شيكات برسم التحصيل) يتعادلان داخل كشف العميل فلا يعود الدين يظهر
    عليه بعد ارتداد شيكه (نفس عطل task32).
    """
    dr_partner_id = cr_partner_id = None
    if cheque.direction == 'Outgoing':
        payable = _resolve_cheque_payable_account(cheque.tenant_id)
        if movement_type in ('collect', 'withdraw'):
            cash = _resolve_cheque_cash_account(cheque.tenant_id, account_id)
            dr, cr = payable, cash
            desc = f"صرف شيك صادر {cheque.cheque_number}"
        elif movement_type in ('bounce', 'cancel'):
            # CHQ-1: الإلغاء والارتداد يتشاركان القيد (الالتزام يسقط والدين
            # يعود للمورد) ويفترقان في الدلالة والسجل: الارتداد رفضٌ من البنك،
            # والإلغاء إيقافٌ منّا قبل الصرف.
            ap, partner = _resolve_cheque_supplier_account(cheque)
            dr, cr = payable, ap
            desc = (
                f"ارتداد شيك صادر {cheque.cheque_number} — إعادة الذمم للمورد"
                if movement_type == 'bounce' else
                f"إلغاء شيك صادر {cheque.cheque_number} — إعادة الذمم للمورد"
            )
            cr_partner_id = partner.pk
        else:  # settle
            ap, partner = _resolve_cheque_supplier_account(cheque)
            cash = _resolve_cheque_cash_account(cheque.tenant_id, account_id)
            dr, cr = ap, cash
            desc = f"تسوية شيك صادر مرتد {cheque.cheque_number}"
            dr_partner_id = partner.pk
    elif movement_type == 'deposit':
        # CHQ-1 — قيد الإيداع الذي طلبه المالك: الورقة تغادر المحفظة إلى البنك
        # قبل تحصيلها الفعلي. مسموح من `Received` وحدها (الإيداع من `Draft`
        # يبقى حركة ورقية بلا قيد كما كان — المسار legacy).
        uc = _resolve_cheque_under_collection_account(cheque.tenant_id)
        in_hand = _resolve_cheque_in_hand_account(cheque.tenant_id)
        dr, cr = uc, in_hand
        desc = f"إيداع شيك {cheque.cheque_number} برسم التحصيل"
    elif movement_type == 'redeposit':
        # إعادة إيداع شيك مرتد — عكس قيد الارتداد بالضبط: الذمّة تعود على
        # العميل مرة أخرى والورقة تعود إلى البنك.
        uc = _resolve_cheque_under_collection_account(cheque.tenant_id)
        ar, partner = _resolve_cheque_ar_account(cheque)
        dr, cr = uc, ar
        desc = f"إعادة إيداع شيك مرتد {cheque.cheque_number}"
        cr_partner_id = partner.pk
    elif movement_type == 'endorse':
        in_hand = _resolve_cheque_in_hand_account(cheque.tenant_id)
        ap, partner = _resolve_cheque_endorsee_account(cheque)
        dr, cr = ap, in_hand
        desc = f"تظهير شيك {cheque.cheque_number} إلى {partner.name}"
        dr_partner_id = partner.pk
    elif movement_type in ('collect', 'withdraw'):
        asset = _resolve_incoming_cheque_asset_account(cheque)
        cash = _resolve_cheque_cash_account(cheque.tenant_id, account_id)
        dr, cr = cash, asset
        desc = f"تحصيل شيك {cheque.cheque_number}"
    elif movement_type == 'bounce' and cheque.status == 'Endorsed':
        # CHQ-4: ارتداد ورقةٍ ظُهِّرت لمورد. الورقة لم تكن في 1107 ولا في 1109
        # (خرجت من المحفظة يوم التظهير)، فالقيد بين ذمّتين: دَينُ المورد يعود
        # كما كان (عكس قيد التظهير) والعميل الساحب يعود مديناً. الحالة المصدر
        # هي المميِّز — `_cheque_movement_gl` يُستدعى قبل تغييرها عمداً.
        ar, customer = _resolve_cheque_ar_account(cheque)
        ap, endorsee = _resolve_cheque_endorsee_account(cheque)
        dr, cr = ar, ap
        desc = (
            f"ارتداد شيك مظهَّر {cheque.cheque_number} — "
            f"الدين يعود على {customer.name} وعلى ذمّة {endorsee.name}"
        )
        dr_partner_id = customer.pk
        cr_partner_id = endorsee.pk
    elif movement_type == 'bounce':
        uc = _resolve_cheque_under_collection_account(cheque.tenant_id)
        ar, partner = _resolve_cheque_ar_account(cheque)
        dr, cr = ar, uc
        desc = f"ارتداد شيك {cheque.cheque_number} — إعادة الذمم على العميل"
        dr_partner_id = partner.pk
    elif movement_type == 'return_to_customer':
        # إرجاع الورقة قبل إيداعها — من `Received` وحدها له قيد (المحفظة
        # تُفرَّغ والذمّة تعود). الإرجاع بعد الارتداد بلا قيد كما كان: قيد
        # الارتداد أعاد الذمّة أصلاً.
        in_hand = _resolve_cheque_in_hand_account(cheque.tenant_id)
        ar, partner = _resolve_cheque_ar_account(cheque)
        dr, cr = ar, in_hand
        desc = f"إرجاع شيك {cheque.cheque_number} للعميل قبل إيداعه"
        dr_partner_id = partner.pk
    else:  # settle
        ar, partner = _resolve_cheque_ar_account(cheque)
        cash = _resolve_cheque_cash_account(cheque.tenant_id, account_id)
        dr, cr = cash, ar
        desc = f"تسوية شيك مرتد {cheque.cheque_number}"
        cr_partner_id = partner.pk
    return dr, cr, dr_partner_id, cr_partner_id, desc


def post_cheque_movement_journal(cheque, movement_type, *, when, movement_id,
                                 user=None, account_id=None, branch_id=None):
    """ترحيل قيد حركة شيك واحدة — Idempotent عبر (CHEQUE_<MOVE>, movement_id).

    CHQ-1: كان المفتاح `(CHEQUE_<MOVE>, cheque_id)` — أي حركةٌ واحدة من كل نوع
    لكل شيك مدى حياته. فارتدادٌ ثانٍ بعد إعادة إيداع كان يجد قيد الارتداد
    الأول ويعيده صامتاً: الذمّة تعود مرة واحدة والمرة الثانية تضيع. المفتاح
    الآن الحركةُ نفسها — كل حدث قيده. القيود القديمة لا تُمسّ (تحمل
    `reference_id=cheque_id` وتبقى كما هي)؛ التغيير للأمام فقط.
    """
    amount = Decimal(str(cheque.amount or 0)).quantize(Decimal("0.01"))
    dr, cr, dr_partner_id, cr_partner_id, desc = _cheque_movement_gl(
        cheque, movement_type, account_id)
    return post_journal(
        tenant_id=cheque.tenant_id,
        transaction_date=when,
        reference_type=f"CHEQUE_{movement_type.upper()}",
        reference_id=movement_id,
        description=desc,
        lines_data=[
            {"account": dr.pk, "partner": dr_partner_id,
             "debit": amount, "credit": Decimal("0"), "description": desc},
            {"account": cr.pk, "partner": cr_partner_id,
             "debit": Decimal("0"), "credit": amount, "description": desc},
        ],
        currency=cheque.currency,
        user=user,
        branch_id=branch_id,
    )


#: CHQ-1 — الحركات التي لها قيدٌ دائماً أياً كانت الحالة المصدر.
_CHEQUE_GL_MOVEMENTS = frozenset({
    'collect', 'withdraw', 'bounce', 'settle', 'redeposit', 'endorse', 'cancel',
})
#: وحركتان قيدُهما مشروط بالحالة المصدر: من `Received` وحدها. من `Draft`
#: (شيك legacy يتيم) أو من `Bounced` تبقيان حركة ورقية بلا قيد كما كانتا.
_CHEQUE_GL_FROM_RECEIVED_ONLY = frozenset({'deposit', 'return_to_customer'})


def transfer_cheque(cheque_id, movement_type, *, user=None, notes='',
                    account_id=None, movement_date=None, bank_account_id=None,
                    endorsed_to_id=None):
    """task11 R2-A3 — تحويل حالة شيك مع القيد المحاسبي المرافق.

    كانت آلة الحالات بلا قيود محاسبية (والواجهة تتجاوزها أصلاً بـ PATCH خام)
    فتبقى المبالغ في «شيكات برسم التحصيل» للأبد. قيود الوارد الآن:
      - deposit (من Received) : مدين شيكات برسم التحصيل ÷ دائن شيكات في المحفظة
      - collect / withdraw    : مدين صندوق/بنك ÷ دائن حساب الورقة الحالي
      - bounce                : مدين ذمم العميل ÷ دائن شيكات برسم التحصيل
      - redeposit             : مدين شيكات برسم التحصيل ÷ دائن ذمم العميل
      - endorse               : مدين ذمم المستفيد ÷ دائن شيكات في المحفظة
      - return_to_customer (من Received) : مدين ذمم العميل ÷ دائن شيكات في المحفظة
      - settle                : مدين صندوق/بنك ÷ دائن ذمم العميل
      - deposit (من Draft) / return_to_customer (من Bounced) : بلا قيد

    T-CHQ2: الجانب الصادر مرآة كاملة — كان بلا قيد إطلاقاً، فيبقى التزام
    «شيكات برسم الدفع» في الميزانية حتى بعد أن يصرف المورد الشيك:
      - collect / withdraw : مدين شيكات برسم الدفع ÷ دائن صندوق/بنك
      - bounce / cancel    : مدين شيكات برسم الدفع ÷ دائن ذمم المورد
      - settle             : مدين ذمم المورد ÷ دائن صندوق/بنك

    يُرحَّل القيد فقط إذا كان الشيك داخل الدفاتر أصلاً (مربوط بفاتورة أو
    سند) — الشيكات المستقلة legacy تتحول حالتها فقط مع تحذير في اللوغ.
    Idempotent عبر (CHEQUE_<MOVE>, movement_id).
    """
    import datetime as _dt
    from .models import Cheque, ChequeMovement

    cheque = Cheque.objects.select_related(
        'tenant', 'partner', 'partner__group', 'sales_invoice', 'currency',
        'supplier_payment', 'supplier_payment__partner',
        'customer_payment', 'purchase_invoice', 'endorsed_to',
    ).get(pk=cheque_id)
    allowed = transitions_for(cheque.direction).get(cheque.status, set())
    if movement_type not in allowed:
        raise ValidationError(
            f"لا يمكن تنفيذ «{movement_type}» على شيك بحالة «{cheque.status}»."
        )
    next_status = STATUS_MAP[movement_type]

    # CHQ-1: لا حركة على ورقةٍ لم يدخل سندُها الدفاتر بعد. بدون هذا الحارس
    # يُحصَّل شيكٌ سندُه غير مرحّل فيُدائَن حسابُ الشيكات الذي لم يُدَّن قط ⇒
    # رصيده سالب والعميل يبقى مديناً رغم أن النقد وصل.
    if cheque_document_is_posted(cheque) is False:
        raise ValidationError(
            f"لا يمكن تحريك الشيك {cheque.cheque_number} قبل ترحيل السند/الفاتورة "
            "المرتبطة به — رحّل المستند أولاً ثم أعد المحاولة."
        )

    # CHQ-4: ورقةٌ مسودة **مربوطة بمستند** لا تُصرَف مباشرةً. حالة `Draft` تعني
    # أن الورقة لم تدخل الدفاتر بعد (لا 1109 مدين ولا 2111 دائن)، فقيدُ الصرف
    # يدائن/يدين حساباً لم يُقيَّد قط ⇒ رصيده سالب. تقع الحالة فعلاً حين يُرحَّل
    # المستند ولا يُكنَس شيكه إلى سند (مرتجع الشراء مثلاً — `logistics/services.py`
    # يتخطّى الكنس صراحةً)، فيبقى `Draft` والمستند مرحّل فيمرّ حارس السند أعلاه.
    # الورقة اليتيمة (legacy، بلا مستند) تكمل مسارها القديم حرفياً.
    if (cheque.status == 'Draft'
            and movement_type in _CHEQUE_GL_MOVEMENTS
            and cheque_is_linked_to_document(cheque)):
        raise ValidationError(
            f"الشيك {cheque.cheque_number} ما زال مسودةً داخل مستنده — لم يدخل "
            "الدفاتر بعد. رحّل المستند (أو أعِد ترحيله) فتُسجَّل الورقة، ثم "
            "حرّكها."
        )

    # CHQ-4: تاريخ الحركة كان يُمرَّر إلى `post_journal` كما وصل، بلا حارس إلا
    # الفترة المالية. فتحصيلٌ بتاريخ الغد يدخل الدفاتر، وتحصيلٌ بتاريخٍ أسبق من
    # إيداعه يجعل مسار الورقة يقرأ عكس ما حدث.
    if movement_date:
        today = timezone.localdate()
        as_date = movement_date
        if isinstance(as_date, str):
            as_date = _dt.date.fromisoformat(as_date)
        if as_date > today:
            raise ValidationError(
                "تاريخ الحركة في المستقبل — الشيكات تُسجَّل بما حدث لا بما سيحدث."
            )
        last_dated = (
            ChequeMovement.objects
            .filter(cheque=cheque, journal__isnull=False)
            .select_related('journal')
            .order_by('-id').first()
        )
        previous = last_dated.journal.transaction_date if last_dated else None
        if previous and as_date < previous:
            raise ValidationError(
                f"تاريخ الحركة ({as_date}) أسبق من آخر حركة مرحّلة على الشيك "
                f"({previous}) — مسار الورقة لا يعود إلى الوراء."
            )

    # CHQ-4: «أودعتُه في أي بنك؟» سؤالٌ لا جواب له في الدفاتر (القيد 1107 ÷ 1109
    # بحسابٍ واحد)، فلو لم يُسأل هنا لضاع إلى الأبد: لا مطالبة بالورقة، ولا
    # اقتراح لبنك التحصيل، ولا قسيمة إيداع. يُلزَم فقط حين للشركة بنوك مسجَّلة —
    # وإلا فالإلزام حقلٌ بلا خيارات يوقف العمل.
    if (movement_type in CHEQUE_MOVEMENTS_NEEDING_BANK_ACCOUNT
            and not bank_account_id
            and tenant_has_active_bank_accounts(cheque.tenant_id)):
        raise ValidationError(
            "حدّد الحساب البنكي الذي أُودع فيه الشيك — بدونه لا يُعرف أين "
            "الورقة ولا يمكن مطابقة كشف البنك."
        )

    # CHQ-1: التظهير يحتاج مستفيداً؛ يُقبل من الطلب أو من قيمة سابقة على الشيك.
    endorsee_changed = False
    if movement_type == 'endorse' and endorsed_to_id:
        from partners.models import Partner
        endorsee = Partner.objects.filter(
            pk=endorsed_to_id, tenant_id=cheque.tenant_id).first()
        if endorsee is None:
            raise ValidationError("الطرف المستفيد من التظهير غير موجود أو لا يتبع هذه الشركة.")
        if cheque.endorsed_to_id != endorsee.pk:
            cheque.endorsed_to = endorsee
            endorsee_changed = True
    when = movement_date or timezone.localdate()
    amount = Decimal(str(cheque.amount or 0)).quantize(Decimal("0.01"))

    # T-BANKS: وجهة الإيداع/الصرف حساب بنكي مسجَّل — حسابه في الشجرة هو
    # الطرف النقدي للقيد، ويُسجَّل على الشيك ليظهر في كشف البنك ومطابقته.
    deposit_account_changed = False
    if bank_account_id:
        from .models import BankAccount
        ba = (
            BankAccount.objects
            .filter(pk=bank_account_id, tenant_id=cheque.tenant_id, is_active=True)
            .select_related('account').first()
        )
        if ba is None:
            raise ValidationError("الحساب البنكي المحدد غير موجود أو لا يتبع هذه الشركة.")
        account_id = ba.account_id
        if cheque.deposit_bank_account_id != ba.pk:
            cheque.deposit_bank_account = ba
            deposit_account_changed = True

    # GL يخص الشيكات المسجَّلة دفترياً فقط — كل اتجاه ومستنداته.
    in_books = cheque_is_linked_to_document(cheque)
    needs_gl = amount > 0 and (
        movement_type in _CHEQUE_GL_MOVEMENTS
        or (movement_type in _CHEQUE_GL_FROM_RECEIVED_ONLY
            and cheque.status == 'Received')
    )
    if needs_gl and not in_books:
        logging.getLogger(__name__).warning(
            "transfer_cheque: cheque %s has no invoice/payment link — status-only transfer",
            cheque.pk,
        )
        needs_gl = False

    journal = None
    with transaction.atomic():
        # CHQ-1: الحركة تُكتب أولاً لأن مفتاح الـidempotency صار مفتاحها —
        # وقيدها يُرحَّل قبل تغيير الحالة، فـ`_cheque_movement_gl` يقرأ الحالة
        # المصدر (هي التي تحسم: المحفظة 1109 أم برسم التحصيل 1107).
        movement = ChequeMovement.objects.create(
            cheque=cheque,
            movement_type=movement_type,
            notes=notes,
            created_by=user,
        )
        if needs_gl:
            journal = post_cheque_movement_journal(
                cheque, movement_type, when=when, user=user,
                movement_id=movement.pk,
                account_id=account_id,
                branch_id=(cheque.sales_invoice.branch_id
                           if cheque.sales_invoice_id else None),
            )
            movement.journal = journal
            movement.save(update_fields=['journal'])

        cheque.status = next_status
        update_fields = ['status']
        if deposit_account_changed:
            update_fields.append('deposit_bank_account')
        if endorsee_changed:
            update_fields.append('endorsed_to')
        cheque.save(update_fields=update_fields)
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


#: CHQ-4: سقف الدفعة الواحدة. الإيداع اليومي في أي شركة عشراتٌ لا مئات، وقسيمة
#: بأكثر من هذا لا تُقرأ ولا تُطبع في ورقة — والسقف يمنع طلباً يقفل الجدول.
CHEQUE_DEPOSIT_BATCH_LIMIT = 200


class ChequeBatchRejected(Exception):
    """CHQ-4: رفضُ دفعة إيداع مع سببٍ **لكل ورقة**.

    `ValidationError` كان سيسطّح قائمة المخالفين إلى نصوص (Django يلفّ كل قيمة
    في القاموس ويحوّلها) فيضيع ربط السبب برقم شيكه — وهو بالضبط ما يحتاجه
    المستخدم ليعرف أي ورقة يستثنيها من التحديد.
    """

    def __init__(self, rejected: list, detail: str):
        super().__init__(detail)
        self.rejected = rejected
        self.detail = detail


def deposit_cheques_batch(
    tenant_id: int, cheque_ids, *, bank_account_id=None, user=None,
    movement_date=None, notes: str = '',
) -> dict:
    """CHQ-4: إيداع عدّة شيكات في البنك دفعةً واحدة — وقسيمةٌ تُسلَّم مع الأوراق.

    إيداع الصباح في أي شركة حزمةُ شيكات لا ورقة: عشرون نافذة وعشرون نداءً كان
    عملاً يدوياً بلا مقابل، وأسوأ منه أن فشل الورقة السابعة يترك ستّاً مودَعة
    وستّاً لا — حالةٌ لا يملك المستخدم تصحيحها. فهنا **الكلّ أو لا شيء**:
    التحقّق كاملاً قبل أي كتابة، ثم `transfer_cheque` لكل ورقة داخل معاملة
    واحدة — فترث الدفعةُ الحُرّاسَ والقيود وidempotency بلا مسار قيدٍ ثانٍ.

    العملة واحدة عمداً: القسيمة ورقةٌ تُقدَّم للبنك بمجموعٍ واحد، ومجموعُ
    عملتين رقمٌ لا معنى له. عملتان ⇒ قسيمتان.
    """
    from .models import BankAccount, Cheque

    ids = list(dict.fromkeys(int(i) for i in (cheque_ids or [])))
    if not ids:
        raise ValidationError("لم تُحدَّد أي شيكات للإيداع.")
    if len(ids) > CHEQUE_DEPOSIT_BATCH_LIMIT:
        raise ValidationError(
            f"الحد الأقصى {CHEQUE_DEPOSIT_BATCH_LIMIT} شيكاً في الدفعة الواحدة — "
            f"حُدِّد {len(ids)}. قسّمها إلى دفعات."
        )

    cheques = list(
        Cheque.objects.filter(tenant_id=tenant_id, pk__in=ids)
        .select_related('partner', 'currency', 'customer_payment', 'sales_invoice',
                        'supplier_payment', 'purchase_invoice', 'bank')
    )
    found = {c.pk for c in cheques}
    rejected = [
        {'cheque_id': i, 'cheque_number': None,
         'reason': 'الشيك غير موجود أو لا يتبع هذه الشركة.'}
        for i in ids if i not in found
    ]

    for cheque in cheques:
        reason = None
        if cheque.direction != 'Incoming':
            reason = 'الإيداع للشيكات الواردة فقط.'
        elif cheque.status != 'Received':
            reason = (
                f"لا يمكن الإيداع من حالة «{status_label(cheque.direction, cheque.status)}»."
            )
        elif cheque_document_is_posted(cheque) is False:
            reason = 'سند الشيك غير مرحّل — رحّله أولاً.'
        if reason:
            rejected.append({
                'cheque_id': cheque.pk,
                'cheque_number': cheque.cheque_number,
                'reason': reason,
            })

    currencies = {c.currency_id for c in cheques}
    if len(currencies) > 1:
        rejected.append({
            'cheque_id': None, 'cheque_number': None,
            'reason': 'القسيمة الواحدة بعملة واحدة — أودع كل عملة في دفعة.',
        })

    bank_account = None
    if bank_account_id:
        bank_account = (
            BankAccount.objects
            .filter(pk=bank_account_id, tenant_id=tenant_id, is_active=True)
            .select_related('bank', 'currency').first()
        )
        if bank_account is None:
            rejected.append({
                'cheque_id': None, 'cheque_number': None,
                'reason': 'الحساب البنكي المحدد غير موجود أو لا يتبع هذه الشركة.',
            })
    elif tenant_has_active_bank_accounts(tenant_id):
        rejected.append({
            'cheque_id': None, 'cheque_number': None,
            'reason': 'حدّد الحساب البنكي المُودَع فيه.',
        })

    if rejected:
        # الذرّية تُقال قبل أن تُنفَّذ: لا كتابة إطلاقاً، والرسالة تعدّ المخالفين
        # بأرقام شيكاتهم كي يعرف المستخدم ما يستثنيه بدل أن يخمّن.
        raise ChequeBatchRejected(
            rejected, 'تعذّر إيداع الدفعة — لم تُودَع أي ورقة.')

    batch_ref = uuid.uuid4().hex[:8]
    batch_note = f"{notes} [batch:{batch_ref}]".strip()
    deposited = []
    with transaction.atomic():
        for cheque in cheques:
            deposited.append(transfer_cheque(
                cheque.pk, 'deposit', user=user, notes=batch_note[:500],
                movement_date=movement_date,
                bank_account_id=bank_account.pk if bank_account else None,
            ))

    total = sum(
        (Decimal(str(c.amount or 0)) for c in deposited), Decimal('0'),
    ).quantize(Decimal('0.01'))
    first = deposited[0]
    return {
        'deposited_count': len(deposited),
        'batch_ref': batch_ref,
        'slip': {
            'slip_date': str(movement_date or timezone.localdate()),
            'batch_ref': batch_ref,
            'notes': notes,
            'bank_account': ({
                'id': bank_account.pk,
                'bank_name': bank_account.bank.name if bank_account.bank_id else '',
                'name': bank_account.name,
                'account_number': bank_account.account_number or '',
            } if bank_account else None),
            'currency_code': getattr(first.currency, 'Code', '') if first.currency_id else '',
            'total': str(total),
            'cheques': [{
                'id': c.pk,
                'cheque_number': c.cheque_number,
                'drawer_bank': (c.bank.name if c.bank_id else None) or c.bank_name or '',
                'payee_name': c.payee_name or '',
                'partner_name': c.partner.name if c.partner_id else '',
                'due_date': str(c.due_date) if c.due_date else '',
                'amount': str(c.amount),
            } for c in deposited],
        },
    }


# ── CHQ-2: الشيك داخل سنده — الترحيل، إلغاؤه، وحارسه ────────────────────────

#: حركات من إنتاج **ترحيل المستند** لا من `transfer_cheque`: قيدها هو قيد
#: السند نفسه (أو لا قيد لها أصلاً في حالة `revert`). تُستثنى من حارس إلغاء
#: الترحيل — وإلا منع السندُ إلغاءَ نفسه بحركته هو.
DOCUMENT_MOVEMENT_TYPES = frozenset({'receive', 'issue', 'revert'})

#: الحالة التي يبلغها الشيك بترحيل سنده، لكل اتجاه. الوارد يدخل **المحفظة**
#: (1109) لا البنك — الاستلام غير الإيداع، وهذا ما يجعل «قيد الإيداع» ممكناً.
#: الصادر يبقى `Under_Collection` بمعنى «مسلَّم» على 2111 كما كان حرفياً.
DOCUMENT_POSTED_STATUS = {'Incoming': 'Received', 'Outgoing': 'Under_Collection'}
DOCUMENT_POSTED_MOVEMENT = {'Incoming': 'receive', 'Outgoing': 'issue'}

#: الحالات التي يستطيع إلغاء ترحيل المستند إرجاعها إلى `Draft` بأمان: الورقة
#: لم تتحرك بعد بعيداً عن يد صاحبها. ما عداها يعني حدثاً مالياً مستقلاً وقع
#: بعد الترحيل (تحصيل، ارتداد، تظهير…) وله قيده الخاص.
DOCUMENT_REVERSIBLE_STATUSES = ('Received', 'Under_Collection')

# T-INTENT: «مسودة» ليست حركةً بعد الترحيل بل حالُ ما قبل الدفاتر — لا قيد لها
# ولا شيء فيها يُعكَس. الحارس أدناه كان يعدّها مانعاً، فورقةٌ عادت مسودةً
# (أو لم تُرحَّل أصلاً) تمنع إلغاء ترحيل مستندها بلا سبب.
DOCUMENT_UNPOST_SAFE_STATUSES = ('Draft',) + DOCUMENT_REVERSIBLE_STATUSES


def record_document_cheque_posting(cheques, *, journal=None, user=None):
    """ترحيل السند يحرّك شيكاته المسودة — الحالة **وصفّ حركة** مربوط بقيده.

    CHQ-2: كان هذا `Cheque.objects.filter(...).update(status=...)` خاماً في
    ثلاثة مواضع — أهمّ حدث في حياة الشيك (دخوله الدفاتر) غائباً عن سجلّه، ولا
    شيء يربطه بالقيد الذي مدّن حسابه. يعيد قائمة الشيكات التي تحرّكت.
    """
    from .models import ChequeMovement

    moved = []
    for cheque in cheques:
        if cheque.status != 'Draft':
            # ورقة legacy وصلت البنك قبل هذا التغيير — مسارها القديم كما هو.
            continue
        next_status = DOCUMENT_POSTED_STATUS.get(cheque.direction)
        if next_status is None:
            continue
        ChequeMovement.objects.create(
            cheque=cheque,
            movement_type=DOCUMENT_POSTED_MOVEMENT[cheque.direction],
            journal=journal,
            notes='ترحيل السند',
            created_by=user,
        )
        cheque.status = next_status
        cheque.save(update_fields=['status'])
        moved.append(cheque)
    return moved


def record_document_cheque_unposting(cheques, *, user=None):
    """إلغاء ترحيل السند يعيد شيكاته مسودةً — ويسجّل الرجوع بدل ابتلاعه.

    بلا قيد: قيد السند حُذف، فلا شيء يُعكَس. يسبقه دائماً
    `guard_document_cheques_before_unpost` الذي يمنع الوصول إلى هنا بورقة
    تجاوزت `Received`/`Under_Collection`.
    """
    from .models import ChequeMovement

    moved = []
    for cheque in cheques:
        if cheque.status not in DOCUMENT_REVERSIBLE_STATUSES:
            continue
        ChequeMovement.objects.create(
            cheque=cheque,
            movement_type='revert',
            notes='إلغاء ترحيل السند',
            created_by=user,
        )
        cheque.status = 'Draft'
        cheque.save(update_fields=['status'])
        moved.append(cheque)
    return moved


def guard_document_cheques_before_unpost(
    cheques, *, document_label: str, action_label: str = 'إلغاء ترحيل',
) -> None:
    """يمنع إلغاء ترحيل مستندٍ تحرّك أحد شيكاته بعد ترحيله.

    العطل المُصلَح: إلغاء الترحيل كان يحذف قيد السند — الذي مدّن حساب الشيكات
    ودائَن الذمم — ويعيد **فقط** ما بقي `Under_Collection` إلى `Draft`. فشيكٌ
    وصل `Collected` يترك قيدَ تحصيله (مدين بنك ÷ دائن حساب الشيكات) وحيداً:
    حساب الشيكات يصير سالباً، والعميل يعود مديناً رغم أن النقد في البنك.

    مانعان مستقلان:
      1. **الحالة** — أي حالة خارج `Draft`/`Received`/`Under_Collection` تعني
         حدثاً مالياً مستقلاً وقع بعد الترحيل. «مسودة» حالُ ما قبل الدفاتر فلا
         تمنع شيئاً.
      2. **قيد حركة مرحَّل** — الورقة قد تبقى `Under_Collection` ولها قيد
         `CHEQUE_DEPOSIT` مستقل (1107 ÷ 1109): حذف قيد السند وحده يترك 1109
         سالباً. حركات المستند نفسه (`receive`/`issue`/`revert`) مستثناة.

    الرسالة تسمّي الشيكات وحالاتها كي يعرف المستخدم ما الذي يعكسه أولاً بدل
    أن يصطدم بجدار.
    """
    from .models import ChequeMovement

    rows = [c for c in cheques if c.status not in DOCUMENT_UNPOST_SAFE_STATUSES]
    blocked = {c.pk: c for c in rows}
    reversible_ids = [c.pk for c in cheques if c.pk not in blocked]
    if reversible_ids:
        with_journal = set(
            ChequeMovement.objects
            .filter(cheque_id__in=reversible_ids, journal__isnull=False)
            .exclude(movement_type__in=DOCUMENT_MOVEMENT_TYPES)
            .values_list('cheque_id', flat=True)
        )
        for cheque in cheques:
            if cheque.pk in with_journal:
                blocked[cheque.pk] = cheque
    if not blocked:
        return
    listing = "، ".join(
        f"{c.cheque_number} ({dict(c.STATUS_CHOICES).get(c.status, c.status)})"
        for c in sorted(blocked.values(), key=lambda c: c.pk)
    )
    logging.getLogger(__name__).warning(
        "unpost blocked for %s: %d cheque(s) already moved", document_label, len(blocked),
    )
    raise ValidationError(
        f"تعذّر {action_label} {document_label}: توجد شيكات تحرّكت بعد ترحيله "
        f"({listing}). اعكس حركة هذه الشيكات أولاً (إرجاع/تسوية) ثم أعد المحاولة."
    )


# T-CHQ2 — محفظة الشيكات: الحالات التي ما تزال الورقة فيها «في اليد»
# (لم تُحصَّل ولم تُردّ ولم تُسوَّ) هي وحدها ما يشكّل رصيد المحفظة.
CHEQUE_OPEN_STATUSES = ('Draft', 'Received', 'Under_Collection', 'Bounced')

CHEQUE_DUE_BUCKETS = (
    ('overdue', 'متأخرة'),
    ('due_7', 'تستحق خلال 7 أيام'),
    ('due_30', 'تستحق خلال 30 يوماً'),
    ('later', 'لاحقاً'),
    ('no_due_date', 'بلا تاريخ استحقاق'),
)


def _cheque_due_bucket(due_date, today):
    """يصنّف تاريخ الاستحقاق إلى دلو واحد — مصدر واحد للواجهة والتقارير."""
    if due_date is None:
        return 'no_due_date'
    delta = (due_date - today).days
    if delta < 0:
        return 'overdue'
    if delta <= 7:
        return 'due_7'
    if delta <= 30:
        return 'due_30'
    return 'later'


def cheque_wallet(tenant_id: int, *, today=None) -> dict:
    """T-CHQ2 — محفظة الشيكات: أين مال الشيكات المفتوحة الآن وما يستحق قريباً.

    كانت شاشة الشيكات قائمة صفوف فقط، فلا أحد يعرف كم في اليد ولا ما تأخّر.
    التجميعة على مستوى الشركة (لا تسرّب بين الشركات) وبالحالة وبتاريخ
    الاستحقاق، لكل اتجاه على حدة، و`net_open` = وارد مفتوح − صادر مفتوح.
    """
    import datetime as _dt
    from .models import Cheque

    today = today or timezone.localdate()
    rows = list(
        Cheque.objects
        .filter(tenant_id=tenant_id, status__in=CHEQUE_OPEN_STATUSES)
        .values_list('direction', 'status', 'due_date', 'amount')
    )

    def side(direction):
        mine = [r for r in rows if r[0] == direction]
        by_status: dict[str, list] = {}
        by_due: dict[str, list] = {}
        for _dir, status, due_date, amount in mine:
            by_status.setdefault(status, []).append(amount or Decimal('0'))
            by_due.setdefault(_cheque_due_bucket(due_date, today), []).append(
                amount or Decimal('0'))
        total = sum((a for _d, _s, _dd, a in mine), Decimal('0'))
        return {
            'open_total': str(Decimal(total).quantize(Decimal('0.01'))),
            'open_count': len(mine),
            'buckets': [
                {
                    'status': status,
                    'count': len(amounts),
                    'amount': str(sum(amounts, Decimal('0')).quantize(Decimal('0.01'))),
                }
                for status, amounts in sorted(by_status.items())
            ],
            'due_buckets': [
                {
                    'key': key,
                    'label': label,
                    'count': len(by_due.get(key, [])),
                    'amount': str(
                        sum(by_due.get(key, []), Decimal('0')).quantize(Decimal('0.01'))),
                }
                for key, label in CHEQUE_DUE_BUCKETS
            ],
        }

    incoming, outgoing = side('Incoming'), side('Outgoing')
    net = Decimal(incoming['open_total']) - Decimal(outgoing['open_total'])
    logger.info(
        "cheque_wallet: tenant=%s incoming=%s outgoing=%s",
        tenant_id, incoming['open_total'], outgoing['open_total'],
    )
    return {
        'as_of': today.isoformat(),
        'incoming': incoming,
        'outgoing': outgoing,
        'net_open': str(net.quantize(Decimal('0.01'))),
    }


#: CHQ-3 — أفق جدول الاستحقاق: 90 يوماً أسبوعاً بأسبوع.
CHEQUE_MATURITY_HORIZON_DAYS = 90


def cheque_maturity_timeline(tenant_id: int, *, today=None,
                             horizon_days: int = CHEQUE_MATURITY_HORIZON_DAYS) -> dict:
    """CHQ-3 — خطّ زمني مؤرَّخ للشيكات المفتوحة، بصافٍ تراكمي يُظهر أثر السيولة.

    `cheque_wallet` يجيب «كم في اليد ومتى تقريباً» بدلاء (متأخر/7/30/لاحقاً)؛
    هذا يجيب سؤالاً آخر لم يكن لأحد: **ماذا يبقى في يدي أسبوعاً بعد أسبوع**
    إذا حُصِّل كل وارد وصُرف كل صادر في موعده. الصافي التراكمي هو الجواب —
    انقلابه إلى السالب في أسبوعٍ ما هو الإنذار الذي يشتري به المالك وقتاً.

    الصفوف: `overdue` (كل ما فات موعده — لا يُسقَط، فالمال المتأخر ما زال
    مستحقاً)، ثم أسبوع لكل سبعة أيام حتى الأفق **بما فيها الأسابيع الفارغة**
    (خطٌّ زمني بثقوب لا يُقرأ)، ثم `beyond` لما بعد الأفق كي لا يختفي مالٌ
    مؤرَّخ بلا ذكر. الشيكات بلا تاريخ استحقاق تعود في `undated` منفصلةً: لا
    موضع لها على خطّ زمني، وحشرها في أي أسبوع كذبة.

    المفتوح هنا هو `CHEQUE_OPEN_STATUSES` نفسه الذي تقرأه المحفظة — رقم واحد
    بصيغة واحدة، فلا تفترق شاشتان على المبلغ ذاته.
    """
    import datetime as _dt
    from .models import Cheque

    today = today or timezone.localdate()
    horizon_end = today + _dt.timedelta(days=horizon_days)
    week_count = -(-(horizon_days + 1) // 7)

    rows_src = (
        Cheque.objects
        .filter(tenant_id=tenant_id, status__in=CHEQUE_OPEN_STATUSES)
        .values_list('direction', 'due_date', 'amount')
    )

    def blank():
        return {'incoming': Decimal('0'), 'incoming_count': 0,
                'outgoing': Decimal('0'), 'outgoing_count': 0}

    buckets = {'overdue': blank(), 'beyond': blank(), 'no_due_date': blank()}
    for index in range(1, week_count + 1):
        buckets[f'w{index}'] = blank()

    for direction, due_date, amount in rows_src:
        if due_date is None:
            key = 'no_due_date'
        elif due_date < today:
            key = 'overdue'
        elif due_date > horizon_end:
            key = 'beyond'
        else:
            key = f'w{((due_date - today).days // 7) + 1}'
        side = 'outgoing' if direction == 'Outgoing' else 'incoming'
        buckets[key][side] += Decimal(str(amount or 0))
        buckets[key][f'{side}_count'] += 1

    def week_span(index):
        start = today + _dt.timedelta(days=7 * (index - 1))
        return start, min(start + _dt.timedelta(days=6), horizon_end)

    spans = [('overdue', 'متأخرة', None, today - _dt.timedelta(days=1))]
    spans += [(f'w{i}', f'الأسبوع {i}', *week_span(i)) for i in range(1, week_count + 1)]
    spans.append(('beyond', f'بعد {horizon_days} يوماً',
                  horizon_end + _dt.timedelta(days=1), None))

    def money(value):
        return str(Decimal(value).quantize(Decimal('0.01')))

    rows, cumulative = [], Decimal('0')
    for key, label, start, end in spans:
        bucket = buckets[key]
        net = bucket['incoming'] - bucket['outgoing']
        cumulative += net
        rows.append({
            'key': key, 'label': label, 'from': start, 'to': end,
            'incoming': money(bucket['incoming']),
            'incoming_count': bucket['incoming_count'],
            'outgoing': money(bucket['outgoing']),
            'outgoing_count': bucket['outgoing_count'],
            'net': money(net),
            'cumulative_net': money(cumulative),
        })

    undated = buckets['no_due_date']
    logger.info(
        "cheque_maturity_timeline: tenant=%s horizon=%s weeks=%s final_net=%s",
        tenant_id, horizon_days, week_count, money(cumulative),
    )
    return {
        'as_of': today.isoformat(),
        'horizon_days': horizon_days,
        'rows': rows,
        'undated': {
            'key': 'no_due_date', 'label': 'بلا تاريخ استحقاق',
            'incoming': money(undated['incoming']),
            'incoming_count': undated['incoming_count'],
            'outgoing': money(undated['outgoing']),
            'outgoing_count': undated['outgoing_count'],
            'net': money(undated['incoming'] - undated['outgoing']),
        },
    }


# ─────────────────────────────────────────────────────────
#  T-BANKS: البنوك وحساباتها والمطابقة البنكية
# ─────────────────────────────────────────────────────────

BANK_PARENT_ACCOUNT_CODE = "1102"


def get_bank_parent_account(tenant):
    """حساب الأب «البنوك» في الشجرة — يُنشأ تحت الأصول المتداولة إن غاب.

    بلا أب لا مكان لحسابات البنوك، وإنشاؤه مرة واحدة أفضل من رفض العملية
    على شركة قديمة بُذرت قبل هذا الحساب.
    """
    acc = Account.objects.filter(tenant=tenant, code=BANK_PARENT_ACCOUNT_CODE).first()
    if acc:
        return acc
    current_assets = Account.objects.filter(tenant=tenant, code="11").first()
    if current_assets is None:
        return (
            Account.objects.filter(tenant=tenant, account_type="Asset",
                                   code__startswith="11").order_by("code").first()
            or Account.objects.filter(tenant=tenant, account_type="Asset").order_by("code").first()
        )
    acc = Account.objects.create(
        tenant=tenant, code=BANK_PARENT_ACCOUNT_CODE, name="البنوك (Banks)",
        parent=current_assets, account_type="Asset", is_active=True,
    )
    logger.info("get_bank_parent_account: created 1102 for tenant=%s", getattr(tenant, "TenantID", tenant))
    return acc


def create_bank_account(*, tenant, bank, name, currency, branch=None, account_number=None,
                        iban=None, is_default=False, notes=None, user=None):
    """ينشئ حساباً بنكياً وحسابه في الشجرة تحت «1102 البنوك» في معاملة واحدة."""
    from .account_classification import SUB_TYPE_BANK
    from .cashbox import allocate_child_account_code
    from .models import BankAccount

    parent = get_bank_parent_account(tenant)
    if parent is None:
        raise ValidationError(
            "لا يوجد حساب أب للبنوك في شجرة الحسابات — أنشئ «11 الأصول المتداولة» أولاً."
        )
    label = (name or "").strip()
    if not label:
        raise ValidationError("اسم الحساب البنكي مطلوب.")
    with transaction.atomic():
        code = allocate_child_account_code(
            parent, tenant,
            marker="K",
            seed=BankAccount.objects.filter(tenant=tenant).count() + 1,
            fallback_prefix=BANK_PARENT_ACCOUNT_CODE,
        )
        gl = Account.objects.create(
            tenant=tenant, code=code, name=f"{bank.name} — {label}"[:100],
            parent=parent, account_type=parent.account_type or "Asset", is_active=True,
            # THA-111: التصنيف يواكب البيانات الجديدة بلا backfill ثانٍ — هذا
            # الحساب بنكيٌّ بحكم إنشائه، لا بحكم رمزه أو اسمه.
            sub_type=SUB_TYPE_BANK,
        )
        if is_default:
            BankAccount.objects.filter(tenant=tenant, is_default=True).update(is_default=False)
        ba = BankAccount.objects.create(
            tenant=tenant, bank=bank, branch=branch, name=label[:150],
            account_number=(account_number or None), iban=(iban or None),
            currency=currency, account=gl, is_default=bool(is_default),
            notes=(notes or None),
        )
    logger.info(
        "create_bank_account: tenant=%s bank=%s account=%s gl=%s(%s)",
        getattr(tenant, "TenantID", tenant), bank.pk, ba.pk, gl.pk, code,
    )
    return ba


def bank_account_statement(bank_account, *, start_date=None, end_date=None, posted_only=True):
    """حركة الحساب البنكي من دفتر الأستاذ + حالة المطابقة لكل سطر.

    يعيد: opening (رصيد ما قبل start_date)، rows، وbook_balance (رصيد الدفاتر
    حتى end_date)، وcleared_balance (المؤشَّر منه فقط).
    """
    from django.db.models import Sum

    qs = (
        JournalLine.objects
        .filter(tenant_id=bank_account.tenant_id, account_id=bank_account.account_id)
        .select_related("journal", "partner")
    )
    if posted_only:
        qs = qs.filter(journal__is_posted=True)

    opening = Decimal("0.00")
    if start_date:
        agg = qs.filter(journal__transaction_date__lt=start_date).aggregate(
            d=Sum("debit"), c=Sum("credit"),
        )
        opening = (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))
        qs = qs.filter(journal__transaction_date__gte=start_date)
    if end_date:
        qs = qs.filter(journal__transaction_date__lte=end_date)

    rows = []
    balance = opening
    cleared = opening
    for line in qs.order_by("journal__transaction_date", "journal_id", "id"):
        movement = (line.debit or Decimal("0")) - (line.credit or Decimal("0"))
        balance += movement
        rec_line = getattr(line, "bank_reconciliation_line", None)
        if rec_line is not None:
            cleared += movement
        rows.append({
            "journal_line_id": line.id,
            "journal_id": line.journal_id,
            "date": line.journal.transaction_date,
            "description": line.description or line.journal.description or "",
            "partner": line.partner.name if line.partner_id else None,
            "debit": line.debit,
            "credit": line.credit,
            "balance": balance,
            "is_cleared": rec_line is not None,
            "reconciliation_id": rec_line.reconciliation_id if rec_line is not None else None,
        })
    return {
        "opening_balance": opening,
        "book_balance": balance,
        "cleared_balance": cleared,
        "rows": rows,
    }


# ─────────────────────────── الخزينة: الصناديق النقدية ───────────────────────────
# T-CASHBOX: الصندوق كيانٌ أول (`CashBoxLedgerAccount`) وحسابُه في الشجرة وجهُه
# المحاسبي. كل ما تحت هذا العنوان يمرّ بـ`post_journal` كغيره — لا استثناء.

CASH_OVERAGE_ACCOUNT_CODE = "4202"   # زيادة الصندوق (إيراد)
CASH_SHORTAGE_ACCOUNT_CODE = "5206"  # عجز الصندوق (مصروف)


def _ensure_coa_account(tenant, code: str):
    """حساب معياري من الشجرة، يُنشأ إن غاب — نفس نهج حسابَي الشيكات."""
    from tenants.services import ensure_operational_account

    acc = Account.objects.filter(tenant=tenant, code=code, is_active=True).first()
    if acc is None:
        acc = ensure_operational_account(tenant, code)
    return acc


def create_cash_box(*, tenant, name, currency_code="ILS", is_default=False,
                    external_id=None, notes=None, user=None):
    """ينشئ صندوقاً نقدياً وحسابَه في الشجرة تحت «1110» في معاملة واحدة.

    T-CASHBOX M2 — على نمط `create_bank_account`. قبلها كان الإنشاء نداءين من
    المتصفح (وثيقة المرآة أولاً ثم حساب الشجرة)، فكان فشل النداء الثاني يترك
    صندوقاً بلا حساب: مالٌ يتحرّك بلا وجهٍ في الدفاتر، وواجهةٌ فيها زرّ إصلاح
    يدوي. الآن نداءٌ واحد وذرّية واحدة: الحساب والربط ووثيقة المرآة معاً أو
    لا شيء.
    """
    from .account_classification import SUB_TYPE_CASH_BOX
    from .cashbox import allocate_cash_box_account_code, get_cash_box_parent_account
    from .models import CashBoxLedgerAccount

    label = (name or "").strip()
    if not label:
        raise ValidationError("اسم الصندوق مطلوب.")
    if len(label) > 100:
        # اسم الحساب في الشجرة 100 محرف — والبتر الصامت في MySQL ينتج حسابين
        # بالاسم نفسه لا يفرّق المستخدم بينهما.
        raise ValidationError("اسم الصندوق طويل — الحدّ 100 محرف.")
    currency = (currency_code or "ILS").strip().upper()[:3] or "ILS"

    parent = get_cash_box_parent_account(tenant)
    if parent is None:
        raise ValidationError(
            "لم يُعثر على حساب أب للصناديق (1110). أنشئ «11 الأصول المتداولة» أولاً."
        )
    ext = (str(external_id).strip() if external_id else "") or uuid.uuid4().hex
    if CashBoxLedgerAccount.objects.filter(tenant=tenant, external_id=ext[:128]).exists():
        raise ValidationError("هذا المعرّف مربوط بالفعل بصندوق.")

    with transaction.atomic():
        code = allocate_cash_box_account_code(parent, tenant)
        gl = Account.objects.create(
            tenant=tenant, code=code, name=label[:100], parent=parent,
            account_type=parent.account_type or "Asset", is_active=True,
            # صندوقٌ بحكم إنشائه — لا اشتقاق لاحق من الرمز أو الاسم.
            sub_type=SUB_TYPE_CASH_BOX,
        )
        first_box = not CashBoxLedgerAccount.objects.filter(tenant=tenant).exists()
        make_default = bool(is_default) or first_box
        if make_default:
            CashBoxLedgerAccount.objects.filter(
                tenant=tenant, is_default=True,
            ).update(is_default=False)
        box = CashBoxLedgerAccount.objects.create(
            tenant=tenant, external_id=ext[:128], name=label[:200],
            currency_code=currency, account=gl, is_default=make_default,
            is_active=True, notes=(notes or None),
        )
        _mirror_cash_box(box, created=True)
    logger.info(
        "create_cash_box: tenant=%s box=%s gl=%s(%s) currency=%s default=%s",
        getattr(tenant, "TenantID", tenant), box.pk, gl.pk, code, currency, make_default,
    )
    return box


def _mirror_cash_box(box, *, created=False):
    """يكتب وثيقة الصندوق في مرآة `bridge` ليبقى قرّاؤها القدامى يعملون.

    المرآة صارت **مشتقّة**: الخادم وحده يكتبها، والرصيد فيها لا يُعتمد (مصدر
    الرصيد هو دفتر الأستاذ). فشلُها لا يُسقط إنشاء الصندوق — التوافق ليس مالاً.
    """
    try:
        from bridge.models import FirestoreMirrorDoc

        # `path` فريد **عالمياً** لا لكل شركة، فالبحث به وحده والشركة تُكتب
        # قيمةً لا مفتاحاً — وإلا اصطدم إدراجٌ ثانٍ بنفس المسار.
        path = f"cashBoxes/{box.external_id}"
        doc, _ = FirestoreMirrorDoc.objects.get_or_create(
            path=path, defaults={"data": {}, "tenant": box.tenant},
        )
        if doc.tenant_id != box.tenant_id:
            doc.tenant = box.tenant
            doc.save(update_fields=["tenant"])
        data = dict(doc.data or {})
        data.update({
            "id": box.external_id,
            "name": box.name,
            "currency": box.currency_code,
            "isActive": box.is_active,
        })
        if created:
            data.setdefault("currentBalance", 0)
        doc.data = data
        doc.save(update_fields=["data"])
    except Exception:
        logger.warning("mirror sync failed for cash box %s", box.pk, exc_info=True)


def set_default_cash_box(box, *, user=None):
    """يجعل الصندوق افتراضي الشركة — واحدٌ فقط، ذرّياً."""
    from .models import CashBoxLedgerAccount

    with transaction.atomic():
        CashBoxLedgerAccount.objects.filter(
            tenant_id=box.tenant_id, is_default=True,
        ).exclude(pk=box.pk).update(is_default=False)
        if not box.is_default:
            box.is_default = True
            box.save(update_fields=["is_default"])
    return box


def update_cash_box(box, *, name=None, is_active=None, notes=None,
                    currency_code=None, user=None):
    """تعديل صندوق — والاسم يزامن حسابَه في الشجرة والمرآة معاً.

    قبلها كانت إعادة التسمية تقع في المرآة وحدها فيبقى اسم الشجرة القديم:
    اسمان لصندوق واحد، وكشفٌ لا يطابق شجرة.
    """
    from .models import CashBoxFxLot

    fields = []
    if name is not None:
        label = (name or "").strip()
        if not label:
            raise ValidationError("اسم الصندوق مطلوب.")
        if len(label) > 100:
            raise ValidationError("اسم الصندوق طويل — الحدّ 100 محرف.")
        box.name = label[:200]
        fields.append("name")
    if notes is not None:
        box.notes = notes or None
        fields.append("notes")
    if currency_code is not None:
        cur = (currency_code or "").strip().upper()[:3]
        if cur and cur != (box.currency_code or "").upper():
            # طبقات FIFO محسوبة بعملة الصندوق — تغييرها بعدها يجعل الرصيد
            # الدفتري بلا معنى، فيُمنع بدل أن يفسد بصمت.
            if CashBoxFxLot.objects.filter(cash_box=box).exists():
                raise ValidationError(
                    "لا يمكن تغيير عملة صندوق له طبقات عملة أجنبية — أنشئ صندوقاً جديداً."
                )
            box.currency_code = cur
            fields.append("currency_code")
    if is_active is not None:
        box.is_active = bool(is_active)
        fields.append("is_active")
        if not box.is_active and box.is_default:
            box.is_default = False
            fields.append("is_default")
    if fields:
        with transaction.atomic():
            box.save(update_fields=fields)
            if "name" in fields and box.account_id:
                Account.objects.filter(pk=box.account_id).update(name=box.name[:100])
            _mirror_cash_box(box)
    return box


def cash_box_statement(cash_box, *, start_date=None, end_date=None, posted_only=True):
    """كشف الصندوق من دفتر الأستاذ برصيد جارٍ حقيقي.

    T-CASHBOX M4 — نظير `bank_account_statement` بلا أعمدة المطابقة. قبلها كان
    الكشف يُبنى في المتصفح بدمج سجلّ المرآة مع أسطر الأستاذ وترتيبٍ مُلفَّق
    (الأستاذ مثبَّت على 12:00 ثم `journal_id ‰ 1000 × 0.001`)، فعمود «الرصيد»
    لم يكن رصيداً جارياً بل مجموعاً تراكمياً لترتيبٍ عشوائي.
    """
    from django.db.models import Sum

    qs = (
        JournalLine.objects
        .filter(tenant_id=cash_box.tenant_id, account_id=cash_box.account_id)
        .select_related("journal", "partner")
    )
    if posted_only:
        qs = qs.filter(journal__is_posted=True)

    opening = Decimal("0.00")
    if start_date:
        agg = qs.filter(journal__transaction_date__lt=start_date).aggregate(
            d=Sum("debit"), c=Sum("credit"),
        )
        opening = (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))
        qs = qs.filter(journal__transaction_date__gte=start_date)
    if end_date:
        qs = qs.filter(journal__transaction_date__lte=end_date)

    rows = []
    balance = opening
    for line in qs.order_by("journal__transaction_date", "journal_id", "id"):
        balance += (line.debit or Decimal("0")) - (line.credit or Decimal("0"))
        rows.append({
            "journal_line_id": line.id,
            "journal_id": line.journal_id,
            "date": line.journal.transaction_date,
            "reference_type": line.journal.reference_type,
            "reference_id": line.journal.reference_id,
            "description": line.description or line.journal.description or "",
            "partner": line.partner.name if line.partner_id else None,
            "debit": line.debit,
            "credit": line.credit,
            "balance": balance,
        })
    return {
        "cash_box_id": cash_box.id,
        "account_id": cash_box.account_id,
        "currency_code": cash_box.currency_code,
        "opening_balance": opening,
        "closing_balance": balance,
        "rows": rows,
    }


def cash_box_balance(cash_box, *, as_of=None) -> Decimal:
    """رصيد الصندوق الدفتري من الأسطر المرحّلة."""
    from django.db.models import Sum

    qs = JournalLine.objects.filter(
        tenant_id=cash_box.tenant_id, account_id=cash_box.account_id,
        journal__is_posted=True,
    )
    if as_of:
        qs = qs.filter(journal__transaction_date__lte=as_of)
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    return ((agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))).quantize(Decimal("0.01"))


def cash_box_adjustment(cash_box, *, direction, amount, contra_account=None,
                        date=None, memo="", user=None):
    """إيداع نقد في صندوق أو سحبه منه — «Put money in / Take money out».

    T-CASHBOX M6: تعميم `deposit-journal` القديم الذي كان إيداعاً فقط ومفتاحه
    `external_id`. المقابل الافتراضي حساب رأس المال (إيداع المالك)، ويجوز
    تمريره صراحةً (مصروف نثري مثلاً).
    """
    from .cashbox import get_cash_box_capital_account

    if direction not in ("in", "out"):
        raise ValidationError("اتجاه الحركة يجب أن يكون in أو out.")
    value = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValidationError("المبلغ يجب أن يكون أكبر من صفر.")
    if not cash_box.is_active:
        raise ValidationError("الصندوق معطَّل — فعّله قبل تسجيل حركة عليه.")
    when = date or timezone.localdate()

    contra = contra_account or get_cash_box_capital_account(cash_box.tenant)
    if contra is None:
        raise ValidationError(
            "لا يوجد حساب مقابل للحركة — عيّن حساب رأس مال (Equity) في الشجرة."
        )
    if direction == "out":
        available = cash_box_balance(cash_box, as_of=when)
        if value > available:
            raise ValidationError(
                f"رصيد {cash_box.name} لا يكفي: المتاح {available}، والمطلوب {value}."
            )
    label = memo.strip() or (
        f"إيداع في {cash_box.name}" if direction == "in" else f"سحب من {cash_box.name}"
    )
    box_debit = value if direction == "in" else Decimal("0")
    box_credit = Decimal("0") if direction == "in" else value
    return post_journal(
        tenant_id=cash_box.tenant_id,
        transaction_date=when,
        reference_type="CASHBOX_ADJUSTMENT",
        reference_id=cash_box.id,
        description=label,
        lines_data=[
            {"account": cash_box.account_id, "debit": box_debit,
             "credit": box_credit, "description": label},
            {"account": contra.id, "debit": box_credit,
             "credit": box_debit, "description": label},
        ],
        user=user,
        idempotent=False,
    )


def _transfer_side(box=None, bank_account=None):
    """يتحقّق من طرف تحويلٍ واحد ويُرجع (حسابه، اسمه، عملته)."""
    if bool(box) == bool(bank_account):
        raise ValidationError("كل طرف من طرفَي التحويل صندوقٌ واحد أو حساب بنكي واحد.")
    if box is not None:
        if not box.is_active:
            raise ValidationError(f"الصندوق {box.name} معطَّل.")
        return box.account_id, box.name, (box.currency_code or "").upper()
    return (
        bank_account.account_id, bank_account.name,
        (getattr(bank_account.currency, "code", "") or "").upper(),
    )


def create_cash_transfer(*, tenant, transfer_date, amount, from_cash_box=None,
                         from_bank_account=None, to_cash_box=None,
                         to_bank_account=None, rate=None, notes=None, user=None):
    """تحويل نقدي بين خزينتين — مستندٌ واحد بقيدٍ واحد.

    T-CASHBOX M6: كان التحويل يُسجَّل إيداعاً هنا وسحباً هناك بلا رابط، فلا
    يُعرف أنهما حركة واحدة ولا يُعكسان معاً. أمّا التحويل إلى صندوق عملة
    أجنبية فيُفوَّض إلى `fx_fifo.transfer_ils_to_fx` لأن طبقات FIFO هي مصدر
    تكلفة العملة، وقيدٌ مباشر بجانبها يفسدها بصمت.
    """
    from .models import CashTransfer

    value = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    if value <= 0:
        raise ValidationError("مبلغ التحويل يجب أن يكون أكبر من صفر.")
    when = transfer_date or timezone.localdate()
    src_account_id, src_name, src_currency = _transfer_side(from_cash_box, from_bank_account)
    dst_account_id, dst_name, dst_currency = _transfer_side(to_cash_box, to_bank_account)
    if src_account_id == dst_account_id:
        raise ValidationError("لا يمكن التحويل من الخزينة إلى نفسها.")

    available = (
        cash_box_balance(from_cash_box, as_of=when) if from_cash_box is not None else None
    )
    if available is not None and value > available:
        raise ValidationError(
            f"رصيد {src_name} لا يكفي: المتاح {available}، والمطلوب {value}."
        )

    fx_rate = Decimal(str(rate or 1))
    label = notes or f"تحويل من {src_name} إلى {dst_name}"

    with transaction.atomic():
        transfer = CashTransfer.objects.create(
            tenant=tenant, transfer_date=when,
            from_cash_box=from_cash_box, from_bank_account=from_bank_account,
            to_cash_box=to_cash_box, to_bank_account=to_bank_account,
            amount=value, rate=fx_rate, notes=notes or None,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        transfer.number = transfer.id
        if to_cash_box is not None and dst_currency and dst_currency != src_currency:
            # الوجهة بعملة أخرى ⇒ المبلغ المُدخل بعملة المصدر، والوارد
            # للصندوق الأجنبي = المبلغ ÷ السعر، وطبقة FIFO تحفظ سعرها.
            from .fx_fifo import transfer_ils_to_fx

            if fx_rate <= 0:
                raise ValidationError("سعر الصرف مطلوب للتحويل بين عملتين مختلفتين.")
            if from_cash_box is None:
                raise ValidationError(
                    "التحويل إلى صندوق عملة أجنبية يبدأ من صندوق نقدي لا من حساب بنكي."
                )
            fc = (value / fx_rate).quantize(Decimal("0.0001"))
            lot = transfer_ils_to_fx(
                to_cash_box, from_cash_box, fc, fx_rate, date=when, user=user,
            )
            transfer.journal = lot.journal
        else:
            jh = post_journal(
                tenant_id=tenant.pk, transaction_date=when,
                reference_type="CASH_TRANSFER", reference_id=transfer.id,
                description=label,
                lines_data=[
                    {"account": dst_account_id, "debit": value,
                     "credit": Decimal("0"), "description": label},
                    {"account": src_account_id, "debit": Decimal("0"),
                     "credit": value, "description": label},
                ],
                user=user,
            )
            transfer.journal = jh
        transfer.save(update_fields=["number", "journal"])
    logger.info(
        "create_cash_transfer: tenant=%s transfer=%s %s→%s amount=%s",
        tenant.pk, transfer.id, src_account_id, dst_account_id, value,
    )
    return transfer


def post_cash_count(count, *, user=None):
    """يرحّل فرق جرد الصندوق: الزيادة إيراد (4202) والعجز مصروف (5206).

    T-CASHBOX M6 — نمط Odoo (Profit/Loss Account). الفرق صفراً ⇒ لا قيد،
    والمستند يبقى سجلَّ جردٍ مطابق.
    """
    from .models import CashCount

    if count.status == CashCount.STATUS_POSTED:
        return count
    box = count.cash_box
    book = cash_box_balance(box, as_of=count.count_date)
    counted = Decimal(str(count.counted_total or 0)).quantize(Decimal("0.01"))
    diff = (counted - book).quantize(Decimal("0.01"))

    with transaction.atomic():
        count.book_balance = book
        count.difference = diff
        count.status = CashCount.STATUS_POSTED
        if diff != 0:
            over = diff > 0
            contra = _ensure_coa_account(
                box.tenant,
                CASH_OVERAGE_ACCOUNT_CODE if over else CASH_SHORTAGE_ACCOUNT_CODE,
            )
            if contra is None:
                raise ValidationError(
                    "تعذّر تحديد حساب فرق الجرد (4202/5206) — أنشئه في شجرة الحسابات."
                )
            label = (
                f"زيادة جرد {box.name}" if over else f"عجز جرد {box.name}"
            )
            magnitude = abs(diff)
            count.journal = post_journal(
                tenant_id=box.tenant_id, transaction_date=count.count_date,
                reference_type="CASH_COUNT", reference_id=count.id,
                description=label,
                lines_data=[
                    {"account": box.account_id,
                     "debit": magnitude if over else Decimal("0"),
                     "credit": Decimal("0") if over else magnitude,
                     "description": label},
                    {"account": contra.id,
                     "debit": Decimal("0") if over else magnitude,
                     "credit": magnitude if over else Decimal("0"),
                     "description": label},
                ],
                user=user,
            )
        count.save(update_fields=["book_balance", "difference", "status", "journal"])
    return count


def bank_reconciliation_summary(reconciliation):
    """ملخص المطابقة: رصيد الدفاتر، المؤشَّر، رصيد الكشف، والفرق."""
    stmt = bank_account_statement(
        reconciliation.bank_account, end_date=reconciliation.statement_date,
    )
    statement_balance = Decimal(str(reconciliation.statement_balance or 0))
    cleared = stmt["cleared_balance"]
    return {
        "book_balance": stmt["book_balance"],
        "cleared_balance": cleared,
        "statement_balance": statement_balance,
        "difference": (statement_balance - cleared).quantize(Decimal("0.01")),
        "uncleared_count": sum(1 for r in stmt["rows"] if not r["is_cleared"]),
        "rows": stmt["rows"],
    }


def close_bank_reconciliation(reconciliation, *, user=None):
    """إقفال المطابقة — يُرفض ما لم يكن الفرق صفراً."""
    from django.utils import timezone
    from .models import BankReconciliation

    if reconciliation.status == BankReconciliation.STATUS_CLOSED:
        return reconciliation
    summary = bank_reconciliation_summary(reconciliation)
    if abs(summary["difference"]) >= Decimal("0.01"):
        raise ValidationError(
            f"لا يمكن إقفال المطابقة والفرق {summary['difference']} — "
            "أشِّر باقي الحركات أو صحّح رصيد الكشف."
        )
    reconciliation.status = BankReconciliation.STATUS_CLOSED
    reconciliation.closed_at = timezone.now()
    reconciliation.save(update_fields=["status", "closed_at"])
    create_audit_log(
        tenant=reconciliation.tenant, user=user, action="POST",
        model_name="BankReconciliation", object_id=reconciliation.pk,
        change_details=(
            f"إقفال مطابقة الحساب {reconciliation.bank_account_id} "
            f"حتى {reconciliation.statement_date} برصيد {reconciliation.statement_balance}"
        ),
    )
    logger.info(
        "close_bank_reconciliation: id=%s bank_account=%s balance=%s",
        reconciliation.pk, reconciliation.bank_account_id, reconciliation.statement_balance,
    )
    return reconciliation


# ─────────────────────────────────────────────────────────
#  task18 DEF-C1: رصيد الشريك من دفتر الأستاذ الفرعي (subledger)
# ─────────────────────────────────────────────────────────

def _attach_statement_document_links(rows: list, *, is_supplier: bool) -> None:
    """يربط حركات كشف الحساب بمستند المرساة (الفاتورة) — استعلامات بالدفعة لا لكل صف.

    الفاتورة مرساة مجموعتها، وسند القبض/الصرف ينضمّ لمجموعة الفاتورة التي وُزّع
    عليها؛ فتُعرَض الحركتان متجاورتين في الواجهة. سند موزَّع على أكثر من فاتورة
    يبقى بلا مرساة واحدة (link_key=None) ويحمل عددها في link_count. يعدّل `rows`
    في مكانها.
    """
    invoice_type = "PURCHASE_INVOICE" if is_supplier else "SALES_INVOICE"
    payment_type = "SUPPLIER_PAYMENT" if is_supplier else "CUSTOMER_PAYMENT"
    invoice_ids = {
        r["reference_id"] for r in rows
        if r["reference_type"] == invoice_type and r["reference_id"]
    }
    payment_ids = {
        r["reference_id"] for r in rows
        if r["reference_type"] == payment_type and r["reference_id"]
    }

    by_payment: dict[int, list[int]] = {}
    if payment_ids:
        if is_supplier:
            from sales.models import SupplierPayment, SupplierPaymentAllocation
            allocations = SupplierPaymentAllocation.objects.filter(
                payment_id__in=payment_ids,
            ).values_list("payment_id", "invoice_id")
        else:
            from sales.models import PaymentAllocation
            allocations = PaymentAllocation.objects.filter(
                payment_id__in=payment_ids,
            ).values_list("payment_id", "invoice_id")
        for pay_id, inv_id in allocations:
            by_payment.setdefault(pay_id, []).append(inv_id)
        if is_supplier:
            # سندات الصرف القديمة مربوطة بالحقل المفرد لا بجدول التوزيعات.
            legacy = SupplierPayment.objects.filter(
                id__in=[p for p in payment_ids if p not in by_payment],
                purchase_invoice__isnull=False,
            ).values_list("id", "purchase_invoice_id")
            for pay_id, inv_id in legacy:
                by_payment.setdefault(pay_id, []).append(inv_id)
        invoice_ids.update(inv_id for links in by_payment.values() for inv_id in links)

    numbers: dict[int, str] = {}
    if invoice_ids:
        if is_supplier:
            from logistics.models import PurchaseInvoice
            source = PurchaseInvoice.objects.filter(id__in=invoice_ids)
        else:
            from sales.models import SalesInvoice
            source = SalesInvoice.objects.filter(id__in=invoice_ids)
        numbers = dict(source.values_list("id", "invoice_number"))

    for row in rows:
        ref_id = row["reference_id"]
        row["document_number"] = None
        row["link_key"] = None
        row["link_label"] = None
        row["link_count"] = 0
        if not ref_id:
            continue
        if row["reference_type"] == invoice_type:
            row["document_number"] = numbers.get(ref_id) or f"#{ref_id}"
            row["link_key"] = f"{invoice_type}:{ref_id}"
            row["link_label"] = row["document_number"]
            row["link_count"] = 1
        elif row["reference_type"] == payment_type:
            links = by_payment.get(ref_id, [])
            row["link_count"] = len(links)
            if len(links) == 1:
                row["link_key"] = f"{invoice_type}:{links[0]}"
                row["link_label"] = numbers.get(links[0]) or f"#{links[0]}"
            elif links:
                row["link_label"] = f"{len(links)} فواتير"


def partner_account_statement(
    *, tenant_id: int, partner_id: int, is_supplier: bool,
    limit: int = 50, offset: int = 0, ordering: str = "newest",
    only_payments: bool = False,
    anchor_reference_type: str | None = None,
    anchor_reference_id: int | None = None,
) -> dict:
    """FEAT-4: كشف حساب الشريك من أسطر القيود المرحَّلة — مع رصيد جارٍ لكل سطر.

    الرصيد الجاري يُحسب خادمياً بالترتيب الزمني ويُطابق `partner_posted_balance`
    (لا مصدر حقيقة موازٍ — A4). للعميل: مدين−دائن؛ للمورد: دائن−مدين. مُرقَّم.

    THA-128: كل سطر يحمل `balance_before` (الرصيد قبل أثره) إلى جانب
    `running_balance` (بعده) — ليسا حساباً ثانياً بل لقطتان من الحلقة نفسها، فما
    يعرضه «تبويب المال» يطابق كشف الحساب بالبناء لا بالمصادفة.

    THA-132: `anchor_reference_type`/`anchor_reference_id` يُرسيان الصفحة على
    مستندٍ بعينه بدل «أحدث N» — فيرى المستندُ حركةَ حسابه حول نفسه ولو كان
    قديماً تلته مئة حركة. المرساة **لا تغيّر الحساب**: الرصيد الجاري يُحسب على
    الحلقة الزمنية كاملةً كما هو، وهي تحكم النافذة المعروضة وحدها. وبلا
    تمريرهما السلوك حرفياً كما كان (المستهلكون القائمون لا يتأثرون).

    `only_payments` يحصر **المعروض** بحركات التسوية دون الفاتورة نفسها. استثناءُ
    الفاتورة لا قائمةُ أنواعٍ مسموحة: القائمة المسموحة تُسقط بصمت كل نوعٍ جديد
    يمسّ المال (ارتداد شيك · تظهير · إشعار دائن)، وإخفاء حركةٍ ماليّة من شاشة
    المال أسوأ من إظهار حركةٍ زائدة. والحساب لا يتأثر بالترشيح إطلاقاً: الرصيد
    الجاري و`closing_balance` يُحسبان على الحساب كلّه.
    """
    base = (
        JournalLine.objects.filter(
            tenant_id=tenant_id, partner_id=partner_id, journal__is_posted=True,
        )
        .order_by("journal__transaction_date", "journal_id", "id")
    )
    # خفيف: عمودان عشريان ونوع المستند فقط لحساب الرصيد الجاري بالترتيب
    # (بحدود أسطر الشريك). النوع لازمٌ للترشيح، ويأتي في الاستعلام نفسه.
    ordered = list(base.values_list(
        "id", "base_debit", "base_credit",
        "journal__reference_type", "journal__reference_id"))
    running = Decimal("0")
    running_by_id: dict[int, Decimal] = {}
    before_by_id: dict[int, Decimal] = {}
    for lid, d, c, _ref_type, _ref_id in ordered:
        d = Decimal(str(d or 0))
        c = Decimal(str(c or 0))
        # اللقطة قبل الأثر ثم بعده — من الحلقة ذاتها، بلا مرور ثانٍ.
        before_by_id[lid] = running
        running += (c - d) if is_supplier else (d - c)
        running_by_id[lid] = running
    closing = running

    # الترشيح بعد الحساب: يحكم ما يُعرض لا كيف يُحسب.
    if only_payments:
        invoice_type = "PURCHASE_INVOICE" if is_supplier else "SALES_INVOICE"
        visible = [row for row in ordered if row[3] != invoice_type]
    else:
        visible = ordered
    total = len(visible)

    normalized_ordering = "oldest" if ordering == "oldest" else "newest"
    display_order = visible if normalized_ordering == "oldest" else list(reversed(visible))

    # THA-132: المرساة — أسطر المستند المطلوب بترتيبها الزمني (قد تكون أكثر من
    # سطر على حساب الطرف نفسه). تُحسب من `ordered` لا من `display_order` كي
    # يبقى «قبل» أوّلَها زمنياً و«بعد» آخرَها مهما كان اتجاه العرض.
    anchor_ids: list[int] = []
    if anchor_reference_type and anchor_reference_id:
        anchor_ids = [
            row[0] for row in ordered
            if row[3] == anchor_reference_type and row[4] == anchor_reference_id
        ]

    if anchor_ids:
        # النافذة تتمركز على المرساة بدل أن تبدأ من الطرف: مستندٌ قديم تلته
        # مئة حركة كان يقع خارج الصفحة الأولى دائماً.
        anchor_set = set(anchor_ids)
        positions = [i for i, row in enumerate(display_order) if row[0] in anchor_set]
        if positions:
            span = positions[-1] - positions[0] + 1
            pad = max((limit - span) // 2, 0)
            offset = max(positions[0] - pad, 0)

    page_ids = [row[0] for row in display_order[offset:offset + limit]]
    page = (
        JournalLine.objects.filter(id__in=page_ids)
        .select_related("journal")
    )
    by_id = {jl.id: jl for jl in page}
    rows = []
    anchor_set = set(anchor_ids)
    for lid in page_ids:
        jl = by_id.get(lid)
        if jl is None:
            continue
        j = jl.journal
        row = {
            "id": jl.id,
            "journal_id": j.id,
            "date": j.transaction_date.isoformat() if j.transaction_date else None,
            "reference_type": j.reference_type,
            "reference_id": j.reference_id,
            "description": jl.description or j.description or "",
            "debit": str(jl.base_debit),
            "credit": str(jl.base_credit),
            "balance_before": str(before_by_id[lid]),
            "running_balance": str(running_by_id[lid]),
        }
        if anchor_reference_type:
            row["is_anchor"] = lid in anchor_set
        rows.append(row)
    _attach_statement_document_links(rows, is_supplier=is_supplier)
    out = {
        "results": rows,
        "count": total,
        "limit": limit,
        "offset": offset,
        "ordering": normalized_ordering,
        "closing_balance": str(closing),
    }
    if anchor_reference_type:
        # «ماذا فعل هذا المستند بالحساب؟» — من لقطتَي الحلقة نفسها لا بحسابٍ
        # ثانٍ: الرصيد قبل أوّل أسطره، وبعد آخرها، والفرق هو أثره الفعلي على
        # الذمم (كامل القيد، لا «المتبقّي» منه).
        out["anchor"] = (
            {
                "line_ids": anchor_ids,
                "balance_before": str(before_by_id[anchor_ids[0]]),
                "balance_after": str(running_by_id[anchor_ids[-1]]),
                "effect": str(
                    running_by_id[anchor_ids[-1]] - before_by_id[anchor_ids[0]]
                ),
            }
            if anchor_ids
            else None
        )
    return out


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


def partner_posted_journal_effect(
    tenant_id: int,
    partner_id: int,
    journal_ids,
    *,
    supplier: bool,
) -> Decimal:
    """صافي أثر مجموعة قيود مرحّلة على رصيد شريك بالعملة الأساسية."""
    from django.db.models import Sum

    ids = [journal_id for journal_id in journal_ids if journal_id]
    if not ids:
        return Decimal("0.00")
    agg = JournalLine.objects.filter(
        tenant_id=tenant_id,
        partner_id=partner_id,
        journal_id__in=ids,
        journal__is_posted=True,
    ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
    debit = Decimal(str(agg["d"] or 0))
    credit = Decimal(str(agg["c"] or 0))
    return (credit - debit if supplier else debit - credit).quantize(Decimal("0.01"))


def attach_partner_posted_balance(rows, partner_id_field: str, *, supplier: bool, attr: str):
    """يضع رصيد الطرف المرحّل على صفوف **صفحة محمَّلة** باستعلام تجميعي واحد.

    البديل `annotate_partner_posted_balance` أدنى يولّد DEPENDENT SUBQUERY فيه
    GROUP BY، فتبني MySQL جدولاً مؤقتاً **لكل صف**: قياس على بيانات حقيقية
    (927 فاتورة، 11 ألف سطر قيد) أعطى 15–20 ثانية للقائمة و~1 ثانية لصفحة
    الخمسين — بينما هذا الشكل 27 ملّي ثانية للخمسين و129 للكل. الفهرسة لا
    تُصلحه: الجدول المؤقت لكل صف يبقى مهما فُهرِس (تُحقّق بـEXPLAIN).

    يُستعمل بعد الترقيم فقط: عدد الأطراف محدودٌ بحجم الصفحة، فالاستعلام واحد
    مهما كثرت الصفوف. الصفحة الفارغة لا تستعلم إطلاقاً.
    """
    from django.db.models import DecimalField, F, Sum

    rows = list(rows)
    tenant_ids = {getattr(row, "tenant_id", None) for row in rows} - {None}
    partner_ids = {getattr(row, partner_id_field, None) for row in rows} - {None}
    if not partner_ids or not tenant_ids:
        for row in rows:
            setattr(row, attr, Decimal("0.00"))
        return rows

    money = DecimalField(max_digits=18, decimal_places=2)
    balance_expression = (
        F("base_credit") - F("base_debit")
        if supplier
        else F("base_debit") - F("base_credit")
    )
    grouped = (
        JournalLine.objects
        .filter(
            tenant_id__in=tenant_ids,
            partner_id__in=partner_ids,
            journal__is_posted=True,
        )
        .values("tenant_id", "partner_id")
        .annotate(total=Sum(balance_expression, output_field=money))
    )
    totals = {
        (row["tenant_id"], row["partner_id"]): Decimal(str(row["total"] or 0))
        for row in grouped
    }
    for row in rows:
        key = (getattr(row, "tenant_id", None), getattr(row, partner_id_field, None))
        setattr(row, attr, totals.get(key, Decimal("0.00")))
    return rows


def annotate_partner_posted_balance(queryset, partner_id_field: str, *, supplier: bool, alias: str):
    """يضيف رصيد الشريك المرحّل إلى queryset واحد بلا استعلام لكل صف.

    ⚠ للصف الواحد (المستند المفتوح) أو للفلترة/الترتيب فقط — لا للقوائم:
    الاستعلام الفرعي المرتبط يُعاد تنفيذه لكل صف. للقوائم استعمل
    `attach_partner_posted_balance` أعلاه.
    """
    from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
    from django.db.models.functions import Coalesce

    money = DecimalField(max_digits=18, decimal_places=2)
    balance_expression = (
        F("base_credit") - F("base_debit")
        if supplier
        else F("base_debit") - F("base_credit")
    )
    balance = (
        JournalLine.objects
        .filter(
            tenant_id=OuterRef("tenant_id"),
            partner_id=OuterRef(partner_id_field),
            journal__is_posted=True,
        )
        .values("partner_id")
        .annotate(total=Sum(balance_expression, output_field=money))
        .values("total")[:1]
    )
    return queryset.annotate(**{
        alias: Coalesce(
            Subquery(balance, output_field=money),
            Value(Decimal("0.00"), output_field=money),
            output_field=money,
        ),
    })

