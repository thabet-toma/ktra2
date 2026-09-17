# B-3 — قراءةُ طلبيات الاستيراد وعروض مورّديه صارت تشترط `import.procurement.view`
# (مفتاحٌ جديد في `core.access`). افتراضيات الأدوار تمنحه لمن يمشي الاستيراد
# (المشتريات، والمحاسب، والمدير عبر "*")، لكن **التجاوزات** لا تراها الافتراضيات:
# دورٌ أو عضوٌ مُنح مفتاحَ استيرادٍ صراحةً كان يقرأ هذه المستندات فعلاً، وبلا هذه
# الهجرة يفقدها فور نشر الكود — انكفاءٌ صامت. سابقتُها `0033_grant_store_pricing`.
from django.db import migrations

IMPORT_KEYS = ('import.deal.manage', 'import.shipment.manage', 'import.doc.unpost')
NEW_KEY = 'import.procurement.view'


def grant_import_view_wherever_import_was_granted(apps, schema_editor):
    RolePermission = apps.get_model('tenants', 'RolePermission')
    MemberPermission = apps.get_model('tenants', 'MemberPermission')

    role_pairs = set(
        RolePermission.objects.filter(permission_key__in=IMPORT_KEYS, allowed=True)
        .values_list('tenant_id', 'role')
    )
    for tenant_id, role in role_pairs:
        RolePermission.objects.get_or_create(
            tenant_id=tenant_id, role=role, permission_key=NEW_KEY,
            defaults={'allowed': True},
        )

    membership_ids = set(
        MemberPermission.objects.filter(permission_key__in=IMPORT_KEYS, allowed=True)
        .values_list('membership_id', flat=True)
    )
    for membership_id in membership_ids:
        MemberPermission.objects.get_or_create(
            membership_id=membership_id, permission_key=NEW_KEY,
            defaults={'allowed': True},
        )


def revoke_import_view_grants_added_by_this_migration(apps, schema_editor):
    # تراجعٌ متحفّظ على نمط 0033: يحذف منحاً صريحاً يطابق ما زرعناه فقط.
    RolePermission = apps.get_model('tenants', 'RolePermission')
    MemberPermission = apps.get_model('tenants', 'MemberPermission')

    role_pairs = set(
        RolePermission.objects.filter(permission_key__in=IMPORT_KEYS, allowed=True)
        .values_list('tenant_id', 'role')
    )
    for tenant_id, role in role_pairs:
        RolePermission.objects.filter(
            tenant_id=tenant_id, role=role, permission_key=NEW_KEY, allowed=True,
        ).delete()

    membership_ids = set(
        MemberPermission.objects.filter(permission_key__in=IMPORT_KEYS, allowed=True)
        .values_list('membership_id', flat=True)
    )
    MemberPermission.objects.filter(
        membership_id__in=membership_ids, permission_key=NEW_KEY, allowed=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0034_field_staff_role'),
    ]

    operations = [
        migrations.RunPython(
            grant_import_view_wherever_import_was_granted,
            revoke_import_view_grants_added_by_this_migration,
        ),
    ]
