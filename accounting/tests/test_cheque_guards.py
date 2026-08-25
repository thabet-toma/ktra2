"""CHQ-4 — أربع ثغرات وُجدت أثناء أودت دورة الشيكات، وسُدَّت.

1. **الحذف بلا حارس**: شيك محصَّل يُحذف وقيود تحصيله تبقى في اليومية بلا ورقة
   تفسّرها. الباب أُغلق أمام تغيير الحالة بـPATCH منذ task11 وتُرك مفتوحاً أمام
   الإفناء الكامل.
2. **PATCH خام يغيّر ما قرأه القيد**: `fields='__all__'` جعل `endorsed_to` و
   `deposit_bank_account` والمبلغ والطرف قابلةً للكتابة بعد الترحيل.
3. **`Endorsed` نهائية**: ارتداد ورقةٍ ظُهِّرت لمورد — حدثٌ يقع فعلاً — لا سبيل
   لتسجيله، فتبقى ذمّة المورد منخفضة بورقةٍ لم تُصرف.
4. **`withdraw` من مسودة مربوطة**: قيدٌ يدائن حساباً لم يُدَّن قط.
5. وحراسة تاريخ الحركة: لا مستقبل، ولا رجوعٌ إلى ما قبل آخر حركة مرحّلة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.models import (
    Account, Bank, BankAccount, Cheque, ChequeMovement, JournalHeader, JournalLine,
)
from accounting.services import create_fiscal_year, transfer_cheque
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings, SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class ChequeGuardsTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chq_guard", password="x")
        cls.ils = Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الحُرّاس", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الحارس", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الحارس", partner_type="Supplier")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="GRD-INV-1", customer=cls.customer,
            currency=cls.ils, invoice_date="2026-06-11",
            status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("1000.00"),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _cheque(self, number, *, status="Received", linked=True, direction="Incoming"):
        return Cheque.objects.create(
            tenant=self.tenant, cheque_number=number, amount=Decimal("1000.00"),
            currency=self.ils, partner=self.customer, status=status,
            direction=direction,
            sales_invoice=self.invoice if (linked and direction == "Incoming") else None,
            bank_name="بنك القدس", due_date="2026-09-30",
        )

    def _partner_balance(self, partner):
        """صافي (مدين − دائن) على حساب الطرف — كشفُه كما يقرؤه المحاسب."""
        total = Decimal("0")
        for line in JournalLine.objects.filter(partner=partner):
            total += Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        return total

    # ── 1. الحذف ────────────────────────────────────────────────────────────

    def test_a_cheque_with_a_posted_movement_cannot_be_deleted(self):
        cheque = self._cheque("DEL-1")
        transfer_cheque(cheque.pk, "collect", user=self.user)
        journals_before = JournalHeader.objects.filter(tenant=self.tenant).count()

        resp = self.client.delete(f"/api/accounting/cheques/{cheque.pk}/")

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertTrue(Cheque.objects.filter(pk=cheque.pk).exists())
        self.assertEqual(
            JournalHeader.objects.filter(tenant=self.tenant).count(),
            journals_before, "تغيّرت اليومية رغم رفض الحذف")

    def test_a_cheque_inside_a_posted_document_cannot_be_deleted(self):
        cheque = self._cheque("DEL-2", status="Draft")
        resp = self.client.delete(f"/api/accounting/cheques/{cheque.pk}/")
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("ألغِ ترحيلها", str(resp.data))

    def test_a_draft_orphan_cheque_is_still_deletable(self):
        """الحارس يمنع ما يترك أثراً — لا يمنع كل شيء."""
        cheque = self._cheque("DEL-3", status="Draft", linked=False)
        resp = self.client.delete(f"/api/accounting/cheques/{cheque.pk}/")
        self.assertEqual(resp.status_code, 204, getattr(resp, "data", None))
        self.assertFalse(Cheque.objects.filter(pk=cheque.pk).exists())

    # ── 2. الكتابة الخام ────────────────────────────────────────────────────

    def test_raw_patch_cannot_move_the_endorsee_after_its_journal_posted(self):
        cheque = self._cheque("PATCH-1")
        transfer_cheque(cheque.pk, "endorse", user=self.user,
                        endorsed_to_id=self.supplier.pk)
        other = Partner.objects.create(
            tenant=self.tenant, name="مورد آخر", partner_type="Supplier")

        resp = self.client.patch(
            f"/api/accounting/cheques/{cheque.pk}/",
            {"endorsed_to": other.pk}, format="json")

        cheque.refresh_from_db()
        self.assertEqual(cheque.endorsed_to_id, self.supplier.pk,
                         f"تغيّر مستفيد التظهير بـPATCH خام ({resp.status_code})")

    def test_raw_patch_cannot_change_the_amount_a_posted_journal_read(self):
        cheque = self._cheque("PATCH-2", status="Draft")
        resp = self.client.patch(
            f"/api/accounting/cheques/{cheque.pk}/",
            {"amount": "9999.00"}, format="json")
        self.assertEqual(resp.status_code, 400, resp.data)
        cheque.refresh_from_db()
        self.assertEqual(Decimal(str(cheque.amount)), Decimal("1000.00"))

    def test_editing_a_harmless_field_still_works(self):
        cheque = self._cheque("PATCH-3", status="Draft")
        resp = self.client.patch(
            f"/api/accounting/cheques/{cheque.pk}/",
            {"notes": "ملاحظة مضافة"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        cheque.refresh_from_db()
        self.assertEqual(cheque.notes, "ملاحظة مضافة")

    # ── 3. ارتداد الشيك المظهَّر ────────────────────────────────────────────

    def test_an_endorsed_cheque_can_bounce_and_both_parties_are_restored(self):
        cheque = self._cheque("ENDO-1")
        transfer_cheque(cheque.pk, "endorse", user=self.user,
                        endorsed_to_id=self.supplier.pk)
        customer_after_endorse = self._partner_balance(self.customer)
        supplier_after_endorse = self._partner_balance(self.supplier)

        transfer_cheque(cheque.pk, "bounce", user=self.user)

        cheque.refresh_from_db()
        self.assertEqual(cheque.status, "Bounced")
        # المورد يعود دائناً كما كان قبل التظهير (ذمّته ارتفعت ثانيةً).
        self.assertEqual(
            self._partner_balance(self.supplier),
            supplier_after_endorse - Decimal("1000.00"),
            "ذمّة المورد لم تُستعَد بعد ارتداد الورقة المظهَّرة")
        # والعميل الساحب يعود مديناً بقيمة الورقة.
        self.assertEqual(
            self._partner_balance(self.customer),
            customer_after_endorse + Decimal("1000.00"),
            "الدين لم يعد على العميل بعد ارتداد شيكه المظهَّر")
        # ولا تُمسّ حسابا الشيكات — الورقة غادرت المحفظة يوم التظهير.
        journal = ChequeMovement.objects.get(
            cheque=cheque, movement_type="bounce").journal
        codes = {line.account.code for line in journal.lines.all()}
        self.assertFalse(codes & {"1107", "1109"},
                         f"قيد ارتداد المظهَّر مسّ حسابات الشيكات: {codes}")

    def test_after_bouncing_an_endorsed_cheque_the_normal_exits_reopen(self):
        cheque = self._cheque("ENDO-2")
        transfer_cheque(cheque.pk, "endorse", user=self.user,
                        endorsed_to_id=self.supplier.pk)
        transfer_cheque(cheque.pk, "bounce", user=self.user)

        transfer_cheque(cheque.pk, "settle", user=self.user)

        cheque.refresh_from_db()
        self.assertEqual(cheque.status, "Settled")

    # ── 4. مسودة مربوطة بمستند ─────────────────────────────────────────────

    def test_a_draft_cheque_inside_a_document_cannot_be_withdrawn(self):
        """القيد كان سيدائن حساباً لم يُدَّن قط ⇒ رصيد سالب لا يكشفه شيء."""
        payment = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.supplier, currency=self.ils,
            payment_date="2026-06-11", amount=Decimal("1000.00"),
            cash_or_bank_account=self.cash, is_posted=True,
        )
        cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number="DRAFT-1", amount=Decimal("1000.00"),
            currency=self.ils, partner=self.supplier, status="Draft",
            direction="Outgoing", supplier_payment=payment,
            bank_name="بنك القدس", due_date="2026-09-30",
        )
        journals_before = JournalHeader.objects.filter(tenant=self.tenant).count()

        with self.assertRaises(ValidationError) as ctx:
            transfer_cheque(cheque.pk, "withdraw", user=self.user)

        self.assertIn("ما زال مسودةً", str(ctx.exception))
        cheque.refresh_from_db()
        self.assertEqual(cheque.status, "Draft")
        self.assertEqual(
            JournalHeader.objects.filter(tenant=self.tenant).count(),
            journals_before)

    def test_an_orphan_draft_cheque_keeps_its_legacy_path(self):
        """الورقة اليتيمة (بلا مستند) تتحرك بلا قيد كما كانت — لا تُمسّ."""
        cheque = self._cheque("DRAFT-2", status="Draft", linked=False)
        transfer_cheque(cheque.pk, "withdraw", user=self.user)
        cheque.refresh_from_db()
        self.assertEqual(cheque.status, "Collected")

    # ── 5. تاريخ الحركة ────────────────────────────────────────────────────

    def test_a_future_movement_date_is_refused(self):
        from django.utils import timezone
        cheque = self._cheque("DATE-1")
        tomorrow = timezone.localdate() + __import__("datetime").timedelta(days=1)

        with self.assertRaises(ValidationError) as ctx:
            transfer_cheque(cheque.pk, "collect", user=self.user,
                            movement_date=str(tomorrow))
        self.assertIn("المستقبل", str(ctx.exception))

    def test_a_movement_cannot_predate_the_last_posted_movement(self):
        bank = Bank.objects.create(tenant=self.tenant, name="بنك فلسطين")
        ledger = Account.objects.create(
            tenant=self.tenant, code="1102-9", name="جاري — أستاذ",
            account_type="Asset",
            parent=Account.objects.get(tenant=self.tenant, code="1102"))
        ba = BankAccount.objects.create(
            tenant=self.tenant, bank=bank, name="الجاري", currency=self.ils,
            account=ledger, is_active=True)
        cheque = self._cheque("DATE-2")
        transfer_cheque(cheque.pk, "deposit", user=self.user,
                        movement_date="2026-08-10", bank_account_id=ba.pk)

        with self.assertRaises(ValidationError) as ctx:
            transfer_cheque(cheque.pk, "collect", user=self.user,
                            movement_date="2026-08-01")
        self.assertIn("أسبق", str(ctx.exception))
