"""W8 — تجميعات جدول الأصناف وبطاقته من StockMovement (المصدر الوحيد):
- purchased_qty = الوارد التراكمي (كل حركات IN).
- avg_monthly_sales = صافي (OUT − RETURN_IN) خلال آخر 90 يوماً ÷ 3.
- avg_weekly_sales (البطاقة) = صافي خلال آخر 28 يوماً ÷ 4.
والنافذة الزمنية تستبعد الحركات الأقدم من الفترة.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from inventory.services import product_profile
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"


class ItemAggregatesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="agg", password="x")
        cls.tenant = create_company("شركة التجميعات", cls.owner)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="AGG-1", name_ar="صنف",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("10"))
        today = datetime.date.today()
        recent = today - datetime.timedelta(days=10)   # داخل 28 و90
        mid = today - datetime.timedelta(days=60)       # داخل 90 فقط
        old = today - datetime.timedelta(days=200)       # خارج الكل

        def mv(mtype, qty, when):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.product, movement_type=mtype,
                quantity=Decimal(str(qty)), movement_date=when)

        mv("IN", 100, old)      # مشتريات تراكمية (بلا نافذة)
        mv("IN", 50, recent)
        mv("OUT", 18, recent)   # مبيعات داخل 28 و90
        mv("RETURN_IN", 6, recent)  # مرتجع داخل 28 و90
        mv("OUT", 12, mid)      # مبيعات داخل 90 فقط
        mv("OUT", 999, old)     # قديم — لا يُحسب

    def _row(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(PRODUCTS_URL, HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        assert res.status_code == 200, res.content[:200]
        data = res.json()
        rows = data["results"] if isinstance(data, dict) else data
        return next(r for r in rows if r["id"] == self.product.id)

    def test_purchased_qty_is_cumulative_in(self):
        assert Decimal(self._row()["purchased_qty"]) == Decimal("150")

    def test_avg_monthly_sales_net_of_returns_over_90d(self):
        # صافي 90ي = (18 + 12) − 6 = 24 ÷ 3 = 8.00. البيع القديم 999 مستبعد.
        assert Decimal(self._row()["avg_monthly_sales"]) == Decimal("8.00")

    def test_profile_avg_weekly_sales_over_28d(self):
        # صافي 28ي = 18 − 6 = 12 ÷ 4 = 3.00 (مبيعات 60 يوماً مستبعدة من الأسبوعي).
        prof = product_profile(tenant_id=self.tenant.TenantID, product_id=self.product.id)
        assert Decimal(prof["avg_weekly_sales"]) == Decimal("3.00")
        assert Decimal(prof["avg_monthly_sales"]) == Decimal("8.00")
