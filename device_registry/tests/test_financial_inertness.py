"""THA-45 M1 — برهان الحياد المالي: اختبارٌ لا وعد.

ثلاثة أذرع: دورة حياة كاملة عبر الـAPI لا تحرّك دفتراً · استبطان `_meta` ينفي أي
علاقة إلى المحاسبة/المبيعات/اللوجستيات/المخزون · وصفر أثر عند إطفاء الوحدة.
ذراعٌ رابع رخيص: لا استيراد لتلك التطبيقات في كود الوحدة أصلاً — يمنع أن يتسلّل
لاحقاً signal أو hook محاسبي بلا FK ظاهرة.
"""
import pathlib
import re

from django.apps import apps
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from core.models import TenantModule
from sales.models import SalesInvoice
from tenants.models import Tenant, UserCompanyMembership


BASE = "/api/devices/records/"
IMEI_A = "490154203237518"
FINANCIAL_APPS = {"accounting", "sales", "logistics", "inventory"}
APP_DIR = pathlib.Path(__file__).resolve().parent.parent
_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(sorted(FINANCIAL_APPS)) + r")\b", re.MULTILINE,
)


class FinancialInertnessTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الحياد المالي")
        self.manager = User.objects.create_user("inertness-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager",
        )
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="sensitive_devices", enabled=True,
        )
        self.client.force_authenticate(self.manager)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def _ledger_counts(self):
        return {
            "journals": JournalHeader.objects.count(),
            "journal_lines": JournalLine.objects.count(),
            "accounts": Account.objects.count(),
            "sales_invoices": SalesInvoice.objects.count(),
        }

    def test_a_full_api_lifecycle_moves_no_ledger_row(self):
        before = self._ledger_counts()

        created = self.client.post(BASE, {
            "customer_name": "زبون التوثيق",
            "customer_phone": "0599123456",
            "model_name": "Galaxy S24",
            "serial_number": "SN-INERT-1",
            "imei": IMEI_A,
        }, format="json", **self.headers)
        self.assertEqual(created.status_code, 201, created.content)
        device_id = created.data["id"]

        self.client.get(f"{BASE}{device_id}/", **self.headers)
        self.client.patch(
            f"{BASE}{device_id}/", {"model_name": "Galaxy S24 Ultra"},
            format="json", **self.headers,
        )
        self.client.patch(
            f"{BASE}{device_id}/", {"status": "delivered"}, format="json", **self.headers,
        )
        self.client.get(f"{BASE}?q={IMEI_A}", **self.headers)
        self.client.delete(f"{BASE}{device_id}/", **self.headers)
        self.client.post(f"{BASE}{device_id}/restore/", {}, format="json", **self.headers)

        self.assertEqual(self._ledger_counts(), before)

    def test_no_model_field_relates_to_a_financial_app(self):
        offenders = []
        for model in apps.get_app_config("device_registry").get_models():
            for field in model._meta.get_fields():
                related = getattr(field, "related_model", None)
                if related is not None and related._meta.app_label in FINANCIAL_APPS:
                    offenders.append(f"{model.__name__}.{field.name} → {related._meta.label}")

        self.assertEqual(offenders, [])

    def test_module_code_does_not_import_a_financial_app(self):
        offenders = []
        for path in sorted(APP_DIR.rglob("*.py")):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            hits = _IMPORT_RE.findall(path.read_text(encoding="utf-8"))
            offenders.extend(f"{path.name}: {hit}" for hit in hits)

        self.assertEqual(offenders, [])

    def test_turning_the_module_off_leaves_no_reachable_surface(self):
        created = self.client.post(BASE, {
            "customer_name": "زبون",
            "customer_phone": "0599123456",
            "model_name": "Pixel 9",
            "serial_number": "SN-INERT-2",
            "imei": IMEI_A,
        }, format="json", **self.headers)
        self.assertEqual(created.status_code, 201, created.content)
        self.license.delete()

        response = self.client.get(BASE, **self.headers)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self._ledger_counts()["journals"], 0)
