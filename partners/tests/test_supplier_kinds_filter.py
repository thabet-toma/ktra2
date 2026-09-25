"""صفحة الأطراف الدائنة: فلتر «الأصناف» المتعدّد من الخادم، وعدّاد كل صنف، والتصنيف الجماعي.

كانت `SupplierManagement` تحمّل 500 طرف وتفلترها في المتصفح — شركةٌ تتجاوزها
تفقد أطرافاً بصمت. و«مورد محلي + وكيل شحن» لا يُعبَّر عنه بـ`partner_type__in`
و`supplier_scope__in` معاً (نطاق الوكيل فارغ فيلتقطه فلتر «غير المصنّف»)، لذا
الصنف قيمةٌ واحدة: `supplier_local`/`supplier_international`/`supplier_unscoped`
أو نوع الطرف نفسه.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class SupplierKindsFilterTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="kinds", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الأصناف", cls.user)
        cls.other = create_company("شركة أخرى", cls.user)
        mk = lambda name, t, scope="", **kw: Partner.objects.create(
            tenant=kw.pop("tenant", cls.tenant), name=name, partner_type=t, supplier_scope=scope, **kw)
        cls.local = mk("مورد محلي", "Supplier", "local")
        cls.intl = mk("مورد دولي", "Supplier", "international")
        cls.unscoped = mk("مورد غير مصنّف", "Supplier")
        cls.ff = mk("وكيل", "FreightForwarder")
        cls.cb = mk("مخلّص", "CustomsBroker")
        cls.lt = mk("نقل محلي", "LocalTransporter")
        cls.carrier = mk("ناقل", "Carrier")
        cls.customer = mk("زبون", "Customer")
        cls.stopped = mk("موقوف", "Supplier", "local", is_active=False)
        cls.foreign = mk("مورد شركة أخرى", "Supplier", tenant=cls.other)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _ids(self, query):
        res = self.client.get(f"/api/partners/?page_size=100&{query}", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        return {r["id"] for r in rows}

    def test_kinds_combines_scoped_suppliers_with_party_types(self):
        self.assertEqual(self._ids("kinds=supplier_local,CustomsBroker"), {self.local.id, self.cb.id})
        # غير المصنّف مورد بنطاق فارغ — لا وكيل الشحن ذو النطاق الفارغ.
        self.assertEqual(self._ids("kinds=supplier_unscoped"), {self.unscoped.id})
        self.assertEqual(
            self._ids("kinds=FreightForwarder,LocalTransporter,Carrier"),
            {self.ff.id, self.lt.id, self.carrier.id},
        )

    def test_partner_type_accepts_a_list(self):
        self.assertEqual(self._ids("partner_type=FreightForwarder,Carrier"), {self.ff.id, self.carrier.id})
        # القيمة المفردة كما كانت.
        self.assertEqual(self._ids("partner_type=CustomsBroker"), {self.cb.id})

    def test_supplier_scope_accepts_a_list_and_keeps_unscoped_visible(self):
        self.assertEqual(
            self._ids("partner_type=Supplier&supplier_scope=local,international"),
            {self.local.id, self.intl.id, self.unscoped.id},
        )

    def test_kind_counts_per_chip_excludes_inactive_and_other_tenants(self):
        res = self.client.get("/api/partners/kind-counts/", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data, {
            "supplier_local": 1, "supplier_international": 1, "supplier_unscoped": 1,
            "FreightForwarder": 1, "CustomsBroker": 1, "LocalTransporter": 1, "Carrier": 1,
        })
        with_inactive = self.client.get("/api/partners/kind-counts/?include_inactive=1", **self.h)
        self.assertEqual(with_inactive.data["supplier_local"], 2)
        searched = self.client.get("/api/partners/kind-counts/?search=مخلّص", **self.h)
        self.assertEqual(searched.data["CustomsBroker"], 1)
        self.assertEqual(searched.data["supplier_local"], 0)

    def test_bulk_scope_classifies_only_this_tenants_suppliers(self):
        res = self.client.post(
            "/api/partners/bulk-scope/",
            {"ids": [self.unscoped.id, self.ff.id, self.foreign.id], "supplier_scope": "international"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["updated"], 1)
        self.unscoped.refresh_from_db()
        self.ff.refresh_from_db()
        self.foreign.refresh_from_db()
        self.assertEqual(self.unscoped.supplier_scope, "international")
        self.assertEqual(self.ff.supplier_scope, "")
        self.assertEqual(self.foreign.supplier_scope, "")

    def test_bulk_scope_rejects_unknown_scope(self):
        res = self.client.post(
            "/api/partners/bulk-scope/", {"ids": [self.unscoped.id], "supplier_scope": "mars"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 400)
