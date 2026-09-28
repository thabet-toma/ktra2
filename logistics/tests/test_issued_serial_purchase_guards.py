"""وحدةٌ تسلسلية حالتها غير `in_stock` تمنع حذفها في مسارات الشراء الثلاثة (#223).

لا حاجة لتمريرها فعلياً عبر أمر صيانة: الغرض هنا حارسُ `release_purchase_serials`
(ومستهلِكاه: إلغاء ترحيل فاتورة الشراء، وإلغاء سند الاستلام، ومرتجع الشراء) — وهو
يفحص `status` وحده بصرف النظر عمّن كتبها. `ProductSerial.STATUS_ISSUED` (#223،
القطعة المغطاة المرقّمة في أمر الصيانة) تُزرع مباشرةً كي يبقى الاختبار مستقلاً عن
دورة `after_sales` كاملة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, ProductSerial, Warehouse
from inventory.serials import SERIAL_MODE_OPTIONAL
from logistics.models import GoodsReceipt, PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import (
    get_or_create_purchase_settings,
    post_purchase_return,
    receive_purchase_invoice,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _base_setup(username):
    user = User.objects.create_user(username=username, password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة الوحدات المصروفة", user)
    create_fiscal_year(tenant, 2026)
    ps = get_or_create_purchase_settings(tenant)
    ps.serial_entry_mode = SERIAL_MODE_OPTIONAL
    ps.save(update_fields=["serial_entry_mode"])
    partner = Partner.objects.create(
        tenant=tenant, name="مورّد", partner_type="Supplier",
        linked_account=Account.objects.get(tenant=tenant, code="2101"),
    )
    product = Product.objects.create(
        tenant=tenant, sku="ISS-1", name_ar="قطعة مصروفة",
        is_serialized=True, quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
    )
    client = APIClient()
    client.force_authenticate(user=user)
    headers = {"HTTP_X_TENANT_ID": str(tenant.TenantID)}
    return tenant, user, partner, product, client, headers


def _mark_issued(tenant, product, serial):
    unit = ProductSerial.objects.get(tenant=tenant, product=product, serial=serial)
    unit.status = ProductSerial.STATUS_ISSUED
    unit.save(update_fields=["status"])
    return unit


def test_unposting_a_purchase_invoice_with_an_issued_unit_is_refused_and_names_it():
    tenant, user, partner, product, client, headers = _base_setup("purch-unpost-iss")
    invoice = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="INV-ISS-1", partner=partner,
        currency=Currency.objects.get(Code="ILS"), invoice_date="2026-06-01",
        exchange_rate=Decimal("1"), grand_total=Decimal("300"),
    )
    PurchaseInvoiceItem.objects.create(
        invoice=invoice, product=product, name="قطعة", quantity=Decimal("3"),
        unit_price=Decimal("100"), total_price=Decimal("300"),
        serials=["ISU-01", "ISU-02", "ISU-03"],
    )
    res = client.post(
        f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
        {}, format="json", **headers,
    )
    assert res.status_code == 201, res.content
    issued = _mark_issued(tenant, product, "ISU-02")

    res = client.post(
        f"/api/logistics/purchase-invoices/{invoice.pk}/unpost/", {}, format="json", **headers,
    )

    assert res.status_code == 400, res.content
    assert "ISU-02" in res.json()["error"]
    invoice.refresh_from_db()
    assert invoice.is_posted
    assert ProductSerial.objects.filter(
        pk=issued.pk, status=ProductSerial.STATUS_ISSUED,
    ).exists()


def test_voiding_a_goods_receipt_with_an_issued_unit_is_refused_and_names_it():
    tenant, user, partner, product, client, headers = _base_setup("gr-void-iss")
    ps = get_or_create_purchase_settings(tenant)
    ps.receive_on_post = False
    ps.save(update_fields=["receive_on_post"])
    warehouse = Warehouse.objects.get(tenant=tenant, is_default=True)

    invoice = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="INV-ISS-2", partner=partner,
        currency=Currency.objects.get(Code="ILS"), invoice_date="2026-06-01",
        exchange_rate=Decimal("1"), grand_total=Decimal("300"),
    )
    item = PurchaseInvoiceItem.objects.create(
        invoice=invoice, product=product, name="قطعة", quantity=Decimal("3"),
        unit_price=Decimal("100"), total_price=Decimal("300"),
        serials=["ISU-11", "ISU-12", "ISU-13"],
    )
    res = client.post(
        f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
        {}, format="json", **headers,
    )
    assert res.status_code == 201, res.content
    receipt = receive_purchase_invoice(
        invoice,
        lines=[{"item_id": item.id, "quantity": Decimal("3"), "warehouse_id": warehouse.id}],
        user=user,
    )["receipt"]
    issued = _mark_issued(tenant, product, "ISU-12")

    res = client.delete(f"/api/logistics/goods-receipts/{receipt.pk}/", **headers)

    assert res.status_code == 400, res.content
    assert "ISU-12" in res.json()["error"]
    assert GoodsReceipt.objects.filter(pk=receipt.pk).exists()
    assert ProductSerial.objects.filter(
        pk=issued.pk, status=ProductSerial.STATUS_ISSUED,
    ).exists()


def test_posting_a_purchase_return_with_an_issued_unit_is_refused_and_names_it():
    tenant, user, partner, product, client, headers = _base_setup("purch-return-iss")
    invoice = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="INV-ISS-3", partner=partner,
        currency=Currency.objects.get(Code="ILS"), invoice_date="2026-06-01",
        exchange_rate=Decimal("1"), grand_total=Decimal("300"),
    )
    PurchaseInvoiceItem.objects.create(
        invoice=invoice, product=product, name="قطعة", quantity=Decimal("3"),
        unit_price=Decimal("100"), total_price=Decimal("300"),
        serials=["ISU-21", "ISU-22", "ISU-23"],
    )
    res = client.post(
        f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
        {}, format="json", **headers,
    )
    assert res.status_code == 201, res.content
    issued = _mark_issued(tenant, product, "ISU-22")

    return_invoice = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="INV-ISS-3-RET", partner=partner,
        currency=Currency.objects.get(Code="ILS"), invoice_date="2026-06-05",
        exchange_rate=Decimal("1"), grand_total=Decimal("300"),
        is_return=True, original_invoice=invoice,
    )
    PurchaseInvoiceItem.objects.create(
        invoice=return_invoice, product=product, name="قطعة", quantity=Decimal("3"),
        unit_price=Decimal("100"), total_price=Decimal("300"),
    )

    with pytest.raises(ValidationError) as exc_info:
        post_purchase_return(return_invoice, user=user)

    assert "ISU-22" in str(exc_info.value)
    return_invoice.refresh_from_db()
    assert not return_invoice.is_posted
    assert ProductSerial.objects.filter(
        pk=issued.pk, status=ProductSerial.STATUS_ISSUED,
    ).exists()
