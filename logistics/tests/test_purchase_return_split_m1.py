"""اختبارات بنية فصل مرتجعات الشراء وهجرة الإسناد الخلفي (تذكرة PRET-M1-MODELS)."""
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import (
    create_purchase_return,
    get_or_create_purchase_settings,
    post_purchase_return,
)
from partners.models import Partner
from sales.models import CustomerPayment, PartyRefundAllocation, SupplierPayment
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
    cash = Account.objects.filter(tenant=tenant, code="1101").first()
    if cash is None:
        cash = Account.objects.create(
            tenant=tenant, code="1101-M1", name="صندوق", account_type="Asset", is_active=True,
        )
    assert ap is not None and inv is not None
    supplier = Partner.objects.create(
        tenant=tenant, name=f"مورد-{username}", partner_type="Supplier", linked_account=ap,
    )
    product = Product.objects.create(
        tenant=tenant, sku=f"SKU-{username}-1", name_ar=f"صنف-{username}-1",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("50"),
    )
    return tenant, supplier, product, ap, inv, cash


@pytest.fixture
def env():
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    return _setup_tenant("m1ret1", "شركة M1", ils)


def _post_local_invoice_via_api(
    tenant,
    supplier,
    *,
    number: str,
    items_data: list[dict],
    discount_amount: Decimal = Decimal("0.00"),
    tax_amount: Decimal = Decimal("0.00"),
    receive_on_post: bool = True,
):
    """إنشاء فاتورة شراء محلية وترحيلها عبر المسار الحقيقي."""
    subtotal = sum((Decimal(str(d["total_price"])) for d in items_data), Decimal("0.00"))
    grand_total = (subtotal - discount_amount + tax_amount).quantize(Decimal("0.01"))
    inv = PurchaseInvoice.objects.create(
        tenant=tenant,
        invoice_number=number,
        invoice_date="2026-06-01",
        partner=supplier,
        currency=tenant._cur,
        exchange_rate=Decimal("1"),
        invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        subtotal=subtotal,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        grand_total=grand_total,
    )
    for d in items_data:
        PurchaseInvoiceItem.objects.create(
            invoice=inv,
            product=d.get("product"),
            name=d["name"],
            quantity=Decimal(str(d["quantity"])),
            received_quantity=Decimal("0"),
            unit_price=Decimal(str(d["unit_price"])),
            total_price=Decimal(str(d["total_price"])),
            is_taxable=d.get("is_taxable", False),
            vat_percent=Decimal(str(d.get("vat_percent", 0))),
            expense_account=d.get("expense_account"),
        )
    client = APIClient()
    client.force_authenticate(user=tenant._owner)
    res = client.post(
        f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
        {"receive_on_post": receive_on_post},
        format="json",
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert res.status_code == 201, res.content
    inv.refresh_from_db()
    return inv


def _run_backfill(**kwargs) -> str:
    """يشغّل الأمر؛ الافتراضي هنا `apply=True` ما لم يُمرَّر `apply` أو `dry_run` صراحةً
    (الأمر نفسه معاينةٌ افتراضياً — تغطّيها اختبارات الأمر المباشرة بلا هذه الدالّة)."""
    kwargs.setdefault("apply", not kwargs.get("dry_run"))
    out = StringIO()
    call_command("backfill_purchase_returns", stdout=out, **kwargs)
    return out.getvalue()


# ── 1) الحقول الجديدة وقيمها الافتراضية ──────────────────────────────────────

def test_new_fields_and_defaults(env):
    tenant, supplier, product, _ap, _inv, _cash = env
    settings_obj = get_or_create_purchase_settings(tenant)
    assert settings_obj.return_goods_on_post == "ask"
    assert settings_obj.price_variance_account is None

    inv = PurchaseInvoice.objects.create(
        tenant=tenant,
        invoice_number="PINV-DEF-1",
        invoice_date="2026-06-01",
        partner=supplier,
        currency=tenant._cur,
    )
    assert inv.return_mode == "legacy_combined"
    assert inv.ship_goods_on_post is True

    item = PurchaseInvoiceItem.objects.create(
        invoice=inv,
        product=product,
        name=product.name_ar,
        quantity=Decimal("5"),
        unit_price=Decimal("10"),
        total_price=Decimal("50"),
    )
    assert item.returned_quantity == Decimal("0")
    assert item.return_of_item is None
    assert item.posted_account is None
    assert item.posted_net_base is None
    assert item.posted_tax_base is None
    assert item.posted_clearing_base is None
    assert item.returned_net_base is None
    assert item.returned_tax_base is None
    assert item.returned_clearing_base is None


# ── 2) GoodsReturn & GoodsReturnLine ─────────────────────────────────────────

def test_goods_return_and_line_constraints(env):
    from logistics.models import GoodsReturn, GoodsReturnLine

    tenant_a, supplier_a, product_a, _ap_a, _inv_a, _cash_a = env
    tenant_b, supplier_b, _product_b, _ap_b, _inv_b, _cash_b = _setup_tenant(
        "m1ret2", "شركة M1 الثانية", tenant_a._cur,
    )
    wh_a = Warehouse.objects.get(tenant=tenant_a, is_default=True)

    grr_a = GoodsReturn.objects.create(
        tenant=tenant_a,
        return_number="GRR-0001",
        return_date="2026-06-15",
        partner=supplier_a,
    )
    assert grr_a.status == "draft"
    assert grr_a.auto_created_by is None

    line = GoodsReturnLine.objects.create(
        tenant=tenant_a,
        goods_return=grr_a,
        product=product_a,
        warehouse=wh_a,
        quantity=Decimal("2.0000"),
        clearing_unit_cost=Decimal("50.0000"),
    )
    assert line.id is not None

    # رفض quantity <= 0
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GoodsReturnLine.objects.create(
                tenant=tenant_a,
                goods_return=grr_a,
                product=product_a,
                warehouse=wh_a,
                quantity=Decimal("0"),
            )

    # return_number فريد داخل الشركة الواحدة
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GoodsReturn.objects.create(
                tenant=tenant_a,
                return_number="GRR-0001",
                return_date="2026-06-16",
                partner=supplier_a,
            )

    # ومسموح تكراره بين شركتين
    grr_b = GoodsReturn.objects.create(
        tenant=tenant_b,
        return_number="GRR-0001",
        return_date="2026-06-15",
        partner=supplier_b,
    )
    assert grr_b.id != grr_a.id


# ── 3) PurchaseReturnAllocation ──────────────────────────────────────────────

def test_purchase_return_allocation_constraints(env):
    from logistics.models import PurchaseReturnAllocation

    tenant, supplier, _product, _ap, _inv, _cash = env
    orig = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PINV-AL-1", invoice_date="2026-06-01",
        partner=supplier, currency=tenant._cur, grand_total=Decimal("100.00"),
    )
    pret = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PRET-AL-1", invoice_date="2026-06-02",
        partner=supplier, currency=tenant._cur, is_return=True,
        original_invoice=orig, grand_total=Decimal("50.00"),
    )

    alloc = PurchaseReturnAllocation.objects.create(
        tenant=tenant,
        purchase_return=pret,
        invoice=orig,
        amount=Decimal("50.00"),
        amount_base=Decimal("50.00"),
    )
    assert alloc.id is not None

    # رفض amount <= 0
    orig2 = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PINV-AL-2", invoice_date="2026-06-03",
        partner=supplier, currency=tenant._cur, grand_total=Decimal("100.00"),
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PurchaseReturnAllocation.objects.create(
                tenant=tenant,
                purchase_return=pret,
                invoice=orig2,
                amount=Decimal("0.00"),
                amount_base=Decimal("0.00"),
            )

    # رفض تكرار (purchase_return, invoice)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PurchaseReturnAllocation.objects.create(
                tenant=tenant,
                purchase_return=pret,
                invoice=orig,
                amount=Decimal("10.00"),
                amount_base=Decimal("10.00"),
            )


# ── 4) PartyRefundAllocation.source_purchase_return ──────────────────────────

def test_party_refund_allocation_source_purchase_return(env):
    tenant, supplier, _product, _ap, _inv, cash = env
    pret = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="PRET-REF-1", invoice_date="2026-06-02",
        partner=supplier, currency=tenant._cur, is_return=True,
        grand_total=Decimal("80.00"),
    )
    refund = CustomerPayment.objects.create(
        tenant=tenant, partner=supplier, kind=CustomerPayment.KIND_RECEIPT,
        payment_date="2026-06-05", amount=Decimal("80.00"),
        currency=tenant._cur, cash_or_bank_account=cash,
    )
    sp = SupplierPayment.objects.create(
        tenant=tenant, partner=supplier, payment_date="2026-06-01",
        amount=Decimal("80.00"), currency=tenant._cur, cash_or_bank_account=cash,
    )

    # مصدر purchase_return وحده يُحفظ
    ok = PartyRefundAllocation.objects.create(
        tenant=tenant,
        refund=refund,
        source_purchase_return=pret,
        amount=Decimal("80.00"),
        amount_base=Decimal("80.00"),
    )
    assert ok.source_purchase_return_id == pret.id

    # مصدران -> IntegrityError
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PartyRefundAllocation.objects.create(
                tenant=tenant,
                refund=refund,
                source_purchase_return=pret,
                source_supplier_payment=sp,
                amount=Decimal("10.00"),
                amount_base=Decimal("10.00"),
            )

    # بلا مصدر -> IntegrityError
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PartyRefundAllocation.objects.create(
                tenant=tenant,
                refund=refund,
                amount=Decimal("10.00"),
                amount_base=Decimal("10.00"),
            )


# ── 5) next_goods_return_number ──────────────────────────────────────────────

def test_next_goods_return_number_sequence_and_tenant_isolation(env):
    from logistics.services import next_goods_return_number

    tenant_a, *_ = env
    tenant_b, *_ = _setup_tenant("m1num2", "شركة ترقيم 2", tenant_a._cur)

    assert next_goods_return_number(tenant_a.TenantID) == "GRR-0001"
    assert next_goods_return_number(tenant_a.TenantID) == "GRR-0002"
    assert next_goods_return_number(tenant_b.TenantID) == "GRR-0001"


# ── 6) الإسناد الخلفي: بندان بسعر واحد في الأصل ─────────────────────────────

def test_backfill_two_lines_same_price_splits_without_return_of_item(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-BF-2L",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
            {"product": product, "name": product.name_ar, "quantity": 4, "unit_price": 10, "total_price": 40},
        ],
        receive_on_post=True,
    )
    l1, l2 = list(orig.items.order_by("id"))
    # محاكاة استلام جزئي على البند الأول: R1=3, R2=4
    l1.received_quantity = Decimal("3.0000")
    l1.save(update_fields=["received_quantity"])

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-BF-2L",
        lines=[{"product": product.id, "quantity": 5, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)
    ret_line = ret.items.get()

    out = _run_backfill(tenant=tenant.TenantID)
    assert "لم يُكتب شيء" not in out

    l1.refresh_from_db()
    l2.refresh_from_db()
    ret_line.refresh_from_db()
    assert l1.returned_quantity == Decimal("3.0000")
    assert l1.received_quantity == Decimal("0.0000")
    assert l2.returned_quantity == Decimal("2.0000")
    assert l2.received_quantity == Decimal("2.0000")
    # توزّع على بندين => return_of_item يبقى فارغاً
    assert ret_line.return_of_item is None

    applied = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, source_return_item=ret_line, status="applied",
    )
    assert applied.count() == 4
    deltas = {(r.item_id, r.field): (r.value_before, r.value_after) for r in applied}
    assert deltas[(l1.id, "returned_quantity")] == ("0.0000", "3.0000")
    assert deltas[(l1.id, "received_quantity")] == ("3.0000", "0.0000")
    assert deltas[(l2.id, "returned_quantity")] == ("0.0000", "2.0000")
    assert deltas[(l2.id, "received_quantity")] == ("4.0000", "2.0000")


# ── 7) بند أصل واحد: يُسند ويُضبط return_of_item ─────────────────────────────

def test_backfill_single_line_sets_return_of_item(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-BF-1L",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 6, "unit_price": 20, "total_price": 120},
        ],
        receive_on_post=True,
    )
    orig_line = orig.items.get()

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-BF-1L",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 20}],
    )
    post_purchase_return(ret, user=tenant._owner)
    ret_line = ret.items.get()

    _run_backfill(tenant=tenant.TenantID)

    orig_line.refresh_from_db()
    ret_line.refresh_from_db()
    assert orig_line.returned_quantity == Decimal("2.0000")
    assert orig_line.received_quantity == Decimal("4.0000")
    assert ret_line.return_of_item_id == orig_line.id

    roi_log = PurchaseReturnBackfill.objects.get(
        tenant=tenant, item=ret_line, source_return_item=ret_line, field="return_of_item", status="applied",
    )
    assert roi_log.value_before is None
    assert roi_log.value_after == str(orig_line.id)


# ── 8) الاستثناءات: تعدّد أسعار، q > ΣR، منتج غائب ────────────────────────────

def test_backfill_exceptions_do_not_modify_items(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, p_multi_price, _ap, _inv, _cash = env
    p_over = Product.objects.create(
        tenant=tenant, sku="SKU-OVER", name_ar="صنف-تجاوز",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"),
    )
    p_absent = Product.objects.create(
        tenant=tenant, sku="SKU-ABSENT", name_ar="صنف-غائب",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"),
    )

    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-BF-EXC",
        items_data=[
            {"product": p_multi_price, "name": p_multi_price.name_ar, "quantity": 3, "unit_price": 10, "total_price": 30},
            {"product": p_multi_price, "name": p_multi_price.name_ar, "quantity": 3, "unit_price": 15, "total_price": 45},
            {"product": p_over, "name": p_over.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
        ],
        receive_on_post=True,
    )
    # p_over مستلم 1 فقط والمرتجع 3
    over_line = orig.items.get(product=p_over)
    over_line.received_quantity = Decimal("1.0000")
    over_line.save(update_fields=["received_quantity"])

    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-BF-EXC",
        lines=[
            {"product": p_multi_price.id, "quantity": 2, "unit_price": 10},
            {"product": p_over.id, "quantity": 3, "unit_price": 10},
        ],
    )
    # صنف غير موجود في الأصل
    PurchaseInvoiceItem.objects.create(
        invoice=ret, product=p_absent, name=p_absent.name_ar,
        quantity=Decimal("1"), unit_price=Decimal("10"), total_price=Decimal("10"),
    )
    post_purchase_return(ret, user=tenant._owner)

    _run_backfill(tenant=tenant.TenantID)

    for it in orig.items.all():
        assert it.returned_quantity == Decimal("0")
    over_line.refresh_from_db()
    assert over_line.received_quantity == Decimal("1.0000")
    for rit in ret.items.all():
        assert rit.return_of_item is None

    excs = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, status="exception", field="returned_quantity",
    )
    assert excs.count() == 3
    ret_by_prod = {rit.product_id: rit.id for rit in ret.items.all()}
    reasons_by_sri = {e.source_return_item_id: e.reason for e in excs}
    assert reasons_by_sri == {
        ret_by_prod[p_multi_price.id]: "أ:تعدد_أسعار",
        ret_by_prod[p_over.id]: "ب:تجاوز_مستلم",
        ret_by_prod[p_absent.id]: "غير_موجود_بالأصل",
    }


# ── 9) --dry-run ──────────────────────────────────────────────────────────────

def test_backfill_dry_run_makes_zero_writes(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-DRY",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-DRY",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)

    before_bf_count = PurchaseReturnBackfill.objects.count()
    out = _run_backfill(tenant=tenant.TenantID, dry_run=True)
    assert "لم يُكتب شيء" in out
    assert PurchaseReturnBackfill.objects.count() == before_bf_count

    orig_line = orig.items.get()
    ret_line = ret.items.get()
    assert orig_line.returned_quantity == Decimal("0")
    assert orig_line.received_quantity == Decimal("5.0000")
    assert orig_line.posted_net_base is None
    assert ret_line.return_of_item is None


def _orig_with_posted_return(tenant, supplier, product, *, tag: str, ret_qty=2):
    orig = _post_local_invoice_via_api(
        tenant, supplier, number=f"PINV-{tag}",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number=f"PRET-{tag}",
        lines=[{"product": product.id, "quantity": ret_qty, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)
    return orig, ret


def test_backfill_command_without_flags_is_preview_and_writes_nothing(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="NOFLAG")

    out = StringIO()
    call_command("backfill_purchase_returns", tenant=tenant.TenantID, stdout=out)
    text = out.getvalue()
    assert "معاينة فقط — مرّر --apply للكتابة" in text
    assert "لم يُكتب شيء" in text
    assert PurchaseReturnBackfill.objects.count() == 0
    line = orig.items.get()
    assert line.returned_quantity == Decimal("0")
    assert line.received_quantity == Decimal("5.0000")
    assert line.posted_net_base is None
    assert ret.items.get().return_of_item is None


def test_backfill_command_apply_flag_writes(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="APPLY")

    out = StringIO()
    call_command("backfill_purchase_returns", tenant=tenant.TenantID, apply=True, stdout=out)
    assert "معاينة فقط" not in out.getvalue()
    assert PurchaseReturnBackfill.objects.filter(tenant=tenant, status="applied").exists()
    line = orig.items.get()
    assert line.returned_quantity == Decimal("2.0000")
    assert ret.items.get().return_of_item_id == line.id


def test_backfill_command_apply_with_dry_run_raises_command_error(env):
    tenant, *_ = env
    with pytest.raises(CommandError, match="--apply|--dry-run"):
        call_command("backfill_purchase_returns", tenant=tenant.TenantID, apply=True, dry_run=True)


def test_backfill_command_dry_run_flag_is_synonym_of_default(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    _orig_with_posted_return(tenant, supplier, product, tag="SYN")
    out = StringIO()
    call_command("backfill_purchase_returns", tenant=tenant.TenantID, dry_run=True, stdout=out)
    assert "معاينة فقط — مرّر --apply للكتابة" in out.getvalue()
    assert PurchaseReturnBackfill.objects.count() == 0


def test_backfill_rollback_is_preview_unless_apply(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="RBPREV")
    _run_backfill(tenant=tenant.TenantID)
    run_id = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, status="applied",
    ).values_list("run_id", flat=True).first()
    assert run_id

    out = StringIO()
    call_command("backfill_purchase_returns", tenant=tenant.TenantID, rollback=run_id, stdout=out)
    assert "معاينة فقط — مرّر --apply للكتابة" in out.getvalue()
    assert orig.items.get().returned_quantity == Decimal("2.0000")
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, status="rolled_back",
    ).count() == 0

    call_command("backfill_purchase_returns", tenant=tenant.TenantID, rollback=run_id,
                 apply=True, stdout=StringIO())
    assert orig.items.get().returned_quantity == Decimal("0.0000")
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, status="rolled_back",
    ).exists()


# ── 10) Idempotency ──────────────────────────────────────────────────────────

def test_backfill_is_idempotent(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-IDEMP",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-IDEMP",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)

    _run_backfill(tenant=tenant.TenantID)
    orig_line = orig.items.get()
    basis_snapshot = (
        orig_line.posted_account_id,
        orig_line.posted_net_base,
        orig_line.posted_tax_base,
        orig_line.posted_clearing_base,
        orig_line.returned_net_base,
        orig_line.returned_tax_base,
        orig_line.returned_clearing_base,
    )
    assert all(v is not None for v in basis_snapshot)
    count_after_first = PurchaseReturnBackfill.objects.filter(tenant=tenant).count()
    basis_count_first = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, invoice=orig, source_return_item__isnull=True,
    ).count()

    _run_backfill(tenant=tenant.TenantID)
    count_after_second = PurchaseReturnBackfill.objects.filter(tenant=tenant).count()
    basis_count_second = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, invoice=orig, source_return_item__isnull=True,
    ).count()

    orig_line.refresh_from_db()
    assert orig_line.returned_quantity == Decimal("2.0000")
    assert orig_line.received_quantity == Decimal("3.0000")
    assert (
        orig_line.posted_account_id,
        orig_line.posted_net_base,
        orig_line.posted_tax_base,
        orig_line.posted_clearing_base,
        orig_line.returned_net_base,
        orig_line.returned_tax_base,
        orig_line.returned_clearing_base,
    ) == basis_snapshot
    assert count_after_second == count_after_first
    assert basis_count_second == basis_count_first


# ── 11) التراجع الذرّي والتعارض ───────────────────────────────────────────────

def test_backfill_rollback_and_conflict_detection(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-RB-2", name_ar="صنف-تراجع-2",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"),
    )
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-RB",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
            {"product": product2, "name": product2.name_ar, "quantity": 4, "unit_price": 10, "total_price": 40},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-RB",
        lines=[
            {"product": product.id, "quantity": 2, "unit_price": 10},
            {"product": product2.id, "quantity": 1, "unit_price": 10},
        ],
    )
    post_purchase_return(ret, user=tenant._owner)

    _run_backfill(tenant=tenant.TenantID)
    run_id = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, status="applied",
    ).values_list("run_id", flat=True).first()
    assert run_id

    # تعديل يدوي على returned_quantity للمنتج الأول فقط -> تعارض يوقف وحدة (orig, product) كاملةً
    orig_line1 = orig.items.get(product=product)
    orig_line2 = orig.items.get(product=product2)
    ret_line1 = ret.items.get(product=product)
    ret_line2 = ret.items.get(product=product2)

    orig_line1.returned_quantity = Decimal("9.0000")
    orig_line1.save(update_fields=["returned_quantity"])

    out_conflict = _run_backfill(tenant=tenant.TenantID, rollback=run_id)
    assert "تعارض" in out_conflict

    orig_line1.refresh_from_db()
    orig_line2.refresh_from_db()
    ret_line1.refresh_from_db()
    ret_line2.refresh_from_db()

    # الوحدة المتعارضة (orig, product) تبقى بلا أي كتابة (لا نصف تراجع)
    assert orig_line1.returned_quantity == Decimal("9.0000")
    assert orig_line1.received_quantity == Decimal("3.0000")
    assert ret_line1.return_of_item_id == orig_line1.id
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, source_return_item=ret_line1, status="applied",
    ).count() == 3

    # الوحدات الأخرى غير المتعارضة (وحدة product2 ووحدة أساس الفاتورة) تُعكس كاملةً
    assert orig_line2.returned_quantity == Decimal("0.0000")
    assert orig_line2.received_quantity == Decimal("4.0000")
    assert ret_line2.return_of_item is None
    assert orig_line1.posted_net_base is None
    assert orig_line2.posted_net_base is None
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, source_return_item=ret_line2, status="rolled_back",
    ).count() == 3
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, invoice=orig, source_return_item__isnull=True, status="rolled_back",
    ).count() == 14


# ── 11-ب) الأقفال في الكتابة الحقيقية (§10.1.3) ─────────────────────────────

class _LockSpy:
    """يلتقط استدعاءات `select_for_update` (موديل + ترتيب) ويُشغّل خطّافاً عند أول قفلِ فاتورة.

    SQLite لا يُصدر `FOR UPDATE`؛ فالجاسوس يثبت الترتيب والقراءة بعد القفل لا القفل الفعلي."""

    def __init__(self, monkeypatch, on_first_invoice_lock=None):
        from django.db.models.query import QuerySet

        self.calls: list[tuple[str, tuple]] = []
        self._hook = on_first_invoice_lock
        original = QuerySet.select_for_update
        spy = self

        def wrapper(qs, *args, **kwargs):
            spy.calls.append((qs.model.__name__, tuple(qs.query.order_by)))
            if qs.model.__name__ == "PurchaseInvoice" and spy._hook is not None:
                hook, spy._hook = spy._hook, None
                hook()
            return original(qs, *args, **kwargs)

        monkeypatch.setattr(QuerySet, "select_for_update", wrapper)

    def models(self) -> list[str]:
        return [m for m, _o in self.calls]


def test_backfill_rollback_locks_invoice_then_items_and_rereads_after_lock(env, monkeypatch):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="LOCKRB")
    _run_backfill(tenant=tenant.TenantID)
    run_id = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, status="applied",
    ).values_list("run_id", flat=True).first()
    line = orig.items.get()
    assert line.returned_quantity == Decimal("2.0000")

    # بين تحميل الصفوف وقفل الفاتورة يغيّر طرفٌ آخر القيمة في القاعدة
    def concurrent_change():
        PurchaseInvoiceItem.objects.filter(pk=line.pk).update(returned_quantity=Decimal("4.0000"))

    spy = _LockSpy(monkeypatch, on_first_invoice_lock=concurrent_change)
    out = _run_backfill(tenant=tenant.TenantID, rollback=run_id)

    # الترتيب الثابت: فاتورة ثم بنودها مرتّبةً بالـid (الأصل أولاً ثم مستند المرتجع)
    assert spy.models()[:2] == ["PurchaseInvoice", "PurchaseInvoiceItem"]
    assert spy.calls[1][1] == ("id",)
    assert spy.models()[:4] == ["PurchaseInvoice", "PurchaseInvoiceItem"] * 2

    # القيمة المفحوصة قُرئت بعد القفل: التعارض يُكتشف ولا يُكتب فوق قيمة الطرف الآخر
    assert "تعارض" in out
    line.refresh_from_db()
    assert line.returned_quantity == Decimal("4.0000")
    assert line.received_quantity == Decimal("3.0000")
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, source_return_item__isnull=False, status="rolled_back",
    ).exists()


def test_backfill_rollback_preview_takes_no_locks(env, monkeypatch):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    _orig_with_posted_return(tenant, supplier, product, tag="LOCKPREV")
    _run_backfill(tenant=tenant.TenantID)
    run_id = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, status="applied",
    ).values_list("run_id", flat=True).first()

    spy = _LockSpy(monkeypatch)
    out = _run_backfill(tenant=tenant.TenantID, rollback=run_id, apply=False)
    assert "معاينة فقط" in out
    assert spy.calls == []


def test_backfill_quantities_apply_locks_original_invoice_then_items_and_reads_after_lock(env, monkeypatch):
    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="LOCKFWD")
    line = orig.items.get()
    assert line.received_quantity == Decimal("5.0000")

    # بين تحميل المرتجعات وقفل الأصل يتغيّر المستلَم في القاعدة (5 -> 3)
    def concurrent_change():
        PurchaseInvoiceItem.objects.filter(pk=line.pk).update(received_quantity=Decimal("3.0000"))

    spy = _LockSpy(monkeypatch, on_first_invoice_lock=concurrent_change)
    _run_backfill(tenant=tenant.TenantID, apply=True)

    assert spy.models()[:2] == ["PurchaseInvoice", "PurchaseInvoiceItem"]
    assert spy.calls[1][1] == ("id",)
    # الكميات حُسبت من القيم المقروءة بعد القفل (3 - 2 = 1) لا من القراءة السابقة (5 - 2 = 3)
    line.refresh_from_db()
    assert line.returned_quantity == Decimal("2.0000")
    assert line.received_quantity == Decimal("1.0000")


def test_backfill_forward_preview_takes_no_locks(env, monkeypatch):
    tenant, supplier, product, _ap, _inv, _cash = env
    _orig_with_posted_return(tenant, supplier, product, tag="LOCKFWDP")
    spy = _LockSpy(monkeypatch)
    _run_backfill(tenant=tenant.TenantID, dry_run=True)
    assert spy.calls == []


def _unreturned_invoice(tenant, supplier, product, *, number):
    """فاتورة مرحّلة بلا مرتجع: أول قفلِ فاتورةٍ في الكتابة الحقيقية يكون لمرحلة الأساس."""
    return _post_local_invoice_via_api(
        tenant, supplier, number=number,
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 2, "unit_price": 10, "total_price": 20},
        ],
        receive_on_post=False,
    )


def test_backfill_basis_apply_locks_invoice_then_items_before_computing(env, monkeypatch):
    from logistics import purchase_return_basis as prb

    tenant, supplier, product, _ap, _inv, _cash = env
    inv = _unreturned_invoice(tenant, supplier, product, number="PINV-LOCKBAS")
    spy = _LockSpy(monkeypatch)
    real_compute = prb._compute_invoice_line_basis_with_reason

    def compute_spy(invoice):
        spy.calls.append(("compute", ()))
        return real_compute(invoice)

    monkeypatch.setattr(prb, "_compute_invoice_line_basis_with_reason", compute_spy)
    prb.run_backfill_for_tenant(tenant, dry_run=False)

    # الفاتورة ثم بنودها مرتّبةً بالـid، ثم الحساب
    assert spy.models() == ["PurchaseInvoice", "PurchaseInvoiceItem", "compute"]
    assert spy.calls[1][1] == ("id",)
    assert inv.items.get().posted_net_base == Decimal("20.00")


def test_backfill_basis_apply_decides_fill_state_on_values_read_after_lock(env, monkeypatch):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    inv = _unreturned_invoice(tenant, supplier, product, number="PINV-LOCKBAS-FILL")
    line = inv.items.get()
    marker = {"posted_net_base": Decimal("1.00"), "posted_tax_base": Decimal("0.00"),
              "posted_clearing_base": Decimal("1.00")}

    # بين تحميل الفواتير وقفلها يعبّئ طرفٌ آخر الأساس ⇒ بعد القفل كلها معبّأة ⇒ تخطٍّ بلا كتابة
    def concurrent_fill():
        PurchaseInvoiceItem.objects.filter(pk=line.pk).update(**marker)

    _LockSpy(monkeypatch, on_first_invoice_lock=concurrent_fill)
    prb.run_backfill_for_tenant(tenant, dry_run=False)

    f = _basis_fields(line)
    assert (f["net"], f["tax"], f["clr"]) == (Decimal("1.00"), Decimal("0.00"), Decimal("1.00"))
    assert f["r_net"] is None
    assert not PurchaseReturnBackfill.objects.filter(tenant=tenant, invoice=inv).exists()


def test_backfill_basis_apply_skips_invoice_unposted_after_lock(env, monkeypatch):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    inv = _unreturned_invoice(tenant, supplier, product, number="PINV-LOCKBAS-UNPOST")

    def concurrent_unpost():
        PurchaseInvoice.objects.filter(pk=inv.pk).update(is_posted=False)

    _LockSpy(monkeypatch, on_first_invoice_lock=concurrent_unpost)
    prb.run_backfill_for_tenant(tenant, dry_run=False)

    f = _basis_fields(inv.items.get())
    assert f["net"] is None and f["r_net"] is None
    assert inv.items.get().posted_account_id is None
    assert not PurchaseReturnBackfill.objects.filter(tenant=tenant, invoice=inv).exists()


def test_backfill_basis_preview_takes_no_locks(env, monkeypatch):
    from logistics import purchase_return_basis as prb

    tenant, supplier, product, _ap, _inv, _cash = env
    _unreturned_invoice(tenant, supplier, product, number="PINV-LOCKBAS-PREV")
    spy = _LockSpy(monkeypatch)
    res = prb.run_backfill_for_tenant(tenant, dry_run=True)
    assert res.basis_matched == 1
    assert spy.calls == []


def test_backfill_quantities_ignore_returns_in_invoice_mode(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="MODEINV")
    PurchaseInvoice.objects.filter(pk=ret.pk).update(return_mode=PurchaseInvoice.RETURN_MODE_INVOICE)

    _run_backfill(tenant=tenant.TenantID)

    line = orig.items.get()
    assert line.returned_quantity == Decimal("0")
    assert line.received_quantity == Decimal("5.0000")
    assert ret.items.get().return_of_item is None
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, source_return_item__invoice=ret,
    ).exists()


def test_backfill_quantities_rereads_applied_log_after_lock(env, monkeypatch):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="APPLOCK")
    line = orig.items.get()
    ret_line = ret.items.get()
    real_lock = prb.lock_invoices_with_items
    fired: list[bool] = []

    # تشغيلٌ متزامن يُسند المرتجع نفسه بين قراءة السجلّ وأخذ الأقفال
    def concurrent_run_applies_first(invoice_ids, **kwargs):
        if not fired:
            fired.append(True)
            PurchaseInvoiceItem.objects.filter(pk=line.pk).update(
                returned_quantity=Decimal("2.0000"), received_quantity=Decimal("3.0000"),
            )
            PurchaseReturnBackfill.objects.create(
                tenant=tenant, run_id="concurrent-run", unit_key=f"qty:{orig.id}:{product.id}",
                invoice=orig, item=line, source_return_item=ret_line, field="returned_quantity",
                value_before="0.0000", value_after="2.0000", status="applied",
            )
        return real_lock(invoice_ids, **kwargs)

    monkeypatch.setattr(prb, "lock_invoices_with_items", concurrent_run_applies_first)
    prb.run_backfill_for_tenant(tenant, dry_run=False)

    line.refresh_from_db()
    assert line.returned_quantity == Decimal("2.0000")
    assert line.received_quantity == Decimal("3.0000")
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, source_return_item=ret_line, status="applied",
    ).exclude(run_id="concurrent-run").exists()


def test_resolve_goods_account_readonly_ignores_other_tenant_account(env, monkeypatch):
    """حساب المخزون المحلول من منتج لا يُقبل إلا إن كان من شركة الفاتورة نفسها (عزل الشركة)."""
    import inventory.services as inv_services
    from logistics import purchase_return_basis as prb

    tenant, _supplier, product, _ap, own_inventory, _cash = env
    other = _setup_tenant("m1ret2", "شركة M1 ب", tenant._cur)
    foreign_account = other[4]
    assert foreign_account.tenant_id != tenant.TenantID

    monkeypatch.setattr(inv_services, "_resolve_line_account", lambda *a, **k: foreign_account)
    invoice = PurchaseInvoice(
        tenant=tenant, deal_id=999999, receipt_status=PurchaseInvoice.RECEIPT_FULL,
    )
    item = PurchaseInvoiceItem(
        product=product, quantity=Decimal("1"), unit_price=Decimal("10"), total_price=Decimal("10"),
    )

    result = prb._resolve_goods_account_readonly(invoice, [item])

    assert result != foreign_account.id
    assert result == own_inventory.id


def test_backfill_draft_old_return_with_apply_leaves_no_trace(env):
    """مرتجع قديم مسوّدة (غير مرحَّل): `--apply` لا يسند كمياته ولا يكتب سجلّاً."""
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-DRAFT",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-DRAFT",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 10}],
    )
    assert ret.is_posted is False

    before_orig = orig.items.values("returned_quantity", "received_quantity", "return_of_item_id").get()
    before_ret = ret.items.values("return_of_item_id", "returned_quantity", "received_quantity").get()

    _run_backfill(tenant=tenant.TenantID, apply=True)

    # لا صفّ كميات ولا ربطٍ بالبند الأصلي (أساس الفاتورة الأصلية المرحّلة يُسجَّل بشكل مشروع)
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant,
        field__in=("returned_quantity", "received_quantity", "return_of_item"),
    ).exists()
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, source_return_item__invoice=ret,
    ).exists()
    assert orig.items.values("returned_quantity", "received_quantity", "return_of_item_id").get() == before_orig
    assert ret.items.values("return_of_item_id", "returned_quantity", "received_quantity").get() == before_ret
    assert before_orig["returned_quantity"] == Decimal("0")
    assert before_ret["return_of_item_id"] is None


# ── 12) دالّة الأساس ومطابقة القيد ومثال التقريب ──────────────────────────────

def test_basis_local_with_expense_discount_tax_and_rounding(env):
    from logistics.models import PurchaseReturnBackfill
    from logistics.purchase_return_basis import basis_matches_journal, compute_invoice_line_basis

    tenant, supplier, product, _ap, _inv, _cash = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-B2", name_ar="صنف-ثاني",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("30"),
    )
    exp_acc = Account.objects.filter(tenant=tenant, account_type="Expense").first()
    if exp_acc is None:
        exp_acc = Account.objects.create(
            tenant=tenant, code="5399", name="مصروف اختبار", account_type="Expense", is_active=True,
        )

    # 1) فاتورة محلية بخصم رأس + بند مصروف + بندي بضاعة + ضريبة
    inv = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-BASIS-1",
        items_data=[
            {"product": None, "name": "خدمة شحن", "quantity": 1, "unit_price": 100, "total_price": 100,
             "is_taxable": True, "vat_percent": 16, "expense_account": exp_acc},
            {"product": product, "name": product.name_ar, "quantity": 2, "unit_price": 100, "total_price": 200,
             "is_taxable": True, "vat_percent": 16},
            {"product": product2, "name": product2.name_ar, "quantity": 3, "unit_price": 100, "total_price": 300,
             "is_taxable": True, "vat_percent": 16},
        ],
        discount_amount=Decimal("60.00"),
        tax_amount=Decimal("86.40"),
        receive_on_post=False,
    )
    basis = compute_invoice_line_basis(inv)
    matched, reason = basis_matches_journal(inv, basis)
    assert matched, reason

    exp_item = inv.items.get(expense_account=exp_acc)
    g1 = inv.items.get(product=product)
    g2 = inv.items.get(product=product2)
    assert basis[exp_item.id].account_id == exp_acc.id
    assert basis[exp_item.id].clearing_base == Decimal("0.00")
    assert basis[exp_item.id].net_base == Decimal("90.00")
    assert (basis[g1.id].clearing_base + basis[g2.id].clearing_base) == Decimal("450.00")
    assert (basis[exp_item.id].tax_base + basis[g1.id].tax_base + basis[g2.id].tax_base) == Decimal("86.40")

    # 2) مثال التقريب: 3 × 33.33 بضريبة 16% -> مجموع ضريبة البنود = قيمة الفاتورة بالضبط
    inv_round = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-BASIS-ROUND",
        items_data=[
            {"product": product, "name": "أ", "quantity": 1, "unit_price": "33.33", "total_price": "33.33",
             "is_taxable": True, "vat_percent": 16},
            {"product": product, "name": "ب", "quantity": 1, "unit_price": "33.33", "total_price": "33.33",
             "is_taxable": True, "vat_percent": 16},
            {"product": product, "name": "ج", "quantity": 1, "unit_price": "33.33", "total_price": "33.33",
             "is_taxable": True, "vat_percent": 16},
        ],
        tax_amount=Decimal("16.00"),
        receive_on_post=False,
    )
    basis_round = compute_invoice_line_basis(inv_round)
    ok_r, reason_r = basis_matches_journal(inv_round, basis_round)
    assert ok_r, reason_r
    assert sum((b.tax_base for b in basis_round.values()), Decimal("0.00")) == Decimal("16.00")
    # توزيع الضريبة على البنود بترتيب الـid: باقي الفلسات (0.01) يذهب إلى أول بند
    round_items = list(inv_round.items.order_by("id"))
    assert [basis_round[it.id].tax_base for it in round_items] == [
        Decimal("5.34"), Decimal("5.33"), Decimal("5.33"),
    ]

    # 3) حالة فرق: نعدّل سطر القيد في الاختبار فتفشل المطابقة وتُحفظ exception
    inv_bad = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-BASIS-BAD",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 2, "unit_price": 50, "total_price": 100,
             "is_taxable": False},
        ],
        receive_on_post=False,
    )
    JournalLine.objects.filter(journal=inv_bad.journal, debit__gt=0).update(
        debit=Decimal("95.00"), base_debit=Decimal("95.00"),
    )

    _run_backfill(tenant=tenant.TenantID)

    # المطابقتان حُفظت حقولهما
    inv.refresh_from_db()
    for it in inv.items.all():
        assert it.posted_net_base is not None
        assert it.returned_net_base == Decimal("0.00")
    inv_round.refresh_from_db()
    for it in inv_round.items.all():
        assert it.posted_tax_base is not None

    # المختلفة بقيت فارغة وسُجِّلت exception
    bad_item = inv_bad.items.get()
    assert bad_item.posted_account is None
    assert bad_item.posted_net_base is None
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, invoice=inv_bad, item__isnull=True, field="basis", status="exception",
    ).exists()


# ── 12-أ) حارس مرآة الترحيل: فاتورة يرفض الترحيلُ قيدَها لا أساس لها ────────────

def _draft_expense_only_invoice(tenant, supplier, *, number, grand_total):
    exp_acc = Account.objects.filter(tenant=tenant, account_type="Expense").first()
    if exp_acc is None:
        exp_acc = Account.objects.create(
            tenant=tenant, code="5398", name="مصروف حارس", account_type="Expense", is_active=True,
        )
    inv = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number=number, invoice_date="2026-06-01", partner=supplier,
        currency=tenant._cur, exchange_rate=Decimal("1"),
        invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        subtotal=Decimal("50.00"), grand_total=Decimal(grand_total),
    )
    PurchaseInvoiceItem.objects.create(
        invoice=inv, product=None, name="خدمة", quantity=Decimal("1"),
        unit_price=Decimal("50"), total_price=Decimal("50"), expense_account=exp_acc,
    )
    return inv


def test_basis_mirror_returns_empty_when_posting_would_reject_negative_inventory_debit(env):
    from logistics.purchase_return_basis import compute_invoice_line_basis

    tenant, supplier, _product, _ap, _inv, _cash = env
    # الإجمالي 10 أقلّ من بند المصروف 50 ⇒ مدين المخزون −40 < −0.02 ⇒ الترحيل يرفض، فلا أساس
    inv = _draft_expense_only_invoice(tenant, supplier, number="PINV-GUARD-NEG", grand_total="10.00")
    assert compute_invoice_line_basis(inv) == {}


def test_basis_mirror_keeps_rounding_tolerance_at_minus_two_fils(env):
    from logistics.purchase_return_basis import compute_invoice_line_basis

    tenant, supplier, _product, _ap, _inv, _cash = env
    # −0.02 بالضبط داخل هامش التقريب كما في الترحيل: يُمتصّ في أكبر حساب مصروف
    inv = _draft_expense_only_invoice(tenant, supplier, number="PINV-GUARD-EDGE", grand_total="49.98")
    basis = compute_invoice_line_basis(inv)
    item = inv.items.get()
    assert basis[item.id].net_base == Decimal("49.98")


# ── 12-ب) أساس العكس E لمرتجعٍ قديم (PRET-M1 fix2 §10.1.2) ─────────────────

def _basis_fields(item):
    item.refresh_from_db()
    return {
        "net": item.posted_net_base, "tax": item.posted_tax_base, "clr": item.posted_clearing_base,
        "r_net": item.returned_net_base, "r_tax": item.returned_tax_base, "r_clr": item.returned_clearing_base,
    }


def test_backfill_basis_carries_already_reversed_for_old_partial_return(env):
    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-E-PART",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 10, "unit_price": 10,
             "total_price": 100, "is_taxable": True, "vat_percent": 16},
        ],
        tax_amount=Decimal("16.00"),
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-E-PART",
        lines=[{"product": product.id, "quantity": 4, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)

    _run_backfill(tenant=tenant.TenantID)

    f = _basis_fields(orig.items.get())
    assert f["net"] == Decimal("100.00")
    assert f["tax"] == Decimal("16.00")
    # E = round(P × R / Q, 2) لكل مكوّنٍ على حدة، R=4 من Q=10
    assert f["r_net"] == Decimal("40.00")
    assert f["r_tax"] == Decimal("6.40")
    assert f["r_clr"] == (f["clr"] * Decimal("4") / Decimal("10")).quantize(Decimal("0.01"))
    assert f["r_clr"] > Decimal("0.00")


def test_backfill_basis_full_quantity_old_return_equals_posted_exactly(env):
    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-E-FULL",
        items_data=[
            {"product": product, "name": "أ", "quantity": 1, "unit_price": "33.33", "total_price": "33.33",
             "is_taxable": True, "vat_percent": 16},
            {"product": product, "name": "ب", "quantity": 1, "unit_price": "33.33", "total_price": "33.33",
             "is_taxable": True, "vat_percent": 16},
            {"product": product, "name": "ج", "quantity": 1, "unit_price": "33.33", "total_price": "33.33",
             "is_taxable": True, "vat_percent": 16},
        ],
        tax_amount=Decimal("16.00"),
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-E-FULL",
        lines=[{"product": product.id, "quantity": 3, "unit_price": "33.33"}],
    )
    post_purchase_return(ret, user=tenant._owner)

    _run_backfill(tenant=tenant.TenantID)

    total_tax = Decimal("0.00")
    for it in orig.items.all():
        f = _basis_fields(it)
        assert it.returned_quantity == Decimal("1.0000")
        assert f["r_net"] == f["net"]
        assert f["r_tax"] == f["tax"]
        assert f["r_clr"] == f["clr"]
        total_tax += f["r_tax"]
    assert total_tax == Decimal("16.00")


def test_backfill_preview_value_after_for_returned_basis_equals_applied(env, monkeypatch):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-E-PREV",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 10, "unit_price": 10,
             "total_price": 100, "is_taxable": True, "vat_percent": 16},
        ],
        tax_amount=Decimal("16.00"),
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-E-PREV",
        lines=[{"product": product.id, "quantity": 3, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)

    captured: list = []
    real = prb._backfill_basis_for_tenant

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        captured.extend(kwargs["pending_logs"])
        return out

    monkeypatch.setattr(prb, "_backfill_basis_for_tenant", spy)
    prb.run_backfill_for_tenant(tenant, dry_run=True)
    preview = {
        r.field: r.value_after for r in captured
        if r.field in ("returned_net_base", "returned_tax_base", "returned_clearing_base")
    }
    assert set(preview) == {"returned_net_base", "returned_tax_base", "returned_clearing_base"}
    assert preview["returned_net_base"] == "30.00"
    assert PurchaseReturnBackfill.objects.count() == 0

    prb.run_backfill_for_tenant(tenant, dry_run=False)
    applied = {
        r.field: r.value_after for r in PurchaseReturnBackfill.objects.filter(
            tenant=tenant, status="applied",
            field__in=("returned_net_base", "returned_tax_base", "returned_clearing_base"),
        )
    }
    assert applied == preview
    item = orig.items.get()
    item.refresh_from_db()
    assert str(item.returned_net_base) == preview["returned_net_base"]
    assert str(item.returned_tax_base) == preview["returned_tax_base"]
    assert str(item.returned_clearing_base) == preview["returned_clearing_base"]


def test_already_reversed_basis_caps_at_posted_when_returned_exceeds_quantity():
    from logistics.purchase_return_basis import already_reversed_basis

    # دفاعي: لا يُعكس أكثر ممّا قُيِّد (12 من 10 ⇒ P بالضبط لا 120.00)
    assert already_reversed_basis(Decimal("100.00"), quantity=10, returned=12) == Decimal("100.00")


def test_already_reversed_basis_rounds_half_up_per_component():
    from logistics.purchase_return_basis import already_reversed_basis

    # 0.025 ⇒ 0.03 بـROUND_HALF_UP (التقريب المصرفي يعطي 0.02)
    assert already_reversed_basis(Decimal("0.05"), quantity=2, returned=1) == Decimal("0.03")
    assert already_reversed_basis(Decimal("16.00"), quantity=3, returned=1) == Decimal("5.33")


def _filled_basis_then_second_old_return(env):
    """تشغيلٌ أوّل يعبّئ الأساس بمرتجعٍ جزئي (2 من 5)، ثم مرتجعٌ قديم ثانٍ مرحَّل (1) على البند نفسه."""
    tenant, supplier, product, _ap, _inv, _cash = env
    orig, _ret1 = _orig_with_posted_return(tenant, supplier, product, tag="E-RERUN", ret_qty=2)
    _run_backfill(tenant=tenant.TenantID)
    line = orig.items.get()
    first = _basis_fields(line)
    first["account"] = line.posted_account_id
    assert line.returned_quantity == Decimal("2.0000")
    assert first["r_net"] == Decimal("20.00")
    ret2 = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-20",
        invoice_number="PRET-E-RERUN-2",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 10}],
    )
    post_purchase_return(ret2, user=tenant._owner)
    return tenant, orig, ret2, first


def test_backfill_rerun_updates_returned_basis_for_new_returned_quantity(env, monkeypatch):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill
    from logistics.purchase_return_basis import already_reversed_basis

    tenant, orig, ret2, first = _filled_basis_then_second_old_return(env)
    returned_fields = ("returned_net_base", "returned_tax_base", "returned_clearing_base")

    captured: list = []
    real = prb._backfill_basis_for_tenant

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        captured.extend(kwargs["pending_logs"])
        return out

    monkeypatch.setattr(prb, "_backfill_basis_for_tenant", spy)
    rows_before = PurchaseReturnBackfill.objects.count()
    prb.run_backfill_for_tenant(tenant, dry_run=True)
    preview = {(r.field, r.value_before, r.value_after) for r in captured if r.field in returned_fields}
    assert PurchaseReturnBackfill.objects.count() == rows_before
    assert _basis_fields(orig.items.get())["r_net"] == Decimal("20.00")

    prb.run_backfill_for_tenant(tenant, dry_run=False)

    line = orig.items.get()
    f = _basis_fields(line)
    assert line.returned_quantity == Decimal("3.0000")
    # posted_* والحساب لا يُمسّان، وreturned_*_base = حصّة returned_quantity الجديدة من المخزَّن
    assert (f["net"], f["tax"], f["clr"]) == (first["net"], first["tax"], first["clr"])
    assert line.posted_account_id == first["account"]
    assert f["r_net"] == already_reversed_basis(first["net"], quantity=5, returned=3) == Decimal("30.00")
    assert f["r_tax"] == already_reversed_basis(first["tax"], quantity=5, returned=3)
    assert f["r_clr"] == already_reversed_basis(first["clr"], quantity=5, returned=3)

    run2 = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, source_return_item__invoice=ret2, status="applied",
    ).values_list("run_id", flat=True).first()
    basis_rows = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run2, invoice=orig, source_return_item__isnull=True, status="applied",
    )
    assert not basis_rows.exclude(field__in=returned_fields).exists()
    applied = {(r.field, r.value_before, r.value_after) for r in basis_rows}
    assert ("returned_net_base", "20.00", "30.00") in applied
    assert all(before != after for _f, before, after in applied)
    assert set(basis_rows.values_list("unit_key", flat=True)) == {f"basis:{orig.id}"}
    assert applied == preview


def test_backfill_rerun_returned_basis_update_rolls_back(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, orig, ret2, first = _filled_basis_then_second_old_return(env)
    _run_backfill(tenant=tenant.TenantID)
    run2 = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, source_return_item__invoice=ret2, status="applied",
    ).values_list("run_id", flat=True).first()
    assert _basis_fields(orig.items.get())["r_net"] == Decimal("30.00")

    _run_backfill(tenant=tenant.TenantID, rollback=run2)
    # كل وحدات التشغيل الثاني عُكست (لا تعارض يُبقي صفّاً مطبَّقاً)
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run2, status="applied",
    ).exists()

    line = orig.items.get()
    f = _basis_fields(line)
    assert line.returned_quantity == Decimal("2.0000")
    assert (f["r_net"], f["r_tax"], f["r_clr"]) == (first["r_net"], first["r_tax"], first["r_clr"])
    assert (f["net"], f["tax"], f["clr"]) == (first["net"], first["tax"], first["clr"])
    assert line.posted_account_id == first["account"]


def test_backfill_basis_stays_empty_when_invoice_has_unassigned_return(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-E-EXC",
        items_data=[
            {"product": product, "name": "س1", "quantity": 3, "unit_price": 10, "total_price": 30},
            {"product": product, "name": "س2", "quantity": 3, "unit_price": 15, "total_price": 45},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-E-EXC",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)

    res = prb.run_backfill_for_tenant(tenant, dry_run=False)
    assert res.exceptions_count == 1
    assert res.basis_matched == 0
    assert res.basis_mismatched == 1
    for it in orig.items.all():
        f = _basis_fields(it)
        assert f["net"] is None and f["tax"] is None and f["clr"] is None
        assert f["r_net"] is None and f["r_tax"] is None and f["r_clr"] is None
        assert it.posted_account_id is None
    row = PurchaseReturnBackfill.objects.get(
        tenant=tenant, invoice=orig, field="basis", status="exception",
    )
    assert row.reason == "مرتجع غير مُسند على الفاتورة"

    # إعادة التشغيل لا تكرّر صفّ الاستثناء
    prb.run_backfill_for_tenant(tenant, dry_run=False)
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, invoice=orig, field="basis", status="exception",
    ).count() == 1


# ── 12-ج) فاتورة معبّأة جزئياً: كلها معبّأة تُتخطّى، كلها فارغة تُعبّأ، المختلطة استثناء ──

def test_backfill_basis_fill_states_all_filled_skip_empty_fill_mixed_exception(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env

    def two_line_invoice(number):
        return _post_local_invoice_via_api(
            tenant, supplier, number=number,
            items_data=[
                {"product": product, "name": "أ", "quantity": 2, "unit_price": 10, "total_price": 20},
                {"product": product, "name": "ب", "quantity": 3, "unit_price": 10, "total_price": 30},
            ],
            receive_on_post=False,
        )

    marker = {"posted_net_base": Decimal("1.00"), "posted_tax_base": Decimal("0.00"),
              "posted_clearing_base": Decimal("1.00")}

    inv_filled = two_line_invoice("PINV-FS-FILLED")
    inv_filled.items.update(**marker)
    inv_empty = two_line_invoice("PINV-FS-EMPTY")
    inv_mixed = two_line_invoice("PINV-FS-MIXED")
    first_mixed = inv_mixed.items.order_by("id").first()
    PurchaseInvoiceItem.objects.filter(pk=first_mixed.pk).update(**marker)

    res = prb.run_backfill_for_tenant(tenant, dry_run=False)

    # كلها معبّأة: لا كتابة ولا سجلّ
    for it in inv_filled.items.all():
        assert it.posted_net_base == Decimal("1.00")
    assert not PurchaseReturnBackfill.objects.filter(tenant=tenant, invoice=inv_filled).exists()

    # كلها فارغة: تُعبّأ
    for it in inv_empty.items.all():
        assert it.posted_net_base in (Decimal("20.00"), Decimal("30.00"))
        assert it.returned_net_base == Decimal("0.00")

    # مختلطة: لا كتابة، واستثناء أساسٍ واحد بالسبب الحرفي
    mixed_items = list(inv_mixed.items.order_by("id"))
    assert mixed_items[0].posted_net_base == Decimal("1.00")
    assert mixed_items[1].posted_net_base is None
    assert mixed_items[1].returned_net_base is None
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, invoice=inv_mixed, status="applied",
    ).exists()
    row = PurchaseReturnBackfill.objects.get(
        tenant=tenant, invoice=inv_mixed, field="basis", status="exception",
    )
    assert row.reason == "أساس معبّأ جزئياً"
    assert res.basis_matched == 1
    assert res.basis_mismatched == 1


# ── 13) لا قيد ولا حركة مخزون جديدة ──────────────────────────────────────────

def test_backfill_creates_no_journals_or_stock_movements(env):
    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-NOJM",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 20, "total_price": 100},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-NOJM",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 20}],
    )
    post_purchase_return(ret, user=tenant._owner)

    jh_before = JournalHeader.objects.count()
    jl_before = JournalLine.objects.count()
    sm_before = StockMovement.objects.count()

    _run_backfill(tenant=tenant.TenantID)

    assert JournalHeader.objects.count() == jh_before
    assert JournalLine.objects.count() == jl_before
    assert StockMovement.objects.count() == sm_before
    assert orig.items.get().returned_quantity == Decimal("1.0000")


# ── 14) العزل بالشركة و--tenant ───────────────────────────────────────────────

def test_backfill_tenant_flag_and_cross_tenant_isolation(env):
    from logistics.models import PurchaseReturnBackfill

    tenant_a, supplier_a, product_a, _ap_a, _inv_a, _cash_a = env
    tenant_b, supplier_b, product_b, _ap_b, _inv_b, _cash_b = _setup_tenant(
        "m1iso2", "شركة M1 معزولة", tenant_a._cur,
    )

    orig_a = _post_local_invoice_via_api(
        tenant_a, supplier_a, number="PINV-ISO-A",
        items_data=[{"product": product_a, "name": product_a.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50}],
        receive_on_post=True,
    )
    ret_a = create_purchase_return(
        tenant_a, original_invoice=orig_a, partner=supplier_a, return_date="2026-06-15",
        invoice_number="PRET-ISO-A",
        lines=[{"product": product_a.id, "quantity": 2, "unit_price": 10}],
    )
    post_purchase_return(ret_a, user=tenant_a._owner)

    # أصل ب يحمل أيضاً بنداً بالمنتج نفسه (product_a) للتثبّت من العزل الحقيقي
    orig_b = _post_local_invoice_via_api(
        tenant_b, supplier_b, number="PINV-ISO-B",
        items_data=[{"product": product_b, "name": product_b.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50}],
        receive_on_post=True,
    )
    orig_b_same_prod = PurchaseInvoiceItem.objects.create(
        invoice=orig_b, product=product_a, name=product_a.name_ar,
        quantity=Decimal("5"), received_quantity=Decimal("5"),
        unit_price=Decimal("10"), total_price=Decimal("50"),
    )
    ret_b = create_purchase_return(
        tenant_b, original_invoice=orig_b, partner=supplier_b, return_date="2026-06-15",
        invoice_number="PRET-ISO-B",
        lines=[{"product": product_b.id, "quantity": 2, "unit_price": 10}],
    )
    post_purchase_return(ret_b, user=tenant_b._owner)

    # مرتجع في شركة أ مربوط خطأً بأصل في شركة ب: يُسجَّل استثناءً على فاتورة المرتجع نفسها بلا إشارة لأصل ب
    ret_cross = create_purchase_return(
        tenant_a, original_invoice=None, partner=supplier_a, return_date="2026-06-16",
        invoice_number="PRET-CROSS",
        lines=[{"product": product_a.id, "quantity": 1, "unit_price": 10}],
    )
    post_purchase_return(ret_cross, user=tenant_a._owner)
    PurchaseInvoice.objects.filter(pk=ret_cross.pk).update(original_invoice=orig_b)
    ret_cross_line = ret_cross.items.get()

    _run_backfill(tenant=tenant_a.TenantID)

    # شركة أ أُسندت
    orig_a_line = orig_a.items.get()
    assert orig_a_line.returned_quantity == Decimal("2.0000")
    assert orig_a_line.posted_net_base == Decimal("50.00")

    # شركة ب لم تُمسّ، وأصل ب (بما فيه بند product_a) لم يُمسّ من المرتجع العابر
    orig_b_line = orig_b.items.get(product=product_b)
    orig_b_same_prod.refresh_from_db()
    assert orig_b_line.returned_quantity == Decimal("0")
    assert orig_b_line.received_quantity == Decimal("5.0000")
    assert orig_b_line.posted_net_base is None
    assert orig_b_same_prod.returned_quantity == Decimal("0")
    assert orig_b_same_prod.received_quantity == Decimal("5.0000")
    ret_cross_line.refresh_from_db()
    assert ret_cross_line.return_of_item is None

    # لا صف سجلّ لشركة أ يشير إلى فاتورة ب أو بنودها
    assert not PurchaseReturnBackfill.objects.filter(tenant=tenant_a).filter(
        Q(invoice=orig_b) | Q(item__invoice=orig_b),
    ).exists()

    # ويوجد صف الاستثناء الجديد مرتبطاً بفاتورة المرتجع نفسها
    cross_exc = PurchaseReturnBackfill.objects.get(
        tenant=tenant_a,
        invoice=ret_cross,
        item__isnull=True,
        source_return_item=ret_cross_line,
        field="returned_quantity",
        status="exception",
    )
    assert cross_exc.reason == "الفاتورة الأصلية في شركة أخرى"


# ── 15) fix1: ضريبة البند بوزن vat_percent والجهة الآمنة ───────────────────────

def test_basis_mixed_vat_percent_weights_by_net_times_vat(env):
    from logistics.purchase_return_basis import basis_matches_journal, compute_invoice_line_basis

    tenant, supplier, product, _ap, _inv, _cash = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-VAT-0", name_ar="صنف-معفى-أو-صفر",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("20"),
    )

    # بندان خاضعان بصافيين متساويين (100 لكلٍّ): أحدهما 16% والآخر 0%
    inv_zero = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-VAT-MIX-0",
        items_data=[
            {"product": product, "name": "خاضع 16%", "quantity": 1, "unit_price": 100, "total_price": 100,
             "is_taxable": True, "vat_percent": 16},
            {"product": product2, "name": "خاضع 0%", "quantity": 1, "unit_price": 100, "total_price": 100,
             "is_taxable": True, "vat_percent": 0},
        ],
        tax_amount=Decimal("16.00"),
        receive_on_post=False,
    )
    basis_zero = compute_invoice_line_basis(inv_zero)
    ok_z, reason_z = basis_matches_journal(inv_zero, basis_zero)
    assert ok_z, reason_z
    it16 = inv_zero.items.get(product=product)
    it0 = inv_zero.items.get(product=product2)
    assert basis_zero[it16.id].tax_base == Decimal("16.00")
    assert basis_zero[it0.id].tax_base == Decimal("0.00")

    # بندان خاضعان بصافيين متساويين (100 لكلٍّ): 16% و8% -> ضريبة 16.00 و8.00
    inv_8 = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-VAT-MIX-8",
        items_data=[
            {"product": product, "name": "خاضع 16%", "quantity": 1, "unit_price": 100, "total_price": 100,
             "is_taxable": True, "vat_percent": 16},
            {"product": product2, "name": "خاضع 8%", "quantity": 1, "unit_price": 100, "total_price": 100,
             "is_taxable": True, "vat_percent": 8},
        ],
        tax_amount=Decimal("24.00"),
        receive_on_post=False,
    )
    basis_8 = compute_invoice_line_basis(inv_8)
    ok_8, reason_8 = basis_matches_journal(inv_8, basis_8)
    assert ok_8, reason_8
    it_a = inv_8.items.get(product=product)
    it_b = inv_8.items.get(product=product2)
    assert basis_8[it_a.id].tax_base == Decimal("16.00")
    assert basis_8[it_b.id].tax_base == Decimal("8.00")

    # عند تصفير كل أوزان vat_percent يرجع التوزيع لوزن الصافي وحده
    inv_all_zero_vat = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-VAT-ALL-0",
        items_data=[
            {"product": product, "name": "أ", "quantity": 2, "unit_price": 100, "total_price": 200,
             "is_taxable": True, "vat_percent": 0},
            {"product": product2, "name": "ب", "quantity": 1, "unit_price": 100, "total_price": 100,
             "is_taxable": True, "vat_percent": 0},
        ],
        tax_amount=Decimal("30.00"),
        receive_on_post=False,
    )
    basis_fb = compute_invoice_line_basis(inv_all_zero_vat)
    ok_fb, reason_fb = basis_matches_journal(inv_all_zero_vat, basis_fb)
    assert ok_fb, reason_fb
    fb_a = inv_all_zero_vat.items.get(product=product)
    fb_b = inv_all_zero_vat.items.get(product=product2)
    assert basis_fb[fb_a.id].tax_base == Decimal("20.00")
    assert basis_fb[fb_b.id].tax_base == Decimal("10.00")


def test_basis_incomplete_clearing_map_stays_empty_and_logs_exception(env, monkeypatch):
    from logistics.models import PurchaseReturnBackfill
    from logistics import purchase_return_basis as prb

    tenant, supplier, product, _ap, _inv, _cash = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-CL-2", name_ar="صنف-تصفية-2",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"),
    )
    inv = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-INC-CL",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 1, "unit_price": 100, "total_price": 100},
            {"product": product2, "name": product2.name_ar, "quantity": 1, "unit_price": 100, "total_price": 100},
        ],
        receive_on_post=False,
    )

    orig_fn = prb.goods_clearing_unit_costs

    def _incomplete(invoice, total_clearing):
        full = orig_fn(invoice, total_clearing)
        first_k = next(iter(full))
        return {first_k: full[first_k]}

    monkeypatch.setattr(prb, "goods_clearing_unit_costs", _incomplete)
    res = prb.run_backfill_for_tenant(tenant, dry_run=False)
    assert res.basis_mismatched == 1
    assert res.exceptions_count == 0
    for it in inv.items.all():
        assert it.posted_net_base is None
        assert it.posted_clearing_base is None
    exc = PurchaseReturnBackfill.objects.get(
        tenant=tenant, invoice=inv, item__isnull=True, field="basis", status="exception",
    )
    assert exc.reason == "خريطة التصفية لا تغطي كل البنود"


def test_backfill_basis_deleted_item_blocks_entire_invoice_unit_rollback(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-BAS-DEL", name_ar="صنف-حذف-أساس",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"),
    )
    inv = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-BAS-DEL",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 1, "unit_price": 100, "total_price": 100},
            {"product": product2, "name": product2.name_ar, "quantity": 1, "unit_price": 50, "total_price": 50},
        ],
        receive_on_post=False,
    )
    _run_backfill(tenant=tenant.TenantID)
    run_id = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, status="applied",
    ).values_list("run_id", flat=True).first()
    assert run_id

    it1 = inv.items.get(product=product)
    it2 = inv.items.get(product=product2)
    it1.delete()

    # الصفوف المحذوف هدفها بقيت بـ item=NULL وتوقف تراجع وحدة الفاتورة كلها
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, invoice=inv, item__isnull=True,
    ).count() == 7

    out = _run_backfill(tenant=tenant.TenantID, rollback=run_id)
    assert "تعارض" in out
    it2.refresh_from_db()
    assert it2.posted_net_base == Decimal("50.00")
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, invoice=inv, status="applied",
    ).count() == 14


def test_basis_goods_item_without_product_stays_empty_and_logs_exception(env):
    from logistics.models import PurchaseReturnBackfill
    from logistics.purchase_return_basis import run_backfill_for_tenant

    tenant, supplier, product, _ap, _inv, _cash = env
    inv = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-NO-PROD",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 1, "unit_price": 100, "total_price": 100},
            {"product": None, "name": "بند بضاعة حر بلا منتج", "quantity": 2, "unit_price": 50, "total_price": 100},
        ],
        receive_on_post=False,
    )

    res = run_backfill_for_tenant(tenant, dry_run=False)
    assert res.basis_mismatched == 1
    assert res.exceptions_count == 0

    for it in inv.items.all():
        assert it.posted_account is None
        assert it.posted_net_base is None
        assert it.posted_tax_base is None
        assert it.posted_clearing_base is None

    exc = PurchaseReturnBackfill.objects.get(
        tenant=tenant, invoice=inv, item__isnull=True, field="basis", status="exception",
    )
    assert exc.reason == "بند بضاعة بلا منتج"


def test_backfill_records_survive_item_delete_and_block_unit_rollback(env):
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-DEL-SETNULL",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 3, "unit_price": 10, "total_price": 30},
            {"product": product, "name": product.name_ar, "quantity": 3, "unit_price": 10, "total_price": 30},
        ],
        receive_on_post=True,
    )
    l1, l2 = list(orig.items.order_by("id"))
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-DEL-SETNULL",
        lines=[{"product": product.id, "quantity": 5, "unit_price": 10}],
    )
    post_purchase_return(ret, user=tenant._owner)
    ret_line = ret.items.get()

    _run_backfill(tenant=tenant.TenantID)
    run_id = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, status="applied",
    ).values_list("run_id", flat=True).first()
    assert run_id

    # حذف بند الأصل الأول: يجب أن تبقى صفوف السجلّ بـ item=NULL
    l1_id = l1.id
    l1.delete()
    surviving = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, source_return_item=ret_line,
    )
    assert surviving.count() == 4
    assert surviving.filter(item__isnull=True).count() == 2

    # التراجع يعامل الهدف المحذوف تعارضاً يوقف الوحدة كاملةً فلا يُعكس l2 أيضاً
    out = _run_backfill(tenant=tenant.TenantID, rollback=run_id)
    assert "تعارض" in out
    l2.refresh_from_db()
    assert l2.returned_quantity == Decimal("2.0000")
    assert l2.received_quantity == Decimal("1.0000")
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id=run_id, source_return_item=ret_line, status="applied",
    ).count() == 4
    # الصفوف المعلّقة على البند المحذوف بقيت `applied` (لم يُعلَّم أيّ منها rolled_back)
    assert surviving.filter(item__isnull=True, status="applied").count() == 2
    assert not PurchaseInvoiceItem.objects.filter(pk=l1_id).exists()


def test_backfill_command_unknown_tenant_raises_command_error(env):
    with pytest.raises(CommandError, match="الشركة"):
        call_command("backfill_purchase_returns", tenant=999999)


def test_backfill_command_unknown_rollback_run_id_raises_command_error(env):
    tenant, *_ = env
    with pytest.raises(CommandError, match="run_id|صفوف|التشغيل"):
        call_command("backfill_purchase_returns", tenant=tenant.TenantID, rollback="00000000-0000-0000-0000-000000000000")


# ── 16) fix4: تفاصيل الاستثناءات، المجموعات المسندة، سبب الأساس الفارغ ─────────

def _exception_details_scenario(env):
    """شركة فيها: مرتجع قديم عابر للشركة، ومرتجع على بندين بسعرين (غير حتمي)، وفاتورة أساسها معبّأ جزئياً.

    تعيد `(tenant, expected)` حيث `expected` مجموعة صفوف
    `(kind, invoice_id, invoice_number, return_item_id, product_id, reason)`."""
    tenant, supplier, product, _ap, _inv, _cash = env
    tenant_b, supplier_b, product_b, _ap_b, _inv_b, _cash_b = _setup_tenant(
        "m1det2", "شركة M1 تفاصيل", tenant._cur,
    )
    orig_b = _post_local_invoice_via_api(
        tenant_b, supplier_b, number="PINV-DET-B",
        items_data=[{"product": product_b, "name": product_b.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50}],
        receive_on_post=True,
    )
    ret_cross = create_purchase_return(
        tenant, original_invoice=None, partner=supplier, return_date="2026-06-16",
        invoice_number="PRET-DET-CROSS",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 10}],
    )
    post_purchase_return(ret_cross, user=tenant._owner)
    PurchaseInvoice.objects.filter(pk=ret_cross.pk).update(original_invoice=orig_b)

    orig_multi = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-DET-MULTI",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 3, "unit_price": 10, "total_price": 30},
            {"product": product, "name": product.name_ar, "quantity": 3, "unit_price": 15, "total_price": 45},
        ],
        receive_on_post=True,
    )
    ret_multi = create_purchase_return(
        tenant, original_invoice=orig_multi, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-DET-MULTI",
        lines=[{"product": product.id, "quantity": 2, "unit_price": 10}],
    )
    post_purchase_return(ret_multi, user=tenant._owner)

    inv_partial = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-DET-PART",
        items_data=[
            {"product": product, "name": "أ", "quantity": 2, "unit_price": 10, "total_price": 20},
            {"product": product, "name": "ب", "quantity": 3, "unit_price": 10, "total_price": 30},
        ],
        receive_on_post=False,
    )
    first = inv_partial.items.order_by("id").first()
    PurchaseInvoiceItem.objects.filter(pk=first.pk).update(
        posted_net_base=Decimal("1.00"), posted_tax_base=Decimal("0.00"),
        posted_clearing_base=Decimal("1.00"),
    )

    expected = {
        ("quantities", ret_cross.id, "PRET-DET-CROSS", ret_cross.items.get().id, product.id,
         "الفاتورة الأصلية في شركة أخرى"),
        ("quantities", orig_multi.id, "PINV-DET-MULTI", ret_multi.items.get().id, product.id,
         "أ:تعدد_أسعار"),
        ("basis", orig_multi.id, "PINV-DET-MULTI", None, None, "مرتجع غير مُسند على الفاتورة"),
        ("basis", inv_partial.id, "PINV-DET-PART", None, None, "أساس معبّأ جزئياً"),
    }
    return tenant, expected


def _detail_rows(res):
    return [
        (d.kind, d.invoice_id, d.invoice_number, d.return_item_id, d.product_id, d.reason)
        for d in res.exceptions
    ]


def _expected_detail_line(row) -> str:
    kind, invoice_id, number, rid, pid, reason = row
    if kind == "quantities":
        return f"  استثناء كميات · فاتورة {number} (#{invoice_id}) · بند مرتجع #{rid} · منتج #{pid} · {reason}"
    return f"  استثناء أساس · فاتورة {number} (#{invoice_id}) · {reason}"


def test_backfill_result_and_command_list_exception_details(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, expected = _exception_details_scenario(env)

    r = prb.run_backfill_for_tenant(tenant, dry_run=True)
    rows = _detail_rows(r)
    assert len(rows) == len(set(rows)) == 4
    assert set(rows) == expected
    assert r.exceptions_count == 2
    assert r.basis_mismatched == 2
    assert len(r.exceptions) == r.exceptions_count + r.basis_mismatched

    out = StringIO()
    call_command("backfill_purchase_returns", stdout=out)
    text = out.getvalue()
    for row in expected:
        assert _expected_detail_line(row) in text
    assert PurchaseReturnBackfill.objects.count() == 0


def test_backfill_exception_details_survive_rerun_dedup(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, expected = _exception_details_scenario(env)

    r1 = prb.run_backfill_for_tenant(tenant, dry_run=False)
    assert set(_detail_rows(r1)) == expected
    exc_rows = PurchaseReturnBackfill.objects.filter(tenant=tenant, status="exception").count()
    assert exc_rows == 4

    # المعاينة الثانية: صفوف الاستثناء موجودة فتُتخطّى في pending_logs، والتفاصيل تبقى كاملة
    r2 = prb.run_backfill_for_tenant(tenant, dry_run=True)
    rows2 = _detail_rows(r2)
    assert len(rows2) == 4
    assert set(rows2) == expected
    assert len(r2.exceptions) == r2.exceptions_count + r2.basis_mismatched
    assert PurchaseReturnBackfill.objects.filter(tenant=tenant, status="exception").count() == exc_rows


def test_backfill_groups_assigned_counts_original_invoice_product_groups(env):
    from logistics import purchase_return_basis as prb

    tenant, supplier, product, _ap, _inv, _cash = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-GRP-2", name_ar="صنف-مجموعة-2",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"),
    )
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-GRP",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
            {"product": product2, "name": product2.name_ar, "quantity": 4, "unit_price": 10, "total_price": 40},
        ],
        receive_on_post=True,
    )
    for number, prod, qty in (
        ("PRET-GRP-1", product, 1), ("PRET-GRP-2", product, 2), ("PRET-GRP-3", product2, 1),
    ):
        ret = create_purchase_return(
            tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
            invoice_number=number,
            lines=[{"product": prod.id, "quantity": qty, "unit_price": 10}],
        )
        post_purchase_return(ret, user=tenant._owner)

    r = prb.run_backfill_for_tenant(tenant, dry_run=True)
    assert r.groups_assigned == 2
    assert r.returns_assigned == 3

    out_preview = StringIO()
    call_command("backfill_purchase_returns", tenant=tenant.TenantID, stdout=out_preview)
    assert out_preview.getvalue().count("مجموعات_مسندة=2") == 2  # سطر الشركة والإجمالي

    out_apply = StringIO()
    call_command("backfill_purchase_returns", tenant=tenant.TenantID, apply=True, stdout=out_apply)
    assert out_apply.getvalue().count("مجموعات_مسندة=2") == 2
    assert orig.items.get(product=product).returned_quantity == Decimal("3.0000")
    assert orig.items.get(product=product2).returned_quantity == Decimal("1.0000")


def _negative_inventory_debit_invoice(tenant, supplier):
    """فاتورة مرحّلة ببند مصروف 50 ثم إجماليها 10 ⇒ مدين المخزون −40 ⇒ الترحيل كان سيرفضها."""
    exp_acc = Account.objects.filter(tenant=tenant, account_type="Expense").first()
    if exp_acc is None:
        exp_acc = Account.objects.create(
            tenant=tenant, code="5397", name="مصروف سبب", account_type="Expense", is_active=True,
        )
    inv = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-NEG-REASON",
        items_data=[
            {"product": None, "name": "خدمة", "quantity": 1, "unit_price": 50, "total_price": 50,
             "expense_account": exp_acc},
        ],
        receive_on_post=False,
    )
    # الإجمالي 10 أقلّ من بند المصروف 50 ⇒ مدين المخزون −40 ⇒ الترحيل كان سيرفض الفاتورة
    PurchaseInvoice.objects.filter(pk=inv.pk).update(grand_total=Decimal("10.00"))
    inv.refresh_from_db()
    return inv


def test_basis_empty_reason_is_truthful_for_negative_inventory_debit(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, _product, _ap, _inv, _cash = env
    inv = _negative_inventory_debit_invoice(tenant, supplier)

    reason = "الترحيل كان سيرفض الفاتورة: مدين مخزون سالب"
    res = prb.run_backfill_for_tenant(tenant, dry_run=False)
    assert res.basis_mismatched == 1
    assert _detail_rows(res) == [("basis", inv.id, "PINV-NEG-REASON", None, None, reason)]
    row = PurchaseReturnBackfill.objects.get(
        tenant=tenant, invoice=inv, item__isnull=True, field="basis", status="exception",
    )
    assert row.reason == reason
    assert inv.items.get().posted_net_base is None


def test_backfill_filled_invoice_with_unassigned_return_logs_exception_and_keeps_fields(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    product2 = Product.objects.create(
        tenant=tenant, sku="SKU-FILL-UN", name_ar="صنف-معبّأ-غير-مسند",
        quantity_on_hand=Decimal("50"), avg_cost=Decimal("10"),
    )
    # product حتميّ (بند واحد) يُسند، وproduct2 بسعرين غير حتميّ يبقى مرتجعه غير مُسند
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-FILL-UN",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
            {"product": product2, "name": product2.name_ar, "quantity": 3, "unit_price": 10, "total_price": 30},
            {"product": product2, "name": product2.name_ar, "quantity": 3, "unit_price": 15, "total_price": 45},
        ],
        receive_on_post=True,
    )
    orig.items.update(
        posted_net_base=Decimal("10.00"), posted_tax_base=Decimal("0.00"),
        posted_clearing_base=Decimal("10.00"), returned_net_base=Decimal("0.00"),
        returned_tax_base=Decimal("0.00"), returned_clearing_base=Decimal("0.00"),
    )
    before = {it.id: _basis_fields(it) for it in orig.items.all()}
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-FILL-UN",
        lines=[
            {"product": product.id, "quantity": 1, "unit_price": 10},
            {"product": product2.id, "quantity": 2, "unit_price": 10},
        ],
    )
    post_purchase_return(ret, user=tenant._owner)

    res = prb.run_backfill_for_tenant(tenant, dry_run=False)

    assert {it.id: _basis_fields(it) for it in orig.items.all()} == before
    row = PurchaseReturnBackfill.objects.get(
        tenant=tenant, invoice=orig, field="basis", status="exception",
    )
    assert row.reason == "مرتجع غير مُسند على الفاتورة"
    assert ("basis", orig.id, "PINV-FILL-UN", None, None, "مرتجع غير مُسند على الفاتورة") in _detail_rows(res)
    # لا صفّ أساسٍ مطبَّق على الفاتورة (صفوف الكميات لبند product الحتمي مشروعة)
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, invoice=orig, status="applied", source_return_item__isnull=True,
    ).exists()
    assert orig.items.get(product=product).returned_quantity == Decimal("1.0000")


def test_create_purchase_return_draft_has_ship_goods_on_post_true(env):
    tenant, supplier, product, _ap, _inv, _cash = env
    orig = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-SHIP-DEF",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 5, "unit_price": 10, "total_price": 50},
        ],
        receive_on_post=True,
    )
    ret = create_purchase_return(
        tenant, original_invoice=orig, partner=supplier, return_date="2026-06-15",
        invoice_number="PRET-SHIP-DEF",
        lines=[{"product": product.id, "quantity": 1, "unit_price": 10}],
    )
    assert ret.is_posted is False
    ret.refresh_from_db()
    assert ret.ship_goods_on_post is True


def test_basis_matches_journal_gives_truthful_reason_for_negative_inventory_debit(env):
    from logistics.purchase_return_basis import basis_matches_journal, compute_invoice_line_basis

    tenant, supplier, _product, _ap, _inv, _cash = env
    inv = _negative_inventory_debit_invoice(tenant, supplier)

    assert basis_matches_journal(inv, compute_invoice_line_basis(inv)) == (
        False, "الترحيل كان سيرفض الفاتورة: مدين مخزون سالب",
    )


def test_basis_matches_journal_empty_basis_for_healthy_invoice_gives_fallback_reason(env):
    from logistics.purchase_return_basis import basis_matches_journal, compute_invoice_line_basis

    tenant, supplier, product, _ap, _inv, _cash = env
    inv = _post_local_invoice_via_api(
        tenant, supplier, number="PINV-EMPTY-BASIS",
        items_data=[
            {"product": product, "name": product.name_ar, "quantity": 2, "unit_price": 10, "total_price": 20},
        ],
        receive_on_post=False,
    )
    # الفاتورة سليمة: أساسها المحسوب يطابق القيد، فالفراغ من المُمرِّر لا من الفاتورة
    assert basis_matches_journal(inv, compute_invoice_line_basis(inv)) == (True, "")

    assert basis_matches_journal(inv, {}) == (False, "أساس البنود المُمرَّر فارغ")


def test_run_backfill_defaults_to_preview(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, ret = _orig_with_posted_return(tenant, supplier, product, tag="PYPREV")

    res = prb.run_backfill_for_tenant(tenant)

    # المعاينة تحسب ما كانت ستكتبه ولا تكتبه
    assert res.returns_assigned == 1
    line = orig.items.get()
    assert line.returned_quantity == Decimal("0")
    assert line.received_quantity == Decimal("5.0000")
    assert _basis_fields(line)["net"] is None
    assert _basis_fields(line)["r_net"] is None
    assert ret.items.get().return_of_item is None
    assert not PurchaseReturnBackfill.objects.filter(tenant=tenant, status="applied").exists()


def test_rollback_backfill_defaults_to_preview(env):
    from logistics import purchase_return_basis as prb
    from logistics.models import PurchaseReturnBackfill

    tenant, supplier, product, _ap, _inv, _cash = env
    orig, _ret = _orig_with_posted_return(tenant, supplier, product, tag="PYRBPREV")
    prb.run_backfill_for_tenant(tenant, run_id="py-rb-preview", dry_run=False)
    applied_before = PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id="py-rb-preview", status="applied",
    ).count()
    assert applied_before > 0
    line = orig.items.get()
    assert line.returned_quantity == Decimal("2.0000")
    written = _basis_fields(line)
    assert written["net"] is not None

    res = prb.rollback_backfill_for_tenant(tenant, run_id="py-rb-preview")

    # المعاينة تعدّ ما كانت ستتراجع عنه ولا تكتب
    assert res.rolled_back == applied_before
    line.refresh_from_db()
    assert line.returned_quantity == Decimal("2.0000")
    assert line.received_quantity == Decimal("3.0000")
    assert _basis_fields(line) == written
    assert PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id="py-rb-preview", status="applied",
    ).count() == applied_before
    assert not PurchaseReturnBackfill.objects.filter(
        tenant=tenant, run_id="py-rb-preview", status="rolled_back",
    ).exists()
