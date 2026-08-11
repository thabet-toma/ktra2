_tax_period_guards = []


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
