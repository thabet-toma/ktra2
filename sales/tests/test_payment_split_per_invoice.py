"""سند قبض يغطّي عدّة فواتير: يجب أن يُنشئ قيداً مستقلاً لكل فاتورة (Dr صندوق /
Cr ذمم) بنفس reference_id — كي يظهر تسديد كل فاتورة كقيد/حركة مستقلة في كشف الحساب
ودفتر اليومية، بدل قيد إجمالي واحد.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesInvoice, CustomerPayment, PaymentAllocation
from sales.services import post_customer_payment
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="paysplit", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الدفعات", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-P", name="ذمم", account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1000-P", name="صندوق", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)

    def _inv(number, total):
        return SalesInvoice.objects.create(
            tenant=tenant, invoice_number=number, customer=customer, currency=ils,
            invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
            grand_total=Decimal(str(total)), status=SalesInvoice.STATUS_POSTED,
        )

    inv1 = _inv("SI-P-1", 100)
    inv2 = _inv("SI-P-2", 50)
    return tenant, customer, cash, ar, ils, inv1, inv2


def _payment(tenant, customer, cash, ils, pairs):
    total = sum(Decimal(str(a)) for _, a in pairs)
    pay = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, currency=ils, exchange_rate=Decimal("1"),
        amount=total, cash_or_bank_account=cash, payment_date="2026-06-20", is_posted=False,
    )
    for inv, amt in pairs:
        PaymentAllocation.objects.create(
            tenant=tenant, payment=pay, invoice=inv, amount=Decimal(str(amt)))
    return pay


def _journals(tenant, pay):
    return list(
        JournalHeader.objects.filter(
            tenant_id=tenant.TenantID, reference_type="CUSTOMER_PAYMENT", reference_id=pay.id
        ).order_by("id")
    )


def test_payment_creates_separate_journal_per_invoice(env):
    tenant, customer, cash, ar, ils, inv1, inv2 = env
    pay = _payment(tenant, customer, cash, ils, [(inv1, 100), (inv2, 50)])

    post_customer_payment(pay)
    pay.refresh_from_db()

    journals = _journals(tenant, pay)
    # قيد مستقل لكل فاتورة (لا قيد إجمالي واحد)
    assert len(journals) == 2
    # كل قيد متوازن ويحمل سطر صندوق مدين + سطر ذمم دائن موسوم بالعميل
    ar_total = Decimal("0")
    seen_invoices = set()
    for jh in journals:
        lines = list(jh.lines.all())
        assert sum(l.debit for l in lines) == sum(l.credit for l in lines)
        cash_lines = [l for l in lines if l.account_id == cash.id]
        ar_lines = [l for l in lines if l.account_id == ar.id]
        assert cash_lines and all(l.partner_id is None for l in cash_lines)
        assert ar_lines and all(l.partner_id == customer.id for l in ar_lines)
        for l in ar_lines:
            ar_total += l.base_credit
            seen_invoices.add(l.description)
    assert ar_total == Decimal("150.00")
    joined = " | ".join(seen_invoices)
    assert "SI-P-1" in joined and "SI-P-2" in joined
    # كشف الحساب: كل فاتورة سطر ذمم مستقل موسوم بالعميل
    ar_partner_lines = JournalLine.objects.filter(
        tenant_id=tenant.TenantID, account=ar, partner=customer
    )
    assert ar_partner_lines.count() == 2


def test_single_invoice_payment_one_journal(env):
    tenant, customer, cash, ar, ils, inv1, _inv2 = env
    pay = _payment(tenant, customer, cash, ils, [(inv1, 100)])

    post_customer_payment(pay)
    pay.refresh_from_db()

    journals = _journals(tenant, pay)
    assert len(journals) == 1
    ar_lines = list(journals[0].lines.filter(account=ar))
    assert len(ar_lines) == 1
    assert ar_lines[0].base_credit == Decimal("100.00")
    assert "SI-P-1" in ar_lines[0].description
    # payment.journal يشير لأول قيد
    assert pay.journal_id == journals[0].id
