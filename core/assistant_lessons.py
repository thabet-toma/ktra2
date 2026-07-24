"""
دروس المساعد الذكي — قواعد سلوك عامة يتعلّمها من تصحيح إنسان له، تُحقن في
تعليمات النظام لكل محادثة (core.ollama_assistant._system_prompt) بعد مراجعة
وتفعيل يدوي من /admin/ (core.models.AssistantLesson).

الكتابة عبر core.assistant_tools.remember_lesson (أداة يستدعيها النموذج فقط
عند تصحيح صريح من إنسان)، والقراءة هنا — فصل بسيط بين المسارين.
"""
from __future__ import annotations

# سقف عدد الدروس المحقونة بكل نداء — يمنع تضخّم تعليمات النظام بلا حدود
# مهما تراكمت الدروس المفعّلة بمرور الوقت؛ الأحدث تفعيلاً هو الأولى بالبقاء.
MAX_INJECTED_LESSONS = 30


def lessons_text() -> str:
    """نص جاهز للحقن في تعليمات النظام، أو فارغ إن لم توجد دروس مفعّلة."""
    from core.models import AssistantLesson

    lessons = list(
        AssistantLesson.objects.filter(is_active=True)
        # ترتيب بـ id احتياطياً: created_at (auto_now_add) قد يتطابق بين صفوف
        # أُنشئت بنفس الميلي ثانية، فيصير الترتيب بالوقت وحده غير حتمي.
        .order_by('-created_at', '-id')
        .values_list('text', flat=True)[:MAX_INJECTED_LESSONS]
    )
    if not lessons:
        return ""
    lines = "\n".join(f"- {text}" for text in reversed(lessons))
    return "دروس متعلَّمة من تصحيحات سابقة (راجعها أدمن ووافق عليها):\n" + lines
