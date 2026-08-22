"""T-APPAID — «المدفوع» على فاتورة الشراء يُحسب ولا يُفترض.

القاعدة السابقة كانت تعطي كل فاتورة نقدية مرحّلة `paid = payable` بغضّ النظر عن
وجود سندٍ في الدفاتر، وتسقط عند غيابه على `attached_cash_amount` — وهو عمودٌ لا
يُرحّل شيئاً (نقطته القديمة تكتبه ولا يقرؤه الترحيل). فكانت الشاشة تقول «مدفوعة
بالكامل» بينما ذمم المورد دائنة: نفس الدرس الذي دُفع ثمنه على جانب البيع
(`amount_paid` = مجموع التوزيعات المرحّلة، لا افتراض).

ما يُحتسب اليوم شيئان، كلاهما قيدٌ فعليّ: سنداتٌ مرحّلة، وتسويةٌ داخل قيد
الفاتورة نفسه (فواتير ما قبل Feature 2 — تُحتسب لأنها حقٌّ لا افتراض).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import (
    annotate_purchase_invoice_payment_summary,
    purchase_invoice_payment_summary,
)
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class PurchasePaidIsComputedTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="appaid", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة المدفوع المحسوب", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-C", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier",
            linked_account=cls.ap)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-C", name="الصندوق",
            account_type="Asset", is_active=True)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="APC-1", name_ar="صنف",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, *, payment_type, total="1000.00"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.ils, invoice_date="2026-06-16",
            exchange_rate=Decimal("1"), grand_total=Decimal(total),
            payment_type=payment_type,
            cash_or_bank_account=(
                self.cash if payment_type == PurchaseInvoice.PAYMENT_TYPE_CASH else None
            ),
        )
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف",
            quantity=Decimal("1"), unit_price=Decimal(total),
            total_price=Decimal(total))
        return inv

    def _post(self, inv):
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content
        inv.refresh_from_db()

    def _list_row(self, inv):
        """الرقم كما تحسبه نسخة SQL — لا كما تحسبه نسخة بايثون."""
        row = annotate_purchase_invoice_payment_summary(
            PurchaseInvoice.objects.filter(pk=inv.pk)
        ).first()
        return row.list_payment_status, Decimal(str(row.list_amount_paid))

    def _detail(self, inv):
        inv = PurchaseInvoice.objects.get(pk=inv.pk)
        summary = purchase_invoice_payment_summary(inv)
        return summary["payment_status"], summary["amount_paid"]

    def test_cash_invoice_is_paid_only_while_its_voucher_stands(self):
        """الفاتورة النقدية مدفوعةٌ لأن سندها مرحّل — فإن أُلغي ترحيله عادت
        «غير مدفوعة». كانت تبقى «مدفوعة بالكامل» لأنها نقدية لا غير."""
        inv = self._invoice("PINV-C-1", payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH)
        self._post(inv)
        assert self._detail(inv) == ("paid", Decimal("1000.00"))
        assert self._list_row(inv) == ("paid", Decimal("1000.00"))

        auto = SupplierPayment.objects.get(auto_settled_invoice=inv)
        undo = self.client.post(
            f"/api/logistics/supplier-payments/{auto.pk}/unpost/",
            {}, format="json", **self._auth())
        assert undo.status_code == 200, undo.content

        assert self._detail(inv) == ("unpaid", Decimal("0.00")), \
            "سندٌ غير مرحّل لا يُسدّد شيئاً — والفاتورة النقدية ليست استثناءً"
        assert self._list_row(inv) == ("unpaid", Decimal("0.00")), \
            "القائمة والتفصيل يقولان الرقم نفسه"

    def test_attached_cash_amount_alone_is_not_payment(self):
        """العمود القديم يُكتب ولا يُرحّل — فلا يُحتسب مدفوعاً."""
        inv = self._invoice("PINV-C-2", payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        self._post(inv)
        PurchaseInvoice.objects.filter(pk=inv.pk).update(
            attached_cash_amount=Decimal("400.00"))

        assert self._detail(inv) == ("unpaid", Decimal("0.00"))
        assert self._list_row(inv) == ("unpaid", Decimal("0.00"))

    def test_legacy_in_journal_settlement_counts_as_paid(self):
        """فاتورة ما قبل Feature 2: التسوية داخل قيدها (مدين ذمم المورد) قيدٌ
        متوازن وصحيح ⇒ تُحتسب مدفوعة. حذفُ القاعدة كان سيقلب فواتير تاريخية
        مسدَّدة إلى «غير مدفوعة»."""
        inv = self._invoice("PINV-C-3", payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        self._post(inv)
        # نحاكي «Section B» القديم: سطرا تسوية داخل قيد الفاتورة نفسه.
        JournalLine.objects.create(
            tenant=self.tenant, journal_id=inv.journal_id, account=self.ap,
            partner=self.partner, debit=Decimal("300.00"), credit=Decimal("0"),
            description="تسوية نقدية قديمة")
        JournalLine.objects.create(
            tenant=self.tenant, journal_id=inv.journal_id, account=self.cash,
            debit=Decimal("0"), credit=Decimal("300.00"),
            description="تسوية نقدية قديمة")

        assert self._detail(inv) == ("partially_paid", Decimal("300.00"))
        assert self._list_row(inv) == ("partially_paid", Decimal("300.00"))

    def test_return_invoice_ap_debit_is_not_a_settlement(self):
        """المرجع يدين الذمم بحكم تعريفه — لا يُقرأ تسويةً فيبدو «مدفوعاً»."""
        original = self._invoice(
            "PINV-C-4", payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        self._post(original)
        ret = self.client.post(
            "/api/logistics/purchase-invoices/returns/",
            {
                "original_invoice": original.pk,
                "partner": self.partner.id,
                "return_date": "2026-06-17",
                "lines": [{
                    "product": self.product.id, "quantity": "1",
                    "unit_price": "1000.00",
                }],
            },
            format="json", **self._auth())
        assert ret.status_code in (200, 201), ret.content
        ret_id = ret.json().get("id") or ret.json().get("invoice", {}).get("id")
        posted = self.client.post(
            f"/api/logistics/purchase-invoices/{ret_id}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert posted.status_code in (200, 201), posted.content

        ret_inv = PurchaseInvoice.objects.get(pk=ret_id)
        assert purchase_invoice_payment_summary(ret_inv)["amount_paid"] == Decimal("0.00")
        status_sql, paid_sql = self._list_row(ret_inv)
        assert paid_sql == Decimal("0.00"), "المرجع ليس مدفوعاً بمدينه للذمم"

    def test_cash_invoice_without_any_cash_account_is_refused_not_skipped(self):
        """التخطّي الصامت كان يُنتج فاتورة «نقدية» بلا تسوية والمورد دائن، ثم
        تقول الشاشة «مدفوعة». الشرط صار ظاهراً عند الترحيل."""
        from unittest.mock import patch

        inv = self._invoice("PINV-C-5", payment_type=PurchaseInvoice.PAYMENT_TYPE_CASH)
        PurchaseInvoice.objects.filter(pk=inv.pk).update(cash_or_bank_account=None)

        with patch("accounting.services.resolve_default_cash_account", return_value=None):
            res = self.client.post(
                f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
                {}, format="json", **self._auth())
        assert res.status_code == 400, res.content
        assert "صندوق" in res.json()["error"], res.json()
        inv.refresh_from_db()
        assert inv.is_posted is False, "الرفض ذرّي — لا فاتورة نصف مرحّلة"
