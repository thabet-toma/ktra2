"""T2 — حالة «نشط/غير نشط» على المنتج (باك-إند فقط).

القاعدة (زوهو «Mark as Inactive» · BC «Blocked» · دفترة Status · أودو Archive):
المنتج غير النشط **يغيب عن كل قائمة/منتقٍ للمستندات الجديدة** ويبقى على المستندات
القديمة والتقارير وشاشات المخزون — فبطاقته وسجلّه يُفتحان بعد التعطيل.

العقد الذي تبني عليه واجهة T4: `status=active|inactive|all` (والافتراضي active)
على `list` فقط (عادياً أو `view=lookup` أو `/api/lookup/products/`)، و
`include_inactive=1` اسمٌ بديل لـ`all`؛ `set-active` و`bulk-set-active`
و`deactivation-impact`. التعطيل بوجود رصيد **مسموح** (قرار المالك) — لذلك يُرجِع
`deactivation-impact` الرصيد والمسوّدات ليحذّر المستخدم قبل التأكيد.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    SalesInvoice, SalesInvoiceLine, SalesOrder, SalesOrderLine,
    SalesQuotation, SalesQuotationLine,
)
from tenants.models import Currency
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"
LOOKUP_URL = "/api/lookup/products/"


class ProductActiveStateTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="act_a", password="x")
        cls.owner_b = User.objects.create_user(username="act_b", password="x")
        cls.t_a = create_company("شركة النشاط أ", cls.owner_a)
        cls.t_b = create_company("شركة النشاط ب", cls.owner_b)
        cls.live = Product.objects.create(tenant=cls.t_a, sku="ACT-1", name_ar="منتج حيّ")
        cls.dead = Product.objects.create(
            tenant=cls.t_a, sku="ACT-2", name_ar="منتج معطَّل", is_active=False)
        cls.foreign = Product.objects.create(tenant=cls.t_b, sku="ACT-3", name_ar="منتج شركة ب")

    def setUp(self):
        self.client.force_authenticate(user=self.owner_a)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.t_a.TenantID)}

    @staticmethod
    def _rows(res):
        # القائمة بلا `page` مصفوفةٌ مجرَّدة، ومعها `page` كائنٌ فيه `results`.
        body = res.json()
        return body["results"] if isinstance(body, dict) else body

    def _ids(self, url, query=""):
        res = self.client.get(url + query, **self.hdr)
        self.assertEqual(res.status_code, 200, res.content[:300])
        return {r["id"] for r in self._rows(res)}

    # ── القائمة ──────────────────────────────────────────────────────────
    def test_new_products_default_to_active(self):
        self.assertTrue(self.live.is_active)

    def test_list_default_hides_inactive(self):
        ids = self._ids(PRODUCTS_URL)
        self.assertIn(self.live.id, ids)
        self.assertNotIn(self.dead.id, ids)

    def test_list_status_inactive_shows_only_inactive(self):
        self.assertEqual(self._ids(PRODUCTS_URL, "?status=inactive"), {self.dead.id})

    def test_list_status_all_shows_both(self):
        self.assertEqual(self._ids(PRODUCTS_URL, "?status=all"), {self.live.id, self.dead.id})

    def test_include_inactive_is_alias_of_all(self):
        both = {self.live.id, self.dead.id}
        self.assertEqual(self._ids(PRODUCTS_URL, "?include_inactive=1"), both)
        self.assertEqual(self._ids(PRODUCTS_URL, "?include_inactive=true"), both)

    def test_unknown_status_falls_back_to_active(self):
        self.assertEqual(self._ids(PRODUCTS_URL, "?status=whatever"), {self.live.id})

    def test_list_serializes_is_active(self):
        res = self.client.get(PRODUCTS_URL + "?status=all", **self.hdr)
        rows = {r["id"]: r for r in self._rows(res)}
        self.assertIs(rows[self.live.id]["is_active"], True)
        self.assertIs(rows[self.dead.id]["is_active"], False)

    def test_view_lookup_hides_inactive_and_exposes_flag(self):
        self.assertEqual(self._ids(PRODUCTS_URL, "?view=lookup"), {self.live.id})
        res = self.client.get(PRODUCTS_URL + "?view=lookup&status=all", **self.hdr)
        rows = {r["id"]: r for r in self._rows(res)}
        self.assertIs(rows[self.dead.id]["is_active"], False)

    def test_lookup_route_hides_inactive(self):
        self.assertEqual(self._ids(LOOKUP_URL), {self.live.id})
        self.assertEqual(
            self._ids(LOOKUP_URL, "?status=all"), {self.live.id, self.dead.id})

    # ── التفاصيل لا تُفلتَر ──────────────────────────────────────────────
    def test_retrieve_and_profile_still_open_for_inactive(self):
        res = self.client.get(f"{PRODUCTS_URL}{self.dead.id}/", **self.hdr)
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertIs(res.json()["is_active"], False)
        profile = self.client.get(f"{PRODUCTS_URL}{self.dead.id}/profile/", **self.hdr)
        self.assertEqual(profile.status_code, 200, profile.content[:300])

    def test_patch_is_active_works(self):
        res = self.client.patch(
            f"{PRODUCTS_URL}{self.live.id}/", {"is_active": False}, format="json", **self.hdr)
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.live.refresh_from_db()
        self.assertFalse(self.live.is_active)
        self.live.is_active = True
        self.live.save()

    # ── set-active ───────────────────────────────────────────────────────
    def test_set_active_toggles_and_returns_product(self):
        p = Product.objects.create(tenant=self.t_a, sku="ACT-T", name_ar="للتبديل")
        res = self.client.post(
            f"{PRODUCTS_URL}{p.id}/set-active/", {"is_active": False}, format="json", **self.hdr)
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json()["id"], p.id)
        self.assertIs(res.json()["is_active"], False)
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        res = self.client.post(
            f"{PRODUCTS_URL}{p.id}/set-active/", {"is_active": True}, format="json", **self.hdr)
        self.assertIs(res.json()["is_active"], True)
        p.refresh_from_db()
        self.assertTrue(p.is_active)

    def test_set_active_requires_boolean(self):
        res = self.client.post(
            f"{PRODUCTS_URL}{self.live.id}/set-active/", {"is_active": "maybe"},
            format="json", **self.hdr)
        self.assertEqual(res.status_code, 400)
        res = self.client.post(
            f"{PRODUCTS_URL}{self.live.id}/set-active/", {}, format="json", **self.hdr)
        self.assertEqual(res.status_code, 400)

    def test_set_active_other_tenant_product_is_404_and_untouched(self):
        res = self.client.post(
            f"{PRODUCTS_URL}{self.foreign.id}/set-active/", {"is_active": False},
            format="json", **self.hdr)
        self.assertEqual(res.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.is_active)

    def test_set_active_works_on_inactive_product(self):
        """get_object لا يفلتر بالحالة — وإلا تعذّرت إعادة التفعيل."""
        p = Product.objects.create(
            tenant=self.t_a, sku="ACT-R", name_ar="أُعيد", is_active=False)
        res = self.client.post(
            f"{PRODUCTS_URL}{p.id}/set-active/", {"is_active": True}, format="json", **self.hdr)
        self.assertEqual(res.status_code, 200, res.content[:300])
        p.refresh_from_db()
        self.assertTrue(p.is_active)

    # ── bulk-set-active ──────────────────────────────────────────────────
    def test_bulk_set_active_updates_only_own_tenant(self):
        a = Product.objects.create(tenant=self.t_a, sku="ACT-B1", name_ar="جملة 1")
        b = Product.objects.create(tenant=self.t_a, sku="ACT-B2", name_ar="جملة 2")
        res = self.client.post(
            PRODUCTS_URL + "bulk-set-active/",
            {"ids": [a.id, b.id, self.foreign.id], "is_active": False},
            format="json", **self.hdr)
        self.assertEqual(res.status_code, 200, res.content[:300])
        self.assertEqual(res.json(), {"updated": 2})
        a.refresh_from_db()
        b.refresh_from_db()
        self.foreign.refresh_from_db()
        self.assertFalse(a.is_active)
        self.assertFalse(b.is_active)
        self.assertTrue(self.foreign.is_active)

    def test_bulk_set_active_validates_body(self):
        for body in (
            {"ids": [], "is_active": False},
            {"ids": "x", "is_active": False},
            {"ids": [self.live.id]},
            {"ids": ["abc"], "is_active": False},
        ):
            res = self.client.post(
                PRODUCTS_URL + "bulk-set-active/", body, format="json", **self.hdr)
            self.assertEqual(res.status_code, 400, body)

    def test_set_active_writes_audit_log(self):
        from core.models import ActivityLog
        p = Product.objects.create(tenant=self.t_a, sku="ACT-L", name_ar="للسجل")
        self.client.post(
            f"{PRODUCTS_URL}{p.id}/set-active/", {"is_active": False}, format="json", **self.hdr)
        self.assertTrue(ActivityLog.objects.filter(
            tenant=self.t_a, entity_type="product", entity_id=p.id, action="update").exists())

    # ── deactivation-impact ──────────────────────────────────────────────
    def test_deactivation_impact_reports_stock_and_open_drafts_only(self):
        cur = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        create_fiscal_year(self.t_a, 2026)
        ar = Account.objects.create(
            tenant=self.t_a, code="1101-I", name="ذمم", account_type="Asset", is_active=True)
        cust = Partner.objects.create(
            tenant=self.t_a, name="عميل", partner_type="Customer", linked_account=ar)
        p = Product.objects.create(
            tenant=self.t_a, sku="ACT-IMP", name_ar="ذو أثر", quantity_on_hand=Decimal("7"))
        other = Product.objects.create(tenant=self.t_a, sku="ACT-OTH", name_ar="آخر")

        def invoice(number, status, product, date="2026-08-01"):
            inv = SalesInvoice.objects.create(
                tenant=self.t_a, invoice_number=number, customer=cust, currency=cur,
                invoice_date=date, invoice_type=SalesInvoice.INVOICE_CREDIT,
                stock_on_post=False, status=status)
            SalesInvoiceLine.objects.create(
                tenant=self.t_a, invoice=inv, product=product,
                quantity=Decimal("1"), unit_price=Decimal("10"))
            return inv

        draft_inv = invoice("SI-D", SalesInvoice.STATUS_DRAFT, p, "2026-08-02")
        invoice("SI-P", SalesInvoice.STATUS_POSTED, p)              # مرحَّلة — تُستثنى
        invoice("SI-X", SalesInvoice.STATUS_CANCELLED, p)           # ملغاة — تُستثنى
        invoice("SI-O", SalesInvoice.STATUS_DRAFT, other)           # منتج آخر — تُستثنى

        q = SalesQuotation.objects.create(
            tenant=self.t_a, quotation_number="Q-OPEN", customer=cust,
            quotation_date="2026-08-03", currency=cur, status=SalesQuotation.STATUS_SENT)
        SalesQuotationLine.objects.create(
            tenant=self.t_a, quotation=q, product=p, quantity=Decimal("1"),
            unit_price=Decimal("10"))
        qc = SalesQuotation.objects.create(
            tenant=self.t_a, quotation_number="Q-CONV", customer=cust,
            quotation_date="2026-08-03", currency=cur, status=SalesQuotation.STATUS_CONVERTED)
        SalesQuotationLine.objects.create(
            tenant=self.t_a, quotation=qc, product=p, quantity=Decimal("1"),
            unit_price=Decimal("10"))

        o = SalesOrder.objects.create(
            tenant=self.t_a, order_number="O-CONF", customer=cust,
            order_date="2026-08-04", currency=cur, status=SalesOrder.STATUS_CONFIRMED)
        SalesOrderLine.objects.create(
            tenant=self.t_a, order=o, product=p, quantity=Decimal("1"), unit_price=Decimal("10"))

        res = self.client.get(f"{PRODUCTS_URL}{p.id}/deactivation-impact/", **self.hdr)
        self.assertEqual(res.status_code, 200, res.content[:300])
        body = res.json()
        self.assertEqual(Decimal(body["quantity_on_hand"]), Decimal("7"))
        self.assertEqual(body["draft_documents_count"], 3)
        rows = body["draft_documents"]
        self.assertEqual(
            {(r["kind"], r["number"]) for r in rows},
            {("sales_invoice", "SI-D"), ("sales_quotation", "Q-OPEN"),
             ("sales_order", "O-CONF")},
        )
        inv_row = next(r for r in rows if r["kind"] == "sales_invoice")
        self.assertEqual(inv_row["id"], draft_inv.id)
        self.assertEqual(inv_row["date"], "2026-08-02")
        self.assertTrue(inv_row["kind_label"])
        # الأحدث أولاً.
        self.assertEqual([r["number"] for r in rows], ["O-CONF", "Q-OPEN", "SI-D"])

    def test_deactivation_impact_caps_rows_but_counts_all(self):
        cur = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        ar = Account.objects.create(
            tenant=self.t_a, code="1101-C", name="ذمم", account_type="Asset", is_active=True)
        cust = Partner.objects.create(
            tenant=self.t_a, name="عميل2", partner_type="Customer", linked_account=ar)
        p = Product.objects.create(tenant=self.t_a, sku="ACT-CAP", name_ar="كثير المسودات")
        for i in range(23):
            inv = SalesInvoice.objects.create(
                tenant=self.t_a, invoice_number=f"SI-CAP-{i}", customer=cust, currency=cur,
                invoice_date="2026-08-01", invoice_type=SalesInvoice.INVOICE_CREDIT,
                stock_on_post=False, status=SalesInvoice.STATUS_DRAFT)
            SalesInvoiceLine.objects.create(
                tenant=self.t_a, invoice=inv, product=p, quantity=Decimal("1"),
                unit_price=Decimal("1"))
        body = self.client.get(
            f"{PRODUCTS_URL}{p.id}/deactivation-impact/", **self.hdr).json()
        self.assertEqual(body["draft_documents_count"], 23)
        self.assertEqual(len(body["draft_documents"]), 20)

    def test_deactivation_impact_empty_and_tenant_scoped(self):
        res = self.client.get(f"{PRODUCTS_URL}{self.live.id}/deactivation-impact/", **self.hdr)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["draft_documents_count"], 0)
        self.assertEqual(res.json()["draft_documents"], [])
        res = self.client.get(f"{PRODUCTS_URL}{self.foreign.id}/deactivation-impact/", **self.hdr)
        self.assertEqual(res.status_code, 404)
