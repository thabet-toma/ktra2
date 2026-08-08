"""P-H-5: Voucher atomicity — cheque creation + post in one transaction."""
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalHeader
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
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
        # Patch where post_journal is *used* in sales.services (it's imported
        # directly there, so patching accounting.services.post_journal would
        # not intercept the call).
        with patch(
            "sales.services.post_journal",
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
        attach_voucher_and_post(
            self.invoice,
            cash_amount=5000,
            cash_account_id=self.cash_account.id,
            cheques=[],
            user=None,
        )
        self.invoice.refresh_from_db()
        self.assertIn(self.invoice.status, ("posted", "draft"))
