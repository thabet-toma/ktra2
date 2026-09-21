"""اختبارات ردّ الدفعة عند ترحيل مرتجع البيع (Issue #167).

يتحقق من:
  1. الشيكات برسم التحصيل (Under_Collection) لا تُخرج نقداً من الصندوق (سقف النقد = 0).
  2. الشيك الأكبر من إجمالي المرتجع لا يُردّ ولا يُجزّأ (الورقة كاملة أو لا شيء).
  3. تفعيل الإعداد (auto_refund_on_sales_return=True): الرد التلقائي ينفذ بجسم طلب فارغ {}.
  4. تعطيل الإعداد (auto_refund_on_sales_return=False): لا رد تلقائي ويبقى الرصيد دائناً.
  5. الاختيار الصريح: يلتزم بسقفَي النقد والورق.
  6. الاختيار الصريح المتجاوز للسقوف يُرفض برسالة عربية.
  7. الاختيار الصريح {cheque_ids: [], cash_amount: 0}: لا يرد شيئاً الآن.
  8. غياب حساب الصندوق عند الحاجة لرد نقدي: يرفض بـ 400 ويرتد الترحيل.
  9. الفترة المالية المقفلة تمنع الترحيل والرد.
  10. إلغاء ترحيل المرتجع: يعيد الشيكات إلى المحفظة ('Received') ويحذف سند الرد التلقائي.
  11. سند الرد المنشأ يدوياً يمنع إلغاء ترحيل المرتجع (حارس السندات).
  12. إعادة ترحيل المرتجع بعد إلغائه لا تُكرر سندات الرد.
  13. أقدمية استحقاق الشيكات: يُرد الشيك الأقدم استحقاقاً أولاً.
  14. سقف النقد التراكمي للمراجيع الجزئية المتعددة.
  15. مرتجع بيع بلا فاتورة أصلية: يتعامل بسلاسة مع الرد التلقائي ويرفض الرد الصريح.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounting.models import Account, Cheque, ChequeMovement, FiscalPeriod, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance, transfer_cheque
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    CustomerPayment,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)
from sales.services import (
    calculate_sales_return_refund_caps,
    get_or_create_sales_settings,
    allocate_customer_payment,
    post_customer_payment,
    post_sales_invoice,
    release_auto_sales_return_refund,
    suggest_fifo_allocations,
)
from sales.services import flow as sales_flow
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

DEC = Decimal("0.01")


@pytest.fixture
def env():
    owner = User.objects.create_user(username="sales_refund_owner", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة مرتجع البيع", owner)
    tenant._cur = cur
    create_fiscal_year(tenant, 2026)

    ar = Account.objects.create(
        tenant=tenant, code="1101-SR", name="ذمم عملاء", account_type="Asset", is_active=True
    )
    cash = Account.objects.create(
        tenant=tenant, code="1110-SR", name="صندوق رئيسي", account_type="Asset", is_active=True
    )
    in_hand = Account.objects.filter(tenant=tenant, code="1109").first()
    if not in_hand:
        in_hand = Account.objects.create(
            tenant=tenant, code="1109", name="شيكات في المحفظة", account_type="Asset", is_active=True
        )
    under_coll = Account.objects.filter(tenant=tenant, code="1107").first()
    if not under_coll:
        under_coll = Account.objects.create(
            tenant=tenant, code="1107", name="شيكات برسم التحصيل", account_type="Asset", is_active=True
        )
    rev = Account.objects.create(
        tenant=tenant, code="4101-SR", name="مبيعات", account_type="Revenue", is_active=True
    )
    cogs = Account.objects.create(
        tenant=tenant, code="5101-SR", name="تكلفة مبيعات", account_type="Expense", is_active=True
    )
    inv = Account.objects.create(
        tenant=tenant, code="1104-SR", name="مخزون", account_type="Asset", is_active=True
    )

    ss = get_or_create_sales_settings(tenant)
    ss.default_cash_account = cash
    ss.default_revenue_account_product = rev
    ss.default_cogs_account = cogs
    ss.default_inventory_account = inv
    ss.auto_refund_on_sales_return = True
    ss.save()

    customer = Partner.objects.create(
        tenant=tenant, name="عميل تجريبي", partner_type="Customer", linked_account=ar
    )
    product = Product.objects.create(
        tenant=tenant, sku="PROD-SR-1", name_ar="منتج تجريبي", avg_cost=Decimal("50"),
        quantity_on_hand=Decimal("100")
    )

    return tenant, owner, cur, ar, cash, rev, customer, product, ss


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _aging_rows(owner, tenant):
    response = _client(owner, tenant).get("/api/sales/reports/aging/")
    assert response.status_code == 200, response.data
    return response.data


def _invoice(
    tenant,
    customer,
    product,
    *,
    total="1000",
    date="2026-06-15",
    kind=SalesInvoice.INVOICE_KIND_SALE,
    original=None,
    number="SI-1",
    cash_account=None,
):
    inv = SalesInvoice.objects.create(
        tenant=tenant,
        invoice_number=number,
        customer=customer,
        currency=tenant._cur,
        invoice_date=date,
        invoice_type=SalesInvoice.INVOICE_CASH if cash_account else SalesInvoice.INVOICE_CREDIT,
        invoice_kind=kind,
        original_invoice=original,
        cash_or_bank_account=cash_account,
        stock_on_post=False,
    )
    SalesInvoiceLine.objects.create(
        tenant=tenant,
        invoice=inv,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal(str(total)),
    )
    return inv


def _pay_invoice_cash(tenant, customer, invoice, cash_account, amount):
    pay = CustomerPayment.objects.create(
        tenant=tenant,
        partner=customer,
        payment_date=invoice.invoice_date,
        amount=Decimal(str(amount)),
        currency=invoice.currency,
        cash_or_bank_account=cash_account,
    )
    PaymentAllocation.objects.create(
        tenant=tenant,
        payment=pay,
        invoice=invoice,
        amount=Decimal(str(amount)),
    )
    post_customer_payment(pay)
    return pay


def _pay_invoice_cheques_and_cash(
    tenant, customer, invoice, cash_account, *, cash_amount="0", cheques_data=()
):
    tot = Decimal(str(cash_amount)) + sum(Decimal(str(c["amount"])) for c in cheques_data)
    pay = CustomerPayment.objects.create(
        tenant=tenant,
        partner=customer,
        payment_date=invoice.invoice_date,
        amount=tot,
        currency=invoice.currency,
        cash_or_bank_account=cash_account,
    )
    PaymentAllocation.objects.create(
        tenant=tenant,
        payment=pay,
        invoice=invoice,
        amount=tot,
    )
    cheque_objs = []
    for cd in cheques_data:
        chq = Cheque.objects.create(
            tenant=tenant,
            customer_payment=pay,
            partner=customer,
            currency=invoice.currency,
            cheque_number=cd["cheque_number"],
            amount=Decimal(str(cd["amount"])),
            due_date=cd.get("due_date", "2026-07-01"),
            bank_name=cd.get("bank_name", "بنك فلسطين"),
            status="Draft",
            direction="Incoming",
        )
        cheque_objs.append(chq)
    post_customer_payment(pay)
    return pay, cheque_objs


# ── 1. الشيكات برسم التحصيل لا تُخرج نقداً من الصندوق ─────────────────────────
def test_under_collection_cheque_does_not_emit_cash(env):
    """شيك برسم التحصيل: لا يخرج نقد من الصندوق وسقف النقد = 0."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="1000", number="SI-ORIG-1")
    post_sales_invoice(orig)

    pay, [chq] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash, cheques_data=[{"cheque_number": "CHQ-UC-1", "amount": "1000"}]
    )
    transfer_cheque(chq.pk, "deposit", user=owner)
    chq.refresh_from_db()
    assert chq.status == "Under_Collection"

    caps = calculate_sales_return_refund_caps(orig)
    assert caps["cash_cap"] == Decimal("0.00")
    assert caps["paper_cap"] == Decimal("0.00")
    assert caps["paper_cheques"] == []

    # ترحيل مرتجع البيع بجسم فارغ مع تفعيل الإعداد
    ret = _invoice(
        tenant, customer, product, total="400", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-UC-1"
    )
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED
    assert ret.amount_paid == Decimal("0.00")
    assert not CustomerPayment.objects.filter(refund_for_invoice=ret).exists()
    assert resp.data["refund_summary"]["cash_amount"] == "0.00"
    assert resp.data["refund_summary"]["paper_amount"] == "0.00"
    assert resp.data["refund_summary"]["credit_balance"] == "400.00"

    # محاولة طلب نقد صريح تتجاوز سقف الصفر تُرفض بـ 400
    ret2 = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-UC-2"
    )
    resp2 = c.post(
        f"/api/sales/invoices/{ret2.id}/post/",
        {"refund": {"cheque_ids": [], "cash_amount": "100.00"}},
        format="json",
    )
    assert resp2.status_code == 400
    assert "يتجاوز سقف النقد" in resp2.data["error"]


# ── 2. الشيك الأكبر من إجمالي المرتجع لا يُردّ ولا يُجزّأ ──────────────────────
def test_cheque_larger_than_return_not_returned_and_not_split(env):
    """شيك بقيمة 800 مع مرتجع بقيمة 500: لا يُرد الشيك ولا يُجزأ، ويُرد النقد المتاح فقط."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="1000", number="SI-BIG-1")
    post_sales_invoice(orig)

    pay, [chq] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash, cash_amount="200",
        cheques_data=[{"cheque_number": "CHQ-BIG-1", "amount": "800"}]
    )
    chq.refresh_from_db()
    assert chq.status == "Received"

    ret = _invoice(
        tenant, customer, product, total="500", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-BIG-1"
    )
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data

    chq.refresh_from_db()
    assert chq.status == "Received"  # الورقة لم تُرد وبقيت في المحفظة
    ret.refresh_from_db()
    assert ret.amount_paid == Decimal("200.00")  # رُد النقد المتاح (200) فقط

    refund_pay = CustomerPayment.objects.get(refund_for_invoice=ret)
    assert refund_pay.amount == Decimal("200.00")
    assert refund_pay.kind == CustomerPayment.KIND_REFUND
    assert resp.data["refund_summary"]["paper_amount"] == "0.00"
    assert resp.data["refund_summary"]["cash_amount"] == "200.00"
    assert resp.data["refund_summary"]["credit_balance"] == "300.00"


# ── 3. تفعيل الإعداد: رد تلقائي بجسم فارغ {} ─────────────────────────────────
def test_auto_refund_when_setting_on(env):
    """الإعداد مفعّل: ترحيل المرتجع بـ {} يُنشئ ويُرحّل سند ردّ دفعة للمبلغ المدفوع."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-AUTO-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-AUTO-1"
    )
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED
    assert ret.amount_paid == Decimal("200.00")

    voucher = CustomerPayment.objects.get(refund_for_invoice=ret)
    assert voucher.is_posted is True
    assert voucher.kind == CustomerPayment.KIND_REFUND
    assert voucher.amount == Decimal("200.00")

    # فحص اتجاه قيد سند رد الدفعة: Dr ذمم العميل / Cr الصندوق
    j_lines = list(JournalLine.objects.filter(journal=voucher.journal))
    ar_lines = [l for l in j_lines if l.account_id == ar.id]
    cash_lines = [l for l in j_lines if l.account_id == cash.id]
    assert len(ar_lines) == 1 and ar_lines[0].debit == Decimal("200.00")
    assert len(cash_lines) == 1 and cash_lines[0].credit == Decimal("200.00")

    assert resp.data["refund_summary"]["cash_amount"] == "200.00"
    assert resp.data["refund_summary"]["credit_balance"] == "0.00"


# ── 4. تعطيل الإعداد: لا رد تلقائي ويبقى الرصيد دائناً ─────────────────────────
def test_no_refund_when_setting_off_and_no_choice(env):
    """الإعداد معطّل: ترحيل المرتجع بـ {} لا يُنشئ سند رد ويبقى رصيد دائن على الذمم."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save()

    orig = _invoice(tenant, customer, product, total="500", number="SI-OFF-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-OFF-1"
    )
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED
    assert ret.amount_paid == Decimal("0.00")
    assert not CustomerPayment.objects.filter(refund_for_invoice=ret).exists()
    assert resp.data["refund_summary"]["cash_amount"] == "0.00"
    assert resp.data["refund_summary"]["credit_balance"] == "200.00"


# ── 5. الاختيار الصريح مع مراعاة السقوف ───────────────────────────────────────
def test_explicit_choice_respects_caps(env):
    """اختيار صريح بإرجاع شيك ومبلغ نقدي ضمن السقوف."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save()

    orig = _invoice(tenant, customer, product, total="500", number="SI-EXP-1")
    post_sales_invoice(orig)
    pay, [chq] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash, cash_amount="300",
        cheques_data=[{"cheque_number": "CHQ-EXP-1", "amount": "200"}]
    )

    ret = _invoice(
        tenant, customer, product, total="300", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-EXP-1"
    )
    c = _client(owner, tenant)
    resp = c.post(
        f"/api/sales/invoices/{ret.id}/post/",
        {"refund": {"cheque_ids": [chq.id], "cash_amount": "100.00"}},
        format="json",
    )
    assert resp.status_code == 200, resp.data

    chq.refresh_from_db()
    assert chq.status == "Returned"
    assert ChequeMovement.objects.filter(cheque=chq, movement_type="return_to_customer").exists()

    ret.refresh_from_db()
    assert ret.amount_paid == Decimal("100.00")
    assert CustomerPayment.objects.filter(refund_for_invoice=ret, amount=Decimal("100.00")).exists()
    assert resp.data["refund_summary"]["paper_amount"] == "200.00"
    assert resp.data["refund_summary"]["cash_amount"] == "100.00"
    assert resp.data["refund_summary"]["credit_balance"] == "0.00"

    # الورق + النقد سدّدا المرتجع كاملاً؛ لا يجوز ردّ مبلغ آخر عليه لاحقاً.
    extra_refund = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("1.00"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    PaymentAllocation.objects.create(
        tenant=tenant, payment=extra_refund, invoice=ret, amount=Decimal("1.00"),
    )
    with pytest.raises(ValidationError) as exc:
        post_customer_payment(extra_refund)
    assert f"مرتجع البيع #{ret.invoice_number}" in str(exc.value)
    extra_refund.refresh_from_db()
    ret.refresh_from_db()
    assert extra_refund.is_posted is False
    assert ret.amount_paid == Decimal("100.00")
    assert not JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=extra_refund.id
    ).exists()


# ── 6. الاختيار الصريح المتجاوز للسقوف يُرفض بجمل عربية ────────────────────────
def test_explicit_choice_exceeding_caps_rejected(env):
    """تجاوز السقوف يرجع 400 بجملة عربية واضحة."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-CAP-1")
    post_sales_invoice(orig)
    pay, [chq] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash, cash_amount="100",
        cheques_data=[{"cheque_number": "CHQ-CAP-1", "amount": "400"}]
    )
    transfer_cheque(chq.pk, "deposit", user=owner)

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-CAP-1"
    )
    c = _client(owner, tenant)

    # طلب نقد يتجاوز سقف النقد المتاح (المتاح 100، المطلوب 150)
    resp = c.post(
        f"/api/sales/invoices/{ret.id}/post/",
        {"refund": {"cheque_ids": [], "cash_amount": "150.00"}},
        format="json",
    )
    assert resp.status_code == 400
    assert "يتجاوز سقف النقد" in resp.data["error"]

    # طلب شيك غير موجود في المحفظة
    resp2 = c.post(
        f"/api/sales/invoices/{ret.id}/post/",
        {"refund": {"cheque_ids": [chq.id], "cash_amount": "0.00"}},
        format="json",
    )
    assert resp2.status_code == 400
    assert "ليس في المحفظة" in resp2.data["error"]

    # طلب نقد يتجاوز إجمالي المرتجع
    orig2 = _invoice(tenant, customer, product, total="500", number="SI-CAP-2")
    post_sales_invoice(orig2)
    _pay_invoice_cash(tenant, customer, orig2, cash, "500")
    ret2 = _invoice(
        tenant, customer, product, total="150", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig2, number="SR-CAP-2"
    )
    resp3 = c.post(
        f"/api/sales/invoices/{ret2.id}/post/",
        {"refund": {"cheque_ids": [], "cash_amount": "250.00"}},
        format="json",
    )
    assert resp3.status_code == 400
    assert "يتجاوز إجمالي مرتجع البيع" in resp3.data["error"]


# ── 7. الاختيار الصريح {cheque_ids: [], cash_amount: 0} («لا شيء الآن») ────────
def test_explicit_choice_refund_nothing(env):
    """المستخدم اختار صراحة «لا شيء الآن» رغم تفعيل الإعداد التلقائي."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-NOTH-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-NOTH-1"
    )
    c = _client(owner, tenant)
    resp = c.post(
        f"/api/sales/invoices/{ret.id}/post/",
        {"refund": {"cheque_ids": [], "cash_amount": "0"}},
        format="json",
    )
    assert resp.status_code == 200, resp.data

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED
    assert ret.amount_paid == Decimal("0.00")
    assert not CustomerPayment.objects.filter(refund_for_invoice=ret).exists()
    assert resp.data["refund_summary"]["cash_amount"] == "0.00"
    assert resp.data["refund_summary"]["credit_balance"] == "200.00"


# ── 8. غياب حساب الصندوق عند الحاجة لرد نقدي ──────────────────────────────────
def test_missing_cash_box_when_cash_refund_needed(env):
    """غياب حساب الصندوق مع الحاجة لرد نقدي: خطأ 400 بجملة عربية والترحيل يرتد."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.default_cash_account = None
    ss.save()
    from accounting.models import CashBoxLedgerAccount
    CashBoxLedgerAccount.objects.filter(tenant_id=tenant.TenantID).delete()
    from django.db.models import Q
    Account.objects.filter(
        tenant_id=tenant.TenantID
    ).filter(
        Q(code__in=["1101", "1102", "1110"])
        | Q(name__icontains="صندوق")
        | Q(name__icontains="نقد")
        | Q(name__icontains="بنك")
    ).exclude(id=ar.id).delete()

    cash_orig = Account.objects.create(
        tenant=tenant, code="8888-X", name="حساب للدفع", account_type="Asset", is_active=True
    )
    orig = _invoice(tenant, customer, product, total="500", number="SI-NOCASH-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash_orig, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-NOCASH-1"
    )
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 400
    assert "المرتجع يتطلب ردّ دفعة نقدية للزبون ولا صندوق محدَّد" in resp.data["error"]

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_DRAFT
    assert not CustomerPayment.objects.filter(refund_for_invoice=ret).exists()


# ── 9. احترام قفل الفترة المالية ─────────────────────────────────────────────
def test_fiscal_period_locked_blocks_refund_and_return(env):
    """الفترة المالية المقفلة تمنع ترحيل المرتجع وسند الرد التابع له."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-LOCK-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-LOCK-1"
    )

    # قفل الفترات المالية
    FiscalPeriod.objects.filter(tenant=tenant).update(is_closed=True)

    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 400
    assert "مغلقة" in resp.data["error"]

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_DRAFT


# ── 10. إلغاء ترحيل المرتجع: استعادة الشيكات وحذف سند الرد ────────────────────
def test_unpost_restores_cheques_and_deletes_system_refund_voucher(env):
    """إلغاء الترحيل يعيد الشيكات إلى 'Received' ويحذف سند الرد التلقائي وقيوده."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-UNP-1")
    post_sales_invoice(orig)
    pay, [chq] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash, cash_amount="200",
        cheques_data=[{"cheque_number": "CHQ-UNP-1", "amount": "200"}]
    )

    ret = _invoice(
        tenant, customer, product, total="400", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-UNP-1"
    )
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data

    chq.refresh_from_db()
    assert chq.status == "Returned"
    assert CustomerPayment.objects.filter(refund_for_invoice=ret).exists()

    # إلغاء ترحيل المرتجع عبر نقطة unpost
    unp_resp = c.post(f"/api/sales/invoices/{ret.id}/unpost/", {}, format="json")
    assert unp_resp.status_code == 200, unp_resp.data

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_DRAFT
    assert ret.amount_paid == Decimal("0.00")

    # سند الرد التلقائي حُذف
    assert not CustomerPayment.objects.filter(refund_for_invoice=ret).exists()

    # الشيك عاد إلى المحفظة بحالة Received
    chq.refresh_from_db()
    assert chq.status == "Received"

    # قيدُ حركة الإرجاع حُذف — والحركةُ نفسُها تبقى: سجلُّ الورقة لا يُمحى،
    # ويُكتب الرجوعُ حركةً كما يفعل تحريرُ شيكات السند.
    movement = ChequeMovement.objects.filter(
        cheque=chq, movement_type="return_to_customer").first()
    assert movement is not None
    assert movement.journal_id is None
    assert movement.sales_return_id is None  # الوسمُ فُرِّغ فلا يُلتقط مرّتين
    assert ChequeMovement.objects.filter(cheque=chq, movement_type="revert").exists()

    # الفاتورة الأصلية لم تتأثر
    orig.refresh_from_db()
    assert orig.status == SalesInvoice.STATUS_POSTED
    assert orig.amount_paid == Decimal("400.00")


def test_release_auto_refund_locks_payment_before_linked_invoices(env, monkeypatch):
    """فكّ المرتجع يشارك السندات ترتيب القفل: الدفع ثم المرتجع/الأصل."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-LOCK-ORDER")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "200")
    ret = _invoice(
        tenant, customer, product, total="200",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-LOCK-ORDER",
    )
    post_sales_invoice(ret)
    refund = CustomerPayment.objects.get(refund_for_invoice=ret)
    order = []
    lock_payments = sales_flow._lock_customer_payments
    lock_invoices = sales_flow._lock_invoices_with_linked_originals

    def record_payments(*args, **kwargs):
        order.append("payments")
        return lock_payments(*args, **kwargs)

    def record_invoices(*args, **kwargs):
        order.append("invoices")
        return lock_invoices(*args, **kwargs)

    monkeypatch.setattr(sales_flow, "_lock_customer_payments", record_payments)
    monkeypatch.setattr(sales_flow, "_lock_invoices_with_linked_originals", record_invoices)
    release_auto_sales_return_refund(ret)

    assert order == ["payments", "invoices"]
    assert not CustomerPayment.objects.filter(pk=refund.pk).exists()


# ── 11. سند الرد اليدوي يمنع إلغاء ترحيل المرتجع ──────────────────────────────
def test_user_created_refund_voucher_blocks_return_unpost(env):
    """سند رد دفعة يدوي (refund_for_invoice=None) يمنع إلغاء ترحيل المرتجع بحارس السندات."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save()

    orig = _invoice(tenant, customer, product, total="500", number="SI-USRPAY-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="300", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-USRPAY-1"
    )
    post_sales_invoice(ret)

    # إنشاء سند رد يدوي وتوزيعه على المرتجع
    manual_pay = CustomerPayment.objects.create(
        tenant=tenant,
        partner=customer,
        payment_date="2026-06-20",
        amount=Decimal("150.00"),
        currency=cur,
        cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
        refund_for_invoice=None,
    )
    PaymentAllocation.objects.create(
        tenant=tenant,
        payment=manual_pay,
        invoice=ret,
        amount=Decimal("150.00"),
    )
    post_customer_payment(manual_pay)

    ret.refresh_from_db()
    assert ret.amount_paid == Decimal("150.00")

    # محاولة إلغاء الترحيل تُصد بالحارس
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/unpost/", {}, format="json")
    assert resp.status_code == 400
    assert "توجد سندات قبض مرحّلة موزّعة عليها" in resp.data["error"]
    assert str(manual_pay.id) in resp.data["error"]

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED


# ── 12. إعادة ترحيل المرتجع لا تُكرر سندات الرد ────────────────────────────────
def test_repost_after_unpost_does_not_duplicate_refund_voucher(env):
    """إلغاء ترحيل المرتجع ثم إعادة ترحيله ينتج سند رد واحد فقط ولا يُضاعف السندات."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-REP-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-REP-1"
    )
    c = _client(owner, tenant)

    assert c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json").status_code == 200
    assert CustomerPayment.objects.filter(refund_for_invoice=ret).count() == 1

    assert c.post(f"/api/sales/invoices/{ret.id}/unpost/", {}, format="json").status_code == 200
    assert CustomerPayment.objects.filter(refund_for_invoice=ret).count() == 0

    assert c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json").status_code == 200
    assert CustomerPayment.objects.filter(refund_for_invoice=ret).count() == 1

    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED
    assert ret.amount_paid == Decimal("200.00")


# ── 13. أقدمية استحقاق الشيكات ───────────────────────────────────────────────
def test_oldest_due_date_cheque_returned_first(env):
    """الشيك الأقدم استحقاقاً يُرد أولاً بالمسار التلقائي."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-OLD-1")
    post_sales_invoice(orig)

    pay, [chq_later, chq_earlier] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash,
        cheques_data=[
            {"cheque_number": "CHQ-LATER", "amount": "100", "due_date": "2026-09-01"},
            {"cheque_number": "CHQ-EARLIER", "amount": "100", "due_date": "2026-07-01"},
        ]
    )

    ret = _invoice(
        tenant, customer, product, total="100", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-OLD-1"
    )
    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data

    chq_earlier.refresh_from_db()
    chq_later.refresh_from_db()
    assert chq_earlier.status == "Returned"
    assert chq_later.status == "Received"
    assert not CustomerPayment.objects.filter(refund_for_invoice=ret).exists()
    assert resp.data["refund_summary"]["paper_amount"] == "100.00"
    assert resp.data["refund_summary"]["cheque_numbers"] == ["CHQ-EARLIER"]


# ── 14. سقف النقد التراكمي للمراجيع الجزئية المتعددة ───────────────────────────
def test_multiple_partial_returns_cumulative_cash_cap(env):
    """مراجيع جزئية متتالية على نفس الفاتورة تلتزم بسقف النقد المتبقي تراكمياً."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="1000", number="SI-CUM-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "1000")

    c = _client(owner, tenant)

    # المرتجع الأول: 600 -> يُرد 600 نقداً
    ret1 = _invoice(
        tenant, customer, product, total="600", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-CUM-1"
    )
    assert c.post(f"/api/sales/invoices/{ret1.id}/post/", {}, format="json").status_code == 200
    ret1.refresh_from_db()
    assert ret1.amount_paid == Decimal("600.00")

    # المرتجع الثاني: 400 -> المتبقي من سقف النقد 1000 - 600 = 400
    ret2 = _invoice(
        tenant, customer, product, total="400", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-CUM-2"
    )
    assert c.post(f"/api/sales/invoices/{ret2.id}/post/", {}, format="json").status_code == 200
    ret2.refresh_from_db()
    assert ret2.amount_paid == Decimal("400.00")

    # المرتجع الثالث: 100 -> استُنفد سقف النقد، فلا يُرد نقد ويبقى رصيداً دائناً
    ret3 = _invoice(
        tenant, customer, product, total="100", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-CUM-3"
    )
    resp3 = c.post(f"/api/sales/invoices/{ret3.id}/post/", {}, format="json")
    assert resp3.status_code == 200
    ret3.refresh_from_db()
    assert ret3.amount_paid == Decimal("0.00")
    assert resp3.data["refund_summary"]["cash_amount"] == "0.00"
    assert resp3.data["refund_summary"]["credit_balance"] == "100.00"


# ── 15. مرتجع بيع بلا فاتورة أصلية ───────────────────────────────────────────
def test_return_without_original_invoice_handles_refund(env):
    """مرتجع بيع مستقل (بلا فاتورة أصلية) يُرحل بـ {} بسلاسة ويرفض الرد الصريح."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ret = _invoice(
        tenant, customer, product, total="300", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=None, number="SR-STANDALONE-1"
    )
    c = _client(owner, tenant)

    # الترحيل بـ {} ينجح ويبقى المبلغ كاملاً كرصيد دائن
    resp = c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data
    ret.refresh_from_db()
    assert ret.status == SalesInvoice.STATUS_POSTED
    assert ret.amount_paid == Decimal("0.00")
    assert resp.data["refund_summary"]["credit_balance"] == "300.00"

    # مرتجع مستقل ثانٍ بمحاولة رد صريح يُرفض
    ret2 = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=None, number="SR-STANDALONE-2"
    )
    resp2 = c.post(
        f"/api/sales/invoices/{ret2.id}/post/",
        {"refund": {"cheque_ids": [], "cash_amount": "50.00"}},
        format="json",
    )
    assert resp2.status_code == 400
    assert "لا يمكن ردّ دفعة لمرتجع بيع غير مربوط بفاتورة بيع أصلية" in resp2.data["error"]


# ── 16. حارسا توزيع سند الردّ ────────────────────────────────────────────────
# ── 18. نقطة refund-options (م٤): بيانات حوار الردّ ────────────────────────────
def test_refund_options_endpoint_reports_wallet_and_bank_split(env):
    """المرتجع على فاتورة دُفعت جزئياً بشيك في المحفظة وجزئياً نقداً: النقطة
    تُعيد سقف النقد وشيك المحفظة والمبلغ عند البنك غير القابل للردّ الآن."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save()

    orig = _invoice(tenant, customer, product, total="1000", number="SI-OPT-1")
    post_sales_invoice(orig)
    pay, [chq_wallet] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash, cash_amount="300",
        cheques_data=[{"cheque_number": "CHQ-OPT-1", "amount": "400", "due_date": "2026-08-01"}]
    )
    pay2, [chq_bank] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash,
        cheques_data=[{"cheque_number": "CHQ-OPT-2", "amount": "300", "due_date": "2026-08-15"}]
    )
    transfer_cheque(chq_bank.pk, "deposit", user=owner)
    chq_bank.refresh_from_db()
    assert chq_bank.status == "Under_Collection"

    ret = _invoice(
        tenant, customer, product, total="700", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-OPT-1"
    )
    c = _client(owner, tenant)
    resp = c.get(f"/api/sales/invoices/{ret.id}/refund-options/")
    assert resp.status_code == 200, resp.data
    data = resp.data
    assert data["applicable"] is True
    assert data["auto_refund_on_sales_return"] is False
    assert data["cash_cap"] == "300.00"
    assert data["return_total"] == "700.00"
    assert data["bank_uncollected_total"] == "300.00"
    assert len(data["paper_cheques"]) == 1
    wallet = data["paper_cheques"][0]
    assert wallet["id"] == chq_wallet.id
    assert wallet["cheque_number"] == "CHQ-OPT-1"
    assert wallet["amount"] == "400.00"
    assert wallet["due_date"] == "2026-08-01"


def test_refund_options_endpoint_non_return_and_no_original(env):
    """فاتورة بيع عادية أو مرتجع بلا فاتورة أصلية: النقطة تردّ بسلاسة بلا خطأ."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    inv = _invoice(tenant, customer, product, total="500", number="SI-OPT-2")
    post_sales_invoice(inv)
    c = _client(owner, tenant)

    resp = c.get(f"/api/sales/invoices/{inv.id}/refund-options/")
    assert resp.status_code == 200, resp.data
    assert resp.data["applicable"] is False
    assert resp.data["paper_cheques"] == []

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=None, number="SR-OPT-2"
    )
    resp2 = c.get(f"/api/sales/invoices/{ret.id}/refund-options/")
    assert resp2.status_code == 200, resp2.data
    assert resp2.data["applicable"] is False
    assert resp2.data["cash_cap"] == "0.00"


def test_refund_voucher_rejected_on_non_return_document(env):
    """سندُ ردٍّ يُوزَّع على فاتورة بيعٍ عاديّة يُرفض — الردُّ لا يُسدَّد به بيعٌ."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    inv = _invoice(tenant, customer, product, total="500", number="SI-GUARD-1")
    post_sales_invoice(inv)

    refund = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-20",
        amount=Decimal("100.00"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    PaymentAllocation.objects.create(
        tenant=tenant, payment=refund, invoice=inv, amount=Decimal("100.00")
    )
    with pytest.raises(Exception) as exc:
        post_customer_payment(refund)
    assert "لا يُوزَّع إلا على مرتجع بيع" in str(exc.value)

    refund.refresh_from_db()
    assert refund.is_posted is False
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("0.00")


def test_refund_voucher_rejected_on_another_partners_return(env):
    """سندُ ردٍّ لزبونٍ يُوزَّع على مرتجع زبونٍ آخر يُرفض — لا يُسدَّد دينُ غيره."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    other = Partner.objects.create(
        tenant=tenant, name="زبون آخر", partner_type="Customer", linked_account=ar
    )
    orig = _invoice(tenant, customer, product, total="500", number="SI-GUARD-2")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-GUARD-2"
    )
    post_sales_invoice(ret, refund_choice={"cheque_ids": [], "cash_amount": "0"})

    refund = CustomerPayment.objects.create(
        tenant=tenant, partner=other, payment_date="2026-06-20",
        amount=Decimal("100.00"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    PaymentAllocation.objects.create(
        tenant=tenant, payment=refund, invoice=ret, amount=Decimal("100.00")
    )
    with pytest.raises(Exception) as exc:
        post_customer_payment(refund)
    assert "لا يخص نفس العميل" in str(exc.value)

    ret.refresh_from_db()
    assert ret.amount_paid == Decimal("0.00")


# ── 17. سجلُّ الشيك لا يُمحى عند فكّ الترحيل ──────────────────────────────────
def test_unpost_keeps_cheque_history_and_writes_revert(env):
    """فكُّ الترحيل يعيد الورقة ويسجّل الرجوع — لا يمحو حلقةَ خروجها للعميل."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-HIST-1")
    post_sales_invoice(orig)
    pay, [chq] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash,
        cheques_data=[{"cheque_number": "CHQ-HIST-1", "amount": "200"}]
    )

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-HIST-1"
    )
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json").status_code == 200
    chq.refresh_from_db()
    assert chq.status == "Returned"

    assert c.post(f"/api/sales/invoices/{ret.id}/unpost/", {}, format="json").status_code == 200

    chq.refresh_from_db()
    assert chq.status == "Received"
    # الحلقتان محفوظتان: خرجت الورقة ثم عادت.
    assert ChequeMovement.objects.filter(
        cheque=chq, movement_type="return_to_customer").exists()
    assert ChequeMovement.objects.filter(cheque=chq, movement_type="revert").exists()
    # ووسمُ الملكيّة فُرِّغ فلا تلتقطه إعادةُ الترحيل مرّتين.
    assert not ChequeMovement.objects.filter(sales_return_id=ret.pk).exists()

    # إعادةُ الترحيل تُخرج الورقة من جديد بحركةٍ ثانية لا بتكرار الأولى.
    assert c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json").status_code == 200
    chq.refresh_from_db()
    assert chq.status == "Returned"
    assert ChequeMovement.objects.filter(
        cheque=chq, movement_type="return_to_customer").count() == 2


# ── 18. الورقةُ المُعادةُ لا تصير نقداً في مرتجعٍ لاحق ────────────────────────
def test_returned_cheque_does_not_become_spendable_cash(env):
    """ورقةٌ رُدَّت في مرتجعٍ سابق لا تفتح سقفَ نقدٍ في المرتجع التالي.

    العطب: سقفُ النقد كان يطرح ما حالتُه 'Received' أو 'Under_Collection' فقط.
    فمتى خرجت الورقةُ من الحالتين — رُدَّت للعميل أو ارتدّت — سقطت من الطرح
    وبقي مبلغُها داخل «التوزيعات المرحّلة»، فتحوّلت قيمتُها إلى نقدٍ قابلٍ
    للصرف. وهو عينُ ما وُضع السقفُ ليمنعه: نقدٌ حقيقيٌّ يخرج مقابل ورقةٍ لم
    تُقبض قطّ — بل ورقةٍ أعدناها لصاحبها بأيدينا.
    """
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="1100", number="SI-LEAK-1")
    post_sales_invoice(orig)
    pay, [chq_a, chq_b] = _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash,
        cheques_data=[
            {"cheque_number": "CHQ-A", "amount": "500", "due_date": "2026-07-01"},
            {"cheque_number": "CHQ-B", "amount": "600", "due_date": "2026-08-01"},
        ],
    )
    # لا نقدَ إطلاقاً: كلُّ ما وصلنا ورقتان لم تُحصَّل واحدةٌ منهما.
    assert calculate_sales_return_refund_caps(orig)["cash_cap"] == Decimal("0.00")


    c = _client(owner, tenant)
    ret1 = _invoice(
        tenant, customer, product, total="500", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-LEAK-1"
    )
    assert c.post(f"/api/sales/invoices/{ret1.id}/post/", {}, format="json").status_code == 200
    chq_a.refresh_from_db()
    assert chq_a.status == "Returned"  # الورقة الأقدم عادت لصاحبها

    # والآن: الورقةُ الثانية ما زالت في المحفظة غيرَ محصَّلة، والأولى خرجت من
    # دفاترنا ورقةً. فلا نقدَ في الصندوق يخصّ هذه الفاتورة إطلاقاً.
    assert calculate_sales_return_refund_caps(orig)["cash_cap"] == Decimal("0.00")

    ret2 = _invoice(
        tenant, customer, product, total="500", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-LEAK-2"
    )
    resp = c.post(f"/api/sales/invoices/{ret2.id}/post/", {}, format="json")
    assert resp.status_code == 200, resp.data

    chq_b.refresh_from_db()
    assert chq_b.status == "Received"  # 600 أكبر من 500 فلا تُجزَّأ ولا تُردّ
    assert resp.data["refund_summary"]["cash_amount"] == "0.00", (
        "خرج نقدٌ من الصندوق مقابل ورقةٍ لم تُقبض — تسريبُ سقف النقد."
    )
    assert resp.data["refund_summary"]["credit_balance"] == "500.00"
    assert not CustomerPayment.objects.filter(refund_for_invoice=ret2).exists()


# ── 19. صافي الذمم بعد المرتجع والاسترداد ────────────────────────────────────
def test_full_unpaid_return_removes_original_from_aging_and_matches_ledger(env):
    """فاتورة 1000 بلا تحصيل + مرتجع كامل بلا رد = لا دين، كما يقول دفتر العميل."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save(update_fields=["auto_refund_on_sales_return"])
    orig = _invoice(tenant, customer, product, total="1000", number="SI-AGING-NET")
    post_sales_invoice(orig)
    ret = _invoice(
        tenant, customer, product, total="1000",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-AGING-NET",
    )
    response = _client(owner, tenant).post(
        f"/api/sales/invoices/{ret.id}/post/",
        {"refund": {"cheque_ids": [], "cash_amount": "0"}}, format="json",
    )
    assert response.status_code == 200, response.data

    rows = _aging_rows(owner, tenant)
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert rows == []
    assert sum((Decimal(row["remaining"]) for row in rows), Decimal("0")) == debit - credit
    assert debit - credit == Decimal("0.00")


def test_auto_cash_refund_leaves_only_original_unpaid_amount_collectible(env):
    """الرد التلقائي الكامل للمرتجع يُصفّر رصيده المفتوح ولا يخصم قيمته مرتين."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="1000", number="SI-AUTO-NET")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "400")
    ret = _invoice(
        tenant, customer, product, total="300",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-AUTO-NET",
    )
    response = _client(owner, tenant).post(
        f"/api/sales/invoices/{ret.id}/post/", {}, format="json",
    )
    assert response.status_code == 200, response.data

    ret.refresh_from_db()
    assert ret.amount_paid == Decimal("300.00")
    rows = _aging_rows(owner, tenant)
    assert [row["invoice_number"] for row in rows] == [orig.invoice_number]
    assert Decimal(rows[0]["remaining"]) == Decimal("600.00")


def test_manual_partial_refund_deducts_only_open_return_credit(env):
    """الرد اليدوي الجزئي يترك الجزء غير المسترد وحده رصيداً دائنًا يخصم من الأصل."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save(update_fields=["auto_refund_on_sales_return"])
    orig = _invoice(tenant, customer, product, total="1000", number="SI-MANUAL-NET")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "400")
    ret = _invoice(
        tenant, customer, product, total="300",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-MANUAL-NET",
    )
    response = _client(owner, tenant).post(
        f"/api/sales/invoices/{ret.id}/post/",
        {"refund": {"cheque_ids": [], "cash_amount": "100.00"}}, format="json",
    )
    assert response.status_code == 200, response.data

    ret.refresh_from_db()
    assert ret.amount_paid == Decimal("100.00")
    rows = _aging_rows(owner, tenant)
    assert [row["invoice_number"] for row in rows] == [orig.invoice_number]
    assert Decimal(rows[0]["remaining"]) == Decimal("400.00")
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert debit - credit == Decimal("400.00")


def test_returned_cheque_settles_return_credit_without_touching_amount_paid(env):
    """الورقة المعادة تُسدّد المرتجع دفترياً ولو بقي amount_paid صفراً."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="1000", number="SI-PAPER-NET")
    post_sales_invoice(orig)
    _pay_invoice_cheques_and_cash(
        tenant, customer, orig, cash,
        cheques_data=[{"cheque_number": "CHQ-PAPER-NET", "amount": "500"}],
    )
    ret = _invoice(
        tenant, customer, product, total="500",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-PAPER-NET",
    )
    response = _client(owner, tenant).post(
        f"/api/sales/invoices/{ret.id}/post/", {}, format="json",
    )
    assert response.status_code == 200, response.data

    ret.refresh_from_db()
    assert ret.amount_paid == Decimal("0.00")
    assert ChequeMovement.objects.filter(
        sales_return=ret, movement_type="return_to_customer", journal_id__isnull=False,
    ).count() == 1
    rows = _aging_rows(owner, tenant)
    assert [row["invoice_number"] for row in rows] == [orig.invoice_number]
    assert Decimal(rows[0]["remaining"]) == Decimal("500.00")
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert debit - credit == Decimal("500.00")
    assert suggest_fifo_allocations(
        tenant_id=tenant.TenantID, partner_id=customer.id, amount=Decimal("1000"),
    ) == [{
        "invoice": orig.id, "invoice_number": orig.invoice_number, "amount": "500.00",
    }]

    extra_refund = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("1"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    PaymentAllocation.objects.create(
        tenant=tenant, payment=extra_refund, invoice=ret, amount=Decimal("1"),
    )
    with pytest.raises(ValidationError) as exc:
        post_customer_payment(extra_refund)
    assert f"مرتجع البيع #{ret.invoice_number}" in str(exc.value)
    extra_refund.refresh_from_db()
    ret.refresh_from_db()
    assert extra_refund.is_posted is False
    assert ret.amount_paid == Decimal("0.00")
    assert not JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=extra_refund.id
    ).exists()


def test_manual_sibling_refunds_cannot_exceed_original_cash_cap(env):
    """الحارس يعيد قراءة سقف الأصل قبل كتابة ردّ الشقيق الثاني."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save(update_fields=["auto_refund_on_sales_return"])
    original = _invoice(tenant, customer, product, total="500", number="SI-SHARED-CAP")
    post_sales_invoice(original)
    _pay_invoice_cash(tenant, customer, original, cash, "300")
    first_return = _invoice(
        tenant, customer, product, total="200",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=original, number="SR-SHARED-CAP-1",
    )
    second_return = _invoice(
        tenant, customer, product, total="200",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=original, number="SR-SHARED-CAP-2",
    )
    post_sales_invoice(first_return, refund_choice={"cheque_ids": [], "cash_amount": "0"})
    post_sales_invoice(second_return, refund_choice={"cheque_ids": [], "cash_amount": "0"})

    first_refund = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("200"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    PaymentAllocation.objects.create(
        tenant=tenant, payment=first_refund, invoice=first_return, amount=Decimal("200"),
    )
    post_customer_payment(first_refund)

    second_refund = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("150"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    PaymentAllocation.objects.create(
        tenant=tenant, payment=second_refund, invoice=second_return, amount=Decimal("150"),
    )
    with pytest.raises(ValidationError) as exc:
        post_customer_payment(second_refund)
    assert original.invoice_number in str(exc.value)

    second_refund.refresh_from_db()
    second_return.refresh_from_db()
    assert second_refund.is_posted is False
    assert second_return.amount_paid == Decimal("0.00")
    assert not JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=second_refund.id
    ).exists()


def test_later_refund_allocation_rechecks_sibling_cash_cap(env):
    """توزيع سند ردّ مرحّل لاحقاً يعيد فحص السقف المشترك قبل ربطه بالمرتجع."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save(update_fields=["auto_refund_on_sales_return"])
    original = _invoice(tenant, customer, product, total="500", number="SI-ALLOC-CAP")
    post_sales_invoice(original)
    _pay_invoice_cash(tenant, customer, original, cash, "300")
    first_return = _invoice(
        tenant, customer, product, total="200",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=original, number="SR-ALLOC-CAP-1",
    )
    second_return = _invoice(
        tenant, customer, product, total="200",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=original, number="SR-ALLOC-CAP-2",
    )
    post_sales_invoice(first_return, refund_choice={"cheque_ids": [], "cash_amount": "0"})
    post_sales_invoice(second_return, refund_choice={"cheque_ids": [], "cash_amount": "0"})

    first_refund = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("200"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    post_customer_payment(first_refund)
    allocate_customer_payment(
        first_refund, [{"invoice": first_return.id, "amount": "200"}],
    )

    second_refund = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("150"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    post_customer_payment(second_refund)
    with pytest.raises(ValidationError) as exc:
        allocate_customer_payment(
            second_refund, [{"invoice": second_return.id, "amount": "150"}],
        )
    assert original.invoice_number in str(exc.value)

    second_return.refresh_from_db()
    assert second_return.amount_paid == Decimal("0.00")
    assert not PaymentAllocation.objects.filter(payment=second_refund).exists()


def test_manual_refund_reduces_next_returns_automatic_cash_cap(env):
    """الرد اليدوي الموزع على مرتجع يدخل السقف التراكمي ولو لم يملك refund_for_invoice."""
    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    ss.auto_refund_on_sales_return = False
    ss.save(update_fields=["auto_refund_on_sales_return"])
    orig = _invoice(tenant, customer, product, total="1000", number="SI-MANUAL-CAP")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret1 = _invoice(
        tenant, customer, product, total="200",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-MANUAL-CAP-1",
    )
    post_sales_invoice(ret1, refund_choice={"cheque_ids": [], "cash_amount": "0"})
    manual = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-20",
        amount=Decimal("100"), currency=cur, cash_or_bank_account=cash,
        kind=CustomerPayment.KIND_REFUND,
    )
    PaymentAllocation.objects.create(
        tenant=tenant, payment=manual, invoice=ret1, amount=Decimal("100"),
    )
    post_customer_payment(manual)

    ss.auto_refund_on_sales_return = True
    ss.save(update_fields=["auto_refund_on_sales_return"])
    ret2 = _invoice(
        tenant, customer, product, total="500",
        kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-MANUAL-CAP-2",
    )
    response = _client(owner, tenant).post(
        f"/api/sales/invoices/{ret2.id}/post/", {}, format="json",
    )
    assert response.status_code == 200, response.data
    ret2.refresh_from_db()
    assert ret2.amount_paid == Decimal("400.00")
    assert response.data["refund_summary"]["credit_balance"] == "100.00"


# ── 20. المستنداتُ الثلاثة مرتبطةٌ في كشف حساب الزبون ─────────────────────────
def test_statement_links_invoice_return_and_refund_together(env):
    """الفاتورةُ والمرتجعُ وسندُ الردّ في مجموعةٍ واحدة، مرساتُها الفاتورةُ الأصليّة.

    قصّة ١٢: «أرى في بطاقة الزبون الفاتورةَ والمرتجعَ وسندَ الردّ مرتبطةً
    ثلاثتَها، لا أرقاماً متفرّقة». المرتجعُ كان يصنع مجموعةً ثانية فتُقرأ
    الحكايةُ الواحدةُ مبعثرةً على مجموعتين.
    """
    from accounting.services import partner_account_statement

    tenant, owner, cur, ar, cash, rev, customer, product, ss = env
    orig = _invoice(tenant, customer, product, total="500", number="SI-LINK-1")
    post_sales_invoice(orig)
    _pay_invoice_cash(tenant, customer, orig, cash, "500")

    ret = _invoice(
        tenant, customer, product, total="200", kind=SalesInvoice.INVOICE_KIND_SALE_RETURN,
        original=orig, number="SR-LINK-1"
    )
    c = _client(owner, tenant)
    assert c.post(f"/api/sales/invoices/{ret.id}/post/", {}, format="json").status_code == 200
    voucher = CustomerPayment.objects.get(refund_for_invoice=ret)

    out = partner_account_statement(
        tenant_id=tenant.TenantID, partner_id=customer.pk, is_supplier=False, limit=200,
    )
    keys = {}
    for r in out["results"]:
        keys.setdefault((r["reference_type"], r["reference_id"]), r["link_key"])

    anchor = f"SALES_INVOICE:{orig.pk}"
    assert keys[("SALES_INVOICE", orig.pk)] == anchor
    assert keys[("SALES_INVOICE", ret.pk)] == anchor, "المرتجع صنع مجموعةً ثانية"
    assert keys[("CUSTOMER_PAYMENT", voucher.pk)] == anchor, "سند الردّ خارج المجموعة"
