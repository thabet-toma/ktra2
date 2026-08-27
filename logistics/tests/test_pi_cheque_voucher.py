"""T-APPAID — النقطة القديمة `payment-voucher` صارت غلافاً يُنتج سنداً حقيقياً.

**ما كانت تفعله** (P-H-1): تكتب `attached_cash_amount` على الفاتورة وتنشئ شيكات
`Draft`، ولا يقرأ الترحيلُ أياً منهما — مالٌ يُسجَّل في الشاشة بلا أثرٍ في
الدفاتر، ثم يُحتسب «مدفوعاً» في ملخّص الفاتورة. مستندٌ ماليّ الشكل عديمُ الأثر
أسوأ من غيابه، لأن المستخدم يبني عليه.

صارت تمرّ من `pay_purchase_invoice` — نفس منسّق زرّ «تسجيل دفعة» — فتُرحّل
الفاتورة وتُخرج سند صرف واحداً مرحّلاً بنقده وشيكاته. هذا الملف يقيس العقد
الجديد ويحرس ألّا يعود القديم.
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
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class PiPaymentVoucherEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pichq", password="x")
        cls.currency = Currency.objects.create(
            Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        cls.tenant = create_company("شركة السند القديم", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-V", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.cash_account = Account.objects.create(
            tenant=cls.tenant, code="1110-V", name="صندوق نقدي",
            account_type="Asset", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد الشيكات", partner_type="Supplier",
            linked_account=cls.ap)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="CHQ-1", name_ar="منتج",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, total="10000.00"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.currency, invoice_date="2026-05-01",
            exchange_rate=Decimal("1"), grand_total=Decimal(total))
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج",
            quantity=Decimal("1"), unit_price=Decimal(total),
            total_price=Decimal(total))
        return inv

    def test_voucher_endpoint_now_posts_a_real_supplier_payment(self):
        inv = self._invoice("INV-CHQ-001")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/payment-voucher/",
            {
                "cash_amount": "2000",
                "cash_account_id": self.cash_account.id,
                "cheques": [
                    {"cheque_number": "CHQ-001", "amount": "3000",
                     "bank_name": "بنك أ", "due_date": "2026-09-01"},
                    {"cheque_number": "CHQ-002", "amount": "5000",
                     "bank_name": "بنك ب", "due_date": "2026-10-01"},
                ],
            },
            format="json", **self._auth())
        assert res.status_code == 200, res.content

        inv.refresh_from_db()
        assert inv.is_posted is True, "الغلاف يُرحّل الفاتورة كما يَعِد اسمه"

        payments = SupplierPayment.objects.filter(purchase_invoice=inv)
        assert payments.count() == 1, "نقدٌ وشيكات في سندٍ واحد"
        payment = payments.first()
        assert payment.is_posted is True
        assert payment.amount == Decimal("10000.00")

        cheques = Cheque.objects.filter(supplier_payment=payment)
        assert cheques.count() == 2
        assert sum((c.amount for c in cheques), Decimal("0")) == Decimal("8000.00")

        # وأثرُه في الدفاتر لا في الشاشة وحدها.
        summary = purchase_invoice_payment_summary(
            PurchaseInvoice.objects.get(pk=inv.pk))
        assert summary["payment_status"] == "paid"
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.partner.id)
        assert (credit - debit) == Decimal("0")

    def test_exceeding_the_total_leaves_the_surplus_on_account(self):
        """التجاوز لم يعد رفضاً بل سلفةً للمورّد — نفس سياسة جانب البيع."""
        inv = self._invoice("INV-CHQ-002", "1000.00")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/payment-voucher/",
            {"cash_amount": "1500", "cash_account_id": self.cash_account.id},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        payment = SupplierPayment.objects.get(purchase_invoice=inv)
        assert payment.amount == Decimal("1500.00")
        assert payment.allocations.first().amount == Decimal("1000.00")

    def test_attached_cash_amount_is_no_longer_writable(self):
        """العمود القديم لا يُكتب من الـAPI — كان يُسجّل مالاً بلا قيد."""
        inv = self._invoice("INV-CHQ-003", "1000.00")
        res = self.client.patch(
            f"/api/logistics/purchase-invoices/{inv.pk}/",
            {"attached_cash_amount": "900"}, format="json", **self._auth())
        assert res.status_code in (200, 400), res.content
        inv.refresh_from_db()
        assert inv.attached_cash_amount == Decimal("0")
