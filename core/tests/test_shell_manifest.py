"""ISSUE #83 — بيان الواجهة: `shell_manifest()` وتسليمه على `/api/permissions/me`."""
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from core.shell_manifest import shell_manifest
from tenants.services import create_company


class ShellManifestFunctionTest(SimpleTestCase):
    def test_general_has_no_manifest(self):
        """اختبار تراجعٍ صريح: `general` بلا بيان — الشريط اليدوي يبقى حرفياً."""
        self.assertIsNone(shell_manifest("general"))
        self.assertIsNone(shell_manifest(None))
        self.assertIsNone(shell_manifest(""))
        self.assertIsNone(shell_manifest("not-a-real-template"))

    def test_accounting_office_manifest_shape(self):
        """ISSUE #271 — بيانُ الموديول الجديد: بلا أتعاب ولا مكتبٍ قديم."""
        manifest = shell_manifest("accounting_office")
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["start_view"], "office-clients")
        self.assertEqual(manifest["first_action"]["view"], "office-clients")
        self.assertEqual(manifest["first_action"]["label_term"], "action.add_office_client")
        self.assertEqual(manifest["empty_state_term"], "empty.office_shell")
        # #275: «اليوم» أوّلُ المجموعات — الشاشةُ التي يفتحها الموظف صباحاً.
        self.assertEqual(
            [group["id"] for group in manifest["groups"]][0], "today",
        )
        self.assertEqual(
            {group["id"]: group["views"] for group in manifest["groups"]},
            {
                "today": ["office-today"],
                # #280/ب: «جاهز للإرسال» مجموعةٌ ثانيةٌ بعد «اليوم» مباشرةً.
                "ready-to-send": ["office-ready-to-send"],
                # #282/أ٢/٢: «المسودّات» — مسودّاتُ الأتعاب وأفعالُ اعتمادها.
                "fee-drafts": ["office-fee-drafts"],
                # #289: لوحةُ صاحب المكتب — مجموعةٌ مستقلّةٌ بعد شاشتَي العمل،
                # والموجّه يحرسها بالدور (مالك) والخادمُ يردّ غيرَه 403.
                "dashboard": ["office-dashboard"],
                "clients": ["office-clients"],
                # #274: التقويم شاشةٌ مستقلّة، فمجموعتُه مستقلّة كإعدادات المكتب.
                "calendar": ["office-calendar"],
                "office-settings": ["office-settings"],
                "treasury": [
                    "cash-boxes", "accounting-banks", "accounting-bank-reconciliation",
                    "accounting-cheques", "accounting-expense-vouchers",
                    "accounting-revenue-vouchers", "credit-debit-notes",
                    "supplier-payments", "supplier-management",
                ],
                "office-accounting": [
                    "accounting-coa", "accounting-journals", "accounting-journal-entry",
                    "accounting-general-ledger", "accounting-trial-balance",
                    "accounting-vat-report", "accounting-fiscal-periods",
                    "accounting-opening-balances", "accounting-exchange-rates",
                    "accounting-balance-sheet", "accounting-income-statement",
                    "accounting-vat-statements", "accounting-year-end-close",
                ],
                "reports": [
                    "reports", "stock-movements", "accounting-trial-balance",
                    "accounting-income-statement", "accounting-balance-sheet",
                    "accounting-vat-report",
                ],
            },
        )
        every_view = {view for group in manifest["groups"] for view in group["views"]}
        self.assertNotIn("client-books", every_view)
        self.assertNotIn("office-desk", every_view)
        self.assertNotIn("sales-invoices", every_view, "لا مجموعةَ أتعابٍ في هذه التذكرة")

    def test_manifest_does_not_mutate_shared_state_across_calls(self):
        """`shell_manifest` يعيد نسخةً عميقة — تعديل صفوف مجموعةٍ في ناتج نداءٍ
        لا يُصيب نداءً تالياً (لا مرجعاً مشتركاً إلى `SHELL_MANIFESTS`)."""
        first = shell_manifest("accounting_office")
        first["groups"][0]["views"].append("corrupted-view")
        second = shell_manifest("accounting_office")
        self.assertNotIn("corrupted-view", second["groups"][0]["views"])


class PermissionsMePayloadCarriesShellTest(APITestCase):
    """البيان يصل على حمولة `/api/permissions/me` نفسها — لا نقطة API مستقلة."""

    def _as(self, user, tenant):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(tenant.TenantID)}

    def test_general_company_sees_no_shell(self):
        user = User.objects.create_user(username="shell-gen-owner", password="x")
        tenant = create_company("شركة عامة للبيان", user)
        res = self.client.get("/api/permissions/me/", **self._as(user, tenant))
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIn("shell", body)
        self.assertIsNone(body["shell"])

    def test_accounting_office_company_sees_its_manifest(self):
        user = User.objects.create_user(username="shell-office-owner", password="x")
        tenant = create_company("مكتب محاسبة للبيان", user, template="accounting_office")
        res = self.client.get("/api/permissions/me/", **self._as(user, tenant))
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIsNotNone(body["shell"])
        self.assertEqual(body["shell"]["start_view"], "office-clients")
        self.assertEqual(body["shell"]["first_action"]["view"], "office-clients")
