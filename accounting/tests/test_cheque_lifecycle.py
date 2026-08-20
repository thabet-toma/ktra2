"""P-H-4 / CHQ-1: إنفاذ آلة حالات الشيك — جدولا الخدمات لكل اتجاه.

كان هذا الملف يختبر `Cheque.change_status` — جدول انتقالات ثانٍ في الموديل
يناقض جدول الخدمات (كان يسمح `Bounced → Under_Collection` بينما الخدمات لا)
وميتٌ إنتاجياً: لا مستدعي له خارج هذا الملف، لأن الحالة تتغير حصراً عبر
`transfer_cheque` التي ترحّل القيد وتكتب الحركة. حُذف الجدولان معاً وأُعيد
الاختبار على المسار الحيّ.

الشيك هنا **يتيم** (بلا فاتورة ولا سند) عمداً: هذا يعزل آلة الحالات عن
الترحيل — مسار legacy قائم ومقصود، حركةٌ بلا قيد مع تحذير في اللوغ.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import Cheque, ChequeMovement
from accounting.services import (
    INCOMING_TRANSITIONS, OUTGOING_TRANSITIONS, transfer_cheque,
)
from partners.models import Partner
from tenants.models import Currency, Tenant


class ChequeLifecycleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=120, CompanyName="Chq Life")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="Chq Partner",
            partner_type="Customer",
        )

    def setUp(self):
        self.cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number="CHQ-001",
            amount=1000, currency=self.currency,
            partner=self.partner, status="Draft",
            direction="Incoming",
        )

    def _move(self, movement_type):
        return transfer_cheque(self.cheque.pk, movement_type)

    def test_draft_to_under_collection_valid(self):
        self._move("deposit")
        self.cheque.refresh_from_db()
        self.assertEqual(self.cheque.status, "Under_Collection")
        self.assertTrue(ChequeMovement.objects.filter(
            cheque=self.cheque, movement_type="deposit").exists())

    def test_draft_to_received_valid(self):
        """CHQ-1: «مستلَم» — الورقة في اليد قبل إيداعها."""
        self._move("receive")
        self.cheque.refresh_from_db()
        self.assertEqual(self.cheque.status, "Received")

    def test_invalid_transition_raises(self):
        with self.assertRaises(ValidationError):
            self._move("collect")

    def test_collected_is_terminal(self):
        self._move("deposit")
        self._move("collect")
        self.cheque.refresh_from_db()
        self.assertEqual(self.cheque.status, "Collected")
        with self.assertRaises(ValidationError):
            self._move("bounce")

    def test_bounced_reopens_through_redeposit_only(self):
        """CHQ-1: العودة من الارتداد اسمها `redeposit` ولها قيدها.

        جدول الموديل المحذوف كان يسمح `Bounced → Under_Collection` بلا حركة
        معرَّفة ولا قيد؛ جدول الخدمات لم يكن يسمح بها إطلاقاً.
        """
        self._move("deposit")
        self._move("bounce")
        self.cheque.refresh_from_db()
        self.assertEqual(self.cheque.status, "Bounced")
        with self.assertRaises(ValidationError):
            self._move("deposit")
        self._move("redeposit")
        self.cheque.refresh_from_db()
        self.assertEqual(self.cheque.status, "Under_Collection")

    def test_returned_is_terminal(self):
        self._move("deposit")
        self._move("bounce")
        self._move("return_to_customer")
        self.cheque.refresh_from_db()
        self.assertEqual(self.cheque.status, "Returned")
        with self.assertRaises(ValidationError):
            self._move("redeposit")

    def test_movement_row_written_for_every_transition(self):
        self._move("deposit")
        self._move("bounce")
        movements = ChequeMovement.objects.filter(cheque=self.cheque)
        self.assertEqual(movements.count(), 2)

    def test_outgoing_cheque_cannot_be_deposited_or_endorsed(self):
        """CHQ-1: جدول لكل اتجاه — «إيداع» شيك صادر بلا معنى وكان مسموحاً."""
        outgoing = Cheque.objects.create(
            tenant=self.tenant, cheque_number="CHQ-OUT-1",
            amount=1000, currency=self.currency, partner=self.partner,
            status="Draft", direction="Outgoing",
        )
        with self.assertRaises(ValidationError):
            transfer_cheque(outgoing.pk, "deposit")
        outgoing.status = "Under_Collection"
        outgoing.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            transfer_cheque(outgoing.pk, "endorse")

    def test_the_two_tables_are_the_single_source(self):
        """كل حالة في `STATUS_CHOICES` لها صفّ في جدولَي الاتجاهين.

        حارس ضد الحالة اليتيمة: حالةٌ تُضاف للموديل بلا صفّ في الجدول تجعل
        `transitions_for(...).get(status)` تعيد فراغاً — فيصير الشيك عالقاً
        بلا مخرج ولا رسالة تشرح لماذا.
        """
        statuses = {code for code, _label in Cheque.STATUS_CHOICES}
        self.assertEqual(statuses - set(INCOMING_TRANSITIONS), set())
        self.assertEqual(statuses - set(OUTGOING_TRANSITIONS), set())
