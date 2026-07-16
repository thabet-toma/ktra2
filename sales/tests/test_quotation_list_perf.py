"""قائمة عروض السعر خفيفة؛ البنود تُجلب من detail عند التوسيع/التعديل فقط."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from inventory.models import Product
from partners.models import Partner
from sales.models import SalesQuotation, SalesQuotationLine
from tenants.models import Currency
from tenants.services import create_company


class SalesQuotationListPerformanceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="quotation_list_perf", password="x")
        cls.currency, _ = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        cls.tenant = create_company("شركة أداء عروض السعر", cls.owner)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل عروض", partner_type="Customer",
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="QUOTE-LIST-P", name_ar="صنف عرض",
        )
        for i in range(6):
            quotation = SalesQuotation.objects.create(
                tenant=cls.tenant, quotation_number=f"Q-PERF-{i}",
                customer=cls.customer, currency=cls.currency,
                quotation_date="2026-07-01", grand_total=Decimal("10"),
            )
            SalesQuotationLine.objects.create(
                tenant=cls.tenant, quotation=quotation, product=cls.product,
                quantity=Decimal("1"), unit_price=Decimal("10"),
                line_total=Decimal("10"),
            )

    def _list(self, page_size):
        self.client.force_authenticate(user=self.owner)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                f"/api/sales/quotations/?page=1&page_size={page_size}",
                HTTP_X_TENANT_ID=str(self.tenant.TenantID),
            )
            assert response.status_code == 200, response.content[:300]
        return response.json()["results"], ctx.captured_queries

    def test_list_omits_lines_and_never_queries_line_table(self):
        two_rows, q_two = self._list(2)
        six_rows, q_six = self._list(6)

        assert len(two_rows) == 2
        assert len(six_rows) == 6
        assert all("lines" not in row and "notes" not in row for row in six_rows)
        assert len(q_six) == len(q_two)
        assert not any(
            "sales_module_quotation_lines" in query["sql"].lower()
            for query in q_six
        )

        detail = self.client.get(
            f"/api/sales/quotations/{six_rows[0]['id']}/",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )
        assert detail.status_code == 200, detail.content[:300]
        assert len(detail.json()["lines"]) == 1
        assert detail.json()["lines"][0]["product_name"] == "صنف عرض"
