"""P-H-3: SupplierPayment AP fallback chain."""
from django.test import TestCase

from accounting.models import Account
from logistics.services import _resolve_ap_account
from partners.models import Partner, PartnerGroup
from tenants.models import Tenant


class SupplierPaymentFallbackTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=110, CompanyName="AP Fall Test")
        cls.group = PartnerGroup.objects.create(
            tenant=cls.tenant, name="Group A",
        )
        cls.partner_no_link = Partner.objects.create(
            tenant=cls.tenant, name="No Link Partner",
            partner_type="Supplier",
        )
        cls.ap_account = Account.objects.create(
            tenant=cls.tenant, code="2101", name="ذمم موردين",
            account_type="Liability", is_active=True,
        )

    def test_fallback_to_code_2101(self):
        account = _resolve_ap_account(self.partner_no_link)
        self.assertIsNotNone(account)
        self.assertEqual(account.code, "2101")

    def test_linked_account_takes_priority(self):
        custom_ap = Account.objects.create(
            tenant=self.tenant, code="2201", name="AP Custom",
            account_type="Liability", is_active=True,
        )
        partner = Partner.objects.create(
            tenant=self.tenant, name="Linked Partner",
            partner_type="Supplier",
            linked_account=custom_ap,
        )
        account = _resolve_ap_account(partner)
        self.assertEqual(account.id, custom_ap.id)

    def test_group_account_payable_fallback(self):
        group_ap = Account.objects.create(
            tenant=self.tenant, code="2301", name="AP Group",
            account_type="Liability", is_active=True,
        )
        self.group.account_payable = group_ap
        self.group.save()
        partner = Partner.objects.create(
            tenant=self.tenant, name="Group Partner",
            partner_type="Supplier",
            group=self.group,
        )
        # The partners.signals post_save handler auto-creates a linked_account
        # for every new Partner. Clear it on the in-memory instance (not via
        # save() — that would re-trigger the signal) so we exercise the
        # group-fallback branch (level 2) of _resolve_ap_account.
        partner.linked_account = None
        account = _resolve_ap_account(partner)
        self.assertEqual(account.id, group_ap.id)

    def test_no_account_raises_validation_error(self):
        tenant = Tenant.objects.create(TenantID=111, CompanyName="No AP Tenant")
        Account.objects.filter(tenant=tenant).delete()
        partner = Partner.objects.create(
            tenant=tenant, name="Orphan Partner",
            partner_type="Supplier",
        )
        with self.assertRaises(Exception):
            _resolve_ap_account(partner)
