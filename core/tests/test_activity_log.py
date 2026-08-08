"""سجل النشاط الموحّد (core.ActivityLog + core.activity + api/activity).

يتحقق:
  - log_activity ينشئ صفاً بالحقول الصحيحة، وأي فشل داخله يُبتلع (غير حاظر).
  - الصفحة العامة (بلا entity_id) للمدير فقط؛ سجل مستند واحد متاح لأي عضو.
  - الافتراضي = اليوم؛ أحداث is_view مستبعَدة من العام وتظهر مع include_views.
  - login/logout يُسجَّلان في سجل النشاط.
  - تفصيل الحركة: فروقات الترويسة وبنود المستند (إضافة/حذف/تغيير سعر أو كمية).
"""
import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from core.activity import (
    build_line_changes,
    describe_activity_changes,
    log_activity,
    log_view,
    snapshot_document_lines,
    snapshot_fields,
)
from core.models import ActivityLog, ActivityLogPartner
from logistics.models import LogisticsDeal, LogisticsShipment, PurchaseInvoice
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import UserCompanyMembership
from tenants.models import Currency
from tenants.services import create_company


class ActivityServiceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="mgr", password="x")
        cls.tenant = create_company("شركة السجل", cls.manager)

    def test_log_activity_creates_row(self):
        log_activity(
            action="create", entity_type="sales_invoice", entity_id=7,
            entity_label="INV-7", description="إنشاء", tenant=self.tenant, user=self.manager,
        )
        row = ActivityLog.objects.get(entity_type="sales_invoice", entity_id=7)
        assert row.action == "create"
        assert row.tenant_id == self.tenant.TenantID
        assert row.user_id == self.manager.id
        assert row.is_view is False

    def test_log_view_marks_is_view(self):
        log_view(entity_type="deal", entity_id=3, entity_label="D-0003", tenant=self.tenant, user=self.manager)
        row = ActivityLog.objects.get(entity_type="deal", entity_id=3)
        assert row.is_view is True
        assert row.action == "view"

    def test_one_activity_links_multiple_partners_without_duplicates(self):
        supplier = Partner.objects.create(
            tenant=self.tenant, name="مورد النشاط", partner_type="Supplier")
        agent = Partner.objects.create(
            tenant=self.tenant, name="وكيل النشاط", partner_type="FreightForwarder")

        log_activity(
            action="create", entity_type="shipment", entity_id=17,
            entity_label="SH-0017", tenant=self.tenant, user=self.manager,
            partner_ids=[supplier.id, agent.id, supplier.id],
        )

        row = ActivityLog.objects.get(entity_type="shipment", entity_id=17)
        assert ActivityLog.objects.filter(entity_type="shipment", entity_id=17).count() == 1
        assert set(ActivityLogPartner.objects.filter(
            activity=row).values_list("partner_id", flat=True)) == {supplier.id, agent.id}

    def test_failure_is_swallowed(self):
        # مجموعة غير قابلة للتسلسل JSON → create يفشل داخلياً ويُبتلع (لا استثناء).
        # assertLogs يلتقط سجل الخطأ فيمنع تسرّب traceback إلى مخرجات الاختبارات،
        # ويؤكّد الشقّ الثاني من العقد: الفشل يُبتلع **ويُسجَّل** — لا يُبتلع بصمت.
        before = ActivityLog.objects.count()
        with self.assertLogs("core.activity", level="ERROR") as captured:
            log_activity(
                action="create", entity_type="x", metadata={"bad": {1, 2, 3}},
                tenant=self.tenant, user=self.manager,
            )
        assert ActivityLog.objects.count() == before  # لم يُنشأ صف، ولم يُرمَ استثناء
        assert "log_activity failed" in captured.output[0]
        assert "TypeError" in captured.output[0]  # سبب الفشل محفوظ في الـ traceback

    def test_no_tenant_is_noop(self):
        # شركة ثانية تُعطّل auto-resolve أحادي الشركة، فيبقى tenant=None فعلاً.
        create_company("شركة ثانية", User.objects.create_user(username="mgr2", password="x"))
        before = ActivityLog.objects.count()
        log_activity(action="create", entity_type="x", tenant=None, request=None, user=self.manager)
        assert ActivityLog.objects.count() == before


class DocumentChangeDetailTest(APITestCase):
    """تفصيل الحركة: ماذا فعل المستخدم بالضبط داخل المستند — لا «تعديل» مجرّدة."""

    LINE_LABELS = {"quantity": "الكمية", "unit_price": "السعر"}

    def _lines(self, *rows):
        return [
            SimpleNamespace(product_id=pid, quantity=Decimal(q), unit_price=Decimal(p), label=name)
            for pid, name, q, p in rows
        ]

    def _snapshot(self, lines):
        return snapshot_document_lines(
            lines, label=lambda line: line.label, fields=self.LINE_LABELS)

    def test_price_change_is_captured_with_old_and_new_value(self):
        before = self._snapshot(self._lines((3, "إطار 205", "2", "100")))
        after = self._snapshot(self._lines((3, "إطار 205", "2", "120")))
        changes = build_line_changes(before=before, after=after, labels=self.LINE_LABELS)
        assert changes == [{
            "kind": "line_changed",
            "label": "إطار 205",
            "changes": [{"field": "unit_price", "label": "السعر", "old": "100", "new": "120"}],
        }]
        assert describe_activity_changes(changes) == "«إطار 205»: السعر من 100 إلى 120"

    def test_added_and_removed_items_are_named(self):
        before = self._snapshot(self._lines((3, "إطار 205", "2", "100")))
        after = self._snapshot(self._lines((7, "زيت محرك", "1", "50")))
        changes = build_line_changes(before=before, after=after, labels=self.LINE_LABELS)
        kinds = [c["kind"] for c in changes]
        assert kinds == ["line_removed", "line_added"]
        text = describe_activity_changes(changes)
        assert "حذف صنف «إطار 205»" in text
        assert "أضاف صنف «زيت محرك» (الكمية 1 · السعر 50)" in text

    def test_repeated_product_keeps_two_distinct_lines(self):
        before = self._snapshot(self._lines(
            (3, "إطار 205", "2", "100"), (3, "إطار 205", "1", "90")))
        after = self._snapshot(self._lines((3, "إطار 205", "2", "100")))
        changes = build_line_changes(before=before, after=after, labels=self.LINE_LABELS)
        assert [c["kind"] for c in changes] == ["line_removed"]

    def test_unchanged_lines_produce_no_noise(self):
        rows = ((3, "إطار 205", "2.0000", "100.00"),)
        changes = build_line_changes(
            before=self._snapshot(self._lines(*rows)),
            after=self._snapshot(self._lines(*rows)),
            labels=self.LINE_LABELS,
        )
        assert changes == []

    def test_decimal_values_drop_trailing_zeros(self):
        before = self._snapshot(self._lines((3, "إطار", "2.0000", "150.5000")))
        after = self._snapshot(self._lines((3, "إطار", "2.0000", "175.0000")))
        changes = build_line_changes(before=before, after=after, labels=self.LINE_LABELS)
        assert changes[0]["changes"][0]["old"] == "150.5"
        assert changes[0]["changes"][0]["new"] == "175"

    def test_zero_valued_field_is_not_listed_on_added_line(self):
        labels = {**self.LINE_LABELS, "discount": "الخصم"}
        line = SimpleNamespace(
            product_id=3, quantity=Decimal("1"), unit_price=Decimal("50"),
            discount=Decimal("0.00"), label="زيت")
        after = snapshot_document_lines([line], label=lambda l: l.label, fields=labels)
        changes = build_line_changes(before=[], after=after, labels=labels)
        assert describe_activity_changes(changes) == "أضاف صنف «زيت» (الكمية 1 · السعر 50)"

    def test_snapshot_fields_prefers_display_label(self):
        row = SimpleNamespace(
            invoice_type="cash", get_invoice_type_display=lambda: "نقدي", notes="ملاحظة")
        assert snapshot_fields(row, ["invoice_type", "notes"]) == {
            "invoice_type": "نقدي", "notes": "ملاحظة"}


class ActivityApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="boss2", password="x")
        cls.staff = User.objects.create_user(username="staff2", password="x")
        cls.tenant = create_company("شركة API السجل", cls.manager)
        UserCompanyMembership.objects.create(user=cls.staff, tenant=cls.tenant, role="staff")

    def _h(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _seed(self):
        log_activity(action="create", entity_type="sales_invoice", entity_id=1,
                     entity_label="INV-1", tenant=self.tenant, user=self.manager)
        log_view(entity_type="sales_invoice", entity_id=1, entity_label="INV-1",
                 tenant=self.tenant, user=self.staff)

    def test_global_feed_manager_only(self):
        self._seed()
        # غير المدير ممنوع من الصفحة العامة (بلا entity_id)
        assert self.client.get("/api/activity/", **self._h(self.staff)).status_code == 403
        # المدير مسموح
        res = self.client.get("/api/activity/", **self._h(self.manager))
        assert res.status_code == 200, res.content

    def test_global_feed_excludes_views_by_default(self):
        self._seed()
        res = self.client.get("/api/activity/", **self._h(self.manager))
        data = res.json()
        rows = data["results"] if isinstance(data, dict) and "results" in data else data
        actions = {r["action"] for r in rows}
        assert "create" in actions
        assert "view" not in actions  # أحداث العرض مستبعَدة من الجدول العام

    def test_include_views_shows_views(self):
        self._seed()
        res = self.client.get(
            f"/api/activity/?user={self.staff.id}&include_views=true", **self._h(self.manager))
        rows = res.json().get("results", res.json())
        assert any(r["action"] == "view" for r in rows)

    def test_entity_scoped_feed_open_to_member(self):
        self._seed()
        # سجل مستند واحد متاح للموظف العادي (ليس صفحة عامة)
        res = self.client.get(
            "/api/activity/?entity_type=sales_invoice&entity_id=1", **self._h(self.staff))
        assert res.status_code == 200, res.content
        rows = res.json().get("results", res.json())
        # سجل المستند يشمل العرض والتعديل معاً
        assert len(rows) >= 2

    def test_default_date_is_today(self):
        # صف قديم (بالأمس) يجب ألا يظهر في العرض العام الافتراضي.
        old = ActivityLog.objects.create(
            tenant=self.tenant, user=self.manager, action="create",
            entity_type="sales_invoice", entity_id=99, entity_label="OLD")
        ActivityLog.objects.filter(pk=old.pk).update(
            timestamp=timezone.now() - timezone.timedelta(days=1))
        log_activity(action="create", entity_type="sales_invoice", entity_id=100,
                     entity_label="NEW", tenant=self.tenant, user=self.manager)
        res = self.client.get("/api/activity/", **self._h(self.manager))
        rows = res.json().get("results", res.json())
        ids = {r["entity_id"] for r in rows}
        assert 100 in ids and 99 not in ids

    def test_partner_feed_includes_current_and_historical_related_documents(self):
        currency = Currency.objects.filter(Code="ILS").first()
        supplier = Partner.objects.create(
            tenant=self.tenant, name="مورد البطاقة", partner_type="Supplier")
        customer = Partner.objects.create(
            tenant=self.tenant, name="عميل البطاقة", partner_type="Customer")
        agent = Partner.objects.create(
            tenant=self.tenant, name="وكيل البطاقة", partner_type="FreightForwarder")
        other = Partner.objects.create(
            tenant=self.tenant, name="طرف آخر", partner_type="Supplier")

        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-ACT-1", partner=supplier,
            order_date=date(2026, 7, 1), currency=currency,
        )
        purchase = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PI-ACT-1", partner=supplier,
            invoice_date=date(2026, 7, 2), currency=currency,
        )
        sale = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SI-ACT-1", customer=customer,
            invoice_date=date(2026, 7, 3), invoice_type="credit",
            status="draft", currency=currency,
        )
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-ACT-1", shipping_agent=agent)

        # صفوف تاريخية بلا partner_links يجب أن تظهر من علاقة المستند الحالية.
        log_activity(
            action="update", entity_type="deal", entity_id=deal.id,
            entity_label=deal.ref_number, tenant=self.tenant, user=self.manager)
        log_activity(
            action="update", entity_type="purchase_invoice", entity_id=purchase.id,
            entity_label=purchase.invoice_number, tenant=self.tenant, user=self.manager)
        log_activity(
            action="update", entity_type="sales_invoice", entity_id=sale.id,
            entity_label=sale.invoice_number, tenant=self.tenant, user=self.manager)
        log_activity(
            action="update", entity_type="shipment", entity_id=shipment.id,
            entity_label=shipment.shipment_number, tenant=self.tenant, user=self.manager)
        log_activity(
            action="update", entity_type="deal", entity_id=999999,
            entity_label="UNRELATED", tenant=self.tenant, user=self.manager,
            partner_ids=[other.id],
        )

        expected = {
            supplier.id: {"D-ACT-1", "PI-ACT-1"},
            customer.id: {"SI-ACT-1"},
            agent.id: {"SH-ACT-1"},
        }
        for partner_id, labels in expected.items():
            response = self.client.get(
                f"/api/activity/?partner_id={partner_id}", **self._h(self.staff))
            assert response.status_code == 200, response.content
            rows = response.json().get("results", response.json())
            assert {row["entity_label"] for row in rows} == labels


class SessionEventTest(APITestCase):
    def test_login_and_logout_logged(self):
        user = User.objects.create_user(username="sess@x.com", email="sess@x.com", password="pw", is_active=True)
        tenant = create_company("شركة الجلسة", user)  # يجعل user مديراً/عضواً

        res = self.client.post(
            "/api/hr/auth/login/",
            data=json.dumps({"email": "sess@x.com", "password": "pw"}),
            content_type="application/json",
        )
        assert res.status_code == 200, res.content
        token = res.json()["token"]
        assert ActivityLog.objects.filter(
            tenant=tenant, user=user, action="login", entity_type="session").exists()

        out = self.client.post(
            "/api/hr/auth/logout/", HTTP_AUTHORIZATION=f"Token {token}")
        assert out.status_code == 200, out.content
        assert ActivityLog.objects.filter(
            tenant=tenant, user=user, action="logout", entity_type="session").exists()
