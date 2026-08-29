"""T-PAYFULL — البيع النقدي بلا صندوق يُرفض بجملةٍ، لا يمرّ بتحذيرٍ في اللوج.

شكوى المالك كانت «أكبس مدفوعة وما بتتغيّر الحالة». المسار السليم يعمل، لكن حين
يعجز `_resolve_settlement_cash_account_id` عن إيجاد صندوق كان الترحيل **ينجح**
والفاتورة تبقى «غير مدفوعة» والعميل مديناً — بلا رسالةٍ واحدة في الشاشة. أي
شاشةٌ تقول «تم الترحيل» بينما نصفُ العملية لم يقع.

وجانب الشراء كان يفعل الصواب أصلاً (`_auto_settle_cash_purchase` يرفع
`ValidationError` بجملةٍ إرشادية — T-APPAID)، فهذا الاختبار يفرض **التماثل**.

الأثر المالي: قبل الإصلاح كانت الفاتورة النقدية تُرحَّل ويبقى العميل مديناً
بكامل قيمتها، فتظهر في كشف حسابه وفي أعمار الذمم مطالبةً وهمية إلى الأبد.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from accounting.models import Account, FiscalPeriod
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine, SalesSettings
from sales.services import post_sales_invoice, posted_allocations_total
from tenants.models import Currency, Tenant, UserCompanyMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    user = User.objects.create_user(username="cashguard", password="x")
    tenant = Tenant.objects.create(TenantID=931, CompanyName="شركة البيع النقدي")
    UserCompanyMembership.objects.create(user=user, tenant=tenant, role="manager")
    currency = Currency.objects.create(
        CurrencyID=931, Code="ILS", Symbol="₪", IsBaseCurrency=True)
    # فخّان في تجهيز هذا الاختبار، كلاهما من سلّم `resolve_cash_account` الأخير:
    #  (1) كود الذمم ليس من `DEFAULT_CASH_ACCOUNT_CODES` ("1101","1102","1110")
    #      عمداً — ذممٌ بكود 1101 تُنتقى صندوقاً فتُسوّى الفاتورة Dr/Cr على
    #      الحساب نفسه: تسويةٌ صوريّة تُخفي العطل الذي نقيسه.
    #  (2) واسم الطرف لا يحمل «نقد» — إشارةُ `partners` تُسمّي حساب الذمم باسم
    #      صاحبه، والسلّم يسقط أخيراً على `name__icontains="نقد"`، فزبونٌ اسمه
    #      «زبون نقدي» يجعل حساب ذممه صندوقَ الشركة.
    ar = Account.objects.create(
        tenant=tenant, code="1130", name="ذمم عملاء",
        account_type="Asset", is_active=True)
    Account.objects.create(
        tenant=tenant, code="4101", name="إيرادات",
        account_type="Revenue", is_active=True)
    SalesSettings.objects.update_or_create(
        tenant=tenant, defaults={"default_ar_account": ar})
    partner = Partner.objects.create(
        tenant=tenant, name="زبون التسوية", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="CASHG-1", name_ar="خدمة", is_service=True)
    FiscalPeriod.objects.create(
        tenant=tenant, name="2026", start_date="2026-01-01",
        end_date="2026-12-31", is_closed=False)
    return tenant, partner, product, currency


def _cash_invoice(env, number, *, cash_account=None):
    tenant, partner, product, currency = env
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=partner,
        currency=currency, invoice_date="2026-07-01",
        invoice_type=SalesInvoice.INVOICE_CASH, stock_on_post=False,
        cash_or_bank_account=cash_account,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=1, unit_price=Decimal("100"))
    return inv


def test_cash_sale_without_any_cash_account_is_refused_not_silently_unsettled(env):
    """لا صندوق على الفاتورة ولا في الإعدادات ولا في الشجرة ⇒ رفضٌ بجملة."""
    inv = _cash_invoice(env, "CASHG-NO-BOX")

    with pytest.raises(ValidationError) as exc:
        post_sales_invoice(inv)

    message = " ".join(getattr(exc.value, "messages", [str(exc.value)]))
    assert "نقدية" in message
    assert "صندوق" in message

    # والأهم: الرفض ارتدّ بكل شيء — لا فاتورةٌ مرحّلة بلا تسوية.
    inv.refresh_from_db()
    assert inv.status != SalesInvoice.STATUS_POSTED
    assert inv.journal_id is None


def test_cash_sale_with_a_cash_account_settles_and_leaves_no_debt(env):
    """المسار السليم لم يتغيّر: سندٌ مرحّل بكامل القيمة والعميل غير مدين."""
    tenant, *_ = env
    cash = Account.objects.create(
        tenant=tenant, code="1110B0001", name="الصندوق الرئيسي",
        account_type="Asset", is_active=True)
    inv = _cash_invoice(env, "CASHG-OK", cash_account=cash)

    post_sales_invoice(inv)

    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED
    assert posted_allocations_total(inv.pk) == Decimal("100.00")


def test_settings_default_cash_account_is_enough(env):
    """الصندوق من إعدادات المبيعات يكفي — لا يلزم وضعه على كل فاتورة."""
    tenant, *_ = env
    cash = Account.objects.create(
        tenant=tenant, code="1110B0002", name="صندوق الإعدادات",
        account_type="Asset", is_active=True)
    SalesSettings.objects.update_or_create(
        tenant=tenant, defaults={"default_cash_account": cash})
    inv = _cash_invoice(env, "CASHG-SETTINGS")

    post_sales_invoice(inv)

    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED
    assert posted_allocations_total(inv.pk) == Decimal("100.00")
