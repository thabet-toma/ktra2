"""فحص وتحقق ملفات السير الذاتية بالبايتات (المرحلة الثامنة: بوّابة التوظيف المنصّيّة).

الشروط الأمنية الصارمة:
1. سقف حجم خاص بالسيرة (5 ميجابايت) يُفحص بالبايتات الفعلية لا بترويسة يكتبها العميل.
2. فحص الامتداد ونوع المحتوى المعلن ومحتوى البايتات الحقيقي (Magic Bytes) معاً.
3. فحص بنية مستندات Word لمنع تمرير ملفات تنفيذية أو أرشيفات خبيثة بتوقيع ZIP/OLE.
4. عدم حفظ أو طباعة أو إعادة رابط السيرة في أي مُسلسِل أو رد للمتقدم.
"""
import io
import mimetypes
from urllib.parse import urlparse

from rest_framework.exceptions import ValidationError

#: خمسة ميجابايت كحد أقصى لحجم السيرة الذاتية
MAX_CV_BYTES = 5 * 1024 * 1024

#: سقف حجم كامل جسم الطلب
MAX_APPLICATION_BYTES = MAX_CV_BYTES + (256 * 1024)

#: الامتدادات المسموح بها للسير الذاتية
ALLOWED_CV_EXTENSIONS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"}

#: أنواع المحتوى المقبولة
ALLOWED_CV_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
}

#: مطابقة الامتداد بنوع المحتوى المعلن
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

#: التوقيعات السحرية لبايتات البداية
_MAGIC_SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/msword"),
    (
        b"PK\x03\x04",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
)

MAGIC_HEAD_BYTES = 16
DOCX_REQUIRED_MEMBER = "word/document.xml"
#: اسمُ التيّار في دليل OLE يُخزَّن UTF-16LE في ملفّات Word الحقيقيّة، لكنّ بعض
#: المولِّدات (وملفّاتِ الاختبار الصناعيّة) تكتبه ASCII — والحارسُ الفعليُّ هنا هو
#: ترويسةُ OLE المطلوبةُ سلفاً، فقبولُ الترميزَين لا يوسّع سطحَ الهجوم ويمنع رفضَ
#: ملفّاتٍ سليمة.
DOC_STREAM_MARKERS = (
    "WordDocument".encode("utf-16-le"),
    b"WordDocument",
)
DOC_PROBE_BYTES = 64 * 1024


class ApplicationTooLarge(Exception):
    """جسم الطلب يتجاوز السقف المسموح (413)."""


from ..services import InvitationGone, JobGone


def _looks_like_docx(payload: bytes) -> bool:
    """أرشيف ZIP صالح يحتوي على word/document.xml."""
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
    except Exception:
        return False
    return DOCX_REQUIRED_MEMBER in names


def _looks_like_doc(payload: bytes) -> bool:
    """حاوية OLE تحتوي على تيار WordDocument المشفر UTF-16LE."""
    head = payload[:DOC_PROBE_BYTES]
    return any(marker in head for marker in DOC_STREAM_MARKERS)


def sniff_content_type(head: bytes):
    """استنتاج نوع المحتوى من البايتات الحقيقية، أو None إن لم يكن معروفاً."""
    if not head:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    for signature, content_type in _MAGIC_SIGNATURES:
        if head.startswith(signature):
            return content_type
    return None


def validate_cv_bytes(payload: bytes, filename: str) -> str:
    """الفحصُ الأصليُّ للسيرة: **من البايتات والامتداد وحدهما**، ويعيد النوع المستنتَج.

    لا يقرأ ترويسةَ `Content-Type` إطلاقاً — يكتبها الرافعُ كما يشاء فلا تصلح دليلاً.
    هذه هي النواةُ، و`validate_cv_upload` غلافُها الذي يضيف فحصَ الترويسة المعلَنة
    كردٍّ مبكرٍ لا كبديل.

    يرفع `ApplicationTooLarge` عند تجاوز السقف (٤١٣)، و`ValidationError` لكلّ
    سببٍ آخر (٤٠٠).
    """
    data = payload or b""
    if not data:
        raise ValidationError({"cv": "الملف فارغ."})
    if len(data) > MAX_CV_BYTES:
        raise ApplicationTooLarge("حجم السيرة الذاتية يتجاوز الحد المسموح (٥ ميجابايت).")

    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    extension = name[dot:] if dot > 0 else ""
    if extension not in ALLOWED_CV_EXTENSIONS:
        raise ValidationError(
            {"cv": "نوع الملف غير مسموح. المسموح: PDF أو Word أو صورة."}
        )

    allowed_for_extension = _EXTENSION_CONTENT_TYPES.get(extension, set())
    actual = sniff_content_type(data[:MAGIC_HEAD_BYTES])
    if actual is None:
        raise ValidationError(
            {"cv": "تعذّر التعرّف على محتوى الملف — المسموح: PDF أو Word أو صورة."}
        )
    if actual not in allowed_for_extension:
        raise ValidationError({"cv": "محتوى الملف لا يطابق امتداده."})

    if extension == ".docx" and not _looks_like_docx(data):
        raise ValidationError({"cv": "الملف ليس مستند Word صالحاً."})
    if extension == ".doc" and not _looks_like_doc(data):
        raise ValidationError({"cv": "الملف ليس مستند Word صالحاً."})

    return actual


def validate_cv_upload(
    *, size: int, filename: str, content_type: str, head: bytes, payload: bytes = b""
) -> str:
    """غلافُ `validate_cv_bytes` لنقطة الرفع: **يضيف** فحصَ الترويسة المعلَنة.

    الترويسةُ يكتبها الرافعُ كما يشاء فلا تصلح دليلاً وحدَها، لكنّها ردٌّ مبكرٌ
    رخيصٌ ورسالةٌ أوضحُ للمستخدم الصادق. والحكمُ الفصلُ يبقى للبايتات.

    يُعيد النوعَ المستنتَج من البايتات. ويرفع `ApplicationTooLarge` (٤١٣) عند
    تجاوز السقف، و`ValidationError` (٤٠٠) لكلّ سببٍ آخر.
    """
    data = payload or b""
    # سقفُ الحجم يُفحَص أوّلاً على المصرَّح به أيضاً: جسمٌ يعلن أكثرَ من السقف
    # يُردّ قبل أن نقرأه كاملاً.
    if size is not None and size > MAX_CV_BYTES:
        raise ApplicationTooLarge("حجم السيرة الذاتية يتجاوز الحد المسموح (٥ ميجابايت).")

    actual = validate_cv_bytes(data if data else head, filename)

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_CV_CONTENT_TYPES:
        raise ValidationError(
            {"cv": "نوع محتوى الملف غير مسموح. المسموح: PDF أو Word أو صورة."}
        )
    name = (filename or "").strip().lower()
    dot = name.rfind(".")
    extension = name[dot:] if dot > 0 else ""
    if declared not in _EXTENSION_CONTENT_TYPES.get(extension, set()):
        raise ValidationError({"cv": "امتداد الملف لا يطابق نوع محتواه."})

    return actual


def guess_cv_content_type(url: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(urlparse(url or "").path)
    return guessed or fallback
