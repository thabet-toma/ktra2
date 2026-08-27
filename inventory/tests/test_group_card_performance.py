"""الكرت المجمّع: عدد الاستعلامات ثابت مهما كبر عدد المنتجات (كان N+1).

«منتجات عامة» في شركة الجرابعه = 1490 منتجاً ⇒ الكرت المجمّع كان يطلق ~10 آلاف
استعلام (7 لكل منتج) فتنتهي مهلة الخادم (30 ثانية) وتظهر الشاشة خربانة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from accounting.services import create_fiscal_year
from inventory.models import Product
from inventory.services import product_group_profile, product_linked_invoices
from tenants.models import Currency
from tenants.services import create_company


class GroupCardQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="grpperf", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الكرت المجمّع", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.products = [
            Product.objects.create(
                tenant=cls.tenant, sku=f"SKU-{i}", name_ar=f"منتج {i}",
                quantity_on_hand=Decimal("10"), avg_cost=Decimal("5"),
            )
            for i in range(25)
        ]

    def test_profile_query_count_does_not_grow_with_members(self):
        ids = [p.id for p in self.products]
        with self.assertNumQueries(3):
            product_group_profile(tenant_id=self.tenant.pk, product_ids=ids[:5])
        with self.assertNumQueries(3):
            product_group_profile(tenant_id=self.tenant.pk, product_ids=ids)

    def test_profile_totals_stay_correct(self):
        ids = [p.id for p in self.products]
        res = product_group_profile(tenant_id=self.tenant.pk, product_ids=ids)
        self.assertEqual(res["member_count"], 25)
        self.assertEqual(Decimal(res["quantity_on_hand"]), Decimal("250"))
        # 25 منتجاً × (10 × 5)
        self.assertEqual(Decimal(res["inventory_valuation"]), Decimal("1250.00"))
        self.assertEqual(res["members"][0]["avg_cost"], "5.0000")

    def test_linked_invoices_dedupes_in_sql_with_flat_query_count(self):
        """فاتورة واحدة بعدة أسطر ⇒ سطر واحد، وبعدد استعلامات ثابت.

        القراءة القديمة كانت تسحب كل أسطر كل فاتورة ثم تُسقط المكرر في بايثون.
        """
        from partners.models import Partner
        from logistics.models import PurchaseInvoice

        supplier = Partner.objects.create(
            tenant=self.tenant, name="مورد", partner_type="Supplier")
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-G1", partner=supplier,
            currency=self.ils, invoice_date="2026-06-20", is_posted=True,
        )
        for p in self.products[:10]:
            invoice.items.create(
                product=p, name=p.name_ar, quantity=Decimal("1"),
                unit_price=Decimal("5"), total_price=Decimal("5"),
            )
        ids = [p.id for p in self.products]
        with self.assertNumQueries(3):
            rows = product_linked_invoices(tenant_id=self.tenant.pk, product_ids=ids)
        self.assertEqual(
            [r["document_number"] for r in rows if r["document_type"] == "PURCHASE_INVOICE"],
            ["INV-G1"],
        )
