"""حرّاسٌ ساكنةٌ على واجهة عدّاد الحضور (#212 212-D).

‏`npm test` هنا يشغّل `utils/*.test.ts` بـ`node --test`: دوالَّ خالصةً لا تُصيّر
مكوّناً. فـ`formatPresenceClock` مُختبَرةٌ هناك فعلاً، وكلُّ ما دونها — النبضةُ
كلَّ دقيقة، والعدّادُ فوق الصورة، ولوحةُ السجلّ في تبويب الأداء — لا يراه
اختبارٌ ولا `tsc`. فيُحرَس نصّاً.
"""
from pathlib import Path
import re
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend_v2"
STAFF = FRONTEND / "components" / "platform" / "staff"
TOP_BAR = STAFF / "StaffTopBar.tsx"
PANEL = STAFF / "StaffPresencePanel.tsx"
CARD = FRONTEND / "components" / "platform" / "EmployeeCard.tsx"
API = FRONTEND / "services" / "platformPresenceApi.ts"
#: حلقةُ النبضة انتقلت إلى هنا في 212-N1 كي تركّبها قشرةُ الشركة أيضاً.
BEAT_HOOK = FRONTEND / "hooks" / "usePlatformPresenceHeartbeat.ts"
APP_LAYOUT = FRONTEND / "components" / "layout" / "AppLayout.tsx"
#: رقاقةُ العدّاد صارت مكوّناً واحداً للموضعَين في 212-N2.
CHIP = FRONTEND / "components" / "platform" / "PresenceClockChip.tsx"
ROOM = FRONTEND / "components" / "platform" / "WorkspaceRoom.tsx"
DASHBOARD = FRONTEND / "components" / "platform" / "PlatformOpsDashboard.tsx"


class HeartbeatTicksEveryMinuteTest(TestCase):
    def test_the_counter_beats_every_minute_and_clears_its_interval(self):
        """«بدي التحديث يكون كل دقيقة للشاشة تجيب المعلومات» — نصُّ طلب المالك."""
        source = BEAT_HOOK.read_text(encoding="utf-8")
        self.assertRegex(source, r"setInterval\([\s\S]*?,\s*(?:60000|60\s*\*\s*1000)\)")
        self.assertIn("clearInterval", source)

    def test_the_interval_actually_calls_the_heartbeat(self):
        """مؤقّتٌ يدقّ ولا ينادي الخادمَ عدّادٌ يتحرّك في الشاشة ولا يُسجّل شيئاً.

        وهذا بعينه ما كان قبل هذه التذكرة: مؤقّتٌ كلَّ دقيقةٍ يحسب فرقَ ساعةِ
        المتصفّح من `sessionStorage` — أخضرَ في حارسِ «كلّ دقيقة» وبلا دفترٍ
        خادميٍّ إطلاقاً.
        """
        source = BEAT_HOOK.read_text(encoding="utf-8")
        self.assertIn("sendPresenceHeartbeat", source)
        interval = source[source.index("setInterval"):]
        self.assertRegex(
            interval[:200], r"beat\(\)",
            "المؤقّتُ لا ينادي دالّةَ النبضة — عدّادٌ يتحرّك بلا تسجيل.",
        )

    def test_the_counter_no_longer_trusts_the_browser_clock(self):
        # **النداءُ لا الذِّكر**: التعليقُ أعلى المكوّن يشرح العدّادَ القديم
        # ليُفهَم سببُ استبداله، ومنعُ الاسمِ نصّاً يمنع كتابةَ ذلك الشرح.
        source = BEAT_HOOK.read_text(encoding="utf-8") + TOP_BAR.read_text(encoding="utf-8")
        for used in ("sessionStorage.getItem", "sessionStorage.setItem", "Date.now()"):
            self.assertNotIn(
                used, source,
                f"عدّادُ الجلسة القديمُ عاد ({used}): رقمٌ يملكه المتصفّح لا يعرفه "
                "التقييمُ ولا يراه المدير.",
            )

    def test_a_hidden_tab_does_not_beat(self):
        """لسانٌ منسيٌّ مفتوحٌ طوالَ الليل ليس حضوراً."""
        source = BEAT_HOOK.read_text(encoding="utf-8")
        self.assertIn("visibilityState", source)


class TheCounterSitsAboveThePhotoTest(TestCase):
    """«يبين بالطاولة فوق صورتو» — والطاولةُ عنده طاولةُ مساحة العمل (212-N2).

    كانت الرقاقةُ في بطاقة الموظّف وحدَها، و**المقعدُ على الطاولة لا يحمل إلّا
    ضوءاً**: والضوءُ يقول «الآن» ولا يقول «كم قعد اليوم» — وهو السؤالُ الذي
    وُضع العدّادُ له، ويدخل جوابُه في التقييم. فصعدت الرقاقةُ على المقعد،
    ومكوّناً واحداً للموضعَين لا نسختين تفترقان عند أوّل تعديلٍ للعتبة.
    """

    #: مرساةُ الصورة في كلّ موضع — تُقرأ لتُقاس الرقاقةُ **قبلها** لا بعدها.
    PHOTO_ANCHORS = ((CARD, "employee.photo_url ?"), (ROOM, "occupant.photoUrl ?"))

    def test_the_chip_is_rendered_above_the_photo_in_both_places(self):
        violations = []
        for source_path, anchor in self.PHOTO_ANCHORS:
            source = source_path.read_text(encoding="utf-8")
            chip = source.find("<PresenceClockChip")
            photo = source.find(anchor)
            if chip == -1:
                violations.append(f"{source_path.name}: لا رقاقةَ عدّادٍ إطلاقاً")
            elif photo == -1:
                violations.append(f"{source_path.name}: مرساةُ الصورة `{anchor}` تغيّرت — الحارسُ يقيس العدم")
            elif chip > photo:
                violations.append(f"{source_path.name}: الرقاقةُ بعد الصورة لا فوقها")
        self.assertEqual(violations, [], f"العدّادُ ليس فوق الوجه: {violations}")

    def test_one_chip_serves_both_places(self):
        """سلّمُ الألوانِ نسختين يفترق عند أوّل تعديلٍ للعتبة."""
        violations = []
        if not CHIP.exists():
            violations.append("لا مكوّنَ رقاقةٍ مشتركاً")
        for source_path, _ in self.PHOTO_ANCHORS:
            source = source_path.read_text(encoding="utf-8")
            # **الاستعمالُ لا الاستيراد**: سطرُ `import` يبقى بعد حذف الوسم،
            # فحارسٌ على الاسم وحدَه يبقى أخضرَ ولا رقاقةَ على الشاشة.
            if "<PresenceClockChip" not in source:
                violations.append(f"{source_path.name}: يرسم رقاقتَه بنفسِه أو لا يرسمها")
            if "bg-emerald-100" in source and "presence" in source.lower():
                violations.append(f"{source_path.name}: سلّمُ ألوانِ الحضور عاد نسخةً محلّيّة")
        self.assertEqual(violations, [], f"الرقاقةُ ليست شيئاً واحداً: {violations}")

    def test_a_payload_without_the_counter_is_not_shown_as_zero(self):
        """صفرُ ثوانٍ «لم يحضر»، وغيابُ الحقل «حمولةٌ لا تحمله» — لا يُوحَّدان.

        والقاعدةُ نفسُها صارت `presenceClockLabel` الخالصةَ يختبرها `npm test`؛
        وما يُحرَس هنا أنّ الرقاقةَ تمرّ بها ولا تنادي المُنسّقَ الخامَ فتعرض
        `00:00` لمن لا تعرف عنه شيئاً.
        """
        source = CHIP.read_text(encoding="utf-8")
        violations = []
        if "presenceClockLabel(" not in source:
            violations.append("الرقاقةُ لا تمرّ بقاعدة «غيابُ الحقل شُرطتان»")
        if "formatPresenceClock(" in source:
            violations.append("الرقاقةُ تنادي المُنسّقَ الخامَ فيصير الغيابُ صفراً")
        if "presenceToneOf(" not in source:
            violations.append("نبرةُ الرقاقة تُقرَّر في المكوّن — منطقٌ لا يراه `npm test`")
        self.assertEqual(violations, [], f"الرقاقةُ تتجاوز قاعدتَها: {violations}")

    def test_both_places_read_the_server_ledger_not_a_client_side_stopwatch(self):
        violations = []
        if "employee.presence_seconds_today" not in CARD.read_text(encoding="utf-8"):
            violations.append("البطاقةُ لا تقرأ دفترَ الخادم")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        # المقعدُ لا يستقصي بنفسِه: الحمولةُ تحمل الحقلين أصلاً، فتمريرُهما
        # يمنع نداءً ثانياً لكلّ وجهٍ حول الطاولة.
        for field in ("presenceSeconds: employee.presence_seconds_today",
                      "presenceTargetHours: employee.presence_target_hours"):
            if field not in dashboard:
                violations.append(f"اللوحةُ لا تمرّر `{field.split(':')[0]}` إلى المقعد")
        for source_path in (CARD, ROOM, CHIP):
            if "setInterval" in source_path.read_text(encoding="utf-8"):
                violations.append(f"{source_path.name}: ساعةُ إيقافٍ في المتصفّح مكان دفتر الخادم")
        self.assertEqual(violations, [], f"العدّادُ لا يقرأ الدفترَ: {violations}")


class PresencePanelShowsTheRuleAndTheEffectTest(TestCase):
    def test_the_panel_is_mounted_in_the_performance_tab(self):
        """لوحةٌ مبنيّةٌ غيرُ مركَّبةٍ شاشةٌ ميّتة — وهذا عيبٌ تكرّر في هذه المواصفة."""
        shell = (STAFF / "StaffShell.tsx").read_text(encoding="utf-8")
        start = shell.find("performance:")
        self.assertNotEqual(start, -1)
        end = shell.find("profile:", start)
        section = shell[start:end if end != -1 else len(shell)]
        self.assertRegex(
            section, r"<StaffPresencePanel[\s/>]",
            "لوحةُ الحضور غير مركَّبةٍ في تبويب «أدائي» — حيث يسكن التقييمُ الذي تؤثّر فيه.",
        )

    def test_the_panel_shows_the_score_before_and_after_the_factor(self):
        """خصمٌ لا يرى صاحبُه مقدارَه شكوى قادمةٌ لا تقييم."""
        source = PANEL.read_text(encoding="utf-8")
        self.assertIn("score_before", source)
        self.assertIn("score_after", source)

    def test_the_panel_shows_the_threshold_and_cap_from_the_server(self):
        """الموظّفُ يعرف القاعدةَ التي حُوسِب بها لا نتيجتَها وحدَها."""
        source = PANEL.read_text(encoding="utf-8")
        self.assertIn("min_hours_per_day", source)
        self.assertIn("day_cap_percent", source)
        self.assertNotRegex(
            source, r"(?:المطلوب|العتبة)\s*٣|>\s*3\s*ساعات",
            "العتبةُ مكتوبةٌ في الواجهة — تُقرأ من السياسة لا تُثبَّت رقماً.",
        )

    def test_no_days_at_all_reads_as_no_judgement_not_as_a_penalty(self):
        source = PANEL.read_text(encoding="utf-8")
        self.assertRegex(source, r"!log\.is_applicable[\s\S]{0,200}لا خصمَ")


class PresenceApiClientIsHonestTest(TestCase):
    def test_the_heartbeat_sends_no_employee_identifier(self):
        """**لا انتحالَ حضور**: من ينبض هو صاحبُ الجلسة، يشتقّه الخادم."""
        source = API.read_text(encoding="utf-8")
        start = source.index("export const sendPresenceHeartbeat")
        # تُقتطَع **جملةُ النبضة وحدَها**: النافذةُ الثابتةُ كانت تمتدّ إلى
        # `getPresenceLog` التي تأخذ `employee` بحقٍّ (قراءةُ المدير)، فيسقط
        # الحارسُ على كودٍ سليم.
        nxt = source.find("export const ", start + 1)
        beat = source[start:nxt if nxt != -1 else len(source)]
        self.assertIn("sendPresenceHeartbeat", beat)
        self.assertNotRegex(
            beat, r"employee",
            "عميلُ الـAPI يرسل معرّفَ موظّفٍ مع النبضة — بابُ انتحالِ حضور.",
        )

    def test_every_presence_route_is_called_from_a_component(self):
        """تعدادُ استهلاكٍ يَعدُّ النداءَ في مكوّن — كدرسِ 212-C."""
        exported = re.findall(r"^export const (\w+)\s*=", API.read_text(encoding="utf-8"), re.MULTILINE)
        self.assertEqual(set(exported), {"sendPresenceHeartbeat", "getPresenceLog"})
        consumers = "\n".join(
            path.read_text(encoding="utf-8")
            # الحلقةُ خارج `staff/` منذ 212-N1 — تركّبها قشرةُ الشركة أيضاً.
            for path in [*STAFF.glob("*.tsx"), CARD, BEAT_HOOK]
        )
        for function in exported:
            with self.subTest(function=function):
                self.assertRegex(
                    consumers, rf"\b{function}\s*\(",
                    f"‏`{function}` مكتوبةٌ في عميل الـAPI ولا يستدعيها مكوّن — نقطةٌ بلا شاشة.",
                )


class PresenceNumbersGoThroughTheFormattersTest(TestCase):
    def test_no_locale_formatters_and_no_second_clock_implementation(self):
        for path in (PANEL, CARD, TOP_BAR, CHIP, ROOM):
            source = path.read_text(encoding="utf-8")
            with self.subTest(source=path.name):
                self.assertNotIn("toLocaleTimeString", source)
                self.assertNotIn("toLocaleString", source)
                self.assertNotIn(
                    "/ 3600", source,
                    f"{path.name} يشتقّ الساعاتَ بنفسِه — التحويلُ في "
                    "`utils/presenceClock.ts` وحدَه، ونسخةٌ ثانيةٌ تعرض `2:5` مكان `02:05`.",
                )


class TheHeartbeatIsNotLockedInsideTheStaffShellTest(TestCase):
    """حضورُ الموظّف كان يُسجَّل من قشرة `/staff` وحدَها (212-N1).

    وهو يقضي يومَه في نظام الشركة التي يخدمها: يفتح `/staff` دقيقةً ثمّ يعمل
    ساعاتٍ في شاشات الشركة. فكان عدّادُ حضوره يقرأ دقائقَ — **والحضورُ يدخل في
    التقييم** (`presence_discipline_factor`)، أي خصمٌ على وقتٍ عُمِل ولم يُسجَّل
    لأنّ الشاشةَ التي تسجّله ليست الشاشةَ التي يعمل فيها.
    """

    def test_the_company_shell_mounts_the_heartbeat(self):
        source = APP_LAYOUT.read_text(encoding="utf-8")
        violations = []
        if "usePlatformPresenceHeartbeat(" not in source:
            violations.append("قشرةُ الشركة لا تركّب النبضة — العدّادُ يقرأ صفراً ليومِ عمل")
        if "presenceHeartbeatEnabled(" not in source:
            violations.append("لا شرطَ على النبضة — كلُّ مستخدمِ شركةٍ ينبض كلَّ دقيقة")
        self.assertEqual(violations, [], f"النبضةُ ما زالت حبيسةَ `/staff`: {violations}")

    def test_the_staff_bar_and_the_company_shell_share_one_loop(self):
        """نسخةٌ ثانيةٌ من الحلقة = مؤقّتان يختلفان بصمتٍ عند أوّل تعديل."""
        top_bar = TOP_BAR.read_text(encoding="utf-8")
        self.assertIn("usePlatformPresenceHeartbeat(", top_bar)
        self.assertNotIn(
            "setInterval", top_bar,
            "شريطُ `/staff` عاد يكتب مؤقّتَه بنفسِه — حلقتان لقاعدةٍ واحدة.",
        )

    def test_the_decision_of_who_beats_is_a_tested_pure_rule(self):
        """قاعدةٌ تُقرَّر في مكوّنٍ لا يراها `npm test` — و`tsc` لا يفحص منطقاً."""
        rule = (FRONTEND / "utils" / "presenceHeartbeat.ts")
        self.assertTrue(rule.exists(), "قاعدةُ «من ينبض» ليست دالّةً خالصةً قابلةً للاختبار.")
        self.assertTrue(
            (FRONTEND / "utils" / "presenceHeartbeat.test.ts").exists(),
            "القاعدةُ الخالصةُ بلا اختبار — البوّابةُ لا تحرس شيئاً.",
        )
        source = rule.read_text(encoding="utf-8")
        self.assertIn(
            "isPlatformEmployee", source,
            "شرطُ النبضة لا يذكر موظّفَ المنصّة — فهو إمّا للجميع أو لأحد.",
        )
