"""نقاطُ #277 — تعديل اللائحة والتمديد والتزامات المكتب والأحداث.

**ما يثبته هذا الملف:**

1. **`GET deadline-rules/` لا يُكسر**: مفاتيحُه القائمة تبقى، وتُضاف `platform`
   و`override` و`history` لكل سطر.
2. **الكتابةُ بمفتاحها**: `office.settings.manage` لتعديل اللائحة والتزامات
   المكتب، و`office.clients.write` للأحداث والتمديد — والمحاسبُ لا يملك الأول.
3. **العزل**: مكتبٌ آخر 404، وزبونٌ لا يراه العضو 404، وبلا المفتاح 403.
4. **الحرّاس**: `DELETE custom-rules/<id>/` ⇒ 405، وتعديلُ سطرٍ برمزٍ مجهول ⇒ 400.
5. **الجرس** يحمل `opens`: «deadline_rules» لنوعَي اللائحة و«client» لغيرهما.
"""
import datetime
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting_office import services
from accounting_office.models import (
    EVENT_KIND_WITHHOLDING,
    FREQUENCY_MONTHLY,
    Obligation,
    OfficeClient,
    OfficeCustomRule,
    TaxCard,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
RULES = f"{BASE}deadline-rules/"
CUSTOM_RULES = f"{BASE}custom-rules/"
CLIENTS = f"{BASE}clients/"
OBLIGATIONS = f"{BASE}obligations/"
ALERTS = f"{BASE}alerts/"

JAN_START = datetime.date(2026, 1, 1)
EVENT_DAY = datetime.date(2026, 2, 10)


class OverridesApiTestCase(APITestCase):
    """مكتبٌ إسرائيليٌّ: صاحبُه، ومحاسبٌ بزبونه، ومكتبٌ ثانٍ للعزل."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="so_owner", password="x")
        cls.tenant = create_company(
            "مكتب التعديلات", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.accountant = member("so_accountant", "accountant")
        cls.colleague = member("so_colleague", "accountant")
        cls.manager = member("so_manager", "office_manager")

        def make(name, responsible, **fields):
            client = OfficeClient.objects.create(
                tenant=cls.tenant, name=name, responsible=responsible,
            )
            TaxCard.objects.create(
                client=client,
                annual_sales=Decimal("0"),
                vat_classification=fields.pop("vat_classification", "authorized"),
            )
            return client

        cls.mine = make("زبون المحاسب", cls.accountant)
        cls.other = make("زبون الزميل", cls.colleague)
        for client in (cls.mine, cls.other):
            services.add_client_service(
                client=client, service=cls.catalog["vat"],
                starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
            )

        cls.outside_owner = User.objects.create_user(username="so_outside", password="x")
        cls.outside = create_company(
            "مكتب التعديلات الآخر", cls.outside_owner, template="accounting_office",
        )
        invalidate_module_cache(cls.outside.pk)
        ready_office(cls.outside, "IL")
        catalog(cls.outside)
        outside_client = OfficeClient.objects.create(
            tenant=cls.outside, name="زبون المكتب الآخر", responsible=cls.outside_owner,
        )
        TaxCard.objects.create(
            client=outside_client, annual_sales=Decimal("0"),
            vat_classification="authorized",
        )
        services.add_client_service(
            client=outside_client, service=services.service_by_code(cls.outside, "vat"),
            starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
        )
        cls.outside_client = outside_client

    def setUp(self):
        # «اليوم» الذي تقرؤه الـviews صريحٌ: زرعُ الالتزامات لا يعتمد على ساعة.
        self.day = datetime.date(2026, 4, 1)
        from unittest import mock

        patcher = mock.patch(
            "accounting_office.views.timezone.localdate", return_value=self.day,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def override(self, user=None, **payload):
        self.as_user(user or self.owner)
        body = {"system": "IL", "code": "il_vat_periodic", **payload}
        return self.client.post(
            f"{RULES}override/", body, format="json", **self.headers(),
        )

    def custom_rule_payload(self, **kwargs):
        body = {
            "name": "تقرير داخلي",
            "service": self.catalog["bookkeeping"].pk,
            "cadence": FREQUENCY_MONTHLY,
            "rule_kind": "day_of_next_month",
            "rule_day": 10,
        }
        body.update(kwargs)
        return body


class DeadlineRulesApiTest(OverridesApiTestCase):
    def test_the_listing_keeps_its_old_keys_and_adds_the_office_ones(self):
        self.as_user(self.owner)
        res = self.client.get(RULES, {"system": "IL"}, **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        rows = res.data["rules"]
        self.assertTrue(rows)
        for key in (
            "code", "name", "service_code", "is_generated", "needs_review",
            "year", "version", "source_url",
        ):
            self.assertIn(key, rows[0], key)
        for key in ("platform", "override", "history"):
            self.assertIn(key, rows[0], key)
        self.assertIsNone(rows[0]["override"])
        self.assertEqual(rows[0]["history"], [])
        self.assertEqual(
            set(rows[0]["platform"]),
            {
                "rule_kind", "rule_day", "rule_month",
                "electronic_extension_days", "rule_kind_label",
            },
        )

    def test_overriding_a_line_requires_the_settings_key(self):
        self.as_user(self.accountant)
        res = self.client.post(
            f"{RULES}override/",
            {"system": "IL", "code": "il_vat_periodic", "rule_day": 20},
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)

    def test_the_owner_overrides_and_the_listing_shows_platform_and_history(self):
        first = self.override(rule_day=20, note="أول")
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.data["changed_obligations"], 0)
        self.override(rule_day=22, note="ثانٍ")

        rows = self.client.get(RULES, {"system": "IL"}, **self.headers()).data["rules"]
        row = next(item for item in rows if item["code"] == "il_vat_periodic")
        self.assertEqual(row["override"]["rule_day"], 22)
        self.assertEqual(row["platform"]["rule_day"], 15)
        self.assertEqual(len(row["history"]), 2)
        self.assertEqual(row["history"][0]["note"], "ثانٍ")
        self.assertEqual(row["history"][0]["rule_day"], 22)
        # «مَن وإمتى» يُرسَلان في السجلّ لا في القاعدة فقط.
        self.assertEqual(row["history"][0]["created_by_name"], "so_owner")
        self.assertIsNotNone(row["history"][0]["created_at"])

    def test_keep_and_clear_override_are_idempotent_endpoints(self):
        # التزاماتٌ حقيقيّة: «لم يتغيّر شيء» في النداء الثاني قيمةٌ تستطيع أن تسقط.
        services.refresh_office(self.tenant, day=self.day)
        self.assertGreater(
            self.override(rule_day=22, note="تأجيل المكتب").data["changed_obligations"], 0,
        )
        self.as_user(self.owner)

        def post(path):
            return self.client.post(
                f"{RULES}{path}",
                {"system": "IL", "code": "il_vat_periodic"},
                format="json",
                **self.headers(),
            )

        for _ in range(2):
            kept = post("keep-override/")
            self.assertEqual(kept.status_code, 200, kept.content)
            self.assertEqual(kept.data["changed_obligations"], 0)
            self.assertEqual(kept.data["override"]["rule_day"], 22)
        active = services.active_rule_overrides(self.tenant)[("IL", "il_vat_periodic")]
        self.assertEqual(active.rule_day, 22)

        cleared = post("clear-override/")
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertGreater(cleared.data["changed_obligations"], 0)
        self.assertEqual(services.active_rule_overrides(self.tenant), {})

        again = post("clear-override/")
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.data["changed_obligations"], 0)
        self.assertEqual(services.active_rule_overrides(self.tenant), {})

    def test_an_unknown_code_is_a_four_hundred(self):
        res = self.override(code="no_such_rule", rule_day=20)

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("code", res.content.decode())

    def test_a_manager_with_the_settings_key_passes(self):
        res = self.override(user=self.manager, rule_day=19, note="من مدير المكتب")

        self.assertEqual(res.status_code, 200, res.content)

    def test_a_day_past_the_month_is_refused_with_the_service_message(self):
        """المدى يُقرأ في الخدمة وحدها — فرسالتُها هي التي تصل لا رسالةُ المسلسِل."""
        res = self.override(rule_day=32, note="يوم خارج الشهر")

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("1 و31", str(res.data["rule_day"]))

    def test_a_day_on_an_end_of_period_line_is_a_four_hundred(self):
        """#277: سطرُ «آخر يوم في الفترة» يرفض اليومَ برسالة الخدمة لا بقبولٍ صامت."""
        res = self.override(
            system="PS", code="ps_income_advances", rule_day=20, note="يوم لا يُقرأ",
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("آخرُ يومٍ في الفترة", str(res.data["rule_day"]))

    def test_an_override_without_a_note_is_a_four_hundred(self):
        """#277: التعديلُ على مسؤوليّة المكتب — ولا يُقبل بلا سببٍ مكتوب."""
        res = self.override(rule_day=20, note="   ")

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("note", res.content.decode())

    def test_clear_and_keep_need_the_settings_key(self):
        self.override(rule_day=22, note="تأجيل المكتب")
        self.as_user(self.accountant)

        for path in ("clear-override/", "keep-override/"):
            res = self.client.post(
                f"{RULES}{path}",
                {"system": "IL", "code": "il_vat_periodic"},
                format="json",
                **self.headers(),
            )
            self.assertEqual(res.status_code, 403, (path, res.content))

    def test_another_office_sees_no_override_on_the_line(self):
        self.override(rule_day=22, note="تأجيل المكتب")

        self.as_user(self.outside_owner)
        rows = self.client.get(
            RULES, {"system": "IL"}, **self.headers(tenant=self.outside),
        ).data["rules"]
        row = next(item for item in rows if item["code"] == "il_vat_periodic")
        self.assertIsNone(row["override"], "تعديلُ مكتبٍ ظهر في مكتبٍ آخر")
        self.assertEqual(row["history"], [])
        self.assertFalse(row["awaiting_decision"])


class ExtensionApiTest(OverridesApiTestCase):
    def setUp(self):
        super().setUp()
        services.refresh_office(self.tenant, day=self.day)
        self.obligation = Obligation.objects.filter(
            client=self.mine, rule_code="il_vat_periodic",
        ).order_by("period_end").first()

    def extend(self, user=None, **body):
        self.as_user(user or self.accountant)
        payload = {
            "until": (self.obligation.actual_deadline + datetime.timedelta(days=30)).isoformat(),
            "note": "مدّدنا",
            **body,
        }
        return self.client.post(
            f"{OBLIGATIONS}{self.obligation.pk}/extend/",
            payload,
            format="json",
            **self.headers(),
        )

    def test_the_writer_extends_and_the_row_carries_the_extension(self):
        res = self.extend()

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNotNone(res.data["extended_to"])
        self.assertEqual(res.data["extension_note"], "مدّدنا")
        self.assertEqual(res.data["due_date"], res.data["extended_to"])

        cleared = self.client.post(
            f"{OBLIGATIONS}{self.obligation.pk}/clear-extension/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertIsNone(cleared.data["extended_to"])
        self.assertEqual(cleared.data["due_date"], cleared.data["actual_deadline"])

    def test_an_empty_note_is_refused(self):
        self.assertEqual(self.extend(note="   ").status_code, 400)

    def test_someone_elses_obligation_is_not_found(self):
        self.assertEqual(self.extend(user=self.colleague).status_code, 404)


class CustomRulesApiTest(OverridesApiTestCase):
    def create(self, user=None, **kwargs):
        self.as_user(user or self.owner)
        return self.client.post(
            CUSTOM_RULES, self.custom_rule_payload(**kwargs),
            format="json", **self.headers(),
        )

    def test_the_owner_creates_edits_and_the_delete_is_refused(self):
        created = self.create()
        self.assertEqual(created.status_code, 201, created.content)
        row = created.data["custom_rules"][0]
        self.assertEqual(row["code"], f"office-{row['id']}")
        self.assertEqual(row["origin_label"], "من المكتب")
        self.assertIn(
            FREQUENCY_MONTHLY,
            [choice["value"] for choice in created.data["cadence_choices"]],
        )
        self.assertNotIn(
            "event", [choice["value"] for choice in created.data["cadence_choices"]],
            "دوريةُ الحدث ليست اختياراً لالتزام المكتب",
        )

        self.as_user(self.owner)
        patched = self.client.patch(
            f"{CUSTOM_RULES}{row['id']}/", {"rule_day": 20, "name": "اسم جديد"},
            format="json", **self.headers(),
        )
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual(patched.data["custom_rules"][0]["rule_day"], 20)
        self.assertEqual(patched.data["custom_rules"][0]["name"], "اسم جديد")

        refused = self.client.delete(
            f"{CUSTOM_RULES}{row['id']}/", **self.headers(),
        )
        self.assertEqual(refused.status_code, 405, refused.content)
        self.assertTrue(OfficeCustomRule.objects.filter(pk=row["id"]).exists())

    def test_a_rule_can_be_created_already_inactive(self):
        created = self.create(is_active=False)

        self.assertEqual(created.status_code, 201, created.content)
        self.assertFalse(created.data["custom_rules"][0]["is_active"])

    def test_reading_and_writing_need_the_settings_key(self):
        """#277: الالتزاماتُ الخاصة قراءةً وكتابةً بمفتاح الإعدادات — لا لكل عضو."""
        self.assertEqual(self.create(user=self.accountant).status_code, 403)

        self.as_user(self.accountant)
        listed = self.client.get(CUSTOM_RULES, **self.headers())
        self.assertEqual(listed.status_code, 403, listed.content)

        self.as_user(self.owner)
        listed = self.client.get(CUSTOM_RULES, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.data["custom_rules"], [])

    def test_patching_needs_the_settings_key(self):
        created = self.create()
        row = created.data["custom_rules"][0]

        self.as_user(self.accountant)
        patched = self.client.patch(
            f"{CUSTOM_RULES}{row['id']}/", {"rule_day": 20},
            format="json", **self.headers(),
        )
        self.assertEqual(patched.status_code, 403, patched.content)

    def test_another_office_does_not_see_our_rules(self):
        self.create()

        self.as_user(self.outside_owner)
        listed = self.client.get(CUSTOM_RULES, **self.headers(tenant=self.outside))
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.data["custom_rules"], [])

    def test_an_unknown_rule_kind_is_refused(self):
        self.assertEqual(self.create(rule_kind="every_now_and_then").status_code, 400)

    def test_a_semiannual_cadence_is_refused_for_an_office_rule(self):
        """#279/D1: «نصف سنوي» دوريةُ سطرٍ منشورٍ لا دوريةَ التزامِ مكتب."""
        refused = self.create(cadence="semiannual")

        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(
            [str(item) for item in refused.data["cadence"]], ["دورية غير معروفة."],
        )
        self.assertFalse(
            OfficeCustomRule.objects.exists(),
            "قاعدةُ مكتبٍ بدوريةٍ خارج `OFFICE_CUSTOM_RULE_CADENCE_CHOICES` حُفظت",
        )

    def test_the_event_cadence_keeps_its_tailored_message(self):
        refused = self.create(cadence="event")

        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertEqual(
            [str(item) for item in refused.data["cadence"]],
            ["التزامُ المكتب دوريٌّ — والحدثُ يُسجَّل من ملفّ الزبون."],
        )
        self.assertFalse(OfficeCustomRule.objects.exists())


class ClientEventsApiTest(OverridesApiTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # بياناتُ هجرة 0007 (v2 وخطُّ الحدث) — الهجراتُ معطَّلةٌ في الاختبار.
        migration = __import__(
            "accounting_office.migrations.0007_office_rule_override",
            fromlist=["seed_event_schedules"],
        )
        migration.seed_event_schedules(django_apps, None)

    def setUp(self):
        super().setUp()
        ready_office(self.tenant, "PS")
        services.add_client_service(
            client=self.mine, service=self.catalog["payroll"],
            starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
        )

    def post_event(self, client=None, user=None, **body):
        self.as_user(user or self.accountant)
        payload = {
            "kind": EVENT_KIND_WITHHOLDING,
            "occurred_on": EVENT_DAY.isoformat(),
            "note": "اقتطاع",
            **body,
        }
        return self.client.post(
            f"{CLIENTS}{(client or self.mine).pk}/events/",
            payload, format="json", **self.headers(),
        )

    def test_the_writer_records_the_event_and_the_row_shows_its_obligation(self):
        created = self.post_event()

        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["event"]["kind"], EVENT_KIND_WITHHOLDING)
        self.assertEqual(len(created.data["obligations"]), 1)
        obligation = created.data["obligations"][0]
        self.assertEqual(obligation["origin"], "event")
        self.assertEqual(obligation["origin_label"], "حدث")
        self.assertEqual(
            obligation["actual_deadline"],
            (EVENT_DAY + datetime.timedelta(days=30)).isoformat(),
        )

        self.as_user(self.accountant)
        listed = self.client.get(
            f"{CLIENTS}{self.mine.pk}/events/", **self.headers(),
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.data["events"]), 1)
        self.assertEqual(
            [choice["value"] for choice in listed.data["event_kinds"]],
            [EVENT_KIND_WITHHOLDING],
        )

    def test_a_client_you_cannot_see_is_not_found(self):
        self.assertEqual(self.post_event(client=self.other).status_code, 404)

    def test_a_client_of_another_office_is_not_found(self):
        self.assertEqual(
            self.post_event(client=self.outside_client).status_code, 404,
        )

    def test_overriding_the_event_line_to_45_days_moves_the_event_obligation(self):
        """#277: سطرُ الحدث مدىً بالأيام — لا يُقصّ بـ31 في المسلسِل."""
        created = self.post_event()
        self.assertEqual(created.status_code, 201, created.content)

        res = self.override(
            system="PS", code="ps_withholding_event", rule_day=45,
            note="تمدّد المكتب 45 يوماً",
        )

        self.assertEqual(res.status_code, 200, res.content)
        saved = Obligation.objects.get(
            client=self.mine, rule_code="ps_withholding_event",
        )
        self.assertEqual(
            saved.legal_date, EVENT_DAY + datetime.timedelta(days=45),
        )

    def test_recording_needs_the_write_key(self):
        readonly = User.objects.create_user(username="so_reader", password="x")
        UserCompanyMembership.objects.create(
            user=readonly, tenant=self.tenant, role="viewer",
        )
        self.assertEqual(self.post_event(user=readonly).status_code, 403)

    def test_a_disabled_kind_is_a_bad_request(self):
        services.set_office_setting(self.tenant, "enabled_event_kinds", [])

        res = self.post_event()

        self.assertEqual(res.status_code, 400, res.content)


class AlertOpensApiTest(OverridesApiTestCase):
    def test_the_row_carries_the_opens_map(self):
        services.refresh_office(self.tenant, day=self.day)
        obligation = Obligation.objects.filter(client=self.mine).first()
        from accounting_office.models import OfficeAlert

        # الجرسُ ولّد تنبيهاته في التشغيل؛ يُصفَّر هنا فيُزرع ما يقيسه الاختبار وحده.
        OfficeAlert.objects.all().delete()
        OfficeAlert.objects.create(
            tenant=self.tenant,
            recipient=self.owner,
            kind="schedule_dates_changed",
            ref_key="schedule:1",
            message="تغيّر موعد 2 التزامات",
            day=self.day,
        )
        OfficeAlert.objects.create(
            tenant=self.tenant,
            recipient=self.owner,
            kind="obligation_late",
            ref_key=f"obligation:{obligation.pk}",
            client=self.mine,
            obligation=obligation,
            message="متأخّر",
            day=self.day,
        )

        self.as_user(self.owner)
        rows = self.client.get(ALERTS, **self.headers()).data["rows"]

        by_kind = {row["kind"]: row for row in rows}
        self.assertEqual(by_kind["schedule_dates_changed"]["opens"], "deadline_rules")
        self.assertEqual(by_kind["obligation_late"]["opens"], "client")
        self.assertEqual(by_kind["schedule_dates_changed"]["client"], None)
