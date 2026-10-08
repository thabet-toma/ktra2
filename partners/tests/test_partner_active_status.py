"""T5 — إيقاف الطرف الكامل: فلتر `status` الثلاثي، أثرُ الإيقاف قبل التنفيذ، الإيقاف الجماعي.

الموقوف يُخفى من المستندات الجديدة لا من الدفع له: الواجهة تطلب `status=all` في شاشات
السندات والشيكات والإشعارات كي يبقى تسوية رصيده ممكنةً، وتطلب `status=inactive`
لعرض الموقوفين وحدهم. ولا يجوز لشركةٍ أن تُوقف أو تقرأ أثر طرف شركةٍ أخرى.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from logistics.models import PurchaseInvoice, PurchaseOrder
from partners.models import Partner
from sales.models import SalesInvoice, SalesOrder, SalesQuotation
from tenants.models import Currency
from tenants.services import create_company


class PartnerActiveStatusTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="t5status", password="x")
        cls.currency = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الحالة", cls.user)
        cls.other = create_company("شركة أخرى للحالة", cls.user)
        mk = lambda name, t, **kw: Partner.objects.create(
            tenant=kw.pop("tenant", cls.tenant), name=name, partner_type=t, **kw)
        cls.active = mk("نشط", "Supplier")
        cls.stopped = mk("موقوف", "Supplier", is_active=False)
        cls.customer = mk("زبون", "Customer")
        cls.stopped_customer = mk("زبون موقوف", "Customer", is_active=False)
        cls.foreign = mk("مورد شركة أخرى", "Supplier", tenant=cls.other)
        cls.foreign_stopped = mk("موقوف شركة أخرى", "Supplier", tenant=cls.other, is_active=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _ids(self, url):
        res = self.client.get(url, **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        return {r["id"] for r in rows}

    # ── status على list / lookup / kind-counts ──────────────────────────────
    def test_status_defaults_to_active_only(self):
        self.assertEqual(self._ids("/api/partners/?partner_type=Supplier"), {self.active.id})
        self.assertEqual(self._ids("/api/partners/lookup/?partner_type=Supplier"), {self.active.id})
        self.assertEqual(
            self._ids("/api/partners/?partner_type=Supplier&status=active"), {self.active.id})

    def test_status_inactive_returns_only_stopped_of_this_tenant(self):
        self.assertEqual(
            self._ids("/api/partners/?partner_type=Supplier&status=inactive"), {self.stopped.id})
        self.assertEqual(
            self._ids("/api/partners/lookup/?partner_type=Supplier&status=inactive"),
            {self.stopped.id})

    def test_status_all_returns_both_but_never_another_tenant(self):
        self.assertEqual(
            self._ids("/api/partners/?partner_type=Supplier&status=all"),
            {self.active.id, self.stopped.id})
        self.assertEqual(
            self._ids("/api/partners/lookup/?partner_type=Supplier&status=all"),
            {self.active.id, self.stopped.id})

    def test_include_inactive_stays_an_alias_of_all(self):
        self.assertEqual(
            self._ids("/api/partners/?partner_type=Supplier&include_inactive=1"),
            {self.active.id, self.stopped.id})
        self.assertEqual(
            self._ids("/api/partners/lookup/?partner_type=Supplier&include_inactive=true"),
            {self.active.id, self.stopped.id})

    def test_explicit_status_wins_over_the_alias(self):
        self.assertEqual(
            self._ids("/api/partners/?partner_type=Supplier&status=inactive&include_inactive=1"),
            {self.stopped.id})

    def test_unknown_status_is_refused_not_silently_widened(self):
        res = self.client.get("/api/partners/?status=banana", **self.h)
        self.assertEqual(res.status_code, 400, res.data)

    def test_kind_counts_follow_status(self):
        res = self.client.get("/api/partners/kind-counts/?status=inactive", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["supplier_unscoped"], 1)
        res = self.client.get("/api/partners/kind-counts/", **self.h)
        self.assertEqual(res.data["supplier_unscoped"], 1)
        res = self.client.get("/api/partners/kind-counts/?status=all", **self.h)
        self.assertEqual(res.data["supplier_unscoped"], 2)

    def test_inactive_partner_detail_still_opens_whatever_the_status(self):
        res = self.client.get(f"/api/partners/{self.stopped.id}/", **self.h)
        self.assertEqual(res.status_code, 200)

    # ── deactivation-impact ─────────────────────────────────────────────────
    def test_impact_reports_balance_and_unposted_documents(self):
        customer = Partner.objects.create(
            tenant=self.tenant, name="زبون برصيد", partner_type="Customer",
            opening_balance=500, opening_balance_date=datetime.date(2026, 1, 1),
        )
        draft = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SI-T5-D", customer=customer,
            currency=self.currency, invoice_date="2026-08-01",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
        )
        SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SI-T5-P", customer=customer,
            currency=self.currency, invoice_date="2026-08-02", status=SalesInvoice.STATUS_POSTED,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
        )
        SalesQuotation.objects.create(
            tenant=self.tenant, quotation_number="QT-T5-1", customer=customer,
            quotation_date=datetime.date(2026, 8, 3), currency=self.currency,
        )
        SalesQuotation.objects.create(
            tenant=self.tenant, quotation_number="QT-T5-DONE", customer=customer,
            quotation_date=datetime.date(2026, 8, 4), currency=self.currency,
            status=SalesQuotation.STATUS_CANCELLED,
        )
        SalesOrder.objects.create(
            tenant=self.tenant, order_number="SO-T5-1", customer=customer,
            order_date=datetime.date(2026, 8, 5), currency=self.currency,
        )

        res = self.client.get(f"/api/partners/{customer.id}/deactivation-impact/", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data["open_balance"]), Decimal("500"))
        self.assertEqual(res.data["balance_side_label"], "مدين")
        self.assertEqual(res.data["draft_documents_count"], 3)
        numbers = [d["number"] for d in res.data["draft_documents"]]
        # الأحدث أولاً؛ المرحَّلة والملغاة خارج المسوّدات.
        self.assertEqual(numbers, ["SO-T5-1", "QT-T5-1", "SI-T5-D"])
        first = res.data["draft_documents"][0]
        self.assertEqual(
            set(first), {"kind", "kind_label", "id", "number", "date"})
        self.assertEqual(first["kind"], "sales_order")
        self.assertEqual(first["date"], "2026-08-05")
        self.assertEqual(
            next(d for d in res.data["draft_documents"] if d["number"] == "SI-T5-D")["id"], draft.id)

    def test_impact_for_creditor_uses_the_same_sign_as_the_profile(self):
        supplier = Partner.objects.create(
            tenant=self.tenant, name="مورد برصيد", partner_type="Supplier",
            opening_balance=300, opening_balance_date=datetime.date(2026, 1, 1),
        )
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PI-T5-D", partner=supplier,
            currency=self.currency, invoice_date="2026-08-06",
        )
        PurchaseOrder.objects.create(
            tenant=self.tenant, order_number="PO-T5-1", supplier=supplier,
            order_date=datetime.date(2026, 8, 7), currency=self.currency,
        )
        profile = self.client.get(f"/api/partners/{supplier.id}/profile/", **self.h).data
        res = self.client.get(f"/api/partners/{supplier.id}/deactivation-impact/", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["open_balance"], profile["balance"])
        self.assertEqual(res.data["balance_side_label"], "دائن")
        self.assertEqual(res.data["draft_documents_count"], 2)
        self.assertEqual(
            {d["kind"] for d in res.data["draft_documents"]},
            {"purchase_invoice", "purchase_order"})

    def test_impact_without_movements_is_zero_and_unlabelled(self):
        res = self.client.get(f"/api/partners/{self.customer.id}/deactivation-impact/", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["open_balance"], "0")
        self.assertEqual(res.data["balance_side_label"], "")
        self.assertEqual(res.data["draft_documents_count"], 0)
        self.assertEqual(res.data["draft_documents"], [])

    def test_impact_caps_the_list_at_twenty_but_counts_all(self):
        for i in range(23):
            SalesQuotation.objects.create(
                tenant=self.tenant, quotation_number=f"QT-T5-N{i:02d}", customer=self.customer,
                quotation_date=datetime.date(2026, 9, 1), currency=self.currency,
            )
        res = self.client.get(f"/api/partners/{self.customer.id}/deactivation-impact/", **self.h)
        self.assertEqual(res.data["draft_documents_count"], 23)
        self.assertEqual(len(res.data["draft_documents"]), 20)

    def test_impact_of_another_tenants_partner_is_404(self):
        res = self.client.get(f"/api/partners/{self.foreign.id}/deactivation-impact/", **self.h)
        self.assertEqual(res.status_code, 404)

    def test_impact_ignores_another_tenants_documents_of_the_same_partner_id_space(self):
        foreign_customer = Partner.objects.create(
            tenant=self.other, name="زبون الآخر", partner_type="Customer")
        SalesQuotation.objects.create(
            tenant=self.other, quotation_number="QT-FOREIGN", customer=foreign_customer,
            quotation_date=datetime.date(2026, 8, 3), currency=self.currency,
        )
        res = self.client.get(f"/api/partners/{self.customer.id}/deactivation-impact/", **self.h)
        self.assertEqual(res.data["draft_documents_count"], 0)

    # ── bulk-set-active ─────────────────────────────────────────────────────
    def test_bulk_set_active_deactivates_and_reactivates_this_tenants_partners(self):
        res = self.client.post(
            "/api/partners/bulk-set-active/",
            {"ids": [self.active.id, self.customer.id], "is_active": False},
            format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data, {"updated": 2})
        self.active.refresh_from_db()
        self.customer.refresh_from_db()
        self.assertFalse(self.active.is_active)
        self.assertFalse(self.customer.is_active)

        res = self.client.post(
            "/api/partners/bulk-set-active/",
            {"ids": [self.active.id, self.customer.id], "is_active": True},
            format="json", **self.h)
        self.assertEqual(res.data, {"updated": 2})
        self.active.refresh_from_db()
        self.assertTrue(self.active.is_active)

    def test_bulk_set_active_never_touches_another_tenant(self):
        res = self.client.post(
            "/api/partners/bulk-set-active/",
            {"ids": [self.foreign.id, self.active.id], "is_active": False},
            format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data, {"updated": 1})
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.is_active)

    def test_bulk_set_active_lands_in_each_partners_activity_log(self):
        """الإيقاف الجماعي يُسجَّل في سجلّ النشاط مربوطاً بكل طرفٍ مسّه — وحده، لا طرف شركةٍ أخرى."""
        from core.models import ActivityLog
        res = self.client.post(
            "/api/partners/bulk-set-active/",
            {"ids": [self.active.id, self.customer.id, self.foreign.id], "is_active": False},
            format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        log = ActivityLog.objects.filter(tenant=self.tenant, entity_type="partner").latest("id")
        self.assertEqual(log.action, "update")
        self.assertIn("أوقف 2", log.description)
        self.assertEqual(
            set(log.partner_links.values_list("partner_id", flat=True)),
            {self.active.id, self.customer.id},
        )

    def test_bulk_set_active_rejects_missing_flag_and_empty_selection(self):
        res = self.client.post(
            "/api/partners/bulk-set-active/", {"ids": [self.active.id]}, format="json", **self.h)
        self.assertEqual(res.status_code, 400, res.data)
        res = self.client.post(
            "/api/partners/bulk-set-active/", {"ids": [], "is_active": False},
            format="json", **self.h)
        self.assertEqual(res.status_code, 400, res.data)
        res = self.client.post(
            "/api/partners/bulk-set-active/", {"ids": ["x"], "is_active": False},
            format="json", **self.h)
        self.assertEqual(res.status_code, 400, res.data)
        self.active.refresh_from_db()
        self.assertTrue(self.active.is_active)
