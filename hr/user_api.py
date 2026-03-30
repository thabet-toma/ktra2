from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authtoken.models import Token

from hr.auth_api import _user_payload

User = get_user_model()


@csrf_exempt
def user_detail(request, pk):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed"}, status=405)
    auth = request.headers.get("Authorization", "").replace("Token ", "").strip()
    token = Token.objects.filter(key=auth).select_related("user").first()
    if not token:
        return JsonResponse({"detail": "Unauthorized"}, status=401)
    try:
        pk_int = int(pk)
    except (TypeError, ValueError):
        return JsonResponse({"detail": "Not found"}, status=404)
    if token.user_id != pk_int and not token.user.is_staff:
        return JsonResponse({"detail": "Forbidden"}, status=403)
    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        return JsonResponse({"detail": "Not found"}, status=404)
    # دائماً نفس منطق login: دمج auth_django + المرآة (الدوار، الموافقة، إلخ)
    return JsonResponse(_user_payload(user))
