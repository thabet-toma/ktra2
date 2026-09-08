from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from hr.auth_api import _user_payload
from hr.models import UserDevice

User = get_user_model()


def _resolve_auth_device(auth_key):
    """جهازُ الدخول صاحبُ هذا المفتاح — أو `None`.

    ISSUE #168: **لا ارتدادَ إلى `authtoken_token`.** الصفُّ القديمُ الباقي بعد
    الهجرة الصامتة ليس اعتماداً؛ قبولُه هنا يجعله مفتاحاً يُحيي جهازاً أُبطل.
    """
    if not auth_key:
        return None
    device = UserDevice.objects.filter(key=auth_key).select_related("user").first()
    if device is None:
        return None
    # نافذةُ الخمس دقائق — الكتابةُ تسقط من المسار الحارّ (انظر صنف المصادقة).
    from django.utils import timezone
    now = timezone.now()
    if not device.last_active_at or (now - device.last_active_at).total_seconds() >= 300:
        UserDevice.objects.filter(pk=device.pk).update(last_active_at=now)
        device.last_active_at = now
    return device


@csrf_exempt
def user_detail(request, pk):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    auth = request.headers.get("Authorization", "").replace("Token ", "").strip()
    device = _resolve_auth_device(auth)
    if not device:
        return JsonResponse({"detail": "Unauthorized"}, status=401)
    try:
        pk_int = int(pk)
    except (TypeError, ValueError):
        return JsonResponse({"detail": "Not found"}, status=404)
    # P2-11 (SCALABILITY_AUDIT §4): كان `is_staff` وحده يكفي لقراءة **أي** حساب
    # في المنصّة كلها عبر الشركات — وهي علامة Django عامة لا صلة لها بعضوية
    # الشركة، تُمنَح لأي مستخدم يدخل لوحة الإدارة. النتيجة: بريد أي مستخدم
    # واسمه ودوره مقروءان من خارج شركته. القراءة الآن مقصورة على: النفس، أو
    # السوبر أدمن، أو من يشارك المستهدَفَ عضويةَ شركة واحدة على الأقل — وهو
    # النطاق الذي تحتاجه شاشات إدارة الأعضاء فعلاً.
    if device.user_id != pk_int and not device.user.is_superuser:
        from tenants.models import UserCompanyMembership
        shared = UserCompanyMembership.objects.filter(
            user_id=device.user_id,
            tenant_id__in=UserCompanyMembership.objects.filter(
                user_id=pk_int,
            ).values("tenant_id"),
        ).exists()
        if not shared:
            return JsonResponse({"detail": "Forbidden"}, status=403)
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    # دائماً نفس منطق login: دمج auth_django + المرآة (الدوار، الموافقة، إلخ)
    return JsonResponse(_user_payload(user))

@csrf_exempt
def list_users(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    auth = request.headers.get("Authorization", "").replace("Token ", "").strip()
    device = _resolve_auth_device(auth)
    if not device:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    # This endpoint exposes platform-wide account identifiers. Company managers
    # administer memberships through an exact username/email lookup instead;
    # they must never be able to enumerate unrelated platform accounts.
    if not device.user.is_superuser:
        return JsonResponse({"detail": "Forbidden"}, status=403)

    users = User.objects.filter(is_active=True).values("id", "username", "email", "first_name", "last_name")
    
    result = []
    for u in users:
        full_name = f"{u['first_name']} {u['last_name']}".strip()
        result.append({
            "id": u["id"],
            "username": u["username"],
            "email": u["email"],
            "full_name": full_name or u["username"]
        })
    return JsonResponse(result, safe=False)
