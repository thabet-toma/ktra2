from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from core.tenant_utils import get_tenant


class TenantQuerySetMixin:
    """Scopes get_queryset() to the current request's tenant.

    Returns queryset.none() when no tenant is resolvable so that data never
    leaks across companies.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_tenant(self.request)
        if tenant:
            return qs.filter(tenant=tenant)
        return qs.none()


class TenantCreateMixin:
    """Injects the current request's tenant into perform_create().

    Raises a 400 ValidationError instead of silently falling back to
    tenant_id=1, so a missing tenant configuration fails loudly.
    """

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"tenant": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)


class BaseTenantViewSet(TenantQuerySetMixin, TenantCreateMixin, viewsets.ModelViewSet):
    """Convenience base combining tenant-scoped queryset and create."""


class DocumentAttachmentsMixin:
    """مرفقات مستندٍ (صورة أو PDF) في `SystemAttachment` — `attachments/` و`attachments/<id>/`.

    مرآة نقاط فاتورة الشراء والبيع (`logistics/views/invoices.py` — `attachments`):
    الرفع نفسه عبر `core/media_views.py` وهذه تربط الرابط بالمستند، وتُحفظ فوراً
    ولو كان المستند مرحّلاً — المطالبة تصل غالباً بعد الترحيل. كل استعلامٍ مُنطاقٌ
    بشركة المستند وجدوله ومعرّفه معاً.
    """

    attachment_table = ''
    attachment_entity_type = ''

    def attachment_label(self, obj) -> str:
        return str(obj.pk)

    @staticmethod
    def _attachment_row(att):
        return {
            'id': att.id,
            'url': att.file_path,
            'file_type': att.file_type or 'Image',
            'filename': (att.file_path or '').rsplit('/', 1)[-1] or 'مرفق',
            'uploaded_at': att.uploaded_at.isoformat() if att.uploaded_at else None,
        }

    def _log_attachment(self, obj, description):
        from core.activity import log_activity

        log_activity(
            action='update', entity_type=self.attachment_entity_type, entity_id=obj.pk,
            entity_label=self.attachment_label(obj)[:200], description=description,
            request=self.request,
        )

    @action(detail=True, methods=['get', 'post'], url_path='attachments')
    def attachments(self, request, pk=None):
        from rest_framework import status
        from rest_framework.response import Response

        from core.models import SystemAttachment

        obj = self.get_object()
        if request.method == 'POST':
            url = str(request.data.get('url') or '').strip()
            if not url.startswith(('http://', 'https://')):
                return Response({'error': 'رابط المرفق غير صالح.'}, status=status.HTTP_400_BAD_REQUEST)
            att, _created = SystemAttachment.objects.get_or_create(
                tenant_id=obj.tenant_id, related_table=self.attachment_table, related_id=obj.pk,
                file_path=url,
                defaults={'file_type': 'PDF' if url.lower().endswith('.pdf') else 'Image'},
            )
            self._log_attachment(obj, 'إرفاق ملف')
            return Response(self._attachment_row(att), status=status.HTTP_201_CREATED)
        rows = SystemAttachment.objects.filter(
            tenant_id=obj.tenant_id, related_table=self.attachment_table, related_id=obj.pk,
        ).order_by('id')
        return Response([self._attachment_row(a) for a in rows])

    @action(detail=True, methods=['delete'], url_path=r'attachments/(?P<attachment_id>[0-9]+)')
    def delete_attachment(self, request, pk=None, attachment_id=None):
        from rest_framework import status
        from rest_framework.response import Response

        from core.models import SystemAttachment

        obj = self.get_object()
        deleted, _ = SystemAttachment.objects.filter(
            id=attachment_id, tenant_id=obj.tenant_id,
            related_table=self.attachment_table, related_id=obj.pk,
        ).delete()
        if not deleted:
            return Response({'error': 'المرفق غير موجود.'}, status=status.HTTP_404_NOT_FOUND)
        self._log_attachment(obj, 'حذف مرفق')
        return Response(status=status.HTTP_204_NO_CONTENT)
