"""بيئة اختبار مشتركة لـ`docshare`.

القيم المزروعة هنا **أسرارٌ تجارية بأرقام مميّزة** لا أرقام عادية: التكلفة
`1234.56` والملاحظة الداخلية نصٌّ فريد. الغرض أن يقدر اختبار التسريب على
البحث عنها حرفياً في الصفحة المُصيَّرة، فوجودها إخفاقٌ لا لبس فيه.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from inventory.models import Product, UnitOfMeasure
from partners.models import Partner
from sales.models import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesQuotation,
    SalesQuotationLine,
)
from tenants.models import Currency
from tenants.services import create_company

#: التكلفة المزروعة — رقمٌ لا يظهر مصادفةً في صفحةٍ سليمة.
SECRET_COST = Decimal("1234.56")
#: ملاحظة البائع لنفسه. `sales.models` (`SalesInvoiceLine`) يفصلها بنيوياً عن
#: `customer_note`، وهذا الاختبار يثبت أن الفصل صمد على السطح العام أيضاً.
SECRET_INTERNAL_NOTE = "ملاحظة-داخلية-لا-تخرج-أبدا"
CUSTOMER_NOTE = "ملاحظة تظهر للزبون"


@pytest.fixture
def base_currency(db):
    return Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True,
    )


@pytest.fixture
def env(db, base_currency):
    """شركة كاملة بفاتورة بيع وعرض سعر — والمنتج يحمل تكلفةً سرّية."""
    owner = User.objects.create_user(username="share-owner", password="x")
    tenant = create_company("شركة المشاركة", owner)
    receivable = Account.objects.create(
        tenant=tenant, code="1101-SH", name="ذمم", account_type="Asset", is_active=True,
    )
    customer = Partner.objects.create(
        tenant=tenant, name="زبون المشاركة", partner_type="Customer",
        linked_account=receivable, phone="0599000000", street_address="شارع الاختبار",
        city="نابلس",
    )
    uom = UnitOfMeasure.objects.create(code="PC-SH", name_ar="قطعة", name_en="Piece")
    product = Product.objects.create(
        tenant=tenant, sku="SH-1", name_ar="منتج المشاركة", name_en="Shared Item",
        uom=uom, quantity_on_hand=Decimal("100"), avg_cost=SECRET_COST,
    )
    return {
        "owner": owner,
        "tenant": tenant,
        "currency": base_currency,
        "customer": customer,
        "product": product,
    }


@pytest.fixture
def invoice(env):
    inv = SalesInvoice.objects.create(
        tenant=env["tenant"], invoice_number="SH-INV-1", customer=env["customer"],
        currency=env["currency"], invoice_date="2026-08-01",
        exchange_rate=Decimal("1"), invoice_type=SalesInvoice.INVOICE_CREDIT,
        subtotal_excl_tax=Decimal("100"), tax_amount=Decimal("16"),
        grand_total=Decimal("116"), notes="شكراً لتعاملكم معنا",
    )
    SalesInvoiceLine.objects.create(
        tenant=env["tenant"], invoice=inv, product=env["product"],
        quantity=Decimal("2"), unit_price=Decimal("50"),
        line_total_excl_tax=Decimal("100"), line_tax_amount=Decimal("16"),
        internal_note=SECRET_INTERNAL_NOTE, customer_note=CUSTOMER_NOTE,
    )
    return inv


#: عيّنة واحدة لكل `doc_type` مسجَّل. `test_public_leakage` يقيس مجموعة مفاتيحها
#: بمجموعة `DOC_TYPES` — فنوعٌ يُسجَّل بلا عيّنة يُسقِط المجموعة **يوم تسجيله**
#: لا يوم يتذكّر أحدٌ أن يكتب له اختباراً.
SAMPLE_FIXTURES = {
    "sales_invoice": "invoice",
    "sales_quotation": "quotation",
    "purchase_invoice": "purchase_invoice",
    "purchase_order": "purchase_order",
    "logistics_deal": "deal",
    "supplier_quotation": "supplier_offer",
    "local_purchase_invoice": "local_purchase_invoice",
    "sales_order": "sales_order",
    "delivery_order": "delivery_order",
    "customer_payment": "customer_payment",
    "supplier_payment": "supplier_payment",
    "credit_debit_note": "credit_debit_note",
    "warranty_card": "warranty_card",
    "service_order": "service_order",
}


@pytest.fixture
def samples(request):
    """`{doc_type: instance}` — تُبنى كسولاً من `SAMPLE_FIXTURES`."""
    return {
        doc_type: request.getfixturevalue(name)
        for doc_type, name in SAMPLE_FIXTURES.items()
    }


@pytest.fixture
def quotation(env):
    quote = SalesQuotation.objects.create(
        tenant=env["tenant"], quotation_number="SH-QT-1", customer=env["customer"],
        currency=env["currency"], quotation_date="2026-08-01",
        valid_until="2099-12-31", exchange_rate=Decimal("1"),
        subtotal=Decimal("100"), tax_amount=Decimal("16"), grand_total=Decimal("116"),
    )
    SalesQuotationLine.objects.create(
        tenant=env["tenant"], quotation=quote, product=env["product"],
        quantity=Decimal("2"), unit_price=Decimal("50"), line_total=Decimal("116"),
    )
    return quote


# ── جانب الشراء ─────────────────────────────────────────────────────────────
#
# القيم المزروعة هنا **أسرارنا نحن لا أسرار المورّد**: نسبة الرسوم ورابط
# المصدر والمتبقّي وخطة الأقساط ومعدّل توزيع التكلفة المستوردة. المورّد يعرف
# سعره الذي كتبه لنا، ولا يعرف — ولا يجوز أن يعرف — أياً من هذه.
SECRET_FEES_PERCENT = Decimal("33.33")
SECRET_SOURCE_LINK = "https://alibaba.example/سرّ-المصدر-لا-يخرج"
SECRET_REMAINING = Decimal("7777.77")
SECRET_LANDED_RATE = Decimal("0.919191")


@pytest.fixture
def supplier(env):
    from accounting.models import Account

    payable = Account.objects.create(
        tenant=env["tenant"], code="2101-SH", name="ذمم دائنة",
        account_type="Liability", is_active=True,
    )
    return Partner.objects.create(
        tenant=env["tenant"], name="مصنع المشاركة", partner_type="Supplier",
        linked_account=payable, phone="0599111111",
        street_address="شارع المصانع", city="قوانغتشو",
    )


@pytest.fixture
def deal(env, supplier):
    from logistics.models import LogisticsDeal, LogisticsDealItem

    row = LogisticsDeal.objects.create(
        tenant=env["tenant"], ref_number="SH-DEAL-1", partner=supplier,
        order_date="2026-08-01", currency=env["currency"],
        subtotal=Decimal("1000"), tax_amount=Decimal("160"),
        total_amount=Decimal("1160"), notes="ملاحظات الصفقة",
        pi_number="PI-9", incoterms="FOB", shipping_method="Sea",
        factory_name="مصنع قوانغتشو",
        # أسرارٌ لا تخرج — يبحث عنها اختبار التسريب حرفياً في الصفحة.
        fees_percentage=SECRET_FEES_PERCENT,
        alibaba_link=SECRET_SOURCE_LINK,
        remaining_amount=SECRET_REMAINING,
        shipping_cost_estimate=Decimal("444.44"),
    )
    LogisticsDealItem.objects.create(
        deal=row, product=env["product"], quantity=Decimal("10"),
        unit_price=Decimal("100"), catalog_number="CAT-1",
    )
    return row


@pytest.fixture
def purchase_invoice(env, supplier):
    from logistics.models import PurchaseInvoice, PurchaseInvoiceItem

    row = PurchaseInvoice.objects.create(
        tenant=env["tenant"], invoice_number="SH-PINV-1", partner=supplier,
        currency=env["currency"], invoice_date="2026-08-02",
        subtotal=Decimal("1000"), tax_amount=Decimal("160"),
        grand_total=Decimal("1160"), notes="ملاحظات فاتورة الشراء",
        supplier_invoice_number="SUP-77",
        import_deal_remaining_rate=SECRET_LANDED_RATE,
        attached_cash_amount=Decimal("500"),
    )
    PurchaseInvoiceItem.objects.create(
        invoice=row, product=env["product"], name="صنف الشراء",
        quantity=Decimal("10"), unit_price=Decimal("100"),
        total_price=Decimal("1000"), catalog_number="CAT-2",
    )
    return row


@pytest.fixture
def purchase_order(env, supplier):
    from logistics.models import PurchaseOrder, PurchaseOrderLine

    row = PurchaseOrder.objects.create(
        tenant=env["tenant"], order_number="SH-PO-1", supplier=supplier,
        order_date="2026-08-03", currency=env["currency"],
        subtotal=Decimal("1000"), tax_amount=Decimal("160"),
        grand_total=Decimal("1160"), notes="ملاحظات أمر الشراء",
    )
    PurchaseOrderLine.objects.create(
        tenant=env["tenant"], order=row, product=env["product"],
        quantity=Decimal("10"), unit_price=Decimal("100"),
        line_total=Decimal("1000"),
    )
    return row


@pytest.fixture
def supplier_offer(env, supplier):
    from logistics.models import SupplierQuotation, SupplierQuotationLine

    row = SupplierQuotation.objects.create(
        tenant=env["tenant"], quotation_number="SH-SQ-1", supplier=supplier,
        quotation_date="2026-08-04", valid_until="2099-12-31",
        currency=env["currency"], subtotal=Decimal("1000"),
        tax_amount=Decimal("160"), grand_total=Decimal("1160"),
        notes="ملاحظات عرض المورّد", alibaba_link=SECRET_SOURCE_LINK,
    )
    SupplierQuotationLine.objects.create(
        tenant=env["tenant"], quotation=row, product=env["product"],
        quantity=Decimal("10"), unit_price=Decimal("100"),
        line_total=Decimal("1000"),
    )
    return row


@pytest.fixture
def local_purchase_invoice(env, supplier):
    """`SalesInvoice` بنوع شراء — الطرف في `customer` وهو المورّد فعلياً."""
    inv = SalesInvoice.objects.create(
        tenant=env["tenant"], invoice_number="SH-LPI-1", customer=supplier,
        currency=env["currency"], invoice_date="2026-08-05",
        exchange_rate=Decimal("1"), invoice_type=SalesInvoice.INVOICE_CREDIT,
        invoice_kind=SalesInvoice.INVOICE_KIND_PURCHASE,
        subtotal_excl_tax=Decimal("100"), tax_amount=Decimal("16"),
        grand_total=Decimal("116"), notes="فاتورة شراء محلّية",
    )
    SalesInvoiceLine.objects.create(
        tenant=env["tenant"], invoice=inv, product=env["product"],
        quantity=Decimal("2"), unit_price=Decimal("50"),
        line_total_excl_tax=Decimal("100"), line_tax_amount=Decimal("16"),
        internal_note=SECRET_INTERNAL_NOTE, customer_note=CUSTOMER_NOTE,
    )
    return inv


# ── سندات وإشعارات وما بعد البيع ────────────────────────────────────────────

@pytest.fixture
def cash_account(env):
    from accounting.models import Account

    return Account.objects.create(
        tenant=env["tenant"], code="1101-CASH-SH", name="صندوق",
        account_type="Asset", is_active=True,
    )


@pytest.fixture
def sales_order(env):
    from sales.models import SalesOrder, SalesOrderLine

    row = SalesOrder.objects.create(
        tenant=env["tenant"], order_number="SH-SO-1", customer=env["customer"],
        order_date="2026-08-06", currency=env["currency"],
        subtotal=Decimal("100"), tax_amount=Decimal("16"),
        grand_total=Decimal("116"), deposit_amount=Decimal("50"),
        notes="ملاحظات الطلبية",
    )
    SalesOrderLine.objects.create(
        tenant=env["tenant"], order=row, product=env["product"],
        quantity=Decimal("2"), unit_price=Decimal("50"), line_total=Decimal("116"),
    )
    return row


@pytest.fixture
def delivery_order(env, invoice):
    from sales.models import DeliveryOrder, DeliveryOrderLine

    row = DeliveryOrder.objects.create(
        tenant=env["tenant"], delivery_number="SH-DO-1", invoice=invoice,
        partner=env["customer"], delivery_date="2026-08-07",
        customer_ref="REF-9", notes="ملاحظات التسليم",
    )
    DeliveryOrderLine.objects.create(
        tenant=env["tenant"], delivery=row, product=env["product"],
        quantity=Decimal("2"),
    )
    return row


@pytest.fixture
def customer_payment(env, cash_account, invoice):
    from sales.models import CustomerPayment, PaymentAllocation

    row = CustomerPayment.objects.create(
        tenant=env["tenant"], partner=env["customer"], payment_date="2026-08-08",
        amount=Decimal("116"), currency=env["currency"],
        cash_or_bank_account=cash_account, is_posted=True, notes="دفعة نقدية",
    )
    PaymentAllocation.objects.create(
        tenant=env["tenant"], payment=row, invoice=invoice, amount=Decimal("100"),
    )
    return row


@pytest.fixture
def supplier_payment(env, cash_account, supplier, purchase_invoice):
    from sales.models import SupplierPayment, SupplierPaymentAllocation

    row = SupplierPayment.objects.create(
        tenant=env["tenant"], partner=supplier, payment_date="2026-08-09",
        amount=Decimal("1160"), currency=env["currency"],
        cash_or_bank_account=cash_account, is_posted=True, notes="دفعة للمورّد",
    )
    SupplierPaymentAllocation.objects.create(
        tenant=env["tenant"], payment=row, invoice=purchase_invoice,
        amount=Decimal("1000"),
    )
    return row


@pytest.fixture
def credit_debit_note(env, invoice):
    from sales.models import CreditDebitNote

    return CreditDebitNote.objects.create(
        tenant=env["tenant"], note_number="SH-CN-1", note_date="2026-08-10",
        note_type=CreditDebitNote.TYPE_CREDIT, customer=env["customer"],
        related_invoice=invoice, amount=Decimal("25"),
        reason="خصم تسوية على الفاتورة",
    )


@pytest.fixture
def aftersales_tenant(env):
    """`after_sales` وحدة مرخّصة — تُفعَّل صراحةً وإلا ردّ السطح «غير مفعّلة»."""
    from core.models import TenantModule
    from core.modules import invalidate_module_cache

    TenantModule.objects.update_or_create(
        tenant=env["tenant"], module_key="after_sales", defaults={"enabled": True},
    )
    invalidate_module_cache(env["tenant"].pk)
    return env["tenant"]


@pytest.fixture
def warranty_card(env, aftersales_tenant):
    from after_sales.models import WarrantyCard

    return WarrantyCard.objects.create(
        tenant=aftersales_tenant, product=env["product"], partner=env["customer"],
        device_name="جهاز المشاركة", serial="SN-SH-1",
        start_date="2026-08-01", duration_months=12, end_date="2099-08-01",
        supplier=None, notes="ملاحظات الكفالة",
    )


@pytest.fixture
def service_order(env, aftersales_tenant):
    from after_sales.models import ServiceOrder

    return ServiceOrder.objects.create(
        tenant=aftersales_tenant, order_number="SH-SVC-1", order_date="2026-08-11",
        partner=env["customer"], product=env["product"], serial="SN-SH-1",
        device_description="جهاز المشاركة", complaint="لا يعمل",
        accessories="شاحن", notes="ملاحظات الصيانة",
    )
