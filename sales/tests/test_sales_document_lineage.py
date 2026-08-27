"""نسب مستندات البيع (T-SLINEAGE): الفاتورة تقول من أين جاءت.

الطلبية كانت تعرض «محوّلة لفاتورة» بلا رقم الفاتورة ولا رابطها، والفاتورة كانت
صامتة عن الطلبية/العرض الذي أنتجها — فينقطع الطريق بين المستندين في الاتجاهين.
الروابط كانت موجودة في القاعدة (`SalesOrder.invoice` و`SalesQuotation.invoice`)
وغير مكشوفة للواجهة من جهة الفاتورة.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, FiscalPeriod
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesQuotation, SalesQuotationLine
from sales.services import convert_order_to_invoice, convert_quotation_to_order
from tenants.models import Currency, Tenant, UserCompanyMembership


class SalesDocumentLineageTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sale-lineage", password="x")
        cls.tenant = Tenant.objects.create(TenantID=171, CompanyName="Lineage Sales Co")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء",
            account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون النسب", partner_type="Customer",
            linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SLN-1", name_ar="منتج", quantity_on_hand=Decimal("20"),
            is_service=True)
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026", start_date="2026-01-01",
            end_date="2026-12-31", is_closed=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _quotation(self):
        quotation = SalesQuotation.objects.create(
            tenant=self.tenant,
            quotation_number=f"Q-L{SalesQuotation.objects.count() + 1}",
            customer=self.customer, quotation_date=date(2026, 7, 1),
            currency=self.currency, grand_total=Decimal("500"),
        )
        SalesQuotationLine.objects.create(
            tenant=self.tenant, quotation=quotation, product=self.product,
            quantity=Decimal("5"), unit_price=Decimal("100"),
        )
        return quotation

    def test_order_list_carries_the_invoice_number_and_id(self):
        order = convert_quotation_to_order(self._quotation(), user=self.user)
        invoice = convert_order_to_invoice(order, user=self.user)
        response = self.client.get("/api/sales/orders/")
        assert response.status_code == 200, response.content
        rows = response.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        row = next(r for r in rows if r["id"] == order.pk)
        assert row["invoice"] == invoice.pk
        assert row["invoice_number"] == invoice.invoice_number

    def test_invoice_names_the_order_it_came_from(self):
        order = convert_quotation_to_order(self._quotation(), user=self.user)
        invoice = convert_order_to_invoice(order, user=self.user)
        response = self.client.get(f"/api/sales/invoices/{invoice.pk}/")
        assert response.status_code == 200, response.content
        source = response.json()["source_document"]
        assert source["kind"] == "order"
        assert source["id"] == order.pk
        assert source["number"] == order.order_number
        # الطلبية نفسها وليدة عرض سعر — يُذكر الجدّ ليكتمل الطريق.
        assert source["origin_kind"] == "quotation"
        assert source["origin_id"] == order.quotation_id

    def test_invoice_names_the_quotation_when_converted_directly(self):
        quotation = self._quotation()
        response = self.client.post(
            f"/api/sales/quotations/{quotation.pk}/convert/",
            {"target": "invoice"}, format="json",
        )
        assert response.status_code in (200, 201), response.content
        quotation.refresh_from_db()
        source = self.client.get(
            f"/api/sales/invoices/{quotation.invoice_id}/"
        ).json()["source_document"]
        assert source["kind"] == "quotation"
        assert source["id"] == quotation.pk
        assert source["number"] == quotation.quotation_number
        assert source["origin_kind"] is None

    def test_invoice_without_a_source_reports_none(self):
        quotation = self._quotation()
        order = convert_quotation_to_order(quotation, user=self.user)
        invoice = convert_order_to_invoice(order, user=self.user)
        # فاتورة أخرى بلا مستند أب — نُنشئها بفصل الطلبية عنها.
        order.invoice = None
        order.save(update_fields=["invoice"])
        source = self.client.get(
            f"/api/sales/invoices/{invoice.pk}/").json()["source_document"]
        assert source is None
