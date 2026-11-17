"""FEAT-1 — purchase line auto-pricing via the shared PriceResolver.

Covers strategy switching (LAST vs LOWEST), the fallback chain (history →
product avg_cost → blank), currency normalization, and the resolve-price
endpoint reading the active Purchase Setting.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.pricing import (
    INDICATIVE_PRICE_INVOICE_WINDOW,
    INDICATIVE_PRICE_LABEL,
    LAST_PURCHASE_PRICE_LABEL,
    PriceStrategy,
    indicative_purchase_prices,
    last_purchase_prices_base_currency,
    purchase_price_list,
    resolve_purchase_price,
)
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
        tenant=tenant, sku="PPR-1", name_ar="منتج", quantity_on_hand=0, avg_cost=Decimal("0"))
    return tenant, ils, usd, supplier, product


def _posted_pi(tenant, supplier, currency, product, *, number, date, price,
               posted=True, exchange_rate="1"):
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, partner=supplier,
        currency=currency, invoice_date=date, exchange_rate=Decimal(exchange_rate),
        is_posted=posted)
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=product, name="منتج",
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
        tenant=tenant, sku="PPR-2", name_ar="منتج٢", quantity_on_hand=0, avg_cost=Decimal("42"))

    result = purchase_price_list(tenant_id=tenant.TenantID)
    # الأساسي = آخر سعر (يُعبَّأ في الخلية)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("130.0000")
    assert result[product.id]["source_type"] == "PURCHASE_INVOICE"
    # المنتج بلا تاريخ شراء → متوسط التكلفة
    assert Decimal(result[other.id]["unit_price"]) == Decimal("42.0000")
    assert result[other.id]["source_type"] == "PRODUCT_AVG_COST"

    # prices تعرض آخر (130) وأقل (100) معاً للاطّلاع
    prices = {p["source_label"]: Decimal(p["unit_price"]) for p in result[product.id]["prices"]}
    assert prices.get("آخر شراء") == Decimal("130.0000")
    assert prices.get("أقل شراء (آخر ٥)") == Decimal("100.0000")

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
    assert prices.get("أقل شراء (آخر ٥)") == Decimal("80.0000")
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
            tenant=cls.tenant, sku="PPRE-1", name_ar="منتج", avg_cost=Decimal("0"))
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
        assert prices.get("أقل شراء (آخر ٥)") == Decimal("60.0000")


class PurchaseLowestPriceCurrencyTest(APITestCase):
    """ISSUE #111: «أقل سعر» (purchase_price_list) يقارن بالعملة **الأساسية**
    بعد التحويل بسعر صرف كلّ فاتورة هي — لا الرقم الخام المخزَّن. اختبارٌ على
    سطح DRF (نقطة `price-list/`) لا بالاستدعاء المباشر لـ`purchase_price_list`.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="lowcur", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة أقل سعر", cls.user)
        cls.sup_usd = Partner.objects.create(
            tenant=cls.tenant, name="مورد دولار", partner_type="Supplier")
        cls.sup_ils = Partner.objects.create(
            tenant=cls.tenant, name="مورد شيكل", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="LOWCUR-1", name_ar="منتج", avg_cost=Decimal("999"))
        # الرقم الخام أصغر (12) لكنه بالدولار بسعر صرف 3.6 → 43.2 شيكلاً أساسياً.
        # وهي الأحدث تاريخاً (فتصير «آخر شراء») — كي يبقى «أقل شراء» مستنداً مختلفاً
        # ويُثبت الاختباران معاً بلا تكرارٍ يُسقط أحدهما.
        cls.usd_invoice = _posted_pi(
            cls.tenant, cls.sup_usd, cls.usd, cls.product,
            number="USD-1", date="2026-06-10", price=12, exchange_rate="3.6")
        # الرقم الخام أكبر (20) لكنه بالشيكل (الأساسية) — فعلياً الأقلّ (20 < 43.2)،
        # وتاريخه أسبق فلا يصير «آخر شراء».
        cls.ils_invoice = _posted_pi(
            cls.tenant, cls.sup_ils, cls.ils, cls.product,
            number="ILS-1", date="2026-06-01", price=20)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_lowest_price_compares_base_currency_not_raw_number(self):
        res = self.client.get(
            "/api/logistics/purchase-invoices/price-list/", **self._auth())
        assert res.status_code == 200, res.content
        row = next(r for r in res.json() if r["product_id"] == self.product.id)
        lowest = next(p for p in row["prices"] if p["source_label"] == "أقل شراء (آخر ٥)")
        # الصحيح: فاتورة الشيكل (20) — لا فاتورة الدولار الخام الأصغر (12) التي
        # كان الكود القديم يختارها بلا نظرٍ إلى العملة.
        assert Decimal(lowest["unit_price"]) == Decimal("20.0000")
        assert lowest["document_id"] == self.ils_invoice.id
        assert lowest["document_number"] == "ILS-1"
        assert lowest["supplier_id"] == self.sup_ils.id
        assert lowest["supplier_name"] == "مورد شيكل"
        assert lowest["document_date"] == "2026-06-01"
        # لا سقوط إلى avg_cost أبداً لـ«أقل شراء» — القيمة من الفاتورة لا 999.
        assert Decimal(lowest["unit_price"]) != Decimal("999.0000")

    def test_no_purchase_history_leaves_lowest_empty_not_avg_cost(self):
        other = Product.objects.create(
            tenant=self.tenant, sku="LOWCUR-2", name_ar="منتج بلا شراء",
            avg_cost=Decimal("77"))
        res = self.client.get(
            "/api/logistics/purchase-invoices/price-list/", **self._auth())
        assert res.status_code == 200, res.content
        row = next((r for r in res.json() if r["product_id"] == other.id), None)
        assert row is not None  # احتياطي avg_cost يبقى يملأ «آخر شراء» وحدها
        labels = [p["source_label"] for p in row["prices"]]
        assert "أقل شراء (آخر ٥)" not in labels
        assert row["source_label"] == "متوسط التكلفة"
        assert Decimal(row["unit_price"]) == Decimal("77.0000")

    def test_tenant_isolation_on_lowest_price(self):
        other_owner = User.objects.create_user(username="lowcur2", password="x")
        other_tenant = create_company("شركة أخرى", other_owner)
        other_sup = Partner.objects.create(
            tenant=other_tenant, name="مورد آخر", partner_type="Supplier")
        # فاتورةٌ أرخص بكثير في شركة أخرى — يجب ألّا تُسرَّب إلى حساب هذه الشركة
        # ولو تشاركتا نفس صفّ المنتج (تجميع SQL مبنيّ على product_id عبر الجدول).
        _posted_pi(
            other_tenant, other_sup, self.ils, self.product,
            number="OTH-1", date="2026-06-05", price=1)
        res = self.client.get(
            "/api/logistics/purchase-invoices/price-list/", **self._auth())
        assert res.status_code == 200, res.content
        row = next(r for r in res.json() if r["product_id"] == self.product.id)
        lowest = next(p for p in row["prices"] if p["source_label"] == "أقل شراء (آخر ٥)")
        assert Decimal(lowest["unit_price"]) == Decimal("20.0000")


# ──────────────────────────────────────────────────────────────────────────
# #133 — السعر التقديري = أقلّ سعرٍ ضمن آخر ٥ مشتريات مرحَّلة (لا كل الفترات)
# ──────────────────────────────────────────────────────────────────────────
def test_indicative_price_excludes_old_floor_outside_window(env):
    """حالة 1: أكثر من ٥ مشتريات مرحَّلة — سعرٌ قديم أرخص يقع **خارج** نافذة
    آخر ٥ فاتورة، فيجب ألّا يظهر إطلاقاً بدل أقلّ سعرٍ ضمن النافذة فعلاً."""
    tenant, ils, _usd, sup, product = env
    assert INDICATIVE_PRICE_INVOICE_WINDOW == 5  # الأرقام أدناه مبنيّة على هذه القيمة تحديداً
    _posted_pi(tenant, sup, ils, product, number="OLD", date="2026-01-01", price=1)
    _posted_pi(tenant, sup, ils, product, number="P-2", date="2026-02-01", price=50)
    _posted_pi(tenant, sup, ils, product, number="P-3", date="2026-03-01", price=90)
    _posted_pi(tenant, sup, ils, product, number="P-4", date="2026-04-01", price=70)
    _posted_pi(tenant, sup, ils, product, number="P-5", date="2026-05-01", price=60)
    _posted_pi(tenant, sup, ils, product, number="P-6", date="2026-06-01", price=80)

    result = indicative_purchase_prices(tenant_id=tenant.TenantID)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("50.0000")
    assert Decimal(result[product.id]["unit_price"]) != Decimal("1.0000")
    assert result[product.id]["document_number"] == "P-2"
    assert result[product.id]["source_label"] == INDICATIVE_PRICE_LABEL
    assert result[product.id]["source_label"] == "أقل شراء (آخر ٥)"


def test_indicative_price_fewer_than_window_uses_what_exists(env):
    """حالة 2: أقل من ٥ مشتريات — يُحسب مما هو موجود، ولا يُحجب المنتج."""
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=100)
    _posted_pi(tenant, sup, ils, product, number="P-2", date="2026-06-15", price=80)

    result = indicative_purchase_prices(tenant_id=tenant.TenantID)
    assert product.id in result
    assert Decimal(result[product.id]["unit_price"]) == Decimal("80.0000")


def test_indicative_price_absent_when_no_purchase_history(env):
    """حالة 3: صفر مشتريات مرحَّلة — المفتاح **غائبٌ** من القاموس، لا صفر ولا
    سقوطٌ إلى avg_cost (هذا رقمُ تفاوضٍ لا تكلفة)."""
    tenant, _ils, _usd, _sup, product = env
    product.avg_cost = Decimal("999")
    product.save(update_fields=["avg_cost"])

    result = indicative_purchase_prices(tenant_id=tenant.TenantID)
    assert product.id not in result


def test_indicative_price_counts_multi_line_invoice_once(env):
    """حالة 4: فاتورةٌ واحدة بسطرين لنفس المنتج تُحتسب فاتورةً **واحدة** ضمن
    نافذة الخمس — لا سطرين يزاحمان فاتورةً أقدم فتخرج ظلماً من النافذة."""
    tenant, ils, _usd, sup, product = env
    old = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="OLD", partner=sup, currency=ils,
        invoice_date="2026-01-01", exchange_rate=Decimal("1"), is_posted=True)
    PurchaseInvoiceItem.objects.create(
        invoice=old, product=product, name="منتج", quantity=Decimal("1"),
        unit_price=Decimal("1"), total_price=Decimal("1"))

    dual = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="DUAL", partner=sup, currency=ils,
        invoice_date="2026-02-01", exchange_rate=Decimal("1"), is_posted=True)
    PurchaseInvoiceItem.objects.create(
        invoice=dual, product=product, name="منتج سطر أ", quantity=Decimal("1"),
        unit_price=Decimal("40"), total_price=Decimal("40"))
    PurchaseInvoiceItem.objects.create(
        invoice=dual, product=product, name="منتج سطر ب", quantity=Decimal("1"),
        unit_price=Decimal("90"), total_price=Decimal("90"))

    _posted_pi(tenant, sup, ils, product, number="P-3", date="2026-03-01", price=70)
    _posted_pi(tenant, sup, ils, product, number="P-4", date="2026-04-01", price=60)
    _posted_pi(tenant, sup, ils, product, number="P-5", date="2026-05-01", price=80)
    _posted_pi(tenant, sup, ils, product, number="P-6", date="2026-06-01", price=95)

    result = indicative_purchase_prices(tenant_id=tenant.TenantID)
    # النافذة (آخر ٥ فاتورة): DUAL، P-3، P-4، P-5، P-6 — لا OLD. أقلّهم سطر
    # DUAL الأرخص (40) — لا سعر OLD القديم (1) ولا سطر DUAL الآخر (90).
    assert Decimal(result[product.id]["unit_price"]) == Decimal("40.0000")
    assert result[product.id]["document_number"] == "DUAL"


def test_indicative_price_normalizes_each_invoice_at_its_own_rate(env):
    """حالة 5 (ISSUE #111 لا اختيارية): فاتورتان بعملتين مختلفتين — يجب أن
    تُقارَن كلٌّ منهما بسعر صرف **مستندها هو**، لا رقمها الخام. رقمٌ خامٌ أصغر
    (12 دولاراً) قد يكون أكبر فعلياً بعد التحويل (43.2 شيكلاً) من رقمٍ خامٍ
    أكبر (20 شيكلاً بالفعل)."""
    tenant, ils, usd, sup, product = env
    _posted_pi(tenant, sup, usd, product, number="USD-1", date="2026-06-10",
               price=12, exchange_rate="3.6")  # 12 × 3.6 = 43.2 أساسياً
    _posted_pi(tenant, sup, ils, product, number="ILS-1", date="2026-06-01",
               price=20)  # 20 أساسياً فعلاً — وهو الأقلّ الحقيقي

    result = indicative_purchase_prices(tenant_id=tenant.TenantID)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("20.0000")
    assert result[product.id]["document_number"] == "ILS-1"


def test_indicative_price_bulk_computation_is_single_query(env, django_assert_num_queries):
    """حالة 6: حارسُ الاستعلام الواحد — تجميعٌ عبر كل منتجات الشركة في استعلام
    SQL واحد (دالّة نافذة)، لا استعلامٌ لكل منتج ولا استعلامٌ مترابط لكل صفّ."""
    tenant, ils, _usd, sup, product = env
    other = Product.objects.create(
        tenant=tenant, sku="PPR-3", name_ar="منتج آخر", quantity_on_hand=0,
        avg_cost=Decimal("0"))
    for i, price in enumerate((100, 80, 60, 40, 20, 10), start=1):
        _posted_pi(tenant, sup, ils, product, number=f"Q-{i}",
                   date=f"2026-0{i}-01", price=price)
    _posted_pi(tenant, sup, ils, other, number="O-1", date="2026-01-01", price=55)

    with django_assert_num_queries(1):
        indicative_purchase_prices(tenant_id=tenant.TenantID)


# ──────────────────────────────────────────────────────────────────────────
# «آخر سعر شراء» للقائمة/الكرت — قراءةٌ دفعية واحدة، لا avg_cost، ولا نافذة
# ──────────────────────────────────────────────────────────────────────────
def test_last_purchase_bulk_is_the_latest_posted_not_the_minimum(env):
    """آخر سعر = **أحدث** فاتورة شراء مرحَّلة، لا الأقلّ ولا متوسطاً.

    الأرقام الثلاثة متمايزة عمداً (٢٠ أقلّ، ١٠٠ وسط، ٤٠ آخر) كي يكشف الاختبار
    أيّ توصيلٍ خاطئ: القيمة الأساسية للصفّ يجب أن تكون ٤٠ — وهي أيضاً ما تعرضه
    «أقلّ شراء» كرقمٍ مختلف (٢٠) فيبقى الحقلان مستقلّين في الاختبار.
    """
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=20)
    _posted_pi(tenant, sup, ils, product, number="P-2", date="2026-06-15", price=100)
    _posted_pi(tenant, sup, ils, product, number="P-3", date="2026-06-20", price=40)

    result = last_purchase_prices_base_currency(tenant_id=tenant.TenantID)
    row = result[product.id]
    assert Decimal(row["unit_price"]) == Decimal("40.0000")
    assert row["document_number"] == "P-3"
    assert row["document_date"] == "2026-06-20"
    assert row["source_type"] == "PURCHASE_INVOICE"
    assert row["source_label"] == LAST_PURCHASE_PRICE_LABEL == "آخر سعر شراء"
    # «أقلّ شراء» رقمٌ آخر فعلاً — لا نسخةً من آخر سعر بلافتةٍ ثانية.
    lowest = indicative_purchase_prices(tenant_id=tenant.TenantID)
    assert Decimal(lowest[product.id]["unit_price"]) == Decimal("20.0000")


def test_last_purchase_bulk_ignores_drafts(env):
    """المسوّدة الأحدث والأرخص لا تصير «آخر سعر شراء» — المرحَّل وحده يُقرأ."""
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="D-1", date="2026-06-25", price=5, posted=False)
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=40)

    result = last_purchase_prices_base_currency(tenant_id=tenant.TenantID)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("40.0000")
    assert result[product.id]["document_number"] == "P-1"


def test_last_purchase_bulk_absent_without_history_not_avg_cost(env):
    """بلا شراء مرحَّل: المفتاح **غائب** — لا سقوطٌ إلى `avg_cost`.

    متوسط التكلفة ليس سعر شراء (وهو هنا ٩٩ لتُكشف أيّ سلسلة احتياطٍ تُدخله).
    """
    tenant, _ils, _usd, _sup, product = env
    product.avg_cost = Decimal("99")
    product.save(update_fields=["avg_cost"])

    result = last_purchase_prices_base_currency(tenant_id=tenant.TenantID)
    assert product.id not in result


def test_last_purchase_bulk_uses_document_rate_and_line_override(env):
    """كل فاتورةٍ تُحوَّل بسعر صرف **سطرها** إن وُجد وإلا فاتورتها — لا رقمٍ خام."""
    tenant, ils, usd, sup, product = env
    # ١٠ دولار × ٣٫٦ = ٣٦ أساسياً (أقدم).
    _posted_pi(tenant, sup, usd, product, number="USD-1", date="2026-06-01",
               price=10, exchange_rate="3.6")
    # ١٠ دولارات بسعر صرف سطرٍ ٤٫٠ = ٤٠ أساسياً (الأحدث) — السطر يسبق الفاتورة.
    latest = _posted_pi(tenant, sup, usd, product, number="USD-2", date="2026-06-10",
                        price=10, exchange_rate="3.6")
    latest.items.update(line_exchange_rate=Decimal("4.0"))

    result = last_purchase_prices_base_currency(tenant_id=tenant.TenantID)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("40.0000")
    assert result[product.id]["document_number"] == "USD-2"
    # ولا رقمٌ خام (١٠) ولا صرفُ اليوم — تحويلُ مستندٍ بعملته هو.
    assert Decimal(result[product.id]["unit_price"]) != Decimal("10.0000")


def test_last_purchase_bulk_equal_dates_break_by_invoice_id(env):
    """تاريخان متساويان: حتميّةٌ بمعرّف الفاتورة الأعلى — كما يفعل المسترجع."""
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="P-OLD", date="2026-06-10", price=10)
    newer = _posted_pi(tenant, sup, ils, product, number="P-NEW", date="2026-06-10", price=70)

    result = last_purchase_prices_base_currency(tenant_id=tenant.TenantID)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("70.0000")
    assert result[product.id]["document_id"] == newer.id
    resolved = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id,
        strategy=PriceStrategy.LAST_PURCHASE)
    assert resolved["unit_price"] == result[product.id]["unit_price"]
    assert resolved["source"]["document_id"] == newer.id


def test_last_purchase_bulk_is_tenant_scoped(env):
    """فاتورةٌ أحدث في شركةٍ أخرى لا تُسرَّب إلى هذه الشركة."""
    tenant, ils, _usd, sup, product = env
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=40)
    other_owner = User.objects.create_user(username="ppr2", password="x")
    other_tenant = create_company("شركة تسعير أخرى", other_owner)
    other_sup = Partner.objects.create(
        tenant=other_tenant, name="مورد آخر", partner_type="Supplier")
    _posted_pi(other_tenant, other_sup, ils, product, number="OTH-1",
               date="2026-07-01", price=1)

    result = last_purchase_prices_base_currency(tenant_id=tenant.TenantID)
    assert Decimal(result[product.id]["unit_price"]) == Decimal("40.0000")
    assert result[product.id]["document_number"] == "P-1"


def test_last_purchase_bulk_honours_product_ids_filter(env):
    """الطلب المقيَّد بمعرّفات صفحةٍ لا يحسب بقية الكتالوج."""
    tenant, ils, _usd, sup, product = env
    other = Product.objects.create(
        tenant=tenant, sku="PPR-9", name_ar="منتج آخر", avg_cost=Decimal("0"))
    _posted_pi(tenant, sup, ils, product, number="P-1", date="2026-06-01", price=40)
    _posted_pi(tenant, sup, ils, other, number="P-2", date="2026-06-01", price=90)

    result = last_purchase_prices_base_currency(
        tenant_id=tenant.TenantID, product_ids=[product.id])
    assert set(result) == {product.id}


def test_last_purchase_bulk_query_count_is_bounded(
        env, django_assert_max_num_queries):
    """استعلامان ثابتان مهما بلغ عدد المنتجات: مسحُ البنود + خريطة حصص الدولية.

    لا استعلامَ لكل صفّ، ولا استعلامٌ مترابط لكل منتج — نفس درس
    `correlated-subquery-on-lists` الذي يمنع ربطَ صفٍّ باستعلامٍ خاصّ به.
    """
    tenant, ils, _usd, sup, product = env
    products = [product]
    for i in range(6):
        products.append(Product.objects.create(
            tenant=tenant, sku=f"PPRQ-{i}", name_ar=f"منتج {i}", avg_cost=Decimal("0")))
    for i, p in enumerate(products):
        _posted_pi(tenant, sup, ils, p, number=f"Q-{i}", date=f"2026-06-0{i + 1}",
                   price=10 + i)

    with django_assert_max_num_queries(2):
        result = last_purchase_prices_base_currency(tenant_id=tenant.TenantID)
    assert len(result) == len(products)
