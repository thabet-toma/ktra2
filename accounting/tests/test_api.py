"""المرحلة 2 — اختبارات الواجهة العامة `accounting.api`.

تغطي كل دالة عامة في api.py:
- post_document: تفويض post_journal (ترحيل + idempotency + رفض غير المتوازن).
- reverse_journal: قلب مدين/دائن، نسخ العملة/المشروع، إلغاء ترحيل الأصل،
  ورفض الأصل غير المرحّل/غير المتوازن/بلا أسطر.
- purge_journals: حذف الأسطر ثم الرؤوس.
- get_account_by_code: بالكود مع/بدون قصر على الفعّالة.
- sync_partner_accounting / ensure_partner_account / create_partner_opening_balance:
  نفس عقد partners/signals قبل النقل (الأكواد المعيارية 2101/1103/… و3300).
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError

from django.db.models import Q

from accounting import api
from accounting.models import (
    Account, JournalHeader, JournalLine, OpeningBalance,
)
from accounting.services import create_fiscal_year
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def env():
    owner = User.objects.create_user(username="facade", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$")
    tenant = create_company("شركة الواجهة", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-F", name="ذمم واجهة", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-F", name="إيراد واجهة", account_type="Revenue", is_active=True)
    return tenant, owner, ils, usd, ar, rev


def _lines(ar, rev, amount="100"):
    amt = D(amount)
    return [
        {"account": ar.id, "debit": amt, "credit": D("0")},
        {"account": rev.id, "debit": D("0"), "credit": amt},
    ]


# ── post_document ────────────────────────────────────────────────────────────

def test_post_document_creates_posted_journal(env):
    tenant, owner, ils, usd, ar, rev = env
    jh = api.post_document(
        tenant_id=tenant.TenantID,
        transaction_date="2026-06-10",
        reference_type="FACADE_DOC",
        reference_id=1,
        description="قيد عبر الواجهة",
        lines_data=_lines(ar, rev),
        user=owner,
    )
    assert jh.is_posted is True
    assert jh.lines.count() == 2
    assert jh.lines.filter(account=ar, debit=D("100.00")).exists()
    assert jh.lines.filter(account=rev, credit=D("100.00")).exists()


def test_post_document_is_idempotent_on_reference(env):
    tenant, owner, ils, usd, ar, rev = env
    first = api.post_document(
        tenant_id=tenant.TenantID, transaction_date="2026-06-10",
        reference_type="FACADE_DOC", reference_id=7,
        description="أول", lines_data=_lines(ar, rev),
    )
    second = api.post_document(
        tenant_id=tenant.TenantID, transaction_date="2026-06-11",
        reference_type="FACADE_DOC", reference_id=7,
        description="ثانٍ", lines_data=_lines(ar, rev, "999"),
    )
    assert second.id == first.id
    assert JournalHeader.objects.filter(
        reference_type="FACADE_DOC", reference_id=7).count() == 1


def test_post_document_rejects_unbalanced(env):
    tenant, owner, ils, usd, ar, rev = env
    with pytest.raises(DjangoValidationError):
        api.post_document(
            tenant_id=tenant.TenantID, transaction_date="2026-06-10",
            reference_type="FACADE_DOC", reference_id=2,
            description="غير متوازن",
            lines_data=[
                {"account": ar.id, "debit": D("100"), "credit": D("0")},
                {"account": rev.id, "debit": D("0"), "credit": D("90")},
            ],
        )
    assert not JournalHeader.objects.filter(
        reference_type="FACADE_DOC", reference_id=2).exists()


# ── reverse_journal ──────────────────────────────────────────────────────────

def _posted_journal(tenant, ar, rev, ref_id=100, **kwargs):
    return api.post_document(
        tenant_id=tenant.TenantID, transaction_date="2026-06-10",
        reference_type="FACADE_SRC", reference_id=ref_id,
        description="قيد أصلي", lines_data=_lines(ar, rev), **kwargs,
    )


def test_reverse_journal_swaps_debit_credit(env):
    tenant, owner, ils, usd, ar, rev = env
    orig = _posted_journal(tenant, ar, rev)
    reversal = api.reverse_journal(
        orig,
        reference_type="FACADE_SRC_UNPOST",
        reference_id=100,
        description=f"عكس القيد #{orig.id}",
        transaction_date="2026-06-12",
    )
    assert reversal.is_posted is True
    assert reversal.reference_type == "FACADE_SRC_UNPOST"
    assert reversal.lines.filter(account=ar, credit=D("100.00"), debit=D("0.00")).exists()
    assert reversal.lines.filter(account=rev, debit=D("100.00"), credit=D("0.00")).exists()
    # البادئة الافتراضية لوصف السطر تشير للقيد الأصلي
    assert all(
        (l.description or "").startswith(f"عكس قيد #{orig.id}: ")
        for l in reversal.lines.all()
    )
    # الافتراضي لا يمسّ الأصل ولا ينسخ العملة
    orig.refresh_from_db()
    assert orig.is_posted is True
    assert reversal.currency_id is None
    assert D(str(reversal.exchange_rate)) == D("1")


def test_reverse_journal_copy_currency_and_rate(env):
    tenant, owner, ils, usd, ar, rev = env
    orig = _posted_journal(
        tenant, ar, rev, ref_id=101, currency=usd, exchange_rate=D("3.7"))
    reversal = api.reverse_journal(
        orig,
        reference_type="FACADE_SRC_UNPOST", reference_id=101,
        description="عكس بعملة الأصل",
        transaction_date="2026-06-12",
        copy_currency=True,
    )
    assert reversal.currency_id == usd.pk
    assert D(str(reversal.exchange_rate)) == D("3.7")
    line = reversal.lines.get(account=rev)
    assert line.base_debit == D("370.00")  # 100 × 3.7 من سعر رأس القيد


def test_reverse_journal_unpost_original_tags_description(env):
    tenant, owner, ils, usd, ar, rev = env
    orig = _posted_journal(tenant, ar, rev, ref_id=102)
    reversal = api.reverse_journal(
        orig,
        reference_type="FACADE_SRC_UNPOST", reference_id=102,
        description="عكس مع إلغاء ترحيل",
        transaction_date="2026-06-12",
        unpost_original=True,
    )
    orig.refresh_from_db()
    assert orig.is_posted is False
    assert f"[ملغى ترحيل — عكس مرحّل #{reversal.id}]" in orig.description
    # الأصل صار غير مرحّل ⇒ عكس ثانٍ يُرفض
    with pytest.raises(DjangoValidationError):
        api.reverse_journal(
            orig, reference_type="FACADE_SRC_UNPOST", reference_id=102,
            description="عكس ثانٍ", transaction_date="2026-06-12",
        )


def test_reverse_journal_copies_line_metadata(env):
    tenant, owner, ils, usd, ar, rev = env
    partner = Partner.objects.create(
        tenant=tenant, name="شريك عكس", partner_type="Customer")
    orig = api.post_document(
        tenant_id=tenant.TenantID, transaction_date="2026-06-10",
        reference_type="FACADE_SRC", reference_id=103,
        description="قيد بشريك",
        lines_data=[
            {"account": ar.id, "debit": D("50"), "credit": D("0"), "partner": partner.id},
            {"account": rev.id, "debit": D("0"), "credit": D("50")},
        ],
    )
    JournalLine.objects.filter(journal=orig, account=ar).update(project_id=77)
    reversal = api.reverse_journal(
        orig,
        reference_type="FACADE_SRC_UNPOST", reference_id=103,
        description="عكس", transaction_date="2026-06-12",
        line_description_prefix=f"عكس #{orig.id}: ",
        copy_project=True,
    )
    line = reversal.lines.get(account=ar)
    assert line.partner_id == partner.id
    assert line.project_id == 77
    assert line.credit == D("50.00")
    assert (line.description or "").startswith(f"عكس #{orig.id}: ")


def test_reverse_journal_rejects_unposted_and_unbalanced(env):
    tenant, owner, ils, usd, ar, rev = env
    draft = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-10",
        reference_type="FACADE_DRAFT", reference_id=1, is_posted=False,
    )
    with pytest.raises(DjangoValidationError):
        api.reverse_journal(
            draft, reference_type="X", reference_id=1,
            description="عكس مسودة", transaction_date="2026-06-12")

    empty = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-10",
        reference_type="FACADE_EMPTY", reference_id=1, is_posted=True,
    )
    with pytest.raises(DjangoValidationError):
        api.reverse_journal(
            empty, reference_type="X", reference_id=2,
            description="عكس فارغ", transaction_date="2026-06-12")

    unbalanced = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-10",
        reference_type="FACADE_UNBAL", reference_id=1, is_posted=True,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=unbalanced, account=ar, debit=D("100"), credit=D("0"))
    JournalLine.objects.create(
        tenant=tenant, journal=unbalanced, account=rev, debit=D("0"), credit=D("60"))
    with pytest.raises(DjangoValidationError):
        api.reverse_journal(
            unbalanced, reference_type="X", reference_id=3,
            description="عكس غير متوازن", transaction_date="2026-06-12")


# ── purge_journals ───────────────────────────────────────────────────────────

def test_purge_journals_deletes_lines_then_headers(env):
    tenant, owner, ils, usd, ar, rev = env
    target = _posted_journal(tenant, ar, rev, ref_id=200)
    keep = _posted_journal(tenant, ar, rev, ref_id=201)
    deleted = api.purge_journals({target.id})
    assert deleted == 1
    assert not JournalHeader.objects.filter(pk=target.id).exists()
    assert not JournalLine.objects.filter(journal_id=target.id).exists()
    assert JournalHeader.objects.filter(pk=keep.id).exists()
    assert api.purge_journals(set()) == 0


# ── get_account_by_code ──────────────────────────────────────────────────────

def test_get_account_by_code(env):
    tenant, owner, ils, usd, ar, rev = env
    assert api.get_account_by_code(tenant, "1101-F") == ar
    assert api.get_account_by_code(tenant.TenantID, "1101-F") == ar
    assert api.get_account_by_code(tenant, "NO-SUCH") is None
    inactive = Account.objects.create(
        tenant=tenant, code="9999-F", name="معطّل", account_type="Asset", is_active=False)
    assert api.get_account_by_code(tenant, "9999-F") == inactive
    assert api.get_account_by_code(tenant, "9999-F", active_only=True) is None


# ── حسابات الشركاء والقيد الافتتاحي ─────────────────────────────────────────

def test_sync_partner_accounting_links_account_under_canonical_parent(env):
    tenant, owner, ils, usd, ar, rev = env
    broker = Partner.objects.create(
        tenant=tenant, name="مخلّص الواجهة", partner_type="CustomsBroker")
    broker.refresh_from_db()
    # signal الإنشاء ربطه سلفاً — نفكّه لنختبر دالة الواجهة مباشرة
    linked_id = broker.linked_account_id
    assert linked_id is not None
    Partner.objects.filter(pk=broker.pk).update(linked_account=None)
    broker.refresh_from_db()

    api.sync_partner_accounting(broker)
    broker.refresh_from_db()
    assert broker.linked_account_id is not None
    parent = broker.linked_account.parent
    assert parent is not None and parent.code == "2107"  # ذمم المخلصين الجمركيين
    # أعاد ربط نفس الحساب القائم بمطابقة الاسم بدل تكرار حساب جديد
    assert broker.linked_account_id == linked_id


def test_ensure_partner_account_backfills_missing_link(env):
    tenant, owner, ils, usd, ar, rev = env
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد الواجهة", partner_type="Supplier")
    Partner.objects.filter(pk=supplier.pk).update(linked_account=None)
    supplier.refresh_from_db()
    assert supplier.linked_account_id is None

    result = api.ensure_partner_account(supplier)
    assert result.linked_account_id is not None
    assert result.linked_account.parent.code == "2101"
    # شريك مربوط سلفاً يُعاد كما هو بلا حفظ إضافي
    again = api.ensure_partner_account(result)
    assert again.linked_account_id == result.linked_account_id
    assert api.ensure_partner_account(None) is None


def test_create_partner_opening_balance_customer_and_supplier(env):
    tenant, owner, ils, usd, ar, rev = env
    customer = Partner.objects.create(
        tenant=tenant, name="عميل افتتاحي", partner_type="Customer")
    customer.refresh_from_db()
    customer.opening_balance = D("500")
    api.create_partner_opening_balance(customer)

    header = JournalHeader.objects.get(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=customer.id)
    assert header.is_posted is True
    offset = Account.objects.get(tenant=tenant, code="3300")
    assert header.lines.filter(
        account=customer.linked_account, debit=D("500.00"), partner_id=customer.id).exists()
    assert header.lines.filter(account=offset, credit=D("500.00")).exists()

    supplier = Partner.objects.create(
        tenant=tenant, name="مورد افتتاحي", partner_type="Supplier",
        opening_balance=D("300"))
    supplier.refresh_from_db()
    # signal الإنشاء ولّد القيد — عميل دائن على حسابه و3300 مدين
    sheader = JournalHeader.objects.get(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=supplier.id)
    assert sheader.lines.filter(
        account=supplier.linked_account, credit=D("300.00"), partner_id=supplier.id).exists()
    assert sheader.lines.filter(account=offset, debit=D("300.00")).exists()

    # idempotency على مستوى sync: لا قيد افتتاحي ثانٍ لنفس الشريك
    api.sync_partner_accounting(supplier)
    assert JournalHeader.objects.filter(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=supplier.id,
    ).count() == 1


def test_create_partner_opening_balance_is_race_safe_idempotent(env):
    """قرار 2026-08-11: القيد الافتتاحي عبر post_journal — إعادة الاستدعاء
    المباشر (تجاوز فحص exists في sync، كما في سباق متزامن) لا تكرر القيد."""
    tenant, owner, ils, usd, ar, rev = env
    customer = Partner.objects.create(
        tenant=tenant, name="عميل السباق", partner_type="Customer")
    customer.refresh_from_db()
    customer.opening_balance = D("250")
    api.create_partner_opening_balance(customer)
    api.create_partner_opening_balance(customer)
    assert JournalHeader.objects.filter(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=customer.id,
    ).count() == 1


def test_create_partner_opening_balance_requires_open_period(env):
    """قرار 2026-08-11: تاريخ رصيد بلا فترة مالية مفتوحة ⇒ لا قيد (يُسجَّل
    الخطأ ولا يسقط حفظ الشريك)؛ تصحيح التاريخ وإعادة الحفظ يُنشئ القيد."""
    tenant, owner, ils, usd, ar, rev = env
    partner = Partner.objects.create(
        tenant=tenant, name="مورد خارج الفترة", partner_type="Supplier",
        opening_balance=D("400"), opening_balance_date=datetime.date(2020, 1, 15))
    partner.refresh_from_db()
    assert partner.linked_account_id is not None  # الحساب يُربط رغم فشل القيد
    assert not JournalHeader.objects.filter(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=partner.id,
    ).exists()

    partner.opening_balance_date = datetime.date(2026, 5, 1)
    partner.save()  # signal ⇒ sync ⇒ المحاولة تنجح الآن
    header = JournalHeader.objects.get(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=partner.id)
    assert header.is_posted is True
    assert str(header.transaction_date) == "2026-05-01"


# ── T119-2: الرصيد الافتتاحي الدائن، وتوحيد التاريخ ──────────────────────────

def test_create_partner_opening_balance_supports_credit_side(env):
    """رصيد سالب = عميل دفع مقدّماً أو مورّد دفعنا له مقدّماً — يقلب طرفَي القيد.

    العميل السالب: دائن على حسابه ومدين على 3300 (نحن مدينون له بما دفع)،
    والمورّد السالب مرآته. لا مبلغ سالب في أي سطر — الاتجاه يُعبَّر عنه بالطرف.
    """
    tenant, owner, ils, usd, ar, rev = env
    prepaid_customer = Partner.objects.create(
        tenant=tenant, name="عميل دفع مقدّماً", partner_type="Customer",
        opening_balance=D("-500"))
    prepaid_customer.refresh_from_db()

    header = JournalHeader.objects.get(
        tenant=tenant, reference_type="PARTNER_OPENING",
        reference_id=prepaid_customer.id)
    offset = Account.objects.get(tenant=tenant, code="3300")
    assert header.lines.filter(
        account=prepaid_customer.linked_account, credit=D("500.00"),
        partner_id=prepaid_customer.id).exists()
    assert header.lines.filter(account=offset, debit=D("500.00")).exists()

    advanced_supplier = Partner.objects.create(
        tenant=tenant, name="مورد مدفوع سلفاً", partner_type="Supplier",
        opening_balance=D("-300"))
    advanced_supplier.refresh_from_db()

    sheader = JournalHeader.objects.get(
        tenant=tenant, reference_type="PARTNER_OPENING",
        reference_id=advanced_supplier.id)
    assert sheader.lines.filter(
        account=advanced_supplier.linked_account, debit=D("300.00"),
        partner_id=advanced_supplier.id).exists()
    assert sheader.lines.filter(account=offset, credit=D("300.00")).exists()

    # لا سطر بمبلغ سالب في أيٍّ من القيدين
    assert not JournalLine.objects.filter(
        journal__in=[header, sheader],
    ).filter(Q(debit__lt=0) | Q(credit__lt=0)).exists()


def test_partner_opening_balance_zero_creates_no_journal(env):
    """صفر يبقى «لا قيد افتتاحي أصلاً» — لا قيد بمبلغ صفر ولا سطر يتيم."""
    tenant, owner, ils, usd, ar, rev = env
    partner = Partner.objects.create(
        tenant=tenant, name="طرف بلا رصيد", partner_type="Customer",
        opening_balance=D("0"))
    partner.refresh_from_db()
    assert partner.linked_account_id is not None
    assert not JournalHeader.objects.filter(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=partner.id,
    ).exists()


def test_partner_opening_balance_date_defaults_to_company_entry_date(env):
    """طرفٌ بلا تاريخ رصيد يتبع تاريخ القيد الافتتاحي للشركة لا تاريخ اليوم.

    كل أرجل الافتتاح على تاريخ واحد، والتاريخ المستعمل يُثبَّت على الطرف كي
    يقرأ المستخدم في بطاقته نفس تاريخ قيده.
    """
    tenant, owner, ils, usd, ar, rev = env
    OpeningBalance.objects.create(tenant=tenant, start_date=datetime.date(2026, 3, 1))

    partner = Partner.objects.create(
        tenant=tenant, name="عميل بلا تاريخ", partner_type="Customer",
        opening_balance=D("700"))
    partner.refresh_from_db()

    header = JournalHeader.objects.get(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=partner.id)
    assert header.transaction_date == datetime.date(2026, 2, 28)
    assert partner.opening_balance_date == datetime.date(2026, 2, 28)


def test_partner_opening_balance_keeps_its_own_date_when_given(env):
    """تاريخٌ مُدخل صراحةً لا يُداس بتاريخ الشركة — الإدخال اليدوي أعلى."""
    tenant, owner, ils, usd, ar, rev = env
    OpeningBalance.objects.create(tenant=tenant, start_date=datetime.date(2026, 3, 1))

    partner = Partner.objects.create(
        tenant=tenant, name="عميل بتاريخه", partner_type="Customer",
        opening_balance=D("200"), opening_balance_date=datetime.date(2026, 5, 1))
    partner.refresh_from_db()

    header = JournalHeader.objects.get(
        tenant=tenant, reference_type="PARTNER_OPENING", reference_id=partner.id)
    assert header.transaction_date == datetime.date(2026, 5, 1)
    assert partner.opening_balance_date == datetime.date(2026, 5, 1)
