"""الخدمةُ لا رصيد لها فلا يُقاس عليها نفاد (T-SERVICELINE، بلاغ المالك).

بلاغ المالك: «لما أدخل خدمة بيقلي تتجاوز المتاح مع إنه خدمة».

الجذر — `sales/serializers.py` (`_validate_stock_availability`): الإعفاء كان
متروكاً لـ`Product.allow_negative_stock` وحده على أساس أن الخدمة تُنشأ به،
و`default=False` (`inventory/models.py`). فخدمةٌ أُنشئت بالافتراضي — ومنها كل
خدمةٍ يزرعها قالبُ مكتب المحاسبة (`ACCOUNTING_FIRM_SERVICES`) وكلُّ خدمةٍ
يُنشئها المستخدم من شاشة الأصناف — كانت تُردّ بـ«الكمية تتجاوز المتوفر في
المخزون (0)» على شيءٍ لا مخزون له أصلاً، متى أطفأت الشركةُ السالبَ العام.

وبقيّةُ المستودع تعفيها **صراحةً** (`sales/services/orders.py` و
`sales/services/numbering.py`: `product.is_service or product.allow_negative_stock`)
— هذا الموضع وحده كان شاذّاً عن القاعدة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

INVOICES_URL = "/api/sales/invoices/"


@pytest.fixture
def env():
    owner = User.objects.create_user(username="svcguard", password="x")
    ils = Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة حارس الخدمة", owner)
    create_fiscal_year(tenant, 2026)
    # الشرط الذي يُفعّل الحارس أصلاً: الشركة تمنع المخزون السالب.
    SalesSettings.objects.update_or_create(
        tenant=tenant, defaults={"allow_negative_stock_default": False})
    ar = Account.objects.create(
        tenant=tenant, code="1103-S", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    # خدمةٌ بالافتراضي: `allow_negative_stock=False` ورصيدٌ صفر — بالضبط ما
    # يُنشئه المستخدم من شاشة الأصناف وما يزرعه قالب المكتب.
    service = Product.objects.create(
        tenant=tenant, sku="GUARD-S1", name_ar="أتعاب تدقيق", is_service=True)
    goods = Product.objects.create(
        tenant=tenant, sku="GUARD-G1", name_ar="بضاعة", quantity_on_hand=0, avg_cost=1)
    return owner, tenant, ils, customer, service, goods


def _body(customer, ils, product, *, number):
    return {
        "invoice_number": number,
        "customer": customer.pk,
        "currency": ils.pk,
        "invoice_date": "2026-06-15",
        "invoice_type": SalesInvoice.INVOICE_CREDIT,
        "stock_on_post": True,
        "lines": [{"product": product.pk, "quantity": "2", "unit_price": "100"}],
    }


def test_service_line_is_not_measured_against_stock(env, client):
    """المعيار: خدمةٌ برصيدٍ صفر تُحفظ رغم منع الشركة للسالب."""
    owner, tenant, ils, customer, service, _goods = env
    client.force_login(owner)
    res = client.post(
        INVOICES_URL,
        _body(customer, ils, service, number="SVC-GUARD-1"),
        content_type="application/json",
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert res.status_code == 201, res.content
    assert SalesInvoice.objects.filter(
        tenant=tenant, invoice_number="SVC-GUARD-1").exists()


def test_goods_line_is_still_measured_against_stock(env, client):
    """التراجع الصريح: الحارس لم يُفتح للبضاعة — بضاعةٌ برصيدٍ صفر تُردّ."""
    owner, tenant, ils, customer, _service, goods = env
    client.force_login(owner)
    res = client.post(
        INVOICES_URL,
        _body(customer, ils, goods, number="SVC-GUARD-2"),
        content_type="application/json",
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert res.status_code == 400, res.content
    assert "تتجاوز المتوفر" in res.content.decode()


def test_service_quantity_leaves_no_stock_movement(env, client):
    """ولا تُخصم كميةٌ من خدمة: رصيدها يبقى كما هو بعد الحفظ."""
    owner, tenant, ils, customer, service, _goods = env
    client.force_login(owner)
    res = client.post(
        INVOICES_URL,
        _body(customer, ils, service, number="SVC-GUARD-3"),
        content_type="application/json",
        HTTP_X_TENANT_ID=str(tenant.TenantID),
    )
    assert res.status_code == 201, res.content
    service.refresh_from_db()
    assert Decimal(str(service.quantity_on_hand)) == Decimal("0")
