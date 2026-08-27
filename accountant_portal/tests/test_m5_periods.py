from datetime import date, timedelta
from decimal import Decimal

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account, AccountingAuditLog, Currency
from accounting.services import post_journal
from accountant_portal.models import PortalSettings, ReviewQuery, TaxPeriodReview
from accountant_portal.readiness import run_readiness_checks
from accountant_portal.services import accept_company_invitation, create_company_invitation
from accountant_portal.models import AccountantProfile
from core.models import TenantModule
from core.modules import invalidate_module_cache
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import MemberPermission, Tenant, UserCompanyMembership


PASSWORD = "Reauth-Pass-4931"

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "accountant-portal-m5",
    }
}


class TaxPeriodBaseTest(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("m5-manager", password=PASSWORD)
        self.accountant = User.objects.create_user("m5-accountant", email="m5@example.com", password=PASSWORD)
        self.tenant = Tenant.objects.create(CompanyName="شركة الفترات")
        TenantModule.objects.create(tenant=self.tenant, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(self.tenant.pk)
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="accountant",
            tax_registration_number="TAX-M5-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        _, token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=[
                "tax.period.view",
                "tax.period.prepare",
                "tax.period.approve",
                "tax.filing.submit",
                "review.query.create",
            ],
        )
        accept_company_invitation(accountant=self.accountant, token=token)
        self.currency = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        self.customer = Partner.objects.create(
            tenant=self.tenant, name="زبون", partner_type="customer", tax_number="123",
        )
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def _invoice(self, number, day, **overrides):
        payload = {
            "tenant": self.tenant,
            "invoice_number": number,
            "customer": self.customer,
            "invoice_date": day,
            "currency": self.currency,
            "status": SalesInvoice.STATUS_POSTED,
            "subtotal_excl_tax": Decimal("100.00"),
            "tax_amount": Decimal("16.00"),
            "grand_total": Decimal("116.00"),
        }
        payload.update(overrides)
        return SalesInvoice.objects.create(**payload)

    def _prepare(self, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30)):
        self.client.force_authenticate(self.accountant)
        return self.client.post(
            "/api/accountant/tax/periods/prepare/",
            {"period_from": str(period_from), "period_to": str(period_to)},
            format="json",
            **self.headers,
        )


class TaxPeriodLifecycleTest(TaxPeriodBaseTest):
    def test_prepare_is_idempotent_and_builds_a_vat_statement(self):
        self._invoice("SI-1", date(2026, 6, 10))

        first = self._prepare()
        second = self._prepare()

        self.assertEqual(first.status_code, 201, first.content)
        self.assertIsNotNone(first.data["period"]["vat"])
        self.assertEqual(first.data["period"]["vat"]["total_sales_vat"], "16.00")
        self.assertEqual(second.status_code, 409, second.content)
        self.assertEqual(second.data["code"], "period_overlap")
        self.assertEqual(TaxPeriodReview.objects.filter(tenant=self.tenant).count(), 1)

    def test_period_boundaries_include_the_last_day_and_exclude_the_next(self):
        self._invoice("SI-IN", date(2026, 6, 30))
        self._invoice("SI-OUT", date(2026, 7, 1))

        prepared = self._prepare()

        self.assertEqual(prepared.status_code, 201, prepared.content)
        self.assertEqual(prepared.data["period"]["vat"]["total_sales_vat"], "16.00")

    def test_returns_are_subtracted_from_the_statement(self):
        original = self._invoice("SI-2", date(2026, 6, 10))
        self._invoice(
            "SR-2", date(2026, 6, 12),
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
            original_invoice=original,
        )

        prepared = self._prepare()

        self.assertEqual(prepared.data["period"]["vat"]["total_sales_vat"], "0.00")

    def test_approval_needs_reauth_the_permission_and_zero_blockers(self):
        self._invoice("SI-3", date(2026, 6, 10))
        period_id = self._prepare().data["period"]["id"]
        url = f"/api/accountant/tax/periods/{period_id}/approve/"

        without_reauth = self.client.post(url, {}, format="json", **self.headers)
        approved = self.client.post(url, {"reauth_password": PASSWORD}, format="json", **self.headers)

        self.assertEqual(without_reauth.status_code, 403, without_reauth.content)
        self.assertEqual(without_reauth.data["code"], "reauth_required")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.data["period"]["status"], "approved")
        self.assertTrue(
            AccountingAuditLog.objects.filter(
                tenant=self.tenant, action="TAX_APPROVED", model_name="TaxPeriodReview",
            ).exists()
        )

    def test_a_blocker_stops_approval_with_409(self):
        self._invoice("SI-4", date(2026, 6, 10), status=SalesInvoice.STATUS_DRAFT)
        period_id = self._prepare().data["period"]["id"]

        response = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/approve/",
            {"reauth_password": PASSWORD},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data["code"], "has_blockers")

    def test_approval_without_the_permission_is_403(self):
        self._invoice("SI-5", date(2026, 6, 10))
        period_id = self._prepare().data["period"]["id"]
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        MemberPermission.objects.filter(
            membership=membership, permission_key="tax.period.approve",
        ).update(allowed=False)

        response = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/approve/",
            {"reauth_password": PASSWORD},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 403, response.content)

    def test_submission_locks_the_period_and_reopen_is_refused(self):
        self._invoice("SI-6", date(2026, 6, 10))
        period_id = self._prepare().data["period"]["id"]
        self.client.post(
            f"/api/accountant/tax/periods/{period_id}/approve/",
            {"reauth_password": PASSWORD}, format="json", **self.headers,
        )

        submitted = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/mark-submitted/",
            {"submission_reference": "VAT-2026-06", "reauth_password": PASSWORD},
            format="json",
            **self.headers,
        )
        self.client.force_authenticate(self.manager)
        reopened = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/reopen/",
            {"reason": "خطأ في الأرقام"},
            format="json",
            **self.headers,
        )

        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(submitted.data["period"]["status"], "locked")
        self.assertEqual(reopened.status_code, 409, reopened.content)
        self.assertEqual(reopened.data["code"], "period_locked")
        for action in ("TAX_SUBMITTED", "TAX_LOCKED"):
            self.assertTrue(
                AccountingAuditLog.objects.filter(tenant=self.tenant, action=action).exists(),
                action,
            )

    def test_manager_reopens_an_approved_period_with_a_mandatory_reason(self):
        self._invoice("SI-7", date(2026, 6, 10))
        period_id = self._prepare().data["period"]["id"]
        self.client.post(
            f"/api/accountant/tax/periods/{period_id}/approve/",
            {"reauth_password": PASSWORD}, format="json", **self.headers,
        )

        self.client.force_authenticate(self.manager)
        without_reason = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/reopen/", {}, format="json", **self.headers,
        )
        reopened = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/reopen/",
            {"reason": "تصحيح فاتورة"},
            format="json",
            **self.headers,
        )

        self.assertEqual(without_reason.status_code, 400, without_reason.content)
        self.assertEqual(reopened.status_code, 200, reopened.content)
        self.assertEqual(reopened.data["period"]["reopen_count"], 1)
        self.assertIn(reopened.data["period"]["status"], ("in_review", "ready"))

    def test_scope_snapshot_never_changes_effective_authorization(self):
        self._invoice("SI-8", date(2026, 6, 10))
        period_id = self._prepare().data["period"]["id"]
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        MemberPermission.objects.filter(
            membership=membership, permission_key="tax.period.approve",
        ).update(allowed=False)
        engagement = self.accountant.accountant_engagements.get(tenant=self.tenant)
        engagement.approved_scope_snapshot = ["tax.period.approve", "admin.settings.manage"]
        engagement.save(update_fields=["approved_scope_snapshot"])

        response = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/approve/",
            {"reauth_password": PASSWORD},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 403, response.content)

    def test_clearance_endpoint_is_reserved_and_returns_501(self):
        self.client.force_authenticate(self.accountant)
        membership = UserCompanyMembership.objects.get(user=self.accountant, tenant=self.tenant)
        MemberPermission.objects.filter(
            membership=membership, permission_key="tax.clearance.issue",
        ).update(allowed=True)

        response = self.client.post("/api/accountant/tax/clearance/", {}, format="json", **self.headers)

        self.assertEqual(response.status_code, 501, response.content)


class ReadinessChecksTest(TaxPeriodBaseTest):
    def _findings(self, period=None):
        return {
            item.code: item
            for item in run_readiness_checks(
                tenant=self.tenant,
                period_from=date(2026, 6, 1),
                period_to=date(2026, 6, 30),
                settings=PortalSettings.objects.get_or_create(tenant=self.tenant)[0],
                period=period,
            )
        }

    def test_missing_party_tax_number_and_draft_documents_are_blockers(self):
        no_tax = Partner.objects.create(tenant=self.tenant, name="بلا رقم", partner_type="customer")
        self._invoice("SI-A", date(2026, 6, 5), customer=no_tax)
        self._invoice("SI-B", date(2026, 6, 6), status=SalesInvoice.STATUS_DRAFT)

        findings = self._findings()

        self.assertEqual(findings["MISSING_PARTY_TAX_NO"].severity, "blocker")
        self.assertEqual(findings["UNPOSTED_DOCS"].severity, "blocker")

    def test_foreign_currency_without_a_rate_is_a_blocker_per_article_13(self):
        usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$", IsBaseCurrency=False)
        self._invoice("SI-C", date(2026, 6, 7), currency=usd, exchange_rate=Decimal("1"))

        findings = self._findings()

        self.assertEqual(findings["FX_RATE_MISSING"].severity, "blocker")

    def test_zero_rated_lines_without_a_tax_rate_are_a_warning(self):
        invoice = self._invoice("SI-D", date(2026, 6, 8), tax_amount=Decimal("0.00"))
        from sales.models import SalesInvoiceLine
        from inventory.models import Product

        product = Product.objects.create(tenant=self.tenant, name_ar="منتج", sku="SKU-1")
        SalesInvoiceLine.objects.create(
            tenant=self.tenant,
            invoice=invoice,
            product=product,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            line_total_excl_tax=Decimal("100"),
            line_tax_amount=Decimal("0"),
        )

        findings = self._findings()

        self.assertEqual(findings["UNCLASSIFIED_ZERO_RATED"].severity, "warning")

    def test_line_tax_that_disagrees_with_the_invoice_total_is_a_blocker(self):
        from inventory.models import Product
        from sales.models import SalesInvoiceLine

        invoice = self._invoice("SI-MIS", date(2026, 6, 11))
        product = Product.objects.create(tenant=self.tenant, name_ar="منتج مطابقة", sku="SKU-MIS")
        SalesInvoiceLine.objects.create(
            tenant=self.tenant,
            invoice=invoice,
            product=product,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            line_total_excl_tax=Decimal("100"),
            line_tax_amount=Decimal("9.00"),  # الفاتورة تقول 16.00
        )

        findings = self._findings()

        self.assertEqual(findings["LINE_VAT_MISMATCH"].severity, "blocker")
        self.assertEqual(findings["LINE_VAT_MISMATCH"].count, 1)

    def test_matching_line_tax_raises_no_mismatch(self):
        from inventory.models import Product
        from sales.models import SalesInvoiceLine

        invoice = self._invoice("SI-OK", date(2026, 6, 12))
        product = Product.objects.create(tenant=self.tenant, name_ar="منتج مطابق", sku="SKU-OK")
        SalesInvoiceLine.objects.create(
            tenant=self.tenant,
            invoice=invoice,
            product=product,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            line_total_excl_tax=Decimal("100"),
            line_tax_amount=Decimal("16.00"),
        )

        self.assertNotIn("LINE_VAT_MISMATCH", self._findings())

    def test_input_vat_older_than_the_window_is_a_warning_per_article_36(self):
        self._invoice(
            "PI-OLD", date(2025, 6, 1),
            invoice_kind=SalesInvoice.INVOICE_KIND_PURCHASE,
        )

        findings = self._findings()

        self.assertEqual(findings["INPUT_VAT_EXPIRED"].severity, "warning")

    def test_duplicate_invoice_number_is_blocked_by_the_database_and_by_the_check(self):
        from django.db import IntegrityError, transaction

        self._invoice("SI-DUP", date(2026, 6, 9))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._invoice("SI-DUP", date(2026, 6, 10))

        # القيد الفريد هو خط الدفاع الأول؛ الفحص يبقى للبيانات القديمة المستوردة.
        self.assertNotIn("DUPLICATE_INVOICE_NO", self._findings())

    def test_all_checks_stay_within_six_queries_on_a_thousand_invoices(self):
        SalesInvoice.objects.bulk_create([
            SalesInvoice(
                tenant=self.tenant,
                invoice_number=f"SI-{index:04d}",
                customer=self.customer,
                invoice_date=date(2026, 6, 10),
                currency=self.currency,
                status=SalesInvoice.STATUS_POSTED,
                subtotal_excl_tax=Decimal("100.00"),
                tax_amount=Decimal("16.00"),
                grand_total=Decimal("116.00"),
            )
            for index in range(1000)
        ])
        settings_row = PortalSettings.objects.get_or_create(tenant=self.tenant)[0]

        with self.assertNumQueries(6):
            run_readiness_checks(
                tenant=self.tenant,
                period_from=date(2026, 6, 1),
                period_to=date(2026, 6, 30),
                settings=settings_row,
            )


@override_settings(CACHES=LOCMEM_CACHE)
class TaxPeriodLockGuardTest(TaxPeriodBaseTest):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.expense = Account.objects.create(
            tenant=self.tenant, code="5101", name="مصروف", account_type="Expense",
        )
        self.cash = Account.objects.create(
            tenant=self.tenant, code="1101", name="صندوق", account_type="Asset",
        )
        self.period = TaxPeriodReview.objects.create(
            tenant=self.tenant,
            period_from=date(2026, 6, 1),
            period_to=date(2026, 6, 30),
            status="locked",
            locked_at=timezone.now(),
        )

    def _post(self, day):
        with patch("accounting.services.validate_fiscal_period"):
            return self._post_journal(day)

    def _post_journal(self, day):
        return post_journal(
            tenant_id=self.tenant.pk,
            transaction_date=day,
            reference_type="TEST",
            reference_id=int(day.strftime("%Y%m%d")),
            description="اختبار قفل الفترة",
            lines_data=[
                {"account": self.expense.pk, "debit": Decimal("10"), "credit": Decimal("0")},
                {"account": self.cash.pk, "debit": Decimal("0"), "credit": Decimal("10")},
            ],
            user=self.manager,
        )

    def test_locked_period_blocks_posting_inside_it_only(self):
        with self.assertRaises(ValidationError):
            self._post(date(2026, 6, 15))

        outside = self._post(date(2026, 7, 1))
        self.assertTrue(outside.is_posted)

    def test_company_may_allow_posting_inside_a_locked_period(self):
        PortalSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"lock_blocks_posting": False},
        )

        posted = self._post(date(2026, 6, 15))

        self.assertTrue(posted.is_posted)

    def test_guard_costs_no_query_when_the_module_is_disabled(self):
        TenantModule.objects.filter(tenant=self.tenant).update(enabled=False)
        invalidate_module_cache(self.tenant.pk)
        from accountant_portal.guards import tax_period_lock_guard

        tax_period_lock_guard(self.tenant.pk, date(2026, 6, 15))  # يُدفّئ الكاش

        with self.assertNumQueries(0):
            tax_period_lock_guard(self.tenant.pk, date(2026, 6, 15))


class PeriodQueryInteractionTest(TaxPeriodBaseTest):
    def test_blocker_query_and_its_resolution_drive_the_period_status(self):
        self._invoice("SI-Q", date(2026, 6, 10))
        period_id = self._prepare().data["period"]["id"]
        period = TaxPeriodReview.objects.get(pk=period_id)

        created = self.client.post(
            "/api/accountant/review/queries/",
            {
                "title": "ينقص مرفق",
                "body": "أرفق الفاتورة",
                "severity": "blocker",
                "entity_type": "sales_invoice",
                "entity_id": SalesInvoice.objects.get(invoice_number="SI-Q").pk,
                "period_review_id": period_id,
            },
            format="json",
            **self.headers,
        )
        period.refresh_from_db()
        blocked_status = period.status
        blocked_approval = self.client.post(
            f"/api/accountant/tax/periods/{period_id}/approve/",
            {"reauth_password": PASSWORD}, format="json", **self.headers,
        )
        self.client.post(
            f"/api/accountant/review/queries/{created.data['query']['id']}/resolve/",
            {}, format="json", **self.headers,
        )
        period.refresh_from_db()

        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(blocked_status, "needs_company_action")
        self.assertEqual(blocked_approval.status_code, 409, blocked_approval.content)
        self.assertEqual(period.status, "ready")
        self.assertEqual(
            ReviewQuery.objects.get(pk=created.data["query"]["id"]).status, "resolved",
        )
