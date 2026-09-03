"""عقد الصفحة العامة — ما يجوز أن يخرج، وكيف يُبنى. بلا استيراد نموذج واحد.

هذه الوحدة هي القاعدة التي تقف عليها كل أنواع المستندات: تعرّف **مجموعة**
مفاتيح الحمولة، والمُنشئ الوحيد الذي يُخرجها، ومفرداتِ العرض (نبرة الحالة،
أنواع القيم، بطاقة الطرف، بطاقة الشركة). لا تعرف `sales` ولا `logistics` ولا
`after_sales` — وهذا هو سبب وجودها ملفاً مستقلاً: النوع يعتمد على العقد، ولا
يعتمد العقد على نوع.

**القائمة البيضاء إيجابية لا سلبية.** «كل شيء عدا التكلفة» كان سينشر أي حقل
يُضاف مستقبلاً إلى النموذج — وقد أُضيف فعلاً `attached_cash_amount`
و`source_discount_amount_override` و`vat_statement`، ولا واحد منها للطرف الآخر.

**والحمولة تُبنى من `payload()` وحدها لا يدوياً.** قبل توسيع السطح إلى عائلة
أنواع كان كل بانٍ يجمّع قاموسه بنفسه، فكان مفتاحٌ زائد في نوعٍ واحد يمرّ ما
دام اختبارُ ذلك النوع لم يُحدَّث. الآن **مجموعة المفاتيح خاصية المُنشئ**:
`payload()` تُخرج `PAYLOAD_FIELDS` بالضبط دائماً، ويسري الحارس على كل نوع
جديد يوم كتابته لا يوم تذكُّر كاتبه.

**ولماذا بانٍ صريح لا `serializers.Serializer`:** هذا السطح يُصيَّر HTML لا JSON
(زاحف واتساب لا ينفّذ JavaScript فالصفحة خادمية بالكامل)، فلا مدخلات تُتحقَّق
ولا تمثيل يُتفاوض عليه — والسيريالايزر هنا طبقةٌ بلا عمل.
"""
from decimal import Decimal

# ── الجمهور: من يفتح الرابط ──────────────────────────────────────────────────
#
# «تسريب» ليست صفة حقلٍ في ذاته بل علاقةً بينه وبين من يفتح الرابط: سعرُ الشراء
# سرٌّ أمام الزبون وحقيقةٌ يعرفها المورّد أصلاً (هو من كتبها لنا)، ونسبةُ ربحنا
# سرٌّ أمام الاثنين. لذلك يحمل كل نوع جمهوره، ويحرس اختبار التسريب أن مستند
# المورّد بلا سعر بيعٍ وأن مستند الزبون بلا تكلفة.
AUDIENCE_CUSTOMER = "customer"
AUDIENCE_SUPPLIER = "supplier"
AUDIENCES = (AUDIENCE_CUSTOMER, AUDIENCE_SUPPLIER)


# ── عقد الحمولة العامة ──────────────────────────────────────────────────────

#: مجموعة مفاتيح الصفحة العامة — كل مفتاح هنا قرارٌ واعٍ بنشره للعالم.
PAYLOAD_FIELDS = (
    "kind", "title", "number", "date", "status_label", "status_tone",
    "party_title", "party_name", "party_address", "party_phone",
    "party_tax_number",
    "currency_code", "currency_symbol",
    "meta_rows", "show_lines", "show_line_prices", "lines", "totals_rows",
    "grand_total", "notes", "decision", "valid_until",
    # ISSUE #115: مسارٌ ثانٍ مستقلّ عن `decision` — أسعارُ بنود تُعدَّل مراراً
    # لا قرارُ قبول/رفض يُقفَل بعد مرّة. `None` لكل نوعٍ لا يقبل تسعيراً.
    "quote",
)

#: نبرة شارة الحالة. النماذج لا تتفق على مفردات الحالة (`posted` هنا و`Open`
#: هناك و`fully_paid` في ثالث)، فالقالب لا يقدر أن يفرّعها — والنوع وحده يعرف
#: ماذا تعني حالته، فيترجمها إلى نبرة.
TONE_OK = "ok"
TONE_WARN = "warn"
TONE_DANGER = "danger"
TONE_MUTED = "muted"
TONES = (TONE_OK, TONE_WARN, TONE_DANGER, TONE_MUTED)

#: أنواع قيم `meta_rows` — التنسيق يبقى في مرشّحات القالب (مصدرٌ واحد لقاعدة
#: الأرقام والتواريخ في `templatetags/docshare_fmt.py`)، والصفّ يقول أيّ مرشّح
#: يلزمه بدل أن يُنسَّق هنا فيصير للقاعدة نسختان تنحرفان.
VALUE_TEXT = "text"
VALUE_DATE = "date"
VALUE_MONEY = "money"
VALUE_QTY = "qty"


def tone_for(mapping: dict, status: str) -> str:
    """نبرةُ حالةٍ من خريطة النوع — وما ليس فيها محايدٌ لا مُقلِق.

    الافتراضُ `muted` لا `danger`: حالةٌ لم نُترجمها بعدُ لا تعني عطلاً، وشارةٌ
    حمراء على مستندٍ سليم تُفزع الزبون بلا سبب.
    """
    return mapping.get(status, TONE_MUTED)


def meta(label: str, value, kind: str = VALUE_TEXT):
    """صفّ بيانات — أو `None` إن كانت القيمة فارغة فيُحذف الصفّ كاملاً.

    صفٌّ بعنوانٍ وقيمةٍ فارغة ليس معلومةً ناقصة بل ضجيجٌ على ورقة الطرف الآخر.
    """
    if value is None or value == "":
        return None
    return {"label": label, "value": value, "kind": kind}


def total(label: str, value, *, strong: bool = False) -> dict:
    """صفّ في جدول الإجماليات. `strong` = السطر المُبرَز (الإجمالي عادةً)."""
    return {"label": label, "value": money(value), "strong": strong}


def money(value) -> Decimal:
    return Decimal(value or 0)


def _party_card(party, title: str) -> dict:
    """بطاقة الطرف كما تُطبع على الورقة — لا رصيده ولا سقفه الائتماني.

    الحقول `party_*` لا `customer_*`: نصفُ الأنواع طرفُها مورّد، واسمُ حقلٍ
    يقول «زبون» فوق اسم مورّد كذبةٌ يقرؤها من يصون الكود بعدنا.

    و`party` يقبل **نصّاً** كما يقبل صفّ `Partner`: عرضُ سعر المورّد قد يحمل
    مورّداً مبدئياً بالاسم وحده (`supplier_draft_name`) قبل أن يتجسّد صفّاً،
    ومستندٌ بلا اسم طرفٍ ورقةٌ مجهولة.
    """
    empty = {
        "party_title": title, "party_name": "", "party_address": "",
        "party_phone": "", "party_tax_number": "",
    }
    if party is None:
        return empty
    if isinstance(party, str):
        return empty | {"party_name": party}
    address = " — ".join(
        part for part in (party.street_address, party.city) if part
    )
    return {
        "party_title": title,
        "party_name": party.name,
        "party_address": address,
        "party_phone": party.phone or "",
        "party_tax_number": party.tax_number or "",
    }


def _currency_card(currency) -> dict:
    if currency is None:
        return {"currency_code": "", "currency_symbol": ""}
    return {
        "currency_code": currency.Code,
        "currency_symbol": currency.Symbol or currency.Code,
    }


def payload(
    *,
    kind: str,
    title: str,
    number: str,
    date,
    status_label: str,
    status_tone: str,
    party_title: str,
    party,
    currency,
    meta_rows=(),
    lines=(),
    totals_rows=(),
    grand_total=Decimal(0),
    notes: str = "",
    decision=None,
    valid_until=None,
    show_lines: bool = True,
    show_line_prices: bool = True,
    quote=None,
) -> dict:
    """المُنشئ الوحيد للحمولة العامة — ومجموعةُ مفاتيحها خاصيةٌ فيه.

    لا بانِيَ نوعٍ يجمّع قاموسه بنفسه بعد اليوم: مفتاحٌ لا يمرّ من هنا لا يخرج
    إلى الصفحة، ومفتاحٌ يُضاف هنا يُخفِق اختبارَ القائمة البيضاء فوراً فيُقرَّر
    نشرُه أو رفضُه صراحةً.
    """
    built = {
        "kind": kind,
        "title": title,
        "number": number or "",
        "date": date,
        "status_label": status_label or "",
        "status_tone": status_tone,
        "meta_rows": [row for row in meta_rows if row],
        "show_lines": show_lines,
        # أعمدةُ السعر تُحذف من الجدول كلّه لا تُملأ أصفاراً: سندُ التسليم
        # كمياتٌ بلا أسعار، وعمودُ «السعر» تحته صفرٌ يقول للمستلم إن البضاعة
        # مجّانية — أسوأ من غيابه.
        "show_line_prices": show_line_prices,
        "lines": list(lines),
        "totals_rows": list(totals_rows),
        "grand_total": money(grand_total),
        "notes": notes or "",
        "decision": decision,
        "valid_until": valid_until,
        "quote": quote,
    }
    built.update(_party_card(party, party_title))
    built.update(_currency_card(currency))
    assert set(built) == set(PAYLOAD_FIELDS), "الحمولة خرجت عن قائمتها البيضاء"
    return built


def tax_percent(line) -> Decimal:
    """نسبة الضريبة المعروضة — تجاوز السطر مقدَّم على نسبة الضريبة المرتبطة."""
    override = getattr(line, "line_tax_percent", None)
    if override is not None:
        return Decimal(override)
    if getattr(line, "tax_rate_id", None):
        return Decimal(line.tax_rate.rate)
    return Decimal(0)


def product_names(line) -> tuple[str, str]:
    """اسم الصنف العربي والإنجليزي — ولقطةُ الاسم مقدَّمةٌ حيث وُجدت.

    مستندات الشراء تحفظ `name_snapshot` وقت الإدخال: الصنف قد يُعاد تسميته
    بعد سنة، والورقة التي بيد المورّد يجب أن تبقى هي الورقة التي وقّعها.
    """
    snapshot = (getattr(line, "name_snapshot", "") or "").strip()
    product = getattr(line, "product", None)
    if product is None:
        return snapshot, ""
    name_ar = snapshot or product.name_ar or product.name_en or ""
    return name_ar, (product.name_en or "")


def line_row(
    *, name: str, name_en: str = "", catalog_no: str = "", note: str = "",
    unit: str = "", quantity=0, unit_price=0, line_discount=0,
    tax_percent=0, line_total=0,
) -> dict:
    """سطر بندٍ في الجدول — قائمة بيضاء ثانية، بنفس حجّة `payload()`."""
    return {
        "name": name or "",
        "name_en": name_en or "",
        "catalog_no": catalog_no or "",
        "note": note or "",
        "unit": unit or "",
        "quantity": money(quantity),
        "unit_price": money(unit_price),
        "line_discount": money(line_discount),
        "tax_percent": money(tax_percent),
        "line_total": money(line_total),
    }


# ── قرار المستلم ────────────────────────────────────────────────────────────

#: مفاتيح العرض في مواصفة القرار — وحدها تخرج إلى الصفحة. البقيّة (`is_open`،
#: `apply`، …) دوالٌّ خادمية لا تُصيَّر، وفصلُها هنا يمنع تسرّبها بحمولةٍ سهوية.
DECISION_DISPLAY_KEYS = (
    "title", "hint", "accept_label", "reject_label",
    "settled_accepted", "settled_rejected", "expired_note",
)

#: مواصفة قرارٍ كاملة = مفاتيح العرض + هذه. النقصُ يُخفِق `tests/test_registry.py`
#: وقت التسجيل، لا وقت أول زائر يضغط «موافق».
DECISION_LOGIC_KEYS = (
    "is_open", "closed_reason", "apply", "entity_type", "entity_label",
)


def decision_display(spec, document):
    """جزءُ العرض من مواصفة القرار + هل البابُ مفتوحٌ الآن.

    يُعاد حتى حين يكون البابُ مغلقاً: الصفحة تحتاج نصّ «تمت الموافقة» بعد
    القرار، وحالةُ المستند تكون قد تحرّكت عن الحالة التي تقبل القرار.
    """
    if spec is None:
        return None
    display = {key: spec[key] for key in DECISION_DISPLAY_KEYS}
    display["open"] = bool(spec["is_open"](document))
    return display


# ── تسعير المورّد (ISSUE #115) ──────────────────────────────────────────────
#
# مسارٌ **مستقلّ تماماً** عن القرار أعلاه — لا تمديدٌ لـ`apply` القرار، ولا
# مشاركةٌ لحقوله. الفرق جوهريّ: القرار قبولٌ/رفضٌ يُقفَل بعد مرّة، والتسعير
# أسعارُ بنودٍ تُعدَّل مراراً ما دام المستند مفتوحاً. راجع `docshare/services.py`
# (`submit_quote`) و`documents/purchase_docs.py` (`QUOTE_PURCHASE_RFQ`).

#: مفاتيح العرض في مواصفة التسعير — وحدها تخرج إلى الصفحة.
QUOTE_DISPLAY_KEYS = (
    "title", "hint", "price_label", "confirm_label",
    "submitted_note", "closed_note",
)

#: مواصفة تسعيرٍ كاملة = مفاتيح العرض + هذه. النقصُ يُخفِق `tests/test_registry.py`.
QUOTE_LOGIC_KEYS = ("is_open", "closed_reason", "apply", "entity_type", "entity_label")


def quote_display(spec, document):
    """جزءُ العرض من مواصفة التسعير + هل البابُ مفتوحٌ الآن — مرآةُ `decision_display`."""
    if spec is None:
        return None
    display = {key: spec[key] for key in QUOTE_DISPLAY_KEYS}
    display["open"] = bool(spec["is_open"](document))
    return display


# ── بطاقة الشركة ────────────────────────────────────────────────────────────

#: هوية الشركة كما تُطبع في ترويسة المستند — لا إعداداتها ولا فترتها المالية
#: ولا نسبها الافتراضية. هذه أيضاً قائمة بيضاء يقيسها اختبار التسريب.
COMPANY_FIELDS = (
    "company_name_primary", "company_name_sub", "address", "po_box",
    "phone", "fax", "email", "logo_url",
    "licensed_dealer_no", "income_tax_file_no",
)


def company_card(tenant) -> dict:
    """ترويسة المستند. شركة بلا صفّ إعدادات تُعرض باسمها المسجَّل لا فارغة."""
    tenant_settings = getattr(tenant, "settings", None)
    if tenant_settings is None:
        return {field: "" for field in COMPANY_FIELDS} | {
            "company_name_primary": tenant.CompanyName or "",
        }
    card = {
        field: (getattr(tenant_settings, field, None) or "")
        for field in COMPANY_FIELDS
    }
    if not card["company_name_primary"]:
        card["company_name_primary"] = tenant.CompanyName or ""
    return card
