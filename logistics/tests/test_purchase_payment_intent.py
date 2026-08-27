"""T-INTENT — نيّة الدفع على مسودة فاتورة الشراء.

مرآة `sales/tests/test_invoice_collect.py` في جزئه الخاص بالنيّة. المسودة تحمل
دفعةً منويّة (نقد + شيكات) بلا أثرٍ في الدفاتر إطلاقاً، فإذا رُحّلت الفاتورة
تجسّدت الدفعةُ **سند صرفٍ واحداً**. إلغاء الترحيل يعيد الحال كما كان: السند
يُحرَّر والشيكات تعود مسودةً والنيّة تبقى — فإعادة الترحيل لا تُنتج سنداً ثانياً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, JournalHeader
from accounting.services import create_fiscal_year, partner_posted_balance
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import (
    annotate_purchase_invoice_payment_summary,
    attach_purchase_payment_voucher,
    purchase_invoice_payment_summary,
)
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class PurchasePaymentIntentTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pintent", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة نيّة الشراء", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-I", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد النيّة", partner_type="Supplier",
            linked_account=cls.ap)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-I", name="الصندوق",
            account_type="Asset", is_active=True)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="INT-1", name_ar="منتج",
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

    def _post(self, inv):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())

    def _unpost(self, inv):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/",
            {}, format="json", **self._auth())

    # ── النيّة لا تلمس الدفاتر ──────────────────────────────────────────────

    def test_attach_leaves_books_untouched(self):
        """الدفعة المرفقة بمسودة: لا قيد ولا سند ولا أثر على رصيد المورد."""
        inv = self._invoice("INT-1")
        balance_before = partner_posted_balance(self.tenant.TenantID, self.partner.pk)

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/attach-payment/",
            {"cash_amount": "40", "cash_account_id": self.cash.pk,
             "cheques": [{"cheque_number": "PC-1", "amount": "25",
                          "due_date": "2026-09-01"}]},
            format="json", **self._auth(),
        )
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        assert inv.attached_cash_amount == Decimal("40.00")
        assert inv.attached_cash_account_id == self.cash.pk
        assert SupplierPayment.objects.filter(partner=self.partner).count() == 0
        assert JournalHeader.objects.filter(tenant=self.tenant).count() == 0
        assert partner_posted_balance(self.tenant.TenantID, self.partner.pk) == balance_before

        summary = purchase_invoice_payment_summary(inv)
        assert summary["pending_payment_total"] == Decimal("65.00")
        assert summary["amount_paid"] == Decimal("0.00")
        assert summary["remaining_balance"] == Decimal("100.00")

    def test_intent_may_not_exceed_invoice_total(self):
        """النيّة وعدٌ على هذه الفاتورة وحدها — الفائض شأن `pay/`."""
        inv = self._invoice("INT-2")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/attach-payment/",
            {"cash_amount": "5000", "cash_account_id": self.cash.pk},
            format="json", **self._auth(),
        )
        assert res.status_code == 400, res.content

    def test_attach_replaces_previous_intent(self):
        """بدلالة الاستبدال: النداء الفارغ يمسح النيّة كلّها."""
        inv = self._invoice("INT-3")
        attach_purchase_payment_voucher(
            inv, cash_amount=30, cash_account_id=self.cash.pk,
            cheques=[{"cheque_number": "PC-3", "amount": "20"}],
        )
        assert Cheque.objects.filter(purchase_invoice=inv, status="Draft").count() == 1

        attach_purchase_payment_voucher(inv, cash_amount=0, cheques=[])
        inv.refresh_from_db()
        assert inv.attached_cash_amount == Decimal("0.00")
        assert inv.attached_cash_account_id is None
        assert Cheque.objects.filter(purchase_invoice=inv, status="Draft").count() == 0

    # ── التجسّد عند الترحيل ─────────────────────────────────────────────────

    def test_intent_materializes_into_one_voucher_on_post(self):
        """الترحيل يكنس النقد والشيكات معاً في سند صرف واحد."""
        inv = self._invoice("INT-4")
        attach_purchase_payment_voucher(
            inv, cash_amount=40, cash_account_id=self.cash.pk,
            cheques=[{"cheque_number": "PC-4", "amount": "25",
                      "due_date": "2026-09-01"}],
        )
        res = self._post(inv)
        assert res.status_code in (200, 201), res.content
        inv.refresh_from_db()

        payments = SupplierPayment.objects.filter(auto_settled_invoice=inv)
        assert payments.count() == 1, "سند واحد لا أكثر"
        assert payments.first().amount == Decimal("65.00")
        summary = purchase_invoice_payment_summary(inv)
        assert summary["amount_paid"] == Decimal("65.00")
        assert summary["remaining_balance"] == Decimal("35.00")
        # النيّة سجلٌّ دائم يبقى بعد التجسّد.
        assert inv.attached_cash_amount == Decimal("40.00")
        # الفاتورة مرحّلة ⇒ لا نيّة معلّقة تُعرَض.
        assert summary["pending_payment_total"] == Decimal("0.00")

    def test_cash_invoice_intent_does_not_double_settle(self):
        """الشراء النقدي: النيّة ثم التسوية التلقائية = إجمالي الفاتورة لا ضِعفها.

        التسوية التلقائية كانت تُسوّي كامل المبلغ بلا نظرٍ لما سُوّي قبلها، فلو
        سبقتها نيّةٌ خرج سندان مجموعهما يتجاوز الفاتورة ويجعل المورد مديناً.
        """
        inv = self._invoice("INT-5", payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH)
        attach_purchase_payment_voucher(
            inv, cash_amount=40, cash_account_id=self.cash.pk)
        res = self._post(inv)
        assert res.status_code in (200, 201), res.content
        inv.refresh_from_db()

        summary = purchase_invoice_payment_summary(inv)
        assert summary["amount_paid"] == Decimal("100.00")
        assert summary["remaining_balance"] == Decimal("0.00")
        total_vouchers = sum(
            (Decimal(str(p.amount)) for p in
             SupplierPayment.objects.filter(partner=self.partner, is_posted=True)),
            Decimal("0"),
        )
        assert total_vouchers == Decimal("100.00"), "لا يجوز أن يتجاوز المدفوع الفاتورة"

    # ── إلغاء الترحيل وإعادته ───────────────────────────────────────────────

    def test_unpost_restores_intent_and_repost_does_not_duplicate(self):
        """إلغاء الترحيل يحرّر السند ويعيد الشيك مسودةً وتبقى النيّة كما هي."""
        inv = self._invoice("INT-6")
        attach_purchase_payment_voucher(
            inv, cash_amount=40, cash_account_id=self.cash.pk,
            cheques=[{"cheque_number": "PC-6", "amount": "25",
                      "due_date": "2026-09-01"}],
        )
        assert self._post(inv).status_code in (200, 201)
        _u = self._unpost(inv)
        assert _u.status_code in (200, 201), _u.content
        inv.refresh_from_db()

        assert SupplierPayment.objects.filter(auto_settled_invoice=inv).count() == 0
        assert inv.attached_cash_amount == Decimal("40.00")
        cheque = Cheque.objects.get(purchase_invoice=inv)
        assert cheque.status == "Draft", "الشيك يعود مسودةً وإلا ضاعت تسويته"
        assert cheque.supplier_payment_id is None
        assert purchase_invoice_payment_summary(inv)["pending_payment_total"] == Decimal("65.00")

        assert self._post(inv).status_code in (200, 201)
        inv.refresh_from_db()
        inv._payment_summary_cache = None  # الملخّص يُخزَّن على النسخة
        assert SupplierPayment.objects.filter(auto_settled_invoice=inv).count() == 1
        assert purchase_invoice_payment_summary(inv)["amount_paid"] == Decimal("65.00")

    def test_pay_with_post_still_materializes_pending_intent(self):
        """نيّةٌ محفوظة + دفع-مع-ترحيل في نداء واحد: لا مال يعلق ولا يزدوج.

        علم الكبت كان يُسكِت كنس النيّة مع التسوية التلقائية معاً، فتعلق
        الدفعة المسجَّلة على فاتورة صارت مرحّلة. الكنس صار خارج العلم، وسقفه
        يمنع الازدواج: سند `pay/` يحسب متبقّيه بعده.
        """
        inv = self._invoice("INT-MIX")
        attach_purchase_payment_voucher(
            inv, cash_amount=30, cash_account_id=self.cash.pk)
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/pay/",
            {"cash": "70", "cash_account_id": self.cash.pk, "post_invoice": True},
            format="json", **self._auth(),
        )
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        inv._payment_summary_cache = None
        summary = purchase_invoice_payment_summary(inv)
        assert summary["amount_paid"] == Decimal("100.00")
        assert summary["remaining_balance"] == Decimal("0.00")
        total_vouchers = sum(
            (Decimal(str(p.amount)) for p in
             SupplierPayment.objects.filter(partner=self.partner, is_posted=True)),
            Decimal("0"),
        )
        assert total_vouchers == Decimal("100.00"), "لا عالق ولا مزدوج"

    def test_deleting_draft_removes_intent_cheques(self):
        """حذف المسودة يحذف شيكات نيّتها — الرابط SET_NULL كان يتركها يتيمة."""
        inv = self._invoice("INT-DEL")
        attach_purchase_payment_voucher(
            inv, cheques=[{"cheque_number": "PC-DEL", "amount": "20"}],
        )
        cheque_id = Cheque.objects.get(purchase_invoice=inv).pk
        res = self.client.delete(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth(),
        )
        assert res.status_code in (200, 204), res.content
        assert not Cheque.objects.filter(pk=cheque_id).exists()

    # ── الزوج الواجب اتفاقه ─────────────────────────────────────────────────

    def test_python_summary_and_sql_annotate_agree(self):
        """قاعدة «المدفوع/المعلّق» مكتوبة مرّتين — ولا يجوز أن تفترقا."""
        drafted = self._invoice("INT-7")
        attach_purchase_payment_voucher(
            drafted, cash_amount=30, cash_account_id=self.cash.pk,
            cheques=[{"cheque_number": "PC-7", "amount": "10"}],
        )
        posted = self._invoice("INT-8")
        attach_purchase_payment_voucher(
            posted, cash_amount=60, cash_account_id=self.cash.pk)
        assert self._post(posted).status_code in (200, 201)
        bare = self._invoice("INT-9")

        rows = {
            row.pk: row for row in annotate_purchase_invoice_payment_summary(
                PurchaseInvoice.objects.filter(tenant=self.tenant)
            )
        }
        for inv in (drafted, posted, bare):
            inv.refresh_from_db()
            inv._payment_summary_cache = None
            py = purchase_invoice_payment_summary(inv)
            sql = rows[inv.pk]
            assert Decimal(str(sql.list_amount_paid)) == py["amount_paid"], inv.invoice_number
            assert Decimal(str(sql.list_remaining_balance)) == py["remaining_balance"], inv.invoice_number
            assert sql.list_payment_status == py["payment_status"], inv.invoice_number
            assert Decimal(str(sql.list_pending_payment_total)) == py["pending_payment_total"], inv.invoice_number
