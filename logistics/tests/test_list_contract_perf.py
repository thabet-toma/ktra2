import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine
from inventory.models import Product
from logistics.models import (
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsPayment,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    LogisticsShipment,
    LogisticsShipmentDeal,
)
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class LogisticsListContractPerformanceTest(TestCase):
    """Regression coverage for light, tenant-safe deal/shipment list contracts."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=970, CompanyName="List Perf")
        cls.other_tenant = Tenant.objects.create(TenantID=971, CompanyName="Other List Perf")
        cls.currency = Currency.objects.create(Code="LPF", Symbol="$", IsBaseCurrency=False)
        cls.user = User.objects.create_user(username="list_perf", password="x")
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role="manager")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.other_tenant, role="manager"
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="Fast Supplier", legal_name="Fast Supplier LLC",
            partner_type="Supplier",
        )
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="Fast Forwarder", partner_type="FreightForwarder"
        )
        cls.other_partner = Partner.objects.create(
            tenant=cls.other_tenant, name="Hidden Supplier", partner_type="Supplier"
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PERF-1", name_ar="منتج البحث التاريخي"
        )
        cls.deals = []
        cls.shipments = []
        cls.purchase_invoices = []
        for idx in range(8):
            deal = LogisticsDeal.objects.create(
                tenant=cls.tenant,
                ref_number=f"D-PERF-{idx:02d}",
                partner=cls.partner,
                order_date=f"2026-06-{idx + 1:02d}",
                currency=cls.currency,
                total_amount=100 + idx,
                remaining_amount=100 + idx,
                description=f"Performance deal {idx}",
                factory_name=f"Factory {idx}",
            )
            LogisticsDealItem.objects.create(
                deal=deal, product=cls.product, quantity=1, unit_price=100 + idx
            )
            LogisticsPayment.objects.create(deal=deal, amount=10, payment_number=1)
            shipment = LogisticsShipment.objects.create(
                tenant=cls.tenant,
                shipment_number=f"SH-PERF-{idx:02d}",
                shipping_agent=cls.agent,
                shipment_name=f"Performance shipment {idx}",
                departure_date=f"2026-06-{idx + 1:02d}",
                shipping_type="air" if idx % 2 else "sea",
                total_shipping_cost_usd=100,
            )
            LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
            LogisticsPayment.objects.create(shipment=shipment, amount=10, payment_number=1)
            cls.deals.append(deal)
            cls.shipments.append(shipment)
            invoice = PurchaseInvoice.objects.create(
                tenant=cls.tenant,
                invoice_number=f"PI-PERF-{idx:02d}",
                invoice_name=f"Historical purchase {idx}",
                invoice_date=f"2026-05-{idx + 1:02d}",
                partner=cls.partner,
                currency=cls.currency,
                grand_total=200 + idx,
                is_posted=idx % 2 == 0,
                is_return=idx == 7,
            )
            PurchaseInvoiceItem.objects.create(
                invoice=invoice, product=cls.product, name=cls.product.name_ar,
                quantity=1, unit_price=200 + idx, total_price=200 + idx,
            )
            cls.purchase_invoices.append(invoice)

        cls.hidden_deal = LogisticsDeal.objects.create(
            tenant=cls.other_tenant,
            ref_number="D-HIDDEN",
            partner=cls.other_partner,
            order_date="2026-06-01",
            currency=cls.currency,
            total_amount=999,
        )
        cls.hidden_shipment = LogisticsShipment.objects.create(
            tenant=cls.other_tenant, shipment_number="SH-HIDDEN"
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _get_with_query_count(self, path):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.content)
        return response, len(captured)

    def test_deal_list_is_light_paginated_searchable_and_constant_query_count(self):
        response, query_count = self._get_with_query_count(
            "/api/logistics/deals/?page=1&page_size=2"
        )
        self.assertEqual(response.data["count"], 8)
        # 7: أضيف prefetch لـ purchase_invoices (رابط «تحولت إلى فاتورة») ثم
        # استعلام رصيد المورد المجمَّع لأطراف الصفحة (`PagePartnerBalanceMixin`)
        # الذي حلّ محلّ استعلام فرعي مرتبط كان يُنفَّذ لكل صف. كلاهما استعلام
        # ثابت واحد لكل الصفحة لا N+1، تحرسه assertion ثبات العدد أدناه.
        self.assertLessEqual(query_count, 7)
        _, large_query_count = self._get_with_query_count(
            "/api/logistics/deals/?page=1&page_size=8"
        )
        self.assertEqual(large_query_count, query_count)
        row = response.data["results"][0]
        self.assertNotIn("items", row)
        self.assertNotIn("payments", row)
        self.assertNotIn("quote_images", row)
        self.assertIn("linked_shipment", row)
        self.assertNotIn(self.hidden_deal.id, [r["id"] for r in response.data["results"]])

        searched = self.client.get("/api/logistics/deals/?page=1&search=البحث التاريخي")
        self.assertEqual(searched.status_code, 200, searched.content)
        self.assertEqual(searched.data["count"], 8)

        detail = self.client.get(f"/api/logistics/deals/{self.deals[0].id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertIn("items", detail.data)
        self.assertIn("payments", detail.data)

    def test_shipment_list_is_light_paginated_filterable_and_constant_query_count(self):
        response, query_count = self._get_with_query_count(
            "/api/logistics/shipments/?page=1&page_size=2"
        )
        self.assertEqual(response.data["count"], 8)
        self.assertLessEqual(query_count, 4)
        _, large_query_count = self._get_with_query_count(
            "/api/logistics/shipments/?page=1&page_size=8"
        )
        self.assertEqual(large_query_count, query_count)
        row = response.data["results"][0]
        self.assertNotIn("deals", row)
        self.assertNotIn("payments", row)
        self.assertNotIn("shipment_deal_allocations", row)
        self.assertEqual(row["deals_count"], 1)
        self.assertEqual(row["payments_count"], 1)
        self.assertNotIn(self.hidden_shipment.id, [r["id"] for r in response.data["results"]])

        filtered = self.client.get(
            "/api/logistics/shipments/?page=1&search=shipment%207&shipping_type=air"
        )
        self.assertEqual(filtered.status_code, 200, filtered.content)
        self.assertEqual(filtered.data["count"], 1)

        detail = self.client.get(f"/api/logistics/shipments/{self.shipments[0].id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertIn("deals", detail.data)
        self.assertIn("payments", detail.data)
        self.assertIn("shipment_deal_allocations", detail.data)

    def test_light_payload_is_materially_smaller_than_detail_payload(self):
        deal_list = self.client.get("/api/logistics/deals/?page=1&page_size=1")
        deal_detail = self.client.get(f"/api/logistics/deals/{self.deals[-1].id}/")
        shipment_list = self.client.get("/api/logistics/shipments/?page=1&page_size=1")
        shipment_detail = self.client.get(
            f"/api/logistics/shipments/{self.shipments[-1].id}/"
        )
        deal_list_bytes = len(json.dumps(deal_list.data, default=str).encode())
        deal_detail_bytes = len(json.dumps(deal_detail.data, default=str).encode())
        shipment_list_bytes = len(json.dumps(shipment_list.data, default=str).encode())
        shipment_detail_bytes = len(json.dumps(shipment_detail.data, default=str).encode())
        self.assertLess(deal_list_bytes, deal_detail_bytes)
        self.assertLess(shipment_list_bytes, shipment_detail_bytes)

    def test_purchase_invoice_list_filters_before_pagination_without_loading_items(self):
        response, query_count = self._get_with_query_count(
            "/api/logistics/purchase-invoices/?page=1&page_size=2&invoice_type=local"
        )
        self.assertEqual(response.data["count"], 8)
        self.assertLessEqual(query_count, 5)
        _, large_query_count = self._get_with_query_count(
            "/api/logistics/purchase-invoices/?page=1&page_size=8&invoice_type=local"
        )
        self.assertEqual(large_query_count, query_count)
        row = response.data["results"][0]
        self.assertEqual(row["items_count"], 1)
        self.assertNotIn("items", row)

        searched = self.client.get(
            "/api/logistics/purchase-invoices/?page=1&search=Historical%20purchase%203"
        )
        self.assertEqual(searched.data["count"], 1)
        posted = self.client.get(
            "/api/logistics/purchase-invoices/?page=1&is_posted=true"
        )
        self.assertEqual(posted.data["count"], 4)
        returned = self.client.get(
            "/api/logistics/purchase-invoices/?page=1&is_return=true"
        )
        self.assertEqual(returned.data["count"], 1)

        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{self.purchase_invoices[0].id}/"
        )
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(len(detail.data["items"]), 1)

    def test_purchase_invoice_list_count_query_stays_flat(self):
        """عدّ الترقيم يجب أن يبقى COUNT بسيطاً بلا GROUP BY.

        أي تجميعة على مستوى الصفّ (`Count('items')` سابقاً) تفرض GROUP BY فيمنع
        جانغو من تقليم التعليقات في استعلام العدّ، فتُنفَّذ استعلامات ملخّص الدفع
        الفرعية لكل صفّ لا لصفوف الصفحة — قِيست 14 ثانية للعدّ وحده على مستأجر
        بـ1,261 فاتورة، فتجاوزت مهلة قراءة MySQL (30 ثانية) وردّت 500.
        """
        empty_invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number="PI-PERF-EMPTY",
            invoice_name="Empty lines purchase",
            invoice_date="2026-05-20",
            partner=self.partner,
            currency=self.currency,
            grand_total=0,
        )

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(
                "/api/logistics/purchase-invoices/?page=1&page_size=2&invoice_type=local"
            )
        self.assertEqual(response.status_code, 200, response.content)
        count_queries = [
            q["sql"] for q in captured if q["sql"].lstrip().startswith("SELECT COUNT(*)")
        ]
        self.assertEqual(len(count_queries), 1, count_queries)
        self.assertNotIn("GROUP BY", count_queries[0].upper(), count_queries[0])

        empty_row = self.client.get(
            "/api/logistics/purchase-invoices/?page=1&search=Empty%20lines%20purchase"
        ).data["results"][0]
        self.assertEqual(empty_row["id"], empty_invoice.id)
        # الاستعلام الفرعي يُرجع NULL لفاتورة بلا بنود — الـCoalesce يبقيها 0.
        self.assertEqual(empty_row["items_count"], 0)

    def test_purchase_invoice_list_exposes_linked_payment_summary_and_supplier_balance(self):
        partial = self.purchase_invoices[0]
        paid = self.purchase_invoices[1]
        cash = Account.objects.create(
            tenant=self.tenant, code="CASH-PI-LIST", name="صندوق القائمة",
            account_type="Asset", is_active=True,
        )
        payable = Account.objects.create(
            tenant=self.tenant, code="AP-PI-LIST", name="ذمم مورد القائمة",
            account_type="Liability", is_active=True,
        )
        journal = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-07-20",
            description="رصيد مورد القائمة", is_posted=True,
        )
        JournalLine.objects.create(
            tenant=self.tenant, journal=journal, account=payable,
            partner=self.partner, debit=0, credit=450,
            base_debit=0, base_credit=450,
        )
        from sales.models import SupplierPayment
        SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.partner, purchase_invoice=partial,
            payment_date="2026-07-20", amount=50, currency=self.currency,
            cash_or_bank_account=cash, is_posted=True,
        )
        SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.partner, purchase_invoice=paid,
            payment_date="2026-07-20", amount=paid.grand_total, currency=self.currency,
            cash_or_bank_account=cash, is_posted=True,
        )

        partial_response = self.client.get(
            "/api/logistics/purchase-invoices/?page=1&payment_status=partially_paid"
        )
        self.assertEqual(partial_response.status_code, 200, partial_response.content)
        self.assertEqual(partial_response.data["count"], 1)
        row = partial_response.data["results"][0]
        self.assertEqual(row["partner_name"], "Fast Supplier")
        self.assertEqual(row["payment_status"], "partially_paid")
        self.assertEqual(row["payment_status_display"], "مدفوعة جزئياً")
        self.assertEqual(Decimal(row["amount_paid"]), Decimal("50.00"))
        self.assertEqual(Decimal(row["remaining_balance"]), Decimal("150.00"))
        self.assertEqual(Decimal(row["supplier_balance"]), Decimal("450.00"))

        paid_response = self.client.get(
            "/api/logistics/purchase-invoices/?page=1&payment_status=paid"
        )
        self.assertEqual(paid_response.data["count"], 1)
        self.assertEqual(paid_response.data["results"][0]["id"], paid.id)
