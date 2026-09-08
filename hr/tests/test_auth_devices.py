"""
اختبارات شاملة لنظام أجهزة الدخول (GitHub #168 — م١ + م٢ + م٣).

القواعد المفروضة:
1. مفتاح مصادقة مستقل لكل جهاز دخول (Two logins => two different keys).
2. إنهاء جهاز يرفض مفتاحه ويبقي المفتاح الآخر صالحاً.
3. تسجيل الخروج العادي ينهي الجهاز الحالي فقط.
4. حارس الجهاز الأساسي: الأجهزة الثانوية تُرفض من العرض والإنهاء برسالة تفسيرية عربية.
5. تعيين الجهاز الأساسي بكلمة المرور الصحيحة ينقل الصفة ويفرغ الأساسي السابق، ومع الخطأ يُرفض.
6. تغيير كلمة المرور ينهي جميع الأجهزة الأخرى ويبقي الجهاز الحالي.
7. هجرة البيانات الصامتة: المفاتيح القديمة تستمر في العمل 100% بعد الهجرة دون رفض أي طلب.
8. تحديث last_active_at لا يكتب مرتين داخل نافذة الـ 5 دقائق.
9. عزل تام: لا يمكن لأي نقطة قراءة أو تعديل أجهزة مستخدم آخر حتى بتمرير معرّفه.
"""
import importlib
from datetime import timedelta
from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from hr.models import UserDevice
from hr.device_utils import derive_device_name

migration_0010 = importlib.import_module("hr.migrations.0010_migrate_tokens_to_user_devices")
migrate_existing_tokens_to_devices = migration_0010.migrate_existing_tokens_to_devices


class UserDeviceAuthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_a = User.objects.create_user(
            username="user_a@ktra.test",
            email="user_a@ktra.test",
            password="password_a_123",
            first_name="أحمد",
            last_name="علي",
        )
        cls.user_b = User.objects.create_user(
            username="user_b@ktra.test",
            email="user_b@ktra.test",
            password="password_b_123",
            first_name="سالم",
            last_name="خالد",
        )

    def _login(self, email="user_a@ktra.test", password="password_a_123", ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"):
        res = self.client.post(
            "/api/hr/auth/login/",
            {"email": email, "password": password},
            content_type="application/json",
            HTTP_USER_AGENT=ua,
            REMOTE_ADDR="192.168.1.10",
        )
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()["token"]

    def _witness(self, user, token_key):
        """نقطة مراقبة واقعية عبر طبقة HTTP للتأكد من صلاحية المفتاح."""
        return self.client.get(
            f"/api/hr/users/{user.pk}/",
            HTTP_AUTHORIZATION=f"Token {token_key}",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 1. اختبار الهجرة الصامتة وحفظ المفاتيح السابقة
    # ──────────────────────────────────────────────────────────────────────────
    def test_migration_existing_token_still_works_after_upgrade(self):
        """
        مفتاح كان موجوداً قبل الترقية في authtoken_token يستمر في العمل
        بنجاح بعد تطبيق هجرة البيانات الصامتة.
        """
        legacy_key = "legacy_secret_key_abcdef1234567890123456"
        # محاكاة حالة قاعدة البيانات قبل الهجرة 0010: التوكن موجود في authtoken
        token = Token.objects.create(user=self.user_a, key=legacy_key)
        # لا صفَّ جهازٍ بعد — هذه حالُ القاعدة قبل الهجرة 0010 حرفياً.
        UserDevice.objects.filter(key=legacy_key).delete()
        self.assertFalse(UserDevice.objects.filter(key=legacy_key).exists())

        # تشغيل دالة الهجرة الصامتة 0010
        migrate_existing_tokens_to_devices(apps, None)

        # التحقق من نسخ المفتاح لجدول UserDevice بنفس القيمة والبيانات المطلوبة
        migrated = UserDevice.objects.filter(key=legacy_key).first()
        self.assertIsNotNone(migrated)
        self.assertEqual(migrated.user, self.user_a)
        self.assertEqual(migrated.device_name, "جهازٌ غير معروف")
        self.assertEqual(migrated.user_agent, "")
        self.assertFalse(migrated.is_primary)

        # الشاهد الحقيقي: إرسال طلب HTTP حقيقي للمصادقة بالمفتاح المهاجر
        res = self._witness(self.user_a, legacy_key)
        self.assertEqual(res.status_code, 200, res.content)

        # الصف القديم ما زال موجوداً في authtoken_token (غير مدمر)
        self.assertTrue(Token.objects.filter(key=legacy_key).exists())

    # ──────────────────────────────────────────────────────────────────────────
    # 2. تسجيل دخول مرتين = مفتاحان مختلفان
    # ──────────────────────────────────────────────────────────────────────────
    def test_two_logins_create_two_different_keys(self):
        """تسجيل دخولين لنفس المستخدم ينتج مفتاحي جهاز مختلفين تماماً."""
        token_1 = self._login()
        token_2 = self._login()

        self.assertNotEqual(token_1, token_2)
        devices = UserDevice.objects.filter(user=self.user_a)
        self.assertEqual(devices.count(), 2)
        keys = set(devices.values_list("key", flat=True))
        self.assertIn(token_1, keys)
        self.assertIn(token_2, keys)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. إنهاء جهاز يرفض مفتاحه ويبقي الآخر
    # ──────────────────────────────────────────────────────────────────────────
    def test_evict_device_rejects_evicted_key_and_preserves_surviving_key(self):
        """إنهاء جهاز يبطل مفتاحه فقط والمفتاح الناجي يواصل العمل بنجاح."""
        tok_1 = self._login()
        tok_2 = self._login()

        # كلاهما صالح قبل الإنهاء
        self.assertEqual(self._witness(self.user_a, tok_1).status_code, 200)
        self.assertEqual(self._witness(self.user_a, tok_2).status_code, 200)

        # الجهاز 1 يستعرض الأجهزة ويطلب إنهاء الجهاز 2
        dev_2 = UserDevice.objects.get(key=tok_2)
        res = self.client.post(
            f"/api/hr/auth/devices/{dev_2.id}/evict/",
            HTTP_AUTHORIZATION=f"Token {tok_1}",
        )
        self.assertEqual(res.status_code, 200, res.content)

        # الجهاز 2 صار مرفوضاً بـ 401
        self.assertEqual(self._witness(self.user_a, tok_2).status_code, 401)
        # الجهاز 1 ما زال صالحاً بـ 200
        self.assertEqual(self._witness(self.user_a, tok_1).status_code, 200)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. تسجيل الخروج العادي ينهي جهازه فقط
    # ──────────────────────────────────────────────────────────────────────────
    def test_ordinary_logout_does_not_evict_other_device(self):
        """تسجيل الخروج من جهاز لا ينهي الجهاز الآخر (إصلاح الخلل المبلغ عنه)."""
        tok_1 = self._login()
        tok_2 = self._login()

        # خروج من الجهاز 2
        res = self.client.post(
            "/api/hr/auth/logout/",
            HTTP_AUTHORIZATION=f"Token {tok_2}",
        )
        self.assertEqual(res.status_code, 200)

        # الجهاز 2 صار ملغياً
        self.assertEqual(self._witness(self.user_a, tok_2).status_code, 401)
        # الجهاز 1 مستمر في العمل بنجاح
        self.assertEqual(self._witness(self.user_a, tok_1).status_code, 200)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. حارس الجهاز الأساسي: الجهاز الثانوي يُرفض برسالة توضيحية
    # ──────────────────────────────────────────────────────────────────────────
    def test_secondary_device_rejected_with_arabic_explanation(self):
        """الجهاز الثانوي يُرفض من العرض والإنهاء عند وجود جهاز أساسي."""
        tok_1 = self._login()
        tok_2 = self._login()

        # الجهاز 1 يعيّن نفسه أساسياً
        res = self.client.post(
            "/api/hr/auth/devices/set-primary/",
            {"password": "password_a_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok_1}",
        )
        self.assertEqual(res.status_code, 200)

        dev_1 = UserDevice.objects.get(key=tok_1)
        self.assertTrue(dev_1.is_primary)

        # الجهاز 2 يحاول عرض الأجهزة => 403 مع اسم الجهاز الأساسي
        res_list = self.client.get(
            "/api/hr/auth/devices/",
            HTTP_AUTHORIZATION=f"Token {tok_2}",
        )
        self.assertEqual(res_list.status_code, 403)
        body = res_list.json()
        self.assertEqual(body["code"], "PRIMARY_DEVICE_REQUIRED")
        self.assertIn("الإدارةُ من الجهاز الأساسيّ", body["detail"])
        self.assertIn(dev_1.display_name, body["detail"])

        # الجهاز 2 يحاول إنهاء الأجهزة الأخرى => 403
        res_evict = self.client.post(
            "/api/hr/auth/devices/evict-others/",
            HTTP_AUTHORIZATION=f"Token {tok_2}",
        )
        self.assertEqual(res_evict.status_code, 403)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. تعيين الأساسي: خطأ كلمة المرور يُرفض، والصحيح ينقل الأساسي ويلغي السابق
    # ──────────────────────────────────────────────────────────────────────────
    def test_set_primary_wrong_password_rejected_and_correct_moves_primary(self):
        """تعيين الجهاز الأساسي يتطلب كلمة مرور ويفرغ الأساسي السابق."""
        tok_1 = self._login()
        tok_2 = self._login()

        # جهاز 1 يصبح أساسياً
        self.client.post(
            "/api/hr/auth/devices/set-primary/",
            {"password": "password_a_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok_1}",
        )
        dev_1 = UserDevice.objects.get(key=tok_1)
        self.assertTrue(dev_1.is_primary)

        # جهاز 2 يحاول التعيين بكلمة مرور خاطئة => 400
        res_fail = self.client.post(
            "/api/hr/auth/devices/set-primary/",
            {"password": "wrong_password"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok_2}",
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertEqual(res_fail.json()["code"], "INVALID_PASSWORD")
        dev_1.refresh_from_db()
        self.assertTrue(dev_1.is_primary)

        # جهاز 2 يعيّن بكلمة مرور صحيحة => 200
        res_ok = self.client.post(
            "/api/hr/auth/devices/set-primary/",
            {"password": "password_a_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok_2}",
        )
        self.assertEqual(res_ok.status_code, 200)

        dev_1.refresh_from_db()
        dev_2 = UserDevice.objects.get(key=tok_2)
        self.assertFalse(dev_1.is_primary)
        self.assertTrue(dev_2.is_primary)

    # ──────────────────────────────────────────────────────────────────────────
    # 7. تغيير كلمة المرور يُنهي الأجهزة الأخرى ويُبقي الحالي
    # ──────────────────────────────────────────────────────────────────────────
    def test_change_password_evicts_others_and_current_lives(self):
        """تغيير كلمة المرور ينهي كل الأجهزة الأخرى ويبقي الجهاز الحالي."""
        tok_1 = self._login()
        tok_2 = self._login()
        tok_3 = self._login()

        # الجهاز 1 يغيّر كلمة المرور
        res = self.client.post(
            "/api/hr/auth/change-password/",
            {"oldPassword": "password_a_123", "newPassword": "new_secret_pass_789"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok_1}",
        )
        self.assertEqual(res.status_code, 200, res.content)

        # الجهاز 2 و 3 ماتا
        self.assertEqual(self._witness(self.user_a, tok_2).status_code, 401)
        self.assertEqual(self._witness(self.user_a, tok_3).status_code, 401)

        # الجهاز 1 حيّ ويعمل
        self.assertEqual(self._witness(self.user_a, tok_1).status_code, 200)

    # ──────────────────────────────────────────────────────────────────────────
    # 8. last_active لا يُكتب مرتين داخل نافذة 5 دقائق
    # ──────────────────────────────────────────────────────────────────────────
    def test_last_active_not_written_twice_inside_five_minute_window(self):
        """صيانة الأداء: لا يتم تحديث last_active_at إلا بعد مضي 5 دقائق."""
        tok = self._login()
        device = UserDevice.objects.get(key=tok)
        original_time = device.last_active_at

        # طلب فوري بعد ثوانٍ قليلة: لا يتغير الوقت في قاعدة البيانات
        self.client.get(f"/api/hr/users/{self.user_a.pk}/", HTTP_AUTHORIZATION=f"Token {tok}")
        device.refresh_from_db()
        self.assertEqual(device.last_active_at, original_time)

        # تعيين تاريخ قديم مضى عليه أكثر من 5 دقائق (310 ثوانٍ)
        past_time = timezone.now() - timedelta(seconds=310)
        UserDevice.objects.filter(pk=device.pk).update(last_active_at=past_time)

        # إرسال طلب جديد: الآن يجب تحديث last_active_at
        self.client.get(f"/api/hr/users/{self.user_a.pk}/", HTTP_AUTHORIZATION=f"Token {tok}")
        device.refresh_from_db()
        self.assertGreater(device.last_active_at, past_time)

    # ──────────────────────────────────────────────────────────────────────────
    # 9. العزل التام: لا يمكن قراءة أو إنهاء أجهزة مستخدم آخر
    # ──────────────────────────────────────────────────────────────────────────
    def test_no_endpoint_accepts_reading_or_evicting_another_users_devices(self):
        """لا يمكن لأي مستخدم رؤية أو إنهاء أجهزة مستخدم آخر حتى بتمرير معرّفه."""
        tok_a = self._login("user_a@ktra.test", "password_a_123")
        tok_b = self._login("user_b@ktra.test", "password_b_123")

        dev_b = UserDevice.objects.get(key=tok_b)

        # المستخدم أ يحاول جلب الأجهزة مع تمرير user_id الخاص بـ ب
        res = self.client.get(
            f"/api/hr/auth/devices/?user_id={self.user_b.id}&user={self.user_b.id}",
            HTTP_AUTHORIZATION=f"Token {tok_a}",
        )
        self.assertEqual(res.status_code, 200)
        returned_ids = [d["id"] for d in res.json()["devices"]]
        self.assertNotIn(dev_b.id, returned_ids)

        # المستخدم أ يحاول إنهاء جهاز ب => 404 Not Found
        res_evict = self.client.post(
            f"/api/hr/auth/devices/{dev_b.id}/evict/",
            HTTP_AUTHORIZATION=f"Token {tok_a}",
        )
        self.assertEqual(res_evict.status_code, 404)
        # جهاز ب ما زال حياً وصالحاً
        self.assertTrue(UserDevice.objects.filter(pk=dev_b.id).exists())
        self.assertEqual(self._witness(self.user_b, tok_b).status_code, 200)

        # المستخدم أ يحاول إعادة تسمية جهاز ب => 404 Not Found
        res_rename = self.client.post(
            f"/api/hr/auth/devices/{dev_b.id}/rename/",
            {"label": "محاولة اختراق"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok_a}",
        )
        self.assertEqual(res_rename.status_code, 404)

    # ──────────────────────────────────────────────────────────────────────────
    # 10. الجهاز الأساسي لا يُنهى من شاشة الأجهزة
    # ──────────────────────────────────────────────────────────────────────────
    def test_primary_device_cannot_be_evicted_from_device_screen(self):
        """لا يمكن إنهاء الجهاز الأساسي من شاشة الأجهزة، تسجيل الخروج العادي هو مخرجه."""
        tok = self._login()
        self.client.post(
            "/api/hr/auth/devices/set-primary/",
            {"password": "password_a_123"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok}",
        )
        dev = UserDevice.objects.get(key=tok)

        res = self.client.post(
            f"/api/hr/auth/devices/{dev.id}/evict/",
            HTTP_AUTHORIZATION=f"Token {tok}",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["code"], "CANNOT_EVICT_PRIMARY")
        self.assertTrue(UserDevice.objects.filter(pk=dev.id).exists())

    # ──────────────────────────────────────────────────────────────────────────
    # 11. اشتقاق الاسم والتسمية المخصصة
    # ──────────────────────────────────────────────────────────────────────────
    def test_device_name_derivation_and_custom_label(self):
        """اشتقاق اسم الجهاز من المتصفح والنظام، وتفضيل التسمية المخصصة إن وجدت."""
        tok = self._login(ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1")
        dev = UserDevice.objects.get(key=tok)
        self.assertEqual(dev.device_name, "Safari على iOS")
        self.assertEqual(dev.display_name, "Safari على iOS")

        # تسمية الجهاز
        res = self.client.post(
            f"/api/hr/auth/devices/{dev.id}/rename/",
            {"label": "هاتف العمل الشخصي"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok}",
        )
        self.assertEqual(res.status_code, 200)
        dev.refresh_from_db()
        self.assertEqual(dev.label, "هاتف العمل الشخصي")
        self.assertEqual(dev.display_name, "هاتف العمل الشخصي")

    # ──────────────────────────────────────────────────────────────────────────
    # 12. حين لا يوجد أساسي: دعوة اختيار الأساسي ومتاح لكل الأجهزة الإدارة
    # ──────────────────────────────────────────────────────────────────────────
    def test_no_primary_invitation_and_all_can_manage(self):
        """عند غياب الجهاز الأساسي، يُسمح لكل جهاز بالإدارة وتظهر دعوة اختيار أساسي."""
        tok_1 = self._login()
        tok_2 = self._login()

        # استعراض الأجهزة من الجهاز 2 بدون وجود أساسي
        res = self.client.get(
            "/api/hr/auth/devices/",
            HTTP_AUTHORIZATION=f"Token {tok_2}",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["has_primary"])
        self.assertIsNotNone(body["primary_invitation"])
        self.assertEqual(len(body["devices"]), 2)

        # التحقق من علامتي is_current و is_primary
        current_dev = next(d for d in body["devices"] if d["is_current"])
        other_dev = next(d for d in body["devices"] if not d["is_current"])
        self.assertFalse(current_dev["is_primary"])
        self.assertFalse(other_dev["is_primary"])

    # ──────────────────────────────────────────────────────────────────────────
    # 13. دعم أفعال HTTP القياسية DELETE و PATCH
    # ──────────────────────────────────────────────────────────────────────────
    def test_direct_delete_and_patch_http_methods(self):
        """دعم طلبات REST القياسية: DELETE للإنهاء و PATCH للتسمية على /auth/devices/<pk>/."""
        tok_1 = self._login()
        tok_2 = self._login()

        dev_2 = UserDevice.objects.get(key=tok_2)

        # إعادة التسمية عبر PATCH
        res_patch = self.client.patch(
            f"/api/hr/auth/devices/{dev_2.id}/",
            {"label": "جهاز مخصص عبر PATCH"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {tok_1}",
        )
        self.assertEqual(res_patch.status_code, 200)
        dev_2.refresh_from_db()
        self.assertEqual(dev_2.label, "جهاز مخصص عبر PATCH")

        # الإنهاء عبر DELETE
        res_del = self.client.delete(
            f"/api/hr/auth/devices/{dev_2.id}/",
            HTTP_AUTHORIZATION=f"Token {tok_1}",
        )
        self.assertEqual(res_del.status_code, 200)
        self.assertFalse(UserDevice.objects.filter(pk=dev_2.id).exists())
        self.assertEqual(self._witness(self.user_a, tok_2).status_code, 401)

    # ──────────────────────────────────────────────────────────────────────────
    # 14. اختبار DRF العام عبر DEFAULT_AUTHENTICATION_CLASSES
    # ──────────────────────────────────────────────────────────────────────────
    def test_drf_viewset_authenticates_with_device_token(self):
        """التحقق من أن DeviceTokenAuthentication يعمل بسلاسة على viewsets الخاصة بـ DRF."""
        tok = self._login()
        # ActivityLogViewSet تستخدم DEFAULT_AUTHENTICATION_CLASSES وتتطلب مصادقة
        res = self.client.get(
            "/api/activity/",
            HTTP_AUTHORIZATION=f"Token {tok}",
        )
        self.assertEqual(res.status_code, 200, res.content)


from django.test import TransactionTestCase  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.state import ProjectState  # noqa: E402


class MigrationSteppingTest(TransactionTestCase):
    """
    اختبار تشغيل الهجرة 0010 مباشرة عبر محرر المخطط (schema_editor)
    باستخدام TransactionTestCase لتمكين محرّر SQLite من العمل خارج atomic block.
    يضمن هذا الاختبار أن كائن الهجرة op.database_forwards ينفذ بصورة كاملة
    وينسخ كل المفاتيح بنجاح ويجعلها صالحة فوراً في طبقة HTTP.
    """
    def test_migration_operation_database_forwards_directly(self):
        user = User.objects.create_user(
            username="mig_user@ktra.test",
            email="mig_user@ktra.test",
            password="x",
        )
        legacy_key_2 = "legacy_key_via_operation_database_forwards_99"
        Token.objects.create(user=user, key=legacy_key_2)

        mig = migration_0010.Migration("0010_migrate_tokens_to_user_devices", "hr")
        op = mig.operations[0]
        state = ProjectState.from_apps(apps)
        with connection.schema_editor() as schema_editor:
            op.database_forwards("hr", schema_editor, state, state)

        migrated = UserDevice.objects.filter(key=legacy_key_2).first()
        self.assertIsNotNone(migrated)
        self.assertEqual(migrated.user, user)
        self.assertEqual(migrated.device_name, "جهازٌ غير معروف")
        self.assertEqual(migrated.user_agent, "")
        self.assertFalse(migrated.is_primary)

        # شاهد HTTP للتأكد من نجاح المصادقة بالمفتاح المهاجر عبر الهجرة الحقيقية
        res = self.client.get(
            f"/api/hr/users/{user.pk}/",
            HTTP_AUTHORIZATION=f"Token {legacy_key_2}",
        )
        self.assertEqual(res.status_code, 200)

