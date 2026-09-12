"""بطاقةُ الموظّف الشخصيّة: الصورة والهاتف والمسمّى الوظيفيّ (التذكرة 211-Q).

`job_title` **حقلٌ منفصلٌ** عن `specialty` عمداً — ذاك مفتاحُ سياسةٍ يُطابَق
بـ`PolicyProfile.specialty` في احتساب الأداء، فإعادةُ استعمالِه للعرض تُبدّل
سياسةَ تقييم الموظّف بصمت. الاختباراتُ هنا تغطي: المديرَ يضبط الثلاثة، والموظّفَ
يضبط صورتَه وهاتفَه وحدَهما، ومحاولتَه المسمّى تُرَدّ 403 بلا أثرٍ في القاعدة،
وموظّفاً آخر يُرَدّ 404 لا 403 (`get_queryset` يضيّق قبل الفعل أصلاً)، ورفعَ
الصورة بـ`tenant=None` محفوظاً في الصفّ.
"""
import json
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import PlatformActivityLog, PlatformEmployee
from platform_ops.serializers import PlatformEmployeeSerializer
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class ProfileCardEndpointTest(PilotScenarioBase):
    def _url(self, employee=None):
        return reverse("platform-ops-employees-profile-card", args=[(employee or self.employee).pk])

    def test_manager_sets_all_three_fields(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.patch(
            self._url(),
            {"photo_url": "https://res.cloudinary.com/demo/photo.jpg", "phone": "0599123456", "job_title": "مسؤول إدخال بيانات"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.photo_url, "https://res.cloudinary.com/demo/photo.jpg")
        self.assertEqual(self.employee.phone, "0599123456")
        self.assertEqual(self.employee.job_title, "مسؤول إدخال بيانات")

    def test_employee_sets_only_photo_and_phone(self):
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        response = client.patch(
            self._url(),
            {"photo_url": "https://res.cloudinary.com/demo/me.jpg", "phone": "0501112222"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.photo_url, "https://res.cloudinary.com/demo/me.jpg")
        self.assertEqual(self.employee.phone, "0501112222")

    def test_employee_cannot_set_job_title_and_the_value_is_unchanged_in_db(self):
        """التحقّقُ من القاعدة لا من الردّ وحدَه — الردُّ قد يكذب، القاعدةُ لا."""
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        response = client.patch(self._url(), {"job_title": "مديرٌ عام"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "job_title_is_manager_only")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.job_title, "")

    def test_an_employee_cannot_reach_another_employees_card(self):
        other = PlatformEmployee.objects.create(
            user=self.admin, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        response = client.patch(self._url(other), {"phone": "0500000000"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_change_is_logged_with_before_and_after(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        client.patch(self._url(), {"phone": "0599999999"}, format="json")
        log = PlatformActivityLog.objects.filter(entity_type="employee_profile_card").order_by("-id").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.details.get("operation"), "set_employee_profile_card")
        self.assertEqual(log.details["before"]["phone"], "")
        self.assertEqual(log.details["after"]["phone"], "0599999999")
        self.assertNotIn("job_title", log.details["after"], "سُجِّل حقلٌ لم يُمَسّ.")

    def test_wire_payload_reflects_updated_fields(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.patch(self._url(), {"job_title": "محلّل بيانات"}, format="json")
        wire = json.loads(response.content.decode("utf-8"))
        self.assertEqual(wire["job_title"], "محلّل بيانات")


class ProfilePhotoUploadEndpointTest(PilotScenarioBase):
    def _url(self, employee=None):
        return reverse("platform-ops-employees-photo", args=[(employee or self.employee).pk])

    def _fake_upload(self, employee=None):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("me.jpg", b"binarydata", content_type="image/jpeg")
        client = APIClient()
        client.force_authenticate(user=employee or self.staff_user)
        with patch("platform_ops.views.upload_media_file") as mocked:
            mocked.return_value = "https://res.cloudinary.com/demo/uploaded.jpg"
            response = client.post(self._url(), {"file": upload}, format="multipart")
        return response, mocked

    def test_upload_calls_the_shared_media_service_with_tenant_none_and_saves_the_row(self):
        response, mocked = self._fake_upload()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["photo_url"], "https://res.cloudinary.com/demo/uploaded.jpg")
        mocked.assert_called_once()
        call_kwargs = mocked.call_args.kwargs
        self.assertIsNone(call_kwargs["tenant"])
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.photo_url, "https://res.cloudinary.com/demo/uploaded.jpg")

    def test_manager_can_upload_for_another_employee(self):
        response, _mocked = self._fake_upload(employee=self.admin)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ProfileCardValidationTest(PilotScenarioBase):
    """القيدُ المُعلَن في النموذج يجب أن يُنفَّذ فعلاً — لا أن يبقى توثيقاً.

    `save()` لا يستدعي المدقّقات، فقيمةٌ أطولُ من `max_length` تمرّ في SQLite
    صامتةً (قاعدةُ الاختبارات) وتصطدم في MySQL بـ1406 في وجه المستخدم. فالبوّابةُ
    الخضراءُ هنا كانت تُخفي خمسمئةً هناك.
    """

    def _url(self):
        return reverse("platform-ops-employees-profile-card", args=[self.employee.pk])

    def _patch(self, payload):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        return client.patch(self._url(), payload, format="json")

    def test_a_phone_longer_than_the_column_is_rejected_not_stored(self):
        response = self._patch({"phone": "0" * 40})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_profile_field")
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.phone, "", "خُزِّنت قيمةٌ تتجاوز طولَ العمود.")

    def test_a_job_title_longer_than_the_column_is_rejected(self):
        response = self._patch({"job_title": "م" * 200})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.job_title, "")

    def test_a_value_that_is_not_a_url_is_rejected_for_the_photo(self):
        response = self._patch({"photo_url": "javascript:alert(1)"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.photo_url, "")

    def test_clearing_the_photo_with_an_empty_string_still_works(self):
        """الفراغُ ليس قيمةً غيرَ صالحة — الحقلُ `blank=True` ومسحُ الصورة مشروع."""
        self.employee.photo_url = "https://res.cloudinary.com/demo/x.jpg"
        self.employee.save(update_fields=["photo_url"])
        response = self._patch({"photo_url": ""})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.photo_url, "")


class DashboardCarriesTheProfileCardTest(PilotScenarioBase):
    """الصورةُ والمسمّى يصلان **حمولةَ اللوحة** لا نقطةَ الموظّف وحدَها.

    الغرفةُ وبطاقةُ اللوحة تُرسمان من `get_platform_dashboard_summary`؛ فحقلٌ
    غائبٌ عنها يعني صورةً محفوظةً في القاعدة لا يراها أحد، ووجهاً بأحرفٍ أولى
    على المقعد — وهو بعينه ما طلبه المالك أن يظهر.
    """

    def test_the_dashboard_employee_card_carries_photo_and_job_title(self):
        from platform_ops.services import get_platform_dashboard_summary

        self.employee.photo_url = "https://res.cloudinary.com/demo/face.jpg"
        self.employee.job_title = "مسؤول مبيعات أول"
        self.employee.save(update_fields=["photo_url", "job_title"])

        summary = get_platform_dashboard_summary(user=self.admin)
        card = next(c for c in summary["employees"] if c["id"] == self.employee.pk)
        self.assertEqual(card["photo_url"], "https://res.cloudinary.com/demo/face.jpg")
        self.assertEqual(card["job_title"], "مسؤول مبيعات أول")


class ProfileCardSerializerTest(PilotScenarioBase):
    def test_serializer_returns_the_three_new_fields(self):
        self.employee.photo_url = "https://res.cloudinary.com/demo/x.jpg"
        self.employee.phone = "0500000001"
        self.employee.job_title = "مسؤول جودة"
        self.employee.save(update_fields=["photo_url", "phone", "job_title"])
        data = PlatformEmployeeSerializer(self.employee).data
        self.assertEqual(data["photo_url"], "https://res.cloudinary.com/demo/x.jpg")
        self.assertEqual(data["phone"], "0500000001")
        self.assertEqual(data["job_title"], "مسؤول جودة")
