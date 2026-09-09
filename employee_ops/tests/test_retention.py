"""أجلُ الاحتفاظ ببيانات المتقدّمين المرفوضين (المواصفة #186 — §٨).

`rejected_retention_months` كان حقلاً في الجدول وشاشةً في الإعدادات **بلا قارئ**:
وعدٌ للشركة بحذفٍ لا يقع. وهذه الاختباراتُ تحرس الوعدَ نفسَه لا وجودَ الحقل.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.models import TenantModule
from core.modules import invalidate_module_cache
from employee_ops.management.commands.purge_rejected_applicants import (
    Command as PurgeCommand,
)
from employee_ops.models import EmployeeOpsSettings, JobApplicant, JobPosting
from tenants.models import Currency
from tenants.services import create_company

CV_URL = "https://res.cloudinary.com/test/raw/upload/old-cv.pdf"


def run_purge(*args, **kwargs):
    command = PurgeCommand()
    call_command(command, *args, **kwargs)
    return command.stats


class RetentionPurgeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager = User.objects.create_user(username="purge_mgr", password="x")
        cls.tenant = create_company("شركة الاحتفاظ", cls.manager)
        TenantModule.objects.create(
            tenant=cls.tenant, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(cls.tenant.pk)
        cls.job = JobPosting.objects.create(
            tenant=cls.tenant, title="وظيفة", description="وصف", token="tok-purge"
        )

    def setUp(self):
        self.settings_row, _ = EmployeeOpsSettings.objects.get_or_create(
            tenant=self.tenant
        )
        self.patcher = mock.patch(
            "employee_ops.management.commands.purge_rejected_applicants."
            "destroy_cloudinary_asset",
            return_value=True,
        )
        self.destroy = self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def _applicant(self, *, status, months_ago, reference, cv_url=""):
        applicant = JobApplicant.objects.create(
            tenant=self.tenant,
            job=self.job,
            name="متقدم",
            phone="0599",
            status=status,
            cv_url=cv_url,
            reference_code=reference,
        )
        # `auto_now` يدهس أيَّ قيمةٍ تُمرَّر للحقل، فالتقادمُ يُكتب بـ`update`.
        JobApplicant.objects.filter(pk=applicant.pk).update(
            updated_at=timezone.now() - timedelta(days=months_ago * 30 + 1)
        )
        return applicant

    def test_a_rejected_applicant_past_the_window_is_deleted_with_their_cv(self):
        old = self._applicant(
            status=JobApplicant.STATUS_REJECTED,
            months_ago=13,
            reference="OLD1",
            cv_url=CV_URL,
        )
        stats = run_purge()

        self.assertFalse(JobApplicant.objects.filter(pk=old.pk).exists())
        self.assertEqual(stats["deleted"], 1)
        # **الحذفُ يشمل الملفّ**: صفٌّ محذوفٌ وسيرةٌ حيّةٌ على المزوّد يعني بياناً
        # شخصيّاً باقياً، ورابطُه هو الصلاحية.
        self.destroy.assert_called_once_with(CV_URL)
        self.assertEqual(stats["files_deleted"], 1)

    def test_a_rejected_applicant_inside_the_window_survives(self):
        """وإلا كان الاختبارُ أعلاه يمرّ لأنّ الأمرَ يحذف كلَّ مرفوض."""
        fresh = self._applicant(
            status=JobApplicant.STATUS_REJECTED, months_ago=2, reference="FRESH1"
        )
        stats = run_purge()

        self.assertTrue(JobApplicant.objects.filter(pk=fresh.pk).exists())
        self.assertEqual(stats["deleted"], 0)

    def test_only_rejected_applicants_are_purged(self):
        """المرفوضُ وحده — لا القديمُ مهما قدُم."""
        keepers = [
            self._applicant(status=status, months_ago=24, reference=f"K{i}")
            for i, status in enumerate(
                [
                    JobApplicant.STATUS_NEW,
                    JobApplicant.STATUS_INTERVIEW,
                    JobApplicant.STATUS_HIRED,
                ]
            )
        ]
        run_purge()
        for applicant in keepers:
            self.assertTrue(
                JobApplicant.objects.filter(pk=applicant.pk).exists(),
                f"حالة {applicant.status} لا تخضع لأجل الاحتفاظ",
            )

    def test_zero_months_means_never_delete_not_delete_now(self):
        """**الصفرُ قرارُ احتفاظٍ لا أمرُ محو.** خلطُهما يمحو بياناتِ من اختار البقاء."""
        self.settings_row.rejected_retention_months = 0
        self.settings_row.save(update_fields=["rejected_retention_months"])

        ancient = self._applicant(
            status=JobApplicant.STATUS_REJECTED, months_ago=120, reference="ANC1"
        )
        stats = run_purge()

        self.assertTrue(JobApplicant.objects.filter(pk=ancient.pk).exists())
        self.assertEqual(stats["deleted"], 0)
        self.assertEqual(stats["tenants_disabled"], 1)

    def test_the_window_follows_the_company_setting_not_a_constant(self):
        """أجلٌ مثبَّتٌ في الكود يجعل الإعدادَ زينةً — هذا ما يمنعه هذا الاختبار."""
        self.settings_row.rejected_retention_months = 3
        self.settings_row.save(update_fields=["rejected_retention_months"])

        five_months = self._applicant(
            status=JobApplicant.STATUS_REJECTED, months_ago=5, reference="M5"
        )
        run_purge()
        self.assertFalse(
            JobApplicant.objects.filter(pk=five_months.pk).exists(),
            "بأجل ٣ أشهر يجب أن يُحذف من عمره ٥ — ولو كان الأجلُ مثبَّتاً على ١٢ لبقي",
        )

    def test_a_dry_run_deletes_nothing_and_touches_no_file(self):
        old = self._applicant(
            status=JobApplicant.STATUS_REJECTED,
            months_ago=13,
            reference="DRY1",
            cv_url=CV_URL,
        )
        stats = run_purge("--dry-run")

        self.assertTrue(JobApplicant.objects.filter(pk=old.pk).exists())
        self.destroy.assert_not_called()
        self.assertEqual(stats["deleted"], 1, "المعاينة تعدّ ما كان سيُحذف")

    def test_the_purge_never_crosses_the_company_line(self):
        other_mgr = User.objects.create_user(username="purge_mgr_b", password="x")
        other = create_company("شركة أخرى", other_mgr)
        EmployeeOpsSettings.objects.get_or_create(tenant=other)
        other_job = JobPosting.objects.create(
            tenant=other, title="وظيفة", description="وصف", token="tok-purge-b"
        )
        outsider = JobApplicant.objects.create(
            tenant=other,
            job=other_job,
            name="غريب",
            phone="0598",
            status=JobApplicant.STATUS_REJECTED,
            reference_code="OUT1",
        )
        JobApplicant.objects.filter(pk=outsider.pk).update(
            updated_at=timezone.now() - timedelta(days=400)
        )
        mine = self._applicant(
            status=JobApplicant.STATUS_REJECTED, months_ago=13, reference="MINE1"
        )

        run_purge("--tenant", str(self.tenant.pk))

        self.assertFalse(JobApplicant.objects.filter(pk=mine.pk).exists())
        self.assertTrue(
            JobApplicant.objects.filter(pk=outsider.pk).exists(),
            "تشغيلٌ مقصورٌ على شركةٍ لا يلمس غيرَها",
        )
