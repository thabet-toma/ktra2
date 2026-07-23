from django.db import models
from tenants.models import Tenant

class SystemAttachment(models.Model):
    id = models.AutoField(primary_key=True, db_column='AttachmentID')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    related_table = models.CharField(max_length=50, db_column='RelatedTable')
    related_id = models.IntegerField(db_column='RelatedID')
    file_type = models.CharField(max_length=50, db_column='FileType', null=True, blank=True)
    file_path = models.CharField(max_length=500, db_column='FilePath')
    uploaded_at = models.DateTimeField(auto_now_add=True, db_column='UploadedAt')

    class Meta:
        db_table = 'system_attachments'
        managed = False


class ActivityLog(models.Model):
    """سجل نشاط موحّد عبر الموقع: مَن فعل ماذا على أي مستند + أحداث الجلسة.

    طبقة Shared/Core واحدة تُغذّي: سجل نشاط كل مستند (فاتورة/صفقة) + الصفحة العامة
    للمدير. أحداث «العرض/الفتح» تُعلَّم is_view=True لتُستبعد من الجدول العام وتبقى
    ظاهرة في تفصيل المستخدم. تُكتب عبر core.activity.log_activity فقط (غير حاظرة).
    """

    ACTIONS = [
        ('create', 'إنشاء'),
        ('update', 'تعديل'),
        ('delete', 'حذف'),
        ('post', 'ترحيل'),
        ('unpost', 'إلغاء ترحيل'),
        ('duplicate', 'نسخ'),
        ('payment', 'دفعة'),
        ('view', 'عرض'),
        ('login', 'تسجيل دخول'),
        ('logout', 'تسجيل خروج'),
    ]

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_column='TenantID')
    user = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True, db_column='UserID')
    action = models.CharField(max_length=20, choices=ACTIONS)
    # يفصل أحداث العرض عن التعديلات — الجدول العام يفلتر is_view=False.
    is_view = models.BooleanField(default=False, db_index=True)
    entity_type = models.CharField(max_length=40)
    entity_id = models.IntegerField(null=True, blank=True)
    entity_label = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=64, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'activity_logs'
        managed = True
        indexes = [
            models.Index(fields=['tenant', '-timestamp'], name='act_tenant_ts_idx'),
            models.Index(fields=['tenant', 'user', '-timestamp'], name='act_tenant_user_ts_idx'),
            models.Index(fields=['tenant', 'entity_type', 'entity_id'], name='act_tenant_entity_idx'),
        ]

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id} by {self.user_id}"


class ActivityLogPartner(models.Model):
    """يربط حدث النشاط الواحد بكل الجهات المتأثرة دون نسخ الحدث."""

    id = models.AutoField(primary_key=True)
    activity = models.ForeignKey(
        ActivityLog, on_delete=models.CASCADE, related_name="partner_links",
        db_column="ActivityLogID",
    )
    partner = models.ForeignKey(
        "partners.Partner", on_delete=models.CASCADE, related_name="activity_links",
        db_column="PartnerID",
    )

    class Meta:
        db_table = "activity_log_partners"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "partner"], name="uniq_activity_log_partner",
            ),
        ]
