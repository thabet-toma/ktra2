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
    # الهيكل التنظيمي (`hr_suite`) — كلها اختيارية: الموظف يبقى صالحاً للرواتب
    # بلا قسمٍ ولا فرعٍ ولا مسمّى معرَّف، تماماً كما كان قبل الوحدة.
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_employees')
    department = models.ForeignKey(
        'hr.Department', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees')
    job_title_ref = models.ForeignKey(
        'hr.JobTitle', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees',
        help_text='مسمّى وظيفي معرَّف — يتقدّم على الحقل النصّي حين يُختار')
    work_location = models.ForeignKey(
        'hr.WorkLocation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employees',
        help_text='موقع بصمته — فارغاً تُقبل بصمته عند أي موقع نشط')
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

    # T-HR: الساعات الإضافية — دقائقها لقطةٌ وأجرها لقطةٌ ثانية. لم يكن للأجر
    # الإضافي وجودٌ في المحرّك قبل وحدة الحضور: كان يُستدلّ عليه في التقرير
    # ولا يُسعَّر.
    overtime_minutes = models.IntegerField(default=0)
    overtime_pay = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    gross = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    absence_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    late_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    # T-HR: قسط السلفة و«صافي المدفوع».
    #
    # **`net` هو ما يدخل الدفاتر، و`net_payable` هو ما يقبضه الموظف.** القسط
    # لا يُخفّض القيد: مصروف الرواتب هو ما استُحقّ كاملاً (مدين 5201 / دائن
    # حساب الموظف بـ`net`)، والقسط يتصافى **داخل حساب الموظف نفسه** مقابل
    # مدينيّة صرف السلفة. أي «قيد سداد» إضافي هنا عدٌّ مزدوج.
    advance_deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_payable = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    # T-HR: وعاء المسير — فارغٌ للقسيمة المُنشأة مفردةً كما كان دائماً.
    # `SET_NULL`: القسيمة مستندٌ قائمٌ بذاته دخل الدفاتر، وحذفُ الوعاء لا يمسّه.
    run = models.ForeignKey(
        'hr.PayrollRun', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payslips')
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
    # T-HR: صرفُ سلفةٍ سندُ صرفٍ عاديّ يحمل مرجعها — لا مسار مالٍ ثانٍ للسلف.
    # فارغاً في سند الراتب المعتاد.
    advance = models.ForeignKey(
        'hr.Advance', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments',
        help_text='السلفة التي يصرفها هذا السند — فارغ في صرف الراتب المعتاد')
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


# ──────────────────────────────────────────────────────────────────────────
# وحدة الموارد البشرية الموسّعة (`hr_suite`) — الهيكل التنظيمي
#
# الفرع موجود سلفاً في `tenants.Branch` ولا يُكرَّر هنا. الجديد قسمٌ داخل
# الشركة (بشجرةٍ من أب وأبناء) ومسمّى وظيفي — وكلاهما يخدم أمرين لا ثالث لهما:
# توجيه الموافقات على الطلبات، وتصفية مسير الرواتب والتقارير.
# ──────────────────────────────────────────────────────────────────────────

class Department(models.Model):
    """قسم داخل الشركة — عقدة في شجرة الهيكل التنظيمي.

    `parent` يبني الشجرة، و`manager` موظفٌ لا مستخدم: المسؤولية التنظيمية تتبع
    الموظف حتى لو لم يكن له حساب دخول أصلاً.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_departments')
    name = models.CharField(max_length=150)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_departments')
    manager = models.ForeignKey(
        'hr.Employee', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='managed_departments')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_departments'
        ordering = ['name']
        unique_together = [['tenant', 'name']]
        indexes = [
            models.Index(fields=['tenant', 'is_active'], name='hrdept_tenant_active'),
        ]

    def __str__(self):
        return self.name


class JobTitle(models.Model):
    """مسمّى وظيفي معرَّف للشركة — بديلٌ منظَّم لحقل `Employee.job_title` النصّي.

    الحقل النصّي القديم يبقى (بياناتٌ قائمة تعتمده) ويُستعمل حين لا يُختار
    مسمّى معرَّف؛ لا هجرة هدّامة تُلقي ما كتبه الناس بأيديهم.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_job_titles')
    name = models.CharField(max_length=150)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='job_titles')
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_job_titles'
        ordering = ['name']
        unique_together = [['tenant', 'name']]

    def __str__(self):
        return self.name


# ──────────────────────────────────────────────────────────────────────────
# الحضور والانصراف — سجلٌّ خام ويومٌ مشتقّ
#
# نموذجان لا واحد، والفصل بينهما هو كل شيء:
#
# - `CheckEvent` **بصمةٌ خام لا تُعدَّل**: لحظةُ ضغطة الموظف بموقعها وصورتها،
#   ومعها **المرفوضة أيضاً** — من بصم خارج نطاق الشركة له حقٌّ في أن يُسأل عن
#   ذلك، والسجل الذي يمحو محاولاته يمحو معه الدليل.
# - `AttendanceDay` **يومٌ مشتقّ** تعيد بناءه `recompute_attendance_day` من
#   البصمات كلَّ مرة. صفٌّ واحد لكل (موظف، يوم) بقيدٍ فريد، فإعادةُ الحساب
#   تصحيحٌ لا تكديس.
#
# ولا يُحتسب راتبٌ من البصمات مباشرةً: الرواتب تقرأ اليوم المشتقّ وحده.
# ──────────────────────────────────────────────────────────────────────────

class WorkLocation(models.Model):
    """موقع عملٍ تُقبل البصمة عنده — إحداثياته ونصف قطره وسياسته.

    السياسة تسكن هنا لا في إعدادات الشركة لأن المواقع تختلف: مقرٌّ رئيسي يشدّد
    (موقع جغرافي + صورة)، ومستودعٌ على أطراف المدينة يكتفي بشبكته.

    **حدّ التخفيف مُعلَن**: إحداثيات المتصفّح ادّعاءٌ من العميل لا إثباتٌ
    مشفَّر. الصورة وقائمة الـIP تجعلان التحايل مكلفاً لا مستحيلاً، ومن أراد
    يقيناً فأمامه بصمة الإصبع على جهازٍ في المكان.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_work_locations')
    name = models.CharField(max_length=150)
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_work_locations')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radius_m = models.PositiveIntegerField(
        default=150, help_text='نصف القطر المقبول حول الموقع بالأمتار')

    require_geo = models.BooleanField(
        default=True, help_text='ارفض البصمة بلا موقع جغرافي داخل النطاق')
    require_photo = models.BooleanField(
        default=False, help_text='ألزِم بصورةٍ لحظة التسجيل')
    allow_ip_fallback = models.BooleanField(
        default=True, help_text='اقبل البصمة من عنوان IP مسموح حتى لو تعذّر الموقع')
    ip_allowlist = models.TextField(
        blank=True, default='',
        help_text='عناوين IP أو نطاقات CIDR، واحدٌ في كل سطر أو مفصولةٌ بفاصلة')

    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_work_locations'
        ordering = ['name']
        unique_together = [['tenant', 'name']]
        indexes = [
            models.Index(fields=['tenant', 'is_active'], name='hrwloc_tenant_active'),
        ]

    def __str__(self):
        return self.name

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class Shift(models.Model):
    """وردية عمل — فترةٌ أو فترتان في اليوم، بسماحها وقاعدة إضافيّها.

    **فترتان لا واحدة** لأن دوام الصباح والمساء بينهما راحةُ ظهيرة هو الشكل
    الغالب في المتاجر هنا، وتمثيلُه بورديتين منفصلتين يجعل يوماً واحداً
    يومين في كل تقرير.

    **الوردية الليلية** حين يكون وقت الانتهاء أبكر من وقت البدء: تعبر منتصف
    الليل، ويومُ الحضور يبقى **يوم بدايتها** — من دخل الساعة العاشرة مساءً
    وخرج السادسة صباحاً عمل يوماً واحداً لا يومين.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_shifts')
    name = models.CharField(max_length=150)

    start1 = models.TimeField(help_text='بداية الفترة الأولى')
    end1 = models.TimeField(help_text='نهاية الفترة الأولى')
    start2 = models.TimeField(null=True, blank=True, help_text='بداية الفترة الثانية (اختيارية)')
    end2 = models.TimeField(null=True, blank=True)

    grace_minutes = models.PositiveIntegerField(
        default=0, help_text='دقائق سماحٍ قبل احتساب التأخير')
    overtime_after_minutes = models.PositiveIntegerField(
        default=0, help_text='دقائق بعد الدوام المقرّر لا تُحتسب إضافياً')
    overtime_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal('1.25'),
        help_text='مضاعف أجر الساعة الإضافية')
    # أيام العطلة الأسبوعية بترقيم `datetime.date.weekday()`: الاثنين 0 … الأحد 6.
    # الافتراضي الجمعة (4) — والترقيم نفسه الذي يستعمله كشف الساعات القائم.
    weekly_off_days = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_shifts'
        ordering = ['name']
        unique_together = [['tenant', 'name']]

    def __str__(self):
        return self.name

    @property
    def periods(self) -> list:
        """فترات الوردية أزواجَ (بداية، نهاية) — واحدة أو اثنتان."""
        out = [(self.start1, self.end1)]
        if self.start2 is not None and self.end2 is not None:
            out.append((self.start2, self.end2))
        return out

    def is_weekly_off(self, weekday: int) -> bool:
        try:
            return int(weekday) in {int(day) for day in (self.weekly_off_days or [])}
        except (TypeError, ValueError):
            return False


class ShiftAssignment(models.Model):
    """إسناد وردية لموظف على مدى تواريخ — «جدول المناوبات».

    `end_date` فارغاً يعني إسناداً مفتوحاً. وحين تتقاطع فترتان يُغلَّب **آخر
    إسناد بدايةً**: المناوبة الجديدة تنسخ ما قبلها لا تتصارع معه.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_shift_assignments')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='shift_assignments')
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='assignments')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_shift_assignments'
        ordering = ['-start_date', '-id']
        indexes = [
            models.Index(fields=['tenant', 'employee', '-start_date'], name='hrsa_tenant_emp_start'),
        ]

    def __str__(self):
        return f"{self.employee_id} → {self.shift_id} من {self.start_date}"

    def covers(self, day) -> bool:
        if day < self.start_date:
            return False
        return self.end_date is None or day <= self.end_date


class CheckEvent(models.Model):
    """بصمة دخول أو خروج — سجلٌّ خام لا يُعدَّل ولا يُحذف.

    التصحيح **بصمةٌ ثانية** أو إبطالٌ بعَلَم `is_voided`، لا تعديلٌ فوق الأصل:
    ورقةٌ يوقّعها الموظف على ساعاته يجب أن يكون خلفها سجلٌّ يُقرأ كما وقع.

    والمرفوضة تُحفظ كذلك (`accepted=False` وسببها): محاولةُ بصمٍ خارج النطاق
    واقعةٌ إدارية، ومحوُها يمحو معه ما يُسأل عنه الموظف أو تُراجَع به السياسة.
    """
    KIND_IN = 'in'
    KIND_OUT = 'out'
    KIND_CHOICES = [(KIND_IN, 'دخول'), (KIND_OUT, 'خروج')]

    SOURCE_ESS = 'ess'
    SOURCE_MANUAL = 'manual'
    SOURCE_IMPORT = 'import'
    SOURCE_CHOICES = [
        (SOURCE_ESS, 'الخدمة الذاتية'),
        (SOURCE_MANUAL, 'إدخال يدوي'),
        (SOURCE_IMPORT, 'استيراد'),
    ]

    REJECT_OUT_OF_RANGE = 'out_of_range'
    REJECT_NO_LOCATION = 'no_location'
    REJECT_NO_GEO = 'no_geo'
    REJECT_IP_BLOCKED = 'ip_blocked'
    REJECT_PHOTO_REQUIRED = 'photo_required'
    REJECT_CHOICES = [
        (REJECT_OUT_OF_RANGE, 'خارج نطاق موقع العمل'),
        (REJECT_NO_LOCATION, 'لا يوجد موقع عمل مُعرَّف'),
        (REJECT_NO_GEO, 'لم يصل الموقع الجغرافي'),
        (REJECT_IP_BLOCKED, 'الشبكة غير مسموحة'),
        (REJECT_PHOTO_REQUIRED, 'الصورة مطلوبة'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_check_events')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='check_events')
    kind = models.CharField(max_length=4, choices=KIND_CHOICES)
    ts = models.DateTimeField(help_text='لحظة البصمة — واعيةٌ بالمنطقة الزمنية')
    attendance_date = models.DateField(
        help_text='اليوم الذي تُنسب إليه — يوم بداية الوردية لا يوم الساعة')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=SOURCE_ESS)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    distance_m = models.PositiveIntegerField(
        null=True, blank=True, help_text='المسافة المحسوبة إلى موقع العمل وقت البصمة')
    ip = models.CharField(max_length=45, blank=True, default='')
    photo_url = models.URLField(blank=True, default='', max_length=500)
    work_location = models.ForeignKey(
        WorkLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='check_events')

    accepted = models.BooleanField(default=True)
    reject_reason = models.CharField(max_length=20, blank=True, default='', choices=REJECT_CHOICES)
    is_voided = models.BooleanField(
        default=False, help_text='أُبطلت إدارياً — تبقى في السجل ولا تدخل الحساب')
    voided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hr_voided_checks')
    voided_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True, default='')

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hr_check_events')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_check_events'
        ordering = ['-ts', '-id']
        indexes = [
            models.Index(fields=['tenant', 'employee', '-ts'], name='hrce_tenant_emp_ts'),
            models.Index(fields=['tenant', 'attendance_date'], name='hrce_tenant_date'),
            models.Index(fields=['employee', 'attendance_date', 'accepted'], name='hrce_emp_date_ok'),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.kind} {self.ts:%Y-%m-%d %H:%M}"


class AttendanceDay(models.Model):
    """يوم حضور مشتقّ — ما تقرأه التقارير والرواتب.

    لا يُكتب بيدٍ إلا عبر `is_manual_override`: بلا هذا العَلَم تكتسحه أول
    إعادة حساب، فالتصحيح اليدوي الذي لا يُعلن نفسه يضيع بصمت.
    """
    STATUS_PRESENT = 'present'
    STATUS_LATE = 'late'
    STATUS_ABSENT = 'absent'
    STATUS_LEAVE = 'leave'
    STATUS_HOLIDAY = 'holiday'
    STATUS_OFF = 'off'
    STATUS_UNSCHEDULED = 'unscheduled'
    STATUS_CHOICES = [
        (STATUS_PRESENT, 'حاضر'),
        (STATUS_LATE, 'متأخّر'),
        (STATUS_ABSENT, 'غائب'),
        (STATUS_LEAVE, 'إجازة'),
        (STATUS_HOLIDAY, 'عطلة رسمية'),
        (STATUS_OFF, 'عطلة أسبوعية'),
        (STATUS_UNSCHEDULED, 'بلا وردية'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_attendance_days')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_days')
    date = models.DateField()
    shift = models.ForeignKey(
        Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_days',
        help_text='لقطة الوردية المُسنَدة يوم الحساب')

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_ABSENT)
    worked_minutes = models.PositiveIntegerField(default=0)
    late_minutes = models.PositiveIntegerField(default=0)
    early_leave_minutes = models.PositiveIntegerField(default=0)
    overtime_minutes = models.PositiveIntegerField(default=0)
    scheduled_minutes = models.PositiveIntegerField(default=0)
    absence_days = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))

    first_in = models.DateTimeField(null=True, blank=True)
    last_out = models.DateTimeField(null=True, blank=True)

    is_manual_override = models.BooleanField(
        default=False, help_text='صُحّح بيد مشرف — إعادة الحساب لا تكتسحه')
    notes = models.CharField(max_length=200, blank=True, default='')

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_attendance_days'
        ordering = ['-date', 'employee_id']
        unique_together = [['employee', 'date']]
        indexes = [
            models.Index(fields=['tenant', 'date'], name='hrad_tenant_date'),
            models.Index(fields=['tenant', 'employee', '-date'], name='hrad_tenant_emp_date'),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.date} {self.status}"


# ──────────────────────────────────────────────────────────────────────────
# الإجازات والعطلات — ما يمنع الغياب من أن يُحتسب غياباً
# ──────────────────────────────────────────────────────────────────────────

class LeaveType(models.Model):
    """نوع إجازة — مدفوعةً أو غير مدفوعة، وباستحقاقها إن كان لها استحقاق.

    الاستحقاق **يُحسب ولا يُخزَّن**: رصيدٌ محفوظ في عمود يفترق عن دفتره عند
    أول تعديلٍ رجعيّ، ولا يُكتشف فرقُه إلا حين يشتكي صاحبه.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_leave_types')
    name = models.CharField(max_length=100)
    is_paid = models.BooleanField(
        default=True, help_text='غير المدفوعة تُسجَّل إجازةً في السجل ويوماً مخصوماً في المال')
    annual_grant = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'),
        help_text='أيام تُمنح دفعةً واحدة مع بداية كل سنة')
    monthly_accrual = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0'),
        help_text='أيام تُستحقّ عن كل شهر خدمة')
    max_days_per_request = models.PositiveIntegerField(
        default=0, help_text='صفر = بلا حدّ')
    requires_balance = models.BooleanField(
        default=True, help_text='امنع الطلب حين لا يكفي الرصيد')
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_leave_types'
        ordering = ['name']
        unique_together = [['tenant', 'name']]

    def __str__(self):
        return self.name


class Holiday(models.Model):
    """عطلة رسمية — يومٌ لا يُسأل فيه أحدٌ عن بصمة."""
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_holidays')
    date = models.DateField()
    name = models.CharField(max_length=150)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_holidays'
        ordering = ['-date']
        unique_together = [['tenant', 'date']]
        indexes = [
            models.Index(fields=['tenant', 'date'], name='hrhol_tenant_date'),
        ]

    def __str__(self):
        return f"{self.date} {self.name}"


class LeaveBalanceAdjustment(models.Model):
    """تسويةُ رصيد إجازة — رصيدٌ افتتاحي أو منحةٌ يدوية أو خصمٌ إداري.

    هي السطر الوحيد الذي يُكتب بيدٍ في دفتر الأرصدة؛ وما عداه مشتقٌّ:
    الاستحقاق من قواعد النوع، والمسحوب من الطلبات المعتمدة.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='hr_leave_adjustments')
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='leave_adjustments')
    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.PROTECT, related_name='adjustments')
    date = models.DateField()
    days = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text='موجبٌ يمنح وسالبٌ يخصم')
    notes = models.CharField(max_length=200, blank=True, default='')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_leave_adjustments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_leave_balance_adjustments'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['tenant', 'employee'], name='hrlba_tenant_emp'),
        ]

    def __str__(self):
        return f"{self.employee_id} {self.leave_type_id} {self.days}"


# ──────────────────────────────────────────────────────────────────────────
# الطلبات والموافقات والسلف
# ──────────────────────────────────────────────────────────────────────────

class ApprovalRule(models.Model):
    """قاعدة توجيه اعتماد — من يوافق، وعلى أي نوع، ولأي قسم أو فرع.

    القاعدة الأخصّ تغلب: قاعدةٌ لقسمٍ بعينه تسبق قاعدةً عامّة، وإلا احتاج كل
    قسمٍ إلى نسخةٍ من كل قاعدة عامّة.

    `approver_user` فارغاً يعني «أيّ حاملٍ لصلاحية الاعتماد» — وهو الشائع في
    الشركات الصغيرة حيث المدير واحدٌ ولا معنى لتسميته في كل قاعدة.
    """
    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='hr_approval_rules')
    #: فارغاً = كل الأنواع. القيم من `EmployeeRequest.KIND_CHOICES`.
    kind = models.CharField(max_length=10, blank=True, default='')
    department = models.ForeignKey(
        'hr.Department', on_delete=models.CASCADE, null=True, blank=True,
        related_name='approval_rules')
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.CASCADE, null=True, blank=True,
        related_name='hr_approval_rules')
    level = models.PositiveSmallIntegerField(
        default=1, help_text='ترتيب المستوى — 1 أولاً ثم 2 وهكذا')
    approver_user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='hr_approval_rules',
        help_text='فارغاً = أي مستخدم يملك صلاحية اعتماد الطلبات')
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_approval_rules'
        ordering = ['level', 'id']
        indexes = [
            models.Index(fields=['tenant', 'is_active'], name='hrar_tenant_active'),
        ]

    def __str__(self):
        return f"{self.kind or 'الكل'} مستوى {self.level}"

    @property
    def specificity(self) -> int:
        """كم قيداً تحمله القاعدة — الأعلى يغلب عند التساوي في المستوى."""
        return sum(1 for v in (self.kind, self.department_id, self.branch_id) if v)


class EmployeeRequest(models.Model):
    """طلب موظف — إجازة أو سلفة أو تسوية مصروف.

    نموذجٌ واحد لأنواعٍ أربعة لأن **دورة الاعتماد واحدة**: تقديمٌ ثم مستويات
    ثم قرار. فصلُها نماذجَ كان يعني نسخ آلة الحالات وقواعد التوجيه أربع مرّات،
    وأربع نسخٍ من قاعدةٍ تعني أربع فرصٍ لانزياحها.
    """
    KIND_LEAVE = 'leave'
    KIND_ADVANCE = 'advance'
    KIND_EXPENSE = 'expense'
    KIND_OTHER = 'other'
    KIND_CHOICES = [
        (KIND_LEAVE, 'إجازة'),
        (KIND_ADVANCE, 'سلفة'),
        (KIND_EXPENSE, 'تسوية مصروف'),
        (KIND_OTHER, 'طلب آخر'),
    ]

    STATUS_DRAFT = 'draft'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'مسودّة'),
        (STATUS_PENDING, 'قيد المراجعة'),
        (STATUS_APPROVED, 'موافق'),
        (STATUS_REJECTED, 'مرفوض'),
        (STATUS_CANCELLED, 'ملغى'),
    ]

    #: الحالات التي لا يُغيَّر فيها الطلب بعدُ.
    OPEN_STATUSES = (STATUS_DRAFT, STATUS_PENDING)

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name='hr_employee_requests')
    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name='requests')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    # الإجازة
    leave_type = models.ForeignKey(
        LeaveType, on_delete=models.PROTECT, null=True, blank=True, related_name='requests')
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)

    # السلفة وتسوية المصروف
    amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    installments = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='عدد أقساط سداد السلفة')

    description = models.TextField(blank=True, default='')
    attachment_url = models.URLField(blank=True, default='', max_length=500)
    execution_date = models.DateField(
        null=True, blank=True, help_text='تاريخ تنفيذ الطلب بعد اعتماده')
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True, default='')

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_requests_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_employee_requests'
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['tenant', 'status'], name='hrer_tenant_status'),
            models.Index(fields=['tenant', 'employee', '-id'], name='hrer_tenant_emp'),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.employee_id} ({self.status})"

    @property
    def leave_days(self) -> Decimal:
        """أيام الإجازة شاملةً الطرفين — يومٌ واحد إن تطابق التاريخان."""
        if not self.date_from or not self.date_to:
            return Decimal('0')
        return Decimal((self.date_to - self.date_from).days + 1)


class ApprovalStep(models.Model):
    """مستوى اعتماد واحد على طلب — تُبنى المستويات كلّها لحظة التقديم.

    بناؤها مقدَّماً لا عند كل قرار: الطلب يُظهر لصاحبه **أين وصل ومن بقي**،
    وسلسلةٌ تُبنى خطوةً بخطوة لا تستطيع أن تقول ذلك.
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'بانتظار'),
        (STATUS_APPROVED, 'موافق'),
        (STATUS_REJECTED, 'مرفوض'),
    ]

    id = models.AutoField(primary_key=True)
    request = models.ForeignKey(
        EmployeeRequest, on_delete=models.CASCADE, related_name='steps')
    level = models.PositiveSmallIntegerField()
    approver_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_approval_steps',
        help_text='فارغاً = أي حاملٍ لصلاحية الاعتماد')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    acted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_approval_actions')
    acted_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        db_table = 'hr_approval_steps'
        ordering = ['level', 'id']
        unique_together = [['request', 'level']]

    def __str__(self):
        return f"{self.request_id} مستوى {self.level} — {self.status}"


class Advance(models.Model):
    """سلفة موظف — مبلغٌ صُرف مقدّماً ويُستردّ أقساطاً من الراتب.

    **ولا مسار مالٍ جديد لها**: الصرف سندُ `PayrollPayment` القائم (بمرجعٍ
    إليها)، فيمرّ بـ`post_payroll_payment` ويُنتج القيد المعتاد
    (مدين حساب الموظف / دائن الصندوق).

    والقسط عند الراتب **لا يُنتج قيداً ثانياً**: يُخفّض ما يُدفع نقداً للموظف
    ويترك دائنية القسيمة كاملةً في حسابه، فيتصافى الدَّينُ داخل الحساب نفسه.
    أي «قيد سداد» إضافي هنا عدٌّ مزدوج (انظر `hr/payroll.py`).
    """
    STATUS_OPEN = 'open'
    STATUS_SETTLED = 'settled'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'قائمة'),
        (STATUS_SETTLED, 'مسدَّدة'),
        (STATUS_CANCELLED, 'ملغاة'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_advances')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='advances')
    request = models.OneToOneField(
        EmployeeRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='advance')
    date = models.DateField()
    total = models.DecimalField(max_digits=15, decimal_places=2)
    monthly_installment = models.DecimalField(max_digits=15, decimal_places=2)
    remaining = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    notes = models.CharField(max_length=200, blank=True, default='')

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hr_advances')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_advances'
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['tenant', 'status'], name='hradv_tenant_status'),
            models.Index(fields=['tenant', 'employee'], name='hradv_tenant_emp'),
        ]

    def __str__(self):
        return f"سلفة {self.employee_id} — {self.total}"

    @property
    def is_disbursed(self) -> bool:
        """أصُرفت فعلاً؟ سلفةٌ لم تُصرَف لا يُخصم قسطها من راتب أحد."""
        return self.payments.exists()


# ──────────────────────────────────────────────────────────────────────────
# العقود — مصدر أرقام الراتب حين توجد
#
# العقد **يتقدّم** على حقول `Employee` حين يكون نشطاً، وهي تبقى fallback:
# لا هجرة هدّامة تُفرغ رواتب الشركات القائمة، ومن لم يبنِ عقوده بعد يبقى
# راتبه يُحسب كما كان بالضبط.
#
# ولا لغةَ صيغٍ هنا: بنودُ العقد **مبالغُ ثابتة** (استحقاق أو خصم). دفترة
# تُتيح صيغاً (‏«{إيرادات المبيعات} × 0.05»)، وهو ما نؤجّله عمداً — محرّكُ
# صيغٍ نصفُ مبنيّ في مسار المال أخطرُ من غيابه، والعمولة اليوم تُدخَل بنداً
# بمبلغها المحسوب.
# ──────────────────────────────────────────────────────────────────────────

class Contract(models.Model):
    """عقد عمل — شروط الأجر المتفق عليها ومدّتها.

    عقدٌ نشطٌ واحد لكل موظف (حارسُه في المُسلسِل لا في قاعدة البيانات، كي
    تبقى العقود المنتهية والملغاة صفوفاً تاريخية تُقرأ).
    """
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_EXPIRED = 'expired'
    STATUS_TERMINATED = 'terminated'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'مسودّة'),
        (STATUS_ACTIVE, 'نشط'),
        (STATUS_EXPIRED, 'منتهٍ'),
        (STATUS_TERMINATED, 'مُنهىً'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_contracts')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='contracts')
    start_date = models.DateField()
    end_date = models.DateField(
        null=True, blank=True, help_text='فارغ = عقد غير محدّد المدة')

    pay_type = models.CharField(
        max_length=10, choices=Employee.PAY_TYPE_CHOICES, default=Employee.PAY_MONTHLY)
    monthly_salary = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    hourly_rate = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    overtime_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text='يتقدّم على مضاعف الوردية — فارغاً تسري قاعدة الوردية')

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    job_title = models.CharField(max_length=150, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    document_url = models.URLField(blank=True, default='', max_length=500)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hr_contracts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_contracts'
        ordering = ['-start_date', '-id']
        indexes = [
            models.Index(fields=['tenant', 'status'], name='hrct_tenant_status'),
            models.Index(fields=['employee', '-start_date'], name='hrct_emp_start'),
        ]

    def __str__(self):
        return f"عقد {self.employee_id} من {self.start_date}"

    def covers(self, day) -> bool:
        """أيغطّي العقد هذا اليوم؟ — نشطاً وضمن مدّته."""
        if self.status != self.STATUS_ACTIVE or day < self.start_date:
            return False
        return self.end_date is None or day <= self.end_date

    @property
    def days_to_expiry(self):
        """أيامٌ حتى انتهائه — `None` للعقد غير محدّد المدة أو غير النشط."""
        if self.end_date is None or self.status != self.STATUS_ACTIVE:
            return None
        from django.utils import timezone as _tz

        return (self.end_date - _tz.localdate()).days


class PayrollRun(models.Model):
    """مسير رواتب — احتساب قسائم فترةٍ لمجموعةٍ من الموظفين دفعةً واحدة.

    وجودُه لا يغيّر شيئاً في **كيف** تُحسب القسيمة أو تُرحَّل: كلٌّ منها تمرّ
    بـ`compute_payslip` و`post_payslip` نفسيهما. ما يضيفه المسير هو الوعاء —
    فترةٌ واحدة، ونطاقٌ (فرع/قسم)، وزرٌّ يرحّل ما اكتمل.

    وحذفُ المسير لا يحذف قسائمه (`SET_NULL` على `Payslip.run`): القسيمة مستندٌ
    قائمٌ بذاته ودخل الدفاتر، والوعاءُ تنظيمٌ فوقها.
    """
    STATUS_DRAFT = 'draft'
    STATUS_COMPUTED = 'computed'
    STATUS_POSTED = 'posted'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'مسودّة'),
        (STATUS_COMPUTED, 'محتسَب'),
        (STATUS_POSTED, 'مرحَّل'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hr_payroll_runs')
    name = models.CharField(max_length=150, blank=True, default='')
    period_start = models.DateField()
    period_end = models.DateField()
    branch = models.ForeignKey(
        'tenants.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hr_payroll_runs')
    department = models.ForeignKey(
        'hr.Department', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payroll_runs')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True, default='')

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hr_payroll_runs')
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hr_payroll_runs'
        ordering = ['-period_start', '-id']
        indexes = [
            models.Index(fields=['tenant', '-period_start'], name='hrrun_tenant_period'),
        ]

    def __str__(self):
        return self.name or f"مسير {self.period_start} — {self.period_end}"


class PayslipAdvance(models.Model):
    """كم خُصم من أيّ سلفة في أيّ كشف — سطرُ الربط الذي يجعل الإلغاء تامّاً.

    بلا هذا الجدول كان إلغاء الترحيل يُعيد الحساب ليعرف كم يردّ، وقواعدُ
    الأقساط قد تكون تغيّرت بينهما فيعود رقمٌ آخر ويبقى الفرق دَيناً وهمياً.
    """
    id = models.AutoField(primary_key=True)
    payslip = models.ForeignKey(
        'hr.Payslip', on_delete=models.CASCADE, related_name='advance_links')
    advance = models.ForeignKey(
        'hr.Advance', on_delete=models.CASCADE, related_name='payslip_links')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hr_payslip_advances'
        ordering = ['id']
        unique_together = [['payslip', 'advance']]

    def __str__(self):
        return f"كشف {self.payslip_id} ← سلفة {self.advance_id} = {self.amount}"


class ContractComponent(models.Model):
    """بند تعويض في العقد — بدلٌ ثابت أو خصمٌ ثابت.

    يصبّ في `allowances` أو `other_deductions` في القسيمة، ويُلتقط **لقطةً**
    وقت الاحتساب كسائر أرقامها: تعديل بندٍ لاحقاً لا يُعيد كتابة قسيمةٍ
    مرحّلة.
    """
    KIND_EARNING = 'earning'
    KIND_DEDUCTION = 'deduction'
    KIND_CHOICES = [
        (KIND_EARNING, 'استحقاق'),
        (KIND_DEDUCTION, 'خصم'),
    ]

    id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(
        Contract, on_delete=models.CASCADE, related_name='components')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_EARNING)
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0'))
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'hr_contract_components'
        ordering = ['position', 'id']

    def __str__(self):
        return f"{self.name} {self.amount}"
