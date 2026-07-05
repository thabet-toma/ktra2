"""ملاحظات/تذكيرات بطاقة الزبون (CRM): إنشاء + عزل بين الشركات + تذكيرات مستحقة.

الهدف القابل للتحقق:
- POST ينشئ ملاحظة مربوطة بالزبون والشركة مع created_by.
- القائمة تُفلتَر بـ ?partner ولا تتسرّب بين الشركات.
- reminders-due يُعيد فقط ملاحظة غير منجزة تاريخ تذكيرها ≤ اليوم.
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
