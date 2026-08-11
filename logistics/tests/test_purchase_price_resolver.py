"""FEAT-1 — purchase line auto-pricing via the shared PriceResolver.

Covers strategy switching (LAST vs LOWEST), the fallback chain (history →
product avg_cost → blank), currency normalization, and the resolve-price
endpoint reading the active Purchase Setting.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.pricing import PriceStrategy, purchase_price_list, resolve_purchase_price
from inventory.models import Product
from logistics.models import (
    PurchaseInvoice,
    PurchaseInvoiceItem,
    PurchaseSettings,
)
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="ppr", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    usd = Currency.objects.create(Code="USD", Name="دولار")
    tenant = create_company("شركة تسعير الشراء", owner)
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد", partner_type="Supplier")
    product = Product.objects.create(
        tenant=tenant, sku="PPR-1", name_ar="صنف", quantity_on_hand=0, avg_cost=Decimal("0"))
    return tenant, ils, usd, supplier, product


def _posted_pi(tenant, supplier, currency, product, *, number, date, price,
               posted=True, exchange_rate="1"):
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, partner=supplier,
        currency=currency, invoice_date=date, exchange_rate=Decimal(exchange_rate),
        is_posted=posted)
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=product, name="صنف",
        quantity=Decimal("1"), unit_price=Decimal(str(price)),
        total_price=Decimal(str(price)))
    return inv


def test_last_purchase_picks_most_recent(env):
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=100)
    _posted_pi(tenant, sup, ils, product, number="P-2", date="2026-06-15", price=130)

    data = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE)
    assert Decimal(data["unit_price"]) == Decimal("130.0000")
    assert data["strategy_used"] == PriceStrategy.LAST_PURCHASE
    assert data["source"]["document_number"] == "P-2"


def test_lowest_purchase_picks_minimum(env):
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=100)
    _posted_pi(tenant, sup, ils, product, number="P-2", date="2026-06-15", price=130)
    _posted_pi(tenant, sup, ils, product, number="P-3", date="2026-06-20", price=80)

    data = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LOWEST_PURCHASE)
    assert Decimal(data["unit_price"]) == Decimal("80.0000")
    assert data["source"]["document_number"] == "P-3"


def test_draft_invoices_are_ignored(env):
    tenant, ils, _usd, sup, product = env
    # A cheaper DRAFT must not influence either strategy (A1: posted-only).
    _posted_pi(tenant, sup, ils, product, number="D-1", date="2026-06-20", price=5, posted=False)
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=100)

    last = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE)
    low = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LOWEST_PURCHASE)
    assert Decimal(last["unit_price"]) == Decimal("100.0000")
    assert Decimal(low["unit_price"]) == Decimal("100.0000")


def test_fallback_to_avg_cost_when_no_history(env):
    tenant, _ils, _usd, _sup, product = env
    product.avg_cost = Decimal("42")
    product.save(update_fields=["avg_cost"])
    data = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE)
    assert Decimal(data["unit_price"]) == Decimal("42.0000")
    assert data["strategy_used"] == PriceStrategy.DEFAULT
    assert data["source"]["document_type"] == "PRODUCT_AVG_COST"


def test_blank_when_no_history_and_no_cost(env):
    tenant, _ils, _usd, _sup, product = env
    data = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE)
    assert data["unit_price"] is None
    assert data["strategy_used"] is None


def test_currency_normalized_to_target_invoice_currency(env):
    tenant, _ils, usd, sup, product = env
    # History recorded in USD at rate 3.6 (1 USD = 3.6 base). Target invoice in
    # base currency (rate 1) → 10 USD becomes 36 base.
    _posted_pi(tenant, sup, usd, product, number="P-USD", date="2026-06-10",
               price=10, exchange_rate="3.6")
    data = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE, target_exchange_rate=Decimal("1"))
    assert Decimal(data["unit_price"]) == Decimal("36.0000")


def test_get_or_create_purchase_settings_default(env):
    tenant = env[0]
    ps = get_or_create_purchase_settings(tenant)
    assert ps.purchase_default_price_strategy == PurchaseSettings.STRATEGY_LAST_PURCHASE
    # idempotent
    assert get_or_create_purchase_settings(tenant).pk == ps.pk


def test_price_list_bulk_last_and_lowest(env):
    # القائمة المنسدلة تعرض «آخر شراء» و«أقل شراء» معاً دائماً، والقيمة الأساسية
    # (unit_price = ما تُعبَّأ به الخلية) هي **آخر** سعر بصرف النظر عن الاستراتيجية.
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=100)
    _posted_pi(tenant, sup, ils, product, number="P-2", date="2026-06-15", price=130)
    other = Product.objects.create(
        tenant=tenant, sku="PPR-2", name_ar="صنف٢", quantity_on_hand=0, avg_cost=Decimal("42"))

    result = purchase_price_list(tenant_id=tenant.TenantID)
    # الأساسي = آخر سعر (يُعبَّأ في الخلية)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("130.0000")
    assert result[product.id]["source_type"] == "PURCHASE_INVOICE"
    # الصنف بلا تاريخ شراء → متوسط التكلفة
    assert Decimal(result[other.id]["unit_price"]) == Decimal("42.0000")
    assert result[other.id]["source_type"] == "PRODUCT_AVG_COST"

    # prices تعرض آخر (130) وأقل (100) معاً للاطّلاع
    prices = {p["source_label"]: Decimal(p["unit_price"]) for p in result[product.id]["prices"]}
    assert prices.get("آخر شراء") == Decimal("130.0000")
    assert prices.get("أقل شراء") == Decimal("100.0000")

    # القيمة الأساسية آخر سعر حتى لو طُلبت استراتيجية «الأدنى» (لا تؤثّر على القائمة)
    low = purchase_price_list(tenant_id=tenant.TenantID, strategy=PriceStrategy.LOWEST_PURCHASE)
    assert Decimal(low[product.id]["unit_price"]) == Decimal("130.0000")


def test_price_list_ignores_drafts(env):
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="D-1", date="2026-06-20", price=5, posted=False)
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=100)
    out = purchase_price_list(tenant_id=tenant.TenantID, strategy=PriceStrategy.LOWEST_PURCHASE)
    assert Decimal(out[product.id]["unit_price"]) == Decimal("100.0000")


def test_price_list_last_is_supplier_scoped_lowest_is_global(env):
    # طلب المالك: «أقل شراء» عام لكل الموردين، و«آخر شراء» للمورد المحدد وحده.
    tenant, ils, _usd, sup_a, product = env
    sup_b = Partner.objects.create(tenant=tenant, name="مورد ب", partner_type="Supplier")
    _posted_pi(tenant, sup_a, ils, product, number="A-1", date="2026-06-01", price=100)
    _posted_pi(tenant, sup_b, ils, product, number="B-1", date="2026-06-15", price=80)

    out = purchase_price_list(tenant_id=tenant.TenantID, supplier_id=sup_a.id)
    prices = {p["source_label"]: Decimal(p["unit_price"]) for p in out[product.id]["prices"]}
    # آخر شراء = من المورد «أ» فقط (لا 80 الأحدث من المورد «ب»)
    assert prices.get("آخر شراء من المورد") == Decimal("100.0000")
    # أقل شراء = الأدنى عبر كل الموردين
    assert prices.get("أقل شراء") == Decimal("80.0000")
    # الخلية تُعبَّأ بآخر سعر للمورد نفسه
    assert Decimal(out[product.id]["unit_price"]) == Decimal("100.0000")


def test_price_list_falls_back_to_lowest_when_supplier_has_no_history(env):
    tenant, ils, _usd, sup_a, product = env
    sup_b = Partner.objects.create(tenant=tenant, name="مورد ب", partner_type="Supplier")
    _posted_pi(tenant, sup_a, ils, product, number="A-1", date="2026-06-01", price=100)

    out = purchase_price_list(tenant_id=tenant.TenantID, supplier_id=sup_b.id)
    labels = [p["source_label"] for p in out[product.id]["prices"]]
    assert "آخر شراء من المورد" not in labels
    assert Decimal(out[product.id]["unit_price"]) == Decimal("100.0000")


def test_resolve_last_purchase_scoped_to_supplier(env):
    tenant, ils, _usd, sup_a, product = env
    sup_b = Partner.objects.create(tenant=tenant, name="مورد ب", partner_type="Supplier")
    _posted_pi(tenant, sup_a, ils, product, number="A-1", date="2026-06-01", price=100)
    _posted_pi(tenant, sup_b, ils, product, number="B-1", date="2026-06-15", price=80)

    data = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE, supplier_id=sup_a.id)
    assert Decimal(data["unit_price"]) == Decimal("100.0000")
    assert data["source"]["document_number"] == "A-1"

    # بلا مورد → السلوك القديم (آخر شراء عبر كل الموردين)
    globl = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE)
    assert Decimal(globl["unit_price"]) == Decimal("80.0000")


def test_resolve_falls_back_to_lowest_when_supplier_has_no_history(env):
    tenant, ils, _usd, sup_a, product = env
    sup_b = Partner.objects.create(tenant=tenant, name="مورد ب", partner_type="Supplier")
    _posted_pi(tenant, sup_a, ils, product, number="A-1", date="2026-06-01", price=100)
    _posted_pi(tenant, sup_a, ils, product, number="A-2", date="2026-06-20", price=140)

    data = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE, supplier_id=sup_b.id)
    assert Decimal(data["unit_price"]) == Decimal("100.0000")
    assert data["strategy_used"] == PriceStrategy.LOWEST_PURCHASE


class PurchasePriceEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ppre", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة منفذ التسعير", cls.user)
        cls.sup = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PPRE-1", name_ar="صنف", avg_cost=Decimal("0"))
        _posted_pi(cls.tenant, cls.sup, cls.ils, cls.product,
                   number="P-1", date="2026-06-01", price=100)
        _posted_pi(cls.tenant, cls.sup, cls.ils, cls.product,
                   number="P-3", date="2026-06-10", price=80)   # lowest, mid-date
        _posted_pi(cls.tenant, cls.sup, cls.ils, cls.product,
                   number="P-2", date="2026-06-20", price=130)  # newest

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_endpoint_uses_active_strategy_and_switches(self):
        # default = LAST_PURCHASE → 130
        res = self.client.get(
            f"/api/logistics/purchase-invoices/resolve-price/?product={self.product.id}",
            **self._auth())
        assert res.status_code == 200, res.content
        assert Decimal(res.json()["unit_price"]) == Decimal("130.0000")

        # switch the setting to LOWEST_PURCHASE → 80
        res = self.client.patch(
            "/api/logistics/purchase-settings/current/",
            {"purchase_default_price_strategy": "LOWEST_PURCHASE"},
            format="json", **self._auth())
        assert res.status_code == 200, res.content

        res = self.client.get(
            f"/api/logistics/purchase-invoices/resolve-price/?product={self.product.id}",
            **self._auth())
        assert Decimal(res.json()["unit_price"]) == Decimal("80.0000")

    def test_price_list_endpoint_returns_bulk_map(self):
        # task24: bulk endpoint feeds the dropdown — default LAST_PURCHASE → 130.
        res = self.client.get(
            "/api/logistics/purchase-invoices/price-list/", **self._auth())
        assert res.status_code == 200, res.content
        row = next(r for r in res.json() if r["product_id"] == self.product.id)
        assert Decimal(row["unit_price"]) == Decimal("130.0000")
        assert row["source_label"] == "آخر شراء"

    def test_price_list_endpoint_scopes_last_to_supplier(self):
        # ?supplier= يحصر «آخر شراء» بذلك المورد ويُبقي «أقل شراء» عاماً.
        other = Partner.objects.create(
            tenant=self.tenant, name="مورد ب", partner_type="Supplier")
        _posted_pi(self.tenant, other, self.ils, self.product,
                   number="B-1", date="2026-07-01", price=60)  # الأحدث والأقل — مورد آخر
        res = self.client.get(
            f"/api/logistics/purchase-invoices/price-list/?supplier={self.sup.id}",
            **self._auth())
        assert res.status_code == 200, res.content
        row = next(r for r in res.json() if r["product_id"] == self.product.id)
        assert Decimal(row["unit_price"]) == Decimal("130.0000")
        prices = {p["source_label"]: Decimal(p["unit_price"]) for p in row["prices"]}
        assert prices.get("آخر شراء من المورد") == Decimal("130.0000")
        assert prices.get("أقل شراء") == Decimal("60.0000")
