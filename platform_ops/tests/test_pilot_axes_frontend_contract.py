"""عقد الواجهة لمحاور تقييم الـpilot (التذكرتان 210-D §٥ و210-E §١).

`tsc` لا يفحص شكلَ ما يصل من الشبكة، فحقلٌ يُرجعه الخادمُ ولا تعلنه الواجهةُ يبقى
غيرَ مقروءٍ بصمت. وهذا بالضبط ما وقع: `weight_original_pct` أُضيف في 210-D كي لا
يقرأ الموظّفُ وزناً أُعيد توزيعُه ظانّاً أنّ السياسة وضعته، و`raw_percent` كي يُرى
الفائضُ فوق الطاقة بعد قصّ الدرجة عند ١٠٠، و`uncatalogued_document_links` كي لا
يُطرَح مقامٌ ناقصٌ صامتاً — وثلاثتُها لم تكن معلنةً في `PilotAxisBreakdown` فلم
تعرضها شاشةٌ قطّ.
"""
import datetime
from pathlib import Path

from django.utils import timezone

from platform_ops.services import calculate_employee_pilot_performance
from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class PilotAxesFrontendContractTest(PilotScenarioBase):
    def setUp(self):
        super().setUp()
        repo_root = Path(__file__).resolve().parents[2]
        self.api_source = (
            repo_root / "frontend_v2" / "services" / "platformPilotApi.ts"
        ).read_text(encoding="utf-8")

    def test_every_axis_key_the_server_emits_is_declared_by_the_interface(self):
        now = timezone.now()
        self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))
        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        declared = _interface_fields(self.api_source, "PilotAxisBreakdown")
        self.assertTrue(declared, "لم يُعثر على واجهة PilotAxisBreakdown.")
        for axis, detail in result["axes"].items():
            missing = set(detail) - declared
            self.assertEqual(
                missing,
                set(),
                f"محور {axis}: حقولٌ يُرجعها الخادم ولا تعلنها PilotAxisBreakdown: {sorted(missing)}",
            )

    def test_the_three_210d_fields_are_declared(self):
        declared = _interface_fields(self.api_source, "PilotAxisBreakdown")
        for field in ("weight_original_pct", "raw_percent", "uncatalogued_document_links"):
            self.assertIn(field, declared, field)
