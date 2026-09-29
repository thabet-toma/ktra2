"""#222 — دورة حياة البطاقة: المرتجع، وإعادة البيع، وثبات الهوية.

خمسة أعطال كانت قائمة، ولكلٍّ اختبارٌ هنا يسقط قبل إصلاحه:

  1. مرجع البيع لا يُنهي البطاقة، فالوحدة المرتجعة تبقى «مغطّاة» في
     `warranty_coverage` وفي المسح وفي تقرير «كفالات تنتهي قريباً».
  2. الوحدة المرتجعة إذا بِيعت ثانيةً لا تأخذ بطاقة (`already_carded` كان
     يسأل «هل لهذه الوحدة بطاقة؟» لا «على هذه الفاتورة؟»).
  3. إلغاء الترحيل يحذف البطاقة، وإعادته تُنشئ بطاقةً بـ`id` جديد.
  4. مرساة البطاقة تنقطع بصمت عند تعديل المسودّة (البنود تُحذف وتُعاد).
  5. المرجع الجزئي يُعيد للمخزون وحدةً بالترتيب لا الوحدة المُسمّاة فعلاً.

ومعها البنود الثلاثة المضافة: التمديد لا يقصّر، والصفحة العامة لا تنشر
الملاحظات ولا تحسب حالتها بمقارنة تاريخ (اختباراهما في `docshare/tests/`).
"""
from datetime import date
from decimal import Decimal

from django.utils import timezone

from after_sales.models import WarrantyCard
from inventory.models import ProductSerial
from inventory.serials import SERIAL_MODE_REQUIRED
from sales.models import SalesInvoice, SalesInvoiceLine

from .test_warranty import SALE_DATE, WarrantyTestBase

BASE = "/api/after-sales/warranties/"

RETURN_DATE = "2026-06-20"


class WarrantyReturnTestBase(WarrantyTestBase):
    """أدواتٌ مشتركة: مرجعُ بيعٍ يُنشأ ويُرحَّل، وقراءةُ التغطية."""

    def sales_return(self, original, *, serials=None, qty="1", product=None,
                     invoice_date=RETURN_DATE):
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"SR-{SalesInvoice.objects.count() + 1:04d}",
            customer=self.customer, currency=self.ils, invoice_date=invoice_date,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
            original_invoice=original,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=product or self.product,
            quantity=Decimal(qty), unit_price=Decimal("2000"),
            serials=list(serials or []),
        )
        return invoice

    def coverage(self, serial):
        return self.client.get(f"{BASE}check/?serial={serial}", **self.headers()).data


class SalesReturnEndsTheCardTest(WarrantyReturnTestBase):
    def test_a_full_return_ends_the_card_and_coverage_stops_saying_covered(self):
        """عطل 1: الوحدة المرتجعة كانت تبقى «سارية» ويقول الاستقبال «مغطّى»."""
        self.stock_units("SN-R1")
        sale = self.sales_invoice(serials=["SN-R1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()

        sale_return = self.sales_return(sale, serials=["SN-R1"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.ended_on, date(2026, 6, 20))
        self.assertEqual(card.end_reason, WarrantyCard.END_RETURNED)
        self.assertEqual(card.end_return_line.invoice_id, sale_return.pk)
        self.assertEqual(card.status_on(date(2026, 6, 21)), "ended")

        covered = self.coverage("SN-R1")
        self.assertFalse(covered["covered"])
        self.assertEqual(covered["cards"], [])

    def test_the_ended_card_is_not_in_the_expiring_report_nor_in_the_scan(self):
        from core.reports import run_report

        self.stock_units("SN-R2")
        sale = self.sales_invoice(serials=["SN-R2"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        self.assertEqual(
            self.post_sale(self.sales_return(sale, serials=["SN-R2"])).status_code, 200,
        )

        rows = run_report(
            "after-sales-warranties-expiring", self.tenant.TenantID, {"days": "3650"},
        )["rows"]
        self.assertEqual([row for row in rows if row["serial"] == "SN-R2"], [])

        scan = self.client.get("/api/scan/?q=SN-R2", **self.headers()).data
        units = [row for row in scan["matches"] if row["type"] == "unit"]
        self.assertTrue(units)
        self.assertFalse(units[0]["warranty"]["covered"])

    def test_the_list_status_filters_never_call_an_ended_card_active(self):
        self.stock_units("SN-R3")
        sale = self.sales_invoice(serials=["SN-R3"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        self.assertEqual(
            self.post_sale(self.sales_return(sale, serials=["SN-R3"])).status_code, 200,
        )

        active = self.client.get(f"{BASE}?status=active", **self.headers()).data
        ended = self.client.get(f"{BASE}?status=ended", **self.headers()).data
        row = self.client.get(f"{BASE}", **self.headers()).data[0]

        self.assertEqual([r["serial"] for r in active], [])
        self.assertEqual([r["serial"] for r in ended], ["SN-R3"])
        self.assertTrue(row["ended"])
        self.assertEqual(row["end_reason"], WarrantyCard.END_RETURNED)
        self.assertEqual(row["status"], "ended")
        self.assertEqual(row["ended_on"], "2026-06-20")

    def test_unposting_the_return_revives_the_card(self):
        self.stock_units("SN-R4")
        sale = self.sales_invoice(serials=["SN-R4"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        sale_return = self.sales_return(sale, serials=["SN-R4"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        self.assertEqual(self.unpost_sale(sale_return).status_code, 200)

        card.refresh_from_db()
        self.assertIsNone(card.ended_on)
        self.assertEqual(card.end_reason, "")
        self.assertIsNone(card.end_return_line_id)
        self.assertTrue(self.coverage("SN-R4")["covered"])

    def test_a_partial_return_ends_exactly_the_named_units_card(self):
        """عطل 5: الترتيب كان يُرجع الوحدة الأولى مهما كان المكتوب على المرجع."""
        self.stock_units("SN-P1", "SN-P2")
        sale = self.sales_invoice(serials=["SN-P1", "SN-P2"], qty="2")
        self.assertEqual(self.post_sale(sale).status_code, 200)
        first = self.cards(serial="SN-P1").get()
        second = self.cards(serial="SN-P2").get()

        # المرجع يُسمّي **الوحدة الثانية** — والترتيب كان سيُعيد الأولى.
        sale_return = self.sales_return(sale, serials=["SN-P2"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        self.assertEqual(
            ProductSerial.objects.get(tenant=self.tenant, serial="SN-P2").status,
            ProductSerial.STATUS_IN_STOCK,
        )
        self.assertEqual(
            ProductSerial.objects.get(tenant=self.tenant, serial="SN-P1").status,
            ProductSerial.STATUS_SOLD,
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.ended_on)
        self.assertEqual(second.end_reason, WarrantyCard.END_RETURNED)
        self.assertTrue(self.coverage("SN-P1")["covered"])
        self.assertFalse(self.coverage("SN-P2")["covered"])

    def test_a_return_naming_a_serial_from_another_invoice_is_rejected(self):
        self.stock_units("SN-P3", "SN-P4")
        sale = self.sales_invoice(serials=["SN-P3"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        other = self.sales_invoice(serials=["SN-P4"])
        self.assertEqual(self.post_sale(other).status_code, 200)

        response = self.post_sale(self.sales_return(sale, serials=["SN-P4"]))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("SN-P4", str(response.content, "utf-8"))

    def test_required_mode_refuses_a_return_that_does_not_name_its_units(self):
        from sales.services import get_or_create_sales_settings

        settings_row = get_or_create_sales_settings(self.tenant)
        settings_row.serial_entry_mode = SERIAL_MODE_REQUIRED
        settings_row.save(update_fields=["serial_entry_mode"])
        self.stock_units("SN-Q1")
        sale = self.sales_invoice(serials=["SN-Q1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)

        response = self.post_sale(self.sales_return(sale))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("إجباري", str(response.content, "utf-8"))

    def test_a_serial_policy_forces_naming_the_returned_unit_under_an_optional_company(self):
        """مراجعة: المرجع كان يقرأ إعداد الشركة وحده فيتخطّى فرض سياسة `serial`."""
        self.stock_units("SN-Q2")
        sale = self.sales_invoice(serials=["SN-Q2"])
        self.assertEqual(self.post_sale(sale).status_code, 200)

        response = self.post_sale(self.sales_return(sale))

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("إجباري", str(response.content, "utf-8"))


class EndingIsOnTheTimelineTest(WarrantyReturnTestBase):
    """قصة ١١٨: الانتهاء بمرجعٍ أو إلغاء ترحيلٍ أو إعادة بيع يظهر في سجلّ البطاقة."""

    def kinds(self, card):
        from after_sales.models import WarrantyCardEvent

        return list(
            WarrantyCardEvent.objects.filter(card=card).order_by("pk")
            .values_list("event_type", "reason_code")
        )

    def test_a_return_and_its_undo_write_ended_then_revived(self):
        self.stock_units("SN-T1")
        sale = self.sales_invoice(serials=["SN-T1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        sale_return = self.sales_return(sale, serials=["SN-T1"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)
        self.assertEqual(self.unpost_sale(sale_return).status_code, 200)

        self.assertEqual(
            self.kinds(card),
            [("ended", WarrantyCard.END_RETURNED), ("revived", "")],
        )

    def test_unposting_and_reposting_the_sale_write_ended_then_revived(self):
        self.stock_units("SN-T2")
        sale = self.sales_invoice(serials=["SN-T2"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()

        self.assertEqual(self.unpost_sale(sale).status_code, 200)
        self.assertEqual(self.post_sale(sale).status_code, 200)

        self.assertEqual(
            self.kinds(card),
            [("ended", WarrantyCard.END_INVOICE_UNPOSTED), ("revived", "")],
        )

    def test_a_resale_writes_ended_superseded_on_the_stale_card(self):
        self.stock_units("SN-T3")
        first = self.sales_invoice(serials=["SN-T3"])
        self.assertEqual(self.post_sale(first).status_code, 200)
        stale = self.cards().get()
        # بطاقةٌ حيّة بقيت على وحدةٍ عادت للمخزن بلا مرجع (بيانات قديمة) — تُشفى بالبيع.
        from inventory.models import ProductSerial as Unit
        Unit.objects.filter(serial="SN-T3").update(
            status=Unit.STATUS_IN_STOCK, sales_line=None,
        )
        second = self.sales_invoice(serials=["SN-T3"])
        self.assertEqual(self.post_sale(second).status_code, 200)

        self.assertIn(("ended", WarrantyCard.END_SUPERSEDED), self.kinds(stale))


class InvoiceLiveFilterTest(WarrantyReturnTestBase):
    """#238: `warranties/?sales_invoice=<id>&live=1` — العدّ على الخادم لا في المتصفّح."""

    def test_live_counts_only_the_unended_cards_of_the_invoice(self):
        self.stock_units("SN-L1", "SN-L2")
        sale = self.sales_invoice(serials=["SN-L1", "SN-L2"], qty="2")
        self.assertEqual(self.post_sale(sale).status_code, 200)
        sale_return = self.sales_return(sale, serials=["SN-L1"])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        response = self.client.get(
            f"{BASE}?sales_invoice={sale.pk}&live=1&page=1&page_size=1", **self.headers(),
        )
        every = self.client.get(
            f"{BASE}?sales_invoice={sale.pk}&page=1&page_size=1", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(every.data["count"], 2)


class SecondBuyerTest(WarrantyReturnTestBase):
    def test_reselling_a_returned_unit_writes_a_fresh_card_for_the_second_buyer(self):
        """عطل 2: `already_carded` كان يمنع كل بطاقةٍ ثانية لنفس الوحدة."""
        from partners.models import Partner

        self.stock_units("SN-S1")
        sale = self.sales_invoice(serials=["SN-S1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        first_card = self.cards().get()
        self.assertEqual(
            self.post_sale(self.sales_return(sale, serials=["SN-S1"])).status_code, 200,
        )

        second_buyer = Partner.objects.create(
            tenant=self.tenant, name="المشتري الثاني", partner_type="Customer",
            linked_account=self.ar, phone="0599000111",
        )
        resale = self.sales_invoice(serials=["SN-S1"])
        SalesInvoice.objects.filter(pk=resale.pk).update(customer=second_buyer)
        resale.refresh_from_db()
        self.assertEqual(self.post_sale(resale).status_code, 200)

        cards = list(self.cards(serial="SN-S1").order_by("id"))
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0].pk, first_card.pk)
        self.assertEqual(cards[0].end_reason, WarrantyCard.END_RETURNED)
        # المشتري الثاني يأخذ **مدة كاملة جديدة** من تاريخ فاتورته.
        self.assertEqual(cards[1].partner_id, second_buyer.pk)
        self.assertEqual(cards[1].customer_name, "المشتري الثاني")
        self.assertEqual(cards[1].start_date, date(2026, 6, 15))
        self.assertEqual(cards[1].end_date, date(2027, 6, 15))
        self.assertTrue(self.coverage("SN-S1")["covered"])

    def test_a_live_auto_card_on_another_invoice_is_superseded_not_duplicated(self):
        """شفاءٌ ذاتي: بيانات قديمة تركت بطاقةً حيّةً لوحدةٍ بِيعت ثانيةً."""
        self.stock_units("SN-S2")
        sale = self.sales_invoice(serials=["SN-S2"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        stale = self.cards().get()
        # نُعيد الوحدة للمخزن بلا مرجع (بيانات قديمة) ثم نبيعها ثانيةً.
        ProductSerial.objects.filter(tenant=self.tenant, serial="SN-S2").update(
            status=ProductSerial.STATUS_IN_STOCK, sales_line=None,
        )
        resale = self.sales_invoice(serials=["SN-S2"])
        self.assertEqual(self.post_sale(resale).status_code, 200)

        stale.refresh_from_db()
        self.assertEqual(stale.end_reason, WarrantyCard.END_SUPERSEDED)
        self.assertEqual(stale.ended_on, date(2026, 6, 15))
        self.assertEqual(self.cards(serial="SN-S2", ended_on__isnull=True).count(), 1)

    def test_a_manual_card_for_the_same_unit_is_never_touched(self):
        self.stock_units("SN-S3")
        sale = self.sales_invoice(serials=["SN-S3"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        unit = ProductSerial.objects.get(tenant=self.tenant, serial="SN-S3")
        manual = WarrantyCard.objects.create(
            tenant=self.tenant, serial="SN-S3", product_serial=unit,
            start_date=date(2026, 1, 1), duration_months=12,
            end_date=date(2027, 1, 1), source=WarrantyCard.SOURCE_MANUAL,
        )
        ProductSerial.objects.filter(pk=unit.pk).update(
            status=ProductSerial.STATUS_IN_STOCK, sales_line=None,
        )
        resale = self.sales_invoice(serials=["SN-S3"])

        self.assertEqual(self.post_sale(resale).status_code, 200)

        manual.refresh_from_db()
        self.assertIsNone(manual.ended_on)


class CardIdentityTest(WarrantyReturnTestBase):
    def test_repost_revives_the_same_card_keeping_its_extension_and_event(self):
        """عطل 3: الحذف وإعادة الإنشاء كانا يكسران كل ما عُلِّق على البطاقة.

        #229: التوثيق انتقل من `notes` إلى `WarrantyCardEvent` — والحدث نفسه
        يبقى على البطاقة (لا يُحذف ولا يُعاد إنشاؤه) عبر دورة التعليق والإحياء.
        """
        from after_sales.models import WarrantyCardEvent

        self.stock_units("SN-T1")
        sale = self.sales_invoice(serials=["SN-T1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        self.client.post(
            f"{BASE}{card.pk}/extend/", {"months": 6, "reason": "مجاملة"},
            format="json", **self.headers(),
        )
        card.refresh_from_db()
        extended_end = card.end_date

        self.assertEqual(self.unpost_sale(sale).status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_INVOICE_UNPOSTED)
        self.assertEqual(card.ended_on, timezone.localdate())

        self.assertEqual(self.post_sale(sale).status_code, 200)

        revived = self.cards(source=WarrantyCard.SOURCE_AUTO_SALE).get()
        self.assertEqual(revived.pk, card.pk)
        self.assertIsNone(revived.ended_on)
        self.assertEqual(revived.end_date, extended_end)
        self.assertTrue(
            WarrantyCardEvent.objects.filter(
                card=revived, event_type=WarrantyCardEvent.TYPE_EXTEND,
            ).exists()
        )

    def test_a_changed_invoice_date_shifts_both_ends_keeping_the_extension(self):
        self.stock_units("SN-T2")
        sale = self.sales_invoice(serials=["SN-T2"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        self.client.post(
            f"{BASE}{card.pk}/extend/", {"months": 1}, format="json", **self.headers(),
        )
        self.assertEqual(self.unpost_sale(sale).status_code, 200)
        SalesInvoice.objects.filter(pk=sale.pk).update(invoice_date="2026-06-25")
        sale.refresh_from_db()

        self.assertEqual(self.post_sale(sale).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.start_date, date(2026, 6, 25))
        # 12 شهراً + تمديد شهر، مُزاحةً عشرة أيام مع الفاتورة.
        self.assertEqual(card.end_date, date(2027, 7, 25))

    def test_editing_the_draft_between_unpost_and_repost_keeps_the_same_card(self):
        """عطل 4: تعديل المسودّة يحذف البند فيُفرَّغ `sales_invoice_line`."""
        self.stock_units("SN-T3")
        sale = self.sales_invoice(serials=["SN-T3"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        self.assertEqual(self.unpost_sale(sale).status_code, 200)

        # الواجهة تُعيد إرسال البنود **بلا `id`** فيُحذف البند ويُعاد إنشاؤه.
        edit = self.client.patch(
            f"/api/sales/invoices/{sale.pk}/",
            {"lines": [{
                "product": self.product.pk, "quantity": "1", "unit_price": "2000",
                "serials": ["SN-T3"],
            }]},
            format="json", **self.headers(),
        )
        self.assertEqual(edit.status_code, 200, edit.content)
        card.refresh_from_db()
        self.assertIsNone(card.sales_invoice_line_id)
        self.assertEqual(card.sales_invoice_id, sale.pk)

        self.assertEqual(self.post_sale(sale).status_code, 200)

        revived = self.cards(source=WarrantyCard.SOURCE_AUTO_SALE).get()
        self.assertEqual(revived.pk, card.pk)
        self.assertIsNone(revived.ended_on)
        self.assertIsNotNone(revived.sales_invoice_line_id)

    def test_a_card_ended_by_a_return_is_never_revived_by_reposting_the_sale(self):
        """§4: «المنتهية بمرجعٍ لا يُحييها ترحيل البيع أبداً» — ولو أُعيد."""
        self.stock_units("SN-T4")
        sale = self.sales_invoice(serials=["SN-T4"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        self.assertEqual(
            self.post_sale(self.sales_return(sale, serials=["SN-T4"])).status_code, 200,
        )

        self.assertEqual(self.unpost_sale(sale).status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_RETURNED)

        self.assertEqual(self.post_sale(sale).status_code, 200)

        # الشهادة التي أُنهيت بمرجعٍ تبقى منتهيةً بسببها، والبيعُ الجديد يأخذ
        # بطاقةً جديدة بدل أن يسرق هويّتها.
        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_RETURNED)
        self.assertEqual(card.ended_on, date(2026, 6, 20))
        live = self.cards(serial="SN-T4", ended_on__isnull=True).get()
        self.assertNotEqual(live.pk, card.pk)

    def test_deleting_the_draft_invoice_turns_its_suspended_cards_to_cancelled(self):
        self.stock_units("SN-T5")
        sale = self.sales_invoice(serials=["SN-T5"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        self.assertEqual(self.unpost_sale(sale).status_code, 200)

        deleted = self.client.delete(
            f"/api/sales/invoices/{sale.pk}/", **self.headers(),
        )
        self.assertEqual(deleted.status_code, 204, deleted.content)

        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_SALE_CANCELLED)
        self.assertIsNotNone(card.ended_on)

    def test_a_card_left_suspended_after_repost_becomes_sale_cancelled(self):
        self.stock_units("SN-T6", "SN-T7")
        sale = self.sales_invoice(serials=["SN-T6"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards(serial="SN-T6").get()
        self.assertEqual(self.unpost_sale(sale).status_code, 200)

        # الوحدة استُبدلت على المسودّة قبل إعادة الترحيل.
        SalesInvoiceLine.objects.filter(invoice=sale).update(serials=["SN-T7"])

        self.assertEqual(self.post_sale(sale).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_SALE_CANCELLED)
        self.assertTrue(self.cards(serial="SN-T7", ended_on__isnull=True).exists())


class ExtendNeverShortensTest(WarrantyTestBase):
    """البند 8: «الإدارة تعطي ولا تأخذ» — التمديد لا يقصّر ولا يمسّ منتهية."""

    def test_an_end_date_before_the_current_one_is_refused(self):
        self.stock_units("SN-X1")
        sale = self.sales_invoice(serials=["SN-X1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()

        response = self.client.post(
            f"{BASE}{card.pk}/extend/", {"end_date": "2026-08-01", "reason": "تقصير"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        card.refresh_from_db()
        self.assertEqual(card.end_date, date(2027, 6, 15))

    def test_the_same_end_date_is_not_an_extension(self):
        self.stock_units("SN-X2")
        sale = self.sales_invoice(serials=["SN-X2"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()

        response = self.client.post(
            f"{BASE}{card.pk}/extend/", {"end_date": "2027-06-15"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_ended_card_cannot_be_extended(self):
        self.stock_units("SN-X3")
        sale = self.sales_invoice(serials=["SN-X3"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        self.assertEqual(self.unpost_sale(sale).status_code, 200)

        response = self.client.post(
            f"{BASE}{card.pk}/extend/", {"months": 3}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)


class ServiceInvoiceWarrantyTest(WarrantyTestBase):
    """§6: فاتورة الصيانة بيعٌ يمرّ من النقطة نفسها — فالقطعة المرقَّمة تُكفَل."""

    def test_a_billable_serialized_part_gets_its_own_card_when_the_invoice_posts(self):
        from after_sales.models import ServiceOrder, ServiceOrderPart
        from after_sales.service_orders import generate_service_invoice

        self.stock_units("SN-PART-1")
        order = ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-W1", order_date=SALE_DATE,
            partner=self.customer, serial="DEVICE-1", complaint="لا يعمل",
        )
        ServiceOrderPart.objects.create(
            order=order, product=self.product, quantity=Decimal("1"),
            billing=ServiceOrderPart.BILLING_BILLABLE, unit_price=Decimal("2000"),
        )
        invoice = generate_service_invoice(order, user=self.user)
        SalesInvoiceLine.objects.filter(invoice=invoice).update(serials=["SN-PART-1"])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card = self.cards(serial="SN-PART-1").get()
        self.assertEqual(card.source, WarrantyCard.SOURCE_AUTO_SALE)
        self.assertEqual(card.partner_id, self.customer.pk)
        self.assertEqual(card.duration_months, 12)
        self.assertEqual(card.sales_invoice_id, invoice.pk)
