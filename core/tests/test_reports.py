"""T-REPORTS: محرّك التقارير — الفهرس، التنفيذ، حدود الشركة، والصلاحية.

التقارير كلها تمرّ من نقطتين فقط (`/api/reports/` و`/api/reports/<key>/`)، فما
يُختبَر هنا هو العقد نفسه: كل تقرير معلن بأعمدته وفلاتره، ويُنفَّذ داخل حدود
الشركة، ويجمع سطر الإجمالي من الأعمدة الموسومة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from core.reports import REPORTS, report_catalog
from inventory.models import Product
from partners.models import Partner
from sales.models import CustomerPayment, SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company


class ReportEngineTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="reporter", password="x")
        cls.other_user = User.objects.create_user(username="outsider", password="x")
        cls.currency, _ = Currency.objects.get_or_create(
            Code="RPT", defaults={"Name": "Report", "Symbol": "R"})
        cls.tenant = create_company("شركة التقارير", cls.user)
        cls.other_tenant = create_company("شركة أخرى", cls.other_user)
        create_fiscal_year(cls.tenant, 2026)

        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون التقارير", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد التقارير", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="RPT-1", name_ar="صنف التقارير",
            brand="ماركة", quantity_on_hand=Decimal("10"), avg_cost=Decimal("4"),
            min_stock_level=20,
        )

        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="SI-RPT-1", customer=cls.customer,
            currency=cls.currency, invoice_date="2026-06-10",
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            status=SalesInvoice.STATUS_POSTED,
            subtotal_excl_tax=Decimal("100"), tax_amount=Decimal("16"),
            grand_total=Decimal("116"), amount_paid=Decimal("16"),
        )
        SalesInvoiceLine.objects.create(
            tenant=cls.tenant, invoice=cls.invoice, product=cls.product,
            quantity=Decimal("5"), unit_price=Decimal("20"),
            line_total_excl_tax=Decimal("100"), line_tax_amount=Decimal("16"),
        )
        # فاتورة خارج نطاق التاريخ — تُثبت أن الفلترة تعمل
        SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="SI-RPT-OLD", customer=cls.customer,
            currency=cls.currency, invoice_date="2025-01-05",
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            status=SalesInvoice.STATUS_POSTED,
            subtotal_excl_tax=Decimal("50"), grand_total=Decimal("50"),
        )
        # فاتورة شركة أخرى — تُثبت عزل الشركات
        other_customer = Partner.objects.create(
            tenant=cls.other_tenant, name="زبون الغير", partner_type="Customer")
        SalesInvoice.objects.create(
            tenant=cls.other_tenant, invoice_number="SI-OTHER", customer=other_customer,
            currency=cls.currency, invoice_date="2026-06-10",
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            status=SalesInvoice.STATUS_POSTED,
            grand_total=Decimal("999"),
        )

        cash = Account.objects.get(tenant=cls.tenant, code="1101")
        CustomerPayment.objects.create(
            tenant=cls.tenant, partner=cls.customer, currency=cls.currency,
            exchange_rate=Decimal("1"), amount=Decimal("16"),
            cash_or_bank_account=cash, payment_date="2026-06-15", is_posted=True,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.active_tenant = self.tenant

    def _headers(self):
        # شركتان في قاعدة الاختبار ⇒ لا حلّ تلقائي؛ الترويسة هي عقد الـAPI.
        return {"HTTP_X_TENANT_ID": str(self.active_tenant.TenantID)}

    def _run(self, key, **params):
        params.setdefault("from", "2026-01-01")
        params.setdefault("to", "2026-12-31")
        return self.client.get(f"/api/reports/{key}/", params, **self._headers())

    # ── الفهرس ───────────────────────────────────────────────────────
    def test_catalog_lists_every_report_grouped_by_category(self):
        res = self.client.get("/api/reports/", **self._headers())
        self.assertEqual(res.status_code, 200, res.data)
        categories = res.data["categories"]
        self.assertTrue(categories, "الفهرس فارغ")
        keys = {r["key"] for c in categories for r in c["reports"]}
        self.assertEqual(keys, set(REPORTS))
        for category in categories:
            self.assertTrue(category["label"])
            for report in category["reports"]:
                self.assertTrue(report["title"])
                self.assertTrue(report["columns"], report["key"])

    def test_catalog_covers_every_document_family(self):
        """«تقارير كافية لكل مستندات المنصة» — لا عائلة مستندات بلا تقرير."""
        catalog = report_catalog()
        categories = {c["key"] for c in catalog}
        self.assertLessEqual(
            {"sales", "purchases", "partners", "inventory", "finance", "import"},
            categories,
        )

    # ── التنفيذ ──────────────────────────────────────────────────────
    def test_unknown_report_returns_404(self):
        self.assertEqual(self.client.get("/api/reports/nope/").status_code, 404)

    def test_sales_summary_totals_only_in_range(self):
        res = self._run("sales-invoices")
        self.assertEqual(res.status_code, 200, res.data)
        numbers = [r["invoice_number"] for r in res.data["rows"]]
        self.assertIn("SI-RPT-1", numbers)
        self.assertNotIn("SI-RPT-OLD", numbers)
        self.assertNotIn("SI-OTHER", numbers)
        self.assertEqual(Decimal(res.data["totals"]["grand_total"]), Decimal("116"))

    def test_sales_by_customer_aggregates_and_names_partner(self):
        res = self._run("sales-by-customer")
        self.assertEqual(res.status_code, 200, res.data)
        row = next(r for r in res.data["rows"] if r["partner_name"] == "زبون التقارير")
        self.assertEqual(Decimal(row["grand_total"]), Decimal("116"))
        self.assertEqual(Decimal(row["remaining"]), Decimal("100"))

    def test_sales_by_product_reports_quantity_and_profit(self):
        res = self._run("sales-by-product")
        row = next(r for r in res.data["rows"] if r["sku"] == "RPT-1")
        self.assertEqual(Decimal(row["quantity"]), Decimal("5"))
        self.assertEqual(Decimal(row["net_sales"]), Decimal("100"))
        # التكلفة = 5 × 4 = 20 ⇒ الربح 80
        self.assertEqual(Decimal(row["profit"]), Decimal("80"))

    def test_low_stock_report_flags_item_under_minimum(self):
        res = self._run("low-stock")
        skus = [r["sku"] for r in res.data["rows"]]
        self.assertIn("RPT-1", skus)

    def test_customer_payments_report_lists_posted_voucher(self):
        res = self._run("customer-payments")
        self.assertEqual(len(res.data["rows"]), 1)
        self.assertEqual(Decimal(res.data["totals"]["amount"]), Decimal("16"))

    def test_receivables_aging_buckets_remaining(self):
        """الأعمار لقطة لكل المتبقّي — لا تُقصّها فترة، والقديم يقع في «أكثر من 90»."""
        res = self._run("receivables-aging", **{"as_of": "2026-12-31"})
        row = next(r for r in res.data["rows"] if r["partner_name"] == "زبون التقارير")
        # 100 متبقٍّ من SI-RPT-1 + 50 من SI-RPT-OLD (خارج الفترة لكنه ما يزال مستحقاً)
        self.assertEqual(Decimal(row["total"]), Decimal("150"))
        self.assertEqual(Decimal(row["b3"]), Decimal("150"))
        self.assertEqual(Decimal(row["b0"]), Decimal("0"))

    def test_every_report_runs_without_error(self):
        """حارس شامل: أي تقرير في السجل ينفَّذ على شركة حقيقية بلا استثناء."""
        for key in REPORTS:
            with self.subTest(report=key):
                res = self._run(key)
                self.assertEqual(res.status_code, 200, f"{key}: {res.data}")
                self.assertIn("rows", res.data)
                self.assertIn("columns", res.data)

    # ── العزل ────────────────────────────────────────────────────────
    def test_report_is_scoped_to_active_company(self):
        self.client.force_authenticate(user=self.other_user)
        self.active_tenant = self.other_tenant
        res = self._run("sales-invoices")
        numbers = [r["invoice_number"] for r in res.data["rows"]]
        self.assertEqual(numbers, ["SI-OTHER"])
