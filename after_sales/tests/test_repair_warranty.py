"""#244 كفالة ١٦ — كفالة الإصلاح: بطاقةٌ تُنشأ عند تسليم أمرٍ «أُصلح».

كل اختبار عبر الـAPI: `service-orders/{id}/transition/` يسلّم الأمر، و
`service-orders/{id}/delivery-effects/` معاينةٌ لا تكتب. البطاقة المنشأة طبقةٌ
واحدة (`source=repair`): بدايتها يوم التسليم ونهايتها بعد `repair_warranty_days`.
"""
from datetime import date, timedelta
from unittest import mock

from django.utils import timezone

from after_sales.models import (
    AfterSalesSettings,
    ManufacturerWarrantor,
    ServiceOrder,
    ServiceOrderEvent,
    WarrantyCard,
    WarrantyCardEvent,
)

from inventory.models import ProductSerial
from rest_framework.test import APIClient

from .test_service_orders import ORDERS
from .test_shop_days_extension import ShopDaysBase
from .test_warranty_void import WARRANTIES
from .test_warranty_lifecycle import WarrantyReturnTestBase

REPAIR_TERMS = "تشمل الكفالة العطل نفسه أو القطعة المستبدلة فقط."


class RepairBase(ShopDaysBase):
    def setUp(self):
        super().setUp()
        self.end = self.today + timedelta(days=30)
        WarrantyCard.objects.filter(pk=self.card.pk).update(end_date=self.end)
        self.card.refresh_from_db()

    def set_settings(self, **fields):
        AfterSalesSettings.objects.update_or_create(tenant=self.tenant, defaults=fields)

    def paid_order(self, **overrides):
        order = self.intake(
            billing_waived_reason="مدفوع نقداً", resolution="استُبدل منفذ الشحن",
            **overrides,
        )
        self.add_part(order, billing="billable", quantity="1", price="30")
        self.assertEqual(self.transition(order, READY_STATUS).status_code, 200)
        return order

    def repair_cards(self, order=None):
        cards = WarrantyCard.objects.filter(
            tenant=self.tenant, source=WarrantyCard.SOURCE_REPAIR,
        )
        return cards.filter(origin_service_order=order) if order is not None else cards


READY_STATUS = ServiceOrder.STATUS_READY


class RepairCardCreationTest(RepairBase):
    def test_a_paid_repaired_delivery_creates_a_90_day_repair_card(self):
        self.set_settings(repair_terms=REPAIR_TERMS)
        order = self.paid_order()

        response = self.deliver(order)

        self.assertEqual(response.status_code, 200, response.content)
        card = self.repair_cards(order).get()
        self.assertEqual(card.start_date, timezone.localdate())
        self.assertEqual(card.end_date, timezone.localdate() + timedelta(days=90))
        self.assertEqual(card.origin_service_order_id, order.pk)
        self.assertEqual(card.terms_text, REPAIR_TERMS)
        self.assertEqual(card.serial, "DEV-1")
        self.assertEqual(card.partner_id, self.customer.pk)
        self.assertIsNone(card.manufacturer_warrantor_id)
        self.assertIsNone(card.manufacturer_end_date)
        self.assertIsNone(card.sales_invoice_id)
        self.assertIn("استُبدل منفذ الشحن", card.coverage_scope)
        self.assertIn(self.part_product.name_ar, card.coverage_scope)
        self.assertIn("كفالة إصلاح", self.warranty_text(order))

    def test_a_covered_repaired_delivery_also_creates_a_repair_card(self):
        order = self.shop_order(in_shop=10, waiting=0, resolution="تبديل اللوحة")

        self.assertEqual(self.deliver(order).status_code, 200)

        card = self.repair_cards(order).get()
        self.assertEqual(card.end_date, timezone.localdate() + timedelta(days=90))
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=10))

    def test_the_default_is_90_days_without_a_settings_row(self):
        order = self.paid_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        card = self.repair_cards(order).get()
        self.assertEqual((card.end_date - card.start_date).days, 90)

    def test_the_configured_days_are_used(self):
        self.set_settings(repair_warranty_days=30)
        order = self.paid_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        card = self.repair_cards(order).get()
        self.assertEqual((card.end_date - card.start_date).days, 30)

    def test_the_card_and_the_order_each_get_an_event(self):
        order = self.paid_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        card = self.repair_cards(order).get()
        event = WarrantyCardEvent.objects.get(
            card=card, event_type=WarrantyCardEvent.TYPE_REPAIR_ISSUED,
        )
        self.assertEqual(event.service_order_id, order.pk)
        self.assertIn(order.order_number, event.text)
        self.assertIn(f"بطاقة #{card.pk}", self.warranty_text(order))

    def test_the_frozen_scope_is_truncated_to_500_characters(self):
        order = self.paid_order()
        ServiceOrder.objects.filter(pk=order.pk).update(resolution="عطل " * 400)

        self.assertEqual(self.deliver(order).status_code, 200)

        scope = self.repair_cards(order).get().coverage_scope
        self.assertLessEqual(len(scope), 500)
        self.assertTrue(scope.startswith("عطل"))


class RepairCardSkipTest(RepairBase):
    def assert_no_card(self, order, needle=None, outcome="repaired"):
        response = self.deliver(order, outcome)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(self.repair_cards(order).exists())
        if needle is None:
            self.assertNotIn("كفالة إصلاح", self.warranty_text(order))
        else:
            self.assertIn(needle, self.warranty_text(order))

    def test_a_longer_dealer_layer_blocks_the_card_and_the_order_says_why(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today + timedelta(days=100),
        )
        order = self.shop_order(in_shop=10, waiting=0)

        self.assert_no_card(order, "أطول من كفالة الإصلاح")

    def test_the_dealer_end_after_the_shop_days_extension_is_what_counts(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today + timedelta(days=75),
        )
        order = self.shop_order(in_shop=20, waiting=0)

        self.assert_no_card(order, "أطول من كفالة الإصلاح")
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.today + timedelta(days=95))

    def test_a_dealer_layer_ending_first_does_not_block(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today + timedelta(days=60),
        )
        order = self.shop_order(in_shop=10, waiting=0)

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertEqual(self.repair_cards(order).count(), 1)

    def test_a_voided_linked_card_does_not_block(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today + timedelta(days=200), voided_at=timezone.now(),
        )
        order = self.intake(
            warranty_card=self.card.pk, billing_waived_reason="مدفوع",
        )
        self.assertEqual(self.transition(order, READY_STATUS).status_code, 200)

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertEqual(self.repair_cards(order).count(), 1)

    def test_a_zero_setting_disables_the_card(self):
        self.set_settings(repair_warranty_days=0)
        order = self.paid_order()

        self.assert_no_card(order)

    def test_only_a_repaired_outcome_creates_a_card(self):
        for outcome in ("unrepaired", "no_fault", "rejected_estimate"):
            with self.subTest(outcome=outcome):
                order = self.paid_order()
                self.assert_no_card(order, outcome=outcome)

    def test_a_second_apply_never_creates_a_second_card(self):
        from after_sales.service_orders import apply_repair_warranty

        order = self.paid_order()
        self.assertEqual(self.deliver(order).status_code, 200)
        order.refresh_from_db()

        again = apply_repair_warranty(order)

        self.assertFalse(again["creates"])
        self.assertEqual(self.repair_cards(order).count(), 1)
        self.assertEqual(self.deliver(order).status_code, 400)
        self.assertEqual(self.repair_cards(order).count(), 1)

    def test_a_failure_after_the_card_rolls_the_delivery_back(self):
        order = self.paid_order()
        self.client.raise_request_exception = False

        with mock.patch(
            "after_sales.service_orders.logger.info", side_effect=RuntimeError("boom"),
        ):
            response = self.deliver(order)

        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.repair_cards(order).exists())
        self.assertEqual(ServiceOrder.objects.get(pk=order.pk).status, READY_STATUS)
        self.assertFalse(
            ServiceOrderEvent.objects.filter(
                order=order, event_type=ServiceOrderEvent.TYPE_WARRANTY,
            ).exists()
        )


class RepairCardLifecycleTest(WarrantyReturnTestBase):
    """مرجع البيع ينهي بطاقة الإصلاح، وإعادة البيع تُحلّ محلّها، وإلغاء ترحيل البيع لا يمسّها."""

    def sold_unit_with_repair_card(self, serial):
        self.stock_units(serial)
        sale = self.sales_invoice(serials=[serial])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        repair = WarrantyCard.objects.create(
            tenant=self.tenant, source=WarrantyCard.SOURCE_REPAIR, serial=serial,
            product=self.product, start_date=date(2026, 6, 16), duration_months=0,
            end_date=date(2026, 9, 14), coverage_scope="استُبدل منفذ الشحن",
        )
        return sale, repair

    def test_a_sale_return_of_the_unit_ends_its_repair_card_as_returned(self):
        sale, repair = self.sold_unit_with_repair_card("SN-RP1")

        sale_return = self.sales_return(sale, serials=["SN-RP1"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        repair.refresh_from_db()
        self.assertEqual(repair.end_reason, WarrantyCard.END_RETURNED)
        self.assertEqual(repair.ended_on, date(2026, 6, 20))
        self.assertEqual(repair.end_return_line.invoice_id, sale_return.pk)
        self.assertEqual(repair.status_on(date(2026, 6, 21)), "ended")

    def test_a_return_of_another_unit_leaves_the_repair_card_alone(self):
        sale, repair = self.sold_unit_with_repair_card("SN-RP2")
        self.stock_units("SN-RP3")
        other = self.sales_invoice(serials=["SN-RP3"])
        self.assertEqual(self.post_sale(other).status_code, 200)

        self.assertEqual(
            self.post_sale(self.sales_return(other, serials=["SN-RP3"])).status_code, 200,
        )

        repair.refresh_from_db()
        self.assertIsNone(repair.ended_on)

    def test_unposting_the_return_revives_the_repair_card(self):
        sale, repair = self.sold_unit_with_repair_card("SN-RP4")
        sale_return = self.sales_return(sale, serials=["SN-RP4"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        self.assertEqual(self.unpost_sale(sale_return).status_code, 200)

        repair.refresh_from_db()
        self.assertIsNone(repair.ended_on)
        self.assertEqual(repair.end_reason, "")

    def test_a_resale_supersedes_the_live_repair_card(self):
        sale, repair = self.sold_unit_with_repair_card("SN-RP5")
        ProductSerial.objects.filter(tenant=self.tenant, serial="SN-RP5").update(
            status=ProductSerial.STATUS_IN_STOCK, sales_line=None,
        )
        resale = self.sales_invoice(serials=["SN-RP5"])

        self.assertEqual(self.post_sale(resale).status_code, 200)

        repair.refresh_from_db()
        self.assertEqual(repair.end_reason, WarrantyCard.END_SUPERSEDED)
        self.assertEqual(repair.ended_on, date(2026, 6, 15))

    def test_unposting_the_sale_does_not_touch_the_repair_card(self):
        sale, repair = self.sold_unit_with_repair_card("SN-RP6")

        self.assertEqual(self.unpost_sale(sale).status_code, 200)

        repair.refresh_from_db()
        self.assertIsNone(repair.ended_on)
        self.assertEqual(repair.end_reason, "")
        self.assertIsNone(repair.voided_at)


class RepairSurfaceBase(RepairBase):
    """جهازٌ لا كفالة عليه غير كفالة الإصلاح (`REP-1`)، وآخر عليه كفالة بيعٍ وإصلاح معاً (`DEV-1`)."""

    def repaired_card(self, serial="REP-1"):
        order = self.paid_order(serial=serial)
        self.assertEqual(self.deliver(order).status_code, 200)
        return self.repair_cards(order).get(), order

    def lookup(self, q):
        response = self.client.get(f"{ORDERS}lookup/", {"q": q}, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def check(self, serial):
        response = self.client.get(
            f"{WARRANTIES}check/", {"serial": serial}, **self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.data


class RepairCoverageTest(RepairSurfaceBase):
    def test_a_repair_only_device_is_repair_covered_but_not_covered(self):
        card, order = self.repaired_card()

        data = self.check("REP-1")

        self.assertFalse(data["covered"])
        self.assertTrue(data["repair_covered"])
        row = data["cards"][0]
        self.assertEqual(row["id"], card.pk)
        self.assertEqual(row["source"], "repair")
        self.assertEqual(row["source_label"], "كفالة إصلاح")
        self.assertEqual(row["origin_order_number"], order.order_number)
        self.assertEqual(row["coverage_scope"], card.coverage_scope)

    def test_a_sale_card_and_a_repair_card_stay_two_rows_and_both_flags_hold(self):
        card, _order = self.repaired_card(serial="DEV-1")

        data = self.check("DEV-1")

        self.assertTrue(data["covered"])
        self.assertTrue(data["repair_covered"])
        self.assertEqual(
            sorted(row["source"] for row in data["cards"]), ["manual", "repair"],
        )

    def test_an_ended_repair_card_is_not_repair_covered(self):
        card, _order = self.repaired_card()
        WarrantyCard.objects.filter(pk=card.pk).update(
            ended_on=timezone.localdate(), end_reason=WarrantyCard.END_RETURNED,
        )

        data = self.check("REP-1")

        self.assertFalse(data["repair_covered"])
        self.assertEqual(data["cards"], [])

    def test_an_expired_repair_card_is_not_repair_covered(self):
        card, _order = self.repaired_card()
        WarrantyCard.objects.filter(pk=card.pk).update(
            end_date=timezone.localdate() - timedelta(days=1),
        )

        self.assertFalse(self.check("REP-1")["repair_covered"])

    def test_resolve_scan_names_the_card_a_repair_warranty(self):
        from after_sales import verify

        card, order = self.repaired_card()

        response = self.client.get(
            f"{WARRANTIES}resolve-scan/", {"q": verify.verify_url(card)}, **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["source_label"], "كفالة إصلاح")
        self.assertEqual(response.data["origin_order_number"], order.order_number)
        self.assertEqual(response.data["coverage_scope"], card.coverage_scope)
        self.assertNotIn("مكفول", str(response.data))


class RepairIntakeVerdictTest(RepairSurfaceBase):
    def row(self, q, source):
        rows = [r for r in self.lookup(q)["results"] if r["card"]["source"] == source]
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def test_a_repair_only_device_gets_the_repair_verdict(self):
        card, _order = self.repaired_card()

        row = self.lookup("REP-1")["results"][0]

        self.assertEqual(row["verdict"], "repair")
        self.assertEqual(row["card"]["id"], card.pk)
        self.assertEqual(row["card"]["source_label"], "كفالة إصلاح")
        self.assertEqual(row["card"]["coverage_scope"], card.coverage_scope)
        self.assertFalse(row["prefill"]["warranty_covered"])

    def test_the_sale_row_and_the_repair_row_are_never_merged(self):
        self.repaired_card(serial="DEV-1")

        results = self.lookup("DEV-1")["results"]

        self.assertEqual(len(results), 2)
        self.assertEqual(self.row("DEV-1", "manual")["verdict"], "dealer")
        self.assertEqual(self.row("DEV-1", "repair")["verdict"], "repair")

    def test_a_repair_card_beats_referral(self):
        card, _order = self.repaired_card()
        maker = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="المصنع")
        WarrantyCard.objects.filter(pk=card.pk).update(
            manufacturer_warrantor=maker,
            manufacturer_start_date=self.today - timedelta(days=5),
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=300),
        )

        self.assertEqual(self.lookup("REP-1")["results"][0]["verdict"], "repair")

    def test_an_ended_or_expired_repair_card_is_not_the_repair_verdict(self):
        card, _order = self.repaired_card()
        WarrantyCard.objects.filter(pk=card.pk).update(
            end_date=self.today - timedelta(days=1),
        )

        self.assertEqual(self.lookup("REP-1")["results"][0]["verdict"], "expired_paid")

        WarrantyCard.objects.filter(pk=card.pk).update(
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )

        self.assertEqual(self.lookup("REP-1")["results"][0]["verdict"], "ended")

    def test_without_the_fault_confirmation_the_order_is_paid_and_linked(self):
        card, _order = self.repaired_card()

        response = self.client.post(
            ORDERS,
            {
                "order_date": "2026-09-29", "partner": self.customer.pk,
                "serial": "REP-1", "device_description": "لابتوب",
                "complaint": "ما زال يشحن ببطء", "warranty_card": card.pk,
                "warranty_covered": True,
            },
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)
        order = ServiceOrder.objects.get(pk=response.data["id"])
        self.assertEqual(order.warranty_card_id, card.pk)
        self.assertFalse(order.warranty_covered)

    def test_with_the_fault_confirmation_the_order_is_covered(self):
        card, _order = self.repaired_card()

        response = self.client.post(
            ORDERS,
            {
                "order_date": "2026-09-29", "partner": self.customer.pk,
                "serial": "REP-1", "device_description": "لابتوب",
                "complaint": "عاد العطل نفسه", "warranty_card": card.pk,
                "warranty_covered": True, "repair_fault_confirmed": True,
            },
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)
        order = ServiceOrder.objects.get(pk=response.data["id"])
        self.assertTrue(order.warranty_covered)

    def test_the_confirmation_does_not_cover_an_expired_repair_card(self):
        card, _order = self.repaired_card()
        WarrantyCard.objects.filter(pk=card.pk).update(
            end_date=self.today - timedelta(days=1),
        )

        response = self.client.post(
            ORDERS,
            {
                "order_date": "2026-09-29", "partner": self.customer.pk,
                "serial": "REP-1", "device_description": "لابتوب",
                "complaint": "عاد العطل", "warranty_card": card.pk,
                "warranty_covered": True, "repair_fault_confirmed": True,
            },
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(ServiceOrder.objects.get(pk=response.data["id"]).warranty_covered)


class RepairCardEditFreezeTest(RepairSurfaceBase):
    """مراجعة: التجميد ومنع التقصير بالتعديل كانا للتلقائية وحدها (#222 بند ٨)."""

    def edit(self, card, **body):
        return self.client.patch(
            f"{WARRANTIES}{card.pk}/", body, format="json", **self.headers(),
        )

    def test_shortening_a_repair_card_by_editing_is_refused(self):
        card, _order = self.repaired_card()

        response = self.edit(card, end_date=(card.end_date - timedelta(days=10)).isoformat())

        self.assertEqual(response.status_code, 400, response.content)
        card.refresh_from_db()
        self.assertEqual(card.end_date, card.start_date + timedelta(days=90))

    def test_the_serial_of_a_repair_card_is_frozen(self):
        card, _order = self.repaired_card()

        response = self.edit(card, serial="OTHER-SERIAL")

        self.assertEqual(response.status_code, 400, response.content)
        card.refresh_from_db()
        self.assertEqual(card.serial, "REP-1")

    def test_notes_on_a_repair_card_stay_editable(self):
        card, _order = self.repaired_card()

        response = self.edit(card, notes="اتصل الزبون")

        self.assertEqual(response.status_code, 200, response.content)


class RepairPublicPageTest(RepairSurfaceBase):
    def open(self, card):
        return APIClient().get(f"/api/w/{card.verify_token}")

    def test_the_public_page_says_repair_warranty_without_order_or_scope(self):
        """المواصفة: «ولا يُعرض النطاق»، و«ما لا يُعرض أبداً: … الصيانات»."""
        card, order = self.repaired_card()

        response = self.open(card)
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("كفالة إصلاح", html)
        self.assertNotIn(order.order_number, html)
        self.assertNotIn("استُبدل منفذ الشحن", html)
        self.assertIn("سارية", html)
        self.assertNotIn("مكفول", html)
        self.assertNotIn("كفالة التاجر", html)
        self.assertNotIn("كفالة المصنع", html)

    def test_the_public_page_leaks_no_price_and_no_notes(self):
        card, _order = self.repaired_card()
        WarrantyCard.objects.filter(pk=card.pk).update(
            notes="ZZ-NOTES-LEAK", terms_text="ZZ-TERMS-LEAK",
        )

        html = self.open(card).content.decode("utf-8")

        for secret in ("ZZ-NOTES-LEAK", "ZZ-TERMS-LEAK", "30.00", "مدفوع نقداً"):
            self.assertNotIn(secret, html, secret)

    def test_an_ended_repair_card_shows_the_not_valid_banner(self):
        card, _order = self.repaired_card()
        WarrantyCard.objects.filter(pk=card.pk).update(
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )

        html = self.open(card).content.decode("utf-8")

        self.assertIn("هذه الشهادة غير سارية", html)
        self.assertIn("كفالة إصلاح", html)

    def test_a_sale_card_page_is_unchanged(self):
        html = self.open(self.card).content.decode("utf-8")

        self.assertIn("كفالة التاجر", html)
        self.assertNotIn("كفالة إصلاح", html)


class RepairDeliveryEffectsTest(RepairBase):
    def test_the_preview_states_exactly_what_delivery_creates(self):
        order = self.paid_order()

        preview = self.effects(order)

        self.assertEqual(preview.status_code, 200, preview.content)
        plan = preview.data["repair_warranty"]
        self.assertTrue(plan["creates"])
        self.assertFalse(self.repair_cards(order).exists())

        self.assertEqual(self.deliver(order).status_code, 200)

        card = self.repair_cards(order).get()
        self.assertEqual(str(plan["start"]), str(card.start_date))
        self.assertEqual(str(plan["end"]), str(card.end_date))

    def test_the_preview_uses_the_post_extension_dealer_end(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today + timedelta(days=75),
        )
        order = self.shop_order(in_shop=20, waiting=0)

        plan = self.effects(order).data["repair_warranty"]

        self.assertFalse(plan["creates"])
        self.assertIn("كفالة التاجر", plan["reason"])
        self.assertIsNone(plan["start"])
        self.assertIsNone(plan["end"])

    def test_the_preview_says_why_when_the_outcome_is_not_repaired(self):
        order = self.paid_order()

        plan = self.effects(order, outcome="no_fault").data["repair_warranty"]

        self.assertFalse(plan["creates"])
        self.assertIn("لا كفالة إصلاح", plan["reason"])

    def test_the_preview_without_an_outcome_asks_for_one(self):
        order = self.paid_order()

        plan = self.effects(order, outcome=None).data["repair_warranty"]

        self.assertFalse(plan["creates"])
        self.assertIn("نتيجة", plan["reason"])

    def test_the_preview_says_the_setting_is_off(self):
        self.set_settings(repair_warranty_days=0)
        order = self.paid_order()

        plan = self.effects(order).data["repair_warranty"]

        self.assertFalse(plan["creates"])
        self.assertIn("مُعطَّلة", plan["reason"])

    def test_a_delivered_order_previews_no_second_card(self):
        order = self.paid_order()
        self.assertEqual(self.deliver(order).status_code, 200)

        plan = self.effects(order).data["repair_warranty"]

        self.assertFalse(plan["creates"])


def _sheet_text(response) -> str:
    import re

    html = response.content.decode("utf-8")
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"<svg.*?</svg>", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


class RepairCertificateTest(RepairSurfaceBase):
    def print_(self, *cards):
        return self.client.post(
            f"{WARRANTIES}print/", {"cards": [c.pk for c in cards]},
            format="json", **self.headers(),
        )

    def test_a_repair_card_prints_its_own_layout_with_order_scope_and_dates(self):
        self.set_settings(repair_terms=REPAIR_TERMS)
        card, order = self.repaired_card()

        response = self.print_(card)

        self.assertEqual(response.status_code, 200, response.content)
        text = _sheet_text(response)
        self.assertIn("كفالة إصلاح", text)
        self.assertIn(order.order_number, text)
        self.assertIn(card.coverage_scope, text)
        self.assertIn(card.start_date.strftime("%d/%m/%Y"), text)
        self.assertIn(card.end_date.strftime("%d/%m/%Y"), text)
        self.assertIn(REPAIR_TERMS, text)
        self.assertIn("<svg", response.content.decode("utf-8"))
        self.assertIn("REP-1", text)

    def test_the_repair_sheet_shows_no_dealer_or_manufacturer_layer(self):
        card, _order = self.repaired_card()

        text = _sheet_text(self.print_(card))

        self.assertNotIn("كفالة التاجر", text)
        self.assertNotIn("كفالة المصنع", text)

    def test_printing_writes_the_issued_event_once(self):
        card, _order = self.repaired_card()

        self.assertEqual(self.print_(card).status_code, 200)
        self.assertEqual(self.print_(card).status_code, 200)

        self.assertEqual(
            WarrantyCardEvent.objects.filter(
                card=card, event_type=WarrantyCardEvent.TYPE_ISSUED,
            ).count(), 1,
        )

    def test_a_repair_card_cannot_join_a_multi_card_sheet(self):
        card, _order = self.repaired_card()

        response = self.print_(card, self.card)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("كفالة الإصلاح", str(response.data))

    def test_another_tenants_repair_card_is_not_printable(self):
        card, _order = self.repaired_card()
        from core.models import TenantModule
        from tenants.services import create_company

        other = create_company("شركة إصلاح أخرى ٢٤٤", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)

        response = self.client.post(
            f"{WARRANTIES}print/", {"cards": [card.pk]}, format="json",
            **self.headers(other),
        )

        self.assertEqual(response.status_code, 404, response.content)


class RepairOrderDetailTest(RepairBase):
    def detail(self, order):
        return self.client.get(f"{ORDERS}{order.pk}/", **self.headers())

    def test_the_order_detail_names_its_repair_card_once_delivered(self):
        order = self.paid_order()
        self.assertIsNone(self.detail(order).data["repair_warranty_card"])

        self.assertEqual(self.deliver(order).status_code, 200)

        card = self.repair_cards(order).get()
        self.assertEqual(self.detail(order).data["repair_warranty_card"], card.pk)

    def test_an_order_without_a_repair_card_names_none(self):
        self.set_settings(repair_warranty_days=0)
        order = self.paid_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertIsNone(self.detail(order).data["repair_warranty_card"])