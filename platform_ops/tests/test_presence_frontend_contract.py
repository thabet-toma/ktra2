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


class HeartbeatTicksEveryMinuteTest(TestCase):
    def test_the_counter_beats_every_minute_and_clears_its_interval(self):
        """«بدي التحديث يكون كل دقيقة للشاشة تجيب المعلومات» — نصُّ طلب المالك."""
        source = TOP_BAR.read_text(encoding="utf-8")
        self.assertRegex(source, r"setInterval\([\s\S]*?,\s*(?:60000|60\s*\*\s*1000)\)")
        self.assertIn("clearInterval", source)

    def test_the_interval_actually_calls_the_heartbeat(self):
        """مؤقّتٌ يدقّ ولا ينادي الخادمَ عدّادٌ يتحرّك في الشاشة ولا يُسجّل شيئاً.

        وهذا بعينه ما كان قبل هذه التذكرة: مؤقّتٌ كلَّ دقيقةٍ يحسب فرقَ ساعةِ
        المتصفّح من `sessionStorage` — أخضرَ في حارسِ «كلّ دقيقة» وبلا دفترٍ
        خادميٍّ إطلاقاً.
        """
        source = TOP_BAR.read_text(encoding="utf-8")
        self.assertIn("sendPresenceHeartbeat", source)
        interval = source[source.index("setInterval"):]
        self.assertRegex(
            interval[:200], r"beat\(\)",
            "المؤقّتُ لا ينادي دالّةَ النبضة — عدّادٌ يتحرّك بلا تسجيل.",
        )

    def test_the_counter_no_longer_trusts_the_browser_clock(self):
        source = TOP_BAR.read_text(encoding="utf-8")
        # **النداءُ لا الذِّكر**: التعليقُ أعلى المكوّن يشرح العدّادَ القديم
        # ليُفهَم سببُ استبداله، ومنعُ الاسمِ نصّاً يمنع كتابةَ ذلك الشرح.
        for used in ("sessionStorage.getItem", "sessionStorage.setItem", "Date.now()"):
            self.assertNotIn(
                used, source,
                f"عدّادُ الجلسة القديمُ عاد ({used}): رقمٌ يملكه المتصفّح لا يعرفه "
                "التقييمُ ولا يراه المدير.",
            )

    def test_a_hidden_tab_does_not_beat(self):
        """لسانٌ منسيٌّ مفتوحٌ طوالَ الليل ليس حضوراً."""
        source = TOP_BAR.read_text(encoding="utf-8")
        self.assertIn("visibilityState", source)


class TheCounterSitsAboveThePhotoTest(TestCase):
    def test_the_counter_is_rendered_above_the_employee_photo_in_the_table(self):
        """«يبين بالطاولة فوق صورتو» — فوقَها لا بجانبها ولا في مكانٍ آخر."""
        source = CARD.read_text(encoding="utf-8")
        self.assertIn("presenceLabel", source)
        chip = source.find("presenceLabel}")
        photo = source.find("employee.photo_url ?")
        self.assertNotEqual(chip, -1, "رقاقةُ العدّاد غير موجودةٍ في بطاقة الموظّف.")
        self.assertNotEqual(photo, -1)
        self.assertLess(
            chip, photo,
            "العدّادُ مرسومٌ بعد الصورة لا فوقها — والمالك طلب «فوق صورتو».",
        )

    def test_a_payload_without_the_counter_is_not_shown_as_zero(self):
        """صفرُ ثوانٍ «لم يحضر»، وغيابُ الحقل «حمولةٌ لا تحمله» — لا يُوحَّدان."""
        source = CARD.read_text(encoding="utf-8")
        self.assertRegex(
            source, r"presenceSeconds === undefined[\s\S]{0,120}--:--",
            "غيابُ الحقل يُعرَض صفراً، فتقول البطاقةُ «لم يحضر» عن موظّفٍ لا تعرف عنه شيئاً.",
        )

    def test_the_card_reads_the_seconds_not_a_client_side_stopwatch(self):
        source = CARD.read_text(encoding="utf-8")
        self.assertIn("employee.presence_seconds_today", source)
        self.assertNotIn("setInterval", source)


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
            for path in [*STAFF.glob("*.tsx"), CARD]
        )
        for function in exported:
            with self.subTest(function=function):
                self.assertRegex(
                    consumers, rf"\b{function}\s*\(",
                    f"‏`{function}` مكتوبةٌ في عميل الـAPI ولا يستدعيها مكوّن — نقطةٌ بلا شاشة.",
                )


class PresenceNumbersGoThroughTheFormattersTest(TestCase):
    def test_no_locale_formatters_and_no_second_clock_implementation(self):
        for path in (PANEL, CARD, TOP_BAR):
            source = path.read_text(encoding="utf-8")
            with self.subTest(source=path.name):
                self.assertNotIn("toLocaleTimeString", source)
                self.assertNotIn("toLocaleString", source)
                self.assertNotIn(
                    "/ 3600", source,
                    f"{path.name} يشتقّ الساعاتَ بنفسِه — التحويلُ في "
                    "`utils/presenceClock.ts` وحدَه، ونسخةٌ ثانيةٌ تعرض `2:5` مكان `02:05`.",
                )
