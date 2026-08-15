"""THA-110 (T4) — «الوضع السهل» قناعُ عرضٍ لا دفترٌ ثانٍ.

الوضع السهل يخفي عن التاجر المبتدئ عناصرَ محرّر فاتورة البيع المتقدّمة (العملة،
«شامل الضريبة»، الاستحقاق للفاتورة المدفوعة، تبويبات الحسابات/بيانات أخرى/الحركات
المالية/سجل النشاط، ومعاينة القيد). القاعدة الحاكمة أن الإخفاء **عرضٌ لا منطق**:
الحقل المخفيّ يحتفظ بقيمته، والافتراضاتُ التي كانت تُطبَّق صامتةً تبقى هي هي.

هذا الملف يسمّر تلك القاعدة على أغلى ما في النظام — القيد المحاسبي: فاتورتان
بمدخلاتٍ متطابقة، واحدةٌ بحمولة «الحقول الظاهرة في الوضع السهل فقط» (الباقي محذوف
فتتولّاه الافتراضيات) وأخرى بحمولةٍ كاملة صريحة بنفس القيم الفعلية — يجب أن
يُنتجا **نفس سطور القيد بالضبط**: الحساب والمدين والدائن والعملة.

الاختبار يُثبّت سلوكاً قائماً ولا يُصلح عيباً — لا سطر خادميّ واحد تغيَّر في
`sales` أو `accounting` أو `inventory` — فهو أخضر منذ ولادته، وذلك مقصود ومصرَّح
به في التذكرة (قاعدة «أحمر قبل الإصلاح» تخصّ إصلاحات المال، ولا سلوك مال يتغيّر
هنا). لو وُلد أحمر لكان ذلك اكتشافَ عيبٍ محاسبيّ قائم لا فشلَ تنفيذ.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, TaxRate
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import CustomerPayment, SalesInvoice
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

INV_DATE = "2026-06-15"


@pytest.fixture
def env():
    owner = User.objects.create_user(username="simplemode", password="x")
    ils = Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الوضع السهل", owner)
    create_fiscal_year(tenant, 2026)

    cash = Account.objects.create(
        tenant=tenant, code="1110-SM", name="صندوق", account_type="Asset",
        is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-SM", name="إيراد المبيعات", account_type="Revenue",
        is_active=True)
    vat_out = Account.objects.get(tenant=tenant, code="2104")
    tax16 = TaxRate.objects.create(
        tenant=tenant, code="VAT16-SM", name="ض.ق.م 16%", rate=Decimal("16.00"),
        tax_account=vat_out, direction="sales", is_active=True)

    # الافتراضاتُ التي يخفيها الوضع السهل — هي بعينها ما يُطبَّق صامتاً اليوم.
    ss = get_or_create_sales_settings(tenant)
    ss.default_currency = ils
    ss.default_cash_account = cash
    ss.default_revenue_account_product = rev
    ss.default_revenue_account_service = rev
    ss.default_payment_type = "cash"
    ss.stock_on_post_default = True
    ss.prices_include_tax = False
    ss.save()

    customer = Partner.objects.create(
        tenant=tenant, name="عميل الوضع السهل", partner_type="Customer")
    product = Product.objects.create(
        tenant=tenant, sku="SM-1", name_ar="صنف", quantity_on_hand=Decimal("1000"),
        avg_cost=Decimal("40"))
    return tenant, owner, ils, cash, rev, tax16, customer, product


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _lines(product, tax):
    return [{
        "product": product.id,
        "quantity": "3",
        "unit_price": "125.00",
        "line_discount": 0,
        "tax_rate": tax.id,
        "serials": [],
    }]


def _simple_payload(customer, product, tax, *, invoice_type):
    """حمولة الوضع السهل: العميل · «مدفوعة» · التاريخ · البنود · الملاحظات.

    ما عداها محذوف عمداً — العملة وحساب الصندوق وحساب الإيراد وخصم المخزون
    والاستحقاق و«شامل الضريبة» كلّها مخفيّة، فتتولّاها افتراضاتُ الإعدادات.
    """
    return {
        "customer": customer.id,
        "invoice_date": INV_DATE,
        "invoice_type": invoice_type,
        "notes": "",
        "lines": _lines(product, tax),
    }


def _explicit_payload(customer, product, tax, currency, cash, rev, *, invoice_type):
    """حمولة الوضع المتقدّم بنفس القيم الفعلية — كل حقلٍ مذكورٌ صراحةً.

    تُطابق `buildPayload` في المحرّر حرفاً بحرف، بما فيه أن حساب الصندوق لا
    يُرسَل إلا للفاتورة المدفوعة.
    """
    payload = {
        "customer": customer.id,
        "invoice_date": INV_DATE,
        "due_date": None,
        "invoice_type": invoice_type,
        "currency": currency.CurrencyID,
        "exchange_rate": 1,
        "invoice_discount": 0,
        "stock_on_post": True,
        "notes": "",
        "lines": _lines(product, tax),
        "book_number": 0,
        "second_date": None,
        "licensed_dealer_no": "",
        "settlement_invoice_no": "",
        "prices_include_tax": False,
        "discount_percent": 0,
        "source_discount_percent_override": None,
        "source_discount_amount_override": None,
        "revenue_account": rev.id,
    }
    if invoice_type == "cash":
        payload["cash_or_bank_account"] = cash.id
    return payload


def _create_and_post(client, payload) -> SalesInvoice:
    res = client.post("/api/sales/invoices/", payload, format="json")
    assert res.status_code == 201, res.data
    inv_id = res.data["id"]
    posted = client.post(f"/api/sales/invoices/{inv_id}/post/", {}, format="json")
    assert posted.status_code == 200, posted.data
    return SalesInvoice.objects.get(pk=inv_id)


def _journal_fingerprint(invoice: SalesInvoice) -> list[tuple]:
    """كامل الأثر المحاسبي للفاتورة: (الحساب · مدين · دائن · العملة).

    البيع النقدي يُسوَّى بسند قبض تلقائي (`_auto_settle_cash_sale`) بقيدٍ مستقل،
    فمقارنة قيد الفاتورة وحده تترك نصف الأثر خارج الفحص — يُضمّ هنا.
    البيان يحمل رقم الفاتورة (وهو مختلف بالضرورة) فلا يدخل البصمة.
    """
    journals = [invoice.journal] if invoice.journal_id else []
    payment_ids = list(
        CustomerPayment.objects.filter(auto_settled_invoice=invoice)
        .values_list("id", flat=True)
    )
    if payment_ids:
        journals += list(
            JournalHeader.objects.filter(
                tenant_id=invoice.tenant_id,
                reference_type="CUSTOMER_PAYMENT",
                reference_id__in=payment_ids,
            )
        )
    rows: list[tuple] = []
    for jh in journals:
        currency_code = jh.currency.Code if jh.currency_id else None
        for line in jh.lines.select_related("account").all():
            rows.append((
                line.account.code,
                Decimal(str(line.debit)),
                Decimal(str(line.credit)),
                currency_code,
            ))
    return sorted(rows, key=lambda r: (r[0], r[1], r[2], r[3] or ""))


def _effective_fields(invoice: SalesInvoice) -> tuple:
    """القيم التي حسمتها الافتراضات — تطابقها هو سببُ تطابق القيد، لا مصادفته.

    `revenue_account` مستثنى عمداً: حذفُه يتركه NULL على الصف، ويُحلّ عند الترحيل
    من `SalesSettings.default_revenue_account_product` نفسه
    (`sales/services/calc.py` → `_default_revenue_account`) — فالمخزَّن يختلف
    والمُرحَّل لا. البصمة أدناه هي التي تحكم، وهي حساب الإيراد بعينه.
    """
    return (
        invoice.currency_id,
        invoice.cash_or_bank_account_id,
        invoice.stock_on_post,
        invoice.prices_include_tax,
        invoice.due_date,
        invoice.invoice_type,
        Decimal(str(invoice.grand_total)),
    )


@pytest.mark.parametrize("invoice_type", ["cash", "credit"])
def test_simple_mode_invoice_posts_identical_journal(env, invoice_type):
    """معيار نجاح المهمة كلها: فاتورة الوضع السهل = فاتورة الوضع المتقدّم، قيداً بقيد."""
    tenant, owner, ils, cash, rev, tax, customer, product = env
    client = _client(owner, tenant)

    simple = _create_and_post(
        client, _simple_payload(customer, product, tax, invoice_type=invoice_type))
    advanced = _create_and_post(
        client,
        _explicit_payload(customer, product, tax, ils, cash, rev,
                          invoice_type=invoice_type),
    )

    # الافتراضات حُسمت إلى نفس القيم — وإلا كان التطابق أدناه مصادفةً لا قاعدة.
    assert _effective_fields(simple) == _effective_fields(advanced)

    simple_rows = _journal_fingerprint(simple)
    advanced_rows = _journal_fingerprint(advanced)
    assert simple_rows == advanced_rows

    # المقارنة تُقاس على قيدٍ حقيقيّ لا على فراغ: ذمم + إيراد + ضريبة مخرجات +
    # تكلفة/مخزون، ومع البيع المدفوع سطرا سند التسوية على الصندوق.
    codes = {row[0] for row in simple_rows}
    assert {rev.code, "2104"} <= codes
    assert (cash.code in codes) is (invoice_type == "cash")
    assert len(simple_rows) >= 5

    # القيد متوازن في الحالتين (فحصٌ مستقل عن المقارنة كي لا يمرّ خطآن متطابقان).
    for rows in (simple_rows, advanced_rows):
        assert sum(r[1] for r in rows) == sum(r[2] for r in rows)


def test_simple_mode_cash_sale_settles_to_the_same_cash_account(env):
    """حساب الصندوق مخفيٌّ في الوضع السهل — وتسويةُ البيع النقدي تصيبه هو نفسه."""
    tenant, owner, ils, cash, rev, tax, customer, product = env
    client = _client(owner, tenant)

    simple = _create_and_post(
        client, _simple_payload(customer, product, tax, invoice_type="cash"))

    payment = CustomerPayment.objects.get(auto_settled_invoice=simple)
    assert payment.cash_or_bank_account_id == cash.id
    simple.refresh_from_db()
    assert simple.amount_paid == simple.grand_total


def test_hidden_tax_inclusive_flag_must_stay_in_the_payload(env):
    """لماذا يُرسِل الوضع السهل قيمة «شامل الضريبة» المخفيّة بدل حذفها.

    `SalesInvoiceSerializer.create` يورّث من الإعدادات العميلَ والعملةَ ونوعَ الدفع
    وخصمَ المخزون وحسابَ الصندوق — لكن **لا** يورّث `prices_include_tax`، فالحذف
    يُسقط الحقل على افتراضِ الحقل نفسه (False) لا على إعداد الشركة. لذا القناع
    يُخفي الخانة ويُبقي قيمتها في الحمولة: الإخفاء عرضٌ لا حذف.
    """
    tenant, owner, ils, cash, rev, tax, customer, product = env
    ss = get_or_create_sales_settings(tenant)
    ss.prices_include_tax = True
    ss.save(update_fields=["prices_include_tax"])
    client = _client(owner, tenant)

    omitted = _create_and_post(
        client, _simple_payload(customer, product, tax, invoice_type="cash"))
    assert omitted.prices_include_tax is False  # لم يرث الإعداد

    sent = dict(_simple_payload(customer, product, tax, invoice_type="cash"))
    sent["prices_include_tax"] = True  # ما يفعله المحرّر فعلاً في الوضع السهل
    kept = _create_and_post(client, sent)
    assert kept.prices_include_tax is True
    # والفرق ماليّ حقيقي: 375 شاملة ⇒ وعاء أصغر وضريبة أقل.
    assert kept.grand_total < omitted.grand_total
