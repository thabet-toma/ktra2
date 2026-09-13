"""اقتراحُ عميلٍ من موظّف — `pending` ولا يظهر في المخزن حتى يعتمده المدير."""
from rest_framework.test import APIClient, APITestCase

from crm.models import Lead

from ._helpers import make_manager, make_staff_employee


class LeadSuggestionTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = make_manager()
        self.employee_user, self.employee = make_staff_employee("suggest-employee")

    def _suggest(self):
        self.client.force_authenticate(user=self.employee_user)
        return self.client.post(
            "/api/platform/crm/leads/",
            {
                "store_name": "محلٌّ مقترَح",
                "phones": [{"raw": "0505555555", "kind": "primary"}],
            },
            format="json",
        )

    def test_employee_suggestion_is_pending_and_hidden_from_the_pool(self):
        res = self._suggest()
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["approval_status"], Lead.Approval.PENDING)
        lead_id = res.json()["id"]

        pool = self.client.get("/api/platform/crm/leads/", {"scope": "pool"})
        self.assertNotIn(lead_id, [row["id"] for row in pool.json()])

    def test_manager_approval_makes_it_visible(self):
        lead_id = self._suggest().json()["id"]

        self.client.force_authenticate(user=self.manager)
        approve_res = self.client.post(f"/api/platform/crm/leads/{lead_id}/approve/")
        self.assertEqual(approve_res.status_code, 200, approve_res.content)
        self.assertEqual(approve_res.json()["approval_status"], Lead.Approval.APPROVED)

        pool = self.client.get("/api/platform/crm/leads/", {"scope": "pool"})
        self.assertIn(lead_id, [row["id"] for row in pool.json()])

    def test_rejection_saves_the_reason(self):
        lead_id = self._suggest().json()["id"]

        self.client.force_authenticate(user=self.manager)
        reject_res = self.client.post(
            f"/api/platform/crm/leads/{lead_id}/reject/", {"reason": "رقمٌ وهميّ"}, format="json",
        )
        self.assertEqual(reject_res.status_code, 200, reject_res.content)
        self.assertEqual(reject_res.json()["approval_status"], Lead.Approval.REJECTED)
        self.assertEqual(reject_res.json()["rejection_reason"], "رقمٌ وهميّ")
