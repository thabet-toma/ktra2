"""حارس وسم الطرف في `post_journal` — الطرف على حساب ذمّته وحده.

`partner_posted_balance` يجمع كل أسطر الطرف بلا فلتر حساب، فسطر صندوق أو مصروف
موسوم بالطرف يُلغي سطر ذمّته ويقلب كشفه. تكرّر ثلاث مرات (مشتريات، استيراد،
استحقاق النقل المحلي f238db18) لأن كل مسار يبني أسطره يدوياً. الحارس يرفض القيد
قبل إنشائه بدل أن يُكتشف الخلل في كشف الزبون بعد أشهر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.account_classification import SUB_TYPE_CASH_BOX, SUB_TYPE_RECEIVABLE
from accounting.api import reverse_journal
from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance, post_journal
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = Decimal


class PartnerTagGuardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ptg", password="x", email="ptg@x.co")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الحارس", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.supplier_ap = Account.objects.create(
            tenant=cls.tenant, code="2101-G1", name="ذمم مورد الحارس",
            account_type="Liability", is_active=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الحارس", partner_type="Supplier",
            linked_account=cls.supplier_ap)
        cls.expense = Account.objects.get(tenant=cls.tenant, code="5305")
        cls.box = Account.objects.create(
            tenant=cls.tenant, code="BOX-G1", name="صندوق الحارس", account_type="Asset",
            sub_type=SUB_TYPE_CASH_BOX, is_active=True)
        cls.vat_input = Account.objects.create(
            tenant=cls.tenant, code="VAT-G1", name="ضريبة مدخلات", account_type="Asset",
            is_active=True)
        cls.other_ar = Account.objects.create(
            tenant=cls.tenant, code="AR-G1", name="ذمم عامة", account_type="Asset",
            sub_type=SUB_TYPE_RECEIVABLE, is_active=True)

    def _post(self, lines, ref_id=1):
        return post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-07-02",
            reference_type="TAG_GUARD_TEST", reference_id=ref_id, description="حارس",
            lines_data=lines)

    @staticmethod
    def _line(account, debit, credit, partner=None):
        return {"account": account.pk, "partner": partner, "debit": D(debit),
                "credit": D(credit), "description": "سطر"}

    def test_expense_line_tagged_with_supplier_is_refused_before_any_write(self):
        with self.assertRaises(ValidationError) as ctx:
            self._post([
                self._line(self.expense, 2000, 0, self.supplier.pk),
                self._line(self.supplier_ap, 0, 2000, self.supplier.pk),
            ])
        self.assertIn("مورد الحارس", str(ctx.exception))
        self.assertIn("5305", str(ctx.exception))
        self.assertFalse(JournalHeader.objects.filter(reference_type="TAG_GUARD_TEST").exists())

    def test_cash_box_line_tagged_is_refused_even_without_linked_account(self):
        bare = Partner.objects.create(tenant=self.tenant, name="طرف بلا حساب",
                                      partner_type="Supplier")
        Partner.objects.filter(pk=bare.pk).update(linked_account=None)
        with self.assertRaises(ValidationError):
            self._post([
                self._line(self.other_ar, 500, 0, bare.pk),
                self._line(self.box, 0, 500, bare.pk),
            ])

    def test_unclassified_account_refused_when_partner_has_own_account(self):
        with self.assertRaises(ValidationError):
            self._post([
                self._line(self.vat_input, 160, 0, self.supplier.pk),
                self._line(self.supplier_ap, 0, 160, self.supplier.pk),
            ])

    def test_control_line_tag_passes_and_moves_the_balance(self):
        self._post([
            self._line(self.expense, 2000, 0),
            self._line(self.supplier_ap, 0, 2000, self.supplier.pk),
        ])
        self.assertEqual(partner_posted_balance(self.tenant.pk, self.supplier.pk),
                         (D("0"), D("2000.00")))

    def test_other_receivable_account_passes(self):
        # ذمم الفاتورة المختارة (`accounts_receivable_account`) أو ذمم المجموعة —
        # حساب ذمم وإن لم يكن حساب الطرف نفسه.
        self._post([
            self._line(self.other_ar, 300, 0, self.supplier.pk),
            self._line(self.expense, 0, 300),
        ])

    def test_legacy_tagged_journal_still_reverses(self):
        journal = self._post([
            self._line(self.expense, 700, 0),
            self._line(self.supplier_ap, 0, 700, self.supplier.pk),
        ])
        # قيد قديم كتبه الكود قبل الحارس: الطرف على سطر المصروف أيضاً.
        JournalLine.objects.filter(journal=journal, account=self.expense).update(
            partner_id=self.supplier.pk)
        rev = reverse_journal(journal, reference_type="JOURNAL_REVERSAL",
                              reference_id=journal.pk, description="عكس",
                              transaction_date="2026-07-03")
        self.assertEqual(rev.lines.filter(partner_id=self.supplier.pk).count(), 2)

    def test_mirror_of_posted_lines_keeps_the_legacy_tag(self):
        # أدوات التصحيح تعادل قيداً قديماً سطراً بسطر: وسمُه يُنسخ وإلا بقي نصفه.
        journal = post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-07-02",
            reference_type="TAG_GUARD_TEST", reference_id=9, description="تسوية",
            lines_data=[
                self._line(self.supplier_ap, 400, 0, self.supplier.pk),
                self._line(self.box, 0, 400, self.supplier.pk),
            ],
            mirrors_posted_lines=True)
        self.assertEqual(journal.lines.filter(partner_id=self.supplier.pk).count(), 2)
