"""P2-11 (SCALABILITY_AUDIT §4): نطاق قراءة بطاقة المستخدم.

`GET /api/hr/users/<pk>/` كان يفتح **أي** حساب في المنصّة كلها لأي مستخدم
عليه علامة `is_staff` — وهي علامة Django عامة تُمنَح لمن يدخل لوحة الإدارة،
لا صلة لها بعضوية شركة. النتيجة: بريد أي مستخدم واسمه ودوره مقروءان من خارج
شركته تماماً.

القراءة الآن مقصورة على: النفس · السوبر أدمن · من يشارك المستهدَف عضويةَ
شركة واحدة على الأقل.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, UserCompanyMembership


class UserDetailScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(CompanyName="شركة أ")
        cls.tenant_b = Tenant.objects.create(CompanyName="شركة ب")

        cls.staff_of_a = User.objects.create_user(
            username="staff_a", password="x", email="staff_a@ktra.test",
            is_staff=True,
        )
        cls.member_of_a = User.objects.create_user(
            username="member_a", password="x", email="member_a@ktra.test",
        )
        cls.member_of_b = User.objects.create_user(
            username="member_b", password="x", email="member_b@ktra.test",
        )
        cls.root = User.objects.create_superuser(
            username="root_user", password="x", email="root@ktra.test",
        )

        UserCompanyMembership.objects.create(
            user=cls.staff_of_a, tenant=cls.tenant_a, role="manager",
        )
        UserCompanyMembership.objects.create(
            user=cls.member_of_a, tenant=cls.tenant_a, role="staff",
        )
        UserCompanyMembership.objects.create(
            user=cls.member_of_b, tenant=cls.tenant_b, role="staff",
        )

        for user in (cls.staff_of_a, cls.member_of_a, cls.member_of_b, cls.root):
            Token.objects.create(user=user)

    def _get(self, requester, target):
        return self.client.get(
            f"/api/hr/users/{target.pk}/",
            HTTP_AUTHORIZATION=f"Token {Token.objects.get(user=requester).key}",
        )

    def test_is_staff_alone_cannot_read_across_companies(self):
        """الحارس الفعلي: موظف شركة أ (is_staff) لا يقرأ عضو شركة ب."""
        response = self._get(self.staff_of_a, self.member_of_b)
        self.assertEqual(response.status_code, 403, response.content)

    def test_shared_company_membership_is_allowed(self):
        response = self._get(self.staff_of_a, self.member_of_a)
        self.assertEqual(response.status_code, 200, response.content)

    def test_self_read_is_always_allowed(self):
        response = self._get(self.member_of_b, self.member_of_b)
        self.assertEqual(response.status_code, 200, response.content)

    def test_superuser_reads_anyone(self):
        response = self._get(self.root, self.member_of_b)
        self.assertEqual(response.status_code, 200, response.content)

    def test_unauthenticated_is_rejected(self):
        response = self.client.get(f"/api/hr/users/{self.member_of_a.pk}/")
        self.assertEqual(response.status_code, 401, response.content)
