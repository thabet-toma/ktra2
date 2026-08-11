"""Section B / Feature 2 — قيد فاتورة الشراء يدين المخزون ويدائن ذمم المورد فقط.

المطلب (المالك — Feature 2): ترحيل فاتورة الشراء يقيّد Dr مخزون/ضريبة /
Cr ذمم المورد بالكامل — ولا يُسوّي النقدية. الدفع للمورد (حتى النقدي) أصبح
وصل دفع مستقل (SupplierPayment: Dr ذمم المورد / Cr صندوق) لا يولّده ترحيل
الفاتورة. لذا قيد فاتورة نقدية يلمس ذمم المورد دائناً فقط — بلا سطر صندوق.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance
from core.models import ActivityLog
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class PurchaseSubledgerRoutingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pisub", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة ذمم الموردين", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-S", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد نقدي", partner_type="Supplier",
            linked_account=cls.ap)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-P", name="الصندوق الرئيسي",
            account_type="Asset", is_active=True)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PSB-1", name_ar="صنف شراء",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_cash_purchase_routes_through_supplier_ap(self):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PINV-CASH-1",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=Decimal("1000.00"),
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH,
            cash_or_bank_account=self.cash)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف شراء",
            quantity=Decimal("1"), unit_price=Decimal("1000.00"),
            total_price=Decimal("1000.00"))

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content

        inv.refresh_from_db()
        jl = list(JournalLine.objects.filter(journal=inv.journal))
        # القيد متوازن
        assert sum(l.debit for l in jl) == sum(l.credit for l in jl)

        ap_lines = [l for l in jl if l.account_id == self.ap.id]
        assert ap_lines, "الشراء النقدي يجب أن يلمس حساب ذمم المورد"
        ap_credit = sum(l.credit for l in ap_lines)
        ap_debit = sum(l.debit for l in ap_lines)
        # Feature 2: ذمم المورد تُدان بكامل القيمة ولا تُسوّى داخل قيد الفاتورة
        assert ap_credit == Decimal("1000.00")
        assert ap_debit == Decimal("0")
        assert all(l.partner_id == self.partner.id for l in ap_lines)

        # توجيه الـsubledger: فقط سطر الذمم (الحساب الرقابي) يَحمل المورد؛ كل سطر
        # آخر (مخزون/وسيط/ضريبة/مصروف) بلا شريك وإلا تلوّث كشف حساب المورد.
        non_ap = [l for l in jl if l.account_id != self.ap.id]
        assert non_ap, "يجب أن يوجد سطر مخزون مقابل"
        assert all(l.partner_id is None for l in non_ap), \
            "سطور غير الذمم يجب ألا تَحمل المورد (وإلا تلوّث الـsubledger)"

        # Feature 2: لا سطر صندوق في قيد الفاتورة — الدفع وصل مستقل
        cash_credit = sum(l.credit for l in jl if l.account_id == self.cash.id)
        assert cash_credit == Decimal("0")

    def test_cash_purchase_auto_settled_supplier_not_creditor(self):
        """T-CASH2 (شراء): ترحيل فاتورة شراء نقدية يُسوّيها تلقائياً بسند صرف
        مستقل، فلا يبقى المورد دائناً (رصيد ذممه الصافي = 0). كانت الأتمتة غير
        مربوطة فبقي الشراء النقدي دائناً للأبد — مرآة بلاغ البيع النقدي."""
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PINV-CASH-SETTLE-1",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-12",
            exchange_rate=Decimal("1"), grand_total=Decimal("1000.00"),
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH,
            cash_or_bank_account=self.cash)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف شراء",
            quantity=Decimal("1"), unit_price=Decimal("1000.00"),
            total_price=Decimal("1000.00"))

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content
        inv.refresh_from_db()

        # سند صرف تلقائي أُنشئ ورُحّل بكامل قيمة الفاتورة
        pay = SupplierPayment.objects.filter(
            partner=self.partner, is_posted=True).first()
        assert pay is not None, "يجب إنشاء سند صرف تلقائي للشراء النقدي"
        assert pay.purchase_invoice_id == inv.id
        assert pay.amount == inv.grand_total
        assert pay.cash_or_bank_account_id == self.cash.id

        # سطر الصندوق في سند الصرف لا يَحمل المورد (T-CASH2 fix)
        pjl = list(JournalLine.objects.filter(journal=pay.journal))
        cash_pay_lines = [l for l in pjl if l.account_id == self.cash.id]
        assert cash_pay_lines and all(l.partner_id is None for l in cash_pay_lines)
        # وسطر الذمم في سند الصرف يَحمل المورد ويُدينه بكامل القيمة
        ap_pay_lines = [l for l in pjl if l.account_id == self.ap.id]
        assert ap_pay_lines and all(l.partner_id == self.partner.id for l in ap_pay_lines)
        assert sum(l.debit for l in ap_pay_lines) == inv.grand_total

        # رصيد المورد الصافي = 0: الفاتورة دائنته 1000 وسند الصرف يَدينه 1000.
        # بعد إصلاح توجيه الـsubledger صار سطر الذمم وحده يَحمل المورد، فيُقاس
        # مباشرةً على partner_posted_balance (بلا فلتر حساب) دون تلوّث المخزون.
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.partner.id)
        assert (credit - debit) == Decimal("0"), \
            "الشراء النقدي يجب ألا يترك المورد دائناً"

    def test_supplier_payment_api_logs_create_and_post_for_supplier(self):
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PINV-PAY-LINK-1",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-14",
            exchange_rate=Decimal("1"), grand_total=Decimal("500.00"),
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=self.product, name="صنف شراء",
            quantity=Decimal("1"), unit_price=Decimal("500.00"),
            total_price=Decimal("500.00"),
        )
        post_invoice = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.id}/post-to-accounting/",
            {}, format="json", **self._auth(),
        )
        assert post_invoice.status_code == 201, post_invoice.content
        create_response = self.client.post(
            "/api/logistics/supplier-payments/",
            {
                "partner": self.partner.id,
                "purchase_invoice": invoice.id,
                "payment_date": "2026-06-14",
                "amount": "125.00",
                "currency": self.ils.CurrencyID,
                "exchange_rate": "1",
                "cash_or_bank_account": self.cash.id,
                "notes": "صرف من بطاقة المورد",
            },
            format="json",
            **self._auth(),
        )
        assert create_response.status_code == 201, create_response.content
        payment_id = create_response.json()["id"]
        # T-AUTOPOST: الحفظ يُرحّل السند فوراً (لا خطوة ترحيل منفصلة).
        assert create_response.json()["is_posted"] is True, create_response.content

        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{invoice.id}/", **self._auth(),
        )
        assert detail.status_code == 200, detail.content
        assert detail.json()["payment_status"] == "partially_paid"
        assert Decimal(detail.json()["amount_paid"]) == Decimal("125.00")
        assert Decimal(detail.json()["remaining_balance"]) == Decimal("375.00")
        assert Decimal(detail.json()["supplier_balance_before_invoice"]) == Decimal("0.00")
        assert Decimal(detail.json()["supplier_balance_after_invoice"]) == Decimal("375.00")
        assert Decimal(detail.json()["supplier_balance_current"]) == Decimal("375.00")
        assert len(detail.json()["payment_details"]) == 1
        assert detail.json()["payment_details"][0]["id"] == payment_id
        assert detail.json()["payment_details"][0]["source"] == "supplier_payment"
        assert detail.json()["payment_details"][0]["is_posted"] is True

        rows = ActivityLog.objects.filter(
            tenant=self.tenant,
            entity_type="supplier_payment",
            entity_id=payment_id,
        ).order_by("id")
        assert list(rows.values_list("action", flat=True)) == ["payment", "post"]
        assert all(
            row.partner_links.filter(partner=self.partner).exists()
            for row in rows
        )

    def test_credit_purchase_supplier_owed_equals_grand_total(self):
        """آجل: الشراء بالأجل لا يُسوّى تلقائياً، فيبقى المورد دائناً بكامل
        الإجمالي. بعد إصلاح التوجيه يَحمل سطرُ الذمم وحده المورد، فيعكس
        partner_posted_balance المبلغ المستحق فعلاً (credit − debit == grand_total)
        بدل صفرٍ زائف كان يَنتج عن مدين المخزون المُلوِّث."""
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PINV-CREDIT-1",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-13",
            exchange_rate=Decimal("1"), grand_total=Decimal("1000.00"),
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف شراء",
            quantity=Decimal("1"), unit_price=Decimal("1000.00"),
            total_price=Decimal("1000.00"))

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content
        inv.refresh_from_db()

        # لا تسوية تلقائية للشراء الآجل
        assert not SupplierPayment.objects.filter(partner=self.partner).exists()

        # سطر الذمم وحده يَحمل المورد
        jl = list(JournalLine.objects.filter(journal=inv.journal))
        assert all(
            l.partner_id == (self.partner.id if l.account_id == self.ap.id else None)
            for l in jl
        ), "فقط سطر الذمم يَحمل المورد"

        # المورد دائن بكامل الإجمالي — لا صفر زائف
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.partner.id)
        assert (credit - debit) == Decimal("1000.00"), \
            "الشراء الآجل غير المدفوع يجب أن يُظهر المورد دائناً بكامل الإجمالي"
