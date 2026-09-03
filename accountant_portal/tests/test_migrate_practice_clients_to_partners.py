# -*- coding: utf-8 -*-
"""ISSUE #86 — أمر الترحيل: `PracticeClient` → `partners.Partner` داخل شركة
مكتب المحاسب. مثل `test_migrate_accountant_offices.py`: الأمر نفسه هو الواجهة
المُختبَرة، والأثر يُتحقَّق منه فوق البيانات مباشرةً (لا استدعاء دوالّه الداخلية).
"""
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    PracticeClient,
    PracticeDocument,
    PracticeProgram,
    PracticeTask,
)
from partners.models import CustomerNote, Partner
from tenants.models import Tenant
from tenants.services import create_company

PASSWORD = "Migrate-Practice-Clients-86"


def _accountant(username):
    user = User.objects.create_user(username, password=PASSWORD, email=f"{username}@example.com")
    AccountantProfile.objects.create(
        user=user, professional_type="licensed_auditor",
        tax_registration_number=f"TAX-{username}", business_address="رام الله",
    )
    return user


def _run(dry_run=False):
    out = StringIO()
    call_command("migrate_practice_clients_to_partners", dry_run=dry_run, stdout=out)
    return out.getvalue()


class MigratePracticeClientsToPartnersTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.accountant = _accountant("acct86-office")
        cls.office = create_company("مكتب ٨٦", cls.accountant)

        cls.plain_client = PracticeClient.objects.create(
            accountant=cls.accountant,
            trade_name="مخبز النور",
            contact_first="سامي",
            contact_last="أحمد",
            phone="0599000000000000000000000",  # أطول من عمود Partner.phone عمداً
            mobile="0599111111",
            email="noor@example.com",
            address="رام الله",
            sector="أغذية",
            tax_number="TAX-NOOR",
            notes="زبونٌ قديم — حذرٌ في التحصيل.",
        )
        program = PracticeProgram.objects.create(
            accountant=cls.accountant, client=cls.plain_client, service_type="رواتب",
        )
        PracticeTask.objects.create(
            accountant=cls.accountant, client=cls.plain_client, title="زيارة",
            due_at="2026-09-05T09:00:00Z",
        )
        PracticeDocument.objects.create(
            accountant=cls.accountant, client=cls.plain_client, program=program,
            name="كشف", url="https://files.example/x.pdf",
        )

        cls.other_tenant = Tenant.objects.create(CompanyName="شركة مرتبطة ٨٦")
        cls.engagement = AccountantEngagement.objects.create(
            accountant=cls.accountant, tenant=cls.other_tenant,
            status="active", initiated_by="company",
        )
        cls.linked_client = PracticeClient.objects.create(
            accountant=cls.accountant, trade_name="شركة مرتبطة ٨٦", engagement=cls.engagement,
        )

        # محاسبٌ بلا مكتب بعد (لم يُرحَّل ISSUE #55) — يبقى بلا مساس.
        cls.officeless_accountant = _accountant("acct86-no-office")
        cls.officeless_client = PracticeClient.objects.create(
            accountant=cls.officeless_accountant, trade_name="زبونٌ بلا مكتب",
        )

    def test_dry_run_writes_nothing(self):
        before_partners = Partner.objects.count()
        before_notes = CustomerNote.objects.count()

        _run(dry_run=True)

        self.assertEqual(Partner.objects.count(), before_partners)
        self.assertEqual(CustomerNote.objects.count(), before_notes)

    def test_a_client_is_migrated_into_a_partner_inside_the_office_tenant(self):
        _run()

        partner = Partner.objects.get(tenant=self.office, name="مخبز النور")
        self.assertEqual(partner.partner_type, "Customer")
        self.assertEqual(partner.mobile, "0599111111")
        self.assertEqual(partner.email, "noor@example.com")
        self.assertEqual(partner.sector, "أغذية")
        self.assertEqual(partner.tax_number, "TAX-NOOR")
        # الحقل الأضيق قُصَّ لا سقط بصمت (Partner.phone أضيق من PracticeClient.phone).
        self.assertEqual(len(partner.phone), Partner._meta.get_field("phone").max_length)
        self.assertEqual(partner.client_type, "unlinked")

    def test_the_contact_name_and_notes_survive_inside_a_customer_note(self):
        _run()

        partner = Partner.objects.get(tenant=self.office, name="مخبز النور")
        marker = CustomerNote.objects.get(
            tenant=self.office, target_type="practice_client_migration",
            target_id=str(self.plain_client.pk),
        )
        self.assertEqual(marker.partner_id, partner.pk)
        self.assertIn("سامي أحمد", marker.body)
        self.assertIn("حذرٌ في التحصيل", marker.body)

    def test_the_contact_name_and_notes_are_also_readable_through_the_live_profile(self):
        """مراجعة 2 من ISSUE #86: بجانب النصّ التاريخي أعلاه، طرفٌ مُرحَّلٌ يجب
        أن يظهر بجهة اتصاله وملاحظاته في `list_office_partners` كأي زبونٍ حيّ."""
        from accountant_portal.practice import list_office_partners

        _run()

        rows = {row["trade_name"]: row for row in list_office_partners(accountant=self.accountant)}
        self.assertEqual(rows["مخبز النور"]["contact_first"], "سامي")
        self.assertEqual(rows["مخبز النور"]["contact_last"], "أحمد")
        self.assertEqual(rows["مخبز النور"]["notes"], "زبونٌ قديم — حذرٌ في التحصيل.")
        self.assertFalse(rows["مخبز النور"]["legacy"])

    def test_engagement_and_managed_tenant_travel_with_the_client(self):
        _run()

        partner = Partner.objects.get(tenant=self.office, name="شركة مرتبطة ٨٦")
        self.assertEqual(partner.engagement_id, self.engagement.pk)
        self.assertEqual(partner.client_type, "engaged")

    def test_child_rows_are_relinked_to_the_new_partner_and_the_legacy_client_is_untouched(self):
        _run()

        partner = Partner.objects.get(tenant=self.office, name="مخبز النور")
        program = PracticeProgram.objects.get(accountant=self.accountant, client=self.plain_client)
        task = PracticeTask.objects.get(accountant=self.accountant, client=self.plain_client)
        document = PracticeDocument.objects.get(accountant=self.accountant, client=self.plain_client)

        self.assertEqual(program.partner_id, partner.pk)
        self.assertEqual(task.partner_id, partner.pk)
        self.assertEqual(document.partner_id, partner.pk)
        # الصفّ الأصلي بلا مساس — لا حذف ولا تعديل.
        self.plain_client.refresh_from_db()
        self.assertEqual(self.plain_client.trade_name, "مخبز النور")
        self.assertEqual(program.client_id, self.plain_client.pk)

    def test_an_accountant_without_an_office_yet_is_skipped_not_broken(self):
        _run()

        self.assertFalse(
            Partner.objects.filter(name="زبونٌ بلا مكتب").exists()
        )
        self.officeless_client.refresh_from_db()  # لم يُحذف ولم يُغيَّر

    def test_rerunning_is_idempotent(self):
        _run()
        partners_after_first = Partner.objects.count()
        notes_after_first = CustomerNote.objects.count()

        _run()

        self.assertEqual(Partner.objects.count(), partners_after_first)
        self.assertEqual(CustomerNote.objects.count(), notes_after_first)

    def test_rerunning_backfills_children_added_after_the_first_pass(self):
        _run()
        partner = Partner.objects.get(tenant=self.office, name="مخبز النور")
        late_task = PracticeTask.objects.create(
            accountant=self.accountant, client=self.plain_client, title="متأخّرة",
            due_at="2026-10-01T09:00:00Z",
        )

        _run()

        late_task.refresh_from_db()
        self.assertEqual(late_task.partner_id, partner.pk)
