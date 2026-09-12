"""إعادةُ التقاط اللقطة بعد قبول الاعتراض (القصة ٤٤، تتمّة 210-F).

قبولُ الاعتراض كان **وعداً بلا أثر**: `resolve_performance_review` لا تمسّ الدرجة
عمداً، و«ثمّ تُعاد اللقطة» لم يكن لها مسارٌ واحدٌ في النظام — `force_refresh`
موجودةٌ ولا يستدعيها إلا الإغلاق، والإغلاقُ idempotent فلا يُعيد الحساب. فشهرٌ
قُبل اعتراضُه كان يبقى بدرجته الخاطئة إلى الأبد.
"""
import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import PerformanceSnapshot, PlatformActivityLog
from platform_ops.services import (
    PlatformOpsError,
    capture_pilot_performance_snapshot,
    recapture_performance_after_accepted_review,
    request_performance_review,
    resolve_performance_review,
)
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class ReviewRecaptureTest(PilotScenarioBase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.year, self.month = now.year, now.month

    def _open_request(self):
        return request_performance_review(
            employee=self.employee,
            period_year=self.year,
            period_month=self.month,
            reason="وحدةٌ اعتُمدت لغيري",
        )

    def _accepted_request(self):
        return resolve_performance_review(
            review_request=self._open_request(),
            accepted=True,
            resolution_note="صحيح — سيُصحَّح الرابط ثمّ تُعاد اللقطة.",
            actor=self.admin,
        )

    # ── الخدمة ──────────────────────────────────────────────────────────────
    def test_an_open_request_cannot_recapture(self):
        """المبرِّرُ هو القبولُ لا الرتبة: طلبٌ مفتوحٌ لا يُعيد حساب شهر."""
        with self.assertRaises(PlatformOpsError) as ctx:
            recapture_performance_after_accepted_review(review_request=self._open_request(), actor=self.admin)
        self.assertEqual(ctx.exception.code, "review_request_not_accepted")

    def test_a_rejected_request_cannot_recapture(self):
        rejected = resolve_performance_review(
            review_request=self._open_request(), accepted=False,
            resolution_note="الدرجةُ صحيحة.", actor=self.admin,
        )
        with self.assertRaises(PlatformOpsError) as ctx:
            recapture_performance_after_accepted_review(review_request=rejected, actor=self.admin)
        self.assertEqual(ctx.exception.code, "review_request_not_accepted")

    def test_recapture_refreshes_the_frozen_snapshot(self):
        """اللقطةُ تُجمَّد عمداً — وهذا هو المسارُ الوحيدُ المشروعُ لإذابتها."""
        self._approve_one_deliverable(received_at=timezone.now() - datetime.timedelta(minutes=20))
        frozen = capture_pilot_performance_snapshot(
            employee=self.employee, period_year=self.year, period_month=self.month, captured_by=self.admin,
        )
        captured_at_before = frozen.captured_at

        accepted = self._accepted_request()
        refreshed = recapture_performance_after_accepted_review(review_request=accepted, actor=self.admin)

        self.assertEqual(refreshed.pk, frozen.pk, "تُحدَّث اللقطةُ نفسُها لا تُنشأ ثانيةٌ تنافسها.")
        self.assertGreater(refreshed.captured_at, captured_at_before)
        self.assertEqual(
            PerformanceSnapshot.objects.filter(
                employee=self.employee, period_year=self.year, period_month=self.month,
            ).count(),
            1,
            "لقطةٌ واحدةٌ للشهر — وإلاّ صار للشهر درجتان.",
        )

    def test_recapture_reads_corrected_data_not_the_old_number(self):
        """التصحيحُ عند المصدر هو ما يغيّر الرقم — وإلاّ فالزرُّ زينة."""
        _, _, events = self._approve_one_deliverable(received_at=timezone.now() - datetime.timedelta(minutes=20))
        frozen = capture_pilot_performance_snapshot(
            employee=self.employee, period_year=self.year, period_month=self.month, captured_by=self.admin,
        )
        before_axes = dict(frozen.axes_data or {})
        before_numerator = (before_axes.get("task_completion") or {}).get("numerator")

        # تصحيحٌ عند المصدر: عكسُ حدث الاستخدام عبر مساره الرسميّ.
        from platform_ops.services import reverse_usage_event
        reverse_usage_event(usage_event=events[0], reason="نُسب لغير صاحبه", actor=self.admin)

        refreshed = recapture_performance_after_accepted_review(
            review_request=self._accepted_request(), actor=self.admin,
        )
        after_numerator = ((refreshed.axes_data or {}).get("task_completion") or {}).get("numerator")
        self.assertNotEqual(after_numerator, before_numerator, "اللقطةُ لم تقرأ التصحيح.")
        self.assertEqual(Decimal(str(after_numerator or 0)), Decimal("0.00"))

    def test_recapture_is_logged_with_the_score_before_and_after(self):
        """تغييرُ درجةٍ بلا «قبلُ وبعدُ» في السجلّ لا يُراجَع."""
        self._approve_one_deliverable(received_at=timezone.now() - datetime.timedelta(minutes=20))
        capture_pilot_performance_snapshot(
            employee=self.employee, period_year=self.year, period_month=self.month, captured_by=self.admin,
        )
        accepted = self._accepted_request()
        recapture_performance_after_accepted_review(review_request=accepted, actor=self.admin)

        log = PlatformActivityLog.objects.filter(entity_type="performance_snapshot").order_by("-id").first()
        self.assertIsNotNone(log, "إعادةُ حسابٍ بلا سجلٍّ نشاطٍ لا أثرَ لها.")
        self.assertEqual(log.details.get("operation"), "recapture_performance_after_accepted_review")
        self.assertEqual(log.details.get("actor_user_id"), self.admin.pk)
        self.assertEqual(log.details.get("review_request_id"), accepted.pk)
        self.assertIn("composite_before", log.details)
        self.assertIn("composite_after", log.details)

    def test_the_wallet_is_untouched_by_a_recapture(self):
        """أسطرُ الشهر قد تكون مدفوعة — تصحيحُها بسطر تسويةٍ ظاهر لا بكتابةٍ فوقها."""
        from platform_ops.models import EmployeeSalaryLine
        from platform_ops.services import close_compensation_month

        self._approve_one_deliverable(received_at=timezone.now() - datetime.timedelta(minutes=20))
        close_compensation_month(period_year=self.year, period_month=self.month, actor=self.admin)
        before = list(
            EmployeeSalaryLine.objects.filter(
                employee=self.employee, period_year=self.year, period_month=self.month,
            ).values_list("pk", "amount", "status").order_by("pk")
        )
        self.assertTrue(before, "لا سطرَ محفظةٍ لنُثبت أنّه لم يُمَسّ.")

        recapture_performance_after_accepted_review(
            review_request=self._accepted_request(), actor=self.admin,
        )
        after = list(
            EmployeeSalaryLine.objects.filter(
                employee=self.employee, period_year=self.year, period_month=self.month,
            ).values_list("pk", "amount", "status").order_by("pk")
        )
        self.assertEqual(after, before)

    def test_recapture_keeps_the_month_on_its_own_frozen_policy(self):
        """«لا أثر رجعي» (210-D): التصحيحُ يمسّ البيانات لا المقياس.

        اعتراضٌ يُقبَل اليومَ على شهرٍ مضى كان يُعيد تسعيرَه بأوزانِ سياسةٍ نُشرت
        **بعده** ويمحو نسختَه المجمَّدة — وتجميدُ اللقطة إنّما بُني ليمنع هذا.
        """
        from platform_ops.services import (
            activate_performance_evaluation_policy,
            create_performance_evaluation_policy_draft,
        )

        self._approve_one_deliverable(received_at=timezone.now() - datetime.timedelta(minutes=20))
        frozen = capture_pilot_performance_snapshot(
            employee=self.employee, period_year=self.year, period_month=self.month, captured_by=self.admin,
        )
        weights_before = dict((frozen.policy_snapshot or {}).get("weights") or {})
        self.assertTrue(weights_before, "لقطةٌ بلا أوزانٍ مجمَّدةٍ لا تُثبت شيئاً.")

        # سياسةٌ جديدةٌ تُنشر بعد اللقطة بأوزانٍ مختلفةٍ تماماً.
        draft = create_performance_evaluation_policy_draft(
            actor=self.admin,
            weights={
                "task_completion": "10.00", "quality_accuracy": "20.00",
                "sla_adherence": "30.00", "customer_satisfaction": "40.00",
            },
        )
        activate_performance_evaluation_policy(
            policy=draft, actor=self.admin, activation_reason="مقياسٌ جديدٌ للشهر القادم",
        )

        refreshed = recapture_performance_after_accepted_review(
            review_request=self._accepted_request(), actor=self.admin,
        )
        self.assertEqual(
            dict((refreshed.policy_snapshot or {}).get("weights") or {}), weights_before,
            "أُعيد تسعيرُ الشهر بأوزانِ سياسةٍ نُشرت بعده — أثرٌ رجعيّ.",
        )

    # ── النقطة ──────────────────────────────────────────────────────────────
    def test_endpoint_is_manager_only(self):
        accepted = self._accepted_request()
        url = reverse("platform-ops-performance-review-requests-recapture", args=[accepted.pk])
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        response = client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "manager_only")

        client.force_authenticate(user=self.admin)
        ok = client.post(url, {}, format="json")
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data["id"], PerformanceSnapshot.objects.get().pk)
        self.assertIn("composite_score", ok.data)

    def test_endpoint_refuses_an_unaccepted_request_with_its_code(self):
        opened = self._open_request()
        url = reverse("platform-ops-performance-review-requests-recapture", args=[opened.pk])
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "review_request_not_accepted")
