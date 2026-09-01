"""T-REPORTS: محرّك تقارير المنصة — سجل واحد لكل تقرير.

لماذا سجلّ لا صفحة لكل تقرير: التقارير كانت متناثرة (ميزان مراجعة وقائمة دخل
وأعمار ديون…) كلٌّ بشاشته ونقطته، فكل تقرير جديد يعني صفحة كاملة. هنا يُعلن
التقرير مرّةً واحدة — عنوانه وفلاتره وأعمدته ودالّة بنائه — وتُنفَّذه نقطتان
اثنتان (`/api/reports/` للفهرس و`/api/reports/<key>/` للتشغيل)، وتعرضه شاشة
واحدة عامّة. إضافة تقرير لاحقاً = دالّة واحدة في هذا الملف.

كل بانٍ يستقبل `(tenant_id, params)` ويُعيد `list[dict]` بمفاتيح أعمدة التقرير.
المبالغ نصوص (`str(Decimal)`) كبقية المشروع — لا عوائم في المال.
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from django.db.models import Case, DecimalField, F, Max, Q, Sum, Value, When
from django.db.models.functions import Coalesce

logger = logging.getLogger("core.reports")

from ._framework import (
    DEC,
    ZERO,
    CATEGORIES,
    KIND_MONEY,
    KIND_NUMBER,
    KIND_INT,
    KIND_DATE,
    KIND_TEXT,
    ReportColumn,
    ReportFilter,
    ReportSpec,
    REPORTS,
    register,
    DATE_FILTERS,
    _parse_date,
    _date_range,
    _apply_dates,
    _int_param,
    _money,
    _qty,
    _sum,
    _money_sum,
    compute_totals,
    report_catalog,
    MAX_ROWS,
    run_report,
)

def _products(tenant_id: int, params: dict):
    from inventory.models import Product

    qs = Product.objects.filter(tenant_id=tenant_id).select_related("category", "family")
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(pk=product)
    return qs


def _stock_valuation(tenant_id: int, params: dict, *, group: str = "product") -> list[dict]:
    """مجمَّعة على المنتج افتراضاً — صفٌّ واحد لكل عائلة، بمتوسط تكلفة **مرجَّح
    بالكمية** (Σqty×cost ÷ Σqty) لا متوسط برانداتها البسيط (#26): براندٌ بقطعتين
    بسعرٍ شاذّ لا يجوز أن يسحب متوسط المنتج معه — وزنُه في المتوسط كميّته لا
    عدده. منتجٌ بلا أبٍ (`family_id` فارغ) يبقى صفّاً بمفرده كسابق عهده.

    `group="product_brand"` (التنقيب) لا يجمع شيئاً — صفٌّ لكل براند كما كان
    التقرير قبل #26، مقصوراً على العائلة/المنتج الذي فُتح.

    #26-دلتا: فلتر `product` (`?product=`) يختار **براندًا بعينه** — قاعدةٌ
    صارمة: صفّ العائلة أرقامه مجموع كل أبنائها أو لا يظهر أصلاً. فحين يضيق
    الفلتر النتيجة لبراندٍ واحد، لا يُعرض صفّ عائلةٍ منقوصٍ متنكّراً بأنه
    المجموع (فراغ `sku`/`brand` كان يُخفي أن الرقم لبراندٍ واحد لا للمنتج) —
    يُعرض صفّ براندٍ حقيقي: `sku`/`brand` كما هما.
    """
    from inventory.services import family_display_name

    qs = _products(tenant_id, params)
    brand_selected = group == "product" and _int_param(params, "product") is not None
    if group == "product_brand":
        family_id = _int_param(params, "family_id")
        product_id = _int_param(params, "product_id")
        if family_id:
            qs = qs.filter(family_id=family_id)
        elif product_id:
            qs = qs.filter(pk=product_id)

    buckets: dict = {}
    for p in qs.order_by("sku"):
        family_id = p.family_id if (group == "product" and not brand_selected) else None
        if family_id:
            family = p.family
            name = family_display_name(family, family_id)
            key = f"family:{family_id}"
            label = {"sku": "", "brand": "", "name": name, "family_id": family_id, "product_id": ""}
        else:
            key = f"product:{p.id}"
            label = {
                "sku": p.sku or "", "brand": p.brand or "",
                "name": p.name_ar or p.name_en or "", "family_id": "", "product_id": p.id,
            }
        bucket = buckets.setdefault(key, {
            **label, "category": p.category.name if p.category_id else "",
            "quantity": ZERO, "value": ZERO,
        })
        qty = Decimal(str(p.quantity_on_hand or 0))
        cost = Decimal(str(p.avg_cost or 0))
        bucket["quantity"] += qty
        bucket["value"] += qty * cost

    rows = []
    for bucket in buckets.values():
        qty = bucket["quantity"]
        rows.append({
            "sku": bucket["sku"], "name": bucket["name"], "brand": bucket["brand"],
            "category": bucket["category"], "family_id": bucket["family_id"],
            "product_id": bucket["product_id"],
            "quantity": _qty(qty),
            "avg_cost": _money(bucket["value"] / qty if qty else ZERO),
            "value": _money(bucket["value"]),
        })
    rows.sort(key=lambda r: (r["sku"] or r["name"]))
    return rows


_STOCK_VALUATION_COLUMNS = (
    ReportColumn("sku", "الرمز", width="120px"),
    ReportColumn("name", "المنتج"),
    ReportColumn("brand", "الماركة", width="120px"),
    ReportColumn("category", "الفئة", width="130px"),
    ReportColumn("quantity", "الرصيد", KIND_NUMBER, total=True, width="100px"),
    ReportColumn("avg_cost", "متوسط التكلفة", KIND_MONEY, width="120px"),
    ReportColumn("value", "القيمة", KIND_MONEY, total=True),
)

register(ReportSpec(
    key="stock-valuation",
    title="تقييم المخزون",
    category="inventory",
    description=(
        "رصيد كل منتج وقيمته بمتوسط التكلفة — قيمة البضاعة على الرفّ. صفٌّ "
        "واحد لكل منتج (متوسط تكلفته مرجَّحٌ بكمية برانداته)، وينقّب إلى تفصيلها."
    ),
    filters=(ReportFilter("product", "المنتج", "product"),),
    columns=_STOCK_VALUATION_COLUMNS,
    permission="inventory.item.view",
    build=lambda t, p: _stock_valuation(t, p, group="product"),
    drill=lambda t, p: _stock_valuation(t, p, group="product_brand"),
    drill_keys=("family_id", "product_id"),
    drill_title="برندات هذا المنتج",
    drill_columns=_STOCK_VALUATION_COLUMNS,
))


def _reorder_rows(tenant_id: int, params: dict, *, level: str = "item") -> list[dict]:
    """جسر واحد بين محرّك التجديد وتقارير المخزون — لا نسخةَ منطقٍ ثانية هنا."""
    from core.replenishment import replenishment_rows

    product = _int_param(params, "product")
    return replenishment_rows(
        tenant_id,
        product_ids=[product] if product else None,
        supplier_id=_int_param(params, "partner"),
        urgency=(params.get("urgency") or None),
        level=level,
    )


def _rate(value) -> str:
    """معدّل صرفٍ يوميّ بمنزلتين — رقمٌ يُقرأ لا كسرٌ بعشرين خانة."""
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


#: أشدّ أوّلاً — يحدّد أيّ عضوٍ مؤهَّلٍ يمثّل حكم صفّ العائلة (الأسوأ يفوز).
_LOW_STOCK_SEVERITY = {"out_of_stock": 0, "low_stock": 1}


def _low_stock_brand_row(r: dict) -> dict:
    """صفّ برندٍ فردي بأرقامه هو — بلا تجميع، وبلا تنكّرٍ باسم عائلته.

    نفس الشكل الذي كان عليه التقرير قبل #26 حرفياً: يُستعمل للتنقيب (كل
    برانداته)، ولمنتجٍ بلا أبٍ، ولفلتر `product` (#26-دلتا): فلترٌ يختار
    براندًا بعينه لا يجوز أن يُعاد كصفّ عائلةٍ منقوصٍ — إن طُلب براندٌ، فبراندٌ
    حقيقيٌّ يُعاد: `sku`/`brand` كما هما، ورقمه هو رقمه لا رقم عائلته.
    """
    from inventory.stock_status import STATUS_LABELS

    minimum = Decimal(str(r["effective_min"]))
    available = Decimal(str(r["available"]))
    return {
        "sku": r["sku"], "name": r["name"],
        "family_id": "", "product_id": r["product_id"],
        "status": STATUS_LABELS[r["status"]],
        "quantity": _qty(available),
        "min_stock_level": _qty(minimum),
        "min_source": "يدوي" if r["manual_min"] else ("محسوب" if minimum > ZERO else "—"),
        "shortage": _qty(max(minimum - available, ZERO)),
        "group_available": _qty(r["group_available"]),
        "newest_alternative": r["newest_alternative"],
        "urgency": r["urgency_label"],
    }


def _low_stock(tenant_id: int, params: dict, *, group: str = "product") -> list[dict]:
    """ما نفد وما اقترب من النفاد معاً — بحالةٍ مكتوبة على كل سطر.

    كان هذا التقرير يشترط `min_stock_level > 0` قبل أن يرى المنتج، والحدّ اليدوي
    فارغٌ في معظم الكتالوج — فكان يصمت عن أغلب ما نفد فعلاً. صار يقرأ الحدّ
    **الفعّال** (`inventory/stock_status.py`): اليدوي إن ضُبط، وإلّا المقترَح
    المحسوب من المبيعات. و«نفذ» لا يشترط حدّاً أصلاً.

    #26: مجمَّعة على المنتج افتراضاً — صفّ العائلة يظهر إن كان لأيٍّ من أبنائها
    حالة نفدٍ/انخفاض. منتجٌ بلا أبٍ يبقى صفّاً بمفرده كسابق عهده.

    #26-دلتا — **قاعدة صارمة: صفّ العائلة أرقامه مجموع كل أبنائها، أو لا يظهر
    أصلاً**. عيبان كانا يخالفانها:

    1. كان يُبنى بتصفية الحالة (نفد/منخفض) **قبل** التجميع، فتغيب عنه إخوةٌ
       متوفّرون — والمتاح المعروض كان مجموع مَن **بقي بعد التصفية** لا مجموع
       العائلة الحقيقي الذي قِيس عليه الحكم نفسه (`stock_status_of` تقارن
       `family_totals[family_id]` — مجموع **كل** الإخوة — بحدّ الأب). الحلّ: لا
       تصفية حالةٍ قبل التجميع؛ يظهر صفّ العائلة إن تأهّل **أيّ** عضوٍ، وأرقامه
       `family_available` المحسوبة أصلاً لكل صفّ (`core/replenishment.py`) —
       لا حسابٌ ثانٍ قد ينحرف عن الحكم الفعلي. وللسبب نفسه يسرد التنقيب **كل**
       الإخوة لا المتأهِّلين وحدهم — وإلا لم يطابق مجموعه رقم الصفّ.
    2. فلتر `product` (`?product=`) يختار **براندًا بعينه** — لا حقيقةً عن كل
       الإخوة. حين يضيق التقرير لفرعٍ واحدٍ من عائلة، لا يجوز أن يُعرض صفٌّ
       باسم العائلة يحمل رقم ذلك الفرع وحده متنكّراً بأنه المجموع؛ يُعرض صفّ
       براندٍ حقيقي بدلاً منه.

    `group="product_brand"` (التنقيب) لا يجمع شيئاً ولا يصفّي حالةً — كل
    براندات العائلة، بأرقامها هي.
    """
    from inventory.stock_status import STATUS_LABELS, STATUS_LOW, STATUS_OUT_OF_STOCK

    qualifying_statuses = (STATUS_OUT_OF_STOCK, STATUS_LOW)
    all_rows = _reorder_rows(tenant_id, params)

    if group == "product_brand":
        family_id = _int_param(params, "family_id")
        product_id = _int_param(params, "product_id")
        if family_id:
            all_rows = [r for r in all_rows if r["family_id"] == family_id]
        elif product_id:
            all_rows = [r for r in all_rows if r["product_id"] == product_id]
        return [_low_stock_brand_row(r) for r in all_rows]

    # فلترٌ يختار براندًا بعينه (#26-دلتا، عيب 2): صفوفٌ حقيقية لا عائلة منقوصة.
    if _int_param(params, "product"):
        return [
            _low_stock_brand_row(r) for r in all_rows if r["status"] in qualifying_statuses
        ]

    # المجمَّع الافتراضي (#26-دلتا، عيب 1): التجميع **قبل** تصفية الحالة.
    groups: dict = {}
    for r in all_rows:
        key = f"family:{r['family_id']}" if r["family_id"] else f"product:{r['product_id']}"
        groups.setdefault(key, []).append(r)

    rows = []
    for members in groups.values():
        qualifying = [m for m in members if m["status"] in qualifying_statuses]
        if not qualifying:
            continue
        if not members[0]["family_id"]:
            rows.append(_low_stock_brand_row(qualifying[0]))
            continue

        # حكم صفّ العائلة = أشدّ عضوٍ مؤهَّل — نفس المتاح لكل الإخوة
        # (`family_available` واحدٌ للعائلة)، والحدّ يختلف حين لا حدّ يدويّ على
        # الأب (كلٌّ يسقط على مقترَحه الخاص، عيبٌ سابقٌ لـ#25 لا يُصحَّح هنا) —
        # فيُختار حدّ **أشدّ** حكمٍ فعلاً حدث، لا أوّل عضوٍ صودف.
        verdict = min(qualifying, key=lambda m: _LOW_STOCK_SEVERITY[m["status"]])
        available = Decimal(str(verdict["family_available"]))
        minimum = Decimal(str(verdict["effective_min"]))
        rows.append({
            "sku": "", "name": verdict["family_name"] or verdict["name"],
            "family_id": verdict["family_id"], "product_id": "",
            "status": STATUS_LABELS[verdict["status"]],
            "quantity": _qty(available),
            "min_stock_level": _qty(minimum),
            "min_source": "يدوي" if verdict["manual_min"] else ("محسوب" if minimum > ZERO else "—"),
            "shortage": _qty(max(minimum - available, ZERO)),
            "group_available": _qty(verdict["group_available"]),
            # صفّ العائلة يمثّل كل بدائلها فعلاً — «بديلٌ» يبقى معنىً لسطر
            # البراند وحده حين لا يُجمَّع.
            "newest_alternative": "",
            "urgency": verdict["urgency_label"],
        })
    return rows


_LOW_STOCK_COLUMNS = (
    ReportColumn("sku", "الرمز", width="120px"),
    ReportColumn("name", "المنتج"),
    ReportColumn("status", "الحالة", width="80px"),
    ReportColumn("quantity", "المتاح", KIND_NUMBER, total=True, width="90px"),
    ReportColumn("min_stock_level", "الحد الأدنى", KIND_NUMBER, width="100px"),
    ReportColumn("min_source", "مصدر الحد", width="90px"),
    ReportColumn("shortage", "النقص", KIND_NUMBER, total=True, width="90px"),
    ReportColumn("group_available", "رصيد الصنف", KIND_NUMBER, width="100px"),
    ReportColumn("newest_alternative", "أحدث بديل متوفّر"),
    ReportColumn("urgency", "القرار", width="80px"),
)

register(ReportSpec(
    key="low-stock",
    title="المنتجات تحت حدّ الطلب",
    category="inventory",
    description=(
        "ما نفذ وما بلغ حدّه الأدنى معاً — صفٌّ واحد لكل منتج (مجموع برانداته "
        "مقارَناً بحدّه). الحدّ يُقرأ يدوياً إن ضُبط وإلّا يُحسب من المبيعات، "
        "وينقّب صفّ المنتج إلى برانداته."
    ),
    filters=(
        ReportFilter("product", "المنتج", "product"),
        ReportFilter("partner", "المورّد", "supplier"),
    ),
    columns=_LOW_STOCK_COLUMNS,
    permission="inventory.item.view",
    row_link="/products/{product_id}",
    build=lambda t, p: _low_stock(t, p, group="product"),
    drill=lambda t, p: _low_stock(t, p, group="product_brand"),
    drill_keys=("family_id", "product_id"),
    drill_title="برندات هذا المنتج",
    drill_columns=_LOW_STOCK_COLUMNS,
))


# ══════════════════════════════════════════════════════════════════════
#  تجديد المخزون — «ماذا أطلب، وكم» بمستوى المنتج أو الصنف
# ══════════════════════════════════════════════════════════════════════
#
# لماذا تقريران لا واحد: «تحت حدّ الطلب» سؤال حالةٍ («ما الذي نفد؟») يقرؤه
# البائع، وهذا سؤال قرارٍ («ماذا أطلب من المورّد وبأي كمية؟») يقرؤه المشتري.
# نفس المحرّك يغذّيهما فلا ينحرف رقمٌ عن رقم، والاختلاف في الأعمدة والترتيب.

_URGENCY_OPTIONS = (
    ("", "الكل"),
    ("urgent", "عاجل"),
    ("deferred", "مؤجَّل"),
    ("dead", "راكد"),
)

_LEVEL_OPTIONS = (("item", "منتج"), ("group", "صنف"))


def _replenishment(tenant_id: int, params: dict) -> list[dict]:
    from inventory.stock_status import STATUS_LABELS

    level = "group" if (params.get("level") or "item") == "group" else "item"
    rows = _reorder_rows(tenant_id, params, level=level)
    if level == "item" and not (params.get("urgency") or None):
        # #33/ط10: صنفٌ **تلقائي** لا يطلب شيئاً يسقط من العرض الافتراضي — لا
        # من المحرّك (الذي يبقيه لأجل فلتر «راكد»)، بل هنا فقط. وحين يُطلب
        # فلتر قرارٍ بعينه صراحةً (`urgency=dead` مثلاً) تُعرض مطابقاته كاملةً
        # بصرف النظر عن الكمية. مقصورٌ على `auto`: المسار اليدوي عرضه اليوم لا
        # يتغيّر حرفاً — منتجٌ مكتملُ الرصيد كان يظهر بكميةٍ صفرية وما زال.
        rows = [r for r in rows if not (r["reorder_mode"] == "auto" and r["order_qty"] <= ZERO)]
    if level == "group":
        return [{
            "group_key": r["group_key"],
            "name": r["group_key"],
            "products_count": r["products_count"],
            "out_of_stock_count": r["out_of_stock_count"],
            "available": _qty(r["available"]),
            "on_order": _qty(r["on_order"]),
            "adu": _rate(r["adu"]),
            "lead_days": _qty(r["lead_days"]),
            "suggested_min": _qty(r["suggested_min"]),
            "suggested_max": _qty(r["suggested_max"]),
            "order_qty": _qty(r["order_qty"]),
            "newest_alternative": r["newest_alternative"],
            "urgency": r["urgency_label"],
        } for r in rows]
    from core.replenishment import MODE_LABELS

    return [{
        "product_id": r["product_id"],
        "sku": r["sku"],
        "name": r["name"],
        "category": r["category"],
        "status": STATUS_LABELS[r["status"]],
        "urgency": r["urgency_label"],
        "available": _qty(r["available"]),
        "on_order": _qty(r["on_order"]),
        "group_available": _qty(r["group_available"]),
        "alternatives": r["alternatives"],
        "newest_alternative": r["newest_alternative"],
        "adu": _rate(r["adu"]),
        "lead_days": _qty(r["lead_days"]),
        "manual_min": _qty(r["manual_min"]) if r["manual_min"] else "",
        "suggested_min": _qty(r["suggested_min"]),
        "suggested_max": _qty(r["suggested_max"]),
        "order_qty": _qty(r["order_qty"]),
        "reason": r["reason"],
        "group_key": r["group_key"],
        # #33: أعمدة تفسّر الرقم — البيع الأسبوعي والاتجاه (من `ProductDemandForecast`
        # إن وُجد صفّه)، وأسابيع التغطية ومخزون الأمان اللذان يحكمان المسار
        # التلقائي، ووضع الصنف نفسه (تلقائي/يدوي).
        "weekly_sale": _qty(r["weekly_sale"]) if r["weekly_sale"] is not None else "",
        "trend_label": r["trend_label"],
        "coverage_weeks": _rate(r["coverage_weeks"]),
        "safety_stock": _qty(r["safety_stock"]),
        "reorder_mode": MODE_LABELS[r["reorder_mode"]],
        # #34/ط9: حدّ المورّد الأدنى — إشارةٌ ظاهرة حين تُرفَع الكمية إليه، لا
        # رفعٌ صامت («silently raising a number the owner will act on is worse
        # than not raising it»).
        "moq_note": (
            f"رُفعت لحدّ المورّد الأدنى ({_qty(r['min_order_qty'])})"
            if r.get("moq_raised") else ""
        ),
    } for r in rows]


def _replenishment_drill(tenant_id: int, params: dict) -> list[dict]:
    """صفّ الصنف يُفتح على منتجاته — من **نفس** الدالّة التي بنت الصفّ."""
    from inventory.stock_status import STATUS_LABELS

    group_key = params.get("group_key")
    # فلتر «القرار» يُسقَط هنا عمداً: صفّ الصنف مصنَّفٌ بأشدّ قرارٍ في أفراده،
    # فلو صُفّي التفصيل بالقرار نفسه لغابت المنتجات التي جعلت الصفّ ما هو عليه —
    # والتنقيب جاء ليُظهر من أين جاء الرقم لا ليكرّر تصنيفه.
    params = {k: v for k, v in params.items() if k != "urgency"}
    rows = _reorder_rows(tenant_id, params, level="item")
    return [{
        "sku": r["sku"],
        "name": r["name"],
        "status": STATUS_LABELS[r["status"]],
        "available": _qty(r["available"]),
        "on_order": _qty(r["on_order"]),
        "adu": _rate(r["adu"]),
        "suggested_min": _qty(r["suggested_min"]),
        "order_qty": _qty(r["order_qty"]),
        "reason": r["reason"],
    } for r in rows if r["group_key"] == group_key]


#: #34/ط5: أقدم من أسبوعٍ ومهلة — تحذيرٌ لا حسابٌ ذاتي (الممنوع صراحةً).
STALE_FORECAST_DAYS = 10


def _replenishment_notice(tenant_id: int, params: dict) -> str | None:
    """تنبّؤ تجديد المخزون أقدم من عشرة أيام ⇒ تحذيرٌ فوق الجدول.

    آخر حساب = أحدث `computed_at` عبر تنبّؤات الشركة (`recompute_demand_forecast`
    يكتبها دفعةً واحدة في نفس التشغيل، فكلّها من نفس الدفعة تقريباً). لا صفوف
    تنبّؤ أصلاً (الأمر لم يُشغَّل قط على هذه الشركة) ⇒ لا شيء يُقاس قِدَمه بعد،
    فلا تحذير — نفس فلسفة `REASON_NO_FORECAST` لكل صفّ (سببٌ مكتوب لا صمت).
    """
    from django.utils import timezone

    from inventory.models import ProductDemandForecast

    last = ProductDemandForecast.objects.filter(tenant_id=tenant_id).aggregate(
        last=Max("computed_at"),
    )["last"]
    if last is None:
        return None
    age_days = (timezone.now() - last).days
    if age_days <= STALE_FORECAST_DAYS:
        return None
    local_date = timezone.localtime(last).date()
    return (
        f"آخر حساب لتنبّؤ الطلب الأسبوعي كان بتاريخ {local_date:%Y-%m-%d} "
        f"({age_days} يوماً) — الكميات المقترَحة للأصناف «التلقائية» قد تكون "
        "مبنيّة على أرقامٍ قديمة. تحقّق أن مهمة recompute_demand_forecast الأسبوعية تعمل."
    )


register(ReportSpec(
    key="stock-replenishment",
    title="تجديد المخزون — ماذا أطلب",
    category="inventory",
    description=(
        "الحدّ الأدنى محسوباً من المبيعات ومهلة التوريد، والكمية المقترح طلبها. "
        "«عاجل» = لا بديل في الصنف. «مؤجَّل» = موديل آخر من الصنف نفسه يغطّي. "
        "«راكد» = رصيدٌ بلا مبيعات. المنتج الحديث في المخزن يعود بلا اقتراح وبسببه."
    ),
    filters=(
        ReportFilter("level", "المستوى", "select", options=_LEVEL_OPTIONS, default="item"),
        ReportFilter("urgency", "القرار", "select", options=_URGENCY_OPTIONS),
        ReportFilter("product", "المنتج", "product"),
        ReportFilter("partner", "المورّد", "supplier"),
    ),
    columns=(
        ReportColumn("sku", "الرمز", width="110px"),
        ReportColumn("name", "المنتج"),
        ReportColumn("urgency", "القرار", width="80px"),
        ReportColumn("status", "الحالة", width="80px"),
        ReportColumn("available", "المتاح", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("on_order", "قيد الطلب", KIND_NUMBER, total=True, width="90px"),
        # «الصنف» عمودٌ ظاهر عمداً: هو مفتاح قرار «مؤجَّل»، وحين يكون اسمَ المنتج
        # نفسه يرى المستخدم فوراً أن منتجاته بلا مجموعةٍ معرَّفة — فيملأ
        # `variant_group` أو `brand` بدل أن يتساءل لماذا «البدائل» صفرٌ دائماً.
        ReportColumn("group_key", "الصنف", width="140px"),
        ReportColumn("group_available", "رصيد الصنف", KIND_NUMBER, width="100px"),
        ReportColumn("alternatives", "بدائل", KIND_INT, width="70px"),
        ReportColumn("newest_alternative", "أحدث بديل متوفّر"),
        ReportColumn("adu", "الصرف اليومي", KIND_NUMBER, width="110px"),
        ReportColumn("lead_days", "المهلة (يوم)", KIND_NUMBER, width="100px"),
        ReportColumn("manual_min", "الحد اليدوي", KIND_NUMBER, width="100px"),
        ReportColumn("suggested_min", "الأدنى المقترَح", KIND_NUMBER, width="120px"),
        ReportColumn("suggested_max", "الأقصى المقترَح", KIND_NUMBER, width="120px"),
        ReportColumn("order_qty", "المقترح طلبه", KIND_NUMBER, total=True, width="110px"),
        # #33: أعمدة تفسّر الرقم — «ما بدي رقم بينزل من السما».
        ReportColumn("weekly_sale", "البيع الأسبوعي", KIND_NUMBER, width="100px"),
        ReportColumn("trend_label", "الاتجاه", width="70px"),
        ReportColumn("coverage_weeks", "أسابيع التغطية", KIND_NUMBER, width="100px"),
        ReportColumn("safety_stock", "مخزون الأمان", KIND_NUMBER, width="100px"),
        ReportColumn("reorder_mode", "الوضع", width="70px"),
        ReportColumn("reason", "ملاحظة"),
        # #34/ط9: حدّ المورّد الأدنى — يظهر فقط حين رُفعت الكمية إليه.
        ReportColumn("moq_note", "حدّ المورّد الأدنى", width="160px"),
    ),
    permission="inventory.item.view",
    row_link="/products/{product_id}",
    notice=_replenishment_notice,
    drill=_replenishment_drill,
    drill_keys=("group_key",),
    drill_title="منتجات هذا الصنف",
    drill_columns=(
        ReportColumn("sku", "الرمز", width="110px"),
        ReportColumn("name", "المنتج"),
        ReportColumn("status", "الحالة", width="80px"),
        ReportColumn("available", "المتاح", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("on_order", "قيد الطلب", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("adu", "الصرف اليومي", KIND_NUMBER, width="110px"),
        ReportColumn("suggested_min", "الأدنى المقترَح", KIND_NUMBER, width="120px"),
        ReportColumn("order_qty", "المقترح طلبه", KIND_NUMBER, total=True, width="110px"),
        ReportColumn("reason", "ملاحظة"),
    ),
    build=_replenishment,
))


def _stock_movements(tenant_id: int, params: dict) -> list[dict]:
    from inventory.models import StockMovement

    qs = StockMovement.objects.filter(tenant_id=tenant_id).select_related(
        "product", "warehouse", "partner",
    )
    qs = _apply_dates(qs, "movement_date", params)
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(product_id=product)
    warehouse = _int_param(params, "warehouse")
    if warehouse:
        qs = qs.filter(warehouse_id=warehouse)
    return [{
        "id": m.id,
        "movement_date": m.movement_date,
        "sku": m.product.sku if m.product_id else "",
        "name": (m.product.name_ar or m.product.name_en) if m.product_id else "",
        "warehouse": m.warehouse.name if m.warehouse_id else "",
        "movement_type": "وارد" if m.movement_type == "IN" else "صادر",
        "quantity": _qty(m.quantity),
        "quantity_after": _qty(m.quantity_after),
        "unit_cost": _money(m.unit_cost),
        "total_cost": _money(m.total_cost),
        "reference": f"{m.reference_type} #{m.reference_id}" if m.reference_type else "",
        "partner_name": m.partner.name if m.partner_id else "",
    } for m in qs.order_by("movement_date", "id")]


register(ReportSpec(
    key="stock-movements",
    title="حركة المخزون",
    category="inventory",
    description="كل حركة وارد وصادر بمصدرها ورصيدها بعد الحركة.",
    filters=DATE_FILTERS + (
        ReportFilter("product", "المنتج", "product"),
        ReportFilter("warehouse", "المستودع", "warehouse"),
    ),
    columns=(
        ReportColumn("movement_date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("sku", "الرمز", width="110px"),
        ReportColumn("name", "المنتج"),
        ReportColumn("warehouse", "المستودع", width="120px"),
        ReportColumn("movement_type", "النوع", width="80px"),
        ReportColumn("quantity", "الكمية", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("quantity_after", "الرصيد بعدها", KIND_NUMBER, width="110px"),
        ReportColumn("unit_cost", "تكلفة الوحدة", KIND_MONEY, width="110px"),
        ReportColumn("total_cost", "إجمالي التكلفة", KIND_MONEY, total=True),
        ReportColumn("reference", "المستند", width="150px"),
        ReportColumn("partner_name", "الطرف"),
    ),
    permission="inventory.item.view",
    build=_stock_movements,
))


def _reserved_stock(tenant_id: int, params: dict) -> list[dict]:
    from sales.services import reserved_stock_rows

    start, end = _date_range(params)
    rows = reserved_stock_rows(
        tenant_id,
        product_id=_int_param(params, "product"),
        customer_id=_int_param(params, "partner"),
        date_from=start, date_to=end,
    )
    return [{
        "order_number": r.get("order_number") or "",
        "partner_name": r.get("customer_name") or "",
        "sku": r.get("sku") or "",
        "name": r.get("product_name") or "",
        "quantity": _qty(r.get("quantity")),
        "reserved_until": r.get("reserved_until"),
    } for r in rows]


register(ReportSpec(
    key="reserved-stock",
    title="الكميات المحجوزة",
    category="inventory",
    description="ما حجزته الطلبيات المؤكَّدة ولم يُسلَّم — نفس مصدر حارس البيع.",
    filters=DATE_FILTERS + (
        ReportFilter("product", "المنتج", "product"),
        ReportFilter("partner", "العميل", "customer"),
    ),
    columns=(
        ReportColumn("order_number", "الطلبية", width="130px"),
        ReportColumn("partner_name", "العميل"),
        ReportColumn("sku", "الرمز", width="110px"),
        ReportColumn("name", "المنتج"),
        ReportColumn("quantity", "المحجوز", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("reserved_until", "الحجز حتى", KIND_DATE, width="110px"),
    ),
    permission="inventory.item.view",
    build=_reserved_stock,
))


# ══════════════════════════════════════════════════════════════════════
#  المالية والنقدية
# ══════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════
#  حركة المخزون حسب بُعد — تقرير واحد بأبعادٍ تُبدَّل، لا تقرير لكل بُعد
# ══════════════════════════════════════════════════════════════════════
#
# لماذا بُعدٌ واحد قابل للتبديل بدل خمسة تقارير: السؤال واحد («ما الذي دخل
# وخرج، وبكم») والمختلف هو **محور** الإجابة وحده. خمسة تقارير تعني خمس نسخ من
# منطق الاتجاه والتكلفة تتباعد مع أول تعديل، وخمسة أسماء يبحث المستخدم بينها.
#
# ومحور الطرف يُقرأ من `StockMovement.partner` كما كتبه `record_stock_movement`:
# استلامُ الشراء يكتب المورّد، وترحيلُ البيع يكتب الزبون. فـ«حسب المورد» ليس
# فلترةً على نوع الحركة بل على **نوع الطرف** — وبذلك يظهر تحت المورّد وارده
# ومرتجعُه إليه معاً، وتحت الزبون صادرُه ومرتجعُه منه. حركةٌ بلا طرف (تحويل
# مستودعي، جرد، تسوية) لا مورّد لها ولا زبون فتغيب عن هذين المحورين وحدهما —
# وهذا مكتوب في وصف التقرير لا مسكوتٌ عنه.

_STOCK_INBOUND = ("IN", "ADJUST_IN", "RETURN_IN")
_STOCK_OUTBOUND = ("OUT", "ADJUST_OUT", "RETURN_OUT")

#: كل بُعد: ترويسة عموده · حقول التجميع · مفتاح الآلة · لافتة الصفّ · قصرُ
#: مجموعةِ الحركات عليه إن لزم. الإضافة لاحقاً = مدخل واحد هنا.
_STOCK_DIMENSIONS: dict[str, dict] = {
    "supplier": {
        "header": "المورد",
        "fields": ("partner_id", "partner__name"),
        "key_of": lambda r: str(r["partner_id"] or ""),
        "label_of": lambda r: r["partner__name"] or "— بلا طرف —",
        "restrict": {"partner__partner_type": "Supplier"},
        "filter_of": lambda key: {"partner_id": int(key)} if key else {"partner__isnull": True},
    },
    "customer": {
        "header": "الزبون",
        "fields": ("partner_id", "partner__name"),
        "key_of": lambda r: str(r["partner_id"] or ""),
        "label_of": lambda r: r["partner__name"] or "— بلا طرف —",
        "restrict": {"partner__partner_type": "Customer"},
        "filter_of": lambda key: {"partner_id": int(key)} if key else {"partner__isnull": True},
    },
    "warehouse": {
        "header": "المستودع",
        "fields": ("warehouse_id", "warehouse__name"),
        "key_of": lambda r: str(r["warehouse_id"] or ""),
        "label_of": lambda r: r["warehouse__name"] or "— غير محدَّد —",
        "restrict": None,
        "filter_of": lambda key: {"warehouse_id": int(key)} if key else {"warehouse__isnull": True},
    },
    "brand": {
        "header": "الماركة",
        "fields": ("product__brand",),
        "key_of": lambda r: r["product__brand"] or "",
        "label_of": lambda r: r["product__brand"] or "— بلا ماركة —",
        "restrict": None,
        # الماركة نصٌّ على المنتج لا مفتاحٌ خارجي: الفارغ والـNULL كلاهما «بلا
        # ماركة»، فيجب أن يلتقطهما التنقيب معاً وإلا فتح صفّاً على لا شيء.
        "filter_of": lambda key: (
            {"product__brand": key} if key else {"product__brand__in": ["", None]}
        ),
    },
    "product": {
        "header": "المنتج",
        "fields": ("product_id", "product__sku", "product__name_ar", "product__name_en"),
        "key_of": lambda r: str(r["product_id"] or ""),
        "label_of": lambda r: (
            r["product__name_ar"] or r["product__name_en"] or r["product__sku"] or "—"
        ),
        "restrict": None,
        "filter_of": lambda key: {"product_id": int(key)},
    },
}

_STOCK_DIM_DEFAULT = "supplier"


def _stock_dimension(params: dict) -> tuple[str, dict]:
    """البُعد المطلوب — وغير المعروف يعود للافتراضي بدل أن يرفع خطأً."""
    raw = str(params.get("group_by") or "").strip() or _STOCK_DIM_DEFAULT
    if raw not in _STOCK_DIMENSIONS:
        raw = _STOCK_DIM_DEFAULT
    return raw, _STOCK_DIMENSIONS[raw]


def _stock_detailed(params: dict) -> bool:
    """مفصَّلاً (صفٌّ لكل بُعد×منتج) أم ملخَّصاً (صفٌّ لكل قيمة بُعد)؟

    المفصَّل هو الافتراضي لأنه ما يُسأل عنه فعلاً («منتجات هذا المورد وكمياتها»)؛
    والملخَّص موجود لأن خمسين مورّداً × مئتَي منتج = عشرة آلاف سطر لا تُقرأ.
    كلاهما يُنقَّب إلى الحركات نفسها.
    """
    return str(params.get("detail") or "lines").strip() != "summary"


def _stock_dimension_queryset(tenant_id: int, params: dict):
    """مجموعة الحركات بعد كل الفلاتر — مصدرٌ واحد للتجميع وللتنقيب.

    وحدةُ المصدر هي ما يجعل «مجموع التنقيب = رقم الصفّ» صحيحاً **بالبناء** لا
    بالمصادفة: لو بُني الرقمان من مجموعتين لانحرفا عند أول فلتر يُنسى في إحداهما.
    """
    from inventory.models import StockMovement

    _key, dim = _stock_dimension(params)
    qs = StockMovement.objects.filter(tenant_id=tenant_id)
    qs = _apply_dates(qs, "movement_date", params)
    if dim["restrict"]:
        qs = qs.filter(**dim["restrict"])
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(product_id=product)
    warehouse = _int_param(params, "warehouse")
    if warehouse:
        qs = qs.filter(warehouse_id=warehouse)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(partner_id=partner)
    return qs


def _stock_signed_sum(field_name: str, types: tuple[str, ...]):
    """مجموع حقلٍ على اتجاهٍ واحد — الكمية مخزَّنة موجبةً والاتجاه في النوع."""
    from django.db.models import Case, When

    return Coalesce(
        Sum(Case(
            When(movement_type__in=types, then=F(field_name)),
            default=Value(ZERO),
            output_field=DecimalField(max_digits=20, decimal_places=4),
        )),
        Value(ZERO),
        output_field=DecimalField(max_digits=20, decimal_places=4),
    )


def _sale_movement_shares(tenant_id: int, qs, extra_fields=()) -> list[dict]:
    """نصيب كل حركة بيع من إيراد سطر فاتورتها — مصدرٌ واحد للتجميع وللتنقيب.

    **لماذا الإيراد يُسنَد إلى الحركة لا إلى الصفّ**: لو حُسب الإيراد من أسطر
    الفواتير مباشرةً لصار في الصفّ الواحد رقمان من عالمين — كميةٌ وتكلفةٌ مجموعتان
    على الحركات، وإيرادٌ مجموعٌ على الأسطر — فينهار معيار «مجموع التنقيب = رقم
    الصفّ» على عمودٍ واحد بلا أن ينبّه أحد. وبإسناده إلى الحركة يبقى كل رقم في
    الصفّ مجموعاً على **نفس** الحركات، ويمتدّ المعيار إلى الإيراد والربح مجّاناً.

    النصيب = صافي سطر (الفاتورة، المنتج) × كمية هذه الحركة ÷ **كل** كمية حركات
    ذلك السطر. المقام غير مفلتر عمداً (`sales_cogs_map` يعطيه على كامل المستند):
    لو قُسِم على الكميات داخل النطاق وحدها لتضخّم نصيبُ الحركة كلما ضاقت الفترة،
    فتقرير شهرٍ يعطي إيراد سنة.

    والتقريب على الحركة لا على مجموعها — فالذرّة نفسها في المسارين، ومجموعهما
    متطابق بالبناء. ثمنُه أن مجموع أنصبة فاتورةٍ قد يخالف صافيها بقرش أو قرشين:
    فرقُ تقريبٍ معلوم، ثمنُه أرخص من رقمين لا يتطابقان على الشاشة.

    حركةُ بيعٍ بلا سطر مقابل (منتجٌ خرج ولا بند له) نصيبُها صفر و**ربحُها صفر لا
    خسارة**: تكلفتها معلومة وإيرادها مجهول، وإعلانُها خسارةً اختراعُ رقم.
    """
    from sales.services import (
        SALES_STOCK_REFERENCE_TYPES,
        sales_cogs_map,
        sales_revenue_map,
    )

    fields = ["id", "reference_id", "product_id", "quantity", "total_cost"]
    for name in extra_fields:
        if name not in fields:
            fields.append(name)
    rows = list(
        qs.filter(
            reference_type__in=SALES_STOCK_REFERENCE_TYPES,
            movement_type__in=_STOCK_OUTBOUND,
        ).values(*fields)
    )
    if not rows:
        return []

    invoice_ids = {r["reference_id"] for r in rows if r["reference_id"]}
    moved = sales_cogs_map(tenant_id=tenant_id, invoice_ids=invoice_ids)
    lines = sales_revenue_map(tenant_id=tenant_id, invoice_ids=invoice_ids)
    for r in rows:
        key = (r["reference_id"], r["product_id"])
        line = lines.get(key)
        total_qty = Decimal(str((moved.get(key) or {}).get("qty") or 0))
        if line is None or total_qty <= 0:
            r["revenue"] = ZERO
            r["profit"] = ZERO
            continue
        share = (line["net"] * Decimal(str(r["quantity"] or 0)) / total_qty).quantize(DEC)
        r["revenue"] = share
        r["profit"] = share - Decimal(str(r["total_cost"] or 0))
    return rows


def _stock_by_dimension(tenant_id: int, params: dict) -> list[dict]:
    """استعلام تجميعي **واحد** للكميات والتكلفة — لا استعلام لكل صفّ.

    الاتجاه يُحسم داخل الاستعلام بـ`Case/When` على نوع الحركة، وأسماءُ الطرف
    والمنتج والمستودع تأتي بضمّها في نفس `values()` — فلا جولةُ جلبٍ ثانية ولا N+1.
    والإيراد يلزمه مرورٌ ثانٍ (لا يسكن في جدول الحركات) بعدد استعلاماتٍ **ثابت**
    لا يتبع عدد الصفوف — وهو الضمان الذي يهمّ.
    """
    from django.db.models import Count

    _key, dim = _stock_dimension(params)
    detailed = _stock_detailed(params)

    group_fields = list(dim["fields"])
    if detailed:
        for extra in ("product_id", "product__sku", "product__name_ar", "product__name_en"):
            if extra not in group_fields:
                group_fields.append(extra)

    rows = (
        _stock_dimension_queryset(tenant_id, params)
        .values(*group_fields)
        .annotate(
            qty_in=_stock_signed_sum("quantity", _STOCK_INBOUND),
            qty_out=_stock_signed_sum("quantity", _STOCK_OUTBOUND),
            cost_in=_stock_signed_sum("total_cost", _STOCK_INBOUND),
            cost_out=_stock_signed_sum("total_cost", _STOCK_OUTBOUND),
            moves=Count("id"),
        )
    )

    # الإيراد والربح مجموعان على **نفس** حركات الصفّ، بمفتاح تجميعٍ واحد.
    revenue_by_group: dict[tuple, Decimal] = {}
    profit_by_group: dict[tuple, Decimal] = {}
    for share in _sale_movement_shares(
        tenant_id, _stock_dimension_queryset(tenant_id, params), group_fields,
    ):
        group_key = tuple(share.get(name) for name in group_fields)
        revenue_by_group[group_key] = revenue_by_group.get(group_key, ZERO) + share["revenue"]
        profit_by_group[group_key] = profit_by_group.get(group_key, ZERO) + share["profit"]

    out: list[dict] = []
    for r in rows:
        qty_in = Decimal(str(r["qty_in"] or 0))
        qty_out = Decimal(str(r["qty_out"] or 0))
        group_key = tuple(r.get(name) for name in group_fields)
        out.append({
            "dim_label": dim["label_of"](r),
            "sku": (r.get("product__sku") or "") if detailed else "",
            "product_name": (
                (r.get("product__name_ar") or r.get("product__name_en") or "")
                if detailed else ""
            ),
            "qty_in": _qty(qty_in),
            "qty_out": _qty(qty_out),
            "qty_net": _qty(qty_in - qty_out),
            "cost_in": _money(r["cost_in"]),
            "cost_out": _money(r["cost_out"]),
            "revenue": _money(revenue_by_group.get(group_key, ZERO)),
            "profit": _money(profit_by_group.get(group_key, ZERO)),
            "moves": r["moves"],
            # مفاتيح آلة لا أعمدة عرض: يحملها الصفّ ليعيدها التنقيب كما هي.
            "dim_key": dim["key_of"](r),
            "row_product": str(r.get("product_id") or "") if detailed else "",
        })

    # مجمَّعاً بالبُعد ثم الأثقل حركةً أولاً — «منتجات هذا المورد» تُقرأ متجاورة.
    out.sort(key=lambda row: (
        row["dim_label"],
        -abs(Decimal(row["qty_in"]) - Decimal(row["qty_out"])),
        row["sku"],
    ))
    return out


def _stock_by_dimension_columns(tenant_id: int, params: dict):
    """العمود الأول يتبع البُعد المختار، وعمودا المنتج يظهران بالتفصيل وحده."""
    dim_key, dim = _stock_dimension(params)
    detailed = _stock_detailed(params)
    columns = [ReportColumn("dim_label", dim["header"], width="200px")]
    if detailed and dim_key != "product":
        columns += [
            ReportColumn("sku", "الرمز", width="110px"),
            ReportColumn("product_name", "المنتج"),
        ]
    elif detailed:
        # البُعد هو المنتج نفسه: يكفي رمزه — عمود الاسم يكرّر العمود الأول.
        columns += [ReportColumn("sku", "الرمز", width="110px")]
    columns += [
        ReportColumn("qty_in", "الوارد", KIND_NUMBER, total=True, width="95px"),
        ReportColumn("qty_out", "الصادر", KIND_NUMBER, total=True, width="95px"),
        ReportColumn("qty_net", "الصافي", KIND_NUMBER, total=True, width="95px"),
        ReportColumn("cost_in", "تكلفة الوارد", KIND_MONEY, total=True, width="120px"),
        ReportColumn("cost_out", "تكلفة الصادر", KIND_MONEY, total=True, width="120px"),
    ]
    # الإيراد والربح يُسندان إلى حركة **البيع**، ومحور المورّد لا يحوي منها شيئاً
    # (طرفُ حركة الشراء هو المورّد وطرفُ حركة البيع هو الزبون). فعمودٌ صفرٌ أبداً
    # يُقرأ «لم نربح من بضاعة هذا المورّد» وهو غير ما يقوله. والسؤال نفسه — ربحُ
    # بضاعةِ مورّدٍ بعينه — يلزمه تتبّعُ طبقات التكلفة (أي بيعةٍ استهلكت أي دفعة
    # شراء)، وهو غير موجودٍ تحت المتوسط المرجّح إلا للوحدات المُرقَّمة.
    if dim_key != "supplier":
        columns += [
            ReportColumn("revenue", "الإيراد", KIND_MONEY, total=True, width="120px"),
            ReportColumn("profit", "الربح", KIND_MONEY, total=True, width="120px"),
        ]
    columns += [
        ReportColumn("moves", "عدد الحركات", KIND_INT, total=True, width="100px"),
    ]
    return tuple(columns)


_STOCK_DRILL_COLUMNS = (
    ReportColumn("movement_date", "التاريخ", KIND_DATE, width="105px"),
    ReportColumn("document", "المستند", width="160px"),
    ReportColumn("sku", "الرمز", width="100px"),
    ReportColumn("product_name", "المنتج"),
    ReportColumn("warehouse", "المستودع", width="110px"),
    ReportColumn("partner_name", "الطرف"),
    ReportColumn("qty_in", "الوارد", KIND_NUMBER, total=True, width="90px"),
    ReportColumn("qty_out", "الصادر", KIND_NUMBER, total=True, width="90px"),
    ReportColumn("qty_net", "الصافي", KIND_NUMBER, total=True, width="90px"),
    ReportColumn("cost_in", "تكلفة الوارد", KIND_MONEY, total=True, width="110px"),
    ReportColumn("cost_out", "تكلفة الصادر", KIND_MONEY, total=True, width="110px"),
    ReportColumn("revenue", "الإيراد", KIND_MONEY, total=True, width="110px"),
    ReportColumn("profit", "الربح", KIND_MONEY, total=True, width="110px"),
    ReportColumn("moves", "عدد الحركات", KIND_INT, total=True, width="95px"),
)


def _stock_by_dimension_drill(tenant_id: int, params: dict) -> list[dict]:
    """حركات صفٍّ واحد — نفس المجموعة المفلترة، مقصورةً على مفتاحَي الصفّ.

    أعمدتها هي أعمدة الصفّ نفسها (وارد/صادر/صافي/تكلفة/عدد) بقيمةٍ لكل حركة، كي
    تكون المقارنة عموداً بعمود لا تفسيراً: مجموع العمود هنا = خانة الصفّ هناك.
    """
    _key, dim = _stock_dimension(params)
    qs = _stock_dimension_queryset(tenant_id, params)

    dim_key = str(params.get("dim_key") or "")
    try:
        qs = qs.filter(**dim["filter_of"](dim_key))
    except (TypeError, ValueError):
        # مفتاح غير صالح لا يفتح كل الحركات — صفّ لا نعرف مفتاحه لا تفصيل له.
        return []
    row_product = _int_param(params, "row_product")
    if row_product:
        qs = qs.filter(product_id=row_product)

    # نفس الدالّة التي بنت عمودَي الإيراد والربح في الصفّ — لا حسابٌ ثانٍ هنا.
    shares = {s["id"]: s for s in _sale_movement_shares(tenant_id, qs)}

    rows = []
    for m in qs.select_related("product", "warehouse", "partner").order_by("movement_date", "id"):
        inbound = m.movement_type in _STOCK_INBOUND
        qty = Decimal(str(m.quantity or 0))
        cost = Decimal(str(m.total_cost or 0))
        share = shares.get(m.id) or {}
        rows.append({
            "id": m.id,
            "movement_date": m.movement_date,
            "document": (
                f"{m.get_reference_type_display()} #{m.reference_id}"
                if m.reference_id else m.get_reference_type_display()
            ),
            "sku": m.product.sku if m.product_id else "",
            "product_name": (
                (m.product.name_ar or m.product.name_en or "") if m.product_id else ""
            ),
            "warehouse": m.warehouse.name if m.warehouse_id else "",
            "partner_name": m.partner.name if m.partner_id else "",
            "qty_in": _qty(qty if inbound else ZERO),
            "qty_out": _qty(ZERO if inbound else qty),
            "qty_net": _qty(qty if inbound else -qty),
            "cost_in": _money(cost if inbound else ZERO),
            "cost_out": _money(ZERO if inbound else cost),
            "revenue": _money(share.get("revenue") or ZERO),
            "profit": _money(share.get("profit") or ZERO),
            "moves": 1,
        })
    return rows


register(ReportSpec(
    key="stock-by-dimension",
    title="حركة المخزون حسب بُعد",
    category="inventory",
    description=(
        "ما دخل وما خرج وبكم وبكم بِيع — بمحورٍ تختاره: المورد أو الزبون أو "
        "المستودع أو الماركة أو المنتج. كل صفّ يُفتح على الحركات التي كوّنته "
        "ومجموعها يطابقه في كل عمود. محورا المورد والزبون يقرآن طرف الحركة، "
        "فالتحويل المستودعي والجرد (بلا طرف) يغيبان عنهما ويظهران في بقية "
        "المحاور. والإيراد والربح مُسنَدان إلى حركة البيع نفسها بنصيبها من صافي "
        "سطر فاتورتها، فلا يظهران على محور المورد — إسنادُ ربحِ بيعةٍ إلى مورّد "
        "بضاعتها يلزمه تتبّع طبقات التكلفة."
    ),
    filters=DATE_FILTERS + (
        ReportFilter(
            "group_by", "جمِّع حسب", "select",
            options=(
                ("supplier", "المورد"),
                ("customer", "الزبون"),
                ("warehouse", "المستودع"),
                ("brand", "الماركة"),
                ("product", "المنتج"),
            ),
            default=_STOCK_DIM_DEFAULT,
        ),
        ReportFilter(
            "detail", "التفصيل", "select",
            options=(("lines", "مفصَّل — صفّ لكل منتج"), ("summary", "ملخَّص")),
            default="lines",
        ),
        ReportFilter("partner", "الطرف", "partner"),
        ReportFilter("product", "المنتج", "product"),
        ReportFilter("warehouse", "المستودع", "warehouse"),
    ),
    # الفهرس يُطلب بلا معاملات فيرى أعمدة البُعد الافتراضي؛ التشغيل يستبدلها.
    columns=_stock_by_dimension_columns(0, {}),
    columns_for=_stock_by_dimension_columns,
    permission="inventory.item.view",
    build=_stock_by_dimension,
    drill=_stock_by_dimension_drill,
    drill_columns=_STOCK_DRILL_COLUMNS,
    drill_keys=("dim_key", "row_product"),
    drill_title="الحركات المكوِّنة للسطر",
))
