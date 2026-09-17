"""سند قبض «على الحساب»: دفعة بلا توزيع (أو بتوزيع جزئي) تُرحَّل وتؤثّر على كشف
حساب العميل (Dr صندوق / Cr ذمم) دون تسديد أي فاتورة، ثم تُوزَّع لاحقاً على الفواتير
بلا قيد جديد (الذمم خُفِّضت أصلاً وقت الترحيل — التوزيع ربط فقط).
"""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesInvoice, CustomerPayment, PaymentAllocation
from sales.services import allocate_customer_payment, post_customer_payment
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    owner = User.objects.create_user(username="onaccount", password="x")
    ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company("شركة على الحساب", owner)
    create_fiscal_year(tenant, 2026)
    ar = Account.objects.create(
        tenant=tenant, code="1101-A", name="ذمم", account_type="Asset", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1000-A", name="صندوق", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)

    def _inv(number, total):
        return SalesInvoice.objects.create(
            tenant=tenant, invoice_number=number, customer=customer, currency=ils,
            invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
            grand_total=Decimal(str(total)), status=SalesInvoice.STATUS_POSTED,
        )

    inv1 = _inv("SI-A-1", 100)
    inv2 = _inv("SI-A-2", 50)
    return tenant, customer, cash, ar, ils, inv1, inv2


def _payment(tenant, customer, cash, ils, amount, pairs=()):
    pay = CustomerPayment.objects.create(
        tenant=tenant, partner=customer, currency=ils, exchange_rate=Decimal("1"),
        amount=Decimal(str(amount)), cash_or_bank_account=cash,
        payment_date="2026-06-20", is_posted=False,
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


def test_post_without_allocations_credits_customer_account(env):
    """المبلغ بلا توزيع: يُقبل الترحيل ويظهر في كشف الحساب بلا تسديد فواتير."""
    tenant, customer, cash, ar, ils, inv1, inv2 = env
    pay = _payment(tenant, customer, cash, ils, 300)

    post_customer_payment(pay)
    pay.refresh_from_db()

    assert pay.is_posted is True
    journals = _journals(tenant, pay)
    assert len(journals) == 1
    lines = list(journals[0].lines.all())
    cash_lines = [l for l in lines if l.account_id == cash.id]
    ar_lines = [l for l in lines if l.account_id == ar.id]
    assert cash_lines and cash_lines[0].base_debit == Decimal("300.00")
    assert all(l.partner_id is None for l in cash_lines)
    # سطر الذمم موسوم بالعميل — فيؤثّر على كشف حسابه (رصيد لصالحه)
    assert ar_lines and ar_lines[0].base_credit == Decimal("300.00")
    assert ar_lines[0].partner_id == customer.id
    # لا فاتورة سُدِّدت
    inv1.refresh_from_db()
    inv2.refresh_from_db()
    assert inv1.amount_paid == Decimal("0")
    assert inv2.amount_paid == Decimal("0")


def test_partial_allocation_posts_remainder_on_account(env):
    """توزيع جزئي: الفاتورة تُسدَّد بجزء والباقي على الحساب — قيد لكل جزء."""
    tenant, customer, cash, ar, ils, inv1, _inv2 = env
    pay = _payment(tenant, customer, cash, ils, 150, [(inv1, 100)])

    post_customer_payment(pay)

    journals = _journals(tenant, pay)
    assert len(journals) == 2  # قيد الفاتورة + قيد الرصيد على الحساب
    ar_credit = sum(
        l.base_credit for j in journals for l in j.lines.all() if l.account_id == ar.id
    )
    assert ar_credit == Decimal("150.00")
    inv1.refresh_from_db()
    assert inv1.amount_paid == Decimal("100.00")


def test_allocate_after_post_settles_invoice_without_new_journal(env):
    """التوزيع اللاحق على فاتورة: ربط فقط + تحديث المدفوع، بلا قيد جديد."""
    tenant, customer, cash, ar, ils, inv1, inv2 = env
    pay = _payment(tenant, customer, cash, ils, 150)
    post_customer_payment(pay)
    journals_before = len(_journals(tenant, pay))

    allocate_customer_payment(pay, [{"invoice": inv1.id, "amount": "100"}])

    inv1.refresh_from_db()
    assert inv1.amount_paid == Decimal("100.00")
    assert len(_journals(tenant, pay)) == journals_before
    alloc = PaymentAllocation.objects.get(payment=pay, invoice=inv1)
    assert alloc.amount == Decimal("100.00")
    assert alloc.amount_in_invoice_currency == Decimal("100.00")

    # المتبقّي غير الموزَّع يقبل توزيعاً ثانياً
    allocate_customer_payment(pay, [{"invoice": inv2.id, "amount": "50"}])
    inv2.refresh_from_db()
    assert inv2.amount_paid == Decimal("50.00")


def test_allocate_beyond_payment_amount_rejected(env):
    tenant, customer, cash, ar, ils, inv1, inv2 = env
    pay = _payment(tenant, customer, cash, ils, 100)
    post_customer_payment(pay)

    with pytest.raises(ValidationError):
        allocate_customer_payment(pay, [{"invoice": inv1.id, "amount": "100"},
                                        {"invoice": inv2.id, "amount": "50"}])
    inv1.refresh_from_db()
    assert inv1.amount_paid == Decimal("0")


def test_allocations_exceeding_payment_amount_rejected_on_post(env):
    tenant, customer, cash, ar, ils, inv1, inv2 = env
    pay = _payment(tenant, customer, cash, ils, 100, [(inv1, 100), (inv2, 50)])

    with pytest.raises(ValidationError):
        post_customer_payment(pay)


class CustomerPaymentApiOnAccountTest(APITestCase):
    """نفس العقد عبر الـ API: إنشاء بلا/بجزء توزيع + نقطة التوزيع اللاحق."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="onaccount_api", password="x")
        cls.currency, _ = Currency.objects.get_or_create(
            Code="OAC", defaults={"Name": "OnAccount", "Symbol": "O"})
        cls.tenant = create_company("شركة على الحساب API", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-B", name="ذمم", account_type="Asset", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1000-B", name="صندوق", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل API", partner_type="Customer", linked_account=cls.ar)
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="SI-API-1", customer=cls.customer,
            currency=cls.currency, invoice_date="2026-06-15",
            invoice_type=SalesInvoice.INVOICE_CREDIT, grand_total=Decimal("100"),
            status=SalesInvoice.STATUS_POSTED,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _create(self, amount, allocations=None):
        body = {
            "partner": self.customer.id,
            "payment_date": "2026-06-20",
            "amount": str(amount),
            "currency": self.currency.CurrencyID,
            "exchange_rate": "1",
            "cash_or_bank_account": self.cash.id,
        }
        if allocations is not None:
            body["allocations"] = allocations
        return self.client.post("/api/sales/payments/", body, format="json")

    def test_create_with_partial_allocation_accepted(self):
        res = self._create(150, [{"invoice": self.invoice.id, "amount": "100"}])
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["unallocated_amount"], "50.00")

    def test_create_with_over_allocation_rejected(self):
        res = self._create(50, [{"invoice": self.invoice.id, "amount": "100"}])
        self.assertEqual(res.status_code, 400)

    def test_list_filtered_by_partner(self):
        """بطاقة الزبون تجلب سنداته وحدها (?partner=) لا كل سندات الشركة."""
        other = Partner.objects.create(
            tenant=self.tenant, name="عميل آخر", partner_type="Customer", linked_account=self.ar)
        mine = self._create(100)
        self.assertEqual(mine.status_code, 201, mine.data)
        theirs = self.client.post(
            "/api/sales/payments/",
            {
                "partner": other.id,
                "payment_date": "2026-06-20",
                "amount": "40",
                "currency": self.currency.CurrencyID,
                "exchange_rate": "1",
                "cash_or_bank_account": self.cash.id,
            },
            format="json",
        )
        self.assertEqual(theirs.status_code, 201, theirs.data)

        res = self.client.get(f"/api/sales/payments/?partner={self.customer.id}")
        self.assertEqual(res.status_code, 200)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        self.assertTrue(rows)
        self.assertTrue(all(r["partner"] == self.customer.id for r in rows))

    def test_post_then_allocate_endpoint(self):
        # T-AUTOPOST: الحفظ يُرحّل السند فوراً؛ التوزيع يأتي بعده.
        res = self._create(100)
        self.assertEqual(res.status_code, 201, res.data)
        pid = res.data["id"]
        self.assertTrue(res.data["is_posted"], res.data)

        allocated = self.client.post(
            f"/api/sales/payments/{pid}/allocate/",
            {"allocations": [{"invoice": self.invoice.id, "amount": "100"}]},
            format="json",
        )
        self.assertEqual(allocated.status_code, 200, allocated.data)
        self.assertEqual(allocated.data["unallocated_amount"], "0.00")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal("100.00"))


def _dealloc_url(pay):
    return f"/api/sales/payments/{pay.id}/deallocate/"


class CustomerPaymentDeallocateTest(APITestCase):
    """A1-3: فكّ توزيعٍ واحد — المبلغ يعود «على الحساب» بلا قيد جديد، والفاتورة
    تعود بمدفوعها وحالتها، والسند بمتاحه غير الموزَّع."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dealloc_c", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        cls.tenant = create_company("شركة فك التوزيع", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-D", name="ذمم", account_type="Asset", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1000-D", name="صندوق", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الفك", partner_type="Customer", linked_account=cls.ar)

    def _auth(self, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.user)
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def _invoice(self, number, total=100, currency=None):
        return SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.customer,
            currency=currency or self.ils, invoice_date="2026-06-15",
            invoice_type=SalesInvoice.INVOICE_CREDIT, grand_total=Decimal(str(total)),
            status=SalesInvoice.STATUS_POSTED,
        )

    def _journal_count(self, pay):
        return JournalHeader.objects.filter(
            tenant_id=self.tenant.TenantID, reference_type="CUSTOMER_PAYMENT",
            reference_id=pay.id).count()

    def _assert_restored(self, pay, inv, res):
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["unallocated_amount"], "150.00")
        self.assertEqual(res.data["allocations"], [])
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal("0.00"))
        detail = self.client.get(f"/api/sales/invoices/{inv.id}/", **self._auth())
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["payment_status"], "unpaid")
        self.assertFalse(PaymentAllocation.objects.filter(payment=pay).exists())

    def test_deallocate_late_allocation_restores_invoice_and_voucher(self):
        inv = self._invoice("SI-D-1")
        pay = _payment(self.tenant, self.customer, self.cash, self.ils, 150)
        post_customer_payment(pay)
        allocate_customer_payment(pay, [{"invoice": inv.id, "amount": "100"}])
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal("100.00"))
        journals = self._journal_count(pay)
        alloc = PaymentAllocation.objects.get(payment=pay)

        res = self.client.post(
            _dealloc_url(pay), {"allocation": alloc.id}, format="json", **self._auth())
        self._assert_restored(pay, inv, res)
        # ربطٌ فقط: لا قيد يُضاف ولا يُحذف.
        self.assertEqual(self._journal_count(pay), journals)
        # الفاتورة تقبل توزيعاً جديداً بعد الفكّ.
        allocate_customer_payment(pay, [{"invoice": inv.id, "amount": "100"}])
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, Decimal("100.00"))

    def test_deallocate_allocation_posted_with_voucher(self):
        inv = self._invoice("SI-D-2")
        pay = _payment(self.tenant, self.customer, self.cash, self.ils, 150, [(inv, 100)])
        post_customer_payment(pay)
        alloc = PaymentAllocation.objects.get(payment=pay)
        res = self.client.post(
            _dealloc_url(pay), {"allocation": alloc.id}, format="json", **self._auth())
        self._assert_restored(pay, inv, res)

    def test_deallocate_on_draft_voucher_only_unlinks(self):
        inv = self._invoice("SI-D-3")
        pay = _payment(self.tenant, self.customer, self.cash, self.ils, 150, [(inv, 100)])
        alloc = PaymentAllocation.objects.get(payment=pay)
        res = self.client.post(
            _dealloc_url(pay), {"allocation": alloc.id}, format="json", **self._auth())
        self._assert_restored(pay, inv, res)

    def test_auto_cash_settlement_refused(self):
        """سند التسوية التلقائية يُحرَّر مع إلغاء ترحيل فاتورته، لا بفكّ توزيعه."""
        inv = self._invoice("SI-D-AUTO")
        pay = _payment(self.tenant, self.customer, self.cash, self.ils, 100, [(inv, 100)])
        pay.auto_settled_invoice = inv
        pay.save(update_fields=["auto_settled_invoice"])
        post_customer_payment(pay)
        alloc = PaymentAllocation.objects.get(payment=pay)
        res = self.client.post(
            _dealloc_url(pay), {"allocation": alloc.id}, format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("ألغِ ترحيل الفاتورة", res.data["error"])
        self.assertTrue(PaymentAllocation.objects.filter(pk=alloc.pk).exists())

    def test_other_tenant_allocation_is_404(self):
        other_user = User.objects.create_user(username="dealloc_c2", password="x")
        other = create_company("شركة أخرى للفك", other_user)
        create_fiscal_year(other, 2026)
        oar = Account.objects.create(
            tenant=other, code="1101-O", name="ذمم", account_type="Asset", is_active=True)
        ocash = Account.objects.create(
            tenant=other, code="1000-O", name="صندوق", account_type="Asset", is_active=True)
        ocust = Partner.objects.create(
            tenant=other, name="عميلهم", partner_type="Customer", linked_account=oar)
        oinv = SalesInvoice.objects.create(
            tenant=other, invoice_number="SI-O-1", customer=ocust, currency=self.ils,
            invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
            grand_total=Decimal("100"), status=SalesInvoice.STATUS_POSTED)
        opay = _payment(other, ocust, ocash, self.ils, 100, [(oinv, 100)])
        post_customer_payment(opay)
        oalloc = PaymentAllocation.objects.get(payment=opay)
        mine = _payment(self.tenant, self.customer, self.cash, self.ils, 50)

        # سندهم عبر شركتي ⇒ 404؛ وتوزيعهم تحت سندي ⇒ 404.
        res = self.client.post(
            _dealloc_url(opay), {"allocation": oalloc.id}, format="json", **self._auth())
        self.assertEqual(res.status_code, 404, res.data)
        res = self.client.post(
            _dealloc_url(mine), {"allocation": oalloc.id}, format="json", **self._auth())
        self.assertEqual(res.status_code, 404, res.data)
        self.assertTrue(PaymentAllocation.objects.filter(pk=oalloc.pk).exists())
        oinv.refresh_from_db()
        self.assertEqual(oinv.amount_paid, Decimal("100.00"))

    def test_cross_currency_posted_allocation_refused(self):
        """سند بعملةٍ غير عملة الفاتورة رُحِّل بقيد فرق عملة لتوزيعه — فكّه يترك
        الفرق معلّقاً، فالمخرج إلغاء ترحيل السند."""
        from accounting.models import ExchangeRate
        usd = Currency.objects.create(Code="USD", Name="دولار", Symbol="$")
        ExchangeRate.objects.create(
            tenant=self.tenant, from_currency=usd, to_currency=self.ils,
            rate=Decimal("4"), effective_date="2026-01-01")
        ExchangeRate.objects.create(
            tenant=self.tenant, from_currency=self.ils, to_currency=usd,
            rate=Decimal("0.25"), effective_date="2026-01-01")
        inv = self._invoice("SI-D-FX", total=400)
        pay = CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, currency=usd,
            exchange_rate=Decimal("4"), amount=Decimal("100"),
            cash_or_bank_account=self.cash, payment_date="2026-06-20")
        PaymentAllocation.objects.create(
            tenant=self.tenant, payment=pay, invoice=inv, amount=Decimal("100"))
        post_customer_payment(pay)
        inv.refresh_from_db()
        paid_before = inv.amount_paid
        alloc = PaymentAllocation.objects.get(payment=pay)

        res = self.client.post(
            _dealloc_url(pay), {"allocation": alloc.id}, format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("ألغِ ترحيل السند", res.data["error"])
        self.assertTrue(PaymentAllocation.objects.filter(pk=alloc.pk).exists())
        inv.refresh_from_db()
        self.assertEqual(inv.amount_paid, paid_before)
