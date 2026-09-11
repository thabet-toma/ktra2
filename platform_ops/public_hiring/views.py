"""نقاط بوّابة التوظيف العامة (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

كل كود AllowAny في مكان واحد داخل هذه الحزمة.
- authentication_classes = [] (تجنباً لـ DeviceTokenAuthentication الافتراضي)
- permission_classes = [AllowAny]
- throttle_classes = [ClientIpScopedThrottle] (بهوية من REMOTE_ADDR حصراً)
- فحص حجم وجسم الطلب بالبايتات الحقيقية
- فحص نوع السيرة الذاتية بالبايتات الحقيقية
- لا وجود لحساب المستخدم User قبل قبول الدعوة
- رابط الدعوة المستهلك أو المنتهي يرد 410، وغير الموجود يرد 404
"""
import logging

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.media_views import MediaUploadError, upload_media_file
from platform_ops.services import (
    accept_applicant_invitation,
    resolve_public_invitation,
    resolve_public_job,
    submit_application,
)
from platform_ops.throttles import ClientIpScopedThrottle

from .cv_validation import (
    ApplicationTooLarge,
    InvitationGone,
    JobGone,
    MAGIC_HEAD_BYTES,
    MAX_APPLICATION_BYTES,
    validate_cv_upload,
)
from .serializers import (
    AcceptInvitationInputSerializer,
    JobApplicationInputSerializer,
    JobApplicationSuccessSerializer,
    PublicInvitationDetailSerializer,
    PublicJobPostingSerializer,
)

logger = logging.getLogger(__name__)


class PublicJobDetailView(APIView):
    """عرض إعلان وظيفة بالرابط العام."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_public_hiring"

    def get(self, request, token):
        try:
            job = resolve_public_job(token)
        except JobGone:
            return Response(
                {"detail": "انتهت فترة التقديم على هذه الوظيفة أو تم إغلاقها."},
                status=status.HTTP_410_GONE,
            )
        serializer = PublicJobPostingSerializer(job)
        return Response(serializer.data)


class PublicJobApplyView(APIView):
    """تقديم طلب على وظيفة بالرابط العام ورفع السيرة الذاتية بأمان."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_apply"
    #: طلبٌ بلا سيرةٍ حمولةٌ JSON عاديّة، وطلبٌ بسيرةٍ متعدّدُ الأجزاء — والاثنان
    #: مقبولان، فلا يُردّ التقديمُ الأبسطُ بـ415.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, token):
        # 1. فحص سقف جسم الطلب من ترويسة CONTENT_LENGTH قبل القراءة الموسعة
        content_length = request.META.get("CONTENT_LENGTH")
        if content_length:
            try:
                if int(content_length) > MAX_APPLICATION_BYTES:
                    return Response(
                        {"detail": "حجم الطلب يتجاوز الحد المسموح به."},
                        status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )
            except (ValueError, TypeError):
                pass

        try:
            job = resolve_public_job(token)
        except JobGone:
            return Response(
                {"detail": "انتهت فترة التقديم على هذه الوظيفة أو تم إغلاقها."},
                status=status.HTTP_410_GONE,
            )

        serializer = JobApplicationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        upload = data.pop("cv_file", None)
        cv_url, cv_name = "", ""

        if upload is not None:
            payload = upload.read()
            upload.seek(0)

            # الفحصُ كلُّه في نقطةٍ واحدة، **والحجمُ من البايتات** لا من ترويسةٍ
            # يكتبها الرافع. وتجاوزُ السقف يردّ 413 لا 400: هو حجمُ حمولةٍ لا
            # خطأُ حقل، والقصّة ٧٥ تطلب أن «أُخبَر بوضوحٍ إن تجاوزه».
            try:
                validate_cv_upload(
                    size=getattr(upload, "size", 0) or len(payload),
                    filename=getattr(upload, "name", "") or "",
                    content_type=getattr(upload, "content_type", "") or "",
                    head=payload[:MAGIC_HEAD_BYTES],
                    payload=payload,
                )
            except ApplicationTooLarge as exc:
                return Response(
                    {"cv": str(exc)},
                    status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )

            try:
                cv_url = upload_media_file(
                    upload, folder="platform_careers_cv", tenant=None
                )
            except MediaUploadError as exc:
                logger.warning("public hiring cv upload failed: %s", exc)
                return Response(
                    {"cv": "تعذّر رفع السيرة الذاتية. حاول مرة أخرى."},
                    status=exc.status_code,
                )
            cv_name = (getattr(upload, "name", "") or "")[:255]

        try:
            applicant = submit_application(
                job=job,
                name=data["name"],
                phone=data["phone"],
                email=data.get("email", ""),
                about=data.get("about", ""),
                cv_url=cv_url,
                cv_name=cv_name,
            )
        except JobGone:
            return Response(
                {"detail": "انتهت فترة التقديم على هذه الوظيفة."},
                status=status.HTTP_410_GONE,
            )

        # الرد يحمل رقم المرجع واسم الملف كما أرسله المتقدم — **لا رابط سيرة**
        # ولا أيّ مسارِ تخزينٍ ولا بيانات داخلية.
        payload = JobApplicationSuccessSerializer(
            {
                "reference_code": applicant.reference_code,
                "status": applicant.status,
                "job_title": job.title,
                "cv_name": cv_name,
            }
        )
        return Response(payload.data, status=status.HTTP_201_CREATED)


class PublicInvitationDetailView(APIView):
    """عرض صفحة الدعوة برابطها العام للمرشح."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_invitation"

    def get(self, request, token):
        try:
            inv = resolve_public_invitation(token)
        except InvitationGone:
            return Response(
                {"detail": "انتهت صلاحية رابط الدعوة أو تم استخدامه مسبقاً."},
                status=status.HTTP_410_GONE,
            )

        payload = {
            "job_title": inv.applicant.job.title,
            "applicant_name": inv.applicant.name,
            "email": inv.applicant.email,
            "expires_at": inv.expires_at,
        }
        serializer = PublicInvitationDetailSerializer(payload)
        return Response(serializer.data)


class PublicInvitationAcceptView(APIView):
    """قبول الدعوة وتعيين كلمة المرور وإنشاء حساب المستخدم وموظف المنصة."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_invitation"

    def post(self, request, token):
        serializer = AcceptInvitationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data["password"]
        username = serializer.validated_data.get("username", "")

        try:
            user, emp, applicant = accept_applicant_invitation(
                token=token,
                password=password,
                username=username,
            )
        except InvitationGone:
            return Response(
                {"detail": "انتهت صلاحية رابط الدعوة أو تم استخدامه مسبقاً."},
                status=status.HTTP_410_GONE,
            )

        return Response(
            {
                "detail": "تم قبول الدعوة وإنشاء الحساب بنجاح.",
                "username": user.username,
                "applicant_status": applicant.status,
            },
            status=status.HTTP_200_OK,
        )
