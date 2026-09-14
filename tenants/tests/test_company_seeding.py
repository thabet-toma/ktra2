"""task11 M5 — guarantees for new-company bootstrapping (create_company):

  - COA seeded with the standard professional accounts (not empty, not copied)
  - TenantBooks seeded (10 books per document type)
  - Items / Partners / Sales invoices start completely EMPTY
  - Creator gets a manager membership; TenantSettings row exists
  - Data of existing companies is not touched
"""
import io

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account, FiscalPeriod
from accounting.services import post_journal
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Tenant, TenantBook, TenantSettings, UserCompanyMembership
from tenants.services import COA_DATA, create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def creator():
    return User.objects.create_user(username="founder", password="x")


def test_new_company_coa_seeded_standard(creator):
    tenant = create_company("شركة الاختبار", creator)

    accounts = Account.objects.filter(tenant=tenant)
    assert accounts.count() == len(COA_DATA)

    # Roots exist with correct types
    roots = {a.code: a for a in accounts.filter(parent__isnull=True)}
    assert set(roots.keys()) == {"1", "2", "3", "4", "5"}
    assert roots["1"].account_type == "Asset"
    assert roots["4"].account_type == "Revenue"

    # Hierarchy is wired (e.g. 1101 under 11 under 1)
    cash = accounts.get(code="1101")
    assert cash.parent.code == "11"
    assert cash.parent.parent.code == "1"


def test_new_company_business_data_empty(creator):
    # Pre-existing company with data must not leak into the new company
    old = create_company("الشركة القديمة", creator)
    Partner.objects.create(tenant=old, name="عميل قديم", partner_type="Customer")
    Product.objects.create(tenant=old, sku="OLD-1", name_ar="منتج قديم")

    tenant = create_company("الشركة الجديدة", creator)

    assert Product.objects.filter(tenant=tenant).count() == 0
    assert Partner.objects.filter(tenant=tenant).count() == 0
    assert SalesInvoice.objects.filter(tenant=tenant).count() == 0
    # Old company untouched
    assert Partner.objects.filter(tenant=old).count() == 1
    assert Product.objects.filter(tenant=old).count() == 1


def test_new_company_books_membership_settings(creator):
    tenant = create_company("شركة الدفاتر", creator)

    # 10 books per document type
    per_type = TenantBook.objects.filter(tenant=tenant).count()
    assert per_type == len(TenantBook.DOCUMENT_TYPES) * 10
    assert not TenantBook.objects.filter(tenant=tenant).exclude(last_used_number=0).exists()

    membership = UserCompanyMembership.objects.get(user=creator, tenant=tenant)
    assert membership.role == "manager"

    assert TenantSettings.objects.filter(tenant=tenant).exists()


def test_create_company_rejects_blank_name(creator):
    with pytest.raises(ValidationError):
        create_company("   ", creator)
    assert Tenant.objects.count() == 0


# ─────────────────────────────────────────────────────────────────────────────
# #213-أ — السنة المالية تولد مع الشركة
#
# ‏`create_fiscal_year` موجودة ومختبَرة منذ زمن، ولم يكن لها **مستدعٍ واحد في
# كود الإنتاج**: كل مستدعيها اختبارات. فكل شركة تُنشأ من الواجهة تولد بلا فترة
# مالية، ولا شيء يُظهر ذلك حتى يرحّل صاحبها أول فاتورة فيُردّ بـ«لا توجد فترة
# مالية مفتوحة». العطب لم يكن في الترحيل ولا في الفترات — كان في أن أحداً لم
# ينادِ الدالة.
# ─────────────────────────────────────────────────────────────────────────────


def test_a_new_company_is_born_with_periods_covering_today(creator):
    tenant = create_company("شركة لها فترات", creator)

    today = timezone.localdate()
    covering = FiscalPeriod.objects.filter(
        tenant=tenant, start_date__lte=today, end_date__gte=today,
        status="Open", is_closed=False,
    )
    assert covering.count() == 1, list(FiscalPeriod.objects.filter(tenant=tenant))
    assert FiscalPeriod.objects.filter(tenant=tenant).count() == 12


def test_the_first_journal_of_a_new_company_posts_on_the_day_it_was_created(creator):
    """الرحلة التي كانت تنكسر — ولا تُقاس بعدّ صفوفٍ بل بترحيلٍ فعليّ ينجح."""
    tenant = create_company("شركة ترحّل يوم إنشائها", creator)
    cash = Account.objects.get(tenant=tenant, code="1101")
    revenue = Account.objects.get(tenant=tenant, code="4101")

    header = post_journal(
        tenant_id=tenant.pk,
        transaction_date=timezone.localdate(),
        reference_type="test_first_post",
        reference_id=1,
        description="أول قيد في شركة جديدة",
        lines_data=[
            {"account": cash.pk, "debit": "100.00", "credit": "0.00"},
            {"account": revenue.pk, "debit": "0.00", "credit": "100.00"},
        ],
        user=creator,
    )
    assert header.is_posted is True


def test_an_explicit_year_is_honoured_and_the_current_one_is_not_seeded(creator):
    tenant = create_company("شركة بسنة صريحة", creator, fiscal_year=2030)

    years = {p.start_date.year for p in FiscalPeriod.objects.filter(tenant=tenant)}
    assert years == {2030}


def test_yearly_granularity_makes_one_period_not_twelve(creator):
    tenant = create_company(
        "شركة بفترة سنوية", creator, fiscal_year=2031, fiscal_granularity="yearly")

    periods = list(FiscalPeriod.objects.filter(tenant=tenant))
    assert len(periods) == 1
    assert periods[0].name == "FY 2031"


def test_a_nonsense_year_is_refused_and_no_company_is_left_behind(creator):
    """الرفض قبل فتح المعاملة — شركةٌ نصفُ مزروعةٍ أسوأ من شركةٍ لم تُنشأ."""
    before = Tenant.objects.count()
    with pytest.raises(ValidationError):
        create_company("شركة بسنة سخيفة", creator, fiscal_year=202)
    assert Tenant.objects.count() == before


def test_an_unknown_granularity_is_refused(creator):
    before = Tenant.objects.count()
    with pytest.raises(ValidationError):
        create_company("شركة بتفصيل مجهول", creator, fiscal_granularity="weekly")
    assert Tenant.objects.count() == before


class CompanyCreationApiSeedsTheFiscalYearTest(APITestCase):
    """الباب الذي يستعمله المستخدم فعلاً — لا استدعاء الخدمة مباشرة."""

    URL = "/api/tenants/companies/"

    def setUp(self):
        self.user = User.objects.create_user(username="fy-founder", password="x")
        self.client.force_authenticate(user=self.user)

    def test_creating_a_company_without_saying_anything_seeds_the_current_year(self):
        res = self.client.post(self.URL, {"CompanyName": "شركة الباب"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)

        tenant = Tenant.objects.get(pk=res.json()["TenantID"])
        today = timezone.localdate()
        self.assertTrue(
            FiscalPeriod.objects.filter(
                tenant=tenant, start_date__lte=today, end_date__gte=today,
                status="Open", is_closed=False,
            ).exists()
        )

    def test_the_year_the_caller_chose_is_the_year_that_is_seeded(self):
        res = self.client.post(
            self.URL,
            {"CompanyName": "شركة بسنتها", "fiscal_year": 2029,
             "fiscal_granularity": "yearly"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)

        tenant = Tenant.objects.get(pk=res.json()["TenantID"])
        periods = list(FiscalPeriod.objects.filter(tenant=tenant))
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].name, "FY 2029")

    def test_a_year_outside_the_sane_range_is_four_hundred_not_five_hundred(self):
        res = self.client.post(
            self.URL, {"CompanyName": "شركة مرفوضة", "fiscal_year": 202}, format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(Tenant.objects.filter(CompanyName="شركة مرفوضة").exists())


# ─────────────────────────────────────────────────────────────────────────────
# #213-أ — إصلاح الشركات التي وُلدت قبل هذا التغيير
#
# ‏`create_company` صار يزرع الفترات، وهذا لا يفيد شركة أُنشئت أمس. المسار
# المعلن للإصلاح هو `heal_company_seed` — الأمر نفسه الذي يستدرك بقية التأسيس
# الناقص، فلا يُخترع له باب ثانٍ.
# ─────────────────────────────────────────────────────────────────────────────


def _heal(tenant) -> str:
    """يشغّل الإصلاح ويعيد سطر تقريره — التقرير هو ما يقرأه المشغّل ويصدّقه."""
    out = io.StringIO()
    call_command("heal_company_seed", tenant=tenant.TenantID, stdout=out)
    return out.getvalue()


def test_healing_gives_a_period_to_a_company_that_was_born_blind(creator):
    tenant = create_company("شركة قديمة", creator)
    FiscalPeriod.objects.filter(tenant=tenant).delete()

    _heal(tenant)

    today = timezone.localdate()
    assert FiscalPeriod.objects.filter(
        tenant=tenant, start_date__lte=today, end_date__gte=today,
        status="Open", is_closed=False,
    ).exists()


def test_healing_a_healthy_company_neither_writes_nor_claims_it_did(creator):
    """‏لا يكفي أن تبقى الصفوف: تقريرٌ يدّعي إصلاحاً لم يقع يكذب على مشغّله.

    ‏`create_fiscal_year` idempotent، فنداؤها على شركةٍ سليمةٍ لا يغيّر صفّاً —
    ولذلك عدُّ الصفوف وحدَه لا يسقط أبداً ولا يحرس شيئاً. الحارسُ الحقيقيُّ هو
    أن اسمَ الشركة يخرج بلا كلمة `fiscal-year` أصلاً.
    """
    tenant = create_company("شركة سليمة", creator)
    before = set(FiscalPeriod.objects.filter(tenant=tenant).values_list("pk", flat=True))

    report = _heal(tenant)

    assert "fiscal-year" not in report, report
    after = set(FiscalPeriod.objects.filter(tenant=tenant).values_list("pk", flat=True))
    assert after == before


def test_healing_leaves_a_month_the_accountant_closed_alone(creator):
    """القفل قرارُ محاسبٍ لا عطبُ تأسيس — والإصلاح لا يراه نقصاً ولا يحاول سدّه.

    لو ضاق فحصُ «هل لليوم فترة؟» إلى المفتوحة وحدَها، لحاول الأمرُ زرعَ السنة
    فاصطدم بحارس التداخل وخرج بسطر `تعذّر` — والشهرُ مقفلٌ بقرارٍ لا بعطب.
    """
    tenant = create_company("شركة أقفلت شهرها", creator)
    today = timezone.localdate()
    current = FiscalPeriod.objects.get(
        tenant=tenant, start_date__lte=today, end_date__gte=today)
    current.status = "Closed"
    current.is_closed = True
    current.save(update_fields=["status", "is_closed"])

    report = _heal(tenant)

    assert "fiscal-year" not in report, report
    current.refresh_from_db()
    assert current.is_closed is True
    assert FiscalPeriod.objects.filter(tenant=tenant).count() == 12
