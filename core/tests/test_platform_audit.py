"""سجلّ تدقيق المنصة (SA-1): كل فعلٍ إداريّ للسوبر أدمن يترك أثراً لا يُمحى."""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import PlatformAuditLog
from core.platform_audit import record_platform_event
from tenants.models import Tenant, UserCompanyMembership


class PlatformAuditLogAppendOnlyTest(TestCase):
    def setUp(self):
        self.entry = record_platform_event('PLAN_PRICE_CHANGED', metadata={'plan': 'Pro'})

    def test_saving_an_existing_row_again_is_refused(self):
        self.entry.reason = 'تعديل لاحق'
        with self.assertRaises(PermissionError):
            self.entry.save()

    def test_deleting_a_row_is_refused(self):
        with self.assertRaises(PermissionError):
            self.entry.delete()

    def test_bulk_update_and_delete_are_refused(self):
        with self.assertRaises(PermissionError):
            PlatformAuditLog.objects.all().update(reason='x')
        with self.assertRaises(PermissionError):
            PlatformAuditLog.objects.all().delete()
        self.assertEqual(PlatformAuditLog.objects.get().reason, '')

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(ValueError):
            record_platform_event('SOMETHING_FREEFORM')

    def test_default_severity_comes_from_the_catalog(self):
        entry = record_platform_event('SUPER_ADMIN_GRANTED')
        self.assertEqual(entry.severity, 'high')


class PlatformAdminActionsAreAuditedTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(
            username='audit-root', email='audit-root@example.com', password='x',
            first_name='مالك', last_name='المنصة',
        )
        cls.member = User.objects.create_user(
            username='audit-member', email='audit-member@example.com', password='x',
        )
        cls.tenant = Tenant.objects.create(
            CompanyName='شركة التدقيق', SubscriptionPlan='Pro', Status='Active',
        )
        cls.manager = User.objects.create_user(username='audit-manager', password='x')
        UserCompanyMembership.objects.create(user=cls.manager, tenant=cls.tenant, role='manager')

    def setUp(self):
        self.client.force_authenticate(self.root)

    def _only(self, action):
        rows = list(PlatformAuditLog.objects.filter(action=action))
        self.assertEqual(len(rows), 1, [r.action for r in PlatformAuditLog.objects.all()])
        return rows[0]

    def test_granting_and_revoking_super_admin_is_recorded_with_actor_and_target(self):
        response = self.client.post(
            '/api/platform/super-admins/', {'identifier': 'audit-member'}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        granted = self._only('SUPER_ADMIN_GRANTED')
        self.assertEqual(granted.actor_id, self.root.pk)
        self.assertEqual(granted.actor_label, 'مالك المنصة')
        self.assertEqual(granted.target_user_id, self.member.pk)
        self.assertEqual(granted.severity, 'high')
        self.assertIsNone(granted.tenant_id)

        response = self.client.delete(f'/api/platform/super-admins/{self.member.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self._only('SUPER_ADMIN_REVOKED').target_user_id, self.member.pk)

    def test_refused_action_leaves_no_audit_row(self):
        response = self.client.post(
            '/api/platform/super-admins/', {'identifier': 'nobody'}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(PlatformAuditLog.objects.exists())

    def test_plan_price_change_is_recorded_without_a_tenant(self):
        response = self.client.put(
            '/api/platform/plan-pricing/',
            {'plan_key': 'Pro', 'monthly_price': '120.00', 'note': 'رفع سنوي'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = self._only('PLAN_PRICE_CHANGED')
        self.assertEqual(entry.metadata['plan'], 'Pro')
        self.assertEqual(entry.metadata['new_price'], '120.00')
        self.assertNotEqual(entry.metadata['previous_price'], entry.metadata['new_price'])
        self.assertEqual(entry.reason, 'رفع سنوي')

    def test_company_status_change_is_recorded_on_the_tenant(self):
        response = self.client.patch(
            f'/api/platform/companies/{self.tenant.pk}/', {'status': 'Suspended'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        entry = self._only('COMPANY_STATUS_CHANGED')
        self.assertEqual(entry.tenant_id, self.tenant.pk)
        self.assertEqual(entry.tenant_label, 'شركة التدقيق')
        self.assertEqual(entry.metadata, {'field': 'Status', 'previous': 'Active', 'new': 'Suspended'})

    def test_saving_the_same_status_records_nothing(self):
        self.client.patch(
            f'/api/platform/companies/{self.tenant.pk}/', {'status': 'Active'}, format='json')
        self.assertFalse(PlatformAuditLog.objects.filter(action='COMPANY_STATUS_CHANGED').exists())

    def test_module_toggle_is_recorded(self):
        response = self.client.post(
            f'/api/platform/companies/{self.tenant.pk}/modules/',
            {'module_key': 'after_sales', 'enabled': True, 'plan_note': 'تجربة'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        entry = self._only('MODULE_TOGGLED')
        self.assertEqual(entry.metadata['module'], 'after_sales')
        self.assertTrue(entry.metadata['enabled'])

    def test_member_add_and_remove_are_recorded(self):
        response = self.client.post(
            f'/api/platform/companies/{self.tenant.pk}/members/',
            {'identifier': 'audit-member', 'role': 'staff'}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        added = self._only('MEMBER_ADDED')
        self.assertEqual(added.target_user_id, self.member.pk)
        membership_id = added.metadata['membership_id']

        response = self.client.delete(
            f'/api/platform/companies/{self.tenant.pk}/members/{membership_id}/')
        self.assertEqual(response.status_code, 204)
        removed = self._only('MEMBER_REMOVED')
        self.assertEqual(removed.target_user_id, self.member.pk)
        self.assertEqual(removed.tenant_id, self.tenant.pk)

    def test_deactivating_a_user_is_recorded(self):
        response = self.client.post(
            f'/api/platform/users/{self.member.pk}/set-active/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        entry = self._only('USER_ACTIVE_CHANGED')
        self.assertEqual(entry.metadata, {'previous': True, 'is_active': False})


class FailedLoginIsAuditedTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='login-audit@example.com', email='login-audit@example.com', password='right-pass',
        )

    def test_wrong_password_is_recorded_without_the_password(self):
        response = self.client.post(
            '/api/hr/auth/login/',
            {'email': 'Login-Audit@example.com', 'password': 'wrong-pass'}, format='json',
        )
        self.assertEqual(response.status_code, 401)
        entry = PlatformAuditLog.objects.get(action='LOGIN_FAILED')
        self.assertIsNone(entry.actor_id)
        self.assertEqual(entry.target_user_id, self.user.pk)
        self.assertEqual(entry.metadata['identifier'], 'login-audit@example.com')
        self.assertNotIn('wrong-pass', str(entry.metadata))

    def test_unknown_account_is_recorded_as_unknown(self):
        self.client.post(
            '/api/hr/auth/login/', {'email': 'ghost@example.com', 'password': 'x'}, format='json')
        entry = PlatformAuditLog.objects.get(action='LOGIN_FAILED')
        self.assertIsNone(entry.target_user_id)
        self.assertFalse(entry.metadata['known_user'])

    def test_successful_login_records_no_failure(self):
        response = self.client.post(
            '/api/hr/auth/login/',
            {'email': 'login-audit@example.com', 'password': 'right-pass'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(PlatformAuditLog.objects.filter(action='LOGIN_FAILED').exists())


class PlatformAuditLogEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(
            username='audit-reader', email='audit-reader@example.com', password='x')
        cls.tenant_a = Tenant.objects.create(CompanyName='أ', SubscriptionPlan='Pro', Status='Active')
        cls.tenant_b = Tenant.objects.create(CompanyName='ب', SubscriptionPlan='Pro', Status='Active')
        record_platform_event('MODULE_TOGGLED', tenant=cls.tenant_a)
        record_platform_event('LIMIT_CHANGED', tenant=cls.tenant_a)
        record_platform_event('MODULE_TOGGLED', tenant=cls.tenant_b)
        record_platform_event('SUPER_ADMIN_GRANTED', reason='مساعد جديد')

    def setUp(self):
        self.client.force_authenticate(self.root)

    def test_lists_everything_newest_first_with_the_event_catalog(self):
        response = self.client.get('/api/platform/audit-log/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 4)
        self.assertEqual(response.data['results'][0]['action'], 'SUPER_ADMIN_GRANTED')
        self.assertEqual(response.data['results'][0]['action_label'], 'منح صلاحية سوبر أدمن')
        self.assertIn('LOGIN_FAILED', {e['action'] for e in response.data['events']})

    def test_filters_by_tenant_action_severity_and_search(self):
        by_tenant = self.client.get(f'/api/platform/audit-log/?tenant={self.tenant_a.pk}')
        self.assertEqual(by_tenant.data['count'], 2)
        by_action = self.client.get('/api/platform/audit-log/?action=MODULE_TOGGLED')
        self.assertEqual(by_action.data['count'], 2)
        by_severity = self.client.get('/api/platform/audit-log/?severity=high')
        self.assertEqual(by_severity.data['count'], 1)
        by_search = self.client.get('/api/platform/audit-log/?q=مساعد')
        self.assertEqual(by_search.data['count'], 1)

    def test_bad_filter_values_are_400_not_500(self):
        self.assertEqual(self.client.get('/api/platform/audit-log/?tenant=abc').status_code, 400)
        self.assertEqual(self.client.get('/api/platform/audit-log/?date_from=2026-13-40').status_code, 400)

    def test_non_admin_is_refused(self):
        outsider = User.objects.create_user(username='audit-outsider', password='x')
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get('/api/platform/audit-log/').status_code, 403)
