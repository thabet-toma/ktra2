"""قالبٌ لكل باب — `client_book` ليس شركةً يملكها أحد.

بلاغُ المالك: «لما أنشئ شركة بيجي دفتر زبون — قيّمه»، و«لما أسجّل عميل بيجيني
٣ خيارات، الخيارين القديمين اللي بيفتحوا ERP كامل هدول غلط».

الجذر: القوالب الثلاثة كانت قائمةً واحدة تُعرض في **أربعة** أبواب مختلفة بلا
تمييز — إنشاء شركة، تبديل قالبها، لوحة «دفاتر عملائي»، وصفحة زبون المكتب
الخارجي. فكان إنشاء «دفتر عميل» كشركةٍ مستقلّة ممكناً (دفترٌ بلا مكتب: بلا زرّ
عودة ولا حصّة ولا وحدة `accountant_portal` مرخَّصة)، وكان فتحُ دفترٍ لزبون
يفتح افتراضياً نظاماً تجارياً كاملاً.

الملاحظة على **رمز الاستجابة عند الـHTTP** لا على استدعاء `assert_*` مباشرة:
الحارس يجب أن يكون في المسار الذي تسلكه الواجهة فعلاً.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.plans import invalidate_limit_cache
from tenants.models import Tenant, UserCompanyMembership

COMPANIES_URL = "/api/tenants/companies/"


class SelfServeTemplateSurfaceTest(APITestCase):
    """بابُ «أنشئ شركتي»: القالبان العامّان فقط."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tpl-owner", password="x")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_general_template_is_accepted(self):
        res = self.client.post(
            COMPANIES_URL, {"CompanyName": "شركة عامة", "template": "general"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)

    def test_accounting_firm_template_is_accepted(self):
        res = self.client.post(
            COMPANIES_URL,
            {"CompanyName": "مكتب محاسبة", "template": "accounting_firm"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)

    def test_client_book_template_is_refused_as_a_standalone_company(self):
        res = self.client.post(
            COMPANIES_URL, {"CompanyName": "دفتر ضائع", "template": "client_book"},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(Tenant.objects.filter(CompanyName="دفتر ضائع").exists())

    def test_switching_an_existing_company_to_client_book_is_refused(self):
        created = self.client.post(
            COMPANIES_URL, {"CompanyName": "شركة قائمة", "template": "general"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        tenant_id = created.json()["TenantID"]

        res = self.client.post(
            f"{COMPANIES_URL}{tenant_id}/set-template/",
            {"template": "client_book"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(
            Tenant.objects.get(pk=tenant_id).template, "general",
        )


class ManagedBookTemplateSurfaceTest(APITestCase):
    """بابُ «دفاتر عملائي»: قالب الدفتر وحده، وهو الافتراضي بلا تصريح."""

    @classmethod
    def setUpTestData(cls):
        cls.office = Tenant.objects.create(
            CompanyName="مكتب الدفاتر", SubscriptionPlan="Pro", Status="Active",
        )
        cls.manager = User.objects.create_user(username="books-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.office, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.office.pk)
        self.client.force_authenticate(user=self.manager)

    def _url(self):
        return f"{COMPANIES_URL}{self.office.pk}/managed-books/"

    def test_book_opens_on_client_book_when_no_template_is_named(self):
        res = self.client.post(
            self._url(), {"CompanyName": "زبون بلا تصريح"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(
            Tenant.objects.get(pk=res.json()["TenantID"]).template, "client_book",
        )

    def test_general_template_is_refused_for_a_client_book(self):
        res = self.client.post(
            self._url(), {"CompanyName": "زبون بنظام كامل", "template": "general"},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(Tenant.objects.filter(CompanyName="زبون بنظام كامل").exists())

    def test_accounting_firm_template_is_refused_for_a_client_book(self):
        res = self.client.post(
            self._url(),
            {"CompanyName": "زبون بقالب مكتب", "template": "accounting_firm"},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
