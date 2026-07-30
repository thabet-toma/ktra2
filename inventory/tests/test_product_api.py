"""task14 M2 (DEF-A2/A3/A4/A5) — Product API:
توليد SKU خادمي، الاسم فقط إلزامي، أخطاء بحقلها الصحيح،
ترتيب حتمي + بحث + فلتر فترة + ترقيم صفحات opt-in، وعزل الشركات.
"""
import datetime

from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from inventory.models import Product, ProductCategory, StockMovement, UnitOfMeasure
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class ProductApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="items_a", password="x")
        cls.owner_b = User.objects.create_user(username="items_b", password="x")
        cls.t_a = create_company("شركة الأصناف أ", cls.owner_a)
        cls.t_b = create_company("شركة الأصناف ب", cls.owner_b)

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
        res = self._post({"name_ar": "صنف بالاسم فقط"})
        assert res.status_code == 201, res.content[:300]
        data = res.json()
        assert data["sku"] == "000001"
        assert data["created_at"]

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
        assert "اسم الصنف مطلوب" in str(payload)

    def test_duplicate_explicit_sku_yields_sku_field_error(self):
        self._auth()
        assert self._post({"name_ar": "الأصل", "sku": "DUP-1"}).status_code == 201
        res = self._post({"name_ar": "المكرر", "sku": "DUP-1"})
        assert res.status_code == 400
        assert "sku" in str(res.json())

    def test_cross_tenant_category_rejected(self):
        self._auth()
        foreign_cat = ProductCategory.objects.create(tenant=self.t_b, name="تصنيف الشركة الأخرى")
        res = self._post({"name_ar": "صنف", "category": foreign_cat.id})
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
            self._post({"name_ar": f"صنف {i}"})
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

    # ── جدول الأصناف: فلتر حالة المخزون + ترتيب حسب الكمية/الحد الأدنى ──
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
            res = self._post({"name_ar": "صنف بداتا شيت", "datasheet_url": url})
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
        pid = self._post({"name_ar": "صنف للحذف"}).json()["id"]
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
        pid = self._post({"name_ar": "صنف بلا مرفق"}).json()["id"]
        with patch("core.models.SystemAttachment") as MockSA:
            MockSA.objects.filter.return_value.first.return_value = None
            res = self.client.delete(
                f"{PRODUCTS_URL}{pid}/datasheets/999/", HTTP_X_TENANT_ID=self._tenant_id,
            )
            assert res.status_code == 404

    # ── W10: اسم الصنف قابل للتعديل بعد الإنشاء (حارس أن name_ar ليس read_only) ──
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

    # ── كرت الصنف: «سعر البيع» يُحفظ من نفس نموذج الكرت (لا شاشة منفصلة) ──
    def test_sale_price_round_trips_through_api(self):
        self._auth()
        created = self._post({"name_ar": "صنف بسعر بيع", "sale_price": "150.5"}).json()
        assert created["sale_price"] == "150.5000"
        res = self.client.patch(
            f"{PRODUCTS_URL}{created['id']}/", {"sale_price": "175"},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert res.status_code in (200, 202), res.content[:300]
        from decimal import Decimal
        assert Product.objects.get(pk=created["id"]).sale_price == Decimal("175")
