"""اختبارات جسر واتساب (Evolution API) ↔ المساعد الذكي.

الحارس الأمني الوحيد هو WhatsAppContact (رقم → شركة) + سرّ الرابط. نتحقق من
رفض السرّ الخاطئ، تجاهل رسائل البوت نفسه والمجموعات، رفض الأرقام غير
المسجَّلة، وأهم شيء: أن الرد فعلاً محصور بشركة الرقم المطابق ولا يرى شركة
أخرى — عبر تزييف Ollama (لا اتصال شبكة حقيقي في هذا الاختبار).
"""
import json
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency, WhatsAppContact
from tenants.services import create_company

pytestmark = pytest.mark.django_db

SECRET = "test-secret-token"
WEBHOOK_PATH = f"/api/assistant/whatsapp/webhook/{SECRET}/"


def _upsert_payload(*, remote_jid, text, from_me=False):
    return {
        "event": "messages.upsert",
        "instance": "ktra-test",
        "data": {
            "key": {"remoteJid": remote_jid, "fromMe": from_me, "id": "ABC123"},
            "pushName": "Tester",
            "message": {"conversation": text},
        },
    }


@pytest.fixture
def env():
    owner = User.objects.create_user(username="wa", password="x", is_superuser=True)
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    a = create_company("شركة أ", owner)
    b = create_company("شركة ب", owner)

    ashraf_a = Partner.objects.create(tenant=a, name="أشرف عجل", partner_type="Customer")
    SalesInvoice.objects.create(
        tenant=a, invoice_number="A-1", customer=ashraf_a, currency=cur,
        invoice_date="2026-06-01", invoice_kind="sale",
        status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("500"),
    )
    ashraf_b = Partner.objects.create(tenant=b, name="أشرف عجل", partner_type="Customer")
    SalesInvoice.objects.create(
        tenant=b, invoice_number="B-1", customer=ashraf_b, currency=cur,
        invoice_date="2026-06-01", invoice_kind="sale",
        status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("9999"),
    )

    WhatsAppContact.objects.create(phone_number="972500000001", tenant=a, is_active=True)
    WhatsAppContact.objects.create(phone_number="972500000009", tenant=b, is_active=False)
    return a, b


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET)
def test_wrong_secret_returns_404(env, client: Client):
    resp = client.post(
        "/api/assistant/whatsapp/webhook/wrong-token/",
        data=json.dumps(_upsert_payload(remote_jid="972500000001@s.whatsapp.net", text="hi")),
        content_type="application/json",
    )
    assert resp.status_code == 404


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET, OLLAMA_API_KEY="x", OLLAMA_MODEL="m")
def test_event_suffix_url_variant_also_works(env, client: Client):
    """Evolution قد يضيف اسم الحدث لآخر الرابط (webhookByEvents) — نقبله أيضاً."""
    a, _ = env
    with patch("core.whatsapp_views._send_reply") as send, \
         patch("core.ollama_assistant.chat") as chat:
        chat.return_value = "رد"
        resp = client.post(
            WEBHOOK_PATH + "messages-upsert/",
            data=json.dumps(_upsert_payload(
                remote_jid="972500000001@s.whatsapp.net", text="سؤال")),
            content_type="application/json",
        )
    assert resp.status_code == 200
    chat.assert_called_once()
    send.assert_called_once()


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET, OLLAMA_API_KEY="x", OLLAMA_MODEL="m")
def test_event_suffix_without_trailing_slash_does_not_redirect(env, client: Client):
    """
    Evolution يبعث .../messages-upsert بلا شرطة مائلة بالآخر — تأكّدنا من سجلات
    الإنتاج. اعتماد Django على APPEND_SLASH كان يحوّل الطلب لـGET ويُفقِد الرسالة
    (301 يحوّل POST→GET) — هذا الاختبار يمنع رجوع الخلل.
    """
    a, _ = env
    with patch("core.whatsapp_views._send_reply") as send, \
         patch("core.ollama_assistant.chat") as chat:
        chat.return_value = "رد"
        resp = client.post(
            WEBHOOK_PATH + "messages-upsert",  # بلا / بالآخر عمداً
            data=json.dumps(_upsert_payload(
                remote_jid="972500000001@s.whatsapp.net", text="سؤال")),
            content_type="application/json",
        )
    assert resp.status_code == 200  # لا 301/301
    chat.assert_called_once()
    send.assert_called_once()


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET)
def test_malformed_body_encoding_is_ignored_not_500(env, client: Client):
    """جسم بترميز غير UTF-8 صالح يجب أن يُتجاهل بأمان لا أن يُسقِط الخادم (500)."""
    resp = client.post(
        WEBHOOK_PATH,
        data=b"\xca\xfe\xba\xbe not valid utf-8",
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ignored"] == "invalid body"


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET)
def test_from_me_is_ignored(env, client: Client):
    with patch("core.whatsapp_views._send_reply") as send:
        resp = client.post(
            WEBHOOK_PATH,
            data=json.dumps(_upsert_payload(
                remote_jid="972500000001@s.whatsapp.net", text="hi", from_me=True)),
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert resp.json()["ignored"] == "own message"
    send.assert_not_called()


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET)
def test_group_chat_is_ignored(env, client: Client):
    with patch("core.whatsapp_views._send_reply") as send:
        resp = client.post(
            WEBHOOK_PATH,
            data=json.dumps(_upsert_payload(remote_jid="12345-6789@g.us", text="hi")),
            content_type="application/json",
        )
    assert resp.json()["ignored"] == "group chat"
    send.assert_not_called()


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET)
def test_unregistered_number_gets_no_assistant_reply(env, client: Client):
    with patch("core.whatsapp_views._send_reply") as send, \
         patch("core.ollama_assistant.chat") as chat:
        resp = client.post(
            WEBHOOK_PATH,
            data=json.dumps(_upsert_payload(
                remote_jid="972599999999@s.whatsapp.net", text="كم بعنا؟")),
            content_type="application/json",
        )
    assert resp.status_code == 200
    chat.assert_not_called()  # لا يصل للمساعد إطلاقاً
    send.assert_called_once()
    assert "غير مصرَّح" in send.call_args[0][1]


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET)
def test_inactive_contact_is_treated_as_unregistered(env, client: Client):
    with patch("core.whatsapp_views._send_reply") as send, \
         patch("core.ollama_assistant.chat") as chat:
        client.post(
            WEBHOOK_PATH,
            data=json.dumps(_upsert_payload(
                remote_jid="972500000009@s.whatsapp.net", text="كم بعنا؟")),
            content_type="application/json",
        )
    chat.assert_not_called()
    send.assert_called_once()


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET, OLLAMA_API_KEY="x", OLLAMA_MODEL="m")
def test_registered_number_gets_reply_scoped_to_its_own_company(env, client: Client):
    a, b = env
    with patch("core.whatsapp_views._send_reply") as send, \
         patch("core.ollama_assistant.chat") as chat:
        chat.return_value = "الرد النهائي"
        client.post(
            WEBHOOK_PATH,
            data=json.dumps(_upsert_payload(
                remote_jid="972500000001@s.whatsapp.net", text="كم بعنا لأشرف؟")),
            content_type="application/json",
        )
    # chat استُدعي بشركة أ (صاحبة الرقم) لا شركة ب — رغم أن كلا الشركتين
    # فيهما عميل بنفس الاسم بمبالغ مختلفة (500 مقابل 9999)
    chat.assert_called_once()
    called_text, called_tenant = chat.call_args[0]
    assert called_text == "كم بعنا لأشرف؟"
    assert called_tenant.pk == a.pk
    send.assert_called_once_with("972500000001", "الرد النهائي")


@override_settings(WHATSAPP_WEBHOOK_SECRET=SECRET)
def test_non_text_message_prompts_for_text(env, client: Client):
    payload = _upsert_payload(remote_jid="972500000001@s.whatsapp.net", text="")
    payload["data"]["message"] = {"audioMessage": {"seconds": 5}}
    with patch("core.whatsapp_views._send_reply") as send:
        client.post(WEBHOOK_PATH, data=json.dumps(payload), content_type="application/json")
    send.assert_called_once()
    assert "نص" in send.call_args[0][1]
