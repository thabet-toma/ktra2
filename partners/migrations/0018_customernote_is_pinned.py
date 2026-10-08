from django.db import migrations, models
from django.db.models import Q


def strip_query_and_fragment(target_id):
    """معرّف ملاحظة الصفحة بلا `?query` ولا `#hash` — يُقطع عند أول علامة منهما."""
    value = str(target_id or '')
    cut = min((i for i in (value.find('?'), value.find('#')) if i >= 0), default=len(value))
    return value[:cut]


def normalize_page_note_target_ids(apps, schema_editor):
    """ملاحظات الصفحات صارت مفتاحها المسار وحده (قرار المالك): كانت `target_id` =
    المسار + الاستعلام، فتختفي الملاحظة بتبديل تبويب أو فلتر. `target_path` يبقى
    كاملاً للتنقّل من التذكير. `update()` مباشر كي لا يُلمس `updated_at`.
    """
    CustomerNote = apps.get_model('partners', 'CustomerNote')
    rows = CustomerNote.objects.filter(target_type='page').filter(
        Q(target_id__contains='?') | Q(target_id__contains='#'),
    ).values_list('pk', 'target_id')
    for pk, target_id in list(rows):
        CustomerNote.objects.filter(pk=pk).update(target_id=strip_query_and_fragment(target_id))


class Migration(migrations.Migration):

    dependencies = [
        ('partners', '0017_partner_is_active'),
    ]

    operations = [
        migrations.AddField(
            model_name='customernote',
            name='is_pinned',
            field=models.BooleanField(
                db_column='IsPinned', default=False,
                help_text='تثبيت على الصفحة — ملاحظة الصفحة المثبّتة غير المنجزة تظهر بشريط أصفر '
                          'أعلى الصفحة لكل مستخدمي الشركة',
            ),
        ),
        migrations.RunPython(normalize_page_note_target_ids, migrations.RunPython.noop),
    ]
