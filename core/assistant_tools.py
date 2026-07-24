"""
أدوات المساعد الذكي — قراءة فقط، مقفولة على شركة المستخدم (Tenant).

كل أداة تُنفَّذ عبر run_tool(name, arguments, tenant) حيث tenant كائن مُحلَّل
مسبقاً من المستدعي (core/assistant_views.py عبر get_tenant للويب، أو
core/whatsapp_views.py عبر WhatsAppContact لواتساب). لا تستقبل الأدوات
TenantID من النموذج إطلاقاً — العزل مفروض خادمياً، فيستحيل أن يرى المستخدم
بيانات شركة أخرى مهما كان نص السؤال.

النموذج (Qwen على Ollama) يختار الأداة ويعبّئ بارامتراتها فقط؛ لا يكتب SQL،
ولا يمرّر أي معرّف شركة.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

logger = logging.getLogger(__name__)

# حدّ أقصى لعدد المطابقات المُعادة عند البحث بالاسم — يمنع ردوداً ضخمة.
MAX_MATCHES = 15


# ── مواصفات الأدوات (صيغة OpenAI tools — يفهمها Ollama) ─────────────────────
# الأداة الرئيسية: run_sql — النموذج يكتب SELECT بحرية على مخطط كترا كاملاً،
# والخادم يحقن عزل الشركة تلقائياً (core/assistant_sql.py). الأدوات الضيقة أدناه
# تبقى في الكود للاختبارات لكنها غير معروضة للنموذج.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "ينفّذ استعلام SQL من نوع SELECT (قراءة فقط) على قاعدة بيانات كترا "
                "ويعيد الصفوف. استخدمه للإجابة عن أي سؤال عن بيانات الشركة: المبيعات، "
                "المشتريات، المخزون، الصفقات، الشركاء، القيود… النظام يحصر النتائج "
                "تلقائياً بشركة المستخدم الحالية، فلا تكتب أي فلتر TenantID بنفسك. "
                "استخدم أسماء الجداول والأعمدة كما في مخطط قاعدة البيانات المرفق في "
                "تعليمات النظام بالضبط."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "استعلام SELECT صالح بلهجة MySQL. مثال: SELECT Name FROM partners WHERE Name LIKE '%أشرف%'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_lesson",
            "description": (
                "يسجّل درساً سلوكياً عاماً للمساعد نفسه — استخدمه **فقط** عندما يصحّحك "
                "المستخدم صراحةً (يقول مثلاً «لأ هيك غلط، الصح كذا» أو «تذكّر هيك دائماً»)، "
                "وليس لتخمين أخطائك بنفسك. اكتب قاعدة عامة قابلة لإعادة الاستخدام مستقبلاً "
                "(مثل «لا تفترض عمود X على جدول Y» أو «استخدم LIKE لا = عند البحث بمقاس»)، "
                "**لا** تكتب أرقاماً أو أسماء أو بيانات خاصة بهذه الشركة تحديداً — الدرس "
                "يُشارَك مع كل الشركات. الدرس لا يؤثر فوراً؛ يُراجعه مسؤول قبل تفعيله."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lesson": {
                        "type": "string",
                        "description": "الدرس بجملة أو جملتين قصيرتين، عام وقابل لإعادة الاستخدام.",
                    }
                },
                "required": ["lesson"],
            },
        },
    },
]

# الأدوات الضيقة السابقة — محفوظة للاختبارات وإعادة الاستخدام، غير معروضة للنموذج.
_LEGACY_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "يبحث عن أصناف/منتجات بالاسم (عربي أو إنجليزي) أو رمز SKU أو الباركود، "
                "ويرجع الكمية المتوفرة حالياً (المتبقي في المخزون) ومتوسط التكلفة وقيمة "
                "المخزون لكل صنف مطابق. استخدمه للأسئلة مثل «كم باقٍ من صنف كذا» أو «شو "
                "المتوفر من المنتج الفلاني»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "نص البحث: جزء من اسم الصنف أو SKU أو الباركود.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sales_to_customer",
            "description": (
                "يجمع إجمالي المبيعات لعميل معيّن (فواتير البيع المرحّلة) مع صافي بعد "
                "مراجيع البيع، وعدد الفواتير، والمبلغ المدفوع والمتبقي. استخدمه لأسئلة "
                "مثل «كم بعنا لأشرف» أو «مبيعات العميل الفلاني هذا الشهر»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "string",
                        "description": "اسم العميل أو جزء منه.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "تاريخ البداية اختياري بصيغة YYYY-MM-DD.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "تاريخ النهاية اختياري بصيغة YYYY-MM-DD.",
                    },
                },
                "required": ["customer"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "purchases_from_supplier",
            "description": (
                "يجمع إجمالي المشتريات من مورد معيّن (فواتير الشراء المرحّلة) مع صافي بعد "
                "مراجيع الشراء، وعدد الفواتير، والمبلغ المدفوع والمتبقي. استخدمه لأسئلة "
                "مثل «شو اشترينا من المورد الفلاني» أو «مشترياتنا من فلان»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier": {
                        "type": "string",
                        "description": "اسم المورد أو جزء منه.",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "تاريخ البداية اختياري بصيغة YYYY-MM-DD.",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "تاريخ النهاية اختياري بصيغة YYYY-MM-DD.",
                    },
                },
                "required": ["supplier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_partners",
            "description": (
                "يبحث عن شركاء (عملاء/موردين/وكلاء) بالاسم عند وجود التباس أو للتأكد من "
                "الاسم الصحيح قبل جمع المبيعات/المشتريات. يرجع الاسم والنوع."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "جزء من اسم الشريك.",
                    },
                    "role": {
                        "type": "string",
                        "enum": ["customer", "supplier", "any"],
                        "description": "تصفية اختيارية: عميل أو مورد أو الكل.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ── أدوات مساعدة ───────────────────────────────────────────────────────────
def _f(value, places: int = 2) -> float:
    """تحويل Decimal/None إلى float مقرّب — لتسلسل JSON بلا ضوضاء عشرية."""
    if value is None:
        return 0.0
    return round(float(value), places)


def _base_currency_code(default: str = "") -> str:
    """رمز العملة الأساسية للنظام — يُذكر في المخرجات كي لا يخمّن النموذج وحدة خاطئة."""
    from tenants.models import Currency

    cur = Currency.objects.filter(IsBaseCurrency=True).only("Code").first()
    return cur.Code if cur and cur.Code else default


def _parse_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except (ValueError, TypeError):
        return None


def _match_partners(tenant, query: str, role: str = "any"):
    from partners.models import Partner

    qs = Partner.objects.filter(tenant=tenant, name__icontains=(query or "").strip())
    role = (role or "any").lower()
    if role == "customer":
        qs = qs.filter(partner_type__in=["Customer", "customer"])
    elif role == "supplier":
        qs = qs.filter(partner_type__in=["Supplier", "supplier"])
    return list(qs.only("id", "name", "partner_type")[: MAX_MATCHES + 1])


def _invoice_totals(tenant, partner, kind: str, return_kind: str, date_from, date_to):
    """صافي إجمالي فواتير مرحّلة لطرف حسب النوع (بيع/شراء) بعد المراجيع."""
    from sales.models import SalesInvoice

    base = SalesInvoice.objects.filter(
        tenant=tenant, customer=partner, status=SalesInvoice.STATUS_POSTED
    )
    if date_from:
        base = base.filter(invoice_date__gte=date_from)
    if date_to:
        base = base.filter(invoice_date__lte=date_to)

    main = base.filter(invoice_kind=kind).aggregate(
        total=Sum("grand_total"), paid=Sum("amount_paid"), n=Count("id")
    )
    ret = base.filter(invoice_kind=return_kind).aggregate(
        total=Sum("grand_total"), n=Count("id")
    )
    gross = main["total"] or Decimal("0")
    returns = ret["total"] or Decimal("0")
    paid = main["paid"] or Decimal("0")
    net = gross - returns
    return {
        "currency": _base_currency_code(),
        "gross_total": _f(gross),
        "returns_total": _f(returns),
        "net_total": _f(net),
        "amount_paid": _f(paid),
        "outstanding": _f(net - paid),
        "invoice_count": int(main["n"] or 0),
        "return_count": int(ret["n"] or 0),
    }


# ── الأدوات ────────────────────────────────────────────────────────────────
def search_products(tenant, *, query: str = "", **_):
    from django.db.models import Q

    from inventory.models import Product

    q = (query or "").strip()
    if not q:
        return {"error": "أدخل نص بحث للصنف."}

    # مطابقة على الاسم العربي/الإنجليزي أو الرمز أو الباركود
    qs = Product.objects.filter(tenant=tenant).filter(
        Q(name_ar__icontains=q)
        | Q(name_en__icontains=q)
        | Q(sku__icontains=q)
        | Q(barcode__icontains=q)
    ).only("id", "sku", "name_ar", "name_en", "quantity_on_hand", "avg_cost")[: MAX_MATCHES + 1]

    rows = list(qs)
    truncated = len(rows) > MAX_MATCHES
    items = []
    for p in rows[:MAX_MATCHES]:
        on_hand = Decimal(str(p.quantity_on_hand or 0))
        avg = Decimal(str(p.avg_cost or 0))
        items.append(
            {
                "sku": p.sku,
                "name": p.name_ar or p.name_en or p.sku,
                "quantity_on_hand": _f(on_hand, 4),
                "avg_cost": _f(avg, 4),
                "inventory_value": _f(on_hand * avg),
            }
        )
    if not items:
        return {"matches": [], "note": f"لا يوجد صنف مطابق لـ «{q}» في هذه الشركة."}
    return {
        "count": len(items),
        "truncated": truncated,
        "currency": _base_currency_code(),
        "matches": items,
    }


def sales_to_customer(tenant, *, customer: str = "", date_from=None, date_to=None, **_):
    matches = _match_partners(tenant, customer, role="customer")
    if not matches:
        # قد يكون النوع غير مضبوط — جرّب أي طرف بالاسم
        matches = _match_partners(tenant, customer, role="any")
    if not matches:
        return {"note": f"لا يوجد عميل باسم «{customer}» في هذه الشركة."}
    if len(matches) > 1:
        return {
            "ambiguous": True,
            "note": "أكثر من طرف يطابق الاسم — اطلب من المستخدم التحديد.",
            "candidates": [
                {"name": p.name, "type": p.partner_type} for p in matches[:MAX_MATCHES]
            ],
        }
    partner = matches[0]
    totals = _invoice_totals(
        tenant,
        partner,
        kind="sale",
        return_kind="sale_return",
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
    )
    return {"customer": partner.name, **totals}


def purchases_from_supplier(tenant, *, supplier: str = "", date_from=None, date_to=None, **_):
    matches = _match_partners(tenant, supplier, role="supplier")
    if not matches:
        matches = _match_partners(tenant, supplier, role="any")
    if not matches:
        return {"note": f"لا يوجد مورد باسم «{supplier}» في هذه الشركة."}
    if len(matches) > 1:
        return {
            "ambiguous": True,
            "note": "أكثر من طرف يطابق الاسم — اطلب من المستخدم التحديد.",
            "candidates": [
                {"name": p.name, "type": p.partner_type} for p in matches[:MAX_MATCHES]
            ],
        }
    partner = matches[0]
    totals = _invoice_totals(
        tenant,
        partner,
        kind="purchase",
        return_kind="purchase_return",
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
    )
    return {"supplier": partner.name, **totals}


def search_partners(tenant, *, query: str = "", role: str = "any", **_):
    matches = _match_partners(tenant, query, role=role)
    if not matches:
        return {"matches": [], "note": f"لا يوجد شريك مطابق لـ «{query}»."}
    return {
        "count": min(len(matches), MAX_MATCHES),
        "truncated": len(matches) > MAX_MATCHES,
        "matches": [
            {"name": p.name, "type": p.partner_type} for p in matches[:MAX_MATCHES]
        ],
    }


def run_sql(tenant, *, query: str = "", **_):
    """أداة text-to-SQL — تفوّض لطبقة SQL الآمنة التي تحقن عزل الشركة."""
    from core.assistant_sql import run_sql as _run

    return _run(tenant.pk, query or "")


MAX_LESSON_LEN = 500


def remember_lesson(tenant, *, lesson: str = "", session_key: str = "", **_):
    """
    يسجّل درساً بحالة غير مفعَّلة (is_active=False) — لا يؤثر على أي محادثة
    حتى يراجعه أدمن ويفعّله من /admin/. tenant غير مستخدَم لعزل بيانات (لا
    يوجد شركة لهذا الجدول عمداً)، فقط لتتبّع مصدر الدرس اختيارياً.
    """
    from core.models import AssistantLesson

    text = (lesson or "").strip()
    if not text:
        return {"error": "الدرس فارغ."}
    text = text[:MAX_LESSON_LEN]
    AssistantLesson.objects.create(text=text, source=session_key or "")
    return {"saved": True, "note": "سُجّل الدرس وينتظر مراجعة أدمن قبل التفعيل."}


_DISPATCH = {
    "run_sql": run_sql,
    "remember_lesson": remember_lesson,
    # أدوات ضيقة (غير معروضة للنموذج، تُستخدم في الاختبارات):
    "search_products": search_products,
    "sales_to_customer": sales_to_customer,
    "purchases_from_supplier": purchases_from_supplier,
    "search_partners": search_partners,
}


def run_tool(name: str, arguments: dict, tenant, session_key: str = "") -> dict:
    """
    ينفّذ أداة واحدة بأمان لصالح `tenant` (كائن Tenant مُحلَّل مسبقاً من المستدعي
    — عبر get_tenant() لمسار الويب، أو عبر WhatsAppContact لمسار واتساب).
    run_tool نفسه لا يحلّ الشركة ولا يقبلها كنص/رقم من النموذج، فيستحيل أن يرى
    المستخدم بيانات شركة أخرى مهما كان نص السؤال. يُعيد قاموساً قابلاً لتسلسل JSON.
    `session_key` سياق خادمي فقط (لتتبّع مصدر remember_lesson) — يُفرض هنا لا
    يُقبل من النموذج، حتى لو حاول تمريره ضمن arguments.
    """
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"أداة غير معروفة: {name}"}

    args = dict(arguments) if isinstance(arguments, dict) else {}
    args.pop("session_key", None)  # وارد من الخادم حصراً — لا نثق بالنموذج فيه
    try:
        return fn(tenant, session_key=session_key, **args)
    except TypeError as exc:
        logger.warning("assistant tool %s bad args %s: %s", name, args, exc)
        return {"error": f"بارامترات غير صحيحة للأداة {name}."}
    except Exception as exc:  # noqa: BLE001 — لا نُسرّب استثناءً للنموذج
        logger.exception("assistant tool %s failed", name)
        return {"error": f"تعذّر تنفيذ الأداة {name}: {exc}"}
