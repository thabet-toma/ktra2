"""مكتب المحاسبة — طبقة بيانات الممارسة: زبائن (أطراف)، برامج، مواعيد، إعدادات.

ISSUE #86: زبون المكتب صار `partners.Partner` داخل شركة مكتب المحاسب — الجدار
المحروس هنا صار: `PracticeProgram`/`PracticeTask`/`PracticeDocument` بلا
`tenant`، وصفّ مكتبٍ آخر (أو زبونٍ خارج شركة المكتب) «غير موجود» لا «ممنوع».
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    PracticeClient,
    PracticeDocument,
    PracticeProgram,
    PracticeSettings,
    PracticeTask,
)
from accountant_portal.practice import (
    MIGRATION_MARKER_TARGET_TYPE,
    archive_office_partner,
    create_office_partner,
    create_practice_document,
    create_practice_program,
    create_practice_task,
    get_office_client_view,
    get_office_partner,
    get_practice_settings,
    list_office_partners,
    office_tenant_id,
    practice_deadlines,
    program_payload,
    restore_office_partner,
    update_office_partner,
    update_practice_settings,
)
from accountant_portal.services import EngagementConflict
from partners.models import CustomerNote, Partner
from tenants.models import Tenant
from tenants.services import create_company


TODAY = date(2026, 8, 14)


def make_accountant(username, tax_number):
    user = User.objects.create_user(username, email=f"{username}@example.com")
    AccountantProfile.objects.create(
        user=user,
        professional_type="licensed_auditor",
        tax_registration_number=tax_number,
        business_address="رام الله",
        email_verified_at=timezone.now(),
    )
    return user


def make_office(username, tax_number):
    """محاسبٌ له مكتب فعلاً — نتيجة `migrate_accountant_offices` (ISSUE #55)."""
    user = make_accountant(username, tax_number)
    create_company(f"مكتب {username}", user)
    return user


class OfficeClientTest(TestCase):
    def setUp(self):
        self.office_a = make_office("office-a", "TAX-PRACTICE-A")
        self.office_b = make_office("office-b", "TAX-PRACTICE-B")
        self.client_a = create_office_partner(
            accountant=self.office_a,
            data={
                "trade_name": "مخبز النور",
                "phone": "0599",
                "email": "noor@example.com",
                "sector": "أغذية",
            },
        )

    # t1 — العزل: صفّ مكتبٍ آخر لا يُفرَّق عن المعدوم.
    def test_another_office_reading_a_client_gets_a_miss_not_a_forbidden(self):
        with self.assertRaises(EngagementConflict) as caught:
            get_office_partner(accountant=self.office_b, partner_id=self.client_a["id"])

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.code, "client_not_found")
        self.assertNotEqual(caught.exception.status_code, 403)

    def test_another_office_cannot_edit_this_client(self):
        with self.assertRaises(EngagementConflict) as caught:
            update_office_partner(
                accountant=self.office_b, partner_id=self.client_a["id"], data={"phone": "0000"},
            )
        self.assertEqual(caught.exception.status_code, 404)
        partner = Partner.objects.get(pk=self.client_a["id"])
        self.assertEqual(partner.phone, "0599")

    def test_listing_returns_only_this_offices_clients(self):
        create_office_partner(accountant=self.office_b, data={"trade_name": "زبون مكتب آخر"})

        names = [item["trade_name"] for item in list_office_partners(accountant=self.office_a)]

        self.assertEqual(names, ["مخبز النور"])

    def test_client_lives_inside_the_offices_own_tenant(self):
        partner = Partner.objects.get(pk=self.client_a["id"])
        self.assertEqual(partner.tenant_id, office_tenant_id(self.office_a))
        self.assertEqual(partner.partner_type, "Customer")

    def test_the_same_trade_name_is_accepted_in_two_offices(self):
        # الفضاء الاسمي لكل شركة على حِدة — Partner لا يفرض تفرّداً على الاسم.
        self.assertIsNotNone(
            create_office_partner(accountant=self.office_b, data={"trade_name": "مخبز النور"})["id"]
        )

    def test_invalid_email_is_refused_before_saving(self):
        with self.assertRaises(EngagementConflict) as caught:
            create_office_partner(
                accountant=self.office_a, data={"trade_name": "زبون", "email": "لا-بريد"},
            )

        self.assertEqual(caught.exception.code, "invalid_email")
        self.assertFalse(Partner.objects.filter(name="زبون").exists())

    def test_a_client_cannot_be_created_without_an_office(self):
        officeless = make_accountant("officeless", "TAX-NO-OFFICE")

        with self.assertRaises(EngagementConflict) as caught:
            create_office_partner(accountant=officeless, data={"trade_name": "زبون بلا مكتب"})

        self.assertEqual(caught.exception.code, "office_required")

    # الجدار: لا طريق من البرامج/المواعيد/المستندات إلى دفاتر شركة أخرى.
    def test_no_practice_model_carries_a_tenant_link(self):
        for model in (PracticeProgram, PracticeTask, PracticeDocument, PracticeSettings):
            leaks = [
                field.name
                for field in model._meta.get_fields()
                if field.is_relation and field.related_model is Tenant
            ]
            self.assertEqual(leaks, [], f"{model.__name__} يحمل رابطاً إلى شركة")


class PracticeEngagementLinkTest(TestCase):
    def setUp(self):
        self.office_a = make_office("link-a", "TAX-LINK-A")
        self.office_b = make_office("link-b", "TAX-LINK-B")
        self.tenant = Tenant.objects.create(CompanyName="شركة مرتبطة")
        self.other_tenant = Tenant.objects.create(CompanyName="شركة مكتب آخر")
        self.engagement_a = AccountantEngagement.objects.create(
            accountant=self.office_a,
            tenant=self.tenant,
            status="active",
            initiated_by="company",
        )
        self.engagement_b = AccountantEngagement.objects.create(
            accountant=self.office_b,
            tenant=self.other_tenant,
            status="active",
            initiated_by="company",
        )

    # t2 — ربط ارتباط مكتبٍ آخر مرفوض، وبنفس رسالة «غير موجود».
    def test_linking_another_offices_engagement_is_refused_as_a_miss(self):
        with self.assertRaises(EngagementConflict) as caught:
            create_office_partner(
                accountant=self.office_a,
                data={"trade_name": "زبون مربوط خطأً", "engagement_id": self.engagement_b.pk},
            )

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.code, "engagement_not_found")
        self.assertFalse(Partner.objects.filter(name="زبون مربوط خطأً").exists())

    def test_updating_a_client_cannot_steal_another_offices_engagement(self):
        client = create_office_partner(accountant=self.office_a, data={"trade_name": "زبون"})

        with self.assertRaises(EngagementConflict) as caught:
            update_office_partner(
                accountant=self.office_a,
                partner_id=client["id"],
                data={"engagement_id": self.engagement_b.pk},
            )

        self.assertEqual(caught.exception.status_code, 404)
        partner = Partner.objects.get(pk=client["id"])
        self.assertIsNone(partner.engagement_id)

    def test_linking_this_offices_engagement_exposes_the_company(self):
        client = create_office_partner(
            accountant=self.office_a,
            data={"trade_name": "زبون على المنصة", "engagement_id": self.engagement_a.pk},
        )

        self.assertEqual(client["engagement_id"], self.engagement_a.pk)
        self.assertEqual(client["tenant_id"], self.tenant.pk)

    def test_one_company_cannot_be_linked_to_two_clients_of_the_same_office(self):
        create_office_partner(
            accountant=self.office_a,
            data={"trade_name": "الزبون الأول", "engagement_id": self.engagement_a.pk},
        )

        with self.assertRaises(EngagementConflict) as caught:
            create_office_partner(
                accountant=self.office_a,
                data={"trade_name": "الزبون الثاني", "engagement_id": self.engagement_a.pk},
            )

        self.assertEqual(caught.exception.code, "engagement_linked")


class PracticeSettingsTest(TestCase):
    def setUp(self):
        self.office = make_accountant("settings-office", "TAX-SETTINGS")

    # t4 — الإعدادات تتجسّد كسولاً بقيمها الافتراضية.
    def test_settings_materialize_lazily_with_their_defaults(self):
        self.assertFalse(PracticeSettings.objects.exists())

        config = get_practice_settings(self.office)

        self.assertEqual(config.default_program_due_days, 15)
        self.assertEqual(
            config.service_types,
            ["ض.ق.م شهرية", "ضريبة دخل سنوية", "مراجعة سنوية", "رواتب"],
        )
        self.assertEqual(PracticeSettings.objects.count(), 1)
        # القراءة الثانية لا تُنشئ صفاً ثانياً.
        self.assertEqual(get_practice_settings(self.office).pk, config.pk)

    def test_a_user_without_a_professional_profile_is_refused(self):
        plain = User.objects.create_user("plain-user")

        with self.assertRaises(EngagementConflict) as caught:
            get_practice_settings(plain)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.code, "accountant_profile_required")

    def test_service_types_are_normalized_and_never_emptied(self):
        config = update_practice_settings(
            accountant=self.office,
            data={"service_types": ["تدقيق", " تدقيق ", "", "ضريبة دخل سنوية"], "default_program_due_days": 30},
        )

        self.assertEqual(config.service_types, ["تدقيق", "ضريبة دخل سنوية"])
        self.assertEqual(config.default_program_due_days, 30)
        with self.assertRaises(EngagementConflict):
            update_practice_settings(accountant=self.office, data={"service_types": []})
        with self.assertRaises(EngagementConflict):
            update_practice_settings(accountant=self.office, data={"default_program_due_days": 0})


class PracticeProgramAndAgendaTest(TestCase):
    def setUp(self):
        self.office = make_office("agenda-office", "TAX-AGENDA")
        self.other = make_office("agenda-other", "TAX-AGENDA-2")
        self.client_row = create_office_partner(
            accountant=self.office, data={"trade_name": "معرض السلام"},
        )

    def test_a_program_without_a_due_date_takes_the_office_default_window(self):
        program = create_practice_program(
            accountant=self.office,
            data={"partner_id": self.client_row["id"], "service_type": "ض.ق.م شهرية"},
            today=TODAY,
        )

        self.assertEqual(program.due_date, TODAY + timedelta(days=15))
        self.assertEqual(program.status, "planned")
        self.assertEqual(program.frequency, "monthly")

    def test_an_unknown_service_type_is_refused_until_it_is_configured(self):
        with self.assertRaises(EngagementConflict) as caught:
            create_practice_program(
                accountant=self.office,
                data={"partner_id": self.client_row["id"], "service_type": "خدمة لم تُعرَّف"},
                today=TODAY,
            )
        self.assertEqual(caught.exception.code, "unknown_service_type")

        update_practice_settings(
            accountant=self.office, data={"service_types": ["خدمة لم تُعرَّف"]},
        )
        self.assertIsNotNone(
            create_practice_program(
                accountant=self.office,
                data={"partner_id": self.client_row["id"], "service_type": "خدمة لم تُعرَّف"},
                today=TODAY,
            ).pk
        )

    def test_overdue_is_derived_from_today_and_never_stored(self):
        program = create_practice_program(
            accountant=self.office,
            data={
                "partner_id": self.client_row["id"],
                "service_type": "رواتب",
                "due_date": "2026-08-01",
            },
            today=TODAY,
        )

        self.assertNotIn("overdue", [choice for choice, _ in PracticeProgram.STATUSES])
        self.assertTrue(program_payload(program, TODAY)["is_overdue"])
        program.status = "done"
        self.assertFalse(program_payload(program, TODAY)["is_overdue"])

    def test_a_program_cannot_be_attached_to_another_offices_client(self):
        with self.assertRaises(EngagementConflict) as caught:
            create_practice_program(
                accountant=self.other,
                data={"partner_id": self.client_row["id"], "service_type": "رواتب"},
                today=TODAY,
            )

        self.assertEqual(caught.exception.status_code, 404)

    def test_documents_stay_inside_the_office_and_match_their_client(self):
        program = create_practice_program(
            accountant=self.office,
            data={"partner_id": self.client_row["id"], "service_type": "رواتب"},
            today=TODAY,
        )
        other_client = create_office_partner(
            accountant=self.office, data={"trade_name": "زبون آخر"},
        )

        document = create_practice_document(
            accountant=self.office,
            data={
                "partner_id": self.client_row["id"],
                "program_id": program.pk,
                "name": "كشف رواتب",
                "url": "https://files.example/x.pdf",
            },
        )

        self.assertEqual(document.program_id, program.pk)
        with self.assertRaises(EngagementConflict) as caught:
            create_practice_document(
                accountant=self.office,
                data={
                    "partner_id": other_client["id"],
                    "program_id": program.pk,
                    "name": "ملف",
                    "url": "https://files.example/y.pdf",
                },
            )
        self.assertEqual(caught.exception.status_code, 404)

    def test_deadlines_merge_programs_tasks_and_the_platform_filing_dates(self):
        tenant = Tenant.objects.create(CompanyName="شركة على المنصة")
        AccountantEngagement.objects.create(
            accountant=self.office, tenant=tenant, status="active", initiated_by="company",
        )
        create_practice_program(
            accountant=self.office,
            data={
                "partner_id": self.client_row["id"],
                "service_type": "ض.ق.م شهرية",
                "due_date": "2026-08-10",
            },
            today=TODAY,
        )
        create_practice_task(
            accountant=self.office,
            data={
                "partner_id": self.client_row["id"],
                "title": "زيارة الزبون",
                "due_at": "2026-08-18",
                "kind": "appointment",
            },
        )
        done = create_practice_program(
            accountant=self.office,
            data={
                "partner_id": self.client_row["id"],
                "service_type": "رواتب",
                "due_date": "2026-08-02",
                "status": "done",
            },
            today=TODAY,
        )

        agenda = practice_deadlines(accountant=self.office, today=TODAY)

        kinds = [item["kind"] for item in agenda["items"]]
        self.assertEqual(kinds, ["program", "appointment", "filing"])
        self.assertEqual(agenda["items"][0]["days_left"], -4)
        self.assertTrue(agenda["items"][0]["is_overdue"])
        self.assertEqual(agenda["items"][2]["tenant_id"], tenant.pk)
        self.assertEqual(agenda["totals"]["overdue"], 1)
        self.assertEqual(agenda["totals"]["due_soon"], 1)
        # المنجز لا يبقى في الأجندة.
        self.assertNotIn(done.pk, [item["id"] for item in agenda["items"] if item["kind"] == "program"])

    def test_the_agenda_never_shows_another_offices_rows(self):
        create_practice_program(
            accountant=self.office,
            data={"partner_id": self.client_row["id"], "service_type": "رواتب"},
            today=TODAY,
        )

        agenda = practice_deadlines(accountant=self.other, today=TODAY)

        self.assertEqual(agenda["items"], [])
        self.assertEqual(agenda["totals"]["count"], 0)

    def test_a_task_may_stand_alone_without_any_client(self):
        task = create_practice_task(
            accountant=self.office,
            data={"title": "اجتماع الفريق", "due_at": "2026-08-20T09:30:00", "kind": "deadline"},
        )

        self.assertIsNone(task.partner_id)
        self.assertEqual(PracticeTask.objects.filter(accountant=self.office).count(), 1)


class PracticeClientArchiveTest(TestCase):
    """مراجعة 2 من ISSUE #86: الأرشفة عادت — حالة طبقة المكتب
    (`PracticeClientArchive`) لا الطرف (`Partner` بلا مفهوم أرشفة)."""

    def setUp(self):
        self.office = make_office("archive-office", "TAX-ARCHIVE")
        self.client_a = create_office_partner(accountant=self.office, data={"trade_name": "مخبز الأمل"})

    def test_deleting_a_client_archives_it_and_keeps_its_programs(self):
        create_practice_program(
            accountant=self.office,
            data={"partner_id": self.client_a["id"], "service_type": "رواتب"},
            today=TODAY,
        )

        archived = archive_office_partner(accountant=self.office, partner_id=self.client_a["id"])

        self.assertEqual(archived["status"], "archived")
        # الطرف نفسه لم يُمسّ — لا حذف ولا تعطيل، فهو يبقى فاعلاً لفواتير الأتعاب.
        self.assertTrue(Partner.objects.filter(pk=self.client_a["id"]).exists())
        self.assertEqual(
            PracticeProgram.objects.filter(partner_id=self.client_a["id"]).count(), 1,
        )
        self.assertEqual(
            [row["id"] for row in list_office_partners(accountant=self.office, status="active")], [],
        )

        restored = restore_office_partner(accountant=self.office, partner_id=self.client_a["id"])
        self.assertEqual(restored["status"], "active")
        self.assertEqual(
            [row["id"] for row in list_office_partners(accountant=self.office, status="active")],
            [self.client_a["id"]],
        )

    def test_another_office_cannot_archive_or_restore_this_client(self):
        other = make_office("archive-other", "TAX-ARCHIVE-OTHER")

        for call in (
            lambda: archive_office_partner(accountant=other, partner_id=self.client_a["id"]),
            lambda: restore_office_partner(accountant=other, partner_id=self.client_a["id"]),
        ):
            with self.assertRaises(EngagementConflict) as caught:
                call()
            self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(
            [row["status"] for row in list_office_partners(accountant=self.office)], ["active"],
        )


class PracticeClientProfileFieldsTest(TestCase):
    """مراجعة 2 من ISSUE #86: جهة الاتصال والملاحظات عادتا — بلا حقلٍ بنيويّ
    جديد على `Partner` (سِجلٌّ جانبيّ محدَّثٌ في مكانه، `PROFILE_NOTE_TARGET_TYPE`)."""

    def setUp(self):
        self.office = make_office("profile-office", "TAX-PROFILE")

    def test_contact_and_notes_round_trip_through_create_list_and_update(self):
        client = create_office_partner(
            accountant=self.office,
            data={
                "trade_name": "زبون",
                "contact_first": "سامي",
                "contact_last": "خالد",
                "notes": "يفضّل الاتصال مساءً",
            },
        )
        self.assertEqual(client["contact_first"], "سامي")
        self.assertEqual(client["contact_last"], "خالد")
        self.assertEqual(client["notes"], "يفضّل الاتصال مساءً")

        listed = list_office_partners(accountant=self.office)
        self.assertEqual(listed[0]["contact_first"], "سامي")
        self.assertEqual(listed[0]["notes"], "يفضّل الاتصال مساءً")

        updated = update_office_partner(
            accountant=self.office, partner_id=client["id"], data={"notes": "غيّر رقمه"},
        )
        self.assertEqual(updated["notes"], "غيّر رقمه")
        # الحقول التي لم تُرسَل في هذا التحديث لا تُمسَح.
        self.assertEqual(updated["contact_first"], "سامي")

    def test_a_client_with_no_profile_note_yet_returns_empty_strings_not_an_error(self):
        client = create_office_partner(accountant=self.office, data={"trade_name": "زبون بلا ملاحظات"})

        self.assertEqual(client["contact_first"], "")
        self.assertEqual(client["notes"], "")


class LegacyClientFallbackTest(TestCase):
    """مراجعة 2 من ISSUE #86 — القيد المنصوص: «محاسبٌ تعثّر ترحيله يبقى على
    سطحه القديم — لا يُحذف شيء قبل نجاح النقل». القراءة تسقط إلى `PracticeClient`
    لكل زبونٍ لم يُرحَّل بعد؛ الكتابة تبقى حصراً على `Partner`.
    """

    def setUp(self):
        self.unmigrated = make_office("legacy-unmigrated", "TAX-LEGACY-UNMIGRATED")
        self.legacy_client = PracticeClient.objects.create(
            accountant=self.unmigrated, trade_name="زبونٌ قديم",
            contact_first="سامي", notes="ملاحظة قديمة",
        )
        self.migrated = make_office("legacy-migrated", "TAX-LEGACY-MIGRATED")
        self.migrated_partner = create_office_partner(
            accountant=self.migrated, data={"trade_name": "زبونٌ منقول"},
        )

    def test_an_unmigrated_accountant_still_sees_their_old_clients(self):
        rows = list_office_partners(accountant=self.unmigrated)

        self.assertEqual([row["trade_name"] for row in rows], ["زبونٌ قديم"])
        self.assertTrue(rows[0]["legacy"])
        self.assertEqual(rows[0]["id"], -self.legacy_client.pk)

    def test_a_migrated_offices_roster_is_unaffected_by_another_offices_legacy_data(self):
        rows = list_office_partners(accountant=self.migrated)

        self.assertEqual([row["trade_name"] for row in rows], ["زبونٌ منقول"])
        self.assertFalse(rows[0]["legacy"])

    def test_migrating_this_specific_client_removes_it_from_the_legacy_fallback(self):
        tenant_id = office_tenant_id(self.unmigrated)
        partner = Partner.objects.create(tenant_id=tenant_id, partner_type="Customer", name="زبونٌ قديم")
        CustomerNote.objects.create(
            tenant_id=tenant_id, partner=partner,
            target_type=MIGRATION_MARKER_TARGET_TYPE, target_id=str(self.legacy_client.pk),
            title="م",
        )

        rows = list_office_partners(accountant=self.unmigrated)

        self.assertEqual([row["trade_name"] for row in rows], ["زبونٌ قديم"])
        self.assertFalse(rows[0]["legacy"])
        self.assertEqual(rows[0]["id"], partner.pk)

    def test_legacy_client_detail_is_readable_but_writes_are_refused(self):
        view = get_office_client_view(accountant=self.unmigrated, client_id=-self.legacy_client.pk)

        self.assertEqual(view["trade_name"], "زبونٌ قديم")
        self.assertEqual(view["contact_first"], "سامي")
        self.assertEqual(view["notes"], "ملاحظة قديمة")

        with self.assertRaises(EngagementConflict) as caught:
            update_office_partner(
                accountant=self.unmigrated, partner_id=-self.legacy_client.pk, data={"phone": "000"},
            )
        self.assertEqual(caught.exception.code, "client_not_found")
        # PracticeClient نفسه لم يُمَسّ — لا كتابة جديدة عليه أبداً.
        self.legacy_client.refresh_from_db()
        self.assertEqual(self.legacy_client.phone, "")

    def test_the_fallback_path_never_writes_to_practice_client(self):
        before = list(PracticeClient.objects.filter(pk=self.legacy_client.pk).values())[0]

        list_office_partners(accountant=self.unmigrated)
        get_office_client_view(accountant=self.unmigrated, client_id=-self.legacy_client.pk)

        after = list(PracticeClient.objects.filter(pk=self.legacy_client.pk).values())[0]
        self.assertEqual(before, after)

    def test_an_unknown_negative_id_is_a_miss_not_a_crash(self):
        with self.assertRaises(EngagementConflict) as caught:
            get_office_client_view(accountant=self.unmigrated, client_id=-999999)
        self.assertEqual(caught.exception.status_code, 404)
