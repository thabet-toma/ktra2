"""رابط المشاركة العام — الصفّ الذي يحوّل مستنداً داخلياً إلى صفحة يفتحها الغريب.

**لماذا app مستقلة:** الحجّة أمنية لا تنظيمية، وهي نفس حجّة `store`. كل كود
`AllowAny` في المنصة يعيش في مجلدين يقرؤهما مراجع الأمن كاملين في جلسة، ويبقى
`sales/views.py` مئة بالمئة خلف المصادقة — بدل view عام مدسوس بين عشرين view
محمي حيث يصير سطرٌ خاطئ في `get_queryset` تسريباً لا يلاحظه أحد.

**لماذا `(doc_type, doc_id)` ولا مفتاح أجنبي:** المستندان اليوم في `sales`،
والمشاركة ستمتدّ إلى `LogisticsDeal` و`CustomerPayment` في apps أخرى. مفتاحٌ
أجنبيّ اختياريّ لكل نوع يعني عموداً جديداً وهجرةً مع كل توسيع. والنصّ + العدد
يجعلان التوسيع سطراً في `documents.DOC_TYPES` بلا هجرة إطلاقاً.
و`GenericForeignKey` مرفوض: يجرّ `ContentType` ويكسر مبدأ السيريالايزر الصريح
الذي تقوم عليه سلامة هذا السطح.

**لماذا التوكن مخزَّن خاماً** — بخلاف دعوة المحاسب (`accountant_portal.models`
(`AccountantEngagement.invitation_token_hash`)) التي تُهشَّر: تلك تُستهلَك مرة
واحدة فلا حاجة لإعادة إظهارها، وهذه تُفتح مراراً و**يجب** أن يقدر المالك على
إعادة نسخ الرابط من نافذة المشاركة بعد أسبوع — وذلك مستحيل مع تهشيرٍ أحادي.
هو نفس اختيار Odoo (`access_token` خام على السجل). المقابل معلوم: تسريب نسخة
القاعدة يسرّب الروابط الحيّة، ويخفّفه الانتهاء الإلزامي والإبطال الفوري
وعشوائية 256 بت.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from tenants.models import Tenant

#: أنواع المستندات المشمولة. التوسيع = سطر هنا وسطر في `documents.DOC_TYPES`.
DOC_SALES_INVOICE = "sales_invoice"
DOC_SALES_QUOTATION = "sales_quotation"
DOC_TYPE_CHOICES = [
    (DOC_SALES_INVOICE, "فاتورة بيع"),
    (DOC_SALES_QUOTATION, "عرض سعر"),
]

DECISION_ACCEPTED = "accepted"
DECISION_REJECTED = "rejected"
DECISION_CHOICES = [
    (DECISION_ACCEPTED, "مقبول"),
    (DECISION_REJECTED, "مرفوض"),
]


class DocumentShare(models.Model):
    """رابط عام واحد لمستند واحد.

    الصفوف المُبطَلة **لا تُحذف**: الرابط الذي خرج إلى واتساب مرة واحدة يبقى
    له أثر يُسأل عنه لاحقاً («مين شارك هالفاتورة ومتى؟»). لذلك لا قيد فرادة
    على `(tenant, doc_type, doc_id)` — الفرادة على التوكن وحده.
    """

    id = models.AutoField(primary_key=True, db_column="DocumentShareID")
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="TenantID",
        to_field="TenantID",
        related_name="document_shares",
    )
    doc_type = models.CharField(
        max_length=20, choices=DOC_TYPE_CHOICES, db_column="DocType",
    )
    doc_id = models.PositiveIntegerField(db_column="DocID")
    #: `secrets.token_urlsafe(32)` = 43 محرفاً. العمود 64 ليتّسع لتغيير الطول لاحقاً.
    token = models.CharField(
        max_length=64, unique=True, db_index=True, db_column="Token",
    )
    #: **إلزامي بلا قيمة فارغة** — «رابط بلا انتهاء» حالةٌ لا نريد أن توجد أصلاً.
    expires_at = models.DateTimeField(db_column="ExpiresAt")
    revoked_at = models.DateTimeField(null=True, blank=True, db_column="RevokedAt")

    view_count = models.PositiveIntegerField(default=0, db_column="ViewCount")
    first_viewed_at = models.DateTimeField(
        null=True, blank=True, db_column="FirstViewedAt",
    )
    last_viewed_at = models.DateTimeField(
        null=True, blank=True, db_column="LastViewedAt",
    )

    #: قرار المستلم — لعرض السعر وحده اليوم. فارغ = لم يُقرَّر بعد.
    decision = models.CharField(
        max_length=10, blank=True, default="", choices=DECISION_CHOICES,
        db_column="Decision",
    )
    decided_at = models.DateTimeField(null=True, blank=True, db_column="DecidedAt")
    decided_ip = models.CharField(
        max_length=64, blank=True, default="", db_column="DecidedIP",
    )
    decided_name = models.CharField(
        max_length=120, blank=True, default="", db_column="DecidedName",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        db_column="CreatedBy_UserID",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_column="CreatedAt")

    class Meta:
        db_table = "document_shares"
        managed = True
        indexes = [
            models.Index(
                fields=["tenant", "doc_type", "doc_id"], name="docshare_doc_idx",
            ),
            models.Index(fields=["tenant", "created_at"], name="docshare_tenant_ts_idx"),
        ]

    def __str__(self):
        return f"{self.doc_type}#{self.doc_id} → {self.token[:8]}…"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_live(self) -> bool:
        """حيّ = لا مُبطَل ولا منتهٍ. هذه هي الدالة الوحيدة التي تعرّف «حيّ»."""
        return not self.is_revoked and not self.is_expired
