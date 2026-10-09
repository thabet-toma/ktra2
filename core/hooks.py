_tax_period_guards = []
_serial_requirement_providers = []
_purchase_line_extensions = {}
_purchase_line_cost_providers = []


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


def register_purchase_line_extension(key, read, write) -> None:
    """سجّل امتداداً لسطر فاتورة الشراء — قراءةٌ وكتابةٌ تحت مفتاح `key` (#235).

    - `read(tenant_id, items) -> {item_id: payload}`: نداءٌ واحد لكل فاتورة لا لكل بند.
    - `write(tenant_id, item, payload, user)`: يُنادى داخل معاملة حفظ الفاتورة؛
      رفعُه لخطأ تحقّق يُسقط الحفظ كلَّه.

    على نمط `register_serial_requirement`: يسجّله `after_sales` عند الإقلاع، ولا
    يعرف `logistics` اسمَ الامتداد ولا مضمونه — الحمولة تصل تحت
    `extensions[key]` وتعود منها.
    """
    if not callable(read) or not callable(write):
        raise TypeError("purchase line extension read/write must be callable")
    _purchase_line_extensions[key] = (read, write)


def purchase_line_extension_reads(tenant_id, items) -> dict:
    """يجمع قراءات كل الامتدادات لبنود فاتورةٍ واحدة: `{item_id: {key: payload}}`.

    السجل الفارغ أو لا بنود ⇒ قاموسٌ فارغ بلا استعلام.
    """
    items = list(items)
    if not items or not _purchase_line_extensions:
        return {}
    result: dict = {}
    for key, (read, _write) in tuple(_purchase_line_extensions.items()):
        for item_id, payload in (read(tenant_id, items) or {}).items():
            result.setdefault(item_id, {})[key] = payload
    return result


def write_purchase_line_extensions(tenant_id, item, extensions, user) -> None:
    """يمرّر حمولة كل امتدادٍ مسجَّل وردت في `extensions` إلى كاتبه.

    مفتاحٌ غائب عن الحمولة لا يُنادى كاتبُه — فلا يُمسّ صفٌّ قائم بحفظٍ لا يذكره،
    ومفتاحٌ غير مسجَّل يُهمل.
    """
    if not extensions or not _purchase_line_extensions:
        return
    for key, (_read, write) in tuple(_purchase_line_extensions.items()):
        if key in extensions:
            write(tenant_id, item, extensions[key], user)


def register_purchase_line_cost_provider(provider) -> None:
    """سجّل مزوّد تكلفة بنود فاتورة الشراء — `provider(invoice) -> {item_id: تكلفة} | None`.

    على نمط `register_serial_requirement`: يسجّله `logistics` عند الإقلاع
    (`AppConfig.ready`) بـ`posted_goods_line_costs`، فيسأل `inventory` عن تكلفة بنود
    الفاتورة الدولية المرحّلة دون أن يستورد `logistics` (عقد import-linter 3).
    """
    if not callable(provider):
        raise TypeError("purchase line cost provider must be callable")
    if provider not in _purchase_line_cost_providers:
        _purchase_line_cost_providers.append(provider)


def purchase_line_costs(invoice):
    """أول جوابٍ غير None من المزوّدين المسجَّلين — أو None (لا مزوّد، أو لا يخصّه)."""
    for provider in tuple(_purchase_line_cost_providers):
        costs = provider(invoice)
        if costs is not None:
            return costs
    return None
