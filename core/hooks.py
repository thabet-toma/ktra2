_tax_period_guards = []
_serial_requirement_providers = []


def register_tax_period_guard(guard) -> None:
    """سجّل حارساً مرة واحدة، بما يلائم إعادة تحميل Django في التطوير."""
    if not callable(guard):
        raise TypeError("tax period guard must be callable")
    if guard not in _tax_period_guards:
        _tax_period_guards.append(guard)


def run_tax_period_guards(tenant_id, transaction_date) -> None:
    """شغّل الحرّاس المسجّلة؛ السجل الفارغ no-op حقيقي."""
    for guard in tuple(_tax_period_guards):
        guard(tenant_id, transaction_date)


def register_serial_requirement(provider) -> None:
    """سجّل مزوّداً — نمط `provider(tenant_id, product_ids) -> {product_id: سبب}` (#233).

    على نمط `register_tax_period_guard` حرفياً: تسجيلٌ مرّةً واحدة، بما يلائم
    إعادة تحميل جانغو في التطوير. يسجّله `after_sales` عند الإقلاع
    (`AppConfig.ready`)؛ لا استيراد لـ`after_sales` من `inventory`/`sales`/
    `logistics` — الربط من هنا وحده.
    """
    if not callable(provider):
        raise TypeError("serial requirement provider must be callable")
    if provider not in _serial_requirement_providers:
        _serial_requirement_providers.append(provider)


def serial_requirements(tenant_id, product_ids) -> dict:
    """يجمع كل المزوّدين المسجَّلين لمنتجات مستندٍ واحد — نداءٌ واحد للدفعة لا لكل بند.

    السجل الفارغ (لا مزوّد، أو لا معرّفات) يعيد قاموساً فارغاً بلا استعلام —
    نفس روح `run_tax_period_guards` الفارغة.
    """
    ids = [pid for pid in dict.fromkeys(product_ids) if pid]
    if not ids or not _serial_requirement_providers:
        return {}
    result: dict = {}
    for provider in tuple(_serial_requirement_providers):
        result.update(provider(tenant_id, ids) or {})
    return result
