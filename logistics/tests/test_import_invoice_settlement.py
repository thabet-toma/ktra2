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

        # ترحيلٌ قديم (قبل 51b12571): المورد دائنٌ بالإجمالي المحمَّل كلّه (بلا الضريبة —
        # دائنُها «ضريبة الاستيراد المستحقة»).
        with mock.patch(
            "logistics.accruals.import_invoice_accrual_credits", return_value=[],
        ):
            inv = self._post(inv)
        old_supplier = inv.journal.lines.filter(account=self.ap).aggregate(
            c=Sum("credit"))["c"]
        self.assertEqual(old_supplier, inv.grand_total - tax)

        shares = import_invoice_cost_shares(inv)
        res = self._recalculate(auto_repost=True)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["reconciliation"]["reposted"], 1)

        inv.refresh_from_db()
        lines = list(inv.journal.lines.all())
        self.assertEqual(
            sum((l.debit for l in lines), D("0")), sum((l.credit for l in lines), D("0")))
        new_supplier = sum((l.credit for l in lines if l.account_id == self.ap.id), D("0"))
        # نقصت ذمّة المورد بحصص الشحن والتخليص والنقل، وبقيت له البضاعة وحدها.
        self.assertEqual(
            old_supplier - new_supplier,
            shares["freight"] + shares["clearance"] + shares["local"])
        self.assertEqual(new_supplier, D("3500.00"))
        # قرار المالك (2026-10-07): ضريبة الفاتورة الدولية تكلفة بضاعة — لا سطر 1105.
        self.assertFalse(any(l.account.code == "1105" for l in lines))

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

    # ── مصدرٌ واحد للعرض: كل ما تقرؤه الواجهة من التكاليف الأربع ────────────
    # INV-0022 على الإنتاج: مسودةٌ دولية دائنوها الأربعة مسدَّدون لأطرافٍ مختلفة،
    # والشاشة تقول «مدفوعة بالكامل» فوق و«المتبقي 7,040.53» تحت — لأن ملخّص
    # المورد يقيس المسودة بإجماليها المحمَّل مقابل دفعات المورد وحده.
    def _list_ids(self, **params):
        res = self.client.get(
            "/api/logistics/purchase-invoices/", {"page_size": 50, **params}, **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        return {r["id"]: r for r in data.get("results", data)}

    def _draft_with_past_due(self):
        invoices = self._release_and_import()
        for deal in self.deals:
            self._pay_deal(deal)
        inv = invoices[0]
        PurchaseInvoice.objects.filter(pk=inv.pk).update(due_date="2026-08-01")
        return inv

    def _assert_supplier_rows_are_supplier_only(self, detail):
        # «رصيد المورد قبل/بعد» جانبُ المورد وحده: حصّته مسدَّدة فلا أثر —
        # لا شحن ولا تخليص ولا نقل مستحقّاً لغيره.
        self.assertEqual(
            D(detail["supplier_balance_after_invoice"]),
            D(detail["supplier_balance_before_invoice"]))

    def test_draft_paid_to_all_four_creditors_reads_paid_everywhere(self):
        inv = self._draft_with_past_due()
        self._pay_freight_and_local()
        self._pay_clearance("690")

        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        ip = detail["import_payment"]
        self.assertEqual((ip["payment_status"], D(ip["remaining_balance"])), ("paid", D("0.00")))
        self.assertFalse(detail["is_overdue"])
        self._assert_supplier_rows_are_supplier_only(detail)

        row = self._list_ids()[inv.pk]
        self.assertEqual(
            (row["import_payment"]["payment_status"], D(row["import_payment"]["remaining_balance"])),
            ("paid", D("0.00")))
        self.assertFalse(row["is_overdue"])
        # فلتر القائمة يقول ما تقوله شارتها.
        self.assertIn(inv.pk, self._list_ids(payment_status="paid"))
        self.assertNotIn(inv.pk, self._list_ids(payment_status="partially_paid"))
        self.assertNotIn(inv.pk, self._list_ids(payment_status="overdue"))

    def test_draft_with_unpaid_freight_owes_exactly_the_freight_share(self):
        from logistics.models import LocalShipmentPayment
        inv = self._draft_with_past_due()
        LocalShipmentPayment.objects.create(
            tenant=self.tenant, local_shipment=self.local, amount=D("450"),
            currency=self.ils, exchange_rate=D("1"), payment_date="2026-07-07",
            cash_box_external_id="box", is_posted=True)
        self._pay_clearance("690")

        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        ip = detail["import_payment"]
        freight = D(ip["components"]["freight"]["cost"])
        self.assertGreater(freight, 0)
        self.assertEqual(ip["payment_status"], "partially_paid")
        self.assertEqual(D(ip["remaining_balance"]), freight)
        self.assertTrue(detail["is_overdue"])
        self._assert_supplier_rows_are_supplier_only(detail)

        row = self._list_ids()[inv.pk]
        self.assertEqual(D(row["import_payment"]["remaining_balance"]), freight)
        self.assertTrue(row["is_overdue"])
        self.assertIn(inv.pk, self._list_ids(payment_status="partially_paid"))
        self.assertNotIn(inv.pk, self._list_ids(payment_status="paid"))
        self.assertIn(inv.pk, self._list_ids(payment_status="overdue"))

    # ── أساس دفع المورد على المسودة الدولية = ما سيدائنه به ترحيلُها ─────────
    # الملخّص يقيس المسودة بإجماليها المحمَّل (لا قيد بعد)، فكانت لوحة الدفع
    # وسقف النيّة يقبلان حصص الوكيل والمخلّص والناقل دفعاً للمورد.
    def _supplier_payable(self, inv):
        res = self.client.get(f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        return D(res.json()["supplier_payable_total"])

    def _ap_credit(self, inv):
        return inv.journal.lines.filter(account=self.ap).aggregate(c=Sum("credit"))["c"]

    def test_draft_supplier_payable_is_what_posting_credits_the_supplier(self):
        inv = self._release_and_import()[0]
        draft = self._supplier_payable(inv)
        self.assertLess(draft, inv.grand_total)
        self.assertEqual(draft, self._ap_credit(self._post(inv)))
        # بعد الترحيل: الحقل نفسه = ما دائنه به القيد.
        self.assertEqual(self._supplier_payable(inv), draft)

    def test_draft_supplier_payable_keeps_unaccrued_component_on_supplier(self):
        # نقلٌ بلا استحقاق مرحّل يبقى على المورد عند الترحيل — والأساس يتبعه.
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
        self.assertEqual(res.status_code, 201, res.content)
        inv = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deals[0])
        draft = self._supplier_payable(inv)
        self.assertGreater(draft, D("3500.00"))  # البضاعة + حصّة النقل
        self.assertEqual(draft, self._ap_credit(self._post(inv)))

    def test_attached_cheques_capped_at_supplier_share_and_settle_on_post(self):
        inv = self._release_and_import()[0]
        share = self._supplier_payable(inv)
        url = f"/api/logistics/purchase-invoices/{inv.pk}/attach-payment/"

        def cheque(amount):
            return {"cash_amount": "0", "cheques": [{
                "cheque_number": "SUP-1", "amount": str(amount), "due_date": "2026-09-01"}]}

        over = self.client.post(url, cheque(share + D("0.01")), format="json", **self._auth())
        self.assertEqual(over.status_code, 400, over.content)
        self.assertIn("المورد", over.json()["error"])

        ok = self.client.post(url, cheque(share), format="json", **self._auth())
        self.assertEqual(ok.status_code, 200, ok.content)
        inv = self._post(PurchaseInvoice.objects.get(pk=inv.pk))
        detail = self.client.get(f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        self.assertEqual(D(detail["remaining_balance"]), D("0.00"))

    # ── الطرف الدائن للرسم: يُدائَن لجهته لا للمورد ─────────────────────────
    def _ktra(self):
        return Partner.objects.create(
            tenant=self.tenant, name="كترا", partner_type="Supplier",
            linked_account=Account.objects.create(
                tenant=self.tenant, code="AP-KTRA", name="ذمم كترا",
                account_type="Liability", is_active=True))

    def _party_fee(self, inv, ktra, amount="420"):
        return inv.fees.create(
            tenant=self.tenant, description="تكاليف كترا", amount=D(amount),
            expense_account=Account.objects.get(tenant=self.tenant, code="5307"),
            capitalize_to_inventory=False, credit_partner=ktra)

    def test_vat_base_fee_changes_only_tax_base(self):
        invoices = self._release_and_import()
        PurchaseInvoice.objects.filter(pk__in=[i.pk for i in invoices]).update(
            tax_rate=D("16"), tax_type="percentage")
        expense = Account.objects.get(tenant=self.tenant, code="5307")
        inv = invoices[0]
        inv.fees.create(tenant=self.tenant, description="رسم خارج الأساس", amount=D("50"),
                        expense_account=expense, capitalize_to_inventory=False)
        self.assertEqual(self._recalculate().status_code, 200)
        inv.refresh_from_db()
        subtotal, tax_without = inv.subtotal, inv.tax_amount
        self.assertEqual(tax_without, (subtotal * D("0.16")).quantize(Q2))

        inv.fees.create(tenant=self.tenant, description="رسم ضمن الأساس", amount=D("100"),
                        expense_account=expense, capitalize_to_inventory=False,
                        is_taxable=True)
        self.assertEqual(self._recalculate().status_code, 200)
        inv.refresh_from_db()
        # الضريبة وحدها ارتفعت بضريبة الرسم؛ البضاعة والرسوم كما هي.
        self.assertEqual(inv.subtotal, subtotal)
        self.assertEqual(inv.tax_amount, ((subtotal + D("100")) * D("0.16")).quantize(Q2))
        self.assertEqual(inv.tax_amount - tax_without, D("16.00"))
        self.assertEqual(
            sorted(f.amount for f in inv.fees.all()), [D("50.00"), D("100.00")])
        # الشاشة (القراءة الحيّة للمسودة) تقول الرقم نفسه.
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        self.assertEqual(D(detail["tax_amount"]), inv.tax_amount)

    def test_party_fee_is_cost_not_supplier_debt(self):
        ktra = self._ktra()
        inv = self._release_and_import()[0]
        before = self._breakdown(inv)
        supplier_payable = self._supplier_payable(inv)
        self._party_fee(inv, ktra)
        after = self._breakdown(inv)
        # حصّة المورد كما هي؛ والرسم — ولو بخيار «لا يُرسمَل» محفوظاً — تكلفةٌ في الإجمالي.
        self.assertEqual(after["components"]["supplier"], before["components"]["supplier"])
        self.assertEqual(D(after["payable_total"]), D(before["payable_total"]) + D("420"))
        self.assertEqual(D(after["remaining_balance"]), D(before["remaining_balance"]) + D("420"))
        self.assertEqual(self._supplier_payable(inv), supplier_payable)

        inv = self._post(PurchaseInvoice.objects.get(pk=inv.pk))
        self.assertEqual(self._ap_credit(inv), supplier_payable)
        party = inv.journal.lines.get(account__code="AP-KTRA")
        self.assertEqual((party.credit, party.partner_id), (D("420.00"), ktra.pk))
        posted = self._breakdown(inv)
        self.assertEqual(D(posted["components"]["supplier"]["cost"]), supplier_payable)

    def test_unpost_repost_and_recalc_repost_keep_credit_party(self):
        ktra = self._ktra()
        inv = self._release_and_import()[0]
        fee = self._party_fee(inv, ktra)

        def party_line(invoice):
            invoice.refresh_from_db()
            line = invoice.journal.lines.get(account__code="AP-KTRA")
            return line.credit, line.partner_id

        # ترحيلٌ قديم الشكل (قبل 51b12571) يجعل «أعد الاحتساب والترحيل» يعيد القيد فعلاً.
        with mock.patch(
            "logistics.accruals.import_invoice_accrual_credits", return_value=[],
        ):
            inv = self._post(inv)
        self.assertEqual(party_line(inv), (D("420.00"), ktra.pk))

        res = self._recalculate(auto_repost=True)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["reconciliation"]["reposted"], 1)
        self.assertEqual(party_line(inv), (D("420.00"), ktra.pk))
        fee.refresh_from_db()
        self.assertEqual(fee.credit_partner_id, ktra.pk)

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/", {}, format="json",
            **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        inv = self._post(PurchaseInvoice.objects.get(pk=inv.pk))
        self.assertEqual(party_line(inv), (D("420.00"), ktra.pk))

    # ── عمولة التحويل في التكلفة تلقائياً: حيث قيّدها قيد الدفعة ─────────────
    def _post_deal_payment_with_commission(self, deal, transfer_usd):
        payment = LogisticsPayment.objects.get(deal=deal)
        LogisticsPayment.objects.filter(pk=payment.pk).update(transfer_cost=D(transfer_usd))
        cash = Account.objects.get(tenant=self.tenant, code="1101")
        res = self.client.post(
            f"/api/logistics/deals/{deal.pk}/post_payment/{payment.pk}/",
            {"bank_account_id": cash.pk}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)

    def _bank_charges(self):
        return Account.objects.get(tenant=self.tenant, name="مصاريف بنكية وعمولات")

    def _net_debit(self, account):
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account=account, journal__is_posted=True,
        ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
        return (agg["d"] or D("0")) - (agg["c"] or D("0"))

    def test_posting_capitalizes_booked_transfer_commission(self):
        self._post_deal_payment_with_commission(self.deals[0], "10")  # 10$ × 3.5
        bank = self._bank_charges()
        self.assertEqual(self._net_debit(bank), D("35.00"))
        inv = self._release_and_import()[0]
        PurchaseInvoice.objects.filter(pk=inv.pk).update(tax_rate=D("16"), tax_type="percentage")
        self.assertEqual(self._recalculate().status_code, 200)
        inv = PurchaseInvoice.objects.get(pk=inv.pk)
        supplier_share = self._supplier_payable(inv)

        inv = self._post(inv)
        lines = list(inv.journal.lines.all())
        self.assertIn((bank.id, D("35.00")), [(l.account_id, l.credit) for l in lines])
        self.assertEqual(
            sum((l.debit for l in lines), D("0")), sum((l.credit for l in lines), D("0")))
        # المصروف البنكي صار تكلفة: «مصاريف بنكية وعمولات» عاد صفراً، والمورد لا يتأثّر.
        self.assertEqual(self._net_debit(bank), D("0.00"))
        self.assertEqual(self._ap_credit(inv), supplier_share)
        # خارج أساس الضريبة.
        self.assertEqual(inv.tax_amount, (inv.subtotal * D("0.16")).quantize(Q2))
        # وفي تفصيل التكاليف سطراً.
        payment = self._breakdown(inv)
        rows = {r["key"]: r for r in payment["cost_rows"]}
        self.assertEqual(D(rows["commission"]["cost"]), D("35.00"))
        self.assertEqual(D(rows["commission"]["remaining"]), D("0.00"))
        self.assertEqual(
            D(payment["payable_total"]), sum((D(r["cost"]) for r in rows.values()), D("0")))
        # التكلفة النهائية للوحدة تحمل العمولة والضريبة: مجموعها = كل مدين القيد = إجمالي التكلفة.
        unit_total = sum((D(u["unit_cost"]) * D(u["quantity"]) for u in payment["unit_costs"]), D("0"))
        self.assertEqual(unit_total.quantize(Q2), sum((l.debit for l in lines), D("0")))
        self.assertEqual(unit_total.quantize(Q2), D(payment["payable_total"]))

    def test_recalc_repost_adds_commission_to_old_posting_once(self):
        from logistics.landed_cost import posted_invoices_cost_drift

        self._post_deal_payment_with_commission(self.deals[0], "10")
        inv = self._release_and_import()[0]
        # ترحيلٌ قبل هذا التعديل: بلا عمولة في التكلفة.
        with mock.patch(
            "logistics.payment_posting.import_invoice_booked_commission",
            return_value=(D("0"), None),
        ):
            inv = self._post(inv)
        bank = self._bank_charges()
        self.assertFalse(inv.journal.lines.filter(account=bank).exists())
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertIn(inv.pk, [r["id"] for r in drift["stale_posted_invoices"]])

        for _ in range(2):
            res = self._recalculate(auto_repost=True)
            self.assertEqual(res.status_code, 200, res.content)
            inv.refresh_from_db()
            credit = inv.journal.lines.filter(account=bank).aggregate(c=Sum("credit"))["c"]
            self.assertEqual(credit, D("35.00"))
            self.assertEqual(self._net_debit(bank), D("0.00"))
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertEqual(drift["stale_posted_invoices"], [])

    def test_archive_deal_commission_is_not_capitalized(self):
        from logistics.payment_posting import import_invoice_booked_commission

        self._post_deal_payment_with_commission(self.deals[0], "10")
        inv = self._release_and_import()[0]
        self.assertEqual(import_invoice_booked_commission(inv)[0], D("35.00"))
        with mock.patch(
            "logistics.payment_posting.live_archive_deal_journals",
            return_value={inv.deal_id: [1]},
        ):
            self.assertEqual(import_invoice_booked_commission(inv)[0], D("0"))

    def test_total_cost_is_one_number_box_rows_journal_and_paid(self):
        """INV-0022/0023: المربّع (`payable_total`) كان بلا العمولة والتفصيل والقيد بها.
        رقمٌ واحد: مجموع `cost_rows` = مدين البضاعة في القيد = ما تعرضه القائمة،
        والعمولة مدفوعةٌ يوم الدفع فالمسدَّدة كلّها «مدفوعة» لا متبقّي فيها."""
        self._post_deal_payment_with_commission(self.deals[0], "10")
        self._pay_deal(self.deals[1])
        invoices = [self._post(inv) for inv in self._release_and_import()]
        inv = invoices[0]
        self.assertEqual(inv.tax_amount, D("0"))
        self._pay_freight_and_local()
        self._pay_clearance("690")

        payment = self._breakdown(inv)
        rows = {r["key"]: r for r in payment["cost_rows"]}
        self.assertEqual(D(rows["commission"]["cost"]), D("35.00"))
        box = D(payment["payable_total"])
        self.assertEqual(box, sum((D(r["cost"]) for r in rows.values()), D("0")))
        # مدين البضاعة (المخزون/2110) في القيد — بلا ضريبة ولا رسوم هنا = كل المدين.
        goods_debit = sum((l.debit for l in inv.journal.lines.all()), D("0"))
        self.assertEqual(box, goods_debit)
        self.assertEqual(D(payment["amount_paid"]), box)
        self.assertEqual(D(payment["remaining_balance"]), D("0.00"))
        self.assertEqual(payment["payment_status"], "paid")
        # القائمة تقرأ الرقم نفسه.
        listed = self.client.get(
            "/api/logistics/purchase-invoices/", {"page_size": 50}, **self._auth()).json()
        row = next(r for r in listed.get("results", listed) if r["id"] == inv.pk)
        self.assertEqual(D(row["import_payment"]["payable_total"]), box)
        self.assertEqual(row["import_payment"]["payment_status"], "paid")

    # ── تكلفة الوحدة في المخزون = حصّة البند من مدين البضاعة المرحّل (لا السعر المستورد) ──
    def _post_and_receive(self, inv):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {"receive_on_post": True}, format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        inv.refresh_from_db()
        return inv

    def _grn_inventory_debit(self, inv):
        from accounting.models import JournalHeader
        grn = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_GRN", reference_id=inv.pk)
        return sum((l.debit for l in grn.lines.all()), D("0"))

    def _receipt_value(self, inv):
        from inventory.models import StockMovement
        moves = StockMovement.objects.filter(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=inv.pk,
            movement_type="IN")
        return sum((m.quantity * m.unit_cost for m in moves), D("0")).quantize(Q2)

    def _stock_value_at_avg(self, inv):
        """قيمة المخزون كما تقرؤها التقارير في النموذج الدوري: الكمية × avg_cost."""
        total = D("0")
        for it in inv.items.select_related("product"):
            it.product.refresh_from_db()
            total += it.quantity * it.product.avg_cost
        return total.quantize(Q2)

    def test_commission_enters_avg_cost_and_receipt_matches_grn(self):
        self._post_deal_payment_with_commission(self.deals[0], "10")  # 35 ₪
        inv = self._post_and_receive(self._release_and_import()[0])
        grn = self._grn_inventory_debit(inv)
        landed = sum((it.landed_line_total_ils for it in inv.items.all()), D("0"))
        self.assertEqual(grn, (landed + D("35")).quantize(Q2))
        # الثابت: Σ(كمية × تكلفة وحدة الحركة) = مدين المخزون في قيد الاستلام بالقرش.
        self.assertEqual(self._receipt_value(inv), grn)
        # والمتوسط (النموذج الدوري — الافتراضي) يحمل العمولة: كان السعرَ المستورد وحده.
        self.assertEqual(self._stock_value_at_avg(inv), grn)

    def test_every_import_fee_enters_unit_cost(self):
        """قرار المالك: كل رسمٍ دوليّ تكلفة — والخيار المحفوظ «لا يُرسمَل» (رسمٌ قديم) لا يغيّره."""
        misc = Account.objects.get(tenant=self.tenant, code="5307")
        inv = self._release_and_import()[0]
        inv.fees.create(tenant=self.tenant, description="تكاليف كترا", amount=D("100"),
                        expense_account=misc, capitalize_to_inventory=True)
        old = inv.fees.create(tenant=self.tenant, description="رسم إداري", amount=D("50"),
                              expense_account=misc, capitalize_to_inventory=False)
        inv = self._post_and_receive(inv)
        landed = sum((it.landed_line_total_ils for it in inv.items.all()), D("0"))
        grn = self._grn_inventory_debit(inv)
        self.assertEqual(grn, (landed + D("150")).quantize(Q2))
        old.refresh_from_db()
        self.assertTrue(old.capitalize_to_inventory)  # الترحيل يثبّته
        self.assertFalse(inv.journal.lines.filter(account=misc, debit__gt=0).exists())
        self.assertEqual(self._receipt_value(inv), grn)
        self.assertEqual(self._stock_value_at_avg(inv), grn)

    def test_reconcile_command_fixes_avg_without_touching_inventory(self):
        from io import StringIO

        from django.core.management import call_command
        from inventory.models import Product

        self._post_deal_payment_with_commission(self.deals[0], "10")
        inv = self._post_and_receive(self._release_and_import()[0])
        grn = self._grn_inventory_debit(inv)
        item = inv.items.select_related("product").get()
        # حال الإنتاج قبل الإصلاح: المتوسط = السعر المستورد بلا العمولة.
        Product.objects.filter(pk=item.product_id).update(avg_cost=item.landed_unit_price_ils)
        inventory_lines = JournalLine.objects.filter(
            tenant=self.tenant, account__code="1104").count()

        out = StringIO()
        call_command("reconcile_import_unit_costs", "--tenant", str(self.tenant.pk), stdout=out)
        report = out.getvalue()
        self.assertIn(inv.invoice_number, report)
        self.assertIn("35.00", report)
        item.product.refresh_from_db()
        self.assertEqual(item.product.avg_cost, item.landed_unit_price_ils)  # قراءةٌ فقط

        call_command("reconcile_import_unit_costs", "--tenant", str(self.tenant.pk), "--apply",
                     stdout=StringIO())
        self.assertEqual(self._stock_value_at_avg(inv), grn)
        # لا مبيع: لا قيد — 1104 كما هو.
        self.assertEqual(JournalLine.objects.filter(
            tenant=self.tenant, account__code="1104").count(), inventory_lines)

    def test_free_line_does_not_drop_invoice_cost_from_avg(self):
        """بندٌ مجاني (سعره 0 — قطع غيار هدية) كان يُسقط الفاتورة كلّها من `posted_goods_line_costs`
        فيُبنى المتوسط من السعر المستورد بلا العمولة (INV-0024: الإنفيرتر 704.65 بدل 901.43)،
        ويتخطّاها `reconcile_import_unit_costs`. المجاني حصّته 0 ويُخفّض المتوسط بكميته وحدها."""
        from io import StringIO

        from django.core.management import call_command
        from inventory.services import product_cost_breakdown

        deal = self.deals[0]
        paid = deal.items.get()
        gift = Product.objects.create(
            tenant=self.tenant, sku="SET-GIFT", name_ar="قطعة هدية",
            quantity_on_hand=D("0"), avg_cost=D("0"))
        LogisticsDealItem.objects.create(deal=deal, product=paid.product, quantity=D("2"), unit_price=D("0"))
        LogisticsDealItem.objects.create(deal=deal, product=gift, quantity=D("3"), unit_price=D("0"))
        self._post_deal_payment_with_commission(deal, "10")  # 35 ₪
        inv = self._post_and_receive(self._release_and_import()[0])
        self.assertEqual(inv.items.filter(landed_line_total_ils=0).count(), 2)
        grn = self._grn_inventory_debit(inv)
        self.assertEqual(self._receipt_value(inv), grn)

        # المتوسط = مدين البضاعة ÷ الكمية كلّها (10 مدفوعة + 2 مجانية)، لا السعر المستورد.
        breakdown = product_cost_breakdown(tenant_id=self.tenant.pk, product_id=paid.product_id)
        self.assertEqual(D(breakdown["total_purchased_qty"]), D("12"))
        self.assertLessEqual(abs(D(breakdown["average_cost"]) * 12 - grn), D("0.01"))
        self.assertLessEqual(abs(self._stock_value_at_avg(inv) - grn), D("0.01"))

        # والأمر لا يتخطّاها: حال الإنتاج (المتوسط بلا العمولة) يُكشف ويُصلَح.
        Product.objects.filter(pk=paid.product_id).update(avg_cost=D("1"))
        out = StringIO()
        call_command("reconcile_import_unit_costs", "--tenant", str(self.tenant.pk), stdout=out)
        self.assertIn(inv.invoice_number, out.getvalue())
        self.assertIn("35.00", out.getvalue())
        call_command("reconcile_import_unit_costs", "--tenant", str(self.tenant.pk), "--apply",
                     stdout=StringIO())
        self.assertLessEqual(abs(self._stock_value_at_avg(inv) - grn), D("0.01"))

    def test_reconcile_command_leaves_fifo_sales_alone(self):
        """المبيع كُلِّف من طبقة FIFO (بالعمولة) لا من avg_cost — فلا فرق مبيعٍ ولا قيد."""
        from io import StringIO

        from django.core.management import call_command
        from accounting.models import JournalHeader
        from inventory.models import Product
        from inventory.services import record_stock_movement

        self._post_deal_payment_with_commission(self.deals[0], "10")
        inv = self._post_and_receive(self._release_and_import()[0])
        grn = self._grn_inventory_debit(inv)
        item = inv.items.select_related("product").get()
        Product.objects.filter(pk=item.product_id).update(avg_cost=item.landed_unit_price_ils)
        product = Product.objects.get(pk=item.product_id)
        sale = record_stock_movement(
            product=product, movement_type="OUT", quantity=D("2"),
            reference_type="SALE", reference_id=999, movement_date="2026-07-20",
            tenant=self.tenant)
        # كلفة البيع = خُمسا قيمة الاستلام (10 وحدات) — تحمل العمولة.
        self.assertEqual(sale.total_cost, (grn * D("2") / D("10")).quantize(Q2))
        journals = JournalHeader.objects.filter(tenant=self.tenant).count()

        out = StringIO()
        call_command("reconcile_import_unit_costs", "--tenant", str(self.tenant.pk), "--apply",
                     stdout=out)
        self.assertNotIn("حركة صرف", out.getvalue())
        self.assertEqual(JournalHeader.objects.filter(tenant=self.tenant).count(), journals)
        sale.refresh_from_db()
        self.assertEqual(sale.total_cost, (grn * D("2") / D("10")).quantize(Q2))
        product.refresh_from_db()
        self.assertEqual((product.avg_cost * D("10")).quantize(Q2), grn)

    # ── قرار المالك (2026-10-07): كل ما في الفاتورة الدولية تكلفة — رقمٌ واحد ──
    def _gr_ir_debit(self, inv):
        from logistics.services import _resolve_gr_ir_account
        clearing = _resolve_gr_ir_account(self.tenant)
        return sum((l.debit for l in inv.journal.lines.filter(account=clearing)), D("0"))

    def test_tax_fee_and_commission_all_cost_one_number_everywhere(self):
        """ض.ق.م 16% + رسمٌ بعد الضريبة + عمولة (INV-0023): Σ(كمية × unit_cost) = إجمالي التكلفة
        = مدين الوسيط (2110) في قيد الفاتورة = مدين المخزون في قيد الاستلام، و1105 لا يتحرّك."""
        self._post_deal_payment_with_commission(self.deals[0], "10")  # 35 ₪
        inv = self._release_and_import()[0]
        PurchaseInvoice.objects.filter(pk=inv.pk).update(tax_rate=D("16"), tax_type="percentage")
        self.assertEqual(self._recalculate().status_code, 200)
        inv = PurchaseInvoice.objects.get(pk=inv.pk)
        self.assertGreater(inv.tax_amount, 0)
        # رسم كترا: 10% من (الأساس + الضريبة) — يُحفظ من الشاشة بلا خيار «يُضاف للتكلفة».
        res = self.client.patch(
            f"/api/logistics/purchase-invoices/{inv.pk}/",
            {"fees": [{"description": "تكاليف كترا", "amount": "0",
                       "calculation_type": "percentage", "calculation_value": "10",
                       "percentage_basis": "after_main_vat",
                       "expense_account": Account.objects.get(tenant=self.tenant, code="5307").id}]},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        fee = inv.fees.get()
        self.assertTrue(fee.capitalize_to_inventory)
        self.assertGreater(fee.amount, 0)

        draft = self._breakdown(inv)
        payable = D(draft["payable_total"])
        draft_units = sum((D(u["unit_cost"]) * D(u["quantity"]) for u in draft["unit_costs"]), D("0"))
        self.assertEqual(draft_units.quantize(Q2), payable)

        vat_before = self._net("1105")
        inv = self._post_and_receive(PurchaseInvoice.objects.get(pk=inv.pk))
        self.assertEqual(self._net("1105"), vat_before)  # لا مدخلات من الفاتورة الدولية
        self.assertEqual(self._gr_ir_debit(inv), payable)
        self.assertEqual(self._grn_inventory_debit(inv), payable)
        self.assertEqual(self._receipt_value(inv), payable)
        self.assertEqual(self._stock_value_at_avg(inv), payable)
        posted = self._breakdown(inv)
        self.assertEqual(D(posted["payable_total"]), payable)
        units = sum((D(u["unit_cost"]) * D(u["quantity"]) for u in posted["unit_costs"]), D("0"))
        self.assertEqual(units.quantize(Q2), payable)

    def test_old_posting_with_input_vat_is_stale_and_repost_capitalizes_it(self):
        """INV-0022: رُحّلت قبل القرار (الضريبة على 1105، الرسم مصروفاً) ⇒ «متأخّرة»، والأمر
        يعرضها؛ و«أعد الاحتساب والترحيل» يرحّلها تكلفةً."""
        from io import StringIO
        from django.core.management import call_command
        from logistics.landed_cost import posted_invoices_cost_drift

        misc = Account.objects.get(tenant=self.tenant, code="5307")
        inv = self._release_and_import()[0]
        PurchaseInvoice.objects.filter(pk=inv.pk).update(tax_rate=D("16"), tax_type="percentage")
        self.assertEqual(self._recalculate().status_code, 200)
        fee = PurchaseInvoice.objects.get(pk=inv.pk).fees.create(
            tenant=self.tenant, description="تكاليف كترا", amount=D("100"),
            expense_account=misc, capitalize_to_inventory=False)
        # الترحيل القديم: بلا القاعدة.
        with mock.patch("logistics.services.import_invoice_capitalizes_all", return_value=False), \
                mock.patch("logistics.services.capitalize_import_fees"):
            inv = self._post(PurchaseInvoice.objects.get(pk=inv.pk))
        self.assertTrue(inv.journal.lines.filter(account__code="1105", debit__gt=0).exists())
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertIn(inv.pk, [r["id"] for r in drift["stale_posted_invoices"]])
        out = StringIO()
        call_command("report_import_off_cost_postings", "--tenant", str(self.tenant.pk), stdout=out)
        self.assertIn(inv.invoice_number, out.getvalue())
        self.assertIn("تكاليف كترا", out.getvalue())

        res = self._recalculate(auto_repost=True)
        self.assertEqual(res.status_code, 200, res.content)
        inv.refresh_from_db()
        fee.refresh_from_db()
        self.assertTrue(fee.capitalize_to_inventory)
        self.assertFalse(inv.journal.lines.filter(account__code="1105").exists())
        self.assertFalse(inv.journal.lines.filter(account=misc, debit__gt=0).exists())
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertEqual(drift["stale_posted_invoices"], [])
        out = StringIO()
        call_command("report_import_off_cost_postings", "--tenant", str(self.tenant.pk), stdout=out)
        self.assertNotIn(inv.invoice_number, out.getvalue())

    # ── خصم الصفقة داخل مبلغها ودفعاتها — لا يُخصم ثانيةً من الفاتورة (INV-0024) ──
    def test_deal_discount_is_inside_payments_not_deducted_again(self):
        """D-0107: بنود 14,000$ − خصم 1,200$ = إجمالي الصفقة = الدفعات. كان البناء ينسخ
        خصم الصفقة (دولاراً) إلى فاتورةٍ بالشيكل بضاعتُها من الدفعات ⇒ يُخصم مرّتين."""
        deal = self.deals[0]
        # بنود 1,200$ − خصم 200$ = 1,000$ = الدفعة (3,500 ₪).
        LogisticsDeal.objects.filter(pk=deal.pk).update(discount_amount=D("200"))
        LogisticsDealItem.objects.filter(deal=deal).update(unit_price=D("120"))
        inv = self._release_and_import()[0]
        self.assertEqual(inv.discount_amount, D("0"))
        self.assertEqual(self._supplier_payable(inv), D("3500.00"))

        # فاتورةٌ بُنيت قبل الإصلاح: إعادة الحساب تصفّر خصمها لا تُبقيه.
        PurchaseInvoice.objects.filter(pk=inv.pk).update(discount_amount=D("200"))
        self.assertEqual(self._recalculate().status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.discount_amount, D("0"))

        payment = self._breakdown(inv)
        payable = D(payment["payable_total"])
        units = sum((D(u["unit_cost"]) * D(u["quantity"]) for u in payment["unit_costs"]), D("0"))
        self.assertEqual(units.quantize(Q2), payable)
        inv = self._post(inv)
        self.assertEqual(self._ap_credit(inv), D("3500.00"))  # الدفعات × السعر
        self.assertEqual(self._gr_ir_debit(inv), payable)

    def test_discount_command_zeroes_drafts_and_lists_posted(self):
        from io import StringIO
        from django.core.management import call_command
        from logistics.landed_cost import posted_invoices_cost_drift

        invoices = self._release_and_import()
        draft = invoices[0]
        PurchaseInvoice.objects.filter(pk=draft.pk).update(discount_amount=D("200"))
        posted = self._post(invoices[1])
        PurchaseInvoice.objects.filter(pk=posted.pk).update(discount_amount=D("150"))
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertIn(posted.pk, [r["id"] for r in drift["stale_posted_invoices"]])

        out = StringIO()
        call_command("fix_import_invoice_discounts", "--tenant", str(self.tenant.pk), stdout=out)
        report = out.getvalue()
        self.assertIn(draft.invoice_number, report)
        self.assertIn(posted.invoice_number, report)
        draft.refresh_from_db()
        self.assertEqual(draft.discount_amount, D("200"))  # قراءةٌ فقط

        call_command("fix_import_invoice_discounts", "--tenant", str(self.tenant.pk), "--apply",
                     stdout=StringIO())
        draft.refresh_from_db()
        posted.refresh_from_db()
        self.assertEqual(draft.discount_amount, D("0"))
        self.assertEqual(posted.discount_amount, D("150"))  # المرحّلة من الشاشة

        res = self._recalculate(auto_repost=True)
        self.assertEqual(res.status_code, 200, res.content)
        posted.refresh_from_db()
        self.assertEqual(posted.discount_amount, D("0"))
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertEqual(drift["stale_posted_invoices"], [])

    # ── ضريبة الفاتورة الدولية دائنُها «ضريبة الاستيراد المستحقة» لا المورد (قرار المالك) ──
    def _taxed_invoice(self):
        inv = self._release_and_import()[0]
        PurchaseInvoice.objects.filter(pk=inv.pk).update(tax_rate=D("16"), tax_type="percentage")
        self.assertEqual(self._recalculate().status_code, 200)
        inv = PurchaseInvoice.objects.get(pk=inv.pk)
        self.assertGreater(inv.tax_amount, 0)
        return inv

    def _tax_payable_account(self):
        return Account.objects.get(tenant=self.tenant, name="ضريبة الاستيراد المستحقة")

    def test_import_tax_credits_tax_payable_not_supplier(self):
        """INV-0023: المورد Beijing دائنٌ 6,496.20 بضاعة + 1,912.40 ض.ق.م — والمورد الأجنبي لا
        يقبض الضريبة. الدائن حساب «ضريبة الاستيراد المستحقة»، والمدين المخزون/2110 كما هو."""
        inv = self._taxed_invoice()
        tax = inv.tax_amount
        self.assertEqual(self._supplier_payable(inv), D("3500.00"))  # البضاعة وحدها
        draft = self._breakdown(inv)
        self.assertEqual(D(draft["components"]["supplier"]["cost"]), D("3500.00"))
        tax_row = next(r for r in draft["cost_rows"] if r["key"] == "tax")
        self.assertEqual((D(tax_row["cost"]), D(tax_row["paid"])), (tax, D("0.00")))
        payable = D(draft["payable_total"])

        inv = self._post_and_receive(inv)
        account = self._tax_payable_account()
        self.assertEqual(account.account_type, "Liability")
        lines = list(inv.journal.lines.all())
        self.assertEqual(self._ap_credit(inv), D("3500.00"))
        self.assertEqual(sum((l.credit for l in lines if l.account_id == account.id), D("0")), tax)
        self.assertEqual(
            sum((l.debit for l in lines), D("0")), sum((l.credit for l in lines), D("0")))
        self.assertEqual(self._gr_ir_debit(inv), payable)
        self.assertEqual(self._grn_inventory_debit(inv), payable)
        self.assertEqual(self._supplier_payable(inv), D("3500.00"))
        posted = self._breakdown(inv)
        self.assertEqual(D(posted["payable_total"]), payable)
        units = sum((D(u["unit_cost"]) * D(u["quantity"]) for u in posted["unit_costs"]), D("0"))
        self.assertEqual(units.quantize(Q2), payable)

        # مدفوع الضريبة من حسابها: دفعات المورد لا تسدّدها، وسند صرفٍ عليه يسدّدها.
        tax_row = next(r for r in posted["cost_rows"] if r["key"] == "tax")
        self.assertEqual(D(tax_row["paid"]), D("0.00"))
        from accounting.services import post_journal
        post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-07-10",
            reference_type="MANUAL", reference_id=None, description="سداد ضريبة الاستيراد",
            lines_data=[
                {"account": account.id, "partner": None, "debit": tax, "credit": D("0"),
                 "description": "ضريبة"},
                {"account": Account.objects.get(tenant=self.tenant, code="1101").id,
                 "partner": None, "debit": D("0"), "credit": tax, "description": "ضريبة"},
            ],
        )
        tax_row = next(r for r in self._breakdown(inv)["cost_rows"] if r["key"] == "tax")
        self.assertEqual((D(tax_row["paid"]), D(tax_row["remaining"])), (tax, D("0.00")))

    def test_tax_credited_to_supplier_is_stale_and_repost_moves_it(self):
        """INV-0023/INV-0025 رُحّلتا وضريبتهما دائنةٌ للمورد ⇒ «متأخّرة»، والأمر يعرضهما،
        و«أعد الاحتساب والترحيل» ينقلها لحساب الضريبة."""
        from io import StringIO
        from django.core.management import call_command
        from logistics.landed_cost import posted_invoices_cost_drift

        inv = self._post(self._taxed_invoice())
        tax = inv.tax_amount
        # قيدٌ قبل القرار: سطر الضريبة على ذمّة المورد.
        line = inv.journal.lines.get(account=self._tax_payable_account())
        JournalLine.objects.filter(pk=line.pk).update(account=self.ap, partner=self.supplier)
        self.assertEqual(self._ap_credit(inv), D("3500.00") + tax)
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertIn(inv.pk, [r["id"] for r in drift["stale_posted_invoices"]])
        out = StringIO()
        call_command("report_import_off_cost_postings", "--tenant", str(self.tenant.pk), stdout=out)
        self.assertIn(inv.invoice_number, out.getvalue())
        self.assertIn("ضريبة دائنةٌ للمورد", out.getvalue())

        res = self._recalculate(auto_repost=True)
        self.assertEqual(res.status_code, 200, res.content)
        inv.refresh_from_db()
        self.assertEqual(self._ap_credit(inv), D("3500.00"))
        self.assertEqual(
            inv.journal.lines.filter(account=self._tax_payable_account()).aggregate(
                c=Sum("credit"))["c"], tax)
        drift = posted_invoices_cost_drift(tenant=self.tenant, shipment_id=self.shipment.id)
        self.assertEqual(drift["stale_posted_invoices"], [])
        out = StringIO()
        call_command("report_import_off_cost_postings", "--tenant", str(self.tenant.pk), stdout=out)
        self.assertNotIn(inv.invoice_number, out.getvalue())
