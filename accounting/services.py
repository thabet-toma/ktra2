import datetime
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Account, ExchangeRate, JournalHeader, JournalLine, AccountingAuditLog, FiscalPeriod, CostCenter
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
        
        # Validate Partner if Present
        if partner_id:
            if not Partner.objects.filter(id=partner_id).exists():
                 raise ValidationError(f"Partner ID {partner_id} does not exist.")
        
        # Validate Cost Center if Present
        if cost_center_id:
             if not CostCenter.objects.filter(id=cost_center_id).exists():
                  raise ValidationError(f"Cost Center ID {cost_center_id} does not exist.")

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
) -> JournalHeader:
    """دالة ترحيل مركزية ذرّية — المسار الوحيد لإنشاء + ترحيل أي قيد محاسبي.

    تفرض:
    - فترة مالية مفتوحة
    - توازن دقيق (debit == credit بعد quantize)
    - جميع الأسطر تابعة لنفس tenant
    - idempotency عبر (reference_type, reference_id)
    - select_for_update لمنع السباق

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

        jh = JournalHeader.objects.create(
            tenant_id=tenant_id,
            transaction_date=transaction_date,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description[:500],
            is_posted=True,
            currency=currency,
            exchange_rate=exchange_rate,
        )

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

