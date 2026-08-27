"""إظهار/إخفاء أسعار المتجر — مفتاحٌ واحد على مستوى المتجر.

سبب وجود المفتاح: `sale_price` على كرت المنتج حقلٌ **تشغيلي** تقرؤه الفوترة،
ووجودُه لا يعني إذناً بإعلانه للعموم. متاجر الجملة تعرض الكتالوج بلا أسعار
وتترك السعر لمحادثة — وهذا ما يفعله هذا المفتاح.

الحجب في `published_products` وحدها: العمودان لا يُقرآن من القاعدة أصلاً،
فتُغطّى المسارات الثلاثة (القائمة، المنتج، الحملة) بالبناء لا بثلاثة شروط.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from inventory.models import Product, UnitOfMeasure
from store.models import StoreCollection, StoreCollectionItem, StoreSettings
from store.tests.test_public_leakage import _walk
from tenants.services import create_company

#: تمثيلات السعرين المزروعين كما قد تخرج من ORM/DRF.
PRICE_TRACES = {
    99, 99.0, Decimal("99"), "99", "99.0", "99.00", "99.0000",
    77, 77.0, Decimal("77"), "77", "77.0", "77.00", "77.0000",
}


class StorePriceVisibilityTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uom = UnitOfMeasure.objects.create(code="PCS", name_ar="قطعة")
        cls.user = User.objects.create_user(username="pv", password="pw123456")
        cls.tenant = create_company("شركة الأسعار", cls.user)
        cls.tenant.store_slug = "prices"
        cls.tenant.save()

        # سعران مزروعان: المتجري والتشغيلي — كلاهما يجب أن يختفي.
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="P-99", name_ar="منتج مُسعَّر",
            is_for_sale_online=True, online_price=Decimal("99.00"),
            sale_price=Decimal("77.00"), quantity_on_hand=Decimal("5"),
            uom=cls.uom,
        )
        cls.collection = StoreCollection.objects.create(
            tenant=cls.tenant, title="حملة", slug="camp",
            featured_product=cls.product,
        )
        StoreCollectionItem.objects.create(
            tenant=cls.tenant, collection=cls.collection, product=cls.product,
        )

    def setUp(self):
        self.public = APIClient()
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.TenantID)

    def _hide_prices(self):
        settings_row, _ = StoreSettings.objects.get_or_create(tenant=self.tenant)
        settings_row.show_prices = False
        settings_row.save(update_fields=["show_prices"])

    # ── الافتراضي: الأسعار ظاهرة كما كانت ──────────────────────────────

    def test_prices_are_shown_by_default(self):
        """المفتاح افتراضيه `True` — لا متجر قائم يفقد أسعاره بالترقية."""
        body = self.public.get("/api/store/prices/products/").json()
        self.assertEqual(Decimal(body["results"][0]["price"]), Decimal("99.00"))
        self.assertTrue(self.public.get("/api/store/prices/").json()["show_prices"])

    # ── الحجب من الحمولة نفسها ─────────────────────────────────────────

    def test_hidden_prices_leave_no_trace_in_any_public_payload(self):
        """لا أثر للسعرين في أي حمولة عامة — مسحٌ تكراري لا غياب مفتاحٍ واحد."""
        self._hide_prices()
        payloads = {
            "list": self.public.get("/api/store/prices/products/").json(),
            "detail": self.public.get(
                f"/api/store/prices/products/{self.product.id}/").json(),
            "campaign": self.public.get(
                "/api/store/prices/collections/camp/").json(),
            "profile": self.public.get("/api/store/prices/").json(),
        }
        for name, body in payloads.items():
            for path, value in _walk(body):
                self.assertNotIn(
                    value, PRICE_TRACES,
                    f"تسريب سعر في {name} عند {path}: {value!r}",
                )

    def test_the_price_key_stays_but_goes_null(self):
        """المفتاح يبقى في العقد وقيمته `null` — لا تغيير في القائمة البيضاء."""
        self._hide_prices()
        row = self.public.get("/api/store/prices/products/").json()["results"][0]
        self.assertIn("price", row)
        self.assertIsNone(row["price"])

    def test_the_profile_announces_the_switch(self):
        """الواجهة تحتاج معرفة الحالة لتُخفي الفرز بالسعر ومبالغ السلة."""
        self._hide_prices()
        self.assertFalse(self.public.get("/api/store/prices/").json()["show_prices"])

    def test_hiding_prices_does_not_hide_the_products(self):
        """متجرٌ بلا أسعار يبقى كتالوجاً كاملاً — الحجب للأرقام لا للمنتجات."""
        self._hide_prices()
        body = self.public.get("/api/store/prices/products/").json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], self.product.id)
        self.assertEqual(body["results"][0]["availability"], "available")

    # ── الضبط من لوحة الإدارة ──────────────────────────────────────────

    def test_the_switch_is_settable_from_the_admin_panel(self):
        res = self.auth.patch(
            "/api/store/admin/settings/", {"show_prices": False}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertFalse(res.json()["show_prices"])
        # وينعكس فوراً على المتجر العام — إبطال الكاش من EXEC-1 يعمل.
        row = self.public.get("/api/store/prices/products/").json()["results"][0]
        self.assertIsNone(row["price"])

    def test_sorting_by_price_is_inert_when_prices_are_hidden(self):
        """فرزٌ بسعرٍ محجوب لا ينهار ولا يعيد ترتيباً عشوائياً."""
        self._hide_prices()
        res = self.public.get(
            "/api/store/prices/products/", {"sort": "price_asc"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["count"], 1)
