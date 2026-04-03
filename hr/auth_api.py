import json
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken.models import Token

from bridge.models import FirestoreMirrorDoc

User = get_user_model()


def _base_payload(user) -> Dict[str, Any]:
    name = (f"{user.first_name} {user.last_name}").strip() or user.username
    role = "manager" if user.is_superuser else "employee"
    return {
        "id": str(user.pk),
        "name": name,
        "email": user.email or user.username,
        "role": role,
        "isApproved": user.is_active,
        "isEmailVerified": True,
        "employmentStatus": "",
        "phone": "",
        "address": "",
        "experienceDescription": "",
        "educationLevel": "",
        "resumeData": None,
        "createdAt": user.date_joined.isoformat() if user.date_joined else None,
    }


def _apply_sole_active_owner_role(user, payload: Dict[str, Any]) -> Dict[str, Any]:
    """إن كان المستخدم النشّط الوحيد في النظام وما زال دوره موظفاً، يُعامل كمدير (صلاحيات الصفقات والشحنات…)."""
    if not user.is_active:
        return payload
    if payload.get("role") in ("manager", "procurement"):
        return payload
    if User.objects.filter(is_active=True).count() == 1:
        return {**payload, "role": "manager"}
    return payload


def _user_payload(user) -> Dict[str, Any]:
    base = _base_payload(user)
    doc = FirestoreMirrorDoc.objects.filter(path=f"users/{user.pk}").first()
    if doc and isinstance(doc.data, dict):
        merged = {**doc.data, **base}
        merged["id"] = str(user.pk)
        # الدور من مرآة users/<id> (مثل أول مستخدم = manager) يبقى ولا يُستبدل بافتراضي base
        if doc.data.get("role"):
            merged["role"] = doc.data["role"]
        return _apply_sole_active_owner_role(user, merged)
    return _apply_sole_active_owner_role(user, base)


def _sync_user_mirror(user, extra: Optional[Dict[str, Any]] = None):
    data = _base_payload(user)
    doc = FirestoreMirrorDoc.objects.filter(path=f"users/{user.pk}").first()
    if doc and isinstance(doc.data, dict):
        data = {**data, **doc.data}
    if extra:
        data = {**data, **extra}
    data["id"] = str(user.pk)
    FirestoreMirrorDoc.objects.update_or_create(
        path=f"users/{user.pk}",
        defaults={"data": data},
    )


def _json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except json.JSONDecodeError:
        return None


@csrf_exempt
def login_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)
    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    # Signup يضع نفس قيمة البريد في username، لكن تعديلات يدوية على DB قد تفصل الحقلين.
    user = User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).first()
    if not user or not user.check_password(password):
        return JsonResponse({"detail": "Invalid credentials"}, status=401)
    if not user.is_active:
        return JsonResponse(
            {"detail": "Account not approved", "code": "NOT_APPROVED"},
            status=403,
        )
    token, _ = Token.objects.get_or_create(user=user)
    _sync_user_mirror(user)
    return JsonResponse({"token": token.key, "user": _user_payload(user)})


@csrf_exempt
def logout_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    auth = request.headers.get("Authorization", "").replace("Token ", "").strip()
    if auth:
        Token.objects.filter(key=auth).delete()
    return JsonResponse({"ok": True})


@csrf_exempt
def signup_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    email = (body.get("email") or "").strip()
    password = body.get("password") or ""
    full_name = (body.get("fullName") or "").strip()
    if User.objects.filter(username=email).exists():
        return JsonResponse({"detail": "Email already registered"}, status=400)
    try:
        validate_password(password)
    except ValidationError as e:
        return JsonResponse({"detail": "; ".join(e.messages)}, status=400)
    parts = full_name.split(" ", 1)
    first = parts[0] or email.split("@")[0]
    last = parts[1] if len(parts) > 1 else ""
    # أول حساب في قاعدة البيانات يُفعّل مباشرة (لا يوجد مدير بعد ليوافق عليه).
    is_first_user = not User.objects.exists()
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=first[:100],
        last_name=last[:100],
        is_active=is_first_user,
    )
    extra = {
        "role": "manager" if is_first_user else "employee",
        "isEmailVerified": True,
        "phone": body.get("phone") or "",
        "address": body.get("address") or "",
        "experienceDescription": body.get("experienceDescription") or "",
        "educationLevel": body.get("educationLevel") or "",
        "resumeData": body.get("resumeData"),
        "employmentStatus": "",
    }
    _sync_user_mirror(user, extra)
    return JsonResponse({"user": _user_payload(user)}, status=201)


@csrf_exempt
def resend_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    return JsonResponse({"ok": True})


@csrf_exempt
def change_password_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    body = _json_body(request)
    if body is None:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)
    auth = request.headers.get("Authorization", "").replace("Token ", "").strip()
    token = Token.objects.filter(key=auth).first()
    if not token:
        return JsonResponse({"detail": "Unauthorized"}, status=401)
    user = token.user
    old = body.get("oldPassword") or ""
    new_p = body.get("newPassword") or ""
    if not user.check_password(old):
        return JsonResponse({"detail": "Invalid old password"}, status=400)
    try:
        validate_password(new_p, user=user)
    except ValidationError as e:
        return JsonResponse({"detail": "; ".join(e.messages)}, status=400)
    user.set_password(new_p)
    user.save()
    return JsonResponse({"ok": True})
