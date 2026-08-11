"""العملاء «المختفون»: عميل اشترى سابقاً ثم توقّف مدّة تتجاوز عتبة الإعدادات
(dormant_customer_days، افتراضها 30 يوماً) — يُرصد من فواتير البيع المرحَّلة وحدها
ويُستهلك من مولّد إشعارات الموقع.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from partners.models import Partner
from sales.models import SalesInvoice
from sales.services import dormant_customers, get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="dormant", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة العملاء المختفين", owner)
    return tenant, ils


def _customer(tenant, name):
    return Partner.objects.create(tenant=tenant, name=name, partner_type="Customer")


def _sale(tenant, customer, ils, *, number, days_ago, posted=True, kind=None):
    return SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=ils,
        invoice_date=date.today() - timedelta(days=days_ago),
        invoice_kind=kind or SalesInvoice.INVOICE_KIND_SALE,
        grand_total=Decimal("100"),
        status=SalesInvoice.STATUS_POSTED if posted else SalesInvoice.STATUS_DRAFT,
    )


def test_customer_silent_beyond_threshold_is_reported(env):
    tenant, ils = env
    gone = _customer(tenant, "زبون مختفٍ")
    _sale(tenant, gone, ils, number="SI-D-1", days_ago=40)

    rows = dormant_customers(tenant_id=tenant.TenantID, days=30)
    assert len(rows) == 1
    assert rows[0]["partner_id"] == gone.id
    assert rows[0]["partner_name"] == "زبون مختفٍ"
    assert rows[0]["days_since"] == 40
    assert rows[0]["last_sale_date"] == (date.today() - timedelta(days=40)).isoformat()
    assert rows[0]["last_invoice_number"] == "SI-D-1"


def test_recent_customer_is_not_reported(env):
    tenant, ils = env
    active = _customer(tenant, "زبون نشط")
    _sale(tenant, active, ils, number="SI-D-2", days_ago=40)
    _sale(tenant, active, ils, number="SI-D-3", days_ago=5)  # عاد واشترى

    assert dormant_customers(tenant_id=tenant.TenantID, days=30) == []


def test_never_bought_customer_is_not_reported(env):
    tenant, _ils = env
    _customer(tenant, "زبون بلا شراء")
    assert dormant_customers(tenant_id=tenant.TenantID, days=30) == []


def test_drafts_and_returns_do_not_count_as_activity(env):
    tenant, ils = env
    gone = _customer(tenant, "زبون مختفٍ")
    _sale(tenant, gone, ils, number="SI-D-4", days_ago=45)
    _sale(tenant, gone, ils, number="SI-D-5", days_ago=2, posted=False)  # مسودة
    _sale(tenant, gone, ils, number="SI-D-6", days_ago=1,
          kind=SalesInvoice.INVOICE_KIND_SALE_RETURN)  # مرجع بيع ليس شراءً

    rows = dormant_customers(tenant_id=tenant.TenantID, days=30)
    assert [r["days_since"] for r in rows] == [45]


def test_ended_dealing_customer_is_skipped(env):
    """من انتهى تعامله رسمياً ليس «مختفياً» — توقّفه معروف."""
    tenant, ils = env
    ended = _customer(tenant, "زبون منتهي التعامل")
    ended.end_of_dealing_date = date.today() - timedelta(days=60)
    ended.save(update_fields=["end_of_dealing_date"])
    _sale(tenant, ended, ils, number="SI-D-7", days_ago=90)

    assert dormant_customers(tenant_id=tenant.TenantID, days=30) == []


def test_zero_days_disables_the_alert(env):
    tenant, ils = env
    gone = _customer(tenant, "زبون مختفٍ")
    _sale(tenant, gone, ils, number="SI-D-8", days_ago=200)

    assert dormant_customers(tenant_id=tenant.TenantID, days=0) == []


def test_threshold_defaults_to_sales_settings(env):
    tenant, ils = env
    gone = _customer(tenant, "زبون مختفٍ")
    _sale(tenant, gone, ils, number="SI-D-9", days_ago=20)

    ss = get_or_create_sales_settings(tenant)
    assert ss.dormant_customer_days == 30  # الافتراضي
    assert dormant_customers(tenant_id=tenant.TenantID) == []

    ss.dormant_customer_days = 15
    ss.save(update_fields=["dormant_customer_days"])
    rows = dormant_customers(tenant_id=tenant.TenantID)
    assert [r["partner_id"] for r in rows] == [gone.id]


def test_longest_silence_first(env):
    tenant, ils = env
    a = _customer(tenant, "أ")
    b = _customer(tenant, "ب")
    _sale(tenant, a, ils, number="SI-D-10", days_ago=35)
    _sale(tenant, b, ils, number="SI-D-11", days_ago=90)

    rows = dormant_customers(tenant_id=tenant.TenantID, days=30)
    assert [r["partner_id"] for r in rows] == [b.id, a.id]


class DormantCustomersEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dormante", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة منفذ المختفين", cls.user)
        cls.gone = Partner.objects.create(
            tenant=cls.tenant, name="زبون مختفٍ", partner_type="Customer")
        _sale(cls.tenant, cls.gone, cls.ils, number="SI-DE-1", days_ago=40)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_endpoint_uses_settings_threshold(self):
        res = self.client.get("/api/sales/reports/dormant-customers/", **self._auth())
        assert res.status_code == 200, res.content
        rows = res.json()
        assert [r["partner_id"] for r in rows] == [self.gone.id]
        assert rows[0]["days_since"] == 40

    def test_endpoint_days_override(self):
        res = self.client.get(
            "/api/sales/reports/dormant-customers/?days=60", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json() == []
