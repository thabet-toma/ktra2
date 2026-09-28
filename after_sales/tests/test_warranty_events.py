"""#229 — سجل أحداث البطاقة (`WarrantyCardEvent`) والحالة الموحّدة.

يثبت:
  1. التمديد اليدوي يكتب حدث `extend` (التاريخين والسبب وكود المجاملة) بدل
     إلحاق سطرٍ في `card.notes` — والملاحظات تبقى كما كانت.
  2. سجل الأحداث يُقرأ عبر `GET warranties/{id}/events/` — للقراءة فقط.
  3. بطاقةٌ عليها حدثٌ لا تُحذف: 400 برسالة مقروءة، لا 500 من `PROTECT`.
  4. `WarrantyCardQuerySet.active_on/expired_on/ended` تحسم فلترة القائمة —
     نفس النتائج التي كانت تُحسب بمقارنة `end_date` حرّة.
  5. البوابة والعزل على النقطة الجديدة.
"""
from datetime import date

from after_sales.models import WarrantyCard, WarrantyCardEvent
from core.models import TenantModule
from tenants.services import create_company

from .test_warranty import WarrantyTestBase

BASE = "/api/after-sales/warranties/"


class ExtendWritesAnEventTest(WarrantyTestBase):
    def manual_payload(self, **overrides):
        data = {
            "device_name": "هاتف زبون",
            "serial": "EV-1",
            "start_date": "2026-06-01",
            "duration_months": 6,
            "customer_name": "سامي",
        }
        data.update(overrides)
        return data

    def test_extend_writes_an_event_with_both_dates_and_reason_not_a_notes_line(self):
        created = self.client.post(
            BASE, self.manual_payload(), format="json", **self.headers(),
        ).data
        card = WarrantyCard.objects.get(pk=created["id"])
        self.assertEqual(card.notes, "")

        response = self.client.post(
            f"{BASE}{created['id']}/extend/", {"months": 3, "reason": "مجاملة زبون قديم"},
            format="json", **self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)

        card.refresh_from_db()
        # #229: الملاحظات لم تُمسّ — التوثيق انتقل إلى السجل الإلحاقي.
        self.assertEqual(card.notes, "")

        event = WarrantyCardEvent.objects.get(card=card)
        self.assertEqual(event.event_type, WarrantyCardEvent.TYPE_EXTEND)
        self.assertEqual(event.reason_code, WarrantyCardEvent.EXTEND_REASON_COURTESY)
        self.assertEqual(event.text, "مجاملة زبون قديم")
        self.assertEqual(event.old_end_date, date(2026, 12, 1))
        self.assertEqual(event.new_end_date, date(2027, 3, 1))
        self.assertEqual(event.tenant_id, self.tenant.pk)

    def test_extend_without_a_reason_still_writes_the_event_with_an_empty_text(self):
        created = self.client.post(
            BASE, self.manual_payload(serial="EV-2"), format="json", **self.headers(),
        ).data

        response = self.client.post(
            f"{BASE}{created['id']}/extend/", {"months": 1}, format="json", **self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)

        event = WarrantyCardEvent.objects.get(card_id=created["id"])
        self.assertEqual(event.text, "")
        self.assertEqual(event.reason_code, WarrantyCardEvent.EXTEND_REASON_COURTESY)


class EventsEndpointActorlessEventTest(WarrantyTestBase):
    """مراجعة: `get_actor_name` كان يُخلَط ترتيب `or`/الشرط في القراءة، وحدثٌ
    بلا فاعل (`actor=None` — مستخدمٌ حُذف، أو حدثٌ كتبته دورةٌ آلية لاحقاً بلا
    مستخدم) يجب ألا يُسقط النقطة بـ500."""

    def test_an_actorless_event_is_listed_with_an_empty_actor_name_not_a_500(self):
        from after_sales.services import log_warranty_event

        card = WarrantyCard.objects.create(
            tenant=self.tenant, serial="EV-NOACTOR", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        log_warranty_event(
            card, event_type=WarrantyCardEvent.TYPE_ENDED, user=None,
        )

        response = self.client.get(f"{BASE}{card.pk}/events/", **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data), 1)
        self.assertIsNone(response.data[0]["actor"])
        self.assertEqual(response.data[0]["actor_name"], "")


class EventsEndpointTest(WarrantyTestBase):
    def test_events_action_lists_them_chronologically(self):
        card = WarrantyCard.objects.create(
            tenant=self.tenant, serial="EV-3", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        self.client.post(
            f"{BASE}{card.pk}/extend/", {"months": 1, "reason": "أ"},
            format="json", **self.headers(),
        )
        self.client.post(
            f"{BASE}{card.pk}/extend/", {"months": 1, "reason": "ب"},
            format="json", **self.headers(),
        )

        response = self.client.get(f"{BASE}{card.pk}/events/", **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(response.data[0]["text"], "أ")
        self.assertEqual(response.data[1]["text"], "ب")
        self.assertEqual(response.data[0]["event_type"], "extend")
        self.assertEqual(response.data[0]["event_type_label"], "تمديد")

    def test_events_action_is_empty_for_a_card_with_no_history(self):
        card = WarrantyCard.objects.create(
            tenant=self.tenant, serial="EV-4", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )

        response = self.client.get(f"{BASE}{card.pk}/events/", **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data, [])


class CardWithAnEventCannotBeDeletedTest(WarrantyTestBase):
    def test_a_card_with_an_event_is_rejected_with_400_not_500(self):
        card = WarrantyCard.objects.create(
            tenant=self.tenant, serial="EV-5", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        self.client.post(
            f"{BASE}{card.pk}/extend/", {"months": 1}, format="json", **self.headers(),
        )

        response = self.client.delete(f"{BASE}{card.pk}/", **self.headers())

        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(WarrantyCard.objects.filter(pk=card.pk).exists())

    def test_a_manual_card_with_no_events_can_still_be_deleted(self):
        card = WarrantyCard.objects.create(
            tenant=self.tenant, serial="EV-6", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )

        response = self.client.delete(f"{BASE}{card.pk}/", **self.headers())

        self.assertEqual(response.status_code, 204, response.content)


class WarrantyCardQuerySetTest(WarrantyTestBase):
    """#229: `active_on`/`expired_on`/`ended` تحسم كل فلترة على `end_date`."""

    def setUp(self):
        super().setUp()
        self.live = WarrantyCard.objects.create(
            tenant=self.tenant, serial="QS-LIVE", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2999, 1, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        self.expired = WarrantyCard.objects.create(
            tenant=self.tenant, serial="QS-DEAD", start_date=date(2020, 1, 1),
            duration_months=6, end_date=date(2020, 6, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        self.finished = WarrantyCard.objects.create(
            tenant=self.tenant, serial="QS-ENDED", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2999, 1, 1),
            source=WarrantyCard.SOURCE_MANUAL,
            ended_on=date(2026, 3, 1), end_reason=WarrantyCard.END_RETURNED,
        )

    def test_active_on_excludes_expired_and_ended(self):
        serials = set(
            WarrantyCard.objects.filter(tenant=self.tenant)
            .active_on(date(2026, 6, 1)).values_list("serial", flat=True)
        )
        self.assertEqual(serials, {"QS-LIVE"})

    def test_expired_on_excludes_live_and_ended(self):
        serials = set(
            WarrantyCard.objects.filter(tenant=self.tenant)
            .expired_on(date(2026, 6, 1)).values_list("serial", flat=True)
        )
        self.assertEqual(serials, {"QS-DEAD"})

    def test_ended_returns_only_the_terminated_card(self):
        serials = set(
            WarrantyCard.objects.filter(tenant=self.tenant)
            .ended().values_list("serial", flat=True)
        )
        self.assertEqual(serials, {"QS-ENDED"})


class EventsEndpointGateAndIsolationTest(WarrantyTestBase):
    def test_events_action_is_404_without_a_module_license(self):
        card = WarrantyCard.objects.create(
            tenant=self.tenant, serial="EV-7", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        self.license.delete()

        response = self.client.get(f"{BASE}{card.pk}/events/", **self.headers())

        self.assertEqual(response.status_code, 404, response.content)

    def test_events_action_never_reaches_another_companys_card(self):
        other = create_company("شركة كفالة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        other_card = WarrantyCard.objects.create(
            tenant=other, serial="EV-OTHER", start_date=date(2026, 1, 1),
            duration_months=6, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )

        response = self.client.get(f"{BASE}{other_card.pk}/events/", **self.headers())

        self.assertEqual(response.status_code, 404, response.content)
