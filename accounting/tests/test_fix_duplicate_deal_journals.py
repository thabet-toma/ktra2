"""`fix_duplicate_deal_journals`: قيدُ شراء الصفقة المُرحَّلُ مرّتين.

شكلُ الإنتاج (الشركة 1): 69 صفقةً و138 قيداً — قيدان لكلِّ صفقة، فالمصروفُ وذمّةُ
المورّد مضاعفان. الأمرُ يحذف الزائدَ وحده، ويترك ما لا يُعرف فيه الحقّ.
"""
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year, partner_posted_balance, post_journal
from logistics.models import LogisticsDeal
from partners.models import Partner
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="dupdeal", password="x")
    tenant = create_company("شركة صفقات مكرَّرة", owner)
    create_fiscal_year(tenant, 2026)
    ap = Account.objects.create(
        tenant=tenant, code="2101-D", name="ذمم مورد الصفقة",
        account_type="Liability", is_active=True)
    expense = Account.objects.get(tenant=tenant, code="5") if Account.objects.filter(
        tenant=tenant, code="5").exists() else Account.objects.create(
        tenant=tenant, code="5-D", name="مصروفات", account_type="Expense", is_active=True)
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد الصين", partner_type="Supplier", linked_account=ap)
    return tenant, supplier, ap, expense


def _deal(tenant, supplier, total, ref="D-0001"):
    return LogisticsDeal.objects.create(
        tenant=tenant, ref_number=ref, partner=supplier, order_date="2026-06-01",
        total_amount=Decimal(total), description="شراء")


def _deal_journal(tenant, supplier, ap, expense, deal, amount):
    return post_journal(
        tenant_id=tenant.TenantID, transaction_date="2026-06-02",
        reference_type="LOGISTICS_DEAL", reference_id=deal.pk,
        description=f"شراء بضاعة (Auto): {deal.ref_number}",
        lines_data=[
            {"account": expense.id, "debit": Decimal(amount), "credit": Decimal("0")},
            {"account": ap.id, "debit": Decimal("0"), "credit": Decimal(amount),
             "partner": supplier.id},
        ],
        idempotent=False,
    )


def _journal_ids(deal):
    return sorted(JournalHeader.objects.filter(
        reference_type="LOGISTICS_DEAL", reference_id=deal.pk).values_list("id", flat=True))


def test_identical_pair_keeps_the_first_and_halves_the_supplier_balance(env):
    tenant, supplier, ap, expense = env
    deal = _deal(tenant, supplier, "4005")
    first = _deal_journal(tenant, supplier, ap, expense, deal, "4005")
    _second = _deal_journal(tenant, supplier, ap, expense, deal, "4005")
    _debit, credit = partner_posted_balance(tenant.TenantID, supplier.id)
    assert credit == Decimal("8010.00")  # الشراءُ مرّتين

    out = StringIO()
    call_command("fix_duplicate_deal_journals", "--apply", stdout=out)

    assert _journal_ids(deal) == [first.id]
    _debit, credit = partner_posted_balance(tenant.TenantID, supplier.id)
    assert credit == Decimal("4005.00")
    assert "1 قيداً مكرَّراً" in out.getvalue()


def test_report_changes_nothing_and_rerun_is_a_noop(env):
    tenant, supplier, ap, expense = env
    deal = _deal(tenant, supplier, "1000")
    _deal_journal(tenant, supplier, ap, expense, deal, "1000")
    _deal_journal(tenant, supplier, ap, expense, deal, "1000")
    before = _journal_ids(deal)

    out = StringIO()
    call_command("fix_duplicate_deal_journals", stdout=out)
    assert "أعد التشغيل بـ--apply" in out.getvalue()
    assert _journal_ids(deal) == before

    call_command("fix_duplicate_deal_journals", "--apply", stdout=StringIO())
    kept = _journal_ids(deal)
    out = StringIO()
    call_command("fix_duplicate_deal_journals", "--apply", stdout=out)
    assert "لا قيدَ صفقةٍ مكرَّراً" in out.getvalue()
    assert _journal_ids(deal) == kept


def test_edited_deal_keeps_the_journal_matching_its_total(env):
    """الصفقةُ عُدِّلت وأُعيد ترحيلُها: الباقي هو المطابقُ للإجمالي لا الأحدثَ آلياً."""
    tenant, supplier, ap, expense = env
    deal = _deal(tenant, supplier, "76625")
    stale = _deal_journal(tenant, supplier, ap, expense, deal, "79140")
    current = _deal_journal(tenant, supplier, ap, expense, deal, "76625")

    call_command("fix_duplicate_deal_journals", "--apply", stdout=StringIO())

    assert _journal_ids(deal) == [current.id]
    assert not JournalHeader.objects.filter(pk=stale.pk).exists()
    _debit, credit = partner_posted_balance(tenant.TenantID, supplier.id)
    assert credit == Decimal("76625.00")


def test_older_journal_survives_when_it_is_the_matching_one(env):
    tenant, supplier, ap, expense = env
    deal = _deal(tenant, supplier, "500")
    matching = _deal_journal(tenant, supplier, ap, expense, deal, "500")
    _newer = _deal_journal(tenant, supplier, ap, expense, deal, "650")

    call_command("fix_duplicate_deal_journals", "--apply", stdout=StringIO())

    assert _journal_ids(deal) == [matching.id]


def test_pair_matching_nothing_is_left_for_review(env):
    tenant, supplier, ap, expense = env
    deal = _deal(tenant, supplier, "900")
    _a = _deal_journal(tenant, supplier, ap, expense, deal, "700")
    _b = _deal_journal(tenant, supplier, ap, expense, deal, "800")
    before = _journal_ids(deal)

    out = StringIO()
    call_command("fix_duplicate_deal_journals", "--apply", stdout=out)

    assert _journal_ids(deal) == before
    assert "متروكةٌ للمراجعة" in out.getvalue()


def test_single_journal_and_other_tenants_are_untouched(env):
    tenant, supplier, ap, expense = env
    lonely = _deal(tenant, supplier, "300", ref="D-0002")
    only = _deal_journal(tenant, supplier, ap, expense, lonely, "300")

    other_owner = User.objects.create_user(username="dupdeal2", password="x")
    other = create_company("شركة أخرى", other_owner)
    create_fiscal_year(other, 2026)
    oap = Account.objects.create(
        tenant=other, code="2101-O", name="ذمم", account_type="Liability", is_active=True)
    oexp = Account.objects.create(
        tenant=other, code="5-O", name="مصروفات", account_type="Expense", is_active=True)
    osup = Partner.objects.create(
        tenant=other, name="مورد آخر", partner_type="Supplier", linked_account=oap)
    odeal = _deal(other, osup, "700", ref="D-0003")
    _deal_journal(other, osup, oap, oexp, odeal, "700")
    _deal_journal(other, osup, oap, oexp, odeal, "700")
    other_before = _journal_ids(odeal)

    call_command("fix_duplicate_deal_journals", "--apply",
                 "--tenant", str(tenant.TenantID), stdout=StringIO())

    assert _journal_ids(lonely) == [only.id]
    assert _journal_ids(odeal) == other_before
