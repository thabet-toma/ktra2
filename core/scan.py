"""T-SCAN: «ما الذي في يدي؟» — حلّالٌ واحد لكل ما يُمسح أو يُكتب في حقل واحد.

لماذا نقطة واحدة لا بحثٌ في كل شاشة: قبل هذا الملف كان في المنصّة أربعة أسطح
بحث منفصلة (الأصناف · الوحدات المُرقَّمة · الأجهزة الحسّاسة · استقبال الصيانة)،
وكلٌّ يسأل المستخدم أن **يعرف نوع ما في يده قبل أن يبحث عنه** — وهو عكس ما يفعله
الموظف على الطاولة: الزبون يناوله علبةً، فيمسح الملصق ولا يدري أهو باركود صنفٍ
أم رقم وحدةٍ بعناها أم IMEI جهازٍ سجّلناه له. مرجع «الأصيل» يحسم هذا بالسابقة:
القراءة تقع في **النافذة الرئيسية** ويوجّه النظام بحسب ما قُرئ، و«ترتيب البحث»
قرارٌ معلن لا ضمني (`docs/aseel_reference/full/الجديد في الاصيل.txt`).

**الشكل يُرتّب ولا يُصفّي.** `guess_kind` يقرأ بنية النصّ (IMEI بـLuhn، باركود
بخانة تحقّق EAN-13) ليعطي الواجهة لافتةً ونيّةَ ترتيب — ولا يُقصر البحث على ذلك
النوع أبداً. الفرق ليس تجميلياً: رقم تسلسلي في متجر هواتف **هو** الـIMEI غالباً،
وباركود داخلي قد يجتاز خانة تحقّق EAN بالمصادفة. حلّالٌ يصفّي بالشكل كان سيُخفي
المطابقة الصحيحة ويقول «غير مسجَّل» عن وحدةٍ في المخزن — وهو أسوأ من لا شيء.

**كل مصدرٍ بصلاحيته.** السجل الذي يربط رقم جهازٍ باسم زبونٍ وهاتفه بيانٌ حسّاس:
الوحدات والأصناف بـ`inventory.item.view`، والأجهزة الحسّاسة بترخيص وحدتها
وصلاحيتها، والكفالة وأوامر الصيانة بترخيص `after_sales` وصلاحيتيهما. من لا يملك
أيّاً منها لا يفتح الحقل أصلاً (403)، ومن يملك بعضها يرى ما يحقّ له وحده — ولا
يُقال له إن هناك ما لا يراه.

هذا الملف يسكن في `core` لأنه الطبقة الوحيدة المسموح لها بمعرفة كل الوحدات:
`inventory` ممنوع من استيراد `sales`/`logistics` (`.importlinter`)، و`after_sales`
يستورد `inventory` فعكسُه دورة. كل استيراداته كسولة داخل الدوال كنمط المستودع.
"""
from __future__ import annotations

import logging

from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from core.tenant_utils import get_tenant

logger = logging.getLogger("core.scan")

PERM_INVENTORY = "inventory.item.view"
PERM_DEVICES = "devices.registry.view"
PERM_WARRANTY = "aftersales.warranty.view"
PERM_ORDERS = "aftersales.order.view"

#: سقف المطابقات الجزئية — الحقل مساعدٌ على التعرّف لا شاشة بحثٍ كاملة. من
#: يريد قائمةً يفتح شاشة الأصناف، وزرّ «اعرض كل النتائج» يقوده إليها.
FUZZY_LIMIT = 8

#: سقف المطابقات التامّة لكل مصدر. `unique_together` هو (شركة، صنف، رقم) فقد
#: يحمل صنفان الرقم نفسه مشروعاً — نعرضهما ويختار المستخدم، ولا نخمّن.
EXACT_LIMIT = 5


# ══════════════════════════════════════════════════════════════════════════
# استنتاج الشكل — لافتةٌ للواجهة، لا مصفاةٌ للبحث
# ══════════════════════════════════════════════════════════════════════════

def guess_kind(term: str) -> str:
    """`imei` أو `barcode` أو `text` — بإعادة استعمال القاعدتين القائمتين.

    لا نسخة ثالثة من Luhn ولا من خانة تحقّق EAN: `device_registry.models`
    و`inventory.serials` يملكانهما ومُختبَرتان، ونسخةٌ ثانية من قاعدةٍ هي خطأ
    مستقبليّ ينتظر أن يتباعد طرفاه.
    """
    from device_registry.models import imei_is_valid
    from inventory.serials import is_valid_ean13

    term = (term or "").strip()
    if not term:
        return "text"
    if imei_is_valid(term):
        return "imei"
    if is_valid_ean13(term):
        return "barcode"
    return "text"


# ══════════════════════════════════════════════════════════════════════════
# الصلاحيات — ما الذي يحقّ لهذا المستخدم أن يراه
# ══════════════════════════════════════════════════════════════════════════

def scan_scope(user, tenant) -> dict:
    """مصادر هذا المستخدم — الترخيص أولاً ثم الصلاحية، كنمط بقية المنصّة."""
    from core.access import user_has_perm
    from core.modules import module_enabled

    inventory = user_has_perm(user, tenant, PERM_INVENTORY)
    devices = (
        module_enabled(tenant, "sensitive_devices")
        and user_has_perm(user, tenant, PERM_DEVICES)
    )
    after_sales = module_enabled(tenant, "after_sales")
    return {
        # الوحدة المُرقَّمة جزءٌ من الصنف لا كيانٌ مستقل — صلاحيتها صلاحيته.
        "units": inventory,
        "products": inventory,
        "devices": devices,
        "warranty": after_sales and user_has_perm(user, tenant, PERM_WARRANTY),
        "orders": after_sales and user_has_perm(user, tenant, PERM_ORDERS),
    }


# ══════════════════════════════════════════════════════════════════════════
# بطاقة القطعة — «من أين جاءت، بكم، لمن ذهبت، وما يغطّيها»
# ══════════════════════════════════════════════════════════════════════════

def _unit_card(unit, row: dict, *, warranty, orders) -> dict:
    """صفّ `_serial_row` مُثرًى بما ينقصه: الكفالة والصيانات وتكلفة الشراء.

    البناء على `inventory.serials._serial_row` لا نسخُه: هو المصدر الذي تقرأه
    بطاقة الصنف وشاشة الوحدات، فأي تعديل عليه يصل هنا مجّاناً — والعكس، لو
    كتبنا استعلامنا لانحرف الجداران بعد أول حقلٍ يُضاف هناك.

    ويستقبل كائن الوحدة نفسه لا معرّفه: `_serial_queryset` جلب `purchase_item`
    و`invoice` بـ`select_related` أصلاً، فإعادة الاستعلام عنهما هنا كانت ستكون
    استعلاماً لكل وحدة مقابل بيانٍ في اليد.
    """
    card = dict(row)

    # «بكم جاءت» — سؤال المالك الأول في مطالبة الكفالة أو المقايضة، وليس في
    # `_serial_row` لأن ذاك يخدم شاشاتٍ لا تعرض المال.
    #
    # واسمُه **سعر الشراء** لا «التكلفة» عمداً: هذا ما كُتب على بند الفاتورة،
    # وتكلفةُ الوحدة المستوردة تُبنى فوقه بمصاريف الشحن والتخليص
    # (`logistics/landed_cost.py`) ولا تُنسب إلى وحدةٍ بعينها أصلاً تحت المتوسط
    # المرجّح. تسميته «تكلفة» كانت ستجعل الموظف يسعّر مقايضةً برقمٍ ناقص.
    card["purchase_unit_price"] = None
    card["purchase_date"] = None
    item = unit.purchase_item if unit.purchase_item_id else None
    if item is not None:
        card["purchase_unit_price"] = str(item.unit_price or 0)
        invoice = item.invoice if item.invoice_id else None
        card["purchase_date"] = (
            invoice.invoice_date.isoformat()
            if invoice and invoice.invoice_date else None
        )

    card["warranty"] = warranty
    card["service_orders"] = list(orders)
    return card


def _warranty_for(tenant_id: int, term: str, scope: dict) -> dict | None:
    """التغطية بالرقم — مرّةً واحدة لا مرّةً لكل وحدة.

    كل الوحدات المطابقة تحمل **الرقم نفسه** (به طابقت)، فالتغطية والصيانات
    واحدة لها جميعاً. حسابُها داخل حلقة الوحدات كان N+1 على أسخن مسار في
    المنصّة — وأمسكه `ScanQueryCountTest` بفارق 19 ← 25.
    """
    if not (scope["warranty"] and term):
        return None
    from after_sales.services import warranty_coverage

    coverage = warranty_coverage(tenant_id, term)
    # `unit` داخل التغطية يكرّر ما في البطاقة أصلاً — نُسقطه كي لا يحمل الردّ
    # رقمَي «العميل» من مصدرين قد يتباعدان على الشاشة.
    return {
        "covered": coverage["covered"],
        "supplier_covered": coverage.get("supplier_covered", False),
        "cards": coverage["cards"],
    }


def _service_orders_for(tenant_id: int, term: str, scope: dict) -> list[dict]:
    """سجلّ الصيانات — **إضافةٌ فوق المقترح**.

    كل مراجع متاجر الهواتف تجعله جوهرَ المسح لا ملحقاً به («a simple IMEI scan
    should pull up the entire ticket history»)، والبيانات هنا أصلاً:
    `ServiceOrder.serial` مفهرس بـ`(tenant, serial)`.
    """
    if not (scope["orders"] and term):
        return []
    from after_sales.models import ServiceOrder

    return [
        {
            "id": order.pk,
            "order_number": order.order_number,
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "status": order.status,
            "status_display": order.get_status_display(),
            "complaint": (order.complaint or "")[:200],
        }
        for order in ServiceOrder.objects
        .filter(tenant_id=tenant_id, serial=term)
        .order_by("-order_date", "-id")[:EXACT_LIMIT]
    ]


def _units(tenant_id: int, term: str, scope: dict) -> list[dict]:
    """الوحدات المطابقة تماماً — التطابق التامّ وحده: رقم الوحدة هويّة لا وصف."""
    if not scope["units"] or not term:
        return []
    from inventory.serials import _serial_queryset, _serial_row

    units = list(
        _serial_queryset(tenant_id).filter(serial=term).order_by("-id")[:EXACT_LIMIT]
    )
    if not units:
        return []
    warranty = _warranty_for(tenant_id, term, scope)
    orders = _service_orders_for(tenant_id, term, scope)
    return [
        _unit_card(unit, _serial_row(unit), warranty=warranty, orders=orders)
        for unit in units
    ]


def _devices(tenant_id: int, term: str, scope: dict) -> list[dict]:
    """أجهزة الزبائن المسجَّلة — بالسيريال أو الـIMEI، وكلاهما يُطابَق تماماً."""
    if not scope["devices"] or not term:
        return []
    from device_registry.models import SensitiveDevice

    return [
        {
            "id": device.pk,
            "model_name": device.model_name,
            "serial_number": device.serial_number,
            "imei": device.imei,
            "status": device.status,
            "status_display": device.get_status_display(),
            "customer_name": device.customer_name,
            "customer_phone": device.customer_phone,
            "registered_at": (
                device.created_at.isoformat() if device.created_at else None
            ),
        }
        for device in SensitiveDevice.objects
        .filter(tenant_id=tenant_id)
        .filter(Q(serial_number=term) | Q(imei=term))
        .order_by("-created_at")[:EXACT_LIMIT]
    ]


def _product_row(product, *, matched_on: str) -> dict:
    return {
        "id": product.pk,
        "sku": product.sku or "",
        "barcode": product.barcode or "",
        "name": product.name_ar or product.name_en or "",
        "brand": product.brand or "",
        "quantity_on_hand": str(product.quantity_on_hand or 0),
        "sale_price": str(product.sale_price or 0),
        "is_serialized": bool(product.is_serialized),
        # لماذا طابق: الموظف يرى أن الرقم باركودٌ لا رمزُ صنف فيثق بالنتيجة.
        "matched_on": matched_on,
    }


def _products(tenant_id: int, term: str, scope: dict) -> list[dict]:
    """الأصناف: التطابق التامّ (باركود ثم رمز) أولاً، ثم المطابقة الجزئية.

    الترتيب مقصود ومسبوقٌ إليه — «خيار البحث عن الباركود المقروء في رقم الصنف
    ثم رقم الكتلوج» في الأصيل. التطابق التامّ يقين والجزئي ترجيح، وخلطهما في
    قائمة واحدة بلا ترتيب يجعل الموظف يقرأ سطراً مرجَّحاً على أنه يقين.
    """
    if not scope["products"] or not term:
        return []
    from inventory.models import Product

    base = Product.objects.filter(tenant_id=tenant_id)
    rows: list[dict] = []
    seen: set[int] = set()

    for field, label in (("barcode", "barcode"), ("sku", "sku")):
        for product in base.filter(**{field: term})[:EXACT_LIMIT]:
            if product.pk not in seen:
                seen.add(product.pk)
                rows.append(_product_row(product, matched_on=label))

    remaining = FUZZY_LIMIT - len(rows)
    if remaining > 0:
        fuzzy = (
            base.filter(
                Q(sku__icontains=term)
                | Q(barcode__icontains=term)
                | Q(name_ar__icontains=term)
                | Q(name_en__icontains=term)
                | Q(brand__icontains=term)
            )
            .exclude(pk__in=seen)
            .order_by("sku")[:remaining]
        )
        rows.extend(_product_row(p, matched_on="partial") for p in fuzzy)
    return rows


# ══════════════════════════════════════════════════════════════════════════
# الحلّال
# ══════════════════════════════════════════════════════════════════════════

def resolve_scan(*, tenant, user, term: str) -> dict:
    """كل ما نعرفه عن هذا الرقم، مرتّباً من الأخصّ إلى الأعمّ.

    يُرجع `matches` قائمةً واحدة موسومةً بالنوع لا خمس قوائم: المستخدم يمسح
    مرّةً ويريد جواباً واحداً، وتقسيمُ الجواب على صناديق يجعله هو مَن يجمعها.
    والوحدة المطابقة تحمل **بطاقتها كاملةً داخل الصفّ** — نداءٌ ثانٍ لفتحها كان
    سيعني وميضةً وشاشتين على فعلٍ واحد.
    """
    tenant_id = getattr(tenant, "pk", None) or getattr(tenant, "TenantID", tenant)
    term = (term or "").strip()
    scope = scan_scope(user, tenant)
    kind = guess_kind(term)

    units = _units(tenant_id, term, scope)
    devices = _devices(tenant_id, term, scope)
    products = _products(tenant_id, term, scope)

    matches: list[dict] = []
    matches.extend({"type": "unit", **row} for row in units)
    matches.extend({"type": "device", **row} for row in devices)
    matches.extend({"type": "product", **row} for row in products)

    # «غير مسجَّل» يعني: بحثنا في كل ما يحقّ لك وما وجدنا. المصطلح لا يُطلق على
    # نصٍّ فارغ — الحقل الفارغ ليس رقماً مجهولاً.
    unregistered = bool(term) and not matches

    # سجلّ بلا PII: الرقم نفسه معرّفُ جهازٍ مربوطٌ بزبون، فلا يُكتب. الشكل
    # وعدد المطابقات يكفيان لتشخيص «لماذا لم يجد المسح شيئاً؟».
    logger.info(
        "scan resolve tenant=%s kind=%s len=%d units=%d devices=%d products=%d",
        tenant_id, kind, len(term), len(units), len(devices), len(products),
    )

    return {
        "term": term,
        "kind": kind,
        "matches": matches,
        "unregistered": unregistered,
        # الواجهة ترسم أزرار «سجّله» بحسب ما يحقّ للمستخدم فعلاً — لا زرّ يقود
        # إلى 403. وهي أيضاً ما يشرح للمستخدم أن نطاق بحثه أضيق من نطاق زميله.
        "scope": scope,
    }


# ══════════════════════════════════════════════════════════════════════════
# النقطة — `GET /api/scan/?q=<term>`
# ══════════════════════════════════════════════════════════════════════════
#
# النقطة في هذا الملف لا في ملفٍ ثالث: الوحدة كلّها ثلاثُ دوالٍّ وواجهةٌ رقيقة
# فوقها، وتوزيعها على ملفين يجعل قراءة الميزة قفزاً بين اثنين بلا مقابل.

@api_view(["GET"])
def scan_lookup(request):
    """«ما الذي في يدي؟» — نقطةٌ واحدة لكل ما يُمسح أو يُكتب.

    بلا كاش عمداً — كبقية أفعال التحقّق في المنصّة: الموظف يمسح ليعرف الآن، وردٌّ
    من ستّين ثانية قد يقول «في المخزن» عن وحدةٍ بيعت للتوّ.
    """
    tenant = get_tenant(request)
    if not tenant:
        raise PermissionDenied("لا شركة نشطة لهذا المستخدم.")

    scope = scan_scope(request.user, tenant)
    # لا مصدر واحد يحقّ له؟ الحقل نفسه لا يُفتح. 403 هنا أصدق من ردٍّ فارغ
    # يقرأه المستخدم «الرقم غير مسجَّل» وهو مسجَّل ولا يراه.
    if not any(scope.values()):
        raise PermissionDenied(
            "صلاحية «عرض الأصناف والمخزون» غير ممنوحة لدورك — لا يمكن التعرّف على الأرقام."
        )

    return Response(resolve_scan(
        tenant=tenant, user=request.user, term=request.query_params.get("q") or "",
    ))
