"""API سجل النشاط الموحّد.

- سجل مستند واحد: ?entity_type=sales_invoice&entity_id=12 → متاح لأي مستخدم مصرّح.
- الصفحة العامة (بلا entity_id): نشاط كل المستخدمين → للمدير/السوبر أدمن فقط.
- فلاتر: user, action, entity_type, date (افتراضي اليوم), date_from/date_to,
  search, include_views (افتراضي false — يستبعد أحداث العرض من الجدول العام).
"""
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.models import ActivityLog
from core.tenant_utils import get_tenant
from core.user_roles import user_is_admin


class ActivityLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = ActivityLog
        fields = [
            "id", "action", "action_label", "is_view", "entity_type", "entity_id",
            "entity_label", "description", "metadata", "user", "user_name",
            "ip_address", "timestamp",
        ]

    def get_user_name(self, obj):
        u = obj.user
        if not u:
            return "—"
        full = f"{u.first_name} {u.last_name}".strip()
        return full or u.username


class ActivityLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = ActivityLogSerializer
    pagination_class = ActivityLogPagination

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return ActivityLog.objects.none()
        qs = ActivityLog.objects.filter(tenant=tenant).select_related("user")

        p = self.request.query_params
        entity_type = p.get("entity_type")
        entity_id = p.get("entity_id")

        # صلاحية: عرض عبر كل المستخدمين (سجل عام) للمدير فقط. سجل مستند واحد متاح للجميع.
        is_entity_scoped = bool(entity_type and entity_id)
        if not is_entity_scoped and not user_is_admin(self.request.user):
            raise PermissionDenied("سجل النشاط العام متاح للمدير فقط.")

        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if entity_id:
            qs = qs.filter(entity_id=entity_id)

        user_id = p.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        act = p.get("action")
        if act:
            qs = qs.filter(action=act)

        # أحداث العرض مستبعَدة افتراضياً من الجدول العام؛ تُطلب صراحةً بـ include_views=true
        # أو ضمن سجل مستند واحد.
        include_views = str(p.get("include_views", "")).lower() in ("1", "true", "yes")
        if not include_views and not is_entity_scoped:
            qs = qs.filter(is_view=False)

        # التاريخ: افتراضي اليوم للصفحة العامة (لا يُطبّق على سجل مستند واحد).
        date_from = parse_date(p.get("date_from") or "")
        date_to = parse_date(p.get("date_to") or "")
        single_date = parse_date(p.get("date") or "")
        if single_date:
            qs = qs.filter(timestamp__date=single_date)
        else:
            if date_from:
                qs = qs.filter(timestamp__date__gte=date_from)
            if date_to:
                qs = qs.filter(timestamp__date__lte=date_to)
            if not is_entity_scoped and not date_from and not date_to:
                from django.utils import timezone
                qs = qs.filter(timestamp__date=timezone.localdate())

        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(entity_label__icontains=search)
                | Q(description__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        return qs.order_by("-timestamp", "-id")

    @action(detail=False, methods=["get"], url_path="users")
    def users(self, request):
        """قائمة المستخدمين الذين لهم نشاط (لفلتر الصفحة العامة). للمدير فقط."""
        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        if not user_is_admin(request.user):
            raise PermissionDenied("متاح للمدير فقط.")
        user_ids = (
            ActivityLog.objects.filter(tenant=tenant, user__isnull=False)
            .values_list("user_id", flat=True)
            .distinct()
        )
        out = []
        for u in User.objects.filter(id__in=list(user_ids)):
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            out.append({"id": u.id, "name": name})
        out.sort(key=lambda x: x["name"])
        return Response(out)
