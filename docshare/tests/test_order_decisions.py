"""قرارُ الطرف الآخر على الطلبيتين — قبولٌ يغيّر الحالة، ورفضٌ لا يغلق باباً.

**القاعدة التي تحكم هذا الملف كلّه:** `cancelled` طريقٌ بلا رجعة في هذا
المستودع — لا مسار «إلغاء الإلغاء» في شاشةٍ ولا في خدمة، والطلبية الملغاة لا
تُحوَّل إلى فاتورة، وإلغاءُ طلبية البيع **يُفرِج عن الكمية المحجوزة**. فجعلُ
ضغطةٍ من رابطٍ بلا تحقّق هويّة تغلق ذلك الباب مخاطرةٌ لا يقابلها مكسب. Odoo
يُلغي عند الرفض لأن بوابته خلف حساب مورّدٍ معروف؛ وهذا رابطٌ يحمله من يحمله.
"""
import pytest

from docshare import services
from docshare.models import DECISION_ACCEPTED, DECISION_REJECTED

pytestmark = pytest.mark.django_db


def _decide(client, tenant, doc_type, doc, decision, name="مسؤول المشتريات", note=""):
    share = services.create_share(tenant, doc_type, doc.pk)
    response = client.post(
        f"/s/{share.token}/decision/",
        {"decision": decision, "name": name, "note": note},
    )
    share.refresh_from_db()
    doc.refresh_from_db()
    return share, response


# ── أمر الشراء: قرار المورّد ────────────────────────────────────────────────

def test_supplier_acceptance_confirms_the_purchase_order(client, env, purchase_order):
    from logistics.models import PurchaseOrder

    assert purchase_order.status == PurchaseOrder.STATUS_DRAFT
    share, response = _decide(
        client, env["tenant"], "purchase_order", purchase_order, DECISION_ACCEPTED,
        name="مدير المصنع",
    )
    assert response.status_code == 302
    assert purchase_order.status == PurchaseOrder.STATUS_CONFIRMED
    assert share.decision == DECISION_ACCEPTED
    assert share.decided_name == "مدير المصنع"


def test_supplier_rejection_records_the_refusal_without_cancelling(
    client, env, purchase_order
):
    """الرفض يُسجَّل باسمه وسببه — والحالة لا تتحرّك، والإلغاء قرارُ صاحبها."""
    from logistics.models import PurchaseOrder

    share, response = _decide(
        client, env["tenant"], "purchase_order", purchase_order, DECISION_REJECTED,
        name="مدير المصنع", note="السعر أقل من كلفتنا",
    )
    assert response.status_code == 302
    assert purchase_order.status == PurchaseOrder.STATUS_DRAFT, (
        "الرفض أغلق باباً لا رجعة منه من رابطٍ بلا تحقّق هويّة"
    )
    assert purchase_order.cancel_reason == ""
    assert share.decision == DECISION_REJECTED
    assert share.decided_note == "السعر أقل من كلفتنا"


def test_the_refusal_reason_reaches_the_page_and_the_activity_log(
    client, env, purchase_order
):
    """«رفض المصنع» بلا «لماذا» تُلزم الموظف بمكالمة ليعرف ما يسعه الحقل."""
    from core.models import ActivityLog

    share, _ = _decide(
        client, env["tenant"], "purchase_order", purchase_order, DECISION_REJECTED,
        note="الكمية غير متوفرة قبل آذار",
    )
    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "الكمية غير متوفرة قبل آذار" in html

    entry = ActivityLog.objects.filter(entity_type="purchase_order").latest("id")
    assert "الكمية غير متوفرة قبل آذار" in entry.description


def test_an_already_confirmed_order_shows_no_buttons_and_refuses_a_posted_decision(
    client, env, purchase_order
):
    from logistics.models import PurchaseOrder

    purchase_order.status = PurchaseOrder.STATUS_CONFIRMED
    purchase_order.save(update_fields=["status"])

    share = services.create_share(env["tenant"], "purchase_order", purchase_order.pk)
    html = client.get(f"/s/{share.token}").content.decode("utf-8")
    assert "قبول الطلبية" not in html

    response = client.post(
        f"/s/{share.token}/decision/", {"decision": DECISION_ACCEPTED, "name": "فلان"},
    )
    assert response.status_code == 409
    assert "لم يعد هذا الأمر قابلاً للقرار" in response.content.decode("utf-8")


def test_an_order_without_lines_says_so_instead_of_failing_silently(client, env, supplier):
    from logistics.models import PurchaseOrder

    empty = PurchaseOrder.objects.create(
        tenant=env["tenant"], order_number="SH-PO-EMPTY", supplier=supplier,
        order_date="2026-08-03", currency=env["currency"],
    )
    share = services.create_share(env["tenant"], "purchase_order", empty.pk)
    response = client.post(
        f"/s/{share.token}/decision/", {"decision": DECISION_ACCEPTED, "name": "فلان"},
    )
    assert response.status_code == 409
    assert "بلا بنود" in response.content.decode("utf-8")


# ── طلبية الزبون: قرار الزبون ───────────────────────────────────────────────

def test_customer_confirmation_reserves_the_goods(client, env, sales_order):
    """التأكيد يحجز — وهو أثرٌ مقصود لا جانبيّ، ونفس ما يفعله زرّ الشاشة."""
    from sales.models import SalesOrder

    assert sales_order.status == SalesOrder.STATUS_DRAFT
    share, response = _decide(
        client, env["tenant"], "sales_order", sales_order, DECISION_ACCEPTED,
        name="أبو أحمد",
    )
    assert response.status_code == 302
    assert sales_order.status == SalesOrder.STATUS_CONFIRMED
    assert sales_order.reserved_until is not None, "التأكيد بلا حجز ليس تأكيداً"
    assert share.decided_name == "أبو أحمد"


def test_customer_rejection_does_not_release_stock_by_cancelling(
    client, env, sales_order
):
    from sales.models import SalesOrder

    _, response = _decide(
        client, env["tenant"], "sales_order", sales_order, DECISION_REJECTED,
        name="أبو أحمد", note="غيّرت رأيي",
    )
    assert response.status_code == 302
    assert sales_order.status == SalesOrder.STATUS_DRAFT
    assert sales_order.cancel_reason == ""


def test_a_shortage_reaches_the_visitor_as_arabic_text_not_a_500(
    client, env, sales_order
):
    """`confirm_sales_order` يرمي عند نقص الكمية.

    بلا لفٍّ في `record_decision` كان الاستثناء يصعد إلى **500 بصفحة بيضاء**،
    فيضغط الزبون ثانيةً وثالثة ولا يعرف أن السبب نفادُ المخزون.
    """
    from decimal import Decimal

    product = env["product"]
    product.quantity_on_hand = Decimal("0")
    product.save(update_fields=["quantity_on_hand"])

    share = services.create_share(env["tenant"], "sales_order", sales_order.pk)
    response = client.post(
        f"/s/{share.token}/decision/",
        {"decision": DECISION_ACCEPTED, "name": "أبو أحمد"},
    )
    assert response.status_code == 409, response.status_code
    body = response.content.decode("utf-8")
    assert "لعدم كفاية الكمية" in body
    # والصفحة تُعاد كاملةً لا شاشة خطأ عارية — الزائر يرى مستنده والسبب معاً.
    assert sales_order.order_number in body


def test_a_decision_is_recorded_once_only(client, env, purchase_order):
    """ضغطتان على «قبول» من جوّالٍ بطيء طلبان — والثاني يرتدّ لا يُعيد الكتابة."""
    share = services.create_share(env["tenant"], "purchase_order", purchase_order.pk)
    first = client.post(
        f"/s/{share.token}/decision/", {"decision": DECISION_ACCEPTED, "name": "فلان"},
    )
    second = client.post(
        f"/s/{share.token}/decision/", {"decision": DECISION_REJECTED, "name": "فلان"},
    )
    assert first.status_code == 302
    assert second.status_code == 409
    share.refresh_from_db()
    assert share.decision == DECISION_ACCEPTED


def test_documents_that_take_no_decision_still_refuse_one(client, env, deal):
    """الصفقة وفاتورة الشراء لا تقبلان قراراً — والرفض صريح لا صامت."""
    share = services.create_share(env["tenant"], "logistics_deal", deal.pk)
    response = client.post(
        f"/s/{share.token}/decision/", {"decision": DECISION_ACCEPTED, "name": "فلان"},
    )
    assert response.status_code == 409
    assert "لا يقبل قراراً" in response.content.decode("utf-8")


def test_confirm_rule_lives_in_one_place_for_both_callers():
    """الشاشة والرابط يستدعيان الخدمة نفسها — لا نسختين تنحرفان.

    كانت الشروط محبوسةً في `PurchaseOrderViewSet.confirm`، و`.importlinter`
    يمنع `docshare` من استيراد `logistics.views` — فكان البديل نسخَها.
    """
    import inspect

    from logistics.services import confirm_purchase_order
    from logistics.views import procurement

    assert callable(confirm_purchase_order)
    source = inspect.getsource(procurement.PurchaseOrderViewSet.confirm)
    assert "confirm_purchase_order(" in source
    assert "STATUS_CONFIRMED" not in source, "قاعدة التأكيد عادت إلى الـview"
