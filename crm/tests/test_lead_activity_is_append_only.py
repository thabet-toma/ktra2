"""سجلُّ التواصل لا يُعدَّل ولا يُحذَف — `PUT`/`PATCH`/`DELETE` تردّ 405 بنصٍّ عربيّ."""
from rest_framework.test import APIClient, APITestCase

from crm.models import LeadPhone
from crm.services import create_lead

from ._helpers import make_staff_employee


class LeadActivityAppendOnlyTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.employee = make_staff_employee("activity-owner")
        self.lead = create_lead(store_name="محل النشاط", phones=[{"raw": "0506666666", "kind": LeadPhone.Kind.PRIMARY}])
        self.lead.assigned_to = self.employee
        self.lead.save(update_fields=["assigned_to"])
        self.client.force_authenticate(user=self.user)
        create_res = self.client.post(
            f"/api/platform/crm/leads/{self.lead.pk}/activities/",
            {"kind": "note", "body": "أوّل تواصل"}, format="json",
        )
        self.assertEqual(create_res.status_code, 201, create_res.content)

    def test_put_is_rejected(self):
        res = self.client.put(
            f"/api/platform/crm/leads/{self.lead.pk}/activities/", {"body": "تعديل"}, format="json",
        )
        self.assertEqual(res.status_code, 405, res.content)
        self.assertEqual(res.json()["detail"], "سجلُّ التواصل لا يُعدَّل ولا يُحذَف.")

    def test_patch_is_rejected(self):
        res = self.client.patch(
            f"/api/platform/crm/leads/{self.lead.pk}/activities/", {"body": "تعديل"}, format="json",
        )
        self.assertEqual(res.status_code, 405, res.content)

    def test_delete_is_rejected(self):
        res = self.client.delete(f"/api/platform/crm/leads/{self.lead.pk}/activities/")
        self.assertEqual(res.status_code, 405, res.content)

    def test_record_still_readable_after_rejected_writes(self):
        self.client.put(f"/api/platform/crm/leads/{self.lead.pk}/activities/", {}, format="json")
        res = self.client.get(f"/api/platform/crm/leads/{self.lead.pk}/activities/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.json()), 1)
