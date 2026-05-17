import datetime
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Account, ExchangeRate, JournalHeader, JournalLine, AccountingAuditLog, FiscalPeriod, CostCenter
from decimal import Decimal
from partners.models import Partner
from tenants.models import Currency

logger = logging.getLogger(__name__)


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

