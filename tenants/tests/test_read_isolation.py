"""task11 M7 — read-side isolation for the ACTUAL endpoints the screens hit.

M5 proved a new company's data is empty *in the database*; these tests prove
the list endpoints (items / suppliers / customers / categories / stock
movements / journals / mapper tasks) return EMPTY for a new company even when
another company has data — the exact failure the owner saw on a fresh company.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from bridge.models import FirestoreMirrorDoc
from inventory.models import Product, ProductCategory, StockMovement
from partners.models import Partner
from accounting.models import Account, JournalHeader
from tenants.services import create_company


class ReadIsolationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="ownera", password="x")
        cls.owner_b = User.objects.create_user(username="ownerb", password="x")
        cls.t_a = create_company("الشركة القديمة", cls.owner_a)
        cls.t_b = create_company("الشركة الجديدة", cls.owner_b)

        # بيانات الشركة القديمة التي يجب ألا تظهر للشركة الجديدة
        cls.partner_a = Partner.objects.create(tenant=cls.t_a, name="مورد قديم", partner_type="Supplier")
        Partner.objects.create(tenant=cls.t_a, name="زبون قديم", partner_type="Customer")
        cls.cat_a = ProductCategory.objects.create(tenant=cls.t_a, name="فئة قديمة")
        cls.prod_a = Product.objects.create(tenant=cls.t_a, sku="OLD-1", name_ar="صنف قديم")
        StockMovement.objects.create(
            tenant=cls.t_a, product=cls.prod_a, movement_type="IN",
            quantity=5, movement_date="2026-06-01",
        )
        FirestoreMirrorDoc.objects.create(
            path="tasks/old-task", data={"id": "old-task", "title": "مهمة قديمة"}, tenant=cls.t_a)

    def _as_b(self):
        self.client.force_authenticate(user=self.owner_b)
        return {"HTTP_X_TENANT_ID": str(self.t_b.TenantID)}

    def _list(self, url):
        res = self.client.get(url, **self._as_b())
        assert res.status_code == 200, f"{url} → {res.status_code}: {res.content[:200]}"
        data = res.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def test_partners_empty_for_new_company(self):
        assert self._list("/api/partners/") == []

    def test_products_empty_for_new_company(self):
        assert self._list("/api/inventory/products/") == []

    def test_categories_empty_for_new_company(self):
        assert self._list("/api/inventory/categories/") == []

    def test_stock_movements_empty_for_new_company(self):
        assert self._list("/api/inventory/stock-movements/") == []

    def test_journals_empty_without_leak(self):
        JournalHeader.objects.create(tenant=self.t_a, transaction_date="2026-06-01")
        assert self._list("/api/accounting/journals/") == []

    def test_mapper_tasks_scoped(self):
        """الصفحة الرئيسية تقرأ المهام من mapper «tasks» — يجب أن تكون فارغة."""
        # mapper auth uses real tokens, not force_authenticate
        from rest_framework.authtoken.models import Token
        token = Token.objects.create(user=self.owner_b)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}",
            HTTP_X_TENANT_ID=str(self.t_b.TenantID),
        )
        res = self.client.get("/api/mapper/tasks/")
        assert res.status_code == 200
        assert res.json() == []

    def test_new_company_coa_seeded_via_endpoint(self):
        """شجرة حسابات الشركة الجديدة ليست فارغة عبر نفس endpoint الشاشة."""
        rows = self._list("/api/accounting/accounts/")
        codes = {r["code"] for r in rows}
        assert {"1", "2", "3", "4", "5", "1101", "2101", "4101"} <= codes
        # كل الصفوف المعادة تخص الشركة الجديدة فقط — لا تسرب من القديمة
        assert len(rows) == Account.objects.filter(tenant=self.t_b).count()
        names = {r["name"] for r in rows}
        assert "مورد قديم" not in names
