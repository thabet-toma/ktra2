"""حارسُ العقد بين حمولة `/api/my-agent/` وأنواع الواجهة التي تقرؤها (#207 م٧-ب).

**لماذا هذا الحارس موجود.** `tsc` في هذا المستودع لا يفحص خصائصَ JSX ولا شكلَ ما
يصل من الشبكة: واجهةٌ (`interface`) تُعلن حقلاً لا يرسله الخادمُ تمرّ خضراءَ في
`npm test` و`tsc` معاً، ثمّ يُصيَّر الحقلُ **فراغاً** على الشاشة بلا خطأٍ في أيّ سجلّ.

وقد وقع ذلك بالضبط في تسليم م٧-ب الأوّل: عشرةُ حقولٍ مخترَعةٍ في
`services/myAgentApi.ts` (`agent.employee_id` و`granted_at` و`created_at` لسجلّ
النشاط و`sample_size`…)، فكانت الشاشةُ تُرسل `employee_id: undefined` فيتعذّر
التقييمُ أصلاً، وتُظهر جدولَ صلاحيّاتٍ كلُّ صفوفه فارغةٌ وعمودَ حالةٍ يقول «معطلة»
عن عضويّاتٍ حيّة.

فالحارسُ يقرأ أسماءَ الحقول من ملفّ الواجهة نفسِه ويقابلها بحمولةٍ **حقيقيّةٍ**
يبنيها الخادم. وهو باتّجاهٍ واحد عمداً: حقلٌ يعلنه الخادمُ ولا تقرؤه الواجهةُ
مقبول، أمّا حقلٌ تقرؤه الواجهةُ ولا يرسله الخادمُ فعطبٌ صامت.
"""
import datetime
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.models import ActivityLog
from tenants.models import Tenant, UserCompanyMembership

from platform_ops.models import (
    AgentGrantedMembership,
    DailyRating,
    Engagement,
    PlatformEmployee,
    ServiceSubscription,
    WorkOrder,
    WorkOrderDeliverable,
)

User = get_user_model()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MY_AGENT_API = REPO_ROOT / "frontend_v2" / "services" / "myAgentApi.ts"
AGENT_BOOKS_UTIL = REPO_ROOT / "frontend_v2" / "utils" / "agentBooks.ts"

#: تعليقاتُ الكتلة والسطر — تُنزَع قبل القراءة كي لا يُقرأ مثالٌ في تعليقٍ حقلاً.
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"^\s*//.*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^\s{2}([a-z_][A-Za-z0-9_]*)\??\s*:", re.MULTILINE)


def _interface_fields(source_text: str, name: str) -> set[str]:
    """أسماءُ حقول `interface <name>` من نصّ TypeScript — بلا تعليقاتٍ ولا حقولٍ متداخلة."""
    cleaned = _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", source_text))
    match = re.search(
        r"export interface " + re.escape(name) + r"\s*\{(.*?)^\}",
        cleaned,
        re.DOTALL | re.MULTILINE,
    )
    if match is None:  # pragma: no cover - يسقط الاختبار برسالته أدناه
        return set()
    return set(_FIELD_RE.findall(match.group(1)))


class MyAgentFrontendContractTest(TestCase):
    """كلُّ حقلٍ تعلنه أنواعُ الواجهة موجودٌ فعلاً في حمولة الخادم."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            TenantID=7301, CompanyName="شركة عقد الواجهة",
        )
        self.owner = User.objects.create_user(
            username="contract_owner", email="contract_owner@test.local",
        )
        UserCompanyMembership.objects.create(
            user=self.owner, tenant=self.tenant, role="manager",
        )
        self.agent_user = User.objects.create_user(
            username="contract_agent", email="contract_agent@test.local",
            first_name="راشد", last_name="الوكيل",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.agent_user, specialty="accountant",
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.engagement = Engagement.objects.create(
            tenant=self.tenant, employee=self.employee,
            status=Engagement.Status.ACTIVE,
        )
        today = timezone.localdate()
        moment = timezone.make_aware(
            datetime.datetime.combine(today, datetime.time(11, 0))
        )
        WorkOrder.objects.create(
            tenant=self.tenant, assignee=self.employee, title="إقفال الشهر",
            status=WorkOrder.Status.APPROVAL, approved_at=moment, received_at=moment,
        )
        DailyRating.objects.create(
            tenant=self.tenant, employee=self.employee,
            service_date=today, stars=4, note="",
        )
        AgentGrantedMembership.objects.create(
            tenant=self.tenant, acting_employee=self.employee,
            engagement=self.engagement, user=self.owner,
            target_user_id=self.owner.pk,
            identity_snapshot={"username": self.owner.username, "full_name": "صاحب الشركة"},
            role_before="", role_after="accountant",
        )
        ActivityLog.objects.create(
            tenant=self.tenant, user=self.agent_user, action="update",
            entity_type="sales_invoice", entity_label="#4120",
            metadata={"old_total": "100.00", "new_total": "250.00"},
            description="تعديل مستند",
        )
        self.client = APIClient()
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.pk))
        self.client.force_authenticate(user=self.owner)

    def _payload(self):
        resp = self.client.get("/api/my-agent/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data

    def _assert_declared_fields_exist(self, *, interface, declared, actual, note=""):
        self.assertTrue(
            declared,
            f"لم يُعثَر على `interface {interface}` — هل أُعيدت تسميتُه؟",
        )
        missing = declared - set(actual)
        self.assertEqual(
            missing,
            set(),
            f"`{interface}` يعلن حقولاً لا يرسلها الخادم: {sorted(missing)}. {note}",
        )

    def test_books_tab_interfaces_match_the_real_payload(self):
        """حقولُ `MyBooksTabData` وما تحتها موجودةٌ في حمولةٍ حقيقيّة."""
        api_src = MY_AGENT_API.read_text(encoding="utf-8")
        payload = self._payload()

        self._assert_declared_fields_exist(
            interface="MyBooksTabData",
            declared=_interface_fields(api_src, "MyBooksTabData"),
            actual=payload.keys(),
        )
        self.assertTrue(payload["agents"], "التركيبةُ لم تُنتج وكيلاً نشطاً")
        self._assert_declared_fields_exist(
            interface="AgentInfo",
            declared=_interface_fields(api_src, "AgentInfo"),
            actual=payload["agents"][0].keys(),
            note="بطاقةُ الوكيل تقرأ هذه الحقول لتُرسل معرّفَ الموظّف مع التقييم.",
        )
        self.assertTrue(payload["granted_memberships"], "التركيبةُ لم تُنتج صفَّ صلاحيّات")
        self._assert_declared_fields_exist(
            interface="GrantedMembership",
            declared=_interface_fields(api_src, "GrantedMembership"),
            actual=payload["granted_memberships"][0].keys(),
        )
        self.assertTrue(payload["activity_log"], "التركيبةُ لم تُنتج صفَّ نشاط")
        self._assert_declared_fields_exist(
            interface="ActivityLogItem",
            declared=_interface_fields(api_src, "ActivityLogItem"),
            actual=payload["activity_log"][0].keys(),
        )
        self.assertIsNotNone(
            payload["agents"][0]["today_rating"], "تقييمُ اليوم لم يصل مع التبويب",
        )
        self._assert_declared_fields_exist(
            interface="TodayRating",
            declared=_interface_fields(api_src, "TodayRating"),
            actual=payload["agents"][0]["today_rating"].keys(),
        )

    def test_link_and_summary_interfaces_match_their_endpoints(self):
        """`GenerateLinkResult` و`EmployeeRatingsSummary` — تقرؤهما بطاقةُ الوكيل أيضاً."""
        api_src = MY_AGENT_API.read_text(encoding="utf-8")

        link = self.client.post(
            "/api/my-agent/daily-ratings/generate-link/",
            {
                "employee_id": self.employee.pk,
                "service_date": timezone.localdate().isoformat(),
            },
        )
        self.assertEqual(link.status_code, status.HTTP_201_CREATED, link.data)
        self._assert_declared_fields_exist(
            interface="GenerateLinkResult",
            declared=_interface_fields(api_src, "GenerateLinkResult"),
            actual=link.data.keys(),
        )

        summary = self.client.get(
            "/api/my-agent/daily-ratings/summary/", {"employee_id": self.employee.pk},
        )
        self.assertEqual(summary.status_code, status.HTTP_200_OK, summary.data)
        self._assert_declared_fields_exist(
            interface="EmployeeRatingsSummary",
            declared=_interface_fields(api_src, "EmployeeRatingsSummary"),
            actual=summary.data.keys(),
        )

    def test_health_score_types_match_both_surfaces(self):
        """نوعا الصحّة في `utils/agentBooks.ts` يطابقان ما يعيده السطحان معاً."""
        util_src = AGENT_BOOKS_UTIL.read_text(encoding="utf-8")
        health = self._payload()["health_scores"]

        self._assert_declared_fields_exist(
            interface="TwoHealthScores",
            declared=_interface_fields(util_src, "TwoHealthScores"),
            actual=health.keys(),
        )
        dimension_fields = _interface_fields(util_src, "HealthScoreDimension")
        for key in ("service_health", "customer_cooperation"):
            self._assert_declared_fields_exist(
                interface=f"HealthScoreDimension ({key})",
                declared=dimension_fields,
                actual=health[key].keys(),
            )

        # فحص بنية صفوف الأسباب (HealthCauseItem)
        wo = WorkOrder.objects.filter(tenant=self.tenant).first()
        WorkOrderDeliverable.objects.create(
            work_order=wo,
            tenant=self.tenant,
            kind=WorkOrderDeliverable.Kind.NOTE,
            review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
        )
        health_with_causes = self._payload()["health_scores"]
        cause_fields = _interface_fields(util_src, "HealthCauseItem")
        self.assertTrue(health_with_causes["service_health"]["breakdown"])
        self._assert_declared_fields_exist(
            interface="HealthCauseItem",
            declared=cause_fields,
            actual=health_with_causes["service_health"]["breakdown"][0].keys(),
        )

        # ونفسُ الشكلِ على سطح السوبر أدمن — مصدرُهما دالّةٌ واحدة.
        admin = User.objects.create_user(
            username="contract_super", email="contract_super@test.local",
            is_staff=True, is_superuser=True,
        )
        admin_client = APIClient()
        admin_client.force_authenticate(user=admin)
        # 210-A §١: صحةُ الشركة على سطح السوبر أدمن لا تُفتح إلا لشركةٍ مؤهَّلة.
        ServiceSubscription.objects.create(tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE)
        resp = admin_client.get(f"/api/platform/ops/companies/{self.tenant.pk}/health/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self._assert_declared_fields_exist(
            interface="TwoHealthScores (سطح السوبر أدمن)",
            declared=_interface_fields(util_src, "TwoHealthScores"),
            actual=resp.data["health_scores"].keys(),
        )

    def test_daily_rating_record_matches_the_serializer_contract(self):
        """`DailyRatingRecord` يطابق ما يعيده `POST /api/my-agent/daily-ratings/`."""
        api_src = MY_AGENT_API.read_text(encoding="utf-8")
        DailyRating.objects.all().delete()
        resp = self.client.post(
            "/api/my-agent/daily-ratings/",
            {
                "employee_id": self.employee.pk,
                "service_date": timezone.localdate().isoformat(),
                "stars": 5,
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self._assert_declared_fields_exist(
            interface="DailyRatingRecord",
            declared=_interface_fields(api_src, "DailyRatingRecord"),
            actual=resp.data.keys(),
        )
