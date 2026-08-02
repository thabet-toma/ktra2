"""ملاحظات/تذكيرات بطاقة الزبون (CRM): إنشاء + عزل بين الشركات + تذكيرات مستحقة.

الهدف القابل للتحقق:
- POST ينشئ ملاحظة مربوطة بالزبون والشركة مع created_by.
- القائمة تُفلتَر بـ ?partner ولا تتسرّب بين الشركات.
- reminders-due يُعيد فقط ملاحظة غير منجزة تاريخ تذكيرها ≤ اليوم.
- alerts يُعيد «عاجل» غير المنجزة التي حلّ موعدها — لأي طرف (عميل أو مورد).
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from partners.models import CustomerNote, Partner
from tenants.models import Tenant, UserCompanyMembership


class CustomerNotesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            TenantID=1, CompanyName="A", SubscriptionPlan="Enterprise", Status="Active")
        cls.tenant_b = Tenant.objects.create(
            TenantID=2, CompanyName="B", SubscriptionPlan="Enterprise", Status="Active")
        cls.user = User.objects.create_user(username="crm", password="x")
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant_a, role="manager", is_default=True)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant_b, role="manager")
        cls.cust_a = Partner.objects.create(tenant=cls.tenant_a, name="زبون A", partner_type="Customer")
        cls.cust_b = Partner.objects.create(tenant=cls.tenant_b, name="زبون B", partner_type="Customer")
        cls.supp_a = Partner.objects.create(tenant=cls.tenant_a, name="مورد A", partner_type="Supplier")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_create_note_sets_tenant_and_author(self):
        res = self.client.post(
            "/api/customer-notes/",
            {"partner": self.cust_a.id, "title": "متابعة دفعة", "body": "اتصال الأسبوع القادم",
             "remind_on": str(date.today() + timedelta(days=2))},
            format="json", HTTP_X_TENANT_ID="1")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        note = CustomerNote.objects.get(pk=res.data["id"])
        self.assertEqual(note.tenant_id, self.tenant_a.TenantID)
        self.assertEqual(note.created_by_id, self.user.id)
        self.assertEqual(res.data["created_by_name"], "crm")

    def test_list_filtered_by_partner_and_isolated(self):
        CustomerNote.objects.create(tenant=self.tenant_a, partner=self.cust_a, title="A-note")
        CustomerNote.objects.create(tenant=self.tenant_b, partner=self.cust_b, title="B-note")

        res = self.client.get(f"/api/customer-notes/?partner={self.cust_a.id}", HTTP_X_TENANT_ID="1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        titles = [n["title"] for n in res.data]
        self.assertIn("A-note", titles)
        self.assertNotIn("B-note", titles)  # عزل الشركة

    def test_reminders_due_only_pending_and_reached(self):
        today = date.today()
        due = CustomerNote.objects.create(
            tenant=self.tenant_a, partner=self.cust_a, title="مستحق", remind_on=today)
        CustomerNote.objects.create(
            tenant=self.tenant_a, partner=self.cust_a, title="مستقبلي",
            remind_on=today + timedelta(days=5))
        CustomerNote.objects.create(
            tenant=self.tenant_a, partner=self.cust_a, title="منجز",
            remind_on=today - timedelta(days=1), is_done=True)

        res = self.client.get("/api/customer-notes/reminders-due/", HTTP_X_TENANT_ID="1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in res.data]
        self.assertEqual(ids, [due.id])  # فقط المستحق غير المنجز
        self.assertEqual(res.data[0]["partner_name"], "زبون A")

    def test_priority_defaults_to_normal_and_round_trips(self):
        res = self.client.post(
            "/api/customer-notes/", {"partner": self.cust_a.id, "title": "بلا أولوية"},
            format="json", HTTP_X_TENANT_ID="1")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["priority"], "normal")
        self.assertEqual(res.data["priority_display"], "عادي")

        urgent = self.client.post(
            "/api/customer-notes/",
            {"partner": self.cust_a.id, "title": "عاجل جداً", "priority": "urgent"},
            format="json", HTTP_X_TENANT_ID="1")
        self.assertEqual(urgent.data["priority_display"], "عاجل")

    def test_alerts_only_urgent_due_and_pending(self):
        today = date.today()
        hit = CustomerNote.objects.create(
            tenant=self.tenant_a, partner=self.cust_a, title="عاجل متأخر",
            priority="urgent", remind_on=today - timedelta(days=3))
        CustomerNote.objects.create(  # عاجل لكن موعده لم يحن
            tenant=self.tenant_a, partner=self.cust_a, title="عاجل قادم",
            priority="urgent", remind_on=today + timedelta(days=1))
        CustomerNote.objects.create(  # عاجل ومنجز
            tenant=self.tenant_a, partner=self.cust_a, title="عاجل منجز",
            priority="urgent", remind_on=today, is_done=True)
        CustomerNote.objects.create(  # مستحق لكن أولويته عادية
            tenant=self.tenant_a, partner=self.cust_a, title="عادي مستحق",
            priority="normal", remind_on=today)

        res = self.client.get(
            f"/api/customer-notes/alerts/?partner={self.cust_a.id}", HTTP_X_TENANT_ID="1")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual([r["id"] for r in res.data], [hit.id])
        self.assertEqual(res.data[0]["priority_display"], "عاجل")

    def test_alerts_work_for_suppliers_too(self):
        note = CustomerNote.objects.create(
            tenant=self.tenant_a, partner=self.supp_a, title="لا تشترِ منه قبل التسوية",
            priority="urgent", remind_on=date.today())
        res = self.client.get(
            f"/api/customer-notes/alerts/?partner={self.supp_a.id}", HTTP_X_TENANT_ID="1")
        self.assertEqual([r["id"] for r in res.data], [note.id])

    def test_alerts_require_partner_and_respect_tenant(self):
        CustomerNote.objects.create(
            tenant=self.tenant_b, partner=self.cust_b, title="عاجل B",
            priority="urgent", remind_on=date.today())
        self.assertEqual(self.client.get(
            "/api/customer-notes/alerts/", HTTP_X_TENANT_ID="1").data, [])
        # الطرف من شركة أخرى ⇒ لا تسرّب حتى بتمرير معرّفه.
        self.assertEqual(self.client.get(
            f"/api/customer-notes/alerts/?partner={self.cust_b.id}",
            HTTP_X_TENANT_ID="1").data, [])

    def test_platform_note_round_trips_and_due_reminder_keeps_internal_target(self):
        payload = {
            "target_type": "supplier_quotation",
            "target_id": "quote-12",
            "target_label": "عرض استيراد SQ-12",
            "target_path": "/import-price-offers?doc=quote-12",
            "title": "العرض بدو مناقشة",
            "remind_on": str(date.today()),
            "priority": "medium",
        }
        created = self.client.post(
            "/api/customer-notes/", payload, format="json", HTTP_X_TENANT_ID="1")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertIsNone(created.data["partner"])

        listed = self.client.get(
            "/api/customer-notes/?target_type=supplier_quotation&target_id=quote-12",
            HTTP_X_TENANT_ID="1")
        self.assertEqual([row["id"] for row in listed.data], [created.data["id"]])

        due = self.client.get(
            "/api/customer-notes/reminders-due/", HTTP_X_TENANT_ID="1")
        reminder = next(row for row in due.data if row["id"] == created.data["id"])
        self.assertEqual(reminder["target_label"], "عرض استيراد SQ-12")
        self.assertEqual(reminder["target_path"], "/import-price-offers?doc=quote-12")
        self.assertIsNone(reminder["partner_id"])

    def test_note_target_and_partner_are_validated_inside_tenant_boundary(self):
        cross_tenant = self.client.post(
            "/api/customer-notes/",
            {"partner": self.cust_b.id, "title": "تسريب"},
            format="json", HTTP_X_TENANT_ID="1")
        self.assertEqual(cross_tenant.status_code, status.HTTP_400_BAD_REQUEST)

        unsafe_path = self.client.post(
            "/api/customer-notes/",
            {
                "target_type": "page",
                "target_id": "x",
                "target_label": "رابط خارجي",
                "target_path": "https://example.com/phish",
                "title": "غير آمن",
            },
            format="json", HTTP_X_TENANT_ID="1")
        self.assertEqual(unsafe_path.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_path", unsafe_path.data)
