"""Q2 — inland single-source reconciliation (OLD clearance-lines/value vs NEW Transport/unit).

Proves the redistribution used by the live landed-cost path: same inland pool, but
volume-heavy deals carry more of it (haulage tracks volume), value-heavy deals carry less.
"""
from decimal import Decimal

from django.test import TestCase
from django.core.management import call_command

from tenants.models import Tenant, Currency
from partners.models import Partner
from logistics.models import (
    LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal,
    LogisticsClearance, LogisticsClearanceLine, LocalShipment,
)
from logistics.domain import inland


class InlandReconcileTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t = Tenant.objects.create(TenantID=980, CompanyName='Recon Co')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
        cls.sup = Partner.objects.create(tenant=cls.t, name='مورد', partner_type='Supplier')
        cls.carrier = Partner.objects.create(tenant=cls.t, name='ناقل', partner_type='Supplier')

    def _scenario(self):
        # A: value 8000 / cbm 1 ;  B: value 2000 / cbm 4
        dA = LogisticsDeal.objects.create(
            tenant=self.t, ref_number='D-A', partner=self.sup, order_date='2026-06-01',
            currency=self.cur, total_amount=Decimal('8000'), total_cbm=Decimal('1'))
        dB = LogisticsDeal.objects.create(
            tenant=self.t, ref_number='D-B', partner=self.sup, order_date='2026-06-01',
            currency=self.cur, total_amount=Decimal('2000'), total_cbm=Decimal('4'))
        sh = LogisticsShipment.objects.create(
            tenant=self.t, shipment_number='SH-R', chargeable_unit='cbm',
            freight_rate=Decimal('100'), total_shipping_cost_usd=Decimal('500'))
        LogisticsShipmentDeal.objects.create(shipment=sh, deal=dA)
        LogisticsShipmentDeal.objects.create(shipment=sh, deal=dB)
        clr = LogisticsClearance.objects.create(tenant=self.t, shipment=sh)
        LogisticsClearanceLine.objects.create(
            clearance=clr, seq=1, line_type='other', description='شحن محلي',
            debit=Decimal('1000'), credit=Decimal('0'))
        LocalShipment.objects.create(
            tenant=self.t, clearance=clr, shipment=sh, carrier=self.carrier,
            amount=Decimal('1000'), currency=self.cur, exchange_rate=Decimal('1'),
            capitalize_to_inventory=True, status='delivered')
        return dA, dB, sh, clr

    def test_transport_pool(self):
        _, _, sh, clr = self._scenario()
        self.assertEqual(inland.transport_pool_ils(sh, clr), Decimal('1000.00'))

    def test_old_vs_new_redistribution(self):
        dA, dB, sh, clr = self._scenario()
        rows = {r['ref_number']: r for r in inland.reconcile_shipment(sh, clr)}
        # OLD by value share (0.8 / 0.2)
        self.assertEqual(rows['D-A']['inland_old_ils'], Decimal('800.00'))
        self.assertEqual(rows['D-B']['inland_old_ils'], Decimal('200.00'))
        # NEW by unit (CBM) share (0.2 / 0.8)
        self.assertEqual(rows['D-A']['inland_new_ils'], Decimal('200.00'))
        self.assertEqual(rows['D-B']['inland_new_ils'], Decimal('800.00'))
        # Deltas cancel — same pool, redistributed onto volume
        self.assertEqual(rows['D-A']['inland_delta_ils'], Decimal('-600.00'))
        self.assertEqual(rows['D-B']['inland_delta_ils'], Decimal('600.00'))
        total_delta = sum((r['inland_delta_ils'] for r in rows.values()), Decimal('0'))
        self.assertEqual(total_delta, Decimal('0.00'))

    def test_sample_command_runs_and_rolls_back(self):
        call_command('reconcile_inland_landed_cost', sample=True)
        # The sample tenant must not persist (rolled back).
        self.assertFalse(Tenant.objects.filter(TenantID=999001).exists())
