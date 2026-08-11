from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import AccountingAuditLog, Currency
from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    ReviewQuery,
    TaxPeriodReview,
)
from accountant_portal.services import accept_company_invitation, create_company_invitation
from core.models import ActivityLog, TenantModule
from core.modules import invalidate_module_cache
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Tenant, UserCompanyMembership


class ReviewWorkspaceTest(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("m4-manager")
        self.accountant = User.objects.create_user("m4-accountant", email="m4@example.com")
        self.tenant = Tenant.objects.create(CompanyName="شركة المراجعة")
        self.other_tenant = Tenant.objects.create(CompanyName="شركة أخرى")
        for tenant in (self.tenant, self.other_tenant):
            TenantModule.objects.create(tenant=tenant, module_key="accountant_portal", enabled=True)
            invalidate_module_cache(tenant.pk)
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="accountant",
            tax_registration_number="TAX-M4-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        engagement, token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=["review.query.create", "finance.export.package", "tax.period.view"],
        )
        self.engagement = accept_company_invitation(accountant=self.accountant, token=token)
        self.currency = Currency.objects.create(
            Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True,
        )
        self.customer = Partner.objects.create(
            tenant=self.tenant, name="زبون المراجعة", partner_type="customer", tax_number="9999",
        )
        self.invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number="SI-M4-1",
            customer=self.customer,
            invoice_date=date(2026, 6, 15),
            currency=self.currency,
            status=SalesInvoice.STATUS_POSTED,
            subtotal_excl_tax=Decimal("100.00"),
            tax_amount=Decimal("16.00"),
            grand_total=Decimal("116.00"),
        )
        self.period = TaxPeriodReview.objects.create(
            tenant=self.tenant,
            period_from=date(2026, 6, 1),
            period_to=date(2026, 6, 30),
            status="ready",
        )
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def _create_query(self, **overrides):
        payload = {
            "title": "فاتورة بلا مرفق",
            "body": "أرفق صورة الفاتورة الأصلية.",
            "severity": "blocker",
            "entity_type": "sales_invoice",
            "entity_id": self.invoice.pk,
            "period_review_id": self.period.pk,
        }
        payload.update(overrides)
        return self.client.post("/api/accountant/review/queries/", payload, format="json", **self.headers)

    def test_blocker_query_moves_the_period_to_needs_company_action(self):
        self.client.force_authenticate(self.accountant)

        response = self._create_query()

        self.assertEqual(response.status_code, 201, response.content)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "needs_company_action")

    def test_answer_then_resolve_returns_the_period_to_ready(self):
        self.client.force_authenticate(self.accountant)
        created = self._create_query()
        query_id = created.data["query"]["id"]

        self.client.force_authenticate(self.manager)
        answered = self.client.post(
            f"/api/accountant/review/queries/{query_id}/answer/",
            {"answer_body": "أُرفقت الفاتورة."},
            format="json",
            **self.headers,
        )
        self.client.force_authenticate(self.accountant)
        resolved = self.client.post(
            f"/api/accountant/review/queries/{query_id}/resolve/", {}, format="json", **self.headers,
        )

        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertEqual(answered.data["query"]["status"], "answered")
        self.assertEqual(resolved.status_code, 200, resolved.content)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, "ready")

    def test_query_cannot_reference_another_companys_document(self):
        foreign_customer = Partner.objects.create(
            tenant=self.other_tenant, name="زبون آخر", partner_type="customer",
        )
        foreign = SalesInvoice.objects.create(
            tenant=self.other_tenant,
            invoice_number="SI-OTHER-1",
            customer=foreign_customer,
            invoice_date=date(2026, 6, 15),
            currency=self.currency,
            status=SalesInvoice.STATUS_POSTED,
        )
        self.client.force_authenticate(self.accountant)

        response = self._create_query(entity_id=foreign.pk)

        self.assertEqual(response.status_code, 404, response.content)
        self.assertFalse(ReviewQuery.objects.filter(entity_id=foreign.pk).exists())

    def test_accountant_cannot_answer_and_company_cannot_raise_without_the_key(self):
        self.client.force_authenticate(self.accountant)
        created = self._create_query()
        query_id = created.data["query"]["id"]

        answered_by_accountant = self.client.post(
            f"/api/accountant/review/queries/{query_id}/answer/",
            {"answer_body": "لا يجوز"},
            format="json",
            **self.headers,
        )

        self.assertEqual(answered_by_accountant.status_code, 403, answered_by_accountant.content)

    def test_query_text_with_newlines_is_sanitized_in_the_activity_log(self):
        self.client.force_authenticate(self.accountant)

        response = self._create_query(title="عنوان\r\nمزوَّر action=DELETE")

        self.assertEqual(response.status_code, 201, response.content)
        entry = ActivityLog.objects.filter(entity_type="accountant_review_query").latest("id")
        self.assertNotIn("\n", entry.description)
        self.assertNotIn("\r", entry.description)

    def test_review_package_csv_export_is_scoped_and_audited(self):
        self.client.force_authenticate(self.accountant)

        response = self.client.post(
            "/api/accountant/review/export/",
            {"period_from": "2026-06-01", "period_to": "2026-06-30", "format": "csv"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode("utf-8-sig")
        self.assertIn("SI-M4-1", body)
        self.assertNotIn("SI-OTHER-1", body)
        self.assertTrue(
            AccountingAuditLog.objects.filter(
                tenant=self.tenant, action="PKG_EXPORTED", model_name="ReviewPackage",
            ).exists()
        )

    def test_export_requires_the_package_permission(self):
        engagement = AccountantEngagement.objects.get(pk=self.engagement.pk)
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        membership.permission_overrides.filter(permission_key="finance.export.package").update(allowed=False)
        self.client.force_authenticate(self.accountant)

        response = self.client.post(
            "/api/accountant/review/export/",
            {"period_from": "2026-06-01", "period_to": "2026-06-30", "format": "csv"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(engagement.status, "active")

    def test_activity_feed_shows_only_the_requesting_accountant(self):
        other_accountant = User.objects.create_user("m4-other-accountant", email="m4b@example.com")
        AccountantProfile.objects.create(
            user=other_accountant,
            professional_type="accountant",
            tax_registration_number="TAX-M4-2",
            business_address="نابلس",
            email_verified_at=timezone.now(),
        )
        _, other_token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=other_accountant,
            scope=["review.query.create"],
        )
        accept_company_invitation(accountant=other_accountant, token=other_token)
        self.client.force_authenticate(other_accountant)
        self._create_query(title="ملاحظة المحاسب الآخر")

        self.client.force_authenticate(self.accountant)
        mine = self.client.get("/api/accountant/activity/", **self.headers)
        self.client.force_authenticate(self.manager)
        company_wide = self.client.get("/api/accountant/activity/", **self.headers)

        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertTrue(all(row["user_id"] == self.accountant.pk for row in mine.data["results"]))
        self.assertEqual(company_wide.status_code, 200, company_wide.content)
        self.assertTrue(
            any(row["user_id"] == other_accountant.pk for row in company_wide.data["results"])
        )
