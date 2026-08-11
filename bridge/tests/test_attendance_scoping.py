"""P0-3 (SCALABILITY_AUDIT): عزل سجلات الحضور والنقاط بين الشركات.

`attendanceSessions`/`attendanceRecords`/`pointsHistory` كانت في
`GLOBAL_COLLECTIONS` ⇒ أي مستخدم من أي شركة يقرأ حضور موظفي كل الشركات
ونقاطهم. هذه آخر ثغرة P0 كانت مفتوحة.

الاختبارات تثبّت ثلاثة أشياء معاً — لأن أياً منها وحده لا يكفي:
  1. **العزل**: شركة ب لا ترى سجل شركة أ (لا في القائمة ولا بالمسار المباشر).
  2. **عدم الانكسار**: شركة أ ما زالت ترى سجلها هي — التقييد لم يُخفِ التاريخ.
  3. **`departments` بقيت عامة**: صفحة «تواصل معنا» تقرؤها بلا سياق شركة،
     وهي المحتوى العام الذي كان يُخلط بالتسريب فيؤجّل إغلاقه.
"""
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from bridge.models import FirestoreMirrorDoc
from tenants.models import Tenant, UserCompanyMembership


class AttendanceScopingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            CompanyName="حضور أ", SubscriptionPlan="Enterprise", Status="Active",
        )
        cls.tenant_b = Tenant.objects.create(
            CompanyName="حضور ب", SubscriptionPlan="Enterprise", Status="Active",
        )
        cls.user_a = User.objects.create_user(username="att_a", password="x")
        cls.user_b = User.objects.create_user(username="att_b", password="x")
        UserCompanyMembership.objects.create(
            user=cls.user_a, tenant=cls.tenant_a, role="manager", is_default=True,
        )
        UserCompanyMembership.objects.create(
            user=cls.user_b, tenant=cls.tenant_b, role="manager", is_default=True,
        )
        cls.token_a = Token.objects.create(user=cls.user_a)
        cls.token_b = Token.objects.create(user=cls.user_b)

        # سجل حضور مملوك لشركة أ (كما تنتجه الهجرة أو الكتابة الجديدة).
        FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/rec-a",
            data={"id": "rec-a", "userId": str(cls.user_a.pk), "points": 10},
            tenant=cls.tenant_a,
        )
        # نقاط يومية مملوكة لشركة أ.
        FirestoreMirrorDoc.objects.create(
            path=f"pointsHistory/{cls.user_a.pk}/days/2026-08-01",
            data={"date": "2026-08-01", "totalPoints": 42},
            tenant=cls.tenant_a,
        )
        # قسم عام — بلا مالك عمداً.
        FirestoreMirrorDoc.objects.create(
            path="departments/dept-1",
            data={"id": "dept-1", "name": "الدعم"},
            tenant=None,
        )

    def _as(self, token, tenant_id=None):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}",
            **({"HTTP_X_TENANT_ID": str(tenant_id)} if tenant_id else {}),
        )

    def test_other_company_cannot_list_attendance_records(self):
        self._as(self.token_b, self.tenant_b.TenantID)
        res = self.client.get("/api/mapper/attendanceRecords/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_other_company_cannot_read_attendance_record_by_path(self):
        self._as(self.token_b, self.tenant_b.TenantID)
        res = self.client.get("/api/mapper/attendanceRecords/rec-a/")
        self.assertEqual(res.status_code, 404)

    def test_other_company_cannot_read_points_history(self):
        self._as(self.token_b, self.tenant_b.TenantID)
        res = self.client.get(
            f"/api/mapper/pointsHistory/{self.user_a.pk}/days/2026-08-01/"
        )
        self.assertEqual(res.status_code, 404)

    def test_owning_company_still_reads_its_own_history(self):
        """التقييد أغلق التسريب ولم يُخفِ التاريخ عن صاحبه."""
        self._as(self.token_a, self.tenant_a.TenantID)
        listing = self.client.get("/api/mapper/attendanceRecords/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([r["id"] for r in listing.json()], ["rec-a"])

        points = self.client.get(
            f"/api/mapper/pointsHistory/{self.user_a.pk}/days/2026-08-01/"
        )
        self.assertEqual(points.status_code, 200)
        self.assertEqual(points.json()["totalPoints"], 42)

    def test_unattributed_record_is_readable_by_nobody(self):
        """ما لم تحسمه الهجرة يبقى NULL — يفشل مغلقاً لا مفتوحاً."""
        FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/rec-orphan",
            data={"id": "rec-orphan", "userId": "999"},
            tenant=None,
        )
        for token, tenant in ((self.token_a, self.tenant_a), (self.token_b, self.tenant_b)):
            self._as(token, tenant.TenantID)
            res = self.client.get("/api/mapper/attendanceRecords/rec-orphan/")
            self.assertEqual(res.status_code, 404, res.content)

    def test_departments_stay_public_and_shared(self):
        """المحتوى العام لم يُمَسّ — وهو العائق الذي كان يُؤجّل إغلاق P0-3."""
        for token, tenant in ((self.token_a, self.tenant_a), (self.token_b, self.tenant_b)):
            self._as(token, tenant.TenantID)
            res = self.client.get("/api/mapper/departments/")
            self.assertEqual(res.status_code, 200)
            self.assertEqual([r["id"] for r in res.json()], ["dept-1"])
