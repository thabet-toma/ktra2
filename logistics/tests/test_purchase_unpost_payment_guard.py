"""T-APINT — إلغاء ترحيل فاتورة الشراء لا يترك سند صرفٍ بلا مقابل.

الجذر المُصلَح: `unpost` كان يحذف قيود الفاتورة وحدها (PURCHASE_INVOICE/GRN/
RECEIPT) ولا يرى سندات الصرف إطلاقاً — فيبقى قيد السند **يدين ذمم المورد بلا
مقابل**: رصيدٌ وهميّ لصالح الشركة عند مورّد لم يُدفع له شيء زائد. وأسوأ حالاته
الفاتورة النقدية: الترحيل نفسه ينشئ سند تسوية ويُرحّله (`_auto_settle_cash_purchase`)
ولا شيء كان يحرّره.

مرآة `sales/tests/test_ar_integrity.py` على جانب المورّد.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.services import create_fiscal_year, partner_posted_balance
from accounting.models import Account
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class PurchaseUnpostPaymentGuardTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="apint", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة حارس الصرف", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-G", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد الحارس", partner_type="Supplier",
            linked_account=cls.ap)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-G", name="الصندوق",
            account_type="Asset", is_active=True)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="APG-1", name_ar="صنف",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, *, payment_type, total="1000.00"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.ils, invoice_date="2026-06-15",
            exchange_rate=Decimal("1"), grand_total=Decimal(total),
            payment_type=payment_type,
            cash_or_bank_account=(
                self.cash if payment_type == PurchaseInvoice.PAYMENT_TYPE_CASH else None
            ),
        )
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف",
            quantity=Decimal("1"), unit_price=Decimal(total),
            total_price=Decimal(total))
        return inv

    def _post(self, inv):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content
        inv.refresh_from_db()
        return res

    def test_unpost_blocked_when_posted_supplier_payment_exists(self):
        """سند صرف مرحّل على الفاتورة يمنع إلغاء ترحيلها — والرسالة تسمّيه."""
        inv = self._invoice("PINV-G-1", payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        self._post(inv)

        created = self.client.post(
            "/api/logistics/supplier-payments/",
            {
                "partner": self.partner.id,
                "purchase_invoice": inv.id,
                "payment_date": "2026-06-15",
                "amount": "400.00",
                "currency": self.ils.CurrencyID,
                "exchange_rate": "1",
                "cash_or_bank_account": self.cash.id,
            },
            format="json", **self._auth(),
        )
        assert created.status_code == 201, created.content
        payment_id = created.json()["id"]
        assert created.json()["is_posted"] is True

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/",
            {}, format="json", **self._auth())
        assert res.status_code == 400, res.content
        assert f"#{payment_id}" in res.json()["error"], res.json()

        # ولم يُمَسّ شيء: الفاتورة ما زالت مرحّلة والسند كما هو.
        inv.refresh_from_db()
        assert inv.is_posted is True
        assert SupplierPayment.objects.get(pk=payment_id).is_posted is True

    def test_unpost_allowed_after_payment_unposted(self):
        """المخرج الذي تُحيل إليه الرسالة يعمل فعلاً — لا طريق مسدود."""
        inv = self._invoice("PINV-G-2", payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        self._post(inv)
        created = self.client.post(
            "/api/logistics/supplier-payments/",
            {
                "partner": self.partner.id, "purchase_invoice": inv.id,
                "payment_date": "2026-06-15", "amount": "400.00",
                "currency": self.ils.CurrencyID, "exchange_rate": "1",
                "cash_or_bank_account": self.cash.id,
            },
            format="json", **self._auth())
        payment_id = created.json()["id"]

        undo = self.client.post(
            f"/api/logistics/supplier-payments/{payment_id}/unpost/",
            {}, format="json", **self._auth())
        assert undo.status_code == 200, undo.content

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/",
            {}, format="json", **self._auth())
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        assert inv.is_posted is False

    def test_cash_invoice_unpost_releases_auto_settlement(self):
        """الفاتورة النقدية: سندُها التلقائي من إنتاج الترحيل ⇒ يُحرَّر معه،
        ورصيد المورد يعود لما كان قبل الترحيل تماماً (صفر ÷ صفر)."""
        inv = self._invoice("PINV-G-3", payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH)
        self._post(inv)

        auto = SupplierPayment.objects.filter(auto_settled_invoice=inv)
        assert auto.count() == 1, "الترحيل ينشئ سند تسوية واحداً"
        assert auto.first().is_posted is True

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/",
            {}, format="json", **self._auth())
        assert res.status_code == 200, res.content

        inv.refresh_from_db()
        assert inv.is_posted is False
        assert SupplierPayment.objects.filter(purchase_invoice=inv).count() == 0, \
            "سند التسوية التلقائي يُحذف مع قيده — لا يبقى مديناً للذمم بلا مقابل"
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.partner.id)
        assert (debit, credit) == (Decimal("0"), Decimal("0")), \
            f"رصيد المورد يجب أن يعود صفراً — وجد {debit}/{credit}"

    def test_cash_invoice_repost_does_not_duplicate_settlement(self):
        """إعادة الترحيل تُنشئ سنداً واحداً لا سندين — التحرير لا التعليق."""
        inv = self._invoice("PINV-G-4", payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH)
        self._post(inv)
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/",
            {}, format="json", **self._auth())
        assert res.status_code == 200, res.content
        self._post(inv)

        assert SupplierPayment.objects.filter(purchase_invoice=inv).count() == 1
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.partner.id)
        assert (credit - debit) == Decimal("0"), \
            "بعد إعادة الترحيل يبقى الشراء النقدي مسدَّداً بلا ازدواج"
