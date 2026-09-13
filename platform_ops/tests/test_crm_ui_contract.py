"""عقدُ واجهة CRM داخل قشرة الموظّف (#212 212-C).

`npm test` هنا يشغّل `utils/*.test.ts` بـ`node --test`: دوالَّ خالصةً **لا تُصيّر
مكوّناً واحداً**، فلا ترى صنفَ CSS ولا خاصيّةَ JSX ولا تخطيطاً. و`tsc` لا يفحص
وجودَ صنفٍ ولا أنّ زرّاً موصولٌ بنقطة. فالحراسةُ ساكنةٌ بالضرورة.

**وأهمُّ ما يحرسه هذا الملفُّ أنّ الشاشةَ تستعمل ما بُني لها.** الصيغةُ الأولى
منه سألت: «هل المسارُ مستهلَكٌ في `platformCrmApi.ts`؟» — وكان الجواب نعم لكلّ
مسار، بينما **خمسٌ من دوالّ العميل لم يكن يستدعيها مكوّنٌ واحد**: صندوقُ طلبات
التحويل والبتُّ فيها وعدّاداتُ الموظّف. أي أنّ زرَّ «طلب تحويل العميل» كان باباً
مسدوداً: الطلبُ يُرسَل ولا يراه أحدٌ أبداً، والحارسُ أخضر. فالمقياسُ الصحيحُ
**الاستدعاءُ من مكوّن** لا التعريفُ في العميل.
"""
from pathlib import Path
import re
from unittest import TestCase

from crm.tests.test_crm_route_guard import _crm_routes

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend_v2"
STAFF = FRONTEND / "components" / "platform" / "staff"
CRM_UI = STAFF / "crm"
API = FRONTEND / "services" / "platformCrmApi.ts"

#: مسارُ الـURLconf ← دالّةُ العميل التي تنادِيه.
ROUTE_TO_FUNCTION = {
    "/api/platform/crm/colleagues/": "listCrmColleagues",
    "/api/platform/crm/stats/me/": "getMyCrmStats",
    "/api/platform/crm/stats/overview/": "getCrmOverview",
    "/api/platform/crm/leads/": "listCrmLeads",
    "/api/platform/crm/leads/lookup/": "lookupCrmPhone",
    "/api/platform/crm/leads/import/": "importCrmLeads",
    "/api/platform/crm/leads/1/": "getCrmLead",
    "/api/platform/crm/leads/1/activities/": "listCrmActivities",
    "/api/platform/crm/leads/1/claim/": "claimCrmLead",
    "/api/platform/crm/leads/1/release/": "releaseCrmLead",
    "/api/platform/crm/leads/1/status/": "changeCrmLeadStatus",
    "/api/platform/crm/leads/1/transfer/": "transferCrmLead",
    "/api/platform/crm/leads/1/transfer-requests/": "requestCrmLeadTransfer",
    "/api/platform/crm/leads/1/approve/": "approveCrmLead",
    "/api/platform/crm/leads/1/reject/": "rejectCrmLead",
    "/api/platform/crm/transfer-requests/": "listCrmTransferRequests",
    "/api/platform/crm/transfer-requests/1/": "getCrmTransferRequest",
    "/api/platform/crm/transfer-requests/1/decide/": "decideCrmTransferRequest",
}

#: دالّةٌ في العميل **لا تُستدعى من مكوّنٍ عن قصد**، ولكلٍّ سببُها المكتوب.
#: الاستثناءُ قرارٌ يُبرَّر لا سطرٌ يمرّ — وبلا هذه القائمة تعود الشاشةُ
#: الناقصةُ إلى الخضرة.
UNUSED_BY_DESIGN = {
    "getCrmTransferRequest":
        "قائمةُ `transfer-requests/` تعيد الكائنَ كاملاً (الطرفان والسببُ والحالةُ "
        "والتواريخ)، فصندوقُ الطلبات لا يحتاج قراءةَ تفصيلٍ ثانيةً لكلّ صفّ.",
    "patchCrmLead":
        "تعديلُ حقول الوصف (المالك/المدينة/العنوان/النشاط) خارج نموذج المالك "
        "البصريّ لهذه المرحلة: ملفُّ العميل قراءةٌ وأفعالٌ لا محرِّرُ بيانات. "
        "النقطةُ قائمةٌ في الخادم ومحروسةٌ هناك، وتُوصَل حين تُطلَب.",
    "createCrmLead":
        "تُستدعى فعلاً من `CrmPanel` (نموذجُ «اقتراح رقم»/«إضافة رقم») — تبقى هنا "
        "فارغةَ الأثر إن حُذف ذلك النموذج، فيسقط عندها التعدادُ لا هذا الاستثناء.",
}


def _component_sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(CRM_UI.glob("*.tsx"))}


def _exported_api_functions(source: str) -> list[str]:
    return re.findall(r"^export const (\w+)\s*=", source, flags=re.MULTILINE)


# قاعدةُ «تبويبُ CRM موصولٌ بلوحته» يملكها تعدادُ لوحات القشرة في
# `test_staff_shell_contract.py` — نسخةٌ ثانيةٌ منها هنا تعني قاعدتين
# تتباعدان.
class CrmRoutesReachTheScreenTest(TestCase):
    """التعدادُ الحاسم: كلُّ مسارٍ في الـURLconf يصل شاشةً فعلاً."""

    def test_the_route_census_matches_the_urlconf_exactly(self):
        routes = set(_crm_routes())
        mapped = set(ROUTE_TO_FUNCTION)
        self.assertEqual(
            routes - mapped, set(),
            f"مسارُ CRM جديدٌ بلا دالّةٍ في العميل: {sorted(routes - mapped)}",
        )
        self.assertEqual(
            mapped - routes, set(),
            f"مسارٌ في جدول هذا الاختبار لم يعد في الـURLconf: {sorted(mapped - routes)}",
        )

    def test_every_route_function_is_called_from_a_component_or_excused(self):
        api_source = API.read_text(encoding="utf-8")
        components = _component_sources()
        for route, function in sorted(ROUTE_TO_FUNCTION.items()):
            with self.subTest(route=route):
                self.assertRegex(
                    api_source, rf"export const {function}\s*=",
                    f"دالّةُ العميل `{function}` للمسار {route} غير معرَّفة.",
                )
                if function in UNUSED_BY_DESIGN:
                    continue
                callers = [
                    name for name, source in components.items()
                    if re.search(rf"\b{function}\s*\(", source)
                ]
                self.assertTrue(
                    callers,
                    f"مسارُ CRM {route} مكتوبٌ في عميل الـAPI ولا **يستدعيه** مكوّنٌ "
                    f"واحد تحت `staff/crm/` — بابٌ مسدود: الفعلُ يُرسَل ولا شاشةَ "
                    f"تُظهره. صِلْه بلوحة، أو استثنِه بسببٍ مكتوبٍ في "
                    f"`UNUSED_BY_DESIGN`.",
                )

    def test_every_exported_api_function_is_used_or_excused(self):
        """التعدادُ الثاني: دالّةٌ بلا مسارٍ خاصٍّ بها لا تفلت.

        ‏`patchCrmLead` تشترك مع `getCrmLead` في مسارٍ واحد (`leads/1/`)، فتعدادُ
        المسارات وحدَه لا يراها. وبلا هذا التأكيد تبقى دالّةٌ مكتوبةٌ لا يستدعيها
        شيءٌ بلا قرارٍ مكتوب.
        """
        components = _component_sources()
        for function in _exported_api_functions(API.read_text(encoding="utf-8")):
            with self.subTest(function=function):
                called = any(
                    re.search(rf"\b{function}\s*\(", source) for source in components.values()
                )
                self.assertTrue(
                    called or function in UNUSED_BY_DESIGN,
                    f"‏`{function}` مُصدَّرةٌ في عميل CRM ولا يستدعيها مكوّن، ولا سببَ "
                    "مكتوباً لذلك في `UNUSED_BY_DESIGN`.",
                )

    def test_every_written_excuse_is_a_real_reason(self):
        for function, reason in UNUSED_BY_DESIGN.items():
            with self.subTest(function=function):
                self.assertGreater(len(reason.strip()), 40)


class CrmPanelsFollowRepoStyleTest(TestCase):
    def test_no_inline_style_or_locale_formatters(self):
        for name, source in _component_sources().items():
            with self.subTest(source=name):
                self.assertNotIn("style={{", source)
                self.assertNotIn("toLocaleDateString", source)
                self.assertNotIn("toLocaleString", source)
                self.assertNotIn("toLocaleTimeString", source)
                self.assertNotIn("dark:", source)
                self.assertNotIn("bg-white", source)
                self.assertNotIn("text-slate-900", source)

    def test_numbers_go_through_format_number(self):
        rendered = "\n".join(_component_sources().values())
        if re.search(r"(?:count|total|pool_size|employee_id|\.id)\s*\}", rendered):
            self.assertIn("formatNumber", rendered, "الأرقام المعروضة في CRM لا تمر عبر formatNumber.")

    def test_no_browser_dialogs_are_used_for_input_or_confirmation(self):
        """‏`window.prompt` ليس واجهةً هنا.

        حوارُ المتصفّح لا يُنسَّق ولا يحمل اتّجاه RTL، ويحجبه بعضُ المتصفّحات
        صامتاً فيبدو الزرُّ معطوباً. والقشرةُ مغلَّفةٌ أصلاً بـ`ToastProvider`
        و`ConfirmProvider`، والسببُ يُكتَب في حقلٍ داخل الصفحة.
        """
        for name, source in _component_sources().items():
            with self.subTest(source=name):
                # التعليقاتُ تذكرها لتشرح القرار؛ المقصودُ **النداء** لا الذكر.
                # ويُؤكَّد على **قائمة** المخالفات لا على النصّ: `assertNotIn`
                # تطبع كومةَ البحث، فيصير خبرُ الفشل الملفَّ كلَّه بلا فائدة.
                used = [
                    dialog for dialog in ("window.prompt(", "window.confirm(", "window.alert(")
                    if dialog in source
                ]
                self.assertEqual(
                    used, [],
                    f"{name} يستعمل {', '.join(used)} — يُستبدَل بحقلٍ في الصفحة.",
                )


class CrmWhatsAppIsHonestTest(TestCase):
    def test_whatsapp_opens_safely_without_recording_an_activity(self):
        source = "\n".join(_component_sources().values())
        self.assertIn("https://wa.me/", source)
        self.assertIn('rel="noopener noreferrer"', source)
        whatsapp_start = source.find("https://wa.me/")
        handler = source[max(0, whatsapp_start - 600):whatsapp_start + 600]
        self.assertNotIn("createCrmActivity", handler, "فتح WhatsApp لا يجوز أن يسجل نشاطاً تلقائياً.")

    def test_the_whatsapp_badge_is_conditional_on_a_whatsapp_number(self):
        """شارةُ «🟢 WhatsApp» كانت تُرسَم دائماً — إخبارٌ بما ليس في البيانات."""
        profile = (CRM_UI / "CrmLeadProfile.tsx").read_text(encoding="utf-8")
        self.assertRegex(
            profile, r"hasWhatsApp\s*=\s*lead\.phones\.some",
            "وجودُ واتساب يجب أن يُشتقَّ من أرقام العميل.",
        )
        badge = profile.find("WhatsApp</span>")
        self.assertNotEqual(badge, -1, "شارةُ واتساب غير موجودة في ملفّ العميل.")
        self.assertIn(
            "hasWhatsApp &&", profile[max(0, badge - 200):badge],
            "شارةُ واتساب تُرسَم بلا شرطٍ على وجود رقمِ واتساب.",
        )


class CrmOwnershipComesFromMyProfileTest(TestCase):
    """«هل أنا صاحبُ هذا العميل؟» سؤالٌ يُجاب من ملفّي لا من دليل الزملاء.

    الدليلُ (`colleagues/`) يعيد `active` وحدَهم عن قصد — فهو منتقي إسنادٍ لا
    سجلَّ موظّفين. واستنباطُ الملكيّة من `is_me` فيه يجعل موظّفاً في إجازةٍ
    غيرَ مالكٍ لعملائه، فيرسل «طلبَ تحويل» على عميلِ نفسِه ويسدَّ بابَه
    (`crm/tests/test_lead_transfer.py`).
    """

    def test_ownership_is_compared_against_my_own_employee_id(self):
        panel = (CRM_UI / "CrmPanel.tsx").read_text(encoding="utf-8")
        self.assertRegex(
            panel, r"isOwner=\{Boolean\(myEmployeeId && [^}]*assigned_to\?\.id === myEmployeeId\)\}",
            "الملكيّةُ لا تُقارَن بمعرّف الموظّف من ملفّه.",
        )
        self.assertNotRegex(
            panel, r"is_me\s*\)[\s\S]{0,80}isOwner",
            "الملكيّةُ عادت تُستنبَط من `is_me` في دليل الزملاء.",
        )

    def test_the_shell_actually_passes_my_employee_id(self):
        shell = (STAFF / "StaffShell.tsx").read_text(encoding="utf-8")
        start = shell.find("crm:")
        self.assertNotEqual(start, -1)
        section = shell[start:start + 300]
        self.assertIn(
            "myEmployeeId=", section,
            "القشرةُ تعرض `CrmPanel` بلا معرّف الموظّف — فتصير الملكيّةُ `false` "
            "دائماً لكلّ موظّف: خاصيّةٌ مطلوبةٌ لا يمرّرها أحدٌ لا يراها `tsc` إن "
            "كان نوعُها يقبل `null`.",
        )


class CrmRequiredFieldsAreDeclaredTest(TestCase):
    """زرٌّ لا يفعل شيئاً ليس زرّاً.

    كان معالجُ التحويل يعود صامتاً على سببٍ فارغٍ (`if (!reason.trim()) return`)
    والحقلُ بلا `required`: فيضغط الموظّفُ «تأكيد التحويل» فلا يحدث شيءٌ ولا
    رسالةَ — حالةٌ لا يفهم منها أنّ عليه كتابةَ سبب.
    """

    def test_every_transfer_reason_field_is_required(self):
        for name in ("CrmPanel.tsx", "CrmLeadProfile.tsx"):
            source = (CRM_UI / name).read_text(encoding="utf-8")
            with self.subTest(source=name):
                for marker in ('placeholder="سبب التحويل"', 'id="crm-transfer-reason"'):
                    if marker in source:
                        field_start = source.rfind("<input", 0, source.index(marker))
                        self.assertIn(
                            "required", source[field_start:source.index(marker)],
                            f"{name}: حقلُ سبب التحويل بلا `required` ومعالجُه يعود صامتاً.",
                        )


class CrmManagerActionsAreGuardedTest(TestCase):
    def test_manager_actions_sit_behind_an_explicit_manager_check(self):
        source = "\n".join(_component_sources().values())
        for action in ("importCrmLeads", "approveCrmLead", "rejectCrmLead", "releaseCrmLead", "getCrmOverview"):
            with self.subTest(action=action):
                self.assertNotEqual(source.find(action), -1, f"فعل المدير {action} غير موجود في اللوحة.")
                # `[^)]*` كي يقبل `if (!isManager || ...)` لا `if (!isManager)` وحدَها.
                self.assertRegex(
                    source,
                    rf"if \(!isManager[^)]*\)[\s\S]{{0,1600}}{action}",
                    f"فعل المدير {action} ليس خلف شرط صفة مدير صريحة.",
                )
