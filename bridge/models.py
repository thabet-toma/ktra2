from django.db import models


class FirestoreMirrorDoc(models.Model):
    """Stores JSON documents keyed by Firestore-style paths (e.g. deals/uuid, users/1).

    tenant: business-data docs are scoped per company. NULL is allowed only for
    global collections (users/tasks/attendance/...) — see views.GLOBAL_COLLECTIONS.
    """

    path = models.CharField(max_length=255, unique=True, db_index=True)
    data = models.JSONField(default=dict)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE,
        null=True, blank=True, db_index=True, related_name='mirror_docs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.path
