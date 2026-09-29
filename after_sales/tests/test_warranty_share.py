"""#239 كفالة ١١ — إرسال الشهادة برابط مشاركة.

كل الاختبارات عبر الـAPI: الموظف يُنشئ الرابط من `POST /api/document-shares/`
والزبون يفتحه بلا مصادقة من `/s/<token>`، فتُقرأ الصفحة كما يقرؤها هو.
"""
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APIClient

from after_sales.models import WarrantyCard, WarrantyCardEvent
from core.models import TenantModule
from core.modules import invalidate_module_cache
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import MemberPermission, TenantSettings, UserCompanyMembership
from tenants.services import create_company

from .test_warranty import SALE_DATE
from .test_warranty_certificate import CertificateTestBase, _fmt, _html, _text

SHARES = "/api/document-shares/"
CERTIFICATE = "warranty_certificate"
CARD = "warranty_card"


class ShareTestBase(CertificateTestBase):
    def setUp(self):
        super().setUp()
        self.visitor = APIClient()

    def share(self, doc_type, doc_id, **extra):
        return self.client.post(
            SHARES, {"doc_type": doc_type, "doc_id": doc_id}, format="json",
            **self.headers(), **extra,
        )

    def page(self, doc_type, doc_id):
        created = self.share(doc_type, doc_id)
        self.assertIn(created.status_code, (200, 201), created.content)
        return self.visitor.get(f"/s/{created.data['token']}")


class SharedPageRendersTheCertificateTest(ShareTestBase):
    def test_invoice_share_link_renders_both_layers_the_qr_and_the_terms(self):
        warrantor = self.warrantor()
        self.cert_card(
            device_name="جهاز-أول", serial="SN-1", terms_text="شرط-مشاركة-١\nشرط-مشاركة-٢",
            manufacturer_warrantor=warrantor, manufacturer_start_date=self.invoice_day,
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=100),
        )
        self.cert_card(device_name="جهاز-ثانٍ", serial="SN-2")
        printed = self.print_(sales_invoice=self.invoice.pk)
        self.assertEqual(printed.status_code, 200, printed.content)

        response = self.page(CERTIFICATE, self.invoice.pk)

        self.assertEqual(response.status_code, 200, response.content)
        html, text = _html(response), _text(response)
        self.assertEqual(html.count("<svg"), 2)
        self.assertEqual(len(re.findall(r'<svg[^>]*width="14(?:\.0+\d*)?mm"', html)), 2)
        self.assertRegex(html, r"<title>[^<]*شهادة كفالة[^<]*</title>")
        self.assertIn("الأجهزة المكفولة (2)", text)
        self.assertIn(self.invoice.invoice_number, text)
        self.assertIn("شرط-مشاركة-١", text)
        self.assertIn("شرط-مشاركة-٢", text)
        self.assertIn("جهاز-أول", html)
        self.assertLess(html.index("جهاز-أول"), html.index("جهاز-ثانٍ"))
        self.assertIn("مركز صيانة المصنع", text)
        self.assertIn("الزبون — استلمت الأجهزة وقرأت الشروط", text)
        self.assertNotIn("<script", html.lower())

    def test_card_share_link_renders_the_single_card_certificate(self):
        card = self.cert_card(device_name="هاتف ذكي فاخر", terms_text="شرط-البطاقة-١")

        response = self.page(CARD, card.pk)

        self.assertEqual(response.status_code, 200, response.content)
        html, text = _html(response), _text(response)
        self.assertEqual(html.count("<svg"), 1)
        self.assertIn('width="25.0mm"', html)
        self.assertRegex(html, r"<title>[^<]*بطاقة كفالة[^<]*</title>")
        self.assertIn("هاتف ذكي فاخر", html)
        self.assertIn("شرط-البطاقة-١", text)
        self.assertIn("الزبون — استلمت الجهاز وقرأت الشروط", text)

    def test_the_page_keeps_the_public_surface_headers(self):
        card = self.cert_card()

        response = self.page(CARD, card.pk)

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("noindex", response["X-Robots-Tag"])

    def test_an_ended_card_share_shows_the_generic_page_never_a_certificate(self):
        card = self.cert_card(ended_on=self.today, end_reason=WarrantyCard.END_RETURNED)

        response = self.page(CARD, card.pk)

        self.assertEqual(response.status_code, 200)
        html = _html(response)
        self.assertNotIn("<svg", html)
        self.assertNotIn("استلمت الجهاز وقرأت الشروط", html)
        self.assertIn("منتهي الصلاحية", html)

    def test_only_the_non_ended_cards_reach_the_invoice_page(self):
        self.cert_card(device_name="جهاز-حيّ", serial="SN-LIVE")
        self.cert_card(
            device_name="جهاز-منتهٍ", serial="SN-DEAD",
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )

        response = self.page(CERTIFICATE, self.invoice.pk)

        html = _html(response)
        self.assertIn("جهاز-حيّ", html)
        self.assertNotIn("جهاز-منتهٍ", html)
        self.assertEqual(html.count("<svg"), 1)

    def test_an_invoice_with_only_ended_cards_cannot_be_shared(self):
        self.cert_card(ended_on=self.today, end_reason=WarrantyCard.END_RETURNED)

        response = self.share(CERTIFICATE, self.invoice.pk)

        self.assertEqual(response.status_code, 404)

    def test_an_invoice_without_cards_cannot_be_shared(self):
        self.assertEqual(self.share(CERTIFICATE, self.invoice.pk).status_code, 404)


class ShareWritesIssuedTest(ShareTestBase):
    def issued_count(self, card):
        return self.issued_events(card).count()

    def test_creating_the_share_writes_issued_once_per_card_with_the_share_channel(self):
        first = self.cert_card(serial="SN-1")
        second = self.cert_card(serial="SN-2")

        response = self.share(CERTIFICATE, self.invoice.pk)

        self.assertEqual(response.status_code, 201, response.content)
        for card in (first, second):
            event = self.issued_events(card).get()
            self.assertEqual(event.reason_code, "share")
            self.assertEqual(event.actor_id, self.user.pk)

    def test_sharing_twice_still_leaves_one_issued_event_per_card(self):
        card = self.cert_card()

        self.share(CERTIFICATE, self.invoice.pk)
        self.share(CERTIFICATE, self.invoice.pk)
        self.share(CARD, card.pk)

        self.assertEqual(self.issued_count(card), 1)

    def test_sharing_a_single_card_writes_issued_with_the_share_channel(self):
        """مراجعة: «`issued`… عند أول طباعة أو مشاركة» — والمشاركة المفردة منها."""
        card = self.cert_card()

        response = self.share(CARD, card.pk)

        self.assertEqual(response.status_code, 201, response.content)
        event = self.issued_events(card).get()
        self.assertEqual(event.reason_code, "share")
        self.assertEqual(event.actor_id, self.user.pk)

    def test_a_card_printed_before_keeps_its_print_event_and_gets_no_second(self):
        printed = self.cert_card(serial="SN-PRINTED")
        fresh = self.cert_card(serial="SN-FRESH")
        self.assertEqual(self.print_(cards=[printed.pk]).status_code, 200)

        self.share(CERTIFICATE, self.invoice.pk)

        self.assertEqual(self.issued_count(printed), 1)
        self.assertEqual(self.issued_events(printed).get().reason_code, "print")
        self.assertEqual(self.issued_events(fresh).get().reason_code, "share")

    def test_an_ended_card_gets_no_issued_event_from_the_invoice_share(self):
        live = self.cert_card(serial="SN-LIVE")
        dead = self.cert_card(
            serial="SN-DEAD", ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )

        self.share(CERTIFICATE, self.invoice.pk)

        self.assertEqual(self.issued_count(live), 1)
        self.assertEqual(self.issued_count(dead), 0)

    def test_the_customer_opening_the_link_never_sees_a_reprint_mark(self):
        card = self.cert_card()
        self.share(CERTIFICATE, self.invoice.pk)
        self.assertEqual(self.issued_count(card), 1)

        response = self.page(CERTIFICATE, self.invoice.pk)

        self.assertNotIn("إعادة طباعة", _text(response))


class SharedPageLeakTest(ShareTestBase):
    def test_no_price_supplier_note_cost_or_tax_number_reaches_the_shared_page(self):
        TenantSettings.objects.filter(tenant=self.tenant).update(
            company_name_primary="مؤسسة-الترويسة",
            licensed_dealer_no="LIC-5544332",
            income_tax_file_no="TAX-9988776",
            address="شارع-الترويسة",
        )
        SalesInvoiceLine.objects.filter(invoice=self.invoice).update(
            unit_price=Decimal("8765.43"),
        )
        self.plain.avg_cost = Decimal("4321.09")
        self.plain.save(update_fields=["avg_cost"])
        card = self.cert_card(
            serial="SN-LEAK", notes="ملاحظة-داخلية-للتاجر",
            supplier=self.supplier,
            supplier_warranty_end_date=self.today + timedelta(days=500),
            manufacturer_warrantor=self.warrantor(),
            manufacturer_start_date=self.invoice_day,
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=100),
            void_note="سبب-إلغاء-داخلي",
        )
        WarrantyCard.objects.filter(pk=card.pk).update(
            supplier_warranty_end_date=self.today + timedelta(days=777),
        )

        for doc_type, doc_id in ((CARD, card.pk), (CERTIFICATE, self.invoice.pk)):
            with self.subTest(doc_type=doc_type):
                response = self.page(doc_type, doc_id)
                self.assertEqual(response.status_code, 200, response.content)
                html, text = _html(response), _text(response)

                self.assertIn("مؤسسة-الترويسة", text)
                self.assertIn("شارع-الترويسة", text)
                for secret in (
                    "TAX-9988776", "LIC-5544332", "8765", "4321", "ملاحظة-داخلية-للتاجر",
                    self.supplier.name, "سبب-إلغاء-داخلي",
                    _fmt(self.today + timedelta(days=777)),
                    _fmt(self.today + timedelta(days=500)),
                ):
                    self.assertNotIn(secret, html, secret)


class GenericPagesAreUntouchedTest(ShareTestBase):
    def test_a_type_without_a_page_hook_still_renders_the_generic_template(self):
        response = self.page("sales_invoice", self.invoice.pk)

        self.assertEqual(response.status_code, 200, response.content)
        html = _html(response)
        self.assertIn('class="doc-kind"', html)
        self.assertIn(self.invoice.invoice_number, html)
        self.assertNotIn("استلمت الجهاز وقرأت الشروط", html)


class ShareGatingTest(ShareTestBase):
    def test_module_off_refuses_the_share_with_404_and_writes_nothing(self):
        card = self.cert_card()
        self.license.delete()
        invalidate_module_cache(self.tenant.pk)

        self.assertEqual(self.share(CERTIFICATE, self.invoice.pk).status_code, 404)
        self.assertEqual(self.share(CARD, card.pk).status_code, 404)
        self.assertFalse(WarrantyCardEvent.objects.filter(card=card).exists())

    def test_a_live_link_answers_410_once_the_module_is_turned_off(self):
        card = self.cert_card()
        created = self.share(CERTIFICATE, self.invoice.pk)
        self.license.delete()
        invalidate_module_cache(self.tenant.pk)

        response = self.visitor.get(f"/s/{created.data['token']}")

        self.assertEqual(response.status_code, 410)
        self.assertNotIn("<svg", _html(response))
        self.assertEqual(self.issued_events(card).count(), 1)

    def test_another_company_invoice_is_404_and_writes_nothing(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_card = self.make_card(tenant=other, serial="X-1")
        foreign_customer = Partner.objects.create(
            tenant=other, name="زبون الغير", partner_type="Customer",
        )
        foreign_invoice = SalesInvoice.objects.create(
            tenant=other, invoice_number="S-FOREIGN-1", customer=foreign_customer,
            currency=self.ils, invoice_date=SALE_DATE,
        )
        WarrantyCard.objects.filter(pk=foreign_card.pk).update(sales_invoice=foreign_invoice)

        self.assertEqual(self.share(CERTIFICATE, foreign_invoice.pk).status_code, 404)
        self.assertEqual(self.share(CARD, foreign_card.pk).status_code, 404)
        self.assertFalse(WarrantyCardEvent.objects.filter(card=foreign_card).exists())

    def test_a_member_without_the_share_permission_is_refused_and_writes_nothing(self):
        card = self.cert_card()
        clerk = User.objects.create_user(username="share-clerk", password="x")
        membership = UserCompanyMembership.objects.create(
            user=clerk, tenant=self.tenant, role="procurement",
        )
        MemberPermission.objects.create(
            membership=membership, permission_key="sales.document.share", allowed=False,
        )
        self.client.force_authenticate(user=clerk)

        self.assertEqual(self.share(CERTIFICATE, self.invoice.pk).status_code, 403)
        self.assertEqual(self.share(CARD, card.pk).status_code, 403)
        self.assertFalse(WarrantyCardEvent.objects.filter(card=card).exists())
