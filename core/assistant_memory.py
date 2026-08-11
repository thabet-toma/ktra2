"""
ذاكرة محادثة قصيرة المدى للمساعد الذكي — تُبقي آخر عدة أدوار (سؤال/جواب) من
كل جلسة (ويب أو واتساب) في كاش الملفات المشترك (FileBasedCache)، فتَعبُر بين
عمليات gunicorn المتعددة على نفس القرص.

جلسة بلا نشاط لأكثر من TTL_SECONDS تُنسى تلقائياً (نافذة منزلقة تُجدَّد مع كل
رسالة) — بداية نظيفة بعد انقطاع طويل، لا تراكم أبدي ولا تضخّم لحجم السياق
المُرسَل للنموذج في كل استدعاء.

session_key يُبنى من المستدعي بما يضمن العزل: يشمل الشركة دائماً، حتى لا
تختلط محادثة شركة بأخرى عبر نفس المستخدم (مدير يبدّل شركات) أو نفس الرقم
(نظرياً، رقم واحد مربوط بشركة واحدة عبر WhatsAppContact).
"""
from __future__ import annotations

from django.core.cache import cache

MAX_TURNS = 10  # آخر 10 أزواج سؤال/جواب (20 رسالة) — سياق كافٍ بلا تضخّم تكلفة
TTL_SECONDS = 1800  # 30 دقيقة خمول تُنسي الجلسة


def _key(session_key: str) -> str:
    return f"assistant:history:{session_key}"


def get_history(session_key: str) -> list[dict]:
    """يعيد قائمة رسائل {role, content} بصيغة جاهزة للدمج داخل messages للنموذج."""
    if not session_key:
        return []
    return cache.get(_key(session_key)) or []


def append_turn(session_key: str, user_message: str, assistant_reply: str) -> None:
    """يضيف دور سؤال/جواب جديد ويقصّ للحد الأقصى، ويجدّد TTL (نافذة منزلقة)."""
    if not session_key:
        return
    history = get_history(session_key)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_reply})
    history = history[-(MAX_TURNS * 2):]
    cache.set(_key(session_key), history, TTL_SECONDS)


def clear_history(session_key: str) -> None:
    if session_key:
        cache.delete(_key(session_key))
