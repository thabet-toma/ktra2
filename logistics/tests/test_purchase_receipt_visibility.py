"""T-RECVIS — «كم انطلب وكم وصل وكم باقي» مقروءٌ من الفاتورة نفسها.

فاتورة كبيرة تصل على دفعات (مورّد إطارات: 2100 قطعة يصل منها 550 أولاً) كانت
تخفي باقيها داخلها: `received_quantity` مكشوفٌ والطرح متروكٌ للقارئ، فلا سبيل
لمعرفة الباقي إلا بتقرير `outstanding` العام أو حسبةٍ باليد.

يُثبت هنا أمران: أن الفاتورة صارت تحمل الباقي لكل بند وملخّصاً في رأسها، وأن
رقمها **هو** رقم تقرير البواقي لا نسخةٌ منه — فالقاعدة صارت دالّةً واحدة
(`purchase_invoice_receipt_summary`) لا ستّ نسخ متطابقة اليوم ومتباعدة غداً.
وتقرير `outstanding` كان بلا أي اختبار قبل هذا الملف.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import (
    get_or_create_purchase_settings,
    purchase_invoice_receipt_summary,
    purchase_item_receipt_quantities,
    receive_purchase_invoice,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class _Line:
    """بند خفيف — الدالّة تقرأ حقلين اثنين فلا تلزمها قاعدة بيانات."""

    def __init__(self, quantity, received, product_id=1):
        self.quantity = quantity
        self.received_quantity = received
        self.product_id = product_id


class _Rel:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeInvoice:
    def __init__(self, lines):
        self.items = _Rel(lines)


class PurchaseItemReceiptQuantitiesTest(APITestCase):
    def test_remaining_is_ordered_minus_received(self):
        assert purchase_item_receipt_quantities(
            _Line(Decimal("100"), Decimal("40"))) == (
            Decimal("100"), Decimal("40"), Decimal("60"))
        # الشكل ثابت على دقّة العمود مهما كانت الحالة — لا «0» مقابل «60.0000».
        assert [str(v) for v in purchase_item_receipt_quantities(
            _Line(Decimal("100"), Decimal("40")))] == [
            "100.0000", "40.0000", "60.0000"]

    def test_over_receipt_never_yields_a_negative_remaining(self):
        """استلامٌ زائد باقيه صفر — لا رقمٌ سالب يقتطع من مجموع بندٍ آخر."""
        assert purchase_item_receipt_quantities(
            _Line(Decimal("10"), Decimal("13")))[2] == Decimal("0")
        assert str(purchase_item_receipt_quantities(
            _Line(Decimal("10"), Decimal("13")))[2]) == "0.0000"

    def test_none_quantities_read_as_zero(self):
        assert purchase_item_receipt_quantities(_Line(None, None))[2] == Decimal("0")


class PurchaseInvoiceReceiptSummaryTest(APITestCase):
    def test_service_line_without_product_is_not_counted(self):
        """بند خدمة لا يدخل مستودعاً، فلا يُبقي الفاتورة ناقصةً إلى الأبد."""
        assert purchase_invoice_receipt_summary(_FakeInvoice([
            _Line(Decimal("100"), Decimal("40")),
            _Line(Decimal("999"), Decimal("0"), product_id=None),
        ])) == {
            "ordered": Decimal("100"), "received": Decimal("40"),
            "remaining": Decimal("60"), "lines_total": 1, "lines_remaining": 1,
        }

    def test_fully_received_line_does_not_inflate_lines_remaining(self):
        summary = purchase_invoice_receipt_summary(_FakeInvoice([
            _Line(Decimal("50"), Decimal("50")),
            _Line(Decimal("50"), Decimal("10")),
        ]))
        assert summary["remaining"] == Decimal("40")
        assert (summary["lines_total"], summary["lines_remaining"]) == (2, 1)


class PurchaseInvoiceReceiptVisibilityAPITest(APITestCase):
    """الفاتورة المرحّلة المستلمة جزئياً تعرض باقيها — وبنفس رقم التقرير."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="recvis", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الإطارات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورّد الإطارات", partner_type="Supplier",
            linked_account=Account.objects.get(tenant=cls.tenant, code="2101"))
        cls.p1 = Product.objects.create(
            tenant=cls.tenant, sku="TYR-1", name_ar="إطار 205/55",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        cls.p2 = Product.objects.create(
            tenant=cls.tenant, sku="TYR-2", name_ar="إطار 225/45",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def setUp(self):
        # الاستلام فعلٌ مستقلّ عن الترحيل — هذا هو سيناريو الوصول على دفعات.
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = False
        ps.save(update_fields=["receive_on_post"])
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

        self.invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-0033", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=Decimal("21000"))
        self.i1 = PurchaseInvoiceItem.objects.create(
            invoice=self.invoice, product=self.p1, name="إطار 205/55",
            quantity=Decimal("1500"), unit_price=Decimal("10"),
            total_price=Decimal("15000"))
        self.i2 = PurchaseInvoiceItem.objects.create(
            invoice=self.invoice, product=self.p2, name="إطار 225/45",
            quantity=Decimal("600"), unit_price=Decimal("10"),
            total_price=Decimal("6000"))

    def _post_invoice(self):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{self.invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers)
        assert res.status_code == 201, res.content

    def _receive_first_item(self, qty):
        receive_purchase_invoice(
            self.invoice,
            lines=[{"item_id": self.i1.id, "quantity": qty,
                    "warehouse_id": self.warehouse.id}],
            user=self.user)
        self.invoice.refresh_from_db()

    def _read_invoice(self):
        res = self.client.get(
            f"/api/logistics/purchase-invoices/{self.invoice.pk}/", **self.headers)
        assert res.status_code == 200, res.content
        return res.json()

    def test_invoice_read_carries_line_remaining_and_header_summary(self):
        self._post_invoice()
        self._receive_first_item(Decimal("550"))

        body = self._read_invoice()
        assert body["receipt_status"] == PurchaseInvoice.RECEIPT_PARTIAL
        assert body["receipt_progress"] == {
            "ordered": "2100.0000", "received": "550.0000",
            "remaining": "1550.0000", "lines_total": 2, "lines_remaining": 2,
        }
        by_id = {row["id"]: row for row in body["items"]}
        assert by_id[self.i1.id]["received_quantity"] == "550.0000"
        assert by_id[self.i1.id]["remaining_quantity"] == "950.0000"
        assert by_id[self.i2.id]["received_quantity"] == "0.0000"
        assert by_id[self.i2.id]["remaining_quantity"] == "600.0000"

    def test_header_summary_equals_the_outstanding_report(self):
        """رقمان على شاشتين لا يجوز أن يفترقا — والمصدر دالّةٌ واحدة."""
        self._post_invoice()
        self._receive_first_item(Decimal("550"))

        header = self._read_invoice()["receipt_progress"]
        report = self.client.get(
            "/api/logistics/goods-receipts/outstanding/", **self.headers).json()
        report_remaining = sum(
            (Decimal(row["remaining_quantity"]) for row in report["rows"]
             if row["invoice"] == self.invoice.pk), Decimal("0"))

        assert report_remaining == Decimal(header["remaining"]) == Decimal("1550")

    def test_fully_received_invoice_reports_zero_remaining(self):
        self._post_invoice()
        receive_purchase_invoice(
            self.invoice,
            lines=[
                {"item_id": self.i1.id, "quantity": Decimal("1500"),
                 "warehouse_id": self.warehouse.id},
                {"item_id": self.i2.id, "quantity": Decimal("600"),
                 "warehouse_id": self.warehouse.id},
            ],
            user=self.user)

        body = self._read_invoice()
        assert body["receipt_status"] == PurchaseInvoice.RECEIPT_FULL
        assert body["receipt_progress"]["remaining"] == "0.0000"
        assert body["receipt_progress"]["lines_remaining"] == 0
        # والفاتورة المكتملة تختفي من تقرير البواقي أصلاً.
        report = self.client.get(
            "/api/logistics/goods-receipts/outstanding/", **self.headers).json()
        assert [r for r in report["rows"] if r["invoice"] == self.invoice.pk] == []
