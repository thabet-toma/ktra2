"""حارس «غير نشط» — مصدر حقيقة واحد لرفض ترحيل مستند تجاريّ فيه صنف أو طرف موقوف.

القرار (المالك): الصنف/الطرف الموقوف يغيب عن المنتقيات (T2)، **والمسودّة المحفوظة قبل
الإيقاف لا تُرحَّل** («اكيد ممنوع الترحيل»). سابقةُ السوق: Business Central يرفض ترحيل
المستندات الجديدة لصنفٍ/مورّدٍ «Blocked» ويُعفي المرتجعات ومذكّرات الدائن؛ وزوهو
يمنع «Inactive» من الفواتير الجديدة.

يُستدعى من البيع واللوجستيات (فهو في `core` لا في أحدهما) على المسارات التي تُنتج
مستنداً **مرحَّلاً أو قابلاً للترحيل**: ترحيل فاتورة البيع/الشراء، وتأكيد الطلبيات،
وتحويل العروض والطلبيات إلى فواتير. ولا يُستدعى أبداً من: المرتجعات، تسليم/استلام
فاتورة مرحَّلة أصلاً، نقل/جرد المخزون، السندات والشيكات والإشعارات — تلك تبقى
مسموحة كي تُسوَّى الأرصدة وتُنظَّف الأرصدة المخزنية للموقوف. ولا يُستدعى من
`record_stock_movement` ولا `post_journal` (طبقتان أدنى لا تعرفان نوع المستند).

الحارس بلا اعتماد على نماذج app: يقرأ `is_active` بالـduck-typing، فلا يخالف عقود
`.importlinter`، ولا يكتب شيئاً في قاعدة البيانات.
"""
from __future__ import annotations

import logging
from typing import Iterable

from django.core.exceptions import ValidationError

logger = logging.getLogger("core.active_guard")

#: نوع الطرف ← اسمه في الرسالة؛ ما عداهما «الطرف».
_PARTNER_ROLE = {"Customer": "العميل", "Supplier": "المورّد"}


def _product_label(product) -> str:
    return (
        getattr(product, "name_ar", None)
        or getattr(product, "name_en", None)
        or getattr(product, "sku", None)
        or f"#{getattr(product, 'pk', '?')}"
    )


def assert_active_for_posting(
    *,
    partner=None,
    products: Iterable = (),
    action: str = "ترحيل",
    document_label: str = "المستند",
) -> None:
    """يرفع `ValidationError` بالعربية تسمّي **كل** مخالف: الأصناف غير النشطة (مكرَّرها
    مرّة، والخدمات صنفٌ كغيرها) والطرف غير النشط. لا يفعل شيئاً إن كان الكلّ نشطاً.

    `action`: «ترحيل» (الافتراضي) · «تأكيد» · «تحويل». `partner`/`products` كائنات
    نماذج حيّة؛ عنصر `None` في `products` (بند بلا صنف) يُتجاوز.
    """
    seen: set = set()
    inactive_products = []
    for product in products:
        if product is None:
            continue
        key = getattr(product, "pk", None) or id(product)
        if key in seen:
            continue
        seen.add(key)
        if not getattr(product, "is_active", True):
            inactive_products.append(product)

    partner_inactive = partner is not None and not getattr(partner, "is_active", True)
    if not inactive_products and not partner_inactive:
        return

    parts = []
    if inactive_products:
        names = "، ".join(f"«{_product_label(p)}»" for p in inactive_products)
        parts.append(f"الصنف {names} غير نشط — نشّطه من قائمة المنتجات أو احذفه من البنود.")
    if partner_inactive:
        role = _PARTNER_ROLE.get(getattr(partner, "partner_type", ""), "الطرف")
        parts.append(
            f"{role} «{getattr(partner, 'name', '') or getattr(partner, 'pk', '?')}» "
            "غير نشط — نشّطه من ملفه أو غيّر الطرف."
        )

    logger.warning(
        "Blocked %s of %s — inactive partner=%s products=%s",
        action, document_label,
        getattr(partner, "pk", None) if partner_inactive else None,
        [p.pk for p in inactive_products],
    )
    raise ValidationError(f"لا يمكن {action} {document_label}: " + " ".join(parts))
