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

    def test_partner_without_link_gets_own_account_under_2101(self):
        """T-DEFACC: المورد بلا حساب مربوط يُنشأ له حسابه تحت «الدائنون».

        كان القيد يقع على 2101 نفسه (الأب العام) فيختلط كل الموردين في حساب
        واحد؛ صار يقع على حساب المورد الخاص وأبوه 2101.
        """
        account = _resolve_ap_account(self.partner_no_link)
        self.assertIsNotNone(account)
        self.assertNotEqual(account.id, self.ap_account.id)
        self.assertEqual(account.parent_id, self.ap_account.id)

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

    def test_group_partner_still_posts_to_its_own_account(self):
        """T-DEFACC: حساب ذمم المجموعة أبٌ لا وجهة — القيد على حساب المورد.

        كان تفريغ `linked_account` يُسقط القيد على حساب المجموعة العام؛ الآن
        يُعاد إنشاء حساب المورد تحت أبيه المعياري (2101) قبل الترحيل.
        """
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
        Partner.objects.filter(pk=partner.pk).update(linked_account=None)
        partner.refresh_from_db()

        account = _resolve_ap_account(partner)

        self.assertNotEqual(account.id, group_ap.id)
        self.assertEqual(account.parent_id, self.ap_account.id)

    def test_no_account_raises_validation_error(self):
        tenant = Tenant.objects.create(TenantID=111, CompanyName="No AP Tenant")
        Account.objects.filter(tenant=tenant).delete()
        partner = Partner.objects.create(
            tenant=tenant, name="Orphan Partner",
            partner_type="Supplier",
        )
        with self.assertRaises(Exception):
            _resolve_ap_account(partner)
