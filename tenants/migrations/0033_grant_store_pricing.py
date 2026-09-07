# مواصفة #166 م٥ — يشقّ `store.manage` إلى مفتاحين: المحتوى (يبقى باسمه
# القديم) والمال (`store.pricing` الجديد). بلا هذه الهجرة يفقد كل دورٍ مُنح
# `store.manage` صراحةً (تجاوز شركة أو تجاوز عضو) قدرته على تسعير المتجر فور
# نشر الكود — انكفاءٌ صامت يُقرأ عطباً لا أماناً (مواصفة #166 م٥، قيدٌ صريح).
# المدير مستثنى: يملك كل شيء عبر "*" في `core.access.ROLE_DEFAULTS` بلا أي
# صفٍّ في هذين الجدولين، فلا شيء يُنسَخ له هنا.
from django.db import migrations

OLD_KEY = 'store.manage'
NEW_KEY = 'store.pricing'


def grant_pricing_wherever_manage_was_granted(apps, schema_editor):
    RolePermission = apps.get_model('tenants', 'RolePermission')
    MemberPermission = apps.get_model('tenants', 'MemberPermission')

    for row in RolePermission.objects.filter(permission_key=OLD_KEY, allowed=True):
        RolePermission.objects.get_or_create(
            tenant_id=row.tenant_id, role=row.role, permission_key=NEW_KEY,
            defaults={'allowed': True},
        )

    for row in MemberPermission.objects.filter(permission_key=OLD_KEY, allowed=True):
        MemberPermission.objects.get_or_create(
            membership_id=row.membership_id, permission_key=NEW_KEY,
            defaults={'allowed': True},
        )


def revoke_pricing_grants_added_by_this_migration(apps, schema_editor):
    # تراجعٌ متحفّظ: يحذف فقط ما يطابق شكل ما زرعناه (منحٌ صريح لكل تجاوز
    # `store.manage` قائم) — لا يمسّ منحاً يدوياً لـ`store.pricing` وحدها
    # أضافه مدير الشركة بعد هذه الهجرة عمداً.
    RolePermission = apps.get_model('tenants', 'RolePermission')
    MemberPermission = apps.get_model('tenants', 'MemberPermission')

    manage_role_pairs = set(
        RolePermission.objects.filter(permission_key=OLD_KEY, allowed=True)
        .values_list('tenant_id', 'role')
    )
    for tenant_id, role in manage_role_pairs:
        RolePermission.objects.filter(
            tenant_id=tenant_id, role=role, permission_key=NEW_KEY, allowed=True,
        ).delete()

    manage_membership_ids = set(
        MemberPermission.objects.filter(permission_key=OLD_KEY, allowed=True)
        .values_list('membership_id', flat=True)
    )
    MemberPermission.objects.filter(
        membership_id__in=manage_membership_ids, permission_key=NEW_KEY, allowed=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0032_seed_purchase_rfq_book'),
    ]

    operations = [
        migrations.RunPython(
            grant_pricing_wherever_manage_was_granted,
            revoke_pricing_grants_added_by_this_migration,
        ),
    ]
