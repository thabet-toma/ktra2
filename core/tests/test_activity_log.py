"""سجل النشاط الموحّد (core.ActivityLog + core.activity + api/activity).

يتحقق:
  - log_activity ينشئ صفاً بالحقول الصحيحة، وأي فشل داخله يُبتلع (غير حاظر).
  - الصفحة العامة (بلا entity_id) للمدير فقط؛ سجل مستند واحد متاح لأي عضو.
  - الافتراضي = اليوم؛ أحداث is_view مستبعَدة من العام وتظهر مع include_views.
  - login/logout يُسجَّلان في سجل النشاط.
"""
import json

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from core.activity import log_activity, log_view
from core.models import ActivityLog
from tenants.models import UserCompanyMembership
from tenants.services import create_company


class ActivityServiceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="mgr", password="x")
        cls.tenant = create_company("شركة السجل", cls.manager)

    def test_log_activity_creates_row(self):
        log_activity(
            action="create", entity_type="sales_invoice", entity_id=7,
            entity_label="INV-7", description="إنشاء", tenant=self.tenant, user=self.manager,
        )
        row = ActivityLog.objects.get(entity_type="sales_invoice", entity_id=7)
        assert row.action == "create"
        assert row.tenant_id == self.tenant.TenantID
        assert row.user_id == self.manager.id
        assert row.is_view is False

    def test_log_view_marks_is_view(self):
        log_view(entity_type="deal", entity_id=3, entity_label="D-0003", tenant=self.tenant, user=self.manager)
        row = ActivityLog.objects.get(entity_type="deal", entity_id=3)
        assert row.is_view is True
        assert row.action == "view"

    def test_failure_is_swallowed(self):
        # مجموعة غير قابلة للتسلسل JSON → create يفشل داخلياً ويُبتلع (لا استثناء).
        before = ActivityLog.objects.count()
        log_activity(
            action="create", entity_type="x", metadata={"bad": {1, 2, 3}},
            tenant=self.tenant, user=self.manager,
        )
        assert ActivityLog.objects.count() == before  # لم يُنشأ صف، ولم يُرمَ استثناء

    def test_no_tenant_is_noop(self):
        # شركة ثانية تُعطّل auto-resolve أحادي الشركة، فيبقى tenant=None فعلاً.
        create_company("شركة ثانية", User.objects.create_user(username="mgr2", password="x"))
        before = ActivityLog.objects.count()
        log_activity(action="create", entity_type="x", tenant=None, request=None, user=self.manager)
        assert ActivityLog.objects.count() == before


class ActivityApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="boss2", password="x")
        cls.staff = User.objects.create_user(username="staff2", password="x")
        cls.tenant = create_company("شركة API السجل", cls.manager)
        UserCompanyMembership.objects.create(user=cls.staff, tenant=cls.tenant, role="staff")

    def _h(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _seed(self):
        log_activity(action="create", entity_type="sales_invoice", entity_id=1,
                     entity_label="INV-1", tenant=self.tenant, user=self.manager)
        log_view(entity_type="sales_invoice", entity_id=1, entity_label="INV-1",
                 tenant=self.tenant, user=self.staff)

    def test_global_feed_manager_only(self):
        self._seed()
        # غير المدير ممنوع من الصفحة العامة (بلا entity_id)
        assert self.client.get("/api/activity/", **self._h(self.staff)).status_code == 403
        # المدير مسموح
        res = self.client.get("/api/activity/", **self._h(self.manager))
        assert res.status_code == 200, res.content

    def test_global_feed_excludes_views_by_default(self):
        self._seed()
        res = self.client.get("/api/activity/", **self._h(self.manager))
        data = res.json()
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        actions = {r["action"] for r in rows}
        assert "create" in actions
        assert "view" not in actions  # أحداث العرض مستبعَدة من الجدول العام

    def test_include_views_shows_views(self):
        self._seed()
        res = self.client.get(
            f"/api/activity/?user={self.staff.id}&include_views=true", **self._h(self.manager))
        rows = res.json().get("results", res.json())
        assert any(r["action"] == "view" for r in rows)

    def test_entity_scoped_feed_open_to_member(self):
        self._seed()
        # سجل مستند واحد متاح للموظف العادي (ليس صفحة عامة)
        res = self.client.get(
            "/api/activity/?entity_type=sales_invoice&entity_id=1", **self._h(self.staff))
        assert res.status_code == 200, res.content
        rows = res.json().get("results", res.json())
        # سجل المستند يشمل العرض والتعديل معاً
        assert len(rows) >= 2

    def test_default_date_is_today(self):
        # صف قديم (بالأمس) يجب ألا يظهر في العرض العام الافتراضي.
        old = ActivityLog.objects.create(
            tenant=self.tenant, user=self.manager, action="create",
            entity_type="sales_invoice", entity_id=99, entity_label="OLD")
        ActivityLog.objects.filter(pk=old.pk).update(
            timestamp=timezone.now() - timezone.timedelta(days=1))
        log_activity(action="create", entity_type="sales_invoice", entity_id=100,
                     entity_label="NEW", tenant=self.tenant, user=self.manager)
        res = self.client.get("/api/activity/", **self._h(self.manager))
        rows = res.json().get("results", res.json())
        ids = {r["entity_id"] for r in rows}
        assert 100 in ids and 99 not in ids


class SessionEventTest(APITestCase):
    def test_login_and_logout_logged(self):
        user = User.objects.create_user(username="sess@x.com", email="sess@x.com", password="pw", is_active=True)
        tenant = create_company("شركة الجلسة", user)  # يجعل user مديراً/عضواً

        res = self.client.post(
            "/api/hr/auth/login/",
            data=json.dumps({"email": "sess@x.com", "password": "pw"}),
            content_type="application/json",
        )
        assert res.status_code == 200, res.content
        token = res.json()["token"]
        assert ActivityLog.objects.filter(
            tenant=tenant, user=user, action="login", entity_type="session").exists()

        out = self.client.post(
            "/api/hr/auth/logout/", HTTP_AUTHORIZATION=f"Token {token}")
        assert out.status_code == 200, out.content
        assert ActivityLog.objects.filter(
            tenant=tenant, user=user, action="logout", entity_type="session").exists()
