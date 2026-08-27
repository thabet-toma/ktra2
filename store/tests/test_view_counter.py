"""عدّاد المشاهدات — الكتابة الوحيدة التي يُطلقها زائر مجهول في المنصة.

ما يحرسه هذا الملف ليس العدّ بل **حدوده**: أين يُكتب، وأين لا يُكتب أبداً،
وأنه لا يلمس صفّ المنتج نفسه.
"""
from decimal import Decimal

from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient

from inventory.models import Product
from store.models import StoreProductView
from tenants.models import Tenant


class StoreViewCounterTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            CompanyName="متجر العدّاد", SubscriptionPlan="Pro", Status="Active",
            store_slug="counter")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="C-1", name_ar="منتج مشاهَد",
            is_for_sale_online=True, online_price=Decimal("9.00"),
            quantity_on_hand=Decimal("4"), avg_cost=Decimal("2"))

    def setUp(self):
        self.client = APIClient()

    def _open_detail(self):
        return self.client.get(
            f"/api/store/counter/products/{self.product.id}/")

    def _row(self):
        return StoreProductView.objects.filter(
            tenant=self.tenant, product=self.product,
            view_date=timezone.localdate()).first()

    def test_opening_a_product_page_counts_one_view(self):
        self.assertEqual(self._open_detail().status_code, 200)
        self.assertEqual(self._row().count, 1)

    def test_repeat_views_accumulate_on_the_same_daily_row(self):
        for _ in range(3):
            self._open_detail()
        self.assertEqual(
            StoreProductView.objects.filter(product=self.product).count(), 1,
            "التجميع يومي — صفّ واحد لليوم لا صفّ لكل مشاهدة")
        self.assertEqual(self._row().count, 3)

    def test_the_list_page_never_writes_a_view(self):
        """المرور في شبكة المنتجات ليس مشاهدة — وإلا صار كل تصفّح كتابةً."""
        self.client.get("/api/store/counter/products/")
        self.assertFalse(StoreProductView.objects.exists())

    def test_a_404_never_writes_a_view(self):
        other = Tenant.objects.create(
            CompanyName="أخرى", SubscriptionPlan="Basic", Status="Active",
            store_slug="counter-other")
        hidden = Product.objects.create(
            tenant=other, sku="H-1", name_ar="مخفي", is_for_sale_online=True)
        res = self.client.get(f"/api/store/counter/products/{hidden.id}/")
        self.assertEqual(res.status_code, 404)
        self.assertFalse(StoreProductView.objects.exists())

    def test_the_counter_never_touches_the_product_row(self):
        """صفّ المنتج يعيش في قلب الـERP — مسارٌ مجهول لا يكتب عليه.

        الرصيد والتكلفة يبقيان بالضبط كما كانا: المتجر قراءة فقط، و
        `record_stock_movement` يبقى الكاتب الوحيد للرصيد.
        """
        before = Product.objects.get(pk=self.product.pk)
        self._open_detail()
        after = Product.objects.get(pk=self.product.pk)
        self.assertEqual(after.quantity_on_hand, before.quantity_on_hand)
        self.assertEqual(after.avg_cost, before.avg_cost)
        self.assertEqual(after.online_price, before.online_price)

    def test_counters_are_isolated_per_tenant(self):
        self._open_detail()
        rows = StoreProductView.objects.all()
        self.assertEqual({row.tenant_id for row in rows}, {self.tenant.pk})
