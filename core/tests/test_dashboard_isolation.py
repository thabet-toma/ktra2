"""task13 M1 — /api/dashboard/ tenant isolation.

The owner's screenshot showed a freshly created company whose dashboard
displayed 66 deals and a 32,924 inventory value belonging to another company:
`trade_dashboard` resolved the tenant and then never used it. These tests hit
the real endpoint and prove a new company sees zeros while the old company
still sees its own numbers.
"""
import datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account, Currency, JournalHeader, JournalLine
from inventory.models import Product, StockMovement
from logistics.models import LogisticsDeal, LogisticsPayment, LogisticsShipment, PurchaseInvoice
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import RolePermission, UserCompanyMembership
from tenants.services import create_company


class DashboardIsolationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="dash_a", password="x")
        cls.owner_b = User.objects.create_user(username="dash_b", password="x")
        cls.staff_a = User.objects.create_user(username="dash_staff_a", password="x")
        cls.t_a = create_company("الشركة القديمة", cls.owner_a)
        cls.t_b = create_company("الشركة الجديدة", cls.owner_b)
        UserCompanyMembership.objects.create(
            user=cls.staff_a, tenant=cls.t_a, role="staff", can_access_import=False
        )
        # T-DASHPERIOD: تجاوز قديم متعمد لإثبات أنه لا يفتح ملخص المدير.
        RolePermission.objects.create(
            tenant=cls.t_a, role="staff",
            permission_key="admin.dashboard.view", allowed=True,
        )
        cls.t_a.import_enabled = True
        cls.t_a.save(update_fields=["import_enabled"])

        currency = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        partner = Partner.objects.create(tenant=cls.t_a, name="مورد قديم", partner_type="Supplier")
        deal = LogisticsDeal.objects.create(
            tenant=cls.t_a, ref_number="D-0001", partner=partner, currency=currency,
            status="Open", total_amount=1000, order_date=timezone.localdate(),
        )
        LogisticsPayment.objects.create(deal=deal, amount=250, is_posted=True,
                                        transfer_date=timezone.localdate())
        LogisticsShipment.objects.create(tenant=cls.t_a, shipment_number="SH-1", status="In-Transit")
        PurchaseInvoice.objects.create(
            tenant=cls.t_a, invoice_number="INV-1", partner=partner, currency=currency,
            invoice_date=timezone.localdate(), status="draft", grand_total=500,
        )
        Product.objects.create(tenant=cls.t_a, sku="OLD-1", name_ar="صنف قديم",
                               quantity_on_hand=10, avg_cost=7)
        customer = Partner.objects.create(
            tenant=cls.t_a, name="عميل قديم", partner_type="Customer"
        )
        SalesInvoice.objects.create(
            tenant=cls.t_a,
            invoice_number="SALE-1",
            customer=customer,
            invoice_date=timezone.localdate(),
            currency=currency,
            status=SalesInvoice.STATUS_POSTED,
            grand_total=900,
        )
        revenue_account = Account.objects.create(
            tenant=cls.t_a, code="DASH-REV", name="إيرادات الاختبار", account_type="Revenue"
        )
        expense_account = Account.objects.create(
            tenant=cls.t_a, code="DASH-EXP", name="مصروفات الاختبار", account_type="Expense"
        )
        journal = JournalHeader.objects.create(
            tenant=cls.t_a,
            transaction_date=timezone.localdate(),
            is_posted=True,
            currency=currency,
            exchange_rate=1,
        )
        JournalLine.objects.create(
            tenant=cls.t_a, journal=journal, account=revenue_account, credit=900
        )
        JournalLine.objects.create(
            tenant=cls.t_a, journal=journal, account=expense_account, debit=250
        )

        # Even if legacy import records exist, a company with the module off
        # must not query or expose an import section.
        hidden_partner = Partner.objects.create(
            tenant=cls.t_b, name="مورد مخفي", partner_type="Supplier"
        )
        LogisticsDeal.objects.create(
            tenant=cls.t_b,
            ref_number="HIDDEN-DEAL",
            partner=hidden_partner,
            currency=currency,
            status="Open",
            total_amount=777,
            order_date=timezone.localdate(),
        )
        PurchaseInvoice.objects.create(
            tenant=cls.t_b,
            invoice_number="HIDDEN-INTL",
            partner=hidden_partner,
            currency=currency,
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            grand_total=333,
        )

    def _dashboard(self, user, tenant):
        self.client.force_authenticate(user=user)
        res = self.client.get("/api/dashboard/", HTTP_X_TENANT_ID=str(tenant.TenantID))
        assert res.status_code == 200, f"{res.status_code}: {res.content[:200]}"
        return res.json()

    def test_new_company_dashboard_all_zero(self):
        data = self._dashboard(self.owner_b, self.t_b)
        assert "import_operations" not in data
        assert data["financials"] == {
            "revenue": 0.0,
            "expenses": 0.0,
            "net_profit": 0.0,
        }
        assert data["sales_invoices"]["total"] == 0
        # International invoices belong to the disabled import module.
        assert data["purchase_invoices"]["total"] == 0
        assert data["purchase_invoices"]["recent"] == []
        assert data["inventory"]["total_products"] == 0
        assert data["inventory"]["inventory_value"] == 0.0
        assert data["inventory"]["low_stock_items"] == []
        assert data["accounting"]["journals_this_month"] == 0
        assert data["alerts"] == []

    def test_old_company_still_sees_its_numbers(self):
        data = self._dashboard(self.owner_a, self.t_a)
        assert data["import_operations"]["deals"]["open"] == 1
        assert data["import_operations"]["deals"]["active_value"] == 1000.0
        assert data["import_operations"]["payments"]["paid_this_month"] == 250.0
        assert data["import_operations"]["shipments"]["in_transit"] == 1
        assert data["sales_invoices"]["total"] == 1
        assert data["sales_invoices"]["recent"][0]["currency_code"] == "ILS"
        assert data["purchase_invoices"]["draft"] == 1
        assert data["inventory"]["total_products"] == 1
        assert data["inventory"]["inventory_value"] == 70.0
        assert data["financials"]["revenue"] == 900.0
        assert data["financials"]["expenses"] == 250.0
        assert data["financials"]["net_profit"] == 650.0

    def test_enabled_company_staff_cannot_see_business_summary(self):
        self.client.force_authenticate(user=self.staff_a)
        res = self.client.get(
            "/api/dashboard/", HTTP_X_TENANT_ID=str(self.t_a.TenantID))
        assert res.status_code == 403

    def test_manager_configured_month_start_filters_cycle_to_date(self):
        today = datetime.date(2026, 7, 26)
        period_start = datetime.date(2026, 7, 20)
        before_period = datetime.date(2026, 7, 19)
        settings = self.t_a.settings
        settings.dashboard_month_start_day = 20
        settings.save(update_fields=["dashboard_month_start_day"])

        currency = Currency.objects.get(Code="ILS")
        customer = Partner.objects.filter(
            tenant=self.t_a, partner_type="Customer").first()
        supplier = Partner.objects.filter(
            tenant=self.t_a, partner_type="Supplier").first()
        product = Product.objects.filter(tenant=self.t_a).first()
        revenue_account = Account.objects.get(tenant=self.t_a, code="DASH-REV")
        expense_account = Account.objects.get(tenant=self.t_a, code="DASH-EXP")
        SalesInvoice.objects.filter(
            tenant=self.t_a, invoice_number="SALE-1"
        ).update(invoice_date=before_period)
        PurchaseInvoice.objects.filter(
            tenant=self.t_a, invoice_number="INV-1"
        ).update(invoice_date=before_period)
        JournalHeader.objects.filter(tenant=self.t_a).update(
            transaction_date=before_period
        )
        LogisticsPayment.objects.filter(deal__tenant=self.t_a).update(
            transfer_date=before_period
        )

        SalesInvoice.objects.create(
            tenant=self.t_a,
            invoice_number="SALE-IN-PERIOD",
            customer=customer,
            invoice_date=period_start,
            currency=currency,
            status=SalesInvoice.STATUS_POSTED,
            grand_total=100,
        )
        PurchaseInvoice.objects.create(
            tenant=self.t_a,
            invoice_number="PURCHASE-IN-PERIOD",
            invoice_date=today,
            partner=supplier,
            currency=currency,
            status="completed",
            grand_total=40,
        )
        journal = JournalHeader.objects.create(
            tenant=self.t_a,
            transaction_date=period_start,
            is_posted=True,
            currency=currency,
            exchange_rate=1,
        )
        JournalLine.objects.create(
            tenant=self.t_a, journal=journal, account=revenue_account, credit=100)
        JournalLine.objects.create(
            tenant=self.t_a, journal=journal, account=expense_account, debit=40)
        StockMovement.objects.create(
            tenant=self.t_a,
            product=product,
            movement_type="IN",
            quantity=1,
            movement_date=today,
        )
        StockMovement.objects.create(
            tenant=self.t_a,
            product=product,
            movement_type="IN",
            quantity=1,
            movement_date=before_period,
        )
        LogisticsPayment.objects.create(
            deal=LogisticsDeal.objects.filter(tenant=self.t_a).first(),
            amount=75,
            is_posted=True,
            transfer_date=today,
        )

        cache.clear()
        with patch("core.dashboard_api.timezone.localdate", return_value=today):
            data = self._dashboard(self.owner_a, self.t_a)

        assert data["period"] == {
            "from": period_start.isoformat(),
            "to": today.isoformat(),
        }
        assert data["financials"] == {
            "revenue": 100.0,
            "expenses": 40.0,
            "net_profit": 60.0,
        }
        assert data["sales_invoices"]["total"] == 1
        assert data["purchase_invoices"]["total"] == 1
        assert data["inventory"]["movements_this_month"] == 1
        assert data["accounting"]["journals_this_month"] == 1
        assert data["import_operations"]["payments"]["paid_this_month"] == 75.0

    def test_month_start_before_boundary_uses_previous_month(self):
        settings = self.t_a.settings
        settings.dashboard_month_start_day = 20
        settings.save(update_fields=["dashboard_month_start_day"])
        today = datetime.date(2026, 6, 19)

        cache.clear()
        with patch("core.dashboard_api.timezone.localdate", return_value=today):
            data = self._dashboard(self.owner_a, self.t_a)

        assert data["period"] == {
            "from": "2026-05-20",
            "to": "2026-06-19",
        }

    def test_month_start_boundary_begins_new_cycle(self):
        settings = self.t_a.settings
        settings.dashboard_month_start_day = 20
        settings.save(update_fields=["dashboard_month_start_day"])
        today = datetime.date(2026, 6, 20)

        cache.clear()
        with patch("core.dashboard_api.timezone.localdate", return_value=today):
            data = self._dashboard(self.owner_a, self.t_a)

        assert data["period"] == {
            "from": "2026-06-20",
            "to": "2026-06-20",
        }

    def test_month_start_day_31_clamps_to_short_month(self):
        settings = self.t_a.settings
        settings.dashboard_month_start_day = 31
        settings.save(update_fields=["dashboard_month_start_day"])
        today = datetime.date(2026, 2, 27)

        cache.clear()
        with patch("core.dashboard_api.timezone.localdate", return_value=today):
            data = self._dashboard(self.owner_a, self.t_a)

        assert data["period"] == {
            "from": "2026-01-31",
            "to": "2026-02-27",
        }

    def test_missing_tenant_header_returns_zeros_not_leak(self):
        """بلا X-Tenant-Id (وبوجود أكثر من شركة) — أصفار، لا تجميع عالمي."""
        self.client.force_authenticate(user=self.owner_b)
        res = self.client.get("/api/dashboard/")
        assert res.status_code == 200
        data = res.json()
        assert "import_operations" not in data
        assert data["sales_invoices"]["total"] == 0
        assert data["inventory"]["total_products"] == 0
