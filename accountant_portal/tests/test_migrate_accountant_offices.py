# -*- coding: utf-8 -*-
"""ISSUE #55 — ترحيل المكتب: كل محاسبٍ مسجَّل يجد مكتبه وزبائنه وارتباطاته كما
تركها. الملاحظة على الأثر عند الـHTTP (صفوف موجودة، حالة الردّ) — لا استدعاء
الأمر داخلياً بمعزل عن أثره، ولا فحص شكل دالّة داخلية.

الأمر نفسه هو الواجهة المُختبَرة (مثل `import_jarabaa`): يُشغَّل عبر
`call_command`، ثم يُتحقَّق من أثره عبر نقاط HTTP قائمة فعلاً —
`/api/tenants/companies/my-companies/` و`/api/accountant/practice/dashboard/`
و`/api/accountant/practice/clients/` — لا عبر استدعاء دوالّه الداخلية.
"""
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APITestCase

from accountant_portal.models import AccountantEngagement, AccountantProfile, PracticeClient
from tenants.models import Tenant, UserCompanyMembership
from tenants.services import create_company

COMPANIES = "/api/tenants/companies/my-companies/"
DASHBOARD = "/api/accountant/practice/dashboard/"
CLIENTS = "/api/accountant/practice/clients/"
PASSWORD = "Migrate-Office-Pass-55"


def _accountant(username):
    user = User.objects.create_user(username, password=PASSWORD, email=f"{username}@example.com")
    AccountantProfile.objects.create(
        user=user, professional_type="licensed_auditor",
        tax_registration_number=f"TAX-{username}", business_address="رام الله",
    )
    return user


def _run_migration(dry_run=False):
    out = StringIO()
    call_command("migrate_accountant_offices", dry_run=dry_run, stdout=out)
    return out.getvalue()


class MigrateAccountantOfficesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # محاسبٌ بلا مكتب بعد — يجب أن يُنشأ له واحد بقالب accounting_firm.
        cls.fresh_accountant = _accountant("acct55-fresh")

        # محاسبٌ له مكتبٌ فعلاً — يجب ألا يُنشأ له مكتبٌ ثانٍ.
        cls.existing_accountant = _accountant("acct55-existing")
        cls.existing_office = create_company("مكتب قائم ٥٥", cls.existing_accountant)

        # زبونٌ يدويٌّ قديم بلا ربط — يجب أن يبقى كما هو (بلا managed_tenant وبلا engagement).
        cls.manual_client = PracticeClient.objects.create(
            accountant=cls.fresh_accountant, trade_name="زبونٌ قديم بلا ربط",
        )

        # مالكُ شركاتِ العملاء — ليس محاسباً، فلا تختلط عضويتُه بمكتب أيّ محاسب.
        cls.client_owner = User.objects.create_user(
            "acct55-client-owner", password=PASSWORD, email="acct55-owner@example.com",
        )

        # ارتباطٌ نشط بلا PracticeClient — يجب أن يصير زبوناً من نوع "مربوطٌ بإذنه".
        cls.client_tenant = create_company("شركة العميل ٥٥", cls.client_owner)
        cls.active_engagement = AccountantEngagement.objects.create(
            accountant=cls.fresh_accountant, tenant=cls.client_tenant,
            status="active", initiated_by="company",
        )

        # ارتباطٌ نشطٌ ثانٍ، لكن اسم زبونه اليدوي موجودٌ سلفاً بلا ربط — يجب أن
        # يُربط بالزبون اليدوي القائم لا أن يُكرَّر.
        cls.client_tenant_2 = create_company("شركة عميل مربوطة سلفاً ٥٥", cls.client_owner)
        cls.pre_named_client = PracticeClient.objects.create(
            accountant=cls.existing_accountant, trade_name="شركة عميل مربوطة سلفاً ٥٥",
        )
        cls.active_engagement_2 = AccountantEngagement.objects.create(
            accountant=cls.existing_accountant, tenant=cls.client_tenant_2,
            status="active", initiated_by="company",
        )

        # ارتباطٌ غير نشط — لا يجوز أن يصير زبوناً.
        cls.declined_tenant = create_company("شركة رفضت الارتباط ٥٥", cls.client_owner)
        cls.declined_engagement = AccountantEngagement.objects.create(
            accountant=cls.fresh_accountant, tenant=cls.declined_tenant,
            status="declined", initiated_by="company",
        )

    def _api_for(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_dry_run_writes_nothing(self):
        before_clients = PracticeClient.objects.count()
        before_offices = UserCompanyMembership.objects.filter(role="manager").count()
        _run_migration(dry_run=True)
        self.assertEqual(PracticeClient.objects.count(), before_clients)
        self.assertEqual(
            UserCompanyMembership.objects.filter(role="manager").count(), before_offices,
        )

    def test_fresh_accountant_gets_an_accounting_firm_office(self):
        _run_migration()
        api = self._api_for(self.fresh_accountant)
        res = api.get(COMPANIES)
        self.assertEqual(res.status_code, 200, res.content)
        offices = [row["tenant"] for row in res.json()]
        self.assertEqual(len(offices), 1)
        self.assertEqual(offices[0]["template"], "accounting_firm")

    def test_accountant_with_existing_office_is_not_duplicated(self):
        _run_migration()
        api = self._api_for(self.existing_accountant)
        res = api.get(COMPANIES)
        self.assertEqual(res.status_code, 200, res.content)
        tenant_ids = [row["tenant"]["TenantID"] for row in res.json()]
        # لا يظهر إلا المكتب القائم وحده — لا مكتب ثانٍ ولا دفتر العميل المُدار.
        self.assertEqual(tenant_ids, [self.existing_office.pk])

    def test_manual_practice_client_untouched(self):
        _run_migration()
        self.manual_client.refresh_from_db()
        self.assertIsNone(self.manual_client.engagement_id)
        self.assertIsNone(self.manual_client.managed_tenant_id)
        self.assertEqual(self.manual_client.client_type, "unlinked")

    def test_active_engagement_becomes_engaged_client_on_dashboard(self):
        _run_migration()
        api = self._api_for(self.fresh_accountant)
        res = api.get(DASHBOARD)
        self.assertEqual(res.status_code, 200, res.content)
        rows = {row["trade_name"]: row for row in res.json()["clients"]}
        self.assertIn("شركة العميل ٥٥", rows)
        self.assertEqual(rows["شركة العميل ٥٥"]["client_type"], "engaged")
        # الزبون اليدوي القديم يبقى ظاهراً بجانبه بلا تغيير في نوعه.
        self.assertEqual(rows["زبونٌ قديم بلا ربط"]["client_type"], "unlinked")
        # الارتباط المرفوض لا يصير زبوناً على الإطلاق.
        self.assertNotIn("شركة رفضت الارتباط ٥٥", rows)

    def test_active_engagement_links_to_existing_manually_named_client_not_duplicated(self):
        _run_migration()
        api = self._api_for(self.existing_accountant)
        res = api.get(CLIENTS)
        self.assertEqual(res.status_code, 200, res.content)
        matches = [
            row for row in res.json()["results"]
            if row["trade_name"] == "شركة عميل مربوطة سلفاً ٥٥"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["client_type"], "engaged")
        self.assertEqual(matches[0]["id"], self.pre_named_client.pk)

    def test_counts_before_after_lose_nothing_and_idempotent_rerun(self):
        active_before = AccountantEngagement.objects.filter(status="active").count()
        clients_before = PracticeClient.objects.count()

        _run_migration()
        active_after_first = AccountantEngagement.objects.filter(status="active").count()
        clients_after_first = PracticeClient.objects.count()
        self.assertEqual(active_after_first, active_before)
        self.assertGreaterEqual(clients_after_first, clients_before)

        # إعادة التشغيل idempotent — لا مضاعفة.
        _run_migration()
        self.assertEqual(
            AccountantEngagement.objects.filter(status="active").count(), active_after_first,
        )
        self.assertEqual(PracticeClient.objects.count(), clients_after_first)
        self.assertEqual(
            UserCompanyMembership.objects.filter(
                user=self.fresh_accountant, role="manager", tenant__managed_by__isnull=True,
            ).count(),
            1,
        )
