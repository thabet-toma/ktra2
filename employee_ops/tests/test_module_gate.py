"""اختبارات بوابات وترخيص وصلاحيات وحدة متابعة الموظفين."""
import re

from django.contrib.auth.models import User
from django.urls import Resolver404, resolve
from rest_framework.test import APITestCase

from core.access import (
    FIELD_STAFF_ROLE,
    ROLE_DEFAULTS,
    ROLE_MODULES,
    permission_catalog,
    user_permissions,
)
from core.models import TenantModule
from core.modules import invalidate_module_cache
from employee_ops.models import EmployeeOpsSettings
from employee_ops.urls import urlpatterns
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company


class EmployeeOpsModuleGateTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True})
        cls.manager_a = User.objects.create_user(username="mgr_a", password="x")
        cls.manager_b = User.objects.create_user(username="mgr_b", password="x")
        cls.staff_a = User.objects.create_user(username="staff_a", password="x")

        cls.tenant_a = create_company("شركة أ", cls.manager_a)
        cls.tenant_b = create_company("شركة ب", cls.manager_b)

        UserCompanyMembership.objects.create(
            user=cls.staff_a, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE
        )

    def test_settings_endpoint_returns_404_when_module_disabled(self):
        """شركةٌ بلا TenantModule للوحدة: GET /api/employee-ops/settings/ يردّ 404 (وليس 403 ولا 401)."""
        self.client.force_authenticate(user=self.staff_a)
        res = self.client.get(
            "/api/employee-ops/settings/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 404)

    def test_settings_endpoint_returns_404_for_manager_when_disabled(self):
        """حتى المدير (صلاحيات *) يرى 404 حين تكون الوحدة مطفأة — الترخيص قبل الصلاحية."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(
            "/api/employee-ops/settings/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 404)

    def test_settings_readable_by_manager_with_defaults_and_without_writing(self):
        """الوحدة مفعَّلة: المدير يقرأ الافتراضيات، و**القراءة لا تكتب صفّاً**.

        `GET` الذي يُنشئ صفّاً عطلٌ لا تحسين: يعطّل القراءة من نسخةٍ قرائية ويترك
        أثراً لمن نظر ولم يغيّر شيئاً.
        """
        TenantModule.objects.create(
            tenant=self.tenant_a, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(self.tenant_a.pk)

        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(
            "/api/employee-ops/settings/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(
            EmployeeOpsSettings.objects.filter(tenant=self.tenant_a).exists(),
            "طلبُ القراءة أنشأ صفّ إعدادات.",
        )
        self.assertEqual(res.data["points_full"], 10)
        self.assertEqual(res.data["points_partial"], 5)
        self.assertEqual(res.data["points_attendance"], 1)
        self.assertEqual(res.data["attendance_daily_cap"], 5)
        self.assertEqual(res.data["leaderboard_highlight_count"], 5)
        self.assertEqual(res.data["rejected_retention_months"], 12)
        self.assertEqual(res.data["invitation_expiry_days"], 7)

    def test_settings_closed_to_the_narrow_role_in_both_directions(self):
        """الموظف الميداني لا يقرأ إعدادات الشركة ولا يكتبها — ٤٠٣ لا ٤٠٤.

        الوحدة مرخَّصة هنا فوجودها ليس سرّاً؛ السرُّ هو أرقامُ الضبط. وقصّة
        المواصفة ٢٩ تجعل ضبط قيم النقاط للمدير.
        """
        TenantModule.objects.get_or_create(
            tenant=self.tenant_a, module_key="employee_ops", defaults={"enabled": True}
        )
        invalidate_module_cache(self.tenant_a.pk)

        self.client.force_authenticate(user=self.staff_a)
        self.assertEqual(
            self.client.get(
                "/api/employee-ops/settings/", HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                "/api/employee-ops/settings/",
                {"points_full": 25},
                format="json",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            403,
        )

    def test_manager_patch_persists_the_new_value(self):
        """قرارُ المدير يصل القاعدة فعلاً — لا يكفي أن يردّ 200."""
        TenantModule.objects.get_or_create(
            tenant=self.tenant_a, module_key="employee_ops", defaults={"enabled": True}
        )
        invalidate_module_cache(self.tenant_a.pk)

        self.client.force_authenticate(user=self.manager_a)
        res_ok = self.client.patch(
            "/api/employee-ops/settings/",
            {"points_full": 25},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_ok.status_code, 200)
        self.assertEqual(res_ok.data["points_full"], 25)
        self.assertEqual(
            EmployeeOpsSettings.objects.get(tenant=self.tenant_a).points_full, 25
        )

    def test_tenant_isolation_on_settings(self):
        """مستخدم الشركة (أ) لا يقرأ ولا يعدّل إعدادات الشركة (ب) ولو مرّر معرّفها في جسم الطلب."""
        TenantModule.objects.get_or_create(
            tenant=self.tenant_a, module_key="employee_ops", defaults={"enabled": True}
        )
        TenantModule.objects.get_or_create(
            tenant=self.tenant_b, module_key="employee_ops", defaults={"enabled": True}
        )
        invalidate_module_cache(self.tenant_a.pk)
        invalidate_module_cache(self.tenant_b.pk)

        # التأكد من وجود صف إعدادات افتراضي لكل شركة
        EmployeeOpsSettings.objects.get_or_create(tenant=self.tenant_a)
        settings_b, _ = EmployeeOpsSettings.objects.get_or_create(tenant=self.tenant_b)

        self.client.force_authenticate(user=self.manager_a)
        res = self.client.patch(
            "/api/employee-ops/settings/",
            {"tenant": self.tenant_b.pk, "points_full": 99},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            EmployeeOpsSettings.objects.get(tenant=self.tenant_a).points_full, 99
        )
        settings_b.refresh_from_db()
        self.assertEqual(settings_b.points_full, 10)

        # محاولة الوصول لسياق شركة ب مباشرة برأس الطلب تُرد بـ 403 لعدم العضوية
        res_cross = self.client.get(
            "/api/employee-ops/settings/",
            HTTP_X_TENANT_ID=str(self.tenant_b.pk),
        )
        self.assertEqual(res_cross.status_code, 403)

    def test_module_registers_no_browsable_root_index(self):
        """جذرُ الوحدة لا يُحلّ إلى عرضٍ أصلاً.

        `DefaultRouter` يسجّل عرضاً على الجذر، فيصير `/api/employee-ops/` صفحةً
        تسرد كلّ مسارات الوحدة — **وهي غير محروسة** بـ`require_module`، فتكشف
        وجودَ الوحدة لشركةٍ لم تشترِها.

        والتأكيدُ **سلوكيّ لا جدولُ مساراتٍ يُحدَّث مع كلّ مرحلة**: قائمةٌ حرفيّةٌ
        بالمسارات المتوقَّعة تصير عبئاً يُعدَّل بلا تفكير، وتفقد معناها. هنا: لو
        أُدخل راوترٌ كامل سقط الاختبارُ فوراً ولو أُضيفت عشرُ نقاطٍ مشروعة مرّ.
        """
        with self.assertRaises(Resolver404):
            resolve("/api/employee-ops/")

        for pattern in urlpatterns:
            name = getattr(pattern, "name", None)
            if name:
                self.assertFalse(
                    name.endswith("-api-root"),
                    f"المسار {name} يكشف فهرس جذر قابل للتصفح.",
                )

    def test_narrow_role_is_not_named_employee(self):
        """الدور الضيّق اسمه field_staff وليس employee المحجوز."""
        self.assertNotIn("employee", ROLE_DEFAULTS)
        self.assertEqual(
            ROLE_DEFAULTS[FIELD_STAFF_ROLE], frozenset({"employee_ops.self"})
        )
        self.assertEqual(ROLE_MODULES[FIELD_STAFF_ROLE], "employee_ops")

    def test_module_permission_keys_hidden_when_module_disabled(self):
        """permission_catalog لا يحوي مفاتيح employee_ops حين تكون الوحدة مطفأة، ويحويهما حين تُفعَّل."""
        tenant_fresh = create_company("شركة اختبار الصلاحيات", self.manager_b)
        catalog_disabled = permission_catalog(tenant_fresh)
        self.assertFalse(
            any(p["key"].startswith("employee_ops.") for p in catalog_disabled)
        )

        TenantModule.objects.create(
            tenant=tenant_fresh, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(tenant_fresh.pk)

        catalog_enabled = permission_catalog(tenant_fresh)
        keys_enabled = {
            p["key"] for p in catalog_enabled if p["key"].startswith("employee_ops.")
        }
        self.assertEqual(keys_enabled, {"employee_ops.self", "employee_ops.manage"})

    def test_field_staff_holds_exactly_one_permission(self):
        """الدور الضيّق يملك `employee_ops.self` **ولا شيء غيرها**.

        تعدادُ بادئاتٍ ممنوعة يترك ما لم يُعدَّ (`store.*` · `finance.*` ·
        `admin.*` · `tax.*`) يمرّ أخضر. المساواةُ بالمجموعة كاملةً هي التأكيد
        الذي يسقط عند أيّ منحٍ عابر.
        """
        TenantModule.objects.get_or_create(
            tenant=self.tenant_a, module_key="employee_ops", defaults={"enabled": True}
        )
        invalidate_module_cache(self.tenant_a.pk)

        self.assertEqual(
            set(user_permissions(self.staff_a, self.tenant_a)),
            {"employee_ops.self"},
        )

    def test_narrow_role_is_assignable_through_the_members_api(self):
        """الدورُ مذكورٌ في `ROLE_CHOICES` — وإلا كان دوراً لا يستطيع مديرٌ منحه.

        ثلاث نقاط تحقّقٍ في المنصّة تبني قائمة الأدوار الصالحة من `ROLE_CHOICES`
        (`core/permissions_api.py` و`tenants/views.py`)، فدورٌ غائبٌ عنها يُرفض
        من كلّ واجهة — واختباراتٌ تصنع العضويّة بـ`objects.create` تتخطّى ذلك
        فتحرس حالةً لا يمكن بلوغها.
        """
        self.assertIn(
            FIELD_STAFF_ROLE,
            {role for role, _ in UserCompanyMembership.ROLE_CHOICES},
        )


class EmployeeOpsEveryRouteIsGatedTest(APITestCase):
    """**حارسٌ معمَّم**: كلُّ مسارٍ تسجّله الوحدة يختفي بإطفائها — بلا قائمةٍ يدويّة.

    القوائمُ اليدويّة في ملفّات الاختبار تحرس ما كُتب فيها يومَ كُتبت؛ ونقطةٌ
    تُضاف في مرحلةٍ لاحقة وتُنسى تمرّ بلا حارس. هذا الاختبار **يعدّ المسارات من
    `employee_ops.urls` نفسِها**، فيغطّي ما لم يُكتب بعد.
    """

    #: المُعفى الوحيد — بسببٍ مكتوب. نقطةُ قبول الدعوة **عامّةٌ بلا مصادقة**
    #: وحارسُها الرمز: رمزٌ لا وجود له يُردّ 400 قبل أن يُعرف صاحبُ الشركة أصلاً،
    #: فلا سبيل لبلوغ فحص الترخيص برمزٍ وهميّ. وحالتُها الحقيقيّة (رمزٌ صالحٌ
    #: لشركةٍ سُحب ترخيصُها ⇒ 404) مُختبَرةٌ في `test_seats_and_invitations.py`.
    EXEMPT = {"employee-ops-invitation-accept"}

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager = User.objects.create_user(username="gate_all_mgr", password="x")
        cls.tenant = create_company("شركة الحارس المعمَّم", cls.manager)
        invalidate_module_cache(cls.tenant.pk)

    def _concrete_paths(self):
        """مساراتٌ حقيقيّةٌ من `urlpatterns` مع تعويض المعاملات برقمٍ ورمزٍ صالحين."""
        from employee_ops import urls as module_urls

        paths = []
        for entry in module_urls.urlpatterns:
            sub = getattr(entry, "url_patterns", None)
            children = sub if sub is not None else [entry]
            prefix = str(entry.pattern) if sub is not None else ""
            for child in children:
                name = getattr(child, "name", None)
                if name in self.EXEMPT:
                    continue
                route = prefix + str(child.pattern)
                route = re.sub(r"<[^>]*pk>", "1", route)
                route = re.sub(r"<[^>]+>", "x", route)
                if "(?" in route or "\\" in route:  # تعبيرٌ نمطيّ لا نستطيع تعويضه
                    continue
                paths.append("/api/employee-ops/" + route)
        return sorted(set(paths))

    def test_every_registered_route_is_404_while_the_module_is_disabled(self):
        paths = self._concrete_paths()
        self.assertGreaterEqual(
            len(paths), 8, f"لم يُلتقط إلا {len(paths)} مساراً — الماشي لا يرى المسارات.",
        )
        self.client.force_authenticate(user=self.manager)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}
        for path in paths:
            for method in ("get", "post"):
                res = getattr(self.client, method)(path, {}, format="json", **headers)
                if res.status_code == 405:
                    continue  # الفعلُ غير مسموحٍ على هذا المسار — لا يقول شيئاً عن البوّابة
                with self.subTest(path=path, method=method):
                    self.assertEqual(
                        res.status_code, 404,
                        f"{method.upper()} {path} ردّ {res.status_code} والوحدة مطفأة.",
                    )

    def test_the_same_routes_stop_returning_404_once_the_module_is_enabled(self):
        """وإلا كان الاختبارُ أعلاه يمرّ لأنّ المسارات غير موجودةٍ أصلاً."""
        TenantModule.objects.create(
            tenant=self.tenant, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(self.tenant.pk)
        self.client.force_authenticate(user=self.manager)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

        live = [
            self.client.get(path, **headers).status_code
            for path in ("/api/employee-ops/settings/", "/api/employee-ops/tasks/")
        ]
        self.assertEqual(live, [200, 200])
