"""Section B / Feature 2 — قيد الفاتورة يدين ذمم العميل بالكامل ولا يُسوّي النقدية.

المطلب (المالك — Feature 2): قيد الفاتورة (Entry A) يدين ذمم العميل بكامل
الإجمالي ويدائن الإيراد فقط. تحصيل النقدية أصبح سنداً مستقلاً «وصل دفع»
(CustomerPayment، Entry B: مدين النقدية / دائن ذمم العميل) لا يولّده ترحيل
الفاتورة إطلاقاً. لذا قيد فاتورة نقدية يلمس الذمم مديناً فقط — بلا سطر صندوق
ولا تسوية دائنة على الذمم.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year, partner_posted_balance, post_journal
from inventory.models import Product
from partners.models import Partner
from sales.models import CustomerPayment, SalesInvoice, SalesInvoiceLine, SupplierPayment
from sales.services import _resolve_ar_account, post_sales_invoice, post_supplier_payment
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="subl", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الذمم", owner)
    tenant._test_currency = ils
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-S", name="ذمم العميل", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="أشرف أبو الرجال", partner_type="Customer", linked_account=ar)
    cash = Account.objects.create(
        tenant=tenant, code="1110-S", name="الصندوق الرئيسي", account_type="Asset", is_active=True)
    product = Product.objects.create(
        tenant=tenant, sku="SB-1", name_ar="صنف", quantity_on_hand=100, avg_cost=10)
    return tenant, customer, cash, product, ar


def test_cash_sale_routes_through_customer_ar(env):
    tenant, customer, cash, product, ar = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="CASH-AR-1", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-11",
        invoice_type=SalesInvoice.INVOICE_CASH, cash_or_bank_account=cash,
        stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("1000.00"))
    post_sales_invoice(inv)
    inv.refresh_from_db()

    jl = list(inv.journal.lines.all())
    # القيد متوازن
    assert sum(l.debit for l in jl) == sum(l.credit for l in jl)

    ar_lines = [l for l in jl if l.account_id == ar.id]
    assert ar_lines, "البيع النقدي يجب أن يلمس حساب ذمم العميل"
    ar_debit = sum(l.debit for l in ar_lines)
    ar_credit = sum(l.credit for l in ar_lines)
    # Feature 2: ذمم العميل تُدين بكامل الفاتورة ولا تُسوّى داخل قيد الفاتورة
    assert ar_debit == inv.grand_total, "ذمم العميل تُدين بكامل قيمة الفاتورة"
    assert ar_credit == Decimal("0"), "ترحيل الفاتورة لا يُسوّي النقدية عبر الذمم"
    # كل أسطر الذمم تحمل العميل في الحقل المرجعي
    assert all(l.partner_id == customer.id for l in ar_lines)

    # توجيه الـsubledger: فقط سطر الذمم (الحساب الرقابي) يَحمل العميل؛ سطور
    # الإيراد/الضريبة/التكلفة بلا شريك وإلا تلوّث كشف حساب العميل.
    non_ar = [l for l in jl if l.account_id != ar.id]
    assert non_ar, "يجب أن يوجد سطر إيراد مقابل"
    assert all(l.partner_id is None for l in non_ar), \
        "سطور غير الذمم يجب ألا تَحمل العميل (وإلا تلوّث الـsubledger)"

    # Feature 2: لا سطر صندوق في قيد الفاتورة — التحصيل سند مستقل
    cash_debit = sum(l.debit for l in jl if l.account_id == cash.id)
    assert cash_debit == Decimal("0")


def test_credit_sale_customer_owed_equals_grand_total(env):
    """آجل: البيع بالأجل لا يُسوّى تلقائياً، فيبقى العميل مديناً بكامل الإجمالي.
    بعد إصلاح التوجيه يَحمل سطرُ الذمم وحده العميل، فيعكس partner_posted_balance
    المبلغ المستحق فعلاً (debit − credit == grand_total) بدل صفرٍ زائف كان
    يَنتج عن دائن الإيراد/المخزون المُلوِّث لو وُسِم بالعميل."""
    tenant, customer, cash, product, ar = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="CREDIT-AR-1", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-13",
        invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("1000.00"))
    post_sales_invoice(inv)
    inv.refresh_from_db()

    # لا تسوية تلقائية للبيع الآجل
    assert not CustomerPayment.objects.filter(partner=customer).exists()

    # سطر الذمم وحده يَحمل العميل
    jl = list(inv.journal.lines.all())
    assert all(
        l.partner_id == (customer.id if l.account_id == ar.id else None)
        for l in jl
    ), "فقط سطر الذمم يَحمل العميل"

    # العميل مدين بكامل الإجمالي — لا صفر زائف
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert (debit - credit) == inv.grand_total, \
        "البيع الآجل غير المحصَّل يجب أن يُظهر العميل مديناً بكامل الإجمالي"


def test_cash_sale_auto_settled_customer_not_debtor(env):
    """T-CASH2: ترحيل فاتورة بيع نقدية يُسوّيها تلقائياً بسند قبض مستقل، فلا يبقى
    العميل مديناً (رصيد الذمم الصافي = 0) وتصبح الفاتورة مدفوعة بالكامل."""
    tenant, customer, cash, product, ar = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="CASH-SETTLE-1", customer=customer,
        currency=tenant._test_currency, invoice_date="2026-06-12",
        invoice_type=SalesInvoice.INVOICE_CASH, cash_or_bank_account=cash,
        stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("1000.00"))
    post_sales_invoice(inv)
    inv.refresh_from_db()

    # سند قبض تلقائي أُنشئ ورُحّل بكامل قيمة الفاتورة
    pay = CustomerPayment.objects.filter(partner=customer, is_posted=True).first()
    assert pay is not None, "يجب إنشاء سند قبض تلقائي للبيع النقدي"
    assert pay.amount == inv.grand_total
    # الفاتورة مدفوعة بالكامل
    assert inv.amount_paid == inv.grand_total
    # رصيد العميل الصافي = 0 (لم يَعُد مديناً) — جوهر بلاغ المالك
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert (debit - credit) == Decimal("0"), "البيع النقدي يجب ألا يترك العميل مديناً"


def test_supplier_payment_zeroes_supplier_balance(env):
    """T-CASH2 (مرآة الموردين): سند الصرف يَسِم المورد على سطر الذمم فقط، أمّا سطر
    الصندوق فبلا شريك (partner=None). فبعد سداد ذمم دائنة كاملة يصبح رصيد المورد
    الصافي = 0 (دائن − مدين). الخطأ السابق: وَسْم سطر الصندوق بالمورد كان يَحسب
    حركة النقدية ضمن ذمم المورد فلا يُصفّر السند رصيده."""
    tenant, customer, cash, product, ar = env
    ap = Account.objects.create(
        tenant=tenant, code="2101-S", name="ذمم المورد",
        account_type="Liability", is_active=True)
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد الاختبار", partner_type="Supplier", linked_account=ap)
    inventory = Account.objects.create(
        tenant=tenant, code="1104-S", name="مخزون",
        account_type="Asset", is_active=True)

    amount = Decimal("700.00")
    # ذمم دائنة افتتاحية على المورد (محاكاة فاتورة شراء): Dr مخزون / Cr ذمم(المورد)
    post_journal(
        tenant_id=tenant.TenantID,
        transaction_date="2026-06-13",
        reference_type="PURCHASE_INVOICE",
        reference_id=999,
        description="فاتورة شراء افتتاحية",
        lines_data=[
            # سطر المخزون لا يَحمل المورد — فقط سطر الذمم (AP) يَسِم الشريك.
            {"account": inventory.id, "partner": None,
             "debit": amount, "credit": Decimal("0")},
            {"account": ap.id, "partner": supplier.id,
             "debit": Decimal("0"), "credit": amount},
        ],
        currency=tenant._test_currency,
        exchange_rate=Decimal("1"),
    )
    # المورد دائن بكامل المبلغ قبل الصرف
    debit, credit = partner_posted_balance(tenant.TenantID, supplier.id)
    assert (credit - debit) == amount

    payment = SupplierPayment.objects.create(
        tenant=tenant, partner=supplier, payment_date="2026-06-14",
        amount=amount, currency=tenant._test_currency, exchange_rate=Decimal("1"),
        cash_or_bank_account=cash, notes="صرف اختبار")
    post_supplier_payment(payment)
    payment.refresh_from_db()

    jl = list(payment.journal.lines.all())
    assert sum(l.debit for l in jl) == sum(l.credit for l in jl)
    # سطر الصندوق لا يَحمل المورد — جوهر الإصلاح
    cash_lines = [l for l in jl if l.account_id == cash.id]
    assert cash_lines and all(l.partner_id is None for l in cash_lines), \
        "سطر الصندوق في سند الصرف يجب ألا يَحمل المورد"
    # سطر الذمم يَحمل المورد
    ap_lines = [l for l in jl if l.account_id == ap.id]
    assert ap_lines and all(l.partner_id == supplier.id for l in ap_lines)
    # رصيد المورد الصافي = 0 (سُدِّدت الذمم بالكامل) — جوهر بلاغ المالك
    debit, credit = partner_posted_balance(tenant.TenantID, supplier.id)
    assert (credit - debit) == Decimal("0"), "سند الصرف يجب أن يُصفّر رصيد المورد"
