"""صلاحية وحدة الاستيراد (نموذج من مستويين) — الجراحة المطوّرة، المرحلة 1.

- السوبر أدمن (thapet64@gmail.com أو is_superuser) يفعّل الاستيراد لكل شركة.
- مدير الشركة يمنح الصلاحية لأعضائها (ضمن شركة مفعّلة).
- قسم «تكاليف الاستيراد» (الشجرة 53*) يُخفى عمّن لا يملك الصلاحية.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from accounting.models import Account
from core.import_access import is_super_admin, user_can_access_import
from tenants.models import Tenant, UserCompanyMembership


class ImportAccessHelperTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=940, CompanyName='Imp Co')
        cls.tenant_on = Tenant.objects.create(TenantID=941, CompanyName='Imp Co On', import_enabled=True)
        cls.superu = User.objects.create_superuser(username='root', password='x', email='root@x.co')
        cls.owner = User.objects.create_user(username='owner', password='x', email='thapet64@gmail.com')
        cls.manager = User.objects.create_user(username='mgr', password='x', email='mgr@x.co')
        cls.staff = User.objects.create_user(username='stf', password='x', email='stf@x.co')
        UserCompanyMembership.objects.create(user=cls.manager, tenant=cls.tenant_on, role='manager')
        cls.staff_m = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant_on, role='staff'
        )

    def test_is_super_admin_by_email_and_superuser(self):
        self.assertTrue(is_super_admin(self.superu))
        self.assertTrue(is_super_admin(self.owner))
        self.assertFalse(is_super_admin(self.manager))

    def test_super_admin_access_requires_enabled_company(self):
        # تفعيل الشركة شرطٌ للجميع — حتى السوبر أدمن لا يرى الاستيراد في شركة معطّلة.
        self.assertFalse(user_can_access_import(self.superu, self.tenant))     # معطّلة
        self.assertFalse(user_can_access_import(self.owner, self.tenant))
        self.assertTrue(user_can_access_import(self.superu, self.tenant_on))   # مفعّلة
        self.assertTrue(user_can_access_import(self.owner, self.tenant_on))

    def test_disabled_company_blocks_everyone(self):
        m = UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role='manager')
        self.assertFalse(user_can_access_import(self.manager, self.tenant))    # الشركة معطّلة
        self.assertFalse(user_can_access_import(self.superu, self.tenant))     # حتى السوبر أدمن
        m.delete()

    def test_enabled_company_manager_implicit(self):
        self.assertTrue(user_can_access_import(self.manager, self.tenant_on))

    def test_enabled_company_staff_needs_grant(self):
        self.assertFalse(user_can_access_import(self.staff, self.tenant_on))
        self.staff_m.can_access_import = True
        self.staff_m.save(update_fields=['can_access_import'])
        self.assertTrue(user_can_access_import(self.staff, self.tenant_on))
        self.staff_m.can_access_import = False
        self.staff_m.save(update_fields=['can_access_import'])


class CoaImportGatingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=942, CompanyName='Coa Co')
        cls.manager = User.objects.create_user(username='cmgr', password='x', email='cmgr@x.co')
        cls.staff = User.objects.create_user(username='cstf', password='x', email='cstf@x.co')
        for u in (cls.manager, cls.staff):
            Token.objects.create(user=u)
        UserCompanyMembership.objects.create(user=cls.manager, tenant=cls.tenant, role='manager')
        cls.staff_m = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role='staff'
        )
        parent = Account.objects.create(tenant=cls.tenant, code='53', name='تكاليف الاستيراد', account_type='Expense')
        Account.objects.create(tenant=cls.tenant, code='5301', name='شحن دولي', account_type='Expense', parent=parent)
        Account.objects.create(tenant=cls.tenant, code='5201', name='رواتب', account_type='Expense')

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        c.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        return c

    def _codes(self, resp):
        data = resp.data
        items = data.get('results', data) if isinstance(data, dict) else data
        return {a.get('code') for a in items}

    def test_staff_in_disabled_company_cannot_see_import_costs(self):
        resp = self._client(self.staff).get('/api/accounting/accounts/')
        self.assertEqual(resp.status_code, 200, resp.content)
        codes = self._codes(resp)
        self.assertNotIn('53', codes)
        self.assertNotIn('5301', codes)
        self.assertIn('5201', codes)

    def test_manager_in_enabled_company_sees_import_costs(self):
        self.tenant.import_enabled = True
        self.tenant.save(update_fields=['import_enabled'])
        codes = self._codes(self._client(self.manager).get('/api/accounting/accounts/'))
        self.assertIn('53', codes)
        self.assertIn('5301', codes)

    def test_granted_staff_in_enabled_company_sees_import_costs(self):
        self.tenant.import_enabled = True
        self.tenant.save(update_fields=['import_enabled'])
        self.staff_m.can_access_import = True
        self.staff_m.save(update_fields=['can_access_import'])
        codes = self._codes(self._client(self.staff).get('/api/accounting/accounts/'))
        self.assertIn('5301', codes)

    def test_ungranted_staff_in_enabled_company_hidden(self):
        self.tenant.import_enabled = True
        self.tenant.save(update_fields=['import_enabled'])
        codes = self._codes(self._client(self.staff).get('/api/accounting/accounts/'))
        self.assertNotIn('5301', codes)


class ImportToggleEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=943, CompanyName='Toggle Co')
        cls.superu = User.objects.create_superuser(username='sa', password='x', email='sa@x.co')
        cls.manager = User.objects.create_user(username='tmgr', password='x', email='tmgr@x.co')
        cls.staff = User.objects.create_user(username='tstf', password='x', email='tstf@x.co')
        UserCompanyMembership.objects.create(user=cls.manager, tenant=cls.tenant, role='manager')
        cls.staff_m = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role='staff'
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        c.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        return c

    def test_super_admin_enables_company_import(self):
        resp = self._client(self.superu).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/set-import-enabled/',
            {'import_enabled': True}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.import_enabled)

    def test_manager_cannot_enable_company_import(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/set-import-enabled/',
            {'import_enabled': True}, format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.import_enabled)

    def test_manager_grants_member_when_enabled(self):
        self.tenant.import_enabled = True
        self.tenant.save(update_fields=['import_enabled'])
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/set-import-access/',
            {'membership_id': self.staff_m.id, 'can_access_import': True}, format='json',
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.staff_m.refresh_from_db()
        self.assertTrue(self.staff_m.can_access_import)

    def test_manager_grant_blocked_when_company_disabled(self):
        resp = self._client(self.manager).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/set-import-access/',
            {'membership_id': self.staff_m.id, 'can_access_import': True}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.staff_m.refresh_from_db()
        self.assertFalse(self.staff_m.can_access_import)

    def test_staff_cannot_grant_member(self):
        self.tenant.import_enabled = True
        self.tenant.save(update_fields=['import_enabled'])
        resp = self._client(self.staff).post(
            f'/api/tenants/companies/{self.tenant.TenantID}/members/set-import-access/',
            {'membership_id': self.staff_m.id, 'can_access_import': True}, format='json',
        )
        self.assertEqual(resp.status_code, 403, resp.content)
