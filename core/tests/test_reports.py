"""T-REPORTS: محرّك التقارير — الفهرس، التنفيذ، حدود الشركة، والصلاحية.

التقارير كلها تمرّ من نقطتين فقط (`/api/reports/` و`/api/reports/<key>/`)، فما
يُختبَر هنا هو العقد نفسه: كل تقرير معلن بأعمدته وفلاتره، ويُنفَّذ داخل حدود
الشركة، ويجمع سطر الإجمالي من الأعمدة الموسومة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance
from core.models import TenantModule
from core.reports import REPORTS, report_catalog
from inventory.models import Product, StockMovement
from logistics.models import PurchaseInvoice
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
        # تقارير الوحدات المرخّصة تُردّ 404 بلا ترخيصها. تُرخَّص كلها هنا كي يبقى
        # «كل تقرير في السجل يُنفَّذ» حارساً شاملاً فعلاً — استثناؤها من الحارس
        # كان سيترك تقارير بلا أي تغطية. (بوابة الترخيص نفسها تُختبر في
        # `after_sales/tests/test_reports.py`.)
        for module_key in {
            spec.module for spec in REPORTS.values() if spec.module
        }:
            TenantModule.objects.create(
                tenant=cls.tenant, module_key=module_key, enabled=True,
            )

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

    def test_sales_by_product_declares_quantity_that_has_no_movement(self):
        """THA-60: بلا حركة مخزون لا تُختلَق تكلفة — الكمية تُعلَن كما هي.

        فاتورة هذه التجهيزة مكتوبة مباشرةً بلا ترحيل، فلا حركة لها. كانت
        التكلفة تُشتقّ من `avg_cost` (5×4=20 ⇒ ربح 80)، وهو رقم يتغيّر مع كل
        شراء لاحق؛ الآن التكلفة صفر **مُعلَناً** في «كمية بلا تكلفة».
        """
        res = self._run("sales-by-product")
        row = next(r for r in res.data["rows"] if r["sku"] == "RPT-1")
        self.assertEqual(Decimal(row["quantity"]), Decimal("5"))
        self.assertEqual(Decimal(row["net_sales"]), Decimal("100"))
        self.assertEqual(Decimal(row["cost"]), Decimal("0"))
        self.assertEqual(Decimal(row["uncosted_qty"]), Decimal("5"))

    def test_sales_by_product_reads_cost_from_the_stock_movement(self):
        """وبوجود الحركة تُقرأ تكلفتها هي — لا متوسط الصنف اليوم (4)."""
        StockMovement.objects.create(
            tenant=self.tenant, product=self.product, movement_type="OUT",
            quantity=Decimal("5"), unit_cost=Decimal("6"), total_cost=Decimal("30"),
            reference_type="SALE", reference_id=self.invoice.id,
            movement_date="2026-06-10",
        )
        res = self._run("sales-by-product")
        row = next(r for r in res.data["rows"] if r["sku"] == "RPT-1")
        self.assertEqual(Decimal(row["cost"]), Decimal("30"))
        self.assertEqual(Decimal(row["profit"]), Decimal("70"))
        self.assertEqual(Decimal(row["uncosted_qty"]), Decimal("0"))

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

    #: تقارير لها حدٌّ على الفترة ترفض النطاق العريض الافتراضي هنا عن حق —
    #: يُشغَّل كلٌّ منها بنطاقه بدل تعطيل الحارس عنه.
    NARROW_PERIOD_REPORTS = {
        "timesheet-daily": {"from": "2026-08-01", "to": "2026-08-31"},
    }

    def test_every_report_runs_without_error(self):
        """حارس شامل: أي تقرير في السجل ينفَّذ على شركة حقيقية بلا استثناء."""
        for key in REPORTS:
            with self.subTest(report=key):
                res = self._run(key, **self.NARROW_PERIOD_REPORTS.get(key, {}))
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
        # بعد تفكيك core/reports إلى حزمة (المرحلة 3): run_report وMAX_ROWS في
        # core.reports._framework، وrun_report يقرأ MAX_ROWS من فضاء اسمها هناك —
        # فالـpatch على الموضع الذي تُقرأ منه القيمة فعلاً (لا على إعادة التصدير).
        from core.reports import _framework as reports_framework

        original = reports_framework.MAX_ROWS
        reports_framework.MAX_ROWS = 2
        try:
            for day in range(1, 5):
                self._post_line(f"2026-07-0{day}", Decimal("10"), Decimal("0"))
            res = self._run("general-journal")
        finally:
            reports_framework.MAX_ROWS = original

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


class PayablesAgingTest(APITestCase):
    """المرحلة 5 / P0-9: أعمار الدائنين — الصحّة أولاً ثم كلفة الاستعلامات.

    التقرير كان يقرأ المفتاح `remaining` من `purchase_invoice_payment_summary`،
    وهو مفتاح **غير موجود** في القاموس العائد (المفتاح الفعلي
    `remaining_balance` — `core/payments.py:196-205`). النتيجة: كل سطر يُقيَّم
    بمتبقٍّ صفر فيُستبعَد، فالتقرير كان يعود فارغاً دائماً — بعد أن ينفّذ ≥6
    استعلامات لكل فاتورة مرحّلة منذ نشأة الشركة.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="payables", password="x")
        cls.tenant = create_company("شركة الدائنين", cls.user)
        cls.currency, _ = Currency.objects.get_or_create(
            Code="PAY", defaults={"Name": "Payables", "Symbol": "P"})
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الأعمار", partner_type="Supplier")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _invoice(self, number, date, total):
        return PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.supplier,
            currency=self.currency, invoice_date=date,
            grand_total=Decimal(total), is_posted=True, is_return=False,
        )

    def _run(self):
        return self.client.get(
            "/api/reports/payables-aging/", {"as_of": "2026-12-31"},
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )

    def test_unpaid_posted_invoice_appears_with_its_remaining(self):
        """الحارس الأساسي: فاتورة مرحّلة غير مدفوعة تظهر بمتبقّيها لا بصفر."""
        self._invoice("PI-AGE-1", "2026-06-10", "300")
        res = self._run()
        self.assertEqual(res.status_code, 200, res.data)
        row = next(
            r for r in res.data["rows"] if r["partner_name"] == "مورد الأعمار")
        self.assertEqual(Decimal(row["total"]), Decimal("300"))
        # 2026-06-10 ← 2026-12-31 = أكثر من 90 يوماً
        self.assertEqual(Decimal(row["b3"]), Decimal("300"))
        self.assertEqual(Decimal(row["b0"]), Decimal("0"))

    def test_query_count_does_not_grow_with_invoice_count(self):
        """تثبيت كلفة P0-9: العدّ نفسه لفاتورة واحدة ولستّ فواتير.

        قبل الإصلاح كان كل صف يضيف ≥6 استعلامات، فالفارق بين الحالتين ≥30.
        بعده الملخّص كله subqueries داخل استعلام القائمة الواحد.
        """
        self._invoice("PI-N-1", "2026-06-10", "100")
        with CaptureQueriesContext(connection) as one_invoice:
            self.assertEqual(self._run().status_code, 200)

        for i in range(2, 8):
            self._invoice(f"PI-N-{i}", "2026-06-10", "100")
        with CaptureQueriesContext(connection) as seven_invoices:
            res = self._run()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            Decimal(next(r for r in res.data["rows"])["total"]), Decimal("700"))
        self.assertEqual(
            len(seven_invoices), len(one_invoice),
            f"عدد الاستعلامات نما مع عدد الفواتير: "
            f"{len(one_invoice)} → {len(seven_invoices)}",
        )


class DynamicColumnsTest(APITestCase):
    """الأعمدة المحسوبة عند التشغيل — عقد `ReportSpec.columns_for`.

    تقريرٌ عمودُه يتبع البيانات (عمود لكل يوم في الفترة) لا يستطيع إعلان أعمدته
    عند التسجيل. الحارس هنا على العقد لا على تقريرٍ بعينه: أعمدة **الناتج** هي
    المحسوبة، والإجمالي يُجمع عليها، والفهرس يبقى على المعلَن لأنه يُطلب بلا
    مستأجرٍ ولا فترة.
    """

    KEY = "test-dynamic-columns"

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dyn", password="x")
        cls.tenant = create_company("شركة الأعمدة", cls.user)

    def setUp(self):
        from rest_framework.exceptions import ValidationError

        from core.reports import _framework as fw

        self.client.force_authenticate(user=self.user)

        def columns_for(tenant_id, params):
            if params.get("boom"):
                raise ValidationError("اختر فترة لا تتجاوز 31 يوماً.")
            return (
                fw.ReportColumn("name", "الاسم"),
                *(
                    fw.ReportColumn(f"d{i}", f"يوم {i}", fw.KIND_NUMBER, total=True)
                    for i in range(1, int(params.get("days", 2)) + 1)
                ),
            )

        fw.register(fw.ReportSpec(
            key=self.KEY,
            title="تقرير الأعمدة الديناميكية",
            category="hr",
            description="اختباري.",
            columns=(fw.ReportColumn("name", "الاسم"),),
            columns_for=columns_for,
            build=lambda tenant_id, params: [
                {"name": "أ", "d1": "3", "d2": "4"},
                {"name": "ب", "d1": "1", "d2": "2"},
            ],
        ))
        self.addCleanup(fw.REPORTS.pop, self.KEY, None)

    def _run(self, **params):
        return self.client.get(
            f"/api/reports/{self.KEY}/", params,
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )

    def test_payload_carries_the_computed_columns_and_totals_them(self):
        res = self._run(days=2)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(
            [c["key"] for c in res.data["columns"]], ["name", "d1", "d2"])
        # الإجمالي على أعمدة التشغيل — لو جُمع على المعلَنة لجاء فارغاً.
        self.assertEqual(Decimal(res.data["totals"]["d1"]), Decimal("4"))
        self.assertEqual(Decimal(res.data["totals"]["d2"]), Decimal("6"))

    def test_catalog_keeps_the_declared_columns(self):
        """الفهرس يُطلب بلا فترة — فيَعِد بما يعرفه فقط، ولا يخمّن."""
        catalog = {r["key"]: r for c in report_catalog() for r in c["reports"]}
        self.assertEqual([c["key"] for c in catalog[self.KEY]["columns"]], ["name"])

    def test_a_rejected_input_is_400_with_its_own_message_not_500(self):
        """حارس التقرير خطأ مستخدم يُصلحه بنفسه، لا عطل خادم بلا معنى."""
        res = self._run(boom="1")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(res.data["error"], "اختر فترة لا تتجاوز 31 يوماً.")

    def test_payload_names_who_generated_it(self):
        res = self._run(days=1)
        self.assertEqual(res.data["generated_by"], "dyn")
