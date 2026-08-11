"""اختبارات ذاكرة المحادثة القصيرة المدى — العزل بين الجلسات هو الأهم هنا،
تماماً كما العزل بين الشركات في اختبارات SQL/الأدوات.

core.test_settings يضبط CACHES على DummyCache عمداً (عزل الاختبارات عن بعض
بلا كاش حقيقي)، فهذا الملف يفعّل LocMemCache حقيقياً محلياً لهذه الاختبارات
فقط — الإنتاج يبقى على FileBasedCache كما هو مضبوط في core/settings.py.
"""
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from core import assistant_memory, ollama_assistant

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _real_cache(settings):
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    cache.clear()
    yield
    cache.clear()


def test_empty_history_for_new_session():
    assert assistant_memory.get_history("session-x") == []


def test_append_and_retrieve_turn():
    assistant_memory.append_turn("s1", "سؤال", "جواب")
    hist = assistant_memory.get_history("s1")
    assert hist == [
        {"role": "user", "content": "سؤال"},
        {"role": "assistant", "content": "جواب"},
    ]


def test_sessions_are_isolated():
    assistant_memory.append_turn("s1", "سؤال شركة أ", "جواب أ")
    assistant_memory.append_turn("s2", "سؤال شركة ب", "جواب ب")
    assert assistant_memory.get_history("s1") == [
        {"role": "user", "content": "سؤال شركة أ"},
        {"role": "assistant", "content": "جواب أ"},
    ]
    assert assistant_memory.get_history("s2") == [
        {"role": "user", "content": "سؤال شركة ب"},
        {"role": "assistant", "content": "جواب ب"},
    ]


def test_history_trims_to_max_turns():
    for i in range(assistant_memory.MAX_TURNS + 5):
        assistant_memory.append_turn("s1", f"سؤال {i}", f"جواب {i}")
    hist = assistant_memory.get_history("s1")
    assert len(hist) == assistant_memory.MAX_TURNS * 2
    # أقدم دور يجب أن يكون قد سقط، وآخر دور محفوظ
    assert hist[-1]["content"] == f"جواب {assistant_memory.MAX_TURNS + 4}"
    assert hist[0]["content"] == f"سؤال {5}"


def test_clear_history():
    assistant_memory.append_turn("s1", "سؤال", "جواب")
    assistant_memory.clear_history("s1")
    assert assistant_memory.get_history("s1") == []


def test_none_session_key_is_noop():
    assistant_memory.append_turn(None, "سؤال", "جواب")  # لا يرفع استثناءً
    assert assistant_memory.get_history(None) == []


@override_settings(OLLAMA_API_KEY="x", OLLAMA_MODEL="m", OLLAMA_BASE_URL="http://fake")
def test_chat_injects_prior_history_and_persists_new_turn():
    """chat() يحقن تاريخ الجلسة قبل السؤال الحالي، ويحفظ الدور الجديد بعد الرد."""

    class _Tenant:
        pk = 1

    assistant_memory.append_turn("s1", "سؤال قديم", "جواب قديم")

    fake_response = {
        "choices": [{"message": {"content": "رد جديد", "tool_calls": []}}]
    }
    with patch("core.ollama_assistant._post_chat", return_value=fake_response) as post:
        reply = ollama_assistant.chat("سؤال جديد", _Tenant(), session_key="s1")

    assert reply == "رد جديد"
    sent_messages = post.call_args[0][0]  # الوسيط الأول لـ _post_chat هو messages
    roles_contents = [(m["role"], m["content"]) for m in sent_messages]
    assert ("user", "سؤال قديم") in roles_contents
    assert ("assistant", "جواب قديم") in roles_contents
    assert ("user", "سؤال جديد") in roles_contents

    # الدور الجديد انحفظ فوق القديم
    hist = assistant_memory.get_history("s1")
    assert hist[-2:] == [
        {"role": "user", "content": "سؤال جديد"},
        {"role": "assistant", "content": "رد جديد"},
    ]


@override_settings(OLLAMA_API_KEY="x", OLLAMA_MODEL="m", OLLAMA_BASE_URL="http://fake")
def test_chat_without_session_key_has_no_memory():
    class _Tenant:
        pk = 1

    fake_response = {
        "choices": [{"message": {"content": "رد", "tool_calls": []}}]
    }
    with patch("core.ollama_assistant._post_chat", return_value=fake_response):
        ollama_assistant.chat("سؤال 1", _Tenant())
        ollama_assistant.chat("سؤال 2", _Tenant())
    # بلا session_key لا شيء يُحفظ
    assert assistant_memory.get_history(None) == []
