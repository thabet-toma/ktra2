"""THA-24 م3 — أمر الصيانة: الحالة، وبواباتها، ومال قطع الغيار.

يثبت بالترتيب الذي تُقرأ به المخاطر:
  1. صرف القطع المغطاة ⇒ حركات `SERVICE_ISSUE` بتكلفة تاريخية + قيد متوازن
     (مدين مصروف الكفالة / دائن المخزون)، و**تكلفة المبيع لأي فاتورة لا تتغيّر**.
  2. التراجع يحذف الحركات والقيد ويفتح قفل البنود.
  3. **البند لا يتجسّد في مستندين أبداً** — حارس THA-65، بالاتجاهين.
  4. بند الأجرة في الفاتورة المولَّدة يُدائن حساب إيرادات **الخدمات** (task60).
  5. بوابتا التسليم والإلغاء.
  6. عزل الشركات و404 بلا ترخيص على كل نقطة.
  7. رصيد المخزون ينخفض **مرة واحدة** بالضبط.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from after_sales.models import (
    ServiceOrder,
    ServiceOrderEvent,
    ServiceOrderPart,
    WarrantyCard,
)
from after_sales.service_orders import (
    JOURNAL_REF_WARRANTY_PARTS,
    STOCK_REF_SERVICE_ISSUE,
    WARRANTY_EXPENSE_CODE,
)
from core.models import TenantModule
from inventory.models import Product, StockMovement, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings, post_sales_invoice, sales_cogs_map
from tenants.models import Currency
from tenants.services import create_company

ORDERS = "/api/after-sales/service-orders/"
ORDER_DATE = "2026-06-15"
PURCHASE_DATE = "2026-06-01"


class ServiceOrderTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="svc", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الصيانة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)

        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد القطع", partner_type="Supplier",
            linked_account=Account.objects.get(tenant=cls.tenant, code="2101"),
        )
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1103-SV", name="ذمم", account_type="Asset",
            is_active=True,
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون الصيانة", partner_type="Customer",
            linked_account=cls.ar, phone="0599000111",
        )
        cls.cogs = Account.objects.create(
            tenant=cls.tenant, code="5101-SV", name="تكلفة المبيعات",
            account_type="Expense", is_active=True,
        )
        cls.inventory_account = Account.objects.create(
            tenant=cls.tenant, code="1104-SV", name="المخزون", account_type="Asset",
            is_active=True,
        )
        # حسابا الإيراد **منفصلان**: بلا فصلهما لا يُثبت اختبار الأجرة شيئاً —
        # كلا البندين سيقع في الحساب نفسه ويمرّ الاختبار وهو لا يقيس (task60).
        cls.revenue_goods = Account.objects.create(
            tenant=cls.tenant, code="4101-SV", name="مبيعات البضائع",
            account_type="Revenue", is_active=True,
        )
        cls.revenue_service = Account.objects.create(
            tenant=cls.tenant, code="4102-SV", name="إيرادات الخدمات",
            account_type="Revenue", is_active=True,
        )
        settings_row = get_or_create_sales_settings(cls.tenant)
        settings_row.default_cogs_account = cls.cogs
        settings_row.default_inventory_account = cls.inventory_account
        settings_row.default_ar_account = cls.ar
        settings_row.default_revenue_account_product = cls.revenue_goods
        settings_row.default_revenue_account_service = cls.revenue_service
        settings_row.default_currency = cls.ils
        settings_row.save()
        get_or_create_purchase_settings(cls.tenant)

    def setUp(self):
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="after_sales", enabled=True,
        )
        self.part_product = Product.objects.create(
            tenant=self.tenant, sku=f"PART-{Product.objects.count() + 1}",
            name_ar="شاشة بديلة",
        )
        self.client.force_authenticate(user=self.user)
        self.receive_parts()

    # ── أدوات ──────────────────────────────────────────────────────────
    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def receive_parts(self, quantity="10", unit_price="25"):
        """يُدخل القطع للمخزن بفاتورة شراء مرحّلة — الطريق الطبيعي الوحيد.

        ضبط `quantity_on_hand`/`avg_cost` مباشرةً يكذب على الدفتر: إلغاء ترحيل
        لاحق يعيد احتساب الرصيد بإعادة تشغيل الحركات، فيجد الرصيد المزروع بلا
        حركةٍ تسنده ويصفّره. الاختبار الذي يزرع رصيداً يختبر وهماً.
        """
        quantity = Decimal(quantity)
        total = quantity * Decimal(unit_price)
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"PB-{PurchaseInvoice.objects.count() + 1:04d}",
            partner=self.supplier, currency=self.ils, invoice_date=PURCHASE_DATE,
            exchange_rate=Decimal("1"), grand_total=total,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=self.part_product, name=self.part_product.name_ar,
            quantity=quantity, unit_price=Decimal(unit_price), total_price=total,
        )
        response = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers(),
        )
        assert response.status_code == 201, response.content
        self.part_product.refresh_from_db()
        return invoice

    def intake(self, **overrides):
        payload = {
            "order_date": ORDER_DATE,
            "partner": self.customer.pk,
            "serial": "DEV-1",
            "device_description": "لابتوب",
            "complaint": "لا يشحن",
        }
        payload.update(overrides)
        response = self.client.post(ORDERS, payload, format="json", **self.headers())
        assert response.status_code == 201, response.content
        return ServiceOrder.objects.get(pk=response.data["id"])

    def add_part(self, order, *, billing="covered", quantity="2", price="0"):
        response = self.client.post(
            f"{ORDERS}{order.pk}/parts/",
            {
                "product": self.part_product.pk, "quantity": quantity,
                "billing": billing, "unit_price": price,
            },
            format="json", **self.headers(),
        )
        assert response.status_code == 201, response.content
        return ServiceOrderPart.objects.get(pk=response.data["id"])

    def post_covered(self, order):
        return self.client.post(
            f"{ORDERS}{order.pk}/post-covered/", {}, format="json", **self.headers(),
        )

    def unpost_covered(self, order):
        return self.client.post(
            f"{ORDERS}{order.pk}/unpost-covered/", {}, format="json", **self.headers(),
        )

    def generate_invoice(self, order, **body):
        return self.client.post(
            f"{ORDERS}{order.pk}/generate-invoice/", body, format="json",
            **self.headers(),
        )

    def transition(self, order, to_status, **body):
        return self.client.post(
            f"{ORDERS}{order.pk}/transition/", {"to_status": to_status, **body},
            format="json", **self.headers(),
        )

    def service_movements(self, order):
        return StockMovement.objects.filter(
            tenant=self.tenant,
            reference_type=STOCK_REF_SERVICE_ISSUE,
            reference_id=order.pk,
        )

    def warranty_journal(self, order):
        return JournalHeader.objects.filter(
            tenant=self.tenant,
            reference_type=JOURNAL_REF_WARRANTY_PARTS,
            reference_id=order.pk,
        )


# ══════════════════════════════════════════════════════════════════════════
# 1 + 7 — صرف القطع المغطاة
# ══════════════════════════════════════════════════════════════════════════

class CoveredPartsPostingTest(ServiceOrderTestBase):
    def test_posting_covered_parts_issues_stock_at_historic_cost_and_balances(self):
        order = self.intake(warranty_covered=True)
        self.add_part(order, billing="covered", quantity="2")

        response = self.post_covered(order)
        self.assertEqual(response.status_code, 200, response.content)

        movement = self.service_movements(order).get()
        self.assertEqual(movement.movement_type, "OUT")
        self.assertEqual(movement.quantity, Decimal("2.0000"))
        # التكلفة التاريخية: الكمية × متوسط التكلفة **قبل** الحركة.
        self.assertEqual(movement.avg_cost_before, Decimal("25.0000"))
        self.assertEqual(movement.total_cost, Decimal("50.00"))

        journal = self.warranty_journal(order).get()
        self.assertTrue(journal.is_posted)
        lines = {line.account.code: line for line in journal.lines.all()}
        expense_code = Account.objects.get(
            tenant=self.tenant, code=WARRANTY_EXPENSE_CODE,
        ).code
        self.assertEqual(lines[expense_code].debit, Decimal("50.00"))
        self.assertEqual(lines[expense_code].credit, Decimal("0.00"))
        self.assertEqual(lines["1104-SV"].credit, Decimal("50.00"))
        self.assertEqual(lines["1104-SV"].debit, Decimal("0.00"))
        self.assertEqual(
            sum(line.debit for line in journal.lines.all()),
            sum(line.credit for line in journal.lines.all()),
        )

    def test_the_warranty_expense_account_is_created_under_operating_expenses_and_pinned(self):
        from after_sales.services import get_or_create_after_sales_settings

        order = self.intake()
        self.add_part(order, billing="covered")

        self.assertEqual(self.post_covered(order).status_code, 200)

        account = Account.objects.get(tenant=self.tenant, code=WARRANTY_EXPENSE_CODE)
        self.assertEqual(account.account_type, "Expense")
        self.assertEqual(account.parent.code, "52")
        # مثبَّت في الإعدادات فلا يُنشأ حسابٌ ثانٍ في المرة التالية.
        self.assertEqual(
            get_or_create_after_sales_settings(self.tenant.pk).warranty_expense_account_id,
            account.pk,
        )

    def test_stock_drops_exactly_once_and_a_second_posting_is_refused(self):
        order = self.intake()
        self.add_part(order, billing="covered", quantity="3")

        self.assertEqual(self.post_covered(order).status_code, 200)

        self.part_product.refresh_from_db()
        self.assertEqual(self.part_product.quantity_on_hand, Decimal("7.0000"))

        again = self.post_covered(order)
        self.assertEqual(again.status_code, 400, again.content)
        self.part_product.refresh_from_db()
        self.assertEqual(self.part_product.quantity_on_hand, Decimal("7.0000"))
        self.assertEqual(self.service_movements(order).count(), 1)

    def test_warranty_issue_never_enters_the_cost_of_goods_sold_base(self):
        """مصروف الكفالة مصروف تشغيلي لا COGS — ولا يلمس ربح أي فاتورة."""
        sale = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SV-SALE-1", customer=self.customer,
            currency=self.ils, invoice_date=ORDER_DATE,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=sale, product=self.part_product,
            quantity=Decimal("1"), unit_price=Decimal("90"),
        )
        post_sales_invoice(sale, user=self.user)
        before = sales_cogs_map(tenant_id=self.tenant.pk, invoice_ids=[sale.pk])

        order = self.intake()
        self.add_part(order, billing="covered", quantity="2")
        self.assertEqual(self.post_covered(order).status_code, 200)

        after = sales_cogs_map(tenant_id=self.tenant.pk, invoice_ids=[sale.pk])
        self.assertEqual(after, before)
        self.assertEqual(after[(sale.pk, self.part_product.pk)]["cost"], Decimal("25.00"))

    def test_posting_with_no_covered_parts_is_refused(self):
        order = self.intake()
        self.add_part(order, billing="billable", price="80")

        response = self.post_covered(order)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.service_movements(order).count(), 0)


# ══════════════════════════════════════════════════════════════════════════
# 2 — التراجع
# ══════════════════════════════════════════════════════════════════════════

class CoveredPartsUnpostTest(ServiceOrderTestBase):
    def test_unpost_deletes_the_journal_and_movements_and_unlocks_the_lines(self):
        order = self.intake()
        part = self.add_part(order, billing="covered", quantity="2")
        self.assertEqual(self.post_covered(order).status_code, 200)

        response = self.unpost_covered(order)
        self.assertEqual(response.status_code, 200, response.content)

        self.assertEqual(self.service_movements(order).count(), 0)
        self.assertEqual(self.warranty_journal(order).count(), 0)
        # المرجع يُقيَّد بنوعه دائماً: `reference_id` وحده يتصادم عبر فضاءات
        # معرّفات المستندات (قيد فاتورة الشراء يحمل الرقم نفسه).
        self.assertFalse(
            JournalLine.objects.filter(
                journal__reference_type=JOURNAL_REF_WARRANTY_PARTS,
                journal__reference_id=order.pk,
            ).exists(),
        )
        part.refresh_from_db()
        self.assertIsNone(part.materialized_at)
        order.refresh_from_db()
        self.assertIsNone(order.covered_posted_at)
        # المخزون عاد كما كان.
        self.part_product.refresh_from_db()
        self.assertEqual(self.part_product.quantity_on_hand, Decimal("10.0000"))

    def test_unpost_then_repost_is_a_full_cycle(self):
        order = self.intake()
        self.add_part(order, billing="covered", quantity="2")
        self.assertEqual(self.post_covered(order).status_code, 200)
        self.assertEqual(self.unpost_covered(order).status_code, 200)

        self.assertEqual(self.post_covered(order).status_code, 200)

        self.assertEqual(self.service_movements(order).count(), 1)
        self.assertEqual(self.warranty_journal(order).count(), 1)
        self.part_product.refresh_from_db()
        self.assertEqual(self.part_product.quantity_on_hand, Decimal("8.0000"))

    def test_unposting_what_was_never_posted_is_refused(self):
        order = self.intake()

        response = self.unpost_covered(order)

        self.assertEqual(response.status_code, 400, response.content)


# ══════════════════════════════════════════════════════════════════════════
# 3 — حارس THA-65: بند واحد، مستند واحد
# ══════════════════════════════════════════════════════════════════════════

class SingleMaterializationGuardTest(ServiceOrderTestBase):
    def test_a_covered_posted_part_can_never_reach_an_invoice(self):
        order = self.intake()
        part = self.add_part(order, billing="covered", quantity="2")
        self.assertEqual(self.post_covered(order).status_code, 200)

        # لا شيء يُفوتر: البند المُجسَّد خارج التقاط الفوترة بحكم نوعه وقفله معاً.
        invoiced = self.generate_invoice(order)
        self.assertEqual(invoiced.status_code, 400, invoiced.content)

        # ولا يُعاد تصنيفه ليتسلّل من الباب الثاني.
        reclassified = self.client.patch(
            f"{ORDERS}{order.pk}/parts/{part.pk}/", {"billing": "billable"},
            format="json", **self.headers(),
        )
        self.assertEqual(reclassified.status_code, 400, reclassified.content)
        part.refresh_from_db()
        self.assertEqual(part.billing, ServiceOrderPart.BILLING_COVERED)

        # الخصم مرة واحدة: حركة صرف كفالة واحدة ولا حركة بيع إطلاقاً.
        self.assertEqual(self.service_movements(order).count(), 1)
        self.assertEqual(
            StockMovement.objects.filter(
                tenant=self.tenant, product=self.part_product,
                reference_type__in=("SALE", "STOCK_ISSUE"),
            ).count(),
            0,
        )

    def test_an_invoiced_part_can_never_be_issued_as_a_warranty_cost(self):
        order = self.intake()
        part = self.add_part(order, billing="billable", quantity="2", price="80")

        response = self.generate_invoice(order)
        self.assertEqual(response.status_code, 201, response.content)
        part.refresh_from_db()
        self.assertIsNotNone(part.materialized_at)
        self.assertIsNotNone(part.sales_invoice_line_id)

        blocked = self.post_covered(order)
        self.assertEqual(blocked.status_code, 400, blocked.content)
        self.assertEqual(self.service_movements(order).count(), 0)

        reclassified = self.client.patch(
            f"{ORDERS}{order.pk}/parts/{part.pk}/", {"billing": "covered"},
            format="json", **self.headers(),
        )
        self.assertEqual(reclassified.status_code, 400, reclassified.content)

    def test_a_materialized_part_cannot_be_deleted_or_edited(self):
        order = self.intake()
        part = self.add_part(order, billing="covered", quantity="1")
        self.assertEqual(self.post_covered(order).status_code, 200)

        removed = self.client.delete(
            f"{ORDERS}{order.pk}/parts/{part.pk}/", **self.headers(),
        )

        self.assertEqual(removed.status_code, 400, removed.content)
        self.assertTrue(ServiceOrderPart.objects.filter(pk=part.pk).exists())

    def test_detaching_a_draft_invoice_reopens_its_lines(self):
        order = self.intake()
        part = self.add_part(order, billing="billable", quantity="2", price="80")
        self.assertEqual(self.generate_invoice(order).status_code, 201)

        response = self.client.post(
            f"{ORDERS}{order.pk}/detach-invoice/", {}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        part.refresh_from_db()
        self.assertIsNone(part.materialized_at)
        self.assertIsNone(part.sales_invoice_line_id)
        order.refresh_from_db()
        self.assertIsNone(order.sales_invoice_id)

    def test_a_posted_invoice_cannot_be_detached(self):
        order = self.intake()
        self.add_part(order, billing="billable", quantity="2", price="80")
        self.assertEqual(self.generate_invoice(order).status_code, 201)
        order.refresh_from_db()
        post_sales_invoice(order.sales_invoice, user=self.user)

        response = self.client.post(
            f"{ORDERS}{order.pk}/detach-invoice/", {}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)


# ══════════════════════════════════════════════════════════════════════════
# 4 — الفاتورة المولَّدة
# ══════════════════════════════════════════════════════════════════════════

class GeneratedInvoiceTest(ServiceOrderTestBase):
    def test_the_labour_line_credits_the_service_revenue_account_not_goods(self):
        order = self.intake()
        self.add_part(order, billing="billable", quantity="1", price="80")

        response = self.generate_invoice(order, labour_amount="120")
        self.assertEqual(response.status_code, 201, response.content)

        order.refresh_from_db()
        invoice = order.sales_invoice
        self.assertEqual(invoice.status, SalesInvoice.STATUS_DRAFT)
        self.assertEqual(invoice.grand_total, Decimal("200.00"))

        post_sales_invoice(invoice, user=self.user)
        credits = {
            line.account.code: line.credit
            for line in JournalLine.objects.filter(
                journal__reference_id=invoice.pk,
                journal__reference_type="SALES_INVOICE",
                credit__gt=0,
            )
        }
        # الفصل هو المقصود: الأجرة خدمة والقطعة بضاعة، ولكلٍّ حسابه.
        self.assertEqual(credits.get("4102-SV"), Decimal("120.00"))
        self.assertEqual(credits.get("4101-SV"), Decimal("80.00"))

    def test_the_labour_amount_falls_back_to_the_recorded_estimate(self):
        order = self.intake(estimated_amount="75")

        response = self.generate_invoice(order)

        self.assertEqual(response.status_code, 201, response.content)
        order.refresh_from_db()
        self.assertEqual(order.sales_invoice.grand_total, Decimal("75.00"))

    def test_generating_with_nothing_to_bill_is_refused(self):
        order = self.intake()

        response = self.generate_invoice(order)

        self.assertEqual(response.status_code, 400, response.content)
        order.refresh_from_db()
        self.assertIsNone(order.sales_invoice_id)

    def test_a_second_invoice_is_refused_while_one_is_attached(self):
        order = self.intake(estimated_amount="75")
        self.assertEqual(self.generate_invoice(order).status_code, 201)

        response = self.generate_invoice(order)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            SalesInvoice.objects.filter(tenant=self.tenant).count(), 1,
        )

    def test_an_order_without_a_partner_bills_the_default_customer(self):
        order = self.intake(partner=None, customer_name="زبون عابر", estimated_amount="50")

        response = self.generate_invoice(order)

        self.assertEqual(response.status_code, 201, response.content)
        order.refresh_from_db()
        self.assertIsNotNone(order.sales_invoice.customer_id)


# ══════════════════════════════════════════════════════════════════════════
# 5 — الحالة وبواباتها
# ══════════════════════════════════════════════════════════════════════════

class WorkflowGateTest(ServiceOrderTestBase):
    def test_intake_writes_the_first_event_and_a_server_generated_number(self):
        order = self.intake()

        self.assertTrue(order.order_number.startswith("SO-"))
        self.assertEqual(order.status, ServiceOrder.STATUS_RECEIVED)
        event = order.events.get()
        self.assertIn("استُلم الجهاز", event.text)
        self.assertEqual(event.actor_id, self.user.pk)

    def test_the_workflow_moves_and_logs_every_step(self):
        order = self.intake()

        self.assertEqual(
            self.transition(order, ServiceOrder.STATUS_IN_DIAGNOSIS).status_code, 200,
        )
        self.assertEqual(
            self.transition(order, ServiceOrder.STATUS_IN_REPAIR).status_code, 200,
        )

        order.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.STATUS_IN_REPAIR)
        moves = order.events.filter(event_type=ServiceOrderEvent.TYPE_STATUS)
        self.assertEqual(moves.count(), 2)
        self.assertEqual(moves.last().to_status, ServiceOrder.STATUS_IN_REPAIR)

    def test_delivery_is_blocked_until_covered_parts_are_posted(self):
        order = self.intake()
        self.add_part(order, billing="covered")
        self.assertEqual(self.transition(order, ServiceOrder.STATUS_READY).status_code, 200)

        blocked = self.transition(
            order, ServiceOrder.STATUS_DELIVERED, outcome="repaired",
        )

        self.assertEqual(blocked.status_code, 400, blocked.content)
        self.assertIn("لم تُرحَّل", str(blocked.content, "utf-8"))
        order.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.STATUS_READY)

    def test_delivery_is_blocked_until_billing_is_resolved_then_a_waiver_opens_it(self):
        order = self.intake()
        self.add_part(order, billing="covered")
        self.assertEqual(self.post_covered(order).status_code, 200)
        self.assertEqual(self.transition(order, ServiceOrder.STATUS_READY).status_code, 200)

        blocked = self.transition(
            order, ServiceOrder.STATUS_DELIVERED, outcome="repaired",
        )
        self.assertEqual(blocked.status_code, 400, blocked.content)

        waived = self.client.patch(
            f"{ORDERS}{order.pk}/", {"billing_waived_reason": "مغطى بالكفالة"},
            format="json", **self.headers(),
        )
        self.assertEqual(waived.status_code, 200, waived.content)

        delivered = self.transition(
            order, ServiceOrder.STATUS_DELIVERED, outcome="repaired",
        )
        self.assertEqual(delivered.status_code, 200, delivered.content)
        order.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.STATUS_DELIVERED)
        self.assertEqual(order.outcome, ServiceOrder.OUTCOME_REPAIRED)
        self.assertIsNotNone(order.delivered_at)

    def test_delivery_needs_an_explicit_outcome(self):
        order = self.intake(billing_waived_reason="بلا كلفة")
        self.assertEqual(self.transition(order, ServiceOrder.STATUS_READY).status_code, 200)

        response = self.transition(order, ServiceOrder.STATUS_DELIVERED)

        self.assertEqual(response.status_code, 400, response.content)

    def test_a_delivered_order_is_frozen(self):
        order = self.intake(billing_waived_reason="بلا كلفة")
        self.assertEqual(self.transition(order, ServiceOrder.STATUS_READY).status_code, 200)
        self.assertEqual(
            self.transition(
                order, ServiceOrder.STATUS_DELIVERED, outcome="no_fault",
            ).status_code,
            200,
        )

        edited = self.client.patch(
            f"{ORDERS}{order.pk}/", {"diagnosis": "بعد التسليم"}, format="json",
            **self.headers(),
        )
        moved = self.transition(order, ServiceOrder.STATUS_IN_REPAIR)

        self.assertEqual(edited.status_code, 400, edited.content)
        self.assertEqual(moved.status_code, 400, moved.content)

    def test_cancellation_is_blocked_while_a_posting_is_live_and_opens_after_unpost(self):
        order = self.intake()
        self.add_part(order, billing="covered")
        self.assertEqual(self.post_covered(order).status_code, 200)

        blocked = self.transition(order, ServiceOrder.STATUS_CANCELLED)
        self.assertEqual(blocked.status_code, 400, blocked.content)

        self.assertEqual(self.unpost_covered(order).status_code, 200)
        cancelled = self.transition(order, ServiceOrder.STATUS_CANCELLED)

        self.assertEqual(cancelled.status_code, 200, cancelled.content)
        order.refresh_from_db()
        self.assertEqual(order.status, ServiceOrder.STATUS_CANCELLED)

    def test_cancellation_is_blocked_while_an_invoice_is_attached(self):
        order = self.intake(estimated_amount="50")
        self.assertEqual(self.generate_invoice(order).status_code, 201)

        response = self.transition(order, ServiceOrder.STATUS_CANCELLED)

        self.assertEqual(response.status_code, 400, response.content)

    def test_orders_are_cancelled_never_deleted(self):
        order = self.intake()

        response = self.client.delete(f"{ORDERS}{order.pk}/", **self.headers())

        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(ServiceOrder.objects.filter(pk=order.pk).exists())

    def test_an_order_needs_an_owner_and_a_device(self):
        nameless = self.client.post(
            ORDERS, {"order_date": ORDER_DATE, "serial": "X-1"}, format="json",
            **self.headers(),
        )
        deviceless = self.client.post(
            ORDERS, {"order_date": ORDER_DATE, "customer_name": "سامي"},
            format="json", **self.headers(),
        )

        self.assertEqual(nameless.status_code, 400, nameless.content)
        self.assertIn("customer_name", nameless.data)
        self.assertEqual(deviceless.status_code, 400, deviceless.content)
        self.assertIn("serial", deviceless.data)

    def test_approval_is_stamped_by_the_server_and_logged(self):
        order = self.intake(estimated_amount="150")

        response = self.client.post(
            f"{ORDERS}{order.pk}/approve/", {"note": "هاتفياً"}, format="json",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        self.assertIsNotNone(order.approved_at)
        self.assertEqual(order.approved_by_id, self.user.pk)
        self.assertTrue(
            order.events.filter(event_type=ServiceOrderEvent.TYPE_APPROVAL).exists(),
        )


# ══════════════════════════════════════════════════════════════════════════
# الاستقبال — البحث الموحّد
# ══════════════════════════════════════════════════════════════════════════

class IntakeLookupTest(ServiceOrderTestBase):
    def test_lookup_reads_the_warranty_card_and_the_open_orders(self):
        WarrantyCard.objects.create(
            tenant=self.tenant, serial="DEV-9", device_name="لابتوب",
            start_date="2026-01-01", duration_months=12, end_date="2999-01-01",
            source=WarrantyCard.SOURCE_MANUAL,
        )
        order = self.intake(serial="DEV-9")

        response = self.client.get(f"{ORDERS}lookup/?serial=DEV-9", **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["warranty"]["covered"])
        self.assertEqual(len(response.data["warranty"]["cards"]), 1)
        self.assertEqual(
            [row["id"] for row in response.data["open_orders"]], [order.pk],
        )

    def test_the_sensitive_device_chip_appears_only_when_that_module_is_licensed(self):
        from device_registry.models import SensitiveDevice

        SensitiveDevice.objects.create(
            tenant=self.tenant, customer_name="سامي", customer_phone="0599000111",
            model_name="آيفون", serial_number="DEV-7", imei="490154203237518",
        )

        unlicensed = self.client.get(
            f"{ORDERS}lookup/?serial=DEV-7", **self.headers(),
        ).data
        TenantModule.objects.create(
            tenant=self.tenant, module_key="sensitive_devices", enabled=True,
        )
        licensed = self.client.get(
            f"{ORDERS}lookup/?serial=DEV-7", **self.headers(),
        ).data

        self.assertEqual(unlicensed["sensitive_devices"], [])
        self.assertEqual(
            [row["serial_number"] for row in licensed["sensitive_devices"]], ["DEV-7"],
        )
        # ولا مفتاح أجنبي في أي اتجاه — الرابط معرّفٌ نصي وحده.
        self.assertFalse(
            any(
                field.related_model is SensitiveDevice
                for field in ServiceOrder._meta.get_fields()
                if getattr(field, "related_model", None) is not None
            )
        )

    def test_lookup_without_a_serial_answers_empty_not_everything(self):
        self.intake(serial="DEV-3")

        response = self.client.get(f"{ORDERS}lookup/?serial=", **self.headers())

        self.assertEqual(response.data["open_orders"], [])
        self.assertEqual(response.data["warranty"]["cards"], [])


# ══════════════════════════════════════════════════════════════════════════
# 6 — البوابة والعزل
# ══════════════════════════════════════════════════════════════════════════

class ServiceOrderModuleGateTest(ServiceOrderTestBase):
    def test_every_endpoint_is_404_without_a_module_license(self):
        order = self.intake()
        part = self.add_part(order, billing="covered")
        self.license.delete()

        calls = [
            ("get", ORDERS, None),
            ("post", ORDERS, {"order_date": ORDER_DATE, "serial": "Z", "customer_name": "س"}),
            ("get", f"{ORDERS}{order.pk}/", None),
            ("patch", f"{ORDERS}{order.pk}/", {"diagnosis": "x"}),
            ("delete", f"{ORDERS}{order.pk}/", None),
            ("post", f"{ORDERS}{order.pk}/transition/", {"to_status": "in_repair"}),
            ("post", f"{ORDERS}{order.pk}/note/", {"text": "x"}),
            ("post", f"{ORDERS}{order.pk}/approve/", {}),
            ("post", f"{ORDERS}{order.pk}/parts/", {"product": self.part_product.pk, "quantity": "1"}),
            ("patch", f"{ORDERS}{order.pk}/parts/{part.pk}/", {"quantity": "2"}),
            ("delete", f"{ORDERS}{order.pk}/parts/{part.pk}/", None),
            ("post", f"{ORDERS}{order.pk}/post-covered/", {}),
            ("post", f"{ORDERS}{order.pk}/unpost-covered/", {}),
            ("post", f"{ORDERS}{order.pk}/generate-invoice/", {}),
            ("post", f"{ORDERS}{order.pk}/detach-invoice/", {}),
            ("get", f"{ORDERS}lookup/?serial=DEV-1", None),
        ]
        for method, url, body in calls:
            with self.subTest(method=method, url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(
                    response.status_code, 404,
                    f"{method} {url} → {response.status_code}",
                )


class ServiceOrderIsolationTest(ServiceOrderTestBase):
    def setUp(self):
        super().setUp()
        self.other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(
            tenant=self.other, module_key="after_sales", enabled=True,
        )
        self.other_order = ServiceOrder.objects.create(
            tenant=self.other, order_number="SO-X-1", order_date=ORDER_DATE,
            customer_name="زبون الغير", serial="OTHER-1",
        )
        self.mine = self.intake(serial="MINE-1")

    def test_the_list_shows_only_the_active_company_orders(self):
        response = self.client.get(ORDERS, **self.headers())

        self.assertEqual([row["serial"] for row in response.data], ["MINE-1"])

    def test_every_detail_endpoint_hides_another_company_order(self):
        calls = [
            ("get", f"{ORDERS}{self.other_order.pk}/", None),
            ("patch", f"{ORDERS}{self.other_order.pk}/", {"diagnosis": "تسريب"}),
            ("post", f"{ORDERS}{self.other_order.pk}/transition/", {"to_status": "in_repair"}),
            ("post", f"{ORDERS}{self.other_order.pk}/post-covered/", {}),
            ("post", f"{ORDERS}{self.other_order.pk}/generate-invoice/", {}),
        ]
        for method, url, body in calls:
            with self.subTest(method=method):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 404, response.content)

        self.other_order.refresh_from_db()
        self.assertEqual(self.other_order.diagnosis, "")

    def test_a_part_cannot_point_at_another_company_product(self):
        outsider = Product.objects.create(
            tenant=self.other, sku="OUT-1", name_ar="صنف الغير",
        )

        response = self.client.post(
            f"{ORDERS}{self.mine.pk}/parts/",
            {"product": outsider.pk, "quantity": "1"}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_an_order_cannot_point_at_another_company_customer(self):
        outsider = Partner.objects.create(
            tenant=self.other, name="زبون الغير", partner_type="Customer",
        )

        response = self.client.post(
            ORDERS,
            {"order_date": ORDER_DATE, "partner": outsider.pk, "serial": "X-9"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_lookup_never_reaches_across_companies(self):
        response = self.client.get(f"{ORDERS}lookup/?serial=OTHER-1", **self.headers())

        self.assertEqual(response.data["open_orders"], [])
