"""مرجع الشراء (create_purchase_return): يُخرج الكمية من المخزن ويعكس قيد الشراء.

يتحقق أن:
  - حركة RETURN_OUT تُنقص المخزون بالكمية المرتجعة.
  - القيد يَدين ذمم المورد (AP) ويَدائن المخزون — عكس استلام الشراء.
  - الفاتورة المرجَعة تُحفظ is_return=True ومُرحّلة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.services import create_purchase_return, post_purchase_return
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="retpur", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة مرجع الشراء", owner)
    tenant._cur = ils
    create_fiscal_year(tenant, 2026)
    # شجرة الحسابات مبذورة عند إنشاء الشركة — نستخدم 2101 (ذمم موردين) و1104 (مخزون).
    ap = Account.objects.filter(tenant=tenant, code="2101").first()
    inv = Account.objects.filter(tenant=tenant, code="1104").first()
    assert ap is not None and inv is not None, "seed missing 2101/1104"
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد", partner_type="Supplier", linked_account=ap)
    product = Product.objects.create(
        tenant=tenant, sku="RET-P", name_ar="منتج", quantity_on_hand=Decimal("10"),
        avg_cost=Decimal("50"))
    return tenant, supplier, product, ap, inv


def test_purchase_return_draft_then_post(env):
    tenant, supplier, product, ap, inv = env
    ret = create_purchase_return(
        tenant,
        original_invoice=None,
        partner=supplier,
        return_date="2026-06-15",
        lines=[{"product": product.id, "quantity": 4, "unit_price": 50}],
    )
    product.refresh_from_db()
    # مرحلة الحفظ: مسودة — لا مخزون ولا قيد.
    assert ret.is_return is True
    assert ret.is_posted is False
    assert ret.status == "draft"
    assert product.quantity_on_hand == Decimal("10")

    # مرحلة الترحيل: تُخرج الكمية وتُنشئ القيد العكسي.
    post_purchase_return(ret, user=None)
    ret.refresh_from_db()
    product.refresh_from_db()
    assert ret.is_posted is True
    assert product.quantity_on_hand == Decimal("6")

    ap_line = JournalLine.objects.filter(journal=ret.journal, account=ap).first()
    inv_line = JournalLine.objects.filter(journal=ret.journal, account=inv).first()
    assert ap_line is not None and Decimal(str(ap_line.debit)) == Decimal("200")
    assert inv_line is not None and Decimal(str(inv_line.credit)) == Decimal("200")


def test_purchase_return_requires_positive_line(env):
    tenant, supplier, product, _ap, _inv = env
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        create_purchase_return(
            tenant, original_invoice=None, partner=supplier,
            return_date="2026-06-15",
            lines=[{"product": product.id, "quantity": 0, "unit_price": 50}],
        )


def _original_invoice(tenant, supplier, product, *, qty, price=50):
    from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PINV-ORIG", invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, is_return=False,
    )
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=product, name="منتج",
        quantity=Decimal(str(qty)), unit_price=Decimal(str(price)),
        total_price=Decimal(str(qty * price)),
    )
    return inv


# ── W6: حارس تجاوز الكمية المرتجعة الكمية الأصلية المفوترة (server-side) ──

def test_return_exceeding_invoiced_qty_rejected(env):
    """مرجع بكمية أكبر من المفوترة (12 من أصل 10) يُرفض."""
    tenant, supplier, product, _ap, _inv = env
    orig = _original_invoice(tenant, supplier, product, qty=10)
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        create_purchase_return(
            tenant, original_invoice=orig, partner=supplier,
            return_date="2026-06-15",
            lines=[{"product": product.id, "quantity": 12, "unit_price": 50}],
        )


def test_cumulative_returns_cannot_exceed_invoiced_qty(env):
    """مجموع المراجيع لا يتجاوز المفوتر: 6 مسموح، ثم 5 (المجموع 11>10) مرفوض."""
    tenant, supplier, product, _ap, _inv = env
    orig = _original_invoice(tenant, supplier, product, qty=10)
    create_purchase_return(
        tenant, original_invoice=orig, partner=supplier,
        return_date="2026-06-15",
        lines=[{"product": product.id, "quantity": 6, "unit_price": 50}],
    )
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        create_purchase_return(
            tenant, original_invoice=orig, partner=supplier,
            return_date="2026-06-16",
            lines=[{"product": product.id, "quantity": 5, "unit_price": 50}],
        )


def test_return_up_to_invoiced_qty_allowed(env):
    """مرجع بكامل الكمية المفوترة (10 من 10) مسموح."""
    tenant, supplier, product, _ap, _inv = env
    orig = _original_invoice(tenant, supplier, product, qty=10)
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier,
        return_date="2026-06-15",
        lines=[{"product": product.id, "quantity": 10, "unit_price": 50}],
    )
    assert ret.is_return is True


def test_returnable_lines_reports_invoiced_returned_remaining(env):
    """W6: منتقي بنود المرجع يعرض المفوتر/المرتجع/المتبقّي بدقة بعد مرجع جزئي."""
    from logistics.services import returnable_lines_for_invoice
    tenant, supplier, product, _ap, _inv = env
    orig = _original_invoice(tenant, supplier, product, qty=10)
    create_purchase_return(
        tenant, original_invoice=orig, partner=supplier,
        return_date="2026-06-15",
        lines=[{"product": product.id, "quantity": 4, "unit_price": 50}],
    )
    rows = returnable_lines_for_invoice(orig)
    assert len(rows) == 1
    row = rows[0]
    assert row["product"] == product.id
    assert Decimal(row["invoiced_qty"]) == Decimal("10")
    assert Decimal(row["returned_qty"]) == Decimal("4")
    assert Decimal(row["remaining_qty"]) == Decimal("6")


# ── مرتجع الفاتورة الدولية: عكسٌ بنسبة قيدها — لا الإجمالي المحمَّل على المورد ──

def _posted_international(tenant, supplier, product, ap, inv):
    """فاتورة دولية مرحّلة: 10 وحدات × 100 ₪ محمَّلة = 1,000 — المورد دائنٌ بحصّته 700،
    والشحن 200 والتخليص 100 عادا إلى حساباتهما (`import_invoice_accrual_credits`)."""
    from accounting.models import JournalHeader
    from logistics.models import PurchaseInvoice, PurchaseInvoiceItem

    freight = Account.objects.create(tenant=tenant, code="5301-R", name="شحن", account_type="Expense")
    clearance = Account.objects.create(tenant=tenant, code="5307-R", name="تخليص", account_type="Expense")
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-01", is_posted=True, exchange_rate=Decimal("1"),
        reference_type="PURCHASE_INVOICE", reference_id=None)
    for account, debit, credit, partner in (
        (inv, 1000, 0, None), (supplier.linked_account, 0, 700, supplier),
        (freight, 0, 200, None), (clearance, 0, 100, None),
    ):
        JournalLine.objects.create(
            tenant=tenant, journal=jh, account=account, debit=Decimal(debit), credit=Decimal(credit),
            partner=partner)
    orig = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PI-INT", invoice_date="2026-06-01", partner=supplier,
        currency=tenant._cur, invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
        subtotal=Decimal("1000"), grand_total=Decimal("1000"), is_posted=True, journal=jh)
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product, name="منتج", quantity=Decimal("10"),
        unit_price=Decimal("100"), total_price=Decimal("1000"), landed_unit_price_ils=Decimal("100"))
    return orig, freight, clearance


def test_international_return_reverses_the_invoice_journal_in_proportion(env):
    """مرتجع 3 من 10: المورد يُدان بحصّته (210) لا بالمحمَّل (300)، والشحن والتخليص بحصّتهما،
    والمخزون يُدائَن بالمحمَّل. كان يدين ذمّة المورد 300 كاملةً — 90 ليست له."""
    from logistics.models import PurchaseInvoice
    tenant, supplier, product, ap, inv = env
    orig, freight, clearance = _posted_international(tenant, supplier, product, ap, inv)

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        # السعر المُرسَل لا يُصدَّق للدولية: سعر الأصل المحمَّل وحده.
        lines=[{"product": product.id, "quantity": 3, "unit_price": 999}],
    )
    assert ret.invoice_type == PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL
    assert (ret.grand_total, ret.tax_amount) == (Decimal("210.00"), Decimal("0.00"))
    assert ret.items.get().unit_price == Decimal("100")

    post_purchase_return(ret, user=None)
    ret.refresh_from_db()
    lines = {
        (l.account_id, l.partner_id): (Decimal(str(l.debit)), Decimal(str(l.credit)))
        for l in JournalLine.objects.filter(journal=ret.journal)
    }
    assert lines == {
        (supplier.linked_account_id, supplier.id): (Decimal("210.00"), Decimal("0")),
        (freight.id, None): (Decimal("60.00"), Decimal("0")),
        (clearance.id, None): (Decimal("30.00"), Decimal("0")),
        (inv.id, None): (Decimal("0"), Decimal("300.00")),
    }
    assert ret.grand_total == Decimal("210.00")


def test_international_return_carries_its_dollars_in_the_same_proportion(env):
    """دائن المورد في الأصل 700 ₪ = 200$؛ مرتجعٌ يدينه 210 ₪ ⇒ 60$ بالنسبة نفسها."""
    tenant, supplier, product, ap, inv = env
    orig, _f, _c = _posted_international(tenant, supplier, product, ap, inv)
    JournalLine.objects.filter(journal=orig.journal, partner=supplier).update(
        amount_currency=Decimal("-200.00"), currency_code="USD")

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        lines=[{"product": product.id, "quantity": 3, "unit_price": 100}],
    )
    post_purchase_return(ret, user=None)
    ret.refresh_from_db()
    line = JournalLine.objects.get(journal=ret.journal, partner=supplier)
    assert (line.debit, line.amount_currency, line.currency_code) == (
        Decimal("210.00"), Decimal("60.00"), "USD")


def test_international_return_needs_the_posted_invoice(env):
    from django.core.exceptions import ValidationError
    tenant, supplier, product, ap, inv = env
    orig, _f, _c = _posted_international(tenant, supplier, product, ap, inv)
    orig.is_posted = False
    orig.journal = None
    orig.save(update_fields=["is_posted", "journal"])
    with pytest.raises(ValidationError, match="رحّل"):
        create_purchase_return(
            tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
            lines=[{"product": product.id, "quantity": 1, "unit_price": 100}])
