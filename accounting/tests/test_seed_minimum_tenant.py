"""`seed_minimum_tenant` — الزرع اليدوي لقاعدةٍ تُبنى من صفر يعمل ولا يكرّر.

كان يكتب `FiscalPeriod.is_active` بعد أن زال الحقل من النموذج فيسقط بـ
`FieldError` قبل أن يزرع الفترة — هذا الاختبار ينفّذ الأمر نفسه على قاعدة
الاختبار مرّتين كي لا يتعفّن ثانيةً بصمت.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounting.management.commands.seed_minimum_tenant import ACCOUNT_TREE
from accounting.models import Account, FiscalPeriod
from tenants.models import Currency, Tenant


class SeedMinimumTenantCommandTest(TestCase):
    def run_seed(self):
        out = StringIO()
        call_command('seed_minimum_tenant', stdout=out)
        return out.getvalue()

    def test_seeds_tenant_currencies_accounts_and_open_period(self):
        output = self.run_seed()

        self.assertIn('Minimum tenant seed complete.', output)
        tenant = Tenant.objects.get(TenantID=1)
        self.assertTrue(Currency.objects.get(Code='ILS').IsBaseCurrency)
        self.assertFalse(Currency.objects.get(Code='USD').IsBaseCurrency)
        self.assertEqual(Account.objects.filter(tenant=tenant).count(), len(ACCOUNT_TREE))
        self.assertEqual(Account.objects.get(tenant=tenant, code='1101').parent.code, '1100')

        year = timezone.localdate().year
        period = FiscalPeriod.objects.get(tenant=tenant, name=str(year))
        self.assertEqual(period.status, 'Open')
        self.assertFalse(period.is_closed)
        self.assertEqual((period.start_date.month, period.start_date.day), (1, 1))
        self.assertEqual((period.end_date.month, period.end_date.day), (12, 31))

    def test_second_run_is_idempotent(self):
        self.run_seed()
        output = self.run_seed()

        self.assertIn('FiscalPeriod exists', output)
        tenant = Tenant.objects.get(TenantID=1)
        self.assertEqual(Tenant.objects.filter(TenantID=1).count(), 1)
        self.assertEqual(Currency.objects.filter(Code__in=['ILS', 'USD']).count(), 2)
        self.assertEqual(Account.objects.filter(tenant=tenant).count(), len(ACCOUNT_TREE))
        self.assertEqual(FiscalPeriod.objects.filter(tenant=tenant).count(), 1)
