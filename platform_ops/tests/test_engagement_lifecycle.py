"""اختبارات دورة حياة الارتباط والعضويات لعمليات المنصة (المرحلة الثانية م٢).

تغطي هذه الاختبارات المتطلبات الصارمة المحدثة وفق مراجعة المسألة #207 و#189:
1. إسناد موظف منصة لخدمة نشطة يوفر دور manager كاملاً، ويسجل created_membership=True إذا كانت العضوية جديدة.
2. إذا وجدت عضوية مسبقة للزبون (مثل محاسب أو مستعرض)، تُرقى لـ manager أثناء نشاط الارتباط مع حفظ دورها السابق،
   وعند التعليق أو الإلغاء يُستعاد دورها السابق دون حذفها.
3. الملكية الدقيقة للعضوية: يُحذف فقط الصف الدقيق المُتتبّع عبر managed_membership عندما يكون created_membership=True.
4. سيناريوهات الأمان عند الاستبدال الخارجي:
   - تعليق -> الزبون ينشئ عضوية بديلة -> استئناف -> إلغاء: لا يحذف العضوية البديلة.
   - حذف العضوية المنشأة خارجياً واستبدالها بعضوية زبون -> إلغاء الارتباط لا يحذف العضوية البديلة.
5. سجل AgentGrantedMembership حقيقي ومتصل بمسارات إضافة الأعضاء وتغيير الأدوار الفعلية:
   - إضافة عضو أو تغيير دوره بواسطة وكيل منصة نشط برباط نشط يُنتج سجلاً في AgentGrantedMembership.
   - نفس الإجراءات بواسطة مدير شركة عادي لا تُنتج أي سجل.
   - لا يُسجل إسناد الوكيل نفسه كسجل AgentGrantedMembership.
6. المغادرة (offboarding) عملية idempotent لا تعيد كتابة status/updated_at في الاستدعاء الثاني المماثل.
7. فرادة الارتباط النشط: تُختبر تسلسلياً على كل محرك، وتُختبر تحت تزامن حقيقي
   على المحركات التي تدعم قفل الصف وحدها (SQLite تقفل الجدول كله فيتشابك الخيطان).
"""
import ast
import inspect
import threading

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import (
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    skipUnlessDBFeature,
)
from rest_framework import status
from rest_framework.test import APIClient

from tenants.models import Tenant, UserCompanyMembership

from platform_ops.models import (
    AgentGrantedMembership,
    Engagement,
    PlatformEmployee,
    ServiceSubscription,
)
from platform_ops.services import (
    EngagementConflict,
    EngagementError,
    assign_platform_employee,
    deactivate_service_subscription,
    offboard_platform_employee,
    record_agent_granted_membership,
    resume_engagement,
    revoke_engagement,
    suspend_engagement,
)

User = get_user_model()


class EngagementLifecycleTest(TestCase):
    """اختبارات دورة حياة الارتباط والتملك الدقيق للعضوية."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin_ops",
            email="admin_ops@platform.local",
            password="x",
        )
        self.staff_user = User.objects.create_user(
            username="agent_salim",
            email="salim@platform.local",
            password="x",
            first_name="سالم",
            last_name="المنصي",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user,
            specialty="data_entry",
            capacity_target=100,
            status=PlatformEmployee.Status.ACTIVE,
        )

        self.tenant = Tenant.objects.create(TenantID=901, CompanyName="Client Alpha Co")
        self.subscription = ServiceSubscription.objects.create(
            tenant=self.tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
            included_quota=500,
        )

    def test_active_service_assignment_creates_manager_membership_and_tracks_exact_row(self):
        """إسناد الخدمة النشطة ينشئ عضوية manager ويسجل created_membership=True ويتتبع الصف بدقة."""
        self.assertFalse(
            UserCompanyMembership.objects.filter(user=self.staff_user, tenant=self.tenant).exists()
        )

        engagement = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
            assigned_by=self.admin_user,
        )

        self.assertEqual(engagement.status, Engagement.Status.ACTIVE)
        self.assertTrue(engagement.created_membership)
        self.assertEqual(engagement.assigned_by, self.admin_user)
        self.assertIsNotNone(engagement.managed_membership)
        self.assertEqual(engagement.previous_role, "")

        membership = engagement.managed_membership
        self.assertEqual(membership.role, "manager")
        self.assertEqual(membership.user, self.staff_user)
        self.assertEqual(membership.tenant, self.tenant)

    def test_no_active_subscription_rejects_assignment(self):
        """غياب الاشتراك النشط يرفض الإسناد (معلق، ملغى، أو غير موجود)."""
        tenant_no_sub = Tenant.objects.create(TenantID=902, CompanyName="No Sub Co")
        with self.assertRaises(EngagementError) as ctx:
            assign_platform_employee(employee=self.employee, tenant=tenant_no_sub)
        self.assertEqual(ctx.exception.code, "subscription_not_active")

        self.subscription.status = ServiceSubscription.Status.SUSPENDED
        self.subscription.save(update_fields=["status"])
        with self.assertRaises(EngagementError) as ctx:
            assign_platform_employee(employee=self.employee, tenant=self.tenant)
        self.assertEqual(ctx.exception.code, "subscription_not_active")

    def test_inactive_or_offboarded_platform_employee_rejects_assignment(self):
        """موظف المنصة غير النشط (في إجازة أو خارج الخدمة) يُرفض إسناده."""
        self.employee.status = PlatformEmployee.Status.ON_LEAVE
        self.employee.save(update_fields=["status"])
        with self.assertRaises(EngagementError) as ctx:
            assign_platform_employee(employee=self.employee, tenant=self.tenant)
        self.assertEqual(ctx.exception.code, "employee_not_active")

        self.employee.status = PlatformEmployee.Status.OFFBOARDED
        self.employee.save(update_fields=["status"])
        with self.assertRaises(EngagementError) as ctx:
            assign_platform_employee(employee=self.employee, tenant=self.tenant)
        self.assertEqual(ctx.exception.code, "employee_not_active")

    def test_preexisting_client_membership_upgraded_to_manager_and_restored_on_suspend_and_revoke(self):
        """العضوية المسبقة للزبون تُرقى لـ manager أثناء النشاط وتستعيد دورها السابق عند التعليق والإلغاء."""
        client_mem = UserCompanyMembership.objects.create(
            user=self.staff_user,
            tenant=self.tenant,
            role="accountant",
        )

        engagement = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
            assigned_by=self.admin_user,
        )

        self.assertFalse(engagement.created_membership)
        self.assertEqual(engagement.previous_role, "accountant")
        self.assertEqual(engagement.managed_membership_id, client_mem.pk)

        # التحقق من ترقية العضوية لمدير فعلياً لتشغيل الدفاتر
        client_mem.refresh_from_db()
        self.assertEqual(client_mem.role, "manager")

        # تعليق الارتباط: يستعيد الدور السابق ولا يحذف العضوية
        suspend_engagement(engagement=engagement, reason="تعليق مؤقت")
        client_mem.refresh_from_db()
        self.assertEqual(client_mem.role, "accountant")

        # استئناف الارتباط: يرقيه مجدداً لـ manager
        resume_engagement(engagement=engagement)
        client_mem.refresh_from_db()
        self.assertEqual(client_mem.role, "manager")

        # إلغاء الارتباط: يستعيد الدور السابق ولا يحذف العضوية
        revoke_engagement(engagement=engagement, revoked_by=self.admin_user, reason="إلغاء نهائي")
        client_mem.refresh_from_db()
        self.assertEqual(client_mem.role, "accountant")
        self.assertTrue(UserCompanyMembership.objects.filter(pk=client_mem.pk).exists())

    def test_suspend_then_client_replacement_then_resume_then_revoke_preserves_replacement(self):
        """سيناريو التعليق ثم استبدال الزبون للعضوية: الاستئناف والإلغاء يحميان الصف البديل."""
        engagement = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
            assigned_by=self.admin_user,
        )
        self.assertTrue(engagement.created_membership)
        original_mem_pk = engagement.managed_membership_id

        # 1. تعليق الارتباط: يحذف العضوية المنشأة
        suspend_engagement(engagement=engagement, reason="تعليق")
        self.assertFalse(UserCompanyMembership.objects.filter(pk=original_mem_pk).exists())

        # 2. الزبون ينشئ عضوية بديلة للمستخدم نفسه بدور viewer
        replacement_mem = UserCompanyMembership.objects.create(
            user=self.staff_user,
            tenant=self.tenant,
            role="viewer",
        )

        # 3. استئناف الارتباط: يعيد حساب created_membership=False ويرقى البديل لـ manager
        resume_engagement(engagement=engagement)
        engagement.refresh_from_db()
        self.assertFalse(engagement.created_membership)
        self.assertEqual(engagement.previous_role, "viewer")
        self.assertEqual(engagement.managed_membership_id, replacement_mem.pk)

        replacement_mem.refresh_from_db()
        self.assertEqual(replacement_mem.role, "manager")

        # 4. إلغاء الارتباط: لا يحذف الصف البديل بل يستعيد دوره viewer
        revoke_engagement(engagement=engagement, revoked_by=self.admin_user)
        replacement_mem.refresh_from_db()
        self.assertEqual(replacement_mem.role, "viewer")
        self.assertTrue(UserCompanyMembership.objects.filter(pk=replacement_mem.pk).exists())

    def test_externally_deleted_managed_membership_does_not_delete_replacement_on_revoke(self):
        """إذا حُذفت العضوية المنشأة خارجياً واستُبدلت بصف زبون، الإلغاء لا يحذف الصف البديل."""
        engagement = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
            assigned_by=self.admin_user,
        )
        self.assertTrue(engagement.created_membership)
        original_mem = engagement.managed_membership

        # حذف الصف الأصلي خارجياً (simulate external deletion)
        original_mem.delete()

        # إنشاء صف بديل للزبون بمعرف جديد
        replacement = UserCompanyMembership.objects.create(
            user=self.staff_user,
            tenant=self.tenant,
            role="procurement",
        )

        # إلغاء الارتباط: يجب ألا يحذف الصف البديل بحجة مطابقة (user, tenant)
        revoke_engagement(engagement=engagement, revoked_by=self.admin_user)
        self.assertTrue(UserCompanyMembership.objects.filter(pk=replacement.pk).exists())
        replacement.refresh_from_db()
        self.assertEqual(replacement.role, "procurement")

    def test_subscription_deactivation_suspends_rather_than_deletes_active_engagements(self):
        """إيقاف/تعليق اشتراك الخدمة يعلق الارتباطات النشطة ولا يحذفها."""
        engagement = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
            assigned_by=self.admin_user,
        )
        self.assertEqual(engagement.status, Engagement.Status.ACTIVE)

        deactivate_service_subscription(
            subscription=self.subscription,
            new_status=ServiceSubscription.Status.SUSPENDED,
            reason="تأخر سداد الاشتراك",
        )

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, ServiceSubscription.Status.SUSPENDED)

        engagement.refresh_from_db()
        self.assertEqual(engagement.status, Engagement.Status.SUSPENDED)
        self.assertIsNotNone(engagement.suspended_at)
        self.assertFalse(
            UserCompanyMembership.objects.filter(user=self.staff_user, tenant=self.tenant).exists()
        )

    def test_offboarding_called_twice_does_not_rewrite_status_updated_at(self):
        """المغادرة idempotent: لا تعيد كتابة status/updated_at في الاستدعاء الثاني."""
        engagement = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
            assigned_by=self.admin_user,
        )

        offboard_platform_employee(
            employee=self.employee,
            actor=self.admin_user,
            reason="استقالة",
        )

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, PlatformEmployee.Status.OFFBOARDED)
        first_updated_at = self.employee.updated_at

        engagement.refresh_from_db()
        self.assertEqual(engagement.status, Engagement.Status.REVOKED)

        # استدعاء المغادرة للمرة الثانية
        offboard_platform_employee(
            employee=self.employee,
            actor=self.admin_user,
            reason="استدعاء مكرر",
        )

        self.employee.refresh_from_db()
        self.assertEqual(self.employee.status, PlatformEmployee.Status.OFFBOARDED)
        # لم تتغير updated_at لعدم إعادة حفظ الصف دون داعٍ
        self.assertEqual(self.employee.updated_at, first_updated_at)


class AgentGrantedMembershipIntegrationTest(TestCase):
    """اختبارات تكامل سجل AgentGrantedMembership عبر نقاط API الحقيقية للشركة."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(TenantID=908, CompanyName="Test Actions Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant,
            status=ServiceSubscription.Status.ACTIVE,
        )

        # مستخدم وكيل منصة
        self.agent_user = User.objects.create_user(
            username="platform_agent_1",
            email="agent1@platform.local",
            password="x",
            first_name="أحمد",
            last_name="الوكيل",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.agent_user,
            specialty="ops",
            status=PlatformEmployee.Status.ACTIVE,
        )

        # إسناد الوكيل كمدير في الشركة
        self.engagement = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
        )

        # مستخدم مدير شركة عادي (ليس موظف منصة)
        self.normal_manager_user = User.objects.create_user(
            username="company_owner_user",
            email="owner@client.local",
            password="x",
        )
        UserCompanyMembership.objects.create(
            user=self.normal_manager_user,
            tenant=self.tenant,
            role="manager",
        )

        # مستخدم مستهدف للإضافة
        self.new_client_user = User.objects.create_user(
            username="target_client_user",
            email="target@client.local",
            password="x",
            first_name="سامي",
            last_name="العميل",
        )

    def test_agent_own_assignment_does_not_create_agent_granted_membership(self):
        """إسناد الوكيل لنفسه لا يسجل AgentGrantedMembership وفق قرار #189."""
        self.assertEqual(
            AgentGrantedMembership.objects.filter(tenant=self.tenant).count(),
            0,
        )

    def test_member_addition_by_platform_agent_creates_agent_granted_record(self):
        """إضافة عضو بواسطة وكيل منصة نشط عبر مسار الشركة ينشئ سجل AgentGrantedMembership."""
        self.client.force_authenticate(user=self.agent_user)
        response = self.client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/",
            {"username_or_email": "target_client_user", "role": "accountant"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        record = AgentGrantedMembership.objects.filter(
            tenant=self.tenant, user=self.new_client_user
        ).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.acting_employee, self.employee)
        self.assertEqual(record.engagement, self.engagement)
        self.assertEqual(record.role_before, "")
        self.assertEqual(record.role_after, "accountant")
        self.assertEqual(record.target_user_id, self.new_client_user.pk)
        self.assertEqual(record.identity_snapshot.get("username"), "target_client_user")
        self.assertEqual(record.identity_snapshot.get("full_name"), "سامي العميل")

    def test_member_role_change_by_platform_agent_creates_agent_granted_record(self):
        """تغيير دور عضو بواسطة وكيل منصة نشط ينشئ سجل AgentGrantedMembership بأدواره السابقة والجديدة."""
        mem = UserCompanyMembership.objects.create(
            user=self.new_client_user,
            tenant=self.tenant,
            role="staff",
        )

        self.client.force_authenticate(user=self.agent_user)
        response = self.client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/change-role/",
            {"membership_id": mem.id, "role": "sales"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        record = AgentGrantedMembership.objects.filter(
            tenant=self.tenant, user=self.new_client_user, role_after="sales"
        ).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.role_before, "staff")
        self.assertEqual(record.role_after, "sales")
        self.assertEqual(record.acting_employee, self.employee)
        self.assertEqual(record.engagement, self.engagement)

    def test_member_addition_by_ordinary_company_manager_does_not_create_agent_granted_record(self):
        """إضافة عضو بواسطة مدير شركة عادي (ليس وكيل منصة) لا تُنشئ أي سجل AgentGrantedMembership."""
        self.client.force_authenticate(user=self.normal_manager_user)
        response = self.client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/",
            {"username_or_email": "target_client_user", "role": "viewer"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(
            AgentGrantedMembership.objects.filter(tenant=self.tenant).count(),
            0,
        )

    def test_record_agent_granted_membership_rejects_mismatched_tenant(self):
        """record_agent_granted_membership ترفض أي تباين بين شركة العضوية وشركة الارتباط."""
        other_tenant = Tenant.objects.create(TenantID=909, CompanyName="Other Co")
        other_mem = UserCompanyMembership.objects.create(
            user=self.new_client_user,
            tenant=other_tenant,
            role="staff",
        )

        with self.assertRaises(EngagementError) as ctx:
            record_agent_granted_membership(
                engagement=self.engagement,
                membership=other_mem,
                role_after="manager",
            )
        self.assertEqual(ctx.exception.code, "tenant_mismatch")


class ConcurrencyLockOrderTest(TransactionTestCase):
    """اختبار التزامن وصرامة ترتيب الأقفال عبر اتصالات ومعاملات متعددة."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="admin_conc",
            email="admin_conc@platform.local",
            password="x",
        )
        self.staff_user = User.objects.create_user(
            username="staff_conc",
            email="staff_conc@platform.local",
            password="x",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user,
            specialty="ops",
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.tenant = Tenant.objects.create(TenantID=910, CompanyName="Conc Co")
        self.subscription = ServiceSubscription.objects.create(
            tenant=self.tenant,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_assignments_for_same_employee_and_tenant(self):
        """محاولة إسنادين متزامنين لنفس (الموظف، الشركة) تسمح بنجاح واحد فقط وترفض الآخر تحت قفل.

        **لماذا الحارس؟** الخدمة تفرض الفرادة بـ`select_for_update` وترتيبِ أقفالٍ معلَن.
        وSQLite لا تعرف قفل الصفّ: كلُّ `select_for_update` عليها يقفل الجدولَ بأكمله،
        فيتشابك الخيطان ويسقط كلاهما بـ«database table is locked» — أي صفرُ نجاحاتٍ
        لا واحد. فالسقوط هناك حكمٌ على المحرِّك لا على الكود، ولا يستطيع هذا التأكيدُ
        السقوطَ للسبب الذي يحمله اسمُه. تُثبَّت الفرادةُ على كلّ محرِّك في الاختبار
        التسلسليّ أدناه، ويبقى هذا للتزامن الحقيقيّ على MySQL (محرِّك الإنتاج).
        """
        results = []
        errors = []

        def run_assign():
            try:
                eng = assign_platform_employee(
                    employee=self.employee,
                    tenant=self.tenant,
                    assigned_by=self.admin_user,
                )
                results.append(eng.pk)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(target=run_assign)
        t2 = threading.Thread(target=run_assign)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # إسناد واحد فقط يجب أن ينجح
        self.assertEqual(len(results), 1, f"نتائج غير متوقعة: {results}, أخطاء: {errors}")
        # الثاني يجب أن يواجه EngagementConflict (أو استثناء قفل قاعدة البيانات)
        self.assertEqual(len(errors), 1)
        self.assertTrue(
            any(isinstance(err, EngagementConflict) for err in errors)
            or any("database is locked" in str(err).lower() for err in errors)
        )

        # التأكد من وجود ارتباط نشط واحد فقط في القاعدة
        self.assertEqual(
            Engagement.objects.filter(
                employee=self.employee, tenant=self.tenant, status=Engagement.Status.ACTIVE
            ).count(),
            1,
        )

    def test_second_assignment_for_same_employee_and_tenant_conflicts(self):
        """الفرادةُ نفسُها بلا خيوط: إسنادٌ ثانٍ لارتباطٍ نشطٍ قائمٍ يُرفض بـEngagementConflict.

        هذا هو التأكيدُ الذي يعمل على كلّ محرِّك — بما فيه SQLite في البوّابة —
        فلا تبقى الفرادةُ محروسةً باختبارٍ يُتخطّى محلّياً.
        """
        first = assign_platform_employee(
            employee=self.employee,
            tenant=self.tenant,
            assigned_by=self.admin_user,
        )

        with self.assertRaises(EngagementConflict) as ctx:
            assign_platform_employee(
                employee=self.employee,
                tenant=self.tenant,
                assigned_by=self.admin_user,
            )
        self.assertEqual(ctx.exception.code, "already_active")

        self.assertEqual(
            Engagement.objects.filter(
                employee=self.employee,
                tenant=self.tenant,
                status=Engagement.Status.ACTIVE,
            ).count(),
            1,
        )
        self.assertEqual(
            Engagement.objects.filter(employee=self.employee, tenant=self.tenant).count(),
            1,
        )
        self.assertEqual(
            Engagement.objects.get(pk=first.pk).status, Engagement.Status.ACTIVE
        )


#: ترتيبُ الأقفال المعلَن في رأس `platform_ops/services.py`.
DECLARED_LOCK_ORDER = (
    "IntegrationKey",
    "ServiceSubscription",
    "PlatformEmployee",
    "Engagement",
    "WorkOrder",
    "WorkOrderDeliverable",
    "UserCompanyMembership",
    "DailyRating",
    "JobPosting",
    "JobApplicantInvitation",
    "JobApplicant",
)



def find_lock_order_violations(source: str) -> list[str]:
    """إرجاعُ كلّ دالّةٍ تطلب `select_for_update` بترتيبٍ يخالف الترتيبَ المعلَن.

    تُقرأ الشيفرةُ ساكنةً: لكلّ دالّة، تُرتَّب نداءاتُ `select_for_update` بموضعها
    في المصدر، ويُستخرج اسمُ النموذج من أقصى يسار سلسلة السمات
    (`Engagement.objects.select_for_update()` ← `Engagement`). ثمّ يجب أن تكون
    رتبُها غيرَ متناقصة. تخطّي نموذجٍ مسموح؛ أخذُه بعد ما هو أدنى منه ليس كذلك.
    """
    rank = {name: index for index, name in enumerate(DECLARED_LOCK_ORDER)}
    violations: list[str] = []

    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        locks: list[tuple[tuple[int, int], str]] = []
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if not isinstance(func, ast.Attribute) or func.attr != "select_for_update":
                continue
            base = func.value
            while isinstance(base, (ast.Attribute, ast.Call)):
                base = base.value if isinstance(base, ast.Attribute) else base.func
            if isinstance(base, ast.Name) and base.id in rank:
                locks.append(((inner.lineno, inner.col_offset), base.id))

        locks.sort()
        previous_rank = -1
        previous_model = ""
        for (lineno, _), model in locks:
            current_rank = rank[model]
            if current_rank < previous_rank:
                violations.append(
                    f"{node.name}: يقفل {model} بعد {previous_model} (سطر {lineno}) "
                    f"— يخالف {' -> '.join(DECLARED_LOCK_ORDER)}"
                )
            previous_rank = max(previous_rank, current_rank)
            previous_model = model

    return violations


class LockOrderSourceGuardTest(SimpleTestCase):
    """حارسُ ترتيبِ الأقفال — التشابكُ ABBA لا تكشفه SQLite ولا اختبارٌ سلوكيّ.

    ترتيبُ الأقفال عقدٌ معلَنٌ في رأس `services.py`؛ ونقضُه لا يظهر إلا على MySQL
    تحت حِملٍ متزامن، حيث تُسقط القاعدةُ إحدى المعاملتين. فيُحرَس ساكناً.
    """

    def test_every_service_function_locks_in_the_declared_order(self):
        from platform_ops import services

        violations = find_lock_order_violations(inspect.getsource(services))
        self.assertEqual(violations, [], "\n".join(violations))

    def test_the_guard_actually_catches_an_inverted_order(self):
        """تأكيدٌ يستطيع السقوط: مصدرٌ مصطنعٌ يقلب الترتيب فيجب أن يُمسَك."""
        inverted = (
            "def bad_service():\n"
            "    Engagement.objects.select_for_update().get(pk=1)\n"
            "    PlatformEmployee.objects.select_for_update().get(pk=2)\n"
        )
        violations = find_lock_order_violations(inverted)
        self.assertEqual(len(violations), 1, violations)
        self.assertIn("bad_service", violations[0])

    def test_the_guard_allows_skipping_a_model_in_the_chain(self):
        """تخطّي حلقةٍ من السلسلة ليس مخالفة — الترتيبُ لا الاكتمال."""
        skipping = (
            "def fine_service():\n"
            "    ServiceSubscription.objects.select_for_update().first()\n"
            "    UserCompanyMembership.objects.select_for_update().first()\n"
        )
        self.assertEqual(find_lock_order_violations(skipping), [])
