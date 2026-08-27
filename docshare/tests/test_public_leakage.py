"""معيار النجاح **السالب** لسطح المشاركة: إثبات غياب التسريب.

هذا الاختبار هو البوابة التي تُجيز صفحةً بلا مصادقة فوق ERP إنتاجي — نفس دور
`store/tests/test_public_leakage.py` لسطح المتجر، وبنفس ثلاث طبقاته:

1. **مساواة مجموعة المفاتيح** — `assert set(keys) == WHITELIST` لا
   `assert "avg_cost" not in keys`. الفرق جوهري: الغياب الفردي يحرس ما خطر
   ببالنا يوم كتابته، ومساواة المجموعة تُفشِل **كل** حقل يُضاف مستقبلاً بلا
   قرار واعٍ — بالبناء لا بالتعداد.
2. **مسحٌ للصفحة المُصيَّرة** — الطبقة الأولى تحرس المفاتيح؛ هذه تحرس القيم،
   فلو تسلّلت التكلفة داخل نصٍّ أو سمة HTML لأمسكتها.
3. **الأعمدة المؤجّلة** — إثبات أن التكلفة **لم تُحمَّل من القاعدة أصلاً**،
   فلا تسريب ممكن حتى بخطأ عرضٍ لاحق.
"""
import pytest

from docshare import services
from docshare.documents import (
    COMPANY_FIELDS,
    build_sales_invoice,
    build_sales_quotation,
    company_card,
    load_sales_invoice,
)
from docshare.models import DOC_SALES_INVOICE, DOC_SALES_QUOTATION
from docshare.tests.conftest import CUSTOMER_NOTE, SECRET_COST, SECRET_INTERNAL_NOTE

pytestmark = pytest.mark.django_db

#: العقد العام للمستند — كل مفتاح هنا قرارٌ واعٍ بنشره للعالم.
DOC_WHITELIST = {
    "kind", "title", "number", "date", "due_date", "valid_until",
    "status", "status_label", "notes", "lines", "totals",
    "show_payment", "can_decide",
    "customer_name", "customer_address", "customer_phone", "customer_tax_number",
    "currency_code", "currency_symbol",
}

LINE_WHITELIST = {
    "name", "name_en", "catalog_no", "note", "unit",
    "quantity", "unit_price", "line_discount", "tax_percent", "line_total",
}

TOTALS_WHITELIST = {
    "subtotal", "discount", "tax", "grand_total", "paid", "remaining",
}


def test_invoice_payload_keys_match_whitelist_exactly(invoice):
    payload = build_sales_invoice(load_sales_invoice(invoice.tenant_id, invoice.pk))
    assert set(payload) == DOC_WHITELIST
    assert set(payload["totals"]) == TOTALS_WHITELIST
    assert set(payload["lines"][0]) == LINE_WHITELIST


def test_quotation_payload_keys_match_whitelist_exactly(quotation):
    from docshare.documents import load_sales_quotation

    payload = build_sales_quotation(
        load_sales_quotation(quotation.tenant_id, quotation.pk)
    )
    assert set(payload) == DOC_WHITELIST
    assert set(payload["totals"]) == TOTALS_WHITELIST
    assert set(payload["lines"][0]) == LINE_WHITELIST


def test_company_card_keys_match_whitelist_exactly(env):
    card = company_card(env["tenant"])
    assert set(card) == set(COMPANY_FIELDS)


def test_rendered_page_never_shows_cost_or_internal_note(client, env, invoice):
    share = services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)
    html = client.get(f"/s/{share.token}").content.decode("utf-8")

    assert str(SECRET_COST) not in html, "تكلفة المنتج ظهرت على الصفحة العامة"
    assert SECRET_INTERNAL_NOTE not in html, "ملاحظة داخلية ظهرت على الصفحة العامة"
    # وما يجب أن يظهر ظهر فعلاً — الاختبار السالب بلا موجب يمرّ على صفحة فارغة.
    assert CUSTOMER_NOTE in html
    assert invoice.invoice_number in html


def test_cost_columns_are_not_even_loaded_from_the_database(invoice):
    """التكلفة ليست «غير معروضة» — هي غير محمَّلة. فرقٌ يمنع تسريباً بخطأ عرض."""
    document = load_sales_invoice(invoice.tenant_id, invoice.pk)
    deferred = document.get_deferred_fields()
    for hidden in ("amount_paid", "exchange_rate", "revenue_account",
                   "attached_cash_amount", "branch"):
        assert hidden in deferred or f"{hidden}_id" in deferred, (
            f"العمود {hidden} حُمِّل من القاعدة إلى السطح العام"
        )


def test_purchase_invoice_is_not_shareable(env, invoice):
    """`SalesInvoice` يخدم الشراء أيضاً — ومشاركته تسرّب المورّد إلى الزبون."""
    from sales.models import SalesInvoice

    invoice.invoice_kind = SalesInvoice.INVOICE_KIND_PURCHASE
    invoice.save(update_fields=["invoice_kind"])
    assert load_sales_invoice(invoice.tenant_id, invoice.pk) is None

    with pytest.raises(services.ShareNotFound):
        services.create_share(env["tenant"], DOC_SALES_INVOICE, invoice.pk)


def test_share_of_another_tenants_document_is_refused(env, invoice, base_currency):
    """عزل الشركة: مستند شركة أخرى غير موجود، لا ممنوع."""
    from django.contrib.auth.models import User
    from tenants.services import create_company

    other_owner = User.objects.create_user(username="other-share", password="x")
    other_tenant = create_company("شركة أخرى", other_owner)

    with pytest.raises(services.ShareNotFound):
        services.create_share(other_tenant, DOC_SALES_INVOICE, invoice.pk)


def test_quotation_page_shows_no_payment_figures(client, env, quotation):
    """«المدفوع/المتبقي» على عرض سعر كذبة — ولا يُعرض أصلاً."""
    share = services.create_share(env["tenant"], DOC_SALES_QUOTATION, quotation.pk)
    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "المتبقي" not in html
    assert quotation.quotation_number in html
