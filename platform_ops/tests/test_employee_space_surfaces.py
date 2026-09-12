"""سطحُ الموظّف: شركاتُه وحصصُها وبنودُ صحّتِه، واعتراضُه على نتيجته.

القصص ٣٩ و٤٠ و٤٤ من #210 (التذكرة 210-E) — ثلاثُها كانت بلا أيّ سطحٍ خادميٍّ أو
واجهةٍ قبل هذا الملفّ.
"""
import datetime

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import (
    CompanyHealthCheck,
    CompanyHealthCheckItem,
    PerformanceReviewRequest,
)
from platform_ops.services import (
    list_employee_engaged_companies,
    request_performance_review,
    resolve_performance_review,
)
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class EmployeeEngagedCompaniesTest(PilotScenarioBase):
    """القصّتان ٣٩ و٤٠."""

    def _approved_check(self):
        """فحصٌ معتمَدٌ واحدٌ للشركة — بنودُه كلُّها تحته.

        **ولا فحصٌ لكلّ بند**: الخدمةُ تقرأ أحدثَ فحصٍ معتمدٍ لكلّ شركة، ففحوصٌ
        متعدّدةٌ تعني أنّ بنودَ الأقدم تسقط — وهو سلوكٌ مقصود، لا فخٌّ للاختبار.
        """
        return CompanyHealthCheck.objects.create(
            tenant=self.tenant,
            kind=CompanyHealthCheck.Kind.BASELINE,
            status=CompanyHealthCheck.Status.APPROVED,
            period=datetime.date(2026, 9, 1),
            approved_at=timezone.now(),
        )

    def _item(self, check, *, owner, item_status, code):
        return CompanyHealthCheckItem.objects.create(
            health_check=check,
            code=code,
            status=item_status,
            owner=owner,
            action="راجع القيود غير المرحّلة",
            due_date=datetime.date(2026, 9, 30),
        )

    def test_quota_is_reported_and_remaining_never_goes_negative(self):
        sub = self.sub
        sub.included_quota = 10
        sub.consumed_quota = 17
        sub.save(update_fields=["included_quota", "consumed_quota"])

        rows = list_employee_engaged_companies(self.employee.user)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["included_quota"], 10)
        self.assertEqual(row["consumed_quota"], 17)
        self.assertEqual(
            row["remaining_quota"], 0,
            "«المتبقّي» كميّةٌ لا تكون سالبة؛ التجاوزُ يُقرأ من over_quota.",
        )
        self.assertEqual(row["over_quota"], 7)

    def test_only_items_owned_by_this_employee_and_needing_action_are_listed(self):
        check = self._approved_check()
        mine = self._item(
            check, owner=self.employee.user,
            item_status=CompanyHealthCheckItem.ItemStatus.RISK, code="risky_mine",
        )
        # بندٌ سليمٌ لي: ليس «مطلوباً منّي علاجُه».
        self._item(
            check, owner=self.employee.user,
            item_status=CompanyHealthCheckItem.ItemStatus.HEALTHY, code="healthy_mine",
        )
        # بندٌ خَطِرٌ لكنّه لزميل: ليس شغلي.
        self._item(
            check, owner=self.admin,
            item_status=CompanyHealthCheckItem.ItemStatus.RISK, code="risky_other",
        )

        rows = list_employee_engaged_companies(self.employee.user)
        codes = [item["code"] for item in rows[0]["health_items"]]
        self.assertEqual(codes, [mine.code], f"البنودُ المعروضة: {codes}")

    def test_draft_check_items_are_not_shown(self):
        draft = CompanyHealthCheck.objects.create(
            tenant=self.tenant,
            kind=CompanyHealthCheck.Kind.BASELINE,
            status=CompanyHealthCheck.Status.DRAFT,
            period=datetime.date(2026, 9, 1),
        )
        CompanyHealthCheckItem.objects.create(
            health_check=draft,
            code="draft_item",
            status=CompanyHealthCheckItem.ItemStatus.RISK,
            owner=self.employee.user,
        )
        rows = list_employee_engaged_companies(self.employee.user)
        self.assertEqual(
            rows[0]["health_items"], [],
            "مسودّةُ الفحص قد تُعدَّل أو تُلغى، فعرضُها يُحمّل الموظّفَ عملاً لم يُعتمد.",
        )

    def test_endpoint_rejects_an_explicit_company_argument(self):
        client = APIClient()
        client.force_authenticate(user=self.employee.user)
        response = client.get("/api/platform/ops/employees/my-companies/", {"tenant": self.tenant.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "cross_tenant_query_disallowed_from_request")


class PerformanceReviewRequestTest(PilotScenarioBase):
    """القصة ٤٤."""

    def test_reason_is_required(self):
        from platform_ops.services import PlatformOpsError

        with self.assertRaises(PlatformOpsError) as ctx:
            request_performance_review(
                employee=self.employee, period_year=2026, period_month=9, reason="   ",
            )
        self.assertEqual(ctx.exception.code, "reason_required")

    def test_a_second_open_request_for_the_same_period_is_refused(self):
        from platform_ops.services import PlatformOpsError

        request_performance_review(
            employee=self.employee, period_year=2026, period_month=9, reason="تصنيفُ ردٍّ خاطئ",
        )
        with self.assertRaises(PlatformOpsError) as ctx:
            request_performance_review(
                employee=self.employee, period_year=2026, period_month=9, reason="مرّةً أخرى",
            )
        self.assertEqual(ctx.exception.code, "review_request_already_open")

    def test_a_new_request_is_allowed_after_the_previous_one_was_resolved(self):
        first = request_performance_review(
            employee=self.employee, period_year=2026, period_month=9, reason="اعتراضٌ أوّل",
        )
        resolve_performance_review(
            review_request=first, accepted=False, resolution_note="لا خطأ في البيانات.",
        )
        second = request_performance_review(
            employee=self.employee, period_year=2026, period_month=9, reason="دليلٌ جديد",
        )
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(
            PerformanceReviewRequest.objects.filter(employee=self.employee).count(), 2,
            "لا حذفَ لصفٍّ: الاعتراضُ وردُّه تاريخٌ يُقرأ لاحقاً.",
        )

    def test_resolving_twice_is_refused(self):
        from platform_ops.services import PlatformOpsError

        row = request_performance_review(
            employee=self.employee, period_year=2026, period_month=9, reason="سبب",
        )
        resolve_performance_review(review_request=row, accepted=True, resolution_note="صُحِّح المصدر.")
        with self.assertRaises(PlatformOpsError) as ctx:
            resolve_performance_review(review_request=row, accepted=False, resolution_note="مرّة أخرى")
        self.assertEqual(ctx.exception.code, "review_request_not_open")

    def test_employee_cannot_resolve_own_request(self):
        row = request_performance_review(
            employee=self.employee, period_year=2026, period_month=9, reason="سبب",
        )
        client = APIClient()
        client.force_authenticate(user=self.employee.user)
        response = client.post(
            f"/api/platform/ops/performance-review-requests/{row.pk}/resolve/",
            {"accepted": True, "resolution_note": "أقبل اعتراضي بنفسي"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "manager_only")
        row.refresh_from_db()
        self.assertEqual(row.status, PerformanceReviewRequest.Status.OPEN)
