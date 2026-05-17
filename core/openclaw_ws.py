"""
اتصال OpenClaw عبر WebSocket (websocket-client).
الرابط النموذجي: ws://host:18789/v1/messages?token=...
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import websocket
except ImportError:  # pragma: no cover
    websocket = None  # type: ignore


def _http_to_ws(http_url: str) -> str:
    u = http_url.strip()
    if u.startswith("https://"):
        return "wss://" + u[8:]
    if u.startswith("http://"):
        return "ws://" + u[7:]
    if u.startswith("wss://") or u.startswith("ws://"):
        return u
    return u


def build_ws_messages_url() -> str:
    """
    يبني عنوان الاتصال بـ /v1/messages عبر WS مع token في query (كما يتوقع OpenClaw).
    """
    explicit = (getattr(settings, "OPENCLAW_WS_MESSAGES_URL", "") or "").strip()
    if explicit:
        base = explicit
    else:
        http = (getattr(settings, "OPENCLAW_MESSAGES_URL", "") or "").strip()
        base = _http_to_ws(http)
    token = (getattr(settings, "OPENCLAW_BEARER_TOKEN", "") or "").strip()
    if not token or not base:
        return ""
    parsed = urlparse(base)
    q = dict(parse_qsl(parsed.query, keep_blank_values=True))
    q["token"] = token
    new_query = urlencode(q)
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )


def probe_websocket(timeout: float = 15.0) -> dict[str, Any]:
    """
    تجربة: اتصال + إرسال JSON خفيف + انتظار رد واحد (إن وُجد).
    """
    if websocket is None:
        return {
            "ok": False,
            "error": "missing_dependency",
            "detail": "ثبّت الحزمة: pip install websocket-client",
        }
    url = build_ws_messages_url()
    if not url:
        return {"ok": False, "error": "no_url", "detail": "OPENCLAW_MESSAGES_URL أو التوكن غير مضبوط."}

    safe_log = url.split("token=")[0] + "token=***" if "token=" in url else url
    t0 = time.perf_counter()
    ws = None
    try:
        ws = websocket.create_connection(url, timeout=timeout)
        ws.settimeout(timeout)
        ping = {
            "channel": "api",
            "message": "ping",
            "chatId": "django-ws-probe",
        }
        ws.send(json.dumps(ping))
        try:
            raw = ws.recv()
        except Exception as recv_exc:
            logger.warning("openclaw_ws probe recv: %s", recv_exc)
            raw = None
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        out: dict[str, Any] = {
            "ok": True,
            "connected": True,
            "ws_url_logged": safe_log,
            "latency_ms": elapsed_ms,
        }
        if raw is not None:
            out["received_preview"] = (raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw))[:800]
        else:
            out["received_preview"] = None
            out["note"] = "اتصل بنجاح لكن لم يُستلم رد خلال المهلة (قد يكون السلوك طبيعياً)."
        return out
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning("openclaw_ws probe failed url=%s err=%s", safe_log, exc)
        return {
            "ok": False,
            "error": "websocket_error",
            "detail": str(exc)[:500],
            "ws_url_logged": safe_log,
            "latency_ms": elapsed_ms,
        }
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def send_chat_payload(body: dict, timeout: float) -> tuple[str | None, str | None]:
    """
    يُرسل جسم الرسالة (نفس حقول HTTP) عبر WebSocket ويستلم نص الرد.
    يعيد (reply_or_none, error_or_none).
    """
    if websocket is None:
        return None, "websocket-client غير مثبت. نفّذ: pip install websocket-client"
    url = build_ws_messages_url()
    if not url:
        return None, "عنوان WS أو التوكن غير مضبوط."
    ws = None
    try:
        ws = websocket.create_connection(url, timeout=timeout)
        ws.settimeout(timeout)
        ws.send(json.dumps(body))
        raw = ws.recv()
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        return text.strip(), None
    except Exception as exc:
        logger.warning("openclaw_ws send_chat: %s", exc)
        return None, str(exc)[:500]
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
