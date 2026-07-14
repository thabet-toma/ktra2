"""M4 — clearance cost is read from `lines` (the cost_lines model shim is gone).

Locks the D2 replacement: `clearance_cost_line_dicts` rebuilds the {label, amount}
list from LogisticsClearanceLine rows, and the serializer still exposes cost_lines
(derived from lines) so existing frontend read paths keep working.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from logistics.models import LogisticsShipment, LogisticsClearance, LogisticsClearanceLine
from logistics.landed_cost import clearance_cost_line_dicts, sum_cost_lines_all_ils


class CostSourceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=960, CompanyName='M4 Co')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
        cls.user = User.objects.create_user(username='m4_user', password='x')
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        self.shipment = LogisticsShipment.objects.create(tenant=self.tenant, shipment_number='SH-M4')
        self.clr = LogisticsClearance.objects.create(tenant=self.tenant, shipment=self.shipment)
        LogisticsClearanceLine.objects.create(
            clearance=self.clr, seq=1, line_type='vat', description='ضريبة',
            debit=Decimal('300'), credit=Decimal('0'))
        LogisticsClearanceLine.objects.create(
            clearance=self.clr, seq=2, line_type='other', description='خصم',
            debit=Decimal('0'), credit=Decimal('50'))

    def test_cost_line_dicts_from_lines(self):
        rows = clearance_cost_line_dicts(self.clr)
        by_label = {r['label']: r['amount'] for r in rows}
        self.assertEqual(by_label['ضريبة'], Decimal('300'))
        self.assertEqual(by_label['خصم'], Decimal('-50'))  # credit → negative
        self.assertEqual(sum_cost_lines_all_ils(self.clr), Decimal('250.00'))

    def test_serializer_still_exposes_cost_lines_from_lines(self):
        resp = self.client.get(f'/api/logistics/clearances/{self.clr.id}/')
        self.assertEqual(resp.status_code, 200, resp.content)
        cost_lines = resp.data.get('cost_lines')
        self.assertIsNotNone(cost_lines)
        labels = {c['label']: c['amount'] for c in cost_lines}
        self.assertEqual(labels['ضريبة'], 300.0)
        self.assertEqual(labels['خصم'], -50.0)

    def test_model_has_no_cost_lines_property(self):
        self.assertFalse(hasattr(LogisticsClearance, 'cost_lines'))
