"""Partner list/lookup bounds, filtering, isolation, and query regression tests."""
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from partners.models import Partner
from tenants.models import Tenant, UserCompanyMembership


class PartnerListPaginationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="partner_list_bounds", password="x")
        cls.tenant = Tenant.objects.create(
            TenantID=911, CompanyName="Partners A", SubscriptionPlan="Enterprise", Status="Active",
        )
        cls.other_tenant = Tenant.objects.create(
            TenantID=912, CompanyName="Partners B", SubscriptionPlan="Enterprise", Status="Active",
        )
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager", is_default=True,
        )
        for i in range(24):
            Partner.objects.create(
                tenant=cls.tenant,
                name=f"Target Partner {i:02d}" if i < 12 else f"Other Partner {i:02d}",
                partner_type="Supplier" if i % 2 == 0 else "Customer",
                phone=f"0599{i:04d}",
            )
        Partner.objects.create(
            tenant=cls.other_tenant, name="Target Partner Secret", partner_type="Supplier",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _list_query_count(self, page_size):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                f"/api/partners/?page=1&page_size={page_size}", **self.headers,
            )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertFalse(any("system_attachments" in q["sql"].lower() for q in captured))
        self.assertTrue(all("attachments" not in row for row in response.json()["results"]))
        return len(captured)

    def test_list_filters_before_bounding_and_has_constant_queries(self):
        response = self.client.get(
            "/api/partners/?page=1&page_size=3&search=Target&partner_type=Supplier",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        payload = response.json()
        self.assertEqual(payload["count"], 6)
        self.assertEqual(len(payload["results"]), 3)
        self.assertNotIn("Target Partner Secret", {row["name"] for row in payload["results"]})
        self.assertEqual(self._list_query_count(5), self._list_query_count(20))

    def test_lookup_is_raw_bounded_and_filterable(self):
        response = self.client.get(
            "/api/partners/lookup/?limit=2&partner_type=Customer&search=Target",
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        payload = response.json()
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 2)
        self.assertTrue(all(row["partner_type"] == "Customer" for row in payload))
        self.assertTrue(all("attachments" not in row for row in payload))
