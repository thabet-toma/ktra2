"""مفردات ملف الاستيراد وقائمته الافتراضية — بيانات صرفة بلا ORM.

`models.py` يستورد مفرداته من هنا؛ لو انعكس الاتجاه لصار الاستيراد دائرياً.
ولأن الملف بلا قاعدة بيانات، يُختبر الكتالوج كما تُختبر أي دالة صافية.

**مفردات المراحل ليست ملكاً لهذه الوحدة.** هي مفاتيح `ImportStageKey` الثمانية
نفسها في `frontend_v2/components/import-flow/importJourneyGuidance.ts`
(`IMPORT_JOURNEY_STAGES`) — مفردةٌ واحدة للرحلة كلها؛ ثانيةٌ تعني شاشتين
تتحدثان لغتين عن الشيء نفسه. الكتالوج يستعمل أربعاً من الثمانية.

**سعر الشحن (CBM) ليس بنداً هنا عمداً.** هو معطى مهيكل يملكه النظام أصلاً
(`LogisticsShipment.freight_rate`)؛ رفعه كملف يخلق مصدراً ثانياً لقيمةٍ لها
مصدر مختبَر. يُعرض في الملف صفّاً **مشتقّاً** يُحسب في الـserializer بلا تخزين.
"""
from dataclasses import dataclass

# ── المراحل: مفاتيح `ImportStageKey` الثمانية، بالترتيب نفسه ────────────────
STAGE_OFFER = "offer"
STAGE_DEAL = "deal"
STAGE_DEAL_PAYMENTS = "deal_payments"
STAGE_SHIPMENT = "shipment"
STAGE_FREIGHT = "freight"
STAGE_CLEARANCE = "clearance"
STAGE_LOCAL = "local"
STAGE_INVOICE = "invoice"

#: التسميات مطابقة لـ`IMPORT_JOURNEY_STAGES` في الواجهة — لا تُترجَم ثانيةً هنا.
STAGE_CHOICES = [
    (STAGE_OFFER, "عرض سعر الاستيراد"),
    (STAGE_DEAL, "الصفقة"),
    (STAGE_DEAL_PAYMENTS, "دفعات الصفقة"),
    (STAGE_SHIPMENT, "الشحنة الدولية"),
    (STAGE_FREIGHT, "الشحن الدولي"),
    (STAGE_CLEARANCE, "التخليص الجمركي"),
    (STAGE_LOCAL, "النقل المحلي"),
    (STAGE_INVOICE, "فاتورة الشراء الدولية"),
]
STAGE_KEYS = [key for key, _ in STAGE_CHOICES]

# ── نوع البند ───────────────────────────────────────────────────────────────
ITEM_DOCUMENT = "document"
ITEM_TASK = "task"
ITEM_TYPE_CHOICES = [
    (ITEM_DOCUMENT, "مستند"),
    (ITEM_TASK, "مهمّة"),
]

# ── المرساة: على أيّ مستند يعلَّق البند ────────────────────────────────────
#: مستندات الصفقة (عرض المورد، PI…) خاصّة بها. مستندات الشحن والتخليص وثائق
#: **شحنة**، والشحنة تحمل عدة صفقات — فترسو على الشحنة وتظهر في ملف كل صفقة
#: عليها. رفعةٌ واحدة تُكمل ملفاتها جميعاً بدل نسخٍ متضاربة لوثيقةٍ واحدة.
ANCHOR_DEAL = "deal"
ANCHOR_SHIPMENT = "shipment"

# ── الصفّ المشتقّ: سعر الشحن ────────────────────────────────────────────────
#: يُعرض في مرحلة الشحنة صفّاً كامل الشكل، ويُبنى في `services.derived_freight_row`
#: من `LogisticsShipment.freight_rate` بلا تخزين. `item_type` خاصٌّ به لأن الواجهة
#: تحتاج أن تعرف أنه لا يُعدَّل من هنا — الملاحظة تقول للمستخدم أين يُدخَل.
ITEM_DERIVED = "derived"
DERIVED_FREIGHT_KIND = "freight_rate"
DERIVED_FREIGHT_LABEL = "سعر الشحن الدولي (لكل CBM أو KG)"
DERIVED_FREIGHT_NOTE = "معطى من بطاقة الشحنة — يُدخَل هناك ولا يُرفع ملفاً."


@dataclass(frozen=True)
class CatalogEntry:
    """بند افتراضي واحد. `kind` مفتاحه الثابت الذي يُعرَف به عبر الإصدارات."""

    stage: str
    anchor: str
    kind: str
    label: str
    required: bool
    item_type: str = ITEM_DOCUMENT


#: الترتيب هنا هو `position` المخزَّن — ترتيب الرحلة كما يمشيها المستخدم.
#: الثلاثية الإلزامية (بوليصة الشحن، قائمة التعبئة، الفاتورة التجارية) هي
#: الإجماع الصناعي؛ والاختيارية الثلاث تُعرض ولا تدخل مقام نسبة الاكتمال إلا
#: إن علّمها المستخدم مطلوبة.
DEFAULT_CATALOG = [
    CatalogEntry(STAGE_OFFER, ANCHOR_DEAL, "supplier_offer", "عرض المورد", True),
    CatalogEntry(STAGE_OFFER, ANCHOR_DEAL, "datasheet", "الداتا شيت", True),

    CatalogEntry(STAGE_DEAL, ANCHOR_DEAL, "proforma_invoice", "الفاتورة المبدئية (PI)", True),
    CatalogEntry(STAGE_DEAL, ANCHOR_DEAL, "order_confirmation", "تأكيد الطلب", True),
    CatalogEntry(
        STAGE_DEAL, ANCHOR_DEAL, "task_match_datasheet",
        "طابِق الداتا شيت مع بنود الصفقة", False, ITEM_TASK,
    ),

    CatalogEntry(STAGE_SHIPMENT, ANCHOR_SHIPMENT, "bill_of_lading", "بوليصة الشحن (B/L أو AWB)", True),
    CatalogEntry(STAGE_SHIPMENT, ANCHOR_SHIPMENT, "packing_list", "قائمة التعبئة", True),
    CatalogEntry(STAGE_SHIPMENT, ANCHOR_SHIPMENT, "commercial_invoice", "الفاتورة التجارية", True),
    CatalogEntry(STAGE_SHIPMENT, ANCHOR_SHIPMENT, "booking_confirmation", "تأكيد الحجز", False),
    CatalogEntry(STAGE_SHIPMENT, ANCHOR_SHIPMENT, "certificate_of_origin", "شهادة المنشأ", False),
    CatalogEntry(STAGE_SHIPMENT, ANCHOR_SHIPMENT, "insurance_certificate", "شهادة التأمين", False),

    CatalogEntry(STAGE_CLEARANCE, ANCHOR_SHIPMENT, "customs_declaration", "البيان الجمركي", True),
    CatalogEntry(STAGE_CLEARANCE, ANCHOR_SHIPMENT, "duties_receipt", "إيصال الرسوم", True),
    CatalogEntry(
        STAGE_CLEARANCE, ANCHOR_SHIPMENT, "task_cross_check_fields",
        "تحقّق تطابق رمز HS والأوزان واسم المرسل إليه عبر المستندات", False, ITEM_TASK,
    ),
]

#: بند الكتالوج يُعرَف بمفتاحه لا بمن أنشأه: `created_by` هو SET_NULL، فحذف
#: مستخدمٍ كان سيحوّل بنوده المخصّصة إلى «بنود نظام» غير قابلة للحذف.
CATALOG_KINDS = frozenset(entry.kind for entry in DEFAULT_CATALOG)
