"""B-3 — قراءةُ طلبيات الشراء وعروض المورّدين تشترط صلاحيةَ عرضِ نطاقها.

قبلها كان `TenantRolePermission` يمرّر كلَّ قراءة، فيقرأ أيُّ عضوٍ في الشركة
مستنداتِ الشراء المحلي والاستيراد معاً. الآن:
- النطاق المحلي ← `purchase.invoice.view` (مفتاحُ قراءة المشتريات القائم).
- نطاق الاستيراد ← `import.procurement.view` (مفتاحٌ جديد — لا مفتاحَ قراءةٍ
  للاستيراد قبله).
الفحصُ على **نطاق المستند نفسه** في التفصيل، لا على القائمة وحدها.
"""
import importlib
from datetime import date

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

from logistics.models import PurchaseRFQ, SupplierQuotation
from tenants.models import (
    Currency, MemberPermission, RolePermission, Tenant, UserCompanyMembership,
)


class ProcurementScopeViewPermissionTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=991, CompanyName='Scope Co')
        cls.other_tenant = Tenant.objects.create(TenantID=992, CompanyName='Other Scope Co')
        cls.currency = Currency.objects.create(Code='ILS', Name='Shekel', IsBaseCurrency=True)

        def member(username, role, tenant=None):
            user = User.objects.create_user(username=username, password='x')
            membership = UserCompanyMembership.objects.create(
                user=user, tenant=tenant or cls.tenant, role=role)
            return user, membership

        cls.manager, _ = member('scope-manager', 'manager')
        cls.procurement, _ = member('scope-procurement', 'procurement')
        cls.accountant, _ = member('scope-accountant', 'accountant')
        # موظفٌ عام: يملك قراءة المشتريات افتراضياً، ولا شيء من الاستيراد.
        cls.staff, _ = member('scope-staff', 'staff')
        # موظف خدمة ذاتية: لا قراءة مشتريات ولا استيراد.
        cls.ess, _ = member('scope-ess', 'ess')
        # موظفٌ مُنح الاستيراد ومُنع المحلي صراحةً.
        cls.importer, importer_membership = member('scope-importer', 'staff')
        MemberPermission.objects.create(
            membership=importer_membership,
            permission_key='import.procurement.view', allowed=True)
        MemberPermission.objects.create(
            membership=importer_membership,
            permission_key='purchase.invoice.view', allowed=False)

        cls.local_rfq = PurchaseRFQ.objects.create(
            tenant=cls.tenant, scope='local', rfq_date=date(2026, 8, 1))
        cls.import_rfq = PurchaseRFQ.objects.create(
            tenant=cls.tenant, scope='import', rfq_date=date(2026, 8, 1))
        cls.other_rfq = PurchaseRFQ.objects.create(
            tenant=cls.other_tenant, scope='local', rfq_date=date(2026, 8, 1))
        cls.local_quote = SupplierQuotation.objects.create(
            tenant=cls.tenant, scope='local', quotation_number='PQ-1', supplier_draft_name='مورد محلي',
            quotation_date=date(2026, 8, 2), currency=cls.currency)
        cls.import_quote = SupplierQuotation.objects.create(
            tenant=cls.tenant, scope='import', quotation_number='IQ-1', supplier_draft_name='مصنع',
            quotation_date=date(2026, 8, 2), currency=cls.currency)

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults['HTTP_X_TENANT_ID'] = str(self.tenant.TenantID)
        return client

    # ── الطلبية ──────────────────────────────────────────────────────────
    def test_member_without_import_view_gets_403_on_import_rfq_list_and_retrieve(self):
        client = self._client(self.staff)
        self.assertEqual(
            client.get('/api/logistics/purchase-rfqs/?scope=import').status_code, 403)
        self.assertEqual(
            client.get(f'/api/logistics/purchase-rfqs/{self.import_rfq.pk}/').status_code, 403)
        self.assertEqual(
            client.get(f'/api/logistics/purchase-rfqs/{self.import_rfq.pk}/comparison/').status_code,
            403)
        # والمحلي يبقى مقروءاً له — قراءة المشتريات من صلاحيات دوره.
        self.assertEqual(
            client.get('/api/logistics/purchase-rfqs/?scope=local').status_code, 200)
        self.assertEqual(
            client.get(f'/api/logistics/purchase-rfqs/{self.local_rfq.pk}/').status_code, 200)

    def test_member_without_local_view_gets_403_on_local_list_and_retrieve(self):
        client = self._client(self.ess)
        self.assertEqual(client.get('/api/logistics/purchase-rfqs/').status_code, 403)
        self.assertEqual(
            client.get('/api/logistics/purchase-rfqs/?scope=local').status_code, 403)
        self.assertEqual(
            client.get(f'/api/logistics/purchase-rfqs/{self.local_rfq.pk}/').status_code, 403)

    def test_import_granted_member_cannot_retrieve_local_rfq_by_id(self):
        client = self._client(self.importer)
        self.assertEqual(
            client.get(f'/api/logistics/purchase-rfqs/{self.local_rfq.pk}/').status_code, 403)
        self.assertEqual(
            client.get('/api/logistics/purchase-rfqs/?scope=local').status_code, 403)
        ok = client.get(f'/api/logistics/purchase-rfqs/{self.import_rfq.pk}/')
        self.assertEqual(ok.status_code, 200, ok.content)
        listed = client.get('/api/logistics/purchase-rfqs/?scope=import')
        self.assertEqual(listed.status_code, 200, listed.content)

    def test_manager_procurement_and_accountant_keep_both_scopes(self):
        for user in (self.manager, self.procurement, self.accountant):
            client = self._client(user)
            for rfq in (self.local_rfq, self.import_rfq):
                response = client.get(f'/api/logistics/purchase-rfqs/{rfq.pk}/')
                self.assertEqual(response.status_code, 200, (user.username, rfq.scope))
            for quote in (self.local_quote, self.import_quote):
                response = client.get(f'/api/logistics/supplier-quotations/{quote.pk}/')
                self.assertEqual(response.status_code, 200, (user.username, quote.scope))
            for scope in ('local', 'import'):
                self.assertEqual(
                    client.get(f'/api/logistics/purchase-rfqs/?scope={scope}').status_code, 200)

    def test_tenant_isolation_still_404_for_other_company_rfq(self):
        client = self._client(self.manager)
        self.assertEqual(
            client.get(f'/api/logistics/purchase-rfqs/{self.other_rfq.pk}/').status_code, 404)

    # ── عرض المورّد ──────────────────────────────────────────────────────
    def test_supplier_quotation_read_follows_its_scope(self):
        staff = self._client(self.staff)
        self.assertEqual(
            staff.get('/api/logistics/supplier-quotations/?scope=import').status_code, 403)
        self.assertEqual(
            staff.get(f'/api/logistics/supplier-quotations/{self.import_quote.pk}/').status_code,
            403)
        self.assertEqual(
            staff.get(f'/api/logistics/supplier-quotations/{self.local_quote.pk}/').status_code,
            200)

        importer = self._client(self.importer)
        self.assertEqual(
            importer.get(f'/api/logistics/supplier-quotations/{self.local_quote.pk}/').status_code,
            403)
        self.assertEqual(
            importer.get(f'/api/logistics/supplier-quotations/{self.import_quote.pk}/').status_code,
            200)
        self.assertEqual(
            importer.get('/api/logistics/supplier-quotations/').status_code, 403)

    # ── الهجرة: من مُنح الاستيراد صراحةً يرث قراءته ──────────────────────
    def test_migration_grants_import_view_wherever_an_import_key_was_granted(self):
        migration = importlib.import_module(
            'tenants.migrations.0035_grant_import_procurement_view')
        RolePermission.objects.create(
            tenant=self.tenant, role='sales',
            permission_key='import.deal.manage', allowed=True)
        RolePermission.objects.create(
            tenant=self.tenant, role='viewer',
            permission_key='import.shipment.manage', allowed=False)
        membership = UserCompanyMembership.objects.get(user=self.staff)
        MemberPermission.objects.create(
            membership=membership, permission_key='import.doc.unpost', allowed=True)

        migration.grant_import_view_wherever_import_was_granted(django_apps, None)

        self.assertTrue(RolePermission.objects.filter(
            tenant=self.tenant, role='sales',
            permission_key='import.procurement.view', allowed=True).exists())
        self.assertFalse(RolePermission.objects.filter(
            tenant=self.tenant, role='viewer',
            permission_key='import.procurement.view').exists())
        self.assertTrue(MemberPermission.objects.filter(
            membership=membership,
            permission_key='import.procurement.view', allowed=True).exists())
        # idempotent
        migration.grant_import_view_wherever_import_was_granted(django_apps, None)
        self.assertEqual(MemberPermission.objects.filter(
            membership=membership, permission_key='import.procurement.view').count(), 1)
