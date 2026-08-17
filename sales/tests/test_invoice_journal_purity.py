"""T1 — قيد الفاتورة لا يُسوّي شيئاً: لا نقد، لا شيكات، ولا «مدفوع» بلا توزيع.

قبل هذا كانت الشيكات المرفقة بالفاتورة تُرحَّل **داخل قيدها** (مدين شيكات برسم
التحصيل / دائن ذمم) وتزيد `amount_paid` بلا صفّ `PaymentAllocation` واحد. أثر
ذلك مالياً:

- `amount_paid` يقول «دُفع 400» بينما مجموع توزيعات السندات المرحّلة صفر —
  فينكسر الثابت الذي تُشتقّ منه حالة الفاتورة وتُحرَس به الجباية المزدوجة.
- التحصيل لا يظهر كمستند مستقل في كشف حساب العميل ولا في شاشة السندات.

العقد الصحيح: قيد الفاتورة (Entry A) يدين الذمم بالكامل ويدائن الإيراد/الضريبة
فقط؛ وما وصل مع الفاتورة (شيكات + نقد البيع النقدي) يُحصَّل بسند قبض حقيقي
واحد مملوك للفاتورة (Entry B) — فيبقى `amount_paid == posted_allocations_total`.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalLine
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    CustomerPayment,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)
from sales.services import (
    attach_voucher_and_post,
    post_sales_invoice,
    posted_allocations_total,
)
from tenants.models import Currency, Tenant, UserCompanyMembership


class InvoiceJournalPurityTest(APITestCase):
    """الفاتورة المرحّلة بشيكات مرفقة عبر واجهة الإرفاق القديمة."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="purity", password="x")
        cls.tenant = Tenant.objects.create(TenantID=173, CompanyName="نقاء القيد")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق",
            account_type="Asset", is_active=True)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء",
            account_type="Asset", is_active=True)
        cls.uc = Account.objects.create(
            tenant=cls.tenant, code="1106", name="شيكات برسم التحصيل",
            account_type="Asset", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="4101", name="إيرادات",
            account_type="Revenue", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="2101", name="ضريبة",
            account_type="Liability", is_active=True)
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={
                "default_cheques_under_collection_account": cls.uc,
                "default_cash_account": cls.cash,
            },
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="زبون النقاء", partner_type="Customer",
            linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PURE-1", name_ar="خدمة", is_service=True)
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026", start_date="2026-01-01",
            end_date="2026-12-31", is_closed=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    # ── أدوات ────────────────────────────────────────────────────────────
    def _draft(self, number, total="1000", invoice_type=SalesInvoice.INVOICE_CREDIT):
        inv = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.partner,
            currency=self.currency, invoice_date="2026-07-01",
            invoice_type=invoice_type, stock_on_post=False,
            cash_or_bank_account=(
                self.cash if invoice_type == SalesInvoice.INVOICE_CASH else None
            ),
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=self.product,
            quantity=1, unit_price=Decimal(total))
        return inv

    def _invoice_journal_lines(self, invoice):
        return list(
            JournalLine.objects.filter(
                journal__reference_type="SALES_INVOICE",
                journal__reference_id=invoice.pk,
            )
        )

    # ── معيار النجاح الملزِم ─────────────────────────────────────────────
    def test_attached_cheques_leave_the_invoice_journal_pure(self):
        """قيد الفاتورة بلا سطر نقد ولا شيكات، و«المدفوع» مُغطّى بتوزيع."""
        inv = self._draft("PURE-CREDIT-1")
        attach_voucher_and_post(
            inv,
            cash_amount=0,
            cash_account_id=None,
            cheques=[{"cheque_number": "CHQ-PURE-1", "amount": "400",
                      "due_date": "2026-09-01"}],
            user=self.user,
        )
        inv.refresh_from_db()

        lines = self._invoice_journal_lines(inv)
        assert lines, "الفاتورة يجب أن تُرحَّل بقيد"
        # لا سطر مدين على شيكات برسم التحصيل ولا على الصندوق داخل قيد الفاتورة
        assert sum(
            l.debit for l in lines if l.account_id == self.uc.pk
        ) == Decimal("0"), "قيد الفاتورة لا يُسوّي الشيكات"
        assert sum(
            l.debit for l in lines if l.account_id == self.cash.pk
        ) == Decimal("0"), "قيد الفاتورة لا يُسوّي النقدية"
        # الذمم تُدين بكامل الإجمالي ولا تُسوَّى داخل القيد نفسه
        assert sum(l.debit for l in lines if l.account_id == self.ar.pk) == \
            inv.grand_total
        assert sum(l.credit for l in lines if l.account_id == self.ar.pk) == \
            Decimal("0")

        # «المدفوع» مساوٍ تماماً لمجموع توزيعات السندات المرحّلة — الثابت
        assert inv.amount_paid == posted_allocations_total(inv.pk)
        assert inv.amount_paid == Decimal("400.00")

    def test_attached_cheques_become_one_posted_voucher(self):
        """الشيك المرفق يصير سند قبض حقيقياً مرحّلاً ومرتبطاً بالفاتورة."""
        inv = self._draft("PURE-CREDIT-2")
        attach_voucher_and_post(
            inv,
            cheques=[{"cheque_number": "CHQ-PURE-2", "amount": "400",
                      "due_date": "2026-09-01"}],
            user=self.user,
        )
        inv.refresh_from_db()

        payments = list(CustomerPayment.objects.filter(auto_settled_invoice=inv))
        assert len(payments) == 1, "سند واحد لا أكثر"
        payment = payments[0]
        assert payment.is_posted
        assert payment.amount == Decimal("400.00")
        assert list(
            PaymentAllocation.objects.filter(payment=payment)
            .values_list("invoice_id", "amount")
        ) == [(inv.pk, Decimal("400.00"))]

        cheque = Cheque.objects.get(sales_invoice=inv)
        assert cheque.customer_payment_id == payment.pk, \
            "الشيك ينتقل إلى ملكية السند"
        assert cheque.status == "Under_Collection"

        # قيد السند هو الذي يحمل التسوية: مدين شيكات برسم التحصيل / دائن ذمم
        pay_lines = JournalLine.objects.filter(
            journal__reference_type="CUSTOMER_PAYMENT",
            journal__reference_id=payment.pk,
        )
        assert {
            (l.account_id, l.debit, l.credit) for l in pay_lines
        } == {
            (self.uc.pk, Decimal("400.00"), Decimal("0.00")),
            (self.ar.pk, Decimal("0.00"), Decimal("400.00")),
        }

    def test_cash_invoice_with_attached_cheques_settles_once(self):
        """بيع نقدي بشيك جزئي: سند واحد يقسم المدين بين الصندوق والشيكات."""
        inv = self._draft("PURE-CASH-1", invoice_type=SalesInvoice.INVOICE_CASH)
        attach_voucher_and_post(
            inv,
            cheques=[{"cheque_number": "CHQ-PURE-3", "amount": "400",
                      "due_date": "2026-09-01"}],
            user=self.user,
        )
        inv.refresh_from_db()

        payments = list(CustomerPayment.objects.filter(partner=self.partner))
        assert len(payments) == 1, "سند تحصيل واحد لا سندان"
        payment = payments[0]
        assert payment.amount == Decimal("1000.00")
        assert inv.amount_paid == Decimal("1000.00")
        assert inv.amount_paid == posted_allocations_total(inv.pk)

        pay_lines = JournalLine.objects.filter(
            journal__reference_type="CUSTOMER_PAYMENT",
            journal__reference_id=payment.pk,
        )
        assert {
            (l.account_id, l.debit, l.credit) for l in pay_lines
        } == {
            (self.cash.pk, Decimal("600.00"), Decimal("0.00")),
            (self.uc.pk, Decimal("400.00"), Decimal("0.00")),
            (self.ar.pk, Decimal("0.00"), Decimal("1000.00")),
        }
        # وقيد الفاتورة نفسه بقي نقيّاً
        lines = self._invoice_journal_lines(inv)
        assert sum(l.debit for l in lines if l.account_id in (self.uc.pk, self.cash.pk)) \
            == Decimal("0")

    def test_unpost_releases_the_attached_cheque_voucher(self):
        """إلغاء الترحيل يحرّر سند الشيكات المرفقة ويعيدها مسودة — طريق للخروج."""
        inv = self._draft("PURE-CREDIT-3")
        attach_voucher_and_post(
            inv,
            cheques=[{"cheque_number": "CHQ-PURE-4", "amount": "400",
                      "due_date": "2026-09-01"}],
            user=self.user,
        )
        res = self.client.post(
            f"/api/sales/invoices/{inv.pk}/unpost/", {}, format="json", **self.h)
        assert res.status_code == 200, res.content

        inv.refresh_from_db()
        assert inv.status == SalesInvoice.STATUS_DRAFT
        assert inv.amount_paid == Decimal("0.00")
        assert not CustomerPayment.objects.filter(auto_settled_invoice=inv).exists()
        cheque = Cheque.objects.get(sales_invoice=inv)
        assert cheque.status == "Draft"
        assert cheque.customer_payment_id is None

        # T-ARINT: إعادة الترحيل تُنتج سنداً واحداً لا سنداً إضافياً
        post_sales_invoice(inv, user=self.user)
        inv.refresh_from_db()
        assert CustomerPayment.objects.filter(auto_settled_invoice=inv).count() == 1
        assert inv.amount_paid == Decimal("400.00")
        assert inv.amount_paid == posted_allocations_total(inv.pk)

    def test_unpost_releases_legacy_invoice_cheques(self):
        """عدم الانحدار: الشيكات المعلّقة على فواتير مرحّلة **قبل** هذا التغيير
        (مربوطة بـ`Cheque.sales_invoice` بلا سند، بنمط التسوية داخل القيد)
        تعود مسودةً بإلغاء الترحيل كما كانت تماماً."""
        inv = self._draft("PURE-LEGACY-1")
        post_sales_invoice(inv, user=self.user)
        inv.refresh_from_db()
        # محاكاة الصفّ القديم: شيك برسم التحصيل معلّق على الفاتورة، و«مدفوع»
        # مكتوب داخل الترحيل بلا صفّ توزيع.
        legacy = Cheque.objects.create(
            tenant=self.tenant, sales_invoice=inv, partner=self.partner,
            direction="Incoming", status="Under_Collection",
            cheque_number="CHQ-LEGACY", amount=Decimal("400.00"),
            currency=self.currency, due_date="2026-09-01",
        )
        SalesInvoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal("400.00"))

        res = self.client.post(
            f"/api/sales/invoices/{inv.pk}/unpost/", {}, format="json", **self.h)
        assert res.status_code == 200, res.content

        legacy.refresh_from_db()
        inv.refresh_from_db()
        assert legacy.status == "Draft"
        assert inv.status == SalesInvoice.STATUS_DRAFT
        assert inv.amount_paid == Decimal("0.00")
