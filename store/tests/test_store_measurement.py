"""مواصفة #166 م٥ — القياس: `StoreCollectionView` (نظير `StoreProductView`)
و`StoreOrderIntent` (لقطةُ نيّةٍ قبل واتساب، لا مستند)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from store.models import StoreCollection, StoreCollectionView, StoreOrderIntent, StoreProduct
from tenants.models import Tenant
from tenants.services import create_company

BOT_UA = "facebookexternalhit/1.1"


class StoreCollectionViewCounterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="متجر عدّاد الحملات", SubscriptionPlan="Pro", Status="Active",
            store_slug="camp-counter")
        cls.collection = StoreCollection.objects.create(
            tenant=cls.tenant, title="حملة", slug="camp-1")

    def setUp(self):
        self.client = APIClient()

    def _open(self, **headers):
        return self.client.get(
            f"/api/store/camp-counter/collections/{self.collection.slug}/", **headers)

    def _row(self):
        return StoreCollectionView.objects.filter(
            tenant=self.tenant, collection=self.collection,
            view_date=timezone.localdate()).first()

    def test_opening_the_campaign_page_counts_one_view(self):
        self.assertEqual(self._open().status_code, 200)
        self.assertEqual(self._row().count, 1)

    def test_repeat_views_accumulate_on_the_same_daily_row(self):
        for _ in range(3):
            self._open()
        self.assertEqual(
            StoreCollectionView.objects.filter(collection=self.collection).count(), 1)
        self.assertEqual(self._row().count, 3)

    def test_a_crawler_user_agent_does_not_increment_the_counter(self):
        self.assertEqual(self._open(HTTP_USER_AGENT=BOT_UA).status_code, 200)
        self.assertIsNone(self._row())

    def test_a_missing_collection_never_writes_a_view(self):
        res = self.client.get("/api/store/camp-counter/collections/does-not-exist/")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(StoreCollectionView.objects.exists())


class StoreOrderIntentTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="متجر النيّات", SubscriptionPlan="Pro", Status="Active",
            store_slug="intent-shop")
        cls.other_tenant = Tenant.objects.create(
            CompanyName="شركة أخرى", SubscriptionPlan="Basic", Status="Active",
            store_slug="intent-other")
        cls.product = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="منتج", price=Decimal("100.00"),
            sale_price=Decimal("80.00"))
        cls.foreign_product = StoreProduct.objects.create(
            tenant=cls.other_tenant, name_ar="منتج غريب", price=Decimal("500.00"))

    def setUp(self):
        self.client = APIClient()

    def _post(self, items, **extra):
        return self.client.post(
            "/api/store/intent-shop/order-intent/",
            {"items": items}, format="json", **extra,
        )

    def test_intent_is_written_with_a_server_computed_total(self):
        res = self._post([{"product_id": self.product.id, "quantity": 2}])
        self.assertEqual(res.status_code, 201, res.content[:300])
        intent = StoreOrderIntent.objects.get(tenant=self.tenant)
        # sale_price (80) يفوز على price (100) — نفس منطق `effective_price`.
        self.assertEqual(intent.total, Decimal("160.00"))
        self.assertEqual(intent.items[0]["product_id"], self.product.id)
        self.assertEqual(intent.items[0]["quantity"], 2)

    def test_the_client_supplied_total_is_ignored(self):
        """السعر القادم من العميل لا يُقرأ إطلاقاً — الخادم يحسبه بنفسه."""
        res = self.client.post(
            "/api/store/intent-shop/order-intent/",
            {
                "items": [{"product_id": self.product.id, "quantity": 1}],
                "total": "1.00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        intent = StoreOrderIntent.objects.get(tenant=self.tenant)
        self.assertEqual(intent.total, Decimal("80.00"))

    def test_a_product_id_from_another_tenant_is_dropped(self):
        res = self._post([
            {"product_id": self.product.id, "quantity": 1},
            {"product_id": self.foreign_product.id, "quantity": 5},
        ])
        self.assertEqual(res.status_code, 201, res.content[:300])
        intent = StoreOrderIntent.objects.get(tenant=self.tenant)
        self.assertEqual(len(intent.items), 1)
        self.assertEqual(intent.items[0]["product_id"], self.product.id)

    def test_all_ids_foreign_or_unknown_is_a_400(self):
        res = self._post([{"product_id": self.foreign_product.id, "quantity": 1}])
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertFalse(StoreOrderIntent.objects.exists())

    def test_empty_items_is_a_400(self):
        res = self._post([])
        self.assertEqual(res.status_code, 400)

    def test_too_many_items_is_a_400(self):
        items = [{"product_id": self.product.id, "quantity": 1}] * 51
        res = self._post(items)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(StoreOrderIntent.objects.exists())

    def test_a_crawler_gets_a_success_response_but_writes_nothing(self):
        """فشلُ التسجيل (أو تجاهله) لا يمنع الاستجابة الناجحة أبداً."""
        res = self._post(
            [{"product_id": self.product.id, "quantity": 1}],
            HTTP_USER_AGENT=BOT_UA,
        )
        self.assertEqual(res.status_code, 201, res.content[:300])
        self.assertFalse(StoreOrderIntent.objects.exists())

    def test_intent_can_be_linked_to_an_active_collection(self):
        collection = StoreCollection.objects.create(
            tenant=self.tenant, title="حملة", slug="linked-camp")
        res = self._post(
            [{"product_id": self.product.id, "quantity": 1}],
        )
        self.assertEqual(res.status_code, 201)
        res2 = self.client.post(
            "/api/store/intent-shop/order-intent/",
            {
                "items": [{"product_id": self.product.id, "quantity": 1}],
                "collection_slug": collection.slug,
            },
            format="json",
        )
        self.assertEqual(res2.status_code, 201, res2.content[:300])
        linked = StoreOrderIntent.objects.filter(collection=collection).first()
        self.assertIsNotNone(linked)

    def test_intent_has_no_customer_identity_fields(self):
        """ليست مستنداً: لا اسم ولا هاتف ولا عنوان ولا حالة."""
        fields = {f.name for f in StoreOrderIntent._meta.get_fields()}
        for forbidden in ("customer_name", "phone", "address", "status"):
            self.assertNotIn(forbidden, fields)


class StoreCollectionAdminMeasurementDisplayTest(TestCase):
    """صفّ الحملة في شاشة إدارة المتجر يعرض مشاهدات/طلبات/نسبة تحويل."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="measure-owner", password="x")
        cls.tenant = create_company("شركة القياس", cls.user)
        cls.tenant.store_slug = "measure-shop"
        cls.tenant.save()
        cls.collection = StoreCollection.objects.create(
            tenant=cls.tenant, title="حملة", slug="measured-camp")
        cls.product = StoreProduct.objects.create(
            tenant=cls.tenant, name_ar="منتج", price=Decimal("10.00"))

    def setUp(self):
        self.auth = APIClient()
        self.auth.force_authenticate(user=self.user)
        self.auth.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.pk)
        self.anon = APIClient()

    def test_views_and_orders_and_conversion_rate_appear_on_the_row(self):
        for _ in range(4):
            self.anon.get(
                f"/api/store/measure-shop/collections/{self.collection.slug}/")
        StoreOrderIntent.objects.create(
            tenant=self.tenant, collection=self.collection,
            items=[{"product_id": self.product.id, "quantity": 1}],
            total=Decimal("10.00"),
        )

        res = self.auth.get("/api/store/admin/collections/")
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        rows = body["results"] if isinstance(body, dict) else body
        row = next(r for r in rows if r["id"] == self.collection.id)
        self.assertEqual(row["views_count"], 4)
        self.assertEqual(row["orders_count"], 1)
        self.assertEqual(row["conversion_rate"], 25.0)

    def test_conversion_rate_is_null_without_views(self):
        res = self.auth.get("/api/store/admin/collections/")
        body = res.json()
        rows = body["results"] if isinstance(body, dict) else body
        row = next(r for r in rows if r["id"] == self.collection.id)
        self.assertEqual(row["views_count"], 0)
        self.assertEqual(row["orders_count"], 0)
        self.assertIsNone(row["conversion_rate"])

    def test_counts_do_not_fan_out_with_multiple_collection_items(self):
        """ضمّان مستقلّان (مشاهدات وطلبات) فوق ضمّ `items` القائم لا يتضاعفان."""
        from store.models import StoreCollectionItem

        second_product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="منتج ثانٍ", price=Decimal("5.00"))
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=self.collection, store_product=self.product)
        StoreCollectionItem.objects.create(
            tenant=self.tenant, collection=self.collection, store_product=second_product)
        for _ in range(3):
            self.anon.get(
                f"/api/store/measure-shop/collections/{self.collection.slug}/")
        StoreOrderIntent.objects.create(
            tenant=self.tenant, collection=self.collection, items=[], total=Decimal("0"))
        StoreOrderIntent.objects.create(
            tenant=self.tenant, collection=self.collection, items=[], total=Decimal("0"))

        res = self.auth.get("/api/store/admin/collections/")
        body = res.json()
        rows = body["results"] if isinstance(body, dict) else body
        row = next(r for r in rows if r["id"] == self.collection.id)
        self.assertEqual(row["items_count"], 2)
        self.assertEqual(row["views_count"], 3)
        self.assertEqual(row["orders_count"], 2)
