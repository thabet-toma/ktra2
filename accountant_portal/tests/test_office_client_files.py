"""مكتب المحاسبة: كل شركة زبون — سحب فواتيره ومصاريفه وملخصه المالي البسيط.

القاعدة: قراءة فقط. المحاسب لا ينشئ ولا يعدّل مستنداً للزبون.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account, Currency, JournalHeader, JournalLine
from accountant_portal.models import AccountantProfile
from accountant_portal.services import accept_company_invitation, create_company_invitation
from core.models import TenantModule
from core.modules import invalidate_module_cache
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Tenant, UserCompanyMembership


class ClientFileTest(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("office-manager")
        self.accountant = User.objects.create_user("office-accountant", email="office@example.com")
        self.client_tenant = Tenant.objects.create(CompanyName="زبون المكتب")
        TenantModule.objects.create(
            tenant=self.client_tenant, module_key="accountant_portal", enabled=True,
        )
        invalidate_module_cache(self.client_tenant.pk)
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.client_tenant, role="manager",
        )
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="licensed_auditor",
            tax_registration_number="TAX-OFFICE-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        _, token = create_company_invitation(
            tenant=self.client_tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=[
                "sales.invoice.view",
                "purchase.invoice.view",
                "accounting.journal.view",
                "accounting.report.view",
            ],
        )
        accept_company_invitation(accountant=self.accountant, token=token)

        self.currency = Currency.objects.create(
            Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True,
        )
        self.customer = Partner.objects.create(
            tenant=self.client_tenant, name="زبون البيع", partner_type="customer", tax_number="11",
        )
        self.sale = self._invoice("SI-OF-1", SalesInvoice.INVOICE_KIND_SALE, Decimal("1000"), Decimal("160"))
        self.purchase = self._invoice("PI-OF-1", SalesInvoice.INVOICE_KIND_PURCHASE, Decimal("400"), Decimal("64"))
        self._invoice("SI-OLD", SalesInvoice.INVOICE_KIND_SALE, Decimal("999"), Decimal("99"), day=date(2026, 1, 5))

        self.revenue = Account.objects.create(
            tenant=self.client_tenant, code="4101", name="إيراد مبيعات", account_type="Revenue",
        )
        self.expense = Account.objects.create(
            tenant=self.client_tenant, code="5101", name="إيجار", account_type="Expense",
        )
        self.cash = Account.objects.create(
            tenant=self.client_tenant, code="1101", name="صندوق", account_type="Asset",
        )
        self._journal(self.revenue, credit=Decimal("1000"))
        self._journal(self.expense, debit=Decimal("300"))

        self.headers = {"HTTP_X_TENANT_ID": str(self.client_tenant.pk)}
        self.client.force_authenticate(self.accountant)

    def _invoice(self, number, kind, subtotal, tax, day=date(2026, 6, 10)):
        return SalesInvoice.objects.create(
            tenant=self.client_tenant,
            invoice_number=number,
            customer=self.customer,
            invoice_date=day,
            currency=self.currency,
            invoice_kind=kind,
            status=SalesInvoice.STATUS_POSTED,
            subtotal_excl_tax=subtotal,
            tax_amount=tax,
            grand_total=subtotal + tax,
        )

    def _journal(self, account, debit=Decimal("0"), credit=Decimal("0")):
        header = JournalHeader.objects.create(
            tenant=self.client_tenant,
            transaction_date=date(2026, 6, 12),
            description="قيد اختبار",
            is_posted=True,
        )
        JournalLine.objects.create(
            tenant=self.client_tenant, journal=header, account=account,
            debit=debit, credit=credit,
        )
        JournalLine.objects.create(
            tenant=self.client_tenant, journal=header, account=self.cash,
            debit=credit, credit=debit,
        )
        return header

    def _get(self, path):
        return self.client.get(path, **self.headers)

    def test_sales_documents_are_pulled_for_the_window_only(self):
        response = self._get("/api/accountant/client/documents/?kind=sales&from=2026-06-01&to=2026-06-30")

        self.assertEqual(response.status_code, 200, response.content)
        numbers = [row["invoice_number"] for row in response.data["results"]]
        self.assertEqual(numbers, ["SI-OF-1"])
        self.assertEqual(response.data["totals"]["grand_total"], "1160.00")

    def test_purchase_documents_are_separated_from_sales(self):
        response = self._get("/api/accountant/client/documents/?kind=purchases&from=2026-06-01&to=2026-06-30")

        numbers = [row["invoice_number"] for row in response.data["results"]]
        self.assertEqual(numbers, ["PI-OF-1"])

    def test_expenses_are_pulled_from_the_ledger_grouped_by_account(self):
        response = self._get("/api/accountant/client/documents/?kind=expenses&from=2026-06-01&to=2026-06-30")

        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["name"]: row for row in response.data["results"]}
        self.assertIn("إيجار", rows)
        self.assertEqual(rows["إيجار"]["amount"], "300.00")

    def test_summary_is_plain_arithmetic_revenue_minus_expenses_and_vat(self):
        response = self._get("/api/accountant/client/summary/?from=2026-06-01&to=2026-06-30")

        self.assertEqual(response.status_code, 200, response.content)
        data = response.data["summary"]
        self.assertEqual(data["revenue"], "1000.00")
        self.assertEqual(data["expenses"], "300.00")
        self.assertEqual(data["profit"], "700.00")
        self.assertEqual(data["output_vat"], "160.00")
        self.assertEqual(data["input_vat"], "64.00")
        self.assertEqual(data["vat_due"], "96.00")

    def test_summary_carries_a_simple_balance_sheet_cumulative_to_the_end_date(self):
        equity = Account.objects.create(
            tenant=self.client_tenant, code="3101", name="رأس المال", account_type="Equity",
        )
        header = JournalHeader.objects.create(
            tenant=self.client_tenant,
            transaction_date=date(2026, 5, 1),  # قبل الفترة — يظهر في الميزانية لا في الربح
            description="رأس مال",
            is_posted=True,
        )
        JournalLine.objects.create(
            tenant=self.client_tenant, journal=header, account=self.cash,
            debit=Decimal("5000"), credit=Decimal("0"),
        )
        JournalLine.objects.create(
            tenant=self.client_tenant, journal=header, account=equity,
            debit=Decimal("0"), credit=Decimal("5000"),
        )

        response = self._get("/api/accountant/client/summary/?from=2026-06-01&to=2026-06-30")

        data = response.data["summary"]
        self.assertEqual(data["equity"], "5000.00")
        # النقد: 5000 رأس مال + 1000 إيراد − 300 مصروف
        self.assertEqual(data["assets"], "5700.00")
        self.assertEqual(data["liabilities"], "0.00")
        self.assertEqual(data["revenue"], "1000.00")

    def test_returns_reduce_both_vat_sides(self):
        self._invoice("SR-OF-1", SalesInvoice.INVOICE_KIND_SALE_RETURN, Decimal("100"), Decimal("16"))

        response = self._get("/api/accountant/client/summary/?from=2026-06-01&to=2026-06-30")

        self.assertEqual(response.data["summary"]["output_vat"], "144.00")
        self.assertEqual(response.data["summary"]["vat_due"], "80.00")

    def test_accountant_can_never_create_or_edit_a_client_document(self):
        created = self.client.post(
            "/api/sales/invoices/",
            {"invoice_number": "SI-NEW"},
            format="json",
            **self.headers,
        )
        edited = self.client.patch(
            f"/api/sales/invoices/{self.sale.pk}/",
            {"grand_total": "1.00"},
            format="json",
            **self.headers,
        )

        self.assertEqual(created.status_code, 403, created.content)
        self.assertEqual(edited.status_code, 403, edited.content)

    def test_another_office_cannot_read_this_client(self):
        stranger = User.objects.create_user("office-stranger", email="stranger@example.com")
        AccountantProfile.objects.create(
            user=stranger,
            professional_type="accountant",
            tax_registration_number="TAX-OFFICE-2",
            business_address="نابلس",
            email_verified_at=timezone.now(),
        )
        self.client.force_authenticate(stranger)

        response = self._get("/api/accountant/client/summary/?from=2026-06-01&to=2026-06-30")

        self.assertIn(response.status_code, (403, 404))


class PracticeAndStatementsTest(ClientFileTest):
    """لوحة المكتب والبيانات المالية — ما يفتحه المحاسب أول الشهر."""

    def test_statements_split_income_from_the_cumulative_balance_sheet(self):
        response = self._get("/api/accountant/client/statements/?from=2026-06-01&to=2026-06-30")

        self.assertEqual(response.status_code, 200, response.content)
        income = response.data["income"]
        balance = response.data["balance"]
        self.assertEqual(income["revenue_total"], "1000.00")
        self.assertEqual(income["expense_total"], "300.00")
        self.assertEqual(income["profit"], "700.00")
        self.assertEqual([row["name"] for row in income["expenses"]], ["إيجار"])
        self.assertEqual(balance["asset_total"], "700.00")

    def test_trend_returns_a_row_for_every_month_even_the_empty_ones(self):
        response = self._get("/api/accountant/client/trend/?months=6")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data["series"]), 6)
        self.assertTrue(all("month" in row and "profit" in row for row in response.data["series"]))

    def test_practice_overview_lists_every_client_with_its_month_numbers(self):
        response = self.client.get("/api/accountant/practice/overview/")

        self.assertEqual(response.status_code, 200, response.content)
        names = [row["company_name"] for row in response.data["clients"]]
        self.assertIn("زبون المكتب", names)
        self.assertEqual(response.data["totals"]["clients"], 1)
        row = response.data["clients"][0]
        for key in ("vat_due", "profit", "filing_due_date", "days_to_filing", "draft_documents"):
            self.assertIn(key, row)

    def test_practice_overview_never_leaks_another_offices_clients(self):
        stranger = User.objects.create_user("practice-stranger", email="practice@example.com")
        AccountantProfile.objects.create(
            user=stranger,
            professional_type="accountant",
            tax_registration_number="TAX-PRACTICE-1",
            business_address="جنين",
            email_verified_at=timezone.now(),
        )
        self.client.force_authenticate(stranger)

        response = self.client.get("/api/accountant/practice/overview/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["clients"], [])
