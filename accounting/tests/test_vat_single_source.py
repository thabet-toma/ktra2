"""issue #79 — مصدرٌ واحد لضريبة القيمة المضافة: `accounting.services.vat_period_totals`.

ثلاثة عارضين كانوا يحسبون الرقم بأنفسهم فيختلفون: `build_vat_statement`
(يَحفظ، من فواتير المبيعات وحدها)، `VatReportView` (يَعرض، من `JournalLine`
بحسابَي «1105»/«2104» مُرمَّزَين)، و`client_financial_summary` (ملخص الزبون في
`accountant_portal`، من فواتير المبيعات أيضاً). الآن الثلاثة يستدعون
`vat_period_totals` وحدها، والدفتر — لا الفاتورة — مصدر الرقم.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accountant_portal.services import client_financial_summary
from accounting.models import Account, TaxRate
from accounting.services import (
    create_expense_voucher,
    create_fiscal_year,
    unpost_expense_voucher,
    vat_period_totals,
)
from inventory.models import Product, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import receive_purchase_invoice
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings, VatStatement
from sales.services import build_vat_statement, post_sales_invoice, vat_statement_diff_report
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _setup_tenant(username):
    """شركة ببذرتها المعيارية (تحمل «1105»/«2104») + اتجاها ضريبة مشتقّان لا مُرمَّزان."""
    user = User.objects.create_user(username=username, password="x")
    ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True,
    )
    tenant = create_company(f"شركة {username}", user)
    create_fiscal_year(tenant, 2026)
    output_account = Account.objects.get(tenant=tenant, code="2104")
    input_account = Account.objects.get(tenant=tenant, code="1105")
    TaxRate.objects.create(
        tenant=tenant, name="ض.ق.م مخرجات", code="VAT-OUT",
        rate=Decimal("16.00"), tax_account=output_account, direction="sales",
    )
    TaxRate.objects.create(
        tenant=tenant, name="ض.ق.م مدخلات", code="VAT-IN",
        rate=Decimal("16.00"), tax_account=input_account, direction="purchase",
    )
    SalesSettings.objects.create(tenant=tenant, vat_input_account=input_account)
    return tenant, user, ils


# ── الاختبار الأهمّ: العارضون الثلاثة يعطون الرقم نفسه ──────────────────────

def test_three_viewers_agree_on_the_same_number_from_three_document_kinds():
    tenant, user, ils = _setup_tenant("vat-triple-agree")
    cash = Account.objects.get(tenant=tenant, code="1101")
    output_rate = TaxRate.objects.get(tenant=tenant, direction="sales")
    warehouse = Warehouse.objects.get(tenant=tenant, is_default=True)

    # مصدر ١ — فاتورة بيع (ضريبة مخرجات 160.00 على 1000).
    customer = Partner.objects.create(tenant=tenant, name="عميل", partner_type="Customer")
    service = Product.objects.create(
        tenant=tenant, sku="SVC-TRI", name_ar="خدمة اختبار", is_service=True,
        quantity_on_hand=0, avg_cost=0,
    )
    invoice = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="TRI-SALE-1", customer=customer, currency=ils,
        invoice_date="2026-06-10", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=invoice, product=service,
        quantity=Decimal("1"), unit_price=Decimal("1000.00"), tax_rate=output_rate,
    )
    post_sales_invoice(invoice)

    # مصدر ٢ — سند مصروف (ضريبة مدخلات 25.00).
    create_expense_voucher(
        tenant=tenant, date=date(2026, 6, 12), amount=Decimal("225.00"), currency=ils,
        tax_amount=Decimal("25.00"), payment_method="cash",
        expense_account_name="مصروف اختبار", cash_or_bank_account_id=cash.pk, user=user,
    )

    # مصدر ٣ — استلام فاتورة شراء/إيصال استلام (ضريبة مدخلات 80.00 على 500).
    supplier = Partner.objects.create(tenant=tenant, name="مورد", partner_type="Supplier")
    product = Product.objects.create(
        tenant=tenant, sku="GOOD-TRI", name_ar="بضاعة اختبار",
        quantity_on_hand=0, avg_cost=0,
    )
    purchase_invoice = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="TRI-PUR-1", partner=supplier, currency=ils,
        invoice_date="2026-06-14", exchange_rate=Decimal("1"), grand_total=Decimal("0"),
    )
    item = PurchaseInvoiceItem.objects.create(
        invoice=purchase_invoice, product=product, name="بضاعة اختبار",
        quantity=Decimal("5"), unit_price=Decimal("100.00"), total_price=Decimal("500.00"),
        is_taxable=True, vat_percent=Decimal("16.00"),
    )
    receive_purchase_invoice(
        purchase_invoice,
        lines=[{"item_id": item.id, "quantity": Decimal("5"), "warehouse_id": warehouse.id}],
        user=user,
    )

    # المتوقَّع: مخرجات 160.00 · مدخلات 25.00 + 80.00 = 105.00 · صافٍ 55.00.
    ledger = vat_period_totals(tenant.pk, date(2026, 6, 1), date(2026, 6, 30))
    assert ledger["output"]["balance_payable"] == Decimal("160.00")
    assert ledger["input"]["balance"] == Decimal("105.00")
    assert ledger["net_payable"] == Decimal("55.00")

    client = APIClient()
    client.force_authenticate(user=user)
    headers = {"HTTP_X_TENANT_ID": str(tenant.pk)}
    report = client.get(
        "/api/accounting/vat-report/?start_date=2026-06-01&end_date=2026-06-30", **headers,
    )
    assert report.status_code == 200, report.content
    assert Decimal(str(report.data["net_payable"])) == Decimal("55.00")
    assert Decimal(str(report.data["output"]["balance_payable"])) == Decimal("160.00")
    assert Decimal(str(report.data["input"]["balance"])) == Decimal("105.00")

    stmt = build_vat_statement(tenant.pk, date(2026, 6, 1), date(2026, 6, 30), user=user)
    assert stmt.total_sales_vat == Decimal("160.00")
    assert stmt.total_purchase_vat == Decimal("105.00")
    assert stmt.net_vat == Decimal("55.00")

    summary = client_financial_summary(
        tenant=tenant, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
    )
    assert Decimal(summary["output_vat"]) == Decimal("160.00")
    assert Decimal(summary["input_vat"]) == Decimal("105.00")
    assert Decimal(summary["vat_due"]) == Decimal("55.00")


# ── حارس فكّ الترحيل داخل فترة كشف نهائي ─────────────────────────────────────

def test_unpost_is_blocked_inside_a_final_statement_period_and_allowed_outside():
    tenant, user, ils = _setup_tenant("vat-unpost-guard")
    cash = Account.objects.get(tenant=tenant, code="1101")

    inside = create_expense_voucher(
        tenant=tenant, date=date(2026, 6, 15), amount=Decimal("100.00"), currency=ils,
        payment_method="cash", expense_account_name="مصروف داخل الفترة",
        cash_or_bank_account_id=cash.pk, user=user,
    )
    outside = create_expense_voucher(
        tenant=tenant, date=date(2026, 7, 15), amount=Decimal("100.00"), currency=ils,
        payment_method="cash", expense_account_name="مصروف خارج الفترة",
        cash_or_bank_account_id=cash.pk, user=user,
    )
    VatStatement.objects.create(
        tenant=tenant, statement_number="VS-FINAL-GUARD",
        period_from=date(2026, 6, 1), period_to=date(2026, 6, 30),
        status=VatStatement.STATUS_FINAL,
    )

    with pytest.raises(ValidationError):
        unpost_expense_voucher(inside, user=user)

    result = unpost_expense_voucher(outside, user=user)
    assert result["journals_deleted"] == 1


# ── لا أثر رجعي: أرقام الكشف النهائي القائم لا تتغيّر ────────────────────────

def test_final_statement_numbers_are_never_recomputed_after_the_fact():
    tenant, user, ils = _setup_tenant("vat-no-retro")
    stmt = VatStatement.objects.create(
        tenant=tenant, statement_number="VS-FROZEN", period_from=date(2026, 6, 1),
        period_to=date(2026, 6, 30), status=VatStatement.STATUS_FINAL,
        total_sales_vat=Decimal("999.00"), total_purchase_vat=Decimal("111.00"),
        net_vat=Decimal("888.00"),
    )

    # نشاطٌ جديد داخل نفس الفترة بعد تجميد الكشف — رقم الدفتر الطازج يختلف حتماً.
    cash = Account.objects.get(tenant=tenant, code="1101")
    create_expense_voucher(
        tenant=tenant, date=date(2026, 6, 20), amount=Decimal("50.00"), currency=ils,
        tax_amount=Decimal("5.00"), payment_method="cash",
        expense_account_name="مصروف لاحق", cash_or_bank_account_id=cash.pk, user=user,
    )

    fresh = vat_period_totals(tenant.pk, date(2026, 6, 1), date(2026, 6, 30))
    assert fresh["net_payable"] != stmt.net_vat

    stmt.refresh_from_db()
    assert stmt.total_sales_vat == Decimal("999.00")
    assert stmt.total_purchase_vat == Decimal("111.00")
    assert stmt.net_vat == Decimal("888.00")


# ── تقرير الفرق: قراءة فقط ──────────────────────────────────────────────────

def test_diff_report_flags_mismatch_without_writing_a_row():
    tenant, user, ils = _setup_tenant("vat-diff-report")
    VatStatement.objects.create(
        tenant=tenant, statement_number="VS-DIFF", period_from=date(2026, 6, 1),
        period_to=date(2026, 6, 30), status=VatStatement.STATUS_DRAFT,
        total_sales_vat=Decimal("50.00"), total_purchase_vat=Decimal("0.00"),
        net_vat=Decimal("50.00"),
    )
    before = VatStatement.objects.count()

    rows = vat_statement_diff_report(tenant.pk)

    assert VatStatement.objects.count() == before  # لا كتابة
    assert len(rows) == 1
    row = rows[0]
    assert row["stored_net_vat"] == Decimal("50.00")
    assert row["computed_net_vat"] == Decimal("0.00")  # لا نشاطَ في الدفتر بعد
    assert row["matches"] is False
    assert row["difference"] == Decimal("-50.00")


# ── تراجع: شركة بلا SalesSettings.vat_input_account وبلا TaxRate شرائي ──────
# لكنها ترحّل ضريبة مدخلات فعلاً على «1105» عبر مسارٍ حقيقي
# (`logistics.services.receive_purchase_invoice` → `_resolve_vat_input_account`
# — يجد الحساب بالكود ثم بالاسم، بلا قراءة `SalesSettings`/`TaxRate` إطلاقاً).
# الاشتقاق وحده كان يُصفِّرها فيُبالَغ في «الصافي المستحق».

def test_input_vat_posted_via_code_fallback_is_still_seen_without_settings_or_tax_rate():
    user = User.objects.create_user(username="vat-no-settings", password="x")
    ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True,
    )
    tenant = create_company("شركة بلا إعدادات ضريبة", user)
    create_fiscal_year(tenant, 2026)
    warehouse = Warehouse.objects.get(tenant=tenant, is_default=True)

    # لا SalesSettings مُنشأة، ولا TaxRate على الإطلاق لهذه الشركة.
    assert not SalesSettings.objects.filter(tenant=tenant).exists()
    assert not TaxRate.objects.filter(tenant=tenant).exists()

    supplier = Partner.objects.create(tenant=tenant, name="مورد", partner_type="Supplier")
    product = Product.objects.create(
        tenant=tenant, sku="GOOD-NOSET", name_ar="بضاعة اختبار",
        quantity_on_hand=0, avg_cost=0,
    )
    purchase_invoice = PurchaseInvoice.objects.create(
        tenant=tenant, invoice_number="NOSET-PUR-1", partner=supplier, currency=ils,
        invoice_date="2026-06-14", exchange_rate=Decimal("1"), grand_total=Decimal("0"),
    )
    item = PurchaseInvoiceItem.objects.create(
        invoice=purchase_invoice, product=product, name="بضاعة اختبار",
        quantity=Decimal("5"), unit_price=Decimal("100.00"), total_price=Decimal("500.00"),
        is_taxable=True, vat_percent=Decimal("16.00"),
    )
    receive_purchase_invoice(
        purchase_invoice,
        lines=[{"item_id": item.id, "quantity": Decimal("5"), "warehouse_id": warehouse.id}],
        user=user,
    )
    ledger = vat_period_totals(tenant.pk, date(2026, 6, 1), date(2026, 6, 30))
    assert ledger["input"]["balance"] == Decimal("80.00")

    client = APIClient()
    client.force_authenticate(user=user)
    headers = {"HTTP_X_TENANT_ID": str(tenant.pk)}
    report = client.get(
        "/api/accounting/vat-report/?start_date=2026-06-01&end_date=2026-06-30", **headers,
    )
    assert report.status_code == 200, report.content
    assert Decimal(str(report.data["input"]["balance"])) == Decimal("80.00")

    stmt = build_vat_statement(tenant.pk, date(2026, 6, 1), date(2026, 6, 30), user=user)
    assert stmt.total_purchase_vat == Decimal("80.00")

    summary = client_financial_summary(
        tenant=tenant, date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
    )
    assert Decimal(summary["input_vat"]) == Decimal("80.00")
