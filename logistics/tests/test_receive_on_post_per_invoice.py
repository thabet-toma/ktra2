"""T-RECVOPT — «استلام البضاعة مع الترحيل» خياراً لكل فاتورة لا للشركة كلّها.

`PurchaseSettings.receive_on_post` كان الحاكم الوحيد، فمورّدٌ واحد يوصّل على
دفعات يُجبر المستخدم على إطفائه **لكل الموردين** فتُفقد الراحة في الحالة
الغالبة (البضاعة تصل مع فاتورتها).

الخيار لحظةُ ترحيل لا حقلٌ محفوظ: ما بعد الترحيل تقوله `receipt_status`
والإرساليات نفسها. ويُثبت هنا أنّه يتقدّم على الإعداد **في الاتجاهين**، وأن
إغفاله يُبقي السلوك القديم حرفياً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class ReceiveOnPostPerInvoiceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="recvopt", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الخيار", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورّد الدفعات", partner_type="Supplier",
            linked_account=Account.objects.get(tenant=cls.tenant, code="2101"))

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        self.product = Product.objects.create(
            tenant=self.tenant, sku=f"OPT-{Product.objects.count() + 1}",
            name_ar="منتج", quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _set_company_default(self, value):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = value
        ps.save(update_fields=["receive_on_post"])

    def _make_invoice(self, qty="10", price="100"):
        grand = Decimal(qty) * Decimal(price)
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"INV-{PurchaseInvoice.objects.count() + 1:04d}",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=grand)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج",
            quantity=Decimal(qty), unit_price=Decimal(price), total_price=grand)
        return inv

    def _post(self, invoice, body=None):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            body if body is not None else {}, format="json", **self.headers)
        assert res.status_code == 201, res.content
        invoice.refresh_from_db()
        self.product.refresh_from_db()
        return res.json()

    def test_invoice_can_opt_out_while_company_default_is_on(self):
        """مورّد الدفعات: هذه الفاتورة وحدها لا تُستلَم — والإعداد العام باقٍ."""
        self._set_company_default(True)
        inv = self._make_invoice()

        self._post(inv, {"receive_on_post": False})

        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
        assert self.product.quantity_on_hand == Decimal("0.0000")
        # والإعداد العام لم يُمسّ — بقية الموردين على راحتهم.
        assert get_or_create_purchase_settings(self.tenant).receive_on_post is True

    def test_invoice_can_opt_in_while_company_default_is_off(self):
        """والعكس: شركةٌ أطفأته عموماً، وفاتورةٌ وصلت بضاعتها كاملةً معها."""
        self._set_company_default(False)
        inv = self._make_invoice()

        self._post(inv, {"receive_on_post": True})

        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
        assert self.product.quantity_on_hand == Decimal("10.0000")

    def test_omitting_the_choice_keeps_the_company_setting(self):
        """النداء القديم (بلا الحقل) يبقى على سلوكه حرفياً — لا تغيير صامت."""
        self._set_company_default(False)
        inv = self._make_invoice()
        self._post(inv)
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT

        self._set_company_default(True)
        inv2 = self._make_invoice()
        self._post(inv2)
        assert inv2.receipt_status == PurchaseInvoice.RECEIPT_FULL

    def test_string_false_is_honoured_not_read_as_truthy(self):
        """`"false"` نصّاً من عميلٍ لا يُرسل JSON منطقياً — لا يُقرأ صحيحاً."""
        self._set_company_default(True)
        inv = self._make_invoice()
        self._post(inv, {"receive_on_post": "false"})
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
