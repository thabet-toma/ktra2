"""بوابةُ التوظيف — الوظيفةُ والرابطُ العامّ والمتقدّم (المواصفة #186، المرحلة ٧).

**هذه أخطرُ نقطةٍ في الوحدة**، وهي وحدها من مراحل المواصفة التي تحمل شروطَ أمانٍ
سابقةً للإطلاق. السببُ مكتوبٌ في تاريخ هذا المستودع لا في نظريّة: الرفعُ المجهول
كان في المنصة و**أُزيل عمداً** لأنّ زائراً واحداً يقفل الـworkers الثلاثة برفعٍ
متزامن — وصفحةُ السيرة تعيد فتحَ الثغرة نفسِها.

فالشروطُ الستّةُ مكتوبةٌ هنا **كوداً لا تعليقاً**:

1. حدُّ حجمٍ خاصٌّ بها (٥MB) لا حدُّ المنصة العامّ — `MAX_CV_BYTES`.
2. أنواعٌ محصورة بفحص **الامتداد ونوع المحتوى الفعليّ معاً** — `validate_cv_upload`.
3. خانقٌ خاصٌّ ضيّقٌ على نقطة التقديم — النطاق `employee_ops_apply` في الإعدادات.
4. `NUM_PROXIES` شرطٌ لازم — يحرسه فحصُ نظامٍ في `employee_ops/checks.py`، فلا
   يبقى بنداً في وثيقةٍ يُنسى: بدونه يتّخذ DRF كاملَ `X-Forwarded-For` هويّةً
   **فالخنقُ بالـIP قابلٌ للتلفيق بترويسةٍ واحدة**، أي أنّ البندين ١ و٣ زينة.
5. الحجر: مُدخَلُ المجهول يُحفظ بحالة «جديد» **ولا يمسّ شيئاً آخر**.
6. قراءةُ السيرة محروسةٌ بالصلاحية، و**رابطُ التخزين المباشر لا يُسلَّم لأحد**.
"""
import io
import mimetypes
import secrets
from urllib.parse import urlparse

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .models import JobApplicant, JobPosting

#: `secrets.token_urlsafe(32)` = ٤٣ محرفاً؛ العمود ٦٤ (نفسُ حساب `docshare`).
TOKEN_BYTES = 32

#: **الشرط ١** — خمسةُ ميجا، لا حدُّ المنصة العامّ (`media_upload`). سيرةٌ فوق
#: خمسة ميجا ليست سيرةً ذاتيّة.
MAX_CV_BYTES = 5 * 1024 * 1024

#: **الشرط ٢** — الامتدادُ ونوعُ المحتوى معاً. الامتدادُ وحده يُعاد تسميتُه في
#: ثانية، ونوعُ المحتوى وحده يُرسله العميلُ كما يشاء: فالاثنان معاً، وكلاهما
#: يجب أن يقع في القائمة **ويصفا الشيءَ نفسه**.
ALLOWED_CV_EXTENSIONS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CV_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
}
#: أيُّ امتدادٍ يقبل أيَّ نوعٍ من هذه — فلا يمرّ `.pdf` بمحتوى `image/png`
#: ولا العكس. الخريطةُ صريحةٌ لأنّ `mimetypes` وحدها متساهلةٌ ومختلفةٌ بين النظم.
_EXTENSION_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
}

#: **«نوعُ المحتوى الفعليّ»** — بايتاتُ الملفّ نفسِه لا ترويسةٌ يكتبها العميل.
#: الترويسةُ المعلَنةُ يضعها الرافعُ كما يشاء، فقبولُها «فحصَ محتوى» تسميةٌ لا
#: فحص. والتوقيعاتُ أدناه أوّلُ بضعةِ بايتاتٍ من كلّ نوعٍ مسموح.
_MAGIC_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    # DOC القديم حاويةُ OLE، وDOCX أرشيفُ ZIP — الاثنان بتوقيعٍ ثابت.
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/msword"),
    (
        b"PK\x03\x04",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
)

#: عددُ البايتات التي تكفي كلَّ التواقيع أعلاه (وWEBP يحتاج ١٢).
MAGIC_HEAD_BYTES = 16

#: توقيعُ ZIP يطابق **كلَّ** أرشيف: `.jar` و`.apk` و`.xlsx` وقنبلةَ ضغط. وتوقيعُ
#: OLE يطابق `.doc` و`.xls` و`.msg` و**`.msi`**. فقبولُهما «فحصَ محتوى» تسميةٌ لا
#: فحص: مثبِّتُ MSI باسم `cv.doc` كان يمرّ من الفحوص الثلاثة، فيستقرّ برنامجٌ
#: خبيثٌ على رابطٍ عامٍّ داخل حساب الشركة، ويُدعى مديرُها للنقر عليه.
#: فالفحصُ يمضي خطوةً أبعد: **بنيةُ الملفّ** لا توقيعُ حاويته.
DOCX_REQUIRED_MEMBER = "word/document.xml"
#: أسماءُ تيّارات OLE مكتوبةٌ UTF-16LE داخل الدليل — وجودُ تيّار Word يميّز
#: مستندَ Word عن بقيّة عائلة OLE.
DOC_STREAM_MARKER = "WordDocument".encode("utf-16-le")
#: يكفي لبلوغ دليل التيّارات في مستندٍ عاديّ بلا قراءة الملفّ كلِّه.
DOC_PROBE_BYTES = 64 * 1024


def _looks_like_docx(payload: bytes) -> bool:
    """أرشيفُ ZIP فيه `word/document.xml` — لا مجرّد أرشيف."""
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
    except Exception:
        return False
    return DOCX_REQUIRED_MEMBER in names


def _looks_like_doc(payload: bytes) -> bool:
    """حاويةُ OLE فيها تيّارُ `WordDocument` — لا `.msi` ولا `.xls`."""
    return DOC_STREAM_MARKER in payload[:DOC_PROBE_BYTES]


def sniff_content_type(head: bytes):
    """نوعُ المحتوى المستنتَجُ من البايتات، أو `None` لما لا نعرفه.

    WEBP خاصّةٌ: `RIFF` ثمّ أربعةُ بايتاتِ حجمٍ ثمّ `WEBP` — فلا يكفي البادئ.
    """
    if not head:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    for signature, content_type in _MAGIC_SIGNATURES:
        if head.startswith(signature):
            return content_type
    return None


#: **سقفُ الجسم كلِّه** — لا حقلِ السيرة وحده. `validate_cv_upload` يعمل على
#: `validated_data`، أي **بعد** أن يكون Django قد حلّل الجسم كاملاً وسكب ما فوق
#: 2.5MB على قرص الخادم. فطلبٌ بسيرةٍ سليمةٍ من ٢ كيلوبايت و٩٩ حقلاً حشواً بـ٥٠٠
#: ميجا لكلٍّ يمرّ من كلّ فحوصنا ويقفل الـworkers الثلاثة — وهو حرفيّاً العطبُ
#: الذي أُزيل لأجله الرفعُ المجهول من هذه المنصة. فالسقفُ يُفحص من `CONTENT_LENGTH`
#: **قبل لمس `request.data`**، ويبقى `client_max_body_size` في nginx هو الحارسَ
#: الذي لا يُلفَّق (الترويسةُ تُزوَّر نزولاً لا صعوداً، فهي سقفٌ صالحٌ لا أرضيّة).
MAX_APPLICATION_BYTES = MAX_CV_BYTES + (256 * 1024)


class ApplicationTooLarge(Exception):
    """جسمُ الطلب فوق السقف — ٤١٣ قبل أن يُحلَّل بايتٌ واحد."""


class JobGone(Exception):
    """الوظيفةُ كانت هنا وانتهت — ٤١٠ لا ٤٠٤."""


def _new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _new_reference_code() -> str:
    """رقمُ مرجعٍ يقرؤه المتقدّم في شاشة الشكر — قصيرٌ وغيرُ متسلسل.

    المتسلسلُ يفشي عددَ المتقدّمين للشركة لكلّ من قدّم.
    """
    return secrets.token_hex(4).upper()


# ────────────────────────── الوظيفة ورابطُها ──────────────────────────


def create_job(*, tenant, actor, **fields) -> JobPosting:
    return JobPosting.objects.create(
        tenant=tenant,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
        token=_new_token(),
        **fields,
    )


def regenerate_job_token(*, job: JobPosting) -> JobPosting:
    """إبطالُ الرابط وإعادةُ توليده بضغطة — الرابطُ القديم يموت فوراً."""
    job.token = _new_token()
    job.save(update_fields=["token", "updated_at"])
    return job


def close_job(*, job: JobPosting) -> JobPosting:
    if job.is_open:
        job.is_open = False
        job.closed_at = timezone.now()
        job.save(update_fields=["is_open", "closed_at", "updated_at"])
    return job


def reopen_job(*, job: JobPosting) -> JobPosting:
    if not job.is_open:
        job.is_open = True
        job.closed_at = None
        job.save(update_fields=["is_open", "closed_at", "updated_at"])
    return job


def job_is_live(job: JobPosting, *, now=None) -> bool:
    """مفتوحةٌ ولم ينتهِ أجلُها — والأجلُ الفارغُ لا ينتهي أبداً."""
    if not job.is_open:
        return False
    if job.expires_at is None:
        return True
    return job.expires_at > (now or timezone.now())


def resolve_public_job(token: str) -> JobPosting:
    """الوظيفةُ خلف المفتاح، أو `JobGone` للمغلقة و`NotFound` لما لم يوجد قطّ.

    الفرقُ بين «كان هنا وانتهى» و«لم يكن هنا قطّ» يهمّ من فتح الرابط — وهو
    نفسُ تمييزِ الـRFQ العامّ في هذا المستودع.

    ولا فحصَ ترخيصٍ هنا: الوحدةُ تُطفأ فتختفي الشاشاتُ من المالك، أمّا رابطٌ
    نُشر في مجموعةٍ فيبقى مقروءاً حتى يُغلق صراحةً — وإطفاءُ اشتراكٍ ليس رسالةً
    يفهمها متقدّمٌ لا علاقةَ له بها. الترخيصُ يحرس **إدارة** الوظائف لا قراءتَها.
    """
    job = JobPosting.objects.filter(token=token).select_related("tenant").first()
    if job is None:
        raise NotFound("لا توجد وظيفة خلف هذا الرابط.")
    if not job_is_live(job):
        raise JobGone()
    return job


# ────────────────────────── السيرة الذاتيّة ──────────────────────────


def validate_cv_upload(
    *, size: int, filename: str, content_type: str, head: bytes, payload: bytes = b""
) -> None:
    """**الشرطان ١ و٢** — يُنفَّذان قبل أن يلمس البايتُ الأوّلُ أيَّ تخزين.

    الترتيبُ مقصود: الحجمُ أوّلاً، فرفضُ ملفٍّ ضخمٍ بعد قراءته يكون قد دفع ثمنَه.
    ثمّ الامتدادُ، ثمّ الترويسةُ المعلَنة، ثمّ **البايتات**: الثلاثةُ الأولى يكتبها
    الرافعُ كما يشاء، والأخيرةُ وحدها لا تُلفَّق.

    و`head` **إلزاميّ**: قيمةٌ افتراضيّةٌ فارغةٌ كانت تجعل أقوى الفحوص الثلاثة
    اختيارياً بحكم التوقيع — يكفي مستدعٍ ينساه ليبقى الحارسان المزوَّران وحدهما.
    """
    if size is None or size <= 0:
        raise ValidationError({"cv": "الملف فارغ."})
    if size > MAX_CV_BYTES:
        raise ValidationError(
            {"cv": "حجم السيرة الذاتية يتجاوز الحد المسموح (٥ ميجابايت)."}
        )

    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    extension = name[dot:] if dot > 0 else ""
    if extension not in ALLOWED_CV_EXTENSIONS:
        raise ValidationError(
            {"cv": "نوع الملف غير مسموح. المسموح: PDF أو Word أو صورة."}
        )

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_CV_CONTENT_TYPES:
        raise ValidationError(
            {"cv": "نوع محتوى الملف غير مسموح. المسموح: PDF أو Word أو صورة."}
        )

    # الاثنان معاً **ويصفان الشيءَ نفسه**: `.pdf` بمحتوى `image/png` يُردّ.
    allowed_for_extension = _EXTENSION_CONTENT_TYPES.get(extension, set())
    if declared not in allowed_for_extension:
        raise ValidationError(
            {"cv": "امتداد الملف لا يطابق نوع محتواه."}
        )

    # **البايتات هي الحَكَم.** ما سبق يقوله الرافعُ عن ملفّه؛ هذا ما يقوله الملفّ
    # عن نفسه. ملفٌّ تنفيذيٌّ أُعيدت تسميتُه `cv.pdf` وأُرسل بترويسة PDF يسقط هنا
    # وهنا فقط.
    actual = sniff_content_type(head)
    if actual is None:
        raise ValidationError(
            {"cv": "تعذّر التعرّف على محتوى الملف — المسموح: PDF أو Word أو صورة."}
        )
    if actual not in allowed_for_extension:
        raise ValidationError({"cv": "محتوى الملف لا يطابق امتداده."})

    # وخطوةٌ أبعد لعائلتَي ZIP وOLE: توقيعُهما يطابق أرشيفاً أو حاويةً لا مستنداً.
    if extension == ".docx" and not _looks_like_docx(payload):
        raise ValidationError({"cv": "الملف ليس مستند Word صالحاً."})
    if extension == ".doc" and not _looks_like_doc(payload):
        raise ValidationError({"cv": "الملف ليس مستند Word صالحاً."})


def guess_cv_content_type(url: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(urlparse(url or "").path)
    return guessed or fallback


# ────────────────────────── التقديم ──────────────────────────


@transaction.atomic
def submit_application(
    *, job: JobPosting, name: str, phone: str, email: str = "",
    about: str = "", cv_url: str = "", cv_name: str = "",
) -> JobApplicant:
    """**الشرط ٥ — الحجر**: يُحفظ بحالة «جديد» ولا يمسّ شيئاً آخر.

    لا موظفاً يُنشأ، ولا مقعداً يُستهلك، ولا دعوةً تُطلق، ولا حقلاً في الوظيفة
    يُحدَّث — على نمط طلب عرض السعر العامّ، حيث لا يمسّ مُدخَلُ المجهول الدفاترَ
    إلا بموافقةٍ بشريّة. الحالةُ مثبَّتةٌ هنا ولا تُقرأ من الطلب.

    وحيّةٌ تُفحص مرّةً أخرى داخل المعاملة: الفحصُ في العرض يسبق الكتابةَ بلحظة،
    وإغلاقٌ يقع في تلك اللحظة كان سيمرّ.
    """
    if not job_is_live(job):
        raise JobGone()

    # رقمُ المرجع عشوائيّ، فالتصادمُ نادرٌ لا مستحيل — والتكرارُ محدودٌ لا حلقة.
    for _ in range(5):
        try:
            with transaction.atomic():
                return JobApplicant.objects.create(
                    tenant=job.tenant,
                    job=job,
                    name=name.strip(),
                    phone=phone.strip(),
                    email=(email or "").strip(),
                    about=(about or "").strip(),
                    cv_url=(cv_url or "").strip(),
                    cv_name=(cv_name or "").strip(),
                    status=JobApplicant.STATUS_NEW,
                    reference_code=_new_reference_code(),
                )
        except IntegrityError:
            continue
    raise ValidationError({"detail": "تعذّر تسجيل الطلب، حاول مرة أخرى."})


# ────────────────────────── دورةُ المتقدّم ──────────────────────────

#: «موظَّف» ليست حالةً تُضبط باليد: تُبلَغ بإنشاء سجلّ الموظف من المتقدّم وحده،
#: وإلا صارت حالةً تقول «وظّفناه» بلا موظفٍ في النظام.
MANUAL_STATUSES = {
    JobApplicant.STATUS_NEW,
    JobApplicant.STATUS_INTERVIEW,
    JobApplicant.STATUS_REJECTED,
}


def set_applicant_status(*, applicant: JobApplicant, status: str) -> JobApplicant:
    if status not in MANUAL_STATUSES:
        raise ValidationError(
            {"status": "حالة «موظَّف» تُبلَغ بإنشاء سجلّ الموظف من المتقدّم."}
        )
    applicant.status = status
    applicant.save(update_fields=["status", "updated_at"])
    return applicant


def rate_applicant(*, applicant: JobApplicant, rating=None, notes=None) -> JobApplicant:
    """نجومٌ من خمسٍ وملاحظةٌ حرّة — صفرٌ يعني «بلا تقييم» لا «صفر نجوم»."""
    fields = ["updated_at"]
    if rating is not None:
        if not 0 <= int(rating) <= 5:
            raise ValidationError({"rating": "التقييم من صفر إلى خمس نجوم."})
        applicant.rating = int(rating)
        fields.append("rating")
    if notes is not None:
        applicant.notes = notes
        fields.append("notes")
    applicant.save(update_fields=fields)
    return applicant


def mark_applicant_hired(*, applicant: JobApplicant, employee) -> JobApplicant:
    """يُستدعى بعد إنشاء الموظف يدويّاً — لا تحويلَ آليّ.

    الإنشاءُ يستهلك مقعداً ويطلق دعوةً، وكلاهما أثقلُ من أن يقع بضغطةٍ واحدةٍ
    بلا مراجعة. فالزرُّ يفتح نموذجَ «أضف موظفاً» مملوءاً بالاسم والرقم، وهذه
    الدالّةُ تُستدعى **عند الحفظ**.
    """
    applicant.status = JobApplicant.STATUS_HIRED
    applicant.hired_employee = employee
    applicant.save(update_fields=["status", "hired_employee", "updated_at"])
    return applicant
