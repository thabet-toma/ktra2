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
