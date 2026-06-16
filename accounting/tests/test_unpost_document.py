"""Feature 1 — التراجع عن الترحيل (Unpost) + الحذف المتسلسل لقيود مستند.

يثبت أن `accounting.services.unpost_document`:
  1. يحذف **كل** قيود المستند (cascade على الأسطر) محصوراً بهذا المستند وحده
     فلا يمسّ قيود أي مستند آخر.
  2. يعيد حركات مخزون المستند بإعادة احتساب الرصيد/متوسط التكلفة بدقة.
  3. عملية ذرّية تُبقي توازن القيود سليماً (إعادة الترحيل تُوازن من جديد).
وأن نقطة النهاية `/sales/invoices/{id}/unpost/` تُرجع الفاتورة لحالة مسودة
وتسمح بحذفها، بينما تعديل/حذف فاتورة مرحّلة محظور برسالة التراجع.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal, unpost_document
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="unpost", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة التراجع", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-U", name="ذمم", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-U", name="إيراد", account_type="Revenue", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="U-1", name_ar="صنف", quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    return tenant, owner, ar, rev, customer, product


def _post_simple_journal(tenant, ar, rev, ref_type, ref_id, amount="100"):
    amt = Decimal(amount)
    return post_journal(
        tenant_id=tenant.TenantID,
        transaction_date="2026-06-11",
        reference_type=ref_type,
        reference_id=ref_id,
        description=f"{ref_type} {ref_id}",
        lines_data=[
            {"account": ar.id, "debit": amt, "credit": Decimal("0")},
            {"account": rev.id, "debit": Decimal("0"), "credit": amt},
        ],
    )


def test_unpost_deletes_only_scoped_journals(env):
    tenant, owner, ar, rev, customer, product = env
    keep = _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 2001)
    target = _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 2002)
    other = _post_simple_journal(tenant, ar, rev, "PURCHASE_INVOICE", 2002)  # same id, diff type

    result = unpost_document(
        tenant_id=tenant.TenantID,
        reference_id=2002,
        journal_reference_types=["SALES_INVOICE", "SALES_DELIVERY_COGS"],
        user=owner,
    )

    assert result["journals_deleted"] == 1
    assert result["lines_deleted"] == 2
    # المستهدف وأسطره حُذِفا
    assert not JournalHeader.objects.filter(pk=target.id).exists()
    assert not JournalLine.objects.filter(journal_id=target.id).exists()
    # القيود الأخرى لم تُمَسّ (نفس reference_id لكن نوع مختلف، وقيد آخر بنفس النوع)
    assert JournalHeader.objects.filter(pk=keep.id).exists()
    assert JournalHeader.objects.filter(pk=other.id).exists()


def test_unpost_reverses_stock_via_replay(env):
    tenant, owner, ar, rev, customer, product = env
    # حركة شراء لمستند آخر (يجب أن تبقى) ثم حركتا المستند المستهدف
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), reference_type="PURCHASE_INVOICE", reference_id=900,
        movement_date="2026-06-01", tenant=tenant)
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("7"), reference_type="PURCHASE_INVOICE", reference_id=901,
        movement_date="2026-06-02", tenant=tenant)
    product.refresh_from_db()
    # WAC: (10*5 + 10*7)/20 = 6 ; qty 20
    assert product.quantity_on_hand == Decimal("20.0000")
    assert product.avg_cost == Decimal("6.0000")

    unpost_document(
        tenant_id=tenant.TenantID,
        reference_id=901,
        journal_reference_types=["PURCHASE_INVOICE"],
        stock_reference_types=["PURCHASE_INVOICE"],
        user=owner,
    )

    product.refresh_from_db()
    # عادت لحالة ما قبل المستند 901: qty 10، متوسط 5
    assert product.quantity_on_hand == Decimal("10.0000")
    assert product.avg_cost == Decimal("5.0000")
    assert not StockMovement.objects.filter(reference_type="PURCHASE_INVOICE", reference_id=901).exists()
    assert StockMovement.objects.filter(reference_type="PURCHASE_INVOICE", reference_id=900).exists()


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def test_posted_sales_invoice_blocks_delete_then_unpost_allows_it(env):
    tenant, owner, ar, rev, customer, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="U-INV-1", customer=customer,
        currency=Currency.objects.get(Code="ILS"), invoice_date="2026-06-11",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("100.00"))

    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED

    # الحذف محظور على المرحّلة
    res = c.delete(f"/api/sales/invoices/{inv.id}/")
    assert res.status_code == 400
    assert res.json().get("can_unpost") is True

    # التراجع عن الترحيل يحذف القيد ويُرجعها مسودة
    res = c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json")
    assert res.status_code == 200, res.content
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_DRAFT
    assert inv.journal_id is None
    assert not JournalHeader.objects.filter(
        reference_type="SALES_INVOICE", reference_id=inv.id).exists()

    # الآن الحذف مسموح
    assert c.delete(f"/api/sales/invoices/{inv.id}/").status_code == 204
