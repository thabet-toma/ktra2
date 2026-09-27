"""SA-9: السوبر أدمن ينشئ شركةً لعميل عبر `create_company` نفسها، وصفحة صحة النظام."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account, FiscalPeriod
from core.models import ActivityLog, PlatformAuditLog
from tenants.models import Branch, Tenant, UserCompanyMembership

URL = '/api/platform/companies/'
HEALTH_URL = '/api/platform/health/'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PlatformCompanyCreateTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(
            username='create-root', email='create-root@example.com', password='x')
        cls.owner = User.objects.create_user(
            username='client-owner', email='owner@client.example', password='x')
        cls.member = User.objects.create_user(username='plain-member', password='x')

    def setUp(self):
        self.client.force_authenticate(self.root)

    def post(self, **data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(URL, {'name': 'شركة العميل', 'owner_email': 'owner@client.example', **data},
                                    format='json')

    def test_options_list_creatable_templates_without_client_book(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        keys = [row['key'] for row in response.data['templates']]
        self.assertIn('general', keys)
        self.assertNotIn('client_book', keys)
        self.assertIn('Trial', [row['key'] for row in response.data['plans']])

    def test_creates_through_create_company_with_owner_as_manager(self):
        response = self.post(trial_days=30)
        self.assertEqual(response.status_code, 201, response.data)
        tenant = Tenant.objects.get(pk=response.data['id'])
        # زرع `create_company` كاملاً — لا مسار ثانٍ ناقص.
        self.assertTrue(Account.objects.filter(tenant=tenant).exists())
        self.assertTrue(Branch.objects.filter(tenant=tenant, is_main=True).exists())
        self.assertTrue(FiscalPeriod.objects.filter(tenant=tenant).exists())
        membership = UserCompanyMembership.objects.get(tenant=tenant)
        self.assertEqual((membership.user, membership.role), (self.owner, 'manager'))
        self.assertFalse(UserCompanyMembership.objects.filter(tenant=tenant, user=self.root).exists())
        self.assertEqual(tenant.SubscriptionPlan, 'Trial')
        self.assertEqual(tenant.subscription_ends_at, timezone.localdate() + timedelta(days=30))

    def test_creation_is_audited_and_logged_in_the_company(self):
        response = self.post()
        tenant_id = response.data['id']
        event = PlatformAuditLog.objects.get(action='COMPANY_CREATED')
        self.assertEqual((event.tenant_id, event.actor, event.target_user),
                         (tenant_id, self.root, self.owner))
        self.assertEqual(event.severity, 'warning')
        self.assertTrue(ActivityLog.objects.filter(
            tenant_id=tenant_id, metadata__event_code='COMPANY_CREATED').exists())

    def test_owner_is_emailed(self):
        self.post()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@client.example'])
        self.assertIn('شركة العميل', mail.outbox[0].subject)

    def test_paid_plan_starts_active_with_optional_end(self):
        ends = timezone.localdate() + timedelta(days=365)
        response = self.post(plan='Pro', subscription_ends_at=ends.isoformat())
        tenant = Tenant.objects.get(pk=response.data['id'])
        self.assertEqual((tenant.SubscriptionPlan, tenant.Status, tenant.subscription_ends_at),
                         ('Pro', 'Active', ends))

    def test_unregistered_owner_is_refused_and_nothing_is_created(self):
        before = Tenant.objects.count()
        response = self.post(owner_email='nobody@client.example')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'owner_not_registered')
        self.assertEqual(Tenant.objects.count(), before)
        self.assertFalse(PlatformAuditLog.objects.filter(action='COMPANY_CREATED').exists())

    def test_invalid_input_is_refused_before_any_write(self):
        before = Tenant.objects.count()
        response = self.post(name='  ', template='client_book', trial_days=500)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data), {'name', 'template', 'trial_days'})
        past = self.post(plan='Basic', subscription_ends_at=timezone.localdate().isoformat())
        self.assertIn('subscription_ends_at', past.data)
        self.assertEqual(Tenant.objects.count(), before)

    def test_failure_after_seeding_rolls_back_the_whole_company(self):
        self.client.raise_request_exception = False
        with mock.patch('core.platform_admin_api.record_platform_event', side_effect=RuntimeError):
            self.assertEqual(self.post().status_code, 500)
        self.assertFalse(Tenant.objects.filter(CompanyName='شركة العميل').exists())

    def test_non_super_admin_is_forbidden(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.client.get(HEALTH_URL).status_code, 403)


class PlatformHealthTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(
            username='health-root', email='health-root@example.com', password='x')
        Tenant.objects.create(CompanyName='شركة صحة', SubscriptionPlan='Pro', Status='Active')

    def setUp(self):
        self.client.force_authenticate(self.root)

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_reports_database_cache_migrations_and_unconfigured_backup(self):
        response = self.client.get(HEALTH_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['database']['ok'])
        self.assertIsNotNone(response.data['database']['ping_ms'])
        self.assertTrue(response.data['cache']['ok'])
        self.assertIsInstance(response.data['migrations']['pending'], list)
        self.assertEqual(response.data['backup'], {'configured': False})
        self.assertEqual(response.data['heaviest_companies'][0]['name'], 'شركة صحة')

    def test_backup_directory_reports_latest_file_name_only(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            for name in ('old.sql.gz', 'new.sql.gz'):
                with open(os.path.join(directory, name), 'wb') as handle:
                    handle.write(b'x')
            old_time = timezone.now().timestamp() - 3 * 24 * 3600
            os.utime(os.path.join(directory, 'old.sql.gz'), (old_time, old_time))
            with override_settings(KTRA_BACKUP_DIR=directory):
                backup = self.client.get(HEALTH_URL).data['backup']
        self.assertEqual(backup['latest_file'], 'new.sql.gz')
        self.assertFalse(backup['stale'])
        self.assertEqual(backup['file_count'], 2)
        self.assertNotIn(directory, str(backup))

    def test_failed_logins_in_last_day_are_counted(self):
        PlatformAuditLog.objects.create(action='LOGIN_FAILED', severity='warning')
        self.assertEqual(self.client.get(HEALTH_URL).data['failed_logins_24h'], 1)
