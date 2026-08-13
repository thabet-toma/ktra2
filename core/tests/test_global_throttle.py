"""المرحلة 5 / P0-7: حدّ معدّل عام على كل الـAPI — لا على accountant_portal وحده.

قبل هذا البند كان `DEFAULT_THROTTLE_CLASSES` مقتصراً على `ScopedRateThrottle`،
وهو لا يعترض إلا الـviews التي تعرّف `throttle_scope` (6 نقاط في
accountant_portal). كل مسارات ERP الفعلية كانت بلا أي سقف
(`docs/SCALABILITY_AUDIT.md` §1.6).

الاختبار يشدّ المعدّل إلى قيمة صغيرة ويتحقّق أن الطلب الزائد يُردّ بـ429.
ملاحظة: `core.test_settings` يستخدم DummyCache (لا يخزّن شيئاً) فعدّادات
الـthrottle لا تتراكم — لذلك يفرض هذا الملف LocMemCache صراحةً، وإلا لمرّ
الاختبار حتى لو لم يكن الحدّ مركّباً أصلاً.
"""
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from tenants.services import create_company

CATALOG_URL = "/api/reports/"
# نقطة `AllowAny`. اختيارها مقصود: DRF ينفّذ check_permissions **قبل**
# check_throttles، فطلبٌ مجهول على نقطة تتطلب مصادقة يُردّ 401 ولا يصل الـthrottle
# أصلاً — قياس AnonRateThrottle عليها كان سيقيس شيئاً آخر.
#
# ST-1 (2026-08-13): لم تعد `CurrencyViewSet` النقطةَ العامة الوحيدة — نقاط
# المتجر الثلاث في `store/views.py` عامة كذلك. تُقاس هنا العملاتُ عمداً: نقاط
# المتجر تحمل `throttle_scope = "store_public"` فوق `anon`، فقياسُ سلة `anon`
# عليها كان سيخلط الحدَّين. سقفُ المتجر نفسه محروسٌ في `store/tests/`.
PUBLIC_URL = "/api/accounting/currencies/"

_LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _rates(**overrides):
    """يشدّ المعدّلات مؤقتاً — بـpatch على `THROTTLE_RATES` لا بـ`override_settings`.

    `SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES`
    سمة صنف تُقيَّم مرة واحدة عند استيراد `rest_framework.throttling`، فتعديل
    `settings.REST_FRAMEWORK` بعد الإقلاع لا يصلها (حتى مع `api_settings.reload()`
    الذي يمسح الكاش الداخلي وحده). القيم الإنتاجية تُقرأ من الإعدادات عند
    الإقلاع كالمعتاد — هذا قيد اختبارٍ لا قيد تشغيل.
    """
    return mock.patch.dict(
        SimpleRateThrottle.THROTTLE_RATES, overrides, clear=False,
    )


class GlobalThrottleTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="throttled", password="x")
        cls.token = Token.objects.create(user=cls.user)
        cls.tenant = create_company("شركة الحدّ المعدّل", cls.user)

    def setUp(self):
        cache.clear()  # عدّادات الـthrottle لا تتسرّب بين الاختبارات
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    @override_settings(CACHES=_LOCMEM)
    def test_authenticated_user_is_throttled_past_the_rate(self):
        """المستخدم المصادَق يُحدّ عند تجاوز `user` rate — 429 لا 200."""
        with _rates(user="3/min"):
            statuses = [
                self.client.get(CATALOG_URL, **self._headers()).status_code
                for _ in range(4)
            ]
        self.assertEqual(statuses[:3], [200, 200, 200], statuses)
        self.assertEqual(statuses[3], 429, statuses)

    @override_settings(CACHES=_LOCMEM)
    def test_anonymous_traffic_is_throttled_on_public_endpoint(self):
        """المجهول له سقفه المنفصل على النقاط العامة (`AllowAny`)."""
        anon = APIClient()
        with _rates(anon="2/min"):
            statuses = [anon.get(PUBLIC_URL).status_code for _ in range(3)]
        self.assertEqual(statuses[:2], [200, 200], statuses)
        self.assertEqual(statuses[2], 429, statuses)

    @override_settings(CACHES=_LOCMEM)
    def test_anonymous_hit_on_protected_endpoint_is_rejected_before_throttling(self):
        """توثيق حدّ المعالجة: الصلاحية تسبق الـthrottle في DRF.

        `APIView.initial` ينفّذ perform_authentication ← check_permissions ←
        check_throttles، فالطلب المجهول على نقطة تتطلب مصادقة يُردّ 401 ولا
        يُحتسَب في عدّاد AnonRateThrottle إطلاقاً. يعني: `anon` يحمي النقاط
        العامة وحدها، وأي حماية لتخمين كلمات المرور تحتاج حدّاً خاصاً على
        نقطة الدخول نفسها (مسجَّلة كثغرة جديدة في SCALABILITY_AUDIT).
        """
        anon = APIClient()
        with _rates(anon="1/min"):
            statuses = [anon.get(CATALOG_URL).status_code for _ in range(3)]
        self.assertEqual(statuses, [401, 401, 401], statuses)

    @override_settings(CACHES=_LOCMEM)
    def test_rate_is_per_user_not_global(self):
        """سقف مستخدم مستنفَد لا يمنع مستخدماً آخر — الحدّ عزلٌ لا قاطع خدمة."""
        other = User.objects.create_user(username="throttled2", password="x")
        other_token = Token.objects.create(user=other)
        other_tenant = create_company("شركة ثانية للحدّ", other)
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=f"Token {other_token.key}")

        with _rates(user="2/min"):
            for _ in range(3):
                self.client.get(CATALOG_URL, **self._headers())
            res = other_client.get(
                CATALOG_URL, HTTP_X_TENANT_ID=str(other_tenant.TenantID))
        self.assertEqual(res.status_code, 200, res.content[:300])
