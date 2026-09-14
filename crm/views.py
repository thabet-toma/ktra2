"""نقاط نواة الـCRM تحت `/api/platform/crm/` — كلُّ نقطةٍ محروسةٌ بموظّف أو مدير عمليات."""
from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from platform_ops.models import PlatformEmployee
from platform_ops.permissions import IsPlatformOperationsManager, IsPlatformOperationsStaff

from .models import Lead, LeadTransfer
from .phone import PhoneNormalizationError, normalize_phone
from .serializers import (
    LeadActivityCreateSerializer,
    LeadActivitySerializer,
    LeadCreateSerializer,
    LeadImportBatchSerializer,
    LeadImportRequestSerializer,
    LeadPatchSerializer,
    LeadSerializer,
    LeadStatusChangeSerializer,
    LeadTransferCreateSerializer,
    LeadTransferSerializer,
    RejectLeadSerializer,
    TransferDecisionSerializer,
)
from .services import (
    CrmError,
    DuplicateLeadError,
    approve_lead,
    can_decide_lead_transfer,
    change_lead_status,
    claim_lead,
    decide_lead_transfer,
    employee_lead_stats,
    follow_up_day_bounds,
    import_leads,
    lead_contact_stats,
    log_activity,
    lookup_lead_by_phone,
    manager_lead_overview,
    reject_lead,
    release_lead,
    request_lead_transfer,
    suggest_lead,
    transfer_lead,
)
from .services import create_lead as create_lead_service


def _is_manager(request, view) -> bool:
    return IsPlatformOperationsManager().has_permission(request, view)


def _current_employee(request):
    return getattr(request.user, "platform_employee", None)


def _transfer_context(request, view) -> dict:
    """سياقُ `LeadTransferSerializer` — هويّتان يحتاجهما `can_decide` (212-Q2-ب)."""
    return {
        "request": request,
        "is_manager": _is_manager(request, view),
        "current_employee": _current_employee(request),
    }


def _get_employee_or_400(pk):
    try:
        return PlatformEmployee.objects.get(pk=pk)
    except PlatformEmployee.DoesNotExist:
        raise ValidationError({"to_employee": ["موظف العمليات غير موجود."]})


def _error_response(exc: CrmError) -> Response:
    return Response({"detail": exc.detail, "code": exc.code}, status=exc.status_code)


def _duplicate_response(exc: DuplicateLeadError) -> Response:
    return Response(
        {
            "detail": exc.detail,
            "code": exc.code,
            "existing_lead_id": exc.existing_lead.pk,
            "existing_lead_name": exc.existing_lead.store_name,
            "matched_phone": exc.matched_e164,
            "assigned_to": exc.assigned_to,
        },
        status=exc.status_code,
    )


def _apply_lead_filters(qs, request):
    params = request.query_params
    status_param = params.get("status")
    if status_param:
        qs = qs.filter(status=status_param)
    q = params.get("q")
    if q:
        qs = qs.filter(Q(store_name__icontains=q) | Q(owner_name__icontains=q))
    phone = params.get("phone")
    if phone:
        try:
            e164 = normalize_phone(phone)
        except PhoneNormalizationError:
            return qs.none()
        qs = qs.filter(phones__e164=e164)
    approval = params.get("approval_status")
    if approval:
        qs = qs.filter(approval_status=approval)
    follow_up = params.get("follow_up")
    if follow_up:
        # الحدُّ يومٌ لا لحظة، ومن `follow_up_day_bounds` وحدَها كي لا يتفرّق
        # تعريفُ «متأخّر» بين المرشّح والعدّاد والشارة — راجع وثيقتَها.
        start_of_today, start_of_tomorrow = follow_up_day_bounds()
        if follow_up == "due":
            qs = qs.filter(next_follow_up_at__lt=start_of_tomorrow)
        elif follow_up == "overdue":
            qs = qs.filter(next_follow_up_at__lt=start_of_today)
        elif follow_up == "upcoming":
            qs = qs.filter(next_follow_up_at__gte=start_of_tomorrow)
        else:
            raise ValidationError({"follow_up": ["القيمة يجب أن تكون due أو overdue أو upcoming."]})
        qs = qs.order_by("next_follow_up_at")
    return qs


def _scoped_queryset_for_list(base, request, view):
    is_manager = _is_manager(request, view)
    employee = _current_employee(request)
    scope = request.query_params.get("scope")
    pool_qs = base.filter(assigned_to__isnull=True, approval_status=Lead.Approval.APPROVED)
    mine_qs = base.filter(assigned_to=employee) if employee else base.none()

    if is_manager:
        if scope == "mine":
            return mine_qs
        if scope == "pool":
            return pool_qs
        return base  # 'all' أو بلا تحديد: كلُّ الصفوف — هذا مدير.

    if scope == "pool":
        return pool_qs
    # 'all' يُضيَّق بصمتٍ إلى 'mine' لغير المدير — لا خطأ.
    return mine_qs


def _scoped_queryset_for_retrieve(base, request, view):
    if _is_manager(request, view):
        return base
    employee = _current_employee(request)
    pool_q = Q(assigned_to__isnull=True, approval_status=Lead.Approval.APPROVED)
    if employee is not None:
        return base.filter(Q(assigned_to=employee) | pool_q)
    return base.filter(pool_q)


class LeadViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """الزبائنُ المحتمَلون — القراءةُ مضيَّقةٌ بالإسناد، والكتابةُ محروسةٌ في الخدمة.

    **`retrieve` مضيَّقةٌ بقائمةٍ (own+pool) فتردّ 404 على صفّ زميل، وكلّ فعلٍ
    آخر (`status`/`activities`/`transfer`/`claim`…) يقرأ الكائن كاملاً ويترك
    الرفضَ لطبقة الخدمة فيردّ 403** — الفرقُ مقصودٌ (§٧-٣ من التذكرة): قراءةُ
    الوجود شيءٌ، والكتابةُ على ملكٍ غير ملكك شيءٌ آخر.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]
    serializer_class = LeadSerializer

    def get_queryset(self):
        base = (
            Lead.objects.select_related("assigned_to__user", "suggested_by__user")
            .prefetch_related("phones")
            .order_by("-created_at")
        )
        if self.action == "list":
            qs = _scoped_queryset_for_list(base, self.request, self)
        elif self.action in {"retrieve", "stats"}:
            # `stats` قراءةٌ على صفٍّ واحد، فتلبس تضييقَ `retrieve` نفسَه: صفُّ
            # زميلٍ يردّ ٤٠٤ لا أرقاماً عنه. ولو لبست تضييقَ الباقي (الصفوفَ
            # كلَّها) لصارت النقطةُ بابَ تجسّسٍ على شغل الزميل بلا حارس.
            qs = _scoped_queryset_for_retrieve(base, self.request, self)
        else:
            qs = base
        return _apply_lead_filters(qs, self.request)

    def create(self, request, *args, **kwargs):
        payload = LeadCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        phones = data.pop("phones")

        is_manager = _is_manager(request, self)
        employee = _current_employee(request)
        try:
            if is_manager:
                lead = create_lead_service(actor=request.user, phones=phones, **data)
            else:
                if employee is None:
                    raise PermissionDenied("لا صفّ موظّفٍ لهذا المستخدم.")
                lead = suggest_lead(employee=employee, actor=request.user, phones=phones, **data)
        except DuplicateLeadError as exc:
            return _duplicate_response(exc)
        except CrmError as exc:
            return _error_response(exc)
        return Response(LeadSerializer(lead).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_manager = _is_manager(request, self)
        employee = _current_employee(request)
        if not is_manager and (employee is None or instance.assigned_to_id != employee.pk):
            raise PermissionDenied("هذا العميلُ مُسنَدٌ لموظّفٍ آخر.")
        serializer = LeadPatchSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(LeadSerializer(instance).data)

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        phone = request.query_params.get("phone", "")
        try:
            result = lookup_lead_by_phone(phone, requesting_employee=_current_employee(request))
        except CrmError as exc:
            return _error_response(exc)
        return Response(result)

    @action(detail=True, methods=["post"])
    def claim(self, request, pk=None):
        employee = _current_employee(request)
        if employee is None:
            raise PermissionDenied("لا صفّ موظّفٍ لهذا المستخدم.")
        lead = self.get_object()
        try:
            lead = claim_lead(lead=lead, employee=employee)
        except CrmError as exc:
            return _error_response(exc)
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"], permission_classes=[IsPlatformOperationsManager])
    def release(self, request, pk=None):
        lead = self.get_object()
        reason = request.data.get("reason", "")
        lead = release_lead(lead=lead, actor=request.user, reason=reason)
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["get", "post", "put", "patch", "delete"])
    def activities(self, request, pk=None):
        """سجلُّ التواصل يُقرأ ويُضاف إليه فقط — `PUT`/`PATCH`/`DELETE` تردّ 405
        بنصٍّ عربيٍّ صريح لا برسالة DRF الإنجليزيّة الافتراضية."""
        if request.method in ("PUT", "PATCH", "DELETE"):
            return Response(
                {"detail": "سجلُّ التواصل لا يُعدَّل ولا يُحذَف.", "code": "activity_append_only"},
                status=405,
            )
        lead = self.get_object()
        is_manager = _is_manager(request, self)
        employee = _current_employee(request)

        if request.method == "GET":
            if not is_manager and (employee is None or lead.assigned_to_id != employee.pk):
                raise PermissionDenied("هذا العميلُ مُسنَدٌ لموظّفٍ آخر.")
            qs = lead.activities.all()
            page = self.paginate_queryset(qs)
            serializer = LeadActivitySerializer(page if page is not None else qs, many=True)
            if page is not None:
                return self.get_paginated_response(serializer.data)
            return Response(serializer.data)

        payload = LeadActivityCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            activity = log_activity(
                lead=lead, employee=employee, actor=request.user, is_manager=is_manager,
                **payload.validated_data,
            )
        except CrmError as exc:
            return _error_response(exc)
        return Response(LeadActivitySerializer(activity).data, status=201)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """ستاتستكس الرقم (212-R4) — تُحسَب في الخادم لأنّ سجلَّ التواصل مُصفَّح."""
        return Response(lead_contact_stats(self.get_object()))

    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        lead = self.get_object()
        payload = LeadStatusChangeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            lead = change_lead_status(
                lead=lead, employee=_current_employee(request), actor=request.user,
                is_manager=_is_manager(request, self), **payload.validated_data,
            )
        except CrmError as exc:
            return _error_response(exc)
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer_direct(self, request, pk=None):
        lead = self.get_object()
        payload = LeadTransferCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        to_employee = _get_employee_or_400(payload.validated_data["to_employee"])
        try:
            transfer = transfer_lead(
                lead=lead, to_employee=to_employee, reason=payload.validated_data["reason"],
                actor=request.user, actor_employee=_current_employee(request),
                is_manager=_is_manager(request, self),
            )
        except CrmError as exc:
            return _error_response(exc)
        # السياقُ يُمرَّر هنا أيضاً كي لا يكون `can_decide` في جوابِ الإنشاء
        # أصدقَ أو أكذبَ منه في جوابِ القائمة — حقلٌ واحدٌ بمعنًى واحد.
        return Response(
            LeadTransferSerializer(transfer, context=_transfer_context(request, self)).data, status=201,
        )

    @action(detail=True, methods=["post"], url_path="transfer-requests")
    def transfer_request(self, request, pk=None):
        lead = self.get_object()
        payload = LeadTransferCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        to_employee = _get_employee_or_400(payload.validated_data["to_employee"])
        try:
            transfer = request_lead_transfer(
                lead=lead, to_employee=to_employee, reason=payload.validated_data["reason"], actor=request.user,
            )
        except CrmError as exc:
            return _error_response(exc)
        # السياقُ يُمرَّر هنا أيضاً كي لا يكون `can_decide` في جوابِ الإنشاء
        # أصدقَ أو أكذبَ منه في جوابِ القائمة — حقلٌ واحدٌ بمعنًى واحد.
        return Response(
            LeadTransferSerializer(transfer, context=_transfer_context(request, self)).data, status=201,
        )

    @action(detail=True, methods=["post"], permission_classes=[IsPlatformOperationsManager])
    def approve(self, request, pk=None):
        lead = self.get_object()
        try:
            lead = approve_lead(lead=lead, actor=request.user)
        except CrmError as exc:
            return _error_response(exc)
        return Response(LeadSerializer(lead).data)

    @action(detail=True, methods=["post"], permission_classes=[IsPlatformOperationsManager])
    def reject(self, request, pk=None):
        lead = self.get_object()
        payload = RejectLeadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            lead = reject_lead(lead=lead, actor=request.user, reason=payload.validated_data["reason"])
        except CrmError as exc:
            return _error_response(exc)
        return Response(LeadSerializer(lead).data)

    @action(detail=False, methods=["post"], url_path="import", permission_classes=[IsPlatformOperationsManager])
    def import_leads_action(self, request):
        payload = LeadImportRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = import_leads(
            rows=payload.validated_data["rows"], uploaded_by=request.user,
            file_name=payload.validated_data.get("file_name", ""),
        )
        return Response(LeadImportBatchSerializer(batch).data, status=201)


class LeadTransferViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """طلباتُ التحويل المعلَّقة والمقرَّرة — قراءةً، والبتُّ عبر `decide`."""

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]
    serializer_class = LeadTransferSerializer

    def get_queryset(self):
        qs = (
            LeadTransfer.objects.select_related("from_employee__user", "to_employee__user", "lead")
            .order_by("-created_at")
        )
        if _is_manager(self.request, self):
            return qs
        employee = _current_employee(self.request)
        if employee is None:
            return qs.none()
        return qs.filter(Q(from_employee=employee) | Q(to_employee=employee))

    def get_serializer_context(self):
        # المُسلسِلُ يحتاج الهويّتين ليجيب `can_decide`، وهما تُحسَبان هنا حيث
        # يعيش `IsPlatformOperationsManager` — فلا يستورد المُسلسِلُ الـviews.
        return {**super().get_serializer_context(), **_transfer_context(self.request, self)}

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        transfer = self.get_object()
        is_manager = _is_manager(request, self)
        employee = _current_employee(request)
        if not can_decide_lead_transfer(transfer=transfer, employee=employee, is_manager=is_manager):
            raise PermissionDenied("لا صلاحيةَ لك للبتّ في هذا التحويل.")
        payload = TransferDecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            transfer = decide_lead_transfer(
                transfer=transfer, approve=payload.validated_data["approve"], actor=request.user,
                note=payload.validated_data.get("note", ""),
            )
        except CrmError as exc:
            return _error_response(exc)
        return Response(LeadTransferSerializer(transfer, context=_transfer_context(request, self)).data)


class ColleagueDirectoryView(APIView):
    """دليلُ الزملاء لمنتقي «تحويل إلى» — معرّفٌ واسمٌ ولا شيءَ غيرَهما.

    **بلا هذه النقطة لا يستطيع موظّفٌ تحويلَ خطٍّ إلى زميل أصلاً**: النقطةُ
    القائمةُ `/api/platform/ops/employees/` تُضيَّق لغير المدير على **صفّه هو
    وحدَه** (`PlatformEmployeeViewSet.get_queryset`) — وذلك تضييقٌ مقصودٌ محروسٌ
    لا يُوسَّع، لأنّه يحمل التقييمَ والمستهدفاتِ والمحفظة. فالحلُّ نقطةٌ ثانيةٌ
    ضيّقةُ الحمولة لا توسيعُ الأولى.

    ولا تُعيد إلّا `active`: من هو «في إجازة» أو «خارج الخدمة» لا يُسلَّم خطٌّ
    يُنتظَر منه اتّصالٌ اليوم — والقائمةُ منتقي إسنادٍ لا سجلَّ موظّفين.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]

    def get(self, request):
        rows = (
            PlatformEmployee.objects.filter(status=PlatformEmployee.Status.ACTIVE)
            .select_related("user")
            .order_by("user__first_name", "user__username")
        )
        me = _current_employee(request)
        return Response([
            {
                "id": employee.pk,
                "name": employee.user.get_full_name() or employee.user.username,
                "job_title": employee.job_title,
                "is_me": bool(me and employee.pk == me.pk),
            }
            for employee in rows
        ])


class MyLeadStatsView(APIView):
    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]

    def get(self, request):
        employee = _current_employee(request)
        if employee is None:
            raise PermissionDenied("لا صفّ موظّفٍ لهذا المستخدم.")
        return Response(employee_lead_stats(employee))


class ManagerLeadOverviewView(APIView):
    permission_classes = [IsPlatformOperationsManager]

    def get(self, request):
        return Response(manager_lead_overview())
