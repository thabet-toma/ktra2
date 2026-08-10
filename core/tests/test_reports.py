"""T-REPORTS: محرّك التقارير — الفهرس، التنفيذ، حدود الشركة، والصلاحية.

التقارير كلها تمرّ من نقطتين فقط (`/api/reports/` و`/api/reports/<key>/`)، فما
يُختبَر هنا هو العقد نفسه: كل تقرير معلن بأعمدته وفلاتره، ويُنفَّذ داخل حدود
الشركة، ويجمع سطر الإجمالي من الأعمدة الموسومة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance
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
        # حساب الذمم المدينة — مادّة اختبارات كشف الحساب ودفتر الأستاذ.
        cls.ar_account = Account.objects.filter(
            tenant=cls.tenant, code__startswith="1102").first() or cash
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

    # ── الدفاتر (T-REPORTS2) ─────────────────────────────────────────
    def _post_line(self, date, debit, credit, *, partner=None, description=""):
        """قيد مرحَّل بسطر واحد على حساب الذمم — مادّة كشف الحساب والأستاذ."""
        journal = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date=date, description=description,
            is_posted=True, currency=self.currency, exchange_rate=Decimal("1"),
        )
        return JournalLine.objects.create(
            tenant=self.tenant, journal=journal, account=self.ar_account,
            debit=debit, credit=credit, base_debit=debit, base_credit=credit,
            partner=partner, description=description,
        )

    def test_partner_statement_carries_opening_balance_into_the_period(self):
        """الحركة السابقة للفترة لا تُهمَل ولا تُعرَض — تُطوى في رصيد افتتاحي.

        بلا هذا يقرأ صاحب الحساب رصيداً يبدأ من الصفر في كل فترة يفتحها.
        """
        self._post_line("2025-11-01", Decimal("300"), Decimal("0"),
                        partner=self.customer, description="قبل الفترة")
        self._post_line("2026-03-05", Decimal("200"), Decimal("0"),
                        partner=self.customer, description="داخل الفترة")
        self._post_line("2026-04-05", Decimal("0"), Decimal("50"),
                        partner=self.customer, description="تحصيل")

        res = self._run("partner-statement", partner=self.customer.id)
        self.assertEqual(res.status_code, 200, res.data)
        rows = res.data["rows"]
        self.assertEqual(rows[0]["description"], "رصيد افتتاحي")
        self.assertEqual(Decimal(rows[0]["balance"]), Decimal("300"))
        # الافتتاحي لا يُعرَض كحركة: 3 أسطر = افتتاحي + حركتا الفترة.
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["description"] for r in rows[1:]], ["داخل الفترة", "تحصيل"])
        self.assertEqual(Decimal(rows[-1]["balance"]), Decimal("450"))
        # الإجمالي على حركات الفترة وحدها — الافتتاحي ليس مديناً ولا دائناً.
        self.assertEqual(Decimal(res.data["totals"]["debit"]), Decimal("200"))
        self.assertEqual(Decimal(res.data["totals"]["credit"]), Decimal("50"))

    def test_partner_statement_matches_posted_balance_source_of_truth(self):
        """الختامي يساوي `partner_posted_balance` — لا مصدر حقيقة موازٍ."""
        self._post_line("2026-02-01", Decimal("700"), Decimal("0"), partner=self.customer)
        self._post_line("2026-02-09", Decimal("0"), Decimal("120"), partner=self.customer)
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.customer.id)

        res = self._run("partner-statement", partner=self.customer.id,
                        **{"from": "1990-01-01", "to": "2099-12-31"})
        self.assertEqual(Decimal(res.data["rows"][-1]["balance"]), debit - credit)

    def test_supplier_statement_flips_the_sign(self):
        """المورد دائن بطبعه: دائن−مدين، وإلا قرأ الطرفان الرقم نفسه بإشارتين."""
        self._post_line("2026-02-01", Decimal("0"), Decimal("400"), partner=self.supplier)
        res = self._run("partner-statement", partner=self.supplier.id)
        self.assertEqual(Decimal(res.data["rows"][-1]["balance"]), Decimal("400"))

    def test_partner_statement_without_a_partner_returns_nothing(self):
        """كشفٌ بلا طرف لا معنى له — لا يجرّ دفتر الشركة كله."""
        res = self._run("partner-statement")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["rows"], [])

    def test_account_ledger_runs_a_debit_minus_credit_balance(self):
        self._post_line("2026-05-01", Decimal("90"), Decimal("0"))
        self._post_line("2026-05-02", Decimal("0"), Decimal("40"))
        res = self._run("account-ledger", account=self.ar_account.id)
        rows = res.data["rows"]
        self.assertEqual(rows[0]["description"], "رصيد افتتاحي")
        self.assertEqual(Decimal(rows[-1]["balance"]), Decimal("50"))

    def test_general_journal_shows_posted_entries_with_their_totals(self):
        self._post_line("2026-06-20", Decimal("75"), Decimal("0"), description="قيد اليومية")
        res = self._run("general-journal")
        row = next(r for r in res.data["rows"] if r["description"] == "قيد اليومية")
        self.assertEqual(row["state"], "مرحّل")
        self.assertEqual(Decimal(row["debit"]), Decimal("75"))

    # ── القصّ لا يكذب ────────────────────────────────────────────────
    def test_truncation_trims_rows_but_never_the_totals(self):
        """التقرير الضخم يُقصّ للعرض؛ الإجمالي يبقى على الصفوف كلها."""
        from core import reports as reports_module

        original = reports_module.MAX_ROWS
        reports_module.MAX_ROWS = 2
        try:
            for day in range(1, 5):
                self._post_line(f"2026-07-0{day}", Decimal("10"), Decimal("0"))
            res = self._run("general-journal")
        finally:
            reports_module.MAX_ROWS = original

        self.assertTrue(res.data["truncated"])
        self.assertEqual(len(res.data["rows"]), 2)
        self.assertGreaterEqual(res.data["total_rows"], 4)
        self.assertGreaterEqual(Decimal(res.data["totals"]["debit"]), Decimal("40"))

    # ── مسار المستند خلف السطر ───────────────────────────────────────
    def test_document_reports_expose_the_path_behind_the_row(self):
        """السطر بابٌ إلى مستنده: الخادم يُعلن المسار فتفتحه الشاشة العامّة."""
        res = self._run("sales-invoices")
        self.assertEqual(res.data["row_link"], "/sales/invoices/{id}")
        self.assertTrue(all("id" in row for row in res.data["rows"]))
        catalog = {r["key"]: r for c in report_catalog() for r in c["reports"]}
        self.assertEqual(catalog["import-deals"]["row_link"], "/deals/{id}")

    # ── العزل ────────────────────────────────────────────────────────
    def test_report_is_scoped_to_active_company(self):
        self.client.force_authenticate(user=self.other_user)
        self.active_tenant = self.other_tenant
        res = self._run("sales-invoices")
        numbers = [r["invoice_number"] for r in res.data["rows"]]
        self.assertEqual(numbers, ["SI-OTHER"])
