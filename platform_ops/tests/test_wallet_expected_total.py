"""الرقمُ الثالث في المحفظة: «متوقَّع» (§٧ من #210).

تطلب §٧ ثلاثةَ أرقامٍ لا اثنين — «تعرض المحفظة: مؤكد، معلق، متوقع» — وكان الخادمُ
يُرجع اثنين فحسب، فلا واجهةَ تستطيع عرضَ الثالث مهما اجتهدت.

والمتوقَّعُ **مشتقٌّ لا مُخترَع**: المؤكَّدُ زائدَ المعلَّق، أي حصيلةُ الشهر لو تحقّق
كلُّ شرطٍ ناقص. و`REVERSED` خارجَه كما هو خارجُ الآخرَين.
"""
import datetime
from decimal import Decimal

from django.utils import timezone

from platform_ops.models import EmployeeSalaryLine, WalletLineStatus
from platform_ops.services import get_employee_wallet_summary
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class WalletExpectedTotalTest(PilotScenarioBase):
    def _line(self, *, amount, status, sequence):
        now = timezone.now()
        return EmployeeSalaryLine.objects.create(
            employee=self.employee,
            period_year=now.year,
            period_month=now.month,
            sequence=sequence,
            amount=Decimal(amount),
            status=status,
            reason="اختبار",
            idempotency_key=f"test-expected-{sequence}",
        )

    def test_expected_is_confirmed_plus_pending_and_excludes_reversed(self):
        now = timezone.now()
        self._line(amount="500.00", status=WalletLineStatus.PAID, sequence=1)
        self._line(amount="100.00", status=WalletLineStatus.PENDING, sequence=2)
        self._line(amount="999.00", status=WalletLineStatus.REVERSED, sequence=3)

        totals = get_employee_wallet_summary(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )["totals"]

        self.assertEqual(totals["confirmed"], Decimal("500.00"))
        self.assertEqual(totals["pending"], Decimal("100.00"))
        self.assertEqual(
            totals["expected"],
            Decimal("600.00"),
            "المتوقَّع = المؤكَّد + المعلَّق، والسطرُ المعكوسُ خارجَه.",
        )

    def test_frontend_declares_the_expected_total(self):
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2] / "frontend_v2" / "services" / "platformPilotApi.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("expected: string", source, "واجهةُ totals يجب أن تعلن `expected`.")
