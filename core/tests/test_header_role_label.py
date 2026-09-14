"""ملصقُ الدور يقول الدورَ بالعربيّة، في كلّ موضعٍ يطبعه.

حارسٌ ساكنٌ بالضرورة: `npm test` هنا يشغّل `utils/*.test.ts` عبر `node --test`
— دوالَّ خالصةً لا تُصيّر مكوّناً — و`tsc` لا يفحص نصَّ واجهةٍ ولا خريطةَ تسميات.
فالمطابقةُ بين مفرداتِ الأدوار والخريطة في الواجهة تُقرأ نصّاً أو لا تُقرأ أصلاً.

**والمفرداتُ اثنتان لا واحدة** (212-P1)، وهذا ما كان يسقط الحارسَ الأوّل: كان
يشتقّ مطلوبَه من `UserCompanyMembership.ROLE_CHOICES` وحدَها فيبقى أخضرَ،
و`hr/auth_api.py` يبني حمولةَ المصادقة بـ
`role = "manager" if user.is_superuser else "employee"` — أي أنّ **كلَّ** من ليس
سوبر أدمن ولا مديرَ عضويّةٍ يصله `employee`، وهي ليست في `ROLE_CHOICES` أصلاً.
فالحالةُ الغالبةُ في النظام كلِّه كانت تُعرَض «الدور: employee» وحارسٌ أخضرُ
فوقها. ولذلك يُقرأ المطلوبُ من **اتّحاد** المفردتين: `ROLE_CHOICES` و`UserRole`
في `frontend_v2/types/user.ts`.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

from tenants.models import UserCompanyMembership

FRONTEND = Path(__file__).resolve().parents[2] / "frontend_v2"
#: مصدرُ التسمية الواحد — يقرؤه كلُّ موضعٍ يطبع الدور.
LABELS = FRONTEND / "utils" / "userRoleLabel.ts"
#: مفردةُ الواجهة كاملةً (`UserRole`) — تُقرأ نصّاً، والملفُّ لا يُعدَّل من هنا.
USER_TYPES = FRONTEND / "types" / "user.ts"
#: المواضعُ التي تطبع الدورَ على الشاشة.
PRINTERS = (
    FRONTEND / "components" / "layout" / "AppLayout.tsx",
    FRONTEND / "components" / "Sidebar.tsx",
)


class HeaderRoleLabelTest(SimpleTestCase):
    """كلُّ دورٍ يمكن أن يحمله المستخدمُ له اسمٌ عربيّ.

    **ولماذا هذا حارسٌ لا تفصيلٌ تجميليّ:** الملصقُ كان ثلاثيّةً تعرف `manager`
    و`procurement` وتطبع «موظف» لكلِّ ما سواهما، ثمّ صار خريطةً تعرف أدوارَ
    العضويّة وحدَها فتطبع `employee` بالإنجليزيّة لأكثر المستخدمين. ومالكُ
    النظام قرأ الملصقَ على حسابٍ فاستنتج أنّ عزلَ الموظّفين مكسور، وأمضى وقتاً
    على عطبٍ لا وجودَ له. الملصقُ الكاذبُ ليس خطأً في التجميل: هو خطأٌ في
    المعلومة التي يُبنى عليها قرار.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = LABELS.read_text(encoding="utf-8")

    def _label_map(self) -> dict[str, str]:
        match = re.search(
            r"export const USER_ROLE_LABEL: Record<string, string> = \{(?P<body>[^}]*)\}",
            self.source,
        )
        self.assertIsNotNone(
            match, "خريطةُ `USER_ROLE_LABEL` اختفت أو أُعيدت تسميتُها."
        )
        return dict(re.findall(r"(\w+)\s*:\s*'([^']+)'", match.group("body")))

    def _ui_roles(self) -> set[str]:
        """مفردةُ `UserRole` كما هي في الواجهة — لا نسخةٌ يدويّةٌ هنا.

        نسخةٌ مكتوبةٌ في هذا الملفّ كانت ستتقادم بصمتٍ عند إضافة دورٍ جديد،
        وهو بعينه ما جعل الحارسَ الأوّلَ يحرس مفردةً ناقصة.
        """
        source = USER_TYPES.read_text(encoding="utf-8")
        match = re.search(r"export type UserRole\s*=(?P<body>[^;]+);", source)
        self.assertIsNotNone(match, "مفردةُ `UserRole` اختفت من `types/user.ts`.")
        roles = set(re.findall(r"'([a-z_]+)'", match.group("body")))
        self.assertGreaterEqual(
            len(roles), 9,
            f"قراءةُ مفردةِ `UserRole` أعادت {len(roles)} أدوارٍ فقط — التعبيرُ لم يعد يطابق الملفّ.",
        )
        return roles

    def test_every_role_the_user_can_carry_has_an_arabic_name(self):
        labels = self._label_map()
        required = self._ui_roles() | {role for role, _ in UserCompanyMembership.ROLE_CHOICES}
        missing = sorted(role for role in required if role not in labels)
        self.assertEqual(
            missing, [],
            f"أدوارٌ بلا اسمٍ عربيّ: {missing} — تُعرَض «مستخدم» للقارئ، "
            "وهو أفضلُ من مفتاحٍ إنجليزيّ ولا يُغني عن اسمها.",
        )

    def test_the_default_role_of_a_plain_user_is_named(self):
        """‏`employee` ليست حالةً نادرة: هي جوابُ `hr/auth_api.py` لكلِّ من ليس
        سوبر أدمن ولا مديرَ عضويّة — أي أكثرِ من يفتح النظام."""
        self.assertIn(
            "employee", self._label_map(),
            "الدورُ الافتراضيُّ في حمولة المصادقة بلا اسمٍ — وهو بلاغُ المالك حرفيّاً.",
        )

    def test_no_two_membership_roles_share_one_name(self):
        """اسمان متطابقان يعيدان العيبَ نفسَه بصيغةٍ أخفى.

        خريطةٌ كاملةُ المفاتيح تمرّ الحارسَ أعلاه وهي تسمّي أربعةَ أدوارٍ «موظف»:
        القارئُ يرى اسماً صحيحَ المبنى ولا يستطيع تمييزَ من أمامه.

        والمقارنةُ على **أدوار العضويّة وحدَها**: `employee` و`staff` من مفردتين
        مختلفتين تصفان الشيءَ نفسَه («ليس مديراً»)، فاسمٌ واحدٌ لهما صدقٌ لا لبس.
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
            f"أدوارٌ مختلفةٌ تحمل الاسمَ نفسَه: {clashes} — القارئُ لا يميّز من أمامه.",
        )

    def test_no_screen_prints_the_raw_role_key(self):
        """والسلسلةُ الشرطيّةُ — أو المفتاحُ العاري — لا يعودان من الباب الخلفيّ.

        خريطةٌ مضبوطةٌ لا تنفع إن بقي موضعٌ يطبع `user.role` كما هو؛ وقد بقي
        موضعان: ترويسةُ `AppLayout` بـ`?? user.role`، وبطاقةُ الحساب في
        `Sidebar` بالمفتاح عارياً بلا خريطةٍ أصلاً.
        """
        # **موضعُ الطباعة بعينه لا كلُّ ذكرٍ للحقل**: `user.role` يُمرَّر أيضاً
        # إلى حسابات الصلاحيات (`groupVisible(..., user.role)`) و`GlobalSearch`،
        # وهي استعمالاتٌ سليمةٌ لا تصل الشاشة. فحارسٌ يمنع الحقلَ أينما ورد
        # يسقط على كودٍ صحيحٍ ويُدفَع إلى التعطيل.
        violations = []
        sites = (
            (PRINTERS[0], r"<span>الدور:[^<]*</span>", "سطرُ «الدور:» في الترويسة"),
            (PRINTERS[1], r'\{user\.isSuperAdmin \? "سوبر أدمن المنصة" : [^}]*\}', "سطرُ الدور في بطاقة الحساب"),
        )
        for path, pattern, what in sites:
            source = path.read_text(encoding="utf-8")
            printed = re.search(pattern, source)
            if printed is None:
                violations.append(f"{path.name}: {what} اختفى — الحارسُ يقيس العدم")
                continue
            if "userRoleLabel(" not in printed.group(0):
                violations.append(f"{path.name}: {what} لا يقرأ مصدرَ التسمية — {printed.group(0).strip()}")
        self.assertEqual(violations, [], f"مفتاحٌ إنجليزيٌّ يصل الشاشة: {violations}")

    def test_the_unknown_role_falls_back_to_a_name_not_a_key(self):
        self.assertRegex(
            self.source, r"\?\?\s*'مستخدم'",
            "البديلُ عند دورٍ مجهولٍ ليس اسماً عربيّاً — فالمفتاحُ يصل الشاشة.",
        )


#: أدوارُ العضويّة كما تقرؤها الشاشاتُ (`utils/memberRoles.ts`).
MEMBER_ROLES_UTIL = FRONTEND / "utils" / "memberRoles.ts"
#: بابُ **إسنادِ** الدور في شاشة «إدارة المستخدمين».
EDIT_USER_MODAL = FRONTEND / "components" / "modals" / "EditUserModal.tsx"


def _element_span(source: str, anchor: str, closing: str) -> str:
    """جسمُ عنصرٍ من `anchor` إلى `closing` — لا الملفُّ كلُّه.

    التأكيدُ المطلوب «قائمةُ الخيارات **داخل** هذا الـ`select`»: ذكرُ الاسم
    في مكانٍ آخرَ من الملفّ لا يجعل الخياراتِ ضيّقة.
    """
    start = source.index(anchor)
    end = source.index(closing, start)
    return source[start:end]


class UsersScreenRoleVocabularyTest(SimpleTestCase):
    """مفردةُ الأدوار في شاشة المستخدمين: نسخةٌ واحدة، وإسنادٌ أضيقُ من العرض."""

    def test_the_members_util_does_not_keep_a_second_label_map(self):
        """خريطةٌ ثانيةٌ تفترق عن الأولى صامتةً — وقد افترقت فعلاً.

        أُنشئت `MEMBER_ROLE_LABELS` خريطةً حرفيّةً بتسعة أسماءٍ مكتوبةٍ بيدها،
        فكان `viewer` «مستعرض» في `userRoleLabel.ts` و«مستعرض (قراءة فقط)» فيها
        منذ أوّل سطر. والحارسُ فوق هذا الملفّ لا يرى نسخةً لا يعرف مكانَها،
        فيبقى أخضرَ على تعريفين متضاربين للشيء نفسِه.
        """
        source = MEMBER_ROLES_UTIL.read_text(encoding="utf-8")
        literals = re.findall(
            r'^\s*(\w+)\s*:\s*"[^"]*[\u0600-\u06FF][^"]*"', source, re.MULTILINE
        )
        self.assertEqual(
            literals, [],
            f"تسمياتٌ عربيّةٌ مكتوبةٌ في `memberRoles.ts`: {literals} — "
            "المصدرُ الواحدُ `utils/userRoleLabel.ts`، وهذه نسخةٌ ثانيةٌ ستفترق.",
        )
        self.assertIn(
            'from "./userRoleLabel.ts"', source,
            "`memberRoles.ts` لا يقرأ مصدرَ التسمية — فمن أين تأتي أسماؤه؟",
        )

    def test_the_user_edit_screen_offers_only_roles_the_server_accepts(self):
        """زرٌّ يَعِد بما يردّه الخادمُ دعوةٌ إلى إحباط.

        `tenants/views.py` يردّ `legal_accountant` من هذا الباب («يُنشأ دور
        المحاسب القانوني من دورة الارتباط المحمية فقط»)، و`ess`/`field_staff`
        يُمنحان من وحدتيهما. فقائمةُ **العرض** تسعةٌ وقائمةُ **الإسناد** ستّة،
        والفرقُ مقصود: تُقرأ أدوارٌ لا تُكتَب من هذه الشاشة.
        """
        source = EDIT_USER_MODAL.read_text(encoding="utf-8")
        span = _element_span(source, 'id="userRole"', "</select>")
        violations = []
        if "ASSIGNABLE_MEMBER_ROLES" not in span:
            violations.append("قائمةُ الأدوار لا تُشتقّ من `ASSIGNABLE_MEMBER_ROLES`")
        if "Object.entries(MEMBER_ROLE_LABELS)" in span:
            violations.append("قائمةُ الإسناد تسرد خريطةَ العرض كلَّها")
        self.assertEqual(
            violations, [], f"بابُ إسنادِ الدور أوسعُ ممّا يقبله الخادم: {violations}"
        )
