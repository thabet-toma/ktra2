"""صيانة التصنيف الوظيفي بعد الـmigration — الاشتقاق لا يموت لحظة تطبيقها.

THA-111 (اعتراض فيبل 2): الـbackfill صنّف حسابات اليوم، والصيانة الذاتية غطّت
إنشاء البنك والصندوق فقط. بقي مساران يُنشئان حسابات مصنَّفة الغرض بلا تصنيف:
بذر شجرة شركة جديدة، والحساب التلقائي للشريك — فالشركة الثانية عشرة كانت تفتح
حقل الذمم فلا تجد فيه شيئاً، والزبون الذي يُنشأ غداً يغيب عن حقل كان يظهر فيه
زبون الأمس. وتغيير نوع الشريك كان ينقل الأب ويترك التصنيف القديم.
"""
import pytest

from accounting.account_classification import (
    SUB_TYPE_CASH_BOX, SUB_TYPE_INVENTORY, SUB_TYPE_PAYABLE, SUB_TYPE_RECEIVABLE,
)
from accounting.models import Account
from partners.models import Partner
from tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(CompanyName="شركة الاختبار", SubscriptionPlan="Basic")


def _acc(tenant, code, name, acc_type="Asset", parent=None, **kw):
    return Account.objects.create(
        tenant=tenant, code=code, name=name, account_type=acc_type,
        parent=parent, is_active=True, **kw,
    )


@pytest.mark.django_db
def test_new_account_inherits_sub_type_from_its_parent(tenant):
    """حساب الزبون تحت «المدينون» ذمّةٌ ولو لم يقل أحد ذلك صراحةً."""
    ar = _acc(tenant, "1103", "المدينون التجاريون")
    ar.refresh_from_db()
    assert ar.sub_type == SUB_TYPE_RECEIVABLE, "جذر معياري يُصنَّف عند إنشائه"

    child = _acc(tenant, "11030001", "زبون جديد", parent=ar)
    child.refresh_from_db()
    assert child.sub_type == SUB_TYPE_RECEIVABLE


@pytest.mark.django_db
def test_seeded_chart_is_classified_without_a_backfill_run(tenant):
    """شركة جديدة: التصنيف يولد مع الشجرة، لا ينتظر هجرة لن تُعاد."""
    for code, name, sub in (
        ("1101", "النقدية", SUB_TYPE_CASH_BOX),
        ("1103", "المدينون التجاريون", SUB_TYPE_RECEIVABLE),
        ("1104", "المخزون", SUB_TYPE_INVENTORY),
    ):
        acc = _acc(tenant, code, name)
        acc.refresh_from_db()
        assert acc.sub_type == sub, f"{code} صُنّف {acc.sub_type} بدل {sub}"


@pytest.mark.django_db
def test_explicit_sub_type_is_never_overwritten_by_the_derivation(tenant):
    """التصحيح اليدوي من بطاقة الحساب أقوى من الاشتقاق."""
    acc = _acc(tenant, "1104", "المخزون", sub_type=SUB_TYPE_CASH_BOX)
    acc.refresh_from_db()
    assert acc.sub_type == SUB_TYPE_CASH_BOX

    acc.name = "المخزون الرئيسي"
    acc.save()
    acc.refresh_from_db()
    assert acc.sub_type == SUB_TYPE_CASH_BOX, "الحفظ اللاحق لا يعيد الاشتقاق"


@pytest.mark.django_db
def test_partner_account_gets_classified_on_creation(tenant):
    """الزبون الذي يُنشأ اليوم يظهر في حقل الذمم كزبون الأمس."""
    from accounting.api import sync_partner_accounting

    _acc(tenant, "1103", "المدينون التجاريون")
    partner = Partner.objects.create(
        tenant=tenant, name="زبون آلي", partner_type="Customer",
    )
    sync_partner_accounting(partner)
    partner.refresh_from_db()

    assert partner.linked_account is not None
    assert partner.linked_account.sub_type == SUB_TYPE_RECEIVABLE


@pytest.mark.django_db
def test_partner_type_change_moves_the_sub_type_too(tenant):
    """مورّد صار عميلاً: ينتقل أبوه ونوعه — والتصنيف معهما، لا يبقى payable."""
    from accounting.api import sync_partner_accounting

    _acc(tenant, "1103", "المدينون التجاريون")
    _acc(tenant, "2101", "الدائنون التجاريون", acc_type="Liability")

    partner = Partner.objects.create(
        tenant=tenant, name="طرف متحوّل", partner_type="Supplier",
    )
    sync_partner_accounting(partner)
    partner.refresh_from_db()
    assert partner.linked_account.sub_type == SUB_TYPE_PAYABLE

    partner.partner_type = "Customer"
    partner.save(update_fields=["partner_type"])
    sync_partner_accounting(partner)
    partner.linked_account.refresh_from_db()

    assert partner.linked_account.sub_type == SUB_TYPE_RECEIVABLE, (
        "التصنيف تخلّف عن الأب ونوع الحساب"
    )


@pytest.mark.django_db
def test_derivation_never_leaks_across_tenants(tenant):
    """الاشتقاق يقرأ شجرة الشركة وحدها."""
    other = Tenant.objects.create(CompanyName="شركة أخرى", SubscriptionPlan="Basic")
    _acc(other, "1103", "المدينون التجاريون")

    acc = _acc(tenant, "9999", "حساب بلا سلالة معيارية")
    acc.refresh_from_db()
    assert acc.sub_type is None
