from django.db import migrations

def backfill_memberships(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Tenant = apps.get_model('tenants', 'Tenant')
    UserCompanyMembership = apps.get_model('tenants', 'UserCompanyMembership')

    # Find or create default Tenant (id=1)
    default_tenant = Tenant.objects.filter(pk=1).first()
    if not default_tenant:
        default_tenant = Tenant.objects.all().first()
    if not default_tenant:
        default_tenant = Tenant.objects.create(
            pk=1,
            CompanyName="Default Company",
            SubscriptionPlan="Enterprise",
            Status="Active"
        )
    
    for user in User.objects.all():
        UserCompanyMembership.objects.get_or_create(
            user=user,
            tenant=default_tenant,
            defaults={
                'role': 'manager',
                'is_default': True
            }
        )

class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0004_usercompanymembership'),
    ]

    operations = [
        migrations.RunPython(backfill_memberships, reverse_code=migrations.RunPython.noop),
    ]
