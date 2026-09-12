"""حرّاسٌ ساكنون على غرفة «مساحة العمل» (#211 م٣، 211-I).

**لماذا بايثون لواجهةٍ في React؟** لأنّ `npm test` هنا يشغّل `utils/*.test.ts` عبر
`node --test` — دوالَّ خالصةً لا تُصيّر مكوّناً واحداً: فلا ترى صنف CSS ولا خاصيّةَ
JSX ولا تخطيطاً. و`tsc` لا يفحص وجودَ صنفٍ في ملفّ أنماط. فالعيبُ الوحيدُ الذي
يُخفي اسمَ موظّفٍ — بطاقتان تتراكبان، أو مقعدٌ بلا قاعدةِ موضعٍ فيستقرّ في الزاوية —
لا يمسكه شيءٌ في البوّابة إلاّ حارسٌ ساكنٌ يقرأ الملفّين معاً.

**والنموذجُ الهندسيُّ مقيسٌ لا مُخمَّن.** قيست صناديقُ المقاعد في متصفّحٍ حقيقيّ
على الملفّين نفسِهما (١٤ عرضاً من ٣٢٠ إلى ١٩٢٠ بكسل)، فخرج منها مقداران ثابتان:
عرضُ البطاقة `max(12% من عرض الغرفة, 64px) × العمق`، وارتفاعُها `100.5px × العمق`
(ثلاثةُ أسطرٍ بـ`truncate` فلا تلتفّ). وعليهما يُعاد حسابُ التراكب هنا في كلّ
تشغيل. والقياسُ الأوّلُ هو ما كشف العيب: عند ٥٤١ بكسل كان المقعدان ٢ و٣ يتراكبان
٦٨×٣٣ بكسل — أي سطرا الدور والحالة لأحدهما مُغطَّيان تماماً — والحلقةُ «العشاريّة»
كانت قد أُنقصت من اثني عشر مقعداً لهذا السبب بالذات ولم تُقِسْ نتيجتَها.
"""
import math
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS_PATH = REPO_ROOT / "frontend_v2" / "styles" / "index.css"
ROOM_PATH = REPO_ROOT / "frontend_v2" / "components" / "platform" / "WorkspaceRoom.tsx"
DASHBOARD_PATH = REPO_ROOT / "frontend_v2" / "components" / "platform" / "PlatformOpsDashboard.tsx"

#: المقداران المقيسان في المتصفّح (انظر شرح الوحدة).
SEAT_WIDTH_PCT = 12.0
SEAT_MIN_WIDTH_PX = 64.0
SEAT_HEIGHT_PX_PER_DEPTH = 100.5

#: حدودُ ارتفاع الغرفة ومقاسُ المقعد — يحرس `RoomBoxModelMatchesTheCssTest` مطابقتَها للملفّ.
ROOM_ASPECT = 16 / 10
ROOM_MIN_HEIGHT_PX = 34 * 16
ROOM_MAX_HEIGHT_PX = 40 * 16

#: العروضُ التي يُعاد الحسابُ عليها — تشمل الهاتفَ واللوحَ والشاشةَ العريضة.
PROBED_WIDTHS = (320, 360, 420, 480, 520, 541, 560, 640, 700, 900, 1200, 1600, 1920)

#: دون هذا العرض تُستبدَل الحلقةُ بشبكةٍ (`@container`)، فلا معنى لفحص التراكب.
RING_MIN_WIDTH_PX = 33.8 * 16


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _room_source() -> str:
    return ROOM_PATH.read_text(encoding="utf-8")


def _seat_rules(css: str) -> dict[int, tuple[float, float, float]]:
    """`.pf-seat-N { left: X%; top: Y%; --pf-depth: D; ... }` → {N: (X, Y, D)}."""
    pattern = re.compile(
        r"\.pf-seat-(\d+)\s*\{[^}]*?left:\s*([\d.]+)%[^}]*?top:\s*([\d.]+)%"
        r"[^}]*?--pf-depth:\s*([\d.]+)",
        re.S,
    )
    return {
        int(index): (float(left), float(top), float(depth))
        for index, left, top, depth in pattern.findall(css)
    }


def _seat_count(source: str) -> int:
    match = re.search(r"const SEAT_COUNT = (\d+);", source)
    assert match is not None, "تعذّر قراءة `SEAT_COUNT` من المكوّن."
    return int(match.group(1))


def _room_height(width: float) -> float:
    return min(max(width / ROOM_ASPECT, ROOM_MIN_HEIGHT_PX), ROOM_MAX_HEIGHT_PX)


class SeatClassesCoverTheComponentTest(SimpleTestCase):
    """كلُّ مقعدٍ يرسمه المكوّن له قاعدةُ موضعٍ — ولا قاعدةَ زائدةٌ بلا مقعد."""

    def test_every_seat_the_component_renders_has_a_position_rule(self):
        """رفعُ `SEAT_COUNT` بلا توليدِ الأصناف يُنتج مقاعدَ بلا `left`/`top`.

        وتلك لا تختفي بل تستقرّ كلُّها في زاوية الغرفة فوق بعضها (`position:
        absolute` بلا إزاحة) — موظّفون مكدَّسون في نقطةٍ واحدة، والشاشةُ لا تشتكي.
        """
        expected = set(range(_seat_count(_room_source())))
        actual = set(_seat_rules(_css()))
        missing = sorted(expected - actual)
        self.assertFalse(
            missing,
            f"مقاعدُ يرسمها المكوّن بلا قاعدةِ موضعٍ في `index.css`: {missing}",
        )

    def test_no_orphan_seat_rule_outlives_the_component(self):
        expected = set(range(_seat_count(_room_source())))
        orphans = sorted(set(_seat_rules(_css())) - expected)
        self.assertFalse(
            orphans,
            f"قواعدُ مقاعدَ لا يرسمها المكوّن (`SEAT_COUNT` نقص ولم تُحذف): {orphans}",
        )

    def test_every_room_class_the_component_uses_is_defined(self):
        """صنفٌ مستعمَلٌ غيرُ معرَّف = عنصرٌ بلا أنماطٍ إطلاقاً، بلا خطأٍ في أيّ بوّابة.

        و`.pf-room-shell` خاصّةً: بدونه لا حاويةَ لاستعلام `@container`، فيبقى
        الهاتفُ على الحلقة المتراكبة والقاعدةُ البديلةُ لا تُطبَّق أبداً.
        """
        css = _css()
        used = set(re.findall(r"pf-(?:room|seat)[\w-]*", _room_source()))
        # `pf-seat-${index}` يُركَّب في زمن التشغيل فيصل هنا بذيلٍ مفتوح
        # (`pf-seat-`)؛ وأرقامُه يحرسها `SeatClassesCoverTheComponentTest` أعلاه.
        used = {name for name in used if not name.endswith("-")}
        # حدُّ كلمةٍ لا تضمين: `.pf-room-shell` جزءٌ من `.pf-room-shellX`، فالبحثُ
        # بالتضمين يقبل صنفاً أُعيدت تسميتُه ويبقى العنصرُ بلا أنماط.
        undefined = sorted(
            name for name in used
            if re.search(rf"\.{re.escape(name)}(?![\w-])", css) is None
        )
        self.assertFalse(
            undefined, f"أصنافٌ يستعملها `WorkspaceRoom.tsx` ولا تعريفَ لها في `index.css`: {undefined}",
        )


class RoomBoxModelMatchesTheCssTest(SimpleTestCase):
    """ثوابتُ النموذج الهندسيّ أعلاه تُقابَل بالملفّ نفسِه.

    بدون هذا الحارس تبقى أرقامُ الوحدة صورةً لِما **كان** في `index.css`: يُحذف
    `min-height` من القاعدة فيعود التراكبُ في المتصفّح، ويظلّ فحصُ التراكب أخضرَ
    لأنّه يحسب بارتفاعٍ لم يعد أحدٌ يفرضه. أي حارسٌ لا يستطيع السقوط.
    """

    def _room_block(self) -> str:
        css = _css()
        start = css.index(".pf-room {")
        return css[start : css.index("}", start)]

    def _seat_block(self) -> str:
        css = _css()
        start = css.index(".pf-seat {")
        return css[start : css.index("}", start)]

    def test_the_room_declares_the_aspect_and_the_two_height_bounds(self):
        block = self._room_block()
        self.assertIn("aspect-ratio: 16 / 10", block)
        self.assertIn(f"min-height: {ROOM_MIN_HEIGHT_PX / 16:g}rem", block)
        self.assertIn(f"max-height: {ROOM_MAX_HEIGHT_PX / 16:g}rem", block)

    def test_the_seat_declares_the_width_the_model_assumes(self):
        block = self._seat_block()
        self.assertIn(f"width: {SEAT_WIDTH_PCT:g}%", block)
        self.assertIn(f"min-width: {SEAT_MIN_WIDTH_PX / 16:g}rem", block)

    def test_the_narrow_fallback_breakpoint_matches_the_skipped_range(self):
        """عتبةُ `@container` هي بعينها العتبةُ التي يتوقّف عندها فحصُ التراكب.

        لو انفصلتا لبقي مدىً من العروض بحلقةٍ حقيقيّةٍ لا يفحصها أحد.
        """
        self.assertIn(
            f"@container (max-width: {RING_MIN_WIDTH_PX / 16:g}rem)", _css(),
        )


class SeatsDoNotOverlapTest(SimpleTestCase):
    """لا بطاقةَ تُغطّي بطاقة — التراكبُ يخفي اسماً، وهو أسوأُ ما يفعله لوحُ حضور."""

    def _overlaps(self, width: float) -> list[tuple[int, int, float, float]]:
        seats = _seat_rules(_css())
        height = _room_height(width)
        seat_width = max(SEAT_WIDTH_PCT / 100 * width, SEAT_MIN_WIDTH_PX)
        boxes = {}
        for index, (left, top, depth) in seats.items():
            boxes[index] = (
                left / 100 * width,
                top / 100 * height,
                seat_width * depth,
                SEAT_HEIGHT_PX_PER_DEPTH * depth,
            )
        found = []
        for i in sorted(boxes):
            for j in sorted(boxes):
                if j <= i:
                    continue
                (ax, ay, aw, ah), (bx, by, bw, bh) = boxes[i], boxes[j]
                overlap_x = (aw + bw) / 2 - abs(ax - bx)
                overlap_y = (ah + bh) / 2 - abs(ay - by)
                if overlap_x > 0 and overlap_y > 0:
                    found.append((i, j, round(overlap_x, 1), round(overlap_y, 1)))
        return found

    def test_no_two_seats_overlap_at_any_probed_width(self):
        for width in PROBED_WIDTHS:
            if width < RING_MIN_WIDTH_PX:
                continue  # شبكةٌ لا حلقة — الفحصُ لا ينطبق
            with self.subTest(width=width):
                found = self._overlaps(width)
                self.assertFalse(
                    found,
                    f"بطاقاتٌ متراكبةٌ عند عرض {width} بكسل (مقعد، مقعد، تراكبٌ أفقيّ، رأسيّ): {found}",
                )

    def test_the_guard_would_catch_a_ring_squeezed_back_into_a_short_room(self):
        """إثباتُ أنّ الحارسَ يستطيع السقوط: بلا `min-height` يعود التراكبُ المقيس.

        هذه هي الحالةُ التي كانت قائمةً فعلاً قبل 211-I — ارتفاعٌ من النسبة وحدَها —
        ويجب أن تُرفَض هنا لا أن تمرّ خضراء.
        """
        seats = _seat_rules(_css())
        width, height = 541.0, 541.0 / ROOM_ASPECT  # الارتفاعُ القديم: نسبةٌ بلا أرضيّة
        seat_width = max(SEAT_WIDTH_PCT / 100 * width, SEAT_MIN_WIDTH_PX)
        worst = 0.0
        for i in sorted(seats):
            for j in sorted(seats):
                if j <= i:
                    continue
                lx, ty, di = seats[i]
                rx, by, dj = seats[j]
                overlap_x = (seat_width * di + seat_width * dj) / 2 - abs(lx - rx) / 100 * width
                overlap_y = (
                    SEAT_HEIGHT_PX_PER_DEPTH * (di + dj) / 2 - abs(ty - by) / 100 * height
                )
                if overlap_x > 0 and overlap_y > 0:
                    worst = max(worst, min(overlap_x, overlap_y))
        self.assertGreater(
            worst, 5,
            "الحارسُ لا يستطيع السقوط: حتى الغرفةُ القصيرةُ القديمة تمرّ بلا تراكب — "
            "فالنموذجُ الهندسيُّ صار متساهلاً ولم يعد يحرس شيئاً.",
        )

    def test_no_seat_is_clipped_by_the_room_edges(self):
        """`overflow: hidden` على الغرفة: مقعدٌ يتجاوز الحافّة يُقصّ نصفُه بصمت."""
        seats = _seat_rules(_css())
        for width in PROBED_WIDTHS:
            if width < RING_MIN_WIDTH_PX:
                continue
            height = _room_height(width)
            seat_width = max(SEAT_WIDTH_PCT / 100 * width, SEAT_MIN_WIDTH_PX)
            for index, (left, top, depth) in sorted(seats.items()):
                cx, cy = left / 100 * width, top / 100 * height
                half_w, half_h = seat_width * depth / 2, SEAT_HEIGHT_PX_PER_DEPTH * depth / 2
                with self.subTest(width=width, seat=index):
                    self.assertGreaterEqual(round(cx - half_w, 1), 0)
                    self.assertLessEqual(round(cx + half_w, 1), width)
                    self.assertGreaterEqual(round(cy - half_h, 1), 0)
                    self.assertLessEqual(round(cy + half_h, 1), math.ceil(height))


class RoomReceivesRealMeetingMembershipTest(SimpleTestCase):
    """اللوحةُ تمرّر مجموعةً حقيقيّةً لعضويّة الاجتماع إلى `derivePresence` (211-H).

    قبل 211-H كان `inMeeting` مُثبَّتاً على `null` بتعليقٍ يشرح أنّ الحمولةَ لا
    تحمل «من هو في اجتماعٍ الآن» بعد. صار الحقلُ موجوداً (`is_in_meeting`)، فبقاءُ
    `null` هنا يعني أنّ الضوءَ الأصفرَ **لن يظهر أبداً** مهما صحّ الخادمُ — عطبٌ
    صامتٌ تماماً: لا خطأ، ولا اختبارَ خادميٍّ يكشفه، فقط غرفةٌ لا يصفرّ فيها أحد.
    """

    def test_derive_presence_receives_a_set_not_a_null_literal(self):
        source = DASHBOARD_PATH.read_text(encoding="utf-8")
        call = re.search(r"derivePresence\(\s*employee\s*,\s*(\w+)\s*,\s*employee\.id\s*\)", source)
        self.assertIsNotNone(call, "لم يُعثر على استدعاء derivePresence في اللوحة.")
        var_name = call.group(1)
        declaration = re.search(rf"\bconst {re.escape(var_name)}\b[^;]*;", source, re.S)
        self.assertIsNotNone(declaration, f"لم يُعثر على تعريف المتغيّر `{var_name}`.")
        block = declaration.group(0)
        self.assertNotIn(
            "null", block,
            f"`{var_name}` يُمرَّر `null` صراحةً إلى derivePresence — الضوءُ الأصفرُ "
            f"لا يظهر أبداً مهما صحّت حمولةُ الخادم: {block!r}",
        )
        self.assertIn(
            "is_in_meeting", block,
            f"`{var_name}` لا يُبنى من `is_in_meeting` — مصدرُه ليس دفترَ الحضور: {block!r}",
        )


class RoomIsReachableTest(SimpleTestCase):
    """غرفةٌ مبنيّةٌ بلا تبويبٍ يفتحها كودٌ ميّت — و`tsc` يقبل مكوّناً لا يُستدعى."""

    def test_the_dashboard_mounts_the_room_behind_its_own_tab(self):
        source = DASHBOARD_PATH.read_text(encoding="utf-8")
        for needle, why in (
            ("<WorkspaceRoom", "المكوّنُ غيرُ مُركَّبٍ في اللوحة."),
            ('"workspace_room"', "لا قيمةَ تبويبٍ للغرفة."),
            ('setActiveTab("workspace_room")', "لا زرَّ يفتح التبويب."),
        ):
            self.assertIn(needle, source, why)

    def test_the_room_wears_the_platform_surface_skin_through_its_host(self):
        """الغرفةُ تعتمد `--pf-glow` المعرَّفَ في `.platform-surface` وحدَه.

        فلو رُكّبت خارجَ الغلاف لخرجت بلا لون: `color-mix` مع متغيّرٍ غير معرَّف
        يُسقط الإعلانَ كلَّه، فتصير الحلقاتُ والطاولةُ شفّافةً بلا خطأٍ ظاهر.
        """
        css = _css()
        surface = css[css.index(".platform-surface {"):]
        self.assertIn("--pf-glow:", surface[: surface.index("}")])
        self.assertIn("platform-surface", DASHBOARD_PATH.read_text(encoding="utf-8"))
