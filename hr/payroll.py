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
    if not employee.account_id and employee.pk:
        # النسخة في الذاكرة قد تكون قديمة: عمليةٌ سابقة في نفس الطلب (صرفُ
        # سلفة، أو دورةُ مسيرٍ على الموظف نفسه) أنشأت الحساب وحفظته، وهذا
        # الكائن ما زال يحمل `None`. القرار على قيمةٍ قديمة كان يُنشئ **حساباً
        # ثانياً للموظف الواحد** فينشقّ رصيده بين حسابين بلا أن يشتكي شيء.
        stored = Employee.objects.filter(pk=employee.pk).values_list(
            "account_id", flat=True).first()
        if stored:
            employee.account_id = stored

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

def attendance_totals(employee: Employee, period_start, period_end) -> dict:
    """مجاميع الحضور المشتقّ في الفترة — أو أصفارٌ إن لم تكن الوحدة تعمل.

    **مصدرٌ ثانٍ يُجمَع لا يحلّ محلّ الأول**: `AttendanceAdjustment` اليدوية
    تبقى كما هي (تصحيحاتٌ ومدخلاتٌ إدارية)، و`AttendanceDay` يضيف إليها ما
    اشتقّه محرّك البصمات. توليدُ صفوف adjustments من الحضور كان البديل، وكان
    يعني حذفاً وإعادةَ توليد عند كل إعادة حساب — ولا يعبّر عن الإضافي أصلاً
    (لا نوعَ له في ذلك النموذج).

    الاستيراد كسولٌ عمداً: قبل بناء وحدة الحضور لم يكن `AttendanceDay` موجوداً،
    والدالّة تعمل بلا وحدةٍ كما تعمل معها.
    """
    zero = {"absence_days": Decimal("0"), "late_minutes": 0, "overtime_minutes": 0}
    try:
        from .models import AttendanceDay
    except ImportError:  # pragma: no cover — قبل وجود الوحدة
        return zero

    rows = AttendanceDay.objects.filter(
        employee=employee, date__gte=period_start, date__lte=period_end)
    totals = dict(zero)
    for row in rows.values("absence_days", "late_minutes", "overtime_minutes"):
        totals["absence_days"] += row["absence_days"] or Decimal("0")
        totals["late_minutes"] += row["late_minutes"] or 0
        totals["overtime_minutes"] += row["overtime_minutes"] or 0
    return totals


def advance_installment(employee: Employee) -> tuple:
    """قسط السلف المستحقّ هذا الشهر، والسلف التي يخصّها.

    السلفة **المصروفة** وحدها تُخصم: سلفةٌ اعتُمدت ولم يُصرَف مالُها ليست
    دَيناً بعد، وخصمُ قسطها يأخذ من الموظف مقابل ما لم يقبضه.

    والقسط لا يتجاوز المتبقّي — آخرُ قسطٍ يُغلق الرصيد مهما كان أصغر من قيمته.
    """
    from .models import Advance

    total = Decimal("0")
    picked = []
    for advance in Advance.objects.filter(
            employee=employee, status=Advance.STATUS_OPEN).order_by("date", "id"):
        if not advance.is_disbursed:
            continue
        due = min(
            money(advance.monthly_installment or 0),
            money(advance.remaining or 0),
        )
        if due <= 0:
            continue
        total += due
        picked.append((advance, due))
    return money(total), picked


def compute_payslip(employee: Employee, period_start, period_end, *,
                    allowances=0, other_deductions=0) -> dict:
    """أرقام كشف الفترة، مشتقّةً من شروط الموظف وسجلاته — بلا حفظ.

    الجزئي: الاستحقاق = مجموع ساعاته المسجّلة × أجر الساعة. لا خصم غياب —
    الغياب عنده هو ببساطة ساعةٌ لم تُسجَّل.

    الدائم: الاستحقاق = الراتب الشهري، ويُخصم منه الغياب بمعدّل اليوم
    والتأخير بمعدّل الدقيقة.

    ومصادر الأرقام ثلاثة تُجمَع ولا يُلغي بعضُها بعضاً:
    1. **الشروط السارية** (`hr/contracts.py`) — العقد النشط إن وُجد، وإلا
       بطاقة الموظف. وبنودُ العقد الثابتة تصبّ في البدلات والخصومات.
    2. **الحضور المشتقّ** (`AttendanceDay`) — غيابٌ وتأخيرٌ وإضافيّ.
    3. **المدخلات اليدوية** (`AttendanceAdjustment` و`WorkLog`) كما كانت.

    والقسط: `net` ما يدخل الدفاتر، و`net_payable` ما يقبضه الموظف.
    """
    if period_end < period_start:
        raise ValidationError({"period_end": "نهاية الفترة قبل بدايتها."})

    from .contracts import daily_rate, effective_terms, minute_rate, overtime_multiplier

    terms = effective_terms(employee, period_end)
    day_rate = daily_rate(employee, terms)
    min_rate = minute_rate(employee, terms)

    hours = Decimal("0")
    absence_days = Decimal("0")
    late_minutes = 0
    absence_deduction = Decimal("0")
    late_deduction = Decimal("0")

    derived = attendance_totals(employee, period_start, period_end)
    overtime_minutes = derived["overtime_minutes"]

    if terms.pay_type == Employee.PAY_HOURLY:
        rate = terms.hourly_rate or Decimal("0")
        hours = sum(
            (log.hours or Decimal("0")) for log in WorkLog.objects.filter(
                employee=employee, date__gte=period_start, date__lte=period_end)
        ) or Decimal("0")
        gross = money(Decimal(hours) * rate)
        # لا خصم غياب للجزئي — لكن تأخيره وغيابه يُسجَّلان للعِلم كما في التقارير.
        absence_days = derived["absence_days"]
        late_minutes = derived["late_minutes"]
    else:
        rate = terms.monthly_salary or Decimal("0")
        gross = money(rate)
        adjustments = AttendanceAdjustment.objects.filter(
            employee=employee, date__gte=period_start, date__lte=period_end)
        for adj in adjustments:
            if adj.kind == AttendanceAdjustment.KIND_ABSENCE:
                absence_days += adj.days or Decimal("0")
                if adj.is_deductible:
                    absence_deduction += (adj.days or Decimal("0")) * day_rate
            else:
                late_minutes += adj.minutes or 0
                if adj.is_deductible:
                    late_deduction += Decimal(adj.minutes or 0) * min_rate
        # ثم الحضور المشتقّ فوقها — والغياب المشتقّ مخصومٌ دائماً: العذر
        # (إجازةً كان أو عطلة) لا يصل إلى هنا أصلاً لأن `AttendanceDay`
        # يُصفّر `absence_days` لتلك الحالات.
        absence_days += derived["absence_days"]
        absence_deduction += derived["absence_days"] * day_rate
        late_minutes += derived["late_minutes"]
        late_deduction += Decimal(derived["late_minutes"]) * min_rate

    overtime_pay = money(
        Decimal(overtime_minutes) * min_rate * overtime_multiplier(employee, period_end, terms))

    # بنود العقد الثابتة تُضاف إلى ما أدخله المستخدم يدوياً في الكشف.
    allowances = money(Decimal(allowances or 0) + terms.earnings_total)
    other_deductions = money(Decimal(other_deductions or 0) + terms.deductions_total)
    absence_deduction = money(absence_deduction)
    late_deduction = money(late_deduction)
    net = money(
        gross + overtime_pay + allowances
        - absence_deduction - late_deduction - other_deductions)

    installment, _advances = advance_installment(employee)
    # القسط لا يبتلع الراتب كلّه: ما يُخصم لا يتجاوز الصافي، والباقي يُرحَّل
    # للشهر التالي — موظفٌ يقبض صفراً هذا الشهر بسبب سلفةٍ مشكلةٌ إنسانية
    # قبل أن تكون محاسبية.
    installment = min(installment, max(net, Decimal("0")))

    return {
        "pay_type": terms.pay_type,
        "rate": money(rate),
        "worked_hours": money(hours),
        "absence_days": money(absence_days),
        "late_minutes": late_minutes,
        "overtime_minutes": overtime_minutes,
        "overtime_pay": overtime_pay,
        "gross": gross,
        "allowances": allowances,
        "absence_deduction": absence_deduction,
        "late_deduction": late_deduction,
        "other_deductions": other_deductions,
        "net": net,
        "advance_deduction": installment,
        "net_payable": money(net - installment),
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
        _consume_advances(payslip)

    logger.info("payroll.payslip_posted tenant=%s payslip=%s net=%s",
                tenant.pk, payslip.pk, net)
    return payslip


def _consume_advances(payslip: Payslip) -> None:
    """ينقص متبقّي السلف بقدر ما خُصم في هذا الكشف — **بلا قيدٍ ثانٍ**.

    القسط تصافٍ داخل حساب الموظف: صرفُ السلفة كان مديناً على حسابه، وقيدُ
    الكشف يُدائنه بكامل `net` (لا بـ`net_payable`)، فيبقى فرقُ القسط رصيداً
    مديناً يتناقص شهراً بعد شهر. أي قيدٍ إضافي هنا يعدّ السداد مرّتين.

    والربط عند **الترحيل** لا عند الاحتساب: مسودّةٌ تُحسب عشر مرّات، وربطُ
    الخصم بالاحتساب كان ينقص الرصيد عشراً.
    """
    from .models import Advance, PayslipAdvance

    due = money(payslip.advance_deduction or 0)
    if due <= 0:
        return
    remaining = due
    for advance in Advance.objects.select_for_update().filter(
            employee=payslip.employee, status=Advance.STATUS_OPEN).order_by("date", "id"):
        if remaining <= 0:
            break
        if not advance.is_disbursed:
            continue
        take = min(money(advance.remaining or 0), remaining)
        if take <= 0:
            continue
        advance.remaining = money(Decimal(advance.remaining) - take)
        if advance.remaining <= 0:
            advance.status = Advance.STATUS_SETTLED
        advance.save(update_fields=["remaining", "status", "updated_at"])
        PayslipAdvance.objects.create(payslip=payslip, advance=advance, amount=take)
        remaining -= take


def _release_advances(payslip: Payslip) -> None:
    """يعيد ما خُصم من السلف عند إلغاء ترحيل الكشف — عكسٌ تامّ لا تقريبيّ.

    نقرأ ما خُصم فعلاً من `PayslipAdvance` لا نعيد حسابه: قواعد الأقساط قد
    تكون تغيّرت بين الترحيل وإلغائه، وإعادةُ الحساب كانت تُرجِع رقماً آخر.
    """
    from .models import PayslipAdvance

    for link in PayslipAdvance.objects.select_related("advance").filter(payslip=payslip):
        advance = link.advance
        advance.remaining = money(Decimal(advance.remaining) + Decimal(link.amount))
        if advance.remaining > 0 and advance.status == advance.STATUS_SETTLED:
            advance.status = advance.STATUS_OPEN
        advance.save(update_fields=["remaining", "status", "updated_at"])
        link.delete()


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
    # ما خُصم من السلف يعود بالضبط — وإلا بقي جزءٌ من دَينٍ مسدَّداً على الورق
    # وغيرَ مسدَّد في الحساب.
    _release_advances(payslip)
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
