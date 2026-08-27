"""كشف الحساب — «تفاصيل الحركة»: سطور فاتورة المبيعات يجب أن تحمل اسم المنتج كي
تُعرض بنودها المُباعة في نافذة التفاصيل (بلا نداء إضافي لحلّ الأسماء بالواجهة).
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.serializers import SalesInvoiceSerializer
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="stmtdet", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة التفاصيل", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-D", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="DET-1", name_ar="إطار ميشلان", quantity_on_hand=10, avg_cost=50)
    return tenant, customer, product


def test_sales_invoice_line_exposes_product_name(env):
    tenant, customer, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="DET-INV-1", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("2"), unit_price=Decimal("75"))

    data = SalesInvoiceSerializer(inv).data
    assert data["lines"][0]["product_name"] == "إطار ميشلان"


class SalesInvoiceDetailQueryCountTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="salesdetailperf", password="x")
        cls.tenant = create_company("شركة أداء تفاصيل البيع", cls.owner)
        cls.currency, _ = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل أداء", partner_type="Customer",
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="DETAIL-PERF-1",
            customer=cls.customer, currency=cls.currency, invoice_date="2026-07-01",
        )
        cls.products = [
            Product.objects.create(
                tenant=cls.tenant, sku=f"DETAIL-P-{i}", name_ar=f"منتج {i}",
            )
            for i in range(6)
        ]

    def _add_lines(self, start, stop):
        for i in range(start, stop):
            SalesInvoiceLine.objects.create(
                tenant=self.tenant, invoice=self.invoice, product=self.products[i],
                quantity=Decimal("1"), unit_price=Decimal("10"),
            )

    def _detail_query_count(self):
        self.client.force_authenticate(user=self.owner)
        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(
                f"/api/sales/invoices/{self.invoice.id}/",
                HTTP_X_TENANT_ID=str(self.tenant.TenantID),
            )
            assert res.status_code == 200, res.content[:300]
        return len(ctx.captured_queries)

    def test_product_name_query_count_is_constant_as_lines_grow(self):
        self._add_lines(0, 2)
        q_two = self._detail_query_count()
        self._add_lines(2, 6)
        q_six = self._detail_query_count()
        assert q_six == q_two, (
            f"N+1 in invoice lines: {q_two} queries for 2 lines, "
            f"{q_six} for 6 lines"
        )
