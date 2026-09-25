"""الفاتورة الدولية تُقرأ بحصّة المورد لا بإجماليها المحمَّل — في التقارير والكرت وآخر سعر شراء.

إجمالي الدولية محمَّل (بضاعة + شحن + تخليص + نقل) وقيدها يدائن المورد بحصّته وحدها؛ فكانت
«المشتريات حسب المورد» و«إجمالي المشتريات» في كرته تضخّم تعامله بحصص الوكيل والمخلّص والناقل،
و«آخر سعر شراء» يقترح لبند شراءٍ جديد سعراً محمَّلاً لم يبعه به المورد قط.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.pricing import PriceStrategy, purchase_price_list, resolve_purchase_price
from core.reports import run_report
from logistics.tests.test_purchase_return_posting import _posted_international, env  # noqa: F401

pytestmark = pytest.mark.django_db


def test_purchase_reports_use_the_supplier_share(env):
    tenant, supplier, product, ap, inv = env
    _posted_international(tenant, supplier, product, ap, inv)

    by_supplier = run_report("purchases-by-supplier", tenant.TenantID, {})
    (row,) = [r for r in by_supplier["rows"] if r["partner_id"] == supplier.id]
    assert Decimal(row["grand_total"]) == Decimal("700.00")

    register = run_report("purchase-invoices", tenant.TenantID, {})
    (row,) = register["rows"]
    assert (Decimal(row["grand_total"]), Decimal(row["landed_total"])) == (Decimal("700.00"), Decimal("1000.00"))


def test_partner_card_total_purchases_is_the_supplier_share(env):
    tenant, supplier, product, ap, inv = env
    _posted_international(tenant, supplier, product, ap, inv)
    client = APIClient()
    client.force_authenticate(user=User.objects.get(username="retpur"))  # مالك الشركة في `env`
    profile = client.get(
        f"/api/partners/{supplier.id}/profile/", HTTP_X_TENANT_ID=str(tenant.TenantID)).data
    assert Decimal(profile["total_purchases"]) == Decimal("700.00")


def test_last_purchase_price_is_the_supplier_price_not_landed(env):
    tenant, supplier, product, ap, inv = env
    # المورد دائنٌ بـ700 من محمَّلٍ 1,000 ⇒ سعره للبند 100 × 0.7.
    _posted_international(tenant, supplier, product, ap, inv)

    resolved = resolve_purchase_price(
        tenant_id=tenant.TenantID, product_id=product.id, strategy=PriceStrategy.LAST_PURCHASE)
    assert Decimal(resolved["unit_price"]) == Decimal("70.0000")  # لا 100 المحمَّل
    listed = purchase_price_list(tenant_id=tenant.TenantID)[product.id]
    assert Decimal(listed["unit_price"]) == Decimal("70.0000")
