"""قرار الزبون على عرض السعر من الرابط العام.

المخاطرة المعلومة والمقبولة: من يملك الرابط يستطيع أن يقرّر — لازمُ قرار
«رابط عام بلا تحقّق هوية»، وهو سلوك Odoo نفسه. ما تحرسه هذه الاختبارات هو
كل ما عدا ذلك: أن القرار لا يتكرّر، ولا يخالف آلة حالات العرض، ولا يُسجَّل
بلا اسم، ولا يمرّ على مستند ليس عرضاً.
"""
import pytest

from docshare import services
from docshare.models import DOC_SALES_INVOICE, DOC_SALES_QUOTATION
from sales.models import SalesQuotation

pytestmark = pytest.mark.django_db


def _shared_sent_quotation(env, quotation):
    """المشاركة تنقل العرض من «مسودة» إلى «أُرسل» — وهي الحالة القابلة للقرار."""
    share = services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)
    quotation.refresh_from_db()
    return share


def test_accept_moves_the_quotation_and_records_the_signer(client, env, quotation):
    share = _shared_sent_quotation(env, quotation)
    response = client.post(
        f"/s/{share.token}/decision/",
        {"decision": "accepted", "name": "أبو محمد"},
    )
    assert response.status_code == 302

    quotation.refresh_from_db()
    share.refresh_from_db()
    assert quotation.status == SalesQuotation.STATUS_ACCEPTED
    assert share.decision == "accepted"
    assert share.decided_name == "أبو محمد"
    assert share.decided_at is not None


def test_reject_moves_the_quotation_to_rejected(client, env, quotation):
    share = _shared_sent_quotation(env, quotation)
    client.post(f"/s/{share.token}/decision/", {"decision": "rejected", "name": "سامي"})
    quotation.refresh_from_db()
    assert quotation.status == SalesQuotation.STATUS_REJECTED


def test_second_decision_is_refused_with_409(client, env, quotation):
    """ضغطتان على «موافق» من جوالٍ بطيء طلبان — والثاني يرتدّ لا يُعيد الكتابة."""
    share = _shared_sent_quotation(env, quotation)
    client.post(f"/s/{share.token}/decision/", {"decision": "accepted", "name": "أول"})
    second = client.post(
        f"/s/{share.token}/decision/", {"decision": "rejected", "name": "ثانٍ"},
    )
    assert second.status_code == 409
    share.refresh_from_db()
    quotation.refresh_from_db()
    assert share.decision == "accepted"
    assert share.decided_name == "أول"
    assert quotation.status == SalesQuotation.STATUS_ACCEPTED


def test_decision_without_a_name_is_refused(client, env, quotation):
    share = _shared_sent_quotation(env, quotation)
    response = client.post(f"/s/{share.token}/decision/", {"decision": "accepted", "name": "  "})
    assert response.status_code == 409
    quotation.refresh_from_db()
    assert quotation.status == SalesQuotation.STATUS_SENT


def test_decision_on_a_converted_quotation_is_refused(client, env, quotation):
    """العرض المحوَّل إلى فاتورة انتهى أمره — والقرار عليه بلا معنى."""
    share = _shared_sent_quotation(env, quotation)
    # تحويل العرض إلى فاتورة يمرّ بـ«مقبول» في الشاشة؛ هنا نضع الحالة
    # النهائية مباشرةً لأن المقصود اختبارُ القرار المتأخّر لا مسارُ التحويل.
    SalesQuotation.objects.filter(pk=quotation.pk).update(
        status=SalesQuotation.STATUS_CONVERTED,
    )

    response = client.post(
        f"/s/{share.token}/decision/", {"decision": "accepted", "name": "متأخر"},
    )
    assert response.status_code == 409
    share.refresh_from_db()
    assert share.decision == ""


def test_invoice_link_accepts_no_decision(client, env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    response = client.post(
        f"/s/{share.token}/decision/", {"decision": "accepted", "name": "أي أحد"},
    )
    assert response.status_code == 409
    share.refresh_from_db()
    assert share.decision == ""


def test_decision_on_a_revoked_link_is_410(client, env, quotation):
    share = _shared_sent_quotation(env, quotation)
    services.revoke_share(share)
    response = client.post(
        f"/s/{share.token}/decision/", {"decision": "accepted", "name": "متأخر"},
    )
    assert response.status_code == 410
    quotation.refresh_from_db()
    assert quotation.status == SalesQuotation.STATUS_SENT


def test_decided_page_shows_the_outcome_and_hides_the_buttons(client, env, quotation):
    share = _shared_sent_quotation(env, quotation)
    client.post(f"/s/{share.token}/decision/", {"decision": "accepted", "name": "ليلى"})
    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "تمت الموافقة على هذا العرض" in html
    assert "ليلى" in html
    assert "موافق على العرض" not in html


def test_expired_offer_hides_the_decision_form(client, env, quotation):
    """انقضاء `valid_until` يُخفي الأزرار — بلا تغيير الحالة في القاعدة.

    إسقاط العرض إلى «منتهي» قرارُ النظام لا قرارُ زائرٍ فتح صفحة.
    """
    share = _shared_sent_quotation(env, quotation)
    quotation.valid_until = "2020-01-01"
    quotation.save(update_fields=["valid_until"])

    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "موافق على العرض" not in html
    assert "منتهي الصلاحية" in html

    quotation.refresh_from_db()
    assert quotation.status == SalesQuotation.STATUS_SENT


def test_decision_is_written_to_the_activity_log(client, env, quotation):
    from core.models import ActivityLog

    share = _shared_sent_quotation(env, quotation)
    client.post(f"/s/{share.token}/decision/", {"decision": "accepted", "name": "رامي"})

    entry = ActivityLog.objects.filter(
        tenant=env["tenant"], entity_type="sales_quotation", entity_id=quotation.pk,
    ).order_by("-id").first()
    assert entry is not None
    assert entry.metadata.get("source") == "public_share"
    assert entry.metadata.get("decided_by_name") == "رامي"
    # `action` محصور بـ`choices` النموذج: قيمة أطول تُلغي القيد بصمت على MySQL.
    assert entry.action in dict(ActivityLog.ACTIONS)
    assert len(entry.action) <= 20
