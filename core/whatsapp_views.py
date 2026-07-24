"""
جسر واتساب ↔ المساعد الذكي عبر Evolution API (self-hosted، غير رسمي).

المسار: واتساب → Evolution API → POST هنا (webhook) → المساعد (Ollama+SQL)
→ الرد يُرسَل رجوعاً عبر Evolution API إلى نفس الرقم.

**الأمان يعتمد بالكامل على WhatsAppContact (tenants.models)** — رقم غير
مُدرَج/غير نشط لا يحصل على أي رد مهما كانت رسالته. لا نثق بأي حقل ضمن
جسم الطلب لتحديد الشركة؛ فقط رقم المرسل بعد مطابقته بالجدول.

حماية الرابط: توكن سرّي مضمَّن في مسار الـ URL نفسه (WHATSAPP_WEBHOOK_SECRET)
— أبسط آلية تعمل بلا اعتماد على دعم Evolution لهيدرز مخصّصة، وكافية لأن
الرابط لا يُنشر ولا يظهر إلا في إعداد Evolution.
"""
from __future__ import annotations

import hmac
import json
import logging

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

# جولات الأدوات مع نموذج بطيء (gpt-oss:120b) قد تستغرق دقيقة على واتساب أيضاً؛
# نفس مهلة OLLAMA_ASSISTANT_TIMEOUT تكفي — لا حاجة لقيمة منفصلة هنا.
_SEND_TIMEOUT = 30


def _secret_ok(provided: str) -> bool:
    expected = (getattr(settings, "WHATSAPP_WEBHOOK_SECRET", "") or "").strip()
    if not expected:
        return False
    return hmac.compare_digest(provided or "", expected)


def _normalize_phone(remote_jid: str) -> str:
    """يستخرج الأرقام فقط من jid مثل '972501234567@s.whatsapp.net'."""
    if not remote_jid:
        return ""
    digits_part = remote_jid.split("@")[0]
    return "".join(ch for ch in digits_part if ch.isdigit())


def _extract_text(message: dict) -> str:
    """يدعم أشكال الرسائل النصية الشائعة في حمولة Baileys/Evolution."""
    if not isinstance(message, dict):
        return ""
    if message.get("conversation"):
        return str(message["conversation"]).strip()
    ext = message.get("extendedTextMessage")
    if isinstance(ext, dict) and ext.get("text"):
        return str(ext["text"]).strip()
    # صور/مستندات بتعليق — نجيب على التعليق كسؤال إن وُجد
    for key in ("imageMessage", "documentMessage", "videoMessage"):
        node = message.get(key)
        if isinstance(node, dict) and node.get("caption"):
            return str(node["caption"]).strip()
    return ""


def _send_reply(number: str, text: str) -> None:
    base = (getattr(settings, "EVOLUTION_API_BASE_URL", "") or "").strip().rstrip("/")
    key = (getattr(settings, "EVOLUTION_API_KEY", "") or "").strip()
    instance = (getattr(settings, "EVOLUTION_INSTANCE_NAME", "") or "").strip()
    if not (base and key and instance):
        logger.warning("[whatsapp] EVOLUTION_* غير مضبوطة — تعذّر إرسال الرد.")
        return
    try:
        requests.post(
            f"{base}/message/sendText/{instance}",
            json={"number": number, "text": text},
            headers={"apikey": key, "Content-Type": "application/json"},
            timeout=_SEND_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("[whatsapp] فشل إرسال الرد إلى %s عبر Evolution: %s", number, exc)


@csrf_exempt
@require_POST
def whatsapp_webhook(request, secret: str, event_suffix: str | None = None):
    """
    POST /api/assistant/whatsapp/webhook/<secret>/ أو .../<secret>/<event_suffix>/
    يُستدعى من Evolution API عند وصول رسالة (event=messages.upsert). event_suffix
    (مثل messages-upsert) قد تضيفه Evolution تلقائياً حسب إعداد عام بسيرفرها —
    غير مستخدَم هنا، نعتمد على event داخل جسم الطلب لتحديد نوع الحدث الفعلي.
    يرجع 200 دائماً (حتى عند التجاهل) كي لا يعيد Evolution محاولة الإرسال.
    """
    if not _secret_ok(secret):
        logger.warning("[whatsapp] webhook secret غير مطابق — طلب مرفوض.")
        return HttpResponse(status=404)  # لا نكشف وجود المسار لسرّ خاطئ

    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        # ValueError يغطي JSONDecodeError وUnicodeDecodeError (جسم بترميز غير UTF-8)
        return JsonResponse({"ignored": "invalid body"})

    event = str(payload.get("event") or "")
    if "upsert" not in event.lower():
        return JsonResponse({"ignored": f"event={event}"})

    data = payload.get("data") or {}
    key = data.get("key") or {}

    if key.get("fromMe"):
        return JsonResponse({"ignored": "own message"})  # صدى رسالة أرسلها البوت نفسه

    remote_jid = str(key.get("remoteJid") or "")
    if remote_jid.endswith("@g.us"):
        return JsonResponse({"ignored": "group chat"})  # لا نرد داخل مجموعات إطلاقاً

    phone = _normalize_phone(remote_jid)
    if not phone:
        return JsonResponse({"ignored": "no phone"})

    text = _extract_text(data.get("message") or {})
    if not text:
        _send_reply(phone, "أرسل سؤالك كنص فقط (بدون صوت/ملصق) وسأجيبك.")
        return JsonResponse({"ok": True, "note": "non-text message"})

    from tenants.models import WhatsAppContact

    contact = (
        WhatsAppContact.objects.filter(phone_number=phone, is_active=True)
        .select_related("tenant")
        .first()
    )
    if contact is None:
        logger.info("[whatsapp] رقم غير مسجَّل تجاهُله: %s", phone)
        _send_reply(phone, "هذا الرقم غير مصرَّح له باستخدام المساعد الذكي. تواصل مع إدارة النظام.")
        return JsonResponse({"ok": True, "note": "unregistered number"})

    from core import ollama_assistant

    if not ollama_assistant.is_configured():
        _send_reply(phone, "المساعد غير مُفعَّل حالياً على الخادم.")
        return JsonResponse({"ok": True, "note": "assistant not configured"})

    try:
        reply = ollama_assistant.chat(text, contact.tenant)
    except requests.exceptions.Timeout:
        reply = "طلبك يستغرق وقتاً أطول من المعتاد. حاول تحديد سؤالك أكثر."
    except requests.RequestException as exc:
        logger.warning("[whatsapp] ollama upstream error tenant=%s: %s", contact.tenant_id, exc)
        reply = "تعذّر الوصول لخدمة المساعد حالياً."
    except Exception:  # noqa: BLE001
        logger.exception("[whatsapp] assistant failed tenant=%s", contact.tenant_id)
        reply = "تعذّر إكمال طلبك، حاول مجدداً."

    _send_reply(phone, reply or "لم أحصل على رد. حاول إعادة صياغة سؤالك.")
    return JsonResponse({"ok": True})
