"""رابط عدّ الجرد — جمهوره **موظف المستودع** صاحبُ اسمٍ على الرابط (K3).

**لماذا وحدة جديدة لا سطرٌ في `voucher_docs`:** هذا النوع الوحيد الذي يكتب
**كميات عدّ** على مسودّة جرد، ويرى كميات النظام بلا أيّ رقمٍ مالي (قرار المالك
ق١: يرى كمية النظام، ولا يرى التكلفة ولا السعر). وحدودُ الجمهور حدودُ ملفٍ كما
في `purchase_docs.py`: من يراجع «ماذا يرى موظف المستودع؟» يقرأ هذا الملف كاملاً.

**وما لا يخرج من هنا:** `avg_cost` و`sale_price` و`online_price` وأيّ حقلٍ
ماليّ. لا يُحمَّل من القاعدة أصلاً في `_public_lines` (`.only` صريح)، ويحرس
الغيابَ اختبارُ قائمة السماح في `inventory/tests/test_stocktake_count_link.py`.

**الكتابة ليست قراراً ولا تسعيراً:** `count` مسارٌ ثالث مستقلّ. العامّ يكتب
`counted_quantity`/`counted_by_name`/`counted_at` على أسطر نطاق الرابط فقط،
داخل `select_for_update` لصفّ الجرد (ثم أسطره)، ثم يحرّك `updated_at` للرأس
فيتقادم `ETag` عند المدير — وهذا هو عقد التزامن مع K1/K2 (اختبار 412).
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.activity import log_activity
from docshare.documents._contract import (
    AUDIENCE_WAREHOUSE,
    TONE_OK,
    TONE_WARN,
    VALUE_DATE,
    company_card,
    meta,
    payload,
)
from docshare.models import DocumentShare
from inventory.models import (
    ProductCategory, Stocktake, StocktakeCountLink, StocktakeLine,
)
from inventory.services import (
    stocktake_count_scope_category_ids,
    stocktake_line_in_count_scope,
)

#: أعمدة الرأس التي يكفي تحميلها للصفحة العامة — لا مبالغ ولا قيود.
_STOCKTAKE_COLUMNS = (
    "id", "tenant_id", "stocktake_number", "stocktake_date", "is_posted", "notes",
)


def load_stocktake_count(tenant_id: int, doc_id: int):
    """يحمل الجرد لرابط العدّ — **بلا فلترة `is_posted`**.

    الفلترة هنا كانت ستجعل الرابط المنتهي يردّ 404 بدل 410: الرابط كان حيّاً
    يوماً، والصفحة يجب أن تقول «انتهى» لا أن تصمت. الحارس في القراءة/الكتابة.
    """
    return (
        Stocktake.objects
        .select_related("warehouse")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(*_STOCKTAKE_COLUMNS, "warehouse__name")
        .first()
    )


def build_stocktake_count(stocktake) -> dict:
    """صفحة `/s/<token>` العامة لهذا النوع: رأسٌ بلا بنودٍ ولا أرقام مالية.

    الصفحة المقصودة للعدّ هي `/api/share/<token>/count/` (JSON) التي تبنيها
    K4؛ وهذه ورقةٌ احتياطية لمن يفتح التوكن في المسار العام: تقول ما هو الجرد
    ومتى، ولا تعرض شيئاً يُكتب عليه.
    """
    return payload(
        kind="stocktake_count",
        title="جرد مستودع",
        number=stocktake.stocktake_number or "",
        date=stocktake.stocktake_date,
        status_label="مُرحَّل" if stocktake.is_posted else "مسودة",
        status_tone=TONE_OK if stocktake.is_posted else TONE_WARN,
        party_title="",
        party=None,
        currency=None,
        meta_rows=[
            meta("التاريخ", stocktake.stocktake_date, VALUE_DATE),
            meta("المستودع", stocktake.warehouse.name if stocktake.warehouse_id else ""),
        ],
        lines=[],
        show_lines=False,
        show_line_prices=False,
        totals_rows=[],
        grand_total=Decimal(0),
        notes=stocktake.notes,
    )


# ── القراءة العامة ──────────────────────────────────────────────────────────

def _decimal_text(value) -> str:
    """كميةٌ كنصٍّ بأربع منازل — لا `float` يضيّع الدقّة ولا فاصلةَ تعريب."""
    return format(Decimal(value).quantize(Decimal("0.0001")), "f")


def _category_path_resolver(tenant_id: int):
    """مسار التصنيف الكامل من خريطةٍ واحدة — لا استعلاماً لكل مستوى.

    الجرد قد يحمل مئات الأسطر، و`line.product.category.parent.parent…` حلقةُ
    استعلامات. نخريط تصنيفات الشركة مرّةً (معرّف ← اسم/أب) ونبني المسار في
    بايثون، بحارس حلقةٍ لبياناتٍ قديمة معطوبة.
    """
    rows = (
        ProductCategory.objects
        .filter(tenant_id=tenant_id)
        .values_list("id", "name", "parent_id")
    )
    by_id = {pk: (name or "", parent_id) for pk, name, parent_id in rows}
    cache: dict[int, str] = {}

    def path(category_id):
        if not category_id:
            return ""
        if category_id in cache:
            return cache[category_id]
        parts: list[str] = []
        seen: set[int] = set()
        current = category_id
        while current and current not in seen:
            seen.add(current)
            name, parent = by_id.get(current, ("", None))
            if name:
                parts.append(name)
            current = parent
        value = " / ".join(reversed(parts))
        cache[category_id] = value
        return value

    return path


def _public_lines(stocktake, category_ids) -> list[dict]:
    """أسطر نطاق الرابط وحدها — بأعمدةٍ صريحة لا تحمل رقماً مالياً واحداً.

    `system_quantity` = **رصيد الشركة الحالي** لصفّ المنتج وقت القراءة
    (`quantity_on_hand`)، لا رصيد المستودع: المستودع على الجرد وسمٌ للحركات
    والرصيد في هذا النظام على مستوى الشركة (انظر `Stocktake.warehouse`).
    """
    rows = (
        StocktakeLine.objects
        .filter(stocktake=stocktake)
        .select_related("product", "product__uom")
        .only(
            "id", "counted_quantity", "counted_by_name",
            "product__sku", "product__name_ar", "product__name_en",
            "product__brand", "product__category_id", "product__quantity_on_hand",
            "product__uom__name_ar", "product__uom_legacy",
        )
        .order_by("id")
    )
    category_path = _category_path_resolver(stocktake.tenant_id)
    lines = []
    for line in rows:
        if not stocktake_line_in_count_scope(line, category_ids):
            continue
        product = line.product
        lines.append({
            "line_id": line.id,
            "sku": product.sku or "",
            "name": product.name_ar or product.name_en or product.sku or "",
            "brand": product.brand or "",
            "category_path": category_path(product.category_id),
            "uom": (
                product.uom.name_ar if product.uom_id
                else (product.uom_legacy or "")
            ),
            "system_quantity": _decimal_text(product.quantity_on_hand),
            "counted_quantity": (
                None if line.counted_quantity is None
                else _decimal_text(line.counted_quantity)
            ),
            "counted_by_name": line.counted_by_name or "",
        })
    return lines


def _services():
    """استيرادٌ كسول: `docshare.services` يستورد `documents` في أعلى ملفه."""
    from docshare import services

    return services


def read_stocktake_count(share, stocktake) -> dict:
    """حمولة `GET /api/share/<token>/count/` — قائمةُ سماحٍ ثابتة."""
    services = _services()
    if stocktake.is_posted:
        raise services.ShareGone(f"{share.doc_type}: posted")
    link = (
        StocktakeCountLink.objects
        .filter(
            share_id=share.pk, tenant_id=share.tenant_id, stocktake_id=stocktake.pk,
        )
        .first()
    )
    if link is None:
        # توكنٌ لنوعٍ آخر أو رابطٌ بلا صفّ عدّ: نفس صمت «غير موجود» أمام من يخمّن.
        raise services.ShareNotFound(share.token)
    category_ids = stocktake_count_scope_category_ids(link.categories)
    company = company_card(share.tenant)
    return {
        "company_name": company["company_name_primary"],
        "stocktake_number": stocktake.stocktake_number or "",
        "date": stocktake.stocktake_date.isoformat(),
        "warehouse": stocktake.warehouse.name if stocktake.warehouse_id else "",
        "counter_name": link.counter_name,
        "finished": link.finished_at is not None,
        "lines": _public_lines(stocktake, category_ids),
    }


# ── الكتابة العامة ──────────────────────────────────────────────────────────

def write_stocktake_count(share, entries, finished: bool, request) -> dict:
    """يكتب كميات العدّ على أسطر نطاق الرابط — وحدها، وعلى جردٍ غير مُرحَّل.

    `entries` قائمة `(line_id, Decimal|None)` **مُتحقَّقٌ منها** في العرض.
    الترتيب داخل المعاملة: قفل صفّ الجرد أولاً ثم المشاركة ثم الأسطر — نفس
    ترتيب `post_stocktake` (جرد ← روابط)، فلا يدخل ترحيلٌ وكتابةُ عدٍّ في
    حلقة انتظارٍ متبادلة.
    """
    services = _services()
    now = timezone.now()

    with transaction.atomic():
        locked = (
            Stocktake.objects.select_for_update()
            .filter(pk=share.doc_id, tenant_id=share.tenant_id)
            .first()
        )
        if locked is None:
            raise services.ShareNotFound(f"{share.doc_type}#{share.doc_id}")
        if locked.is_posted:
            raise services.ShareGone(f"{share.doc_type}: posted")

        # إعادة جلب المشاركة تحت القفل: إبطالٌ متزامن (أو انتهاء) بين الحلّ
        # والكتابة يجب أن يردّ 410 لا أن يكتب على رابطٍ ميّت.
        locked_share = (
            DocumentShare.objects.select_for_update().filter(pk=share.pk).first()
        )
        if locked_share is None or not locked_share.is_live:
            raise services.ShareGone(share.token)

        link = (
            StocktakeCountLink.objects
            .filter(
                share_id=locked_share.pk, tenant_id=share.tenant_id,
                stocktake_id=locked.pk,
            )
            .first()
        )
        if link is None:
            raise services.ShareNotFound(share.token)

        category_ids = stocktake_count_scope_category_ids(link.categories)
        # التكرار في الطلب: آخر قيمةٍ هي المقصودة (النموذج قد يرسل السطر مرّتين).
        latest = {}
        for line_id, quantity in entries:
            latest[line_id] = quantity

        lines = {
            line.pk: line
            for line in (
                locked.lines.select_for_update()
                .select_related("product")
                .filter(pk__in=latest.keys())
                .only("id", "counted_quantity", "counted_by_name", "counted_at",
                      "product__category_id")
                .order_by("pk")
            )
        }

        written = 0
        ignored = 0
        changed = []
        for line_id, quantity in latest.items():
            line = lines.get(line_id)
            if line is None or not stocktake_line_in_count_scope(line, category_ids):
                # سطرُ جردٍ آخر أو خارج نطاق الرابط: يُتجاهل ويُعدّ، لا خطأ —
                # رسالةُ خطأٍ هنا تخبر الشركة الأخرى أن معرّفها موجود.
                ignored += 1
                continue
            line.set_count(quantity, link.counter_name, now)
            changed.append(line)
            written += 1

        if changed:
            StocktakeLine.objects.bulk_update(
                changed,
                ["counted_quantity", "counted_by_name", "counted_at"],
                batch_size=200,
            )
            # **عقد التزامن**: تحريكُ ختم الرأس يجعل ETag المدير قديماً، فيُردّ
            # حفظُه القديم 412 ويُطبِّق K2 تحديثه بدل محو عدّ الموظف.
            locked.save(update_fields=["updated_at"])

        just_finished = bool(finished and link.finished_at is None)
        if just_finished:
            link.finished_at = now
            link.save(update_fields=["finished_at"])

        if written or just_finished:
            # آخر نشاطٍ على الرابط بنفس حقول `submit_quote` (اسم/وقت/IP) —
            # فشاشة المدير تعرف مَن كتب ومتى بلا جدولٍ جديد.
            locked_share.decided_name = link.counter_name
            locked_share.decided_ip = services.client_ip(request)
            locked_share.decided_at = now
            locked_share.save(
                update_fields=["decided_name", "decided_ip", "decided_at"])

            # `action` محصورٌ بـchoices النموذج؛ التفصيل في `metadata`.
            log_activity(
                action="update",
                entity_type="stocktake",
                entity_id=locked.pk,
                entity_label=locked.stocktake_number or f"جرد #{locked.pk}",
                description=(
                    f"عدّ من رابط عام — {link.counter_name} "
                    f"({written} سطر)"
                ),
                metadata={
                    "source": "public_count_link",
                    "share_id": locked_share.pk,
                    "counter_name": link.counter_name,
                    "written": written,
                    "ignored": ignored,
                    "finished": link.finished_at is not None,
                    "ip": locked_share.decided_ip,
                },
                request=request,
                tenant=share.tenant,
                user=None,
            )

    return {
        "written": written,
        "ignored": ignored,
        "finished": link.finished_at is not None,
    }


#: مواصفة النوع في `docshare.documents.DOC_TYPES`. مفتاح `count` **اختياريّ**
#: في السجلّ (اختبار السجلّ يطلب الأساسيات لا هذا)، وهو وحده ما تعرفه نقطتا
#: العدّ العامّتان؛ نوعٌ لا يعرّفه لا يكسب سطح عدّ.
STOCKTAKE_COUNT_SPEC = {
    "label": "رابط عدّ جرد",
    "loader": load_stocktake_count,
    "builder": build_stocktake_count,
    #: صلاحية سطر المشاركة في قائمة `/api/document-shares/`: **إدارة الأصناف**
    #: لا قراءتها، لأن الصفّ يحمل توكناً حيّاً يكتب على الجرد — و`inventory.item.view`
    #: يملكها «مستعرض» أيضاً، فيقرأ التوكن ويكتب من الرابط العامّ متجاوزاً دوره.
    #: **إنشاءُ** الرابط نفسه يمرّ من `StocktakeViewSet` بصلاحية تعديل الجرد
    #: (PATCH) لا من هذا المفتاح.
    "permission": "inventory.item.manage",
    "audience": AUDIENCE_WAREHOUSE,
    "decision": None,
    "count": {
        "read": read_stocktake_count,
        "write": write_stocktake_count,
    },
}

STOCKTAKE_DOC_TYPES = {"stocktake_count": STOCKTAKE_COUNT_SPEC}
