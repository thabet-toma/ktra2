"""«خطّتي»: حدودُ شركةِ الطالب واستهلاكُها — `GET /api/my-plan/usage/`.

ثلاثةُ أعطابٍ يحرسها هذا الملفّ، وكلٌّ منها صامت:

- **الحدُّ المعروضُ غيرُ الحدِّ المفروض.** البطاقةُ كانت تقرأ حدودَها من حمولة
  الأسعار **العامّة**، وتلك تعرف `PLAN_DEFAULTS` وحدَها؛ فشركةٌ رُفع لها الحدُّ
  بـ`TenantLimit` ترى رقمَ الخطّة لا رقمَها، ثمّ تُمنَع عند رقمٍ غيرِ الذي قرأته.
- **تسريبُ شركةٍ إلى أخرى.** هذه دالّةٌ لا ViewSet، فلا `get_queryset` تحرسها؛
  والعزلُ كلُّه معلَّقٌ على أنّ الشركةَ تُحلّ من الطلب لا من معامل.
- **عددُ الاستعلامات يكبر بصمت.** الصفحةُ تقرأ أحدَ عشرَ حدّاً، وكلُّ حدٍّ عدٌّ
  مستقلّ؛ فحدٌّ جديدٌ يُضاف إلى `LIMITS` يزيد استعلاماً بلا أن يلاحظه أحد.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import TenantLimit
from core.plans import LIMITS, PLAN_DEFAULTS, invalidate_limit_cache
from tenants.models import Tenant, UserCompanyMembership

URL = "/api/my-plan/usage/"


class MyPlanUsageTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            TenantID=7701, CompanyName="شركةُ الحدّ", SubscriptionPlan="Basic"
        )
        # شركةٌ ثانيةٌ ليست زينة: بشركةٍ واحدةٍ في القاعدة يحلّ `get_tenant`
        # الشركةَ الوحيدةَ تلقائيّاً، فيمرّ اختبارُ العزل خضراءَ بلا عزلٍ أصلاً.
        self.other = Tenant.objects.create(
            TenantID=7702, CompanyName="شركةٌ أخرى", SubscriptionPlan="Pro"
        )
        self.user = User.objects.create_user(username="plan_member", password="x")
        UserCompanyMembership.objects.create(
            user=self.user, tenant=self.tenant, role="employee"
        )
        self.outsider = User.objects.create_user(username="plan_outsider", password="x")
        UserCompanyMembership.objects.create(
            user=self.outsider, tenant=self.other, role="manager"
        )
        invalidate_limit_cache(self.tenant.TenantID)

    def _get(self, user=None, tenant=None):
        if user is not None:
            self.client.force_authenticate(user=user)
        return self.client.get(
            URL, HTTP_X_TENANT_ID=str((tenant or self.tenant).TenantID)
        )

    # --- الشكل ---------------------------------------------------------

    def test_every_limit_the_server_enforces_appears_in_the_payload(self):
        """مفتاحٌ بمفتاح مع `LIMITS` — لا جدولَ منسوخاً باليد.

        نقصانُ مفتاحٍ هنا يعني حدّاً يُفرَض على الشركة ولا تراه في بطاقتها، فتُمنَع
        عند سقفٍ لم يُعرَض لها قطّ.
        """
        response = self._get(self.user)
        self.assertEqual(response.status_code, 200)
        keys = [row["key"] for row in response.data["limits"]]
        self.assertEqual(keys, list(LIMITS))

    def test_the_payload_does_not_reveal_the_private_deal_behind_the_limit(self):
        """`plan_default` و`override` و`has_override` لا مكانَ لها هنا.

        التجاوزُ اتّفاقٌ بين المنصّة والشركة، وعرضُه لكلّ عضوٍ فيها كشفٌ لا يلزم
        لقراءة «كم بقي لي» — والفعّالُ وحدَه هو ما يُفرَض فهو وحدَه ما يُعرَض.
        """
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="sales.invoices", max_value=999
        )
        invalidate_limit_cache(self.tenant.TenantID)
        row = self._get(self.user).data["limits"][0]
        for leaked in ("plan_default", "override", "has_override"):
            self.assertNotIn(leaked, row)

    # --- الحدُّ الفعّال لا افتراضُ الخطّة -------------------------------

    def test_the_limit_shown_is_the_one_actually_enforced_not_the_plan_default(self):
        """تجاوزُ `TenantLimit` يغلب افتراضَ الخطّة في المعروض كما يغلبه في المفروض.

        هذا بعينه العطبُ الذي جعل البطاقةَ تُبنى على نقطةِ أسعارٍ عامّةٍ خطأً:
        تلك لا تعرف الشركةَ أصلاً، فرقمُها صحيحٌ للخطّة وكاذبٌ لهذه الشركة.
        """
        default = PLAN_DEFAULTS["Basic"]["sales.invoices"]
        raised = default + 500
        TenantLimit.objects.create(
            tenant=self.tenant, limit_key="sales.invoices", max_value=raised
        )
        invalidate_limit_cache(self.tenant.TenantID)

        rows = {r["key"]: r for r in self._get(self.user).data["limits"]}
        self.assertEqual(rows["sales.invoices"]["limit"], raised)
        self.assertNotEqual(rows["sales.invoices"]["limit"], default)

    def test_usage_is_counted_from_the_real_tables(self):
        """عضوان في الشركة ⇒ استهلاكُ «أعضاء الشركة» اثنان — لا صفرٌ ثابت."""
        rows = {r["key"]: r for r in self._get(self.user).data["limits"]}
        self.assertEqual(rows["company.members"]["usage"], 1)

        User.objects.create_user(username="plan_member_2", password="x")
        UserCompanyMembership.objects.create(
            user=User.objects.get(username="plan_member_2"),
            tenant=self.tenant, role="employee",
        )
        rows = {r["key"]: r for r in self._get(self.user).data["limits"]}
        self.assertEqual(rows["company.members"]["usage"], 2)

    # --- العزل ---------------------------------------------------------

    def test_a_member_cannot_read_another_companys_usage(self):
        """ترويسةٌ لشركةٍ لا عضويّةَ فيها تُرَدّ، ولا يتسرّب رقمٌ منها.

        الدالّةُ ليست ViewSet فلا `get_queryset` تفلتر لها؛ عزلُها كلُّه أنّ
        الشركةَ تُحلّ من الطلب عبر `get_tenant` الذي يتحقّق من العضويّة.
        """
        response = self._get(self.user, tenant=self.other)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("limits", getattr(response, "data", {}) or {})

    def test_an_anonymous_visitor_gets_nothing(self):
        """نقطةٌ مصادَقةٌ لا عامّة — الحدودُ العامّةُ لها `/api/pricing/plans/`."""
        response = self.client.get(URL, HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        self.assertIn(response.status_code, (401, 403))

    # --- الأداء --------------------------------------------------------

    def test_the_whole_card_costs_a_fixed_number_of_queries(self):
        """عددٌ **مطلق**، لا موازنةُ تشغيلٍ بتشغيلٍ لنفس المعطيات.

        التركيبُ اليوم ستّةَ عشرَ: ثلاثةٌ لحلّ الشركة والتحقّق من العضويّة وقراءة
        التجاوزات، وثلاثةَ عشرَ عدّاً لأحدَ عشرَ حدّاً — **لا واحدٌ لكلّ حدّ**،
        فـ`documents.invoices` يعدّ البيعَ والشراءَ معاً و`employee_ops.seats`
        يعدّ الأعضاءَ والدعواتِ المعلَّقة. ورقمٌ مطلقٌ لا صيغةٌ على `len(LIMITS)`:
        الصيغةُ تفترض عدّاً واحداً لكلّ حدٍّ وهي مخالِفةٌ للواقع، فتتحرّك مع
        الكود بدل أن تمسكه.

        وثلاثةُ أعدادٍ من الثلاثةَ عشرَ **مكرَّرةٌ فعلاً** (عدّا البيع والشراء
        يقعان مرّتين: مرّةً لحدّهما ومرّةً لحدّ المجموع) — نقصٌ قائمٌ في
        `limit_rows` يسبق هذه التذكرة ويخصّ لوحةَ المنصّة أيضاً، مسجَّلٌ هنا
        صراحةً كي لا يُقرأ الرقمُ ستّةَ عشرَ على أنّه الأمثل.

        وتثبيتُ الرقم يجعل أيَّ حدٍّ جديدٍ يُضاف إلى `LIMITS` **قراراً واعياً** لا
        زيادةً صامتةً على نقطةٍ تُفتَح مع كلّ زيارةٍ للإعدادات. واختباراتُ هذا
        المستودع تعمل على `DummyCache`، أي على المسار غير المكشوف بالضبط: كاشُ
        التجاوزات لا يُنقذ هنا.
        """
        self.client.force_authenticate(user=self.user)
        self.client.get(URL, HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        with self.assertNumQueries(16):
            response = self.client.get(
                URL, HTTP_X_TENANT_ID=str(self.tenant.TenantID)
            )
        self.assertEqual(response.status_code, 200)
