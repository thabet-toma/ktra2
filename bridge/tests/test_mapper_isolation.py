"""task11 M1 — mapper tenant isolation + soft-delete + boolean filter coercion.

The invoice archive (OldPurchaseInvoice) reads/writes /api/mapper/invoices/*.
These tests pin the three M1 guarantees:
  1. Business docs are scoped per company (cross-company access → 404/empty).
  2. DELETE is a soft-delete — the row survives and lists exclude it.
  3. `isHistorical__exact=true` matches boolean True stored in JSON.
"""
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from bridge.models import FirestoreMirrorDoc
from tenants.models import Tenant, UserCompanyMembership


class MapperIsolationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            TenantID=1, CompanyName="Company A", SubscriptionPlan="Enterprise", Status="Active")
        cls.tenant_b = Tenant.objects.create(
            TenantID=2, CompanyName="Company B", SubscriptionPlan="Enterprise", Status="Active")

        cls.user_a = User.objects.create_user(username="usera", password="x")
        cls.user_b = User.objects.create_user(username="userb", password="x")
        cls.superuser = User.objects.create_superuser(username="root", password="x")
        UserCompanyMembership.objects.create(user=cls.user_a, tenant=cls.tenant_a, role="manager", is_default=True)
        UserCompanyMembership.objects.create(user=cls.user_b, tenant=cls.tenant_b, role="manager", is_default=True)
        cls.token_a = Token.objects.create(user=cls.user_a)
        cls.token_b = Token.objects.create(user=cls.user_b)
        cls.super_token = Token.objects.create(user=cls.superuser)

    def _as(self, token, tenant_id=None):
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}",
            **({"HTTP_X_TENANT_ID": str(tenant_id)} if tenant_id else {}),
        )

    def test_requires_auth(self):
        res = self.client.get("/api/mapper/invoices/")
        self.assertEqual(res.status_code, 401)

    def test_post_assigns_tenant_and_lists_are_scoped(self):
        self._as(self.token_a, self.tenant_a.TenantID)
        res = self.client.post(
            "/api/mapper/invoices/",
            {"id": "inv-a", "invoiceNumber": "i-100", "isHistorical": True},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        doc = FirestoreMirrorDoc.objects.get(path="invoices/inv-a")
        self.assertEqual(doc.tenant_id, self.tenant_a.TenantID)

        # Company B sees an empty archive
        self._as(self.token_b, self.tenant_b.TenantID)
        res = self.client.get("/api/mapper/invoices/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

        # Company A sees its own doc
        self._as(self.token_a, self.tenant_a.TenantID)
        res = self.client.get("/api/mapper/invoices/")
        ids = [r["id"] for r in res.json()]
        self.assertIn("inv-a", ids)

    def test_cross_tenant_doc_access_hidden(self):
        FirestoreMirrorDoc.objects.create(
            path="invoices/secret", data={"id": "secret", "total": 999}, tenant=self.tenant_a)

        self._as(self.token_b, self.tenant_b.TenantID)
        self.assertEqual(self.client.get("/api/mapper/invoices/secret/").status_code, 404)
        self.assertEqual(
            self.client.put("/api/mapper/invoices/secret/", {"total": 0}, format="json").status_code,
            404,
        )
        # DELETE on another tenant's doc must NOT touch it
        self.client.delete("/api/mapper/invoices/secret/")
        doc = FirestoreMirrorDoc.objects.get(path="invoices/secret")
        self.assertFalse(doc.data.get("deleted", False))

    def test_delete_is_soft(self):
        FirestoreMirrorDoc.objects.create(
            path="invoices/inv-del", data={"id": "inv-del", "isHistorical": True}, tenant=self.tenant_a)

        self._as(self.token_a, self.tenant_a.TenantID)
        res = self.client.delete("/api/mapper/invoices/inv-del/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("soft_deleted"))

        # Row survives, flagged deleted
        doc = FirestoreMirrorDoc.objects.get(path="invoices/inv-del")
        self.assertTrue(doc.data["deleted"])
        self.assertIn("deletedAt", doc.data)

        # Hidden from lists and direct GET …
        res = self.client.get("/api/mapper/invoices/")
        self.assertEqual([r for r in res.json() if r["id"] == "inv-del"], [])
        self.assertEqual(self.client.get("/api/mapper/invoices/inv-del/").status_code, 404)

        # … but recoverable with include_deleted=1
        res = self.client.get("/api/mapper/invoices/?include_deleted=1")
        self.assertIn("inv-del", [r["id"] for r in res.json()])

    def test_boolean_filter_coercion(self):
        """isHistorical__exact=true must match JSON boolean True (the archive
        filter previously compared True == "true" and matched nothing)."""
        FirestoreMirrorDoc.objects.create(
            path="invoices/hist", data={"id": "hist", "isHistorical": True}, tenant=self.tenant_a)
        FirestoreMirrorDoc.objects.create(
            path="invoices/active", data={"id": "active", "isHistorical": False}, tenant=self.tenant_a)

        self._as(self.token_a, self.tenant_a.TenantID)
        res = self.client.get("/api/mapper/invoices/?isHistorical__exact=true")
        ids = [r["id"] for r in res.json()]
        self.assertEqual(ids, ["hist"])

    def test_user_mirror_cannot_be_enumerated_or_read_cross_user(self):
        FirestoreMirrorDoc.objects.create(
            path=f"users/{self.user_a.pk}", data={"id": str(self.user_a.pk), "isApproved": True})

        self._as(self.token_b, self.tenant_b.TenantID)
        self.assertEqual(self.client.get("/api/mapper/users/").status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/mapper/users/{self.user_a.pk}/").status_code,
            404,
        )

        self._as(self.token_a, self.tenant_a.TenantID)
        self.assertEqual(
            self.client.get(f"/api/mapper/users/{self.user_a.pk}/").status_code,
            200,
        )

        self._as(self.super_token, self.tenant_a.TenantID)
        self.assertEqual(self.client.get("/api/mapper/users/").status_code, 200)

    def test_scoped_collection_without_tenant_header_multi_tenant(self):
        """With >1 tenant in the DB and no X-Tenant-Id, business collections
        must refuse rather than guess."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token_a.key}")
        res = self.client.get("/api/mapper/invoices/")
        self.assertEqual(res.status_code, 400)

    def test_membership_enforced(self):
        """User B presenting tenant A's id is rejected by membership check."""
        self._as(self.token_b, self.tenant_a.TenantID)
        res = self.client.get("/api/mapper/invoices/")
        self.assertEqual(res.status_code, 403)

    # ── الحضور مجموعة عالمية (تسريب P0-3 مؤجَّل — راجع bridge/views.py) ──
    def test_attendance_collection_stays_global(self):
        """attendanceRecords عالمية عمداً حتى تُنفَّذ هجرة النسبة الصحيحة —
        تقييدها كان يمحو تاريخ الشركات ويكسر الصفحة العامة. تبقى مقروءة عبر
        الشركات (تسريب موثّق) لكن الوثيقة اليتيمة لا تُتبنّى (P0-4 منفصل)."""
        FirestoreMirrorDoc.objects.create(
            path="attendanceRecords/rec-a", data={"id": "rec-a", "userId": "7"}, tenant=None)
        self._as(self.token_b, self.tenant_b.TenantID)
        # عالمية ⇒ مقروءة من أي شركة (السلوك القائم، غير مقيَّد بعد)
        ids = [r["id"] for r in self.client.get("/api/mapper/attendanceRecords/").json()]
        self.assertIn("rec-a", ids)

    # ── P0-4: الوثائق اليتيمة المُنطاقة (tenant NULL) لا تُقرأ ولا تُتبنّى ──
    def test_orphan_scoped_doc_is_not_readable(self):
        FirestoreMirrorDoc.objects.create(
            path="invoices/orphan", data={"id": "orphan", "total": 5}, tenant=None)
        self._as(self.token_b, self.tenant_b.TenantID)
        self.assertEqual(
            self.client.get("/api/mapper/invoices/orphan/").status_code, 404)
        self.assertNotIn(
            "orphan",
            [r["id"] for r in self.client.get("/api/mapper/invoices/").json()])

    def test_orphan_scoped_doc_cannot_be_adopted_on_write(self):
        FirestoreMirrorDoc.objects.create(
            path="invoices/orphan2", data={"id": "orphan2", "total": 5}, tenant=None)
        self._as(self.token_b, self.tenant_b.TenantID)
        res = self.client.put(
            "/api/mapper/invoices/orphan2/", {"total": 999}, format="json")
        self.assertEqual(res.status_code, 404)
        # لم تُتبنَّ ولا تغيّرت
        doc = FirestoreMirrorDoc.objects.get(path="invoices/orphan2")
        self.assertIsNone(doc.tenant_id)
        self.assertEqual(doc.data.get("total"), 5)
