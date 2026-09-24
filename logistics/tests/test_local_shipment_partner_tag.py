"""استحقاق النقل المحلي يسِم سطر ذمم الناقل وحده — كشف الناقل يرى الدائن.

إنتاج: قيد #10961 (LS-0002، اسامه، 2,000) وسم سطر المصروف 5305 بالناقل أيضاً،
و`partner_posted_balance` يجمع كل أسطر الطرف بلا فلتر حساب ⇒ المدين يُلغي الدائن
وكشف الناقل لا يتحرّك. الهجرة 0090 تُزيل الوسم من القيود القديمة.
"""
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance, post_journal
from logistics.accruals import post_local_shipment_accrual
from logistics.models import LocalShipment, LogisticsShipment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class LocalShipmentAccrualPartnerTagTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="lspt", password="x", email="lspt@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة النقل", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.carrier_ap = Account.objects.create(
            tenant=cls.tenant, code="AP-OSAMA", name="ذمم اسامه",
            account_type="Liability", is_active=True)
        cls.carrier = Partner.objects.create(
            tenant=cls.tenant, name="اسامه", partner_type="LocalTransporter",
            linked_account=cls.carrier_ap)
        cls.expense = Account.objects.get(tenant=cls.tenant, code="5305")
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-LS")

    def _local(self, number="LS-0002"):
        return LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, carrier=self.carrier,
            amount=D("2000"), currency=self.ils, exchange_rate=D("1"),
            expense_account=self.expense, delivery_date="2026-07-02",
            shipment_number=number)

    def test_accrual_credits_carrier_in_partner_balance(self):
        journal = post_local_shipment_accrual(self._local())
        debit, credit = partner_posted_balance(self.tenant.pk, self.carrier.pk)
        self.assertEqual((debit, credit), (D("0"), D("2000.00")))
        self.assertIsNone(journal.lines.get(account=self.expense).partner_id)
        self.assertEqual(journal.lines.get(account=self.carrier_ap).partner_id, self.carrier.pk)

    def test_migration_untags_legacy_expense_line_idempotently(self):
        local = self._local("LS-OLD")
        # كما رحّله الكود القديم: الطرف على السطرين (حارس post_journal يرفضه اليوم،
        # فيُكتب الوسم كما تركه الكود القديم في القاعدة).
        journal = post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-07-02",
            reference_type="LOCAL_SHIPMENT", reference_id=local.pk, description="قديم",
            lines_data=[
                {"account": self.expense.pk,
                 "debit": D(2000), "credit": D(0), "description": "استحقاق"},
                {"account": self.carrier_ap.pk, "partner": self.carrier.pk,
                 "debit": D(0), "credit": D(2000), "description": "ارسالية"},
            ])
        JournalLine.objects.filter(journal=journal, account=self.expense).update(
            partner_id=self.carrier.pk)
        self.assertEqual(partner_posted_balance(self.tenant.pk, self.carrier.pk),
                         (D("2000.00"), D("2000.00")))

        migration = importlib.import_module(
            "logistics.migrations.0090_untag_local_shipment_expense_partner")
        for _ in range(2):  # idempotent
            migration.untag_local_shipment_expense_lines(django_apps, None)
        self.assertEqual(partner_posted_balance(self.tenant.pk, self.carrier.pk),
                         (D("0"), D("2000.00")))
        amounts = sorted(JournalLine.objects.filter(journal=journal)
                         .values_list("debit", "credit"))
        self.assertEqual(amounts, [(D("0"), D("2000.00")), (D("2000.00"), D("0"))])
