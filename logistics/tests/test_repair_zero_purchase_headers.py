"""اختبارات أمر إصلاح ترويسة فواتير الشراء الصفرية وإصلاح مصدر import_jarabaa (PRET-ZERO-HEADERS)."""
from __future__ import annotations

import logging
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal
from inventory.models import Product, StockMovement, Warehouse
from logistics.models import (
    PurchaseInvoice,
    PurchaseInvoiceFee,
    PurchaseInvoiceItem,
)
from logistics.purchase_return_basis import (
    basis_matches_journal,
    compute_invoice_line_basis,
)
from logistics.services import (
    annotate_purchase_invoice_payment_summary,
    purchase_invoice_payment_summary,
    receive_purchase_invoice,
)
from partners.models import Partner, PartnerGroup
from sales.models import SupplierPayment, SupplierPaymentAllocation
from sales.services import post_supplier_payment
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _setup_tenant(username: str, company_name: str, ils: Currency):
    owner = User.objects.create_user(username=username, password="x")
    tenant = create_company(company_name, owner)
    create_fiscal_year(tenant, 2026)

    def _acc(code: str, name: str, atype: str) -> Account:
        obj = Account.objects.filter(tenant=tenant, code=code).first()
        if obj is None:
            obj = Account.objects.create(
                tenant=tenant, code=code, name=name, account_type=atype, is_active=True,
            )
        return obj

    ap = _acc("2101", "الدائنون التجاريون", "Liability")
    inv_acc = _acc("1104", "المخزون", "Asset")
    cash = _acc("1101", "النقدية", "Asset")
    vat_acc = _acc("1105", "ضريبة مدخلات", "Asset")
    rev_acc = _acc("4101", "المبيعات", "Revenue")
    cogs_acc = _acc("5101", "تكلفة المبيعات", "Expense")

    supp_group, _ = PartnerGroup.objects.get_or_create(
        tenant=tenant,
        name=f"موردون-{username}",
        group_type="Supplier",
        defaults={"account_payable": ap},
    )
    supplier = Partner.objects.create(
        tenant=tenant,
        name=f"مورد-{username}",
        partner_type="Supplier",
        group=supp_group,
        linked_account=ap,
    )
    wh = Warehouse.objects.filter(tenant=tenant, is_default=True).first()
    if wh is None:
        wh = Warehouse.objects.create(
            tenant=tenant, code=f"MAIN-{username}", name="المستودع الرئيسي",
            is_default=True, is_active=True,
        )
    product = Product.objects.create(
        tenant=tenant,
        sku=f"SKU-{username}-1",
        name_ar=f"صنف-{username}-1",
        quantity_on_hand=Decimal("0"),
        avg_cost=Decimal("0"),
    )
    return {
        "tenant": tenant,
        "owner": owner,
        "ils": ils,
        "ap": ap,
        "inv_acc": inv_acc,
        "cash": cash,
        "vat_acc": vat_acc,
        "rev_acc": rev_acc,
        "cogs_acc": cogs_acc,
        "supp_group": supp_group,
        "supplier": supplier,
        "warehouse": wh,
        "product": product,
    }


@pytest.fixture
def env():
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    return _setup_tenant("pzh1", "شركة الترويسة الصفرية", ils)


def _auto_note(invoice_number: str) -> str:
    return f"دفع تلقائي — فاتورة شراء {invoice_number}"


def _create_zero_header_invoice(
    e: dict,
    *,
    number: str,
    lines: list[tuple[Decimal, Decimal]] | None = None,
    with_payment: bool = True,
    post_invoice: bool = True,
    post_payment: bool = True,
    payment_amount: Decimal | None = None,
    payment_partner: Partner | None = None,
    status_after: str | None = None,
    is_return: bool = False,
    invoice_type: str = PurchaseInvoice.INVOICE_TYPE_LOCAL,
    tax_rate: Decimal = Decimal("0"),
    tax_amount: Decimal = Decimal("0"),
    discount_amount: Decimal = Decimal("0"),
    shipping_cost: Decimal = Decimal("0"),
    exchange_rate: Decimal = Decimal("1"),
    item_taxable: bool = False,
    item_discount: Decimal | None = None,
):
    """يبني فاتورة شراء صفرية الرأس بأقرب مسار لإنتاج import_jarabaa."""
    tenant = e["tenant"]
    supplier = e["supplier"]
    inv = PurchaseInvoice.objects.create(
        tenant=tenant,
        invoice_number=number,
        invoice_type=invoice_type,
        partner=supplier,
        invoice_date="2026-06-01",
        currency=e["ils"],
        exchange_rate=exchange_rate,
        subtotal=Decimal("0.00"),
        discount_amount=discount_amount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        shipping_cost=shipping_cost,
        grand_total=Decimal("0.00"),
        status="draft",
        is_return=is_return,
    )
    items_spec = [(Decimal("2"), Decimal("50.00"))] if lines is None else lines
    recv_lines = []
    gross = Decimal("0.00")
    created_items = []
    for idx, (qty, up) in enumerate(items_spec, start=1):
        lt = (qty * up).quantize(Decimal("0.01"))
        gross += lt
        it = PurchaseInvoiceItem.objects.create(
            invoice=inv,
            product=e["product"],
            name=f"{e['product'].name_ar}-{idx}",
            quantity=qty,
            unit_price=up,
            total_price=lt,
            is_taxable=item_taxable,
            discount_amount=item_discount,
        )
        created_items.append(it)
        recv_lines.append({
            "item_id": it.id,
            "quantity": qty,
            "warehouse_id": e["warehouse"].id,
        })

    if post_invoice and created_items and not is_return:
        receive_purchase_invoice(
            inv, lines=recv_lines, branch=None, user=None, movement_date="2026-06-01",
        )
        inv.refresh_from_db()

    sp = None
    if with_payment:
        amt = payment_amount if payment_amount is not None else gross
        sp = SupplierPayment.objects.create(
            tenant=tenant,
            partner=payment_partner or supplier,
            payment_date="2026-06-01",
            amount=amt,
            currency=e["ils"],
            exchange_rate=Decimal("1"),
            cash_or_bank_account=e["cash"],
            notes=_auto_note(number),
        )
        if post_payment:
            post_supplier_payment(sp, user=None)
            sp.refresh_from_db()
        if status_after is None:
            status_after = "fully_paid"

    if status_after is not None:
        PurchaseInvoice.objects.filter(pk=inv.pk).update(status=status_after)
        inv.refresh_from_db()

    return inv, sp, gross


def _run_repair(**kwargs) -> str:
    out = StringIO()
    call_command("repair_zero_purchase_headers", stdout=out, **kwargs)
    return out.getvalue()


# ── (1) معاينة بلا --apply ────────────────────────────────────────────────────

def test_preview_does_not_write_and_counts_eligible(env):
    inv, sp, gross = _create_zero_header_invoice(
        env, number="PO-PREV-1", lines=[(Decimal("3"), Decimal("40.00"))], with_payment=True,
    )
    assert gross == Decimal("120.00")

    output = _run_repair()

    inv.refresh_from_db()
    sp.refresh_from_db()
    assert inv.subtotal == Decimal("0.00")
    assert inv.grand_total == Decimal("0.00")
    assert inv.tax_amount == Decimal("0.00")
    assert sp.purchase_invoice_id is None
    assert "DRY-RUN" in output
    assert "مؤهّلة" in output
    assert "الإجمالي=1 (1 مع سند / 0 بلا سند)" in output
    assert "120.00" in output
    assert "تخطّي" not in output


# ── (2) --apply مع سند مطابق ─────────────────────────────────────────────────

def test_apply_repairs_header_links_payment_and_preserves_ledger(env, caplog):
    inv, sp, gross = _create_zero_header_invoice(
        env,
        number="PO-APP-1",
        lines=[(Decimal("2"), Decimal("50.00")), (Decimal("1"), Decimal("35.00"))],
        with_payment=True,
    )
    assert gross == Decimal("135.00")
    journals_before = JournalHeader.objects.count()
    movements_before = StockMovement.objects.count()
    status_before = inv.status
    receipt_status_before = inv.receipt_status

    with caplog.at_level(logging.INFO):
        output = _run_repair(apply=True)

    inv.refresh_from_db()
    sp.refresh_from_db()

    assert "APPLIED" in output
    assert inv.subtotal == Decimal("135.00")
    assert inv.grand_total == Decimal("135.00")
    assert inv.tax_amount == Decimal("0.00")
    assert sp.purchase_invoice_id == inv.pk
    assert inv.status == status_before == "fully_paid"
    assert inv.receipt_status == receipt_status_before == PurchaseInvoice.RECEIPT_FULL
    assert JournalHeader.objects.count() == journals_before
    assert StockMovement.objects.count() == movements_before

    summary = purchase_invoice_payment_summary(inv)
    assert summary["payment_status"] == "paid"
    assert summary["remaining_balance"] == Decimal("0.00")
    assert summary["amount_paid"] == Decimal("135.00")

    annotated = annotate_purchase_invoice_payment_summary(
        PurchaseInvoice.objects.filter(pk=inv.pk)
    ).get()
    assert annotated.list_payment_status == "paid"
    assert annotated.list_remaining_balance == Decimal("0.00")

    matched, reason = basis_matches_journal(inv, compute_invoice_line_basis(inv))
    assert matched is True, reason

    # logger.info سجّل معرّف الفاتورة ومعرّف السند
    assert any(
        f"invoice_id={inv.pk}" in rec.getMessage()
        and f"payment_id={sp.pk}" in rec.getMessage()
        for rec in caplog.records
        if rec.levelno == logging.INFO
    )


# ── (3) فاتورة صفرية بلا سند (حالة المسودات الأربع) ──────────────────────────

def test_apply_zero_header_without_payment_becomes_unpaid(env):
    inv, sp, gross = _create_zero_header_invoice(
        env, number="PO-NOPAY-1", lines=[(Decimal("4"), Decimal("25.00"))], with_payment=False,
    )
    assert sp is None
    assert gross == Decimal("100.00")
    assert inv.status == "draft"

    _run_repair(apply=True)

    inv.refresh_from_db()
    assert inv.subtotal == Decimal("100.00")
    assert inv.grand_total == Decimal("100.00")
    assert inv.tax_amount == Decimal("0.00")
    assert inv.status == "draft"

    summary = purchase_invoice_payment_summary(inv)
    assert summary["payment_status"] == "unpaid"
    assert summary["remaining_balance"] == Decimal("100.00")
    matched, reason = basis_matches_journal(inv, compute_invoice_line_basis(inv))
    assert matched is True, reason


# ── (4) تخطٍّ بسببٍ مسمّى لكل حالة ───────────────────────────────────────────

def test_skip_journal_debit_mismatch(env):
    inv, sp, _gross = _create_zero_header_invoice(env, number="PO-JDEBIT-1", with_payment=True)
    # نغيّر مدين المخزون في القيد لنكسر التطابق
    JournalLine.objects.filter(journal=inv.journal, debit__gt=0).update(
        debit=Decimal("90.00"), base_debit=Decimal("90.00"),
    )
    output = _run_repair(apply=True)
    inv.refresh_from_db()
    sp.refresh_from_db()
    assert inv.grand_total == Decimal("0.00")
    assert sp.purchase_invoice_id is None
    assert "تخطّي [قيد لا يطابق البنود]: عدد=1" in output


def test_skip_journal_with_vat_input_debit(env):
    inv, sp, _gross = _create_zero_header_invoice(env, number="PO-JVAT-1", with_payment=True)
    JournalLine.objects.create(
        tenant=env["tenant"],
        journal=inv.journal,
        account=env["vat_acc"],
        debit=Decimal("16.00"),
        credit=Decimal("0.00"),
        base_debit=Decimal("16.00"),
        base_credit=Decimal("0.00"),
    )
    output = _run_repair(apply=True)
    inv.refresh_from_db()
    sp.refresh_from_db()
    assert inv.grand_total == Decimal("0.00")
    assert sp.purchase_invoice_id is None
    assert "تخطّي [قيد لا يطابق البنود]: عدد=1" in output


def test_skip_journal_wrong_supplier_ap_credit(env):
    inv, sp, _gross = _create_zero_header_invoice(env, number="PO-JAP-1", with_payment=True)
    other_supplier = Partner.objects.create(
        tenant=env["tenant"], name="مورد آخر للقيد", partner_type="Supplier", linked_account=env["ap"],
    )
    JournalLine.objects.filter(journal=inv.journal, credit__gt=0).update(partner=other_supplier)
    output = _run_repair(apply=True)
    inv.refresh_from_db()
    sp.refresh_from_db()
    assert inv.grand_total == Decimal("0.00")
    assert sp.purchase_invoice_id is None
    assert "تخطّي [قيد لا يطابق البنود]: عدد=1" in output


@pytest.mark.parametrize(
    ("case_name", "expected_reason"),
    [
        ("tax_rate", "ضريبة في الترويسة (tax_rate/tax_amount)"),
        ("tax_amount", "ضريبة في الترويسة (tax_rate/tax_amount)"),
        ("discount", "خصم على الترويسة (discount_amount)"),
        ("item_discount", "بند بخصم (discount_amount/discount_percent)"),
        ("shipping", "تكلفة شحن (shipping_cost)"),
        ("fee", "توجد رسوم على الفاتورة"),
        ("item_taxable", "بند خاضع للضريبة (is_taxable)"),
        ("is_return", "مرتجع (is_return)"),
        ("not_posted", "غير مرحّلة"),
        ("no_items", "بلا بنود"),
        ("international", "فاتورة دولية"),
        ("exchange_rate", "سعر صرف غير 1 (exchange_rate)"),
    ],
)
def test_skip_ineligible_invoice_with_named_reason(env, case_name, expected_reason):
    if case_name == "tax_rate":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-TR", tax_rate=Decimal("16.0000"), with_payment=False,
        )
    elif case_name == "tax_amount":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-TA", tax_amount=Decimal("16.00"), with_payment=False,
        )
    elif case_name == "discount":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-DISC", discount_amount=Decimal("5.00"), with_payment=False,
        )
    elif case_name == "item_discount":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-IDISC", item_discount=Decimal("5.00"), with_payment=False,
        )
    elif case_name == "shipping":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-SHIP", shipping_cost=Decimal("15.00"), with_payment=False,
        )
    elif case_name == "fee":
        inv, sp, _ = _create_zero_header_invoice(env, number="PO-SK-FEE", with_payment=False)
        PurchaseInvoiceFee.objects.create(
            tenant=env["tenant"],
            invoice=inv,
            expense_account=env["cogs_acc"],
            description="رسوم شحن",
            amount=Decimal("20.00"),
        )
    elif case_name == "item_taxable":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-ITAX", item_taxable=True, with_payment=False,
        )
    elif case_name == "is_return":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PRET-SK", is_return=True, post_invoice=False, with_payment=False,
        )
        jh = post_journal(
            tenant_id=env["tenant"].TenantID,
            transaction_date="2026-06-01",
            reference_type="PURCHASE_RETURN",
            reference_id=inv.pk,
            description="مرتجع",
            lines_data=[
                {"account": env["ap"].id, "partner": env["supplier"].id, "debit": Decimal("100.00"), "credit": Decimal("0")},
                {"account": env["inv_acc"].id, "partner": None, "debit": Decimal("0"), "credit": Decimal("100.00")},
            ],
        )
        PurchaseInvoice.objects.filter(pk=inv.pk).update(is_posted=True, journal=jh)
    elif case_name == "not_posted":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-NP", post_invoice=False, with_payment=False,
        )
    elif case_name == "no_items":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-NI", lines=[], post_invoice=False, with_payment=False,
        )
        jh = post_journal(
            tenant_id=env["tenant"].TenantID,
            transaction_date="2026-06-01",
            reference_type="PURCHASE_INVOICE",
            reference_id=inv.pk,
            description="بلا بنود",
            lines_data=[
                {"account": env["inv_acc"].id, "partner": None, "debit": Decimal("10.00"), "credit": Decimal("0")},
                {"account": env["ap"].id, "partner": env["supplier"].id, "debit": Decimal("0"), "credit": Decimal("10.00")},
            ],
        )
        PurchaseInvoice.objects.filter(pk=inv.pk).update(is_posted=True, journal=jh)
    elif case_name == "international":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-INTL", invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            post_invoice=False, with_payment=False,
        )
        PurchaseInvoice.objects.filter(pk=inv.pk).update(is_posted=True)
    elif case_name == "exchange_rate":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-SK-FX", exchange_rate=Decimal("3.700000"), with_payment=False,
        )

    output = _run_repair(apply=True)
    inv.refresh_from_db()
    assert inv.subtotal == Decimal("0.00")
    assert inv.grand_total == Decimal("0.00")
    assert f"تخطّي [{expected_reason}]: عدد=1" in output
    assert "الإجمالي=0 (0 مع سند / 0 بلا سند)" in output


@pytest.mark.parametrize(
    ("pay_case", "expected_reason"),
    [
        ("diff_amount", "سند تلقائي بمبلغ مختلف"),
        ("diff_partner", "سند تلقائي لمورد مختلف"),
        ("already_linked", "سند تلقائي مربوط مسبقاً"),
        ("auto_settled_linked", "سند تلقائي مربوط مسبقاً"),
        ("allocated", "سند تلقائي موزَّع"),
        ("not_posted", "سند تلقائي غير مرحّل"),
        ("duplicate", "سند تلقائي مكرّر"),
    ],
)
def test_skip_invoice_completely_when_auto_payment_mismatched(env, pay_case, expected_reason):
    other_supplier = Partner.objects.create(
        tenant=env["tenant"], name="مورد-مختلف", partner_type="Supplier", linked_account=env["ap"],
    )
    other_inv, _, _ = _create_zero_header_invoice(
        env, number="PO-OTHER-REF", with_payment=False,
    )
    PurchaseInvoice.objects.filter(pk=other_inv.pk).update(grand_total=Decimal("100.00"), subtotal=Decimal("100.00"))

    if pay_case == "diff_amount":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-P-AMT", with_payment=True, payment_amount=Decimal("90.00"),
        )
    elif pay_case == "diff_partner":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-P-PRT", with_payment=True, payment_partner=other_supplier,
        )
    elif pay_case == "already_linked":
        inv, sp, _ = _create_zero_header_invoice(env, number="PO-P-LNK", with_payment=True)
        SupplierPayment.objects.filter(pk=sp.pk).update(purchase_invoice=other_inv)
    elif pay_case == "auto_settled_linked":
        inv, sp, _ = _create_zero_header_invoice(env, number="PO-P-AUT", with_payment=True)
        SupplierPayment.objects.filter(pk=sp.pk).update(auto_settled_invoice=other_inv)
    elif pay_case == "allocated":
        inv, sp, _ = _create_zero_header_invoice(env, number="PO-P-ALC", with_payment=True)
        SupplierPaymentAllocation.objects.create(
            tenant=env["tenant"], payment=sp, invoice=other_inv, amount=Decimal("50.00"),
        )
    elif pay_case == "not_posted":
        inv, sp, _ = _create_zero_header_invoice(
            env, number="PO-P-NP", with_payment=True, post_payment=False,
        )
    elif pay_case == "duplicate":
        inv, sp, _ = _create_zero_header_invoice(env, number="PO-P-DUP", with_payment=True)
        sp2 = SupplierPayment.objects.create(
            tenant=env["tenant"],
            partner=env["supplier"],
            payment_date="2026-06-01",
            amount=Decimal("100.00"),
            currency=env["ils"],
            exchange_rate=Decimal("1"),
            cash_or_bank_account=env["cash"],
            notes=_auto_note("PO-P-DUP"),
        )
        post_supplier_payment(sp2, user=None)

    output = _run_repair(apply=True)

    # الفاتورة لم تُمسّ أبداً (لا ترويسة ولا ربط)
    inv.refresh_from_db()
    sp.refresh_from_db()
    assert inv.subtotal == Decimal("0.00")
    assert inv.grand_total == Decimal("0.00")
    if pay_case not in ("already_linked",):
        assert sp.purchase_invoice_id is None
    else:
        assert sp.purchase_invoice_id == other_inv.pk
    assert f"تخطّي [{expected_reason}]: عدد=1" in output
    assert "الإجمالي=0 (0 مع سند / 0 بلا سند)" in output


# ── (5) العزل بـ --tenant والـ idempotency ─────────────────────────────────────

def test_tenant_isolation_and_idempotency(env):
    env_b = _setup_tenant("pzh2", "شركة ثانية", env["ils"])

    inv_a, sp_a, gross_a = _create_zero_header_invoice(
        env, number="PO-TA-1", lines=[(Decimal("2"), Decimal("75.00"))], with_payment=True,
    )
    inv_b, sp_b, gross_b = _create_zero_header_invoice(
        env_b, number="PO-TB-1", lines=[(Decimal("3"), Decimal("60.00"))], with_payment=True,
    )

    out1 = _run_repair(tenant=env["tenant"].TenantID, apply=True)
    inv_a.refresh_from_db()
    sp_a.refresh_from_db()
    inv_b.refresh_from_db()
    sp_b.refresh_from_db()

    assert inv_a.subtotal == gross_a == Decimal("150.00")
    assert inv_a.grand_total == gross_a == Decimal("150.00")
    assert sp_a.purchase_invoice_id == inv_a.pk
    # الشركة الأخرى لم تُمسّ
    assert inv_b.subtotal == Decimal("0.00")
    assert inv_b.grand_total == Decimal("0.00")
    assert sp_b.purchase_invoice_id is None
    assert "150.00" in out1

    # التشغيل الثاني idempotent: صفر مؤهّلة، ولا يلمس شيئاً
    out2 = _run_repair(tenant=env["tenant"].TenantID, apply=True)
    inv_a.refresh_from_db()
    sp_a.refresh_from_db()
    inv_b.refresh_from_db()
    assert inv_a.grand_total == Decimal("150.00")
    assert sp_a.purchase_invoice_id == inv_a.pk
    assert inv_b.grand_total == Decimal("0.00")
    assert "الإجمالي=0 (0 مع سند / 0 بلا سند)" in out2


def test_command_rejects_conflicting_flags_and_unknown_tenant(env):
    with pytest.raises(CommandError, match="متعارضان"):
        _run_repair(apply=True, dry_run=True)
    with pytest.raises(CommandError, match="غير موجودة"):
        _run_repair(tenant=999999)


# ── (6) إصلاح المصدر import_jarabaa._stage_purchases ─────────────────────────

def test_import_jarabaa_stage_purchases_writes_totals_and_links_payment(env, tmp_path):
    from accounting.management.commands.import_jarabaa import Command as JarabaaCommand

    (tmp_path / "Purchase_orders.csv").write_text(
        "PurchaseOrderNo;SupplierNo;SupplierBusinessName;Date;PaymentStatus;Notes\n"
        f"1001;1;{env['supplier'].name};2026-06-01;Paid;فاتورة مدفوعة\n"
        f"1002;1;{env['supplier'].name};2026-06-02;Unpaid;فاتورة آجلة\n",
        encoding="utf-8",
    )
    (tmp_path / "Purchase_order_items.csv").write_text(
        "no;item;quantity;unit_price\n"
        f"1001;{env['product'].name_ar};2;50.00\n"
        f"1001;{env['product'].name_ar};1;30.00\n"
        f"1002;{env['product'].name_ar};3;20.00\n",
        encoding="utf-8",
    )

    cmd = JarabaaCommand(stdout=StringIO())
    cmd.csv_dir = tmp_path
    cmd.limit = 0
    cmd.tenant = env["tenant"]
    cmd.tid = env["tenant"].TenantID
    cmd.summary = {}
    cmd.ils = env["ils"]
    cmd.acc = {
        "1101": env["cash"],
        "1104": env["inv_acc"],
        "2101": env["ap"],
        "4101": env["rev_acc"],
        "5101": env["cogs_acc"],
    }
    cmd.warehouse = env["warehouse"]
    cmd.supp_group = env["supp_group"]
    cmd.supp_by_name = {env["supplier"].name: env["supplier"]}
    cmd.supp_by_num = {1: env["supplier"]}
    cmd.default_supplier = env["supplier"]
    cmd._cat_cache = {}
    cmd.prod_by_name = {env["product"].name_ar: env["product"]}
    cmd._auto_seq = 0

    cmd._stage_purchases()

    inv_paid = PurchaseInvoice.objects.get(tenant=env["tenant"], invoice_number="PO-1001")
    inv_unpaid = PurchaseInvoice.objects.get(tenant=env["tenant"], invoice_number="PO-1002")

    assert inv_paid.is_posted is True
    assert inv_paid.subtotal == Decimal("130.00")
    assert inv_paid.grand_total == Decimal("130.00")
    assert inv_paid.tax_amount == Decimal("0.00")

    sp = SupplierPayment.objects.get(
        tenant=env["tenant"], notes="دفع تلقائي — فاتورة شراء PO-1001",
    )
    assert sp.is_posted is True
    assert sp.purchase_invoice_id == inv_paid.pk
    assert purchase_invoice_payment_summary(inv_paid)["payment_status"] == "paid"
    assert purchase_invoice_payment_summary(inv_paid)["remaining_balance"] == Decimal("0.00")

    assert inv_unpaid.is_posted is True
    assert inv_unpaid.subtotal == Decimal("60.00")
    assert inv_unpaid.grand_total == Decimal("60.00")
    assert inv_unpaid.tax_amount == Decimal("0.00")
    assert not SupplierPayment.objects.filter(
        tenant=env["tenant"], notes="دفع تلقائي — فاتورة شراء PO-1002",
    ).exists()
    assert purchase_invoice_payment_summary(inv_unpaid)["payment_status"] == "unpaid"
    assert purchase_invoice_payment_summary(inv_unpaid)["remaining_balance"] == Decimal("60.00")
