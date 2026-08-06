"""T-DEFACC: حسابات افتراضية غير فارغة + قيد على حساب الطرف نفسه.

قاعدتان تُغطّيهما هذه الاختبارات لكل معاملة (فاتورة بيع/شراء، سند قبض، سند صرف):

1. حساب الصندوق الافتراضي مضبوط في الإعدادات تلقائياً (لا يبقى فارغاً)، وكل
   مستند يرث منه حين لا يُحدَّد الصندوق صراحةً.
2. القيد يقع على حساب الزبون/المورد نفسه في الشجرة — لا على حساب الأب العام
   (المدينون/الدائنون) — حتى لو كانت مجموعة الطرف تحمل حساب ذمم عاماً.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year, resolve_default_cash_account
from partners.models import Partner, PartnerGroup
from sales.models import CustomerPayment, SalesInvoice, SalesSettings
from sales.services import (
    _resolve_ar_account,
    _resolve_ar_account_for_partner,
    get_or_create_sales_settings,
    post_customer_payment,
)
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="defacc", password="x")
    ils = Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة الافتراضيات", owner)
    create_fiscal_year(tenant, 2026)
    # مجموعة عملاء تحمل حساب الذمم الأب (المدينون التجاريون) — الفخّ الذي كان
    # يجرّ القيد إلى الحساب العام بدل حساب الزبون.
    ar_parent = Account.objects.get(tenant=tenant, code="1103")
    group = PartnerGroup.objects.create(
        tenant=tenant, name="عملاء التجزئة", account_receivable=ar_parent)
    customer = Partner.objects.create(
        tenant=tenant, name="زبون التجزئة", partner_type="Customer", group=group)
    customer.refresh_from_db()
    return tenant, customer, ar_parent, ils


def test_sales_settings_seed_fills_cash_and_ar_defaults(env):
    """شركة جديدة: الصندوق والذمم الافتراضيان يُملآن تلقائياً من الشجرة."""
    tenant, *_ = env
    SalesSettings.objects.filter(tenant_id=tenant.TenantID).update(
        default_cash_account=None, default_ar_account=None)

    ss = get_or_create_sales_settings(tenant)

    assert ss.default_cash_account is not None
    assert ss.default_cash_account.code == "1101"
    assert ss.default_ar_account is not None
    # 1103 = المدينون التجاريون — الأب الصحيح، لا 1201 (أراضٍ) ولا 1106 (دفعات موردين)
    assert ss.default_ar_account.code == "1103"


def test_purchase_settings_seed_fills_cash_default(env):
    """إعدادات الشراء ترث نفس صندوق المبيعات — مصدر واحد لا صندوقان."""
    from logistics.services import get_or_create_purchase_settings

    tenant, *_ = env
    ps = get_or_create_purchase_settings(tenant)

    assert ps.default_cash_account is not None
    assert ps.default_cash_account.code == "1101"


def test_resolve_default_cash_account_is_single_source(env):
    """المُحلِّل المشترك يُرجع صندوق الإعدادات، ويرتدّ إلى 1101 حين تفرغ."""
    tenant, *_ = env
    ss = get_or_create_sales_settings(tenant)
    assert resolve_default_cash_account(tenant.TenantID).id == ss.default_cash_account_id

    SalesSettings.objects.filter(tenant_id=tenant.TenantID).update(default_cash_account=None)
    from logistics.models import PurchaseSettings
    PurchaseSettings.objects.filter(tenant_id=tenant.TenantID).update(default_cash_account=None)
    assert resolve_default_cash_account(tenant.TenantID).code == "1101"


def test_invoice_ar_uses_customer_own_account_not_group_parent(env):
    """فاتورة البيع: المدين حساب الزبون نفسه رغم أن مجموعته تحمل حساب الأب."""
    tenant, customer, ar_parent, ils = env
    assert customer.linked_account_id, "التوقيع يُنشئ حساب الزبون تحت 1103"
    invoice = SalesInvoice.objects.create(
        tenant=tenant, invoice_number="SI-DEF-1", customer=customer, currency=ils,
        invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
        grand_total=Decimal("100"),
    )

    account = _resolve_ar_account(invoice)

    assert account.id == customer.linked_account_id
    assert account.id != ar_parent.id
    assert account.parent_id == ar_parent.id


def test_payment_ar_uses_customer_own_account_not_group_parent(env):
    """سند القبض: الدائن حساب الزبون نفسه لا «المدينون» العام."""
    tenant, customer, ar_parent, _ils = env

    account = _resolve_ar_account_for_partner(customer)

    assert account.id == customer.linked_account_id
    assert account.id != ar_parent.id


def test_customer_payment_journal_credits_customer_own_account(env):
    """القيد المرحَّل نفسه يقع على حساب الزبون — لا على الحساب العام."""
    tenant, customer, ar_parent, ils = env
    cash = get_or_create_sales_settings(tenant).default_cash_account
    pay = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, currency=ils, exchange_rate=Decimal("1"),
        amount=Decimal("250"), cash_or_bank_account=cash,
        payment_date="2026-06-20", is_posted=False,
    )

    post_customer_payment(pay)
    pay.refresh_from_db()

    lines = list(pay.journal.lines.all())
    credit_lines = [l for l in lines if l.base_credit > 0]
    assert len(credit_lines) == 1
    assert credit_lines[0].account_id == customer.linked_account_id
    assert credit_lines[0].account_id != ar_parent.id


class OmittedCashAccountApiTest(APITestCase):
    """سند القبض وسند الصرف بلا حقل صندوق: يُقبلان ويرثان صندوق الشركة."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="defacc-api", password="x")
        cls.currency, _ = Currency.objects.get_or_create(
            Code="DFA", defaults={"Name": "Defacc", "Symbol": "D"})
        cls.tenant = create_company("شركة سندات بلا صندوق", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")
        cls.expected_cash = Account.objects.get(tenant=cls.tenant, code="1101")

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_receipt_without_cash_account_uses_company_default(self):
        res = self.client.post("/api/sales/payments/", {
            "partner": self.customer.id,
            "payment_date": "2026-06-20",
            "amount": "100",
            "currency": self.currency.CurrencyID,
            "exchange_rate": "1",
        }, format="json")

        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["cash_or_bank_account"], self.expected_cash.id)

    def test_voucher_without_cash_account_uses_company_default(self):
        res = self.client.post("/api/logistics/supplier-payments/", {
            "partner": self.supplier.id,
            "payment_date": "2026-06-20",
            "amount": "70",
            "currency": self.currency.CurrencyID,
            "exchange_rate": "1",
        }, format="json")

        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["cash_or_bank_account"], self.expected_cash.id)


def test_partner_without_linked_account_gets_one_before_posting(env):
    """طرف بلا حساب مربوط: يُنشأ له حسابه تحت الأب بدل الترحيل على الأب نفسه."""
    tenant, customer, ar_parent, _ils = env
    Partner.objects.filter(pk=customer.pk).update(linked_account=None)
    customer.refresh_from_db()
    assert customer.linked_account_id is None

    account = _resolve_ar_account_for_partner(customer)

    assert account.id != ar_parent.id
    assert account.parent_id == ar_parent.id
    customer.refresh_from_db()
    assert customer.linked_account_id == account.id


def test_supplier_without_linked_account_gets_one_before_posting(env):
    """مرآة المورد: الذمم الدائنة تقع على حسابه لا على «الدائنون» العام."""
    from logistics.services import _resolve_ap_account

    tenant, *_ = env
    ap_parent = Account.objects.get(tenant=tenant, code="2101")
    supplier = Partner.objects.create(
        tenant=tenant, name="مورد بلا حساب", partner_type="Supplier")
    Partner.objects.filter(pk=supplier.pk).update(linked_account=None)
    supplier.refresh_from_db()

    account = _resolve_ap_account(supplier)

    assert account.id != ap_parent.id
    assert account.parent_id == ap_parent.id
