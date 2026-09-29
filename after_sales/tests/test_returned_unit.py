"""#246 كفالة ١٨ — مصير الجهاز المعطوب بعد الاستبدال.

كل اختبار عبر الـAPI: أمر استبدال يُسلَّم (فيصير الجهاز القديم `defective` ومصيره «محجوز
عندنا»)، ثم `service-orders/{id}/returned-unit/` يقرّر مصيره: للمورد، أو يعود للمخزن
بقيدٍ يسترد كلفته، أو يُتلَف. والمال هنا حركة مخزون وقيد — فيُقاس كلٌّ منهما بالرقم.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from accounting.models import JournalHeader
from after_sales.models import ServiceOrder, ServiceOrderEvent
from core.models import TenantModule
from core.reports import run_report
from inventory.models import Product, ProductSerial, StockMovement
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from sales.services import get_or_create_sales_settings
from tenants.models import UserCompanyMembership
from tenants.services import create_company

from .test_replacement import ReplacementBase
from .test_service_orders import ORDERS
from .test_warranty import PURCHASE_DATE, WarrantyTestBase

RESTOCK = "SERVICE_RESTOCK"
RECOVERY = "SERVICE_WARRANTY_RECOVERY"


class ReturnedUnitBase(ReplacementBase):
    def setUp(self):
        # لا نستدعي `ReplacementBase.setUp`: هو يشتري الوحدات كلّها بسعرٍ واحد،
        # وهنا سعر البديل هو المتغيّر الذي تُقاس به قاعدة «الأقل من الكلفتين».
        WarrantyTestBase.setUp(self)
        self.today = timezone.localdate()
        self.stock_priced("OLD-1", "1000")
        self.sale = self.sales_invoice(serials=["OLD-1"])
        self.assertEqual(self.post_sale(self.sale).status_code, 200)
        self.card = self.cards().get()
        self.old_unit = self.unit("OLD-1")

    def stock_priced(self, serial, price):
        price = Decimal(price)
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"P-{PurchaseInvoice.objects.count() + 1:04d}",
            partner=self.supplier, currency=self.ils, invoice_date=PURCHASE_DATE,
            exchange_rate=Decimal("1"), grand_total=price,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=self.product, name=self.product.name_ar,
            quantity=Decimal("1"), unit_price=price, total_price=price,
            serials=[serial],
        )
        response = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers(),
        )
        assert response.status_code == 201, response.content

    def delivered(self, new_price="1000"):
        """أمر استبدال سُلِّم: البديل اشتُري بـ`new_price` فهو كلفة `issued_cost`."""
        self.stock_priced("NEW-1", new_price)
        order = self.posted_order()
        response = self.deliver(order)
        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        return order

    def fate(self, order, state, note="", **extra):
        return self.client.post(
            f"{ORDERS}{order.pk}/returned-unit/", {"state": state, "note": note},
            format="json", **self.headers(), **extra,
        )

    def restock_movements(self, order):
        return StockMovement.objects.filter(
            tenant=self.tenant, reference_type=RESTOCK, reference_id=order.pk,
        )

    def recovery_journals(self, order):
        return JournalHeader.objects.filter(
            tenant=self.tenant, reference_type=RECOVERY, reference_id=order.pk,
        )

    def inventory_account(self):
        return get_or_create_sales_settings(self.tenant).default_inventory_account

    def clerk(self, name):
        user = User.objects.create_user(username=name, password="x")
        UserCompanyMembership.objects.create(user=user, tenant=self.tenant, role="sales")
        self.client.force_authenticate(user=user)
        return user

    def events(self, order, text):
        return ServiceOrderEvent.objects.filter(
            order=order, event_type=ServiceOrderEvent.TYPE_WARRANTY, text__contains=text,
        )


# ══════════════════════════════════════════════════════════════════════════
# الحالة الابتدائية: محجوز عندنا
# ══════════════════════════════════════════════════════════════════════════

class HeldAtDeliveryTest(ReturnedUnitBase):
    def test_delivering_a_replacement_leaves_the_old_unit_held_with_us(self):
        order = self.delivered()

        self.assertEqual(order.returned_unit_state, "held")
        detail = self.client.get(f"{ORDERS}{order.pk}/", **self.headers()).data
        self.assertEqual(detail["returned_unit_state"], "held")
        # الوحدة المعطوبة تُعرف من بطاقة الأمر القديمة (`product_serial`).
        self.assertEqual(detail["returned_unit_serial"], "OLD-1")
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_DEFECTIVE)

    def test_an_order_without_a_replacement_has_no_returned_unit(self):
        order = self.order()

        detail = self.client.get(f"{ORDERS}{order.pk}/", **self.headers()).data

        self.assertEqual(detail["returned_unit_state"], "")
        self.assertEqual(detail["returned_unit_serial"], "")


# ══════════════════════════════════════════════════════════════════════════
# العودة للمخزن: الحركة والقيد
# ══════════════════════════════════════════════════════════════════════════

class RestockTest(ReturnedUnitBase):
    def assert_restocked_at(self, order, expected_cost):
        expected = Decimal(expected_cost)
        movement = self.restock_movements(order).get()
        self.assertEqual(movement.movement_type, "IN")
        self.assertEqual(movement.product_id, self.product.pk)
        self.assertEqual(movement.quantity, Decimal("1"))
        self.assertEqual(movement.unit_cost, expected)
        self.assertEqual(movement.total_cost, expected)

        journal = self.recovery_journals(order).get()
        lines = list(journal.lines.all())
        self.assertEqual(len(lines), 2)
        debit = next(line for line in lines if line.debit > 0)
        credit = next(line for line in lines if line.credit > 0)
        self.assertEqual(debit.account_id, self.inventory_account().pk)
        self.assertEqual(credit.account.code, "5206")
        self.assertEqual(debit.debit, expected)
        self.assertEqual(credit.credit, expected)
        self.assertEqual(sum(line.debit for line in lines), sum(line.credit for line in lines))

    def test_restock_takes_the_replacement_cost_when_it_is_the_smaller(self):
        order = self.delivered(new_price="600")
        part = order.parts.get(replaces_device=True)
        self.assertEqual(part.issued_cost, Decimal("600.00"))

        response = self.fate(order, "restocked")

        self.assertEqual(response.status_code, 200, response.content)
        self.assert_restocked_at(order, "600.00")

    def test_restock_takes_the_old_unit_historical_cost_when_it_is_the_smaller(self):
        order = self.delivered(new_price="1500")
        part = order.parts.get(replaces_device=True)
        self.assertEqual(part.issued_cost, Decimal("1500.00"))

        response = self.fate(order, "restocked")

        self.assertEqual(response.status_code, 200, response.content)
        self.assert_restocked_at(order, "1000.00")

    def test_restock_returns_the_unit_to_stock_and_the_original_invoice_stays_guarded(self):
        """قصة ١٤٢: الإلغاء مرفوضٌ بعد الاستبدال ولو أُعيد المعطوب للمخزن —
        كان سيُعيد البديل الذي بيد الزبون للمخزن، وإعادة الترحيل تبيع المعطوب."""
        order = self.delivered()
        self.assertEqual(self.unpost_sale(self.sale).status_code, 400)
        quantity_before = Product.objects.get(pk=self.product.pk).quantity_on_hand

        response = self.fate(order, "restocked", "عاد سليماً من الفحص")

        self.assertEqual(response.status_code, 200, response.content)
        unit = self.unit("OLD-1")
        self.assertEqual(unit.status, ProductSerial.STATUS_IN_STOCK)
        self.assertIsNone(unit.sales_line_id)
        self.assertEqual(
            Product.objects.get(pk=self.product.pk).quantity_on_hand,
            quantity_before + 1,
        )
        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "restocked")
        self.assertTrue(self.events(order, "عاد سليماً من الفحص").exists())
        response = self.unpost_sale(self.sale)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("OLD-1", str(response.content, "utf-8"))
        self.assertEqual(self.unit("NEW-1").status, ProductSerial.STATUS_SOLD)

    def test_restock_is_all_or_nothing_when_the_period_is_closed(self):
        from accounting.models import FiscalPeriod

        order = self.delivered()
        FiscalPeriod.objects.filter(
            tenant=self.tenant, start_date__lte=self.today, end_date__gte=self.today,
        ).update(is_closed=True)

        response = self.fate(order, "restocked")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.restock_movements(order).exists())
        self.assertFalse(self.recovery_journals(order).exists())
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_DEFECTIVE)
        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "held")


# ══════════════════════════════════════════════════════════════════════════
# التراجع عن العودة للمخزن
# ══════════════════════════════════════════════════════════════════════════

class UndoRestockTest(ReturnedUnitBase):
    def test_undo_while_in_stock_reverses_the_money_and_the_unit(self):
        order = self.delivered()
        self.assertEqual(self.fate(order, "restocked").status_code, 200)
        quantity_restocked = Product.objects.get(pk=self.product.pk).quantity_on_hand

        response = self.fate(order, "held", "أُعيد بالخطأ")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(self.restock_movements(order).exists())
        self.assertFalse(self.recovery_journals(order).exists())
        self.assertEqual(
            Product.objects.get(pk=self.product.pk).quantity_on_hand,
            quantity_restocked - 1,
        )
        unit = self.unit("OLD-1")
        self.assertEqual(unit.status, ProductSerial.STATUS_DEFECTIVE)
        self.assertEqual(unit.sales_line_id, self.sale.lines.get().pk)
        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "held")
        self.assertTrue(self.events(order, "أُعيد بالخطأ").exists())
        # والفاتورة الأصلية عادت محروسةً كما كانت.
        self.assertEqual(self.unpost_sale(self.sale).status_code, 400)

    def test_undo_after_the_unit_was_sold_again_is_refused(self):
        order = self.delivered()
        self.assertEqual(self.fate(order, "restocked").status_code, 200)
        resale = self.sales_invoice(serials=["OLD-1"])
        self.assertEqual(self.post_sale(resale).status_code, 200)
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_SOLD)

        response = self.fate(order, "held")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.restock_movements(order).count(), 1)
        self.assertEqual(self.recovery_journals(order).count(), 1)
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_SOLD)
        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "restocked")

    def test_undo_needs_the_post_permission(self):
        order = self.delivered()
        self.assertEqual(self.fate(order, "restocked").status_code, 200)
        self.clerk("undo-clerk")

        response = self.fate(order, "held")

        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(self.restock_movements(order).count(), 1)


# ══════════════════════════════════════════════════════════════════════════
# الإتلاف والمورد
# ══════════════════════════════════════════════════════════════════════════

class DisposedTest(ReturnedUnitBase):
    def test_disposing_needs_a_note(self):
        order = self.delivered()

        for note in ("", "   "):
            with self.subTest(note=note):
                response = self.fate(order, "disposed", note)
                self.assertEqual(response.status_code, 400, response.content)

        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "held")

    def test_disposing_with_a_note_moves_no_stock_and_no_money(self):
        order = self.delivered()
        movements_before = StockMovement.objects.filter(tenant=self.tenant).count()
        journals_before = JournalHeader.objects.filter(tenant=self.tenant).count()

        response = self.fate(order, "disposed", "لوحة أم محترقة")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            StockMovement.objects.filter(tenant=self.tenant).count(), movements_before,
        )
        self.assertEqual(
            JournalHeader.objects.filter(tenant=self.tenant).count(), journals_before,
        )
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_DEFECTIVE)
        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "disposed")
        self.assertTrue(self.events(order, "لوحة أم محترقة").exists())

    def test_disposed_is_final(self):
        order = self.delivered()
        self.assertEqual(self.fate(order, "disposed", "تالف").status_code, 200)

        for state in ("held", "with_supplier", "restocked"):
            with self.subTest(state=state):
                self.assertEqual(self.fate(order, state).status_code, 400)


class WithSupplierTest(ReturnedUnitBase):
    def test_sending_to_the_supplier_flags_the_claim_and_logs_it(self):
        order = self.delivered()
        self.assertFalse(order.supplier_claim)

        response = self.fate(order, "with_supplier", "أُرسل بالشحنة 12")

        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "with_supplier")
        self.assertTrue(order.supplier_claim)
        self.assertTrue(self.events(order, "أُرسل بالشحنة 12").exists())
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_DEFECTIVE)

    def test_a_unit_at_the_supplier_can_still_come_back_to_stock(self):
        order = self.delivered()
        self.assertEqual(self.fate(order, "with_supplier").status_code, 200)

        response = self.fate(order, "restocked")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.restock_movements(order).count(), 1)

    def test_held_to_held_and_an_unknown_state_are_refused(self):
        order = self.delivered()

        self.assertEqual(self.fate(order, "held").status_code, 400)
        self.assertEqual(self.fate(order, "vanished").status_code, 400)


# ══════════════════════════════════════════════════════════════════════════
# البوابات
# ══════════════════════════════════════════════════════════════════════════

class GuardsTest(ReturnedUnitBase):
    def test_an_order_without_a_replacement_is_refused(self):
        order = ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-PLAIN", order_date=self.today,
            partner=self.customer, status=ServiceOrder.STATUS_DELIVERED,
        )

        response = self.fate(order, "disposed", "ملاحظة")

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_replacement_order_not_yet_delivered_is_refused(self):
        self.stock_priced("NEW-1", "1000")
        order = self.posted_order()

        response = self.fate(order, "with_supplier")

        self.assertEqual(response.status_code, 400, response.content)
        order.refresh_from_db()
        self.assertEqual(order.returned_unit_state, "")

    def test_restock_without_the_post_permission_is_403(self):
        order = self.delivered()
        self.clerk("fate-clerk")

        response = self.fate(order, "restocked")

        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(self.restock_movements(order).exists())
        self.assertEqual(self.unit("OLD-1").status, ProductSerial.STATUS_DEFECTIVE)

    def test_the_edit_permission_is_enough_for_the_non_money_fates(self):
        order = self.delivered()
        self.clerk("fate-clerk2")

        response = self.fate(order, "with_supplier")

        self.assertEqual(response.status_code, 200, response.content)

    def test_module_off_is_404(self):
        order = self.delivered()
        self.license.delete()

        response = self.fate(order, "with_supplier")

        self.assertEqual(response.status_code, 404, response.content)

    def test_another_company_order_is_404(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign = ServiceOrder.objects.create(
            tenant=other, order_number="SO-OTHER", order_date=self.today,
            status=ServiceOrder.STATUS_DELIVERED,
            returned_unit_state=ServiceOrder.RETURNED_HELD,
        )

        response = self.fate(foreign, "with_supplier")

        self.assertEqual(response.status_code, 404, response.content)
        foreign.refresh_from_db()
        self.assertEqual(foreign.returned_unit_state, "held")


# ══════════════════════════════════════════════════════════════════════════
# قائمة المتابعة «أجهزة معطوبة لدينا»
# ══════════════════════════════════════════════════════════════════════════

class FollowUpListTest(ReturnedUnitBase):
    def test_the_filter_returns_only_held_and_with_supplier_of_this_company(self):
        held = self.delivered()

        def direct(number, state, tenant=None):
            return ServiceOrder.objects.create(
                tenant=tenant or self.tenant, order_number=number, order_date=self.today,
                status=ServiceOrder.STATUS_DELIVERED, returned_unit_state=state,
            )

        at_supplier = direct("SO-SUP", ServiceOrder.RETURNED_WITH_SUPPLIER)
        direct("SO-DISP", ServiceOrder.RETURNED_DISPOSED)
        direct("SO-STOCK", ServiceOrder.RETURNED_RESTOCKED)
        direct("SO-NONE", "")
        other = create_company("شركة المتابعة", self.user)
        direct("SO-FOREIGN", ServiceOrder.RETURNED_HELD, tenant=other)

        response = self.client.get(
            f"{ORDERS}?returned_unit_state=held,with_supplier", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        results = response.data["results"] if "results" in response.data else response.data
        self.assertEqual(
            sorted(row["id"] for row in results), sorted([held.pk, at_supplier.pk]),
        )
        self.assertTrue(all("returned_unit_state" in row for row in results))


# ══════════════════════════════════════════════════════════════════════════
# التقرير: كلفة الكفالة تطرح ما استُردّ
# ══════════════════════════════════════════════════════════════════════════

class WarrantyCostReportTest(ReturnedUnitBase):
    def rows_of(self, order):
        payload = run_report(
            "after-sales-warranty-cost", self.tenant.TenantID, {},
        )
        return payload, [r for r in payload["rows"] if r["order_number"] == order.order_number]

    def test_the_recovery_is_subtracted_and_the_replacement_column_marks_both_rows(self):
        order = self.delivered(new_price="600")
        payload, rows = self.rows_of(order)
        self.assertEqual([r["total_cost"] for r in rows], ["600.00"])
        self.assertEqual(payload["totals"]["total_cost"], "600.00")

        self.assertEqual(self.fate(order, "restocked").status_code, 200)
        payload, rows = self.rows_of(order)

        self.assertEqual(sorted(r["total_cost"] for r in rows), ["-600.00", "600.00"])
        self.assertEqual(payload["totals"]["total_cost"], "0.00")
        self.assertEqual(payload["totals"]["quantity"], "0")
        self.assertEqual({r["replacement"] for r in rows}, {"استبدال", "استرداد"})

    def test_a_partial_recovery_leaves_the_difference_as_the_real_cost(self):
        order = self.delivered(new_price="1500")
        self.assertEqual(self.fate(order, "restocked").status_code, 200)

        payload, _rows = self.rows_of(order)

        self.assertEqual(payload["totals"]["total_cost"], "500.00")

    def test_an_order_without_a_replacement_has_an_empty_replacement_column(self):
        product = Product.objects.create(tenant=self.tenant, sku="RPT-PLAIN", name_ar="قطعة")
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="RPT-P1", partner=self.supplier,
            currency=self.ils, invoice_date=PURCHASE_DATE, exchange_rate=Decimal("1"),
            grand_total=Decimal("400"),
        )
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=product, name="قطعة", quantity=Decimal("10"),
            unit_price=Decimal("40"), total_price=Decimal("400"),
        )
        self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers(),
        )
        order = self.order()
        self.client.post(
            f"{ORDERS}{order.pk}/parts/",
            {"product": product.pk, "quantity": "1", "billing": "covered"},
            format="json", **self.headers(),
        )
        self.assertEqual(self.post_covered(order).status_code, 200)

        _payload, rows = self.rows_of(order)

        self.assertEqual([r["replacement"] for r in rows], [""])
