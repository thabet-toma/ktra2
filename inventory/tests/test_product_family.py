"""#20: كيان «المنتج» (`ProductFamily`) فوق «البراند» (`Product`).

تسجيل منتجٍ جديد — عبر أيّ مسارٍ من المسارين في الخادم — يُنشئ الأب وبراندَه
الضمنيّ معاً، ذرّياً، بلا تسريب براندٍ بلا أبٍ فوقه. وقاعدة التعايش: الحقول
«الأبوية» تُقرأ من الأب إن كان للبراند أب، وإلا من صفّه هو.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, ProductCategory, ProductFamily
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"
FAMILIES_URL = "/api/inventory/product-families/"


class ProductFamilyCreationTest(APITestCase):
    """المسار الأوّل: واجهة المنتجات (ProductViewSet.create)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="fam_a", password="x")
        cls.owner_b = User.objects.create_user(username="fam_b", password="x")
        cls.t_a = create_company("شركة الأب أ", cls.owner_a)
        cls.t_b = create_company("شركة الأب ب", cls.owner_b)
        cls.category_a = ProductCategory.objects.create(tenant=cls.t_a, name="إلكترونيات")

    def _auth(self, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.owner_a)
        self._tenant_id = str((tenant or self.t_a).TenantID)

    def _post(self, payload, tenant_id=None):
        return self.client.post(
            PRODUCTS_URL, payload, format="json",
            HTTP_X_TENANT_ID=tenant_id or self._tenant_id,
        )

    def _get(self, url, tenant_id=None):
        return self.client.get(url, HTTP_X_TENANT_ID=tenant_id or self._tenant_id)

    # ── 1) تسجيل منتجٍ جديد يُنشئ الأب وبراندَه الضمني معاً، ذرّياً ──
    def test_registering_a_product_creates_family_and_one_implicit_child(self):
        self._auth()
        res = self._post({
            "name_ar": "طابعة ليزر",
            "category": self.category_a.id,
            "min_stock_level": 5,
            "max_stock_level": 50,
            "is_serialized": True,
            "is_service": False,
        })
        assert res.status_code == 201, res.content[:300]
        data = res.json()

        assert ProductFamily.objects.filter(tenant=self.t_a).count() == 1
        assert Product.objects.filter(tenant=self.t_a).count() == 1

        product = Product.objects.get(pk=data["id"])
        assert product.family_id is not None
        family = product.family

        # الأب يحمل حقول #9 «على المنتج».
        assert family.name_ar == "طابعة ليزر"
        assert family.category_id == self.category_a.id
        assert family.min_stock_level == 5
        assert family.max_stock_level == 50
        assert family.is_serialized is True

        # الأب لا يحمل أي رقم — لا رصيد ولا تكلفة.
        assert not hasattr(family, "quantity_on_hand")
        assert not hasattr(family, "avg_cost")

        # النسخ الدفاعي على البراند الضمني: كل مستهلكٍ قائم يقرأ من صفّه مباشرةً.
        assert product.category_id == self.category_a.id
        assert product.min_stock_level == 5
        assert product.max_stock_level == 50
        assert product.is_serialized is True

    def test_registering_two_products_creates_two_independent_families(self):
        self._auth()
        first = self._post({"name_ar": "أوّل"}).json()
        second = self._post({"name_ar": "ثانٍ"}).json()
        assert Product.objects.get(pk=first["id"]).family_id != \
            Product.objects.get(pk=second["id"]).family_id
        assert ProductFamily.objects.filter(tenant=self.t_a).count() == 2

    # ── 3) عزل الشركات: قراءة أو إرفاق أب شركةٍ أخرى ممنوع ──
    def test_company_isolation_cannot_read_foreign_family(self):
        self._auth(user=self.owner_b, tenant=self.t_b)
        foreign = self._post({"name_ar": "منتج ب"}).json()
        foreign_family_id = Product.objects.get(pk=foreign["id"]).family_id

        self._auth(user=self.owner_a, tenant=self.t_a)
        res = self._get(f"{FAMILIES_URL}{foreign_family_id}/")
        assert res.status_code == 404

        listing = self._get(FAMILIES_URL).json()
        assert all(row["id"] != foreign_family_id for row in listing)

    def test_company_isolation_cannot_attach_to_foreign_family_on_create(self):
        """محاولة تهريب `family` أجنبي في حمولة التسجيل لا تُلحق المنتج به —
        الحقل غير قابلٍ للكتابة من العميل أصلاً؛ نقطة الإنشاء الموحّدة تصنع
        أباً جديداً تابعاً لشركة المستخدم دائماً."""
        self._auth(user=self.owner_b, tenant=self.t_b)
        foreign = self._post({"name_ar": "منتج ب"}).json()
        foreign_family_id = Product.objects.get(pk=foreign["id"]).family_id

        self._auth()
        res = self._post({"name_ar": "منتج أ", "family": foreign_family_id})
        assert res.status_code == 201, res.content[:300]
        product = Product.objects.get(pk=res.json()["id"])
        assert product.family_id != foreign_family_id
        assert product.family.tenant_id == self.t_a.pk


class ProductFamilyMaterializationTest(APITestCase):
    """المسار الثاني: تجسيد المنتج المبدئي في عرض السعر عند التحويل
    (`logistics.services.materialize_quotation_draft_parties`)."""

    @classmethod
    def setUpTestData(cls):
        from tenants.models import Currency

        cls.owner = User.objects.create_user(username="fam_quote", password="x")
        cls.tenant = create_company("شركة عروض الأسعار", cls.owner)
        cls.currency = Currency.objects.create(
            Code="FQC", Name="Family Quote Currency", IsBaseCurrency=False,
        )

        from partners.models import Partner
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد محلي", partner_type="Supplier",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _quotation_payload(self, **overrides):
        payload = {
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
                "name_snapshot": "منتجٌ لم يُسجَّل بعد",
                "quantity": "3.000",
                "unit_price": "12.5000",
            }],
        }
        payload.update(overrides)
        return payload

    def test_materialized_product_gets_a_family_too(self):
        created = self.client.post(
            "/api/logistics/supplier-quotations/",
            self._quotation_payload(), format="json",
        )
        assert created.status_code == 201, created.content[:300]
        quotation_id = created.data["id"]

        assert Product.objects.filter(tenant=self.tenant).count() == 0
        assert ProductFamily.objects.filter(tenant=self.tenant).count() == 0

        converted = self.client.post(
            f"/api/logistics/supplier-quotations/{quotation_id}/convert-to-purchase-order/",
            {}, format="json",
        )
        assert converted.status_code == 201, converted.content[:300]

        # مسار الإنشاء الثاني لا يُسرّب براندًا بلا أبٍ فوقه.
        assert Product.objects.filter(tenant=self.tenant).count() == 1
        assert ProductFamily.objects.filter(tenant=self.tenant).count() == 1

        product = Product.objects.get(tenant=self.tenant)
        assert product.name_ar == "منتجٌ لم يُسجَّل بعد"
        assert product.family_id is not None
        assert product.family.tenant_id == self.tenant.pk
        assert product.family.name_ar == "منتجٌ لم يُسجَّل بعد"


class ProductFamilyCoexistenceTest(APITestCase):
    """قاعدة التعايش (#20/#9): الحقل يُقرأ من الأب إن كان للبراند أب، وإلا من
    صفّ البراند نفسه — عبر `GET /products/<id>/profile/`."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fam_coexist", password="x")
        cls.tenant = create_company("شركة التعايش", cls.owner)
        cls.orphan_category = ProductCategory.objects.create(
            tenant=cls.tenant, name="تصنيف البراند نفسه",
        )
        cls.family_category = ProductCategory.objects.create(
            tenant=cls.tenant, name="تصنيف الأب",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.tenant_id = str(self.tenant.TenantID)

    def _profile(self, product_id):
        return self.client.get(
            f"{PRODUCTS_URL}{product_id}/profile/", HTTP_X_TENANT_ID=self.tenant_id,
        )

    # ── 4) صفّ بلا أبٍ يقرأ حقوله «الأبوية» من صفّه هو ──
    def test_orphan_child_resolves_from_its_own_columns(self):
        product = Product.objects.create(
            tenant=self.tenant, sku="ORPHAN-1", name_ar="براندٌ بلا أب",
            category=self.orphan_category, is_service=True, min_stock_level=9,
        )
        assert product.family_id is None

        res = self._profile(product.id)
        assert res.status_code == 200, res.content[:300]
        data = res.json()
        assert data["category"] == self.orphan_category.name
        assert data["is_service"] is True
        assert data["min_stock_level"] == 9

    def test_child_with_family_resolves_from_the_parent_not_its_own_columns(self):
        """البرهان الحاسم على القاعدة: قيمتا الأب والابن متعارضتان عمداً هنا،
        والقراءة يجب أن تنحاز للأب — لا لأنهما تصادفا متطابقتين."""
        family = ProductFamily.objects.create(
            tenant=self.tenant, name_ar="المنتج الأب",
            category=self.family_category, is_service=True, min_stock_level=20,
        )
        product = Product.objects.create(
            tenant=self.tenant, sku="LINKED-1", name_ar="براندٌ بأب",
            family=family,
            # قيمٌ مختلفة عمداً على صفّ البراند نفسه — يجب ألّا تظهر.
            category=self.orphan_category, is_service=False, min_stock_level=1,
        )

        res = self._profile(product.id)
        assert res.status_code == 200, res.content[:300]
        data = res.json()
        assert data["category"] == self.family_category.name
        assert data["is_service"] is True
        assert data["min_stock_level"] == 20


class ProductFamilyWriteDirectionTest(APITestCase):
    """مراجعة الالتزام: اتجاه الكتابة واحدٌ لا اثنان، والمنفذ لا يصنع أباً يتيماً."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fam_dir", password="x")
        cls.tenant = create_company("شركة اتجاه الكتابة", cls.owner)
        cls.cat_a = ProductCategory.objects.create(tenant=cls.tenant, name="تصنيف أ")
        cls.cat_b = ProductCategory.objects.create(tenant=cls.tenant, name="تصنيف ب")

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, payload):
        res = self.client.post(PRODUCTS_URL, payload, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"])

    def test_editing_the_brand_keeps_the_parent_mirror_in_step(self):
        """تعديل صفّ البراند يجرّ الأب معه — وإلا قرأ الكرت أباً متجمّداً على
        قيمة الإنشاء، فيعرض تصنيفاً قديماً بعد تعديله فعلاً."""
        from inventory.services import product_profile

        product = self._create({"name_ar": "منتج المرآة", "category": self.cat_a.id})
        assert product.family.category_id == self.cat_a.id

        res = self.client.patch(
            f"{PRODUCTS_URL}{product.id}/",
            {"category": self.cat_b.id, "is_service": True, "min_stock_level": 7},
            format="json", **self.hdr,
        )
        assert res.status_code in (200, 202), res.content[:300]

        product.refresh_from_db()
        assert product.family.category_id == self.cat_b.id
        assert product.family.is_service is True
        assert product.family.min_stock_level == 7

        profile = product_profile(tenant_id=self.tenant.TenantID, product_id=product.id)
        assert profile["category"] == "تصنيف ب"
        assert profile["is_service"] is True
        assert profile["min_stock_level"] == 7

    def test_the_parent_endpoint_is_read_only(self):
        """لا يُنشأ أبٌ وحده (منتجٌ بلا براندات حالةٌ لا مكان لها)، ولا يُكتب
        عليه مباشرةً فيتفرّع اتجاه كتابةٍ ثانٍ يترك القرّاء على قيمةٍ قديمة."""
        product = self._create({"name_ar": "منتج القراءة"})
        family_id = product.family_id

        assert self.client.get(FAMILIES_URL, **self.hdr).status_code == 200
        assert self.client.post(
            FAMILIES_URL, {"name_ar": "أبٌ يتيم"}, format="json", **self.hdr,
        ).status_code == 405
        assert self.client.patch(
            f"{FAMILIES_URL}{family_id}/", {"name_ar": "س"}, format="json", **self.hdr,
        ).status_code == 405
        assert self.client.delete(
            f"{FAMILIES_URL}{family_id}/", **self.hdr,
        ).status_code == 405


class ProductFamilyIntegrityTest(APITestCase):
    """ثغرتان كشفتهما المراجعة: كاتبٌ يتجاوز المرآة، وحذفٌ يترك أباً بلا أبناء."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fam_int", password="x")
        cls.tenant = create_company("شركة سلامة الأب", cls.owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, payload):
        res = self.client.post(PRODUCTS_URL, payload, format="json", **self.hdr)
        assert res.status_code == 201, res.content[:300]
        return Product.objects.get(pk=res.json()["id"])

    def test_bulk_writer_of_reorder_levels_carries_the_parent_with_it(self):
        """محرّك التجديد يكتب الحدّين بـ`bulk_update` — والقراءة تفضّل الأب،
        فبلا مزامنةٍ يعرض الكرت الحدَّ القديم بعد تطبيق الجديد بلا خطأٍ ظاهر."""
        from inventory.services import product_profile, sync_families_from_products

        product = self._create({"name_ar": "منتج الحدود", "min_stock_level": 2})
        assert product.family.min_stock_level == 2

        product.min_stock_level = 11
        product.max_stock_level = 40
        Product.objects.bulk_update([product], ["min_stock_level", "max_stock_level"])
        sync_families_from_products([product])

        product.refresh_from_db()
        assert product.family.min_stock_level == 11
        assert product.family.max_stock_level == 40
        profile = product_profile(tenant_id=self.tenant.TenantID, product_id=product.id)
        assert profile["min_stock_level"] == 11

    def test_deleting_the_last_brand_removes_its_parent(self):
        """«منتج بلا براندات» حالةٌ لا مكان لها — ولا شيء يشير إليها فتبقى يتيمة."""
        product = self._create({"name_ar": "منتج للحذف"})
        family_id = product.family_id
        assert ProductFamily.objects.filter(pk=family_id).exists()

        res = self.client.delete(f"{PRODUCTS_URL}{product.id}/", **self.hdr)
        assert res.status_code in (200, 204), res.content[:300]
        assert not ProductFamily.objects.filter(pk=family_id).exists()


class FamilyFieldsStayOneTruthTest(APITestCase):
    """الحقول «الأبوية» لا تتفرّق بين إخوةٍ تحت أبٍ واحد — تعديلٌ من أيّ صفّ يعمّ."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fam_truth", password="x")
        cls.tenant = create_company("شركة الحقيقة الواحدة", cls.owner)
        cls.cat = ProductCategory.objects.create(tenant=cls.tenant, name="تصنيف جديد")

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_renaming_from_one_brand_row_reaches_its_siblings(self):
        from inventory.services import add_brand_to_family, create_product_with_family

        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="اسم قديم")
        add_brand_to_family(family=family, brand_name="براند أول", tenant=self.tenant)
        second, created = add_brand_to_family(
            family=family, brand_name="براند ثانٍ", tenant=self.tenant)
        assert created is True

        res = self.client.patch(
            f"{PRODUCTS_URL}{first.id}/",
            {"name_ar": "اسم جديد", "category": self.cat.id},
            format="json", **self.hdr,
        )
        assert res.status_code in (200, 202), res.content[:300]

        family.refresh_from_db()
        second.refresh_from_db()
        assert family.name_ar == "اسم جديد"
        # الشقيق كان يبقى على الاسم القديم، فيعرض المنتقي اسمين للشيء نفسه.
        assert second.name_ar == "اسم جديد"
        assert second.category_id == self.cat.id
        # والبراند نفسه لا يُمَسّ — هو ما يميّز الصفَّين.
        assert second.brand == "براند ثانٍ"
        first.refresh_from_db()
        assert first.brand == "براند أول"
