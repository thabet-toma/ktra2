"""ST-3 — الثلاثة التي لا يغطّيها اختبارٌ آخر في رحلة «متجري».

سلسلةُ «افتح ثم انشر فيراه الزائر» مثبَّتةٌ في `test_store_slug.py`
(`test_the_whole_journey_open_then_publish_then_it_is_public`)، وقواعد السعر
والتوفّر في `test_store_api.py` — فلا تُكرَّر هنا. ما يبقى بلا حارس ثلاثة:

1. **مراجعة أول تفعيل** — الاستعلام الذي يقرؤه الحوار قبل فتح المتجر. سببها
   أن `is_for_sale_online` علمٌ قديم سابق للمتجر (ورفيقه `online_price` تقرؤه
   الفوترة)، فقد يكون معلَّماً على منتجات بلا نيّة نشر، وتصير علنيةً لحظةَ
   اختيار المعرّف.
2. **فورية الظهور** — قائمة المتجر تُكاش ٦٠ ثانية، لكن كتابات النشر تُبطل
   الكاش (THA-423، `store/cache.py`)، فالنشر يظهر فوراً. كان يتأخّر دقيقةً
   قبل الإبطال، وهو ما كان يجعل الناشر يظنّ الحفظ فشل فيعيد الكرّة.
3. **الاتجاه العكسي** — إلغاء النشر يُخفي المنتج فعلاً؛ لا قيمة لمفتاحٍ يفتح
   ولا يُغلق.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from inventory.models import Product
from tenants.models import Tenant
from tenants.services import create_company

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=_LOCMEM)
class StorePublishFlowTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(username="flow-owner", password="x")
        self.tenant = create_company("شركة الرحلة", self.manager)

        # منتجٌ عُلِّم «للبيع عبر الإنترنت» قبل وجود المتجر — الحالة التي وُضعت
        # مراجعة أول تفعيل من أجلها بالضبط.
        self.legacy = Product.objects.create(
            tenant=self.tenant, sku="OLD-1", name_ar="منتج مُسعَّر قديماً",
            is_for_sale_online=True, sale_price=Decimal("25.00"),
            quantity_on_hand=Decimal("5"))
        self.fresh = Product.objects.create(
            tenant=self.tenant, sku="NEW-1", name_ar="منتج لم يُنشر بعد",
            is_for_sale_online=False, sale_price=Decimal("40.00"),
            quantity_on_hand=Decimal("8"))

    def _manager(self):
        client = APIClient()
        client.force_authenticate(user=self.manager)
        return client

    def _open_store(self, slug="flow-shop"):
        res = self._manager().post(
            f"/api/tenants/companies/{self.tenant.pk}/set-store-slug/",
            {"store_slug": slug}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk))
        self.assertEqual(res.status_code, 200, res.content[:300])

    def _public_names(self, slug="flow-shop"):
        res = APIClient().get(f"/api/store/{slug}/products/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        return {row["name_ar"] for row in res.json()["results"]}

    def _publish(self, product, published, **extra):
        res = self._manager().patch(
            f"/api/inventory/products/{product.pk}/",
            {"is_for_sale_online": published, **extra}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.pk))
        self.assertEqual(res.status_code, 200, res.content[:300])

    # ── ١) ما يعرضه حوار أول تفعيل ───────────────────────────────────────
    def test_the_first_activation_review_names_what_is_about_to_become_public(self):
        """الحوار لا يخمّن: يقرأ نفس القائمة التي سيراها الزائر بعد الفتح.

        المتجر ما زال مقفلاً هنا (`store_slug` فارغ)، والقائمة تُقرأ مع ذلك —
        وهذا هو المقصود: تُعرَض **قبل** الفتح لا بعده.
        """
        self.assertIsNone(Tenant.objects.get(pk=self.tenant.pk).store_slug)
        res = self._manager().get(
            "/api/inventory/products/?view=lookup&is_for_sale_online=true&page=1",
            HTTP_X_TENANT_ID=str(self.tenant.pk))
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["name_ar"], "منتج مُسعَّر قديماً")

        # وما عُرِض هو حرفياً ما يصير علنياً بعد الفتح — لا أكثر ولا أقل.
        self._open_store()
        self.assertEqual(self._public_names(), {"منتج مُسعَّر قديماً"})

    # ── ٢) تأخّر الظهور بمقدار عمر الكاش ─────────────────────────────────
    def test_a_freshly_published_item_appears_immediately(self):
        """النشر يظهر فوراً — الكاش لا يحجبه دقيقةً بعد الحفظ.

        كان يتأخّر إلى انتهاء الـTTL: مفاتيح القائمة بصمةُ معاملات لا تُمسح
        بنمط، فلم يكن للنشر ما يُبطلها. صار المفتاح يحمل رقم نسخةٍ لكل شركة
        (`store/cache.py`) وكلُّ كتابة نشرٍ ترفعه، فتُهجَر الحمولة القديمة.
        """
        self._open_store()
        self.assertEqual(self._public_names(), {"منتج مُسعَّر قديماً"})  # يملأ الكاش

        self._publish(self.fresh, True, online_price="33.00")
        self.assertEqual(
            self._public_names(), {"منتج مُسعَّر قديماً", "منتج لم يُنشر بعد"})

    # ── ٣) الاتجاه العكسي ────────────────────────────────────────────────
    def test_unpublishing_removes_the_item_from_the_storefront(self):
        self._open_store()
        self.assertEqual(self._public_names(), {"منتج مُسعَّر قديماً"})

        self._publish(self.legacy, False)
        self.assertEqual(self._public_names(), set())  # بلا انتظار TTL

        # والصفحة المباشرة للمنتج تصير 404 — لا صفحةٌ يتيمة يبقى رابطها حيّاً.
        self.assertEqual(
            APIClient().get(
                f"/api/store/flow-shop/products/{self.legacy.pk}/").status_code,
            404)
