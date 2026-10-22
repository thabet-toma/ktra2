"""هويّة `ClientIpScopedThrottle` — وضعان يقرّرهما `DRF_NUM_PROXIES` وحده.

بلا `NUM_PROXIES` يتّخذ DRF **كامل** `X-Forwarded-For` هويّةً، فترويسةٌ يكتبها
العميل تشتري دلواً جديداً في كلّ طلب — أي حدٌّ بلا حدّ. فالهويّة هنا `REMOTE_ADDR`
حصراً، وهي خلف وكيلٍ عكسيٍّ دلوٌ واحدٌ للجميع: تشدّدٌ آمن لا انفلاتٌ صامت.

ومعه (الإنتاج: nginx مفرد ⇒ `DRF_NUM_PROXIES=1`) نفوّض الهويّة إلى DRF الذي
يأخذ العنوان رقم `NUM_PROXIES` من **آخر** الترويسة — أي العنوانَ الذي أضافه
الوكيلُ الأخير، لا أوّلَ ما كتبه العميل. وهذا هو ما يعيد لكلّ موظّفٍ دلوَه
بلا أن يشتري العميلُ دلوَ غيره بترويسة.

`api_settings` يخزّن `REST_FRAMEWORK` عند أوّل قراءة، فـ`override_settings` وحده
لا يبلغه — يُعاد تحميله صراحةً في الاتجاهين.
"""
from contextlib import contextmanager

from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.settings import api_settings

from core.throttles import ClientIpScopedThrottle


@contextmanager
def _num_proxies(value):
    """يضبط `NUM_PROXIES` ثم يعيد تحميل `api_settings` بعد زوال الضبط أيضاً."""
    try:
        with override_settings(REST_FRAMEWORK={"NUM_PROXIES": value}):
            api_settings.reload()
            yield
    finally:
        api_settings.reload()


class ClientIpScopedThrottleIdentityTest(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        api_settings.reload()
        self.addCleanup(api_settings.reload)

    def _ident(self, xff=None, remote="127.0.0.1"):
        extra = {"REMOTE_ADDR": remote}
        if xff is not None:
            extra["HTTP_X_FORWARDED_FOR"] = xff
        request = self.factory.get("/api/share/token/count/", **extra)
        return ClientIpScopedThrottle().get_ident(request)

    def test_without_num_proxies_a_forged_header_does_not_change_the_bucket(self):
        with _num_proxies(None):
            self.assertEqual(self._ident(xff="6.6.6.6"), "127.0.0.1")
            self.assertEqual(self._ident(xff="6.6.6.6, 1.2.3.4"), "127.0.0.1")
            self.assertEqual(self._ident(remote="9.9.9.9"), "9.9.9.9")

    def test_with_one_proxy_the_identity_is_the_last_forwarded_address(self):
        with _num_proxies(1):
            # nginx يضيف عنوان الزائر آخر القائمة؛ وما قبله يكتبه العميل.
            self.assertEqual(
                self._ident(xff="6.6.6.6, 1.2.3.4", remote="127.0.0.1"),
                "1.2.3.4")
            self.assertNotEqual(
                self._ident(xff="5.6.7.8", remote="127.0.0.1"), "1.2.3.4")

    def test_with_one_proxy_and_no_header_the_identity_is_remote_addr(self):
        with _num_proxies(1):
            self.assertEqual(self._ident(remote="127.0.0.1"), "127.0.0.1")
