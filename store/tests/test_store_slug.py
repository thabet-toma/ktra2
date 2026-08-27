"""كتابة معرّف المتجر — النقطة التي تفتح متجراً وتقفله.

المعرّف نفسه هو مفتاح التفعيل، فهذه النقطة هي حرفياً «افتح متجري / أقفله».
لذلك تُحرَس بصلاحية مدير، ويُحرَس شكلُها بقاعدة واحدة لا نسختين.
"""
from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

from tenants.models import RolePermission, Tenant, UserCompanyMembership
from tenants.services import create_company


class StoreSlugEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="slug-manager", password="x")
        cls.tenant = create_company("شركة المعرّف", cls.manager)
        cls.staff = User.objects.create_user(username="slug-staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role="staff")
        cls.outsider = User.objects.create_user(username="slug-outsider", password="x")

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _post(self, user, value):
        return self._client(user).post(
            f"/api/tenants/companies/{self.tenant.pk}/set-store-slug/",
            {"store_slug": value}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

    def _slug(self):
        return Tenant.objects.get(pk=self.tenant.pk).store_slug

    # ── الحارس ───────────────────────────────────────────────────────────
    def test_manager_can_open_the_store(self):
        res = self._post(self.manager, "my-shop")
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(self._slug(), "my-shop")

    def test_a_plain_member_is_refused(self):
        self.assertEqual(self._post(self.staff, "staff-shop").status_code, 403)
        self.assertIsNone(self._slug())

    def test_the_guard_is_store_manage_not_the_general_company_settings(self):
        """ST-3: فتح المتجر قرارٌ تجاري مستقل عن إعدادات الشركة.

        مَن يُمنح «إعدادات الشركة العامة» يضبط العنوان والشعار — ولا يفتح بذلك
        متجراً عاماً يعرض أسعار الشركة للملأ. المفتاحان منفصلان عمداً، وهذا
        الاختبار هو ما يمنع الرجوع الصامت إلى المفتاح القديم.
        """
        RolePermission.objects.create(
            tenant=self.tenant, role="staff",
            permission_key="admin.settings.manage", allowed=True)
        self.assertEqual(self._post(self.staff, "settings-shop").status_code, 403)
        self.assertIsNone(self._slug())

    def test_a_member_granted_store_manage_can_open_the_store(self):
        """المفتاح مُدرَج في كتالوج `core/access.py` فعلاً — لا مجرّد نصّ.

        تجاوزات الشركة تتجاهل أي مفتاح خارج الكتالوج (`core/access.py`
        (`_apply`))، فمنحٌ يفتح النقطة يثبت أن المفتاح صار جزءاً من النظام
        ويظهر في شاشة الصلاحيات، لا سلسلة نصّية في سطر حراسة.
        """
        RolePermission.objects.create(
            tenant=self.tenant, role="staff",
            permission_key="store.manage", allowed=True)
        res = self._post(self.staff, "granted-shop")
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(self._slug(), "granted-shop")

    def test_a_non_member_is_refused_with_or_without_the_tenant_header(self):
        """الغريب يُردّ قبل أن يصل الـaction — بحارس المنصة لا بحارسنا.

        `core/tenant_utils.py` يرفض عضويةً غير قائمة ويسجّل تنبيهاً أمنياً،
        سواء أُرسلت ترويسة `X-Tenant-Id` أم تُركت للحلّ التلقائي. النقطة هنا
        ليست الرمز بل أن **لا مسار** يوصل غير العضو إلى كتابة المعرّف.
        """
        self.assertEqual(self._post(self.outsider, "x-shop").status_code, 403)
        bare = self._client(self.outsider).post(
            f"/api/tenants/companies/{self.tenant.pk}/set-store-slug/",
            {"store_slug": "x-shop"}, format="json")
        self.assertEqual(bare.status_code, 403)
        self.assertIsNone(self._slug())

    def test_anonymous_is_rejected(self):
        res = APIClient().post(
            f"/api/tenants/companies/{self.tenant.pk}/set-store-slug/",
            {"store_slug": "anon-shop"}, format="json")
        self.assertIn(res.status_code, (401, 403))
        self.assertIsNone(self._slug())

    # ── التحقّق ──────────────────────────────────────────────────────────
    def test_bad_shapes_are_refused(self):
        # حالة الأحرف ليست هنا عمداً — تُصحَّح لا تُرفض (الاختبار أدناه).
        for value in ("ab", "with space", "under_score", "شركة", "a" * 41, "-"):
            with self.subTest(value=value):
                self.assertEqual(self._post(self.manager, value).status_code, 400)
                self.assertIsNone(self._slug())

    def test_reserved_words_are_refused(self):
        for value in ("api", "admin", "store", "app", "login"):
            with self.subTest(value=value):
                self.assertEqual(self._post(self.manager, value).status_code, 400)

    def test_a_slug_taken_by_another_company_is_refused(self):
        Tenant.objects.create(
            CompanyName="السابقة", SubscriptionPlan="Basic", Status="Active",
            store_slug="taken-one")
        res = self._post(self.manager, "taken-one")
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIsNone(self._slug())

    def test_resaving_the_same_slug_is_not_a_conflict(self):
        self._post(self.manager, "same-shop")
        self.assertEqual(self._post(self.manager, "same-shop").status_code, 200)

    def test_uppercase_input_is_normalised_not_rejected(self):
        """المدير يكتب المعرّف بيده — تصحيح حالة الأحرف أرفق من رسالة خطأ."""
        self.assertEqual(self._post(self.manager, "  MyShop2  ").status_code, 200)
        self.assertEqual(self._slug(), "myshop2")

    # ── الإقفال ──────────────────────────────────────────────────────────
    def test_an_empty_value_closes_the_store(self):
        self._post(self.manager, "closing-shop")
        res = self._post(self.manager, "")
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertIsNone(self._slug())
        self.assertEqual(
            APIClient().get("/api/store/closing-shop/products/").status_code, 404)

    def test_two_closed_stores_coexist(self):
        """NULL مكرّر تحت قيد unique — الحالة الافتراضية لكل شركات المنصة."""
        Tenant.objects.create(
            CompanyName="مقفلة 1", SubscriptionPlan="Basic", Status="Active")
        Tenant.objects.create(
            CompanyName="مقفلة 2", SubscriptionPlan="Basic", Status="Active")
        self.assertEqual(Tenant.objects.filter(store_slug__isnull=True).count(), 3)

    # ── الرحلة كاملةً كما تمشيها شاشة «متجري» ────────────────────────────
    def test_the_whole_journey_open_then_publish_then_it_is_public(self):
        """ST-3: نفس السيناريو اليدوي، مثبَّتاً — فلا تنكسر السلسلة بصمت.

        الشاشة لا تملك نقطة نشر خاصة بها: تفتح المتجر بـ`set-store-slug`،
        ثم تنشر المنتج بـPATCH على `ProductViewSet` القائم. الحلقة الثالثة —
        أن يظهر عند الزائر — هي التي لا يثبتها أيّ اختبار في الطرفين وحده.
        """
        from inventory.models import Product

        product = Product.objects.create(
            tenant=self.tenant, sku="J-1", name_ar="منتج الرحلة",
            sale_price="25.00", is_for_sale_online=False)

        self.assertEqual(self._post(self.manager, "journey-shop").status_code, 200)

        # النشر — نفس النداء الذي ترسله الشاشة، بلا سيريالايزر ثانٍ.
        patch = self._client(self.manager).patch(
            f"/api/inventory/products/{product.pk}/",
            {"is_for_sale_online": True, "online_price": "19.90"}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(patch.status_code, 200, patch.content[:300])

        # وفلتر الشاشة يراه في تبويب «المعروضة».
        listed = self._client(self.manager).get(
            "/api/inventory/products/?is_for_sale_online=true",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        ).json()
        self.assertEqual([row["id"] for row in listed], [product.pk])

        # والزائر — بلا أي توكن — يراه بسعر المتجر.
        public = APIClient().get("/api/store/journey-shop/products/")
        self.assertEqual(public.status_code, 200, public.content[:300])
        results = public.json()["results"]
        self.assertEqual([row["id"] for row in results], [product.pk])
        self.assertEqual(results[0]["price"], "19.90")

    # ── الباب الخلفي ─────────────────────────────────────────────────────
    def test_a_plain_patch_on_the_company_cannot_write_the_slug(self):
        """`store_slug` للقراءة فقط في السيريالايزر — وإلا تجاوز PATCH التحقّق."""
        res = self._client(self.manager).patch(
            f"/api/tenants/companies/{self.tenant.pk}/",
            {"store_slug": "api"}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertIsNone(self._slug())
