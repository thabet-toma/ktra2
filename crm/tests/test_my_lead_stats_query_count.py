"""عدّادات الموظف، ومنها المتأخر، تبقى استعلامًا مجمّعًا واحدًا."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from crm.models import LeadPhone
from crm.services import create_lead

from ._helpers import make_staff_employee


class MyLeadStatsQueryCountTest(TestCase):
    def test_overdue_count_uses_the_existing_single_aggregate_query(self):
        user, employee = make_staff_employee("my-stats-owner")
        lead = create_lead(
            store_name="موعد متأخر",
            phones=[{"raw": "0522000001", "kind": LeadPhone.Kind.PRIMARY}],
        )
        lead.assigned_to = employee
        lead.next_follow_up_at = timezone.now() - timedelta(days=1)
        lead.save(update_fields=["assigned_to", "next_follow_up_at"])

        client = APIClient()
        client.force_authenticate(user=user)
        with self.assertNumQueries(2):
            response = client.get("/api/platform/crm/stats/me/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["overdue"], 1)
