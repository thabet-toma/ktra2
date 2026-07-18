"""M1 — Deal→Shipment create-from-deals (fixes RC-1).

The exact action the owner said was impossible ("I can't even convert a deal into
a shipment"), wired the correct direction: select Ready-to-Ship deals → create one
shipment. Covers aggregation (CBM+KG), freight = rate×Σunit, penny-reconciled
allocation, stage advance, and the guard rails.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from partners.models import Partner
from logistics.models import LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal
from logistics.domain import allocation


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=930, CompanyName='M1 Co')
        cls.other_tenant = Tenant.objects.create(TenantID=931, CompanyName='M1 Other')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True}
        )
        cls.user = User.objects.create_user(username='m1_user', password='x')
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        cls.partner = Partner.objects.create(tenant=cls.tenant, name='Supplier X', partner_type='Supplier')
        cls.other_partner = Partner.objects.create(tenant=cls.other_tenant, name='Supplier Y', partner_type='Supplier')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _mk_deal(self, ref, tenant=None, partner=None, **kw):
        return LogisticsDeal.objects.create(
            tenant=tenant or self.tenant, ref_number=ref,
            partner=partner or self.partner, order_date='2026-06-01',
            currency=self.cur, total_amount=kw.pop('total_amount', 1000), **kw,
        )

    def _create(self, deal_ids, unit='cbm', rate=100, header=None):
        return self.client.post(
            '/api/logistics/shipments/create-from-deals/',
            {'deal_ids': deal_ids, 'chargeable_unit': unit, 'freight_rate': rate,
             'header': header or {}},
            format='json',
        )


class CreateFromDealsTest(_Base):
    def test_regular_create_assigns_a_shipment_number_when_the_form_sends_blank(self):
        response = self.client.post(
            '/api/logistics/shipments/',
            {'shipment_number': '', 'shipment_name': 'شحنة واجهة جديدة'},
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertRegex(response.data['shipment_number'], r'^SH-\d{4}$')
        self.assertEqual(
            LogisticsShipment.objects.get(pk=response.data['id']).tenant_id,
            self.tenant.pk,
        )

    def test_regular_create_ignores_other_tenant_sequence(self):
        LogisticsShipment.objects.create(
            tenant=self.other_tenant, shipment_number='SH-0099'
        )
        response = self.client.post(
            '/api/logistics/shipments/', {'shipment_number': ''}, format='json'
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['shipment_number'], 'SH-0001')

    def test_blank_number_cannot_erase_a_saved_shipment_number(self):
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number='SH-0042'
        )
        response = self.client.patch(
            f'/api/logistics/shipments/{shipment.pk}/',
            {'shipment_number': ''},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        shipment.refresh_from_db()
        self.assertEqual(shipment.shipment_number, 'SH-0042')

    def test_create_from_two_deals_cbm(self):
        d1 = self._mk_deal('D-1001', total_cbm=Decimal('2'))
        d2 = self._mk_deal('D-1002', total_cbm=Decimal('3'))
        resp = self._create([d1.id, d2.id], unit='cbm', rate=100)
        self.assertEqual(resp.status_code, 201, resp.content)
        sh = LogisticsShipment.objects.get(pk=resp.data['id'])
        # Freight total = 100 × (2+3) = 500
        self.assertEqual(sh.total_shipping_cost_usd, Decimal('500.00'))
        self.assertEqual(sh.chargeable_unit, 'cbm')
        self.assertEqual(sh.total_volume, Decimal('5.000'))
        links = {l.deal_id: l.allocated_shipping_cost
                 for l in LogisticsShipmentDeal.objects.filter(shipment=sh)}
        self.assertEqual(links[d1.id], Decimal('200.00'))
        self.assertEqual(links[d2.id], Decimal('300.00'))
        # Deals advanced to IN_SHIPMENT
        d1.refresh_from_db(); d2.refresh_from_db()
        self.assertEqual(d1.stage, LogisticsDeal.STAGE_IN_SHIPMENT)
        self.assertEqual(d1.shipping_workflow_status, 'sw_wait_arrival')

    def test_allocation_exposes_deal_measures(self):
        """The wizard needs each deal's CBM/KG to show + warn on missing volume."""
        d1 = self._mk_deal('D-1009', total_cbm=Decimal('2'), total_weight_kg=Decimal('50'))
        resp = self._create([d1.id], unit='cbm', rate=10)
        self.assertEqual(resp.status_code, 201, resp.content)
        alloc = resp.data['shipment_deal_allocations'][0]
        self.assertEqual(str(alloc['deal_total_cbm']), '2.000')
        self.assertEqual(str(alloc['deal_total_weight_kg']), '50.000')

    def test_create_kg_basis(self):
        d1 = self._mk_deal('D-1003', total_weight_kg=Decimal('100'))
        d2 = self._mk_deal('D-1004', total_weight_kg=Decimal('300'))
        resp = self._create([d1.id, d2.id], unit='kg', rate=2)
        self.assertEqual(resp.status_code, 201, resp.content)
        sh = LogisticsShipment.objects.get(pk=resp.data['id'])
        self.assertEqual(sh.chargeable_unit, 'kg')
        self.assertEqual(sh.total_shipping_cost_usd, Decimal('800.00'))  # 2 × 400
        self.assertEqual(sh.total_weight_kg, Decimal('400.000'))
        links = {l.deal_id: l.allocated_shipping_cost
                 for l in LogisticsShipmentDeal.objects.filter(shipment=sh)}
        self.assertEqual(links[d1.id], Decimal('200.00'))
        self.assertEqual(links[d2.id], Decimal('600.00'))

    def test_allocation_reconciles_to_penny(self):
        """Fractional split must sum back to the freight total with zero leakage."""
        d1 = self._mk_deal('D-1005', total_cbm=Decimal('1'))
        d2 = self._mk_deal('D-1006', total_cbm=Decimal('2'))
        d3 = self._mk_deal('D-1007', total_cbm=Decimal('3'))
        resp = self._create([d1.id, d2.id, d3.id], unit='cbm', rate='16.6667')
        self.assertEqual(resp.status_code, 201, resp.content)
        sh = LogisticsShipment.objects.get(pk=resp.data['id'])
        total = sh.total_shipping_cost_usd
        alloc_sum = sum(
            (l.allocated_shipping_cost for l in LogisticsShipmentDeal.objects.filter(shipment=sh)),
            Decimal('0'),
        )
        self.assertEqual(alloc_sum, total)  # exact reconciliation

    def test_header_fields_applied(self):
        agent = Partner.objects.create(tenant=self.tenant, name='Forwarder', partner_type='ShippingAgent')
        d1 = self._mk_deal('D-1008', total_cbm=Decimal('1'))
        resp = self._create(
            [d1.id], unit='cbm', rate=50,
            header={'shipment_name': 'شحنة الصين', 'shipping_agent_id': agent.id, 'shipping_type': 'air'},
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        sh = LogisticsShipment.objects.get(pk=resp.data['id'])
        self.assertEqual(sh.shipment_name, 'شحنة الصين')
        self.assertEqual(sh.shipping_agent_id, agent.id)
        self.assertEqual(sh.shipping_type, 'air')


class CreateFromDealsGuardsTest(_Base):
    def test_reject_empty(self):
        self.assertEqual(self._create([], rate=1).status_code, 400)

    def test_reject_invalid_unit(self):
        d1 = self._mk_deal('D-1101', total_cbm=Decimal('1'))
        self.assertEqual(self._create([d1.id], unit='container', rate=1).status_code, 400)

    def test_reject_already_linked_deal(self):
        d1 = self._mk_deal('D-1102', total_cbm=Decimal('1'))
        first = self._create([d1.id], rate=10)
        self.assertEqual(first.status_code, 201, first.content)
        # Second attempt with the same deal must fail and create nothing new.
        n_before = LogisticsShipment.objects.count()
        second = self._create([d1.id], rate=10)
        self.assertEqual(second.status_code, 400, second.content)
        self.assertEqual(LogisticsShipment.objects.count(), n_before)

    def test_reject_other_tenant_deal(self):
        foreign = self._mk_deal('D-1103', tenant=self.other_tenant, partner=self.other_partner, total_cbm=Decimal('1'))
        resp = self._create([foreign.id], rate=10)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(LogisticsShipmentDeal.objects.filter(deal=foreign).exists())

    def test_reject_invoiced_deal(self):
        d1 = self._mk_deal('D-1104', total_cbm=Decimal('1'), stage=LogisticsDeal.STAGE_INVOICED)
        resp = self._create([d1.id], rate=10)
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_reject_deal_missing_cbm_when_rate(self):
        """Freight rate applied but deal has no CBM → clear error, nothing created."""
        d1 = self._mk_deal('D-1105')  # total_cbm defaults to 0
        resp = self._create([d1.id], unit='cbm', rate=100)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('الحجم', str(resp.data))
        self.assertFalse(LogisticsShipmentDeal.objects.filter(deal=d1).exists())

    def test_reject_deal_missing_kg_when_rate(self):
        d1 = self._mk_deal('D-1106', total_cbm=Decimal('2'))  # has CBM, no KG
        resp = self._create([d1.id], unit='kg', rate=5)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('الوزن', str(resp.data))

    def test_allow_missing_measure_when_no_rate(self):
        """No freight rate → header-first creation is allowed even with 0 measure."""
        d1 = self._mk_deal('D-1107')  # no CBM
        resp = self._create([d1.id], unit='cbm', rate=0)
        self.assertEqual(resp.status_code, 201, resp.content)


class ReadyToShipListTest(_Base):
    def test_lists_only_ready_to_ship_unlinked(self):
        """Only «تم الشحن للوكيل» (READY_TO_SHIP) appears — drafts and cancelled excluded."""
        d1 = self._mk_deal('D-1201', total_cbm=Decimal('1'), stage=LogisticsDeal.STAGE_READY_TO_SHIP)
        draft = self._mk_deal('D-1202', total_cbm=Decimal('1'), stage=LogisticsDeal.STAGE_DRAFT)
        cancelled = self._mk_deal('D-1203', total_cbm=Decimal('1'), status='Cancelled')
        resp = self.client.get('/api/logistics/deals/ready-to-ship/')
        self.assertEqual(resp.status_code, 200, resp.content)
        ids = [r['id'] for r in resp.data]
        self.assertIn(d1.id, ids)
        self.assertNotIn(draft.id, ids)       # manufacturing → not shippable yet
        self.assertNotIn(cancelled.id, ids)

    def test_excludes_after_shipment_creation(self):
        d1 = self._mk_deal('D-1204', total_cbm=Decimal('1'), stage=LogisticsDeal.STAGE_READY_TO_SHIP)
        self._create([d1.id], rate=10)
        resp = self.client.get('/api/logistics/deals/ready-to-ship/')
        self.assertNotIn(d1.id, [r['id'] for r in resp.data])


class ReconcileEngineTest(TestCase):
    """Pure engine invariant: largest-remainder always sums to the total exactly."""

    def test_reconcile_sums_exact_across_random(self):
        import random
        random.seed(42)
        for _ in range(200):
            total = Decimal(str(random.randint(1, 100000))) / Decimal('100')
            n = random.randint(1, 8)
            weights = [Decimal(str(random.randint(0, 50))) for _ in range(n)]
            parts = allocation.reconcile(total, weights)
            self.assertEqual(sum(parts, Decimal('0')), total.quantize(Decimal('0.01')))
            self.assertEqual(len(parts), n)
