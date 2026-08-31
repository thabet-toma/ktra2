"""THA-18 — لقطة اسم بند فاتورة البيع: تُكتب عند الترحيل لا عند الإنشاء.

إعادة تسمية منتج لا تعود تُعيد كتابة ما تعرضه فاتورة بيعٍ **مرحَّلة** — الاسم
يتجمَّد لحظة الترحيل. غير المرحَّلة تبقى تتبع اسم المنتج الحي.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from inventory.services import record_stock_movement
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="namesnap", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة لقطة الاسم", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-N", name="ذمم", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="NS-1", name_ar="اسم قديم",
        quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
    record_stock_movement(
        product=product, movement_type="IN", quantity=Decimal("100"),
        unit_cost=Decimal("10"), reference_type="OPENING", reference_id=0,
        movement_date="2026-06-01", tenant=tenant)
    product.refresh_from_db()
    cogs = Account.objects.create(
        tenant=tenant, code="5101-N", name="تكلفة", account_type="Expense", is_active=True)
    inv_acc = Account.objects.create(
        tenant=tenant, code="1104-N", name="مخزون", account_type="Asset", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cogs_account = cogs
    ss.default_inventory_account = inv_acc
    ss.save(update_fields=["default_cogs_account", "default_inventory_account"])
    return tenant, owner, cur, customer, product


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _make_invoice(tenant, customer, product, currency, number, *, stock_on_post=True):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=currency,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CASH,
        stock_on_post=stock_on_post)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("2"), unit_price=Decimal("50"))
    return inv


def test_posted_invoice_freezes_name_at_posting_time(env):
    tenant, owner, cur, customer, product = env
    inv = _make_invoice(tenant, customer, product, cur, "NS-POST-1")
    c = _client(owner, tenant)

    res = c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json")
    assert res.status_code == 200, res.content[:300]
    line = SalesInvoiceLine.objects.get(invoice=inv)
    assert line.name_snapshot == "اسم قديم"

    # إعادة تسمية المنتج بعد الترحيل
    product.name_ar = "اسم جديد"
    product.save(update_fields=["name_ar"])

    detail = c.get(f"/api/sales/invoices/{inv.id}/", format="json").json()
    assert detail["lines"][0]["product_name"] == "اسم قديم"


def test_unposted_invoice_follows_live_product_name(env):
    tenant, owner, cur, customer, product = env
    inv = _make_invoice(tenant, customer, product, cur, "NS-DRAFT-1")
    c = _client(owner, tenant)

    detail = c.get(f"/api/sales/invoices/{inv.id}/", format="json").json()
    assert detail["lines"][0]["product_name"] == "اسم قديم"

    product.name_ar = "اسم جديد"
    product.save(update_fields=["name_ar"])

    detail = c.get(f"/api/sales/invoices/{inv.id}/", format="json").json()
    assert detail["lines"][0]["product_name"] == "اسم جديد"

    line = SalesInvoiceLine.objects.get(invoice=inv)
    assert line.name_snapshot == ""


def test_backfill_command_is_idempotent(env):
    from io import StringIO

    from django.core.management import call_command

    tenant, owner, cur, customer, product = env
    inv = _make_invoice(tenant, customer, product, cur, "NS-BF-1")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    # محاكاة الصفوف القديمة: فاتورة **مرحَّلة** بلا لقطة (رُحِّلت قبل THA-18).
    SalesInvoiceLine.objects.filter(invoice=inv).update(name_snapshot="")
    line = SalesInvoiceLine.objects.get(invoice=inv)
    assert line.name_snapshot == ""

    call_command("backfill_invoice_name_snapshots", "--apply", stdout=StringIO())
    line.refresh_from_db()
    assert line.name_snapshot == "اسم قديم"

    # منتجٌ أُعيدت تسميته بعد التعبئة الأولى — التشغيلة الثانية لا تلمس اللقطة القائمة
    product.name_ar = "اسم بعد التعبئة"
    product.save(update_fields=["name_ar"])
    call_command("backfill_invoice_name_snapshots", "--apply", stdout=StringIO())
    line.refresh_from_db()
    assert line.name_snapshot == "اسم قديم"

    # بندٌ آخر له لقطة مكتوبة يدوياً مسبقاً — لا يُستبدل بالاسم الحالي
    other = SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal("10"),
        name_snapshot="لقطة موجودة سلفاً")
    call_command("backfill_invoice_name_snapshots", "--apply", stdout=StringIO())
    other.refresh_from_db()
    assert other.name_snapshot == "لقطة موجودة سلفاً"


def test_unposting_returns_the_line_to_the_live_product_name(env):
    """إلغاء الترحيل يُرجع الفاتورة مسودةً — فتسقط اللقطة ويعود الاسم حياً."""
    tenant, owner, cur, customer, product = env
    inv = _make_invoice(tenant, customer, product, cur, "NS-UNPOST-1")
    c = _client(owner, tenant)

    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    assert SalesInvoiceLine.objects.get(invoice=inv).name_snapshot == "اسم قديم"

    res = c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json")
    assert res.status_code == 200, res.content[:300]
    assert SalesInvoiceLine.objects.get(invoice=inv).name_snapshot == ""

    product.name_ar = "اسم جديد"
    product.save(update_fields=["name_ar"])
    detail = c.get(f"/api/sales/invoices/{inv.id}/", format="json").json()
    assert detail["lines"][0]["product_name"] == "اسم جديد"

    # وإعادة الترحيل تُجمّد الاسم الجديد لا القديم
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    assert SalesInvoiceLine.objects.get(invoice=inv).name_snapshot == "اسم جديد"


def test_backfill_never_freezes_a_draft(env):
    """المسودّة لا تُجمَّد: الفارغة تعني «اتبع الاسم الحي»، ولا مسارَ يمسحها بعدها."""
    from io import StringIO

    from django.core.management import call_command

    tenant, owner, cur, customer, product = env
    draft = _make_invoice(tenant, customer, product, cur, "NS-BF-DRAFT")

    call_command("backfill_invoice_name_snapshots", "--apply", stdout=StringIO())

    assert SalesInvoiceLine.objects.get(invoice=draft).name_snapshot == ""
    c = _client(owner, tenant)
    product.name_ar = "اسم جديد"
    product.save(update_fields=["name_ar"])
    detail = c.get(f"/api/sales/invoices/{draft.id}/", format="json").json()
    assert detail["lines"][0]["product_name"] == "اسم جديد"


def test_backfill_tenant_flag_leaves_other_companies_untouched(env):
    """`--tenant` يحصر الأثر بشركةٍ واحدة — والحقل يخرج خاماً للواجهة."""
    from io import StringIO

    from django.core.management import call_command

    tenant, owner, cur, customer, product = env
    inv = _make_invoice(tenant, customer, product, cur, "NS-BF-T1")
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    SalesInvoiceLine.objects.filter(invoice=inv).update(name_snapshot="")

    call_command(
        "backfill_invoice_name_snapshots", "--apply",
        "--tenant", str(tenant.TenantID + 999), stdout=StringIO(),
    )
    assert SalesInvoiceLine.objects.get(invoice=inv).name_snapshot == ""

    call_command(
        "backfill_invoice_name_snapshots", "--apply",
        "--tenant", str(tenant.TenantID), stdout=StringIO(),
    )
    line = SalesInvoiceLine.objects.get(invoice=inv)
    assert line.name_snapshot == "اسم قديم"

    # الحقل خامّاً في العقد — الواجهة تفرّق به بين المجمَّد والمشتقّ حياً.
    detail = c.get(f"/api/sales/invoices/{inv.id}/", format="json").json()
    assert detail["lines"][0]["name_snapshot"] == "اسم قديم"
