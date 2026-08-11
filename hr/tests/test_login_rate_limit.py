"""المرحلة 5 / P0-13: حدّ محاولات الدخول على ‎/api/hr/auth/login/‎.

النقطة دالة Django عادية (لا DRF) فكانت خارج سلسلة الـthrottle كلياً
(`SCALABILITY_AUDIT.md` §1.7): تخمين كلمات مرور بلا سقف، وكل محاولة تجزئة
PBKDF2 مقصودة البطء. الحدّ يعدّ **المحاولات الفاشلة** بمفتاحي بريد وIP،
والفحص يسبق check_password.

ملاحظة الكاش: `core.test_settings` على DummyCache (لا يخزّن) فالعدّادات لا
تتراكم — الاختبارات تفرض LocMemCache، وإلا مرّت خضراء بلا حدٍّ مركّب أصلاً.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings

from hr.auth_api import LOGIN_MAX_FAILURES

LOGIN_URL = "/api/hr/auth/login/"

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(
    CACHES=_LOCMEM,
    # ‏~30 محاولة دخول في هذه الحزمة — PBKDF2 الإنتاجي يجعلها ~27ث؛ المُجزّئ
    # السريع يخصّ الاختبار ولا يغيّر ما يُختبر (منطق العدّ لا التجزئة).
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class LoginRateLimitTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="limited@x.com", email="limited@x.com", password="correct-horse")

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _attempt(self, email="limited@x.com", password="wrong", ip="10.0.0.9"):
        return self.client.post(
            LOGIN_URL, {"email": email, "password": password},
            content_type="application/json", REMOTE_ADDR=ip,
        )

    def test_failures_past_limit_return_429_before_password_check(self):
        for _ in range(LOGIN_MAX_FAILURES):
            self.assertEqual(self._attempt().status_code, 401)
        res = self._attempt()
        self.assertEqual(res.status_code, 429, res.content[:200])
        self.assertEqual(res.json()["code"], "RATE_LIMITED")
        self.assertIn("Retry-After", res)
        # وحتى كلمة المرور الصحيحة تُرفض ما دام القفل قائماً — الفحص يسبق
        # check_password فلا يُستهلك CPU على تجزئة لطلب محظور.
        self.assertEqual(self._attempt(password="correct-horse").status_code, 429)

    def test_successful_login_resets_the_counter(self):
        for _ in range(LOGIN_MAX_FAILURES - 1):
            self._attempt()
        self.assertEqual(self._attempt(password="correct-horse").status_code, 200)
        # بعد النجاح: الحصة عادت كاملة — فشل واحد جديد لا يقفل
        self.assertEqual(self._attempt().status_code, 401)

    def test_email_lock_follows_the_account_across_ips(self):
        """قفل البريد يتبع الحساب لا المصدر — تبديل الـIP لا يفتح الحساب."""
        for i in range(LOGIN_MAX_FAILURES):
            self._attempt(ip=f"10.0.1.{i}")
        res = self._attempt(ip="10.0.2.99")
        self.assertEqual(res.status_code, 429)

    def test_ip_lock_does_not_leak_to_other_accounts_from_other_ips(self):
        """حساب آخر من IP آخر لا يتأثر بقفل الأول — الحدّ عزل لا قاطع خدمة."""
        User.objects.create_user(
            username="other@x.com", email="other@x.com", password="pw-other")
        for _ in range(LOGIN_MAX_FAILURES):
            self._attempt()
        res = self._attempt(email="other@x.com", password="pw-other", ip="10.9.9.9")
        self.assertEqual(res.status_code, 200, res.content[:200])
