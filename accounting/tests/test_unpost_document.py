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
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine, VoidedJournal
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
        tenant=tenant, sku="U-1", name_ar="منتج", quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
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


def test_unpost_blocked_when_later_sale_consumed_stock(env):
    """التراجع عن مستند مُورِّد للمخزون يُمنع إن استهلكت مبيعات لاحقة رصيده/تكلفته،
    ولا يُحذف شيء (إجهاض ذرّي) — والرسالة تذكر المستند المتأثّر."""
    tenant, owner, ar, rev, customer, product = env
    _post_simple_journal(tenant, ar, rev, "PURCHASE_INVOICE", 905)
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), reference_type="PURCHASE_INVOICE", reference_id=905,
        movement_date="2026-06-01", tenant=tenant)
    # بيع لاحق يستهلك المخزون (حركة OUT مرجعها فاتورة بيع #770)
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("4"),
        unit_cost=Decimal("5"), reference_type="SALE", reference_id=770,
        movement_date="2026-06-05", tenant=tenant)

    with pytest.raises(DjangoValidationError) as exc:
        unpost_document(
            tenant_id=tenant.TenantID,
            reference_id=905,
            journal_reference_types=["PURCHASE_INVOICE"],
            stock_reference_types=["PURCHASE_INVOICE"],
            user=owner,
        )
    assert "770" in str(exc.value)  # المستند المعتمِد مذكور في الرسالة
    # لم يُحذف شيء: قيد الشراء وحركته باقيان
    assert JournalHeader.objects.filter(reference_type="PURCHASE_INVOICE", reference_id=905).exists()
    assert StockMovement.objects.filter(reference_type="PURCHASE_INVOICE", reference_id=905).exists()


def test_unpost_consumer_document_allowed(env):
    """التراجع عن مستند مستهلِك (فاتورة بيع) مسموح — لا تابعين له — فيُحذف قيده
    وحركته دون المساس بمخزون الشراء الذي صرف منه."""
    tenant, owner, ar, rev, customer, product = env
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), reference_type="PURCHASE_INVOICE", reference_id=906,
        movement_date="2026-06-01", tenant=tenant)
    _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 780)
    record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("3"),
        unit_cost=Decimal("5"), reference_type="SALE", reference_id=780,
        movement_date="2026-06-06", tenant=tenant)

    unpost_document(
        tenant_id=tenant.TenantID,
        reference_id=780,
        journal_reference_types=["SALES_INVOICE", "SALES_DELIVERY_COGS"],
        stock_reference_types=["SALE", "STOCK_ISSUE"],
        user=owner,
    )
    assert not JournalHeader.objects.filter(reference_type="SALES_INVOICE", reference_id=780).exists()
    assert not StockMovement.objects.filter(reference_type="SALE", reference_id=780).exists()
    # حركة الشراء التي صُرف منها لم تُمَسّ
    assert StockMovement.objects.filter(reference_type="PURCHASE_INVOICE", reference_id=906).exists()


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


# ── Feature 2 — حجز رقم القيد وإعادة استخدامه عند إعادة الترحيل ──────────────

def test_recycle_reserves_then_repost_reuses_same_number(env):
    """post → unpost(recycle) → الرقم محجوز → re-post يُعيد نفس الرقم نصّاً."""
    tenant, owner, ar, rev, customer, product = env
    original = _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 3001)
    original_id = original.id

    unpost_document(
        tenant_id=tenant.TenantID,
        reference_id=3001,
        journal_reference_types=["SALES_INVOICE", "SALES_DELIVERY_COGS"],
        user=owner,
        recycle=True,
    )

    # القيد الحيّ حُذِف، والرقم محجوز في سلّة المحذوفات
    assert not JournalHeader.objects.filter(pk=original_id).exists()
    res = VoidedJournal.objects.get(
        tenant_id=tenant.TenantID, reference_type="SALES_INVOICE", reference_id=3001)
    assert res.original_journal_id == original_id

    # إعادة الترحيل تُعيد نفس الرقم وتستهلك الحجز
    reposted = _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 3001)
    assert reposted.id == original_id
    assert not VoidedJournal.objects.filter(
        tenant_id=tenant.TenantID, reference_type="SALES_INVOICE", reference_id=3001).exists()
    assert JournalHeader.objects.filter(pk=original_id).count() == 1


def test_recycle_reserves_only_primary_journal(env):
    """مستند بقيدين (فاتورة + تكلفة مبيعات): يُحجز رقم القيد الأساسي فقط."""
    tenant, owner, ar, rev, customer, product = env
    primary = _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 3100)
    cogs = _post_simple_journal(tenant, ar, rev, "SALES_DELIVERY_COGS", 3100)

    unpost_document(
        tenant_id=tenant.TenantID,
        reference_id=3100,
        journal_reference_types=["SALES_INVOICE", "SALES_DELIVERY_COGS"],
        user=owner,
        recycle=True,
    )

    reservations = VoidedJournal.objects.filter(tenant_id=tenant.TenantID, reference_id=3100)
    assert reservations.count() == 1
    res = reservations.get()
    assert res.reference_type == "SALES_INVOICE"
    assert res.original_journal_id == primary.id
    # القيد الفرعي حُذِف دون حجز
    assert not JournalHeader.objects.filter(pk=cogs.id).exists()


def test_unpost_without_recycle_creates_no_reservation(env):
    """السلوك الافتراضي (recycle=False) لا يحجز أي رقم."""
    tenant, owner, ar, rev, customer, product = env
    _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 3200)
    unpost_document(
        tenant_id=tenant.TenantID,
        reference_id=3200,
        journal_reference_types=["SALES_INVOICE"],
        user=owner,
    )
    assert not VoidedJournal.objects.filter(
        tenant_id=tenant.TenantID, reference_id=3200).exists()


def test_repost_falls_back_to_new_number_when_reserved_id_occupied(env):
    """إن كان الرقم المحجوز مشغولاً (حالة غير متوقعة): يسقط لرقم جديد + يستهلك الحجز."""
    tenant, owner, ar, rev, customer, product = env
    occupant = _post_simple_journal(tenant, ar, rev, "PURCHASE_INVOICE", 4000)
    # حجز يدوي يشير إلى رقم مشغول فعلاً
    VoidedJournal.objects.create(
        tenant_id=tenant.TenantID, original_journal_id=occupant.id,
        reference_type="SALES_INVOICE", reference_id=4001)

    reposted = _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 4001)
    assert reposted.id != occupant.id  # لم يَدُس على القيد المشغول
    assert JournalHeader.objects.filter(pk=occupant.id).exists()  # المشغول سليم
    assert not VoidedJournal.objects.filter(
        tenant_id=tenant.TenantID, reference_id=4001).exists()  # الحجز استُهلِك


def test_sales_invoice_repost_reuses_journal_number_via_api(env):
    """E2E عبر نقاط النهاية: post → unpost → re-post يُعيد نفس رقم القيد."""
    tenant, owner, ar, rev, customer, product = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="U-INV-RE", customer=customer,
        currency=Currency.objects.get(Code="ILS"), invoice_date="2026-06-11",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("100.00"))
    c = _client(owner, tenant)

    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    first_journal_id = inv.journal_id
    assert first_journal_id is not None

    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    assert inv.journal_id is None
    assert VoidedJournal.objects.get(
        tenant_id=tenant.TenantID, reference_type="SALES_INVOICE",
        reference_id=inv.id).original_journal_id == first_journal_id

    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    assert inv.journal_id == first_journal_id  # نفس الرقم بالضبط
    assert not VoidedJournal.objects.filter(
        tenant_id=tenant.TenantID, reference_id=inv.id).exists()
