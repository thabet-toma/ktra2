"""نقطة الرفع الموحّدة ‎/api/media/upload/‎ — ترفع إلى Cloudinary (الخادم يحمل السرّ)
وتعيد الرابط. الجلسة الأمنية 2026-08-11 (P0-8): صارت تتطلب مصادقة Token وخاضعة
لـthrottle — لا رفع مجهول يقفل worker. Cloudinary مُموّه (mock) — لا اتصال شبكي.

ومنذ THA-252: كل رفع يُسجّل بايتاته ومالكه في `core.TenantAsset`، وكل حذف من
التطبيق يمحو السطر — القياس يُكتب لحظة الرفع لأنه لا يمكن استرجاعه بعدها.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import TenantAsset
from core.tenant_utils import invalidate_tenant_cache
from tenants.models import Tenant, UserCompanyMembership

UPLOAD_URL = "/api/media/upload/"

FAKE_CLOUDINARY = {"CLOUD_NAME": "test-cloud", "API_KEY": "key", "API_SECRET": "secret"}


class MediaUploadTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="uploader", password="x")
        cls.token = Token.objects.create(user=cls.user)

    def setUp(self):
        cache.clear()  # عدّادات الـthrottle بين الاختبارات
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_anonymous_upload_rejected(self):
        # P0-8: بلا توكن ⇒ 401/403، ولا يُستدعى Cloudinary إطلاقاً
        anon = APIClient()
        f = SimpleUploadedFile("x.png", b"\x89PNG fake", content_type="image/png")
        res = anon.post(UPLOAD_URL, {"file": f}, format="multipart")
        assert res.status_code in (401, 403), res.content[:300]

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


@override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY)
class MediaUploadLedgerTest(TestCase):
    """سجلّ البايتات: مَن يملك الملف المرفوع، وكم يزن — يُكتب لحظة الرفع.

    شركتان في القاعدة عمداً: شركةٌ واحدة تُفعّل الحلّ التلقائي في `get_tenant`
    فيمرّ اختبار «بلا شركة» كذباً.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(CompanyName="شركة الرفع", Status="Active")
        Tenant.objects.create(CompanyName="شركة ثانية", Status="Active")
        cls.member = User.objects.create_user(username="ledger-member", password="x")
        UserCompanyMembership.objects.create(
            user=cls.member, tenant=cls.tenant, role="manager")
        cls.member_token = Token.objects.create(user=cls.member)
        cls.admin = User.objects.create_superuser(
            username="ledger-root", email="ledger-root@example.com", password="x")
        cls.admin_token = Token.objects.create(user=cls.admin)

    def setUp(self):
        cache.clear()
        invalidate_tenant_cache()  # كاش «الشركة الوحيدة» على مستوى العملية

    def _api(self, token, tenant=None):
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        if tenant is not None:
            api.credentials(
                HTTP_AUTHORIZATION=f"Token {token.key}",
                HTTP_X_TENANT_ID=str(tenant.pk),
            )
        return api

    @staticmethod
    def _cloudinary_result(public_id="ktra_uploads/pic", size=2048):
        return {
            "secure_url": f"https://res.cloudinary.com/test-cloud/image/upload/v1/{public_id}.png",
            "public_id": public_id,
            "bytes": size,
            "resource_type": "image",
        }

    @staticmethod
    def _png():
        return SimpleUploadedFile("pic.png", b"\x89PNG fake", content_type="image/png")

    @patch("cloudinary.uploader.upload")
    def test_upload_with_a_company_records_its_bytes_and_owner(self, mock_upload):
        folder = f"ktra_uploads/t{self.tenant.pk}"
        mock_upload.return_value = self._cloudinary_result(f"{folder}/pic", 2048)

        res = self._api(self.member_token, self.tenant).post(
            UPLOAD_URL, {"file": self._png()}, format="multipart")

        assert res.status_code == 200, res.content[:300]
        # الرفع نفسه يذهب إلى مجلّد الشركة — الأصول الجديدة قابلة للتمييز عند المزوّد
        assert mock_upload.call_args.kwargs.get("folder") == folder
        asset = TenantAsset.objects.get(public_id=f"{folder}/pic")
        assert asset.tenant_id == self.tenant.pk
        assert asset.bytes == 2048
        assert asset.resource_type == "image"
        assert asset.folder == folder
        assert asset.source == "upload"
        assert asset.uploaded_by_id == self.member.pk

    @patch("cloudinary.uploader.upload")
    def test_platform_scope_from_a_super_admin_is_attributed_to_no_company(self, mock_upload):
        mock_upload.return_value = self._cloudinary_result("ktra_uploads/note", 512)

        # سوبر أدمن بشركةٍ نشطة في ترويسته — صورة ملاحظة التطوير ليست ملكها
        res = self._api(self.admin_token, self.tenant).post(
            UPLOAD_URL, {"file": self._png(), "scope": "platform"}, format="multipart")

        assert res.status_code == 200, res.content[:300]
        assert mock_upload.call_args.kwargs.get("folder") == "ktra_uploads"
        asset = TenantAsset.objects.get(public_id="ktra_uploads/note")
        assert asset.tenant_id is None
        assert asset.uploaded_by_id == self.admin.pk

    @patch("cloudinary.uploader.upload")
    def test_platform_scope_from_a_normal_user_is_attributed_normally(self, mock_upload):
        folder = f"ktra_uploads/t{self.tenant.pk}"
        mock_upload.return_value = self._cloudinary_result(f"{folder}/sneaky", 100)

        # النطاق المنصّي قدرةُ سوبر أدمن؛ من غيره يُتجاهل ويُنسب الملف لشركته
        res = self._api(self.member_token, self.tenant).post(
            UPLOAD_URL, {"file": self._png(), "scope": "platform"}, format="multipart")

        assert res.status_code == 200, res.content[:300]
        assert TenantAsset.objects.get(public_id=f"{folder}/sneaky").tenant_id == self.tenant.pk

    @patch("cloudinary.uploader.upload")
    def test_upload_without_a_company_is_recorded_unattributed_not_refused(self, mock_upload):
        mock_upload.return_value = self._cloudinary_result("ktra_uploads/orphan", 64)

        res = self._api(self.member_token).post(
            UPLOAD_URL, {"file": self._png()}, format="multipart")

        # لا شركة ولا نطاق منصّي ⇒ الرفع يمرّ ويظهر في «غير منسوب»، ولا يفشل المستخدم
        assert res.status_code == 200, res.content[:300]
        assert TenantAsset.objects.get(public_id="ktra_uploads/orphan").tenant_id is None

    @patch("cloudinary.uploader.upload")
    def test_a_failing_ledger_write_never_breaks_a_successful_upload(self, mock_upload):
        mock_upload.return_value = self._cloudinary_result("ktra_uploads/kept", 7)

        with patch(
            "core.models.TenantAsset.objects.update_or_create",
            side_effect=RuntimeError("db down"),
        ):
            res = self._api(self.member_token, self.tenant).post(
                UPLOAD_URL, {"file": self._png()}, format="multipart")

        # الملف صار عند Cloudinary فعلاً — إخفاء الرابط يخسره بلا فائدة
        assert res.status_code == 200, res.content[:300]
        assert res.json()["url"].endswith("kept.png")
        assert not TenantAsset.objects.exists()

    @patch("cloudinary.uploader.destroy")
    def test_destroying_an_asset_forgets_its_bytes(self, mock_destroy):
        mock_destroy.return_value = {"result": "ok"}
        TenantAsset.objects.create(
            tenant=self.tenant, public_id="ktra_uploads/gone", bytes=900,
            resource_type="image", folder="ktra_uploads",
        )
        from core.media_views import destroy_cloudinary_asset

        assert destroy_cloudinary_asset(
            "https://res.cloudinary.com/test-cloud/image/upload/v1/ktra_uploads/gone.png"
        ) is True
        assert not TenantAsset.objects.filter(public_id="ktra_uploads/gone").exists()


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
