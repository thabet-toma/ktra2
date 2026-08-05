import json
import logging
import time
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken.models import Token

from bridge.models import FirestoreMirrorDoc

logger = logging.getLogger(__name__)

User = get_user_model()


def _base_payload(user) -> Dict[str, Any]:
    name = (f"{user.first_name} {user.last_name}").strip() or user.username
    role = "manager" if user.is_superuser else "employee"
    from accountant_portal.models import AccountantProfile

    accountant_profile = (
        AccountantProfile.objects
        .filter(user_id=user.pk)
        .only("email_verified_at")
        .first()
    )
    return {
        "id": str(user.pk),
        "name": name,
        "email": user.email or user.username,
        "role": role,
        "isApproved": user.is_active,
        "isEmailVerified": (
            accountant_profile.email_verified_at is not None
            if accountant_profile is not None else True
        ),
        "accountType": "legal_accountant" if accountant_profile is not None else "",
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


def _import_flags(user) -> Dict[str, Any]:
    """أعلام صلاحية الاستيراد للواجهة (إخفاء قائمة الاستيراد). الإنفاذ الموثوق
    يبقى على الخادم لكل شركة نشطة؛ canAccessImport يُحسب من العضوية الافتراضية."""
    try:
        from core.import_access import is_super_admin, user_can_access_import
        from tenants.models import UserCompanyMembership

        # canAccessImport هنا قيمة أوّلية من الشركة الافتراضية فقط؛ الواجهة تعيد
        # حسابها للشركة النشطة (CompanyContext). تفعيل الشركة شرطٌ للجميع.
        m = (
            UserCompanyMembership.objects.filter(user=user, is_default=True).select_related("tenant").first()
            or UserCompanyMembership.objects.filter(user=user).select_related("tenant").first()
        )
        tenant = m.tenant if m else None
        return {
            "isSuperAdmin": is_super_admin(user),
            "canAccessImport": user_can_access_import(user, tenant),
        }
    except Exception:  # noqa: BLE001 — لا نعطّل المصادقة بسبب حساب الأعلام
        logger.exception("import flags computation failed for user=%s", getattr(user, "pk", None))
        return {"isSuperAdmin": False, "canAccessImport": False}


def _user_payload(user) -> Dict[str, Any]:
    base = _base_payload(user)
    doc = FirestoreMirrorDoc.objects.filter(path=f"users/{user.pk}").first()
    if doc and isinstance(doc.data, dict):
        merged = {**doc.data, **base}
        merged["id"] = str(user.pk)
        # الدور من مرآة users/<id> (مثل أول مستخدم = manager) يبقى ولا يُستبدل بافتراضي base
        if doc.data.get("role"):
            merged["role"] = doc.data["role"]
        result = _apply_sole_active_owner_role(user, merged)
    else:
        result = _apply_sole_active_owner_role(user, base)

    # Membership is the authoritative company role. A manager membership must
    # override the legacy mirror/default employee value after company creation.
    from tenants.models import UserCompanyMembership

    if UserCompanyMembership.objects.filter(user=user, role="manager").exists():
        result = {**result, "role": "manager"}
    return {**result, **_import_flags(user)}


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


def _default_tenant_for(user):
    """شركة المستخدم الافتراضية — لربط أحداث الجلسة (دخول/خروج) بها."""
    try:
        from tenants.models import UserCompanyMembership

        m = (
            UserCompanyMembership.objects.filter(user=user, is_default=True).select_related("tenant").first()
            or UserCompanyMembership.objects.filter(user=user).select_related("tenant").first()
        )
        return m.tenant if m else None
    except Exception:  # noqa: BLE001
        return None


def _log_session_event(request, user, action):
    """يسجّل حدث دخول/خروج في سجل النشاط الموحّد (غير حاظر)."""
    from core.activity import log_activity

    name = (f"{user.first_name} {user.last_name}").strip() or user.username
    log_activity(
        action=action,
        entity_type="session",
        entity_label=name,
        description="تسجيل دخول" if action == "login" else "تسجيل خروج",
        request=request,
        tenant=_default_tenant_for(user),
        user=user,
    )


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
    _log_session_event(request, user, "login")
    return JsonResponse({"token": token.key, "user": _user_payload(user)})


@csrf_exempt
def logout_view(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    auth = request.headers.get("Authorization", "").replace("Token ", "").strip()
    if auth:
        tok = Token.objects.filter(key=auth).select_related("user").first()
        if tok is not None:
            _log_session_event(request, tok.user, "logout")
            tok.delete()
    return JsonResponse({"ok": True})


@csrf_exempt
def signup_view(request):
    started_at = time.monotonic()

    def reject(detail, reason, field=None):
        logger.info(
            "signup rejected reason=%s duration_ms=%d",
            reason,
            round((time.monotonic() - started_at) * 1000),
        )
        payload = {"detail": detail}
        if field:
            payload["field"] = field
        return JsonResponse(payload, status=400)

    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    body = _json_body(request)
    if not isinstance(body, dict):
        return reject("يجب أن يكون الطلب كائن JSON صالحاً.", "invalid_json")

    raw_full_name = body.get("fullName")
    raw_email = body.get("email")
    password = body.get("password")
    full_name = raw_full_name.strip() if isinstance(raw_full_name, str) else ""
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""

    if not full_name:
        return reject("الاسم الكامل مطلوب.", "missing_full_name", "fullName")
    if not email:
        return reject("البريد الإلكتروني مطلوب.", "missing_email", "email")
    if not isinstance(password, str) or not password:
        return reject("كلمة المرور مطلوبة.", "missing_password", "password")
    try:
        validate_email(email)
    except ValidationError:
        return reject("أدخل بريداً إلكترونياً صالحاً.", "invalid_email", "email")
    if len(email) > User._meta.get_field("username").max_length:
        return reject("أدخل بريداً إلكترونياً صالحاً.", "invalid_email", "email")
    if len(password) < 6:
        return reject(
            "يجب أن تتكون كلمة المرور من 6 أحرف على الأقل.",
            "password_too_short",
            "password",
        )
    if User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).exists():
        return reject("البريد الإلكتروني مسجل مسبقاً.", "duplicate_email", "email")

    parts = full_name.split(maxsplit=1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    try:
        with transaction.atomic():
            try:
                # Inner savepoint lets a duplicate race roll back cleanly while
                # the outer transaction still owns user + mirror atomically.
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        password=password,
                        first_name=first[:150],
                        last_name=last[:150],
                        is_active=True,
                    )
            except IntegrityError:
                return reject(
                    "البريد الإلكتروني مسجل مسبقاً.",
                    "duplicate_email",
                    "email",
                )
            _sync_user_mirror(user)
    except Exception:
        logger.exception(
            "signup failed reason=persistence_error duration_ms=%d",
            round((time.monotonic() - started_at) * 1000),
        )
        raise

    logger.info(
        "signup completed duration_ms=%d",
        round((time.monotonic() - started_at) * 1000),
    )
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
