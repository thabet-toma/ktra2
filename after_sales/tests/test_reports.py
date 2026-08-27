"""THA-24 م5 — تقارير ما بعد البيع: البوابة، والنطاق، وصدق الأرقام.

يثبت:
  1. التقارير الثلاثة **غير موجودة** (404) لشركةٍ بلا ترخيص — لا 403 يكشفها،
     ولا تظهر في الفهرس أصلاً.
  2. كل تقرير محصور بشركته.
  3. «تنتهي قريباً» نافذة تصرّف: المنتهية خارجها، وما بعد النافذة خارجها.
  4. «المفتوحة» تستثني المُسلَّم والملغى وتقيس العمر بالأيام.
  5. كلفة الكفالة تُقرأ من حركات `SERVICE_ISSUE` بتكلفتها التاريخية، والإجمالي
     يُحسب على الصفوف كاملةً قبل أي قصّ.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from after_sales.models import ServiceOrder, WarrantyCard
from core.models import TenantModule
from core.reports import REPORTS, run_report
from inventory.models import Product, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

KEYS = [
    "after-sales-warranties-expiring",
    "after-sales-open-orders",
    "after-sales-warranty-cost",
]

ORDERS = "/api/after-sales/service-orders/"


class AfterSalesReportsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="rep", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة التقارير", cls.user)
        create_fiscal_year(cls.tenant, timezone.localdate().year)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier",
            linked_account=Account.objects.get(tenant=cls.tenant, code="2101"),
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون التقارير", partner_type="Customer",
            phone="0599777888",
        )
        inv_acc = Account.objects.create(
            tenant=cls.tenant, code="1104-RP", name="مخزون", account_type="Asset",
            is_active=True,
        )
        settings_row = get_or_create_sales_settings(cls.tenant)
        settings_row.default_inventory_account = inv_acc
        settings_row.save()
        get_or_create_purchase_settings(cls.tenant)

    def setUp(self):
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="after_sales", enabled=True,
        )
        self.today = timezone.localdate()
        self.client.force_authenticate(user=self.user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def card(self, serial, *, ends_in_days, tenant=None):
        end = self.today + datetime.timedelta(days=ends_in_days)
        return WarrantyCard.objects.create(
            tenant=tenant or self.tenant, serial=serial, device_name="جهاز",
            partner=self.customer if tenant is None else None,
            customer_phone="0599777888",
            start_date=end - datetime.timedelta(days=365), duration_months=12,
            end_date=end, source=WarrantyCard.SOURCE_MANUAL,
        )

    def order(self, *, status=ServiceOrder.STATUS_RECEIVED, age_days=0, tenant=None):
        return ServiceOrder.objects.create(
            tenant=tenant or self.tenant,
            order_number=f"SO-{ServiceOrder.objects.count() + 1}",
            order_date=self.today - datetime.timedelta(days=age_days),
            partner=self.customer if tenant is None else None,
            customer_name="زبون", serial="RP-1", device_description="جهاز",
            status=status,
        )

    def run_spec(self, key, **params):
        return run_report(key, self.tenant.TenantID, params)

    # ── البوابة ────────────────────────────────────────────────────────
    def test_every_report_is_404_without_a_module_license(self):
        self.card("GATE-1", ends_in_days=10)
        self.license.delete()

        for key in KEYS:
            with self.subTest(report=key):
                response = self.client.get(f"/api/reports/{key}/", **self.headers())
                self.assertEqual(response.status_code, 404, response.content)

    def test_reports_vanish_from_the_catalog_without_a_license(self):
        with_license = self.client.get("/api/reports/", **self.headers()).data
        self.license.delete()
        without = self.client.get("/api/reports/", **self.headers()).data

        def keys_of(payload):
            return {
                report["key"]
                for category in payload["categories"]
                for report in category["reports"]
            }

        self.assertTrue(set(KEYS) <= keys_of(with_license))
        self.assertEqual(set(KEYS) & keys_of(without), set())

    def test_a_licensed_company_reaches_every_report(self):
        for key in KEYS:
            with self.subTest(report=key):
                response = self.client.get(f"/api/reports/{key}/", **self.headers())
                self.assertEqual(response.status_code, 200, response.content)
                self.assertIn("rows", response.data)
                self.assertIn("totals", response.data)

    # ── كفالات تنتهي قريباً ────────────────────────────────────────────
    def test_expiring_window_excludes_the_already_expired_and_the_far_future(self):
        self.card("SOON-1", ends_in_days=5)
        self.card("EDGE-30", ends_in_days=30)
        self.card("FAR-90", ends_in_days=90)
        self.card("GONE-1", ends_in_days=-3)

        payload = self.run_spec("after-sales-warranties-expiring")

        serials = [row["serial"] for row in payload["rows"]]
        self.assertEqual(serials, ["SOON-1", "EDGE-30"])
        self.assertEqual(payload["rows"][0]["days_remaining"], 5)
        self.assertEqual(payload["rows"][0]["customer"], "زبون التقارير")

    def test_the_window_is_a_parameter_not_a_constant(self):
        self.card("SOON-1", ends_in_days=5)
        self.card("FAR-90", ends_in_days=90)

        wide = self.run_spec("after-sales-warranties-expiring", days="120")

        self.assertEqual([row["serial"] for row in wide["rows"]], ["SOON-1", "FAR-90"])

    # ── أوامر مفتوحة ───────────────────────────────────────────────────
    def test_open_orders_exclude_delivered_and_cancelled_and_measure_age(self):
        self.order(age_days=12)
        self.order(status=ServiceOrder.STATUS_DELIVERED, age_days=3)
        self.order(status=ServiceOrder.STATUS_CANCELLED, age_days=4)

        payload = self.run_spec("after-sales-open-orders")

        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["age_days"], 12)
        self.assertEqual(payload["rows"][0]["billing"], "لم يُحسم")

    def test_open_orders_can_be_narrowed_to_one_status(self):
        self.order(status=ServiceOrder.STATUS_RECEIVED)
        self.order(status=ServiceOrder.STATUS_IN_REPAIR)

        payload = self.run_spec("after-sales-open-orders", status=ServiceOrder.STATUS_IN_REPAIR)

        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["status"], "قيد الإصلاح")

    # ── كلفة قطع الكفالة ───────────────────────────────────────────────
    def test_warranty_cost_reads_the_historic_cost_of_service_issue_movements(self):
        product = Product.objects.create(
            tenant=self.tenant, sku="RP-PART", name_ar="قطعة",
        )
        # المخزون يدخل بفاتورة شراء مرحّلة — رصيدٌ مزروع لا حركة له يكذب.
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="RP-P1", partner=self.supplier,
            currency=self.ils, invoice_date=self.today, exchange_rate=Decimal("1"),
            grand_total=Decimal("400"),
        )
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=product, name="قطعة", quantity=Decimal("10"),
            unit_price=Decimal("40"), total_price=Decimal("400"),
        )
        self.assertEqual(
            self.client.post(
                f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
                {}, format="json", **self.headers(),
            ).status_code,
            201,
        )

        order = self.order()
        self.client.post(
            f"{ORDERS}{order.pk}/parts/",
            {"product": product.pk, "quantity": "3", "billing": "covered"},
            format="json", **self.headers(),
        )
        posted = self.client.post(
            f"{ORDERS}{order.pk}/post-covered/", {}, format="json", **self.headers(),
        )
        self.assertEqual(posted.status_code, 200, posted.content)

        payload = self.run_spec("after-sales-warranty-cost")

        self.assertEqual(len(payload["rows"]), 1)
        row = payload["rows"][0]
        self.assertEqual(row["order_number"], order.order_number)
        self.assertEqual(row["total_cost"], "120.00")
        self.assertEqual(row["unit_cost"], "40.00")
        # الإجمالي يُحسب على الصفوف كاملةً — عمودان موسومان total.
        self.assertEqual(payload["totals"]["total_cost"], "120.00")
        self.assertEqual(payload["totals"]["quantity"], "3")

    def test_warranty_cost_ignores_ordinary_sales_movements(self):
        """النوع هو الفاصل: حركة بيع لا تدخل هذا التقرير مهما تشابه معرّفها."""
        from inventory.services import record_stock_movement

        product = Product.objects.create(
            tenant=self.tenant, sku="RP-SALE", name_ar="منتج مبيع",
            quantity_on_hand=Decimal("10"), avg_cost=Decimal("7"),
        )
        record_stock_movement(
            product=product, movement_type="OUT", quantity=Decimal("2"),
            reference_type="SALE", reference_id=1, movement_date=self.today,
            tenant=self.tenant,
        )

        payload = self.run_spec("after-sales-warranty-cost")

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["totals"]["total_cost"], "0.00")

    # ── العزل ──────────────────────────────────────────────────────────
    def test_every_report_is_scoped_to_the_active_company(self):
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        self.card("OTHER-1", ends_in_days=10, tenant=other)
        self.order(tenant=other)
        self.card("MINE-1", ends_in_days=10)
        self.order()

        expiring = self.run_spec("after-sales-warranties-expiring")
        open_orders = self.run_spec("after-sales-open-orders")

        self.assertEqual([row["serial"] for row in expiring["rows"]], ["MINE-1"])
        self.assertEqual(len(open_orders["rows"]), 1)
        self.assertEqual(open_orders["rows"][0]["customer"], "زبون التقارير")

    def test_the_three_reports_are_registered_under_their_own_category(self):
        for key in KEYS:
            with self.subTest(report=key):
                spec = REPORTS[key]
                self.assertEqual(spec.category, "after_sales")
                self.assertEqual(spec.module, "after_sales")
                self.assertTrue(spec.permission.startswith("aftersales."))
