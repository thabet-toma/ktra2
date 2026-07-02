"""
رفع الوسائط الموحّد إلى Cloudinary — نقطة الاختناق الوحيدة لكل رفوعات المنصة.
الواجهة ترسل الملف (multipart: file) ونعيد الرابط الآمن (secure_url). السرّ يبقى
في الخادم (settings.CLOUDINARY_STORAGE) ولا يُعرَّض للمتصفح إطلاقاً.

مفتوح للجميع (AllowAny) مطابقةً لسلوك الـ upload preset السابق (كان قابلاً للنداء من
العالم)، لكنه الآن يمرّ عبر الخادم بالسرّ المضبوط ⇒ أفضل: يخفي المفاتيح ويفرض حداً للحجم.
"""
from __future__ import annotations

import logging
import re

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    parser_classes,
    permission_classes,
)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")


def _resource_type(name: str, content_type: str | None) -> str:
    """image للصور، raw للـPDF/المستندات (يتفادى مشاكل الرفع الموقّع)، auto لغيرها."""
    ct = (content_type or "").lower()
    n = (name or "").lower()
    if ct.startswith("image/") or n.endswith(_IMAGE_EXTS):
        return "image"
    if "pdf" in ct or n.endswith(".pdf"):
        return "raw"
    return "auto"


@api_view(["POST"])
@authentication_classes([])  # نقطة عامة — نتفادى مصادقة الجلسة/CSRF للرفع المجهول
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def media_upload(request):
    """
    رفع ملف واحد (حقل النموذج: file) إلى Cloudinary وإرجاع رابطه.
    الرد الناجح: { "url": "https://res.cloudinary.com/..." }
    """
    f = request.FILES.get("file")
    if not f:
        return Response({"detail": "حقل file مطلوب."}, status=status.HTTP_400_BAD_REQUEST)

    size = getattr(f, "size", 0) or 0
    if size > MAX_UPLOAD_BYTES:
        return Response(
            {"detail": f"حجم الملف يتجاوز الحد ({MAX_UPLOAD_BYTES // (1024 * 1024)}MB)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cfg = getattr(settings, "CLOUDINARY_STORAGE", {}) or {}
    cloud_name = (cfg.get("CLOUD_NAME") or "").strip()
    api_key = (cfg.get("API_KEY") or "").strip()
    api_secret = (cfg.get("API_SECRET") or "").strip()
    if not all([cloud_name, api_key, api_secret]):
        return Response(
            {"detail": "لم تُضبط بيانات Cloudinary على الخادم."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

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
            folder="ktra_uploads",
        )
    except Exception as exc:  # فشل الرفع لا يُسقط الطلب بـ 500 غامض
        logger.warning("media_upload failed name=%s err=%s", getattr(f, "name", "?"), exc)
        return Response(
            {"detail": f"فشل رفع الملف إلى Cloudinary: {exc}"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    url = result.get("secure_url") or result.get("url")
    if not url:
        return Response(
            {"detail": "لم يُعَد رابط الملف من Cloudinary."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    logger.info("media_upload ok name=%s -> %s", getattr(f, "name", "?"), url[:80])
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
        logger.info("destroy_cloudinary_asset ok public_id=%s rtype=%s", public_id, rtype)
        return True
    except Exception as exc:
        logger.warning("destroy_cloudinary_asset failed url=%s err=%s", url[:80], exc)
        return False
