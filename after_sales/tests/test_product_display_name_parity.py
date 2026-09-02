"""#41 — اسم المنتج المعروض يحمل براندَه: الكفالة، أمر الصيانة، وتقاريرهما.

نفس السياق القاطع: أخوان تحت أبٍ واحد ببراندين مختلفين. القرارات الملزمة
#37/#38/#39/#40 لا تُعاد. المنتج الغائب هنا **حالة مشروعة** (جهازٌ لا يقابله
صنفٌ في الكتالوج) — الاحتياط `device_name`/`device_description` يبقى حرفاً بحرف.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from after_sales.models import ServiceOrder, ServiceOrderEvent, ServiceOrderPart, WarrantyCard
from after_sales.serializers import (
    ServiceOrderListSerializer,
    ServiceOrderPartSerializer,
    ServiceOrderSerializer,
    WarrantyCardSerializer,
)
from core.models import TenantModule
from core.reports import run_report
from inventory.models import Product
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"
WARRANTIES = "/api/after-sales/warranties/"
ORDERS = "/api/after-sales/service-orders/"


class AfterSalesProductDisplayNameParityTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="apdnp", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة تناظر ما بعد البيع", cls.user)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون التناظر", partner_type="Customer",
            phone="0599123456")

    def setUp(self):
        TenantModule.objects.create(
            tenant=self.tenant, module_key="after_sales", enabled=True)
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _register(self, name):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": name}, format="json", **self.headers)
        assert res.status_code == 201, res.content[:300]
        return res.json()

    def _add_brand(self, family_id, brand):
        res = self.client.post(
            f"{PRODUCTS_URL}add-brand/", {"family_id": family_id, "brand": brand},
            format="json", **self.headers,
        )
        assert res.status_code in (200, 201), res.content[:300]
        return res.json()

    def _siblings(self, size, brand_a, brand_b):
        first = self._register(size)
        family_id = Product.objects.get(pk=first["id"]).family_id
        named = self._add_brand(family_id, brand_a)
        second = self._add_brand(family_id, brand_b)
        return (Product.objects.get(pk=named["id"]), Product.objects.get(pk=second["id"]))

    # ── 1) after_sales/serializers.py — WarrantyCardSerializer ──

    def test_warranty_card_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("جهاز صوت 5.1", "سوني", "بايونير")
        for p in (p1, p2):
            res = self.client.post(
                WARRANTIES,
                {"product": p.pk, "partner": self.customer.pk,
                 "start_date": "2026-06-01", "duration_months": 12},
                format="json", **self.headers)
            self.assertEqual(res.status_code, 201, res.content)

        rows = self.client.get(WARRANTIES, **self.headers).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        names = {r["product"]: r["product_name"] for r in rows}
        self.assertNotEqual(names[p1.pk], names[p2.pk])
        self.assertIn("سوني", names[p1.pk])
        self.assertIn("بايونير", names[p2.pk])

    def test_warranty_card_falls_back_to_device_name_when_product_is_absent(self):
        """المنتج الغائب حالةٌ مشروعة هنا (جهازٌ خارج الكتالوج) — الاحتياط
        `device_name` لم يتغيّر بحرف."""
        card = WarrantyCard(product=None, device_name="جهاز حرّ خارج الكتالوج")
        self.assertEqual(
            WarrantyCardSerializer().get_product_name(card), "جهاز حرّ خارج الكتالوج")

    # ── 2) after_sales/serializers.py — ServiceOrderPartSerializer ──

    def test_service_order_part_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("بطارية لابتوب", "دِل", "إتش بي")
        order_res = self.client.post(
            ORDERS,
            {"order_date": "2026-06-10", "partner": self.customer.pk,
             "device_description": "لابتوب", "complaint": "لا يشحن"},
            format="json", **self.headers)
        self.assertEqual(order_res.status_code, 201, order_res.content)
        order_id = order_res.data["id"]

        for p in (p1, p2):
            res = self.client.post(
                f"{ORDERS}{order_id}/parts/",
                {"product": p.pk, "quantity": "1"}, format="json", **self.headers)
            self.assertEqual(res.status_code, 201, res.content)

        parts = ServiceOrderPart.objects.filter(order_id=order_id).select_related("product")
        names = {part.product_id: ServiceOrderPartSerializer().get_product_name(part)
                 for part in parts}
        self.assertNotEqual(names[p1.pk], names[p2.pk])
        self.assertIn("دِل", names[p1.pk])
        self.assertIn("إتش بي", names[p2.pk])

    def test_service_order_part_falls_back_to_empty_string_when_product_is_absent(self):
        part = ServiceOrderPart(product=None)
        self.assertEqual(ServiceOrderPartSerializer().get_product_name(part), "")

    # ── 3) after_sales/serializers.py — ServiceOrderSerializer + ServiceOrderListSerializer ──

    def test_service_order_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("طابعة ليزر", "كانون", "إبسون")
        ids = {}
        for p in (p1, p2):
            res = self.client.post(
                ORDERS,
                {"order_date": "2026-06-10", "partner": self.customer.pk,
                 "product": p.pk, "complaint": "لا تطبع"},
                format="json", **self.headers)
            self.assertEqual(res.status_code, 201, res.content)
            ids[p.pk] = res.data["id"]

        detail_1 = self.client.get(f"{ORDERS}{ids[p1.pk]}/", **self.headers).json()
        detail_2 = self.client.get(f"{ORDERS}{ids[p2.pk]}/", **self.headers).json()
        self.assertNotEqual(detail_1["product_name"], detail_2["product_name"])
        self.assertIn("كانون", detail_1["product_name"])
        self.assertIn("إبسون", detail_2["product_name"])

        listing = self.client.get(ORDERS, **self.headers).json()
        rows = listing["results"] if isinstance(listing, dict) else listing
        list_names = {r["id"]: r["product_name"] for r in rows}
        self.assertEqual(list_names[ids[p1.pk]], detail_1["product_name"])
        self.assertEqual(list_names[ids[p2.pk]], detail_2["product_name"])

    def test_service_order_falls_back_to_device_description_when_product_is_absent(self):
        order = ServiceOrder(product=None, device_description="جهازٌ حرّ")
        self.assertEqual(
            ServiceOrderSerializer().get_product_name(order), "جهازٌ حرّ")
        self.assertEqual(
            ServiceOrderListSerializer().get_product_name(order), "جهازٌ حرّ")

    # ── 4) core/reports/after_sales.py — التقارير الثلاثة ──

    def test_warranties_expiring_report_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("جهاز إنذار", "هانيويل", "بوش")
        today = date(2026, 6, 15)
        end = today + timedelta(days=10)
        WarrantyCard.objects.create(
            tenant=self.tenant, product=p1, serial="WC-1",
            partner=self.customer, start_date=today - timedelta(days=355),
            duration_months=12, end_date=end, source=WarrantyCard.SOURCE_MANUAL)
        WarrantyCard.objects.create(
            tenant=self.tenant, product=p2, serial="WC-2",
            partner=self.customer, start_date=today - timedelta(days=355),
            duration_months=12, end_date=end, source=WarrantyCard.SOURCE_MANUAL)

        from unittest import mock
        with mock.patch("core.reports.after_sales.timezone.localdate", return_value=today):
            result = run_report(
                "after-sales-warranties-expiring", self.tenant.TenantID, {"days": 30})
        names = {r["serial"]: r["device"] for r in result["rows"]}
        self.assertNotEqual(names["WC-1"], names["WC-2"])
        self.assertIn("هانيويل", names["WC-1"])
        self.assertIn("بوش", names["WC-2"])

    def test_warranties_expiring_report_falls_back_to_device_name(self):
        WarrantyCard.objects.create(
            tenant=self.tenant, product=None, device_name="جهاز حرّ", serial="WC-FREE",
            partner=self.customer, start_date=date(2026, 5, 1),
            duration_months=2, end_date=date(2026, 7, 1),
            source=WarrantyCard.SOURCE_MANUAL)
        from unittest import mock
        with mock.patch(
            "core.reports.after_sales.timezone.localdate", return_value=date(2026, 6, 15),
        ):
            result = run_report(
                "after-sales-warranties-expiring", self.tenant.TenantID, {"days": 60})
        row = next(r for r in result["rows"] if r["serial"] == "WC-FREE")
        self.assertEqual(row["device"], "جهاز حرّ")

    def test_open_service_orders_report_shows_distinct_brand_names_for_siblings(self):
        p1, p2 = self._siblings("مكيّف سبليت", "إل جي", "شارب")
        ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-RPT-1", order_date=date(2026, 6, 1),
            partner=self.customer, product=p1, complaint="لا يبرّد",
            status=ServiceOrder.STATUS_RECEIVED)
        ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-RPT-2", order_date=date(2026, 6, 1),
            partner=self.customer, product=p2, complaint="لا يبرّد",
            status=ServiceOrder.STATUS_RECEIVED)

        result = run_report("after-sales-open-orders", self.tenant.TenantID, {})
        names = {r["order_number"]: r["device"] for r in result["rows"]}
        self.assertNotEqual(names["SO-RPT-1"], names["SO-RPT-2"])
        self.assertIn("إل جي", names["SO-RPT-1"])
        self.assertIn("شارب", names["SO-RPT-2"])

    def test_open_service_orders_report_falls_back_to_device_description(self):
        ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-RPT-FREE", order_date=date(2026, 6, 1),
            partner=self.customer, product=None, device_description="جهازٌ حرّ",
            complaint="عطل", status=ServiceOrder.STATUS_RECEIVED)
        result = run_report("after-sales-open-orders", self.tenant.TenantID, {})
        row = next(r for r in result["rows"] if r["order_number"] == "SO-RPT-FREE")
        self.assertEqual(row["device"], "جهازٌ حرّ")

    # ── 5) #43 — after_sales/views.py (`_log_part`): سطر مسار أمر الصيانة ──

    def test_service_order_part_timeline_event_shows_sibling_brand(self):
        p1, p2 = self._siblings("سماعة رأس", "بوز", "سيني هايزر")
        order_res = self.client.post(
            ORDERS,
            {"order_date": "2026-06-10", "partner": self.customer.pk,
             "device_description": "سماعة", "complaint": "لا صوت"},
            format="json", **self.headers)
        self.assertEqual(order_res.status_code, 201, order_res.content)
        order_id = order_res.data["id"]

        res = self.client.post(
            f"{ORDERS}{order_id}/parts/",
            {"product": p2.pk, "quantity": "1"}, format="json", **self.headers)
        self.assertEqual(res.status_code, 201, res.content)

        event = ServiceOrderEvent.objects.filter(
            order_id=order_id, event_type=ServiceOrderEvent.TYPE_PART).latest("id")
        self.assertIn("سيني هايزر", event.text)

    def test_pre_existing_timeline_event_text_is_untouched_by_the_fix(self):
        """لا backfill (#38): سطرٌ قديمٌ كُتب بالصيغة العارية قبل هذا الإصلاح
        يبقى كما هو حرفاً — التغيير من الآن فصاعداً فقط."""
        order = ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-LEGACY-EVT", order_date=date(2026, 6, 1),
            partner=self.customer, device_description="جهازٌ قديم", complaint="عطل",
            status=ServiceOrder.STATUS_RECEIVED)
        legacy_text = "أُضيفت قطعة: 215/65/16 × 1 (مفوترة على الزبون)"
        legacy = ServiceOrderEvent.objects.create(
            order=order, event_type=ServiceOrderEvent.TYPE_PART, text=legacy_text)

        p1, p2 = self._siblings("مضخة مياه", "غروندفوس", "ويلو")
        res = self.client.post(
            f"{ORDERS}{order.id}/parts/",
            {"product": p2.pk, "quantity": "1"}, format="json", **self.headers)
        self.assertEqual(res.status_code, 201, res.content)

        legacy.refresh_from_db()
        self.assertEqual(legacy.text, legacy_text)

    def test_warranty_cost_report_shows_distinct_brand_names_for_siblings(self):
        from after_sales.service_orders import STOCK_REF_SERVICE_ISSUE
        from inventory.models import StockMovement

        p1, p2 = self._siblings("مروحة تبريد", "كوماك", "أوريون")
        order = ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SO-RPT-COST", order_date=date(2026, 6, 1),
            partner=self.customer, product=p1, complaint="عطل",
            status=ServiceOrder.STATUS_RECEIVED)
        StockMovement.objects.create(
            tenant=self.tenant, product=p1, movement_type="OUT",
            reference_type=STOCK_REF_SERVICE_ISSUE, reference_id=order.pk,
            quantity=Decimal("1"), unit_cost=Decimal("20"), total_cost=Decimal("20"),
            movement_date="2026-06-02")
        StockMovement.objects.create(
            tenant=self.tenant, product=p2, movement_type="OUT",
            reference_type=STOCK_REF_SERVICE_ISSUE, reference_id=order.pk,
            quantity=Decimal("1"), unit_cost=Decimal("30"), total_cost=Decimal("30"),
            movement_date="2026-06-02")

        result = run_report("after-sales-warranty-cost", self.tenant.TenantID, {})
        names = {r["unit_cost"]: r["product"] for r in result["rows"]}
        self.assertNotEqual(names["20.00"], names["30.00"])
        self.assertIn("كوماك", names["20.00"])
        self.assertIn("أوريون", names["30.00"])
