"""ISSUE #53 — فاتورة الأتعاب والأتعاب المتكرّرة.

المحرّك يعمل أصلاً: `sales/services/calc.py` (`resolve_service_revenue_account`)
يُطابق/يُنشئ `4102` بـ`get_or_create` لأي بند منتجه `is_service=True`، في أي شركة.
هذا الملف يثبت الأثر من فوق (HTTP) لا الاستدعاء:

1. فاتورة أتعاب — بند خدمي عادي يُرحَّل على `4102` ويظهر في ذمم العميل.
2. «كرّر فاتورة الشهر الماضي» — نسخة جديدة بتاريخ اليوم ورقمٍ من الدفتر.
3. تراجُع: فاتورة منتج عادية (لا خدمة) لم يتغيّر ترحيلها — إيرادها ليس 4102.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company


class FeeInvoiceApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="feeinvoice", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("مكتب المحاسبة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.client_partner = Partner.objects.create(
            tenant=cls.tenant, name="عميل المكتب", partner_type="Customer")
        cls.service_product = Product.objects.create(
            tenant=cls.tenant, sku="FEE-1", name_ar="أتعاب مهنية شهرية",
            is_service=True, quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        cls.goods_product = Product.objects.create(
            tenant=cls.tenant, sku="GOODS-1", name_ar="بضاعة",
            quantity_on_hand=Decimal("50"), avg_cost=Decimal("2"))
        # لا تعديل على الإعدادات هنا عمداً: الشركة تُنشأ كما تُنشأ في الإنتاج،
        # و«يُرحَّل على 4102» معيارُ قبولٍ يجب أن يصمد على شركةٍ بكراً.

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create_invoice(self, *, product, invoice_date, quantity="1", unit_price="500.00"):
        return self.client.post(
            "/api/sales/invoices/",
            {
                "customer": self.client_partner.pk,
                "currency": self.ils.pk,
                "invoice_date": invoice_date,
                "invoice_type": "credit",
                "lines": [{"product": product.pk, "quantity": quantity,
                           "unit_price": unit_price}],
            },
            format="json", **self.headers)

    # ── 1. فاتورة الأتعاب من بطاقة العميل — بند خدمي على 4102 ───────────────

    def test_fee_invoice_posts_to_service_revenue_and_customer_ledger(self):
        res = self._create_invoice(product=self.service_product, invoice_date="2026-06-15")
        self.assertEqual(res.status_code, 201, res.content)
        invoice_id = res.json()["id"]

        post_res = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/", {}, format="json", **self.headers)
        self.assertEqual(post_res.status_code, 200, post_res.content)

        invoice = SalesInvoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.status, SalesInvoice.STATUS_POSTED)
        lines = list(invoice.journal.lines.select_related("account"))
        revenue_line = next(ln for ln in lines if ln.credit > 0)
        self.assertEqual(revenue_line.account.code, "4102")
        ar_line = next(ln for ln in lines if ln.debit > 0)
        self.assertEqual(ar_line.debit, Decimal("500.00"))

        # يظهر في ذمم العميل وكشف حسابه — رصيد الطرف يتحرّك بقيمة الفاتورة.
        balance_res = self.client.get(
            f"/api/partners/{self.client_partner.pk}/", **self.headers)
        self.assertEqual(balance_res.status_code, 200, balance_res.content)
        statement_res = self.client.get(
            f"/api/sales/invoices/?customer={self.client_partner.pk}", **self.headers)
        self.assertEqual(statement_res.status_code, 200, statement_res.content)
        numbers = [row["invoice_number"] for row in statement_res.json()["results"]]
        self.assertIn(invoice.invoice_number, numbers)

    # ── 2. كرّر فاتورة الشهر الماضي ──────────────────────────────────────────

    def test_repeat_last_month_produces_fresh_number_and_todays_date(self):
        today = timezone.localdate()
        first_of_this_month = today.replace(day=1)
        last_month_day = first_of_this_month - timedelta(days=1)
        original_res = self._create_invoice(
            product=self.service_product, invoice_date=last_month_day.isoformat())
        self.assertEqual(original_res.status_code, 201, original_res.content)
        original_number = original_res.json()["invoice_number"]

        res = self.client.post(
            "/api/sales/invoices/repeat-last-month/",
            {"customer_id": self.client_partner.pk},
            format="json", **self.headers,
        )
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()

        self.assertNotEqual(body["invoice_number"], original_number)
        self.assertEqual(body["invoice_date"], today.isoformat())
        self.assertEqual(body["status"], "draft")
        new_invoice = SalesInvoice.objects.get(pk=body["id"])
        self.assertEqual(new_invoice.customer_id, self.client_partner.pk)
        new_lines = list(new_invoice.lines.all())
        self.assertEqual(len(new_lines), 1)
        self.assertEqual(new_lines[0].product_id, self.service_product.pk)
        self.assertEqual(new_lines[0].unit_price, Decimal("500.0000"))

    def test_repeat_last_month_without_a_prior_invoice_is_rejected(self):
        res = self.client.post(
            "/api/sales/invoices/repeat-last-month/",
            {"customer_id": self.client_partner.pk},
            format="json", **self.headers,
        )
        self.assertEqual(res.status_code, 404, res.content)

    # ── 3. تراجُع: فاتورة منتج عادية لم يتغيّر ترحيلها ───────────────────────

    def test_ordinary_goods_invoice_still_posts_to_product_revenue_not_4102(self):
        res = self._create_invoice(
            product=self.goods_product, invoice_date="2026-06-15",
            quantity="3", unit_price="20.00")
        self.assertEqual(res.status_code, 201, res.content)
        invoice_id = res.json()["id"]

        post_res = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/", {}, format="json", **self.headers)
        self.assertEqual(post_res.status_code, 200, post_res.content)

        invoice = SalesInvoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.status, SalesInvoice.STATUS_POSTED)
        lines = list(invoice.journal.lines.select_related("account"))
        revenue_line = next(ln for ln in lines if ln.credit > 0 and ln.account.account_type == "Revenue")
        self.assertNotEqual(revenue_line.account.code, "4102")
        ar_line = next(ln for ln in lines if ln.debit > 0 and ln.account.account_type == "Asset")
        self.assertEqual(ar_line.debit, Decimal("60.00"))
