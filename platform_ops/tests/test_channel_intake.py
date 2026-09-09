"""اختبارات قناة الاستقبال ومفتاحها وIdempotency واحتساب الفوترة (المرحلة الرابعة م٤).

تغطي هذه الاختبارات المتطلبات الصارمة المحددة بالاسم:
1. idempotency: نفس external_ref مرتين -> أمر عمل واحد وعملية مفوترة واحدة (التحقق من العداد لا من عدد الصفوف وحده).
2. نفس external_ref لشركتين مختلفتين -> أمران (الفرادة لكل شركة وقناة لا عالمية).
3. الحمولة المرفوضة: حمولة تحمل assignee أو status أو price تُرفض — اختبار الثلاثة كلاً على حدة.
4. الشركة من المفتاح لا من الحمولة: حمولة تدعي شركة أخرى لا تنشئ شيئاً في تلك الشركة.
5. المفتاح المبطل يُرفض، والمدوَّر يقبل الجديد ويرفض القديم.
6. الرمز الخام لا يُحفظ: بعد التوليد، لا يوجد أي صف في القاعدة يحمل الرمز الخام في أي حقل.
7. الخانق يعمل ومربوط بالمفتاح.
8. سقف الحجم يُفحص بالبايتات: حمولة تعلن حجماً صغيراً وجسمها أكبر تُرفض.
9. طول العمود مقابل أطول رمز لكل حقل choices جديد (channel, status).
10. العزل بالشركة: لا تسريب عبر الشركات في نقطة الاستقبال أو مفاتيح التكامل.
"""
import hashlib
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from core.models import TenantAsset
from tenants.models import Tenant

from platform_ops.models import (
    IntegrationKey,
    PlatformEmployee,
    ServiceSubscription,
    WorkOrder,
)
from platform_ops.services import (
    IntegrationKeyConflict,
    authenticate_integration_key,
    IntegrationKeyError,
    generate_integration_key,
    receive_channel_work_order,
    revoke_integration_key,
    rotate_integration_key,
)

User = get_user_model()


class ChannelIntakeTest(TestCase):
    """مجموعة اختبارات سطح نقطة الاستقبال وطبقة الخدمات للمرحلة الرابعة."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.tenant_a = Tenant.objects.create(TenantID=2001, CompanyName="Alpha Logistics Co")
        self.tenant_b = Tenant.objects.create(TenantID=2002, CompanyName="Beta Trading Co")

        self.sub_a = ServiceSubscription.objects.create(
            tenant=self.tenant_a,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
            included_quota=100,
            consumed_quota=0,
            overage_unit_price=Decimal("5.00"),
        )
        self.sub_b = ServiceSubscription.objects.create(
            tenant=self.tenant_b,
            status=ServiceSubscription.Status.ACTIVE,
            plan="standard",
            included_quota=50,
            consumed_quota=0,
            overage_unit_price=Decimal("10.00"),
        )

        self.key_a, self.raw_token_a = generate_integration_key(
            tenant=self.tenant_a,
            channel=IntegrationKey.Channel.WHATSAPP,
            name="Alpha WhatsApp",
        )
        self.key_b, self.raw_token_b = generate_integration_key(
            tenant=self.tenant_b,
            channel=IntegrationKey.Channel.WHATSAPP,
            name="Beta WhatsApp",
        )

    def tearDown(self):
        cache.clear()

    def test_01_idempotency_same_external_ref_returns_same_order_and_charges_once(self):
        """1. idempotency: نفس external_ref مرتين -> أمر عمل واحد وعملية مفوترة واحدة.

        التحقق من العداد consumed_quota لا من عدد الصفوف وحده.
        """
        payload = {
            "external_ref": "REF-MSG-1001",
            "title": "فاتورة توريد بضاعة",
            "description": "استلام مستندات الشحنة",
            "kind": "data_entry",
        }

        # الطلب الأول: قبول وإنشاء جديد
        res1 = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED, res1.data)
        wo_id_1 = res1.data["id"]

        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 1)
        self.assertEqual(
            WorkOrder.objects.filter(tenant=self.tenant_a, external_ref="REF-MSG-1001").count(),
            1,
        )

        # الطلب الثاني: نفس المرجع الخارجي تماماً
        res2 = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK, res2.data)
        wo_id_2 = res2.data["id"]

        # أمر العمل نفسه لم يتغير
        self.assertEqual(wo_id_1, wo_id_2)

        # التحقق الحاسم من العداد: لم يزد ولم يُحتسب مرتين
        self.sub_a.refresh_from_db()
        self.assertEqual(
            self.sub_a.consumed_quota,
            1,
            "إعادة إرسال نفس external_ref زادت عداد العمليات المفوترة وهذا خرق صارم لـ idempotency.",
        )
        self.assertEqual(
            WorkOrder.objects.filter(tenant=self.tenant_a, external_ref="REF-MSG-1001").count(),
            1,
        )

    def test_02_same_external_ref_for_two_different_companies_creates_two_orders(self):
        """2. نفس external_ref لشركتين مختلفتين -> أمران (الفرادة لكل شركة وقناة لا عالمية)."""
        ref = "SHARED-MSG-777"
        payload = {
            "external_ref": ref,
            "title": "طلب مشترك المرجع",
            "description": "نفس المرجع الخارجي من قناتين لشركتين مختلفتين",
        }

        res_a = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_a.status_code, status.HTTP_201_CREATED, res_a.data)

        res_b = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_b,
        )
        self.assertEqual(res_b.status_code, status.HTTP_201_CREATED, res_b.data)

        self.assertNotEqual(res_a.data["id"], res_b.data["id"])
        self.assertEqual(WorkOrder.objects.get(pk=res_a.data["id"]).tenant_id, self.tenant_a.pk)
        self.assertEqual(WorkOrder.objects.get(pk=res_b.data["id"]).tenant_id, self.tenant_b.pk)
        # والردُّ نحيفٌ عمداً: لا يحمل تفاصيلَ تشغيلٍ داخليّةً لقناةٍ خارجيّة
        self.assertNotIn("policy_snapshot", res_a.data)
        self.assertNotIn("assignee", res_a.data)

        self.sub_a.refresh_from_db()
        self.sub_b.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 1)
        self.assertEqual(self.sub_b.consumed_quota, 1)

    def test_03_rejected_payload_assignee_status_price_rejected_individually(self):
        """3. الحمولة المرفوضة: حمولة تحمل assignee أو status أو price تُرفض — اختبار الثلاثة كلاً على حدة."""
        base_payload = {
            "external_ref": "REF-REJECT-TEST",
            "title": "طلب مرفوض",
        }

        # 3.1 اختبار assignee
        payload_with_assignee = dict(base_payload, assignee=1)
        res_assignee = self.client.post(
            "/api/platform/ops/intake/",
            data=payload_with_assignee,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_assignee.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assignee", res_assignee.data.get("detail", ""))

        # 3.2 اختبار status
        payload_with_status = dict(base_payload, status="closed")
        res_status = self.client.post(
            "/api/platform/ops/intake/",
            data=payload_with_status,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_status.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", res_status.data.get("detail", ""))

        # 3.3 اختبار price
        payload_with_price = dict(base_payload, price=150.0)
        res_price = self.client.post(
            "/api/platform/ops/intake/",
            data=payload_with_price,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_price.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("price", res_price.data.get("detail", ""))

        # تأكيد عدم إنشاء أي صف أو احتساب عملية لأي طلب مرفوض
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 0)
        self.assertFalse(WorkOrder.objects.filter(external_ref="REF-REJECT-TEST").exists())

    def test_04_tenant_derived_from_key_not_payload_claims_other_tenant_creates_nothing_there(self):
        """4. الشركة من المفتاح لا من الحمولة: حمولة تدعي شركة أخرى لا تنشئ شيئاً في تلك الشركة."""
        # نرسل بمفتاح الشركة A ولكن نمرر معرف الشركة B في الحمولة
        payload = {
            "external_ref": "REF-SPOOF-TENANT",
            "title": "محاولة انتحال شركة",
            "tenant": self.tenant_b.pk,
            "tenant_id": self.tenant_b.pk,
            "company_id": self.tenant_b.pk,
        }

        res = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # التأكيد القاطع: أمر العمل أُنشئ للشركة A (صاحبة المفتاح) وليس B
        wo = WorkOrder.objects.get(external_ref="REF-SPOOF-TENANT")
        self.assertEqual(wo.tenant_id, self.tenant_a.pk)
        self.assertNotEqual(wo.tenant_id, self.tenant_b.pk)

        # الشركة B لم تتأثر بأي شكل
        self.assertFalse(
            WorkOrder.objects.filter(tenant=self.tenant_b, external_ref="REF-SPOOF-TENANT").exists()
        )
        self.sub_b.refresh_from_db()
        self.assertEqual(self.sub_b.consumed_quota, 0)

    def test_05_revoked_key_rejected_and_rotated_key_accepts_new_and_rejects_old(self):
        """5. المفتاح المبطل يُرفض، والمدوَّر يقبل الجديد ويرفض القديم."""
        payload = {"external_ref": "REF-KEY-LIFECYCLE", "title": "اختبار دورة حياة المفتاح"}

        # 5.1 إبطال المفتاح A
        revoke_integration_key(key=self.key_a, reason="إبطال أمني تجريبي")
        res_revoked = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_revoked.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("مبطل", res_revoked.data.get("detail", ""))

        # 5.2 تدوير المفتاح B
        old_token_b = self.raw_token_b
        rotated_key_b, new_token_b = rotate_integration_key(key=self.key_b)
        self.assertNotEqual(old_token_b, new_token_b)

        # القديم يُرفض
        res_old = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=old_token_b,
        )
        self.assertEqual(res_old.status_code, status.HTTP_401_UNAUTHORIZED)

        # الجديد يُقبل
        res_new = self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=new_token_b,
        )
        self.assertEqual(res_new.status_code, status.HTTP_201_CREATED)

    def test_06_raw_token_is_never_stored_in_database(self):
        """6. الرمز الخام لا يُحفظ: بعد التوليد، لا يوجد أي صف في القاعدة يحمل الرمز الخام في أي حقل."""
        key, raw_token = generate_integration_key(
            tenant=self.tenant_a,
            channel=IntegrationKey.Channel.TELEGRAM,
            name="Telegram Key",
        )

        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        key.refresh_from_db()
        self.assertEqual(key.token_hash, expected_hash)

        # فحص كافة حقول الصف: الرمز الخام لا يوجد في أي حقل إطلاقاً
        for field in key._meta.get_fields():
            if field.is_relation:
                continue
            val = getattr(key, field.name, None)
            if val is not None:
                self.assertNotIn(
                    raw_token,
                    str(val),
                    f"الرمز الخام وُجد في الحقل {field.name} وهذا تسريب خطير.",
                )

        # فحص عدم وجود الرمز الخام في أي نموذج آخر
        self.assertFalse(IntegrationKey.objects.filter(token_hash=raw_token).exists())

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_07_throttle_works_and_is_tied_to_key(self):
        """7. الخانق يعمل ومربوط بالمفتاح."""
        # توليد مفتاحين لاختبار أن خانق المفتاح الأول لا يعطل المفتاح الثاني
        key_t1, token_t1 = generate_integration_key(
            tenant=self.tenant_a,
            channel=IntegrationKey.Channel.API,
        )
        key_t2, token_t2 = generate_integration_key(
            tenant=self.tenant_b,
            channel=IntegrationKey.Channel.API,
        )

        from platform_ops.throttles import IntegrationKeyThrottle

        # ضبط معدل منخفض للاختبار (3/minute)
        original_rate = IntegrationKeyThrottle.get_rate

        def mocked_rate(self_throttle):
            return "3/minute"

        IntegrationKeyThrottle.get_rate = mocked_rate
        try:
            # 3 طلبات تنجح
            for i in range(3):
                res = self.client.post(
                    "/api/platform/ops/intake/",
                    data={"external_ref": f"THROTTLE-1-{i}", "title": f"طلب {i}"},
                    format="json",
                    HTTP_X_INTEGRATION_KEY=token_t1,
                )
                self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

            # الطلب الرابع بنفس المفتاح يُخنق بـ 429
            res4 = self.client.post(
                "/api/platform/ops/intake/",
                data={"external_ref": "THROTTLE-1-OVERFLOW", "title": "طلب زائد"},
                format="json",
                HTTP_X_INTEGRATION_KEY=token_t1,
            )
            self.assertEqual(res4.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

            # المفتاح الثاني من نفس العميل/IP يعمل بحرية ولا يتأثر بخنق المفتاح الأول
            res_other = self.client.post(
                "/api/platform/ops/intake/",
                data={"external_ref": "THROTTLE-2-OK", "title": "طلب مفتاح آخر"},
                format="json",
                HTTP_X_INTEGRATION_KEY=token_t2,
            )
            self.assertEqual(res_other.status_code, status.HTTP_201_CREATED)
        finally:
            IntegrationKeyThrottle.get_rate = original_rate

    def test_08_byte_size_limit_is_enforced_on_the_bytes_actually_read(self):
        """8. سقفُ الحجم يُفحَص بالبايتات: بالمعلَن قبل القراءة، وبالمقروء فعلاً بعدها.

        **ولا تأكيدَ على «ترويسةٍ تكذب بالنقصان»**: تحت خادمٍ حقيقيّ يقطع جانغو
        القراءةَ عند `CONTENT_LENGTH`، فجسمٌ أكبرُ من المعلَن لا يصل الكودَ أصلاً —
        وتأكيدٌ لا يستطيع السقوطَ في الإنتاج للسبب الذي يحمله اسمُه ليس حارساً.
        """
        # المعلَنُ فوق السقف يُردّ قبل تحميل الحمولة في الذاكرة
        res_declared = self.client.post(
            "/api/platform/ops/intake/",
            data='{"external_ref": "REF-DECLARED-HUGE"}',
            content_type="application/json",
            CONTENT_LENGTH=str(300 * 1024),
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(
            res_declared.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, res_declared.data
        )

        # والبايتاتُ المقروءةُ فعلاً هي الحكم
        huge_body = '{"external_ref": "REF-TOO-LARGE", "data": "' + ("B" * (257 * 1024)) + '"}'
        res_huge = self.client.post(
            "/api/platform/ops/intake/",
            data=huge_body,
            content_type="application/json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_huge.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.assertIn("الحد الأقصى", res_huge.data.get("detail", ""))

        # ولا صفَّ ولا عمليّةً محتسبةً لأيٍّ من المردودَين
        self.sub_a.refresh_from_db()
        self.assertEqual(self.sub_a.consumed_quota, 0)
        self.assertFalse(
            WorkOrder.objects.filter(
                external_ref__in=["REF-DECLARED-HUGE", "REF-TOO-LARGE"]
            ).exists()
        )

    def test_09_media_attachments_require_valid_tenant_asset_ids_and_reject_raw_urls(self):
        """المرفقات عبر خدمة الوسائط فقط: تُقبل بالمعرفات وتُرفض بالروابط الحرة."""
        # 1. رفض الروابط المباشرة في الحمولة
        payload_with_url = {
            "external_ref": "REF-URL-REJECT",
            "title": "طلب مع رابط",
            "file_url": "https://malicious.external.com/invoice.pdf",
        }
        res_url = self.client.post(
            "/api/platform/ops/intake/",
            data=payload_with_url,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_url.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("روابط", res_url.data.get("detail", ""))

        # 1ب. ورابطٌ **مدفونٌ** داخل قائمة مرفقات يُرفض كذلك
        res_nested = self.client.post(
            "/api/platform/ops/intake/",
            data={
                "external_ref": "REF-NESTED-URL",
                "title": "طلب برابط مدفون",
                "attachments": [{"name": "فاتورة", "url": "https://evil.example.com/x.pdf"}],
            },
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_nested.status_code, status.HTTP_400_BAD_REQUEST, res_nested.data)
        self.assertFalse(WorkOrder.objects.filter(external_ref="REF-NESTED-URL").exists())

        # 2. معرف مرفق يتبع شركة أخرى يُرفض
        asset_b = TenantAsset.objects.create(
            tenant=self.tenant_b,
            public_id="asset_company_b_123",
            bytes=1024,
        )
        payload_cross_tenant_asset = {
            "external_ref": "REF-CROSS-ASSET",
            "title": "طلب بمرفق شركة أخرى",
            "attachment_ids": [asset_b.id],
        }
        res_cross = self.client.post(
            "/api/platform/ops/intake/",
            data=payload_cross_tenant_asset,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_cross.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("المرفق", res_cross.data.get("detail", ""))

        # 3. معرف مرفق يتبع لنفس الشركة يُقبل
        asset_a = TenantAsset.objects.create(
            tenant=self.tenant_a,
            public_id="asset_company_a_456",
            bytes=2048,
        )
        payload_valid_asset = {
            "external_ref": "REF-VALID-ASSET",
            "title": "طلب بمرفق صحيح",
            "attachment_ids": [asset_a.id],
        }
        res_valid = self.client.post(
            "/api/platform/ops/intake/",
            data=payload_valid_asset,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )
        self.assertEqual(res_valid.status_code, status.HTTP_201_CREATED)
        wo = WorkOrder.objects.get(external_ref="REF-VALID-ASSET")
        self.assertEqual(wo.attachment_ids, [asset_a.id])

    def test_10_tenant_isolation_no_data_leakage(self):
        """10. العزل بالشركة: نقطة الاستقبال لا تسرب أي معلومات أو بيانات للشركات الأخرى."""
        # ننشئ أمراً للشركة A
        self.client.post(
            "/api/platform/ops/intake/",
            data={"external_ref": "ISOLATION-A-1", "title": "أمر سري للشركة A"},
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token_a,
        )

        # استعلام الشركة B بنفس المرجع لا يجد أمر الشركة A
        wo_b = WorkOrder.objects.filter(tenant=self.tenant_b, external_ref="ISOLATION-A-1").first()
        self.assertIsNone(wo_b)

        # المفتاح الخاص بالشركة A لا يستطيع إنشاء شيء للشركة B
        # والشركة B لا تتأثر حصتها
        self.sub_b.refresh_from_db()
        self.assertEqual(self.sub_b.consumed_quota, 0)


class ChoicesColumnWidthPhaseFourTest(SimpleTestCase):
    """9. اختبار مقارنة max_length بأطول مفتاح رمز في كل حقل choices جديد.

    MySQL يُلغي القيد بصمت إذا كان أطول رمز يتجاوز طول العمود؛ وSQLite لا تكشفه.
    """

    def test_choices_column_widths_accommodate_longest_keys(self):
        fields = [
            (IntegrationKey, "channel"),
            (IntegrationKey, "status"),
            (WorkOrder, "channel"),
        ]
        for model, name in fields:
            with self.subTest(model=model.__name__, field=name):
                field = model._meta.get_field(name)
                keys = [key for key, _ in (field.choices or [])]
                self.assertTrue(len(keys) > 0, f"{model.__name__}.{name} ليس له خيارات.")
                longest = max(keys, key=len)
                self.assertGreaterEqual(
                    field.max_length,
                    len(longest),
                    f"{model.__name__}.{name}: العمود {field.max_length} وأطول رمز "
                    f"'{longest}' طوله {len(longest)} — القيد يسقط بصمت على MySQL.",
                )


class ChannelIntakeAcceptsRealDocumentsTest(TestCase):
    """ما **يجب أن يمرّ**: الغرضُ الأوّلُ للقناة أن يرسل الزبونُ مستنداً.

    الفحصُ الأوّلُ كان يغوص في الحمولة كلِّها ويردُّ أيَّ مفتاحٍ اسمُه `amount` أو
    `cost` أو `rate`، ويردُّ أيَّ نصٍّ فيه `http://` — فكانت **كلُّ فاتورةٍ حقيقيّةٍ
    تُرفَض**، وهي بالضبط ما بُنيت الوحدةُ لاستقباله. فيُحرَس القبولُ كما يُحرَس المنع.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.tenant = Tenant.objects.create(TenantID=2051, CompanyName="Real Docs Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
            included_quota=100,
        )
        self.key, self.raw_token = generate_integration_key(
            tenant=self.tenant, channel=IntegrationKey.Channel.WHATSAPP
        )

    def tearDown(self):
        cache.clear()

    def _post(self, payload):
        return self.client.post(
            "/api/platform/ops/intake/",
            data=payload,
            format="json",
            HTTP_X_INTEGRATION_KEY=self.raw_token,
        )

    def test_an_invoice_carrying_amounts_in_its_lines_is_accepted(self):
        response = self._post({
            "external_ref": "INV-REAL-001",
            "title": "فاتورة مورّد",
            "document": {
                "invoice_no": "2026-114",
                "total_amount": 1450.75,
                "lines": [
                    {"item": "ورق تصوير", "qty": 10, "unit_price": 12.5, "amount": 125.0},
                    {"item": "حبر طابعة", "qty": 3, "unit_price": 90.0, "amount": 270.0},
                ],
            },
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        wo = WorkOrder.objects.get(external_ref="INV-REAL-001")
        self.assertEqual(wo.tenant_id, self.tenant.pk)
        # والحمولةُ تُحفظ كما وصلت — المبالغُ جزءٌ من المستند لا أمرٌ للمنصّة
        self.assertEqual(wo.intake_payload["document"]["total_amount"], 1450.75)

    def test_free_text_mentioning_a_link_is_accepted(self):
        response = self._post({
            "external_ref": "MSG-WITH-LINK",
            "title": "رسالة زبون",
            "description": "الفاتورة موجودة على https://drive.example.com/x وأرسلتها لك كمرفق",
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_a_control_field_at_the_top_level_is_still_rejected(self):
        """التضييقُ لم يفتح البابَ: حقلُ التحكُّم في المستوى الأعلى ما زال يُردّ."""
        for field, value in (("assignee", 1), ("status", "closed"), ("price", 99)):
            with self.subTest(field=field):
                response = self._post({
                    "external_ref": f"CTRL-{field}",
                    "title": "محاولة إملاء",
                    field: value,
                })
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(WorkOrder.objects.filter(external_ref=f"CTRL-{field}").exists())


class IntegrationKeyReissueTest(TestCase):
    """إعادةُ إصدار مفتاحِ قناةٍ أُبطل — ومَن يحفظ سببَ الإبطال.

    الفرادةُ على (شركة، قناة) **غيرُ مشروطة** فالصفُّ واحد. فكان الإبطالُ طريقاً
    مسدوداً: `generate` يرفض لوجود صفّ، و`rotate` يُحيي الصفَّ **ويمحو** سببَ
    إبطاله. فالقناةُ إمّا تموت أو يضيع أثرُها.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=2061, CompanyName="Reissue Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth"
        )
        self.admin = User.objects.create_superuser(
            username="reissue_admin", email="reissue_admin@platform.local", password="x"
        )

    def test_a_revoked_channel_can_be_issued_a_new_key_and_keeps_its_revocation_trail(self):
        key, first_token = generate_integration_key(
            tenant=self.tenant, channel=IntegrationKey.Channel.WHATSAPP
        )
        revoke_integration_key(key=key, revoked_by=self.admin, reason="تسرّب الرمز")

        key2, second_token = generate_integration_key(
            tenant=self.tenant, channel=IntegrationKey.Channel.WHATSAPP
        )

        # الصفُّ نفسُه — فالفرادةُ غيرُ مشروطةٍ ولا تحتمل صفّاً ثانياً
        self.assertEqual(key2.pk, key.pk)
        self.assertEqual(key2.status, IntegrationKey.Status.ACTIVE)
        self.assertNotEqual(second_token, first_token)
        self.assertEqual(
            IntegrationKey.objects.filter(
                tenant=self.tenant, channel=IntegrationKey.Channel.WHATSAPP
            ).count(),
            1,
        )

        # الرمزُ القديم لا يعمل والجديدُ يعمل
        self.assertEqual(authenticate_integration_key(first_token), (None, "invalid"))
        self.assertEqual(authenticate_integration_key(second_token)[0].pk, key.pk)

        # وأثرُ الإبطال محفوظٌ لا ممحوّ
        self.assertEqual(len(key2.revocation_history), 1)
        self.assertEqual(key2.revocation_history[0]["reason"], "تسرّب الرمز")
        self.assertEqual(key2.revocation_history[0]["revoked_by_id"], self.admin.pk)
        self.assertIsNotNone(key2.revocation_history[0]["revoked_at"])

    def test_an_active_key_still_conflicts(self):
        generate_integration_key(tenant=self.tenant, channel=IntegrationKey.Channel.TELEGRAM)
        with self.assertRaises(IntegrationKeyConflict) as ctx:
            generate_integration_key(tenant=self.tenant, channel=IntegrationKey.Channel.TELEGRAM)
        self.assertEqual(ctx.exception.code, "already_exists")

    def test_a_revoked_key_is_never_resurrected_by_rotation(self):
        """التدويرُ لا يُحيي مبطَلاً — وإلّا مُحيت أسبابُ الإبطال بنداءٍ واحد."""
        key, _ = generate_integration_key(
            tenant=self.tenant, channel=IntegrationKey.Channel.EMAIL
        )
        revoke_integration_key(key=key, revoked_by=self.admin, reason="انتهى التعاقد")

        with self.assertRaises(IntegrationKeyError) as ctx:
            rotate_integration_key(key=key)
        self.assertEqual(ctx.exception.code, "key_revoked")

        key.refresh_from_db()
        self.assertEqual(key.status, IntegrationKey.Status.REVOKED)
        self.assertEqual(key.revocation_reason, "انتهى التعاقد")
        self.assertEqual(key.revoked_by_id, self.admin.pk)


class IntegrationKeyAdminEndpointsTest(TestCase):
    """بابُ الإصدار والتدوير والإبطال — بلاه لا يكون الإبطالُ «فوريّاً».

    المواصفةُ تقول «قابلٌ للإبطال والتدوير **فوراً** عند تسرّبه». وخدماتٌ بلا نقطةٍ
    تستدعيها تعني أنّ المفتاحَ المسرَّب يُبطَل من `manage.py shell` وحدَه — وهذا
    ليس فوريّاً ولا يفعله أحدٌ تحت الضغط.
    """

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.tenant = Tenant.objects.create(TenantID=2071, CompanyName="Key Door Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth"
        )
        self.admin = User.objects.create_superuser(
            username="key_admin", email="key_admin@platform.local", password="x"
        )
        self.outsider = User.objects.create_user(
            username="key_outsider", email="key_outsider@platform.local", password="x"
        )

    def tearDown(self):
        cache.clear()

    def _intake(self, token, ref):
        return self.client.post(
            "/api/platform/ops/intake/",
            data={"external_ref": ref, "title": "طلب"},
            format="json",
            HTTP_X_INTEGRATION_KEY=token,
        )

    def test_issue_rotate_and_revoke_through_the_api(self):
        self.client.force_authenticate(user=self.admin)

        issued = self.client.post(
            "/api/platform/ops/integration-keys/issue/",
            data={"tenant": self.tenant.pk, "channel": "whatsapp", "name": "قناة الشركة"},
            format="json",
        )
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED, issued.data)
        first_token = issued.data["raw_token"]
        key_id = issued.data["id"]
        # لا تجزئةَ ولا رمزَ في العرض العاديّ
        self.assertNotIn("token_hash", issued.data)

        self.client.force_authenticate(user=None)
        self.assertEqual(self._intake(first_token, "DOOR-1").status_code, status.HTTP_201_CREATED)

        # التدوير: الجديدُ يعمل والقديمُ يسقط فوراً
        self.client.force_authenticate(user=self.admin)
        rotated = self.client.post(f"/api/platform/ops/integration-keys/{key_id}/rotate/")
        self.assertEqual(rotated.status_code, status.HTTP_200_OK, rotated.data)
        second_token = rotated.data["raw_token"]
        self.assertNotEqual(second_token, first_token)

        self.client.force_authenticate(user=None)
        self.assertEqual(self._intake(first_token, "DOOR-2").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self._intake(second_token, "DOOR-3").status_code, status.HTTP_201_CREATED)

        # الإبطال: يسقط المفتاحُ ويبقى سببُه
        self.client.force_authenticate(user=self.admin)
        revoked = self.client.post(
            f"/api/platform/ops/integration-keys/{key_id}/revoke/",
            data={"reason": "تسرّب الرمز"},
            format="json",
        )
        self.assertEqual(revoked.status_code, status.HTTP_200_OK, revoked.data)
        self.assertEqual(revoked.data["status"], IntegrationKey.Status.REVOKED)
        self.assertEqual(revoked.data["revocation_reason"], "تسرّب الرمز")

        self.client.force_authenticate(user=None)
        self.assertEqual(self._intake(second_token, "DOOR-4").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_door_is_shut_to_anyone_but_a_platform_manager(self):
        self.client.force_authenticate(user=self.outsider)
        response = self.client.post(
            "/api/platform/ops/integration-keys/issue/",
            data={"tenant": self.tenant.pk, "channel": "whatsapp"},
            format="json",
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
            response.data,
        )
        self.assertEqual(IntegrationKey.objects.count(), 0)
