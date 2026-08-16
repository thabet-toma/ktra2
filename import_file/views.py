"""API ملف الاستيراد — وحدة مرخّصة محايدة مالياً.

ترتيب البوابتين مقصود ولا يُعكس: `require_module` **قبل** `require_perm` في
`initial()`، فترد الشركة غير المرخّصة **404 لا 403** — 403 يُثبت وجود الوحدة،
و404 لا يُثبت شيئاً (سابقة `after_sales/views.py` و`device_registry/views.py`).

الشركة تأتي من الحارس نفسه لا من جسم الطلب، وكل استعلام مقيَّد بها — فمعرّف
صفقةٍ أو بندٍ من شركة أخرى «غير موجود» مهما مُرِّر صراحةً.

الرفع لا يمرّ من هنا: الملف يُرفع بمسار المنصة القائم (`POST /api/media/upload/`)
ويُسجَّل رابطه هنا. مسار رفعٍ ثانٍ كان يعني حدّ حجمٍ ثانياً وقياس تخزينٍ ثانياً.
"""
import logging
from uuid import uuid4

from rest_framework import mixins, status as http_status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.access import require_perm
from core.api_defaults import ApiAuthAndUser
from core.media_views import destroy_cloudinary_asset
from core.modules import require_module
from logistics.models import LogisticsDeal

from .catalog import CATALOG_KINDS, DEFAULT_CATALOG
from .models import ImportFileDocument, ImportFileItem
from .serializers import (
    ImportFileDocumentSerializer,
    ImportFileItemCreateSerializer,
    ImportFileItemSerializer,
    ImportFileItemUpdateSerializer,
    serialize_import_file,
)
from .services import ensure_file_items, shipment_for_deal

logger = logging.getLogger(__name__)

MODULE_KEY = "import_file"

PERM_VIEW = "importfile.file.view"
PERM_MANAGE = "importfile.file.manage"


class LicensedImportFileViewSet(viewsets.GenericViewSet):
    """الأساس المشترك: الترخيص ثم الصلاحية ثم الشركة النشطة في كل استعلام."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    action_perms: dict[str, str] = {}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # الترخيص أولاً: بلا ترخيص لا يُكشف حتى أن الصلاحية ناقصة.
        self.tenant = require_module(request, MODULE_KEY)
        required = self.action_perms.get(self.action)
        if required:
            require_perm(request, required, tenant=self.tenant)


class DealImportFileViewSet(LicensedImportFileViewSet):
    """ملف صفقة واحدة — قراءةٌ واحدة تُرجع كل ما تعرضه الشاشة."""

    serializer_class = ImportFileItemSerializer
    action_perms = {"file": PERM_VIEW}

    def get_queryset(self):
        return LogisticsDeal.objects.filter(tenant=self.tenant)

    @action(detail=True, methods=["get"], url_path="file")
    def file(self, request, pk=None):
        """يفتح الملف ويزرع ما ينقصه — قراءةٌ بأثر كتابة idempotent.

        التزريع عند الفتح لا عند إنشاء الصفقة: الصفقات السابقة كلها كانت ستبقى
        بلا ملف، والصفقة التي تنضمّ إلى شحنة بعد إنشائها كانت ستبقى بلا بنود شحنة.
        """
        deal = self.get_object()
        ensure_file_items(deal)
        return Response(serialize_import_file(deal, shipment_for_deal(deal)))


class ImportFileItemViewSet(
    mixins.CreateModelMixin, mixins.DestroyModelMixin, LicensedImportFileViewSet,
):
    """بنود الملف — إضافة مخصّصة، تعديل، حذف، وإرفاق مستند.

    لا `update` هنا عمداً: البند يُعدَّل بـPATCH لحقوله المسموحة وحدها، و`PUT`
    كان سيعني استبدال صفٍّ كامل بمرساته ومفتاحه.
    """

    serializer_class = ImportFileItemSerializer
    action_perms = {
        "create": PERM_MANAGE,
        "partial_update": PERM_MANAGE,
        "destroy": PERM_MANAGE,
        "add_document": PERM_MANAGE,
    }

    def get_queryset(self):
        return (
            ImportFileItem.objects
            .filter(tenant=self.tenant)
            .prefetch_related("documents")
        )

    def create(self, request, *args, **kwargs):
        form = ImportFileItemCreateSerializer(
            data=request.data, context=self.get_serializer_context(),
        )
        form.is_valid(raise_exception=True)
        item = form.save(
            tenant=self.tenant,
            # مفتاح البند المخصّص من الخادم: ما ليس في الكتالوج مخصّص، وهو
            # التمييز الوحيد الذي لا يتبدّل بحذف مستخدم أو بتحرير حقل.
            kind=f"custom_{uuid4().hex[:12]}",
            # بعد كل بنود الكتالوج، وترتيبها بينها بترتيب إنشائها (`id`).
            position=len(DEFAULT_CATALOG),
            created_by=request.user,
        )
        return Response(
            ImportFileItemSerializer(item).data, status=http_status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        item = self.get_object()
        form = ImportFileItemUpdateSerializer(item, data=request.data, partial=True)
        form.is_valid(raise_exception=True)
        return Response(ImportFileItemSerializer(form.save()).data)

    def perform_destroy(self, instance):
        if instance.kind in CATALOG_KINDS:
            raise ValidationError({
                "detail": (
                    "بند من القائمة الافتراضية لا يُحذف — علّمه «غير مطلوب» فيخرج من "
                    "حساب الاكتمال ويبقى سؤاله في الملف."
                )
            })
        instance.delete()

    @action(detail=True, methods=["post"], url_path="documents")
    def add_document(self, request, pk=None):
        """يسجّل ملفاً رُفع سلفاً عبر `/api/media/upload/` — لا بايتات تمرّ هنا."""
        item = self.get_object()
        form = ImportFileDocumentSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        document = form.save(
            tenant=self.tenant, item=item, uploaded_by=request.user,
        )
        return Response(
            ImportFileDocumentSerializer(document).data,
            status=http_status.HTTP_201_CREATED,
        )


class ImportFileDocumentViewSet(mixins.DestroyModelMixin, LicensedImportFileViewSet):
    """المرفقات — الحذف وحده؛ الإضافة على بندها، والتعديل لا معنى له لملف مرفوع."""

    serializer_class = ImportFileDocumentSerializer
    action_perms = {"destroy": PERM_MANAGE}

    def get_queryset(self):
        return ImportFileDocument.objects.filter(tenant=self.tenant)

    def perform_destroy(self, instance):
        """الصفّ أولاً ثم الأصل: SQL هو المصدر الموثوق، وحذف Cloudinary أفضل-جهد.

        تركُ الأصل بعد حذف صفّه يترك blob يتيماً تُدفع فاتورته ولا يراه أحد.
        """
        url = instance.url
        instance.delete()
        destroy_cloudinary_asset(url)
