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
    date = models.DateField()
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
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
        ]

    def __str__(self):
        return f"{self.title} - {self.amount}"

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
