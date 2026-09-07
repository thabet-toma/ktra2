"""نماذج كتالوج المتجر المستقلّ (مواصفة #166 — المرحلة ١): ما يُختبَر بالنموذج
لا بالهجرة — تحقّق العمق، فرادة الـslug، سجلّ الأسعار، والحالة الافتراضية.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase

from store.models import StoreCategory, StorePriceHistory, StoreProduct
from tenants.models import Tenant


def _tenant(name="متجر الاختبار"):
    return Tenant.objects.create(CompanyName=name, SubscriptionPlan="Pro")


class StoreCategoryDepthTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()

    def test_a_two_level_category_is_valid(self):
        parent = StoreCategory.objects.create(
            tenant=self.tenant, name="إلكترونيات", slug="electronics"
        )
        child = StoreCategory(
            tenant=self.tenant, name="هواتف", slug="phones", parent=parent
        )
        child.full_clean()  # لا يرمي

    def test_a_grandchild_is_rejected(self):
        grandparent = StoreCategory.objects.create(
            tenant=self.tenant, name="إلكترونيات", slug="electronics"
        )
        parent = StoreCategory.objects.create(
            tenant=self.tenant, name="هواتف", slug="phones", parent=grandparent
        )
        grandchild = StoreCategory(
            tenant=self.tenant, name="إكسسوارات هواتف", slug="phone-accessories",
            parent=parent,
        )
        with self.assertRaises(ValidationError):
            grandchild.clean()

    def test_a_category_cannot_be_its_own_parent(self):
        category = StoreCategory.objects.create(
            tenant=self.tenant, name="إلكترونيات", slug="electronics"
        )
        category.parent_id = category.pk
        with self.assertRaises(ValidationError):
            category.clean()

    def test_reparenting_a_category_that_already_has_children_is_rejected(self):
        # الحفرة الأصلية: `clean()` كان يفحص أبَ الأب الجديد فقط، ولا يفحص
        # أبناءَ الفئة نفسها — فإعادةُ تأبية «أ» (ولها ابنٌ «ب») تحت جذرٍ آخر
        # «ج» كانت تمرّ فتصير الشجرةُ الفعليّة ج←أ←ب، أي ثلاثةَ مستويات.
        a = StoreCategory.objects.create(tenant=self.tenant, name="أ", slug="a")
        StoreCategory.objects.create(
            tenant=self.tenant, name="ب", slug="b", parent=a
        )
        c = StoreCategory.objects.create(tenant=self.tenant, name="ج", slug="c")
        a.parent = c
        with self.assertRaises(ValidationError):
            a.save()

    def test_objects_create_with_a_grandchild_parent_is_rejected(self):
        # الحفرة الثانية: `clean()` لا يُستدعى من `save()` في جانغو، فـ
        # `objects.create()` كان يتجاوز التحقّق كلّياً وبصمت — لا استثناء.
        grandparent = StoreCategory.objects.create(
            tenant=self.tenant, name="إلكترونيات", slug="electronics"
        )
        parent = StoreCategory.objects.create(
            tenant=self.tenant, name="هواتف", slug="phones", parent=grandparent
        )
        with self.assertRaises(ValidationError):
            StoreCategory.objects.create(
                tenant=self.tenant, name="إكسسوارات", slug="accessories",
                parent=parent,
            )

    def test_bulk_create_bypasses_validation_by_design(self):
        # الهجرةُ تستعمل `bulk_create` عمداً (لا تمرّ بـ`save()`) — يجب أن
        # يبقى يعمل بلا استثناءٍ حتى لو حُقن به عمقٌ غيرُ صالح، فهذا مسارٌ
        # واعٍ يتحمّل بناؤه صحّةَ المدخلات، لا مساراً منسيّاً يجب حراسته.
        parent = StoreCategory.objects.create(
            tenant=self.tenant, name="أب", slug="parent-bulk"
        )
        created = StoreCategory.objects.bulk_create([
            StoreCategory(
                tenant=self.tenant, name="فئة١", slug="bulk-1", parent=parent,
            ),
            StoreCategory(
                tenant=self.tenant, name="فئة٢", slug="bulk-2", parent=parent,
            ),
        ])
        self.assertEqual(len(created), 2)


class StoreProductSlugTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()

    def test_slug_is_generated_from_arabic_name(self):
        product = StoreProduct.objects.create(tenant=self.tenant, name_ar="جوال سامسونج")
        self.assertTrue(product.slug)

    def test_a_slug_collision_gets_a_numeric_suffix(self):
        first = StoreProduct.objects.create(tenant=self.tenant, name_ar="جوال")
        second = StoreProduct.objects.create(tenant=self.tenant, name_ar="جوال")
        self.assertNotEqual(first.slug, second.slug)
        self.assertTrue(second.slug.startswith(first.slug))

    def test_an_explicit_slug_is_kept_as_is(self):
        product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="جوال", slug="my-custom-slug"
        )
        self.assertEqual(product.slug, "my-custom-slug")

    def test_the_same_slug_is_allowed_across_different_tenants(self):
        other_tenant = _tenant("متجرٌ آخر")
        first = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="جوال", slug="phone"
        )
        second = StoreProduct.objects.create(
            tenant=other_tenant, name_ar="جوال", slug="phone"
        )
        self.assertEqual(first.slug, second.slug)


class StoreProductDefaultsTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()

    def test_stock_state_defaults_to_in_stock(self):
        product = StoreProduct.objects.create(tenant=self.tenant, name_ar="جوال")
        self.assertEqual(product.stock_state, StoreProduct.STOCK_IN_STOCK)


class StorePriceHistoryTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()

    def test_creating_a_product_with_a_price_writes_history(self):
        product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="جوال", price="100.00"
        )
        self.assertEqual(
            StorePriceHistory.objects.filter(store_product=product).count(), 1
        )
        self.assertEqual(
            StorePriceHistory.objects.get(store_product=product).price, 100
        )

    def test_saving_with_the_same_price_writes_nothing_new(self):
        product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="جوال", price="100.00"
        )
        product.description = "وصفٌ جديد لا يمسّ السعر"
        product.save()
        self.assertEqual(
            StorePriceHistory.objects.filter(store_product=product).count(), 1
        )

    def test_changing_the_price_writes_a_new_history_row(self):
        product = StoreProduct.objects.create(
            tenant=self.tenant, name_ar="جوال", price="100.00"
        )
        product.price = "90.00"
        product.save()
        self.assertEqual(
            StorePriceHistory.objects.filter(store_product=product).count(), 2
        )
