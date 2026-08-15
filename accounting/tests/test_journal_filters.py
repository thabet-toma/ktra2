"""A3 (THA-188) — دفتر اليومية: تصفية بالحساب وبالمستخدم، ووسم قيد التسوية.

ثلاثة عقود يثبتها هذا الملف:

  1. `?account=` يُرجع **بالضبط** القيود التي لها سطر على ذلك الحساب — ولا
     يكرّر رأس القيد إن كان له أكثر من سطر عليه (استعلام Exists لا ضمّ
     +distinct: الضمّ يكرّر الصف فيفسد الترقيم — count ≠ ما يُبثّ فعلاً).
  2. `?user=` يُرجع قيود مُنشئها وحده — و`created_by` يُختَم من مساري الإنشاء
     كليهما: القيد اليدوي من الشاشة (`JournalViewSet.create`) والقيد الآلي
     (`post_journal`).
  3. قيد التسوية يدور دورة كاملة: إنشاء بـ`reference_type='ADJUSTMENT'` ←
     ظهور في القائمة ← تصفية تُرجعه وحده.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

DATE = "2026-03-15"


@pytest.fixture
def env():
    owner = User.objects.create_user(
        username="jf-owner", password="x", first_name="سامي", last_name="المحاسب")
    other = User.objects.create_user(username="jf-other", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة دفتر اليومية", owner)
    create_fiscal_year(tenant, 2026)
    cash = Account.objects.create(
        tenant=tenant, code="1000-F", name="الصندوق", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4000-F", name="إيراد", account_type="Revenue", is_active=True)
    exp = Account.objects.create(
        tenant=tenant, code="5000-F", name="مصروف", account_type="Expense", is_active=True)
    return {
        "tenant": tenant, "owner": owner, "other": other,
        "cash": cash, "rev": rev, "exp": exp,
    }


def _client(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    return client, {"HTTP_X_TENANT_ID": str(tenant.TenantID)}


def _journal(tenant, pairs, *, created_by=None, reference_type="MANUAL"):
    """قيد محفوظ مباشرةً — pairs = [(account, debit, credit), …]."""
    header = JournalHeader.objects.create(
        tenant=tenant, transaction_date=DATE, description="قيد اختبار",
        reference_type=reference_type, created_by=created_by,
    )
    for account, debit, credit in pairs:
        JournalLine.objects.create(
            tenant=tenant, journal=header, account=account,
            debit=Decimal(debit), credit=Decimal(credit),
        )
    return header


def _payload(cash, rev, *, reference_type="MANUAL"):
    return {
        "transaction_date": DATE,
        "description": "قيد من الشاشة",
        "reference_type": reference_type,
        "reference_id": None,
        "is_posted": False,
        "exchange_rate": 1,
        "lines": [
            {"account": cash.id, "debit": 100, "credit": 0, "description": "صندوق"},
            {"account": rev.id, "debit": 0, "credit": 100, "description": "إيراد"},
        ],
    }


def _ids(data):
    return [row["id"] for row in data["results"]]


# ── 1) التصفية بالحساب ──

def test_account_filter_returns_exactly_the_journals_touching_it(env):
    both = _journal(env["tenant"], [(env["cash"], "100", "0"), (env["rev"], "0", "100")])
    cash_twice = _journal(env["tenant"], [
        (env["cash"], "40", "0"), (env["cash"], "60", "0"), (env["rev"], "0", "100")])
    without = _journal(env["tenant"], [(env["exp"], "70", "0"), (env["rev"], "0", "70")])

    client, h = _client(env["owner"], env["tenant"])
    res = client.get(f"/api/accounting/journals/?account={env['cash'].id}", **h)
    assert res.status_code == 200, res.content
    data = res.json()

    assert sorted(_ids(data)) == sorted([both.id, cash_twice.id])
    assert without.id not in _ids(data)
    # القيد ذو السطرين على نفس الحساب يظهر مرة واحدة، والعدّاد يطابق ما بُثّ.
    assert data["count"] == 2
    assert len(data["results"]) == 2


def test_account_filter_does_not_duplicate_a_journal_across_pages(env):
    """الضمّ+distinct كان يعطي count أكبر من عدد الصفوف الحقيقية ⇒ صفحة يتيمة."""
    for _ in range(3):
        _journal(env["tenant"], [
            (env["cash"], "30", "0"), (env["cash"], "70", "0"), (env["rev"], "0", "100")])

    client, h = _client(env["owner"], env["tenant"])
    seen = []
    for page in (1, 2, 3):
        res = client.get(
            f"/api/accounting/journals/?account={env['cash'].id}"
            f"&page={page}&page_size=1", **h)
        assert res.status_code == 200, res.content
        seen += _ids(res.json())
    assert len(seen) == len(set(seen)) == 3

    res = client.get(
        f"/api/accounting/journals/?account={env['cash'].id}&page_size=1", **h)
    assert res.json()["count"] == 3


def test_account_filter_rejects_a_non_numeric_account_without_leaking(env):
    _journal(env["tenant"], [(env["cash"], "100", "0"), (env["rev"], "0", "100")])
    client, h = _client(env["owner"], env["tenant"])
    res = client.get("/api/accounting/journals/?account=abc", **h)
    assert res.status_code == 200
    assert res.json()["count"] == 0


# ── 2) التصفية بالمستخدم ──

def test_user_filter_matches_the_creator(env):
    mine = _journal(
        env["tenant"], [(env["cash"], "100", "0"), (env["rev"], "0", "100")],
        created_by=env["owner"])
    theirs = _journal(
        env["tenant"], [(env["exp"], "50", "0"), (env["rev"], "0", "50")],
        created_by=env["other"])
    legacy = _journal(env["tenant"], [(env["cash"], "10", "0"), (env["rev"], "0", "10")])

    client, h = _client(env["owner"], env["tenant"])
    data = client.get(f"/api/accounting/journals/?user={env['owner'].id}", **h).json()
    assert _ids(data) == [mine.id]
    # القيود القديمة (بلا مستخدم) لا تُنسب لأحد.
    assert legacy.id not in _ids(data)

    data = client.get(f"/api/accounting/journals/?user={env['other'].id}", **h).json()
    assert _ids(data) == [theirs.id]


def test_manual_entry_from_the_screen_stamps_its_creator(env):
    client, h = _client(env["owner"], env["tenant"])
    res = client.post(
        "/api/accounting/journals/", _payload(env["cash"], env["rev"]),
        format="json", **h)
    assert res.status_code == 201, res.content
    created = JournalHeader.objects.get(pk=res.json()["id"])
    assert created.created_by_id == env["owner"].id

    data = client.get(f"/api/accounting/journals/?user={env['owner'].id}", **h).json()
    assert _ids(data) == [created.id]
    # عمود «المستخدم» في الدفتر: الاسم الكامل إن وُجد، وإلا اسم الدخول.
    assert data["results"][0]["created_by_name"] == "سامي المحاسب"


def test_posted_journal_stamps_its_creator(env):
    jh = post_journal(
        tenant_id=env["tenant"].TenantID,
        transaction_date=DATE,
        reference_type="MANUAL",
        reference_id=None,
        description="قيد آلي",
        lines_data=[
            {"account": env["cash"].id, "debit": 100, "credit": 0},
            {"account": env["rev"].id, "debit": 0, "credit": 100},
        ],
        user=env["owner"],
    )
    assert jh.created_by_id == env["owner"].id


def test_posted_journal_without_a_user_stays_unattributed(env):
    jh = post_journal(
        tenant_id=env["tenant"].TenantID,
        transaction_date=DATE,
        reference_type="MANUAL",
        reference_id=None,
        description="قيد آلي بلا مستخدم",
        lines_data=[
            {"account": env["cash"].id, "debit": 5, "credit": 0},
            {"account": env["rev"].id, "debit": 0, "credit": 5},
        ],
    )
    assert jh.created_by_id is None


# ── 3) قيد التسوية ──

def test_adjustment_entry_round_trips_create_list_filter(env):
    client, h = _client(env["owner"], env["tenant"])
    res = client.post(
        "/api/accounting/journals/",
        _payload(env["cash"], env["rev"], reference_type="ADJUSTMENT"),
        format="json", **h)
    assert res.status_code == 201, res.content
    adjustment_id = res.json()["id"]

    plain = client.post(
        "/api/accounting/journals/", _payload(env["cash"], env["rev"]),
        format="json", **h)
    assert plain.status_code == 201, plain.content

    listed = client.get("/api/accounting/journals/", **h).json()
    assert set(_ids(listed)) == {adjustment_id, plain.json()["id"]}
    row = next(r for r in listed["results"] if r["id"] == adjustment_id)
    assert row["reference_type"] == "ADJUSTMENT"
    assert row["source_label"] == "قيد تسوية"

    filtered = client.get(
        "/api/accounting/journals/?reference_type=ADJUSTMENT", **h).json()
    assert _ids(filtered) == [adjustment_id]


# ── خيارات فلتر المستخدم ──

def test_journal_users_endpoint_lists_only_this_tenant_creators(env):
    _journal(
        env["tenant"], [(env["cash"], "100", "0"), (env["rev"], "0", "100")],
        created_by=env["owner"])

    stranger = User.objects.create_user(username="jf-stranger", password="x")
    other_tenant = create_company("شركة أخرى", stranger)
    other_account = Account.objects.create(
        tenant=other_tenant, code="1000-X", name="صندوق", account_type="Asset",
        is_active=True)
    _journal(other_tenant, [(other_account, "10", "0")], created_by=stranger)

    client, h = _client(env["owner"], env["tenant"])
    res = client.get("/api/accounting/journals/users/", **h)
    assert res.status_code == 200, res.content
    assert res.json() == [{"id": env["owner"].id, "name": "سامي المحاسب"}]
