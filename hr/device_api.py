"""
واجهة إدارة أجهزة الدخول للمستخدم (GitHub #168 — م٢).

تتيح للمستخدم إدارة أجهزته الخاصة حصراً:
1. عرض أجهزتي مع بيان الجهاز الحالي والجهاز الأساسي.
2. إنهاء جهاز محدد.
3. إنهاء جميع الأجهزة الأخرى عدا الحالي.
4. تعيين الجهاز الحالي كجهاز أساسي (يتطلب كلمة المرور).
5. إعادة تسمية جهاز (تسمية مخصصة تعلو فوق الاسم المشتق).

قواعد الأمان وحارس الجهاز الأساسي:
- كل العمليات تعمل على حساب المستخدم المتصل حصراً — لا يوجد أي بارامتر للمستخدم (لا في المسار ولا في الاستعلام ولا في الجسم).
- حارس الجهاز الأساسي: إذا عيّن المستخدم جهازاً أساسياً، فالإدارة (العرض والإنهاء) محصورة بالجهاز الأساسي.
- إذا لم يُعيّن أي جهاز أساسي بعد، تكون الإدارة متاحة لكل الأجهزة مع إظهار دعوة لاختيار جهاز أساسي.
- لا يمكن إنهاء الجهاز الأساسي من هذه الشاشة؛ تسجيل الخروج العادي هو طريقة إنهائه.
"""
import json
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from hr.models import UserDevice
from hr.auth_api import _default_tenant_for, _json_body


def _authenticate_request(request):
    """
    التحقق من ترويسة المصادقة وإرجاع (user, current_device).
    إذا كانت الترويسة غير صالحة أو غير موجودة يرجع (None, None).
    """
    auth = request.headers.get("Authorization", "").replace("Token ", "").strip()
    if not auth:
        return None, None
    # ISSUE #168: جدولُ الأجهزة وحدَه — لا ارتدادَ إلى `authtoken_token`، وإلّا
    # صار الصفُّ القديمُ الباقي بعد الهجرة مفتاحاً يُحيي جهازاً أُبطل.
    device = UserDevice.objects.filter(key=auth).select_related("user").first()
    if not device or not device.user.is_active:
        return None, None
    return device.user, device


def _check_primary_guard(user, current_device):
    """
    فحص حارس الجهاز الأساسي:
    - إذا لم يحدد المستخدم أي جهاز أساسي بعد: الإدارة متاحة للجميع (None).
    - إذا كان الجهاز الحالي هو الأساسي: مسموح (None).
    - إذا كان هناك جهاز أساسي والجهاز الحالي ثانوي: يُرفض بـ 403 ورسالة عربية توضح اسم الأساسي.
    """
    primary_device = UserDevice.objects.filter(user=user, is_primary=True).first()
    if primary_device is None:
        return None
    if current_device and current_device.pk == primary_device.pk:
        return None

    msg = f"الإدارةُ من الجهاز الأساسيّ — {primary_device.display_name}. لجعل هذا الجهاز أساسيّاً أدخل كلمةَ مرورك."
    return JsonResponse(
        {
            "detail": msg,
            "code": "PRIMARY_DEVICE_REQUIRED",
            "primary_device_name": primary_device.display_name,
        },
        status=403,
    )


def _log_device_eviction(request, user, device_name, count=1):
    """تسجيل حدث إنهاء جهاز الدخول في سجل النشاط الموحد."""
    from core.activity import log_activity

    desc = f"إنهاء جهاز: {device_name}" if count == 1 else f"إنهاء {count} أجهزة دخول"
    log_activity(
        action="device_evict",
        entity_type="session",
        entity_label=device_name,
        description=desc,
        request=request,
        tenant=_default_tenant_for(user),
        user=user,
    )


@csrf_exempt
def list_devices_view(request):
    """قائمة بأجهزة الدخول الخاصة بالمستخدم المتصل."""
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    user, current_device = _authenticate_request(request)
    if not user:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    guard_error = _check_primary_guard(user, current_device)
    if guard_error:
        return guard_error

    primary_device = UserDevice.objects.filter(user=user, is_primary=True).first()
    devices = UserDevice.objects.filter(user=user).order_by("-is_primary", "-last_active_at", "-created_at")

    data = [
        {
            "id": d.id,
            "name": d.display_name,
            "device_name": d.device_name,
            "label": d.label,
            "ip_address": d.ip_address,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "last_active_at": d.last_active_at.isoformat() if d.last_active_at else None,
            "is_primary": d.is_primary,
            "is_current": (current_device is not None and d.id == current_device.id),
        }
        for d in devices
    ]
    has_primary = primary_device is not None
    invitation = None if has_primary else "لم يتم تعيين جهاز أساسي بعد. يمكنك تعيين هذا الجهاز كجهاز أساسي لحماية حسابك."

    return JsonResponse({
        "devices": data,
        "has_primary": has_primary,
        "primary_invitation": invitation,
    })


@csrf_exempt
def evict_device_view(request, pk):
    """إنهاء جهاز دخول محدد تابع للمستخدم المتصل."""
    if request.method not in ("POST", "DELETE"):
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    user, current_device = _authenticate_request(request)
    if not user:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    guard_error = _check_primary_guard(user, current_device)
    if guard_error:
        return guard_error

    target = UserDevice.objects.filter(pk=pk, user=user).first()
    if not target:
        return JsonResponse({"detail": "Device not found"}, status=404)

    if target.is_primary:
        return JsonResponse(
            {
                "detail": "لا يمكن إنهاء الجهاز الأساسي من هذه الشاشة. تسجيل الخروج العادي هو طريقة إنهائه.",
                "code": "CANNOT_EVICT_PRIMARY",
            },
            status=400,
        )

    name = target.display_name
    target.delete()

    _log_device_eviction(request, user, name, count=1)
    return JsonResponse({"ok": True, "detail": f"تم إنهاء الجهاز: {name}"})


@csrf_exempt
def evict_others_view(request):
    """إنهاء جميع أجهزة الدخول الأخرى للمستخدم والإبقاء على الجهاز الحالي."""
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    user, current_device = _authenticate_request(request)
    if not user:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    guard_error = _check_primary_guard(user, current_device)
    if guard_error:
        return guard_error

    current_pk = current_device.pk if current_device else None
    others = UserDevice.objects.filter(user=user)
    if current_pk:
        others = others.exclude(pk=current_pk)

    count = others.count()
    others.delete()

    _log_device_eviction(request, user, "جميع الأجهزة الأخرى", count=count)
    return JsonResponse({"ok": True, "evicted_count": count, "detail": f"تم إنهاء {count} أجهزة"})


@csrf_exempt
def set_primary_view(request):
    """
    تعيين الجهاز الحالي كجهاز أساسي.
    يتطلب إدخال كلمة المرور، ويجب أن يتم من نفس الجهاز الذي سيصبح أساسياً.
    """
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    user, current_device = _authenticate_request(request)
    if not user:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    if not current_device:
        return JsonResponse({"detail": "No active device found"}, status=400)

    body = _json_body(request) or {}
    password = body.get("password") or ""
    if not password or not user.check_password(password):
        return JsonResponse(
            {"detail": "كلمة المرور غير صحيحة", "code": "INVALID_PASSWORD"},
            status=400,
        )

    with transaction.atomic():
        UserDevice.objects.filter(user=user, is_primary=True).update(is_primary=False)
        current_device.is_primary = True
        current_device.save(update_fields=["is_primary"])

    from core.activity import log_activity
    log_activity(
        action="update",
        entity_type="session",
        entity_label=current_device.display_name,
        description=f"تعيين الجهاز الأساسي: {current_device.display_name}",
        request=request,
        tenant=_default_tenant_for(user),
        user=user,
    )
    return JsonResponse({"ok": True, "detail": "تم تعيين هذا الجهاز كجهاز أساسي"})


@csrf_exempt
def rename_device_view(request, pk):
    """إعادة تسمية جهاز دخول محدد للمستخدم."""
    if request.method not in ("POST", "PATCH"):
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    user, current_device = _authenticate_request(request)
    if not user:
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    guard_error = _check_primary_guard(user, current_device)
    if guard_error:
        return guard_error

    target = UserDevice.objects.filter(pk=pk, user=user).first()
    if not target:
        return JsonResponse({"detail": "Device not found"}, status=404)

    body = _json_body(request) or {}
    label = (body.get("label") or body.get("name") or "").strip()
    target.label = label
    target.save(update_fields=["label"])

    return JsonResponse({
        "ok": True,
        "device": {
            "id": target.id,
            "name": target.display_name,
            "device_name": target.device_name,
            "label": target.label,
            "is_primary": target.is_primary,
        },
    })


@csrf_exempt
def device_detail_view(request, pk):
    """نقطة مشتركة تدعم DELETE للإنهاء و PATCH للتسمية."""
    if request.method == "DELETE":
        return evict_device_view(request, pk)
    elif request.method == "PATCH":
        return rename_device_view(request, pk)
    return JsonResponse({"detail": "Method not allowed"}, status=405)
