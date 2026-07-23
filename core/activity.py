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

logger = logging.getLogger("core.activity")


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
