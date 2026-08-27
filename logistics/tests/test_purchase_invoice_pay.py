"""T-APPAY — الدفع من داخل فاتورة الشراء: نقطة واحدة ذرّية.

مرآة `sales/tests/test_invoice_collect.py`. كان الدفع خطوتين في الواجهة: «رحّل»
ثم «افتح سند الصرف» — نداءان مستقلّان، فانقطاعُ الثاني يترك فاتورةً مرحّلة بلا
سند ومورّداً دائناً والمستخدمُ يظنّ أنه دفع. النقطة `pay/` تجمعهما في معاملة
واحدة، وتقبل ما يقبله نظيرها في البيع: نقد + شيكات + سلف المورّد المرحّلة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque
from accounting.services import create_fiscal_year, partner_posted_balance
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import purchase_invoice_payment_summary
from partners.models import Partner
from sales.models import SupplierPayment, SupplierPaymentAllocation
from tenants.models import Currency
from tenants.services import create_company


class PurchaseInvoicePayTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="appay", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الدفع الموحّد", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-P", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد الدفع", partner_type="Supplier",
            linked_account=cls.ap)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-P", name="الصندوق",
            account_type="Asset", is_active=True)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PAY-1", name_ar="منتج",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, *, payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT,
                 total="100.00"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.ils, invoice_date="2026-06-18",
            exchange_rate=Decimal("1"), grand_total=Decimal(total),
            payment_type=payment_type,
            cash_or_bank_account=(
                self.cash if payment_type == PurchaseInvoice.PAYMENT_TYPE_CASH else None
            ),
        )
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج",
            quantity=Decimal("1"), unit_price=Decimal(total),
            total_price=Decimal(total))
        return inv

    def _pay(self, inv, body):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/pay/",
            body, format="json", **self._auth())

    def test_post_and_pay_in_one_call_produces_one_voucher(self):
        """60 نقداً + 40 شيكاً على فاتورة 100 ⇒ سندٌ واحد وذمم المورد صفر."""
        inv = self._invoice("PINV-P-1")
        res = self._pay(inv, {
            "post_invoice": True,
            "cash": "60.00",
            "cash_account_id": self.cash.id,
            "cheques": [{
                "cheque_number": "CHQ-1", "amount": "40.00",
                "due_date": "2026-07-01", "bank_name": "بنك",
            }],
        })
        assert res.status_code == 200, res.content

        inv.refresh_from_db()
        assert inv.is_posted is True
        payments = SupplierPayment.objects.filter(purchase_invoice=inv)
        assert payments.count() == 1, "نقدٌ وشيكات في سندٍ واحد لا سندين"
        payment = payments.first()
        assert payment.is_posted is True
        assert payment.amount == Decimal("100.00")
        assert Cheque.objects.filter(supplier_payment=payment).count() == 1

        summary = purchase_invoice_payment_summary(PurchaseInvoice.objects.get(pk=inv.pk))
        assert summary["payment_status"] == "paid"
        assert summary["remaining_balance"] == Decimal("0.00")
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.partner.id)
        assert (credit - debit) == Decimal("0")

    def test_partial_payment_leaves_partially_paid(self):
        inv = self._invoice("PINV-P-2")
        res = self._pay(inv, {
            "post_invoice": True, "cash": "30.00", "cash_account_id": self.cash.id,
        })
        assert res.status_code == 200, res.content
        summary = purchase_invoice_payment_summary(PurchaseInvoice.objects.get(pk=inv.pk))
        assert summary["payment_status"] == "partially_paid"
        assert summary["amount_paid"] == Decimal("30.00")
        assert summary["remaining_balance"] == Decimal("70.00")

    def test_overpayment_stays_on_account_as_supplier_advance(self):
        """الفائض سلفةٌ للمورّد لا تسديدٌ لفاتورةٍ أكبر من قيمتها."""
        inv = self._invoice("PINV-P-3")
        res = self._pay(inv, {
            "post_invoice": True, "cash": "150.00", "cash_account_id": self.cash.id,
        })
        assert res.status_code == 200, res.content
        payment = SupplierPayment.objects.get(purchase_invoice=inv)
        allocated = SupplierPaymentAllocation.objects.filter(payment=payment).first()
        assert allocated.amount == Decimal("100.00"), "التوزيع مقصوصٌ على المتبقّي"
        assert payment.amount == Decimal("150.00")
        summary = purchase_invoice_payment_summary(PurchaseInvoice.objects.get(pk=inv.pk))
        assert summary["payment_status"] == "paid"

    def test_paying_from_a_supplier_advance_creates_no_new_journal(self):
        """سلفةٌ سابقة للمورّد تُطبَّق على الفاتورة ربطاً بلا قيد جديد."""
        advance = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.partner, payment_date="2026-06-17",
            amount=Decimal("40.00"), currency=self.ils, exchange_rate=Decimal("1"),
            cash_or_bank_account=self.cash, notes="سلفة للمورد")
        from sales.services import post_supplier_payment
        post_supplier_payment(advance, user=self.user)
        journals_before = SupplierPayment.objects.filter(is_posted=True).count()

        inv = self._invoice("PINV-P-4")
        res = self._pay(inv, {
            "post_invoice": True,
            "cash": "60.00",
            "cash_account_id": self.cash.id,
            "from_on_account": [{"payment_id": advance.pk, "amount": "40.00"}],
        })
        assert res.status_code == 200, res.content

        summary = purchase_invoice_payment_summary(PurchaseInvoice.objects.get(pk=inv.pk))
        assert summary["payment_status"] == "paid", summary
        assert SupplierPaymentAllocation.objects.filter(
            payment=advance, invoice=inv).count() == 1
        # السلفة سندٌ واحد كما كان — التطبيق ربطٌ لا سندٌ جديد.
        assert SupplierPayment.objects.filter(is_posted=True).count() == journals_before + 1

    def test_cash_invoice_is_settled_once_not_twice(self):
        """التسوية التلقائية تُكبَت حين يتولّاها الدفع الصريح — سندٌ واحد."""
        inv = self._invoice(
            "PINV-P-5", payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH)
        res = self._pay(inv, {
            "post_invoice": True, "cash": "100.00", "cash_account_id": self.cash.id,
        })
        assert res.status_code == 200, res.content
        assert SupplierPayment.objects.filter(purchase_invoice=inv).count() == 1
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.partner.id)
        assert (credit - debit) == Decimal("0")

    def test_cash_invoice_underpayment_is_refused_entirely(self):
        """نقصٌ بعد نقدٍ مذكور على فاتورة نقدية ⇒ يرتدّ كلّ شيء."""
        inv = self._invoice(
            "PINV-P-6", payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH)
        res = self._pay(inv, {
            "post_invoice": True, "cash": "40.00", "cash_account_id": self.cash.id,
        })
        assert res.status_code == 400, res.content
        inv.refresh_from_db()
        assert inv.is_posted is False, "التراجع كامل — لا فاتورة مرحّلة بلا دفعها"
        assert SupplierPayment.objects.filter(purchase_invoice=inv).count() == 0

    def test_bad_cheque_rolls_back_the_posting_too(self):
        """شيكٌ بلا تاريخ استحقاق يُرفض — ولا تبقى الفاتورة مرحّلة بلا سند."""
        inv = self._invoice("PINV-P-7")
        res = self._pay(inv, {
            "post_invoice": True,
            "cheques": [{"cheque_number": "CHQ-X", "amount": "100.00"}],
        })
        assert res.status_code == 400, res.content
        inv.refresh_from_db()
        assert inv.is_posted is False
        assert SupplierPayment.objects.filter(purchase_invoice=inv).count() == 0

    def test_paying_a_draft_without_post_consent_is_refused(self):
        inv = self._invoice("PINV-P-8")
        res = self._pay(inv, {"cash": "100.00", "cash_account_id": self.cash.id})
        assert res.status_code == 400, res.content
        inv.refresh_from_db()
        assert inv.is_posted is False

    def test_return_invoice_cannot_be_paid(self):
        """مرجع الشراء يخفّض الذمم بحكم تعريفه — لا يُدفع."""
        inv = self._invoice("PINV-P-9")
        PurchaseInvoice.objects.filter(pk=inv.pk).update(is_return=True)
        inv.refresh_from_db()
        res = self._pay(inv, {
            "post_invoice": True, "cash": "10.00", "cash_account_id": self.cash.id,
        })
        assert res.status_code == 400, res.content
