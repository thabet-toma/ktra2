"""#41 — اسم المنتج المعروض يحمل براندَه: مسارات المبيعات (عروض/طلبيات/تسليم/مرتجع).

نفس السياق القاطع في كل مكان: أخوان تحت أبٍ واحد ببراندين مختلفين — صنفٌ منفرد
لا يثبت شيئاً لأن اسمه مميّزٌ بالصدفة. القرارات الملزمة #37/#38/#39/#40 لا تُعاد.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import DeliveryOrderLine, SalesInvoice, SalesInvoiceLine, SalesQuotationLine, SalesOrderLine
from sales.serializers import (
    DeliveryOrderLineSerializer,
    SalesOrderLineSerializer,
    SalesQuotationLineSerializer,
)
from sales.services import get_or_create_sales_settings
from sales.services.flow import (
    guard_sales_return_quantities,
    remaining_delivery_lines,
    returnable_lines_for_invoice,
)
from tenants.models import Currency
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class SalesProductDisplayNameParityTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="spdnp", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة تناظر المبيعات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-SP", name="ذمم", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون التناظر", partner_type="Customer",
            linked_account=cls.ar)
        cogs = Account.objects.create(
            tenant=cls.tenant, code="5101-SP", name="تكلفة", account_type="Expense",
            is_active=True)
        inv_acc = Account.objects.create(
            tenant=cls.tenant, code="1104-SP", name="مخزون", account_type="Asset",
            is_active=True)
        ss = get_or_create_sales_settings(cls.tenant)
        ss.default_cogs_account = cogs
        ss.default_inventory_account = inv_acc
        ss.save(update_fields=["default_cogs_account", "default_inventory_account"])

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    # ── أدوات: أخوان تحت أبٍ واحد (نظير inventory/tests/test_brand_grouping.py) ──

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

    def _siblings(self, size, brand_a, brand_b):
        first = self._register(size)
        family_id = Product.objects.get(pk=first["id"]).family_id
        named = self._add_brand(family_id, brand_a)
        second = self._add_brand(family_id, brand_b)
        p1 = Product.objects.get(pk=named["id"])
        p2 = Product.objects.get(pk=second["id"])
        for p in (p1, p2):
            record_stock_movement(
                product=p, movement_type="IN", quantity=Decimal("100"),
                unit_cost=Decimal("10"), reference_type="OPENING", reference_id=0,
                movement_date="2026-06-01", tenant=self.tenant)
            p.refresh_from_db()
        return p1, p2

    def _posted_invoice(self, p1, p2, *, number, stock_on_post=False):
        inv = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.customer,
            currency=self.ils, invoice_date="2026-06-15",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=stock_on_post)
        l1 = SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=p1,
            quantity=Decimal("5"), unit_price=Decimal("100"))
        l2 = SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=p2,
            quantity=Decimal("5"), unit_price=Decimal("100"))
        res = self.client.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json",
                                **self.headers)
        self.assertEqual(res.status_code, 200, res.content)
        return inv, l1, l2

    # ── 1) sales/serializers.py — DeliveryOrderLineSerializer ──

    def test_delivery_order_line_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("305/70/19", "غودير", "هانكوك")
        inv, l1, l2 = self._posted_invoice(p1, p2, number="SP-DO-1")

        res = self.client.post(
            f"/api/sales/invoices/{inv.id}/deliver/",
            {"lines": [{"line_id": l1.id, "quantity": 5}, {"line_id": l2.id, "quantity": 5}]},
            format="json", **self.headers)
        self.assertEqual(res.status_code, 200, res.content)

        listing = self.client.get(
            f"/api/sales/delivery-orders/?invoice={inv.id}", **self.headers).json()
        rows = listing["results"] if isinstance(listing, dict) else listing
        self.assertEqual(len(rows), 1)
        detail = self.client.get(
            f"/api/sales/delivery-orders/{rows[0]['id']}/", **self.headers).json()
        names = {row["product"]: row["product_name"] for row in detail["lines"]}

        self.assertNotEqual(names[p1.pk], names[p2.pk])
        self.assertIn("غودير", names[p1.pk])
        self.assertIn("هانكوك", names[p2.pk])

    def test_delivery_order_line_fallback_to_none_is_unchanged(self):
        line = DeliveryOrderLine(product=None)
        self.assertIsNone(DeliveryOrderLineSerializer().get_product_name(line))

    # ── 2) sales/serializers.py — SalesQuotationLineSerializer ──

    def test_quotation_line_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("245/40/18", "بيريلي", "فالكن")
        res = self.client.post(
            "/api/sales/quotations/",
            {"customer": self.customer.pk, "quotation_date": "2026-06-20",
             "lines": [
                 {"product": p1.pk, "quantity": "2", "unit_price": "80"},
                 {"product": p2.pk, "quantity": "3", "unit_price": "90"},
             ]},
            format="json", **self.headers)
        self.assertEqual(res.status_code, 201, res.content)
        names = {l["product"]: l["product_name"] for l in res.json()["lines"]}

        self.assertNotEqual(names[p1.pk], names[p2.pk])
        self.assertIn("بيريلي", names[p1.pk])
        self.assertIn("فالكن", names[p2.pk])

    def test_quotation_line_fallback_to_none_is_unchanged(self):
        line = SalesQuotationLine(product=None)
        self.assertIsNone(SalesQuotationLineSerializer().get_product_name(line))

    # ── 3) sales/serializers.py — SalesOrderLineSerializer ──

    def test_order_line_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("195/65/15", "كومهو", "نكسن")
        res = self.client.post(
            "/api/sales/orders/",
            {"customer": self.customer.pk, "order_date": "2026-06-20",
             "currency": self.ils.CurrencyID,
             "lines": [
                 {"product": p1.pk, "quantity": "2", "unit_price": "80"},
                 {"product": p2.pk, "quantity": "3", "unit_price": "90"},
             ]},
            format="json", **self.headers)
        self.assertEqual(res.status_code, 201, res.content)
        names = {l["product"]: l["product_name"] for l in res.json()["lines"]}

        self.assertNotEqual(names[p1.pk], names[p2.pk])
        self.assertIn("كومهو", names[p1.pk])
        self.assertIn("نكسن", names[p2.pk])

    def test_order_line_fallback_to_none_is_unchanged(self):
        line = SalesOrderLine(product=None)
        self.assertIsNone(SalesOrderLineSerializer().get_product_name(line))

    # ── 4) sales/services/flow.py — returnable_lines_for_invoice (شاشة المرتجع) ──

    def test_return_rows_show_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("225/55/17", "يوكوهاما", "تويو")
        inv, l1, l2 = self._posted_invoice(p1, p2, number="SP-RET-1")

        res = self.client.get(
            f"/api/sales/invoices/{inv.id}/returnable-lines/", **self.headers)
        self.assertEqual(res.status_code, 200, res.content)
        names = {r["product"]: r["name"] for r in res.json()["lines"]}

        self.assertNotEqual(names[p1.pk], names[p2.pk])
        self.assertIn("يوكوهاما", names[p1.pk])
        self.assertIn("تويو", names[p2.pk])

    # ── 5) sales/services/flow.py — remaining_delivery_lines (شاشة التسليم) ──

    def test_delivery_lines_endpoint_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("175/70/13", "أبولو", "سيلرون")
        inv, l1, l2 = self._posted_invoice(p1, p2, number="SP-DL-1")

        res = self.client.get(
            f"/api/sales/invoices/{inv.id}/delivery-lines/", **self.headers)
        self.assertEqual(res.status_code, 200, res.content)
        names = {r["product"]: r["product_name"] for r in res.json()["lines"]}

        self.assertNotEqual(names[p1.pk], names[p2.pk])
        self.assertIn("أبولو", names[p1.pk])
        self.assertIn("سيلرون", names[p2.pk])

    # ── 6) sales/views.py — outstanding (البواقي غير المسلَّمة) ──

    def test_outstanding_delivery_report_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("265/60/18", "كومو", "لينغلونغ")
        inv, l1, l2 = self._posted_invoice(p1, p2, number="SP-OUT-1")

        res = self.client.get("/api/sales/delivery-orders/outstanding/", **self.headers)
        self.assertEqual(res.status_code, 200, res.content)
        rows = {r["product"]: r["product_name"] for r in res.json()["rows"]
                if r["invoice"] == inv.id}
        self.assertNotEqual(rows[p1.pk], rows[p2.pk])
        self.assertIn("كومو", rows[p1.pk])
        self.assertIn("لينغلونغ", rows[p2.pk])

    # ── 7) رسالة الخطأ: حارس كمية المرتجع تسمّي المنتج ببراندٍ مميِّز ──

    def test_return_quantity_guard_message_names_the_product_with_its_brand(self):
        p1, _p2 = self._siblings("155/65/14", "دبليو دبليو", "زد زد")
        inv, l1, _l2 = self._posted_invoice(p1, _p2, number="SP-GRD-1")

        res = self.client.post(
            "/api/sales/invoices/",
            {"invoice_kind": SalesInvoice.INVOICE_KIND_SALE_RETURN,
             "invoice_date": "2026-06-20", "currency": self.ils.CurrencyID,
             "customer": self.customer.pk, "original_invoice": inv.id,
             "lines": [{"product": p1.pk, "quantity": "99", "unit_price": "100"}]},
            format="json", **self.headers)
        self.assertEqual(res.status_code, 400, res.content)
        message = str(res.data)
        self.assertIn("دبليو دبليو", message)

    def test_return_quantity_guard_falls_back_to_id_when_product_row_is_gone(self):
        """احتياطٌ حرفيّ كما كان: منتجٌ غير موجود أصلاً في الطلب ⇒ `#{id}`."""
        inv, _l1, _l2 = self._posted_invoice(*self._siblings(
            "135/80/12", "أ", "ب"), number="SP-GRD-2")
        with self.assertRaises(ValidationError) as ctx:
            guard_sales_return_quantities(
                inv, [{"product": 999999, "quantity": Decimal("1")}])
        self.assertIn("#999999", str(ctx.exception))
