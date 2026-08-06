"""مرشد رحلة الاستيراد — نقطة الحقائق الخام التي يقرأها المرشد في كل الشاشات.

الخادم هنا **لا يقرر** الخطوة التالية (قرار المراحل في مصدر واحد بالواجهة)؛
يجمّع الوقائع فقط: عروض بانتظار قرار، صفقات ودفعاتها، وشحنات وحالة الشحن
والتخليص والنقل المحلي والفاتورة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from logistics.models import (
    LocalShipment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsDeal,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
    SupplierQuotation,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


D = lambda value: Decimal(str(value))


class ImportJourneySummaryTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="journey-guide", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة مرشد الاستيراد", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)

        cls.agent_ap = Account.objects.create(
            tenant=cls.tenant, code="AP-AGENT-J", name="ذمم وكيل الشحن",
            account_type="Liability", is_active=True,
        )
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل الشحن", partner_type="ShippingAgent",
            linked_account=cls.agent_ap,
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="المصنع الصيني", partner_type="Supplier",
        )
        cls.carrier = Partner.objects.create(
            tenant=cls.tenant, name="الناقل المحلي", partner_type="LocalTransporter",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _get(self):
        return self.client.get("/api/logistics/import-journey/", **self._auth())

    def _deal(self, ref, *, total="1000", stage="sw_mfg_start"):
        return LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=ref, partner=self.supplier,
            order_date="2026-07-01", total_amount=D(total), currency=self.usd,
            shipping_workflow_status=stage,
        )

    # ── العروض ──
    def test_import_offers_awaiting_decision_are_counted(self):
        for i, st in enumerate(["draft", "sent", "under_discussion", "accepted", "converted"]):
            SupplierQuotation.objects.create(
                tenant=self.tenant, quotation_number=f"IQ-{i}", scope="import",
                supplier=self.supplier, quotation_date="2026-07-01",
                status=st, currency=self.usd,
            )
        # عرض شراء محلي لا يخصّ رحلة الاستيراد إطلاقاً
        SupplierQuotation.objects.create(
            tenant=self.tenant, quotation_number="PQ-1", scope="local",
            supplier=self.supplier, quotation_date="2026-07-01",
            status="sent", currency=self.usd,
        )
        data = self._get().json()
        self.assertEqual(data["offers"]["awaiting_decision"], 3)
        self.assertEqual(data["offers"]["accepted_not_converted"], 1)

    # ── الصفقات ودفعاتها ──
    def test_deal_row_reports_payment_count_and_remaining(self):
        deal = self._deal("D-1", total="1000")
        LogisticsPayment.objects.create(
            deal=deal, payment_number=1, amount=D("400"), confirmed_by_supplier=True,
        )
        LogisticsPayment.objects.create(deal=deal, payment_number=2, amount=D("300"))
        data = self._get().json()
        row = next(r for r in data["deals"]["rows"] if r["id"] == deal.pk)
        self.assertEqual(row["payments_count"], 2)
        self.assertEqual(row["pending_payments_count"], 1)
        self.assertEqual(Decimal(row["paid"]), D("400"))
        self.assertEqual(Decimal(row["remaining"]), D("600"))
        self.assertIsNone(row["shipment_id"])
        self.assertEqual(data["deals"]["without_shipment"], 1)

    def test_released_and_cancelled_deals_leave_the_active_journey(self):
        self._deal("D-DONE", stage="sw_released")
        cancelled = self._deal("D-CANCEL")
        cancelled.status = "Cancelled"
        cancelled.save(update_fields=["status"])
        live = self._deal("D-LIVE")
        data = self._get().json()
        self.assertEqual([r["id"] for r in data["deals"]["rows"]], [live.pk])

    # ── الشحنات ──
    def test_shipment_row_carries_every_stage_fact(self):
        deal = self._deal("D-SHIP")
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-J1", shipment_name="شحنة المرشد",
            shipping_agent=self.agent, total_shipping_cost_usd=D("2000"),
            departure_date="2026-07-01",
        )
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        LogisticsPayment.objects.create(
            shipment=shipment, payment_number=1, amount=D("500"),
            confirmed_by_supplier=True,
        )
        clearance = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=shipment, declaration_number="DEC-9",
            customs_broker=self.agent,
        )
        LogisticsClearanceLine.objects.create(
            clearance=clearance, seq=1, description="رسوم البيان", debit=D("350"),
        )
        LocalShipment.objects.create(
            tenant=self.tenant, shipment=shipment, carrier=self.carrier,
            amount=D("180"), currency=self.ils,
        )

        row = next(r for r in self._get().json()["shipments"] if r["id"] == shipment.pk)
        self.assertEqual(row["deals_count"], 1)
        self.assertEqual(Decimal(row["freight_total_usd"]), D("2000"))
        self.assertEqual(Decimal(row["freight_paid_usd"]), D("500"))
        self.assertFalse(row["freight_is_posted"])
        self.assertEqual(row["clearance_id"], clearance.pk)
        self.assertEqual(Decimal(row["clearance_cost"]), D("350"))
        self.assertEqual(row["local_count"], 1)
        self.assertEqual(Decimal(row["local_remaining"]), D("180"))
        self.assertEqual(row["invoices_count"], 0)
        self.assertEqual(row["remaining_deals"], 1)

    def test_shipment_without_deals_still_appears_so_the_guide_can_ask_for_them(self):
        LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-EMPTY", departure_date="2026-07-01",
        )
        numbers = [r["number"] for r in self._get().json()["shipments"]]
        self.assertIn("SH-EMPTY", numbers)

    # ── العزل ──
    def test_another_company_sees_nothing_of_ours(self):
        self._deal("D-MINE")
        other_user = User.objects.create_user(username="journey-other", password="x")
        other = create_company("شركة أخرى", other_user)
        self.client.force_authenticate(user=other_user)
        resp = self.client.get(
            "/api/logistics/import-journey/",
            HTTP_X_TENANT_ID=str(other.TenantID),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["deals"]["rows"], [])
