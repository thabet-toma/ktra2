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
from django.utils import timezone
from rest_framework.test import APIRequestFactory, APITestCase

from core.models import ActivityLog
from core.pricing import last_purchase_prices_base_currency
from inventory.models import Product, ProductCategory, ProductFamily, StockLayer, StockMovement, UnitOfMeasure
from inventory.serializers import StockMovementSerializer
from inventory.services import add_brand_to_family, create_product_with_family
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


def _posted_purchase(tenant, supplier, product, *, number, date, price):
    """فاتورة شراء مرحَّلة بسطرٍ واحد — الشكل الحقيقي الذي يقرأه `core.pricing`."""
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, partner=supplier,
        currency=Currency.objects.filter(IsBaseCurrency=True).first(),
        invoice_date=date, exchange_rate=Decimal("1"), is_posted=True,
    )
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=product, name="منتج", quantity=Decimal("1"),
        unit_price=Decimal(str(price)), total_price=Decimal(str(price)),
    )
    return inv



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
        """العقد يكسب حقلين فقط (لا يتوسّع أكثر، قرارٌ صريح على #12) — بالإضافة
        إلى زوجٍ لاحقٍ صريح آخر: السعر التقديري (#133).

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
            "is_serialized",
            "is_for_sale_online", "online_price", "online_description",
            "attachments", "supplier_codes_text",
        }
        # #133: زوجٌ صريحٌ آخر أُضيف لاحقاً — السعر التقديري (أقلّ شراء ضمن
        # آخر ٥ فواتير) ومصدره، ليقرأه منتقي المستندات بلا فتح كرت المنتج.
        #
        # #147: وحقلٌ ثالثٌ صريح — `image_url`. توسيعٌ **مقصود** لا سهو:
        # صفحةُ طلب عرض السعر العامّة تعرض صورة كلّ صنفٍ للمورّد الذي يسعّر،
        # ومحرِّرُ بند الطلبية يرفعها من مكانه — وكلاهما يقرأ المنتجات من عقد
        # المنتقي لا من العقد الكامل. حقلٌ نصّيٌّ واحد (رابط) لا كائن.
        #
        # #233: رابعٌ صريح — `serial_required_by`. سببُ فرض الرقم التسلسلي
        # (سياسة كفالة `serial`) — يقرأه محرّرا البيع والشراء ليُظهرا عمود
        # الأرقام على البند حتى لو كان نمط الشركة «بدون».
        assert set(row.keys()) == known_before | {
            "family_id", "family_name",
            "indicative_purchase_price", "indicative_purchase_price_source",
            "image_url",
            "serial_required_by",
            # T2: `is_active` — المنتقي يعرض المعطَّل حين تُطلب `status=all`
            # (مستندٌ قديم يحمل منتجاً عُطِّل لاحقاً)، فيلزمه أن يعرف أيّها معطَّل.
            "is_active",
        }

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
        صفٍّ يُعيد بالضبط ما بُني هذا العقد الضيّق ليمنعه.

        الحدّ صار ٧ لا ٦ بعد #133: `indicative_purchase_price`/`_source` يقرآن
        من خريطةٍ واحدة (`_indicative_purchase_price_map`) — استعلامٌ إضافيٌّ
        **واحد** ثابت مهما بلغ عدد الصفوف، لا استعلاماً لكل صفّ.

        والحدّ صار ٨ لا ٧ بعد #233: `serial_required_by` يقرأ من
        `serial_requirement_map` — نداءُ `core.hooks.serial_requirements`
        الواحد لهذه الصفحة (`ProductViewSet._serial_requirement_map`) يفتح
        استعلاماً إضافياً ثابتاً واحداً (سياسات الكفالة)، لا استعلاماً لكل صفّ.
        """
        for i in range(10):
            create_product_with_family(tenant=self.t_a, name_ar=f"منتج {i}", sku=f"FAMQ-{i}")
        self._auth()

        with CaptureQueriesContext(connection) as captured:
            res = self._get("?view=lookup")

        assert res.status_code == 200, res.content[:300]
        assert len(res.json()) == 10
        assert len(captured) <= 8, [q["sql"] for q in captured]

    # ── «آخر سعر شراء» على قائمة المنتجات (ITEM-PURCHASE-DISPLAY) ──
    def test_list_exposes_last_purchase_price_apart_from_lowest_and_avg_cost(self):
        """الرقم الأساسي في القائمة هو آخر سعر شراء — لا الأقلّ ولا متوسط التكلفة.

        الأرقام الثلاثة متمايزة (متوسط ٣٠ · أقلّ ٢٠ · آخر ٤٠) كي يكشف الاختبار
        أيّ توصيلٍ خاطئ: لو قُرئ الحقل من `indicative_purchase_price` لظهر ٢٠،
        ولو سقط إلى `avg_cost` لظهر ٣٠.
        """
        sup = Partner.objects.create(
            tenant=self.t_a, name="مورد القائمة", partner_type="Supplier")
        product = Product.objects.create(
            tenant=self.t_a, sku="LAST-1", name_ar="منتج الأسعار", avg_cost=Decimal("30"))
        _posted_purchase(self.t_a, sup, product, number="L-1", date="2026-06-01", price=20)
        _posted_purchase(self.t_a, sup, product, number="L-2", date="2026-06-15", price=100)
        _posted_purchase(self.t_a, sup, product, number="L-3", date="2026-06-20", price=40)
        self._auth()

        res = self._get()

        assert res.status_code == 200, res.content[:300]
        row = next(r for r in res.json() if r["id"] == product.id)
        assert Decimal(row["last_purchase_price"]) == Decimal("40.0000")
        assert Decimal(row["indicative_purchase_price"]) == Decimal("20.0000")
        assert Decimal(row["avg_cost"]) == Decimal("30")

    def test_list_last_purchase_price_is_null_without_posted_history(self):
        """بلا شراء مرحَّل يبقى الحقل `null` — لا سقوطَ إلى `avg_cost`.

        الواجهة تعرضه «—»؛ رقمُ متوسط التكلفة مكان سعر الشراء كذبةٌ صامتة.
        """
        product = Product.objects.create(
            tenant=self.t_a, sku="LAST-2", name_ar="بلا شراء", avg_cost=Decimal("30"))
        self._auth()

        res = self._get()

        assert res.status_code == 200, res.content[:300]
        row = next(r for r in res.json() if r["id"] == product.id)
        assert row["last_purchase_price"] is None
        assert row["indicative_purchase_price"] is None

    def test_list_last_purchase_price_is_tenant_scoped(self):
        """فاتورة شركةٍ أخرى (ولو كانت أحدث) لا تُسرَّب إلى صفّ هذه الشركة."""
        sup = Partner.objects.create(
            tenant=self.t_a, name="مورد محلي", partner_type="Supplier")
        product = Product.objects.create(
            tenant=self.t_a, sku="LAST-3", name_ar="منتج مشترك", avg_cost=Decimal("0"))
        _posted_purchase(self.t_a, sup, product, number="LOC-1", date="2026-06-01", price=40)
        foreign_sup = Partner.objects.create(
            tenant=self.t_b, name="مورد أجنبي", partner_type="Supplier")
        _posted_purchase(self.t_b, foreign_sup, product, number="FOR-1",
                         date="2026-07-01", price=1)
        self._auth()

        res = self._get()

        assert res.status_code == 200, res.content[:300]
        row = next(r for r in res.json() if r["id"] == product.id)
        assert Decimal(row["last_purchase_price"]) == Decimal("40.0000")

    def test_list_last_purchase_price_adds_no_query_per_row(self):
        """الحقل يُقرأ من خريطةٍ واحدة للصفحة — لا استعلامَ لكل صفّ.

        القائمة كاملةً تُقاس مرّتين: صفٌّ واحد وستةُ صفوف. تساوي العددين هو
        البرهان؛ رقمٌ ثابتٌ مطلقٌ يكذب مع كل إضافةٍ إلى `get_serializer_context`.
        """
        sup = Partner.objects.create(
            tenant=self.t_a, name="مورد الدفعة", partner_type="Supplier")
        products = []
        for i in range(6):
            p = Product.objects.create(
                tenant=self.t_a, sku=f"LASTQ-{i}", name_ar=f"منتج دفعة {i}",
                avg_cost=Decimal("0"))
            _posted_purchase(self.t_a, sup, p, number=f"LQ-{i}",
                             date=f"2026-06-0{i + 1}", price=10 + i)
            products.append(p)
        self._auth()

        with CaptureQueriesContext(connection) as small:
            one = self._get("?search=LASTQ-0")
        with CaptureQueriesContext(connection) as large:
            many = self._get()

        assert len(one.json()) == 1
        assert len(many.json()) == 6
        assert len(large) == len(small), [q["sql"] for q in large]

    # ── ITEM-PURCHASE-DISPLAY: نطاقُ خريطة آخر سعر شراء = الصفوف المعروضة ──
    def _scope_calls(self, spy):
        """نطاقُ كلّ نداءٍ للدالّة الحقيقية (`product_ids`) — لا نتيجةً مُستبدلة.

        البرهان نطاقُ النداء نفسه لا الرقم المعروض: الخريطةُ الشاملة تُرجع الرقم
        الصحيح أيضاً، فما يفرّقها عمّا يجب هو ما طُلب مسحُه.
        """
        return [call.kwargs.get("product_ids") for call in spy.call_args_list]

    def test_filtered_list_does_not_load_purchase_prices_for_unshown_products(self):
        """قائمةٌ مُرشَّحة لا تُحمِّل أسعار شراء منتجات الشركة التي لا تُعرَض.

        المنتجات الأخرى من **الشركة نفسها** عمداً: العزل بين الشركات يخفي
        العَرَض ويُوهم أنّ النطاق ضُبط.
        """
        sup = Partner.objects.create(
            tenant=self.t_a, name="مورد النطاق", partner_type="Supplier")
        wanted = Product.objects.create(
            tenant=self.t_a, sku="SCOPE-1", name_ar="المطلوب", avg_cost=Decimal("0"))
        _posted_purchase(self.t_a, sup, wanted, number="SC-1", date="2026-06-01", price=40)
        for i in range(3):
            noise = Product.objects.create(
                tenant=self.t_a, sku=f"NOISE-{i}", name_ar=f"غير مطلوب {i}",
                avg_cost=Decimal("0"))
            _posted_purchase(self.t_a, sup, noise, number=f"NZ-{i}",
                             date="2026-06-02", price=900 + i)
        self._auth()

        with patch("core.pricing.last_purchase_prices_base_currency",
                   wraps=last_purchase_prices_base_currency) as spy:
            res = self._get("?search=SCOPE-1")

        assert res.status_code == 200, res.content[:300]
        rows = res.json()
        assert [row["id"] for row in rows] == [wanted.id]
        assert Decimal(rows[0]["last_purchase_price"]) == Decimal("40.0000")
        assert self._scope_calls(spy) == [[wanted.id]], self._scope_calls(spy)

    def test_retrieve_does_not_load_purchase_prices_for_other_products(self):
        """الصفّ المفرد لم يعد يمسح بنود شراء الشركة كلها لأجل رقمٍ واحد."""
        sup = Partner.objects.create(
            tenant=self.t_a, name="مورد الكرت", partner_type="Supplier")
        wanted = Product.objects.create(
            tenant=self.t_a, sku="ONE-1", name_ar="الكرت", avg_cost=Decimal("0"))
        _posted_purchase(self.t_a, sup, wanted, number="ON-1", date="2026-06-01", price=40)
        for i in range(3):
            noise = Product.objects.create(
                tenant=self.t_a, sku=f"ONE-N{i}", name_ar=f"جار {i}", avg_cost=Decimal("0"))
            _posted_purchase(self.t_a, sup, noise, number=f"ON-N{i}",
                             date="2026-06-02", price=70 + i)
        self._auth()

        with patch("core.pricing.last_purchase_prices_base_currency",
                   wraps=last_purchase_prices_base_currency) as spy:
            res = self.client.get(
                f"{PRODUCTS_URL}{wanted.id}/", HTTP_X_TENANT_ID=self._tenant_id)

        assert res.status_code == 200, res.content[:300]
        assert Decimal(res.json()["last_purchase_price"]) == Decimal("40.0000")
        assert self._scope_calls(spy) == [[wanted.id]], self._scope_calls(spy)

    def test_paginated_family_completion_scopes_to_every_returned_row(self):
        """صفحةٌ مكتملةُ العائلات: النطاق = صفوف الاستجابة ومنها الأخ الواقع
        خارج الصفحة — وإلا رجع الصفّ المجمَّع بلا رقم — ولا يدخل غريبٌ لا يُعرَض.
        """
        sup = Partner.objects.create(
            tenant=self.t_a, name="مورد العائلة", partner_type="Supplier")
        family = ProductFamily.objects.create(tenant=self.t_a, name_ar="عائلة النطاق")
        # ترتيب الإنشاء يحكم `-id`: الغريب أقدمُ فلا يقع في الصفحة الأولى.
        stranger = Product.objects.create(
            tenant=self.t_a, sku="PG-X", name_ar="غريب عن الصفحة", avg_cost=Decimal("0"))
        outside = Product.objects.create(
            tenant=self.t_a, family=family, sku="PG-1", name_ar="خارج الصفحة",
            avg_cost=Decimal("0"))
        inside = Product.objects.create(
            tenant=self.t_a, family=family, sku="PG-2", name_ar="داخل الصفحة",
            avg_cost=Decimal("0"))
        _posted_purchase(self.t_a, sup, outside, number="PG-OUT", date="2026-06-01", price=11)
        _posted_purchase(self.t_a, sup, inside, number="PG-IN", date="2026-06-05", price=22)
        _posted_purchase(self.t_a, sup, stranger, number="PG-X1", date="2026-06-09", price=99)
        self._auth()

        with patch("core.pricing.last_purchase_prices_base_currency",
                   wraps=last_purchase_prices_base_currency) as spy:
            res = self._get("?page=1&page_size=1&complete_families=1")

        assert res.status_code == 200, res.content[:300]
        rows = {
            row["id"]: Decimal(row["last_purchase_price"] or "0")
            for row in res.json()["results"]
        }
        # الصفحة = الأحدث (-id) والباقي إكمالُ عائلة؛ ولكل صفٍّ آخر سعرٍ لبرنده.
        assert rows == {inside.id: Decimal("22.0000"), outside.id: Decimal("11.0000")}
        assert [set(ids) for ids in self._scope_calls(spy)] == [{inside.id, outside.id}], \
            self._scope_calls(spy)

    def test_create_and_update_responses_scope_to_the_saved_product(self):
        """ردُّ الإنشاء/التعديل صفٌّ واحد: نطاقُه منتجه لا الشركة كاملة."""
        sup = Partner.objects.create(
            tenant=self.t_a, name="مورد الكتابة", partner_type="Supplier")
        other = Product.objects.create(
            tenant=self.t_a, sku="WR-0", name_ar="منتج قائم", avg_cost=Decimal("0"))
        _posted_purchase(self.t_a, sup, other, number="WR-1", date="2026-06-01", price=77)
        self._auth()

        with patch("core.pricing.last_purchase_prices_base_currency",
                   wraps=last_purchase_prices_base_currency) as create_spy:
            created = self._post({"name_ar": "منتج كتابة"})
        assert created.status_code == 201, created.content[:300]
        body = created.json()
        assert body["last_purchase_price"] is None
        assert self._scope_calls(create_spy) == [[body["id"]]], self._scope_calls(create_spy)

        with patch("core.pricing.last_purchase_prices_base_currency",
                   wraps=last_purchase_prices_base_currency) as update_spy:
            updated = self.client.patch(
                f"{PRODUCTS_URL}{body['id']}/", {"name_ar": "منتج كتابة معدّل"},
                format="json", HTTP_X_TENANT_ID=self._tenant_id)
        assert updated.status_code == 200, updated.content[:300]
        assert updated.json()["last_purchase_price"] is None
        assert self._scope_calls(update_spy) == [[body["id"]]], self._scope_calls(update_spy)

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

    def test_stock_movement_create_rejects_forged_sale_reference(self):
        prod = Product.objects.create(
            tenant=self.t_a,
            sku="MANUAL-OUT-1",
            name_ar="منتج صرف",
            quantity_on_hand=Decimal("10"),
            avg_cost=Decimal("5"),
        )
        self._auth()

        res = self.client.post(
            "/api/inventory/stock-movements/",
            {
                "product": prod.id,
                "movement_type": "OUT",
                "quantity": "2",
                "unit_cost": "5",
                "reference_type": "SALE",
                "reference_id": 123,
            },
            format="json",
            HTTP_X_TENANT_ID=self._tenant_id,
        )

        assert res.status_code == 400, res.content[:300]
        assert res.json() == {"error": "نوع المرجع غير مسموح في الحركة اليدوية"}
        assert StockMovement.objects.filter(tenant=self.t_a, product=prod).count() == 0
        prod.refresh_from_db()
        assert prod.quantity_on_hand == Decimal("10")

    def test_stock_movement_create_rejects_forged_purchase_reference(self):
        prod = Product.objects.create(
            tenant=self.t_a,
            sku="MANUAL-IN-1",
            name_ar="منتج وارد",
            quantity_on_hand=Decimal("0"),
            avg_cost=Decimal("0"),
        )
        self._auth()

        res = self.client.post(
            "/api/inventory/stock-movements/",
            {
                "product": prod.id,
                "movement_type": "IN",
                "quantity": "5",
                "unit_cost": "10",
                "reference_type": "PURCHASE_INVOICE",
            },
            format="json",
            HTTP_X_TENANT_ID=self._tenant_id,
        )

        assert res.status_code == 400, res.content[:300]
        assert res.json() == {"error": "نوع المرجع غير مسموح في الحركة اليدوية"}
        assert StockMovement.objects.filter(tenant=self.t_a, product=prod).count() == 0
        assert StockLayer.objects.filter(tenant=self.t_a, product=prod).count() == 0

    def test_stock_movement_create_defaults_missing_reference_type_to_manual(self):
        prod = Product.objects.create(
            tenant=self.t_a,
            sku="MANUAL-DEF-1",
            name_ar="منتج افتراضي",
        )
        self._auth()

        res = self.client.post(
            "/api/inventory/stock-movements/",
            {
                "product": prod.id,
                "movement_type": "IN",
                "quantity": "3",
                "unit_cost": "4",
            },
            format="json",
            HTTP_X_TENANT_ID=self._tenant_id,
        )

        assert res.status_code == 201, res.content[:300]
        assert StockMovement.objects.get(pk=res.json()["id"]).reference_type == "MANUAL"

    def test_stock_movement_create_allows_explicit_manual_reference(self):
        prod = Product.objects.create(
            tenant=self.t_a,
            sku="MANUAL-EXP-1",
            name_ar="منتج يدوي",
        )
        self._auth()

        res = self.client.post(
            "/api/inventory/stock-movements/",
            {
                "product": prod.id,
                "movement_type": "IN",
                "quantity": "3",
                "unit_cost": "4",
                "reference_type": "MANUAL",
            },
            format="json",
            HTTP_X_TENANT_ID=self._tenant_id,
        )

        assert res.status_code == 201, res.content[:300]
        assert StockMovement.objects.get(pk=res.json()["id"]).reference_type == "MANUAL"

    def test_stock_movement_create_normalizes_null_and_empty_reference_type_to_manual(self):
        prod = Product.objects.create(
            tenant=self.t_a,
            sku="MANUAL-NULL-1",
            name_ar="منتج فارغ المرجع",
        )
        self._auth()

        for raw_ref in (None, ""):
            res = self.client.post(
                "/api/inventory/stock-movements/",
                {
                    "product": prod.id,
                    "movement_type": "IN",
                    "quantity": "1",
                    "unit_cost": "2",
                    "reference_type": raw_ref,
                },
                format="json",
                HTTP_X_TENANT_ID=self._tenant_id,
            )
            assert res.status_code == 201, res.content[:300]
            assert StockMovement.objects.get(pk=res.json()["id"]).reference_type == "MANUAL"

    def test_stock_movement_serializer_treats_reference_fields_as_read_only(self):
        prod = Product.objects.create(
            tenant=self.t_a,
            sku="SER-RO-1",
            name_ar="منتج سيريالايزر",
        )
        serializer = StockMovementSerializer(
            data={
                "product": prod.id,
                "movement_type": "IN",
                "quantity": "5",
                "unit_cost": "4",
                "movement_date": "2026-11-18",
                "reference_type": "SALE",
                "reference_id": 123,
            }
        )
        assert serializer.is_valid(), serializer.errors
        assert "reference_type" not in serializer.validated_data
        assert "reference_id" not in serializer.validated_data

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

    # ── M1B-3a: السعر الثابت (standard_cost) في السيريالايزر وسجل النشاط ──
    def test_standard_cost_round_trips_and_logs_activity(self):
        self._auth()
        created = self._post({"name_ar": "منتج بسعر ثابت", "standard_cost": "10.50"}).json()
        assert created["standard_cost"] == "10.5000"
        assert Product.objects.get(pk=created["id"]).standard_cost == Decimal("10.5000")

        res = self.client.patch(
            f"{PRODUCTS_URL}{created['id']}/", {"standard_cost": "14.25"},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert res.status_code == 200, res.content[:300]
        assert res.json()["standard_cost"] == "14.2500"
        assert Product.objects.get(pk=created["id"]).standard_cost == Decimal("14.2500")

        activity = ActivityLog.objects.filter(
            tenant=self.t_a, entity_type="product", entity_id=created["id"], action="update",
        ).latest("id")
        assert activity.metadata["changes"] == [{
            "field": "standard_cost",
            "label": "السعر الثابت",
            "old": "10.5",
            "new": "14.25",
        }]

        bad = self.client.patch(
            f"{PRODUCTS_URL}{created['id']}/", {"standard_cost": "-1"},
            format="json", HTTP_X_TENANT_ID=self._tenant_id,
        )
        assert bad.status_code == 400, bad.content[:300]

    # ── M3-COGS: inventory_avg_cost و method_cost في Product API + الدفعة الواحدة ──
    def _make_purchase_layer(
        self, tenant, product, *, qty, unit_cost, layer_date,
        reference_type="PURCHASE_INVOICE", is_provisional=False,
    ):
        mv = StockMovement.objects.create(
            tenant=tenant,
            product=product,
            movement_type="IN",
            quantity=Decimal(str(qty)),
            unit_cost=Decimal(str(unit_cost)),
            total_cost=(Decimal(str(qty)) * Decimal(str(unit_cost))).quantize(Decimal("0.01")),
            reference_type=reference_type,
            movement_date=layer_date,
        )
        return StockLayer.objects.create(
            tenant=tenant,
            product=product,
            layer_date=layer_date,
            original_qty=Decimal(str(qty)),
            remaining_qty=Decimal(str(qty)),
            unit_cost=Decimal(str(unit_cost)),
            source_movement=mv,
            is_provisional=is_provisional,
        )

    def test_list_exposes_inventory_avg_cost_from_open_layers_not_product_avg_cost(self):
        p_layers = Product.objects.create(
            tenant=self.t_a, sku="IAVG-1", name_ar="له طبقات",
            avg_cost=Decimal("99.0000"),
        )
        p_empty = Product.objects.create(
            tenant=self.t_a, sku="IAVG-2", name_ar="بلا طبقات مفتوحة",
            avg_cost=Decimal("55.0000"),
        )
        self._make_purchase_layer(
            self.t_a, p_layers, qty=8, unit_cost=10,
            layer_date=datetime.date(2026, 6, 1),
        )
        self._make_purchase_layer(
            self.t_a, p_layers, qty=4, unit_cost=16,
            layer_date=datetime.date(2026, 6, 2),
        )
        self._auth()

        rows = {r["id"]: r for r in self._get().json()}
        assert Decimal(rows[p_layers.id]["inventory_avg_cost"]) == Decimal("12.0000")
        assert Decimal(rows[p_layers.id]["avg_cost"]) == Decimal("99.0000")
        assert rows[p_empty.id]["inventory_avg_cost"] is None

    def test_list_exposes_method_cost_per_tenant_cogs_method_with_fallback(self):
        from sales.models import SalesSettings

        today = timezone.localdate()
        p_std = Product.objects.create(
            tenant=self.t_a, sku="MC-STD", name_ar="معياري",
            standard_cost=Decimal("7.0000"),
        )
        p_no_std = Product.objects.create(
            tenant=self.t_a, sku="MC-NOSTD", name_ar="بلا معياري",
            standard_cost=None,
        )
        self._make_purchase_layer(
            self.t_a, p_std, qty=5, unit_cost=10, layer_date=today - datetime.timedelta(days=2),
        )
        self._make_purchase_layer(
            self.t_a, p_std, qty=5, unit_cost=20, layer_date=today - datetime.timedelta(days=1),
        )
        self._make_purchase_layer(
            self.t_a, p_no_std, qty=4, unit_cost=15, layer_date=today - datetime.timedelta(days=1),
        )
        self._auth()

        ss, _ = SalesSettings.objects.get_or_create(tenant=self.t_a)

        # 1) standard: uses standard_cost when set, falls back to inventory_avg_cost when None
        ss.cogs_cost_method = "standard"
        ss.save(update_fields=["cogs_cost_method"])
        rows = {r["id"]: r for r in self._get().json()}
        assert Decimal(rows[p_std.id]["method_cost"]) == Decimal("7.0000")
        assert Decimal(rows[p_no_std.id]["method_cost"]) == Decimal("15.0000")

        # 2) last_purchase: latest non-provisional purchase layer up to today
        ss.cogs_cost_method = "last_purchase"
        ss.save(update_fields=["cogs_cost_method"])
        rows = {r["id"]: r for r in self._get().json()}
        assert Decimal(rows[p_std.id]["method_cost"]) == Decimal("20.0000")

        # 3) fifo: equals inventory_avg_cost
        ss.cogs_cost_method = "fifo"
        ss.save(update_fields=["cogs_cost_method"])
        rows = {r["id"]: r for r in self._get().json()}
        assert Decimal(rows[p_std.id]["method_cost"]) == Decimal("15.0000")
        assert rows[p_std.id]["method_cost"] == rows[p_std.id]["inventory_avg_cost"]

    def test_last_purchase_unit_costs_matches_method_unit_cost_and_ignores_provisional_and_future(self):
        from inventory.cogs_method import last_purchase_unit_costs, method_unit_cost

        as_of = datetime.date(2026, 6, 10)
        p1 = Product.objects.create(tenant=self.t_a, sku="LPUC-1", name_ar="أول")
        p2 = Product.objects.create(tenant=self.t_a, sku="LPUC-2", name_ar="ثان")
        p3 = Product.objects.create(tenant=self.t_a, sku="LPUC-3", name_ar="بلا شراء")

        self._make_purchase_layer(
            self.t_a, p1, qty=3, unit_cost=11, layer_date=datetime.date(2026, 6, 1),
        )
        self._make_purchase_layer(
            self.t_a, p1, qty=2, unit_cost=14, layer_date=datetime.date(2026, 6, 10),
        )
        # Provisional layer on same/later date must be ignored
        self._make_purchase_layer(
            self.t_a, p1, qty=1, unit_cost=99, layer_date=datetime.date(2026, 6, 10),
            is_provisional=True,
        )
        # Future layer beyond as_of must be ignored
        self._make_purchase_layer(
            self.t_a, p1, qty=1, unit_cost=88, layer_date=datetime.date(2026, 6, 11),
        )
        # Non-purchase movement must be ignored
        self._make_purchase_layer(
            self.t_a, p2, qty=5, unit_cost=50, layer_date=datetime.date(2026, 6, 5),
            reference_type="ADJUST_IN",
        )
        self._make_purchase_layer(
            self.t_a, p2, qty=5, unit_cost=22, layer_date=datetime.date(2026, 6, 4),
        )

        with CaptureQueriesContext(connection) as captured:
            batched = last_purchase_unit_costs(
                tenant_id=self.t_a.TenantID,
                product_ids=[p1.id, p2.id, p3.id],
                as_of=as_of,
            )

        assert len(captured) == 1
        for prod in (p1, p2, p3):
            expected = method_unit_cost(product=prod, method="last_purchase", as_of=as_of)
            assert batched.get(prod.id) == expected
        assert batched[p1.id] == Decimal("14.0000")
        assert batched[p2.id] == Decimal("22.0000")
        assert p3.id not in batched

    def test_m3_product_list_query_count_same_for_2_and_6_products(self):
        from sales.models import SalesSettings

        ss, _ = SalesSettings.objects.get_or_create(tenant=self.t_a)
        ss.cogs_cost_method = "last_purchase"
        ss.save(update_fields=["cogs_cost_method"])

        today = timezone.localdate()
        for i in range(6):
            p = Product.objects.create(
                tenant=self.t_a, sku=f"M3Q-{i}", name_ar=f"دفعة م3 {i}",
                standard_cost=Decimal("5.0000"),
            )
            self._make_purchase_layer(
                self.t_a, p, qty=4, unit_cost=10 + i, layer_date=today,
            )
        self._auth()

        with CaptureQueriesContext(connection) as two_q:
            two = self._get("?page=1&page_size=2")
        with CaptureQueriesContext(connection) as six_q:
            six = self._get("?page=1&page_size=6")

        assert len(two.json()["results"]) == 2
        assert len(six.json()["results"]) == 6
        assert "inventory_avg_cost" in six.json()["results"][0]
        assert "method_cost" in six.json()["results"][0]
        assert len(six_q) == len(two_q), [q["sql"] for q in six_q]

    def test_m3_product_fields_are_tenant_isolated_and_null_without_request(self):
        from inventory.serializers import ProductSerializer
        from sales.models import SalesSettings

        today = timezone.localdate()
        p_a = Product.objects.create(
            tenant=self.t_a, sku="ISO-A", name_ar="منتج أ", standard_cost=Decimal("9.0000"),
        )
        # Tenant A: 1 @ 10 + 1 @ 14 -> open-layer avg = 12, latest purchase = 14
        self._make_purchase_layer(
            self.t_a, p_a, qty=1, unit_cost=10,
            layer_date=today - datetime.timedelta(days=2),
        )
        self._make_purchase_layer(
            self.t_a, p_a, qty=1, unit_cost=14,
            layer_date=today - datetime.timedelta(days=1),
        )
        # Foreign tenant layer with a PURCHASE_INVOICE movement and LATER date than tenant A's purchase
        self._make_purchase_layer(
            self.t_b, p_a, qty=10, unit_cost=500,
            layer_date=today, reference_type="PURCHASE_INVOICE",
        )
        ss_b, _ = SalesSettings.objects.get_or_create(tenant=self.t_b)
        ss_b.cogs_cost_method = "standard"
        ss_b.save(update_fields=["cogs_cost_method"])

        ss_a, _ = SalesSettings.objects.get_or_create(tenant=self.t_a)
        ss_a.cogs_cost_method = "last_purchase"
        ss_a.save(update_fields=["cogs_cost_method"])

        self._auth()
        row = next(r for r in self._get().json() if r["id"] == p_a.id)
        assert Decimal(row["inventory_avg_cost"]) == Decimal("12.0000")
        assert Decimal(row["method_cost"]) == Decimal("14.0000")

        # No request in context -> null for the new computed fields, no exception
        no_ctx = ProductSerializer(p_a).data
        assert no_ctx["inventory_avg_cost"] is None
        assert no_ctx["method_cost"] is None

    def test_derived_avg_costs_matches_derived_avg_cost_and_scopes_to_tenant(self):
        from inventory.fifo import derived_avg_cost, derived_avg_costs

        p_layers = Product.objects.create(tenant=self.t_a, sku="DAC-1", name_ar="طبقات")
        p_frac = Product.objects.create(tenant=self.t_a, sku="DAC-2", name_ar="كسور")
        p_zero = Product.objects.create(tenant=self.t_a, sku="DAC-3", name_ar="صفر")
        p_other = Product.objects.create(tenant=self.t_b, sku="DAC-B", name_ar="شركة ب")

        self._make_purchase_layer(
            self.t_a, p_layers, qty=8, unit_cost=10, layer_date=datetime.date(2026, 6, 1),
        )
        self._make_purchase_layer(
            self.t_a, p_layers, qty=4, unit_cost=16, layer_date=datetime.date(2026, 6, 2),
        )
        self._make_purchase_layer(
            self.t_a, p_frac, qty="0.3333", unit_cost="1.0001", layer_date=datetime.date(2026, 6, 1),
        )
        self._make_purchase_layer(
            self.t_a, p_frac, qty=2, unit_cost=3, layer_date=datetime.date(2026, 6, 2),
        )
        self._make_purchase_layer(
            self.t_b, p_other, qty=5, unit_cost=50, layer_date=datetime.date(2026, 6, 2),
        )

        with CaptureQueriesContext(connection) as empty_q:
            assert derived_avg_costs(tenant_id=self.t_a.TenantID, product_ids=[]) == {}
        assert len(empty_q) == 0

        with CaptureQueriesContext(connection) as scoped_q:
            scoped = derived_avg_costs(
                tenant_id=self.t_a.TenantID,
                product_ids=[p_layers.id, p_frac.id, p_zero.id],
            )
        assert len(scoped_q) == 1
        assert scoped[p_layers.id] == derived_avg_cost(
            tenant_id=self.t_a.TenantID, product_id=p_layers.id,
        )
        assert scoped[p_frac.id] == derived_avg_cost(
            tenant_id=self.t_a.TenantID, product_id=p_frac.id,
        )
        assert p_zero.id not in scoped
        assert derived_avg_cost(tenant_id=self.t_a.TenantID, product_id=p_zero.id) == Decimal("0")

        with CaptureQueriesContext(connection) as all_q:
            all_tenant = derived_avg_costs(tenant_id=self.t_a.TenantID, product_ids=None)
        assert len(all_q) == 1
        assert set(all_tenant.keys()) == {p_layers.id, p_frac.id}
        assert p_other.id not in all_tenant

    def test_unscoped_product_serializer_caches_per_context_without_n_plus_1(self):
        from inventory.serializers import ProductSerializer
        from sales.models import SalesSettings

        ss, _ = SalesSettings.objects.get_or_create(tenant=self.t_a)
        ss.cogs_cost_method = "last_purchase"
        ss.save(update_fields=["cogs_cost_method"])

        today = timezone.localdate()
        created = []
        for i in range(6):
            p = Product.objects.create(
                tenant=self.t_a, sku=f"UNSC-{i}", name_ar=f"بلا نطاق {i}",
                standard_cost=Decimal("5.0000"),
            )
            self._make_purchase_layer(
                self.t_a, p, qty=4, unit_cost=10 + i, layer_date=today,
            )
            created.append(p)

        factory = APIRequestFactory()
        qs_two = Product.objects.filter(
            tenant=self.t_a, pk__in=[p.id for p in created[:2]],
        ).prefetch_related("price_tiers").order_by("id")
        qs_six = Product.objects.filter(
            tenant=self.t_a, pk__in=[p.id for p in created],
        ).prefetch_related("price_tiers").order_by("id")

        req_two = factory.get(PRODUCTS_URL, HTTP_X_TENANT_ID=str(self.t_a.TenantID))
        req_two.user = self.owner_a
        req_six = factory.get(PRODUCTS_URL, HTTP_X_TENANT_ID=str(self.t_a.TenantID))
        req_six.user = self.owner_a

        with CaptureQueriesContext(connection) as two_q:
            two_data = ProductSerializer(
                qs_two, many=True,
                context={
                    "request": req_two,
                    "product_attachments": {},
                    "serial_requirement_map": {},
                },
            ).data
        with CaptureQueriesContext(connection) as six_q:
            six_data = ProductSerializer(
                qs_six, many=True,
                context={
                    "request": req_six,
                    "product_attachments": {},
                    "serial_requirement_map": {},
                },
            ).data

        assert len(two_data) == 2
        assert len(six_data) == 6
        assert len(six_q) == len(two_q), [q["sql"] for q in six_q]

        req_scoped = factory.get(PRODUCTS_URL, HTTP_X_TENANT_ID=str(self.t_a.TenantID))
        req_scoped.user = self.owner_a
        scoped_data = ProductSerializer(
            qs_six, many=True,
            context={
                "request": req_scoped,
                "product_attachments": {},
                "serial_requirement_map": {},
                "last_purchase_price_product_ids": [p.id for p in created],
            },
        ).data
        unscoped_by_id = {r["id"]: r for r in six_data}
        scoped_by_id = {r["id"]: r for r in scoped_data}
        assert unscoped_by_id[created[0].id]["inventory_avg_cost"] == "10.0000"
        assert unscoped_by_id[created[0].id]["method_cost"] is not None
        for p in created:
            assert unscoped_by_id[p.id]["inventory_avg_cost"] == scoped_by_id[p.id]["inventory_avg_cost"]
            assert unscoped_by_id[p.id]["method_cost"] == scoped_by_id[p.id]["method_cost"]
