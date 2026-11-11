"""نقاط التذكيرات والرسائل — #280 (الجزء الأول).

**ما يثبته هذا الملف:**

1. **السجلُّ إلحاقيّ**: لا `PUT` ولا `PATCH` ولا `DELETE` على `reminder-log/` (405)،
   ولا كتابةَ صفٍّ إلا بفعلِ إرسالٍ أو تصحيح.
2. **الافتراضيُّ محميّ**: بديلُ المكتب يُكتب بمفتاح `office.settings.manage`،
   و«ارجع للافتراضي» يحذفه، والرمزُ المجهول 400 يسمّيه.
3. **الإرسالُ التلقائيُّ مقفل**: أيُّ `True` على `reminder_auto_send` ⇒ 400 برسالته.
4. **الرؤيةُ هي الحكم**: زبونُ عضوٍ آخر 404 على كل فعل، وغيرُ المرخَّص 404 للجميع.
5. **الصلاحياتُ كما هي**: القراءةُ لكل عضو، والكتابةُ بمفتاحها.
"""
import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office.models import (
    DOCUMENT_STATUS_REQUIRED,
    REMINDER_BALANCE,
    REMINDER_DOCUMENTS,
    Contact,
    DocumentChecklistItem,
    OfficeAlert,
    OfficeClient,
    OfficeHoliday,
    ReminderLog,
    ReminderPostpone,
    ReminderTemplate,
)
from accounting_office.services import resolve_setting, set_office_setting
from accounting_office.views import OfficeReminderLogViewSet
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
CLIENTS = f"{BASE}clients/"
CONTACTS = f"{BASE}contacts/"
TEMPLATES = f"{BASE}reminder-templates/"
READY = f"{BASE}ready-to-send/"
LOG = f"{BASE}reminder-log/"
HOLIDAYS = f"{BASE}office-holidays/"
SETTINGS = f"{BASE}settings/"

#: النقاطُ تمرّ باليوم الحقيقيّ (`timezone.localdate()`) في أفعالها، فالتواريخُ
#: هنا نسبةٌ إليه لا ثوابتُ في 2026: فترةٌ انتهت قبل ثلاثة أيام — والتذكيرُ
#: مستحقٌّ فيها اليوم لأن `documents_reminder_start_days` = 1.
#:
#: **واليومُ مُثبَّتٌ على الأربعاء**: عطلةُ المكتب الافتراضية الجمعة، فاختبارٌ
#: يُقرأ يومَ جمعةٍ تصير قائمتُه فارغةً بالحاجز لا بالنقص — فتنجح تأكيداتُ
#: «قائمةٌ فارغة» بلا أن تثبت شيئاً، ويسقط ما يعني أن يرى بنداً.
TODAY = timezone.localdate()
TODAY -= datetime.timedelta(days=(TODAY.weekday() - 2) % 7)
PERIOD_END = TODAY - datetime.timedelta(days=3)
PERIOD_START = PERIOD_END.replace(day=1)
UNTIL = TODAY + datetime.timedelta(days=7)


class RemindersApiTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager = User.objects.create_user(username="rem_api_mgr", password="x")
        cls.tenant = create_company(
            "مكتب تذكير API", cls.manager, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        set_office_setting(cls.tenant, "tax_system", "IL")
        set_office_setting(cls.tenant, "office_size", "small")
        # صريحاً لا اعتماداً على الافتراضي: الجمعةُ هي اليومُ الذي لا يقع عليه
        # `TODAY` أعلاه، فالقائمةُ المحسوبة تُقاس بمحتواها لا بحاجز اليوم.
        set_office_setting(cls.tenant, "rest_days", ["fri"])
        cls.viewer = User.objects.create_user(username="rem_api_viewer", password="x")
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant, role="viewer",
        )
        cls.other = User.objects.create_user(username="rem_api_other", password="x")
        UserCompanyMembership.objects.create(
            user=cls.other, tenant=cls.tenant, role="accountant",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    # ── البناء ────────────────────────────────────────────────────────────
    def make_client(self, name="محل الأوراق", *, responsible=None):
        client = OfficeClient.objects.create(
            tenant=self.tenant, name=name, responsible=responsible or self.manager,
        )
        DocumentChecklistItem.objects.create(
            tenant=self.tenant, client=client, item_code="probe_0",
            name="فاتورة مشتريات", cadence="monthly",
            period_start=PERIOD_START, period_end=PERIOD_END,
            status=DOCUMENT_STATUS_REQUIRED,
        )
        return client

    def make_contact(self, name="أبو أحمد", *, phone="0599123456", language="ar"):
        res = self.client.post(
            CONTACTS,
            {"name": name, "phone": phone, "language": language},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        return Contact.objects.get(pk=res.data["id"])

    def attach_primary(self, client, contact):
        res = self.client.post(
            f"{CLIENTS}{client.pk}/contacts/",
            {"contact": contact.pk, "is_primary": True},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

    def ready_pair(self, name="محل الأوراق"):
        client = self.make_client(name)
        contact = self.make_contact()
        self.attach_primary(client, contact)
        return client, contact

    def item(self, client, *, period_start=PERIOD_START, period_end=PERIOD_END):
        return {
            "client_id": client.pk,
            "reminder_type": REMINDER_DOCUMENTS,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        }


class ConsentApiTest(RemindersApiTestCase):
    def test_the_contact_carries_its_consent_fields_on_read(self):
        contact = self.make_contact()
        res = self.client.get(f"{CONTACTS}{contact.pk}/", **self.headers())
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["reminders_consent"])
        self.assertEqual(
            res.data["consent_types"],
            [REMINDER_DOCUMENTS, "deadline", "balance", "appointment"],
        )

    def test_consent_is_granted_and_withdrawn_through_the_contact_api(self):
        contact = self.make_contact()

        granted = self.client.post(
            f"{CONTACTS}{contact.pk}/consent/",
            {"consent": True, "types": [REMINDER_DOCUMENTS], "channel": "talk"},
            format="json", **self.headers(),
        )
        self.assertEqual(granted.status_code, 200, granted.content)
        self.assertEqual(granted.data["consent_types"], [REMINDER_DOCUMENTS])
        self.assertEqual(granted.data["consent_channel"], "talk")
        self.assertEqual(granted.data["consent_on"], timezone.localdate().isoformat())

        withdrawn = self.client.post(
            f"{CONTACTS}{contact.pk}/consent/",
            {"consent": False},
            format="json", **self.headers(),
        )
        self.assertEqual(withdrawn.status_code, 200, withdrawn.content)
        self.assertFalse(withdrawn.data["reminders_consent"])
        self.assertEqual(
            withdrawn.data["consent_withdrawn_by"]["id"], self.manager.pk,
        )

    def withdraw(self, contact):
        res = self.client.post(
            f"{CONTACTS}{contact.pk}/consent/", {"consent": False},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_who_withdrew_is_an_object_with_a_name_on_the_client_contacts_list(self):
        # الواجهةُ تقرأ `consent_withdrawn_by.name` بعد كل `refreshLinks` — فحقلُ FK
        # تلقائيّ يخرج رقماً و«سُحبت … — undefined». الشكلُ نفسُه شكلُ
        # `contact_consent_payload`: `{id, name}` بالاسم الكامل وإلا اسمُ المستخدم.
        self.manager.first_name, self.manager.last_name = "منى", "الحسن"
        self.manager.save()
        client = self.make_client()
        withdrawn = self.make_contact("أبو سحب")
        kept = self.make_contact("أم بقاء", phone="0599000111")
        self.attach_primary(client, withdrawn)
        self.attach_primary(client, kept)
        self.withdraw(withdrawn)

        res = self.client.get(f"{CLIENTS}{client.pk}/contacts/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        by_name = {row["contact"]["name"]: row["contact"] for row in res.data}
        self.assertEqual(
            by_name["أبو سحب"]["consent_withdrawn_by"],
            {"id": self.manager.pk, "name": "منى الحسن"},
        )
        self.assertIsNone(by_name["أم بقاء"]["consent_withdrawn_by"])

    def test_who_withdrew_has_the_same_shape_on_the_contact_endpoints(self):
        contact = self.make_contact()
        self.withdraw(contact)
        expected = {"id": self.manager.pk, "name": "rem_api_mgr"}

        detail = self.client.get(f"{CONTACTS}{contact.pk}/", **self.headers())
        listing = self.client.get(CONTACTS, **self.headers())

        self.assertEqual(detail.data["consent_withdrawn_by"], expected)
        self.assertEqual(
            [row["consent_withdrawn_by"] for row in listing.data], [expected],
        )

    def test_promoting_a_contact_returns_who_withdrew_as_an_object(self):
        client = self.make_client()
        contact = self.make_contact()
        self.attach_primary(client, contact)
        self.withdraw(contact)

        res = self.client.post(
            f"{CLIENTS}{client.pk}/contacts/{contact.pk}/primary/",
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            res.data["contact"]["consent_withdrawn_by"],
            {"id": self.manager.pk, "name": "rem_api_mgr"},
        )

    def test_the_withdrawer_costs_no_query_per_contact(self):
        # `select_related` على الجهات الثلاثة: عدّادُ الاستعلامات لا يتبع عددَ
        # الجهات التي سُحب إذنُها.
        client = self.make_client()

        def queries_for_list():
            with CaptureQueriesContext(connection) as captured:
                res = self.client.get(
                    f"{CLIENTS}{client.pk}/contacts/", **self.headers(),
                )
            self.assertEqual(res.status_code, 200, res.content)
            return len(captured), len(res.data)

        first = self.make_contact("جهة ١", phone="0599000001")
        self.attach_primary(client, first)
        self.withdraw(first)
        one_query_count, one_row = queries_for_list()
        for index in (2, 3, 4):
            extra = self.make_contact(f"جهة {index}", phone=f"059900000{index}")
            self.attach_primary(client, extra)
            self.withdraw(extra)
        many_query_count, many_rows = queries_for_list()

        self.assertEqual((one_row, many_rows), (1, 4))
        self.assertEqual(many_query_count, one_query_count)

    def test_an_unknown_type_or_channel_is_a_400(self):
        contact = self.make_contact()
        for payload in (
            {"consent": True, "types": ["newsletter"]},
            {"consent": True, "channel": "email"},
            {"consent": "نعم"},
        ):
            with self.subTest(payload=payload):
                res = self.client.post(
                    f"{CONTACTS}{contact.pk}/consent/", payload,
                    format="json", **self.headers(),
                )
                self.assertEqual(res.status_code, 400, res.content)

    def test_writing_consent_needs_the_write_key(self):
        contact = self.make_contact()
        self.client.force_authenticate(user=self.viewer)
        res = self.client.post(
            f"{CONTACTS}{contact.pk}/consent/", {"consent": False},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)


class TemplateApiTest(RemindersApiTestCase):
    def test_every_member_reads_the_effective_bodies_and_the_defaults(self):
        self.client.force_authenticate(user=self.viewer)
        res = self.client.get(TEMPLATES, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.data["rows"]), 8)
        self.assertIn("client_name", res.data["placeholders"])

    def test_the_office_overrides_one_body_and_returns_to_the_default(self):
        res = self.client.put(
            f"{TEMPLATES}{REMINDER_DOCUMENTS}/ar/",
            {"body": "أهلاً {client_name} — {office_name}"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(ReminderTemplate.objects.filter(tenant=self.tenant).exists())

        reset = self.client.delete(f"{TEMPLATES}{REMINDER_DOCUMENTS}/ar/", **self.headers())
        self.assertEqual(reset.status_code, 200, reset.content)
        self.assertFalse(ReminderTemplate.objects.filter(tenant=self.tenant).exists())

    def test_an_unknown_placeholder_is_a_400_that_names_it(self):
        res = self.client.put(
            f"{TEMPLATES}{REMINDER_DOCUMENTS}/ar/",
            {"body": "أهلاً {deadline_name}"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("deadline_name", str(res.data))

    def test_writing_a_body_needs_the_settings_key(self):
        self.client.force_authenticate(user=self.viewer)
        res = self.client.put(
            f"{TEMPLATES}{REMINDER_DOCUMENTS}/ar/", {"body": "نص"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)

    def test_an_unknown_type_or_language_is_a_400(self):
        for path in (
            f"{TEMPLATES}newsletter/ar/",
            f"{TEMPLATES}{REMINDER_DOCUMENTS}/en/",
        ):
            with self.subTest(path=path):
                res = self.client.put(
                    path, {"body": "نص"}, format="json", **self.headers(),
                )
                self.assertEqual(res.status_code, 400, res.content)


class ReadyToSendApiTest(RemindersApiTestCase):
    def test_the_list_groups_the_day_into_messages(self):
        client, contact = self.ready_pair()

        res = self.client.get(
            f"{READY}?day={TODAY.isoformat()}", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(len(res.data["messages"]), 1, res.data)
        message = res.data["messages"][0]
        self.assertEqual(message["recipient"]["contact_id"], contact.pk)
        self.assertEqual(message["items"][0]["client_id"], client.pk)
        self.assertEqual(message["items"][0]["step"], 1)

    def test_a_sent_message_writes_one_row_per_item(self):
        client, contact = self.ready_pair()

        res = self.client.post(
            f"{READY}sent/",
            {
                "contact_id": contact.pk,
                "body": "النصُّ المرسل",
                "channel": "whatsapp",
                "items": [self.item(client)],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        row = ReminderLog.objects.get()
        self.assertEqual(row.kind, ReminderLog.KIND_SENT)
        self.assertEqual(row.body, "النصُّ المرسل")
        self.assertEqual(row.recipient_phone, "0599123456")
        self.assertEqual(res.data["rows"][0]["id"], row.pk)

    def test_the_answer_carries_row_ids_when_bulk_insert_returns_no_rows(self):
        """MySQL لا يُرجع المفاتيح من `bulk_create` — والجوابُ يحملها رغم ذلك."""
        client, contact = self.ready_pair()

        with mock.patch.object(
            type(connection.features),
            "can_return_rows_from_bulk_insert",
            new_callable=mock.PropertyMock,
            return_value=False,
        ):
            sent = self.client.post(
                f"{READY}sent/",
                {"contact_id": contact.pk, "body": "نص", "items": [self.item(client)]},
                format="json", **self.headers(),
            )
            dismissed = self.client.post(
                f"{READY}dismiss/", {"items": [self.item(client)]},
                format="json", **self.headers(),
            )

        for res, kind in ((sent, "sent"), (dismissed, "dismissed")):
            with self.subTest(kind=kind):
                self.assertEqual(res.status_code, 201, res.content)
                stored = ReminderLog.objects.get(kind=kind)
                self.assertEqual(
                    [row["id"] for row in res.data["rows"]], [stored.pk], res.data,
                )

    def test_a_sent_call_without_a_body_is_a_400_and_writes_nothing(self):
        client, contact = self.ready_pair()
        for body in ("", "   "):
            with self.subTest(body=body):
                res = self.client.post(
                    f"{READY}sent/",
                    {"contact_id": contact.pk, "body": body, "items": [self.item(client)]},
                    format="json", **self.headers(),
                )
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("body", res.data)
        missing = self.client.post(
            f"{READY}sent/",
            {"contact_id": contact.pk, "items": [self.item(client)]},
            format="json", **self.headers(),
        )
        self.assertEqual(missing.status_code, 400, missing.content)
        self.assertFalse(ReminderLog.objects.exists())

    def test_a_sent_message_takes_whatsapp_only(self):
        client, contact = self.ready_pair()
        payload = {
            "contact_id": contact.pk,
            "body": "النصُّ المرسل",
            "items": [self.item(client)],
        }

        bad = self.client.post(
            f"{READY}sent/", {**payload, "channel": "phone"},
            format="json", **self.headers(),
        )
        self.assertEqual(bad.status_code, 400, bad.content)
        self.assertFalse(ReminderLog.objects.exists())

        blank = self.client.post(f"{READY}sent/", payload, format="json", **self.headers())
        self.assertEqual(blank.status_code, 201, blank.content)
        self.assertEqual(ReminderLog.objects.get().channel, "whatsapp")

    def test_a_manual_reminder_takes_phone_or_in_person_only(self):
        client, contact = self.ready_pair()
        payload = {
            "contact_id": contact.pk,
            "body": "اتصلنا",
            "channel": "phone",
            "items": [self.item(client)],
        }
        ok = self.client.post(
            f"{READY}manual/", payload, format="json", **self.headers(),
        )
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(ReminderLog.objects.get().kind, ReminderLog.KIND_MANUAL)

        bad = self.client.post(
            f"{READY}manual/", {**payload, "channel": "carrier-pigeon"},
            format="json", **self.headers(),
        )
        self.assertEqual(bad.status_code, 400, bad.content)

    def test_a_dismissal_writes_a_dismissed_row_and_takes_a_reason(self):
        client, contact = self.ready_pair()

        res = self.client.post(
            f"{READY}dismiss/",
            {"items": [self.item(client)], "reason": "مشغول"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        row = ReminderLog.objects.get()
        self.assertEqual(row.kind, ReminderLog.KIND_DISMISSED)
        self.assertEqual(row.reason, "مشغول")
        self.assertEqual(row.body, "")

    def test_a_postponement_needs_a_date_after_today(self):
        client, contact = self.ready_pair()
        res = self.client.post(
            f"{READY}postpone/",
            {
                "client_id": client.pk,
                "reminder_type": REMINDER_DOCUMENTS,
                "until": UNTIL.isoformat(),
                "reason": "مسافر",
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            ReminderPostpone.objects.get(client=client).until, UNTIL,
        )

        past = self.client.post(
            f"{READY}postpone/",
            {
                "client_id": client.pk,
                "reminder_type": REMINDER_DOCUMENTS,
                "until": TODAY.isoformat(),
            },
            format="json", **self.headers(),
        )
        self.assertEqual(past.status_code, 400, past.content)
        self.assertIn("until", past.data)
        self.assertEqual(ReminderPostpone.objects.filter(client=client).count(), 1)

    def test_an_invisible_client_is_a_404(self):
        """زبونُ غيري لا يظهر ولا يُرسَل له — والمحاسبُ بلا مفتاح «يرى الكل»."""
        client, contact = self.ready_pair(name="زبون المدير")
        self.client.force_authenticate(user=self.other)

        listed = self.client.get(
            f"{READY}?day={TODAY.isoformat()}", **self.headers(),
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["messages"], [])

        sent = self.client.post(
            f"{READY}sent/",
            {
                "contact_id": contact.pk,
                "body": "نص",
                "channel": "whatsapp",
                "items": [self.item(client)],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(sent.status_code, 404, sent.content)
        self.assertFalse(ReminderLog.objects.exists())

    def test_every_action_needs_the_write_key(self):
        client, contact = self.ready_pair()
        self.client.force_authenticate(user=self.viewer)
        for path in ("sent/", "manual/", "dismiss/", "postpone/"):
            with self.subTest(path=path):
                res = self.client.post(f"{READY}{path}", {}, format="json", **self.headers())
                self.assertEqual(res.status_code, 403, res.content)

    def test_an_unknown_reminder_type_is_a_400(self):
        client, contact = self.ready_pair()
        res = self.client.post(
            f"{READY}sent/",
            {
                "contact_id": contact.pk,
                "body": "نص",
                "channel": "whatsapp",
                "items": [{**self.item(client), "reminder_type": "newsletter"}],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_the_list_can_be_narrowed_to_one_type(self):
        client, contact = self.ready_pair()
        res = self.client.get(
            f"{READY}?day={TODAY.isoformat()}&reminder_type={REMINDER_BALANCE}",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["messages"], [])


class ReminderLogApiTest(RemindersApiTestCase):
    def sent_row(self):
        client, contact = self.ready_pair()
        res = self.client.post(
            f"{READY}sent/",
            {
                "contact_id": contact.pk,
                "body": "نص",
                "channel": "whatsapp",
                "items": [self.item(client)],
            },
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        return ReminderLog.objects.get()

    def test_the_log_is_listed_and_never_updated_or_deleted(self):
        row = self.sent_row()

        listed = self.client.get(LOG, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.data["rows"][0]["id"], row.pk)

        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                res = getattr(self.client, method)(f"{LOG}{row.pk}/", **self.headers())
                self.assertEqual(res.status_code, 405, res.content)
        self.assertEqual(ReminderLog.objects.filter(pk=row.pk).count(), 1)

    def test_the_log_endpoint_advertises_the_read_only_row_it_returns(self):
        """`serializer_class` يقول الحقيقة: سطرُ السجلّ للقراءة لا حمولةُ تأجيل."""
        row = self.sent_row()

        res = self.client.get(f"{LOG}{row.pk}/", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)

        fields = OfficeReminderLogViewSet.serializer_class().fields
        self.assertEqual(set(fields), set(res.data))
        self.assertTrue(
            all(field.read_only for field in fields.values()),
            [name for name, field in fields.items() if not field.read_only],
        )

    def test_the_undo_points_at_the_row_it_reverts(self):
        row = self.sent_row()

        res = self.client.post(f"{LOG}{row.pk}/undo/", {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 201, res.content)
        undo = ReminderLog.objects.get(kind=ReminderLog.KIND_UNDO)
        self.assertEqual(undo.reverts_id, row.pk)
        self.assertEqual(res.data["row"]["id"], undo.pk)

        again = self.client.post(
            f"{LOG}{undo.pk}/undo/", {}, format="json", **self.headers(),
        )
        self.assertEqual(again.status_code, 400, again.content)

    def test_the_clients_log_is_served_on_the_client_file(self):
        row = self.sent_row()
        res = self.client.get(
            f"{CLIENTS}{row.client_id}/reminder-log/", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["rows"][0]["id"], row.pk)

    def test_a_client_of_another_member_is_a_404_on_the_log(self):
        """المحاسبُ بلا «يرى زبائن غيره»: زبونُ المدير 404، وزبونُه 200."""
        mine, contact = self.ready_pair(name="زبون المحاسب")
        OfficeClient.objects.filter(pk=mine.pk).update(responsible=self.other)
        managers_client, manager_contact = self.ready_pair(name="زبون المدير")

        self.client.force_authenticate(user=self.other)
        self.assertEqual(
            self.client.get(
                f"{CLIENTS}{mine.pk}/reminder-log/", **self.headers(),
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"{CLIENTS}{managers_client.pk}/reminder-log/", **self.headers(),
            ).status_code,
            404,
        )

    def test_undoing_someone_elses_row_is_a_404(self):
        """سطرُ زبونٍ لا يراه المحاسب لا يُبطَل: الرؤيةُ تحكم الفعلَ والقراءةَ."""
        managers_client = self.make_client("زبون المدير")
        hidden = ReminderLog.objects.create(
            tenant=self.tenant,
            client=managers_client,
            reminder_type=REMINDER_DOCUMENTS,
            kind=ReminderLog.KIND_SENT,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )

        self.client.force_authenticate(user=self.other)
        res = self.client.post(
            f"{LOG}{hidden.pk}/undo/", {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 404, res.content)
        self.assertFalse(ReminderLog.objects.filter(kind=ReminderLog.KIND_UNDO).exists())


class HolidayApiTest(RemindersApiTestCase):
    def test_every_member_lists_but_the_settings_key_writes(self):
        res = self.client.post(
            HOLIDAYS,
            {"date": TODAY.isoformat(), "name": "عيد المكتب"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        holiday = OfficeHoliday.objects.get(tenant=self.tenant)
        self.assertEqual(holiday.date, TODAY)

        self.client.force_authenticate(user=self.viewer)
        listed = self.client.get(HOLIDAYS, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.data), 1)

        refused = self.client.post(
            HOLIDAYS, {"date": UNTIL.isoformat(), "name": "آخر"},
            format="json", **self.headers(),
        )
        self.assertEqual(refused.status_code, 403, refused.content)

    def test_the_same_day_twice_is_a_400_and_delete_removes_it(self):
        first = self.client.post(
            HOLIDAYS, {"date": TODAY.isoformat(), "name": "عيد"},
            format="json", **self.headers(),
        )
        self.assertEqual(first.status_code, 201, first.content)
        again = self.client.post(
            HOLIDAYS, {"date": TODAY.isoformat(), "name": "مكرّر"},
            format="json", **self.headers(),
        )
        self.assertEqual(again.status_code, 400, again.content)

        deleted = self.client.delete(
            f"{HOLIDAYS}{first.data['id']}/", **self.headers(),
        )
        self.assertEqual(deleted.status_code, 204, deleted.content)
        self.assertFalse(OfficeHoliday.objects.filter(tenant=self.tenant).exists())


class ReminderSettingsApiTest(RemindersApiTestCase):
    def test_auto_send_is_locked_off_with_its_message(self):
        res = self.client.put(
            f"{SETTINGS}reminder_auto_send/", {"value": True},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn(
            "الإرسال التلقائي غير متاح قبل المرحلة الثانية", str(res.data),
        )

        off = self.client.put(
            f"{SETTINGS}reminder_auto_send/", {"value": False},
            format="json", **self.headers(),
        )
        self.assertEqual(off.status_code, 200, off.content)

    def test_the_send_window_is_validated_hours_and_order(self):
        invalid_hour = self.client.put(
            f"{SETTINGS}reminder_send_hour_start/", {"value": 25},
            format="json", **self.headers(),
        )
        self.assertEqual(invalid_hour.status_code, 400, invalid_hour.content)

        inverted = self.client.put(
            f"{SETTINGS}reminder_send_hour_end/", {"value": 7},
            format="json", **self.headers(),
        )
        self.assertEqual(inverted.status_code, 400, inverted.content)
        self.assertIn("أبكر", str(inverted.data))

        # والبدايةُ المتأخّرةُ عن النهاية مرفوضةٌ كذلك — الفحصُ متساوٍ على الطرفين،
        # وإلا قُبلت بدايةُ 20 على نهاية 19 (الافتراضيّان 9 و19).
        late_start = self.client.put(
            f"{SETTINGS}reminder_send_hour_start/", {"value": 20},
            format="json", **self.headers(),
        )
        self.assertEqual(late_start.status_code, 400, late_start.content)
        self.assertIn("نافذة الإرسال", str(late_start.data))

        # و«ارجع للافتراضي» حذفٌ لا كتابة، لكنه يحرّك الطرف إلى افتراضيّه (19):
        # نافذةٌ 20→23 تصير 20→19 بمسحٍ واحد — فيُرفض بالرسالة نفسها ويبقى الطرف.
        for key, value in (("end", 23), ("start", 20)):
            ok = self.client.put(
                f"{SETTINGS}reminder_send_hour_{key}/", {"value": value},
                format="json", **self.headers(),
            )
            self.assertEqual(ok.status_code, 200, ok.content)
        reset = self.client.delete(
            f"{SETTINGS}reminder_send_hour_end/", **self.headers(),
        )
        self.assertEqual(reset.status_code, 400, reset.content)
        self.assertIn("نافذة الإرسال", str(reset.data))
        self.assertEqual(
            resolve_setting(self.tenant, "reminder_send_hour_end"), 23,
        )

        # ومسحُ البداية يُعيدها إلى 9 فتبقى النافذة مرتَّبة: يمرّ.
        reset_start = self.client.delete(
            f"{SETTINGS}reminder_send_hour_start/", **self.headers(),
        )
        self.assertEqual(reset_start.status_code, 200, reset_start.content)

    def test_the_reminder_group_is_served_with_its_defaults(self):
        res = self.client.get(SETTINGS, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        groups = {
            row["key"]: row for row in res.data["settings"]
        }
        for key, default in (
            ("reminder_types_enabled", [REMINDER_DOCUMENTS, "deadline", "balance", "appointment"]),
            ("reminder_auto_send", False),
            ("reminder_merge_daily", True),
            ("documents_reminder_start_days", 1),
            ("documents_reminder_interval_days", 3),
            ("documents_reminder_max", 3),
            ("reminder_send_hour_start", 9),
            ("reminder_send_hour_end", 19),
            ("reminder_escalation_owner_days", 2),
        ):
            with self.subTest(key=key):
                self.assertEqual(groups[key]["value"], default)
                self.assertEqual(groups[key]["group"], "reminders")
