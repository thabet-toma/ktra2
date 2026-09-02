"""ISSUE #78 — أتعاب المكتب لكل خدمة، لا حساباً واحداً ميتاً.

الفجوة: `_resolve_revenue_account_for_line` كانت تحرس تجاوز حساب المنتج نفسه
(`sale_account_override`) بـ`not is_service` — فأي بندٍ خدميّ يسقط حتماً إلى
`_default_revenue_account(is_service=True)` (حساب الخدمات العام «4102») ولو
كان للمنتج حساب أتعابٍ خاص. الحسابات الأربعة المزروعة مع قالب «مكتب محاسبة»
(4103 مسك الدفاتر · 4104 الإقرارات · 4105 التدقيق · 4106 الاستشارات) كانت
حسابات ميتة لأن `create_company` لم تكن تزرع أي بندٍ خدميّ يشير إليها أصلاً.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings
from sales.services import post_sales_invoice, resolve_service_revenue_account
from tenants.company_templates import ACCOUNTING_FIRM_SERVICES
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _make_tenant(username, *, template="accounting_firm"):
    owner = User.objects.create_user(username=username, password="x")
    ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company(f"مكتب {username}", owner, template=template)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    return tenant


def _customer(tenant, *, code):
    ar = Account.objects.create(
        tenant=tenant, code=f"1101-{code}", name="ذمم", account_type="Asset", is_active=True)
    return Partner.objects.create(
        tenant=tenant, name=f"عميل {code}", partner_type="Customer", linked_account=ar)


def _invoice(tenant, customer, *lines, number):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    for product, qty, price in lines:
        SalesInvoiceLine.objects.create(
            tenant=tenant, invoice=inv, product=product,
            quantity=Decimal(str(qty)), unit_price=Decimal(str(price)))
    return inv


def _credit_by_account(journal):
    return {
        line.account_id: line.credit
        for line in JournalLine.objects.filter(journal=journal)
        if line.credit and line.credit > 0
    }


# ── الزرع: خمس خدمات مربوطة بحساباتها ────────────────────────────────────────

def test_accounting_firm_template_seeds_five_linked_services():
    tenant = _make_tenant("svcfee-seed")
    services = Product.objects.filter(tenant=tenant, is_service=True)
    assert services.count() == 5

    by_sku = {p.sku: p for p in services}
    assert set(by_sku) == {sku for sku, _name, _code in ACCOUNTING_FIRM_SERVICES}
    for sku, _name, account_code in ACCOUNTING_FIRM_SERVICES:
        product = by_sku[sku]
        assert product.sale_account_override is not None
        assert product.sale_account_override.code == account_code


def test_general_template_seeds_no_services():
    tenant = _make_tenant("svcfee-general", template="general")
    assert not Product.objects.filter(tenant=tenant, is_service=True).exists()


# ── الترحيل: البند الخدميّ يقيّد على حساب أتعابه لا 4102 ────────────────────

def test_bookkeeping_service_posts_to_4103_not_4102():
    tenant = _make_tenant("svcfee-bk")
    customer = _customer(tenant, code="BK")
    bookkeeping = Product.objects.get(tenant=tenant, sku="SVC-BOOKKEEPING")
    inv = _invoice(tenant, customer, (bookkeeping, 1, 500), number="OFF-BK-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()

    fees_4103 = Account.objects.get(tenant=tenant, code="4103")
    credits = _credit_by_account(inv.journal)
    assert credits.get(fees_4103.pk) == Decimal("500.00")

    general_service_account = resolve_service_revenue_account(tenant.TenantID)
    assert general_service_account.pk not in credits


def test_all_seeded_services_post_to_their_own_account():
    tenant = _make_tenant("svcfee-all")
    customer = _customer(tenant, code="ALL")
    for sku, _name, account_code in ACCOUNTING_FIRM_SERVICES:
        product = Product.objects.get(tenant=tenant, sku=sku)
        inv = _invoice(tenant, customer, (product, 1, 100), number=f"OFF-{sku}")
        post_sales_invoice(inv)
        inv.refresh_from_db()
        account = Account.objects.get(tenant=tenant, code=account_code)
        credits = _credit_by_account(inv.journal)
        assert credits.get(account.pk) == Decimal("100.00")


# ── السلوك القديم محفوظ: خدمة بلا حساب خاص، ومنتجٌ غير خدميّ بلا تغيير ──────

def test_service_without_override_still_falls_back_to_general_service_account():
    tenant = _make_tenant("svcfee-noovr")
    customer = _customer(tenant, code="NOOVR")
    plain_service = Product.objects.create(
        tenant=tenant, sku="SVC-PLAIN", name_ar="خدمة عامة", is_service=True)
    inv = _invoice(tenant, customer, (plain_service, 1, 60), number="OFF-PLAIN-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()

    general_service_account = resolve_service_revenue_account(tenant.TenantID)
    credits = _credit_by_account(inv.journal)
    assert credits.get(general_service_account.pk) == Decimal("60.00")


def test_non_service_product_override_behaviour_unchanged():
    tenant = _make_tenant("svcfee-goods", template="general")
    customer = _customer(tenant, code="GOODS")
    special = Account.objects.create(
        tenant=tenant, code="4900-GOODS", name="إيراد بضاعة خاص",
        account_type="Revenue", is_active=True)
    goods = Product.objects.create(
        tenant=tenant, sku="GOODS-1", name_ar="بضاعة", quantity_on_hand=10,
        avg_cost=1, sale_account_override=special)
    inv = _invoice(tenant, customer, (goods, 2, 40), number="OFF-GOODS-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()

    credits = _credit_by_account(inv.journal)
    assert credits.get(special.pk) == Decimal("80.00")


def test_non_service_product_without_override_routes_as_before():
    tenant = _make_tenant("svcfee-goods-plain", template="general")
    customer = _customer(tenant, code="GOODSP")
    goods = Product.objects.create(
        tenant=tenant, sku="GOODS-PLAIN-1", name_ar="بضاعة عادية",
        quantity_on_hand=10, avg_cost=1)
    inv = _invoice(tenant, customer, (goods, 1, 30), number="OFF-GOODS-2")
    post_sales_invoice(inv)
    inv.refresh_from_db()

    product_account = Account.objects.get(tenant=tenant, code="4101")
    credits = _credit_by_account(inv.journal)
    assert credits.get(product_account.pk) == Decimal("30.00")
