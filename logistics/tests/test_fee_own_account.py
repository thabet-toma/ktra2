"""رسم الفاتورة الدولية = حسابه هو (قرار المالك — يحلّ محلّ اختيار «الطرف الدائن»).

دائن الرسم حسابُ ذمّةٍ باسم الرسم نفسه تحت «مستحقات رسوم الاستيراد» — يُنشأ إن غاب،
ويُسدَّد بسند صرف عليه. حسابُ مصروفٍ بالاسم نفسه (مدين الرسم) لا يصلح دائناً.
المحلية كما كانت: رسمها على المورد.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_expense_voucher, create_fiscal_year
from logistics.models import PurchaseInvoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class FeeOwnAccountTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="fee-own", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة رسم بحسابه", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.misc = Account.objects.get(tenant=cls.tenant, code="5307")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مصنع الصين", partner_type="Supplier",
            linked_account=cls.ap)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL):
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, invoice_type=invoice_type,
            invoice_date="2026-07-05", partner=self.supplier, currency=self.ils,
            subtotal=D("1000"), grand_total=D("1000"))
        invoice.items.create(
            name="بضاعة", quantity=D("1"), unit_price=D("1000"), total_price=D("1000"))
        return invoice

    def _save_fee(self, invoice, description="تكاليف كترا", amount="100"):
        res = self.client.patch(
            f"/api/logistics/purchase-invoices/{invoice.pk}/",
            {"fees": [{"description": description, "amount": amount,
                       "expense_account": self.misc.id}]},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        return invoice.fees.select_related("credit_account", "expense_account").get()

    def _post(self, invoice):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {"receive_on_post": False}, format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        return JournalHeader.objects.get(reference_type="PURCHASE_INVOICE", reference_id=invoice.pk)

    def _balance(self, account):
        lines = JournalLine.objects.filter(account=account, journal__is_posted=True)
        return sum((l.base_credit - l.base_debit for l in lines), D("0"))

    def test_new_fee_name_creates_accrual_account_credited_and_cleared_by_voucher(self):
        invoice = self._invoice("FOA-1")
        fee = self._save_fee(invoice)
        accrual = fee.credit_account
        self.assertIsNotNone(accrual)
        self.assertEqual(accrual.name, "تكاليف كترا")
        self.assertEqual(accrual.account_type, "Liability")
        self.assertEqual(accrual.parent.name, "مستحقات رسوم الاستيراد")
        self.assertEqual(accrual.parent.account_type, "Liability")

        journal = self._post(invoice)
        lines = list(journal.lines.all())
        self.assertIn((accrual.id, D("100.00")), [(l.account_id, l.credit) for l in lines])
        supplier = sum((l.credit for l in lines if l.account_id == self.ap.id), D("0"))
        self.assertEqual(supplier, D("1000.00"))  # المورد بلا الرسم
        self.assertEqual(self._balance(accrual), D("100.00"))

        # سند صرفٍ على الحساب بلا شريك يصفّره.
        create_expense_voucher(
            tenant=self.tenant, date="2026-07-10", amount=D("100"), currency=self.ils,
            payment_method="cash", expense_account=accrual,
            cash_or_bank_account_id=self.cash.id, description="دفع تكاليف كترا")
        self.assertEqual(self._balance(accrual), D("0.00"))

    def test_same_name_expense_account_is_not_the_credit(self):
        invoice = self._invoice("FOA-2")
        fee = self._save_fee(invoice)
        # مدين الرسم الدولي يُربط بحساب مصروفٍ بالاسم نفسه تحت «53» — والدائن ذمّةٌ بجانبه.
        self.assertEqual(fee.expense_account.name, "تكاليف كترا")
        self.assertEqual(fee.expense_account.account_type, "Expense")
        self.assertNotEqual(fee.credit_account_id, fee.expense_account_id)
        self.assertEqual(fee.credit_account.account_type, "Liability")
        journal = self._post(invoice)
        self.assertFalse(journal.lines.filter(account=fee.expense_account, credit__gt=0).exists())
        # الاسم نفسه على فاتورةٍ ثانية: الحساب نفسه، لا حسابٌ جديد.
        other = self._save_fee(self._invoice("FOA-2B"))
        self.assertEqual(other.credit_account_id, fee.credit_account_id)

    def test_unsaved_draft_fee_is_bound_when_posted(self):
        # الرسوم الـ14 القديمة: بلا طرفٍ دائن في القاعدة — الترحيل يربطها بالقاعدة نفسها.
        invoice = self._invoice("FOA-3")
        fee = invoice.fees.create(
            tenant=self.tenant, description="كترا", amount=D("50"),
            expense_account=self.misc, capitalize_to_inventory=False)
        journal = self._post(invoice)
        fee.refresh_from_db()
        self.assertEqual(fee.credit_account.name, "كترا")
        self.assertTrue(journal.lines.filter(account=fee.credit_account, credit=D("50.00")).exists())
        self.assertFalse(journal.lines.filter(account=self.ap, credit=D("1050.00")).exists())

    def test_local_invoice_fee_stays_on_supplier(self):
        invoice = self._invoice("FOA-4", PurchaseInvoice.INVOICE_TYPE_LOCAL)
        fee = self._save_fee(invoice, description="رسوم توصيل")
        self.assertIsNone(fee.credit_account_id)
        journal = self._post(invoice)
        self.assertTrue(journal.lines.filter(account=self.ap, credit=D("1100.00")).exists())
