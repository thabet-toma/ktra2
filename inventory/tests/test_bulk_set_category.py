"""C3 — نقل منتجاتٍ (واحداً أو جماعةً) إلى تصنيف، وإعادة ربط تصنيفٍ بأب.

`category` حقلُ **منتجٍ** (عائلة) لا حقلُ براند: نقلُ براندٍ واحد ينقل كل
براندات المنتج نفسه عبر `sync_family_from_product` — لا كتابةً مباشرةً على
`ProductFamily` من الـview. والتصنيف الأب في `PATCH categories/{id}/` محروسٌ
سلفاً في `CategorySerializer._validate_parent`؛ الاختبار هنا يثبّت عقد الـUI
الذي يعتمد عليه (الحلقة 400، والنقل المشروع 200) ولا يغيّر الحارس.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from inventory.models import Product, ProductCategory, ProductFamily
from inventory.views import ProductViewSet
from tenants.models import UserCompanyMembership
from tenants.services import create_company

pytestmark = pytest.mark.django_db

PRODUCTS_URL = "/api/inventory/products/"
CATEGORIES_URL = "/api/inventory/categories/"
BULK_SET_CATEGORY_URL = f"{PRODUCTS_URL}bulk-set-category/"


@pytest.fixture
def catalog():
    """شركتان، ومديرٌ ومستعرض (عرضٌ فقط) في الأولى — نفس نمط S2."""
    manager = User.objects.create_user(username="move-cat-manager", password="x")
    tenant = create_company("شركة نقل التصنيف", manager)
    viewer = User.objects.create_user(username="move-cat-viewer", password="x")
    UserCompanyMembership.objects.create(user=viewer, tenant=tenant, role="viewer")

    other_owner = User.objects.create_user(username="move-cat-other", password="x")
    other_tenant = create_company("شركة نقل التصنيف الأخرى", other_owner)
    return tenant, manager, viewer, other_tenant, other_owner


def _client(tenant, user):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.TenantID)
    return client


def _category(tenant, name, parent=None):
    return ProductCategory.objects.create(tenant=tenant, name=name, parent=parent)


def _product(tenant, sku, name, category=None, family=None):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=name, category=category, family=family,
    )


def _family(tenant, name, category=None):
    return ProductFamily.objects.create(tenant=tenant, name_ar=name, category=category)


def _post(client, body):
    return client.post(BULK_SET_CATEGORY_URL, body, format="json")


def test_moves_two_products_and_reports_the_count(catalog):
    tenant, manager, *_ = catalog
    category = _category(tenant, "إطارات")
    first = _product(tenant, "MOVE-1", "إطار أول")
    second = _product(tenant, "MOVE-2", "إطار ثان")

    res = _post(_client(tenant, manager), {
        "product_ids": [first.id, second.id], "category": category.id,
    })

    assert res.status_code == 200, res.content[:300]
    assert res.json() == {"moved": 2, "brands_moved": 2, "skipped": []}
    for product in (first, second):
        product.refresh_from_db()
        assert product.category_id == category.id


def test_moving_one_brand_moves_the_whole_family(catalog):
    """`category` حقلُ عائلة — نقل براندٍ واحد ينقل إخوته وأباهم معه."""
    tenant, manager, *_ = catalog
    category = _category(tenant, "فلاتر")
    family = _family(tenant, "فلتر زيت")
    brands = [
        _product(tenant, f"FAM-{index}", f"براند {index}", family=family)
        for index in range(1, 4)
    ]

    res = _post(_client(tenant, manager), {
        "product_ids": [brands[0].id], "category": category.id,
    })

    assert res.status_code == 200, res.content[:300]
    assert res.json() == {"moved": 1, "brands_moved": 3, "skipped": []}
    family.refresh_from_db()
    assert family.category_id == category.id
    for product in brands:
        product.refresh_from_db()
        assert product.category_id == category.id


def test_null_category_clears_it(catalog):
    tenant, manager, *_ = catalog
    category = _category(tenant, "إطارات")
    product = _product(tenant, "CLEAR-1", "منتج مصنَّف", category=category)

    res = _post(_client(tenant, manager), {
        "product_ids": [product.id], "category": None,
    })

    assert res.status_code == 200, res.content[:300]
    assert res.json() == {"moved": 1, "brands_moved": 1, "skipped": []}
    product.refresh_from_db()
    assert product.category_id is None


def test_foreign_category_is_rejected_and_nothing_changes(catalog):
    tenant, manager, _, other_tenant, _other_owner = catalog
    foreign = _category(other_tenant, "تصنيف الشركة الأخرى")
    product = _product(tenant, "FOREIGN-CAT-1", "منتج")

    res = _post(_client(tenant, manager), {
        "product_ids": [product.id], "category": foreign.id,
    })

    assert res.status_code == 400, res.content[:300]
    assert "التصنيف غير موجود لهذه الشركة" in str(res.json())
    product.refresh_from_db()
    assert product.category_id is None


def test_foreign_product_id_is_skipped_and_not_written(catalog):
    tenant, manager, _, other_tenant, _other_owner = catalog
    category = _category(tenant, "إطارات")
    other_category = _category(other_tenant, "تصنيف الآخرين")
    mine = _product(tenant, "MINE-1", "منتجي")
    theirs = _product(other_tenant, "THEIRS-1", "منتجهم", category=other_category)

    res = _post(_client(tenant, manager), {
        "product_ids": [mine.id, theirs.id], "category": category.id,
    })

    assert res.status_code == 200, res.content[:300]
    assert res.json() == {"moved": 1, "brands_moved": 1, "skipped": [theirs.id]}
    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.category_id == category.id
    assert theirs.category_id == other_category.id


def test_viewer_without_item_manage_is_forbidden_and_nothing_changes(catalog):
    tenant, _manager, viewer, *_ = catalog
    category = _category(tenant, "إطارات")
    product = _product(tenant, "VIEWER-1", "منتج")

    res = _post(_client(tenant, viewer), {
        "product_ids": [product.id], "category": category.id,
    })

    assert res.status_code == 403, res.content[:300]
    product.refresh_from_db()
    assert product.category_id is None


@pytest.mark.parametrize("kind", [
    "empty_list", "not_a_list", "string_id", "bool_id",
    "missing_category", "string_category", "float_category",
])
def test_malformed_bodies_are_rejected_without_writing(catalog, kind):
    tenant, manager, *_ = catalog
    category = _category(tenant, "إطارات")
    product = _product(tenant, "BAD-BODY-1", "منتج")
    # كلُّ جسمٍ يُبنى هنا من جديد: جسمٌ مشتركٌ بين الحالات يتلوّث بمعرّف الحالة
    # السابقة فيصير الاختبار يثبت شيئاً آخر.
    bodies = {
        "empty_list": {"product_ids": [], "category": category.id},
        "not_a_list": {"product_ids": product.id, "category": category.id},
        "string_id": {"product_ids": [product.id, "x"], "category": category.id},
        "bool_id": {"product_ids": [True], "category": category.id},
        "missing_category": {"product_ids": [product.id]},
        "string_category": {"product_ids": [product.id], "category": "12"},
        "float_category": {"product_ids": [product.id], "category": 1.5},
    }
    # الرسالة بعينها: «التصنيف غير موجود» لا تُشبع رفضاً لمعرّفٍ من نوعٍ خاطئ.
    expected_errors = {
        "empty_list": "لم تُحدَّد منتجات",
        "not_a_list": "لم تُحدَّد منتجات",
        "string_id": "معرّف منتج غير صالح في القائمة",
        "bool_id": "معرّف منتج غير صالح في القائمة",
        "missing_category": "category مطلوب",
        "string_category": "category يجب أن يكون معرّف تصنيف أو null",
        "float_category": "category يجب أن يكون معرّف تصنيف أو null",
    }
    body = bodies[kind]

    res = _post(_client(tenant, manager), body)

    assert res.status_code == 400, (body, res.content[:300])
    assert expected_errors[kind] in str(res.json()), res.content[:300]
    product.refresh_from_db()
    assert product.category_id is None


def test_product_already_in_the_target_is_neither_moved_nor_counted(catalog):
    tenant, manager, *_ = catalog
    category = _category(tenant, "إطارات")
    already = _product(tenant, "ALREADY-1", "في الهدف", category=category)
    other = _product(tenant, "ALREADY-2", "خارجه")

    res = _post(_client(tenant, manager), {
        "product_ids": [already.id, other.id], "category": category.id,
    })

    assert res.status_code == 200, res.content[:300]
    assert res.json() == {"moved": 1, "brands_moved": 1, "skipped": []}


def test_two_requested_brands_of_one_family_move_the_whole_family(catalog):
    """براندان مطلوبان من العائلة نفسها: `moved` 2 و`brands_moved` حجم العائلة."""
    tenant, manager, *_ = catalog
    category = _category(tenant, "فلاتر")
    family = _family(tenant, "فلتر زيت")
    brands = [
        _product(tenant, f"SAME-{index}", f"براند {index}", family=family)
        for index in range(1, 4)
    ]

    res = _post(_client(tenant, manager), {
        "product_ids": [brands[0].id, brands[1].id], "category": category.id,
    })

    assert res.status_code == 200, res.content[:300]
    assert res.json() == {"moved": 2, "brands_moved": 3, "skipped": []}
    for product in brands:
        product.refresh_from_db()
        assert product.category_id == category.id


def test_inconsistent_family_counts_only_the_rows_that_really_changed(catalog):
    """عائلةٌ مرآتها على الهدف وصفوفُها على غيره: نقلُ براندٍ يغيّر صفَّه وحده.

    `sync_family_from_product` لا يدفع شيئاً حين يطابق الأبُ صفَّ البراند بعد
    الكتابة، فعدُّ «كل صفوف العائلة» كان يبالغ بعدد الإخوة الذين لم يتحرّكوا.
    """
    tenant, manager, *_ = catalog
    category = _category(tenant, "فلاتر")
    other = _category(tenant, "إطارات")
    family = _family(tenant, "فلتر زيت", category=category)
    moved = _product(tenant, "ODD-1", "براند أول", category=other, family=family)
    _product(tenant, "ODD-2", "براند ثان", category=other, family=family)
    _product(tenant, "ODD-3", "براند ثالث", category=other, family=family)

    res = _post(_client(tenant, manager), {
        "product_ids": [moved.id], "category": category.id,
    })

    assert res.status_code == 200, res.content[:300]
    assert res.json() == {"moved": 1, "brands_moved": 1, "skipped": []}
    # من القاعدة لا من الردّ: صفٌّ واحد صار على الهدف، والاثنان الباقيان على حالهما.
    assert Product.objects.filter(
        tenant=tenant, family=family, category=category,
    ).count() == 1
    assert Product.objects.filter(
        tenant=tenant, family=family, category=other,
    ).count() == 2


def test_more_than_a_thousand_ids_is_rejected_before_any_write(catalog):
    tenant, manager, *_ = catalog
    category = _category(tenant, "إطارات")
    product = _product(tenant, "CAP-1", "منتج")
    ids = [product.id, *range(10_000, 11_000)]  # 1001 معرّفاً

    res = _post(_client(tenant, manager), {
        "product_ids": ids, "category": category.id,
    })

    assert res.status_code == 400, res.content[:300]
    assert "الحدّ الأقصى 1000 منتج" in str(res.json())
    product.refresh_from_db()
    assert product.category_id is None


def test_a_real_move_is_written_to_the_activity_log(catalog):
    from core.models import ActivityLog

    tenant, manager, *_ = catalog
    category = _category(tenant, "إطارات")
    first = _product(tenant, "LOG-1", "أول")
    second = _product(tenant, "LOG-2", "ثان")

    res = _post(_client(tenant, manager), {
        "product_ids": [first.id, second.id], "category": category.id,
    })

    assert res.status_code == 200, res.content[:300]
    activity = ActivityLog.objects.get(
        tenant=tenant, entity_type="product", action="update",
    )
    assert activity.description == "نقل 2 منتجاً إلى تصنيف «إطارات»"
    assert activity.metadata == {
        "product_ids": [first.id, second.id], "category": category.id,
    }


def test_bulk_set_category_is_a_write_not_a_read_only_post(catalog):
    """`read_only_post_actions` يعامل الـPOST كأنه GET في حارس الكتابة،
    و`finalize_response` في `store/cache.py` **يتخطّى** إبطال كاش المتجر له —
    وهذه نقطة كتابةٌ حقيقية فلا تُذكر هناك."""
    assert "bulk_set_category" not in ProductViewSet.read_only_post_actions


def test_category_reparent_guards_hold_and_valid_move_succeeds(catalog):
    """العقد الذي تبني عليه الشجرة: الحلقة 400، والنقل المشروع 200."""
    tenant, manager, *_ = catalog
    root = _category(tenant, "جذر")
    child = _category(tenant, "ابن", parent=root)
    grandchild = _category(tenant, "حفيد", parent=child)
    other_root = _category(tenant, "فرع آخر")
    client = _client(tenant, manager)

    res = client.patch(
        f"{CATEGORIES_URL}{root.id}/", {"parent": grandchild.id}, format="json",
    )
    assert res.status_code == 400, res.content[:300]
    assert "حلقة" in str(res.json())
    root.refresh_from_db()
    assert root.parent_id is None

    res = client.patch(
        f"{CATEGORIES_URL}{child.id}/", {"parent": other_root.id}, format="json",
    )
    assert res.status_code == 200, res.content[:300]
    child.refresh_from_db()
    assert child.parent_id == other_root.id
