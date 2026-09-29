"""#238 كفالة ١٠ — طباعة شهادة الكفالة A5 وسحب البطاقة اليدوية.

كل الاختبارات عبر الـAPI: `POST warranties/print/` يعيد `text/html` نُقرأ نصُّه
كما يقرؤه الزبون على الورق، وحالة الكفالة تُسأل من `status_on` وطبقاتها لا من
القالب.
"""
import json
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User

from after_sales.models import WarrantyCard, WarrantyCardEvent
from after_sales.services import log_warranty_event
from core.models import TenantModule
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import MemberPermission, TenantSettings, UserCompanyMembership
from tenants.services import create_company

from .test_warranty import SALE_DATE
from .test_warranty_verify import ENDED_BANNER, VerifyTestBase

BASE = "/api/after-sales/warranties/"
PRINT = f"{BASE}print/"
REPRINT_MARK = "إعادة طباعة"
NEVER_ISSUED_DELETE_OK = 204
ISSUED_DELETE_TEXT = "صدرت هذه البطاقة للزبون فلا تُحذف — اسحبها"


def _html(response) -> str:
    return response.content.decode("utf-8")


def _text(response) -> str:
    """نصّ الورقة كما يُقرأ: بلا `style` ولا `svg` ولا وسوم، بمسافات موحّدة."""
    html = _html(response)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"<svg.*?</svg>", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _fmt(day) -> str:
    return day.strftime("%d/%m/%Y")


class CertificateTestBase(VerifyTestBase):
    def setUp(self):
        super().setUp()
        self.invoice_day = self.today - timedelta(days=20)
        self.invoice = self.multi_line_invoice(
            [(self.plain, "1")], invoice_date=self.invoice_day,
        )

    def cert_card(self, **overrides) -> WarrantyCard:
        fields = dict(
            sales_invoice=self.invoice, start_date=self.invoice_day,
            end_date=self.today + timedelta(days=200), terms_text="",
        )
        fields.update(overrides)
        return self.make_card(**fields)

    def print_(self, **body):
        return self.client.post(PRINT, body, format="json", **self.headers())

    def delete(self, card):
        return self.client.delete(f"{BASE}{card.pk}/", **self.headers())

    def withdraw(self, card, reason="سُحبت لأنها أُصدرت بالخطأ"):
        body = {} if reason is None else {"reason": reason}
        return self.client.post(
            f"{BASE}{card.pk}/withdraw/", body, format="json", **self.headers(),
        )

    def unwithdraw(self, card, reason="عادت الكفالة سارية"):
        body = {} if reason is None else {"reason": reason}
        return self.client.post(
            f"{BASE}{card.pk}/unwithdraw/", body, format="json", **self.headers(),
        )

    def issued_events(self, card):
        return WarrantyCardEvent.objects.filter(
            card=card, event_type=WarrantyCardEvent.TYPE_ISSUED,
        )


# ══════════════════════════════════════════════════════════════════════════
# المحتوى والتخطيط
# ══════════════════════════════════════════════════════════════════════════

class CertificateContentTest(CertificateTestBase):
    def test_single_card_prints_html_with_a_25mm_qr_and_no_store(self):
        card = self.cert_card(device_name="هاتف ذكي فاخر")

        response = self.print_(cards=[card.pk])

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertIn("no-store", response["Cache-Control"])
        html = _html(response)
        self.assertIn("هاتف ذكي فاخر", html)
        self.assertEqual(html.count("<svg"), 1)
        self.assertIn('width="25.0mm"', html)
        self.assertNotIn("<script", html.lower())
        self.assertRegex(html, r"<title>[^<]*بطاقة كفالة[^<]*</title>")

    def test_invoice_certificate_lists_the_rows_with_14mm_qr_codes(self):
        first = self.cert_card(device_name="جهاز-أول", serial="SN-1")
        second = self.cert_card(device_name="جهاز-ثانٍ", serial="SN-2")

        response = self.print_(sales_invoice=self.invoice.pk)

        self.assertEqual(response.status_code, 200, response.content)
        html, text = _html(response), _text(response)
        self.assertLess(html.index("جهاز-أول"), html.index("جهاز-ثانٍ"))
        self.assertEqual(html.count("<svg"), 2)
        self.assertEqual(len(re.findall(r'<svg[^>]*width="14(?:\.0+\d*)?mm"', html)), 2)
        self.assertIn("الأجهزة المكفولة (2)", text)
        self.assertIn(self.invoice.invoice_number, text)
        self.assertRegex(html, r"<title>[^<]*شهادة كفالة[^<]*</title>")
        self.assertIn("SN-1", text)
        self.assertIn("SN-2", text)
        self.assertEqual(
            {first.pk, second.pk},
            set(self.issued_events(first).values_list("card_id", flat=True))
            | set(self.issued_events(second).values_list("card_id", flat=True)),
        )

    def test_each_distinct_terms_text_prints_once_under_the_devices_it_covers(self):
        self.cert_card(device_name="أ", serial="S1", terms_text="شرط-مشترك-١")
        self.cert_card(device_name="ب", serial="S2", terms_text="شرط-مشترك-١")
        self.cert_card(device_name="ج", serial="S3", terms_text="شرط-خاص-٢")

        text = _text(self.print_(sales_invoice=self.invoice.pk))

        self.assertEqual(text.count("شرط-مشترك-١"), 1)
        self.assertEqual(text.count("شرط-خاص-٢"), 1)
        self.assertIn("تسري على الأجهزة 1 و2", text)
        self.assertIn("تسري على الجهاز 3", text)

    def test_an_old_card_without_terms_prints_the_companys_current_terms(self):
        """المواصفة: «البطاقة القديمة الفارغة تُطبع بشروط الشركة الحالية»."""
        from after_sales.services import get_or_create_after_sales_settings

        settings_row = get_or_create_after_sales_settings(self.tenant.pk)
        settings_row.default_terms = "شرط-الشركة-الحالي"
        settings_row.save(update_fields=["default_terms"])
        empty = self.cert_card(serial="S-OLD", terms_text="")
        frozen = self.cert_card(serial="S-NEW", terms_text="شرط-مجمَّد")

        single = _text(self.print_(cards=[empty.pk]))
        both = _text(self.print_(sales_invoice=self.invoice.pk))

        self.assertIn("شرط-الشركة-الحالي", single)
        self.assertIn("تسري على الجهاز 1", both)
        self.assertEqual(both.count("شرط-الشركة-الحالي"), 1)
        self.assertEqual(both.count("شرط-مجمَّد"), 1)
        frozen.refresh_from_db()
        self.assertEqual(frozen.terms_text, "شرط-مجمَّد")

    def test_terms_text_lines_become_list_items(self):
        card = self.cert_card(terms_text="البند الأول\nالبند الثاني")

        html = _html(self.print_(cards=[card.pk]))

        self.assertEqual(len(re.findall(r"<li[^>]*>\s*البند", html)), 2)

    def test_no_manufacturer_layer_is_printed_explicitly_as_none(self):
        card = self.cert_card()

        single = _text(self.print_(cards=[card.pk]))
        self.assertIn("كفالة المصنع لا يوجد", single)

        self.cert_card(serial="SN-2")
        table = _html(self.print_(sales_invoice=self.invoice.pk))
        self.assertGreaterEqual(table.count('class="none">لا يوجد'), 2)

    def test_a_warrantor_is_printed_once_with_a_reference_number(self):
        warrantor = self.warrantor(name="مركز-المصنع-الوحيد")
        for serial in ("SN-1", "SN-2"):
            self.cert_card(
                serial=serial, manufacturer_warrantor=warrantor,
                manufacturer_start_date=self.invoice_day,
                manufacturer_duration_months=24,
                manufacturer_end_date=self.today + timedelta(days=300),
            )

        response = self.print_(sales_invoice=self.invoice.pk)

        self.assertEqual(_text(response).count("مركز-المصنع-الوحيد"), 1)
        self.assertIn("0568-000-111", _text(response))
        self.assertEqual(_html(response).count('class="ref">1</span>'), 3)

    def test_from_date_prints_only_when_the_start_differs_from_the_invoice_date(self):
        warrantor = self.warrantor()
        later = self.invoice_day + timedelta(days=9)
        differs = self.cert_card(
            serial="SN-D", manufacturer_warrantor=warrantor,
            manufacturer_start_date=later, manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=300),
        )
        same = self.cert_card(
            serial="SN-S", manufacturer_warrantor=warrantor,
            manufacturer_start_date=self.invoice_day, manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=300),
        )

        differs_text = _text(self.print_(cards=[differs.pk]))
        same_text = _text(self.print_(cards=[same.pk]))

        self.assertIn(f"من {_fmt(later)}", differs_text)
        self.assertNotIn(f"من {_fmt(self.invoice_day)}", same_text)
        self.assertNotIn(f"من {_fmt(self.invoice_day)}", differs_text)

    def test_customer_signature_block_and_issuer_name(self):
        self.user.first_name = "سامي"
        self.user.last_name = "عودة"
        self.user.save(update_fields=["first_name", "last_name"])
        card = self.cert_card(customer_name="أحمد خليل", customer_phone="0599-123456")

        text = _text(self.print_(cards=[card.pk]))

        self.assertIn("أحمد خليل", text)
        self.assertIn("0599-123456", text)
        self.assertIn("البائع — التوقيع وختم المحل", text)
        self.assertIn("أصدرها: سامي عودة", text)
        self.assertIn("الزبون — استلمت الجهاز وقرأت الشروط", text)

    def test_shop_days_extension_is_rendered_from_its_events(self):
        card = self.cert_card()
        log_warranty_event(
            card, event_type=WarrantyCardEvent.TYPE_EXTEND,
            reason_code=WarrantyCardEvent.EXTEND_REASON_SHOP_DAYS,
            old_end_date=card.end_date, new_end_date=card.end_date + timedelta(days=6),
        )

        text = _text(self.print_(cards=[card.pk]))

        self.assertIn("مُدِّدت 6 يوماً", text)

    def test_no_extension_line_without_shop_days_events(self):
        card = self.cert_card()
        log_warranty_event(
            card, event_type=WarrantyCardEvent.TYPE_EXTEND,
            reason_code=WarrantyCardEvent.EXTEND_REASON_COURTESY,
            old_end_date=card.end_date, new_end_date=card.end_date + timedelta(days=6),
        )

        self.assertNotIn("مُدِّدت", _text(self.print_(cards=[card.pk])))

    def test_invoice_quantity_card_prints_the_covered_quantity_and_of_original(self):
        invoice = self.multi_line_invoice([(self.plain, "4")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()

        whole = _text(self.print_(cards=[card.pk]))
        self.assertIn("الكمية المكفولة 4", whole)
        self.assertNotIn("من أصل", whole)

        self.assertEqual(
            self.post_sale(self.sales_return(invoice, qty="3", product=self.plain)).status_code,
            200,
        )
        partial = _text(self.print_(cards=[card.pk]))
        self.assertIn("الكمية المكفولة 1 من أصل 4", partial)


class CertificateStatesTest(CertificateTestBase):
    def test_voided_card_shows_the_slanted_stamp_on_the_dealer_line_only(self):
        warrantor = self.warrantor()
        mfr_end = self.today + timedelta(days=300)
        card = self.cert_card(
            voided_at=self.now(), void_reason=WarrantyCard.VOID_LIQUID,
            void_note="ملاحظة-داخلية-سرية",
            manufacturer_warrantor=warrantor, manufacturer_start_date=self.invoice_day,
            manufacturer_duration_months=24, manufacturer_end_date=mfr_end,
        )

        response = self.print_(cards=[card.pk])

        self.assertEqual(response.status_code, 200, response.content)
        html, text = _html(response), _text(response)
        self.assertEqual(html.count('class="stamp-big'), 1)
        self.assertEqual(text.count("ملغاة"), 1)
        self.assertNotIn("ملاحظة-داخلية-سرية", html)
        self.assertIn(_fmt(mfr_end), text)
        self.assertNotIn(_fmt(card.end_date), text)

    def test_voided_row_on_an_invoice_certificate_stamps_only_its_dealer_cell(self):
        voided = self.cert_card(
            serial="SN-V", voided_at=self.now(), void_reason=WarrantyCard.VOID_LIQUID,
            end_date=self.today + timedelta(days=150),
        )
        healthy = self.cert_card(serial="SN-H")

        response = self.print_(sales_invoice=self.invoice.pk)

        html, text = _html(response), _text(response)
        self.assertEqual(html.count('class="stamp"'), 1)
        self.assertEqual(text.count("ملغاة"), 1)
        self.assertIn(_fmt(healthy.end_date), text)
        self.assertNotIn(_fmt(voided.end_date), text)
        self.assertNotIn('class="stamp-big', html)

    def test_expired_card_prints_with_a_grey_expired_stamp(self):
        card = self.cert_card(end_date=self.today - timedelta(days=3))

        response = self.print_(cards=[card.pk])

        self.assertEqual(response.status_code, 200, response.content)
        html, text = _html(response), _text(response)
        self.assertIn('class="stamp stamp-grey"', html)
        self.assertIn("منتهية", text)
        self.assertEqual(self.issued_events(card).count(), 1)

    def test_a_single_ended_card_is_refused_with_400(self):
        card = self.cert_card(ended_on=self.today, end_reason=WarrantyCard.END_RETURNED)

        response = self.print_(cards=[card.pk])

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.issued_events(card).count(), 0)

    def test_ended_rows_are_dropped_from_the_invoice_certificate(self):
        self.cert_card(device_name="جهاز-سارٍ", serial="SN-1")
        self.cert_card(
            device_name="جهاز-منتهٍ", serial="SN-2",
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )
        self.cert_card(device_name="جهاز-آخر", serial="SN-3")

        response = self.print_(sales_invoice=self.invoice.pk)

        text = _text(response)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("جهاز-سارٍ", text)
        self.assertIn("جهاز-آخر", text)
        self.assertNotIn("جهاز-منتهٍ", text)
        self.assertIn("الأجهزة المكفولة (2)", text)

    def test_an_invoice_whose_cards_are_all_ended_is_400(self):
        self.cert_card(serial="SN-1", ended_on=self.today, end_reason=WarrantyCard.END_RETURNED)

        self.assertEqual(self.print_(sales_invoice=self.invoice.pk).status_code, 400)

    def test_an_invoice_without_cards_is_400(self):
        self.assertEqual(self.print_(sales_invoice=self.invoice.pk).status_code, 400)

    def test_the_body_needs_exactly_one_of_cards_or_invoice(self):
        card = self.cert_card()

        self.assertEqual(self.print_().status_code, 400)
        self.assertEqual(self.print_(cards=[]).status_code, 400)
        self.assertEqual(
            self.print_(cards=[card.pk], sales_invoice=self.invoice.pk).status_code, 400,
        )

    def now(self):
        from django.utils import timezone

        return timezone.now()


# ══════════════════════════════════════════════════════════════════════════
# الإصدار وإعادة الطباعة
# ══════════════════════════════════════════════════════════════════════════

class IssuedEventAndReprintTest(CertificateTestBase):
    def test_issued_is_written_once_across_two_prints_and_the_second_is_marked(self):
        card = self.cert_card()

        first = self.print_(cards=[card.pk])
        second = self.print_(cards=[card.pk])

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(self.issued_events(card).count(), 1)
        self.assertNotIn(REPRINT_MARK, _text(first))
        self.assertIn(REPRINT_MARK, _text(second))
        self.assertIn(_fmt(self.today), _text(second))

    def test_issued_event_carries_the_print_channel_and_the_actor(self):
        card = self.cert_card()

        self.print_(cards=[card.pk])

        event = self.issued_events(card).get()
        self.assertEqual(event.reason_code, "print")
        self.assertEqual(event.actor_id, self.user.pk)

    def test_a_failed_print_writes_no_issued_event(self):
        card = self.cert_card(ended_on=self.today, end_reason=WarrantyCard.END_RETURNED)

        self.print_(cards=[card.pk])

        self.assertFalse(WarrantyCardEvent.objects.filter(card=card).exists())


# ══════════════════════════════════════════════════════════════════════════
# لا تسريب
# ══════════════════════════════════════════════════════════════════════════

class CertificateLeakTest(CertificateTestBase):
    def test_no_price_supplier_note_or_tax_number_reaches_the_paper(self):
        TenantSettings.objects.filter(tenant=self.tenant).update(
            company_name_primary="مؤسسة-الترويسة",
            licensed_dealer_no="LIC-5544332",
            income_tax_file_no="TAX-9988776",
            address="شارع-الترويسة",
        )
        SalesInvoiceLine.objects.filter(invoice=self.invoice).update(
            unit_price=Decimal("8765.43"),
        )
        warrantor = self.warrantor()
        card = self.cert_card(
            serial="SN-LEAK", notes="ملاحظة-داخلية-للتاجر",
            supplier=self.supplier,
            supplier_warranty_end_date=self.today + timedelta(days=500),
            manufacturer_warrantor=warrantor, manufacturer_start_date=self.invoice_day,
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=100),
            void_note="سبب-إلغاء-داخلي",
        )
        WarrantyCard.objects.filter(pk=card.pk).update(
            supplier_warranty_end_date=self.today + timedelta(days=777),
        )

        for body in ({"cards": [card.pk]}, {"sales_invoice": self.invoice.pk}):
            with self.subTest(body=body):
                response = self.print_(**body)
                self.assertEqual(response.status_code, 200, response.content)
                html = _html(response)
                text = _text(response)

                self.assertIn("مؤسسة-الترويسة", text)
                self.assertIn("شارع-الترويسة", text)
                for secret in (
                    "TAX-9988776", "LIC-5544332", "8765", "ملاحظة-داخلية-للتاجر", self.supplier.name,
                    "سبب-إلغاء-داخلي", _fmt(self.today + timedelta(days=777)),
                    _fmt(self.today + timedelta(days=500)),
                ):
                    self.assertNotIn(secret, html, secret)


# ══════════════════════════════════════════════════════════════════════════
# الصلاحية والترخيص والعزل
# ══════════════════════════════════════════════════════════════════════════

class CertificatePermissionAndIsolationTest(CertificateTestBase):
    def as_viewless_clerk(self):
        clerk = User.objects.create_user(username="cert-clerk", password="x")
        membership = UserCompanyMembership.objects.create(
            user=clerk, tenant=self.tenant, role="procurement",
        )
        MemberPermission.objects.create(
            membership=membership, permission_key="aftersales.warranty.view", allowed=False,
        )
        self.client.force_authenticate(user=clerk)

    def test_without_the_view_permission_it_is_403_and_nothing_is_written(self):
        card = self.cert_card()
        self.as_viewless_clerk()

        self.assertEqual(self.print_(cards=[card.pk]).status_code, 403)
        self.assertEqual(self.print_(sales_invoice=self.invoice.pk).status_code, 403)
        self.assertFalse(WarrantyCardEvent.objects.filter(card=card).exists())

    def test_module_off_is_404_before_the_permission_is_asked(self):
        card = self.cert_card()
        self.as_viewless_clerk()
        self.license.delete()

        self.assertEqual(self.print_(cards=[card.pk]).status_code, 404)

    def test_another_company_card_or_invoice_is_404(self):
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
        mine = self.cert_card()

        self.assertEqual(self.print_(cards=[foreign_card.pk]).status_code, 404)
        self.assertEqual(self.print_(cards=[mine.pk, foreign_card.pk]).status_code, 404)
        self.assertEqual(self.print_(sales_invoice=foreign_invoice.pk).status_code, 404)
        self.assertFalse(WarrantyCardEvent.objects.filter(card=foreign_card).exists())
        self.assertFalse(WarrantyCardEvent.objects.filter(card=mine).exists())


# ══════════════════════════════════════════════════════════════════════════
# الحذف والسحب لبطاقة يدوية
# ══════════════════════════════════════════════════════════════════════════

class DeleteVersusWithdrawTest(CertificateTestBase):
    def test_a_never_issued_manual_card_can_be_deleted(self):
        card = self.cert_card(sales_invoice=None)

        self.assertEqual(self.delete(card).status_code, NEVER_ISSUED_DELETE_OK)
        self.assertFalse(WarrantyCard.objects.filter(pk=card.pk).exists())

    def test_a_printed_card_cannot_be_deleted_and_says_to_withdraw(self):
        card = self.cert_card(sales_invoice=None)
        self.assertEqual(self.print_(cards=[card.pk]).status_code, 200)

        response = self.delete(card)

        self.assertEqual(response.status_code, 400)
        self.assertIn(ISSUED_DELETE_TEXT, json.dumps(response.json(), ensure_ascii=False))
        self.assertTrue(WarrantyCard.objects.filter(pk=card.pk).exists())

    def test_a_card_with_any_event_cannot_be_deleted_with_the_same_text(self):
        card = self.cert_card(sales_invoice=None)
        log_warranty_event(
            card, event_type=WarrantyCardEvent.TYPE_EXTEND,
            reason_code=WarrantyCardEvent.EXTEND_REASON_COURTESY,
            old_end_date=card.end_date, new_end_date=card.end_date + timedelta(days=1),
        )

        response = self.delete(card)

        self.assertEqual(response.status_code, 400)
        self.assertIn(ISSUED_DELETE_TEXT, json.dumps(response.json(), ensure_ascii=False))

    def test_can_delete_tells_the_screen_whether_to_show_delete_or_withdraw(self):
        card = self.cert_card(sales_invoice=None)
        self.assertTrue(self.client.get(f"{BASE}{card.pk}/", **self.headers()).data["can_delete"])

        self.print_(cards=[card.pk])

        self.assertFalse(self.client.get(f"{BASE}{card.pk}/", **self.headers()).data["can_delete"])


class WithdrawTest(CertificateTestBase):
    def test_withdrawing_ends_the_card_and_the_public_page_says_not_valid(self):
        card = self.cert_card(sales_invoice=None)
        self.print_(cards=[card.pk])

        response = self.withdraw(card, reason="أُصدرت للزبون الخطأ")

        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        self.assertEqual(card.ended_on, self.today)
        self.assertEqual(card.end_reason, WarrantyCard.END_WITHDRAWN)
        event = WarrantyCardEvent.objects.get(
            card=card, event_type=WarrantyCardEvent.TYPE_ENDED,
        )
        self.assertEqual(event.reason_code, "withdrawn")
        self.assertIn("أُصدرت للزبون الخطأ", event.text)
        self.assertEqual(_html(self.open(card)).count(ENDED_BANNER), 1)
        self.assertEqual(response.data["end_reason"], "withdrawn")

    def test_a_withdrawn_card_is_refused_by_print(self):
        card = self.cert_card(sales_invoice=None)
        self.assertEqual(self.withdraw(card).status_code, 200)

        self.assertEqual(self.print_(cards=[card.pk]).status_code, 400)

    def test_withdrawing_needs_a_reason_of_five_characters(self):
        card = self.cert_card(sales_invoice=None)

        self.assertEqual(self.withdraw(card, reason=None).status_code, 400)
        self.assertEqual(self.withdraw(card, reason="   ").status_code, 400)
        self.assertEqual(self.withdraw(card, reason="قصير").status_code, 400)
        card.refresh_from_db()
        self.assertIsNone(card.ended_on)

    def test_withdrawing_twice_or_an_auto_card_is_400(self):
        manual = self.cert_card(sales_invoice=None)
        auto = self.cert_card(source=WarrantyCard.SOURCE_AUTO_SALE, serial="SN-AUTO")
        self.assertEqual(self.withdraw(manual).status_code, 200)

        self.assertEqual(self.withdraw(manual).status_code, 400)
        self.assertEqual(self.withdraw(auto).status_code, 400)
        auto.refresh_from_db()
        self.assertIsNone(auto.ended_on)

    def test_unwithdraw_revives_the_same_card_id_and_token(self):
        card = self.cert_card(sales_invoice=None)
        token, pk = card.verify_token, card.pk
        self.withdraw(card)

        response = self.unwithdraw(card, reason="سُحبت بالخطأ وهي سارية")

        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        self.assertEqual((card.pk, card.verify_token), (pk, token))
        self.assertIsNone(card.ended_on)
        self.assertEqual(card.end_reason, "")
        self.assertTrue(WarrantyCardEvent.objects.filter(
            card=card, event_type=WarrantyCardEvent.TYPE_REVIVED,
        ).exists())
        self.assertNotIn(ENDED_BANNER, _html(self.open(card)))
        self.assertEqual(self.print_(cards=[card.pk]).status_code, 200)

    def test_unwithdraw_needs_a_reason_and_a_withdrawn_card(self):
        withdrawn = self.cert_card(sales_invoice=None)
        self.withdraw(withdrawn)
        returned = self.cert_card(
            sales_invoice=None, serial="SN-R",
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )
        healthy = self.cert_card(sales_invoice=None, serial="SN-H")

        self.assertEqual(self.unwithdraw(withdrawn, reason="قصير").status_code, 400)
        self.assertEqual(self.unwithdraw(returned).status_code, 400)
        self.assertEqual(self.unwithdraw(healthy).status_code, 400)
        returned.refresh_from_db()
        self.assertEqual(returned.end_reason, WarrantyCard.END_RETURNED)

    def test_withdraw_is_404_without_the_module_and_for_another_company(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign = self.make_card(tenant=other, serial="X-1")
        mine = self.cert_card(sales_invoice=None)

        self.assertEqual(self.withdraw(foreign).status_code, 404)
        self.assertEqual(self.unwithdraw(foreign).status_code, 404)
        foreign.refresh_from_db()
        self.assertIsNone(foreign.ended_on)

        self.license.delete()
        self.assertEqual(self.withdraw(mine).status_code, 404)
        self.assertEqual(self.unwithdraw(mine).status_code, 404)


# ══════════════════════════════════════════════════════════════════════════
# زبونٌ واحد في الشهادة الواحدة
# ══════════════════════════════════════════════════════════════════════════

class OneCustomerPerCertificateTest(CertificateTestBase):
    MIXED_TEXT = "البطاقات لزبائن مختلفين"

    def other_partner(self):
        return Partner.objects.create(
            tenant=self.tenant, name="زبون ثانٍ", partner_type="Customer",
        )

    def test_cards_of_two_partners_are_refused_and_write_no_issued_event(self):
        first = self.cert_card(serial="SN-A", partner=self.customer)
        second = self.cert_card(serial="SN-B", partner=self.other_partner())

        response = self.print_(cards=[first.pk, second.pk])

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(self.MIXED_TEXT, json.dumps(response.json(), ensure_ascii=False))
        self.assertEqual(self.issued_events(first).count(), 0)
        self.assertEqual(self.issued_events(second).count(), 0)

    def test_walk_in_cards_with_different_name_or_phone_are_refused(self):
        a = self.cert_card(serial="SN-A", customer_name="أحمد", customer_phone="0599111111")
        b = self.cert_card(serial="SN-B", customer_name="أحمد", customer_phone="0599222222")
        c = self.cert_card(serial="SN-C", customer_name="خالد", customer_phone="0599111111")

        for pair in ((a, b), (a, c)):
            with self.subTest(pair=[card.serial for card in pair]):
                response = self.print_(cards=[card.pk for card in pair])
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(self.issued_events(pair[0]).count(), 0)

    def test_a_partner_card_and_a_walk_in_card_are_not_the_same_customer(self):
        a = self.cert_card(serial="SN-A", partner=self.customer)
        b = self.cert_card(serial="SN-B", customer_name=self.customer.name)

        self.assertEqual(self.print_(cards=[a.pk, b.pk]).status_code, 400)

    def test_the_same_partner_across_two_invoices_prints(self):
        other_invoice = self.multi_line_invoice(
            [(self.plain, "1")], invoice_date=self.invoice_day,
        )
        a = self.cert_card(serial="SN-A", partner=self.customer)
        b = self.cert_card(serial="SN-B", partner=self.customer, sales_invoice=other_invoice)

        response = self.print_(cards=[a.pk, b.pk])

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.issued_events(a).count(), 1)
        self.assertEqual(self.issued_events(b).count(), 1)

    def test_the_same_walk_in_customer_is_matched_after_normalizing(self):
        other_invoice = self.multi_line_invoice(
            [(self.plain, "1")], invoice_date=self.invoice_day,
        )
        a = self.cert_card(serial="SN-A", customer_name="أحمد  علي", customer_phone="0599-111 111")
        b = self.cert_card(
            serial="SN-B", customer_name=" أحمد علي ", customer_phone="0599111111",
            sales_invoice=other_invoice,
        )

        self.assertEqual(self.print_(cards=[a.pk, b.pk]).status_code, 200)

    def test_an_invoice_certificate_is_unaffected(self):
        self.cert_card(serial="SN-A", partner=self.customer)
        self.cert_card(serial="SN-B", partner=self.customer)

        self.assertEqual(self.print_(sales_invoice=self.invoice.pk).status_code, 200)
