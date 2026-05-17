from decimal import Decimal

from django.db import migrations


def ensure_vat16(apps, schema_editor):
    TaxRate = apps.get_model("accounting", "TaxRate")
    Tenant = apps.get_model("tenants", "Tenant")
    Account = apps.get_model("accounting", "Account")

    for tenant in Tenant.objects.all():
        tid = tenant.TenantID
        if TaxRate.objects.filter(tenant_id=tid, code="VAT16").exists():
            continue
        acc = (
            Account.objects.filter(tenant_id=tid, account_type="Liability")
            .order_by("id")
            .first()
        )
        if acc is None:
            acc = Account.objects.filter(tenant_id=tid).order_by("id").first()
        if acc is None:
            continue
        TaxRate.objects.create(
            tenant_id=tid,
            name="ضريبة القيمة المضافة 16%",
            code="VAT16",
            rate=Decimal("16.00"),
            tax_account_id=acc.id,
            is_active=True,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0010_align_legacy_tax_rates_columns"),
    ]

    operations = [
        migrations.RunPython(ensure_vat16, noop_reverse),
    ]
