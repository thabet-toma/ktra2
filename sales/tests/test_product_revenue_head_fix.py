"""ISSUE #59 — حساب إيراد المنتجات كان يُثبَّت على رأس شجرة الإيرادات «4» لا 4101.

`get_or_create_sales_settings` كانت تُثبّت `default_revenue_account_product`
بأوّل حساب إيراد بالكود (`'4' < '41' < '4101'`) — رأس الشجرة، حسابٌ أب لا يصلح
هدفاً للترحيل. هذا الملف يثبت:
1. شركة جديدة تُرحّل بند بضاعة على `4101` لا على الرأس.
2. `resolve_product_revenue_account` تُثبِّت وتُعيد استعمال نفس الحساب (مرآة
   `resolve_service_revenue_account` — انظر `test_service_revenue_split.py`).
3. أمر الإصلاح `fix_product_revenue_account_default` يُبدّل الصفوف الخاطئة
   (حساب أب) وحدها، idempotent، ولا يمسّ صفاً صحيحاً.
"""
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings
from sales.services import (
    get_or_create_sales_settings,
    post_sales_invoice,
    resolve_product_revenue_account,
)
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="prodrev", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة المنتجات ٥٩", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-P", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل البضاعة", partner_type="Customer", linked_account=ar)
    goods = Product.objects.create(
        tenant=tenant, sku="P59-G1", name_ar="بضاعة", quantity_on_hand=10, avg_cost=1)
    return tenant, customer, goods


def _invoice(tenant, customer, product, *, number, qty="1", price="100"):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal(qty), unit_price=Decimal(price))
    return inv


# ── 1+2. شركة بكر: المحرّك يحلّ 4101 لا الرأس ────────────────────────────────

def test_resolve_product_revenue_account_is_not_the_revenue_root(env):
    tenant, *_ = env
    account = resolve_product_revenue_account(tenant.TenantID)
    assert account is not None
    assert account.account_type == "Revenue"
    assert account.parent_id is not None  # ليس رأس الشجرة «4» (بلا أب)
    assert account.code == "4101"
    settings_obj = SalesSettings.objects.get(tenant_id=tenant.TenantID)
    assert settings_obj.default_revenue_account_product_id == account.pk
    # تُثبَّت — استدعاء ثانٍ يعيد نفس الحساب بلا إنشاء آخر.
    assert resolve_product_revenue_account(tenant.TenantID).pk == account.pk


def test_fresh_company_creation_leaves_product_account_empty(env):
    tenant, *_ = env
    ss = get_or_create_sales_settings(tenant)
    # لا حساب مُثبَّت بعد الإنشاء مباشرة — `resolve_product_revenue_account`
    # وحدها تملؤه لاحقاً، لا `get_or_create_sales_settings` بنفسها.
    assert ss.default_revenue_account_product_id is None


def test_goods_invoice_posts_to_product_revenue_not_head(env):
    tenant, customer, goods = env
    inv = _invoice(tenant, customer, goods, number="P59-INV-1", qty="2", price="50")
    post_sales_invoice(inv)
    inv.refresh_from_db()

    product_account = resolve_product_revenue_account(tenant.TenantID)
    lines = list(JournalLine.objects.filter(journal=inv.journal))
    revenue_line = next(ln for ln in lines if ln.credit and ln.credit > 0)
    assert revenue_line.account_id == product_account.pk
    assert revenue_line.account.code == "4101"
    # رأس الشجرة نفسه لم يُستعمل هدفاً لأي سطر قيد.
    head = Account.objects.get(tenant=tenant, code="4")
    assert not any(ln.account_id == head.pk for ln in lines)


# ── 3. أمر الإصلاح على شركات قائمة ──────────────────────────────────────────

def _run_fix(dry_run=False):
    out = StringIO()
    call_command("fix_product_revenue_account_default", dry_run=dry_run, stdout=out)
    return out.getvalue()


@pytest.fixture
def legacy_env():
    """شركتان: واحدة على الحساب الخاطئ (الرأس)، وأخرى على حسابٍ صحيح سلفاً."""
    owner = User.objects.create_user(username="prodrev-legacy", password="x")

    broken_tenant = create_company("شركة قديمة معطوبة ٥٩", owner)
    create_fiscal_year(broken_tenant, 2026)
    head = Account.objects.get(tenant=broken_tenant, code="4")
    ss_broken = get_or_create_sales_settings(broken_tenant)
    ss_broken.default_revenue_account_product = head
    ss_broken.save(update_fields=["default_revenue_account_product"])

    healthy_tenant = create_company("شركة سليمة ٥٩", owner)
    create_fiscal_year(healthy_tenant, 2026)
    leaf = Account.objects.get(tenant=healthy_tenant, code="4101")
    ss_healthy = get_or_create_sales_settings(healthy_tenant)
    ss_healthy.default_revenue_account_product = leaf
    ss_healthy.save(update_fields=["default_revenue_account_product"])

    return broken_tenant, healthy_tenant, leaf


def test_fix_command_replaces_only_the_head_account(legacy_env):
    broken_tenant, healthy_tenant, leaf = legacy_env
    _run_fix()

    ss_broken = SalesSettings.objects.get(tenant_id=broken_tenant.TenantID)
    assert ss_broken.default_revenue_account_product.code == "4101"
    assert ss_broken.default_revenue_account_product.parent_id is not None

    # الصف الصحيح سلفاً لم يُمَسّ.
    ss_healthy = SalesSettings.objects.get(tenant_id=healthy_tenant.TenantID)
    assert ss_healthy.default_revenue_account_product_id == leaf.pk


def test_fix_command_dry_run_writes_nothing(legacy_env):
    broken_tenant, _healthy_tenant, _leaf = legacy_env
    head = Account.objects.get(tenant=broken_tenant, code="4")
    _run_fix(dry_run=True)
    ss_broken = SalesSettings.objects.get(tenant_id=broken_tenant.TenantID)
    assert ss_broken.default_revenue_account_product_id == head.pk


def test_fix_command_is_idempotent(legacy_env):
    broken_tenant, _healthy_tenant, _leaf = legacy_env
    _run_fix()
    ss_after_first = SalesSettings.objects.get(tenant_id=broken_tenant.TenantID)
    fixed_account_id = ss_after_first.default_revenue_account_product_id

    output = _run_fix()
    ss_after_second = SalesSettings.objects.get(tenant_id=broken_tenant.TenantID)
    assert ss_after_second.default_revenue_account_product_id == fixed_account_id
    assert "أُصلح 0 صفّاً" in output
