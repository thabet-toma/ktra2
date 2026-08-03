"""اختبارات دروس المساعد — التسجيل، بوابة المراجعة (is_active)، والحقن بالبرومبت.

المهم أمنياً هنا: الدرس **لا يظهر** بالبرومبت إلا بعد تفعيل يدوي (is_active=True)،
حتى لو حاول النموذج نداء remember_lesson مباشرة — لا تأثير فوري على أي محادثة.
"""
import pytest

from core.assistant_lessons import lessons_text
from core.assistant_tools import remember_lesson
from core.models import AssistantLesson

pytestmark = pytest.mark.django_db


class _Tenant:
    pk = 1


def test_remember_lesson_creates_inactive_row():
    res = remember_lesson(_Tenant(), lesson="استخدم LIKE لا = عند البحث بمقاس", session_key="wa:123:1")
    assert res["saved"] is True
    row = AssistantLesson.objects.get()
    assert row.is_active is False
    assert row.text == "استخدم LIKE لا = عند البحث بمقاس"
    assert row.source == "wa:123:1"


def test_remember_lesson_rejects_empty():
    res = remember_lesson(_Tenant(), lesson="   ")
    assert "error" in res
    assert AssistantLesson.objects.count() == 0


def test_remember_lesson_truncates_overlong_text():
    long_text = "س" * 900
    remember_lesson(_Tenant(), lesson=long_text)
    row = AssistantLesson.objects.get()
    assert len(row.text) == 500


def test_lessons_text_empty_when_none_active():
    AssistantLesson.objects.create(text="درس غير مفعّل", is_active=False)
    assert lessons_text() == ""


def test_lessons_text_includes_only_active():
    AssistantLesson.objects.create(text="درس مفعّل", is_active=True)
    AssistantLesson.objects.create(text="درس غير مفعّل", is_active=False)
    out = lessons_text()
    assert "درس مفعّل" in out
    assert "درس غير مفعّل" not in out


def test_lessons_text_caps_injected_count():
    from core.assistant_lessons import MAX_INJECTED_LESSONS

    for i in range(MAX_INJECTED_LESSONS + 5):
        AssistantLesson.objects.create(text=f"درس {i}", is_active=True)
    out = lessons_text()
    assert out.count("- درس") == MAX_INJECTED_LESSONS
    # الأحدث (أرقام أعلى) هي التي بقيت
    assert f"درس {MAX_INJECTED_LESSONS + 4}" in out
    assert "درس 0" not in out
