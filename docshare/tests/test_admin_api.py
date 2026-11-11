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


def test_generic_create_refuses_a_payment_notice_and_creates_nothing(
    env, office_tenant, payment_notice,
):
    """م٣ (#285): إشعارُ الدفع لا يُنشَأ من الباب العامّ — 400 كما رابطُ العدّ.

    بابُه الوحيد «جاهز للإرسال» (`accounting_office.appointments`)، وهو يختار
    الالتزامَ من زبائن العضو المرئيّين. وهذا السطحَ يأخذ **أيّ** معرّف `Obligation`
    (متسلسلٌ يُخمَّن)، فصلاحيةُ النوع وحدها كانت تكفي محاسباً ليتّخذ رابطاً عامّاً
    بأسماء زملائه ومبالغهم: صلاحيتُه `office.clients.write` بلا `office.clients.all`.
    """
    from docshare.models import DOC_PAYMENT_NOTICE, DocumentShare

    accountant = _member(env["tenant"], "share-accountant-create", "accountant")
    before = DocumentShare.objects.count()

    response = _client(accountant, env["tenant"]).post(
        SHARES_URL, {"doc_type": DOC_PAYMENT_NOTICE, "doc_id": payment_notice.pk},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "جاهز للإرسال" in response.data["detail"], response.data
    assert "token" not in response.data
    assert DocumentShare.objects.count() == before


def test_an_accountant_lists_reads_and_revokes_only_their_own_clients_notice(
    env, office_tenant, make_payment_notice_obligation,
):
    """م٣ (#285): القائمةُ والقراءةُ والإبطالُ على `visible_clients` لا على الشركة.

    دورُ `accountant` يكتب زبائن المكتب ولا يرى زبائن غيره: بلا هذا النطاق كان
    `GET ?doc_type=payment_notice` يُعيد `token` و`public_url` لكل إشعارات الشركة،
    ويُبطل المحاسبُ أيَّ رابطٍ منها.
    """
    from docshare.models import DOC_PAYMENT_NOTICE

    accountant = _member(env["tenant"], "share-accountant-scope", "accountant")
    mine = make_payment_notice_obligation(
        name="زبون المحاسب", responsible=accountant,
    )
    theirs = make_payment_notice_obligation(name="زبون الزميل")
    my_share = services.create_share(env["tenant"], DOC_PAYMENT_NOTICE, mine.pk)
    their_share = services.create_share(env["tenant"], DOC_PAYMENT_NOTICE, theirs.pk)

    api = _client(accountant, env["tenant"])

    rows = _rows(api.get(SHARES_URL, {"doc_type": DOC_PAYMENT_NOTICE}))
    assert [row["doc_id"] for row in rows] == [mine.pk], rows

    assert api.get(f"{SHARES_URL}{their_share.pk}/").status_code == 404
    refused = api.post(f"{SHARES_URL}{their_share.pk}/revoke/", {}, format="json")
    assert refused.status_code == 404
    their_share.refresh_from_db()
    assert their_share.revoked_at is None

    # والحارسُ لا يمنع المحاسب من رابطه هو — وإلا صار النطاقُ حجباً لا تقييداً.
    allowed = api.post(f"{SHARES_URL}{my_share.pk}/revoke/", {}, format="json")
    assert allowed.status_code == 200, allowed.data
    my_share.refresh_from_db()
    assert my_share.revoked_at is not None


def test_an_unlicensed_company_cannot_read_or_revoke_a_payment_notice_share(
    env, office_tenant, payment_notice,
):
    """م٢ (#285): الترخيصُ قبل الصلاحية في القراءة والإبطال أيضاً — 404 لا 403.

    الصفُّ يبقى (الروابطُ لا تُحذَف)، لكن سطحَ الإدارة لا يُقِرّ بوجوده لشركةٍ أُطفئ
    ترخيصُها: 403 يُثبت لمن يخمّن المعرّفات أنّ الرابط موجود. والقراءةُ قبل الإطفاء
    تُثبت أنّ المعرّف **مرئيٌّ** أصلاً، فلا يمرّ الاختبار لأن الكائن لم يُوجَد.
    """
    from core.models import TenantModule
    from core.modules import invalidate_module_cache
    from docshare.models import DOC_PAYMENT_NOTICE

    share = services.create_share(
        env["tenant"], DOC_PAYMENT_NOTICE, payment_notice.pk,
    )
    api = _client(env["owner"], env["tenant"])
    assert api.get(f"{SHARES_URL}{share.pk}/").status_code == 200

    TenantModule.objects.filter(
        tenant=env["tenant"], module_key="accounting_office"
    ).update(enabled=False)
    invalidate_module_cache(env["tenant"].pk)

    assert api.get(f"{SHARES_URL}{share.pk}/").status_code == 404
    refused = api.post(f"{SHARES_URL}{share.pk}/revoke/", {}, format="json")
    assert refused.status_code == 404
    share.refresh_from_db()
    assert share.revoked_at is None


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


def test_generic_create_refuses_purchase_rfq_and_creates_nothing(
    env, purchase_rfq, rfq_recipient,
):
    """طلبُ عرض السعر لا يُشارَك من السطح العامّ — له بابان خاصّان به.

    `create_share` هنا بجمهورٍ خاصّ (`is_public=False`) وبإعادة الحيّ القائم،
    فكان نداءٌ مباشر يعيد **رابطَ المورّد المسمّى** نفسه — وصفحتُه معبّأةٌ
    بأسعار ذلك المورّد. الرابط العامّ المشروع وحده:
    `POST /api/logistics/purchase-rfqs/<id>/public-link/`.
    """
    from docshare.models import DOC_PURCHASE_RFQ, DocumentShare

    services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, dedupe=False,
    )
    before = DocumentShare.objects.count()

    response = _client(env["owner"], env["tenant"]).post(
        SHARES_URL, {"doc_type": DOC_PURCHASE_RFQ, "doc_id": purchase_rfq.pk},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "public-link" in response.data["detail"]
    assert "token" not in response.data
    assert DocumentShare.objects.count() == before
