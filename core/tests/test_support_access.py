"""SA-2: إذن دخول فريق كترا إلى شركة — لا دخول صامت بعد اليوم."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core.access import user_permissions
from core.models import ActivityLog, PlatformAuditLog, SupportAccessGrant
from tenants.models import Tenant, UserCompanyMembership

MY_PLAN = '/api/my-plan/usage/'          # قراءة داخل الشركة
SET_UI_MODE = '/api/tenants/companies/set-ui-mode/'  # كتابة داخل الشركة
TENANT_SIDE = '/api/support-access/'


class SupportAccessBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(
            username='sa-root', email='sa-root@example.com', password='x')
        cls.other_root = User.objects.create_superuser(
            username='sa-root-2', email='sa-root-2@example.com', password='x')
        cls.tenant = Tenant.objects.create(
            CompanyName='شركة الزبون', SubscriptionPlan='Pro', Status='Active')
        cls.other_tenant = Tenant.objects.create(
            CompanyName='شركة أخرى', SubscriptionPlan='Pro', Status='Active')
        cls.owner = User.objects.create_user(
            username='sa-owner', email='owner@customer.example', password='x')
        cls.staff = User.objects.create_user(username='sa-staff', password='x')
        cls.other_owner = User.objects.create_user(username='sa-other-owner', password='x')
        UserCompanyMembership.objects.create(user=cls.owner, tenant=cls.tenant, role='manager')
        UserCompanyMembership.objects.create(user=cls.staff, tenant=cls.tenant, role='staff')
        UserCompanyMembership.objects.create(
            user=cls.other_owner, tenant=cls.other_tenant, role='manager')

    def _as(self, user, tenant=None):
        self.client.force_authenticate(user)
        return {'HTTP_X_TENANT_ID': str((tenant or self.tenant).pk)}

    def _request(self, **data):
        self.client.force_authenticate(self.root)
        payload = {'reason': 'فحص فرق أرصدة المخزون', **data}
        return self.client.post(
            f'/api/platform/companies/{self.tenant.pk}/support-access/', payload, format='json')

    def _approve(self, grant_id, **data):
        return self.client.post(
            f'{TENANT_SIDE}{grant_id}/approve/', data, format='json', **self._as(self.owner))


class NoSilentEntryTest(SupportAccessBase):
    def test_super_admin_without_membership_or_grant_is_refused_with_a_code(self):
        response = self.client.get(MY_PLAN, **self._as(self.root))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'support_access_required')

    def test_super_admin_who_is_a_member_enters_as_before(self):
        UserCompanyMembership.objects.create(user=self.root, tenant=self.tenant, role='manager')
        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 200)

    @override_settings(SUPER_ADMIN_EMAILS=['configured@example.com'])
    def test_email_configured_super_admin_follows_the_same_rule(self):
        configured = User.objects.create_user(
            username='configured', email='configured@example.com', password='x')
        response = self.client.get(MY_PLAN, **self._as(configured))
        self.assertEqual(response.data['code'], 'support_access_required')

    def test_members_are_untouched(self):
        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.staff)).status_code, 200)


class RequestApproveFlowTest(SupportAccessBase):
    def test_request_then_approve_read_only_then_read_but_not_write(self):
        response = self._request(scope='read_only', hours=24)
        self.assertEqual(response.status_code, 201, response.content)
        grant_id = response.data['id']
        self.assertEqual(response.data['status'], 'pending')

        # قبل الموافقة: لا دخول.
        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 403)

        listing = self.client.get(TENANT_SIDE, **self._as(self.owner))
        self.assertEqual([row['id'] for row in listing.data['pending']], [grant_id])

        approved = self._approve(grant_id, hours=4)
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.data['status'], 'active')
        self.assertEqual(approved.data['scope'], 'read_only')

        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 200)
        write = self.client.post(SET_UI_MODE, {'ui_mode': 'simple'}, format='json', **self._as(self.root))
        self.assertEqual(write.status_code, 403)
        self.assertEqual(write.data['code'], 'support_access_read_only')

        actions = list(PlatformAuditLog.objects.values_list('action', flat=True))
        for expected in ('SUPPORT_ACCESS_REQUESTED', 'SUPPORT_ACCESS_APPROVED', 'SUPPORT_ACCESS_USED'):
            self.assertIn(expected, actions)
        self.assertEqual(PlatformAuditLog.objects.filter(action='SUPPORT_ACCESS_USED').count(), 1)
        self.assertTrue(ActivityLog.objects.filter(
            tenant=self.tenant, entity_type='support_access').exists())

    def test_full_scope_allows_writes_and_every_write_lands_in_the_company_log(self):
        grant_id = self._request(scope='full', hours=24).data['id']
        self._approve(grant_id)

        response = self.client.post(
            SET_UI_MODE, {'ui_mode': 'simple'}, format='json', **self._as(self.root))
        self.assertNotEqual(response.status_code, 403, response.content)
        write_row = ActivityLog.objects.get(
            tenant=self.tenant, entity_type='support_access',
            metadata__method='POST')
        self.assertEqual(write_row.metadata['support_grant_id'], grant_id)
        self.assertEqual(write_row.user_id, self.root.pk)

    def test_company_can_shorten_and_downgrade_but_not_extend_or_upgrade(self):
        grant_id = self._request(scope='full', hours=24).data['id']
        too_long = self._approve(grant_id, hours=168)
        self.assertEqual(too_long.status_code, 400)
        downgraded = self._approve(grant_id, hours=4, scope='read_only')
        self.assertEqual(downgraded.data['scope'], 'read_only')

        read_only_id = SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=self.other_root, reason='قراءة فقط',
            requested_scope='read_only', requested_hours=24,
        ).pk
        upgraded = self._approve(read_only_id, scope='full')
        self.assertEqual(upgraded.data['scope'], 'read_only')

    def test_only_a_manager_of_that_company_decides(self):
        grant_id = self._request().data['id']
        by_staff = self.client.post(
            f'{TENANT_SIDE}{grant_id}/approve/', {}, format='json', **self._as(self.staff))
        self.assertEqual(by_staff.status_code, 403)
        by_other_company = self.client.post(
            f'{TENANT_SIDE}{grant_id}/approve/', {}, format='json',
            **self._as(self.other_owner, self.other_tenant))
        self.assertEqual(by_other_company.status_code, 404)

    def test_reject_leaves_no_access(self):
        grant_id = self._request().data['id']
        response = self.client.post(
            f'{TENANT_SIDE}{grant_id}/reject/', {'note': 'ليس الآن'}, format='json',
            **self._as(self.owner))
        self.assertEqual(response.data['status'], 'rejected')
        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 403)

    def test_duplicate_pending_request_and_member_request_are_refused(self):
        self.assertEqual(self._request().status_code, 201)
        self.assertEqual(self._request().status_code, 400)
        UserCompanyMembership.objects.create(
            user=self.other_root, tenant=self.tenant, role='manager')
        self.client.force_authenticate(self.other_root)
        response = self.client.post(
            f'/api/platform/companies/{self.tenant.pk}/support-access/',
            {'reason': 'أنا عضو أصلاً'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_bad_inputs_are_400(self):
        self.assertEqual(self._request(reason='').status_code, 400)
        self.assertEqual(self._request(hours=5).status_code, 400)
        self.assertEqual(self._request(scope='admin').status_code, 400)

    def test_pending_request_goes_stale_after_72_hours(self):
        grant_id = self._request().data['id']
        SupportAccessGrant.objects.filter(pk=grant_id).update(
            created_at=timezone.now() - timedelta(hours=73))
        listing = self.client.get(TENANT_SIDE, **self._as(self.owner))
        self.assertEqual(listing.data['pending'], [])
        self.assertEqual(self._approve(grant_id).status_code, 400)


class GrantEndsTest(SupportAccessBase):
    def _active(self, scope='full', user=None):
        return SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=user or self.root, reason='دعم مباشر',
            requested_scope=scope, requested_hours=24, status='active', scope=scope,
            expires_at=timezone.now() + timedelta(hours=24),
        )

    def test_expired_grant_closes_the_door(self):
        grant = self._active()
        SupportAccessGrant.objects.filter(pk=grant.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.get(MY_PLAN, **self._as(self.root))
        self.assertEqual(response.data['code'], 'support_access_required')

    def test_company_revokes_and_the_next_request_is_refused(self):
        grant = self._active()
        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 200)
        revoked = self.client.post(f'{TENANT_SIDE}{grant.pk}/revoke/', {}, format='json', **self._as(self.owner))
        self.assertEqual(revoked.data['status'], 'revoked')
        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 403)

    def test_super_admin_ends_his_own_session_early(self):
        grant = self._active()
        self.client.force_authenticate(self.root)
        response = self.client.post(f'/api/platform/support-access/{grant.pk}/end/', {}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['status'], 'revoked')
        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 403)

    def test_a_grant_is_personal(self):
        self._active(user=self.other_root)
        response = self.client.get(MY_PLAN, **self._as(self.root))
        self.assertEqual(response.data['code'], 'support_access_required')


class FixedCarveOutsTest(SupportAccessBase):
    def setUp(self):
        SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=self.root, reason='دعم كامل',
            requested_scope='full', requested_hours=24, status='active', scope='full',
            expires_at=timezone.now() + timedelta(hours=24),
        )

    def test_support_session_lacks_member_and_permission_management(self):
        perms = user_permissions(self.root, self.tenant)
        self.assertNotIn('admin.members.manage', perms)
        self.assertNotIn('admin.permissions.manage', perms)
        self.assertIn('admin.settings.manage', perms)
        # عضوٌ مديرٌ حقيقيّ لا يتأثّر.
        self.assertIn('admin.members.manage', user_permissions(self.owner, self.tenant))

    def test_support_session_cannot_touch_its_own_grants_from_inside(self):
        response = self.client.get(TENANT_SIDE, **self._as(self.root))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'support_access_forbidden')

    def test_export_paths_are_closed_even_for_reading(self):
        # على مستوى البوابة مباشرةً: نقطة التصدير الحقيقية محروسةٌ أيضاً بترخيص
        # وحدتها (404 قبل الوصول هنا)، فلا تشهد وحدها أن البوابة تغلقها.
        from django.test import RequestFactory

        from core.support_access import SupportAccessForbidden
        from core.tenant_utils import get_tenant

        request = RequestFactory().get(
            '/api/reports/stock/export/', HTTP_X_TENANT_ID=str(self.tenant.pk))
        request.user = self.root
        with self.assertRaises(SupportAccessForbidden):
            get_tenant(request)
        request = RequestFactory().get('/api/reports/stock/', HTTP_X_TENANT_ID=str(self.tenant.pk))
        request.user = self.root
        self.assertEqual(get_tenant(request).pk, self.tenant.pk)


class EmergencyAccessTest(SupportAccessBase):
    def test_emergency_is_immediate_short_high_severity_and_notifies_the_company(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self._request(emergency=True, reason='توقّف الترحيل عند الزبون الآن')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['status'], 'active')
        self.assertTrue(response.data['is_emergency'])
        self.assertEqual(response.data['scope'], 'full')
        grant = SupportAccessGrant.objects.get(pk=response.data['id'])
        self.assertAlmostEqual(
            (grant.expires_at - grant.created_at).total_seconds(), 4 * 3600, delta=5)

        self.assertEqual(self.client.get(MY_PLAN, **self._as(self.root)).status_code, 200)
        audit = PlatformAuditLog.objects.get(action='SUPPORT_ACCESS_EMERGENCY')
        self.assertEqual(audit.severity, 'high')
        self.assertEqual(audit.reason, 'توقّف الترحيل عند الزبون الآن')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@customer.example'])
        self.assertIn('طارئ', mail.outbox[0].subject)

    def test_emergency_still_needs_a_reason(self):
        self.assertEqual(self._request(emergency=True, reason='').status_code, 400)


class PlatformSupportListTest(SupportAccessBase):
    def test_platform_lists_pending_and_active_across_companies(self):
        pending_id = self._request().data['id']
        SupportAccessGrant.objects.create(
            tenant=self.other_tenant, requested_by=self.root, reason='ساري',
            requested_scope='read_only', requested_hours=4, status='active', scope='read_only',
            expires_at=timezone.now() + timedelta(hours=4),
        )
        self.client.force_authenticate(self.root)
        pending = self.client.get('/api/platform/support-access/?status=pending')
        self.assertEqual([row['id'] for row in pending.data['results']], [pending_id])
        active = self.client.get('/api/platform/support-access/?status=active')
        self.assertEqual([row['tenant_name'] for row in active.data['results']], ['شركة أخرى'])
        self.assertEqual(self.client.get('/api/platform/support-access/?status=x').status_code, 400)


class CompanyEndpointsByIdTest(SupportAccessBase):
    """`/api/tenants/companies/<pk>/…` يحلّ الشركة من المسار لا من `get_tenant` —
    فلا يجوز أن يكون باباً خلفياً يتجاوز الإذن (مراجعة SA-2)."""

    def _grant(self, scope):
        return SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=self.root, reason='دعم مباشر',
            requested_scope=scope, requested_hours=24, status='active', scope=scope,
            expires_at=timezone.now() + timedelta(hours=24),
        )

    def test_without_a_grant_the_company_is_invisible_by_id_and_in_the_list(self):
        self.client.force_authenticate(self.root)
        self.assertEqual(
            self.client.get(f'/api/tenants/companies/{self.tenant.pk}/members/').status_code, 404)
        response = self.client.patch(
            f'/api/tenants/companies/{self.tenant.pk}/', {'CompanyName': 'اختراق'}, format='json')
        self.assertEqual(response.status_code, 404)
        listed = self.client.get('/api/tenants/companies/')
        rows = listed.data.get('results', listed.data) if isinstance(listed.data, dict) else listed.data
        self.assertNotIn(self.tenant.pk, [row['TenantID'] for row in rows])
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.CompanyName, 'شركة الزبون')

    def test_read_only_grant_reads_by_id_but_cannot_write(self):
        self._grant('read_only')
        self.client.force_authenticate(self.root)
        self.assertEqual(
            self.client.get(f'/api/tenants/companies/{self.tenant.pk}/members/').status_code, 200)
        response = self.client.patch(
            f'/api/tenants/companies/{self.tenant.pk}/', {'CompanyName': 'تعديل'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['code'], 'support_access_read_only')

    def test_full_grant_still_cannot_manage_members_by_id(self):
        self._grant('full')
        self.client.force_authenticate(self.root)
        response = self.client.post(
            f'/api/tenants/companies/{self.tenant.pk}/members/change-role/',
            {'user_id': self.staff.pk, 'role': 'manager'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            UserCompanyMembership.objects.get(user=self.staff, tenant=self.tenant).role, 'staff')

    def test_another_admins_grant_or_an_expired_one_does_not_open_by_id(self):
        # الشروط الثلاثة على **صفّ الإذن نفسه**: إذنٌ ساري لغيره + إذنٌ منتهٍ له
        # لا يجتمعان فيفتحا الشركة.
        SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=self.other_root, reason='إذن زميل',
            requested_scope='full', requested_hours=24, status='active', scope='full',
            expires_at=timezone.now() + timedelta(hours=24),
        )
        SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=self.root, reason='إذن منتهٍ',
            requested_scope='full', requested_hours=4, status='active', scope='full',
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.client.force_authenticate(self.root)
        self.assertEqual(
            self.client.get(f'/api/tenants/companies/{self.tenant.pk}/members/').status_code, 404)

    def test_super_admin_member_keeps_normal_access_by_id(self):
        UserCompanyMembership.objects.create(user=self.root, tenant=self.other_tenant, role='manager')
        self.client.force_authenticate(self.root)
        self.assertEqual(
            self.client.get(f'/api/tenants/companies/{self.other_tenant.pk}/members/').status_code, 200)


class CompanyListCapTest(SupportAccessBase):
    def test_open_grants_survive_a_long_history_and_history_is_capped(self):
        from core.support_access_api import HISTORY_LIMIT

        pending = SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=self.root, reason='طلب قديم معلّق',
            requested_scope='read_only', requested_hours=4)
        for number in range(HISTORY_LIMIT + 1):
            SupportAccessGrant.objects.create(
                tenant=self.tenant, requested_by=self.other_root, reason=f'سابق {number}',
                requested_scope='read_only', requested_hours=4, status='revoked')
        response = self.client.get(TENANT_SIDE, **self._as(self.owner))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['pending']], [pending.pk])
        self.assertEqual(len(response.data['history']), HISTORY_LIMIT)


class SupportRoleIsNotManagerTest(SupportAccessBase):
    """جلسة الدعم لا تمرّ بفحوص «للمدير وحده» التي تقرأ اسم الدور لا الصلاحيات."""

    def setUp(self):
        SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=self.root, reason='support',
            requested_scope='full', requested_hours=24, status='active', scope='full',
            expires_at=timezone.now() + timedelta(hours=24),
        )

    def test_support_session_role_is_support_not_manager(self):
        from core.access import SUPPORT_ROLE, user_tenant_role

        self.assertEqual(user_tenant_role(self.root, self.tenant), SUPPORT_ROLE)
        response = self.client.get('/api/permissions/me/', **self._as(self.root))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['is_manager'])
        self.assertIn('admin.settings.manage', response.data['permissions'])
        self.assertNotIn('admin.members.manage', response.data['permissions'])

    def test_super_admin_member_keeps_manager_role_and_owner_is_untouched(self):
        from core.access import user_tenant_role

        UserCompanyMembership.objects.create(user=self.root, tenant=self.other_tenant, role='manager')
        self.assertEqual(user_tenant_role(self.root, self.other_tenant), 'manager')
        self.assertEqual(user_tenant_role(self.owner, self.tenant), 'manager')
