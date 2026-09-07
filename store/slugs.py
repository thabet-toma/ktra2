"""توليد slug صالح للعربية — النسخةُ الحيّة التي يستعملها النموذج (`store/models.py`).

`django.utils.text.slugify` الافتراضي (`allow_unicode=False`) يُفرغ الأسماء
العربية تماماً (تطبيع Unicode يُسقط الأحرف غير اللاتينية). `allow_unicode=True`
ينقلها حرفياً بدلاً من ذلك. وحين يبقى الناتج فارغاً رغم ذلك (اسمٌ من رموزٍ
فقط) يُستعمل معرّفٌ رقميٌّ عوضاً عن slug فارغ — لا يُسمح بفراغه أبداً.

**هذا الملفّ للكود الحيّ فقط.** هجرةُ البيانات
`store/migrations/0006_migrate_catalog_to_store_product.py` تحمل نسخةً
مجمَّدةً مستقلّةً من نفس المنطق (`_build_unique_slug_frozen`) **ولا تستورد من
هنا** — الهجرةُ أثرٌ يجب أن يُنتج نفسَ النتيجة بعد سنوات، فتعديلاً هنا لا يجوز
أن يُغيّر بصمتٍ سلوكَ إعادة تشغيل تلك السلسلة على قاعدةٍ جديدة
(`fresh-db-migration-chain`). **لا توحّد الملفّين.**
"""
from django.utils import timezone
from django.utils.text import slugify


def build_unique_slug(name, slug_exists):
    """يبني slug فريداً من `name` عبر `slug_exists(candidate) -> bool`.

    عند التصادم يُضاف لاحقةٌ رقميّةٌ متصاعدة (`-2`، `-3`، ...) حتى الفرادة.
    """
    base = slugify(name or "", allow_unicode=True)
    if not base:
        base = str(int(timezone.now().timestamp() * 1000))
    candidate = base
    suffix = 2
    while slug_exists(candidate):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate
