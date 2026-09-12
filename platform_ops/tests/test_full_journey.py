"""الرحلةُ الكاملةُ عبر الطبقات الحقيقيّة، وحارسُ نصوصِ الـE2E (210-F).

**لماذا هذا الملفّ موجودٌ إلى جانب `frontend_v2/e2e/platform-ops-full-journey.spec.ts`؟**

ذاك الاختبارُ يُموّه الشبكةَ بالكامل: يؤكّد على نصوصٍ **كتبَها هو** في الـmock،
فيبقى أخضرَ ولو تغيّر الخادمُ كلُّه. وهو نافعٌ لما بُني له — إثباتِ وصلة الواجهة
والمسارات — وعاجزٌ بنيوياً عن إثبات الرحلة نفسِها.

فهنا نصفُ العقد الآخر:

١. **الرحلةُ عبر الخدمات الحقيقيّة** — لا mock: اعتمادُ مُسلَّمٍ يولّد وحدةً في
   الدفتر، والوحدةُ تدخل محورَ الإنجاز، والإغلاقُ يولّد أسطرَ المحفظة، وChampions
   والربحيّةُ يقرآن ما تولّد. كلُّ حلقةٍ تنكسر يسقط هذا الاختبار.

٢. **حارسُ نصوص الـE2E** — يقرأ ملفَّ Playwright نفسَه ويقابل كلَّ تسميةٍ
   مُموَّهةٍ فيه بثوابت الخادم. أمسك عند كتابته أربعةَ نصوصٍ مُلفَّقة: فئةً
   (`customer_acquisition`) وفئةً (`fastest_delivery`) لا وجودَ لهما أصلاً،
   و«مربحة» بدل «مربح»، و«اقتراح شراء وحدات إضافية» بدل «شراء وحدات إضافية» —
   والاختبارُ المُموَّهُ كان أخضرَ عليها كلِّها.
"""
import datetime
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import timezone

from platform_ops.models import (
    AcquisitionCommissionLine,
    EmployeeSalaryLine,
    PerformanceSnapshot,
    ServiceUsageEvent,
    ServiceSubscription,
    WalletLineStatus,
    WorkOrderDeliverable,
)
from platform_ops.services import (
    CHAMPION_CATEGORY_LABELS,
    PLAN_FIT_LABELS,
    PROFITABILITY_LABELS,
    build_champions_board,
    calculate_employee_pilot_performance,
    close_compensation_month,
    compute_customer_profitability,
)
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class FullJourneyTest(PilotScenarioBase):
    """تفعيلٌ ← أمرُ عملٍ ← ربطٌ ← تسليمٌ ← اعتمادٌ ← وحدةٌ ← تقييمٌ ← محفظةٌ ← Champions ← ربحيّة."""

    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.year, self.month = now.year, now.month
        ServiceSubscription.objects.filter(pk=self.sub.pk).update(
            monthly_fee=Decimal("400.00"), included_quota=2, overage_unit_price=Decimal("25.00"),
        )
        self.sub.refresh_from_db()

    def test_the_journey_holds_from_approval_to_profitability(self):
        now = timezone.now()
        received = now - datetime.timedelta(hours=2)

        # ── ١) الاعتمادُ يولّد وحدةً في الدفتر ────────────────────────────
        before = ServiceUsageEvent.objects.count()
        _, deliverable, events = self._approve_one_deliverable(received_at=received)
        self.assertEqual(ServiceUsageEvent.objects.count(), before + 1, "الاعتمادُ يولّد حدثَ استخدامٍ واحداً.")
        event = events[0]
        self.assertTrue(event.chargeable_to_customer)
        self.assertTrue(event.creditable_to_employee)
        self.assertEqual(event.employee_id, self.employee.pk)
        self.assertGreater(event.units, Decimal("0.00"), "وحدةٌ بصفرٍ تعني كتالوجاً لم يُطبَّق.")

        # ── ٢) الوحدةُ تدخل محورَ الإنجاز ─────────────────────────────────
        perf = calculate_employee_pilot_performance(
            employee=self.employee, period_year=self.year, period_month=self.month,
        )
        completion = perf["axes"]["task_completion"]
        self.assertTrue(completion["applicable"], "وحدةٌ معتمَدةٌ ولا محورَ إنجازٍ منطبق: الحلقةُ مقطوعة.")
        self.assertEqual(
            Decimal(str(completion["numerator"])), event.units,
            "بسطُ المحور هو وحداتُ الدفتر عينُها لا رقمٌ يُعاد اشتقاقه.",
        )
        self.assertGreater(completion["denominator"], 0, "المقامُ وحداتُ المُسنَد — صفرٌ يعني أنّ الربطَ لم يُقيَّم.")

        # ── ٣) الإغلاقُ الشهريّ يلتقط اللقطةَ ويولّد المحفظة ─────────────
        close, created = close_compensation_month(
            period_year=self.year, period_month=self.month, actor=self.admin,
        )
        self.assertTrue(created)
        snapshot = PerformanceSnapshot.objects.filter(
            employee=self.employee, period_year=self.year, period_month=self.month,
        ).first()
        self.assertIsNotNone(snapshot, "الإغلاقُ بلا لقطةٍ يترك الشهرَ بلا تقييمٍ مجمَّد.")
        self.assertTrue(
            EmployeeSalaryLine.objects.filter(
                employee=self.employee, period_year=self.year, period_month=self.month,
            ).exists(),
            "الإغلاقُ يولّد سطرَ راتبٍ للموظّف النشط.",
        )

        # الإغلاقُ idempotent: نداءٌ ثانٍ لا يضاعف سطراً مالياً.
        salary_count = EmployeeSalaryLine.objects.count()
        commission_count = AcquisitionCommissionLine.objects.count()
        again, created_again = close_compensation_month(
            period_year=self.year, period_month=self.month, actor=self.admin,
        )
        self.assertFalse(created_again)
        self.assertEqual(again.pk, close.pk)
        self.assertEqual(EmployeeSalaryLine.objects.count(), salary_count)
        self.assertEqual(AcquisitionCommissionLine.objects.count(), commission_count)

        # ── ٤) Champions يقرأ ما تولّد ───────────────────────────────────
        board = build_champions_board(period_year=self.year, period_month=self.month)
        self.assertEqual(
            {c["category"] for c in board["categories"]}, set(CHAMPION_CATEGORY_LABELS),
            "الفئاتُ الستُّ ثابتةٌ لا تتغيّر ببيانات الشهر.",
        )

        # ── ٥) الربحيّةُ تقرأ نفسَ الوحدة ────────────────────────────────
        rows = compute_customer_profitability(period_year=self.year, period_month=self.month)
        row = next(r for r in rows if r["tenant_id"] == self.tenant.pk)
        self.assertEqual(
            Decimal(str(row["chargeable_units"])), event.units,
            "وحداتُ الربحيّة هي وحداتُ الدفتر عينُها — لا حسابٌ موازٍ.",
        )
        self.assertEqual(row["revenue"], 400.0, "وحدةٌ واحدةٌ دون حصّةِ اثنتين: رسمٌ بلا تجاوز.")
        self.assertIn(row["state"], PROFITABILITY_LABELS)
        self.assertTrue(
            row["contributors"], "تكلفةٌ بشريّةٌ بلا مساهمين تعني رقماً لا يُفتَح إلى مصدره.",
        )
        self.assertEqual(row["contributors"][0]["employee_id"], self.employee.pk)

    def test_a_reversed_usage_event_unwinds_the_same_chain(self):
        """العكسُ ليس حذفاً — ولا بدّ أن يَسري في المحور والربحيّة معاً."""
        from platform_ops.services import reverse_usage_event

        _, _, events = self._approve_one_deliverable(received_at=timezone.now() - datetime.timedelta(hours=1))
        event = events[0]
        before = compute_customer_profitability(period_year=self.year, period_month=self.month)
        before_units = next(r for r in before if r["tenant_id"] == self.tenant.pk)["chargeable_units"]

        reverse_usage_event(usage_event=event, reason="اعتراضٌ مقبول", actor=self.admin)

        after = compute_customer_profitability(period_year=self.year, period_month=self.month)
        after_row = next(r for r in after if r["tenant_id"] == self.tenant.pk)
        self.assertEqual(after_row["chargeable_units"], 0.0, "العكسُ يطرح؛ وإلا شُحن العميلُ ضِعفاً.")
        self.assertGreater(before_units, 0.0)

        perf = calculate_employee_pilot_performance(
            employee=self.employee, period_year=self.year, period_month=self.month,
        )
        self.assertEqual(
            Decimal(str(perf["axes"]["task_completion"]["numerator"])), Decimal("0.00"),
            "وحدةٌ عُكست لا تبقى إنجازاً في التقييم.",
        )


class E2EMockLabelsMatchServerTest(SimpleTestCase):
    """حارسُ نصوصِ الاختبارِ المُموَّه — الحمايةُ الوحيدةُ من تلفيقٍ أخضر.

    اختبارُ Playwright يكتب ردودَه بنفسه، فتسميةٌ مُخترَعةٌ فيه تمرّ بلا أثر ثمّ
    تُقرأ توثيقاً لسلوكٍ لا وجودَ له. هذا الحارسُ يقابل كلَّ تسميةٍ في ذلك الملفّ
    بثوابت الخادم: إن اخترع الملفُّ فئةً أو غيّر تسميةً، سقط هنا.
    """

    SPEC = Path(settings.BASE_DIR) / "frontend_v2" / "e2e" / "platform-ops-full-journey.spec.ts"

    def _spec_text(self) -> str:
        self.assertTrue(self.SPEC.exists(), f"ملفُّ الرحلة غائب: {self.SPEC}")
        return self.SPEC.read_text(encoding="utf-8")

    #: (تعبيرُ الالتقاط، خريطةُ الخادم، اسمٌ للرسالة) — شكلٌ واحدٌ لكلّ الحقول
    #: المقترنة `مفتاح/تسمية` في الـmock، بدل ثلاثِ طرائقَ متطابقةِ الشكل.
    def _pairs(self, pattern: str):
        return re.findall(pattern, self._spec_text())

    def _assert_pairs_match(self, *, pattern: str, server_map: dict, what: str, required: bool = True):
        pairs = self._pairs(pattern)
        if required:
            self.assertTrue(pairs, f"لا {what} في ملفّ الرحلة — إمّا حُذف التبويب أو تغيّر الشكل.")
        for key, label in pairs:
            with self.subTest(**{what: key}):
                self.assertIn(key, server_map, f"{what} لا يُرجعه الخادم: {key}")
                self.assertEqual(str(server_map[key]), label, f"تسميةُ {key} تخالف الخادم.")

    def test_champion_categories_in_the_mock_exist_on_the_server(self):
        self._assert_pairs_match(
            pattern=r'category:\s*"([^"]+)",\s*category_label:\s*"([^"]+)"',
            server_map=CHAMPION_CATEGORY_LABELS, what="فئةَ Champions",
        )

    def test_profitability_states_in_the_mock_exist_on_the_server(self):
        self._assert_pairs_match(
            pattern=r'state:\s*"([^"]+)",\s*state_label:\s*"([^"]+)"',
            server_map=PROFITABILITY_LABELS, what="حالةَ ربحيّة",
        )

    def test_plan_fit_suggestions_in_the_mock_exist_on_the_server(self):
        self._assert_pairs_match(
            pattern=r'code:\s*"([^"]+)",\s*label:\s*"([^"]+)"',
            server_map=PLAN_FIT_LABELS, what="اقتراحَ مطابقةِ خطّة",
        )

    def test_deliverable_review_labels_in_the_mock_exist_on_the_server(self):
        """أمسك «قيد المراجعة» و«معتمَد» و«مردود» — والخادمُ يقول «بانتظار المراجعة»
        و«مقبول» و«مرفوض». ثلاثةُ تأكيداتٍ خضراءَ على نصٍّ لا يُرجعه الخادمُ قطّ."""
        self._assert_pairs_match(
            pattern=r'review_status:\s*"([^"]+)",\s*review_status_display:\s*"([^"]+)"',
            server_map=dict(WorkOrderDeliverable.ReviewStatus.choices), what="حالةَ مراجعةِ مُسلَّم",
        )
        # الإسناداتُ اللاحقةُ على الكائن نفسِه (`deliverable.review_status_display = ...`)
        # لا يلتقطها الاقترانُ أعلاه، فتُقابَل بالتسميات المشروعة وحدَها.
        standalone = re.findall(r'review_status_display\s*=\s*"([^"]+)"', self._spec_text())
        allowed = set(dict(WorkOrderDeliverable.ReviewStatus.choices).values())
        for label in standalone:
            with self.subTest(label=label):
                self.assertIn(label, allowed, f"تسميةُ مراجعةٍ لا يُرجعها الخادم: {label}")

    def test_wallet_and_subscription_labels_in_the_mock_exist_on_the_server(self):
        self._assert_pairs_match(
            pattern=r'status:\s*"(pending|eligible|approved|payable|paid|reversed)",\s*status_display:\s*"([^"]+)"',
            server_map=dict(WalletLineStatus.choices), what="حالةَ سطرِ محفظة", required=False,
        )
        self._assert_pairs_match(
            pattern=r'status:\s*"(trial|active|suspended|cancelled)",\s*status_display:\s*"([^"]+)"',
            server_map=dict(ServiceSubscription.Status.choices), what="حالةَ اشتراك", required=False,
        )
