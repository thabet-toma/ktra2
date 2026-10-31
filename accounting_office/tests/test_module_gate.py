"""بوابة ترخيص وحدة مكتب المحاسبة — #271.

**القاعدة المركزيّة:** كلُّ نقطة تحت `/api/accounting-office/` تمرّ بـ
`require_module(request, "accounting_office")` فتردّ **404** لشركةٍ غير مرخّصة.
404 لا 403: 403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً.

والحارسُ **معمَّم** لا قائمةً يدويّة: المسارات تُقرأ من `accounting_office/urls.py`
نفسها، فنقطةٌ تُضاف في تذكرةٍ لاحقة وتُنسى محروسةٌ تلقائياً.
"""
import re

from django.contrib.auth.models import User
from django.urls import Resolver404, resolve
from rest_framework.test import APITestCase

from core.models import TenantModule
from core.modules import MODULES, invalidate_module_cache, module_enabled
from accounting_office.models import OfficeClient, TaxCard
from tenants.models import Currency
from tenants.services import create_company, switch_company_template

BASE = "/api/accounting-office/"


def enable_module(tenant):
    """ترخيص الوحدة لشركةٍ في الاختبار — الصفّ ثم إبطال الكاش."""
    license_row = TenantModule.objects.create(
        tenant=tenant, module_key="accounting_office", enabled=True,
    )
    invalidate_module_cache(tenant.pk)
    return license_row


class AccountingOfficeLicenceGateTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager = User.objects.create_user(username="office_mgr", password="x")
        cls.tenant = create_company("مكتب النور", cls.manager)
        invalidate_module_cache(cls.tenant.pk)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def _concrete_paths(self):
        """مساراتٌ حقيقيّةٌ من `urlpatterns` نفسها، بمعاملاتٍ مُعوَّضة.

        الراوتر يكتب معاملاته تعبيراً نمطياً (`(?P<pk>[^/.]+)`) لا بـ`<int:pk>`،
        فالتعويض هنا نوعان: تعبيرُ الراوتر، ومسارُ `path()` العادي.
        """
        from accounting_office import urls as module_urls

        def concretize(route: str) -> str:
            route = re.sub(r"\(\?P<pk>[^)]*\)", "1", route)
            route = re.sub(r"\(\?P<contact_id>[^)]*\)", "1", route)
            route = re.sub(r"\(\?P<client_service_id>[^)]*\)", "1", route)
            route = re.sub(r"\(\?P<key>[^)]*\)", "tax_system", route)
            route = re.sub(r"<[^>]*pk>", "1", route)
            route = re.sub(r"<[^>]+>", "x", route)
            return route.replace("^", "").replace("$", "")

        paths = []
        for entry in module_urls.urlpatterns:
            sub = getattr(entry, "url_patterns", None)
            children = sub if sub is not None else [entry]
            prefix = str(entry.pattern) if sub is not None else ""
            for child in children:
                route = concretize(prefix + str(child.pattern))
                if "(?" in route or "\\" in route:  # تعبيرٌ نمطيّ لا نستطيع تعويضه
                    continue
                paths.append(BASE + route)
        return sorted(set(paths))

    def test_no_route_is_reachable_without_the_licence(self):
        paths = self._concrete_paths()
        self.assertGreaterEqual(
            len(paths), 10,
            f"لم يُلتقط إلا {len(paths)} مساراً — الماشي لا يرى المسارات.",
        )
        self.client.force_authenticate(user=self.manager)
        for path in paths:
            for method in ("get", "post", "put", "delete", "options"):
                res = getattr(self.client, method)(path, {}, format="json", **self.headers())
                if res.status_code == 405:
                    continue  # الفعل غير مسموحٍ على هذا المسار — لا يقول شيئاً عن البوّابة
                with self.subTest(path=path, method=method):
                    self.assertEqual(
                        res.status_code, 404,
                        f"{method.upper()} {path} ردّ {res.status_code} والوحدة مطفأة.",
                    )

    def test_the_same_routes_stop_returning_404_once_licensed(self):
        """وإلا كان الاختبار أعلاه يمرّ لأنّ المسارات غير موجودةٍ أصلاً.

        والفحصُ يمرّ على **كل** مسارٍ ولّده `_concrete_paths` — لا ثلاثةً منتقاة.
        والمقياسُ **`OPTIONS` → 200**: `OfficeModuleViewSet.initial` ينادي
        `require_module` ولـOPTIONS أيضاً، و`SimpleMetadata.determine_actions`
        يبتلع `Http404` من `get_object` — فتردّ 200 لكل مسارٍ والوحدةُ مرخَّصة ولو
        لم يوجد الكائن، و404 بلا ترخيص. (حلُّ المسار `resolve` لا يتغيّر بالترخيص
        فلا يصلح مقياساً.) وثلاثةُ ردودِ GET معروفةٍ (200) تثبت أن التسجيل يعمل.
        """
        enable_module(self.tenant)
        client = OfficeClient.objects.create(tenant=self.tenant, name="زبون البوّابة")
        TaxCard.objects.create(client=client)
        self.client.force_authenticate(user=self.manager)
        headers = self.headers()

        paths = self._concrete_paths()
        self.assertGreaterEqual(len(paths), 10)
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.options(path, **headers).status_code, 200)
        self.assertEqual(
            self.client.get(f"{BASE}clients/", **headers).status_code, 200,
        )
        self.assertEqual(
            self.client.get(f"{BASE}clients/{client.pk}/tax-card/", **headers).status_code, 200,
        )
        self.assertEqual(
            self.client.get(f"{BASE}settings/", **headers).status_code, 200,
        )

    def test_options_on_a_setting_key_answers_200_not_500(self):
        """انحدار: `OPTIONS` على `settings/<key>/` كان يسقط بـ`AssertionError` (500).

        `SimpleMetadata.determine_actions` ينادي `get_object` لفعل `PUT`، ولا
        queryset لسجلّ الإعدادات.
        """
        enable_module(self.tenant)
        self.client.force_authenticate(user=self.manager)
        res = self.client.options(f"{BASE}settings/tax_system/", **self.headers())
        self.assertEqual(res.status_code, 200)

    def test_the_module_registers_no_browsable_root_index(self):
        """جذر الوحدة لا يُحلّ إلى عرضٍ أصلاً — `DefaultRouter` يكشف وجودها بلا حارس."""
        with self.assertRaises(Resolver404):
            resolve(BASE)

        from accounting_office import urls as module_urls

        for pattern in module_urls.urlpatterns:
            name = getattr(pattern, "name", None)
            if name:
                self.assertFalse(name.endswith("-api-root"))

    def test_the_module_key_exists_in_the_registry_with_the_agreed_plan(self):
        definition = MODULES.get("accounting_office")
        self.assertIsNotNone(definition, "الوحدة غير مسجّلة في core.modules.MODULES.")
        self.assertEqual(definition["label"], "مكتب المحاسبة")
        self.assertEqual(definition["plans"], ("Pro", "Enterprise"))
        self.assertIsNone(definition["legacy_flag"])


class AccountingOfficeTemplateLicenceTest(APITestCase):
    """القالب الجديد **هو** المنتج: يُرخّص الوحدة عند الإنشاء، والقديم لا يمسّه."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager = User.objects.create_user(username="office_tpl_mgr", password="x")

    def test_the_new_template_grants_the_licence_on_creation(self):
        tenant = create_company("مكتب جديد بالقالب", self.manager, template="accounting_office")
        invalidate_module_cache(tenant.pk)

        self.assertEqual(tenant.template, "accounting_office")
        self.assertTrue(
            module_enabled(tenant, "accounting_office"),
            "قالب accounting_office لم يُرخّص وحدته عند الإنشاء.",
        )

    def test_general_and_the_old_office_template_do_not_grant_the_licence(self):
        general = create_company("شركة عامة", self.manager, template="general")
        old_office = create_company("مكتب قديم", self.manager, template="accounting_firm")
        invalidate_module_cache(general.pk)
        invalidate_module_cache(old_office.pk)

        self.assertFalse(module_enabled(general, "accounting_office"))
        self.assertFalse(module_enabled(old_office, "accounting_office"))
        self.assertFalse(
            TenantModule.objects.filter(module_key="accounting_office").exclude(
                tenant__template="accounting_office",
            ).exists(),
            "زُرع ترخيص مكتب المحاسبة لقالبٍ آخر.",
        )

    def test_switching_to_the_new_template_does_not_grant_a_licence(self):
        """نقطة الزرع واحدة في `create_company` — التبديل اللاحق لا يمنح تراخيص."""
        tenant = create_company("شركة تتحوّل للقالب", self.manager, template="general")
        switch_company_template(tenant, "accounting_office")
        tenant.refresh_from_db()
        invalidate_module_cache(tenant.pk)

        self.assertEqual(tenant.template, "accounting_office")
        self.assertFalse(module_enabled(tenant, "accounting_office"))

    def test_a_member_of_an_unlicensed_company_gets_404_not_403(self):
        """حتى المدير — الترخيص قبل الصلاحية."""
        tenant = create_company("شركة بلا ترخيص", self.manager, template="general")
        invalidate_module_cache(tenant.pk)
        self.client.force_authenticate(user=self.manager)

        res = self.client.get(f"{BASE}clients/", HTTP_X_TENANT_ID=str(tenant.pk))
        self.assertEqual(res.status_code, 404)

    def test_a_non_member_cannot_reach_the_module(self):
        """شركةٌ مرخّصة لكن المستخدم ليس عضواً فيها — لا يراها."""
        tenant = create_company("مكتب غيري", self.manager, template="accounting_office")
        invalidate_module_cache(tenant.pk)
        outsider = User.objects.create_user(username="office_outsider", password="x")
        # شركتُه الخاصة تُنشئ عضويّته تلقائياً؛ وهو ليس عضواً في `tenant`.
        create_company("شركتي أنا", outsider)
        self.client.force_authenticate(user=outsider)

        res = self.client.get(f"{BASE}clients/", HTTP_X_TENANT_ID=str(tenant.pk))
        # 403: `get_tenant` يرفض غير العضو بـ`PermissionDenied` قبل فحص الترخيص،
        # و`require_module` يعيد رفعه كما هو (يحوّله 404 لـ`accountant_portal` وحده).
        self.assertEqual(res.status_code, 403)
