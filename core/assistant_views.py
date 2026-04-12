"""
بروكسي المساعد الذكي → webhook n8n (POST JSON).
لا يُعرَّض رابط n8n للمتصفح؛ الطلب يمر عبر Django بعد المصادقة.
"""
from __future__ import annotations

import logging

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser

logger = logging.getLogger(__name__)


def _extract_reply(payload):
    """يتوافق مع {reply} أو {output} أو أشكال شائعة من n8n / LLM."""
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


@api_view(["POST"])
@authentication_classes(ApiAuthAndUser["authentication_classes"])
@permission_classes(ApiAuthAndUser["permission_classes"])
def assistant_chat(request):
    """
    الطلب:  { "message": "نص السؤال" }
    النجاح: { "reply": "..." }  (يُستخرج من reply أو output في رد n8n)
    """
    raw = request.data.get("message")
    message = (raw if isinstance(raw, str) else str(raw or "")).strip()
    if not message:
        return Response(
            {"detail": "حقل message مطلوب وغير فارغ."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    url = getattr(settings, "N8N_ASSISTANT_WEBHOOK_URL", "") or ""
    if not str(url).strip():
        return Response(
            {
                "detail": "لم يُضبط رابط المساعد. أضف N8N_ASSISTANT_WEBHOOK_URL في البيئة أو settings."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    timeout = getattr(settings, "N8N_ASSISTANT_WEBHOOK_TIMEOUT", 300)
    try:
        upstream = requests.post(
            str(url).strip(),
            json={"message": message},
            headers={"Content-Type": "application/json"},
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
            {"detail": "تعذر الوصول إلى خدمة المساعد. تأكد من أن n8n يعمل على الخادم."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except requests.RequestException as exc:
        logger.warning("assistant_chat upstream error: %s", exc)
        return Response(
            {"detail": f"تعذر الاتصال بخدمة المساعد: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    try:
        body = upstream.json()
    except ValueError:
        text = (upstream.text or "").strip()
        if not upstream.ok:
            return Response(
                {"detail": text or f"خطأ من الخدمة الخارجية ({upstream.status_code})"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"reply": text})

    if not upstream.ok:
        err = _extract_reply(body) or str(body)
        return Response(
            {"detail": err or f"خطأ من الخدمة الخارجية ({upstream.status_code})"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    reply = _extract_reply(body)
    if not reply and isinstance(body, dict):
        reply = str(body).strip() if body else ""

    return Response({"reply": reply or ""})
