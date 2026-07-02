"""نقطة الرفع الموحّدة ‎/api/media/upload/‎ — ترفع إلى Cloudinary (الخادم يحمل السرّ)
وتعيد الرابط. مفتوحة للجميع (تُعيد استخدام سلوك preset السابق) بحدّ حجم.
Cloudinary مُموّه (mock) — لا اتصال شبكي فعلي في الاختبار.
"""
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

UPLOAD_URL = "/api/media/upload/"


class MediaUploadTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("cloudinary.uploader.upload")
    def test_pdf_upload_returns_secure_url_as_raw(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/dd63wjj5x/raw/upload/ds.pdf"
        }
        f = SimpleUploadedFile("ds.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        res = self.client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == 200, res.content[:300]
        assert res.json()["url"].endswith("ds.pdf")
        # PDF ⇒ resource_type=raw (يتفادى مشاكل الرفع الموقّع للمستندات)
        assert mock_upload.call_args.kwargs.get("resource_type") == "raw"

    @patch("cloudinary.uploader.upload")
    def test_image_upload_uses_image_resource_type(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/dd63wjj5x/image/upload/x.png"
        }
        f = SimpleUploadedFile("x.png", b"\x89PNG fake", content_type="image/png")
        res = self.client.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code == 200, res.content[:300]
        assert mock_upload.call_args.kwargs.get("resource_type") == "image"

    def test_missing_file_is_400(self):
        res = self.client.post(UPLOAD_URL, {}, format="multipart")
        assert res.status_code == 400


class CloudinaryRefParseTest(TestCase):
    """استخراج public_id/resource_type من رابط Cloudinary لحذف الأصل."""

    def test_raw_keeps_extension_in_public_id(self):
        from core.media_views import _parse_cloudinary_ref
        pid, rtype = _parse_cloudinary_ref(
            "https://res.cloudinary.com/dd63wjj5x/raw/upload/v1/ktra_uploads/ds.pdf"
        )
        assert rtype == "raw"
        assert pid == "ktra_uploads/ds.pdf"  # raw ⇒ الامتداد جزء من الـpublic_id

    def test_image_strips_extension(self):
        from core.media_views import _parse_cloudinary_ref
        pid, rtype = _parse_cloudinary_ref(
            "https://res.cloudinary.com/dd63wjj5x/image/upload/v9/ktra_uploads/pic.png"
        )
        assert rtype == "image"
        assert pid == "ktra_uploads/pic"  # image ⇒ يُزال الامتداد

    def test_non_cloudinary_url_returns_none(self):
        from core.media_views import _parse_cloudinary_ref, destroy_cloudinary_asset
        assert _parse_cloudinary_ref("https://example.com/x.pdf") == (None, None)
        assert destroy_cloudinary_asset("https://example.com/x.pdf") is False
