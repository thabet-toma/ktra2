"""«تعديل الاستحقاق» بقيد فرق، وتعديل تكلفة البضاعة معه، والفائض.

كان «تراجع عن الاستحقاق» يحذف القيد ويُعاد الترحيل — فيضيع الأثر، والفواتير المرحّلة
تبقى على التكلفة القديمة. الآن: القيد الأصلي باقٍ وقيدُ فرقٍ على المستند نفسه، وكل
فاتورة دولية مرحّلة على الشحنة تُسوّى تكلفتُها: الباقي في المخزن على المخزون وطبقته،
والمبيع على ت.ب.م، وغير المستلَم على وسيط الاستلام. وما زاد من المدفوع لأن المستحق نزل
يعود «تحت الحساب» للطرف (توزيعٌ يُقلَّص أو دفعةٌ تُفصل) فيُوزَّع أو يُستردّ.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product, StockLayer, StockMovement
from inventory.services import record_stock_movement
from logistics.accruals import (
    post_clearance_accrual,
    post_freight_accrual,
    post_local_shipment_accrual,
)
from logistics.domain.party_accruals import accrual_status
from logistics.landed_cost import posted_invoices_cost_drift
from logistics.models import (
    LocalShipment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
)
from logistics.services import GR_IR_ACCOUNT_CODE
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))
Q2 = D("0.01")


class AccrualAdjustTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="accadj", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة تعديل الاستحقاق", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)

        def liability(code, name):
            return Account.objects.create(
                tenant=cls.tenant, code=code, name=name, account_type="Liability", is_active=True)

        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="BOX-ADJ", name="صندوق", account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="adj-box", name="صندوق", currency_code="ILS",
            account=cls.cash)
        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مصنع", partner_type="Supplier", linked_account=cls.ap)
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل", partner_type="ShippingAgent",
            linked_account=liability("AP-AG", "ذمم الوكيل"))
        cls.broker = Partner.objects.create(
            tenant=cls.tenant, name="مخلّص", partner_type="CustomsBroker",
            linked_account=liability("AP-BR", "ذمم المخلص"))
        cls.carrier = Partner.objects.create(
            tenant=cls.tenant, name="ناقل", partner_type="LocalTransporter",
            linked_account=liability("AP-CA", "ذمم الناقل"))

        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-ADJ", shipping_agent=cls.agent,
            chargeable_unit="cbm", freight_rate=D("1000"), total_shipping_cost_usd=D("1000"),
            departure_date="2026-07-01")
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-ADJ", partner=cls.supplier,
            order_date="2026-06-01", total_amount=D("1000"), total_cbm=D("1"))
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="ADJ-1", name_ar="صنف", quantity_on_hand=D("0"), avg_cost=D("0"))
        LogisticsDealItem.objects.create(
            deal=cls.deal, product=cls.product, quantity=D("10"), unit_price=D("100"))
        LogisticsShipmentDeal.objects.create(shipment=cls.shipment, deal=cls.deal)
        LogisticsPayment.objects.create(
            deal=cls.deal, amount=D("1000"), usd_to_ils=D("3.5"), status="Confirmed")

        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, customs_broker=cls.broker,
            clearance_date="2026-07-05", currency=cls.ils)
        for seq, (line_type, desc, amount) in enumerate((
            ("vat", "ضريبة القيمة المضافة", "300"),
            ("broker_commission", "عمولة المخلص", "600"),
        ), start=1):
            LogisticsClearanceLine.objects.create(
                clearance=cls.clearance, seq=seq, line_type=line_type,
                description=desc, debit=D(amount), credit=D("0"))
        cls.local = LocalShipment.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, clearance=cls.clearance,
            carrier=cls.carrier, amount=D("450"), currency=cls.ils, exchange_rate=D("1"),
            capitalize_to_inventory=True,
            expense_account=Account.objects.get(tenant=cls.tenant, code="5305"),
            delivery_date="2026-07-06")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        post_freight_accrual(LogisticsShipment.objects.get(pk=self.shipment.pk), D("3.6"))
        post_clearance_accrual(LogisticsClearance.objects.get(pk=self.clearance.pk))
        post_local_shipment_accrual(LocalShipment.objects.get(pk=self.local.pk))

    # ── مساعدات ─────────────────────────────────────────────────────────────
    def _invoice(self, *, post=True, receive=True):
        res = self.client.post(
            "/api/logistics/purchase-invoices/import-from-clearance/",
            {"clearance_id": self.clearance.id, "deal_ids": [self.deal.id],
             "deal_remaining_rate": "3.5", "shipment_remaining_rate": "3.6"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)
        inv = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)
        if post:
            res = self.client.post(
                f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
                {"receive_on_post": receive}, format="json", **self.h)
            self.assertEqual(res.status_code, 201, res.content)
            inv.refresh_from_db()
        return inv

    def _sell(self, qty):
        return record_stock_movement(
            product=Product.objects.get(pk=self.product.pk), movement_type="OUT",
            quantity=D(qty), reference_type="SALE", reference_id=990001,
            movement_date="2026-07-20", tenant=self.tenant)

    def _adjust_clearance(self, commission, **extra):
        lines = [
            {"label": "ضريبة القيمة المضافة", "amount": 300, "type": "vat"},
            {"label": "عمولة المخلص", "amount": commission, "type": "broker_commission"},
        ]
        return self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/adjust-accrual/",
            {"cost_lines": lines, "date": "2026-08-01", **extra}, format="json", **self.h)

    def _net(self, code, **filters):
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account__code=code, **filters,
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        return ((agg["d"] or D("0")) - (agg["c"] or D("0"))).quantize(Q2)

    def _party_credit(self, partner):
        agg = JournalLine.objects.filter(tenant=self.tenant, partner=partner).aggregate(
            d=Sum("base_debit"), c=Sum("base_credit"))
        return ((agg["c"] or D("0")) - (agg["d"] or D("0"))).quantize(Q2)

    # ── M3: قيد فرقٍ لا حذف ─────────────────────────────────────────────────
    def test_clearance_adjustment_posts_a_difference_journal_and_keeps_the_original(self):
        original = LogisticsClearance.objects.get(pk=self.clearance.pk).journal_id
        res = self._adjust_clearance(750)
        self.assertEqual(res.status_code, 200, res.content)

        clearance = LogisticsClearance.objects.get(pk=self.clearance.pk)
        self.assertEqual(clearance.journal_id, original, "القيد الأصلي باقٍ")
        adj = JournalHeader.objects.get(pk=res.data["journal_id"])
        self.assertEqual((adj.reference_type, adj.reference_id),
                         ("LOGISTICS_CLEARANCE_ADJUST", clearance.pk))
        self.assertEqual(str(adj.transaction_date), "2026-08-01")
        rows = {(l.account.code, l.partner_id): (l.debit, l.credit) for l in adj.lines.select_related("account")}
        self.assertEqual(rows, {
            ("5302", None): (D("150.00"), D("0.00")),
            ("AP-BR", self.broker.id): (D("0.00"), D("150.00")),
        })
        self.assertEqual(accrual_status("clearance", clearance)["due"], D("1050.00"))
        self.assertEqual(self._party_credit(self.broker), D("1050.00"))
        self.assertEqual((res.data["due_before"], res.data["due_after"]), ("900.00", "1050.00"))

        # تعديلٌ ثانٍ يُقاس على الأصل وكل تعديلاته.
        again = self._adjust_clearance(500)
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.data["difference"], "-250.00")
        self.assertEqual(self._party_credit(self.broker), D("800.00"))

    def test_same_amounts_are_refused_and_preview_writes_nothing(self):
        same = self._adjust_clearance(600)
        self.assertEqual(same.status_code, 400, same.content)

        journals = JournalHeader.objects.filter(tenant=self.tenant).count()
        preview = self._adjust_clearance(700, preview=True)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.data["difference"], "100.00")
        self.assertIsNone(preview.data["journal_id"])
        self.assertEqual(JournalHeader.objects.filter(tenant=self.tenant).count(), journals)
        self.assertEqual(
            LogisticsClearance.objects.get(pk=self.clearance.pk).lines.get(line_type="broker_commission").debit,
            D("600.00"), "المعاينة لا تكتب بنود التخليص")

    def test_local_adjustment_and_unpost_removes_adjustments_too(self):
        res = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/adjust-accrual/",
            {"amount": "500"}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._party_credit(self.carrier), D("500.00"))
        self.assertEqual(LocalShipment.objects.get(pk=self.local.pk).amount, D("500.00"))

        undo = self.client.post(f"/api/logistics/local-shipments/{self.local.pk}/unpost/", {}, **self.h)
        self.assertEqual(undo.status_code, 200, undo.content)
        self.assertEqual(self._party_credit(self.carrier), D("0.00"))
        self.assertFalse(JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="LOCAL_SHIPMENT_ADJUST").exists())

    def test_freight_adjustment_keeps_the_agent_dollar_balance_true(self):
        # الدولار نزل والسعر صعد: فرق الشيكل موجب وفرق الدولار سالب.
        res = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/adjust-freight-accrual/",
            {"freight_rate": "900", "freight_exchange_rate": "4.2"}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        ship = LogisticsShipment.objects.get(pk=self.shipment.pk)
        self.assertEqual((ship.total_shipping_cost_usd, ship.freight_exchange_rate), (D("900.00"), D("4.2")))
        self.assertEqual(self._party_credit(self.agent), D("3780.00"))
        usd = JournalLine.objects.filter(tenant=self.tenant, partner=self.agent).aggregate(
            a=Sum("amount_currency"))["a"]
        self.assertEqual(usd, D("-900.00"))

        # تعيين سعر الشحن بعد الاستحقاق كان يغيّر الدولار بصمت — صار يوجّه إلى التعديل.
        blocked = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/freight/",
            {"chargeable_unit": "cbm", "freight_rate": 800}, format="json", **self.h)
        self.assertEqual(blocked.status_code, 400, blocked.content)

    # ── M4: تكلفة البضاعة تتعدّل تلقائياً ──────────────────────────────────
    def test_posted_invoice_is_revalued_stock_on_inventory_and_sold_on_cogs(self):
        inv = self._invoice()
        layer = StockLayer.objects.get(tenant=self.tenant, product=self.product)
        cost_before = layer.unit_cost
        sale = self._sell("4")
        sale_cost_before = sale.total_cost

        res = self._adjust_clearance(900)  # +300 على العمولة
        self.assertEqual(res.status_code, 200, res.content)
        [reval] = res.data["revaluations"]
        self.assertEqual(reval["invoice_number"], inv.invoice_number)
        self.assertEqual((D(reval["inventory"]), D(reval["cogs"]), D(reval["clearing"])),
                         (D("180.00"), D("120.00"), D("0.00")))

        journal = JournalHeader.objects.get(pk=reval["journal_id"])
        self.assertEqual((journal.reference_type, journal.reference_id),
                         ("PURCHASE_INVOICE_LANDED_ADJ", inv.pk))
        self.assertEqual(self._net("5302"), D("0.00"), "حصّة الفاتورة تُصفّي فرق العمولة")
        from inventory.services import _resolve_line_account
        cogs = _resolve_line_account(self.product, "cogs", tenant_id=self.tenant.TenantID)
        self.assertEqual(self._net(cogs.code, journal=journal), D("120.00"))

        layer.refresh_from_db()
        self.assertEqual(layer.unit_cost - cost_before, D("30.0000"))
        sale.refresh_from_db()
        self.assertEqual(sale.total_cost - sale_cost_before, D("120.00"))
        product = Product.objects.get(pk=self.product.pk)
        self.assertEqual(product.avg_cost.quantize(Q2), layer.unit_cost.quantize(Q2))
        # الفاتورة المرحّلة تطابق شحنتها بعد التعديل — لا لافتة «تغيّرت التكاليف».
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.pk)
        self.assertEqual(drift["stale_posted_invoices"], [])

    def test_cost_follows_goods_moved_between_warehouses(self):
        self._invoice()
        product = Product.objects.get(pk=self.product.pk)
        out = record_stock_movement(
            product=product, movement_type="OUT", quantity=D("10"),
            reference_type="WAREHOUSE_TRANSFER", reference_id=880001,
            movement_date="2026-07-15", tenant=self.tenant)
        record_stock_movement(
            product=Product.objects.get(pk=product.pk), movement_type="IN", quantity=D("10"),
            unit_cost=out.unit_cost, reference_type="WAREHOUSE_TRANSFER", reference_id=880001,
            movement_date="2026-07-15", tenant=self.tenant)
        self._sell("4")  # من طبقة الوجهة
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        [reval] = res.data["revaluations"]
        self.assertEqual((D(reval["inventory"]), D(reval["cogs"])), (D("180.00"), D("120.00")))
        dest = StockLayer.objects.get(
            tenant=self.tenant, source_movement__reference_type="WAREHOUSE_TRANSFER")
        source = StockLayer.objects.get(
            tenant=self.tenant, source_movement__reference_type="PURCHASE_INVOICE")
        self.assertEqual(dest.unit_cost, source.unit_cost)

    def test_unreceived_goods_go_to_clearing_and_arrive_at_the_new_cost(self):
        inv = self._invoice(receive=False)
        res = self._adjust_clearance(1100)  # +500
        self.assertEqual(res.status_code, 200, res.content)
        [reval] = res.data["revaluations"]
        self.assertEqual(D(reval["clearing"]), D("500.00"))

        inv.refresh_from_db()
        item = inv.items.get()
        received = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.id, "quantity": "10",
                        "warehouse_id": self._default_warehouse_id()}]},
            format="json", **self.h)
        self.assertEqual(received.status_code, 200, received.content)
        move = StockMovement.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=inv.pk)
        self.assertEqual(move.total_cost, item.landed_line_total_ils)
        self.assertEqual(self._net(GR_IR_ACCOUNT_CODE), D("0.00"))

    def test_stale_posted_invoice_blocks_the_adjustment(self):
        inv = self._invoice()
        PurchaseInvoice.objects.filter(pk=inv.pk).update(subtotal=D("1"))
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn(inv.invoice_number, res.data["error"])

    def test_draft_invoice_is_rebuilt(self):
        inv = self._invoice(post=False)
        before = inv.subtotal
        res = self._adjust_clearance(900)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["drafts_updated"], 1)
        inv.refresh_from_db()
        self.assertEqual(inv.subtotal - before, D("300.00"))

    # ── M5: التخفيض تحت المدفوع يعود «تحت الحساب» ──────────────────────────
    def test_reduction_after_full_payment_splits_the_excess_on_account(self):
        from sales.models import SupplierPayment

        paid = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/pay_from_cashbox/",
            {"amount": "450", "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-10"}, format="json", **self.h)
        self.assertEqual(paid.status_code, 201, paid.content)
        box_before = self._net(self.cash.code)
        preview = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/adjust-accrual/",
            {"amount": "400", "preview": True}, format="json", **self.h)
        self.assertEqual((preview.data["surplus_after"], preview.data["on_account"]), ("50.00", None))
        res = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/adjust-accrual/",
            {"amount": "400"}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["surplus_after"], "50.00")

        # الدفعة صارت 400 على الإرسالية، والـ50 سند صرفٍ مرحَّلٌ «تحت الحساب» — والصندوق كما هو.
        voucher = SupplierPayment.objects.get(pk=res.data["on_account"]["voucher"])
        self.assertEqual((voucher.amount, voucher.is_posted, voucher.partner_id), (D("50.00"), True, self.carrier.id))
        self.assertEqual(self._net(self.cash.code), box_before)
        status = accrual_status("local", LocalShipment.objects.get(pk=self.local.pk))
        self.assertEqual((status["overpaid"], status["surplus"], status["remaining"]), (D("0"), D("0"), D("0")))
        profile = self.client.get(f"/api/partners/{self.carrier.id}/profile/", **self.h).data
        self.assertEqual((profile["accrual_surplus"], profile["on_account_payments"]), ("0.00", "50.00"))
        surplus = self.client.get(f"/api/partners/{self.carrier.id}/surplus/", **self.h).data["rows"]
        self.assertEqual([(r["source"], r["id"], r["unallocated"]) for r in surplus],
                         [("supplier_payment", voucher.pk, "50.00")])

        # دفعةٌ أكبر من المستحق لحظتها ← «تحت الحساب» لا فائض.
        more = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/pay_from_cashbox/",
            {"amount": "1000", "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-10"}, format="json", **self.h)
        self.assertEqual(more.status_code, 201, more.content)
        broker = self.client.get(f"/api/partners/{self.broker.id}/profile/", **self.h).data
        self.assertEqual((broker["on_account_payments"], broker["accrual_surplus"]), ("100.00", "0.00"))

    def test_reduction_trims_an_allocated_voucher_back_on_account(self):
        from logistics.domain.party_accruals import allocate_voucher_to_accruals, voucher_unallocated
        from logistics.models import LogisticsAccrualAllocation
        from sales.models import SupplierPayment
        from sales.services import post_supplier_payment

        voucher = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.broker, payment_date="2026-07-08", amount=D("900"),
            currency=self.ils, exchange_rate=D("1"), cash_or_bank_account=self.cash)
        post_supplier_payment(voucher, user=self.user)
        allocate_voucher_to_accruals(voucher, [{"kind": "clearance", "id": self.clearance.pk, "amount": "900"}])
        res = self._adjust_clearance(400)  # المستحق 900 ← 700
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn(f"سند صرف #{voucher.pk} (200.00)", res.data["on_account"]["released"])
        alloc = LogisticsAccrualAllocation.objects.get(payment=voucher)
        self.assertEqual((alloc.amount, alloc.amount_base), (D("700.00"), D("700.00")))
        self.assertEqual(voucher_unallocated(voucher), D("200.00"))
        status = accrual_status("clearance", LogisticsClearance.objects.get(pk=self.clearance.pk))
        self.assertEqual((status["overpaid"], status["remaining"]), (D("0"), D("0")))
        broker = self.client.get(f"/api/partners/{self.broker.id}/profile/", **self.h).data
        self.assertEqual((broker["on_account_payments"], broker["accrual_surplus"]), ("200.00", "0.00"))

    def _default_warehouse_id(self):
        from inventory.models import Warehouse
        return Warehouse.objects.get(tenant=self.tenant, is_default=True).id
