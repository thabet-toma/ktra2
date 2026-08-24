"""T-ITEMS M5 — الحقول التي كانت تُعرض ولا تُحفظ.

شرائح الأسعار وتجاوزات الحسابات والوحدات الإضافية كانت في كرت الصنف حقولاً
يملؤها المستخدم ويقرأ «تم الحفظ» ثم لا يجد شيئاً: لا نقطة تكتبها. الشرائح
خصوصاً ليست زينة — `core/pricing.py` يقرأ شريحة البيع الأولى كمصدرٍ للسعر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from inventory.models import Product, ProductPriceTier, UnitOfMeasure
from tenants.models import Currency
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class ProductRealFieldsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="tiers_a", password="x")
        cls.owner_b = User.objects.create_user(username="tiers_b", password="x")
        cls.t_a = create_company("شركة الشرائح أ", cls.owner_a)
        cls.t_b = create_company("شركة الشرائح ب", cls.owner_b)
        cls.currency = Currency.objects.filter(IsBaseCurrency=True).first() \
            or Currency.objects.first()

    def setUp(self):
        self.client.force_authenticate(user=self.owner_a)
        self._tenant_id = str(self.t_a.TenantID)

    def _post(self, payload):
        return self.client.post(PRODUCTS_URL, payload, format="json",
                                HTTP_X_TENANT_ID=self._tenant_id)

    def _patch(self, pk, payload):
        return self.client.patch(f"{PRODUCTS_URL}{pk}/", payload, format="json",
                                 HTTP_X_TENANT_ID=self._tenant_id)

    def _get(self, pk):
        return self.client.get(f"{PRODUCTS_URL}{pk}/", HTTP_X_TENANT_ID=self._tenant_id)

    # ── شرائح الأسعار ──
    def test_price_tiers_round_trip(self):
        res = self._post({
            "name_ar": "صنف بشرائح",
            "price_tiers": [
                {"tier_type": "sale", "tier_number": 1, "price": "100",
                 "currency": self.currency.pk, "tax_inclusive": False},
                {"tier_type": "purchase", "tier_number": 1, "price": "60",
                 "currency": self.currency.pk, "tax_inclusive": True},
            ],
        })
        assert res.status_code == 201, res.content[:400]
        pid = res.json()["id"]
        assert ProductPriceTier.objects.filter(product_id=pid).count() == 2

        body = self._get(pid).json()
        tiers = {(t["tier_type"], t["tier_number"]): t for t in body["price_tiers"]}
        assert Decimal(tiers[("sale", 1)]["price"]) == Decimal("100")
        assert tiers[("purchase", 1)]["tax_inclusive"] is True

    def test_resaving_updates_in_place_and_does_not_duplicate(self):
        pid = self._post({
            "name_ar": "صنف",
            "price_tiers": [{"tier_type": "sale", "tier_number": 1, "price": "100",
                             "currency": self.currency.pk}],
        }).json()["id"]

        res = self._patch(pid, {
            "price_tiers": [{"tier_type": "sale", "tier_number": 1, "price": "125",
                             "currency": self.currency.pk}],
        })
        assert res.status_code in (200, 202), res.content[:400]
        rows = ProductPriceTier.objects.filter(product_id=pid)
        assert rows.count() == 1, "قيد التفرّد هو المفتاح — لا شريحة مكرّرة"
        assert rows.first().price == Decimal("125")

    def test_omitting_tiers_keeps_them_but_empty_list_clears(self):
        pid = self._post({
            "name_ar": "صنف",
            "price_tiers": [{"tier_type": "sale", "tier_number": 1, "price": "100",
                             "currency": self.currency.pk}],
        }).json()["id"]

        # تعديلٌ لا يذكر الشرائح لا يمسّها (وإلا مسح كلُّ تغيير اسمٍ الشرائح).
        assert self._patch(pid, {"name_ar": "اسم جديد"}).status_code in (200, 202)
        assert ProductPriceTier.objects.filter(product_id=pid).count() == 1

        # قائمةٌ فارغة صريحة = امسح.
        assert self._patch(pid, {"price_tiers": []}).status_code in (200, 202)
        assert ProductPriceTier.objects.filter(product_id=pid).count() == 0

    def test_sale_tier_reaches_the_pricing_engine(self):
        """الشريحة ليست حقلاً مخزَّناً فحسب — المحرّك يقرؤها فعلاً."""
        from core.pricing import resolve_sales_price

        pid = self._post({
            "name_ar": "صنف مسعَّر بالشريحة",
            "price_tiers": [{"tier_type": "sale", "tier_number": 1, "price": "77",
                             "currency": self.currency.pk}],
        }).json()["id"]

        resolved = resolve_sales_price(
            tenant_id=self.t_a.TenantID, product_id=pid, customer_id=None,
        )
        assert Decimal(str(resolved["unit_price"])) == Decimal("77"), resolved

    # ── تجاوزات الحسابات ──
    def test_account_overrides_round_trip(self):
        account = Account.objects.filter(tenant=self.t_a).first()
        assert account is not None, "الشركة الجديدة تأتي بشجرة حسابات"
        pid = self._post({"name_ar": "صنف بحساب"}).json()["id"]

        res = self._patch(pid, {"sale_account_override": account.pk})
        assert res.status_code in (200, 202), res.content[:400]
        assert Product.objects.get(pk=pid).sale_account_override_id == account.pk

    def test_foreign_account_override_rejected(self):
        foreign = Account.objects.filter(tenant=self.t_b).first()
        assert foreign is not None
        pid = self._post({"name_ar": "صنف"}).json()["id"]

        res = self._patch(pid, {"sale_account_override": foreign.pk})
        assert res.status_code == 400, res.content[:400]
        assert "غير موجود لهذه الشركة" in str(res.json())
        assert Product.objects.get(pk=pid).sale_account_override_id is None

    # ── الوحدات الإضافية والوصف والموقع ──
    def test_extra_units_description_and_location_are_saved(self):
        box = UnitOfMeasure.objects.create(code="BOX", name_ar="كرتونة", name_en="Box")
        pid = self._post({"name_ar": "صنف"}).json()["id"]

        res = self._patch(pid, {
            "uom2": box.pk, "uom2_factor": "12",
            "description": "بيان داخلي", "storage_location": "رفّ A-3",
        })
        assert res.status_code in (200, 202), res.content[:400]
        product = Product.objects.get(pk=pid)
        assert product.uom2_id == box.pk
        assert product.uom2_factor == Decimal("12")
        assert product.description == "بيان داخلي"
        assert product.storage_location == "رفّ A-3"

    def test_item_card_full_payload_loses_nothing(self):
        """حارس الصنف الذي كان يكذب: حمولة الكرت كاملةً تعود كما أُرسلت.

        العطل الأصلي لم يكن في حقلٍ بعينه بل في **صمت** DRF: أي مفتاح خارج
        `Meta.fields` يُرمى بلا خطأ، فتقول الشاشة «تم الحفظ» ولا شيء حُفظ. هذا
        الاختبار يرسل ما يرسله كرت الصنف فعلاً ويقارن الوارد بالصادر حقلاً حقلاً.
        """
        box = UnitOfMeasure.objects.create(code="BX2", name_ar="صندوق", name_en="Box")
        piece = UnitOfMeasure.objects.create(code="PC2", name_ar="حبة", name_en="Piece")
        account = Account.objects.filter(tenant=self.t_a).first()

        payload = {
            "name_ar": "صنف الكرت الكامل", "name_en": "Full card item",
            "brand": "روك بيلد", "variant_group": "195/65/15",
            "min_stock_level": 5, "max_stock_level": 50,
            "sale_price": 199.5,
            "barcode": None, "is_serialized": False, "is_service": False,
            "warranty_months": 12, "supplier_warranty_months": 24,
            "uom_id": piece.pk,
            "uom2": box.pk, "uom2_factor": "12",
            "description": "بيان داخلي", "storage_location": "A-3",
            "sale_account_override": account.pk,
            "price_tiers": [
                {"tier_type": "sale", "tier_number": 1, "price": "199.5",
                 "currency": self.currency.pk, "tax_inclusive": False},
            ],
        }
        created = self._post(payload)
        assert created.status_code == 201, created.content[:400]
        body = self._get(created.json()["id"]).json()

        assert body["name_ar"] == "صنف الكرت الكامل"
        assert body["brand"] == "روك بيلد"
        assert body["uom_id"] == piece.pk
        assert body["uom_name"] == "حبة"
        assert body["uom2"] == box.pk
        assert Decimal(body["uom2_factor"]) == Decimal("12")
        assert body["description"] == "بيان داخلي"
        assert body["storage_location"] == "A-3"
        assert body["sale_account_override"] == account.pk
        assert body["warranty_months"] == 12
        assert len(body["price_tiers"]) == 1
        # «النوع» يُنشئ تصنيفَ مجموعةٍ خادمياً (task31) — والصنف يبقى داخله.
        assert body["variant_group"] == "195/65/15"

    def test_internal_description_is_separate_from_store_description(self):
        """وصف المتجر يراه العالم؛ البيان الداخلي لا — فلا يدوس أحدهما الآخر."""
        pid = self._post({
            "name_ar": "صنف",
            "description": "ملاحظة داخلية",
            "online_description": "نصّ التسويق",
        }).json()["id"]
        product = Product.objects.get(pk=pid)
        assert product.description == "ملاحظة داخلية"
        assert product.online_description == "نصّ التسويق"
