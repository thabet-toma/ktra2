"""سطح الإدارة المصادَق عليه: الصلاحية، عزل الشركة، الإنشاء والإبطال."""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from docshare import services
from docshare.models import DOC_SALES_INVOICE, DOC_SALES_QUOTATION
from tenants.models import UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db

SHARES_URL = "/api/document-shares/"


def _client(user, tenant):
    api = APIClient()
    api.force_authenticate(user=user)
    api.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return api


def _rows(response):
    """القائمة قد تكون مُرقَّمة أو خاماً — الاختبار يهتمّ بالصفوف لا بالغلاف."""
    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


def _member(tenant, username, role):
    user = User.objects.create_user(username=username, password="x")
    UserCompanyMembership.objects.create(user=user, tenant=tenant, role=role)
    return user


def test_manager_can_create_a_share_and_gets_the_public_url(env, invoice):
    api = _client(env["owner"], env["tenant"])
    response = api.post(
        SHARES_URL, {"doc_type": DOC_SALES_INVOICE, "doc_id": invoice.pk, "days": 7},
        format="json",
    )
    assert response.status_code == 201, response.data
    body = response.data
    assert body["token"]
    assert body["public_url"].endswith(f"/s/{body['token']}")
    assert body["is_live"] is True
    assert body["view_count"] == 0


def test_viewer_cannot_create_a_share(env, invoice):
    viewer = _member(env["tenant"], "share-viewer", "viewer")
    api = _client(viewer, env["tenant"])
    response = api.post(
        SHARES_URL, {"doc_type": DOC_SALES_INVOICE, "doc_id": invoice.pk},
        format="json",
    )
    assert response.status_code == 403


def test_sales_employee_can_create_a_share(env, quotation):
    seller = _member(env["tenant"], "share-seller", "sales")
    api = _client(seller, env["tenant"])
    response = api.post(
        SHARES_URL, {"doc_type": DOC_SALES_QUOTATION, "doc_id": quotation.pk},
        format="json",
    )
    assert response.status_code == 201, response.data


def test_permission_is_taken_from_the_type_not_hardcoded(env, invoice, monkeypatch):
    """صلاحية النوع تُقرأ من `DOC_TYPES`، لا `sales.document.share` مثبَّتةً.

    كانت صلاحية المبيعات مثبَّتةً حرفياً في كل طريقة على هذا السطح بينما
    `DOC_TYPES[…]["permission"]` معلَنةٌ ومهملة. الأثر لحظةَ أول نوع شراء:
    **موظف المبيعات يشارك فواتير المورّدين** وموظف المشتريات لا يقدر.

    الاختبار يحقن نوعاً وهمياً بصلاحية غير مبيعاتية بدل انتظار نوعٍ حقيقي:
    ما يُقاس هنا هو التوصيل نفسه، وهو واحدٌ لكل الأنواع.
    """
    from docshare import documents

    fake = dict(documents.DOC_TYPES[DOC_SALES_INVOICE])
    fake["permission"] = "purchase.invoice.create"
    monkeypatch.setitem(documents.DOC_TYPES, "fake_purchase_doc", fake)

    seller = _member(env["tenant"], "share-seller-perm", "sales")
    api = _client(seller, env["tenant"])

    # موظف المبيعات يملك `sales.document.share` ولا يملك `purchase.invoice.create`.
    refused = api.post(
        SHARES_URL, {"doc_type": "fake_purchase_doc", "doc_id": invoice.pk},
        format="json",
    )
    assert refused.status_code == 403, refused.data

    # ونفس المستند تحت نوعه المبيعاتي يمرّ — فالرفض صلاحيةُ نوعٍ لا عطلٌ عام.
    allowed = api.post(
        SHARES_URL, {"doc_type": DOC_SALES_INVOICE, "doc_id": invoice.pk},
        format="json",
    )
    assert allowed.status_code == 201, allowed.data


def test_listing_hides_types_the_user_cannot_share(env, invoice, monkeypatch):
    """القائمة مفلترةٌ بصلاحية النوع لا محجوبةً كلّها ولا مكشوفةً كلّها."""
    from docshare import documents

    fake = dict(documents.DOC_TYPES[DOC_SALES_INVOICE])
    fake["permission"] = "purchase.invoice.create"
    monkeypatch.setitem(documents.DOC_TYPES, "fake_purchase_doc", fake)
    services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    services.create_share(env["tenant"], "fake_purchase_doc", invoice.pk)

    seller = _member(env["tenant"], "share-seller-list", "sales")
    rows = _rows(_client(seller, env["tenant"]).get(SHARES_URL))
    assert {row["doc_type"] for row in rows} == {DOC_SALES_INVOICE}


def test_unknown_document_is_404_not_403(env):
    """404 لا 403: 403 يُثبت لمن يخمّن المعرّفات أن المستند موجود."""
    api = _client(env["owner"], env["tenant"])
    response = api.post(
        SHARES_URL, {"doc_type": DOC_SALES_INVOICE, "doc_id": 999_999}, format="json",
    )
    assert response.status_code == 404


def test_bad_doc_type_is_400(env, invoice):
    api = _client(env["owner"], env["tenant"])
    response = api.post(
        SHARES_URL, {"doc_type": "no_such_document_type", "doc_id": invoice.pk},
        format="json",
    )
    assert response.status_code == 400


def test_sales_employee_cannot_share_a_purchase_document(env, deal):
    """جانبان جمهورُهما مختلف ⇒ مفتاحان مختلفان.

    البائع يملك `sales.document.share` ولا يملك `purchase.document.share`،
    فإرسالُ صفقةٍ إلى المصنع ليس عملَه.
    """
    seller = _member(env["tenant"], "seller-vs-purchase", "sales")
    response = _client(seller, env["tenant"]).post(
        SHARES_URL, {"doc_type": "logistics_deal", "doc_id": deal.pk}, format="json",
    )
    assert response.status_code == 403


def test_procurement_employee_can_share_a_purchase_document(env, deal):
    """وموظف المشتريات يملكه افتراضياً — إرسال الصفقة إلى المصنع عملُه."""
    buyer = _member(env["tenant"], "buyer-shares-deal", "procurement")
    response = _client(buyer, env["tenant"]).post(
        SHARES_URL, {"doc_type": "logistics_deal", "doc_id": deal.pk}, format="json",
    )
    assert response.status_code == 201, response.data


def test_procurement_employee_cannot_share_a_sales_invoice(env, invoice):
    """والمنعُ متبادل — ولولا ذلك لكان المفتاحان مفتاحاً واحداً بلا معنى."""
    buyer = _member(env["tenant"], "buyer-vs-sales", "procurement")
    response = _client(buyer, env["tenant"]).post(
        SHARES_URL, {"doc_type": DOC_SALES_INVOICE, "doc_id": invoice.pk},
        format="json",
    )
    assert response.status_code == 403


def test_listing_is_scoped_to_the_company(env, invoice):
    services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)

    other_owner = User.objects.create_user(username="other-admin", password="x")
    other_tenant = create_company("شركة الجارة", other_owner)
    api = _client(other_owner, other_tenant)

    response = api.get(SHARES_URL)
    assert response.status_code == 200
    assert len(_rows(response)) == 0


def test_revoke_kills_the_public_page(client, env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    assert client.get(f"/s/{share.token}").status_code == 200

    api = _client(env["owner"], env["tenant"])
    response = api.post(f"{SHARES_URL}{share.pk}/revoke/", {}, format="json")
    assert response.status_code == 200
    assert response.data["is_live"] is False

    assert client.get(f"/s/{share.token}").status_code == 410


def test_another_company_cannot_revoke_your_link(env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)

    other_owner = User.objects.create_user(username="other-revoker", password="x")
    other_tenant = create_company("شركة المتطفّلة", other_owner)
    api = _client(other_owner, other_tenant)

    response = api.post(f"{SHARES_URL}{share.pk}/revoke/", {}, format="json")
    assert response.status_code == 404
    share.refresh_from_db()
    assert share.revoked_at is None


def test_filtering_by_document_returns_only_its_links(env, invoice, quotation):
    services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)

    api = _client(env["owner"], env["tenant"])
    response = api.get(
        SHARES_URL, {"doc_type": DOC_SALES_INVOICE, "doc_id": invoice.pk},
    )
    results = _rows(response)
    assert len(results) == 1
    assert results[0]["doc_type"] == DOC_SALES_INVOICE


def test_anonymous_cannot_reach_the_admin_surface(env, invoice):
    response = APIClient().get(SHARES_URL)
    assert response.status_code in (401, 403)
