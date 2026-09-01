"""#25: جسر التجميع + حالة المخزون + محور البدائل.

سلوكيٌّ عبر HTTP لا استيراد دوالّ داخلية — النسخة السابقة من هذا الملف كانت
تستورد `product_group_key`/`product_group_profile`/`tire_size_key` مباشرةً
وتختبر تنفيذها لا سلوكها الخارجي. كل ما يلي يقرأ استجابة الواجهة الخادمية
(حقول السيريالايزر ونقاط الـ`action`) كما يراها المالك فعلاً.

**الأب درجةٌ أولى فوق السلّم القديم، ولا درجةٌ منه حُذفت** — ومنها درجة مقاس
الإطار: بيانات ما قبل هذا النموذج (`family_id` فارغ) لا تزال تتجمّع بلا هجرة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from inventory.models import Product, ProductFamily
from inventory.services import add_brand_to_family, record_stock_movement
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class BrandFamilyGroupingTest(APITestCase):
    """مفتاح الأب: درجةٌ أولى فوق السلّم، ولا درجةٌ قديمة تُحذف."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="bgf", password="x")
        cls.tenant = create_company("شركة تجميع البراندات", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _register(self, name, **extra):
        payload = {"name_ar": name, **extra}
        res = self.client.post(PRODUCTS_URL, payload, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        return res.json()

    def _add_brand(self, family_id, brand):
        res = self.client.post(
            f"{PRODUCTS_URL}add-brand/", {"family_id": family_id, "brand": brand},
            format="json", **self.hdr,
        )
        return res

    def _get(self, product_id):
        res = self.client.get(f"{PRODUCTS_URL}{product_id}/", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return res.json()

    # 1) براندان تحت أبٍ واحد يتشاركان مفتاح تجميعٍ واحد.
    def test_two_brands_under_one_parent_share_one_group_key(self):
        first = self._register("طابعة ليزر")
        family_id = Product.objects.get(pk=first["id"]).family_id
        family = ProductFamily.objects.get(pk=family_id)
        # أوّل براندٍ صريح يُسمّي الضمنيّ (200، نفس الصفّ)؛ الثاني ينشئ صفّاً جديداً (201).
        named = self._add_brand(family_id, "دانتير")
        assert named.status_code == 200, named.content[:300]
        second = self._add_brand(family_id, "أوتولوكس")
        assert second.status_code == 201, second.content[:300]

        first_body = self._get(named.json()["id"])
        second_body = self._get(second.json()["id"])
        assert first_body["group_key"] == second_body["group_key"]
        assert first_body["group_key"] == (family.name_ar or family.name_en)

    # منتجان بلا أبٍ مشترك (كلّ تسجيلٍ عبر الواجهة يصنع أباً مستقلاً) يحتفظان
    # بسلوك اليوم: لا يتجمّعان لمجرّد تشابه الاسم.
    def test_two_products_without_a_shared_parent_keep_todays_behaviour(self):
        a = self._register("زيت محرك 5W30")
        b = self._register("زيت محرك توربو")
        body_a = self._get(a["id"])
        body_b = self._get(b["id"])
        assert body_a["group_key"] != body_b["group_key"]

    # 2) منتجٌ أبوه بلا تجميعٍ صريح (لا مجموعة، لا مقاس، لا براند) لا يزال
    # يتجمّع — عبر مفتاح الأب وحده. لا درجةٌ حُذفت.
    def test_product_whose_parent_has_no_explicit_grouping_still_groups(self):
        registered = self._register("سماعة بلوتوث")
        body = self._get(registered["id"])
        assert body["group_key"]  # غير فارغ رغم غياب كل الدرجات الأدنى

    # درجة مقاس الإطار لم تُحذف: منتجان بلا أبٍ مشترك (بياناتٌ قديمة، كما قبل
    # هذا النموذج) لا يزالان يتجمّعان بمقاس الإطار المُستخرَج من الاسم.
    def test_tire_size_rung_still_groups_legacy_familyless_products(self):
        p1 = Product.objects.create(
            tenant=self.tenant, sku="LEG-1", name_ar="185/65/14 روك بيلد")
        p2 = Product.objects.create(
            tenant=self.tenant, sku="LEG-2", name_ar="185/65/14 جلاكسي")
        assert p1.family_id is None and p2.family_id is None  # بياناتٌ قديمة بلا أب

        body1 = self._get(p1.id)
        body2 = self._get(p2.id)
        assert body1["group_key"] == body2["group_key"] == "185/65/14"

    # درجة البراند لم تُحذف: منتجان بلا أبٍ مشترك ولا مقاس يتجمّعان بالبراند.
    def test_brand_rung_still_groups_familyless_products(self):
        p1 = Product.objects.create(
            tenant=self.tenant, sku="LEG-3", name_ar="بطارية ضفة", brand="مايكل")
        p2 = Product.objects.create(
            tenant=self.tenant, sku="LEG-4", name_ar="فتحي", brand="مايكل")
        body1 = self._get(p1.id)
        body2 = self._get(p2.id)
        assert body1["group_key"] == body2["group_key"] == "مايكل"

    # درجة المجموعة الصريحة لم تُحذف، وتبقى فوق مقاس الإطار والبراند.
    def test_explicit_variant_group_rung_still_overrides_familyless_products(self):
        p = Product.objects.create(
            tenant=self.tenant, sku="LEG-5", name_ar="انفيرتر 11 كيلو واط",
            brand="SMH", variant_group="انفيرتر 11")
        body = self._get(p.id)
        assert body["group_key"] == "انفيرتر 11"

    def test_display_name_appends_brand_in_parens(self):
        registered = self._register("مضخة مياه", brand="اسكو")
        body = self._get(registered["id"])
        assert body["display_name"] == "مضخة مياه (اسكو)"

    def test_has_group_flag_still_reflects_explicit_variant_group(self):
        registered = self._register("مضخة هواء", variant_group="مضخات الهواء")
        body = self._get(registered["id"])
        assert body["has_group"] is True

        plain = self._register("مروحة عادية")
        plain_body = self._get(plain["id"])
        assert plain_body["has_group"] is False

    # #23: الفخّ الصريح — `has_group` كانت تتجاهل الأب كلّياً. منتجٌ بأكثر من
    # براندٍ يجب أن يُظهر عنصر «كشف البراندات»، ومنتجٌ ببراندٍ واحدٍ (الضمنيّ
    # وحده) يبقى بلا عنصرٍ كما اليوم.
    def test_has_group_flag_now_reflects_multi_brand_families(self):
        first = self._register("سخّان مياه")
        family_id = Product.objects.get(pk=first["id"]).family_id
        # الأوّل يُسمّي الضمنيّ (200، نفس الصفّ)؛ الثاني ينشئ صفّاً جديداً (201).
        named = self._add_brand(family_id, "أرستون")
        assert named.status_code == 200, named.content[:300]
        second = self._add_brand(family_id, "أريستون")
        assert second.status_code == 201, second.content[:300]

        first_body = self._get(named.json()["id"])
        second_body = self._get(second.json()["id"])
        assert first_body["has_group"] is True
        assert second_body["has_group"] is True

    def test_has_group_flag_stays_false_for_a_single_brand_family(self):
        """أبٌ ببراندٍ ضمنيٍّ واحد فقط — لا شيء يُكشَف، فلا عنصر."""
        registered = self._register("مكيّف هواء")
        body = self._get(registered["id"])
        assert body["has_group"] is False

    # #23: شاشة الأصناف تحتاج معرّف الأب واسمه لتجمع صفوف البراندات في صفٍّ واحد.
    def test_full_serializer_exposes_family_id_and_family_name(self):
        first = self._register("غسّالة")
        family_id = Product.objects.get(pk=first["id"]).family_id
        family = ProductFamily.objects.get(pk=family_id)
        body = self._get(first["id"])
        assert body["family_id"] == family_id
        assert body["family_name"] == (family.name_ar or family.name_en)


class GroupProfileAndCatalogEndpointsTest(APITestCase):
    """نقاط الكرت المجمّع والفهارس (brands/groups/names/group-ledger) — عبر HTTP."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="bge", password="x")
        cls.tenant = create_company("شركة كرت البراندات", cls.owner)
        cls.p1 = Product.objects.create(
            tenant=cls.tenant, sku="E-1", name_ar="185/65/14", brand="روك بيلد")
        cls.p2 = Product.objects.create(
            tenant=cls.tenant, sku="E-2", name_ar="185/65/14", brand="جلاكسي")
        record_stock_movement(
            product=cls.p1, movement_type="IN", quantity=Decimal("3"),
            unit_cost=Decimal("100"), movement_date="2026-06-01", tenant=cls.tenant)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_group_profile_endpoint(self):
        r = self.client.get(
            f"{PRODUCTS_URL}group-profile/?ids={self.p1.id},{self.p2.id}", **self.hdr)
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["name"] == "185/65/14"
        assert body["member_count"] == 2
        assert Decimal(body["quantity_on_hand"]) == Decimal("3")

    def test_group_profile_endpoint_excludes_a_foreign_tenants_id(self):
        other_owner = User.objects.create_user(username="bge2", password="x")
        other = create_company("شركة أخرى", other_owner)
        theirs = Product.objects.create(
            tenant=other, sku="X-1", name_ar="185/65/14", brand="ب")

        r = self.client.get(
            f"{PRODUCTS_URL}group-profile/?ids={self.p1.id},{self.p2.id},{theirs.id}",
            **self.hdr)
        assert r.status_code == 200, r.content
        assert r.json()["member_count"] == 2  # فقط منتجا شركتي — لا تسريب

    def test_brands_endpoint_lists_distinct(self):
        r = self.client.get(f"{PRODUCTS_URL}brands/", **self.hdr)
        assert r.status_code == 200, r.content
        assert r.json() == ["جلاكسي", "روك بيلد"]  # مميّزة ومرتّبة

    def test_groups_endpoint_lists_distinct(self):
        Product.objects.create(
            tenant=self.tenant, sku="GR-1", name_ar="ا", variant_group="انفيرتر 11")
        r = self.client.get(f"{PRODUCTS_URL}groups/", **self.hdr)
        assert r.status_code == 200, r.content
        assert r.json() == ["انفيرتر 11"]

    def test_names_endpoint_lists_distinct(self):
        r = self.client.get(f"{PRODUCTS_URL}names/", **self.hdr)
        assert r.status_code == 200, r.content
        assert r.json() == ["185/65/14"]

    def test_group_ledger_endpoint(self):
        r = self.client.get(
            f"{PRODUCTS_URL}group-ledger/?ids={self.p1.id},{self.p2.id}", **self.hdr)
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["count"] == 1
        assert body["results"][0]["product_name"] == "185/65/14 (روك بيلد)"

    # #23: كرت المنتج المفرد يفتح كرت إخوته بمعرّف الأب مباشرةً — لا حاجة
    # لتعداد براندات المنتج في الطلب.
    def test_group_profile_accepts_a_family_selector(self):
        from inventory.services import create_product_with_family, add_brand_to_family

        family, first = create_product_with_family(tenant=self.tenant, name_ar="لابتوب")
        first.brand = "ديل"
        first.save(update_fields=["brand"])
        add_brand_to_family(family=family, brand_name="اتش بي", tenant=self.tenant)

        r = self.client.get(f"{PRODUCTS_URL}group-profile/?family={family.id}", **self.hdr)
        assert r.status_code == 200, r.content
        assert r.json()["member_count"] == 2

    def test_group_profile_family_selector_excludes_a_foreign_tenants_family(self):
        other_owner = User.objects.create_user(username="bge3", password="x")
        other = create_company("شركة ثالثة", other_owner)
        from inventory.services import create_product_with_family
        theirs_family, _theirs = create_product_with_family(tenant=other, name_ar="طابعة")

        r = self.client.get(
            f"{PRODUCTS_URL}group-profile/?family={theirs_family.id}", **self.hdr)
        assert r.status_code == 200, r.content
        assert r.json()["member_count"] == 0  # أبٌ من شركةٍ أخرى — لا تسريب


class ParentStockStatusTest(APITestCase):
    """البند 3: الحالة من مجموع الأبناء مقابل حدّ الأب — لا رصيد براندٍ وحده."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="pss", password="x")
        cls.tenant = create_company("شركة حالة الأب", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _get(self, product_id):
        res = self.client.get(f"{PRODUCTS_URL}{product_id}/", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return res.json()

    def test_one_low_brand_inside_a_well_stocked_product_is_not_flagged_low(self):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "هاتف", "min_stock_level": 20},
            format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        low_brand = Product.objects.get(pk=res.json()["id"])
        low_brand.brand = "سامسونج"
        low_brand.save(update_fields=["brand"])

        add_res = self.client.post(
            f"{PRODUCTS_URL}add-brand/",
            {"family_id": low_brand.family_id, "brand": "آبل"},
            format="json", **self.hdr,
        )
        assert add_res.status_code == 201, add_res.content[:300]
        well_stocked_brand = Product.objects.get(pk=add_res.json()["id"])

        # البراند الأول رصيده 2 — تحت حدّ الـ20 لو حُسب وحده. الثاني 100.
        record_stock_movement(
            product=low_brand, movement_type="IN", quantity=Decimal("2"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)
        record_stock_movement(
            product=well_stocked_brand, movement_type="IN", quantity=Decimal("100"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)

        body = self._get(low_brand.id)
        assert body["stock_status"] == "in_stock", body  # 2+100=102 > 20

    def test_a_single_brand_product_below_its_own_min_is_still_flagged_low(self):
        """بلا إخوة، السلوك القديم يبقى كما هو — لا الحالة عمياء عن كل شيء."""
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "لابتوب", "min_stock_level": 20},
            format="json", **self.hdr,
        )
        product = Product.objects.get(pk=res.json()["id"])
        record_stock_movement(
            product=product, movement_type="IN", quantity=Decimal("2"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)

        body = self._get(product.id)
        assert body["stock_status"] == "low_stock", body


class FamilyAwareStockStatusFilterTest(APITestCase):
    """#28: فلتر `?stock_status=` يقيس حالة الأب لا البراند وحده — نفس ما
    تعرضه الشارة (#25). قبل هذا الإصلاح كان الفلتر يقرأ حدّ كل براندٍ على
    صفّه هو، فيناقض الشارة في الصفّ الواحد: يُفلتر المستخدم على «منخفض»
    فيعود صفٌّ شارتُه «متوفّر» — أو العكس، أبٌ منخفضٌ لا يظهر كل برانداته."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fasf", password="x")
        cls.tenant = create_company("شركة فلتر حالة الأب", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _filter(self, status, view=None):
        query = f"?stock_status={status}"
        if view:
            query += f"&view={view}"
        res = self.client.get(f"{PRODUCTS_URL}{query}", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return res.json()

    def _list(self):
        res = self.client.get(PRODUCTS_URL, **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return {row["sku"]: row for row in res.json()}

    def _add_brand(self, family_id, brand):
        res = self.client.post(
            f"{PRODUCTS_URL}add-brand/", {"family_id": family_id, "brand": brand},
            format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"])

    # 1) براندٌ منخفضٌ وحده (2 مقابل حدٍّ 20) داخل منتجٍ وفير (أخوه 100) —
    # الشارة تقول «متوفّر» (102 > 20)، فالفلتر يجب ألّا يُعيده تحت «منخفض».
    def test_filter_excludes_a_brand_low_alone_inside_an_abundant_family(self):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "غسّالة فائقة", "min_stock_level": 20},
            format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        low_brand = Product.objects.get(pk=res.json()["id"])
        low_brand.brand = "أ"
        low_brand.save(update_fields=["brand"])
        well_brand = self._add_brand(low_brand.family_id, "ب")

        record_stock_movement(
            product=low_brand, movement_type="IN", quantity=Decimal("2"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)
        record_stock_movement(
            product=well_brand, movement_type="IN", quantity=Decimal("100"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)

        rows = self._list()
        assert rows[low_brand.sku]["stock_status"] == "in_stock", rows[low_brand.sku]

        low_result_skus = {r["sku"] for r in self._filter("low_stock")}
        assert low_brand.sku not in low_result_skus, low_result_skus
        assert well_brand.sku not in low_result_skus, low_result_skus

    # 2) الأب منخفضٌ إجمالاً (0 + 10 مقابل حدٍّ 30) — يجب أن يظهر **كل**
    # برانداته تحت «منخفض»، حتى البراند برصيدٍ صفرٍ الذي وحده كان سيُصنَّف
    # «نافذ» لا «منخفض» — والفلتر القديم كان يفلتره خارج «منخفض» كليةً.
    def test_filter_includes_a_zero_stock_sibling_when_the_family_is_low(self):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "شاشة عرض", "min_stock_level": 30},
            format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        zero_brand = Product.objects.get(pk=res.json()["id"])
        zero_brand.brand = "أ"
        zero_brand.save(update_fields=["brand"])
        low_brand = self._add_brand(zero_brand.family_id, "ب")

        record_stock_movement(
            product=low_brand, movement_type="IN", quantity=Decimal("10"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)

        rows = self._list()
        assert rows[zero_brand.sku]["stock_status"] == "low_stock", rows[zero_brand.sku]
        assert rows[low_brand.sku]["stock_status"] == "low_stock", rows[low_brand.sku]

        low_result_skus = {r["sku"] for r in self._filter("low_stock")}
        assert {zero_brand.sku, low_brand.sku} <= low_result_skus, low_result_skus

    # #28: قرارٌ موثَّق لا سهوٌ — `view=lookup` يبقى برصيد البراند وحده، فالبراند
    # الصفري داخل منتجٍ وفير يبقى «نافذ» في المنتقي، ولو اختفى من جدول الأصناف.
    def test_lookup_view_still_judges_the_zero_brand_alone(self):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "طابعة حبر"}, format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        zero_brand = Product.objects.get(pk=res.json()["id"])
        zero_brand.brand = "أ"
        zero_brand.save(update_fields=["brand"])
        abundant_brand = self._add_brand(zero_brand.family_id, "ب")
        record_stock_movement(
            product=abundant_brand, movement_type="IN", quantity=Decimal("50"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)

        lookup_out = self._filter("out_of_stock", view="lookup")
        assert {r["sku"] for r in lookup_out} == {zero_brand.sku}, lookup_out

        table_out = {r["sku"] for r in self._filter("out_of_stock")}
        assert zero_brand.sku not in table_out, table_out  # الأب وفيرٌ إجمالاً

    # #28: الخدمة شارتُها «متوفّر» دائماً (بلا مخزونٍ يُقاس). ولها منذ #20 أبٌ
    # كسائر المنتجات، وأبوها بلا رصيد فحكمه «نفذ» — فلو قرأ الفلتر حكم الأب
    # وحده لسقطت كل خدمةٍ من «متوفّر» (أبٌ شاذّ) ومن «نفذ» (استثناء الخدمة)
    # معاً: بندٌ لا يظهر تحت أيّ حالة بينما شارته تقول «متوفّر».
    def test_service_stays_in_stock_in_the_filter_as_its_badge_says(self):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "خدمة تركيب", "is_service": True},
            format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        service = Product.objects.get(pk=res.json()["id"])
        assert service.family_id is not None  # الخدمة تأخذ أباً كسائر المنتجات

        rows = self._list()
        assert rows[service.sku]["stock_status"] == "in_stock", rows[service.sku]
        assert service.sku in {r["sku"] for r in self._filter("in_stock")}
        assert service.sku not in {r["sku"] for r in self._filter("out_of_stock")}


class ReplenishmentAlternativesAxisTest(APITestCase):
    """البند 4: محور «البدائل» يعطي عدداً حقيقياً لمنتجٍ متعدّد البراندات."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="repl", password="x")
        cls.tenant = create_company("شركة محور البدائل", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_alternatives_axis_counts_sibling_brands_with_stock(self):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "شاحن سريع"}, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        first = Product.objects.get(pk=res.json()["id"])
        first.brand = "أنكر"
        first.save(update_fields=["brand"])

        add_res = self.client.post(
            f"{PRODUCTS_URL}add-brand/",
            {"family_id": first.family_id, "brand": "بيلكن"},
            format="json", **self.hdr,
        )
        assert add_res.status_code == 201, add_res.content[:300]
        second = Product.objects.get(pk=add_res.json()["id"])

        for product in (first, second):
            record_stock_movement(
                product=product, movement_type="IN", quantity=Decimal("5"),
                unit_cost=Decimal("10"), movement_date="2026-05-01", tenant=self.tenant)

        report = self.client.get(
            "/api/reports/stock-replenishment/", **self.hdr)
        assert report.status_code == 200, report.content[:300]
        rows = {r["product_id"]: r for r in report.json()["rows"]}
        assert rows[first.id]["alternatives"] == 1  # البديل الوحيد: البراند الثاني
        assert rows[second.id]["alternatives"] == 1


class FamilyStockStatusQueryBudgetTest(APITestCase):
    """البند 5: مجموع الإخوة استعلامٌ واحدٌ للطلب — لا يكبر مع عدد الصفوف."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fsb", password="x")
        cls.tenant = create_company("شركة ميزانية استعلامات الأب", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _make_families(self, count):
        from inventory.services import create_product_with_family

        start = Product.objects.filter(tenant=self.tenant).count()
        for i in range(start, start + count):
            family, first = create_product_with_family(
                tenant=self.tenant, name_ar=f"منتج {i}", min_stock_level=5,
                sku=f"Q-{i}-1")
            first.brand = f"براند {i}-1"
            first.quantity_on_hand = Decimal("3")
            first.save(update_fields=["brand", "quantity_on_hand"])
            Product.objects.create(
                tenant=self.tenant, family=family, brand=f"براند {i}-2",
                sku=f"Q-{i}-2", quantity_on_hand=Decimal("20"))

    def test_family_available_map_is_one_query_regardless_of_row_count(self):
        from inventory.stock_status import family_available_map

        self._make_families(6)
        with self.assertNumQueries(1):
            family_available_map(self.tenant.TenantID)

    # #23: `has_group` تحتاج عدّ إخوة كل أبٍ — نفس شرط عدم النمو.
    def test_family_brand_counts_is_one_query_regardless_of_row_count(self):
        from inventory.services import family_brand_counts

        self._make_families(6)
        with self.assertNumQueries(1):
            family_brand_counts(self.tenant.TenantID)

    def test_products_list_query_count_does_not_grow_with_brand_rows(self):
        self._make_families(2)
        with CaptureQueriesContext(connection) as small:
            r1 = self.client.get(PRODUCTS_URL, **self.hdr)
        assert r1.status_code == 200, r1.content[:300]

        self._make_families(6)  # عائلاتٌ وبراندات أكثر بكثير في نفس الشركة
        with CaptureQueriesContext(connection) as large:
            r2 = self.client.get(PRODUCTS_URL, **self.hdr)
        assert r2.status_code == 200, r2.content[:300]

        assert len(r1.json()) == 4      # 2 عائلة × براندان
        assert len(r2.json()) == 16     # 8 عائلات (2+6) × براندان
        assert len(large) == len(small), (len(small), len(large))

    # #28: `family_status_map` استعلامان اثنان للشركة كلّها — لا يكبران مع
    # عدد الأبناء (`family_available_map` الواحد + استعلامٌ واحدٌ على الحدود).
    def test_family_status_map_is_two_queries_regardless_of_row_count(self):
        from inventory.stock_status import family_status_map

        self._make_families(6)
        with self.assertNumQueries(2):
            family_status_map(self.tenant.TenantID)

    # #28: فلتر `?stock_status=` يستخدم نفس الخريطة — عدد استعلاماته لا يكبر
    # مع عدد الصفوف/البراندات، تماماً كالقائمة بلا فلتر.
    def test_stock_status_filter_query_count_does_not_grow_with_brand_rows(self):
        self._make_families(2)
        with CaptureQueriesContext(connection) as small:
            r1 = self.client.get(f"{PRODUCTS_URL}?stock_status=low_stock", **self.hdr)
        assert r1.status_code == 200, r1.content[:300]

        self._make_families(6)
        with CaptureQueriesContext(connection) as large:
            r2 = self.client.get(f"{PRODUCTS_URL}?stock_status=low_stock", **self.hdr)
        assert r2.status_code == 200, r2.content[:300]

        # هذه العائلات وفيرةٌ (23 > 5) لا منخفضة — الفلتر يستبعدها كلّها بحقّ.
        assert r1.json() == []
        assert r2.json() == []
        assert len(large) == len(small), (len(small), len(large))

    # #35: الحدّان الحاكمان يُشتقّان من نفس استعلام `family_status_map` — لا
    # استعلامٌ ثالث. عدد الاستعلامات يبقى اثنين مهما كبر عدد العائلات.
    def test_family_status_and_thresholds_is_two_queries_regardless_of_row_count(self):
        from inventory.stock_status import family_status_and_thresholds

        self._make_families(6)
        with self.assertNumQueries(2):
            family_status_and_thresholds(self.tenant.TenantID)

    # #35: القائمة الكاملة (شارةٌ وحدٌّ حاكم معاً في كل صفّ) لا تدفع استعلاماً
    # إضافياً — ولا يكبر عددها مع عدد العائلات، تماماً كما قبل إضافة الحدّ.
    def test_products_list_query_count_stays_flat_with_effective_thresholds(self):
        self._make_families(2)
        with CaptureQueriesContext(connection) as small:
            r1 = self.client.get(PRODUCTS_URL, **self.hdr)
        assert r1.status_code == 200, r1.content[:300]

        self._make_families(6)
        with CaptureQueriesContext(connection) as large:
            r2 = self.client.get(PRODUCTS_URL, **self.hdr)
        assert r2.status_code == 200, r2.content[:300]

        assert all("effective_min_stock_level" in row for row in r1.json())
        assert all("effective_max_stock_level" in row for row in r2.json())
        assert len(large) == len(small), (len(small), len(large))


class FamilyGoverningThresholdTest(APITestCase):
    """#35: الرقم المعروض على صفّ المنتج (`effective_min/max_stock_level`)
    يطابق الحدّ الذي حَكَم على شارة الصفّ نفسه — لا حدّ البراند المرجعي الخام
    إن اختلف بعد ضمٍّ لا يُسوّي حدود إخوته (`merge_products` لا يمسّ
    `min_stock_level`/`max_stock_level` أصلاً، #24)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fgt", password="x")
        cls.tenant = create_company("شركة الحدّ الحاكم", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _get(self, product_id):
        res = self.client.get(f"{PRODUCTS_URL}{product_id}/", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        return res.json()

    def _diverge(self, *, field, anchor_value, sibling_value, family_value):
        """عائلةٌ بأخوين مختلفَي الحدّ، والأب على قيمةٍ ثالثة — يحاكي أثر ضمٍّ
        (#24) لا يُسوّي حدود إخوته: `merge_products` يُعيد ربط `family_id`
        وحده، فيبقى كل براندٍ على حدّه القديم بينما الأب يحمل حدّاً ثالثاً."""
        from inventory.services import create_product_with_family

        family, anchor = create_product_with_family(
            tenant=self.tenant, name_ar="منتج", sku="ANCHOR-1", **{field: anchor_value},
        )
        Product.objects.create(
            tenant=self.tenant, family=family, brand="ب٢", sku="SIB-1",
            **{field: sibling_value},
        )
        # المرجعي (أصغر معرّف) ليس آخر من حُرِّر — الأب على قيمةٍ ثالثة.
        ProductFamily.objects.filter(pk=family.pk).update(**{field: family_value})
        return anchor

    def test_min_stock_level_row_shows_family_threshold_and_it_matches_the_badge(self):
        anchor = self._diverge(
            field="min_stock_level", anchor_value=10, sibling_value=30, family_value=99,
        )
        record_stock_movement(
            product=anchor, movement_type="IN", quantity=Decimal("50"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)

        body = self._get(anchor.id)
        # لو حُكمت الشارة بحدّ المرجعي الخام (10) لكانت «متوفّر» (50 > 10)؛
        # حدّ الأب (99) يخفضها إلى «منخفض» (50 ≤ 99) — وهذا ما حُوكِمت به فعلاً.
        assert body["stock_status"] == "low_stock", body
        # والرقم المعروض هو نفسه الرقم الذي حكم — لا رقم المرجعي المجاور.
        assert body["effective_min_stock_level"] == 99, body
        assert body["min_stock_level"] == 10  # الحقل الخام لم يُمسّ — الكتابة لا تتغيّر

    def test_max_stock_level_row_shows_family_threshold_and_it_matches_the_badge(self):
        anchor = self._diverge(
            field="max_stock_level", anchor_value=200, sibling_value=10, family_value=40,
        )
        record_stock_movement(
            product=anchor, movement_type="IN", quantity=Decimal("60"),
            unit_cost=Decimal("10"), movement_date="2026-06-01", tenant=self.tenant)

        body = self._get(anchor.id)
        # لو حُكمت الشارة بحدّ المرجعي الخام (200) لبقيت «متوفّر» (60 ≤ 200)؛
        # حدّ الأب (40) يرفعها إلى «فائض» (60 > 40) — وهذا ما حُوكِمت به فعلاً.
        assert body["stock_status"] == "overstock", body
        assert body["effective_max_stock_level"] == 40, body
        assert body["max_stock_level"] == 200  # الحقل الخام لم يُمسّ

    def test_product_without_family_shows_its_own_threshold_unchanged(self):
        product = Product.objects.create(
            tenant=self.tenant, sku="ORPHAN-1", name_ar="بلا أب",
            min_stock_level=15, max_stock_level=25,
        )
        body = self._get(product.id)
        assert body["effective_min_stock_level"] == 15, body
        assert body["effective_max_stock_level"] == 25, body
        assert body["min_stock_level"] == 15
        assert body["max_stock_level"] == 25

    def test_patching_min_max_still_writes_the_brand_row_and_mirrors_up_to_family(self):
        """البند 6: الكتابة لا تتغيّر — التعديل يبقى على صفّ البراند ويصعد
        إلى الأب، والحقلان الكاتبان يعودان في الاستجابة كما أُرسلا رغم
        إضافة `effective_*` القرائيَّين بجانبهما."""
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": "جهاز", "min_stock_level": 5, "max_stock_level": 50},
            format="json", **self.hdr,
        )
        assert res.status_code == 201, res.content[:300]
        product = Product.objects.get(pk=res.json()["id"])

        patch = self.client.patch(
            f"{PRODUCTS_URL}{product.id}/",
            {"min_stock_level": 12, "max_stock_level": 60},
            format="json", **self.hdr,
        )
        assert patch.status_code == 200, patch.content[:300]
        body = patch.json()
        # الحقلان الكاتبان يعودان كما أُرسلا — لا يبتلعهما الحقل الجديد القرائي.
        assert body["min_stock_level"] == 12
        assert body["max_stock_level"] == 60
        # ويصعدان إلى الأب كما اليوم (#20) — مصدر `effective_*` نفسه.
        product.refresh_from_db()
        family = product.family
        assert family.min_stock_level == 12
        assert family.max_stock_level == 60
        assert body["effective_min_stock_level"] == 12
        assert body["effective_max_stock_level"] == 60
