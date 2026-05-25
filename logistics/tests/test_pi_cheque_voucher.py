"""P-H-1: Cheque attached to PurchaseInvoice via attach_pi_payment_voucher."""
from decimal import Decimal

from django.test import TestCase

from accounting.models import Account, Cheque
from logistics.models import PurchaseInvoice
from logistics.services import attach_pi_payment_voucher
from partners.models import Partner
from tenants.models import Currency, Tenant


class PiChequeVoucherTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=90, CompanyName="PI Chq Test")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.cash_account = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق نقدي",
            account_type="Asset", is_active=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="PI Chq Supplier",
            partner_type="Supplier",
        )
        cls.invoice = PurchaseInvoice.objects.create(
            tenant=cls.tenant, invoice_number="INV-CHQ-001",
            partner=cls.partner, currency=cls.currency,
            grand_total=Decimal("10000.00"),
            invoice_date="2026-05-01",
        )

    def test_attach_cash_and_cheques(self):
        attach_pi_payment_voucher(
            self.invoice,
            cash_amount=2000,
            cash_account_id=self.cash_account.id,
            cheques=[
                {"cheque_number": "CHQ-001", "amount": "3000", "bank_name": "بنك أ"},
                {"cheque_number": "CHQ-002", "amount": "5000", "bank_name": "بنك ب"},
            ],
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.attached_cash_amount, Decimal("2000.00"))
        cheques = Cheque.objects.filter(purchase_invoice=self.invoice)
        self.assertEqual(cheques.count(), 2)
        total_chq = sum((c.amount for c in cheques), Decimal("0"))
        self.assertEqual(total_chq, Decimal("8000.00"))

    def test_exceeding_grand_total_raises(self):
        with self.assertRaises(Exception):
            attach_pi_payment_voucher(
                self.invoice,
                cash_amount=20000,
                cheques=[],
            )

    def test_replace_semantics_deletes_old_draft_cheques(self):
        Cheque.objects.create(
            tenant=self.tenant, purchase_invoice=self.invoice,
            cheque_number="OLD-CHQ", amount=1000,
            status="Draft", direction="Outgoing",
            currency=self.currency,
        )
        attach_pi_payment_voucher(
            self.invoice,
            cash_amount=0,
            cheques=[
                {"cheque_number": "NEW-CHQ", "amount": "5000"},
            ],
        )
        cheques = Cheque.objects.filter(purchase_invoice=self.invoice)
        self.assertEqual(cheques.count(), 1)
        self.assertEqual(cheques.first().cheque_number, "NEW-CHQ")
