"""#240 — الخطوة ٢ من ٢: مفتاح الهاتف لكل بطاقة قائمة، **لكل الشركات**.

لا فلترة على ترخيص الوحدة عمداً (كالهجرة 0015): الصفوف خاملةٌ خلف `module_enabled`،
والنموذج التاريخي لا يحمل `save()` فيُحسب المفتاح هنا صراحةً.

الترقيم بـ`pk` لا بـ`phone_key=""`: هاتفٌ أقصر من تسعة أرقام يبقى مفتاحه فارغاً
ولو حُسب، فالانتقاء بالفراغ لا ينتهي.

التطبيع نسخةٌ خاصة هنا لا استيرادٌ من `after_sales.models`: هجرة البيانات لا
تتّكئ على كودٍ حيٍّ قد يتحرّك أو يتغيّر لاحقاً — وإلا انقلبت نتيجتها مع الزمن.

**لا رجوع (`RunPython.noop`) بقصد:** التراجع عن الخطوة ١ يُسقط العمود كلّه.
"""
import re

from django.db import migrations

_KEY_LENGTH = 9
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _phone_key(raw) -> str:
    digits = re.sub(r"\D", "", (raw or "").translate(_DIGITS))
    return digits[-_KEY_LENGTH:] if len(digits) >= _KEY_LENGTH else ""


def fill_phone_keys(card_model, batch_size: int = 500) -> int:
    """يملأ `phone_key` لكل صفٍّ له هاتف. يُرجع عدد الصفوف المفحوصة — يُختبر مباشرةً."""
    seen = 0
    last_pk = 0
    while True:
        batch = list(
            card_model.objects.filter(pk__gt=last_pk).exclude(customer_phone="")
            .order_by("pk")[:batch_size]
        )
        if not batch:
            return seen
        for card in batch:
            card.phone_key = _phone_key(card.customer_phone)
        card_model.objects.bulk_update(batch, ["phone_key"])
        seen += len(batch)
        last_pk = batch[-1].pk


def backfill_phone_keys(apps, schema_editor):
    fill_phone_keys(apps.get_model('after_sales', 'WarrantyCard'))


class Migration(migrations.Migration):

    dependencies = [
        ('after_sales', '0018_warrantycard_phone_key'),
    ]

    operations = [
        migrations.RunPython(backfill_phone_keys, migrations.RunPython.noop),
    ]
