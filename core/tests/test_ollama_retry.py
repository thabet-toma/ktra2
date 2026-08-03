"""اختبار مرونة _post_chat — إعادة محاولة واحدة عند فشل عابر (429/5xx/شبكة).

الخطة المجانية لـ Ollama تُقيّد لحظياً تحت رسائل متتابعة؛ إعادة المحاولة تمنع
فشلاً عابراً من الوصول للمستخدم كـ«تعذّر الوصول».
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from core import ollama_assistant


def _resp(status, json_body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body or {}
    if status >= 400:
        r.raise_for_status.side_effect = requests.exceptions.HTTPError(response=r)
    else:
        r.raise_for_status.return_value = None
    return r


def test_post_chat_retries_once_on_429_then_succeeds():
    ok = {"choices": [{"message": {"content": "تم"}}]}
    with patch("core.ollama_assistant.requests.post",
               side_effect=[_resp(429), _resp(200, ok)]) as post, \
         patch("core.ollama_assistant.time.sleep"):
        out = ollama_assistant._post_chat([], None, "http://x", "k", "m", 10)
    assert out == ok
    assert post.call_count == 2


def test_post_chat_retries_once_on_connection_error_then_succeeds():
    ok = {"choices": [{"message": {"content": "تم"}}]}
    with patch("core.ollama_assistant.requests.post",
               side_effect=[requests.exceptions.ConnectionError(), _resp(200, ok)]) as post, \
         patch("core.ollama_assistant.time.sleep"):
        out = ollama_assistant._post_chat([], None, "http://x", "k", "m", 10)
    assert out == ok
    assert post.call_count == 2


def test_post_chat_raises_after_second_failure():
    with patch("core.ollama_assistant.requests.post",
               side_effect=requests.exceptions.ConnectionError()), \
         patch("core.ollama_assistant.time.sleep"):
        with pytest.raises(requests.exceptions.ConnectionError):
            ollama_assistant._post_chat([], None, "http://x", "k", "m", 10)
