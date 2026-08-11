"""
طبقة SQL آمنة للمساعد الذكي — text-to-SQL مع عزل شركة مضمون خادمياً.

الفكرة: النموذج يرى مخطط قاعدة كترا كاملاً ويكتب استعلام SELECT بحرية لأي سؤال،
والخادم **يحقن فلتر TenantID تلقائياً في كل جدول** عبر شجرة SQL (sqlglot) — فلا
يستطيع النموذج (ولا حقن أوامر عبر السؤال) رؤية بيانات شركة أخرى إطلاقاً، دون أن
يضطر النموذج للتفكير بالعزل.

ضمانات:
- قراءة فقط: SELECT/WITH فقط، وكلمات التعديل/DDL مرفوضة.
- عبارة واحدة فقط (لا `;` متعددة).
- حقن `TenantID = <شركة الجلسة>` لكل جدول مملوك لشركة في كل نطاق (scope) —
  الجداول العامة (العملات، وحدات القياس) لا تُفلتر لأنها مشتركة.
- سقف صفوف إلزامي.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

logger = logging.getLogger(__name__)

MAX_ROWS = 200

# التطبيقات التي يُعرض مخططها للنموذج (نستبعد جداول Django الداخلية).
_BUSINESS_APPS = {"sales", "inventory", "partners", "accounting", "logistics", "tenants"}

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|GRANT|REVOKE"
    r"|LOAD\s+DATA|INTO\s+OUTFILE|OUTFILE|DUMPFILE|EXEC|EXECUTE|CALL|XP_|SP_"
    r"|SLEEP|BENCHMARK|INFORMATION_SCHEMA|SHOW\s+DATABASES|SET\s|LOCK\s|HANDLER)\b",
    re.IGNORECASE,
)
_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

_tenant_tables_cache: set[str] | None = None
_business_tables_cache: set[str] | None = None
_catalog_cache: str | None = None


# ── مخطط ومجموعة الجداول المملوكة لشركة (من موديلات Django — دائماً محدّث) ──
def _iter_business_models():
    from django.apps import apps

    for model in apps.get_models():
        if model._meta.app_label in _BUSINESS_APPS and model._meta.managed:
            yield model


def tenant_scoped_tables() -> set[str]:
    """أسماء الجداول (lowercase) التي فيها عمود TenantID — تُفلتر إلزامياً."""
    global _tenant_tables_cache
    if _tenant_tables_cache is None:
        tables: set[str] = set()
        for model in _iter_business_models():
            for field in model._meta.concrete_fields:
                if getattr(field, "column", None) == "TenantID":
                    tables.add(model._meta.db_table.lower())
                    break
        _tenant_tables_cache = tables
    return _tenant_tables_cache


def business_tables() -> set[str]:
    """كل جداول الأعمال المسموح الاستعلام عنها (lowercase) — أي جدول آخر يُرفض."""
    global _business_tables_cache
    if _business_tables_cache is None:
        _business_tables_cache = {m._meta.db_table.lower() for m in _iter_business_models()}
    return _business_tables_cache


def schema_catalog() -> str:
    """كتالوج نصّي مضغوط لكل جداول الأعمال وأعمدتها — يُدرج في تعليمات النظام."""
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    lines: list[str] = []
    for model in sorted(_iter_business_models(), key=lambda m: m._meta.db_table):
        cols: list[str] = []
        for field in model._meta.concrete_fields:
            col = getattr(field, "column", None)
            if not col:
                continue
            if field.is_relation and field.related_model is not None:
                rel = field.related_model._meta.db_table
                cols.append(f"{col}→{rel}")
            elif getattr(field, "choices", None):
                vals = "|".join(str(c[0]) for c in field.choices)
                cols.append(f"{col}[{vals}]")
            else:
                cols.append(col)
        label = (model._meta.verbose_name or "").strip()
        head = f"{model._meta.db_table}" + (f" ({label})" if label else "")
        lines.append(f"- {head}: " + ", ".join(cols))
    _catalog_cache = "\n".join(lines)
    return _catalog_cache


def invalidate_caches() -> None:
    global _tenant_tables_cache, _business_tables_cache, _catalog_cache
    _tenant_tables_cache = None
    _business_tables_cache = None
    _catalog_cache = None


# ── التحقق والحقن ──────────────────────────────────────────────────────────
def _validate_readonly(sql: str) -> str | None:
    cleaned = sql.strip()
    if not cleaned:
        return "الاستعلام فارغ."
    if not _ALLOWED_START.match(cleaned):
        return "مسموح فقط بـ SELECT أو WITH … SELECT."
    # منع تعدّد العبارات (فاصلة منقوطة في المنتصف)
    if ";" in cleaned.rstrip(";"):
        return "عبارة واحدة فقط مسموحة (بدون ; متعددة)."
    m = _FORBIDDEN.search(cleaned)
    if m:
        return f"الكلمة «{m.group().strip()}» غير مسموحة في استعلام قراءة."
    return None


def inject_tenant(sql: str, tenant_id: int, dialect: str = "mysql") -> str:
    """
    يحقن TenantID = tenant_id لكل جدول مملوك لشركة في كل نطاق. يرفع ValueError
    عند فشل التحليل. `dialect` لهجة التحليل والإخراج (mysql للإنتاج، sqlite للاختبار).
    """
    tenant_tables = tenant_scoped_tables()
    allowed = business_tables()
    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"تعذّر تحليل الاستعلام: {exc}") from exc

    # رفض أي جدول خارج جداول الأعمال (يمنع auth_user وجداول Django الداخلية)
    for tbl in tree.find_all(exp.Table):
        if tbl.name and tbl.name.lower() not in allowed:
            raise ValueError(
                f"الجدول «{tbl.name}» غير متاح للاستعلام. استخدم جداول الأعمال المذكورة في المخطط فقط."
            )

    for scope in traverse_scope(tree):
        select = scope.expression
        if not isinstance(select, exp.Select):
            continue
        for alias, source in scope.sources.items():
            # المصادر التي هي جداول فيزيائية فقط (النطاقات الفرعية تُعالَج بذاتها)
            if isinstance(source, exp.Table):
                tname = source.name.lower()
                if tname in tenant_tables:
                    predicate = exp.column("TenantID", table=alias).eq(
                        exp.Literal.number(int(tenant_id))
                    )
                    select.where(predicate, copy=False)

    out = tree.sql(dialect=dialect)
    if not re.search(r"\bLIMIT\b", out, re.IGNORECASE):
        out = f"{out.rstrip(';')} LIMIT {MAX_ROWS}"
    return out


def _safe(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        # عدد صحيح كـ int، وإلا float — لتسلسل JSON (MySQL يرجع Decimal بعكس SQLite)
        return int(v) if v == v.to_integral_value() else float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return str(v)
    return v


def run_sql(tenant_id: int, query: str, max_rows: int = MAX_ROWS) -> dict:
    """
    ينفّذ استعلام قراءة بعد التحقق وحقن عزل الشركة. يعيد قاموساً قابلاً لتسلسل
    JSON: {columns, rows, count} أو {error}.
    """
    err = _validate_readonly(query or "")
    if err:
        return {"error": err}

    from django.db import connection

    dialect = "sqlite" if connection.vendor == "sqlite" else "mysql"
    try:
        safe_sql = inject_tenant(query, tenant_id, dialect=dialect)
    except ValueError as exc:
        return {"error": str(exc)}

    try:
        with connection.cursor() as cursor:
            cursor.execute(safe_sql)
            columns = [c[0] for c in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(max_rows)
        result = [[_safe(cell) for cell in row] for row in rows]
        logger.info("[assistant_sql] tenant=%s rows=%d sql=%s", tenant_id, len(result), safe_sql[:120])
        return {"columns": columns, "rows": result, "count": len(result), "executed_sql": safe_sql}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[assistant_sql] error tenant=%s: %s | sql=%s", tenant_id, exc, safe_sql[:200])
        return {"error": f"خطأ في تنفيذ الاستعلام: {exc}"}
