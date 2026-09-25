"""كشف حساب الطرف: «القيد المعكوس وعكسه» يُعلَّم زوجاً ليُطوى في العرض.

مثال الإنتاج (yoyo): دفعة #283 مدين 13,928.63 وعكسها #10979 دائن 13,928.63، والصحيحة
#10980 بـ4,298.96 — كانت تظهر سطرين كاملين والرصيد الجاري يمرّ بينهما بقيمة مضلّلة.
الخادم لا يحذف ولا يدمج: يعلّم الزوج ويرسل الرصيد محسوباً بلا الأزواج إلى جانب الخام.
"""
from decimal import Decimal

import pytest

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import partner_account_statement, partner_posted_balance
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _journal(tenant, *, date, lines, ref_type, ref_id=1, description=""):
    """lines: list of (account, debit, credit, partner[, line_description])."""
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date=date, is_posted=True, exchange_rate=Decimal("1"),
        reference_type=ref_type, reference_id=ref_id, description=description)
    for acc, d, c, partner, *rest in lines:
        JournalLine.objects.create(
            tenant=tenant, journal=jh, account=acc, description=(rest[0] if rest else ""),
            debit=Decimal(str(d)), credit=Decimal(str(c)), partner=partner)
    return jh


@pytest.fixture
def env():
    from django.contrib.auth.models import User

    owner = User.objects.create_user(username="revpair", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة الأزواج", owner)
    ap = Account.objects.create(
        tenant=tenant, code="2102-X", name="ذمم وكلاء", account_type="Liability", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1110-X", name="صندوق", account_type="Asset", is_active=True)
    freight = Account.objects.create(
        tenant=tenant, code="5101-X", name="شحن", account_type="Expense", is_active=True)
    agent = Partner.objects.create(
        tenant=tenant, name="yoyo", partner_type="FreightForwarder", linked_account=ap)
    return tenant, ap, cash, freight, agent


def _statement(tenant, agent, **kw):
    return partner_account_statement(
        tenant_id=tenant.TenantID, partner_id=agent.id, is_supplier=True,
        ordering="oldest", limit=100, **kw)


def _yoyo(env):
    tenant, ap, cash, freight, agent = env
    accrual = _journal(tenant, date="2026-05-01", ref_type="SHIPMENT_FREIGHT_ACCRUAL",
                       lines=[(freight, "11348.22", 0, None), (ap, 0, "11348.22", agent)])
    wrong = _journal(tenant, date="2026-05-10", ref_type="LOGISTICS_PAYMENT", ref_id=175,
                     lines=[(ap, "13928.63", 0, agent), (cash, 0, "13928.63", None)])
    reversal = _journal(
        tenant, date="2026-05-10", ref_type="LOGISTICS_PAYMENT_UNPOST", ref_id=175,
        description=f"[تصحيح عملة] دفعة #175 — عكس القيد #{wrong.id} (قيمته بالشيكل خاطئة)",
        lines=[(ap, 0, "13928.63", agent, f"عكس قيد #{wrong.id}: دفعة"),
               (cash, "13928.63", 0, None, f"عكس قيد #{wrong.id}: دفعة")])
    right = _journal(tenant, date="2026-05-10", ref_type="LOGISTICS_PAYMENT", ref_id=175,
                     lines=[(ap, "4298.96", 0, agent), (cash, 0, "4298.96", None)])
    return accrual, wrong, reversal, right


def test_zero_net_pair_is_marked_and_the_closing_balance_is_unchanged(env):
    tenant, _ap, _cash, _freight, agent = env
    accrual, wrong, reversal, right = _yoyo(env)

    st = _statement(tenant, agent)
    by_journal = {r["journal_id"]: r for r in st["results"]}
    # لا حذف ولا دمج: الأسطر الأربعة كلّها في الردّ.
    assert st["count"] == 4 and len(st["results"]) == 4

    for jid in (wrong.id, reversal.id):
        assert by_journal[jid]["reversal_pair_id"] == wrong.id
    assert by_journal[wrong.id]["reversal_pair"] == {
        "original_journal_id": wrong.id, "reversal_journal_id": reversal.id, "role": "original"}
    assert by_journal[reversal.id]["reversal_pair"]["role"] == "reversal"
    for jid in (accrual.id, right.id):
        assert by_journal[jid]["reversal_pair_id"] is None
        assert by_journal[jid]["reversal_pair"] is None

    # الخام كما كان: الرصيد يمرّ بالقيمة المضلّلة −2,580.41 بين القيد وعكسه.
    assert Decimal(by_journal[wrong.id]["running_balance"]) == Decimal("-2580.41")
    # المطويّ: الزوج لا يحرّك الرصيد، فلا قيمة مضلّلة.
    assert Decimal(by_journal[wrong.id]["running_balance_folded"]) == Decimal("11348.22")
    assert Decimal(by_journal[reversal.id]["balance_before_folded"]) == Decimal("11348.22")
    assert Decimal(by_journal[right.id]["balance_before_folded"]) == Decimal("11348.22")
    assert Decimal(by_journal[right.id]["running_balance_folded"]) == Decimal("7049.26")

    # الختامي واحدٌ في الحالتين ويطابق الدفتر.
    assert Decimal(st["closing_balance"]) == Decimal("7049.26")
    assert by_journal[right.id]["running_balance"] == by_journal[right.id]["running_balance_folded"]
    debit, credit = partner_posted_balance(tenant.TenantID, agent.id)
    assert credit - debit == Decimal(st["closing_balance"])


def test_partial_reversal_is_not_a_pair(env):
    tenant, ap, cash, _freight, agent = env
    original = _journal(tenant, date="2026-05-10", ref_type="LOGISTICS_PAYMENT", ref_id=9,
                        lines=[(ap, "1000.00", 0, agent), (cash, 0, "1000.00", None)])
    partial = _journal(tenant, date="2026-05-11", ref_type="LOGISTICS_PAYMENT_UNPOST", ref_id=9,
                       description=f"عكس القيد #{original.id}",
                       lines=[(ap, 0, "400.00", agent), (cash, "400.00", 0, None)])

    st = _statement(tenant, agent)
    assert all(r["reversal_pair_id"] is None for r in st["results"])
    rows = {r["journal_id"]: r for r in st["results"]}
    # بلا زوج: المطويّ هو الخام نفسه — العكس الجزئي حركةٌ حقيقية لا تُخفى.
    for jid in (original.id, partial.id):
        assert rows[jid]["running_balance_folded"] == rows[jid]["running_balance"]
    assert Decimal(st["closing_balance"]) == Decimal("-600.00")


def test_manual_journal_reversal_pairs_by_its_reference(env):
    tenant, ap, cash, _freight, agent = env
    original = _journal(tenant, date="2026-05-10", ref_type="MANUAL", ref_id=None,
                        lines=[(ap, "250.00", 0, agent), (cash, 0, "250.00", None)])
    reversal = _journal(tenant, date="2026-05-12", ref_type="JOURNAL_REVERSAL", ref_id=original.id,
                        lines=[(ap, 0, "250.00", agent), (cash, "250.00", 0, None)])

    rows = {r["journal_id"]: r for r in _statement(tenant, agent)["results"]}
    assert rows[original.id]["reversal_pair_id"] == original.id
    assert rows[reversal.id]["reversal_pair_id"] == original.id


def test_unpost_type_without_text_pairs_with_the_same_document(env):
    tenant, ap, cash, _freight, agent = env
    original = _journal(tenant, date="2026-05-10", ref_type="CLEARANCE_PAYMENT", ref_id=31,
                        lines=[(ap, "90.00", 0, agent), (cash, 0, "90.00", None)])
    other = _journal(tenant, date="2026-05-10", ref_type="CLEARANCE_PAYMENT", ref_id=32,
                     lines=[(ap, "90.00", 0, agent), (cash, 0, "90.00", None)])
    reversal = _journal(tenant, date="2026-05-12", ref_type="CLEARANCE_PAYMENT_UNPOST", ref_id=31,
                        lines=[(ap, 0, "90.00", agent), (cash, "90.00", 0, None)])

    rows = {r["journal_id"]: r for r in _statement(tenant, agent)["results"]}
    assert rows[reversal.id]["reversal_pair_id"] == original.id
    assert rows[original.id]["reversal_pair_id"] == original.id
    assert rows[other.id]["reversal_pair_id"] is None


def test_pair_marker_does_not_cross_tenants(env):
    """«عكس قيد #N» يشير إلى رقم قيدٍ في شركة أخرى: لا زوج."""
    tenant, ap, cash, _freight, agent = env
    from django.contrib.auth.models import User

    other_tenant = create_company("شركة أخرى", User.objects.create_user(username="revpair2"))
    other_ap = Account.objects.create(
        tenant=other_tenant, code="2102-Y", name="ذمم", account_type="Liability", is_active=True)
    foreign = _journal(other_tenant, date="2026-05-01", ref_type="LOGISTICS_PAYMENT",
                       lines=[(other_ap, "50.00", 0, None)])
    _journal(tenant, date="2026-05-02", ref_type="LOGISTICS_PAYMENT_UNPOST",
             description=f"عكس القيد #{foreign.id}",
             lines=[(ap, 0, "50.00", agent), (cash, "50.00", 0, None)])

    assert all(r["reversal_pair_id"] is None for r in _statement(tenant, agent)["results"])


def test_printed_statement_folds_pairs_by_default_and_shows_them_on_request(env):
    from core.reports import REPORTS

    tenant, _ap, _cash, _freight, agent = env
    accrual, wrong, reversal, right = _yoyo(env)
    build = REPORTS["partner-statement"].build

    folded = build(tenant.TenantID, {"partner": str(agent.id)})
    shown = build(tenant.TenantID, {"partner": str(agent.id), "reversals": "show"})

    # الخام: افتتاحي + أربع حركات؛ المطويّ: افتتاحي + استحقاق + سطر الزوج + الصحيحة.
    assert [r["id"] for r in shown[1:]] == [accrual.id, wrong.id, reversal.id, right.id]
    assert len(folded) == 4
    summary = folded[2]
    assert summary["description"] == f"قيد صُحّح: #{wrong.id} ⇄ #{reversal.id} (صافي 0)"
    assert Decimal(summary["debit"]) == 0 and Decimal(summary["credit"]) == 0
    assert Decimal(summary["balance"]) == Decimal("11348.22")
    assert "-2580.41" not in {r["balance"] for r in folded}
    # الختامي نفسه في الحالتين.
    assert folded[-1]["balance"] == shown[-1]["balance"] == "7049.26"


def test_printed_statement_keeps_a_pair_split_by_the_period(env):
    """أصلٌ قبل الفترة وعكسه داخلها: الأصل في الافتتاحي، فطيُّ العكس يُفسد الرصيد."""
    from core.reports import REPORTS

    tenant, _ap, _cash, _freight, agent = env
    _accrual, wrong, reversal, _right = _yoyo(env)
    JournalHeader.objects.filter(pk=wrong.pk).update(transaction_date="2026-04-01")

    rows = REPORTS["partner-statement"].build(
        tenant.TenantID, {"partner": str(agent.id), "from": "2026-04-15"})
    assert reversal.id in [r["id"] for r in rows]
    assert rows[-1]["balance"] == "7049.26"
