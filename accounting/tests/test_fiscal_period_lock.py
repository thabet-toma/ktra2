"""A2 (THA-196 · يشمل THA-184 وTHA-185) — قفل الشهر المالي.

يثبت أن الشهر المُقفَل يُعبَّر عنه، ويُرفض فعلاً من كل مسار كتابة، وأن كل
استثناء منه مُسجَّل:

  1. `create_fiscal_year` بالتفصيل الشهري يُنشئ 12 فترة (`2026-01` … `2026-12`).
  2. `post_journal` بتاريخ داخل شهر مُقفَل يُرفض برسالة عربية واضحة.
  3. `unpost_document` لمستند مؤرَّخ داخل شهر مُقفَل يُرفض ولا يُعكَس شيء
     (THA-184 — الثغرة: كان يحذف القيود ويعيد المخزون بلا أي حارس فترة).
  4. إنشاء فترة متداخلة مع فترة قائمة يُرفض بـ400 (THA-185).
  5. `close/` يُرجع 409 إن بقيت قيود غير مرحّلة، إلا بـ`force=true` — والإغلاق
     القسري يُكتب في سجل التدقيق.
  6. `reopen/` يشترط سبباً (400 بدونه)، والسبب يُحفظ في سجل التدقيق — هذه هي
     «صلاحية الاستثناء المسجَّلة».
  7. THA-197: مسارات CRUD العادية على الفترة لا تلتفّ حول القفل — صلاحية
     `accounting.period.manage` مطلوبة، والفترة المُقفَلة لا تُعدَّل ولا تُحذف،
     وكل تعديل أو حذف يُكتب في سجل التدقيق.
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.test import APIClient

from accounting.models import (
    AccountingAuditLog,
    Account,
    FiscalPeriod,
    JournalHeader,
)
from accounting.services import create_fiscal_year, post_journal, unpost_document
from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="period-lock", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة قفل الفترة", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-P", name="ذمم", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-P", name="إيراد", account_type="Revenue", is_active=True)
    product = Product.objects.create(
        tenant=tenant, sku="P-1", name_ar="منتج", quantity_on_hand=Decimal("0"),
        avg_cost=Decimal("0"))
    return tenant, owner, ar, rev, product


def _client(owner, tenant):
    client = APIClient()
    client.force_authenticate(user=owner)
    return client, {"HTTP_X_TENANT_ID": str(tenant.TenantID)}


def _close_month(tenant, name):
    period = FiscalPeriod.objects.get(tenant=tenant, name=name)
    period.status = "Closed"
    period.is_closed = True
    period.save(update_fields=["status", "is_closed"])
    return period


def _post_simple_journal(tenant, ar, rev, ref_type, ref_id, date="2026-06-11"):
    return post_journal(
        tenant_id=tenant.TenantID,
        transaction_date=date,
        reference_type=ref_type,
        reference_id=ref_id,
        description=f"{ref_type} {ref_id}",
        lines_data=[
            {"account": ar.id, "debit": Decimal("100"), "credit": Decimal("0")},
            {"account": rev.id, "debit": Decimal("0"), "credit": Decimal("100")},
        ],
    )


# ── 1) الإنشاء الشهري ──────────────────────────────────────────────────────

def test_create_fiscal_year_builds_twelve_months(env):
    tenant, *_ = env
    periods = FiscalPeriod.objects.filter(tenant=tenant).order_by("start_date")
    assert periods.count() == 12
    assert [p.name for p in periods] == [f"2026-{m:02d}" for m in range(1, 13)]
    assert str(periods.first().start_date) == "2026-01-01"
    assert str(periods.last().end_date) == "2026-12-31"
    # وحدة فبراير تنتهي في آخر أيامه فعلاً (لا يوم زائد ولا ناقص).
    assert str(periods[1].end_date) == "2026-02-28"
    # استدعاء ثانٍ لنفس السنة لا يُكرّر ولا يفشل (idempotent).
    again = create_fiscal_year(tenant, 2026)
    assert len(again) == 12
    assert FiscalPeriod.objects.filter(tenant=tenant).count() == 12


# ─────────────────────────────────────────────────────────────────────────────
# #213-أ (تكملة) — السنة المالية تبدأ من أيّ تاريخ، لا من كانون الثاني وحده
#
# طلب المالك: «بدي ابلش من أي تاريخ، مش لازم أول السنة؛ الديفولت كانون الثاني
# وبكون الخيار معبّى، وهو قبل الإنشاء بقدر يغيّره». وهو خيار قياسي في Odoo
# وXero وZoho Books — سنةٌ ماليةٌ تموزية أو نيسانية ليست حالةً شاذّة.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_july_start_makes_twelve_contiguous_periods(env):
    """اثنتا عشرة فترةً من تموز إلى حزيران — بلا فجوةٍ ولا تداخل."""
    tenant, *_ = env
    periods = create_fiscal_year(tenant, start="2040-07-01")

    assert len(periods) == 12
    assert periods[0].start_date == datetime.date(2040, 7, 1)
    assert periods[-1].end_date == datetime.date(2041, 6, 30)
    for earlier, later in zip(periods, periods[1:]):
        assert later.start_date == earlier.end_date + datetime.timedelta(days=1)


def test_a_january_start_is_byte_for_byte_the_old_year_call(env):
    """المسارُ القديم حالةٌ خاصّةٌ من الجديد — لا سلوكٌ ثانٍ بجانبه.

    لو انزاح يومٌ واحدٌ هنا لتغيّرت فتراتُ كلّ شركةٍ قائمةٍ في المستودع.
    """
    tenant, *_ = env
    by_year = [(p.name, p.start_date, p.end_date) for p in create_fiscal_year(tenant, 2041)]
    # idempotent: النداء الثاني بالمدى نفسه يعيد الصفوف ذاتها لا صفوفاً جديدة.
    by_start = [
        (p.name, p.start_date, p.end_date)
        for p in create_fiscal_year(tenant, start="2041-01-01")
    ]

    assert by_year == by_start
    assert by_year[0] == ("2041-01", datetime.date(2041, 1, 1), datetime.date(2041, 1, 31))
    assert by_year[-1] == ("2041-12", datetime.date(2041, 12, 1), datetime.date(2041, 12, 31))


def test_a_yearly_period_off_january_is_named_across_both_years(env):
    """`FY 2042/2043` — الاسمُ يقول أين تقع السنةُ حين لا تطابق التقويمية."""
    tenant, *_ = env
    periods = create_fiscal_year(tenant, start="2042-07-01", granularity="yearly")

    assert len(periods) == 1
    assert periods[0].name == "FY 2042/2043"
    assert periods[0].start_date == datetime.date(2042, 7, 1)
    assert periods[0].end_date == datetime.date(2043, 6, 30)


def test_a_start_on_the_thirty_first_does_not_drift(env):
    """الإزاحةُ من المرساة لا من الفترة السابقة — وإلا انزلق اليومُ شهراً بشهر."""
    tenant, *_ = env
    periods = create_fiscal_year(tenant, start="2043-01-31")

    assert periods[0].start_date == datetime.date(2043, 1, 31)
    assert periods[1].start_date == datetime.date(2043, 2, 28)
    # لو حُسبت من شباط لصار آذارُ في 28، ولضاعت ثلاثةُ أيامٍ من السنة كلّها.
    assert periods[2].start_date == datetime.date(2043, 3, 31)
    assert periods[-1].end_date == datetime.date(2044, 1, 30)


def test_a_period_starting_mid_month_is_not_named_after_that_month(env):
    """مدىً من 31 كانون الثاني إلى 27 شباط أكثرُ أيّامه في شباط.

    تسميتُه «2043-01» تكذب على من يقرأ القائمة، فالاسمُ يصير تاريخَ بدئه.
    """
    tenant, *_ = env
    periods = create_fiscal_year(tenant, start="2043-01-31")

    assert periods[0].name == "2043-01-31"
    assert periods[1].name == "2043-02-28"
    # وأوّلُ الشهر يبقى `YYYY-MM` حرفاً بحرف — أسماءُ الفترات القائمة لا تتغيّر.
    assert create_fiscal_year(tenant, start="2046-01-01")[0].name == "2046-01"


def test_a_year_and_a_start_together_are_refused(env):
    """أحدُهما لا كلاهما — وإلّا صمت أحدُ الوسيطين ولا يدري المستدعي أيُّهما."""
    tenant, *_ = env
    with pytest.raises(DjangoValidationError):
        create_fiscal_year(tenant, 2044, start="2044-07-01")
    with pytest.raises(DjangoValidationError):
        create_fiscal_year(tenant)


def test_an_impossible_start_is_a_message_not_a_server_error(env):
    """`parse_date` **ترفع** على 2045-02-31 ولا تعيد `None`."""
    tenant, *_ = env
    with pytest.raises(DjangoValidationError):
        create_fiscal_year(tenant, start="2045-02-31")
    with pytest.raises(DjangoValidationError):
        create_fiscal_year(tenant, start="ليس تاريخاً")


def test_create_fiscal_year_yearly_granularity_still_available(env):
    tenant, *_ = env
    periods = create_fiscal_year(tenant, 2027, granularity="yearly")
    assert len(periods) == 1
    assert periods[0].name == "FY 2027"
    assert str(periods[0].start_date) == "2027-01-01"
    assert str(periods[0].end_date) == "2027-12-31"


# ── 2) t1: الترحيل داخل شهر مُقفَل ─────────────────────────────────────────

def test_post_journal_into_a_closed_month_is_refused(env):
    """اختبار المالك الأول: شهر مُقفَل يرفض أي قيد جديد برسالة واضحة."""
    tenant, owner, ar, rev, _product = env
    _close_month(tenant, "2026-06")

    with pytest.raises(DjangoValidationError) as exc:
        _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 3001, date="2026-06-11")

    message = str(exc.value)
    assert "2026-06" in message
    assert "مغلقة" in message
    assert not JournalHeader.objects.filter(
        tenant_id=tenant.TenantID, reference_id=3001).exists()
    # الشهر المجاور المفتوح ما زال يقبل — القفل شهريّ لا سنويّ.
    assert _post_simple_journal(
        tenant, ar, rev, "SALES_INVOICE", 3002, date="2026-07-11").is_posted


# ── 3) t4 (THA-184): إلغاء الترحيل داخل شهر مُقفَل ────────────────────────

def test_unpost_inside_a_closed_month_is_refused_and_reverses_nothing(env):
    """THA-184: التراجع عن الترحيل تعديلٌ على الشهر المُقفَل — يُرفض كالترحيل.

    الحالة قبل الإصلاح: `unpost_document` لم يستدعِ أي حارس فترة، فكان يحذف
    قيود مستند مؤرَّخ داخل شهر مُقفَل ويعيد حركات مخزونه بصمت.
    """
    tenant, owner, ar, rev, product = env
    journal = _post_simple_journal(
        tenant, ar, rev, "PURCHASE_INVOICE", 4001, date="2026-06-11")
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("10"),
        unit_cost=Decimal("5"), reference_type="PURCHASE_INVOICE", reference_id=4001,
        movement_date="2026-06-11", tenant=tenant)
    _close_month(tenant, "2026-06")

    with pytest.raises(DjangoValidationError) as exc:
        unpost_document(
            tenant_id=tenant.TenantID,
            reference_id=4001,
            journal_reference_types=["PURCHASE_INVOICE"],
            stock_reference_types=["PURCHASE_INVOICE"],
            user=owner,
            document_label="فاتورة شراء #4001",
        )

    message = str(exc.value)
    assert "2026-06" in message
    assert "مغلقة" in message
    # لا شيء عُكِس: القيد وأسطره وحركة المخزون والرصيد كما كانت.
    assert JournalHeader.objects.filter(pk=journal.id).exists()
    assert StockMovement.objects.filter(
        tenant=tenant, reference_type="PURCHASE_INVOICE", reference_id=4001).count() == 1
    product.refresh_from_db()
    assert product.quantity_on_hand == Decimal("10")


def test_unpost_stays_allowed_while_the_month_is_open(env):
    """الحارس يمنع المُقفَل وحده — الشهر المفتوح يتراجع كما كان."""
    tenant, owner, ar, rev, _product = env
    journal = _post_simple_journal(
        tenant, ar, rev, "PURCHASE_INVOICE", 4002, date="2026-06-11")

    result = unpost_document(
        tenant_id=tenant.TenantID,
        reference_id=4002,
        journal_reference_types=["PURCHASE_INVOICE"],
        user=owner,
    )

    assert result["journals_deleted"] == 1
    assert not JournalHeader.objects.filter(pk=journal.id).exists()


# ── 4) t3 (THA-185): منع التداخل ──────────────────────────────────────────

def test_creating_an_overlapping_period_is_refused(env):
    tenant, owner, *_ = env
    client, headers = _client(owner, tenant)

    res = client.post(
        "/api/accounting/fiscal-periods/",
        {"name": "ربع أول", "start_date": "2026-02-15", "end_date": "2026-04-15"},
        format="json", **headers)

    assert res.status_code == 400, res.content
    assert "تتداخل" in str(res.content, "utf-8")
    assert FiscalPeriod.objects.filter(tenant=tenant).count() == 12


def test_creating_a_period_in_a_free_range_is_allowed(env):
    tenant, owner, *_ = env
    client, headers = _client(owner, tenant)

    res = client.post(
        "/api/accounting/fiscal-periods/",
        {"name": "2025-12", "start_date": "2025-12-01", "end_date": "2025-12-31"},
        format="json", **headers)

    assert res.status_code == 201, res.content
    assert FiscalPeriod.objects.filter(tenant=tenant, name="2025-12").exists()


def test_overlap_is_scoped_to_the_tenant(env):
    """فترة شركة أخرى ليست تداخلاً — عزل الشركات يسبق كل قاعدة."""
    tenant, owner, *_ = env
    other_owner = User.objects.create_user(username="period-lock-2", password="x")
    # #213-أ: كل شركة تولد بفترات سنة، فلو وُلدت هذه بـ2026 لصار 2026-06 موجوداً
    # عندها فعلاً ورُدّ الطلبُ لتكرارٍ داخل الشركة — لا لتداخلٍ عبر الشركات، وهو
    # ما يقيسه هذا الاختبار. سنةٌ أخرى تُبقي المدى حرّاً عندها ومشغولاً عند
    # جارتها، فيبقى الرفضُ المحتمل رفضاً عابراً للشركات لا غير.
    other = create_company("شركة أخرى", other_owner, fiscal_start="2030-01-01")
    client, headers = _client(other_owner, other)

    res = client.post(
        "/api/accounting/fiscal-periods/",
        {"name": "2026-06", "start_date": "2026-06-01", "end_date": "2026-06-30"},
        format="json", **headers)

    assert res.status_code == 201, res.content


def test_create_year_action_refuses_to_overlap_an_existing_year(env):
    tenant, owner, *_ = env
    client, headers = _client(owner, tenant)

    res = client.post(
        "/api/accounting/fiscal-periods/create-year/",
        {"year": 2026, "granularity": "yearly"}, format="json", **headers)

    assert res.status_code == 400, res.content
    assert "تتداخل" in str(res.content, "utf-8")
    assert FiscalPeriod.objects.filter(tenant=tenant).count() == 12


def test_create_year_action_defaults_to_monthly(env):
    tenant, owner, *_ = env
    client, headers = _client(owner, tenant)

    res = client.post(
        "/api/accounting/fiscal-periods/create-year/",
        {"year": 2028}, format="json", **headers)

    assert res.status_code == 201, res.content
    assert len(res.json()) == 12
    assert FiscalPeriod.objects.filter(tenant=tenant, name="2028-01").exists()


def test_create_year_action_accepts_an_explicit_start(env):
    """#213-أ: بلا `start` كانت الشركةُ التي سنتُها تموزيّةٌ عاجزةً عن سنتها
    الثانية — طلبُ السنة يبني كانونَ الثاني فيتقاطع مع نصف سنتها القائمة ويُردّ.
    """
    tenant, owner, *_ = env
    client, headers = _client(owner, tenant)

    res = client.post(
        "/api/accounting/fiscal-periods/create-year/",
        {"start": "2027-07-01"}, format="json", **headers)

    assert res.status_code == 201, res.content
    assert len(res.json()) == 12
    assert FiscalPeriod.objects.filter(
        tenant=tenant, name="2027-07", start_date=datetime.date(2027, 7, 1),
    ).exists()
    assert FiscalPeriod.objects.filter(
        tenant=tenant, end_date=datetime.date(2028, 6, 30),
    ).exists()


def test_create_year_action_refuses_a_request_naming_neither(env):
    """لا سنةَ ولا تاريخ: رسالةٌ لا إنشاءٌ صامتٌ لسنةٍ لم يطلبها أحد."""
    tenant, owner, *_ = env
    client, headers = _client(owner, tenant)

    res = client.post(
        "/api/accounting/fiscal-periods/create-year/", {}, format="json", **headers)

    assert res.status_code == 400, res.content
    assert FiscalPeriod.objects.filter(tenant=tenant).count() == 12


# ── 5) الإغلاق مع قيود غير مرحّلة ─────────────────────────────────────────

def test_close_is_refused_while_unposted_journals_remain(env):
    tenant, owner, ar, rev, _product = env
    JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-05", description="مسودة",
        is_posted=False, reference_type="MANUAL", reference_id=None)
    period = FiscalPeriod.objects.get(tenant=tenant, name="2026-06")
    client, headers = _client(owner, tenant)

    res = client.post(
        f"/api/accounting/fiscal-periods/{period.id}/close/", {}, format="json", **headers)

    assert res.status_code == 409, res.content
    assert "1" in str(res.content, "utf-8")
    period.refresh_from_db()
    assert period.is_closed is False


def test_forced_close_succeeds_and_is_written_to_the_audit_log(env):
    tenant, owner, ar, rev, _product = env
    JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-05", description="مسودة",
        is_posted=False, reference_type="MANUAL", reference_id=None)
    period = FiscalPeriod.objects.get(tenant=tenant, name="2026-06")
    client, headers = _client(owner, tenant)

    res = client.post(
        f"/api/accounting/fiscal-periods/{period.id}/close/",
        {"force": True}, format="json", **headers)

    assert res.status_code == 200, res.content
    period.refresh_from_db()
    assert period.is_closed is True
    entry = AccountingAuditLog.objects.filter(
        tenant=tenant, model_name="FiscalPeriod", object_id=period.id,
    ).order_by("-id").first()
    assert entry is not None
    assert "forced" in entry.change_details.lower()


# ── 6) t2: إعادة الفتح تشترط سبباً مسجَّلاً ────────────────────────────────

def test_reopen_without_a_reason_is_refused(env):
    """اختبار المالك الثاني: الاستثناء لا يمرّ بلا سبب مكتوب."""
    tenant, owner, *_ = env
    period = _close_month(tenant, "2026-06")
    client, headers = _client(owner, tenant)

    res = client.post(
        f"/api/accounting/fiscal-periods/{period.id}/reopen/", {}, format="json", **headers)

    assert res.status_code == 400, res.content
    period.refresh_from_db()
    assert period.is_closed is True

    blank = client.post(
        f"/api/accounting/fiscal-periods/{period.id}/reopen/",
        {"reason": "   "}, format="json", **headers)
    assert blank.status_code == 400, blank.content


def test_reopen_with_a_reason_records_it_in_the_audit_log(env):
    tenant, owner, *_ = env
    period = _close_month(tenant, "2026-06")
    client, headers = _client(owner, tenant)
    reason = "تصحيح فاتورة مورّد وردت متأخرة"

    res = client.post(
        f"/api/accounting/fiscal-periods/{period.id}/reopen/",
        {"reason": reason}, format="json", **headers)

    assert res.status_code == 200, res.content
    period.refresh_from_db()
    assert period.is_closed is False
    entry = AccountingAuditLog.objects.filter(
        tenant=tenant, model_name="FiscalPeriod", object_id=period.id, action="UPDATE",
    ).order_by("-id").first()
    assert entry is not None
    assert reason in entry.change_details
    assert entry.user_id == owner.id


# ── 7) THA-197: CRUD الفترة لا يلتفّ حول القفل ────────────────────────────

@pytest.fixture
def roles(env):
    """موظف مبيعات ومحاسب داخل نفس الشركة — نمط تثبيت الأدوار في
    `test_accounting_permissions.py`."""
    tenant, *_ = env
    seller = User.objects.create_user(username="period-seller", password="x")
    keeper = User.objects.create_user(username="period-keeper", password="x")
    UserCompanyMembership.objects.create(user=seller, tenant=tenant, role="sales")
    UserCompanyMembership.objects.create(user=keeper, tenant=tenant, role="accountant")
    return seller, keeper


def _audit_rows(tenant, period_id=None):
    qs = AccountingAuditLog.objects.filter(tenant=tenant, model_name="FiscalPeriod")
    if period_id is not None:
        qs = qs.filter(object_id=period_id)
    return qs


def test_sales_employee_cannot_patch_a_period(env, roles):
    """الثغرة الأصلية: PATCH كان يمرّ بـ200 لأي عضو."""
    tenant, *_ = env
    seller, _keeper = roles
    period = FiscalPeriod.objects.get(tenant=tenant, name="2026-06")
    client, headers = _client(seller, tenant)

    res = client.patch(
        f"/api/accounting/fiscal-periods/{period.id}/",
        {"name": "شهر المبيعات"}, format="json", **headers)

    assert res.status_code == 403, res.content
    period.refresh_from_db()
    assert period.name == "2026-06"


def test_sales_employee_cannot_delete_a_period(env, roles):
    """الثغرة الأصلية: DELETE كان يمرّ بـ204 لأي عضو."""
    tenant, *_ = env
    seller, _keeper = roles
    period = FiscalPeriod.objects.get(tenant=tenant, name="2026-06")
    client, headers = _client(seller, tenant)

    res = client.delete(f"/api/accounting/fiscal-periods/{period.id}/", **headers)

    assert res.status_code == 403, res.content
    assert FiscalPeriod.objects.filter(pk=period.pk).exists()


def test_sales_employee_cannot_create_a_period(env, roles):
    tenant, *_ = env
    seller, _keeper = roles
    client, headers = _client(seller, tenant)

    res = client.post(
        "/api/accounting/fiscal-periods/",
        {"name": "2025-12", "start_date": "2025-12-01", "end_date": "2025-12-31"},
        format="json", **headers)

    assert res.status_code == 403, res.content
    assert not FiscalPeriod.objects.filter(tenant=tenant, name="2025-12").exists()


def test_patching_a_closed_period_is_refused_and_it_stays_closed(env, roles):
    """المُقفَل لا يُفتح إلا عبر `reopen/` بسبب مسجَّل — لا عبر تعديل عادي."""
    tenant, *_ = env
    _seller, keeper = roles
    period = _close_month(tenant, "2026-06")
    client, headers = _client(keeper, tenant)

    res = client.patch(
        f"/api/accounting/fiscal-periods/{period.id}/",
        {"is_closed": False, "status": "Open"}, format="json", **headers)

    assert res.status_code == 400, res.content
    period.refresh_from_db()
    assert period.is_closed is True
    assert period.status == "Closed"


def test_patching_a_closed_period_cannot_shift_its_boundaries(env, roles):
    """الباب الجانبي: تحريك التواريخ يفتح أياماً داخل شهر مُقفَل بلا سبب مسجَّل."""
    tenant, *_ = env
    _seller, keeper = roles
    period = _close_month(tenant, "2026-06")
    client, headers = _client(keeper, tenant)

    res = client.patch(
        f"/api/accounting/fiscal-periods/{period.id}/",
        {"end_date": "2026-06-15"}, format="json", **headers)

    assert res.status_code == 400, res.content
    period.refresh_from_db()
    assert str(period.end_date) == "2026-06-30"


def test_renaming_an_open_period_succeeds_and_is_audit_logged(env, roles):
    tenant, *_ = env
    _seller, keeper = roles
    period = FiscalPeriod.objects.get(tenant=tenant, name="2026-09")
    client, headers = _client(keeper, tenant)
    before = _audit_rows(tenant, period.id).count()

    res = client.patch(
        f"/api/accounting/fiscal-periods/{period.id}/",
        {"name": "أيلول 2026"}, format="json", **headers)

    assert res.status_code == 200, res.content
    period.refresh_from_db()
    assert period.name == "أيلول 2026"
    assert _audit_rows(tenant, period.id).count() == before + 1
    entry = _audit_rows(tenant, period.id).order_by("-id").first()
    assert entry.action == "UPDATE"
    assert entry.user_id == keeper.id


def test_deleting_a_closed_period_is_refused(env, roles):
    """الحذف ثم إعادة الإنشاء مفتوحاً = إعادة فتح بلا سجل."""
    tenant, *_ = env
    _seller, keeper = roles
    period = _close_month(tenant, "2026-06")
    client, headers = _client(keeper, tenant)

    res = client.delete(f"/api/accounting/fiscal-periods/{period.id}/", **headers)

    assert res.status_code == 400, res.content
    assert FiscalPeriod.objects.filter(pk=period.pk).exists()


def test_deleting_a_period_holding_posted_journals_is_refused(env, roles):
    """حذف فترة عليها قيود يترك تاريخاً بلا فترة تغطّيه — فيُشلّ المدى كلّه."""
    tenant, _owner, ar, rev, _product = env
    _seller, keeper = roles
    _post_simple_journal(tenant, ar, rev, "SALES_INVOICE", 5001, date="2026-06-11")
    period = FiscalPeriod.objects.get(tenant=tenant, name="2026-06")
    client, headers = _client(keeper, tenant)

    res = client.delete(f"/api/accounting/fiscal-periods/{period.id}/", **headers)

    assert res.status_code == 400, res.content
    assert FiscalPeriod.objects.filter(pk=period.pk).exists()


def test_deleting_an_open_journal_free_period_succeeds_and_is_audit_logged(env, roles):
    """حالة الخطأ المطبعي: فترة أُنشئت بتاريخ خاطئ تبقى قابلة للحذف."""
    tenant, *_ = env
    _seller, keeper = roles
    period = FiscalPeriod.objects.get(tenant=tenant, name="2026-09")
    client, headers = _client(keeper, tenant)
    before = _audit_rows(tenant, period.id).count()

    res = client.delete(f"/api/accounting/fiscal-periods/{period.id}/", **headers)

    assert res.status_code == 204, res.content
    assert not FiscalPeriod.objects.filter(pk=period.pk).exists()
    assert _audit_rows(tenant, period.id).count() == before + 1
    entry = _audit_rows(tenant, period.id).order_by("-id").first()
    assert entry.action == "DELETE"
    assert entry.user_id == keeper.id
