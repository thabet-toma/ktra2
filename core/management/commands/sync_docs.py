"""يولّد الحقائق الميكانيكية داخل وثائق التنقّل بدل كتابتها بيد.

**لماذا:** كل ما يُكتب بيد ويصف الكود يتقادم حتماً. جرد واحد على هذا المستودع
أظهر: 13 مرجعاً لملفات لم تعد موجودة، و21 رقم سطر منزاحاً، و«1,025 اختباراً»
في ثلاثة مواضع بينما العدد الحقيقي تجاوز 1,080. كلها **حقائق مشتقّة من الكود**
لا آراء — فمكانها التوليد لا الذاكرة البشرية.

النثر البشري (المسؤوليات، القواعد، «لماذا») يبقى مكتوباً بيد خارج كتل التوليد.

    <!-- AUTO:<اسم>:START -->    ← المولَّد بينهما، لا يُحرَّر يدوياً
    <!-- AUTO:<اسم>:END -->

الاستعمال:
    python manage.py sync_docs              # يكتب
    python manage.py sync_docs --check      # يفشل إن تقادمت كتلة (نمط
                                            #  makemigrations --check)
    python manage.py sync_docs --strip-lines  # مرّة واحدة: `f.py:12` → `f.py`

`--check` يستدعيه حارس `core/tests/test_docs_freshness.py`، فتصير الكتل
المتقادمة إخفاقَ اختبار محلياً — وهو المهم لأن CI لا تعمل على كل الفروع.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

REPO_ROOT = Path(settings.BASE_DIR)

#: `sales/services.py:32` → `sales/services.py` (خارج كتل AUTO فقط)
LINE_REF_RE = re.compile(r"(`[A-Za-z_][\w./-]*\.(?:py|ts|tsx)):\d+`")


def _auto_block_re(name):
    """الكتلة الفارغة يجب أن تطابق أيضاً — وإلا لم تُملأ أول مرة أبداً."""
    return re.compile(
        rf"(<!--\s*AUTO:{re.escape(name)}:START\s*-->)(.*?)(<!--\s*AUTO:{re.escape(name)}:END\s*-->)",
        re.S,
    )


def _local_apps():
    """أسماء الـapps المحلية من `INSTALLED_APPS`.

    ثلاثة apps مسجَّلة بصيغة `after_sales.apps.AfterSalesConfig` لا بالاسم
    المجرّد؛ فلترةٌ ساذجة بـ`"." not in app` كانت تُسقطها بصمت من الجدول ومن
    فحص التغطية معاً.
    """
    apps = []
    for entry in settings.INSTALLED_APPS:
        if entry.startswith("django.") or entry.startswith("rest_framework"):
            continue
        name = entry.split(".")[0]
        if (REPO_ROOT / name).is_dir():
            apps.append(name)
    return apps


def _count_python(app_dir, tests):
    """يعدّ أسطر بايثون في app **مقرَّبةً للمئة**: الكود أو الاختبارات، بلا migrations.

    التقريب مقصود: العدد الدقيق يتغيّر مع كل سطر يُضاف، فيجعل كتلة التوليد
    متقادمة بعد **أي** تعديل مهما صغر — ضجيجٌ على كل جلسة مقابل دقّةٍ لا قيمة
    لها. قيمة العمود ترتيبيّة («أيّ app أضخم») لا محاسبية، والتقريب يبقيها
    صادقة ويجعل الكتلة تتحرّك عند نموّ حقيقي فقط.
    """
    total = 0
    for path in app_dir.rglob("*.py"):
        parts = path.relative_to(app_dir).parts
        if "migrations" in parts:
            continue
        in_tests = "tests" in parts or path.name.startswith("test_")
        if in_tests != tests:
            continue
        total += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return round(total / 100) * 100


# ── المولِّدات ───────────────────────────────────────────────────────────────

# ملاحظة: لا مولِّد لعدد الاختبارات عمداً. الرقم يتغيّر مع **كل** اختبار يُضاف،
# فتوليده يعني ضجيج تحديثٍ دائماً مقابل عددٍ لا يحتاجه أحد بدقّة. الإصلاح الحقيقي
# أن يُمنَع ذكره في الوثائق أصلاً — يحرسه `test_no_hardcoded_test_counts`،
# ومكانه الطبيعي خرج `manage.py test`.


def gen_module_index():
    """قائمة الموديولات التي لها وثيقة — تكتشف الجديد تلقائياً."""
    modules = sorted(p.stem for p in (REPO_ROOT / "docs" / "modules").glob("*.md"))
    return " · ".join(f"`{m}`" for m in modules)


def gen_apps_table(existing):
    """يحدّث أعمدة الأرقام فقط ويُبقي النثر البشري كما هو.

    التوليد الكامل كان سيمحو عمود «المسؤولية» — وهو أثمن ما في الجدول ولا
    يمكن اشتقاقه من الكود.

    **درس مدفوع الثمن:** خطأ في اكتشاف الـapps أسقط أربعة منها من دورة توليد،
    فكُتب الجدول بدونها، فضاع نصّها نهائياً في الدورة التالية (لم يعد لها صفٌّ
    يُقرأ منه). لذلك: مولِّد يفقد صفّاً كان موجوداً **يرفض الكتابة** بدل أن
    يمحو — فقدان النصّ البشري لا يُسترجع إلا من git.
    """
    rows = {}
    for line in existing.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].startswith("`"):
            rows[cells[0].strip("`")] = cells

    apps = [a for a in _local_apps() if (REPO_ROOT / a).is_dir()]
    lost = sorted(set(rows) - set(apps))
    if lost:
        raise CommandError(
            "المولِّد سيفقد صفوفاً موجودة (ونصّها البشري معها): "
            f"{', '.join(lost)}. صحّح اكتشاف الـapps قبل الكتابة."
        )

    out = ["| App | المسؤولية | كود | اختبار | مسار الـAPI |",
           "|---|---|---:|---:|---|"]
    sized = []
    for app in apps:
        prev = rows.get(app, [f"`{app}`", "—", "0", "0", "—"])
        sized.append((_count_python(REPO_ROOT / app, tests=False), app, prev))
    for code, app, prev in sorted(sized, reverse=True):
        tests = _count_python(REPO_ROOT / app, tests=True)
        out.append(f"| `{app}` | {prev[1]} | {code:,} | {tests:,} | {prev[4]} |")
    return "\n".join(out)


def _walk_urls(patterns, prefix=""):
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from _walk_urls(entry.url_patterns, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern):
            view = entry.callback
            cls = getattr(view, "cls", None) or getattr(view, "view_class", None)
            target = cls or view
            yield (
                "/" + (prefix + str(entry.pattern)).lstrip("/"),
                getattr(target, "__name__", str(target)),
                getattr(target, "__module__", ""),
            )


#: `(?P<pk>[^/.]+)` → `{pk}` — الفهرس يُقرأ بالعين لا بمحرّك regex.
NAMED_GROUP_RE = re.compile(r"\(\?P<(\w+)>[^)]*\)")


def _readable_path(raw):
    """يحوّل نمط جانغو الخام إلى مسار مقروء."""
    path = NAMED_GROUP_RE.sub(r"{\1}", raw)
    path = path.replace("^", "").replace("$", "").replace("\\.", ".")
    return "/" + path.lstrip("/")


def gen_api_index():
    """فهرس «أين نقطة الـAPI؟» — مشتقّ من resolver جانغو فلا يكذب أبداً.

    هذا أقوى ردٍّ على سؤال «وين أروح»: يحوّل «صلّح ترحيل فاتورة البيع» إلى قفزة
    مباشرة للملف بلا قراءة سطر كود واحد.

    تُستبعَد نسخ `.format` التي يولّدها DRF لكل مسار (توأمٌ لكل صفّ، ضجيج صافٍ).
    """
    seen, rows = set(), []
    for raw, view, module in _walk_urls(get_resolver().url_patterns):
        if not module or module.startswith("django."):
            continue
        if "(?P<format>" in raw:
            continue
        path = _readable_path(raw)
        key = (path, view)
        if key in seen:
            continue
        seen.add(key)
        rows.append((path, view, module))

    lines = ["| المسار | الـView | الملف |", "|---|---|---|"]
    lines += [
        f"| `{path}` | `{view}` | `{module.replace('.', '/')}.py` |"
        for path, view, module in sorted(rows)
    ]
    return f"عدد النقاط: **{len(rows)}**\n\n" + "\n".join(lines)


#: الكتلة → (الملفات الوجهة، المولِّد، هل يحتاج المحتوى القديم؟)
GENERATORS = {
    "module_index": (["CLAUDE.md"], gen_module_index, False),
    "apps_table": (["ARCHITECTURE.md"], gen_apps_table, True),
    "api_index": (["docs/API_INDEX.md"], gen_api_index, False),
}


class Command(BaseCommand):
    help = "يولّد كتل AUTO في وثائق التنقّل (أو يتحقق من طزاجتها بـ--check)"

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true",
                            help="لا يكتب؛ يفشل إن تقادمت كتلة")
        parser.add_argument("--strip-lines", action="store_true",
                            help="مرّة واحدة: يحذف أرقام الأسطر من مراجع الملفات")

    def handle(self, *args, **options):
        if options["strip_lines"]:
            return self._strip_lines()
        stale = self._sync(check=options["check"])
        if options["check"] and stale:
            raise CommandError(
                "كتل AUTO متقادمة — شغّل `python manage.py sync_docs`:\n  "
                + "\n  ".join(stale)
            )
        self.stdout.write(self.style.SUCCESS(
            "كتل AUTO محدَّثة." if not options["check"] else "كل كتل AUTO طازجة."
        ))

    def _sync(self, check):
        stale = []
        for name, (targets, generator, needs_existing) in GENERATORS.items():
            for target in targets:
                path = REPO_ROOT / target
                if not path.exists():
                    if check:
                        stale.append(f"{target} → غير موجود")
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        f"# {Path(target).stem}\n\n"
                        f"> **مولَّد بالكامل — لا تحرّره يدوياً.**\n"
                        f"> `python manage.py sync_docs`\n\n"
                        f"<!-- AUTO:{name}:START -->\n<!-- AUTO:{name}:END -->\n",
                        encoding="utf-8",
                    )
                    text = path.read_text(encoding="utf-8")
                else:
                    text = path.read_text(encoding="utf-8")
                match = _auto_block_re(name).search(text)
                if not match:
                    continue  # الوثيقة لا تطلب هذه الكتلة
                body = match.group(2)
                fresh = generator(body) if needs_existing else generator()
                if body.strip() == fresh.strip():
                    continue
                stale.append(f"{target} → AUTO:{name}")
                if not check:
                    text = _auto_block_re(name).sub(
                        lambda m: f"{m.group(1)}\n{fresh}\n{m.group(3)}", text, count=1
                    )
                    path.write_text(text, encoding="utf-8")
        return stale

    def _strip_lines(self):
        """ينفّذ سياسة «الرموز لا الأسطر» على الوثائق القائمة.

        رقم السطر ينزاح مع كل تعديل على الملف المُشار إليه، فيكذب بصمت.
        الرمز بين قوسين بعده يبقى صحيحاً ويجده الوكيل بـgrep فوراً.
        """
        docs = [REPO_ROOT / "CLAUDE.md", REPO_ROOT / "AGENTS.md",
                REPO_ROOT / "ARCHITECTURE.md", REPO_ROOT / "docs" / "DEPENDENCIES.md"]
        docs += sorted((REPO_ROOT / "docs" / "modules").glob("*.md"))
        changed = 0
        for doc in docs:
            if not doc.exists():
                continue
            text = doc.read_text(encoding="utf-8")
            stripped, count = LINE_REF_RE.subn(r"\1`", text)
            if count:
                doc.write_text(stripped, encoding="utf-8")
                changed += count
                self.stdout.write(f"  {doc.name}: {count} مرجعاً")
        self.stdout.write(self.style.SUCCESS(f"حُذف {changed} رقم سطر."))
