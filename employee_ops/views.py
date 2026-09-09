"""API متابعة الموظفين.

ترتيب البوابتين مقصود ومُلزِم: `require_module` **قبل** `require_perm`،
فترد الشركة غير المرخّصة **404 لا 403** — 403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً.
والشركة تأتي من الحارس نفسه، لا من جسم الطلب.
"""
from django.db.models import (
    Case,
    CharField,
    Count,
    Exists,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.access import require_perm, user_has_perm
from core.api_defaults import ApiAuthAndUser
from core.modules import require_module
from hr.models import Employee
from tenants.models import UserCompanyMembership

from .models import (
    EmployeeInvitation,
    EmployeeNote,
    EmployeeProfile,
    PointEntry,
    Task,
    TaskAssignment,
    TaskSubmission,
)
from .serializers import (
    AcceptInvitationSerializer,
    ActivityRangeSerializer,
    EmployeeCreateSerializer,
    EmployeeInvitationSerializer,
    EmployeeListSerializer,
    EmployeeNoteInputSerializer,
    EmployeeNoteSerializer,
    EmployeeOpsSettingsSerializer,
    EmployeeUpdateSerializer,
    ManualPointEntrySerializer,
    PointEntrySerializer,
    TaskAssignmentSerializer,
    TaskCreateSerializer,
    TaskSerializer,
    TaskSubmissionCreateSerializer,
    TaskSubmissionReviewSerializer,
    TaskSubmissionSerializer,
    TaskUpdateSerializer,
    UnreviewSubmissionSerializer,
)
from .services import (
    ACTIVITY_TAB_LIMIT,
    MODULE_KEY,
    NOTES_LIST_LIMIT,
    parse_month_bounds,
    accept_invitation,
    attendance_check_in,
    cancel_invitation,
    create_employee_note,
    create_employee_with_invitation,
    create_task,
    deactivate_employee,
    employee_activity,
    employee_card,
    delete_task,
    get_leaderboard_data,
    get_or_create_settings,
    get_points_summary,
    invite_employee,
    load_pending_invitation,
    reactivate_employee,
    record_manual_points,
    resend_invitation,
    review_submission,
    settings_for_read,
    start_task_timer,
    stop_task_timer,
    submit_task,
    unreview_submission,
    update_task,
)

PERM_MANAGE = "employee_ops.manage"
PERM_SELF = "employee_ops.self"

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
    "activity": PERM_MANAGE,
    "card": PERM_MANAGE,
}

# الملاحظةُ لا يقرؤها إلا حاملُ `employee_ops.manage` — **لا «مديرُه المباشر»**:
# حقلُ `manager` في هذه الوحدة معلومةٌ لا حارس، ولا يُفلتَر به استعلامٌ في أيّ
# مكان. **ولا تعديلَ ولا حذف**: العيبُ الذي
# وُجد هذا الجدولُ لإزالته هو حقلٌ «يُدهَس بكلّ حفظ»، وتحريرُ النصّ في مكانه هو
# الدهسُ نفسُه بنطاقٍ أضيق. والمواصفة (§٧ · القصّة ٣٤) تريدها **دليلاً لا انطباعاً**،
# ولم تطلب أيّاً منهما. من أخطأ يكتب ملاحظةً تصحّحه — والتاريخُ يبقى كاملاً.
_NOTE_ACTION_PERMS = {
    "list": PERM_MANAGE,
    "create": PERM_MANAGE,
}

_INVITATION_ACTION_PERMS = {
    "list": PERM_MANAGE,
    "retrieve": PERM_MANAGE,
    "resend": PERM_MANAGE,
    "cancel": PERM_MANAGE,
}

_TASK_ACTION_PERMS = {
    "list": PERM_MANAGE,
    "create": PERM_MANAGE,
    # القراءةُ المفردة لحاملِ أيّ المفتاحين — والموظفُ لا يفتح إلا مهمّةً
    # أُسندت إليه (الفلترةُ في `retrieve` نفسِها). بلا هذا كان الموظف يرى قائمة
    # `mine` ولا يستطيع فتح بندٍ منها.
    "retrieve": None,
    "update": PERM_MANAGE,
    "partial_update": PERM_MANAGE,
    "destroy": PERM_MANAGE,
    "mine": PERM_SELF,
    "start": PERM_SELF,
    "stop": PERM_SELF,
    "submit": PERM_SELF,
}

# `None` هنا تعني «أيُّ المفتاحين يكفي» لا «بلا حارس»: القراءةُ مفتوحةٌ لحاملِ
# `self` (فيرى تسليماتِه وحدها) ولحاملِ `manage` (فيرى الطابور كلَّه)، والفلترةُ
# في `list`/`retrieve` نفسِهما. والفشلُ يبقى مغلقاً: فعلٌ **غير مذكورٍ** في هذا
# الجدول يُردّ ٤٠٤ — الفحصُ بـ`not in` قبل القراءة لا بـ`.get`.
_SUBMISSION_ACTION_PERMS = {
    "list": None,
    "retrieve": None,
    "review": PERM_MANAGE,
    "unreview": PERM_MANAGE,
}

_POINT_ACTION_PERMS = {
    "list": None,
    "summary": PERM_SELF,
    "manual": PERM_MANAGE,
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


def _employee_open_task_count(tenant, *, overdue_only: bool = False):
    """عدّادُ مهامّ الموظف المفتوحة كاستعلامٍ فرعيّ لا كضمّ.

    ضمُّ `TaskAssignment` و`PointEntry` في نفس الاستعلام يضاعف الصفوف فيتضخّم
    كلا العدّادين — العطبُ الكلاسيكيّ لتجميعين على علاقتين. فكلُّ عدّادٍ هنا
    استعلامٌ فرعيّ مستقلّ: صفٌّ واحدٌ لكلّ موظف، بلا تقاطع.

    والشركةُ في الفلتر صراحةً: الإسنادُ يحمل `tenant` بذاته، فلا يكفي أن يكون
    الموظفُ الخارجيُّ مفلتراً.
    """
    predicate = Q(tenant=tenant, employee=OuterRef("pk"))
    predicate &= ~Q(status=TaskAssignment.STATUS_COMPLETED)
    if overdue_only:
        predicate &= Q(task__due_date__lt=timezone.localdate())
    return Coalesce(
        Subquery(
            TaskAssignment.objects.filter(predicate)
            .order_by()
            .values("employee")
            .annotate(n=Count("id"))
            .values("n")[:1],
            output_field=IntegerField(),
        ),
        Value(0),
    )


def _employee_last_activity(tenant):
    """وقتُ آخر حدثٍ للموظف في المنصة — استعلامٌ فرعيٌّ على نقطة النشاط القائمة.

    قراءةٌ فقط، بلا نقطةِ تسجيلٍ جديدةٍ ولا فهرسٍ جديد: الفهرسُ
    `act_tenant_user_ts_idx` على (شركة، مستخدم، وقت) موجودٌ ويخدم هذا الترتيب.
    وموظفٌ بلا حسابٍ يعود بـNULL — لا نشاطَ لمن لا يدخل.
    """
    from core.models import ActivityLog

    return Subquery(
        ActivityLog.objects.filter(tenant=tenant, user_id=OuterRef("user_id"))
        .order_by("-timestamp", "-id")
        .values("timestamp")[:1]
    )


def _employee_month_points(tenant):
    """مجموعُ نقاط الشهر الجاري للموظف — نفسُ حدودِ الشهر التي يستعملها كرتُه.

    `parse_month_bounds(None)` هي مصدرُ الحدود الوحيد، فلا يفترق رقمُ القائمة
    عن رقمِ الكرت لأنّ أحدهما حسب الشهرَ بطريقته.
    """
    start_date, end_date, _ = parse_month_bounds(None)
    return Coalesce(
        Subquery(
            PointEntry.objects.filter(
                tenant=tenant,
                employee=OuterRef("pk"),
                awarded_on__gte=start_date,
                awarded_on__lte=end_date,
            )
            .order_by()
            .values("employee")
            .annotate(total=Sum("points"))
            .values("total")[:1],
            output_field=IntegerField(),
        ),
        Value(0),
    )


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
                # مرآةُ `EmployeeInvitation.VISIBLE_STATUSES` في SQL — تُبنى منها
                # لا تُكتب بجانبها، فلا تفترقان.
                annotated_invitation_status=Case(
                    *[
                        When(raw_inv_status=value, then=Value(value))
                        for value in EmployeeInvitation.VISIBLE_STATUSES
                    ],
                    default=Value("none"),
                    output_field=CharField(),
                )
            )
            .annotate(
                # «هل يستطيع الدخول اليوم؟» لا «هل له صفُّ مستخدمٍ يوماً ما؟».
                # العائدُ إلى العمل يحتفظ بـ`user` وتُحذف عضويّتُه، فبناءُ زرِّ
                # الدعوة على `has_account` كان يحرمه من دعوةٍ يقبلها الخادم.
                has_membership=Exists(
                    UserCompanyMembership.objects.filter(
                        tenant=self.tenant, user_id=OuterRef("user_id")
                    )
                ),
                open_tasks=_employee_open_task_count(self.tenant),
                overdue_tasks=_employee_open_task_count(self.tenant, overdue_only=True),
                month_points=_employee_month_points(self.tenant),
                last_activity=_employee_last_activity(self.tenant),
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
        if inv and inv.status in EmployeeInvitation.VISIBLE_STATUSES:
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

    @action(detail=True, methods=["get"])
    def card(self, request, pk=None):
        employee = get_object_or_404(
            Employee.objects.filter(tenant=self.tenant).select_related(
                "employee_ops_profile__manager"
            ),
            pk=pk,
        )
        return Response(employee_card(tenant=self.tenant, employee=employee))

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        employee = get_object_or_404(
            Employee.objects.filter(tenant=self.tenant), pk=pk
        )
        window = ActivityRangeSerializer(data=request.query_params)
        window.is_valid(raise_exception=True)
        events = employee_activity(
            tenant=self.tenant,
            employee=employee,
            date_from=window.validated_data["date_from"],
            date_to=window.validated_data["date_to"],
        )
        return Response({
            "limit": ACTIVITY_TAB_LIMIT,
            "results": [
                {
                    "id": e.id,
                    "action": e.action,
                    "entity_type": e.entity_type,
                    "entity_id": e.entity_id,
                    "entity_label": e.entity_label,
                    "description": e.description,
                    "timestamp": e.timestamp,
                }
                for e in events
            ],
        })

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


class EmployeeNoteViewSet(viewsets.ViewSet):
    """ملاحظاتُ المديرين على الموظفين — تبويبٌ في كرت الموظف لا شاشةٌ عامّة.

    مجموعةٌ مسطّحةٌ بفلترِ `?employee=` لا مسارٌ متداخلٌ بتعبيرٍ نمطيّ: الحارسُ
    المعمَّم في `test_module_gate.py` يعدّ المسارات من `urls.py` ويتخطّى ما لا
    يستطيع تعويض معاملاته — فمسارٌ متداخلٌ يخرج من حراسته بصمت.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        if self.action not in _NOTE_ACTION_PERMS:
            raise Http404
        require_perm(request, _NOTE_ACTION_PERMS[self.action], tenant=self.tenant)

    def _employee_or_404(self, employee_id):
        return get_object_or_404(
            Employee.objects.filter(tenant=self.tenant), pk=employee_id
        )

    def list(self, request):
        employee_id = request.query_params.get("employee")
        if not (employee_id or "").isdigit():
            raise ValidationError({"employee": "معرّف الموظف مطلوب."})
        employee = self._employee_or_404(int(employee_id))
        qs = EmployeeNote.objects.filter(
            tenant=self.tenant, employee=employee
        ).select_related("author")[:NOTES_LIST_LIMIT]
        return Response(EmployeeNoteSerializer(qs, many=True).data)

    def create(self, request):
        serializer = EmployeeNoteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee_id = serializer.validated_data.get("employee")
        if employee_id is None:
            raise ValidationError({"employee": "معرّف الموظف مطلوب."})
        employee = self._employee_or_404(employee_id)
        note = create_employee_note(
            tenant=self.tenant,
            employee=employee,
            actor=request.user,
            body=serializer.validated_data["body"],
        )
        return Response(
            EmployeeNoteSerializer(note).data, status=status.HTTP_201_CREATED
        )


class TaskViewSet(viewsets.ViewSet):
    """إدارة المهام ومتابعة إسناداتها ومؤقتاتها وتسليماتها."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        # الفشلُ مغلق: فعلٌ **غير مذكورٍ** في الجدول يُردّ ٤٠٤. و`None` قيمةٌ
        # مذكورةٌ تعني «أيُّ المفتاحين يكفي» — الفحصُ بـ`not in` لا بـ`.get`.
        if self.action not in _TASK_ACTION_PERMS:
            raise Http404
        required = _TASK_ACTION_PERMS[self.action]
        self.has_manage = user_has_perm(request.user, self.tenant, PERM_MANAGE)
        if required:
            require_perm(request, required, tenant=self.tenant)
        elif not self.has_manage:
            require_perm(request, PERM_SELF, tenant=self.tenant)

    def list(self, request):
        qs = (
            Task.objects.filter(tenant=self.tenant)
            .select_related("created_by")
            .prefetch_related("assignments__employee")
            .order_by("-id")
        )
        serializer = TaskSerializer(qs, many=True)
        return Response(serializer.data)

    def create(self, request):
        serializer = TaskCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = create_task(tenant=self.tenant, actor=request.user, **serializer.validated_data)
        task = (
            Task.objects.filter(tenant=self.tenant, pk=task.pk)
            .select_related("created_by")
            .prefetch_related("assignments__employee")
            .first()
        )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        task = get_object_or_404(
            Task.objects.filter(tenant=self.tenant)
            .select_related("created_by")
            .prefetch_related("assignments__employee"),
            pk=pk,
        )
        employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
        if not self.has_manage:
            # **٤٠٤ لا ٤٠٣**: مهمّةٌ ليست له لا يجب أن يعرف بوجودها أصلاً.
            if not employee or not any(
                a.employee_id == employee.id for a in task.assignments.all()
            ):
                raise Http404
        context = {"request": request}
        if employee:
            context["employee_id"] = employee.id
        return Response(TaskSerializer(task, context=context).data)

    def update(self, request, pk=None):
        return self._save_update(request, pk=pk, partial=False)

    def partial_update(self, request, pk=None):
        return self._save_update(request, pk=pk, partial=True)

    def _save_update(self, request, pk=None, partial=False):
        task = get_object_or_404(Task.objects.filter(tenant=self.tenant), pk=pk)
        serializer = TaskUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        task = update_task(task=task, actor=request.user, **serializer.validated_data)
        task = (
            Task.objects.filter(tenant=self.tenant, pk=task.pk)
            .select_related("created_by")
            .prefetch_related("assignments__employee")
            .first()
        )
        return Response(TaskSerializer(task).data)

    def destroy(self, request, pk=None):
        task = get_object_or_404(Task.objects.filter(tenant=self.tenant), pk=pk)
        delete_task(task=task, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
        if not employee:
            return Response([])
        qs = (
            Task.objects.filter(tenant=self.tenant, assignments__employee=employee)
            .select_related("created_by")
            .prefetch_related("assignments__employee")
            .distinct()
            .order_by("-id")
        )
        serializer = TaskSerializer(
            qs, many=True, context={"request": request, "employee_id": employee.id}
        )
        return Response(serializer.data)

    def _get_requester_employee(self, request) -> Employee:
        employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
        if not employee:
            raise NotFound("سجل الموظف غير موجود في هذه الشركة.")
        return employee

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        task = get_object_or_404(Task.objects.filter(tenant=self.tenant), pk=pk)
        employee = self._get_requester_employee(request)
        assignment = start_task_timer(task=task, employee=employee)
        return Response(TaskAssignmentSerializer(assignment).data)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        task = get_object_or_404(Task.objects.filter(tenant=self.tenant), pk=pk)
        employee = self._get_requester_employee(request)
        assignment = stop_task_timer(task=task, employee=employee)
        return Response(TaskAssignmentSerializer(assignment).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        task = get_object_or_404(Task.objects.filter(tenant=self.tenant), pk=pk)
        employee = self._get_requester_employee(request)
        serializer = TaskSubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission = submit_task(
            task=task,
            employee=employee,
            actor=request.user,
            body=serializer.validated_data.get("body", ""),
            items=serializer.validated_data.get("items", []),
            attachments=serializer.validated_data.get("attachments", []),
        )
        submission = (
            TaskSubmission.objects.filter(tenant=self.tenant, pk=submission.pk)
            .select_related("task", "employee", "reviewer")
            .prefetch_related("items", "attachments")
            .first()
        )
        return Response(TaskSubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


class TaskSubmissionViewSet(viewsets.ViewSet):
    """عرض تسليمات المهام ومراجعتها."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        if self.action not in _SUBMISSION_ACTION_PERMS:
            raise Http404
        required = _SUBMISSION_ACTION_PERMS[self.action]
        if required:
            require_perm(request, required, tenant=self.tenant)
        else:
            has_manage = user_has_perm(request.user, self.tenant, PERM_MANAGE)
            has_self = user_has_perm(request.user, self.tenant, PERM_SELF)
            if not (has_manage or has_self):
                require_perm(request, PERM_SELF, tenant=self.tenant)

    def list(self, request):
        has_manage = user_has_perm(request.user, self.tenant, PERM_MANAGE)
        if has_manage:
            qs = TaskSubmission.objects.filter(tenant=self.tenant)
        else:
            employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
            if not employee:
                return Response([])
            qs = TaskSubmission.objects.filter(tenant=self.tenant, employee=employee)

        # فلترةٌ في الخادم لا في المتصفّح: فتحُ مهمّةٍ واحدةٍ كان يُنزل سجلَّ
        # تسليمات الشركة كلَّه — بنصوصه وبنوده ومرفقاته — ثمّ يرمي ما لا يخصّها.
        task_id = request.query_params.get("task")
        if task_id:
            if not str(task_id).isdigit():
                raise ValidationError({"task": "معرّف المهمّة يجب أن يكون رقماً."})
            qs = qs.filter(task_id=int(task_id))

        decision = request.query_params.get("decision")
        if decision:
            valid = {value for value, _ in TaskSubmission.DECISION_CHOICES}
            if decision not in valid:
                raise ValidationError({"decision": "قرارُ مراجعةٍ غيرُ معروف."})
            qs = qs.filter(decision=decision)

        qs = (
            qs.select_related("task", "employee", "reviewer")
            .prefetch_related("items", "attachments")
            .order_by("-created_at")
        )
        serializer = TaskSubmissionSerializer(qs, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        submission = get_object_or_404(
            TaskSubmission.objects.filter(tenant=self.tenant)
            .select_related("task", "employee", "reviewer")
            .prefetch_related("items", "attachments"),
            pk=pk,
        )
        has_manage = user_has_perm(request.user, self.tenant, PERM_MANAGE)
        if not has_manage:
            employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
            if not employee or submission.employee_id != employee.id:
                raise Http404
        return Response(TaskSubmissionSerializer(submission).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        submission = get_object_or_404(
            TaskSubmission.objects.filter(tenant=self.tenant)
            .select_related("task", "employee"),
            pk=pk,
        )
        serializer = TaskSubmissionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reviewed = review_submission(
            submission=submission,
            actor=request.user,
            decision=serializer.validated_data["decision"],
            reviewer_notes=serializer.validated_data.get("reviewer_notes", ""),
        )
        reviewed = (
            TaskSubmission.objects.filter(tenant=self.tenant, pk=reviewed.pk)
            .select_related("task", "employee", "reviewer")
            .prefetch_related("items", "attachments")
            .first()
        )
        return Response(TaskSubmissionSerializer(reviewed).data)

    @action(detail=True, methods=["post"])
    def unreview(self, request, pk=None):
        submission = get_object_or_404(
            TaskSubmission.objects.filter(tenant=self.tenant)
            .select_related("task", "employee"),
            pk=pk,
        )
        serializer = UnreviewSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        unreviewed, _ = unreview_submission(
            submission=submission,
            actor=request.user,
            reason=serializer.validated_data["reason"],
        )
        unreviewed = (
            TaskSubmission.objects.filter(tenant=self.tenant, pk=unreviewed.pk)
            .select_related("task", "employee", "reviewer")
            .prefetch_related("items", "attachments")
            .first()
        )
        return Response(TaskSubmissionSerializer(unreviewed).data)


class PointViewSet(viewsets.ViewSet):
    """سجل النقاط والنقاط اليدوية وملخص شاشة يومي."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        if self.action not in _POINT_ACTION_PERMS:
            raise Http404
        required = _POINT_ACTION_PERMS[self.action]
        if required:
            require_perm(request, required, tenant=self.tenant)
        else:
            has_manage = user_has_perm(request.user, self.tenant, PERM_MANAGE)
            has_self = user_has_perm(request.user, self.tenant, PERM_SELF)
            if not (has_manage or has_self):
                require_perm(request, PERM_SELF, tenant=self.tenant)

    def list(self, request):
        has_manage = user_has_perm(request.user, self.tenant, PERM_MANAGE)
        if has_manage:
            qs = PointEntry.objects.filter(tenant=self.tenant)
            emp_id = request.query_params.get("employee")
            if emp_id and emp_id.isdigit():
                qs = qs.filter(employee_id=int(emp_id))
        else:
            employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
            if not employee:
                return Response([])
            qs = PointEntry.objects.filter(tenant=self.tenant, employee=employee)

        # **الشهرُ الحاليّ افتراضاً**: سجلٌّ بلا نافذةٍ ينمو بلا سقفٍ لمديرٍ يفتحه
        # بعد سنة. و`?month=YYYY-MM` تفتح شهراً بعينه.
        start_date, end_date, _ = parse_month_bounds(request.query_params.get("month"))
        qs = qs.filter(awarded_on__gte=start_date, awarded_on__lte=end_date)

        qs = (
            qs.select_related("employee", "created_by")
            .order_by("-awarded_on", "-created_at", "-id")
        )
        serializer = PointEntrySerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
        if not employee:
            # من لا سجلَّ موظفٍ له: صفرُ نقاطٍ **وبلا رتبة** — `rank: 0` رقمٌ
            # يُقرأ رتبةً، و`None` تقول «خارج اللوحة» بلا لبس.
            return Response({
                "employee": None,
                "employee_name": "",
                "points": 0,
                "rank": None,
                "open_tasks_count": 0,
            })
        data = get_points_summary(tenant=self.tenant, employee=employee)
        return Response(data)

    @action(detail=False, methods=["post"])
    def manual(self, request):
        serializer = ManualPointEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        entry = record_manual_points(
            tenant=self.tenant,
            actor=request.user,
            employee_id=validated["employee"],
            points=validated["points"],
            reason=validated["reason"],
        )
        return Response(PointEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class AttendanceCheckInView(APIView):
    """زر تأكيد الحضور لكسب نقاط النشاط اليومي (مفتاح employee_ops.self).

    ملاحظة: هذا ليس حضورَ الدوام: `hr` فيه حضورٌ حقيقيّ بمفتاح `ess.self`.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        require_perm(request, PERM_SELF, tenant=self.tenant)

    def post(self, request):
        employee = Employee.objects.filter(tenant=self.tenant, user=request.user).first()
        if not employee:
            raise NotFound("سجل الموظف غير موجود في هذه الشركة.")
        res = attendance_check_in(
            tenant=self.tenant,
            employee=employee,
            actor=request.user,
        )
        return Response(res, status=status.HTTP_200_OK)


class LeaderboardView(APIView):
    """لوحة الشرف الشهرية — يراها الجميع كاملة من أولها لآخرها."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.tenant = require_module(request, MODULE_KEY)
        require_perm(request, PERM_SELF, tenant=self.tenant)

    def get(self, request):
        month_str = request.query_params.get("month")
        results, month = get_leaderboard_data(tenant=self.tenant, month_str=month_str)
        settings = settings_for_read(self.tenant)
        return Response({
            "month": month,
            "highlight_count": settings.leaderboard_highlight_count,
            "results": results,
        })

