"""الطرف الدائن لرسم الفاتورة (`PurchaseInvoiceFee.credit_partner`/`credit_account`).

كان كل رسمٍ يُدائَن على مورد الفاتورة: «تكاليف كترا» على فاتورةٍ دولية تجعل المورد
الصيني دائناً بها. الرسم ذو الطرف الدائن يُدائَن لجهته في سطرٍ مستقل، وذمّة المورد
بلا مبلغه؛ وجانب المدين لا يتغيّر.
"""
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount, JournalHeader
from accounting.services import create_fiscal_year, partner_posted_balance
from logistics.models import PurchaseInvoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class FeeCreditPartyPostingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="fee-credit", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الطرف الدائن", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)

        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.misc_fees = Account.objects.get(tenant=cls.tenant, code="5307")
        cls.bank_charges = Account.objects.create(
            tenant=cls.tenant, code="5208", name="مصاريف بنكية وعمولات",
            account_type="Expense", is_active=True)
        cls.ktra_ap = Account.objects.create(
            tenant=cls.tenant, code="AP-KTRA", name="ذمم كترا",
            account_type="Liability", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="BOX-FEE", name="صندوق الرسوم",
            account_type="Asset", is_active=True)
        CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="fee-box", name="صندوق الرسوم",
            currency_code="ILS", account=cls.cash)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مصنع الصين", partner_type="Supplier",
            linked_account=cls.ap)
        cls.ktra = Partner.objects.create(
            tenant=cls.tenant, name="كترا", partner_type="Supplier",
            linked_account=cls.ktra_ap)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, **fee):
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number,
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            invoice_date="2026-07-05", partner=self.supplier, currency=self.ils,
            subtotal=D("1000"), grand_total=D("1000"))
        invoice.items.create(
            name="بضاعة", quantity=D("1"), unit_price=D("1000"), total_price=D("1000"))
        if fee:
            invoice.fees.create(tenant=self.tenant, **{
                "description": "تكاليف كترا", "amount": D("100"),
                "expense_account": self.misc_fees, "capitalize_to_inventory": False,
                **fee,
            })
        return invoice

    def _post(self, invoice, expect=201):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {"receive_on_post": False}, format="json", **self._auth())
        self.assertEqual(res.status_code, expect, res.content)
        return res

    def _lines(self, invoice):
        journal = JournalHeader.objects.get(
            reference_type="PURCHASE_INVOICE", reference_id=invoice.pk)
        return sorted(
            (l.account.code, l.debit, l.credit, l.partner_id) for l in journal.lines.all())

    def test_fee_without_credit_party_journal_unchanged(self):
        # قبل الطرف الدائن: مدين البضاعة + مدين مصروف الرسم / دائن المورد بالإجمالي + الرسم.
        invoice = self._invoice("FCP-0", description="رسم فحص")
        self._post(invoice)
        lines = self._lines(invoice)
        self.assertIn(("5307", D("100.00"), D("0.00"), None), lines)
        self.assertIn(("2101", D("0.00"), D("1100.00"), self.supplier.pk), lines)
        self.assertEqual(len([l for l in lines if l[2] > 0]), 1)
        self.assertEqual(sum(l[1] for l in lines), D("1100.00"))
        self.assertEqual(sum(l[2] for l in lines), D("1100.00"))

    def test_credit_partner_fee_credits_party_and_voucher_clears_it(self):
        invoice = self._invoice("FCP-1", credit_partner=self.ktra)
        self._post(invoice)
        lines = self._lines(invoice)
        # المدين كما كان، والدائن انقسم: المورد بالإجمالي وحده، وكترا برسمها بوسمها.
        self.assertIn(("5307", D("100.00"), D("0.00"), None), lines)
        self.assertIn(("2101", D("0.00"), D("1000.00"), self.supplier.pk), lines)
        self.assertIn(("AP-KTRA", D("0.00"), D("100.00"), self.ktra.pk), lines)
        self.assertEqual(sum(l[1] for l in lines), sum(l[2] for l in lines))

        debit, credit = partner_posted_balance(self.tenant.TenantID, self.ktra.pk)
        self.assertEqual(credit - debit, D("100.00"))
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{invoice.pk}/", **self._auth()).json()
        self.assertEqual(D(detail["payable_total"]), D("1000.00"))
        fee = detail["fees"][0]
        self.assertEqual(fee["credit_partner"], self.ktra.pk)
        self.assertEqual(fee["credit_partner_name"], "كترا")

        voucher = self.client.post("/api/logistics/supplier-payments/", {
            "partner": self.ktra.id, "payment_date": "2026-07-08", "amount": "100",
            "currency": self.ils.CurrencyID, "exchange_rate": "1",
            "cash_or_bank_account": self.cash.id,
        }, format="json", **self._auth())
        self.assertEqual(voucher.status_code, 201, voucher.content)
        debit, credit = partner_posted_balance(self.tenant.TenantID, self.ktra.pk)
        self.assertEqual(credit - debit, D("0.00"))

    def test_capitalized_credit_account_fee_raises_cost_not_supplier(self):
        # عمولة الحوالة على التكلفة: مدين المخزون، دائن «مصاريف بنكية وعمولات».
        plain = self._invoice("FCP-2A")
        self._post(plain)
        invoice = self._invoice(
            "FCP-2", description="عمولات الحوالات", amount=D("194.40"),
            credit_account=self.bank_charges, capitalize_to_inventory=True)
        self._post(invoice)
        before, lines = self._lines(plain), self._lines(invoice)
        self.assertIn(("5208", D("0.00"), D("194.40"), None), lines)
        self.assertIn(("2101", D("0.00"), D("1000.00"), self.supplier.pk), lines)
        self.assertEqual(sum(l[1] for l in lines), sum(l[1] for l in before) + D("194.40"))
        # المرسمَل لا يُدين حساب مصروف الرسم.
        self.assertFalse([l for l in lines if l[0] == "5307"])

    def test_cash_or_bank_credit_party_is_refused(self):
        for target in (self.cash, Account.objects.get(tenant=self.tenant, code="1101")):
            invoice = self._invoice(f"FCP-3-{target.code}")
            res = self.client.patch(
                f"/api/logistics/purchase-invoices/{invoice.pk}/",
                {"fees": [{"description": "رسم", "amount": "50",
                           "expense_account": self.misc_fees.id,
                           "credit_account": target.id}]},
                format="json", **self._auth())
            self.assertEqual(res.status_code, 400, res.content)
            self.assertIn("صندوقاً أو بنكاً", str(res.json()))
            self.assertFalse(invoice.fees.exists())

        # رسمٌ وصل للقاعدة بغير الواجهة: الترحيل يرفضه أيضاً.
        invoice = self._invoice("FCP-3", credit_account=self.cash)
        res = self._post(invoice, expect=400)
        self.assertIn("صندوقاً أو بنكاً", res.json()["error"])
        self.assertFalse(JournalHeader.objects.filter(
            reference_type="PURCHASE_INVOICE", reference_id=invoice.pk).exists())

    def test_both_credit_fields_and_taxable_party_fee_are_refused(self):
        invoice = self._invoice("FCP-4")
        for extra in ({"credit_account": self.bank_charges.id},
                      {"is_taxable": True}):
            res = self.client.patch(
                f"/api/logistics/purchase-invoices/{invoice.pk}/",
                {"fees": [{"description": "رسم", "amount": "50",
                           "expense_account": self.misc_fees.id,
                           "credit_partner": self.ktra.id, **extra}]},
                format="json", **self._auth())
            self.assertEqual(res.status_code, 400, res.content)

    def test_archive_locked_deal_refuses_party_fee(self):
        # ترحيل فاتورة صفقة الأرشيف مقفلٌ أصلاً (`assert_invoice_not_archive_locked`)؛
        # الحارس هنا عند الحفظ: لا يُسجَّل عليها رسمٌ بطرفٍ دائن.
        from logistics.models import LogisticsDeal
        invoice = self._invoice("FCP-5")
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-ARCH", partner=self.supplier,
            order_date="2026-06-01", total_amount=D("1000"))
        PurchaseInvoice.objects.filter(pk=invoice.pk).update(deal=deal)
        payload = {"fees": [{"description": "تكاليف كترا", "amount": "50",
                             "expense_account": self.misc_fees.id,
                             "credit_partner": self.ktra.id}]}
        with mock.patch(
            "logistics.payment_posting.live_archive_deal_journals",
            return_value={deal.pk: [1]},
        ):
            res = self.client.patch(
                f"/api/logistics/purchase-invoices/{invoice.pk}/", payload,
                format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("أرشيف", str(res.json()))
        res = self.client.patch(
            f"/api/logistics/purchase-invoices/{invoice.pk}/", payload,
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(invoice.fees.get().credit_partner_id, self.ktra.pk)
