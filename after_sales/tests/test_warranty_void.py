"""#236 — إلغاء كفالة التاجر، ورفضها لهذا العطل، وتقصيرها.

يثبت عبر الـAPI:
  1. «رفض الكفالة لهذا العطل» على أمر: القطع المغطّاة غير المرحّلة تصير مفوترة
     بسعر البيع والبطاقة تبقى فعّالة.
  2. الإلغاء يقلب كفالة التاجر وحدها (المصنع لا يُمسّ) والتغطية `False`.
  3. قطع مغطّاة مرحّلة في أمر مفتوح ⇒ رفض الإجراء كلّه واسم الأمر في الرسالة.
  4. التراجع عن الإلغاء يُسجَّل ولا يعيد القطع مغطّاة.
  5. الصلاحية `aftersales.warranty.void` والترخيص والعزل والحالات المرفوضة.
  6. الحارسان الدائمان: الترحيل على بطاقة ملغاة، و`warranty_covered=True` عليها.
  7. التقصير بصلاحية وسبب ولا يُسمّى تمديداً.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from after_sales.models import (
    ManufacturerWarrantor,
    ServiceOrder,
    ServiceOrderEvent,
    ServiceOrderPart,
    WarrantyCard,
    WarrantyCardEvent,
)
from core.models import TenantModule
from inventory.models import Product
from tenants.models import UserCompanyMembership
from tenants.services import create_company

from .test_service_orders import ORDERS, ServiceOrderTestBase

WARRANTIES = "/api/after-sales/warranties/"
LONG_AGO = "2026-01-01"
FAR_END = "2999-01-01"


class VoidTestBase(ServiceOrderTestBase):
    def setUp(self):
        super().setUp()
        self.card = self.make_card()
        self.clerk = User.objects.create_user(username="void-clerk", password="x")
        UserCompanyMembership.objects.create(
            user=self.clerk, tenant=self.tenant, role="sales",
        )

    def make_card(self, **overrides):
        fields = {
            "tenant": self.tenant, "serial": "DEV-1", "device_name": "لابتوب",
            "start_date": LONG_AGO, "duration_months": 12, "end_date": FAR_END,
            "source": WarrantyCard.SOURCE_MANUAL,
        }
        fields.update(overrides)
        return WarrantyCard.objects.create(**fields)

    def covered_order(self, card=None, **overrides):
        card = card or self.card
        return self.intake(
            warranty_card=card.pk, warranty_covered=True, **overrides,
        )

    def void(self, card=None, **body):
        card = card or self.card
        body = {"reason": "liquid", "note": "", **body}
        return self.client.post(
            f"{WARRANTIES}{card.pk}/void/", body, format="json", **self.headers(),
        )

    def unvoid(self, card=None, **body):
        card = card or self.card
        return self.client.post(
            f"{WARRANTIES}{card.pk}/unvoid/", body, format="json", **self.headers(),
        )

    def impact(self, card=None):
        card = card or self.card
        return self.client.get(
            f"{WARRANTIES}{card.pk}/void-impact/", **self.headers(),
        )

    def refuse(self, order, **body):
        body = {"reason": "physical_damage", "note": "", **body}
        return self.client.post(
            f"{ORDERS}{order.pk}/refuse-coverage/", body, format="json", **self.headers(),
        )

    def restore(self, order, **body):
        return self.client.post(
            f"{ORDERS}{order.pk}/restore-coverage/", body, format="json", **self.headers(),
        )

    def shorten(self, card=None, **body):
        card = card or self.card
        return self.client.post(
            f"{WARRANTIES}{card.pk}/shorten/", body, format="json", **self.headers(),
        )

    def as_clerk(self):
        self.client.force_authenticate(user=self.clerk)


# ══════════════════════════════════════════════════════════════════════════
# رفض الكفالة لهذا العطل — على مستوى الأمر
# ══════════════════════════════════════════════════════════════════════════

class RefuseCoverageForThisFaultTest(VoidTestBase):
    def test_refusing_bills_the_covered_parts_and_leaves_the_card_active(self):
        self.part_product.sale_price = Decimal("40")
        self.part_product.save(update_fields=["sale_price"])
        order = self.covered_order()
        part = self.add_part(order, billing="covered", quantity="2", price="0")

        response = self.refuse(order, reason="liquid")

        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        part.refresh_from_db()
        self.card.refresh_from_db()
        self.assertFalse(order.warranty_covered)
        self.assertEqual(part.billing, ServiceOrderPart.BILLING_BILLABLE)
        self.assertEqual(part.unit_price, Decimal("40"))
        self.assertIsNone(self.card.voided_at)
        self.assertEqual(self.card.status_on(date(2026, 6, 20)), "active")
        event = WarrantyCardEvent.objects.get(
            card=self.card, event_type=WarrantyCardEvent.TYPE_COVERAGE_REFUSED,
        )
        self.assertEqual(event.service_order_id, order.pk)
        self.assertEqual(event.reason_code, "liquid")

    def test_an_empty_price_stays_zero_and_the_event_says_so(self):
        order = self.covered_order()
        part = self.add_part(order, billing="covered", quantity="1", price="0")

        response = self.refuse(order)

        self.assertEqual(response.status_code, 200, response.content)
        part.refresh_from_db()
        self.assertEqual(part.billing, ServiceOrderPart.BILLING_BILLABLE)
        self.assertEqual(part.unit_price, Decimal("0"))
        event = ServiceOrder.objects.get(pk=order.pk).events.filter(
            event_type=ServiceOrderEvent.TYPE_WARRANTY,
        ).first()
        self.assertIsNotNone(event)
        self.assertIn("بلا سعر", event.text)

    def test_the_public_verify_page_does_not_change(self):
        from docshare import services as share_services

        share = share_services.create_share(self.tenant, "warranty_card", self.card.pk)
        public = Client()

        before = public.get(f"/s/{share.token}")
        self.assertEqual(before.status_code, 200)
        before_html = before.content.decode("utf-8")
        self.assertIn("بطاقة كفالة", before_html)
        self.assertNotIn("منتهي", before_html)

        order = self.covered_order()
        self.assertEqual(self.refuse(order).status_code, 200)

        after = public.get(f"/s/{share.token}")
        self.assertEqual(after.status_code, 200)
        after_html = after.content.decode("utf-8")
        self.assertIn("بطاقة كفالة", after_html)
        self.assertNotIn("منتهي", after_html)

    def test_other_reason_needs_a_note(self):
        order = self.covered_order()

        response = self.refuse(order, reason="other", note="  ")

        self.assertEqual(response.status_code, 400, response.content)
        order.refresh_from_db()
        self.assertTrue(order.warranty_covered)

    def test_restoring_needs_a_reason_and_does_not_flip_parts_back(self):
        order = self.covered_order()
        part = self.add_part(order, billing="covered", quantity="1", price="10")
        self.refuse(order)

        short = self.restore(order, reason="خطأ")
        self.assertEqual(short.status_code, 400, short.content)

        response = self.restore(order, reason="تبيّن أن العطل مغطّى")
        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        part.refresh_from_db()
        self.assertTrue(order.warranty_covered)
        self.assertEqual(part.billing, ServiceOrderPart.BILLING_BILLABLE)
        self.assertTrue(WarrantyCardEvent.objects.filter(
            card=self.card, event_type=WarrantyCardEvent.TYPE_COVERAGE_RESTORED,
            service_order=order,
        ).exists())

    def test_restoring_an_order_that_was_never_refused_is_400(self):
        order = self.covered_order()

        response = self.restore(order, reason="لم يُرفض أصلاً")

        self.assertEqual(response.status_code, 400, response.content)

    def test_refusing_with_posted_covered_parts_is_refused_and_names_the_order(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="1")
        self.assertEqual(self.post_covered(order).status_code, 200)

        response = self.refuse(order)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(order.order_number, str(response.data))
        order.refresh_from_db()
        self.assertTrue(order.warranty_covered)


# ══════════════════════════════════════════════════════════════════════════
# إلغاء كفالة التاجر
# ══════════════════════════════════════════════════════════════════════════

class VoidDealerWarrantyTest(VoidTestBase):
    def test_voiding_flips_the_dealer_layer_and_leaves_the_manufacturer_alone(self):
        self.card.manufacturer_warrantor = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="الوكيل الرسمي",
        )
        self.card.manufacturer_start_date = LONG_AGO
        self.card.manufacturer_duration_months = 24
        self.card.manufacturer_end_date = FAR_END
        self.card.save()

        response = self.void(reason="tampered")

        self.assertEqual(response.status_code, 200, response.content)
        self.card.refresh_from_db()
        self.assertIsNotNone(self.card.voided_at)
        self.assertEqual(self.card.voided_by_id, self.user.pk)
        self.assertEqual(self.card.void_reason, "tampered")
        self.assertEqual(self.card.status_on(date(2026, 6, 20)), "voided")
        self.assertEqual(self.card.manufacturer_status_on(date(2026, 6, 20)), "active")
        self.assertEqual(response.data["status"], "voided")
        self.assertEqual(response.data["void"]["reason"], "tampered")
        self.assertTrue(response.data["void"]["reason_label"])
        self.assertTrue(WarrantyCardEvent.objects.filter(
            card=self.card, event_type=WarrantyCardEvent.TYPE_VOID,
            reason_code="tampered",
        ).exists())

    def test_coverage_is_false_for_a_voided_card(self):
        self.void()

        response = self.client.get(
            f"{ORDERS}lookup/?serial=DEV-1", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["warranty"]["covered"])

    def test_the_list_filters_voided_and_drops_it_from_active(self):
        self.void()

        voided = self.client.get(f"{WARRANTIES}?status=voided", **self.headers())
        active = self.client.get(f"{WARRANTIES}?status=active", **self.headers())

        def ids(response):
            rows = response.data["results"] if "results" in response.data else response.data
            return [row["id"] for row in rows]

        self.assertEqual(ids(voided), [self.card.pk])
        self.assertNotIn(self.card.pk, ids(active))

    def test_voiding_bills_open_covered_parts_and_returns_the_order_to_approval(self):
        self.part_product.sale_price = Decimal("30")
        self.part_product.save(update_fields=["sale_price"])
        order = self.covered_order()
        part = self.add_part(order, billing="covered", quantity="1", price="0")
        for status in ("in_diagnosis", "awaiting_approval"):
            self.assertEqual(self.transition(order, status).status_code, 200)
        self.client.post(f"{ORDERS}{order.pk}/approve/", {}, format="json", **self.headers())
        self.assertEqual(self.transition(order, "in_repair").status_code, 200)

        response = self.void(service_order=order.pk)

        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        part.refresh_from_db()
        self.card.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.STATUS_AWAITING_APPROVAL)
        self.assertIsNone(order.approved_at)
        self.assertFalse(order.warranty_covered)
        self.assertEqual(part.billing, ServiceOrderPart.BILLING_BILLABLE)
        self.assertEqual(part.unit_price, Decimal("30"))
        self.assertEqual(self.card.void_service_order_id, order.pk)
        self.assertTrue(order.events.filter(
            event_type=ServiceOrderEvent.TYPE_WARRANTY,
        ).exists())

    def test_delivered_and_cancelled_orders_are_untouched(self):
        cancelled = self.covered_order(serial="DEV-1")
        self.add_part(cancelled, billing="covered", quantity="1")
        self.assertEqual(
            self.transition(cancelled, "cancelled", note="أُلغي").status_code, 200,
        )
        cancelled_part = cancelled.parts.get()

        response = self.void()

        self.assertEqual(response.status_code, 200, response.content)
        cancelled.refresh_from_db()
        cancelled_part.refresh_from_db()
        self.assertTrue(cancelled.warranty_covered)
        self.assertEqual(cancelled_part.billing, ServiceOrderPart.BILLING_COVERED)

    def test_posted_covered_parts_in_an_open_order_refuse_the_whole_void(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="1")
        self.assertEqual(self.post_covered(order).status_code, 200)

        response = self.void()

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(order.order_number, str(response.data))
        self.card.refresh_from_db()
        self.assertIsNone(self.card.voided_at)

    def test_impact_preview_matches_what_the_void_does(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="3", price="12")

        preview = self.impact()

        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertTrue(preview.data["can_void"])
        self.assertEqual(preview.data["orders"][0]["id"], order.pk)
        self.assertEqual(len(preview.data["orders"][0]["parts"]), 1)

        self.void()
        order.refresh_from_db()
        self.assertFalse(order.warranty_covered)
        self.assertEqual(order.parts.get().billing, ServiceOrderPart.BILLING_BILLABLE)

    def test_impact_preview_lists_the_blocker_when_a_part_is_posted(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="1")
        self.post_covered(order)

        preview = self.impact()

        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertFalse(preview.data["can_void"])
        self.assertIn(order.order_number, " ".join(preview.data["blockers"]))

    def test_other_reason_needs_a_note(self):
        response = self.void(reason="other", note="")

        self.assertEqual(response.status_code, 400, response.content)
        self.card.refresh_from_db()
        self.assertIsNone(self.card.voided_at)

    def test_an_unknown_reason_is_400(self):
        self.assertEqual(self.void(reason="ghost").status_code, 400)

    def test_an_already_voided_card_is_400(self):
        self.assertEqual(self.void().status_code, 200)

        self.assertEqual(self.void().status_code, 400)

    def test_an_ended_card_is_400(self):
        self.card.ended_on = date(2026, 6, 1)
        self.card.end_reason = WarrantyCard.END_RETURNED
        self.card.save()

        self.assertEqual(self.void().status_code, 400)

    def test_an_order_of_another_card_is_400(self):
        other_card = self.make_card(serial="DEV-2")
        order = self.covered_order(card=other_card, serial="DEV-2")

        response = self.void(service_order=order.pk)

        self.assertEqual(response.status_code, 400, response.content)

    def test_unvoid_is_logged_and_does_not_flip_parts_back(self):
        order = self.covered_order()
        part = self.add_part(order, billing="covered", quantity="1", price="10")
        self.void()

        short = self.unvoid(reason="خطأ")
        self.assertEqual(short.status_code, 400, short.content)

        response = self.unvoid(reason="أُلغيت بالخطأ")
        self.assertEqual(response.status_code, 200, response.content)
        self.card.refresh_from_db()
        part.refresh_from_db()
        self.assertIsNone(self.card.voided_at)
        self.assertEqual(self.card.void_reason, "")
        self.assertEqual(part.billing, ServiceOrderPart.BILLING_BILLABLE)
        self.assertTrue(WarrantyCardEvent.objects.filter(
            card=self.card, event_type=WarrantyCardEvent.TYPE_UNVOID,
        ).exists())

    def test_unvoiding_a_card_that_is_not_voided_is_400(self):
        self.assertEqual(self.unvoid(reason="لا شيء يُتراجع عنه").status_code, 400)


# ══════════════════════════════════════════════════════════════════════════
# الصلاحية والترخيص والعزل
# ══════════════════════════════════════════════════════════════════════════

class VoidPermissionAndIsolationTest(VoidTestBase):
    def test_without_the_void_permission_every_action_is_403(self):
        order = self.covered_order()
        self.as_clerk()

        calls = [
            ("post", f"{WARRANTIES}{self.card.pk}/void/", {"reason": "liquid"}),
            ("post", f"{WARRANTIES}{self.card.pk}/unvoid/", {"reason": "أُلغيت بالخطأ"}),
            ("get", f"{WARRANTIES}{self.card.pk}/void-impact/", None),
            ("post", f"{WARRANTIES}{self.card.pk}/shorten/",
             {"end_date": "2026-12-31", "reason": "اتفاق مع الزبون"}),
            ("post", f"{ORDERS}{order.pk}/refuse-coverage/", {"reason": "liquid"}),
            ("post", f"{ORDERS}{order.pk}/restore-coverage/", {"reason": "أُلغيت بالخطأ"}),
        ]
        for method, url, body in calls:
            with self.subTest(url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 403, f"{url} → {response.content}")

        self.card.refresh_from_db()
        self.assertIsNone(self.card.voided_at)

    def test_every_action_is_404_without_a_module_license(self):
        order = self.covered_order()
        self.assertEqual(self.impact().status_code, 200)
        self.assertEqual(
            self.client.get(f"{ORDERS}{order.pk}/", **self.headers()).status_code, 200,
        )
        self.license.delete()

        calls = [
            ("post", f"{WARRANTIES}{self.card.pk}/void/", {"reason": "liquid"}),
            ("post", f"{WARRANTIES}{self.card.pk}/unvoid/", {"reason": "أُلغيت بالخطأ"}),
            ("get", f"{WARRANTIES}{self.card.pk}/void-impact/", None),
            ("post", f"{WARRANTIES}{self.card.pk}/shorten/",
             {"end_date": "2026-12-31", "reason": "اتفاق مع الزبون"}),
            ("post", f"{ORDERS}{order.pk}/refuse-coverage/", {"reason": "liquid"}),
            ("post", f"{ORDERS}{order.pk}/restore-coverage/", {"reason": "أُلغيت بالخطأ"}),
        ]
        for method, url, body in calls:
            with self.subTest(url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 404, f"{url} → {response.content}")

    def test_another_company_card_and_order_are_404(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_card = WarrantyCard.objects.create(
            tenant=other, serial="X-1", device_name="جهاز الغير",
            start_date=LONG_AGO, duration_months=12, end_date=FAR_END,
            source=WarrantyCard.SOURCE_MANUAL,
        )
        foreign_order = ServiceOrder.objects.create(
            tenant=other, order_number="SO-X-9", order_date="2026-06-15",
            customer_name="زبون الغير", serial="X-1", warranty_card=foreign_card,
            warranty_covered=True,
        )

        calls = [
            ("post", f"{WARRANTIES}{foreign_card.pk}/void/", {"reason": "liquid"}),
            ("post", f"{WARRANTIES}{foreign_card.pk}/unvoid/", {"reason": "أُلغيت بالخطأ"}),
            ("get", f"{WARRANTIES}{foreign_card.pk}/void-impact/", None),
            ("post", f"{WARRANTIES}{foreign_card.pk}/shorten/",
             {"end_date": "2026-12-31", "reason": "اتفاق مع الزبون"}),
            ("post", f"{ORDERS}{foreign_order.pk}/refuse-coverage/", {"reason": "liquid"}),
            ("post", f"{ORDERS}{foreign_order.pk}/restore-coverage/", {"reason": "أُلغيت بالخطأ"}),
        ]
        for method, url, body in calls:
            with self.subTest(url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 404, f"{url} → {response.content}")

        foreign_card.refresh_from_db()
        self.assertIsNone(foreign_card.voided_at)

    def test_a_service_order_of_another_company_is_400_or_404_never_accepted(self):
        other = create_company("شركة ثانية", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_order = ServiceOrder.objects.create(
            tenant=other, order_number="SO-X-8", order_date="2026-06-15",
            customer_name="زبون الغير", serial="DEV-1",
        )

        response = self.void(service_order=foreign_order.pk)

        self.assertIn(response.status_code, (400, 404), response.content)
        self.card.refresh_from_db()
        self.assertIsNone(self.card.voided_at)


# ══════════════════════════════════════════════════════════════════════════
# الحارسان الدائمان
# ══════════════════════════════════════════════════════════════════════════

class VoidedCardGuardsTest(VoidTestBase):
    def test_posting_covered_parts_on_a_voided_card_is_refused(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="1")
        WarrantyCard.objects.filter(pk=self.card.pk).update(voided_at="2026-06-16T10:00:00Z")

        response = self.post_covered(order)

        self.assertEqual(response.status_code, 400, response.content)
        order.refresh_from_db()
        self.assertIsNone(order.covered_posted_at)

    def test_posting_covered_parts_on_an_ended_card_is_refused(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="1")
        WarrantyCard.objects.filter(pk=self.card.pk).update(
            ended_on=date(2026, 6, 1), end_reason=WarrantyCard.END_RETURNED,
        )

        response = self.post_covered(order)

        self.assertEqual(response.status_code, 400, response.content)

    def test_the_serializer_refuses_covered_true_on_an_order_of_a_voided_card(self):
        self.assertEqual(self.void().status_code, 200)

        created = self.client.post(
            ORDERS,
            {
                "order_date": "2026-06-15", "partner": self.customer.pk,
                "serial": "DEV-1", "warranty_card": self.card.pk,
                "warranty_covered": True,
            },
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 400, created.content)

        order = self.intake(warranty_card=self.card.pk, warranty_covered=False)
        patched = self.client.patch(
            f"{ORDERS}{order.pk}/", {"warranty_covered": True},
            format="json", **self.headers(),
        )
        self.assertEqual(patched.status_code, 400, patched.content)
        order.refresh_from_db()
        self.assertFalse(order.warranty_covered)

    def test_extending_a_voided_card_is_refused(self):
        self.assertEqual(self.void().status_code, 200)

        response = self.client.post(
            f"{WARRANTIES}{self.card.pk}/extend/",
            {"months": 1, "reason": "مجاملة"}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)


# ══════════════════════════════════════════════════════════════════════════
# التقصير — قصّة ٤٤
# ══════════════════════════════════════════════════════════════════════════

class ShortenWarrantyTest(VoidTestBase):
    def test_shortening_logs_old_and_new_dates_with_a_distinct_reason_code(self):
        response = self.shorten(end_date="2026-12-31", reason="اتفاق مع الزبون")

        self.assertEqual(response.status_code, 200, response.content)
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, date(2026, 12, 31))
        event = WarrantyCardEvent.objects.get(
            card=self.card, event_type=WarrantyCardEvent.TYPE_EXTEND,
        )
        self.assertEqual(event.reason_code, WarrantyCardEvent.EXTEND_REASON_SHORTEN)
        self.assertEqual(event.old_end_date, date(2999, 1, 1))
        self.assertEqual(event.new_end_date, date(2026, 12, 31))
        self.assertIn("اتفاق مع الزبون", event.text)

    def test_shortening_needs_a_reason(self):
        response = self.shorten(end_date="2026-12-31", reason="  ")

        self.assertEqual(response.status_code, 400, response.content)
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, date(2999, 1, 1))

    def test_shortening_must_actually_shorten(self):
        response = self.shorten(end_date="3000-01-01", reason="اتفاق مع الزبون")

        self.assertEqual(response.status_code, 400, response.content)

    def test_shortening_below_the_start_date_is_400(self):
        response = self.shorten(end_date="2025-12-31", reason="اتفاق مع الزبون")

        self.assertEqual(response.status_code, 400, response.content)

    def test_shortening_a_voided_or_ended_card_is_400(self):
        self.assertEqual(self.void().status_code, 200)
        self.assertEqual(
            self.shorten(end_date="2026-12-31", reason="اتفاق مع الزبون").status_code, 400,
        )
        ended = self.make_card(
            serial="DEV-3", ended_on=date(2026, 6, 1),
            end_reason=WarrantyCard.END_RETURNED,
        )
        self.assertEqual(
            self.shorten(ended, end_date="2026-12-31", reason="اتفاق مع الزبون").status_code,
            400,
        )


# ══════════════════════════════════════════════════════════════════════════
# جولة المراجعة الوحيدة على #236
# ══════════════════════════════════════════════════════════════════════════

class RefuseRegressesTheOrderTest(VoidTestBase):
    def to_status(self, order, final):
        for status in ("in_diagnosis", "awaiting_approval"):
            self.assertEqual(self.transition(order, status).status_code, 200)
        approved = self.client.post(
            f"{ORDERS}{order.pk}/approve/", {}, format="json", **self.headers(),
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        for status in ("in_repair", "ready"):
            self.assertEqual(self.transition(order, status).status_code, 200)
            if status == final:
                break

    def test_refusing_an_in_repair_order_returns_it_to_awaiting_approval(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="1", price="0")
        self.to_status(order, "in_repair")
        order.refresh_from_db()
        self.assertIsNotNone(order.approved_at)

        response = self.refuse(order)

        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.STATUS_AWAITING_APPROVAL)
        self.assertIsNone(order.approved_at)
        self.assertIsNone(order.approved_by)

    def test_refusing_a_ready_order_returns_it_to_awaiting_approval(self):
        order = self.covered_order()
        self.add_part(order, billing="covered", quantity="1", price="0")
        self.to_status(order, "ready")

        response = self.refuse(order)

        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.STATUS_AWAITING_APPROVAL)
        self.assertIsNone(order.approved_at)


class ClosedCardEditRuleTest(VoidTestBase):
    """#228 «على البطاقة المنتهية أو الملغاة»: الملاحظات وحدها تُعدَّل."""

    def patch(self, card, **body):
        return self.client.patch(
            f"{WARRANTIES}{card.pk}/", body, format="json", **self.headers(),
        )

    def assert_notes_only(self, card):
        blocked = {
            "device_name": "جهاز آخر",
            "end_date": "2998-01-01",
            "supplier_warranty_end_date": "2030-01-01",
            "start_date": "2025-12-01",
        }
        for field, value in blocked.items():
            with self.subTest(field=field):
                response = self.patch(card, **{field: value})
                self.assertEqual(response.status_code, 400, response.content)
        card.refresh_from_db()
        self.assertEqual(card.device_name, "لابتوب")
        self.assertEqual(card.end_date, date(2999, 1, 1))

        response = self.patch(card, notes="ملاحظة جديدة")
        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        self.assertEqual(card.notes, "ملاحظة جديدة")

        same = self.patch(card, notes="أخرى", device_name="لابتوب")
        self.assertEqual(same.status_code, 200, same.content)

    def test_a_voided_card_takes_notes_only(self):
        self.assertEqual(self.void().status_code, 200)

        self.assert_notes_only(self.card)

    def test_an_ended_card_takes_notes_only(self):
        ended = self.make_card(
            serial="DEV-9", ended_on=date(2026, 6, 1),
            end_reason=WarrantyCard.END_RETURNED,
        )

        self.assert_notes_only(ended)


class AutoCardShorteningBypassTest(VoidTestBase):
    def patch(self, card, **body):
        return self.client.patch(
            f"{WARRANTIES}{card.pk}/", body, format="json", **self.headers(),
        )

    def test_patching_an_auto_card_end_date_earlier_points_to_the_shorten_action(self):
        auto = self.make_card(serial="DEV-A", source=WarrantyCard.SOURCE_AUTO_SALE)

        response = self.patch(auto, end_date="2026-12-31")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("زر «تقصير»", str(response.data))
        auto.refresh_from_db()
        self.assertEqual(auto.end_date, date(2999, 1, 1))
        self.assertFalse(WarrantyCardEvent.objects.filter(card=auto).exists())

    def test_an_auto_card_end_date_can_still_be_moved_later(self):
        auto = self.make_card(serial="DEV-B", source=WarrantyCard.SOURCE_AUTO_SALE)

        response = self.patch(auto, end_date="3000-01-01")

        self.assertEqual(response.status_code, 200, response.content)

    def test_a_manual_card_keeps_its_free_end_date_edit(self):
        response = self.patch(self.card, end_date="2026-12-31")

        self.assertEqual(response.status_code, 200, response.content)
        self.card.refresh_from_db()
        self.assertEqual(self.card.end_date, date(2026, 12, 31))


class VoidedCardListQueryCountTest(VoidTestBase):
    def voided_card(self, serial):
        order = self.intake(serial=f"ORDER-{serial}")
        return self.make_card(
            serial=serial, voided_at="2026-06-16T10:00:00Z", voided_by=self.clerk,
            void_reason="liquid", void_service_order=order,
        )

    def listing(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(WARRANTIES, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return len(queries), [row for row in rows if row["void"]]

    def test_the_query_count_does_not_grow_with_more_voided_cards(self):
        self.voided_card("V-1")
        few_queries, few_rows = self.listing()
        for index in range(2, 6):
            self.voided_card(f"V-{index}")

        many_queries, many_rows = self.listing()

        self.assertEqual(len(few_rows), 1)
        self.assertEqual(len(many_rows), 5)
        self.assertEqual(few_queries, many_queries)


class OrderCoverageRefusedFlagTest(VoidTestBase):
    def flag(self, order):
        response = self.client.get(f"{ORDERS}{order.pk}/", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["warranty_status"]["coverage_refused"]

    def test_the_flag_follows_the_latest_refusal_or_restoration(self):
        order = self.covered_order()
        self.assertIs(self.flag(order), False)

        self.assertEqual(self.refuse(order).status_code, 200)
        self.assertIs(self.flag(order), True)

        self.assertEqual(self.restore(order, reason="تبيّن أن العطل مغطّى").status_code, 200)
        self.assertIs(self.flag(order), False)

        self.assertEqual(self.refuse(order).status_code, 200)
        self.assertIs(self.flag(order), True)

    def test_an_uncovered_order_that_was_never_refused_is_not_flagged(self):
        order = self.intake(warranty_card=self.card.pk, warranty_covered=False)

        self.assertIs(self.flag(order), False)

    def test_a_refusal_on_another_order_does_not_flag_this_one(self):
        refused = self.covered_order()
        other = self.intake(
            warranty_card=self.card.pk, warranty_covered=False,
            duplicate_open_reason="أمر ثانٍ لعطل مختلف",
        )
        self.assertEqual(self.refuse(refused).status_code, 200)

        self.assertIs(self.flag(refused), True)
        self.assertIs(self.flag(other), False)
