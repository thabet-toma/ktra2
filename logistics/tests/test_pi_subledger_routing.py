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
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
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

        # Feature 2: لا سطر صندوق في قيد الفاتورة — الدفع وصل مستقل
        cash_credit = sum(l.credit for l in jl if l.account_id == self.cash.id)
        assert cash_credit == Decimal("0")
