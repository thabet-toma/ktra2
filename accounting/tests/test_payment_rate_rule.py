"""القاعدة الواحدة لسعر صرف الدفعة (`accounting/services.py` — `require_payment_rate`).

الشيكل: 1 بلا سؤال. غيره: السعر من الطلب إلزامي، و1 أو صفر أو غيابه مرفوض.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.services import require_payment_rate
from tenants.models import Currency


class RequirePaymentRateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ils, _ = Currency.objects.get_or_create(Code='ILS', defaults={'IsBaseCurrency': True})
        cls.usd, _ = Currency.objects.get_or_create(Code='USD', defaults={'IsBaseCurrency': False})

    def test_base_currency_is_one_whatever_was_sent(self):
        for sent in (None, '', '3.7', 0):
            with self.subTest(sent=sent):
                self.assertEqual(require_payment_rate(self.ils, sent), Decimal('1'))

    def test_no_currency_is_base(self):
        self.assertEqual(require_payment_rate(None, None), Decimal('1'))

    def test_foreign_rate_is_returned_exactly(self):
        self.assertEqual(require_payment_rate(self.usd, '3.715'), Decimal('3.715'))
        self.assertEqual(require_payment_rate(self.usd.pk, Decimal('3.6')), Decimal('3.6'))

    def test_foreign_without_a_real_rate_is_rejected_on_the_named_field(self):
        for sent in (None, '', '0', '-2', '1', 1, '1.00', 'abc', 'NaN'):
            with self.subTest(sent=sent):
                with self.assertRaises(ValidationError) as ctx:
                    require_payment_rate(self.usd, sent, field='rate')
                self.assertIn('rate', ctx.exception.message_dict)
                self.assertIn('USD', ctx.exception.message_dict['rate'][0])


class AllocationInInvoiceCurrencyTest(TestCase):
    """تحويل التوزيع بلا جدول أسعار: سعر السند للفاتورة بالشيكل، وإلا ما ذكره المستخدم."""

    @classmethod
    def setUpTestData(cls):
        cls.ils, _ = Currency.objects.get_or_create(Code='ILS', defaults={'IsBaseCurrency': True})
        cls.usd, _ = Currency.objects.get_or_create(Code='USD', defaults={'IsBaseCurrency': False})
        cls.eur, _ = Currency.objects.get_or_create(Code='EUR', defaults={'IsBaseCurrency': False})

    def convert(self, amount, pay, rate, inv, stated=None):
        from accounting.services import allocation_in_invoice_currency
        return allocation_in_invoice_currency(
            amount, pay_currency=pay, pay_rate=rate, invoice_currency=inv,
            stated_in_invoice=stated)

    def test_same_currency_is_untouched(self):
        self.assertEqual(self.convert('100', self.usd, '3.7', self.usd), (Decimal('100'), Decimal('1')))
        self.assertEqual(self.convert('100', None, None, self.ils), (Decimal('100'), Decimal('1')))

    def test_foreign_voucher_on_shekel_invoice_uses_the_voucher_rate(self):
        self.assertEqual(self.convert('100', self.usd, '3.7', self.ils),
                         (Decimal('370.00'), Decimal('3.7')))

    def test_other_pairs_need_the_amount_stated_in_invoice_currency(self):
        for pay, inv in ((self.ils, self.usd), (self.usd, self.eur)):
            with self.subTest(pay=pay.Code, inv=inv.Code):
                with self.assertRaisesMessage(ValidationError, inv.Code):
                    self.convert('370', pay, '1', inv)
        self.assertEqual(self.convert('370', self.ils, None, self.usd, stated='100'),
                         (Decimal('100.00'), Decimal('0.270270')))


class PostJournalUnitRateGuardTest(TestCase):
    """شبكة الأمان: قيدٌ بعملةٍ غير الأساس وسعره 1 يُرفض في `post_journal` نفسها."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from accounting.models import Account
        from accounting.services import create_fiscal_year
        from tenants.services import create_company

        cls.ils, _ = Currency.objects.get_or_create(Code='ILS', defaults={'IsBaseCurrency': True})
        cls.usd, _ = Currency.objects.get_or_create(Code='USD', defaults={'IsBaseCurrency': False})
        cls.tenant = create_company('شركة الحارس', User.objects.create_user(username='guard'))
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code='1101')
        cls.expense = Account.objects.get(tenant=cls.tenant, code='5203')

    def post(self, ref, currency, rate, **extra):
        from accounting.services import post_journal
        return post_journal(
            tenant_id=self.tenant.pk, transaction_date='2026-06-10', reference_type='TEST_GUARD',
            reference_id=ref, description='حارس', currency=currency, exchange_rate=Decimal(rate),
            **extra,
            lines_data=[
                {'account': self.expense.pk, 'debit': Decimal('10'), 'credit': Decimal('0')},
                {'account': self.cash.pk, 'debit': Decimal('0'), 'credit': Decimal('10')},
            ])

    def test_foreign_journal_at_one_is_refused(self):
        from accounting.models import JournalHeader
        with self.assertRaisesMessage(ValidationError, 'USD'):
            self.post(1, self.usd, '1')
        self.assertFalse(JournalHeader.objects.filter(reference_type='TEST_GUARD').exists())

    def test_base_at_one_and_foreign_at_a_real_rate_pass(self):
        self.assertTrue(self.post(2, self.ils, '1').is_posted)
        self.assertTrue(self.post(3, None, '1').is_posted)
        self.assertEqual(self.post(4, self.usd, '3.7').exchange_rate, Decimal('3.7'))

    def test_mirror_of_a_legacy_unit_rate_journal_still_posts(self):
        # أداة تصحيحٍ تعادل قيداً دولارياً قديماً رُحِّل بسعر 1 — رفضُها يُبقي نصفه بلا تصحيح.
        mirror = self.post(5, self.usd, '1', idempotent=False, mirrors_posted_lines=True)
        self.assertTrue(mirror.is_posted)
