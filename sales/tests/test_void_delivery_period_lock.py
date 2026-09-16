"""إلغاءُ إرساليّة بيعٍ داخل فترةٍ مقفلة يُمنع — كإلغاء ترحيل الفاتورة (THA-184).

`void_delivery_note` يحذف قيدَ الإرساليّة وحركاتِ مخزونها مباشرةً، و`unpost_document`
وحده كان يمرّ بحارس الفترة: «قفلٌ يمنع الإضافة ويسمح بالحذف ليس قفلاً».
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, FiscalPeriod, JournalHeader
from accounting.services import create_fiscal_year
from inventory.models import Product
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import DeliveryOrder, SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def test_voiding_a_delivery_note_inside_a_closed_period_is_refused():
    owner = User.objects.create_user(username="dlvlock", password="x")
    cur = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة القفل", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(tenant=tenant, code="1101-DL", name="ذمم", account_type="Asset", is_active=True)
    cogs = Account.objects.create(tenant=tenant, code="5101-DL", name="تكلفة", account_type="Expense", is_active=True)
    inv_acc = Account.objects.create(tenant=tenant, code="1104-DL", name="مخزون", account_type="Asset", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = cogs
    ss.default_inventory_account = inv_acc
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="DL-LOCK", name_ar="منتج", quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"), unit_cost=Decimal("10"),
        reference_type="OPENING", reference_id=0, movement_date="2026-06-01", tenant=tenant)
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="DL-LOCK-1", customer=customer, currency=cur,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False)
    line = SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product, quantity=Decimal("4"), unit_price=Decimal("50"))
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    delivery = c.post(
        "/api/sales/delivery-orders/",
        {"invoice": inv.id, "lines": [{"line_id": line.id, "quantity": 4}]}, format="json")
    assert delivery.status_code in (200, 201), delivery.content
    delivery_id = delivery.json()["id"]
    journal_id = DeliveryOrder.objects.get(pk=delivery_id).journal_id
    FiscalPeriod.objects.filter(tenant=tenant).update(is_closed=True)

    res = c.delete(f"/api/sales/delivery-orders/{delivery_id}/")

    assert res.status_code == 400, res.content
    assert DeliveryOrder.objects.filter(pk=delivery_id).exists()
    assert JournalHeader.objects.filter(pk=journal_id).exists()
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("6.0000")
