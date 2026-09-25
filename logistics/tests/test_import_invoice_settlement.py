"""الفاتورة الدولية: ترحيلها يُطابق استحقاقات شحنتها، ودفعها = تكاليفها الأربع.

عند الإفراج يُدين الاستحقاقُ 5301 وبنودَ التخليص ومصروفَ النقل ويُدائن الوكيلَ
والمخلّصَ والناقل (accruals.py)؛ والفاتورة ترسمل التكلفة نفسها في البضاعة.
كان ترحيلها يُدائن المورد بالإجمالي المحمَّل كلّه — فتثبت تكاليف الشحن مرّتين
(مصروفاً ومخزوناً) وتتضخّم ذمّة المورد بما لا يدين به. وضريبة الاستيراد كانت
تُعدّ مرّتين: مدخلاتٍ في 1105 وتكلفةً في حوض التخليص.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.accruals import (
    AccrualSkipped,
    post_clearance_accrual,
    post_freight_accrual,
    post_local_shipment_accrual,
)
from logistics.landed_cost import import_invoice_cost_shares
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
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))
Q2 = D("0.01")


class ImportInvoiceSettlementTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="impsettle", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة تسوية الاستيراد", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)

        def liability(code, name):
            return Account.objects.create(
                tenant=cls.tenant, code=code, name=name,
                account_type="Liability", is_active=True)

        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مصنع الكوابل", partner_type="Supplier",
            linked_account=cls.ap)
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل الشحن", partner_type="ShippingAgent",
            linked_account=liability("AP-AGENT", "ذمم الوكيل"))
        cls.broker = Partner.objects.create(
            tenant=cls.tenant, name="المخلّص", partner_type="CustomsBroker",
            linked_account=liability("AP-BROKER", "ذمم المخلص"))
        cls.carrier = Partner.objects.create(
            tenant=cls.tenant, name="الناقل", partner_type="LocalTransporter",
            linked_account=liability("AP-CARRIER", "ذمم الناقل"))

        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-SET-1",
            shipping_agent=cls.agent, total_shipping_cost_usd=D("1000"),
            departure_date="2026-07-01")
        cls.deals = []
        for n, (usd, cbm) in enumerate((("1000", "1"), ("2000", "2"), ("3000", "3")), start=1):
            deal = LogisticsDeal.objects.create(
                tenant=cls.tenant, ref_number=f"D-SET-{n}", partner=cls.supplier,
                order_date="2026-06-01", total_amount=D(usd),
                total_cbm=D(cbm))
            product = Product.objects.create(
                tenant=cls.tenant, sku=f"SET-{n}", name_ar=f"صنف {n}",
                quantity_on_hand=D("0"), avg_cost=D("0"))
            LogisticsDealItem.objects.create(
                deal=deal, product=product, quantity=D("10"), unit_price=D(usd) / 10)
            LogisticsShipmentDeal.objects.create(shipment=cls.shipment, deal=deal)
            LogisticsPayment.objects.create(
                deal=deal, amount=D(usd), usd_to_ils=D("3.5"), status="Confirmed")
            cls.deals.append(deal)

        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, customs_broker=cls.broker,
            clearance_date="2026-07-05", currency=cls.ils, declaration_number="CL-SET")
        for seq, (line_type, desc, amount) in enumerate((
            ("vat", "ضريبة القيمة المضافة", "300"),
            ("broker_commission", "عمولة المخلص", "600"),
            ("declaration_fee", "رسوم البيان", "90"),
        ), start=1):
            LogisticsClearanceLine.objects.create(
                clearance=cls.clearance, seq=seq, line_type=line_type,
                description=desc, debit=D(amount), credit=D("0"))
        cls.local = LocalShipment.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, clearance=cls.clearance,
            carrier=cls.carrier, amount=D("450"), currency=cls.ils,
            exchange_rate=D("1"), capitalize_to_inventory=True,
            expense_account=Account.objects.get(tenant=cls.tenant, code="5305"),
            delivery_date="2026-07-06")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _accrue(self, *, local=True):
        # نسخٌ طازجة: إنشاء التخليص يقلب حالة الشحنة بإشارة.
        post_freight_accrual(LogisticsShipment.objects.get(pk=self.shipment.pk), D("3.6"))
        post_clearance_accrual(LogisticsClearance.objects.get(pk=self.clearance.pk))
        if local:
            post_local_shipment_accrual(LocalShipment.objects.get(pk=self.local.pk))

    def _release_and_import(self):
        """الإفراج: الاستحقاقات الثلاثة، ثم فاتورةٌ لكل صفقة."""
        self._accrue()
        res = self.client.post(
            "/api/logistics/purchase-invoices/import-from-clearance/",
            {"clearance_id": self.clearance.id,
             "deal_ids": [d.id for d in self.deals],
             "deal_remaining_rate": "3.5", "shipment_remaining_rate": "3.6"},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        return [PurchaseInvoice.objects.get(tenant=self.tenant, deal=d) for d in self.deals]

    def _post(self, inv):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {"receive_on_post": False}, format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        inv.refresh_from_db()
        return inv

    def _net(self, code):
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account__code=code,
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        return ((agg["d"] or D("0")) - (agg["c"] or D("0"))).quantize(Q2)

    # ── M1: ضريبة الاستيراد مدخلاتٌ لا تكلفة ───────────────────────────────
    def test_import_vat_is_input_tax_not_landed_cost(self):
        invoices = self._release_and_import()
        clearance_shares = sum(
            (import_invoice_cost_shares(inv)["clearance"] for inv in invoices), D("0"))
        # حوض التخليص 690 (عمولة + بيان) — لا 990 بضريبة الـ300.
        self.assertLessEqual(abs(clearance_shares - D("690")), D("0.05"))

    # ── M2: المورد بما يخصّه، والاستحقاقات تُصفّى بالحصص ─────────────────
    def test_posting_credits_supplier_merchandise_only_and_clears_accruals(self):
        invoices = self._release_and_import()
        for inv in invoices:
            self._post(inv)
            lines = list(inv.journal.lines.all())
            self.assertEqual(
                sum((l.debit for l in lines), D("0")), sum((l.credit for l in lines), D("0")))
            # المورد دائنٌ بالبضاعة وحدها: دولار الصفقة × 3.5 (سعر دفعاتها).
            supplier_credit = sum(
                (l.credit for l in lines if l.account_id == self.ap.id), D("0"))
            self.assertEqual(supplier_credit, (inv.deal.total_amount * D("3.5")).quantize(Q2))
            # وبالدولار: مبلغ الصفقة نفسه — كشف المورد بالدولار يقرؤه.
            supplier_line = next(l for l in lines if l.account_id == self.ap.id)
            self.assertEqual((supplier_line.amount_currency, supplier_line.currency_code),
                             (-inv.deal.total_amount, "USD"))
            # سطر الذمم وحده يحمل الشريك.
            self.assertFalse(any(
                l.partner_id for l in lines if l.account_id != self.ap.id))

        # كل استحقاق صُفّي بحصص فواتيره (فروق تقريب الحصص وحدها).
        for code in ("5301", "5302", "5303", "5305"):
            self.assertLessEqual(abs(self._net(code)), D("0.05"), code)
        # الضريبة في المدخلات مرّةً واحدة.
        self.assertEqual(self._net("1105"), D("300.00"))
        # ذمم المورد = البضاعة (6000$ × 3.5) لا الإجمالي المحمَّل.
        ap_credit = JournalLine.objects.filter(
            tenant=self.tenant, account=self.ap, partner=self.supplier,
        ).aggregate(c=Sum("credit"))["c"]
        self.assertEqual(ap_credit, D("21000.00"))
        # والبضاعة حملت التكلفة كاملة: إجمالي الفواتير = بضاعة + 3600 + 690 + 450.
        grand = sum((inv.grand_total for inv in invoices), D("0"))
        self.assertLessEqual(abs(grand - D("25740")), D("0.05"))

    def test_component_without_posted_accrual_stays_on_supplier(self):
        # نقلٌ محلي بلا استحقاق مرحّل: حصّته تبقى على المورد كما كانت.
        self._accrue(local=False)
        with mock.patch(
            "logistics.accruals.post_local_shipment_accrual",
            side_effect=AccrualSkipped("الناقل بلا حساب"),
        ):
            res = self.client.post(
                "/api/logistics/purchase-invoices/import-from-clearance/",
                {"clearance_id": self.clearance.id, "deal_ids": [self.deals[0].id],
                 "deal_remaining_rate": "3.5", "shipment_remaining_rate": "3.6"},
                format="json", **self._auth())
        self.assertFalse(LocalShipment.objects.get(pk=self.local.pk).is_posted)
        self.assertEqual(res.status_code, 201, res.content)
        inv = self._post(PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deals[0]))
        local_share = import_invoice_cost_shares(inv)["local"]
        self.assertGreater(local_share, 0)
        supplier_credit = inv.journal.lines.filter(account=self.ap).aggregate(
            c=Sum("credit"))["c"]
        self.assertEqual(supplier_credit, D("3500.00") + local_share)

    # ── حارس الترحيل يقارن التكاليف لا الإجمالي: ضريبة الفاتورة ليست تكلفة شحنة ──
    def _recalculate(self, **extra):
        res = self.client.post(
            "/api/logistics/purchase-invoices/recalculate-landed-cost/",
            {"shipment_id": self.shipment.id, **extra}, format="json", **self._auth())
        return res

    def test_invoice_own_tax_does_not_block_posting_or_repost(self):
        # الإنتاج (شحنة 13): الفاتورة تحمل ضريبة 16% والصفقة بلا ضريبة. إعادة
        # الاحتساب تُبقي ضريبة الفاتورة، والصفّ المعاد بناؤه يأخذ ضريبة الصفقة —
        # فكان الحارس يرى «الإجمالي تغيّر» بقيمة الضريبة وحدها ويرفض دائماً.
        invoices = self._release_and_import()
        PurchaseInvoice.objects.filter(pk__in=[i.pk for i in invoices]).update(
            tax_rate=D("16"), tax_type="percentage")
        self.assertEqual(self._recalculate().status_code, 200)
        inv = PurchaseInvoice.objects.get(pk=invoices[0].pk)
        tax = (inv.subtotal * D("0.16")).quantize(Q2)
        self.assertEqual(inv.tax_amount, tax)

        # ترحيلٌ قديم (قبل 51b12571): المورد دائنٌ بالإجمالي المحمَّل كلّه.
        with mock.patch(
            "logistics.accruals.import_invoice_accrual_credits", return_value=[],
        ):
            inv = self._post(inv)
        old_supplier = inv.journal.lines.filter(account=self.ap).aggregate(
            c=Sum("credit"))["c"]
        self.assertEqual(old_supplier, inv.grand_total)

        shares = import_invoice_cost_shares(inv)
        res = self._recalculate(auto_repost=True)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["reconciliation"]["reposted"], 1)

        inv.refresh_from_db()
        lines = list(inv.journal.lines.all())
        self.assertEqual(
            sum((l.debit for l in lines), D("0")), sum((l.credit for l in lines), D("0")))
        new_supplier = sum((l.credit for l in lines if l.account_id == self.ap.id), D("0"))
        # نقصت ذمّة المورد بحصص الشحن والتخليص والنقل، وبقيت له البضاعة + ضريبة فاتورته.
        self.assertEqual(
            old_supplier - new_supplier,
            shares["freight"] + shares["clearance"] + shares["local"])
        self.assertEqual(new_supplier, D("3500.00") + tax)
        # ضريبة الفاتورة مدخلاتٌ في 1105، لا تكلفة: البضاعة لم تتغيّر بها.
        vat = sum((l.debit for l in lines if l.account.code == "1105"), D("0"))
        self.assertEqual(vat, tax)

    def test_posting_still_refuses_when_shipment_costs_changed(self):
        # الحارس باقٍ لما وُضع له: تكلفةٌ أُضيفت للشحنة بعد بناء الفاتورة.
        inv = self._release_and_import()[0]
        LogisticsClearanceLine.objects.create(
            clearance=self.clearance, seq=9, line_type="broker_commission",
            description="عمولة إضافية", debit=D("600"), credit=D("0"))
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {"receive_on_post": False}, format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("إعادة حساب التكلفة", res.json()["error"])

    # ── 3ب: حالة الدفع = التكاليف الأربع مقابل الدفعات الأربع ─────────────
    def _pay_deal(self, deal):
        """دفعة صفقة مرحّلة كما يرحّلها `deals.post_payment`: مدين ذمم المورد."""
        from accounting.services import post_journal
        cash = Account.objects.get(tenant=self.tenant, code="1101")
        payment = LogisticsPayment.objects.get(deal=deal)
        ils = (payment.amount * payment.usd_to_ils).quantize(Q2)
        journal = post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-06-10",
            reference_type="LOGISTICS_PAYMENT", reference_id=payment.pk,
            description=f"دفعة {deal.ref_number}",
            lines_data=[
                {"account": self.ap.id, "partner": self.supplier.id,
                 "debit": ils, "credit": D("0"), "description": "دفعة صفقة"},
                {"account": cash.id, "partner": None,
                 "debit": D("0"), "credit": ils, "description": "دفعة صفقة"},
            ],
        )
        LogisticsPayment.objects.filter(pk=payment.pk).update(is_posted=True, journal=journal)

    def _pay_clearance(self, amount):
        from logistics.models import LogisticsClearancePayment
        LogisticsClearancePayment.objects.create(
            tenant=self.tenant, clearance=self.clearance, amount=D(amount),
            currency=self.ils, cash_box_external_id="box", is_posted=True,
            payment_date="2026-07-07")

    def _pay_freight_and_local(self):
        from logistics.models import LocalShipmentPayment
        LogisticsPayment.objects.create(
            shipment=self.shipment, amount=D("1000"), usd_to_ils=D("3.6"),
            status="Paid", is_posted=True)
        LocalShipmentPayment.objects.create(
            tenant=self.tenant, local_shipment=self.local, amount=D("450"),
            currency=self.ils, exchange_rate=D("1"), payment_date="2026-07-07",
            cash_box_external_id="box", is_posted=True)

    def _breakdown(self, inv):
        res = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()["import_payment"]

    def test_shared_clearance_payment_is_attributed_once_across_invoices(self):
        invoices = self._release_and_import()
        self._pay_clearance("500")
        attributed = [
            D(self._breakdown(inv)["components"]["clearance"]["paid"]) for inv in invoices]
        self.assertTrue(all(part > 0 for part in attributed), attributed)
        self.assertEqual(sum(attributed, D("0")), D("500.00"))

    def test_broker_voucher_allocated_to_clearance_counts_as_clearance_paid(self):
        """سند صرفٍ للمخلّص وُزِّع على التخليص مدفوعٌ للتخليص في 3ب — كدفعة التخليص نفسها."""
        invoices = self._release_and_import()
        box = Account.objects.create(
            tenant=self.tenant, code="BOX-3B", name="صندوق", account_type="Asset", is_active=True)
        voucher = self.client.post("/api/logistics/supplier-payments/", {
            "partner": self.broker.id, "payment_date": "2026-07-08", "amount": "500",
            "currency": self.ils.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": box.id,
        }, format="json", **self._auth())
        self.assertEqual(voucher.status_code, 201, voucher.content)
        before = sum((D(self._breakdown(inv)["components"]["clearance"]["paid"]) for inv in invoices), D("0"))
        self.assertEqual(before, D("0.00"))
        res = self.client.post(
            f"/api/logistics/supplier-payments/{voucher.json()['id']}/allocate-accruals/",
            {"allocations": [{"kind": "clearance", "id": self.clearance.id, "amount": "500"}]},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        attributed = [D(self._breakdown(inv)["components"]["clearance"]["paid"]) for inv in invoices]
        self.assertEqual(sum(attributed, D("0")), D("500.00"))

    def test_status_follows_all_four_costs(self):
        invoices = [self._post(inv) for inv in self._release_and_import()]
        inv = invoices[0]
        first = self._breakdown(inv)
        self.assertEqual(first["payment_status"], "unpaid")
        self.assertEqual(D(first["payable_total"]), inv.grand_total)

        # المورد مسدَّد وحده: جزئية، والمتبقّي = الشحن + التخليص + المحلي.
        for deal in self.deals:
            self._pay_deal(deal)
        partial = self._breakdown(inv)
        self.assertEqual(partial["payment_status"], "partially_paid")
        comps = partial["components"]
        self.assertEqual(D(comps["supplier"]["remaining"]), D("0.00"))
        self.assertEqual(
            D(partial["remaining_balance"]),
            sum((D(comps[k]["cost"]) for k in ("freight", "clearance", "local")), D("0")))

        # كلّ الدائنين مسدَّدون: مدفوعة.
        self._pay_freight_and_local()
        self._pay_clearance("690")
        for inv in invoices:
            done = self._breakdown(inv)
            self.assertEqual(done["payment_status"], "paid", done)
            self.assertEqual(D(done["remaining_balance"]), D("0.00"))

    def test_supplier_side_summary_is_supplier_portion_and_list_matches(self):
        invoices = [self._post(inv) for inv in self._release_and_import()]
        self._pay_deal(self.deals[0])
        inv = invoices[0]
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        # المستحقّ للمورد = ما دائنه به الترحيل، ودفعة الصفقة سدّدته.
        self.assertEqual(D(detail["payable_total"]), D("3500.00"))
        self.assertEqual(D(detail["remaining_balance"]), D("0.00"))
        self.assertEqual(detail["payment_status"], "paid")
        # القائمة (نسخة SQL) تقول الرقم نفسه.
        listed = self.client.get(
            "/api/logistics/purchase-invoices/", {"page_size": 50}, **self._auth()).json()
        rows = listed.get("results", listed)
        row = next(r for r in rows if r["id"] == inv.pk)
        self.assertEqual(D(row["payable_total"]), D("3500.00"))
        self.assertEqual(D(row["remaining_balance"]), D("0.00"))
        self.assertEqual(row["payment_status"], "paid")
        self.assertEqual(row["import_payment"]["payment_status"], "partially_paid")
        # سند المورد لا يتجاوز حصّته: ما بقي للمورد صفر.
        other = next(r for r in rows if r["id"] == invoices[1].pk)
        self.assertEqual(D(other["remaining_balance"]), D("7000.00"))

    def test_deal_paid_through_endpoint_matches_supplier_cost(self):
        """INV-0021 على الإنتاج: صفقةٌ مدفوعةٌ كاملةً بدولار
        بسعر 3.24 عبر زرّ الدفع نفسه — كانت تُعرض «مدفوع 690» مقابل تكلفة 2,235.60:
        القيد رحّل الرقم الدولاري، والملخّص يقرأ الاسميّ لا الأساس."""
        deal = self.deals[0]
        payment = LogisticsPayment.objects.get(deal=deal)
        LogisticsPayment.objects.filter(pk=payment.pk).update(usd_to_ils=D("3.24"))
        cash = Account.objects.get(tenant=self.tenant, code="1101")
        res = self.client.post(
            f"/api/logistics/deals/{deal.pk}/post_payment/{payment.pk}/",
            {"bank_account_id": cash.pk}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        payment.refresh_from_db()
        ap_base = JournalLine.objects.filter(
            journal=payment.journal, account=self.ap).aggregate(s=Sum("base_debit"))["s"]
        self.assertEqual(ap_base, D("3240.00"))  # 1000$ × 3.24

        inv = self._post(self._release_and_import()[0])
        supplier = self._breakdown(inv)["components"]["supplier"]
        self.assertEqual(D(supplier["cost"]), D("3240.00"))
        self.assertEqual(D(supplier["paid"]), D(supplier["cost"]))
        self.assertEqual(D(supplier["remaining"]), D("0.00"))
        # ملخّص المورد في التفصيل والقائمة (نسخة SQL) يقرآن الأساس كذلك.
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        self.assertEqual(D(detail["remaining_balance"]), D("0.00"))
        listed = self.client.get(
            "/api/logistics/purchase-invoices/", {"page_size": 50}, **self._auth()).json()
        row = next(r for r in listed.get("results", listed) if r["id"] == inv.pk)
        self.assertEqual(D(row["remaining_balance"]), D("0.00"))
