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
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import TenantAsset
from tenants.models import Tenant

from .authentication import HasValidIntegrationKey, IntegrationKeyAuthentication
from .services import (
    IntegrationKeyError,
    PlatformOpsError,
    WorkOrderError,
    generate_integration_key,
    receive_channel_work_order,
    revoke_integration_key,
    rotate_integration_key,
)
from .throttles import IntegrationKeyThrottle

from .models import (
    Engagement,
    IntegrationKey,
    PlatformEmployee,
    ServiceSubscription,
    WorkOrder,
)
from .permissions import IsPlatformOperationsManager, IsPlatformOperationsStaff
from .serializers import (
    IntegrationKeySerializer,
    PlatformEmployeeSerializer,
    ServiceSubscriptionSerializer,
    WorkOrderSerializer,
)


class PlatformEmployeeViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ موظفي عمليات المنصة — مدير العمليات فقط."""

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = PlatformEmployeeSerializer
    queryset = PlatformEmployee.objects.select_related("user").all().order_by("-created_at")


class ServiceSubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """عرضُ اشتراكات خدمة المتابعة — مدير العمليات فقط."""

    permission_classes = [IsPlatformOperationsManager]
    serializer_class = ServiceSubscriptionSerializer
    queryset = ServiceSubscription.objects.select_related("tenant").all().order_by("-created_at")


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
        qs = super().get_queryset()
        user = self.request.user

        # مديرُ المنصّة يرى كلَّ شيء — هو صاحبُ المنصّة لا موظّفٌ فيها.
        if IsPlatformOperationsManager().has_permission(self.request, self):
            return qs

        # وموظّفُ المنصّة يرى شركاتِ ارتباطاتِه النشطة وحدَها.
        engaged_tenant_ids = Engagement.objects.filter(
            employee__user=user,
            status=Engagement.Status.ACTIVE,
        ).values_list("tenant_id", flat=True)
        return qs.filter(tenant_id__in=engaged_tenant_ids)


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
