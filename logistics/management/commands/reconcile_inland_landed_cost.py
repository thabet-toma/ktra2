"""Old-vs-new inland landed-cost reconciliation (import redesign Q2).

Shows, per deal, the landed-cost impact of making Transport the single inland
source (basis: chargeable unit) instead of the clearance «شحن محلي» lines (basis:
deal value). Review this before we flip the live path.

Usage:
  # Real data (read-only) — run on production to see the actual impact:
  python manage.py reconcile_inland_landed_cost --shipment-id 123
  python manage.py reconcile_inland_landed_cost --tenant-id 3        # all shipments w/ clearance

  # Self-contained demo on synthetic data (created then rolled back):
  python manage.py reconcile_inland_landed_cost --sample
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction


def _fmt(d) -> str:
    return f"{Decimal(str(d or 0)):,.2f}"


class Command(BaseCommand):
    help = "Reconcile OLD (clearance lines / value share) vs NEW (Transport / unit share) inland landed cost."

    def add_arguments(self, parser):
        parser.add_argument('--shipment-id', type=int, default=None)
        parser.add_argument('--tenant-id', type=int, default=None)
        parser.add_argument('--sample', action='store_true')

    def handle(self, *args, **opts):
        from logistics.models import LogisticsShipment, LogisticsClearance
        from logistics.domain import inland

        if opts['sample']:
            self._run_sample()
            return

        sid = opts['shipment_id']
        tid = opts['tenant_id']
        if sid is not None:
            shipments = LogisticsShipment.objects.filter(pk=sid)
        elif tid is not None:
            shipments = LogisticsShipment.objects.filter(tenant_id=tid)
        else:
            self.stderr.write(self.style.ERROR("Provide --shipment-id, --tenant-id, or --sample."))
            return

        grand_old = Decimal('0')
        grand_new = Decimal('0')
        any_rows = False
        for sh in shipments:
            clr = LogisticsClearance.objects.filter(shipment=sh).first()
            if not clr:
                continue
            rows = inland.reconcile_shipment(sh, clr)
            if not rows:
                continue
            any_rows = True
            self._print_table(sh, rows)
            grand_old += sum((r['inland_old_ils'] for r in rows), Decimal('0'))
            grand_new += sum((r['inland_new_ils'] for r in rows), Decimal('0'))

        if not any_rows:
            self.stdout.write(self.style.WARNING("No shipments with a clearance found for the given filter."))
            return
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"GRAND TOTAL inland — OLD={_fmt(grand_old)}  NEW={_fmt(grand_new)}  "
            f"DELTA={_fmt(grand_new - grand_old)}"))
        self.stdout.write("Nothing was modified — review the deltas, then approve flipping the live path.")

    def _print_table(self, shipment, rows):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Shipment {shipment.shipment_number} (id={shipment.id}) — chargeable_unit={shipment.chargeable_unit}"))
        self.stdout.write(
            f"  {'deal':<12}{'merch':>12}{'customs':>12}"
            f"{'inland_OLD':>13}{'inland_NEW':>13}{'delta':>11}")
        for r in rows:
            self.stdout.write(
                f"  {r['ref_number']:<12}{_fmt(r['merch_ils']):>12}{_fmt(r['customs_ils']):>12}"
                f"{_fmt(r['inland_old_ils']):>13}{_fmt(r['inland_new_ils']):>13}"
                f"{_fmt(r['inland_delta_ils']):>11}")
        sub_old = sum((r['inland_old_ils'] for r in rows), Decimal('0'))
        sub_new = sum((r['inland_new_ils'] for r in rows), Decimal('0'))
        self.stdout.write(
            f"  {'— subtotal':<12}{'':>12}{'':>12}"
            f"{_fmt(sub_old):>13}{_fmt(sub_new):>13}{_fmt(sub_new - sub_old):>11}")

    def _run_sample(self):
        """Build a representative scenario, print the comparison, then roll back."""
        from tenants.models import Tenant, Currency
        from partners.models import Partner
        from logistics.models import (
            LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal,
            LogisticsClearance, LogisticsClearanceLine, LocalShipment,
        )
        from logistics.domain import inland

        with transaction.atomic():
            t = Tenant.objects.create(TenantID=999001, CompanyName='RECON SAMPLE')
            cur, _ = Currency.objects.get_or_create(
                Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
            sup = Partner.objects.create(tenant=t, name='مورد', partner_type='Supplier')
            carrier = Partner.objects.create(tenant=t, name='ناقل', partner_type='Supplier')

            # Two deals: unequal VALUE vs unequal VOLUME so the two bases diverge.
            #  A: value 8000, cbm 1   B: value 2000, cbm 4  → value share 80/20, unit share 20/80
            dA = LogisticsDeal.objects.create(
                tenant=t, ref_number='D-A', partner=sup, order_date='2026-06-01',
                currency=cur, total_amount=Decimal('8000'), total_cbm=Decimal('1'))
            dB = LogisticsDeal.objects.create(
                tenant=t, ref_number='D-B', partner=sup, order_date='2026-06-01',
                currency=cur, total_amount=Decimal('2000'), total_cbm=Decimal('4'))
            sh = LogisticsShipment.objects.create(
                tenant=t, shipment_number='SH-RECON', chargeable_unit='cbm',
                freight_rate=Decimal('100'), total_shipping_cost_usd=Decimal('500'))
            LogisticsShipmentDeal.objects.create(shipment=sh, deal=dA)
            LogisticsShipmentDeal.objects.create(shipment=sh, deal=dB)
            clr = LogisticsClearance.objects.create(tenant=t, shipment=sh)
            # OLD inland source: a clearance «شحن محلي» line of 1000 ILS.
            LogisticsClearanceLine.objects.create(
                clearance=clr, seq=1, line_type='other', description='شحن محلي',
                debit=Decimal('1000'), credit=Decimal('0'))
            # NEW inland source: a capitalized Transport row of the same 1000 ILS.
            LocalShipment.objects.create(
                tenant=t, clearance=clr, shipment=sh, carrier=carrier,
                amount=Decimal('1000'), currency=cur, exchange_rate=Decimal('1'),
                capitalize_to_inventory=True, status='delivered')

            rows = inland.reconcile_shipment(sh, clr)
            self.stdout.write(self.style.MIGRATE_HEADING(
                "SAMPLE — inland pool 1000 ILS; A(value 8000/cbm 1) B(value 2000/cbm 4)"))
            self.stdout.write("OLD basis = deal VALUE share; NEW basis = CBM/KG (unit) share.")
            self._print_table(sh, rows)
            self.stdout.write("")
            self.stdout.write("Interpretation: same 1000 ILS pool, redistributed — value-heavy A "
                              "carries less inland, volume-heavy B carries more (haulage tracks volume).")
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS("Sample rolled back — no data persisted."))
