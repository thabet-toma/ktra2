"""دفترُ اليومية يسمّي المرتجعَ باسمه — بلاغُ المالك الثاني في #214-ب.

**البلاغ حرفيّاً:** «المرتجع … لمّا أضغط عليه بتبيّن كلمة فاتورة مبيعات بالعنوان».

ودفترُ اليومية آخرُ السطوح المالية الثلاثة التي كانت تقرأ الاسمَ من نوع المرجع
وحدَه: قيدُ مرتجع البيع يُكتب بـ`reference_type="SALES_INVOICE"` **كالبيعة حرفاً**
لأنّ المرتجع فعلاً صفُّ `SalesInvoice` بنوعٍ آخر.

**ولم يُلمَس القيد:** تغييرُ `reference_type` يمسّ مفتاحَ الـidempotency الذي
يبني عليه فكُّ الترحيل وسلّةُ المحذوفات. فالنوعُ الحقيقيُّ يُرسَل بجانبه، مقروءاً
من الخريطة التي تبنيها القائمةُ أصلاً — **بلا استعلامٍ إضافيّ**.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import JournalHeader
from core.terminology import term as tenant_term
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency
from tenants.services import create_company


class JournalReturnNamingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="jrnl_kind", password="x")
        cls.tenant = create_company("شركة تسمية قيد المرتجع", cls.owner)
        cls.cur = (Currency.objects.filter(IsBaseCurrency=True).first()
                   or Currency.objects.create(
                       Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True))
        cls.cust = Partner.objects.create(
            tenant=cls.tenant, name="عميل الدفتر", partner_type="Customer")

    def _invoice(self, number, *, kind, original=None):
        return SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.cust,
            currency=self.cur, invoice_date="2026-06-15",
            grand_total=Decimal("100"), invoice_kind=kind, original_invoice=original)

    def _journal(self, *, reference_type, reference_id, description="قيد"):
        return JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-06-15", description=description,
            reference_type=reference_type, reference_id=reference_id)

    def _rows(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            "/api/accounting/journals/", HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        self.assertEqual(response.status_code, 200, response.content[:200])
        data = response.data
        return data["results"] if isinstance(data, dict) and "results" in data else data

    def _by_description(self):
        return {row["description"]: row for row in self._rows()}

    def test_the_journal_tells_a_return_apart_from_a_sale(self):
        """قلبُ البلاغ: قيدان بنفس `reference_type` ويجب أن يُقرآ مستندَين."""
        sale = self._invoice("SI-J1", kind=SalesInvoice.INVOICE_KIND_SALE)
        ret = self._invoice("SR-J1", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
                            original=sale)
        self._journal(reference_type="SALES_INVOICE", reference_id=sale.id,
                      description="قيد البيعة")
        self._journal(reference_type="SALES_INVOICE", reference_id=ret.id,
                      description="قيد المرتجع")

        rows = self._by_description()
        # الحقلُ الذي كانت الواجهةُ عمياءَ بدونه — والنوعان متطابقان فيه سلفاً.
        self.assertEqual(rows["قيد البيعة"]["reference_type"],
                         rows["قيد المرتجع"]["reference_type"])
        self.assertEqual(rows["قيد المرتجع"]["reference_kind"], "sale_return")
        self.assertEqual(rows["قيد المرتجع"]["source_label"], "مرتجع بيع")
        # والملخّصُ أيضاً: كان يكتب «فاتورة مبيعات SR-J1» على المرتجع.
        self.assertIn("مرتجع بيع", rows["قيد المرتجع"]["reference_summary"])
        self.assertNotIn(tenant_term(self.tenant, "doc.sales_invoice"),
                         rows["قيد المرتجع"]["reference_summary"])

    def test_an_ordinary_sale_keeps_the_name_its_company_chose(self):
        """الاسمُ يتبدّل بقالب الشركة (ISSUE #82) — والتفرقةُ يجب ألّا تخطفه.

        علاجٌ يسمّي كلَّ قيدٍ من عنده يكسر مكتبَ المحاسبة حيث اسمُها «فاتورة
        أتعاب»، فيُصلح شكوىً ويفتح أخرى.
        """
        sale = self._invoice("SI-J2", kind=SalesInvoice.INVOICE_KIND_SALE)
        self._journal(reference_type="SALES_INVOICE", reference_id=sale.id,
                      description="قيد بيعةٍ عاديّة")
        row = self._by_description()["قيد بيعةٍ عاديّة"]
        self.assertEqual(row["source_label"], tenant_term(self.tenant, "doc.sales_invoice"))
        self.assertEqual(row["reference_kind"], "sale")

    def test_every_row_carries_the_field_even_when_it_has_no_kind(self):
        """حقلٌ يظهر أحياناً يجعل الواجهةَ تخمّن غيابَه — يُرسَل دائماً ولو `None`."""
        self._journal(reference_type="MANUAL", reference_id=None,
                      description="قيدٌ يدويّ")
        row = self._by_description()["قيدٌ يدويّ"]
        self.assertIn("reference_kind", row)
        self.assertIsNone(row["reference_kind"])

    def test_a_purchase_return_is_not_shown_as_a_raw_identifier(self):
        """`PURCHASE_RETURN` نوعُ مرجعٍ منشورٌ منذ مرتجع الشراء ولم يُسجَّل في أيّ
        خريطة أسماء، فكان المحاسبُ العربيُّ يقرأ المعرِّفَ الإنجليزيَّ خاماً."""
        self._journal(reference_type="PURCHASE_RETURN", reference_id=77,
                      description="قيد مرتجع الشراء")
        row = self._by_description()["قيد مرتجع الشراء"]
        self.assertEqual(row["source_label"], "مرتجع شراء")
        self.assertNotIn("PURCHASE_RETURN", row["reference_summary"])
        self.assertIn("مرتجع شراء", row["reference_summary"])

    def test_naming_the_return_costs_no_extra_query(self):
        """التسميةُ تقرأ الخريطةَ التي تبنيها القائمةُ أصلاً. ولو سُئل المستندُ
        لكلّ صفّ لصار الدفترُ يبطؤ كلّما كبر — وهو أكثرُ الشاشات صفوفاً."""
        def add(prefix, count):
            for i in range(count):
                ret = self._invoice(f"SR-{prefix}-{i}",
                                    kind=SalesInvoice.INVOICE_KIND_SALE_RETURN)
                self._journal(reference_type="SALES_INVOICE", reference_id=ret.id,
                              description=f"مرتجع {prefix}{i}")

        def count_queries():
            self.client.force_authenticate(user=self.owner)
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(
                    "/api/accounting/journals/",
                    HTTP_X_TENANT_ID=str(self.tenant.TenantID))
                self.assertEqual(response.status_code, 200)
            return len(ctx.captured_queries)

        add("a", 2)
        small = count_queries()
        add("b", 4)
        large = count_queries()
        self.assertEqual(large, small, f"N+1: {small} استعلاماً لقيدين مقابل {large} لستّة")
