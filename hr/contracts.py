"""الشروط الفعّالة — من أين يأتي رقمُ الراتب في تاريخٍ بعينه.

**سؤالٌ واحد لكل من يحتاج رقماً**: `effective_terms(employee, day)`. تسأله
الرواتب فتعرف الأساسي والبدلات، ويسأله محرّك الإضافي فيعرف المضاعف. وبلا هذه
النقطة كان كل مستهلكٍ سيقرأ `Contract` بشروطه الخاصة، فينزاح حكمٌ عن حكم.

**والعقد يتقدّم على حقول `Employee` حين يكون نشطاً وحدهما fallback.** فشركةٌ
لم تبنِ عقودها بعد يبقى راتبها يُحسب كما كان بالضبط — وهذا شرط: الوحدة تُضاف
إلى نظامٍ يدفع رواتب اليوم، لا إلى صفحةٍ بيضاء.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils import timezone

from .models import Contract, Employee

logger = logging.getLogger(__name__)

ZERO = Decimal('0')

#: نافذة التنبيه الافتراضية لانتهاء العقود — شهر يكفي لتجديدٍ أو إشعارِ إنهاء.
EXPIRY_WARNING_DAYS = 30


@dataclass(frozen=True)
class Terms:
    """شروط الأجر السارية في يومٍ ما — ومن أين جاءت.

    `source` ليست زينة: شاشةُ الرواتب تقول للمحاسب «هذا الرقم من العقد #12»
    أو «من بطاقة الموظف»، فلا يبحث عن سبب اختلافٍ لا يراه.
    """

    pay_type: str
    monthly_salary: Decimal
    hourly_rate: Decimal
    overtime_multiplier: Decimal | None
    source: str  # 'contract' أو 'employee'
    contract_id: int | None = None
    earnings: tuple = field(default_factory=tuple)
    deductions: tuple = field(default_factory=tuple)

    @property
    def earnings_total(self) -> Decimal:
        return sum((amount for _name, amount in self.earnings), ZERO)

    @property
    def deductions_total(self) -> Decimal:
        return sum((amount for _name, amount in self.deductions), ZERO)


def active_contract(employee, day=None):
    """العقد الساري في هذا اليوم — أحدثُ عقدٍ نشطٍ يغطّيه."""
    day = day or timezone.localdate()
    for contract in (
        Contract.objects
        .filter(employee=employee, status=Contract.STATUS_ACTIVE)
        .prefetch_related('components')
        .order_by('-start_date', '-id')
    ):
        if contract.covers(day):
            return contract
    return None


def effective_terms(employee, day=None) -> Terms:
    """شروط أجر الموظف في يومٍ ما — من عقده النشط، وإلا من بطاقته."""
    contract = active_contract(employee, day)
    if contract is None:
        return Terms(
            pay_type=employee.pay_type,
            monthly_salary=employee.monthly_salary or ZERO,
            hourly_rate=employee.hourly_rate or ZERO,
            overtime_multiplier=None,
            source='employee',
        )

    earnings, deductions = [], []
    for component in contract.components.all():
        bucket = earnings if component.kind == component.KIND_EARNING else deductions
        bucket.append((component.name, Decimal(component.amount or 0)))

    return Terms(
        pay_type=contract.pay_type,
        monthly_salary=contract.monthly_salary or ZERO,
        hourly_rate=contract.hourly_rate or ZERO,
        overtime_multiplier=contract.overtime_multiplier,
        source='contract',
        contract_id=contract.pk,
        earnings=tuple(earnings),
        deductions=tuple(deductions),
    )


def daily_rate(employee, terms) -> Decimal:
    """أجر اليوم — أساس خصم الغياب، مبنيّاً على الشروط السارية.

    أيام الدوام الشهرية تبقى على بطاقة الموظف حتى مع وجود عقد: هي أساسُ
    اشتقاقٍ متفقٌ عليه لا شرطُ أجر، وتكرارُها في العقد كان يفتح بابَ رقمين
    ينزاحان.
    """
    days = employee.working_days_per_month or ZERO
    if terms.pay_type != Employee.PAY_MONTHLY or days <= 0:
        return ZERO
    return (terms.monthly_salary or ZERO) / days


def minute_rate(employee, terms) -> Decimal:
    """أجر الدقيقة — أساس خصم التأخير وتسعير الإضافي.

    للموظف الجزئي يُشتقّ من أجر ساعته مباشرةً؛ وللدائم من أجر يومه على ساعات
    دوامه. وبلا هذا الفرق كان الإضافيُّ للجزئي يُسعَّر بصفر (لأن `daily_rate`
    تعود صفراً لغير الشهري) فيعمل ساعاتٍ زائدة بلا أجر.
    """
    if terms.pay_type == Employee.PAY_HOURLY:
        return (terms.hourly_rate or ZERO) / Decimal('60')
    hours = employee.standard_hours_per_day or ZERO
    if hours <= 0:
        return ZERO
    return daily_rate(employee, terms) / (hours * Decimal('60'))


def overtime_multiplier(employee, day, terms=None) -> Decimal:
    """مضاعف الساعة الإضافية — العقد أولاً، ثم الوردية، ثم بلا مضاعف.

    الترتيب مقصود: الاتفاق المكتوب يغلب قاعدةَ الجدول، والجدولُ يغلب الصمت.
    وحين لا عقدَ ولا وردية يعود `1` لا صفر — الساعة الإضافية بلا مضاعفٍ تبقى
    ساعةَ عملٍ تُدفع، وصفرٌ هنا كان يبتلع أجراً استُحقّ.
    """
    from . import attendance as engine

    terms = terms or effective_terms(employee, day)
    if terms.overtime_multiplier is not None:
        return Decimal(terms.overtime_multiplier)
    shift = engine.shift_for(employee, day)
    if shift is not None and shift.overtime_multiplier is not None:
        return Decimal(shift.overtime_multiplier)
    return Decimal('1')


def expiring_contracts(tenant_id, *, within_days=EXPIRY_WARNING_DAYS, today=None):
    """عقودٌ تنتهي خلال النافذة — ومعها المنتهية التي لم تُغلق بعد.

    **محسوبٌ بلا مجدول**: لا cron في هذه المنصة، فالتنبيه سؤالٌ يُطرح عند فتح
    الشاشة لا رسالةٌ تُرسَل ليلاً. ثمنُه أن من لا يفتح التطبيق لا يُنبَّه —
    مقبولٌ مقابل ألّا نعلّق ميزةً على بنيةٍ غير موجودة.
    """
    import datetime

    today = today or timezone.localdate()
    horizon = today + datetime.timedelta(days=max(0, int(within_days)))
    return (
        Contract.objects
        .filter(
            tenant_id=tenant_id,
            status=Contract.STATUS_ACTIVE,
            end_date__isnull=False,
            end_date__lte=horizon,
        )
        .select_related('employee')
        .order_by('end_date')
    )
