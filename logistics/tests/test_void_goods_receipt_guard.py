"""إلغاءُ إرساليّة شراءٍ بيعت بضاعتُها يُمنع — كإلغاء ترحيل فاتورة الشراء نفسِها.

`void_goods_receipt` كان يحذف حركاتِ الوارد مباشرةً، و`StockLayer.source_movement`
بـCASCADE: فطبقةُ الإرساليّة تُمحى **ومعها صفوفُ استهلاك مبيعاتٍ لاحقة** من خارجها،
فيضيع سجلُّ كلفة تلك المبيعات بلا إنذار. `reverse_stock_movements` تحرس هذه الحالة
صراحةً منذ #137؛ والحارسُ صار واحداً يمرّ به المساران. وهو القرارُ نفسُه الذي يطبّقه
`release_purchase_serials` على الوحدات المرقَّمة: لا يُمحى أصلُ وحدةٍ بيعت.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, StockLayer, StockLayerConsumption, Warehouse
from inventory.services import record_stock_movement
from logistics.models import GoodsReceipt, PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings, receive_purchase_invoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def received():
    user = User.objects.create_user(username="voidgr", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة الإرساليّات", user)
    create_fiscal_year(tenant, 2026)
    ps = get_or_create_purchase_settings(tenant)
    ps.receive_on_post = False
    ps.save(update_fields=["receive_on_post"])
    warehouse = Warehouse.objects.get(tenant=tenant, is_default=True)
    partner = Partner.objects.create(
        tenant=tenant, name="مورّد", partner_type="Supplier",
        linked_account=Account.objects.get(tenant=tenant, code="2101"))
    product = Product.objects.create(
        tenant=tenant, sku="GR-1", name_ar="إطار الإرساليّة",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    invoice = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="INV-GR-1", partner=partner, currency=ils,
        invoice_date="2026-06-11", exchange_rate=Decimal("1"), grand_total=Decimal("100"))
    item = PurchaseInvoiceItem.objects.create(
        invoice=invoice, product=product, name="إطار", quantity=Decimal("10"),
        unit_price=Decimal("10"), total_price=Decimal("100"))

    client = APIClient()
    client.force_authenticate(user=user)
    headers = {"HTTP_X_TENANT_ID": str(tenant.TenantID)}
    res = client.post(
        f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
        {}, format="json", **headers)
    assert res.status_code == 201, res.content
    receipt = receive_purchase_invoice(
        invoice, lines=[{"item_id": item.id, "quantity": Decimal("10"),
                         "warehouse_id": warehouse.id}], user=user)["receipt"]
    return tenant, client, headers, product, receipt


def test_voiding_a_receipt_whose_goods_were_sold_is_refused_and_touches_nothing(received):
    tenant, client, headers, product, receipt = received
    sale = record_stock_movement(
        product=product, movement_type="OUT", quantity=Decimal("4"),
        movement_date="2026-06-20", tenant=tenant)
    assert StockLayerConsumption.objects.filter(movement=sale).exists()

    res = client.delete(f"/api/logistics/goods-receipts/{receipt.pk}/", **headers)

    assert res.status_code == 400, res.content
    assert "بيعت" in res.json()["error"]
    assert GoodsReceipt.objects.filter(pk=receipt.pk).exists()
    assert StockLayerConsumption.objects.filter(movement=sale).exists(), \
        "مُحي سجلُّ كلفة بيعةٍ لاحقة مع طبقة الإرساليّة."
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("6.0000")


def test_voiding_an_untouched_receipt_still_works(received):
    tenant, client, headers, product, receipt = received

    res = client.delete(f"/api/logistics/goods-receipts/{receipt.pk}/", **headers)

    assert res.status_code == 200, res.content
    assert not GoodsReceipt.objects.filter(pk=receipt.pk).exists()
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("0.0000")
    assert not StockLayer.objects.filter(product=product, remaining_qty__gt=0).exists()
