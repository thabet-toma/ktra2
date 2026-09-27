"""SA-3: كم حركةً وكم مستنداً في كل شركة — بكلفةٍ ثابتة مهما كثرت الشركات."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import JournalHeader
from core.models import ActivityLog
from core.usage import USAGE_COUNTERS, compute_usage
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency, Tenant


class UsageCountersTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser(
            username='usage-root', email='usage-root@example.com', password='x')
        cls.member = User.objects.create_user(username='usage-member', password='x')
        cls.currency = Currency.objects.create(
            Code='ILS', Name='شيكل', Symbol='₪', IsBaseCurrency=True)
        cls.busy = Tenant.objects.create(CompanyName='شركة نشطة', SubscriptionPlan='Pro', Status='Active')
        cls.idle = Tenant.objects.create(CompanyName='شركة خاملة', SubscriptionPlan='Basic', Status='Active')
        today = timezone.localdate()
        cls.this_month = today.replace(day=1)
        cls.old = cls.this_month - timedelta(days=40)

        for number, (date, posted) in enumerate(
                [(cls.this_month, True), (cls.old, True), (cls.this_month, False)]):
            JournalHeader.objects.create(
                tenant=cls.busy, transaction_date=date, reference_type='USAGE',
                reference_id=number, is_posted=posted)
        customer = Partner.objects.create(tenant=cls.busy, name='عميل', partner_type='Customer')
        for number, date in enumerate([cls.this_month, cls.old]):
            SalesInvoice.objects.create(
                tenant=cls.busy, invoice_number=f'SI-U-{number}', customer=customer,
                currency=cls.currency, invoice_date=date, stock_on_post=False)
        ActivityLog.objects.create(
            tenant=cls.busy, user=cls.member, action='create', entity_type='x')
        stale = ActivityLog.objects.create(
            tenant=cls.busy, user=cls.root, action='create', entity_type='x')
        ActivityLog.objects.filter(pk=stale.pk).update(timestamp=timezone.now() - timedelta(days=45))

    def setUp(self):
        cache.clear()

    def test_counts_movements_and_documents_all_time_and_this_month(self):
        row = compute_usage([self.busy.pk, self.idle.pk])[self.busy.pk]
        # القيود المرحّلة وحدها حركات — المسودة لا.
        self.assertEqual(row['counters']['journal_entries'], {'total': 2, 'month': 1})
        self.assertEqual(row['counters']['sales_invoices'], {'total': 2, 'month': 1})
        self.assertEqual(row['movements_total'], 2)
        self.assertEqual(row['movements_month'], 1)
        self.assertEqual(row['documents_total'], 2)
        self.assertEqual(row['documents_month'], 1)
        self.assertEqual(row['last_document_date'], self.this_month)
        # نشاطٌ قبل 45 يوماً لا يُعدّ في «النشطين خلال 30 يوماً».
        self.assertEqual(row['active_users_30d'], 1)

    def test_idle_company_is_all_zeros_not_missing(self):
        row = compute_usage([self.idle.pk])[self.idle.pk]
        self.assertEqual(row['documents_total'], 0)
        self.assertEqual(row['movements_total'], 0)
        self.assertIsNone(row['last_document_date'])

    def test_query_count_does_not_grow_with_the_number_of_companies(self):
        with CaptureQueriesContext(connection) as few:
            compute_usage([self.busy.pk, self.idle.pk])
        extra = [
            Tenant.objects.create(CompanyName=f'إضافية {n}', SubscriptionPlan='Basic', Status='Active').pk
            for n in range(5)
        ]
        with CaptureQueriesContext(connection) as many:
            compute_usage([self.busy.pk, self.idle.pk, *extra])
        self.assertEqual(len(few), len(many))
        self.assertEqual(len(many), len(USAGE_COUNTERS) + 1)

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_platform_endpoint_is_cached_and_refreshable(self):
        cache.clear()
        self.client.force_authenticate(self.root)
        first = self.client.get('/api/platform/usage/')
        self.assertEqual(first.status_code, 200)
        busy = next(r for r in first.data['results'] if r['tenant_id'] == self.busy.pk)
        self.assertEqual(busy['name'], 'شركة نشطة')
        self.assertEqual(busy['documents_total'], 2)
        self.assertIn('sales_invoices', {c['key'] for c in first.data['counter_catalog']})

        JournalHeader.objects.create(
            tenant=self.busy, transaction_date=self.this_month, reference_type='USAGE',
            reference_id=99, is_posted=True)
        cached = self.client.get('/api/platform/usage/')
        self.assertEqual(cached.data['computed_at'], first.data['computed_at'])
        refreshed = self.client.get('/api/platform/usage/?refresh=1')
        busy = next(r for r in refreshed.data['results'] if r['tenant_id'] == self.busy.pk)
        self.assertEqual(busy['movements_total'], 3)

    def test_company_endpoint_is_live(self):
        self.client.force_authenticate(self.root)
        response = self.client.get(f'/api/platform/companies/{self.busy.pk}/usage/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['counter_catalog'][0]['key'], 'journal_entries')
        self.assertEqual(response.data['counters']['journal_entries'], {'total': 2, 'month': 1})
        self.assertEqual(response.data['movements_total'], 2)
        self.assertEqual(self.client.get('/api/platform/companies/999999/usage/').status_code, 404)
