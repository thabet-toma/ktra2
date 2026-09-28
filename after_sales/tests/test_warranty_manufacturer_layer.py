"""#232 — طبقة كفالة المصنع على البطاقة.

يثبت:
  1. سياسةٌ بجهة كفالة مصنع تُنتج طبقة مصنع بنهايتها على البطاقة التلقائية.
  2. سياسةٌ بلا جهة لا تُنتج طبقة مصنع («لا يوجد» صراحةً — `None` لا فراغ).
  3. حالتا الطبقتين مستقلتان: تاجرٌ منتهٍ ومصنعٌ سارٍ معاً.
  4. المشتري الثاني لوحدة مرتجعة: تاجرٌ كاملة من تاريخ بيعه هو، ومصنعٌ منسوخ
     كما هو من البطاقة الأولى — ولو تغيّرت السياسة بين البيعتين.
  5. تعديل بداية كفالة المصنع يعيد احتساب نهايتها من المدة المجمَّدة، ولا
     يمسّ طبقة التاجر؛ وتعديل الجهة أو المدة على بطاقةٍ تلقائية مرفوض.
  6. البطاقة اليدوية: نفس تحقّق السياسة (مدةٌ بلا جهة مرفوضة، وجهةٌ محتاجة
     مدةً وبداية)، والنهاية تُشتقّ من الخادم لا من العميل.
  7. بطاقة `sale_cancelled` (مسودّة بيعها حُذفت) أو `invoice_unposted` (بيعها
     غير نافذ الآن) لا تصلح مصدراً لنسخ طبقة المصنع — بيعها لم يقع أو لم يعد
     قائماً؛ يُتجاوَزان إلى بطاقةٍ أقدم مؤهَّلة ثم إلى السياسة.
"""
from datetime import date
from decimal import Decimal

from after_sales.models import ManufacturerWarrantor, WarrantyCard, WarrantyPolicy
from sales.models import SalesInvoice, SalesInvoiceLine

from .test_warranty import BASE, SALE_DATE, WarrantyTestBase
from .test_warranty_lifecycle import WarrantyReturnTestBase

RESALE_DATE = "2026-08-01"


class AutoCardManufacturerLayerTest(WarrantyTestBase):
    def make_warrantor(self, **overrides):
        overrides.setdefault("tenant", self.tenant)
        overrides.setdefault("name", f"جهة-{ManufacturerWarrantor.objects.count() + 1}")
        return ManufacturerWarrantor.objects.create(**overrides)

    def test_policy_with_a_warrantor_gives_the_card_a_manufacturer_end_date(self):
        warrantor = self.make_warrantor(name="سوني الشرق الأوسط")
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor, manufacturer_months=24,
        )
        self.stock_units("SN-M1")
        invoice = self.sales_invoice(serials=["SN-M1"])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card = self.cards().get()
        self.assertEqual(card.manufacturer_warrantor_id, warrantor.pk)
        self.assertEqual(card.manufacturer_start_date, date(2026, 6, 15))
        self.assertEqual(card.manufacturer_duration_months, 24)
        self.assertEqual(card.manufacturer_end_date, date(2028, 6, 15))
        self.assertEqual(card.manufacturer_status_on(date(2026, 6, 15)), "active")

        response = self.client.get(f"{BASE}{card.pk}/", **self.headers())
        self.assertEqual(response.data["manufacturer_warrantor_name"], "سوني الشرق الأوسط")
        self.assertEqual(response.data["manufacturer_end_date"], "2028-06-15")

    def test_policy_without_a_warrantor_gives_no_manufacturer_layer(self):
        # سياسة `self.product` الافتراضية (setUp) بلا جهة كفالة مصنع.
        self.stock_units("SN-M2")
        invoice = self.sales_invoice(serials=["SN-M2"])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card = self.cards().get()
        self.assertIsNone(card.manufacturer_warrantor_id)
        self.assertIsNone(card.manufacturer_start_date)
        self.assertIsNone(card.manufacturer_end_date)
        self.assertIsNone(card.manufacturer_status_on())

        response = self.client.get(f"{BASE}{card.pk}/", **self.headers())
        self.assertEqual(response.data["manufacturer_warrantor_name"], "")
        self.assertIsNone(response.data["manufacturer_status"])
        self.assertIsNone(response.data["manufacturer_end_date"])

    def test_dealer_and_manufacturer_statuses_are_independent(self):
        """تاجرٌ منتهٍ (شهرٌ واحد من ٢٠٢٦-٠٦-١٥) ومصنعٌ سارٍ (٢٤ شهراً) معاً."""
        warrantor = self.make_warrantor()
        WarrantyPolicy.objects.filter(product=self.product).update(
            dealer_months=1, manufacturer_warrantor=warrantor, manufacturer_months=24,
        )
        self.stock_units("SN-M3")
        invoice = self.sales_invoice(serials=["SN-M3"])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card = self.cards().get()
        self.assertEqual(card.end_date, date(2026, 7, 15))
        self.assertEqual(card.status_on(), "expired")
        self.assertEqual(card.manufacturer_status_on(), "active")

        response = self.client.get(f"{BASE}{card.pk}/", **self.headers())
        self.assertEqual(response.data["status"], "expired")
        self.assertEqual(response.data["manufacturer_status"], "active")


class ManufacturerLayerResaleTest(WarrantyReturnTestBase):
    def test_second_buyer_gets_full_dealer_warranty_and_a_copied_manufacturer_layer(self):
        from partners.models import Partner

        warrantor = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="جهة الإصلاح المعتمدة",
        )
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor, manufacturer_months=24,
        )
        self.stock_units("SN-RS1")
        sale = self.sales_invoice(serials=["SN-RS1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        first_card = self.cards().get()
        self.assertEqual(first_card.manufacturer_end_date, date(2028, 6, 15))

        self.assertEqual(
            self.post_sale(self.sales_return(sale, serials=["SN-RS1"])).status_code, 200,
        )

        # السياسة تتغيّر بين البيعتين — والنسخة تبقى كما كانت وقت البطاقة الأولى.
        WarrantyPolicy.objects.filter(product=self.product).update(manufacturer_months=36)

        second_buyer = Partner.objects.create(
            tenant=self.tenant, name="المشتري الثاني", partner_type="Customer",
            linked_account=self.ar,
        )
        resale = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="S-RESALE-1", customer=second_buyer,
            currency=self.ils, invoice_date=RESALE_DATE,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=resale, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-RS1"],
        )

        self.assertEqual(self.post_sale(resale).status_code, 200)

        cards = list(self.cards(serial="SN-RS1").order_by("id"))
        self.assertEqual(len(cards), 2)
        second_card = cards[1]
        self.assertEqual(second_card.partner_id, second_buyer.pk)
        # كفالة تاجر كاملة جديدة من تاريخ البيع الثاني — لا امتداد من الأولى.
        self.assertEqual(second_card.start_date, date(2026, 8, 1))
        self.assertEqual(second_card.duration_months, 12)
        self.assertEqual(second_card.end_date, date(2027, 8, 1))
        # طبقة المصنع منسوخة حرفياً من البطاقة الأولى — المدة ٢٤ لا ٣٦ الجديدة،
        # والبداية والنهاية كما كانتا، لا محسوبتين من تاريخ البيع الثاني.
        self.assertEqual(second_card.manufacturer_warrantor_id, warrantor.pk)
        self.assertEqual(second_card.manufacturer_start_date, date(2026, 6, 15))
        self.assertEqual(second_card.manufacturer_duration_months, 24)
        self.assertEqual(second_card.manufacturer_end_date, date(2028, 6, 15))


class ManufacturerLayerSkipsNonStandingCardsTest(WarrantyTestBase):
    """بطاقة بيعٍ لم يقف (`sale_cancelled`) أو غير نافذ الآن (`invoice_unposted`)
    لا تصلح مصدراً لنسخ طبقة المصنع — تُتجاوَز إلى بطاقةٍ أقدم مؤهَّلة ثم للسياسة."""

    def test_a_cancelled_sales_draft_card_is_skipped_and_the_policy_is_used_instead(self):
        warrantor_a = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="جهة البيع الأول",
        )
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor_a, manufacturer_months=24,
        )
        self.stock_units("SN-CANC1")
        sale_a = self.sales_invoice(serials=["SN-CANC1"])
        self.assertEqual(self.post_sale(sale_a).status_code, 200)
        card_a = self.cards().get()
        self.assertEqual(card_a.manufacturer_end_date, date(2028, 6, 15))

        # إلغاء ترحيل البيع الأول ثم حذف مسودّته — بيعه لم يعد قائماً أبداً.
        self.assertEqual(self.unpost_sale(sale_a).status_code, 200)
        deleted = self.client.delete(f"/api/sales/invoices/{sale_a.pk}/", **self.headers())
        self.assertEqual(deleted.status_code, 204, deleted.content)
        card_a.refresh_from_db()
        self.assertEqual(card_a.end_reason, WarrantyCard.END_SALE_CANCELLED)

        # السياسة تتغيّر بعد إلغاء البيع الأول — ما يُنسخ يجب أن يكون سياسة
        # اليوم لا بطاقة بيعٍ لم يقف قط.
        warrantor_b = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="جهة البيع الثاني",
        )
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor_b, manufacturer_months=36,
        )

        sale_b = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="S-CANC-B", customer=self.customer,
            currency=self.ils, invoice_date=RESALE_DATE,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=sale_b, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-CANC1"],
        )
        self.assertEqual(self.post_sale(sale_b).status_code, 200)

        card_b = self.cards(serial="SN-CANC1").exclude(pk=card_a.pk).get()
        # من السياسة الحالية — الجهة B ببداية تاريخ الفاتورة B، لا الجهة A
        # ببداية البيع الأول الذي لم يقف.
        self.assertEqual(card_b.manufacturer_warrantor_id, warrantor_b.pk)
        self.assertEqual(card_b.manufacturer_start_date, date(2026, 8, 1))
        self.assertEqual(card_b.manufacturer_duration_months, 36)
        self.assertEqual(card_b.manufacturer_end_date, date(2029, 8, 1))

    def test_a_still_unposted_card_is_skipped_too(self):
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة معلّقة")
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor, manufacturer_months=24,
        )
        self.stock_units("SN-SUSP1")
        sale_a = self.sales_invoice(serials=["SN-SUSP1"])
        self.assertEqual(self.post_sale(sale_a).status_code, 200)
        card_a = self.cards().get()

        # لا حذف — البيع الأول معلَّقٌ فقط (`invoice_unposted`)، لم يُحذف مسودّةً.
        self.assertEqual(self.unpost_sale(sale_a).status_code, 200)
        card_a.refresh_from_db()
        self.assertEqual(card_a.end_reason, WarrantyCard.END_INVOICE_UNPOSTED)

        WarrantyPolicy.objects.filter(product=self.product).update(manufacturer_months=36)

        sale_b = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="S-SUSP-B", customer=self.customer,
            currency=self.ils, invoice_date=RESALE_DATE,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=sale_b, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-SUSP1"],
        )
        self.assertEqual(self.post_sale(sale_b).status_code, 200)

        card_b = self.cards(serial="SN-SUSP1").exclude(pk=card_a.pk).get()
        self.assertEqual(card_b.manufacturer_start_date, date(2026, 8, 1))
        self.assertEqual(card_b.manufacturer_duration_months, 36)

    def test_falls_through_to_an_older_qualifying_card_when_the_newest_is_cancelled(self):
        """الأحدث `sale_cancelled` يُتجاوَز إلى بطاقةٍ أقدم `returned` مؤهَّلة."""
        from partners.models import Partner

        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة أصلية")
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor, manufacturer_months=24,
        )
        self.stock_units("SN-FT1")
        first_sale = self.sales_invoice(serials=["SN-FT1"])
        self.assertEqual(self.post_sale(first_sale).status_code, 200)
        first_card = self.cards().get()
        self.assertEqual(first_card.manufacturer_end_date, date(2028, 6, 15))

        # مرجع كامل — البطاقة الأولى تنتهي `returned` (مؤهَّلة للنسخ).
        return_invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SR-FT1", customer=self.customer,
            currency=self.ils, invoice_date="2026-06-20",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN, original_invoice=first_sale,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=return_invoice, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-FT1"],
        )
        self.assertEqual(self.post_sale(return_invoice).status_code, 200)
        first_card.refresh_from_db()
        self.assertEqual(first_card.end_reason, WarrantyCard.END_RETURNED)

        # بيعٌ ثانٍ يُلغى ترحيله ثم تُحذف مسودّته — بطاقته الأحدث لكنها لم تقف.
        second_buyer = Partner.objects.create(
            tenant=self.tenant, name="مشترٍ ثانٍ", partner_type="Customer",
            linked_account=self.ar,
        )
        second_sale = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="S-FT2", customer=second_buyer,
            currency=self.ils, invoice_date="2026-07-01",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=second_sale, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-FT1"],
        )
        self.assertEqual(self.post_sale(second_sale).status_code, 200)
        second_card = self.cards(serial="SN-FT1").exclude(pk=first_card.pk).get()
        self.assertEqual(second_card.manufacturer_end_date, date(2028, 6, 15))  # منسوخة من الأولى

        self.assertEqual(self.unpost_sale(second_sale).status_code, 200)
        deleted = self.client.delete(f"/api/sales/invoices/{second_sale.pk}/", **self.headers())
        self.assertEqual(deleted.status_code, 204, deleted.content)
        second_card.refresh_from_db()
        self.assertEqual(second_card.end_reason, WarrantyCard.END_SALE_CANCELLED)

        # بيعٌ ثالث — يجب أن يتجاوز بطاقة البيع الثاني الملغى ويعود للأولى
        # `returned` المؤهَّلة، لا للسياسة (رغم أنها كانت ستنتج نتيجةً مختلفة).
        WarrantyPolicy.objects.filter(product=self.product).update(manufacturer_months=48)
        third_sale = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="S-FT3", customer=self.customer,
            currency=self.ils, invoice_date="2026-09-01",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=third_sale, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-FT1"],
        )
        self.assertEqual(self.post_sale(third_sale).status_code, 200)

        third_card = (
            self.cards(serial="SN-FT1")
            .exclude(pk__in=[first_card.pk, second_card.pk]).get()
        )
        self.assertEqual(third_card.manufacturer_warrantor_id, warrantor.pk)
        self.assertEqual(third_card.manufacturer_start_date, date(2026, 6, 15))
        self.assertEqual(third_card.manufacturer_duration_months, 24)
        self.assertEqual(third_card.manufacturer_end_date, date(2028, 6, 15))


class ManufacturerLayerEditTest(WarrantyTestBase):
    def _carded_unit(self, serial, *, months=24):
        warrantor = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name=f"جهة-{ManufacturerWarrantor.objects.count() + 1}",
        )
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=warrantor, manufacturer_months=months,
        )
        self.stock_units(serial)
        invoice = self.sales_invoice(serials=[serial])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        return warrantor, self.cards().get()

    def test_editing_the_manufacturer_start_recomputes_its_end_and_leaves_dealer_alone(self):
        _warrantor, card = self._carded_unit("SN-M5")
        dealer_end_before = card.end_date

        response = self.client.patch(
            f"{BASE}{card.pk}/", {"manufacturer_start_date": "2026-07-01"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        self.assertEqual(card.manufacturer_start_date, date(2026, 7, 1))
        self.assertEqual(card.manufacturer_duration_months, 24)  # مجمَّدة
        self.assertEqual(card.manufacturer_end_date, date(2028, 7, 1))
        self.assertEqual(card.end_date, dealer_end_before)  # طبقة التاجر لم تُمَسّ

    def test_editing_the_manufacturer_warrantor_on_an_auto_card_is_rejected(self):
        _warrantor, card = self._carded_unit("SN-M6")
        other = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة أخرى")

        response = self.client.patch(
            f"{BASE}{card.pk}/", {"manufacturer_warrantor": other.pk},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        card.refresh_from_db()
        self.assertNotEqual(card.manufacturer_warrantor_id, other.pk)

    def test_editing_the_manufacturer_duration_on_an_auto_card_is_rejected(self):
        _warrantor, card = self._carded_unit("SN-M7")

        response = self.client.patch(
            f"{BASE}{card.pk}/", {"manufacturer_duration_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        card.refresh_from_db()
        self.assertEqual(card.manufacturer_duration_months, 24)


class ManualCardManufacturerLayerTest(WarrantyTestBase):
    def test_manual_card_with_a_warrantor_needs_months_and_a_start_date(self):
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة يدوية")
        payload = {
            "device_name": "هاتف زبون", "serial": "MAN-M1",
            "start_date": "2026-06-01", "duration_months": 6,
            "manufacturer_warrantor": warrantor.pk, "manufacturer_duration_months": 0,
        }

        response = self.client.post(BASE, payload, format="json", **self.headers())

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("manufacturer_duration_months", response.data)

    def test_manual_card_creates_a_manufacturer_layer_with_a_derived_end_date(self):
        warrantor = ManufacturerWarrantor.objects.create(tenant=self.tenant, name="جهة يدوية")
        payload = {
            "device_name": "هاتف زبون", "serial": "MAN-M2",
            "start_date": "2026-06-01", "duration_months": 6,
            "manufacturer_warrantor": warrantor.pk,
            "manufacturer_duration_months": 12,
            "manufacturer_start_date": "2026-06-01",
        }

        response = self.client.post(BASE, payload, format="json", **self.headers())

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["manufacturer_end_date"], "2027-06-01")
        self.assertEqual(response.data["manufacturer_warrantor_name"], "جهة يدوية")

    def test_a_card_cannot_be_created_pointing_at_another_companys_warrantor(self):
        from tenants.services import create_company

        other = create_company("شركة كفالة أخرى", self.user)
        outsider = ManufacturerWarrantor.objects.create(tenant=other, name="جهة الغير")

        response = self.client.post(
            BASE,
            {"serial": "X-1", "start_date": "2026-01-01", "duration_months": 6,
             "manufacturer_warrantor": outsider.pk, "manufacturer_duration_months": 6,
             "manufacturer_start_date": "2026-01-01"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("manufacturer_warrantor", response.data)
