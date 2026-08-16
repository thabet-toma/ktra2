"""سيريالايزرات ملف الاستيراد — والصفّ المشتقّ الذي يُعرض ولا يُخزَّن.

ثلاث قواعد تحكم هذا الملف:

- **المرساة تُحلّ بشركة الطلب.** `TenantScopedPrimaryKeyRelatedField` يقيّد
  الصفقة والشحنة بالشركة النشطة وقت الحلّ، فمعرّف شركة أخرى يصير «غير موجود»
  برسالة DRF القياسية — لا يكشف وجود السجل ولا يعبر إليه.
- **بند الكتالوج اسمُه ثابت.** الملف يُقرأ عبر الزمن، وإعادة تسمية «الفاتورة
  المبدئية» تجعل ملفاً قديماً يتحدث لغةً لا يعرفها أحد. المخصّص وحده يُعاد تسميته.
- **علامة الإنجاز لبنود المهامّ وحدها.** بند المستند يكتمل بمرفقه؛ قبول `done`
  عليه كان يكتب قيمةً لا تُقرأ ويُري المستخدم «منجَزاً» لا وجود لورقته.
"""
from collections import defaultdict

from rest_framework import serializers

from core.api_defaults import TenantScopedPrimaryKeyRelatedField
from logistics.models import LogisticsDeal, LogisticsShipment

from .catalog import CATALOG_KINDS, ITEM_TASK, STAGE_CHOICES
from .models import ImportFileDocument, ImportFileItem
from .services import derived_freight_row, file_items_for_deal, stage_progress


class ImportFileDocumentSerializer(serializers.ModelSerializer):
    """المرفق قراءةً وكتابةً — الرفع نفسه سبق عبر `POST /api/media/upload/`."""

    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ImportFileDocument
        fields = [
            "id", "url", "filename", "mime_type", "size_bytes",
            "uploaded_by", "uploaded_by_name", "uploaded_at",
        ]
        # الشركة والبند والرافع من سياق الطلب لا من جسمه.
        read_only_fields = ["uploaded_by", "uploaded_at"]

    def get_uploaded_by_name(self, obj):
        if not obj.uploaded_by_id:
            return ""
        return obj.uploaded_by.get_full_name() or obj.uploaded_by.username

    def validate_url(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("رابط الملف مطلوب — ارفع الملف أولاً.")
        return value


class ImportFileItemSerializer(serializers.ModelSerializer):
    """صفّ البند كما تقرؤه الشاشة — بشكلٍ يطابق شكل الصفّ المشتقّ حرفياً."""

    documents = ImportFileDocumentSerializer(many=True, read_only=True)
    is_done = serializers.BooleanField(read_only=True)
    is_custom = serializers.SerializerMethodField()
    derived = serializers.SerializerMethodField()

    class Meta:
        model = ImportFileItem
        fields = [
            "id", "stage", "item_type", "kind", "label", "required",
            "done", "is_done", "note", "position", "is_custom", "derived",
            "documents", "created_at",
        ]

    def get_is_custom(self, obj) -> bool:
        return obj.kind not in CATALOG_KINDS

    def get_derived(self, obj) -> bool:
        # ثابتة: البند المخزَّن ليس مشتقّاً أبداً. الحقل موجود ليقرأه المستخدم
        # بالمفتاح نفسه في الصفّين، فلا يحتاج شكلين لصفّ واحد.
        return False


class ImportFileItemCreateSerializer(serializers.ModelSerializer):
    """بند يضيفه المستخدم فوق الكتالوج — مستنداً كان أو مهمّة."""

    deal = TenantScopedPrimaryKeyRelatedField(
        queryset=LogisticsDeal.objects.all(), required=False, allow_null=True,
    )
    shipment = TenantScopedPrimaryKeyRelatedField(
        queryset=LogisticsShipment.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = ImportFileItem
        fields = ["deal", "shipment", "stage", "item_type", "label", "required", "note"]

    def validate_label(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("اسم البند مطلوب.")
        return value

    def validate(self, attrs):
        if bool(attrs.get("deal")) == bool(attrs.get("shipment")):
            raise serializers.ValidationError({
                "deal": "البند يرسو على صفقة أو على شحنة — واحدة بالضبط لا اثنتان ولا صفر."
            })
        return attrs


class ImportFileItemUpdateSerializer(serializers.ModelSerializer):
    """ما يُعدَّل على بند قائم: حالته ولزومه وملاحظته، واسمه إن كان مخصّصاً."""

    class Meta:
        model = ImportFileItem
        fields = ["done", "required", "note", "label"]

    def validate_label(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("اسم البند مطلوب.")
        return value

    def validate(self, attrs):
        item = self.instance
        label = attrs.get("label")
        if label is not None and label != item.label and item.kind in CATALOG_KINDS:
            raise serializers.ValidationError({
                "label": (
                    "هذا بند من القائمة الافتراضية — اسمه ثابت ليبقى الملف مقروءاً "
                    "عبر الصفقات. أضف بنداً مخصّصاً إن أردت صياغتك."
                )
            })
        if "done" in attrs and item.item_type != ITEM_TASK:
            raise serializers.ValidationError({
                "done": "بند المستند يكتمل برفع مرفقه لا بعلامة يدوية."
            })
        return attrs


def serialize_import_file(deal, shipment) -> dict:
    """الملف كاملاً: البنود بمراحلها ومرفقاتها، الصفّ المشتقّ، ونِسَب الاكتمال.

    المراحل الفارغة تُحذف: مرحلةٌ بلا بند ولا صفّ ليست معلومة، وعرضها ٠/٠ يملأ
    الشاشة بأربع مراحل صامتة. والمرحلة تظهر لحظة يضيف المستخدم بنداً فيها.
    """
    items = list(file_items_for_deal(deal).prefetch_related("documents"))
    rows: dict[str, list] = defaultdict(list)
    for item in items:
        rows[item.stage].append(ImportFileItemSerializer(item).data)

    derived = derived_freight_row(shipment)
    if derived is not None:
        rows[derived["stage"]].append(derived)

    progress = stage_progress(items, shipment=shipment)
    stages = [
        {
            "stage": key,
            "label": label,
            "items": rows[key],
            "progress": progress.get(key, {"done": 0, "total": 0}),
        }
        for key, label in STAGE_CHOICES
        if rows[key]
    ]
    return {
        "deal": {"id": deal.pk, "ref_number": deal.ref_number},
        "shipment": (
            {"id": shipment.pk, "shipment_number": shipment.shipment_number}
            if shipment is not None else None
        ),
        "stages": stages,
        "progress": {
            "done": sum(stage["progress"]["done"] for stage in stages),
            "total": sum(stage["progress"]["total"] for stage in stages),
        },
    }
