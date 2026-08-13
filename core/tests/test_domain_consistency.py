"""حارس اتّساق الدومين — يمنع نصف المشروع من البقاء على عنوان ميّت بصمت.

**لماذا يوجد هذا الملف:** تغيّر دومين الإنتاج إلى `ktra-pro.tech`، وبقي 26 ملفاً
متتبَّعاً يحمل الاسم القديم `smart.ktragroup.com` — **والمجموعة كانت خضراء طوال
ذلك**. لا شيء كان يربط «الدومين الحيّ» بما هو مكتوب في الملفّات، فبقي الفارق
غير مرئي حتى قرأه إنسان.

والثمن ليس تجميلياً. الاسم القديم **يُحلّ إلى خادم لا يخصّ المشروع**
(‏`173.208.138.113`)، وكان مكتوباً في:

- `frontend_v2/index.html`: وسم `canonical` يقول لجوجل إن العنوان الحقيقي لهذه
  الصفحة على ذلك الخادم — وجوجل يقدّم `canonical` على `sitemap.xml` عند التعارض،
  فتصحيح الـsitemap وحده كان يُبطله سطر واحد.
- `og:image` / `twitter:image`: صورة معاينة كل رابط يُشارَك على واتساب وفيسبوك.
- `core/settings.py`: `ALLOWED_HOSTS` و`CORS`/`CSRF` — إعدادُ أمانٍ يصف ماضياً.

**نطاق الحارس — التاريخ مستثنى عمداً:** `docs/history/` و`docs/CHANGELOG.md`
و`task9.md` تصف **ما حدث** لا ما هو قائم، وإعادة كتابتها تزوير لا صيانة. كذلك
`migrations/` — تتجمّد على لحظتها بحكم طبيعتها.

**مُعمَّم لا مخصَّص:** `RETIRED_DOMAINS` قائمة، فأي تغيير دومين لاحق يضيف سطراً
هنا ويرث الحراسة كاملة بدل أن يعيد اكتشاف نفس العطل. السابقة في هذا المشروع:
`core/tests/test_docs_freshness.py` يحرس طزاجة الوثائق بنفس المنطق.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: دومين الإنتاج الحيّ — المرجع الذي يُقاس عليه كل ما سواه.
LIVE_DOMAIN = "ktra-pro.tech"

#: دومينات متقاعدة. الاسم وحده يكفي (لا نثبّت النطاق الفرعي) كي يُلتقط
#: `smart.ktragroup.com` و`api.smart.ktragroup.com` و`noor.smart.ktragroup.com` معاً.
RETIRED_DOMAINS = (
    "ktragroup",
    "ktraerp.servebeer.com",
)

#: امتدادات نصّية تُفحَص داخل `frontend_v2/public/` (لا صور ولا خطوط).
PUBLIC_TEXT_SUFFIXES = {".txt", ".xml", ".json", ".webmanifest", ".html", ".svg"}

#: مسارات مستثناة — كلٌّ بسببه. الإعفاء قرار معلَن لا سهو.
EXEMPTIONS = {
    "docs/history": "سجلّ تاريخي يصف الماضي — إعادة كتابته تزوير",
    "docs/CHANGELOG.md": "يوثّق ما حدث، لا ما هو قائم",
    "task9.md": "مستند تدقيق مؤرَّخ — نصّه المصدر نفسه",
    "core/tests/test_domain_consistency.py": "الحارس نفسه — لا يُمنع من تسمية ما يمنعه",
}

#: مجلدات لا تُفحَص إطلاقاً: مولَّدة أو غير متتبَّعة أو خارج المشروع.
PRUNED_DIRS = {
    "node_modules", "dist", "dist-ssr", "venv", ".venv", "__pycache__",
    ".git", ".claude", ".multica", ".agent_context", ".pytest_cache",
    "migrations", "test-results", ".clone", "playwright-report",
}


def _is_exempt(rel: str) -> bool:
    return any(rel == e or rel.startswith(f"{e}/") for e in EXEMPTIONS)


def _walk(root: Path, suffixes):
    """يمشي في شجرة مع تقليم `PRUNED_DIRS` — أرخص من rglob ثم الفلترة."""
    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if entry.name in PRUNED_DIRS:
            continue
        if entry.is_dir():
            yield from _walk(entry, suffixes)
        elif entry.suffix in suffixes:
            yield entry


def _delivered_files():
    """كل ملف يصل المستخدم أو يضبط سلوك الإنتاج.

    القائمة صريحة عمداً: حارسٌ يفحص كل شيء يلتقط ضجيجاً فيُعطَّل بعد شهر.
    """
    files = [REPO_ROOT / "frontend_v2" / "index.html", REPO_ROOT / "ARCHITECTURE.md"]
    files += _walk(REPO_ROOT / "frontend_v2" / "public", PUBLIC_TEXT_SUFFIXES)
    files += _walk(REPO_ROOT / "frontend_v2", {".ts", ".tsx"})
    files += _walk(REPO_ROOT / "core", {".py"})
    files += _walk(REPO_ROOT / "docs" / "modules", {".md"})
    seen, unique = set(), []
    for path in files:
        if path.exists() and path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


class DomainConsistencyTest(SimpleTestCase):
    """كل إخفاق هنا يعني: عنوانٌ مُسلَّم يشير إلى خادم لا يخصّ المشروع."""

    def test_no_retired_domain_in_delivered_files(self):
        pattern = re.compile("|".join(re.escape(d) for d in RETIRED_DOMAINS))
        offenders = []
        for path in _delivered_files():
            rel = path.relative_to(REPO_ROOT).as_posix()
            if _is_exempt(rel):
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if pattern.search(line):
                    offenders.append(f"{rel}:{number} → {line.strip()[:90]}")
        self.assertEqual(
            offenders, [],
            "هذه الملفات تحمل دوميناً متقاعداً يُحلّ إلى خادم خارج المشروع، فتُوجَّه\n"
            f"إليه محركات البحث ومعاينات المشاركة. الدومين الحيّ هو {LIVE_DOMAIN}:\n  "
            + "\n  ".join(offenders),
        )

    def test_public_seo_tags_point_at_the_live_domain(self):
        """`canonical` و`og:url` و`og:image` — أخطر خمسة أسطر في المشروع للفهرسة.

        فحصٌ إيجابي لا سلبي: غياب الاسم القديم لا يثبت وجود الجديد (حذفُ الوسم
        يُرضي الاختبار الأول ويُسكت جوجل عن الأصل الصحيح).
        """
        html = (REPO_ROOT / "frontend_v2" / "index.html").read_text(encoding="utf-8")
        required = [
            (r'<link rel="canonical" href="https://%s/?"' % re.escape(LIVE_DOMAIN), "canonical"),
            (r'property="og:url" content="https://%s' % re.escape(LIVE_DOMAIN), "og:url"),
            (r'property="og:image" content="https://%s' % re.escape(LIVE_DOMAIN), "og:image"),
            (r'name="twitter:image" content="https://%s' % re.escape(LIVE_DOMAIN), "twitter:image"),
            (r'"url":\s*"https://%s' % re.escape(LIVE_DOMAIN), "JSON-LD url"),
        ]
        missing = [name for pattern, name in required if not re.search(pattern, html)]
        self.assertEqual(
            missing, [],
            f"وسوم عامة لا تشير إلى {LIVE_DOMAIN} في frontend_v2/index.html: "
            + "، ".join(missing),
        )

    def test_sitemap_and_robots_announce_the_live_domain(self):
        public = REPO_ROOT / "frontend_v2" / "public"
        sitemap = (public / "sitemap.xml").read_text(encoding="utf-8")
        robots = (public / "robots.txt").read_text(encoding="utf-8")
        self.assertIn(f"<loc>https://{LIVE_DOMAIN}/", sitemap)
        self.assertIn(f"Sitemap: https://{LIVE_DOMAIN}/sitemap.xml", robots)

    def test_exemptions_are_real_paths(self):
        """إعفاء لمسار محذوف = قائمة تتعفّن هي الأخرى."""
        stale = sorted(e for e in EXEMPTIONS if not (REPO_ROOT / e).exists())
        self.assertEqual(stale, [], f"إعفاءات لمسارات غير موجودة: {stale}")
