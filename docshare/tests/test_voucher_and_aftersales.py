"""قواعدُ خاصةٌ بالسندات وما بعد البيع — كلٌّ منها منعٌ مقصود لا صدفة.

اختبارُ القائمة البيضاء في `test_public_leakage` يدور على كل نوع ويقيس
المفاتيح. هذا الملف يقيس ما لا تراه المفاتيح: **متى يُرفض المستند أصلاً**،
وماذا يعني غيابُ جدولٍ أو غيابُ رقم.
"""
import pytest

from docshare import services
from docshare.documents import DOC_TYPES

pytestmark = pytest.mark.django_db


def _html(client, tenant, doc_type, doc):
    share = services.create_share(tenant, doc_type, doc.pk)
    return share, client.get(f"/s/{share.token}").content.decode("utf-8")


# ── السندات ─────────────────────────────────────────────────────────────────

def test_unposted_voucher_cannot_be_shared(env, cash_account):
    """ورقةُ إيصالٍ بيد الزبون على دفعةٍ لم تدخل الدفاتر تُنازَع ولا تُسحَب."""
    from sales.models import CustomerPayment

    draft = CustomerPayment.objects.create(
        tenant=env["tenant"], partner=env["customer"], payment_date="2026-08-08",
        amount=10, currency=env["currency"], cash_or_bank_account=cash_account,
        is_posted=False,
    )
    with pytest.raises(services.ShareNotFound):
        services.create_share(env["tenant"], "customer_payment", draft.pk)


def test_receipt_lists_the_invoices_it_settled_and_what_stayed_on_account(
    client, env, customer_payment, invoice
):
    """116 دُفعت و100 وُزِّعت ⇒ «على الحساب» 16 مشتقّةً طرحاً لا مقروءةً من عمود."""
    _, html = _html(client, env["tenant"], "customer_payment", customer_payment)

    assert "سند قبض" in html
    assert invoice.invoice_number in html, "الفاتورة المسدَّدة لم تُذكر على الإيصال"
    assert "على الحساب" in html
    assert "16" in html


def test_receipt_has_no_line_table(client, env, customer_payment):
    """سندٌ بجدول «الصنف/الوحدة/الكمية/ض.%» ضجيجٌ يُربك من يقرأ إيصالاً."""
    _, html = _html(client, env["tenant"], "customer_payment", customer_payment)
    assert "الوحدة" not in html
    assert "ض.%" not in html


def test_delivery_note_shows_quantities_without_any_price(
    client, env, delivery_order
):
    """سند التسليم كمياتٌ بلا أسعار — من يستلم ليس بالضرورة من يعرف الأسعار."""
    _, html = _html(client, env["tenant"], "delivery_order", delivery_order)

    assert "سند تسليم" in html
    assert "منتج المشاركة" in html
    assert "السعر" not in html
    assert "الإجمالي" not in html


# ── ما بعد البيع: وحدة مرخّصة ───────────────────────────────────────────────

def test_warranty_card_hides_the_supplier_behind_it(
    client, env, aftersales_tenant, warranty_card
):
    """كفالةُ مورّدنا شأنٌ بيننا وبينه — عرضُها يفتح تفاوضاً لا شأن للزبون به."""
    from partners.models import Partner

    backer = Partner.objects.create(
        tenant=aftersales_tenant, name="مورّد-الكفالة-الخفي", partner_type="Supplier",
    )
    warranty_card.supplier = backer
    warranty_card.supplier_warranty_end_date = "2099-01-01"
    warranty_card.save(update_fields=["supplier", "supplier_warranty_end_date"])

    _, html = _html(client, aftersales_tenant, "warranty_card", warranty_card)
    assert "مورّد-الكفالة-الخفي" not in html
    assert "بطاقة كفالة" in html
    assert "SN-SH-1" in html


def test_service_order_hides_the_estimate_until_it_is_approved(
    client, env, aftersales_tenant, service_order
):
    """رقمٌ داخليّ قبل الاعتماد يقرؤه الزبون التزاماً ثم يتغيّر — فيصير خُلفاً."""
    from decimal import Decimal

    service_order.estimated_amount = Decimal("321.45")
    service_order.save(update_fields=["estimated_amount"])

    _, html = _html(client, aftersales_tenant, "service_order", service_order)
    assert "321.45" not in html
    assert "التقدير المعتمد" not in html
    assert "لا يعمل" in html  # الشكوى تظهر — الاختبار السالب بلا موجب بلا قيمة


def test_approved_estimate_does_appear(
    client, env, aftersales_tenant, service_order
):
    from decimal import Decimal

    from django.utils import timezone

    service_order.estimated_amount = Decimal("321.45")
    service_order.approved_at = timezone.now()
    service_order.save(update_fields=["estimated_amount", "approved_at"])

    _, html = _html(client, aftersales_tenant, "service_order", service_order)
    assert "التقدير المعتمد" in html
    assert "321.45" in html


def test_turning_the_module_off_kills_a_live_link_with_410(
    client, env, aftersales_tenant, warranty_card
):
    """رابطٌ حيّ لوحدةٍ أُطفئت ⇒ **410 لا 404**: كان حيّاً يوماً، والزائر يفهم.

    وإبقاؤه عاملاً كان يعني أن وحدةً غير مشترَك بها تخدم صفحاتٍ للعالم.
    """
    from core.models import TenantModule
    from core.modules import invalidate_module_cache

    share, _ = _html(client, aftersales_tenant, "warranty_card", warranty_card)
    assert client.get(f"/s/{share.token}").status_code == 200

    TenantModule.objects.filter(
        tenant=aftersales_tenant, module_key="after_sales"
    ).update(enabled=False)
    invalidate_module_cache(aftersales_tenant.pk)

    assert client.get(f"/s/{share.token}").status_code == 410


def test_unlicensed_company_gets_404_not_403(env, warranty_card):
    """وحدةٌ غير مرخّصة تختفي كمسارٍ غير موجود — قرارٌ قائم في `core/modules.py`.

    وترتيبُ الفحصين هو ما يجعله صادقاً: **مديرٌ** يملك `"*"` من الصلاحيات، فلو
    سبقت الصلاحيةُ الترخيصَ لمرّ إلى 403 «ممنوع» — وهو إقرارٌ بوجود الوحدة.
    الاختبار يستعمل مديراً بالذات لهذا السبب.
    """
    from django.contrib.auth.models import User
    from rest_framework.test import APIClient

    from core.models import TenantModule
    from core.modules import invalidate_module_cache
    from tenants.models import UserCompanyMembership

    TenantModule.objects.filter(
        tenant=env["tenant"], module_key="after_sales"
    ).update(enabled=False)
    invalidate_module_cache(env["tenant"].pk)

    user = User.objects.create_user(username="unlicensed-sharer", password="x")
    UserCompanyMembership.objects.create(
        user=user, tenant=env["tenant"], role="manager",
    )
    api = APIClient()
    api.force_authenticate(user=user)
    api.credentials(HTTP_X_TENANT_ID=str(env["tenant"].TenantID))

    response = api.post(
        "/api/document-shares/",
        {"doc_type": "warranty_card", "doc_id": warranty_card.pk},
        format="json",
    )
    assert response.status_code == 404, response.data


def test_licensed_types_declare_their_module():
    """النوع الذي يعيش في وحدة مرخّصة يقولها في سجلّه لا في نيّة كاتبه."""
    for doc_type in ("warranty_card", "service_order"):
        assert DOC_TYPES[doc_type].get("module") == "after_sales", doc_type
