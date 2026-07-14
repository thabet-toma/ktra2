"""M3 — unified stage machine.

`stage` is canonical; the legacy cache columns (status/order_status/payment_status/
shipping_workflow_status) are strictly derived. Every automated advance routes
through the ONE guarded service (no bulk-.update bypass — RC-7), and manual PATCHes
keep `stage` in step (single source of truth — RC-2).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from partners.models import Partner
from logistics.models import (
    LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal,
    LogisticsClearance, PurchaseInvoice,
)
from logistics.domain import stages


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=950, CompanyName='M3 Co')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
        cls.user = User.objects.create_user(username='m3_user', password='x')
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

    def _shipment_with(self, *deals, unit='cbm', rate=10):
        resp = self.client.post(
            '/api/logistics/shipments/create-from-deals/',
            {'deal_ids': [d.id for d in deals], 'chargeable_unit': unit, 'freight_rate': rate},
            format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return LogisticsShipment.objects.get(pk=resp.data['id'])


class AutomatedTransitionsTest(_Base):
    def test_link_to_shipment_sets_in_shipment(self):
        d = self._mk_deal('D-3001', total_cbm=Decimal('1'))
        self._shipment_with(d)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_IN_SHIPMENT)
        self.assertEqual(d.shipping_workflow_status, 'sw_wait_arrival')

    def test_clearance_sets_at_clearance(self):
        d = self._mk_deal('D-3002', total_cbm=Decimal('1'))
        sh = self._shipment_with(d)
        LogisticsClearance.objects.create(tenant=self.tenant, shipment=sh)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_AT_CLEARANCE)
        self.assertEqual(d.shipping_workflow_status, 'sw_wait_clearance')

    def test_invoice_sets_invoiced_and_closed(self):
        d = self._mk_deal('D-3003', shipping_workflow_status='sw_wait_clearance')
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number='PI-3003',
            partner=self.partner, deal=d, currency=self.cur)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_INVOICED)
        self.assertEqual(d.shipping_workflow_status, 'sw_released')
        self.assertEqual(d.status, 'Closed')

    def test_clearance_does_not_regress_invoiced_deal(self):
        d = self._mk_deal('D-3004', total_cbm=Decimal('1'))
        sh = self._shipment_with(d)
        # Release via invoice first
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number='PI-3004',
            partner=self.partner, deal=d, shipment=sh, currency=self.cur)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_INVOICED)
        # Now a clearance on the same shipment must NOT drag it back to at_clearance
        LogisticsClearance.objects.create(tenant=self.tenant, shipment=sh)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_INVOICED)


class ManualPatchKeepsStageSyncedTest(_Base):
    def test_manual_workflow_patch_updates_stage(self):
        d = self._mk_deal('D-3101')
        resp = self.client.patch(
            f'/api/logistics/deals/{d.id}/',
            {'shipping_workflow_status': 'sw_wait_intl_ship'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_READY_TO_SHIP)

    def test_cancel_sets_stage_cancelled(self):
        d = self._mk_deal('D-3102')
        resp = self.client.patch(
            f'/api/logistics/deals/{d.id}/', {'status': 'Cancelled'}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_CANCELLED)


class GuardedServiceTest(_Base):
    def test_advance_rejects_invalid_edge_without_force(self):
        d = self._mk_deal('D-3201')  # stage draft
        with self.assertRaises(ValidationError):
            stages.advance_deal_stage(d, LogisticsDeal.STAGE_INVOICED)

    def test_advance_idempotent(self):
        d = self._mk_deal('D-3202')
        stages.advance_deal_stage(d, LogisticsDeal.STAGE_READY_TO_SHIP)
        # Re-issuing the same target is a no-op success.
        result = stages.advance_deal_stage(d, LogisticsDeal.STAGE_READY_TO_SHIP)
        self.assertEqual(result, LogisticsDeal.STAGE_READY_TO_SHIP)

    def test_forward_edge_allowed(self):
        d = self._mk_deal('D-3203')
        stages.advance_deal_stage(d, LogisticsDeal.STAGE_READY_TO_SHIP)
        stages.advance_deal_stage(d, LogisticsDeal.STAGE_IN_SHIPMENT)
        d.refresh_from_db()
        self.assertEqual(d.stage, LogisticsDeal.STAGE_IN_SHIPMENT)
