"""اختبارات المرحلة السابعة (م٧): التقييم اليومي، تبويب «من يمسك دفاتري»، ودرجتا الصحة.

تغطي هذه الاختبارات المتطلبات الصارمة:
1. no_work_on_date: منع إنشاء تقييم أو رابط ليوم لم يعمل فيه الموظف فعلياً في الشركة.
2. token_expires_after_72h: انتهاء صلاحية الرابط بعد 72 ساعة ويرد بـ 410 Gone صريحة.
3. single_edit_allowed: السماح بالتعديل مرة واحدة فقط ورفض التعديل الثاني بـ 400 / Conflict.
4. raw_token_never_stored: عدم حفظ الرمز الخام في القاعدة أبداً وحفظ المهشر SHA-256 فقط.
5. no_public_leakage: استجابة الرابط العام مقيدة بقائمة بيضاء صارمة ولا تسرب بيانات داخلية.
6. client_ip_scoped_throttle: حماية الرابط العام بالخانق ClientIpScopedThrottle بربط REMOTE_ADDR.
7. who_manages_my_books_excludes_view_login: استبعاد حركات العرض view والدخول login من سجل نشاط الوكيل.
8. tenant_isolation: عزل الشركات ورفض وسائط الشركات الممنوعة بـ 400 Bad Request.
9. agent_derived_strictly_from_engagement: اشتقاق الوكيل حصراً من Engagement النشط لا من جدول العضويات.
10. two_health_scores_strictly_separated: فصل درجتي الصحة (صحة الخدمة vs تعاون الزبون) وعدم تأثرهما بالباقة.
11. choice_column_max_length: فحص اتساع حقول choices للنماذج المضافة.
"""
import datetime
from decimal import Decimal
import hashlib

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import ActivityLog
from tenants.models import Tenant, UserCompanyMembership

from platform_ops.models import (
    AgentGrantedMembership,
    DailyRating,
    DailyRatingToken,
    Engagement,
    PlatformActivityLog,
    PlatformEmployee,
    ServiceSubscription,
    WorkOrder,
    WorkOrderComment,
    WorkOrderDeliverable,
)
from platform_ops.services import (
    DailyRatingConflict,
    DailyRatingError,
    RatingTokenGone,
    RatingTokenNotFound,
    calculate_employee_ratings_summary,
    calculate_two_health_scores,
    generate_daily_rating_token,
    get_my_books_tab_data,
    has_employee_worked_on_date,
    resolve_daily_rating_token,
    submit_daily_rating,
    suspend_engagement,
    update_daily_rating,
)

User = get_user_model()


class DailyRatingsAndBooksTest(TestCase):
    """مجموعة اختبارات التقييم اليومي، تبويب من يمسك دفاتري، ودرجتي الصحة."""

    def setUp(self):
        # 1. شركات الاختبار
        self.tenant_a = Tenant.objects.create(
            TenantID=5001,
            CompanyName="شركة التجارة الأولى",
        )
        self.tenant_b = Tenant.objects.create(
            TenantID=5002,
            CompanyName="شركة المقاولات الثانية",
        )

        # 2. مستخدمو الاختبار
        self.owner_user_a = User.objects.create_user(
            username="owner_a",
            email="owner_a@example.com",
            first_name="مالك",
            last_name="الأولى",
        )
        UserCompanyMembership.objects.create(
            user=self.owner_user_a,
            tenant=self.tenant_a,
            role="manager",
        )

        self.agent_user = User.objects.create_user(
            username="agent_ops",
            email="agent@platform.test",
            first_name="أحمد",
            last_name="الوكيل",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.agent_user,
            specialty="accountant",
            status=PlatformEmployee.Status.ACTIVE,
        )

        # ارتباط نشط مع الشركة أ
        self.engagement_a = Engagement.objects.create(
            tenant=self.tenant_a,
            employee=self.employee,
            status=Engagement.Status.ACTIVE,
        )

        # عميل API
        self.client = APIClient()

        # تاريخ الخدمة
        self.service_date = timezone.localdate()

    def _record_work_for_employee(self, tenant, employee, date):
        """مساعد لتسجيل عمل فعلي للموظف في تاريخ معين."""
        now_on_date = timezone.make_aware(
            datetime.datetime.combine(date, datetime.time(10, 0, 0))
        )
        return WorkOrder.objects.create(
            tenant=tenant,
            assignee=employee,
            title="إدخال فواتير المشتريات",
            status=WorkOrder.Status.APPROVAL,
            approved_at=now_on_date,
            received_at=now_on_date,
        )

    # --------------------------------------------------------------------------
    # 1. التحقق من العمل الفعلي (no_work_on_date)
    # --------------------------------------------------------------------------
    def test_no_rating_without_actual_work_on_date(self):
        """منع تقييم يوم لم يعمل فيه الموظف بالشركة."""
        # في هذا اليوم لم يسجل أي عمل للموظف في الشركة أ
        self.assertFalse(has_employee_worked_on_date(self.tenant_a, self.employee, self.service_date))

        # محاولة إنشاء رابط يومي مهشر تفشل بـ DailyRatingError
        with self.assertRaises(DailyRatingError) as ctx:
            generate_daily_rating_token(
                tenant=self.tenant_a,
                employee=self.employee,
                service_date=self.service_date,
            )
        self.assertEqual(ctx.exception.code, "no_work_on_date")

        # محاولة إرسال تقييم مباشرة تفشل أيضاً
        with self.assertRaises(DailyRatingError) as ctx:
            submit_daily_rating(
                tenant=self.tenant_a,
                employee=self.employee,
                service_date=self.service_date,
                stars=5,
            )
        self.assertEqual(ctx.exception.code, "no_work_on_date")

        # الآن نسجل عملاً للموظف في الشركة أ في هذا اليوم
        self._record_work_for_employee(self.tenant_a, self.employee, self.service_date)
        self.assertTrue(has_employee_worked_on_date(self.tenant_a, self.employee, self.service_date))

        # الآن ينجح إنشاء الرابط وإرسال التقييم
        token_obj, raw_token = generate_daily_rating_token(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
        )
        self.assertIsNotNone(token_obj)
        self.assertTrue(raw_token)

    # --------------------------------------------------------------------------
    # 2. انتهاء صلاحية الرابط بعد 72 ساعة (token_expires_after_72h)
    # --------------------------------------------------------------------------
    def test_token_expires_after_72h_returns_410_gone(self):
        """ينتهي الرابط بعد 72 ساعة ويعيد 410 صريحة."""
        self._record_work_for_employee(self.tenant_a, self.employee, self.service_date)
        token_obj, raw_token = generate_daily_rating_token(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
        )

        # فحص الرابط العام وهو لا يزال صالحاً (GET)
        resp = self.client.get(f"/api/my-agent/ratings/public/{raw_token}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["company_name"], self.tenant_a.CompanyName)

        # تقديم وقت الانتهاء للماضي لمحاكاة مرور أكثر من 72 ساعة
        token_obj.expires_at = timezone.now() - datetime.timedelta(hours=1)
        token_obj.save(update_fields=["expires_at"])

        # استعلام الخدمة مباشرة يرفع RatingTokenGone
        with self.assertRaises(RatingTokenGone):
            resolve_daily_rating_token(raw_token)

        # استعلام نقطة النهاية العامة GET يعيد 410 GONE صريحة
        resp_get = self.client.get(f"/api/my-agent/ratings/public/{raw_token}/")
        self.assertEqual(resp_get.status_code, status.HTTP_410_GONE)
        self.assertIn("انتهت صلاحية", resp_get.data["detail"])

        # استعلام نقطة النهاية العامة POST يعيد 410 GONE صريحة
        resp_post = self.client.post(
            f"/api/my-agent/ratings/public/{raw_token}/",
            {"stars": 4, "note": "تقييم متأخر"},
        )
        self.assertEqual(resp_post.status_code, status.HTTP_410_GONE)

    # --------------------------------------------------------------------------
    # 3. السماح بالتعديل مرة واحدة ورفض التعديل الثاني (single_edit_allowed)
    # --------------------------------------------------------------------------
    def test_single_edit_allowed_second_edit_rejected(self):
        """يسمح بالتعديل مرة واحدة فقط وتُرفض المحاولة الثانية بـ 400."""
        self._record_work_for_employee(self.tenant_a, self.employee, self.service_date)

        # إنشاء التقييم الأولي (5 نجوم)
        rating = submit_daily_rating(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
            stars=5,
            note="عمل ممتاز",
        )
        self.assertFalse(rating.edited_once)
        self.assertEqual(rating.stars, 5)

        # التعديل الأول مسموح (تغيير إلى 4 نجوم)
        updated = update_daily_rating(
            rating_id=rating.pk,
            stars=4,
            note="تعديل ملاحظة أولى",
        )
        self.assertTrue(updated.edited_once)
        self.assertEqual(updated.stars, 4)

        # التعديل الثاني مرفوض بـ DailyRatingConflict
        with self.assertRaises(DailyRatingConflict) as ctx:
            update_daily_rating(
                rating_id=rating.pk,
                stars=3,
                note="تعديل ثان مرفوض",
            )
        self.assertEqual(ctx.exception.code, "already_edited")

        # فحص من خلال API داخل التطبيق (PUT/PATCH)
        self.client.force_authenticate(user=self.owner_user_a)
        resp_edit = self.client.patch(
            f"/api/my-agent/daily-ratings/{rating.pk}/",
            {"stars": 2, "note": "محاولة عبر API"},
        )
        self.assertEqual(resp_edit.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already_edited", str(resp_edit.data))

    # --------------------------------------------------------------------------
    # 4. عدم حفظ الرمز الخام في القاعدة إطلاقاً (raw_token_never_stored)
    # --------------------------------------------------------------------------
    def test_raw_token_never_stored_in_database(self):
        """الرمز الخام لا يحفظ في قاعدة البيانات أبداً، ويخزن فقط الـ SHA-256."""
        self._record_work_for_employee(self.tenant_a, self.employee, self.service_date)
        token_obj, raw_token = generate_daily_rating_token(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
        )

        token_obj.refresh_from_db()
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        self.assertEqual(token_obj.token_hash, expected_hash)
        self.assertNotEqual(token_obj.token_hash, raw_token)
        self.assertNotIn(raw_token, token_obj.token_hash)

        # التأكد من أن الرمز الخام لا يوجد في أي حقل نصي في جدول DailyRatingToken
        for field in DailyRatingToken._meta.fields:
            val = getattr(token_obj, field.name)
            if isinstance(val, str):
                self.assertNotIn(raw_token, val)

    # --------------------------------------------------------------------------
    # 5. عدم تسريب البيانات العامة (no_public_leakage)
    # --------------------------------------------------------------------------
    def test_no_public_leakage_in_public_endpoints(self):
        """الرابط العام يعيد فقط الحقول المسموحة في القائمة البيضاء."""
        self._record_work_for_employee(self.tenant_a, self.employee, self.service_date)
        _, raw_token = generate_daily_rating_token(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
        )

        client_anon = APIClient()
        resp = client_anon.get(f"/api/my-agent/ratings/public/{raw_token}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        allowed_keys = {
            "company_name",
            "employee_name",
            "service_date",
            "stars",
            "note",
            "already_rated",
            "can_rate",
            "can_edit",
        }
        self.assertEqual(set(resp.data.keys()), allowed_keys)

        # التأكد من عدم وجود أي معلومات حساسة
        leak_candidates = [
            "tenant_id",
            "employee_id",
            "token_hash",
            "email",
            "password",
            "database",
            "settings",
            "financial",
            "balance",
        ]
        # **على القيم لا المفاتيح**: `assertNotIn(x, dict)` يفحص المفاتيح، وسطرُ
        # تساوي مجموعة المفاتيح أعلاه يجعل الحلقةَ عاجزةً عن السقوط تحت أي تغيير.
        rendered = str(resp.data)
        for candidate in leak_candidates:
            self.assertNotIn(candidate, rendered)

        # تجربة تقديم تقييم ناجح عبر الرابط العام
        post_resp = client_anon.post(
            f"/api/my-agent/ratings/public/{raw_token}/",
            {"stars": 5, "note": "تقييم عام ممتاز"},
        )
        self.assertEqual(post_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(set(post_resp.data.keys()), allowed_keys)
        self.assertEqual(post_resp.data["stars"], 5)
        self.assertTrue(post_resp.data["already_rated"])

    # --------------------------------------------------------------------------
    # 6. الخانق ClientIpScopedThrottle بربط REMOTE_ADDR
    # --------------------------------------------------------------------------
    def test_client_ip_scoped_throttle_active_on_public_view(self):
        """التحقق من تفعيل الخانق ClientIpScopedThrottle بربط REMOTE_ADDR."""
        from platform_ops.throttles import ClientIpScopedThrottle
        from platform_ops.views import PublicDailyRatingView

        self.assertIn(ClientIpScopedThrottle, PublicDailyRatingView.throttle_classes)
        self.assertEqual(PublicDailyRatingView.throttle_scope, "platform_ops_public_rating")

        # فحص منطق get_ident في ClientIpScopedThrottle
        throttle = ClientIpScopedThrottle()
        from django.test import RequestFactory
        factory = RequestFactory()
        req = factory.get("/api/my-agent/ratings/public/test/", REMOTE_ADDR="198.51.100.42")
        ident = throttle.get_ident(req)
        self.assertEqual(ident, "198.51.100.42")

    # --------------------------------------------------------------------------
    # 7. استبعاد view و login من سجل النشاط وإظهار التغيير المالي (who_manages_my_books)
    # --------------------------------------------------------------------------
    def test_who_manages_my_books_excludes_view_and_login_and_shows_diff(self):
        """تبويب من يمسك دفاتري يستبعد view و login ويظهر التغيير المالي من ماذا إلى ماذا."""
        # تسجيل أنشطة مختلفة في ActivityLog
        # 1. نشاط استعراض view (يجب استبعاده)
        ActivityLog.objects.create(
            tenant=self.tenant_a,
            user=self.agent_user,
            action="view",
            entity_type="sales_invoice",
            entity_label="فاتورة #100",
            description="عرض فاتورة",
        )
        # 2. نشاط دخول login (يجب استبعاده)
        ActivityLog.objects.create(
            tenant=self.tenant_a,
            user=self.agent_user,
            action="login",
            entity_type="user",
            description="تسجيل دخول",
        )
        # 3. نشاط مالي مع تغيير صريح (يجب ظهوره بصيغة من ماذا إلى ماذا)
        ActivityLog.objects.create(
            tenant=self.tenant_a,
            user=self.agent_user,
            action="update",
            entity_type="sales_invoice",
            entity_label="فاتورة #101",
            metadata={"old_total": "100.00", "new_total": "250.00"},
            description="تعديل فاتورة مبيعات",
        )
        # 4. نشاط في شركة أخرى tenant_b (يجب ألا يظهر في شركة tenant_a)
        ActivityLog.objects.create(
            tenant=self.tenant_b,
            user=self.agent_user,
            action="create",
            entity_type="sales_invoice",
            entity_label="فاتورة سرية في ب",
            description="فاتورة شركة أخرى",
        )

        # استعلام بيانات تبويب دفاتري
        data = get_my_books_tab_data(self.tenant_a)
        activities = data["activity_log"]

        # يجب أن نجد فقط النشاط رقم 3
        self.assertEqual(len(activities), 1)
        act = activities[0]
        self.assertEqual(act["action"], "update")
        self.assertIn("تغيير الإجمالي من 100.00 إلى 250.00", act["description"])

        # التأكد من استبعاد view و login وسجلات الشركات الأخرى
        for item in activities:
            self.assertNotEqual(item["action"], "view")
            self.assertNotEqual(item["action"], "login")
            self.assertNotIn("فاتورة سرية", item["description"])

    # --------------------------------------------------------------------------
    # 8. عزل الشركات ورفض وسائط الشركات الممنوعة بـ 400 (tenant_isolation)
    # --------------------------------------------------------------------------
    def test_tenant_isolation_and_cross_tenant_params_rejected(self):
        """رفض وسائط الشركات الصريحة بـ 400 وعزل الشركة عند الاستعلام."""
        self.client.force_authenticate(user=self.owner_user_a)

        # تجربة تمرير tenant_id صريح في query_params
        resp_q = self.client.get(f"/api/my-agent/?tenant_id={self.tenant_b.pk}")
        self.assertEqual(resp_q.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp_q.data.get("code"), "cross_tenant_query_disallowed_from_request")

        # تجربة تمرير company في query_params لـ daily-ratings
        resp_dr = self.client.get(f"/api/my-agent/daily-ratings/?company={self.tenant_b.pk}")
        self.assertEqual(resp_dr.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp_dr.data.get("code"), "cross_tenant_query_disallowed_from_request")

        # استعلام طبيعي لتبويب my-agent يعيد بيانات شركة المستخدم (tenant_a) فقط
        resp_ok = self.client.get("/api/my-agent/")
        self.assertEqual(resp_ok.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_ok.data["tenant_id"], self.tenant_a.pk)

    # --------------------------------------------------------------------------
    # 9. اشتقاق الوكيل حصراً من Engagement النشط لا من جدول العضويات
    # --------------------------------------------------------------------------
    def test_agent_derived_strictly_from_engagement_not_memberships(self):
        """اشتقاق الوكيل حصراً من صف Engagement النشط."""
        # إضافة مستخدم كمدير آخر في جدول العضويات
        other_manager = User.objects.create_user(
            username="other_mgr",
            email="other_mgr@test.local",
            first_name="مدير",
            last_name="محلي",
        )
        UserCompanyMembership.objects.create(
            user=other_manager,
            tenant=self.tenant_a,
            role="manager",
        )

        data = get_my_books_tab_data(self.tenant_a)
        agent = data["agent"]
        self.assertIsNotNone(agent)
        # الوكيل هو موظف المنصة المرتبط بـ Engagement حصراً
        self.assertEqual(agent["user_id"], self.agent_user.pk)
        self.assertEqual(agent["username"], self.agent_user.username)
        self.assertIn("مدير النظام والعمليات", agent["role_title"])
        self.assertIn("يعمل وكيل المنصة بصلاحية مدير كاملة", agent["authority_notice"])

        # إلغاء أو تعليق الارتباط
        suspend_engagement(engagement=self.engagement_a, reason="تعليق تجريبي")

        # بعد التعليق، لا يوجد وكيل نشط
        data_after = get_my_books_tab_data(self.tenant_a)
        self.assertIsNone(data_after["agent"])
        self.assertFalse(data_after["can_suspend"])

    # --------------------------------------------------------------------------
    # 10. فصل درجتي الصحة وعدم تأثرهما بالباقة (two_health_scores_strictly_separated)
    # --------------------------------------------------------------------------
    def test_two_health_scores_strictly_separated_and_independent_of_quota(self):
        """فصل صحة الخدمة عن تعاون الزبون، واستبعاد استهلاك الباقة تماماً."""
        # 1. حالة بداية مثالية: الدرجتان 100
        initial = calculate_two_health_scores(self.tenant_a)
        self.assertEqual(initial["service_health"]["score"], 100)
        self.assertEqual(initial["customer_cooperation"]["score"], 100)
        self.assertEqual(initial["service_health"]["status"], "excellent")
        self.assertEqual(initial["customer_cooperation"]["status"], "excellent")

        # 2. تقصير من المنصة: تجاوزُ أجل. يخصم من صحة الخدمة وحدها.
        past_deadline = timezone.now() - datetime.timedelta(days=2)
        WorkOrder.objects.create(
            tenant=self.tenant_a,
            assignee=self.employee,
            title="أمر متأخر جداً",
            status=WorkOrder.Status.DATA_ENTRY,
            deadline_at=past_deadline,
        )

        after_service_fault = calculate_two_health_scores(self.tenant_a)
        self.assertEqual(after_service_fault["service_health"]["score"], 85)
        self.assertEqual(after_service_fault["service_health"]["status"], "good")
        self.assertTrue(any("علينا:" in r for r in after_service_fault["service_health"]["top_reasons"]))
        self.assertEqual(after_service_fault["customer_cooperation"]["score"], 100)

        # 3. الإلغاء **رقمٌ تشخيصيٌّ لا عقوبةٌ آليّة** (المواصفة §٨).
        WorkOrder.objects.create(
            tenant=self.tenant_a,
            assignee=self.employee,
            title="أمر تم إلغاؤه",
            status=WorkOrder.Status.CANCELLED,
            cancelled_at=timezone.now(),
        )
        after_cancel = calculate_two_health_scores(self.tenant_a)
        self.assertEqual(
            after_cancel["service_health"]["score"], 85,
            "الإلغاءُ خصم من الدرجة، والمواصفة تنصّ أنّه لا يعاقب آليّاً",
        )
        self.assertEqual(after_cancel["rework_diagnostic"]["cancelled_work_orders"], 1)
        self.assertFalse(after_cancel["rework_diagnostic"]["counts_against_score"])

        # 4. تقصير من الزبون (أمر عمل بانتظار العميل) — لا يمسّ صحة الخدمة.
        WorkOrder.objects.create(
            tenant=self.tenant_a,
            assignee=self.employee,
            title="أمر بانتظار العميل",
            status=WorkOrder.Status.WAITING_CUSTOMER,
        )

        after_customer_delay = calculate_two_health_scores(self.tenant_a)
        self.assertEqual(after_customer_delay["customer_cooperation"]["score"], 85)
        self.assertTrue(any("بانتظار الزبون:" in r for r in after_customer_delay["customer_cooperation"]["top_reasons"]))
        # **على المتغيّر الصحيح**: كان التأكيدُ يقرأ لقطةً حُسبت قبل إنشاء أمرِ
        # الانتظار وأُكّدت 75 أصلاً — فنصفُ «الفصلِ الصارم» لم يكن مُختبَراً إطلاقاً.
        self.assertEqual(
            after_customer_delay["service_health"]["score"], 85,
            "تقصيرُ الزبون خصم من صحّة الخدمة — والدرجتان لا تختلطان",
        )

        # 5. تقييمٌ منخفضٌ **منفرد** لا يُعاقَب عليه (المواصفة §١٠).
        self._record_work_for_employee(self.tenant_a, self.employee, self.service_date)
        submit_daily_rating(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
            stars=1,
        )
        after_one_low = calculate_two_health_scores(self.tenant_a)
        self.assertEqual(
            after_one_low["service_health"]["score"], 85,
            "تقييمٌ منفردٌ خصم من الدرجة قبل بلوغ حدّ العيّنة",
        )
        self.assertFalse(after_one_low["ratings_sample"]["counts_against_score"])

        # 6. تغيير استهلاك الباقة أو الاشتراك لا يؤثر على أي من الدرجتين نهائياً
        ServiceSubscription.objects.create(
            tenant=self.tenant_a,
            included_quota=10,
            consumed_quota=50,  # تجاوز الباقة بشكل كبير
            status=ServiceSubscription.Status.ACTIVE,
        )
        after_quota = calculate_two_health_scores(self.tenant_a)
        self.assertEqual(after_quota["service_health"]["score"], 85)
        self.assertEqual(after_quota["customer_cooperation"]["score"], 85)

    # --------------------------------------------------------------------------
    # 11. اتساع أعمدة Choices (choice_column_max_length)
    # --------------------------------------------------------------------------
    def test_choice_column_max_length(self):
        """التحقق من أن max_length يتسع لأطول مفتاح في choices."""
        field = DailyRating._meta.get_field("source")
        max_choice_len = max(len(choice[0]) for choice in DailyRating.Source.choices)
        self.assertLessEqual(
            max_choice_len,
            field.max_length,
            f"max_length ({field.max_length}) أقل من أطول قيمة في Source ({max_choice_len})",
        )

    # --------------------------------------------------------------------------
    # 12. ملخص تقييمات الموظف وحد العينة (sample size threshold)
    # --------------------------------------------------------------------------
    def test_employee_ratings_summary_sample_size_threshold(self):
        """عتبة حجم العينة الأدنى لحساب متوسط التقييم."""
        self._record_work_for_employee(self.tenant_a, self.employee, self.service_date)

        # تقييم واحد فقط (أقل من min_sample_size=5)
        submit_daily_rating(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
            stars=5,
        )

        summary = calculate_employee_ratings_summary(
            employee=self.employee,
            min_sample_size=5,
        )
        self.assertEqual(summary["status"], "insufficient_data")
        self.assertIsNone(summary["average_stars"])
        self.assertEqual(summary["sample_size"], 1)

        # إذا طلبنا min_sample_size=1 يصبح كافياً
        summary_one = calculate_employee_ratings_summary(
            employee=self.employee,
            min_sample_size=1,
        )
        self.assertEqual(summary_one["status"], "sufficient_data")
        self.assertEqual(summary_one["average_stars"], 5.0)

    # --------------------------------------------------------------------------
    # 13. تعليق وصول الوكيل من قبل صاحب الشركة (suspend)
    # --------------------------------------------------------------------------
    def test_owner_can_suspend_agent_via_api(self):
        """لصاحب الشركة تعليق وصول الوكيل عبر POST /api/my-agent/suspend/."""
        self.client.force_authenticate(user=self.owner_user_a)
        resp = self.client.post(
            "/api/my-agent/suspend/",
            {"reason": "طلب المالك تعليق مؤقت"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("تم تعليق وصول الوكيل", resp.data["detail"])

        self.engagement_a.refresh_from_db()
        self.assertEqual(self.engagement_a.status, Engagement.Status.SUSPENDED)


class DailyRatingsReviewFixesTest(TestCase):
    """عيوبٌ وُجدت في مراجعة م٧ سطراً سطراً — كلُّ تأكيدٍ هنا أُثبت سقوطُه قبل إصلاحه.

    العزلُ المكتوبُ باليد، وتعديلُ المُقاسِ لمقياسه، وعقدُ الخطأ، و`PATCH` المكسور،
    والعدُّ الكاذب، واستعلامٌ لكلِّ صفّ، وخانقٌ يُفحص تركيبُه لا منعُه.
    """

    def setUp(self):
        self.tenant_a = Tenant.objects.create(TenantID=6001, CompanyName="شركة المراجعة أ")
        self.tenant_b = Tenant.objects.create(TenantID=6002, CompanyName="شركة المراجعة ب")

        self.owner = User.objects.create_user(username="rev_owner", email="rev_owner@t.local")
        UserCompanyMembership.objects.create(user=self.owner, tenant=self.tenant_a, role="manager")

        # عضوٌ عاديٌّ في الشركة نفسها — ليس صاحبها.
        self.viewer = User.objects.create_user(username="rev_viewer", email="rev_viewer@t.local")
        UserCompanyMembership.objects.create(user=self.viewer, tenant=self.tenant_a, role="viewer")

        self.agent_user = User.objects.create_user(username="rev_agent", email="rev_agent@p.local")
        self.employee = PlatformEmployee.objects.create(
            user=self.agent_user,
            specialty="accountant",
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.engagement = Engagement.objects.create(
            tenant=self.tenant_a,
            employee=self.employee,
            status=Engagement.Status.ACTIVE,
        )
        self.service_date = timezone.localdate()
        self.client = APIClient()

    def _work(self):
        now_on_date = timezone.make_aware(
            datetime.datetime.combine(self.service_date, datetime.time(10, 0, 0))
        )
        return WorkOrder.objects.create(
            tenant=self.tenant_a,
            assignee=self.employee,
            title="عملٌ فعليٌّ في اليوم",
            status=WorkOrder.Status.APPROVAL,
            approved_at=now_on_date,
            received_at=now_on_date,
        )

    def _rating(self, stars=5):
        self._work()
        return submit_daily_rating(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
            stars=stars,
            note="شهادةُ الزبون",
        )

    # -- ع١: المُقاسُ لا يعدّل مقياسه ولا يمحوه ------------------------------
    def test_rated_employee_cannot_edit_own_rating(self):
        """موظّفُ المنصّة كان يرى تقييمَه في `get_queryset` فيستطيع تعديلَه.

        نجمةٌ واحدةٌ تصير خمساً بطلبٍ واحد — وهي عينُ ثغرةِ م٥ في ثوبٍ جديد.
        """
        rating = self._rating(stars=1)
        self.client.force_authenticate(user=self.agent_user)
        resp = self.client.patch(
            f"/api/my-agent/daily-ratings/{rating.pk}/",
            {"stars": 5, "note": "رفعتُ تقييمي بنفسي"},
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        rating.refresh_from_db()
        self.assertEqual(rating.stars, 1)
        self.assertFalse(rating.edited_once)

    def test_daily_rating_can_never_be_deleted(self):
        """`ModelViewSet` كان يفتح الحذفَ بلا حارسٍ إطلاقاً — والمُقاسُ يرى صفَّه."""
        rating = self._rating(stars=1)
        for actor in (self.agent_user, self.owner):
            self.client.force_authenticate(user=actor)
            resp = self.client.delete(f"/api/my-agent/daily-ratings/{rating.pk}/")
            self.assertEqual(
                resp.status_code,
                status.HTTP_405_METHOD_NOT_ALLOWED,
                f"{actor.username} استطاع حذفَ التقييم: {resp.status_code}",
            )
        self.assertTrue(DailyRating.objects.filter(pk=rating.pk).exists())

    # -- ع٢: العزلُ عبر المصدر الواحد لا باليد -------------------------------
    def test_header_naming_a_foreign_tenant_is_denied_not_swapped(self):
        """الترويسةُ التي تسمّي شركةً لا عضويّةَ لك فيها كانت تُتجاهَل بصمت.

        فيسقط الطلبُ على «أوّلِ عضويّةٍ يعيدها المحرّك» ويردّ 200 ببياناتِ شركةٍ
        أخرى غير التي طُلبت — ردٌّ صحيحُ الشكل عن سؤالٍ لم يُطرَح.
        """
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(
            "/api/my-agent/",
            HTTP_X_TENANT_ID=str(self.tenant_b.pk),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

    def test_malformed_tenant_header_is_denied_not_a_crash(self):
        """`filter(tenant_id="abc")` كان يرفع `ValueError` — أي 500 لا 403."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/my-agent/", HTTP_X_TENANT_ID="abc")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)

    # -- ع٣: التعليقُ لصاحب الشركة وحدَه --------------------------------------
    def test_ordinary_member_cannot_suspend_the_agent(self):
        """أيُّ عضوٍ — ولو `viewer` — كان يقطع وصولَ الوكيل بطلبٍ واحد."""
        self.client.force_authenticate(user=self.viewer)
        resp = self.client.post("/api/my-agent/suspend/", {"reason": "بلا صفة"})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.data)
        self.engagement.refresh_from_db()
        self.assertEqual(self.engagement.status, Engagement.Status.ACTIVE)

    # -- ع٤: عقدُ الخطأ يحمل الرمزَ وحالتَه ----------------------------------
    def test_service_error_response_carries_code_and_its_own_status(self):
        """الردُّ كان يحمل النصَّ وحدَه بحالةٍ مثبَّتةٍ 400 — فيضيع رمزُ الخطأ."""
        rating = self._rating()
        update_daily_rating(rating_id=rating.pk, stars=4, note="التعديلُ الوحيد")

        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(
            f"/api/my-agent/daily-ratings/{rating.pk}/",
            {"stars": 2, "note": "محاولةٌ ثانية"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get("code"), "already_edited")

    # -- ع٥: تعديلُ الملاحظةِ وحدَها -----------------------------------------
    def test_patching_only_the_note_is_accepted_and_keeps_the_stars(self):
        """`stars` كانت إلزاميّةً حتى في `PATCH`، و`partial` يُلتقَط ثمّ يُهمَل."""
        rating = self._rating(stars=4)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.patch(
            f"/api/my-agent/daily-ratings/{rating.pk}/",
            {"note": "تصحيحُ الملاحظةِ وحدَها"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        rating.refresh_from_db()
        self.assertEqual(rating.stars, 4)
        self.assertEqual(rating.note, "تصحيحُ الملاحظةِ وحدَها")

    # -- ع٦ وع٧: عددٌ صادقٌ واستعلامٌ محدود ----------------------------------
    def test_total_activities_count_is_the_real_total_not_the_page_cap(self):
        """كان العددُ `len` بعد القصّ — فيتجمّد على السقف ويكذب أبداً."""
        from platform_ops.services import MY_BOOKS_ACTIVITY_PAGE_CAP

        extra = 5
        for i in range(MY_BOOKS_ACTIVITY_PAGE_CAP + extra):
            ActivityLog.objects.create(
                tenant=self.tenant_a,
                user=self.agent_user,
                action="update",
                entity_type="sales_invoice",
                entity_label=f"فاتورة #{i}",
                description="تعديل فاتورة",
            )

        data = get_my_books_tab_data(self.tenant_a)
        self.assertEqual(len(data["activity_log"]), MY_BOOKS_ACTIVITY_PAGE_CAP)
        self.assertEqual(data["total_activities_count"], MY_BOOKS_ACTIVITY_PAGE_CAP + extra)

    def test_activity_log_does_not_query_once_per_row(self):
        """الحلقةُ تقرأ صاحبَ كلِّ صفّ — وبلا `select_related` صارت ٣٠ استعلاماً."""
        rows = 30
        for i in range(rows):
            ActivityLog.objects.create(
                tenant=self.tenant_a,
                user=self.agent_user,
                action="update",
                entity_type="sales_invoice",
                entity_label=f"فاتورة #{i}",
                description="تعديل فاتورة",
            )

        with CaptureQueriesContext(connection) as ctx:
            data = get_my_books_tab_data(self.tenant_a)

        self.assertEqual(len(data["activity_log"]), rows)
        self.assertLess(
            len(ctx.captured_queries),
            rows,
            f"استعلامٌ لكلّ صفّ: {len(ctx.captured_queries)} استعلاماً لـ{rows} صفّاً",
        )

    # -- ع١٠: الخانقُ يُختبَر بالمنع لا بفحصِ التركيب -------------------------
    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    )
    def test_public_rating_link_ignores_a_forged_forwarded_for(self):
        """كان الاختبارُ يتحقّق أنّ الصنفَ مذكورٌ في `throttle_classes` فقط.

        وذلك يثبت التركيبَ لا المنعَ. هنا ثلاثةُ طلباتٍ بترويسةٍ مزوَّرةٍ مختلفةٍ
        في كلّ مرّة، والثالثُ يجب أن يُردّ بـ429.
        """
        from unittest import mock

        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle

        cache.clear()
        self._work()
        _, raw_token = generate_daily_rating_token(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
        )
        path = f"/api/my-agent/ratings/public/{raw_token}/"
        anon = APIClient()

        with mock.patch.dict(
            ScopedRateThrottle.THROTTLE_RATES, {"platform_ops_public_rating": "2/hour"}
        ):
            codes = [
                anon.get(path, HTTP_X_FORWARDED_FOR=f"10.0.0.{i}").status_code
                for i in range(3)
            ]

        self.assertEqual(codes[:2], [200, 200], codes)
        self.assertEqual(codes[2], 429, "تزويرُ الترويسة اشترى دلواً جديداً للرابط العام")

    # -- ع٨: اسمُ المستند بمعجمِ الشركة لا حرفياً ----------------------------
    def test_activity_description_uses_the_company_own_document_vocabulary(self):
        """كان «فاتورة مبيعات» مكتوباً حرفياً في جدولِ الأسماء.

        فمكتبُ المحاسبة — الذي يسمّيها «فاتورة أتعاب» — كان يقرأ في سجلّ وكيله
        معجمَ شركةٍ غيرِه. وهذا ما يحرسه `core/tests/test_terminology_guard.py`.
        """
        firm = Tenant.objects.create(
            TenantID=6003, CompanyName="مكتب المحاسبة", template="accounting_firm",
        )
        Engagement.objects.create(
            tenant=firm, employee=self.employee, status=Engagement.Status.ACTIVE,
        )
        ActivityLog.objects.create(
            tenant=firm,
            user=self.agent_user,
            action="update",
            entity_type="sales_invoice",
            entity_label="#77",
            # بلا وصفٍ مخزَّن: هذا هو الفرعُ الذي يُركَّب فيه الاسمُ من المعجم.
            description="",
        )

        desc = get_my_books_tab_data(firm)["activity_log"][0]["description"]
        self.assertIn("فاتورة أتعاب", desc)
        self.assertNotIn("فاتورة مبيعات", desc)

    # -- ع٩: سطحُ الزبون خارج جذرِ السوبر أدمن -------------------------------
    def test_tenant_facing_routes_are_not_under_the_super_admin_root(self):
        """كانت نقاطُ م٧ السبعُ تحت `/api/platform/` — جذرٌ عقدُه أن لا أحدَ
        دون السوبر أدمن يقرأ نقطةً تحته، وفيها رابطٌ يُفتح **بلا دخولٍ أصلاً**.

        يحرس ذلك عموماً `core/tests/test_platform_admin.py::PlatformRouteGuardTest`،
        وهنا التأكيدُ الموجب: النقاطُ حيّةٌ في موضعها الجديد.
        """
        from django.urls import get_resolver

        def walk(patterns, prefix=""):
            for entry in patterns:
                route = prefix + str(entry.pattern)
                if hasattr(entry, "url_patterns"):
                    yield from walk(entry.url_patterns, route)
                else:
                    yield route

        platform_routes = [
            r for r in walk(get_resolver().url_patterns) if r.startswith("api/platform/")
        ]
        for needle in ("daily-ratings", "my-agent", "ratings/public"):
            self.assertFalse(
                [r for r in platform_routes if needle in r],
                f"«{needle}» ما زالت تحت جذر السوبر أدمن",
            )

        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.get("/api/my-agent/").status_code, status.HTTP_200_OK)

    # -- ك: عقدُ م٦ باقٍ — `company` تضييقٌ لا وسيطُ شركة --------------------
    def test_m6_company_drilldown_still_answers_and_is_not_rejected(self):
        """م٧ أضافت `company` إلى تُرسانة الرفض المشتركة، و`WorkOrderViewSet`
        يقرؤها بعد أسطرٍ من فحصِ تلك التُّرسانة — فصار كلُّ نقرِ بطاقةِ شركةٍ
        في لوحة م٦ يردّ 400 والفرعُ الذي يقرؤها ميّتاً. والواجهةُ ترسلها فعلاً
        (`platformOpsApi.ts`)، ولا اختبارَ كان يغطّيها.
        """
        root = User.objects.create_superuser(
            username="rev_root", email="rev_root@k.local", password="x",
        )
        WorkOrder.objects.create(
            tenant=self.tenant_a, assignee=self.employee, title="أمرٌ في أ",
            status=WorkOrder.Status.DATA_ENTRY,
        )
        WorkOrder.objects.create(
            tenant=self.tenant_b, assignee=self.employee, title="أمرٌ في ب",
            status=WorkOrder.Status.DATA_ENTRY,
        )
        self.client.force_authenticate(user=root)

        resp = self.client.get(f"/api/platform/ops/work-orders/?company={self.tenant_a.pk}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        rows = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        self.assertEqual([r["tenant"] for r in rows], [self.tenant_a.pk])

        # وتسميةُ الشركة صراحةً تبقى مرفوضة كما كانت.
        denied = self.client.get(f"/api/platform/ops/work-orders/?tenant={self.tenant_a.pk}")
        self.assertEqual(denied.status_code, status.HTTP_400_BAD_REQUEST)

    # -- أ: الرابطُ العامُّ لا يمحو تقييمَ صاحب الشركة ----------------------
    def test_public_link_sees_an_existing_in_app_rating_and_does_not_overwrite_it(self):
        """كان الرابطُ يقرأ `token.rating` وهو يُولَّد فارغاً دائماً.

        فصاحبُ الشركة يقيّم ٥ من داخل التطبيق، ثمّ يُفتح الرابطُ فيُقال له «لم
        يُقيَّم بعد»، فيُرسل ١ — فتُمحى الخمسُ **ويُحرق** حقُّ التعديل الوحيد.
        """
        # **الترتيبُ هو الفخّ**: الرابطُ يُسَكّ صباحاً (فـ`token.rating` فارغ)، ثمّ
        # يقيّم صاحبُ الشركة من داخل التطبيق نهاراً، ثمّ يُفتح الرابط.
        self._work()
        _, raw_token = generate_daily_rating_token(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
        )
        rating = submit_daily_rating(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
            stars=5,
            note="شهادةُ الزبون",
        )
        anon = APIClient()
        path = f"/api/my-agent/ratings/public/{raw_token}/"

        seen = anon.get(path)
        self.assertEqual(seen.status_code, status.HTTP_200_OK)
        self.assertTrue(seen.data["already_rated"], seen.data)
        self.assertEqual(seen.data["stars"], 5)
        self.assertFalse(seen.data["can_rate"])

        rating.refresh_from_db()
        self.assertEqual(rating.stars, 5)
        self.assertFalse(rating.edited_once)

    # -- ب: الرابطُ المُسلَّم يصل فعلاً ---------------------------------------
    def test_generate_link_returns_a_url_that_actually_resolves(self):
        """كان يُسلِّم `/api/platform/ops/ratings/public/…` وهو 404 بعد نقل المسار،
        ويشير إلى جذر السوبر أدمن الذي نُقلت منه عمداً. ولا اختبارَ كان يقرأ الحقل.
        """
        self._work()
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            "/api/my-agent/daily-ratings/generate-link/",
            {"employee_id": self.employee.pk, "service_date": self.service_date.isoformat()},
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        public_url = resp.data["public_url"]
        self.assertNotIn("/api/platform/", public_url)
        self.assertEqual(APIClient().get(public_url).status_code, status.HTTP_200_OK, public_url)

    # -- ت: عمرُ الرابط ٧٢ ساعةً مقيسٌ لا مفترَض ----------------------------
    def test_token_lifetime_is_actually_seventy_two_hours(self):
        """اختبارُ الانتهاء كان يقدّم `expires_at` بيده ثمّ يؤكّد 410 — فيمرّ
        بالضبط كما هو لو كان العمرُ خمسَ دقائقَ أو عشرَ سنوات. والمواصفة تسمّي
        «الرابطُ ينتهي بعد ٧٢ ساعة» اختباراً إلزاميّاً بالاسم.
        """
        from platform_ops.services import RATING_TOKEN_LIFETIME

        self._work()
        token_obj, _ = generate_daily_rating_token(
            tenant=self.tenant_a,
            employee=self.employee,
            service_date=self.service_date,
        )
        self.assertEqual(RATING_TOKEN_LIFETIME, datetime.timedelta(hours=72))
        lifetime = token_obj.expires_at - token_obj.created_at
        self.assertAlmostEqual(lifetime.total_seconds(), 72 * 3600, delta=30)

    # -- ز: رمزٌ جديدٌ يُبطل سابقَه، والمُبطَل يردّ 410 ----------------------
    def test_issuing_a_new_link_revokes_the_previous_one_for_the_same_day(self):
        """`revoked_at` و`is_revoked` كانا حقلاً وخاصّيّةً **بلا كاتبٍ واحد**،
        وتوثيقُ العرض يَعِد بـ«410 للرمز المُبطَل» — وعدٌ لا يستطيع التحقّق.
        ورابطان حيّان لليوم نفسِه نافذتا كتابةٍ على شهادةٍ واحدة.
        """
        self._work()
        old_token, old_raw = generate_daily_rating_token(
            tenant=self.tenant_a, employee=self.employee, service_date=self.service_date,
        )
        _, new_raw = generate_daily_rating_token(
            tenant=self.tenant_a, employee=self.employee, service_date=self.service_date,
        )

        old_token.refresh_from_db()
        self.assertIsNotNone(old_token.revoked_at)
        self.assertTrue(old_token.is_revoked)
        self.assertFalse(old_token.is_live)

        anon = APIClient()
        self.assertEqual(
            anon.get(f"/api/my-agent/ratings/public/{old_raw}/").status_code,
            status.HTTP_410_GONE,
        )
        self.assertEqual(
            anon.get(f"/api/my-agent/ratings/public/{new_raw}/").status_code,
            status.HTTP_200_OK,
        )

    # -- ج: عضوٌ عاديٌّ لا يكتب الشهادةَ ولا يسكّ رابطَها --------------------
    def test_ordinary_member_can_neither_rewrite_the_rating_nor_mint_a_link(self):
        """البوّابةُ وُضعت على الإنشاء والتعليق ونُسيت على التعديل والتوليد.

        فـ`viewer` لا يستطيع إنشاءَ الشهادة لكنّه يعيد كتابتها، ويسكّ رمزاً
        يفتح سطحاً **بلا مصادقة** يكشف اسمَ الشركة واسمَ الموظف.
        """
        rating = self._rating(stars=5)
        self.client.force_authenticate(user=self.viewer)

        patched = self.client.patch(
            f"/api/my-agent/daily-ratings/{rating.pk}/",
            {"stars": 1, "note": "أعدتُ كتابةَ شهادةِ غيري"},
        )
        self.assertEqual(patched.status_code, status.HTTP_403_FORBIDDEN, patched.data)
        rating.refresh_from_db()
        self.assertEqual(rating.stars, 5)
        self.assertFalse(rating.edited_once)

        minted = self.client.post(
            "/api/my-agent/daily-ratings/generate-link/",
            {"employee_id": self.employee.pk, "service_date": self.service_date.isoformat()},
        )
        self.assertEqual(minted.status_code, status.HTTP_403_FORBIDDEN, minted.data)

    def test_ordinary_member_cannot_open_the_books_tab(self):
        """التبويبُ يعرض نشاطَ الوكيل الماليَّ ودرجتَي الصحّة، وقصصُ المواصفة
        ٤٩–٥٥ كلُّها «كصاحب شركة» — وكان مفتوحاً لأيّ عضو.
        """
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(
            self.client.get("/api/my-agent/").status_code, status.HTTP_403_FORBIDDEN,
        )

    # -- د: وسيطٌ غيرُ رقميٍّ = 400 لا 500 -----------------------------------
    def test_summary_with_a_non_numeric_employee_id_is_a_bad_request_not_a_crash(self):
        """`PlatformEmployee.objects.get(pk="abc")` يرفع `ValueError` لا
        `DoesNotExist`، والمعالجُ يلتقط الثانيَ وحدَه — فالوسيطُ يُسقط 500.
        """
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/my-agent/daily-ratings/summary/?employee_id=abc")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)

    # -- هـ: اصطدامُ إنشاءين متزامنين تعارضٌ لا 500 --------------------------
    def test_losing_the_create_race_raises_a_conflict_not_an_integrity_error(self):
        """`select_for_update` على صفٍّ غيرِ موجودٍ لا يقفل شيئاً، فإرسالان
        متزامنان لليوم نفسِه يمرّان معاً ويصطدمان بالقيد. الملفُّ نفسُه يشرح
        هذا في `generate_integration_key` ويترجم الاصطدام — وهنا لم يُترجَم.

        نُحاكي خسارةَ السباق بإخفاء الصفِّ القائم عن بحثِ القفل وحدَه.
        """
        from unittest import mock

        rating = self._rating(stars=5)
        self.assertTrue(DailyRating.objects.filter(pk=rating.pk).exists())

        class _Blind:
            def filter(self, *a, **kw):
                return DailyRating.objects.none()

        with mock.patch.object(
            type(DailyRating.objects), "select_for_update", lambda self: _Blind()
        ):
            with self.assertRaises(DailyRatingConflict) as ctx:
                submit_daily_rating(
                    tenant=self.tenant_a,
                    employee=self.employee,
                    service_date=self.service_date,
                    stars=3,
                )
        self.assertEqual(ctx.exception.code, "already_rated")
        self.assertEqual(ctx.exception.status_code, 409)
        # ولم يُنشأ صفٌّ ثانٍ: القيدُ في القاعدة هو الحارس، والخدمةُ ترجمت اصطدامَه.
        self.assertEqual(DailyRating.objects.filter(tenant=self.tenant_a).count(), 1)

    # -- ع: ما يختمه الزبونُ بنفسه ليس «عملاً فعليّاً» ----------------------
    def test_customer_submitted_work_order_does_not_manufacture_a_ratable_day(self):
        """`received_at` يُختم لحظةَ إرسالِ الزبون عبر القناة (م٤)، وكان يُقبَل
        دليلَ عملٍ — فرفعُ الزبونِ مستنداً يصنع يومَ عملٍ لموظّفٍ لم يلمس شيئاً،
        والمواصفة تشترط «عملٌ فعليٌّ ذلك اليوم».
        """
        stamp = timezone.make_aware(
            datetime.datetime.combine(self.service_date, datetime.time(9, 0, 0))
        )
        WorkOrder.objects.create(
            tenant=self.tenant_a,
            assignee=self.employee,
            title="ما رفعه الزبون بنفسه",
            status=WorkOrder.Status.RECEIVED,
            received_at=stamp,
        )
        self.assertFalse(
            has_employee_worked_on_date(self.tenant_a, self.employee, self.service_date)
        )

        with self.assertRaises(DailyRatingError) as ctx:
            submit_daily_rating(
                tenant=self.tenant_a,
                employee=self.employee,
                service_date=self.service_date,
                stars=5,
            )
        self.assertEqual(ctx.exception.code, "no_work_on_date")

    # -- ص: التغييرُ الماليُّ يُقرأ من الشكل الذي يكتبه المستودع فعلاً -------
    def test_financial_change_reads_the_line_shapes_real_producers_write(self):
        """كان يقرأ `old`/`new` من المستوى الأعلى وحدَه، فبنودُ الأسطر التي
        يكتبها `build_line_changes` (`line_changed`/`line_added`) تُسقَط بصمت —
        وهناك يسكن المال. والفرعُ البديل (`old_total`…) بلا منتِجٍ في المستودع.
        """
        ActivityLog.objects.create(
            tenant=self.tenant_a,
            user=self.agent_user,
            action="update",
            entity_type="sales_invoice",
            entity_label="#900",
            description="",
            metadata={"changes": [{
                "kind": "line_changed",
                "label": "شاشة",
                "changes": [{"label": "السعر", "old": "100.00", "new": "250.00"}],
            }]},
        )

        desc = get_my_books_tab_data(self.tenant_a)["activity_log"][0]["description"]
        self.assertIn("250.00", desc)
        self.assertIn("100.00", desc)

    # -- س: حجمُ الملاحظة على السطح العام محدود -----------------------------
    def test_public_note_is_bounded_in_bytes(self):
        """حقلٌ بلا حدٍّ يصبّ في `TextField` على نقطةٍ **بلا مصادقة**؛ والمواصفة
        تسمّي «الحجمَ والفحصَ بالبايتات» على الأسطح العامة.
        """
        from platform_ops.serializers import PUBLIC_RATING_NOTE_MAX_LENGTH

        self._work()
        _, raw_token = generate_daily_rating_token(
            tenant=self.tenant_a, employee=self.employee, service_date=self.service_date,
        )
        resp = APIClient().post(
            f"/api/my-agent/ratings/public/{raw_token}/",
            {"stars": 5, "note": "ب" * (PUBLIC_RATING_NOTE_MAX_LENGTH + 1)},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.data)
        self.assertFalse(DailyRating.objects.filter(tenant=self.tenant_a).exists())
