"""حرّاسُ الـthrottle — الفخُّ الصامت: اختبارُ حدٍّ معدّلٍ يمرّ أخضر وهو لا يحرس شيئاً.

`core/test_settings.py` يضبط الكاش على `DummyCache` عمداً (عزلُ الاختبارات عن
بعضها)، و`SimpleRateThrottle` يعدّ في الكاش — فالعدّاد لا يتراكم أبداً تحت
الاختبارات، و«أرسلتُ ١١ طلباً فجاء 429» **لا يمكنه السقوط** إن نُسي فرضُ كاشٍ
حقيقيّ في الملف. الاختبارُ يمرّ، والحارسُ في الإنتاج قد يكون معطوباً.

ثلاثةُ حرّاس هنا:
  1. `DummyCache` يبقى الافتراضَ في `core/test_settings` — قلبُه صامتاً يجعل
     اختباراتٍ تتسرّب إلى بعضها عبر الكاش.
  2. كلُّ `throttle_scope` (أو `scope` على صنف throttle) له معدّلٌ معرَّف:
     اسمٌ مطبعيٌّ واحد ⇒ `ImproperlyConfigured` عند أول طلبٍ في الإنتاج،
     ولا اختبارَ يمسكه لأنّ النقطة قد لا تُطرَق في المجموعة أصلاً.
  3. كلُّ ملفِ اختبارٍ يؤكّد ردّاً بـ429 يفرض كاشاً حقيقيّة (`LocMemCache`).
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parent.parent.parent
_SKIP_DIR = ("venv", "worktrees", "node_modules", "site-packages", "migrations")
# ردُّ HTTP بـ429 — لا رقمَ 429 داخل مبلغٍ أو ردِّ خدمةٍ خارجيّةٍ مُحاكاة.
_RESPONSE_429 = re.compile(
    r"HTTP_429|status_code\s*(==|,)\s*429|status_code\s*!=\s*429")
_SCOPE = re.compile(r"^\s*(?:throttle_)?scope\s*=\s*[\"']([\w-]+)[\"']", re.M)


def _production_sources():
    for path in REPO.rglob("*.py"):
        parts = str(path)
        if any(skip in parts for skip in _SKIP_DIR) or "tests" in path.parts:
            continue
        yield path


def _test_sources():
    for path in REPO.rglob("*.py"):
        if any(skip in str(path) for skip in _SKIP_DIR):
            continue
        if "tests" in path.parts:
            yield path


class ThrottleGuardTest(SimpleTestCase):
    def test_test_settings_keep_dummy_cache(self):
        """قلبُ الافتراض إلى كاشٍ حقيقيّة يجعل الاختبارات تتسرّب عبر الكاش."""
        backend = settings.CACHES["default"]["BACKEND"]
        self.assertEqual(
            backend, "django.core.cache.backends.dummy.DummyCache",
            "الافتراضُ في الاختبارات DummyCache؛ الملفُّ الذي يلزمه كاشٌ حقيقيّة "
            "يفرضها بـ@override_settings(CACHES=...LocMemCache) لنفسه وحده.",
        )

    def test_every_declared_throttle_scope_has_a_rate(self):
        rates = set(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"])
        declared = {}
        for path in _production_sources():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "Throttle" not in text and "throttle_scope" not in text:
                continue
            for scope in _SCOPE.findall(text):
                declared.setdefault(scope, set()).add(str(path.relative_to(REPO)))
        self.assertTrue(declared, "لم يُعثر على أيّ throttle_scope — تعطّل الماسح.")
        missing = {s: sorted(f) for s, f in declared.items() if s not in rates}
        self.assertEqual(
            missing, {},
            "نطاقٌ بلا معدّل في DEFAULT_THROTTLE_RATES ⇒ ImproperlyConfigured عند "
            f"أوّل طلبٍ على النقطة: {missing}",
        )

    def test_tests_asserting_429_force_a_real_cache(self):
        offenders = []
        for path in _test_sources():
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _RESPONSE_429.search(text) and "LocMemCache" not in text:
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(
            offenders, [],
            "ملفٌّ يؤكّد ردّ 429 وكاشُه DummyCache: العدّادُ لا يتراكم فالتأكيدُ لا "
            "يستطيع السقوطَ للسبب الذي يحمله اسمُه. افرض LocMemCache في الملف "
            f"(سابقة: core/tests/test_global_throttle.py): {offenders}",
        )
