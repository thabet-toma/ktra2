"""نقطة الوكيل للأصناف بعد نقلها من `core` إلى `inventory` — ومعها تصدير `brand`.

النقل كان لإصلاح عقد الاستيراد (`core` ممنوع من `inventory.serializers`)، وهذا
النوع من النقل يُسكِت نقطةً بصمت إن سقط سطر في `core/urls.py` — فالاختبار هنا
يمرّ عبر **المسار العام** لا باستدعاء الدالة، ليثبت أن البوت الخارجي ما زال
يجدها على عنوانها القديم حرفياً.

و`brand`: البوت يطبعها في كل سطر تشخيص وفي أسباب استبعاد الأصناف؛ بدونها كان
يطبع أقواساً فارغة «❌ 205/65/16 () — رصيد 0».
"""
import pytest
from django.contrib.auth.models import User

from inventory.models import Product
from tenants.services import create_company

pytestmark = pytest.mark.django_db

URL = "/api/agent/products/"
KEY = "test-agent-key-strong"


@pytest.fixture
def env(settings):
    settings.AGENT_DB_API_KEY = KEY
    owner = User.objects.create_user(username="agp", password="x")
    tenant = create_company("شركة الأصناف", owner)
    Product.objects.create(
        tenant=tenant, sku="AGP-1", name_ar="إطار", brand="ميشلان")
    return tenant


def test_lookup_exposes_brand(client, env):
    tenant = env

    res = client.get(URL, {"tenant_id": tenant.TenantID}, HTTP_X_AGENT_KEY=KEY)

    assert res.status_code == 200, res.content[:300]
    row = next(r for r in res.json()["results"] if r["sku"] == "AGP-1")
    assert row["brand"] == "ميشلان"


def test_endpoint_still_answers_on_its_public_path(client, env):
    """المسار العام لم يتغيّر بالنقل — لو سقط سطر urls لظهر هنا 404."""
    tenant = env

    assert client.get(
        URL, {"tenant_id": tenant.TenantID}, HTTP_X_AGENT_KEY=KEY,
    ).status_code == 200


def test_missing_key_is_rejected(client, env):
    tenant = env

    assert client.get(URL, {"tenant_id": tenant.TenantID}).status_code == 401
