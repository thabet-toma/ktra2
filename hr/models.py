from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from tenants.models import Tenant

class Task(models.Model):
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('IN_PROGRESS', 'In Progress'),
        ('WAITING_FOR_REVIEW', 'Waiting For Review'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
    ]
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tasks')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    
    total_work_time = models.IntegerField(default=0) # Stored in milliseconds or seconds
    work_start_time = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.status}"

class TaskSubmission(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    id = models.AutoField(primary_key=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='submissions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    items = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewer_notes = models.TextField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reviewed_submissions')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Late', 'Late'),
    ]
    
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    punch_in_time = models.DateTimeField(null=True, blank=True)
    punch_out_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Present')
    notes = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['user', 'date']]

class PersonalExpense(models.Model):
    """مصروف شخصي — دفتر جيب المستخدم، لا دفاتر الشركة.

    قرارات تصميم مقصودة (لا تُعكس بلا طلب المالك):
    - **بلا ربط بشجرة الحسابات**: لا FK إلى Account ولا JournalHeader ولا ترحيل.
      التسجيل هنا لا يُنتج قيداً ولا يظهر في أي تقرير مالي للشركة.
    - **بلا tenant**: المصروف يتبع صاحبه لا الشركة النشطة، فلا يختفي عند تبديل
      الشركة. العزل الوحيد المعتبر هو المستخدم.
    - **الفئة مفتاح نصّي لا قائمة مغلقة**: الكتالوج صار لكل مستخدم
      (`PersonalExpenseCategory`) فيعيد تسميته ويضيف إليه؛ `CATEGORY_CHOICES`
      بقيت بذرة الافتراضيات ومرجع التسمية لمن لم يخصّص كتالوجه بعد.
    """
    CATEGORY_CHOICES = [
        ('food', 'طعام وشراب'),
        ('transport', 'مواصلات'),
        ('bills', 'فواتير واشتراكات'),
        ('health', 'صحة'),
        ('shopping', 'تسوّق'),
        ('family', 'أسرة وتعليم'),
        ('entertainment', 'ترفيه'),
        ('other', 'أخرى'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_expenses')
    sheet = models.ForeignKey(
        'PersonalExpenseSheet', on_delete=models.CASCADE, null=True, blank=True,
        related_name='expenses',
    )
    date = models.DateField()
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, default='other')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    is_paid = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_personal_expenses'
        indexes = [
            models.Index(fields=['user', '-date'], name='hrpe_user_date'),
            models.Index(fields=['user', 'is_paid'], name='hrpe_user_paid'),
            models.Index(fields=['user', 'sheet'], name='hrpe_user_sheet'),
        ]

    def __str__(self):
        return f"{self.title} - {self.amount}"

class PersonalExpenseSheet(models.Model):
    """ورقة مصاريف — تبويب بأسلوب إكسل داخل دفتر المستخدم الشخصي.

    كل مصروف يسكن ورقة واحدة، والورقة تتبع صاحبها كما يتبعه المصروف (بلا
    tenant، بلا أثر محاسبي). حذف الورقة يحذف مصاريفها — لذا يمنع الخادم حذف
    الورقة الأخيرة كي لا يفقد المستخدم دفتره كاملاً بضغطة.
    """
    DEFAULT_NAME = 'الورقة 1'

    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_expense_sheets')
    name = models.CharField(max_length=60)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_personal_expense_sheets'
        ordering = ['position', 'id']
        unique_together = [['user', 'name']]

    def __str__(self):
        return self.name

    @classmethod
    def ensure_default(cls, user):
        """ورقة أولى لمن لا ورقة له — يستدعيها العرض قبل أي قائمة."""
        sheet = cls.objects.filter(user=user).order_by('position', 'id').first()
        if sheet is None:
            sheet = cls.objects.create(user=user, name=cls.DEFAULT_NAME, position=0)
        return sheet

class PersonalExpenseCategory(models.Model):
    """فئة مصاريف يملكها المستخدم — يعيد تسميتها ويضيف غيرها.

    `key` هو ما يُخزَّن في `PersonalExpense.category` (لا الاسم)، فتبقى المصاريف
    مرتبطة بفئتها بعد إعادة التسمية. المفاتيح الثمانية الأولى مطابقة لبذرة
    `PersonalExpense.CATEGORY_CHOICES` كي تُقرأ البيانات السابقة بلا ترحيل.
    """
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_expense_categories')
    key = models.CharField(max_length=20)
    label = models.CharField(max_length=60)
    position = models.IntegerField(default=0)

    class Meta:
        db_table = 'hr_personal_expense_categories'
        ordering = ['position', 'id']
        unique_together = [['user', 'key']]

    def __str__(self):
        return self.label

    @classmethod
    def ensure_defaults(cls, user):
        """يزرع الفئات الافتراضية لمستخدم لم يخصّص كتالوجه بعد (مرة واحدة)."""
        if not cls.objects.filter(user=user).exists():
            cls.objects.bulk_create([
                cls(user=user, key=key, label=label, position=index)
                for index, (key, label) in enumerate(PersonalExpense.CATEGORY_CHOICES)
            ])
        return cls.objects.filter(user=user)

    @classmethod
    def label_map(cls, user_id):
        """مفتاح ← اسم معروض؛ الافتراضيات أساساً وكتالوج المستخدم فوقها."""
        labels = dict(PersonalExpense.CATEGORY_CHOICES)
        labels.update(dict(cls.objects.filter(user_id=user_id).values_list('key', 'label')))
        return labels

    @classmethod
    def next_key(cls, user):
        """مفتاح جديد قصير (cN) لا يصطدم بمفاتيح المستخدم ولا بالافتراضيات."""
        taken = set(dict(PersonalExpense.CATEGORY_CHOICES))
        taken.update(cls.objects.filter(user=user).values_list('key', flat=True))
        index = len(taken) + 1
        while f'c{index}' in taken:
            index += 1
        return f'c{index}'

class Employee(models.Model):
    """موظف على كشف الرواتب — وله حسابه الخاص تحت بند «رواتب مستحقة» في الشجرة.

    نوعان لا ثالث لهما (نموذج Odoo نفسه، مبسّطاً لحجم الشركة):

    - **دائم (`monthly`)**: أجرٌ شهري ثابت. لا تُسجَّل له ساعات — يُسجَّل ما
      يُخصم منه: غيابات وتأخيرات (`AttendanceAdjustment`). معدّل اليوم
      والدقيقة يُشتقّان من الراتب وأيام/ساعات الدوام المتفق عليها.
    - **جزئي (`hourly`)**: أجرٌ بالساعة متفقٌ عليه (`hourly_rate`). استحقاقه
      كلّه مشتقّ من ساعاته اليومية المسجّلة (`WorkLog`) — لا خصم غياب لمن
      لا يُدفع له إلا عن ساعة عمل فعلية.

    `account` هو حساب الموظف في شجرة الحسابات (ابن «2112 رواتب مستحقة
    للموظفين») — يُنشأ تلقائياً عند إنشاء الموظف، فرصيده الدائن هو ما له عندنا.
    """
    PAY_MONTHLY = 'monthly'
    PAY_HOURLY = 'hourly'
    PAY_TYPE_CHOICES = [
        (PAY_MONTHLY, 'دائم — راتب شهري'),
        (PAY_HOURLY, 'جزئي — أجر بالساعة'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='employees')
    code = models.CharField(max_length=20, blank=True, default='')
    name = models.CharField(max_length=150)
    pay_type = models.CharField(max_length=10, choices=PAY_TYPE_CHOICES, default=PAY_MONTHLY)

    monthly_salary = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    hourly_rate = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    # أساس اشتقاق معدّل اليوم/الدقيقة للموظف الدائم — متفقٌ عليه لا مفروض.
    standard_hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('8'))
    working_days_per_month = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('26'))

    job_title = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=40, blank=True, default='')
    national_id = models.CharField(max_length=40, blank=True, default='')
    hire_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT, null=True, blank=True,
        related_name='payroll_employees',
        help_text='حساب الموظف في الشجرة تحت «رواتب مستحقة للموظفين»',
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_employees',
        help_text='ربط اختياري بمستخدم النظام — لا يلزم لكل موظف',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_employees'
        ordering = ['name']
        unique_together = [['tenant', 'code']]
        indexes = [
            models.Index(fields=['tenant', 'is_active'], name='hremp_tenant_active'),
        ]

    def __str__(self):
        return self.name

    @property
    def daily_rate(self) -> Decimal:
        """أجر اليوم للموظف الدائم — أساس خصم الغياب."""
        days = self.working_days_per_month or Decimal('0')
        if self.pay_type != self.PAY_MONTHLY or days <= 0:
            return Decimal('0')
        return (self.monthly_salary or Decimal('0')) / days

    @property
    def minute_rate(self) -> Decimal:
        """أجر الدقيقة للموظف الدائم — أساس خصم التأخير."""
        hours = self.standard_hours_per_day or Decimal('0')
        if hours <= 0:
            return Decimal('0')
        return self.daily_rate / (hours * Decimal('60'))


class WorkLog(models.Model):
    """ساعات عمل يوم واحد — سجلّ الموظف الجزئي الذي يُبنى عليه استحقاقه.

    صفٌّ واحد لكل (موظف، يوم): الإدخال المكرّر لنفس اليوم تصحيحٌ لا إضافة،
    وإلا ضوعفت الساعات بصمت وضوعف معها الراتب.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='work_logs')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='work_logs')
    date = models.DateField()
    hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    notes = models.CharField(max_length=200, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_work_logs'
        ordering = ['-date', '-id']
        unique_together = [['employee', 'date']]
        indexes = [
            models.Index(fields=['tenant', 'employee', '-date'], name='hrwl_tenant_emp_date'),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.date} {self.hours}h"


class AttendanceAdjustment(models.Model):
    """غياب أو تأخير للموظف الدائم — ما يُخصم من راتبه الثابت.

    `is_deductible=False` تُسجّل الواقعة بلا خصم (إجازة مأذونة، تأخير معذور):
    السجل الإداري مطلوبٌ حتى حين لا يترتّب عليه مال.
    """
    KIND_ABSENCE = 'absence'
    KIND_LATE = 'late'
    KIND_CHOICES = [
        (KIND_ABSENCE, 'غياب'),
        (KIND_LATE, 'تأخير'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='attendance_adjustments')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_adjustments')
    date = models.DateField()
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_ABSENCE)
    days = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1'),
                               help_text='أيام الغياب (0.5 = نصف يوم) — للنوع «غياب»')
    minutes = models.IntegerField(default=0, help_text='دقائق التأخير — للنوع «تأخير»')
    is_deductible = models.BooleanField(default=True)
    notes = models.CharField(max_length=200, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_attendance_adjustments'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['tenant', 'employee', '-date'], name='hraa_tenant_emp_date'),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.date} {self.kind}"


class Payslip(models.Model):
    """كشف راتب لفترة — المستند الذي يدخل الدفاتر.

    كل المبالغ **لقطة** (snapshot) وقت الاحتساب: تعديل راتب الموظف لاحقاً لا
    يعيد كتابة تاريخه، والقيد المرحّل يبقى مطابقاً لكشفه.

    القيد عند الاعتماد سطران لا أكثر:
        من ح/ 5201 الرواتب والأجور        (صافي الاستحقاق)
        إلى ح/ حساب الموظف (2112…)        (صافي الاستحقاق)

    قرار مقصود: الخصومات كلّها تُخفّض المصروف بدل فتح التزامات وسيطة — لا
    استقطاعات ضريبية/تأمينية في هذا النطاق. إضافتها لاحقاً سطر في القيد لا
    إعادة تصميم.
    """
    STATUS_DRAFT = 'draft'
    STATUS_POSTED = 'posted'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'مسودة'),
        (STATUS_POSTED, 'مرحّل'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payslips')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='payslips')
    period_start = models.DateField()
    period_end = models.DateField()

    # لقطات وقت الاحتساب
    pay_type = models.CharField(max_length=10, choices=Employee.PAY_TYPE_CHOICES, default=Employee.PAY_MONTHLY)
    rate = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                               help_text='الراتب الشهري أو أجر الساعة وقت الاحتساب')
    worked_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    absence_days = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    late_minutes = models.IntegerField(default=0)

    gross = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    absence_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True, default='')
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='posted_payslips')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_payslips'
        ordering = ['-period_start', '-id']
        unique_together = [['employee', 'period_start', 'period_end']]
        indexes = [
            models.Index(fields=['tenant', '-period_start'], name='hrps_tenant_period'),
            models.Index(fields=['tenant', 'status'], name='hrps_tenant_status'),
        ]

    def __str__(self):
        return f"كشف {self.employee_id} {self.period_start}"


class PayrollPayment(models.Model):
    """صرف راتب — يُفرغ ذمة الموظف من الصندوق/البنك.

        من ح/ حساب الموظف (2112…)
        إلى ح/ الصندوق أو البنك

    يُرحَّل فور الحفظ كسندَي القبض والصرف (لا مسودّة نقدية تُنسى)، ويُلغى
    ترحيله بحذفه.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='payroll_payments')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='payroll_payments')
    payslip = models.ForeignKey(Payslip, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='payments')
    date = models.DateField()
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    cash_account = models.ForeignKey(
        'accounting.Account', on_delete=models.PROTECT, null=True, blank=True,
        related_name='payroll_payments',
        help_text='مصدر الدفع — صندوق أو بنك؛ الصندوق الافتراضي إن تُرك فارغاً',
    )
    notes = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='payroll_payments')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_payroll_payments'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['tenant', '-date'], name='hrpp_tenant_date'),
        ]

    def __str__(self):
        return f"صرف {self.employee_id} {self.amount}"


class PointsHistory(models.Model):
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='points')
    date = models.DateField()
    
    task_points = models.IntegerField(default=0)
    attendance_points = models.IntegerField(default=0)
    activity_points = models.IntegerField(default=0)
    total_points = models.IntegerField(default=0)
    
    completed_tasks = models.IntegerField(default=0)
    work_minutes = models.IntegerField(default=0)
    attended = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['user', 'date']]
