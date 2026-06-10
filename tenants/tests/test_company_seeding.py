"""task11 M5 — guarantees for new-company bootstrapping (create_company):

  - COA seeded with the standard professional accounts (not empty, not copied)
  - TenantBooks seeded (10 books per document type)
  - Items / Partners / Sales invoices start completely EMPTY
  - Creator gets a manager membership; TenantSettings row exists
  - Data of existing companies is not touched
"""
import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from accounting.models import Account
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Tenant, TenantBook, TenantSettings, UserCompanyMembership
from tenants.services import COA_DATA, create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def creator():
    return User.objects.create_user(username="founder", password="x")


def test_new_company_coa_seeded_standard(creator):
    tenant = create_company("شركة الاختبار", creator)

    accounts = Account.objects.filter(tenant=tenant)
    assert accounts.count() == len(COA_DATA)

    # Roots exist with correct types
    roots = {a.code: a for a in accounts.filter(parent__isnull=True)}
    assert set(roots.keys()) == {"1", "2", "3", "4", "5"}
    assert roots["1"].account_type == "Asset"
    assert roots["4"].account_type == "Revenue"

    # Hierarchy is wired (e.g. 1101 under 11 under 1)
    cash = accounts.get(code="1101")
    assert cash.parent.code == "11"
    assert cash.parent.parent.code == "1"


def test_new_company_business_data_empty(creator):
    # Pre-existing company with data must not leak into the new company
    old = create_company("الشركة القديمة", creator)
    Partner.objects.create(tenant=old, name="عميل قديم", partner_type="Customer")
    Product.objects.create(tenant=old, sku="OLD-1", name_ar="صنف قديم")

    tenant = create_company("الشركة الجديدة", creator)

    assert Product.objects.filter(tenant=tenant).count() == 0
    assert Partner.objects.filter(tenant=tenant).count() == 0
    assert SalesInvoice.objects.filter(tenant=tenant).count() == 0
    # Old company untouched
    assert Partner.objects.filter(tenant=old).count() == 1
    assert Product.objects.filter(tenant=old).count() == 1


def test_new_company_books_membership_settings(creator):
    tenant = create_company("شركة الدفاتر", creator)

    # 10 books per document type
    per_type = TenantBook.objects.filter(tenant=tenant).count()
    assert per_type == len(TenantBook.DOCUMENT_TYPES) * 10
    assert not TenantBook.objects.filter(tenant=tenant).exclude(last_used_number=0).exists()

    membership = UserCompanyMembership.objects.get(user=creator, tenant=tenant)
    assert membership.role == "manager"

    assert TenantSettings.objects.filter(tenant=tenant).exists()


def test_create_company_rejects_blank_name(creator):
    with pytest.raises(ValidationError):
        create_company("   ", creator)
    assert Tenant.objects.count() == 0
