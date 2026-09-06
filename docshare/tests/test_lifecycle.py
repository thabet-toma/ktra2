"""دورة حياة الرابط: إنشاؤه، إعادة استعماله، انتهاؤه، إبطاله، وعدّ مشاهداته."""
from datetime import timedelta

import pytest
from django.utils import timezone

from docshare import services
from docshare.models import (
    DOC_PURCHASE_RFQ,
    DOC_SALES_INVOICE,
    DOC_SALES_QUOTATION,
    DocumentShare,
)
from sales.models import SalesQuotation

pytestmark = pytest.mark.django_db


def test_sharing_twice_reuses_the_live_link(env, invoice):
    """«مشاركة» مرتين لا تُنتج رابطين — وإلا صار لكل مستند طابورُ روابط حيّة."""
    first = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    second = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    assert first.pk == second.pk
    assert DocumentShare.objects.filter(doc_id=invoice.pk).count() == 1


def test_token_is_long_and_unique(env, invoice, quotation):
    invoice_share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    quote_share = services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)
    assert len(invoice_share.token) >= 40
    assert invoice_share.token != quote_share.token


def test_public_page_renders_for_a_live_link(client, env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    response = client.get(f"/s/{share.token}")
    assert response.status_code == 200
    assert response["X-Robots-Tag"].startswith("noindex")
    assert "no-store" in response["Cache-Control"]
    assert b"og:title" in response.content


def test_api_share_path_works_without_touching_nginx(client, env, invoice):
    """المسار الطويل يعمل فوراً — فلا ميزة معطَّلة بانتظار إعداد الخادم."""
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    assert client.get(f"/api/share/{share.token}/").status_code == 200


def test_unknown_token_is_404(client):
    assert client.get("/s/لا-يوجد-هذا-التوكن-اطلاقا").status_code == 404


def test_expired_link_is_410_not_404(client, env, invoice):
    """410 لا 404: «انتهى» رسالةٌ يفهمها الزبون فيطلب رابطاً جديداً."""
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    DocumentShare.objects.filter(pk=share.pk).update(
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    response = client.get(f"/s/{share.token}")
    assert response.status_code == 410
    assert invoice.invoice_number.encode() not in response.content


def test_revoked_link_is_410_and_row_survives(client, env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    services.revoke_share(share)
    assert client.get(f"/s/{share.token}").status_code == 410
    # الصفّ يبقى: «من شارك هذا المستند ومتى؟» سؤالٌ يُسأل بعد الإبطال لا قبله.
    assert DocumentShare.objects.filter(pk=share.pk).exists()


def test_resharing_after_revoke_mints_a_new_token(env, invoice):
    first = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    services.revoke_share(first)
    second = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    assert second.pk != first.pk
    assert second.token != first.token


def test_deleted_document_behind_a_live_link_is_404(client, env, quotation):
    share = services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)
    quotation.lines.all().delete()
    quotation.delete()
    assert client.get(f"/s/{share.token}").status_code == 404


def test_human_visit_is_counted(client, env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    client.get(f"/s/{share.token}", HTTP_USER_AGENT="Mozilla/5.0 (iPhone)")
    share.refresh_from_db()
    assert share.view_count == 1
    assert share.first_viewed_at is not None


def test_whatsapp_crawler_is_not_counted_as_a_view(client, env, invoice):
    """واتساب يجلب الرابط **أثناء الكتابة قبل الإرسال**.

    احتساب جلبه مشاهدةً يجعل «شوهد» تكذب على المالك: يرى أن الزبون فتح
    الفاتورة قبل أن يضغط هو زرّ الإرسال.
    """
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    client.get(f"/s/{share.token}", HTTP_USER_AGENT="WhatsApp/2.24 A")
    client.get(f"/s/{share.token}", HTTP_USER_AGENT="facebookexternalhit/1.1")
    share.refresh_from_db()
    assert share.view_count == 0


def test_sharing_a_draft_quotation_sends_it(env, quotation):
    """مشاركة العرض هي إرساله — وبدونها يسقط قبول الزبون على آلة الحالات."""
    assert quotation.status == SalesQuotation.STATUS_DRAFT
    services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)
    quotation.refresh_from_db()
    assert quotation.status == SalesQuotation.STATUS_SENT


def test_sharing_a_posted_invoice_changes_nothing_about_it(env, invoice):
    before = invoice.status
    services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    invoice.refresh_from_db()
    assert invoice.status == before


def test_expiry_days_outside_the_allowed_set_fall_back_to_default(env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk, days=9999)
    expected = timezone.now() + timedelta(days=services.DEFAULT_EXPIRY_DAYS)
    assert abs((share.expires_at - expected).total_seconds()) < 60


# ── مواصفة #147 (المرحلة 3ب): جمهورُ الرابط — عامٌّ أو مورّدٌ مسمّى ─────────
#
# ISSUE (عطبٌ حيّ قبل الإصلاح): `create_share(dedupe=True)` كانت تعيد أحدث
# رابطٍ حيّ للمستند **بلا تمييز جمهور** — طلبيةٌ أُرسلت لموردٍ مسمّى، ثم طُلب
# لها رابطٌ عامّ، كانت تُعيد رابط ذلك المورّد الخاص نفسه. الاختبار التالي
# يُكتب ليُخفق **قبل** إصلاح `active_share`/`create_share` (TDD) ويمرّ بعده.

def test_public_share_does_not_reuse_an_existing_named_recipient_share(env, purchase_rfq):
    """رابطٌ خاصٌّ لمورّدٍ مسمّى موجودٌ سلفاً (`dedupe=False`، الجمهور الافتراضي
    `is_public=False`) — وطلبُ رابطٍ **عامّ** بعده يجب ألّا يعيد ذلك الرابط."""
    named_share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, dedupe=False,
    )
    assert named_share.is_public is False

    public_share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )

    assert public_share.pk != named_share.pk
    assert public_share.token != named_share.token
    assert public_share.is_public is True


def test_asking_twice_for_a_public_link_reuses_the_same_live_share(env, purchase_rfq):
    first = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )
    second = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )
    assert first.pk == second.pk


def test_named_recipient_shares_still_dedupe_false_by_default(env, purchase_rfq):
    """`dedupe=False` لموردَين مسمَّيين يبقى كما هو — لا تغيّره راية الجمهور."""
    first = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, dedupe=False,
    )
    second = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, dedupe=False,
    )
    assert first.pk != second.pk
    assert first.is_public is False and second.is_public is False


def test_public_rfq_share_expiry_defaults_to_the_reply_deadline(env, purchase_rfq):
    """رابطٌ عامٌّ يتّبع مهلة ردّ الطلبية — لا الشهر الافتراضي دائماً."""
    from datetime import date

    from logistics.services import public_rfq_share_expiry_days

    purchase_rfq.reply_deadline = date.today() + timedelta(days=5)
    purchase_rfq.save(update_fields=["reply_deadline"])
    days = public_rfq_share_expiry_days(purchase_rfq)
    share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True, days=days,
    )
    expected = timezone.now() + timedelta(days=days)
    assert abs((share.expires_at - expected).total_seconds()) < 60
    # المهلةُ أقرب بكثير من الشهر الافتراضي — لم تسقط على `DEFAULT_EXPIRY_DAYS`.
    assert days < services.DEFAULT_EXPIRY_DAYS or days == 7

    purchase_rfq.reply_deadline = None
    purchase_rfq.save(update_fields=["reply_deadline"])
    assert public_rfq_share_expiry_days(purchase_rfq) == services.DEFAULT_EXPIRY_DAYS


def test_awarding_the_rfq_revokes_the_public_share_but_keeps_the_row(
    client, env, purchase_rfq, rfq_recipient,
):
    from rest_framework.test import APIClient

    from logistics.models import PurchaseRFQ
    from logistics.services import submit_rfq_supplier_quote

    purchase_rfq.scope = PurchaseRFQ.SCOPE_IMPORT
    purchase_rfq.save(update_fields=["scope"])
    line_id = purchase_rfq.lines.first().pk
    submit_rfq_supplier_quote(rfq_recipient, name="مصنع المشاركة", prices={line_id: "10"})

    public_share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )

    api = APIClient()
    api.force_authenticate(user=env["owner"])
    api.credentials(HTTP_X_TENANT_ID=str(env["tenant"].pk))
    response = api.post(
        f"/api/logistics/purchase-rfqs/{purchase_rfq.pk}/award/",
        {"supplier": rfq_recipient.supplier_id},
    )
    assert response.status_code == 200, response.content

    public_share.refresh_from_db()
    assert public_share.is_revoked
    assert DocumentShare.objects.filter(pk=public_share.pk).exists()


def test_cancelling_the_rfq_revokes_the_public_share_but_keeps_the_row(
    client, env, purchase_rfq,
):
    from rest_framework.test import APIClient

    public_share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )

    api = APIClient()
    api.force_authenticate(user=env["owner"])
    api.credentials(HTTP_X_TENANT_ID=str(env["tenant"].pk))
    response = api.post(f"/api/logistics/purchase-rfqs/{purchase_rfq.pk}/cancel/")
    assert response.status_code == 200, response.content

    public_share.refresh_from_db()
    assert public_share.is_revoked
    assert DocumentShare.objects.filter(pk=public_share.pk).exists()


def test_manual_stop_action_revokes_the_public_share_but_keeps_the_row(
    client, env, purchase_rfq,
):
    from rest_framework.test import APIClient

    public_share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )

    api = APIClient()
    api.force_authenticate(user=env["owner"])
    api.credentials(HTTP_X_TENANT_ID=str(env["tenant"].pk))
    response = api.post(f"/api/logistics/purchase-rfqs/{purchase_rfq.pk}/stop-public-link/")
    assert response.status_code == 200, response.content

    public_share.refresh_from_db()
    assert public_share.is_revoked
    assert DocumentShare.objects.filter(pk=public_share.pk).exists()

    # ولا رابطَ حيّاً بعدها — النداء الثاني يقول صراحةً إنه لا يوجد ما يُبطَل.
    second = api.post(f"/api/logistics/purchase-rfqs/{purchase_rfq.pk}/stop-public-link/")
    assert second.status_code == 400
