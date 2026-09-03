"""ISSUE #57 — الفترات الضريبية على دفتر العميل: تغيير الطريق لا المنطق.

`TaxPeriodReview` وفحوص `readiness.py` وحارس `guards.py` (M5) لا تتغيّر هنا حرفاً
واحداً — هذه الاختبارات تثبت أنها **تعمل على دفتر العميل المُدار** حين يفتح
المكتب بطاقته (`X-Tenant-Id` = دفتر العميل) لا على دفتر المكتب نفسه، وأن قفل
فترةٍ على دفتر عميل لا يمسّ دفتر المكتب ولا دفتر عميلٍ آخر. الملاحظة على الأثر
عند الـHTTP (صفوف موجودة، حالة المستند، كود الاستجابة) — لا استدعاء
`post_journal` مباشرة ولا فحص شكل دالّة داخلية.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine, TaxRate
from accounting.services import create_fiscal_year
from accountant_portal.models import TaxPeriodReview
from core.models import TenantModule
from core.modules import invalidate_module_cache
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company

ACC = "/api/accounting"
TAX = "/api/accountant/tax/periods"
PASSWORD = "Office-Manager-Pass-77"


def _configure_vat_accounts(tenant):
    """issue #79: TaxRate باتجاه المخرجات على «2104» — كلاهما مزروع في COA_DATA."""
    output_account = Account.objects.get(tenant=tenant, code="2104")
    input_account = Account.objects.get(tenant=tenant, code="1105")
    TaxRate.objects.create(
        tenant=tenant, name="ض.ق.م مخرجات", code="VAT-OUT",
        rate=Decimal("16.00"), tax_account=output_account, direction="sales",
    )
    TaxRate.objects.create(
        tenant=tenant, name="ض.ق.م مدخلات", code="VAT-IN",
        rate=Decimal("16.00"), tax_account=input_account, direction="purchase",
    )


def _invoice(tenant, currency, number, day, **overrides):
    customer = Partner.objects.create(
        tenant=tenant, name=f"زبون {number}", partner_type="customer", tax_number="123",
    )
    payload = {
        "tenant": tenant,
        "invoice_number": number,
        "customer": customer,
        "invoice_date": day,
        "currency": currency,
        "status": SalesInvoice.STATUS_POSTED,
        "subtotal_excl_tax": Decimal("100.00"),
        "tax_amount": Decimal("16.00"),
        "grand_total": Decimal("116.00"),
    }
    payload.update(overrides)
    invoice = SalesInvoice.objects.create(**payload)
    _post_tax_journal(invoice)
    return invoice


def _post_tax_journal(invoice):
    """قيدٌ حقيقي لضريبة الفاتورة — `build_vat_statement` (issue #79) يقرأ الدفتر لا `tax_amount`."""
    amount = Decimal(str(invoice.tax_amount or 0))
    if amount == 0 or invoice.status != SalesInvoice.STATUS_POSTED:
        return
    tenant = invoice.tenant
    try:
        contra = Account.objects.get(tenant=tenant, code="1103")
        if invoice.invoice_kind == SalesInvoice.INVOICE_KIND_PURCHASE:
            vat_account = Account.objects.get(tenant=tenant, code="1105")
            vat_debit, vat_credit = amount, Decimal("0")
        elif invoice.invoice_kind == SalesInvoice.INVOICE_KIND_PURCHASE_RETURN:
            vat_account = Account.objects.get(tenant=tenant, code="1105")
            vat_debit, vat_credit = Decimal("0"), amount
        elif invoice.invoice_kind == SalesInvoice.INVOICE_KIND_SALE_RETURN:
            vat_account = Account.objects.get(tenant=tenant, code="2104")
            vat_debit, vat_credit = amount, Decimal("0")
        else:  # sale
            vat_account = Account.objects.get(tenant=tenant, code="2104")
            vat_debit, vat_credit = Decimal("0"), amount
    except Account.DoesNotExist:
        return
    header = JournalHeader.objects.create(
        tenant=tenant, transaction_date=invoice.invoice_date,
        description=f"ضريبة — {invoice.invoice_number}", is_posted=True,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=header, account=vat_account,
        debit=vat_debit, credit=vat_credit,
    )
    JournalLine.objects.create(
        tenant=tenant, journal=header, account=contra,
        debit=vat_credit, credit=vat_debit,
    )


class ClientBookTaxPeriodRoutingTest(APITestCase):
    """معيار القبول: المكتب يجهّز فترة العميل من بطاقته، والفحوص على دفتره هو."""

    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )[0]
        cls.office_manager = User.objects.create_user(
            "office-mgr-57", password=PASSWORD, email="office57@example.com",
        )
        cls.office = create_company("مكتب محاسبة ٥٧", cls.office_manager)
        cls.book = create_company("عميل مُدار ٥٧", cls.office_manager, managed_by=cls.office)
        TenantModule.objects.create(tenant=cls.book, module_key="accountant_portal", enabled=True)
        create_fiscal_year(cls.book, 2026)
        create_fiscal_year(cls.office, 2026)
        _configure_vat_accounts(cls.book)

    def setUp(self):
        invalidate_module_cache(self.book.pk)
        self.client.force_authenticate(self.office_manager)
        self.book_headers = {"HTTP_X_TENANT_ID": str(self.book.pk)}

    def _prepare(self, period_from=date(2026, 6, 1), period_to=date(2026, 6, 30)):
        return self.client.post(
            f"{TAX}/prepare/",
            {"period_from": str(period_from), "period_to": str(period_to)},
            format="json", **self.book_headers,
        )

    def test_prepared_period_and_readiness_reflect_the_clients_own_book(self):
        # مسودة على دفتر **المكتب نفسه** — لا يجوز أن تظهر مانعاً على فترة العميل.
        _invoice(
            self.office, self.currency, "OFFICE-DRAFT", date(2026, 6, 5),
            status=SalesInvoice.STATUS_DRAFT,
        )
        # فاتورة مرحَّلة على دفتر **العميل** — هذه وحدها ما يجب أن تراه الفحوص.
        _invoice(self.book, self.currency, "BOOK-1", date(2026, 6, 10))

        prepared = self._prepare()
        self.assertEqual(prepared.status_code, 201, prepared.content)
        period_id = prepared.data["period"]["id"]
        period = TaxPeriodReview.objects.get(pk=period_id)
        self.assertEqual(period.tenant_id, self.book.pk)
        self.assertEqual(prepared.data["period"]["vat"]["total_sales_vat"], "16.00")

        readiness = self.client.get(f"{TAX}/{period_id}/readiness/", **self.book_headers)
        self.assertEqual(readiness.status_code, 200, readiness.content)
        codes = {item["code"] for item in readiness.data["findings"]}
        self.assertNotIn("UNPOSTED_DOCS", codes)  # مسودة المكتب لم تتسرّب إلى فحوص العميل

        # ولا أثر لهذا التجهيز على دفتر المكتب نفسه — لا صفّ هناك أصلاً.
        self.assertEqual(TaxPeriodReview.objects.filter(tenant=self.office).count(), 0)

    def _lock_the_book(self):
        _invoice(self.book, self.currency, "BOOK-LOCK", date(2026, 6, 15))
        period_id = self._prepare().data["period"]["id"]
        approve = self.client.post(
            f"{TAX}/{period_id}/approve/", {"reauth_password": PASSWORD},
            format="json", **self.book_headers,
        )
        self.assertEqual(approve.status_code, 200, approve.content)
        submit = self.client.post(
            f"{TAX}/{period_id}/mark-submitted/",
            {"submission_reference": "VAT-57", "reauth_password": PASSWORD},
            format="json", **self.book_headers,
        )
        self.assertEqual(submit.status_code, 200, submit.content)
        self.assertEqual(submit.data["period"]["status"], "locked")

    def _expense_payload(self, tenant):
        cash = Account.objects.get(tenant=tenant, code="1101")
        electricity = Account.objects.get(tenant=tenant, code="5203")
        return {
            "date": "2026-06-15", "expense_account": electricity.pk, "amount": "50.00",
            "currency": self.currency.pk, "payment_method": "cash", "cash_or_bank_account": cash.pk,
        }

    def test_locked_period_blocks_posting_on_the_clients_book_only(self):
        self._lock_the_book()

        blocked = self.client.post(
            f"{ACC}/expense-vouchers/", self._expense_payload(self.book),
            format="json", **self.book_headers,
        )
        self.assertEqual(blocked.status_code, 400, blocked.content)

        office_headers = {"HTTP_X_TENANT_ID": str(self.office.pk)}
        allowed_on_office = self.client.post(
            f"{ACC}/expense-vouchers/", self._expense_payload(self.office),
            format="json", **office_headers,
        )
        self.assertEqual(allowed_on_office.status_code, 201, allowed_on_office.content)

        other_book = create_company("عميل آخر ٥٧", self.office_manager, managed_by=self.office)
        create_fiscal_year(other_book, 2026)
        other_headers = {"HTTP_X_TENANT_ID": str(other_book.pk)}
        allowed_on_other_book = self.client.post(
            f"{ACC}/expense-vouchers/", self._expense_payload(other_book),
            format="json", **other_headers,
        )
        self.assertEqual(allowed_on_other_book.status_code, 201, allowed_on_other_book.content)


    def test_readiness_query_count_does_not_grow_with_the_clients_invoices(self):
        """الفحوص مشتقّة ومحكومة بعددٍ ثابت — على دفتر العميل أيضاً.

        `test_m5_periods.py` يثبت الحدّ (ستّة استعلامات) على محرّك الجاهزية
        نفسه. هذا يثبته من فوق، على **دفتر عميلٍ مُدار**، لأن الطريق إليه
        اكتسب في هذه الجولة حارسَين يعملان في كل طلب: قناع القالب
        (`core.permissions.TemplateSurfacePermission`) وقراءة اشتراك الدفتر
        من مكتبه (`core/plans.py` — `_billing_tenant`). فلو أضاف أيٌّ منهما
        استعلاماً لكل صفّ لظهر هنا لا هناك.
        """
        for i in range(5):
            _invoice(self.book, self.currency, f"Q-SMALL-{i}", date(2026, 6, 3))
        period_id = self._prepare().data["period"]["id"]
        url = f"{TAX}/{period_id}/readiness/"

        self.client.get(url, **self.book_headers)  # إحماء أي كاش لكل عملية
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(url, **self.book_headers).status_code, 200)

        for i in range(200):
            _invoice(self.book, self.currency, f"Q-BIG-{i}", date(2026, 6, 4))
        with CaptureQueriesContext(connection) as big:
            self.assertEqual(self.client.get(url, **self.book_headers).status_code, 200)

        self.assertEqual(
            len(big.captured_queries), len(small.captured_queries),
            f"عدد الاستعلامات كبر مع عدد الفواتير: {len(small.captured_queries)} ⇒ "
            f"{len(big.captured_queries)}",
        )
