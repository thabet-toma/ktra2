"""تجميع البراندات: المنتجات بنفس المقاس/الأساس (مثل عجل 185/65/14) تُجمَّع تحت
عقدة أب واحدة، والكرت المجمّع يجمع مؤشّرات كل البراندات. مصدر التجميع group_key
(مقاس الإطار من الاسم، وإلا الاسم) — فيعمل على البيانات القائمة بلا هجرة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product
from inventory.services import (
    product_display_name,
    product_group_key,
    product_group_profile,
    record_stock_movement,
    tire_size_key,
)
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="bg", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة العجل", owner)
    from accounting.services import create_fiscal_year
    create_fiscal_year(tenant, 2026)
    return tenant


def test_tire_size_key_extraction():
    assert tire_size_key("185/65/14 روك بيلد") == "185/65/14"
    assert tire_size_key("عجل 31/10.5/15") == "31/10.5/15"
    # ليس مقاساً: تاريخ أو رقم عادي
    assert tire_size_key("فاتورة 12/5/2024") is None
    assert tire_size_key("زيت محرك 5W30") is None


def test_group_key_groups_same_size_different_brands(env):
    """براندان مختلفان بنفس المقاس ⇒ نفس group_key (يتجمّعان)."""
    p1 = Product.objects.create(tenant=env, sku="T-1", name_ar="185/65/14", brand="روك بيلد")
    p2 = Product.objects.create(tenant=env, sku="T-2", name_ar="185/65/14", brand="جلاكسي")
    # صنف عادي بلا مقاس ⇒ مفتاحه اسمه
    p3 = Product.objects.create(tenant=env, sku="O-1", name_ar="زيت محرك")
    assert product_group_key(p1) == product_group_key(p2) == "185/65/14"
    assert product_group_key(p3) == "زيت محرك"


def test_group_key_works_on_legacy_embedded_names(env):
    """البيانات القائمة (البراند داخل الاسم) تتجمّع تلقائياً بلا هجرة."""
    p1 = Product.objects.create(tenant=env, sku="L-1", name_ar="255/65/15 روك بيلد")
    p2 = Product.objects.create(tenant=env, sku="L-2", name_ar="255/65/15 جلاكسي")
    assert product_group_key(p1) == product_group_key(p2) == "255/65/15"


def test_group_key_falls_back_to_brand(env):
    """منتجان بنفس البراند (بلا مجموعة صريحة ولا مقاس) يتجمّعان بالبراند."""
    p1 = Product.objects.create(tenant=env, sku="BR-1", name_ar="بطارية ضفة", brand="مايكل")
    p2 = Product.objects.create(tenant=env, sku="BR-2", name_ar="فتحي", brand="مايكل")
    assert product_group_key(p1) == product_group_key(p2) == "مايكل"
    # المجموعة الصريحة تتقدّم على البراند
    p3 = Product.objects.create(tenant=env, sku="BR-3", name_ar="x", brand="مايكل", variant_group="رف A")
    assert product_group_key(p3) == "رف A"


def test_display_name_appends_brand_in_parens(env):
    p = Product.objects.create(tenant=env, sku="D-1", name_ar="185/65/14", brand="روك بيلد")
    assert product_display_name(p) == "185/65/14 (روك بيلد)"
    # البراند مذكور أصلاً ⇒ لا تكرار
    p2 = Product.objects.create(tenant=env, sku="D-2", name_ar="185/65/14 جلاكسي", brand="جلاكسي")
    assert product_display_name(p2) == "185/65/14 جلاكسي"


def test_explicit_variant_group_overrides_and_flags(env):
    """المجموعة الصريحة تصير مفتاح التجميع ويظهر مجلّدها حتى لمنتج واحد."""
    from inventory.services import product_has_explicit_group
    # اسم وصفي فريد (لا مقاس) + مجموعة صريحة
    p = Product.objects.create(
        tenant=env, sku="V-1", name_ar="انفيرتر 11 كيلو واط", brand="SMH",
        variant_group="انفيرتر 11")
    assert product_group_key(p) == "انفيرتر 11"   # الصريح يتقدّم على الاسم
    assert product_has_explicit_group(p) is True
    # بلا مجموعة صريحة ⇒ احتياطي الاسم
    p2 = Product.objects.create(tenant=env, sku="V-2", name_ar="انفيرتر 11 كيلو واط")
    assert product_group_key(p2) == "انفيرتر 11 كيلو واط"
    assert product_has_explicit_group(p2) is False


def test_group_profile_aggregates_brands(env):
    """الكرت المجمّع = مجموع مخزون البراندين."""
    p1 = Product.objects.create(tenant=env, sku="G-1", name_ar="185/65/14", brand="روك بيلد")
    p2 = Product.objects.create(tenant=env, sku="G-2", name_ar="185/65/14", brand="جلاكسي")
    record_stock_movement(
        product=p1, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("100"), movement_date="2026-06-01", tenant=env)
    record_stock_movement(
        product=p2, movement_type="IN", quantity=Decimal("5"),
        unit_cost=Decimal("100"), movement_date="2026-06-01", tenant=env)

    prof = product_group_profile(tenant_id=env.TenantID, product_ids=[p1.id, p2.id])
    assert prof["name"] == "185/65/14"
    assert prof["member_count"] == 2
    assert Decimal(prof["quantity_on_hand"]) == Decimal("15")  # 10 + 5
    assert Decimal(prof["inventory_valuation"]) == Decimal("1500.00")
    brands = {m["brand"] for m in prof["members"]}
    assert brands == {"روك بيلد", "جلاكسي"}


def test_group_profile_isolates_tenant(env):
    """تمرير معرّف من شركة أخرى لا يُسرّب بياناتها."""
    other_owner = User.objects.create_user(username="bg2", password="x")
    other = create_company("شركة أخرى", other_owner)
    mine = Product.objects.create(tenant=env, sku="M-1", name_ar="185/65/14", brand="أ")
    theirs = Product.objects.create(tenant=other, sku="X-1", name_ar="185/65/14", brand="ب")
    prof = product_group_profile(tenant_id=env.TenantID, product_ids=[mine.id, theirs.id])
    assert prof["member_count"] == 1  # فقط منتج شركتي


class BrandGroupingEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="bge", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة كرت", cls.user)
        cls.p1 = Product.objects.create(
            tenant=cls.tenant, sku="E-1", name_ar="185/65/14", brand="روك بيلد")
        cls.p2 = Product.objects.create(
            tenant=cls.tenant, sku="E-2", name_ar="185/65/14", brand="جلاكسي")
        record_stock_movement(
            product=cls.p1, movement_type="IN", quantity=Decimal("3"),
            unit_cost=Decimal("100"), movement_date="2026-06-01", tenant=cls.tenant)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_serializer_exposes_group_fields(self):
        r = self.client.get(f"/api/inventory/products/{self.p1.id}/", **self._auth())
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["group_key"] == "185/65/14"
        assert body["display_name"] == "185/65/14 (روك بيلد)"
        assert body["brand"] == "روك بيلد"

    def test_group_profile_endpoint(self):
        r = self.client.get(
            f"/api/inventory/products/group-profile/?ids={self.p1.id},{self.p2.id}",
            **self._auth())
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["name"] == "185/65/14"
        assert body["member_count"] == 2
        assert Decimal(body["quantity_on_hand"]) == Decimal("3")

    def test_brands_endpoint_lists_distinct(self):
        r = self.client.get("/api/inventory/products/brands/", **self._auth())
        assert r.status_code == 200, r.content
        assert r.json() == ["جلاكسي", "روك بيلد"]  # مميّزة ومرتّبة

    def test_groups_endpoint_lists_distinct(self):
        Product.objects.create(tenant=self.tenant, sku="GR-1", name_ar="ا", variant_group="انفيرتر 11")
        r = self.client.get("/api/inventory/products/groups/", **self._auth())
        assert r.status_code == 200, r.content
        assert r.json() == ["انفيرتر 11"]

    def test_names_endpoint_lists_distinct(self):
        # اسمان مميّزان (p1/p2 بنفس الاسم «185/65/14») ⇒ اسم واحد.
        r = self.client.get("/api/inventory/products/names/", **self._auth())
        assert r.status_code == 200, r.content
        assert r.json() == ["185/65/14"]

    def test_group_ledger_endpoint(self):
        r = self.client.get(
            f"/api/inventory/products/group-ledger/?ids={self.p1.id},{self.p2.id}",
            **self._auth())
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["count"] == 1
        assert body["results"][0]["product_name"] == "185/65/14 (روك بيلد)"
