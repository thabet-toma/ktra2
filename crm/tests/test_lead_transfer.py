"""تحويلُ العميل — مباشرٌ من صاحبه/المدير، أو طلبٌ معلَّق يبتّ فيه المدير."""
from django.test import TestCase
from rest_framework.test import APIClient, APITestCase

from crm.models import LeadPhone, LeadTransfer
from crm.services import CrmValidationError, create_lead, request_lead_transfer, transfer_lead

from ._helpers import make_manager, make_staff_employee


class LeadTransferTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = make_manager()
        self.owner_user, self.owner = make_staff_employee("transfer-owner")
        self.other_user, self.other = make_staff_employee("transfer-target")
        self.bystander_user, self.bystander = make_staff_employee("transfer-bystander")
        self.lead = create_lead(store_name="محل التحويل", phones=[{"raw": "0504444444", "kind": LeadPhone.Kind.PRIMARY}])
        self.lead.assigned_to = self.owner
        self.lead.save(update_fields=["assigned_to"])

    def test_owner_can_transfer_directly(self):
        self.client.force_authenticate(user=self.owner_user)
        res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer/",
            {"to_employee": self.other.pk, "reason": "إجازة"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["status"], LeadTransfer.Status.APPROVED)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.other.pk)

    def test_empty_reason_is_rejected(self):
        self.client.force_authenticate(user=self.owner_user)
        res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer/",
            {"to_employee": self.other.pk, "reason": "   "}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.owner.pk)

    def test_bystander_requests_a_pending_transfer_that_manager_decides(self):
        self.client.force_authenticate(user=self.bystander_user)
        request_res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer-requests/",
            {"to_employee": self.bystander.pk, "reason": "أعرف صاحب المحل"}, format="json",
        )
        self.assertEqual(request_res.status_code, 201, request_res.content)
        self.assertEqual(request_res.json()["status"], LeadTransfer.Status.PENDING)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.owner.pk)  # لم يتغيّر الإسنادُ بعد

        transfer_id = request_res.json()["id"]
        self.client.force_authenticate(user=self.manager)
        decide_res = self.client.post(
            f"/api/platform/crm/transfer-requests/{transfer_id}/decide/",
            {"approve": True}, format="json",
        )
        self.assertEqual(decide_res.status_code, 200, decide_res.content)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to_id, self.bystander.pk)

    def test_owner_cannot_open_a_transfer_request_on_their_own_lead(self):
        """**البابُ المسدود**: طلبٌ من صاحب العميل يسدُّ تحويلَه هو.

        بلا هذا الحارس يُنشَأ طلبٌ معلَّقٌ من الموظّف إلى نفسِه، ثمّ يرفض
        `transfer_already_pending` كلَّ تحويلٍ لاحقٍ حتى يبتَّ أحدٌ فيه. والواجهةُ
        كانت تصل إلى هذه الحالة فعلاً: الملكيّةُ كانت تُستنبَط من `is_me` في دليل
        الزملاء، والدليلُ يستثني غيرَ `active`.
        """
        self.client.force_authenticate(user=self.owner_user)
        res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer-requests/",
            {"to_employee": self.other.pk, "reason": "أريد تسليمه"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(LeadTransfer.objects.filter(lead=self.lead).count(), 0)

        # وبابُه ما زال مفتوحاً: التحويلُ المباشرُ يعمل بعد الرفض.
        direct = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer/",
            {"to_employee": self.other.pk, "reason": "أريد تسليمه"}, format="json",
        )
        self.assertEqual(direct.status_code, 201, direct.content)

    def _pending_request(self) -> int:
        """طلبٌ معلَّقٌ من زميلٍ على عميل `self.owner` — يعيد معرّفَه."""
        self.client.force_authenticate(user=self.bystander_user)
        res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer-requests/",
            {"to_employee": self.bystander.pk, "reason": "أعرف صاحب المحل"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["id"]

    def _can_decide_for(self, user, transfer_id: int) -> bool:
        self.client.force_authenticate(user=user)
        res = self.client.get("/api/platform/crm/transfer-requests/")
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        rows = body.get("results", body) if isinstance(body, dict) else body
        row = next(row for row in rows if row["id"] == transfer_id)
        return row["can_decide"]

    def test_the_requester_is_told_he_cannot_decide_his_own_request(self):
        """212-Q2-ب: الصندوقُ كان يرسم «قبول» لطالبِ التحويل نفسِه، والخادمُ يردّ ٤٠٣."""
        transfer_id = self._pending_request()
        self.assertFalse(self._can_decide_for(self.bystander_user, transfer_id))
        self.assertTrue(self._can_decide_for(self.owner_user, transfer_id))
        self.assertTrue(self._can_decide_for(self.manager, transfer_id))

    def test_the_flag_follows_the_lead_not_the_row_it_was_written_on(self):
        """`from_employee` يسجّل مالكَ **يومِ الطلب**، والعميلُ قد ينتقل بعدَه.

        فاشتقاقُ الزرّ منه في الواجهة يرسمه لمن لم يعد يملك — ولذلك الحقلُ يأتي
        من الخادم مقروءاً من `lead.assigned_to` **الآن**.

        وثغرةٌ مجاورةٌ وُجدت أثناء كتابة هذا الاختبار ولم تُصلَح هنا (خارج نطاق
        التذكرة): `LeadTransferViewSet.get_queryset` يُضيَّق على
        `from_employee | to_employee`، فمن صار صاحبَ العميل بعد كتابة الطلب
        **لا يرى الطلبَ أصلاً** وإن كان `decide` يسمح له. أثرُها محصورٌ في حالةِ
        انتقالِ عميلٍ وطلبٌ معلَّقٌ عليه، والمديرُ يبتّ فيها.
        """
        transfer_id = self._pending_request()
        # الطالبُ نفسُه في الاختبار السابق يملك البتَّ لأنّه صاحبُ العميل؛ وهنا
        # يفقده **دون أن يتغيّر الصفُّ** — فالحقلُ يقرأ العميلَ لا الصفَّ.
        self.assertTrue(self._can_decide_for(self.owner_user, transfer_id))
        self.lead.assigned_to = self.other
        self.lead.save(update_fields=["assigned_to"])
        self.assertFalse(self._can_decide_for(self.owner_user, transfer_id))

    def test_a_settled_request_offers_no_decision_to_anyone(self):
        transfer_id = self._pending_request()
        self.client.force_authenticate(user=self.owner_user)
        decided = self.client.post(
            f"/api/platform/crm/transfer-requests/{transfer_id}/decide/", {"approve": False}, format="json",
        )
        self.assertEqual(decided.status_code, 200, decided.content)
        self.assertFalse(decided.json()["can_decide"])
        self.assertFalse(self._can_decide_for(self.manager, transfer_id))

    def test_old_transfer_record_stays_readable_after_transfer(self):
        self.client.force_authenticate(user=self.owner_user)
        first = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/transfer/",
            {"to_employee": self.other.pk, "reason": "إجازة"}, format="json",
        )
        transfer_id = first.json()["id"]

        self.client.force_authenticate(user=self.manager)
        res = self.client.get(f"/api/platform/crm/transfer-requests/{transfer_id}/")
        self.assertNotIn(res.status_code, (404,))


class LeadTransferServiceGuardTest(TestCase):
    """اختبارُ الخدمة مباشرةً — لا الـHTTP: المُسلسِل يتحقّق من السبب الفارغ هو
    أيضاً، فطلبٌ عبر الـview لا يثبت وحده أنّ الحارس **في الخدمة** حيٌّ فعلاً
    كما تنصّ التذكرة (§٥). هذا الاختبار يستدعي `transfer_lead` مباشرةً فيتجاوز
    المُسلسِل تماماً."""

    def test_service_refuses_a_request_from_the_owner_bypassing_the_view(self):
        """الحارسُ في الخدمة لا في الـview — كقاعدة الوحدة الرابعة."""
        _, owner = make_staff_employee("request-guard-owner")
        _, other = make_staff_employee("request-guard-target")
        lead = create_lead(store_name="محل الطلب", phones=[{"raw": "0504321777", "kind": LeadPhone.Kind.PRIMARY}])
        lead.assigned_to = owner
        lead.save(update_fields=["assigned_to"])

        with self.assertRaises(CrmValidationError):
            request_lead_transfer(lead=lead, to_employee=other, reason="سبب", actor=owner.user)
        self.assertEqual(LeadTransfer.objects.filter(lead=lead).count(), 0)

    def test_service_rejects_empty_reason_even_bypassing_the_serializer(self):
        _, owner = make_staff_employee("service-guard-owner")
        _, other = make_staff_employee("service-guard-target")
        lead = create_lead(store_name="محل خدمة", phones=[{"raw": "0504321000", "kind": LeadPhone.Kind.PRIMARY}])
        lead.assigned_to = owner
        lead.save(update_fields=["assigned_to"])

        with self.assertRaises(CrmValidationError):
            transfer_lead(
                lead=lead, to_employee=other, reason="   ", actor=owner.user,
                actor_employee=owner, is_manager=False,
            )
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to_id, owner.pk)
