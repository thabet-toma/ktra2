"""ملصقُ الدور في ترويسة التطبيق يقول الدورَ الذي في الخادم.

حارسٌ ساكنٌ بالضرورة: `npm test` هنا يشغّل `utils/*.test.ts` عبر `node --test`
— دوالَّ خالصةً لا تُصيّر مكوّناً — و`tsc` لا يفحص نصَّ واجهةٍ ولا خريطةَ تسميات.
فالمطابقةُ بين خيارات النموذج والخريطة في الـTSX تُقرأ نصّاً أو لا تُقرأ أصلاً.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

from tenants.models import UserCompanyMembership

APP_LAYOUT = (
    Path(__file__).resolve().parents[2]
    / "frontend_v2" / "components" / "layout" / "AppLayout.tsx"
)


class HeaderRoleLabelTest(SimpleTestCase):
    """كلُّ دورٍ يمنحه الخادمُ له اسمٌ في الترويسة.

    **ولماذا هذا حارسٌ لا تفصيلٌ تجميليّ:** كان الملصقُ ثلاثيّةً تعرف `manager`
    و`procurement` وتطبع «موظف» لكلِّ ما سواهما — سبعةً من تسعة، حتى «مستعرض».
    ومالكُ النظام قرأه على حسابِ سوبر أدمن فاستنتج أنّ عزلَ الموظّفين مكسور،
    وأمضى وقتاً على عطبٍ لا وجودَ له. الملصقُ الكاذبُ ليس خطأً في التجميل: هو
    خطأٌ في المعلومة التي يُبنى عليها قرار.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = APP_LAYOUT.read_text(encoding="utf-8")

    def _label_map(self) -> dict[str, str]:
        match = re.search(
            r"const MEMBERSHIP_ROLE_LABEL: Record<string, string> = \{(?P<body>[^}]*)\}",
            self.source,
        )
        self.assertIsNotNone(
            match, "خريطةُ `MEMBERSHIP_ROLE_LABEL` اختفت أو أُعيدت تسميتُها."
        )
        return {
            key: label
            for key, label in re.findall(
                r"(\w+)\s*:\s*'([^']+)'", match.group("body")
            )
        }

    def test_every_membership_role_the_server_grants_has_a_name_in_the_header(self):
        labels = self._label_map()
        missing = [
            f"{role} ({display})"
            for role, display in UserCompanyMembership.ROLE_CHOICES
            if role not in labels
        ]
        self.assertEqual(
            missing, [],
            f"أدوارٌ يمنحها الخادمُ بلا اسمٍ في الترويسة: {missing} — "
            "تُعرَض بمفتاحها الإنجليزيّ أو بالاسم الخطأ.",
        )

    def test_no_two_roles_share_one_name(self):
        """اسمان متطابقان يعيدان العيبَ نفسَه بصيغةٍ أخفى.

        خريطةٌ كاملةُ المفاتيح تمرّ الحارسَ أعلاه وهي تسمّي أربعةَ أدوارٍ «موظف»:
        القارئُ يرى اسماً صحيحَ المبنى ولا يستطيع تمييزَ من أمامه — وهو بعينه
        ما فعلته الثلاثيّةُ المستبدَلة.
        """
        labels = self._label_map()
        granted = {role for role, _ in UserCompanyMembership.ROLE_CHOICES}
        seen: dict[str, list[str]] = {}
        for role, label in labels.items():
            if role in granted:
                seen.setdefault(label, []).append(role)
        clashes = {label: roles for label, roles in seen.items() if len(roles) > 1}
        self.assertEqual(
            clashes, {},
            f"أدوارٌ مختلفةٌ تحمل الاسمَ نفسَه في الترويسة: {clashes} — "
            "القارئُ لا يميّز من أمامه.",
        )

    def test_the_header_reads_the_map_and_not_a_hand_written_chain(self):
        """والسلسلةُ الشرطيّةُ لا تعود من الباب الخلفيّ.

        خريطةٌ مضبوطةٌ فوق الملفّ لا تنفع إن بقي الملصقُ يحسب اسمَه بثلاثيّةٍ
        خاصّةٍ به: الحارسان أعلاه يقرآن الخريطةَ وحدَها فيبقيان أخضرَين.
        """
        header = re.search(r"<span>الدور:[^<]*</span>", self.source)
        self.assertIsNotNone(header, "سطرُ «الدور:» في الترويسة اختفى.")
        self.assertIn(
            "MEMBERSHIP_ROLE_LABEL", header.group(0),
            f"ملصقُ الدور لا يقرأ الخريطة: {header.group(0)}",
        )
        self.assertNotIn(
            "?", header.group(0).replace("??", ""),
            f"ملصقُ الدور عاد يحسب اسمَه بسلسلةٍ شرطيّة: {header.group(0)}",
        )
