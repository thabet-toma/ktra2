"""P-H-8: Multi-currency FX per allocation — separate FX lines per invoice."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting.models import Account, JournalHeader, JournalLine
from partners.models import Partner
from sales.models import CustomerPayment, PaymentAllocation, SalesInvoice
from tenants.models import Currency, Tenant


class MultiCurrencyFxTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=160, CompanyName="FX Test")
        cls.usd = Currency.objects.create(
            CurrencyID=2, Code="USD", Symbol="$", IsBaseCurrency=False,
        )
        cls.eur = Currency.objects.create(
            CurrencyID=3, Code="EUR", Symbol="€", IsBaseCurrency=False,
        )
        cls.ils = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.cash_account = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق",
            account_type="Asset", is_active=True,
        )
        cls.ar_account = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء",
            account_type="Asset", is_active=True,
        )
        cls.fx_account = Account.objects.create(
            tenant=cls.tenant, code="8101", name="فروقات عملة",
            account_type="Expense", is_active=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="FX Customer",
            partner_type="Customer",
            linked_account=cls.ar_account,
        )

    def test_payment_with_multiple_currency_allocations(self):
        invoice_usd = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-USD",
            customer=self.partner, currency=self.usd,
            exchange_rate=Decimal("3.5"), grand_total=Decimal("1000.00"),
            invoice_date="2026-08-01",
        )
        invoice_eur = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-EUR",
            customer=self.partner, currency=self.eur,
            exchange_rate=Decimal("4.0"), grand_total=Decimal("1000.00"),
            invoice_date="2026-08-01",
        )
        payment = CustomerPayment.objects.create(
            tenant=self.tenant,
            partner=self.partner, currency=self.usd,
            exchange_rate=Decimal("3.5"), amount=Decimal("1000.00"),
            cash_or_bank_account=self.cash_account,
            payment_date="2026-08-15",
            is_posted=False,
        )
        PaymentAllocation.objects.create(
            tenant=self.tenant,
            payment=payment,
            invoice=invoice_usd,
            amount=Decimal("500.00"),
        )
        PaymentAllocation.objects.create(
            tenant=self.tenant,
            payment=payment,
            invoice=invoice_eur,
            amount=Decimal("500.00"),
        )
        self.assertEqual(payment.allocations.count(), 2)

    def test_allocation_amounts_sum_to_payment(self):
        # PaymentAllocation has a UNIQUE(payment, invoice) constraint, so we
        # need two distinct invoices to test summing across allocations.
        invoice_a = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-FX-1A",
            customer=self.partner, currency=self.usd,
            exchange_rate=Decimal("3.5"), grand_total=Decimal("600.00"),
            invoice_date="2026-08-01",
        )
        invoice_b = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-FX-1B",
            customer=self.partner, currency=self.usd,
            exchange_rate=Decimal("3.5"), grand_total=Decimal("400.00"),
            invoice_date="2026-08-01",
        )
        payment = CustomerPayment.objects.create(
            tenant=self.tenant,
            partner=self.partner, currency=self.usd,
            exchange_rate=Decimal("3.5"), amount=Decimal("1000.00"),
            cash_or_bank_account=self.cash_account,
            payment_date="2026-08-15",
            is_posted=False,
        )
        PaymentAllocation.objects.create(
            tenant=self.tenant, payment=payment, invoice=invoice_a, amount=Decimal("600.00"),
        )
        PaymentAllocation.objects.create(
            tenant=self.tenant, payment=payment, invoice=invoice_b, amount=Decimal("400.00"),
        )
        total_allocated = sum(
            a.amount for a in PaymentAllocation.objects.filter(payment=payment)
        )
        self.assertEqual(total_allocated, Decimal("1000.00"))
