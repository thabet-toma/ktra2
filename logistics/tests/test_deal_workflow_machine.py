"""task12 M1+M2 — آلة مراحل الصفقة + حصص الشحن:

- المراحل الثلاث الأولى يدوية حرة (من None ومن بعضها) — كان None→sw_mfg_start فقط
  فيرتد محدد المراحل دائماً (T12-A1).
- إلغاء الصفقة يثبت ولا يدوسه _sync_legacy_status_fields (T12-A2).
- إنشاء فاتورة شراء مرتبطة بصفقة → sw_released (T12-A3).
- add_deal يوزّع حصص الشحن فوراً ويرفض صفقة شركة أخرى (T12-B1/B2).
- ترقيم الصفقات server-side عند الغياب/التكرار (T12-B4).
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from partners.models import Partner
from logistics.models import (
    LogisticsDeal,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
)


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=910, CompanyName='WF Co')
        cls.other_tenant = Tenant.objects.create(TenantID=920, CompanyName='Other Co')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True}
        )
        cls.user = User.objects.create_user(username='wf_user', password='x')
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.other_tenant, role='manager')
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name='Supplier X', partner_type='Supplier'
        )
        cls.other_partner = Partner.objects.create(
            tenant=cls.other_tenant, name='Supplier Y', partner_type='Supplier'
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _mk_deal(self, ref, tenant=None, partner=None, **kw):
        return LogisticsDeal.objects.create(
            tenant=tenant or self.tenant,
            ref_number=ref,
            partner=partner or self.partner,
            order_date='2026-06-01',
            currency=self.cur,
            total_amount=kw.pop('total_amount', 1000),
            **kw,
        )


class WorkflowManualStagesTest(_Base):
    def test_pick_any_manual_stage_from_none(self):
        """صفقة جديدة: اختيار المرحلة الثالثة مباشرة يجب أن يُقبل ويثبت."""
        deal = self._mk_deal('D-0101')
        resp = self.client.patch(
            f'/api/logistics/deals/{deal.id}/',
            {'shipping_workflow_status': 'sw_wait_intl_ship'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        self.assertEqual(deal.shipping_workflow_status, 'sw_wait_intl_ship')

    def test_move_back_between_manual_stages(self):
        deal = self._mk_deal('D-0102', shipping_workflow_status='sw_wait_intl_ship')
        resp = self.client.patch(
            f'/api/logistics/deals/{deal.id}/',
            {'shipping_workflow_status': 'sw_mfg_start'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        self.assertEqual(deal.shipping_workflow_status, 'sw_mfg_start')

    def test_jump_to_auto_stage_rejected(self):
        """القفز اليدوي إلى مرحلة نهائية يُرفض 400 برسالة واضحة."""
        deal = self._mk_deal('D-0103')
        resp = self.client.patch(
            f'/api/logistics/deals/{deal.id}/',
            {'shipping_workflow_status': 'sw_released'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        deal.refresh_from_db()
        self.assertIsNone(deal.shipping_workflow_status)


class DealCancelPersistsTest(_Base):
    def test_cancel_sticks_after_save(self):
        deal = self._mk_deal('D-0201')
        resp = self.client.patch(
            f'/api/logistics/deals/{deal.id}/',
            {'status': 'Cancelled'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        self.assertEqual(deal.status, 'Cancelled')
        # حفظ لاحق لا يعيدها إلى Open
        deal.save()
        deal.refresh_from_db()
        self.assertEqual(deal.status, 'Cancelled')


class ReleasedOnInvoiceTest(_Base):
    def test_purchase_invoice_releases_deal(self):
        deal = self._mk_deal('D-0301', shipping_workflow_status='sw_wait_clearance')
        PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number='INV-T-0001',
            partner=self.partner,
            deal=deal,
            currency=self.cur,
        )
        deal.refresh_from_db()
        self.assertEqual(deal.shipping_workflow_status, 'sw_released')
        self.assertEqual(deal.status, 'Closed')

    def test_invoice_without_deal_noop(self):
        deal = self._mk_deal('D-0302')
        PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number='INV-T-0002',
            partner=self.partner,
            currency=self.cur,
        )
        deal.refresh_from_db()
        self.assertIsNone(deal.shipping_workflow_status)


class ShipmentAllocationTest(_Base):
    def _mk_shipment(self, **kw):
        return LogisticsShipment.objects.create(
            tenant=self.tenant,
            shipment_number=kw.pop('shipment_number', 'SH-T-1'),
            total_shipping_cost_usd=kw.pop('total_shipping_cost_usd', Decimal('781.10')),
            **kw,
        )

    def test_add_deal_distributes_allocations(self):
        shipment = self._mk_shipment()
        d1 = self._mk_deal('D-0401', total_cbm=Decimal('2'))
        d2 = self._mk_deal('D-0402', total_cbm=Decimal('2'))
        for d in (d1, d2):
            resp = self.client.post(
                f'/api/logistics/shipments/{shipment.id}/add_deal/',
                {'deal_id': d.id},
                format='json',
            )
            self.assertEqual(resp.status_code, 200, resp.content)
        total_alloc = sum(
            link.allocated_shipping_cost
            for link in LogisticsShipmentDeal.objects.filter(shipment=shipment)
        )
        self.assertEqual(total_alloc, Decimal('781.10'))

    def test_remove_deal_redistributes(self):
        shipment = self._mk_shipment(shipment_number='SH-T-2')
        d1 = self._mk_deal('D-0403', total_cbm=Decimal('1'))
        d2 = self._mk_deal('D-0404', total_cbm=Decimal('1'))
        for d in (d1, d2):
            self.client.post(
                f'/api/logistics/shipments/{shipment.id}/add_deal/',
                {'deal_id': d.id}, format='json',
            )
        resp = self.client.post(
            f'/api/logistics/shipments/{shipment.id}/remove_deal/',
            {'deal_id': d2.id}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        link = LogisticsShipmentDeal.objects.get(shipment=shipment)
        self.assertEqual(link.allocated_shipping_cost, Decimal('781.10'))

    def test_add_deal_rejects_other_tenant_deal(self):
        shipment = self._mk_shipment(shipment_number='SH-T-3')
        foreign = self._mk_deal(
            'D-0405', tenant=self.other_tenant, partner=self.other_partner
        )
        resp = self.client.post(
            f'/api/logistics/shipments/{shipment.id}/add_deal/',
            {'deal_id': foreign.id}, format='json',
        )
        self.assertEqual(resp.status_code, 404, resp.content)
        self.assertFalse(
            LogisticsShipmentDeal.objects.filter(shipment=shipment).exists()
        )


class ServerSideDealNumberTest(_Base):
    def _post_deal(self, ref):
        return self.client.post(
            '/api/logistics/deals/',
            {
                'ref_number': ref,
                'partner': self.partner.id,
                'order_date': '2026-06-01',
                'currency': self.cur.CurrencyID,
                'items': [],
            },
            format='json',
        )

    def test_duplicate_ref_regenerated(self):
        self._mk_deal('D-0001')
        resp = self.client.post(
            '/api/logistics/deals/',
            {
                'ref_number': 'D-0001',
                'partner': self.partner.id,
                'order_date': '2026-06-01',
                'currency': self.cur.CurrencyID,
                'items': [],
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.data['ref_number'], 'D-0002')

    def test_missing_ref_generated(self):
        resp = self.client.post(
            '/api/logistics/deals/',
            {
                'partner': self.partner.id,
                'order_date': '2026-06-01',
                'currency': self.cur.CurrencyID,
                'items': [],
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(str(resp.data['ref_number']).startswith('D-'))
