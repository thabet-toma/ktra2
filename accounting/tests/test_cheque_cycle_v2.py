"""CHQ-1 — آلة حالات الشيك الجديدة: «مستلَم» وقيد الإيداع والتظهير والإلغاء.

قبل الإصلاح:
- **لا حالة «مستلَم»** — الورقة في اليد والورقة في البنك حالة واحدة، فقيد
  الإيداع الذي تطلبه كل الأنظمة المهنية (دفترة/الأصيل) لا وجود له أصلاً.
- **`redeposit` مستحيل**: مرجع القيد كان `(CHEQUE_<MOVE>, cheque_id)` فارتدادٌ
  ثانٍ بعد إعادة الإيداع يعيد قيد الارتداد الأول صامتاً — الذمّة تُعاد مرة
  واحدة والمرة الثانية تضيع.
- **حركة على شيك سنده غير مرحّل مسموحة**: `cheque_is_linked_to_document` يفحص
  الـFK لا `is_posted`، فيمكن تحصيل شيك لم يدخل الدفاتر ⇒ 1107 سالب.
- **الريزولفر يطابق بالاسم**: `name__icontains="شيكات"` مع وجود حسابَي شيكات
  يعيد أيّهما اتفق — قيد إيداع 1109 ÷ 1109 يتعادل فلا تكشفه أي موازنة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase
from django.test import TestCase

from accounting.models import Account, Cheque, ChequeMovement, JournalHeader
from accounting.services import (
    create_fiscal_year,
    transfer_cheque,
)
from partners.models import Partner
from sales.models import (
    CustomerPayment, SalesInvoice, SalesSettings, SupplierPayment,
)
from tenants.models import Currency
from tenants.services import create_company


class ChequeCycleV2Test(APITestCase):
    """الدورة الجديدة عبر `transfer_cheque` — كل انتقال بقيده المحدَّد."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqv2", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة دورة الشيك", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الدورة", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الدورة", partner_type="Supplier")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.uc_acc = Account.objects.get(tenant=cls.tenant, code="1107")
        cls.payable_acc = Account.objects.get(tenant=cls.tenant, code="2111")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="V2-INV-1", customer=cls.customer,
            currency=cls.ils, invoice_date="2026-06-11",
            status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("500.00"),
        )

    def _in_hand_account(self):
        return Account.objects.get(tenant=self.tenant, code="1109")

    def _incoming(self, status="Received", amount="500.00"):
        return Cheque.objects.create(
            tenant=self.tenant, cheque_number=f"IN-{Cheque.objects.count() + 1}",
            amount=Decimal(amount), currency=self.ils, partner=self.customer,
            status=status, direction="Incoming", sales_invoice=self.invoice,
        )

    def _posted_supplier_payment(self):
        return SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.supplier, currency=self.ils,
            payment_date="2026-06-11", amount=Decimal("400.00"),
            cash_or_bank_account=self.cash, is_posted=True,
        )

    def _outgoing(self, status="Under_Collection"):
        return Cheque.objects.create(
            tenant=self.tenant, cheque_number=f"OUT-{Cheque.objects.count() + 1}",
            amount=Decimal("400.00"), currency=self.ils, partner=self.supplier,
            status=status, direction="Outgoing",
            supplier_payment=self._posted_supplier_payment(),
        )

    @staticmethod
    def _lines(journal):
        return {l.account_id: (l.debit, l.credit) for l in journal.lines.all()}

    # ── 1) قيد الإيداع من «مستلَم» ─────────────────────────────
    def test_deposit_from_received_posts_1107_against_1109(self):
        """الإيداع الذي طلبه المالك: الورقة تنتقل من المحفظة إلى البنك بقيد."""
        chq = self._incoming(status="Received")
        transfer_cheque(chq.pk, "deposit", user=self.user,
                        movement_date="2026-06-11")
        chq.refresh_from_db()
        assert chq.status == "Under_Collection"

        movement = ChequeMovement.objects.get(cheque=chq, movement_type="deposit")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_DEPOSIT",
            reference_id=movement.pk)
        lines = self._lines(jh)
        assert lines[self.uc_acc.pk] == (Decimal("500.00"), Decimal("0.00"))
        assert lines[self._in_hand_account().pk] == (Decimal("0.00"), Decimal("500.00"))
        assert movement.journal_id == jh.pk

    # ── 2) التظهير يخفض ذمة المورد المستفيد ───────────────────
    def test_endorse_lowers_the_beneficiary_supplier_balance(self):
        chq = self._incoming(status="Received")
        transfer_cheque(chq.pk, "endorse", user=self.user,
                        endorsed_to_id=self.supplier.pk,
                        movement_date="2026-06-11")
        chq.refresh_from_db()
        assert chq.status == "Endorsed"
        assert chq.endorsed_to_id == self.supplier.pk

        movement = ChequeMovement.objects.get(cheque=chq, movement_type="endorse")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_ENDORSE",
            reference_id=movement.pk)
        self.supplier.refresh_from_db()
        lines = self._lines(jh)
        # ذمة المورد تنخفض: حسابه مدين بمبلغ الشيك، مقابل حساب المحفظة
        assert lines[self.supplier.linked_account_id] == (Decimal("500.00"), Decimal("0.00"))
        assert lines[self._in_hand_account().pk] == (Decimal("0.00"), Decimal("500.00"))
        # الشريك يُوسم على سطر الذمم وحده (نفس قاعدة الارتداد)
        partners = {l.account_id: l.partner_id for l in jh.lines.all()}
        assert partners[self.supplier.linked_account_id] == self.supplier.pk
        assert partners[self._in_hand_account().pk] is None

    # ── 3) إعادة الإيداع ثم ارتداد ثانٍ = قيدا ارتداد منفصلان ──
    def test_redeposit_then_second_bounce_posts_two_separate_journals(self):
        """مفتاح الـidempotency على الحركة لا على الشيك.

        بمفتاح الشيك كان القيد الثاني يُختصر إلى الأول صامتاً: الذمّة تعود
        مرة واحدة بينما الشيك ارتدّ مرتين.
        """
        chq = self._incoming(status="Under_Collection")
        transfer_cheque(chq.pk, "bounce", user=self.user, movement_date="2026-06-11")
        transfer_cheque(chq.pk, "redeposit", user=self.user, movement_date="2026-06-12")
        chq.refresh_from_db()
        assert chq.status == "Under_Collection"
        transfer_cheque(chq.pk, "bounce", user=self.user, movement_date="2026-06-13")
        chq.refresh_from_db()
        assert chq.status == "Bounced"

        bounces = JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="CHEQUE_BOUNCE")
        assert bounces.count() == 2, "الارتداد الثاني أعاد قيد الأول بدل قيد جديد"
        # كل قيد ارتداد يعيد الذمّة كاملة على العميل
        self.customer.refresh_from_db()
        total_ar_debit = sum(
            l.debit for jh in bounces for l in jh.lines.all()
            if l.account_id == self.customer.linked_account_id
        )
        assert total_ar_debit == Decimal("1000.00")
        # وإعادة الإيداع بينهما قيدها الخاص: 1107 مدين ÷ ذمم العميل دائن
        redeposit = ChequeMovement.objects.get(cheque=chq, movement_type="redeposit")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_REDEPOSIT",
            reference_id=redeposit.pk)
        lines = self._lines(jh)
        assert lines[self.uc_acc.pk] == (Decimal("500.00"), Decimal("0.00"))
        assert lines[self.customer.linked_account_id] == (Decimal("0.00"), Decimal("500.00"))

    # ── 4) إلغاء شيك صادر يعيد ذمة المورد ─────────────────────
    def test_cancel_outgoing_restores_the_supplier_balance(self):
        chq = self._outgoing()
        transfer_cheque(chq.pk, "cancel", user=self.user, movement_date="2026-06-11")
        chq.refresh_from_db()
        assert chq.status == "Cancelled"

        movement = ChequeMovement.objects.get(cheque=chq, movement_type="cancel")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_CANCEL",
            reference_id=movement.pk)
        self.supplier.refresh_from_db()
        lines = self._lines(jh)
        assert lines[self.payable_acc.pk] == (Decimal("400.00"), Decimal("0.00"))
        assert lines[self.supplier.linked_account_id] == (Decimal("0.00"), Decimal("400.00"))

    # ── 5) رفض أي حركة على شيك سنده غير مرحّل ─────────────────
    def test_movement_on_an_unposted_document_is_rejected(self):
        """`cheque_is_linked_to_document` كان يفحص الـFK لا `is_posted`.

        فشيكٌ داخل سند لم يُرحَّل بعد كان يُحصَّل بقيد يدائن 1107 الذي لم
        يُدَّن أصلاً ⇒ الحساب سالب والعميل يبقى مديناً.
        """
        payment = CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, currency=self.ils,
            payment_date="2026-06-11", amount=Decimal("500.00"),
            cash_or_bank_account=self.cash, is_posted=False,
        )
        chq = Cheque.objects.create(
            tenant=self.tenant, cheque_number="IN-UNPOSTED",
            amount=Decimal("500.00"), currency=self.ils, partner=self.customer,
            status="Under_Collection", direction="Incoming",
            customer_payment=payment,
        )
        with self.assertRaises(ValidationError):
            transfer_cheque(chq.pk, "collect", user=self.user,
                            movement_date="2026-06-11")
        chq.refresh_from_db()
        assert chq.status == "Under_Collection"
        assert not ChequeMovement.objects.filter(cheque=chq).exists()


class ChequeAccountResolversTest(TestCase):
    """الريزولفران صريحان — لا مطابقة بالاسم بين حسابَي شيكات.

    الخطر المغلق هنا: بحساب «شيكات في المحفظة» الجديد صار في الشجرة حسابا أصل
    اسم كليهما يحوي «شيكات»، فالـfallback القديم `name__icontains="شيكات"`
    يعيد أيّهما اتفق. قيد إيداع طرفاه نفس الحساب **يتعادل** فلا تكشفه أي
    موازنة ولا أي تأكيد رصيد — يبقى صامتاً إلى أن يُقرأ كشف الحساب بالعين.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqres", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الريزولفر", cls.user)

    def test_both_cheque_accounts_resolve_to_their_own_code(self):
        from accounting.services import (
            _resolve_cheque_in_hand_account,
            _resolve_cheque_under_collection_account,
        )
        # الشجرة المعيارية تحمل الحسابين ولا إعدادات مبيعات تحسم أيّاً منهما
        assert Account.objects.filter(tenant=self.tenant, code="1107").exists()
        assert Account.objects.filter(tenant=self.tenant, code="1109").exists()
        SalesSettings.objects.filter(tenant=self.tenant).update(
            default_cheques_under_collection_account=None)

        uc = _resolve_cheque_under_collection_account(self.tenant.TenantID)
        in_hand = _resolve_cheque_in_hand_account(self.tenant.TenantID)
        assert uc.code == "1107", f"برسم التحصيل حُلّ إلى {uc.code}"
        assert in_hand.code == "1109", f"المحفظة حُلّت إلى {in_hand.code}"
        assert uc.pk != in_hand.pk

    def test_tenant_with_only_the_in_hand_account_creates_1107_instead_of_picking_it(self):
        """شركة بلا 1107 يُنشأ لها الحساب — ولا يُلتقط 1109 أبداً.

        CHQ-4: كان هذا الاختبار يثبّت `ValidationError`. أُبدِل المعيار بعد
        إثبات أن الرمي خطأ: مسار ترحيل السند يُنشئ 1107 تلقائياً
        (`sales/services/calc.py` (`resolve_cheques_under_collection_account`))
        بينما مسار حركة الشيك كان يرمي — فشركةٌ بلا 1107 تُرحّل سندها بنجاح ثم
        تصطدم بجدار عند أول إيداع، بلا أي طريق من الشاشة. الخطر الذي حرسه
        الاختبار الأصلي (التقاط «شيكات في المحفظة» بمطابقة الاسم) يبقى محروساً
        هنا، وبصرامة أشدّ: الحساب المُعاد كوده 1107 وهو غير حساب المحفظة.
        """
        from accounting.services import _resolve_cheque_under_collection_account
        Account.objects.filter(tenant=self.tenant, code="1107").delete()
        in_hand = Account.objects.get(tenant=self.tenant, code="1109")
        assert Account.objects.filter(
            tenant=self.tenant, name__icontains="شيكات", account_type="Asset",
        ).exists(), "الشجرة يجب أن تبقى فيها «شيكات في المحفظة» ليكون الفخّ حقيقياً"

        acc = _resolve_cheque_under_collection_account(self.tenant.TenantID)

        assert acc.code == "1107", f"برسم التحصيل حُلّ إلى {acc.code}"
        assert acc.pk != in_hand.pk, "التُقط حساب المحفظة بدل إنشاء 1107"
