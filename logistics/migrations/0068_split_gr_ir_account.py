from django.db import migrations


OLD_CODE = "2106"
NEW_CODE = "2110"
GR_IR_NAME = "بضاعة مُستلَمة لم تُفوتَر (GR/IR Clearing)"
GR_IR_REFERENCE_TYPES = ("PURCHASE_INVOICE", "PURCHASE_GRN", "GOODS_RECEIPT")


def split_gr_ir_account(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    JournalLine = apps.get_model("accounting", "JournalLine")

    affected_tenant_ids = list(
        JournalLine.objects.filter(
            account__code=OLD_CODE,
            journal__reference_type__in=GR_IR_REFERENCE_TYPES,
        ).values_list("tenant_id", flat=True).distinct()
    )

    for tenant_id in affected_tenant_ids:
        old_account = Account.objects.get(tenant_id=tenant_id, code=OLD_CODE)
        gr_ir_account = Account.objects.filter(
            tenant_id=tenant_id, code=NEW_CODE,
        ).first()
        if gr_ir_account is not None and (
            gr_ir_account.name != GR_IR_NAME
            or gr_ir_account.account_type != "Liability"
        ):
            raise RuntimeError(
                f"Cannot migrate tenant {tenant_id}: account code {NEW_CODE} "
                "is already used for another purpose."
            )
        if gr_ir_account is None:
            gr_ir_account = Account.objects.create(
                tenant_id=tenant_id,
                code=NEW_CODE,
                name=GR_IR_NAME,
                account_type="Liability",
                parent_id=old_account.parent_id,
                is_active=True,
            )

        JournalLine.objects.filter(
            tenant_id=tenant_id,
            account_id=old_account.id,
            journal__reference_type__in=GR_IR_REFERENCE_TYPES,
        ).update(account_id=gr_ir_account.id)


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0026_journal_indexes"),
        ("logistics", "0067_supplierquotation_order_name_and_description"),
    ]

    operations = [
        migrations.RunPython(split_gr_ir_account, migrations.RunPython.noop),
    ]
