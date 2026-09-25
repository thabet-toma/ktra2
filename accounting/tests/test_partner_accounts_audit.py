"""حسابات الأطراف في الشجرة: الأب الغائب يُكمَل، والخلل يُعرض للمستخدم، والأمر يصلح.

إنتاج (شركة 1): 2109 «ذمم الناقلين» غائب فكان الناقل يُنشأ بلا حساب بصمت —
`sync_partner_accounting` تبتلع أخطاءها كي لا يسقط حفظ الطرف.
"""
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting.models import Account, AccountingAuditLog
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class PartnerParentHealingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ppheal", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الأب الغائب", cls.user)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        # شجرة بُذرت قبل إضافة 2109 — حال الإنتاج.
        Account.objects.filter(tenant=self.tenant, code="2109").delete()

    def test_carrier_gets_an_account_when_2109_was_missing(self):
        carrier = Partner.objects.create(tenant=self.tenant, name="ناقل", partner_type="Carrier")
        carrier.refresh_from_db()
        self.assertIsNotNone(carrier.linked_account_id)
        self.assertEqual(carrier.linked_account.parent.code, "2109")
        self.assertTrue(Account.objects.filter(tenant=self.tenant, code="2109").exists())

    def test_save_response_warns_when_no_account_could_be_made(self):
        with mock.patch("accounting.api._ensure_partner_parent"):
            res = self.client.post(
                "/api/partners/", {"name": "اسامه", "partner_type": "Carrier"},
                format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn("2109", res.data["account_warning"])
        self.assertIsNone(res.data["linked_account"])

    def test_healthy_save_has_no_warning(self):
        res = self.client.post(
            "/api/partners/", {"name": "حاييم", "partner_type": "CustomsBroker"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertNotIn("account_warning", res.data)


class AuditPartnerAccountsCommandTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ppaudit", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة التدقيق", cls.user)

    def _run(self, *args):
        out = StringIO()
        call_command("audit_partner_accounts", "--tenant", str(self.tenant.TenantID), *args, stdout=out)
        return out.getvalue()

    def test_reports_then_fixes_missing_and_misfiled_accounts_idempotently(self):
        Account.objects.filter(tenant=self.tenant, code="2109").delete()
        with mock.patch("accounting.api._ensure_partner_parent"):
            carrier = Partner.objects.create(tenant=self.tenant, name="ناقل بلا حساب", partner_type="Carrier")
        broker = Partner.objects.create(tenant=self.tenant, name="مخلّص", partner_type="CustomsBroker")
        broker.refresh_from_db()
        # حساب المخلّص نُقل خطأً تحت الدائنين العامّين.
        wrong_parent = Account.objects.get(tenant=self.tenant, code="2101")
        Account.objects.filter(pk=broker.linked_account_id).update(parent=wrong_parent)
        healthy = Partner.objects.create(tenant=self.tenant, name="مورد سليم", partner_type="Supplier")

        report = self._run()
        self.assertIn(f"#{carrier.id}", report)
        self.assertIn(f"#{broker.id}", report)
        self.assertNotIn(f"#{healthy.id} ", report)
        carrier.refresh_from_db()
        self.assertIsNone(carrier.linked_account_id)  # القراءة لا تكتب

        self._run("--apply")
        carrier.refresh_from_db()
        broker.refresh_from_db()
        self.assertEqual(carrier.linked_account.parent.code, "2109")
        self.assertEqual(broker.linked_account.parent.code, "2107")
        self.assertEqual(
            AccountingAuditLog.objects.filter(model_name="Partner", object_id__in=[carrier.id, broker.id]).count(),
            2,
        )

        self.assertIn("0 طرفاً بخلل", self._run("--apply"))
