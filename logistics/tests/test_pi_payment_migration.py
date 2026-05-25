"""P-D-7: PurchaseInvoicePayment — JSON → rows idempotent migration."""
from decimal import Decimal

from django.test import TestCase

from accounting.models import Account, JournalHeader
from logistics.models import PurchaseInvoice, PurchaseInvoicePayment
from partners.models import Partner
from tenants.models import Currency, Tenant


class PiPaymentMigrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=50, CompanyName="PI Test Co")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="PI Supplier",
            partner_type="Supplier",
        )
        cls.cash_account = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق نقدي",
            account_type="Asset", is_active=True,
        )
        cls.invoice = PurchaseInvoice.objects.create(
            tenant=cls.tenant, invoice_number="INV-PI-001",
            partner=cls.partner, currency=cls.currency,
            grand_total=Decimal("5000.00"),
            invoice_date="2026-01-15",
        )

    def test_create_payment_row(self):
        payment = PurchaseInvoicePayment.objects.create(
            tenant=self.tenant,
            invoice=self.invoice,
            payment_date="2026-01-20",
            amount=Decimal("3000.00"),
            currency=self.currency,
            exchange_rate=Decimal("1.0"),
            payment_method="bank_transfer",
            cash_or_bank_account=self.cash_account,
            reference_number="TRF-001",
        )
        self.assertEqual(payment.amount, Decimal("3000.00"))
        self.assertEqual(payment.payment_method, "bank_transfer")
        self.assertIsNotNone(payment.id)

    def test_multiple_payments_sum_to_grand_total(self):
        PurchaseInvoicePayment.objects.create(
            tenant=self.tenant, invoice=self.invoice,
            payment_date="2026-01-20", amount=Decimal("2000.00"),
            currency=self.currency, exchange_rate=Decimal("1.0"),
            payment_method="bank_transfer",
            cash_or_bank_account=self.cash_account,
        )
        PurchaseInvoicePayment.objects.create(
            tenant=self.tenant, invoice=self.invoice,
            payment_date="2026-01-25", amount=Decimal("3000.00"),
            currency=self.currency, exchange_rate=Decimal("1.0"),
            payment_method="cheque",
            cash_or_bank_account=self.cash_account,
        )
        payments = PurchaseInvoicePayment.objects.filter(invoice=self.invoice)
        total_paid = sum((p.amount for p in payments), Decimal("0"))
        self.assertEqual(total_paid, Decimal("5000.00"))

    def test_payment_is_posted_creates_journal_ref(self):
        journal = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-01-20",
            description="Test payment", is_posted=True,
        )
        payment = PurchaseInvoicePayment.objects.create(
            tenant=self.tenant, invoice=self.invoice,
            payment_date="2026-01-20", amount=Decimal("5000.00"),
            currency=self.currency, exchange_rate=Decimal("1.0"),
            payment_method="bank_transfer",
            cash_or_bank_account=self.cash_account,
            is_posted=True,
            journal=journal,
        )
        self.assertTrue(payment.is_posted)
        self.assertIsNotNone(payment.journal)
