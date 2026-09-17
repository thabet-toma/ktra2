"""#21: «هذا موجود — أضف براند».

اقتراحٌ مطبَّعٌ (لا حرفي، ولا صوتي) عند تسجيل اسمٍ موجود — اقتراحٌ لا منع. ومن
داخل شاشة المنتج: أوّل براندٍ صريح يُسمّي البراند الضمنيّ الوحيد (تحديثٌ لصفّه
القائم، لا صفٌّ جديد)، والثاني فصاعداً يُنشئ صفّاً تحت **نفس** الأب. بلا حركة
مخزون ولا قيد محاسبي في الحالتين.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import JournalHeader
from inventory.models import Product, ProductFamily, StockMovement
from inventory.services import record_stock_movement
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"
FAMILIES_URL = "/api/inventory/product-families/"


class ProductNameOfferTest(APITestCase):
    """1) الاقتراح يفتح لاسمٍ مطابقٍ بعد التطبيع. 2) لا يمنع. 6) عزل الشركات."""

    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="offer_a", password="x")
        cls.owner_b = User.objects.create_user(username="offer_b", password="x")
        cls.tenant_a = create_company("شركة الاقتراح أ", cls.owner_a)
        cls.tenant_b = create_company("شركة الاقتراح ب", cls.owner_b)

    def _auth(self, user, tenant):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(tenant.TenantID)}

    def _register(self, name, hdr):
        res = self.client.post(PRODUCTS_URL, {"name_ar": name}, format="json", **hdr)
        assert res.status_code == 201, res.content[:300]
        return res.json()

    def _check_name(self, name, hdr):
        return self.client.get(f"{FAMILIES_URL}check-name/", {"name": name}, **hdr)

    def test_offer_fires_for_a_diacritic_and_spacing_variant(self):
        hdr = self._auth(self.owner_a, self.tenant_a)
        registered = self._register("مِرْوَحَة    سقف", hdr)
        family_id = Product.objects.get(pk=registered["id"]).family_id

        res = self._check_name("مروحة سقف", hdr)
        assert res.status_code == 200
        match = res.json()["match"]
        assert match is not None
        assert match["id"] == family_id

    def test_offer_does_not_fire_for_a_consonant_difference(self):
        """«سامسونج» و«سامسونغ»: حرفٌ حقيقيٌّ مختلف، لا تنويع كتابة — لا اقتراح."""
        hdr = self._auth(self.owner_a, self.tenant_a)
        self._register("سامسونج", hdr)

        res = self._check_name("سامسونغ", hdr)
        assert res.status_code == 200
        assert res.json()["match"] is None

    def test_offer_does_not_block_registering_a_genuinely_different_product(self):
        hdr = self._auth(self.owner_a, self.tenant_a)
        self._register("مروحة سقف", hdr)
        before = ProductFamily.objects.filter(tenant=self.tenant_a).count()

        offer = self._check_name("مروحة سقف", hdr)
        assert offer.json()["match"] is not None  # الاقتراح ظهر...

        second = self._register("مروحة سقف توربو", hdr)  # ...لكنه لم يمنع التسجيل
        assert ProductFamily.objects.filter(tenant=self.tenant_a).count() == before + 1
        first_family_id = Product.objects.filter(
            tenant=self.tenant_a, name_ar="مروحة سقف"
        ).first().family_id
        second_family_id = Product.objects.get(pk=second["id"]).family_id
        assert second_family_id != first_family_id

    def test_offer_never_matches_another_companys_product(self):
        hdr_a = self._auth(self.owner_a, self.tenant_a)
        self._register("جهاز اختبار العزل", hdr_a)

        hdr_b = self._auth(self.owner_b, self.tenant_b)
        res = self._check_name("جهاز اختبار العزل", hdr_b)
        assert res.status_code == 200
        assert res.json()["match"] is None


class AddBrandTest(APITestCase):
    """3) أوّل براندٍ صريح يُسمّي الضمنيّ. 4) الثاني يُنشئ صفّاً تحت نفس الأب.
    5) بلا حركة مخزون ولا قيد محاسبي في الحالتين."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="brand_owner", password="x")
        cls.tenant = create_company("شركة إضافة البراند", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _register(self, name):
        res = self.client.post(PRODUCTS_URL, {"name_ar": name}, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"])

    def _add_brand(self, family_id, brand, sku=None):
        payload = {"family_id": family_id, "brand": brand}
        if sku:
            payload["sku"] = sku
        return self.client.post(
            f"{PRODUCTS_URL}add-brand/", payload, format="json", **self.hdr,
        )

    def test_first_explicit_brand_renames_the_implicit_row(self):
        implicit = self._register("مقاس إطار 195/85/15")
        family_id = implicit.family_id
        # تاريخٌ حقيقيّ على الصفّ الضمنيّ قبل التسمية — يجب أن يبقى بعدها.
        record_stock_movement(
            product=implicit, movement_type="IN", quantity=Decimal("10"),
            unit_cost=Decimal("5"), movement_date="2026-06-01", tenant=self.tenant,
        )

        res = self._add_brand(family_id, "دانتير")
        assert res.status_code == 200, res.content[:300]
        data = res.json()
        assert data["created"] is False
        assert data["id"] == implicit.id  # نفس الصفّ، لا صفّ جديد

        assert Product.objects.filter(family_id=family_id).count() == 1
        implicit.refresh_from_db()
        assert implicit.brand == "دانتير"
        assert implicit.quantity_on_hand == Decimal("10")  # التاريخ ورث كاملاً
        assert StockMovement.objects.filter(product=implicit).count() == 1

    def test_second_brand_creates_new_row_under_same_parent_not_a_second_one(self):
        implicit = self._register("مقاس إطار 205/55/16")
        family_id = implicit.family_id
        self._add_brand(family_id, "دانتير")

        res = self._add_brand(family_id, "أوتولوكس")
        assert res.status_code == 201, res.content[:300]
        data = res.json()
        assert data["created"] is True
        assert data["id"] != implicit.id

        brands = Product.objects.filter(family_id=family_id)
        assert brands.count() == 2
        assert set(brands.values_list("brand", flat=True)) == {"دانتير", "أوتولوكس"}
        assert ProductFamily.objects.filter(tenant=self.tenant).count() == 1

        new_brand = Product.objects.get(pk=data["id"])
        assert new_brand.quantity_on_hand == Decimal("0")
        assert new_brand.avg_cost == Decimal("0")

    def test_neither_case_moves_stock_or_posts_a_journal(self):
        implicit = self._register("منتج بلا أثر محاسبي")
        family_id = implicit.family_id
        record_stock_movement(
            product=implicit, movement_type="IN", quantity=Decimal("4"),
            unit_cost=Decimal("2"), movement_date="2026-06-01", tenant=self.tenant,
        )

        movements_before = StockMovement.objects.filter(tenant=self.tenant).count()
        journals_before = JournalHeader.objects.filter(tenant=self.tenant).count()
        qty_before = Product.objects.get(pk=implicit.id).quantity_on_hand
        cost_before = Product.objects.get(pk=implicit.id).avg_cost

        first = self._add_brand(family_id, "دانتير")
        assert first.status_code == 200
        second = self._add_brand(family_id, "أوتولوكس")
        assert second.status_code == 201

        assert StockMovement.objects.filter(tenant=self.tenant).count() == movements_before
        assert JournalHeader.objects.filter(tenant=self.tenant).count() == journals_before
        implicit.refresh_from_db()
        assert implicit.quantity_on_hand == qty_before
        assert implicit.avg_cost == cost_before

    def test_add_brand_requires_a_brand_name(self):
        implicit = self._register("منتج بلا اسم براند")
        res = self._add_brand(implicit.family_id, "")
        assert res.status_code == 400

    def test_add_brand_rejects_a_foreign_company_family(self):
        other_owner = User.objects.create_user(username="brand_other", password="x")
        other_tenant = create_company("شركة أخرى للبراند", other_owner)
        self.client.force_authenticate(user=other_owner)
        foreign = self.client.post(
            PRODUCTS_URL, {"name_ar": "منتج شركة أخرى"}, format="json",
            HTTP_X_TENANT_ID=str(other_tenant.TenantID),
        ).json()
        foreign_family_id = Product.objects.get(pk=foreign["id"]).family_id

        self.client.force_authenticate(user=self.owner)
        res = self._add_brand(foreign_family_id, "براند")
        assert res.status_code == 404


class ProductNameOfferForLegacyProductsTest(APITestCase):
    """«هذا موجود» كان يبحث في الآباء وحدَها (`ProductFamily`) — فمنتجٌ قديمٌ بلا أب
    (أغلبُ الكتالوج) لا يُقترَح أبداً، ويُسجَّل اسمُه مرّةً ثانيةً منتجاً منفصلاً.
    المطابقةُ تشمل الآن الصفوفَ بلا أب، والردُّ يسمّي ما يُرسَل إلى `add-brand`."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="legacy_offer_owner", password="x")
        cls.tenant = create_company("شركة الاقتراح القديم", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _check(self, name):
        res = self.client.get(f"{FAMILIES_URL}check-name/", {"name": name}, **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return res.json()["match"]

    def test_a_familyless_product_is_offered_by_its_product_id(self):
        legacy = Product.objects.create(
            tenant=self.tenant, sku="OFFER-LEG-1", name_ar="بطّارية 70 أمبير", family=None,
        )
        match = self._check("بطارية  70 أمبير")
        assert match is not None
        assert match["product_id"] == legacy.id
        assert match["family_id"] is None
        assert match["id"] is None  # `id` يبقى معرّفَ الأب كما كان — ولا أبَ هنا

    def test_a_family_match_keeps_its_contract_and_names_the_family(self):
        res = self.client.post(PRODUCTS_URL, {"name_ar": "مروحة سقف"}, format="json", **self.hdr)
        family_id = Product.objects.get(pk=res.json()["id"]).family_id

        match = self._check("مروحة سقف")
        assert match["id"] == family_id
        assert match["family_id"] == family_id
        assert match["product_id"] is None

    def test_a_foreign_companys_familyless_product_is_never_offered(self):
        other = User.objects.create_user(username="legacy_offer_other", password="x")
        other_tenant = create_company("شركة غريبة للاقتراح", other)
        Product.objects.create(tenant=other_tenant, sku="OFFER-FOREIGN", name_ar="ثلاجة غريبة", family=None)
        assert self._check("ثلاجة غريبة") is None


class AddBrandToLegacyProductTest(APITestCase):
    """«أضف براند» على منتجٍ قديمٍ بلا أب — حالُ الكتالوج كلِّه تقريباً.

    كلُّ منتجٍ سُجّل قبل #20 يحمل `family_id` فارغاً (قيس على قاعدة التطوير:
    1760 من 1763). والنقطةُ كانت تشترط `family_id`، فكرتُ المنتج لا يرسم قسمَ
    البراندات أصلاً لمنتجٍ بلا أب — **لا بابَ لإضافة براندٍ لمنتجٍ قائم**، والبابُ
    الوحيدُ الباقي (زرُّ «تكرار» في القائمة) يُنشئ منتجاً منفصلاً. `product_id`
    يتبنّى له أباً (`adopt_family_for_product`) ثمّ يُضيف البراند، في معاملةٍ واحدة.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="legacy_brand_owner", password="x")
        cls.tenant = create_company("شركة البراند القديم", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _legacy(self, name, sku, brand=""):
        product = Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=name, brand=brand, family=None,
        )
        assert product.family_id is None
        return product

    def _add(self, payload):
        return self.client.post(f"{PRODUCTS_URL}add-brand/", payload, format="json", **self.hdr)

    def test_first_brand_names_the_legacy_row_and_gives_it_a_parent(self):
        legacy = self._legacy("بطارية 70 أمبير", "LEG-1")
        record_stock_movement(
            product=legacy, movement_type="IN", quantity=Decimal("6"),
            unit_cost=Decimal("40"), movement_date="2026-06-01", tenant=self.tenant,
        )

        res = self._add({"product_id": legacy.id, "brand": "فارتا"})
        assert res.status_code == 200, res.content[:300]
        data = res.json()
        assert data["created"] is False
        assert data["id"] == legacy.id

        legacy.refresh_from_db()
        assert legacy.family_id is not None
        assert data["family_id"] == legacy.family_id
        assert legacy.brand == "فارتا"
        assert legacy.quantity_on_hand == Decimal("6")
        assert ProductFamily.objects.filter(tenant=self.tenant).count() == 1

    def test_second_brand_on_a_named_legacy_row_creates_a_sibling_not_a_product(self):
        legacy = self._legacy("بطارية 100 أمبير", "LEG-2", brand="فارتا")

        res = self._add({"product_id": legacy.id, "brand": "بوش"})
        assert res.status_code == 201, res.content[:300]
        data = res.json()
        assert data["created"] is True

        legacy.refresh_from_db()
        sibling = Product.objects.get(pk=data["id"])
        assert sibling.family_id == legacy.family_id is not None
        assert set(
            Product.objects.filter(family_id=legacy.family_id).values_list("brand", flat=True)
        ) == {"فارتا", "بوش"}
        assert ProductFamily.objects.filter(tenant=self.tenant).count() == 1

    def test_product_id_of_a_row_that_already_has_a_parent_reuses_it(self):
        res = self.client.post(PRODUCTS_URL, {"name_ar": "مروحة", "brand": "توشيبا"}, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        product = Product.objects.get(pk=res.json()["id"])

        added = self._add({"product_id": product.id, "brand": "شارب"})
        assert added.status_code == 201, added.content[:300]
        assert added.json()["family_id"] == product.family_id
        assert ProductFamily.objects.filter(tenant=self.tenant).count() == 1

    def test_a_failed_add_leaves_the_legacy_row_without_a_parent(self):
        """التبنّي والإضافة معاملةٌ واحدة: رفضُ الإضافة لا يترك أباً يتيماً.

        الرفضُ يُحقَن **داخل** الإضافة نفسِها (بعد التبنّي) — رفضٌ يسبق التبنّي
        (رقمٌ مكرَّر مثلاً) يمرّ بلا معاملةٍ أصلاً فلا يختبر شيئاً."""
        from unittest import mock

        from django.core.exceptions import ValidationError as DjangoValidationError

        legacy = self._legacy("بطارية 45 أمبير", "LEG-3", brand="فارتا")

        with mock.patch(
            "inventory.services.add_brand_to_family",
            side_effect=DjangoValidationError("تعذّر توليد رقم منتج — أعد المحاولة."),
        ):
            res = self._add({"product_id": legacy.id, "brand": "بوش"})
        assert res.status_code == 400, res.content[:300]
        legacy.refresh_from_db()
        assert legacy.family_id is None
        assert ProductFamily.objects.filter(tenant=self.tenant).count() == 0

    def test_requires_a_family_or_a_product(self):
        res = self._add({"brand": "فارتا"})
        assert res.status_code == 400
        assert "family_id" in res.json()

    def test_rejects_a_foreign_company_product_without_adopting_it(self):
        other_owner = User.objects.create_user(username="legacy_brand_other", password="x")
        other_tenant = create_company("شركة أخرى قديمة", other_owner)
        foreign = Product.objects.create(
            tenant=other_tenant, sku="FOREIGN-LEG", name_ar="منتج غريب", family=None,
        )

        res = self._add({"product_id": foreign.id, "brand": "فارتا"})
        assert res.status_code == 404
        foreign.refresh_from_db()
        assert foreign.family_id is None
        assert foreign.brand == ""


class QuotationMaterializationNormalizedMatchTest(APITestCase):
    """قاعدة المطابقة الموضع الثاني: تجسيد عرض السعر (`logistics.services
    .materialize_quotation_draft_parties`) يعيد استعمال منتجاً قائماً بعد
    التطبيع، لا مطابقةً حرفية فقط."""

    @classmethod
    def setUpTestData(cls):
        from tenants.models import Currency

        cls.owner = User.objects.create_user(username="offer_quote", password="x")
        cls.tenant = create_company("شركة تطبيع عروض الأسعار", cls.owner)
        cls.currency = Currency.objects.create(
            Code="NQC", Name="Normalized Quote Currency", IsBaseCurrency=False,
        )
        from partners.models import Partner
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد محلي", partner_type="Supplier",
        )
        # ISSUE #117: هذا الاختبار يحوّل عرضاً إلى طلبية شراء — الإعداد الجديد
        # مطفأ افتراضاً، فيلزم إشعاله هنا كي يبقى الملف يختبر ما صُمّم لاختباره.
        from logistics.services import get_or_create_purchase_settings
        ps = get_or_create_purchase_settings(cls.tenant)
        ps.use_purchase_orders = True
        ps.save(update_fields=["use_purchase_orders"])

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _quotation_payload(self, name_snapshot):
        return {
            "scope": "local",
            "supplier": self.supplier.id,
            "quotation_date": "2026-08-31",
            "status": "accepted",
            "currency": self.currency.pk,
            "exchange_rate": "1.000000",
            "discount_amount": "0",
            "tax_rate": "0",
            "shipping_cost_estimate": "0",
            "is_shipping_included": False,
            "lines": [{
                "seq": 1,
                "name_snapshot": name_snapshot,
                "quantity": "3.000",
                "unit_price": "12.5000",
            }],
        }

    def test_materialization_reuses_existing_product_by_normalized_name(self):
        existing = Product.objects.create(
            tenant=self.tenant, sku="NQ-1", name_ar="مِرْوَحَة    سقف",
        )

        created = self.client.post(
            "/api/logistics/supplier-quotations/",
            self._quotation_payload("مروحة سقف"), format="json", **self.hdr,
        )
        assert created.status_code == 201, created.content[:300]
        quotation_id = created.data["id"]

        converted = self.client.post(
            f"/api/logistics/supplier-quotations/{quotation_id}/convert-to-purchase-order/",
            {}, format="json", **self.hdr,
        )
        assert converted.status_code == 201, converted.content[:300]

        assert Product.objects.filter(tenant=self.tenant).count() == 1  # لا تضاعف

        from logistics.models import SupplierQuotationLine
        line = SupplierQuotationLine.objects.get(quotation_id=quotation_id)
        assert line.product_id == existing.id


class AddBrandPlanLimitTest(APITestCase):
    """البراند الثاني صفُّ منتجٍ جديد — فلا يكون هذا الباب التفافاً على حدّ الخطة."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="brand_limit", password="x")
        cls.tenant = create_company("شركة حدّ الخطة", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _family_of(self, name):
        res = self.client.post(
            "/api/inventory/products/", {"name_ar": name}, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"]).family_id

    def _add_brand(self, family_id, brand):
        return self.client.post(
            "/api/inventory/products/add-brand/",
            {"family_id": family_id, "brand": brand}, format="json", **self.hdr)

    def test_naming_the_implicit_brand_is_never_charged_but_a_new_row_is(self):
        from unittest.mock import patch as mock_patch

        family_id = self._family_of("منتج الحدّ")

        # الحدّ مستنفَد: تسميةُ الضمنيّ لا تُنشئ صفّاً فتمرّ...
        with mock_patch("core.plans.check_limit", return_value="بلغت حدّ المنتجات."):
            named = self._add_brand(family_id, "براند أوّل")
            assert named.status_code == 200, named.content[:300]
            assert named.json()["created"] is False

            # ...والثاني صفٌّ جديد فيُرفض بالحدّ نفسه.
            second = self._add_brand(family_id, "براند ثانٍ")
            assert second.status_code == 400, second.content[:300]
            assert "plan_limit" in second.json()

        assert Product.objects.filter(family_id=family_id).count() == 1
