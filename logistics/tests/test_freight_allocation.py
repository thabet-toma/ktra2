"""M2 — freight allocation engine: explicit CBM/KG unit, recompute-on-switch,
penny reconciliation, single code path.
"""
from decimal import Decimal

from django.test import TestCase, SimpleTestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from partners.models import Partner
from accounting.models import JournalHeader
from logistics.models import LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal
from logistics.domain import allocation


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=940, CompanyName='M2 Co')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
        cls.user = User.objects.create_user(username='m2_user', password='x')
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        cls.partner = Partner.objects.create(tenant=cls.tenant, name='Supplier', partner_type='Supplier')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _mk_deal(self, ref, **kw):
        return LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=ref, partner=self.partner,
            order_date='2026-06-01', currency=self.cur, total_amount=1000, **kw)

    def _create_shipment(self, deals, unit='cbm', rate=100):
        resp = self.client.post(
            '/api/logistics/shipments/create-from-deals/',
            {'deal_ids': [d.id for d in deals], 'chargeable_unit': unit, 'freight_rate': rate},
            format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return LogisticsShipment.objects.get(pk=resp.data['id'])


class SetFreightRecomputeTest(_Base):
    def test_switch_unit_recomputes_total_and_allocation(self):
        d1 = self._mk_deal('D-2001', total_cbm=Decimal('2'), total_weight_kg=Decimal('100'))
        d2 = self._mk_deal('D-2002', total_cbm=Decimal('3'), total_weight_kg=Decimal('300'))
        sh = self._create_shipment([d1, d2], unit='cbm', rate=100)
        # CBM basis: total = 100 × 5 = 500, split 2:3
        self.assertEqual(sh.total_shipping_cost_usd, Decimal('500.00'))

        # Switch to KG @ rate 2 → total = 2 × 400 = 800, split 100:300
        resp = self.client.patch(
            f'/api/logistics/shipments/{sh.id}/freight/',
            {'chargeable_unit': 'kg', 'freight_rate': 2}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        sh.refresh_from_db()
        self.assertEqual(sh.chargeable_unit, 'kg')
        self.assertEqual(sh.total_shipping_cost_usd, Decimal('800.00'))
        links = {l.deal_id: l.allocated_shipping_cost
                 for l in LogisticsShipmentDeal.objects.filter(shipment=sh)}
        self.assertEqual(links[d1.id], Decimal('200.00'))
        self.assertEqual(links[d2.id], Decimal('600.00'))
        # No stale value: allocations reconcile to the new total.
        self.assertEqual(sum(links.values(), Decimal('0')), sh.total_shipping_cost_usd)

    def test_switch_reconciles_to_penny(self):
        d1 = self._mk_deal('D-2003', total_cbm=Decimal('1'))
        d2 = self._mk_deal('D-2004', total_cbm=Decimal('1'))
        d3 = self._mk_deal('D-2005', total_cbm=Decimal('1'))
        sh = self._create_shipment([d1, d2, d3], unit='cbm', rate=10)
        resp = self.client.patch(
            f'/api/logistics/shipments/{sh.id}/freight/',
            {'chargeable_unit': 'cbm', 'freight_rate': '33.3334'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        sh.refresh_from_db()
        alloc = sum((l.allocated_shipping_cost for l in LogisticsShipmentDeal.objects.filter(shipment=sh)), Decimal('0'))
        self.assertEqual(alloc, sh.total_shipping_cost_usd)

    def test_reject_invalid_unit(self):
        d1 = self._mk_deal('D-2006', total_cbm=Decimal('1'))
        sh = self._create_shipment([d1], rate=10)
        resp = self.client.patch(
            f'/api/logistics/shipments/{sh.id}/freight/',
            {'chargeable_unit': 'container', 'freight_rate': 5}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_reject_switch_to_unit_deal_lacks(self):
        """Switching to KG when a deal has no weight → clear error (same guard as create)."""
        d1 = self._mk_deal('D-2008', total_cbm=Decimal('2'))  # CBM only, no KG
        sh = self._create_shipment([d1], unit='cbm', rate=10)
        resp = self.client.patch(
            f'/api/logistics/shipments/{sh.id}/freight/',
            {'chargeable_unit': 'kg', 'freight_rate': 5}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('الوزن', str(resp.data))

    def test_reject_when_posted(self):
        d1 = self._mk_deal('D-2007', total_cbm=Decimal('1'))
        sh = self._create_shipment([d1], rate=10)
        jh = JournalHeader.objects.create(tenant=self.tenant)
        LogisticsShipment.objects.filter(pk=sh.id).update(transit_journal=jh)
        resp = self.client.patch(
            f'/api/logistics/shipments/{sh.id}/freight/',
            {'chargeable_unit': 'kg', 'freight_rate': 5}, format='json')
        self.assertEqual(resp.status_code, 400, resp.content)


class ResolveChargeableUnitTest(SimpleTestCase):
    """The single fallback path: explicit field wins; legacy triad maps deterministically."""

    def _sh(self, **kw):
        from types import SimpleNamespace
        base = dict(chargeable_unit=None, pricing_method=None, unit_type=None)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_explicit_field_wins(self):
        self.assertEqual(allocation.resolve_chargeable_unit(self._sh(chargeable_unit='kg')), 'kg')

    def test_legacy_weight_maps_kg(self):
        self.assertEqual(
            allocation.resolve_chargeable_unit(self._sh(pricing_method='unit', unit_type='weight')), 'kg')

    def test_legacy_container_folds_to_cbm(self):
        self.assertEqual(
            allocation.resolve_chargeable_unit(self._sh(pricing_method='unit', unit_type='container')), 'cbm')

    def test_default_cbm(self):
        self.assertEqual(allocation.resolve_chargeable_unit(self._sh()), 'cbm')
