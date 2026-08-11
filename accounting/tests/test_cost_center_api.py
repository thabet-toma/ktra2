"""عقد نقطة مراكز التكلفة.

«تعديل بطاقة الطرف» يحمّل العملات ومراكز التكلفة والبطاقة في `Promise.all`
واحدة — فسقوط مراكز التكلفة بـ500 كان يفرّغ الشاشة كلها ويعرض «حدث خطأ داخلي
في الخادم». السبب كان عمود `Code` الناقص في جدول legacy (هاجرته 0031)، وهذا
الاختبار يثبّت أن النقطة تُرجع الحقول التي تعتمدها الواجهة.
"""
import pytest
from django.contrib.auth.models import User

from accounting.models import CostCenter
from tenants.services import create_company

pytestmark = pytest.mark.django_db


@pytest.fixture
def env(client):
    owner = User.objects.create_user(username="costcenters", password="x")
    tenant = create_company("شركة مراكز التكلفة", owner)
    client.force_login(owner)
    return tenant, client


def test_cost_center_list_returns_the_fields_the_party_card_reads(env):
    tenant, client = env
    CostCenter.objects.create(tenant=tenant, name="فرع رام الله", code="RM")

    response = client.get(
        "/api/accounting/cost-centers/", HTTP_X_TENANT_ID=str(tenant.TenantID))

    assert response.status_code == 200, response.content
    payload = response.json()
    rows = payload["results"] if isinstance(payload, dict) else payload
    assert [(row["name"], row["code"]) for row in rows] == [("فرع رام الله", "RM")]
