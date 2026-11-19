"""إعداد «فاتورة البيع بخسارة» (W1) — عند ضبط `SalesSettings.loss_invoice_policy` على
`block`، يُرفض **حفظ أو ترحيل** فاتورة بيع فيها **أي سطر** يُباع بخسارة (صافي البيع <
التكلفة المتوقَّعة لطريقة تكلفة المبيعات مع السقوط إلى متوسط التكلفة)، حتى لو كان
إجمالي الفاتورة رابحاً. `allow` = السماح بالحفظ والترحيل بخسارة. المراجيع مُعفاة.
`allow` افتراضياً فلا يؤثر على السلوك القائم. الحالة الوسطى `save_only` في
`test_stock_loss_policies.py`.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings
from sales.serializers import SalesInvoiceSerializer
from sales.services import post_sales_invoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="lossblk", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الخسارة", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-B", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    # المنتج تكلفته 100 — البيع بأقل منه = خسارة، وبأكثر = ربح.
    product = Product.objects.create(
        tenant=tenant, sku="LOSS-1", name_ar="منتج", quantity_on_hand=100, avg_cost=100)
    return tenant, customer, product


def _invoice(tenant, customer, product, *, unit_price, number):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-15",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal(str(unit_price)))
    return inv


def _settings(tenant, *, block):
    SalesSettings.objects.update_or_create(
        tenant=tenant, defaults={"loss_invoice_policy": (
            SalesSettings.POLICY_BLOCK if block else SalesSettings.POLICY_ALLOW)})


def test_loss_invoice_blocked_when_setting_on(env):
    tenant, customer, product = env
    _settings(tenant, block=True)
    inv = _invoice(tenant, customer, product, unit_price=80, number="LOSS-INV-1")
    with pytest.raises(ValidationError):
        post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status != SalesInvoice.STATUS_POSTED


def test_profit_invoice_allowed_when_setting_on(env):
    tenant, customer, product = env
    _settings(tenant, block=True)
    inv = _invoice(tenant, customer, product, unit_price=150, number="PROFIT-INV-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


def test_loss_invoice_allowed_when_setting_off(env):
    tenant, customer, product = env
    _settings(tenant, block=False)
    inv = _invoice(tenant, customer, product, unit_price=80, number="LOSS-OFF-1")
    post_sales_invoice(inv)
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED


# ── W1: الحارس على مستوى السطر + عند الحفظ (لا الترحيل فقط) ──

def _save_via_serializer(tenant, customer, product, *, lines, number,
                         kind=SalesInvoice.INVOICE_KIND_SALE,
                         date="2026-06-15"):
    """يحفظ فاتورة عبر السيريالايزر (مسار الحفظ الفعلي: create)."""
    data = {
        "invoice_number": number,
        "customer": customer.id,
        "currency": tenant._test_currency.pk,
        "invoice_date": date,
        "invoice_type": SalesInvoice.INVOICE_CREDIT,
        "stock_on_post": False,
        "invoice_kind": kind,
        "lines": lines,
    }
    ser = SalesInvoiceSerializer(data=data)
    ser.is_valid(raise_exception=True)
    return ser.save(tenant=tenant)


def _mixed_lines(product):
    """فاتورة رابحة إجمالاً لكن فيها سطر خاسر: 150 (ربح) + 80 (خسارة)، التكلفة 100."""
    return [
        {"product": product.id, "quantity": "1", "unit_price": "150"},
        {"product": product.id, "quantity": "1", "unit_price": "80"},
    ]


def test_profitable_invoice_with_loss_line_rejected_on_save_when_on(env):
    """(أ) فاتورة رابحة إجمالاً بها سطر واحد بخسارة تُرفض **عند الحفظ** والمفتاح مفعّل."""
    tenant, customer, product = env
    _settings(tenant, block=True)
    with pytest.raises(ValidationError):
        _save_via_serializer(tenant, customer, product,
                             lines=_mixed_lines(product), number="MIX-ON-1")
    # المعاملة تراجعت — لم تُحفظ الفاتورة.
    assert not SalesInvoice.objects.filter(tenant=tenant, invoice_number="MIX-ON-1").exists()


def test_profitable_invoice_with_loss_line_saved_when_off(env):
    """(ب) نفس الفاتورة تُحفظ حين المفتاح مطفأ (السماح بالخسارة)."""
    tenant, customer, product = env
    _settings(tenant, block=False)
    inv = _save_via_serializer(tenant, customer, product,
                               lines=_mixed_lines(product), number="MIX-OFF-1")
    assert SalesInvoice.objects.filter(pk=inv.pk).exists()


def test_return_with_loss_line_saved_when_on(env):
    """(ج) المرجع (sale_return) لا يخضع للحارس حتى مع سطر «خسارة» والمفتاح مفعّل."""
    tenant, customer, product = env
    _settings(tenant, block=True)
    inv = _save_via_serializer(
        tenant, customer, product,
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        lines=[{"product": product.id, "quantity": "1", "unit_price": "80"}],
        number="RET-ON-1",
    )
    assert SalesInvoice.objects.filter(pk=inv.pk).exists()


# ── M1B-4: حارس الخسارة يقارن بالتكلفة المتوقَّعة للطريقة ─────────────────

def test_loss_guard_uses_standard_cost_instead_of_avg_cost(env):
    """T7: standard_cost أعلى من السعر مع avg_cost أدنى منه ⇒ يُمنع؛ والعكس يُمرَّر."""
    tenant, customer, product = env
    SalesSettings.objects.update_or_create(
        tenant=tenant,
        defaults={
            "loss_invoice_policy": SalesSettings.POLICY_BLOCK,
            "cogs_cost_method": "standard",
        },
    )

    # standard_cost (120) > unit_price (100) بينما avg_cost (80) < unit_price (100) ⇒ يمنع
    product.avg_cost = Decimal("80")
    product.standard_cost = Decimal("120")
    product.save(update_fields=["avg_cost", "standard_cost"])

    with pytest.raises(ValidationError, match="تحتوي بنداً يُباع بخسارة"):
        _save_via_serializer(
            tenant, customer, product,
            lines=[{"product": product.id, "quantity": "1", "unit_price": "100"}],
            number="STD-BLK-1",
        )
    inv_blk = _invoice(tenant, customer, product, unit_price=100, number="STD-BLK-POST")
    with pytest.raises(ValidationError, match="تحتوي بنداً يُباع بخسارة"):
        post_sales_invoice(inv_blk)

    # العكس: standard_cost (80) < unit_price (100) بينما avg_cost (120) > unit_price (100) ⇒ يمرّ
    product.avg_cost = Decimal("120")
    product.standard_cost = Decimal("80")
    product.save(update_fields=["avg_cost", "standard_cost"])

    saved = _save_via_serializer(
        tenant, customer, product,
        lines=[{"product": product.id, "quantity": "1", "unit_price": "100"}],
        number="STD-PASS-1",
    )
    post_sales_invoice(saved)
    saved.refresh_from_db()
    assert saved.status == SalesInvoice.STATUS_POSTED


def test_loss_guard_last_purchase_uses_layer_on_or_before_invoice_date(env):
    """T8: last_purchase يقرأ أحدث طبقة شراء بتاريخ ≤ تاريخ الفاتورة ويتجاهل اللاحقة."""
    from inventory.tests.test_unpost_provisional_reconciliation import _receive

    tenant, customer, product = env
    SalesSettings.objects.update_or_create(
        tenant=tenant,
        defaults={
            "loss_invoice_policy": SalesSettings.POLICY_BLOCK,
            "cogs_cost_method": "last_purchase",
        },
    )

    # طبقة سابقة لتاريخ الفاتورة (2026-06-15) بتكلفة 120، وطبقة لاحقة (2026-06-20) بتكلفة 50
    _receive(product, "5", "120", 3001, date="2026-06-10")
    _receive(product, "5", "50", 3002, date="2026-06-20")
    product.avg_cost = Decimal("50")
    product.save(update_fields=["avg_cost"])

    # تاريخ الفاتورة 2026-06-15 ⇒ يقرأ 120 (ويتجاهل 50 اللاحقة) ⇒ يمنع بيع 100
    with pytest.raises(ValidationError, match="تحتوي بنداً يُباع بخسارة"):
        _save_via_serializer(
            tenant, customer, product,
            lines=[{"product": product.id, "quantity": "1", "unit_price": "100"}],
            number="LP-BLK-1",
        )

    # تاريخ الفاتورة 2026-06-25 ⇒ يقرأ 50 ⇒ يمرّ
    inv_pass = _save_via_serializer(
        tenant, customer, product,
        lines=[{"product": product.id, "quantity": "1", "unit_price": "100"}],
        number="LP-PASS-1",
        date="2026-06-25",
    )
    assert inv_pass.pk is not None


def test_loss_guard_standard_without_standard_cost_falls_back_to_avg_cost(env):
    """T9: standard مع standard_cost=None يسقط إلى avg_cost."""
    tenant, customer, product = env
    SalesSettings.objects.update_or_create(
        tenant=tenant,
        defaults={
            "loss_invoice_policy": SalesSettings.POLICY_BLOCK,
            "cogs_cost_method": "standard",
        },
    )

    product.standard_cost = None
    product.avg_cost = Decimal("120")
    product.save(update_fields=["standard_cost", "avg_cost"])
    with pytest.raises(ValidationError, match="تحتوي بنداً يُباع بخسارة"):
        _save_via_serializer(
            tenant, customer, product,
            lines=[{"product": product.id, "quantity": "1", "unit_price": "100"}],
            number="STD-NONE-BLK",
        )

    product.avg_cost = Decimal("80")
    product.save(update_fields=["avg_cost"])
    inv = _save_via_serializer(
        tenant, customer, product,
        lines=[{"product": product.id, "quantity": "1", "unit_price": "100"}],
        number="STD-NONE-PASS",
    )
    assert inv.pk is not None


def test_loss_guard_last_purchase_handles_none_invoice_date(env):
    """invoice_date=None في last_purchase يسقط إلى localdate() بدل تعثّر ORM بـ layer_date__lte=None."""
    from django.utils.timezone import localdate
    from inventory.tests.test_unpost_provisional_reconciliation import _receive

    tenant, customer, product = env
    SalesSettings.objects.update_or_create(
        tenant=tenant,
        defaults={
            "loss_invoice_policy": SalesSettings.POLICY_BLOCK,
            "cogs_cost_method": "last_purchase",
        },
    )
    _receive(product, "5", "120", 3003, date=str(localdate()))
    product.avg_cost = Decimal("50")
    product.save(update_fields=["avg_cost"])

    inv = SalesInvoice(
        tenant=tenant, invoice_number="LP-NODATE", customer=customer,
        currency=tenant._test_currency, invoice_date=None,
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    line = SalesInvoiceLine(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("100"),
        line_total_excl_tax=Decimal("100"),
    )
    from sales.services.calc import guard_loss_invoice
    with pytest.raises(ValidationError, match="تحتوي بنداً يُباع بخسارة"):
        guard_loss_invoice(inv, [line], {product.id: product}, stage=SalesSettings.STAGE_SAVE)
