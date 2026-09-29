"""#237 كفالة ٩ — رمز التحقق الدائم وصفحة التحقق العامة `/api/w/<token>`.

الباب: عميل الاختبار (رمز الزبون يُفتح بلا مصادقة، والموظف يقرأ عبر واجهة
الكفالة). الصفحة تُفحص نصاً من الرد نفسه، على نمط اختبار تسريب `docshare`.
"""
import importlib
import re
from datetime import date, timedelta

import segno
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from after_sales import verify
from after_sales.models import ManufacturerWarrantor, WarrantyCard
from core.models import TenantModule
from sales.models import SalesInvoice
from tenants.services import create_company

from .test_warranty_invoice_cards import InvoiceCardTestBase

PAGE = "/api/w/"
NOT_FOUND_TEXT = "لا توجد كفالة مسجّلة خلف هذا الرمز — تحقّق من البائع"
UNAVAILABLE_TEXT = "التحقق الإلكتروني غير متاح حالياً؛ الشهادة الورقية تبقى المرجع — راجع البائع"
ENDED_BANNER = "هذه الشهادة غير سارية"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def _html(response) -> str:
    return response.content.decode("utf-8")


class VerifyTestBase(InvoiceCardTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.public = APIClient()
        self.today = timezone.localdate()

    def make_card(self, *, tenant=None, **overrides) -> WarrantyCard:
        today = self.today
        fields = dict(
            tenant=tenant or self.tenant, device_name="هاتف ذكي", serial="SN-ABCDEF1234",
            start_date=today - timedelta(days=20), duration_months=12,
            end_date=today + timedelta(days=10), source=WarrantyCard.SOURCE_MANUAL,
        )
        fields.update(overrides)
        return WarrantyCard.objects.create(**fields)

    def warrantor(self, name="مركز صيانة المصنع", phone="0568-000-111"):
        obj, _ = ManufacturerWarrantor.objects.get_or_create(
            tenant=self.tenant, name=name, defaults={"phone": phone},
        )
        return obj

    def open(self, card):
        return self.public.get(f"{PAGE}{card.verify_token}")


class TokenShapeTest(VerifyTestBase):
    def test_a_new_card_gets_a_22_char_url_safe_token_and_tokens_differ(self):
        first, second = self.make_card(), self.make_card(serial="SN-2")

        for card in (first, second):
            self.assertRegex(card.verify_token, r"^[A-Za-z0-9_-]{22}$")
        self.assertNotEqual(first.verify_token, second.verify_token)

    def test_the_token_is_not_editable_through_the_staff_api(self):
        card = self.make_card()
        original = card.verify_token

        response = self.client.patch(
            f"/api/after-sales/warranties/{card.pk}/", {"verify_token": "x" * 22, "notes": "n"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.verify_token, original)


class TokenStabilityTest(VerifyTestBase):
    def test_serial_card_keeps_id_and_token_across_unpost_and_repost(self):
        self.stock_units("SN-V1")
        sale = self.sales_invoice(serials=["SN-V1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        card_id, token = card.pk, card.verify_token

        self.assertEqual(self.unpost_sale(sale).status_code, 200)
        self.assertEqual(self.public.get(f"{PAGE}{token}").status_code, 200)
        self.assertEqual(self.post_sale(sale).status_code, 200)

        again = self.cards().get()
        self.assertEqual((again.pk, again.verify_token), (card_id, token))

    def test_invoice_card_keeps_token_across_unpost_and_repost(self):
        invoice = self.multi_line_invoice([(self.plain, "3")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()
        card_id, token = card.pk, card.verify_token

        self.assertEqual(self.unpost_sale(invoice).status_code, 200)
        self.assertEqual(self.post_sale(invoice).status_code, 200)

        again = self.invoice_card()
        self.assertEqual((again.pk, again.verify_token), (card_id, token))

    def test_return_then_unposting_the_return_revives_the_same_token(self):
        self.stock_units("SN-V2")
        sale = self.sales_invoice(serials=["SN-V2"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        token = card.verify_token
        sale_return = self.sales_return(sale, serials=["SN-V2"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)
        card.refresh_from_db()
        self.assertIsNotNone(card.ended_on)

        self.assertEqual(self.unpost_sale(sale_return).status_code, 200)

        card.refresh_from_db()
        self.assertIsNone(card.ended_on)
        self.assertEqual(card.verify_token, token)
        self.assertNotIn(ENDED_BANNER, _html(self.public.get(f"{PAGE}{token}")))


class PublicPageStatesTest(VerifyTestBase):
    def test_active_dealer_layer_shows_remaining_days(self):
        card = self.make_card(end_date=self.today + timedelta(days=10))

        response = self.open(card)

        self.assertEqual(response.status_code, 200)
        self.assertIn("سارية — متبقٍّ 10 يوماً", _html(response))
        self.assertNotIn(ENDED_BANNER, _html(response))

    def test_last_day_reads_last_day_not_zero_days(self):
        card = self.make_card(end_date=self.today)

        html = _html(self.open(card))

        self.assertIn("آخر يوم", html)
        self.assertNotIn("متبقٍّ 0", html)

    def test_expired_dealer_layer(self):
        card = self.make_card(end_date=self.today - timedelta(days=1))

        self.assertIn("منتهية", _html(self.open(card)))

    def test_voided_dealer_layer_says_voided_without_reason_or_date(self):
        voided_at = timezone.now() - timedelta(days=3)
        card = self.make_card(
            voided_at=voided_at, void_reason=WarrantyCard.VOID_LIQUID,
            void_note="سائل مسكوب ZZ-VOID-NOTE",
        )

        html = _html(self.open(card))

        self.assertIn("ملغاة", html)
        self.assertNotIn(ENDED_BANNER, html)
        for leaked in (
            "ZZ-VOID-NOTE", "تعرّض لسوائل", "liquid",
            voided_at.date().isoformat(), voided_at.strftime("%d/%m/%Y"),
        ):
            self.assertNotIn(leaked, html)

    def test_not_started_dealer_layer(self):
        card = self.make_card(
            start_date=self.today + timedelta(days=5),
            end_date=self.today + timedelta(days=370),
        )

        self.assertIn("لم تبدأ بعد", _html(self.open(card)))

    def test_zero_month_dealer_layer_reads_none(self):
        card = self.make_card(
            duration_months=0, start_date=self.today, end_date=self.today,
        )

        html = _html(self.open(card))

        self.assertIn("كفالة التاجر", html)
        self.assertIn("لا يوجد", html)
        self.assertNotIn("آخر يوم", html)

    def test_no_manufacturer_layer_reads_none(self):
        card = self.make_card()

        html = _html(self.open(card))

        self.assertIn("كفالة المصنع", html)
        self.assertRegex(html, r"كفالة المصنع[\s\S]*لا يوجد")

    def test_active_manufacturer_layer_shows_days_name_and_phone(self):
        card = self.make_card(
            manufacturer_warrantor=self.warrantor(),
            manufacturer_start_date=self.today - timedelta(days=30),
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=45),
        )

        html = _html(self.open(card))

        self.assertIn("سارية — متبقٍّ 45 يوماً", html)
        self.assertIn("مركز صيانة المصنع", html)
        self.assertIn("0568-000-111", html)

    def test_expired_and_not_started_manufacturer_layers(self):
        expired = self.make_card(
            manufacturer_warrantor=self.warrantor(),
            manufacturer_start_date=self.today - timedelta(days=400),
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today - timedelta(days=35),
        )
        future = self.make_card(
            serial="SN-FUT-9999", manufacturer_warrantor=self.warrantor(),
            manufacturer_start_date=self.today + timedelta(days=9),
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=374),
        )

        self.assertRegex(_html(self.open(expired)), r"كفالة المصنع[\s\S]*منتهية")
        self.assertRegex(_html(self.open(future)), r"كفالة المصنع[\s\S]*لم تبدأ بعد")

    def test_manufacturer_layer_is_never_reported_as_voided(self):
        card = self.make_card(
            voided_at=timezone.now(), void_reason=WarrantyCard.VOID_MISUSE,
            manufacturer_warrantor=self.warrantor(),
            manufacturer_start_date=self.today - timedelta(days=30),
            manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=45),
        )

        html = _html(self.open(card))

        self.assertEqual(html.count("ملغاة"), 1)
        self.assertIn("سارية — متبقٍّ 45 يوماً", html)

    def test_ended_card_shows_the_single_not_valid_banner(self):
        card = self.make_card(
            ended_on=self.today, end_reason=WarrantyCard.END_RETURNED,
        )

        html = _html(self.open(card))

        self.assertEqual(html.count(ENDED_BANNER), 1)
        self.assertNotIn("أُرجع الجهاز", html)
        self.assertNotIn("returned", html)

    def test_ended_wins_over_voided_with_one_banner(self):
        card = self.make_card(
            ended_on=self.today, end_reason=WarrantyCard.END_INVOICE_UNPOSTED,
            voided_at=timezone.now(), void_reason=WarrantyCard.VOID_OTHER,
        )

        html = _html(self.open(card))

        self.assertEqual(html.count(ENDED_BANNER), 1)
        self.assertNotIn("ملغاة", html)


class PublicPageContentTest(VerifyTestBase):
    def test_serial_is_masked_to_last_four(self):
        card = self.make_card(serial="SN-ABCDEF1234")

        html = _html(self.open(card))

        self.assertIn("1234", html)
        self.assertNotIn("SN-ABCDEF1234", html)
        self.assertNotIn("ABCDEF", html)

    def test_short_serial_is_masked_to_last_two(self):
        card = self.make_card(serial="AB123")

        html = _html(self.open(card))

        self.assertIn("23", html)
        self.assertNotIn("AB123", html)
        self.assertNotIn("B12", html)

    def test_invoice_card_shows_quantity_line_and_no_serial_row(self):
        invoice = self.multi_line_invoice([(self.plain, "4")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()

        html = _html(self.open(card))

        self.assertIn("كفالة على الفاتورة · الكمية 4", html)
        self.assertNotIn("الرقم التسلسلي", html)

    def test_partly_returned_invoice_card_shows_the_covered_quantity(self):
        invoice = self.multi_line_invoice([(self.plain, "4")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()
        self.assertEqual(
            self.post_sale(self.sales_return(invoice, qty="3", product=self.plain)).status_code,
            200,
        )

        self.assertIn("كفالة على الفاتورة · الكمية 1", _html(self.open(card)))

    def test_page_names_the_company_and_the_device_and_carries_no_script(self):
        card = self.make_card(device_name="هاتف ذكي فاخر")

        html = _html(self.open(card))

        self.assertIn(self.tenant.CompanyName, html)
        self.assertIn("هاتف ذكي فاخر", html)
        self.assertNotIn("<script", html.lower())

    def test_product_linked_card_shows_the_product_name(self):
        card = self.make_card(device_name="", product=self.product)

        self.assertIn("لابتوب مكفول", _html(self.open(card)))

    def test_page_leaks_no_private_field(self):
        """القائمة البيضاء: لا اسم ولا هاتف ولا فاتورة ولا رقم بطاقة ولا ملاحظات ولا مورّد."""
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="S-LEAK-0042", customer=self.customer,
            currency=self.ils, invoice_date=self.today,
            invoice_type=SalesInvoice.INVOICE_CREDIT,
        )
        card = self.make_card(
            pk=987654, customer_name="ZZ-CUSTOMER-NAME", customer_phone="0599-LEAK-777",
            sales_invoice=invoice, partner=self.customer, notes="ZZ-NOTES-LEAK",
            terms_text="ZZ-TERMS-LEAK", supplier=self.supplier,
            supplier_warranty_end_date=date(2031, 3, 17),
            start_date=date(2026, 9, 1), end_date=self.today + timedelta(days=10),
            manufacturer_warrantor=self.warrantor(),
            manufacturer_start_date=date(2026, 9, 2), manufacturer_duration_months=12,
            manufacturer_end_date=self.today + timedelta(days=40),
        )

        html = _html(self.open(card))

        self.assertEqual(self.open(card).status_code, 200)
        for secret in (
            "ZZ-CUSTOMER-NAME", "0599-LEAK-777", "S-LEAK-0042", "987654",
            "ZZ-NOTES-LEAK", "ZZ-TERMS-LEAK", self.supplier.name, "زبون الكفالة",
            "2031", "17/03", "2026-09-01", "2026-09-02",
            (self.today + timedelta(days=10)).isoformat(),
            (self.today + timedelta(days=40)).isoformat(),
        ):
            self.assertNotIn(secret, html, secret)


class PublicPageNotFoundTest(VerifyTestBase):
    def test_unknown_well_formed_token_is_404_with_the_text(self):
        response = self.public.get(f"{PAGE}{'A' * 22}")

        self.assertEqual(response.status_code, 404)
        self.assertIn(NOT_FOUND_TEXT, _html(response))

    def test_malformed_tokens_are_404_without_touching_the_database(self):
        for token in ("short", "A" * 21, "A" * 23, "A" * 21 + "!", "a b" + "c" * 19):
            with self.subTest(token=token):
                with self.assertNumQueries(0):
                    response = self.public.get(f"{PAGE}{token}")
                self.assertEqual(response.status_code, 404)
                self.assertIn(NOT_FOUND_TEXT, _html(response))

    def test_module_off_gives_the_unavailable_text_without_the_company_name(self):
        card = self.make_card()
        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(
            enabled=False,
        )

        response = self.open(card)

        self.assertEqual(response.status_code, 404)
        html = _html(response)
        self.assertIn(UNAVAILABLE_TEXT, html)
        self.assertNotIn(self.tenant.CompanyName, html)
        self.assertNotIn("هاتف ذكي", html)

    def test_unlicensed_company_token_is_not_a_leak_of_another_company(self):
        other = create_company("شركة أخرى الوحدة مطفأة", self.user)
        card = self.make_card(tenant=other)

        response = self.open(card)

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("شركة أخرى", _html(response))


class PublicPageHeadersAndMethodsTest(VerifyTestBase):
    def test_hardening_headers_on_the_page_and_on_the_404(self):
        card = self.make_card()

        for response in (self.open(card), self.public.get(f"{PAGE}{'B' * 22}")):
            self.assertEqual(response["X-Robots-Tag"], "noindex")
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_page_needs_no_authentication(self):
        card = self.make_card()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

        self.assertEqual(client.get(f"{PAGE}{card.verify_token}").status_code, 200)

    def test_head_works_and_writes_are_405(self):
        card = self.make_card()
        url = f"{PAGE}{card.verify_token}"

        self.assertEqual(self.public.head(url).status_code, 200)
        for method in ("post", "put", "patch", "delete"):
            self.assertEqual(getattr(self.public, method)(url).status_code, 405, method)

    def test_a_trailing_slash_resolves_too(self):
        card = self.make_card()

        self.assertEqual(self.public.get(f"{PAGE}{card.verify_token}/").status_code, 200)

    def test_opening_the_page_writes_nothing(self):
        card = self.make_card()
        before = WarrantyCard.objects.filter(pk=card.pk).values_list("updated_at", flat=True).get()

        self.open(card)

        after = WarrantyCard.objects.filter(pk=card.pk).values_list("updated_at", flat=True).get()
        self.assertEqual(before, after)


@override_settings(CACHES=LOCMEM)
class PublicPageThrottleTest(VerifyTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_the_thirty_first_request_in_a_minute_is_429(self):
        card = self.make_card()
        url = f"{PAGE}{card.verify_token}"

        codes = [self.public.get(url).status_code for _ in range(31)]

        self.assertEqual(codes[:30], [200] * 30)
        self.assertEqual(codes[30], 429)


class ResolveScanTest(VerifyTestBase):
    def test_resolves_a_scanned_url_or_a_bare_token_in_the_same_company(self):
        card = self.make_card()
        for scanned in (
            verify.verify_url(card), f"  {verify.verify_url(card)}/  ", card.verify_token,
            f"https://other-host.test/api/w/{card.verify_token}?x=1",
        ):
            with self.subTest(scanned=scanned):
                self.assertEqual(verify.resolve_scan(self.tenant, scanned), card)

    def test_another_companys_token_resolves_to_nothing(self):
        other = create_company("شركة الجار", self.user)
        foreign = self.make_card(tenant=other)

        self.assertIsNone(verify.resolve_scan(self.tenant, verify.verify_url(foreign)))
        self.assertIsNone(verify.resolve_scan(self.tenant, foreign.verify_token))

    def test_garbage_resolves_to_nothing_without_a_query(self):
        with self.assertNumQueries(0):
            for scanned in ("", "hello", "SN-1234", "https://x.test/api/w/short", None):
                self.assertIsNone(verify.resolve_scan(self.tenant, scanned))

    def test_returns_an_invoice_card_that_has_no_serial(self):
        invoice = self.multi_line_invoice([(self.plain, "2")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()
        self.assertEqual(card.serial, "")

        self.assertEqual(verify.resolve_scan(self.tenant, verify.verify_url(card)), card)

    def test_staff_endpoint_returns_the_card(self):
        card = self.make_card()

        response = self.client.get(
            "/api/after-sales/warranties/resolve-scan/", {"q": verify.verify_url(card)},
            **self.headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], card.pk)
        self.assertEqual(response.data["verify_url"], verify.verify_url(card))

    def test_staff_endpoint_is_404_for_another_companys_token(self):
        other = create_company("شركة الجار", self.user)
        foreign = self.make_card(tenant=other)

        response = self.client.get(
            "/api/after-sales/warranties/resolve-scan/", {"q": foreign.verify_token},
            **self.headers(),
        )

        self.assertEqual(response.status_code, 404)

    def test_staff_endpoint_is_404_without_the_module_and_403_without_permission(self):
        card = self.make_card()
        url = "/api/after-sales/warranties/resolve-scan/"
        outsider = User.objects.create_user(username="nobody", password="x")

        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(
            enabled=False,
        )
        self.assertEqual(
            self.client.get(url, {"q": card.verify_token}, **self.headers()).status_code, 404,
        )
        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(
            enabled=True,
        )
        cache.clear()
        anonymous = APIClient()
        self.assertIn(
            anonymous.get(url, {"q": card.verify_token}, **self.headers()).status_code,
            (401, 403),
        )
        self.client.force_authenticate(user=outsider)
        self.assertIn(
            self.client.get(url, {"q": card.verify_token}, **self.headers()).status_code,
            (403, 404),
        )


class StaffApiExposureTest(VerifyTestBase):
    def test_serializer_exposes_a_read_only_verify_url(self):
        card = self.make_card()

        data = self.client.get(
            f"/api/after-sales/warranties/{card.pk}/", **self.headers(),
        ).data

        self.assertEqual(data["verify_url"], f"{verify.verify_base_url()}/api/w/{card.verify_token}")
        self.assertNotIn("verify_token", data)

    def test_qr_endpoint_returns_svg_and_url_for_own_card_only(self):
        card = self.make_card()
        other = create_company("شركة الجار", self.user)
        foreign = self.make_card(tenant=other)

        mine = self.client.get(
            f"/api/after-sales/warranties/{card.pk}/qr/", **self.headers(),
        )
        theirs = self.client.get(
            f"/api/after-sales/warranties/{foreign.pk}/qr/", **self.headers(),
        )

        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.data["verify_url"], verify.verify_url(card))
        self.assertTrue(mine.data["svg"].lstrip().startswith("<svg"))
        self.assertEqual(theirs.status_code, 404)


class VerifyModuleTest(VerifyTestBase):
    def test_mask_serial_keeps_four_or_two(self):
        self.assertTrue(verify.mask_serial("SN-ABCDEF1234").endswith("1234"))
        self.assertTrue(verify.mask_serial("AB123").endswith("23"))
        self.assertNotIn("AB1", verify.mask_serial("AB123"))
        self.assertTrue(verify.mask_serial("123456").endswith("3456"))
        self.assertNotIn("12", verify.mask_serial("123456"))
        self.assertEqual(verify.mask_serial(""), "")

    def test_mask_serial_never_reveals_a_serial_in_full(self):
        for serial in ("A", "AB"):
            self.assertNotIn(serial, verify.mask_serial(serial).replace("•", ""))

    def test_verify_url_uses_the_setting_then_falls_back_to_the_share_base(self):
        card = self.make_card()
        with override_settings(
            WARRANTY_VERIFY_BASE_URL="https://verify.example.test/",
            DOCSHARE_PUBLIC_BASE_URL="https://share.example.test",
        ):
            self.assertEqual(
                verify.verify_url(card),
                f"https://verify.example.test/api/w/{card.verify_token}",
            )
        with override_settings(
            WARRANTY_VERIFY_BASE_URL="", DOCSHARE_PUBLIC_BASE_URL="https://share.example.test",
        ):
            self.assertEqual(
                verify.verify_url(card),
                f"https://share.example.test/api/w/{card.verify_token}",
            )

    def test_qr_is_svg_with_error_level_m_and_border_four(self):
        card = self.make_card()

        svg = verify.qr_svg(card, 30)
        qr = verify.make_qr(card)

        self.assertTrue(svg.lstrip().startswith("<svg"))
        self.assertIn("mm", svg)
        self.assertEqual(qr.error, "M")
        modules = qr.symbol_size(border=4)[0]
        self.assertEqual(modules, qr.symbol_size(border=0)[0] + 8)
        self.assertEqual(segno.make(verify.verify_url(card), error="m", boost_error=False).error, "M")

    def test_new_verify_tokens_are_distinct_url_safe_and_22_chars(self):
        tokens = {verify.new_verify_token() for _ in range(2000)}

        self.assertEqual(len(tokens), 2000)
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_-]{22}", t) for t in tokens))


class BackfillMigrationTest(VerifyTestBase):
    """الخطوة ٣ تمنع NULL في القاعدة الحيّة، فالمساعدُ يملأ «الفارغ» كذلك — والاختبار
    يستعمل صفاً فارغاً واحداً لأن الفرادة تمنع اثنين؛ وعلى NULL الحقيقي جُرّبت
    الهجرة الفعلية يدوياً (تقرير التسليم)."""

    def _helper(self):
        return importlib.import_module(
            "after_sales.migrations.0015_backfill_warranty_verify_tokens",
        ).fill_verify_tokens

    def test_backfill_gives_a_blank_row_a_fresh_valid_token_and_spares_the_rest(self):
        keep = [self.make_card(serial=f"SN-BF-{i}") for i in range(4)]
        blank = self.make_card(serial="SN-BF-BLANK")
        WarrantyCard.objects.filter(pk=blank.pk).update(verify_token="")
        before = {card.pk: card.verify_token for card in keep}

        self._helper()(WarrantyCard, batch_size=2)

        blank.refresh_from_db()
        self.assertRegex(blank.verify_token, r"^[A-Za-z0-9_-]{22}$")
        self.assertNotIn(blank.verify_token, before.values())
        for card in keep:
            card.refresh_from_db()
            self.assertEqual(card.verify_token, before[card.pk])

    def test_backfilled_tokens_open_the_public_page(self):
        card = self.make_card()
        WarrantyCard.objects.filter(pk=card.pk).update(verify_token="")

        self._helper()(WarrantyCard, batch_size=2)

        card.refresh_from_db()
        self.assertEqual(self.open(card).status_code, 200)
