"""#245 كفالة ١٧ — استبدال الجهاز تحت الكفالة.

كل اختبار عبر الـAPI: سطر «استبدال» يُضاف على `service-orders/{id}/parts/`، ويُرحَّل
بـ`post-covered/`، ويُسلَّم الأمر بـ`transition/` بنتيجة `replaced`. التسليم يُنهي بطاقة
الجهاز القديم، ويصدر بطاقةً للبديل، ويبدّل الوحدتين في `ProductSerial`.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from after_sales.verify import mask_serial
from after_sales.models import (
    AfterSalesSettings,
    ManufacturerWarrantor,
    ServiceOrder,
    ServiceOrderEvent,
    ServiceOrderPart,
    WarrantyCard,
    WarrantyCardEvent,
    WarrantyPolicy,
)
from inventory.models import Product, ProductSerial
from sales.models import SalesInvoice
from tenants.models import UserCompanyMembership

from .test_service_orders import ORDERS
from .test_warranty_lifecycle import WarrantyReturnTestBase

DELIVERED = ServiceOrder.STATUS_DELIVERED


class ReplacementBase(WarrantyReturnTestBase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.stock_units("OLD-1", "NEW-1", "NEW-2")
        self.sale = self.sales_invoice(serials=["OLD-1"])
        self.assertEqual(self.post_sale(self.sale).status_code, 200)
        self.card = self.cards().get()
        self.old_unit = ProductSerial.objects.get(tenant=self.tenant, serial="OLD-1")

    def unit(self, serial):
        return ProductSerial.objects.get(tenant=self.tenant, serial=serial)

    def order(self, **overrides):
        payload = {
            "order_date": self.today.isoformat(),
            "partner": self.customer.pk,
            "product": self.product.pk,
            "serial": "OLD-1",
            "device_description": "لابتوب",
            "complaint": "لا يعمل",
            "warranty_card": self.card.pk,
            "warranty_covered": True,
            "billing_waived_reason": "استبدال تحت الكفالة",
        }
        payload.update(overrides)
        response = self.client.post(ORDERS, payload, format="json", **self.headers())
        assert response.status_code == 201, response.content
        return ServiceOrder.objects.get(pk=response.data["id"])

    def replace_line(self, order, serial="NEW-1", *, product=None, **overrides):
        payload = {
            "product": (product or self.product).pk,
            "quantity": "1",
            "billing": "covered",
            "serials": [serial] if serial else [],
            "replaces_device": True,
        }
        payload.update(overrides)
        return self.client.post(
            f"{ORDERS}{order.pk}/parts/", payload, format="json", **self.headers(),
        )

    def posted_order(self, serial="NEW-1", **order_overrides):
        order = self.order(**order_overrides)
        response = self.replace_line(order, serial)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.post_covered(order).status_code, 200)
        return order

    def post_covered(self, order):
        return self.client.post(
            f"{ORDERS}{order.pk}/post-covered/", {}, format="json", **self.headers(),
        )

    def transition(self, order, to_status, **body):
        return self.client.post(
            f"{ORDERS}{order.pk}/transition/", {"to_status": to_status, **body},
            format="json", **self.headers(),
        )

    def deliver(self, order, outcome="replaced"):
        return self.transition(order, DELIVERED, outcome=outcome)

    def effects(self, order, outcome="replaced"):
        return self.client.get(
            f"{ORDERS}{order.pk}/delivery-effects/?outcome={outcome}", **self.headers(),
        )

    def new_card(self):
        return WarrantyCard.objects.get(
            tenant=self.tenant, source=WarrantyCard.SOURCE_REPLACEMENT,
        )


# ══════════════════════════════════════════════════════════════════════════
# سطر الاستبدال — شروطه وصلاحيته
# ══════════════════════════════════════════════════════════════════════════

class ReplacementLineTest(ReplacementBase):
    def test_a_covered_serialized_unit_is_added_as_the_replacement_line(self):
        order = self.order()

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 201, response.content)
        part = ServiceOrderPart.objects.get(pk=response.data["id"])
        self.assertTrue(part.replaces_device)
        self.assertEqual(part.serials, ["NEW-1"])
        self.assertFalse(response.data["replacement_product_differs"])

    def test_a_clerk_without_the_replace_permission_is_refused(self):
        order = self.order()
        clerk = User.objects.create_user(username="repl-clerk", password="x")
        UserCompanyMembership.objects.create(user=clerk, tenant=self.tenant, role="sales")
        self.client.force_authenticate(user=clerk)

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(order.parts.exists())

    def test_the_same_clerk_can_still_add_an_ordinary_part(self):
        order = self.order()
        clerk = User.objects.create_user(username="repl-clerk2", password="x")
        UserCompanyMembership.objects.create(user=clerk, tenant=self.tenant, role="sales")
        self.client.force_authenticate(user=clerk)

        response = self.replace_line(order, replaces_device=False)

        self.assertEqual(response.status_code, 201, response.content)

    def test_a_clerk_cannot_flip_an_existing_part_into_a_replacement(self):
        order = self.order()
        part_id = self.replace_line(order, replaces_device=False).data["id"]
        clerk = User.objects.create_user(username="repl-clerk3", password="x")
        UserCompanyMembership.objects.create(user=clerk, tenant=self.tenant, role="sales")
        self.client.force_authenticate(user=clerk)

        response = self.client.patch(
            f"{ORDERS}{order.pk}/parts/{part_id}/", {"replaces_device": True},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 403, response.content)

    def test_quantity_must_be_exactly_one(self):
        order = self.order()

        response = self.replace_line(order, quantity="2", serials=["NEW-1", "NEW-2"])

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("replaces_device", response.data)

    def test_the_serial_is_mandatory(self):
        order = self.order()

        response = self.replace_line(order, serial=None)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("serials", response.data)

    def test_the_line_must_be_covered_not_billable(self):
        order = self.order()

        response = self.replace_line(order, billing="billable")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("replaces_device", response.data)

    def test_a_non_serialized_product_is_refused(self):
        order = self.order()

        response = self.replace_line(order, product=self.plain, serial=None)

        self.assertEqual(response.status_code, 400, response.content)

    def test_the_unit_must_be_in_stock(self):
        order = self.order()

        response = self.replace_line(order, serial="OLD-1")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("serials", response.data)

    def test_an_unknown_serial_is_refused(self):
        order = self.order()

        response = self.replace_line(order, serial="NOPE-9")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("serials", response.data)

    def test_the_orders_own_device_cannot_replace_itself(self):
        order = self.order(serial="NEW-1")

        response = self.replace_line(order, serial="NEW-1")

        self.assertEqual(response.status_code, 400, response.content)

    def test_only_one_replacement_line_per_order(self):
        order = self.order()
        self.assertEqual(self.replace_line(order, "NEW-1").status_code, 201)

        response = self.replace_line(order, "NEW-2")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("replaces_device", response.data)

    def test_an_order_without_a_card_cannot_replace(self):
        order = self.order(warranty_card=None, warranty_covered=False)

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_order_not_marked_covered_cannot_replace(self):
        order = self.order(warranty_covered=False)

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_invoice_card_cannot_be_replaced(self):
        invoice_card = WarrantyCard.objects.create(
            tenant=self.tenant, device_name="كرتون", product=self.plain,
            start_date=self.today, duration_months=12,
            end_date=self.today + timedelta(days=300), quantity=3,
            source=WarrantyCard.SOURCE_AUTO_SALE,
        )
        order = self.order(warranty_card=invoice_card.pk, serial="")
        ServiceOrder.objects.filter(pk=order.pk).update(warranty_covered=True)

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_ended_card_cannot_be_replaced(self):
        order = self.order()
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_voided_card_cannot_be_replaced(self):
        order = self.order()
        WarrantyCard.objects.filter(pk=self.card.pk).update(voided_at=timezone.now())

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_card_whose_dealer_layer_lapsed_on_the_order_date_cannot_be_replaced(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today - timedelta(days=1),
        )
        order = self.order()
        ServiceOrder.objects.filter(pk=order.pk).update(warranty_covered=True)

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_repair_card_cannot_be_replaced(self):
        repair = WarrantyCard.objects.create(
            tenant=self.tenant, source=WarrantyCard.SOURCE_REPAIR, serial="OLD-1",
            product=self.product, start_date=self.today, duration_months=0,
            end_date=self.today + timedelta(days=60), coverage_scope="منفذ الشحن",
        )
        order = self.order(warranty_card=repair.pk)
        ServiceOrder.objects.filter(pk=order.pk).update(warranty_covered=True)

        response = self.replace_line(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_different_product_is_allowed_with_a_warning(self):
        other = Product.objects.create(
            tenant=self.tenant, sku="ALT-1", name_ar="طراز أحدث", is_serialized=True,
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        self.make_policy(other, dealer_months=12)
        self.stock_units("ALT-1", product=other)
        order = self.order()

        response = self.replace_line(order, "ALT-1", product=other)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.data["replacement_product_differs"])
        self.assertTrue(response.data["replacement_warning"])

    def test_an_edit_that_breaks_the_rules_is_refused_and_a_valid_one_passes(self):
        order = self.order()
        part_id = self.replace_line(order).data["id"]

        bad = self.client.patch(
            f"{ORDERS}{order.pk}/parts/{part_id}/", {"quantity": "2"},
            format="json", **self.headers(),
        )
        good = self.client.patch(
            f"{ORDERS}{order.pk}/parts/{part_id}/", {"serials": ["NEW-2"]},
            format="json", **self.headers(),
        )

        self.assertEqual(bad.status_code, 400, bad.content)
        self.assertEqual(good.status_code, 200, good.content)
        self.assertEqual(ServiceOrderPart.objects.get(pk=part_id).serials, ["NEW-2"])


# ══════════════════════════════════════════════════════════════════════════
# الترحيل والتسليم
# ══════════════════════════════════════════════════════════════════════════

class ReplacementDeliveryTest(ReplacementBase):
    def test_posting_the_replacement_line_issues_the_new_unit(self):
        order = self.posted_order()

        self.assertEqual(self.unit("NEW-1").status, ProductSerial.STATUS_ISSUED)
        part = order.parts.get()
        self.assertIsNotNone(part.materialized_at)
        self.assertEqual(part.issued_cost, Decimal("1000.00"))

    def test_delivery_needs_the_replaced_outcome_once_a_replacement_is_posted(self):
        order = self.posted_order()

        response = self.deliver(order, "repaired")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("outcome", response.data)
        order.refresh_from_db()
        self.assertNotEqual(order.status, DELIVERED)

    def test_the_replaced_outcome_without_a_posted_replacement_is_refused(self):
        order = self.order()

        response = self.deliver(order, "replaced")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("outcome", response.data)

    def test_an_unposted_replacement_line_blocks_delivery(self):
        order = self.order()
        self.assertEqual(self.replace_line(order).status_code, 201)

        response = self.deliver(order, "replaced")

        self.assertEqual(response.status_code, 400, response.content)

    def test_delivery_ends_the_old_card_and_issues_the_new_one(self):
        order = self.posted_order()

        response = self.deliver(order)

        self.assertEqual(response.status_code, 200, response.content)
        self.card.refresh_from_db()
        self.assertEqual(self.card.ended_on, self.today)
        self.assertEqual(self.card.end_reason, WarrantyCard.END_SUPERSEDED)
        new = self.new_card()
        self.assertEqual(new.serial, "NEW-1")
        self.assertEqual(new.product_serial_id, self.unit("NEW-1").pk)
        self.assertEqual(new.product_id, self.product.pk)
        self.assertEqual(new.replaces_id, self.card.pk)
        self.assertEqual(new.replacement_order_id, order.pk)
        self.assertEqual(new.start_date, self.today)
        self.assertEqual(new.partner_id, self.customer.pk)
        self.assertEqual(new.sales_invoice_id, self.sale.pk)
        self.assertEqual(new.status_on(self.today), WarrantyCard.STATUS_ACTIVE)
        self.assertNotEqual(new.verify_token, self.card.verify_token)

    def test_the_new_card_keeps_the_longer_of_the_old_end_and_the_repair_days(self):
        order = self.posted_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertEqual(self.new_card().end_date, self.card.end_date)

    def assert_nearly_finished_card_gets_ninety_days(self, repair_days):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today + timedelta(days=10),
        )
        AfterSalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"repair_warranty_days": repair_days},
        )
        order = self.posted_order()

        preview = self.effects(order).data["replacement"]
        self.assertEqual(self.deliver(order).status_code, 200)

        expected = self.today + timedelta(days=90)
        self.assertEqual(self.new_card().end_date, expected)
        self.assertEqual(str(preview["new_end"]), expected.isoformat())

    def test_a_nearly_finished_card_gets_ninety_days_with_the_repair_setting_off(self):
        self.assert_nearly_finished_card_gets_ninety_days(0)

    def test_a_nearly_finished_card_gets_ninety_days_with_a_shorter_repair_setting(self):
        self.assert_nearly_finished_card_gets_ninety_days(30)

    def test_a_card_with_more_than_ninety_days_left_keeps_its_own_end(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            end_date=self.today + timedelta(days=200),
        )
        AfterSalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"repair_warranty_days": 0},
        )
        order = self.posted_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertEqual(self.new_card().end_date, self.today + timedelta(days=200))

    def test_the_new_card_carries_the_old_cards_terms_not_the_new_products_policy(self):
        WarrantyCard.objects.filter(pk=self.card.pk).update(terms_text="شروط الزبون الأصلية")
        WarrantyPolicy.objects.filter(product=self.product).update(
            terms_override="شروط سياسة المنتج الجديد",
        )
        AfterSalesSettings.objects.update_or_create(
            tenant=self.tenant, defaults={"default_terms": "شروط الشركة العامة"},
        )
        order = self.posted_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertEqual(self.new_card().terms_text, "شروط الزبون الأصلية")

    def test_the_manufacturer_layer_is_resolved_for_the_new_unit_from_the_delivery_date(self):
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="وكيل")
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor, manufacturer_months=24,
        )
        order = self.posted_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        new = self.new_card()
        self.assertEqual(new.manufacturer_warrantor_id, warrantor.pk)
        self.assertEqual(new.manufacturer_start_date, self.today)
        self.assertEqual(new.manufacturer_duration_months, 24)
        self.assertIsNotNone(new.supplier_warranty_end_date)

    def test_the_units_swap_on_the_original_sales_line(self):
        sales_line = self.old_unit.sales_line
        order = self.posted_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        new_unit, old_unit = self.unit("NEW-1"), self.unit("OLD-1")
        self.assertEqual(new_unit.status, ProductSerial.STATUS_SOLD)
        self.assertEqual(new_unit.sales_line_id, sales_line.pk)
        self.assertEqual(old_unit.status, ProductSerial.STATUS_DEFECTIVE)
        self.assertEqual(old_unit.sales_line_id, sales_line.pk)

    def test_without_a_sales_line_the_replacement_stays_issued(self):
        manual = WarrantyCard.objects.create(
            tenant=self.tenant, device_name="لابتوب", serial="OLD-1",
            product=self.product, product_serial=self.old_unit,
            start_date=self.today - timedelta(days=5), duration_months=12,
            end_date=self.today + timedelta(days=300),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )
        ProductSerial.objects.filter(pk=self.old_unit.pk).update(
            status=ProductSerial.STATUS_IN_STOCK, sales_line=None,
        )
        order = self.posted_order(warranty_card=manual.pk)

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertEqual(self.unit("NEW-1").status, ProductSerial.STATUS_ISSUED)
        self.assertEqual(self.new_card().replaces_id, manual.pk)

    def test_both_cards_and_the_order_record_the_replacement(self):
        order = self.posted_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        new = self.new_card()
        for card in (self.card, new):
            event = WarrantyCardEvent.objects.get(
                card=card, event_type=WarrantyCardEvent.TYPE_REPLACEMENT,
            )
            self.assertEqual(event.service_order_id, order.pk)
            self.assertIn(order.order_number, event.text)
        self.assertTrue(
            ServiceOrderEvent.objects.filter(
                order=order, event_type=ServiceOrderEvent.TYPE_WARRANTY,
                text__contains="استُبدل",
            ).exists()
        )

    def test_no_shop_days_extension_and_no_repair_card_on_a_replacement(self):
        order = self.posted_order()

        self.assertEqual(self.deliver(order).status_code, 200)

        self.assertFalse(
            WarrantyCard.objects.filter(source=WarrantyCard.SOURCE_REPAIR).exists()
        )
        self.assertFalse(
            WarrantyCardEvent.objects.filter(
                event_type=WarrantyCardEvent.TYPE_EXTEND,
            ).exists()
        )

    def test_delivery_fails_whole_when_the_card_ended_after_posting(self):
        order = self.posted_order()
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )

        response = self.deliver(order)

        self.assertEqual(response.status_code, 400, response.content)
        order.refresh_from_db()
        self.assertNotEqual(order.status, DELIVERED)
        self.assertFalse(
            WarrantyCard.objects.filter(source=WarrantyCard.SOURCE_REPLACEMENT).exists()
        )
        self.assertEqual(self.unit("NEW-1").status, ProductSerial.STATUS_ISSUED)

    def test_delivery_effects_previews_the_replacement_without_writing(self):
        order = self.posted_order()

        response = self.effects(order)

        self.assertEqual(response.status_code, 200, response.content)
        replacement = response.data["replacement"]
        self.assertTrue(replacement["applies"])
        self.assertEqual(replacement["new_serial"], "NEW-1")
        self.assertEqual(replacement["old_serial"], "OLD-1")
        self.assertTrue(replacement["suggested_waiver_reason"])
        self.assertFalse(
            WarrantyCard.objects.filter(source=WarrantyCard.SOURCE_REPLACEMENT).exists()
        )

    def test_delivery_effects_for_a_normal_outcome_says_no_replacement(self):
        order = self.order()

        response = self.effects(order, "repaired")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["replacement"]["applies"])


# ══════════════════════════════════════════════════════════════════════════
# الحرّاس — ما بعد الاستبدال
# ══════════════════════════════════════════════════════════════════════════

class ReplacementGuardTest(ReplacementBase):
    def replaced(self):
        order = self.posted_order()
        self.assertEqual(self.deliver(order).status_code, 200)
        return order

    def test_the_original_invoice_cannot_be_unposted_while_a_unit_is_defective(self):
        self.replaced()

        response = self.unpost_sale(self.sale)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("OLD-1", response.content.decode("utf-8"))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, SalesInvoice.STATUS_POSTED)
        self.assertEqual(self.unit("NEW-1").status, ProductSerial.STATUS_SOLD)

    def test_a_delivered_replacement_cannot_be_unposted(self):
        order = self.replaced()

        response = self.client.post(
            f"{ORDERS}{order.pk}/unpost-covered/", {}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_returning_the_replacement_unit_ends_the_new_card_as_returned(self):
        self.replaced()
        new = self.new_card()

        sale_return = self.sales_return(self.sale, serials=["NEW-1"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        new.refresh_from_db()
        self.assertEqual(new.end_reason, WarrantyCard.END_RETURNED)
        self.assertEqual(self.unit("NEW-1").status, ProductSerial.STATUS_IN_STOCK)
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_DEFECTIVE)

    def test_a_defective_unit_never_re_enters_the_sellable_stock(self):
        self.replaced()

        resale = self.sales_invoice(serials=["OLD-1"])
        response = self.post_sale(resale)

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_defective_unit_is_not_a_customer_holding_in_the_coverage_check(self):
        self.replaced()

        unit = self.client.get(
            "/api/after-sales/warranties/check/?serial=OLD-1", **self.headers(),
        ).data["unit"]

        self.assertEqual(unit["status"], ProductSerial.STATUS_DEFECTIVE)
        self.assertIsNone(unit["customer_name"])


# ══════════════════════════════════════════════════════════════════════════
# العرض — الشهادة، الصفحة العامة، الفحص، الاستقبال، المسح
# ══════════════════════════════════════════════════════════════════════════

class ReplacementDisplayTest(ReplacementBase):
    def replaced(self):
        order = self.posted_order()
        self.assertEqual(self.deliver(order).status_code, 200)
        return order

    def test_the_new_certificate_says_which_device_it_stands_in_for(self):
        order = self.replaced()
        new = self.new_card()

        response = self.client.post(
            f"/api/after-sales/warranties/print/", {"cards": [new.pk]},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        html = " ".join(response.content.decode("utf-8").split())
        self.assertIn(
            f"بديلاً عن الجهاز {mask_serial('OLD-1')} — أمر {order.order_number}", html,
        )

    def test_the_old_cards_public_page_is_not_valid_and_hides_the_new_card(self):
        self.replaced()
        new = self.new_card()

        response = APIClient().get(f"/api/w/{self.card.verify_token}")
        html = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("هذه الشهادة غير سارية", html)
        self.assertNotIn("NEW-1", html)
        self.assertNotIn(new.verify_token, html)
        self.assertNotIn("بديل", html)

    def test_the_coverage_check_on_the_old_serial_names_the_replacement(self):
        order = self.replaced()

        data = self.client.get(
            "/api/after-sales/warranties/check/?serial=OLD-1", **self.headers(),
        ).data

        replaced_by = data["replaced_by"]
        self.assertEqual(replaced_by["serial"], "NEW-1")
        self.assertEqual(replaced_by["order_number"], order.order_number)
        self.assertEqual(replaced_by["card"], self.new_card().pk)

    def test_the_coverage_check_on_an_unreplaced_serial_has_no_replacement(self):
        data = self.client.get(
            "/api/after-sales/warranties/check/?serial=OLD-1", **self.headers(),
        ).data

        self.assertIsNone(data["replaced_by"])

    def test_the_intake_lookup_flags_the_replaced_card_row(self):
        order = self.replaced()

        response = self.client.get(f"{ORDERS}lookup/?q=OLD-1", **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        rows = [result["card"] for result in response.data["results"]]
        replaced = [c for c in rows if c.get("replaced_by")]
        self.assertEqual(len(replaced), 1, response.data)
        self.assertEqual(replaced[0]["replaced_by"]["serial"], "NEW-1")
        self.assertEqual(replaced[0]["replaced_by"]["order_number"], order.order_number)

    def test_the_scan_of_the_old_serial_carries_the_replacement(self):
        self.replaced()

        response = self.client.get("/api/scan/?q=OLD-1", **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        unit = [m for m in response.json()["matches"] if m["type"] == "unit"]
        self.assertEqual(len(unit), 1, response.json())
        self.assertEqual(unit[0]["warranty"]["replaced_by"]["serial"], "NEW-1")
