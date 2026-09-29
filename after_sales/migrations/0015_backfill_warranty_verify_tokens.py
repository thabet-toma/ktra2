"""#237 — الخطوة ٢ من ٣: رمز لكل بطاقة قائمة، **لكل الشركات**.

لا فلترة على ترخيص الوحدة عمداً (استثناءٌ مُعلَن في المواصفة #228 §هجرات البيانات):
الرمز عمودٌ لازمٌ لفرادةٍ غير nullable، والصفوف خاملةٌ خلف `module_enabled`.

الدفعات تمنع تحميل جدولٍ كبير في الذاكرة، ويعمل المساعد على النموذج التاريخي.

**لا رجوع (`RunPython.noop`) بقصد:** التراجع عن الخطوة ١ يُسقط العمود كلّه فلا يبقى
ما يُنقَّى، والرموز المولَّدة لا معنى لمسحها وحدها.
"""
import secrets

from django.db import migrations
from django.db.models import Q


def fill_verify_tokens(card_model, batch_size: int = 500) -> int:
    """يملأ كل صفٍّ رمزُه NULL أو فارغ. يُرجع عدد الصفوف — يُختبر مباشرةً."""
    filled = 0
    pending = Q(verify_token__isnull=True) | Q(verify_token="")
    while True:
        batch = list(card_model.objects.filter(pending).order_by("pk")[:batch_size])
        if not batch:
            return filled
        for card in batch:
            card.verify_token = secrets.token_urlsafe(16)
        card_model.objects.bulk_update(batch, ["verify_token"])
        filled += len(batch)


def backfill_verify_tokens(apps, schema_editor):
    fill_verify_tokens(apps.get_model('after_sales', 'WarrantyCard'))


class Migration(migrations.Migration):

    dependencies = [
        ('after_sales', '0014_warrantycard_verify_token_nullable'),
    ]

    operations = [
        migrations.RunPython(backfill_verify_tokens, migrations.RunPython.noop),
    ]
