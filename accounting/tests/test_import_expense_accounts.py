"""رسوم الفواتير الدولية → حسابات تحت «53 مصاريف الاستيراد المباشرة».

الكتابة بالاسم تكفي: إن وُجد الحساب يُربط، وإلا يُنشأ ابناً مباشراً للبند «53».
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounting.models import Account
from accounting.services import resolve_import_expense_account
from tenants.models import Tenant, UserCompanyMembership


class ResolveImportExpenseAccountServiceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=950, CompanyName='Imp Fees Co', import_enabled=True)
        cls.parent = Account.objects.create(
            tenant=cls.tenant, code='53', name='مصاريف الاستيراد المباشرة', account_type='Expense',
        )
        Account.objects.create(
            tenant=cls.tenant, code='5301', name='مصاريف الشحن الدولي (International Shipping)',
            account_type='Expense', parent=cls.parent,
        )
        Account.objects.create(
            tenant=cls.tenant, code='5307', name='رسوم استيراد متنوعة (Misc. Import Fees)',
            account_type='Expense', parent=cls.parent,
        )

    def test_existing_account_matched_by_arabic_name(self):
        account, created = resolve_import_expense_account(self.tenant.pk, ' مصاريف الشحن  الدولي ')
        self.assertFalse(created)
        self.assertEqual(account.code, '5301')

    def test_new_name_creates_child_of_53(self):
        account, created = resolve_import_expense_account(self.tenant.pk, 'تكاليف كترا')
        self.assertTrue(created)
        self.assertEqual(account.code, '5308')
        self.assertEqual(account.parent_id, self.parent.pk)
        self.assertEqual(account.account_type, 'Expense')
        self.assertEqual(account.name, 'تكاليف كترا')

    def test_same_name_twice_does_not_duplicate(self):
        first, _ = resolve_import_expense_account(self.tenant.pk, 'تكاليف كترا')
        second, created = resolve_import_expense_account(self.tenant.pk, 'تكاليف كترا')
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)

    def test_blank_name_returns_nothing(self):
        account, created = resolve_import_expense_account(self.tenant.pk, '   ')
        self.assertIsNone(account)
        self.assertFalse(created)

    def test_missing_parent_returns_nothing(self):
        other = Tenant.objects.create(TenantID=951, CompanyName='No Coa Co', import_enabled=True)
        account, created = resolve_import_expense_account(other.pk, 'تكاليف كترا')
        self.assertIsNone(account)
        self.assertFalse(created)


class ResolveImportExpenseEndpointTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=952, CompanyName='Imp Fees Api', import_enabled=True)
        cls.parent = Account.objects.create(
            tenant=cls.tenant, code='53', name='مصاريف الاستيراد المباشرة', account_type='Expense',
        )
        cls.manager = User.objects.create_user(username='ifmgr', password='x', email='ifmgr@x.co')
        cls.staff = User.objects.create_user(username='ifstf', password='x', email='ifstf@x.co')
        UserCompanyMembership.objects.create(user=cls.manager, tenant=cls.tenant, role='manager')
        UserCompanyMembership.objects.create(user=cls.staff, tenant=cls.tenant, role='staff')

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        c.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        return c

    def test_manager_creates_then_reuses_account(self):
        url = '/api/accounting/accounts/resolve-import-expense/'
        first = self._client(self.manager).post(url, {'name': 'تكاليف كترا'}, format='json')
        self.assertEqual(first.status_code, 201, first.content)
        self.assertTrue(first.data['created'])
        self.assertEqual(first.data['code'], '5301')

        second = self._client(self.manager).post(url, {'name': 'تكاليف كترا'}, format='json')
        self.assertEqual(second.status_code, 200, second.content)
        self.assertFalse(second.data['created'])
        self.assertEqual(second.data['id'], first.data['id'])

    def test_user_without_import_access_is_rejected(self):
        resp = self._client(self.staff).post(
            '/api/accounting/accounts/resolve-import-expense/',
            {'name': 'تكاليف كترا'}, format='json',
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(Account.objects.filter(tenant=self.tenant, name='تكاليف كترا').exists())
