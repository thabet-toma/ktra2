"""طبقة تسجيل النشاط المشتركة (Shared/Core).

نقطة كتابة **وحيدة** لسجل النشاط عبر الموقع. آمنة/غير حاظرة: أي فشل يُبتلع
ويُسجَّل في اللوج ولا يعطّل الطلب الأصلي إطلاقاً (بروتوكول Safe Logging).

الاستخدام:
    from core.activity import log_activity, log_view
    log_activity(action='post', entity_type='sales_invoice',
                 entity_id=inv.id, entity_label=inv.invoice_number,
                 description='ترحيل فاتورة مبيعات')
"""
import logging
from datetime import date, datetime
from decimal import Decimal

logger = logging.getLogger("core.activity")


def _activity_value(value) -> str:
    """حوّل قيمة حقل إلى تمثيل ثابت وآمن للتخزين في JSON."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    if isinstance(value, Decimal):
        # G1: بلا أصفار زائدة — «150.5» لا «150.5000» في نصّ السجل.
        return format(value.normalize(), "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def snapshot_fields(instance, fields) -> dict:
    """لقطة حقول ترويسة قبل/بعد الحفظ — تفضّل التسمية المعروضة على القيمة الخام."""
    values = {}
    for field in fields:
        display = getattr(instance, f"get_{field}_display", None)
        values[field] = display() if callable(display) else getattr(instance, field, None)
    return values


def snapshot_document_lines(lines, *, label, fields, key: str = "product_id") -> list[dict]:
    """لقطة بنود مستند قابلة للمقارنة — تُلتقط قبل الحفظ وبعده.

    هوية البند = قيمة `key` + ترتيب تكرارها، كي يبقى المنتج المكرَّر سطرين
    متمايزين بدل أن يبتلع أحدهما الآخر. `label` دالة تُعيد اسم البند المعروض.
    """
    rows: list[dict] = []
    seen: dict = {}
    for line in lines:
        raw_key = getattr(line, key, None)
        seen[raw_key] = seen.get(raw_key, 0) + 1
        row = {"key": f"{raw_key}#{seen[raw_key]}", "label": label(line)}
        row.update({field: _activity_value(getattr(line, field, None)) for field in fields})
        rows.append(row)
    return rows


def _line_values(row: dict, labels: dict) -> list[dict]:
    """قيم البند المضاف/المحذوف — بلا الفارغ ولا الصفر (خصم 0 ضجيج لا معلومة)."""
    return [
        {"label": label, "value": row.get(field, "")}
        for field, label in labels.items() if (row.get(field) or "") not in ("", "0")
    ]


def build_line_changes(*, before: list[dict], after: list[dict], labels: dict) -> list[dict]:
    """فروقات بنود المستند: بند مضاف / بند محذوف / حقل تغيّر داخل بند."""
    before_keys = {row["key"] for row in before}
    after_map = {row["key"]: row for row in after}
    changes: list[dict] = []
    for row in before:
        new_row = after_map.get(row["key"])
        if new_row is None:
            changes.append({
                "kind": "line_removed",
                "label": row["label"],
                "values": _line_values(row, labels),
            })
            continue
        field_changes = [
            {"field": field, "label": label,
             "old": row.get(field, ""), "new": new_row.get(field, "")}
            for field, label in labels.items()
            if row.get(field, "") != new_row.get(field, "")
        ]
        if field_changes:
            changes.append({
                "kind": "line_changed",
                "label": new_row["label"],
                "changes": field_changes,
            })
    for row in after:
        if row["key"] not in before_keys:
            changes.append({
                "kind": "line_added",
                "label": row["label"],
                "values": _line_values(row, labels),
            })
    return changes


def build_header_snapshot_changes(header: dict, labels: dict) -> list[dict]:
    """حقول ترويسة مستندٍ أُنشئ أو حُذف — قيمةٌ واحدة لا «من ← إلى».

    الإنشاء والحذف ليسا فرقاً بين حالتين: لا قيمة قديمة في الأول ولا جديدة في
    الثاني. فالنوع `field_set` يعرض القيمة وحدها بدل «— ← أحمد» التي تُقرأ خطأً
    على أنها تعديل. الفارغ يُسقط: حقلٌ لم يُملأ ليس معلومة.
    """
    changes = []
    for field, label in labels.items():
        value = _activity_value(header.get(field))
        if value in ("", "0"):
            continue
        changes.append({"kind": "field_set", "field": field, "label": label, "new": value})
    return changes


def build_document_snapshot_changes(
    *, header: dict, lines: list[dict], labels: dict, line_labels: dict, removed: bool = False,
) -> list[dict]:
    """لقطة مستند كامل كقائمة فروقات — للإنشاء (كلّه جديد) أو للحذف (كلّه زال).

    البنود تمرّ بـ`build_line_changes` نفسها بلقطةٍ فارغة على الطرف المقابل، فلا
    تُكتب قواعد المقارنة مرتين ولا تتباعد نسختاها لاحقاً.
    """
    empty: list[dict] = []
    line_changes = (
        build_line_changes(before=lines, after=empty, labels=line_labels)
        if removed
        else build_line_changes(before=empty, after=lines, labels=line_labels)
    )
    return build_header_snapshot_changes(header, labels) + line_changes


def _values_suffix(change: dict) -> str:
    values = change.get("values") or []
    if not values:
        return ""
    return " (" + " · ".join(f'{v["label"]} {v["value"]}' for v in values) + ")"


def describe_activity_changes(changes: list[dict]) -> str:
    """يحوّل الفروقات إلى جملة عربية واحدة تُقرأ في سجل النشاط وتقبل البحث."""
    parts = []
    for change in changes:
        kind = change.get("kind", "field")
        if kind == "field_set":
            parts.append(f'{change["label"]}: {change["new"]}')
        elif kind == "line_added":
            parts.append(f'أضاف منتج «{change["label"]}»{_values_suffix(change)}')
        elif kind == "line_removed":
            parts.append(f'حذف منتج «{change["label"]}»{_values_suffix(change)}')
        elif kind == "line_changed":
            inner = "، ".join(
                f'{c["label"]} من {c["old"] or "—"} إلى {c["new"] or "—"}'
                for c in change["changes"]
            )
            parts.append(f'«{change["label"]}»: {inner}')
        else:
            parts.append(
                f'{change["label"]} من «{change["old"]}» إلى «{change["new"]}»')
    return "؛ ".join(parts)


def build_activity_changes(*, before: dict, after: dict, labels: dict) -> list[dict]:
    """أنشئ فروقات حقول مقروءة مع تجاهل القيم التي لم تتغيّر فعلياً."""
    changes = []
    for field, label in labels.items():
        old_value = _activity_value(before.get(field))
        new_value = _activity_value(after.get(field))
        if old_value == new_value:
            continue
        changes.append({
            "field": field,
            "label": label,
            "old": old_value,
            "new": new_value,
        })
    return changes


def _client_ip(request) -> str | None:
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.META.get("REMOTE_ADDR") or None)


def log_activity(
    *,
    action: str,
    entity_type: str,
    entity_id=None,
    entity_label: str = "",
    description: str = "",
    metadata: dict | None = None,
    partner_ids=None,
    request=None,
    tenant=None,
    user=None,
    is_view: bool = False,
) -> None:
    """يسجّل حدثاً واحداً. لا يرمي أبداً.

    يحلّ الطلب/الشركة/المستخدم/الـ IP تلقائياً عند عدم تمريرها.
    """
    try:
        from core.models import ActivityLog, ActivityLogPartner
        from core.tenant_utils import get_tenant
        from core.logger_middleware import get_current_request

        if request is None:
            request = get_current_request()
        if tenant is None:
            tenant = get_tenant(request)
        if tenant is None:
            # بلا شركة لا يمكن ربط الحدث بأمان — نتجاهل بصمت.
            return
        if user is None and request is not None:
            u = getattr(request, "user", None)
            if u is not None and getattr(u, "is_authenticated", False):
                user = u

        from django.db import transaction

        # Savepoint: لو فشل الإدراج داخل معاملة المتصل، يتراجع المخفظ (savepoint)
        # فقط دون كسر معاملته الأصلية — التسجيل يبقى غير حاظر تماماً.
        with transaction.atomic():
            activity = ActivityLog.objects.create(
                tenant=tenant,
                user=user,
                action=action,
                is_view=is_view,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_label=(entity_label or "")[:200],
                description=description or "",
                metadata=metadata or {},
                ip_address=_client_ip(request),
            )
            requested_partner_ids = set(partner_ids or [])
            if requested_partner_ids:
                from partners.models import Partner

                valid_partner_ids = Partner.objects.filter(
                    tenant=tenant, id__in=requested_partner_ids,
                ).values_list("id", flat=True)
                ActivityLogPartner.objects.bulk_create(
                    [
                        ActivityLogPartner(activity=activity, partner_id=partner_id)
                        for partner_id in valid_partner_ids
                    ],
                    ignore_conflicts=True,
                )
    except Exception:  # noqa: BLE001 — التسجيل لا يعطّل الطلب أبداً
        logger.exception("log_activity failed (action=%s entity=%s#%s)", action, entity_type, entity_id)


def log_view(*, entity_type: str, entity_id=None, entity_label: str = "", request=None, tenant=None, user=None) -> None:
    """غلاف مختصر لحدث عرض/فتح مستند (is_view=True)."""
    log_activity(
        action="view",
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        description="فتح/عرض",
        request=request,
        tenant=tenant,
        user=user,
        is_view=True,
    )
