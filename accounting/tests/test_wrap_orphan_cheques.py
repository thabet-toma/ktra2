"""T-CHQ3 — ضمّ الشيكات السائبة (المُنشأة قبل توحيد المسار) إلى سنداتها.

بلاغ المالك: «أنا كبست تحويل وما حطّ قيود». تلك الشيكات موجودة في القواعد
الحيّة بلا سند ⇒ بلا قيد، ولا يصلحها توحيد المسار وحده.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from accounting.models import Account, Cheque, JournalHeader
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesSettings
from tenants.models import Currency
from tenants.services import create_company


class WrapOrphanChequesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqwrap", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الشيكات السائبة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون قديم", partner_type="Customer")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.uc_acc = Account.objects.get(tenant=cls.tenant, code="1107")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={
                "default_cheques_under_collection_account": cls.uc_acc,
                "default_cash_account": cls.cash,
            },
        )

    def _orphan(self, number="OLD-1", **over):
        fields = dict(
            tenant=self.tenant, cheque_number=number, amount=Decimal("300.00"),
            currency=self.ils, partner=self.customer, status="Under_Collection",
            direction="Incoming", issue_date="2026-08-01", due_date="2026-08-05",
        )
        fields.update(over)
        return Cheque.objects.create(**fields)

    def _run(self, *extra):
        out = StringIO()
        call_command(
            "wrap_orphan_cheques_in_vouchers",
            "--tenant-id", str(self.tenant.TenantID), *extra,
            stdout=out, stderr=StringIO(),
        )
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        chq = self._orphan()
        out = self._run()
        self.assertIn("معاينة", out)
        chq.refresh_from_db()
        self.assertIsNone(chq.customer_payment_id)

    def test_wraps_orphan_in_a_posted_voucher_on_account(self):
        chq = self._orphan()
        self._run("--apply")
        chq.refresh_from_db()
        self.assertIsNotNone(chq.customer_payment_id)
        payment = chq.customer_payment
        self.assertTrue(payment.is_posted)
        self.assertEqual(payment.allocations.count(), 0)  # على الحساب
        debit = next(ln for ln in payment.journal.lines.select_related("account")
                     if ln.debit > 0)
        self.assertEqual(debit.account.code, "1107")

    def test_wrapped_cheque_can_then_be_collected(self):
        chq = self._orphan()
        self._run("--apply")
        self.client.force_authenticate(user=self.user) if hasattr(
            self.client, "force_authenticate") else None
        from accounting.services import transfer_cheque
        transfer_cheque(chq.pk, "collect", user=self.user,
                        movement_date="2026-08-07")
        self.assertTrue(JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="CHEQUE_COLLECT",
            reference_id=chq.pk).exists())

    def test_skips_cheque_already_inside_a_document(self):
        """التشغيل مرتين لا ينشئ سنداً ثانياً للورقة نفسها."""
        from sales.models import CustomerPayment
        self._orphan(number="OLD-2")
        self._run("--apply")
        out = self._run("--apply")
        self.assertIn("مربوط بسند/فاتورة أصلاً", out)
        self.assertEqual(CustomerPayment.objects.filter(tenant=self.tenant).count(), 1)

    def test_skips_cheque_without_partner(self):
        chq = self._orphan(number="OLD-3")
        Cheque.objects.filter(pk=chq.pk).update(partner=None)
        out = self._run("--apply")
        self.assertIn("بلا طرف", out)
        chq.refresh_from_db()
        self.assertIsNone(chq.customer_payment_id)
