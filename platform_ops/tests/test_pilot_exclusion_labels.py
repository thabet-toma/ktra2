"""استبعاداتُ محاور الـpilot تصل الشاشةَ بأسمائها العربيّة لا برموزها.

كان `PilotAxesTable` يطبع `exclusions` كما يرسلها الخادم، فقرأ الموظّفُ في عمود
«الاستبعادات»: «onboarding، waiting_customer، transferred_before_due».

حارسٌ ساكنٌ بالضرورة (كـ`core/tests/test_header_role_label.py`): `npm test` يشغّل
دوالَّ خالصة ولا يرى ما يرسله الخادم، و`tsc` لا يفحص نصّاً. فالمطابقةُ تُقرأ من
الطرفين: الرموزُ من مصدرها في `calculate_employee_pilot_performance`، والأسماءُ من
choices النماذج التي جاءت منها الرموز.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

from platform_ops.models import Engagement, WorkOrder, WorkOrderDeliverable

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ROOT / "platform_ops" / "services.py"
LABELS = ROOT / "frontend_v2" / "utils" / "pilotExclusions.ts"

#: الرموزُ التي لها choices خادميّة، مع تسميتها هناك.
CHOICE_BACKED = {
    "onboarding": Engagement.Kind.ONBOARDING.label,
    "waiting_customer": WorkOrder.Status.WAITING_CUSTOMER.label,
    "customer_new_info": WorkOrderDeliverable.RejectionCategory.CUSTOMER_NEW_INFO.label,
    "other": WorkOrderDeliverable.RejectionCategory.OTHER.label,
}


class PilotExclusionLabelsTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.labels_source = LABELS.read_text(encoding="utf-8")

    def _block(self, name: str) -> str:
        match = re.search(rf"export const {name}[^=]*= \{{(?P<body>[^}}]*)\}}", self.labels_source)
        self.assertIsNotNone(match, f"خريطةُ `{name}` اختفت من `utils/pilotExclusions.ts`.")
        return match.group("body")

    def _server_codes(self) -> set[str]:
        """كلُّ رمزٍ في قوائم `"exclusions": [...]` — من المصدر لا نسخةً هنا."""
        source = SERVICES.read_text(encoding="utf-8")
        lists = re.findall(r'"exclusions":\s*\[([^\]]*)\]', source)
        self.assertGreaterEqual(len(lists), 4, "قراءةُ قوائم الاستبعاد لم تعد تطابق `services.py`.")
        return {code for body in lists for code in re.findall(r'"([a-z_]+)"', body)}

    def test_every_exclusion_the_server_sends_has_an_arabic_name(self):
        named = set(re.findall(r"^\s*(\w+)\s*:", self._block("PILOT_EXCLUSION_LABELS"), re.M))
        missing = sorted(self._server_codes() - named)
        self.assertEqual(missing, [], f"رموزُ استبعادٍ تصل الشاشةَ بلا اسمٍ عربيّ: {missing}")

    def test_names_match_the_server_choices_they_come_from(self):
        rejection = dict(re.findall(r"(\w+)\s*:\s*'([^']+)'", self._block("REJECTION_CATEGORY_LABELS")))
        self.assertEqual(
            rejection, {value: label for value, label in WorkOrderDeliverable.RejectionCategory.choices},
            "أسماءُ تصنيف الردّ افترقت عن `WorkOrderDeliverable.RejectionCategory`.",
        )
        literal = dict(re.findall(r"(\w+)\s*:\s*'([^']+)'", self._block("PILOT_EXCLUSION_LABELS")))
        resolved = {**literal, **{code: rejection[code] for code in ("customer_new_info", "other")}}
        for code, label in CHOICE_BACKED.items():
            self.assertEqual(resolved.get(code), label, f"اسمُ `{code}` افترق عن choices خادمه.")
