"""TASK-2a — موقع التخزين لكل مخزن: كيانٌ مستقلّ، نقطةُ استبدال، ومهاجرةُ القديم.

`Product.storage_location` (T-ITEMS M5) عمودٌ نصّيٌّ واحد بلا مخزن: يكتب فيه
المستخدم «A86» أو «عمود B صف 7» معاً فيُقرأ النصّ تخميناً، ولا يُعرف في أيّ
مستودع. والمنتج الواحد يُخزَّن في أكثر من مستودع، ولكلّ مستودعٍ عنوانُه —
فالعمود الواحد إمّا يكذب أو يفقد نصف الحقيقة.

الموقع **إرشاديٌّ بلا أثر مخزني أو محاسبي**: لا حركةَ مخزونٍ ولا قيدَ ولا رصيدَ
لكل موقع — الرصيد يبقى رقمَ الشركة الواحد كما هو، والعمود القديم يبقى أيضاً.
"""
import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from rest_framework.test import APIClient, APITestCase

from core.models import ActivityLog
from inventory.models import (
    Product, ProductStorageLocation, StockMovement, Warehouse,
)
from inventory.services import product_storage_locations
from tenants.models import UserCompanyMembership
from tenants.services import create_company

PRODUCTS_URL = "/api/inventory/products/"
BACKFILL_MODULE = "inventory.migrations.0045_product_storage_location"


def storage_url(product_id):
    return f"{PRODUCTS_URL}{product_id}/storage-locations/"


class ProductStorageLocationsApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner_a = User.objects.create_user(username="storage_a", password="x")
        cls.owner_b = User.objects.create_user(username="storage_b", password="x")
        cls.t_a = create_company("شركة المواقع أ", cls.owner_a)
        cls.t_b = create_company("شركة المواقع ب", cls.owner_b)
        cls.wh_1 = Warehouse.objects.create(tenant=cls.t_a, name="مخزن أ", code="WH1")
        cls.wh_2 = Warehouse.objects.create(tenant=cls.t_a, name="مخزن ب", code="WH2")
        cls.wh_other = Warehouse.objects.create(tenant=cls.t_b, name="مخزن ج", code="WH3")

    def setUp(self):
        self.client.force_authenticate(user=self.owner_a)
        self.tenant_id = str(self.t_a.TenantID)

    # ── أدوات ──────────────────────────────────────────────────────────
    def _product(self, name="منتج المواقع"):
        res = self.client.post(
            PRODUCTS_URL, {"name_ar": name}, format="json",
            HTTP_X_TENANT_ID=self.tenant_id)
        assert res.status_code == 201, res.content[:400]
        return res.json()["id"]

    def _get(self, product_id, client=None):
        return (client or self.client).get(
            storage_url(product_id), HTTP_X_TENANT_ID=self.tenant_id)

    def _put(self, product_id, payload, client=None):
        return (client or self.client).put(
            storage_url(product_id), payload, format="json",
            HTTP_X_TENANT_ID=self.tenant_id)

    @staticmethod
    def _sorted(rows):
        """الترتيب المتعاقَد عليه: اسم المخزن ثم id — يُحسب في بايثون فلا يعتمد
        الاختبار على ترتيب محارف العربية في محرّك قاعدةٍ بعينه."""
        return sorted(rows, key=lambda row: (row["warehouse_name"], row["id"]))

    # ── الاستبدال الكامل ───────────────────────────────────────────────
    def test_put_two_kinds_returns_and_persists_them(self):
        product_id = self._product()
        res = self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "grid", "column": "B", "row": "7"},
            {"warehouse": self.wh_2.pk, "kind": "code", "code": "A86"},
        ])
        assert res.status_code == 200, res.content[:400]
        rows = res.json()
        assert len(rows) == 2
        assert rows == self._sorted(rows), rows

        by_warehouse = {row["warehouse"]: row for row in rows}
        grid = by_warehouse[self.wh_1.pk]
        assert grid["warehouse_name"] == "مخزن أ"
        assert (grid["kind"], grid["column"], grid["row"], grid["code"]) == (
            "grid", "B", "7", "")
        assert grid["label"] == "عمود B · صف 7"
        code = by_warehouse[self.wh_2.pk]
        assert (code["kind"], code["code"]) == ("code", "A86")
        assert code["label"] == "A86"

        stored = {
            row.warehouse_id: row
            for row in ProductStorageLocation.objects.filter(product_id=product_id)
        }
        assert set(stored) == {self.wh_1.pk, self.wh_2.pk}
        assert stored[self.wh_1.pk].label == "عمود B · صف 7"
        assert stored[self.wh_1.pk].tenant_id == self.t_a.TenantID

        # الإجراء المجاور على المنتج (`set-active`) يسجّل في `ActivityLog` — وهذا مثله.
        assert ActivityLog.objects.filter(
            tenant=self.t_a, entity_type="product", entity_id=product_id,
            action="update").exists()

    def test_second_put_replaces_in_place_and_empty_list_clears(self):
        product_id = self._product()
        self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "grid", "column": "B", "row": "7"},
            {"warehouse": self.wh_2.pk, "kind": "code", "code": "A86"},
        ])
        kept_id = ProductStorageLocation.objects.get(
            product_id=product_id, warehouse=self.wh_1).pk

        res = self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "code", "code": "C12"},
        ])
        assert res.status_code == 200, res.content[:400]
        rows = list(ProductStorageLocation.objects.filter(product_id=product_id))
        assert len(rows) == 1, "القائمة تصف الحالة النهائية — والغائب يُحذف"
        assert rows[0].pk == kept_id, "الباقي يُحدَّث في مكانه لا يُحذف ويُعاد إنشاؤه"
        assert (rows[0].kind, rows[0].column, rows[0].row, rows[0].code) == (
            "code", "", "", "C12")

        cleared = self._put(product_id, [])
        assert cleared.status_code == 200, cleared.content[:400]
        assert cleared.json() == []
        assert not ProductStorageLocation.objects.filter(product_id=product_id).exists()

    def test_values_are_trimmed_before_saving(self):
        product_id = self._product()
        res = self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "grid", "column": " B ", "row": " 7 "},
        ])
        assert res.status_code == 200, res.content[:400]
        assert res.json()[0]["label"] == "عمود B · صف 7"
        assert res.json()[0]["column"] == "B"

    # ── الرفض: 400 قبل أيّ كتابة ───────────────────────────────────────
    def test_invalid_payloads_are_rejected_before_any_write(self):
        product_id = self._product()
        assert self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "code", "code": "KEEP"},
        ]).status_code == 200
        before = list(
            ProductStorageLocation.objects.filter(product_id=product_id).values())

        cases = {
            "grid بلا صف": [
                {"warehouse": self.wh_1.pk, "kind": "grid", "column": "B"}],
            "grid بلا عمود": [
                {"warehouse": self.wh_1.pk, "kind": "grid", "row": "7"}],
            "grid بعمودٍ من مسافات": [
                {"warehouse": self.wh_1.pk, "kind": "grid", "column": "   ", "row": "7"}],
            "code فارغ": [
                {"warehouse": self.wh_1.pk, "kind": "code", "code": "   "}],
            "مخزن مكرّر": [
                {"warehouse": self.wh_1.pk, "kind": "code", "code": "A1"},
                {"warehouse": self.wh_1.pk, "kind": "code", "code": "A2"},
            ],
            "جسم ليس قائمة": {"warehouse": self.wh_1.pk, "kind": "code", "code": "A1"},
            "نوع مجهول": [
                {"warehouse": self.wh_1.pk, "kind": "shelf", "code": "A1"}],
        }
        for label, payload in cases.items():
            with self.subTest(label):
                res = self._put(product_id, payload)
                assert res.status_code == 400, (label, res.content[:300])
                after = list(ProductStorageLocation.objects.filter(
                    product_id=product_id).values())
                assert after == before, f"{label}: تغيّرت القاعدة رغم الرفض"

        # الرسالة تسمّي المخزن المكرَّر — الخطأ يُصلَح لا يُخمَّن.
        duplicate = self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "code", "code": "A1"},
            {"warehouse": self.wh_1.pk, "kind": "code", "code": "A2"},
        ])
        assert duplicate.status_code == 400
        assert self.wh_1.name in str(duplicate.json())

    def test_body_is_capped_at_two_hundred_locations(self):
        product_id = self._product()
        payload = []
        for index in range(201):
            warehouse = Warehouse.objects.create(
                tenant=self.t_a, name=f"مخزن إضافي {index:03d}")
            payload.append(
                {"warehouse": warehouse.pk, "kind": "code", "code": f"R{index}"})

        res = self._put(product_id, payload)
        assert res.status_code == 400, res.content[:300]
        assert "200" in str(res.json())
        assert not ProductStorageLocation.objects.filter(product_id=product_id).exists()

    # ── العزل بين الشركات ──────────────────────────────────────────────
    def test_tenant_isolation(self):
        product_id = self._product()
        res = self._put(product_id, [
            {"warehouse": self.wh_other.pk, "kind": "code", "code": "Z9"},
        ])
        assert res.status_code == 400, res.content[:300]
        assert not ProductStorageLocation.objects.filter(product_id=product_id).exists()

        foreign = Product.objects.create(
            tenant=self.t_b, sku="FOREIGN-1", name_ar="منتج الشركة الأخرى")
        res = self._put(foreign.pk, [
            {"warehouse": self.wh_other.pk, "kind": "code", "code": "Z9"},
        ])
        assert res.status_code == 404, res.content[:300]
        assert not ProductStorageLocation.objects.filter(product_id=foreign.pk).exists()

        ProductStorageLocation.objects.create(
            tenant=self.t_b, product=foreign, warehouse=self.wh_other,
            kind="code", code="B-77")
        assert self._get(foreign.pk).status_code == 404
        assert self._get(product_id).json() == []
        assert product_storage_locations(
            tenant_id=self.t_b.TenantID, product_id=product_id) == []

    # ── الحقول غير المستعملة تُفرَّغ ─────────────────────────────────────
    def test_kind_blanks_the_other_fields(self):
        product_id = self._product()
        res = self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "grid",
             "column": "C", "row": "3", "code": "A86"},
        ])
        assert res.status_code == 200, res.content[:400]
        row = ProductStorageLocation.objects.get(
            product_id=product_id, warehouse=self.wh_1)
        assert (row.kind, row.column, row.row, row.code) == ("grid", "C", "3", "")
        assert res.json()[0]["code"] == ""

        res = self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "code", "code": "A86",
             "column": "C", "row": "3"},
        ])
        assert res.status_code == 200, res.content[:400]
        row.refresh_from_db()
        assert (row.kind, row.column, row.row, row.code) == ("code", "", "", "A86")

    # ── كرت المنتج ─────────────────────────────────────────────────────
    def test_product_profile_carries_storage_locations(self):
        product_id = self._product()
        self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "grid", "column": "B", "row": "7"},
        ])
        res = self.client.get(
            f"{PRODUCTS_URL}{product_id}/profile/", HTTP_X_TENANT_ID=self.tenant_id)
        assert res.status_code == 200, res.content[:300]
        assert res.json()["storage_locations"] == [{
            "warehouse_id": self.wh_1.pk,
            "warehouse_name": "مخزن أ",
            "kind": "grid",
            "column": "B",
            "row": "7",
            "code": "",
            "label": "عمود B · صف 7",
        }]

    # ── الصلاحية: قاعدة تعديل المنتج نفسها ──────────────────────────────
    def test_viewer_reads_but_cannot_write(self):
        viewer = User.objects.create_user(username="storage_viewer", password="x")
        UserCompanyMembership.objects.create(user=viewer, tenant=self.t_a, role="viewer")
        product_id = self._product()
        assert self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "code", "code": "A86"},
        ]).status_code == 200

        client = APIClient()
        client.force_authenticate(user=viewer)
        assert self._get(product_id, client=client).status_code == 200

        res = self._put(product_id, [], client=client)
        assert res.status_code == 403, res.content[:300]
        assert ProductStorageLocation.objects.filter(product_id=product_id).count() == 1

    def test_seller_writes_like_product_edit(self):
        """لا `inventory.item.manage`: البائع يعدّل المنتج من الفاتورة (قرار المالك)."""
        seller = User.objects.create_user(username="storage_seller", password="x")
        UserCompanyMembership.objects.create(user=seller, tenant=self.t_a, role="sales")
        product_id = self._product()
        client = APIClient()
        client.force_authenticate(user=seller)

        res = self._put(product_id, [
            {"warehouse": self.wh_1.pk, "kind": "code", "code": "A86"},
        ], client=client)
        assert res.status_code == 200, res.content[:400]


# ── الهجرة: نقل القيم القديمة إلى صفوف مواقع ────────────────────────────
# الدالّة تُستدعى مباشرةً (لا الهجرة كوحدة) كي تُختبر شروطها بلا بناء قاعدةٍ
# كاملة من الصفر، وهو نفس عقد `apps` الذي يمرّره `RunPython`.

def _backfill():
    module = importlib.import_module(BACKFILL_MODULE)
    module.backfill_storage_locations(django_apps)


def _company(name):
    owner = User.objects.create_user(username=f"bf-{name}", password="x")
    return create_company(name, owner)


def _legacy(tenant, sku, text):
    return Product.objects.create(
        tenant=tenant, sku=sku, name_ar=sku, storage_location=text)


@pytest.mark.django_db
def test_backfill_moves_the_text_into_the_default_warehouse():
    tenant = _company("هجرة الافتراضي")
    default = Warehouse.objects.get(tenant=tenant, is_default=True)
    product = _legacy(tenant, "BF-1", "  A86  ")

    _backfill()

    row = ProductStorageLocation.objects.get(product_id=product.pk)
    assert (row.warehouse_id, row.kind, row.code) == (default.pk, "code", "A86")
    assert row.tenant_id == tenant.TenantID
    # إرشادي: لا حركة مخزون ولا أثر محاسبي على مَن هاجر.
    assert not StockMovement.objects.filter(product=product).exists()
    assert Product.objects.get(pk=product.pk).storage_location == "  A86  "


@pytest.mark.django_db
def test_backfill_falls_back_to_the_first_active_warehouse():
    tenant = _company("هجرة البديل")
    Warehouse.objects.filter(tenant=tenant).update(is_default=False, is_active=False)
    first = Warehouse.objects.create(tenant=tenant, name="مخزن 1", code="M1")
    Warehouse.objects.create(tenant=tenant, name="مخزن 2", code="M2")
    product = _legacy(tenant, "BF-2", "B-2")

    _backfill()

    assert ProductStorageLocation.objects.get(
        product_id=product.pk).warehouse_id == first.pk


@pytest.mark.django_db
def test_backfill_skips_a_tenant_without_any_usable_warehouse():
    tenant = _company("هجرة بلا مخزن")
    Warehouse.objects.filter(tenant=tenant).delete()
    product = _legacy(tenant, "BF-3", "A86")

    _backfill()

    assert not ProductStorageLocation.objects.filter(product_id=product.pk).exists()

    # ومخازنُ موجودةٌ لكنها كلها معطَّلة ⇒ لا «أوّل فعّال» ⇒ لا صفّ.
    Warehouse.objects.create(tenant=tenant, name="معطَّل", code="OFF", is_active=False)
    _backfill()
    assert not ProductStorageLocation.objects.filter(product_id=product.pk).exists()


@pytest.mark.django_db
def test_backfill_skips_empty_and_blank_text():
    tenant = _company("هجرة الفراغ")
    empty = _legacy(tenant, "BF-4", "")
    blank = _legacy(tenant, "BF-5", "   ")
    null = _legacy(tenant, "BF-6", None)

    _backfill()

    assert not ProductStorageLocation.objects.filter(
        product_id__in=[empty.pk, blank.pk, null.pk]).exists()


@pytest.mark.django_db
def test_backfill_is_idempotent_and_keeps_an_existing_row():
    tenant = _company("هجرة التكرار")
    default = Warehouse.objects.get(tenant=tenant, is_default=True)
    duplicated = _legacy(tenant, "BF-7", "A86")
    ProductStorageLocation.objects.create(
        tenant=tenant, product=duplicated, warehouse=default,
        kind="grid", column="D", row="9")
    fresh = _legacy(tenant, "BF-8", "A87")

    _backfill()
    _backfill()

    assert ProductStorageLocation.objects.filter(product_id=duplicated.pk).count() == 1
    assert ProductStorageLocation.objects.get(product_id=fresh.pk).code == "A87"
    kept = ProductStorageLocation.objects.get(product_id=duplicated.pk)
    assert (kept.kind, kept.column, kept.row, kept.code) == ("grid", "D", "9", "")


@pytest.mark.django_db
def test_backfill_truncates_the_code_to_the_column_length():
    tenant = _company("هجرة الطول")
    product = _legacy(tenant, "BF-9", "قسم-" + "X" * 60)

    _backfill()

    assert ProductStorageLocation.objects.get(product_id=product.pk).code == (
        "قسم-" + "X" * 60)[:50]
