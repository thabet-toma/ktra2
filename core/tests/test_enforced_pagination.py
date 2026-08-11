"""المرحلة 5 / P0-5: الترقيم الإلزامي على قوائم الفئة أ.

`OptionalPageNumberPagination` يعيد الجدول كاملاً بلا ?page= — مقبول للقوائم
الصغيرة، قاتل للجداول التي تنمو بلا حد. `EnforcedPageNumberPagination` يرقّم
دائماً، ويُركَّب endpoint-بـendpoint مع تعديل مستهلكي الواجهة في نفس الـcommit.

هذا الملف يحمل العقد المشترك: كل endpoint مسجَّل في ENFORCED_ENDPOINTS يجب أن
يعيد غلاف {results,count} حتى بلا ?page= وألا يتجاوز سقف الصفحة. الإضافات
اللاحقة تُسجَّل هنا سطراً واحداً.
"""
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from tenants.services import create_company

# (المسار، الحد الأدنى من الصفوف المزروعة كي يكون الاختبار ذا معنى يُضاف لاحقاً
#  لكل endpoint عند تركيبه — هنا يكفي التحقق من شكل الاستجابة الفارغة/الصغيرة)
ENFORCED_ENDPOINTS = [
    "/api/logistics/payments/",
    "/api/logistics/deals/",
    "/api/inventory/stock-movements/",
]


class EnforcedPaginationContractTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pager", password="x")
        cls.tenant = create_company("شركة الترقيم", cls.user)
        cls.token = Token.objects.create(user=cls.user)

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _h(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_no_page_param_still_returns_paginated_envelope(self):
        """بلا ?page= ⇒ غلاف {results,count} لا مصفوفة خام — عقد الفئة أ."""
        for url in ENFORCED_ENDPOINTS:
            with self.subTest(url=url):
                res = self.client.get(url, **self._h())
                self.assertEqual(res.status_code, 200, f"{url}: {res.content[:200]}")
                data = res.json()
                self.assertIsInstance(
                    data, dict, f"{url} أعاد مصفوفة خام — الترقيم غير مُنفَذ")
                self.assertIn("results", data, url)
                self.assertIn("count", data, url)

    def test_page_size_is_capped(self):
        """page_size فوق السقف (200) لا يُحترم حرفياً — الحماية من ?page_size=1e9."""
        for url in ENFORCED_ENDPOINTS:
            with self.subTest(url=url):
                res = self.client.get(
                    url, {"page": 1, "page_size": 999999}, **self._h())
                self.assertEqual(res.status_code, 200, url)
                self.assertLessEqual(len(res.json()["results"]), 200, url)
