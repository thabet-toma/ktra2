"""مواصفة #137 (المرحلة 3) — قيدُ تكلفة المبيعات يطابق كلفة FIFO الفعليّة.

`inventory.services.record_stock_movement` صار يسجّل `StockMovement.total_cost`
من الطبقات المستهلَكة فعلاً (FIFO، #137 المرحلة 2 — منجزة). كان
`sales/services/calc.py` لا يزال يبني قيد ت.ب.م من `qty × Product.avg_cost` —
رقمٌ صحيح تحت المتوسط المرجَّح فقط، وتحت FIFO ينحرف عن الحركة الفعلية كلّما
عبرت البيعة طبقتين بسعرين مختلفين، بل ويسقط صفراً حين تُستهلك كل الطبقات
المفتوحة قبل بناء القيد.

هذا الملف يحرس أن الأرقام الثلاثة دائماً رقمٌ واحد: مدين حساب ت.ب.م في قيد
الفاتورة/الإرسالية = مجموع `StockMovement.total_cost` لحركات هذا المستند =
ما تُرجعه `sales_cogs_map` له.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APIClient

from accounting.models import Account, JournalLine, VoidedJournal
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import DeliveryOrder, SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings, sales_cogs_map
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

Q2 = Decimal("0.01")


@pytest.fixture
def env():
    owner = User.objects.create_user(username="fifocogs", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة تكلفة FIFO", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-FC", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل FIFO", partner_type="Customer", linked_account=ar)
    cogs = Account.objects.create(
        tenant=tenant, code="5101-FC", name="تكلفة مبيعات", account_type="Expense",
        is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-FC", name="مخزون", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-FC", name="مبيعات", account_type="Revenue", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = cogs
    ss.default_inventory_account = inv_acc
    ss.default_revenue_account_product = rev
    ss.save(update_fields=[
        "default_cogs_account", "default_inventory_account",
        "default_revenue_account_product",
    ])
    return tenant, owner, cur, customer, cogs, inv_acc, rev


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _new_product(tenant, sku):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=f"منتج {sku}",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )


def _receive(tenant, product, qty, unit_cost, *, date):
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal(qty),
        unit_cost=Decimal(unit_cost), reference_type="OPENING", reference_id=0,
        movement_date=date, tenant=tenant,
    )


def _cogs_debit_total(journal_id, cogs_account) -> Decimal:
    total = JournalLine.objects.filter(
        journal_id=journal_id, account=cogs_account, debit__gt=0,
    ).aggregate(t=Sum("debit"))["t"]
    return Decimal(str(total or 0)).quantize(Q2)


def _movement_cost_total(reference_type, reference_id) -> Decimal:
    total = StockMovement.objects.filter(
        reference_type=reference_type, reference_id=reference_id,
    ).aggregate(t=Sum("total_cost"))["t"]
    return Decimal(str(total or 0)).quantize(Q2)


def _cogs_map_total(tenant, invoice_id) -> Decimal:
    cmap = sales_cogs_map(tenant_id=tenant.TenantID, invoice_ids=[invoice_id])
    return sum((v["cost"] for v in cmap.values()), Decimal("0")).quantize(Q2)


# ─────────────────────────────────────────────────────────────────────────
# الاختبار المركزي: بيعة تعبر طبقتين بسعرين مختلفين.
# ─────────────────────────────────────────────────────────────────────────

def test_fifo_cost_crossing_two_layers_matches_journal_movement_and_cogs_map(env):
    """استلم 50@10 ثم 20@60، وبِع 60 في فاتورة واحدة — الكلفة الحقيقية FIFO =
    50×10 + 10×60 = 1100، لا متوسط 60×24.2857 ≈ 1457.14."""
    tenant, owner, cur, customer, cogs, inv_acc, rev = env
    product = _new_product(tenant, "FC-1")
    _receive(tenant, product, "50", "10", date="2026-06-01")
    _receive(tenant, product, "20", "60", date="2026-06-02")

    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="FC-INV-1", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=True)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("60"), unit_price=Decimal("100"))

    c = _client(owner, tenant)
    res = c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    assert res.status_code == 200, res.data

    inv.refresh_from_db()
    expected = Decimal("1100.00")
    assert _cogs_debit_total(inv.journal_id, cogs) == expected
    assert _movement_cost_total("SALE", inv.id) == expected
    assert _cogs_map_total(tenant, inv.id) == expected


def test_fifo_cost_single_layer_is_the_simple_case(env):
    """بيعةٌ داخل طبقةٍ واحدة — القيد والحركة والخريطة كلّها متطابقة، بلا تعقيد."""
    tenant, owner, cur, customer, cogs, inv_acc, rev = env
    product = _new_product(tenant, "FC-2")
    _receive(tenant, product, "100", "15", date="2026-06-01")

    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="FC-INV-2", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=True)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("10"), unit_price=Decimal("50"))

    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200

    inv.refresh_from_db()
    expected = Decimal("150.00")  # 10 × 15
    assert _cogs_debit_total(inv.journal_id, cogs) == expected
    assert _movement_cost_total("SALE", inv.id) == expected
    assert _cogs_map_total(tenant, inv.id) == expected


def test_partial_delivery_cogs_matches_delivered_layers_only(env):
    """تسليمٌ جزئيّ: ت.ب.م على المُسلَّم فعلاً وبكلفة طبقاته هو، لا كامل السطر."""
    tenant, owner, cur, customer, cogs, inv_acc, rev = env
    product = _new_product(tenant, "FC-3")
    _receive(tenant, product, "5", "10", date="2026-06-01")
    _receive(tenant, product, "10", "50", date="2026-06-02")

    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="FC-INV-3", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False)
    line = SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("12"), unit_price=Decimal("100"))

    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    # الفاتورة لا تخصم المخزون عند الترحيل ⇒ لا حركة ولا ت.ب.م بعد الترحيل وحده.
    assert not StockMovement.objects.filter(reference_type="SALE", reference_id=inv.id).exists()

    res = c.post(
        f"/api/sales/invoices/{inv.id}/deliver/",
        {"lines": [{"line_id": line.id, "quantity": 8}]}, format="json")
    assert res.status_code in (200, 201), res.data

    expected = Decimal("200.00")  # 5×10 + 3×50 — الطبقتان اللتان يعبرهما تسليم 8 وحدات
    delivery = DeliveryOrder.objects.filter(invoice=inv).latest("id")
    assert _cogs_debit_total(delivery.journal_id, cogs) == expected
    assert _movement_cost_total("SALE", inv.id) == expected
    assert _cogs_map_total(tenant, inv.id) == expected


def test_unpost_repost_reproduces_identical_fifo_cost(env):
    """إلغاء الترحيل ثمّ إعادته: القيد الثاني يحمل نفس رقم الأوّل بالضبط —
    الطبقات عادت لمواقعها فالاستهلاك يتكرّر مطابقاً."""
    tenant, owner, cur, customer, cogs, inv_acc, rev = env
    product = _new_product(tenant, "FC-4")
    _receive(tenant, product, "50", "10", date="2026-06-01")
    _receive(tenant, product, "20", "60", date="2026-06-02")

    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="FC-INV-4", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=True)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("60"), unit_price=Decimal("100"))

    c = _client(owner, tenant)
    expected = Decimal("1100.00")

    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    first_journal_id = inv.journal_id
    assert _cogs_debit_total(first_journal_id, cogs) == expected

    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200
    assert not StockMovement.objects.filter(reference_type="SALE", reference_id=inv.id).exists()
    assert VoidedJournal.objects.get(
        tenant=tenant, reference_type="SALES_INVOICE", reference_id=inv.id,
    ).original_journal_id == first_journal_id

    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    assert inv.journal_id == first_journal_id
    assert _cogs_debit_total(inv.journal_id, cogs) == expected
    assert _movement_cost_total("SALE", inv.id) == expected
    assert _cogs_map_total(tenant, inv.id) == expected


def test_service_product_has_no_movement_and_no_cogs_row(env):
    """منتج خدمة في الفاتورة — لا سطر ت.ب.م له ولا حركة مخزون."""
    tenant, owner, cur, customer, cogs, inv_acc, rev = env
    product = _new_product(tenant, "FC-5")
    _receive(tenant, product, "10", "20", date="2026-06-01")
    service = Product.objects.create(
        tenant=tenant, sku="FC-5-SVC", name_ar="خدمة توصيل", is_service=True)

    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="FC-INV-5", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=True)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("3"), unit_price=Decimal("50"))
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=service,
        quantity=Decimal("1"), unit_price=Decimal("200"))

    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    inv.refresh_from_db()

    assert not StockMovement.objects.filter(
        reference_type="SALE", reference_id=inv.id, product=service).exists()
    assert StockMovement.objects.filter(
        reference_type="SALE", reference_id=inv.id, product=product).count() == 1

    expected = Decimal("60.00")  # 3 × 20 — كلفة المنتج وحده، الخدمة بلا كلفة مخزون
    assert _cogs_debit_total(inv.journal_id, cogs) == expected
    assert _movement_cost_total("SALE", inv.id) == expected
    assert _cogs_map_total(tenant, inv.id) == expected
