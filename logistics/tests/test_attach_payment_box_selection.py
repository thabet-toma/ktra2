"""T-CASHBOX M1 — الحارس: الصندوق الذي اختاره المستخدم هو الذي يُدائَن.

كانت الأسبقية `invoice.cash_or_bank_account_id or invoice.attached_cash_account_id`،
ورأسُ الفاتورة تملؤه الواجهة تلقائياً بأوّل حساب نقدي في الشجرة (= صندوق
الشيقل، لأنه الأقلّ كوداً). فالمستخدم يختار صندوق الدولار في لوحة الدفع
ويُدائَن صندوق الشيقل — بلا خطأ ولا تحذير. لا اختبار كان يحرس هذا.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from accounting.services import create_cash_box, create_fiscal_year
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class AttachPaymentBoxSelectionTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="boxsel", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة اختيار الصندوق", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-B", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد الصناديق", partner_type="Supplier",
            linked_account=cls.ap)
        # صندوق الشيقل أوّلاً كي يكون هو ما تلتقطه الواجهة القديمة تلقائياً.
        cls.shekel_box = create_cash_box(
            tenant=cls.tenant, name="صندوق الشيقل", currency_code="ILS",
            is_default=True, user=cls.user)
        cls.dollar_box = create_cash_box(
            tenant=cls.tenant, name="صندوق الدولار", currency_code="USD", user=cls.user)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="BOX-1", name_ar="منتج",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, *, header_account=None, total="100.00"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.ils, invoice_date="2026-06-18",
            exchange_rate=Decimal("1"), grand_total=Decimal(total),
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT,
            cash_or_bank_account=header_account,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج",
            quantity=Decimal("1"), unit_price=Decimal(total),
            total_price=Decimal(total))
        return inv

    def _attach(self, inv, account, amount="40"):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/attach-payment/",
            {"cash_amount": amount, "cash_account_id": account.pk},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        return res

    def _post(self, inv):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())

    def _cash_line_accounts(self, payment):
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="SUPPLIER_PAYMENT",
            reference_id=payment.pk)
        return {line.account_id for line in jh.lines.filter(credit__gt=0)}

    def test_selected_box_wins_over_autofilled_header(self):
        """الحارس المركزي: الرأس مملوء بصندوق الشيقل، والمستخدم اختار الدولار."""
        inv = self._invoice("BOXSEL-1", header_account=self.shekel_box.account)
        self._attach(inv, self.dollar_box.account)

        res = self._post(inv)
        self.assertEqual(res.status_code, 201, res.content)

        payment = SupplierPayment.objects.get(auto_settled_invoice=inv)
        self.assertEqual(payment.cash_or_bank_account_id, self.dollar_box.account_id)
        credited = self._cash_line_accounts(payment)
        self.assertIn(self.dollar_box.account_id, credited)
        self.assertNotIn(self.shekel_box.account_id, credited)

    def test_header_still_used_when_nothing_was_attached_explicitly(self):
        """بلا اختيار في اللوحة يبقى الرأس مصدراً — الإصلاح لم يُلغِ الرأس."""
        inv = self._invoice("BOXSEL-2", header_account=self.dollar_box.account)
        inv.attached_cash_amount = Decimal("40.00")
        inv.attached_cash_account = None
        inv.save(update_fields=["attached_cash_amount", "attached_cash_account"])

        res = self._post(inv)
        self.assertEqual(res.status_code, 201, res.content)

        payment = SupplierPayment.objects.get(auto_settled_invoice=inv)
        self.assertEqual(payment.cash_or_bank_account_id, self.dollar_box.account_id)

    def test_falls_back_to_company_default_box_not_generic_cash(self):
        """بلا رأس ولا اختيار: افتراضي الشركة صندوقٌ حقيقي لا «1101 النقدية»."""
        inv = self._invoice("BOXSEL-3", header_account=None)
        inv.attached_cash_amount = Decimal("40.00")
        inv.save(update_fields=["attached_cash_amount"])

        res = self._post(inv)
        self.assertEqual(res.status_code, 201, res.content)

        payment = SupplierPayment.objects.get(auto_settled_invoice=inv)
        self.assertEqual(payment.cash_or_bank_account_id, self.shekel_box.account_id)
        generic = Account.objects.filter(tenant=self.tenant, code="1101").first()
        if generic:
            self.assertNotEqual(payment.cash_or_bank_account_id, generic.pk)
