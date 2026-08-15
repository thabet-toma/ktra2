"""مكتب المحاسبة — طبقة بيانات الممارسة: زبائن يدويون، برامج، مواعيد، إعدادات.

الجدار المحروس هنا: زبون المكتب **سجلّ ممارسة لا دفترَ حسابات** — لا `tenant` في
أي نموذج، وصفّ مكتبٍ آخر «غير موجود» لا «ممنوع»، والحذف أرشفة.
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
    archive_practice_client,
    create_practice_client,
    create_practice_document,
    create_practice_program,
    create_practice_task,
    get_practice_client,
    get_practice_settings,
    list_practice_clients,
    practice_deadlines,
    program_payload,
    restore_practice_client,
    update_practice_client,
    update_practice_settings,
)
from accountant_portal.services import EngagementConflict
from tenants.models import Tenant


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


class PracticeClientTest(TestCase):
    def setUp(self):
        self.office_a = make_accountant("office-a", "TAX-PRACTICE-A")
        self.office_b = make_accountant("office-b", "TAX-PRACTICE-B")
        self.client_a = create_practice_client(
            accountant=self.office_a,
            data={
                "trade_name": "مخبز النور",
                "contact_first": "سامي",
                "phone": "0599",
                "email": "noor@example.com",
                "sector": "أغذية",
            },
        )

    # t1 — العزل: صفّ مكتبٍ آخر لا يُفرَّق عن المعدوم.
    def test_another_office_reading_a_client_gets_a_miss_not_a_forbidden(self):
        with self.assertRaises(EngagementConflict) as caught:
            get_practice_client(accountant=self.office_b, client_id=self.client_a.pk)

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.code, "client_not_found")
        self.assertNotEqual(caught.exception.status_code, 403)

    def test_another_office_cannot_edit_or_archive_this_client(self):
        for call in (
            lambda: update_practice_client(
                accountant=self.office_b, client_id=self.client_a.pk, data={"phone": "0000"},
            ),
            lambda: archive_practice_client(accountant=self.office_b, client_id=self.client_a.pk),
        ):
            with self.assertRaises(EngagementConflict) as caught:
                call()
            self.assertEqual(caught.exception.status_code, 404)
        self.client_a.refresh_from_db()
        self.assertEqual(self.client_a.phone, "0599")
        self.assertEqual(self.client_a.status, "active")

    def test_listing_returns_only_this_offices_clients(self):
        create_practice_client(accountant=self.office_b, data={"trade_name": "زبون مكتب آخر"})

        names = [item.trade_name for item in list_practice_clients(accountant=self.office_a)]

        self.assertEqual(names, ["مخبز النور"])

    def test_trade_name_is_required_and_unique_inside_one_office(self):
        with self.assertRaises(EngagementConflict) as missing:
            create_practice_client(accountant=self.office_a, data={"trade_name": "   "})
        with self.assertRaises(EngagementConflict) as duplicate:
            create_practice_client(accountant=self.office_a, data={"trade_name": "مخبز النور"})

        self.assertEqual(missing.exception.status_code, 400)
        self.assertEqual(duplicate.exception.code, "duplicate_client")
        # نفس الاسم في مكتب آخر مقبول — الفضاء الاسمي لكل مكتب.
        self.assertIsNotNone(
            create_practice_client(accountant=self.office_b, data={"trade_name": "مخبز النور"}).pk
        )

    def test_invalid_email_is_refused_before_saving(self):
        with self.assertRaises(EngagementConflict) as caught:
            create_practice_client(
                accountant=self.office_a, data={"trade_name": "زبون", "email": "لا-بريد"},
            )

        self.assertEqual(caught.exception.code, "invalid_email")
        self.assertFalse(PracticeClient.objects.filter(trade_name="زبون").exists())

    # t3 — الحذف أرشفة، لا إتلاف.
    def test_deleting_a_client_archives_the_row_and_keeps_its_history(self):
        create_practice_program(
            accountant=self.office_a,
            data={"client_id": self.client_a.pk, "service_type": "رواتب"},
            today=TODAY,
        )

        archived = archive_practice_client(accountant=self.office_a, client_id=self.client_a.pk)

        self.assertEqual(archived.status, "archived")
        self.assertTrue(PracticeClient.objects.filter(pk=self.client_a.pk).exists())
        self.assertEqual(PracticeProgram.objects.filter(client=self.client_a).count(), 1)
        self.assertEqual(
            [item.pk for item in list_practice_clients(accountant=self.office_a, status="active")],
            [],
        )
        self.assertEqual(
            restore_practice_client(accountant=self.office_a, client_id=self.client_a.pk).status,
            "active",
        )

    # الجدار: لا طريق من سجلّ الممارسة إلى دفاتر شركة.
    def test_no_practice_model_carries_a_tenant_link(self):
        for model in (
            PracticeClient,
            PracticeProgram,
            PracticeTask,
            PracticeDocument,
            PracticeSettings,
        ):
            leaks = [
                field.name
                for field in model._meta.get_fields()
                if field.is_relation and field.related_model is Tenant
            ]
            self.assertEqual(leaks, [], f"{model.__name__} يحمل رابطاً إلى شركة")


class PracticeEngagementLinkTest(TestCase):
    def setUp(self):
        self.office_a = make_accountant("link-a", "TAX-LINK-A")
        self.office_b = make_accountant("link-b", "TAX-LINK-B")
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
            create_practice_client(
                accountant=self.office_a,
                data={"trade_name": "زبون مربوط خطأً", "engagement_id": self.engagement_b.pk},
            )

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.code, "engagement_not_found")
        self.assertFalse(PracticeClient.objects.filter(trade_name="زبون مربوط خطأً").exists())

    def test_updating_a_client_cannot_steal_another_offices_engagement(self):
        client = create_practice_client(accountant=self.office_a, data={"trade_name": "زبون"})

        with self.assertRaises(EngagementConflict) as caught:
            update_practice_client(
                accountant=self.office_a,
                client_id=client.pk,
                data={"engagement_id": self.engagement_b.pk},
            )

        self.assertEqual(caught.exception.status_code, 404)
        client.refresh_from_db()
        self.assertIsNone(client.engagement_id)

    def test_linking_this_offices_engagement_exposes_the_company(self):
        client = create_practice_client(
            accountant=self.office_a,
            data={"trade_name": "زبون على المنصة", "engagement_id": self.engagement_a.pk},
        )

        self.assertEqual(client.engagement_id, self.engagement_a.pk)
        self.assertEqual(client.engagement.tenant_id, self.tenant.pk)

    def test_one_company_cannot_be_linked_to_two_clients_of_the_same_office(self):
        create_practice_client(
            accountant=self.office_a,
            data={"trade_name": "الزبون الأول", "engagement_id": self.engagement_a.pk},
        )

        with self.assertRaises(EngagementConflict) as caught:
            create_practice_client(
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
        self.office = make_accountant("agenda-office", "TAX-AGENDA")
        self.other = make_accountant("agenda-other", "TAX-AGENDA-2")
        self.client_row = create_practice_client(
            accountant=self.office, data={"trade_name": "معرض السلام"},
        )

    def test_a_program_without_a_due_date_takes_the_office_default_window(self):
        program = create_practice_program(
            accountant=self.office,
            data={"client_id": self.client_row.pk, "service_type": "ض.ق.م شهرية"},
            today=TODAY,
        )

        self.assertEqual(program.due_date, TODAY + timedelta(days=15))
        self.assertEqual(program.status, "planned")
        self.assertEqual(program.frequency, "monthly")

    def test_an_unknown_service_type_is_refused_until_it_is_configured(self):
        with self.assertRaises(EngagementConflict) as caught:
            create_practice_program(
                accountant=self.office,
                data={"client_id": self.client_row.pk, "service_type": "خدمة لم تُعرَّف"},
                today=TODAY,
            )
        self.assertEqual(caught.exception.code, "unknown_service_type")

        update_practice_settings(
            accountant=self.office, data={"service_types": ["خدمة لم تُعرَّف"]},
        )
        self.assertIsNotNone(
            create_practice_program(
                accountant=self.office,
                data={"client_id": self.client_row.pk, "service_type": "خدمة لم تُعرَّف"},
                today=TODAY,
            ).pk
        )

    def test_overdue_is_derived_from_today_and_never_stored(self):
        program = create_practice_program(
            accountant=self.office,
            data={
                "client_id": self.client_row.pk,
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
                data={"client_id": self.client_row.pk, "service_type": "رواتب"},
                today=TODAY,
            )

        self.assertEqual(caught.exception.status_code, 404)

    def test_documents_stay_inside_the_office_and_match_their_client(self):
        program = create_practice_program(
            accountant=self.office,
            data={"client_id": self.client_row.pk, "service_type": "رواتب"},
            today=TODAY,
        )
        other_client = create_practice_client(
            accountant=self.office, data={"trade_name": "زبون آخر"},
        )

        document = create_practice_document(
            accountant=self.office,
            data={
                "client_id": self.client_row.pk,
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
                    "client_id": other_client.pk,
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
                "client_id": self.client_row.pk,
                "service_type": "ض.ق.م شهرية",
                "due_date": "2026-08-10",
            },
            today=TODAY,
        )
        create_practice_task(
            accountant=self.office,
            data={
                "client_id": self.client_row.pk,
                "title": "زيارة الزبون",
                "due_at": "2026-08-18",
                "kind": "appointment",
            },
        )
        done = create_practice_program(
            accountant=self.office,
            data={
                "client_id": self.client_row.pk,
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
            data={"client_id": self.client_row.pk, "service_type": "رواتب"},
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

        self.assertIsNone(task.client_id)
        self.assertEqual(PracticeTask.objects.filter(accountant=self.office).count(), 1)
