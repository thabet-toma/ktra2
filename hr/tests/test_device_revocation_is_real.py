"""حارسُ الإبطال الحقيقيّ لأجهزة الدخول (ISSUE #168).

الحقيقةُ الوحيدةُ المهمّةُ في هذه الميزة أنّ **مفتاحاً يعمل أو لا يعمل**. وهذه
الاختباراتُ تضرب نقطةً محميّةً عاديّةً بالمفتاح بعد إبطاله وتتوقّع رفضاً — لا
تفحص صنفَ المصادقة ولا تعدّ النداءات، فإعادةُ كتابته بالكامل يجب ألّا تكسر
واحداً منها ما دام السلوكُ ثابتاً.

**لماذا هذا الملفّ موجود:** الهجرةُ الصامتة تترك صفَّ `authtoken_token` قائماً
بنفس قيمة المفتاح إلى جانب صفّ الجهاز الجديد — وهي حالةُ **كلِّ مستخدمٍ قائمٍ
يوم النشر**. فإن قَبِل أيُّ مسارٍ مصادقةً بالرجوع إلى جدول التوكن القديم، صار
ذلك الصفُّ مفتاحاً هيكليّاً يُحيي جهازاً أُبطل: يخرج المستخدمُ فلا يخرج، ويُخرج
جهازاً فيعود. وهو عينُ العطب الذي وُلدت الميزةُ لإصلاحه، عائداً بشكلٍ آخر.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from hr.models import UserDevice

pytestmark = pytest.mark.django_db


#: نقطةٌ محميّةٌ عاديّة — شاهدةٌ على أنّ المفتاح مات فعلاً، لا على حالة القاعدة.
PROTECTED_URL = "/api/hr/tasks/"


def _migrated_user():
    """مستخدمٌ كما يتركه النشر: صفُّ توكنٍ قديم وصفُّ جهازٍ بنفس المفتاح."""
    user = User.objects.create_user(username="legacy_user", password="pw12345678")
    token = Token.objects.create(user=user)
    device, _ = UserDevice.objects.get_or_create(
        key=token.key,
        defaults={"user": user, "device_name": "جهازٌ غير معروف"},
    )
    return user, token, device


def _client(key):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Token {key}")
    return c


def test_logout_actually_revokes_a_migrated_key():
    """الخروجُ العاديُّ يُبطل المفتاح ولو بقي صفُّ التوكن القديم في القاعدة."""
    user, token, device = _migrated_user()
    key = token.key

    assert _client(key).get(PROTECTED_URL).status_code != 401, (
        "المفتاح يجب أن يعمل قبل الخروج — وإلا فالاختبار لا يقيس شيئاً."
    )

    assert _client(key).post("/api/hr/auth/logout/").status_code == 200

    assert _client(key).get(PROTECTED_URL).status_code == 401, (
        "المفتاح ما زال يعمل بعد الخروج — صفُّ التوكن القديم أحيا الجهازَ المحذوف."
    )


def test_evicting_a_migrated_device_actually_revokes_it():
    """إخراجُ جهازٍ مهاجَرٍ يُبطل مفتاحَه ولا يُحييه صفُّ التوكن القديم."""
    user, token, device = _migrated_user()
    key = token.key

    # جهازٌ ثانٍ يبقى حيّاً — ومنه يقع الإخراج.
    other = UserDevice.objects.create(user=user, device_name="جهازٌ آخر")

    resp = _client(other.key).post(f"/api/hr/auth/devices/{device.pk}/evict/")
    assert resp.status_code == 200, resp.content

    assert _client(key).get(PROTECTED_URL).status_code == 401, (
        "المفتاح المُخرَج ما زال يعمل — الإخراجُ لم يُبطل شيئاً."
    )
    assert _client(other.key).get(PROTECTED_URL).status_code != 401, (
        "إخراجُ جهازٍ أسقط الجهازَ الباقي — الإبطالُ يجب أن يكون لجهازه وحدَه."
    )


def test_a_bare_legacy_token_row_is_not_a_credential():
    """صفُّ توكنٍ بلا جهازٍ مقابلٍ لا يفتح شيئاً — جدولُ الأجهزة وحدَه مصدرُ الحقيقة."""
    user = User.objects.create_user(username="orphan_token_user", password="pw12345678")
    token = Token.objects.create(user=user)
    UserDevice.objects.filter(key=token.key).delete()

    assert _client(token.key).get(PROTECTED_URL).status_code == 401, (
        "توكنٌ قديمٌ بلا صفِّ جهازٍ ما زال يُصادِق — فالمفتاحُ الهيكليُّ حيّ."
    )
