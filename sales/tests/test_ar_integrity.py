"""سلامة ذمم العملاء — منع ازدواج التحصيل وبقاء السندات معلّقة بعد إلغاء الترحيل.

الجذر: `unpost_invoice` كان يصفّر `amount_paid` ويحذف قيود الفاتورة وحدها، تاركاً
سندات القبض المرحّلة وتوزيعاتها وقيودها (CUSTOMER_PAYMENT) حيّة ⇒ يبقى الطرف
الدائن في الذمم بلا مقابل. الأعراض الثلاثة (بيانات إنتاج، tenant 6):

1. فاتورة نقدية أُلغي ترحيلها ثم أُعيد ⇒ سند قبض تلقائي ثانٍ ⇒ ذمم مدائنة مرّتين.
2. فاتورة آجلة عليها سند مرحّل أُلغي ترحيلها ⇒ صف توزيع يتيم يُدفع ثانيةً لاحقاً.
3. فاتورة نقدية قديمة قيدها يخصم الصندوق مباشرة (بلا مدين ذمم) ومع ذلك أُنشئ لها
   سند قبض ⇒ ازدواج نقدية + دائن ذمم بلا مقابل.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework.test import APIClient

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_posted_balance
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    CustomerPayment,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
)
from sales.services import (
    _auto_settle_cash_sale,
    get_or_create_sales_settings,
    post_customer_payment,
    post_sales_invoice,
)
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db

DEC = Decimal("0.01")


@pytest.fixture
def env():
    owner = User.objects.create_user(username="arintegrity", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    cur = Currency.objects.get(Code="ILS")
    tenant = create_company("شركة سلامة الذمم", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-AR", name="ذمم", account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1110-AR", name="صندوق", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-AR", name="إيراد", account_type="Revenue", is_active=True)
    ss = get_or_create_sales_settings(tenant)
    ss.default_cash_account = cash
    ss.default_revenue_account_product = rev
    ss.save(update_fields=["default_cash_account", "default_revenue_account_product"])
    customer = Partner.objects.create(
        tenant=tenant, name="عميل الذمم", partner_type="Customer", linked_account=ar)
    product = Product.objects.create(
        tenant=tenant, sku="AR-1", name_ar="صنف", quantity_on_hand=Decimal("1000"),
        avg_cost=Decimal("1"))
    return tenant, owner, cur, ar, cash, rev, customer, product


def _client(owner, tenant):
    c = APIClient()
    c.force_authenticate(user=owner)
    c.credentials(HTTP_X_TENANT_ID=str(tenant.TenantID))
    return c


def _invoice(tenant, cur, customer, product, *, total, cash_account=None, number="SI-1"):
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=cur,
        invoice_date="2026-06-15",
        invoice_type=(
            SalesInvoice.INVOICE_CASH if cash_account else SalesInvoice.INVOICE_CREDIT
        ),
        cash_or_bank_account=cash_account, stock_on_post=False)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=Decimal(total))
    return inv


def _posted_allocations_total(inv) -> Decimal:
    return sum(
        (Decimal(str(a.amount)) for a in PaymentAllocation.objects.filter(
            invoice=inv, payment__is_posted=True)),
        Decimal("0"),
    )


def _net_balance(tenant, customer) -> Decimal:
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    return (debit - credit).quantize(DEC)


# ── العرض 1: إعادة ترحيل فاتورة نقدية تُنشئ سنداً ثانياً ────────────────────
def test_cash_invoice_repost_does_not_duplicate_settlement(env):
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="1580", cash_account=cash,
                   number="SI-6-154")
    c = _client(owner, tenant)

    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200
    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200
    assert c.post(f"/api/sales/invoices/{inv.id}/post/", {}, format="json").status_code == 200

    inv.refresh_from_db()
    # سند واحد فقط — لا ازدواج
    assert CustomerPayment.objects.filter(partner=customer).count() == 1
    assert _posted_allocations_total(inv) == Decimal("1580.00")
    assert inv.amount_paid == Decimal("1580.00")
    # رصيد العميل صفر (لا دائن وهمي)
    assert _net_balance(tenant, customer) == Decimal("0.00")


# ── العرض 2: إلغاء ترحيل فاتورة عليها سند مرحّل ─────────────────────────────
def test_unpost_blocked_when_posted_payment_allocated(env):
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="3900", number="SI-6-62")
    post_sales_invoice(inv)
    pay = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-20",
        amount=Decimal("3900"), currency=cur, cash_or_bank_account=cash)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=pay, invoice=inv, amount=Decimal("3900"))
    post_customer_payment(pay)

    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json")

    assert resp.status_code == 400
    assert str(pay.id) in resp.json()["error"]
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED
    assert inv.amount_paid == Decimal("3900.00")
    assert _net_balance(tenant, customer) == Decimal("0.00")


def test_unposting_the_payment_first_unblocks_the_invoice(env):
    """المخرج المطلوب من الرسالة: ألغِ ترحيل السند ثم الفاتورة — بلا أثر متبقٍّ."""
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="3900", number="SI-6-62")
    post_sales_invoice(inv)
    pay = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-20",
        amount=Decimal("3900"), currency=cur, cash_or_bank_account=cash)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=pay, invoice=inv, amount=Decimal("3900"))
    post_customer_payment(pay)

    c = _client(owner, tenant)
    assert c.post(f"/api/sales/payments/{pay.id}/unpost/", {}, format="json").status_code == 200
    pay.refresh_from_db()
    inv.refresh_from_db()
    assert pay.is_posted is False
    assert inv.amount_paid == Decimal("0.00")
    assert not JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=pay.id).exists()

    assert c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json").status_code == 200
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_DRAFT
    assert _net_balance(tenant, customer) == Decimal("0.00")


def test_blocked_unpost_rolls_back_the_auto_settlement_release(env):
    """المنع ذرّي: إن مُنع الإلغاء بسبب سند مستخدم، لا يُفقد سند التسوية التلقائي."""
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="1000", cash_account=cash,
                   number="SI-ATOMIC")
    post_sales_invoice(inv)
    auto = CustomerPayment.objects.get(auto_settled_invoice=inv)
    # سند مستخدم مرحّل «على الحساب» رُبط بالفاتورة (شكل قديم فاسد)
    manual = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("400"), currency=cur, cash_or_bank_account=cash,
        notes="دفعة عميل")
    post_customer_payment(manual)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=manual, invoice=inv, amount=Decimal("400"),
        amount_in_invoice_currency=Decimal("400"))

    c = _client(owner, tenant)
    resp = c.post(f"/api/sales/invoices/{inv.id}/unpost/", {}, format="json")

    assert resp.status_code == 400
    assert str(manual.id) in resp.json()["error"]
    inv.refresh_from_db()
    assert inv.status == SalesInvoice.STATUS_POSTED
    # سند التسوية التلقائي وقيوده لم يُفقدا (تراجعت المعاملة كاملةً)
    assert CustomerPayment.objects.filter(pk=auto.pk).exists()
    assert JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=auto.pk).exists()


def test_deleting_a_posted_payment_removes_its_journals(env):
    """حذف سند مرحّل كان يترك قيده (دائن ذمم) يتيماً ⇒ رصيد دائن وهمي."""
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="500", number="SI-DEL")
    post_sales_invoice(inv)
    pay = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-20",
        amount=Decimal("500"), currency=cur, cash_or_bank_account=cash)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=pay, invoice=inv, amount=Decimal("500"))
    post_customer_payment(pay)

    c = _client(owner, tenant)
    assert c.delete(f"/api/sales/payments/{pay.id}/").status_code == 204

    assert not JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=pay.id).exists()
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("0.00")
    # الفاتورة وحدها ⇒ العميل مدين بقيمتها لا أقلّ
    assert _net_balance(tenant, customer) == Decimal("500.00")


# ── العرض 3: فاتورة نقدية قديمة بلا مدين ذمم ────────────────────────────────
def _legacy_cash_invoice(tenant, cur, customer, cash, rev, product, *, total="250.00"):
    """قيد قديم: Dr صندوق / Cr إيراد — بلا سطر ذمم إطلاقاً."""
    grand = Decimal(total)
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="SI-6-2", customer=customer, currency=cur,
        invoice_date="2026-06-13", invoice_type=SalesInvoice.INVOICE_CASH,
        cash_or_bank_account=cash, stock_on_post=False,
        status=SalesInvoice.STATUS_POSTED, grand_total=grand,
        amount_paid=Decimal("0"))
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=grand)
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-13", is_posted=True,
        exchange_rate=Decimal("1"), reference_type="SALES_INVOICE", reference_id=inv.id)
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=cash, partner=None,
        debit=grand, credit=Decimal("0"), description=f"تحصيل نقدي — {inv.invoice_number}")
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=rev, partner=None,
        debit=Decimal("0"), credit=grand, description=f"مبيعات — {inv.invoice_number}")
    inv.journal = jh
    inv.save(update_fields=["journal"])
    return inv


def test_auto_settle_skips_invoice_whose_journal_has_no_ar_debit(env):
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _legacy_cash_invoice(tenant, cur, customer, cash, rev, product)

    _auto_settle_cash_sale(inv)

    # لا سند قبض: الذمم لم تُمدَّن أصلاً فلا يجوز أن تُدائن
    assert CustomerPayment.objects.filter(partner=customer).count() == 0
    assert _net_balance(tenant, customer) == Decimal("0.00")


def test_auto_settle_skips_invoice_that_already_has_a_posted_allocation(env):
    """الاعتماد على (grand − amount_paid) وحده لا يكفي: amount_paid يُصفَّر من الخارج."""
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="1000", cash_account=cash,
                   number="SI-GUARD")
    post_sales_invoice(inv)
    assert CustomerPayment.objects.filter(partner=customer).count() == 1

    # محاكاة الجذر: تصفير amount_paid من الخارج ثم إعادة المحاولة
    SalesInvoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal("0"))
    inv.refresh_from_db()
    _auto_settle_cash_sale(inv)

    assert CustomerPayment.objects.filter(partner=customer).count() == 1


# ── المطلب 3: قيد الفاتورة النقدية يمرّ عبر الذمم دائماً ────────────────────
def test_cash_invoice_journal_debits_ar_never_cash_directly(env):
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="777", cash_account=cash,
                   number="SI-DESIGN")
    post_sales_invoice(inv)
    inv.refresh_from_db()

    lines = list(JournalLine.objects.filter(journal_id=inv.journal_id))
    ar_debits = [l for l in lines if l.account_id == ar.id and l.debit > 0]
    assert len(ar_debits) == 1
    assert ar_debits[0].debit == Decimal("777.00")
    assert ar_debits[0].partner_id == customer.id
    # النمط القديم (Dr صندوق داخل قيد الفاتورة) ممنوع
    assert not [l for l in lines if l.account_id == cash.id]


# ── المطلب 4: مجموع التوزيعات لا يتجاوز إجمالي الفاتورة ─────────────────────
def test_allocations_cannot_exceed_invoice_total(env):
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="1000", number="SI-CAP")
    post_sales_invoice(inv)
    first = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-20",
        amount=Decimal("1000"), currency=cur, cash_or_bank_account=cash)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=first, invoice=inv, amount=Decimal("1000"))
    post_customer_payment(first)

    # الجذر: amount_paid صُفِّر من الخارج فسقط الحارس القديم (grand − amount_paid)
    SalesInvoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal("0"))
    second = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-21",
        amount=Decimal("1000"), currency=cur, cash_or_bank_account=cash)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=second, invoice=inv, amount=Decimal("1000"))

    with pytest.raises(ValidationError):
        post_customer_payment(second)

    assert JournalHeader.objects.filter(
        reference_type="CUSTOMER_PAYMENT", reference_id=second.id).count() == 0


# ── المطلب 5: أمر الكشف والإصلاح ────────────────────────────────────────────
def test_audit_command_reports_and_fixes_orphan_allocation(env, capsys):
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="900", number="SI-ORPHAN")
    post_sales_invoice(inv)
    pay = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date="2026-06-20",
        amount=Decimal("900"), currency=cur, cash_or_bank_account=cash)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=pay, invoice=inv, amount=Decimal("900"))
    post_customer_payment(pay)
    # محاكاة الفساد القديم: الفاتورة رجعت مسودة والسند بقي مرحّلاً
    SalesInvoice.objects.filter(pk=inv.pk).update(
        status=SalesInvoice.STATUS_DRAFT, amount_paid=Decimal("0"))

    call_command("audit_ar_integrity")
    out = capsys.readouterr().out
    assert "SI-ORPHAN" in out
    # dry-run لا يغيّر شيئاً
    assert PaymentAllocation.objects.filter(invoice=inv).count() == 1

    call_command("audit_ar_integrity", "--fix")
    # التوزيع اليتيم أُزيل — السند يبقى مرحّلاً «على الحساب»
    assert PaymentAllocation.objects.filter(invoice=inv).count() == 0
    pay.refresh_from_db()
    assert pay.is_posted is True


def test_audit_command_detects_over_allocation_and_credit_customers(env, capsys):
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="1580", cash_account=cash,
                   number="SI-6-154")
    post_sales_invoice(inv)
    # محاكاة العرض 1 كما وقع في الإنتاج: سند تلقائي ثانٍ بنفس التوقيع القديم.
    # (يُرحَّل «على الحساب» ثم يُربط الصفّ مباشرةً — فالحارس الجديد يمنع تكوين
    # هذه الحالة عبر المسار الطبيعي، وهو المقصود.)
    SalesInvoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal("0"))
    inv.refresh_from_db()
    dup = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, payment_date=inv.invoice_date,
        amount=Decimal("1580"), currency=cur, cash_or_bank_account=cash,
        notes=f"تحصيل نقدي تلقائي — فاتورة {inv.invoice_number}")
    post_customer_payment(dup)
    PaymentAllocation.objects.create(
        tenant=tenant, payment=dup, invoice=inv, amount=Decimal("1580"),
        amount_in_invoice_currency=Decimal("1580"))
    assert _net_balance(tenant, customer) == Decimal("-1580.00")

    call_command("audit_ar_integrity")
    out = capsys.readouterr().out
    assert "SI-6-154" in out
    assert customer.name in out  # رصيد دائن لعميل

    call_command("audit_ar_integrity", "--fix")
    inv.refresh_from_db()
    assert _posted_allocations_total(inv) == Decimal("1580.00")
    assert inv.amount_paid == Decimal("1580.00")
    assert _net_balance(tenant, customer) == Decimal("0.00")


# ── المطلب 6: «المدفوع» مسنودٌ بتوزيع — والقديم يُصنَّف ولا يُلمس ─────────────
def _legacy_in_journal_settled_invoice(
    tenant, cur, customer, ar, rev, product, *, total="400.00", number="SI-LEGACY"
):
    """الشكل السابق لـT1: قيد الفاتورة نفسه يحمل التسوية — مدين «شيكات برسم
    التحصيل» ÷ دائن ذمم — و`amount_paid` زاد بلا صفّ توزيع. القيد متوازن وصحيح."""
    grand = Decimal(total)
    under_collection = Account.objects.create(
        tenant=tenant, code="1120-AR", name="شيكات برسم التحصيل",
        account_type="Asset", is_active=True)
    inv = SalesInvoice.objects.create(
        tenant=tenant, invoice_number=number, customer=customer, currency=cur,
        invoice_date="2026-06-14", invoice_type=SalesInvoice.INVOICE_CREDIT,
        stock_on_post=False, status=SalesInvoice.STATUS_POSTED,
        grand_total=grand, amount_paid=grand)
    SalesInvoiceLine.objects.create(
        tenant=tenant, invoice=inv, product=product,
        quantity=Decimal("1"), unit_price=grand)
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-14", is_posted=True,
        exchange_rate=Decimal("1"), reference_type="SALES_INVOICE", reference_id=inv.id)
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ar, partner=customer,
        debit=grand, credit=Decimal("0"), description=f"ذمم — {number}")
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=rev, partner=None,
        debit=Decimal("0"), credit=grand, description=f"مبيعات — {number}")
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=under_collection, partner=None,
        debit=grand, credit=Decimal("0"), description=f"شيكات — {number}")
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ar, partner=customer,
        debit=Decimal("0"), credit=grand, description=f"تسوية داخل القيد — {number}")
    inv.journal = jh
    inv.save(update_fields=["journal"])
    return inv


def test_audit_repairs_amount_paid_that_no_allocation_backs(env, capsys):
    """«مدفوع» بلا سند ولا تسوية داخل القيد ⇒ يتيم حقيقي: يُبلَّغ ثم يُصلَح."""
    tenant, owner, cur, ar, cash, rev, customer, product = env
    inv = _invoice(tenant, cur, customer, product, total="600", number="SI-DRIFT")
    post_sales_invoice(inv)
    SalesInvoice.objects.filter(pk=inv.pk).update(amount_paid=Decimal("600"))

    call_command("audit_ar_integrity")
    out = capsys.readouterr().out
    assert "SI-DRIFT" in out
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("600.00")  # العرض وحده لا يكتب

    call_command("audit_ar_integrity", "--apply")
    inv.refresh_from_db()
    assert inv.amount_paid == Decimal("0.00")
    assert inv.amount_paid == _posted_allocations_total(inv)


def test_audit_reports_legacy_in_journal_settlement_without_repairing_it(env, capsys):
    """قيدٌ يحمل تسويته متوازنٌ وصحيح — يُصنَّف «قديم» ولا يُمسّ `amount_paid`."""
    tenant, owner, cur, ar, cash, rev, customer, product = env
    legacy = _legacy_in_journal_settled_invoice(tenant, cur, customer, ar, rev, product)
    # والشكل الثاني: نقدية ما قبل الميزة 2 — قيدها بلا مدين ذمم إطلاقاً
    direct_cash = _legacy_cash_invoice(tenant, cur, customer, cash, rev, product)
    SalesInvoice.objects.filter(pk=direct_cash.pk).update(amount_paid=Decimal("250"))

    call_command("audit_ar_integrity", "--apply")
    out = capsys.readouterr().out

    assert "SI-LEGACY" in out and "قديم" in out
    legacy.refresh_from_db()
    direct_cash.refresh_from_db()
    assert legacy.amount_paid == Decimal("400.00")
    assert direct_cash.amount_paid == Decimal("250.00")


def test_audit_command_ignores_supplier_credit_balances(env, capsys):
    """أرصدة الموردين الدائنة طبيعية — يجب ألا تُبلَّغ كخطأ."""
    tenant, owner, cur, ar, cash, rev, customer, product = env
    ap = Account.objects.create(
        tenant=tenant, code="2101-AR", name="موردون", account_type="Liability", is_active=True)
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد دائن", partner_type="Supplier", linked_account=ap)
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date="2026-06-13", is_posted=True,
        exchange_rate=Decimal("1"), reference_type="PURCHASE_INVOICE", reference_id=999)
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=ap, partner=supplier,
        debit=Decimal("0"), credit=Decimal("400"), description="ذمم مورد")
    JournalLine.objects.create(
        tenant=tenant, journal=jh, account=rev, partner=None,
        debit=Decimal("400"), credit=Decimal("0"), description="مشتريات")

    call_command("audit_ar_integrity")
    out = capsys.readouterr().out
    assert supplier.name not in out
