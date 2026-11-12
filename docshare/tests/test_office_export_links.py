"""نوعا تصدير المكتب لا يُنشآن من الباب العامّ — #290 (إصلاحُ البند المانع).

**العطبُ الذي يحرسه هذا الملفّ:** `POST /api/document-shares/` يفحص **صلاحيةَ
النوع** وحدها (`DOC_TYPES[…]["permission"]`)، ونوعا التصدير يعلنان
`office.clients.all`. فعضوٌ مُنح ذلك المفتاح بلا دورٍ معتمِد (`manager`/
`office_manager`) وبلا `office.amounts.view` كان يأخذ منه رابطاً عامّاً لنسخة
بيانات المكتب كلّه — أسماءَ زبائنه ومبالغَهم — متجاوزاً شرطَي الدور والمبالغ
اللذين تفرضهما نقطةُ التصدير. الرفضُ الصريح في `DocumentShareViewSet.create`
يُغلق الباب، ويبقى البابُ الشرعيّ `POST /api/accounting-office/exports/…`.

**والاختبارُ يسقط على الحالة قبل الإصلاح**: الرفضُ الجديد هو ما يُنتج 400 هنا،
ولو أُزيل لَعاد السطحُ يردّ 201 ويُنشئ صفَّ مشاركة (وهو ما كان يحدث فعلاً).
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting_office.services import set_office_setting
from core.modules import invalidate_module_cache
from docshare.models import (
    DOC_OFFICE_CLIENT_NAMES,
    DOC_OFFICE_DATA_EXPORT,
    DocumentShare,
)
from tenants.models import Currency, MemberPermission, UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db

#: سطحُ إنشاء الروابط العامّ (المصادَق عليه) — البابُ الذي يجب أن يرفض.
SHARES_URL = "/api/document-shares/"
#: بابُ التصدير الشرعيّ — يفرض الدورَ والمفتاحَ ورؤيةَ المبالغ معاً.
EXPORT_FULL_LINK = "/api/accounting-office/exports/full-link/"
EXPORT_CLIENT_NAMES = "/api/accounting-office/exports/client-names/"

#: ما يميّز رفضَنا عن أيّ حارسٍ آخر: رسالتُه توجّه إلى نقطة التصدير.
EXPORT_ROUTE_MARKER = "POST /api/accounting-office/exports/…"


def _client(user, tenant):
    api = APIClient()
    api.force_authenticate(user=user)
    api.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return api


def _member(tenant, username, role):
    user = User.objects.create_user(username=username, password="x")
    UserCompanyMembership.objects.create(user=user, tenant=tenant, role=role)
    return user


@pytest.fixture
def office_tenant(db):
    """مكتبُ محاسبةٍ مرخَّص، نظامُه فلسطينيّ — النوعُ الثاني (`م111`) يلزمه."""
    Currency.objects.get_or_create(
        Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
    )
    owner = User.objects.create_user(username="oe_surface_owner", password="x")
    tenant = create_company("مكتب سطح التصدير", owner, template="accounting_office")
    invalidate_module_cache(tenant.pk)
    set_office_setting(tenant, "tax_system", "PS")
    set_office_setting(tenant, "office_size", "solo")
    return {"owner": owner, "tenant": tenant}


def test_a_member_with_the_key_but_no_approver_role_is_refused_by_the_new_guard(
    office_tenant,
):
    """`office.clients.all` وحدها لا تُنشئ رابطَ النسخة — الرفضُ **400 برسالتنا**.

    والفحصُ على `detail` لا على الحالة وحدها: 403 من حارس الصلاحية أو 404 من
    بوابة الترخيص كانا سيمرّان على «ليست 201» ويُخفيان أن الباب ما زال مفتوحاً
    لحارسٍ آخر. الرسالةُ هنا هي رسالةُ الرفض الجديد حرفياً.
    """
    tenant = office_tenant["tenant"]
    accountant = _member(tenant, "oe_key_only", "accountant")
    MemberPermission.objects.create(
        membership=UserCompanyMembership.objects.get(
            tenant=tenant, user=accountant,
        ),
        permission_key="office.clients.all",
        allowed=True,
    )
    api = _client(accountant, tenant)

    for doc_type in (DOC_OFFICE_DATA_EXPORT, DOC_OFFICE_CLIENT_NAMES):
        response = api.post(
            SHARES_URL, {"doc_type": doc_type, "doc_id": tenant.pk}, format="json",
        )

        assert response.status_code == 400, (doc_type, response.data)
        assert EXPORT_ROUTE_MARKER in response.data["detail"], (
            doc_type, response.data["detail"],
        )

    assert not DocumentShare.objects.filter(
        doc_type__in=[DOC_OFFICE_DATA_EXPORT, DOC_OFFICE_CLIENT_NAMES],
    ).exists(), "أُنشئ صفُّ مشاركةٍ من الباب العامّ"


def test_the_owner_creates_both_links_from_the_accounting_office_route(office_tenant):
    """والمالكُ يبقى ينجح من نقطته: رابطا النسخة والبيان يُنشآن هناك."""
    tenant = office_tenant["tenant"]
    api = _client(office_tenant["owner"], tenant)

    full = api.post(EXPORT_FULL_LINK, {}, format="json")
    assert full.status_code == 201, full.data
    full_share = DocumentShare.objects.get(doc_type=DOC_OFFICE_DATA_EXPORT)
    assert full_share.doc_id == tenant.pk
    assert full.data["url"].endswith(f"/s/{full_share.token}")

    names = api.post(EXPORT_CLIENT_NAMES, {}, format="json")
    assert names.status_code == 201, names.data
    names_share = DocumentShare.objects.get(doc_type=DOC_OFFICE_CLIENT_NAMES)
    assert names_share.doc_id == tenant.pk
    assert names.data["url"].endswith(f"/s/{names_share.token}")
