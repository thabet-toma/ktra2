"""
بروكسي المساعد الذكي → OpenClaw على مضيف بعيد.
- الرسائل: WebSocket (ws://…/v1/messages?token=…) عند OPENCLAW_USE_WEBSOCKET، ثم تراجع لـ HTTP POST عند الفشل.
- الملفات: POST multipart كالسابق.
OpenClaw ليس على نفس آلة Django؛ الاتصال صادر من خادم التطبيق.
لا يُعرَّض التوكن للمتصفح؛ الطلب يمر عبر Django بعد المصادقة.
"""
from __future__ import annotations

import json
import logging
import time

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core import openclaw_ws

logger = logging.getLogger(__name__)

# OpenClaw: POST /v1/messages غالباً غير موجود (404) — البوابة الحقيقية WebSocket + connect؛ HTTP قد يكون /v1/responses إن فُعّل.
OPENCLAW_CHAT_MISMATCH_AR = (
    "بوابة OpenClaw هنا لا تستجيب لـ POST على مسار /v1/messages (غالباً 404). "
    "اختبار WebSocket ينجح لأنه يفتح الاتصال فقط، أما الدردشة فتحتاج واجهة HTTP مفعّلة (مثل POST /v1/responses في إعداد البوابة) "
    "أو عميل WebSocket كامل بعد قبول اقتران الجهاز (pairing) من لوحة التحكم."
)


def _messages_url() -> str:
    return (getattr(settings, "OPENCLAW_MESSAGES_URL", "") or "").strip()


def _files_url() -> str:
    return (getattr(settings, "OPENCLAW_FILES_URL", "") or "").strip()


def _bearer_token() -> str:
    return (getattr(settings, "OPENCLAW_BEARER_TOKEN", "") or "").strip()


def _assistant_timeout() -> int:
    return int(getattr(settings, "OPENCLAW_ASSISTANT_TIMEOUT", 600) or 600)


def _openclaw_headers(*, json_request: bool) -> dict:
    """
    كل طلب إلى OpenClaw (رسائل أو ملفات) يجب أن يتضمن:
        Authorization: Bearer <OPENCLAW_BEARER_TOKEN>
    """
    token = _bearer_token()
    if not token:
        return {}
    headers = {"Authorization": f"Bearer {token}"}
    if json_request:
        headers["Content-Type"] = "application/json"
    return headers


def _extract_upstream_error(payload) -> str:
    """استخراج نص خطأ من JSON (لا يستخدم حقل message كنجاح — يُفضّل detail)."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("detail", "error", "message", "title", "reason"):
            v = payload.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
    return str(payload).strip()


def _extract_reply(payload):
    """يتوافق مع {reply} أو {output} أو أشكال شائعة من OpenClaw."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list) and payload:
        return _extract_reply(payload[0])
    if isinstance(payload, dict):
        for key in ("reply", "output", "text", "message", "answer"):
            v = payload.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict) and msg.get("content"):
                return str(msg["content"]).strip()
        data = payload.get("data")
        if data is not None:
            inner = _extract_reply(data)
            if inner:
                return inner
    return ""


def _normalize_file_ids(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        return [s] if s else []
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                out.append(s)
        return out
    return []


def _extract_file_id(payload) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("fileId", "file_id", "id", "uid"):
            v = payload.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
        data = payload.get("data")
        if isinstance(data, dict):
            inner = _extract_file_id(data)
            if inner:
                return inner
    return ""


@api_view(["POST"])
@authentication_classes(ApiAuthAndUser["authentication_classes"])
@permission_classes(ApiAuthAndUser["permission_classes"])
def assistant_chat(request):
    """
    الطلب:  { "message": "نص", اختياري "file_ids": ["..."] }
    النجاح: { "reply": "..." }
    """
    raw = request.data.get("message")
    message = (raw if isinstance(raw, str) else str(raw or "")).strip()
    file_ids = _normalize_file_ids(
        request.data.get("file_ids") or request.data.get("fileIds")
    )

    if not message and not file_ids:
        return Response(
            {"detail": "أدخل نصاً أو أرفق ملفاً (أو الاثنين)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    url = _messages_url()
    if not url:
        return Response(
            {"detail": "لم يُضبط رابط المساعد. أضف OPENCLAW_MESSAGES_URL في البيئة أو settings."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not _bearer_token():
        return Response(
            {
                "detail": "لم يُضبط توكن OpenClaw. أضف OPENCLAW_BEARER_TOKEN في بيئة الخادم."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    timeout = _assistant_timeout()
    uid = getattr(request.user, "pk", None)
    chat_id = f"user-{uid}" if uid is not None else "anonymous"
    text = message
    if file_ids:
        refs = "\n".join(f"[file:{fid}]" for fid in file_ids)
        text = f"{message}\n\n{refs}".strip() if message else refs
    body: dict = {
        "channel": "api",
        "message": text,
        "chatId": chat_id,
    }
    if file_ids:
        body["fileIds"] = file_ids

    use_ws = bool(getattr(settings, "OPENCLAW_USE_WEBSOCKET", False))
    if use_ws:
        raw, ws_err = openclaw_ws.send_chat_payload(body, float(timeout))
        if ws_err is None and raw is not None:
            try:
                parsed = json.loads(raw)
                reply = _extract_reply(parsed) if isinstance(parsed, (dict, list)) else str(parsed).strip()
            except json.JSONDecodeError:
                reply = raw.strip()
            if not reply.strip():
                reply = "تم إرسال رسالتك. سيصلك الرد قريباً إن كانت الخدمة تعمل بلا رد فوري."
            return Response({"reply": reply})
        logger.warning("OpenClaw WebSocket غير متاح أو فشل؛ التراجع لـ HTTP: %s", ws_err)

    headers = _openclaw_headers(json_request=True)

    try:
        upstream = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        logger.warning("assistant_chat timeout after %ss url=%s", timeout, url)
        return Response(
            {"detail": "المساعد يعالج طلبك لكنه يستغرق وقتاً أطول من المعتاد. حاول مرة أخرى أو اجعل سؤالك أكثر تحديداً."},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        logger.warning("assistant_chat connection error url=%s", url)
        return Response(
            {"detail": "تعذر الوصول إلى خدمة المساعد. تحقق من تشغيل البوابة والشبكة."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except requests.RequestException as exc:
        logger.warning("assistant_chat upstream error: %s", exc)
        return Response(
            {"detail": f"تعذر الاتصال بخدمة المساعد: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        body_json = upstream.json()
    except ValueError:
        text = (upstream.text or "").strip()
        if not upstream.ok:
            if upstream.status_code == 404:
                return Response(
                    {"detail": OPENCLAW_CHAT_MISMATCH_AR},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response(
                {"detail": text or f"خطأ من الخدمة الخارجية ({upstream.status_code})"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"reply": text})

    if not upstream.ok:
        err = _extract_upstream_error(body_json)
        if not err:
            err = _extract_reply(body_json) or str(body_json)
        logger.warning(
            "assistant_chat upstream HTTP %s url=%s body=%s",
            upstream.status_code,
            url,
            err[:500] if err else upstream.text[:500],
        )
        if upstream.status_code == 404:
            return Response(
                {"detail": OPENCLAW_CHAT_MISMATCH_AR},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "detail": err
                or f"خطأ من خدمة المساعد (HTTP {upstream.status_code}). تحقق من الرابط والتوكن."
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    reply = _extract_reply(body_json)
    if not reply and isinstance(body_json, dict):
        reply = str(body_json).strip() if body_json else ""

    if not reply.strip() and upstream.ok:
        reply = "تم إرسال رسالتك. سيصلك الرد قريباً إن كانت الخدمة تعمل بلا رد فوري."

    return Response({"reply": reply or ""})


@api_view(["POST"])
@authentication_classes(ApiAuthAndUser["authentication_classes"])
@permission_classes(ApiAuthAndUser["permission_classes"])
def assistant_upload(request):
    """
    رفع ملف (PDF وغيره) إلى OpenClaw — حقل النموذج: file
    النجاح: { "file_id": "..." }
    """
    f = request.FILES.get("file")
    if not f:
        return Response(
            {"detail": "حقل file مطلوب."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    url = _files_url()
    if not url:
        return Response(
            {"detail": "لم يُضبط OPENCLAW_FILES_URL."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not _bearer_token():
        return Response(
            {"detail": "لم يُضبط OPENCLAW_BEARER_TOKEN في بيئة الخادم."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    timeout = min(_assistant_timeout(), 600)
    content_type = getattr(f, "content_type", None) or "application/octet-stream"
    try:
        f.seek(0)
        payload = f.read()
    except Exception as exc:
        logger.warning("assistant_upload read error: %s", exc)
        return Response(
            {"detail": "تعذر قراءة الملف."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    files = {"file": (f.name, payload, content_type)}

    try:
        upstream = requests.post(
            url,
            files=files,
            headers=_openclaw_headers(json_request=False),
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        logger.warning("assistant_upload timeout url=%s", url)
        return Response(
            {"detail": "انتهت مهلة رفع الملف."},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        logger.warning("assistant_upload connection error url=%s", url)
        return Response(
            {"detail": "تعذر الاتصال بخدمة رفع الملفات."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except requests.RequestException as exc:
        logger.warning("assistant_upload upstream error: %s", exc)
        return Response(
            {"detail": f"تعذر رفع الملف: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        data = upstream.json()
    except ValueError:
        text = (upstream.text or "").strip()
        if not upstream.ok:
            return Response(
                {"detail": text or f"خطأ رفع ({upstream.status_code})"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {"detail": "استجابة غير متوقعة من خدمة الملفات."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    if not upstream.ok:
        err = _extract_upstream_error(data) or _extract_reply(data) or str(data)
        return Response(
            {"detail": err or f"خطأ رفع ({upstream.status_code})"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    fid = _extract_file_id(data)
    if not fid:
        logger.warning("assistant_upload: no file id in response keys=%s", list(data.keys()) if isinstance(data, dict) else type(data))
        return Response(
            {"detail": "لم يُعاد معرّف الملف من الخدمة."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response({"file_id": fid})


@api_view(["GET"])
@authentication_classes(ApiAuthAndUser["authentication_classes"])
@permission_classes(ApiAuthAndUser["permission_classes"])
def assistant_openclaw_status(request):
    """
    يعمل على **خادم Django** (مسار API تبع التطبيق)، ليس على سيرفر OpenClaw.
    من هنا نرسل طلباً صادراً إلى OPENCLAW_STATUS_URL (مثل http://72.60...:18789/v1/status).
    """
    status_url = (getattr(settings, "OPENCLAW_STATUS_URL", "") or "").strip()
    if not status_url:
        return Response(
            {"detail": "لم يُضبط OPENCLAW_STATUS_URL."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not _bearer_token():
        return Response(
            {"detail": "لم يُضبط OPENCLAW_BEARER_TOKEN."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    timeout = min(30, _assistant_timeout())
    headers = {"Authorization": f"Bearer {_bearer_token()}"}
    t0 = time.perf_counter()

    try:
        upstream = requests.get(status_url, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return Response(
            {
                "ok": False,
                "error": "timeout",
                "checked_from": "django_application_server",
                "openclaw_status_url": status_url,
                "latency_ms": elapsed_ms,
                "hints_ar": [
                    f"انتهت مهلة الاتصال من خادم Django إلى {status_url}.",
                    "جرّب فتح نفس الرابط من متصفح جهازك؛ إن فشل الاثنان قد يكون المنفذ مسكراً عند مزود الاستضافة (Inbound على سيرفر OpenClaw).",
                ],
            },
            status=status.HTTP_200_OK,
        )
    except requests.exceptions.ConnectionError as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning("assistant_openclaw_status connection error url=%s exc=%s", status_url, exc)
        return Response(
            {
                "ok": False,
                "error": "connection_error",
                "error_detail": str(exc)[:300],
                "checked_from": "django_application_server",
                "openclaw_status_url": status_url,
                "latency_ms": elapsed_ms,
                "hints_ar": [
                    "رفض الاتصال أو تعذر الوصول — غالباً جدار حماية أو المنفذ غير مفتوح للوصول من شبكة خادم Django.",
                    "افتح من متصفحك نفس عنوان /v1/status على IP الخارجي؛ إن نجح من المتصفح وفشل هنا، راجع حظر الصادر من سيرفر التطبيق أو مسار الشبكة بين السيرفرين.",
                ],
            },
            status=status.HTTP_200_OK,
        )
    except requests.RequestException as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning("assistant_openclaw_status error url=%s exc=%s", status_url, exc)
        return Response(
            {
                "ok": False,
                "error": "request_error",
                "error_detail": str(exc)[:300],
                "checked_from": "django_application_server",
                "openclaw_status_url": status_url,
                "latency_ms": elapsed_ms,
            },
            status=status.HTTP_200_OK,
        )

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    text = (upstream.text or "").strip()
    preview = text[:400]
    ok_http = 200 <= upstream.status_code < 300

    body: dict = {
        "ok": ok_http,
        "checked_from": "django_application_server",
        "openclaw_status_url": status_url,
        "http_status": upstream.status_code,
        "latency_ms": elapsed_ms,
        "body_preview": preview,
    }

    if not ok_http:
        body["hints_ar"] = [
            "الاستجابة من OpenClaw ليست نجاح HTTP 2xx. إن كان المنفذ يعمل من المتصفح، راجع التوكن أو أن نقطة /v1/status تتطلب إعداداً مختلفاً.",
        ]

    return Response(body)


@api_view(["GET"])
@authentication_classes(ApiAuthAndUser["authentication_classes"])
@permission_classes(ApiAuthAndUser["permission_classes"])
def assistant_openclaw_ws_probe(request):
    """تجربة اتصال WebSocket إلى ws://…/v1/messages?token=… (من خادم Django فقط)."""
    t = min(30.0, float(_assistant_timeout()))
    return Response(openclaw_ws.probe_websocket(timeout=t))
