"""S2 — كتابةُ الكتالوج تشترط `inventory.item.manage`.

كان `CategoryViewSet` يقبل كلَّ دورٍ غير «مستعرض»: البائع والموظف والمحاسب
يُنشئون تصنيفاتٍ ويعيدون ربطها ويحذفونها. وكذلك `ProductViewSet.destroy`
و«أضف براند». قرار المالك (2026-10-21): تُقفل هذه الثلاثة وحدها — إنشاء المنتج
وتعديله يبقيان على قاعدة الأدوار العامة، لأن البيع يعدّل من الفاتورة.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from inventory.models import Product, ProductCategory
from tenants.models import UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db

CATEGORIES_URL = "/api/inventory/categories/"
PRODUCTS_URL = "/api/inventory/products/"

#: الأدوار التي لا تملك `inventory.item.manage` في `core/access.py`.
ROLES_WITHOUT_KEY = ("sales", "staff", "accountant")
#: الأدوار التي تملكه اليوم: المدير («*») والمشتريات.
ROLES_WITH_KEY = ("procurement", "manager")
ALL_ROLES = ROLES_WITHOUT_KEY + ROLES_WITH_KEY


@pytest.fixture
def catalog():
    owner = User.objects.create_user(username="catalog-manager", password="x")
    tenant = create_company("شركة كتابة الكتالوج", owner)
    users = {"manager": owner}
    for role in ROLES_WITHOUT_KEY + ("procurement",):
        user = User.objects.create_user(username=f"catalog-{role}", password="x")
        UserCompanyMembership.objects.create(user=user, tenant=tenant, role=role)
        users[role] = user
    return tenant, users


def _client(tenant, user):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.TenantID)
    return client


def _create_product(client, name="منتج الاختبار"):
    res = client.post(PRODUCTS_URL, {"name_ar": name}, format="json")
    assert res.status_code == 201, res.content[:300]
    return res.json()["id"]


def _category_write(client, operation, category_id):
    if operation == "create":
        return client.post(CATEGORIES_URL, {"name": "تصنيف جديد"}, format="json")
    if operation == "update":
        return client.put(f"{CATEGORIES_URL}{category_id}/", {"name": "اسم معدَّل"}, format="json")
    if operation == "partial_update":
        return client.patch(f"{CATEGORIES_URL}{category_id}/", {"name": "اسم معدَّل"}, format="json")
    return client.delete(f"{CATEGORIES_URL}{category_id}/")


@pytest.mark.parametrize("operation", ("create", "update", "partial_update", "destroy"))
@pytest.mark.parametrize("role", ALL_ROLES)
def test_category_writes_require_item_manage(catalog, role, operation):
    tenant, users = catalog
    client = _client(tenant, users[role])
    category = ProductCategory.objects.create(tenant=tenant, name="إطارات")

    # القراءة تبقى لكل عضو — القفل على الكتابة وحدها.
    assert client.get(CATEGORIES_URL).status_code == 200
    assert client.get(f"{CATEGORIES_URL}{category.id}/").status_code == 200

    res = _category_write(client, operation, category.id)
    expected = {"create": 201, "update": 200, "partial_update": 200, "destroy": 204}[operation]
    if role in ROLES_WITH_KEY:
        assert res.status_code == expected, (role, operation, res.status_code, res.content[:300])
    else:
        assert res.status_code == 403, (role, operation, res.content[:300])
        # لا شيء تحرّك: لا صفَّ جديد، ولا اسماً مُسَّ، ولا صفَّ اختفى.
        assert list(
            ProductCategory.objects.filter(tenant=tenant).values_list("name", flat=True)
        ) == ["إطارات"]


@pytest.mark.parametrize("role", ALL_ROLES)
def test_product_delete_requires_item_manage(catalog, role):
    tenant, users = catalog
    product_id = _create_product(_client(tenant, users["manager"]))

    res = _client(tenant, users[role]).delete(f"{PRODUCTS_URL}{product_id}/")
    if role in ROLES_WITH_KEY:
        assert res.status_code == 204, (role, res.content[:300])
    else:
        assert res.status_code == 403, (role, res.content[:300])
        assert Product.objects.filter(pk=product_id).exists()


@pytest.mark.parametrize("role", ALL_ROLES)
def test_add_brand_requires_item_manage(catalog, role):
    tenant, users = catalog
    product_id = _create_product(_client(tenant, users["manager"]))

    res = _client(tenant, users[role]).post(
        f"{PRODUCTS_URL}add-brand/",
        {"product_id": product_id, "brand": "تويو"},
        format="json",
    )
    if role in ROLES_WITH_KEY:
        # منتجٌ براندُه فارغ: أوّلُ براندٍ صريح **يُسمّي** البراند الضمنيّ (تحديثُ
        # الصفّ القائم لا إنشاءُ صفٍّ جديد)، فتردّ النقطة 200 لا 201.
        assert res.status_code == 200, (role, res.status_code, res.content[:300])
        assert Product.objects.get(pk=product_id).brand == "تويو"
    else:
        assert res.status_code == 403, (role, res.content[:300])
        assert Product.objects.get(pk=product_id).brand == ""


def test_sales_still_creates_and_edits_products(catalog):
    """قرار المالك: القفل على الحذف وحده — البيع يُنشئ ويعدّل (تعديل سريع من الفاتورة)."""
    tenant, users = catalog
    client = _client(tenant, users["sales"])

    res = client.post(PRODUCTS_URL, {"name_ar": "منتج البيع"}, format="json")
    assert res.status_code == 201, res.content[:300]
    product_id = res.json()["id"]

    res = client.patch(f"{PRODUCTS_URL}{product_id}/", {"name_ar": "اسم محدَّث"}, format="json")
    assert res.status_code == 200, res.content[:300]
    assert Product.objects.get(pk=product_id).name_ar == "اسم محدَّث"
