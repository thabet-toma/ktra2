"""#26: تقارير المنتجات — التجميع على المنتج افتراضاً، والتنقيب إلى البراند.

المعيار الحاسم في كل اختبار هنا: صفٌّ واحد لكل منتج (لا لكل براند)، ومجموع
تنقيبه = رقم الصفّ بالضبط (`docs/modules/core.md` — 6.1.1). والتكلفة المجمَّعة
متوسطٌ **مرجَّح بالكمية** — مثال المالك نفسه (#14): 40 وحدة بتكلفة 22.5 وبرندٌ
شاذّ بقطعتين بتكلفة 40 لا يجوز أن يسحب متوسط المنتج نحوه.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from inventory.models import Product, ProductFamily, StockMovement
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company


def _run(client, key, tenant_id, **params):
    res = client.get(f"/api/reports/{key}/", params, HTTP_X_TENANT_ID=str(tenant_id))
    assert res.status_code == 200, res.content[:400]
    return res.json()


def _drill(client, key, tenant_id, row, **params):
    """يقرأ مفاتيح الصفّ كما تفعل الشاشة — لا معرفةً مكتوبة بمفاتيح تقريرٍ بعينه."""
    catalog_row_keys = ("family_id", "product_id")
    for k in catalog_row_keys:
        params[k] = row.get(k, "")
    res = client.get(
        f"/api/reports/{key}/drill/", params, HTTP_X_TENANT_ID=str(tenant_id))
    assert res.status_code == 200, res.content[:400]
    return res.json()


class FamilyRollupReportsTest(APITestCase):
    """منتجٌ بثلاثة برانداتٍ عبر أربعة تقارير: تقييم المخزون، تحت حدّ الطلب،
    المبيعات حسب المنتج، والمشتريات حسب المنتج."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="family-reporter", password="x")
        cls.other_user = User.objects.create_user(username="family-outsider", password="x")
        cls.tenant = create_company("شركة التجميع", cls.user)
        cls.other_tenant = create_company("شركة الجوار", cls.other_user)
        cls.currency, _ = Currency.objects.get_or_create(
            Code="FAM", defaults={"Name": "Family", "Symbol": "F"})

        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون التجميع", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد التجميع", partner_type="Supplier")

        # المنتج: مقاس 195/85/15 — مثال المالك بالضبط، وبرندٌ ثالث فوقه.
        cls.family = ProductFamily.objects.create(
            tenant=cls.tenant, name_ar="مقاس 195/85/15", min_stock_level=100,
        )
        cls.brand_a = Product.objects.create(
            tenant=cls.tenant, family=cls.family, sku="TIRE-A", brand="دانتير",
            name_ar="195/85/15 دانتير", quantity_on_hand=Decimal("40"),
            avg_cost=Decimal("22.5"), min_stock_level=100,
        )
        cls.brand_b = Product.objects.create(
            tenant=cls.tenant, family=cls.family, sku="TIRE-B", brand="أوتولوكس",
            name_ar="195/85/15 أوتولوكس", quantity_on_hand=Decimal("2"),
            avg_cost=Decimal("40"), min_stock_level=100,
        )
        cls.brand_c = Product.objects.create(
            tenant=cls.tenant, family=cls.family, sku="TIRE-C", brand="سي",
            name_ar="195/85/15 سي", quantity_on_hand=Decimal("8"),
            avg_cost=Decimal("25"), min_stock_level=100,
        )
        # منتجٌ بلا أبٍ — يبقى صفّاً بمفرده كسابق عهده.
        cls.standalone = Product.objects.create(
            tenant=cls.tenant, sku="STD-1", brand="", name_ar="منتج مستقل",
            quantity_on_hand=Decimal("1"), avg_cost=Decimal("10"), min_stock_level=3,
        )

        # عائلةٌ أخرى في شركة الجوار — تُثبت عزل الشركات.
        cls.other_family = ProductFamily.objects.create(
            tenant=cls.other_tenant, name_ar="عائلة الجوار", min_stock_level=5,
        )
        Product.objects.create(
            tenant=cls.other_tenant, family=cls.other_family, sku="OTH-A", brand="غ",
            name_ar="منتج الجوار", quantity_on_hand=Decimal("1"), avg_cost=Decimal("9"),
            min_stock_level=5,
        )

        # مبيعات: برندان من نفس المنتج بفاتورة واحدة، بحركة صرفٍ مكلَّفة لكل سطر.
        cls.sale = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="SI-FAM-1", customer=cls.customer,
            currency=cls.currency, invoice_date="2026-06-10",
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
            status=SalesInvoice.STATUS_POSTED,
            subtotal_excl_tax=Decimal("230"), grand_total=Decimal("230"),
        )
        SalesInvoiceLine.objects.create(
            tenant=cls.tenant, invoice=cls.sale, product=cls.brand_a,
            quantity=Decimal("3"), unit_price=Decimal("50"),
            line_total_excl_tax=Decimal("150"),
        )
        SalesInvoiceLine.objects.create(
            tenant=cls.tenant, invoice=cls.sale, product=cls.brand_b,
            quantity=Decimal("1"), unit_price=Decimal("80"),
            line_total_excl_tax=Decimal("80"),
        )
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.brand_a, movement_type="OUT",
            quantity=Decimal("3"), unit_cost=Decimal("20"), total_cost=Decimal("60"),
            reference_type="SALE", reference_id=cls.sale.id, movement_date="2026-06-10",
        )
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.brand_b, movement_type="OUT",
            quantity=Decimal("1"), unit_cost=Decimal("35"), total_cost=Decimal("35"),
            reference_type="SALE", reference_id=cls.sale.id, movement_date="2026-06-10",
        )

        # مشتريات: برندان من نفس المنتج بفاتورة شراءٍ واحدة.
        cls.purchase = PurchaseInvoice.objects.create(
            tenant=cls.tenant, invoice_number="PI-FAM-1", partner=cls.supplier,
            currency=cls.currency, invoice_date="2026-05-01",
            grand_total=Decimal("150"), is_posted=True, is_return=False,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=cls.purchase, product=cls.brand_a, name=cls.brand_a.name_ar,
            quantity=Decimal("5"), unit_price=Decimal("20"), total_price=Decimal("100"),
        )
        PurchaseInvoiceItem.objects.create(
            invoice=cls.purchase, product=cls.brand_b, name=cls.brand_b.name_ar,
            quantity=Decimal("1"), unit_price=Decimal("50"), total_price=Decimal("50"),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _params(self, **over):
        params = {"from": "2026-01-01", "to": "2026-12-31"}
        params.update(over)
        return params

    # ── تقييم المخزون: متوسطٌ مرجَّح، لا بسيط ──────────────────────────
    def test_stock_valuation_rolls_up_to_one_row_with_weighted_average_cost(self):
        data = _run(self.client, "stock-valuation", self.tenant.TenantID, **self._params())
        rows = {r["name"]: r for r in data["rows"]}

        # صفٌّ واحد للمنتج المجمَّع — لا ثلاثة.
        self.assertIn("مقاس 195/85/15", rows)
        self.assertNotIn("195/85/15 دانتير", rows)
        family_row = rows["مقاس 195/85/15"]
        self.assertEqual(family_row["sku"], "")
        self.assertEqual(Decimal(family_row["quantity"]), Decimal("50"))  # 40+2+8

        # المرجَّح بالكمية: (40×22.5 + 2×40 + 8×25) ÷ 50 = 23.60
        weighted = (
            Decimal("40") * Decimal("22.5") + Decimal("2") * Decimal("40")
            + Decimal("8") * Decimal("25")
        ) / Decimal("50")
        self.assertEqual(weighted, Decimal("23.6"))
        self.assertEqual(Decimal(family_row["avg_cost"]), weighted)

        # والاختبار الذي يفشل مع متوسطٍ بسيط: (22.5+40+25)/3 = 29.1666… ≠ 23.6.
        simple_average = (Decimal("22.5") + Decimal("40") + Decimal("25")) / Decimal("3")
        self.assertNotEqual(Decimal(family_row["avg_cost"]), simple_average.quantize(Decimal("0.01")))

        # القيمة نفسها: مجموع (كمية×تكلفة) — تحقُّقٌ مستقلّ عن صيغة المتوسط.
        total_value = (
            Decimal("40") * Decimal("22.5") + Decimal("2") * Decimal("40")
            + Decimal("8") * Decimal("25")
        )
        self.assertEqual(Decimal(family_row["value"]), total_value)

        # المنتج المستقلّ يبقى صفّاً بمفرده بنفس القيم القديمة تماماً.
        standalone_row = rows["منتج مستقل"]
        self.assertEqual(standalone_row["sku"], "STD-1")
        self.assertEqual(Decimal(standalone_row["quantity"]), Decimal("1"))
        self.assertEqual(Decimal(standalone_row["avg_cost"]), Decimal("10"))

        # عزل الشركة.
        self.assertNotIn("منتج الجوار", rows)

    def test_stock_valuation_drill_sums_to_the_family_row(self):
        data = _run(self.client, "stock-valuation", self.tenant.TenantID, **self._params())
        family_row = next(r for r in data["rows"] if r["name"] == "مقاس 195/85/15")
        self.assertIsNotNone(data["drill"], "التقرير يجب أن يُعلن أنه يُنقَّب")

        drill = _drill(
            self.client, "stock-valuation", self.tenant.TenantID, family_row,
            **self._params(),
        )
        self.assertEqual({r["brand"] for r in drill["rows"]}, {"دانتير", "أوتولوكس", "سي"})
        self.assertEqual(len(drill["rows"]), 3)

        # مجموع تفصيل البراندات = رقم صفّ المنتج، عموداً بعمود.
        self.assertEqual(Decimal(drill["totals"]["quantity"]), Decimal(family_row["quantity"]))
        self.assertEqual(Decimal(drill["totals"]["value"]), Decimal(family_row["value"]))

    def test_stock_valuation_drill_of_a_foreign_family_returns_nothing(self):
        row = {"family_id": self.other_family.pk, "product_id": ""}
        drill = _drill(
            self.client, "stock-valuation", self.tenant.TenantID, row, **self._params(),
        )
        self.assertEqual(drill["rows"], [])

    def test_stock_valuation_query_count_does_not_scale_with_row_count(self):
        from core.reports import run_report

        params = self._params()

        def _count():
            with CaptureQueriesContext(connection) as captured:
                payload = run_report("stock-valuation", self.tenant.TenantID, params)
            self.assertTrue(payload["rows"])
            return len(captured.captured_queries), len(payload["rows"])

        before, rows_before = _count()
        for i in range(6):
            Product.objects.create(
                tenant=self.tenant, sku=f"EXTRA-{i}", brand="أخرى",
                name_ar=f"منتج إضافي {i}", quantity_on_hand=Decimal("1"),
                avg_cost=Decimal("1"),
            )
        after, rows_after = _count()
        self.assertGreater(rows_after, rows_before)
        self.assertEqual(before, after, "عدد الاستعلامات تبع عدد الصفوف")
        self.assertLessEqual(after, 3, "التقرير تجاوز سقف الاستعلامات الثابت")

    # ── تحت حدّ الطلب ─────────────────────────────────────────────────
    def test_low_stock_rolls_up_the_family_and_leaves_the_standalone_product_untouched(self):
        data = _run(self.client, "low-stock", self.tenant.TenantID, **self._params())
        rows = {r["name"]: r for r in data["rows"]}

        # 40+2+8 = 50 متاح، الحدّ 100 ⇒ منخفض، النقص 50 — صفٌّ واحد.
        self.assertIn("مقاس 195/85/15", rows)
        family_row = rows["مقاس 195/85/15"]
        self.assertEqual(family_row["status"], "منخفض")
        self.assertEqual(Decimal(family_row["quantity"]), Decimal("50"))
        self.assertEqual(Decimal(family_row["min_stock_level"]), Decimal("100"))
        self.assertEqual(Decimal(family_row["shortage"]), Decimal("50"))

        # المنتج المستقلّ: رصيد 1 وحدٌّ 3 ⇒ نقص 2 — كما كان قبل #26 تماماً.
        standalone_row = rows["منتج مستقل"]
        self.assertEqual(standalone_row["status"], "منخفض")
        self.assertEqual(Decimal(standalone_row["quantity"]), Decimal("1"))
        self.assertEqual(Decimal(standalone_row["shortage"]), Decimal("2"))

    def test_low_stock_drill_sums_to_the_family_row(self):
        data = _run(self.client, "low-stock", self.tenant.TenantID, **self._params())
        family_row = next(r for r in data["rows"] if r["name"] == "مقاس 195/85/15")
        drill = _drill(
            self.client, "low-stock", self.tenant.TenantID, family_row, **self._params(),
        )
        self.assertEqual(len(drill["rows"]), 3)
        self.assertEqual(Decimal(drill["totals"]["quantity"]), Decimal(family_row["quantity"]))

    # ── المبيعات حسب المنتج ──────────────────────────────────────────
    def test_sales_by_product_rolls_up_the_family(self):
        data = _run(self.client, "sales-by-product", self.tenant.TenantID, **self._params())
        rows = {r["name"]: r for r in data["rows"]}
        self.assertIn("مقاس 195/85/15", rows)
        family_row = rows["مقاس 195/85/15"]
        self.assertEqual(Decimal(family_row["quantity"]), Decimal("4"))  # 3+1
        self.assertEqual(Decimal(family_row["net_sales"]), Decimal("230"))
        self.assertEqual(Decimal(family_row["cost"]), Decimal("95"))  # 60+35
        self.assertEqual(Decimal(family_row["profit"]), Decimal("135"))

    def test_sales_by_product_drill_sums_to_the_family_row(self):
        data = _run(self.client, "sales-by-product", self.tenant.TenantID, **self._params())
        family_row = next(r for r in data["rows"] if r["name"] == "مقاس 195/85/15")
        drill = _drill(
            self.client, "sales-by-product", self.tenant.TenantID, family_row,
            **self._params(),
        )
        self.assertEqual({r["sku"] for r in drill["rows"]}, {"TIRE-A", "TIRE-B"})
        self.assertEqual(Decimal(drill["totals"]["net_sales"]), Decimal(family_row["net_sales"]))
        self.assertEqual(Decimal(drill["totals"]["profit"]), Decimal(family_row["profit"]))

    # ── المشتريات حسب المنتج ─────────────────────────────────────────
    def test_purchases_by_product_rolls_up_the_family(self):
        data = _run(self.client, "purchases-by-product", self.tenant.TenantID, **self._params())
        rows = {r["name"]: r for r in data["rows"]}
        self.assertIn("مقاس 195/85/15", rows)
        family_row = rows["مقاس 195/85/15"]
        self.assertEqual(Decimal(family_row["quantity"]), Decimal("6"))  # 5+1
        self.assertEqual(Decimal(family_row["total_price"]), Decimal("150"))  # 100+50

    def test_purchases_by_product_drill_sums_to_the_family_row(self):
        data = _run(self.client, "purchases-by-product", self.tenant.TenantID, **self._params())
        family_row = next(r for r in data["rows"] if r["name"] == "مقاس 195/85/15")
        drill = _drill(
            self.client, "purchases-by-product", self.tenant.TenantID, family_row,
            **self._params(),
        )
        self.assertEqual({r["sku"] for r in drill["rows"]}, {"TIRE-A", "TIRE-B"})
        self.assertEqual(
            Decimal(drill["totals"]["total_price"]), Decimal(family_row["total_price"]),
        )

    # ── #26-دلتا — فلتر `product` يختار براندًا، لا حقيقةً عن كل العائلة ──
    # قاعدة: صفّ العائلة أرقامه مجموع كل أبنائها، أو لا يظهر أصلاً. حين يضيق
    # `?product=` النتيجة لبراندٍ واحد، يجب أن يعود صفُّ ذلك البراند الحقيقي
    # — sku/برند كما هما — لا صفَّ عائلةٍ فارغَ الهوية يحمل رقم برندٍ واحد.

    def test_stock_valuation_product_filter_returns_a_real_brand_row_not_a_hollow_family_row(self):
        data = _run(
            self.client, "stock-valuation", self.tenant.TenantID,
            **self._params(product=self.brand_a.id),
        )
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["sku"], "TIRE-A")
        self.assertEqual(row["brand"], "دانتير")
        self.assertNotEqual(row["name"], "مقاس 195/85/15")
        self.assertEqual(Decimal(row["quantity"]), Decimal("40"))
        self.assertEqual(Decimal(row["avg_cost"]), Decimal("22.5"))
        self.assertEqual(Decimal(row["value"]), Decimal("900"))

    def test_low_stock_product_filter_returns_a_real_brand_row_not_a_hollow_family_row(self):
        data = _run(
            self.client, "low-stock", self.tenant.TenantID,
            **self._params(product=self.brand_a.id),
        )
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["sku"], "TIRE-A")
        self.assertNotEqual(row["name"], "مقاس 195/85/15")
        # رقمه هو رقمه — رصيده وحده (40) لا مجموع العائلة (50).
        self.assertEqual(Decimal(row["quantity"]), Decimal("40"))
        self.assertEqual(Decimal(row["min_stock_level"]), Decimal("100"))
        self.assertEqual(Decimal(row["shortage"]), Decimal("60"))

    def test_sales_by_product_product_filter_returns_a_real_brand_row(self):
        data = _run(
            self.client, "sales-by-product", self.tenant.TenantID,
            **self._params(product=self.brand_a.id),
        )
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["sku"], "TIRE-A")
        self.assertNotEqual(row["name"], "مقاس 195/85/15")
        self.assertEqual(Decimal(row["quantity"]), Decimal("3"))
        self.assertEqual(Decimal(row["net_sales"]), Decimal("150"))
        self.assertEqual(Decimal(row["cost"]), Decimal("60"))
        self.assertEqual(Decimal(row["profit"]), Decimal("90"))

    def test_purchases_by_product_product_filter_returns_a_real_brand_row(self):
        data = _run(
            self.client, "purchases-by-product", self.tenant.TenantID,
            **self._params(product=self.brand_a.id),
        )
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["sku"], "TIRE-A")
        self.assertNotEqual(row["name"], "مقاس 195/85/15")
        self.assertEqual(Decimal(row["quantity"]), Decimal("5"))
        self.assertEqual(Decimal(row["total_price"]), Decimal("100"))


class DivergentThresholdLowStockTest(APITestCase):
    """عائلةٌ بلا حدٍّ يدويٍّ على الأب — فيسقط كلّ ابنٍ على مقترَحه الخاص
    (عيبٌ سابقٌ لـ#25، غير مُصحَّحٍ هنا)، فبرندٌ يصير «منخفضاً» وآخر «متوفّراً»
    بنفس المتاح العائلي. المعيار الحاسم: صفّ العائلة يعرض متاح العائلة **كله**
    لا نصيب البرند الذي رفع الراية وحده، والتنقيب يسرد كل الإخوة — حتى
    المتوفّرين — كي يطابق مجموعه رقم الصفّ."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="divergent-reporter", password="x")
        cls.tenant = create_company("شركة الانحراف", cls.user)
        cls.today = timezone.localdate()

        # بلا `min_stock_level` على الأب — كل ابنٍ يسقط على مقترَحه الخاص.
        cls.family = ProductFamily.objects.create(
            tenant=cls.tenant, name_ar="عائلة منحرفة الحدّ",
        )
        cls.brand_a = Product.objects.create(
            tenant=cls.tenant, family=cls.family, sku="DIV-A", brand="أ",
            name_ar="منحرف أ", quantity_on_hand=Decimal("2"), avg_cost=Decimal("10"),
        )
        cls.brand_b = Product.objects.create(
            tenant=cls.tenant, family=cls.family, sku="DIV-B", brand="ب",
            name_ar="منحرف ب", quantity_on_hand=Decimal("18"), avg_cost=Decimal("10"),
        )
        # تاريخ مبيعاتٍ حقيقي للبرند «أ» وحده — يمنحه مقترَحاً محسوباً موجباً
        # (نفس نمط `test_reports_replenishment.py` — تسع حركاتٍ أسبوعية).
        for week in range(1, 10):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.brand_a, movement_type="OUT",
                quantity=Decimal("30"),
                movement_date=cls.today - datetime.timedelta(days=week * 7),
            )
        # البرند «ب» بلا أي حركة — سجلّه قصيرٌ فمقترَحه صفر، فيبقى «متوفّراً».

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _params(self, **over):
        params = {"from": "2026-01-01", "to": "2026-12-31"}
        params.update(over)
        return params

    def test_family_row_shows_the_full_family_available_not_the_flagging_brands_slice(self):
        from core.replenishment import replenishment_rows

        ground_truth = replenishment_rows(
            self.tenant.TenantID, product_ids=[self.brand_a.id, self.brand_b.id],
        )
        pr_a = next(r for r in ground_truth if r["product_id"] == self.brand_a.id)
        pr_b = next(r for r in ground_truth if r["product_id"] == self.brand_b.id)

        # شرطٌ لازم لصحّة الاختبار: الانحراف تحقّق فعلاً — وإلا فالاختبار لا
        # يفحص شيئاً (نفس تحذير التذكرة حرفياً).
        self.assertIn(pr_a["status"], ("low_stock", "out_of_stock"))
        self.assertEqual(pr_b["status"], "in_stock")
        self.assertEqual(pr_a["family_available"], pr_b["family_available"])
        family_available = pr_a["family_available"]
        self.assertEqual(family_available, Decimal("20"))  # 2 + 18
        verdict_threshold = Decimal(str(pr_a["effective_min"]))
        self.assertGreater(verdict_threshold, Decimal("0"))

        data = _run(self.client, "low-stock", self.tenant.TenantID, **self._params())
        row = next(r for r in data["rows"] if r["name"] == "عائلة منحرفة الحدّ")

        # العيب القديم: «المتاح» كان رصيد البرند «أ» وحده (2) — والصحيح متاح
        # العائلة كلّه (20)، وهو نفس ما قِيس عليه الحكم فعلاً.
        self.assertEqual(Decimal(row["quantity"]), family_available)
        self.assertNotEqual(Decimal(row["quantity"]), pr_a["available"])
        self.assertEqual(Decimal(row["min_stock_level"]), verdict_threshold)
        self.assertEqual(
            Decimal(row["shortage"]), max(verdict_threshold - family_available, Decimal("0")),
        )
        # ولا يعود يناقض «رصيد الصنف» المجاور له في نفس السطر.
        self.assertEqual(Decimal(row["group_available"]), family_available)

    def test_drill_lists_every_brand_including_the_in_stock_one_and_sums_exactly(self):
        data = _run(self.client, "low-stock", self.tenant.TenantID, **self._params())
        row = next(r for r in data["rows"] if r["name"] == "عائلة منحرفة الحدّ")
        drill = _drill(self.client, "low-stock", self.tenant.TenantID, row, **self._params())

        skus = {r["sku"] for r in drill["rows"]}
        self.assertEqual(
            skus, {"DIV-A", "DIV-B"},
            "العيب القديم كان يُسقط البرند المتوفّر من التنقيب فلا يطابق مجموعه رقم الصفّ",
        )
        self.assertEqual(Decimal(drill["totals"]["quantity"]), Decimal(row["quantity"]))
