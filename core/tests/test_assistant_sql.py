"""اختبارات طبقة SQL الآمنة للمساعد — العزل الإلزامي هو الأهم.

نتحقق أن حقن TenantID يشمل كل جدول في كل نطاق (JOIN/subquery/CTE)، وأن الجداول
العامة لا تُفلتر، وأن أوامر التعديل مرفوضة، وأن التنفيذ الفعلي لا يسرّب شركة أخرى.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from core.assistant_sql import _safe, inject_tenant, run_sql, tenant_scoped_tables
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _norm(s: str) -> str:
    return s.replace("`", "").replace('"', "").lower()


def test_tenant_tables_include_core_and_exclude_globals():
    t = tenant_scoped_tables()
    assert "products" in t
    assert "sales_module_invoices" in t
    assert "partners" in t
    # عامة بلا شركة
    assert "currencies" not in t
    assert "units_of_measure" not in t


def test_inject_simple_select():
    out = _norm(inject_tenant("SELECT * FROM products", 7))
    assert "products.tenantid = 7" in out


def test_inject_join_filters_both_tenant_tables():
    sql = (
        "SELECT i.GrandTotal, p.Name FROM sales_module_invoices i "
        "JOIN partners p ON p.PartnerID = i.CustomerID"
    )
    out = _norm(inject_tenant(sql, 3))
    assert "i.tenantid = 3" in out
    assert "p.tenantid = 3" in out


def test_inject_does_not_filter_global_table():
    sql = "SELECT c.Code FROM currencies c"
    out = _norm(inject_tenant(sql, 9))
    assert "tenantid" not in out  # currencies عامة


def test_inject_subquery_scope():
    sql = (
        "SELECT * FROM products WHERE ProductID IN "
        "(SELECT ProductID FROM products WHERE QuantityOnHand > 0)"
    )
    out = _norm(inject_tenant(sql, 5))
    # كلا النطاقين يجب أن يُفلترا
    assert out.count("tenantid = 5") >= 2


def test_safe_serializes_decimal():
    # MySQL يرجع Decimal (SQLite يرجع float فيخفي المشكلة) — يجب أن يتسلسل JSON
    import json
    from decimal import Decimal

    assert _safe(Decimal("5.50")) == 5.5
    assert _safe(Decimal("12")) == 12
    json.dumps({"v": _safe(Decimal("99.99"))})  # لا يرفع استثناءً


def test_non_business_table_is_rejected():
    # جداول Django الداخلية ممنوعة حتى للقراءة
    res = run_sql(1, "SELECT username, password FROM auth_user")
    assert "error" in res
    assert "auth_user" in res["error"]


def test_forbidden_write_is_rejected():
    assert "error" in run_sql(1, "UPDATE products SET QuantityOnHand = 0")
    assert "error" in run_sql(1, "DROP TABLE products")
    assert "error" in run_sql(1, "SELECT 1; DELETE FROM products")


@pytest.fixture
def two_companies():
    owner = User.objects.create_user(username="sql", password="x", is_superuser=True)
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    a = create_company("شركة أ", owner)
    b = create_company("شركة ب", owner)
    Product.objects.create(tenant=a, sku="A-1", name_ar="صنف أ",
                           quantity_on_hand=Decimal("40"), avg_cost=Decimal("10"))
    Product.objects.create(tenant=b, sku="B-1", name_ar="صنف ب",
                           quantity_on_hand=Decimal("999"), avg_cost=Decimal("1"))
    ca = Partner.objects.create(tenant=a, name="عميل أ", partner_type="Customer")
    cb = Partner.objects.create(tenant=b, name="عميل ب", partner_type="Customer")
    SalesInvoice.objects.create(tenant=a, invoice_number="A-S1", customer=ca, currency=cur,
                                invoice_date="2026-06-01", invoice_kind="sale",
                                status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("500"))
    SalesInvoice.objects.create(tenant=b, invoice_number="B-S1", customer=cb, currency=cur,
                                invoice_date="2026-06-01", invoice_kind="sale",
                                status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("8888"))
    return a, b


def test_run_sql_scopes_products_to_company(two_companies):
    a, b = two_companies
    res = run_sql(a.pk, "SELECT SKU, QuantityOnHand FROM products")
    skus = {r[0] for r in res["rows"]}
    assert skus == {"A-1"}  # لا B-1 من شركة ب


def test_run_sql_cannot_reach_other_company_even_if_asked(two_companies):
    a, b = two_companies
    # حتى لو حاول النموذج استهداف شركة ب صراحةً، الحقن يضيف AND TenantID=a → فارغ
    res = run_sql(a.pk, f"SELECT GrandTotal FROM sales_module_invoices WHERE TenantID = {b.pk}")
    assert res["count"] == 0
    # وبلا شرط، يرى مبيعات شركته فقط
    res2 = run_sql(a.pk, "SELECT GrandTotal FROM sales_module_invoices")
    totals = {float(r[0]) for r in res2["rows"]}
    assert totals == {500.0}  # لا 8888
