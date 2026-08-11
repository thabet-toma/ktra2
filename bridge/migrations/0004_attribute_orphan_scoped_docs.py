# الجلسة الأمنية 2026-08-11 — P0-4: إغلاق ثغرة تبنّي الوثائق اليتيمة.
#
# قبل هذا كانت الوثائق المُنطاقة بـtenant=NULL (المتبقية من قبل إدخال العزل)
# مقروءة/قابلة للكتابة من أي شركة، وأول كاتب «يتبناها». الكود الآن يرفضها
# (404)، وهذه الهجرة تنسب اليتيمة الموجودة للشركة الافتراضية (tenant #1) —
# نفس نمط 0003 — فلا تبقى وثيقة حيّة بلا مالك ولا تُفقد بيانات مشروعة.
#
# المجموعات العالمية (غير مُنطاقة) تُستثنى: users/publicGallery/aboutLinks —
# هذه تبقى tenant=NULL عمداً (مصادقة/محتوى عام).
from django.db import migrations

# يجب أن تطابق GLOBAL_COLLECTIONS في bridge/views.py بعد P0-3.
_GLOBAL_ROOTS = {'users', 'publicGallery', 'aboutLinks'}


def attribute_orphans(apps, schema_editor):
    FirestoreMirrorDoc = apps.get_model('bridge', 'FirestoreMirrorDoc')
    Tenant = apps.get_model('tenants', 'Tenant')
    default = Tenant.objects.filter(TenantID=1).first() or Tenant.objects.order_by('TenantID').first()
    if default is None:
        return
    for doc in FirestoreMirrorDoc.objects.filter(tenant__isnull=True).iterator():
        root = (doc.path or '').strip('/').split('/')[0]
        if root in _GLOBAL_ROOTS:
            continue  # عالمية عمداً — تبقى بلا مالك
        doc.tenant = default
        doc.save(update_fields=['tenant'])


class Migration(migrations.Migration):

    dependencies = [
        ('bridge', '0003_scope_tasks_to_tenant'),
    ]

    operations = [
        migrations.RunPython(attribute_orphans, migrations.RunPython.noop),
    ]
