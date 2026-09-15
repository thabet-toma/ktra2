"""نقاط بوّابة التوظيف العامة (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

كل كود AllowAny في مكان واحد داخل هذه الحزمة.
- authentication_classes = [] (تجنباً لـ DeviceTokenAuthentication الافتراضي)
- permission_classes = [AllowAny]
- throttle_classes = [ClientIpScopedThrottle] (بهوية من REMOTE_ADDR حصراً)
- فحص حجم وجسم الطلب بالبايتات الحقيقية
- فحص نوع السيرة الذاتية بالبايتات الحقيقية
- لا وجود لحساب المستخدم User قبل قبول الدعوة
- رابط الدعوة المستهلك أو المنتهي يرد 410، وغير الموجود يرد 404
- وقبولُ الدعوة **يُصدر جلسةَ دخولٍ فوراً** (`hr.auth_api.issue_login_session`):
  الرمزُ المهشَّرُ أُثبت واستُهلك، فبقاءُ الحساب بلا جلسةٍ بابٌ مسدودٌ لا احتياط
"""
import json
import logging

from django.conf import settings
from django.utils.safestring import mark_safe
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from core.media_views import MediaUploadError, upload_media_file
from hr.auth_api import issue_login_session
from platform_ops.services import (
    ApplicantReplyClosed,
    TRACKING_DENIED_DETAIL,
    TrackingDenied,
    TrackingSessionExpired,
    accept_applicant_invitation,
    applicant_can_reply,
    applicant_public_status_label,
    applicant_public_updates,
    applicant_upcoming_meetings,
    issue_tracking_session,
    job_apply_url,
    job_public_url,
    record_applicant_reply,
    resolve_applicant_tracking,
    resolve_public_invitation,
    resolve_public_job,
    resolve_tracking_session,
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
    PublicApplicantMeetingSerializer,
    PublicApplicantStateSerializer,
    PublicApplicantUpdateSerializer,
    PublicInvitationDetailSerializer,
    PublicJobPostingSerializer,
    TrackingLookupInputSerializer,
    TrackingReplyInputSerializer,
    TrackingSessionInputSerializer,
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


# ==============================================================================
# ‏#215: متابعةُ المتقدّم — بابٌ عامٌّ بعاملين، على نفس صفحة التقديم
# ==============================================================================


def _tracking_payload(applicant, *, session: str) -> dict:
    """حمولةُ لوحة المتابعة. مصدرٌ واحدٌ للأبواب الثلاثة فلا تتباعد ثلاثُ نسخ."""
    return {
        "session": session,
        "job": PublicJobPostingSerializer(applicant.job).data,
        "applicant": PublicApplicantStateSerializer(
            {
                "reference_code": applicant.reference_code,
                "status": applicant.status,
                "status_display": applicant_public_status_label(applicant.status),
                "can_reply": applicant_can_reply(applicant),
            }
        ).data,
        "updates": PublicApplicantUpdateSerializer(
            applicant_public_updates(applicant), many=True
        ).data,
        "meetings": PublicApplicantMeetingSerializer(
            applicant_upcoming_meetings(applicant), many=True
        ).data,
    }


class PublicApplicantTrackView(APIView):
    """فتحُ متابعةِ طلبٍ برقم التتبّع ورقم الهاتف معاً.

    **`POST` لا `GET` عمداً**: الهاتفُ بياناتٌ شخصيّةٌ، وسلسلةُ الاستعلام تُكتب
    في سجلّات الخادم وتُرسَل في `Referer` إلى كلّ رابطٍ يُنقَر من الصفحة.

    **وخانقٌ أضيقُ من خانق التقديم**: هذا سطحُ التخمين لا سطحُ الاستخدام.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_track"

    def post(self, request, token):
        serializer = TrackingLookupInputSerializer(data=request.data)
        if not serializer.is_valid():
            # حتى خطأُ الشكل يخرج بالنصّ الموحَّد: «الحقلُ مطلوب» تقول للمجرِّب
            # أيَّ الحقلين نسي، وهي معلومةٌ لا يحتاجها إلا هو.
            return Response(
                {"detail": TRACKING_DENIED_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            applicant = resolve_applicant_tracking(
                job_token=token,
                reference_code=serializer.validated_data["reference_code"],
                phone=serializer.validated_data["phone"],
            )
        except TrackingDenied:
            return Response(
                {"detail": TRACKING_DENIED_DETAIL},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session = issue_tracking_session(applicant)
        return Response(_tracking_payload(applicant, session=session))


class PublicApplicantTrackRefreshView(APIView):
    """تحديثُ اللوحة بجلسةٍ قائمة — بلا إعادة إرسال الهاتف في كلّ نداء."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_track_session"

    def post(self, request):
        serializer = TrackingSessionInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": "انتهت الجلسة. أدخل رقمك مرّةً أخرى."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        raw_session = serializer.validated_data["session"]
        try:
            applicant = resolve_tracking_session(raw_session)
        except TrackingSessionExpired as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(_tracking_payload(applicant, session=raw_session))


class PublicApplicantReplyView(APIView):
    """ردُّ المتقدّم على فريق التوظيف — الاتجاهُ الثاني للقناة."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_track_session"

    def post(self, request):
        serializer = TrackingReplyInputSerializer(data=request.data)
        if not serializer.is_valid():
            if "session" in serializer.errors:
                return Response(
                    {"detail": "انتهت الجلسة. أدخل رقمك مرّةً أخرى."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            applicant = resolve_tracking_session(serializer.validated_data["session"])
        except TrackingSessionExpired as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            update = record_applicant_reply(
                applicant=applicant, body=serializer.validated_data["body"]
            )
        except ApplicantReplyClosed as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return Response(
                exc.detail if hasattr(exc, "detail") else str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            PublicApplicantUpdateSerializer(update).data,
            status=status.HTTP_201_CREATED,
        )


#: طولُ وصفِ المعاينة. فيسبوك يقتطع ما بعد ~٣٠٠ محرف، وواتساب أقصرُ منه —
#: فالقطعُ هنا عند حدٍّ نعرفه أفضلُ من قطعٍ في منتصف كلمةٍ لا نتحكّم به.
SOCIAL_DESCRIPTION_LIMIT = 200

#: تسمياتُ `schema.org` لأنواع الدوام. جدولٌ صريحٌ لا `.upper()`: «عقد» عندنا
#: `contract` واسمُها هناك `CONTRACTOR` — والاشتقاقُ الآليّ يُخرج قيمةً يرفضها
#: مُدقّقُ جوجل بصمتٍ فلا يظهر الإعلانُ في «وظائف جوجل» ولا يُقال لأحدٍ لماذا.
SCHEMA_EMPLOYMENT_TYPES = {
    "full_time": "FULL_TIME",
    "part_time": "PART_TIME",
    "contract": "CONTRACTOR",
    "temporary": "TEMPORARY",
}


def _one_line(text: str) -> str:
    """نصٌّ حرٌّ إلى سطرٍ واحدٍ صالحٍ لوسمِ `content`."""
    return " ".join((text or "").split())


def _social_description(job) -> str:
    """وصفُ المعاينة: سطرُ الحقائق أوّلاً ثمّ أوّلُ الوصف.

    الترتيبُ مقصود — المكانُ ونوعُ الدوامُ والراتب هي ما يقرّر به القارئُ في
    فيسبوك أن يضغط، وأوّلُ سطرٍ من الوصف كثيراً ما يكون تحيّةً لا معلومة.
    """
    facts = [
        _one_line(value)
        for value in (job.location, job.get_employment_type_display(), job.salary_range)
        if value
    ]
    body = _one_line(job.description)
    text = " · ".join(facts)
    text = f"{text} — {body}" if text and body else (text or body)
    if len(text) > SOCIAL_DESCRIPTION_LIMIT:
        text = text[:SOCIAL_DESCRIPTION_LIMIT].rstrip() + "…"
    return text


def _job_ld(job, share_url: str) -> str:
    """`JobPosting` JSON-LD — ما تقرؤه «وظائف جوجل».

    يُبنى في بايثون ويُهرَّب `<` و`>` و`&` بصيغة يونيكود: وصفُ الوظيفة نصٌّ
    يكتبه إنسانٌ في لوحة التحكّم، و`</script>` داخلَه يُنهي الوسمَ ويفتح باب
    حقنٍ في صفحةٍ عامّة. (نفس ما يفعله `django.utils.html.json_script`.)

    ثمّ `mark_safe` **بعد** ذلك التهريب لا بدلاً منه: تهريبُ القالب التلقائيُّ
    يقلب كلَّ `"` إلى `&quot;` فيصير الوسمُ نصّاً ليس JSON — ومُدقّقُ جوجل
    يتجاهل ما لا يُحلَّل **بلا رسالةٍ ولا أثر**، فيبدو الإعلانُ سليماً ولا يظهر
    في «وظائف جوجل» أبداً. أمسكه اختبارُ `json.loads` على نصّ الردّ الخامّ.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": job.title,
        "description": job.description,
        "datePosted": job.created_at.date().isoformat(),
        "url": share_url,
        "hiringOrganization": {
            "@type": "Organization",
            "name": "K.T.R.A",
            "sameAs": str(getattr(settings, "PLATFORM_JOB_PUBLIC_BASE_URL", "")),
        },
        "directApply": True,
    }
    if job.expires_at:
        payload["validThrough"] = job.expires_at.isoformat()
    if job.location:
        payload["jobLocation"] = {
            "@type": "Place",
            "address": {"@type": "PostalAddress", "addressLocality": job.location},
        }
    schema_type = SCHEMA_EMPLOYMENT_TYPES.get(job.employment_type)
    if schema_type:
        payload["employmentType"] = schema_type
    if job.salary_range:
        # نصٌّ حرٌّ («٥٠٠–٨٠٠ دينار») لا `MonetaryAmount`: الأخيرةُ تلزمها عملةٌ
        # ورقمٌ وفترة، ولا عمود لأيٍّ منها في `JobPosting` — واختلاقُها كذب.
        payload["baseSalary"] = job.salary_range
    return mark_safe(
        json.dumps(payload, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


class PublicJobPageView(APIView):
    """`GET /j/<token>` و`GET /api/careers/j/<token>/` — صفحةُ الإعلان (#214-أ).

    **الصفحةُ الوحيدةُ في هذه الحزمة التي تُصيَّر HTML**، ولذات السبب الذي بُنيت
    لأجله صفحةُ `docshare`: زاحفُ فيسبوك وواتساب ولينكدإن لا ينفّذ JavaScript،
    والخادمُ الأمامي يخدم `index.html` لكلّ ما ليس `/api/` — فكان الرابطُ يُلصَق
    فيظهر بعنوان المنصّة العامّ لكلّ وظيفةٍ على حدة.

    وتختلف عن `docshare` في شيءٍ واحدٍ جوهريّ: تلك مستنداتٌ خاصّةٌ تُوسَم
    `noindex`، وهذا إعلانٌ **يُراد أن يُفهرَس** — فلا وسمَ منعٍ هنا، ومعه
    `JobPosting` JSON-LD. والصفحةُ تعمل بلا JavaScript إطلاقاً.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ClientIpScopedThrottle]
    throttle_scope = "platform_ops_public_hiring"
    renderer_classes = [TemplateHTMLRenderer]

    def _notice(self, title, message, status_code):
        return Response(
            {"notice_title": title, "notice_message": message},
            template_name="platform_ops/careers/notice.html",
            status=status_code,
        )

    def get(self, request, token):
        try:
            job = resolve_public_job(token)
        except JobGone:
            return self._notice(
                "انتهى التقديمُ على هذه الوظيفة",
                "أُغلق هذا الإعلان أو انتهت مدّتُه. تابع صفحةَ وظائف المنصّة لإعلانٍ جديد.",
                status.HTTP_410_GONE,
            )
        except NotFound:
            # `resolve_public_job` تُطلقها لرابطٍ لا وظيفةَ خلفه. بلا التقاطها
            # يردّ DRF جسمَ خطأٍ بلا قالبٍ فينكسر التصيير — لا صفحةَ تُقرأ.
            return self._notice(
                "الرابطُ غير صالح",
                "لا توجد وظيفةٌ خلف هذا الرابط. تأكّد من نسخه كاملاً.",
                status.HTTP_404_NOT_FOUND,
            )

        share_url = job_public_url(job.token)
        return Response(
            {
                "job": job,
                "share_url": share_url,
                "apply_url": job_apply_url(job.token),
                "employment_type_display": job.get_employment_type_display(),
                "social_title": f"{job.title} — التقديمُ على الوظيفة ومعرفةُ التفاصيل",
                "social_description": _social_description(job),
                "social_image": str(getattr(settings, "PLATFORM_JOB_SHARE_IMAGE", "")).strip(),
                "job_ld": _job_ld(job, share_url),
            },
            template_name="platform_ops/careers/job.html",
        )


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
            "note": inv.note,
            "contact_phone": inv.contact_phone,
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

        # **الدعوةُ تُدخِله لا تُخبره فقط**: الرمزُ المهشَّر أُثبت واستُهلك للتوّ،
        # فطلبُ كلمةِ سرٍّ ثانيةً بعد سطرين إجراءٌ بلا فائدةٍ أمنيّة وبابٌ مسدودٌ عملياً —
        # المتقدّمُ لا يعرف أين شاشةُ الدخول ولا أنّ اسمَ المستخدم يصلح فيها.
        session = issue_login_session(request, user)
        return Response(
            {
                "detail": "تم قبول الدعوة وإنشاء الحساب بنجاح.",
                "username": user.username,
                "applicant_status": applicant.status,
                "token": session["token"],
                "user": session["user"],
            },
            status=status.HTTP_200_OK,
        )
