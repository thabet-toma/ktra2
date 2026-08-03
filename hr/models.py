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
