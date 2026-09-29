"""#243 كفالة ١٥ — التمديد التلقائي بأيام الصيانة عند التسليم.

كل اختبار عبر الـAPI: `service-orders/{id}/transition/` يسلّم الأمر، و
`service-orders/{id}/delivery-effects/` معاينةٌ لا تكتب. تواريخ «جاهز» تُزاح
بتعديل `created_at` للحدث لأن الساعة من الخادم لا من العميل.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.utils import timezone

from after_sales.models import (
    AfterSalesSettings,
    ServiceOrder,
    ServiceOrderEvent,
    WarrantyCard,
    WarrantyCardEvent,
)
from after_sales.service_orders import apply_shop_days_extension
from core.models import TenantModule
from tenants.models import MemberPermission, UserCompanyMembership
from tenants.services import create_company

from .test_service_orders import ORDERS
from .test_warranty_void import WARRANTIES, VoidTestBase

READY = ServiceOrder.STATUS_READY
DELIVERED = ServiceOrder.STATUS_DELIVERED
CERT_PRINT = f"{WARRANTIES}print/"


class ShopDaysBase(VoidTestBase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.end = self.today + timedelta(days=100)
        WarrantyCard.objects.filter(pk=self.card.pk).update(end_date=self.end)
        self.card.refresh_from_db()

    def shop_order(self, *, in_shop=20, waiting=5, card=None, **overrides):
        """أمر مغطّى بدأ قبل `in_shop + waiting` يوماً، وصار «جاهزاً» قبل `waiting` أيام."""
        order = self.covered_order(
            card=card,
            order_date=(self.today - timedelta(days=in_shop + waiting)).isoformat(),
            billing_waived_reason="مغطى بالكفالة",
            **overrides,
        )
        self.make_ready(order, days_ago=waiting)
        return order

    def make_ready(self, order, *, days_ago):
        response = self.transition(order, READY)
        self.assertEqual(response.status_code, 200, response.content)
        last = ServiceOrderEvent.objects.filter(order=order, to_status=READY).latest("id")
        ServiceOrderEvent.objects.filter(pk=last.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago),
        )

    def deliver(self, order, outcome="repaired"):
        return self.transition(order, DELIVERED, outcome=outcome)

    def effects(self, order, outcome="repaired"):
        url = f"{ORDERS}{order.pk}/delivery-effects/"
        if outcome is not None:
            url += f"?outcome={outcome}"
        return self.client.get(url, **self.headers())

    def shop_events(self, card=None):
        return WarrantyCardEvent.objects.filter(
            card=card or self.card, event_type=WarrantyCardEvent.TYPE_EXTEND,
            reason_code=WarrantyCardEvent.EXTEND_REASON_SHOP_DAYS,
        )

    def warranty_text(self, order):
        return " | ".join(
            ServiceOrderEvent.objects.filter(
                order=order, event_type=ServiceOrderEvent.TYPE_WARRANTY,
            ).values_list("text", flat=True)
        )

    def assert_not_extended(self, order, needle, card=None):
        card = card or self.card
        before = card.end_date
        response = self.deliver(order)
        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        self.assertEqual(card.end_date, before)
        self.assertFalse(self.shop_events(card).exists())
        self.assertIn(needle, self.warranty_text(order))


class ShopDaysExtensionTest(ShopDaysBase):
    def test_days_stop_at_the_ready_date_not_at_the_late_pickup(self):
        order = self.shop_order(in_shop=20, waiting=5)

        response = self.deliver(order)

        self.assertEqual(response.status_code, 200, response.content)
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=20))
        event = self.shop_events().get()
        self.assertEqual(event.old_end_date, self.end)
        self.assertEqual(event.new_end_date, self.end + timedelta(days=20))
        self.assertEqual(event.service_order_id, order.pk)
        self.assertIn("مُدِّدت كفالة التاجر 20 يوماً", self.warranty_text(order))

    def test_unrepaired_also_extends(self):
        order = self.shop_order(in_shop=10, waiting=0)

        self.assertEqual(self.deliver(order, "unrepaired").status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=10))

    def test_the_last_ready_counts_after_a_return_to_repair(self):
        order = self.covered_order(
            order_date=(self.today - timedelta(days=25)).isoformat(),
            billing_waived_reason="مغطى بالكفالة",
        )
        self.make_ready(order, days_ago=15)
        self.assertEqual(self.transition(order, ServiceOrder.STATUS_IN_REPAIR).status_code, 200)
        self.make_ready(order, days_ago=8)

        self.assertEqual(self.deliver(order).status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=17))

    def test_start_is_the_earlier_of_the_order_date_and_the_created_date(self):
        order = self.shop_order(in_shop=12, waiting=2)
        ServiceOrder.objects.filter(pk=order.pk).update(
            created_at=timezone.now() - timedelta(days=30),
        )

        self.assertEqual(self.deliver(order).status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=28))

    def test_delivery_without_a_ready_transition_counts_to_the_delivery_date(self):
        order = self.covered_order(
            order_date=(self.today - timedelta(days=9)).isoformat(),
            billing_waived_reason="مغطى بالكفالة",
        )

        self.assertEqual(self.deliver(order).status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=9))

    def test_the_manual_extension_still_writes_the_courtesy_code(self):
        new_end = (self.end + timedelta(days=3)).isoformat()

        response = self.client.post(
            f"{WARRANTIES}{self.card.pk}/extend/", {"end_date": new_end},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        event = WarrantyCardEvent.objects.get(
            card=self.card, event_type=WarrantyCardEvent.TYPE_EXTEND,
        )
        self.assertEqual(event.reason_code, WarrantyCardEvent.EXTEND_REASON_COURTESY)
        self.assertFalse(self.shop_events().exists())


class ShopDaysNoExtensionTest(ShopDaysBase):
    def test_no_fault_does_not_extend_and_the_order_says_why(self):
        order = self.shop_order()
        before = self.card.end_date

        self.assertEqual(self.deliver(order, "no_fault").status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, before)
        self.assertFalse(self.shop_events().exists())
        self.assertIn("لا عطل", self.warranty_text(order))

    def test_rejected_estimate_does_not_extend(self):
        order = self.shop_order()
        before = self.card.end_date

        self.assertEqual(self.deliver(order, "rejected_estimate").status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, before)
        self.assertFalse(self.shop_events().exists())

    def test_an_uncovered_order_does_not_extend(self):
        order = self.shop_order()
        ServiceOrder.objects.filter(pk=order.pk).update(warranty_covered=False)

        self.assert_not_extended(order, "غير مغطى")

    def test_a_voided_card_does_not_extend(self):
        order = self.shop_order()
        WarrantyCard.objects.filter(pk=self.card.pk).update(voided_at=timezone.now())
        self.card.refresh_from_db()

        self.assert_not_extended(order, "ملغاة")

    def test_an_ended_card_does_not_extend(self):
        order = self.shop_order()
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )
        self.card.refresh_from_db()

        self.assert_not_extended(order, "منتهية")

    def test_a_quantity_card_above_one_does_not_extend(self):
        card = self.make_card(serial="", quantity=3, device_name="كيبل")
        card.refresh_from_db()
        order = self.shop_order(card=card, invoice_piece_confirmed=True)
        self.assertTrue(ServiceOrder.objects.get(pk=order.pk).warranty_covered)

        self.assert_not_extended(order, "بطاقة كمية", card=card)

    def test_a_quantity_card_of_one_does_extend(self):
        card = self.make_card(serial="", quantity=1, device_name="كيبل", end_date=self.end)
        order = self.shop_order(in_shop=6, waiting=0, card=card, invoice_piece_confirmed=True)

        self.assertEqual(self.deliver(order).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.end_date, self.end + timedelta(days=6))

    def test_a_card_not_active_on_the_receipt_day_does_not_extend(self):
        order = self.shop_order(in_shop=20, waiting=5)
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today - timedelta(days=40),
        )
        self.card.refresh_from_db()

        self.assert_not_extended(order, "يوم الاستلام")

    def test_zero_shop_days_do_not_extend_and_are_logged(self):
        order = self.covered_order(
            order_date=self.today.isoformat(), billing_waived_reason="مغطى بالكفالة",
        )
        self.make_ready(order, days_ago=0)

        self.assert_not_extended(order, "صفر")

    def test_the_setting_off_stops_the_extension(self):
        AfterSalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"extend_for_shop_days": False},
        )
        order = self.shop_order()

        self.assert_not_extended(order, "إعدادات الكفالة")

    def test_an_order_without_a_card_writes_no_warranty_event(self):
        AfterSalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"repair_warranty_days": 0},
        )
        order = self.intake(billing_waived_reason="بلا كلفة")
        self.assertEqual(self.transition(order, READY).status_code, 200)

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertFalse(
            ServiceOrderEvent.objects.filter(
                order=order, event_type=ServiceOrderEvent.TYPE_WARRANTY,
            ).exists()
        )


class ShopDaysOnceTest(ShopDaysBase):
    def test_the_same_order_never_extends_twice(self):
        order = self.shop_order(in_shop=20, waiting=5)
        self.assertEqual(self.deliver(order).status_code, 200)
        warranty_events = ServiceOrderEvent.objects.filter(
            order=order, event_type=ServiceOrderEvent.TYPE_WARRANTY,
        ).count()

        apply_shop_days_extension(ServiceOrder.objects.get(pk=order.pk))
        apply_shop_days_extension(ServiceOrder.objects.get(pk=order.pk))

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=20))
        self.assertEqual(self.shop_events().count(), 1)
        self.assertEqual(
            ServiceOrderEvent.objects.filter(
                order=order, event_type=ServiceOrderEvent.TYPE_WARRANTY,
            ).count(),
            warranty_events,
        )

    def test_two_orders_of_one_card_each_extend_once(self):
        first = self.shop_order(in_shop=10, waiting=1)
        self.assertEqual(self.deliver(first).status_code, 200)
        second = self.shop_order(in_shop=4, waiting=1)
        self.assertEqual(self.deliver(second).status_code, 200)

        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end + timedelta(days=14))
        self.assertEqual(self.shop_events().count(), 2)


class DeliveryEffectsPreviewTest(ShopDaysBase):
    def test_the_preview_matches_what_delivery_writes(self):
        order = self.shop_order(in_shop=20, waiting=5)

        preview = self.effects(order)

        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertTrue(preview.data["extends"])
        self.assertEqual(preview.data["days"], 20)
        self.assertEqual(str(preview.data["old_end"]), str(self.end))
        self.assertFalse(preview.data["repair_warranty"]["creates"])
        self.assertFalse(self.shop_events().exists())
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end)

        self.assertEqual(self.deliver(order).status_code, 200)

        self.card.refresh_from_db()
        event = self.shop_events().get()
        self.assertEqual(str(preview.data["new_end"]), str(self.card.end_date))
        self.assertEqual((event.new_end_date - event.old_end_date).days, preview.data["days"])

    def test_the_preview_states_the_reason_when_it_does_not_extend(self):
        order = self.shop_order()

        preview = self.effects(order, outcome="no_fault")

        self.assertFalse(preview.data["extends"])
        self.assertIn("لا عطل", preview.data["reason"])
        self.assertEqual(preview.data["days"], 0)

    def test_the_preview_without_an_outcome_asks_for_one(self):
        order = self.shop_order()

        preview = self.effects(order, outcome=None)

        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertFalse(preview.data["extends"])
        self.assertIn("نتيجة", preview.data["reason"])

    def test_an_unknown_outcome_is_400(self):
        order = self.shop_order()

        self.assertEqual(self.effects(order, outcome="whatever").status_code, 400)

    def test_an_order_already_extended_previews_no_second_extension(self):
        order = self.shop_order()
        self.assertEqual(self.deliver(order).status_code, 200)

        preview = self.effects(order)

        self.assertFalse(preview.data["extends"])

    def test_the_detail_response_does_not_carry_the_preview(self):
        order = self.shop_order()

        detail = self.client.get(f"{ORDERS}{order.pk}/", **self.headers())

        self.assertNotIn("delivery_effects", detail.data)


class ShopDaysTransactionTest(ShopDaysBase):
    def test_a_failure_after_the_extension_rolls_the_delivery_back(self):
        order = self.shop_order()
        self.client.raise_request_exception = False

        with mock.patch(
            "after_sales.service_orders.logger.info", side_effect=RuntimeError("boom"),
        ):
            response = self.deliver(order)

        self.assertEqual(response.status_code, 500)
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, self.end)
        self.assertFalse(self.shop_events().exists())
        self.assertEqual(ServiceOrder.objects.get(pk=order.pk).status, READY)
        self.assertEqual(self.warranty_text(order), "")


class ShopDaysCertificateTest(ShopDaysBase):
    def test_the_certificate_shows_the_extension_with_the_order_number(self):
        order = self.shop_order(in_shop=20, waiting=5)
        self.assertEqual(self.deliver(order).status_code, 200)
        order.refresh_from_db()

        response = self.client.post(
            CERT_PRINT, {"cards": [self.card.pk]}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        html = response.content.decode("utf-8")
        self.assertIn(f"مُدِّدت 20 يوماً — صيانة {order.order_number}", " ".join(html.split()))


class ShopDaysGatingAndIsolationTest(ShopDaysBase):
    def test_the_preview_is_404_without_a_module_license(self):
        order = self.shop_order()
        self.assertEqual(self.effects(order).status_code, 200)
        self.license.delete()

        self.assertEqual(self.effects(order).status_code, 404)

    def test_the_preview_is_403_without_the_order_view_permission(self):
        order = self.shop_order()
        membership = UserCompanyMembership.objects.get(user=self.clerk, tenant=self.tenant)
        MemberPermission.objects.create(
            membership=membership, permission_key="aftersales.order.view", allowed=False,
        )
        self.as_clerk()

        self.assertEqual(self.effects(order).status_code, 403)

    def test_another_company_order_is_404_and_untouched(self):
        other = create_company("شركة أخرى", User.objects.create_user(username="o", password="x"))
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_card = WarrantyCard.objects.create(
            tenant=other, serial="X-1", device_name="جهاز الغير",
            start_date="2026-01-01", duration_months=12, end_date=self.end,
            source=WarrantyCard.SOURCE_MANUAL,
        )
        foreign_order = ServiceOrder.objects.create(
            tenant=other, order_number="SO-X-9",
            order_date=self.today - timedelta(days=30), customer_name="زبون الغير",
            serial="X-1", warranty_card=foreign_card, warranty_covered=True,
            status=READY,
        )

        self.assertEqual(self.effects(foreign_order).status_code, 404)
        self.assertEqual(self.deliver(foreign_order).status_code, 404)

        own = self.shop_order()
        self.assertEqual(self.deliver(own).status_code, 200)
        foreign_card.refresh_from_db()
        self.assertEqual(foreign_card.end_date, self.end)
        self.assertFalse(WarrantyCardEvent.objects.filter(card=foreign_card).exists())
