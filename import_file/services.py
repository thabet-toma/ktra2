"""تزريع ملف الاستيراد وقراءته وحساب اكتماله.

`ensure_file_items` **قراءةٌ بأثر كتابة idempotent**: تُستدعى عند كل فتح للملف
فتُنشئ ما ينقص ولا تكرّر ما وُجد (سابقة `resolve_warranty_expense_account` —
«يُنشأ ويُثبَّت»). البديل — التزريع مرّةً عند إنشاء الصفقة — كان يترك كل صفقة
سابقة بلا ملف، ويترك الصفقة التي انضمّت إلى شحنة بعد إنشائها بلا بنود شحنة
أبداً.

عزل الشركة في كل استعلام هنا: الصفقة هي مصدر `tenant`، والشحنة تُقرأ مفلترةً
بها لا بمعرّف الربط وحده.
"""
from collections import defaultdict

from django.db.models import Count, Q

from logistics.models import LogisticsShipment, LogisticsShipmentDeal

from .catalog import (
    ANCHOR_SHIPMENT,
    DEFAULT_CATALOG,
    DERIVED_FREIGHT_KIND,
    DERIVED_FREIGHT_LABEL,
    DERIVED_FREIGHT_NOTE,
    ITEM_DERIVED,
    STAGE_SHIPMENT,
)
from .models import ImportFileItem


def shipment_id_for_deal(deal) -> int | None:
    """معرّف الشحنة التي انضمّت إليها الصفقة، إن وُجدت.

    الصفقة تعيش على شحنة واحدة كحد أقصى — قاعدة يفرضها الضمّ نفسه في
    `logistics/domain/shipment_builder.py` (`create_shipment_from_deals` يرفض
    صفقةً مربوطة بشحنة). لذلك مسار الملف خطيّ: بنود الصفقة + بنود شحنتها.
    """
    return (
        LogisticsShipmentDeal.objects
        .filter(deal_id=deal.pk, shipment__tenant_id=deal.tenant_id)
        .values_list("shipment_id", flat=True)
        .first()
    )


def shipment_for_deal(deal):
    """كائن شحنة الصفقة — يقرأه الصفّ المشتقّ، بالفلترة نفسها لا بالمعرّف وحده."""
    shipment_id = shipment_id_for_deal(deal)
    if shipment_id is None:
        return None
    return (
        LogisticsShipment.objects
        .filter(pk=shipment_id, tenant_id=deal.tenant_id)
        .first()
    )


def derived_freight_row(shipment) -> dict | None:
    """صفّ سعر الشحن — يُعرض ولا يُخزَّن، ومصدره الوحيد بطاقة الشحنة.

    **هذه الدالة هي المصدر الواحد للصفّ ولحسابه معاً.** الصفّ يُعرض في الملف
    كبندٍ مطلوب، فيدخل مقام مرحلة الشحنة: صفٌّ ظاهر يقول «غير منجَز» بينما
    النسبة تقول ١٠٠٪ رقمٌ لا يستطيع المستخدم تفسيره. لذلك يبنيه الـserializer
    من هنا، ويحسبه `stage_progress` من هنا — فلا صيغتان لشيء واحد.
    """
    if shipment is None:
        return None
    rate = shipment.freight_rate
    return {
        "id": None,
        "stage": STAGE_SHIPMENT,
        "item_type": ITEM_DERIVED,
        "kind": DERIVED_FREIGHT_KIND,
        "label": DERIVED_FREIGHT_LABEL,
        "required": True,
        "done": bool(rate and rate > 0),
        "is_done": bool(rate and rate > 0),
        "note": DERIVED_FREIGHT_NOTE,
        "position": len(DEFAULT_CATALOG),
        "is_custom": False,
        "derived": True,
        "documents": [],
        "created_at": None,
    }


def ensure_file_items(deal) -> int:
    """يزرع بنود الكتالوج الناقصة لهذه الصفقة ولشحنتها. يُرجع عدد ما أُنشئ.

    الفرادة `(tenant, deal|shipment, kind)` تُفرض هنا بـ`get_or_create` لا بقيد
    شرطي في القاعدة — السبب في `import_file/models.py`.
    """
    shipment_id = shipment_id_for_deal(deal)
    created = 0
    for position, entry in enumerate(DEFAULT_CATALOG):
        if entry.anchor == ANCHOR_SHIPMENT:
            if shipment_id is None:
                continue
            anchor = {"deal": None, "shipment_id": shipment_id}
        else:
            anchor = {"deal_id": deal.pk, "shipment": None}

        _, was_created = ImportFileItem.objects.get_or_create(
            tenant_id=deal.tenant_id,
            kind=entry.kind,
            **anchor,
            defaults={
                "stage": entry.stage,
                "item_type": entry.item_type,
                "label": entry.label,
                "required": entry.required,
                "position": position,
            },
        )
        created += int(was_created)
    return created


def file_items_for_deal(deal):
    """بنود ملف هذه الصفقة: صفوفها + صفوف شحنتها، مُثراةً بعدد المرفقات.

    الإثراء ليس تحسيناً اختيارياً — بدونه تصير `is_done` استعلاماً لكل بند.
    """
    anchor = Q(deal_id=deal.pk)
    shipment_id = shipment_id_for_deal(deal)
    if shipment_id is not None:
        anchor |= Q(shipment_id=shipment_id)
    return (
        ImportFileItem.objects
        .filter(anchor, tenant_id=deal.tenant_id)
        .annotate(document_count=Count("documents"))
    )


def stage_progress(items, *, shipment=None) -> dict[str, dict[str, int]]:
    """`{stage: {done, total}}` — **البنود المطلوبة وحدها** بسطاً ومقاماً.

    البند الاختياري خارج الكسر بطرفيه: إدخاله في المقام وحده يجعل ملفاً كامل
    الأوراق يظهر ناقصاً إلى الأبد، وإدخاله في البسط وحده يتجاوز المئة. من أراده
    محسوباً علّمه `required` — وهي القيمة الوحيدة التي يملكها هنا.

    تمرير `shipment` يضمّ الصفّ المشتقّ (سعر الشحن) إلى مرحلة الشحنة — يمرّره كل
    من يعرض الصفّ، فيتطابق ما يُعرض مع ما يُحسب دائماً.
    """
    progress: dict[str, dict[str, int]] = {}
    for item in items:
        if not item.required:
            continue
        bucket = progress.setdefault(item.stage, {"done": 0, "total": 0})
        bucket["total"] += 1
        if item.is_done:
            bucket["done"] += 1

    derived = derived_freight_row(shipment)
    if derived is not None:
        bucket = progress.setdefault(derived["stage"], {"done": 0, "total": 0})
        bucket["total"] += 1
        bucket["done"] += int(derived["is_done"])
    return progress


def attach_file_progress(summary, tenant):
    """يضيف `file_progress` إلى صفوف ملخّص رحلة الاستيراد — صفقاتها وشحناتها.

    الإثراء يعيش هنا لا في `logistics/import_journey.py`: المرشد يعمل كما هو حين
    تُطفأ هذه الوحدة أو تُحذف، ولا يعرف بانٍ عام بوحدةٍ مرخّصة.

    **الحساب هو `stage_progress` نفسها التي تحسب لوحة الملف**، بالبنود نفسها
    (بنود الصفقة + بنود شحنتها) وبالشحنة نفسها ممرَّرةً. لو حُسب هنا بصيغة ثانية
    لاختلفت شارة المرشد عن الملف بواحد على كل شحنة — الصفّ المشتقّ — ورقمٌ يخالف
    مصدره على الشاشة نفسها لا يستطيع المستخدم تفسيره.

    ثلاثة استعلامات جماعية مهما بلغ عدد الصفوف — بنود الصفقات، بنود الشحنات،
    ثم أسعار الشحن. استعلامٌ لكل صفّ هنا يهبط على شاشةٍ تُحمَّل في كل صفحة استيراد.

    التزريع ليس من شأنها: الملف يُزرع عند فتحه (`ensure_file_items`)، فالمرشد
    يعرض ما هو مسجَّل لا ما سيُنشأ — قراءةٌ تكتب لكل صفقة نشطة في كل تحميل صفحة
    ثمنٌ لا يقابله شيء.
    """
    deal_rows = summary.get("deals", {}).get("rows", [])
    shipment_rows = summary.get("shipments", [])

    deal_ids = [row["id"] for row in deal_rows]
    shipment_ids = {row["id"] for row in shipment_rows}
    shipment_ids.update(row["shipment_id"] for row in deal_rows if row["shipment_id"])

    items_by_deal: dict[int, list] = defaultdict(list)
    if deal_ids:
        for item in (
            ImportFileItem.objects
            .filter(tenant=tenant, deal_id__in=deal_ids)
            .annotate(document_count=Count("documents"))
        ):
            items_by_deal[item.deal_id].append(item)

    items_by_shipment: dict[int, list] = defaultdict(list)
    shipments: dict[int, LogisticsShipment] = {}
    if shipment_ids:
        for item in (
            ImportFileItem.objects
            .filter(tenant=tenant, shipment_id__in=shipment_ids)
            .annotate(document_count=Count("documents"))
        ):
            items_by_shipment[item.shipment_id].append(item)
        shipments = {
            shipment.pk: shipment
            for shipment in LogisticsShipment.objects
            .filter(tenant=tenant, pk__in=shipment_ids)
            .only("id", "freight_rate")
        }

    for row in deal_rows:
        shipment_id = row["shipment_id"]
        row["file_progress"] = stage_progress(
            items_by_deal.get(row["id"], []) + items_by_shipment.get(shipment_id, []),
            shipment=shipments.get(shipment_id),
        )

    for row in shipment_rows:
        row["file_progress"] = stage_progress(
            items_by_shipment.get(row["id"], []), shipment=shipments.get(row["id"]),
        )

    return summary
