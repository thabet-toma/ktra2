"""الإحالة للوكيل وورقتها (#241) — من واجهة الـAPI وحدها.

ورقة الإحالة لا تُنشئ أمر صيانة، وتُرفض لغير حكم `referral`، وتكتب حدث `referred`؛
والإصلاح المدفوع بطلب الزبون يمرّ بعلَم إنشاءٍ يتحقّق منه الخادم ويكتب التنبيه والقبول.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from after_sales.models import (
    ManufacturerWarrantor,
    ServiceOrder,
    ServiceOrderEvent,
    WarrantyCard,
    WarrantyCardEvent,
)
from core.models import TenantModule
from sales.models import SalesInvoiceLine
from tenants.models import MemberPermission, TenantSettings, UserCompanyMembership
from tenants.services import create_company

from .test_intake import IntakeTestBase
from .test_warranty_certificate import CertificateTestBase, _fmt, _html, _text

BASE = "/api/after-sales/warranties/"
ORDERS = "/api/after-sales/service-orders/"
NO_REFERRAL_TEXT = "لا تُحال هذه البطاقة"


class SlipTestBase(CertificateTestBase):
    def referral_card(self, **overrides) -> WarrantyCard:
        self.mfr_end = self.today + timedelta(days=100)
        self.mfr = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="وكيل-الأجهزة",
            service_center_address="شارع-المركز-القديم", phone="02-111-0000",
        )
        fields = dict(
            serial="SN-REF-1", device_name="هاتف-الإحالة",
            end_date=self.today - timedelta(days=5),
            manufacturer_warrantor=self.mfr, manufacturer_start_date=self.invoice_day,
            manufacturer_duration_months=12, manufacturer_end_date=self.mfr_end,
        )
        fields.update(overrides)
        return self.cert_card(**fields)

    def slip(self, card):
        return self.client.post(
            f"{BASE}{card.pk}/referral-slip/", {}, format="json", **self.headers(),
        )

    def referred(self, card):
        return WarrantyCardEvent.objects.filter(
            card=card, event_type=WarrantyCardEvent.TYPE_REFERRED,
        )


class ReferralSlipContentTest(SlipTestBase):
    def test_slip_prints_the_live_warrantor_address_end_date_qr_invoice_and_both_signatures(self):
        TenantSettings.objects.filter(tenant=self.tenant).update(
            company_name_primary="مؤسسة-الترويسة", address="شارع-الترويسة",
        )
        card = self.referral_card()
        ManufacturerWarrantor.objects.filter(pk=self.mfr.pk).update(
            service_center_address="شارع-المركز-الجديد", phone="09-222-3333",
        )

        response = self.slip(card)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertIn("no-store", response["Cache-Control"])
        html, text = _html(response), _text(response)
        self.assertIn("شارع-المركز-الجديد", text)
        self.assertIn("09-222-3333", text)
        self.assertNotIn("شارع-المركز-القديم", html)
        self.assertNotIn("02-111-0000", html)
        self.assertIn("وكيل-الأجهزة", text)
        self.assertIn(f"كفالة المصنع سارية حتى {_fmt(self.mfr_end)}", text)
        self.assertIn("<svg", html)
        self.assertIn(self.invoice.invoice_number, text)
        self.assertIn(_fmt(self.invoice_day), text)
        self.assertIn("SN-REF-1", text)
        self.assertIn("هاتف-الإحالة", text)
        self.assertIn("مؤسسة-الترويسة", text)
        self.assertIn("ورقة إحالة", text)
        self.assertIn("<b>المحل</b>", html)
        self.assertIn("<b>مركز الخدمة — استلام</b>", html)

    def test_the_customer_is_named_on_the_slip(self):
        card = self.referral_card(customer_name="الزبون-المُحال", customer_phone="0599-777-666")

        text = _text(self.slip(card))

        self.assertIn("الزبون-المُحال", text)
        self.assertIn("0599-777-666", text)

    def test_a_voided_dealer_layer_is_not_mentioned_at_all(self):
        card = self.referral_card(
            voided_at=timezone.now(), void_reason="liquid", void_note="سبب-إلغاء-داخلي",
        )

        response = self.slip(card)

        self.assertEqual(response.status_code, 200, response.content)
        text = _text(response)
        self.assertNotIn("ملغاة", text)
        self.assertNotIn("كفالة التاجر", text)

    def test_a_second_print_carries_the_reprint_mark(self):
        card = self.referral_card()

        self.assertNotIn("إعادة طباعة", _text(self.slip(card)))
        self.assertIn("إعادة طباعة", _text(self.slip(card)))


class ReferralSlipLeakTest(SlipTestBase):
    def test_no_void_reason_note_price_supplier_notes_or_tax_number_reaches_the_paper(self):
        TenantSettings.objects.filter(tenant=self.tenant).update(
            licensed_dealer_no="LIC-5544332", income_tax_file_no="TAX-9988776",
        )
        SalesInvoiceLine.objects.filter(invoice=self.invoice).update(
            unit_price=Decimal("8765.43"),
        )
        self.mfr = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="وكيل-التسريب", phone="02-333-4444",
            service_center_address="عنوان-المركز",
        )
        card = self.cert_card(
            serial="SN-LEAK", notes="ملاحظة-داخلية-للتاجر", supplier=self.supplier,
            end_date=self.today - timedelta(days=5),
            voided_at=timezone.now(), void_reason="liquid", void_note="سبب-إلغاء-داخلي",
            manufacturer_warrantor=self.mfr, manufacturer_start_date=self.invoice_day,
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=100),
        )
        WarrantyCard.objects.filter(pk=card.pk).update(
            supplier_warranty_end_date=self.today + timedelta(days=777),
        )
        void_label = dict(WarrantyCard.VOID_REASON_CHOICES)["liquid"]
        self.mfr.notes = "ملاحظة-الجهة-الداخلية"
        self.mfr.save()

        response = self.slip(card)

        self.assertEqual(response.status_code, 200, response.content)
        html = _html(response)
        for secret in (
            "TAX-9988776", "LIC-5544332", "8765", "ملاحظة-داخلية-للتاجر",
            self.supplier.name, "سبب-إلغاء-داخلي", void_label,
            _fmt(self.today + timedelta(days=777)), "ملاحظة-الجهة-الداخلية",
        ):
            self.assertNotIn(secret, html, secret)


class ReferralSlipVerdictAndEventTest(SlipTestBase):
    def assert_refused(self, card):
        response = self.slip(card)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(NO_REFERRAL_TEXT, str(response.data))
        self.assertFalse(self.referred(card).exists())

    def test_a_dealer_card_is_refused_and_writes_no_event(self):
        self.assert_refused(self.cert_card(end_date=self.today + timedelta(days=30)))

    def test_an_expired_paid_card_is_refused_and_writes_no_event(self):
        self.assert_refused(self.cert_card(end_date=self.today - timedelta(days=5)))

    def test_an_ended_card_is_refused_and_writes_no_event(self):
        card = self.referral_card(
            ended_on=self.today - timedelta(days=1), end_reason=WarrantyCard.END_RETURNED,
        )
        self.assert_refused(card)

    def test_each_print_writes_exactly_one_referred_event_and_no_service_order(self):
        card = self.referral_card()
        orders_before = ServiceOrder.objects.count()

        first = self.slip(card)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(self.referred(card).count(), 1)
        self.slip(card)
        self.assertEqual(self.referred(card).count(), 2)

        event = self.referred(card).first()
        self.assertEqual(event.actor, self.user)
        self.assertEqual(event.reason_code, "print")
        self.assertIn("وكيل-الأجهزة", event.text)
        self.assertEqual(ServiceOrder.objects.count(), orders_before)

    def test_the_referral_shows_in_the_card_history_with_a_label(self):
        card = self.referral_card()
        self.slip(card)

        response = self.client.get(f"{BASE}{card.pk}/events/", **self.headers())

        referred = [e for e in response.data if e["event_type"] == "referred"]
        self.assertEqual(len(referred), 1)
        self.assertEqual(referred[0]["event_type_label"], "إحالة لمركز الوكيل")


class ReferralSlipAccessTest(SlipTestBase):
    def as_viewless_clerk(self):
        clerk = User.objects.create_user(username="ref-clerk", password="x")
        membership = UserCompanyMembership.objects.create(
            user=clerk, tenant=self.tenant, role="procurement",
        )
        MemberPermission.objects.create(
            membership=membership, permission_key="aftersales.warranty.view", allowed=False,
        )
        self.client.force_authenticate(user=clerk)

    def test_without_the_view_permission_it_is_403_and_nothing_is_written(self):
        card = self.referral_card()
        self.as_viewless_clerk()

        self.assertEqual(self.slip(card).status_code, 403)
        self.assertFalse(self.referred(card).exists())

    def test_module_off_is_404_before_the_permission_is_asked(self):
        card = self.referral_card()
        self.as_viewless_clerk()
        self.license.delete()

        self.assertEqual(self.slip(card).status_code, 404)
        self.assertFalse(self.referred(card).exists())

    def test_another_company_card_is_404_and_writes_nothing(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_warrantor = ManufacturerWarrantor.objects.create(tenant=other, name="وكيل الغير")
        foreign = self.make_card(
            tenant=other, serial="X-1", end_date=self.today - timedelta(days=5),
            manufacturer_warrantor=foreign_warrantor,
            manufacturer_start_date=self.invoice_day, manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=100),
        )

        self.assertEqual(self.slip(foreign).status_code, 404)
        self.assertFalse(self.referred(foreign).exists())


class PaidDespiteReferralTest(IntakeTestBase):
    def referral_card(self, **overrides):
        self.mfr_end = "2999-01-01"
        return self.make_card(
            end_date="2026-03-01", manufacturer_warrantor=self.make_warrantor(),
            manufacturer_start_date="2026-01-01", manufacturer_duration_months=24,
            manufacturer_end_date=self.mfr_end, **overrides,
        )

    def test_the_flag_creates_a_paid_order_with_the_warning_and_the_acceptance(self):
        card = self.referral_card()

        response = self.order_for(
            warranty_card=card.pk, warranty_covered=True, paid_despite_referral=True,
        )

        self.assertEqual(response.status_code, 201, response.content)
        order = ServiceOrder.objects.get(pk=response.data["id"])
        self.assertFalse(order.warranty_covered)
        self.assertEqual(order.warranty_card_id, card.pk)
        texts = list(ServiceOrderEvent.objects.filter(order=order).values_list("text", flat=True))
        self.assertTrue(any(
            "كفالة المصنع سارية حتى" in text and "قد يُسقطها" in text for text in texts
        ), texts)
        self.assertTrue(any("وافق" in text and "إصلاح مدفوع" in text for text in texts), texts)
        acceptance = ServiceOrderEvent.objects.filter(order=order, text__contains="وافق").first()
        self.assertEqual(acceptance.actor, self.user)

    def test_the_flag_on_a_dealer_card_is_400_and_creates_no_order(self):
        card = self.make_card()

        response = self.order_for(warranty_card=card.pk, paid_despite_referral=True)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(ServiceOrder.objects.exists())

    def test_the_flag_on_an_expired_paid_card_is_400(self):
        card = self.make_card(end_date="2026-03-01")

        response = self.order_for(warranty_card=card.pk, paid_despite_referral=True)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(ServiceOrder.objects.exists())

    def test_the_flag_without_a_card_is_400(self):
        response = self.order_for(paid_despite_referral=True)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(ServiceOrder.objects.exists())

    def test_an_order_without_the_flag_on_a_referral_card_keeps_its_own_coverage_choice(self):
        card = self.referral_card()

        response = self.order_for(warranty_card=card.pk, warranty_covered=False)

        self.assertEqual(response.status_code, 201, response.content)
        order = ServiceOrder.objects.get(pk=response.data["id"])
        self.assertFalse(
            ServiceOrderEvent.objects.filter(order=order, text__contains="وافق").exists()
        )

    def test_another_company_card_with_the_flag_is_rejected(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign = WarrantyCard.objects.create(
            tenant=other, serial="F-1", device_name="x", start_date="2026-01-01",
            duration_months=1, end_date="2026-03-01", source=WarrantyCard.SOURCE_MANUAL,
            manufacturer_warrantor=ManufacturerWarrantor.objects.create(tenant=other, name="غ"),
            manufacturer_start_date="2026-01-01", manufacturer_duration_months=24,
            manufacturer_end_date="2999-01-01",
        )

        response = self.order_for(warranty_card=foreign.pk, paid_despite_referral=True)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(ServiceOrder.objects.exists())
