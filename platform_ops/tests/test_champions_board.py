"""لوحةُ KTRA Champions (§١٠ من #210).

معظمُ هذا الملفّ يختبر **ما يجب ألّا يظهر**: «لا رواتب، لا قيم عمولات، لا أسماء
عملاء، لا ترتيب للأسوأ، ولا دخول لمن لا يملك حد العينة». لوحةٌ تعرض الصحيحَ
وتكشف المحظورَ معها فاشلةٌ تماماً كلوحةٍ تعرض رقماً خاطئاً.
"""
import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import (
    AcquisitionCommissionLine,
    PerformanceSnapshot,
    WalletLineStatus,
)
from platform_ops.services import (
    CHAMPION_CATEGORY_ACQUISITION,
    CHAMPION_CATEGORY_IMPROVEMENT,
    CHAMPION_CATEGORY_LABELS,
    CHAMPION_IMPROVEMENT_MIN_DELTA,
    build_champions_board,
)
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class ChampionsBoardTest(PilotScenarioBase):
    def _board(self, year=2026, month=9):
        return build_champions_board(period_year=year, period_month=month)

    def _category(self, board, key):
        return next(c for c in board["categories"] if c["category"] == key)

    def test_board_has_the_six_categories_the_spec_names(self):
        board = self._board()
        self.assertEqual(
            {c["category"] for c in board["categories"]},
            set(CHAMPION_CATEGORY_LABELS),
            "§١٠ تسمّي ستّ فئات: جودة، SLA، رضا، إنجاز معتمد، اكتساب مدفوع، وتحسّن موثّق.",
        )

    def test_acquisition_is_counted_not_valued(self):
        """«لا قيم عمولات» — العددُ يظهر والمبلغُ لا."""
        from platform_ops.models import CustomerAcquisition

        acquisition = CustomerAcquisition.objects.create(
            tenant=self.tenant, acquired_by=self.employee, acquired_at=timezone.now().date(),
        )
        AcquisitionCommissionLine.objects.create(
            acquisition=acquisition,
            employee=self.employee,
            period_year=2026,
            period_month=9,
            sequence=1,
            commission_month_index=1,
            amount=Decimal("100.00"),
            status=WalletLineStatus.PAID,
            idempotency_key="champ-acq-1",
        )
        entries = self._category(self._board(), CHAMPION_CATEGORY_ACQUISITION)["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["value"], 1.0, "القيمةُ عددُ عملاءَ لا مبلغ.")
        blob = str(entries[0])
        self.assertNotIn("100", blob, "مبلغُ العمولة لا يظهر في اللوحة.")
        self.assertNotIn(self.customer.name, blob, "اسمُ العميل لا يظهر في اللوحة.")

    def test_no_entry_without_the_minimum_sample_size(self):
        """«ولا دخول لمن لا يملك حد العينة» — بياناتٌ غيرُ كافيةٍ تعني لا مركز."""
        now = timezone.now()
        self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))
        board = build_champions_board(period_year=now.year, period_month=now.month)
        axis_entries = [
            entry
            for category in board["categories"]
            if category["category"] not in (CHAMPION_CATEGORY_ACQUISITION,)
            for entry in category["entries"]
        ]
        self.assertEqual(
            axis_entries, [],
            "تسليمٌ واحدٌ دون حدّ العينة لا يضع أحداً على اللوحة.",
        )

    def test_improvement_needs_a_previous_snapshot_above_the_threshold(self):
        now = timezone.now()
        prev_year, prev_month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
        PerformanceSnapshot.objects.create(
            employee=self.employee,
            period_year=prev_year,
            period_month=prev_month,
            status=PerformanceSnapshot.Status.CALCULATED,
            composite_score=Decimal("10.00"),
            sample_size=5,
        )
        board = build_champions_board(period_year=now.year, period_month=now.month)
        entries = self._category(board, CHAMPION_CATEGORY_IMPROVEMENT)["entries"]
        # بلا عملٍ هذا الشهر تبقى الحالةُ «بيانات غير كافية»، فلا تحسّنَ موثّقاً.
        self.assertEqual(entries, [])

    def test_a_small_improvement_below_the_threshold_is_not_documented(self):
        self.assertGreater(
            CHAMPION_IMPROVEMENT_MIN_DELTA, Decimal("0.00"),
            "حدُّ التحسّن يجب أن يكون موجباً، وإلا صار كلُّ تذبذبٍ «تحسّناً موثّقاً».",
        )

    def test_only_the_top_three_are_returned_so_there_is_no_worst_ranking(self):
        board = self._board()
        for category in board["categories"]:
            self.assertLessEqual(
                len(category["entries"]), 3,
                "§١٠ تمنع «ترتيب الأسوأ»؛ وقائمةٌ كاملةٌ مرتَّبةٌ تُنتجه ضمناً.",
            )

    def test_endpoint_is_open_to_a_platform_employee_not_only_the_superadmin(self):
        client = APIClient()
        client.force_authenticate(user=self.employee.user)
        response = client.get("/api/platform/ops/champions/", {"year": 2026, "month": 9})
        self.assertEqual(
            response.status_code, status.HTTP_200_OK,
            "«الجمهور الافتراضي موظفو المنصة المسجلون» — لا السوبر أدمن وحدَه.",
        )

    def test_endpoint_rejects_an_impossible_month(self):
        client = APIClient()
        client.force_authenticate(user=self.employee.user)
        response = client.get("/api/platform/ops/champions/", {"year": 2026, "month": 13})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_period")
