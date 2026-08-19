"""ST-1 — معيار النجاح **السالب** للمتجر العام: إثبات غياب التسريب.

هذا الاختبار هو البوابة الوحيدة التي تُجيز نقطةً بلا مصادقة فوق ERP إنتاجي.
وهو سالبٌ عمداً: لقطة شاشة تُثبت أن شيئاً **يظهر**، ولا تُثبت أبداً أن شيئاً
آخر **لا يظهر** — وما نحرسه هنا هو الثاني.

ثلاث طبقات، كلٌّ تُمسِك ما تفوّته الأخرى:

1. **عزل الشركة** — نتائج `/store/alpha/` لا تحمل صنف شركة أخرى ولا صنفاً
   غير منشور، لا في القائمة ولا بالوصول المباشر بالمعرّف.
2. **إحكام الحمولة بمساواة مجموعة المفاتيح** — `assertEqual(set(keys), WHITELIST)`
   لا `assertNotIn('avg_cost', keys)`. الفرق جوهري: الغياب الفردي يحرس ما
   خطر ببالنا يوم كتابته، ومساواة المجموعة تُفشِل **كل** حقل يُضاف مستقبلاً
   إلى المنتج أو إلى السيريالايزر بلا قرار واعٍ — بالبناء لا بالتعداد.
3. **مسح تكراري للقيم** — الطبقة الثانية تحرس أسماء المفاتيح؛ هذه تحرس القيم
   نفسها، فلو تسلّل الرصيد داخل نصٍّ أو عنصرٍ متداخل لأمسكته.

القيم المزروعة: `quantity_on_hand = 7` و`avg_cost = 5` — رقمان كلاهما سرّ
تجاري: الأول يكشف حجم المخزون للمنافس، والثاني يكشف هامش الربح.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from core.models import SystemAttachment
from inventory.models import Product, ProductCategory, UnitOfMeasure
from tenants.models import Tenant, TenantSettings

#: العقد العام للمنتج — كل مفتاح هنا قرارٌ واعٍ بنشره للعالم.
PUBLIC_WHITELIST = {
    "id", "name_ar", "name_en", "brand", "category_name", "uom_name",
    "price", "availability", "description", "images", "cover_overlay",
}

#: الحالات النصية للتوفّر — حالة لا رقم.
AVAILABILITY_STATES = {"available", "limited", "out", "preorder"}

#: العقد العام لبطاقة الشركة وإعدادات المظهر والهوية العامة.
PROFILE_WHITELIST = {
    "slug", "name", "logo_url", "phone", "address", "currency",
    "hero_title", "hero_subtitle", "announcement_bar", "show_announcement",
    "theme_preset", "primary_color", "accent_color", "background_color",
    "background_image_url", "background_style", "banner_image_url",
    "instagram_url", "tiktok_url", "facebook_url", "snapchat_url",
    "whatsapp_number", "catalog_mode_default", "allow_cart", "show_prices",
}

#: تمثيلات الرصيد (7) والتكلفة (5) التي قد تخرج بها من ORM/DRF.
FORBIDDEN_VALUES = {
    7, 5, 7.0, 5.0, Decimal("7"), Decimal("5"),
    "7", "5", "7.0", "5.0", "7.00", "5.00", "7.0000", "5.0000",
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
        cls.uom = UnitOfMeasure.objects.create(
            code="PCS", name_ar="قطعة", name_en="Piece")

        cls.tenant_a = Tenant.objects.create(
            CompanyName="شركة ألفا", SubscriptionPlan="Pro", Status="Active",
            store_slug="alpha")
        TenantSettings.objects.create(
            tenant=cls.tenant_a, company_name_primary="شركة ألفا للتجارة",
            phone="0790000000", address="عمّان — شارع المدينة",
            logo_url="https://res.cloudinary.com/demo/logo-alpha.png")
        cls.category_a = ProductCategory.objects.create(
            tenant=cls.tenant_a, name="إطارات")

        cls.tenant_b = Tenant.objects.create(
            CompanyName="شركة بيتا", SubscriptionPlan="Pro", Status="Active",
            store_slug="beta")
        cls.category_b = ProductCategory.objects.create(
            tenant=cls.tenant_b, name="بطاريات")

        # الشركة الثالثة: متجرها مقفل (store_slug = NULL) — الحالة الافتراضية
        # لكل شركات المنصة القائمة، ولا backfill يغيّرها.
        cls.tenant_closed = Tenant.objects.create(
            CompanyName="شركة بلا متجر", SubscriptionPlan="Basic", Status="Active")

        # PA — المنتج المنشور الوحيد لألفا. الرصيد والتكلفة يُكتبان مباشرةً هنا
        # لأنه تجهيز اختبار لا مسار مخزون: `record_stock_movement` يبقى الكاتب
        # الوحيد في كود الإنتاج، وهذا الاختبار لا يلمس أي مسار كتابة أصلاً.
        cls.pa = Product.objects.create(
            tenant=cls.tenant_a, sku="PA-1", name_ar="إطار 185/65", name_en="Tyre 185/65",
            brand="ميشلان", category=cls.category_a, uom=cls.uom,
            min_stock_level=2, is_for_sale_online=True,
            online_price=Decimal("19.99"), online_description="إطار صيفي بأداء ممتاز",
            quantity_on_hand=Decimal("7"), avg_cost=Decimal("5"),
        )
        SystemAttachment.objects.create(
            tenant=cls.tenant_a, related_table="products", related_id=cls.pa.id,
            file_type="Product Image",
            file_path="https://res.cloudinary.com/demo/image/upload/pa.jpg")

        # PA2 — صنف ألفا **غير منشور**: النشر اختيار صريح لا افتراض.
        cls.pa2 = Product.objects.create(
            tenant=cls.tenant_a, sku="PA-2", name_ar="إطار سرّي", name_en="Secret Tyre",
            brand="ميشلان", category=cls.category_a, uom=cls.uom,
            is_for_sale_online=False, online_price=Decimal("31.00"),
            quantity_on_hand=Decimal("40"), avg_cost=Decimal("22"),
        )

        # PB — صنف شركة أخرى، منشور في متجرها هي.
        cls.pb = Product.objects.create(
            tenant=cls.tenant_b, sku="PB-1", name_ar="بطارية 70", name_en="Battery 70",
            brand="فارتا", category=cls.category_b, uom=cls.uom,
            is_for_sale_online=True, online_price=Decimal("45.50"),
            quantity_on_hand=Decimal("12"), avg_cost=Decimal("30"),
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

    # ── 3. مسح تكراري للقيم ──────────────────────────────────────────────
    def test_no_stock_or_cost_value_appears_anywhere_in_the_payload(self):
        """الرصيد 7 والتكلفة 5 لا يظهران في أي ورقة من شجرة الرد.

        مفتاح `id` مستثنى وحده: مفتاح مرتّب تلقائياً لا علاقة له بالمخزون،
        وقد يصادف الرقم 5 أو 7 فيُحمِّر الاختبار كذباً. عزل المعرّفات نفسه
        محروسٌ في `test_list_shows_only_this_tenants_published_products`.
        """
        payloads = {
            "list": self._list().json(),
            "detail": self._detail(self.pa.id).json(),
        }
        for name, payload in payloads.items():
            for path, value in _walk(payload):
                if path.endswith(".id"):
                    continue
                self.assertNotIn(
                    value, FORBIDDEN_VALUES,
                    f"تسريب في حمولة {name} عند {path}: {value!r} — "
                    "الرصيد الخام أو التكلفة وصلا الزائر",
                )

    def test_availability_is_one_of_the_three_text_states(self):
        values = [item["availability"] for item in self._items(self._list().json())]
        values.append(self._detail(self.pa.id).json()["availability"])
        self.assertTrue(values)
        for value in values:
            self.assertIn(value, AVAILABILITY_STATES)

    def test_limited_state_is_derived_not_the_number(self):
        """رصيد 7 وحدّ أدنى 2 ⇒ «متوفر»؛ والقيمة نصّ لا رقم."""
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
