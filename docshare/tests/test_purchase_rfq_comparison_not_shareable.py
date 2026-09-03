"""ISSUE #116 (مواصفة #108 §٨) — ورقةُ مقارنة الموردين داخليّةٌ بحتة.

هذا حارسُ **قرارٍ** لا حارسُ سلوكٍ عابر: المصفوفة (`/api/logistics/purchase-
rfqs/<id>/comparison/`) لا تصل رابطاً عاماً أبداً — لا اليوم ولا مستقبلاً بلا
مراجعة صريحة لهذا الملف. لذلك الاختبار يسمّي مرشَّح مفتاح `doc_type` بعينه
ويثبت غيابه من السجلّ، لا مجرّد أن أيّ سلسلة عشوائية تُرفَض (ذاك كان سيمرّ على
أي خطأ إملائي بلا أن يحرس القرار نفسه).
"""
import pytest
from django.contrib.auth.models import User

from docshare import services
from docshare.documents import DOC_TYPES

pytestmark = pytest.mark.django_db

#: مرشَّح الاسم الذي كان يُستعمَل لو أُريد مشاركة المصفوفة — يبقى غائباً عمداً.
COMPARISON_DOC_TYPE_CANDIDATES = (
    "purchase_rfq_comparison",
    "rfq_comparison",
    "purchase_comparison",
)


def test_comparison_sheet_has_no_doc_type_in_the_registry():
    """القرار نفسه: لا مفتاح تسجيل لورقة المقارنة — طلبُ نوعها يرتدّ دوماً."""
    for candidate in COMPARISON_DOC_TYPE_CANDIDATES:
        assert candidate not in DOC_TYPES, (
            f"«{candidate}» صار في DOC_TYPES — ورقة المقارنة يجب أن تبقى "
            "داخليّة بحتة ولا تصل docshare إطلاقاً (مواصفة #108 §٨)."
        )


def test_creating_a_share_for_the_comparison_sheet_is_rejected_at_the_service():
    """`create_share` يرفض أي `doc_type` غير مسجَّل — بنيوياً لا استثناءً محلّياً."""
    from tenants.models import Tenant

    tenant = Tenant.objects.create(TenantID=8901, CompanyName="RFQ Comparison Co")
    for candidate in COMPARISON_DOC_TYPE_CANDIDATES:
        with pytest.raises(services.ShareNotFound):
            services.create_share(tenant, candidate, 1)


def test_admin_api_rejects_sharing_the_comparison_sheet():
    """سطح الإدارة (`POST /api/document-shares/`) يردّ 400 لا يخترق التسجيل."""
    from rest_framework.test import APIClient

    from tenants.services import create_company

    owner = User.objects.create_user(username="rfq-comparison-owner", password="x")
    tenant = create_company("شركة مقارنة الموردين", owner)

    api = APIClient()
    api.force_authenticate(user=owner)
    api.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))

    response = api.post(
        "/api/document-shares/",
        {"doc_type": "purchase_rfq_comparison", "doc_id": 1},
        format="json",
    )
    assert response.status_code == 400, response.data
