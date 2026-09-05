"""قالب «إطارات» (`tyres`) — مطابقٌ اليوم لقالب `general` حرفياً، بمفتاحٍ
منفصل تُعلَّق عليه تخصيصات لاحقة (`tenants/company_templates.py`).

الأهم هنا: النقل من `general` إلى `tyres` لشركة قائمة لا يزرع شيئاً ولا يحذف
شيئاً — بذرة `tyres` (`coa=None`, `document_types=None`) هي نفسها `COA_DATA`
وكل أنواع الدفاتر الخمسة عشر، فأي شركة `general` تملكها فعلاً بالكامل.
"""
import re

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from accounting.models import Account
from tenants.company_templates import _GOODS_MOVEMENT_HIDDEN_PATHS, template_hides_path
from tenants.models import Tenant, TenantBook
from tenants.services import COA_DATA, create_company, switch_company_template

pytestmark = pytest.mark.django_db


@pytest.fixture
def creator():
    return User.objects.create_user(username="tyres-founder", password="x")


def _account_codes(tenant):
    return set(Account.objects.filter(tenant=tenant).values_list("code", flat=True))


def _book_types(tenant):
    return set(TenantBook.objects.filter(tenant=tenant).values_list("document_type", flat=True))


def test_tyres_company_produces_the_same_coa_as_general(creator):
    general_tenant = create_company("شركة عامة", creator, template="general")
    tyres_tenant = create_company("شركة إطارات", creator, template="tyres")

    assert _account_codes(tyres_tenant) == _account_codes(general_tenant)
    assert _account_codes(tyres_tenant) == {row[0] for row in COA_DATA}


def test_tyres_company_produces_the_same_book_types_as_general(creator):
    general_tenant = create_company("شركة عامة ٢", creator, template="general")
    tyres_tenant = create_company("شركة إطارات ٢", creator, template="tyres")

    assert _book_types(tyres_tenant) == _book_types(general_tenant)
    assert _book_types(tyres_tenant) == set(dict(TenantBook.DOCUMENT_TYPES))


def test_switching_general_company_to_tyres_creates_and_deletes_nothing(creator):
    tenant = create_company("شركة تتحوّل لإطارات", creator, template="general")

    before_account_codes = _account_codes(tenant)
    before_book_types = _book_types(tenant)
    before_account_count = Account.objects.filter(tenant=tenant).count()

    result = switch_company_template(tenant, "tyres")

    assert result["accounts_created"] == []
    assert result["book_types_created"] == []
    assert _account_codes(tenant) == before_account_codes
    assert _book_types(tenant) == before_book_types
    assert Account.objects.filter(tenant=tenant).count() == before_account_count
    assert not Account.objects.filter(tenant=tenant, is_active=False).exists()

    tenant.refresh_from_db()
    assert tenant.template == "tyres"


def test_tyres_hides_no_path():
    for path in _GOODS_MOVEMENT_HIDDEN_PATHS:
        assert template_hides_path("tyres", path) is False


def test_switch_command_preview_does_not_change_tenant_template(creator):
    tenant = create_company("شركة معاينة فقط", creator, template="general")

    call_command("switch_company_template", "--tenant-id", str(tenant.TenantID), "--template", "tyres")

    tenant.refresh_from_db()
    assert tenant.template == "general"
    assert not Account.objects.filter(tenant=tenant, is_active=False).exists()


def test_switch_command_apply_performs_the_switch(creator):
    tenant = create_company("شركة تُنقَل بالأمر", creator, template="general")

    call_command(
        "switch_company_template",
        "--tenant-id", str(tenant.TenantID),
        "--template", "tyres",
        "--apply",
    )

    tenant.refresh_from_db()
    assert tenant.template == "tyres"


def test_preview_count_matches_what_apply_actually_creates(creator, capsys):
    """حارس انزياح بين نسختَي «ما الناقص؟».

    المعاينة في الأمر تحسب الحسابات الناقصة بنسختها الخاصة، و
    `switch_company_template` تحسبها بنسختها داخل الخدمة. لو انزاحت إحداهما
    عن الأخرى صار الأمر يطبع رقماً كاذباً لمن يشغّله على الإنتاج قبل الكتابة —
    وهو الاستعمال الوحيد الذي بُني له. فيُشدّ الرقمان إلى بعضهما هنا.

    تُختار شركةٌ بقالب `accounting_firm` عمداً: بذرتها تُسقط عشرات أكواد
    `COA_DATA`، فالنقل إلى `tyres` يزرع فعلاً ولا يكون الرقمان صفرين متطابقين
    بالصدفة.
    """
    tenant = create_company("شركة ناقصة الحسابات", creator, template="accounting_firm")

    call_command(
        "switch_company_template",
        "--tenant-id", str(tenant.TenantID),
        "--template", "tyres",
    )
    preview = capsys.readouterr().out
    match = re.search(r"حسابات ستُزرع \((\d+)\)", preview)
    assert match, f"لم تُطبع سطر المعاينة المتوقَّع:\n{preview}"
    previewed = int(match.group(1))
    assert previewed > 0, "الشركة المختارة لا ينقصها شيء — الحارس لا يحرس شيئاً."

    result = switch_company_template(tenant, "tyres")

    assert len(result["accounts_created"]) == previewed, (
        f"المعاينة قالت {previewed} حساباً والتنفيذ زرع "
        f"{len(result['accounts_created'])} — النسختان انزاحتا."
    )
