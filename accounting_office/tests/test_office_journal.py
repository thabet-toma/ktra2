"""القيدُ التلقائيُّ للدفعات والشطب في دفاتر المكتب (#284، الجزء أ).

**القواعدُ التي يسقط عندها الاختبار:**
1. دفعةٌ على زبونٍ له مسودّةٌ معتمدة ⇒ قيدٌ **متوازن**: مدينٌ حسابُ طريقة الدفع،
   دائنٌ الذمّمُ المدينة، و**وسمُ الطرف على سطر الذمّم وحده**.
2. حسابُ طريقة الدفع: نقدٌ ⇒ النقد · بنك/تحويل/بطاقة ⇒ البنك · شيك ⇒ الشيكات.
3. الشيكُ يسبق القيد: صفُّ `Cheque` بالقيمة الصحيحة على حساب الشيكات، وإعادةُ
   النداء لا تُكرّر شيكاً ولا قيداً (`idempotent` على `(النوع، المعرّف)`).
4. الشطبُ قيدُه المتوازن: مدينٌ حسابُ الشطب، دائنٌ الذمّمُ المدينة بوسم الطرف.
5. إطفاءُ `office_journal_enabled` ⇒ لا قيدَ ولا شيك، والدفعةُ تُنشأ عاديًّا.
6. فترةٌ مقفلة ⇒ **400 برسالة «مغلقة»** و**لا صفَّ دفعة** يُكتب ولا شيك — الذرّية.
7. كودُ حسابٍ خاطئ في الإعدادات ⇒ 400 يُسمّي المفتاحَ والكود.
8. زبونٌ بلا طرف ⇒ يُنشأ الطرفُ ويُربط مرّةً واحدة (نداءان ⇒ طرفٌ واحد).
9. `office_journal_writeoff_account` افتراضُه **فارغ** لأن الشجرة لا تحمل حساب
   ديونٍ معدومة — فالشطبُ يُرفض 400 باسم المفتاح حتى يقرّر المالك حسابَه.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalHeader
from accounting_office import office_journal, payments, services, settings_registry
from accounting_office.models import (
    FeeDraft,
    FeePayment,
    FeeWriteOff,
    OfficeClient,
    TaxCard,
)
from core.modules import invalidate_module_cache
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

BASE = "/api/accounting-office/"
PAYMENTS = f"{BASE}fees/payments/"
DRAFTS = f"{BASE}fees/drafts/"


def decimal_of(value) -> Decimal:
    """المبلغُ كما يصل من الـAPI أو من القيد — عشريٌّ أو نصّ، لا فرق."""
    return Decimal(str(value))


class OfficeJournalTestCase(APITestCase):
    """أساسٌ مشترك: مكتبٌ بقالب `accounting_office`، وزبونٌ ومسودّةٌ معتمدة."""

    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )[0]
        cls.owner = User.objects.create_user(username="journal_owner", password="x")
        cls.tenant = create_company("مكتب القيود", cls.owner, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)
        services.set_office_setting(cls.tenant, "tax_system", "PS")
        services.set_office_setting(cls.tenant, "office_size", "small")
        # أكوادُ الشجرة الافتراضية التي يحلّها القيد — تُقرأ مرّةً للاختبار كلّه.
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.bank = Account.objects.get(tenant=cls.tenant, code="1102")
        cls.receivable = Account.objects.get(tenant=cls.tenant, code="1103")
        cls.cheques = Account.objects.get(tenant=cls.tenant, code="1107")

    def setUp(self):
        self.client.force_authenticate(user=self.owner)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def make_client(self, name="زبون القيود"):
        client = OfficeClient.objects.create(tenant=self.tenant, name=name)
        TaxCard.objects.create(client=client)
        return client

    def make_draft(self, client, total):
        return FeeDraft.objects.create(
            tenant=self.tenant,
            client=client,
            year=2026,
            month=3,
            subtotal=Decimal(str(total)),
            total=Decimal(str(total)),
            status=FeeDraft.STATUS_APPROVED,
            approved_by=self.owner,
        )

    def post_payment(self, payload):
        return self.client.post(PAYMENTS, payload, format="json", **self.headers())

    def payment_of(self, client, amount, *, method="cash", paid_at="2026-05-01", **extra):
        payload = {
            "client": client.pk,
            "amount": amount,
            "method": method,
            "paid_at": paid_at,
        }
        payload.update(extra)
        res = self.post_payment(payload)
        self.assertEqual(res.status_code, 201, res.content)
        return FeePayment.objects.get(pk=res.data["id"]), res

    def journal_of(self, *, reference_type, reference_id):
        return JournalHeader.objects.get(
            tenant=self.tenant,
            reference_type=reference_type,
            reference_id=reference_id,
        )

    def config_write_off_account(self, code="5405"):
        """حسابُ ديونٍ معدومةٍ يصنعه المكتب — الشجرةُ المبذورة لا تحمله."""
        Account.objects.get_or_create(
            tenant=self.tenant,
            code=code,
            defaults={"name": "ديون معدومة", "account_type": "Expense"},
        )
        services.set_office_setting(self.tenant, "office_journal_writeoff_account", code)


class PaymentJournalTest(OfficeJournalTestCase):
    def test_a_cash_payment_posts_one_balanced_journal_tagged_on_receivable_only(self):
        client = self.make_client()
        self.make_draft(client, "300")

        payment, res = self.payment_of(client, "300.00")

        journal = self.journal_of(
            reference_type="office_fee_payment", reference_id=payment.pk,
        )
        self.assertTrue(journal.is_posted)
        self.assertEqual(journal.transaction_date, payment.paid_at)
        self.assertEqual(journal.created_by_id, self.owner.pk)
        self.assertIn(payment.receipt_number, journal.description)
        self.assertIn(client.name, journal.description)

        lines = list(journal.lines.all())
        self.assertEqual(len(lines), 2)
        cash_line = next(line for line in lines if line.account_id == self.cash.pk)
        receivable_line = next(
            line for line in lines if line.account_id == self.receivable.pk
        )
        self.assertEqual(decimal_of(cash_line.debit), Decimal("300.00"))
        self.assertEqual(decimal_of(cash_line.credit), Decimal("0.00"))
        self.assertEqual(decimal_of(receivable_line.debit), Decimal("0.00"))
        self.assertEqual(decimal_of(receivable_line.credit), Decimal("300.00"))
        totals = journal.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        self.assertEqual(totals["debit"], totals["credit"], "قيدٌ غير متوازن")

        # وسمُ الطرف على سطر الذمّم وحده — `post_journal` نفسه يرفض وسمَ غيره.
        partner = Partner.objects.get(tenant=self.tenant, pk=receivable_line.partner_id)
        self.assertEqual(partner.name, client.name)
        self.assertIsNone(cash_line.partner_id)

        # ونقطةُ الدفعات تقول إن القيد وقع — ردُّ الإنشاء وقائمةُ القراءة معاً.
        self.assertEqual(res.data["journal_entry"], journal.pk)
        listed = self.client.get(PAYMENTS, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        row = next(item for item in listed.data if item["id"] == payment.pk)
        self.assertEqual(row["journal_entry"], journal.pk)

    def test_each_payment_method_debits_its_own_money_account(self):
        """الطرقُ الأربع المعلَنة في النموذج: نقد · شيك · تحويل · بطاقة."""
        expected = {
            "cash": self.cash,
            "transfer": self.bank,
            "card": self.bank,
            "cheque": self.cheques,
        }
        for method, account in expected.items():
            with self.subTest(method=method):
                client = self.make_client(f"زبون {method}")
                payment, _res = self.payment_of(client, "50.00", method=method)
                journal = self.journal_of(
                    reference_type="office_fee_payment", reference_id=payment.pk,
                )
                debit_accounts = [
                    line.account_id
                    for line in journal.lines.filter(debit__gt=0)
                ]
                self.assertEqual(debit_accounts, [account.pk])
                credit_accounts = [
                    line.account_id
                    for line in journal.lines.filter(credit__gt=0)
                ]
                self.assertEqual(credit_accounts, [self.receivable.pk])

    def test_the_method_map_knows_a_bank_method_and_refuses_an_unknown_one(self):
        """`bank` في الخريطة بقرار التذكرة (طريقةُ مصرفٍ مستقبلية) — وليست اليوم
        قيمةً في `FEE_PAYMENT_METHOD_CHOICES`؛ والمجهولةُ تُرفض ولا تُخمَّن."""
        self.assertEqual(
            office_journal._method_account_key("bank"),
            office_journal.BANK_ACCOUNT_KEY,
        )
        with self.assertRaises(ValidationError):
            office_journal._method_account_key("crypto")


class ChequeJournalTest(OfficeJournalTestCase):
    def test_a_cheque_payment_creates_the_cheque_row_and_a_cheques_journal(self):
        client = self.make_client()

        payment, _res = self.payment_of(client, "250.00", method="cheque")

        cheque = Cheque.objects.get(
            tenant=self.tenant, cheque_number=payment.receipt_number,
        )
        self.assertEqual(decimal_of(cheque.amount), Decimal("250.00"))
        self.assertEqual(cheque.direction, "Incoming")
        self.assertEqual(cheque.status, "Draft")
        self.assertIsNone(cheque.due_date)
        self.assertEqual(
            cheque.partner_id, OfficeClient.objects.get(pk=client.pk).partner_id,
        )

        journal = self.journal_of(
            reference_type="office_fee_payment", reference_id=payment.pk,
        )
        line = journal.lines.get(account_id=self.cheques.pk)
        self.assertEqual(decimal_of(line.debit), Decimal("250.00"))

    def test_a_second_call_neither_duplicates_the_cheque_nor_the_journal(self):
        client = self.make_client()
        payment, _res = self.payment_of(client, "250.00", method="cheque")
        first = self.journal_of(
            reference_type="office_fee_payment", reference_id=payment.pk,
        )

        again = office_journal.post_payment_journal(payment, actor=self.owner)

        self.assertEqual(again.pk, first.pk)
        self.assertEqual(
            JournalHeader.objects.filter(
                tenant=self.tenant,
                reference_type="office_fee_payment",
                reference_id=payment.pk,
            ).count(),
            1,
        )
        self.assertEqual(
            Cheque.objects.filter(
                tenant=self.tenant, cheque_number=payment.receipt_number,
            ).count(),
            1,
        )


class WriteOffJournalTest(OfficeJournalTestCase):
    def test_a_write_off_posts_a_balanced_journal_against_the_writeoff_account(self):
        self.config_write_off_account()
        client = self.make_client()
        draft = self.make_draft(client, "300")
        self.payment_of(client, "100.00")

        write_off = payments.write_off_fee_draft(
            draft, amount="80.00", reason="تنازلٌ عن المتبقّي", actor=self.owner,
        )

        journal = self.journal_of(
            reference_type="office_fee_writeoff", reference_id=write_off.pk,
        )
        # التاريخُ المحلّيُّ للشطب لا `.date()` على لحظةٍ بـUTC (تنزلق يوماً
        # بين منتصف الليل والثانية صباحاً بتوقيت المكتب).
        self.assertEqual(
            journal.transaction_date, timezone.localdate(write_off.created_at),
        )
        lines = list(journal.lines.all())
        writeoff_line = next(
            line for line in lines if line.account.code == "5405"
        )
        receivable_line = next(
            line for line in lines if line.account_id == self.receivable.pk
        )
        self.assertEqual(decimal_of(writeoff_line.debit), Decimal("80.00"))
        self.assertEqual(decimal_of(receivable_line.credit), Decimal("80.00"))
        self.assertIsNone(writeoff_line.partner_id)
        self.assertEqual(
            receivable_line.partner_id,
            OfficeClient.objects.get(pk=client.pk).partner_id,
        )
        totals = journal.lines.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        self.assertEqual(totals["debit"], totals["credit"])

    def test_the_writeoff_account_has_no_default_so_the_write_off_is_refused(self):
        """الشجرةُ المبذورة لا تحمل حسابَ ديونٍ معدومة — القرارُ للمالك.

        والرفضُ عند **إنشاء الصفّ** لا بعد قراءة الكشف: `ValidationError` باسم
        المفتاح من `office_journal._account`، فالشطبُ لا يُكتب بلا قيده.
        """
        self.assertEqual(
            services.resolve_setting(self.tenant, "office_journal_writeoff_account"),
            "",
        )
        client = self.make_client()
        draft = self.make_draft(client, "300")

        with self.assertRaises(ValidationError) as ctx:
            payments.write_off_fee_draft(
                draft, amount="10.00", reason="تنازل", actor=self.owner,
            )

        self.assertIn("office_journal_writeoff_account", ctx.exception.message_dict)
        self.assertEqual(FeeWriteOff.objects.count(), 0)


class SettingGateTest(OfficeJournalTestCase):
    def test_the_default_cheque_code_is_the_seeded_under_collection_account(self):
        """`1107` ليس رقماً مخترَعاً هنا — سطرُه في بذرة الشجرة التشغيلية،
        وحسابُه موجودٌ في شجرة مكتبٍ مبنيٍّ بقالب `accounting_office`."""
        from tenants.services import COA_DATA, OPERATIONAL_ACCOUNT_CODES

        code = next(
            row[0] for row in COA_DATA if "شيكات برسم التحصيل" in row[1]
        )
        self.assertEqual(settings_registry.CHEQUE_UNDER_COLLECTION_CODE, code)
        self.assertIn(code, OPERATIONAL_ACCOUNT_CODES)
        self.assertTrue(
            Account.objects.filter(tenant=self.tenant, code=code, is_active=True).exists(),
        )

    def test_the_receivable_account_carries_the_partner_tag_not_the_money_account(self):
        """`post_journal` يرفض وسمَ طرفٍ على غير ذمّته — فالقيدُ المتوازن وحده
        لا يكفي: الوسمُ هو ما يجعل كشفَ الطرف يقرأ الدفعة."""
        client = self.make_client()
        payment, _res = self.payment_of(client, "40.00")
        journal = self.journal_of(
            reference_type="office_fee_payment", reference_id=payment.pk,
        )
        tagged = [line for line in journal.lines.all() if line.partner_id]
        self.assertEqual(len(tagged), 1)
        self.assertEqual(tagged[0].account_id, self.receivable.pk)

    def test_disabling_the_journal_leaves_no_journal_and_no_cheque(self):
        services.set_office_setting(self.tenant, "office_journal_enabled", False)
        client = self.make_client()
        self.make_draft(client, "300")

        payment, res = self.payment_of(client, "100.00", method="cheque")

        self.assertEqual(FeePayment.objects.filter(tenant=self.tenant).count(), 1)
        self.assertFalse(JournalHeader.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(Cheque.objects.filter(tenant=self.tenant).exists())
        self.assertIsNone(res.data["journal_entry"])
        self.assertEqual(payment.receipt_number, "2026-00001")

    def test_a_wrong_account_code_is_a_400_naming_the_setting_and_the_code(self):
        services.set_office_setting(self.tenant, "office_journal_cash_account", "9999")
        client = self.make_client()
        self.make_draft(client, "300")

        res = self.post_payment({
            "client": client.pk,
            "amount": "100.00",
            "method": "cash",
            "paid_at": "2026-05-01",
        })

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("office_journal_cash_account", res.data)
        self.assertIn("9999", str(res.data))
        self.assertEqual(FeePayment.objects.filter(tenant=self.tenant).count(), 0)

    def test_a_disabled_account_is_a_400_naming_the_setting(self):
        """كودٌ موجودٌ لكن الحسابُ معطَّل — 400 يسمّي المفتاحَ ويقول «معطَّل»."""
        inactive = Account.objects.create(
            tenant=self.tenant,
            code="1199",
            name="نقدٌ معطَّل",
            account_type="Asset",
            is_active=False,
        )
        services.set_office_setting(
            self.tenant, "office_journal_cash_account", inactive.code,
        )
        client = self.make_client()
        self.make_draft(client, "300")

        res = self.post_payment({
            "client": client.pk,
            "amount": "100.00",
            "method": "cash",
            "paid_at": "2026-05-01",
        })

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("office_journal_cash_account", res.data)
        self.assertIn("معطَّل", str(res.data))
        self.assertEqual(FeePayment.objects.filter(tenant=self.tenant).count(), 0)


class ClosedPeriodTest(OfficeJournalTestCase):
    def test_a_closed_period_is_a_400_that_writes_no_payment_and_no_cheque(self):
        client = self.make_client()
        self.make_draft(client, "300")
        day = datetime.date(2026, 5, 15)
        closed = FiscalPeriod.objects.filter(
            tenant=self.tenant, start_date__lte=day, end_date__gte=day,
        ).update(status="Closed", is_closed=True)
        self.assertEqual(closed, 1, "لا فترةَ مالية تغطي تاريخ الاختبار")
        before = FeePayment.objects.filter(tenant=self.tenant).count()

        res = self.post_payment({
            "client": client.pk,
            "amount": "100.00",
            "method": "cheque",
            "paid_at": day.isoformat(),
        })

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("مغلقة", str(res.data))
        # الصفُّ كلُّه يرجع: لا دفعةً بلا قيد — العددُ قبل الطلب وبعده واحد.
        after = FeePayment.objects.filter(tenant=self.tenant).count()
        self.assertEqual(after, before, f"قبل الطلب: {before} — وبعده: {after}")
        self.assertFalse(Cheque.objects.filter(tenant=self.tenant).exists())


class PartnerLinkTest(OfficeJournalTestCase):
    def test_a_client_without_a_partner_gets_one_partner_linked_once(self):
        client = self.make_client("منشأة بلا طرف")
        self.assertIsNone(client.partner_id)

        first = office_journal.partner_for(client)
        second = office_journal.partner_for(OfficeClient.objects.get(pk=client.pk))

        self.assertEqual(first.pk, second.pk, "طرفان لزبونٍ واحد")
        self.assertEqual(first.partner_type, "Customer")
        self.assertEqual(first.tenant_id, self.tenant.pk)
        self.assertEqual(first.name, client.name)
        self.assertEqual(
            Partner.objects.filter(tenant=self.tenant, name=client.name).count(), 1,
        )
        self.assertEqual(
            OfficeClient.objects.get(pk=client.pk).partner_id, first.pk,
        )

    def test_a_payment_links_the_partner_and_reuses_it_on_the_next_one(self):
        client = self.make_client()
        self.payment_of(client, "10.00", paid_at="2026-05-01")
        linked = OfficeClient.objects.get(pk=client.pk).partner_id
        self.assertIsNotNone(linked)

        self.payment_of(client, "10.00", paid_at="2026-05-02")

        self.assertEqual(OfficeClient.objects.get(pk=client.pk).partner_id, linked)
        self.assertEqual(Partner.objects.filter(tenant=self.tenant).count(), 1)
