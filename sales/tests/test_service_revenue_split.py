"""إيراد الخدمات يُقيَّد على حسابه لا على إيراد البضائع (T-SERVICELINE).

المالك: «بفواتير البيع بدي بند للخدمات ويتسجل بإيرادات كخدمات.»

الفجوة: `_default_revenue_account(is_service=True)` كانت **ترتدّ إلى حساب إيراد
المنتجات** متى كان `default_revenue_account_service` فارغاً — وهو الحال في كل
شركة لم تُضبط يدوياً. فيُقيَّد بيع الخدمة كبيع بضاعة، ويضيع الفصل الذي طُلب.
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
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="svcrev", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الخدمات", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-S", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل الخدمات", partner_type="Customer", linked_account=ar)
    goods = Product.objects.create(
        tenant=tenant, sku="SVC-G1", name_ar="بضاعة", quantity_on_hand=10, avg_cost=1)
    service = Product.objects.create(
        tenant=tenant, sku="SVC-S1", name_ar="تركيب إطارات", is_service=True)
    return tenant, customer, goods, service


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


def test_service_revenue_account_is_created_when_missing(env):
    tenant, *_ = env
    account = resolve_service_revenue_account(tenant.TenantID)
    assert account is not None
    assert account.account_type == "Revenue"
    # مُثبَّت على الإعدادات كي لا يُنشأ حسابٌ ثانٍ في المرة التالية.
    settings_obj = SalesSettings.objects.get(tenant_id=tenant.TenantID)
    assert settings_obj.default_revenue_account_service_id == account.pk
    assert resolve_service_revenue_account(tenant.TenantID).pk == account.pk


def test_service_line_credits_the_service_revenue_account(env):
    tenant, customer, goods, service = env
    inv = _invoice(tenant, customer, (goods, 1, 100), (service, 1, 40), number="SVC-INV-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()

    service_account = resolve_service_revenue_account(tenant.TenantID)
    credits = {
        line.account_id: line.credit
        for line in JournalLine.objects.filter(journal=inv.journal)
        if line.credit and line.credit > 0
    }
    assert credits.get(service_account.pk) == Decimal("40.00")
    # إيراد البضاعة على حساب آخر — الفصل هو المطلوب، لا مجرد وجود الحساب.
    goods_accounts = [a for a, amount in credits.items()
                      if a != service_account.pk and amount == Decimal("100.00")]
    assert goods_accounts


def test_configured_service_account_is_respected(env):
    tenant, customer, _goods, service = env
    chosen = Account.objects.create(
        tenant=tenant, code="4900-SVC", name="إيرادات خدمات مختارة",
        account_type="Revenue", is_active=True)
    SalesSettings.objects.update_or_create(
        tenant=tenant, defaults={"default_revenue_account_service": chosen})
    inv = _invoice(tenant, customer, (service, 2, 25), number="SVC-INV-2")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    credited = JournalLine.objects.filter(
        journal=inv.journal, account=chosen, credit=Decimal("50.00"))
    assert credited.exists()
    assert Account.objects.filter(
        tenant=tenant, account_type="Revenue").count() >= 1
