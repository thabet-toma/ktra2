"""#24: الضمّ الجماعي — منتجات قائمة (براندات منتجٍ واحد فعلياً) تحت أبٍ واحد.

الخطّ الأحمر (#13): **بلا حركة مخزون ولا قيد محاسبي إطلاقاً** — كل براند
يحتفظ برصيده وتكلفته وحركاته كما هي، ويُثبَت بمقارنة عدد الصفوف قبل/بعد لا
بتخمين. والمحدِّد في جسم الطلب لا في عنوانه (نفس درس كرت المجموعة، #22).
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import JournalHeader
from inventory.models import Product, ProductCategory, ProductFamily, ProductMerge, StockMovement, UnitOfMeasure
from inventory.services import merge_products, undo_product_merge
from tenants.services import create_company

MERGE_URL = "/api/inventory/products/merge/"
UNDO_URL = "/api/inventory/products/merge-undo/"

# أكبر من عدد منتجات «منتجات عامة» في شركة الجرابعه (1490) التي كسرت الإنتاج.
MANY = 1500


class ProductMergeTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="merge_owner", password="x")
        cls.tenant = create_company("شركة الضمّ", cls.owner)
        cls.uom_piece = UnitOfMeasure.objects.create(code="PC-MRG", name_ar="قطعة", name_en="Piece")
        cls.uom_box = UnitOfMeasure.objects.create(code="BX-MRG", name_ar="صندوق", name_en="Box")

        cls.other_owner = User.objects.create_user(username="merge_other", password="x")
        cls.other_tenant = create_company("شركة أخرى (ضمّ)", cls.other_owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.tenant_id = str(self.tenant.TenantID)

    def _post(self, url, payload, tenant_id=None):
        return self.client.post(
            url, payload, format="json", HTTP_X_TENANT_ID=tenant_id or self.tenant_id,
        )

    def _make_standalone(self, tenant, *, name, uom=None, is_serialized=False, category=None,
                          quantity=Decimal("0"), avg_cost=Decimal("0")):
        """منتجٌ قائم ببراندٍ ضمنيّ واحد — أبٌ خاصٌّ به وحده، مثل ما تُنشئه
        `create_product_with_family` فعلاً (#20)."""
        family = ProductFamily.objects.create(
            tenant=tenant, name_ar=name, uom=uom or self.uom_piece, is_serialized=is_serialized,
            category=category,
        )
        return Product.objects.create(
            tenant=tenant, sku=f"SKU-{ProductFamily.objects.count()}-{name}", name_ar=name,
            family=family, uom=uom or self.uom_piece, is_serialized=is_serialized,
            category=category, quantity_on_hand=quantity, avg_cost=avg_cost,
        )

    # ── 1) ضمٌّ جماعي: أبٌ واحد، وكل براندٍ يحتفظ برصيده وتكلفته وحركاته ──
    def test_merge_puts_products_under_one_parent_keeping_balances(self):
        target = self._make_standalone(
            self.tenant, name="195/85/15 دانتير", quantity=Decimal("10"), avg_cost=Decimal("100"))
        sibling = self._make_standalone(
            self.tenant, name="195/85/15 أوتولوكس", quantity=Decimal("4"), avg_cost=Decimal("80"))
        StockMovement.objects.create(
            tenant=self.tenant, product=sibling, movement_type="IN", quantity=Decimal("4"),
            unit_cost=Decimal("80"), total_cost=Decimal("320"), movement_date=datetime.date.today(),
        )

        res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [sibling.id],
        })
        self.assertEqual(res.status_code, 200, res.content[:300])
        data = res.json()
        self.assertEqual(data["merged_product_ids"], [sibling.id])
        self.assertIn("merge_id", data)

        sibling.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(sibling.family_id, target.family_id)
        # الرصيد والتكلفة والحركات بقيت كما هي — بلا نقلٍ ولا إعادة توزيع.
        self.assertEqual(sibling.quantity_on_hand, Decimal("4"))
        self.assertEqual(sibling.avg_cost, Decimal("80"))
        self.assertEqual(target.quantity_on_hand, Decimal("10"))
        self.assertEqual(target.avg_cost, Decimal("100"))
        self.assertEqual(
            StockMovement.objects.filter(product=sibling).count(), 1)

    # ── 2) بلا حركة مخزون وبلا قيد محاسبي — عدّاً لا تخميناً ──
    def test_merge_creates_zero_stock_movements_and_zero_journal_rows(self):
        target = self._make_standalone(self.tenant, name="هاتف A", quantity=Decimal("5"))
        sibling = self._make_standalone(self.tenant, name="هاتف B", quantity=Decimal("7"))
        StockMovement.objects.create(
            tenant=self.tenant, product=target, movement_type="IN", quantity=Decimal("5"),
            unit_cost=Decimal("10"), total_cost=Decimal("50"), movement_date=datetime.date.today(),
        )

        movements_before = StockMovement.objects.filter(tenant=self.tenant).count()
        journals_before = JournalHeader.objects.filter(tenant=self.tenant).count()

        res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [sibling.id],
        })
        self.assertEqual(res.status_code, 200, res.content[:300])

        self.assertEqual(
            StockMovement.objects.filter(tenant=self.tenant).count(), movements_before)
        self.assertEqual(
            JournalHeader.objects.filter(tenant=self.tenant).count(), journals_before)

    # ── 3) التراجع يعيد الحالة السابقة كاملةً بلا أثر ──
    def test_undo_restores_previous_state_completely(self):
        target = self._make_standalone(self.tenant, name="اسم الهدف")
        sibling = self._make_standalone(self.tenant, name="اسم قديم")
        original_family_id = sibling.family_id
        original_name = sibling.name_ar
        original_brand = sibling.brand

        merge_res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [sibling.id],
            "brands": {str(sibling.id): "أوتولوكس"},
        })
        self.assertEqual(merge_res.status_code, 200, merge_res.content[:300])
        merge_id = merge_res.json()["merge_id"]

        sibling.refresh_from_db()
        self.assertEqual(sibling.family_id, target.family_id)
        self.assertEqual(sibling.name_ar, "اسم الهدف")
        self.assertEqual(sibling.brand, "أوتولوكس")

        undo_res = self._post(UNDO_URL, {"merge_id": merge_id})
        self.assertEqual(undo_res.status_code, 200, undo_res.content[:300])
        self.assertEqual(undo_res.json()["restored_product_ids"], [sibling.id])

        sibling.refresh_from_db()
        self.assertEqual(sibling.family_id, original_family_id)
        self.assertEqual(sibling.name_ar, original_name)
        self.assertEqual(sibling.brand, original_brand)

        # التراجع لا يُقبل ثانيةً على نفس السجلّ (بلا أثرٍ متكرّر).
        repeat = self._post(UNDO_URL, {"merge_id": merge_id})
        self.assertEqual(repeat.status_code, 400)
        self.assertEqual(ProductMerge.objects.get(pk=merge_id).undone_at is not None, True)

    # ── 3ب) الهدف براندٌ كباقي البراندات — دلتا ٢: الاسم يتوحّد فيبقى البراند
    # وحده يميّز الصفوف في المنتقي؛ التراجع يعيد براند الهدف أيضاً لا الإخوة وحدهم.
    def test_brands_supplied_for_target_and_sibling_are_applied_and_undone(self):
        target = self._make_standalone(self.tenant, name="195/85/15")
        sibling = self._make_standalone(self.tenant, name="195/85/15 قديم")
        original_target_brand = target.brand
        original_sibling_brand = sibling.brand
        original_target_family_id = target.family_id

        res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [sibling.id],
            "brands": {str(target.id): "دانتير", str(sibling.id): "أوتولوكس"},
        })
        self.assertEqual(res.status_code, 200, res.content[:300])
        merge_id = res.json()["merge_id"]
        # الهدف لم يُنقل (لم يتغيّر أبوه) فلا يظهر في «المنقولين» — فرقٌ في
        # الدلالة عن التغيير الفعلي على براندِه.
        self.assertEqual(res.json()["merged_product_ids"], [sibling.id])

        target.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(target.brand, "دانتير")
        self.assertEqual(sibling.brand, "أوتولوكس")
        # الاسمان توحّدا (التطبيع)، والبراندان يفرّقان الصفّين في المنتقي.
        self.assertEqual(target.name_ar, sibling.name_ar)
        self.assertNotEqual(target.brand, sibling.brand)

        undo_res = self._post(UNDO_URL, {"merge_id": merge_id})
        self.assertEqual(undo_res.status_code, 200, undo_res.content[:300])
        # الهدف يعود ضمن المُستعادين أيضاً — لا الإخوة المنقولون وحدهم.
        self.assertCountEqual(undo_res.json()["restored_product_ids"], [target.id, sibling.id])

        target.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(target.brand, original_target_brand)
        self.assertEqual(sibling.brand, original_sibling_brand)
        self.assertEqual(target.family_id, original_target_family_id)

    # ── 4) محدِّدٌ في الجسم بعدد يفوق ما كسر الإنتاج (>=1500) ──
    def test_body_selector_accepts_at_least_1500_ids_and_url_stays_short(self):
        target = self._make_standalone(self.tenant, name="منتج جامع كبير")
        # معرّفات من ستّ خانات كما في قاعدة الإنتاج (نفس اصطلاح كرت المجموعة،
        # #22) — طول العنوان هو موضوع الاختبار، وترقيمُ قاعدةٍ فارغة يجعله أقصر.
        base = 200000
        ProductFamily.objects.bulk_create([
            ProductFamily(
                id=base + i, tenant=self.tenant, name_ar=f"براند {i}",
                uom=self.uom_piece, is_serialized=False)
            for i in range(MANY - 1)
        ])
        Product.objects.bulk_create([
            Product(
                id=base + i, tenant=self.tenant, sku=f"MRG-{i}", name_ar=f"براند {i}",
                family_id=base + i, uom=self.uom_piece, is_serialized=False)
            for i in range(MANY - 1)
        ])
        ids = [base + i for i in range(MANY - 1)]
        self.assertGreater(len(",".join(str(i) for i in ids)), 8 * 1024)

        res = self._post(MERGE_URL, {"target_product_id": target.id, "product_ids": ids})
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(len(res.json()["merged_product_ids"]), MANY - 1)
        self.assertLess(len(MERGE_URL), 100)

        self.assertEqual(
            Product.objects.filter(tenant=self.tenant, family_id=target.family_id).count(),
            MANY,
        )

    # ── 5) يُمنع عند اختلاف الوحدة أو التتبّع التسلسلي — وهذان فقط ──
    def test_merge_blocked_on_differing_unit_of_measure(self):
        target = self._make_standalone(self.tenant, name="هدف الوحدة", uom=self.uom_piece)
        mismatched = self._make_standalone(self.tenant, name="وحدة مختلفة", uom=self.uom_box)

        res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [mismatched.id],
        })
        self.assertEqual(res.status_code, 400, res.content[:300])
        mismatched.refresh_from_db()
        self.assertNotEqual(mismatched.family_id, target.family_id)

    def test_merge_blocked_on_differing_serial_tracking(self):
        target = self._make_standalone(self.tenant, name="هدف التسلسلي", is_serialized=False)
        mismatched = self._make_standalone(self.tenant, name="تسلسلي مختلف", is_serialized=True)

        res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [mismatched.id],
        })
        self.assertEqual(res.status_code, 400, res.content[:300])
        mismatched.refresh_from_db()
        self.assertNotEqual(mismatched.family_id, target.family_id)

    def test_merge_allowed_despite_differing_category(self):
        """التصنيف حقلٌ أبويّ يُسمَح باختلافه ويُتبنّى ما على الهدف (#13) —
        لا مانعٌ مخترَع خارج الوحدة والتتبّع التسلسلي."""
        cat_a = ProductCategory.objects.create(tenant=self.tenant, name="تصنيف أ")
        cat_b = ProductCategory.objects.create(tenant=self.tenant, name="تصنيف ب")
        target = self._make_standalone(self.tenant, name="هدف التصنيف", category=cat_a)
        other = self._make_standalone(self.tenant, name="تصنيف مختلف", category=cat_b)

        res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [other.id],
        })
        self.assertEqual(res.status_code, 200, res.content[:300])
        other.refresh_from_db()
        self.assertEqual(other.family_id, target.family_id)

    # ── 6) عزل الشركات: لا يجوز أن يمتدّ الضمّ إلى شركةٍ أخرى ──
    def test_merge_cannot_pull_in_a_foreign_company_product(self):
        target = self._make_standalone(self.tenant, name="هدف محلي")
        foreign = self._make_standalone(self.other_tenant, name="منتج شركة أخرى")
        foreign_family_id = foreign.family_id

        res = self._post(MERGE_URL, {
            "target_product_id": target.id, "product_ids": [foreign.id],
        })
        # لا شيء لهذه الشركة سوى الهدف نفسه — المعرّف الأجنبي يُتجاهل بصمت.
        self.assertEqual(res.status_code, 400, res.content[:300])

        foreign.refresh_from_db()
        self.assertEqual(foreign.family_id, foreign_family_id)
        self.assertEqual(foreign.tenant_id, self.other_tenant.pk)

    def test_merge_cannot_use_a_foreign_target(self):
        foreign_target = self._make_standalone(self.other_tenant, name="هدف أجنبي")
        local = self._make_standalone(self.tenant, name="منتج محلي")

        res = self._post(MERGE_URL, {
            "target_product_id": foreign_target.id, "product_ids": [local.id],
        })
        self.assertEqual(res.status_code, 400, res.content[:300])
        local.refresh_from_db()
        self.assertNotEqual(local.family_id, foreign_target.family_id)


class OrphanFamilyIsHiddenAfterMergeTest(APITestCase):
    """الأب الذي فقد برانداته بالضمّ يبقى في القاعدة للتراجع ولا يراه أحد."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="merge_orphan", password="x")
        cls.tenant = create_company("شركة الأب اليتيم", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, name):
        res = self.client.post(
            "/api/inventory/products/", {"name_ar": name}, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"])

    def test_merged_away_parent_disappears_from_reads_but_undo_still_works(self):
        from inventory.models import ProductFamily

        keep = self._create("منتج باقٍ")
        gone = self._create("منتج مضموم")
        orphan_family_id = gone.family_id

        res = self.client.post(
            "/api/inventory/products/merge/",
            {"target_product_id": keep.id, "product_ids": [gone.id]},
            format="json", **self.hdr,
        )
        assert res.status_code in (200, 201), res.content[:300]

        # باقٍ في القاعدة — سجلّ التراجع يشير إليه.
        assert ProductFamily.objects.filter(pk=orphan_family_id).exists()

        # ولا يظهر في القراءة: لا في القائمة ولا في اقتراح «هذا موجود».
        listed = self.client.get("/api/inventory/product-families/", **self.hdr).json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        assert orphan_family_id not in {r["id"] for r in rows}

        offer = self.client.get(
            "/api/inventory/product-families/check-name/?name=منتج مضموم", **self.hdr,
        )
        assert offer.status_code == 200, offer.content[:300]
        match = offer.json()["match"]
        assert match is None or match["id"] != orphan_family_id


class LegacyCatalogueMergeTest(APITestCase):
    """#24-دلتا ٣: الكتالوج القديم — كل صفوفه بلا أب — هو ما بُنيت له الأداة.

    قبل هذا كانت `merge_products` تشترط أباً للهدف سلفاً، فترفض كل ضمٍّ على
    بياناتٍ حقيقية برسالة «بلا منتجٍ أبٍ فوقه»: أداةُ التنظيف عاجزةٌ عن لمس ما
    بُنيت لتنظيفه.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="legacy-merge", password="x")
        self.tenant = create_company("شركة الكتالوج القديم", self.user)
        self.a = Product.objects.create(
            tenant=self.tenant, sku="OLD-A", name_ar="215/75/15 دانتير",
            quantity_on_hand=Decimal("10"), avg_cost=Decimal("100"))
        self.b = Product.objects.create(
            tenant=self.tenant, sku="OLD-B", name_ar="215/75/15 روك بيلد",
            quantity_on_hand=Decimal("4"), avg_cost=Decimal("120"))

    def test_two_products_with_no_parent_at_all_can_be_merged(self):
        self.assertIsNone(self.a.family_id)
        self.assertIsNone(self.b.family_id)

        merge, moved = merge_products(
            tenant=self.tenant, target_product_id=self.a.id,
            product_ids=[self.b.id], user=self.user,
        )

        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertIsNotNone(self.a.family_id)
        self.assertEqual(self.b.family_id, self.a.family_id)
        self.assertEqual([p.id for p in moved], [self.b.id])
        # الأرقام لم تُمَسّ: الأب لا يحمل رقماً، والرصيد والتكلفة على البراند.
        self.assertEqual(self.a.quantity_on_hand, Decimal("10"))
        self.assertEqual(self.b.quantity_on_hand, Decimal("4"))
        self.assertEqual(self.b.avg_cost, Decimal("120"))

    def test_undo_returns_the_target_to_having_no_parent_at_all(self):
        """التراجع بلا أثر يشمل الأب الذي اكتسبه الهدف للتوّ — وإلا بقي تحت
        أبٍ لم يكن له قبل الضمّ."""
        merge, _ = merge_products(
            tenant=self.tenant, target_product_id=self.a.id,
            product_ids=[self.b.id], user=self.user,
        )
        undo_product_merge(tenant=self.tenant, merge_id=merge.id)

        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertIsNone(self.a.family_id)
        self.assertIsNone(self.b.family_id)
