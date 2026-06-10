"""task11 M3 — validate_journal_entry must reject partners/cost-centers
belonging to another company."""
import pytest
from django.core.exceptions import ValidationError

from accounting.models import Account, CostCenter, JournalHeader
from accounting.services import create_fiscal_year, validate_journal_entry
from partners.models import Partner
from tenants.models import Tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_tenants():
    t1 = Tenant.objects.create(TenantID=1, CompanyName="A", SubscriptionPlan="Enterprise", Status="Active")
    t2 = Tenant.objects.create(TenantID=2, CompanyName="B", SubscriptionPlan="Enterprise", Status="Active")
    create_fiscal_year(t1, 2026)
    return t1, t2


def _lines(account, partner_id=None, cost_center_id=None):
    return [
        {"account": account.id, "partner": partner_id, "cost_center": cost_center_id, "debit": 100, "credit": 0},
        {"account": account.id, "debit": 0, "credit": 100},
    ]


def test_partner_from_other_tenant_rejected(two_tenants):
    t1, t2 = two_tenants
    acc = Account.objects.create(tenant=t1, code="1101", name="Cash", account_type="Asset")
    foreign_partner = Partner.objects.create(tenant=t2, name="B-Partner", partner_type="Customer")

    header = JournalHeader(tenant_id=t1.TenantID, transaction_date="2026-06-10")
    with pytest.raises(ValidationError, match="Partner"):
        validate_journal_entry(header, _lines(acc, partner_id=foreign_partner.id))


def test_cost_center_from_other_tenant_rejected(two_tenants):
    t1, t2 = two_tenants
    acc = Account.objects.create(tenant=t1, code="1101", name="Cash", account_type="Asset")
    foreign_cc = CostCenter.objects.create(tenant=t2, name="B-CC")

    header = JournalHeader(tenant_id=t1.TenantID, transaction_date="2026-06-10")
    with pytest.raises(ValidationError, match="Cost Center"):
        validate_journal_entry(header, _lines(acc, cost_center_id=foreign_cc.id))


def test_same_tenant_partner_and_cc_accepted(two_tenants):
    t1, _ = two_tenants
    acc = Account.objects.create(tenant=t1, code="1101", name="Cash", account_type="Asset")
    partner = Partner.objects.create(tenant=t1, name="A-Partner", partner_type="Customer")
    cc = CostCenter.objects.create(tenant=t1, name="A-CC")

    header = JournalHeader(tenant_id=t1.TenantID, transaction_date="2026-06-10")
    # No exception expected
    validate_journal_entry(header, _lines(acc, partner_id=partner.id, cost_center_id=cc.id))
