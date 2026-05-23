from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from tenants.models import Tenant, Currency
from logistics.models import LogisticsDeal
from partners.models import Partner
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token


def _set_tenant_on_client(client, tenant_id):
    """Helper to set X-Tenant-Id header."""
    client.credentials(HTTP_X_TENANT_ID=str(tenant_id))


class TenantIsolationDealTest(TestCase):
    """P-C-4: Tenant isolation for logistics deals."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(TenantID=10, CompanyName='Tenant A')
        cls.tenant_b = Tenant.objects.create(TenantID=20, CompanyName='Tenant B')
        cur, _ = Currency.objects.get_or_create(Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
        cls.user = User.objects.create_user(username='testuser', password='pass123')
        Token.objects.create(user=cls.user)

        partner_a = Partner.objects.create(
            tenant=cls.tenant_a, name='Partner A',
            code='PA001', account_receivable=None, account_payable=None,
        )
        partner_b = Partner.objects.create(
            tenant=cls.tenant_b, name='Partner B',
            code='PB001', account_receivable=None, account_payable=None,
        )

        cls.deal_a = LogisticsDeal.objects.create(
            tenant=cls.tenant_a, ref_number='D-A-001',
            partner=partner_a, order_date='2026-01-01',
            currency=cur, total_amount=1000,
        )
        cls.deal_b = LogisticsDeal.objects.create(
            tenant=cls.tenant_b, ref_number='D-B-001',
            partner=partner_b, order_date='2026-01-01',
            currency=cur, total_amount=2000,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_only_own_tenant_deals(self):
        _set_tenant_on_client(self.client, 10)
        resp = self.client.get('/api/logistics/deals/')
        self.assertEqual(resp.status_code, 200)
        ids = [d['id'] for d in resp.data]
        self.assertIn(self.deal_a.id, ids)
        self.assertNotIn(self.deal_b.id, ids)

    def test_create_without_tenant_header_returns_400(self):
        self.client.credentials()  # no X-Tenant-Id
        resp = self.client.post('/api/logistics/deals/', {
            'ref_number': 'D-NO-TENANT',
            'partner': 1,
            'order_date': '2026-01-01',
            'currency': 1,
            'total_amount': 500,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_cannot_access_other_tenant_deal(self):
        _set_tenant_on_client(self.client, 10)
        resp = self.client.get(f'/api/logistics/deals/{self.deal_b.id}/')
        self.assertEqual(resp.status_code, 404)
