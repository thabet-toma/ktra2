"""
أدوار التطبيق كما تُعاد في /api/auth/login (مرآة users/<id> + قواعد المستخدم النشط الوحيد).
تُستخدم لفحوص الـ API التي يجب أن تطابق ما يراه المستخدم في الواجهة.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


def django_user_app_role(user: AbstractUser | None) -> str:
    """نفس منطق الدور الفعلي بعد login (بدون حقول العرض الأخرى)."""
    from django.contrib.auth import get_user_model

    from bridge.models import FirestoreMirrorDoc

    User = get_user_model()
    if not user or not user.is_authenticated:
        return ""

    role = "manager" if getattr(user, "is_superuser", False) else "employee"
    doc = FirestoreMirrorDoc.objects.filter(path=f"users/{user.pk}").first()
    if doc and isinstance(doc.data, dict) and doc.data.get("role"):
        role = str(doc.data["role"]).strip()

    payload_role = str(role).lower()
    if not getattr(user, "is_active", False):
        return payload_role

    if payload_role in ("manager", "procurement"):
        return payload_role

    if User.objects.filter(is_active=True).count() == 1:
        return "manager"

    return payload_role or "employee"


def user_can_unpost_logistics_deal_payment(user: AbstractUser | None) -> bool:
    """إلغاء ترحيل دفعة صفقة: موظفو Django أو مدير التطبيق (كما في الواجهة)."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    return django_user_app_role(user) == "manager"
