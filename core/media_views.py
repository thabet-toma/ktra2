"""
رفع الوسائط الموحّد إلى Cloudinary — نقطة الاختناق الوحيدة لكل رفوعات المنصة.
الواجهة ترسل الملف (multipart: file) ونعيد الرابط الآمن (secure_url). السرّ يبقى
في الخادم (settings.CLOUDINARY_STORAGE) ولا يُعرَّض للمتصفح إطلاقاً.

تقييد أمني (الجلسة الأمنية 2026-08-11 — P0-8 في docs/SCALABILITY_AUDIT.md):
كانت النقطة `AllowAny` بلا مصادقة ولا throttle ⇒ أي زائر يقدر يشغّل رفع
Cloudinary متزامناً حتى 25MB فيقفل worker (وسقف الـworkers = 3). الآن تتطلب
مصادقة Token وتخضع لـthrottle مخصص. (قسم الرفع في PublicGallery للزوار أُخفي
في نفس الجلسة — لا مستهلك مجهول باقٍ.)
"""
from __future__ import annotations

import logging
import re

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    parser_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from core.import_access import is_super_admin
from core.tenant_utils import get_tenant

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")


class MediaUploadThrottle(UserRateThrottle):
    scope = "media_upload"


class MediaUploadError(Exception):
    """فشل رفع يحمل حالته ورسالته العربية — كي يردّها كل مستهلك بنفس الصياغة."""

    def __init__(self, detail: str, status_code: int):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _resource_type(name: str, content_type: str | None) -> str:
    """image للصور، raw للـPDF/المستندات (يتفادى مشاكل الرفع الموقّع)، auto لغيرها."""
    ct = (content_type or "").lower()
    n = (name or "").lower()
    if ct.startswith("image/") or n.endswith(_IMAGE_EXTS):
        return "image"
    if "pdf" in ct or n.endswith(".pdf"):
        return "raw"
    return "auto"


def _record_asset(result: dict, *, folder: str, tenant, uploaded_by) -> None:
    """يسجّل الأصل المرفوع في `core.TenantAsset` — أفضل-جهد لا يُسقط رفعاً ناجحاً.

    البايتات والـ`public_id` يأتيان من ردّ Cloudinary نفسه، فالسجلّ **بلا نداء
    شبكي إضافي**. وهو `update_or_create` لا `create` لأن `public_id` فريد: إعادة
    رفعٍ على نفس المعرّف أو صفٌّ كتبه الاسترجاع الأثري لا يجوز أن يرفع
    `IntegrityError` في وجه مستخدمٍ رفعُه نجح.

    الفشل هنا يُسجَّل ERROR ولا يُرمى: الملف صار عند Cloudinary فعلاً، وإخفاء
    رابطه يخسره على المستخدم بلا فائدة — والاسترجاع الأثري يداوي السجلّ لاحقاً.
    """
    public_id = (result.get("public_id") or "").strip()
    if not public_id:
        logger.error("tenant_asset ledger skipped: no public_id in cloudinary result")
        return
    try:
        from core.models import TenantAsset

        TenantAsset.objects.update_or_create(
            public_id=public_id[:191],
            defaults={
                "tenant": tenant,
                "bytes": int(result.get("bytes") or 0),
                "resource_type": (result.get("resource_type") or "")[:20],
                "folder": folder[:200],
                "source": "upload",
                "uploaded_by": (
                    uploaded_by
                    if getattr(uploaded_by, "is_authenticated", False)
                    else None
                ),
            },
        )
    except Exception as exc:
        logger.error(
            "tenant_asset ledger write failed public_id=%s err=%s", public_id[:120], exc)


def _forget_asset(public_id: str) -> None:
    """يمحو سطر السجلّ بعد حذف الأصل فعلياً — أفضل-جهد كالحذف نفسه."""
    try:
        from core.models import TenantAsset

        TenantAsset.objects.filter(public_id=public_id).delete()
    except Exception as exc:
        logger.warning(
            "tenant_asset ledger delete failed public_id=%s err=%s", public_id[:120], exc)


def upload_media_file(
    f, folder: str = "ktra_uploads", *, tenant=None, uploaded_by=None,
) -> str:
    """يرفع ملفاً واحداً إلى Cloudinary ويعيد رابطه الآمن.

    قلب الرفع مشترك: النقطة العامة `/api/media/upload/` ومسار مستندات مكتب
    المحاسبة كلاهما ينادي هذه الدالة، فحدُّ الحجم وفحص الاعتماد وصياغة الفشل
    تبقى نسخةً واحدة. الفشل يخرج كـ`MediaUploadError` بحالته، والمستهلك يردّه.

    ولأنها نقطة الاختناق الوحيدة، فهي أيضاً المكان الوحيد الذي يُقاس فيه
    استهلاك التخزين: `tenant` يضع الملف في مجلّد شركته
    (`{folder}/t{id}`) ويكتب سطر `core.TenantAsset` بحجمه ومالكه.
    """
    size = getattr(f, "size", 0) or 0
    if size > MAX_UPLOAD_BYTES:
        raise MediaUploadError(
            f"حجم الملف يتجاوز الحد ({MAX_UPLOAD_BYTES // (1024 * 1024)}MB).",
            status.HTTP_400_BAD_REQUEST,
        )

    cfg = getattr(settings, "CLOUDINARY_STORAGE", {}) or {}
    cloud_name = (cfg.get("CLOUD_NAME") or "").strip()
    api_key = (cfg.get("API_KEY") or "").strip()
    api_secret = (cfg.get("API_SECRET") or "").strip()
    if not all([cloud_name, api_key, api_secret]):
        raise MediaUploadError(
            "لم تُضبط بيانات Cloudinary على الخادم.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    target_folder = f"{folder}/t{tenant.pk}" if tenant is not None else folder

    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
        f.seek(0)
        result = cloudinary.uploader.upload(
            f,
            resource_type=_resource_type(
                getattr(f, "name", ""), getattr(f, "content_type", None)
            ),
            folder=target_folder,
        )
    except Exception as exc:  # فشل الرفع لا يُسقط الطلب بـ 500 غامض
        logger.warning("media_upload failed name=%s err=%s", getattr(f, "name", "?"), exc)
        raise MediaUploadError(
            f"فشل رفع الملف إلى Cloudinary: {exc}", status.HTTP_502_BAD_GATEWAY,
        ) from exc

    url = result.get("secure_url") or result.get("url")
    if not url:
        raise MediaUploadError(
            "لم يُعَد رابط الملف من Cloudinary.", status.HTTP_502_BAD_GATEWAY,
        )

    _record_asset(result, folder=target_folder, tenant=tenant, uploaded_by=uploaded_by)
    logger.info("media_upload ok name=%s -> %s", getattr(f, "name", "?"), url[:80])
    return url


@api_view(["POST"])
@permission_classes([IsAuthenticated])  # P0-8: لا رفع مجهول — يقفل الـworker
@throttle_classes([MediaUploadThrottle])
@parser_classes([MultiPartParser, FormParser])
def media_upload(request):
    """
    رفع ملف واحد (حقل النموذج: file) إلى Cloudinary وإرجاع رابطه.
    الرد الناجح: { "url": "https://res.cloudinary.com/..." }

    حقل اختياري `scope=platform`: يجعل الملف أصلاً **منصّياً** لا يتبع شركة —
    صور ملاحظات التطوير يرفعها سوبر أدمن وشركةٌ ما نشطةٌ في ترويسته، فنسبُها
    إليها يحمّل شركةً بريئةً بايتاتٍ لا تراها. وهو قدرةُ سوبر أدمن حصراً:
    من غيره يُتجاهل الحقل ويُنسب الملف لشركته كالمعتاد.
    """
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "حقل file مطلوب."}, status=status.HTTP_400_BAD_REQUEST)

    platform_scope = (
        str(request.data.get("scope") or "").strip().lower() == "platform"
        and is_super_admin(request.user)
    )
    # بلا شركة وبلا نطاق منصّي: الرفع يمرّ ويُسجَّل بلا نسبة («غير منسوب») —
    # القياس ناقصٌ صراحةً أهون من رفعٍ يفشل في وجه مستخدم.
    tenant = None if platform_scope else get_tenant(request)

    try:
        url = upload_media_file(f, tenant=tenant, uploaded_by=request.user)
    except MediaUploadError as exc:
        return Response({"detail": exc.detail}, status=exc.status_code)

    return Response({"url": url})


def _parse_cloudinary_ref(url: str) -> tuple[str | None, str | None]:
    """يستخرج (public_id, resource_type) من secure_url لأصل Cloudinary.

    مثال: https://res.cloudinary.com/<cloud>/<rtype>/upload/v123/<folder>/<name>.<ext>
    - raw: الامتداد جزء من الـpublic_id فيُبقى · image/video: يُزال الامتداد.
    """
    m = re.search(
        r"res\.cloudinary\.com/[^/]+/(image|raw|video)/upload/(?:v\d+/)?(.+)$",
        url or "",
    )
    if not m:
        return None, None
    rtype, rest = m.group(1), m.group(2)
    public_id = rest if rtype == "raw" else re.sub(r"\.[^./]+$", "", rest)
    return public_id, rtype


def destroy_cloudinary_asset(url: str) -> bool:
    """حذف أفضل-جهد لأصل Cloudinary من رابطه. لا يرمي استثناءً — يسجّل تحذيراً عند الفشل
    (الحذف من SQL يبقى المصدر الموثوق؛ فشل Cloudinary لا يجب أن يُسقط العملية)."""
    if not (url and isinstance(url, str) and "res.cloudinary.com" in url):
        return False
    public_id, rtype = _parse_cloudinary_ref(url)
    if not public_id:
        return False
    cfg = getattr(settings, "CLOUDINARY_STORAGE", {}) or {}
    cloud_name = (cfg.get("CLOUD_NAME") or "").strip()
    api_key = (cfg.get("API_KEY") or "").strip()
    api_secret = (cfg.get("API_SECRET") or "").strip()
    if not all([cloud_name, api_key, api_secret]):
        return False
    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
        cloudinary.uploader.destroy(public_id, resource_type=rtype, invalidate=True)
        _forget_asset(public_id)  # البايتات لم تعد محسوبةً على أحد
        logger.info("destroy_cloudinary_asset ok public_id=%s rtype=%s", public_id, rtype)
        return True
    except Exception as exc:
        logger.warning("destroy_cloudinary_asset failed url=%s err=%s", url[:80], exc)
        return False
