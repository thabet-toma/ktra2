"""A2-1 — «اعتماد نهائي» لكشف ض.ق.م: قفلٌ ضريبيٌّ حقيقي (نمط Tax Lock Date في Odoo).

قبل هذا: `assert_no_final_vat_statement` موجودٌ ويحرس فكّ الترحيل، لكن لا كود
إنتاجٍ يضع `VatStatement.status='final'` أصلاً — فالحارس لا يُطلق أبداً — ولا
شيء يمنع **ترحيل** مستندٍ جديد مؤرَّخ داخل فترةٍ مُقدَّمة. قرار المالك: الاعتماد
النهائي يمنع الترحيل وفكّه معاً داخل فترته، والمخرج الوحيد «إعادة فتح» للمدير.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounting.models import Account, AccountingAuditLog, JournalHeader, JournalLine, TaxRate
from accounting.services import (
    create_expense_voucher,
    create_fiscal_year,
    post_journal,
    post_journal_entry,
    unpost_expense_voucher,
)
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings, VatStatement
from sales.services import finalize_vat_statement, post_sales_invoice, reopen_vat_statement
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db

JUNE = (date(2026, 6, 1), date(2026, 6, 30))


def _setup_tenant(username):
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
    SalesSettings.objects.create(tenant=tenant, vat_input_account=input_account)
    return tenant, user, ils


def _expense(tenant, user, ils, when, tax="0"):
    cash = Account.objects.get(tenant=tenant, code="1101")
    return create_expense_voucher(
        tenant=tenant, date=when, amount=Decimal("116.00"), currency=ils,
        tax_amount=Decimal(tax), payment_method="cash",
        expense_account_name="مصروف قفل ضريبي", cash_or_bank_account_id=cash.pk, user=user,
    )


def _simple_journal(tenant, when, ref_id):
    cash = Account.objects.get(tenant=tenant, code="1101")
    capital = Account.objects.filter(tenant=tenant, account_type="Revenue", is_active=True).first()
    return post_journal(
        tenant_id=tenant.pk, transaction_date=when, reference_type="TEST_VAT_LOCK",
        reference_id=ref_id, description="قيد اختبار القفل",
        lines_data=[
            {"account": cash.id, "debit": Decimal("10"), "credit": Decimal("0")},
            {"account": capital.id, "debit": Decimal("0"), "credit": Decimal("10")},
        ],
    )


def _draft_sales_invoice(tenant, ils, number, when):
    customer = Partner.objects.create(tenant=tenant, name=f"عميل {number}", partner_type="Customer")
    service = Product.objects.create(
        tenant=tenant, sku=f"SVC-{number}", name_ar="خدمة", is_service=True,
        quantity_on_hand=0, avg_cost=0,
    )
    invoice = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=ils,
        invoice_date=when, invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=invoice, product=service, quantity=Decimal("1"),
        unit_price=Decimal("100.00"),
        tax_rate=TaxRate.objects.get(tenant=tenant, direction="sales"),
    )
    return invoice


# ── الخدمة: الاعتماد يحفظ الأرقام من الدفتر ويضع `final` ─────────────────────

def test_finalize_by_period_creates_a_final_statement_from_the_ledger():
    tenant, user, ils = _setup_tenant("vat-lock-finalize")
    _expense(tenant, user, ils, date(2026, 6, 10), tax="16.00")

    stmt = finalize_vat_statement(tenant.pk, period_from=JUNE[0], period_to=JUNE[1], user=user)

    assert stmt.status == VatStatement.STATUS_FINAL
    assert stmt.total_purchase_vat == Decimal("16.00")
    assert stmt.net_vat == Decimal("-16.00")
    assert AccountingAuditLog.objects.filter(
        tenant=tenant, model_name="VatStatement", object_id=stmt.pk,
        change_details__icontains="final",
    ).exists()


def test_finalizing_an_existing_draft_refreshes_its_numbers_before_locking():
    tenant, user, ils = _setup_tenant("vat-lock-refresh")
    draft = VatStatement.objects.create(
        tenant=tenant, statement_number="VS-STALE", period_from=JUNE[0], period_to=JUNE[1],
        total_sales_vat=Decimal("999.00"), net_vat=Decimal("999.00"),
    )
    _expense(tenant, user, ils, date(2026, 6, 12), tax="16.00")

    stmt = finalize_vat_statement(tenant.pk, statement_id=draft.pk, user=user)

    assert stmt.pk == draft.pk
    assert stmt.status == VatStatement.STATUS_FINAL
    assert stmt.total_sales_vat == Decimal("0.00")
    assert stmt.net_vat == Decimal("-16.00")


def test_finalizing_an_already_final_statement_is_refused():
    tenant, user, _ils = _setup_tenant("vat-lock-twice")
    stmt = finalize_vat_statement(tenant.pk, period_from=JUNE[0], period_to=JUNE[1], user=user)
    with pytest.raises(ValidationError):
        finalize_vat_statement(tenant.pk, statement_id=stmt.pk, user=user)


# ── الحارس: الترحيل داخل الفترة مرفوض، وخارجها مقبول ─────────────────────────

def test_posting_a_journal_inside_a_final_period_is_refused_and_outside_passes():
    tenant, user, _ils = _setup_tenant("vat-lock-journal")
    stmt = finalize_vat_statement(tenant.pk, period_from=JUNE[0], period_to=JUNE[1], user=user)

    with pytest.raises(ValidationError) as exc:
        _simple_journal(tenant, date(2026, 6, 15), 1)
    assert stmt.statement_number in str(exc.value)
    assert "كشف ضريبة نهائي" in str(exc.value)
    assert not JournalHeader.objects.filter(tenant=tenant, reference_type="TEST_VAT_LOCK").exists()

    assert _simple_journal(tenant, date(2026, 7, 1), 2).is_posted


def test_posting_a_sales_invoice_inside_a_final_period_is_refused():
    tenant, user, ils = _setup_tenant("vat-lock-sale")
    finalize_vat_statement(tenant.pk, period_from=JUNE[0], period_to=JUNE[1], user=user)

    inside = _draft_sales_invoice(tenant, ils, "LOCK-IN", "2026-06-20")
    with pytest.raises(ValidationError):
        post_sales_invoice(inside)
    inside.refresh_from_db()
    assert inside.status != SalesInvoice.STATUS_POSTED

    outside = _draft_sales_invoice(tenant, ils, "LOCK-OUT", "2026-07-02")
    post_sales_invoice(outside)
    outside.refresh_from_db()
    assert outside.status == SalesInvoice.STATUS_POSTED


def test_posting_a_manual_draft_journal_inside_a_final_period_is_refused():
    """`post_journal_entry` (زرّ «ترحيل» على قيدٍ يدويّ مسودة) مسارٌ ثانٍ يفرض الفترة."""
    tenant, user, _ils = _setup_tenant("vat-lock-manual")
    cash = Account.objects.get(tenant=tenant, code="1101")
    revenue = Account.objects.filter(tenant=tenant, account_type="Revenue", is_active=True).first()
    header = JournalHeader.objects.create(
        tenant=tenant, transaction_date=date(2026, 6, 5), description="يدوي", is_posted=False,
    )
    JournalLine.objects.create(tenant=tenant, journal=header, account=cash, debit=5, credit=0)
    JournalLine.objects.create(tenant=tenant, journal=header, account=revenue, debit=0, credit=5)
    finalize_vat_statement(tenant.pk, period_from=JUNE[0], period_to=JUNE[1], user=user)

    with pytest.raises(ValidationError):
        post_journal_entry(header.pk, user=user)
    header.refresh_from_db()
    assert header.is_posted is False


def test_unposting_inside_a_final_period_is_refused():
    tenant, user, ils = _setup_tenant("vat-lock-unpost")
    voucher = _expense(tenant, user, ils, date(2026, 6, 8))
    finalize_vat_statement(tenant.pk, period_from=JUNE[0], period_to=JUNE[1], user=user)

    with pytest.raises(ValidationError):
        unpost_expense_voucher(voucher, user=user)
    voucher.refresh_from_db()
    assert voucher.is_posted is True


def test_reopen_lifts_the_lock_and_is_audit_logged():
    tenant, user, _ils = _setup_tenant("vat-lock-reopen")
    stmt = finalize_vat_statement(tenant.pk, period_from=JUNE[0], period_to=JUNE[1], user=user)

    with pytest.raises(ValidationError):
        reopen_vat_statement(stmt, user=user, reason="   ")

    reopened = reopen_vat_statement(stmt, user=user, reason="إقرار معدَّل لفاتورة مورّد متأخرة")
    assert reopened.status == VatStatement.STATUS_DRAFT
    assert AccountingAuditLog.objects.filter(
        tenant=tenant, model_name="VatStatement", object_id=stmt.pk,
        change_details__contains="إقرار معدَّل",
    ).exists()
    assert _simple_journal(tenant, date(2026, 6, 15), 3).is_posted


def test_another_tenants_final_statement_does_not_lock_this_tenant():
    tenant_a, user_a, _ = _setup_tenant("vat-lock-tenant-a")
    tenant_b, _user_b, _ = _setup_tenant("vat-lock-tenant-b")
    finalize_vat_statement(tenant_a.pk, period_from=JUNE[0], period_to=JUNE[1], user=user_a)

    assert _simple_journal(tenant_b, date(2026, 6, 15), 4).is_posted


# ── الواجهة البرمجية: القائمة، الاعتماد، وإعادة الفتح للمدير وحده ──────────────

def _client(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    return client, {"HTTP_X_TENANT_ID": str(tenant.pk)}


def test_api_lists_finalizes_and_manager_reopens():
    tenant, owner, _ils = _setup_tenant("vat-lock-api")
    client, h = _client(owner, tenant)

    res = client.post("/api/accounting/vat-statements/finalize/", {
        "period_from": "2026-06-01", "period_to": "2026-06-30",
    }, format="json", **h)
    assert res.status_code == 200, res.content
    assert res.data["status"] == "final"
    stmt_id = res.data["id"]

    res = client.get("/api/accounting/vat-statements/", **h)
    assert res.status_code == 200, res.content
    assert [row["id"] for row in res.data] == [stmt_id]
    assert res.data[0]["status"] == "final"

    res = client.post(f"/api/accounting/vat-statements/{stmt_id}/reopen/", {}, format="json", **h)
    assert res.status_code == 400, res.content  # السبب إلزامي

    res = client.post(f"/api/accounting/vat-statements/{stmt_id}/reopen/", {
        "reason": "تصحيح",
    }, format="json", **h)
    assert res.status_code == 200, res.content
    assert res.data["status"] == "draft"

    res = client.post(f"/api/accounting/vat-statements/{stmt_id}/finalize/", {}, format="json", **h)
    assert res.status_code == 200, res.content
    assert res.data["status"] == "final"


def test_api_non_manager_cannot_reopen_and_sales_cannot_finalize():
    tenant, owner, _ils = _setup_tenant("vat-lock-roles")
    accountant = User.objects.create_user(username="vat-lock-accountant", password="x")
    seller = User.objects.create_user(username="vat-lock-seller", password="x")
    UserCompanyMembership.objects.create(user=accountant, tenant=tenant, role="accountant")
    UserCompanyMembership.objects.create(user=seller, tenant=tenant, role="sales")

    client, h = _client(seller, tenant)
    res = client.post("/api/accounting/vat-statements/finalize/", {
        "period_from": "2026-06-01", "period_to": "2026-06-30",
    }, format="json", **h)
    assert res.status_code == 403, res.content

    client, h = _client(accountant, tenant)
    res = client.post("/api/accounting/vat-statements/finalize/", {
        "period_from": "2026-06-01", "period_to": "2026-06-30",
    }, format="json", **h)
    assert res.status_code == 200, res.content
    stmt_id = res.data["id"]

    res = client.post(f"/api/accounting/vat-statements/{stmt_id}/reopen/", {
        "reason": "محاولة محاسب",
    }, format="json", **h)
    assert res.status_code == 403, res.content
    assert VatStatement.objects.get(pk=stmt_id).status == VatStatement.STATUS_FINAL


def test_api_is_tenant_isolated():
    tenant_a, owner_a, _ = _setup_tenant("vat-lock-iso-a")
    tenant_b, owner_b, _ = _setup_tenant("vat-lock-iso-b")
    stmt_a = finalize_vat_statement(tenant_a.pk, period_from=JUNE[0], period_to=JUNE[1], user=owner_a)

    client, h = _client(owner_b, tenant_b)
    res = client.get("/api/accounting/vat-statements/", **h)
    assert res.status_code == 200
    assert res.data == []
    res = client.post(f"/api/accounting/vat-statements/{stmt_a.pk}/reopen/", {
        "reason": "تسلّل",
    }, format="json", **h)
    assert res.status_code == 404, res.content
    res = client.post(f"/api/accounting/vat-statements/{stmt_a.pk}/finalize/", {}, format="json", **h)
    assert res.status_code == 404, res.content
    stmt_a.refresh_from_db()
    assert stmt_a.status == VatStatement.STATUS_FINAL
