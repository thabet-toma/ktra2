"""task12 M4 — إدارة الشركة والأعضاء:

- تعديل الشركة manager-only (كان مفتوحاً لأي عضو — T12-B3).
- حذف الشركة محظور نهائياً من الـ API.
- أعضاء: list (أي عضو) / add / change-role / remove (مدير فقط) + حماية آخر مدير.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, UserCompanyMembership


class CompanyAdminTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=930, CompanyName='Admin Co')
        cls.manager = User.objects.create_user(username='mgr', password='x', email='mgr@x.co')
        cls.staff = User.objects.create_user(username='stf', password='x', email='stf@x.co')
        cls.outsider = User.objects.create_user(username='out', password='x', email='out@x.co')
        cls.platform_user = User.objects.create_user(
            username='private-user', password='x', email='private@x.co'
        )
        cls.superuser = User.objects.create_superuser(
            username='root', password='x', email='root@x.co'
        )
        for u in (cls.manager, cls.staff, cls.outsider, cls.platform_user, cls.superuser):
            Token.objects.create(user=u)
        cls.mgr_membership = UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.tenant, role='manager'
        )
        cls.staff_membership = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role='staff'
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        c.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        return c

    def _token_client(self, user):
        c = APIClient()
        token = Token.objects.get(user=user)
        c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return c

    # ── تعديل/حذف الشركة ──
    def test_staff_cannot_rename_company(self):
        resp = self._client(self.staff).patch(
            f'/api/tenants/companies/{self.tenant.TenantID}/',
            {'CompanyName': 'Hacked'}, format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.CompanyName, 'Admin Co')

    def test_manager_can_rename_company(self):
        resp = self._client(self.manager).patch(
            f'/api/tenants/companies/{self.tenant.TenantID}/',
            {'CompanyName': 'Renamed Co'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.CompanyName, 'Renamed Co')

    def test_delete_company_blocked_even_for_manager(self):
        resp = self._client(self.manager).delete(f'/api/tenants/companies/{self.tenant.TenantID}/')
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertTrue(Tenant.objects.filter(TenantID=self.tenant.TenantID).exists())

    # ── الأعضاء ──
    def test_member_can_list_members(self):
        resp = self._client(self.staff).get(f'/api/tenants/companies/{self.tenant.TenantID}/members/')
        self.assertEqual(resp.status_code, 200, resp.content)
        usernames = {m['username'] for m in resp.data}
        self.assertEqual(usernames, {'mgr', 'stf'})

    def test_company_manager_cannot_list_platform_users(self):
        resp = self._token_client(self.manager).get('/api/hr/users/')
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_superuser_can_list_platform_users(self):
        resp = self._token_client(self.superuser).get('/api/hr/users/')
        self.assertEqual(resp.status_code, 200, resp.content)
        usernames = {row['username'] for row in resp.json()}
        self.assertIn('private-user', usernames)

    def test_outsider_cannot_list_members(self):
        resp = self._client(self.outsider).get(f'/api/tenants/companies/{self.tenant.TenantID}/members/')
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_manager_adds_member_with_role(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/',
            {'username_or_email': 'out@x.co', 'role': 'accountant'}, format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        m = UserCompanyMembership.objects.get(user=self.outsider, tenant=self.tenant)
        self.assertEqual(m.role, 'accountant')

    def test_add_member_requires_exact_identifier(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/',
            {'username_or_email': 'private', 'role': 'staff'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(
            UserCompanyMembership.objects.filter(user=self.platform_user, tenant=self.tenant).exists()
        )

        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/',
            {'username_or_email': 'PRIVATE@X.CO', 'role': 'viewer'}, format='json',
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(
            UserCompanyMembership.objects.filter(
                user=self.platform_user, tenant=self.tenant, role='viewer'
            ).exists()
        )

    def test_add_existing_member_has_clear_error(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/',
            {'username_or_email': self.staff.email, 'role': 'viewer'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn('عضو في الشركة بالفعل', str(resp.data['username_or_email']))

    def test_staff_cannot_add_member(self):
        resp = self._client(self.staff).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/',
            {'username_or_email': 'out', 'role': 'staff'}, format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_add_unknown_user_rejected(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/',
            {'username_or_email': 'ghost@x.co', 'role': 'staff'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_change_role(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/change-role/',
            {'membership_id': self.staff_membership.id, 'role': 'viewer'}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.staff_membership.refresh_from_db()
        self.assertEqual(self.staff_membership.role, 'viewer')

    def test_cannot_downgrade_last_manager(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/change-role/',
            {'membership_id': self.mgr_membership.id, 'role': 'staff'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.mgr_membership.refresh_from_db()
        self.assertEqual(self.mgr_membership.role, 'manager')

    def test_remove_member_and_last_manager_guard(self):
        c = self._client(self.manager)
        resp = c.post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/remove/',
            {'membership_id': self.staff_membership.id}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(
            UserCompanyMembership.objects.filter(id=self.staff_membership.id).exists()
        )
        resp = c.post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/remove/',
            {'membership_id': self.mgr_membership.id}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
