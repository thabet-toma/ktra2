"""اختبارات المرحلة السادسة (م٦): اللوحة التفاعلية، شريط التدخل، التنقيب، PlatformNotification، وPlatformActivityLog.

تغطي هذه الاختبارات المتطلبات الصارمة:
1. الفلترة الخادمية للإشعارات: لا يرى المستخدم إلا إشعاراته، ولا يمكن لمستخدم رؤية إشعارات غيره.
2. سجل النشاط المنصي العابر للشركات (PlatformActivityLog): يعبر الشركات زمنياً ولا يلمس ActivityLog.
3. رفض وسائط الشركات الممنوعة بـ 400 Bad Request عند التنقيب أو استعلام اللوحة أو السجل.
4. عزل النطاق: موظف المنصة يرى فقط الشركات المرتبطة به.
5. اتساع أعمدة choices: التحقق من أن max_length يتسع لأطول مفتاح في PlatformNotification وPlatformActivityLog.
6. كشف الشذوذات الأربعة فقط (critical_delay, overloaded, absent_with_work, low_score) وترتيب الأسوأ أولاً.
7. عتبة الـ 15 دقيقة للنشاط الأخير من hr.models.UserDevice (اختبار 14 دقيقة و16 دقيقة).
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import ActivityLog
from hr.models import UserDevice
from tenants.models import Tenant

from platform_ops.models import (
    IntegrationKey,
    Engagement,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    PlatformNotification,
    PolicyProfile,
    ServiceSubscription,
    WorkOrder,
)
from platform_ops.views import PLATFORM_ACTIVITY_PAGE_CAP
from platform_ops.services import (
    create_work_order,
    generate_integration_key,
    receive_channel_work_order,
    transition_work_order_status,
    ANOMALY_ABSENT_WITH_WORK,
    ANOMALY_CRITICAL_DELAY,
    ANOMALY_LOW_SCORE,
    ANOMALY_OVERLOADED,
    create_platform_notification,
    detect_platform_anomalies,
    get_employee_last_active,
    get_platform_dashboard_summary,
    is_recently_active,
    log_platform_activity,
)

User = get_user_model()


class DashboardAndNotificationsTest(TestCase):
    """مجموعة اختبارات المرحلة السادسة."""

    def setUp(self):
        # 1. شركات ومشتريات
        self.tenant_a = Tenant.objects.create(TenantID=2001, CompanyName="Alpha Corporation")
        self.tenant_b = Tenant.objects.create(TenantID=2002, CompanyName="Beta Enterprises")

        self.sub_a = ServiceSubscription.objects.create(
            tenant=self.tenant_a,
            status=ServiceSubscription.Status.ACTIVE,
            plan="enterprise",
        )
        self.sub_b = ServiceSubscription.objects.create(
            tenant=self.tenant_b,
            status=ServiceSubscription.Status.ACTIVE,
            plan="standard",
        )

        # 2. مستخدمون: مدير منصة، وموظفان
        self.user_manager = User.objects.create_superuser(
            username="ops_director",
            email="director@platform.local",
            password="pwd",
            first_name="مدير",
            last_name="المنصة",
        )

        self.user_emp1 = User.objects.create_user(
            username="emp_kareem",
            email="kareem@platform.local",
            password="pwd",
            first_name="كريم",
            last_name="العمليات",
        )
        self.emp1 = PlatformEmployee.objects.create(
            user=self.user_emp1,
            specialty="data_entry",
            capacity_target=5,
            status=PlatformEmployee.Status.ACTIVE,
        )

        self.user_emp2 = User.objects.create_user(
            username="emp_sara",
            email="sara@platform.local",
            password="pwd",
            first_name="سارة",
            last_name="التدقيق",
        )
        self.emp2 = PlatformEmployee.objects.create(
            user=self.user_emp2,
            specialty="review",
            capacity_target=3,
            status=PlatformEmployee.Status.ACTIVE,
        )

        # ارتباط emp1 بالشركة A
        self.eng_a = Engagement.objects.create(
            employee=self.emp1,
            tenant=self.tenant_a,
            status=Engagement.Status.ACTIVE,
            assigned_by=self.user_manager,
        )

        # عملاء واجهات API
        self.client_manager = APIClient()
        self.client_manager.force_authenticate(user=self.user_manager)

        self.client_emp1 = APIClient()
        self.client_emp1.force_authenticate(user=self.user_emp1)

        self.client_emp2 = APIClient()
        self.client_emp2.force_authenticate(user=self.user_emp2)

    # --------------------------------------------------------------------------
    # 1. الإشعارات: الفلترة الخادمية وعمليات القراءة
    # --------------------------------------------------------------------------

    def test_notification_server_filtered_strictly(self):
        """لا يرى المستخدم إلا إشعاراته الخادمية، ولا يمكن استرجاع إشعارات غيره."""
        n1 = create_platform_notification(
            recipient=self.user_emp1,
            tenant=self.tenant_a,
            notification_type=PlatformNotification.NotificationType.SLA_BREACH,
            title="تجاوز الأجل",
            message="تم تجاوز أجل أمر العمل",
        )
        n2 = create_platform_notification(
            recipient=self.user_emp2,
            tenant=self.tenant_b,
            notification_type=PlatformNotification.NotificationType.LOW_SCORE,
            title="تقييم منخفض",
            message="التقييم الشهري أقل من المتوقع",
        )

        # الموظف 1 يرى فقط n1
        resp1 = self.client_emp1.get("/api/platform/ops/notifications/")
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        ids1 = [item["id"] for item in resp1.data["results"] if "results" in resp1.data] if isinstance(resp1.data, dict) and "results" in resp1.data else [item["id"] for item in resp1.data]
        self.assertIn(n1.id, ids1)
        self.assertNotIn(n2.id, ids1)

        # الموظف 2 يرى فقط n2
        resp2 = self.client_emp2.get("/api/platform/ops/notifications/")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        ids2 = [item["id"] for item in resp2.data["results"] if "results" in resp2.data] if isinstance(resp2.data, dict) and "results" in resp2.data else [item["id"] for item in resp2.data]
        self.assertIn(n2.id, ids2)
        self.assertNotIn(n1.id, ids2)

        # الموظف 1 لا يستطيع قراءة تفاصيل إشعار الموظف 2
        resp_detail = self.client_emp1.get(f"/api/platform/ops/notifications/{n2.id}/")
        self.assertEqual(resp_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_notification_mark_read_and_mark_all_read(self):
        """اختبار تعليم إشعار كمقروء وتعليم كل الإشعارات كمقروءة."""
        n1 = create_platform_notification(
            recipient=self.user_emp1,
            notification_type=PlatformNotification.NotificationType.SLA_BREACH,
            title="إشعار 1",
        )
        n2 = create_platform_notification(
            recipient=self.user_emp1,
            notification_type=PlatformNotification.NotificationType.QUOTA_EXCEEDED,
            title="إشعار 2",
        )

        # قراءة العداد غير المقروء
        resp_count = self.client_emp1.get("/api/platform/ops/notifications/unread-count/")
        self.assertEqual(resp_count.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_count.data["unread_count"], 2)

        # تعليم n1 كمقروء
        resp_mark = self.client_emp1.post(f"/api/platform/ops/notifications/{n1.id}/mark-read/")
        self.assertEqual(resp_mark.status_code, status.HTTP_200_OK)
        self.assertTrue(resp_mark.data["is_read"])

        # تعليم الكل كمقروء
        resp_all = self.client_emp1.post("/api/platform/ops/notifications/mark-all-read/")
        self.assertEqual(resp_all.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_all.data["marked_count"], 1)  # بقي n2 فقط

        n2.refresh_from_db()
        self.assertTrue(n2.is_read)
        self.assertIsNotNone(n2.read_at)

    # --------------------------------------------------------------------------
    # 2. سجل النشاط العابر للشركات (PlatformActivityLog)
    # --------------------------------------------------------------------------

    def test_platform_activity_log_cross_tenant_and_independent(self):
        """سجل النشاط العابر يجمع نشاط موظف عبر شركات متعددة ولا يلمس جدول ActivityLog المستأجر."""
        initial_core_logs = ActivityLog.objects.count()

        now = timezone.now()
        t1 = now - datetime.timedelta(minutes=30)
        t2 = now - datetime.timedelta(minutes=10)
        t3 = now

        log1 = log_platform_activity(
            employee=self.emp1,
            tenant=self.tenant_a,
            action=PlatformActivityLog.Action.WORK_ORDER_TRANSITION,
            description="انتقال أمر عمل شركة أ",
            created_at=t1,
        )
        log2 = log_platform_activity(
            employee=self.emp1,
            tenant=self.tenant_b,
            action=PlatformActivityLog.Action.DELIVERABLE_SUBMIT,
            description="تسليم مخرج لشركة ب",
            created_at=t2,
        )
        log3 = log_platform_activity(
            employee=self.emp1,
            tenant=None,  # نشاط عام كلقطة أداء
            action=PlatformActivityLog.Action.SNAPSHOT_CAPTURED,
            description="لقطة أداء شهرية",
            created_at=t3,
        )

        # التأكد التام من عدم مساس جدول core.models.ActivityLog
        self.assertEqual(ActivityLog.objects.count(), initial_core_logs)

        # المدير يستعلم عن سجل النشاط العابر: يرى كل الشركات ومرتباً عكسياً زمنياً
        resp = self.client_manager.get("/api/platform/ops/activity-logs/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
        ids = [item["id"] for item in results]
        self.assertEqual(ids[:3], [log3.id, log2.id, log1.id])

        # نقطة نشاط الموظف الخاصة: /api/platform/ops/employees/{id}/activity/
        resp_emp_activity = self.client_emp1.get(f"/api/platform/ops/employees/{self.emp1.id}/activity/")
        self.assertEqual(resp_emp_activity.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_emp_activity.data), 3)

        # الموظف لا يستطيع فتح سجل نشاط موظف آخر
        resp_forbidden = self.client_emp1.get(f"/api/platform/ops/employees/{self.emp2.id}/activity/")
        self.assertIn(resp_forbidden.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    # --------------------------------------------------------------------------
    # 3. رفض وسائط الشركات الممنوعة بـ 400 Bad Request
    # --------------------------------------------------------------------------

    def test_forbidden_tenant_query_parameters_rejected_with_400(self):
        """رفض صريح بـ 400 لأي محاولة لتمرير معاملات الشركة في مسارات المنصة."""
        forbidden_keys = ["tenant", "tenants", "tenant_id", "tenant_ids"]

        endpoints = [
            "/api/platform/ops/dashboard/",
            "/api/platform/ops/work-orders/",
            "/api/platform/ops/activity-logs/",
            "/api/platform/ops/notifications/",
            f"/api/platform/ops/employees/{self.emp1.id}/activity/",
        ]

        for url in endpoints:
            for key in forbidden_keys:
                resp = self.client_manager.get(f"{url}?{key}=2001")
                self.assertEqual(
                    resp.status_code,
                    status.HTTP_400_BAD_REQUEST,
                    f"المسار {url} مع المعامل {key} لم يرجع 400!",
                )
                self.assertIn("cross_tenant_query_disallowed_from_request", str(resp.data))

    # --------------------------------------------------------------------------
    # 4. عزل النطاق في أوامر العمل
    # --------------------------------------------------------------------------

    def test_work_order_scoping_for_staff_vs_manager(self):
        """موظف المنصة يرى أوامر شركات ارتباطه النشط فقط، بينما المدير يرى الكل."""
        wo_a = WorkOrder.objects.create(
            tenant=self.tenant_a,
            title="أمر عمل في شركة أ",
            kind=WorkOrder.Kind.DATA_ENTRY,
            source=WorkOrder.Source.CHANNEL,
            assignee=self.emp1,
        )
        wo_b = WorkOrder.objects.create(
            tenant=self.tenant_b,
            title="أمر عمل في شركة ب",
            kind=WorkOrder.Kind.REVIEW,
            source=WorkOrder.Source.CHANNEL,
            assignee=self.emp2,
        )

        # emp1 مرتبط بشركة أ فقط
        resp_emp1 = self.client_emp1.get("/api/platform/ops/work-orders/")
        self.assertEqual(resp_emp1.status_code, status.HTTP_200_OK)
        results1 = resp_emp1.data["results"] if isinstance(resp_emp1.data, dict) and "results" in resp_emp1.data else resp_emp1.data
        ids1 = [item["id"] for item in results1]
        self.assertIn(wo_a.id, ids1)
        self.assertNotIn(wo_b.id, ids1)

        # manager يرى الاثنين
        resp_mgr = self.client_manager.get("/api/platform/ops/work-orders/")
        self.assertEqual(resp_mgr.status_code, status.HTTP_200_OK)
        results_mgr = resp_mgr.data["results"] if isinstance(resp_mgr.data, dict) and "results" in resp_mgr.data else resp_mgr.data
        ids_mgr = [item["id"] for item in results_mgr]
        self.assertIn(wo_a.id, ids_mgr)
        self.assertIn(wo_b.id, ids_mgr)

    # --------------------------------------------------------------------------
    # 5. اتساع أعمدة choices
    # --------------------------------------------------------------------------

    def test_choices_column_width_meets_or_exceeds_longest_key(self):
        """عرض أعمدة choices في الموديلات الجديدة يتسع لأطول مفتاح نصي."""
        # PlatformNotification.notification_type
        notif_field = PlatformNotification._meta.get_field("notification_type")
        longest_notif_key = max(len(choice) for choice in PlatformNotification.NotificationType.values)
        self.assertGreaterEqual(
            notif_field.max_length,
            longest_notif_key,
            f"حقل notification_type عرضه {notif_field.max_length} وأطول قيمة {longest_notif_key}",
        )

        # PlatformActivityLog.action
        act_field = PlatformActivityLog._meta.get_field("action")
        longest_act_key = max(len(choice) for choice in PlatformActivityLog.Action.values)
        self.assertGreaterEqual(
            act_field.max_length,
            longest_act_key,
            f"حقل action عرضه {act_field.max_length} وأطول قيمة {longest_act_key}",
        )

    # --------------------------------------------------------------------------
    # 6. كشف الشذوذات الأربعة وترتيب الأسوأ أولاً
    # --------------------------------------------------------------------------

    def test_anomaly_detections_and_worst_first_ordering(self):
        """كشف الشذوذات الأربعة فقط وترتيبها بحسب الأولوية والحدة."""
        now = timezone.now()

        # 1. تأخر حرج (critical_delay): موعد نهائي قبل 3 ساعات
        wo_delayed = WorkOrder.objects.create(
            tenant=self.tenant_a,
            title="أمر عمل متأخر حرج",
            kind=WorkOrder.Kind.DATA_ENTRY,
            status=WorkOrder.Status.DATA_ENTRY,
            assignee=self.emp1,
            deadline_at=now - datetime.timedelta(hours=3),
        )

        # 2. حمل مفرط (overloaded): emp2 طاقته المستهدفة 3، سننشئ له 4 أوامر نشطة
        for i in range(4):
            WorkOrder.objects.create(
                tenant=self.tenant_a,
                title=f"أمر نشط إضافي {i}",
                kind=WorkOrder.Kind.REVIEW,
                status=WorkOrder.Status.SCREENING,
                assignee=self.emp2,
                deadline_at=now + datetime.timedelta(hours=10),
            )

        # 3. غياب مع وجود عمل (absent_with_work): emp1 لديه عمل، وسننشئ جهاز نشط قبل 40 دقيقة
        UserDevice.objects.create(
            user=self.user_emp1,
            device_name="Laptop Kareem",
            last_active_at=now - datetime.timedelta(minutes=40),
        )

        # 4. تقييم منخفض (low_score): لقطة أداء لـ emp2 بدرجة 45
        policy = PolicyProfile.objects.create(specialty="review", name="Review Policy")
        PerformanceSnapshot.objects.create(
            employee=self.emp2,
            period_year=now.year,
            period_month=now.month,
            status="completed",
            composite_score=Decimal("45.00"),
            sample_size=10,
            policy_profile=policy,
        )

        # استدعاء دالة كشف الشذوذات
        anomalies = detect_platform_anomalies(now=now)
        types_detected = {a["anomaly_type"] for a in anomalies}

        self.assertIn(ANOMALY_CRITICAL_DELAY, types_detected)
        self.assertIn(ANOMALY_OVERLOADED, types_detected)
        self.assertIn(ANOMALY_ABSENT_WITH_WORK, types_detected)
        self.assertIn(ANOMALY_LOW_SCORE, types_detected)

        # لا يوجد أنواع شذوذ أخرى
        self.assertTrue(types_detected.issubset({
            ANOMALY_CRITICAL_DELAY,
            ANOMALY_OVERLOADED,
            ANOMALY_ABSENT_WITH_WORK,
            ANOMALY_LOW_SCORE,
        }))

        # الترتيب الأسوأ أولاً: critical_delay يسبق low_score
        first_type = anomalies[0]["anomaly_type"]
        self.assertEqual(first_type, ANOMALY_CRITICAL_DELAY)

    # --------------------------------------------------------------------------
    # 7. عتبة الـ 15 دقيقة للنشاط الأخير من UserDevice
    # --------------------------------------------------------------------------

    def test_last_active_threshold_14m_and_16m(self):
        """التحقق الدقيق من عتبة الـ 15 دقيقة: 14 دقيقة نشط، و16 دقيقة غير نشط."""
        now = timezone.now()

        # حالة 1: نشاط قبل 14 دقيقة (نشط)
        device1 = UserDevice.objects.create(
            user=self.user_emp1,
            device_name="Device 1",
            last_active_at=now - datetime.timedelta(minutes=14),
        )
        self.assertTrue(is_recently_active(self.emp1, threshold_minutes=15, now=now))

        # تحديث النشاط إلى قبل 16 دقيقة (غير نشط)
        device1.last_active_at = now - datetime.timedelta(minutes=16)
        device1.save(update_fields=["last_active_at"])
        self.assertFalse(is_recently_active(self.emp1, threshold_minutes=15, now=now))

        # حالة عدم وجود أي جهاز (غير نشط)
        self.assertIsNone(get_employee_last_active(self.emp2))
        self.assertFalse(is_recently_active(self.emp2, threshold_minutes=15, now=now))

    # --------------------------------------------------------------------------
    # 8. استجابة لوحة المعلومات (PlatformDashboardView)
    # --------------------------------------------------------------------------

    def test_platform_dashboard_summary_payload(self):
        """التحقق من بنية رد لوحة المعلومات واحتوائها على البطاقات والشذوذات والتنقيب."""
        resp = self.client_manager.get("/api/platform/ops/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.data
        self.assertEqual(data["view_unit"], "employee")
        self.assertIn("employees", data)
        self.assertIn("companies", data)
        self.assertIn("anomalies", data)
        self.assertIn("total_anomalies_count", data)

        # التحقق من أن بطاقة الموظف تحتوي على المؤشرات الأساسية دون نقاط تحفيزية
        emp_card = data["employees"][0]
        self.assertIn("id", emp_card)
        self.assertIn("name", emp_card)
        self.assertIn("active_work_orders_count", emp_card)
        self.assertIn("overdue_work_orders_count", emp_card)
        self.assertIn("last_active_at", emp_card)
        self.assertIn("is_active_now", emp_card)
        self.assertNotIn("points", emp_card)  # لا نقاط تحفيزية (gamification)


class DashboardHonestyTest(TestCase):
    """اللوحةُ لا تلفّق رقماً، ولا تُصدِر استعلاماً لكلّ بطاقة."""

    def setUp(self):
        self.manager = User.objects.create_superuser(
            username="dash_mgr", email="dash_mgr@ktra.local", password="x"
        )
        self.tenant = Tenant.objects.create(TenantID=4101, CompanyName="Dash Honest Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth"
        )
        self.employees = []
        for i in range(4):
            user = User.objects.create_user(
                username=f"dash_staff_{i}", email=f"dash{i}@ktra.local", password="x"
            )
            emp = PlatformEmployee.objects.create(
                user=user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE
            )
            Engagement.objects.create(
                employee=emp, tenant=self.tenant, status=Engagement.Status.ACTIVE
            )
            UserDevice.objects.create(
                user=user,
                device_name=f"Dash Device {i}",
                last_active_at=timezone.now() - datetime.timedelta(minutes=i),
            )
            self.employees.append(emp)

    def test_an_employee_without_enough_data_is_not_scored_as_perfect(self):
        """موظّفٌ بلا بياناتٍ كان يُحسَب ١٠٠ في مفتاح الترتيب — أي «كاملَ الدرجة».

        فيُدفَع إلى ذيل «الأسوأ أوّلاً» حيث لا يراه أحد، والمواصفةُ تقول إنّ العيّنةَ
        الناقصةَ **تُخرجه من الترتيب** لا تضعه على قمّته.
        """
        summary = get_platform_dashboard_summary(user=self.manager)
        cards = summary["employees"]
        self.assertTrue(cards)

        for card in cards:
            perf = card["performance"]
            self.assertEqual(
                perf["status"],
                PerformanceSnapshot.Status.INSUFFICIENT_DATA,
                "تهيئةُ الاختبار تفترض غيابَ البيانات",
            )
            self.assertIsNone(
                perf["composite_score"],
                "درجةٌ رقميّةٌ لموظّفٍ بلا بيانات — رقمٌ ملفَّق.",
            )
            self.assertFalse(
                card["is_ranked"],
                "موظّفٌ بلا بياناتٍ مُدرَجٌ في الترتيب الرسميّ.",
            )

    def test_the_dashboard_reads_last_seen_for_everyone_in_one_query(self):
        """آخرُ ظهورٍ باستعلامٍ واحدٍ لا باستعلامٍ لكلّ بطاقة.

        الدرسُ مسجَّلٌ في هذا المستودع: الدمجُ في SQL لا في بايثون. وهذه شاشةٌ
        تُفتَح على عشرات البطاقات.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            get_platform_dashboard_summary(user=self.manager)

        device_queries = [
            q for q in ctx.captured_queries if "hr_userdevice" in q["sql"].lower()
        ]
        self.assertLessEqual(
            len(device_queries),
            1,
            f"استعلامُ آخرِ ظهورٍ تكرّر {len(device_queries)} مرّةً لأربعة موظّفين — "
            "يكبر مع كلّ بطاقة.",
        )

    def test_last_seen_is_a_timestamp_not_a_lamp(self):
        summary = get_platform_dashboard_summary(user=self.manager)
        cards = summary["employees"]
        for card in cards:
            self.assertIsNotNone(card["last_active_at"], "طابعُ آخرِ ظهورٍ مفقود")


class PlatformActivityLogIsCappedTest(TestCase):
    """سجلُّ النشاط تحرٍّ لا تفريغُ جدول — والصفحةُ غيرُ مصفَّحةٍ افتراضياً."""

    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_superuser(
            username="cap_mgr", email="cap_mgr@ktra.local", password="x"
        )
        self.staff_user = User.objects.create_user(
            username="cap_staff", email="cap_staff@ktra.local", password="x"
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE
        )
        PlatformActivityLog.objects.bulk_create([
            PlatformActivityLog(
                employee=self.employee,
                action=PlatformActivityLog.Action.WORK_ORDER_TRANSITION,
                description=f"حدث رقم {i}",
            )
            for i in range(PLATFORM_ACTIVITY_PAGE_CAP + 25)
        ])

    def test_the_activity_endpoint_never_returns_more_than_the_cap(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(
            f"/api/platform/ops/employees/{self.employee.pk}/activity/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            len(response.data),
            PLATFORM_ACTIVITY_PAGE_CAP,
            "الاستجابةُ تحمل كلَّ صفوف الموظّف — استجابةٌ تكبر بلا حدّ.",
        )


class NotificationsHaveRealProducersTest(TestCase):
    """صندوقُ الإشعارات كان **بلا مُنتِجٍ واحد** في الكود.

    `create_platform_notification` لم يستدعِها إلا الاختبار — فالصندوقُ يبقى فارغاً
    في الإنتاج مهما تجاوزت شركةٌ باقتَها أو تأخّر أمرُ عمل. والمواصفةُ تطلب صندوقاً
    «يقول لي ما استجدّ».
    """

    def setUp(self):
        self.manager = User.objects.create_superuser(
            username="notif_mgr", email="notif_mgr@ktra.local", password="x"
        )
        self.tenant = Tenant.objects.create(TenantID=4201, CompanyName="Notify Co")
        self.subscription = ServiceSubscription.objects.create(
            tenant=self.tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
            included_quota=2,
            consumed_quota=0,
        )
        self.key, self.raw_token = generate_integration_key(
            tenant=self.tenant, channel=IntegrationKey.Channel.WHATSAPP
        )

    def test_crossing_the_quota_notifies_once_not_on_every_request(self):
        for i in range(4):
            receive_channel_work_order(
                key=self.key, title=f"طلب {i}", external_ref=f"NOTIF-{i}"
            )

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.consumed_quota, 4)

        quota_notes = PlatformNotification.objects.filter(
            notification_type=PlatformNotification.NotificationType.QUOTA_EXCEEDED,
            recipient=self.manager,
        )
        self.assertEqual(
            quota_notes.count(),
            1,
            "إشعارُ التجاوز يُطلَق مرّةً عند العبور لا في كلّ عمليّةٍ بعده.",
        )
        self.assertEqual(quota_notes.first().tenant_id, self.tenant.pk)

    def test_approving_a_work_order_after_its_deadline_notifies_the_breach(self):
        staff_user = User.objects.create_user(
            username="notif_staff", email="notif_staff@ktra.local", password="x"
        )
        employee = PlatformEmployee.objects.create(
            user=staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE
        )
        Engagement.objects.create(
            employee=employee, tenant=self.tenant, status=Engagement.Status.ACTIVE
        )

        received = timezone.now() - datetime.timedelta(hours=100)
        wo = create_work_order(
            tenant=self.tenant, title="أمر متأخّر", received_at=received
        )
        wo.assignee = employee
        wo.save(update_fields=["assignee"])

        for target in (
            WorkOrder.Status.SCREENING,
            WorkOrder.Status.DATA_ENTRY,
            WorkOrder.Status.REVIEW,
        ):
            wo = transition_work_order_status(work_order=wo, target_status=target)

        self.assertEqual(
            PlatformNotification.objects.filter(
                notification_type=PlatformNotification.NotificationType.SLA_BREACH
            ).count(),
            0,
            "لا إشعارَ قبل الاعتماد — الأجلُ لا يُحسَم إلا عنده.",
        )

        transition_work_order_status(
            work_order=wo, target_status=WorkOrder.Status.APPROVAL
        )

        breaches = PlatformNotification.objects.filter(
            notification_type=PlatformNotification.NotificationType.SLA_BREACH
        )
        self.assertGreaterEqual(breaches.count(), 1, "لا إشعارَ لتجاوزِ أجلٍ وقع فعلاً.")
        self.assertIn(staff_user.pk, set(breaches.values_list("recipient_id", flat=True)))
        self.assertIn(self.manager.pk, set(breaches.values_list("recipient_id", flat=True)))

    def test_an_on_time_approval_raises_no_breach_notification(self):
        """تأكيدٌ يستطيع السقوط: أمرٌ في وقته لا يُنتج إشعارَ تجاوز."""
        wo = create_work_order(tenant=self.tenant, title="أمر في وقته")
        for target in (
            WorkOrder.Status.SCREENING,
            WorkOrder.Status.DATA_ENTRY,
            WorkOrder.Status.REVIEW,
            WorkOrder.Status.APPROVAL,
        ):
            wo = transition_work_order_status(work_order=wo, target_status=target)

        self.assertEqual(
            PlatformNotification.objects.filter(
                notification_type=PlatformNotification.NotificationType.SLA_BREACH
            ).count(),
            0,
        )
