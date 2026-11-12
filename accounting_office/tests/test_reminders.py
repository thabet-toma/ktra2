"""التذكيرات والرسائل: «جاهز للإرسال» وتذكير الأوراق الناقصة — #280 (الجزء الأول).

**ما يثبته هذا الملف:**

1. **الموافقةُ على التذكير** تُمنح وتُسحب بتاريخها وقناتها، ورافضُ التذكير (أو
   مَن لا يحمل نوعَه في `consent_types`) لا يظهر في القائمة أبداً.
2. **القوالبُ افتراضيّةٌ في الكود** (عربيٌّ وعبريٌّ لكل نوع)، وبديلُ المكتب يغلبها،
   و«ارجع للافتراضي» يحذف البديل، والرمزُ المجهول يرفض بـ400 يسمّيه.
3. **الإيقاعُ يُحسب عند القراءة ولا يُخزَّن**: أوّلُ تذكيرٍ بعد انتهاء الفترة
   بيوم، والثاني بعد ثلاثة أيامٍ من الأوّل للإرسال، ولا رابعَ بعد الثالث.
4. **الأوراقُ الواصلةُ تخرج من النصّ**، و«وصلت ناقصة» تبقى، والفترةُ تنتهي من
   نفسها حين لا يبقى بندٌ مطلوبٌ أو ناقص.
5. **«شيل لهذه المرة» يُعيد الإيقاع ولا يُعدّ**، و«أجّل» يحجب حتى تاريخه،
   ويومُ راحة الزبون وعطلةُ المكتب يؤجّلان الظهورَ لا يُلغيانه.
6. **السجلُّ إلحاقيّ**: التصحيحُ صفُّ `undo` جديد يشير إلى ما يُبطله، والملغى
   لا يُعدّ، ولا يُبطَل الـ`undo` مرّتين.
7. **التصعيدُ بعد الحدّ**: تنبيهٌ للمسؤول في يوم الاستحقاق التالي، ولصاحب
   المكتب بعد يومين، ويُسقطهما اكتمالُ الأوراق عند القراءة.
8. **الكلفةُ ثابتة**: قائمةُ «جاهز للإرسال» لا تكلّف استعلاماً لكل زبون.
9. **البندُ يحمل نظامَ زبونه الضريبيّ** (#280/ب) ليُبنى رابطُ الواتساب منه، ولا
   نظامَ مستلِمٍ واحداً يُفرَض على بنودِ زبونين مختلفَي النظام.
"""
import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounting_office import fee_invoices, services
from accounting_office.models import (
    CONSENT_CHANNEL_PAPER,
    CONSENT_CHANNEL_TALK,
    DOCUMENT_STATUS_PARTIAL,
    DOCUMENT_STATUS_RECEIVED,
    DOCUMENT_STATUS_REQUIRED,
    OFFICE_ALERT_KIND_REMINDER_LIMIT,
    OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER,
    REMINDER_APPOINTMENT,
    REMINDER_BALANCE,
    REMINDER_CHANNEL_WHATSAPP,
    REMINDER_DEADLINE,
    REMINDER_DEFAULT_TEXTS,
    REMINDER_DOCUMENTS,
    REMINDER_PLACEHOLDERS,
    REMINDER_TYPE_CHOICES,
    Contact,
    DocumentChecklistItem,
    FeeDraft,
    FeeDraftLine,
    OfficeAlert,
    OfficeClient,
    OfficeHoliday,
    OfficeSettingValue,
    ReminderLog,
    ReminderPostpone,
    ReminderTemplate,
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

#: كانون الثاني 2026: بدايتُه يوم خميس ونهايتُه يوم سبت، فيكون 1 شباط أحداً.
JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
#: السنةُ 2026 كاملة — **تبدأ في اليوم نفسه الذي يبدأ فيه كانون الثاني**، وهو ما
#: يجعل مفتاحَ التنبيه بلا نهاية الفترة يصطدم.
YEAR_START = datetime.date(2026, 1, 1)
YEAR_END = datetime.date(2026, 12, 31)
FEB_FIRST = datetime.date(2026, 2, 1)       # أوّلُ يومٍ بعد انتهاء الفترة — الأحد
FEB_SECOND = datetime.date(2026, 2, 2)      # الاثنين
FEB_THIRD = datetime.date(2026, 2, 3)       # الثلاثاء
FEB_FOURTH = datetime.date(2026, 2, 4)      # الأربعاء — بعد ثلاثة أيامٍ من الإرسال الأوّل
FEB_FIFTH = datetime.date(2026, 2, 5)       # الخميس
FEB_SEVENTH = datetime.date(2026, 2, 7)     # السبت
FEB_TENTH = datetime.date(2026, 2, 10)      # الثلاثاء — يومُ الاستحقاق الرابع
FEB_TWELFTH = datetime.date(2026, 2, 12)    # الخميس — بعد يومين من تنبيه المسؤول
#: يومُ جمعة — عطلةُ المكتب الافتراضية في السجلّ (`rest_days = ["fri"]`).
FRIDAY = datetime.date(2026, 2, 6)


def at(row, day):
    """يُثبّت يومَ الصفّ — `auto_now_add` يكتب لحظةَ الاختبار لا تاريخَه المحسوب."""
    stamp = datetime.datetime.combine(day, datetime.time(12, 0))
    ReminderLog.objects.filter(pk=row.pk).update(
        created_at=timezone.make_aware(stamp),
    )
    return row


class RemindersTestCase(TestCase):
    """مكتبٌ جاهزٌ (نظامٌ ضريبيٌّ وحجم)، وزبونٌ بأوراقٍ ناقصةٍ في كانون الثاني."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="rem_owner", password="x")
        cls.tenant = create_company(
            "مكتب التذكير", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    # ── البناء ────────────────────────────────────────────────────────────
    def make_member(self, username, *, role="accountant"):
        """عضوٌ في مكتب الاختبار — المسؤولُ يجب أن يكون عضواً وإلا رفضه النموذج."""
        user = User.objects.create_user(username=username, password="x")
        UserCompanyMembership.objects.create(user=user, tenant=self.tenant, role=role)
        return user

    def make_client(self, name="زبون التذكير", *, responsible=None, **card):
        client = OfficeClient.objects.create(
            tenant=self.tenant, name=name, responsible=responsible or self.owner,
        )
        fields = {"annual_sales": 0, "vat_classification": "authorized"}
        fields.update(card)
        TaxCard.objects.create(client=client, **fields)
        return client

    def add_missing(
        self, client, *,
        names=("فاتورة مشتريات",),
        period_start=JAN_START,
        period_end=JAN_END,
        status=DOCUMENT_STATUS_REQUIRED,
    ):
        taken = set(
            DocumentChecklistItem.objects
            .filter(client=client, period_start=period_start)
            .values_list("item_code", flat=True),
        )
        rows = []
        for name in names:
            index = 0
            while f"probe_{index}" in taken:
                index += 1
            taken.add(f"probe_{index}")
            rows.append(DocumentChecklistItem.objects.create(
                tenant=self.tenant,
                client=client,
                item_code=f"probe_{index}",
                name=name,
                cadence="monthly",
                period_start=period_start,
                period_end=period_end,
                status=status,
            ))
        return rows

    def make_contact(self, name="أبو أحمد", *, phone="0599123456", language="ar", **extra):
        return Contact.objects.create(
            tenant=self.tenant, name=name, phone=phone, language=language, **extra,
        )

    def ready_client(self, name="زبون التذكير", *, contact=None, **extra):
        """زبونٌ بجهةٍ رئيسية وبندٍ ناقصٍ في كانون الثاني — الحالةُ المحسوبة."""
        client = self.make_client(name, **extra)
        contact = contact or self.make_contact()
        services.link_client_contact(client=client, contact=contact, is_primary=True)
        self.add_missing(client)
        return client, contact

    def send(self, client, *, day, contact, period_start=JAN_START, period_end=JAN_END):
        rows = services.mark_reminders_sent(
            self.tenant,
            user=self.owner,
            contact_id=contact.pk,
            body="نصٌّ أُرسل",
            items=[{
                "client_id": client.pk,
                "reminder_type": REMINDER_DOCUMENTS,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            }],
        )
        for row in rows:
            at(row, day)
        return rows

    def ready(self, day=FEB_FIRST, **kwargs):
        return services.ready_to_send_payload(
            self.tenant, user=self.owner, day=day, **kwargs,
        )

    def messages(self, day=FEB_FIRST, **kwargs):
        return self.ready(day, **kwargs)["messages"]

    def only_item(self, day=FEB_FIRST, **kwargs):
        messages = self.messages(day, **kwargs)
        self.assertEqual(len(messages), 1, messages)
        self.assertEqual(len(messages[0]["items"]), 1, messages)
        return messages[0]["items"][0]


# ── الموافقة (#280/D2) ───────────────────────────────────────────────────────
class ConsentTest(RemindersTestCase):
    def test_granting_writes_the_date_the_channel_and_the_types(self):
        contact = self.make_contact(reminders_consent=False, consent_types=[])

        services.set_contact_consent(
            contact,
            consent=True,
            types=[REMINDER_DOCUMENTS, REMINDER_DEADLINE],
            channel=CONSENT_CHANNEL_TALK,
            actor=self.owner,
            day=FEB_FIRST,
        )

        contact.refresh_from_db()
        self.assertTrue(contact.reminders_consent)
        self.assertEqual(contact.consent_types, [REMINDER_DOCUMENTS, REMINDER_DEADLINE])
        self.assertEqual(contact.consent_on, FEB_FIRST)
        self.assertEqual(contact.consent_channel, CONSENT_CHANNEL_TALK)
        self.assertIsNone(contact.consent_withdrawn_on)
        self.assertIsNone(contact.consent_withdrawn_by_id)

    def test_withdrawing_records_the_day_and_the_member_and_clears_nothing_else(self):
        contact = self.make_contact(consent_on=JAN_START, consent_channel=CONSENT_CHANNEL_PAPER)

        services.set_contact_consent(
            contact, consent=False, actor=self.owner, day=FEB_FIRST,
        )

        contact.refresh_from_db()
        self.assertFalse(contact.reminders_consent)
        self.assertEqual(contact.consent_withdrawn_on, FEB_FIRST)
        self.assertEqual(contact.consent_withdrawn_by_id, self.owner.pk)
        self.assertEqual(contact.consent_channel, CONSENT_CHANNEL_PAPER)

    def test_an_unknown_type_or_channel_is_refused(self):
        contact = self.make_contact()

        with self.assertRaises(DjangoValidationError) as caught:
            services.set_contact_consent(
                contact, consent=True, types=["newsletter"], actor=self.owner,
            )
        self.assertIn("newsletter", str(caught.exception))

        with self.assertRaises(DjangoValidationError) as caught:
            services.set_contact_consent(
                contact, consent=True, channel="email", actor=self.owner,
            )
        self.assertIn("email", str(caught.exception))

    def test_a_withdrawn_consent_keeps_the_contact_out_of_the_ready_list(self):
        client, contact = self.ready_client()
        self.assertEqual(len(self.messages(FEB_FIRST)), 1)

        services.set_contact_consent(
            contact, consent=False, actor=self.owner, day=FEB_FIRST,
        )

        self.assertEqual(self.messages(FEB_FIRST), [])
        self.assertEqual(self.messages(FEB_SECOND), [])

    def test_a_contact_whose_types_lack_documents_is_not_a_recipient(self):
        client, contact = self.ready_client()
        services.set_contact_consent(
            contact, consent=True, types=[REMINDER_BALANCE], actor=self.owner,
            day=FEB_FIRST,
        )
        self.assertEqual(self.messages(FEB_FIRST), [])

    def test_a_new_contact_takes_the_office_default_types(self):
        services.set_office_setting(
            self.tenant,
            services.REMINDER_DEFAULT_CONSENT_TYPES_KEY,
            [REMINDER_DOCUMENTS, REMINDER_APPOINTMENT],
        )
        contact = services.create_contact(
            self.tenant, name="جهة جديدة", phone="0599000000", language="ar",
        )
        self.assertEqual(contact.consent_types, [REMINDER_DOCUMENTS, REMINDER_APPOINTMENT])
        self.assertTrue(contact.reminders_consent)


# ── القوالب (#280/D3) ────────────────────────────────────────────────────────
class TemplateTest(RemindersTestCase):
    def test_every_type_ships_an_arabic_and_a_hebrew_default(self):
        self.assertEqual(
            set(REMINDER_DEFAULT_TEXTS),
            {key for key, _label in REMINDER_TYPE_CHOICES},
        )
        for reminder_type, texts in REMINDER_DEFAULT_TEXTS.items():
            with self.subTest(reminder_type=reminder_type):
                self.assertEqual(set(texts), {"ar", "he"})
                for language, body in texts.items():
                    self.assertTrue(body.strip(), (reminder_type, language))
                    for placeholder in REMINDER_PLACEHOLDERS:
                        self.assertNotIn(
                            "{" + placeholder + "_", body,
                            f"رمزٌ آخر غير المعتمد في {reminder_type}/{language}",
                        )

    def test_the_documents_template_names_the_client_the_period_and_the_missing_list(self):
        body = REMINDER_DEFAULT_TEXTS[REMINDER_DOCUMENTS]["ar"]
        for placeholder in ("{client_name}", "{period}", "{missing_list}", "{office_name}"):
            self.assertIn(placeholder, body)

    def test_the_effective_body_is_the_default_until_the_office_overrides_it(self):
        rows = services.reminder_templates_payload(self.tenant)
        self.assertEqual(len(rows["rows"]), len(REMINDER_TYPE_CHOICES) * 2)
        self.assertEqual(rows["placeholders"], list(REMINDER_PLACEHOLDERS))
        row = next(
            item for item in rows["rows"]
            if item["reminder_type"] == REMINDER_DOCUMENTS and item["language"] == "ar"
        )
        self.assertFalse(row["is_custom"])
        self.assertEqual(row["body"], REMINDER_DEFAULT_TEXTS[REMINDER_DOCUMENTS]["ar"])
        self.assertEqual(row["default_body"], row["body"])

    def test_saving_an_override_never_touches_the_shipped_default(self):
        services.set_reminder_template(
            self.tenant,
            reminder_type=REMINDER_DOCUMENTS,
            language="ar",
            body="نصُّ المكتب — {client_name}",
            actor=self.owner,
        )

        row = next(
            item for item in services.reminder_templates_payload(self.tenant)["rows"]
            if item["reminder_type"] == REMINDER_DOCUMENTS and item["language"] == "ar"
        )
        self.assertTrue(row["is_custom"])
        self.assertEqual(row["body"], "نصُّ المكتب — {client_name}")
        self.assertEqual(row["default_body"], REMINDER_DEFAULT_TEXTS[REMINDER_DOCUMENTS]["ar"])
        self.assertEqual(ReminderTemplate.objects.filter(tenant=self.tenant).count(), 1)

    def test_returning_to_the_default_deletes_the_override_only(self):
        services.set_reminder_template(
            self.tenant,
            reminder_type=REMINDER_DOCUMENTS,
            language="ar",
            body="نصُّ المكتب",
            actor=self.owner,
        )
        services.reset_reminder_template(
            self.tenant, reminder_type=REMINDER_DOCUMENTS, language="ar",
        )

        self.assertFalse(ReminderTemplate.objects.filter(tenant=self.tenant).exists())
        row = next(
            item for item in services.reminder_templates_payload(self.tenant)["rows"]
            if item["reminder_type"] == REMINDER_DOCUMENTS and item["language"] == "ar"
        )
        self.assertEqual(row["body"], REMINDER_DEFAULT_TEXTS[REMINDER_DOCUMENTS]["ar"])

    def test_an_unknown_placeholder_is_refused_and_named(self):
        with self.assertRaises(DjangoValidationError) as caught:
            services.set_reminder_template(
                self.tenant,
                reminder_type=REMINDER_DOCUMENTS,
                language="ar",
                body="أهلاً {client_name} — {deadline_name}",
                actor=self.owner,
            )
        self.assertIn("deadline_name", str(caught.exception))
        self.assertFalse(ReminderTemplate.objects.filter(tenant=self.tenant).exists())

    def test_an_empty_body_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            services.set_reminder_template(
                self.tenant,
                reminder_type=REMINDER_DOCUMENTS,
                language="ar",
                body="   ",
                actor=self.owner,
            )

    def test_rendering_substitutes_the_known_placeholders_and_leaves_the_rest(self):
        rendered = services.render_reminder_body(
            "{client_name} — {period} — {unknown_thing}",
            {"client_name": "أبو أحمد", "period": "كانون الثاني 2026"},
        )
        self.assertEqual(rendered, "أبو أحمد — كانون الثاني 2026 — {unknown_thing}")

    def test_a_body_with_braces_that_is_not_a_placeholder_never_crashes(self):
        self.assertEqual(
            services.render_reminder_body("{1} { } {office_name}", {"office_name": "مكتبنا"}),
            "{1} { } مكتبنا",
        )

    def test_an_unknown_type_or_language_is_refused(self):
        with self.assertRaises(DjangoValidationError):
            services.set_reminder_template(
                self.tenant, reminder_type="newsletter", language="ar",
                body="نصّ", actor=self.owner,
            )
        with self.assertRaises(DjangoValidationError):
            services.set_reminder_template(
                self.tenant, reminder_type=REMINDER_DOCUMENTS, language="en",
                body="نصّ", actor=self.owner,
            )


# ── الإيقاع (#280/D6) ────────────────────────────────────────────────────────
class CadenceTest(RemindersTestCase):
    def test_the_first_reminder_is_due_one_day_after_the_period_ends(self):
        self.ready_client()

        self.assertEqual(self.messages(JAN_END), [])
        item = self.only_item(FEB_FIRST)
        self.assertEqual(item["step"], 1)
        self.assertEqual(item["max"], 3)
        self.assertEqual(item["period_label"], "كانون الثاني 2026")
        self.assertEqual(item["missing_list"], ["فاتورة مشتريات"])

    def test_the_second_reminder_comes_three_days_after_the_first_send(self):
        client, contact = self.ready_client()
        self.send(client, day=FEB_FIRST, contact=contact)

        self.assertEqual(self.messages(FEB_THIRD), [])
        item = self.only_item(FEB_FOURTH)
        self.assertEqual(item["step"], 2)

    def test_there_is_no_fourth_reminder_after_the_third(self):
        client, contact = self.ready_client()
        self.send(client, day=FEB_FIRST, contact=contact)
        self.send(client, day=FEB_FOURTH, contact=contact)
        self.send(client, day=FEB_SEVENTH, contact=contact)

        self.assertEqual(self.messages(FEB_TENTH), [])
        self.assertEqual(self.messages(datetime.date(2026, 3, 1)), [])

    def test_a_received_item_leaves_the_text_and_a_partial_one_stays(self):
        client, contact = self.ready_client()
        rows = self.add_missing(
            client, names=("تقرير مدقّق",), status=DOCUMENT_STATUS_PARTIAL,
        )
        received = self.add_missing(
            client, names=("كشف بنك",), status=DOCUMENT_STATUS_RECEIVED,
        )

        item = self.only_item()

        self.assertEqual(item["missing_list"], ["فاتورة مشتريات", "تقرير مدقّق"])
        self.assertNotIn("كشف بنك", item["missing_list"])
        self.assertEqual(item["missing_codes"], ["probe_0", rows[0].item_code])
        self.assertEqual(received[0].status, DOCUMENT_STATUS_RECEIVED)

    def test_the_reminders_stop_when_no_required_row_remains(self):
        client, contact = self.ready_client()
        DocumentChecklistItem.objects.filter(client=client).update(
            status=DOCUMENT_STATUS_RECEIVED,
        )
        self.assertEqual(self.messages(FEB_FIRST), [])

    def test_a_dismissal_restarts_the_interval_and_is_not_counted(self):
        client, contact = self.ready_client()
        services.dismiss_reminders(
            self.tenant,
            user=self.owner,
            items=[{
                "client_id": client.pk,
                "reminder_type": REMINDER_DOCUMENTS,
                "period_start": JAN_START.isoformat(),
                "period_end": JAN_END.isoformat(),
            }],
        )
        for row in ReminderLog.objects.filter(client=client, kind="dismissed"):
            at(row, FEB_FIRST)

        self.assertEqual(self.messages(FEB_THIRD), [])
        item = self.only_item(FEB_FOURTH)
        self.assertEqual(item["step"], 1)

    def test_a_manual_reminder_counts_toward_the_maximum(self):
        client, contact = self.ready_client()
        services.mark_reminders_manual(
            self.tenant,
            user=self.owner,
            contact_id=contact.pk,
            body="اتصلنا فيه",
            channel="phone",
            items=[{
                "client_id": client.pk,
                "reminder_type": REMINDER_DOCUMENTS,
                "period_start": JAN_START.isoformat(),
                "period_end": JAN_END.isoformat(),
            }],
        )
        for row in ReminderLog.objects.filter(client=client, kind="manual"):
            at(row, FEB_FIRST)

        self.assertEqual(self.only_item(FEB_FOURTH)["step"], 2)

    def test_an_undo_removes_one_count_and_cannot_be_undone_twice(self):
        client, contact = self.ready_client()
        sent = self.send(client, day=FEB_FIRST, contact=contact)[0]
        self.assertEqual(self.only_item(FEB_FOURTH)["step"], 2)

        services.undo_reminder_log(sent, actor=self.owner)
        self.assertEqual(self.only_item(FEB_FOURTH)["step"], 1)

        undo = ReminderLog.objects.get(reverts=sent)
        with self.assertRaises(DjangoValidationError):
            services.undo_reminder_log(undo, actor=self.owner)
        self.assertEqual(
            ReminderLog.objects.filter(reverts=undo).count(), 0,
        )

    def test_a_reverted_row_still_exists_and_the_undo_points_at_it(self):
        client, contact = self.ready_client()
        sent = self.send(client, day=FEB_FIRST, contact=contact)[0]

        undo = services.undo_reminder_log(sent, actor=self.owner)

        self.assertEqual(undo.kind, ReminderLog.KIND_UNDO)
        self.assertEqual(undo.reverts_id, sent.pk)
        self.assertEqual(undo.body, "")
        self.assertEqual(ReminderLog.objects.filter(kind=ReminderLog.KIND_SENT).count(), 1)


# ── القائمة والتجميع (#280/D9) ───────────────────────────────────────────────
class ReadyListTest(RemindersTestCase):
    def test_one_person_who_is_recipient_for_two_clients_gets_one_message(self):
        shared = self.make_contact(name="أبو أحمد")
        first, _contact = self.ready_client("محل أول", contact=shared)
        second, _contact = self.ready_client("محل ثانٍ", contact=shared)

        messages = self.messages()

        self.assertEqual(len(messages), 1, messages)
        self.assertEqual(messages[0]["recipient"]["contact_id"], shared.pk)
        self.assertEqual(
            sorted(item["client_id"] for item in messages[0]["items"]),
            sorted([first.pk, second.pk]),
        )
        self.assertIn("محل أول", messages[0]["body"])
        self.assertIn("محل ثانٍ", messages[0]["body"])

    def test_each_item_carries_the_tax_system_of_its_own_client(self):
        """#280/ب: النظامُ في بند الرسالة لا في مستلِمها — فلا نظامٌ واحدٌ يُفرَض.

        رسالةُ شخصٍ واحدٍ قد تجمع بندَي زبونين بنظامين مختلفين، والواجهةُ تبني
        رابطَ الواتساب من نظام **صاحب البند** (والأرضيُّ لا يُعرف مفتاحُ دولته
        إلا منه). فيُقرأ نظامُ كل بندٍ من زبونه، أو يبقى `None` إن غاب.
        """
        shared = self.make_contact(name="أبو أحمد")
        first, _contact = self.ready_client("محل أول", contact=shared)
        second, _contact = self.ready_client("محل ثانٍ", contact=shared)
        # المكتب كلُّه على IL، وهذا الزبون وحده على PS — تخصيصُ زبونٍ لا مكتب.
        services.set_client_setting(first, "tax_system", "PS")

        items = {item["client_id"]: item for item in self.messages()[0]["items"]}

        self.assertEqual(items[first.pk]["tax_system"], "PS")
        self.assertEqual(items[second.pk]["tax_system"], "IL")

    def test_an_item_whose_client_has_no_tax_system_carries_none(self):
        """وإن غاب النظامُ (مكتبٌ لم يختر بعدُ) بقي `None` — لا افتراضيَّ يُخترَع.

        `tax_system` بلا افتراضيٍّ في السجلّ، والخدمةُ ترفض حذفَه؛ فيُحذف الصفُّ
        مباشرةً هنا ليُحاكى مكتبٌ في أول تشغيله.
        """
        client, _contact = self.ready_client()
        OfficeSettingValue.objects.filter(
            tenant=self.tenant, key="tax_system",
        ).delete()

        items = self.messages()[0]["items"]

        self.assertEqual([item["client_id"] for item in items], [client.pk])
        self.assertIsNone(items[0]["tax_system"])

    def test_the_assigned_recipient_for_the_type_beats_the_primary_contact(self):
        client, primary = self.ready_client()
        accountant = self.make_contact(name="المحاسب", phone="0569000000", language="he")
        services.link_client_contact(client=client, contact=accountant)
        services.set_reminder_recipient(
            client=client, reminder_type=REMINDER_DOCUMENTS, contact=accountant,
        )

        messages = self.messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["recipient"]["contact_id"], accountant.pk)

    def test_the_body_is_rendered_in_the_recipients_language(self):
        client, contact = self.ready_client()
        self.assertIn("ناقصنا منك", self.messages()[0]["body"])

        contact.language = "he"
        contact.save(update_fields=["language"])

        body = self.messages()[0]["body"]
        self.assertIn("חסרים לנו", body)
        self.assertNotIn("ناقصنا منك", body)

    def test_an_office_override_replaces_the_body_of_the_message(self):
        client, contact = self.ready_client()
        services.set_reminder_template(
            self.tenant,
            reminder_type=REMINDER_DOCUMENTS,
            language="ar",
            body="{client_name}: بدنا {missing_list}",
            actor=self.owner,
        )

        self.assertEqual(self.messages()[0]["body"], "زبون التذكير: بدنا فاتورة مشتريات")

    def test_a_contact_without_a_phone_still_appears(self):
        client, contact = self.ready_client()
        contact.phone = ""
        contact.save(update_fields=["phone"])

        messages = self.messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["recipient"]["phone"], "")
        self.assertFalse(messages[0]["recipient"]["has_phone"])

    def test_merging_off_gives_one_message_per_item(self):
        services.set_office_setting(self.tenant, services.REMINDER_MERGE_DAILY_KEY, False)
        shared = self.make_contact(name="أبو أحمد")
        self.ready_client("محل أول", contact=shared)
        self.ready_client("محل ثانٍ", contact=shared)

        messages = self.messages()

        self.assertEqual(len(messages), 2)
        for message in messages:
            self.assertEqual(len(message["items"]), 1)

    def test_an_ended_client_is_not_listed(self):
        client, contact = self.ready_client()
        client.status = OfficeClient.STATUS_ENDED
        client.ended_on = FEB_FIRST
        client.save(update_fields=["status", "ended_on"])

        self.assertEqual(self.messages(), [])

    def test_the_assignee_filter_keeps_the_responsibles_clients_only(self):
        other = self.make_member("rem_other")
        mine, _contact = self.ready_client("محلي")
        theirs, contact = self.ready_client("زبون غيري", responsible=other)

        messages = self.messages(assignee=self.owner.pk)

        listed = {
            item["client_id"] for message in messages for item in message["items"]
        }
        self.assertEqual(listed, {mine.pk})

    def test_a_client_of_another_office_is_never_listed(self):
        other_owner = User.objects.create_user(username="rem_foreign", password="x")
        other = create_company("مكتب آخر", other_owner, template="accounting_office")
        invalidate_module_cache(other.pk)
        ready_office(other, "IL")
        foreign = OfficeClient.objects.create(
            tenant=other, name="زبون مكتبٍ آخر", responsible=other_owner,
        )
        DocumentChecklistItem.objects.create(
            tenant=other, client=foreign, item_code="probe_0", name="ورقة",
            cadence="monthly", period_start=JAN_START, period_end=JAN_END,
            status=DOCUMENT_STATUS_REQUIRED,
        )

        listed = {
            item["client_id"]
            for message in self.messages() for item in message["items"]
        }
        self.assertNotIn(foreign.pk, listed)

    def test_the_type_filter_offers_nothing_for_a_client_without_that_item(self):
        """الفلترُ لا يبتكر بنوداً: زبونٌ بأوراقٍ ناقصةٍ فقط لا بندَ «اللي عليه» له.

        (كان اسمُ هذا الاختبار «قبل أن يصير للنوع مولّد» — وقد صار له مولّدُ
        فواتير الأتعاب؛ وبقاءُ الاسم يوصف به سلوكٌ استُبدل.)
        """
        self.ready_client()
        self.assertEqual(self.messages(reminder_type=REMINDER_BALANCE), [])
        self.assertEqual(self.messages(reminder_type=REMINDER_DOCUMENTS), self.messages())

    def test_the_balance_filter_shows_the_fee_invoice_item(self):
        """نوعُ «اللي عليه» له مولّدٌ: فاتورةُ أتعابٍ صادرةٌ تظهر ببندها ومبلغها."""
        client, _contact = self.ready_client()
        draft = FeeDraft.objects.create(
            tenant=self.tenant,
            client=client,
            year=2026,
            month=1,
            subtotal=Decimal("300.00"),
            total=Decimal("300.00"),
            status=FeeDraft.STATUS_APPROVED,
            generated_at=timezone.make_aware(
                datetime.datetime(2026, 1, 31, 12, 0),
            ),
        )
        FeeDraftLine.objects.create(
            tenant=self.tenant, draft=draft, label="الاشتراك الشهري",
            amount=Decimal("300.00"), source="subscription",
        )
        invoice = fee_invoices.issue_for_draft(draft, actor=self.owner, day=JAN_END)

        items = [
            item
            for message in self.messages(reminder_type=REMINDER_BALANCE)
            for item in message["items"]
        ]

        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["client_id"], client.pk)
        self.assertEqual(items[0]["reminder_type"], REMINDER_BALANCE)
        self.assertEqual(items[0]["invoice"]["number"], invoice.number)
        self.assertEqual(
            Decimal(items[0]["invoice"]["total"]), Decimal(invoice.total),
        )


# ── الحجب (#280/D5، D8) ──────────────────────────────────────────────────────
class BlocksTest(RemindersTestCase):
    def test_the_clients_rest_day_hides_it_and_the_next_day_shows_it(self):
        client, contact = self.ready_client()
        services.set_client_setting(client, "rest_days", ["sun"])

        self.assertEqual(self.messages(FEB_FIRST), [])
        self.assertEqual(len(self.messages(FEB_SECOND)), 1)

    def test_the_body_names_the_next_reminder_day_not_a_past_one(self):
        """`{due_date}` يومٌ قادمٌ لا يومُ الاستحقاق المحسوب (وهو اليوم أو قبله).

        بعد يوم راحةٍ صار `next_due` في الماضي، وطبعتُه في الرسالة تطلب ورقةً
        بتاريخٍ مضى — فيُطبَع `day + interval_days` بصيغة `dd/MM/yyyy`.
        """
        client, contact = self.ready_client()
        services.set_client_setting(client, "rest_days", ["sun"])

        self.assertEqual(self.messages(FEB_FIRST), [])
        body = self.messages(FEB_SECOND)[0]["body"]

        upcoming = FEB_SECOND + datetime.timedelta(days=3)
        self.assertIn(upcoming.strftime("%d/%m/%Y"), body)
        self.assertNotIn(FEB_FIRST.strftime("%d/%m/%Y"), body)

    def test_the_office_rest_day_blocks_on_its_default(self):
        self.ready_client()

        self.assertEqual(self.messages(FRIDAY), [])
        self.assertEqual(len(self.messages(FEB_SEVENTH)), 1)

    def test_an_office_holiday_blocks_the_whole_day(self):
        self.ready_client()
        OfficeHoliday.objects.create(
            tenant=self.tenant, date=FEB_FIRST, name="عيد المكتب",
        )

        self.assertEqual(self.messages(FEB_FIRST), [])
        self.assertEqual(len(self.messages(FEB_SECOND)), 1)

    def test_a_postponement_hides_the_pair_until_its_date(self):
        client, contact = self.ready_client()

        services.postpone_reminder(
            self.tenant,
            user=self.owner,
            day=FEB_FIRST,
            client_id=client.pk,
            reminder_type=REMINDER_DOCUMENTS,
            until=FEB_FIFTH,
            reason="مسافر",
        )

        self.assertEqual(self.messages(FEB_FOURTH), [])
        self.assertEqual(len(self.messages(FEB_FIFTH)), 1)
        self.assertEqual(ReminderPostpone.objects.filter(client=client).count(), 1)

    def test_a_postponement_with_no_date_clears_the_hiding(self):
        client, contact = self.ready_client()
        services.postpone_reminder(
            self.tenant, user=self.owner, day=FEB_FIRST,
            client_id=client.pk, reminder_type=REMINDER_DOCUMENTS, until=FEB_FIFTH,
        )
        services.postpone_reminder(
            self.tenant, user=self.owner, day=FEB_FIRST,
            client_id=client.pk, reminder_type=REMINDER_DOCUMENTS, until=None,
        )

        self.assertEqual(len(self.messages(FEB_FIRST)), 1)

    def test_a_postponement_date_must_be_after_today(self):
        client, contact = self.ready_client()
        with self.assertRaises(DjangoValidationError):
            services.postpone_reminder(
                self.tenant, user=self.owner, day=FEB_FIRST,
                client_id=client.pk, reminder_type=REMINDER_DOCUMENTS,
                until=FEB_FIRST,
            )


# ── التصعيد (#280/D11) ───────────────────────────────────────────────────────
class EscalationTest(RemindersTestCase):
    def reach_the_limit(self):
        client, contact = self.ready_client()
        self.send(client, day=FEB_FIRST, contact=contact)
        self.send(client, day=FEB_FOURTH, contact=contact)
        self.send(client, day=FEB_SEVENTH, contact=contact)
        return client

    def test_the_responsible_is_alerted_on_the_day_the_next_reminder_was_due(self):
        client = self.reach_the_limit()

        services.refresh_office(self.tenant, day=FEB_TENTH)

        alert = OfficeAlert.objects.get(
            kind=OFFICE_ALERT_KIND_REMINDER_LIMIT, client=client,
        )
        self.assertEqual(alert.recipient_id, self.owner.pk)
        self.assertIn(client.name, alert.message)
        self.assertIn("كانون الثاني 2026", alert.message)
        self.assertIn("3 تذكيرات", alert.message)

    def test_the_owner_is_alerted_two_days_after_the_responsible(self):
        client = self.reach_the_limit()
        services.refresh_office(self.tenant, day=FEB_TENTH)
        self.assertFalse(
            OfficeAlert.objects.filter(kind=OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER).exists(),
        )

        services.refresh_office(self.tenant, day=FEB_TWELFTH)

        alert = OfficeAlert.objects.get(
            kind=OFFICE_ALERT_KIND_REMINDER_LIMIT_OWNER, client=client,
        )
        self.assertEqual(alert.recipient_id, self.owner.pk)

    def test_nothing_escalates_before_the_interval_passes(self):
        client = self.reach_the_limit()

        services.refresh_office(self.tenant, day=FEB_SEVENTH)

        self.assertFalse(OfficeAlert.objects.filter(client=client).exists())

    def test_the_alert_is_generated_once_per_day_and_not_twice(self):
        client = self.reach_the_limit()
        services.refresh_office(self.tenant, day=FEB_TENTH)
        services.refresh_office(self.tenant, day=FEB_TENTH)

        self.assertEqual(
            OfficeAlert.objects.filter(
                kind=OFFICE_ALERT_KIND_REMINDER_LIMIT, client=client,
            ).count(),
            1,
        )

    def test_a_month_and_the_year_that_begin_on_the_same_day_alert_twice(self):
        """الفترةُ السنوية تبدأ في 1 كانون الثاني كالشهرية — والمفتاحُ يحمل النهايتين.

        بمفتاحٍ على بداية الفترة وحدها يتساوى المرءُ فيرى تنبيهاً واحداً،
        ويختفي الآخرُ من الجرس بلا أن يُقرأ.
        """
        client, contact = self.ready_client()
        self.add_missing(client, period_start=YEAR_START, period_end=YEAR_END)
        for day in (FEB_FIRST, FEB_FOURTH, FEB_SEVENTH):
            self.send(client, day=day, contact=contact)
            self.send(
                client, day=day, contact=contact,
                period_start=YEAR_START, period_end=YEAR_END,
            )

        services.refresh_office(self.tenant, day=FEB_TENTH)

        self.assertEqual(
            OfficeAlert.objects.filter(
                kind=OFFICE_ALERT_KIND_REMINDER_LIMIT, client=client,
            ).count(),
            2,
        )

    def test_completing_the_papers_drops_the_alert_at_read_time(self):
        client = self.reach_the_limit()
        services.refresh_office(self.tenant, day=FEB_TENTH)
        self.assertEqual(
            len(self.messages(FEB_TENTH)), 0,
        )
        self.assertIn(
            OFFICE_ALERT_KIND_REMINDER_LIMIT,
            [
                row["kind"]
                for row in services.alerts_payload(
                    self.tenant, user=self.owner, day=FEB_TENTH,
                )["rows"]
            ],
        )

        DocumentChecklistItem.objects.filter(client=client).update(
            status=DOCUMENT_STATUS_RECEIVED,
        )

        rows = services.alerts_payload(self.tenant, user=self.owner, day=FEB_TENTH)["rows"]
        self.assertEqual(
            [row["kind"] for row in rows if row["kind"] == OFFICE_ALERT_KIND_REMINDER_LIMIT],
            [],
        )

    def test_the_bell_only_scans_the_clients_that_hold_a_reminder_alert(self):
        """بلا تنبيهِ تذكيرٍ قائم لا تُقرأ فتراتُ الأوراق — الكلفةُ لا تكبر بالزبائن."""
        self.ready_client()

        self.assertEqual(services._live_reminder_alert_refs(self.tenant), set())

    def test_the_alert_opens_the_clients_documents_tab(self):
        client = self.reach_the_limit()
        services.refresh_office(self.tenant, day=FEB_TENTH)

        row = next(
            item for item in
            services.alerts_payload(self.tenant, user=self.owner, day=FEB_TENTH)["rows"]
            if item["kind"] == OFFICE_ALERT_KIND_REMINDER_LIMIT
        )
        self.assertEqual(row["opens"], "client_documents")


# ── الكلفة والعزل ────────────────────────────────────────────────────────────
class CostTest(RemindersTestCase):
    def test_the_ready_list_costs_the_same_for_one_client_and_for_five(self):
        self.ready_client()
        with CaptureQueriesContext(connection) as one:
            services.ready_to_send_payload(self.tenant, user=self.owner, day=FEB_FIRST)

        for index in range(4):
            self.ready_client(f"زبون {index}")
        with CaptureQueriesContext(connection) as five:
            payload = services.ready_to_send_payload(
                self.tenant, user=self.owner, day=FEB_FIRST,
            )

        self.assertEqual(len(payload["messages"]), 5)
        self.assertEqual(
            len(one.captured_queries), len(five.captured_queries),
            [query["sql"] for query in five.captured_queries],
        )

    def test_a_dismissal_of_many_items_is_one_metadata_query_and_one_insert(self):
        """تنحيةُ ثلاثة بنودٍ استعلامُ بياناتٍ واحد و`bulk_create` واحد — لا ثلاثة."""
        pairs = [self.ready_client(f"زبون {index}") for index in range(3)]
        items = [
            {
                "client_id": client.pk,
                "reminder_type": REMINDER_DOCUMENTS,
                "period_start": JAN_START.isoformat(),
                "period_end": JAN_END.isoformat(),
            }
            for client, _contact in pairs
        ]

        with CaptureQueriesContext(connection) as captured:
            rows = services.dismiss_reminders(self.tenant, user=self.owner, items=items)

        self.assertEqual(len(rows), 3)
        inserts = [
            query["sql"] for query in captured.captured_queries
            if query["sql"].lstrip().upper().startswith("INSERT")
        ]
        metadata = [
            query["sql"] for query in captured.captured_queries
            if DocumentChecklistItem._meta.db_table in query["sql"]
        ]
        self.assertEqual(len(inserts), 1, inserts)
        self.assertEqual(len(metadata), 1, metadata)


class SettingsBatchTest(RemindersTestCase):
    """`resolve_settings_for_clients` — مفاتيحُ مجموعةٍ في مسحةٍ واحدةٍ بحارسي المحلّل."""

    def test_the_payload_resolves_the_reminder_settings_once(self):
        """«جاهز للإرسال» يقرأ الإعدادات مرّةً واحدةً لا في الحساب وفي الحمولة."""
        self.ready_client()
        calls = []
        original = services.resolve_settings_for_clients

        def counted(tenant, keys, clients):
            calls.append(tuple(keys))
            return original(tenant, keys, clients)

        with mock.patch.object(services, "resolve_settings_for_clients", counted):
            messages = self.messages()

        self.assertEqual(len(messages), 1, messages)
        self.assertEqual(len(calls), 1, calls)

    def test_it_matches_the_single_key_resolver_and_takes_the_client_override(self):
        client, _contact = self.ready_client()
        services.set_client_setting(client, "rest_days", ["sun"])
        services.set_client_setting(
            client, services.DOCUMENTS_REMINDER_INTERVAL_DAYS_KEY, 5,
        )

        resolved = services.resolve_settings_for_clients(
            self.tenant,
            [services.DOCUMENTS_REMINDER_INTERVAL_DAYS_KEY, "rest_days"],
            [client],
        )

        self.assertEqual(resolved[client.pk]["rest_days"], ["sun"])
        self.assertEqual(
            resolved[client.pk][services.DOCUMENTS_REMINDER_INTERVAL_DAYS_KEY], 5,
        )
        self.assertEqual(
            resolved[client.pk]["rest_days"],
            services.resolve_setting_for_clients(
                self.tenant, "rest_days", [client],
            )[client.pk],
        )

    def test_a_client_of_another_office_or_an_office_only_key_is_refused(self):
        client, _contact = self.ready_client()
        other_owner = User.objects.create_user(username="rem_batch_foreign", password="x")
        other = create_company("مكتب رابع", other_owner, template="accounting_office")
        invalidate_module_cache(other.pk)
        stranger = OfficeClient.objects.create(
            tenant=other, name="زبون مكتبٍ رابع", responsible=other_owner,
        )

        with self.assertRaises(DjangoValidationError):
            services.resolve_settings_for_clients(
                self.tenant, ["rest_days"], [client, stranger],
            )
        with self.assertRaises(DjangoValidationError):
            services.resolve_settings_for_clients(self.tenant, ["office_size"], [client])


class LogShapeTest(RemindersTestCase):
    def test_a_sent_row_is_whatsapp_only_and_a_blank_channel_means_whatsapp(self):
        """`sent` قناةٌ واحدة: «انبعثت» واتساب، و«تلفون» ليس إرسالاً بالتطبيق."""
        client, contact = self.ready_client()
        payload = {
            "contact_id": contact.pk,
            "body": "نص",
            "items": [{
                "client_id": client.pk,
                "reminder_type": REMINDER_DOCUMENTS,
                "period_start": JAN_START.isoformat(),
                "period_end": JAN_END.isoformat(),
            }],
        }

        for channel in ("phone", "in_person", "carrier-pigeon"):
            with self.subTest(channel=channel):
                with self.assertRaises(DjangoValidationError) as caught:
                    services.mark_reminders_sent(
                        self.tenant, user=self.owner, channel=channel, **payload,
                    )
                self.assertIn("channel", caught.exception.message_dict)

        self.assertFalse(ReminderLog.objects.exists())

        rows = services.mark_reminders_sent(self.tenant, user=self.owner, **payload)
        self.assertEqual(rows[0].channel, REMINDER_CHANNEL_WHATSAPP)

    def test_a_sent_row_without_a_body_is_refused(self):
        """السجلُّ لا يُمحى: «انبعثت» بلا نصٍّ تسجّل رسالةً لم تُكتب أصلاً."""
        client, contact = self.ready_client()
        for body in ("", "   ", None):
            with self.subTest(body=body):
                with self.assertRaises(DjangoValidationError) as caught:
                    services.mark_reminders_sent(
                        self.tenant, user=self.owner, contact_id=contact.pk,
                        body=body,
                        items=[{
                            "client_id": client.pk,
                            "reminder_type": REMINDER_DOCUMENTS,
                            "period_start": JAN_START.isoformat(),
                            "period_end": JAN_END.isoformat(),
                        }],
                    )
                self.assertIn("body", caught.exception.message_dict)

        self.assertFalse(ReminderLog.objects.exists())

    def test_the_log_row_carries_the_snapshots_of_the_person_at_send_time(self):
        client, contact = self.ready_client()
        sent = self.send(client, day=FEB_FIRST, contact=contact)[0]

        self.assertEqual(sent.recipient_name, "أبو أحمد")
        self.assertEqual(sent.recipient_phone, "0599123456")
        self.assertEqual(sent.period_start, JAN_START)
        self.assertEqual(sent.period_end, JAN_END)
        self.assertEqual(sent.kind, ReminderLog.KIND_SENT)
        self.assertEqual(sent.channel, ReminderLog.CHANNEL_WHATSAPP)
        self.assertEqual(sent.subject["document_item_codes"], ["probe_0"])
        self.assertEqual(sent.created_by_id, self.owner.pk)

        contact.name = "اسمٌ آخر"
        contact.save(update_fields=["name"])
        sent.refresh_from_db()
        self.assertEqual(sent.recipient_name, "أبو أحمد")

    def test_the_clients_log_is_newest_first(self):
        client, contact = self.ready_client()
        self.send(client, day=FEB_FIRST, contact=contact)
        self.send(client, day=FEB_FOURTH, contact=contact)

        payload = services.client_reminder_log_payload(client)
        rows = payload["rows"]

        self.assertEqual([row["kind"] for row in rows], ["sent", "sent"])
        self.assertEqual(rows[0]["period_label"], "كانون الثاني 2026")
        self.assertEqual(rows[0]["recipient_name"], "أبو أحمد")

    def test_a_body_or_contact_from_another_office_is_refused(self):
        client, contact = self.ready_client()
        other_owner = User.objects.create_user(username="rem_api_foreign", password="x")
        other = create_company("مكتب ثالث", other_owner, template="accounting_office")
        invalidate_module_cache(other.pk)
        stranger = Contact.objects.create(tenant=other, name="غريب", phone="0599")

        with self.assertRaises(DjangoValidationError):
            services.mark_reminders_sent(
                self.tenant, user=self.owner,
                contact_id=stranger.pk, body="نص",
                items=[{
                    "client_id": client.pk, "reminder_type": REMINDER_DOCUMENTS,
                    "period_start": JAN_START.isoformat(),
                    "period_end": JAN_END.isoformat(),
                }],
            )

    def test_a_client_outside_the_users_visibility_is_refused(self):
        other = self.make_member("rem_other_owner")
        foreign_client, contact = self.ready_client(
            "زبون موظّفٍ آخر", responsible=other,
        )
        accountant = self.make_member("rem_accountant")

        with self.assertRaises(DjangoValidationError):
            services.dismiss_reminders(
                self.tenant, user=accountant,
                items=[{
                    "client_id": foreign_client.pk, "reminder_type": REMINDER_DOCUMENTS,
                    "period_start": JAN_START.isoformat(),
                    "period_end": JAN_END.isoformat(),
                }],
            )
