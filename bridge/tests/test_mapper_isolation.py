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
        UserCompanyMembership.objects.create(user=cls.user_a, tenant=cls.tenant_a, role="manager", is_default=True)
        UserCompanyMembership.objects.create(user=cls.user_b, tenant=cls.tenant_b, role="manager", is_default=True)
        cls.token_a = Token.objects.create(user=cls.user_a)
        cls.token_b = Token.objects.create(user=cls.user_b)

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

    def test_global_collection_not_scoped(self):
        """users/* mirror docs are auth-level — readable regardless of company."""
        FirestoreMirrorDoc.objects.create(
            path=f"users/{self.user_a.pk}", data={"id": str(self.user_a.pk), "isApproved": True})

        self._as(self.token_b, self.tenant_b.TenantID)
        res = self.client.get(f"/api/mapper/users/{self.user_a.pk}/")
        self.assertEqual(res.status_code, 200)

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
