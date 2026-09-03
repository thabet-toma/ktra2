"""ISSUE #83 — بيان الواجهة: `shell_manifest()` وتسليمه على `/api/permissions/me`."""
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from core.shell_manifest import UNBUILT_VIEWS, shell_manifest
from tenants.services import create_company


class ShellManifestFunctionTest(SimpleTestCase):
    def test_general_has_no_manifest(self):
        """اختبار تراجعٍ صريح: `general` بلا بيان — الشريط اليدوي يبقى حرفياً."""
        self.assertIsNone(shell_manifest("general"))
        self.assertIsNone(shell_manifest(None))
        self.assertIsNone(shell_manifest(""))
        self.assertIsNone(shell_manifest("not-a-real-template"))

    def test_accounting_firm_manifest_shape(self):
        manifest = shell_manifest("accounting_firm")
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["start_view"], "dashboard")
        self.assertEqual(manifest["first_action"]["view"], "sales-invoices")
        self.assertEqual(manifest["first_action"]["label_term"], "doc.sales_invoice")
        group_ids = [g["id"] for g in manifest["groups"]]
        self.assertEqual(
            group_ids,
            ["home", "clients", "fees", "treasury", "office-accounting", "reports", "office"],
        )

    def test_client_book_manifest_shape(self):
        manifest = shell_manifest("client_book")
        self.assertIsNotNone(manifest)
        self.assertEqual(manifest["first_action"]["view"], "document-coding")
        group_ids = [g["id"] for g in manifest["groups"]]
        self.assertEqual(
            group_ids,
            ["home", "entry", "receipt-payment", "parties", "accounts", "results",
             "declarations", "settings"],
        )

    def test_client_book_shows_where_profit_and_tax_land(self):
        """بلاغ المالك: «مش واضح لما أسجّل مصروف وإيراد وين ببين الأرباح عشان الضريبة».

        الأربعة (إيراد · مصروف · ربح · ضريبة صافية) كانت تُعرض على شاشة البداية
        وحدها (`ClientBookFinancialPosition`)، ولا قائمةَ دخلٍ ولا ميزانيةً في
        الشريط كلّه — فمن غادر شاشة البداية لم يجد طريق عودة، وبدا القالبُ
        دفترَ إدخالٍ بلا نتيجة.
        """
        views = {v for g in shell_manifest("client_book")["groups"] for v in g["views"]}
        self.assertIn("accounting-income-statement", views)
        self.assertIn("accounting-balance-sheet", views)
        self.assertIn("dashboard", views)

    def test_client_book_entry_group_carries_both_vouchers(self):
        """سندا المصروف والإيراد مادّةُ هذا القالب اليومية — في «الإدخال» معاً.

        سند الإيراد كان بلا شاشةٍ في الواجهة أصلاً (نقاطه الخادمية من #80 بلا
        مستدعٍ)، فلم يكن له مكانٌ يُذكر فيه.
        """
        entry = next(
            g for g in shell_manifest("client_book")["groups"] if g["id"] == "entry")
        self.assertIn("accounting-expense-vouchers", entry["views"])
        self.assertIn("accounting-revenue-vouchers", entry["views"])

    def test_unbuilt_views_are_declared_not_hidden(self):
        """القاعدة الملزِمة تخصّ القناع لا البناء: شاشةٌ لم تُبنَ بعد تبقى مذكورة،
        والواجهة (`utils/shellManifest.ts`) هي من تسقطها إلى `dashboard`."""
        firm = shell_manifest("accounting_firm")
        book = shell_manifest("client_book")
        self.assertIn("office-desk", [v for g in firm["groups"] for v in g["views"]])
        self.assertEqual(set(firm["unbuilt_views"]), UNBUILT_VIEWS)
        self.assertEqual(set(book["unbuilt_views"]), UNBUILT_VIEWS)

    def test_document_coding_is_no_longer_unbuilt(self):
        """issue #85 بنى الشاشة (`DocumentCodingPage.tsx`) — لم تعد تسقط إلى
        `dashboard` رغم بقائها مذكورة في مجموعة «الإدخال» لدفتر العميل."""
        book = shell_manifest("client_book")
        self.assertIn("document-coding", [v for g in book["groups"] for v in g["views"]])
        self.assertNotIn("document-coding", UNBUILT_VIEWS)

    def test_manifest_does_not_mutate_shared_state_across_calls(self):
        """`shell_manifest` يعيد نسخةً عميقة — تعديل صفوف مجموعةٍ في ناتج نداءٍ
        لا يُصيب نداءً تالياً (لا مرجعاً مشتركاً إلى `SHELL_MANIFESTS`)."""
        first = shell_manifest("accounting_firm")
        first["groups"][0]["views"].append("corrupted-view")
        second = shell_manifest("accounting_firm")
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

    def test_accounting_firm_company_sees_its_manifest(self):
        user = User.objects.create_user(username="shell-firm-owner", password="x")
        tenant = create_company("مكتب محاسبة للبيان", user, template="accounting_firm")
        res = self.client.get("/api/permissions/me/", **self._as(user, tenant))
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIsNotNone(body["shell"])
        self.assertEqual(body["shell"]["start_view"], "dashboard")
        self.assertEqual(body["shell"]["first_action"]["view"], "sales-invoices")

    def test_client_book_company_sees_its_manifest(self):
        user = User.objects.create_user(username="shell-book-owner", password="x")
        tenant = create_company("دفتر عميل للبيان", user, template="client_book")
        res = self.client.get("/api/permissions/me/", **self._as(user, tenant))
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIsNotNone(body["shell"])
        self.assertEqual(body["shell"]["first_action"]["view"], "document-coding")
