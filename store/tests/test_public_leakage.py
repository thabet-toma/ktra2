"""ST-1 — معيار النجاح **السالب** للمتجر العام: إثبات غياب التسريب.

هذا الاختبار هو البوابة الوحيدة التي تُجيز نقطةً بلا مصادقة فوق ERP إنتاجي.
وهو سالبٌ عمداً: لقطة شاشة تُثبت أن شيئاً **يظهر**، ولا تُثبت أبداً أن شيئاً
آخر **لا يظهر** — وما نحرسه هنا هو الثاني.

طبقتان، كلٌّ تُمسِك ما تفوّته الأخرى:

1. **عزل الشركة** — نتائج `/store/alpha/` لا تحمل منتج شركة أخرى ولا منتجاً
   غير منشور، لا في القائمة ولا بالوصول المباشر بالمعرّف.
2. **إحكام الحمولة بمساواة مجموعة المفاتيح** — `assertEqual(set(keys), WHITELIST)`
   لا `assertNotIn('avg_cost', keys)`. الفرق جوهري: الغياب الفردي يحرس ما
   خطر ببالنا يوم كتابته، ومساواة المجموعة تُفشِل **كل** حقل يُضاف مستقبلاً
   إلى المنتج أو إلى السيريالايزر بلا قرار واعٍ — بالبناء لا بالتعداد.

THA-166 م٢: المصدر صار `store.StoreProduct` — الكتالوجُ المستقلّ الذي **لا
يحمل أصلاً** أعمدة رصيدٍ أو تكلفة (`quantity_on_hand`/`avg_cost`)، فمسحُ
القيم التكراريّ الذي كان يحرس تسرّبهما (رصيدٌ وتكلفةٌ مزروعان في `Product`
سابقاً) صار يحرس فراغاً — لا حقل يمكن أن يتسرّب لأنه غير موجود بنيوياً على
النموذج من الأصل. حُذف ذلك الاختبار
(`test_no_stock_or_cost_value_appears_anywhere_in_the_payload`) لهذا السبب
بالذات؛ الضمانةُ المكافئة الآن بنيوية ومُثبَتةٌ في `store/tests/test_store_api.py`
(`test_raw_stock_and_cost_never_reach_python`) بفحص حقول النموذج نفسه لا بمسح القيم.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from store.models import StoreBrand, StoreProduct
from tenants.models import Tenant, TenantSettings

#: العقد العام للمنتج — كل مفتاح هنا قرارٌ واعٍ بنشره للعالم.
#: THA-166 م٢: الأصلُ أحد عشر حقلاً بقيت كما هي + ستّةٌ إضافيةٌ محضة
#: (`slug` · `original_price` · `discount_percent` · `categories` ·
#: `stock_state` · `brand_id`) — توسيعُها هنا هو لحظةُ القرار الواعي بنشر
#: كلّ مفتاحٍ جديد للعالم.
PUBLIC_WHITELIST = {
    "id", "name_ar", "name_en", "brand", "category_name", "uom_name",
    "price", "availability", "description", "images", "cover_overlay",
    "slug", "original_price", "discount_percent", "categories",
    "stock_state", "brand_id",
}

#: الحالات النصية للتوفّر — حالة لا رقم. `limited` سقطت (THA-166 م٢): كانت
#: تُحسَب من رصيدٍ مخزنيّ، والرصيدُ مقطوعٌ عن كتالوج المتجر المستقلّ بقرار مالك.
AVAILABILITY_STATES = {"available", "out", "preorder"}

#: العقد العام لبطاقة الشركة وإعدادات المظهر والهوية العامة.
PROFILE_WHITELIST = {
    "slug", "name", "logo_url", "phone", "address", "currency",
    "hero_title", "hero_subtitle", "announcement_bar", "show_announcement",
    "theme_preset", "primary_color", "accent_color", "background_color",
    "background_image_url", "background_style", "banner_image_url",
    "instagram_url", "tiktok_url", "facebook_url", "snapchat_url",
    "whatsapp_number", "catalog_mode_default", "allow_cart", "show_prices",
}

def _walk(node, path="$"):
    """يولّد (المسار، القيمة) لكل ورقة في شجرة JSON."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, node


class StorePublicLeakageTest(TestCase):
    """زائر مجهول تماماً — `APIClient` بلا أي ترويسة توكن ولا جلسة."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            CompanyName="شركة ألفا", SubscriptionPlan="Pro", Status="Active",
            store_slug="alpha")
        TenantSettings.objects.create(
            tenant=cls.tenant_a, company_name_primary="شركة ألفا للتجارة",
            phone="0790000000", address="عمّان — شارع المدينة",
            logo_url="https://res.cloudinary.com/demo/logo-alpha.png")
        cls.brand_a = StoreBrand.objects.create(tenant=cls.tenant_a, name="ميشلان")

        cls.tenant_b = Tenant.objects.create(
            CompanyName="شركة بيتا", SubscriptionPlan="Pro", Status="Active",
            store_slug="beta")

        # الشركة الثالثة: متجرها مقفل (store_slug = NULL) — الحالة الافتراضية
        # لكل شركات المنصة القائمة، ولا backfill يغيّرها.
        cls.tenant_closed = Tenant.objects.create(
            CompanyName="شركة بلا متجر", SubscriptionPlan="Basic", Status="Active")

        # PA — المنتج المنشور الوحيد لألفا.
        cls.pa = StoreProduct.objects.create(
            tenant=cls.tenant_a, name_ar="إطار 185/65", name_en="Tyre 185/65",
            brand=cls.brand_a, price=Decimal("19.99"),
            description="إطار صيفي بأداء ممتاز", is_active=True,
        )

        # PA2 — منتج ألفا **غير منشور**: النشر اختيار صريح لا افتراض.
        cls.pa2 = StoreProduct.objects.create(
            tenant=cls.tenant_a, name_ar="إطار سرّي", name_en="Secret Tyre",
            brand=cls.brand_a, price=Decimal("31.00"), is_active=False,
        )

        # PB — منتج شركة أخرى، منشور في متجرها هي.
        cls.pb = StoreProduct.objects.create(
            tenant=cls.tenant_b, name_ar="بطارية 70", name_en="Battery 70",
            price=Decimal("45.50"), is_active=True,
        )

    def setUp(self):
        # بلا `credentials()` — ولا ترويسة X-Tenant-Id: الشركة تأتي من الـslug
        # في المسار وحده، فلا ترويسةَ يتلاعب بها الزائر.
        self.client = APIClient()

    # ── أدوات ────────────────────────────────────────────────────────────
    def _list(self, slug="alpha", **params):
        return self.client.get(f"/api/store/{slug}/products/", params)

    def _detail(self, product_id, slug="alpha"):
        return self.client.get(f"/api/store/{slug}/products/{product_id}/")

    @staticmethod
    def _items(payload):
        """يقبل المصفوفة الخام والغلاف المرقَّم معاً."""
        return payload["results"] if isinstance(payload, dict) else payload

    # ── 1. عزل الشركة ────────────────────────────────────────────────────
    def test_list_shows_only_this_tenants_published_products(self):
        res = self._list()
        self.assertEqual(res.status_code, 200, res.content[:400])
        ids = {item["id"] for item in self._items(res.json())}
        self.assertEqual(
            ids, {self.pa.id},
            f"القائمة يجب أن تحمل PA وحده — لا PB ({self.pb.id}) ولا PA2 ({self.pa2.id})",
        )

    def test_each_store_sees_its_own_products_only(self):
        ids = {item["id"] for item in self._items(self._list(slug="beta").json())}
        self.assertEqual(ids, {self.pb.id})

    # ── 2. إحكام الحمولة — مساواة مجموعة المفاتيح ────────────────────────
    def test_list_item_keys_are_exactly_the_public_whitelist(self):
        for item in self._items(self._list().json()):
            self.assertEqual(set(item.keys()), PUBLIC_WHITELIST)

    def test_detail_keys_are_exactly_the_public_whitelist(self):
        res = self._detail(self.pa.id)
        self.assertEqual(res.status_code, 200, res.content[:400])
        self.assertEqual(set(res.json().keys()), PUBLIC_WHITELIST)

    def test_availability_is_one_of_the_three_text_states(self):
        values = [item["availability"] for item in self._items(self._list().json())]
        values.append(self._detail(self.pa.id).json()["availability"])
        self.assertTrue(values)
        for value in values:
            self.assertIn(value, AVAILABILITY_STATES)

    def test_availability_is_derived_from_stock_state_not_its_raw_name(self):
        """THA-166 م٢: `stock_state='in_stock'` (افتراضيّ `pa`) ⇒ «available» —
        اسمٌ عامٌّ مختلفٌ عن اسم الحالة الداخلية، لا رقمٌ مخزنيّ كما كان سابقاً."""
        self.assertEqual(self.pa.stock_state, StoreProduct.STOCK_IN_STOCK)
        self.assertEqual(self._detail(self.pa.id).json()["availability"], "available")

    # ── 4. التقاطع بالمعرّف ──────────────────────────────────────────────
    def test_other_tenants_product_id_under_this_slug_is_404(self):
        self.assertEqual(self._detail(self.pb.id).status_code, 404)

    def test_unpublished_product_id_is_404(self):
        self.assertEqual(self._detail(self.pa2.id).status_code, 404)

    def test_unknown_slug_is_404(self):
        self.assertEqual(self._list(slug="nope").status_code, 404)
        self.assertEqual(self._detail(self.pa.id, slug="nope").status_code, 404)

    def test_tenant_with_closed_store_is_404(self):
        """`store_slug = NULL` = المتجر مقفل — لا مسار يصل إليه إطلاقاً."""
        self.assertEqual(self.tenant_closed.store_slug, None)
        self.assertEqual(self._list(slug="").status_code, 404)
        self.assertEqual(self.client.get("/api/store/").status_code, 404)

    # ── 5. بطاقة الشركة ──────────────────────────────────────────────────
    def test_store_profile_carries_the_contact_card_only(self):
        res = self.client.get("/api/store/alpha/")
        self.assertEqual(res.status_code, 200, res.content[:400])
        self.assertEqual(set(res.json().keys()), PROFILE_WHITELIST)
        self.assertEqual(res.json()["name"], "شركة ألفا للتجارة")

    def test_store_profile_of_a_closed_store_is_404(self):
        self.assertEqual(self.client.get("/api/store/gamma/").status_code, 404)
