"""سطحُ الموظّف يخفي ما لا يستطيعه — لا يعرضه ثمّ يردّ الخادمُ ٤٠٣ (212-Q2).

قاعدةُ المالك حرفيّاً: «الفرقُ الوحيد إنّه يراعي الصلاحيات، ما يبيّنّ لهم إنّهم
بقدروا يحطّوا التقييم أو أيّ صلاحيّة للسوبر أدمن». أي أنّ مساحةَ الموظّف هي
مركزُ القيادة نفسُه، والفرقُ **ما يُعرَض** لا شاشةٌ أفقر.

**ولماذا حارسٌ ساكن:** `npm test` هنا `node --test` على دوالَّ خالصةٍ لا يصيّر
مكوّناً، و`tsc` لا يفحص شرطَ عرضٍ في JSX. فالسؤالُ «هل هذا الزرُّ محجوبٌ عمّن
لا يملكه؟» يُقرأ نصّاً أو لا يُقرأ أصلاً.

**والعطبُ الذي أنشأ هذا الملفّ:** `WorkOrdersPanel` تُركَّب في القشرتين، وكان
زرّا «اعتماد» و«رفض» على المُسلَّم يُصيَّران بلا شرطٍ — فصاحبُ العمل يرى على
تسليمه هو الحكمَ الذي يولّد وحداتِ استخدامٍ تُخصم من حصّة العميل وتُحتسب إنجازاً
له. والخادمُ يردّ `manager_only`، فالزرُّ كان وعداً كاذباً ودعوةً إلى تقييم النفس
في آنٍ واحد.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend_v2"
PLATFORM_VIEWS = REPO / "platform_ops" / "views.py"
CRM_VIEWS = REPO / "crm" / "views.py"
WORK_ORDERS = FRONTEND / "components" / "platform" / "WorkOrdersPanel.tsx"

#: جذرُ سطحِ الموظّف — كلُّ ما يُصيَّر له يُبلَغ من هنا بالاستيراد.
STAFF_ENTRY = "components/platform/staff/StaffShell.tsx"

#: نداءاتُ العميل التي يحرسها الخادمُ لمدير العمليات وحدَه، وكلُّ سطرٍ منها
#: يتحقّق من مصدر الخادم في `test_every_watched_call_is_really_manager_only`
#: — فالجدولُ لا يتقادم بصمتٍ إن فُتح فعلٌ أو أُغلق.
MANAGER_ONLY_CALLS: dict[str, tuple[Path, str]] = {
    "assignWorkOrder": (PLATFORM_VIEWS, "assign"),
    "changeWorkOrderPriority": (PLATFORM_VIEWS, "change_priority"),
    "createWorkOrder": (PLATFORM_VIEWS, "create_order"),
    "reviewWorkOrderDeliverable": (PLATFORM_VIEWS, "review_deliverable"),
    "releaseCrmLead": (CRM_VIEWS, "release"),
    "approveCrmLead": (CRM_VIEWS, "approve"),
    "rejectCrmLead": (CRM_VIEWS, "reject"),
    "importCrmLeads": (CRM_VIEWS, "import_leads_action"),
}

#: أسماءُ رايةِ الصلاحيّة كما تُسمّى في الواجهة — كلاهما `is_platform_admin`.
GATE_FLAGS = ("isManager", "canManage")

#: خصائصُ الحدث: الزرُّ الذي يُنقر، لا نداءٌ في `useEffect`. الفرقُ جوهريّ —
#: تحميلٌ مشروطٌ داخل الدالّة لا يَعِد المستخدمَ بشيء، والزرُّ يَعِد.
EVENT_PROPS = ("onClick", "onSubmit", "onChange")

IMPORT_RE = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+['\"]([^'\"]+)['\"]", re.S)
COMPONENT_RE = re.compile(r"^(?:export )?const (\w+)(?::\s*React\.FC|\s*=\s*\(|\s*=\s*React\.memo)", re.M)


def _staff_surface() -> dict[str, str]:
    """ملفّاتُ الواجهة المبلوغةُ من قشرة الموظّف ← نصُّها.

    الاستيرادُ هو الحقيقة: مكوّنٌ لا يبلغه استيرادٌ من `StaffShell` لا يراه
    الموظّفُ مهما كان اسمُه، ومكوّنٌ يبلغه يراه ولو كان مكتوباً لِلوحة المدير.
    """
    seen: dict[str, str] = {}
    stack = [STAFF_ENTRY]
    while stack:
        rel = stack.pop()
        if rel in seen:
            continue
        path = FRONTEND / rel
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        seen[rel] = source
        for _, target in IMPORT_RE.findall(source):
            if not target.startswith("."):
                continue
            base = (path.parent / target).resolve()
            for suffix in (".tsx", ".ts"):
                candidate = base.with_suffix(suffix)
                if candidate.exists():
                    stack.append(candidate.relative_to(FRONTEND).as_posix())
                    break
    return seen


def _gated_spans(source: str) -> list[tuple[int, int]]:
    """مدَياتُ JSX المشروطةُ بالصلاحيّة — `{isManager && ...}` بأقواسها المتوازنة."""
    spans: list[tuple[int, int]] = []
    for flag in GATE_FLAGS:
        for match in re.finditer(r"\{" + flag + r"\s*&&", source):
            depth = 0
            for index in range(match.start(), len(source)):
                if source[index] == "{":
                    depth += 1
                elif source[index] == "}":
                    depth -= 1
                    if depth == 0:
                        spans.append((match.start(), index))
                        break
    return spans


def _inside(spans: list[tuple[int, int]], position: int) -> bool:
    return any(start <= position <= end for start, end in spans)


def _enclosing_component(source: str, position: int) -> str | None:
    name = None
    for match in COMPONENT_RE.finditer(source):
        if match.start() > position:
            break
        name = match.group(1)
    return name


ARROW_RE = re.compile(r"const (\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]*?)?=>\s*\{")


def _handlers_calling(source: str, call: str) -> set[str]:
    """أسماءُ المعالِجات التي يمرّ نداءُ الخادم من **داخل جسمها**.

    والقياسُ على الجسم لا على «أقربِ `const` قبله»: النداءُ يُكتب عادةً
    ‏`const updated = await assignWorkOrder(...)`، فأقربُ تعريفٍ قبله هو
    `updated` لا المعالِج — وحارسٌ يقرأ الاسمَ الخطأ لا يجد له `onClick`
    فيمرّ أخضرَ على زرٍّ مكشوف. قِيس ذلك: بهذه القراءةِ الخطأ نجا تخريبُ
    «الإسنادُ والأولويّةُ بلا شرط».
    """
    handlers: set[str] = set()
    positions = [match.start() for match in re.finditer(re.escape(call) + r"\s*\(", source)]
    if not positions:
        return handlers
    for match in ARROW_RE.finditer(source):
        brace = source.index("{", match.end() - 1)
        depth = 0
        for index in range(brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    if any(brace < position < index for position in positions):
                        handlers.add(match.group(1))
                    break
    return handlers


class TheEmployeeSurfaceHidesWhatItCannotDoTest(SimpleTestCase):
    """لا زرَّ على سطح الموظّف يقود إلى فعلٍ يحرسه الخادمُ للمدير وحدَه."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.surface = _staff_surface()

    def test_the_surface_reader_reaches_the_shared_panels(self):
        """قارئُ السطح ليس فارغاً — وإلّا مرّ الحارسُ الآتي على العدم."""
        self.assertIn(
            "components/platform/WorkOrdersPanel.tsx", self.surface,
            "قارئُ الاستيراد لم يبلغ لوحةَ أوامر العمل — الحارسُ التالي يقيس لا شيء.",
        )
        self.assertGreaterEqual(len(self.surface), 20, f"سطحٌ من {len(self.surface)} ملفّاً فقط — القراءةُ انكسرت.")

    def test_every_watched_call_is_really_manager_only(self):
        """الجدولُ أعلاه يُقاس على مصدر الخادم لا يُصدَّق.

        فعلٌ يُفتَح للموظّف يوماً يجب أن يخرج من الجدول، لا أن يبقى فيه فيخفي
        الحارسُ زرّاً صار من حقّه.
        """
        violations = []
        for call, (views, action) in MANAGER_ONLY_CALLS.items():
            source = views.read_text(encoding="utf-8")
            start = source.find(f"def {action}(self, request")
            if start == -1:
                violations.append(f"{call}: لا فعلَ باسم `{action}` في {views.name}")
                continue
            decorator = source.rfind("@action(", 0, start)
            end = source.find("@action(", start)
            block = source[decorator if decorator != -1 else start:end if end != -1 else len(source)]
            declared = "permission_classes=[IsPlatformOperationsManager]" in block
            inline = "if not IsPlatformOperationsManager().has_permission(request, self):" in block
            if not (declared or inline):
                violations.append(f"{call}: `{action}` لم يعد محروساً لمدير العمليات وحدَه")
        self.assertEqual(violations, [], f"جدولُ الأفعال المحروسة تقادم: {violations}")

    def test_no_control_on_the_employee_surface_triggers_a_manager_only_call(self):
        """‏**الحارسُ نفسُه**: كلُّ زرٍّ يقود إلى فعلِ مديرٍ يجب أن يكون محجوباً.

        وثلاثةُ أشكالٍ للحجب تُقبل، وهي المستعمَلةُ فعلاً في هذا الكود:
        شرطٌ في JSX (`{isManager && ...}`)، أو خروجٌ مبكّرٌ من المكوّن كلِّه
        (`if (!isManager) return null;`)، أو مكوّنٌ كلُّ مواضعِ تركيبه مشروطة.
        """
        violations = []
        for rel, source in sorted(self.surface.items()):
            spans = _gated_spans(source)
            early_out = any(f"if (!{flag}) return null;" in source for flag in GATE_FLAGS)
            for call in MANAGER_ONLY_CALLS:
                if f"{call}(" not in source:
                    continue
                for handler in _handlers_calling(source, call):
                    for prop in EVENT_PROPS:
                        for match in re.finditer(re.escape(prop) + r"=\{[^}]*\b" + re.escape(handler) + r"\b", source):
                            if early_out or _inside(spans, match.start()):
                                continue
                            owner = _enclosing_component(source, match.start())
                            if owner and self._mounted_only_behind_a_gate(owner, rel):
                                continue
                            violations.append(f"{rel}: `{prop}` ← `{handler}` ← `{call}` بلا شرطِ صلاحيّة")
        self.assertEqual(
            violations, [],
            "أزرارٌ تَعِد الموظّفَ بفعلٍ يردّه الخادمُ لمدير العمليات وحدَه: " + str(violations),
        )

    def _mounted_only_behind_a_gate(self, component: str, home: str) -> bool:
        """مكوّنٌ داخليٌّ لا يُصيَّر إلّا داخل شرطٍ — فأزرارُه محجوبةٌ بتركيبه."""
        mounts = 0
        for rel, source in self.surface.items():
            spans = _gated_spans(source)
            for match in re.finditer(r"<" + re.escape(component) + r"[\s/>]", source):
                if rel == home and match.start() < source.find(f"const {component}"):
                    continue
                mounts += 1
                if not _inside(spans, match.start()):
                    return False
        return mounts > 0


class TheVerdictOnTheWorkIsNotForItsAuthorTest(SimpleTestCase):
    """حكمُ المُسلَّم للمدير، وخبرُه لصاحبه — 212-Q2 حرفيّاً.

    الحجبُ هنا **حجبُ فعلٍ لا حجبُ معلومة**: الموظّفُ يبقى يقرأ حالةَ تسليمه
    (بانتظار المراجعة · معتمَد · مردود) وسببَ الردّ إن رُدّ. لو حُجبت الحالةُ
    معها لصار الموظّفُ يسلّم في الظلام، وهو عطبٌ آخرُ بدل عطب.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = WORK_ORDERS.read_text(encoding="utf-8")

    def test_the_verdict_buttons_sit_behind_the_manager_flag(self):
        """‏**المرساةُ نقرةٌ لا كلمة**: «رفض» جزءٌ من «تأكيد الرفض»، وتسمياتُ
        الحالات تكرّر نصوصَ الأزرار — فالبحثُ بالنصّ يقيس أوّلَ ما صادف."""
        spans = _gated_spans(self.source)
        violations = []
        clicks = {
            "اعتماد المُسلَّم": "onClick={() => handleApprove(d.id)}",
            "تأكيد الردّ": "onClick={() => handleReject(d.id)}",
            "فتحُ نموذج الردّ": "onClick={() => setRejectingId(d.id)}",
        }
        for what, anchor in clicks.items():
            position = self.source.find(anchor)
            if position == -1:
                violations.append(f"«{what}» اختفى — الحارسُ يقيس العدم")
            elif not _inside(spans, position):
                violations.append(f"«{what}» يُعرَض بلا شرطِ صلاحيّة")
        self.assertEqual(violations, [], f"حكمُ المُسلَّم معروضٌ لصاحبه: {violations}")

    def test_the_author_still_reads_the_verdict(self):
        spans = _gated_spans(self.source)
        badge = self.source.find("{d.review_status_display}")
        self.assertNotEqual(badge, -1, "شارةُ حالة المُسلَّم اختفت.")
        self.assertFalse(
            _inside(spans, badge),
            "حالةُ المُسلَّم صارت خلف شرط المدير — فالموظّفُ يسلّم ولا يعرف مصيرَ تسليمه.",
        )
