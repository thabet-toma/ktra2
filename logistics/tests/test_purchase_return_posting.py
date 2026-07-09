"""مرجع الشراء (create_purchase_return): يُخرج الكمية من المخزن ويعكس قيد الشراء.

يتحقق أن:
  - حركة RETURN_OUT تُنقص المخزون بالكمية المرتجعة.
  - القيد يَدين ذمم المورد (AP) ويَدائن المخزون — عكس استلام الشراء.
  - الفاتورة المرجَعة تُحفظ is_return=True ومُرحّلة.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.services import create_purchase_return, post_purchase_return
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="retpur", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة مرجع الشراء", owner)
    tenant._cur = ils
    create_fiscal_year(tenant, 2026)
    # شجرة الحسابات مبذورة عند إنشاء الشركة — نستخدم 2101 (ذمم موردين) و1104 (مخزون).
    ap = Account.objects.filter(tenant=tenant, code="2101").first()
    inv = Account.objects.filter(tenant=tenant, code="1104").first()
    assert ap is not None and inv is not None, "seed missing 2101/1104"
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد", partner_type="Supplier", linked_account=ap)
    product = Product.objects.create(
        tenant=tenant, sku="RET-P", name_ar="صنف", quantity_on_hand=Decimal("10"),
        avg_cost=Decimal("50"))
    return tenant, supplier, product, ap, inv


def test_purchase_return_draft_then_post(env):
    tenant, supplier, product, ap, inv = env
    ret = create_purchase_return(
        tenant,
        original_invoice=None,
        partner=supplier,
        return_date="2026-06-15",
        lines=[{"product": product.id, "quantity": 4, "unit_price": 50}],
    )
    product.refresh_from_db()
    # مرحلة الحفظ: مسودة — لا مخزون ولا قيد.
    assert ret.is_return is True
    assert ret.is_posted is False
    assert ret.status == "draft"
    assert product.quantity_on_hand == Decimal("10")

    # مرحلة الترحيل: تُخرج الكمية وتُنشئ القيد العكسي.
    post_purchase_return(ret, user=None)
    ret.refresh_from_db()
    product.refresh_from_db()
    assert ret.is_posted is True
    assert product.quantity_on_hand == Decimal("6")

    ap_line = JournalLine.objects.filter(journal=ret.journal, account=ap).first()
    inv_line = JournalLine.objects.filter(journal=ret.journal, account=inv).first()
    assert ap_line is not None and Decimal(str(ap_line.debit)) == Decimal("200")
    assert inv_line is not None and Decimal(str(inv_line.credit)) == Decimal("200")


def test_purchase_return_requires_positive_line(env):
    tenant, supplier, product, _ap, _inv = env
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        create_purchase_return(
            tenant, original_invoice=None, partner=supplier,
            return_date="2026-06-15",
            lines=[{"product": product.id, "quantity": 0, "unit_price": 50}],
        )
