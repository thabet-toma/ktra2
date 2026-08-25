"""CHQ-4 — البحث والفلترة والترقيم في الخادم لا في المتصفح.

كانت `GET /cheques/` بلا أي باراميتر: الجدول كاملاً في كل فتح للشاشة، والفلترة
في الذاكرة، **ولا بحث برقم الشيك إطلاقاً** — وهو المفتاح الطبيعي للبحث في أي
نظام شيكات. الترقيم يبقى opt-in (`?page=`) فلا ينكسر مستهلكٌ يتوقع مصفوفة خام.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings
from tenants.models import Currency
from tenants.services import create_company


class ChequeListFiltersTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chq_filter", password="x")
        cls.ils = Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الفلاتر", cls.user)
        cls.other = create_company("شركة الجارة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="أحمد التاجر", partner_type="Customer")
        cls.other_customer = Partner.objects.create(
            tenant=cls.tenant, name="سعيد المقاول", partner_type="Customer")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="FLT-INV", customer=cls.customer,
            currency=cls.ils, invoice_date="2026-06-11",
            status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("5000.00"),
        )
        common = dict(currency=cls.ils, direction="Incoming",
                      sales_invoice=cls.invoice)
        Cheque.objects.create(
            tenant=cls.tenant, cheque_number="AA-1001", amount=Decimal("100.00"),
            partner=cls.customer, status="Received", bank_name="بنك فلسطين",
            due_date="2026-09-01", **common)
        Cheque.objects.create(
            tenant=cls.tenant, cheque_number="BB-2002", amount=Decimal("300.00"),
            partner=cls.other_customer, status="Under_Collection",
            bank_name="بنك القدس", due_date="2026-10-15", **common)
        Cheque.objects.create(
            tenant=cls.tenant, cheque_number="CC-3003", amount=Decimal("200.00"),
            partner=cls.customer, status="Received", bank_name="بنك الأردن",
            due_date="2026-11-20", **common)
        # ورقة شركةٍ أخرى — الفلاتر لا تنقض عزل الشركة.
        Cheque.objects.create(
            tenant=cls.other, cheque_number="AA-1001", amount=Decimal("999.00"),
            currency=cls.ils, direction="Incoming", status="Received",
            bank_name="بنك فلسطين", due_date="2026-09-01")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _numbers(self, query=""):
        resp = self.client.get(f"/api/accounting/cheques/{query}")
        self.assertEqual(resp.status_code, 200, resp.data)
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        return [r["cheque_number"] for r in rows]

    def test_search_finds_a_cheque_by_its_number(self):
        self.assertEqual(self._numbers("?search=BB-2002"), ["BB-2002"])

    def test_search_also_reaches_the_bank_and_the_partner(self):
        self.assertEqual(self._numbers("?search=القدس"), ["BB-2002"])
        self.assertEqual(sorted(self._numbers("?search=أحمد")),
                         ["AA-1001", "CC-3003"])

    def test_search_never_crosses_the_company_boundary(self):
        """الشركة الجارة لها شيك بالرقم نفسه — لا يظهر."""
        rows = self._numbers("?search=AA-1001")
        self.assertEqual(rows, ["AA-1001"])
        resp = self.client.get("/api/accounting/cheques/?search=AA-1001")
        data = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(Decimal(data[0]["amount"]), Decimal("100.00"),
                         "ظهر شيك الشركة الأخرى")

    def test_status_and_partner_and_due_range_filter_on_the_server(self):
        self.assertEqual(self._numbers("?status=Under_Collection"), ["BB-2002"])
        self.assertEqual(sorted(self._numbers(f"?partner={self.customer.id}")),
                         ["AA-1001", "CC-3003"])
        self.assertEqual(
            sorted(self._numbers("?due_from=2026-10-01&due_to=2026-12-31")),
            ["BB-2002", "CC-3003"])

    def test_ordering_is_a_whitelist_and_a_bad_value_falls_back(self):
        self.assertEqual(self._numbers("?ordering=amount"),
                         ["AA-1001", "CC-3003", "BB-2002"])
        self.assertEqual(self._numbers("?ordering=-amount"),
                         ["BB-2002", "CC-3003", "AA-1001"])
        # قيمة غير مسموحة لا تكسر الطلب ولا تصل `order_by`.
        self.assertEqual(self._numbers("?ordering=tenant__CompanyName"),
                         self._numbers())

    def test_pagination_stays_opt_in(self):
        raw = self.client.get("/api/accounting/cheques/")
        self.assertIsInstance(raw.data, list, "الترقيم صار إلزامياً بلا ?page=")

        paged = self.client.get("/api/accounting/cheques/?page=1&page_size=2")
        self.assertEqual(paged.data["count"], 3)
        self.assertEqual(len(paged.data["results"]), 2)

    def test_filters_and_pagination_compose(self):
        resp = self.client.get(
            f"/api/accounting/cheques/?partner={self.customer.id}&page=1&page_size=1")
        self.assertEqual(resp.data["count"], 2, "العدّ حُسب قبل الفلترة")
        self.assertEqual(len(resp.data["results"]), 1)
