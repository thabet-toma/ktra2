"""دورة حياة الرابط: إنشاؤه، إعادة استعماله، انتهاؤه، إبطاله، وعدّ مشاهداته."""
from datetime import timedelta

import pytest
from django.utils import timezone

from docshare import services
from docshare.models import DOC_SALES_INVOICE, DOC_SALES_QUOTATION, DocumentShare
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
