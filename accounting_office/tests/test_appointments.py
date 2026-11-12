"""المواعيد مع الزبون وتذكيرا الموعد والموعد الرسميّ القريب — #281.

**ما يثبته هذا الملف:**

1. **الموعدُ حجزُ موظّفٍ بتاريخه ووقته** (`scheduled_at` لحظةٌ لا تاريخ)، وحالاته
   الثلاث (`scheduled`/`done`/`cancelled`) — **ولا حذف**: الإلغاءُ يكتب حالة.
2. **«تأكيدُ الموعد» رسالةُ تذكيرٍ بالسجلّ القائم** (`ReminderLog` بنوع `appointment`)،
   ويُختم `confirmed_at` حين تُسجَّل — لا جدولَ رسائلٍ ثانٍ.
3. **«هل على الزبون شيء؟» دالّةٌ نقيّة**: أوراقٌ ناقصةٌ ⇒ نعم، مبلغٌ غيرُ مدفوعٍ ⇒
   نعم، أوراقٌ كاملةٌ بلا مبلغٍ ⇒ لا، «انقدّم» ⇒ لا.
4. **مولّد «موعد رسمي قريب»** يظهر قبل **7 أيام** وقبل **يومين** من آخر موعدٍ فعليّ
   (`Obligation.due_date`: الممدَّدُ أو الفعليّ) — **لا محرّكاً موازياً**، وبالشرط
   الحاسم وحده.
5. **مولّد «تذكير موعد»** يظهر قبل الموعد بعددِ الأيام المضبوط (إعدادُ المكتب
   ويُخصَّص للزبون)، ولا موعدَ ملغىً ولا موعدَ بعد أن مضى.
6. **التوقّفُ عند الحاجز**: نوعٌ مطفأ في `reminder_types_enabled` لا يظهر، وتأجيلٌ
   يحجب، والحدُّ الأقصى يوقف بعد العددين.
7. **«اليوم» و«التقويم» يحملان المواعيد**: عدّادٌ في `counters` وقسمٌ في الحمولة.
8. **العزلُ والصلاحية**: زبونُ غيرك **404**، والكتابةُ بمفتاح `office.clients.write`.

**والترتيبُ لا الانتظار**: التواريخُ تُمرَّر صريحةً إلى كل دالّة، فلا ساعةَ تُنتظر
ولا `sleep` — ما يُفحص هو ترتيبُ الأحداث (إنشاءٌ ← تأكيدٌ ← إلغاء).
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import appointments, services
from accounting_office.models import (
    APPOINTMENT_KIND_CALL,
    APPOINTMENT_KIND_VISIT,
    APPOINTMENT_STATUS_CANCELLED,
    APPOINTMENT_STATUS_DONE,
    APPOINTMENT_STATUS_SCHEDULED,
    DOCUMENT_STATUS_REQUIRED,
    DeadlineRule,
    OBLIGATION_DIRECTION_DUE,
    OBLIGATION_DIRECTION_REFUND,
    OBLIGATION_STATUS_NOT_REQUIRED,
    OBLIGATION_STATUS_PENDING,
    OBLIGATION_STATUS_SUBMITTED,
    REMINDER_APPOINTMENT,
    REMINDER_DEADLINE,
    REMINDER_DOCUMENTS,
    ClientAppointment,
    Contact,
    DocumentChecklistItem,
    OfficeClient,
    Obligation,
    PeriodTask,
    ReminderLog,
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
APPOINTMENTS = f"{BASE}appointments/"

#: كانون الثاني 2026 فترتُ الالتزام، وشباط يومُ الحساب.
#: 1 شباط 2026 **أحد** — لا يومَ راحةٍ افتراضياً (الجمعة 6 شباط).
JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
DAY = datetime.date(2026, 2, 1)           # الأحد — يومُ الحساب
BEFORE_DAY = datetime.date(2026, 1, 30)   # قبل الموعد بيومين
#: موعدٌ رسميٌّ في 10 شباط: أوّلُ تذكيرٍ قبل سبعة أيام (3 شباط)، والثاني قبل
#: يومين (8 شباط) — لا يومٌ منهما جمعة.
DUE = datetime.date(2026, 2, 10)
SEVEN_DAYS_BEFORE = datetime.date(2026, 2, 3)
TWO_DAYS_BEFORE = datetime.date(2026, 2, 8)
TWO_DAYS_BEFORE_EVE = datetime.date(2026, 2, 7)


def at(day, hour=10, minute=30):
    """لحظةٌ واعيةٌ في يومٍ صريح — الموعدُ وقتٌ لا تاريخ."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, minute)))


def at_log(row, day):
    """يُثبّت **يومَ** صفِّ السجلّ — `auto_now_add` يكتب لحظةَ الاختبار لا يومَه.

    ونافذةُ #281 تُقاس بأيام الصفوف لا بعدّها، فصفٌّ بتاريخ ساعة الاختبار لا يقع
    في نافذةِ يومٍ محسوبٍ في شباط 2026. النمطُ نفسُه في `at` بـ`test_reminders.py`.
    """
    stamp = datetime.datetime.combine(day, datetime.time(12, 0))
    ReminderLog.objects.filter(pk=row.pk).update(created_at=timezone.make_aware(stamp))
    return row


class OfficeFixture(TestCase):
    """مكتبٌ جاهزٌ (نظامٌ ضريبيٌّ وحجم)، وزبونٌ ببطاقته وجهته الرئيسية."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="ap_owner", password="x")
        cls.tenant = create_company(
            "مكتب المواعيد", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

    def make_member(self, username, *, role="accountant"):
        user = User.objects.create_user(username=username, password="x")
        UserCompanyMembership.objects.create(user=user, tenant=self.tenant, role=role)
        return user

    def make_client(self, name="زبون المواعيد", *, responsible=None, **card):
        client = OfficeClient.objects.create(
            tenant=self.tenant, name=name, responsible=responsible or self.owner,
        )
        fields = {"annual_sales": 0, "vat_classification": "authorized"}
        fields.update(card)
        TaxCard.objects.create(client=client, **fields)
        return client

    def make_contact(self, name="أبو أحمد", *, phone="0599123456", language="ar", **extra):
        return Contact.objects.create(
            tenant=self.tenant, name=name, phone=phone, language=language, **extra,
        )

    def link(self, client, contact):
        services.link_client_contact(client=client, contact=contact, is_primary=True)
        return contact

    def ready_client(self, name="زبون المواعيد"):
        """زبونٌ بجهةٍ رئيسيةٍ مربوطة — مستلِمُ كلّ تذكيره افتراضاً."""
        client = self.make_client(name)
        self.link(client, self.make_contact())
        return client

    def add_missing(self, client, *, names=("فاتورة مشتريات",), period_start=JAN_START,
                    period_end=JAN_END, status=DOCUMENT_STATUS_REQUIRED):
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

    def add_obligation(
        self, client, *, actual=DUE, status=OBLIGATION_STATUS_PENDING,
        amount=None, client_paid=False, direction="",
        period_start=JAN_START, period_end=JAN_END, service_code="vat",
    ):
        """التزامٌ محفوظٌ بتاريخه الصريح — لا ساعةَ ولا محرّكَ تحديث.

        **و`service_code` للالتزام الثاني في الفترة نفسها**: خدمةٌ تتداخل مع خدمةٍ
        قائمةٍ للزبون تُرفض، فالتزامان في فترةٍ واحدة يحتاجان خدمتين.
        """
        service = services.add_client_service(
            client=client, service=self.catalog[service_code],
            starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
        )
        task = PeriodTask.objects.create(
            tenant=self.tenant,
            client=client,
            client_service=service,
            period_start=period_start,
            period_end=period_end,
            internal_deadline=actual,
        )
        return Obligation.objects.create(
            tenant=self.tenant,
            client=client,
            client_service=service,
            task=task,
            rule=DeadlineRule.objects.filter(
                schedule__tax_system="IL", schedule__year=2026,
                code="il_vat_periodic",
            ).first(),
            rule_code="il_vat_periodic",
            name="דוח תקופתי",
            period_start=period_start,
            period_end=period_end,
            legal_date=actual,
            official_date=actual,
            actual_deadline=actual,
            internal_deadline=actual,
            status=status,
            amount=amount,
            client_paid=client_paid,
            direction=direction,
        )

    def ready(self, day=DAY, **kwargs):
        return services.ready_to_send_payload(
            self.tenant, user=self.owner, day=day, **kwargs,
        )

    def items(self, day=DAY, reminder_type=None):
        payload = self.ready(day, reminder_type=reminder_type)
        return [item for message in payload["messages"] for item in message["items"]]


# ── د6: دالّةُ «هل على الزبون شيء؟» — نقيّةٌ ومفردة ─────────────────────────────
class ClientOwesTest(SimpleTestCase):
    """الحالاتُ الأربعُ المحسومة، بلا قاعدة بيانات: دالّةٌ نقيّةٌ تُفحص وحدها."""

    def test_whole_papers_and_no_amount_is_nothing_owed(self):
        self.assertFalse(appointments.client_owes(
            status=OBLIGATION_STATUS_PENDING, missing=(), amount=None, client_paid=False,
        ))

    def test_whole_papers_with_an_unpaid_amount_is_owed(self):
        self.assertTrue(appointments.client_owes(
            status=OBLIGATION_STATUS_PENDING,
            missing=(),
            amount=Decimal("620.00"),
            client_paid=False,
        ))

    def test_missing_papers_alone_are_owed(self):
        self.assertTrue(appointments.client_owes(
            status=OBLIGATION_STATUS_PENDING,
            missing=("فاتورة مشتريات",),
            amount=None,
            client_paid=False,
        ))

    def test_a_submitted_obligation_owes_nothing_whatever_the_papers(self):
        self.assertFalse(appointments.client_owes(
            status=OBLIGATION_STATUS_SUBMITTED,
            missing=("فاتورة مشتريات",),
            amount=Decimal("620.00"),
            client_paid=False,
        ))

    def test_a_not_required_obligation_owes_nothing_either(self):
        self.assertFalse(appointments.client_owes(
            status=OBLIGATION_STATUS_NOT_REQUIRED,
            missing=("فاتورة مشتريات",),
            amount=Decimal("620.00"),
            client_paid=False,
        ))

    def test_a_paid_amount_is_not_owed_and_a_refund_is_on_us_not_on_the_client(self):
        self.assertFalse(appointments.client_owes(
            status=OBLIGATION_STATUS_PENDING, missing=(),
            amount=Decimal("620.00"), client_paid=True,
        ))
        self.assertFalse(appointments.client_owes(
            status=OBLIGATION_STATUS_PENDING, missing=(),
            amount=Decimal("620.00"), client_paid=False,
            direction=OBLIGATION_DIRECTION_REFUND,
        ))
        self.assertTrue(appointments.client_owes(
            status=OBLIGATION_STATUS_PENDING, missing=(),
            amount=Decimal("620.00"), client_paid=False,
            direction=OBLIGATION_DIRECTION_DUE,
        ))


# ── الموعدُ نفسه (د1، د4) ─────────────────────────────────────────────────────
class AppointmentLifecycleTest(OfficeFixture):
    def test_a_new_appointment_is_scheduled_with_its_kind_and_its_time(self):
        client = self.ready_client()

        row = appointments.create_appointment(
            self.tenant,
            user=self.owner,
            client_id=client.pk,
            kind=APPOINTMENT_KIND_CALL,
            scheduled_at=at(DAY, 9, 15),
            note="تلفون عن أوراق كانون الثاني",
        )

        stored = ClientAppointment.objects.get(pk=row["id"])
        self.assertEqual(stored.tenant_id, self.tenant.pk)
        self.assertEqual(stored.client_id, client.pk)
        self.assertEqual(stored.kind, APPOINTMENT_KIND_CALL)
        self.assertEqual(
            timezone.localtime(stored.scheduled_at),
            timezone.localtime(at(DAY, 9, 15)),
        )
        self.assertEqual(stored.status, APPOINTMENT_STATUS_SCHEDULED)
        self.assertEqual(stored.created_by_id, self.owner.pk)
        self.assertEqual(row["time"], "09:15")
        self.assertEqual(row["day"], DAY.isoformat())

    def test_the_kind_is_one_of_the_four_and_anything_else_is_refused(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
        )
        self.assertEqual(row["kind_label"], "زيارة")

        with self.assertRaises(DjangoValidationError) as caught:
            appointments.create_appointment(
                self.tenant, user=self.owner, client_id=client.pk,
                kind="lunch", scheduled_at=at(DAY),
            )
        self.assertIn("lunch", str(caught.exception))

    def test_a_client_of_another_office_is_not_visible_so_the_create_is_refused(self):
        outside_owner = User.objects.create_user(username="ap_outside", password="x")
        outside = create_company("مكتب آخر", outside_owner, template="accounting_office")
        outside_client = OfficeClient.objects.create(
            tenant=outside, name="زبون غيري", responsible=outside_owner,
        )

        with self.assertRaises(services.ReminderClientNotVisible):
            appointments.create_appointment(
                self.tenant, user=self.owner, client_id=outside_client.pk,
                kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
            )

    def test_cancelling_writes_the_status_and_never_deletes_the_row(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
        )

        cancelled = appointments.cancel_appointment(
            ClientAppointment.objects.get(pk=row["id"]), actor=self.owner,
        )

        stored = ClientAppointment.objects.get(pk=row["id"])
        self.assertEqual(stored.status, APPOINTMENT_STATUS_CANCELLED)
        self.assertEqual(cancelled["status"], APPOINTMENT_STATUS_CANCELLED)
        self.assertEqual(cancelled["status_label"], "ملغى")
        self.assertIsNotNone(stored.cancelled_at)

    def test_a_cancelled_appointment_is_neither_rescheduled_nor_confirmed(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
        )
        stored = ClientAppointment.objects.get(pk=row["id"])
        appointments.cancel_appointment(stored, actor=self.owner)
        stored.refresh_from_db()

        with self.assertRaises(DjangoValidationError):
            appointments.reschedule_appointment(stored, scheduled_at=at(DAY, 12), actor=self.owner)
        with self.assertRaises(DjangoValidationError):
            appointments.send_appointment_confirmation(self.tenant, stored, actor=self.owner)

    def test_rescheduling_moves_the_time_and_keeps_the_row_numbered_once(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY, 10, 0),
        )
        stored = ClientAppointment.objects.get(pk=row["id"])

        moved = appointments.reschedule_appointment(
            stored, scheduled_at=at(DAY, 13, 45), actor=self.owner,
        )

        self.assertEqual(ClientAppointment.objects.filter(pk=row["id"]).count(), 1)
        self.assertEqual(moved["time"], "13:45")
        self.assertEqual(moved["id"], row["id"])

    def test_rescheduling_clears_the_confirmation_so_it_can_be_confirmed_again(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY, 10, 0),
        )
        stored = ClientAppointment.objects.get(pk=row["id"])
        confirmed = appointments.send_appointment_confirmation(
            self.tenant, stored, actor=self.owner,
        )
        self.assertIsNotNone(confirmed["appointment"]["confirmed_at"])
        stored.refresh_from_db()

        moved = appointments.reschedule_appointment(
            stored, scheduled_at=at(DAY + datetime.timedelta(days=1), 9, 0),
            actor=self.owner,
        )

        # الموعدُ صار وقتاً آخر: تأكيدُه القديمُ لم يعد تأكيداً له، والتقويمُ يخفي
        # زرَّ «ابعت تأكيد» متى وُجد `confirmed_at`.
        self.assertIsNone(moved["confirmed_at"])
        self.assertIsNone(ClientAppointment.objects.get(pk=row["id"]).confirmed_at)

    def test_the_confirmation_body_names_absent_values_in_the_recipients_language(self):
        absent = {"ar": "ولا شي", "he": "אין"}
        for language in ("ar", "he"):
            with self.subTest(language=language):
                client = self.make_client(f"زبون {language}")
                self.link(client, self.make_contact(
                    name=f"جهة {language}", language=language,
                ))
                # قالبُ مكتبٍ يقرأ الرموزَ التي لا يحملها الموعد.
                services.set_reminder_template(
                    self.tenant, reminder_type=REMINDER_APPOINTMENT, language=language,
                    body="{period}|{amount}|{missing_list}", actor=self.owner,
                )
                row = appointments.create_appointment(
                    self.tenant, user=self.owner, client_id=client.pk,
                    kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
                )

                sent = appointments.send_appointment_confirmation(
                    self.tenant, ClientAppointment.objects.get(pk=row["id"]),
                    actor=self.owner,
                )

                # عُرفٌ واحدٌ لقيمة الغياب مع تذكير الموعد الرسميّ — لا فراغ هنا و«لا شيء» هناك.
                self.assertEqual(sent["body"], "|".join([absent[language]] * 3))

    def test_marking_it_done_keeps_the_time_and_moves_only_the_status(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
        )
        stored = ClientAppointment.objects.get(pk=row["id"])

        done = appointments.complete_appointment(stored, actor=self.owner)

        self.assertEqual(done["status"], APPOINTMENT_STATUS_DONE)
        self.assertEqual(done["time"], "10:30")

    def test_the_confirmation_is_a_reminder_log_row_and_stamps_the_confirmed_at(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
        )
        stored = ClientAppointment.objects.get(pk=row["id"])

        sent = appointments.send_appointment_confirmation(self.tenant, stored, actor=self.owner)

        stored.refresh_from_db()
        logs = ReminderLog.objects.filter(
            tenant=self.tenant, client=client, reminder_type=REMINDER_APPOINTMENT,
        )
        self.assertEqual(logs.count(), 1)
        log = logs.get()
        self.assertEqual(log.kind, ReminderLog.KIND_SENT)
        self.assertEqual(log.period_start, DAY)
        self.assertEqual(log.period_end, DAY)
        self.assertTrue(log.body.strip(), "تأكيدٌ بلا نصّ لا يُسجَّل")
        self.assertIn(DAY.strftime("%d/%m/%Y"), log.body)
        self.assertIsNotNone(stored.confirmed_at)
        self.assertGreaterEqual(stored.confirmed_at, stored.created_at)
        self.assertEqual(sent["log"]["id"], log.pk)

    def test_a_confirmation_without_a_primary_contact_is_refused_with_a_message(self):
        client = self.make_client("زبون بلا جهة")

        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
        )
        stored = ClientAppointment.objects.get(pk=row["id"])

        with self.assertRaises(DjangoValidationError) as caught:
            appointments.send_appointment_confirmation(self.tenant, stored, actor=self.owner)
        self.assertIn("جهة", str(caught.exception))
        self.assertEqual(
            ReminderLog.objects.filter(reminder_type=REMINDER_APPOINTMENT).count(), 0,
        )
        stored.refresh_from_db()
        self.assertIsNone(stored.confirmed_at)

    def test_the_client_payload_lists_the_appointments_with_the_kind_choices(self):
        client = self.ready_client()
        appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY, 11, 0),
        )
        appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_CALL, scheduled_at=at(DAY + datetime.timedelta(days=2), 8, 0),
        )

        payload = appointments.client_appointments_payload(client, day=DAY)

        self.assertEqual(len(payload["rows"]), 2)
        self.assertEqual(payload["rows"][0]["time"], "11:00")
        self.assertEqual(
            [choice["label"] for choice in payload["kind_choices"]],
            ["زيارة", "مكالمة", "توقيع", "استلام أوراق"],
        )


# ── مولّد «موعد رسمي قريب» (د3، د6) ─────────────────────────────────────────
class DeadlineReminderTest(OfficeFixture):
    def deadline_items(self, day=DAY):
        return [
            item for item in self.items(day)
            if item["reminder_type"] == REMINDER_DEADLINE
        ]

    def send_deadline(self, client, *, day):
        """صفُّ إرسالٍ **بيوم نافذته الصريح** — لا بساعة الاختبار."""
        contact = services.resolve_reminder_recipient(client, REMINDER_DEADLINE).contact
        rows = services.mark_reminders_sent(
            self.tenant,
            user=self.owner,
            contact_id=contact.pk,
            body="تذكير",
            items=[{
                "client_id": client.pk,
                "reminder_type": REMINDER_DEADLINE,
                "period_start": JAN_START.isoformat(),
                "period_end": JAN_END.isoformat(),
            }],
        )
        return [at_log(row, day) for row in rows]

    def test_seven_days_before_the_actual_deadline_it_is_ready(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        items = self.deadline_items(SEVEN_DAYS_BEFORE)

        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["client_id"], client.pk)
        # `due_date` في البند يومُ استحقاق التذكير المحسوب (7 أيام قبل الموعد)،
        # والموعدُ نفسُه يُقرأ من النصّ — لا نسخةَ ثانية منه في البند.
        self.assertEqual(items[0]["due_date"], SEVEN_DAYS_BEFORE.isoformat())
        self.assertEqual(items[0]["reminder_type_label"], "موعد رسمي قريب")
        self.assertEqual(items[0]["step"], 1)
        self.assertEqual(items[0]["max"], 2)

    def test_nothing_appears_a_day_before_the_seventh_day(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        self.assertEqual(
            self.deadline_items(SEVEN_DAYS_BEFORE - datetime.timedelta(days=1)), [],
        )

    def test_the_second_reminder_waits_for_the_two_day_mark(self):
        client = self.ready_client()

        # الحدثُ الأوّل: رسالةٌ سُجّلت في النافذة الأولى — ثم تُقاس النافذةُ التالية
        # بأيّام الصفوف لا بعدّها.
        self.send_deadline(client, day=SEVEN_DAYS_BEFORE)
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        self.assertEqual(self.deadline_items(TWO_DAYS_BEFORE_EVE), [])
        items = self.deadline_items(TWO_DAYS_BEFORE)
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["step"], 2)

        # والثاني يُقفل النافذة: لا ثالثَ بعد النافذتين.
        self.send_deadline(client, day=TWO_DAYS_BEFORE)
        self.assertEqual(self.deadline_items(TWO_DAYS_BEFORE), [])

    def test_an_obligation_that_moved_on_owes_nothing(self):
        client = self.ready_client()
        self.add_obligation(
            client, actual=DUE, amount=Decimal("620.00"),
            status=OBLIGATION_STATUS_SUBMITTED,
        )
        self.assertEqual(self.deadline_items(SEVEN_DAYS_BEFORE), [])

    def test_whole_papers_and_no_amount_is_no_reminder(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=None)
        self.assertEqual(self.deadline_items(SEVEN_DAYS_BEFORE), [])

    def test_missing_papers_alone_are_enough(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=None)
        self.add_missing(client)

        items = self.deadline_items(SEVEN_DAYS_BEFORE)

        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["missing_list"], ["فاتورة مشتريات"])

    def test_a_paid_amount_alone_is_not_enough(self):
        client = self.ready_client()
        self.add_obligation(
            client, actual=DUE, amount=Decimal("620.00"), client_paid=True,
        )
        self.assertEqual(self.deadline_items(SEVEN_DAYS_BEFORE), [])

    def test_the_extension_moves_the_trigger_and_the_due_date_with_it(self):
        client = self.ready_client()
        obligation = self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))
        extended = DUE + datetime.timedelta(days=6)
        Obligation.objects.filter(pk=obligation.pk).update(extended_to=extended)

        self.assertEqual(self.deadline_items(SEVEN_DAYS_BEFORE), [])
        moved_trigger = extended - datetime.timedelta(days=7)
        items = self.deadline_items(moved_trigger)
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["due_date"], moved_trigger.isoformat())
        # النصُّ يطبَع الموعدَ الممدَّد لا الأصليّ — فالمولّدُ قرأ `due_date` وحدها.
        message = self.ready(moved_trigger)["messages"][0]
        self.assertIn(extended.strftime("%d/%m/%Y"), message["body"])
        self.assertNotIn(DUE.strftime("%d/%m/%Y"), message["body"])

    def test_the_shipped_template_names_the_period_and_the_deadline(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        messages = self.ready(SEVEN_DAYS_BEFORE)["messages"]

        self.assertEqual(len(messages), 1, messages)
        body = messages[0]["body"]
        self.assertIn(DUE.strftime("%d/%m/%Y"), body)
        self.assertIn("موعد التقديم", body)
        self.assertIn("كانون الثاني 2026", body)

    def test_a_disabled_type_is_hidden_even_when_the_client_owes_something(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))
        services.set_office_setting(
            self.tenant, services.REMINDER_TYPES_ENABLED_KEY, [REMINDER_DOCUMENTS],
        )

        self.assertEqual(self.deadline_items(SEVEN_DAYS_BEFORE), [])

    # ── بندٌ واحدٌ لكل (زبون، فترة) ─────────────────────────────────────────
    def test_two_obligations_of_one_period_are_one_item(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("300.00"))
        self.add_obligation(
            client, actual=DUE + datetime.timedelta(days=4),
            amount=Decimal("200.00"), service_code="payroll",
        )
        self.add_missing(client)

        items = self.deadline_items(SEVEN_DAYS_BEFORE)

        # التزامان في الفترة الواحدة بندان بمفتاحٍ واحد: تحذيرُ مفاتيحَ مكرَّرة في
        # الواجهة، وعدّادٌ مشتركٌ يسقط بندَ «قبل ٢». فالبندُ للفترة لا للالتزام.
        self.assertEqual(len(items), 1, items)
        # وأقربُ موعدٍ في الفترة هو ما يفتح النافذة (10 شباط لا 14 منه).
        self.assertEqual(items[0]["due_date"], SEVEN_DAYS_BEFORE.isoformat())
        self.assertEqual(items[0]["missing_list"], ["فاتورة مشتريات"])
        # والمبلغُ مجموعُ المستحقّ على الفترة: 300 + 200.
        self.assertIn("500.00", self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"])

    def test_an_earlier_deadline_with_nothing_owed_does_not_open_the_window(self):
        client = self.ready_client()
        # التزامٌ أبكر لا شيءَ عليه (4 شباط)، وآخرُ أبعدُ عليه المبلغ (10 شباط):
        # الموعدُ الذي يفتح النافذةَ موعدُ ما **عليه شيء** لا أبكرُ التزامٍ في الفترة.
        earliest = DAY + datetime.timedelta(days=3)
        self.add_obligation(
            client, actual=earliest, amount=None, service_code="payroll",
        )
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))
        earlier_window = earliest - datetime.timedelta(days=7)

        self.assertEqual(self.deadline_items(earlier_window), [])
        items = self.deadline_items(SEVEN_DAYS_BEFORE)

        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["due_date"], SEVEN_DAYS_BEFORE.isoformat())
        self.assertIn(
            DUE.strftime("%d/%m/%Y"), self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"],
        )

    def test_a_paid_earlier_deadline_does_not_drop_the_reminder_of_the_real_one(self):
        client = self.ready_client()
        # مدفوعٌ موعدُه 3 شباط وعليه 620 موعدُه 10 شباط: من 4 شباط كان `day <= due`
        # خطأً للفترة كلّها فلا «قبل ٧» ولا «قبل ٢» عن 10 شباط أبداً.
        paid_day = SEVEN_DAYS_BEFORE
        self.add_obligation(
            client, actual=paid_day, amount=Decimal("100.00"),
            client_paid=True, service_code="payroll",
        )
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        after_paid_deadline = paid_day + datetime.timedelta(days=1)
        items = self.deadline_items(after_paid_deadline)
        self.assertEqual(len(items), 1, items)
        body = self.ready(after_paid_deadline)["messages"][0]["body"]
        self.assertIn(DUE.strftime("%d/%m/%Y"), body)
        self.assertNotIn(paid_day.strftime("%d/%m/%Y"), body)
        # و«قبل ٢» تصل عن 10 شباط نفسه.
        items = self.deadline_items(TWO_DAYS_BEFORE)
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["step"], 2)

    def test_an_owing_deadline_already_passed_does_not_hide_the_later_extended_one(self):
        client = self.ready_client()
        # عليه شيءٌ وموعدُه مضى (2 شباط ⇒ متأخّرٌ يخصّه الأحمر)، وآخرُ ممدَّدٌ إلى
        # 10 شباط: البندُ يُحسب من موعد الممدَّد لا من الذي مضى.
        self.add_obligation(
            client, actual=DAY + datetime.timedelta(days=1), amount=Decimal("100.00"),
            service_code="payroll",
        )
        extended = self.add_obligation(
            client, actual=DAY, amount=Decimal("620.00"),
        )
        Obligation.objects.filter(pk=extended.pk).update(extended_to=DUE)
        inside = SEVEN_DAYS_BEFORE + datetime.timedelta(days=2)

        items = self.deadline_items(inside)

        self.assertEqual(len(items), 1, items)
        self.assertIn(
            DUE.strftime("%d/%m/%Y"), self.ready(inside)["messages"][0]["body"],
        )

    def test_a_period_whose_owing_deadlines_all_passed_has_no_item(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DAY, amount=Decimal("620.00"))

        # المتأخّرُ يخصّه التنبيهُ الأحمر (`obligation_late`) لا نصُّ «قريب».
        self.assertEqual(self.deadline_items(DAY + datetime.timedelta(days=1)), [])

    # ── نافذةٌ لا عدّاد ──────────────────────────────────────────────────────
    def test_a_dismissal_silences_the_window_until_the_next_one(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))
        in_first_window = DUE - datetime.timedelta(days=5)
        self.assertEqual(len(self.deadline_items(in_first_window)), 1)

        services.dismiss_reminders(
            self.tenant,
            user=self.owner,
            items=[{
                "client_id": client.pk,
                "reminder_type": REMINDER_DEADLINE,
                "period_start": JAN_START.isoformat(),
                "period_end": JAN_END.isoformat(),
            }],
        )
        for row in ReminderLog.objects.filter(
            client=client, kind=ReminderLog.KIND_DISMISSED,
        ):
            at_log(row, in_first_window)

        # «شيل» يُسكته حتّى نهاية نافذته — لا يُنحّى كلَّ يوم.
        self.assertEqual(
            self.deadline_items(in_first_window + datetime.timedelta(days=1)), [],
        )
        self.assertEqual(self.deadline_items(TWO_DAYS_BEFORE_EVE), [])
        # والنافذةُ التالية تُعيده مرّةً: موضعُها الثاني من موضعين.
        items = self.deadline_items(TWO_DAYS_BEFORE)
        self.assertEqual(len(items), 1, items)
        self.assertEqual((items[0]["step"], items[0]["max"]), (2, 2))

    def test_a_send_does_not_repeat_inside_the_same_day(self):
        client = self.ready_client()
        due_soon = DAY + datetime.timedelta(days=2)
        self.add_obligation(client, actual=due_soon, amount=Decimal("620.00"))
        self.assertEqual(len(self.deadline_items(DAY)), 1)

        self.send_deadline(client, day=DAY)

        # رسالتُه سُجّلت اليوم: بندٌ ثانٍ في اليوم نفسه إلحاحٌ مكرَّر.
        self.assertEqual(self.deadline_items(DAY), [])

    def test_the_second_window_opens_once(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        self.send_deadline(client, day=TWO_DAYS_BEFORE)

        self.assertEqual(self.deadline_items(TWO_DAYS_BEFORE), [])
        self.assertEqual(
            self.deadline_items(TWO_DAYS_BEFORE + datetime.timedelta(days=1)), [],
        )
        # ولا بندَ بعد يوم الموعد نفسه: بعده متأخّرٌ لا قريب.
        self.assertEqual(
            self.deadline_items(DUE + datetime.timedelta(days=1)), [],
        )

    # ── المبلغُ في النصّ والنصُّ في الحالات الثلاث ────────────────────────────
    def _assert_no_dangling_line(self, body):
        """لا سطرَ ينتهي بعنوانٍ بلا قيمة — ولا فراغَ مزدوجاً من قيمةٍ غائبة."""
        self.assertNotIn("  ", body)
        for line in body.splitlines():
            self.assertFalse(line.rstrip().endswith(":"), repr(line))

    def test_an_amount_without_missing_papers_reads_whole(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        body = self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"]

        self.assertIn("620.00", body)
        self.assertNotIn("ولسا بدنا نستلم منك", body)
        self._assert_no_dangling_line(body)

    def test_missing_papers_are_named_in_the_body(self):
        client = self.ready_client()
        self.add_obligation(client, actual=DUE, amount=None)
        self.add_missing(client)

        body = self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"]

        self.assertIn("فاتورة مشتريات", body)
        self._assert_no_dangling_line(body)

    def test_the_hebrew_body_carries_the_amount(self):
        client = self.make_client("زبون عبريّ")
        self.link(client, self.make_contact(name="أبو العبريّ", language="he"))
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        body = self.ready(SEVEN_DAYS_BEFORE)["messages"][0]["body"]

        self.assertIn("המועד להגשה", body)
        self.assertIn("620.00", body)
        self._assert_no_dangling_line(body)

    def test_the_message_text_carries_the_amount_to_a_member_without_amounts_view(self):
        """**استثناءٌ مقصودٌ من قاعدة القناع** — يُثبَّت قراراً لا يُمحى بصمت.

        نصُّ الرسالة موجَّهٌ إلى **الزبون نفسه** (مبلغُه عليه)، وقنعُه عن موظّفٍ بلا
        `office.amounts.view` يُرسل «—» إلى الزبون بدل مبلغه. أما الحمولةُ المهيكلة
        (`items`) فلا تحمل مفتاحَ مبلغٍ في جذرها: الاستثناءُ في نصّ الرسالة وصفِّ
        سجلّها وحدهما — **و«إشعار الدفع» (#285) استثناءٌ ثانٍ صريح**: أسطرُه ومجموعُه
        في `items[].notice` لأن الإشعارَ نفسَه هو المخرَجُ الموجَّه للزبون (د3).
        """
        member = self.make_member("ap_no_amounts", role="accountant")
        self.assertFalse(services.can_see_amounts(self.tenant, member))
        client = self.make_client("زبون المحاسب", responsible=member)
        self.link(client, self.make_contact(name="جهة المحاسب"))
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))

        payload = services.ready_to_send_payload(
            self.tenant, user=member, day=SEVEN_DAYS_BEFORE,
        )

        self.assertEqual(len(payload["messages"]), 1, payload["messages"])
        message = payload["messages"][0]
        self.assertIn("مبلغ مستحقّ: 620.00", message["body"])
        # الحارسُ على **سطر المبلغ** لا على الشرطة في كلّ النصّ: عنوانُ إشعار الدفع
        # الثابت (#285) يحمل شرطةً طويلةً من نصّه، فالحرفُ وحده لم يبقَ دليلاً على
        # قناعٍ تسلّل — والسطرُ هو ما يُقاس.
        self.assertNotIn("مبلغ مستحقّ: —", message["body"])
        for item in message["items"]:
            self.assertFalse(
                {"amount", "amount_label"} & set(item), f"مبلغٌ في بند الحمولة: {item}",
            )
        # وصفُّ السجلّ المحفوظ يحمل ما أُرسل: النصُّ نفسه بمبلغه.
        contact = message["recipient"]["contact_id"]
        rows = services.mark_reminders_sent(
            self.tenant,
            user=member,
            contact_id=contact,
            body=message["body"],
            items=[{
                "client_id": client.pk,
                "reminder_type": REMINDER_DEADLINE,
                "period_start": JAN_START.isoformat(),
                "period_end": JAN_END.isoformat(),
            }],
        )
        log = services.reminder_log_row(rows[0], masked=True)
        self.assertIn("620.00", log["body"])


# ── مولّد «تذكير موعد» (بند ٢) ──────────────────────────────────────────────
class AppointmentReminderTest(OfficeFixture):
    def appointment_items(self, day=DAY):
        return [
            item for item in self.items(day)
            if item["reminder_type"] == REMINDER_APPOINTMENT
        ]

    def make_appointment(self, client, *, scheduled_at, kind=APPOINTMENT_KIND_VISIT):
        return ClientAppointment.objects.create(
            tenant=self.tenant, client=client, kind=kind,
            scheduled_at=scheduled_at, created_by=self.owner,
        )

    def test_a_day_before_the_appointment_the_reminder_is_ready(self):
        client = self.ready_client()
        self.make_appointment(client, scheduled_at=at(DAY + datetime.timedelta(days=1), 10, 0))

        items = self.appointment_items(DAY)

        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["reminder_type_label"], "تذكير موعد")
        # تسميةُ الفترة في بند الموعد وقتُ الموعد نفسه لا اسمُ الشهر.
        self.assertEqual(
            items[0]["period_label"],
            f"{(DAY + datetime.timedelta(days=1)):%d/%m/%Y} 10:00",
        )

    def test_two_appointments_of_one_client_on_one_day_are_one_item(self):
        client = self.ready_client()
        day_after = DAY + datetime.timedelta(days=1)
        self.make_appointment(client, scheduled_at=at(day_after, 14, 0))
        self.make_appointment(client, scheduled_at=at(day_after, 10, 0))

        payload = self.ready(DAY)
        items = [item for message in payload["messages"] for item in message["items"]]

        # المفتاحُ `(زبون، موعد، يوم، يوم)` واحدٌ للموعدين: بندان به = مفتاحُ React
        # مكرَّر، وإرسالُ أحدهما يُسكت الآخر. فبندٌ واحدٌ للزبون واليوم يحمل الوقتين.
        self.assertEqual(len(items), 1, items)
        self.assertEqual(len(payload["messages"]), 1, payload["messages"])
        self.assertEqual(
            items[0]["period_label"], f"{day_after:%d/%m/%Y} 10:00، 14:00",
        )
        keys = [
            (item["client_id"], item["reminder_type"], item["period_start"], item["period_end"])
            for item in items
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_it_does_not_appear_two_days_before_with_the_default_one_day(self):
        client = self.ready_client()
        self.make_appointment(client, scheduled_at=at(DAY + datetime.timedelta(days=2), 10, 0))

        self.assertEqual(self.appointment_items(DAY), [])

    def test_the_client_override_moves_the_lead_time(self):
        client = self.ready_client()
        services.set_client_setting(client, appointments.APPOINTMENT_REMINDER_DAYS_KEY, 3)
        self.make_appointment(client, scheduled_at=at(DAY + datetime.timedelta(days=2), 10, 0))

        items = self.appointment_items(DAY)

        self.assertEqual(len(items), 1, items)

    def test_a_cancelled_or_done_appointment_is_not_reminded(self):
        client = self.ready_client()
        soon = at(DAY + datetime.timedelta(days=1), 10, 0)
        cancelled = self.make_appointment(client, scheduled_at=soon)
        done = self.make_appointment(client, scheduled_at=soon)
        ClientAppointment.objects.filter(pk=cancelled.pk).update(
            status=APPOINTMENT_STATUS_CANCELLED,
        )
        ClientAppointment.objects.filter(pk=done.pk).update(status=APPOINTMENT_STATUS_DONE)

        self.assertEqual(self.appointment_items(DAY), [])

    def test_after_one_reminder_the_slot_is_closed(self):
        client = self.ready_client()
        contact = services.resolve_reminder_recipient(client, REMINDER_APPOINTMENT).contact
        day_after = DAY + datetime.timedelta(days=1)
        self.make_appointment(client, scheduled_at=at(day_after, 10, 0))

        for row in services.mark_reminders_sent(
            self.tenant,
            user=self.owner,
            contact_id=contact.pk,
            body="تذكير الموعد",
            items=[{
                "client_id": client.pk,
                "reminder_type": REMINDER_APPOINTMENT,
                "period_start": day_after.isoformat(),
                "period_end": day_after.isoformat(),
            }],
        ):
            at_log(row, DAY)

        self.assertEqual(self.appointment_items(DAY), [])

    def test_the_reminder_body_carries_the_appointment_date(self):
        client = self.ready_client()
        day_after = DAY + datetime.timedelta(days=1)
        self.make_appointment(client, scheduled_at=at(day_after, 10, 0))

        messages = self.ready(DAY)["messages"]

        self.assertEqual(len(messages), 1, messages)
        self.assertIn(day_after.strftime("%d/%m/%Y"), messages[0]["body"])

    def test_the_office_setting_governs_the_default_lead_time(self):
        client = self.ready_client()
        services.set_office_setting(
            self.tenant, appointments.APPOINTMENT_REMINDER_DAYS_KEY, 7,
        )
        self.make_appointment(client, scheduled_at=at(DAY + datetime.timedelta(days=5), 10, 0))

        items = self.appointment_items(DAY)

        self.assertEqual(len(items), 1, items)

    # ── التأكيدُ لا يستهلك نافذةَ التذكير ────────────────────────────────────
    def confirm(self, client, *, slot_day):
        """تأكيدٌ مسجَّلٌ **بيومه الصريح** — لا بساعة الاختبار."""
        row = self.make_appointment(client, scheduled_at=at(slot_day, 10, 0))
        sent = appointments.send_appointment_confirmation(
            self.tenant, ClientAppointment.objects.get(pk=row.pk), actor=self.owner,
        )
        at_log(ReminderLog.objects.get(pk=sent["log"]["id"]), DAY)
        return sent

    def test_a_confirmation_does_not_spend_the_day_before_reminder(self):
        client = self.ready_client()
        slot_day = DUE
        self.confirm(client, slot_day=slot_day)
        day_before = slot_day - datetime.timedelta(days=1)

        # قبل النافذة بيوم: لا بندَ بعد (الحجزُ حُجز، والتذكيرُ لم يحن).
        self.assertEqual(self.appointment_items(day_before - datetime.timedelta(days=1)), [])
        items = self.appointment_items(day_before)

        # التأكيدُ رسالةُ حجزٍ لا تذكيرُ «قبله بيوم»: صفُّه قبل النافذة فلا يعدّها.
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["period_start"], slot_day.isoformat())
        self.assertEqual(items[0]["due_date"], day_before.isoformat())
        self.assertEqual((items[0]["step"], items[0]["max"]), (1, 1))

    def test_a_confirmation_inside_the_window_keeps_the_slot_closed(self):
        client = self.ready_client()
        self.confirm(client, slot_day=DAY + datetime.timedelta(days=1))

        # والتأكيدُ داخل النافذة نفسها يُسكتها: رسالتُه وصلت اليوم.
        self.assertEqual(self.appointment_items(DAY), [])


# ── فلترُ النوع في «جاهز للإرسال» ───────────────────────────────────────────
class ReminderTypeFilterTest(OfficeFixture):
    def seed_three_types(self, client):
        """ثلاثةُ بنودٍ مستحقّةٍ في اليوم نفسه — نوعٌ لكلِّ مولّد."""
        self.add_missing(client)
        self.add_obligation(client, actual=DUE, amount=Decimal("620.00"))
        ClientAppointment.objects.create(
            tenant=self.tenant,
            client=client,
            kind=APPOINTMENT_KIND_VISIT,
            scheduled_at=at(SEVEN_DAYS_BEFORE + datetime.timedelta(days=1), 10, 0),
            created_by=self.owner,
        )

    def test_the_type_filter_offers_its_own_type_only(self):
        client = self.ready_client()
        self.seed_three_types(client)

        self.assertEqual(
            {item["reminder_type"] for item in self.items(SEVEN_DAYS_BEFORE)},
            {REMINDER_DOCUMENTS, REMINDER_DEADLINE, REMINDER_APPOINTMENT},
        )
        for wanted in (REMINDER_DOCUMENTS, REMINDER_APPOINTMENT, REMINDER_DEADLINE):
            with self.subTest(wanted=wanted):
                self.assertEqual(
                    {
                        item["reminder_type"]
                        for item in self.items(SEVEN_DAYS_BEFORE, reminder_type=wanted)
                    },
                    {wanted},
                )


# ── «اليوم» والتقويم (بند ٥) ────────────────────────────────────────────────
class AppointmentSurfacesTest(OfficeFixture):
    def test_today_counts_this_day_appointments_and_lists_them_in_order(self):
        client = self.ready_client()
        appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY, 14, 0),
        )
        appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_CALL, scheduled_at=at(DAY, 9, 30),
        )
        appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT,
            scheduled_at=at(DAY + datetime.timedelta(days=1), 10, 0),
        )

        payload = services.today_payload(self.tenant, user=self.owner, day=DAY)

        self.assertEqual(payload["counters"]["appointments"], 2)
        self.assertEqual(
            [row["time"] for row in payload["appointments"]], ["09:30", "14:00"],
        )

    def test_a_cancelled_appointment_is_out_of_the_day_count(self):
        client = self.ready_client()
        row = appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY),
        )
        appointments.cancel_appointment(
            ClientAppointment.objects.get(pk=row["id"]), actor=self.owner,
        )

        payload = services.today_payload(self.tenant, user=self.owner, day=DAY)

        self.assertEqual(payload["counters"]["appointments"], 0)
        self.assertEqual(payload["appointments"], [])

    def test_the_calendar_carries_the_appointments_of_its_range(self):
        client = self.ready_client()
        appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY, 10, 0),
        )
        appointments.create_appointment(
            self.tenant, user=self.owner, client_id=client.pk,
            kind=APPOINTMENT_KIND_VISIT,
            scheduled_at=at(DAY + datetime.timedelta(days=20), 10, 0),
        )

        payload = services.calendar_payload(
            self.tenant, user=self.owner,
            start=DAY, end=DAY + datetime.timedelta(days=7), today=DAY,
        )

        self.assertEqual(len(payload["appointments"]), 1, payload["appointments"])
        self.assertEqual(payload["appointments"][0]["day"], DAY.isoformat())
        self.assertEqual(payload["appointments"][0]["client"]["id"], client.pk)
        # التقويمُ يحجز أيضاً: أنواعُ المواعيد تصل معه بتسمياتها.
        self.assertEqual(len(payload["kind_choices"]), 4)

    def test_the_calendar_appointments_follow_its_client_filter(self):
        one = self.ready_client("زبون أوّل")
        two = self.ready_client("زبون ثانٍ")
        for client in (one, two):
            appointments.create_appointment(
                self.tenant, user=self.owner, client_id=client.pk,
                kind=APPOINTMENT_KIND_VISIT, scheduled_at=at(DAY, 10, 0),
            )

        payload = services.calendar_payload(
            self.tenant, user=self.owner,
            start=DAY, end=DAY + datetime.timedelta(days=7), today=DAY,
            client=one.pk,
        )

        self.assertEqual(
            [row["client"]["id"] for row in payload["appointments"]], [one.pk],
        )


# ── الـAPI: العزلُ والمفتاح (د5) ────────────────────────────────────────────
class AppointmentApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="apa_owner", password="x")
        cls.tenant = create_company("مكتب API المواعيد", cls.owner, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(user=user, tenant=cls.tenant, role=role)
            return user

        cls.accountant = member("apa_accountant", "accountant")
        cls.viewer = member("apa_viewer", "viewer")
        cls.colleague = member("apa_colleague", "accountant")

        def make(name, responsible):
            client = OfficeClient.objects.create(
                tenant=cls.tenant, name=name, responsible=responsible,
            )
            TaxCard.objects.create(
                client=client, vat_classification="authorized", annual_sales=0,
            )
            return client

        cls.mine = make("زبون المحاسب", cls.accountant)
        cls.other = make("زبون الزميل", cls.colleague)
        # جهةٌ رئيسيّةٌ مربوطةٌ برقم — «ابعت تأكيد» يريد مستلِماً فعليّاً (د4).
        cls.contact = Contact.objects.create(
            tenant=cls.tenant, name="أبو المحاسب", phone="0599123456", language="ar",
        )
        services.link_client_contact(
            client=cls.mine, contact=cls.contact, is_primary=True,
        )

        cls.outside_owner = User.objects.create_user(username="apa_outside", password="x")
        cls.outside = create_company(
            "مكتب آخر للمواعيد", cls.outside_owner, template="accounting_office",
        )
        invalidate_module_cache(cls.outside.pk)
        ready_office(cls.outside, "IL")
        cls.outside_client = OfficeClient.objects.create(
            tenant=cls.outside, name="زبون المكتب الآخر", responsible=cls.outside_owner,
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def create(self, client, *, when=None, kind=APPOINTMENT_KIND_VISIT, **extra):
        self.as_user(self.owner)
        payload = {
            "client_id": client.pk,
            "kind": kind,
            "scheduled_at": (when or at(DAY)).isoformat(),
        }
        payload.update(extra)
        return self.client.post(
            APPOINTMENTS, payload, format="json", **self.headers(),
        )

    def test_the_owner_creates_and_reads_the_appointment_through_the_api(self):
        res = self.create(self.mine)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["status"], APPOINTMENT_STATUS_SCHEDULED)

        listing = self.client.get(
            APPOINTMENTS, {"client": self.mine.pk}, **self.headers(),
        )
        self.assertEqual(listing.status_code, 200, listing.content)
        self.assertEqual(len(listing.data["rows"]), 1)
        self.assertEqual(len(listing.data["kind_choices"]), 4)

    def test_a_zero_or_missing_client_is_400(self):
        self.as_user(self.owner)
        res = self.client.post(
            APPOINTMENTS,
            {"kind": APPOINTMENT_KIND_VISIT, "scheduled_at": at(DAY).isoformat()},
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_a_member_without_the_write_key_cannot_book(self):
        self.as_user(self.viewer)
        res = self.client.post(
            APPOINTMENTS,
            {
                "client_id": self.mine.pk,
                "kind": APPOINTMENT_KIND_VISIT,
                "scheduled_at": at(DAY).isoformat(),
            },
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)

    def test_a_client_of_another_member_is_404_not_403(self):
        self.as_user(self.colleague)
        res = self.client.get(
            APPOINTMENTS, {"client": self.mine.pk}, **self.headers(),
        )
        self.assertEqual(res.status_code, 404, res.content)

    def test_a_client_of_another_office_is_404_on_every_action(self):
        res = self.create(self.outside_client)
        self.assertEqual(res.status_code, 404, res.content)

    def test_confirm_reschedule_and_cancel_come_back_with_the_row(self):
        created = self.create(self.mine)
        pk = created.data["id"]

        confirm = self.client.post(
            f"{APPOINTMENTS}{pk}/confirm/", {}, format="json", **self.headers(),
        )
        self.assertEqual(confirm.status_code, 200, confirm.content)
        self.assertIsNotNone(confirm.data["appointment"]["confirmed_at"])

        moved = self.client.post(
            f"{APPOINTMENTS}{pk}/reschedule/",
            # الشكلُ الذي يرسله `input[type=datetime-local]`: بلا ثوانٍ ولا منطقة.
            {"scheduled_at": "2026-02-01T12:00"},
            format="json",
            **self.headers(),
        )
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(moved.data["appointment"]["time"], "12:00")

        cancelled = self.client.post(
            f"{APPOINTMENTS}{pk}/cancel/", {}, format="json", **self.headers(),
        )
        self.assertEqual(cancelled.status_code, 200, cancelled.content)
        self.assertEqual(cancelled.data["appointment"]["status"], APPOINTMENT_STATUS_CANCELLED)

    def test_the_list_is_bounded_by_day_and_by_the_clients_the_member_sees(self):
        self.as_user(self.owner)
        self.client.post(
            APPOINTMENTS,
            {
                "client_id": self.mine.pk,
                "kind": APPOINTMENT_KIND_VISIT,
                "scheduled_at": at(DAY).isoformat(),
            },
            format="json",
            **self.headers(),
        )
        self.client.post(
            APPOINTMENTS,
            {
                "client_id": self.other.pk,
                "kind": APPOINTMENT_KIND_VISIT,
                "scheduled_at": at(DAY + datetime.timedelta(days=3)).isoformat(),
            },
            format="json",
            **self.headers(),
        )

        today = self.client.get(APPOINTMENTS, {"day": DAY.isoformat()}, **self.headers())
        self.assertEqual(today.status_code, 200, today.content)
        self.assertEqual(len(today.data["rows"]), 1, today.data["rows"])

        self.as_user(self.accountant)
        mine = self.client.get(APPOINTMENTS, {}, **self.headers())
        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertEqual([row["client"]["id"] for row in mine.data["rows"]], [self.mine.pk])
