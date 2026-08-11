"""خلفية كاش ملفّية لا تُسقِط الطلب حين يتعثّر نظام الملفات.

**العطل الذي عالجته** (بلاغ محلي 2026-08-11، `accounting/accounts/` يردّ 500 بـ
`PermissionError: [Errno 13] Permission denied`):

`FileBasedCache._delete` في Django يلتقط `FileNotFoundError` وحدها:

    try:
        os.remove(fname)
    except FileNotFoundError:
        return False

على لينكس هذا يكفي — `unlink` على ملف مفتوح ينجح. **على ويندوز يفشل**: حذف ملف
يمسكه طلبٌ آخر يرمي `PermissionError`، وهو لا يُلتقَط فيصعد إلى المستخدم 500.

ولماذا انكشف الآن تحديداً: بعد P0-7 صار `UserRateThrottle` يقرأ ويكتب عدّاداً في
الكاش عند **كل** طلب API، وشاشة كفواتير المبيعات تُطلق عشرة طلبات متوازية — فيقرأ
أحدها ملفاً منتهي الصلاحية بينما يحذفه الآخر. وقد وثّق التدقيق نفسه (§1.1) أن هذه
الخلفية بلا قفل بين العمليات، فالسباق ليس مفاجأةً بل نتيجةٌ متوقّعة.

**المبدأ:** الكاش مُسرِّع لا مصدر حقيقة. تعثّره يجب أن يعني «إخفاقة كاش» (نعيد
الحساب) لا «سقوط الطلب». وهذا مطابق لما نفعله مع Redis أصلاً
(`IGNORE_EXCEPTIONS: True` في `core/settings.py`) — الخلفية الملفّية كانت الوحيدة
التي تُسقط الطلب، وهذا الملف يسدّ التفاوت.

كل تعثّر يُسجَّل بمستوى `warning` مع اسم العملية: العطل يبقى مرئياً في السجل ولا
يختفي بصمت، لكنه لا يصل المستخدم.
"""
import logging

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.filebased import FileBasedCache

logger = logging.getLogger(__name__)


class ResilientFileBasedCache(FileBasedCache):
    """`FileBasedCache` تتعامل مع أخطاء نظام الملفات كإخفاقة كاش لا كخطأ خادم."""

    def get(self, key, default=None, version=None):
        try:
            return super().get(key, default, version)
        except OSError as exc:
            logger.warning("cache.get failed (treated as miss): %s", exc)
            return default

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            super().set(key, value, timeout, version)
        except OSError as exc:
            # الكتابة الضائعة تعني إعادة حساب لاحقاً — لا شيء يفسد.
            logger.warning("cache.set failed (value not cached): %s", exc)

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            return super().add(key, value, timeout, version)
        except OSError as exc:
            logger.warning("cache.add failed: %s", exc)
            return False

    def touch(self, key, timeout=DEFAULT_TIMEOUT, version=None):
        try:
            return super().touch(key, timeout, version)
        except OSError as exc:
            logger.warning("cache.touch failed: %s", exc)
            return False

    def has_key(self, key, version=None):
        try:
            return super().has_key(key, version)
        except OSError as exc:
            logger.warning("cache.has_key failed (treated as miss): %s", exc)
            return False

    def _delete(self, fname):
        """موضع العطل الأصلي — الحذف المتزامن على ويندوز.

        فشل الحذف غير ضارّ: الملف إما منتهي الصلاحية فيُتجاهَل عند القراءة
        التالية، أو سيحذفه الـcull لاحقاً.
        """
        try:
            return super()._delete(fname)
        except OSError as exc:
            logger.warning("cache._delete failed (entry left behind): %s", exc)
            return False
