from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import DatabaseError, connection
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import AccountingAuditLog
from core.models import ActivityLog, TenantModule
from core.modules import invalidate_module_cache, module_enabled, require_module
from tenants.models import Tenant, UserCompanyMembership
from tenants.services import create_company


LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "accountant-portal-module-tests",
    }
}


class ModuleEnabledTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(CompanyName="شركة اختبار الوحدات")

    def test_returns_false_without_a_tenant_or_for_an_unknown_module(self):
        self.assertFalse(module_enabled(None, "accountant_portal"))
        self.assertFalse(module_enabled(self.tenant, "unknown"))

    def test_legacy_import_module_reads_tenant_flag_without_queries(self):
        self.tenant.import_enabled = True

        with self.assertNumQueries(0):
            self.assertTrue(module_enabled(self.tenant, "import"))

    def test_repeated_checks_query_once_per_request(self):
        TenantModule.objects.create(
            tenant=self.tenant,
            module_key="accountant_portal",
            enabled=True,
        )
        request = RequestFactory().get("/api/accountant/")

        with patch("core.modules.get_current_request", return_value=request):
            with self.assertNumQueries(1):
                self.assertTrue(module_enabled(self.tenant, "accountant_portal"))
                self.assertTrue(module_enabled(self.tenant, "accountant_portal"))

    def test_require_module_hides_disabled_module_with_404(self):
        request = RequestFactory().get("/api/accountant/")

        with patch("core.tenant_utils.get_tenant", return_value=self.tenant):
            with self.assertRaises(Http404):
                require_module(request, "accountant_portal")


@override_settings(CACHES=LOCMEM_CACHE)
class PlatformModuleToggleTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="module-root", email="module-root@example.com", password="x"
        )
        cls.manager = User.objects.create_user(username="module-manager", password="x")
        cls.tenant = Tenant.objects.create(CompanyName="شركة تبديل الوحدة")
        UserCompanyMembership.objects.create(
            user=cls.manager,
            tenant=cls.tenant,
            role="manager",
        )

    def setUp(self):
        cache.clear()

    def test_company_manager_cannot_toggle_a_platform_module(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(
            f"/api/platform/companies/{self.tenant.pk}/modules/",
            {"module_key": "accountant_portal", "enabled": True},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(TenantModule.objects.filter(tenant=self.tenant).exists())

    def test_super_admin_toggles_module_invalidates_cache_and_writes_audit(self):
        with patch("core.modules.get_current_request", return_value=None):
            self.assertFalse(module_enabled(self.tenant, "accountant_portal"))

        self.client.force_authenticate(self.superuser)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/platform/companies/{self.tenant.pk}/modules/",
                {
                    "module_key": "accountant_portal",
                    "enabled": True,
                    "plan_note": "Pilot",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.data,
            {
                "module_key": "accountant_portal",
                "enabled": True,
                "plan_note": "Pilot",
            },
        )
        row = TenantModule.objects.get(
            tenant=self.tenant,
            module_key="accountant_portal",
        )
        self.assertTrue(row.enabled)
        self.assertEqual(row.enabled_by, self.superuser)
        self.assertIsNotNone(row.enabled_at)
        with patch("core.modules.get_current_request", return_value=None):
            self.assertTrue(module_enabled(self.tenant, "accountant_portal"))
        self.assertTrue(
            AccountingAuditLog.objects.filter(
                tenant=self.tenant,
                action="MODULE_TOGGLED",
                model_name="TenantModule",
                object_id=row.pk,
            ).exists()
        )
        self.assertTrue(
            ActivityLog.objects.filter(
                tenant=self.tenant,
                action="update",
                entity_type="tenant_module",
                entity_id=row.pk,
                metadata__event_code="MODULE_TOGGLED",
            ).exists()
        )

    def test_toggle_schedules_cache_invalidation_after_commit(self):
        self.client.force_authenticate(self.superuser)

        with patch("core.platform_admin_api.transaction.on_commit") as on_commit:
            response = self.client.post(
                f"/api/platform/companies/{self.tenant.pk}/modules/",
                {"module_key": "accountant_portal", "enabled": True},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        on_commit.assert_called_once()

    def test_financial_audit_failure_rolls_back_module_toggle(self):
        self.client.force_authenticate(self.superuser)

        with patch(
            "accounting.services.AccountingAuditLog.objects.create",
            side_effect=DatabaseError("audit unavailable"),
        ):
            response = self.client.post(
                f"/api/platform/companies/{self.tenant.pk}/modules/",
                {"module_key": "accountant_portal", "enabled": True},
                format="json",
            )

        self.assertEqual(response.status_code, 500)
        self.assertFalse(
            TenantModule.objects.filter(
                tenant=self.tenant,
                module_key="accountant_portal",
            ).exists()
        )

    def test_disabling_warm_module_cache_takes_effect_after_commit(self):
        TenantModule.objects.create(
            tenant=self.tenant,
            module_key="accountant_portal",
            enabled=True,
        )
        with patch("core.modules.get_current_request", return_value=None):
            self.assertTrue(module_enabled(self.tenant, "accountant_portal"))

        self.client.force_authenticate(self.superuser)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/platform/companies/{self.tenant.pk}/modules/",
                {"module_key": "accountant_portal", "enabled": False},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        with patch("core.modules.get_current_request", return_value=None):
            self.assertFalse(module_enabled(self.tenant, "accountant_portal"))

    def test_legacy_import_toggle_does_not_create_tenant_module_row(self):
        self.client.force_authenticate(self.superuser)

        response = self.client.post(
            f"/api/platform/companies/{self.tenant.pk}/modules/",
            {"module_key": "import", "enabled": True, "plan_note": "Legacy"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.import_enabled)
        self.assertFalse(
            TenantModule.objects.filter(
                tenant=self.tenant,
                module_key="import",
            ).exists()
        )

    def test_unknown_module_is_rejected(self):
        self.client.force_authenticate(self.superuser)

        response = self.client.post(
            f"/api/platform/companies/{self.tenant.pk}/modules/",
            {"module_key": "unknown", "enabled": True},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(TenantModule.objects.filter(tenant=self.tenant).exists())


class DisabledModuleSurfaceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="module-owner", password="x")
        cls.tenant = create_company("شركة سطح الوحدة", cls.owner)

    def setUp(self):
        self.client.force_authenticate(self.owner)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def test_accountant_routes_are_not_exposed_before_the_module_api_exists(self):
        paths = [
            "/api/accountant/",
            "/api/accountant/signup/",
            "/api/accountant/engagements/",
            "/api/accountant/workspace/companies/",
            "/api/accountant/tax/periods/",
        ]

        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, **self.headers).status_code, 404)

    def test_disabled_module_adds_no_permissions_or_role(self):
        mine = self.client.get("/api/permissions/me/", **self.headers)
        matrix = self.client.get("/api/permissions/matrix/", **self.headers)

        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertFalse(any(key.startswith("tax.") for key in mine.data["permissions"]))
        self.assertEqual(matrix.status_code, 200, matrix.content)
        self.assertNotIn("legal_accountant", str(matrix.data))
        self.assertNotIn("tax.", str(matrix.data))

    def test_accountant_portal_license_does_not_change_dashboard_query_count(self):
        cache.clear()
        with CaptureQueriesContext(connection) as disabled_queries:
            disabled = self.client.get("/api/dashboard/", **self.headers)
        self.assertEqual(disabled.status_code, 200, disabled.content)

        TenantModule.objects.create(
            tenant=self.tenant,
            module_key="accountant_portal",
            enabled=True,
        )
        invalidate_module_cache(self.tenant.pk)
        cache.clear()
        with CaptureQueriesContext(connection) as enabled_queries:
            enabled = self.client.get("/api/dashboard/", **self.headers)
        self.assertEqual(enabled.status_code, 200, enabled.content)

        self.assertEqual(len(enabled_queries), len(disabled_queries))
        self.assertFalse(
            any("tenant_modules" in query["sql"] for query in enabled_queries.captured_queries)
        )
