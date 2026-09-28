"""#222 §٧ — أداة إصلاح البيانات `repair_warranty_lifecycle`.

الأعطال الأربعة عاشت في الإنتاج قبل إصلاحها، فبقيت في القاعدة بطاقاتٌ حيّة
لأجهزةٍ أُرجعت أو بِيعت لغير صاحبها. الأمر يقرأها ويقول ماذا سيفعل، ولا يكتب
شيئاً إلا بـ`--apply` — وتشغيلُه مرّتين كتشغيله مرّة.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

from after_sales.models import ServiceOrder, WarrantyCard
from inventory.models import ProductSerial
from core.models import TenantModule
from sales.models import SalesInvoiceLine

from .test_warranty_lifecycle import WarrantyReturnTestBase


class RepairCommandTest(WarrantyReturnTestBase):
    def repair(self, *, apply=False, tenant=None):
        out = StringIO()
        args = ["--tenant", str((tenant or self.tenant).TenantID)]
        if apply:
            args.append("--apply")
        call_command("repair_warranty_lifecycle", *args, stdout=out)
        return out.getvalue()

    def _returned_unit_with_a_live_card(self, serial):
        """يصنع حالة (أ): وحدةٌ أُرجعت وبطاقتها ما زالت حيّة (سلوك ما قبل #222)."""
        self.stock_units(serial)
        sale = self.sales_invoice(serials=[serial])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards(serial=serial).get()
        sale_return = self.sales_return(sale, serials=[serial])
        self.assertEqual(self.post_sale(sale_return).status_code, 200)
        # نُعيد عقارب الساعة: هكذا كانت البطاقة تبقى قبل الإصلاح.
        WarrantyCard.objects.filter(pk=card.pk).update(
            ended_on=None, end_reason="", end_return_line=None,
        )
        return card, sale_return

    # ── (أ) وحدةٌ أُرجعت وبطاقتها حيّة ──────────────────────────────────
    def test_dry_run_reports_the_returned_unit_and_writes_nothing(self):
        card, _ = self._returned_unit_with_a_live_card("SN-RP1")

        output = self.repair()

        self.assertIn("SN-RP1", output)
        self.assertIn("returned", output)
        card.refresh_from_db()
        self.assertIsNone(card.ended_on)

    def test_apply_ends_the_returned_card_by_its_return_date_and_is_idempotent(self):
        card, sale_return = self._returned_unit_with_a_live_card("SN-RP2")

        self.repair(apply=True)

        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_RETURNED)
        self.assertEqual(card.ended_on, date(2026, 6, 20))
        self.assertEqual(card.end_return_line.invoice_id, sale_return.pk)

        second = self.repair(apply=True)
        card.refresh_from_db()
        self.assertEqual(card.ended_on, date(2026, 6, 20))
        self.assertIn("لا شيء", second)

    # ── مرساة البند انقطعت (تعديل مسودّة سابق) — القياس على الفاتورة لا البند ──
    def test_returned_unit_is_fixed_even_when_the_cards_line_anchor_was_nulled(self):
        """كان `unit.sales_line_id != card.sales_invoice_line_id` يتجاهلها لمجرّد
        فراغ مرساة البند — رغم أن مرساة الفاتورة (`sales_invoice`) ما زالت صحيحة.
        """
        card, sale_return = self._returned_unit_with_a_live_card("SN-RP8")
        WarrantyCard.objects.filter(pk=card.pk).update(sales_invoice_line=None)

        self.repair(apply=True)

        card.refresh_from_db()
        self.assertEqual(card.end_reason, WarrantyCard.END_RETURNED)
        self.assertEqual(card.end_return_line.invoice_id, sale_return.pk)

    def test_resold_unit_check_ignores_a_nulled_line_anchor_still_on_the_same_invoice(self):
        """كان الفحص يقارن أرقام بنود، فبندٌ جديد على **نفس** الفاتورة (بعد
        تعديل مسودّة حذف القديم) يبدو «بيعاً ثانياً» ويُستبدَل خطأً.
        """
        self.stock_units("SN-RP9")
        sale = self.sales_invoice(serials=["SN-RP9"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards(serial="SN-RP9").get()
        new_line = SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=sale, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-RP9"],
        )
        ProductSerial.objects.filter(tenant=self.tenant, serial="SN-RP9").update(
            sales_line=new_line,
        )
        WarrantyCard.objects.filter(pk=card.pk).update(sales_invoice_line=None)

        output = self.repair(apply=True)

        self.assertNotIn("superseded", output)
        card.refresh_from_db()
        self.assertIsNone(card.ended_on)
        self.assertEqual(self.cards(serial="SN-RP9").count(), 1)

    def test_a_card_with_neither_invoice_anchor_is_reported_not_guessed(self):
        self.stock_units("SN-RP10")
        sale = self.sales_invoice(serials=["SN-RP10"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards(serial="SN-RP10").get()
        WarrantyCard.objects.filter(pk=card.pk).update(
            sales_invoice=None, sales_invoice_line=None,
        )

        output = self.repair(apply=True)

        self.assertIn("SN-RP10", output)
        self.assertIn("بلا مرساة", output)
        card.refresh_from_db()
        self.assertIsNone(card.ended_on)

    # ── (ب) وحدةٌ بِيعت لزبونٍ آخر والبطاقة القديمة حيّة ────────────────
    def test_apply_supersedes_a_card_whose_unit_was_sold_again(self):
        from partners.models import Partner

        self.stock_units("SN-RP3")
        first_sale = self.sales_invoice(serials=["SN-RP3"])
        self.assertEqual(self.post_sale(first_sale).status_code, 200)
        stale = self.cards(serial="SN-RP3").get()
        # بيعٌ ثانٍ من خلف الخدمة — كما كانت البيانات القديمة تصل.
        second_buyer = Partner.objects.create(
            tenant=self.tenant, name="المشتري اللاحق", partner_type="Customer",
            linked_account=self.ar,
        )
        resale = self.sales_invoice(serials=[])
        resale.customer = second_buyer
        resale.save(update_fields=["customer"])
        line = resale.lines.get()
        ProductSerial.objects.filter(tenant=self.tenant, serial="SN-RP3").update(
            sales_line=line, status=ProductSerial.STATUS_SOLD,
        )

        self.repair(apply=True)

        stale.refresh_from_db()
        self.assertEqual(stale.end_reason, WarrantyCard.END_SUPERSEDED)
        fresh = self.cards(serial="SN-RP3", ended_on__isnull=True).get()
        self.assertNotEqual(fresh.pk, stale.pk)
        self.assertEqual(fresh.partner_id, second_buyer.pk)
        self.assertEqual(fresh.start_date, date(2026, 6, 15))
        self.assertIn("بأثر رجعي", fresh.notes)

        before = list(self.cards().values_list("pk", flat=True))
        self.repair(apply=True)
        self.assertEqual(list(self.cards().values_list("pk", flat=True)), before)

    # ── (ج) أوامر صيانة بلا بطاقة — تقرير فقط ──────────────────────────
    def test_service_orders_without_a_card_are_reported_never_linked(self):
        self.stock_units("SN-RP4")
        sale = self.sales_invoice(serials=["SN-RP4"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        order = ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-RP-1", order_date="2026-07-01",
            partner=self.customer, serial="SN-RP4", complaint="لا يشحن",
        )

        output = self.repair(apply=True)

        self.assertIn("SO-RP-1", output)
        order.refresh_from_db()
        self.assertIsNone(order.warranty_card_id)

    # ── البوابة ────────────────────────────────────────────────────────
    def test_an_unlicensed_company_is_refused(self):
        TenantModule.objects.filter(
            tenant=self.tenant, module_key="after_sales",
        ).delete()
        from core.modules import invalidate_module_cache

        invalidate_module_cache(self.tenant.pk)

        with self.assertRaises(CommandError):
            self.repair(apply=True)

    def test_another_company_is_never_touched(self):
        from tenants.services import create_company

        other = create_company("شركة الإصلاح الأخرى", self.user)
        TenantModule.objects.create(
            tenant=other, module_key="after_sales", enabled=True,
        )
        outsider = WarrantyCard.objects.create(
            tenant=other, serial="SN-RP5", start_date=date(2026, 1, 1),
            duration_months=12, end_date=date(2027, 1, 1),
            source=WarrantyCard.SOURCE_AUTO_SALE,
        )
        self._returned_unit_with_a_live_card("SN-RP6")

        output = self.repair(apply=True)

        self.assertNotIn("SN-RP5", output)
        outsider.refresh_from_db()
        self.assertIsNone(outsider.ended_on)


class RepairCommandNoWorkTest(WarrantyReturnTestBase):
    def test_a_healthy_company_reports_nothing_to_fix(self):
        self.stock_units("SN-RP7")
        sale = self.sales_invoice(serials=["SN-RP7"])
        self.assertEqual(self.post_sale(sale).status_code, 200)

        out = StringIO()
        call_command(
            "repair_warranty_lifecycle", "--tenant", str(self.tenant.TenantID),
            stdout=out,
        )

        self.assertIn("لا شيء", out.getvalue())
        self.assertEqual(self.cards(ended_on__isnull=False).count(), 0)
        self.assertEqual(Decimal(self.cards().count()), Decimal(1))
