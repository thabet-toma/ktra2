"""Regression coverage for bounded sales list contracts and server filters."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import Account
from partners.models import Partner
from sales.models import CustomerPayment, SalesInvoice, SalesQuotation, SupplierPayment
from tenants.models import Currency, Tenant, UserCompanyMembership


class SalesListPaginationFilterTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sales_list_bounds", password="x")
        cls.tenant = Tenant.objects.create(
            TenantID=901, CompanyName="Sales list A", SubscriptionPlan="Enterprise", Status="Active",
        )
        cls.other_tenant = Tenant.objects.create(
            TenantID=902, CompanyName="Sales list B", SubscriptionPlan="Enterprise", Status="Active",
        )
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager", is_default=True,
        )
        cls.currency, _ = Currency.objects.get_or_create(
            Code="PGT", defaults={"Name": "Pagination", "Symbol": "P"},
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الهدف", legal_name="Target Customer",
            partner_type="Customer",
        )
        cls.other_customer = Partner.objects.create(
            tenant=cls.other_tenant, name="عميل شركة أخرى", partner_type="Customer",
        )
        for i in range(24):
            SalesInvoice.objects.create(
                tenant=cls.tenant,
                invoice_number=f"INV-BOUND-{i:02d}",
                customer=cls.customer,
                invoice_date=date(2026, 7, 1) + timedelta(days=i % 10),
                invoice_type="cash" if i % 2 == 0 else "credit",
                status="posted" if i % 3 == 0 else "draft",
                currency=cls.currency,
                grand_total=Decimal(i + 1),
            )
        SalesInvoice.objects.create(
            tenant=cls.other_tenant, invoice_number="INV-BOUND-SECRET",
            customer=cls.other_customer, invoice_date=date(2026, 7, 5),
            currency=cls.currency,
        )
        for i in range(8):
            SalesQuotation.objects.create(
                tenant=cls.tenant, quotation_number=f"QT-BOUND-{i}",
                customer=cls.customer, quotation_date=date(2026, 7, 1) + timedelta(days=i),
                status="sent" if i % 2 else "draft", currency=cls.currency,
            )
        cls.other_quotation = SalesQuotation.objects.create(
            tenant=cls.other_tenant, quotation_number="QT-BOUND-SECRET",
            customer=cls.other_customer, quotation_date=date(2026, 7, 5),
            currency=cls.currency,
        )
        cls.cash_account = Account.objects.create(
            tenant=cls.tenant, code="CASH-BOUND-A", name="صندوق شركة أ",
            account_type="Asset", is_active=True,
        )
        cls.other_cash_account = Account.objects.create(
            tenant=cls.other_tenant, code="CASH-BOUND-B", name="صندوق شركة ب",
            account_type="Asset", is_active=True,
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد شركة أ", partner_type="Supplier",
        )
        cls.other_supplier = Partner.objects.create(
            tenant=cls.other_tenant, name="مورد شركة ب", partner_type="Supplier",
        )
        cls.customer_payment = CustomerPayment.objects.create(
            tenant=cls.tenant, partner=cls.customer, payment_date=date(2026, 7, 5),
            amount=Decimal("25.00"), currency=cls.currency,
            cash_or_bank_account=cls.cash_account,
        )
        cls.other_customer_payment = CustomerPayment.objects.create(
            tenant=cls.other_tenant, partner=cls.other_customer,
            payment_date=date(2026, 7, 5), amount=Decimal("35.00"),
            currency=cls.currency, cash_or_bank_account=cls.other_cash_account,
        )
        cls.supplier_payment = SupplierPayment.objects.create(
            tenant=cls.tenant, partner=cls.supplier, payment_date=date(2026, 7, 5),
            amount=Decimal("45.00"), currency=cls.currency,
            cash_or_bank_account=cls.cash_account,
        )
        cls.other_supplier_payment = SupplierPayment.objects.create(
            tenant=cls.other_tenant, partner=cls.other_supplier,
            payment_date=date(2026, 7, 5), amount=Decimal("55.00"),
            currency=cls.currency, cash_or_bank_account=cls.other_cash_account,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_invoice_page_is_bounded_filtered_and_tenant_isolated(self):
        response = self.client.get(
            "/api/sales/invoices/?page=1&page_size=5&search=Target&invoice_type=cash"
            "&status=posted&date_from=2026-07-01&date_to=2026-07-10",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        payload = response.json()
        self.assertLessEqual(len(payload["results"]), 5)
        self.assertTrue(payload["results"])
        self.assertTrue(all(row["invoice_type"] == "cash" for row in payload["results"]))
        self.assertTrue(all(row["status"] == "posted" for row in payload["results"]))
        self.assertNotIn("INV-BOUND-SECRET", {row["invoice_number"] for row in payload["results"]})

    def _invoice_query_count(self, page_size):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                f"/api/sales/invoices/?page=1&page_size={page_size}", **self.headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any("sales_module_invoice_lines" in q["sql"].lower() for q in captured))
        return len(captured)

    def test_invoice_list_query_count_is_constant_as_page_grows(self):
        self.assertEqual(self._invoice_query_count(5), self._invoice_query_count(20))

    def test_quotation_server_filters_apply_before_pagination(self):
        response = self.client.get(
            "/api/sales/quotations/?page=1&page_size=3&search=QT-BOUND&status=sent"
            "&date_from=2026-07-02&date_to=2026-07-08",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        payload = response.json()
        self.assertLessEqual(len(payload["results"]), 3)
        self.assertEqual(payload["count"], 4)
        self.assertTrue(all(row["status"] == "sent" for row in payload["results"]))

    @staticmethod
    def _result_ids(response):
        payload = response.json()
        rows = payload.get("results", []) if isinstance(payload, dict) else payload
        return {row["id"] for row in rows}

    def test_financial_lists_fail_closed_without_tenant(self):
        for url in (
            "/api/sales/invoices/?page=1",
            "/api/sales/payments/?page=1",
            "/api/sales/quotations/?page=1",
            "/api/logistics/supplier-payments/?page=1",
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, response.content[:300])
                self.assertEqual(response.json()["count"], 0)
                self.assertEqual(response.json()["results"], [])

    def test_financial_lists_exclude_other_tenant_rows(self):
        cases = (
            ("/api/sales/payments/?page=1", self.other_customer_payment.id),
            ("/api/sales/quotations/?page=1", self.other_quotation.id),
            ("/api/logistics/supplier-payments/?page=1", self.other_supplier_payment.id),
        )
        for url, foreign_id in cases:
            with self.subTest(url=url):
                response = self.client.get(url, **self.headers)
                self.assertEqual(response.status_code, 200, response.content[:300])
                self.assertNotIn(foreign_id, self._result_ids(response))

    def test_foreign_tenant_header_is_forbidden(self):
        foreign_header = {"HTTP_X_TENANT_ID": str(self.other_tenant.TenantID)}
        for url in (
            "/api/sales/invoices/?page=1",
            "/api/sales/payments/?page=1",
            "/api/sales/quotations/?page=1",
            "/api/logistics/supplier-payments/?page=1",
        ):
            with self.subTest(url=url):
                response = self.client.get(url, **foreign_header)
                self.assertEqual(response.status_code, 403, response.content[:300])
