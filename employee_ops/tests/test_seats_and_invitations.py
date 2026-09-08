"""اختبارات المرحلة الثانية لوحدة متابعة الموظفين: المقاعد ودورة الدعوة وعزل الشركات."""
import hashlib
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.access import FIELD_STAFF_ROLE
from core.models import TenantLimit, TenantModule
from core.modules import invalidate_module_cache
from core.plans import bulk_usage, current_usage
from hr.models import Employee
from tenants.models import Currency, Tenant, UserCompanyMembership
from tenants.services import create_company

from employee_ops.models import EmployeeInvitation, EmployeeOpsSettings, EmployeeProfile


class EmployeeOpsSeatsAndInvitationsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True})
        cls.manager_a = User.objects.create_user(
            username="manager_a", password="password123"
        )
        cls.manager_b = User.objects.create_user(
            username="manager_b", password="password123"
        )

        cls.tenant_a = create_company("شركة الاختبار أ", cls.manager_a)
        cls.tenant_a.SubscriptionPlan = "Pro"
        cls.tenant_a.save(update_fields=["SubscriptionPlan"])

        cls.tenant_b = create_company("شركة الاختبار ب", cls.manager_b)
        cls.tenant_b.SubscriptionPlan = "Pro"
        cls.tenant_b.save(update_fields=["SubscriptionPlan"])

        TenantModule.objects.create(
            tenant=cls.tenant_a, module_key="employee_ops", enabled=True
        )
        TenantModule.objects.create(
            tenant=cls.tenant_b, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(cls.tenant_a.pk)
        invalidate_module_cache(cls.tenant_b.pk)

    def test_seat_limit_blocks_before_save_with_module_seat_message(self):
        """حدٌّ ٢ مقاعد: الثالث يُردّ 400، ورسالتُه تسمّي مقاعد متابعة الموظفين لا أعضاء الشركة،
        ولا يُنشأ صفُّ موظفٍ ولا صفُّ دعوة (منعٌ قبل الحفظ).
        """
        TenantLimit.objects.create(
            tenant=self.tenant_a,
            limit_key="employee_ops.seats",
            max_value=2,
        )
        self.client.force_authenticate(user=self.manager_a)

        # دعوة 1
        res1 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف 1"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res1.status_code, 201)

        # دعوة 2
        res2 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف 2"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res2.status_code, 201)

        # الموظف الثالث يجب أن يُمنع قبل الحفظ
        res3 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف 3"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res3.status_code, 400)
        self.assertIn("plan_limit", res3.data)
        self.assertIn("مقاعد متابعة الموظفين", res3.data["plan_limit"])
        self.assertNotIn("أعضاء الشركة", res3.data["plan_limit"])

        # تأكيد عدم إنشاء صف موظف ولا دعوة للموظف الثالث
        self.assertFalse(Employee.objects.filter(tenant=self.tenant_a, name="موظف 3").exists())
        self.assertEqual(
            EmployeeInvitation.objects.filter(tenant=self.tenant_a).count(), 2
        )

    def test_pending_invitation_consumes_a_seat(self):
        """دعوةٌ معلّقة تُحسب في current_usage."""
        usage_initial = current_usage(self.tenant_a, "employee_ops.seats")
        self.assertEqual(usage_initial, 0)

        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف معلق"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 201)

        usage_after = current_usage(self.tenant_a, "employee_ops.seats")
        self.assertEqual(usage_after, 1)

    def test_expired_invitation_frees_its_seat(self):
        """نفسُ الدعوة بأجلٍ ماضٍ لا تُحسب، والإرسالُ التالي ينجح."""
        TenantLimit.objects.create(
            tenant=self.tenant_a,
            limit_key="employee_ops.seats",
            max_value=1,
        )
        self.client.force_authenticate(user=self.manager_a)

        res1 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف سينتهي"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(current_usage(self.tenant_a, "employee_ops.seats"), 1)

        # نجعل الدعوة منتهية الأجل
        inv = EmployeeInvitation.objects.filter(tenant=self.tenant_a).first()
        inv.expires_at = timezone.now() - timedelta(days=1)
        inv.save(update_fields=["expires_at"])

        # تحرر المقعد تلقائياً
        self.assertEqual(current_usage(self.tenant_a, "employee_ops.seats"), 0)

        # الإرسال التالي ينجح لأن المقعد تحرر
        res2 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف جديد بعد الانتهاء"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(current_usage(self.tenant_a, "employee_ops.seats"), 1)

    def test_seat_limit_rechecked_at_acceptance(self):
        """أنشئ دعوتين بحدٍّ ٢، اقبل الأولى، ثمّ اخفض الحدّ إلى ١ (TenantLimit) واقبل الثانية ⇒ تُرفض بلا إنشاء مستخدم."""
        TenantLimit.objects.create(
            tenant=self.tenant_a,
            limit_key="employee_ops.seats",
            max_value=2,
        )
        self.client.force_authenticate(user=self.manager_a)

        res1 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "مرشح 1"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token1 = res1.data["raw_token"]

        res2 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "مرشح 2"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token2 = res2.data["raw_token"]

        # قبول الأولى
        self.client.force_authenticate(user=None)
        acc1 = self.client.post(
            f"/api/employee-ops/invitations/accept/{token1}/",
            {"username": "candidate_1", "password": "Password123!"},
        )
        self.assertEqual(acc1.status_code, 201)

        # خفض الحد إلى 1
        TenantLimit.objects.filter(
            tenant=self.tenant_a, limit_key="employee_ops.seats"
        ).update(max_value=1)

        # محاولة قبول الثانية ترفض
        acc2 = self.client.post(
            f"/api/employee-ops/invitations/accept/{token2}/",
            {"username": "candidate_2", "password": "Password123!"},
        )
        self.assertEqual(acc2.status_code, 400)
        self.assertIn("plan_limit", acc2.data)
        self.assertFalse(User.objects.filter(username="candidate_2").exists())

    def test_erp_member_does_not_consume_a_module_seat(self):
        """عضوٌ بدور manager أو staff لا يزيد employee_ops.seats ولو كان مربوطاً بسجلّ موظف."""
        staff_user = User.objects.create_user(username="staff_erp", password="password123")
        UserCompanyMembership.objects.create(
            user=staff_user, tenant=self.tenant_a, role="staff"
        )
        emp = Employee.objects.create(
            tenant=self.tenant_a,
            name="موظف ERP",
            code="ERP001",
            user=staff_user,
        )
        EmployeeProfile.objects.create(
            tenant=self.tenant_a,
            employee=emp,
        )
        self.assertEqual(current_usage(self.tenant_a, "employee_ops.seats"), 0)

    def test_company_members_count_unchanged_for_an_existing_company(self):
        """شركةٌ فيها أدوارٌ قائمة: current_usage(tenant, "company.members") قبل وبعد إضافة عضوٍ بدور field_staff — الرقم لا يتغيّر.
        وتوأمُه المجمَّع bulk_usage يعطي نفس الرقم.
        """
        usage_before = current_usage(self.tenant_a, "company.members")
        bulk_before = bulk_usage(keys=["company.members"], tenant_ids=[self.tenant_a.pk])["company.members"].get(self.tenant_a.pk, 0)
        self.assertEqual(usage_before, bulk_before)

        # إضافة عضو field_staff
        field_user = User.objects.create_user(username="field_user_test", password="password123")
        UserCompanyMembership.objects.create(
            user=field_user, tenant=self.tenant_a, role=FIELD_STAFF_ROLE
        )

        usage_after = current_usage(self.tenant_a, "company.members")
        bulk_after = bulk_usage(keys=["company.members"], tenant_ids=[self.tenant_a.pk])["company.members"].get(self.tenant_a.pk, 0)

        self.assertEqual(usage_before, usage_after)
        self.assertEqual(bulk_before, bulk_after)
        self.assertEqual(usage_after, bulk_after)

    def test_accept_creates_user_membership_and_links_employee(self):
        """القبول يُنشئ مستخدماً بدور field_staff، ويربط employee.user، والحالة accepted،
        وكلمةُ المرور مهشَّرة (user.check_password(...) صحيح وuser.password != raw).
        """
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "أحمد السعيد"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token = res.data["raw_token"]
        emp_id = res.data["employee"]["id"]

        self.client.force_authenticate(user=None)
        raw_pass = "MySecretPass123!"
        acc = self.client.post(
            f"/api/employee-ops/invitations/accept/{token}/",
            {"username": "ahmed_ops", "password": raw_pass, "first_name": "أحمد", "last_name": "السعيد"},
        )
        self.assertEqual(acc.status_code, 201)

        user = User.objects.get(username="ahmed_ops")
        self.assertTrue(user.check_password(raw_pass))
        self.assertNotEqual(user.password, raw_pass)

        # التحقق من العضوية
        mem = UserCompanyMembership.objects.get(user=user, tenant=self.tenant_a)
        self.assertEqual(mem.role, FIELD_STAFF_ROLE)

        # ربط الموظف
        emp = Employee.objects.get(id=emp_id)
        self.assertEqual(emp.user, user)

        # حالة الدعوة
        inv = EmployeeInvitation.objects.get(tenant=self.tenant_a, employee=emp)
        self.assertEqual(inv.status, EmployeeInvitation.STATUS_ACCEPTED)
        self.assertEqual(inv.accepted_user, user)
        self.assertIsNotNone(inv.accepted_at)

    def test_accept_refuses_a_weak_password_and_creates_nothing(self):
        """نقطةٌ عامّةٌ تُنشئ حساب دخول تُطبّق قواعد كلمة المرور.

        `set_password` لا يُشغّل `AUTH_PASSWORD_VALIDATORS` من نفسه — تُستدعى
        صراحةً (كما في `hr/auth_api.py`). بدونها يُقبل «1» كلمةَ مرورٍ لحسابٍ
        حقيقيّ في شركةٍ حقيقيّة، والرابطُ عامٌّ بلا مصادقة.
        """
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف كلمة ضعيفة"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token = res.data["raw_token"]

        self.client.force_authenticate(user=None)
        acc = self.client.post(
            f"/api/employee-ops/invitations/accept/{token}/",
            {"username": "weakpass_user", "password": "1"},
        )
        self.assertEqual(acc.status_code, 400)
        self.assertFalse(User.objects.filter(username="weakpass_user").exists())
        self.assertEqual(
            EmployeeInvitation.objects.get(token_hash=hashlib.sha256(token.encode()).hexdigest()).status,
            EmployeeInvitation.STATUS_PENDING,
            "الدعوة استُهلكت رغم رفض كلمة المرور.",
        )

    def test_raw_token_is_never_stored(self):
        """لا صفَّ دعوةٍ يحوي الرمز الخام في أيّ حقل، وtoken_hash يساوي sha256 للرمز."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف الرمز"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        raw_token = res.data["raw_token"]
        inv = EmployeeInvitation.objects.filter(tenant=self.tenant_a).latest("id")

        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self.assertEqual(inv.token_hash, expected_hash)

        # **كلُّ حقول الصفّ لا `token_hash` وحده**: الاسمُ يَعِد «في أيّ حقل»،
        # فحقلٌ يُضاف غداً ويخزّن الرمزَ خاماً يجب أن يُسقط هذا الاختبار.
        stored = {
            field.attname: getattr(inv, field.attname)
            for field in EmployeeInvitation._meta.concrete_fields
        }
        leaking = [name for name, value in stored.items() if raw_token in str(value)]
        self.assertEqual(leaking, [], f"الرمز الخام مخزَّنٌ في: {leaking} — {stored}")

    def test_accept_rejects_used_cancelled_and_unknown_token(self):
        """400 لكلٍّ، برسالةٍ واحدةٍ لا تفرّق بين «لا وجود له» و«ألغي»."""
        self.client.force_authenticate(user=self.manager_a)

        # دعوة ستُقبل
        res1 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "دعوة ستُقبل"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token_used = res1.data["raw_token"]

        # دعوة ستُلغى
        res2 = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "دعوة ستُلغى"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token_cancelled = res2.data["raw_token"]
        inv2_id = res2.data["invitation"]["id"]
        self.client.post(
            f"/api/employee-ops/invitations/{inv2_id}/cancel/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )

        # قبول الأولى
        self.client.force_authenticate(user=None)
        self.client.post(
            f"/api/employee-ops/invitations/accept/{token_used}/",
            {"username": "user_used", "password": "Password123!"},
        )

        # فحص الحالات الثلاث
        acc_unknown = self.client.post(
            "/api/employee-ops/invitations/accept/completely_unknown_token/",
            {"username": "user_unknown", "password": "Password123!"},
        )
        acc_used = self.client.post(
            f"/api/employee-ops/invitations/accept/{token_used}/",
            {"username": "user_used_again", "password": "Password123!"},
        )
        acc_cancelled = self.client.post(
            f"/api/employee-ops/invitations/accept/{token_cancelled}/",
            {"username": "user_cancelled", "password": "Password123!"},
        )

        self.assertEqual(acc_unknown.status_code, 400)
        self.assertEqual(acc_used.status_code, 400)
        self.assertEqual(acc_cancelled.status_code, 400)

        # الرسالة واحدة لا تفرّق
        self.assertEqual(acc_unknown.data, acc_used.data)
        self.assertEqual(acc_unknown.data, acc_cancelled.data)

    def test_accept_returns_410_for_expired_invitation(self):
        """انتهت صلاحية الدعوة: 410 والحالة تصير expired في القاعدة."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "دعوة ستنتهي"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token = res.data["raw_token"]
        inv = EmployeeInvitation.objects.get(id=res.data["invitation"]["id"])
        inv.expires_at = timezone.now() - timedelta(days=1)
        inv.save(update_fields=["expires_at"])

        self.client.force_authenticate(user=None)
        acc = self.client.post(
            f"/api/employee-ops/invitations/accept/{token}/",
            {"username": "user_expired", "password": "Password123!"},
        )
        self.assertEqual(acc.status_code, 410)

        inv.refresh_from_db()
        self.assertEqual(inv.status, EmployeeInvitation.STATUS_EXPIRED)

    def test_accept_returns_404_when_module_licence_revoked_after_invite(self):
        """404 عندما يُسحب ترخيص الوحدة بعد إرسال الدعوة."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف الترخيص الملغي"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token = res.data["raw_token"]

        # سحب ترخيص الوحدة
        TenantModule.objects.filter(
            tenant=self.tenant_a, module_key="employee_ops"
        ).update(enabled=False)
        invalidate_module_cache(self.tenant_a.pk)

        self.client.force_authenticate(user=None)
        acc = self.client.post(
            f"/api/employee-ops/invitations/accept/{token}/",
            {"username": "user_no_license", "password": "Password123!"},
        )
        self.assertEqual(acc.status_code, 404)

    def test_resend_kills_the_old_token(self):
        """الرمز القديم يُردّ 400 بعد إعادة الإرسال."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف إعادة الإرسال"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        old_token = res.data["raw_token"]
        inv_id = res.data["invitation"]["id"]

        # إعادة الإرسال
        res_resend = self.client.post(
            f"/api/employee-ops/invitations/{inv_id}/resend/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_resend.status_code, 200)
        new_token = res_resend.data["raw_token"]
        self.assertNotEqual(old_token, new_token)

        self.client.force_authenticate(user=None)
        # الرمز القديم يموت فوراً
        acc_old = self.client.post(
            f"/api/employee-ops/invitations/accept/{old_token}/",
            {"username": "user_old_tok", "password": "Password123!"},
        )
        self.assertEqual(acc_old.status_code, 400)

        # الرمز الجديد يعمل بنجاح
        acc_new = self.client.post(
            f"/api/employee-ops/invitations/accept/{new_token}/",
            {"username": "user_new_tok", "password": "Password123!"},
        )
        self.assertEqual(acc_new.status_code, 201)

    def test_public_accept_get_leaks_nothing_but_two_names(self):
        """صفحةٌ يفتحها مجهولٌ بالرابط: اسمُ الشركة واسمُ الموظف وعلمُ «يلزمه حساب» — لا غير.

        التأكيدُ على **مجموعة المفاتيح كاملةً** لا على غياب مفتاحٍ بعينه: حقلٌ
        يُضاف للردّ غداً (هاتفٌ أو معرّف) يُسقط هذا الاختبار، وهو المقصود.
        """
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "خالد بن الوليد", "phone": "0555123456"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token = res.data["raw_token"]

        self.client.force_authenticate(user=None)
        get_res = self.client.get(f"/api/employee-ops/invitations/accept/{token}/")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(
            set(get_res.data.keys()),
            {"company_name", "employee_name", "needs_account"},
        )
        self.assertEqual(get_res.data["company_name"], self.tenant_a.CompanyName)
        self.assertEqual(get_res.data["employee_name"], "خالد بن الوليد")
        self.assertTrue(get_res.data["needs_account"])
        self.assertNotIn("0555123456", str(get_res.data))

    def test_deactivate_frees_seat_and_keeps_history(self):
        """التعطيل يحرّر المقعد، وhr.Employee باقٍ وEmployeeProfile باقٍ، والعضويّةُ حُذفت."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "سالم العبدالله"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        token = res.data["raw_token"]
        emp_id = res.data["employee"]["id"]

        self.client.force_authenticate(user=None)
        self.client.post(
            f"/api/employee-ops/invitations/accept/{token}/",
            {"username": "salem_ops", "password": "Password123!"},
        )
        self.assertEqual(current_usage(self.tenant_a, "employee_ops.seats"), 1)

        user = User.objects.get(username="salem_ops")
        self.assertTrue(UserCompanyMembership.objects.filter(user=user, tenant=self.tenant_a).exists())

        # تعطيل الموظف
        self.client.force_authenticate(user=self.manager_a)
        deact = self.client.post(
            f"/api/employee-ops/employees/{emp_id}/deactivate/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(deact.status_code, 200)

        # تحرر المقعد
        self.assertEqual(current_usage(self.tenant_a, "employee_ops.seats"), 0)

        # السجل باقٍ
        emp = Employee.objects.get(id=emp_id)
        self.assertFalse(emp.is_active)
        self.assertTrue(EmployeeProfile.objects.filter(tenant=self.tenant_a, employee=emp).exists())

        # العضوية حذفت
        self.assertFalse(UserCompanyMembership.objects.filter(user=user, tenant=self.tenant_a).exists())

    def test_deactivate_does_not_touch_a_manager_membership(self):
        """موظفٌ عضويّتُه manager: التعطيل لا يحذف عضويّته."""
        emp = Employee.objects.create(
            tenant=self.tenant_a,
            name="المدير الموظف",
            code="MGR001",
            user=self.manager_a,
        )
        EmployeeProfile.objects.create(
            tenant=self.tenant_a,
            employee=emp,
        )

        self.client.force_authenticate(user=self.manager_a)
        deact = self.client.post(
            f"/api/employee-ops/employees/{emp.id}/deactivate/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(deact.status_code, 200)

        emp.refresh_from_db()
        self.assertFalse(emp.is_active)
        self.assertTrue(
            UserCompanyMembership.objects.filter(
                user=self.manager_a, tenant=self.tenant_a, role="manager"
            ).exists()
        )

    def test_tenant_isolation_on_employees_and_invitations(self):
        """مديرُ الشركة (أ) لا يرى ولا يعدّل موظفاً ولا دعوةً في الشركة (ب) (٤٠٤ لا ٤٠٣ على المستند غير المملوك)."""
        # إنشاء موظف ودعوة في شركة ب
        self.client.force_authenticate(user=self.manager_b)
        res_b = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف شركة ب"},
            HTTP_X_TENANT_ID=str(self.tenant_b.pk),
        )
        emp_b_id = res_b.data["employee"]["id"]
        inv_b_id = res_b.data["invitation"]["id"]

        # مدير شركة أ يحاول الوصول إلى موارد شركة ب
        self.client.force_authenticate(user=self.manager_a)

        # قراءة موظف شركة ب
        get_emp = self.client.get(
            f"/api/employee-ops/employees/{emp_b_id}/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(get_emp.status_code, 404)

        # تعديل موظف شركة ب
        patch_emp = self.client.patch(
            f"/api/employee-ops/employees/{emp_b_id}/",
            {"name": "اسم مخترق"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(patch_emp.status_code, 404)

        # دعوة موظف شركة ب
        invite_emp = self.client.post(
            f"/api/employee-ops/employees/{emp_b_id}/invite/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(invite_emp.status_code, 404)

        # تعطيل موظف شركة ب
        deact_emp = self.client.post(
            f"/api/employee-ops/employees/{emp_b_id}/deactivate/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(deact_emp.status_code, 404)

        # إعادة إرسال دعوة شركة ب
        resend_inv = self.client.post(
            f"/api/employee-ops/invitations/{inv_b_id}/resend/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(resend_inv.status_code, 404)

        # إلغاء دعوة شركة ب
        cancel_inv = self.client.post(
            f"/api/employee-ops/invitations/{inv_b_id}/cancel/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(cancel_inv.status_code, 404)

    def test_employee_list_query_count_is_small_and_does_not_grow(self):
        """عددُ الاستعلامات **ثابتٌ وصغير** — لا ثابتاً وحده.

        ثباتُ العدد بلا سقفٍ مطلق يمرّ بخمسين استعلاماً ما دامت خمسين في
        الحالتين. السقفُ هو ما يمنع N+1 فعلاً، والثباتُ يمنع نموّه مع الصفوف.
        """
        self.client.force_authenticate(user=self.manager_a)

        # إنشاء 3 موظفين
        for i in range(1, 4):
            self.client.post(
                "/api/employee-ops/employees/",
                {"name": f"موظف قياس {i}"},
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            )

        with CaptureQueriesContext(connection) as ctx_3:
            res_3 = self.client.get(
                "/api/employee-ops/employees/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            )
        self.assertEqual(res_3.status_code, 200)
        self.assertEqual(len(res_3.data), 3)
        count_3 = len(ctx_3)
        self.assertLessEqual(
            count_3, 6,
            f"قائمةُ الموظفين تُصدر {count_3} استعلاماً لثلاثة صفوف — استعلامٌ لكل صفّ.",
        )

        # إنشاء 7 موظفين إضافيين (المجموع 10)
        for i in range(4, 11):
            self.client.post(
                "/api/employee-ops/employees/",
                {"name": f"موظف قياس {i}"},
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            )

        with CaptureQueriesContext(connection) as ctx_10:
            res_10 = self.client.get(
                "/api/employee-ops/employees/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            )
        self.assertEqual(res_10.status_code, 200)
        self.assertEqual(len(res_10.data), 10)
        count_10 = len(ctx_10)

        self.assertEqual(
            count_3,
            count_10,
            f"عدد الاستعلامات نما مع عدد الموظفين! عند 3 موظفين: {count_3}، وعند 10 موظفين: {count_10}",
        )

    def test_module_does_not_create_accounting_account_for_the_employee(self):
        """موظفٌ مُنشأٌ من الموديول: employee.account_id is None. (إنشاءُ الحساب ملكيّةُ مسار الرواتب وحده.)"""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "موظف بلا حساب محاسبي"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 201)
        emp_id = res.data["employee"]["id"]
        emp = Employee.objects.get(id=emp_id)
        self.assertIsNone(emp.account_id)

    def test_returning_employee_keeps_the_same_account_and_history(self):
        """«العودةُ دعوةٌ جديدة على السجلّ نفسه فيتّصل تاريخه» (المواصفة §٤).

        العطبُ الذي يمنعه هذا الاختبار: التعطيلُ يحذف العضويّة ويُبقي
        `hr.Employee.user`، فكان القبولُ الثاني يرفض اسم المستخدم القديم ويُنشئ
        حساباً **ثانياً** — فتصير العضويّةُ على حسابٍ و`Employee.user` على حسابٍ
        ميّت، وينقطع التاريخ الذي وُعد باتّصاله.
        """
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "عائد إلى شركته"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        emp_id = res.data["employee"]["id"]

        self.client.force_authenticate(user=None)
        acc = self.client.post(
            f"/api/employee-ops/invitations/accept/{res.data['raw_token']}/",
            {"username": "returning_one", "password": "Password123!"},
        )
        self.assertEqual(acc.status_code, 201)
        first_user = Employee.objects.get(pk=emp_id).user
        self.assertIsNotNone(first_user)

        # غادر — تعطيلٌ لا حذف: المقعد يتحرّر والحساب والسجلّ يبقيان.
        self.client.force_authenticate(user=self.manager_a)
        self.assertEqual(
            self.client.post(
                f"/api/employee-ops/employees/{emp_id}/deactivate/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            200,
        )
        self.assertEqual(current_usage(self.tenant_a, "employee_ops.seats"), 0)

        # عاد: تفعيلُ السجلّ ثمّ دعوةٌ جديدة عليه.
        self.client.post(
            f"/api/employee-ops/employees/{emp_id}/reactivate/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        again = self.client.post(
            f"/api/employee-ops/employees/{emp_id}/invite/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(again.status_code, 201)

        # صفحةُ الدعوة تقول إنّه لا يلزمه حساب — فالشاشةُ لا تسأله كلمة مرور.
        self.client.force_authenticate(user=None)
        page = self.client.get(
            f"/api/employee-ops/invitations/accept/{again.data['raw_token']}/"
        )
        self.assertFalse(page.data["needs_account"])

        acc2 = self.client.post(
            f"/api/employee-ops/invitations/accept/{again.data['raw_token']}/", {}
        )
        self.assertEqual(acc2.status_code, 201)

        # **حسابٌ واحدٌ لا اثنان**، والعضويّة عليه، والسجلّ ما زال يشير إليه.
        self.assertEqual(User.objects.filter(username="returning_one").count(), 1)
        self.assertEqual(Employee.objects.get(pk=emp_id).user_id, first_user.pk)
        membership = UserCompanyMembership.objects.get(
            user=first_user, tenant=self.tenant_a
        )
        self.assertEqual(membership.role, FIELD_STAFF_ROLE)

    def test_employee_and_invitation_endpoints_are_404_when_module_disabled(self):
        """كلُّ نقاط المرحلة تختفي بإطفاء الوحدة — لا نقطةٌ واحدةٌ منها.

        حارسُ الوحدة في `initial()` لكلّ ViewSet، فسقوطُ واحدٍ منها في سهوٍ لا
        يظهر إن اختبرنا نقطةً واحدة.
        """
        TenantModule.objects.filter(
            tenant=self.tenant_a, module_key="employee_ops"
        ).update(enabled=False)
        invalidate_module_cache(self.tenant_a.pk)
        self.client.force_authenticate(user=self.manager_a)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant_a.pk)}

        for path in (
            "/api/employee-ops/settings/",
            "/api/employee-ops/employees/",
            "/api/employee-ops/invitations/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, **headers).status_code, 404)
        self.assertEqual(
            self.client.post(
                "/api/employee-ops/employees/", {"name": "لا يجب أن يُنشأ"}, **headers
            ).status_code,
            404,
        )
        self.assertFalse(
            Employee.objects.filter(tenant=self.tenant_a, name="لا يجب أن يُنشأ").exists()
        )

    def test_cancelled_invitation_cannot_be_revived_by_resend(self):
        """«تُلغى بضغطة» تعني ما تقوله — الملغاةُ لا تُحيا بإعادة إرسال."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/employees/",
            {"name": "ملغاة"},
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        inv_id = res.data["invitation"]["id"]
        self.assertEqual(
            self.client.post(
                f"/api/employee-ops/invitations/{inv_id}/cancel/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            200,
        )
        again = self.client.post(
            f"/api/employee-ops/invitations/{inv_id}/resend/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(again.status_code, 400)
        self.assertEqual(
            EmployeeInvitation.objects.get(pk=inv_id).status,
            EmployeeInvitation.STATUS_CANCELLED,
        )
