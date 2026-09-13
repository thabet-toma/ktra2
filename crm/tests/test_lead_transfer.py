"""تحويلُ العميل — مباشرٌ من صاحبه/المدير، أو طلبٌ معلَّق يبتّ فيه المدير."""
from django.test import TestCase
from rest_framework.test import APIClient, APITestCase

from crm.models import LeadPhone, LeadTransfer
from crm.services import CrmValidationError, create_lead, transfer_lead

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
