"""T-IMPOFFER — فصل الموردين الدوليين عن المحليين.

المالك: «بدنا نفصل الموردين الدوليين عن المحليين.»

الفصل لا يجوز أن يُخفي موردي الشركة القائمين: الموردون الذين لم يُصنَّفوا بعد
(`supplier_scope=''`) يظهرون في **الجانبين** حتى يُصنَّفهم المستخدم، وإلا لوجد
المالك شاشة استيراد فارغة بعد التحديث.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from partners.models import Partner
from tenants.models import Tenant, UserCompanyMembership


class SupplierScopeFilterTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=984, CompanyName='Supplier Scope Co')
        cls.user = User.objects.create_user(username='supplier-scope', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.international = Partner.objects.create(
            tenant=cls.tenant, name='Shenzhen Factory', partner_type='Supplier',
            supplier_scope=Partner.SUPPLIER_SCOPE_INTERNATIONAL,
        )
        cls.local = Partner.objects.create(
            tenant=cls.tenant, name='مورد محلي', partner_type='Supplier',
            supplier_scope=Partner.SUPPLIER_SCOPE_LOCAL,
        )
        cls.unclassified = Partner.objects.create(
            tenant=cls.tenant, name='مورد قديم', partner_type='Supplier',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def names(self, query):
        response = self.client.get(f'/api/partners/lookup/?limit=100&{query}')
        self.assertEqual(response.status_code, 200, response.content)
        return {row['name'] for row in response.data}

    def test_unclassified_supplier_stays_visible_on_both_sides(self):
        international = self.names('partner_type=Supplier&supplier_scope=international')
        self.assertIn('Shenzhen Factory', international)
        self.assertIn('مورد قديم', international)
        self.assertNotIn('مورد محلي', international)

        local = self.names('partner_type=Supplier&supplier_scope=local')
        self.assertIn('مورد محلي', local)
        self.assertIn('مورد قديم', local)
        self.assertNotIn('Shenzhen Factory', local)

    def test_no_scope_filter_returns_every_supplier(self):
        everyone = self.names('partner_type=Supplier')
        self.assertEqual(
            everyone, {'Shenzhen Factory', 'مورد محلي', 'مورد قديم'},
        )

    def test_scope_is_readable_and_writable_through_the_partner_card(self):
        detail = self.client.get(f'/api/partners/{self.unclassified.id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data['supplier_scope'], '')

        patched = self.client.patch(
            f'/api/partners/{self.unclassified.id}/',
            {'supplier_scope': 'international'}, format='json',
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        self.unclassified.refresh_from_db()
        self.assertEqual(
            self.unclassified.supplier_scope, Partner.SUPPLIER_SCOPE_INTERNATIONAL,
        )
