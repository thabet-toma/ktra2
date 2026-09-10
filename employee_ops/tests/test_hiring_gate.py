"""بوابةُ التوظيف — الرابطُ العامّ والتقديمُ وشروطُ الأمان الستّة (المرحلة ٧).

**لماذا هذا الملفّ أطولُ من إخوته:** هذه النقطةُ الوحيدةُ في الوحدة التي يبلغها
**مجهولٌ بلا حساب**، ويرفع فيها ملفاً. والرفعُ المجهول كان في هذه المنصة
و**أُزيل عمداً** لأنّ زائراً واحداً يقفل الـworkers الثلاثة برفعٍ متزامن — فصفحةُ
السيرة تعيد فتحَ البابِ نفسِه، ولا تُفتح إلا بحرّاسٍ مُختبَرين.

وكلُّ اختبارٍ هنا يسأل: **ما العطبُ الذي يجعله يسقط؟** — والجوابُ مكتوبٌ فيه.
"""
import io
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from rest_framework.test import APITestCase

from core.access import FIELD_STAFF_ROLE
from core.models import TenantModule
from core.modules import invalidate_module_cache
from employee_ops.hiring import (
    MAX_APPLICATION_BYTES,
    MAX_CV_BYTES,
    sniff_content_type,
)
from employee_ops.models import JobApplicant, JobPosting
from hr.models import Employee
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

PDF_HEAD = b"%PDF-1.7\n"
PNG_HEAD = b"\x89PNG\r\n\x1a\n"


def pdf_file(name="cv.pdf", size=2048):
    body = PDF_HEAD + b"0" * max(0, size - len(PDF_HEAD))
    return SimpleUploadedFile(name, body, content_type="application/pdf")


class HiringBaseTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager = User.objects.create_user(username="hire_mgr", password="x")
        cls.tenant = create_company("شركة التوظيف", cls.manager)
        TenantModule.objects.create(
            tenant=cls.tenant, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(cls.tenant.pk)

        cls.staff_user = User.objects.create_user(username="hire_staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff_user, tenant=cls.tenant, role=FIELD_STAFF_ROLE
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    @property
    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def make_job(self, **overrides):
        payload = {"title": "مندوب مبيعات", "description": "وصف الوظيفة"}
        payload.update(overrides)
        res = self.client.post(
            "/api/employee-ops/jobs/", payload, format="json", **self.headers
        )
        self.assertEqual(res.status_code, 201, res.data)
        return res.data


class JobPostingTest(HiringBaseTest):
    def test_creating_a_job_mints_an_unguessable_link(self):
        job = self.make_job()
        # `token_urlsafe(32)` = ٤٣ محرفاً. معرّفٌ متسلسلٌ يُخمَّن بالعدّ، فيصير
        # «رابطٌ لوظيفةٍ واحدة» جولةً على وظائف الشركات كلِّها.
        self.assertGreaterEqual(len(job["token"]), 40)

        # والخاصّيّةُ التي تهمّ فعلاً: **المعرّفُ المتسلسل لا يبلغ الوظيفة**.
        # (المطابقةُ النصّيّةُ بين الرقم والمفتاح عبثٌ — مفتاحٌ عشوائيٌّ من ٤٣
        # محرفاً يحوي الرقم «1» صدفةً في أغلب الأحيان، فتأكيدٌ عليها يسقط بلا
        # عطبٍ ويمرّ بلا حراسة.)
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(
                f"/api/employee-ops/public/jobs/{job['id']}/"
            ).status_code,
            404,
            "الوصولُ بالمعرّف المتسلسل يجب أن يفشل",
        )

    def test_two_jobs_never_share_a_link(self):
        self.assertNotEqual(self.make_job()["token"], self.make_job()["token"])

    def test_regenerating_the_token_kills_the_old_link_immediately(self):
        job = self.make_job()
        old_token = job["token"]
        res = self.client.post(
            f"/api/employee-ops/jobs/{job['id']}/regenerate-token/",
            {}, format="json", **self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertNotEqual(res.data["token"], old_token)

        self.client.force_authenticate(user=None)
        gone = self.client.get(f"/api/employee-ops/public/jobs/{old_token}/")
        self.assertEqual(gone.status_code, 404, "الرابطُ القديم يجب أن يموت فوراً")

    def test_an_expiry_in_the_past_is_refused_at_creation(self):
        """رابطٌ ميّتٌ لحظةَ إنشائه لا يُكتشَف لاحقاً — يُمنع عند الكتابة."""
        res = self.client.post(
            "/api/employee-ops/jobs/",
            {
                "title": "وظيفة",
                "description": "وصف",
                "expires_at": (timezone.now() - timedelta(days=1)).isoformat(),
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 400)

    def test_a_job_with_applicants_cannot_be_deleted(self):
        """الحذفُ يمحو بياناتِ أشخاصٍ لم يخطئوا؛ الإغلاقُ يفعل ما أراده المالك."""
        job = self.make_job()
        self.client.force_authenticate(user=None)
        self.client.post(
            f"/api/employee-ops/public/jobs/{job['token']}/apply/",
            {"name": "متقدم", "phone": "0599"}, format="multipart",
        )
        self.client.force_authenticate(user=self.manager)
        res = self.client.delete(
            f"/api/employee-ops/jobs/{job['id']}/", **self.headers
        )
        self.assertEqual(res.status_code, 400)
        self.assertTrue(JobPosting.objects.filter(pk=job["id"]).exists())

    def test_a_field_staff_cannot_see_or_touch_jobs(self):
        """الوظائفُ خلف `employee_ops.manage` — و`employee_ops.self` لا يكفي."""
        self.client.force_authenticate(user=self.staff_user)
        for method, path in (
            ("get", "/api/employee-ops/jobs/"),
            ("get", "/api/employee-ops/applicants/"),
        ):
            res = getattr(self.client, method)(path, **self.headers)
            self.assertEqual(res.status_code, 403, f"{path} ردّ {res.status_code}")


class PublicJobLinkTest(HiringBaseTest):
    def test_an_open_job_is_readable_without_any_login(self):
        job = self.make_job(location="رام الله")
        self.client.force_authenticate(user=None)
        res = self.client.get(f"/api/employee-ops/public/jobs/{job['token']}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["title"], "مندوب مبيعات")
        self.assertEqual(res.data["location"], "رام الله")

    def test_the_public_payload_carries_nothing_but_the_posting(self):
        """قائمةٌ بيضاءُ صريحة: لا مفتاحٌ ولا معرّفٌ ولا شركةٌ ولا عددُ متقدّمين.

        كم تقدّم على وظيفةٍ معلومةٌ تجاريّةٌ لصاحبها لا لكلّ من فتح الرابط.
        """
        job = self.make_job()
        self.client.force_authenticate(user=None)
        res = self.client.get(f"/api/employee-ops/public/jobs/{job['token']}/")
        self.assertEqual(
            set(res.data.keys()),
            {
                "title", "description", "requirements",
                "location", "employment_type", "salary_range",
            },
        )

    def test_a_closed_job_answers_410_not_404(self):
        """الفرقُ بين «كان هنا وانتهى» و«لم يكن هنا قطّ» يهمّ من فتح الرابط."""
        job = self.make_job()
        self.client.post(
            f"/api/employee-ops/jobs/{job['id']}/close/", {}, format="json", **self.headers
        )
        self.client.force_authenticate(user=None)
        res = self.client.get(f"/api/employee-ops/public/jobs/{job['token']}/")
        self.assertEqual(res.status_code, 410)

    def test_an_expired_job_answers_410_too(self):
        job = self.make_job()
        JobPosting.objects.filter(pk=job["id"]).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        self.client.force_authenticate(user=None)
        res = self.client.get(f"/api/employee-ops/public/jobs/{job['token']}/")
        self.assertEqual(res.status_code, 410)

    def test_a_job_with_no_expiry_never_expires(self):
        """الأجلُ اختياريّ: إعلانٌ يُنشر مرّةً ويُنسى، وانتهاءٌ إجباريٌّ يقتله بصمت."""
        job = self.make_job()
        self.assertIsNone(job["expires_at"])
        self.client.force_authenticate(user=None)
        res = self.client.get(f"/api/employee-ops/public/jobs/{job['token']}/")
        self.assertEqual(res.status_code, 200)

    def test_a_token_that_never_existed_answers_404(self):
        self.client.force_authenticate(user=None)
        res = self.client.get("/api/employee-ops/public/jobs/nope-nope-nope/")
        self.assertEqual(res.status_code, 404)


class PublicApplicationTest(HiringBaseTest):
    def _apply(self, token, **payload):
        data = {"name": "سائل", "phone": "0599123456"}
        data.update(payload)
        return self.client.post(
            f"/api/employee-ops/public/jobs/{token}/apply/", data, format="multipart"
        )

    def test_an_anonymous_application_is_quarantined_as_new(self):
        """**الشرط ٥** — لا يمسّ شيئاً غير جدولِه: لا موظفٌ ولا مقعدٌ ولا دعوة."""
        job = self.make_job()
        employees_before = Employee.objects.count()
        self.client.force_authenticate(user=None)

        res = self._apply(job["token"], about="نبذة")
        self.assertEqual(res.status_code, 201, res.data)

        applicant = JobApplicant.objects.get()
        self.assertEqual(applicant.status, JobApplicant.STATUS_NEW)
        self.assertEqual(applicant.tenant_id, self.tenant.pk)
        self.assertIsNone(applicant.hired_employee_id)
        self.assertEqual(Employee.objects.count(), employees_before)

    def test_the_thank_you_screen_gets_a_reference_and_nothing_else(self):
        """لا معرّفٌ داخليّ ولا اسمُ شركةٍ ولا رابطُ سيرة."""
        job = self.make_job()
        self.client.force_authenticate(user=None)
        res = self._apply(job["token"])
        self.assertEqual(set(res.data.keys()), {"reference_code"})
        self.assertTrue(res.data["reference_code"])

    def test_the_applicant_cannot_choose_their_own_status_or_rating(self):
        """حقلٌ يقبله المُسلسِل بابٌ يُفتح — والحالةُ محجورةٌ في الخدمة."""
        job = self.make_job()
        self.client.force_authenticate(user=None)
        res = self._apply(job["token"], status="hired", rating="5")
        self.assertEqual(res.status_code, 201)
        applicant = JobApplicant.objects.get()
        self.assertEqual(applicant.status, JobApplicant.STATUS_NEW)
        self.assertEqual(applicant.rating, 0)

    def test_name_and_phone_are_the_only_mandatory_fields(self):
        job = self.make_job()
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.post(
                f"/api/employee-ops/public/jobs/{job['token']}/apply/",
                {"phone": "0599"}, format="multipart",
            ).status_code, 400,
        )
        self.assertEqual(
            self.client.post(
                f"/api/employee-ops/public/jobs/{job['token']}/apply/",
                {"name": "بلا رقم"}, format="multipart",
            ).status_code, 400,
        )
        # وبلا سيرةٍ ولا بريدٍ ولا نبذةٍ يمرّ: الإلزامُ يخسر متقدّمين ويشتري خطراً.
        self.assertEqual(self._apply(job["token"]).status_code, 201)

    def test_applying_to_a_closed_job_answers_410(self):
        job = self.make_job()
        self.client.post(
            f"/api/employee-ops/jobs/{job['id']}/close/", {}, format="json", **self.headers
        )
        self.client.force_authenticate(user=None)
        self.assertEqual(self._apply(job["token"]).status_code, 410)
        self.assertEqual(JobApplicant.objects.count(), 0)

    def test_a_module_that_is_off_closes_reading_and_writing_alike(self):
        """الترخيصُ سُحب ⇒ **٤١٠ للقراءة والكتابة معاً**.

        كانت القراءةُ تبقى مفتوحةً والكتابةُ وحدها تُغلق، فيرى المتقدّمُ وظيفةً
        حيّةً ويملأ النموذجَ ويرفع سيرةً بخمسة ميجا ثمّ يُقال له «انتهى التقديم».
        الحالةُ المغلقةُ تُرى **قبل** العمل لا بعده.

        ولا يتكدّس متقدّمون في وحدةٍ لا يفتحها المالك: لا هو يراهم ولا هم
        يعرفون أنّهم في العدم.
        """
        job = self.make_job()
        TenantModule.objects.filter(
            tenant=self.tenant, module_key="employee_ops"
        ).update(enabled=False)
        invalidate_module_cache(self.tenant.pk)
        self.client.force_authenticate(user=None)

        self.assertEqual(
            self.client.get(
                f"/api/employee-ops/public/jobs/{job['token']}/"
            ).status_code, 410,
        )
        self.assertEqual(self._apply(job["token"]).status_code, 410)
        self.assertEqual(JobApplicant.objects.count(), 0)

    def test_a_free_text_flood_is_refused(self):
        job = self.make_job()
        self.client.force_authenticate(user=None)
        res = self._apply(job["token"], about="ا" * 6000)
        self.assertEqual(res.status_code, 400)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class ApplyThrottleTest(HiringBaseTest):
    """**الشرط ٣** — خانقٌ خاصٌّ ضيّقٌ على نقطة التقديم.

    فخّان يجعلان اختبارَ خانقٍ **عاجزاً عن السقوط** لو كُتب ساذجاً، وكلاهما
    مُبطَّلٌ هنا صراحةً:

    - كاشُ الاختبارات `DummyCache` لا يخزّن شيئاً، وخانقُ DRF يعدّ في الكاش —
      فبلا `LocMemCache` لا يعدّ أصلاً ولو نُزع الخانقُ كلُّه.
    - و`SimpleRateThrottle.THROTTLE_RATES` **سمةُ صنفٍ تُربط لحظةَ استيراد DRF**،
      فـ`override_settings(REST_FRAMEWORK=...)` لا يبلغها: الصنفُ يبقى ممسكاً
      بالقاموس القديم. لذا يُرقَّع القاموسُ نفسُه.
    """

    def test_the_third_application_from_one_ip_is_refused(self):
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle

        cache.clear()
        job = self.make_job()
        self.client.force_authenticate(user=None)
        path = f"/api/employee-ops/public/jobs/{job['token']}/apply/"

        with mock.patch.dict(
            ScopedRateThrottle.THROTTLE_RATES, {"employee_ops_apply": "2/hour"}
        ):
            codes = [
                self.client.post(
                    path, {"name": "س", "phone": "059"}, format="multipart"
                ).status_code
                for _ in range(3)
            ]

        self.assertEqual(codes[:2], [201, 201])
        self.assertEqual(codes[2], 429, "الطلبُ الثالث يتجاوز 2/hour فيُخنق")
        # والصفُّ الثالث لم يُكتب: الخنقُ يقع قبل العرض لا بعده.
        self.assertEqual(JobApplicant.objects.count(), 2)

    def test_the_apply_scope_is_narrower_than_the_public_read_scope(self):
        """أضيقُ من أضيقِ خانقٍ قائم — كتابةٌ من مجهولٍ لا قراءةٌ تُعاد.

        يسقط هذا لو ساوى أحدٌ النطاقين أو وسّع نطاقَ التقديم يوماً.
        """
        from rest_framework.throttling import ScopedRateThrottle

        rates = ScopedRateThrottle.THROTTLE_RATES

        def per_hour(rate: str) -> float:
            count, _, period = rate.partition("/")
            factor = {"s": 3600.0, "m": 60.0, "h": 1.0, "d": 1 / 24.0}[period[0]]
            return float(count) * factor

        self.assertLess(
            per_hour(rates["employee_ops_apply"]),
            per_hour(rates["employee_ops_job_public"]),
        )
        self.assertLess(
            per_hour(rates["employee_ops_apply"]), per_hour(rates["anon"])
        )


class CvUploadGuardTest(HiringBaseTest):
    """**الشرطان ١ و٢** — الحجمُ والنوعُ، والبايتاتُ هي الحَكَم."""

    def setUp(self):
        super().setUp()
        self.job = self.make_job()
        self.patcher = mock.patch(
            "employee_ops.views.upload_media_file",
            return_value="https://res.cloudinary.com/test/raw/upload/cv.pdf",
        )
        self.upload = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def _apply_with(self, upload):
        self.client.force_authenticate(user=None)
        return self.client.post(
            f"/api/employee-ops/public/jobs/{self.job['token']}/apply/",
            {"name": "س", "phone": "059", "cv": upload},
            format="multipart",
        )

    def test_a_valid_pdf_is_accepted_and_stored(self):
        res = self._apply_with(pdf_file())
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(JobApplicant.objects.get().cv_url)
        self.assertTrue(self.upload.called)

    def test_a_file_over_five_megabytes_never_reaches_the_provider(self):
        """الحجمُ يُفحص **قبل** الرفع: رفضٌ بعد الرفع يكون قد دفع ثمنَه.

        واسمُه «المزوّد» لا «التخزين»: الجسمُ يكون قد بلغ قرصَ الخادم المؤقّتَ
        قبل هذه النقطة — وحارسُ ذلك `CONTENT_LENGTH` في `AnonymousUploadDosTest`.
        """
        big = SimpleUploadedFile(
            "cv.pdf", PDF_HEAD + b"0" * (MAX_CV_BYTES + 1), content_type="application/pdf"
        )
        res = self._apply_with(big)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(self.upload.called, "لم يكن يجوز أن يبلغ المخنق")
        self.assertEqual(JobApplicant.objects.count(), 0)

    def test_a_forbidden_extension_is_refused(self):
        evil = SimpleUploadedFile(
            "payload.exe", b"MZ\x90\x00", content_type="application/pdf"
        )
        res = self._apply_with(evil)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(self.upload.called)

    def test_a_forbidden_content_type_is_refused(self):
        weird = SimpleUploadedFile(
            "cv.pdf", PDF_HEAD, content_type="application/x-msdownload"
        )
        self.assertEqual(self._apply_with(weird).status_code, 400)
        self.assertFalse(self.upload.called)

    def test_an_extension_that_disagrees_with_its_declared_type_is_refused(self):
        mismatched = SimpleUploadedFile("cv.pdf", PDF_HEAD, content_type="image/png")
        self.assertEqual(self._apply_with(mismatched).status_code, 400)
        self.assertFalse(self.upload.called)

    def test_a_renamed_executable_declaring_pdf_is_caught_by_its_bytes(self):
        """**الحارسُ الوحيد الذي لا يُلفَّق.**

        الاسمُ `cv.pdf` والترويسةُ `application/pdf` — كلاهما يكتبه الرافع. لولا
        فحصِ البايتات لمرّ هذا الملفّ إلى التخزين بامتيازٍ كامل.
        """
        disguised = SimpleUploadedFile(
            "cv.pdf", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/pdf"
        )
        res = self._apply_with(disguised)
        self.assertEqual(res.status_code, 400, "بايتاتُ EXE خلف اسمِ PDF يجب أن تُردّ")
        self.assertFalse(self.upload.called)
        self.assertEqual(JobApplicant.objects.count(), 0)

    def test_a_png_renamed_to_pdf_is_caught_too(self):
        """ليس EXE وحده: أيُّ تناقضٍ بين الامتداد والمحتوى يُردّ."""
        disguised = SimpleUploadedFile(
            "cv.pdf", PNG_HEAD + b"0" * 64, content_type="application/pdf"
        )
        self.assertEqual(self._apply_with(disguised).status_code, 400)
        self.assertFalse(self.upload.called)

    def test_the_sniffer_knows_each_allowed_type(self):
        self.assertEqual(sniff_content_type(b"%PDF-1.4"), "application/pdf")
        self.assertEqual(sniff_content_type(b"\xff\xd8\xff\xe0"), "image/jpeg")
        self.assertEqual(sniff_content_type(PNG_HEAD), "image/png")
        self.assertEqual(
            sniff_content_type(b"RIFF\x00\x00\x00\x00WEBP"), "image/webp"
        )
        self.assertIsNone(sniff_content_type(b"MZ\x90\x00"))
        self.assertIsNone(sniff_content_type(b""))


class CvReadIsGuardedTest(HiringBaseTest):
    """**الشرط ٦** — السيرةُ خلف صلاحية، ورابطُ التخزين لا يُسلَّم لأحد."""

    CV_URL = "https://res.cloudinary.com/test/raw/upload/secret-cv.pdf"

    def setUp(self):
        super().setUp()
        job = JobPosting.objects.create(
            tenant=self.tenant, title="وظيفة", description="وصف", token="tok-cv"
        )
        self.applicant = JobApplicant.objects.create(
            tenant=self.tenant, job=job, name="متقدم", phone="0599",
            cv_url=self.CV_URL, cv_name="cv.pdf", reference_code="REF1",
        )

    def test_no_manager_response_ever_carries_the_storage_url(self):
        """الردُّ يُخزَّن في سجلّ متصفّحٍ ويُنسخ في رسالة — والرابطُ **هو** الصلاحية.

        فمن يقرأ الرابطَ يقرأ سيرةَ إنسانٍ خارج الشركة كائناً من كان.
        """
        listing = self.client.get("/api/employee-ops/applicants/", **self.headers)
        detail = self.client.get(
            f"/api/employee-ops/applicants/{self.applicant.pk}/", **self.headers
        )
        for res in (listing, detail):
            self.assertEqual(res.status_code, 200)
            self.assertNotIn(self.CV_URL, str(res.data))
            self.assertNotIn("cv_url", str(res.data))

        # وتعرف الشاشةُ أنّ هناك ملفاً بلا أن تعرف أين هو.
        self.assertTrue(listing.data[0]["has_cv"])
        self.assertEqual(listing.data[0]["cv_name"], "cv.pdf")

    def test_the_cv_is_streamed_through_the_server_never_as_a_link(self):
        """**بايتاتٌ لا إعادةُ توجيه.**

        كان الردُّ ٣٠٢ وترويسةُ `Location` تحمل رابطَ التخزين حرفيّاً — أي أنّ
        الردَّ كان يحمل ما تقول المواصفةُ إنّه «لا يُسلَّم بأيّ حال»، ويبقى في
        سجلّ المتصفّح صالحاً للنسخ بعد انتهاء الجلسة. يسقط هذا الاختبارُ لحظةَ
        عودةِ إعادة التوجيه.
        """
        with mock.patch("employee_ops.views.requests.get") as fetch:
            fetch.return_value = mock.Mock(
                raw=io.BytesIO(b"%PDF-1.7 fake"),
                headers={"Content-Type": "application/pdf"},
                raise_for_status=mock.Mock(),
            )
            res = self.client.get(
                f"/api/employee-ops/applicants/{self.applicant.pk}/cv/", **self.headers
            )

        self.assertEqual(res.status_code, 200)
        self.assertNotIn("Location", res)
        self.assertNotIn(self.CV_URL, str(dict(res.items())))
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertIn("inline", res["Content-Disposition"])
        self.assertEqual(b"".join(res.streaming_content), b"%PDF-1.7 fake")

    def test_a_field_staff_cannot_reach_the_cv(self):
        self.client.force_authenticate(user=self.staff_user)
        res = self.client.get(
            f"/api/employee-ops/applicants/{self.applicant.pk}/cv/", **self.headers
        )
        self.assertEqual(res.status_code, 403)

    def test_an_anonymous_visitor_cannot_reach_the_cv(self):
        self.client.force_authenticate(user=None)
        res = self.client.get(f"/api/employee-ops/applicants/{self.applicant.pk}/cv/")
        self.assertIn(res.status_code, (401, 403, 404))

    def test_another_company_cannot_reach_the_cv(self):
        other_mgr = User.objects.create_user(username="hire_mgr_b", password="x")
        other = create_company("شركة أخرى", other_mgr)
        TenantModule.objects.create(
            tenant=other, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(other.pk)
        self.client.force_authenticate(user=other_mgr)
        res = self.client.get(
            f"/api/employee-ops/applicants/{self.applicant.pk}/cv/",
            HTTP_X_TENANT_ID=str(other.pk),
        )
        self.assertEqual(res.status_code, 404)


class AnonymousUploadDosTest(HiringBaseTest):
    """**العطبُ الذي أُزيل لأجله الرفعُ المجهول من هذه المنصة أصلاً.**

    زائرٌ واحدٌ برفعٍ متزامنٍ يقفل الـworkers الثلاثة، وسجلُّ المستودع يحمل ذلك
    قراراً موثّقاً (`core/media_views.py`: «لا رفع مجهول — يقفل الـworker»).
    """

    def test_a_body_above_the_cap_is_refused_before_it_is_parsed(self):
        """`CONTENT_LENGTH` قبل `request.data`.

        الفحصُ السابقُ كان على `validated_data`، أي **بعد** أن يحلّل جانغو الجسمَ
        كلَّه ويسكب ما فوق 2.5MB على قرص الخادم: طلبٌ بسيرةٍ سليمةٍ من ٢ كيلوبايت
        و٩٩ حقلاً حشواً بمئات الميجات كان يمرّ من كلّ فحوصنا.
        """
        job = self.make_job()
        self.client.force_authenticate(user=None)
        res = self.client.post(
            f"/api/employee-ops/public/jobs/{job['token']}/apply/",
            {"name": "س", "phone": "059"},
            format="multipart",
            CONTENT_LENGTH=str(MAX_APPLICATION_BYTES + 1),
        )
        self.assertEqual(res.status_code, 413)
        self.assertEqual(JobApplicant.objects.count(), 0)

    def test_a_normal_body_is_not_refused(self):
        """وإلا كان الاختبارُ أعلاه يمرّ لأنّ كلَّ طلبٍ يُردّ ٤١٣."""
        job = self.make_job()
        self.client.force_authenticate(user=None)
        res = self.client.post(
            f"/api/employee-ops/public/jobs/{job['token']}/apply/",
            {"name": "س", "phone": "059"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201)


class ThrottleIdentityCannotBeForgedTest(HiringBaseTest):
    """**الشرط ٣ يصير زينةً إن كانت الهويّةُ ترويسةً يكتبها العميل.**

    `NUM_PROXIES` غيرُ مضبوطٍ افتراضياً، وعندها يبني DRF الهويّةَ من كامل
    `X-Forwarded-For` — فترويسةٌ جديدةٌ لكلّ طلبٍ تعني دلواً جديداً، و«٥/ساعة»
    تصير بلا حدّ. وهذا الاختبارُ **كان يسقط** قبل `ClientIpScopedThrottle`.
    """

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    )
    def test_a_forged_forwarded_for_does_not_buy_a_fresh_bucket(self):
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle

        cache.clear()
        job = self.make_job()
        self.client.force_authenticate(user=None)
        path = f"/api/employee-ops/public/jobs/{job['token']}/apply/"

        with mock.patch.dict(
            ScopedRateThrottle.THROTTLE_RATES, {"employee_ops_apply": "2/hour"}
        ):
            codes = [
                self.client.post(
                    path,
                    {"name": "س", "phone": "059"},
                    format="multipart",
                    # ترويسةٌ مختلفةٌ في كلّ طلب — الحيلةُ كلُّها.
                    HTTP_X_FORWARDED_FOR=f"10.0.0.{i}",
                ).status_code
                for i in range(3)
            ]

        self.assertEqual(codes[2], 429, "تزويرُ الترويسة لا يجدّد الدلو")


class TheOtherTwoPublicEndpointsCannotBeForgedEither(HiringBaseTest):
    """القضيّة #208: نقطتان من ثلاثٍ كانتا على `ScopedRateThrottle` المجرَّد.

    `PublicJobApplyView` وحدَها كانت على `ClientIpScopedThrottle`. أمّا
    `PublicJobView` (قراءةُ الوظيفة) و`AcceptInvitationPublicView` (قبولُ الدعوة)
    فبقيتا على الصنف المجرَّد — وهويّتُه من `X-Forwarded-For` حين يكون
    `NUM_PROXIES` غيرَ مضبوط، وهو غيرُ مضبوطٍ هنا. فترويسةٌ جديدةٌ لكلّ طلبٍ
    تشتري دلواً جديداً، ويصير الحدُّ بلا حدّ.

    **وهذان التأكيدان كانا يسقطان قبل الإصلاح.**
    """

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    )
    def test_public_job_read_ignores_a_forged_forwarded_for(self):
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle

        cache.clear()
        job = self.make_job()
        self.client.force_authenticate(user=None)
        path = f"/api/employee-ops/public/jobs/{job['token']}/"

        with mock.patch.dict(
            ScopedRateThrottle.THROTTLE_RATES, {"employee_ops_job_public": "2/hour"}
        ):
            codes = [
                self.client.get(path, HTTP_X_FORWARDED_FOR=f"10.0.0.{i}").status_code
                for i in range(3)
            ]

        self.assertEqual(codes[:2], [200, 200], codes)
        self.assertEqual(codes[2], 429, "تزويرُ الترويسة اشترى دلواً جديداً لقراءة الوظيفة")

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    )
    def test_invitation_acceptance_ignores_a_forged_forwarded_for(self):
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle

        cache.clear()
        self.client.force_authenticate(user=None)
        # رمزٌ لا وجودَ له: المهمُّ أن يمرّ الطلبُ بالخانق قبل أن يُردّ،
        # فالخنقُ يقع قبل حلّ الرمز لا بعده.
        path = "/api/employee-ops/invitations/accept/no-such-token-208/"

        with mock.patch.dict(
            ScopedRateThrottle.THROTTLE_RATES, {"employee_ops_invite": "2/hour"}
        ):
            codes = [
                self.client.get(path, HTTP_X_FORWARDED_FOR=f"10.0.1.{i}").status_code
                for i in range(3)
            ]

        self.assertNotIn(429, codes[:2], codes)
        self.assertEqual(codes[2], 429, "تزويرُ الترويسة اشترى دلواً جديداً لقبول الدعوة")


class WordContainerSignaturesAreNotEnoughTest(HiringBaseTest):
    """توقيعُ ZIP يطابق كلَّ أرشيف، وتوقيعُ OLE يطابق **`.msi`**.

    فمثبِّتُ MSI باسم `cv.doc` بترويسة `application/msword` كان يمرّ من الفحوص
    الثلاثة، فيستقرّ برنامجٌ خبيثٌ على رابطٍ عامٍّ داخل حساب الشركة ويُدعى مديرُها
    للنقر عليه.
    """

    def setUp(self):
        super().setUp()
        self.job = self.make_job()
        self.patcher = mock.patch(
            "employee_ops.views.upload_media_file", return_value="https://x/y.doc"
        )
        self.upload = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def _apply_with(self, upload):
        self.client.force_authenticate(user=None)
        return self.client.post(
            f"/api/employee-ops/public/jobs/{self.job['token']}/apply/",
            {"name": "س", "phone": "059", "cv": upload},
            format="multipart",
        )

    def test_an_ole_container_that_is_not_a_word_document_is_refused(self):
        msi = SimpleUploadedFile(
            "cv.doc",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512,
            content_type="application/msword",
        )
        self.assertEqual(self._apply_with(msi).status_code, 400)
        self.assertFalse(self.upload.called)

    def test_a_plain_zip_renamed_to_docx_is_refused(self):
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("payload.exe", b"MZ\x90\x00")
        fake = SimpleUploadedFile(
            "cv.docx",
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )
        self.assertEqual(self._apply_with(fake).status_code, 400)
        self.assertFalse(self.upload.called)

    def test_a_real_docx_still_passes(self):
        """وإلا كان الاختباران أعلاه يمرّان لأنّ كلَّ docx يُردّ."""
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", b"<w:document/>")
            archive.writestr("[Content_Types].xml", b"<Types/>")
        real = SimpleUploadedFile(
            "cv.docx",
            buffer.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )
        self.assertEqual(self._apply_with(real).status_code, 201)
        self.assertTrue(self.upload.called)


class JobsNeverCrossTheCompanyLineTest(HiringBaseTest):
    """حارسُ عزلٍ للوظائف — كان موجوداً للمتقدّمين وحدهم."""

    def setUp(self):
        super().setUp()
        self.job = self.make_job()
        self.other_mgr = User.objects.create_user(username="hire_mgr_x", password="x")
        self.other = create_company("شركة خامسة", self.other_mgr)
        TenantModule.objects.create(
            tenant=self.other, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(self.other.pk)
        self.client.force_authenticate(user=self.other_mgr)
        self.other_headers = {"HTTP_X_TENANT_ID": str(self.other.pk)}

    def test_every_job_route_is_404_for_another_company(self):
        job_id = self.job["id"]
        cases = [
            ("get", f"/api/employee-ops/jobs/{job_id}/"),
            ("patch", f"/api/employee-ops/jobs/{job_id}/"),
            ("delete", f"/api/employee-ops/jobs/{job_id}/"),
            ("post", f"/api/employee-ops/jobs/{job_id}/close/"),
            ("post", f"/api/employee-ops/jobs/{job_id}/reopen/"),
            ("post", f"/api/employee-ops/jobs/{job_id}/regenerate-token/"),
        ]
        for method, path in cases:
            with self.subTest(path=f"{method} {path}"):
                res = getattr(self.client, method)(
                    path, {}, format="json", **self.other_headers
                )
                self.assertEqual(res.status_code, 404)

    def test_the_listing_shows_only_our_own_jobs(self):
        res = self.client.get("/api/employee-ops/jobs/", **self.other_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, [])


class ApplicantLifecycleTest(HiringBaseTest):
    def setUp(self):
        super().setUp()
        self.job = JobPosting.objects.create(
            tenant=self.tenant, title="وظيفة", description="وصف", token="tok-life"
        )
        self.applicant = JobApplicant.objects.create(
            tenant=self.tenant, job=self.job, name="أحمد", phone="0599111",
            reference_code="REF2",
        )

    def _patch(self, **payload):
        return self.client.patch(
            f"/api/employee-ops/applicants/{self.applicant.pk}/",
            payload, format="json", **self.headers,
        )

    def test_the_manager_moves_the_applicant_through_the_three_manual_states(self):
        for value in ("interview", "rejected", "new"):
            res = self._patch(status=value)
            self.assertEqual(res.status_code, 200, res.data)
            self.assertEqual(res.data["status"], value)

    def test_hired_cannot_be_set_by_hand(self):
        """حالةٌ تقول «وظّفناه» بلا موظفٍ في النظام كذبةٌ يقرؤها المدير لاحقاً."""
        res = self._patch(status="hired")
        self.assertEqual(res.status_code, 400)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.status, JobApplicant.STATUS_NEW)

    def test_hiring_links_the_applicant_to_a_real_employee_record(self):
        employee = Employee.objects.create(
            tenant=self.tenant, name="أحمد", code="H01"
        )
        res = self.client.post(
            f"/api/employee-ops/applicants/{self.applicant.pk}/hire/",
            {"employee": employee.pk}, format="json", **self.headers,
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.status, JobApplicant.STATUS_HIRED)
        self.assertEqual(self.applicant.hired_employee_id, employee.pk)

    def test_hiring_cannot_borrow_another_company_employee(self):
        other_mgr = User.objects.create_user(username="hire_mgr_c", password="x")
        other = create_company("شركة ثالثة", other_mgr)
        outsider = Employee.objects.create(tenant=other, name="غريب", code="H99")
        res = self.client.post(
            f"/api/employee-ops/applicants/{self.applicant.pk}/hire/",
            {"employee": outsider.pk}, format="json", **self.headers,
        )
        self.assertEqual(res.status_code, 404)
        self.applicant.refresh_from_db()
        self.assertIsNone(self.applicant.hired_employee_id)

    def test_a_rating_outside_five_stars_is_refused(self):
        self.assertEqual(self._patch(rating=6).status_code, 400)
        self.assertEqual(self._patch(rating=-1).status_code, 400)
        self.assertEqual(self._patch(rating=5).status_code, 200)

    def test_filters_and_search_narrow_the_list(self):
        JobApplicant.objects.create(
            tenant=self.tenant, job=self.job, name="سارة", phone="0598222",
            status=JobApplicant.STATUS_INTERVIEW, reference_code="REF3",
        )

        by_status = self.client.get(
            "/api/employee-ops/applicants/?status=interview", **self.headers
        )
        self.assertEqual([r["name"] for r in by_status.data], ["سارة"])

        by_phone = self.client.get(
            "/api/employee-ops/applicants/?search=0599", **self.headers
        )
        self.assertEqual([r["name"] for r in by_phone.data], ["أحمد"])

        by_name = self.client.get(
            "/api/employee-ops/applicants/?search=سار", **self.headers
        )
        self.assertEqual([r["name"] for r in by_name.data], ["سارة"])

    def test_a_garbage_filter_is_refused_not_ignored(self):
        """فلترٌ مجهولٌ يُتجاهَل يعني قائمةً كاملةً تُقدَّم على أنّها مفلترة."""
        self.assertEqual(
            self.client.get(
                "/api/employee-ops/applicants/?status=nope", **self.headers
            ).status_code, 400,
        )
        self.assertEqual(
            self.client.get(
                "/api/employee-ops/applicants/?job=abc", **self.headers
            ).status_code, 400,
        )

    def test_applicants_never_cross_the_company_line(self):
        other_mgr = User.objects.create_user(username="hire_mgr_d", password="x")
        other = create_company("شركة رابعة", other_mgr)
        TenantModule.objects.create(
            tenant=other, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(other.pk)
        self.client.force_authenticate(user=other_mgr)
        res = self.client.get(
            "/api/employee-ops/applicants/", HTTP_X_TENANT_ID=str(other.pk)
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, [])


class NumProxiesCheckTest(APITestCase):
    """**الشرط ٤** — الشرطُ الذي يجعل البندين ١ و٣ زينةً إن سقط."""

    def test_the_check_fires_while_num_proxies_is_unset(self):
        from employee_ops.checks import check_num_proxies_configured

        with override_settings(REST_FRAMEWORK={"NUM_PROXIES": None}):
            issues = check_num_proxies_configured(None)
        self.assertEqual(len(issues), 1)
        self.assertIn("X-Forwarded-For", issues[0].msg)

    def test_the_check_is_silent_once_it_is_set(self):
        from employee_ops.checks import check_num_proxies_configured

        with override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1}):
            self.assertEqual(check_num_proxies_configured(None), [])

    def test_declaring_the_gate_live_raises_the_severity_to_error(self):
        """«شرطٌ لازمٌ **قبل الإطلاق**» — فعند إعلان الإطلاق يصير خطأً.

        ولا يُدّعى أنّه «يمنع الإقلاع»: جانغو **لا يشغّل فحوصَ النظام تحت WSGI**،
        فالخطأُ يوقف أوامرَ `manage.py` ولا يوقف gunicorn. الحارسُ الحقيقيُّ ضدّ
        تزوير الهويّة هو `ClientIpScopedThrottle` لا هذا الفحص.
        """
        import os
        from django.core.checks import Error
        from employee_ops.checks import check_num_proxies_configured

        with override_settings(REST_FRAMEWORK={"NUM_PROXIES": None}):
            with mock.patch.dict(os.environ, {"EMPLOYEE_OPS_HIRING_LIVE": "1"}):
                issues = check_num_proxies_configured(None)
        self.assertEqual(len(issues), 1)
        self.assertIsInstance(issues[0], Error)

    def test_the_check_is_actually_registered(self):
        """الفحصُ الذي لا يُسجَّل لا يفحص شيئاً.

        الاختباراتُ أعلاه تنادي الدالّةَ مباشرةً، فتبقى خضراءَ لو حُذف
        `@register()` أو حُذف استيرادُها من `apps.ready()` — أي لو صار الفحصُ
        ميّتاً تماماً.
        """
        from django.core.checks.registry import registry
        from employee_ops.checks import check_num_proxies_configured

        self.assertIn(check_num_proxies_configured, registry.get_checks())


class InvitationLinkPointsAtThePageTest(HiringBaseTest):
    """رابطُ الدعوة يقود إلى صفحةٍ يملؤها إنسان، لا إلى نقطة API تردّ JSON.

    كان يشير إلى `/api/employee-ops/invitations/accept/<token>/` — يفتحه الموظفُ
    فيرى JSON. الوحدةُ كلُّها كانت خضراء والحلقةُ مكسورةٌ عند هذه النقطة وحدها.
    """

    def test_the_invite_link_targets_the_join_page(self):
        from employee_ops.views import INVITE_PAGE_PATH

        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف جديد", "phone": "0599777"},
            format="json",
            **self.headers,
        )
        self.assertEqual(res.status_code, 201, res.data)

        url = res.data["invitation_url"]
        token = res.data["raw_token"]
        self.assertTrue(
            url.endswith(f"{INVITE_PAGE_PATH}{token}"),
            f"رابطُ الدعوة «{url}» لا يقود إلى صفحة الانضمام",
        )
        self.assertNotIn(
            "/api/", url, "رابطٌ يُرسل لإنسانٍ لا يشير إلى نقطة API"
        )
