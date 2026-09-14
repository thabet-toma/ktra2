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
    "/api/platform/crm/leads/1/stats/": "getCrmLeadStats",
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


class CrmFollowUpsAreReadFromLeadDataTest(TestCase):
    """حقولُ المتابعة لا تكفي في النوع: يجب أن تصل إلى عين الموظف."""

    def test_the_lead_card_reads_its_follow_up_date(self):
        lead_list = (CRM_UI / "CrmLeadList.tsx").read_text(encoding="utf-8")
        reads = re.findall(r"lead\.next_follow_up_at", lead_list)
        self.assertTrue(
            reads,
            "بطاقة العميل لا تقرأ `lead.next_follow_up_at`؛ الموعد المحفوظ لا يعود للموظف.",
        )

    def test_status_change_activity_reads_both_ends_in_the_profile(self):
        profile = (CRM_UI / "CrmLeadProfile.tsx").read_text(encoding="utf-8")
        missing = [
            field for field in ("activity.status_before", "activity.status_after")
            if field not in profile
        ]
        self.assertEqual(
            missing, [],
            f"سجل تغيير الحالة لا يقرأ: {missing}.",
        )

    def test_the_overdue_badge_measures_a_day_not_an_instant(self):
        """«متأخّرة» على البطاقة تُقاس بيومٍ مضى، لا بلحظةِ `Date.now()`.

        بقياس اللحظة يصير موعدُ **اليوم** (تكتبه الشاشةُ 09:00) «متأخّراً» في
        التاسعة وواحدة وهو عملُ اليوم؛ والأسوأُ أنّ الخادمَ يعدّ «المتأخّرة»
        بقاعدةٍ أخرى (`crm.services.follow_up_day_bounds`) فيختلف الرقمُ في
        الشريط عن الشارة في القائمة **على الشاشة نفسِها**. فالقاعدةُ واحدةٌ في
        الطرفين، وهذا الحارسُ يمنع رجوعَ الواجهة إلى اللحظة.
        """
        lead_list = (CRM_UI / "CrmLeadList.tsx").read_text(encoding="utf-8")
        match = re.search(r"const isOverdue = (?P<expression>[^;]*);", lead_list)
        self.assertIsNotNone(match, "تعبيرُ `isOverdue` غائبٌ عن بطاقة العميل.")
        expression = match.group("expression")
        self.assertNotIn(
            "Date.now()", expression,
            f"شارةُ «متأخّرة» تقيس اللحظةَ لا اليومَ: {expression}",
        )
        self.assertRegex(
            lead_list, r"setHours\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)",
            "لا حدَّ يومٍ محلّيّاً في الملفّ؛ فبأيِّ شيءٍ تُقارَن المواعيد؟",
        )

    def test_the_follow_ups_tab_is_hidden_from_a_desk_that_cannot_have_rows(self):
        """تبويبُ «متابعاتي» خلف وجودِ دفترٍ شخصيّ — وإلّا فهو صفرٌ بحكم البناء.

        النطاقُ يُرشَّح خادميّاً بـ`assigned_to=employee`، وسوبر أدمن بلا صفِّ
        `PlatformEmployee` يعيد له الخادمُ `base.none()`. فتبويبٌ يُعرَض له هو
        وعدٌ بقائمةٍ **لا تملأها بياناتٌ أبداً** — وهو بعينه عطبُ 212-H الذي
        أبلغ عنه المالكُ: شاشةٌ تعمل وتُظهر صفراً والقاعدةُ ملأى.
        """
        lead_list = (CRM_UI / "CrmLeadList.tsx").read_text(encoding="utf-8")
        tab = re.search(r"\{hasPersonalDesk && [^\n]*?onScope\('follow_ups'\)", lead_list)
        self.assertIsNotNone(
            tab,
            "تبويبُ «متابعاتي» غيرُ مقيَّدٍ بـ`hasPersonalDesk`؛ مديرٌ بلا صفِّ موظّفٍ يراه فارغاً دائماً.",
        )
        panel = (CRM_UI / "CrmPanel.tsx").read_text(encoding="utf-8")
        self.assertRegex(
            panel, r"hasPersonalDesk=\{myEmployeeId !== null\}",
            "الحاوية لا تمرّر وجودَ الدفتر الشخصيّ، فالقيدُ في القائمة بلا مصدرِ حقيقة.",
        )

    def test_the_manager_card_reads_the_overdue_field_not_a_doctored_name(self):
        """عدّادُ المتأخّرات حقلٌ يُعرَض، لا نصٌّ يُلحَم داخل اسم الموظّف.

        أوّلُ صيغةٍ لهذه اللوحة كانت تُعيد كتابةَ `employee_name` نفسِه إلى
        «أحمد — متأخرة: ٣» عند التحميل: فيصير الاسمُ في البيانات ليس اسماً — لا
        يُفرز ولا يُبحث فيه ولا تُلوَّن منه شارةٌ ولا يصلح لقائمةِ اختيار، وأيُّ
        قارئٍ آخرَ لنفس الحقل يقرأ رقماً ملتصقاً باسمٍ.
        """
        manager = (CRM_UI / "CrmManagerPanel.tsx").read_text(encoding="utf-8")
        # التأكيدُ على **قائمةِ مخالفات** لا على نصّ الملفّ: `assertIn` على ملفٍّ
        # بحجم ثمانية كيلوبايت يطبع الملفَّ كلَّه في خبر الفشل فلا يُقرأ.
        violations = []
        if "employee.overdue" not in manager:
            violations.append("لا يقرأ `employee.overdue` — المدير لا يرى مَن تأخّرت متابعاتُه")
        if "employee_name:" in manager:
            violations.append("يُعيد كتابةَ `employee_name` — الرقمُ شارةٌ لا حشوٌ في الاسم")
        self.assertEqual(violations, [], f"CrmManagerPanel.tsx: {violations}")

    def test_profile_derives_the_pipeline_from_the_single_exported_source(self):
        lead_list = (CRM_UI / "CrmLeadList.tsx").read_text(encoding="utf-8")
        profile = (CRM_UI / "CrmLeadProfile.tsx").read_text(encoding="utf-8")
        violations = []
        if "export const CRM_LEAD_PIPELINE" not in lead_list:
            violations.append("CrmLeadList.tsx: المصدر المصدَّر للمراحل غائب")
        if "CRM_LEAD_PIPELINE" not in profile:
            violations.append("CrmLeadProfile.tsx: لا يستورد مصدر المراحل")
        if "CRM_LEAD_PIPELINE.map" not in profile:
            violations.append("CrmLeadProfile.tsx: الخط لا يرسم من المصدر الواحد")
        self.assertEqual(
            violations, [],
            f"سلسلة الحالة ليست مشتقة من مصدر واحد: {violations}",
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


class CrmPanelIsMountedInBothWorkspacesTest(TestCase):
    """المالك والمسوّق يدخلان لوحة CRM نفسها من قشرتيهما، لا من بابين."""

    def test_the_crm_panel_is_mounted_in_the_command_centre_and_staff_shell(self):
        dashboard = (FRONTEND / "components" / "platform" / "PlatformOpsDashboard.tsx").read_text(encoding="utf-8")
        staff_shell = (STAFF / "StaffShell.tsx").read_text(encoding="utf-8")

        self.assertRegex(
            dashboard,
            r'activeTab === "crm"\s*&&\s*<CrmPanel\s+isManager=\{true\}\s+myEmployeeId=\{null\}\s*/>',
            "مركز القيادة لا يركّب لوحة CRM للمالك؛ زرّ العملاء لا يجوز أن يفتح باب /staff منفصلاً.",
        )
        self.assertRegex(
            staff_shell,
            r'crm:\s*<CrmPanel\s+isManager=\{capabilities\.is_platform_admin\}\s+myEmployeeId=\{profile\?\.id \?\? null\}\s*/>',
            "قشرة الموظف لم تعد تركّب لوحة CRM؛ المسوّق هو مستعملها الأول ولا يجوز أن يحذفه تركيب المالك.",
        )


class CrmPanelLandsOnADeskThatHasRowsTest(TestCase):
    """البابُ الجديدُ لا يُفتح على غرفةٍ فارغةٍ بحكم البناء.

    مركزُ القيادة يركّب اللوحةَ بـ`myEmployeeId={null}` (قرارٌ صحيحٌ: لا يجوز
    اختراعُ ملكيّةِ عميلٍ لسوبر أدمن بلا صفّ موظّف) — ومن ذلك القرارِ نفسِه يلزم
    شيئان لا يمسكهما `tsc` ولا `npm test`:

    ١) النطاقُ الابتدائيُّ لا يكون `'mine'` ثابتاً: الخادمُ يرشّح `mine` بـ
       `assigned_to=employee` فيعيد `none()` بلا صفٍّ — **صفرٌ بحكم البناء**،
       مُثبَتٌ خادميّاً في
       `crm/tests/test_manager_without_employee_row.py`.
    ٢) شريطُ «عدّاداتي» لا يُركَّب لمن لا دفترَ له: نقطتُه ترفع 403، واللوحةُ
       تعرض نصَّ الخطأ مكانَها بالتصميم — فيصير صدرُ الشاشة اعتذاراً.

    وكلُّ ذلك بلا أيّ خطأٍ في الطرفين: صفحةٌ تعمل وتقول «لا عملاء» والقاعدةُ
    مملوءة. وهذا الصنفُ بعينه («صفرٌ بحكم البناء») هو ما كُشف في 212-E2 على
    `claimed_count`.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.panel = (CRM_UI / "CrmPanel.tsx").read_text(encoding="utf-8")

    def _initial_scope_expression(self) -> str:
        match = re.search(
            r"useState<Scope>\((?P<expression>[^;]*)\);", self.panel
        )
        self.assertIsNotNone(match, "لم يُعثر على النطاق الابتدائيّ في `CrmPanel`.")
        return match.group("expression")

    def test_the_initial_scope_is_derived_from_whether_there_is_a_personal_desk(self):
        expression = self._initial_scope_expression()
        self.assertIn(
            "myEmployeeId", expression,
            f"النطاقُ الابتدائيُّ ثابتٌ لا يقرأ وجودَ دفترٍ شخصيّ: `{expression}` — "
            "مالكُ المنصّة يهبط على «عملائي» وهي صفرٌ بحكم البناء.",
        )
        self.assertIn(
            "'all'", expression,
            f"لا نطاقَ بديلاً لمن لا دفترَ له: `{expression}` — "
            "و«المخزن المتاح» ليس بديلاً، فهو لا يحمل عميلاً مُسنَداً.",
        )

    def test_my_stats_is_mounted_only_where_there_is_a_personal_desk(self):
        mount = re.search(r".{0,40}<CrmMyStats\b", self.panel)
        self.assertIsNotNone(mount, "شريطُ «عدّاداتي» لم يعد مركَّباً في اللوحة.")
        self.assertIn(
            "myEmployeeId", mount.group(0),
            f"شريطُ «عدّاداتي» مركَّبٌ بلا شرطِ دفترٍ شخصيّ: `{mount.group(0).strip()}` — "
            "نقطتُه ترفع 403 لمن لا صفَّ موظّفٍ له، فيصير صدرُ شاشته اعتذاراً.",
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


def _braced_span(source: str, anchor: str) -> str:
    """جسمُ تعبيرٍ من `{` عند `anchor` إلى قوسه المُطابِق.

    التأكيدُ المطلوب «الزرّان **داخل** هذا الشرط»، ولا يُقاس بـ`in` على الملفّ
    كلِّه: شرطٌ يبقى مكتوباً وزرٌّ يُنقَل من تحته يمرّان معاً.
    """
    start = source.index(anchor)
    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"تعبيرٌ مفتوحُ الأقواس عند: {anchor}")


class CrmPromisesOnlyWhatTheServerAllowsTest(TestCase):
    """212-Q2-ب — زرٌّ يَعِد بفعلٍ يردّه الخادمُ ٤٠٣ دعوةٌ إلى إحباط.

    ليست هذه صلاحيّةَ سوبر أدمن (تلك حرسها 212-Q2) بل **صلاحيّةَ صاحبِ الشيء**:
    الخادمُ يبتّ في التحويل لصاحب العميل أو المدير، ويكتب النشاطَ والحالةَ لهما
    وحدَهما — والشاشةُ كانت ترسم الأزرارَ للجميع.
    """

    def test_the_decide_buttons_sit_inside_the_server_flag(self):
        source = (CRM_UI / "CrmTransferInbox.tsx").read_text(encoding="utf-8")
        span = _braced_span(source, "{!row.can_decide ?")
        for trigger in ("void decide(row, true)", "setDecidingId(decidingId === row.id"):
            with self.subTest(trigger=trigger):
                self.assertIn(
                    trigger, span,
                    "زرُّ البتّ خارج شرط `can_decide` — يُرسَم لطالب التحويل نفسِه.",
                )

    def test_the_reject_form_is_gated_too_not_only_its_button(self):
        """الزرُّ بابٌ والنموذجُ بابٌ ثانٍ: حجبُ الأوّل وحدَه يترك الثاني قابلاً للفتح."""
        source = (CRM_UI / "CrmTransferInbox.tsx").read_text(encoding="utf-8")
        self.assertIn("decidingId === row.id && row.can_decide", source)

    def test_the_inbox_does_not_rewrite_the_rule_from_the_row(self):
        """`from_employee` مالكُ **يومِ الطلب**؛ نسخةٌ ثانيةٌ من القاعدة به تكذب بعد انتقال العميل."""
        source = (CRM_UI / "CrmTransferInbox.tsx").read_text(encoding="utf-8")
        self.assertNotIn("from_employee?.id ===", source)
        self.assertNotIn("myEmployeeId", source)

    def test_writing_on_a_lead_is_gated_by_ownership_in_the_profile(self):
        """`log_activity` و`change_lead_status` ترفعان ٤٠٣ لغير صاحب العميل والمدير."""
        source = (CRM_UI / "CrmLeadProfile.tsx").read_text(encoding="utf-8")
        self.assertIn("const canWrite = isOwner || isManager;", source)
        for anchor in ('{canWrite ? <div className="mt-4 flex', '{canWrite ? <div className="mt-5 flex'):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, source, "نموذجُ كتابةٍ بلا شرط ملكيّة.")
        self.assertIn("{noteOpen && canWrite &&", source)

    def test_requesting_a_transfer_stays_open_to_everyone(self):
        """**الحجبُ لا يُوسَّع**: طلبُ التحويل غرضُه أن يفتحه من ليس صاحبَ العميل.

        وبلا هذا التأكيد يكون «أغلقتُ كلَّ شيءٍ خلف `canWrite`» إصلاحاً يمرّ
        أخضرَ ويسدّ البابَ الذي بُني عمداً (`transfer-requests/` في الخادم).
        """
        source = (CRM_UI / "CrmLeadProfile.tsx").read_text(encoding="utf-8")
        form_start = source.index("<form onSubmit={submitTransfer}")
        prefix = source[max(0, form_start - 120):form_start]
        self.assertNotIn("canWrite", prefix, "نموذجُ طلب التحويل صار خلف شرط الملكيّة.")
