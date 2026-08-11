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

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce

logger = logging.getLogger("core.reports")


DEC = Decimal("0.01")
ZERO = Decimal("0")

# ── فئات التقارير (ترتيب العرض في الفهرس) ─────────────────────────────
CATEGORIES: list[tuple[str, str]] = [
    ("sales", "المبيعات"),
    ("purchases", "المشتريات"),
    ("partners", "العملاء والموردون"),
    ("inventory", "المخزون"),
    ("finance", "المالية والنقدية"),
    ("accounting", "المحاسبة"),
    ("import", "الاستيراد"),
    ("hr", "الموارد البشرية"),
]

# أنواع الأعمدة التي تفهمها الواجهة: text | money | number | int | date | badge
KIND_MONEY = "money"
KIND_NUMBER = "number"
KIND_INT = "int"
KIND_DATE = "date"
KIND_TEXT = "text"


@dataclass(frozen=True)
class ReportColumn:
    key: str
    header: str
    kind: str = KIND_TEXT
    #: يُجمع في سطر الإجمالي أسفل الجدول
    total: bool = False
    width: str | None = None


@dataclass(frozen=True)
class ReportFilter:
    key: str
    label: str
    #: date | partner | customer | supplier | product | warehouse | select | text
    kind: str
    options: tuple[tuple[str, str], ...] = ()
    default: str | None = None


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    category: str
    description: str
    columns: tuple[ReportColumn, ...]
    build: Callable[[int, dict], list[dict]]
    filters: tuple[ReportFilter, ...] = ()
    permission: str | None = None
    #: تقرير له شاشة مخصّصة قائمة — الفهرس يقود إليها بدل الجدول العام
    screen_path: str | None = None
    #: مسار المستند خلف السطر، بقوالب من مفاتيح الصف — «/sales/invoices/{id}».
    #: وجوده يجعل السطر قابلاً للفتح في الشاشة العامّة (لا شاشة تعرف مستنداتها).
    row_link: str | None = None


REPORTS: dict[str, ReportSpec] = {}


def register(spec: ReportSpec) -> ReportSpec:
    if spec.key in REPORTS:
        raise ValueError(f"تقرير مكرر: {spec.key}")
    REPORTS[spec.key] = spec
    return spec


# ── أدوات مشتركة ──────────────────────────────────────────────────────

DATE_FILTERS = (
    ReportFilter("from", "من تاريخ", "date"),
    ReportFilter("to", "إلى تاريخ", "date"),
)


def _parse_date(value) -> datetime.date | None:
    from django.utils.dateparse import parse_date

    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    return parse_date(str(value))


def _date_range(params: dict) -> tuple[datetime.date | None, datetime.date | None]:
    return _parse_date(params.get("from")), _parse_date(params.get("to"))


def _apply_dates(qs, field_name: str, params: dict):
    start, end = _date_range(params)
    if start:
        qs = qs.filter(**{f"{field_name}__gte": start})
    if end:
        qs = qs.filter(**{f"{field_name}__lte": end})
    return qs


def _int_param(params: dict, key: str) -> int | None:
    raw = params.get(key)
    return int(raw) if raw not in (None, "") and str(raw).isdigit() else None


def _money(value) -> str:
    """مبلغ نصّي بقرشين — مصدر واحد لتنسيق المال في كل التقارير."""
    return str(Decimal(str(value or 0)).quantize(DEC))


def _qty(value) -> str:
    """كمية بلا أصفار زائدة — الكميات كسرية أحياناً والقطع صحيحة غالباً."""
    dec = Decimal(str(value or 0)).normalize()
    return format(dec, "f")


def _sum(rows: list[dict], key: str) -> str:
    return _money(sum((Decimal(str(r.get(key) or 0)) for r in rows), ZERO))


def _money_sum(field_name: str):
    return Coalesce(
        Sum(field_name), Value(ZERO), output_field=DecimalField(max_digits=20, decimal_places=4),
    )


def compute_totals(spec: ReportSpec, rows: list[dict]) -> dict[str, str]:
    """سطر الإجمالي من الأعمدة الموسومة `total=True` — لا حساب يدوي لكل تقرير."""
    totals: dict[str, str] = {}
    for col in spec.columns:
        if not col.total:
            continue
        acc = sum((Decimal(str(r.get(col.key) or 0)) for r in rows), ZERO)
        totals[col.key] = _money(acc) if col.kind == KIND_MONEY else _qty(acc)
    return totals


def report_catalog() -> list[dict]:
    """الفهرس مرتَّباً بالفئات — يستهلكه `ReportsHubPage`."""
    by_category: dict[str, list[dict]] = {}
    for spec in REPORTS.values():
        by_category.setdefault(spec.category, []).append({
            "key": spec.key,
            "title": spec.title,
            "description": spec.description,
            "permission": spec.permission,
            "screen_path": spec.screen_path,
            "row_link": spec.row_link,
            "filters": [
                {
                    "key": f.key, "label": f.label, "kind": f.kind,
                    "options": [{"value": v, "label": l} for v, l in f.options],
                    "default": f.default,
                }
                for f in spec.filters
            ],
            "columns": [
                {"key": c.key, "header": c.header, "kind": c.kind,
                 "total": c.total, "width": c.width}
                for c in spec.columns
            ],
        })
    out = []
    for key, label in CATEGORIES:
        reports = sorted(by_category.get(key, []), key=lambda r: r["title"])
        if reports:
            out.append({"key": key, "label": label, "reports": reports})
    return out


#: سقف الصفوف المُرسَلة للمتصفح. دفتر يوميةٍ لشركةٍ عاملة يتجاوز 30 ألف سطر،
#: ورسمها كلها يُجمّد التبويب. الإجماليات تُحسب على الصفوف كاملةً قبل القصّ —
#: فالمعروض ينقص، والمجموع لا يكذب.
MAX_ROWS = 5000


def run_report(key: str, tenant_id: int, params: dict) -> dict:
    """ينفّذ تقريراً ويُعيد الحمولة الكاملة (أعمدة + صفوف + إجماليات)."""
    spec = REPORTS[key]
    rows = spec.build(tenant_id, params or {})
    total_rows = len(rows)
    totals = compute_totals(spec, rows)
    truncated = total_rows > MAX_ROWS
    if truncated:
        rows = rows[:MAX_ROWS]
    logger.info(
        "reports.run key=%s tenant=%s rows=%s truncated=%s params=%s",
        key, tenant_id, total_rows, truncated,
        {k: v for k, v in (params or {}).items() if v},
    )
    return {
        "key": spec.key,
        "title": spec.title,
        "category": spec.category,
        "description": spec.description,
        "row_link": spec.row_link,
        "columns": [
            {"key": c.key, "header": c.header, "kind": c.kind,
             "total": c.total, "width": c.width}
            for c in spec.columns
        ],
        "rows": rows,
        "totals": totals,
        "total_rows": total_rows,
        "truncated": truncated,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


# ══════════════════════════════════════════════════════════════════════
#  المبيعات
# ══════════════════════════════════════════════════════════════════════

