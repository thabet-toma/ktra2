"""#41 — اسم المنتج المعروض يحمل براندَه: الإرسالية وفاتورتها ونقاط أخرى.

السياق الوحيد الذي يُظهر العطب أخوان تحت أبٍ واحد؛ صنفٌ منفرد لا يثبت شيئاً
لأن اسمه مميّزٌ بالصدفة. مثال البلاغ نفسه: 215/65/16 بدانتير ايكو جرين
ودانتير جريبماكس A/T — `str(product)` كانت تُعيد «215/65/16» للاثنين معاً.

القرارات الملزمة: #37 (الجراحي لا الجذري) · #38 (القيم المجمَّدة) · #39 (الجرد)
· #40 (الواجهة). لا تُفتَح هذه القرارات هنا.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from core.models import ActivityLog
from inventory.models import Product, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem, PurchaseOrder
from logistics.serializers.goods_receipts import GoodsReceiptLineSerializer
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"
AGENT_URL = "/api/agent/products/"
AGENT_KEY = "test-agent-key-parity"


class ProductDisplayNameParityTest(APITestCase):
    """براندان تحت أبٍ واحد يظهران بأسماء مختلفة — في كل سَيمٍ لمسته #41."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pdnp", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة تناظر أسماء المنتجات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.inv_acc = Account.objects.get(tenant=cls.tenant, code="1104")
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورّد الإطارات", partner_type="Supplier",
            linked_account=Account.objects.get(tenant=cls.tenant, code="2101"))

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        get_or_create_purchase_settings(self.tenant)

    # ── أدوات بناء أخوين تحت أبٍ واحد (نظير inventory/tests/test_brand_grouping.py) ──

    def _register(self, name):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": name}, format="json", **self.headers)
        assert res.status_code == 201, res.content[:300]
        return res.json()

    def _add_brand(self, family_id, brand):
        res = self.client.post(
            f"{PRODUCTS_URL}add-brand/", {"family_id": family_id, "brand": brand},
            format="json", **self.headers,
        )
        assert res.status_code in (200, 201), res.content[:300]
        return res.json()

    def _siblings(self, size="215/65/16", brand_a="دانتير ايكو جرين",
                  brand_b="دانتير جريبماكس A/T"):
        """صنفان بنفس الاسم (المقاس) تحت أبٍ واحد ببراندين مختلفين — مثال البلاغ حرفياً."""
        first = self._register(size)
        family_id = Product.objects.get(pk=first["id"]).family_id
        named = self._add_brand(family_id, brand_a)
        second = self._add_brand(family_id, brand_b)
        p1 = Product.objects.get(pk=named["id"])
        p2 = Product.objects.get(pk=second["id"])
        assert p1.family_id == p2.family_id
        assert p1.name_ar == p2.name_ar == size
        assert p1.pk != p2.pk
        return p1, p2

    # ── 1) الاختبار الذي يمثّل البلاغ: بندا إرسالية واحدة، اسمان مختلفان ──

    def test_goods_receipt_shows_distinct_brand_names_for_siblings(self):
        """RED على الكود قبل الإصلاح: `str(product)` تُعيد «215/65/16» للسطرين
        معاً فيتساويان — راجع «إثبات الحمرة» في تقرير التنفيذ."""
        p1, p2 = self._siblings()
        res = self.client.post(
            "/api/logistics/goods-receipts/",
            {"partner": self.partner.pk, "receipt_date": "2026-06-20",
             "supplier_ref": "بوليصة 33",
             "lines": [
                 {"product_id": p1.pk, "quantity": 4, "unit_price": 100,
                  "warehouse_id": self.warehouse.pk},
                 {"product_id": p2.pk, "quantity": 6, "unit_price": 120,
                  "warehouse_id": self.warehouse.pk},
             ]},
            format="json", **self.headers)
        self.assertEqual(res.status_code, 201, res.content)
        lines = {l["product"]: l["product_name"] for l in res.json()["lines"]}

        self.assertNotEqual(lines[p1.pk], lines[p2.pk])
        self.assertIn("دانتير ايكو جرين", lines[p1.pk])
        self.assertIn("دانتير جريبماكس A/T", lines[p2.pk])
        self.assertNotEqual(lines[p1.pk], "215/65/16")
        self.assertNotEqual(lines[p2.pk], "215/65/16")

    # ── 2) الاتّساق بين المستندين: نفس النصّ حرفاً بحرف ──

    def test_invoice_and_its_receipt_show_byte_identical_names(self):
        p1, p2 = self._siblings()
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = False
        ps.save(update_fields=["receive_on_post"])

        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-PARITY-1", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=Decimal("1200"))
        i1 = PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=p1, name="215/65/16",
            quantity=Decimal("4"), unit_price=Decimal("100"), total_price=Decimal("400"))
        i2 = PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=p2, name="215/65/16",
            quantity=Decimal("6"), unit_price=Decimal("120"), total_price=Decimal("720"))

        post = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers)
        self.assertEqual(post.status_code, 201, post.content)
        recv = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/receive/",
            {"lines": [
                {"item_id": i1.id, "quantity": 4, "warehouse_id": self.warehouse.pk},
                {"item_id": i2.id, "quantity": 6, "warehouse_id": self.warehouse.pk},
            ]}, format="json", **self.headers)
        self.assertEqual(recv.status_code, 200, recv.content)

        inv_body = self.client.get(
            f"/api/logistics/purchase-invoices/{invoice.pk}/", **self.headers).json()
        inv_names = {row["product"]: row["product_name"] for row in inv_body["items"]}

        receipts = self.client.get(
            f"/api/logistics/goods-receipts/?invoice={invoice.pk}", **self.headers).json()
        receipts = receipts["results"] if isinstance(receipts, dict) else receipts
        self.assertEqual(len(receipts), 1)
        receipt_body = self.client.get(
            f"/api/logistics/goods-receipts/{receipts[0]['id']}/", **self.headers).json()
        receipt_names = {row["product"]: row["product_name"] for row in receipt_body["lines"]}

        self.assertEqual(inv_names[p1.pk], receipt_names[p1.pk])
        self.assertEqual(inv_names[p2.pk], receipt_names[p2.pk])
        self.assertNotEqual(inv_names[p1.pk], inv_names[p2.pk])
        self.assertIn("دانتير ايكو جرين", inv_names[p1.pk])
        self.assertIn("دانتير جريبماكس A/T", inv_names[p2.pk])

    # ── 3) البواقي (goods_receipts.py — outstanding) ──

    def test_outstanding_receipts_report_distinguishes_siblings(self):
        p1, p2 = self._siblings(size="185/65/15", brand_a="أرستون", brand_b="جلاكسي")
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = False
        ps.save(update_fields=["receive_on_post"])
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-PARITY-2", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=Decimal("1000"))
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=p1, name="185/65/15",
            quantity=Decimal("5"), unit_price=Decimal("100"), total_price=Decimal("500"))
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=p2, name="185/65/15",
            quantity=Decimal("5"), unit_price=Decimal("100"), total_price=Decimal("500"))
        post = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers)
        self.assertEqual(post.status_code, 201, post.content)

        report = self.client.get(
            "/api/logistics/goods-receipts/outstanding/", **self.headers).json()
        rows = {r["product"]: r["product_name"] for r in report["rows"]
                if r["invoice"] == invoice.pk}
        self.assertNotEqual(rows[p1.pk], rows[p2.pk])
        self.assertIn("أرستون", rows[p1.pk])
        self.assertIn("جلاكسي", rows[p2.pk])

    # ── 4) بند فاتورة الشراء القابل للاستلام (invoices.py — receivable-lines) ──

    def test_receivable_lines_endpoint_distinguishes_siblings(self):
        p1, p2 = self._siblings(size="225/45/17", brand_a="ميشلان", brand_b="بريدجستون")
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-PARITY-3", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=Decimal("1000"))
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=p1, name="225/45/17",
            quantity=Decimal("3"), unit_price=Decimal("100"), total_price=Decimal("300"))
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=p2, name="225/45/17",
            quantity=Decimal("3"), unit_price=Decimal("100"), total_price=Decimal("300"))

        res = self.client.get(
            f"/api/logistics/purchase-invoices/{invoice.pk}/receivable-lines/",
            **self.headers)
        self.assertEqual(res.status_code, 200, res.content)
        rows = {r["product"]: r["product_name"] for r in res.json()["lines"]}
        self.assertNotEqual(rows[p1.pk], rows[p2.pk])
        self.assertIn("ميشلان", rows[p1.pk])
        self.assertIn("بريدجستون", rows[p2.pk])

    # ── 5) المنتج الغائب: الاحتياط لم يتغيّر (`None`) ──

    def test_goods_receipt_line_falls_back_to_none_when_product_is_absent(self):
        """احتياطٌ حرفيّ كما كان — `GoodsReceiptLine.product` غير قابل لـNULL في
        القاعدة (PROTECT بلا `null=True`)، فالمسار الوحيد لبلوغ هذا الفرع نسخةٌ
        غير محفوظة في الذاكرة، تماماً كما تفعل `_Line`/`_FakeInvoice` في
        `test_purchase_receipt_visibility.py`."""
        line = GoodsReceiptLine_Unsaved()
        self.assertIsNone(GoodsReceiptLineSerializer().get_product_name(line))

    # ── 6) القيمة المجمَّدة: التحويل يجمّد البراند، والبند القديم لا يتغيّر ──

    def test_conversion_freezes_brand_and_old_lines_are_untouched(self):
        p1, p2 = self._siblings(size="205/55/16", brand_a="كونتيننتال", brand_b="بيرلي")

        # بندٌ قديمٌ محفوظ **قبل** هذا التغيير (محاكاة: يحمل المقاس عارياً فقط،
        # كما كانت `str(line.product)` تكتبه). لا شيء في هذه المهمة يمسّه.
        legacy_invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-LEGACY-1", partner=self.partner,
            currency=self.ils, invoice_date="2026-01-05",
            exchange_rate=Decimal("1"), grand_total=Decimal("100"))
        legacy_item = PurchaseInvoiceItem.objects.create(
            invoice=legacy_invoice, product=p2, name="205/55/16",
            quantity=Decimal("1"), unit_price=Decimal("100"), total_price=Decimal("100"))

        order = PurchaseOrder.objects.create(
            tenant=self.tenant, order_number="PO-PARITY-1", supplier=self.partner,
            order_date="2026-06-11", currency=self.ils, exchange_rate=Decimal("1"),
            status=PurchaseOrder.STATUS_CONFIRMED, subtotal=Decimal("100"),
            grand_total=Decimal("100"),
        )
        from logistics.models import PurchaseOrderLine
        PurchaseOrderLine.objects.create(
            tenant=self.tenant, order=order, product=p2, seq=1,
            quantity=Decimal("1"), unit_price=Decimal("100"),
        )

        from logistics.services import convert_purchase_order_to_invoice
        new_invoice, _created = convert_purchase_order_to_invoice(order, user=self.user)
        new_item = PurchaseInvoiceItem.objects.get(invoice=new_invoice)

        self.assertIn("بيرلي", new_item.name)
        self.assertEqual(new_item.name, "205/55/16 (بيرلي)")

        # لا backfill: البند القديم كما كُتب يومها بالضبط.
        legacy_item.refresh_from_db()
        self.assertEqual(legacy_item.name, "205/55/16")

    # ── 7) لافتة سجلّ النشاط: القصّ ≤200، والقيد مكتوبٌ فعلاً (يُقرأ من القاعدة) ──

    def test_agent_created_product_activity_label_is_truncated_and_persisted(self):
        from django.test import override_settings

        # 190 حرفاً (تحت حدّ `name_ar` — 200) + براند 40 حرفاً ⇒ «الاسم (البراند)»
        # يتجاوز 200 فيلزمه القصّ عند الكتابة، لا داخل `product_display_name` نفسها.
        long_name = "س" * 190
        long_brand = "ب" * 40
        with override_settings(AGENT_DB_API_KEY=AGENT_KEY):
            res = self.client.post(
                AGENT_URL,
                {"tenant_id": self.tenant.TenantID, "name_ar": long_name,
                 "brand": long_brand},
                format="json", HTTP_X_AGENT_KEY=AGENT_KEY,
            )
            self.assertEqual(res.status_code, 201, res.content[:300])
            product_id = res.json()["id"]

        # يُقرأ من القاعدة بعد الحفظ فعلاً — لا يُفترض أن الكتابة نجحت.
        activity = ActivityLog.objects.get(
            tenant=self.tenant, entity_type="product", entity_id=product_id,
            action="create",
        )
        expected = (long_name + " (" + long_brand + ")")[:200]
        self.assertEqual(len(expected), 200)  # يثبت أن المثال يتجاوز الحدّ فعلاً قبل القصّ
        self.assertEqual(activity.entity_label, expected)
        self.assertLessEqual(len(activity.entity_label), 200)


class GoodsReceiptLine_Unsaved:
    """كائنٌ خفيف يطابق شكل `GoodsReceiptLine` لموضع الاحتياط وحده — لا قاعدة بيانات."""
    product_id = None
    product = None
