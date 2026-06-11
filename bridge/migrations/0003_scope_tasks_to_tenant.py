# task11 M7 — «tasks» mirror docs become tenant-scoped.
# 0002 left them global (tenant=NULL); attribute existing ones to the default
# company (tenant #1) so they keep showing there and stop leaking elsewhere.
from django.db import migrations


def backfill_tasks_tenant(apps, schema_editor):
    FirestoreMirrorDoc = apps.get_model('bridge', 'FirestoreMirrorDoc')
    Tenant = apps.get_model('tenants', 'Tenant')
    default = Tenant.objects.filter(TenantID=1).first() or Tenant.objects.order_by('TenantID').first()
    if default is None:
        return
    FirestoreMirrorDoc.objects.filter(
        tenant__isnull=True, path__startswith='tasks/'
    ).update(tenant=default)


class Migration(migrations.Migration):

    dependencies = [
        ('bridge', '0002_firestoremirrordoc_tenant'),
    ]

    operations = [
        migrations.RunPython(backfill_tasks_tenant, migrations.RunPython.noop),
    ]
