"""مواصفة #166 م٥ — شقّ `store.manage` عن `store.pricing`.

`store.manage` يحكم المحتوى، و`store.pricing` وحده يحكم المال: `price`/
`sale_price` على `StoreProduct`، و`discount_percent`/`starts_at`/`ends_at`
على `StoreCollection`. الحارسُ خادميٌّ على مستوى المُسلسِل — إخفاءُ حقلٍ في
الشاشة ليس صلاحية.
"""
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from store.models import StoreCollection, StoreProduct
from tenants.models import MemberPermission, RolePermission, UserCompanyMembership
from tenants.services import create_company


class _PricingGuardBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="pricing-manager", password="x")
        cls.tenant = create_company("شركة التسعير", cls.manager)
        cls.tenant.store_slug = "pricing-shop"
        cls.tenant.save()

        # كل موظفي هذه الشركة يملكون `store.manage` عبر تجاوز الدور — لا
        # `store.pricing` (تجاوزٌ على مستوى (شركة، دور) لا يُكرَّر لكل عضو).
        RolePermission.objects.create(
            tenant=cls.tenant, role="staff",
            permission_key="store.manage", allowed=True)

        cls.staff = User.objects.create_user(username="pricing-staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role="staff")

        # موظفٌ ثانٍ يملك المفتاحين معاً — `store.pricing` بتجاوزٍ فردي فوق دوره.
        cls.pricer = User.objects.create_user(username="pricing-pricer", password="x")
        pricer_membership = UserCompanyMembership.objects.create(
            user=cls.pricer, tenant=cls.tenant, role="staff")
        MemberPermission.objects.create(
            membership=pricer_membership,
            permission_key="store.pricing", allowed=True)

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.pk)
        return client


class StoreProductPricingGuardTest(_PricingGuardBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.product = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="منتج", price=Decimal("100.00"))

    def test_manage_only_user_cannot_change_price(self):
        res = self._client(self.staff).patch(
            f"/api/store/admin/products/{self.product.id}/",
            {"price": "150.00"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("price", str(res.content, "utf-8"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("100.00"))

    def test_manage_only_user_cannot_change_sale_price(self):
        res = self._client(self.staff).patch(
            f"/api/store/admin/products/{self.product.id}/",
            {"sale_price": "80.00"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("sale_price", str(res.content, "utf-8"))

    def test_manage_only_user_can_edit_non_priced_fields(self):
        res = self._client(self.staff).patch(
            f"/api/store/admin/products/{self.product.id}/",
            {"name_ar": "اسمٌ جديد", "description": "وصفٌ جديد"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.product.refresh_from_db()
        self.assertEqual(self.product.name_ar, "اسمٌ جديد")

    def test_saving_the_same_price_is_not_a_change_and_is_not_rejected(self):
        """الرفضُ على محاولة التغيير لا على وجود المفتاح في الحمولة."""
        res = self._client(self.staff).patch(
            f"/api/store/admin/products/{self.product.id}/",
            {"price": "100.00", "name_ar": "اسمٌ آخر"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])

    def test_pricer_can_change_price(self):
        res = self._client(self.pricer).patch(
            f"/api/store/admin/products/{self.product.id}/",
            {"price": "150.00"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("150.00"))

    def test_manager_can_always_change_price(self):
        """المدير يملك كل شيء بـ`"*"` — بلا أي تجاوزٍ مخزَّن له."""
        res = self._client(self.manager).patch(
            f"/api/store/admin/products/{self.product.id}/",
            {"price": "999.00"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])

    def test_creating_a_product_with_a_price_is_rejected_without_pricing(self):
        res = self._client(self.staff).post(
            "/api/store/admin/products/",
            {"name_ar": "منتجٌ جديد", "price": "50.00"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("price", str(res.content, "utf-8"))

    def test_creating_a_product_without_a_price_is_allowed_without_pricing(self):
        res = self._client(self.staff).post(
            "/api/store/admin/products/",
            {"name_ar": "منتجٌ جديد بلا سعر"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])


class StoreCollectionPricingGuardTest(_PricingGuardBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.collection = StoreCollection.objects.create(
            tenant=cls.tenant, title="حملة", slug="campaign-1")

    def test_manage_only_user_cannot_set_discount_percent(self):
        res = self._client(self.staff).patch(
            f"/api/store/admin/collections/{self.collection.id}/",
            {"discount_percent": "30.00"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("discount_percent", str(res.content, "utf-8"))

    def test_manage_only_user_cannot_set_dates(self):
        res = self._client(self.staff).patch(
            f"/api/store/admin/collections/{self.collection.id}/",
            {"starts_at": "2026-09-08T00:00:00Z"}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("starts_at", str(res.content, "utf-8"))

    def test_manage_only_user_can_build_the_rest_of_the_campaign(self):
        """المسوّق يبني الحملة كاملةً ويتركها بخصمٍ صفريٍّ حتى يعتمدها التسعير."""
        res = self._client(self.staff).patch(
            f"/api/store/admin/collections/{self.collection.id}/",
            {"title": "حملة جديدة", "badge_text": "عرضٌ خاص", "is_active": True},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])

    def test_pricer_can_set_discount_percent(self):
        res = self._client(self.pricer).patch(
            f"/api/store/admin/collections/{self.collection.id}/",
            {"discount_percent": "25.00"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.collection.refresh_from_db()
        self.assertEqual(self.collection.discount_percent, Decimal("25.00"))


class GrantStorePricingMigrationTest(TestCase):
    """هجرة `tenants/0033`: كل من كان يملك `store.manage` عبر تجاوزٍ صريح
    يُمنح `store.pricing` تلقائياً — لا انكفاء عند الترقية."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="grant-manager", password="x")
        cls.tenant = create_company("شركة المنح", cls.manager)
        cls.staff = User.objects.create_user(username="grant-staff", password="x")
        cls.membership = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role="staff")

    def setUp(self):
        self.migration = importlib.import_module(
            "tenants.migrations.0033_grant_store_pricing")

    def test_role_override_of_store_manage_gains_store_pricing(self):
        RolePermission.objects.create(
            tenant=self.tenant, role="staff",
            permission_key="store.manage", allowed=True)

        self.migration.grant_pricing_wherever_manage_was_granted(django_apps, None)

        self.assertTrue(
            RolePermission.objects.filter(
                tenant=self.tenant, role="staff",
                permission_key="store.pricing", allowed=True,
            ).exists()
        )

    def test_member_override_of_store_manage_gains_store_pricing(self):
        MemberPermission.objects.create(
            membership=self.membership, permission_key="store.manage", allowed=True)

        self.migration.grant_pricing_wherever_manage_was_granted(django_apps, None)

        self.assertTrue(
            MemberPermission.objects.filter(
                membership=self.membership,
                permission_key="store.pricing", allowed=True,
            ).exists()
        )

    def test_denying_store_manage_does_not_grant_pricing(self):
        RolePermission.objects.create(
            tenant=self.tenant, role="staff",
            permission_key="store.manage", allowed=False)

        self.migration.grant_pricing_wherever_manage_was_granted(django_apps, None)

        self.assertFalse(
            RolePermission.objects.filter(
                tenant=self.tenant, role="staff", permission_key="store.pricing",
            ).exists()
        )

    def test_manager_needs_no_grant_because_the_wildcard_already_covers_it(self):
        """المدير يملك «*» في `ROLE_DEFAULTS` بلا أي صفٍّ في هذين الجدولين."""
        from core.access import user_has_perm

        self.assertTrue(user_has_perm(self.manager, self.tenant, "store.pricing"))
        self.assertFalse(
            RolePermission.objects.filter(tenant=self.tenant, role="manager").exists()
        )
