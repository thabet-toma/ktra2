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
