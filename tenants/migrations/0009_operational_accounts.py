"""task13 M2 — data migration: complete operational accounts on existing trees.

1) Every seeded tenant gets the accounts the posting paths expect:
   1107 شيكات برسم التحصيل · 1110 صناديق النقدية ·
   2106/2107/2108 ذمم وكلاء الشحن/المخلصين/النقل المحلي.
2) Logistics-partner ledger accounts auto-created under the WRONG parents
   (2102 قروض / 2103 مصاريف مستحقة / 2104 ضريبة المخرجات) are re-parented to
   the new dedicated payable parents, keeping the GL hierarchy honest.
"""
from django.db import migrations

OPS_ACCOUNTS = [
    # (code, name, type, parent_code)
    ("1107", "شيكات برسم التحصيل (Cheques Under Collection)", "Asset", "11"),
    ("1110", "صناديق النقدية (Cash Boxes)", "Asset", "11"),
    ("2106", "ذمم وكلاء الشحن (Freight Forwarders Payable)", "Liability", "21"),
    ("2107", "ذمم المخلصين الجمركيين (Customs Brokers Payable)", "Liability", "21"),
    ("2108", "ذمم النقل المحلي (Local Transporters Payable)", "Liability", "21"),
]

# partner_type → (old wrong parent code, new dedicated parent code)
REPARENT = {
    "FreightForwarder": ("2102", "2106"),
    "CustomsBroker": ("2103", "2107"),
    "LocalTransporter": ("2104", "2108"),
}


def forwards(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    Account = apps.get_model("accounting", "Account")
    Partner = apps.get_model("partners", "Partner")

    for tenant in Tenant.objects.all():
        # 1) ensure operational accounts (only when the standard parent exists)
        for code, name, acc_type, parent_code in OPS_ACCOUNTS:
            if Account.objects.filter(tenant=tenant, code=code).exists():
                continue
            parent = Account.objects.filter(tenant=tenant, code=parent_code).first()
            if parent is None:
                continue
            Account.objects.create(
                tenant=tenant, code=code, name=name,
                account_type=acc_type, parent=parent, is_active=True,
            )

        # 2) re-parent mis-filed logistics partner accounts
        for ptype, (old_code, new_code) in REPARENT.items():
            new_parent = Account.objects.filter(tenant=tenant, code=new_code).first()
            if new_parent is None:
                continue
            partners = Partner.objects.filter(
                tenant=tenant, partner_type=ptype,
                linked_account__isnull=False,
                linked_account__parent__code=old_code,
            ).select_related("linked_account")
            for p in partners:
                acc = p.linked_account
                acc.parent = new_parent
                acc.account_type = new_parent.account_type
                acc.save(update_fields=["parent", "account_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0008_heal_company_seed"),
        ("accounting", "0023_alter_cheque_status"),
        ("partners", "0006_n9_t8_partner_row_color"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
