"""اختبارات بوابة التوظيف المنصية ومسار دعوة المرشحين (#207 المرحلة الثامنة - ب).

تغطي هذه الوحدة الشروط العشرة الصارمة:
1. test_hiring_portal_models_have_no_tenant_foreign_key
2. test_cv_file_validation_size_and_mime_and_magic_bytes
3. test_public_job_apply_without_cv_succeeds
4. test_public_job_apply_with_cv_upload_and_security
5. test_closed_job_apply_returns_410_gone
6. test_invitation_generation_stores_sha256_hash_only
7. test_invitation_acceptance_creates_user_and_employee_under_atomic_lock
8. test_consumed_or_expired_invitation_returns_410_gone
9. test_cv_url_never_exposed_in_serializers_and_redirect_endpoint_protected
10. test_recruiter_permission_isolation_and_operations_block
"""
import datetime
import hashlib
import io
import zipfile
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from tenants.models import Tenant
from platform_ops.models import (
    JobApplicant,
    JobApplicantInvitation,
    JobPosting,
    PlatformEmployee,
    PlatformRecruiter,
)
from platform_ops.public_hiring.cv_validation import (
    MAX_CV_BYTES,
    ApplicationTooLarge,
    InvitationGone,
    JobGone,
    validate_cv_bytes,
)
from platform_ops.serializers import (
    JobApplicantSerializer,
    JobPostingSerializer,
)
from platform_ops.public_hiring.serializers import (
    PublicJobPostingSerializer,
)
from platform_ops.services import (
    APPLICANT_TRANSITIONS,
    accept_applicant_invitation,
    close_job_posting,
    create_applicant_invitation,
    create_job_posting,
    create_platform_recruiter,
    is_platform_recruiter,
    job_is_live,
    job_public_url,
    invitation_public_url,
    rate_applicant,
    regenerate_job_posting_token,
    reopen_job_posting,
    resolve_public_invitation,
    resolve_public_job,
    revoke_platform_recruiter,
    submit_application,
    transition_applicant_status,
)


class PlatformHiringPortalTests(TestCase):
    """مجموعة اختبارات بوابة التوظيف المنصية الشاملة."""

    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username="platform_admin",
            email="admin@platform.local",
            password="AdminPassword123!",
        )
        self.recruiter_user = User.objects.create_user(
            username="recruiter_jane",
            email="recruiter@platform.local",
            password="RecruiterPass123!",
        )
        self.recruiter = PlatformRecruiter.objects.create(
            user=self.recruiter_user,
            is_active=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular_joe",
            email="joe@example.com",
            password="UserPass123!",
        )
        self.live_job = JobPosting.objects.create(
            title="مهندس عمليات منصية",
            specialty="operations",
            description="إدارة ومتابعة طلبات وشركات المنصة",
            requirements="خبرة في Django وREST APIs",
            location="عن بعد",
            employment_type="full_time",
            salary_range="10000 - 15000 SAR",
            token="live_job_token_1234567890abcdef",
            is_open=True,
            created_by=self.admin_user,
        )

    # 1. فحص خلو نماذج التوظيف من أي حقل أو ارتباط بشركة (tenant)
    def test_hiring_portal_models_have_no_tenant_foreign_key(self):
        """نماذج التوظيف المنصي تتبع المنصة لا أي شركة، ويُحظر ربطها بـ tenant."""
        hiring_models = [
            JobPosting,
            JobApplicant,
            JobApplicantInvitation,
            PlatformRecruiter,
        ]

        for model in hiring_models:
            field_names = [f.name for f in model._meta.get_fields()]
            self.assertNotIn(
                "tenant",
                field_names,
                f"النموذج {model.__name__} يحتوي على حقل باسم 'tenant' بشكل غير مسموح.",
            )
            for field in model._meta.get_fields():
                related_model = getattr(field, "related_model", None)
                if related_model is not None:
                    self.assertNotEqual(
                        related_model,
                        Tenant,
                        f"النموذج {model.__name__} يرتبط بنموذج Tenant عبر الحقل {field.name}.",
                    )

    # 2. فحص التحقق من حجم ونوع وتوقيع البايتات السحرية لملف السيرة الذاتية
    def test_cv_file_validation_size_and_mime_and_magic_bytes(self):
        """فحص الفرز الأمني لملفات السيرة الذاتية حسب الحجم والبايتات السحرية والامتداد."""
        # أ) ملف PDF صحيح
        valid_pdf_bytes = b"%PDF-1.4\n%sample pdf content for test\n%%EOF"
        mime = validate_cv_bytes(valid_pdf_bytes, "resume.pdf")
        self.assertEqual(mime, "application/pdf")

        # ب) ملف DOCX صحيح (أرشيف ZIP يحتوي word/document.xml)
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w") as zf:
            zf.writestr("word/document.xml", "<w:document></w:document>")
        valid_docx_bytes = bio.getvalue()
        mime_docx = validate_cv_bytes(valid_docx_bytes, "resume.docx")
        self.assertIn("wordprocessingml", mime_docx)

        # ج) ملف DOC قديم صحيح (OLE2 header + WordDocument stream)
        valid_doc_bytes = (
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
            + b"\x00" * 64
            + b"WordDocument"
            + b"\x00" * 64
        )
        mime_doc = validate_cv_bytes(valid_doc_bytes, "resume.doc")
        self.assertEqual(mime_doc, "application/msword")

        # د) تجاوز سقف الحجم (5 ميغابايت)
        oversized_bytes = b"%PDF-1.4\n" + b"X" * (MAX_CV_BYTES + 10)
        with self.assertRaises(ApplicationTooLarge):
            validate_cv_bytes(oversized_bytes, "large.pdf")

        # هـ) ملف فارغ
        with self.assertRaises(ValidationError):
            validate_cv_bytes(b"", "empty.pdf")

        # و) امتداد زائف: ملف تنفيذي باسم pdf
        fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00executable content"
        with self.assertRaises(ValidationError):
            validate_cv_bytes(fake_pdf, "malicious.pdf")

        # ز) امتداد غير مدعوم
        with self.assertRaises(ValidationError):
            validate_cv_bytes(b"some plain text", "resume.txt")

    # 3. تقديم طلب توظيف عام بدون سيرة ذاتية ينجح بحالة new
    def test_public_job_apply_without_cv_succeeds(self):
        """التقديم على وظيفة عامة بالبيانات الأساسية دون ملف سيرة ذاتية."""
        apply_url = f"/api/careers/jobs/{self.live_job.token}/apply/"
        payload = {
            "name": "عبد الله محمد",
            "phone": "0551122334",
            "email": "abdullah@example.com",
            "about": "مهتم بالانضمام لفريق عمليات المنصة",
        }

        response = self.client.post(apply_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data.get("reference_code"))
        self.assertEqual(response.data.get("status"), "new")
        self.assertEqual(response.data.get("job_title"), self.live_job.title)

        ref_code = response.data["reference_code"]
        applicant = JobApplicant.objects.get(reference_code=ref_code)
        self.assertEqual(applicant.name, "عبد الله محمد")
        self.assertEqual(applicant.status, JobApplicant.Status.NEW)
        self.assertEqual(applicant.cv_url, "")
        self.assertEqual(applicant.cv_name, "")

    # 4. تقديم طلب توظيف مع رفع ملف سيرة ذاتية وحجب الرابط عن الاستجابة
    def test_public_job_apply_with_cv_upload_and_security(self):
        """رفع سيرة ذاتية وحفظها بأمان، مع التأكد من عدم تسريب رابطها في الاستجابة."""
        apply_url = f"/api/careers/jobs/{self.live_job.token}/apply/"
        valid_pdf_content = b"%PDF-1.4\n%valid cv file\n%%EOF"
        cv_file = SimpleUploadedFile(
            "candidate_cv.pdf",
            valid_pdf_content,
            content_type="application/pdf",
        )

        payload = {
            "name": "مها خالد",
            "phone": "0598877665",
            "email": "maha@example.com",
            "about": "خبرة 4 سنوات في العمليات",
            "cv_file": cv_file,
        }

        # التخزينُ السحابيُّ يُرقَّع: اختبارُ وحدةٍ لا يخرج إلى الشبكة، والسابقةُ
        # `employee_ops/tests/test_hiring_gate.py` تفعل الشيءَ نفسَه.
        with mock.patch(
            "platform_ops.public_hiring.views.upload_media_file",
            return_value="https://res.cloudinary.com/test/raw/upload/candidate_cv.pdf",
        ) as upload:
            response = self.client.post(apply_url, payload, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(upload.call_count, 1)

        # الحارس الأمني: cv_url لا يُسرّب في الرد العام
        self.assertNotIn("cv_url", response.data)
        self.assertEqual(response.data.get("cv_name"), "candidate_cv.pdf")

        ref_code = response.data["reference_code"]
        applicant = JobApplicant.objects.get(reference_code=ref_code)
        self.assertEqual(applicant.cv_name, "candidate_cv.pdf")
        self.assertTrue(bool(applicant.cv_url))

    # 5. التقديم على وظيفة مغلقة أو منتهية يرد بـ 410 Gone
    def test_closed_job_apply_returns_410_gone(self):
        """الوظيفة المغلقة أو المنتهية ترد بـ 410 صريحة عند العرض أو التقديم."""
        # أ) إغلاق يدوي
        self.live_job.is_open = False
        self.live_job.save()

        detail_url = f"/api/careers/jobs/{self.live_job.token}/"
        apply_url = f"/api/careers/jobs/{self.live_job.token}/apply/"

        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, status.HTTP_410_GONE)

        res_apply = self.client.post(apply_url, {"name": "زيد", "phone": "0500000000"})
        self.assertEqual(res_apply.status_code, status.HTTP_410_GONE)

        # ب) فحص الوظيفة المنتهية الصلاحية زمنياً
        self.live_job.is_open = True
        self.live_job.expires_at = timezone.now() - datetime.timedelta(days=2)
        self.live_job.save()

        res_detail_exp = self.client.get(detail_url)
        self.assertEqual(res_detail_exp.status_code, status.HTTP_410_GONE)

        # فحص طبقة الخدمات
        with self.assertRaises(JobGone):
            resolve_public_job(self.live_job.token)

    # 6. توليد دعوة قبول المرشح يحفظ فقط تجزئة SHA-256 للرمز في القاعدة
    def test_invitation_generation_stores_sha256_hash_only(self):
        """رمز الدعوة الخام لا يُخزن أبداً، بل يُخزن مهشراً (SHA-256)."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="طارق زياد",
            phone="0512345678",
            reference_code="REF-TAREQ-1",
            status=JobApplicant.Status.OFFERED,
        )

        invitation, raw_token = create_applicant_invitation(
            applicant=applicant,
            created_by=self.admin_user,
            expires_in_hours=48,
        )

        # الرمز الخام ذو طول كافٍ وغير قابل للتخمين
        self.assertGreaterEqual(len(raw_token), 32)

        # التجزئة المتوقعة
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self.assertEqual(invitation.token_hash, expected_hash)

        # الرمز الخام غير موجود بنصه في القاعدة
        self.assertFalse(
            JobApplicantInvitation.objects.filter(token_hash__contains=raw_token).exists()
        )

        # بقاء حالة المرشح offered
        applicant.refresh_from_db()
        self.assertEqual(applicant.status, JobApplicant.Status.OFFERED)

    # 7. قبول الدعوة يُنشئ المستخدم وموظف المنصة ويُحدّث المرشح تحت قفل ذري
    def test_invitation_acceptance_creates_user_and_employee_under_atomic_lock(self):
        """قبول الدعوة ينشئ الحساب والموظف ويسجل القبول في معاملة ذرية متسقة."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="سالم مبارك",
            phone="0599988877",
            email="salem@platform.local",
            reference_code="REF-SALEM-77",
            status=JobApplicant.Status.OFFERED,
        )

        invitation, raw_token = create_applicant_invitation(
            applicant=applicant,
            created_by=self.admin_user,
        )

        accept_url = f"/api/careers/invitations/{raw_token}/accept/"
        accept_payload = {
            "username": "salem_ops",
            "password": "SecurePassword2026!",
        }

        response = self.client.post(accept_url, accept_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("username"), "salem_ops")
        self.assertEqual(response.data.get("applicant_status"), "hired")

        # التحقق من إنشاء المستخدم
        user = User.objects.get(username="salem_ops")
        self.assertTrue(user.check_password("SecurePassword2026!"))
        self.assertEqual(user.email, "salem@platform.local")

        # التحقق من إنشاء موظف المنصة
        emp = PlatformEmployee.objects.get(user=user)
        # التخصّصُ من حقل الوظيفة لا من عنوانها — العنوانُ نصٌّ حرٌّ أطولُ من العمود
        # الهدفِ ولا يطابق أيَّ `PolicyProfile`.
        self.assertEqual(emp.specialty, "operations")
        self.assertEqual(emp.status, PlatformEmployee.Status.ACTIVE)

        # التحقق من ربط الموظف بالمرشح وتحديث حالته
        applicant.refresh_from_db()
        self.assertEqual(applicant.status, JobApplicant.Status.HIRED)
        self.assertEqual(applicant.hired_employee, emp)

        # استهلاك الدعوة
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_accepted)
        self.assertTrue(invitation.is_consumed)

    # 8. الدعوة المستهلكة أو المنتهية ترد بـ 410 Gone صريحة
    def test_consumed_or_expired_invitation_returns_410_gone(self):
        """رابط الدعوة المستهلك أو المنتهي يرد بـ 410 Gone."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="نوف ناصر",
            phone="0577766655",
            email="nouf@platform.local",
            reference_code="REF-NOUF-88",
            status=JobApplicant.Status.OFFERED,
        )

        invitation, raw_token = create_applicant_invitation(
            applicant=applicant,
            created_by=self.admin_user,
        )

        # قبولها أول مرة
        accept_applicant_invitation(
            token=raw_token,
            password="StrongPassword123!",
            username="nouf_staff",
        )

        # محاولة عرضها أو قبولها ثانية ترد بـ 410
        invite_url = f"/api/careers/invitations/{raw_token}/"
        accept_url = f"/api/careers/invitations/{raw_token}/accept/"

        res_get = self.client.get(invite_url)
        self.assertEqual(res_get.status_code, status.HTTP_410_GONE)

        res_post = self.client.post(
            accept_url,
            {"username": "nouf_second", "password": "Password123!"},
            format="json",
        )
        self.assertEqual(res_post.status_code, status.HTTP_410_GONE)

        # فحص انتهاء الصلاحية
        invitation.accepted_at = None
        invitation.expires_at = timezone.now() - datetime.timedelta(hours=1)
        invitation.save()

        res_get_exp = self.client.get(invite_url)
        self.assertEqual(res_get_exp.status_code, status.HTTP_410_GONE)

        # فحص رمز غير موجود نهائياً (404)
        res_404 = self.client.get("/api/careers/invitations/non_existent_token_xyz/")
        self.assertEqual(res_404.status_code, status.HTTP_404_NOT_FOUND)

    # 9. حظر ظهور رابط cv_url في كل المسلسلات وحماية مسار التحميل المخصص
    def test_cv_url_never_exposed_in_serializers_and_redirect_endpoint_protected(self):
        """حظر تسريب cv_url في المسلسلات وإتاحته فقط عبر نقطة تحويل محمية."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="فهد إبراهيم",
            phone="0544433221",
            email="fahad@example.com",
            reference_code="REF-FAHAD-99",
            cv_url="https://storage.platform.local/media/cvs/fahad_cv.pdf",
            cv_name="fahad_cv.pdf",
        )

        # 1. فحص المسلسل الإداري الداخلي
        admin_data = JobApplicantSerializer(applicant).data
        self.assertNotIn("cv_url", admin_data)
        self.assertIn("has_cv", admin_data)
        self.assertTrue(admin_data["has_cv"])
        self.assertEqual(admin_data["cv_name"], "fahad_cv.pdf")

        # 2. فحص المسلسلات العامة
        pub_job_data = PublicJobPostingSerializer(self.live_job).data
        self.assertNotIn("cv_url", pub_job_data)

        # 3. فحص نقطة التحميل المخصصة cv/
        cv_endpoint = f"/api/platform/ops/job-applicants/{applicant.id}/cv/"

        # أ) غير مسجل دخول => 401
        self.client.force_authenticate(user=None)
        res_anon = self.client.get(cv_endpoint)
        self.assertEqual(res_anon.status_code, status.HTTP_401_UNAUTHORIZED)

        # ب) مستخدم عادي => 403
        self.client.force_authenticate(user=self.regular_user)
        res_forbidden = self.client.get(cv_endpoint)
        self.assertEqual(res_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # ج) مسؤولُ توظيف => **بايتاتٌ لا إعادةُ توجيه**.
        #
        # ترويسةُ `Location` هي رابطُ التخزين حرفيّاً، فتحويلُ الطلب يسلّم ما تقول
        # المواصفةُ إنّه «لا يُسلَّم بأيّ حال»، ويبقى في سجلّ المتصفّح صالحاً بعد
        # انتهاء الجلسة — والرابطُ عند المزوّد **هو** الصلاحية. فالخادمُ يجلب
        # ويمرّر، ولا يغادر الرابطُ الخادمَ في أيّ ترويسةٍ أو جسم.
        self.client.force_authenticate(user=self.recruiter_user)
        fake_upstream = mock.Mock()
        fake_upstream.headers = {"Content-Type": "application/pdf"}
        fake_upstream.raw = io.BytesIO(b"%PDF-1.4 stored cv bytes %%EOF")
        fake_upstream.raise_for_status = mock.Mock()
        with mock.patch(
            "platform_ops.views.requests.get", return_value=fake_upstream
        ) as fetch:
            res_recruiter = self.client.get(cv_endpoint)

        self.assertEqual(res_recruiter.status_code, status.HTTP_200_OK)
        fetch.assert_called_once()
        self.assertNotIn("Location", res_recruiter)
        self.assertEqual(res_recruiter["Content-Type"], "application/pdf")
        self.assertIn("fahad_cv.pdf", res_recruiter["Content-Disposition"])
        body = b"".join(res_recruiter.streaming_content)
        self.assertIn(b"stored cv bytes", body)
        # ولا يظهر رابطُ التخزين في أيّ ترويسةٍ أو في الجسم.
        self.assertNotIn(b"storage.platform.local", body)
        for header_value in res_recruiter.headers.values():
            self.assertNotIn("storage.platform.local", str(header_value))

        # د) متقدم بدون سيرة ذاتية => 404
        applicant_no_cv = JobApplicant.objects.create(
            job=self.live_job,
            name="ماجد صالح",
            phone="0511111111",
            reference_code="REF-MAJED-00",
            cv_url="",
        )
        res_no_cv = self.client.get(f"/api/platform/ops/job-applicants/{applicant_no_cv.id}/cv/")
        self.assertEqual(res_no_cv.status_code, status.HTTP_404_NOT_FOUND)

    # 10. عزل صلاحية مسؤول التوظيف ومنعه من لوحة العمليات أو مسارات المستأجرين
    def test_recruiter_permission_isolation_and_operations_block(self):
        """مسؤول التوظيف يصل للوظائف والمتقدمين فقط، ويُحظر عليه لوحات وعمليات المنصة."""
        self.client.force_authenticate(user=self.recruiter_user)

        # 1. مسارات التوظيف المسموحة
        res_jobs = self.client.get("/api/platform/ops/job-postings/")
        self.assertEqual(res_jobs.status_code, status.HTTP_200_OK)

        res_applicants = self.client.get("/api/platform/ops/job-applicants/")
        self.assertEqual(res_applicants.status_code, status.HTTP_200_OK)

        # 2. مسارات العمليات المحظورة تماماً على مسؤول التوظيف (403)
        blocked_endpoints = [
            "/api/platform/ops/recruiters/",       # محصورة بمدير المنصة
            "/api/platform/ops/dashboard/",        # لوحة تحكم العمليات
            "/api/platform/ops/work-orders/",      # أوامر العمل
            "/api/platform/ops/employees/",        # موظفو العمليات
            "/api/platform/ops/subscriptions/",    # الاشتراكات
            "/api/platform/ops/integration-keys/", # مفاتيح القنوات
            "/api/platform/dashboard/",            # لوحة السوبر أدمن العامة
        ]

        for url in blocked_endpoints:
            res = self.client.get(url)
            self.assertEqual(
                res.status_code,
                status.HTTP_403_FORBIDDEN,
                f"مسؤول التوظيف تمكن من الوصول إلى {url} بحالة {res.status_code} دون تصريح!",
            )

        # 3. إذا تم إلغاء تنشيط مسؤول التوظيف، يُمنع حتى من مسارات التوظيف
        self.recruiter.is_active = False
        self.recruiter.save()

        res_jobs_revoked = self.client.get("/api/platform/ops/job-postings/")
        self.assertEqual(res_jobs_revoked.status_code, status.HTTP_403_FORBIDDEN)

    # 12. طولُ العمود مقابل أطولِ مفتاحِ رمزٍ، وتخصّصُ الوظيفة يسع عمودَ الموظّف
    def test_choice_columns_fit_their_longest_key_and_specialty_fits_target(self):
        """طولُ عمودٍ أقصرُ من أطولِ رمزٍ يُلغي القيدَ بصمت على MySQL ولا تكشفه SQLite.

        والسابقتان في هذا المستودع `ActivityLog.action` و`docshare.doc_type`.
        ويُلحق بهما هنا فحصٌ ثالث: `JobPosting.specialty` يُنسَخ حرفيّاً إلى
        `PlatformEmployee.specialty` عند قبول الدعوة، فلا يجوز أن يكون أوسعَ منه.
        """
        for model, field_name in (
            (JobPosting, "employment_type"),
            (JobApplicant, "status"),
        ):
            field = model._meta.get_field(field_name)
            self.assertTrue(field.choices, f"{model.__name__}.{field_name} بلا choices")
            longest = max(len(str(key)) for key, _ in field.choices)
            self.assertGreaterEqual(
                field.max_length,
                longest,
                f"{model.__name__}.{field_name}: العمود {field.max_length} وأطولُ رمزٍ {longest}",
            )

        source = JobPosting._meta.get_field("specialty")
        target = PlatformEmployee._meta.get_field("specialty")
        self.assertLessEqual(
            source.max_length,
            target.max_length,
            "تخصّصُ الوظيفة أوسعُ من عمود تخصّص الموظّف — بترٌ صامتٌ على SQLite وخطأٌ على MySQL.",
        )

    # 13. الحالةُ لا تتحرّك بكتابةٍ مباشرة
    def test_status_cannot_be_moved_by_a_plain_patch(self):
        """`PATCH {"status": "hired"}` كان يصنع مقبولاً بلا حسابٍ ولا موظّف.

        الحالةُ تتحرّك بـ`transition-status` وحدَها فتمرّ بجدول الانتقالات وبحارس
        «حالةُ المقبول تُبلَغ بقبول الدعوة». وكتابتُها مباشرةً كانت تتجاوز الاثنين
        وتُنتج متقدّماً «مقبولاً» بلا `PlatformEmployee` ولا دعوةٍ مستهلَكة.
        """
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="سارة يوسف",
            phone="0577766554",
            reference_code="REF-SARA-11",
        )
        self.client.force_authenticate(user=self.recruiter_user)

        res = self.client.patch(
            f"/api/platform/ops/job-applicants/{applicant.id}/",
            {"status": JobApplicant.Status.HIRED},
            format="json",
        )
        # 405 (لا تحريرَ أصلاً) أو 400 (مرفوض) أو 200 (قُبل الطلب وتُجوهل الحقل) —
        # المهمُّ أنّ الحالةَ لم تتحرّك، لا الرمزُ الذي رُدّ به.
        self.assertIn(
            res.status_code,
            (
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_405_METHOD_NOT_ALLOWED,
            ),
        )

        applicant.refresh_from_db()
        self.assertNotEqual(
            applicant.status,
            JobApplicant.Status.HIRED,
            "كتابةٌ مباشرةٌ حرّكت الحالة إلى «مقبول» متجاوزةً جدولَ الانتقالات.",
        )
        self.assertIsNone(applicant.hired_employee)

        # ونقلُ المتقدّم إلى إعلانٍ آخر ليس تحريراً كذلك.
        other_job = JobPosting.objects.create(
            title="وظيفة أخرى",
            specialty="sales",
            description="وصف",
            token="other_job_token_abcdef0123456789",
            is_open=True,
        )
        self.client.patch(
            f"/api/platform/ops/job-applicants/{applicant.id}/",
            {"job": other_job.pk},
            format="json",
        )
        applicant.refresh_from_db()
        self.assertEqual(applicant.job_id, self.live_job.pk)


class PlatformRecruiterRouteScopeTest(TestCase):
    """الاستثناءُ الوحيدُ المعلَن على `/api/platform/` — ومحصورٌ بمسارَيه.

    عقدُ `core/urls.py` أنّ لا نقطةَ تحت `/api/platform/` تُقرأ بغير سوبر أدمن،
    وم٨-ب أدخلت دوراً منصّيّاً ليس سوبر أدمن ويقرأ نقطتين. فيُحرَس حدُّ الاستثناء
    بعدّ **كلّ** المسارات من الـURLconf لا بقائمةٍ مكتوبةٍ بيد: نقطةٌ جديدةٌ تنفتح
    له سهواً تُسقط هذا الاختبار.

    ومكانُه هنا لا في `core/tests/`: حارسُ العزل يمنع `core` من استيراد
    `platform_ops`، والاتّجاهُ المسموح هو العكس.
    """

    def setUp(self):
        self.client = APIClient()
        self.recruiter_user = User.objects.create_user(username="scope-recruiter", password="x")
        self.recruiter = PlatformRecruiter.objects.create(user=self.recruiter_user, is_active=True)

    #: ما يفتحه دورُ التوظيف عمداً — بادئاتٌ لا مساراتٌ حرفيّة، لتشمل التفاصيل.
    HIRING_PREFIXES = (
        "/api/platform/ops/job-postings",
        "/api/platform/ops/job-applicants",
    )

    @staticmethod
    def _platform_routes():
        """كلُّ مسارٍ تحت `/api/platform/` كما يراه المحلِّلُ — لا قائمةٌ مكتوبةٌ بيد.

        يُقرأ من `django.urls.get_resolver()` لا باستيراد `core.urls`: حارسُ العزل
        يحصر ما تستورده هذه الوحدةُ من `core` في قائمةٍ بيضاءَ صريحة، والمحلِّلُ
        نفسُه مصدرٌ أدقُّ على أيّ حال.
        """
        import re as _re

        from django.urls import get_resolver

        def walk(patterns, prefix=""):
            for entry in patterns:
                route = prefix + str(entry.pattern)
                if hasattr(entry, "url_patterns"):
                    yield from walk(entry.url_patterns, route)
                else:
                    yield route

        urls = []
        for route in walk(get_resolver().url_patterns):
            route = route.replace("^", "").replace("$", "")
            if not route.startswith("api/platform/"):
                continue
            if "format" in route:
                continue
            route = _re.sub(r"<int:[^>]+>", "1", route)
            route = _re.sub(r"<str:[^>]+>", "x", route)
            route = _re.sub(r"\(\?P<\w+>[^)]+\)", "1", route)
            urls.append("/" + route)
        return sorted(set(urls))

    def test_a_platform_recruiter_reaches_the_hiring_routes_and_nothing_else(self):
        routes = self._platform_routes()
        self.client.force_authenticate(user=self.recruiter_user)

        closed = 0
        for route in routes:
            if route.startswith(self.HIRING_PREFIXES):
                continue
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(
                    response.status_code,
                    403,
                    f"دورُ التوظيف وصل إلى {route} بحالة {response.status_code}",
                )
            closed += 1

        self.assertGreaterEqual(closed, 12, f"عدد المسارات المفحوصة أقل من المتوقع: {closed}")

        # وليس 403 للكلّ: مسارا التوظيف يُفتحان له فعلاً.
        self.assertEqual(self.client.get("/api/platform/ops/job-postings/").status_code, 200)
        self.assertEqual(self.client.get("/api/platform/ops/job-applicants/").status_code, 200)

    def test_recruiter_can_set_the_platform_specialty_on_a_job(self):
        """التخصّصُ حقلٌ قابلٌ للضبط من سطح التوظيف لا قيمةٌ تُخمَّن من العنوان.

        بلا إتاحته في المُسلسِل يبقى فارغاً دوماً فيُوظَّف المقبولُ بلا تخصّص،
        ولا يطابق أداؤه أيَّ `PolicyProfile`.
        """
        self.client.force_authenticate(user=self.recruiter_user)
        res = self.client.post(
            "/api/platform/ops/job-postings/",
            {
                "title": "مدخل بيانات أول",
                "specialty": "data_entry",
                "description": "إدخال مستندات الزبائن",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data.get("specialty"), "data_entry")
        self.assertEqual(
            JobPosting.objects.get(pk=res.data["id"]).specialty, "data_entry"
        )

class PublicSurfaceGuardTest(TestCase):
    """سطحُ الوحدة العامّ **يُقرأ دفعةً واحدة** — قائمةٌ معلَنةٌ لا اكتشافٌ بالصدفة.

    القصّة ٧٩: «أريد أن يكون كلُّ كود `AllowAny` في حزمةٍ واحدة، لأراجع سطحَ
    الهجوم دفعةً واحدة». والحارسُ هنا أقوى من التجميع وحدَه: يعدّ **كلّ** صنفِ
    view في الوحدة يحمل `AllowAny`، ويؤكّد أنّه في موضعٍ معلَن، وأنّه يُعلن
    مصادقتَه صراحةً (فالافتراضيُّ العامّ `DeviceTokenAuthentication`)، وأنّ خانقَه
    `ClientIpScopedThrottle` **لا** `ScopedRateThrottle` المجرّد الذي هويّتُه من
    `X-Forwarded-For` القابلِ للتزوير — وهو العيبُ الذي وجدته #190 في نقطتين من
    ثلاثٍ في `employee_ops`، فلا يُنسَخ هنا.

    نقطةٌ عامّةٌ جديدةٌ تُضاف بلا خانقٍ أو خارج المواضع المعلَنة تُسقط هذا الاختبار.
    """

    #: المواضعُ المعلَنة لكود `AllowAny` في الوحدة، بسببٍ مكتوبٍ لكلٍّ.
    DECLARED_PUBLIC_MODULES = {
        "platform_ops.public_hiring.views":
            "بوّابةُ التوظيف: الإعلانُ والتقديمُ والدعوةُ وقبولُها (م٨-ب).",
        "platform_ops.views":
            "`PublicDailyRatingView` وحدَها — رابطُ التقييم اليوميّ العامّ (م٧)، "
            "سبقت إنشاءَ حزمة `public_hiring` وتسكن سطحَ المستأجرين لا التوظيف.",
    }

    #: أسماءُ أصنافِ الـview العامّة المعلَنة — الجردُ الذي يقرؤه مراجعُ الأمن.
    DECLARED_PUBLIC_VIEWS = {
        "PublicJobDetailView",
        "PublicJobApplyView",
        "PublicInvitationDetailView",
        "PublicInvitationAcceptView",
        "PublicDailyRatingView",
    }

    @staticmethod
    def _public_view_classes():
        import inspect

        from rest_framework.permissions import AllowAny

        from platform_ops import views as ops_views
        from platform_ops.public_hiring import views as hiring_views

        found = {}
        for module in (ops_views, hiring_views):
            for name, obj in vars(module).items():
                if not inspect.isclass(obj):
                    continue
                if getattr(obj, "__module__", "") != module.__name__:
                    continue
                permissions = getattr(obj, "permission_classes", None) or []
                if AllowAny in permissions:
                    found[name] = obj
        return found

    def test_every_public_view_is_declared_authenticated_explicitly_and_ip_throttled(self):
        from platform_ops.throttles import ClientIpScopedThrottle

        found = self._public_view_classes()

        self.assertEqual(
            set(found), self.DECLARED_PUBLIC_VIEWS,
            "سطحُ الوحدة العامّ تغيّر: حدِّث الجردَ المعلَن هنا بسببٍ مكتوبٍ لكلّ نقطة.",
        )

        for name, view in found.items():
            with self.subTest(view=name):
                self.assertIn(
                    view.__module__, self.DECLARED_PUBLIC_MODULES,
                    f"{name} يحمل AllowAny خارج المواضع المعلَنة ({view.__module__}).",
                )
                self.assertEqual(
                    list(getattr(view, "authentication_classes", ["<unset>"])), [],
                    f"{name} لا يُعلن مصادقتَه صراحةً، فيرث `DeviceTokenAuthentication` العامّ.",
                )
                throttles = list(getattr(view, "throttle_classes", []) or [])
                self.assertTrue(
                    throttles, f"{name} نقطةٌ عامّةٌ **بلا خانق**.",
                )
                for throttle in throttles:
                    self.assertTrue(
                        issubclass(throttle, ClientIpScopedThrottle),
                        f"{name} يستعمل {throttle.__name__} لا ClientIpScopedThrottle — "
                        "هويّةُ الخانق تصير من ترويسةٍ قابلةٍ للتزوير.",
                    )
                scope = getattr(view, "throttle_scope", "")
                self.assertTrue(scope, f"{name} بلا `throttle_scope`.")
                self.assertIn(
                    scope,
                    settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
                    f"نطاقُ خانق {name} («{scope}») بلا معدّلٍ في الإعدادات.",
                )


class PlatformHiringAdminSurfaceTests(TestCase):
    """اختبارات السطح الإداري للتوظيف المنصي (#207 م٨-ب)."""

    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username="admin_surface",
            email="admin_surface@platform.local",
            password="AdminPassword123!",
        )
        self.recruiter_user = User.objects.create_user(
            username="recruiter_surface",
            email="recruiter_surface@platform.local",
            password="RecruiterPass123!",
        )
        self.recruiter = PlatformRecruiter.objects.create(
            user=self.recruiter_user,
            is_active=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular_surface",
            email="regular_surface@example.com",
            password="RegularPass123!",
        )
        self.live_job = JobPosting.objects.create(
            title="مطور بايثون وجانغو",
            specialty="operations",
            description="وصف الوظيفة المنصية للاختبار",
            location="عن بعد",
            employment_type="full_time",
            token="admin_surface_live_job_token_123",
            is_open=True,
            created_by=self.admin_user,
        )

    def test_platform_staff_me_capabilities(self):
        """1. platform-staff/me/: سوبر أدمن، مسؤول توظيف نشط، مسؤول ملغى، مستخدم عادي، مجهول."""
        url = "/api/platform-staff/me/"

        # سوبر أدمن
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_platform_admin"])

        # مسؤول توظيف نشط
        self.client.force_authenticate(user=self.recruiter_user)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_platform_recruiter"])
        self.assertFalse(res.data["is_platform_admin"])

        # مسؤول توظيف ملغى
        self.recruiter.is_active = False
        self.recruiter.save(update_fields=["is_active"])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_platform_recruiter"])

        # مستخدم عادي
        self.client.force_authenticate(user=self.regular_user)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_platform_admin"])
        self.assertFalse(res.data["is_platform_recruiter"])
        self.assertFalse(res.data["is_platform_employee"])

        # مجهول (غير مسجل دخول)
        self.client.force_authenticate(user=None)
        res = self.client.get(url)
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_recruiter_assignment_revocation_reassignment_and_permissions(self):
        """2. إسناد مسؤول بالاسم وبالبريد بحروف مختلفة، معرّف غير موجود، إلغاء، إعادة إسناد بنفس pk، 405 لـ PATCH/PUT، 403 لمسؤول التوظيف."""
        url = "/api/platform/ops/recruiters/"

        # مسؤول التوظيف نفسه على recruiters/ يرد 403
        self.client.force_authenticate(user=self.recruiter_user)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin_user)

        # إسناد بالاسم
        candidate1 = User.objects.create_user(username="cand1", email="cand1@test.local")
        res = self.client.post(url, {"identifier": "cand1"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recruiter_id = res.data["id"]

        # إسناد بالبريد بحروف مختلفة الحالة
        candidate2 = User.objects.create_user(username="cand2", email="MixedCase@Test.Local")
        res = self.client.post(url, {"identifier": "mixedcase@test.local"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # معرّف غير موجود => 400
        res = self.client.post(url, {"identifier": "nonexistent_user_xyz"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # الإلغاء => الصف باقٍ و is_active=False
        del_res = self.client.delete(f"{url}{recruiter_id}/")
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        rec1 = PlatformRecruiter.objects.get(pk=recruiter_id)
        self.assertFalse(rec1.is_active)

        # إعادة الإسناد => الـ pk نفسه و is_active=True
        re_res = self.client.post(url, {"identifier": "cand1"}, format="json")
        self.assertEqual(re_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(re_res.data["id"], recruiter_id)
        rec1.refresh_from_db()
        self.assertTrue(rec1.is_active)

        # PATCH و PUT => 405
        patch_res = self.client.patch(f"{url}{recruiter_id}/", {"is_active": False}, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        put_res = self.client.put(f"{url}{recruiter_id}/", {"identifier": "cand1"}, format="json")
        self.assertEqual(put_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_applicant_next_statuses_matches_machine_without_hired(self):
        """3. next_statuses لكل حالة يساوي APPLICANT_TRANSITIONS[status] - {hired} ولا يحوي hired أبداً."""
        self.client.force_authenticate(user=self.recruiter_user)
        for val, _ in JobApplicant.Status.choices:
            applicant = JobApplicant.objects.create(
                job=self.live_job,
                name=f"متقدم {val}",
                phone="0500000000",
                reference_code=f"REF-ST-{val}",
                status=val,
            )
            res = self.client.get(f"/api/platform/ops/job-applicants/{applicant.pk}/")
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            returned_values = {item["value"] for item in res.data.get("next_statuses", [])}
            expected_values = APPLICANT_TRANSITIONS.get(val, set()) - {JobApplicant.Status.HIRED}
            self.assertEqual(returned_values, expected_values)
            self.assertNotIn(JobApplicant.Status.HIRED, returned_values)

    def test_destroy_job_posting_with_applicants_fails_without_applicants_succeeds(self):
        """4. حذف إعلان له متقدم => 400 والمتقدم ما زال موجوداً · إعلان بلا متقدمين => 204."""
        self.client.force_authenticate(user=self.recruiter_user)
        # إعلان له متقدم
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="متقدم تجريبي",
            phone="0511111111",
            reference_code="REF-DEL-1",
            status=JobApplicant.Status.NEW,
        )
        res = self.client.delete(f"/api/platform/ops/job-postings/{self.live_job.pk}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("أغلق الإعلانَ بدل حذفه", str(res.data))
        # المتقدم ما زال موجوداً
        self.assertTrue(JobApplicant.objects.filter(pk=applicant.pk).exists())
        self.assertTrue(JobPosting.objects.filter(pk=self.live_job.pk).exists())

        # إعلان بلا متقدمين => 204
        empty_job = JobPosting.objects.create(
            title="وظيفة فارغة",
            specialty="operations",
            description="وظيفة للتأكد من الحذف",
            token="empty_job_token_del_test",
            is_open=True,
            created_by=self.admin_user,
        )
        res_empty = self.client.delete(f"/api/platform/ops/job-postings/{empty_job.pk}/")
        self.assertEqual(res_empty.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(JobPosting.objects.filter(pk=empty_job.pk).exists())

    def test_invitation_lifecycle_and_validation(self):
        """5. متقدم new أو rejected => 400 · offered => 201 · دعوة ثانية => الأولى revoked_at و 410 · expires_in_hours غير صالح => 400."""
        self.client.force_authenticate(user=self.recruiter_user)

        # متقدم new => 400
        app_new = JobApplicant.objects.create(
            job=self.live_job,
            name="متقدم جديد",
            phone="0522222222",
            reference_code="REF-INV-NEW",
            status=JobApplicant.Status.NEW,
        )
        res_new = self.client.post(f"/api/platform/ops/job-applicants/{app_new.pk}/invite/", {}, format="json")
        self.assertEqual(res_new.status_code, status.HTTP_400_BAD_REQUEST)
        app_new.refresh_from_db()
        self.assertEqual(app_new.status, JobApplicant.Status.NEW)
        self.assertEqual(app_new.invitations.count(), 0)

        # متقدم rejected => 400
        app_rej = JobApplicant.objects.create(
            job=self.live_job,
            name="متقدم مرفوض",
            phone="0533333333",
            reference_code="REF-INV-REJ",
            status=JobApplicant.Status.REJECTED,
        )
        res_rej = self.client.post(f"/api/platform/ops/job-applicants/{app_rej.pk}/invite/", {}, format="json")
        self.assertEqual(res_rej.status_code, status.HTTP_400_BAD_REQUEST)
        app_rej.refresh_from_db()
        self.assertEqual(app_rej.status, JobApplicant.Status.REJECTED)
        self.assertEqual(app_rej.invitations.count(), 0)

        # متقدم offered => 201
        app_offered = JobApplicant.objects.create(
            job=self.live_job,
            name="مرشح معروض",
            phone="0544444444",
            email="offered@test.local",
            reference_code="REF-INV-OFFERED",
            status=JobApplicant.Status.OFFERED,
        )
        # فحص expires_in_hours غير صحيح: "abc" أو 0 أو 500 => 400
        for bad_hours in ("abc", 0, 500):
            res_bad = self.client.post(
                f"/api/platform/ops/job-applicants/{app_offered.pk}/invite/",
                {"expires_in_hours": bad_hours},
                format="json",
            )
            self.assertEqual(res_bad.status_code, status.HTTP_400_BAD_REQUEST)

        # إصدار دعوة أولى صالحة
        res_inv1 = self.client.post(
            f"/api/platform/ops/job-applicants/{app_offered.pk}/invite/",
            {"expires_in_hours": 72},
            format="json",
        )
        self.assertEqual(res_inv1.status_code, status.HTTP_201_CREATED)
        token1 = res_inv1.data["token"]
        inv1_id = res_inv1.data["invitation_id"]

        # رمزها على GET /api/careers/invitations/<token>/ يرد 200
        res_token1_check = self.client.get(f"/api/careers/invitations/{token1}/")
        self.assertEqual(res_token1_check.status_code, status.HTTP_200_OK)

        # إصدار دعوة ثانية للمتقدم نفسه
        res_inv2 = self.client.post(
            f"/api/platform/ops/job-applicants/{app_offered.pk}/invite/",
            {"expires_in_hours": 48},
            format="json",
        )
        self.assertEqual(res_inv2.status_code, status.HTTP_201_CREATED)

        # الأولى أصبحت revoked_at مكتوبة
        inv1 = JobApplicantInvitation.objects.get(pk=inv1_id)
        self.assertIsNotNone(inv1.revoked_at)
        self.assertTrue(inv1.is_revoked)
        self.assertTrue(inv1.is_consumed)

        # ورمزها على GET /api/careers/invitations/<token>/ يرد 410
        res_token1_gone = self.client.get(f"/api/careers/invitations/{token1}/")
        self.assertEqual(res_token1_gone.status_code, status.HTTP_410_GONE)

    def test_rejected_applicant_cannot_accept_invitation(self):
        """أ١. رفض المتقدم يبطل دعواته الحية وقبول الدعوة لمتقدم غير offered يرد 410 ولا ينشئ مستخدماً."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="مرشح مرفوض",
            phone="0555555555",
            email="rejected_candidate@example.com",
            status=JobApplicant.Status.OFFERED,
            reference_code="REF-REJ-INV-1",
        )
        invitation, raw_token = create_applicant_invitation(
            applicant=applicant,
            created_by=self.recruiter_user,
            expires_in_hours=72,
        )
        self.assertTrue(invitation.is_live)
        initial_user_count = User.objects.count()

        transition_applicant_status(
            applicant=applicant,
            target_status=JobApplicant.Status.REJECTED,
            actor=self.recruiter_user,
        )

        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.revoked_at)
        self.assertTrue(invitation.is_revoked)
        self.assertTrue(invitation.is_consumed)

        res_get = self.client.get(f"/api/careers/invitations/{raw_token}/")
        self.assertEqual(res_get.status_code, status.HTTP_410_GONE)

        res_post = self.client.post(
            f"/api/careers/invitations/{raw_token}/accept/",
            {"password": "ValidPassword123!", "username": "candidate_rejected_user"},
            format="json",
        )
        self.assertEqual(res_post.status_code, status.HTTP_410_GONE)

        self.assertEqual(User.objects.count(), initial_user_count)
        self.assertFalse(User.objects.filter(username="candidate_rejected_user").exists())

        applicant.refresh_from_db()
        self.assertEqual(applicant.status, JobApplicant.Status.REJECTED)
        self.assertIsNone(applicant.hired_employee)

    def test_patch_is_open_on_job_posting_is_ignored(self):
        """أ٢. PATCH على الإعلان بحقل is_open يتم تجاهله لأن الحقل للقراءة فقط."""
        job = JobPosting.objects.create(
            title="وظيفة تجريبية",
            token="test_patch_job_token_123",
            is_open=True,
            created_by=self.recruiter_user,
        )
        self.client.force_authenticate(user=self.recruiter_user)
        res = self.client.patch(
            f"/api/platform/ops/job-postings/{job.pk}/",
            {"is_open": False},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        job.refresh_from_db()
        self.assertTrue(job.is_open)
        self.assertIsNone(job.closed_at)

    def test_cv_download_arabic_filename_header(self):
        """أ٣. اسم السيرة العربي في Content-Disposition يحوي inline وfilename*=utf-8''."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="سالم أحمد",
            phone="0512345678",
            email="salem@example.com",
            reference_code="REF-SALEM-CV",
            cv_url="https://storage.platform.local/media/cvs/salem_cv.pdf",
            cv_name="سيرتي.pdf",
        )
        self.client.force_authenticate(user=self.recruiter_user)
        fake_upstream = mock.Mock()
        fake_upstream.headers = {"Content-Type": "application/pdf"}
        fake_upstream.raw = io.BytesIO(b"%PDF-1.4 stored arabic cv bytes %%EOF")
        fake_upstream.raise_for_status = mock.Mock()

        with mock.patch("platform_ops.views.requests.get", return_value=fake_upstream):
            res = self.client.get(f"/api/platform/ops/job-applicants/{applicant.pk}/cv/")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        disp = res.get("Content-Disposition", "")
        self.assertIn("inline", disp)
        self.assertIn("filename*=utf-8''", disp)

    def test_invitation_accept_password_validation(self):
        """أ٧. كلمة المرور تفحص ضد django validate_password وترد 400 على password."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="مرشح كلمة مرور",
            phone="0522222222",
            email="candidate_pwd@example.com",
            status=JobApplicant.Status.OFFERED,
            reference_code="REF-PWD-TEST",
        )
        _, raw_token = create_applicant_invitation(applicant=applicant, created_by=self.recruiter_user)

        res = self.client.post(
            f"/api/careers/invitations/{raw_token}/accept/",
            {"password": "password", "username": "pwd_user_test"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", res.data)

    def test_invitation_accept_username_collision_race_condition(self):
        """أ٧. سباق اسم المستخدم: IntegrityError داخل atomic savepoint يرفع ValidationError وليس 500."""
        applicant = JobApplicant.objects.create(
            job=self.live_job,
            name="مرشح سباق",
            phone="0533333333",
            email="candidate_race@example.com",
            status=JobApplicant.Status.OFFERED,
            reference_code="REF-RACE-TEST",
        )
        _, raw_token = create_applicant_invitation(applicant=applicant, created_by=self.recruiter_user)

        with mock.patch("django.contrib.auth.models.UserManager.create_user", side_effect=IntegrityError("duplicate username")):
            res = self.client.post(
                f"/api/careers/invitations/{raw_token}/accept/",
                {"password": "SecurePassword123!", "username": "race_user"},
                format="json",
            )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", res.data)


