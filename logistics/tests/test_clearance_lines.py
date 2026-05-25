"""P-D-1: Clearance lines — create, sum debit/credit, VAT calc."""
from decimal import Decimal

from django.test import TestCase

from accounting.models import Account
from logistics.models import (
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsDeal,
    LogisticsShipment,
)
from partners.models import Partner
from tenants.models import Currency, Tenant


class ClearanceLinesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=99, CompanyName="Test Co")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="Supplier Co",
            partner_type="Supplier",
        )
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-CL-001",
            partner=cls.partner, order_date="2026-01-01",
            currency=cls.currency, total_amount=1000,
        )
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-CL-001",
        )
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment,
            status='Processing',
            currency=cls.currency, grand_total=500,
        )
        cls.expense_account = Account.objects.create(
            tenant=cls.tenant, code="5301", name="رسوم شحن",
            account_type="Expense", is_active=True,
        )
        cls.vat_account = Account.objects.create(
            tenant=cls.tenant, code="1105", name="ضريبة مدخلات",
            account_type="Asset", is_active=True,
        )

    def _create_line(self, line_type, debit=0, credit=0, vat_percent=None, account=None):
        seq = LogisticsClearanceLine.objects.filter(clearance=self.clearance).count() + 1
        return LogisticsClearanceLine.objects.create(
            clearance=self.clearance,
            seq=seq,
            line_type=line_type,
            account=account or self.expense_account,
            description=f"Test line {seq}",
            debit=Decimal(str(debit)),
            credit=Decimal(str(credit)),
            vat_percent=Decimal(str(vat_percent)) if vat_percent else Decimal('0'),
        )

    def test_create_clearance_line(self):
        line = self._create_line("broker_commission", debit=150)
        self.assertEqual(line.clearance_id, self.clearance.id)
        self.assertEqual(line.debit, Decimal("150.00"))
        self.assertEqual(line.credit, Decimal("0.00"))

    def test_sum_debit_matches_grand_total(self):
        self._create_line("declaration_fee", debit=300)
        self._create_line("terminal", debit=200)
        lines = LogisticsClearanceLine.objects.filter(clearance=self.clearance)
        total_debit = sum((l.debit for l in lines), Decimal("0"))
        self.assertEqual(total_debit, Decimal("500.00"))

    def test_vat_calculation_on_line(self):
        line = self._create_line("broker_commission", debit=1000, vat_percent=17)
        vat_amount = (line.debit * line.vat_percent / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(vat_amount, Decimal("170.00"))

    def test_credit_and_debit_lines(self):
        self._create_line("customs_system", debit=500)
        self._create_line("other", credit=500, account=self.vat_account)
        lines = LogisticsClearanceLine.objects.filter(clearance=self.clearance)
        total_dr = sum((l.debit for l in lines), Decimal("0"))
        total_cr = sum((l.credit for l in lines), Decimal("0"))
        self.assertEqual(total_dr, Decimal("500.00"))
        self.assertEqual(total_cr, Decimal("500.00"))
