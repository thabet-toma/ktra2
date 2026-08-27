"""تقرير «حركة المخزون حسب بُعد» — المحور يتبدّل، والرقم يُفتح على مفرداته.

المعيار الذي تدور حوله كل الاختبارات هنا: **مجموع التنقيب = رقم الصفّ بالضبط**.
وهو يُختبَر لا على صفٍّ واحد بل على كل صفّ في كل محور — لأن الخطر ليس أن يخطئ
صفٌّ بعينه، بل أن يُبنى الرقم المجمَّع من مجموعةٍ وتُبنى مفرداته من مجموعةٍ أخرى
فينحرفا عند أول فلتر يُنسى في إحداهما.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement, Warehouse
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company


class StockByDimensionReportTest(APITestCase):
    """موردان × ثلاثة منتجات، وارد وصادر ومرتجع — ومستودعان."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dim-reporter", password="x")
        cls.other_user = User.objects.create_user(username="dim-outsider", password="x")
        cls.tenant = create_company("شركة الأبعاد", cls.user)
        cls.other_tenant = create_company("شركة الجوار", cls.other_user)
        cls.main = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.branch_wh = Warehouse.objects.create(
            tenant=cls.tenant, name="مستودع الفرع", code="W2")

        cls.sup_a = Partner.objects.create(
            tenant=cls.tenant, name="مورد ألف", partner_type="Supplier")
        cls.sup_b = Partner.objects.create(
            tenant=cls.tenant, name="مورد باء", partner_type="Supplier")
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون التقرير", partner_type="Customer")

        cls.laptop = Product.objects.create(
            tenant=cls.tenant, sku="LAP", name_ar="لابتوب", brand="ديل",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        cls.mouse = Product.objects.create(
            tenant=cls.tenant, sku="MOU", name_ar="فأرة", brand="ديل",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        cls.paper = Product.objects.create(
            tenant=cls.tenant, sku="PAP", name_ar="ورق", brand="",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

        def move(product, mtype, qty, cost, *, partner=None, warehouse=None,
                 date="2026-06-10", ref_type="PURCHASE_INVOICE", ref_id=1,
                 tenant=None):
            return StockMovement.objects.create(
                tenant=tenant or cls.tenant, product=product, movement_type=mtype,
                quantity=Decimal(qty), unit_cost=Decimal(cost),
                total_cost=Decimal(qty) * Decimal(cost),
                reference_type=ref_type, reference_id=ref_id,
                partner=partner, warehouse=warehouse or cls.main,
                movement_date=date,
            )

        # مورد ألف: لابتوبان في دفعتين + فأرات، ومرتجعُ لابتوبٍ واحد إليه.
        move(cls.laptop, "IN", "3", "1000", partner=cls.sup_a, ref_id=11)
        move(cls.laptop, "IN", "2", "1100", partner=cls.sup_a, ref_id=12,
             date="2026-06-12")
        move(cls.mouse, "IN", "10", "20", partner=cls.sup_a, ref_id=11)
        move(cls.laptop, "RETURN_OUT", "1", "1000", partner=cls.sup_a, ref_id=13,
             date="2026-06-15")
        # مورد باء: ورق في مستودع الفرع.
        move(cls.paper, "IN", "50", "2", partner=cls.sup_b, ref_id=21,
             warehouse=cls.branch_wh)
        # الزبون: فاتورة بيع حقيقية — الإيراد يُسنَد إلى حركتها لا يُختلَق.
        # خصم فاتورة 100 على أسطر مجموعها 2600 ⇒ صافي سطر اللابتوب 2500.
        cls.currency, _ = Currency.objects.get_or_create(
            Code="DIM", defaults={"Name": "بُعد", "Symbol": "D"})
        cls.sale = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="SI-DIM-1", customer=cls.customer,
            currency=cls.currency, invoice_date="2026-06-20",
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            status=SalesInvoice.STATUS_POSTED,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
            subtotal_excl_tax=Decimal("2600"), invoice_discount=Decimal("100"),
            grand_total=Decimal("2500"),
        )
        SalesInvoiceLine.objects.create(
            tenant=cls.tenant, invoice=cls.sale, product=cls.laptop,
            quantity=Decimal("2"), unit_price=Decimal("1300"),
            line_total_excl_tax=Decimal("2600"),
        )
        move(cls.laptop, "OUT", "2", "1040", partner=cls.customer,
             ref_type="SALE", ref_id=cls.sale.id, date="2026-06-20")
        move(cls.mouse, "RETURN_IN", "1", "20", partner=cls.customer,
             ref_type="SALE", ref_id=cls.sale.id, date="2026-06-22")
        # بلا طرف: تحويل مستودعي — يغيب عن محورَي المورد والزبون عمداً.
        move(cls.laptop, "OUT", "1", "1040", partner=None,
             ref_type="WAREHOUSE_TRANSFER", ref_id=41, date="2026-06-25")
        # خارج الفترة — يُثبت أن التاريخ يفلتر فعلاً.
        move(cls.laptop, "IN", "99", "1000", partner=cls.sup_a, ref_id=99,
             date="2025-01-01")
        # شركة الجوار — يُثبت عزل الشركات.
        other_supplier = Partner.objects.create(
            tenant=cls.other_tenant, name="مورد الجوار", partner_type="Supplier")
        other_product = Product.objects.create(
            tenant=cls.other_tenant, sku="OTH", name_ar="منتج الجوار",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        move(other_product, "IN", "7", "5", partner=other_supplier,
             warehouse=Warehouse.objects.get(tenant=cls.other_tenant, is_default=True),
             tenant=cls.other_tenant)

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    # ── أدوات ─────────────────────────────────────────────────────────
    def _headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _params(self, **over):
        params = {"from": "2026-01-01", "to": "2026-12-31"}
        params.update(over)
        return params

    def _run(self, **over):
        res = self.client.get(
            "/api/reports/stock-by-dimension/", self._params(**over), **self._headers())
        assert res.status_code == 200, res.content
        return res.data

    def _drill(self, row, **over):
        params = self._params(**over)
        params["dim_key"] = row["dim_key"]
        params["row_product"] = row["row_product"]
        res = self.client.get(
            "/api/reports/stock-by-dimension/drill/", params, **self._headers())
        assert res.status_code == 200, res.content
        return res.data

    # ── المحاور ───────────────────────────────────────────────────────
    def test_supplier_dimension_lists_each_suppliers_products_and_quantities(self):
        """«حسب المورد» ⇒ لكل مورد منتجاته وكمياتها — لا منتجَ مورّدٍ آخر معه."""
        data = self._run(group_by="supplier")
        self.assertEqual(data["columns"][0]["header"], "المورد")

        by_supplier: dict[str, dict[str, dict]] = {}
        for row in data["rows"]:
            by_supplier.setdefault(row["dim_label"], {})[row["sku"]] = row

        self.assertEqual(set(by_supplier), {"مورد ألف", "مورد باء"})
        alef = by_supplier["مورد ألف"]
        self.assertEqual(set(alef), {"LAP", "MOU"})
        # 3 + 2 وارد، ومرتجعٌ واحد إليه ⇒ صافي 4. والدفعة القديمة (99) خارج الفترة.
        self.assertEqual(Decimal(alef["LAP"]["qty_in"]), Decimal("5"))
        self.assertEqual(Decimal(alef["LAP"]["qty_out"]), Decimal("1"))
        self.assertEqual(Decimal(alef["LAP"]["qty_net"]), Decimal("4"))
        self.assertEqual(Decimal(alef["LAP"]["cost_in"]), Decimal("5200"))
        self.assertEqual(alef["LAP"]["moves"], 3)
        self.assertEqual(Decimal(alef["MOU"]["qty_in"]), Decimal("10"))

        self.assertEqual(set(by_supplier["مورد باء"]), {"PAP"})
        self.assertEqual(Decimal(by_supplier["مورد باء"]["PAP"]["qty_in"]), Decimal("50"))

        # عزل الشركة: لا مورّد جارٍ ولا منتجُه.
        self.assertNotIn("مورد الجوار", by_supplier)
        self.assertNotIn("OTH", {r["sku"] for r in data["rows"]})

    def test_customer_dimension_reads_the_other_side_of_the_same_movements(self):
        """المحور يقلب السؤال بلا أن يقلب البيانات: الصادر والمرتجع تحت الزبون."""
        data = self._run(group_by="customer")
        self.assertEqual(data["columns"][0]["header"], "الزبون")
        rows = {r["sku"]: r for r in data["rows"]}
        self.assertEqual(set(rows), {"LAP", "MOU"})
        self.assertEqual(Decimal(rows["LAP"]["qty_out"]), Decimal("2"))
        self.assertEqual(Decimal(rows["MOU"]["qty_in"]), Decimal("1"))
        # التحويل المستودعي بلا طرف ⇒ لا يظهر في محورَي الطرف.
        self.assertEqual(Decimal(rows["LAP"]["qty_out"]), Decimal("2"))

    def test_partnerless_movements_appear_on_the_warehouse_axis(self):
        """ما يغيب عن محور الطرف لا يضيع — محور المستودع يراه."""
        data = self._run(group_by="warehouse", detail="summary")
        by_wh = {r["dim_label"]: r for r in data["rows"]}
        self.assertIn(self.main.name, by_wh)
        self.assertIn("مستودع الفرع", by_wh)
        # المستودع الرئيسي: 3+2+10+1 وارد = 16، وصادر 1+2+1 = 4.
        self.assertEqual(Decimal(by_wh[self.main.name]["qty_in"]), Decimal("16"))
        self.assertEqual(Decimal(by_wh[self.main.name]["qty_out"]), Decimal("4"))

    def test_brand_axis_groups_by_product_brand_and_names_the_blank(self):
        data = self._run(group_by="brand", detail="summary")
        by_brand = {r["dim_label"]: r for r in data["rows"]}
        self.assertIn("ديل", by_brand)
        self.assertIn("— بلا ماركة —", by_brand)
        self.assertEqual(Decimal(by_brand["— بلا ماركة —"]["qty_in"]), Decimal("50"))

    def test_summary_drops_the_product_columns_and_folds_its_rows(self):
        detailed = self._run(group_by="supplier")
        summary = self._run(group_by="supplier", detail="summary")
        self.assertIn("sku", {c["key"] for c in detailed["columns"]})
        self.assertNotIn("sku", {c["key"] for c in summary["columns"]})
        # مورد ألف منتجان مفصَّلاً وصفٌّ واحد ملخَّصاً، والوارد نفسه (5 + 10).
        alef = next(r for r in summary["rows"] if r["dim_label"] == "مورد ألف")
        self.assertEqual(Decimal(alef["qty_in"]), Decimal("15"))
        self.assertEqual(len([r for r in detailed["rows"] if r["dim_label"] == "مورد ألف"]), 2)

    # ── المعيار: مجموع التنقيب = رقم الصفّ ─────────────────────────────
    def test_every_row_in_every_axis_equals_the_sum_of_its_drilled_movements(self):
        """المعيار الحاسم — على كل صفّ في كل محور وفي الوضعين، لا على عيّنة.

        المقارنة على **كل** عمود مجموعٍ لا على الكمية وحدها: انحرافُ التكلفة أو
        عدد الحركات دليلُ الخلل نفسه — رقمٌ لا تسنده مفرداته.
        """
        total_columns = (
            "qty_in", "qty_out", "qty_net", "cost_in", "cost_out",
            "revenue", "profit", "moves",
        )
        checked = 0
        for axis in ("supplier", "customer", "warehouse", "brand", "product"):
            for detail in ("lines", "summary"):
                data = self._run(group_by=axis, detail=detail)
                self.assertTrue(data["rows"], f"محور {axis}/{detail} بلا صفوف")
                self.assertIsNotNone(data["drill"], "التقرير يجب أن يُعلن أنه يُنقَّب")
                for row in data["rows"]:
                    drill = self._drill(row, group_by=axis, detail=detail)
                    self.assertTrue(
                        drill["rows"],
                        f"صفّ بلا حركات: {axis}/{detail}/{row['dim_label']}",
                    )
                    for column in total_columns:
                        self.assertEqual(
                            Decimal(str(drill["totals"][column])),
                            Decimal(str(row[column])),
                            f"{axis}/{detail}/{row['dim_label']}/{row['sku']} ← {column}",
                        )
                    checked += 1
        self.assertGreater(checked, 10, "التغطية أقلّ من أن تُطمئن")

    def test_drill_obeys_the_reports_own_filters(self):
        """التنقيب نافذةٌ على نفس المجموعة — لا بابٌ خلفيّ يتخطّى الفترة.

        الدفعة القديمة (99 وحدة في 2025) خارج الفترة: لو بنى التنقيب مجموعته
        بنفسه لظهرت فيه، ولانفصل مجموعُه عن رقم الصفّ بلا أن يُنبّه أحد.
        """
        data = self._run(group_by="supplier")
        row = next(r for r in data["rows"] if r["dim_label"] == "مورد ألف" and r["sku"] == "LAP")
        drill = self._drill(row, group_by="supplier")
        self.assertEqual(Decimal(drill["totals"]["qty_in"]), Decimal("5"))
        self.assertNotIn(Decimal("99"), [Decimal(r["qty_in"]) for r in drill["rows"]])

    def test_drill_of_a_foreign_tenant_row_returns_nothing(self):
        """مفتاح صفٍّ من شركة أخرى لا يفتح حركاتها — العزل قبل المفتاح."""
        foreign = Partner.objects.get(tenant=self.other_tenant, name="مورد الجوار")
        res = self.client.get(
            "/api/reports/stock-by-dimension/drill/",
            self._params(group_by="supplier", dim_key=str(foreign.pk), row_product=""),
            **self._headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["rows"], [])

    # ── تطابق الإيراد مع مصدره الوحيد ─────────────────────────────────
    def test_revenue_matches_the_platforms_single_revenue_source(self):
        """إيراد المحور = صافي «المبيعات حسب المنتج» — لا رقمُ إيرادٍ ثانٍ.

        الفاتورة: سطرٌ بـ2600 وخصمُ فاتورة 100 ⇒ الصافي 2500 (نصيبه من الخصم
        كامله، إذ هو السطر الوحيد). الرقم نفسه يجب أن يخرج من تقرير المبيعات
        ومن هذا التقرير — لأن كليهما يقرأ `sales_revenue_map`.
        """
        by_product = self.client.get(
            "/api/reports/sales-by-product/", self._params(), **self._headers())
        self.assertEqual(by_product.status_code, 200, by_product.content)
        sales_row = next(r for r in by_product.data["rows"] if r["sku"] == "LAP")
        self.assertEqual(Decimal(sales_row["net_sales"]), Decimal("2500"))

        data = self._run(group_by="product")
        dim_row = next(r for r in data["rows"] if r["sku"] == "LAP")
        self.assertEqual(Decimal(dim_row["revenue"]), Decimal("2500"))
        # الربح = الإيراد − تكلفة حركة البيع (2 × 1040)، لا − «تكلفة الصادر»
        # التي تشمل التحويل المستودعي والمرتجع للمورّد.
        self.assertEqual(Decimal(dim_row["profit"]), Decimal("420"))

    def test_a_movement_outside_the_period_does_not_inflate_the_share(self):
        """المقام كلُّ كميات السطر لا ما في النطاق — وإلّا أعطى شهرٌ إيرادَ سنة."""
        narrow = self._run(group_by="product", **{"from": "2026-06-20", "to": "2026-06-20"})
        row = next(r for r in narrow["rows"] if r["sku"] == "LAP")
        # حركةُ البيع كلّها داخل اليوم ⇒ الإيراد كامل، ولا يتضخّم بضيق النطاق.
        self.assertEqual(Decimal(row["revenue"]), Decimal("2500"))

    def test_revenue_and_profit_are_absent_from_the_supplier_axis(self):
        """عمودٌ صفرٌ أبداً يُقرأ خطأً — فلا يُعرض حيث لا يمكن أن يكون صادقاً."""
        supplier_columns = {c["key"] for c in self._run(group_by="supplier")["columns"]}
        customer_columns = {c["key"] for c in self._run(group_by="customer")["columns"]}
        self.assertNotIn("revenue", supplier_columns)
        self.assertNotIn("profit", supplier_columns)
        self.assertIn("revenue", customer_columns)
        self.assertIn("profit", customer_columns)

    # ── الأداء ────────────────────────────────────────────────────────
    def test_query_count_is_constant_no_matter_how_many_rows(self):
        """العقد ليس «استعلامٌ واحد» بل «عددٌ ثابت لا يتبع عدد الصفوف».

        الإيراد لا يسكن في جدول الحركات فيلزمه مرورٌ ثانٍ؛ وما يجب أن يُحرَس هو
        ألّا يتحوّل ذلك المرور إلى استعلامٍ لكل صفّ. فيُقاس التقرير على البيانات
        كما هي، ثم على ضِعفها تقريباً — والعدد نفسه.
        """
        from core.reports import run_report

        params = {"from": "2026-01-01", "to": "2026-12-31", "group_by": "product"}

        def _count():
            with CaptureQueriesContext(connection) as captured:
                payload = run_report("stock-by-dimension", self.tenant.TenantID, params)
            self.assertTrue(payload["rows"])
            return len(captured.captured_queries), len(payload["rows"])

        before, rows_before = _count()

        # صفوف جديدة بمنتجاتٍ وفواتير جديدة — لا تكرارٌ لصفٍّ قائم.
        for index in range(6):
            product = Product.objects.create(
                tenant=self.tenant, sku=f"EXTRA-{index}", name_ar=f"منتج {index}",
                brand="ماركة أخرى", quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
            invoice = SalesInvoice.objects.create(
                tenant=self.tenant, invoice_number=f"SI-EX-{index}",
                customer=self.customer, currency=self.currency,
                invoice_date="2026-06-20", invoice_type=SalesInvoice.INVOICE_CREDIT,
                status=SalesInvoice.STATUS_POSTED,
                invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
                subtotal_excl_tax=Decimal("100"), grand_total=Decimal("100"))
            SalesInvoiceLine.objects.create(
                tenant=self.tenant, invoice=invoice, product=product,
                quantity=Decimal("1"), unit_price=Decimal("100"),
                line_total_excl_tax=Decimal("100"))
            StockMovement.objects.create(
                tenant=self.tenant, product=product, movement_type="OUT",
                quantity=Decimal("1"), unit_cost=Decimal("60"), total_cost=Decimal("60"),
                reference_type="SALE", reference_id=invoice.id,
                partner=self.customer, warehouse=self.main, movement_date="2026-06-20")

        after, rows_after = _count()
        self.assertGreater(rows_after, rows_before)
        self.assertEqual(before, after, "عدد الاستعلامات تبع عدد الصفوف")
        # سقفٌ صريح كي لا يتسلّل مرورٌ ثالث بلا أن يلاحظه أحد.
        self.assertLessEqual(after, 5, "الصفحة تجاوزت خمسة استعلامات")

    def test_unknown_axis_falls_back_instead_of_failing(self):
        """محورٌ لا نعرفه يعود للافتراضي — رابطٌ قديم لا يُسقط الشاشة."""
        data = self._run(group_by="لا-يوجد")
        self.assertEqual(data["columns"][0]["header"], "المورد")

    def test_a_report_without_drill_says_so_instead_of_pretending(self):
        res = self.client.get(
            "/api/reports/low-stock/drill/", self._params(), **self._headers())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("لا يُنقَّب", res.data["error"])
