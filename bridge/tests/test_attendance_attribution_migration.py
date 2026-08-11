"""P0-3: منطق النسب في `0005_scope_attendance_and_points_to_tenant`.

الهجرة هي نصف الإصلاح: التقييد بلا نسبٍ صحيح يُخفي تاريخ الحضور والنقاط عن
أصحابه. وهي أيضاً الخطوة التي **لا يمكن التراجع عنها بسهولة** على بيانات
حقيقية، فمنطقها مُختبَر هنا مباشرةً بدل الوثوق بتشغيلها مرة واحدة.

الحالات الثلاث التي تحكم صحّتها:
  • مالك بعضوية واحدة   → يُنسَب لشركته.
  • مالك بعضويتين       → لا يُنسَب (لا شيء في الوثيقة يدلّ على أيّ شركة).
  • مالك غير موجود/مشوّه → لا يُنسَب.
وما لا يُنسَب يبقى NULL ⇒ لا تقرؤه أي شركة (يفشل مغلقاً).
"""
from django.contrib.auth.models import User
from django.test import TestCase

from bridge.models import FirestoreMirrorDoc
from tenants.models import Tenant, UserCompanyMembership


def _load_migration():
    """الهجرة يبدأ اسمها برقم فلا تُستورَد بـimport عادي."""
    import importlib
    return importlib.import_module(
        "bridge.migrations.0005_scope_attendance_and_points_to_tenant"
    )


class _Apps:
    """بديل مصغّر لـ`apps` الذي تتلقّاه RunPython — يُرجع النماذج الحقيقية."""

    _MODELS = {
        ("bridge", "FirestoreMirrorDoc"): FirestoreMirrorDoc,
        ("tenants", "UserCompanyMembership"): UserCompanyMembership,
    }

    def get_model(self, app_label, model_name):
        return self._MODELS[(app_label, model_name)]


class AttendanceAttributionMigrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(CompanyName="نسب أ", Status="Active")
        cls.tenant_b = Tenant.objects.create(CompanyName="نسب ب", Status="Active")

        cls.solo = User.objects.create_user(username="solo_member", password="x")
        cls.dual = User.objects.create_user(username="dual_member", password="x")
        UserCompanyMembership.objects.create(
            user=cls.solo, tenant=cls.tenant_a, role="staff",
        )
        UserCompanyMembership.objects.create(
            user=cls.dual, tenant=cls.tenant_a, role="staff",
        )
        UserCompanyMembership.objects.create(
            user=cls.dual, tenant=cls.tenant_b, role="staff",
        )

    def _run(self):
        _load_migration().attribute_to_owner_company(_Apps(), None)

    def test_points_history_owner_comes_from_the_path(self):
        doc = FirestoreMirrorDoc.objects.create(
            path=f"pointsHistory/{self.solo.pk}/days/2026-08-01",
            data={"totalPoints": 5}, tenant=None,
        )
        self._run()
        doc.refresh_from_db()
        self.assertEqual(doc.tenant_id, self.tenant_a.TenantID)

    def test_attendance_record_owner_comes_from_user_id(self):
        doc = FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/r1",
            data={"userId": str(self.solo.pk)}, tenant=None,
        )
        self._run()
        doc.refresh_from_db()
        self.assertEqual(doc.tenant_id, self.tenant_a.TenantID)

    def test_session_owner_comes_from_created_by(self):
        doc = FirestoreMirrorDoc.objects.create(
            path="attendanceSessions/s1",
            data={"createdBy": str(self.solo.pk)}, tenant=None,
        )
        self._run()
        doc.refresh_from_db()
        self.assertEqual(doc.tenant_id, self.tenant_a.TenantID)

    def test_multi_company_owner_is_left_unattributed(self):
        """عضو في شركتين: لا شيء في الوثيقة يحسم أيّهما — فلا تُنسَب."""
        doc = FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/r2",
            data={"userId": str(self.dual.pk)}, tenant=None,
        )
        self._run()
        doc.refresh_from_db()
        self.assertIsNone(doc.tenant_id)

    def test_unknown_or_malformed_owner_is_left_unattributed(self):
        missing = FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/r3", data={"userId": "999999"}, tenant=None,
        )
        malformed = FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/r4", data={"userId": "not-a-number"}, tenant=None,
        )
        self._run()
        missing.refresh_from_db()
        malformed.refresh_from_db()
        self.assertIsNone(missing.tenant_id)
        self.assertIsNone(malformed.tenant_id)

    def test_already_attributed_docs_are_not_touched(self):
        doc = FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/r5",
            data={"userId": str(self.solo.pk)}, tenant=self.tenant_b,
        )
        self._run()
        doc.refresh_from_db()
        self.assertEqual(doc.tenant_id, self.tenant_b.TenantID)
