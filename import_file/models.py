"""ملف الاستيراد — بنود قائمة التحقّق ومرفقاتها.

الوحدة **محايدة مالياً بالكامل** على نمط `device_registry`: لا قيد ولا حركة
مخزون ولا مسّ لأي مبلغ. والاتجاه أُحادي — `import_file → logistics` — فلا FK
من أي app نحوها، وإطفاء ترخيصها لا يكسر شيئاً خارجها.

ثلاث قواعد تحكم هذا الملف:

- **المرساة واحدة بالضبط.** البند يرسو على صفقة أو على شحنة، لا على الاثنين
  ولا على لا شيء، ويفرضها `CheckConstraint` في قاعدة البيانات لا نيّةُ الكود.
- **لا فرادة شرطية.** فرادة `(tenant, deal, kind)` و`(tenant, shipment, kind)`
  مشروطتان بمرساةٍ فارغة، وMySQL لا تنفّذ الفرادة الشرطية بينما SQLite تنفّذها
  فيكذب الاختبار على الإنتاج (السابقة والسبب في `after_sales/models.py`).
  الحصر يعيش في `import_file/services.py` (`ensure_file_items`) بـ`get_or_create`.
- **حالة بند المستند مشتقّة** من وجود مرفق، لا عمود يُحدَّث. عمود `done` لبنود
  المهامّ وحدها؛ خلطهما كان يسمح بملفٍّ «مكتمل» بلا ورقة واحدة.

حقول `ImportFileDocument` تطابق عمداً شكل الـRFC المؤجَّل
(`docs/decisions/attachments_model.md`) — التوحيد لاحقاً ترحيل بيانات لا
إعادة تصميم.
"""
from django.db import models

from tenants.models import Tenant

from .catalog import (
    ITEM_DOCUMENT,
    ITEM_TASK,
    ITEM_TYPE_CHOICES,
    STAGE_CHOICES,
)


class ImportFileItem(models.Model):
    """بند في ملف الاستيراد — مستندٌ مطلوب أو مهمّة يدوية.

    `kind` مفتاح ثابت (سلَگ) يُعرَف به البند عبر الإصدارات؛ `label` عربيٌّ
    **مخزَّن** لا مُشتقٌّ من الكتالوج: بنود المستخدم المخصّصة لا كتالوج لها،
    وتغييرُ صياغةٍ في الكتالوج لاحقاً لا يجوز أن يعيد تسمية ملفاتٍ سابقة.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="import_file_items",
    )
    deal = models.ForeignKey(
        "logistics.LogisticsDeal", on_delete=models.CASCADE, null=True, blank=True,
        related_name="import_file_items",
    )
    shipment = models.ForeignKey(
        "logistics.LogisticsShipment", on_delete=models.CASCADE, null=True, blank=True,
        related_name="import_file_items",
        help_text="وثائق الشحن والتخليص ترسو على الشحنة وتظهر في ملف كل صفقة عليها",
    )

    stage = models.CharField(max_length=16, choices=STAGE_CHOICES)
    item_type = models.CharField(
        max_length=16, choices=ITEM_TYPE_CHOICES, default=ITEM_DOCUMENT,
    )
    kind = models.CharField(max_length=64)
    label = models.CharField(max_length=200)

    required = models.BooleanField(
        default=True, help_text="يدخل مقام نسبة اكتمال المرحلة",
    )
    done = models.BooleanField(
        default=False, help_text="لبنود المهامّ وحدها — حالة المستند مشتقّة من مرفقه",
    )
    note = models.CharField(max_length=300, blank=True, default="")
    position = models.PositiveSmallIntegerField(default=0)

    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_import_file_items",
        help_text="فارغ لبنود الكتالوج — النظام زرعها لا مستخدم",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "import_file_items"
        constraints = [
            # مرساةٌ فارغة تُنتج بنداً لا ملف له، ومرساتان تُنتجان بنداً يظهر
            # في ملفين ويُحسب مرتين. القيد في القاعدة لأن كِلا الخطأين يُكتب
            # صامتاً ويُقرأ متأخراً.
            models.CheckConstraint(
                condition=(
                    models.Q(deal__isnull=False, shipment__isnull=True)
                    | models.Q(deal__isnull=True, shipment__isnull=False)
                ),
                name="import_file_item_one_anchor",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "deal"], name="impfile_item_tenant_deal_idx"),
            models.Index(fields=["tenant", "shipment"], name="impfile_item_tenant_ship_idx"),
        ]
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.label} ({self.kind})"

    @property
    def is_done(self) -> bool:
        """منجَز = مهمّة معلَّمة، أو بند مستند له مرفق واحد على الأقل.

        تقرأ `document_count` حين يكون البند مُثرىً به (`file_items_for_deal`
        تُثريه دائماً)؛ وإلا استعلمت — قراءةٌ مفردة تكلّف استعلاماً، وقائمةٌ
        غير مُثراة تكلّف N+1، فأثرِها.
        """
        if self.item_type == ITEM_TASK:
            return self.done
        count = getattr(self, "document_count", None)
        if count is None:
            count = self.documents.count()
        return count > 0


class ImportFileDocument(models.Model):
    """ملف مرفوع يُشبع بند مستند.

    الرفع نفسه يمرّ بمسار المنصة القائم (`POST /api/media/upload/`) ويُسجَّل
    هنا رابطُه ووصفه — لا مسار رفع ثانٍ.
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="import_file_documents",
    )
    item = models.ForeignKey(
        ImportFileItem, on_delete=models.CASCADE, related_name="documents",
    )

    url = models.CharField(max_length=500)
    filename = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=100, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)

    uploaded_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_import_file_documents",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "import_file_documents"
        indexes = [
            models.Index(fields=["tenant", "item"], name="impfile_doc_tenant_item_idx"),
        ]
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return self.filename or self.url
