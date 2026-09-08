from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from hr.auth_api import _user_payload
from hr.authentication import resolve_device, touch_last_active

User = get_user_model()


def _resolve_auth_device(request):
    """جهازُ الدخول صاحبُ مفتاح هذا الطلب — أو `None`، مع تحديث «آخر نشاط».

    الحلُّ والنافذةُ من `hr.authentication` — مصدرٌ واحدٌ للقاعدتين، فلا تتباعد
    نسختان منهما بصمت.
    """
    device = resolve_device(request)
    if device is not None:
        touch_last_active(device)
    return device


@csrf_exempt
def user_detail(request, pk):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    device = _resolve_auth_device(request)
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
    device = _resolve_auth_device(request)
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
