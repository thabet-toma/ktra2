"""task14 M2 (DEF-A2/A3/A4/A5) — Product API:
توليد SKU خادمي، الاسم فقط إلزامي، أخطاء بحقلها الصحيح،
ترتيب حتمي + بحث + فلتر فترة + ترقيم صفحات opt-in، وعزل الشركات.
"""
import datetime
from decimal import Decimal

from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from core.models import ActivityLog
from inventory.models import Product, ProductCategory, ProductFamily, StockMovement, UnitOfMeasure
from inventory.services import add_brand_to_family, create_product_with_family
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class ProductApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="items_a", password="x")
        cls.owner_b = User.objects.create_user(username="items_b", password="x")
        cls.t_a = create_company("شركة المنتجات أ", cls.owner_a)
        cls.t_b = create_company("شركة المنتجات ب", cls.owner_b)

    def _auth(self, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.owner_a)
        self._tenant_id = str((tenant or self.t_a).TenantID)

    def _post(self, payload):
        return self.client.post(PRODUCTS_URL, payload, format="json",
                                HTTP_X_TENANT_ID=self._tenant_id)

    def _get(self, query=""):
        return self.client.get(PRODUCTS_URL + query, HTTP_X_TENANT_ID=self._tenant_id)

    # ── DEF-A2: الاسم فقط إلزامي + SKU خادمي ──
    def test_create_with_name_only_generates_sku(self):
        self._auth()
        res = self._post({"name_ar": "منتج بالاسم فقط"})
        assert res.status_code == 201, res.content[:300]
        data = res.json()
        assert data["sku"] == "000001"
        assert data["created_at"]

        activity = ActivityLog.objects.get(
            tenant=self.t_a, entity_type="product", entity_id=data["id"], action="create",
        )
        assert activity.user_id == self.owner_a.id
        assert activity.entity_label == "منتج بالاسم فقط"
        assert activity.description == "أضاف المنتج «منتج بالاسم فقط»"

    def test_sku_sequence_increments_and_ignores_legacy_fb(self):
        self._auth()
        Product.objects.create(tenant=self.t_a, sku="FB-d5cc09e9-7cb0", name_ar="مهاجر قديم")
        first = self._post({"name_ar": "أول"}).json()
        second = self._post({"name_en": "second"}).json()
        assert first["sku"] == "000001"
        assert second["sku"] == "000002"

    def test_sku_sequence_is_per_tenant(self):
        self._auth()
        assert self._post({"name_ar": "أ-1"}).json()["sku"] == "000001"
        self._auth(user=self.owner_b, tenant=self.t_b)
        assert self._post({"name_ar": "ب-1"}).json()["sku"] == "000001"

    # ── DEF-A3: أخطاء دقيقة بحقلها ──
    def test_missing_name_yields_field_specific_error(self):
        self._auth()
        res = self._post({"sku": "X-1"})
        assert res.status_code == 400
        body = res.json()
        payload = body.get("error", {}).get("details", body)
        assert "name_ar" in str(payload)
        assert "اسم المنتج مطلوب" in str(payload)

    def test_duplicate_explicit_sku_yields_sku_field_error(self):
        self._auth()
        assert self._post({"name_ar": "الأصل", "sku": "DUP-1"}).status_code == 201
        res = self._post({"name_ar": "المكرر", "sku": "DUP-1"})
        assert res.status_code == 400
        assert "sku" in str(res.json())

    def test_cross_tenant_category_rejected(self):
        self._auth()
        foreign_cat = ProductCategory.objects.create(tenant=self.t_b, name="تصنيف الشركة الأخرى")
        res = self._post({"name_ar": "منتج", "category": foreign_cat.id})
        assert res.status_code == 400
        assert "category" in str(res.json())

    # ── DEF-A5: ترتيب حتمي + بحث + فترة + ترقيم opt-in ──
    def test_default_ordering_is_newest_first(self):
        self._auth()
        self._post({"name_ar": "الأقدم"})
        self._post({"name_ar": "الأحدث"})
        rows = self._get().json()
        assert isinstance(rows, list)
        assert rows[0]["name_ar"] == "الأحدث"
        assert rows[0]["id"] > rows[1]["id"]

    def test_search_filters_by_name_and_sku(self):
        self._auth()
        self._post({"name_ar": "مكيف سبليت"})
        self._post({"name_ar": "ثلاجة", "sku": "FRIDGE-9"})
        by_name = self._get("?search=سبليت").json()
        assert len(by_name) == 1 and by_name[0]["name_ar"] == "مكيف سبليت"
        by_sku = self._get("?search=FRIDGE").json()
        assert len(by_sku) == 1 and by_sku[0]["name_ar"] == "ثلاجة"

    def test_created_period_filter(self):
        self._auth()
        self._post({"name_ar": "اليوم"})
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        assert self._get(f"?created_from={tomorrow}").json() == []
        assert len(self._get(f"?created_to={tomorrow}").json()) == 1

    def test_pagination_is_opt_in(self):
        self._auth()
        for i in range(3):
            self._post({"name_ar": f"منتج {i}"})
        plain = self._get().json()
        assert isinstance(plain, list) and len(plain) == 3
        paged = self._get("?page=1&page_size=2").json()
        assert paged["count"] == 3
        assert len(paged["results"]) == 2

    def test_read_isolation_unchanged(self):
        self._auth()
        self._post({"name_ar": "سري لشركة أ"})
        self._auth(user=self.owner_b, tenant=self.t_b)
        assert self._get().json() == []

    def test_lookup_list_batches_attachments_and_skips_analytics(self):
        Product.objects.bulk_create([
            Product(tenant=self.t_a, sku=f"LOOK-{i}", name_ar=f"محدد {i}")
            for i in range(3)
        ])
        self._auth()

        with patch("core.models.SystemAttachment") as MockAttachment:
            MockAttachment.objects.filter.return_value = []
            res = self._get("?view=lookup")

        assert res.status_code == 200, res.content[:300]
        assert len(res.json()) == 3
        assert MockAttachment.objects.filter.call_count == 1
        assert all("purchased_qty" not in row for row in res.json())
        assert all({
            "id", "sku", "name_ar", "name_en", "display_name",
            "category", "hs_code", "min_stock_level", "quantity_on_hand",
            "avg_cost", "is_for_sale_online", "online_price",
            "online_description", "attachments",
        }.issubset(row) for row in res.json())

    def test_lookup_list_carries_every_field_the_invoice_picker_reads(self):
        """منتقي المنتج في الفواتير يحتاج الباركود وسعر البيع وعلَم الخدمة.

        بدونها كانت شاشات البيع تجلب العقد **الكامل** لكل المنتجات: قياس على
        بيانات حقيقية (1490 منتجاً) أعطى 1,145 كيلوبايت و1,249 ملّي ثانية عند
        كل فتح للشاشة، مقابل عقد المنتقي 609 كيلوبايت و331 ملّي ثانية.
        """
        Product.objects.create(
            tenant=self.t_a, sku="PICK-1", name_ar="منتج المنتقي",
            barcode="6291001", sale_price="12.50", is_service=False,
        )
        self._auth()

        res = self._get("?view=lookup")

        assert res.status_code == 200, res.content[:300]
        row = next(r for r in res.json() if r["sku"] == "PICK-1")
        assert row["barcode"] == "6291001"
        assert Decimal(row["sale_price"]) == Decimal("12.50")
        assert row["is_service"] is False
        # T-REORDER: شارة «نفذ/منخفض» في بند الفاتورة وشريط «بدائل من نفس النوع»
        # يقرآن هذين الحقلين. مكوّنٌ يقرأ حقلاً لا يرسله العقد يعرض فراغاً بصمت،
        # و`tsc` لا يكشفه (لا `@types/react` فلا فحص لخصائص JSX) — فالحارس هنا.
        assert row["stock_status"] == "out_of_stock"   # بلا رصيد ⇒ نفذ ولو بلا حدّ أدنى
        assert row["group_key"] == "منتج المنتقي"       # بلا مجموعة صريحة ⇒ الاسم
        # وما زال العقد أضيق من الكامل — لا تحليلات ولا حقول الكرت.
        assert "purchased_qty" not in row
        assert "avg_monthly_sales" not in row

    # ── #22: منتقي المنتجات في المستندات ──
    def test_lookup_contract_gains_exactly_family_id_and_family_name(self):
        """العقد يكسب حقلين فقط — لا يتوسّع أكثر (قرارٌ صريح على #12).

        `category` تُضبَط عمداً لأن `category_name` (`source='category.name'`)
        تُسقَط من الردّ حين تكون فارغة — لا حقلٌ ناقص، بل `SkipField` على
        سلسلة مصدرٍ منقّطة تشير إلى `None`؛ ضبطها هنا يجعل مجموعة الحقول
        المرجعية دقيقةً بدل أن تكذب بحسب بيانات الاختبار.
        """
        category = ProductCategory.objects.create(tenant=self.t_a, name="تصنيف")
        family, product = create_product_with_family(
            tenant=self.t_a, name_ar="منتج بأب", category=category)
        self._auth()

        res = self._get("?view=lookup")

        assert res.status_code == 200, res.content[:300]
        row = next(r for r in res.json() if r["id"] == product.id)
        assert row["family_id"] == family.id
        assert row["family_name"] == "منتج بأب"
        known_before = {
            "id", "sku", "barcode", "name_ar", "name_en", "display_name", "brand",
            "category", "category_name", "hs_code", "min_stock_level",
            "stock_status", "group_key", "quantity_on_hand", "reserved_quantity",
            "available_quantity", "avg_cost", "sale_price", "is_service",
            "is_serialized", "warranty_months", "supplier_warranty_months",
            "is_for_sale_online", "online_price", "online_description",
            "attachments", "supplier_codes_text",
        }
        assert set(row.keys()) == known_before | {"family_id", "family_name"}

    def test_lookup_list_exposes_every_brand_of_a_family_each_with_the_brand_in_its_name(self):
        """كتابة اسم المنتج تُنزل كل برانداته — كلٌّ بصيغة «اسم المنتج (البراند)».

        الأساس البنيوي: كل براندٍ تحت نفس الأب يشارك `name_ar` نفسه (مزامنة
        `sync_family_from_product`)، فبحثٌ نصّي موضعي عن اسم المنتج في الواجهة
        يطابق الجميع تلقائياً بلا أي منطق بحثٍ إضافي.
        """
        family, first = create_product_with_family(tenant=self.t_a, name_ar="هاتف ذكي")
        add_brand_to_family(family=family, brand_name="سامسونج", tenant=self.t_a)
        second, _created = add_brand_to_family(family=family, brand_name="آبل", tenant=self.t_a)
        self._auth()

        res = self._get("?view=lookup")

        assert res.status_code == 200, res.content[:300]
        rows = [r for r in res.json() if r["family_id"] == family.id]
        assert len(rows) == 2
        assert {r["name_ar"] for r in rows} == {"هاتف ذكي"}
        assert {r["display_name"] for r in rows} == {
            "هاتف ذكي (سامسونج)", "هاتف ذكي (آبل)",
        }

    def test_lookup_list_never_returns_a_family_row(self):
        """المنتج (الأب) غير قابل للاختيار في بندٍ بنيويّاً — لا يظهر أصلاً في
        عقد المنتقي، الذي يُبنى فوق `Product` (البراند) لا `ProductFamily`."""
        family, product = create_product_with_family(tenant=self.t_a, name_ar="منتج مُفرد")
        self._auth()

        res = self._get("?view=lookup")

        assert res.status_code == 200, res.content[:300]
        rows = res.json()
        assert all("brands" not in r for r in rows)
        row_ids = {r["id"] for r in rows}
        assert product.id in row_ids
        # عقد المنتقي أصلاً لا مسار له إلى `ProductFamily` — التحقّق الإيجابي
        # هنا أن كل صفٍّ عائدٍ هو براندٌ حقيقي موجود في جدول `Product`.
        assert row_ids == set(
            Product.objects.filter(tenant=self.t_a).values_list("id", flat=True)
        )
        assert ProductFamily.objects.filter(tenant=self.t_a).count() >= 1

    def test_lookup_family_name_does_not_add_a_query_per_row(self):
        """`family_name` يُقرأ من `select_related('family')` — عقد المنتقي
        مقيسٌ صراحةً (609ك/331مِلّي على 1490 منتجاً)، فحقلٌ يفتح استعلاماً لكل
        صفٍّ يُعيد بالضبط ما بُني هذا العقد الضيّق ليمنعه."""
        for i in range(10):
            create_product_with_family(tenant=self.t_a, name_ar=f"منتج {i}", sku=f"FAMQ-{i}")
        self._auth()

        with CaptureQueriesContext(connection) as captured:
            res = self._get("?view=lookup")

        assert res.status_code == 200, res.content[:300]
        assert len(res.json()) == 10
        assert len(captured) <= 6, [q["sql"] for q in captured]

    def test_category_tree_query_count_is_constant(self):
        root = ProductCategory.objects.create(tenant=self.t_a, name="جذر")
        ProductCategory.objects.bulk_create([
            ProductCategory(tenant=self.t_a, parent=root, name=f"فرع {i}")
            for i in range(20)
        ])
        self._auth()

        with CaptureQueriesContext(connection) as captured:
            res = self.client.get(
                "/api/inventory/categories/?root_only=true",
                HTTP_X_TENANT_ID=self._tenant_id,
            )

        assert res.status_code == 200, res.content[:300]
        assert len(res.json()) == 1
        assert len(res.json()[0]["children"]) == 20
        assert len(captured) <= 6, [q["sql"] for q in captured]

    def test_global_uom_list_contract(self):
        uom, _ = UnitOfMeasure.objects.get_or_create(
            code="EA", defaults={"name_ar": "حبة", "name_en": "Each"},
        )
        expected = {
            "id": uom.id,
            "code": "EA",
            "name_ar": "حبة",
            "name_en": "Each",
        }

        self._auth()
        first = self.client.get(
            "/api/inventory/uom/", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert first.status_code == 200, first.content[:300]
        assert expected in first.json()

        self._auth(user=self.owner_b, tenant=self.t_b)
        second = self.client.get(
            "/api/inventory/uom/", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert second.status_code == 200, second.content[:300]
        assert expected in second.json()
        assert "tenant" not in second.json()[0]

    def test_stock_summary_is_tenant_scoped_and_totals_match_visible_rows(self):
        Product.objects.create(
            tenant=self.t_a, sku="SUM-A1", name_ar="محلي 1",
            quantity_on_hand=2, avg_cost=10,
        )
        Product.objects.create(
            tenant=self.t_a, sku="SUM-A2", name_ar="محلي 2",
            quantity_on_hand=3, avg_cost=5,
        )
        foreign = Product.objects.create(
            tenant=self.t_b, sku="SUM-B1", name_ar="شركة أخرى",
            quantity_on_hand=99, avg_cost=100,
        )

        self._auth()
        res = self.client.get(
            "/api/inventory/stock-movements/summary/",
            HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert res.status_code == 200, res.content[:300]
        data = res.json()
        visible_ids = {row["id"] for row in data["products"]}
        assert foreign.id not in visible_ids
        assert visible_ids == {
            Product.objects.get(tenant=self.t_a, sku="SUM-A1").id,
            Product.objects.get(tenant=self.t_a, sku="SUM-A2").id,
        }
        assert data["total_products_in_stock"] == 2
        assert data["total_inventory_value"] == 35.0

    def test_stock_movement_create_rejects_foreign_tenant_product(self):
        foreign = Product.objects.create(
            tenant=self.t_b,
            sku="FOREIGN-STOCK",
            name_ar="رصيد شركة أخرى",
            quantity_on_hand=7,
            avg_cost=3,
        )
        self._auth()

        res = self.client.post(
            "/api/inventory/stock-movements/",
            {
                "product": foreign.id,
                "movement_type": "IN",
                "quantity": "5",
                "unit_cost": "4",
                "reference_type": "MANUAL",
            },
            format="json",
            HTTP_X_TENANT_ID=self._tenant_id,
        )

        assert res.status_code == 404, res.content[:300]
        foreign.refresh_from_db()
        assert foreign.quantity_on_hand == 7
        assert not StockMovement.objects.filter(product=foreign).exists()

    # ── جدول المنتجات: فلتر حالة المخزون + ترتيب حسب الكمية/الحد الأدنى ──
    def _seed_stock_mix(self):
        # qty/min_stock_level للقراءة فقط في الـ serializer — نُنشئها مباشرة.
        from decimal import Decimal
        Product.objects.create(tenant=self.t_a, sku="ST-OUT", name_ar="نفذ",
                               quantity_on_hand=Decimal("0"), min_stock_level=9)
        Product.objects.create(tenant=self.t_a, sku="ST-LOW", name_ar="منخفض",
                               quantity_on_hand=Decimal("3"), min_stock_level=5)
        Product.objects.create(tenant=self.t_a, sku="ST-OK", name_ar="متوفر",
                               quantity_on_hand=Decimal("20"), min_stock_level=1)

    def test_stock_status_filter_out_of_stock(self):
        self._auth()
        self._seed_stock_mix()
        rows = self._get("?stock_status=out_of_stock").json()
        assert {r["sku"] for r in rows} == {"ST-OUT"}

    def test_stock_status_filter_low_stock(self):
        self._auth()
        self._seed_stock_mix()
        rows = self._get("?stock_status=low_stock").json()
        assert {r["sku"] for r in rows} == {"ST-LOW"}

    def test_stock_status_filter_in_stock(self):
        self._auth()
        self._seed_stock_mix()
        rows = self._get("?stock_status=in_stock").json()
        assert {r["sku"] for r in rows} == {"ST-OK"}

    # ── ST-3: فلتر «المنشور في المتجر» — الذي تُبنى عليه شاشة «متجري» ──
    def _seed_publishing_mix(self):
        Product.objects.create(tenant=self.t_a, sku="ON-1", name_ar="معروض",
                               is_for_sale_online=True)
        Product.objects.create(tenant=self.t_a, sku="OFF-1", name_ar="غير معروض",
                               is_for_sale_online=False)
        # منتج شركة أخرى منشور — الفلتر يُطبَّق بعد فلترة الشركة لا قبلها.
        Product.objects.create(tenant=self.t_b, sku="ON-B", name_ar="جار منشور",
                               is_for_sale_online=True)

    def test_published_filter_returns_only_this_tenants_published_items(self):
        self._auth()
        self._seed_publishing_mix()
        rows = self._get("?is_for_sale_online=true").json()
        assert {r["sku"] for r in rows} == {"ON-1"}

    def test_published_filter_false_returns_the_unpublished_ones(self):
        self._auth()
        self._seed_publishing_mix()
        assert {r["sku"] for r in self._get("?is_for_sale_online=false").json()} == {"OFF-1"}

    def test_an_absent_or_junk_publishing_filter_does_not_narrow_the_list(self):
        """قيمة غير مفهومة لا تُصفّي بصمت — الجدول العام يبقى كما هو."""
        self._auth()
        self._seed_publishing_mix()
        assert {r["sku"] for r in self._get().json()} == {"ON-1", "OFF-1"}
        assert {r["sku"] for r in self._get("?is_for_sale_online=maybe").json()} == {"ON-1", "OFF-1"}

    def test_ordering_by_quantity_and_min_stock_level(self):
        self._auth()
        self._seed_stock_mix()
        asc = [r["sku"] for r in self._get("?ordering=quantity_on_hand").json()]
        assert asc == ["ST-OUT", "ST-LOW", "ST-OK"]
        # min_stock_level قابل للترتيب الآن (كان غائباً عن ordering_fields)
        by_min = [r["sku"] for r in self._get("?ordering=min_stock_level").json()]
        assert by_min == ["ST-OK", "ST-LOW", "ST-OUT"]

    # ── داتا شيت المنتج: رابط Cloudinary يُوجَّه لمرفق file_type='Datasheet' ──
    # SystemAttachment مُدار خارجياً (managed=False) فلا يُبنى جدوله في قاعدة الاختبار،
    # لذا نُموّهه ونتحقّق أن مسار الحفظ يستدعي create بالنوع والرابط الصحيحين.
    def test_datasheet_url_routed_to_attachment_create(self):
        self._auth()
        url = "https://res.cloudinary.com/dd63wjj5x/raw/upload/ds.pdf"
        with patch("core.models.SystemAttachment") as MockSA:
            MockSA.objects.filter.return_value.exists.return_value = False
            res = self._post({"name_ar": "منتج بداتا شيت", "datasheet_url": url})
            assert res.status_code == 201, res.content[:300]
            ds_calls = [
                c.kwargs for c in MockSA.objects.create.call_args_list
                if c.kwargs.get("file_type") == "Datasheet"
            ]
            assert len(ds_calls) == 1
            assert ds_calls[0]["file_path"] == url
            assert ds_calls[0]["related_table"] == "products"

    def test_remove_datasheet_deletes_row_and_destroys_cloudinary(self):
        from unittest.mock import MagicMock
        self._auth()
        pid = self._post({"name_ar": "منتج للحذف"}).json()["id"]
        url = "https://res.cloudinary.com/dd63wjj5x/raw/upload/v1/ktra_uploads/ds.pdf"
        att = MagicMock(id=77, file_path=url)
        with patch("core.models.SystemAttachment") as MockSA, \
                patch("core.media_views.destroy_cloudinary_asset") as mock_destroy:
            MockSA.objects.filter.return_value.first.return_value = att
            res = self.client.delete(
                f"{PRODUCTS_URL}{pid}/datasheets/77/", HTTP_X_TENANT_ID=self._tenant_id,
            )
            assert res.status_code == 204, res.content[:300]
            mock_destroy.assert_called_once_with(url)  # يُحاول حذف Cloudinary بالرابط
            att.delete.assert_called_once()             # ويحذف صف SQL

    def test_remove_datasheet_missing_is_404(self):
        self._auth()
        pid = self._post({"name_ar": "منتج بلا مرفق"}).json()["id"]
        with patch("core.models.SystemAttachment") as MockSA:
            MockSA.objects.filter.return_value.first.return_value = None
            res = self.client.delete(
                f"{PRODUCTS_URL}{pid}/datasheets/999/", HTTP_X_TENANT_ID=self._tenant_id,
            )
            assert res.status_code == 404

    # ── W10: اسم المنتج قابل للتعديل بعد الإنشاء (حارس أن name_ar ليس read_only) ──
    def test_patch_updates_name_ar(self):
        self._auth()
        pid = self._post({"name_ar": "الاسم القديم"}).json()["id"]
        res = self.client.patch(
            f"{PRODUCTS_URL}{pid}/", {"name_ar": "الاسم الجديد"},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert res.status_code in (200, 202), res.content[:300]
        p = Product.objects.get(pk=pid)
        assert p.name_ar == "الاسم الجديد"
        activity = ActivityLog.objects.get(
            tenant=self.t_a, entity_type="product", entity_id=pid, action="update",
        )
        assert activity.description == "غيّر اسم المنتج من «الاسم القديم» إلى «الاسم الجديد»"
        assert activity.metadata["changes"] == [{
            "field": "name_ar",
            "label": "اسم المنتج",
            "old": "الاسم القديم",
            "new": "الاسم الجديد",
        }]

    # ── كرت المنتج: «سعر البيع» يُحفظ من نفس نموذج الكرت (لا شاشة منفصلة) ──
    def test_sale_price_round_trips_through_api(self):
        self._auth()
        created = self._post({"name_ar": "منتج بسعر بيع", "sale_price": "150.5"}).json()
        assert created["sale_price"] == "150.5000"
        res = self.client.patch(
            f"{PRODUCTS_URL}{created['id']}/", {"sale_price": "175"},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert res.status_code in (200, 202), res.content[:300]
        from decimal import Decimal
        assert Product.objects.get(pk=created["id"]).sale_price == Decimal("175")
        activity = ActivityLog.objects.filter(
            tenant=self.t_a, entity_type="product", entity_id=created["id"], action="update",
        ).latest("id")
        # G1: بلا أصفار زائدة في نصّ السجل — «150.5» لا «150.5000».
        assert activity.description == (
            "عدّل سعر البيع للمنتج «منتج بسعر بيع» من 150.5 إلى 175"
        )
        assert activity.metadata["changes"] == [{
            "field": "sale_price",
            "label": "سعر البيع",
            "old": "150.5",
            "new": "175",
        }]

        before = ActivityLog.objects.filter(
            tenant=self.t_a, entity_type="product", entity_id=created["id"], action="update",
        ).count()
        same = self.client.patch(
            f"{PRODUCTS_URL}{created['id']}/", {"sale_price": "175"},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert same.status_code in (200, 202), same.content[:300]
        assert ActivityLog.objects.filter(
            tenant=self.t_a, entity_type="product", entity_id=created["id"], action="update",
        ).count() == before

    # ── #33: مفتاح التجديد يُقرأ ويُكتب من كرت المنتج، والافتراضي يدوي ──
    def test_reorder_mode_round_trips_through_api(self):
        self._auth()
        created = self._post({"name_ar": "منتج تجديد"}).json()
        assert created["reorder_mode"] == "manual"
        res = self.client.patch(
            f"{PRODUCTS_URL}{created['id']}/", {"reorder_mode": "auto"},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert res.status_code in (200, 202), res.content[:300]
        assert Product.objects.get(pk=created["id"]).reorder_mode == "auto"

    # ── M0: تعديلٌ يحمل «النوع» و«التصنيف» معاً كان يسقط 500 ──
    def test_patch_with_variant_group_and_category_succeeds(self):
        """`_auto_create_group_category` كان يقرأ `self.instance` — وهي صفة
        السيريالايزر لا الـViewSet — فكلّ تعديلٍ يمرّ بهذا الفرع يرفع
        AttributeError. الكرت يرسل الحقلين معاً في كل حفظ، فالمسار حيّ لا نادر.

        task20: القاعدة نفسها حُذفت بلا بديل — لم يعد تصنيفٌ فرعي يُخترع من
        `variant_group`، والتصنيف المُرسَل صراحةً يبقى كما هو.
        """
        self._auth()
        category = ProductCategory.objects.create(tenant=self.t_a, name="إطارات")
        pid = self._post({"name_ar": "إطار", "category": category.id}).json()["id"]

        res = self.client.patch(
            f"{PRODUCTS_URL}{pid}/",
            {"variant_group": "195/65/15", "category": category.id},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert res.status_code in (200, 202), res.content[:300]
        product = Product.objects.get(pk=pid)
        assert product.variant_group == "195/65/15"
        # task20: بلا اختراع تصنيفٍ فرعي — التصنيف يبقى ما أرسله المستخدم بالضبط.
        assert product.category_id == category.id

    # ── M0: التصنيف محدِّدٌ يعني شجرته (كان exact-id هنا وشجرةً في الكرت المجمّع) ──
    def test_category_filter_includes_descendants(self):
        self._auth()
        root = ProductCategory.objects.create(tenant=self.t_a, name="جذر")
        child = ProductCategory.objects.create(tenant=self.t_a, name="ابن", parent=root)
        grandchild = ProductCategory.objects.create(tenant=self.t_a, name="حفيد", parent=child)
        Product.objects.create(tenant=self.t_a, sku="R-1", name_ar="منتج الجذر", category=root)
        Product.objects.create(tenant=self.t_a, sku="C-1", name_ar="منتج الابن", category=child)
        Product.objects.create(tenant=self.t_a, sku="G-1", name_ar="منتج الحفيد", category=grandchild)
        Product.objects.create(tenant=self.t_a, sku="O-1", name_ar="منتج خارج الشجرة")

        names = {row["name_ar"] for row in self._get(f"?category={root.id}").json()}
        assert names == {"منتج الجذر", "منتج الابن", "منتج الحفيد"}

        leaf_names = {row["name_ar"] for row in self._get(f"?category={child.id}").json()}
        assert leaf_names == {"منتج الابن", "منتج الحفيد"}

    def test_foreign_category_filter_returns_nothing(self):
        self._auth()
        foreign = ProductCategory.objects.create(tenant=self.t_b, name="تصنيف الشركة الأخرى")
        Product.objects.create(tenant=self.t_a, sku="X-1", name_ar="منتجي")
        assert self._get(f"?category={foreign.id}").json() == []

    # ── M0: الكرت كان يعرض رقم الوحدة مكان اسمها ──
    def test_uom_name_returns_the_name_not_the_id(self):
        self._auth()
        uom = UnitOfMeasure.objects.create(code="PCS", name_ar="قطعة", name_en="Piece")
        created = self._post({"name_ar": "منتج بوحدة", "uom_id": uom.id}).json()
        assert created["uom_id"] == uom.id
        assert created["uom_name"] == "قطعة"

    def test_uom_name_falls_back_to_legacy_text(self):
        self._auth()
        product = Product.objects.create(
            tenant=self.t_a, sku="L-1", name_ar="منتج قديم", uom_legacy="كرتونة",
        )
        res = self.client.get(f"{PRODUCTS_URL}{product.id}/", HTTP_X_TENANT_ID=self._tenant_id)
        assert res.status_code == 200, res.content[:300]
        assert res.json()["uom_name"] == "كرتونة"
