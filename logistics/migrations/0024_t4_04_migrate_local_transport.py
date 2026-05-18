"""T4-04: surface historical clearance local-transport as LocalShipment.

Owner complaint: local transport appears both inside the clearance
screen and on the standalone "الشحن المحلي" page. Going forward the
clearance entry path is removed (UI change) and LocalShipment is the
single source. This migration back-fills the *existing* shipping-tagged
clearance payments as LocalShipment records so they show up in the one
place — WITHOUT touching any posted financial data:

  * capitalize_to_inventory = False  → landed cost is unchanged (the
    cost keeps flowing through the clearance cost-line exactly as
    before via sum_carrier_clearance_cost_line_ils).
  * journal / is_posted are copied from the source payment — NO new
    journal is created, nothing is re-posted.
  * idempotent: a marker in notes prevents duplicates on re-run.
  * reversible: reverse() deletes only the rows this migration created.
"""
from django.db import migrations

_MARKER = "[T4-04-MIGRATED]"


def _is_shipping_payment(notes):
    n = str(notes or "").lstrip()
    return n.startswith("[شحن]") or n.startswith("شحن")


def forwards(apps, schema_editor):
    LogisticsClearancePayment = apps.get_model("logistics", "LogisticsClearancePayment")
    LocalShipment = apps.get_model("logistics", "LocalShipment")

    for pay in LogisticsClearancePayment.objects.select_related("clearance").all():
        if not _is_shipping_payment(pay.notes):
            continue
        if not pay.customs_broker_id:
            # carrier is required (NOT NULL); skip rows we cannot map.
            continue
        clr = pay.clearance
        # idempotency: skip if already migrated for this payment.
        if LocalShipment.objects.filter(
            clearance_id=pay.clearance_id,
            journal_id=pay.journal_id,
            notes__contains=f"{_MARKER} pay#{pay.id}",
        ).exists():
            continue
        LocalShipment.objects.create(
            tenant_id=pay.tenant_id,
            clearance_id=pay.clearance_id,
            shipment_id=getattr(clr, "shipment_id", None),
            shipment_number=f"LS-MIG-{pay.id}",
            carrier_id=pay.customs_broker_id,
            amount=pay.amount or 0,
            currency_id=pay.currency_id or 1,
            exchange_rate=1,
            payment_type="credit",
            journal_id=pay.journal_id,
            is_posted=pay.is_posted,
            capitalize_to_inventory=False,
            status="delivered",
            notes=(
                f"{_MARKER} pay#{pay.id} — مُرحّل تلقائياً من دفعة شحن التخليص. "
                f"التكلفة مُرسملة عبر بند التخليص؛ هذا السجل للتوحيد/العرض فقط "
                f"(لا قيد جديد، لا تغيير في landed cost)."
            ),
        )


def backwards(apps, schema_editor):
    LocalShipment = apps.get_model("logistics", "LocalShipment")
    LocalShipment.objects.filter(notes__contains=_MARKER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("logistics", "0023_add_short_name_to_deal"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
