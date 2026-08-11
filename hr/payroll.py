"""محرّك الرواتب — الاشتقاق والحسابات والترحيل.

**لا مسار محاسبي موازٍ**: كل قيد هنا يمرّ بـ`accounting.services.post_journal`
وكل تراجع بـ`unpost_document` — نفس المسار الذي تمرّ به الفواتير والسندات،
فيرث الرواتب مجاناً: التحقق من الفترة المالية، التوازن الدقيق، طبيعة الحساب،
idempotency، وحجز رقم القيد وإعادة استخدامه.

**ربط الشجرة** يكرّر نمط البنوك والصناديق حرفياً (`get_bank_parent_account` +
`allocate_child_account_code`): بندٌ أبٌ واحد لكل شركة، وحسابٌ ابنٌ لكل موظف.

    2112 رواتب مستحقة للموظفين (Salaries Payable)   ← الأب
      └── 2112E0001  محمد ...                       ← حساب الموظف
    5201 الرواتب والأجور                            ← المصروف (قائم أصلاً)

دورة المستند:

    اعتماد الكشف:   من ح/ 5201 المصروف        إلى ح/ حساب الموظف
    صرف الراتب:     من ح/ حساب الموظف         إلى ح/ الصندوق أو البنك

فرصيد حساب الموظف الدائن = ما له عندنا ولم يُصرف بعد.
"""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from rest_framework.exceptions import ValidationError

from accounting.cashbox import allocate_child_account_code
from accounting.models import Account, JournalLine
from accounting.services import post_journal, resolve_default_cash_account, unpost_document
from tenants.services import ensure_operational_account

from .models import AttendanceAdjustment, Employee, Payslip, PayrollPayment, WorkLog

logger = logging.getLogger(__name__)

#: بند الرواتب في الشجرة. 2110 محجوز لـGR/IR و2111 لشيكات الدفع — 2112 أول شاغر.
PAYROLL_PARENT_CODE = "2112"
PAYROLL_PARENT_NAME = "رواتب مستحقة للموظفين (Salaries Payable)"
#: حساب المصروف — موجود في الشجرة المعيارية (`tenants.services.COA_DATA`).
PAYROLL_EXPENSE_CODE = "5201"

REF_PAYSLIP = "PAYROLL_PAYSLIP"
REF_PAYMENT = "PAYROLL_PAYMENT"

CENTS = Decimal("0.01")


def money(value) -> Decimal:
    """كل مبلغ يُخزَّن أو يُرحَّل مقرّباً لقرشين — لا كسور خفية تكسر التوازن."""
    return Decimal(str(value or 0)).quantize(CENTS, rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────────────────
#  الشجرة: بند الرواتب وحساب كل موظف
# ─────────────────────────────────────────────────────────

def get_payroll_parent_account(tenant):
    """بند «رواتب مستحقة للموظفين» — يُنشأ تحت الالتزامات المتداولة إن غاب.

    مرآة `accounting.services.get_bank_parent_account`: بلا أبٍ لا مكان لحسابات
    الموظفين، وإنشاؤه مرة واحدة أفضل من ردّ المستخدم على شركة بُذرت قبل الرواتب.
    """
    acc = Account.objects.filter(tenant=tenant, code=PAYROLL_PARENT_CODE).first()
    if acc:
        return acc
    current_liabilities = (
        Account.objects.filter(tenant=tenant, code="21").first()
        or Account.objects.filter(tenant=tenant, account_type="Liability",
                                  code__startswith="21").order_by("code").first()
        or Account.objects.filter(tenant=tenant, account_type="Liability").order_by("code").first()
    )
    acc = Account.objects.create(
        tenant=tenant, code=PAYROLL_PARENT_CODE, name=PAYROLL_PARENT_NAME,
        parent=current_liabilities, account_type="Liability", is_active=True,
    )
    logger.info(
        "payroll.parent_account_created tenant=%s code=%s parent=%s",
        getattr(tenant, "TenantID", tenant), PAYROLL_PARENT_CODE,
        current_liabilities.code if current_liabilities else "-",
    )
    return acc


def get_payroll_expense_account(tenant):
    """حساب مصروف الرواتب (5201) — يُضمن وجوده كما تُضمن حسابات الشيكات."""
    return ensure_operational_account(tenant, PAYROLL_EXPENSE_CODE)


def next_employee_code(tenant) -> str:
    """رقم الموظف التالي — تسلسل بسيط لكل شركة.

    الرقم إلزامي فعلياً (مفتاح فريد مع الشركة)، وتركه للمستخدم يعني تصادماً
    عند أول موظفين بلا رقم. من كتب رقمه احتُرِم، ومن تركه فارغاً رُقِّم له.
    """
    used = set(
        Employee.objects.filter(tenant=tenant).values_list("code", flat=True)
    )
    numbers = [int(code) for code in used if str(code).isdigit()]
    candidate = (max(numbers) + 1) if numbers else 1
    while str(candidate) in used:
        candidate += 1
    return str(candidate)


def ensure_employee_account(employee: Employee):
    """حساب الموظف في الشجرة — يُنشأ مرة واحدة ويُعاد استعماله بعدها.

    الاسم يتبع اسم الموظف عند تغييره، فلا يبقى في الشجرة اسمٌ هجره صاحبه.
    """
    tenant = employee.tenant
    label = (employee.name or "").strip() or f"موظف #{employee.pk}"
    if employee.account_id:
        account = employee.account
        if account.name != label[:100]:
            account.name = label[:100]
            account.save(update_fields=["name"])
        return account

    parent = get_payroll_parent_account(tenant)
    code = allocate_child_account_code(
        parent, tenant,
        marker="E",
        seed=Employee.objects.filter(tenant=tenant).exclude(account__isnull=True).count() + 1,
        fallback_prefix=PAYROLL_PARENT_CODE,
    )
    account = Account.objects.create(
        tenant=tenant, code=code, name=label[:100], parent=parent,
        account_type=parent.account_type or "Liability", is_active=True,
    )
    employee.account = account
    employee.save(update_fields=["account"])
    logger.info(
        "payroll.employee_account_created tenant=%s employee=%s account=%s(%s)",
        getattr(tenant, "TenantID", tenant), employee.pk, account.pk, code,
    )
    return account


def employee_balances(tenant_id: int, employees) -> dict:
    """{معرّف الموظف: رصيده} باستعلام تجميعي **واحد** للصفحة كلها.

    الرصيد = دائن حسابه ناقص مدينه من القيود المرحّلة وحدها. استعلامٌ لكل صف
    هنا يعني عشرات الاستعلامات لصفحة موظفين واحدة — الدرس نفسه المستفاد من
    أرصدة الأطراف في القوائم.
    """
    from django.db.models import Sum

    by_account = {
        e.account_id: e.pk for e in employees if e.account_id
    }
    if not by_account:
        return {e.pk: Decimal("0.00") for e in employees}

    rows = (
        JournalLine.objects
        .filter(tenant_id=tenant_id, account_id__in=by_account.keys(),
                journal__is_posted=True)
        .values("account_id")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
    )
    balances = {e.pk: Decimal("0.00") for e in employees}
    for row in rows:
        employee_id = by_account.get(row["account_id"])
        if employee_id is not None:
            balances[employee_id] = money((row["credit"] or 0) - (row["debit"] or 0))
    return balances


def employee_balance(employee: Employee) -> Decimal:
    """رصيد موظف واحد — غلاف رقيق حول `employee_balances`."""
    return employee_balances(employee.tenant_id, [employee]).get(employee.pk, Decimal("0.00"))


# ─────────────────────────────────────────────────────────
#  الاحتساب — مصدر واحد للأرقام: المعاينة والحفظ يستدعيانه معاً
# ─────────────────────────────────────────────────────────

def compute_payslip(employee: Employee, period_start, period_end, *,
                    allowances=0, other_deductions=0) -> dict:
    """أرقام كشف الفترة، مشتقّةً من نوع الموظف وسجلاته — بلا حفظ.

    الجزئي: الاستحقاق = مجموع ساعاته المسجّلة × أجر الساعة. لا خصم غياب —
    الغياب عنده هو ببساطة ساعةٌ لم تُسجَّل.

    الدائم: الاستحقاق = الراتب الشهري، ويُخصم منه الغياب بمعدّل اليوم
    والتأخير بمعدّل الدقيقة، ولا يُحتسب إلا ما وُسم قابلاً للخصم.
    """
    if period_end < period_start:
        raise ValidationError({"period_end": "نهاية الفترة قبل بدايتها."})

    hours = Decimal("0")
    absence_days = Decimal("0")
    late_minutes = 0
    absence_deduction = Decimal("0")
    late_deduction = Decimal("0")

    if employee.pay_type == Employee.PAY_HOURLY:
        rate = employee.hourly_rate or Decimal("0")
        hours = sum(
            (log.hours or Decimal("0")) for log in WorkLog.objects.filter(
                employee=employee, date__gte=period_start, date__lte=period_end)
        ) or Decimal("0")
        gross = money(Decimal(hours) * rate)
    else:
        rate = employee.monthly_salary or Decimal("0")
        gross = money(rate)
        adjustments = AttendanceAdjustment.objects.filter(
            employee=employee, date__gte=period_start, date__lte=period_end)
        for adj in adjustments:
            if adj.kind == AttendanceAdjustment.KIND_ABSENCE:
                absence_days += adj.days or Decimal("0")
                if adj.is_deductible:
                    absence_deduction += (adj.days or Decimal("0")) * employee.daily_rate
            else:
                late_minutes += adj.minutes or 0
                if adj.is_deductible:
                    late_deduction += Decimal(adj.minutes or 0) * employee.minute_rate

    allowances = money(allowances)
    other_deductions = money(other_deductions)
    absence_deduction = money(absence_deduction)
    late_deduction = money(late_deduction)
    net = money(gross + allowances - absence_deduction - late_deduction - other_deductions)

    return {
        "pay_type": employee.pay_type,
        "rate": money(rate),
        "worked_hours": money(hours),
        "absence_days": money(absence_days),
        "late_minutes": late_minutes,
        "gross": gross,
        "allowances": allowances,
        "absence_deduction": absence_deduction,
        "late_deduction": late_deduction,
        "other_deductions": other_deductions,
        "net": net,
    }


def apply_computation(payslip: Payslip) -> Payslip:
    """يعيد احتساب الكشف من سجلات موظفه — يُستدعى عند كل حفظ لمسودّة."""
    if payslip.status == Payslip.STATUS_POSTED:
        raise ValidationError("كشف مرحّل لا يُعاد احتسابه — ألغِ ترحيله أولاً.")
    numbers = compute_payslip(
        payslip.employee, payslip.period_start, payslip.period_end,
        allowances=payslip.allowances, other_deductions=payslip.other_deductions,
    )
    for field, value in numbers.items():
        setattr(payslip, field, value)
    return payslip


# ─────────────────────────────────────────────────────────
#  الترحيل
# ─────────────────────────────────────────────────────────

def post_payslip(payslip: Payslip, *, user=None) -> Payslip:
    """اعتماد الكشف: مصروف الرواتب مديناً وذمّة الموظف دائنة."""
    if payslip.status == Payslip.STATUS_POSTED:
        raise ValidationError("الكشف مرحّل بالفعل.")
    net = money(payslip.net)
    if net <= 0:
        raise ValidationError("لا يُرحَّل كشف صافيه صفر أو أقل — راجع الساعات والخصومات.")

    tenant = payslip.tenant
    expense = get_payroll_expense_account(tenant)
    if expense is None:
        raise ValidationError(
            f"حساب «الرواتب والأجور» ({PAYROLL_EXPENSE_CODE}) غير موجود في شجرة الحسابات."
        )
    employee_account = ensure_employee_account(payslip.employee)

    with transaction.atomic():
        post_journal(
            tenant_id=tenant.pk,
            transaction_date=payslip.period_end,
            reference_type=REF_PAYSLIP,
            reference_id=payslip.pk,
            description=f"راتب {payslip.employee.name} — {payslip.period_start} إلى {payslip.period_end}",
            lines_data=[
                {"account": expense.pk, "debit": net, "credit": 0,
                 "description": f"راتب {payslip.employee.name}"},
                {"account": employee_account.pk, "debit": 0, "credit": net,
                 "description": f"مستحق لـ{payslip.employee.name}"},
            ],
            user=user,
        )
        from django.utils import timezone

        payslip.status = Payslip.STATUS_POSTED
        payslip.posted_at = timezone.now()
        payslip.posted_by = user if getattr(user, "is_authenticated", False) else None
        payslip.save(update_fields=["status", "posted_at", "posted_by", "updated_at"])

    logger.info("payroll.payslip_posted tenant=%s payslip=%s net=%s",
                tenant.pk, payslip.pk, net)
    return payslip


def unpost_payslip(payslip: Payslip, *, user=None) -> dict:
    """إلغاء ترحيل الكشف — ممنوع إن صُرف منه شيء (وإلا صار الصرف بلا استحقاق)."""
    if payslip.status != Payslip.STATUS_POSTED:
        raise ValidationError("الكشف غير مرحّل.")
    if payslip.payments.exists():
        raise ValidationError(
            "لا يمكن إلغاء ترحيل كشف صُرفت منه دفعات — احذف سندات الصرف المرتبطة أولاً."
        )
    result = unpost_document(
        tenant_id=payslip.tenant_id,
        reference_id=payslip.pk,
        journal_reference_types=[REF_PAYSLIP],
        user=user,
        document_label=f"كشف راتب #{payslip.pk}",
    )
    payslip.status = Payslip.STATUS_DRAFT
    payslip.posted_at = None
    payslip.posted_by = None
    payslip.save(update_fields=["status", "posted_at", "posted_by", "updated_at"])
    logger.info("payroll.payslip_unposted tenant=%s payslip=%s", payslip.tenant_id, payslip.pk)
    return result


def resolve_payment_source(tenant, account_id=None):
    """مصدر الدفع: الحساب المختار، وإلا الصندوق الافتراضي للشركة."""
    if account_id:
        account = Account.objects.filter(tenant=tenant, pk=account_id).first()
        if account is None:
            raise ValidationError({"cash_account": "حساب الدفع غير موجود في هذه الشركة."})
        return account
    account = resolve_default_cash_account(tenant.pk)
    if account is None:
        raise ValidationError(
            "لا يوجد صندوق افتراضي للشركة — اختر حساب الدفع يدوياً أو عيّن صندوقاً افتراضياً."
        )
    return account


def post_payroll_payment(payment: PayrollPayment, *, user=None) -> PayrollPayment:
    """صرف الراتب: ذمّة الموظف مدينة والصندوق دائن."""
    amount = money(payment.amount)
    if amount <= 0:
        raise ValidationError({"amount": "مبلغ الصرف يجب أن يكون أكبر من صفر."})

    tenant = payment.tenant
    source = payment.cash_account or resolve_payment_source(tenant)
    employee_account = ensure_employee_account(payment.employee)

    with transaction.atomic():
        if payment.cash_account_id != source.pk:
            payment.cash_account = source
            payment.save(update_fields=["cash_account"])
        post_journal(
            tenant_id=tenant.pk,
            transaction_date=payment.date,
            reference_type=REF_PAYMENT,
            reference_id=payment.pk,
            description=f"صرف راتب {payment.employee.name} من {source.name}",
            lines_data=[
                {"account": employee_account.pk, "debit": amount, "credit": 0,
                 "description": f"صرف مستحق {payment.employee.name}"},
                {"account": source.pk, "debit": 0, "credit": amount,
                 "description": f"صرف راتب {payment.employee.name}"},
            ],
            user=user,
        )
    logger.info("payroll.payment_posted tenant=%s payment=%s amount=%s",
                tenant.pk, payment.pk, amount)
    return payment


def unpost_payroll_payment(payment: PayrollPayment, *, user=None) -> dict:
    """يحذف قيد الصرف — يسبق حذف السند نفسه."""
    result = unpost_document(
        tenant_id=payment.tenant_id,
        reference_id=payment.pk,
        journal_reference_types=[REF_PAYMENT],
        user=user,
        document_label=f"صرف راتب #{payment.pk}",
    )
    logger.info("payroll.payment_unposted tenant=%s payment=%s",
                payment.tenant_id, payment.pk)
    return result
