"""P-H-5: Voucher atomicity — cheque creation + post in one transaction."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalHeader
from inventory.models import Product
from partners.models import Partner
from sales.models import CustomerPayment, SalesInvoice, SalesInvoiceLine
from sales.services import attach_voucher_and_post
from tenants.models import Currency, Tenant


class VoucherAtomicityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=130, CompanyName="Atomic Test")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.cash_account = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق نقدي",
            account_type="Asset", is_active=True,
        )
        cls.revenue_account = Account.objects.create(
            tenant=cls.tenant, code="4101", name="إيرادات مبيعات",
            account_type="Revenue", is_active=True,
        )
        cls.ar_account = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء",
            account_type="Asset", is_active=True,
        )
        # Accounts required by post_sales_invoice / attach_payment_voucher.
        Account.objects.create(
            tenant=cls.tenant, code="1106", name="شيكات برسم التحصيل",
            account_type="Asset", is_active=True,
        )
        Account.objects.create(
            tenant=cls.tenant, code="5101", name="تكلفة المبيعات",
            account_type="Expense", is_active=True,
        )
        Account.objects.create(
            tenant=cls.tenant, code="1104", name="المخزون",
            account_type="Asset", is_active=True,
        )
        Account.objects.create(
            tenant=cls.tenant, code="2101", name="ض.ق.م مستحقة",
            account_type="Liability", is_active=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="Atomic Customer",
            partner_type="Customer",
            linked_account=cls.ar_account,
        )
        # Service product to skip COGS / inventory account resolution —
        # this test is about voucher atomicity, not stock accounting.
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="ATOM-PROD", name_ar="منتج ذري",
            is_service=True,
        )
        # post_journal requires an open fiscal period covering the invoice date.
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026",
            start_date="2026-01-01", end_date="2026-12-31",
            is_closed=False,
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="INV-ATOM-001",
            customer=cls.partner, currency=cls.currency,
            grand_total=Decimal("5000.00"), invoice_date="2026-07-01",
            stock_on_post=False,
        )
        SalesInvoiceLine.objects.create(
            tenant=cls.tenant,
            invoice=cls.invoice,
            product=cls.product, quantity=1, unit_price=Decimal("5000.00"),
        )

    def test_post_failure_removes_cheques(self):
        # Patch where post_journal is *used*: بعد تفكيك sales/services إلى حزمة
        # (المرحلة 3) صارت attach_voucher_and_post في sales.services.flow، وهي
        # تربط post_journal في فضاء اسمها هناك — فالـpatch على موضع الاستخدام.
        # (patching accounting.services.post_journal لا يعترض لأنه مستورد مباشرة.)
        with patch(
            "sales.services.flow.post_journal",
            side_effect=ValueError("فشل الترحيل"),
        ):
            with self.assertRaises(ValueError):
                attach_voucher_and_post(
                    self.invoice,
                    cash_amount=2000,
                    cash_account_id=self.cash_account.id,
                    cheques=[
                        {"cheque_number": "CHQ-ATOM", "amount": "3000",
                         "due_date": "2026-09-01"},
                    ],
                    user=None,
                )
        cheque_count = Cheque.objects.filter(
            sales_invoice=self.invoice,
        ).count()
        self.assertEqual(cheque_count, 0)

    def test_successful_attach_and_post(self):
        """T2: النقدي المرفق صار سند قبض حقيقياً — لا رقماً في عمود لا يُرحَّل.

        كان هذا الفحص `assertIn(status, ("posted", "draft"))` — شرطٌ لا يمكن أن
        يسقط؛ ثم صار في T1 يُثبّت أن `attached_cash_amount` «يُسجَّل ولا
        يُرحَّل». وذاك بالضبط العيب: مالٌ يدخل الصندوق ولا أثر له في الدفاتر.
        العقد الآن: قيد الفاتورة يبقى نقيّاً، والنقد يُحصَّل بسند مرحّل واحد،
        والعمود القديم يُصفَّر.
        """
        attach_voucher_and_post(
            self.invoice,
            cash_amount=5000,
            cash_account_id=self.cash_account.id,
            cheques=[],
            user=None,
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, SalesInvoice.STATUS_POSTED)
        self.assertEqual(self.invoice.attached_cash_amount, Decimal("0.00"))

        lines = list(self.invoice.journal.lines.all())
        self.assertEqual(sum(l.debit for l in lines), sum(l.credit for l in lines))
        # لا سطر صندوق داخل قيد الفاتورة — التحصيل مستند مستقل
        self.assertEqual(
            sum(l.debit for l in lines if l.account_id == self.cash_account.id),
            Decimal("0"),
        )
        # الذمم تُدين بكامل الإجمالي ولا تُسوَّى داخل القيد نفسه
        self.assertEqual(
            sum(l.debit for l in lines if l.account_id == self.ar_account.id),
            self.invoice.grand_total,
        )
        self.assertEqual(
            sum(l.credit for l in lines if l.account_id == self.ar_account.id),
            Decimal("0"),
        )
        # النقد المرفق: سند قبض واحد مرحّل بتوزيع كامل يُسدّد الفاتورة
        payment = CustomerPayment.objects.get(auto_settled_invoice=self.invoice)
        self.assertTrue(payment.is_posted)
        self.assertEqual(payment.amount, Decimal("5000.00"))
        self.assertEqual(self.invoice.amount_paid, Decimal("5000.00"))
        pay_lines = [
            l for jh in JournalHeader.objects.filter(
                tenant=self.tenant, reference_type="CUSTOMER_PAYMENT",
                reference_id=payment.pk)
            for l in jh.lines.all()
        ]
        self.assertEqual(
            sum(l.debit for l in pay_lines if l.account_id == self.cash_account.id),
            Decimal("5000.00"),
        )
        self.assertEqual(
            sum(l.credit for l in pay_lines if l.account_id == self.ar_account.id),
            Decimal("5000.00"),
        )

    def test_attached_cheques_are_swept_into_a_posted_voucher(self):
        """T1: الشيك المرفق لا يُسوَّى داخل قيد الفاتورة بل بسند قبض مرحَّل."""
        attach_voucher_and_post(
            self.invoice,
            cash_amount=0,
            cash_account_id=None,
            cheques=[{"cheque_number": "CHQ-ATOM-2", "amount": "3000",
                      "due_date": "2026-09-01"}],
            user=None,
        )
        self.invoice.refresh_from_db()

        uc = Account.objects.get(tenant=self.tenant, code="1106")
        lines = list(self.invoice.journal.lines.all())
        self.assertEqual(
            sum(l.debit for l in lines if l.account_id == uc.id), Decimal("0"),
        )
        payment = CustomerPayment.objects.get(auto_settled_invoice=self.invoice)
        self.assertTrue(payment.is_posted)
        self.assertEqual(payment.amount, Decimal("3000.00"))
        self.assertEqual(self.invoice.amount_paid, Decimal("3000.00"))
        cheque = Cheque.objects.get(sales_invoice=self.invoice)
        self.assertEqual(cheque.customer_payment_id, payment.pk)
        self.assertEqual(cheque.status, "Under_Collection")
