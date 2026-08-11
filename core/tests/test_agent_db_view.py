"""الجلسة الأمنية 2026-08-11 — P0-2: تقييد نقطة SQL الخام للوكيل.

قبل الإصلاح كانت `/api/agent/query/` بلا مصادقة (`@authentication_classes([])`)
وحارسها الوحيد مفتاح ثابت مشترك + قائمة سوداء regex قابلة للتجاوز. هذه
الاختبارات تثبّت الطبقات الثلاث: مصادقة superuser، مفتاح API، والتحليل النحوي
الذي يرفض العبارات المتعددة وغير-SELECT وحقن INTO.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from tenants.models import Tenant, UserCompanyMembership

URL = "/api/agent/query/"
KEY = "test-agent-key-strong"


@override_settings(AGENT_DB_API_KEY=KEY)
class AgentQuerySecurityTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            TenantID=1, CompanyName="A", SubscriptionPlan="Enterprise", Status="Active")
        cls.root = User.objects.create_superuser(username="root", password="x")
        cls.staff = User.objects.create_user(username="staff", password="x", is_staff=True)
        cls.member = User.objects.create_user(username="m", password="x")
        UserCompanyMembership.objects.create(
            user=cls.member, tenant=cls.tenant, role="manager", is_default=True)
        cls.root_token = Token.objects.create(user=cls.root)
        cls.staff_token = Token.objects.create(user=cls.staff)
        cls.member_token = Token.objects.create(user=cls.member)

    def setUp(self):
        cache.clear()  # عدّادات الـthrottle
        self.client = APIClient()

    def _post(self, sql, token=None, key=KEY):
        creds = {}
        if token:
            creds["HTTP_AUTHORIZATION"] = f"Token {token.key}"
        if key is not None:
            creds["HTTP_X_AGENT_KEY"] = key
        return self.client.post(URL, {"sql": sql}, format="json", **creds)

    # ── الطبقة 1: المصادقة ──
    def test_anonymous_rejected(self):
        self.assertIn(self._post("SELECT 1", token=None).status_code, (401, 403))

    def test_non_superuser_rejected(self):
        self.assertEqual(self._post("SELECT 1", token=self.member_token).status_code, 403)
        self.assertEqual(self._post("SELECT 1", token=self.staff_token).status_code, 403)

    # ── الطبقة 2: مفتاح API ──
    def test_wrong_key_rejected(self):
        self.assertEqual(
            self._post("SELECT 1", token=self.root_token, key="wrong").status_code, 401)

    @override_settings(AGENT_DB_API_KEY="")
    def test_unconfigured_key_fails_closed(self):
        self.assertEqual(
            self._post("SELECT 1", token=self.root_token, key="").status_code, 401)

    # ── الطبقة 3: التحليل النحوي ──
    def test_valid_select_succeeds(self):
        res = self._post("SELECT 1 AS n", token=self.root_token)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["rows"], [[1]])

    def test_multiple_statements_rejected(self):
        res = self._post("SELECT 1; DROP TABLE auth_user", token=self.root_token)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertTrue(User.objects.filter(username="root").exists())

    def test_non_select_rejected(self):
        self.assertEqual(
            self._post("UPDATE auth_user SET is_staff=1", token=self.root_token).status_code, 400)

    def test_select_into_outfile_rejected(self):
        res = self._post(
            "SELECT * FROM auth_user INTO OUTFILE '/tmp/x'", token=self.root_token)
        self.assertEqual(res.status_code, 400, res.content)
