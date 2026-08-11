"""بلاغ 2026-08-11: `accounting/accounts/` يردّ 500 محلياً بـ
`PermissionError: [Errno 13] Permission denied`.

الجذر ليس في الحسابات ولا في أي نقطة بعينها: `FileBasedCache._delete` في Django
يلتقط `FileNotFoundError` وحدها، وعلى ويندوز حذفُ ملفٍ يمسكه طلبٌ آخر يرمي
`PermissionError` فيصعد إلى المستخدم. وبعد P0-7 صار الـthrottle يلمس الكاش عند
**كل** طلب API، فشاشة تُطلق عشرة طلبات متوازية تكفي لإحداث السباق.

الاختبار يثبّت الحدّين:
  1. الخلفية القياسية **تُسقط** العملية عند تعثّر نظام الملفات (توثيق العطل).
  2. `ResilientFileBasedCache` تحوّله إلى إخفاقة كاش — لا استثناء يصعد.

المحاكاة بـ`os.remove` يرمي `PermissionError` هي نفس ما يحدث على ويندوز حرفياً،
وتعمل على أي منصّة فيبقى الحارس ذا معنى على لينكس أيضاً (CI).
"""
import os
import shutil
import tempfile
from unittest import mock

from django.core.cache.backends.filebased import FileBasedCache
from django.test import SimpleTestCase

from core.cache_backends import ResilientFileBasedCache


def _params():
    return {"OPTIONS": {"MAX_ENTRIES": 100, "CULL_FREQUENCY": 20}}


class CacheResilienceTest(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ktra-cache-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _expired_entry(self, cache, key="throttle_user_7"):
        """يكتب مدخلاً منتهي الصلاحية — القراءة التالية ستحاول حذفه."""
        cache.set(key, ["ts"], 300)
        # مهلة سالبة ⇒ منتهٍ فوراً، فيسلك `_is_expired` مسار الحذف.
        cache.set(key, ["ts"], -1)
        return key

    def test_stock_backend_propagates_filesystem_error(self):
        """توثيق العطل: الخلفية القياسية تُسقط العملية."""
        cache = FileBasedCache(self.tmp, _params())
        key = self._expired_entry(cache)
        with mock.patch(
            "os.remove", side_effect=PermissionError(13, "Permission denied")
        ):
            with self.assertRaises(PermissionError):
                cache.get(key)

    def test_resilient_backend_degrades_to_miss(self):
        """الإصلاح: نفس الظرف يصير إخفاقة كاش بلا استثناء."""
        cache = ResilientFileBasedCache(self.tmp, _params())
        key = self._expired_entry(cache)
        with mock.patch(
            "os.remove", side_effect=PermissionError(13, "Permission denied")
        ):
            self.assertIsNone(cache.get(key))

    def test_resilient_set_survives_filesystem_error(self):
        """كتابة ضائعة تعني إعادة حساب لاحقاً — لا سقوط طلب."""
        cache = ResilientFileBasedCache(self.tmp, _params())
        with mock.patch(
            "tempfile.mkstemp", side_effect=PermissionError(13, "Permission denied")
        ):
            cache.set("k", "v", 60)  # يجب ألا يرمي

    def test_resilient_has_key_and_delete_survive(self):
        cache = ResilientFileBasedCache(self.tmp, _params())
        key = self._expired_entry(cache, "probe")
        with mock.patch(
            "os.remove", side_effect=PermissionError(13, "Permission denied")
        ):
            self.assertFalse(cache.has_key(key))
            self.assertFalse(cache.delete(key))

    def test_normal_operation_is_unchanged(self):
        """السلوك السليم يبقى سليماً — لا نبتلع إلا أخطاء نظام الملفات."""
        cache = ResilientFileBasedCache(self.tmp, _params())
        cache.set("alpha", {"n": 1}, 60)
        self.assertEqual(cache.get("alpha"), {"n": 1})
        self.assertTrue(cache.has_key("alpha"))
        self.assertTrue(cache.delete("alpha"))
        self.assertIsNone(cache.get("alpha"))
        self.assertFalse(os.path.exists(cache._key_to_file("alpha")))
