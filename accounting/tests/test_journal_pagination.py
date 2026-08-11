"""عقد الترقيم على دفتر اليومية.

صيانة الأداء 2026-07 جعلته اختيارياً (بلا ?page= مصفوفة خام)؛ المرحلة 5 /
P0-5 (2026-08-11) قلبت العقد: الترقيم **إلزامي** — بلا ?page= تُرجَع الصفحة
الأولى داخل غلاف {results, count, next}، ومستهلكو الواجهة حُدِّثوا معه في
نفس الـcommit (شاشة القيد وDocumentPaymentsTab).
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import JournalHeader
from tenants.services import create_company


class JournalPaginationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="pgowner", password="x")
        cls.tenant = create_company("شركة الترقيم", cls.owner)
        for i in range(7):
            JournalHeader.objects.create(
                tenant=cls.tenant, transaction_date=f"2026-06-{i + 1:02d}",
                description=f"قيد {i + 1}",
            )

    def _get(self, url):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(url, HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        assert res.status_code == 200, f"{url} → {res.status_code}: {res.content[:200]}"
        return res.json()

    def test_without_page_returns_first_page_envelope(self):
        # P0-5: الترقيم إلزامي — بلا ?page= غلافٌ بالصفحة الأولى، لا مصفوفة خام.
        data = self._get("/api/accounting/journals/")
        assert isinstance(data, dict)
        assert data["count"] == 7
        assert len(data["results"]) == 7

    def test_with_page_returns_drf_envelope(self):
        data = self._get("/api/accounting/journals/?page=1&page_size=3")
        assert isinstance(data, dict)
        assert data["count"] == 7
        assert len(data["results"]) == 3
        assert data["next"] is not None

    def test_last_page_has_no_next(self):
        data = self._get("/api/accounting/journals/?page=3&page_size=3")
        assert len(data["results"]) == 1
        assert data["next"] is None
