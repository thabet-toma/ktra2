from django.db import models


class FirestoreMirrorDoc(models.Model):
    """Stores JSON documents keyed by Firestore-style paths (e.g. deals/uuid, users/1)."""

    path = models.CharField(max_length=255, unique=True, db_index=True)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.path
