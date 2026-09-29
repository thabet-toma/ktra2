"""#242 كفالة ١٤ — سجل الصيانات في البطاقة، وشريط الكفالة بطبقتيه.

`service_history` على تفصيل البطاقة وحده (لا القائمة)، و`warranty_status` على
أمر الصيانة يحمل الطبقتين. كل شيء من واجهة الـAPI كما يراه العميل.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from after_sales.models import (
    ManufacturerWarrantor,
    ServiceOrder,
    WarrantyCard,
    WarrantyCardEvent,
)
from core.models import TenantModule
from tenants.models import MemberPermission, UserCompanyMembership
from tenants.services import create_company

from .test_service_orders import ORDERS
from .test_warranty_void import FAR_END, LONG_AGO, WARRANTIES, VoidTestBase


class ServiceHistoryTestBase(VoidTestBase):
    def detail(self, card=None):
        card = card or self.card
        response = self.client.get(f"{WARRANTIES}{card.pk}/", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def history(self, card=None):
        return self.detail(card)["service_history"]

    def linked_order(self, order_date, **overrides):
        return self.intake(
            warranty_card=self.card.pk, warranty_covered=True, order_date=order_date,
            duplicate_open_reason="عطل آخر على الجهاز نفسه", **overrides,
        )

    def extend(self, card=None, months=1):
        card = card or self.card
        response = self.client.post(
            f"{WARRANTIES}{card.pk}/extend/", {"months": months, "reason": "مجاملة"},
            format="json", **self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def other_company(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        return other


class TimelineTest(ServiceHistoryTestBase):
    def test_two_orders_and_an_extension_are_all_listed_newest_first(self):
        first = self.linked_order("2026-06-15", complaint="الشكوى الأولى")
        second = self.linked_order("2026-07-20", complaint="الشكوى الثانية")
        self.extend()

        timeline = self.history()["timeline"]

        self.assertEqual(
            [(row["kind"], row.get("id")) for row in timeline][1:],
            [("order", second.pk), ("order", first.pk)],
        )
        self.assertEqual(timeline[0]["kind"], "event")
        self.assertEqual(timeline[0]["event_type"], WarrantyCardEvent.TYPE_EXTEND)
        self.assertEqual(len(timeline), 3)

    def test_an_order_row_carries_number_status_coverage_and_complaint(self):
        order = self.linked_order("2026-06-15", complaint="لا يشحن")

        (row,) = self.history()["timeline"]

        self.assertEqual(row["kind"], "order")
        self.assertEqual(row["id"], order.pk)
        self.assertEqual(row["order_number"], order.order_number)
        self.assertEqual(row["status"], ServiceOrder.STATUS_RECEIVED)
        self.assertTrue(row["status_label"])
        self.assertIs(row["covered"], True)
        self.assertEqual(row["complaint"], "لا يشحن")
        self.assertEqual(row["date"], "2026-06-15")

    def test_an_event_row_carries_type_label_text_and_user(self):
        self.extend()

        (row,) = self.history()["timeline"]

        self.assertEqual(row["kind"], "event")
        self.assertEqual(row["event_type"], "extend")
        self.assertTrue(row["event_type_label"])
        self.assertEqual(row["text"], "مجاملة")
        self.assertEqual(row["actor_name"], self.user.username)
        self.assertEqual(row["date"], str(timezone.localdate()))

    def test_on_the_same_day_the_later_created_entry_comes_first(self):
        today = str(timezone.localdate())
        order = self.linked_order(today)
        self.extend()
        after_event = self.history()["timeline"]
        self.assertEqual([row["kind"] for row in after_event], ["event", "order"])

        WarrantyCardEvent.objects.filter(card=self.card).update(
            created_at=timezone.now() - timedelta(hours=2),
        )
        ServiceOrder.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(hours=1),
        )

        self.assertEqual(
            [row["kind"] for row in self.history()["timeline"]], ["order", "event"],
        )

    def test_another_company_orders_and_events_never_appear(self):
        other = self.other_company()
        foreign_card = WarrantyCard.objects.create(
            tenant=other, serial=self.card.serial, device_name="جهاز الغير",
            start_date=LONG_AGO, duration_months=12, end_date=FAR_END,
            source=WarrantyCard.SOURCE_MANUAL,
        )
        foreign_order = ServiceOrder.objects.create(
            tenant=other, order_date="2026-06-01", serial=self.card.serial,
            customer_name="زبون الغير", complaint="سرّ الشركة الأخرى",
            warranty_card=foreign_card,
        )
        WarrantyCardEvent.objects.create(
            tenant=other, card=foreign_card, event_type=WarrantyCardEvent.TYPE_EXTEND,
            text="حدث الشركة الأخرى",
        )
        mine = self.linked_order("2026-06-15")

        history = self.history()

        self.assertEqual([row["id"] for row in history["timeline"]], [mine.pk])
        self.assertEqual(history["maybe_related"], [])
        self.assertNotIn(foreign_order.pk, [row["id"] for row in history["maybe_related"]])
        self.assertNotIn("حدث الشركة الأخرى", str(history))
        self.assertNotIn("سرّ الشركة الأخرى", str(history))


class MaybeRelatedTest(ServiceHistoryTestBase):
    def unlinked_order(self, **overrides):
        return self.intake(**overrides)

    def test_an_older_unlinked_order_with_the_same_serial_is_listed_and_stays_unlinked(self):
        old = self.unlinked_order(order_date="2025-03-01", complaint="أمر قديم")

        history = self.history()

        self.assertEqual([row["id"] for row in history["maybe_related"]], [old.pk])
        row = history["maybe_related"][0]
        self.assertEqual(row["order_number"], old.order_number)
        self.assertEqual(row["order_date"], "2025-03-01")
        self.assertEqual(row["complaint"], "أمر قديم")
        self.assertTrue(row["status_label"])
        self.assertEqual(history["timeline"], [])
        old.refresh_from_db()
        self.assertIsNone(old.warranty_card_id)

    def test_reading_the_history_links_nothing(self):
        old = self.unlinked_order(order_date="2025-03-01")

        self.history()
        self.history()

        old.refresh_from_db()
        self.assertIsNone(old.warranty_card_id)
        self.assertEqual(ServiceOrder.objects.filter(warranty_card=self.card).count(), 0)

    def test_the_same_serial_in_another_company_never_appears(self):
        other = self.other_company()
        ServiceOrder.objects.create(
            tenant=other, order_date="2025-03-01", serial=self.card.serial,
            customer_name="زبون الغير", complaint="أمر شركة أخرى",
        )

        self.assertEqual(self.history()["maybe_related"], [])

    def test_an_order_already_linked_to_a_card_is_not_maybe_related(self):
        self.linked_order("2026-06-15")

        history = self.history()

        self.assertEqual(history["maybe_related"], [])
        self.assertEqual(len(history["timeline"]), 1)

    def test_the_serial_matches_exactly_never_as_a_pattern(self):
        self.unlinked_order(order_date="2025-03-01", serial="DEV-10")
        self.unlinked_order(order_date="2025-03-02", serial="XDEV-1")
        self.unlinked_order(order_date="2025-03-03", serial="DEV-%")

        self.assertEqual(self.history()["maybe_related"], [])

    def test_a_card_without_a_serial_has_no_maybe_related(self):
        blank = self.make_card(serial="", device_name="إطارات")
        self.unlinked_order(order_date="2025-03-01", serial="")

        self.assertEqual(self.history(blank)["maybe_related"], [])


class HistoryQueryCountTest(ServiceHistoryTestBase):
    def listing(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(WARRANTIES, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return len(queries), rows

    def test_the_list_does_not_carry_the_history_and_does_not_grow_with_it(self):
        self.linked_order("2026-06-15")
        few_queries, few_rows = self.listing()
        for index in range(4):
            self.linked_order(f"2026-07-0{index + 1}")
            self.extend()
        self.make_card(serial="OTHER-2")

        many_queries, many_rows = self.listing()

        self.assertEqual((len(few_rows), len(many_rows)), (1, 2))
        for row in few_rows + many_rows:
            self.assertNotIn("service_history", row)
        self.assertEqual(few_queries, many_queries)

    def test_the_detail_query_count_is_bounded_by_entries(self):
        self.linked_order("2026-06-15")
        self.extend()
        with CaptureQueriesContext(connection) as few:
            self.detail()
        for index in range(4):
            self.linked_order(f"2026-07-0{index + 1}")
            self.extend()
            self.intake(
                order_date="2025-01-01", duplicate_open_reason="أمر ثانٍ للجهاز نفسه",
            )

        with CaptureQueriesContext(connection) as many:
            self.assertEqual(len(self.history()["timeline"]), 10)

        self.assertEqual(len(few), len(many))


class HistoryGatingTest(ServiceHistoryTestBase):
    def test_the_detail_is_404_without_a_module_license(self):
        self.assertEqual(self.detail()["id"], self.card.pk)
        self.license.delete()

        response = self.client.get(f"{WARRANTIES}{self.card.pk}/", **self.headers())

        self.assertEqual(response.status_code, 404)

    def test_without_the_view_permission_the_detail_is_403(self):
        buyer = User.objects.create_user(username="history-buyer", password="x")
        membership = UserCompanyMembership.objects.create(
            user=buyer, tenant=self.tenant, role="procurement",
        )
        MemberPermission.objects.create(
            membership=membership, permission_key="aftersales.warranty.view", allowed=False,
        )
        self.client.force_authenticate(user=buyer)

        response = self.client.get(f"{WARRANTIES}{self.card.pk}/", **self.headers())

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("service_history", str(response.data))

    def test_another_company_card_is_404(self):
        other = self.other_company()
        foreign = WarrantyCard.objects.create(
            tenant=other, serial="X-1", device_name="جهاز الغير",
            start_date=LONG_AGO, duration_months=12, end_date=FAR_END,
            source=WarrantyCard.SOURCE_MANUAL,
        )

        response = self.client.get(f"{WARRANTIES}{foreign.pk}/", **self.headers())

        self.assertEqual(response.status_code, 404)


class PublicVerifyPageTest(ServiceHistoryTestBase):
    def test_the_public_page_shows_no_service_history(self):
        self.linked_order("2026-06-15", complaint="شكوى-خاصة-٧٧")
        self.intake(
            order_date="2025-03-01", complaint="قديم-خاص-٨٨",
            duplicate_open_reason="أمر ثانٍ للجهاز نفسه",
        )
        self.extend()

        response = APIClient().get(f"/api/w/{self.card.verify_token}")

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for leaked in ("شكوى-خاصة-٧٧", "قديم-خاص-٨٨", "مجاملة", "ربما مرتبطة", "سجل الصيانات"):
            self.assertNotIn(leaked, html)
        self.assertNotIn("service_history", html)


class OrderWarrantyStatusTest(ServiceHistoryTestBase):
    def warrantor(self, name="وكيل لينوفو"):
        return ManufacturerWarrantor.objects.create(tenant=self.tenant, name=name)

    def status_of(self, order):
        response = self.client.get(f"{ORDERS}{order.pk}/", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["warranty_status"]

    def layered_card(self, **overrides):
        return self.make_card(
            serial="LAYER-1", manufacturer_warrantor=self.warrantor(),
            manufacturer_start_date=LONG_AGO, manufacturer_duration_months=24,
            manufacturer_end_date="2998-01-01", **overrides,
        )

    def test_the_status_carries_both_layers_the_flags_and_the_old_keys(self):
        card = self.layered_card()
        order = self.covered_order(card, serial="LAYER-1")

        status = self.status_of(order)

        self.assertEqual(status["id"], card.pk)
        self.assertEqual(status["status"], "active")
        self.assertEqual(status["end_date"], card.end_date)
        self.assertIsInstance(status["days_remaining"], int)
        self.assertIs(status["void"], False)
        self.assertIs(status["ended"], False)
        self.assertEqual(status["manufacturer_status"], "active")
        self.assertEqual(status["manufacturer_end_date"], "2998-01-01")
        self.assertEqual(status["manufacturer_warrantor_name"], "وكيل لينوفو")
        self.assertIsInstance(status["manufacturer_days_remaining"], int)
        self.assertEqual(status["covered_quantity"], 0)
        for key in (
            "coverage_refused", "supplier_warranty_end_date", "supplier_warranty_active",
        ):
            self.assertIn(key, status)

    def test_a_voided_card_shows_void_true_and_the_manufacturer_layer_stays_active(self):
        card = self.layered_card()
        order = self.covered_order(card, serial="LAYER-1")
        self.assertEqual(self.void(card).status_code, 200)

        status = self.status_of(order)

        self.assertIs(status["void"], True)
        self.assertEqual(status["status"], "voided")
        self.assertIs(status["ended"], False)
        self.assertEqual(status["manufacturer_status"], "active")

    def test_an_ended_card_shows_ended_true(self):
        card = self.layered_card()
        order = self.covered_order(card, serial="LAYER-1")
        WarrantyCard.objects.filter(pk=card.pk).update(
            ended_on=timezone.localdate(), end_reason=WarrantyCard.END_RETURNED,
        )

        status = self.status_of(order)

        self.assertIs(status["ended"], True)
        self.assertEqual(status["status"], "ended")
        self.assertIs(status["void"], False)

    def test_a_card_without_a_warrantor_has_a_null_manufacturer_layer(self):
        order = self.covered_order()

        status = self.status_of(order)

        self.assertIsNone(status["manufacturer_status"])
        self.assertIsNone(status["manufacturer_end_date"])
        self.assertEqual(status["manufacturer_warrantor_name"], "")

    def test_an_invoice_card_reports_its_covered_quantity(self):
        card = self.make_card(serial="", device_name="إطارات", quantity=4, returned_quantity=1)
        order = self.intake(
            warranty_card=card.pk, warranty_covered=True, serial="",
            invoice_piece_confirmed=True,
        )

        status = self.status_of(order)

        self.assertEqual(status["covered_quantity"], 3)
        self.assertEqual(status["quantity"], 4)
