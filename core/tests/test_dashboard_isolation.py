"""task13 M1 — /api/dashboard/ tenant isolation.

The owner's screenshot showed a freshly created company whose dashboard
displayed 66 deals and a 32,924 inventory value belonging to another company:
`trade_dashboard` resolved the tenant and then never used it. These tests hit
the real endpoint and prove a new company sees zeros while the old company
still sees its own numbers.
"""
import datetime

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Currency
from inventory.models import Product
from logistics.models import LogisticsDeal, LogisticsPayment, LogisticsShipment, PurchaseInvoice
from partners.models import Partner
from tenants.services import create_company


class DashboardIsolationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="dash_a", password="x")
        cls.owner_b = User.objects.create_user(username="dash_b", password="x")
        cls.t_a = create_company("الشركة القديمة", cls.owner_a)
        cls.t_b = create_company("الشركة الجديدة", cls.owner_b)

        currency = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        partner = Partner.objects.create(tenant=cls.t_a, name="مورد قديم", partner_type="Supplier")
        deal = LogisticsDeal.objects.create(
            tenant=cls.t_a, ref_number="D-0001", partner=partner, currency=currency,
            status="Open", total_amount=1000, order_date=datetime.date.today(),
        )
        LogisticsPayment.objects.create(deal=deal, amount=250, is_posted=True,
                                        transfer_date=datetime.date.today())
        LogisticsShipment.objects.create(tenant=cls.t_a, shipment_number="SH-1", status="In-Transit")
        PurchaseInvoice.objects.create(
            tenant=cls.t_a, invoice_number="INV-1", partner=partner, currency=currency,
            status="draft", grand_total=500,
        )
        Product.objects.create(tenant=cls.t_a, sku="OLD-1", name_ar="صنف قديم",
                               quantity_on_hand=10, avg_cost=7)

    def _dashboard(self, user, tenant):
        self.client.force_authenticate(user=user)
        res = self.client.get("/api/dashboard/", HTTP_X_TENANT_ID=str(tenant.TenantID))
        assert res.status_code == 200, f"{res.status_code}: {res.content[:200]}"
        return res.json()

    def test_new_company_dashboard_all_zero(self):
        data = self._dashboard(self.owner_b, self.t_b)
        assert data["deals"]["total"] == 0
        assert data["deals"]["open_value"] == 0.0
        assert data["deals"]["recent"] == []
        assert data["shipments"]["total"] == 0
        assert data["shipments"]["recent"] == []
        assert data["payments"]["total"] == 0
        assert data["payments"]["total_paid"] == 0.0
        assert data["invoices"]["total"] == 0
        assert data["invoices"]["recent"] == []
        assert data["inventory"]["total_products"] == 0
        assert data["inventory"]["inventory_value"] == 0.0
        assert data["inventory"]["low_stock_items"] == []
        assert data["accounting"]["journals_this_month"] == 0
        assert data["alerts"] == []

    def test_old_company_still_sees_its_numbers(self):
        data = self._dashboard(self.owner_a, self.t_a)
        assert data["deals"]["total"] == 1
        assert data["deals"]["open_value"] == 1000.0
        assert data["payments"]["total_paid"] == 250.0
        assert data["shipments"]["in_transit"] == 1
        assert data["invoices"]["draft"] == 1
        assert data["inventory"]["total_products"] == 1
        assert data["inventory"]["inventory_value"] == 70.0

    def test_missing_tenant_header_returns_zeros_not_leak(self):
        """بلا X-Tenant-Id (وبوجود أكثر من شركة) — أصفار، لا تجميع عالمي."""
        self.client.force_authenticate(user=self.owner_b)
        res = self.client.get("/api/dashboard/")
        assert res.status_code == 200
        data = res.json()
        assert data["deals"]["total"] == 0
        assert data["inventory"]["total_products"] == 0
