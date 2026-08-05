"""M7 — التصليب: أسرار السجلات، حقن الأسطر، منع التعديل عبر مسار بديل، تدقيق كل فعل حسّاس."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import AccountingAuditLog, Currency
from accountant_portal.models import AccountantProfile, TaxPeriodReview
from accountant_portal.services import accept_company_invitation, create_company_invitation
from core.models import ActivityLog, TenantModule
from core.modules import invalidate_module_cache
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Tenant, UserCompanyMembership


PASSWORD = "Hardening-Pass-4931"


class HardeningTest(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("m7-manager", password=PASSWORD)
        self.accountant = User.objects.create_user("m7-accountant", email="m7@example.com", password=PASSWORD)
        self.tenant = Tenant.objects.create(CompanyName="شركة التصليب")
        TenantModule.objects.create(tenant=self.tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(self.tenant.pk)
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="licensed_auditor",
            tax_registration_number="TAX-M7-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        self.engagement, self.token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=["tax.period.view", "tax.period.prepare", "tax.period.approve"],
            note="ملاحظة\r\nمزوَّرة action=DELETE",
        )
        accept_company_invitation(accountant=self.accountant, token=self.token)
        self.currency = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        self.customer = Partner.objects.create(
            tenant=self.tenant, name="زبون", partner_type="customer", tax_number="55",
        )
        self.invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number="SI-M7-1",
            customer=self.customer,
            invoice_date=date(2026, 6, 10),
            currency=self.currency,
            status=SalesInvoice.STATUS_POSTED,
            subtotal_excl_tax=Decimal("100.00"),
            tax_amount=Decimal("16.00"),
            grand_total=Decimal("116.00"),
        )
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def test_no_password_or_invitation_token_reaches_any_log(self):
        self.client.force_authenticate(self.accountant)
        prepared = self.client.post(
            "/api/accountant/tax/periods/prepare/",
            {"period_from": "2026-06-01", "period_to": "2026-06-30"},
            format="json",
            **self.headers,
        )
        approved = self.client.post(
            f"/api/accountant/tax/periods/{prepared.data['period']['id']}/approve/",
            {"reauth_password": PASSWORD},
            format="json",
            **self.headers,
        )

        self.assertEqual(approved.status_code, 200, approved.content)
        activity = " ".join(
            f"{row.description} {row.entity_label} {row.metadata}"
            for row in ActivityLog.objects.all()
        )
        audit = " ".join(
            f"{row.action} {row.change_details}" for row in AccountingAuditLog.objects.all()
        )
        for secret in (PASSWORD, self.token):
            self.assertNotIn(secret, activity)
            self.assertNotIn(secret, audit)

    def test_invitation_token_is_never_returned_by_the_api(self):
        self.client.force_authenticate(self.manager)

        listed = self.client.get("/api/accountant/company/engagements/", **self.headers)

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertNotIn(self.token, str(listed.data))
        self.assertNotIn("invitation_token_hash", str(listed.data))

    def test_carriage_returns_in_user_text_never_split_a_log_line(self):
        entries = ActivityLog.objects.filter(entity_type="accountant_engagement")

        self.assertTrue(entries.exists())
        for row in entries:
            self.assertNotIn("\n", row.description)
            self.assertNotIn("\r", row.description)
            self.assertNotIn("\n", row.entity_label)

    def test_accountant_cannot_edit_a_posted_document_through_another_endpoint(self):
        self.client.force_authenticate(self.accountant)

        patched = self.client.patch(
            f"/api/sales/invoices/{self.invoice.pk}/",
            {"grand_total": "1.00"},
            format="json",
            **self.headers,
        )
        deleted = self.client.delete(f"/api/sales/invoices/{self.invoice.pk}/", **self.headers)

        self.assertEqual(patched.status_code, 403, patched.content)
        self.assertEqual(deleted.status_code, 403, deleted.content)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.grand_total, Decimal("116.00"))

    def test_every_sensitive_action_writes_a_financial_audit_row(self):
        self.client.force_authenticate(self.accountant)
        prepared = self.client.post(
            "/api/accountant/tax/periods/prepare/",
            {"period_from": "2026-06-01", "period_to": "2026-06-30"},
            format="json",
            **self.headers,
        )
        period_id = prepared.data["period"]["id"]
        self.client.post(
            f"/api/accountant/tax/periods/{period_id}/approve/",
            {"reauth_password": PASSWORD}, format="json", **self.headers,
        )
        self.client.force_authenticate(self.manager)
        self.client.patch(
            "/api/accountant/company/settings/",
            {"filing_due_days": 20},
            format="json",
            **self.headers,
        )
        self.client.post(
            f"/api/accountant/company/engagements/{self.engagement.pk}/suspend/",
            {"reason": "مراجعة"},
            format="json",
            **self.headers,
        )

        written = set(
            AccountingAuditLog.objects.filter(tenant=self.tenant).values_list("action", flat=True)
        )
        for action in ("ENG_REQUESTED", "ENG_APPROVED", "ENG_SUSPENDED", "TAX_PREPARED", "TAX_APPROVED", "PORTAL_CFG_SET"):
            self.assertIn(action, written, action)
        self.assertTrue(all(len(action) <= 20 for action in written))

    def test_revoked_engagement_answer_is_a_typed_403_the_ui_can_act_on(self):
        from accountant_portal.services import revoke_engagement

        revoke_engagement(engagement=self.engagement, actor=self.manager, reason="انتهاء العقد")
        self.client.force_authenticate(self.accountant)

        response = self.client.get("/api/accountant/tax/periods/", **self.headers)

        self.assertIn(response.status_code, (403, 404))
        if response.status_code == 403:
            self.assertEqual(response.data.get("code"), "engagement_inactive")

    def test_locked_period_is_listed_but_never_reopened_by_the_accountant(self):
        period = TaxPeriodReview.objects.create(
            tenant=self.tenant,
            period_from=date(2026, 5, 1),
            period_to=date(2026, 5, 31),
            status="locked",
            locked_at=timezone.now(),
        )
        self.client.force_authenticate(self.accountant)

        response = self.client.post(
            f"/api/accountant/tax/periods/{period.pk}/reopen/",
            {"reason": "محاولة"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 403, response.content)
        period.refresh_from_db()
        self.assertEqual(period.status, "locked")
