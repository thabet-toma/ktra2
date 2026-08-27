"""إصلاح بيانات قديمة — فاتورة بيع نقدية رُحِّلت بالكود القديم كانت تَسِم سطر
الصندوق بالعميل (Dr صندوق موسوم بالعميل / Cr إيراد، بلا سطر ذمم). فبقي في كشف
حساب العميل «تحصيل نقدي — <رقم>» مديناً بلا دائن مقابل ⇒ رصيد شبح لا يُصفَّر.

أمر `fix_legacy_cash_partner_tags` يُزيل وسم الشريك عن هذا السطر (الصندوق لا
يَحمل شريكاً) ويضبط `amount_paid` للفاتورة، فيُصفَّر رصيد العميل.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="legacycash", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة نقدي قديم", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-L", name="ذمم", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-L", name="إيراد", account_type="Revenue", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1110-L", name="صندوق", account_type="Asset", is_active=True)
    product = Product.objects.create(
        tenant=tenant, sku="LC-1", name_ar="منتج", quantity_on_hand=100, avg_cost=10)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل نقدي", partner_type="Customer", linked_account=ar)
    return tenant, ar, rev, cash, product, customer


def _legacy_cash_invoice(tenant, customer, cash, rev, product, *, grand=Decimal("250.00")):
    """يحاكي فاتورة بيع نقدية مُرحَّلة بالكود القديم: Dr صندوق (موسوم بالعميل) /
    Cr إيراد، بلا سطر ذمم، و amount_paid=0 (لم يضبطه الكود القديم)."""
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="SI-6-2", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-13",
        invoice_type=SalesInvoice.INVOICE_CASH, cash_or_bank_account=cash,
        stock_on_post=False, status=SalesInvoice.STATUS_POSTED,
        grand_total=grand, amount_paid=Decimal("0"),
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=grand)
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-13", is_posted=True,
        exchange_rate=Decimal("1"),
        reference_type="SALES_INVOICE", reference_id=inv.id)
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=cash, partner=customer,
        debit=grand, credit=Decimal("0"),
        description=f"تحصيل نقدي — {inv.invoice_number}")
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=rev, partner=None,
        debit=Decimal("0"), credit=grand,
        description=f"مبيعات — {inv.invoice_number}")
    inv.journal = jh
    inv.save(update_fields=["journal"])
    return inv


def test_legacy_cash_sale_leaves_phantom_debit(env):
    """قبل الإصلاح: العميل يظهر مديناً بـ 250 شبحاً بسبب وسم سطر الصندوق به."""
    tenant, ar, rev, cash, product, customer = env
    _legacy_cash_invoice(tenant, customer, cash, rev, product)
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert (debit - credit) == Decimal("250.00")


def test_fix_command_zeroes_customer_balance(env):
    tenant, ar, rev, cash, product, customer = env
    inv = _legacy_cash_invoice(tenant, customer, cash, rev, product)

    call_command("fix_legacy_cash_partner_tags", "--apply")

    # سطر الصندوق لم يَعُد يَحمل العميل
    cash_line = JournalLine.objects.get(
        journal__reference_type="SALES_INVOICE", account=cash,
        description__startswith="تحصيل نقدي")
    assert cash_line.partner_id is None

    # رصيد العميل الصافي = 0 — جوهر بلاغ المالك
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert (debit - credit) == Decimal("0")

    # الفاتورة صارت مدفوعة بالكامل (يتخطّاها backfill لاحقاً)
    inv.refresh_from_db()
    assert inv.amount_paid == inv.grand_total


def test_fix_command_is_idempotent_and_dry_run_safe(env):
    tenant, ar, rev, cash, product, customer = env
    _legacy_cash_invoice(tenant, customer, cash, rev, product)

    # dry-run لا يغيّر شيئاً
    call_command("fix_legacy_cash_partner_tags")
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert (debit - credit) == Decimal("250.00")

    # التطبيق ثم إعادته آمن (لا يقلب الرصيد سالباً)
    call_command("fix_legacy_cash_partner_tags", "--apply")
    call_command("fix_legacy_cash_partner_tags", "--apply")
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert (debit - credit) == Decimal("0")
