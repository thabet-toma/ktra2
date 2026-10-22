"""#20: كيان «المنتج» (`ProductFamily`) فوق «البراند» (`Product`).

تسجيل منتجٍ جديد — عبر أيّ مسارٍ من المسارين في الخادم — يُنشئ الأب وبراندَه
الضمنيّ معاً، ذرّياً، بلا تسريب براندٍ بلا أبٍ فوقه. وقاعدة التعايش: الحقول
«الأبوية» تُقرأ من الأب إن كان للبراند أب، وإلا من صفّه هو.
"""
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
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
        # ISSUE #117: هذا الاختبار يحوّل عرضاً إلى طلبية شراء — الإعداد الجديد
        # مطفأ افتراضاً، فيلزم إشعاله هنا كي يبقى الملف يختبر ما صُمّم لاختباره.
        from logistics.services import get_or_create_purchase_settings
        ps = get_or_create_purchase_settings(cls.tenant)
        ps.use_purchase_orders = True
        ps.save(update_fields=["use_purchase_orders"])

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
        cls.other_owner = User.objects.create_user(username="fam_truth_other", password="x")
        cls.other_tenant = create_company("شركة أخرى للحقيقة الواحدة", cls.other_owner)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _foreign_brand_pointing_at(self, family, intruder=None):
        """صفٌّ لشركةٍ أخرى تلف مفتاح أبيه فأشار إلى أب هذه الشركة — يدوياً
        بـ`.update()` كما يحدث في القاعدة فعلاً (لا يفلتر المفتاحَ الأجنبيّ).

        `intruder` لمن يُنشأ قبل العائلة فيأخذ معرّفاً أصغر من برانداتها.
        """
        intruder = intruder or Product.objects.create(
            tenant=self.other_tenant, sku="FOREIGN-1", name_ar="اسم الشركة الأخرى")
        Product.objects.filter(pk=intruder.pk).update(family_id=family.pk)
        intruder.refresh_from_db()
        return intruder

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

    def test_family_sync_never_writes_into_another_companys_brand(self):
        """صفٌّ فاسدٌ من شركةٍ أخرى يشير إلى أب هذه الشركة لا ينزل عليه اسمُها.

        لا مسار API يصل إلى عائلةٍ عبر شركتين اليوم، لكن صفّاً واحداً تلف مفتاحه
        كان يكفي لينزل عليه اسمُ هذه الشركة وتصنيفُها وحساباتها — فيصير صفَّ
        الشركة الأخرى ببيانات شركةٍ لا تخصّه، بلا خطأٍ ظاهر.
        """
        from inventory.services import (
            add_brand_to_family, create_product_with_family, sync_family_from_product,
        )

        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="اسم قديم")
        add_brand_to_family(family=family, brand_name="براند أول", tenant=self.tenant)
        sibling, created = add_brand_to_family(
            family=family, brand_name="براند ثانٍ", tenant=self.tenant)
        assert created is True
        intruder = self._foreign_brand_pointing_at(family)

        first.name_ar = "اسم جديد"
        assert sync_family_from_product(first) is True

        sibling.refresh_from_db()
        intruder.refresh_from_db()
        assert sibling.name_ar == "اسم جديد"
        assert intruder.name_ar == "اسم الشركة الأخرى"

    def test_batch_family_sync_never_writes_into_another_companys_brand(self):
        """نفس الحارس على النسخة الدفعة (`sync_families_from_products`)."""
        from inventory.services import (
            add_brand_to_family, create_product_with_family, sync_families_from_products,
        )

        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="منتج الحدود")
        add_brand_to_family(family=family, brand_name="براند أول", tenant=self.tenant)
        sibling, created = add_brand_to_family(
            family=family, brand_name="براند ثانٍ", tenant=self.tenant)
        assert created is True
        intruder = self._foreign_brand_pointing_at(family)

        first.min_stock_level = 9
        first.save(update_fields=["min_stock_level"])
        sync_families_from_products([first])

        sibling.refresh_from_db()
        intruder.refresh_from_db()
        assert sibling.min_stock_level == 9
        assert intruder.min_stock_level is None

    def test_sync_from_a_foreign_brand_writes_nothing_and_returns_false(self):
        """براندٌ من شركةٍ أخرى يُزامَن فلا يكتب شيئاً — لا على أبينا ولا على إخوته.

        لا مسار API يمنع تعديل صفٍّ فاسدٍ كُتب مفتاحُ أبيه يدوياً، فتمريره إلى
        `sync_family_from_product` كان ينزل باسمه وحدّه على أبٍ ليس له.
        """
        from inventory.services import (
            add_brand_to_family, create_product_with_family, sync_family_from_product,
        )

        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="اسم عائلتنا")
        add_brand_to_family(family=family, brand_name="براند أول", tenant=self.tenant)
        intruder = self._foreign_brand_pointing_at(family)

        intruder.name_ar = "اسم الدخيل"
        intruder.min_stock_level = 99
        assert sync_family_from_product(intruder) is False

        family.refresh_from_db()
        first.refresh_from_db()
        assert family.name_ar == "اسم عائلتنا"
        assert family.min_stock_level is None
        assert first.name_ar == "اسم عائلتنا"
        assert first.min_stock_level is None

    def test_batch_sync_skips_the_foreign_row_and_still_processes_ours(self):
        """الدفعة تُسقط صفَّ الشركة الأخرى من الكتابة ولا تُسقط بقية الدفعة."""
        from inventory.services import (
            add_brand_to_family, create_product_with_family, sync_families_from_products,
        )

        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="اسم عائلتنا")
        add_brand_to_family(family=family, brand_name="براند أول", tenant=self.tenant)
        sibling, created = add_brand_to_family(
            family=family, brand_name="براند ثانٍ", tenant=self.tenant)
        assert created is True
        intruder = self._foreign_brand_pointing_at(family)

        first.min_stock_level = 7
        first.save(update_fields=["min_stock_level"])
        intruder.name_ar = "اسم الدخيل"
        intruder.min_stock_level = 99
        intruder.save(update_fields=["name_ar", "min_stock_level"])

        sync_families_from_products([intruder, first])

        family.refresh_from_db()
        sibling.refresh_from_db()
        intruder.refresh_from_db()
        assert family.name_ar == "اسم عائلتنا"
        assert family.min_stock_level == 7
        assert sibling.name_ar == "اسم عائلتنا"
        assert sibling.min_stock_level == 7
        assert intruder.name_ar == "اسم الدخيل"
        assert intruder.min_stock_level == 99

    def test_add_brand_rejects_a_tenant_that_is_not_the_familys(self):
        """شركةٌ مفروضةٌ تخالف شركة الأب تُرفض قبل أي استعلامٍ أو كتابة."""
        from inventory.services import add_brand_to_family, create_product_with_family

        family, _first = create_product_with_family(
            tenant=self.tenant, name_ar="منتج محروس")
        add_brand_to_family(family=family, brand_name="براند أول", tenant=self.tenant)
        before_family = Product.objects.filter(family=family).count()
        before_other = Product.objects.filter(tenant=self.other_tenant).count()

        # العدّاد خارج `assertRaises` عمداً: `assertNumQueries` لا يفحص متى
        # خرج استثناءٌ من جسمه — و`assertRaises` لا يستعلم فالتغطية للنداء وحده.
        with self.assertNumQueries(0):
            with self.assertRaises(ValidationError) as ctx:
                add_brand_to_family(
                    family=family, brand_name="براند غريب", tenant=self.other_tenant)

        assert ctx.exception.messages == ['البراند والمنتج من شركتين مختلفتين.']
        assert Product.objects.filter(family=family).count() == before_family
        assert Product.objects.filter(tenant=self.other_tenant).count() == before_other

    def test_add_brand_names_our_implicit_row_despite_a_foreign_row_under_our_family(self):
        """«البراند الضمنيّ» يُبحث عنه في شركتنا وحدها: صفٌّ دخيلٌ بمعرّفٍ أصغر
        كان يُعدّ فيُسقِط الحالة إلى إنشاء صفٍّ جديد، أو يُسمَّى هو لو اقتصر
        الاختيار على أوّل صفّ بلا فلتر شركة."""
        from inventory.services import add_brand_to_family, create_product_with_family

        # الدخيل يُنشأ أولاً فيأخذ معرّفاً أصغر من براندنا، ثم يُوجَّه إلى أبينا.
        foreign = Product.objects.create(
            tenant=self.other_tenant, sku="FOREIGN-1", name_ar="اسم الشركة الأخرى")
        family, own = create_product_with_family(
            tenant=self.tenant, name_ar="منتج بلا براند")
        foreign = self._foreign_brand_pointing_at(family, intruder=foreign)
        assert foreign.pk < own.pk

        product, created = add_brand_to_family(
            family=family, brand_name="البراند الأول", tenant=self.tenant)

        assert created is False
        assert product.pk == own.pk
        own.refresh_from_db()
        foreign.refresh_from_db()
        assert own.brand == "البراند الأول"
        assert (foreign.brand or "") == ""
        assert Product.objects.filter(family=family).count() == 2


class ProductFamilySearchTest(APITestCase):
    """منتقي «المنتج» في التقارير يبحث في الخادم — لا ينزّل الكتالوج كلّه ليكتب
    حرفاً. البحث على الاسمين، ومقيَّدٌ بالشركة كبقية `get_queryset`."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="fam_search", password="x")
        cls.outsider = User.objects.create_user(username="fam_search_out", password="x")
        cls.tenant = create_company("شركة البحث", cls.owner)
        cls.other_tenant = create_company("شركة البحث الأخرى", cls.outsider)
        from inventory.services import create_product_with_family

        cls.family, _ = create_product_with_family(
            tenant=cls.tenant, name_ar="مقاس 195/85/15", sku="FAM-195")
        cls.other_family, _ = create_product_with_family(
            tenant=cls.tenant, name_ar="مقاس 205/55/16", sku="FAM-205")
        cls.foreign_family, _ = create_product_with_family(
            tenant=cls.other_tenant, name_ar="مقاس 195/85/15 الجار", sku="FAM-GAR")

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_search_narrows_to_the_matching_family_only(self):
        res = self.client.get(f"{FAMILIES_URL}?search=205", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        ids = {row["id"] for row in res.json()}
        assert ids == {self.other_family.id}

    def test_search_never_returns_another_company_family(self):
        res = self.client.get(f"{FAMILIES_URL}?search=195", **self.hdr)
        assert res.status_code == 200, res.content[:300]
        ids = {row["id"] for row in res.json()}
        assert self.family.id in ids
        assert self.foreign_family.id not in ids
