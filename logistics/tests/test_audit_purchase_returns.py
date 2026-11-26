"""اختبارات أمر القراءة فقط `audit_purchase_returns` (تذكرة PRET-M0-AUDIT)."""
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement, Warehouse
from inventory.services import record_stock_movement
from logistics.models import (
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    PurchaseInvoiceItem,
)
from logistics.services import (
    GR_IR_ACCOUNT_CODE,
    create_purchase_return,
    get_or_create_purchase_settings,
    post_purchase_return,
    receive_purchase_invoice,
)
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _setup_tenant(username: str, company_name: str, ils: Currency):
    owner = User.objects.create_user(username=username, password="x")
    tenant = create_company(company_name, owner)
    tenant._cur = ils
    tenant._owner = owner
    create_fiscal_year(tenant, 2026)
    ap = Account.objects.filter(tenant=tenant, code="2101").first()
    inv = Account.objects.filter(tenant=tenant, code="1104").first()
    assert ap is not None and inv is not None
    supplier = Partner.objects.create(
        tenant=tenant, name=f"مورد-{username}", partner_type="Supplier", linked_account=ap,
    )
    product = Product.objects.create(
        tenant=tenant, sku=f"SKU-{username}-1", name_ar=f"صنف-{username}-1",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("50"),
    )
    return tenant, supplier, product, ap, inv


@pytest.fixture
def env():
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    return _setup_tenant("audret1", "شركة تدقيق المرتجعات", ils)


def _run_audit(**kwargs) -> str:
    out = StringIO()
    call_command("audit_purchase_returns", stdout=out, **kwargs)
    return out.getvalue()


def _section_block(output: str, header_prefix: str, next_prefix: str | None = None) -> str:
    start = output.index(header_prefix)
    if next_prefix and next_prefix in output[start:]:
        end = output.index(next_prefix, start)
        return output[start:end]
    return output[start:]


def _posted_local_original(tenant, supplier, product, ap, *, inv_account, qty=10, price=50,
                           received_qty=10, debit_account=None, number="PINV-ORIG-1"):
    debit_acc = debit_account or inv_account
    total = (Decimal(str(qty)) * Decimal(str(price))).quantize(Decimal("0.01"))
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-01", is_posted=True,
        exchange_rate=Decimal("1"), currency=tenant._cur,
        reference_type="PURCHASE_INVOICE", reference_id=None,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=debit_acc, debit=total, credit=Decimal("0"),
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ap, debit=Decimal("0"), credit=total, partner=supplier,
    )
    orig = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        subtotal=total, grand_total=total, is_posted=True, status="completed", journal=jh,
    )
    JournalHeader.objects.filter(pk=jh.pk).update(reference_id=orig.id)
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product, name=product.name_ar,
        quantity=Decimal(str(qty)), received_quantity=Decimal(str(received_qty)),
        unit_price=Decimal(str(price)), total_price=total,
    )
    return orig


def _post_international_via_api(tenant, supplier, product, *, number: str, qty: Decimal,
                                unit_cost_ils: Decimal, receive_on_post: bool = False):
    """إنشاء فاتورة دولية وترحيلها عبر نقطة النهاية الحقيقية لإنتاج قيد 2110 فعلي."""
    if not tenant.import_enabled:
        tenant.import_enabled = True
        tenant.save(update_fields=["import_enabled"])
    ps = get_or_create_purchase_settings(tenant)
    ps.receive_on_post = False
    ps.save(update_fields=["receive_on_post"])

    total = (qty * unit_cost_ils).quantize(Decimal("0.01"))
    n = LogisticsDeal.objects.count() + 1
    deal = LogisticsDeal.objects.create(
        tenant=tenant, ref_number=f"AUD-D-{n}", partner=supplier,
        order_date="2026-06-01", total_amount=Decimal("1000.00"),
    )
    LogisticsDealItem.objects.create(
        deal=deal, product=product, quantity=qty, unit_price=Decimal("100"),
    )
    shipment = LogisticsShipment.objects.create(
        tenant=tenant, shipment_number=f"AUD-S-{n}", status="Clearing",
    )
    LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)

    orig = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, exchange_rate=Decimal("1"),
        invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
        subtotal=total, grand_total=total, deal=deal, shipment=shipment,
    )
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product, name=product.name_ar,
        quantity=qty, received_quantity=Decimal("0"),
        unit_price=unit_cost_ils, total_price=total,
        landed_unit_price_ils=unit_cost_ils, landed_line_total_ils=total,
    )

    client = APIClient()
    client.force_authenticate(user=tenant._owner)
    res = client.post(
        f"/api/logistics/purchase-invoices/{orig.pk}/post-to-accounting/",
        {"receive_on_post": receive_on_post},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert res.status_code == 201, res.content
    orig.refresh_from_db()
    return orig


def _fx_doubled_return(tenant, supplier, product, ap, inv, usd, *, number, original=None,
                       invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL):
    """مرتجع بعملة أجنبية متضاعف قبل B1: 100$ بسعر 3.7 => debit=370.00, base_debit=1369.00."""
    rate = Decimal("3.700000")
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-16", is_posted=True,
        currency=usd, exchange_rate=rate,
        reference_type="PURCHASE_RETURN", reference_id=None,
    )
    ret = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, invoice_date="2026-06-16",
        partner=supplier, currency=usd, exchange_rate=rate,
        invoice_type=invoice_type, is_return=True, original_invoice=original,
        subtotal=Decimal("370.00"), tax_amount=Decimal("0.00"), grand_total=Decimal("370.00"),
        is_posted=True, status="completed", journal=jh,
    )
    JournalHeader.objects.filter(pk=jh.pk).update(reference_id=ret.id)
    PurchaseInvoiceItem.objects.create(
        invoice=ret, product=product, name=product.name_ar,
        quantity=Decimal("1"), unit_price=Decimal("100"), total_price=Decimal("100.00"),
        is_taxable=False, vat_percent=Decimal("0"),
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ap,
        debit=Decimal("370.00"), credit=Decimal("0.00"), partner=supplier,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=inv,
        debit=Decimal("0.00"), credit=Decimal("370.00"), partner=None,
    )
    return ret


def test_audit_purchase_returns_s1_counts(env):
    tenant, supplier, product, ap, inv = env
    orig = _posted_local_original(tenant, supplier, product, ap, inv_account=inv, qty=10, price=50)

    ret_posted = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S1-POSTED",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret_posted, user=None)

    create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-16",
        invoice_number="PRET-S1-DRAFT",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 50}],
    )

    out = _run_audit(tenant=tenant.TenantID)
    s1 = _section_block(out, "S1:", "S2:")
    assert "مرحّل=1 " in s1
    assert "مسودّة=1 " in s1
    assert "بأصل=1 " in s1
    assert "حرّ=1\n" in s1


def test_audit_purchase_returns_s2_inventory_credit_vs_movement_cost(env):
    tenant, supplier, product, ap, inv = env

    ret_clean = create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S2-CLEAN",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret_clean, user=None)

    ret_drift = create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-16",
        invoice_number="PRET-S2-DRIFT",
        lines=[{"product": product.id, "quantity": 3, "unit_price": 60}],
    )
    post_purchase_return(ret_drift, user=None)
    # القيد دائن 1104 بـ 180.00؛ نعدّل كلفة الحركة في بيانات الاختبار لتصبح 150.00 -> فرق +30.00
    StockMovement.objects.filter(
        tenant=tenant, reference_type="PURCHASE_RETURN", reference_id=ret_drift.id,
        movement_type="RETURN_OUT",
    ).update(total_cost=Decimal("150.00"))

    out = _run_audit(tenant=tenant.TenantID)
    s2 = _section_block(out, "S2:", "S3:")
    assert "عدد المتأثرين=1 " in s2
    assert "مستثنى_S5=0 " in s2
    assert "موقّع=30.00 " in s2
    assert "مطلق=30.00\n" in s2
    assert "PRET-S2-DRIFT" in s2
    assert "دائن_1104=180.00 " in s2
    assert "كلفة_الحركة=150.00 " in s2
    assert "فرق=30.00\n" in s2
    assert "PRET-S2-CLEAN" not in s2


def test_audit_purchase_returns_s2_excludes_s5_fx_doubled(env):
    tenant, supplier, product, ap, inv = env
    usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$", IsBaseCurrency=False)
    rate = Decimal("3.700000")

    # مرتجع محلي بعملة أجنبية متضاعف قبل B1: القيد يحمل base_credit=1369.00 بدل 370.00
    # وحركة RETURN_OUT بكلفة 100.00 — يجب أن يُستثنى من S2 ولا يُسجَّل خطراً مكرراً.
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-16", is_posted=True,
        currency=usd, exchange_rate=rate,
        reference_type="PURCHASE_RETURN", reference_id=None,
    )
    ret_dbl = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PRET-FX-EXCL", invoice_date="2026-06-16",
        partner=supplier, currency=usd, exchange_rate=rate,
        invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL, is_return=True,
        subtotal=Decimal("370.00"), tax_amount=Decimal("0.00"), grand_total=Decimal("370.00"),
        is_posted=True, status="completed", journal=jh,
    )
    JournalHeader.objects.filter(pk=jh.pk).update(reference_id=ret_dbl.id)
    PurchaseInvoiceItem.objects.create(
        invoice=ret_dbl, product=product, name=product.name_ar,
        quantity=Decimal("1"), unit_price=Decimal("100"), total_price=Decimal("100.00"),
        is_taxable=False, vat_percent=Decimal("0"),
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ap,
        debit=Decimal("370.00"), credit=Decimal("0.00"), partner=supplier,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=inv,
        debit=Decimal("0.00"), credit=Decimal("370.00"), partner=None,
    )
    StockMovement.objects.create(
        tenant=tenant, product=product, movement_type="RETURN_OUT",
        quantity=Decimal("1"), unit_cost=Decimal("100.00"), total_cost=Decimal("100.00"),
        reference_type="PURCHASE_RETURN", reference_id=ret_dbl.id,
        movement_date="2026-06-16",
    )

    out = _run_audit(tenant=tenant.TenantID)
    s2 = _section_block(out, "S2:", "S3:")
    assert "مستثنى_S5=1 " in s2
    assert "عدد المتأثرين=0 " in s2
    assert "PRET-FX-EXCL" not in s2


def test_audit_purchase_returns_s3_unreceived_international_confirmed(env):
    tenant, supplier, product, _ap, _inv = env
    orig = _post_international_via_api(
        tenant, supplier, product, number="PI-INT-UNRECV",
        qty=Decimal("10"), unit_cost_ils=Decimal("100"), receive_on_post=False,
    )

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-INT-UNRECV",
        lines=[{"product": product.id, "quantity": 3, "unit_price": 100}],
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s3 = _section_block(out, "S3:", "S4:")
    assert "دولية مرحّلة=1 " in s3
    assert "فواتير_متأثرة=1 " in s3
    assert "سعر≠1=0 " in s3
    assert "مؤكّد=300.00 " in s3
    assert "حدّ_أعلى=0.00\n" in s3
    assert "PI-INT-UNRECV" in s3
    assert "مرتجعات=1 " in s3
    assert "حصة_2110=300.00 " in s3
    assert "مفتوح_2110=1000.00 " in s3
    assert "منزاح=300.00 " in s3
    assert "[مؤكّد]" in s3


def test_audit_purchase_returns_s3_fully_received_via_grn_not_listed(env):
    tenant, supplier, product, _ap, _inv = env
    wh = Warehouse.objects.get(tenant=tenant, is_default=True)
    orig = _post_international_via_api(
        tenant, supplier, product, number="PI-INT-FULLGRN",
        qty=Decimal("10"), unit_cost_ils=Decimal("100"), receive_on_post=False,
    )
    item = orig.items.get()
    receive_purchase_invoice(
        orig,
        lines=[{"item_id": item.id, "quantity": Decimal("10"), "warehouse_id": wh.id}],
        user=tenant._owner,
    )

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-INT-FULLGRN",
        lines=[{"product": product.id, "quantity": 3, "unit_price": 100}],
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s3 = _section_block(out, "S3:", "S4:")
    assert "دولية مرحّلة=1 " in s3
    assert "فواتير_متأثرة=0 " in s3
    assert "مؤكّد=0.00 " in s3
    assert "حدّ_أعلى=0.00\n" in s3
    assert "PI-INT-FULLGRN" not in s3


def test_audit_purchase_returns_s3_partially_received_upper_bound(env):
    tenant, supplier, product, _ap, _inv = env
    wh = Warehouse.objects.get(tenant=tenant, is_default=True)
    orig = _post_international_via_api(
        tenant, supplier, product, number="PI-INT-PARTIAL",
        qty=Decimal("10"), unit_cost_ils=Decimal("100"), receive_on_post=False,
    )
    item = orig.items.get()
    # استلام 4 وحدات عبر PURCHASE_GRN (مفتوح 2110 = 600.00)، ثم إرجاع 7 (S = 700.00) -> min(700, 600) = 600.00
    receive_purchase_invoice(
        orig,
        lines=[{"item_id": item.id, "quantity": Decimal("4"), "warehouse_id": wh.id}],
        user=tenant._owner,
    )

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-INT-PARTIAL",
        lines=[{"product": product.id, "quantity": 7, "unit_price": 100}],
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s3 = _section_block(out, "S3:", "S4:")
    assert "دولية مرحّلة=1 " in s3
    assert "فواتير_متأثرة=1 " in s3
    assert "مؤكّد=0.00 " in s3
    assert "حدّ_أعلى=600.00\n" in s3
    assert "PI-INT-PARTIAL" in s3
    assert "مرتجعات=1 " in s3
    assert "حصة_2110=700.00 " in s3
    assert "مفتوح_2110=600.00 " in s3
    assert "منزاح=600.00 " in s3
    assert "[حدّ_أعلى]" in s3


def test_audit_purchase_returns_s4_old_originals_no_2110_unreceived(env):
    tenant, supplier, product, ap, inv = env
    gr_ir = Account.objects.create(
        tenant=tenant, code=GR_IR_ACCOUNT_CODE, name="وسيط", account_type="Liability",
    )

    orig_no_2110 = _posted_local_original(
        tenant, supplier, product, ap, inv_account=inv,
        qty=10, price=50, received_qty=4, debit_account=inv, number="PINV-NO-2110",
    )
    ret1 = create_purchase_return(
        tenant, original_invoice=orig_no_2110, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S4-1",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret1, user=None)

    orig_with_2110 = _posted_local_original(
        tenant, supplier, product, ap, inv_account=inv,
        qty=10, price=50, received_qty=4, debit_account=gr_ir, number="PINV-WITH-2110",
    )
    ret2 = create_purchase_return(
        tenant, original_invoice=orig_with_2110, partner=supplier, return_date="2026-06-16",
        invoice_number="PRET-S4-2",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret2, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s4 = _section_block(out, "S4:", "S5:")
    assert "العدد=1 " in s4
    assert "منها_مغطّى_بالحركات=0\n" in s4
    assert "PINV-NO-2110" in s4
    assert "غير_مستلم=6.0000 " in s4
    assert "مرتجع=2.0000 " in s4
    assert "استلام_بالحركات=0.0000\n" in s4
    assert "PINV-WITH-2110" not in s4


def test_audit_purchase_returns_s4_stale_movements_and_per_line_clip(env):
    tenant, supplier, product, ap, inv = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-S4-P2", name_ar="صنف-ثاني",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("50"),
    )

    # 1) فاتورة قديمة حقل received_quantity فيها صفر (بلا تعبئة خلفية)، لكن حركة المخزون
    # IN (PURCHASE_INVOICE) أثبتت استلام كامل الكمية (10) -> مغطّاة بالحركات.
    orig_stale = _posted_local_original(
        tenant, supplier, product, ap, inv_account=inv,
        qty=10, price=50, received_qty=0, debit_account=inv, number="PINV-S4-STALE",
    )
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"), unit_cost=Decimal("50"),
        reference_type="PURCHASE_INVOICE", reference_id=orig_stale.id,
        partner=supplier, movement_date="2026-06-01", tenant=tenant,
    )
    ret_stale = create_purchase_return(
        tenant, original_invoice=orig_stale, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S4-STALE",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret_stale, user=None)

    # 2) سطر مستلم بزيادة (5 مطلوب، 8 مستلم) وسطر غير مستلم (5 مطلوب، 2 مستلم):
    # قصّ كل سطر عند الصفر يُظهر غير_مستلم=3.00 لا 0.00.
    orig_clip = _posted_local_original(
        tenant, supplier, product, ap, inv_account=inv,
        qty=5, price=50, received_qty=8, debit_account=inv, number="PINV-S4-CLIP",
    )
    PurchaseInvoiceItem.objects.create(
        invoice=orig_clip, product=product2, name=product2.name_ar,
        quantity=Decimal("5"), received_quantity=Decimal("2"),
        unit_price=Decimal("50"), total_price=Decimal("250"),
    )
    ret_clip = create_purchase_return(
        tenant, original_invoice=orig_clip, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S4-CLIP",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 50}],
    )
    post_purchase_return(ret_clip, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s4 = _section_block(out, "S4:", "S5:")
    assert "العدد=2 " in s4
    assert "منها_مغطّى_بالحركات=1\n" in s4
    assert "PINV-S4-STALE · غير_مستلم=10.0000 · مرتجع=2.0000 · استلام_بالحركات=10.0000" in s4
    assert "PINV-S4-CLIP · غير_مستلم=3.0000 · مرتجع=1.0000 · استلام_بالحركات=0.0000" in s4


def test_audit_purchase_returns_s5_fx_doubled_local_returns(env):
    tenant, supplier, product, ap, inv = env
    usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$", IsBaseCurrency=False)
    rate = Decimal("3.700000")

    # 1) مرتجع سليم بعد B1: 100$ بسعر 3.7 => debit=100.00, base_debit=370.00
    ret_ok = create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-FX-OK", currency=usd, exchange_rate=rate,
        lines=[{"product": product.id, "quantity": 1, "unit_price": 100}],
    )
    post_purchase_return(ret_ok, user=None)

    # 2) مرتجع متضاعف قبل B1: 100$ بسعر 3.7 => debit=370.00, base_debit=1369.00 (فائض 999.00)
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-16", is_posted=True,
        currency=usd, exchange_rate=rate,
        reference_type="PURCHASE_RETURN", reference_id=None,
    )
    ret_dbl = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PRET-FX-DBL", invoice_date="2026-06-16",
        partner=supplier, currency=usd, exchange_rate=rate,
        invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL, is_return=True,
        subtotal=Decimal("370.00"), tax_amount=Decimal("0.00"), grand_total=Decimal("370.00"),
        is_posted=True, status="completed", journal=jh,
    )
    JournalHeader.objects.filter(pk=jh.pk).update(reference_id=ret_dbl.id)
    PurchaseInvoiceItem.objects.create(
        invoice=ret_dbl, product=product, name=product.name_ar,
        quantity=Decimal("1"), unit_price=Decimal("100"), total_price=Decimal("100.00"),
        is_taxable=False, vat_percent=Decimal("0"),
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ap,
        debit=Decimal("370.00"), credit=Decimal("0.00"), partner=supplier,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=inv,
        debit=Decimal("0.00"), credit=Decimal("370.00"), partner=None,
    )

    out = _run_audit(tenant=tenant.TenantID)
    s5 = _section_block(out, "S5:", "S6:")
    assert "العدد=1 " in s5
    assert "فائض_الأساس=999.00\n" in s5
    assert "PRET-FX-DBL" in s5
    assert "فعلي=1369.00 " in s5
    assert "صحيح=370.00 " in s5
    assert "فائض=999.00\n" in s5
    assert "PRET-FX-OK" not in s5


def test_audit_purchase_returns_s6_backfill_exceptions_and_deterministic(env):
    tenant, supplier, product1, _ap, _inv = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-P2", name_ar="صنف-سعرين",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("20"),
    )
    product3 = Product.objects.create(
        tenant=tenant, sku="SKU-P3", name_ar="صنف-غير-مستلم",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("30"),
    )
    product4 = Product.objects.create(
        tenant=tenant, sku="SKU-P4", name_ar="صنف-سعر-واحد-متعدد",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("15"),
    )
    product5 = Product.objects.create(
        tenant=tenant, sku="SKU-P5", name_ar="صنف-غائب-عن-الاصل",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("25"),
    )

    orig = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PINV-S6", invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        subtotal=Decimal("500"), grand_total=Decimal("500"), is_posted=True, status="completed",
    )
    # حتمي: بند واحد، مستلم 5، مرتجع 3
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product1, name=product1.name_ar,
        quantity=Decimal("5"), received_quantity=Decimal("5"),
        unit_price=Decimal("10"), total_price=Decimal("50"),
    )
    # استثناء (أ): سطران بسعرين مختلفين 10 و 12، مستلم كفاية (3+3=6 >= 2)
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product2, name=product2.name_ar,
        quantity=Decimal("3"), received_quantity=Decimal("3"),
        unit_price=Decimal("10"), total_price=Decimal("30"),
    )
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product2, name=product2.name_ar,
        quantity=Decimal("3"), received_quantity=Decimal("3"),
        unit_price=Decimal("12"), total_price=Decimal("36"),
    )
    # استثناء (ب): مرتجع 3 > مستلم 1
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product3, name=product3.name_ar,
        quantity=Decimal("5"), received_quantity=Decimal("1"),
        unit_price=Decimal("30"), total_price=Decimal("150"),
    )
    # استثناء (ج): نفس الصنف على سطرين بالسعر نفسه 15، مستلم 2+2=4 >= 2
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product4, name=product4.name_ar,
        quantity=Decimal("2"), received_quantity=Decimal("2"),
        unit_price=Decimal("15"), total_price=Decimal("30"),
    )
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product4, name=product4.name_ar,
        quantity=Decimal("2"), received_quantity=Decimal("2"),
        unit_price=Decimal("15"), total_price=Decimal("30"),
    )

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S6",
        lines=[
            {"product": product1.id, "quantity": 3, "unit_price": 10},
            {"product": product2.id, "quantity": 2, "unit_price": 10},
            {"product": product3.id, "quantity": 3, "unit_price": 30},
            {"product": product4.id, "quantity": 2, "unit_price": 15},
        ],
    )
    # صنف غائب عن الأصل (مرتجع قديم قبل حراس W6)
    PurchaseInvoiceItem.objects.create(
        invoice=ret, product=product5, name=product5.name_ar,
        quantity=Decimal("1"), unit_price=Decimal("25"), total_price=Decimal("25"),
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s6 = _section_block(out, "S6:", "S7:")
    assert "حتمي=1 " in s6
    assert "تعدد_أسعار=1 " in s6
    assert "أسطر_متعددة_بسعر_واحد=1 " in s6
    assert "تجاوز_مستلم=1 " in s6
    assert "غير_موجود_بالأصل=1\n" in s6
    assert "PINV-S6" in s6
    assert product1.name_ar not in s6
    assert "صنف-سعرين" in s6
    assert "صنف-غير-مستلم" in s6
    assert "[أسطر_متعددة_بسعر_واحد]" in s6
    assert "[غير_موجود_بالأصل]" in s6
    assert (
        f"    PINV-S6 · «صنف-غائب-عن-الاصل» (#{product5.id}) · [غير_موجود_بالأصل] · "
        "مرتجع=1.0000 · مستلم=0.0000\n"
    ) in s6


def test_audit_purchase_returns_s7_sales_invoice_old_path(env):
    tenant, supplier, _product, _ap, _inv = env
    SalesInvoice.objects.create(
        tenant=tenant, invoice_number="SPR-POSTED", customer=supplier,
        invoice_date="2026-06-01", currency=tenant._cur,
        invoice_kind=SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
        status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("100"),
    )
    SalesInvoice.objects.create(
        tenant=tenant, invoice_number="SPR-DRAFT", customer=supplier,
        invoice_date="2026-06-02", currency=tenant._cur,
        invoice_kind=SalesInvoice.INVOICE_KIND_PURCHASE_RETURN,
        status=SalesInvoice.STATUS_DRAFT, grand_total=Decimal("50"),
    )
    # فاتورة بيع عادية لا تُعدّ
    SalesInvoice.objects.create(
        tenant=tenant, invoice_number="SINV-NORMAL", customer=supplier,
        invoice_date="2026-06-03", currency=tenant._cur,
        invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("200"),
    )

    out = _run_audit(tenant=tenant.TenantID)
    s7 = _section_block(out, "S7:", "S8:")
    assert "مرحّل=1 " in s7
    assert "مسودّة=1 " in s7


def test_audit_purchase_returns_no_writes_and_s8_totals(env):
    tenant, supplier, product, ap, inv = env
    usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$", IsBaseCurrency=False)

    # سجل S2 فرق 25.00 + سجل S3 دولية 2110 بمبلغ 200.00 (مؤكّد، على منتج كلفته 100 كي لا يصنع فرق S2)
    ret_s2 = create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S8-S2",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 100}],
    )
    post_purchase_return(ret_s2, user=None)
    StockMovement.objects.filter(
        tenant=tenant, reference_type="PURCHASE_RETURN", reference_id=ret_s2.id,
    ).update(total_cost=Decimal("75.00"))

    product_s3 = Product.objects.create(
        tenant=tenant, sku="SKU-S8-INT", name_ar="صنف-دولي-S8",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("100"),
    )
    orig = _post_international_via_api(
        tenant, supplier, product_s3, number="PI-S8-INT",
        qty=Decimal("4"), unit_cost_ils=Decimal("100"), receive_on_post=False,
    )
    ret_s3 = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-16",
        invoice_number="PRET-S8-S3",
        lines=[{"product": product_s3.id, "quantity": 2, "unit_price": 100}],
    )
    post_purchase_return(ret_s3, user=None)

    # مرتجع S5 متضاعف (فائض أساس 999.00): يُستثنى من Σ S2 فيجب أن يظهر في سطر S8 مستقل.
    _fx_doubled_return(tenant, supplier, product, ap, inv, usd, number="PRET-S8-S5")

    models_to_check = (
        PurchaseInvoice, PurchaseInvoiceItem, StockMovement,
        JournalHeader, JournalLine, SalesInvoice, Account,
    )
    before_counts = {m.__name__: m.objects.count() for m in models_to_check}

    with CaptureQueriesContext(connection) as ctx:
        out = _run_audit(tenant=tenant.TenantID)

    write_prefixes = ("INSERT", "UPDATE", "DELETE", "REPLACE")
    write_queries = [
        q["sql"] for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith(write_prefixes)
    ]
    assert write_queries == []

    after_counts = {m.__name__: m.objects.count() for m in models_to_check}
    assert after_counts == before_counts

    s8 = _section_block(out, "S8:", "ملخّص شركة")
    assert "انجراف 1104 (Σ S2، بلا مرتجعات S5) موقّع=25.00 " in s8
    assert "مطلق=25.00\n" in s8
    assert "مؤكّد=200.00 " in s8
    assert "حدّ_أعلى=0.00 · سعر≠1=0\n" in s8
    assert "فائض_أساس S5=999.00\n" in s8
    summary = _section_block(out, "ملخّص شركة", "الإجمالي العام")
    assert "فائض_أساس S5=999.00)" in summary
    grand = out.split("الإجمالي العام")[-1]
    assert "فائض_أساس S5=999.00)" in grand
    assert "مجموع_موقّع" not in out
    assert "مجموع_مطلق" not in out


def test_audit_purchase_returns_tenant_isolation(env):
    tenant_a, supplier_a, product_a, ap_a, inv_a = env
    tenant_b, supplier_b, product_b, ap_b, inv_b = _setup_tenant(
        "audret2", "شركة ثانية معزولة", tenant_a._cur,
    )

    ret_a = create_purchase_return(
        tenant_a, original_invoice=None, partner=supplier_a, return_date="2026-06-15",
        invoice_number="PRET-TENANT-A",
        lines=[{"product": product_a.id, "quantity": 1, "unit_price": 40}],
    )
    post_purchase_return(ret_a, user=None)
    StockMovement.objects.filter(
        tenant=tenant_a, reference_type="PURCHASE_RETURN", reference_id=ret_a.id,
    ).update(total_cost=Decimal("30.00"))

    orig_b = _posted_local_original(
        tenant_b, supplier_b, product_b, ap_b, inv_account=inv_b,
        qty=5, price=90, received_qty=5, number="PINV-TENANT-B-SECRET",
    )
    # أصل ب يحمل أيضاً سطر المنتج «أ» بكمية غير مستلمة: لو تسرّب إلى S4 أو S6 لظهر عدّاً واسماً.
    PurchaseInvoiceItem.objects.create(
        invoice=orig_b, product=product_a, name=product_a.name_ar,
        quantity=Decimal("5"), received_quantity=Decimal("0"),
        unit_price=Decimal("40"), total_price=Decimal("200"),
    )
    ret_b = create_purchase_return(
        tenant_b, original_invoice=None, partner=supplier_b, return_date="2026-06-15",
        invoice_number="PRET-TENANT-B",
        lines=[{"product": product_b.id, "quantity": 1, "unit_price": 90}],
    )
    post_purchase_return(ret_b, user=None)
    StockMovement.objects.filter(
        tenant=tenant_b, reference_type="PURCHASE_RETURN", reference_id=ret_b.id,
    ).update(total_cost=Decimal("70.00"))

    # مرتجع في شركة أ مربوط خطأً بأصل في شركة ب لا يجوز أن يطبع بيانات شركة ب في S6
    ret_cross = create_purchase_return(
        tenant_a, original_invoice=None, partner=supplier_a, return_date="2026-06-16",
        invoice_number="PRET-CROSS-A",
        lines=[{"product": product_a.id, "quantity": 1, "unit_price": 50}],
    )
    post_purchase_return(ret_cross, user=None)
    PurchaseInvoice.objects.filter(pk=ret_cross.pk).update(original_invoice=orig_b)

    only_a = _run_audit(tenant=tenant_a.TenantID)
    assert tenant_a.CompanyName in only_a
    assert tenant_b.CompanyName not in only_a
    assert "PRET-TENANT-A" in only_a
    assert "PRET-TENANT-B" not in only_a
    assert "PINV-TENANT-B-SECRET" not in only_a

    both = _run_audit()
    assert tenant_a.CompanyName in both
    assert tenant_b.CompanyName in both
    block_a = _section_block(both, f"شركة {tenant_a.TenantID} —", f"شركة {tenant_b.TenantID} —")
    assert "PRET-TENANT-A" in block_a
    assert "PRET-TENANT-B" not in block_a
    assert "PINV-TENANT-B-SECRET" not in block_a
    assert "S1: مرحّل=2 " in block_a
    # المرتجع العابر للشركات لا يدخل S4 ولا S6 في شركة أ ولا يُحسب استثناءً.
    assert "S4: العدد=0 " in block_a
    assert (
        "S6: حتمي=0 · تعدد_أسعار=0 · أسطر_متعددة_بسعر_واحد=0 · "
        "تجاوز_مستلم=0 · منها_ب_أصل_مغطّى_بالحركات=0 · غير_موجود_بالأصل=0\n"
    ) in block_a
    assert "PRET-TENANT-B" in both
    assert "موقّع=30.00, مطلق=30.00" in both.split("الإجمالي العام")[-1]


def test_audit_purchase_returns_skips_silent_tenant(env):
    tenant_a, supplier_a, product_a, _ap_a, _inv_a = env
    _setup_tenant("audsilent", "شركة صامتة بلا مرتجعات", tenant_a._cur)

    ret_a = create_purchase_return(
        tenant_a, original_invoice=None, partner=supplier_a, return_date="2026-06-15",
        invoice_number="PRET-ACTIVE-A",
        lines=[{"product": product_a.id, "quantity": 1, "unit_price": 40}],
    )
    post_purchase_return(ret_a, user=None)

    out = _run_audit()
    assert tenant_a.CompanyName in out
    assert "شركة صامتة بلا مرتجعات" not in out
    assert "شركات بلا مرتجعات: 1" in out
    assert "الإجمالي العام (1 شركة)" in out


def test_audit_purchase_returns_s4_sub_cent_unreceived_and_movement_precision(env):
    tenant, supplier, product, ap, inv = env

    # 10 مطلوب و9.995 مستلم: الباقي 0.0050 بدقة الكمية (4 منازل) — تقريبه لمنزلتين يُسقطه.
    orig = _posted_local_original(
        tenant, supplier, product, ap, inv_account=inv,
        qty=10, price=50, received_qty=Decimal("9.995"), debit_account=inv, number="PINV-S4-SUBCENT",
    )
    # حركة IN بـ9.995 فقط: لا تغطّي 10 (المقارنة بدقة الكمية لا بالتقريب لمنزلتين).
    StockMovement.objects.create(
        tenant=tenant, product=product, movement_type="IN",
        quantity=Decimal("9.995"), unit_cost=Decimal("50.0000"), total_cost=Decimal("499.75"),
        reference_type="PURCHASE_INVOICE", reference_id=orig.id,
        movement_date="2026-06-01",
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S4-SUBCENT",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 50}],
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s4 = _section_block(out, "S4:", "S5:")
    assert "العدد=1 " in s4
    assert "منها_مغطّى_بالحركات=0\n" in s4
    assert "PINV-S4-SUBCENT · غير_مستلم=0.0050 · مرتجع=1.0000 · استلام_بالحركات=9.9950\n" in s4


def test_audit_purchase_returns_s3_counts_only_returns_whose_original_is_international(env):
    tenant, supplier, product, ap, inv = env
    usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$", IsBaseCurrency=False)
    orig = _posted_local_original(
        tenant, supplier, product, ap, inv_account=inv, qty=10, price=50, number="PINV-LOCAL-ORIG",
    )

    # مرتجع موسوم «دولي» وأصله محلي: `post_purchase_return` يوجّهه بحسب الأصل فرُحِّل محلياً.
    ret_marked = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-MARKED-INTL",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret_marked, user=None)
    PurchaseInvoice.objects.filter(pk=ret_marked.pk).update(
        invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
    )
    # وإن كان متضاعفاً بعملة أجنبية فمكانه S5 لا S3.
    _fx_doubled_return(
        tenant, supplier, product, ap, inv, usd, number="PRET-INTL-DBL", original=orig,
        invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
    )

    out = _run_audit(tenant=tenant.TenantID)
    s3 = _section_block(out, "S3:", "S4:")
    assert "دولية مرحّلة=0 " in s3
    assert "فواتير_متأثرة=0 " in s3
    s5 = _section_block(out, "S5:", "S6:")
    assert "العدد=1 " in s5
    assert "فائض_الأساس=999.00\n" in s5
    assert "PRET-INTL-DBL" in s5


def test_audit_purchase_returns_s3_shipment_synced_receipt_is_upper_bound(env):
    tenant, supplier, product, _ap, _inv = env
    orig = _post_international_via_api(
        tenant, supplier, product, number="PI-INT-SYNCED",
        qty=Decimal("10"), unit_cost_ils=Decimal("100"), receive_on_post=False,
    )
    # المسار القديم (Cleared عبر `sync_import_receipt_from_shipment_stock`) لا يمكن إنتاجه بالخدمات
    # الحالية، فنصوغ أثره مباشرةً: `received_quantity` مضبوطة وبلا قيد PURCHASE_GRN و2110 مفتوح.
    orig.items.update(received_quantity=Decimal("10"))

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-INT-SYNCED",
        lines=[{"product": product.id, "quantity": 3, "unit_price": 100}],
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s3 = _section_block(out, "S3:", "S4:")
    assert "فواتير_متأثرة=1 " in s3
    assert "مؤكّد=0.00 " in s3
    assert "حدّ_أعلى=300.00\n" in s3
    assert "PI-INT-SYNCED" in s3
    assert "[حدّ_أعلى]" in s3
    assert "[مؤكّد]" not in s3


def test_audit_purchase_returns_s3_counts_originals_with_exchange_rate_not_one(env):
    tenant, supplier, product, _ap, _inv = env
    orig = _post_international_via_api(
        tenant, supplier, product, number="PI-INT-RATE",
        qty=Decimal("10"), unit_cost_ils=Decimal("100"), receive_on_post=False,
    )
    JournalHeader.objects.filter(pk=orig.journal_id).update(exchange_rate=Decimal("3.700000"))
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-INT-RATE",
        lines=[{"product": product.id, "quantity": 3, "unit_price": 100}],
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s3 = _section_block(out, "S3:", "S4:")
    assert "فواتير_متأثرة=1 " in s3
    assert "سعر≠1=1 " in s3
    # سطر 2110 في S8 وجزء S3 في الإجمالي العام يحملان العدّاد نفسه: مجموعهما يخلط عملتين.
    s8 = _section_block(out, "S8:", "ملخّص شركة")
    assert "انجراف 2110 الدولي (Σ S3) مؤكّد=300.00 · حدّ_أعلى=0.00 · سعر≠1=1\n" in s8
    grand = out.split("الإجمالي العام")[-1]
    assert "S3=1 (مؤكّد=300.00, حدّ_أعلى=0.00, سعر≠1=1)" in grand


def test_audit_purchase_returns_picks_lowest_journal_id_deterministically(env):
    tenant, supplier, product, ap, inv = env
    ret = create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-TWO-JOURNALS",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret, user=None)
    # قيد ثانٍ لنفس المرتجع بمعرّف أعلى ودائن مخزون مختلف؛ نفصل `journal` كي يُحسم الاختيار بالمرجع.
    decoy = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-15", is_posted=True,
        exchange_rate=Decimal("1"), currency=tenant._cur,
        reference_type="PURCHASE_RETURN", reference_id=ret.id,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=decoy, account=ap, debit=Decimal("999.00"), credit=Decimal("0.00"),
        partner=supplier,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=decoy, account=inv, debit=Decimal("0.00"), credit=Decimal("999.00"),
    )
    PurchaseInvoice.objects.filter(pk=ret.pk).update(journal=None)

    out = _run_audit(tenant=tenant.TenantID)
    s2 = _section_block(out, "S2:", "S3:")
    assert "عدد المتأثرين=0 " in s2
    assert "PRET-TWO-JOURNALS" not in s2


def test_audit_purchase_returns_s6_quantities_printed_at_qty_precision(env):
    tenant, supplier, product, _ap, _inv = env
    orig = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PINV-S6-PREC", invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        subtotal=Decimal("250"), grand_total=Decimal("250"), is_posted=True, status="completed",
    )
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product, name=product.name_ar,
        quantity=Decimal("5"), received_quantity=Decimal("2.000"),
        unit_price=Decimal("50"), total_price=Decimal("250"),
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S6-PREC",
        lines=[{"product": product.id, "quantity": Decimal("2.005"), "unit_price": 50}],
    )
    post_purchase_return(ret, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s6 = _section_block(out, "S6:", "S7:")
    assert "تجاوز_مستلم=1 " in s6
    # تجاوز 0.005 يظهر بدقة الكمية: بمنزلتين كان يُطبع «2.01» مقابل «2.00».
    assert "PINV-S6-PREC · «صنف-audret1-1»" in s6
    assert "[ب:تجاوز_مستلم] · مرتجع=2.0050 · مستلم=2.0000\n" in s6


def _post_local_via_api_with_receipt(tenant, supplier, product, *, number: str, qty: Decimal):
    """فاتورة محلية تُرحَّل وتُستلَم عبر نقطة النهاية الحقيقية فتُسجَّل حركة IN (PURCHASE_INVOICE)."""
    total = (qty * Decimal("50")).quantize(Decimal("0.01"))
    orig = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, exchange_rate=Decimal("1"),
        invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        subtotal=total, grand_total=total,
    )
    PurchaseInvoiceItem.objects.create(
        invoice=orig, product=product, name=product.name_ar,
        quantity=qty, received_quantity=Decimal("0"),
        unit_price=Decimal("50"), total_price=total, is_taxable=False, vat_percent=Decimal("0"),
    )
    client = APIClient()
    client.force_authenticate(user=tenant._owner)
    res = client.post(
        f"/api/logistics/purchase-invoices/{orig.pk}/post-to-accounting/",
        {"receive_on_post": True},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert res.status_code == 201, res.content
    orig.refresh_from_db()
    return orig


def test_audit_purchase_returns_s6_counts_b_rows_whose_original_is_covered_by_movements(env):
    tenant, supplier, product, _ap, _inv = env

    # 1) أصل محلي استُلم فعلاً (حركة IN بالكمية كاملة)، ثم يُعاد received_quantity إلى صفر
    # بـ update() لمحاكاة الفواتير القديمة التي لم يُعبَّأ حقلها خلفياً -> ب مغطّى بالحركات.
    orig_cov = _post_local_via_api_with_receipt(
        tenant, supplier, product, number="PINV-S6-COVERED", qty=Decimal("5"),
    )
    assert StockMovement.objects.filter(
        tenant=tenant, movement_type="IN", reference_type="PURCHASE_INVOICE",
        reference_id=orig_cov.id,
    ).exists()
    orig_cov.items.update(received_quantity=Decimal("0"))
    ret_cov = create_purchase_return(
        tenant, original_invoice=orig_cov, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-S6-COVERED",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 50}],
    )
    post_purchase_return(ret_cov, user=None)

    # 2) أصل بلا حركة استلام ومرتجعه يتجاوز المستلم -> ب غير مغطّى، لا يدخل العدّاد.
    orig_bare = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PINV-S6-BARE", invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        subtotal=Decimal("250"), grand_total=Decimal("250"), is_posted=True, status="completed",
    )
    PurchaseInvoiceItem.objects.create(
        invoice=orig_bare, product=product, name=product.name_ar,
        quantity=Decimal("5"), received_quantity=Decimal("0"),
        unit_price=Decimal("50"), total_price=Decimal("250"),
    )
    ret_bare = create_purchase_return(
        tenant, original_invoice=orig_bare, partner=supplier, return_date="2026-06-16",
        invoice_number="PRET-S6-BARE",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 50}],
    )
    post_purchase_return(ret_bare, user=None)

    out = _run_audit(tenant=tenant.TenantID)
    s6 = _section_block(out, "S6:", "S7:")
    assert "تجاوز_مستلم=2 " in s6
    assert "منها_ب_أصل_مغطّى_بالحركات=1 " in s6
    rows = s6.splitlines()
    cov_row = next(line for line in rows if "PINV-S6-COVERED" in line)
    bare_row = next(line for line in rows if "PINV-S6-BARE" in line)
    assert cov_row.endswith("[ب:تجاوز_مستلم] · مرتجع=2.0000 · مستلم=0.0000 · مغطّى_بالحركات")
    assert bare_row.endswith("[ب:تجاوز_مستلم] · مرتجع=1.0000 · مستلم=0.0000")


def test_audit_purchase_returns_closing_line_and_inventory_account_warning(env, monkeypatch):
    tenant, supplier, product, _ap, _inv = env
    create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-16",
        invoice_number="PRET-WARN-DRAFT",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 50}],
    )

    normal = _run_audit(tenant=tenant.TenantID)
    assert normal.rstrip().endswith("تقرير فقط — لم يُكتب شيء في قاعدة البيانات.")
    assert "تحذير" not in normal

    # حالة غياب حساب المخزون تُصاغ بإحلال `_resolve_inventory_account` (شجرة الحسابات تُنشأ كاملة).
    from django.core.exceptions import ValidationError
    from logistics.management.commands import audit_purchase_returns as cmd

    def _missing(_tenant):
        raise ValidationError("لا حساب مخزون")

    monkeypatch.setattr(cmd, "_resolve_inventory_account", _missing)
    warned = _run_audit(tenant=tenant.TenantID)
    block = _section_block(warned, f"شركة {tenant.TenantID} —", "الإجمالي العام")
    assert block.count("تحذير") == 1
    assert "حساب المخزون" in block
    assert warned.rstrip().endswith("تقرير فقط — لم يُكتب شيء في قاعدة البيانات.")
