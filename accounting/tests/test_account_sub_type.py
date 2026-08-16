"""THA-111-T1 — التصنيف الوظيفي للحساب (`Account.sub_type`).

`account_type` الخمسة (أصل/التزام/حقوق/إيراد/مصروف) تكفي التقارير ولا تكفي
المنتقي: «الصندوق الافتراضي» و«حساب القبض» كلاهما «أصل»، فكانت كل شاشة تخمّن
الصندوق ببادئة الرقم أو باسم الحساب — ثلاث شاشات بثلاث إجابات. `sub_type`
يخزّن الجواب مرة واحدة مشتقّاً من الروابط التي يملكها الخادم أصلاً
(`BankAccount.account`، `CashBoxLedgerAccount.account`، `Partner.linked_account`)
ثم من الشجرة المعيارية ثم من اسم الحساب — بهذا الترتيب من الحجّية.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.account_classification import (
    SUB_TYPE_BANK, SUB_TYPE_CASH_BOX, SUB_TYPE_INVENTORY, SUB_TYPE_PAYABLE,
    SUB_TYPE_RECEIVABLE, backfill_account_sub_types,
)
from accounting.models import Account, Bank, BankAccount, CashBoxLedgerAccount
from accounting.services import create_bank_account
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="subtype-owner", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة التصنيف", owner)
    client = APIClient()
    client.force_authenticate(user=owner)
    return tenant, client, ils, owner


def _headers(tenant):
    return {"HTTP_X_TENANT_ID": str(tenant.TenantID)}


def _child(tenant, parent_code, code, name, account_type="Asset"):
    """حسابٌ كما كان **قبل** الهجرة: بلا تصنيف.

    `Account.save()` صار يشتقّ التصنيف عند الإنشاء (THA-111، اعتراض فيبل 2)،
    وهذه الاختبارات تفحص الـbackfill — ومجاله صفوف ما قبل الهجرة الفارغة. لولا
    التفريغ هنا لفحصت اشتقاق الإنشاء مرتين ولم تفحص الـbackfill ولا مرة.
    """
    parent = Account.objects.filter(tenant=tenant, code=parent_code).first()
    account = Account.objects.create(
        tenant=tenant, code=code, name=name, parent=parent,
        account_type=account_type, is_active=True,
    )
    Account.objects.filter(pk=account.pk).update(sub_type=None)
    account.sub_type = None
    return account


def _sub_type(account):
    account.refresh_from_db()
    return account.sub_type


# ── الحجّة الأولى: الروابط التي ينشئها الخادم ──────────────────────────────

def test_account_linked_from_a_bank_account_is_bank(env):
    tenant, _client, ils, _owner = env
    bank = Bank.objects.create(tenant=tenant, name="بنك التصنيف")
    ba = create_bank_account(tenant=tenant, bank=bank, name="جاري شيكل", currency=ils)
    Account.objects.filter(pk=ba.account_id).update(sub_type=None)

    backfill_account_sub_types()

    assert _sub_type(ba.account) == SUB_TYPE_BANK


def test_account_linked_from_a_cash_box_is_cash_box(env):
    tenant, _client, _ils, _owner = env
    acc = _child(tenant, "1110", "1110B0001", "صندوق الفرع")
    CashBoxLedgerAccount.objects.create(
        tenant=tenant, external_id="fs-box-1", name="صندوق الفرع", account=acc)

    backfill_account_sub_types()

    assert _sub_type(acc) == SUB_TYPE_CASH_BOX


def test_partner_links_classify_receivable_and_payable(env):
    tenant, _client, _ils, _owner = env
    customer_account = _child(tenant, "1103", "1103-9001", "ذمة زبون")
    supplier_account = _child(tenant, "21", "2101-9001", "ذمة مورد", "Liability")
    Partner.objects.create(tenant=tenant, name="زبون", partner_type="Customer",
                           linked_account=customer_account)
    Partner.objects.create(tenant=tenant, name="مورد", partner_type="Supplier",
                           linked_account=supplier_account)

    backfill_account_sub_types()

    assert _sub_type(customer_account) == SUB_TYPE_RECEIVABLE
    assert _sub_type(supplier_account) == SUB_TYPE_PAYABLE


# ── الحجّة الثانية: سلالة الشجرة المعيارية ────────────────────────────────

def test_descendant_of_the_inventory_root_is_inventory(env):
    tenant, _client, _ils, _owner = env
    acc = _child(tenant, "1104", "110401", "مخزون فرع رام الله")

    backfill_account_sub_types()

    assert _sub_type(acc) == SUB_TYPE_INVENTORY


def test_the_link_beats_the_lineage_when_they_disagree(env):
    """حساب مركون تحت «1104 المخزون» لكنه مربوط بحساب بنكي: الرابط هو الجواب."""
    tenant, _client, ils, _owner = env
    bank = Bank.objects.create(tenant=tenant, name="بنك في غير مكانه")
    misfiled = _child(tenant, "1104", "110499", "حساب بنكي مركون تحت المخزون")
    BankAccount.objects.create(
        tenant=tenant, bank=bank, name="جاري مركون", currency=ils, account=misfiled)

    backfill_account_sub_types()

    assert _sub_type(misfiled) == SUB_TYPE_BANK


# ── الحجّة الثالثة: اسم الحساب ────────────────────────────────────────────

def test_a_petty_cash_till_is_a_cash_box_by_its_name(env):
    """انحراف `SalesInvoiceEditor` (`/till|petty/`) يُستوعَب هنا لا في شاشة."""
    tenant, _client, _ils, _owner = env
    acc = _child(tenant, "11", "1199", "Petty cash till")

    backfill_account_sub_types()

    assert _sub_type(acc) == SUB_TYPE_CASH_BOX


def test_a_name_match_outside_the_assets_does_not_classify(env):
    """«عمولات بنكية» مصروف لا بنك — الاسم وحده لا يكفي خارج الأصول."""
    tenant, _client, _ils, _owner = env
    acc = _child(tenant, "5", "5199", "عمولات بنكية", account_type="Expense")

    backfill_account_sub_types()

    assert _sub_type(acc) is None


# ── سلامة الـbackfill ─────────────────────────────────────────────────────

def test_backfill_is_idempotent_and_keeps_a_manual_correction(env):
    tenant, _client, _ils, _owner = env
    acc = _child(tenant, "1104", "110402", "مخزون آخر")
    backfill_account_sub_types()
    assert _sub_type(acc) == SUB_TYPE_INVENTORY

    Account.objects.filter(pk=acc.pk).update(sub_type=SUB_TYPE_CASH_BOX)
    backfill_account_sub_types()

    assert _sub_type(acc) == SUB_TYPE_CASH_BOX


def test_a_tenant_without_the_standard_roots_does_not_break(env):
    tenant, _client, _ils, _owner = env
    Account.objects.filter(tenant=tenant).delete()
    lonely = Account.objects.create(
        tenant=tenant, code="9001", name="حساب وحيد", account_type="Asset")

    backfill_account_sub_types()

    assert _sub_type(lonely) is None


def test_backfill_does_not_leak_across_companies(env):
    tenant, _client, _ils, _owner = env
    other_owner = User.objects.create_user(username="subtype-other", password="x")
    other = create_company("شركة أخرى", other_owner)
    ours = _child(tenant, "1104", "110403", "مخزوننا")
    theirs = _child(other, "1104", "110403", "مخزونهم")

    backfill_account_sub_types(tenant_ids=[tenant.TenantID])

    assert _sub_type(ours) == SUB_TYPE_INVENTORY
    assert _sub_type(theirs) is None


# ── الصيانة الذاتية عند الإنشاء ───────────────────────────────────────────

def test_creating_a_bank_account_through_the_api_classifies_its_gl_account(env):
    tenant, client, ils, _owner = env
    bank = Bank.objects.create(tenant=tenant, name="بنك الإنشاء")

    res = client.post("/api/accounting/bank-accounts/", {
        "bank": bank.pk, "name": "جاري جديد", "currency": ils.CurrencyID,
    }, format="json", **_headers(tenant))

    assert res.status_code == 201, res.data
    ba = BankAccount.objects.get(pk=res.data["id"])
    assert ba.account.sub_type == SUB_TYPE_BANK


def test_creating_a_cash_box_through_the_api_classifies_its_gl_account(env):
    tenant, client, _ils, _owner = env

    res = client.post("/api/accounting/cash-box-accounts/", {
        "external_id": "fs-box-api", "name": "صندوق المعرض", "currency_code": "ILS",
    }, format="json", **_headers(tenant))

    assert res.status_code in (200, 201), res.data
    link = CashBoxLedgerAccount.objects.get(tenant=tenant, external_id="fs-box-api")
    assert link.account.sub_type == SUB_TYPE_CASH_BOX


# ── الـAPI ────────────────────────────────────────────────────────────────

def test_accounts_endpoint_exposes_sub_type_and_patch_sets_it(env):
    tenant, client, _ils, _owner = env
    acc = _child(tenant, "1104", "110404", "مخزون للتعديل")
    backfill_account_sub_types()

    res = client.get("/api/accounting/accounts/", **_headers(tenant))
    assert res.status_code == 200, res.data
    payload = res.json()
    rows = payload["results"] if isinstance(payload, dict) else payload
    row = next(r for r in rows if r["id"] == acc.pk)
    assert row["sub_type"] == SUB_TYPE_INVENTORY

    res = client.patch(f"/api/accounting/accounts/{acc.pk}/", {"sub_type": "cash_box"},
                       format="json", **_headers(tenant))
    assert res.status_code == 200, res.data
    assert _sub_type(acc) == SUB_TYPE_CASH_BOX

    res = client.patch(f"/api/accounting/accounts/{acc.pk}/", {"sub_type": "nonsense"},
                       format="json", **_headers(tenant))
    assert res.status_code == 400, res.data
