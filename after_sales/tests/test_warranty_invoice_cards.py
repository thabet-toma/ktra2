"""#234 كفالة ٦ — بطاقة «كفالة على الفاتورة» بالكمية لمنتجات `method=invoice`.

قبل هذه التذكرة، منتجٌ بسياسة `METHOD_INVOICE` (كإطارٍ بلا رقم تسلسلي) لا يأخذ
بطاقة كفالة مطلقاً — `test_non_serialized_line_gets_no_automatic_card` في
`test_warranty.py` كان اسمُه القاعدةَ نفسَها (حُدِّث الآن ليعكس السلوك الجديد).
هنا الدورة الكاملة: بطاقة واحدة لكل (فاتورة، منتج) بمجموع كمية بنودها، مرتجعٌ
جزئي يُنقص التغطية، تعليقٌ وإحياءٌ بالكمية المُعاد حسابها، ومنتجٌ سياسته `serial`
على الفاتورة نفسها لا يزال يأخذ بطاقةً لكل وحدة.
"""
from datetime import date
from decimal import Decimal

from after_sales.models import WarrantyCard, WarrantyCardEvent, WarrantyPolicy
from inventory.models import Product
from sales.models import SalesInvoice, SalesInvoiceLine

from .test_warranty import SALE_DATE
from .test_warranty_lifecycle import WarrantyReturnTestBase

BASE = "/api/after-sales/warranties/"


class InvoiceCardTestBase(WarrantyReturnTestBase):
    """`self.plain` (`WarrantyTestBase.setUp`) سياسته `METHOD_INVOICE` جاهزةً —
    نزيده رصيداً كافياً للبيع والمرتجع المتكرّرين في هذه المجموعة."""

    def setUp(self):
        super().setUp()
        Product.objects.filter(pk=self.plain.pk).update(
            quantity_on_hand=Decimal("1000"), avg_cost=Decimal("5"),
        )

    def multi_line_invoice(self, lines, *, invoice_date=SALE_DATE):
        """فاتورة بيع بعدّة بنود — `lines` = [(product, qty), ...]."""
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"S-{SalesInvoice.objects.count() + 1:04d}",
            customer=self.customer, currency=self.ils, invoice_date=invoice_date,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        for product, qty in lines:
            SalesInvoiceLine.objects.create(
                tenant=self.tenant, invoice=invoice, product=product,
                quantity=Decimal(qty), unit_price=Decimal("100"),
            )
        return invoice

    def invoice_card(self, product=None):
        return WarrantyCard.objects.get(
            tenant=self.tenant, product=product or self.plain, product_serial__isnull=True,
        )


class TwoLinesSumToOneCardTest(InvoiceCardTestBase):
    def test_two_lines_of_the_same_product_produce_one_card_with_summed_quantity(self):
        invoice = self.multi_line_invoice([(self.plain, "2"), (self.plain, "3")])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        cards = self.cards(product=self.plain, product_serial__isnull=True)
        self.assertEqual(cards.count(), 1)
        card = cards.get()
        self.assertEqual(card.quantity, 5)
        self.assertEqual(card.returned_quantity, 0)
        self.assertEqual(card.covered_quantity, 5)
        self.assertIsNone(card.product_serial_id)
        self.assertEqual(card.serial, "")
        self.assertEqual(card.sales_invoice_id, invoice.pk)

        api = self.client.get(f"{BASE}{card.pk}/", **self.headers()).data
        self.assertEqual(api["quantity"], 5)
        self.assertEqual(api["returned_quantity"], 0)
        self.assertEqual(api["covered_quantity"], 5)


class PartialReturnCoversRemainderTest(InvoiceCardTestBase):
    def test_returning_three_of_four_then_the_fourth_ends_the_card(self):
        invoice = self.multi_line_invoice([(self.plain, "4")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()

        first_return = self.sales_return(invoice, qty="3", product=self.plain)
        self.assertEqual(self.post_sale(first_return).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.returned_quantity, 3)
        self.assertEqual(card.covered_quantity, 1)
        self.assertIsNone(card.ended_on)
        partial_event = WarrantyCardEvent.objects.get(
            card=card, event_type=WarrantyCardEvent.TYPE_ENDED,
        )
        self.assertEqual(partial_event.quantity, 3)

        second_return = self.sales_return(
            invoice, qty="1", product=self.plain, invoice_date="2026-06-21",
        )
        self.assertEqual(self.post_sale(second_return).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.returned_quantity, 4)
        self.assertEqual(card.covered_quantity, 0)
        self.assertEqual(card.end_reason, WarrantyCard.END_RETURNED)
        self.assertEqual(card.ended_on, date(2026, 6, 21))
        self.assertEqual(card.status_on(date(2026, 6, 22)), "ended")


class UnpostReturnRevivesCoverageTest(InvoiceCardTestBase):
    def test_unposting_a_partial_return_covers_again_with_a_revived_event(self):
        invoice = self.multi_line_invoice([(self.plain, "4")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()
        sale_return = self.sales_return(invoice, qty="3", product=self.plain)
        self.assertEqual(self.post_sale(sale_return).status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.covered_quantity, 1)

        self.assertEqual(self.unpost_sale(sale_return).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.returned_quantity, 0)
        self.assertEqual(card.covered_quantity, 4)
        self.assertIsNone(card.ended_on)
        event = WarrantyCardEvent.objects.get(
            card=card, event_type=WarrantyCardEvent.TYPE_REVIVED,
        )
        self.assertEqual(event.quantity, 3)

    def test_unposting_a_full_return_reopens_the_ended_card(self):
        invoice = self.multi_line_invoice([(self.plain, "2")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()
        sale_return = self.sales_return(invoice, qty="2", product=self.plain)
        self.assertEqual(self.post_sale(sale_return).status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_RETURNED)
        self.assertIsNotNone(card.ended_on)

        self.assertEqual(self.unpost_sale(sale_return).status_code, 200)

        card.refresh_from_db()
        self.assertIsNone(card.ended_on)
        self.assertEqual(card.end_reason, "")
        self.assertEqual(card.covered_quantity, 2)


class RepostRecomputesQuantityTest(InvoiceCardTestBase):
    def test_unpost_and_repost_keeps_the_same_card_id_and_recomputes_quantity(self):
        invoice = self.multi_line_invoice([(self.plain, "2")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()
        card_id = card.pk

        self.assertEqual(self.unpost_sale(invoice).status_code, 200)
        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_INVOICE_UNPOSTED)
        self.assertIsNotNone(card.ended_on)

        edit = self.client.patch(
            f"/api/sales/invoices/{invoice.pk}/",
            {"lines": [{
                "product": self.plain.pk, "quantity": "5", "unit_price": "100",
            }]},
            format="json", **self.headers(),
        )
        self.assertEqual(edit.status_code, 200, edit.content)

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.pk, card_id)
        self.assertIsNone(card.ended_on)
        self.assertEqual(card.quantity, 5)
        self.assertEqual(card.covered_quantity, 5)


class ProductRemovedFromInvoiceTest(InvoiceCardTestBase):
    def test_removing_the_product_from_the_invoice_before_reposting_cancels_its_card(self):
        self.stock_units("SN-INV1")
        invoice = self.multi_line_invoice([(self.plain, "2")])
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-INV1"],
        )
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        plain_card = self.invoice_card()
        serial_card = self.cards(serial="SN-INV1").get()

        self.assertEqual(self.unpost_sale(invoice).status_code, 200)

        # الفاتورة تُعدَّل فتفقد بند الإطار كلياً وتُبقي بند الجهاز المُرقَّم.
        edit = self.client.patch(
            f"/api/sales/invoices/{invoice.pk}/",
            {"lines": [{
                "product": self.product.pk, "quantity": "1", "unit_price": "2000",
                "serials": ["SN-INV1"],
            }]},
            format="json", **self.headers(),
        )
        self.assertEqual(edit.status_code, 200, edit.content)

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        plain_card.refresh_from_db()
        self.assertEqual(plain_card.end_reason, WarrantyCard.END_SALE_CANCELLED)
        self.assertIsNotNone(plain_card.ended_on)
        serial_card.refresh_from_db()
        self.assertIsNone(serial_card.ended_on)
        self.assertEqual(serial_card.pk, self.cards(serial="SN-INV1", ended_on__isnull=True).get().pk)


class MixedMethodInvoiceTest(InvoiceCardTestBase):
    def test_a_serial_method_product_on_the_same_invoice_still_gets_per_unit_cards(self):
        self.stock_units("SN-MIX1", "SN-MIX2")
        invoice = self.multi_line_invoice([(self.plain, "3")])
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=self.product,
            quantity=Decimal("2"), unit_price=Decimal("2000"),
            serials=["SN-MIX1", "SN-MIX2"],
        )

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        invoice_card = self.invoice_card()
        self.assertEqual(invoice_card.quantity, 3)
        self.assertIsNone(invoice_card.product_serial_id)
        serial_cards = self.cards(product=self.product, product_serial__isnull=False)
        self.assertEqual(
            sorted(serial_cards.values_list("serial", flat=True)),
            ["SN-MIX1", "SN-MIX2"],
        )


class ReturnSurvivesPolicyChangeTest(InvoiceCardTestBase):
    """#234-review (١أ): المطابقة على بطاقةٍ موجودة لا على سياسة اليوم — مرجعٌ
    يمسّ بطاقة فاتورةٍ صُرفت أيام كانت السياسة `invoice`، ولو تغيّرت لاحقاً."""

    def test_return_still_reduces_the_card_after_the_policy_changes_to_serial(self):
        invoice = self.multi_line_invoice([(self.plain, "4")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()

        WarrantyPolicy.objects.filter(product=self.plain).update(
            method=WarrantyPolicy.METHOD_SERIAL,
        )

        sale_return = self.sales_return(invoice, qty="1", product=self.plain)
        self.assertEqual(self.post_sale(sale_return).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.returned_quantity, 1)
        self.assertEqual(card.covered_quantity, 3)


class ReviveSurvivesPolicyChangeTest(InvoiceCardTestBase):
    """#234-review (١ب): إعادة الترحيل بعد تغيّر السياسة تُحيي البطاقة القائمة
    بنفس الـ`id` لا تُلغيها — السياسة تقرّر الإنشاء لا الإحياء."""

    def test_unpost_change_policy_then_repost_revives_the_same_card(self):
        invoice = self.multi_line_invoice([(self.plain, "2")])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.invoice_card()
        card_id = card.pk

        self.assertEqual(self.unpost_sale(invoice).status_code, 200)
        WarrantyPolicy.objects.filter(product=self.plain).update(
            method=WarrantyPolicy.METHOD_SERIAL,
        )

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card.refresh_from_db()
        self.assertEqual(card.pk, card_id)
        self.assertIsNone(card.ended_on)
        self.assertEqual(card.quantity, 2)


class FractionalQuantityRefusedTest(InvoiceCardTestBase):
    """#234-review (٣): `int()` كان يقصّ الكسر صامتاً — الآن يُرفض الترحيل بوضوح."""

    def test_fractional_quantity_for_an_invoice_policy_product_is_refused_at_post(self):
        invoice = self.multi_line_invoice([(self.plain, "2.5")])

        response = self.post_sale(invoice)

        self.assertEqual(response.status_code, 400, response.content)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, SalesInvoice.STATUS_DRAFT)
        self.assertEqual(self.cards(product=self.plain).count(), 0)


class InvoiceCardTenantIsolationTest(InvoiceCardTestBase):
    def test_tenant_isolation_through_the_endpoint(self):
        from core.models import TenantModule
        from tenants.services import create_company

        other = create_company("شركة كفالة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        other_card = WarrantyCard.objects.create(
            tenant=other, device_name="إطار شركة أخرى", serial="",
            start_date=date(2026, 1, 1), duration_months=12, end_date=date(2027, 1, 1),
            quantity=5, returned_quantity=2, source=WarrantyCard.SOURCE_MANUAL,
        )

        listing = self.client.get(BASE, **self.headers())
        self.assertNotIn(other_card.pk, [row["id"] for row in listing.data])

        detail = self.client.get(f"{BASE}{other_card.pk}/", **self.headers())
        self.assertEqual(detail.status_code, 404)

        other_card.refresh_from_db()
        self.assertEqual(other_card.quantity, 5)
        self.assertEqual(other_card.returned_quantity, 2)
