"""
إعدادات DRF المشتركة للواجهات التي يجب أن تكون مصادقاً عليها.
يُفضّل ربط كل ViewSet حساس (محاسبة، شركاء، …) بـ Token أو جلسة Django.
"""
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from core.permissions import TenantRolePermission

# جلسة + توكن: الواجهة v2 ترسل Header Token؛ لوحة الإدارة / أدوات نفس الأصل قد تستخدم الجلسة.
# task11 R2-B: TenantRolePermission — دور «مستعرض» قراءة فقط.
ApiAuthAndUser = {
    "authentication_classes": [TokenAuthentication, SessionAuthentication],
    "permission_classes": [IsAuthenticated, TenantRolePermission],
}
