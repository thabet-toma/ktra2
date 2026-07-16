"""W11/M4 — قائمة القيود: ملخّص المرجع لفواتير المبيعات/تحصيلات العملاء مُجمَّع (بلا N+1).

قبل الإصلاح: كل صف SALES_INVOICE/CUSTOMER_PAYMENT كان يُطلق استعلاماً مفرداً في
`build_journal_reference_summary` ⇒ عدد الاستعلامات يزيد مع عدد القيود. الآن يُبنى
map واحد من صفوف الصفحة (نمط pay_map) ⇒ عدد الاستعلامات ثابت مهما زاد عدد القيود.
"""
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import JournalHeader
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company


class JournalReferenceSummaryQueryCountTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="refperf", password="x")
        cls.tenant = create_company("شركة أداء المرجع", cls.owner)
        cls.cur = (Currency.objects.filter(IsBaseCurrency=True).first()
                   or Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True))
        cls.cust = Partner.objects.create(tenant=cls.tenant, name="عميل", partner_type="Customer")

    def _add_sales_ref_journals(self, prefix, n):
        for i in range(n):
            inv = SalesInvoice.objects.create(
                tenant=self.tenant, invoice_number=f"SI-{prefix}-{i}", customer=self.cust,
                currency=self.cur, invoice_date="2026-06-15",
            )
            JournalHeader.objects.create(
                tenant=self.tenant, transaction_date="2026-06-15",
                description=f"قيد {prefix}{i}",
                reference_type="SALES_INVOICE", reference_id=inv.id,
            )

    def _list_query_count(self):
        self.client.force_authenticate(user=self.owner)
        with CaptureQueriesContext(connection) as ctx:
            res = self.client.get(
                "/api/accounting/journals/", HTTP_X_TENANT_ID=str(self.tenant.TenantID))
            assert res.status_code == 200, res.content[:200]
        return len(ctx.captured_queries)

    def test_sales_reference_summary_query_count_is_constant(self):
        self._add_sales_ref_journals("a", 2)
        q_small = self._list_query_count()
        self._add_sales_ref_journals("b", 4)  # الآن 6 قيود مرجعها فواتير مبيعات
        q_large = self._list_query_count()
        # عدد الاستعلامات لا يتأثر بعدد القيود (batched) — قبل الإصلاح كان q_large > q_small.
        assert q_large == q_small, (
            f"N+1 لم يُحلّ: {q_small} استعلام لـ2 قيد مقابل {q_large} لـ6 قيود")
