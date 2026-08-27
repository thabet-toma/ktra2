"""المبيعات — تماثل دورة post → unpost → repost للمخزون والقيد معاً.

يثبت (تحقّق فقط، بلا تغيير على كود المبيعات) أن فاتورة المبيعات التي تخصم
المخزون عند الترحيل: إلغاء الترحيل يُعيد المخزون ويحذف القيد، وإعادة الترحيل
تخصم المخزون من جديد بنفس رقم القيد — متماثل وidempotent، كالمشتريات.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, VoidedJournal
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="sstock", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة المبيعات", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-S", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="SS-1", name_ar="منتج", quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    # رصيد افتتاحي مدعوم بحركة مخزون (كالواقع) — حتى تُعيد إعادة الاحتساب 100 بدقة.
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("100"),
        unit_cost=Decimal("10"), reference_type="OPENING", reference_id=0,
        movement_date="2026-06-01", tenant=tenant)
    product.refresh_from_db()
    cogs = Account.objects.create(
        tenant=tenant, code="5101-S", name="تكلفة", account_type="Expense", is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-S", name="مخزون", account_type="Asset", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = cogs
    ss.default_inventory_account = inv_acc
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    return tenant, owner, cur, customer, product


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def test_sales_post_unpost_repost_restores_stock_and_journal(env):
    tenant, owner, cur, customer, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="S-1", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CASH, stock_on_post=True)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("5"), unit_price=Decimal("100"))
    c = _client(owner, tenant)

    # ── ترحيل: خصم المخزون + قيد ──
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("95.0000")
    assert StockMovement.objects.filter(reference_type="SALE", reference_id=inv.id).exists()
    inv.refresh_from_db()
    first_journal_id = inv.journal_id
    assert first_journal_id is not None

    # ── إلغاء الترحيل: المخزون يعود + القيد يُحذف + الرقم محجوز ──
    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("100.0000")
    assert not StockMovement.objects.filter(reference_type="SALE", reference_id=inv.id).exists()
    assert not JournalHeader.objects.filter(reference_type="SALES_INVOICE", reference_id=inv.id).exists()
    assert VoidedJournal.objects.get(
        tenant=tenant, reference_type="SALES_INVOICE",
        reference_id=inv.id).original_journal_id == first_journal_id

    # ── إعادة الترحيل: يخصم المخزون من جديد بنفس رقم القيد ──
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("95.0000")
    inv.refresh_from_db()
    assert inv.journal_id == first_journal_id

    # ── تكرار (idempotent، بلا انجراف) ──
    c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json")
    c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("95.0000")
    inv.refresh_from_db()
    assert inv.journal_id == first_journal_id
