"""واجهات برمجة تطبيقات عمليات المنصة (المرحلة الأولى).

**قراءةٌ فقط في هذه المرحلة.** تغييرُ الحالة في هذه الوحدة يمرّ بطبقة الخدمات
(`platform_ops/services.py`) لا بـ`ModelViewSet` عامّ: الإسنادُ وتفعيلُ الخدمة
لهما قواعدُ لا يعرفها المُسلسِل — بوّابةُ الاشتراك النشط، وفرادةُ الارتباط تحت
قفل، وسجلُّ النشاط. فنقاطُ الكتابة تُفتح في مرحلتها ومعها خدمتُها.

**ولا فلترَ شركةٍ هنا عن قصد.** قاعدةُ المستودع أنّ `get_queryset` بلا فلتر
شركة تسريبُ بيانات، وهي قاعدةُ مسارات المستأجرين. هذه مساراتُ منصّةٍ تحت
`/api/platform/` بلا `X-Tenant-Id` أصلاً، محروسةٌ بـ`IsPlatformOperationsManager`،
وغرضُها بالضبط أن يرى مديرُ العمليات كلَّ الشركات في جدولٍ واحد.
"""
import requests
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils import timezone
from rest_framework import status, viewsets

from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import TenantAsset
from core.tenant_utils import get_tenant
from tenants.models import Tenant, UserCompanyMembership

from .authentication import HasValidIntegrationKey, IntegrationKeyAuthentication
from .services import (
    DailyRatingError,
    IntegrationKeyError,
    PlatformOpsError,
    RatingTokenGone,
    RatingTokenNotFound,
    WorkOrderError,
    calculate_employee_performance,
    calculate_employee_ratings_summary,
    calculate_two_health_scores,
    capture_performance_snapshot,
    close_job_posting,
    create_applicant_invitation,
    create_job_posting,
    create_platform_recruiter,
    generate_daily_rating_token,
    generate_integration_key,
    get_my_books_tab_data,
    get_tenant_quota_usage,
    get_platform_dashboard_summary,
    invitation_public_url,
    rank_employees_performance,
    rate_applicant,
    receive_channel_work_order,
    regenerate_job_posting_token,
    reopen_job_posting,
    resolve_daily_rating_token,
    rating_public_url,
    revoke_integration_key,
    revoke_platform_recruiter,
    rotate_integration_key,
    submit_daily_rating,
    suspend_engagement,
    transition_applicant_status,
    update_daily_rating,
    is_platform_employee,
    is_platform_recruiter,
)
from .throttles import ClientIpScopedThrottle, IntegrationKeyThrottle

from core.platform_admin_api import IsPlatformAdmin

from .models import (
    DailyRating,
    Engagement,
    IntegrationKey,
    JobApplicant,
    JobPosting,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformNotification,
    PlatformRecruiter,
    PolicyProfile,
    ServiceSubscription,
    SubscriptionBillingRecord,
    WorkOrder,
)
from .permissions import (
    IsPlatformOperationsManager,
    IsPlatformOperationsStaff,
    IsPlatformRecruiter,
)
from .public_hiring.cv_validation import guess_cv_content_type
from .serializers import (
    DailyRatingCreateSerializer,
    DailyRatingSerializer,
    DailyRatingUpdateSerializer,
    GenerateRatingLinkSerializer,
    IntegrationKeySerializer,
    JobApplicantSerializer,
    JobPostingSerializer,
    PerformanceSnapshotSerializer,
    PlatformActivityLogSerializer,
    PlatformEmployeeSerializer,
    PlatformNotificationSerializer,
    PlatformRecruiterSerializer,
    PolicyProfileSerializer,
    PublicRatingSubmitSerializer,
    ServiceSubscriptionSerializer,
    SubscriptionBillingRecordSerializer,
    WorkOrderSerializer,
)


#: رسالةُ رفضِ تحديدِ الشركات من الطلب — الشركاتُ تُشتقّ من الارتباطات وحدَها.
#: سقفُ صفوفِ سجلّ النشاط في استجابةٍ واحدة — تحرٍّ لا تفريغُ جدول.
PLATFORM_ACTIVITY_PAGE_CAP = 200

CROSS_TENANT_FROM_REQUEST_KEYS = ("tenant", "tenants", "tenant_ids", "tenant_id")

#: نقاطُ **سطح المستأجر** (م٧) تُضيف `company`/`companies` إلى المرفوض: شركتُها
#: من الجلسة لا من الطلب، فأيُّ تسميةٍ للشركة فيه محاولةُ عبور.
#: **ولا تُضاف إلى التُّرسانة المشتركة**: `WorkOrderViewSet` يقبل `company`
#: **تضييقاً داخل النطاق المشتقّ** — عقدُ م٦ («كلُّ رقمٍ يصل إلى صفوفه»)، وإدراجُها
#: هناك يجعل كلَّ نقرةِ بطاقةِ شركةٍ تردّ 400 ويُميت الفرعَ الذي يقرؤها بعد أسطر.
TENANT_SURFACE_FORBIDDEN_KEYS = CROSS_TENANT_FROM_REQUEST_KEYS + ("company", "companies")


def _service_error(exc):
    """ردُّ خطأِ خدمةٍ بعقدِ الوحدة: الرمزُ في الجسم، والحالةُ من الاستثناء لا مثبّتة."""
    return Response({"detail": exc.detail, "code": exc.code}, status=exc.status_code)


def _reject_cross_tenant_from_request(request):
    """رفضُ أيِّ وسيطِ شركةٍ يرسله العميل — في المسار أو الجسم — بـ400 لا بتجاهلٍ صامت."""
    body = request.data if isinstance(getattr(request, "data", None), dict) else {}
    for forbidden_key in TENANT_SURFACE_FORBIDDEN_KEYS:
        if forbidden_key in request.query_params or forbidden_key in body:
            raise ValidationError({
                "detail": "تحديد وسائط الشركات غير مسموح.",
                "code": "cross_tenant_query_disallowed_from_request",
            })


def _resolve_caller_tenant(request):
    """حلُّ شركةِ المستخدم عبر المصدر الواحد `core.tenant_utils.get_tenant`.

    لا تُلفَّق الشركةُ أبداً: `get_tenant` يتحقّق من العضوية ويرفض شركةً موقوفةً أو
    ترويسةً مشوَّهة. وحين لا تُرسَل الترويسةُ **ولا** يملك المستخدمُ إلا عضويّةً
    واحدة، تُتَّخذ هي — وإن تعدّدت عضويّاتُه لزمته الترويسةُ صراحةً، فاختيارُ
    «أوّلِ صفٍّ يعيده المحرّك» انقلابُ شركةٍ صامت.

    **وترويسةٌ أُرسلت ولم تُحَلّ تُرَدّ ولا تسقط على البديل**: `get_tenant` بلا
    `raise_on_missing` يكتفي بسطرِ تحذيرٍ ويعيد `None` عند الترويسة المشوَّهة أو
    المجهولة — فلو تلاها البديلُ لعاد 200 ببياناتِ شركةٍ غيرِ التي طُلبت.
    """
    header_sent = bool(request.headers.get("X-Tenant-Id") or request.META.get("HTTP_X_TENANT_ID"))
    tenant = get_tenant(request, raise_on_missing=header_sent)
    if tenant is not None:
        return tenant

    memberships = list(
        UserCompanyMembership.objects.filter(user=request.user)
        .select_related("tenant")
        .order_by("tenant_id")[:2]
    )
    if len(memberships) == 1:
        return memberships[0].tenant
    if len(memberships) > 1:
        raise PermissionDenied("لديك أكثر من شركة؛ أرسل X-Tenant-Id لتحديد الشركة المقصودة.")
    raise PermissionDenied("لا توجد شركة مرتبطة بهذا الحساب.")


def _require_tenant_manager(request, tenant):
    """صاحبُ الشركة (`manager`) وحده — أو السوبر أدمن. عضويّةٌ عاديّةٌ لا تكفي."""
    user = request.user
    if user.is_superuser or IsPlatformOperationsManager().has_permission(request, None):
        return
    is_manager = UserCompanyMembership.objects.filter(
        user=user, tenant=tenant, role="manager",
    ).exists()
    if not is_manager:
        raise PermissionDenied("هذا الإجراء متاح لصاحب الشركة وحده.")


def _resolve_period(raw_year, raw_month):
    """(سنة، شهر) أو خطأٌ صريح — **ولا فترةَ نصفَ محدَّدة**.

    كان `?year=2026` بلا شهرٍ يسقط في الفرع الافتراضيّ فيُعيد أداءَ **كلّ الأزمان**
    وكأنّه أداءُ تلك السنة — إجابةٌ خاطئةٌ صامتة، وهي أسوأُ من خطأ.
    """
    if raw_year in (None, "") and raw_month in (None, ""):
        return None, None, None
    if raw_year in (None, "") or raw_month in (None, ""):
        return None, None, "السنة والشهر يُمرَّران معاً أو لا يُمرَّران — لا أحدُهما وحدَه."
    try:
        year = int(raw_year)
        month = int(raw_month)
    except (TypeError, ValueError):
        return None, None, "السنة والشهر يجب أن يكونا رقمين صحيحين."
    if not (1 <= month <= 12):
        return None, None, "الشهر يجب أن يكون بين ١ و١٢."
    if not (2000 <= year <= 2100):
        return None, None, "السنة خارج المدى المقبول."
    return year, month, None


class PlatformEmployeeViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ موظفي عمليات المنصة وتقييم الأداء — مدير العمليات وفريق العمليات."""

    permission_classes = [IsPlatformOperationsManager | IsPlatformOperationsStaff]
    serializer_class = PlatformEmployeeSerializer
    queryset = PlatformEmployee.objects.select_related("user").all().order_by("-created_at")

    def get_queryset(self):
        qs = super().get_queryset()
        if IsPlatformOperationsManager().has_permission(self.request, self):
            return qs
        return qs.filter(user=self.request.user)

    @action(detail=True, methods=["get"], url_path="performance")
    def performance(self, request, pk=None):
        """استعلام أداء الموظف عبر المقاييس الستة والمحاور الخمسة والدرجة المركبة.

        قاعدة عزل الشركات:
        - الاستعلام العابر للشركات مشروع، لكن الشركات تُشتق من الارتباطات حصراً.
        - لا يُقبل أي وسيط شركة (tenant, tenant_ids, tenants) من الطلب؛ والمحاولة الصريحة تُرفض بـ 400.
        """
        params = request.query_params
        for forbidden_key in CROSS_TENANT_FROM_REQUEST_KEYS:
            if forbidden_key in params:
                return Response(
                    {
                        "detail": "تحديد الشركات غير مسموح؛ تُشتق الشركات تلقائياً من الارتباطات.",
                        "code": "cross_tenant_query_disallowed_from_request",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        emp = self.get_object()
        # موظف المنصة العادي لا يرى إلا أداءه فقط
        is_manager = IsPlatformOperationsManager().has_permission(request, self)
        if not is_manager and emp.user_id != request.user.id:
            return Response(
                {"detail": "غير مصرح لك باستعراض أداء موظف آخر."},
                status=status.HTTP_403_FORBIDDEN,
            )

        year, month, period_error = _resolve_period(
            params.get("year") or params.get("period_year"),
            params.get("month") or params.get("period_month"),
        )
        if period_error:
            return Response({"detail": period_error}, status=status.HTTP_400_BAD_REQUEST)

        perf_data = calculate_employee_performance(
            employee=emp,
            period_year=year,
            period_month=month,
        )
        return Response(perf_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="ranking")
    def ranking(self, request):
        """ترتيب موظفي المنصة — مدير العمليات فقط."""
        if not IsPlatformOperationsManager().has_permission(request, self):
            return Response(
                {"detail": "ترتيب الموظفين متاح لمدير العمليات فقط."},
                status=status.HTTP_403_FORBIDDEN,
            )

        params = request.query_params
        year, month, period_error = _resolve_period(
            params.get("year") or params.get("period_year"),
            params.get("month") or params.get("period_month"),
        )
        if period_error:
            return Response({"detail": period_error}, status=status.HTTP_400_BAD_REQUEST)

        ranking_data = rank_employees_performance(
            period_year=year,
            period_month=month,
        )
        return Response(ranking_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request, pk=None):
        """سجل نشاط الموظف عابراً كل الشركات — للمدير أو الموظف نفسه."""
        params = request.query_params
        for forbidden_key in CROSS_TENANT_FROM_REQUEST_KEYS:
            if forbidden_key in params:
                return Response(
                    {
                        "detail": "تحديد الشركات غير مسموح؛ تُشتق الشركات تلقائياً من الارتباطات.",
                        "code": "cross_tenant_query_disallowed_from_request",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        emp = self.get_object()
        is_manager = IsPlatformOperationsManager().has_permission(request, self)
        if not is_manager and emp.user_id != request.user.id:
            return Response(
                {"detail": "غير مصرح لك باستعراض سجل نشاط موظف آخر."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # **بسقفٍ صريح**: القائمةُ كانت تُسلسِل كلَّ صفوف الموظّف بلا حدّ، والصفحةُ
        # غيرُ مصفَّحةٍ افتراضياً (`OptionalPageNumberPagination` اختياريّة). موظّفٌ
        # بعامٍ من العمل يعني آلافَ الصفوف في استجابةٍ واحدة. والسقفُ نفسُه المعمولُ
        # به في تبويب نشاط `employee_ops`.
        logs = PlatformActivityLog.objects.filter(employee=emp).order_by(
            "-created_at"
        )[:PLATFORM_ACTIVITY_PAGE_CAP]
        serializer = PlatformActivityLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)



class ServiceSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ اشتراكات خدمة المتابعة — مدير العمليات فقط."""

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = ServiceSubscriptionSerializer
    queryset = ServiceSubscription.objects.select_related("tenant").all().order_by("-created_at")


class SubscriptionBillingRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """سجلُّ ما فُوتر فعلاً — قراءةٌ لمدير العمليات وحدَه.

    **قراءةٌ لا كتابة**: الفواتيرُ تُصدَر بأمر الإدارة `bill_service_subscriptions`
    وحدَه (المواصفة: «التوليدُ أمرُ إدارةٍ idempotent — لا توليدٌ كسولٌ عند فتح
    شاشة»)، وهذه النقطةُ نافذةٌ على الناتج لا بابٌ ثانٍ لإنتاجه.
    """

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = SubscriptionBillingRecordSerializer
    queryset = (
        SubscriptionBillingRecord.objects.select_related("invoice", "subscription__tenant")
        .all()
        .order_by("-period_end", "-id")
    )

    def get_queryset(self):
        qs = super().get_queryset()
        subscription_id = self.request.query_params.get("subscription")
        if subscription_id:
            qs = qs.filter(subscription_id=subscription_id)
        # `company` لا `tenant`: عميلُ الواجهة يُسقط مفاتيحَ `tenant*` من كلّ نداءٍ
        # لهذه الوحدة عمداً (`buildCleanQueryString`)، فمرشِّحٌ باسمها لا يصل أبداً.
        # والتسميةُ نفسُها سابقةُ التنقيب في لوحة القيادة.
        company_id = self.request.query_params.get("company")
        if company_id:
            qs = qs.filter(subscription__tenant_id=company_id)
        return qs


class IntegrationKeyViewSet(viewsets.ReadOnlyModelViewSet):
    """مفاتيحُ قنوات الاستقبال — قراءةٌ للمدير، وثلاثةُ أفعالٍ تمرّ بطبقة الخدمات.

    **ولمَ أفعالٌ على viewset للقراءة؟** القاعدةُ في هذه الوحدة أنّ تغييرَ الحالة
    يمرّ بالخدمة لا بـCRUD عامّ — والأفعالُ الثلاثةُ هنا نداءاتٌ مباشرةٌ للخدمات
    نفسِها، فلا تفتح طريقاً يلتفّ عليها. **وبلا هذا الباب** لا يكون المفتاحُ
    «قابلاً للإبطال والتدوير **فوراً** عند تسرّبه» كما تطلب المواصفة، بل عبر
    `manage.py shell` وحدَه — وهذا ليس إبطالاً فوريّاً.

    والرمزُ الخامُّ يظهر **مرّةً واحدةً** في ردّ الإصدار أو التدوير، ولا يُحفَظ.
    """

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = IntegrationKeySerializer
    queryset = IntegrationKey.objects.select_related("tenant").all().order_by("-created_at")

    def _service_error(self, exc):
        return Response({"detail": exc.detail, "code": exc.code}, status=exc.status_code)

    @action(detail=False, methods=["post"], url_path="issue")
    def issue(self, request):
        """إصدارُ مفتاحٍ لقناةِ شركة. الرمزُ الخامُّ في الردّ ولن يظهر ثانيةً."""
        try:
            key, raw_token = generate_integration_key(
                tenant=request.data.get("tenant"),
                channel=str(request.data.get("channel", "")).strip(),
                name=str(request.data.get("name", "")).strip(),
            )
        except IntegrationKeyError as exc:
            return self._service_error(exc)
        except Tenant.DoesNotExist:
            return Response({"detail": "الشركة غير موجودة."}, status=status.HTTP_404_NOT_FOUND)

        data = IntegrationKeySerializer(key).data
        data["raw_token"] = raw_token
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="rotate")
    def rotate(self, request, pk=None):
        """تدويرُ الرمز: الجديدُ يعمل والقديمُ يسقط فوراً."""
        try:
            key, raw_token = rotate_integration_key(key=self.get_object())
        except IntegrationKeyError as exc:
            return self._service_error(exc)

        data = IntegrationKeySerializer(key).data
        data["raw_token"] = raw_token
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, pk=None):
        """إبطالُ المفتاح نهائيّاً — الصفُّ يبقى لأثر المراجعة."""
        try:
            key = revoke_integration_key(
                key=self.get_object(),
                revoked_by=request.user,
                reason=str(request.data.get("reason", "")).strip(),
            )
        except IntegrationKeyError as exc:
            return self._service_error(exc)

        return Response(IntegrationKeySerializer(key).data, status=status.HTTP_200_OK)


class WorkOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ أوامر العمل — قراءة فقط لموظفي ومديري عمليات المنصة.

    **وهذه النقطةُ مفلترةٌ بخلاف أختَيها أعلاه، والفرقُ مقصود**: النقطتان السابقتان
    لمدير المنصّة وحدَه (`IsPlatformOperationsManager`) فيرى كلَّ شيءٍ بحكم موقعه.
    أمّا هنا فيدخل **موظّفُ المنصّة** أيضاً، وهو ليس مالكَ منصّةٍ بل موظّفُ تشغيل:
    فلو بقي `queryset` بلا فلترٍ لرأى أوامرَ **كلِّ الشركات** لا شركاتِه — وهو تسريبٌ
    عابرٌ للشركات داخل الوحدة نفسِها.

    والشركاتُ **تُشتقّ من الارتباطات النشطة** (`Engagement`) لا من الطلب: لا يقبل
    المسارُ قائمةَ شركاتٍ حرّةً، وإلّا صار البابُ الذي أُغلق.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]
    serializer_class = WorkOrderSerializer
    queryset = (
        WorkOrder.objects.select_related("tenant", "assignee__user", "created_by")
        .all()
        .order_by("-created_at")
    )

    def get_queryset(self):
        # 1. فحص وسائط الشركات الممنوعة من الطلب
        params = self.request.query_params
        for forbidden_key in CROSS_TENANT_FROM_REQUEST_KEYS:
            if forbidden_key in params:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    "detail": "تحديد الشركات غير مسموح؛ تُشتق الشركات تلقائياً من الارتباطات.",
                    "code": "cross_tenant_query_disallowed_from_request",
                })

        qs = super().get_queryset()
        user = self.request.user

        # مديرُ المنصّة يرى كلَّ شيء — هو صاحبُ المنصّة لا موظّفٌ فيها.
        if IsPlatformOperationsManager().has_permission(self.request, self):
            base_qs = qs
        else:
            # وموظّفُ المنصّة يرى شركاتِ ارتباطاتِه النشطة وحدَها.
            engaged_tenant_ids = Engagement.objects.filter(
                employee__user=user,
                status=Engagement.Status.ACTIVE,
            ).values_list("tenant_id", flat=True)
            base_qs = qs.filter(tenant_id__in=engaged_tenant_ids)

        # 2. فلاتر التنقيب (company, work_order, assignee, status, is_overdue, metric, kind)
        #
        # **تضييقٌ داخل نطاقٍ مشتقٍّ لا اختيارُ شركةٍ من الطلب**: بطاقةُ الشركة كانت
        # تنقر على رقمِها فتصل قائمةَ **كلّ** الشركات، لأنّ المسارَ يرفض `tenant*` كلَّها.
        # والرفضُ في محلّه — الشركاتُ لا تُختار من الطلب — لكنّ التنقيبَ يلزمه أن يقول
        # «هذه الشركة». فالمفتاحُ اسمُه `company` ويُطبَّق **بعد** الفلترة بالنطاق:
        # شركةٌ خارجَ ارتباطاتك تُعيد صفراً لا تسريباً، فالخاصّيّةُ الأمنيّةُ باقية.
        company_id = params.get("company")
        if company_id:
            base_qs = base_qs.filter(tenant_id=company_id)

        # ورقمُ أمرِ عملٍ بعينه: شذوذُ «تأخّرٌ حرج» ينقر على أمرٍ واحدٍ لا على قائمة.
        work_order_id = params.get("work_order")
        if work_order_id:
            base_qs = base_qs.filter(pk=work_order_id)

        assignee_id = params.get("assignee") or params.get("employee_id")
        if assignee_id:
            base_qs = base_qs.filter(assignee_id=assignee_id)

        status_param = params.get("status")
        if status_param:
            base_qs = base_qs.filter(status=status_param)

        kind_param = params.get("kind")
        if kind_param:
            base_qs = base_qs.filter(kind=kind_param)

        is_overdue = params.get("is_overdue")
        if is_overdue in ("true", "1", True):
            now = timezone.now()
            base_qs = base_qs.filter(
                deadline_at__isnull=False,
                deadline_at__lt=now,
            ).exclude(status__in=[WorkOrder.Status.CLOSED, WorkOrder.Status.CANCELLED, WorkOrder.Status.APPROVAL])

        metric = params.get("metric")
        if metric == "active":
            base_qs = base_qs.filter(status__in=[
                WorkOrder.Status.RECEIVED,
                WorkOrder.Status.SCREENING,
                WorkOrder.Status.DATA_ENTRY,
                WorkOrder.Status.REVIEW,
                WorkOrder.Status.APPROVAL,
                WorkOrder.Status.WAITING_CUSTOMER,
            ])
        elif metric == "overdue":
            now = timezone.now()
            base_qs = base_qs.filter(
                deadline_at__isnull=False,
                deadline_at__lt=now,
            ).exclude(status__in=[WorkOrder.Status.CLOSED, WorkOrder.Status.CANCELLED, WorkOrder.Status.APPROVAL])
        elif metric == "completed":
            base_qs = base_qs.filter(status__in=[WorkOrder.Status.APPROVAL, WorkOrder.Status.CLOSED])
        elif metric in ("cancelled", "rework"):
            base_qs = base_qs.filter(status=WorkOrder.Status.CANCELLED)

        return base_qs


class PolicyProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """عرض ملفات سياسات الأداء — مدير العمليات وفريق العمليات."""

    permission_classes = [IsPlatformOperationsManager | IsPlatformOperationsStaff]
    serializer_class = PolicyProfileSerializer
    queryset = PolicyProfile.objects.all().order_by("specialty")


class PerformanceSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """عرض اللقطات الشهرية المجمدة — قراءة فقط للموظف، والتقاط للمدير."""

    permission_classes = [IsPlatformOperationsManager | IsPlatformOperationsStaff]
    serializer_class = PerformanceSnapshotSerializer
    queryset = (
        PerformanceSnapshot.objects.select_related("employee__user", "policy_profile", "captured_by")
        .all()
        .order_by("-period_year", "-period_month")
    )

    def get_queryset(self):
        qs = super().get_queryset()
        if IsPlatformOperationsManager().has_permission(self.request, self):
            return qs
        return qs.filter(employee__user=self.request.user)

    @action(detail=False, methods=["post"], url_path="capture")
    def capture(self, request):
        """التقاط لقطة أداء شهرية (idempotent) — مدير العمليات فقط."""
        if not IsPlatformOperationsManager().has_permission(request, self):
            return Response(
                {"detail": "التقاط لقطة الأداء متاح لمدير العمليات فقط."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data
        for forbidden_key in CROSS_TENANT_FROM_REQUEST_KEYS:
            if forbidden_key in data or forbidden_key in request.query_params:
                return Response(
                    {
                        "detail": "تحديد الشركات غير مسموح؛ تُشتق الشركات تلقائياً من الارتباطات.",
                        "code": "cross_tenant_query_disallowed_from_request",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        emp_id = data.get("employee") or data.get("employee_id")
        force = bool(data.get("force_refresh", False))

        if not emp_id:
            return Response(
                {"detail": "الموظف حقل إلزامي لالتقاط اللقطة."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # سنةٌ أو شهرٌ فاسدان كانا يبلغان `datetime.date(y, 13, 1)` فيرتدّان ٥٠٠
        year, month, period_error = _resolve_period(
            data.get("period_year") or data.get("year"),
            data.get("period_month") or data.get("month"),
        )
        if period_error or year is None:
            return Response(
                {"detail": period_error or "السنة والشهر حقلان إلزاميان لالتقاط اللقطة."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            employee = PlatformEmployee.objects.get(pk=emp_id)
        except (PlatformEmployee.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "موظف المنصة غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        existed = PerformanceSnapshot.objects.filter(
            employee=employee, period_year=year, period_month=month
        ).exists()
        snapshot = capture_performance_snapshot(
            employee=employee,
            period_year=year,
            period_month=month,
            captured_by=request.user,
            force_refresh=force,
        )
        # ٢٠١ تعني «أُنشئ». إعادةُ لقطةٍ قائمةٍ ليست إنشاءً، والعمليّةُ idempotent.
        return Response(
            PerformanceSnapshotSerializer(snapshot).data,
            status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED,
        )


# ==============================================================================
# نقطة استقبال أوامر العمل من القنوات الخارجية (المرحلة الرابعة م٤)
# ==============================================================================

MAX_INTAKE_PAYLOAD_BYTES = 256 * 1024  # 256 KB

#: حقولُ **التحكُّم** في أمر العمل التي لا يمليها الزبون — الجدولةُ والتسعيرُ قرارُ المنصّة.
#:
#: **والفحصُ على المستوى الأعلى وحدَه، والقائمةُ ضيّقةٌ عمداً.** الغرضُ الأوّلُ للقناة أن
#: يرسل الزبونُ **مستنداً** (فاتورةً غالباً)، والفاتورةُ تحمل مبالغَ وأسعارَ بنودٍ بطبيعتها.
#: فقائمةٌ تضمّ `amount` أو `cost`، أو فحصٌ يغوص في البنود، كان يردُّ كلَّ فاتورةٍ حقيقيّة —
#: أي يُبطل الوحدةَ التي بُنيت لاستقبالها. المنعُ عن إملاء **مُسنَدِ أمر العمل وحالتِه
#: وسعرِ خدمتِنا**، لا عن ذكر مالٍ في مستند الزبون.
FORBIDDEN_INTAKE_CONTROL_FIELDS = frozenset({
    "assignee",
    "assignee_id",
    "status",
    "return_status",
    "price",
    "unit_price",
    "service_price",
})

#: حقولُ المرفقات التي يُمنَع أن تحمل رابطاً — المرفقُ يُرفع أوّلاً وتُرسَل معرّفاتُه.
#:
#: **وهذه تُفحَص في كلّ عمقٍ** بخلاف حقول التحكُّم: `{"attachments": [{"url": "…"}]}`
#: مرفقٌ برابطٍ مهما دُفن، وقصرُ الفحص على المستوى الأعلى يترك البابَ الخلفيَّ مفتوحاً.
#: والمفحوصُ **اسمُ الحقل** لا كلُّ نصٍّ فيه رابط: رسالةُ زبونٍ تذكر رابطاً حمولةٌ مشروعة.
ATTACHMENT_LINK_FIELDS = frozenset({
    "url", "file_url", "link", "links", "attachment_url", "attachment_urls", "file_links",
})


def _first_matching_key(data, names, *, deep):
    """أوّلُ مفتاحٍ في `data` اسمُه ضمن `names` — في المستوى الأعلى أو في كلّ عمق."""
    if isinstance(data, dict):
        for k, v in data.items():
            if str(k).strip().lower() in names:
                return str(k)
            if deep:
                found = _first_matching_key(v, names, deep=True)
                if found:
                    return found
    elif deep and isinstance(data, list):
        for item in data:
            found = _first_matching_key(item, names, deep=True)
            if found:
                return found
    return None


class WorkOrderIntakeView(APIView):
    """نقطة استقبال أوامر العمل من القنوات (م٤).

    القواعد الصارمة:
    1. ليست AllowAny: تُصادق بمفتاح القناة حصراً.
    2. الشركة تُشتق من المفتاح لا من الحمولة.
    3. الحمولة لا تحمل مُسنَداً ولا حالة ولا سعراً؛ وإلا تُرفض صراحة.
    4. لا روابط إنترنت عشوائية؛ المرفقات بمعرفات أصول فقط.
    5. خانق مربوط بالمفتاح.
    6. فحص سقف الحجم بالبايتات الحقيقية (لا بالترويسة).
    7. فرادة external_ref لضمان idempotency: إعادة الطلب ترجع نفس الأمر
       دون احتساب عملية مفوترة ثانية.
    """

    authentication_classes = [IntegrationKeyAuthentication]
    permission_classes = [HasValidIntegrationKey]
    throttle_classes = [IntegrationKeyThrottle]

    def post(self, request):
        key = getattr(request, "auth", None)
        if not key or not hasattr(key, "tenant"):
            return Response(
                {"detail": "مفتاح القناة غير متوفر أو غير صالح."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # 1. سقفُ الحجم بالبايتات — **قبل** قراءة الجسم ثمّ عليه
        #
        # `CONTENT_LENGTH` ترويسةٌ يكتبها المرسِل فلا تُصدَّق وحدَها، لكنّها تُغني عن
        # تحميلِ حمولةٍ ضخمةٍ في الذاكرة قبل ردِّها. والحكمُ النهائيُّ على **البايتات
        # المقروءة فعلاً**. (وما كان هنا من استنطاقِ `wsgi.input` بـ`getbuffer`/`getvalue`
        # داخل `except Exception: pass` كان مسرحاً: هذه سماتُ `FakePayload` في عميل
        # الاختبار وحدَه، وتحت خادمٍ حقيقيٍّ يقطع جانغو القراءةَ عند `CONTENT_LENGTH`
        # فلا يمكن أن يزيد الجسمُ عن المعلَن أصلاً.)
        declared = request.META.get("CONTENT_LENGTH")
        if declared:
            try:
                if int(declared) > MAX_INTAKE_PAYLOAD_BYTES:
                    return Response(
                        {"detail": f"حجم الحمولة يتجاوز الحد الأقصى المسموح ({MAX_INTAKE_PAYLOAD_BYTES} بايت)."},
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )
            except (TypeError, ValueError):
                pass

        if len(request.body) > MAX_INTAKE_PAYLOAD_BYTES:
            return Response(
                {"detail": f"حجم الحمولة يتجاوز الحد الأقصى المسموح ({MAX_INTAKE_PAYLOAD_BYTES} بايت)."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # 2. فحص الحقول الممنوعة (assignee, status, price وما يكافئها)
        forbidden_key = _first_matching_key(
            request.data, FORBIDDEN_INTAKE_CONTROL_FIELDS, deep=False
        )
        if forbidden_key:
            return Response(
                {"detail": f"الحمولة لا يجوز أن تحمل حقلاً ممنوعاً: {forbidden_key}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. منع حقول المرفقات التي تحمل روابط
        link_field = _first_matching_key(
            request.data, ATTACHMENT_LINK_FIELDS, deep=True
        )
        if link_field:
            return Response(
                {
                    "detail": f"روابط المرفقات غير مسموحة في الحقل {link_field}: تُرفع "
                    "المرفقات عبر خدمة الوسائط ثمّ تُرسَل معرّفاتها في attachment_ids."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. فحص والتحقق من معرفات المرفقات
        attachment_ids = request.data.get("attachment_ids")
        if attachment_ids is not None:
            if not isinstance(attachment_ids, list):
                return Response(
                    {"detail": "حقل attachment_ids يجب أن يكون قائمة معرفات رقمية."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            for aid in attachment_ids:
                if not isinstance(aid, int) or isinstance(aid, bool):
                    return Response(
                        {"detail": "كل عنصر في attachment_ids يجب أن يكون معرفاً رقمياً صحيحاً."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            valid_ids = set(
                TenantAsset.objects.filter(
                    id__in=attachment_ids,
                    tenant=key.tenant,
                ).values_list("id", flat=True)
            )
            invalid_ids = [aid for aid in attachment_ids if aid not in valid_ids]
            if invalid_ids:
                return Response(
                    {"detail": f"المرفق {invalid_ids[0]} غير موجود أو لا يتبع لهذه الشركة."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 5. استخراج البيانات (الشركة حصراً من المفتاح، والبيانات المزعومة للشركة تُتجاهل)
        external_ref = str(request.data.get("external_ref", "")).strip()
        if not external_ref:
            return Response(
                {"detail": "حقل المرجع الخارجي (external_ref) إلزامي."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        title = str(request.data.get("title", "")).strip()
        description = str(request.data.get("description", "")).strip()
        kind = str(request.data.get("kind", WorkOrder.Kind.DATA_ENTRY)).strip()

        try:
            work_order, created = receive_channel_work_order(
                key=key,
                title=title,
                external_ref=external_ref,
                description=description,
                kind=kind,
                attachment_ids=attachment_ids,
                intake_payload=request.data if isinstance(request.data, dict) else {},
            )
        except WorkOrderError as exc:
            return Response({"detail": exc.detail}, status=exc.status_code)
        except PlatformOpsError as exc:
            return Response({"detail": exc.detail}, status=exc.status_code)

        # **ردٌّ نحيفٌ لا مُسلسِلُ الإدارة**: `WorkOrderSerializer` يحمل `assignee`
        # و`policy_snapshot` و`waiting_seconds_total` — تفاصيلُ تشغيلٍ داخليّةٌ لا شأنَ
        # لقناةٍ خارجيّةٍ بها. القناةُ تحتاج أن تعرف: وصل، ومرجعُه، وأينَ صار.
        data = {
            "id": work_order.pk,
            "external_ref": work_order.external_ref,
            "channel": work_order.channel,
            "status": work_order.status,
            "received_at": work_order.received_at,
            "created": created,
        }
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(data, status=response_status)


# ==============================================================================
# المرحلة السادسة (م٦): صندوق الإشعارات، السجل العابر، واللوحة التفاعلية
# ==============================================================================

class PlatformNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """صندوق إشعارات منصي مفلتر على الخادم حصراً (م٦).

    - الفلترة على الخادم حصراً: المستخدم لا يستقبل إلا إشعاراته.
    - أنواع مغلقة: تجاوز أجل (sla_breach)، تقييم منخفض (low_score)، تجاوز باقة (quota_exceeded).
    - تحديث كل 60 ثانية ما دام التبويب ظاهراً في الواجهة.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]
    serializer_class = PlatformNotificationSerializer
    queryset = (
        PlatformNotification.objects.select_related("recipient", "tenant")
        .all()
        .order_by("-created_at")
    )

    def get_queryset(self):
        params = self.request.query_params
        for forbidden_key in CROSS_TENANT_FROM_REQUEST_KEYS:
            if forbidden_key in params:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    "detail": "تحديد الشركات غير مسموح؛ تُشتق الشركات تلقائياً من الارتباطات.",
                    "code": "cross_tenant_query_disallowed_from_request",
                })
        # فلترة خادمية صارمة لا استثناء فيها: لا يرى المستخدم إلا إشعاراته
        return super().get_queryset().filter(recipient=self.request.user)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        """تعليم إشعار واحد كمقروء."""
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])
        return Response(PlatformNotificationSerializer(notification).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        """تعليم كافة إشعارات المستخدم كمقروءة."""
        now = timezone.now()
        count = self.get_queryset().filter(is_read=False).update(
            is_read=True, read_at=now, updated_at=now
        )
        return Response({"marked_count": count}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """عدد الإشعارات غير المقروءة للمستخدم الحالي."""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread_count": count}, status=status.HTTP_200_OK)


class PlatformActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """سجل نشاط موظف المنصة عابراً كل الشركات في جدول واحد (القصة رقم ١٣ - م٦).

    - بنية خاصة بوحدة عمليات المنصة وليست توسيعاً لـ ActivityLog.
    - مفهرس زمنياً للقراءة العابرة للشركات.
    - يرفض وسائط الشركات من الطلب بـ 400.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]
    serializer_class = PlatformActivityLogSerializer
    queryset = (
        PlatformActivityLog.objects.select_related("employee__user", "tenant")
        .all()
        .order_by("-created_at")
    )

    def get_queryset(self):
        params = self.request.query_params
        for forbidden_key in CROSS_TENANT_FROM_REQUEST_KEYS:
            if forbidden_key in params:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({
                    "detail": "تحديد الشركات غير مسموح؛ تُشتق الشركات تلقائياً من الارتباطات.",
                    "code": "cross_tenant_query_disallowed_from_request",
                })

        qs = super().get_queryset()
        user = self.request.user
        is_manager = IsPlatformOperationsManager().has_permission(self.request, self)

        if not is_manager:
            qs = qs.filter(employee__user=user)
        else:
            employee_id = params.get("employee") or params.get("employee_id")
            if employee_id:
                qs = qs.filter(employee_id=employee_id)

        action_param = params.get("action")
        if action_param:
            qs = qs.filter(action=action_param)

        return qs


class PlatformDashboardView(APIView):
    """اللوحة التفاعلية وشريط التدخل والتنقيب (م٦).

    - بطاقة لكل موظف افتراضاً، مع مبدل (موظف / شركة).
    - الترتيب الأسوأ أولاً.
    - شريط التدخل: شذوذ فقط (أربعة أنواع لا أكثر).
    - التنقيب: كل رقم ينقر إلى صفوفه.
    - عزل الشركات: مشتقة من الارتباطات، وتحديد الشركات من الطلب مرفوض بـ 400.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]

    def get(self, request):
        params = request.query_params
        for forbidden_key in CROSS_TENANT_FROM_REQUEST_KEYS:
            if forbidden_key in params:
                return Response(
                    {
                        "detail": "تحديد الشركات غير مسموح؛ تُشتق الشركات تلقائياً من الارتباطات.",
                        "code": "cross_tenant_query_disallowed_from_request",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        data = get_platform_dashboard_summary(user=request.user)
        return Response(data, status=status.HTTP_200_OK)


def _rating_for_token(token_obj):
    """التقييمُ القائمُ لمفتاح (شركة، موظف، يوم) — مصدرُ حقيقةٍ واحدٌ للرابط العام."""
    return DailyRating.objects.filter(
        tenant_id=token_obj.tenant_id,
        employee_id=token_obj.employee_id,
        service_date=token_obj.service_date,
    ).first()


class PublicDailyRatingView(APIView):
    """الرابط اليومي العام للتقييم المهشر بلا تسجيل دخول (م٧).

    - لا يتطلب مصادقة (AllowAny).
    - محمي بالخانق ClientIpScopedThrottle (بربط REMOTE_ADDR حصراً).
    - يعيد 404 للرمز غير الصالح، و410 صريحة للرمز المنتهي أو المبطل.
    - حمولة الرد مقيدة بقائمة بيضاء صارمة لمنع أي تسريب لمعلومات الشركة أو الموظف.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_public_rating"

    def get(self, request, token):
        try:
            token_obj = resolve_daily_rating_token(token)
        except RatingTokenNotFound:
            return Response(
                {"detail": "الرابط غير صالح أو غير موجود."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except RatingTokenGone:
            return Response(
                {"detail": "انتهت صلاحية هذا الرابط."},
                status=status.HTTP_410_GONE,
            )

        emp = token_obj.employee
        # **لا `token_obj.rating`**: الرمزُ يُولَّد فارغاً، فتقييمٌ سُجّل من داخل
        # التطبيق لنفس (الشركة، الموظف، اليوم) كان يبدو للرابط «لم يُقيَّم بعد» —
        # فيصفه فاتحُ الرابط تعديلاً يمحو نجماتِ صاحب الشركة **ويحرق** حقَّ التعديل.
        rating = _rating_for_token(token_obj)
        payload = {
            "company_name": token_obj.tenant.CompanyName,
            "employee_name": emp.user.get_full_name() or emp.user.username if emp and emp.user else "",
            "service_date": token_obj.service_date.isoformat(),
            "stars": rating.stars if rating else None,
            "note": rating.note if rating else "",
            "already_rated": bool(rating),
            "can_rate": not bool(rating),
            "can_edit": bool(rating and not rating.edited_once),
        }
        return Response(payload, status=status.HTTP_200_OK)

    def post(self, request, token):
        try:
            token_obj = resolve_daily_rating_token(token)
        except RatingTokenNotFound:
            return Response(
                {"detail": "الرابط غير صالح أو غير موجود."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except RatingTokenGone:
            return Response(
                {"detail": "انتهت صلاحية هذا الرابط."},
                status=status.HTTP_410_GONE,
            )

        serializer = PublicRatingSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stars = serializer.validated_data["stars"]
        note = serializer.validated_data.get("note", "")

        try:
            rating = submit_daily_rating(
                tenant=token_obj.tenant,
                employee=token_obj.employee,
                service_date=token_obj.service_date,
                stars=stars,
                note=note,
                source=DailyRating.Source.TOKEN,
                token_obj=token_obj,
            )
        except DailyRatingError as exc:
            return _service_error(exc)

        emp = token_obj.employee
        payload = {
            "company_name": token_obj.tenant.CompanyName,
            "employee_name": emp.user.get_full_name() or emp.user.username if emp and emp.user else "",
            "service_date": token_obj.service_date.isoformat(),
            "stars": rating.stars,
            "note": rating.note,
            "already_rated": True,
            "can_rate": False,
            "can_edit": not rating.edited_once,
        }
        return Response(payload, status=status.HTTP_200_OK)


class DailyRatingViewSet(viewsets.ModelViewSet):
    """التقييم اليومي لموظفي المنصة داخل التطبيق (م٧).

    - لصاحب الشركة وهو مسجل الدخول، أو موظفي/مديري المنصة.
    - ترفض وسائط الشركات الصريحة بـ 400.
    - تعتمد عزل الشركة والتحقق من العمل الفعلي في اليوم المقيم.
    - التعديل مسموح مرة واحدة فقط.

    **التقييمُ شهادةُ الزبون لا سجلٌّ داخليّ**: موظّفُ المنصّة يقرأ تقييماتِه ولا
    يكتبها، ولا يحذفها أحد — فمقياسٌ يملك المُقاسُ محوَه ليس مقياساً.
    """

    serializer_class = DailyRatingSerializer
    permission_classes = [IsAuthenticated]
    queryset = DailyRating.objects.select_related("tenant", "employee__user", "rated_by").all().order_by("-service_date")

    def _resolve_tenant(self, request):
        _reject_cross_tenant_from_request(request)
        if IsPlatformOperationsManager().has_permission(request, self):
            return get_tenant(request)
        return _resolve_caller_tenant(request)

    def _is_rated_employee(self, request):
        """هل المستخدمُ موظَّفَ منصّةٍ يقرأ تقييماتِ نفسِه؟ فحينها لا يكتب ولا يحذف."""
        return (
            not IsPlatformOperationsManager().has_permission(request, self)
            and IsPlatformOperationsStaff().has_permission(request, self)
            and hasattr(request.user, "platform_employee")
        )

    def destroy(self, request, *args, **kwargs):
        """التقييمُ لا يُحذَف — لا من المنصّة ولا من الشركة."""
        return Response(
            {"detail": "لا يجوز حذف تقييم يومي.", "code": "rating_delete_forbidden"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_queryset(self):
        _reject_cross_tenant_from_request(self.request)

        user = self.request.user
        qs = super().get_queryset()

        if IsPlatformOperationsManager().has_permission(self.request, self):
            employee_id = self.request.query_params.get("employee") or self.request.query_params.get("employee_id")
            if employee_id:
                qs = qs.filter(employee_id=employee_id)
            return qs

        if IsPlatformOperationsStaff().has_permission(self.request, self) and hasattr(user, "platform_employee"):
            return qs.filter(employee=user.platform_employee)

        tenant = self._resolve_tenant(self.request)
        if tenant:
            return qs.filter(tenant=tenant)
        return qs.none()

    def create(self, request, *args, **kwargs):
        tenant = self._resolve_tenant(request)
        if not tenant:
            return Response({"detail": "يجب تحديد شركة صالحة لإرسال التقييم."}, status=status.HTTP_400_BAD_REQUEST)
        _require_tenant_manager(request, tenant)

        serializer = DailyRatingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            emp = PlatformEmployee.objects.get(pk=data["employee_id"])
        except PlatformEmployee.DoesNotExist:
            return Response({"detail": "موظف المنصة غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        try:
            rating = submit_daily_rating(
                tenant=tenant,
                employee=emp,
                service_date=data["service_date"],
                stars=data["stars"],
                note=data.get("note", ""),
                source=DailyRating.Source.IN_APP,
                user=request.user,
            )
        except DailyRatingError as exc:
            return _service_error(exc)

        return Response(DailyRatingSerializer(rating).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        if self._is_rated_employee(request):
            raise PermissionDenied("موظف المنصة لا يعدّل التقييم الصادر بحقه.")
        instance = self.get_object()
        # الشهادةُ شهادةُ صاحب الشركة: عضوٌ عاديٌّ لا يملك إنشاءها فلا يملك إعادةَ كتابتها.
        if not IsPlatformOperationsManager().has_permission(request, self):
            _require_tenant_manager(request, instance.tenant)
        serializer = DailyRatingUpdateSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            rating = update_daily_rating(
                rating_id=instance.pk,
                stars=data.get("stars", instance.stars),
                note=data.get("note", instance.note),
            )
        except DailyRatingError as exc:
            return _service_error(exc)

        return Response(DailyRatingSerializer(rating).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="generate-link")
    def generate_link(self, request):
        tenant = self._resolve_tenant(request)
        if not tenant:
            return Response({"detail": "يجب تحديد شركة صالحة."}, status=status.HTTP_400_BAD_REQUEST)
        # الرابطُ يفتح سطحاً **بلا مصادقة** يكشف اسمَ الشركة واسمَ الموظف — فسكّه
        # لصاحب الشركة وحدَه، لا لكلّ من يملك عضويّةً فيها.
        _require_tenant_manager(request, tenant)

        serializer = GenerateRatingLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            emp = PlatformEmployee.objects.get(pk=data["employee_id"])
        except PlatformEmployee.DoesNotExist:
            return Response({"detail": "موظف المنصة غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        try:
            token_obj, raw_token = generate_daily_rating_token(
                tenant=tenant,
                employee=emp,
                service_date=data["service_date"],
            )
        except DailyRatingError as exc:
            return _service_error(exc)

        return Response({
            "token": raw_token,
            # بناءُ الرابط في الخدمة لا هنا: النقطةُ تُسلّم ما تحسبه الخدمة (عقدُ الوحدة
            # في رأس `services.py`)، وأساسُه إعدادٌ صريحٌ لا ترويسةُ `Host`.
            "public_url": rating_public_url(raw_token),
            "api_path": reverse("tenant-public-rating", kwargs={"token": raw_token}),
            "expires_at": token_obj.expires_at.isoformat(),
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        employee_id = request.query_params.get("employee") or request.query_params.get("employee_id")
        if not employee_id:
            return Response({"detail": "معرف الموظف مطلوب."}, status=status.HTTP_400_BAD_REQUEST)

        # `get(pk="abc")` يرفع `ValueError` لا `DoesNotExist` — أي 500 على وسيطٍ من المستخدم.
        try:
            employee_id = int(employee_id)
        except (TypeError, ValueError):
            return Response({"detail": "معرف الموظف يجب أن يكون رقماً."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            emp = PlatformEmployee.objects.get(pk=employee_id)
        except PlatformEmployee.DoesNotExist:
            return Response({"detail": "موظف المنصة غير موجود."}, status=status.HTTP_404_NOT_FOUND)

        tenant = None
        if not IsPlatformOperationsManager().has_permission(request, self):
            tenant = self._resolve_tenant(request)

        summary_data = calculate_employee_ratings_summary(
            employee=emp,
            tenant=tenant,
        )
        return Response(summary_data, status=status.HTTP_200_OK)


class TenantAgentBooksViewSet(viewsets.ViewSet):
    """تبويب «من يمسك دفاتري» لصاحب الشركة (م٧).

    - المصدر الوحيد لمعرفة الوكيل هو صف Engagement النشط (لا جدول العضويات).
    - يقال للزبون صراحةً إن الوكيل يعمل بصلاحية مدير.
    - نشاط الوكيل داخل هذه الشركة وحدها، مع استبعاد view و login.
    - التغيير المالي يظهر «من ماذا إلى ماذا».
    - تظهر قائمة AgentGrantedMembership.
    - لصاحب الشركة تعليق وصول الوكيل بنفسه عبر نقطة suspend.
    - درجتا الصحة منفصلتان (صحة الخدمة، وتعاون الزبون) دون خلط وبأعلى 3 أسباب.
    """

    permission_classes = [IsAuthenticated]

    def _resolve_tenant(self, request):
        _reject_cross_tenant_from_request(request)
        return _resolve_caller_tenant(request)

    def list(self, request):
        tenant = self._resolve_tenant(request)
        # التبويبُ يعرض نشاطَ الوكيل الماليَّ «من ماذا إلى ماذا» ودرجتَي الصحّة —
        # قصصُ المواصفة ٤٩–٥٥ كلُّها «كصاحب شركة»، فلا يفتحه `viewer`.
        _require_tenant_manager(request, tenant)
        books_data = get_my_books_tab_data(tenant)
        health_scores = calculate_two_health_scores(tenant)

        payload = {
            "tenant_id": tenant.pk,
            "tenant_name": tenant.CompanyName,
            "agents": books_data["agents"],
            "service_date": books_data["service_date"],
            "granted_memberships": books_data["granted_memberships"],
            "activity_log": books_data["activity_log"],
            "total_activities_count": books_data["total_activities_count"],
            "activity_page_cap": books_data["activity_page_cap"],
            "health_scores": health_scores,
            "can_suspend": books_data["can_suspend"],
        }
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="quota")
    def quota(self, request):
        """استهلاكُ الشركة من باقتها — القصّة ٦٢، «حتى لا تفاجئني الفاتورة».

        الأرقامُ من دالّة الفوترة نفسِها لا من حسبةٍ ثانية، و`viewer` لا يفتحها:
        قيمةُ الفاتورة شأنُ صاحب الشركة.
        """
        tenant = self._resolve_tenant(request)
        _require_tenant_manager(request, tenant)
        return Response(get_tenant_quota_usage(tenant), status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="suspend")
    def suspend(self, request):
        tenant = self._resolve_tenant(request)
        _require_tenant_manager(request, tenant)
        reason = str(request.data.get("reason", "تعليق وصول الوكيل بطلب من صاحب الشركة")).strip()
        engagement_id = request.data.get("engagement_id")

        if engagement_id is not None:
            try:
                engagement_id_int = int(engagement_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "معرف الارتباط غير صالح.", "code": "invalid_engagement_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            engagement = Engagement.objects.filter(pk=engagement_id_int, tenant=tenant).first()
            if not engagement:
                return Response(
                    {"detail": "الارتباط غير موجود لهذه الشركة.", "code": "engagement_not_found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if engagement.status != Engagement.Status.ACTIVE:
                return Response(
                    {"detail": "الارتباط ليس نشطاً ليتم تعليقه.", "code": "engagement_not_active"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            suspend_engagement(engagement=engagement, reason=reason)
            return Response(
                {
                    "detail": "تم تعليق وصول الوكيل للشركة بنجاح.",
                    "suspended_count": 1,
                    "engagement_id": engagement.pk,
                },
                status=status.HTTP_200_OK,
            )

        active_engagements = list(
            Engagement.objects.filter(tenant=tenant, status=Engagement.Status.ACTIVE).order_by("pk")
        )
        if not active_engagements:
            return Response(
                {"detail": "لا يوجد ارتباط وكيل نشط لهذه الشركة ليتم تعليقه."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(active_engagements) > 1:
            return Response(
                {
                    "detail": "يوجد أكثر من وكيل نشط لهذه الشركة، يجب تحديد معرف الارتباط (engagement_id) لتعليقه.",
                    "code": "engagement_id_required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        single_engagement = active_engagements[0]
        suspend_engagement(engagement=single_engagement, reason=reason)
        return Response(
            {
                "detail": "تم تعليق وصول الوكيل للشركة بنجاح.",
                "suspended_count": 1,
                "engagement_id": single_engagement.pk,
            },
            status=status.HTTP_200_OK,
        )


class CompanyHealthView(APIView):
    """عرض درجتي الصحة لشركة معينة في مسار السوبر أدمن (م٧ - قصص ٢٣-٢٤).

    - صلاحيتها كصلاحية WorkOrderViewSet: موظف المنصة يقرأ شركات ارتباطاته النشطة وحدها،
      والمدير يقرأ جميع الشركات.
    - شركة خارج نطاق الموظف أو غير موجودة ⇒ 404 (دون تلميح لوجودها).
    - مستخدم مصادق عادي ليس موظفاً ولا مديراً ⇒ 403 (حارس الجذر).
    - تُطلب عند الفتح لتجنب N+1 في اللوحة.
    """

    permission_classes = [IsPlatformOperationsStaff | IsPlatformOperationsManager]

    def get(self, request, tenant_id: int):
        user = request.user
        is_manager = IsPlatformOperationsManager().has_permission(request, self)

        if not is_manager:
            has_active_engagement = Engagement.objects.filter(
                employee__user=user,
                tenant_id=tenant_id,
                status=Engagement.Status.ACTIVE,
            ).exists()
            if not has_active_engagement:
                raise Http404("الشركة غير موجودة أو خارج نطاق العمليات.")

        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            raise Http404("الشركة غير موجودة.")

        # `health_scores` مفتاحاً واحداً بنفس شكله في `/api/my-agent/` — لا نسخةً ثانيةً
        # مسطّحةً بجانبه: حمولةٌ تحمل الرقمَ مرّتين تدعو قارئاً لأن يقرأ النسخةَ الأخرى.
        return Response({
            "tenant_id": tenant.pk,
            "company_name": tenant.CompanyName,
            "health_scores": calculate_two_health_scores(tenant),
        }, status=status.HTTP_200_OK)


class PlatformRecruiterViewSet(viewsets.ModelViewSet):
    """إدارة مسؤولي التوظيف المنصي — محصورة بمدير العمليات المنصية / السوبر أدمن.

    الإسنادُ والإلغاءُ يمرّان بطبقة الخدمات لا بـCRUD عامّ: `create_platform_recruiter`
    تُعيد تفعيلَ صفٍّ مُلغىً بدل أن تسقط بتصادم الفرادة، و`revoke_platform_recruiter`
    **تُعطّل ولا تحذف** فيبقى أثرُ من أُسند إليه الدور.
    """

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = PlatformRecruiterSerializer
    queryset = PlatformRecruiter.objects.select_related("user").order_by("-created_at")
    #: لا `PUT`/`PATCH`: تفعيلُ الدور بكتابة `is_active` مباشرةً يلتفّ على الخدمة.
    #: الإسنادُ `POST` والإلغاءُ `DELETE`، وإعادةُ الإسناد `POST` ثانيةً تُعيد التفعيل.
    http_method_names = ["get", "post", "delete", "head", "options"]

    def perform_create(self, serializer):
        # `identifier` حُلَّ إلى مستخدمٍ في `validate_identifier`.
        user = serializer.validated_data["identifier"]
        serializer.instance = create_platform_recruiter(user)

    def perform_destroy(self, instance):
        revoke_platform_recruiter(instance.user)


class JobPostingViewSet(viewsets.ModelViewSet):
    """إدارة إعلانات الوظائف المنصية — متاحة لمسؤولي التوظيف ومديري المنصة."""

    permission_classes = [IsPlatformRecruiter]
    serializer_class = JobPostingSerializer

    def get_queryset(self):
        qs = JobPosting.objects.prefetch_related("applicants").order_by("-created_at")
        is_open = self.request.query_params.get("is_open")
        if is_open is not None:
            if str(is_open).lower() in ("true", "1"):
                qs = qs.filter(is_open=True)
            elif str(is_open).lower() in ("false", "0"):
                qs = qs.filter(is_open=False)
        return qs

    def perform_create(self, serializer):
        # الكتابةُ عبر الخدمة لا عبر المُسلسِل: توليدُ المفتاح ونصُّ الإلزام
        # يسكنان `create_job_posting` وحدَها، فلا تتباعد نسختان.
        user = self.request.user if getattr(self.request, "user", None) and self.request.user.is_authenticated else None
        data = serializer.validated_data
        serializer.instance = create_job_posting(
            title=data.get("title", ""),
            description=data.get("description", ""),
            created_by=user,
            specialty=data.get("specialty", ""),
            requirements=data.get("requirements", ""),
            location=data.get("location", ""),
            employment_type=data.get("employment_type", ""),
            salary_range=data.get("salary_range", ""),
            expires_at=data.get("expires_at"),
        )

    def perform_destroy(self, instance):
        if instance.applicants.exists():
            raise ValidationError("لا يمكن حذف إعلان وظيفة له متقدمون. أغلق الإعلانَ بدل حذفه.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        job = self.get_object()
        job = close_job_posting(job=job)
        return Response(self.get_serializer(job).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        job = self.get_object()
        job = reopen_job_posting(job=job)
        return Response(self.get_serializer(job).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="regenerate-link")
    def regenerate_link(self, request, pk=None):
        job = self.get_object()
        job = regenerate_job_posting_token(job=job)
        return Response(self.get_serializer(job).data, status=status.HTTP_200_OK)


class JobApplicantViewSet(viewsets.ReadOnlyModelViewSet):
    """متابعةُ المتقدّمين على الوظائف المنصّية — **قراءةٌ وأفعالٌ لا CRUD**.

    - متاحة لمسؤولي التوظيف ومديري المنصة (`IsPlatformRecruiter`).
    - **لا إنشاءَ ولا حذفَ من هنا**: المتقدّمُ يولد من الصفحة العامّة وحدَها
      («التقديمُ من صفحةٍ عامّةٍ بلا حساب»)، وقد كان `POST` هنا يسقط بـ500 أصلاً
      لأنّ `job` قراءةٌ فقط فيُنشأ الصفُّ بلا وظيفة.
    - **ولا تحريرَ مباشراً**: الحالةُ تتحرّك بـ`transition-status` والتقييمُ بـ`rate`،
      فيمرّان بجدول الانتقالات وبحارس «حالةُ المقبول تُبلَغ بقبول الدعوة».
    - رابط السيرة الذاتية لا يُعاد في البيانات؛ الوصول له عبر `cv/` الذي يمرّر
      البايتاتِ ولا يسلّم رابطَ التخزين.
    """

    permission_classes = [IsPlatformRecruiter]
    serializer_class = JobApplicantSerializer

    def get_queryset(self):
        qs = JobApplicant.objects.select_related("job", "hired_employee__user").order_by("-created_at")
        job_id = self.request.query_params.get("job") or self.request.query_params.get("job_id")
        if job_id:
            qs = qs.filter(job_id=job_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=True, methods=["post"], url_path="transition-status")
    def transition_status(self, request, pk=None):
        applicant = self.get_object()
        target_status = request.data.get("status")
        if not target_status:
            return Response({"status": "الحالة المستهدفة مطلوبة."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            applicant = transition_applicant_status(
                applicant=applicant,
                target_status=target_status,
                actor=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail if hasattr(exc, "detail") else str(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(applicant).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        applicant = self.get_object()
        rating = request.data.get("rating")
        notes = request.data.get("notes")
        try:
            applicant = rate_applicant(applicant=applicant, rating=rating, notes=notes)
        except ValidationError as exc:
            return Response(exc.detail if hasattr(exc, "detail") else str(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(applicant).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def invite(self, request, pk=None):
        applicant = self.get_object()
        raw_hours = request.data.get("expires_in_hours", 72)
        if raw_hours is None or raw_hours == "":
            raw_hours = 72
        try:
            expires_in_hours = int(raw_hours)
        except (ValueError, TypeError):
            return Response(
                {"expires_in_hours": "مدة الصلاحية يجب أن تكون عدداً صحيحاً بالساعات بين 1 و168."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not 1 <= expires_in_hours <= 168:
            return Response(
                {"expires_in_hours": "مدة الصلاحية يجب أن تكون بين 1 و168 ساعة (أسبوع كحد أقصى)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            invitation, raw_token = create_applicant_invitation(
                applicant=applicant,
                created_by=request.user,
                expires_in_hours=expires_in_hours,
            )
        except ValidationError as exc:
            return Response(
                exc.detail if hasattr(exc, "detail") else str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": "تم إصدار رابط الدعوة بنجاح.",
                "invitation_id": invitation.pk,
                "token": raw_token,
                "invite_url": invitation_public_url(raw_token),
                "expires_at": invitation.expires_at.isoformat(),
                "applicant_id": applicant.pk,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def cv(self, request, pk=None):
        """السيرةُ خلف صلاحية، **ورابطُ التخزين لا يغادر الخادم**.

        **بايتاتٌ لا إعادةُ توجيه**: ترويسةُ `Location` **هي** رابطُ التخزين
        حرفيّاً، فالردُّ يحمل ما تقول المواصفةُ إنّه «لا يُسلَّم بأيّ حال»، ويبقى
        في سجلّ المتصفّح صالحاً للنسخ بعد انتهاء الجلسة — والرابطُ عند المزوّد
        **هو** الصلاحية، فتسليمُه تسليمٌ دائم. هذا العيبُ وقع في `employee_ops`
        وأُصلح هناك بالنمط نفسِه، فلا يُعاد هنا.
        """
        applicant = self.get_object()
        if not applicant.cv_url:
            raise Http404("لا توجد سيرة ذاتية لهذا المتقدم.")

        try:
            upstream = requests.get(applicant.cv_url, stream=True, timeout=20)
            upstream.raise_for_status()
        except requests.RequestException:
            raise APIException("تعذّر جلب السيرة الذاتية من التخزين.")

        safe_name = (applicant.cv_name or "cv").replace('"', "").replace("\\", "")
        response = FileResponse(
            upstream.raw,
            as_attachment=False,
            filename=safe_name,
            content_type=upstream.headers.get("Content-Type")
            or guess_cv_content_type(applicant.cv_url),
        )
        return response


class PlatformStaffCapabilitiesView(APIView):
    """قدراتُ المستخدم الحاليّ على المنصّة — لتعرف الواجهةُ أيَّ بابٍ تُظهر له (م٨-ب).

    **خارج `/api/platform/` عمداً**: ذلك الجذرُ يردّ 403 لكلّ من ليس سوبر أدمن،
    وحارسُه يعدّ مساراتِه كلَّها، وهذا سؤالٌ يطرحه **كلُّ** مستخدمٍ عن نفسه. وبدونه
    لا تعرف الواجهةُ أنّ مسؤولَ التوظيف — وليس سوبر أدمن — له شاشةٌ يدخلها، فيبقى
    الدورُ الذي بُني له الاستثناءُ الوحيدُ بلا باب: حمولةُ المصادقة تسكن `hr` التي
    يمنعها حارسُ العزل من استيراد هذه الوحدة.

    يُجيب عن المستخدم نفسِه وحدَه ولا يقبل معرّفاً من الطلب.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "is_platform_admin": bool(IsPlatformAdmin().has_permission(request, self)),
                "is_platform_recruiter": bool(is_platform_recruiter(user)),
                "is_platform_employee": bool(is_platform_employee(user)),
            },
            status=status.HTTP_200_OK,
        )
