"""مكتب المحاسبة — سطح الـAPI تحت `/api/accountant/practice/`.

ثلاثة أشياء تُختبر هنا فوق HTTP لا فوق دوال الخدمات: أن الدورة الكاملة تعمل من
المتصفح، وأن **صفّ مكتبٍ آخر «غير موجود» (404) لا «ممنوع»** حتى من فوق الشبكة،
وأن إطفاء العَلَم يُخفي السطح كاملاً بـ404 — فلا يكشف الردُّ أن هناك ما يُطفأ.

Cloudinary مُموّه (mock) — لا اتصال شبكي، على نمط `core/tests/test_media_upload.py`.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accountant_portal.models import (
    AccountantProfile,
    PracticeClient,
    PracticeDocument,
    PracticeProgram,
    PracticeTask,
)
from core.models import TenantAsset

BASE = "/api/accountant/practice"

#: كل مسارات المكتب — تُستعمل في اختبار العَلَم المُطفأ كي لا ينفلت مسار جديد
#: من الحارس بصمت (المسار الذي لا يظهر هنا لا يُحرَس).
PRACTICE_ROUTES = (
    ("get", f"{BASE}/clients/"),
    ("post", f"{BASE}/clients/"),
    ("get", f"{BASE}/clients/1/"),
    ("patch", f"{BASE}/clients/1/"),
    ("delete", f"{BASE}/clients/1/"),
    ("post", f"{BASE}/clients/1/restore/"),
    ("get", f"{BASE}/programs/"),
    ("post", f"{BASE}/programs/"),
    ("patch", f"{BASE}/programs/1/"),
    ("delete", f"{BASE}/programs/1/"),
    ("get", f"{BASE}/tasks/"),
    ("post", f"{BASE}/tasks/"),
    ("patch", f"{BASE}/tasks/1/"),
    ("delete", f"{BASE}/tasks/1/"),
    ("get", f"{BASE}/documents/"),
    ("post", f"{BASE}/documents/upload/"),
    ("delete", f"{BASE}/documents/1/"),
    ("get", f"{BASE}/settings/"),
    ("patch", f"{BASE}/settings/"),
    ("get", f"{BASE}/deadlines/"),
    ("get", f"{BASE}/dashboard/"),
)


def make_office(username, tax_number):
    user = User.objects.create_user(username, email=f"{username}@example.com")
    AccountantProfile.objects.create(
        user=user,
        professional_type="licensed_auditor",
        tax_registration_number=tax_number,
        business_address="رام الله",
        email_verified_at=timezone.now(),
    )
    return user


def api_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


class PracticeApiBase(TestCase):
    def setUp(self):
        cache.clear()  # عدّادات الـthrottle بين الاختبارات
        self.office_a = make_office("api-office-a", "TAX-API-A")
        self.office_b = make_office("api-office-b", "TAX-API-B")
        self.api_a = api_for(self.office_a)
        self.api_b = api_for(self.office_b)


class PracticeClientApiTest(PracticeApiBase):
    def test_the_full_client_cycle_works_over_http(self):
        created = self.api_a.post(
            f"{BASE}/clients/",
            {"trade_name": "مخبز النور", "phone": "0599", "sector": "أغذية"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content[:300])
        client_id = created.json()["client"]["id"]

        listed = self.api_a.get(f"{BASE}/clients/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 1)
        self.assertEqual(listed.json()["results"][0]["trade_name"], "مخبز النور")

        detail = self.api_a.get(f"{BASE}/clients/{client_id}/")
        self.assertEqual(detail.json()["client"]["phone"], "0599")

        patched = self.api_a.patch(
            f"{BASE}/clients/{client_id}/", {"phone": "0567"}, format="json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["client"]["phone"], "0567")

        # الحذف أرشفة: الصفّ باقٍ ويعود بـrestore.
        archived = self.api_a.delete(f"{BASE}/clients/{client_id}/")
        self.assertEqual(archived.status_code, 200)
        self.assertEqual(archived.json()["client"]["status"], "archived")
        self.assertTrue(PracticeClient.objects.filter(pk=client_id).exists())
        self.assertEqual(
            self.api_a.get(f"{BASE}/clients/?status=active").json()["count"], 0,
        )
        restored = self.api_a.post(f"{BASE}/clients/{client_id}/restore/")
        self.assertEqual(restored.json()["client"]["status"], "active")

    def test_a_missing_trade_name_is_a_400_in_arabic(self):
        response = self.api_a.post(f"{BASE}/clients/", {"trade_name": " "}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_client")
        self.assertEqual(response.json()["detail"], "الاسم التجاري مطلوب.")

    def test_another_office_gets_a_miss_not_a_forbidden_on_every_client_route(self):
        client_id = self.api_a.post(
            f"{BASE}/clients/", {"trade_name": "زبون مكتب أ"}, format="json",
        ).json()["client"]["id"]

        for response in (
            self.api_b.get(f"{BASE}/clients/{client_id}/"),
            self.api_b.patch(f"{BASE}/clients/{client_id}/", {"phone": "0"}, format="json"),
            self.api_b.delete(f"{BASE}/clients/{client_id}/"),
            self.api_b.post(f"{BASE}/clients/{client_id}/restore/"),
        ):
            self.assertEqual(response.status_code, 404, response.content[:300])
            self.assertEqual(response.json()["code"], "client_not_found")
        self.assertEqual(self.api_b.get(f"{BASE}/clients/").json()["count"], 0)
        PracticeClient.objects.get(pk=client_id)  # لم يُمسّ

    def test_a_user_without_a_professional_profile_never_sees_the_surface(self):
        plain = User.objects.create_user("plain-api-user")

        response = api_for(plain).get(f"{BASE}/clients/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "accountant_profile_required")

    def test_an_anonymous_request_is_refused(self):
        response = APIClient().get(f"{BASE}/clients/")

        self.assertIn(response.status_code, (401, 403))


class PracticeProgramAndTaskApiTest(PracticeApiBase):
    def setUp(self):
        super().setUp()
        self.client_id = self.api_a.post(
            f"{BASE}/clients/", {"trade_name": "معرض السلام"}, format="json",
        ).json()["client"]["id"]

    def test_the_full_program_cycle_works_over_http(self):
        created = self.api_a.post(
            f"{BASE}/programs/",
            {"client_id": self.client_id, "service_type": "رواتب", "due_date": "2026-09-01"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content[:300])
        program_id = created.json()["program"]["id"]
        self.assertEqual(created.json()["program"]["client_name"], "معرض السلام")

        listed = self.api_a.get(f"{BASE}/programs/?client_id={self.client_id}")
        self.assertEqual(listed.json()["count"], 1)

        patched = self.api_a.patch(
            f"{BASE}/programs/{program_id}/", {"status": "done"}, format="json",
        )
        self.assertEqual(patched.json()["program"]["status"], "done")

        deleted = self.api_a.delete(f"{BASE}/programs/{program_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(PracticeProgram.objects.filter(pk=program_id).exists())

    def test_an_unknown_service_type_is_422_until_it_is_configured(self):
        response = self.api_a.post(
            f"{BASE}/programs/",
            {"client_id": self.client_id, "service_type": "خدمة لم تُعرَّف"},
            format="json",
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "unknown_service_type")

    def test_another_office_cannot_touch_a_program(self):
        program_id = self.api_a.post(
            f"{BASE}/programs/",
            {"client_id": self.client_id, "service_type": "رواتب"},
            format="json",
        ).json()["program"]["id"]

        for response in (
            self.api_b.patch(f"{BASE}/programs/{program_id}/", {"status": "done"}, format="json"),
            self.api_b.delete(f"{BASE}/programs/{program_id}/"),
        ):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], "program_not_found")
        self.assertEqual(self.api_b.get(f"{BASE}/programs/").json()["count"], 0)
        self.assertTrue(PracticeProgram.objects.filter(pk=program_id).exists())

    def test_the_full_task_cycle_works_over_http(self):
        created = self.api_a.post(
            f"{BASE}/tasks/",
            {"title": "زيارة الزبون", "due_at": "2026-09-05", "kind": "appointment"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content[:300])
        task_id = created.json()["task"]["id"]

        self.assertEqual(self.api_a.get(f"{BASE}/tasks/").json()["count"], 1)
        done = self.api_a.patch(f"{BASE}/tasks/{task_id}/", {"status": "done"}, format="json")
        self.assertEqual(done.json()["task"]["status"], "done")
        self.assertEqual(self.api_a.delete(f"{BASE}/tasks/{task_id}/").status_code, 204)
        self.assertFalse(PracticeTask.objects.filter(pk=task_id).exists())

    def test_another_office_cannot_touch_a_task(self):
        task_id = self.api_a.post(
            f"{BASE}/tasks/", {"title": "اجتماع", "due_at": "2026-09-05"}, format="json",
        ).json()["task"]["id"]

        response = self.api_b.delete(f"{BASE}/tasks/{task_id}/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "task_not_found")
        self.assertTrue(PracticeTask.objects.filter(pk=task_id).exists())

    def test_the_agenda_merges_the_offices_dues_and_shows_no_other_office(self):
        self.api_a.post(
            f"{BASE}/programs/",
            {"client_id": self.client_id, "service_type": "ض.ق.م شهرية", "due_date": "2026-01-05"},
            format="json",
        )
        self.api_a.post(
            f"{BASE}/tasks/", {"title": "زيارة", "due_at": "2036-01-05"}, format="json",
        )

        agenda = self.api_a.get(f"{BASE}/deadlines/")

        self.assertEqual(agenda.status_code, 200)
        self.assertEqual(agenda.json()["totals"]["count"], 2)
        self.assertEqual(agenda.json()["totals"]["overdue"], 1)
        self.assertEqual(self.api_b.get(f"{BASE}/deadlines/").json()["totals"]["count"], 0)


class PracticeSettingsApiTest(PracticeApiBase):
    def test_settings_read_materializes_defaults_and_patch_narrows_them(self):
        read = self.api_a.get(f"{BASE}/settings/")

        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json()["settings"]["default_program_due_days"], 15)
        self.assertEqual(len(read.json()["settings"]["service_types"]), 4)

        patched = self.api_a.patch(
            f"{BASE}/settings/",
            {"default_program_due_days": 30, "service_types": ["تدقيق", "تدقيق"]},
            format="json",
        )
        self.assertEqual(patched.json()["settings"]["default_program_due_days"], 30)
        self.assertEqual(patched.json()["settings"]["service_types"], ["تدقيق"])
        # إعدادات مكتب أ لا تمسّ مكتب ب.
        self.assertEqual(
            self.api_b.get(f"{BASE}/settings/").json()["settings"]["default_program_due_days"], 15,
        )

    def test_an_out_of_range_window_is_refused(self):
        response = self.api_a.patch(
            f"{BASE}/settings/", {"default_program_due_days": 0}, format="json",
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "invalid_settings")


class PracticeDocumentUploadApiTest(PracticeApiBase):
    def setUp(self):
        super().setUp()
        self.client_id = self.api_a.post(
            f"{BASE}/clients/", {"trade_name": "زبون المستندات"}, format="json",
        ).json()["client"]["id"]

    @patch("cloudinary.uploader.upload")
    def test_uploading_a_document_stores_the_returned_url(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/dd63wjj5x/raw/upload/statement.pdf"
        }
        upload = SimpleUploadedFile("statement.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

        response = self.api_a.post(
            f"{BASE}/documents/upload/",
            {"file": upload, "client_id": self.client_id, "name": "كشف حساب"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.content[:300])
        document = PracticeDocument.objects.get(pk=response.json()["document"]["id"])
        self.assertEqual(document.url, "https://res.cloudinary.com/dd63wjj5x/raw/upload/statement.pdf")
        self.assertEqual(document.name, "كشف حساب")
        self.assertEqual(document.accountant_id, self.office_a.pk)
        self.assertEqual(mock_upload.call_args.kwargs.get("resource_type"), "raw")
        listed = self.api_a.get(f"{BASE}/documents/?client_id={self.client_id}")
        self.assertEqual(listed.json()["count"], 1)

    @patch("cloudinary.uploader.upload")
    def test_an_office_document_is_recorded_under_its_uploader_not_a_company(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/x/raw/upload/ktra_practice_documents/s.pdf",
            "public_id": "ktra_practice_documents/s.pdf",
            "bytes": 4096,
            "resource_type": "raw",
        }
        upload = SimpleUploadedFile("s.pdf", b"%PDF-1.4 fake", content_type="application/pdf")

        self.api_a.post(
            f"{BASE}/documents/upload/",
            {"file": upload, "client_id": self.client_id},
            format="multipart",
        )

        asset = TenantAsset.objects.get(public_id="ktra_practice_documents/s.pdf")
        # مستند المكتب يملكه المحاسب: بايتاته لا تُحمَّل على شركة زبونه
        self.assertIsNone(asset.tenant_id)
        self.assertEqual(asset.uploaded_by_id, self.office_a.pk)
        self.assertEqual(asset.bytes, 4096)
        self.assertEqual(asset.folder, "ktra_practice_documents")

    @patch("cloudinary.uploader.upload")
    def test_the_file_name_stands_in_when_no_name_is_sent(self, mock_upload):
        mock_upload.return_value = {"secure_url": "https://res.cloudinary.com/x/image/upload/p.png"}
        upload = SimpleUploadedFile("p.png", b"\x89PNG fake", content_type="image/png")

        response = self.api_a.post(
            f"{BASE}/documents/upload/",
            {"file": upload, "client_id": self.client_id},
            format="multipart",
        )

        self.assertEqual(response.json()["document"]["name"], "p.png")

    @patch("cloudinary.uploader.upload")
    def test_uploading_to_another_offices_client_is_a_miss_and_never_calls_cloudinary(self, mock_upload):
        upload = SimpleUploadedFile("x.pdf", b"%PDF-1.4", content_type="application/pdf")

        response = self.api_b.post(
            f"{BASE}/documents/upload/",
            {"file": upload, "client_id": self.client_id},
            format="multipart",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "client_not_found")
        # العزل يُفحص **قبل** الرفع — لا رفعٌ يُدفع ثمنه لزبون ليس لك.
        mock_upload.assert_not_called()
        self.assertFalse(PracticeDocument.objects.exists())

    def test_a_missing_file_is_400_before_any_row_is_written(self):
        response = self.api_a.post(
            f"{BASE}/documents/upload/", {"client_id": self.client_id}, format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "missing_file")
        self.assertFalse(PracticeDocument.objects.exists())

    @patch("cloudinary.uploader.upload", side_effect=RuntimeError("cloudinary down"))
    def test_a_failed_upload_leaves_no_document_behind(self, _mock_upload):
        upload = SimpleUploadedFile("y.pdf", b"%PDF-1.4", content_type="application/pdf")

        response = self.api_a.post(
            f"{BASE}/documents/upload/",
            {"file": upload, "client_id": self.client_id},
            format="multipart",
        )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(PracticeDocument.objects.exists())

    @patch("cloudinary.uploader.upload")
    def test_a_document_can_be_deleted_by_its_office_only(self, mock_upload):
        mock_upload.return_value = {"secure_url": "https://res.cloudinary.com/x/raw/upload/d.pdf"}
        upload = SimpleUploadedFile("d.pdf", b"%PDF-1.4", content_type="application/pdf")
        document_id = self.api_a.post(
            f"{BASE}/documents/upload/",
            {"file": upload, "client_id": self.client_id},
            format="multipart",
        ).json()["document"]["id"]

        refused = self.api_b.delete(f"{BASE}/documents/{document_id}/")
        self.assertEqual(refused.status_code, 404)
        self.assertEqual(refused.json()["code"], "document_not_found")
        self.assertTrue(PracticeDocument.objects.filter(pk=document_id).exists())

        self.assertEqual(self.api_a.delete(f"{BASE}/documents/{document_id}/").status_code, 204)
        self.assertFalse(PracticeDocument.objects.filter(pk=document_id).exists())


@override_settings(ACCOUNTANT_PRACTICE_ENABLED=False)
class PracticeFlagOffTest(PracticeApiBase):
    """العَلَم مُطفأ ⇒ السطح غير موجود — 404 لا 403، ولا حتى للمحاسب نفسه."""

    def test_every_practice_route_is_404_when_the_flag_is_off(self):
        for method, path in PRACTICE_ROUTES:
            with self.subTest(route=f"{method.upper()} {path}"):
                response = getattr(self.api_a, method)(path, {}, format="json")
                self.assertEqual(response.status_code, 404, response.content[:200])

    def test_the_pre_existing_portal_routes_stay_untouched_by_the_flag(self):
        # العَلَم يخصّ سطح المكتب الجديد وحده؛ بوابة الارتباطات القائمة لا تتأثر.
        self.assertEqual(self.api_a.get("/api/accountant/me/").status_code, 200)
        self.assertEqual(self.api_a.get("/api/accountant/practice/overview/").status_code, 200)
