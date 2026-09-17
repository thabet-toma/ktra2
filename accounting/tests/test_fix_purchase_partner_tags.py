"""A1-2 — `fix_purchase_partner_tags`: قيود شراء قديمة وسمت المخزون/الضريبة/الوسيط
بالمورد فألغى مدينُها دائنَ الذمم. العرض لا يغيّر شيئاً، `--apply` يُزيل الوسم عن
غير الرقابي وحده، والتكرار بلا أثر، ورصيد المورد بعده = مبلغ الذمم."""
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance, post_journal
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="fixpurtag", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة وسم قديم", owner)
    create_fiscal_year(tenant, 2026)
    acc = {code: Account.objects.get(tenant=tenant, code=code) for code in ("1104", "1105")}
    ap = Account.objects.create(
        tenant=tenant, code="2101-FX", name="ذمم مورد قديم",
        account_type="Liability", is_active=True)
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد قديم", partner_type="Supplier", linked_account=ap)
    acc["ap"] = ap
    acc["grir"] = Account.objects.create(
        tenant=tenant, code="2110-FX", name="وسيط الاستلام",
        account_type="Liability", is_active=True)
    acc["other_liab"] = Account.objects.create(
        tenant=tenant, code="2999-FX", name="خصوم أخرى",
        account_type="Liability", is_active=True)
    return tenant, supplier, acc


def _legacy(tenant, supplier, ref_type, legs):
    """قيد بالشكل القديم: كل الأسطر موسومة بالمورد."""
    return post_journal(
        tenant_id=tenant.TenantID, transaction_date="2026-06-11",
        reference_type=ref_type, reference_id=None, description=f"قديم {ref_type}",
        lines_data=[
            {"account": a.id, "debit": Decimal(d), "credit": Decimal(c), "partner": supplier.id}
            for a, d, c in legs
        ],
        idempotent=False,
    )


def _tags(journal):
    return sorted(
        (l.account.code, l.partner_id)
        for l in JournalLine.objects.filter(journal=journal).select_related("account")
    )


def test_report_then_apply_then_noop(env):
    tenant, supplier, acc = env
    pi = _legacy(tenant, supplier, "PURCHASE_INVOICE", [
        (acc["1104"], "200", "0"), (acc["1105"], "32", "0"), (acc["ap"], "0", "232")])
    rc = _legacy(tenant, supplier, "PURCHASE_RECEIPT", [
        (acc["1104"], "100", "0"), (acc["ap"], "0", "100")])
    ret = _legacy(tenant, supplier, "PURCHASE_RETURN", [
        (acc["ap"], "58", "0"), (acc["1104"], "0", "50"), (acc["1105"], "0", "8")])
    grn = _legacy(tenant, supplier, "PURCHASE_GRN", [
        (acc["1104"], "40", "0"), (acc["grir"], "0", "40")])
    # لا سطر ذمم معروف: لا يُعرف أين ساق المورد ⇒ يُترك للمراجعة ولا يُلمس.
    ambiguous = _legacy(tenant, supplier, "PURCHASE_INVOICE", [
        (acc["1104"], "70", "0"), (acc["other_liab"], "0", "70")])
    before = {j.id: _tags(j) for j in (pi, rc, ret, grn, ambiguous)}
    # التلوّث: كل قيد يُلغي نفسه فرصيد المورد صفر رغم 232 + 100 − 58 مستحقّة.
    d, c = partner_posted_balance(tenant.TenantID, supplier.id)
    assert c - d == Decimal("0")

    out = StringIO()
    call_command("fix_purchase_partner_tags", stdout=out)
    report = out.getvalue()
    assert "PURCHASE_INVOICE: 2 سطراً في 1 قيداً" in report
    assert "PURCHASE_GRN: 2 سطراً في 1 قيداً" in report
    assert f"[{ambiguous.id}]" in report
    assert {j.id: _tags(j) for j in (pi, rc, ret, grn, ambiguous)} == before

    call_command("fix_purchase_partner_tags", "--apply", stdout=StringIO())
    for j in (pi, rc, ret):
        assert all(
            pid == (supplier.id if code == "2101-FX" else None) for code, pid in _tags(j)
        ), _tags(j)
    assert all(pid is None for _code, pid in _tags(grn))
    assert _tags(ambiguous) == before[ambiguous.id]
    d, c = partner_posted_balance(tenant.TenantID, supplier.id)
    # الذمم: 232 + 100 − 58 = 274؛ والقيد الملتبس متروك كما هو (يُلغي نفسه).
    assert (d, c) == (Decimal("128.00"), Decimal("402.00"))
    assert c - d == Decimal("274.00")
    # لا مبالغ ولا حسابات تغيّرت: القيود ما زالت متوازنة بنفس الأسطر.
    for j in (pi, rc, ret, grn):
        assert [code for code, _ in _tags(j)] == [code for code, _ in before[j.id]]

    snapshot = list(JournalLine.objects.values_list("id", "partner_id", "debit", "credit"))
    out = StringIO()
    call_command("fix_purchase_partner_tags", "--apply", stdout=out)
    assert "لا أسطر شراء بحاجة إصلاح" in out.getvalue()
    assert list(JournalLine.objects.values_list("id", "partner_id", "debit", "credit")) == snapshot


def test_tenant_flag_limits_scope(env):
    tenant, supplier, acc = env
    other_owner = User.objects.create_user(username="fixpurtag2", password="x")
    other = create_company("شركة أخرى", other_owner)
    create_fiscal_year(other, 2026)
    oap = Account.objects.create(
        tenant=other, code="2101-OX", name="ذمم", account_type="Liability", is_active=True)
    osup = Partner.objects.create(
        tenant=other, name="مورد آخر", partner_type="Supplier", linked_account=oap)
    mine = _legacy(tenant, supplier, "PURCHASE_INVOICE", [
        (acc["1104"], "10", "0"), (acc["ap"], "0", "10")])
    theirs = _legacy(other, osup, "PURCHASE_INVOICE", [
        (Account.objects.get(tenant=other, code="1104"), "10", "0"), (oap, "0", "10")])

    call_command("fix_purchase_partner_tags", "--apply", "--tenant", str(tenant.TenantID),
                 stdout=StringIO())
    assert JournalLine.objects.filter(journal=mine, partner__isnull=False).count() == 1
    assert JournalLine.objects.filter(journal=theirs, partner__isnull=False).count() == 2
