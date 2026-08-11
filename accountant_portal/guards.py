"""حارس قفل الفترة الضريبية — يُسجَّل في `core.hooks` ويُنادى من نقطة الاختناق
الوحيدة لكل قيد (`accounting.services.post_journal`).

R2: أول سطر بوليان مكيَّش؛ الشركة غير المرخّصة للوحدة تخرج بلا أي استعلام.
"""
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date


LOCKED_PERIOD_MESSAGE = (
    "الفترة الضريبية مقفلة بعد تقديم الإقرار — لا ترحيل ولا إلغاء ترحيل بتاريخ داخلها."
)


def _as_date(value):
    if hasattr(value, "year") and hasattr(value, "month"):
        return value
    return parse_date(str(value))


def tax_period_lock_guard(tenant_id, transaction_date):
    from core.modules import module_enabled

    if not module_enabled(tenant_id, "accountant_portal"):
        return

    from accountant_portal.models import PortalSettings, TaxPeriodReview

    transaction_date = _as_date(transaction_date)
    if transaction_date is None:
        return
    locked = TaxPeriodReview.objects.filter(
        tenant_id=tenant_id,
        status="locked",
        period_from__lte=transaction_date,
        period_to__gte=transaction_date,
    ).exists()
    if not locked:
        return
    # ق11 — للشركة أن تسمح بالترحيل داخل فترة مقفلة، والافتراض المنع.
    blocks = PortalSettings.objects.filter(tenant_id=tenant_id).values_list(
        "lock_blocks_posting", flat=True,
    ).first()
    if blocks is False:
        return
    raise ValidationError(LOCKED_PERIOD_MESSAGE)


def register_guards():
    from core.hooks import register_tax_period_guard

    register_tax_period_guard(tax_period_lock_guard)
