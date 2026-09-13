"""استيرادُ دفعة — صفٌّ مكرَّرٌ يُسجَّل ولا يُسقِط الدفعة."""
from rest_framework.test import APIClient, APITestCase

from crm.models import Lead, LeadImportBatch, LeadPhone
from crm.services import create_lead

from ._helpers import make_manager, make_staff_employee


class LeadImportTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.manager = make_manager()
        self.client.force_authenticate(user=self.manager)
        self.existing = create_lead(
            store_name="محلٌّ سابق", phones=[{"raw": "0507777777", "kind": LeadPhone.Kind.PRIMARY}],
        )

    def test_batch_with_a_duplicate_creates_the_valid_row_and_records_the_duplicate(self):
        res = self.client.post(
            "/api/platform/crm/leads/import/",
            {
                "file_name": "دفعة.csv",
                "rows": [
                    {"store_name": "محلٌّ جديد", "phone": "0508888888"},
                    {"store_name": "محلٌّ مكرَّر", "phone": "0507777777"},
                ],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertEqual(data["created_count"], 1)
        self.assertEqual(data["duplicate_count"], 1)
        self.assertEqual(len(data["duplicates"]), 1)
        self.assertEqual(data["duplicates"][0]["existing_lead_id"], self.existing.pk)

        batch = LeadImportBatch.objects.get(pk=data["id"])
        self.assertEqual(batch.leads.count(), 1)  # الصفّ الجديد وحده مربوطٌ بالدفعة
        self.assertEqual(Lead.objects.count(), 2)  # القديم + الجديد، لا ثالث

    def test_invalid_row_is_counted_and_does_not_abort_the_batch(self):
        res = self.client.post(
            "/api/platform/crm/leads/import/",
            {"rows": [{"store_name": "", "phone": ""}, {"store_name": "محلٌّ صحيح", "phone": "0509999999"}]},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        data = res.json()
        self.assertEqual(data["invalid_count"], 1)
        self.assertEqual(data["created_count"], 1)

    def test_only_manager_can_import(self):
        employee_user, _ = make_staff_employee("import-employee")
        self.client.force_authenticate(user=employee_user)
        res = self.client.post("/api/platform/crm/leads/import/", {"rows": []}, format="json")
        self.assertEqual(res.status_code, 403, res.content)
