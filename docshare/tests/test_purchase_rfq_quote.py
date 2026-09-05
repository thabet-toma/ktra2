"""رابط المورّد الخاص على طلب عرض السعر — ISSUE #115 (مواصفة #108 §٥).

مسارٌ ثانٍ **مستقلّ تماماً** عن `record_decision`/`test_decision.py`: الكتابة
أسعارُ بنودٍ لا قرارَ قبول/رفض، وتُقبل مراراً ما دامت الطلبية «مُرسَلة» — لا
مرّةً واحدة كالقرار. يُحتذى بنيةُ `docshare/tests/test_public_leakage.py`
حرفياً للتسريب، و`test_decision.py`/`test_lifecycle.py` لدورة الحياة.
"""
from decimal import Decimal

import pytest

from docshare import services
from docshare.models import DOC_PURCHASE_RFQ, DocumentShare
from docshare.tests.conftest import SECRET_ESTIMATED_PRICE

pytestmark = pytest.mark.django_db


def _wire_share(env, rfq, recipient):
    """رابطٌ خاصٌّ لمستقبِلٍ بعينه — يحاكي ما تفعله `send/`/`recipients/` فعلياً
    (`logistics/views/procurement.py` — `_wire_rfq_recipient_shares`)."""
    share = services.create_share(env["tenant"], DOC_PURCHASE_RFQ, rfq.pk, dedupe=False)
    recipient.share = share
    recipient.save(update_fields=["share"])
    return share


def _renderings(value) -> tuple:
    """نفس تقنية `test_purchase_leakage._renderings` — القيمة تظهر خاماً أو
    مجمَّعةً بفواصل الآلاف (مرشّح `money`)."""
    raw = str(value)
    grouped = f"{value:,}"
    return tuple({raw, grouped, raw.rstrip("0").rstrip(".")})


# ── التسريب ──────────────────────────────────────────────────────────────

def test_supplier_page_never_shows_the_estimated_price_or_lowest_price(
    client, env, purchase_rfq, rfq_recipient,
):
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    html = client.get(f"/s/{share.token}").content.decode("utf-8")

    for form in _renderings(SECRET_ESTIMATED_PRICE):
        assert form not in html, f"السعر التقديري ظهر على صفحة المورّد بالصورة «{form}»"
    assert "أقل سعر" not in html
    # وما يجب أن يظهر ظهر فعلاً.
    assert purchase_rfq.rfq_number in html
    assert "مواصفات تجريبية" in html
    assert "قطعة" in html


def test_each_line_is_rendered_exactly_once_not_twice(
    client, env, purchase_rfq, rfq_recipient,
):
    """جدولان يمرّان على `doc.lines` نفسِها = كلُّ صنفٍ مرّتين أمام المورّد.

    القالبُ يفترض إطفاءَ الجدول العام لهذا النوع ويقوله في تعليقه، والباني لم
    يكن يمرّر `show_lines=False` — فالورقةُ التي يُسعِّر منها المورّد كانت تُظهر
    كلَّ بندٍ مكرَّراً بخانتَي سعرٍ لا واحدة. حارسٌ على العدد لا على الوجود.
    """
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    html = client.get(f"/s/{share.token}").content.decode("utf-8")

    line = purchase_rfq.lines.order_by("seq", "id").first()
    name = line.name_snapshot or (line.product and line.product.name_ar) or ""
    assert name, "البند بلا اسم — الاختبار نفسه لا معنى له حينها"
    assert html.count(name) == 1, (
        f"اسم البند «{name}» ظهر {html.count(name)} مرّة — الجدولان يتكرّران"
    )
    # وخانةُ السعر لكلّ بندٍ واحدةٌ لا اثنتان.
    assert html.count(f'name="price_{line.id}"') == 1


def test_estimated_price_is_not_even_loaded_from_the_database(purchase_rfq):
    from docshare.documents import DOC_TYPES

    document = DOC_TYPES["purchase_rfq"]["loader"](purchase_rfq.tenant_id, purchase_rfq.pk)
    line = document.lines.only("id").first()
    # التحميل هنا على مستوى بنود الطلبية يجري في `build_purchase_rfq` بأعمدة
    # محصورة لا تذكر `estimated_price` — القياس المباشر يكون على استعلام الباني
    # نفسه لا على تحميلٍ يدويّ لاحق قد يخفي الفرق.
    from docshare.documents.purchase_docs import build_purchase_rfq

    build_purchase_rfq(document)  # لا يرمي، ولا يستدعي `estimated_price` إطلاقاً


def test_page_title_follows_the_rfq_scope(client, env, purchase_rfq, rfq_recipient):
    """ISSUE #133 غ٥: العنوان كان ثابتاً («طلب عرض سعر») بلا تمييزٍ بين شراءٍ
    محلّي واستيراد."""
    from logistics.models import PurchaseRFQ

    share_local = _wire_share(env, purchase_rfq, rfq_recipient)
    local_html = client.get(f"/s/{share_local.token}").content.decode("utf-8")
    assert "طلب عرض سعر — شراء محلّي" in local_html
    assert "طلب عرض سعر — استيراد" not in local_html

    purchase_rfq.scope = PurchaseRFQ.SCOPE_IMPORT
    purchase_rfq.save(update_fields=["scope"])
    import_html = client.get(f"/s/{share_local.token}").content.decode("utf-8")
    assert "طلب عرض سعر — استيراد" in import_html


def test_two_suppliers_get_two_different_links_and_never_see_each_other(
    client, env, supplier, purchase_rfq, rfq_recipient,
):
    """رابطان لموردَين على الطلبية نفسها — كلٌّ منهما توكِنٌ مستقلّ."""
    from accounting.models import Account
    from logistics.models import PurchaseRFQRecipient
    from partners.models import Partner

    payable = Account.objects.create(
        tenant=env["tenant"], code="2102-SH", name="ذمم دائنة ٢",
        account_type="Liability", is_active=True,
    )
    supplier2 = Partner.objects.create(
        tenant=env["tenant"], name="مصنع ثانٍ", partner_type="Supplier",
        linked_account=payable, phone="0599222222",
    )
    recipient2 = PurchaseRFQRecipient.objects.create(
        tenant=env["tenant"], rfq=purchase_rfq, supplier=supplier2,
    )

    share1 = _wire_share(env, purchase_rfq, rfq_recipient)
    share2 = _wire_share(env, purchase_rfq, recipient2)
    assert share1.token != share2.token

    line_id = purchase_rfq.lines.first().pk
    client.post(
        f"/s/{share1.token}/quote/",
        {"name": "مصنع المشاركة", f"price_{line_id}": "10"},
    )
    # عرض المورّد الأوّل لا يظهر على رابط الثاني — الصفحة أصلاً بلا جدول عروضٍ
    # مقارَنة (`show_lines` للطلبية بلا أسعارٍ ثابتة)، فلا مسرَّبَ ممكناً.
    html2 = client.get(f"/s/{share2.token}").content.decode("utf-8")
    assert "10.0000" not in html2
    assert "مصنع المشاركة" not in html2


# ── الكتابة والتعديل ─────────────────────────────────────────────────────

def _line_id(rfq):
    return rfq.lines.first().pk


def test_writing_a_price_generates_a_supplier_quotation_linked_to_the_rfq(
    client, env, purchase_rfq, rfq_recipient,
):
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)

    response = client.post(
        f"/s/{share.token}/quote/",
        {"name": "أبو خالد", f"price_{line_id}": "55.5"},
    )
    assert response.status_code == 302

    rfq_recipient.refresh_from_db()
    assert rfq_recipient.replied_at is not None
    assert rfq_recipient.quotation_id is not None

    quotation = rfq_recipient.quotation
    assert quotation.rfq_id == purchase_rfq.pk
    assert quotation.supplier_id == rfq_recipient.supplier_id
    assert quotation.supplier_contact == "أبو خالد"
    assert quotation.lines.count() == 1
    line = quotation.lines.first()
    assert line.unit_price == Decimal("55.5000")
    assert quotation.grand_total == Decimal("555.00")  # 10 × 55.5

    share.refresh_from_db()
    assert share.decided_name == "أبو خالد"
    assert share.decided_ip != ""


def test_editing_the_price_updates_the_same_quotation_not_a_new_one(
    client, env, purchase_rfq, rfq_recipient,
):
    from logistics.models import SupplierQuotation

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)

    client.post(f"/s/{share.token}/quote/", {"name": "أول", f"price_{line_id}": "50"})
    rfq_recipient.refresh_from_db()
    first_quotation_id = rfq_recipient.quotation_id
    first_replied_at = rfq_recipient.replied_at

    client.post(f"/s/{share.token}/quote/", {"name": "أول مجدداً", f"price_{line_id}": "70"})
    rfq_recipient.refresh_from_db()

    assert rfq_recipient.quotation_id == first_quotation_id
    assert rfq_recipient.replied_at == first_replied_at  # وقت أوّل ردّ لا يتغيّر
    assert SupplierQuotation.objects.filter(rfq=purchase_rfq).count() == 1

    quotation = rfq_recipient.quotation
    assert quotation.lines.count() == 1  # لا يتضاعف — تحديثٌ في مكانه
    assert quotation.lines.first().unit_price == Decimal("70.0000")
    assert quotation.grand_total == Decimal("700.00")


def test_quote_without_a_name_is_refused(client, env, purchase_rfq, rfq_recipient):
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    response = client.post(f"/s/{share.token}/quote/", {"name": "  ", f"price_{line_id}": "10"})
    assert response.status_code == 409
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation_id is None


def test_quote_missing_a_line_price_is_refused(client, env, purchase_rfq, rfq_recipient):
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    response = client.post(f"/s/{share.token}/quote/", {"name": "بلا سعر كامل"})
    assert response.status_code == 409
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation_id is None


def test_a_validation_error_the_supplier_can_actually_trigger_is_shown_bilingually(
    client, env, purchase_rfq, rfq_recipient,
):
    """ISSUE #133 غ٤ (مراجعة الجولة الثانية): «رسائلُ التحقّق» بندٌ صريح في
    المواصفة ضمن ما يجب أن يظهر بلغتين — سعرٌ ناقصٌ خطأٌ يقع فيه مورّدٌ
    حقيقيّ عن غير قصد، لا حالة تلاعبٍ بالنموذج. مورّدٌ يقف عند رسالةٍ لا
    يقرؤها توقّف تماماً في اللحظة التي حاول فيها أن يساعد."""
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    response = client.post(f"/s/{share.token}/quote/", {"name": "بلا سعر كامل"})
    assert response.status_code == 409
    html = response.content.decode("utf-8")
    assert "الرجاء إدخال سعر لكل بند." in html
    assert "Please enter a price for every line." in html


# ── إغلاق الطلبية ────────────────────────────────────────────────────────

def test_quote_is_rejected_once_the_rfq_is_awarded(client, env, purchase_rfq, rfq_recipient):
    from logistics.models import PurchaseRFQ

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)

    purchase_rfq.status = PurchaseRFQ.STATUS_AWARDED
    purchase_rfq.save(update_fields=["status"])

    response = client.post(
        f"/s/{share.token}/quote/", {"name": "متأخر", f"price_{line_id}": "10"},
    )
    assert response.status_code == 409
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation_id is None


def test_quote_is_rejected_once_the_rfq_is_cancelled(client, env, purchase_rfq, rfq_recipient):
    from logistics.models import PurchaseRFQ

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)

    purchase_rfq.status = PurchaseRFQ.STATUS_CANCELLED
    purchase_rfq.save(update_fields=["status"])

    response = client.post(
        f"/s/{share.token}/quote/", {"name": "متأخر", f"price_{line_id}": "10"},
    )
    assert response.status_code == 409


def test_page_hides_the_price_boxes_once_closed(client, env, purchase_rfq, rfq_recipient):
    from logistics.models import PurchaseRFQ

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    purchase_rfq.status = PurchaseRFQ.STATUS_AWARDED
    purchase_rfq.save(update_fields=["status"])

    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    # لا صناديق سعرٍ ولا نموذج إرسال — الجملة نفسها («إرسال الأسعار») تظهر
    # أيضاً داخل نصّ الإغلاق، فالفحص على عنصر النموذج لا على الجملة.
    assert 'name="price_' not in html
    assert 'id="rfq-quote-form"' not in html
    assert "لم يعد بالإمكان إرسال الأسعار" in html


# ── دورة حياة الرابط ─────────────────────────────────────────────────────

def test_expired_link_is_410(client, env, purchase_rfq, rfq_recipient):
    from datetime import timedelta

    from django.utils import timezone

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    DocumentShare.objects.filter(pk=share.pk).update(
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    assert client.get(f"/s/{share.token}").status_code == 410
    line_id = _line_id(purchase_rfq)
    response = client.post(
        f"/s/{share.token}/quote/", {"name": "متأخر", f"price_{line_id}": "10"},
    )
    assert response.status_code == 410


def test_revoked_link_is_410(client, env, purchase_rfq, rfq_recipient):
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    services.revoke_share(share)
    line_id = _line_id(purchase_rfq)
    response = client.post(
        f"/s/{share.token}/quote/", {"name": "بعد الإبطال", f"price_{line_id}": "10"},
    )
    assert response.status_code == 410
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation_id is None


# ── عزل الشركة ───────────────────────────────────────────────────────────

def test_share_of_another_tenants_rfq_is_refused(env, purchase_rfq):
    from django.contrib.auth.models import User
    from tenants.services import create_company

    other_owner = User.objects.create_user(username="other-rfq-share", password="x")
    other_tenant = create_company("شركة أخرى للطلبيات", other_owner)

    with pytest.raises(services.ShareNotFound):
        services.create_share(other_tenant, DOC_PURCHASE_RFQ, purchase_rfq.pk)


def test_a_live_link_does_not_leak_into_another_tenant_even_by_id_guessing(
    client, env, base_currency, purchase_rfq, rfq_recipient,
):
    """توكِنٌ صحيح يحلّ إلى صاحبه دائماً — ‏`share.tenant_id` من الصفّ نفسه لا
    من الطلب الوارد، فلا معنى لمحاولة «فتحه من شركة أخرى»: هويّة الشركة
    مقفلة داخل الرابط لحظة إصداره."""
    from django.contrib.auth.models import User
    from tenants.services import create_company

    other_owner = User.objects.create_user(username="other-rfq-viewer", password="x")
    create_company("شركة ثالثة", other_owner)

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    response = client.get(f"/s/{share.token}")
    assert response.status_code == 200
    assert share.tenant_id == env["tenant"].pk



# ── ISSUE #115 (سدُّ ثغرة): المورّدُ العائد يجد أسعارَه ولا يجد أسعارَ غيره ──

def test_returning_supplier_finds_own_prices_prefilled(
    client, env, purchase_rfq, rfq_recipient,
):
    """«يمكنكم التعديل» وعدٌ لا يُوفى إن عاد المورّد إلى خاناتٍ فارغةٍ كلِّها —
    فيضطرّ أن يعيد كتابة كلّ سعرٍ كي يصحّح واحداً."""
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    client.post(f"/s/{share.token}/quote/", {"name": "مصنع العودة", f"price_{line_id}": "11.5"})

    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert 'value="11.5000"' in html


def test_prefill_never_shows_a_rivals_price_on_this_link(
    client, env, supplier, purchase_rfq, rfq_recipient,
):
    """التعبئةُ تجري في طبقة العرض حيث الرابط معروف — فالحارسُ شرطان لا واحد:
    أن يرى المورّدُ سعرَه، **وألّا يرى سعرَ منافسه**."""
    from partners.models import Partner
    from logistics.models import PurchaseRFQRecipient

    rival = Partner.objects.create(
        tenant=env["tenant"], name="مورّد منافس", partner_type="Supplier",
        linked_account=supplier.linked_account, phone="0599333333",
    )
    rival_recipient = PurchaseRFQRecipient.objects.create(
        tenant=env["tenant"], rfq=purchase_rfq, supplier=rival,
    )
    share_mine = _wire_share(env, purchase_rfq, rfq_recipient)
    share_rival = _wire_share(env, purchase_rfq, rival_recipient)

    line_id = _line_id(purchase_rfq)
    client.post(f"/s/{share_mine.token}/quote/", {"name": "أنا", f"price_{line_id}": "11.5"})
    client.post(f"/s/{share_rival.token}/quote/", {"name": "منافس", f"price_{line_id}": "99.5"})

    mine = client.get(f"/s/{share_mine.token}").content.decode("utf-8")
    assert 'value="11.5000"' in mine
    assert "99.5" not in mine

    rival_html = client.get(f"/s/{share_rival.token}").content.decode("utf-8")
    assert 'value="99.5000"' in rival_html
    # القيمة المعبّأة وحدها، لا الرقم الخام: «11.5» يظهر في CSS الصفحة
    # (`font-size:11.5px`) فيُنتج إخفاقاً كاذباً.
    assert 'value="11.5000"' not in rival_html


# ── ISSUE #122 (حارسُ عدم الانحدار): المسارُ العامّ لم يتغيّر بحرف ──────────

def test_public_link_still_refuses_a_partially_priced_reply(
    client, env, purchase_rfq, rfq_recipient,
):
    """«غير متوفّر» بابٌ فُتح للمحرِّر الداخليّ وحدَه — لا لنموذج المورّد.

    الرقمُ الناقصُ على الرابط لا يُقرأ «لا أحمله» بل «نسيتُ الخانة»: لا أحدَ
    خلفه يسأل. فالقاعدةُ هناك تبقى سعراً لكلّ بند، وتوسيعُ ما حولها لا يجوز
    أن يُرخيها.
    """
    from logistics.models import PurchaseRFQLine

    second = PurchaseRFQLine.objects.create(
        tenant=env["tenant"], rfq=purchase_rfq, seq=2,
        name_snapshot="بند ثانٍ", quantity=Decimal("4"), unit_of_measure="قطعة",
    )
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    first = _line_id(purchase_rfq)

    half = client.post(
        f"/s/{share.token}/quote/", {"name": "نصف جواب", f"price_{first}": "10"},
    )
    assert half.status_code == 409
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation_id is None

    # وبالسعرين معاً يمرّ — فالرفضُ أعلاه سببه النقصُ لا شيءٌ آخر.
    whole = client.post(
        f"/s/{share.token}/quote/",
        {"name": "جواب كامل", f"price_{first}": "10", f"price_{second.pk}": "20"},
    )
    assert whole.status_code == 302
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation.lines.count() == 2


# ── ISSUE #133 غ٢: عملة المورّد الأجنبيّ ─────────────────────────────────

def test_quote_page_offers_a_currency_selector_defaulting_to_base(
    client, env, purchase_rfq, rfq_recipient,
):
    """عملةٌ **بسعر صرفٍ قابلٍ للحسم اليوم** تدخل الاختيار — بلا سعرٍ مسجَّل
    لا مكان لها فيه (انظر الاختبار التالي)."""
    from datetime import date

    from accounting.models import ExchangeRate
    from tenants.models import Currency

    usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
    ExchangeRate.objects.create(
        tenant=env["tenant"], from_currency=usd, to_currency=env["currency"],
        rate=Decimal("3.7"), effective_date=date(2020, 1, 1),
    )
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    html = client.get(f"/s/{share.token}").content.decode("utf-8")

    assert 'name="currency"' in html
    assert ">ILS<" in html or "ILS" in html
    assert ">USD<" in html or "USD" in html


def test_currency_options_exclude_a_currency_with_no_configured_rate(
    client, env, purchase_rfq, rfq_recipient,
):
    """عملةٌ بلا سعر صرفٍ مسجَّل لا تدخل القائمة أصلاً — لا نعرض اختياراً لا
    نحسن تحويله، فلا يُحفظ سعرٌ ملفَّق (١) عند القبول عليه لاحقاً."""
    from tenants.models import Currency

    Currency.objects.create(Code="EUR", Name="يورو", IsBaseCurrency=False)
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    html = client.get(f"/s/{share.token}").content.decode("utf-8")

    assert "ILS" in html
    assert "EUR" not in html


def test_submitting_a_currency_with_no_configured_rate_is_refused_not_defaulted(
    client, env, purchase_rfq, rfq_recipient,
):
    """محاكاةُ نموذجٍ مُتلاعَبٍ به (عملةٌ لم تُعرَض في القائمة أصلاً) —
    يُرفَض صراحةً بدل تخزين سعر صرفٍ ملفَّق ١. هذا هو بالضبط العطب الذي
    كتبت هذه التذكرة لإغلاقه: لا يجوز أن يعود بابٌ خلفيّ إليه."""
    from tenants.models import Currency

    eur = Currency.objects.create(Code="EUR", Name="يورو", IsBaseCurrency=False)
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)

    response = client.post(
        f"/s/{share.token}/quote/",
        {"name": "مصنع أوروبي", f"price_{line_id}": "10", "currency": str(eur.pk)},
    )
    assert response.status_code == 409
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation_id is None


def test_supplier_priced_in_a_foreign_currency_is_stored_in_that_currency(
    client, env, purchase_rfq, rfq_recipient,
):
    """مورّدٌ صينيّ يكتب ١٠ يقصد دولارات — قبل هذه التذكرة كانت تُحفظ ١٠
    شيكلاً بصمت (العملة الأساسية دائماً)، أرخص مما هي حقيقةً فيربح أفضلَ
    عرضٍ بالمقارنة وهو ليس كذلك."""
    from datetime import date

    from accounting.models import ExchangeRate
    from tenants.models import Currency

    usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
    ExchangeRate.objects.create(
        tenant=env["tenant"], from_currency=usd, to_currency=env["currency"],
        rate=Decimal("3.7"), effective_date=date(2020, 1, 1),
    )
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)

    response = client.post(
        f"/s/{share.token}/quote/",
        {"name": "مصنع أجنبي", f"price_{line_id}": "10", "currency": str(usd.pk)},
    )
    assert response.status_code == 302

    rfq_recipient.refresh_from_db()
    quotation = rfq_recipient.quotation
    assert quotation.currency_id == usd.pk
    assert quotation.exchange_rate == Decimal("3.700000")
    # السعر المخزَّن بعملة المورّد نفسها — ١٠ دولارات لا ١٠ شواكل.
    assert quotation.lines.first().unit_price == Decimal("10.0000")


def test_foreign_currency_quote_is_converted_in_the_comparison_matrix(
    client, env, purchase_rfq, rfq_recipient,
):
    from datetime import date

    from accounting.models import ExchangeRate
    from tenants.models import Currency

    usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
    ExchangeRate.objects.create(
        tenant=env["tenant"], from_currency=usd, to_currency=env["currency"],
        rate=Decimal("3.7"), effective_date=date(2020, 1, 1),
    )
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    client.post(
        f"/s/{share.token}/quote/",
        {"name": "مصنع أجنبي", f"price_{line_id}": "10", "currency": str(usd.pk)},
    )

    from django.contrib.auth.models import User
    from rest_framework.test import APIClient

    api = APIClient()
    api.force_authenticate(user=env["owner"])
    api.credentials(HTTP_X_TENANT_ID=str(env["tenant"].pk))
    response = api.get(f"/api/logistics/purchase-rfqs/{purchase_rfq.pk}/comparison/")
    assert response.status_code == 200, response.content
    supplier_row = response.data["suppliers"][0]
    assert supplier_row["currency_code"] == "USD"
    # ١٠ دولارات × ٣٫٧ = ٣٧ بالعملة الأساسية — لا ١٠ شواكل.
    assert supplier_row["prices"][str(line_id)] == "37.0000"


def test_currency_missing_from_submission_defaults_to_base_as_before(
    client, env, purchase_rfq, rfq_recipient,
):
    """رابطٌ لم يُحدَّث بعد (أو نموذجٌ قديم مخزَّن في المتصفّح) بلا حقل عملة —
    السلوك يبقى حرفياً كما قبل هذه التذكرة: عملة الأساس."""
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    response = client.post(
        f"/s/{share.token}/quote/", {"name": "بلا عملة", f"price_{line_id}": "10"},
    )
    assert response.status_code == 302
    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation.currency_id == env["currency"].pk
    assert rfq_recipient.quotation.exchange_rate == Decimal("1")


def test_public_link_stamps_supplier_link_and_the_rfq_line_lineage(
    client, env, purchase_rfq, rfq_recipient,
):
    """العمودُ الذي سعّره المورّدُ بنفسه يُختَم كذلك — لا يُستنتَج لاحقاً."""
    from logistics.models import SupplierQuotation

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    response = client.post(
        f"/s/{share.token}/quote/", {"name": "أبو خالد", f"price_{line_id}": "12"},
    )
    assert response.status_code == 302

    rfq_recipient.refresh_from_db()
    quotation = rfq_recipient.quotation
    assert quotation.entry_source == SupplierQuotation.ENTRY_SUPPLIER_LINK
    # ونَسَبُ السطر يُكتَب هنا أيضاً — المصفوفةُ تطابق بالنَسَب لا بالترتيب.
    assert quotation.lines.first().rfq_line_id == line_id


# ── ISSUE #133 غ٣ (مواصفة #130 §١): ملاحظتان لا حقلٌ واحد ──────────────────
#
# نصّ المورّد نفسه على السطر، وملاحظةٌ عامّة على الطلبية كلّها — كلاهما يُكتب
# من رابط المورّد العام وحده (`submit_rfq_supplier_quote`)، ودمجهما مع تعليقنا
# الداخلي هو بعينه محو الأصل. انظر أيضاً `docshare/documents/purchase_docs.py`
# (`build_purchase_rfq`, `QUOTE_PURCHASE_RFQ`) و`docshare/views.py`
# (`_attach_quote_prefill`).

def test_supplier_line_note_is_stored_and_comes_back_on_read(
    client, env, purchase_rfq, rfq_recipient,
):
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    response = client.post(
        f"/s/{share.token}/quote/",
        {
            "name": "أبو خالد", f"price_{line_id}": "10",
            f"note_{line_id}": "عندي مقاس آخر فقط، الباقي مطابق",
        },
    )
    assert response.status_code == 302

    rfq_recipient.refresh_from_db()
    line = rfq_recipient.quotation.lines.first()
    assert line.supplier_note == "عندي مقاس آخر فقط، الباقي مطابق"

    # ويعود على القراءة أيضاً — يُعبّأ في خانة الملاحظات حين يفتح المورّد رابطه
    # ثانية، بنفس منطق تعبئة السعر (`_rfq_quote_prefill`).
    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "عندي مقاس آخر فقط، الباقي مطابق" in html


def test_supplier_general_note_for_the_whole_rfq_is_stored_and_returned(
    client, env, purchase_rfq, rfq_recipient,
):
    """المورّد قد يردّ على الطلبية ككلّ («لا نورّد لهذه المنطقة») — ولا موضع
    لذلك في سطر."""
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    response = client.post(
        f"/s/{share.token}/quote/",
        {
            "name": "أبو خالد", f"price_{line_id}": "10",
            "general_note": "لا نورّد لهذه المنطقة حالياً",
        },
    )
    assert response.status_code == 302

    rfq_recipient.refresh_from_db()
    assert rfq_recipient.quotation.general_note == "لا نورّد لهذه المنطقة حالياً"

    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "لا نورّد لهذه المنطقة حالياً" in html


def test_internal_note_never_alters_the_suppliers_text_and_no_platform_path_can_edit_it(
    client, env, purchase_rfq, rfq_recipient,
):
    """حارسُ سلامة الدليل (T-132): نصّ المورّد بايتاً بايت بعد أن نكتب ملاحظتنا
    الداخلية، ومحرِّرُ العروض الداخليّ — السطح الوحيد الذي يعدّل عرضاً بعد
    إنشائه — لا يقدر أن يمسّه: `supplier_note` للقراءة فقط بنيوياً في مُسلسِله،
    لا فرعَ تحقّقٍ يتجاهل قيمةً وصلت."""
    from logistics.serializers.procurement import SupplierQuotationLineSerializer

    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    client.post(
        f"/s/{share.token}/quote/",
        {
            "name": "أبو خالد", f"price_{line_id}": "10",
            f"note_{line_id}": "نصّ المورّد الأصلي",
        },
    )
    rfq_recipient.refresh_from_db()
    line = rfq_recipient.quotation.lines.first()
    assert line.supplier_note == "نصّ المورّد الأصلي"

    # الحقل للقراءة فقط بنيوياً في المُسلسِل الداخليّ — لا اعتماد على أن يتذكّر
    # كلّ فرعٍ ألّا يكتبه.
    assert SupplierQuotationLineSerializer().fields["supplier_note"].read_only

    # ولو حاول أحدٌ تمريره في تعديلٍ يدويّ عبر المُسلسِل نفسه، النصّ لا يتغيّر.
    serializer = SupplierQuotationLineSerializer(
        instance=line, data={"supplier_note": "تلاعب"}, partial=True,
    )
    serializer.is_valid(raise_exception=True)
    saved = serializer.save()
    saved.refresh_from_db()
    assert saved.supplier_note == "نصّ المورّد الأصلي"

    # وكتابةُ ملاحظتنا الداخلية على نفس السطر لا تمسّ نصّ المورّد بحرف.
    line.internal_note = "نتحقّق من هذا مع المستودع"
    line.save(update_fields=["internal_note"])
    line.refresh_from_db()
    assert line.supplier_note == "نصّ المورّد الأصلي"


def test_comparison_matrix_carries_the_suppliers_note_and_our_reply_never_leaks_to_the_public_page(
    client, env, purchase_rfq, rfq_recipient,
):
    """ملاحظةُ المورّد سببُ وجود المصفوفة أصلاً («هذا ما عندي بدل ما طلبت») —
    وتعليقُنا الداخليّ يظهر **بجانبها في هذه الشاشة المصادَق عليها وحدها**
    (مراجعة الجولة الثانية — مصفوفة المقارنة هي نقطة كتابته أيضاً، انظر
    `logistics/tests/test_purchase_rfq_award_and_comparison.py`)، ولا يخرج
    أبداً إلى السطح العامّ بلا مصادقة الذي يفتحه المورّد نفسه."""
    share = _wire_share(env, purchase_rfq, rfq_recipient)
    line_id = _line_id(purchase_rfq)
    client.post(
        f"/s/{share.token}/quote/",
        {
            "name": "أبو خالد", f"price_{line_id}": "10",
            f"note_{line_id}": "ملاحظة المورّد الظاهرة",
        },
    )
    rfq_recipient.refresh_from_db()
    line = rfq_recipient.quotation.lines.first()
    line.internal_note = "سرّنا-الداخلي-لا-يخرج-للمورّد"
    line.save(update_fields=["internal_note"])

    from rest_framework.test import APIClient

    api = APIClient()
    api.force_authenticate(user=env["owner"])
    api.credentials(HTTP_X_TENANT_ID=str(env["tenant"].pk))
    response = api.get(f"/api/logistics/purchase-rfqs/{purchase_rfq.pk}/comparison/")
    assert response.status_code == 200, response.content
    supplier_row = response.data["suppliers"][0]
    assert supplier_row["notes"][str(line_id)] == "ملاحظة المورّد الظاهرة"
    # الشاشة المصادَق عليها **تعرض** التعليق الداخليّ الآن — هذا هو مكانه
    # الطبيعيّ (مصفوفة المقارنة، لا محرّر العروض)، لا تسريباً.
    assert (
        supplier_row["internal_notes"][str(line_id)]["text"]
        == "سرّنا-الداخلي-لا-يخرج-للمورّد"
    )

    # وعلى السطح العامّ الذي يفتحه المورّد نفسه — الغائب دائماً بلا استثناء.
    public_html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "سرّنا-الداخلي-لا-يخرج-للمورّد" not in public_html
