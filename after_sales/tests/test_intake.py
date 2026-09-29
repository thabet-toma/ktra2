"""#240 — الاستقبال الموحّد: البحث والحكم والتعبئة.

يثبت عبر الـAPI:
  1. البحث بالهاتف يجد البطاقة نفسها أياً كانت كتابة الرقم (0599 / +970 / 00970 /
     أرقام هندية)، والأقصر من تسعة أرقام يردّ رسالة بلا نتائج.
  2. الحكم `intake_verdict` بترتيبه: منتهية ثم كفالة تاجر ثم إحالة ثم ملغاة ثم
     منتهية مدفوعة، ومعه التعبئة المسبقة (لا `sales_invoice` أبداً).
  3. بطاقة الفاتورة لا تغطّي إلا بتأكيد «القطعة من هذه الفاتورة».
  4. الأمر المكرّر: 409 بالأمر القائم ما لم يُرسَل سببٌ فيُسجَّل حدثاً.
  5. الحصر بالشركة والوحدة والصلاحية، وعدم كسر استدعاء `?serial=` القديم.
"""
import importlib
from datetime import date

from django.contrib.auth.models import User

from after_sales.models import (
    ManufacturerWarrantor,
    ServiceOrder,
    ServiceOrderEvent,
    WarrantyCard,
    phone_key_of,
)
from core.models import TenantModule
from sales.models import SalesInvoice
from tenants.models import UserCompanyMembership
from tenants.services import create_company

from .test_service_orders import ORDERS, ServiceOrderTestBase

LOOKUP = f"{ORDERS}lookup/"
LONG_AGO = "2026-01-01"
FAR_END = "2999-01-01"
PAST_END = "2026-03-01"
DAY = "2026-09-29"


class IntakeTestBase(ServiceOrderTestBase):
    def make_card(self, **overrides):
        fields = {
            "tenant": self.tenant, "serial": "DEV-1", "device_name": "لابتوب",
            "start_date": LONG_AGO, "duration_months": 12, "end_date": FAR_END,
            "source": WarrantyCard.SOURCE_MANUAL,
        }
        fields.update(overrides)
        return WarrantyCard.objects.create(**fields)

    def make_invoice(self, number="S-9001", tenant=None, customer=None):
        return SalesInvoice.objects.create(
            tenant=tenant or self.tenant, invoice_number=number,
            customer=customer or self.customer, currency=self.ils,
            invoice_date="2026-02-01", invoice_type=SalesInvoice.INVOICE_CREDIT,
        )

    def make_invoice_card(self, invoice=None, quantity=3, **overrides):
        invoice = invoice or self.make_invoice()
        return self.make_card(
            serial="", product=self.part_product, sales_invoice=invoice,
            quantity=quantity, partner=self.customer, **overrides,
        )

    def make_warrantor(self):
        return ManufacturerWarrantor.objects.create(tenant=self.tenant, name="المصنع")

    def lookup(self, q, param="q", headers=None):
        return self.client.get(
            LOOKUP, {param: q}, **(headers or self.headers()),
        )

    def one(self, q):
        response = self.lookup(q)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data["results"]), 1, response.data)
        return response.data["results"][0]

    def order_for(self, **body):
        return self.client.post(
            ORDERS,
            {
                "order_date": "2026-09-29", "partner": self.customer.pk,
                "device_description": "لابتوب", "complaint": "لا يشحن", **body,
            },
            format="json", **self.headers(),
        )


class PhoneKeyTest(IntakeTestBase):
    def test_helper_keeps_last_nine_digits_after_converting_arabic_digits(self):
        self.assertEqual(phone_key_of("0599123456"), "599123456")
        self.assertEqual(phone_key_of("+970 599-123-456"), "599123456")
        self.assertEqual(phone_key_of("00970599123456"), "599123456")
        self.assertEqual(phone_key_of("٠٥٩٩١٢٣٤٥٦"), "599123456")
        self.assertEqual(phone_key_of("۰۵۹۹۱۲۳۴۵۶"), "599123456")
        self.assertEqual(phone_key_of("05991234"), "")
        self.assertEqual(phone_key_of(""), "")

    def test_card_fills_phone_key_on_create_and_when_the_phone_changes(self):
        card = self.make_card(customer_phone="0599123456")
        self.assertEqual(card.phone_key, "599123456")

        card.customer_phone = "0568111222"
        card.save(update_fields=["customer_phone", "updated_at"])
        card.refresh_from_db()
        self.assertEqual(card.phone_key, "568111222")

        card.customer_phone = ""
        card.save()
        card.refresh_from_db()
        self.assertEqual(card.phone_key, "")

    def test_the_backfill_migration_does_not_import_live_app_code(self):
        import inspect

        migration = importlib.import_module(
            "after_sales.migrations.0019_backfill_warranty_phone_keys",
        )
        source = inspect.getsource(migration)
        self.assertNotIn("from after_sales", source)
        self.assertNotIn("import after_sales", source)

    def test_the_backfill_migration_normalises_arabic_indic_digits_itself(self):
        migration = importlib.import_module(
            "after_sales.migrations.0019_backfill_warranty_phone_keys",
        )
        card = self.make_card(serial="AR", customer_phone="٠٥٩٩١٢٣٤٥٦")
        WarrantyCard.objects.update(phone_key="")

        migration.fill_phone_keys(WarrantyCard)

        card.refresh_from_db()
        self.assertEqual(card.phone_key, "599123456")

    def test_backfill_helper_fills_rows_written_before_the_column_existed(self):
        migration = importlib.import_module(
            "after_sales.migrations.0019_backfill_warranty_phone_keys",
        )
        first = self.make_card(serial="A", customer_phone="0599123456")
        second = self.make_card(serial="B", customer_phone="+970568111222")
        blank = self.make_card(serial="C")
        WarrantyCard.objects.update(phone_key="")

        migration.fill_phone_keys(WarrantyCard, batch_size=2)

        first.refresh_from_db()
        second.refresh_from_db()
        blank.refresh_from_db()
        self.assertEqual(first.phone_key, "599123456")
        self.assertEqual(second.phone_key, "568111222")
        self.assertEqual(blank.phone_key, "")


class PhoneLookupTest(IntakeTestBase):
    def test_every_spelling_of_the_phone_finds_the_same_card(self):
        card = self.make_card(customer_phone="+970 599-123-456")
        for spelling in ("0599123456", "+970599123456", "00970599123456", "٠٥٩٩١٢٣٤٥٦"):
            with self.subTest(spelling=spelling):
                row = self.one(spelling)
                self.assertEqual(row["card"]["id"], card.pk)
                self.assertEqual(row["matched_on"], "phone")

    def test_fewer_than_nine_digits_returns_the_message_and_no_results(self):
        self.make_card(customer_phone="0599123456")
        response = self.lookup("05991234")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["message"], "اكتب الرقم كاملاً")

    def test_phone_results_are_capped_at_twenty_and_flag_truncation(self):
        for index in range(22):
            self.make_card(serial=f"P-{index}", customer_phone="0599123456")
        response = self.lookup("0599123456")
        self.assertEqual(len(response.data["results"]), 20)
        self.assertTrue(response.data["truncated"])

    def test_a_different_number_never_matches(self):
        self.make_card(customer_phone="0599123456")
        self.assertEqual(self.lookup("0599123457").data["results"], [])


class SerialAndInvoiceLookupTest(IntakeTestBase):
    def test_serial_is_exact_and_marked_matched_on_serial(self):
        card = self.make_card(serial="DEV-1")
        self.make_card(serial="DEV-10")
        row = self.one("DEV-1")
        self.assertEqual(row["card"]["id"], card.pk)
        self.assertEqual(row["matched_on"], "serial")
        self.assertEqual(self.lookup("DEV").data["results"], [])

    def test_invoice_number_matches_exactly_and_ignores_case(self):
        card = self.make_invoice_card(self.make_invoice("S-9001"))
        row = self.one("s-9001")
        self.assertEqual(row["card"]["id"], card.pk)
        self.assertEqual(row["matched_on"], "invoice")
        self.assertEqual(row["card"]["quantity"], 3)
        self.assertEqual(row["card"]["covered_quantity"], 3)

    def test_invoice_search_never_treats_wildcards_as_wildcards(self):
        self.make_invoice_card(self.make_invoice("S-9001"))
        self.assertEqual(self.lookup("S-9%").data["results"], [])
        self.assertEqual(self.lookup("S_9001").data["results"], [])

    def test_legacy_serial_parameter_is_an_alias_of_q(self):
        card = self.make_card(serial="DEV-1")
        response = self.lookup("DEV-1", param="serial")
        self.assertEqual(response.data["results"][0]["card"]["id"], card.pk)
        self.assertIn("warranty", response.data)
        self.assertIn("open_orders", response.data)
        self.assertIn("sensitive_devices", response.data)

    def test_a_sold_unit_without_a_card_is_listed_apart(self):
        from inventory.models import ProductSerial

        unit = ProductSerial.objects.create(
            tenant=self.tenant, product=self.part_product, serial="NOCARD-1",
            status=ProductSerial.STATUS_SOLD,
        )
        response = self.lookup("NOCARD-1")
        self.assertEqual(response.data["results"], [])
        self.assertEqual(
            [row["serial"] for row in response.data["units_without_card"]],
            [unit.serial],
        )

    def test_a_unit_that_has_a_card_is_not_listed_as_without_one(self):
        from inventory.models import ProductSerial

        unit = ProductSerial.objects.create(
            tenant=self.tenant, product=self.part_product, serial="DEV-1",
            status=ProductSerial.STATUS_SOLD,
        )
        self.make_card(serial="DEV-1", product_serial=unit)
        self.assertEqual(self.lookup("DEV-1").data["units_without_card"], [])


class VerdictTest(IntakeTestBase):
    def verdict(self, **card_fields):
        self.make_card(**card_fields)
        return self.one("DEV-1")["verdict"]

    def test_active_dealer_warranty_is_dealer(self):
        self.assertEqual(self.verdict(), "dealer")

    def test_expired_dealer_and_no_manufacturer_is_expired_paid(self):
        self.assertEqual(self.verdict(end_date=PAST_END), "expired_paid")

    def test_expired_dealer_with_active_manufacturer_is_referral(self):
        self.assertEqual(
            self.verdict(
                end_date=PAST_END, manufacturer_warrantor=self.make_warrantor(),
                manufacturer_start_date=LONG_AGO, manufacturer_duration_months=24,
                manufacturer_end_date=FAR_END,
            ),
            "referral",
        )

    def test_voided_with_active_manufacturer_is_referral(self):
        self.assertEqual(
            self.verdict(
                voided_at="2026-05-01T10:00:00Z", void_reason="liquid",
                manufacturer_warrantor=self.make_warrantor(),
                manufacturer_start_date=LONG_AGO, manufacturer_duration_months=24,
                manufacturer_end_date=FAR_END,
            ),
            "referral",
        )

    def test_voided_without_manufacturer_is_voided_paid(self):
        self.assertEqual(
            self.verdict(voided_at="2026-05-01T10:00:00Z", void_reason="liquid"),
            "voided_paid",
        )

    def test_active_dealer_wins_over_active_manufacturer(self):
        self.assertEqual(
            self.verdict(
                manufacturer_warrantor=self.make_warrantor(),
                manufacturer_start_date=LONG_AGO, manufacturer_duration_months=24,
                manufacturer_end_date=FAR_END,
            ),
            "dealer",
        )

    def test_ended_wins_over_everything(self):
        self.assertEqual(
            self.verdict(
                ended_on="2026-05-01", end_reason=WarrantyCard.END_RETURNED,
                manufacturer_warrantor=self.make_warrantor(),
                manufacturer_start_date=LONG_AGO, manufacturer_duration_months=24,
                manufacturer_end_date=FAR_END,
            ),
            "ended",
        )

    def test_invoice_card_fully_returned_is_not_dealer(self):
        card = self.make_invoice_card(quantity=2)
        WarrantyCard.objects.filter(pk=card.pk).update(returned_quantity=2)
        self.assertEqual(self.one("S-9001")["verdict"], "expired_paid")

    def test_row_carries_both_layers_void_and_ended_details(self):
        self.make_card(
            ended_on="2026-05-01", end_reason=WarrantyCard.END_RETURNED,
            manufacturer_warrantor=self.make_warrantor(),
            manufacturer_start_date=LONG_AGO, manufacturer_duration_months=24,
            manufacturer_end_date=FAR_END,
        )
        card = self.one("DEV-1")["card"]
        self.assertEqual(card["manufacturer"]["warrantor"], "المصنع")
        self.assertEqual(str(card["dealer"]["end_date"]), FAR_END)
        self.assertEqual(str(card["manufacturer"]["end_date"]), FAR_END)
        self.assertEqual(card["ended"]["end_reason"], WarrantyCard.END_RETURNED)
        self.assertIsNone(card["void"])

    def test_an_open_order_is_listed_on_the_row(self):
        card = self.make_card()
        order = self.intake(warranty_card=card.pk)
        row = self.one("DEV-1")
        self.assertEqual([o["id"] for o in row["open_orders"]], [order.pk])
        self.assertTrue(row["duplicate_blocked"])
        self.assertEqual(row["verdict"], "dealer")


class PrefillTest(IntakeTestBase):
    def test_dealer_prefills_covered_and_the_live_partner_phone(self):
        card = self.make_card(
            partner=self.customer, customer_name="لقطة", customer_phone="0599555666",
            product=self.part_product,
        )
        prefill = self.one("DEV-1")["prefill"]
        self.assertEqual(prefill["partner"], self.customer.pk)
        self.assertEqual(prefill["customer_name"], self.customer.name)
        self.assertEqual(prefill["customer_phone"], "0599000111")
        self.assertEqual(prefill["product"], self.part_product.pk)
        self.assertEqual(prefill["serial"], "DEV-1")
        self.assertEqual(prefill["device_description"], "لابتوب")
        self.assertEqual(prefill["warranty_card"], card.pk)
        self.assertTrue(prefill["warranty_covered"])

    def test_card_snapshot_is_used_when_there_is_no_partner(self):
        self.make_card(customer_name="زبون خارجي", customer_phone="0599555666")
        prefill = self.one("DEV-1")["prefill"]
        self.assertIsNone(prefill["partner"])
        self.assertEqual(prefill["customer_name"], "زبون خارجي")
        self.assertEqual(prefill["customer_phone"], "0599555666")

    def test_non_dealer_verdicts_are_not_prefilled_as_covered(self):
        card = self.make_card(end_date=PAST_END)
        prefill = self.one("DEV-1")["prefill"]
        self.assertFalse(prefill["warranty_covered"])
        self.assertEqual(prefill["warranty_card"], card.pk)

    def test_ended_card_does_not_prefill_the_customer(self):
        card = self.make_card(
            partner=self.customer, customer_name="لقطة", customer_phone="0599555666",
            ended_on="2026-05-01", end_reason=WarrantyCard.END_RETURNED,
        )
        prefill = self.one("DEV-1")["prefill"]
        self.assertIsNone(prefill["partner"])
        self.assertEqual(prefill["customer_name"], "")
        self.assertEqual(prefill["customer_phone"], "")
        self.assertEqual(prefill["warranty_card"], card.pk)
        self.assertFalse(prefill["warranty_covered"])

    def test_sales_invoice_is_never_prefilled(self):
        self.make_card(sales_invoice=self.make_invoice())
        self.assertNotIn("sales_invoice", self.one("DEV-1")["prefill"])

    def test_the_dealer_state_is_read_through_status_on_not_raw_dates(self):
        from unittest import mock

        self.make_card(end_date=PAST_END)
        with mock.patch.object(
            WarrantyCard, "status_on", return_value=WarrantyCard.STATUS_ACTIVE,
        ):
            self.assertEqual(self.one("DEV-1")["verdict"], "dealer")

    def test_prefill_links_the_latest_card_whatever_its_state(self):
        self.make_card(
            ended_on="2026-04-01", end_reason=WarrantyCard.END_RETURNED,
        )
        newest = self.make_card(end_date=PAST_END)
        response = self.lookup("DEV-1")
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["prefill"]["warranty_card"], newest.pk)


class InvoiceCardConfirmationTest(IntakeTestBase):
    def test_invoice_card_without_confirmation_is_paid_but_linked(self):
        card = self.make_invoice_card()
        response = self.order_for(warranty_card=card.pk, warranty_covered=True)
        self.assertEqual(response.status_code, 201, response.content)
        order = ServiceOrder.objects.get(pk=response.data["id"])
        self.assertEqual(order.warranty_card_id, card.pk)
        self.assertFalse(order.warranty_covered)

    def test_invoice_card_with_confirmation_is_covered(self):
        card = self.make_invoice_card()
        response = self.order_for(
            warranty_card=card.pk, warranty_covered=True, invoice_piece_confirmed=True,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(ServiceOrder.objects.get(pk=response.data["id"]).warranty_covered)

    def test_prefill_asks_for_the_confirmation_on_an_invoice_card_only(self):
        self.make_invoice_card()
        self.assertTrue(self.one("S-9001")["prefill"]["requires_item_confirm"])
        self.make_card(serial="DEV-1")
        self.assertFalse(self.one("DEV-1")["prefill"]["requires_item_confirm"])

    def test_serial_card_needs_no_confirmation(self):
        card = self.make_card()
        order = self.intake(warranty_card=card.pk, warranty_covered=True)
        self.assertTrue(order.warranty_covered)


class DuplicateOrderTest(IntakeTestBase):
    def test_second_order_on_the_same_card_is_409_with_the_existing_order(self):
        card = self.make_card()
        first = self.intake(warranty_card=card.pk)
        response = self.order_for(warranty_card=card.pk, serial="DEV-1")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.data["code"], "duplicate_open_order")
        self.assertEqual(response.data["existing_order"]["id"], first.pk)
        self.assertEqual(ServiceOrder.objects.filter(tenant=self.tenant).count(), 1)

    def test_a_reason_opens_the_order_and_writes_an_event(self):
        card = self.make_card()
        self.intake(warranty_card=card.pk)
        response = self.order_for(
            warranty_card=card.pk, serial="DEV-1",
            duplicate_open_reason="عطل ثانٍ مختلف",
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = ServiceOrder.objects.get(pk=response.data["id"])
        event = ServiceOrderEvent.objects.filter(order=order, text__contains="عطل ثانٍ مختلف")
        self.assertTrue(event.exists())

    def test_blank_reason_is_not_a_reason(self):
        card = self.make_card()
        self.intake(warranty_card=card.pk)
        response = self.order_for(
            warranty_card=card.pk, serial="DEV-1", duplicate_open_reason="   ",
        )
        self.assertEqual(response.status_code, 409)

    def test_same_serial_without_a_card_is_a_duplicate_too(self):
        self.intake(serial="LOOSE-1")
        self.assertEqual(self.order_for(serial="LOOSE-1").status_code, 409)

    def test_delivered_and_cancelled_orders_do_not_block(self):
        card = self.make_card()
        first = self.intake(warranty_card=card.pk)
        ServiceOrder.objects.filter(pk=first.pk).update(status=ServiceOrder.STATUS_DELIVERED)
        self.assertEqual(
            self.order_for(warranty_card=card.pk, serial="DEV-1").status_code, 201,
        )
        ServiceOrder.objects.filter(tenant=self.tenant).update(
            status=ServiceOrder.STATUS_CANCELLED,
        )
        self.assertEqual(
            self.order_for(warranty_card=card.pk, serial="DEV-1").status_code, 201,
        )

    def test_invoice_card_is_blocked_only_when_open_orders_reach_covered_quantity(self):
        card = self.make_invoice_card(quantity=2)
        body = {"warranty_card": card.pk, "serial": ""}
        self.assertEqual(self.order_for(**body).status_code, 201)
        self.assertEqual(self.order_for(**body).status_code, 201)
        self.assertTrue(self.one("S-9001")["duplicate_blocked"])
        third = self.order_for(**body)
        self.assertEqual(third.status_code, 409, third.content)

    def test_invoice_card_with_room_left_is_not_flagged_blocked(self):
        card = self.make_invoice_card(quantity=2)
        self.assertEqual(
            self.order_for(warranty_card=card.pk, serial="").status_code, 201,
        )
        self.assertFalse(self.one("S-9001")["duplicate_blocked"])


class CardLookupTest(IntakeTestBase):
    def by_card(self, card_id, headers=None):
        return self.client.get(LOOKUP, {"card": card_id}, **(headers or self.headers()))

    def test_a_card_that_is_not_the_latest_of_its_unit_gets_its_own_verdict_and_prefill(self):
        old = self.make_card(ended_on="2026-04-01", end_reason=WarrantyCard.END_RETURNED)
        newest = self.make_card(end_date=PAST_END)

        response = self.by_card(old.pk)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data["results"]), 1, response.data)
        row = response.data["results"][0]
        self.assertEqual(row["card"]["id"], old.pk)
        self.assertEqual(row["verdict"], "ended")
        self.assertEqual(row["prefill"]["warranty_card"], old.pk)
        self.assertNotEqual(row["prefill"]["warranty_card"], newest.pk)

    def test_the_row_has_the_same_shape_as_a_search_row(self):
        self.make_card()
        card = WarrantyCard.objects.get()
        order = self.order_for(serial="DEV-1", warranty_card=card.pk)
        self.assertEqual(order.status_code, 201, order.content)

        by_card = self.by_card(card.pk).data["results"][0]

        self.assertEqual(set(by_card), set(self.one("DEV-1")))
        self.assertEqual(len(by_card["open_orders"]), 1)
        self.assertTrue(by_card["duplicate_blocked"])

    def test_a_card_with_no_serial_no_invoice_and_no_phone_still_resolves(self):
        card = self.make_card(serial="", customer_name="زبون بلا هاتف")

        response = self.by_card(card.pk)

        self.assertEqual(response.status_code, 200, response.content)
        row = response.data["results"][0]
        self.assertEqual(row["card"]["id"], card.pk)
        self.assertEqual(row["verdict"], "dealer")
        self.assertEqual(row["prefill"]["customer_name"], "زبون بلا هاتف")

    def test_another_companys_card_id_is_404(self):
        other_user = User.objects.create_user(username="other-owner", password="x")
        other = create_company("شركة أخرى", other_user)
        theirs = WarrantyCard.objects.create(
            tenant=other, serial="THEIRS-1", start_date=LONG_AGO, end_date=FAR_END,
        )

        self.assertEqual(self.by_card(theirs.pk).status_code, 404)
        self.assertEqual(self.by_card(999999).status_code, 404)
        self.assertEqual(self.by_card("abc").status_code, 404)

    def test_card_mode_has_the_same_gating_as_search(self):
        card = self.make_card()
        outsider = User.objects.create_user(username="no-orders", password="x")
        UserCompanyMembership.objects.create(user=outsider, tenant=self.tenant, role="ess")
        self.client.force_authenticate(user=outsider)
        self.assertEqual(self.by_card(card.pk).status_code, 403)

        self.client.force_authenticate(user=self.user)
        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(
            enabled=False,
        )
        self.assertEqual(self.by_card(card.pk).status_code, 404)


class IntakeAccessTest(IntakeTestBase):
    def test_another_companys_serial_invoice_and_phone_never_match(self):
        other_user = User.objects.create_user(username="other-owner", password="x")
        other = create_company("شركة أخرى", other_user)
        WarrantyCard.objects.create(
            tenant=other, serial="THEIRS-1", customer_phone="0599777888",
            start_date=LONG_AGO, end_date=FAR_END,
        )
        SalesInvoice.objects.create(
            tenant=other, invoice_number="OTHER-1",
            customer=self.customer.__class__.objects.create(
                tenant=other, name="غريب", partner_type="Customer",
            ),
            currency=self.ils, invoice_date="2026-02-01",
            invoice_type=SalesInvoice.INVOICE_CREDIT,
        )
        for term in ("THEIRS-1", "OTHER-1", "0599777888"):
            with self.subTest(term=term):
                self.assertEqual(self.lookup(term).data["results"], [])

    def test_module_off_is_404(self):
        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(
            enabled=False,
        )
        self.assertEqual(self.lookup("DEV-1").status_code, 404)

    def test_user_without_order_permission_is_403(self):
        outsider = User.objects.create_user(username="no-orders", password="x")
        UserCompanyMembership.objects.create(user=outsider, tenant=self.tenant, role="ess")
        self.client.force_authenticate(user=outsider)
        self.assertEqual(self.lookup("DEV-1").status_code, 403)

    def test_a_user_who_can_only_create_orders_may_look_up(self):
        from unittest import mock

        clerk = User.objects.create_user(username="creator", password="x")
        UserCompanyMembership.objects.create(user=clerk, tenant=self.tenant, role="ess")
        self.client.force_authenticate(user=clerk)
        self.assertEqual(self.lookup("DEV-1").status_code, 403)

        with mock.patch(
            "after_sales.views.user_has_perm",
            side_effect=lambda user, tenant, key: key == "aftersales.order.create",
        ):
            self.assertEqual(self.lookup("DEV-1").status_code, 200)
