"""حذف الشحنة يعيد صفقاتها «جاهزة للشحن» — ولا استحقاق ولا دفعة على شحنة محذوفة.

إنتاج: حذف SH-0017 ترك D-0111 في in_shipment فاختفت من ready-to-ship؛ وتخليص
الشحنة المحذوفة S-0016 قَبِل استحقاق 1,500 لأن التخليص لا يُخفى مع شحنته.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from logistics.accruals import AccrualSkipped, post_freight_accrual
from logistics.models import (
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsDeal,
    LogisticsShipment,
    LogisticsShipmentDeal,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class ShipmentDeleteReleasesDealsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="shd", password="x", email="shd@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة الشحن", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")
        broker_ap = Account.objects.create(
            tenant=cls.tenant, code="AP-BR", name="ذمم مخلّص",
            account_type="Liability", is_active=True)
        cls.broker = Partner.objects.create(
            tenant=cls.tenant, name="مخلّص", partner_type="Supplier", linked_account=broker_ap)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        self.deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-0111", partner=self.supplier,
            order_date="2026-09-01", total_amount=D("1000"), currency=self.usd,
            stage=LogisticsDeal.STAGE_READY_TO_SHIP, shipping_workflow_status="sw_wait_intl_ship")
        self.shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-0017")
        LogisticsShipmentDeal.objects.create(shipment=self.shipment, deal=self.deal)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, LogisticsDeal.STAGE_IN_SHIPMENT)

    def _ready_ids(self):
        resp = self.client.get("/api/logistics/deals/ready-to-ship/", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        rows = data.get("results", data) if isinstance(data, dict) else data
        return {r["id"] for r in rows}

    def _delete(self):
        return self.client.delete(f"/api/logistics/shipments/{self.shipment.pk}/", **self.h)

    def _clearance(self, **extra):
        clearance = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=self.shipment, customs_broker=self.broker,
            status="Processing", currency=self.ils, **extra)
        LogisticsClearanceLine.objects.create(
            clearance=clearance, seq=1, line_type="declaration_fee",
            description="رسوم", debit=D("1500"), credit=D("0"))
        return clearance

    def test_delete_returns_deal_to_ready_to_ship(self):
        self.assertNotIn(self.deal.pk, self._ready_ids())
        resp = self._delete()
        self.assertEqual(resp.status_code, 204, resp.content)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, LogisticsDeal.STAGE_READY_TO_SHIP)
        self.assertFalse(LogisticsShipmentDeal.objects.filter(deal=self.deal).exists())
        self.assertIn(self.deal.pk, self._ready_ids())

    def test_remove_deal_returns_deal_to_ready_to_ship(self):
        resp = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/remove_deal/",
            {"deal_id": self.deal.pk}, format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, LogisticsDeal.STAGE_READY_TO_SHIP)

    def test_delete_removes_unposted_clearance_and_releases_deal(self):
        clearance = self._clearance()
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, LogisticsDeal.STAGE_AT_CLEARANCE)
        resp = self._delete()
        self.assertEqual(resp.status_code, 204, resp.content)
        self.assertFalse(LogisticsClearance.objects.filter(pk=clearance.pk).exists())
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.stage, LogisticsDeal.STAGE_READY_TO_SHIP)

    def test_delete_refused_when_clearance_accrual_posted(self):
        clearance = self._clearance()
        resp = self.client.post(
            f"/api/logistics/clearances/{clearance.pk}/post-to-accounting/", **self.h)
        self.assertEqual(resp.status_code, 201, resp.content)
        resp = self._delete()
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("استحقاق", resp.json()["detail"])
        self.shipment.refresh_from_db()
        self.assertFalse(self.shipment.is_deleted)
        self.assertTrue(LogisticsShipmentDeal.objects.filter(deal=self.deal).exists())

    def test_delete_refused_when_deal_past_clearance(self):
        LogisticsDeal.objects.filter(pk=self.deal.pk).update(
            stage=LogisticsDeal.STAGE_INVOICED, shipping_workflow_status="sw_released")
        resp = self._delete()
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("D-0111", resp.json()["detail"])
        self.assertTrue(LogisticsShipmentDeal.objects.filter(deal=self.deal).exists())

    def test_deleted_shipment_clearance_refuses_accrual_and_payment(self):
        # شحنة حُذفت قبل الإصلاح: التخليص بقي ظاهراً وأزراره تعمل.
        clearance = self._clearance()
        self.shipment.refresh_from_db()
        self.shipment.delete()
        resp = self.client.post(
            f"/api/logistics/clearances/{clearance.pk}/post-to-accounting/", **self.h)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("محذوفة", resp.json()["error"])
        self.assertFalse(JournalHeader.objects.filter(
            reference_type="LOGISTICS_CLEARANCE", reference_id=clearance.pk).exists())
        resp = self.client.post(
            f"/api/logistics/clearances/{clearance.pk}/pay_from_cashbox/",
            {"amount": "100", "cash_box_external_id": "x"}, format="json", **self.h)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("محذوفة", resp.json()["error"])

    def test_deleted_shipment_refuses_freight_accrual(self):
        agent = Partner.objects.create(
            tenant=self.tenant, name="وكيل", partner_type="Supplier",
            linked_account=self.broker.linked_account)
        self.shipment.shipping_agent = agent
        self.shipment.total_shipping_cost_usd = D("500")
        self.shipment.save()
        self.shipment.delete()
        with self.assertRaisesMessage(AccrualSkipped, "محذوفة"):
            post_freight_accrual(self.shipment, D("3.5"))
