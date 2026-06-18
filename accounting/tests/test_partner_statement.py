"""FEAT-4 — Party (customer/supplier) profile: account statement running
balance reconciles to the canonical posted balance, and the profile endpoint
reports the correct Dr/Cr side.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import partner_account_statement, partner_posted_balance
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

pytestmark = pytest.mark.django_db


def _journal(tenant, *, date, lines):
    """lines: list of (account, debit, credit, partner)."""
    jh = JournalHeader.objects.create(
        tenant=tenant, transaction_date=date, is_posted=True, exchange_rate=Decimal("1"),
        reference_type="SALES_INVOICE", reference_id=1)
    for acc, d, c, partner in lines:
        JournalLine.objects.create(
            tenant=tenant, journal=jh, account=acc,
            debit=Decimal(str(d)), credit=Decimal(str(c)), partner=partner)
    return jh


@pytest.fixture
def env():
    owner = User.objects.create_user(username="pstmt", password="x")
    Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
    tenant = create_company("شركة كشف الحساب", owner)
    ar = Account.objects.create(
        tenant=tenant, code="1101-X", name="ذمم", account_type="Asset", is_active=True)
    rev = Account.objects.create(
        tenant=tenant, code="4101-X", name="إيراد", account_type="Revenue", is_active=True)
    cash = Account.objects.create(
        tenant=tenant, code="1110-X", name="صندوق", account_type="Asset", is_active=True)
    customer = Partner.objects.create(
        tenant=tenant, name="عميل", partner_type="Customer", linked_account=ar)
    return tenant, ar, rev, cash, customer


def test_customer_statement_running_balance_reconciles(env):
    tenant, ar, rev, cash, customer = env
    # Sale 100 on credit (Dr AR / Cr Rev), then receipt 30 (Dr cash / Cr AR).
    _journal(tenant, date="2026-06-01",
             lines=[(ar, 100, 0, customer), (rev, 0, 100, None)])
    _journal(tenant, date="2026-06-05",
             lines=[(cash, 30, 0, None), (ar, 0, 30, customer)])

    st = partner_account_statement(
        tenant_id=tenant.TenantID, partner_id=customer.id, is_supplier=False)
    assert st["count"] == 2
    balances = [Decimal(r["running_balance"]) for r in st["results"]]
    assert balances == [Decimal("100"), Decimal("70")]
    assert Decimal(st["closing_balance"]) == Decimal("70")

    # reconciles to the canonical posted balance
    debit, credit = partner_posted_balance(tenant.TenantID, customer.id)
    assert (debit - credit) == Decimal(st["closing_balance"])


def test_statement_pagination(env):
    tenant, ar, rev, cash, customer = env
    for i in range(5):
        _journal(tenant, date=f"2026-06-0{i+1}",
                 lines=[(ar, 10, 0, customer), (rev, 0, 10, None)])
    page = partner_account_statement(
        tenant_id=tenant.TenantID, partner_id=customer.id, is_supplier=False,
        limit=2, offset=2)
    assert page["count"] == 5
    assert len(page["results"]) == 2
    # third row running balance = 30 (after 3 entries of 10)
    assert Decimal(page["results"][0]["running_balance"]) == Decimal("30")


class PartnerProfileEndpointTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ppstmt", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة بطاقة شريك", cls.user)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-Y", name="ذمم", account_type="Asset", is_active=True)
        cls.rev = Account.objects.create(
            tenant=cls.tenant, code="4101-Y", name="إيراد", account_type="Revenue", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer", linked_account=cls.ar)
        _journal(cls.tenant, date="2026-06-01",
                 lines=[(cls.ar, 250, 0, cls.customer), (cls.rev, 0, 250, None)])

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_profile_and_statement_endpoints(self):
        r = self.client.get(f"/api/partners/{self.customer.id}/profile/", **self._auth())
        assert r.status_code == 200, r.content
        body = r.json()
        assert Decimal(body["balance"]) == Decimal("250")
        assert body["balance_side"] == "Dr"

        r = self.client.get(f"/api/partners/{self.customer.id}/statement/", **self._auth())
        assert r.status_code == 200, r.content
        assert Decimal(r.json()["closing_balance"]) == Decimal("250")
