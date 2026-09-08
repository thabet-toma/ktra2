"""API متابعة الموظفين.

ترتيب البوابتين مقصود ومُلزِم: `require_module` **قبل** `require_perm`،
فترد الشركة غير المرخّصة **404 لا 403** — 403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً.
والشركة تأتي من الحارس نفسه، لا من جسم الطلب.
"""
from django.db.models import Case, CharField, OuterRef, Subquery, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.access import require_perm
from core.api_defaults import ApiAuthAndUser
from core.modules import require_module
from hr.models import Employee

from .models import EmployeeInvitation, EmployeeProfile
from .serializers import (
    AcceptInvitationSerializer,
    EmployeeCreateSerializer,
    EmployeeInvitationSerializer,
    EmployeeListSerializer,
    EmployeeOpsSettingsSerializer,
    EmployeeUpdateSerializer,
)
from .services import (
    MODULE_KEY,
    accept_invitation,
    cancel_invitation,
    create_employee_with_invitation,
    deactivate_employee,
    get_or_create_settings,
    invite_employee,
    load_pending_invitation,
    reactivate_employee,
    resend_invitation,
    settings_for_read,
)

PERM_MANAGE = "employee_ops.manage"

_SETTINGS_ACTION_PERMS = {
    "list": PERM_MANAGE,
    "update": PERM_MANAGE,
    "partial_update": PERM_MANAGE,
}

_EMPLOYEE_ACTION_PERMS = {
    "list": PERM_MANAGE,
    "create": PERM_MANAGE,
    "retrieve": PERM_MANAGE,
    "partial_update": PERM_MANAGE,
    "invite": PERM_MANAGE,
    "deactivate": PERM_MANAGE,
    "reactivate": PERM_MANAGE,
}

_INVITATION_ACTION_PERMS = {
    "list": PERM_MANAGE,
    "retrieve": PERM_MANAGE,
    "resend": PERM_MANAGE,
    "cancel": PERM_MANAGE,
}


def _invitation_url(request, raw_token: str) -> str:
    """رابطُ الدعوة من جدول المسارات لا من نصٍّ مكرّر — تغييرُ المسار يتبعه وحده.

    ملاحظة: يشير اليوم إلى نقطة الـAPI مباشرةً؛ صفحةُ الواجهة مرحلةٌ لاحقة
    (مذكورةٌ في `docs/modules/employee_ops.md`).
    """
    return request.build_absolute_uri(
        reverse("employee-ops-invitation-accept", kwargs={"token": raw_token})
    )


class EmployeeOpsSettingsViewSet(viewsets.ViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        required = _SETTINGS_ACTION_PERMS.get(self.action)
        if required is None:
            raise Http404
        require_perm(request, required, tenant=self.tenant)

    def list(self, request):
        serializer = EmployeeOpsSettingsSerializer(settings_for_read(self.tenant))
        return Response(serializer.data)

    def update(self, request):
        return self._save(request, partial=False)

    def partial_update(self, request):
        return self._save(request, partial=True)

    def _save(self, request, *, partial: bool):
        settings_obj = get_or_create_settings(self.tenant)
        serializer = EmployeeOpsSettingsSerializer(
            settings_obj, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EmployeeViewSet(viewsets.ViewSet):
    """إدارة موظفي الشركة في وحدة متابعة الموظفين."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        required = _EMPLOYEE_ACTION_PERMS.get(self.action)
        if required is None:
            raise Http404
        require_perm(request, required, tenant=self.tenant)

    def list(self, request):
        # الفلترُ بالشركة هنا دفاعٌ في العمق: قائمةُ الموظفين مفلترةٌ بها أصلاً،
        # لكنّ استعلاماً فرعياً بلا شركةٍ يبقى سطراً يُنسخ إلى موضعٍ لا فلتر فيه.
        latest_inv_status = Subquery(
            EmployeeInvitation.objects.filter(
                employee=OuterRef("pk"), tenant=self.tenant
            )
            .order_by("-id")
            .values("status")[:1]
        )
        qs = (
            Employee.objects.filter(tenant=self.tenant)
            .select_related("employee_ops_profile__manager")
            .annotate(raw_inv_status=latest_inv_status)
            .annotate(
                annotated_invitation_status=Case(
                    When(
                        raw_inv_status=EmployeeInvitation.STATUS_PENDING,
                        then=Value(EmployeeInvitation.STATUS_PENDING),
                    ),
                    When(
                        raw_inv_status=EmployeeInvitation.STATUS_ACCEPTED,
                        then=Value(EmployeeInvitation.STATUS_ACCEPTED),
                    ),
                    default=Value("none"),
                    output_field=CharField(),
                )
            )
            .order_by("id")
        )
        serializer = EmployeeListSerializer(qs, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = EmployeeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        employee, profile, invitation, raw_token = create_employee_with_invitation(
            tenant=self.tenant,
            actor=request.user,
            name=data["name"],
            phone=data.get("phone", ""),
            job_title=data.get("job_title", ""),
            manager=data.get("manager"),
        )
        invitation_url = _invitation_url(request, raw_token)
        return Response(
            {
                "employee": {
                    "id": employee.id,
                    "name": employee.name,
                    "code": employee.code,
                    "phone": employee.phone,
                    "job_title": employee.job_title,
                    "is_active": employee.is_active,
                    "has_account": False,
                    "manager": profile.manager_id,
                    "manager_name": profile.manager.name if profile.manager else None,
                    "invitation_status": "pending",
                },
                "invitation": EmployeeInvitationSerializer(invitation).data,
                "raw_token": raw_token,
                "invitation_url": invitation_url,
            },
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        employee = get_object_or_404(
            Employee.objects.filter(tenant=self.tenant).select_related("employee_ops_profile__manager"),
            pk=pk,
        )
        inv = (
            EmployeeInvitation.objects.filter(employee=employee, tenant=self.tenant)
            .order_by("-id")
            .first()
        )
        status_val = "none"
        if inv and inv.status in (
            EmployeeInvitation.STATUS_PENDING,
            EmployeeInvitation.STATUS_ACCEPTED,
        ):
            status_val = inv.status
        setattr(employee, "annotated_invitation_status", status_val)
        serializer = EmployeeListSerializer(employee)
        return Response(serializer.data)

    def partial_update(self, request, pk=None):
        employee = get_object_or_404(Employee.objects.filter(tenant=self.tenant), pk=pk)
        serializer = EmployeeUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        update_fields = ["updated_at"]
        if "name" in data:
            employee.name = data["name"].strip()
            update_fields.append("name")
        if "phone" in data:
            employee.phone = data["phone"].strip()
            update_fields.append("phone")
        if "job_title" in data:
            employee.job_title = data["job_title"].strip()
            update_fields.append("job_title")

        if len(update_fields) > 1:
            employee.save(update_fields=update_fields)

        if "manager" in data:
            manager_id = data["manager"]
            manager_obj = None
            if manager_id is not None:
                manager_obj = Employee.objects.filter(tenant=self.tenant, pk=manager_id).first()
                if manager_obj is None:
                    raise ValidationError({"manager": "المدير المحدد غير موجود في هذه الشركة."})
            profile, _ = EmployeeProfile.objects.get_or_create(tenant=self.tenant, employee=employee)
            profile.manager = manager_obj
            profile.save(update_fields=["manager", "updated_at"])

        return self.retrieve(request, pk=pk)

    @action(detail=True, methods=["post"])
    def invite(self, request, pk=None):
        employee = get_object_or_404(Employee.objects.filter(tenant=self.tenant), pk=pk)
        invitation, raw_token = invite_employee(employee=employee, actor=request.user)
        invitation_url = _invitation_url(request, raw_token)
        return Response(
            {
                "invitation": EmployeeInvitationSerializer(invitation).data,
                "raw_token": raw_token,
                "invitation_url": invitation_url,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        employee = get_object_or_404(Employee.objects.filter(tenant=self.tenant), pk=pk)
        deactivate_employee(employee=employee, actor=request.user)
        return Response({"status": "deactivated", "id": employee.id})

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        employee = get_object_or_404(Employee.objects.filter(tenant=self.tenant), pk=pk)
        reactivate_employee(employee=employee, actor=request.user)
        return Response({"status": "reactivated", "id": employee.id})


class EmployeeInvitationViewSet(viewsets.ViewSet):
    """إدارة دعوات انضمام الموظفين."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        required = _INVITATION_ACTION_PERMS.get(self.action)
        if required is None:
            raise Http404
        require_perm(request, required, tenant=self.tenant)

    def list(self, request):
        qs = EmployeeInvitation.objects.filter(
            tenant=self.tenant, status=EmployeeInvitation.STATUS_PENDING
        ).select_related("employee", "created_by").order_by("-created_at")
        serializer = EmployeeInvitationSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        invitation = get_object_or_404(
            EmployeeInvitation.objects.filter(tenant=self.tenant), pk=pk
        )
        serializer = EmployeeInvitationSerializer(invitation)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        invitation = get_object_or_404(
            EmployeeInvitation.objects.filter(tenant=self.tenant), pk=pk
        )
        invitation, raw_token = resend_invitation(invitation, actor=request.user)
        invitation_url = _invitation_url(request, raw_token)
        return Response({
            "invitation": EmployeeInvitationSerializer(invitation).data,
            "raw_token": raw_token,
            "invitation_url": invitation_url,
        })

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invitation = get_object_or_404(
            EmployeeInvitation.objects.filter(tenant=self.tenant), pk=pk
        )
        invitation = cancel_invitation(invitation, actor=request.user)
        return Response({
            "invitation": EmployeeInvitationSerializer(invitation).data,
        })


class AcceptInvitationPublicView(APIView):
    """النقطة العامة لقبول دعوة الموظف (بلا مصادقة، مع خانق تقنين)."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "employee_ops_invite"

    def get(self, request, token):
        # نفسُ سلسلة التحقّق التي يستعملها القبول — مصدرٌ واحد، فلا يقبل مسارٌ
        # ما يرفضه الآخر.
        invitation = load_pending_invitation(token)
        # **الاسمان وحدهما**: هذه صفحةٌ يفتحها مجهولٌ بالرابط، فلا هاتفَ ولا
        # بريدَ ولا معرّفاتٍ تُسلَّم فيها.
        return Response({
            "company_name": invitation.tenant.CompanyName,
            "employee_name": invitation.employee.name,
            # الموظفُ العائد يملك حسابه أصلاً، فالشاشةُ لا تسأله كلمةَ مرورٍ جديدة.
            "needs_account": not invitation.employee.user_id,
        })

    def post(self, request, token):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user, membership = accept_invitation(
            token=token,
            username=data["username"],
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        return Response(
            {
                "message": "تم قبول الدعوة بنجاح وإنشاء الحساب.",
                "username": user.username,
            },
            status=status.HTTP_201_CREATED,
        )
