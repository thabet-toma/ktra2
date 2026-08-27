from django.core.cache import cache
from django.http import Http404

from core.logger_middleware import get_current_request
from core.models import TenantModule


MODULES = {
    "accountant_portal": {
        "label": "بوابة المحاسب القانوني الخارجي",
        "plans": ("Pro", "Enterprise"),
        "legacy_flag": None,
    },
    "after_sales": {
        "label": "خدمة ما بعد البيع",
        "plans": ("Pro", "Enterprise"),
        "legacy_flag": None,
    },
    "hr_suite": {
        "label": "الموارد البشرية — الحضور والورديات والعقود والطلبات",
        "plans": ("Pro", "Enterprise"),
        "legacy_flag": None,
    },
    "import": {
        "label": "الاستيراد والشحن والتخليص",
        "plans": ("Enterprise",),
        "legacy_flag": "import_enabled",
    },
    "import_file": {
        "label": "ملف الاستيراد",
        "plans": ("Enterprise",),
        "legacy_flag": None,
    },
    "sensitive_devices": {
        "label": "تسجيل وتتبع الأجهزة الحساسة",
        "plans": ("Pro", "Enterprise"),
        "legacy_flag": None,
    },
}

_REQUEST_CACHE_ATTR = "_tenant_module_enabled"
_CACHE_TTL_SECONDS = 300


def _tenant_id(tenant):
    """يقبل كائن الشركة أو معرّفها — الحارس في مسار الترحيل لا يملك إلا المعرّف."""
    if tenant is None:
        return None
    if isinstance(tenant, int):
        return tenant
    return getattr(tenant, "pk", None)


def _shared_cache_key(tenant_id):
    return f"modules:{tenant_id}"


def _request_cache(request):
    values = getattr(request, _REQUEST_CACHE_ATTR, None)
    if values is None:
        values = {}
        setattr(request, _REQUEST_CACHE_ATTR, values)
    return values


def module_enabled(tenant, key: str) -> bool:
    """مصدر الحقيقة الواحد لترخيص الوحدات على مستوى الشركة."""
    definition = MODULES.get(key)
    tenant_id = _tenant_id(tenant)
    if definition is None or tenant_id is None:
        return False

    legacy_flag = definition["legacy_flag"]
    if legacy_flag:
        if not hasattr(tenant, legacy_flag):
            from tenants.models import Tenant

            tenant = Tenant.objects.filter(pk=tenant_id).only(legacy_flag).first()
        return bool(getattr(tenant, legacy_flag, False))

    request = get_current_request()
    request_values = _request_cache(request) if request is not None else None
    if request_values is not None and tenant_id in request_values:
        return key in request_values[tenant_id]

    cache_key = _shared_cache_key(tenant_id)
    enabled_keys = cache.get(cache_key)
    if enabled_keys is None:
        enabled_keys = tuple(
            TenantModule.objects.filter(tenant_id=tenant_id, enabled=True)
            .values_list("module_key", flat=True)
        )
        cache.set(cache_key, enabled_keys, timeout=_CACHE_TTL_SECONDS)

    enabled_keys = frozenset(enabled_keys)
    if request_values is not None:
        request_values[tenant_id] = enabled_keys
    return key in enabled_keys


def invalidate_module_cache(tenant_id, request=None) -> None:
    """أبطل الكاش المشترك وكاش الطلب الحالي بعد أي تبديل."""
    cache.delete(_shared_cache_key(tenant_id))
    current_request = request if request is not None else get_current_request()
    if current_request is None:
        return
    values = getattr(current_request, _REQUEST_CACHE_ATTR, None)
    if values is not None:
        values.pop(tenant_id, None)


def guard_module_surface(request, key: str) -> None:
    """أخفِ سطح الوحدة كاملاً عن شركة غير مرخّصة، حتى في المسارات غير المرتبطة بشركة.

    المسارات الهوياتية (تسجيل/تحقق بريد) تعمل بلا `X-Tenant-Id`؛ فإن أُرسل الهيدر
    فالطلب داخل سياق شركة، ويجب أن يختفي المسار إن لم تكن الوحدة مرخّصة لها.
    """
    if request.headers.get("X-Tenant-Id") or request.META.get("HTTP_X_TENANT_ID"):
        require_module(request, key)


def require_module(request, key: str):
    """أخفِ الوحدة غير المرخّصة كمسار غير موجود لمنع كشفها."""
    from django.core.exceptions import PermissionDenied
    from core.tenant_utils import get_tenant

    try:
        tenant = get_tenant(request)
    except PermissionDenied:
        if key == "accountant_portal":
            raise Http404 from None
        raise
    if not module_enabled(tenant, key):
        raise Http404
    return tenant
