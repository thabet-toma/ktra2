"""سياسة ترحيل مستند لم يوافق عليه الزبون (T3).

حالة موافقة الزبون (T2) على الفاتورة وسند القبض تُقرأ عند الترحيل:

- الافتراضي `allow`: المحاسب يُحذَّر (`customer_approval_warning` في استجابة الترحيل) ويرحّل.
- `save_only` («منع الترحيل حتى موافقة الزبون»): `ValidationError` عربي من الخدمة نفسها —
  فيلتزم بها كل مسار ترحيل (نقطة الترحيل، التحصيل، الترحيل التلقائي) بقاعدةٍ واحدة.
- مستندات المنصة (`not_required`) لا يُحذَّر عليها ولا تُمنع أبداً.
- موافقةٌ تغيّر المحتوى بعدها بمسارٍ لا يمرّ بـ`drop_approval_if_changed` تُعامَل غير صالحة.
- الإرسالية بلا حارس (الزبون يؤكد الاستلام بعد التسليم) — شارةٌ فقط.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    CustomerApprovalFields,
    CustomerPayment,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)
from sales.services import get_or_create_sales_settings, post_customer_payment, post_sales_invoice
from sales.services.customer_approval import approval_post_issue
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

ALLOW = SalesSettings.POLICY_ALLOW
SAVE_ONLY = SalesSettings.POLICY_SAVE_ONLY
PENDING = CustomerApprovalFields.APPROVAL_PENDING
APPROVED = CustomerApprovalFields.APPROVAL_APPROVED
REJECTED = CustomerApprovalFields.APPROVAL_REJECTED
URLS = {"invoice": "/api/sales/invoices/{id}/", "payment": "/api/sales/payments/{id}/"}
SETTING_LABEL = "ترحيل مستند لم يوافق عليه الزبون"


@pytest.fixture
def env():
    owner = User.objects.create_user(username="cap-owner", password="x")
    cur, _ = Currency.objects.get_or_create(
        Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True})
    tenant = create_company("شركة سياسة الموافقة", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-A", name="ذمم", account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1000-A", name="صندوق", account_type="Asset", is_active=True)
    Account.objects.create(
        tenant=tenant, code="4101-A", name="إيراد", account_type="Revenue", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="CAP-1", name_ar="خدمة", is_service=True)
    client = APIClient()
    client.force_authenticate(user=owner)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return {
        "tenant": tenant, "cur": cur, "cash": cash, "customer": customer,
        "product": product, "client": client,
    }


def _policy(env, value):
    ss = get_or_create_sales_settings(env["tenant"])
    ss.customer_approval_post_policy = value
    ss.save(update_fields=["customer_approval_post_policy"])


def _invoice(env, number="CAP-INV-1", *, invoice_type=SalesInvoice.INVOICE_CREDIT):
    inv = SalesInvoice.objects.create(
        tenant=env["tenant"], invoice_number=number, customer=env["customer"],
        currency=env["cur"], invoice_date="2026-06-15", invoice_type=invoice_type,
        stock_on_post=False,
        cash_or_bank_account=env["cash"] if invoice_type == SalesInvoice.INVOICE_CASH else None)
    line = SalesInvoiceLine.objects.create(
        tenant=env["tenant"], invoice=inv, product=env["product"], quantity=Decimal("5"),
        unit_price=Decimal("100"))
    return inv, line


def _payment(env):
    return CustomerPayment.objects.create(
        tenant=env["tenant"], partner=env["customer"], payment_date="2026-06-20",
        amount=Decimal("100"), currency=env["cur"], exchange_rate=Decimal("1"),
        cash_or_bank_account=env["cash"])


def _make(env, kind, number="CAP-INV-1"):
    return _invoice(env, number)[0] if kind == "invoice" else _payment(env)


def _decide(env, kind, doc, status, **body):
    res = env["client"].post(
        URLS[kind].format(id=doc.id) + "customer-approval/",
        {"status": status, **body}, format="json")
    assert res.status_code == 200, res.content
    doc.refresh_from_db()


def _post(env, kind, doc):
    return env["client"].post(URLS[kind].format(id=doc.id) + "post/", {}, format="json")


def _journals(env):
    return JournalHeader.objects.filter(tenant=env["tenant"]).count()


def _is_posted(kind, doc):
    doc.refresh_from_db()
    return doc.status == SalesInvoice.STATUS_POSTED if kind == "invoice" else doc.is_posted


KINDS = ["invoice", "payment"]


# ── الافتراضي: تحذير فقط ──

def test_default_policy_is_allow(env):
    assert get_or_create_sales_settings(env["tenant"]).customer_approval_post_policy == ALLOW


@pytest.mark.parametrize("kind", KINDS)
def test_allow_policy_pending_posts_with_a_warning(env, kind):
    doc = _make(env, kind)
    _decide(env, kind, doc, PENDING)
    res = _post(env, kind, doc)
    assert res.status_code == 200, res.content
    assert res.json()["customer_approval_warning"] == "بانتظار موافقة الزبون"
    assert _is_posted(kind, doc)


@pytest.mark.parametrize("kind", KINDS)
def test_allow_policy_rejected_posts_with_a_warning_naming_who_and_why(env, kind):
    doc = _make(env, kind)
    _decide(env, kind, doc, REJECTED, by_name="خالد", note="السعر غالٍ")
    res = _post(env, kind, doc)
    assert res.status_code == 200, res.content
    assert res.json()["customer_approval_warning"] == "اعترض الزبون (خالد) — السعر غالٍ"
    assert _is_posted(kind, doc)


@pytest.mark.parametrize("kind", KINDS)
def test_approved_and_unchanged_posts_without_a_warning(env, kind):
    doc = _make(env, kind)
    _decide(env, kind, doc, APPROVED, by_name="خالد")
    res = _post(env, kind, doc)
    assert res.status_code == 200, res.content
    assert "customer_approval_warning" not in res.json()
    assert _is_posted(kind, doc)


@pytest.mark.parametrize("kind", KINDS)
def test_platform_document_posts_without_a_warning_under_either_policy(env, kind):
    for policy in (ALLOW, SAVE_ONLY):
        _policy(env, policy)
        doc = _make(env, kind, f"CAP-INV-{policy}")
        assert doc.customer_approval_status == CustomerApprovalFields.APPROVAL_NOT_REQUIRED
        res = _post(env, kind, doc)
        assert res.status_code == 200, res.content
        assert "customer_approval_warning" not in res.json()


def test_approved_but_content_changed_through_a_path_that_skips_the_drop(env):
    """تعديلٌ بالـORM لا يمرّ بـ`drop_approval_if_changed`: الحالة تبقى «موافق» والبصمة قديمة."""
    inv, line = _invoice(env)
    _decide(env, "invoice", inv, APPROVED, by_name="خالد")
    SalesInvoiceLine.objects.filter(pk=line.pk).update(unit_price=Decimal("999"))
    inv.refresh_from_db()
    assert inv.customer_approval_status == APPROVED
    assert approval_post_issue(inv) == "عُدّل بعد موافقة الزبون"

    res = _post(env, "invoice", inv)
    assert res.status_code == 200, res.content
    assert res.json()["customer_approval_warning"] == "عُدّل بعد موافقة الزبون"


# ── منع الترحيل ──

@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("status", [PENDING, REJECTED])
def test_save_only_refuses_pending_and_rejected_and_posts_nothing(env, kind, status):
    _policy(env, SAVE_ONLY)
    doc = _make(env, kind)
    _decide(env, kind, doc, status, by_name="خالد", note="ملاحظة")
    before = _journals(env)

    res = _post(env, kind, doc)

    assert res.status_code == 400
    message = res.json()["error"]
    assert not message.startswith("["), message  # جملة عربية لا تمثيل بايثون
    assert ("بانتظار موافقة الزبون" if status == PENDING else "اعترض الزبون (خالد)") in message
    assert SETTING_LABEL in message
    assert "منع الترحيل حتى موافقة الزبون" in message  # خيار الإعداد كما يراه المستخدم في الشاشة
    assert not _is_posted(kind, doc)
    assert _journals(env) == before


@pytest.mark.parametrize("kind", KINDS)
def test_save_only_lets_an_approved_document_post(env, kind):
    _policy(env, SAVE_ONLY)
    doc = _make(env, kind)
    _decide(env, kind, doc, APPROVED, by_name="خالد")
    res = _post(env, kind, doc)
    assert res.status_code == 200, res.content
    assert "customer_approval_warning" not in res.json()
    assert _is_posted(kind, doc)


def test_save_only_refuses_approval_whose_content_changed_behind_the_drop(env):
    _policy(env, SAVE_ONLY)
    inv, line = _invoice(env)
    _decide(env, "invoice", inv, APPROVED, by_name="خالد")
    SalesInvoiceLine.objects.filter(pk=line.pk).update(quantity=Decimal("6"))
    before = _journals(env)

    res = _post(env, "invoice", inv)

    assert res.status_code == 400
    assert "عُدّل بعد موافقة الزبون" in res.json()["error"]
    assert not _is_posted("invoice", inv)
    assert _journals(env) == before


def test_payment_changed_behind_the_drop_is_refused_under_save_only(env):
    _policy(env, SAVE_ONLY)
    pay = _payment(env)
    _decide(env, "payment", pay, APPROVED, by_name="خالد")
    CustomerPayment.objects.filter(pk=pay.pk).update(amount=Decimal("250"))

    res = _post(env, "payment", pay)

    assert res.status_code == 400
    assert "عُدّل بعد موافقة الزبون" in res.json()["error"]
    assert not _is_posted("payment", pay)


# ── القاعدة في الخدمة لا في نقطة الترحيل وحدها ──

def test_service_level_guard_covers_every_posting_path(env):
    _policy(env, SAVE_ONLY)
    inv, _ = _invoice(env)
    _decide(env, "invoice", inv, PENDING)
    with pytest.raises(ValidationError) as exc:
        post_sales_invoice(inv)
    assert SETTING_LABEL in " ".join(exc.value.messages)

    pay = _payment(env)
    _decide(env, "payment", pay, REJECTED, by_name="س")
    with pytest.raises(ValidationError):
        post_customer_payment(pay)
    assert not _is_posted("invoice", inv)
    assert not _is_posted("payment", pay)


def test_collect_path_obeys_the_same_rule(env):
    """التحصيل من داخل الفاتورة مع ترحيلها يمرّ بـ`post_sales_invoice` فيُمنع كالنقطة نفسها."""
    _policy(env, SAVE_ONLY)
    inv, _ = _invoice(env)
    _decide(env, "invoice", inv, PENDING)
    res = env["client"].post(
        f"/api/sales/invoices/{inv.id}/collect/",
        {"cash": "100", "cash_account_id": env["cash"].id, "post_invoice": True}, format="json")
    assert res.status_code == 400
    assert "بانتظار موافقة الزبون" in res.json()["error"]
    assert not _is_posted("invoice", inv)
    assert not CustomerPayment.objects.filter(tenant=env["tenant"]).exists()


def test_auto_settlement_payment_is_never_blocked(env):
    """فاتورة نقدية موافَق عليها تُنشئ داخل الترحيل سند قبض للتسوية: السند الداخلي
    `not_required` دائماً فلا يصطدم بالحارس حتى تحت `save_only`."""
    _policy(env, SAVE_ONLY)
    inv, _ = _invoice(env, "CAP-CASH-1", invoice_type=SalesInvoice.INVOICE_CASH)
    _decide(env, "invoice", inv, APPROVED, by_name="خالد")

    res = _post(env, "invoice", inv)

    assert res.status_code == 200, res.content
    settlement = CustomerPayment.objects.filter(tenant=env["tenant"])
    assert settlement.exists()
    assert all(
        p.customer_approval_status == CustomerApprovalFields.APPROVAL_NOT_REQUIRED
        and p.is_posted for p in settlement)


# ── الإعداد ──

def test_settings_round_trip_and_rejects_block(env):
    client = env["client"]
    got = client.get("/api/sales/settings/current/")
    assert got.status_code == 200
    assert got.json()["customer_approval_post_policy"] == ALLOW

    put = client.put(
        "/api/sales/settings/current/", {"customer_approval_post_policy": SAVE_ONLY},
        format="json")
    assert put.status_code == 200, put.content
    assert put.json()["customer_approval_post_policy"] == SAVE_ONLY
    assert client.get("/api/sales/settings/current/").json()[
        "customer_approval_post_policy"] == SAVE_ONLY

    # «منع الحفظ» بلا معنى هنا: المستند يجب أن يُحفظ ليراه الزبون.
    bad = client.put(
        "/api/sales/settings/current/", {"customer_approval_post_policy": "block"},
        format="json")
    assert bad.status_code == 400
    assert get_or_create_sales_settings(env["tenant"]).customer_approval_post_policy == SAVE_ONLY


# ── الدالة الخالصة ──

def test_approval_post_issue_messages(env):
    inv, _ = _invoice(env)
    assert approval_post_issue(inv) is None
    _decide(env, "invoice", inv, PENDING)
    assert approval_post_issue(inv) == "بانتظار موافقة الزبون"
    _decide(env, "invoice", inv, REJECTED, by_name="خالد", note="لا")
    assert approval_post_issue(inv) == "اعترض الزبون (خالد) — لا"
    _decide(env, "invoice", inv, APPROVED, by_name="خالد")
    assert approval_post_issue(inv) is None
