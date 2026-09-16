"""طلبا PUT متزامنان على وثيقةٍ لم تُنشأ بعد لا يُسقطان أحدَهما بـ500.

`/staff` يرسل `PUT /api/mapper/activityStatus/<id>/` من أكثر من موضعٍ في اللحظة
نفسها. كان `_write` يقرأ الوثيقة (`filter().first()`)، فإن لم يجدها بنى صفّاً جديداً
وحفظه — فالطلبان يقرآن «غير موجودة» معاً ويُدرجان معاً، والثاني يصطدم بفرادة `path`:
`IntegrityError (1062) Duplicate entry 'activityStatus/20'` ⟵ 500.

يُحاكى الطلبُ الأسبق هنا بصفٍّ موجودٍ فعلاً وقراءةٍ مُرغَمةٍ على «غير موجودة» — عينُ
النافذة بين القراءة والإدراج.
"""
from unittest import mock

from django.contrib.auth.models import User
from django.db.models.query import QuerySet
from rest_framework.test import APITestCase

from bridge.models import FirestoreMirrorDoc
from hr.models import UserDevice
from tenants.models import Tenant, UserCompanyMembership


class MapperConcurrentCreateTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            TenantID=1, CompanyName="Company A", SubscriptionPlan="Enterprise", Status="Active")
        cls.user = User.objects.create_user(username="racer", password="x")
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role="manager", is_default=True)
        cls.token = UserDevice.objects.create(user=cls.user)

    def setUp(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {self.token.key}", HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def test_put_racing_a_parallel_create_updates_instead_of_500(self):
        path = f"activityStatus/{self.user.pk}"
        FirestoreMirrorDoc.objects.create(path=path, data={"state": "online"}, tenant=self.tenant)

        original_first = QuerySet.first

        def first_misses_the_parallel_insert(qs):
            if qs.model is FirestoreMirrorDoc:
                return None
            return original_first(qs)

        with mock.patch.object(QuerySet, "first", first_misses_the_parallel_insert):
            res = self.client.put(f"/api/mapper/{path}/", {"state": "away"}, format="json")

        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(FirestoreMirrorDoc.objects.filter(path=path).count(), 1)
        self.assertEqual(FirestoreMirrorDoc.objects.get(path=path).data, {"state": "away"})

    def test_patch_on_an_existing_doc_still_merges(self):
        path = f"activityStatus/{self.user.pk}"
        FirestoreMirrorDoc.objects.create(
            path=path, data={"state": "online", "since": "08:00"}, tenant=self.tenant)

        res = self.client.patch(f"/api/mapper/{path}/", {"state": "away"}, format="json")

        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(
            FirestoreMirrorDoc.objects.get(path=path).data, {"state": "away", "since": "08:00"})

    def test_failed_sync_on_a_new_doc_leaves_no_empty_row(self):
        """الإدراجُ صار قبل المعاملة؛ مزامنةٌ تفشل لا تترك وثيقةً `{}` في القائمة."""
        with mock.patch("bridge.views._sync_partner_from_mirror_supplier", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.client.put("/api/mapper/suppliers/s-1/", {"name": "مورّد"}, format="json")

        self.assertFalse(FirestoreMirrorDoc.objects.filter(path="suppliers/s-1").exists())

    def test_put_creates_a_missing_doc(self):
        path = f"activityStatus/{self.user.pk}"

        res = self.client.put(f"/api/mapper/{path}/", {"state": "online"}, format="json")

        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(FirestoreMirrorDoc.objects.get(path=path).data, {"state": "online"})
