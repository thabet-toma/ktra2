"""نوع الطرف المرتبط بالحساب (T-COAMENU).

شجرة الحسابات تعرض الطرف المرتبط بالحساب، لكنها كانت تعيد الاسم فقط — فلا تعرف
الواجهة أعميلٌ هو أم مورد، ولا تستطيع أن تقترح إجراءه الصحيح (فاتورة مبيعات
وسند قبض للعميل، فاتورة شراء وسند صرف للمورد). النوع جزء من عقد الحساب الآن.
"""
import pytest
from django.contrib.auth.models import User

from accounting.models import Account
from partners.models import Partner
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(client):
    owner = User.objects.create_user(username="coamenu", password="x")
    tenant = create_company("شركة الشجرة", owner)
    client.force_login(owner)
    return tenant, client


def _account(tenant, code, name):
    return Account.objects.create(
        tenant=tenant, code=code, name=name, account_type="Asset", is_active=True)


def _rows(client, tenant):
    response = client.get(
        "/api/accounting/accounts/", HTTP_X_TENANT_ID=str(tenant.TenantID))
    assert response.status_code == 200, response.content
    payload = response.json()
    return payload["results"] if isinstance(payload, dict) else payload


def test_linked_partner_exposes_its_type(env):
    tenant, client = env
    customer_account = _account(tenant, "1101-C", "ذمم زبون")
    supplier_account = _account(tenant, "2101-S", "ذمم مورد")
    Partner.objects.create(
        tenant=tenant, name="زبون الشجرة", partner_type="Customer",
        linked_account=customer_account)
    Partner.objects.create(
        tenant=tenant, name="مورد الشجرة", partner_type="Supplier",
        linked_account=supplier_account)

    by_id = {row["id"]: row for row in _rows(client, tenant)}
    assert by_id[customer_account.pk]["linked_partner"]["partner_type"] == "Customer"
    assert by_id[customer_account.pk]["linked_partner"]["trade_name"] == "زبون الشجرة"
    assert by_id[supplier_account.pk]["linked_partner"]["partner_type"] == "Supplier"


def test_account_without_a_partner_reports_none(env):
    tenant, client = env
    plain = _account(tenant, "1105-X", "حساب بلا طرف")
    by_id = {row["id"]: row for row in _rows(client, tenant)}
    assert by_id[plain.pk]["linked_partner"] is None
