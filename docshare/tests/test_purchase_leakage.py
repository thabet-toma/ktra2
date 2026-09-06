"""ما يراه **المورّد** وما لا يراه — بوابة توسيع السطح إلى جانب الشراء.

الحجّة التي أجازت هذا التوسيع: الرقم على مستند الشراء هو السعر الذي كتبه
المورّد لنا، فهو يعرفه قبلنا — ومشاركتُه معه ليست كشفاً. لكن **الورقة نفسها
تحمل أرقاماً أخرى ليست له**: نسبةَ ربحنا، وتقديرَنا للشحن، وما تبقّى علينا،
ومن أين جئنا بالبضاعة، ومعدّلَ توزيع التكلفة المستوردة. هذا الملف هو ما يجعل
تلك الحجّة صادقةً بالكود لا بالنيّة.

**وثلاث طبقات لا واحدة، كما في `test_public_leakage`:** مجموعةُ المفاتيح
(هناك، بالدوران على كل نوع)، وقيمُ الصفحة المُصيَّرة (هنا)، والأعمدةُ التي لم
تُحمَّل من القاعدة أصلاً (هنا كذلك) — فحتى خطأُ عرضٍ لاحق لا يجد ما يعرضه.
"""
import pytest

from docshare import services
from docshare.documents import DOC_TYPES
from docshare.documents._contract import AUDIENCE_SUPPLIER
from docshare.tests.conftest import (
    SECRET_FEES_PERCENT,
    SECRET_INTERNAL_NOTE,
    SECRET_REMAINING,
    SECRET_SOURCE_LINK,
)

pytestmark = pytest.mark.django_db


def _renderings(value) -> tuple[str, ...]:
    """الصور التي قد يظهر بها رقمٌ على الصفحة — الخام والمجمَّع والمقصوص.

    البحث عن `str(value)` وحده يمرّ كاذباً: `7777.77` تُطبع «7,777.77» بمرشّح
    `money`، فاختبارٌ يبحث عن الأولى يقول «لا تسريب» والثانيةُ على الشاشة.
    """
    raw = str(value)
    grouped = f"{value:,}"
    return tuple({raw, grouped, raw.rstrip("0").rstrip(".")})


def _assert_absent(html: str, value, label: str) -> None:
    for form in _renderings(value):
        assert form not in html, f"{label} ظهر على صفحة المورّد بالصورة «{form}»"


def _share_html(client, tenant, doc_type, doc):
    share = services.create_share(tenant, doc_type, doc.pk)
    return client.get(f"/s/{share.token}").content.decode("utf-8")


def test_deal_page_hides_our_margin_our_source_and_what_we_still_owe(
    client, env, deal
):
    """الصفقة أغنى مستنداتنا بالحقول الحسّاسة — وأخطرُها لو خرجت كما هي."""
    html = _share_html(client, env["tenant"], "logistics_deal", deal)

    _assert_absent(html, SECRET_FEES_PERCENT, "نسبة الرسوم/الربح")
    _assert_absent(html, SECRET_REMAINING, "المتبقّي علينا")
    assert SECRET_SOURCE_LINK not in html, "رابط المصدر ظهر على صفحة المورّد"

    # وما يجب أن يظهر ظهر — الاختبار السالب بلا موجب يمرّ على صفحة فارغة.
    assert deal.ref_number in html
    assert "مصنع المشاركة" in html
    assert "FOB" in html


def test_supplier_offer_page_hides_the_source_link(client, env, supplier_offer):
    html = _share_html(client, env["tenant"], "supplier_quotation", supplier_offer)
    assert SECRET_SOURCE_LINK not in html
    assert supplier_offer.quotation_number in html


def test_local_purchase_page_hides_the_internal_note(
    client, env, local_purchase_invoice
):
    """ملاحظةُ الموظف لنفسه ليست للمورّد كما ليست للزبون — الفصل واحد."""
    html = _share_html(
        client, env["tenant"], "local_purchase_invoice", local_purchase_invoice
    )
    assert SECRET_INTERNAL_NOTE not in html
    assert local_purchase_invoice.invoice_number in html


@pytest.mark.parametrize(
    "doc_type,fixture,hidden",
    [
        (
            "purchase_invoice", "purchase_invoice",
            (
                "import_deal_remaining_rate", "import_shipment_remaining_rate",
                "import_use_cost_lines", "attached_cash_amount",
                "cash_or_bank_account", "journal", "exchange_rate", "is_posted",
            ),
        ),
        (
            "logistics_deal", "deal",
            (
                "fees_percentage", "remaining_amount", "shipping_cost_estimate",
                "alibaba_link", "price_offer_id", "installment_plan_enabled",
                "journal", "currency_rate", "is_posted",
            ),
        ),
        (
            "supplier_quotation", "supplier_offer",
            ("alibaba_link", "decision_reason", "notes_log", "attachments",
             "exchange_rate"),
        ),
    ],
)
def test_our_own_numbers_are_not_even_loaded_from_the_database(
    request, doc_type, fixture, hidden
):
    """الحقل ليس «غير معروض» — هو غير محمَّل. فرقٌ يمنع تسريباً بخطأ عرضٍ لاحق."""
    document = request.getfixturevalue(fixture)
    loaded = DOC_TYPES[doc_type]["loader"](document.tenant_id, document.pk)
    deferred = loaded.get_deferred_fields()
    for field in hidden:
        assert field in deferred or f"{field}_id" in deferred, (
            f"[{doc_type}] العمود {field} حُمِّل من القاعدة إلى صفحة المورّد"
        )


def test_every_purchase_type_declares_the_supplier_audience():
    """الجمهور ليس تعليقاً: الأنواع الخمسة كلها للمورّد، والحارس يقرؤه."""
    supplier_types = {
        "purchase_invoice", "purchase_order", "logistics_deal",
        "supplier_quotation", "local_purchase_invoice",
    }
    for doc_type in supplier_types:
        assert DOC_TYPES[doc_type]["audience"] == AUDIENCE_SUPPLIER, doc_type
        assert DOC_TYPES[doc_type]["permission"] == "purchase.document.share", doc_type


def test_local_purchase_cannot_be_shared_as_a_sales_invoice(env, local_purchase_invoice):
    """الحارس القديم لم يُرفَع: نوعٌ من الشراء لا يمرّ من باب البيع.

    التوسيع قرَن الحارسَ بمرآته ولم ينقضه — الحصر إيجابيّ على الجانبين.
    """
    from docshare.models import DOC_SALES_INVOICE

    with pytest.raises(services.ShareNotFound):
        services.create_share(
            env["tenant"], DOC_SALES_INVOICE, local_purchase_invoice.pk
        )


def test_sales_invoice_cannot_be_shared_as_a_local_purchase(env, invoice):
    """والعكس كذلك: فاتورة بيعٍ لا تخرج من باب الشراء بترويسة «المورّد»."""
    with pytest.raises(services.ShareNotFound):
        services.create_share(env["tenant"], "local_purchase_invoice", invoice.pk)


def test_estimated_price_is_still_deferred_on_the_public_path(
    client, env, purchase_rfq,
):
    """مواصفة #147 (المرحلة 3ب): نفس الحارس على الرابط **العامّ** — الباني
    واحدٌ لكلا الجمهورين، فالتحميل المحدود يسري عليهما معاً بلا تفرّع."""
    from docshare import services
    from docshare.documents import DOC_TYPES
    from docshare.documents.purchase_docs import build_purchase_rfq
    from docshare.models import DOC_PURCHASE_RFQ

    share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )
    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    from docshare.tests.conftest import SECRET_ESTIMATED_PRICE

    for form in (str(SECRET_ESTIMATED_PRICE), f"{SECRET_ESTIMATED_PRICE:,}"):
        assert form not in html, f"السعر التقديري ظهر على الرابط العامّ بالصورة «{form}»"

    document = DOC_TYPES["purchase_rfq"]["loader"](purchase_rfq.tenant_id, purchase_rfq.pk)
    line = document.lines.only("id").first()
    deferred = line.get_deferred_fields()
    assert "estimated_price" in deferred
    build_purchase_rfq(document)  # لا يرمي، ولا يستدعي `estimated_price` إطلاقاً


def test_product_image_reaches_the_public_rfq_payload(env, purchase_rfq):
    """مواصفة #147 (المرحلة 3ب): الصورة تصل الحمولة — لا `estimated_price`."""
    from docshare.documents import DOC_TYPES

    product = purchase_rfq.lines.first().product
    product.image_url = "https://cdn.example/products/shared-item.png"
    product.save(update_fields=["image_url"])

    document = DOC_TYPES["purchase_rfq"]["loader"](purchase_rfq.tenant_id, purchase_rfq.pk)
    payload = DOC_TYPES["purchase_rfq"]["builder"](document)
    line = payload["lines"][0]
    assert line["image_url"] == product.image_url


def test_public_rfq_page_shows_no_trace_of_other_respondents_not_even_a_count(
    client, env, purchase_rfq, rfq_recipient,
):
    """مواصفة #147 (المرحلة 3ب): لا أسعار غيرك، ولا أسماؤهم، **ولا حتى عددهم**
    — العددُ وحده معلومةُ تفاوضٍ («كم عرضاً وصل؟»). البناء هنا يضمن ذلك بنيوياً:
    `build_purchase_rfq` لا يستعلم `PublicSupplierQuoteRequest` إطلاقاً (يحرسه
    اختبار القائمة البيضاء أعلاه)، وهذا الاختبار يثبته بالقيم على صفحةٍ فعلية.
    """
    from docshare import services
    from docshare.models import DOC_PURCHASE_RFQ
    from logistics.services import record_public_quote_request, submit_rfq_supplier_quote

    line_id = purchase_rfq.lines.first().pk
    submit_rfq_supplier_quote(
        rfq_recipient, name="مصنع المشاركة السرّي", prices={line_id: "77.77"},
    )
    record_public_quote_request(
        purchase_rfq, name="غريبٌ أوّل", email="stranger-one@example.com",
        prices={line_id: "55.55"},
    )
    record_public_quote_request(
        purchase_rfq, name="غريبٌ ثانٍ", email="stranger-two@example.com",
        prices={line_id: "33.33"},
    )

    share = services.create_share(
        env["tenant"], DOC_PURCHASE_RFQ, purchase_rfq.pk, is_public=True,
    )
    html = client.get(f"/s/{share.token}").content.decode("utf-8")

    for leaked in (
        "مصنع المشاركة السرّي", "غريبٌ أوّل", "غريبٌ ثانٍ",
        "stranger-one@example.com", "stranger-two@example.com",
    ):
        assert leaked not in html, f"«{leaked}» ظهر على الرابط العامّ"
    for price in ("77.77", "55.55", "33.33"):
        assert price not in html, f"سعرٌ لمستجيبٍ آخر («{price}») ظهر على الرابط العامّ"


def test_arabic_page_never_shows_an_english_status_label(client, env, deal, supplier_offer):
    """`LogisticsDeal` و`SupplierQuotation` يحملان `choices` إنجليزية.

    فكانت الورقة التي تُرسَل إلى مصنعٍ صينيّ تعرض «Open» و«Draft» وسط عربية —
    وتصحيحُ النموذج يمسّ شاشاتٍ وتقاريرَ تعتمد نصّه، فالترجمة تسكن حيث تُعرض.
    """
    for doc_type, doc, english in (
        ("logistics_deal", deal, "Open"),
        ("supplier_quotation", supplier_offer, "Draft"),
    ):
        share = services.create_share(env["tenant"], doc_type, doc.pk)
        html = client.get(f"/s/{share.token}").content.decode("utf-8")
        badge = html.split('class="badge')[1].split("</span>")[0]
        assert english not in badge, f"[{doc_type}] شارة الحالة بالإنجليزية: {badge}"
