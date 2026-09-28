"""#230 — جهات كفالة المصنع وإعدادات الوحدة.

يثبت:
  1. CRUD كامل على `ManufacturerWarrantor`، وأرشفةٌ عبر `is_active=False` لا حذف.
  2. الاسم فريد للشركة — تكراره يُرفض بـ400.
  3. حذف جهة **مرتبطة** يُرفض بـ400 مقروءاً لا 500 (`ProtectedError` عامٌّ —
     لا شيء يشير إليها بعد في هذا المعلم، فالسيناريو يُحاكى بتعطيل `delete()`).
  4. `lookup/` يقرأها من يملك `purchase.invoice.edit` أو `aftersales.warranty.view`
     (لا CRUD الكامل)، وتستثني المؤرشفة.
  5. إدارة الجهات والإعدادات خلف `aftersales.settings.manage` وحدها.
  6. إعدادات شركة جديدة: التمديد بأيام الصيانة مفعَّل، وكفالة الإصلاح 90 يوماً.
  7. شروط فوق 2000 حرف وكفالة إصلاح خارج المدى تُرفض بـ400.
  8. البوابة (`require_module` قبل `require_perm`) والعزل بين الشركات.
"""
from unittest import mock

from django.contrib.auth.models import User
from django.db.models import ProtectedError

from after_sales.models import AfterSalesSettings, ManufacturerWarrantor
from core.models import TenantModule
from tenants.models import UserCompanyMembership
from tenants.services import create_company

from .test_warranty import WarrantyTestBase

WARRANTORS = "/api/after-sales/manufacturer-warrantors/"
LOOKUP = f"{WARRANTORS}lookup/"
SETTINGS = "/api/after-sales/settings/"


class WarrantorAndSettingsBase(WarrantyTestBase):
    """يضيف مستخدمَي مشتريات ومبيعات بلا `aftersales.settings.manage` فوق المدير."""

    def setUp(self):
        super().setUp()
        self.procurement_user = User.objects.create_user(username="procurement-230", password="x")
        UserCompanyMembership.objects.create(
            user=self.procurement_user, tenant=self.tenant, role="procurement",
        )
        self.sales_user = User.objects.create_user(username="sales-230", password="x")
        UserCompanyMembership.objects.create(
            user=self.sales_user, tenant=self.tenant, role="sales",
        )
        self.ess_user = User.objects.create_user(username="ess-230", password="x")
        UserCompanyMembership.objects.create(
            user=self.ess_user, tenant=self.tenant, role="ess",
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self


# ══════════════════════════════════════════════════════════════════════════
# جهات كفالة المصنع — CRUD وأرشفة
# ══════════════════════════════════════════════════════════════════════════

class ManufacturerWarrantorCrudTest(WarrantorAndSettingsBase):
    def test_manager_creates_and_lists_a_warrantor(self):
        response = self.client.post(
            WARRANTORS,
            {"name": "الوكيل الرسمي", "service_center_address": "رام الله", "phone": "022345678"},
            format="json", **self.headers(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["name"], "الوكيل الرسمي")
        self.assertTrue(response.data["is_active"])

        listed = self.client.get(WARRANTORS, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        names = [row["name"] for row in listed.data["results"]] if "results" in listed.data else [
            row["name"] for row in listed.data
        ]
        self.assertIn("الوكيل الرسمي", names)

    def test_manager_edits_a_warrantor(self):
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة أولى")

        response = self.client.patch(
            f"{WARRANTORS}{warrantor.pk}/", {"phone": "059000111"}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        warrantor.refresh_from_db()
        self.assertEqual(warrantor.phone, "059000111")

    def test_archiving_sets_is_active_false_instead_of_deleting(self):
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة للأرشفة")

        response = self.client.patch(
            f"{WARRANTORS}{warrantor.pk}/", {"is_active": False}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        warrantor.refresh_from_db()
        self.assertFalse(warrantor.is_active)
        self.assertTrue(ManufacturerWarrantor.objects.filter(pk=warrantor.pk).exists())

    def test_duplicate_name_within_tenant_is_rejected_with_400(self):
        ManufacturerWarrantor.objects.create(tenant=self.tenant, name="سامسونج فلسطين")

        response = self.client.post(
            WARRANTORS, {"name": "سامسونج فلسطين"}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("name", response.data)

    def test_same_name_is_allowed_across_two_tenants(self):
        ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة مشتركة الاسم")
        other = create_company("شركة كفالة أخرى ٢٣٠", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)

        response = self.client.post(
            WARRANTORS, {"name": "جهة مشتركة الاسم"}, format="json", **self.headers(other),
        )

        self.assertEqual(response.status_code, 201, response.content)

    def test_deleting_an_unreferenced_warrantor_succeeds(self):
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة تُحذف")

        response = self.client.delete(f"{WARRANTORS}{warrantor.pk}/", **self.headers())

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(ManufacturerWarrantor.objects.filter(pk=warrantor.pk).exists())

    def test_deleting_a_referenced_warrantor_returns_400_not_500(self):
        """لا موديل يشير إلى `ManufacturerWarrantor` بـPROTECT بعد في هذا المعلم
        (السياسة/بند الشراء/البطاقة تذاكر لاحقة) — الفحص العام يُثبَت بمحاكاة
        `ProtectedError` نفسها التي سترفعها قاعدة البيانات حين يوجد مرجعٌ فعلي."""
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة مرتبطة مستقبلاً")

        with mock.patch(
            "after_sales.models.ManufacturerWarrantor.delete",
            side_effect=ProtectedError("محمية", []),
        ):
            response = self.client.delete(f"{WARRANTORS}{warrantor.pk}/", **self.headers())

        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(ManufacturerWarrantor.objects.filter(pk=warrantor.pk).exists())


class ManufacturerWarrantorPermissionTest(WarrantorAndSettingsBase):
    def test_a_user_without_settings_manage_cannot_create(self):
        self.as_user(self.sales_user)

        response = self.client.post(WARRANTORS, {"name": "محاولة موظف مبيعات"}, format="json", **self.headers())

        self.assertEqual(response.status_code, 403, response.content)

    def test_a_user_without_settings_manage_cannot_list_the_full_crud(self):
        self.as_user(self.procurement_user)

        response = self.client.get(WARRANTORS, **self.headers())

        self.assertEqual(response.status_code, 403, response.content)

    def test_404_without_a_module_license(self):
        self.license.delete()

        response = self.client.post(WARRANTORS, {"name": "بلا ترخيص"}, format="json", **self.headers())

        self.assertEqual(response.status_code, 404, response.content)

    def test_a_warrantor_from_another_tenant_is_not_reachable(self):
        other = create_company("شركة كفالة أخرى ٢٣٠-ب", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign = ManufacturerWarrantor.objects.create(tenant=other, name="جهة شركة أخرى")

        response = self.client.get(f"{WARRANTORS}{foreign.pk}/", **self.headers())

        self.assertEqual(response.status_code, 404, response.content)


# ══════════════════════════════════════════════════════════════════════════
# lookup/ — أوسع من إدارة الجهات
# ══════════════════════════════════════════════════════════════════════════

class ManufacturerWarrantorLookupTest(WarrantorAndSettingsBase):
    def setUp(self):
        super().setUp()
        self.active = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة مفعَّلة")
        self.archived = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="جهة مؤرشفة", is_active=False,
        )

    def test_lookup_excludes_archived_warrantors(self):
        response = self.client.get(LOOKUP, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        names = {row["name"] for row in response.data}
        self.assertEqual(names, {"جهة مفعَّلة"})

    def test_lookup_is_readable_by_a_purchase_invoice_editor_without_settings_manage(self):
        self.as_user(self.procurement_user)

        response = self.client.get(LOOKUP, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)

    def test_lookup_is_readable_by_the_aftersales_view_permission(self):
        # موظف المبيعات يملك `aftersales.warranty.view` لا `purchase.invoice.edit`.
        self.as_user(self.sales_user)

        response = self.client.get(LOOKUP, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)

    def test_lookup_is_403_for_a_user_with_neither_permission(self):
        self.as_user(self.ess_user)

        response = self.client.get(LOOKUP, **self.headers())

        self.assertEqual(response.status_code, 403, response.content)

    def test_lookup_is_404_without_a_module_license(self):
        self.license.delete()

        response = self.client.get(LOOKUP, **self.headers())

        self.assertEqual(response.status_code, 404, response.content)


# ══════════════════════════════════════════════════════════════════════════
# settings/ — GET/PATCH
# ══════════════════════════════════════════════════════════════════════════

class AfterSalesSettingsEndpointTest(WarrantorAndSettingsBase):
    def test_new_tenant_defaults_are_shop_days_on_and_repair_ninety_days(self):
        response = self.client.get(SETTINGS, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["extend_for_shop_days"])
        self.assertEqual(response.data["repair_warranty_days"], 90)
        self.assertEqual(response.data["default_terms"], "")
        self.assertEqual(response.data["repair_terms"], "")

    def test_manager_patches_the_settings(self):
        response = self.client.patch(
            SETTINGS,
            {
                "default_terms": "الكفالة لا تشمل سوء الاستخدام.",
                "extend_for_shop_days": False,
                "repair_warranty_days": 30,
                "repair_terms": "كفالة الإصلاح تغطي القطعة المستبدلة فقط.",
            },
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        settings_row = AfterSalesSettings.objects.get(tenant=self.tenant)
        self.assertEqual(settings_row.default_terms, "الكفالة لا تشمل سوء الاستخدام.")
        self.assertFalse(settings_row.extend_for_shop_days)
        self.assertEqual(settings_row.repair_warranty_days, 30)
        self.assertEqual(settings_row.repair_terms, "كفالة الإصلاح تغطي القطعة المستبدلة فقط.")

    def test_repair_warranty_days_zero_turns_it_off(self):
        response = self.client.patch(
            SETTINGS, {"repair_warranty_days": 0}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["repair_warranty_days"], 0)

    def test_repair_warranty_days_above_730_is_rejected(self):
        response = self.client.patch(
            SETTINGS, {"repair_warranty_days": 731}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("repair_warranty_days", response.data)

    def test_default_terms_over_2000_chars_is_rejected(self):
        response = self.client.patch(
            SETTINGS, {"default_terms": "أ" * 2001}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("default_terms", response.data)

    def test_repair_terms_over_2000_chars_is_rejected(self):
        response = self.client.patch(
            SETTINGS, {"repair_terms": "ب" * 2001}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("repair_terms", response.data)

    def test_a_user_without_settings_manage_cannot_patch(self):
        self.as_user(self.sales_user)

        response = self.client.patch(
            SETTINGS, {"repair_warranty_days": 10}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 403, response.content)
        # الرفض قبل أي كتابة: لا صفّ إعداداتٍ يُنشأ أصلاً برفض الصلاحية.
        self.assertFalse(AfterSalesSettings.objects.filter(tenant=self.tenant).exists())

    def test_a_user_without_any_aftersales_permission_can_still_read(self):
        # `GET` لا يحتاج صلاحيةً خاصة — القراءة وحدها خلف الترخيص (نمط
        # `SalesSettingsViewSet.current`، لا `require_perm` على GET).
        self.as_user(self.ess_user)

        response = self.client.get(SETTINGS, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)

    def test_404_without_a_module_license(self):
        self.license.delete()

        response = self.client.get(SETTINGS, **self.headers())

        self.assertEqual(response.status_code, 404, response.content)

    def test_tenant_isolation_two_companies_have_independent_settings(self):
        other = create_company("شركة كفالة أخرى ٢٣٠-إعدادات", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)

        self.client.patch(
            SETTINGS, {"repair_warranty_days": 15}, format="json", **self.headers(),
        )
        other_response = self.client.get(SETTINGS, **self.headers(other))

        self.assertEqual(other_response.status_code, 200, other_response.content)
        self.assertEqual(other_response.data["repair_warranty_days"], 90)
