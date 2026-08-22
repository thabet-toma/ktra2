"""T-DUE — تاريخ الاستحقاق ومهلة السداد و«متأخرة»، على الجانبين بقاعدة واحدة.

كان `due_date` على فاتورة البيع وحدها، وفاتورة الشراء بلا «متى يُدفع» أصلاً:
أعمارُ الذمم **الدائنة** تُعمَّر بتاريخ الفاتورة بينما نظيرتها المدينة تُعمَّر
بالاستحقاق (`core/reports/financial.py`)، فتظهر فاتورةٌ مهلتها 60 يوماً في خانة
«31–60» بعد 31 يوماً وهي لم تستحقّ بعد. ولا شاشة تقول «هذه تأخّرت».

و«متأخرة» ليست حالة دفعٍ رابعة بل بُعدٌ فوقها: جعلُها قيمةً في `payment_status`
كان يكسر الفلاتر والشارات القائمة ويخفي «كم بقي» خلف «تأخّر».
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from core.payments import document_overdue_state, resolve_due_date
from core.reports import run_report
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company


class DueDateRuleTest(APITestCase):
    """القاعدة النقيّة — بلا ORM ولا HTTP."""

    def test_explicit_due_date_beats_terms(self):
        explicit = datetime.date(2026, 9, 1)
        assert resolve_due_date(datetime.date(2026, 8, 1), explicit, 30) == explicit

    def test_terms_derive_the_due_date_when_absent(self):
        assert resolve_due_date(datetime.date(2026, 8, 1), None, 30) \
            == datetime.date(2026, 8, 31)

    def test_zero_terms_means_due_on_receipt(self):
        assert resolve_due_date(datetime.date(2026, 8, 1), None, 0) \
            == datetime.date(2026, 8, 1)

    def test_no_terms_and_no_date_stays_empty(self):
        assert resolve_due_date(datetime.date(2026, 8, 1), None, None) is None

    def test_overdue_needs_both_a_due_date_and_a_remainder(self):
        past = timezone.localdate() - datetime.timedelta(days=5)
        assert document_overdue_state(past, Decimal("10"))["is_overdue"] is True
        assert document_overdue_state(past, Decimal("10"))["days_overdue"] == 5
        # سُدِّدت ⇒ لا تأخّر مهما مضى.
        assert document_overdue_state(past, Decimal("0"))["is_overdue"] is False
        # بلا تاريخ استحقاق لا تخمين.
        assert document_overdue_state(None, Decimal("10"))["is_overdue"] is False


class PurchaseDueDateTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="due", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الاستحقاق", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-D", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1103-D", name="ذمم العملاء",
            account_type="Asset", is_active=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الاستحقاق", partner_type="Supplier",
            linked_account=cls.ap)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الاستحقاق", partner_type="Customer",
            linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="DUE-1", name_ar="صنف",
            quantity_on_hand=Decimal("100"), avg_cost=Decimal("10"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_purchase_terms_derive_the_due_date_through_the_api(self):
        res = self.client.post(
            "/api/logistics/purchase-invoices/",
            {
                "partner": self.supplier.id,
                "invoice_date": "2026-08-01",
                "payment_terms_days": 30,
                "currency": "ILS",
                "exchange_rate": "1",
                "items": [{
                    "product": self.product.id, "name": "صنف",
                    "quantity": "1", "unit_price": "100", "total_price": "100",
                }],
            },
            format="json", **self._auth())
        assert res.status_code == 201, res.content
        assert res.json()["due_date"] == "2026-08-31"

    def test_explicit_purchase_due_date_is_not_overwritten(self):
        res = self.client.post(
            "/api/logistics/purchase-invoices/",
            {
                "partner": self.supplier.id,
                "invoice_date": "2026-08-01",
                "payment_terms_days": 30,
                "due_date": "2026-10-15",
                "currency": "ILS",
                "exchange_rate": "1",
                "items": [],
            },
            format="json", **self._auth())
        assert res.status_code == 201, res.content
        assert res.json()["due_date"] == "2026-10-15"

    def _overdue_purchase(self, number="PINV-DUE-1"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.supplier,
            currency=self.ils, invoice_date=timezone.localdate() - datetime.timedelta(days=40),
            due_date=timezone.localdate() - datetime.timedelta(days=10),
            exchange_rate=Decimal("1"), grand_total=Decimal("100.00"))
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف",
            quantity=Decimal("1"), unit_price=Decimal("100"),
            total_price=Decimal("100"))
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        inv.refresh_from_db()
        return inv

    def test_purchase_detail_and_list_agree_on_overdue(self):
        inv = self._overdue_purchase()
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        assert detail["is_overdue"] is True
        assert detail["days_overdue"] == 10
        # الحالة تبقى «غير مدفوعة» — التأخّر بُعدٌ فوقها لا بديلٌ عنها.
        assert detail["payment_status"] == "unpaid"

        listed = self.client.get(
            "/api/logistics/purchase-invoices/?page=1&payment_status=overdue",
            **self._auth()).json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        assert [r["id"] for r in rows] == [inv.pk]
        assert rows[0]["is_overdue"] is True
        assert rows[0]["days_overdue"] == 10

    def test_a_paid_invoice_is_never_overdue(self):
        inv = self._overdue_purchase("PINV-DUE-2")
        cash = Account.objects.create(
            tenant=self.tenant, code="1110-D", name="صندوق",
            account_type="Asset", is_active=True)
        paid = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/pay/",
            {"cash": "100.00", "cash_account_id": cash.id},
            format="json", **self._auth())
        assert paid.status_code == 200, paid.content
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        assert detail["is_overdue"] is False

    def test_payables_aging_buckets_by_due_date_not_invoice_date(self):
        """فاتورة عمرها 40 يوماً ومهلتها 60 لم تستحقّ بعد ⇒ خانة «حتى 30»."""
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PINV-DUE-3", partner=self.supplier,
            currency=self.ils,
            invoice_date=timezone.localdate() - datetime.timedelta(days=40),
            due_date=timezone.localdate() + datetime.timedelta(days=20),
            exchange_rate=Decimal("1"), grand_total=Decimal("100.00"))
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف",
            quantity=Decimal("1"), unit_price=Decimal("100"), total_price=Decimal("100"))
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())

        report = run_report("payables-aging", self.tenant.TenantID, {})
        row = next(r for r in report["rows"] if r["partner_name"] == "مورد الاستحقاق")
        assert Decimal(row["b0"]) == Decimal("100.00"), report["rows"]
        assert Decimal(row["b1"]) == Decimal("0.00")

    def test_sales_side_shares_the_same_rule(self):
        inv = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SINV-DUE-1", customer=self.customer,
            currency=self.ils,
            invoice_date=timezone.localdate() - datetime.timedelta(days=20),
            due_date=timezone.localdate() - datetime.timedelta(days=3),
            invoice_type=SalesInvoice.INVOICE_CREDIT,
            status=SalesInvoice.STATUS_POSTED,
            grand_total=Decimal("100.00"), amount_paid=Decimal("0"))
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("100"))

        detail = self.client.get(
            f"/api/sales/invoices/{inv.pk}/", **self._auth()).json()
        assert detail["is_overdue"] is True
        assert detail["days_overdue"] == 3

        listed = self.client.get(
            "/api/sales/invoices/?page=1&payment_status=overdue", **self._auth()).json()
        rows = listed["results"] if isinstance(listed, dict) else listed
        assert inv.pk in [r["id"] for r in rows]

    def test_sales_terms_derive_the_due_date_too(self):
        res = self.client.post(
            "/api/sales/invoices/",
            {
                "customer": self.customer.id,
                "invoice_date": "2026-08-01",
                "payment_terms_days": 45,
                "currency": self.ils.CurrencyID,
                "lines": [{"product": self.product.id, "quantity": "1", "unit_price": "100"}],
            },
            format="json", **self._auth())
        assert res.status_code == 201, res.data
        assert res.data["due_date"] == "2026-09-15"
