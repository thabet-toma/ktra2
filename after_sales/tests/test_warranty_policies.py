"""#231 — سياسات الكفالة تحلّ محلّ حقلَي المنتج.

يثبت:
  1. التحقّق: طبقة واحدة على الأقل > 0، `manufacturer_months` مرتبطةٌ بوجود
     الجهة اتجاهين، `serial` مرفوضةٌ لمنتج خدمة، الشروط البديلة بسقف 2000.
  2. CRUD: صفٌّ واحدٌ لكل براند (تكرار المنتج 400)، تعديلٌ، وتحقّق العزل بين
     الشركات (منتج/جهة شركة أخرى → 400 عبر الجسم، والسجل نفسه → 404 عبر الرابط).
  3. البوابة: `require_module` قبل `require_perm` (404 بلا ترخيص)، وقراءة
     `aftersales.warranty.view` مقابل كتابة `aftersales.settings.manage`.
  4. `create_auto_warranty_cards` يقرأ `dealer_months`/`terms_text` من
     السياسة، ولا سياسة = لا بطاقة، وتعديل السياسة بعد البيع لا يمسّ بطاقةً صدرت.
  5. `bulk/` يكتب صفاً واحداً لكل براند تحت منتجٍ أبٍ أو تصنيف — كلٌّ أو لا شيء.
  6. الهجرة: `policy_kwargs_from_legacy_product` (الدالة التي تكتبها فعلياً
     `after_sales/migrations/0008_backfill_warranty_policies.py`) تُختبَر
     مباشرةً بحالةٍ تحاكي شكل المنتج قبل حذف عمودَيه.
"""
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.contrib.auth.models import User

from after_sales.models import ManufacturerWarrantor, WarrantyCard, WarrantyPolicy
from core.models import TenantModule
from inventory.models import Product, ProductCategory, ProductSerial
from inventory.serials import SERIAL_MODE_OFF, SERIAL_MODE_REQUIRED
from inventory.services import (
    add_brand_to_family, create_product_with_family, record_stock_movement,
)
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from sales.services import get_or_create_sales_settings
from tenants.models import UserCompanyMembership
from tenants.services import create_company

from .test_warranty import PURCHASE_DATE, WarrantyTestBase

POLICIES = "/api/after-sales/warranty-policies/"
BULK = f"{POLICIES}bulk/"
SERIAL_IMPACT = f"{POLICIES}serial-impact/"


class WarrantyPolicyTestBase(WarrantyTestBase):
    def setUp(self):
        super().setUp()
        self.warrantor = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="جهة كفالة تجريبية",
        )
        self.sales_user = User.objects.create_user(username="sales-231", password="x")
        UserCompanyMembership.objects.create(
            user=self.sales_user, tenant=self.tenant, role="sales",
        )
        self.ess_user = User.objects.create_user(username="ess-231", password="x")
        UserCompanyMembership.objects.create(
            user=self.ess_user, tenant=self.tenant, role="ess",
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)
        return self

    def new_product(self, **overrides):
        overrides.setdefault("tenant", self.tenant)
        overrides.setdefault("sku", f"WP-{Product.objects.count() + 1}")
        overrides.setdefault("name_ar", "منتجٌ للاختبار")
        overrides.setdefault("is_serialized", True)
        overrides.setdefault("quantity_on_hand", Decimal("0"))
        overrides.setdefault("avg_cost", Decimal("0"))
        return Product.objects.create(**overrides)


# ══════════════════════════════════════════════════════════════════════════
# التحقّق
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicyValidationTest(WarrantyPolicyTestBase):
    def test_at_least_one_layer_must_be_positive(self):
        product = self.new_product()

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 0,
             "manufacturer_months": 0, "supplier_months": 0},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("dealer_months", response.data)

    def test_a_supplier_only_policy_is_rejected(self):
        """كفالة المورّد داخلية لا طبقة للزبون — وحدها كانت ستُصدر بطاقةً بصفر شهر."""
        product = self.new_product()

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 0,
             "manufacturer_months": 0, "supplier_months": 12},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("dealer_months", response.data)

    def test_serial_method_is_rejected_for_a_service_product(self):
        service = self.new_product(is_serialized=False, is_service=True, name_ar="خدمة تركيب")

        response = self.client.post(
            POLICIES,
            {"product": service.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("method", response.data)

    def test_invoice_method_is_allowed_for_a_service_product(self):
        service = self.new_product(is_serialized=False, is_service=True, name_ar="خدمة تركيب")

        response = self.client.post(
            POLICIES,
            {"product": service.pk, "method": "invoice", "dealer_months": 3},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)

    def test_manufacturer_months_above_zero_requires_a_warrantor(self):
        product = self.new_product()

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 0,
             "manufacturer_months": 12},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("manufacturer_months", response.data)

    def test_a_warrantor_without_months_is_rejected(self):
        product = self.new_product()

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 0,
             "manufacturer_warrantor": self.warrantor.pk, "manufacturer_months": 0},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("manufacturer_months", response.data)

    def test_manufacturer_layer_alone_is_a_valid_policy(self):
        product = self.new_product()

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 0,
             "manufacturer_warrantor": self.warrantor.pk, "manufacturer_months": 24},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)

    def test_terms_override_over_2000_chars_is_rejected(self):
        product = self.new_product()

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 12,
             "terms_override": "أ" * 2001},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("terms_override", response.data)


# ══════════════════════════════════════════════════════════════════════════
# CRUD والعزل
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicyCrudTest(WarrantyPolicyTestBase):
    def test_manager_creates_reads_and_edits_a_policy(self):
        product = self.new_product()

        created = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 12,
             "manufacturer_warrantor": self.warrantor.pk, "manufacturer_months": 24,
             "supplier_months": 6, "terms_override": "شروطٌ خاصة"},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["manufacturer_warrantor_name"], "جهة كفالة تجريبية")
        self.assertEqual(created.data["method_label"], "برقم تسلسلي")

        edited = self.client.patch(
            f"{POLICIES}{created.data['id']}/", {"dealer_months": 18}, format="json",
            **self.headers(),
        )
        self.assertEqual(edited.status_code, 200, edited.content)
        self.assertEqual(WarrantyPolicy.objects.get(pk=created.data["id"]).dealer_months, 18)

    def test_a_second_policy_for_the_same_brand_is_rejected(self):
        product = self.new_product()
        WarrantyPolicy.objects.create(
            tenant=self.tenant, product=product, method=WarrantyPolicy.METHOD_SERIAL,
            dealer_months=12,
        )

        response = self.client.post(
            POLICIES, {"product": product.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("product", response.data)

    def test_a_product_from_another_tenant_is_rejected_with_400(self):
        other = create_company("شركة كفالة أخرى ٢٣١", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_product = Product.objects.create(
            tenant=other, sku="FOREIGN-1", name_ar="منتج شركة أخرى", is_serialized=True,
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )

        response = self.client.post(
            POLICIES, {"product": foreign_product.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("product", response.data)

    def test_a_warrantor_from_another_tenant_is_rejected_with_400(self):
        other = create_company("شركة كفالة أخرى ٢٣١-ب", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_warrantor = ManufacturerWarrantor.objects.create(tenant=other, name="جهة أخرى")
        product = self.new_product()

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 0,
             "manufacturer_warrantor": foreign_warrantor.pk, "manufacturer_months": 12},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("manufacturer_warrantor", response.data)

    def test_a_policy_from_another_tenant_is_not_reachable(self):
        other = create_company("شركة كفالة أخرى ٢٣١-ج", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_product = Product.objects.create(
            tenant=other, sku="FOREIGN-2", name_ar="منتج", is_serialized=True,
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        foreign_policy = WarrantyPolicy.objects.create(
            tenant=other, product=foreign_product, method=WarrantyPolicy.METHOD_SERIAL,
            dealer_months=12,
        )

        response = self.client.get(f"{POLICIES}{foreign_policy.pk}/", **self.headers())

        self.assertEqual(response.status_code, 404, response.content)


# ══════════════════════════════════════════════════════════════════════════
# البوابة: require_module ثم require_perm
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicyGateTest(WarrantyPolicyTestBase):
    def test_404_without_a_module_license(self):
        self.license.delete()

        response = self.client.get(POLICIES, **self.headers())

        self.assertEqual(response.status_code, 404, response.content)

    def test_read_needs_the_warranty_view_permission(self):
        self.as_user(self.ess_user)

        response = self.client.get(POLICIES, **self.headers())

        self.assertEqual(response.status_code, 403, response.content)

    def test_a_sales_employee_can_read_but_not_write(self):
        product = self.new_product()
        self.as_user(self.sales_user)

        readable = self.client.get(POLICIES, **self.headers())
        self.assertEqual(readable.status_code, 200, readable.content)

        blocked = self.client.post(
            POLICIES, {"product": product.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )
        self.assertEqual(blocked.status_code, 403, blocked.content)

    def test_bulk_needs_settings_manage_not_just_warranty_manage(self):
        self.as_user(self.sales_user)

        response = self.client.post(
            BULK, {"family": 1, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 403, response.content)


# ══════════════════════════════════════════════════════════════════════════
# إنشاء البطاقة من السياسة
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicyCardCreationTest(WarrantyPolicyTestBase):
    def test_editing_the_policy_after_the_sale_freezes_the_issued_card(self):
        WarrantyPolicy.objects.filter(product=self.product).update(
            dealer_months=6, terms_override="الشروط الأصلية",
        )
        self.stock_units("SN-POL1")
        invoice = self.sales_invoice(serials=["SN-POL1"])
        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card = WarrantyCard.objects.get(tenant=self.tenant, serial="SN-POL1")
        self.assertEqual(card.duration_months, 6)
        self.assertEqual(card.terms_text, "الشروط الأصلية")

        response = self.client.patch(
            f"{POLICIES}{WarrantyPolicy.objects.get(product=self.product).pk}/",
            {"dealer_months": 99, "terms_override": "شروطٌ جديدة بعد البيع"},
            format="json", **self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)

        card.refresh_from_db()
        self.assertEqual(card.duration_months, 6)
        self.assertEqual(card.terms_text, "الشروط الأصلية")

    def test_default_company_terms_are_used_when_the_policy_has_no_override(self):
        from after_sales.services import get_or_create_after_sales_settings

        settings_row = get_or_create_after_sales_settings(self.tenant.pk)
        settings_row.default_terms = "شروط الشركة العامة"
        settings_row.save(update_fields=["default_terms"])
        WarrantyPolicy.objects.filter(product=self.product).update(terms_override="")

        self.stock_units("SN-POL2")
        invoice = self.sales_invoice(serials=["SN-POL2"])
        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card = WarrantyCard.objects.get(tenant=self.tenant, serial="SN-POL2")
        self.assertEqual(card.terms_text, "شروط الشركة العامة")


# ══════════════════════════════════════════════════════════════════════════
# bulk/ — صفٌّ لكل براند تحت منتجٍ أبٍ أو تصنيف
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicyBulkTest(WarrantyPolicyTestBase):
    def test_requires_exactly_one_of_family_or_category(self):
        response = self.client.post(
            BULK, {"method": "serial", "dealer_months": 6}, format="json", **self.headers(),
        )
        self.assertEqual(response.status_code, 400, response.content)

        category = ProductCategory.objects.create(tenant=self.tenant, name="فئة")
        both = self.client.post(
            BULK, {"family": 1, "category": category.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )
        self.assertEqual(both.status_code, 400, both.content)

    def test_bulk_writes_one_policy_row_per_brand_under_a_family(self):
        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="راوتر", brand="الأصلي", is_serialized=True,
        )
        second, _ = add_brand_to_family(family=family, brand_name="تي بي لينك", tenant=self.tenant)
        third, _ = add_brand_to_family(family=family, brand_name="نتغير", tenant=self.tenant)

        response = self.client.post(
            BULK,
            {"family": family.pk, "method": "serial", "dealer_months": 12,
             "supplier_months": 3},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["applied"], 3)
        for product in (first, second, third):
            policy = WarrantyPolicy.objects.get(product=product)
            self.assertEqual(policy.dealer_months, 12)
            self.assertEqual(policy.supplier_months, 3)

    def test_bulk_writes_one_policy_row_per_brand_under_a_category(self):
        category = ProductCategory.objects.create(tenant=self.tenant, name="طابعات")
        first = self.new_product(category=category, name_ar="طابعة أولى")
        second = self.new_product(category=category, name_ar="طابعة ثانية")

        response = self.client.post(
            BULK, {"category": category.pk, "method": "serial", "dealer_months": 9},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["applied"], 2)
        self.assertEqual(WarrantyPolicy.objects.get(product=first).dealer_months, 9)
        self.assertEqual(WarrantyPolicy.objects.get(product=second).dealer_months, 9)

    def test_bulk_upserts_an_existing_policy_instead_of_duplicating(self):
        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="سماعة", brand="الأصلي", is_serialized=True,
        )
        WarrantyPolicy.objects.create(
            tenant=self.tenant, product=first, method=WarrantyPolicy.METHOD_SERIAL,
            dealer_months=1,
        )

        response = self.client.post(
            BULK, {"family": family.pk, "method": "serial", "dealer_months": 20},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(WarrantyPolicy.objects.filter(product=first).count(), 1)
        self.assertEqual(WarrantyPolicy.objects.get(product=first).dealer_months, 20)

    def test_bulk_is_all_or_nothing_when_one_brand_fails_validation(self):
        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="جهاز مختلط", brand="سلعة", is_serialized=True,
        )
        service_sibling, _ = add_brand_to_family(
            family=family, brand_name="تركيب", tenant=self.tenant,
        )
        Product.objects.filter(pk=service_sibling.pk).update(is_service=True)

        response = self.client.post(
            BULK, {"family": family.pk, "method": "serial", "dealer_months": 12},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(WarrantyPolicy.objects.filter(product=first).exists())

    def test_bulk_selector_from_another_tenant_yields_400_not_leaked_rows(self):
        other = create_company("شركة كفالة أخرى ٢٣١-بالك", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign_family, _ = create_product_with_family(
            tenant=other, name_ar="منتج شركة أخرى", brand="أصلي", is_serialized=True,
        )

        response = self.client.post(
            BULK, {"family": foreign_family.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)


# ══════════════════════════════════════════════════════════════════════════
# الهجرة — دالّة التحويل النقية
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicyDataMigrationTest(WarrantyPolicyTestBase):
    def setUp(self):
        super().setUp()
        self.migration = import_module(
            "after_sales.migrations.0008_backfill_warranty_policies"
        )

    def _legacy(self, **overrides):
        base = dict(
            id=1, tenant_id=self.tenant.pk, is_serialized=True,
            warranty_months=12, supplier_warranty_months=24,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_serialized_product_maps_to_the_serial_method(self):
        kwargs = self.migration.policy_kwargs_from_legacy_product(self._legacy())

        self.assertEqual(kwargs["method"], "serial")
        self.assertEqual(kwargs["dealer_months"], 12)
        self.assertEqual(kwargs["supplier_months"], 24)
        self.assertIsNone(kwargs["manufacturer_warrantor"])
        self.assertEqual(kwargs["manufacturer_months"], 0)

    def test_non_serialized_product_maps_to_the_invoice_method(self):
        kwargs = self.migration.policy_kwargs_from_legacy_product(
            self._legacy(is_serialized=False)
        )

        self.assertEqual(kwargs["method"], "invoice")

    def test_a_missing_supplier_duration_becomes_zero_not_none(self):
        kwargs = self.migration.policy_kwargs_from_legacy_product(
            self._legacy(supplier_warranty_months=None)
        )

        self.assertEqual(kwargs["supplier_months"], 0)

    # ملاحظة: `backfill_policies` نفسها (لا الدالّة النقية) لا تُختبَر بـORM هنا
    # عمداً — عمودا `warranty_months`/`supplier_warranty_months` لم يعودا
    # موجودين على `inventory.Product` الحيّ في هذه الجلسة (حُذفا في هجرة #039
    # اللاحقة)، فلا مجال لإدخال حالةٍ «قبل الحذف» عبر ORM لنموذجٍ حاليّ — هذا
    # بالضبط سبب استخلاص `policy_kwargs_from_legacy_product` كدالّةٍ نقية
    # معزولة، وهي المُختبَرة أعلاه بكائنٍ يحاكي الشكل القديم.


# ══════════════════════════════════════════════════════════════════════════
# #233 — فرض الرقم التسلسلي: سياسة `serial` تفرض على المنتج المكفول ما لا
# يفرضه نمط الشركة، والترقيم عند البيع يفتح مخزوناً قديماً بلا نسخٍ لمنطق
# `register_existing_serials`.
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicySerialEnforcementTest(WarrantyPolicyTestBase):
    """`self.product` من `WarrantyTestBase.setUp` يحمل سياسة `serial` جاهزة."""

    def _stock_without_serials(self, qty, product=None):
        record_stock_movement(
            product=product or self.product, movement_type="IN", quantity=Decimal(qty),
            unit_cost=Decimal("1000"), reference_type="OPENING", reference_id=0,
            movement_date="2026-06-01", tenant=self.tenant,
        )

    def _purchase_invoice(self, *, serials=None, qty="2", product=None):
        product = product or self.product
        grand = Decimal(qty) * Decimal("1000")
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"P-233-{PurchaseInvoice.objects.count() + 1:04d}",
            partner=self.supplier, currency=self.ils, invoice_date=PURCHASE_DATE,
            exchange_rate=Decimal("1"), grand_total=grand,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=product, name=product.name_ar,
            quantity=Decimal(qty), unit_price=Decimal("1000"), total_price=grand,
            serials=list(serials or []),
        )
        return invoice

    def _post_purchase(self, invoice):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers(),
        )

    # ── البيع: الفرض يعلو نمط الشركة ──────────────────────────────────
    def test_forced_product_requires_a_serial_even_when_company_mode_is_off(self):
        ss = get_or_create_sales_settings(self.tenant)
        ss.serial_entry_mode = SERIAL_MODE_OFF
        ss.save(update_fields=["serial_entry_mode"])
        self.stock_units("F-233-1")

        invoice = self.sales_invoice(qty="1")  # بلا رقم مختار
        response = self.post_sale(invoice)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("إجباري", response.data["error"])

    def test_forced_product_posts_once_the_serial_is_declared_under_off_mode(self):
        ss = get_or_create_sales_settings(self.tenant)
        ss.serial_entry_mode = SERIAL_MODE_OFF
        ss.save(update_fields=["serial_entry_mode"])
        self.stock_units("F-233-2")

        invoice = self.sales_invoice(qty="1", serials=["F-233-2"])
        response = self.post_sale(invoice)

        self.assertEqual(response.status_code, 200, response.content)
        unit = ProductSerial.objects.get(tenant=self.tenant, serial="F-233-2")
        self.assertEqual(unit.status, ProductSerial.STATUS_SOLD)

    # ── الترقيم عند البيع ──────────────────────────────────────────────
    def test_new_serial_within_unnumbered_balance_is_registered_and_consumed(self):
        self._stock_without_serials("3")

        invoice = self.sales_invoice(qty="1", serials=["NEW-233-1"])
        response = self.post_sale(invoice)

        self.assertEqual(response.status_code, 200, response.content)
        unit = ProductSerial.objects.get(tenant=self.tenant, serial="NEW-233-1")
        self.assertEqual(unit.status, ProductSerial.STATUS_SOLD)

    def test_new_serials_beyond_the_unnumbered_balance_are_rejected(self):
        self._stock_without_serials("1")

        invoice = self.sales_invoice(qty="2", serials=["NEW-233-2", "NEW-233-3"])
        response = self.post_sale(invoice)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("رصيد", response.data["error"])
        self.assertFalse(
            ProductSerial.objects.filter(
                tenant=self.tenant, serial__in=["NEW-233-2", "NEW-233-3"],
            ).exists()
        )

    def test_new_serial_at_the_unnumbered_balance_boundary_is_accepted(self):
        """#233-r1: الحدّ الفاصل — رصيدٌ = 1 تُباع منه وحدةٌ واحدة برقمٍ جديد.
        رصيد ما **قبل** حركة هذا البيع = 1 (يُقبل)؛ لو قُرئ الرصيد **بعد**
        حركة الصرف لصار صفراً فرُفض خطأً — هذا ما يميّز الاختبارين أعلاه
        (3 تُباع 1، و1 تُباع 2) عن هذه الحالة."""
        self._stock_without_serials("1")

        invoice = self.sales_invoice(qty="1", serials=["BOUND-233-1"])
        response = self.post_sale(invoice)

        self.assertEqual(response.status_code, 200, response.content)
        unit = ProductSerial.objects.get(tenant=self.tenant, serial="BOUND-233-1")
        self.assertEqual(unit.status, ProductSerial.STATUS_SOLD)

    # ── الشراء: الفرض لا يرفع النمط إلى «إجباري» ────────────────────────
    def test_purchase_is_not_forced_to_required_unless_company_mode_is_required(self):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.serial_entry_mode = SERIAL_MODE_OFF
        ps.save(update_fields=["serial_entry_mode"])

        invoice = self._purchase_invoice(qty="2")  # بلا أرقام
        response = self._post_purchase(invoice)

        self.assertEqual(response.status_code, 201, response.content)

    def test_purchase_is_forced_to_required_when_company_mode_is_required(self):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.serial_entry_mode = SERIAL_MODE_REQUIRED
        ps.save(update_fields=["serial_entry_mode"])

        invoice = self._purchase_invoice(qty="2")  # بلا أرقام
        response = self._post_purchase(invoice)

        self.assertEqual(response.status_code, 400, response.content)

    # ── إلغاء التتبّع مرفوضٌ ما دامت السياسة قائمة ──────────────────────
    def test_untracking_a_product_is_refused_while_a_serial_policy_exists(self):
        response = self.client.patch(
            f"/api/inventory/products/{self.product.pk}/",
            {"is_serialized": False}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("is_serialized", response.data)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_serialized)

    def test_untracking_a_sibling_is_refused_when_it_would_untrack_a_forced_brand(self):
        """#233-r1: `is_serialized` حقلٌ أبويّ — إطفاؤه على براندٍ بلا سياسة
        (B) يُنزَل على كل إخوته بعد الحفظ (`sync_family_from_product` ←
        `_push_family_fields_to_siblings`)، فيُطفئ تتبّع أخيه المفروض (A) دون
        أن يمرّ الطلب من حارس A مطلقاً — الحارس يجب أن يفحص العائلة كلها."""
        family, brand_a = create_product_with_family(
            tenant=self.tenant, name_ar="سماعة ٢٣٣-شقيق", brand="أ", is_serialized=True,
        )
        brand_b, _ = add_brand_to_family(family=family, brand_name="ب", tenant=self.tenant)
        self.make_policy(brand_a, dealer_months=6)
        brand_b.refresh_from_db()
        self.assertTrue(brand_b.is_serialized)  # ورث الحالة من الأب عند الإنشاء

        response = self.client.patch(
            f"/api/inventory/products/{brand_b.pk}/",
            {"is_serialized": False}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("is_serialized", response.data)
        brand_a.refresh_from_db()
        self.assertTrue(brand_a.is_serialized)
        brand_b.refresh_from_db()
        self.assertTrue(brand_b.is_serialized)

    # ── الوحدة مُطفأة: نمط الشركة وحده يحكم ─────────────────────────────
    def test_disabled_module_lets_the_company_mode_govern_despite_a_policy(self):
        self.license.delete()
        from core.modules import invalidate_module_cache

        invalidate_module_cache(self.tenant.pk)
        ss = get_or_create_sales_settings(self.tenant)
        ss.serial_entry_mode = SERIAL_MODE_OFF
        ss.save(update_fields=["serial_entry_mode"])
        self._stock_without_serials("1")

        invoice = self.sales_invoice(qty="1")  # بلا رقم — ولا فرض، فالوحدة مطفأة
        response = self.post_sale(invoice)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ProductSerial.objects.filter(tenant=self.tenant).count(), 0)


# ══════════════════════════════════════════════════════════════════════════
# #233 — حفظ سياسة `serial` يرفع `is_serialized` على البراند (والإخوة)
# ══════════════════════════════════════════════════════════════════════════

class WarrantyPolicySerialTrackingSyncTest(WarrantyPolicyTestBase):
    def test_creating_a_serial_policy_raises_is_serialized_on_an_untracked_brand(self):
        product = self.new_product(is_serialized=False)

        response = self.client.post(
            POLICIES,
            {"product": product.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)
        product.refresh_from_db()
        self.assertTrue(product.is_serialized)

    def test_creating_a_serial_policy_raises_is_serialized_on_sibling_brands(self):
        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="سماعة ٢٣٣", brand="الأصلي", is_serialized=False,
        )
        second, _ = add_brand_to_family(family=family, brand_name="آخر", tenant=self.tenant)
        Product.objects.filter(pk__in=[first.pk, second.pk]).update(is_serialized=False)

        response = self.client.post(
            POLICIES,
            {"product": first.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)
        second.refresh_from_db()
        self.assertTrue(second.is_serialized)

    def test_updating_a_policy_to_serial_raises_is_serialized(self):
        product = self.new_product(is_serialized=False)
        policy = WarrantyPolicy.objects.create(
            tenant=self.tenant, product=product, method=WarrantyPolicy.METHOD_INVOICE,
            dealer_months=6,
        )

        response = self.client.patch(
            f"{POLICIES}{policy.pk}/", {"method": "serial"}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        product.refresh_from_db()
        self.assertTrue(product.is_serialized)

    def test_bulk_apply_of_a_serial_policy_raises_is_serialized_on_every_brand(self):
        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="راوتر ٢٣٣", brand="الأصلي", is_serialized=False,
        )
        second, _ = add_brand_to_family(family=family, brand_name="ثانٍ", tenant=self.tenant)
        Product.objects.filter(pk__in=[first.pk, second.pk]).update(is_serialized=False)

        response = self.client.post(
            BULK, {"family": family.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        for product in (first, second):
            product.refresh_from_db()
            self.assertTrue(product.is_serialized)

    def test_deleting_a_serial_policy_does_not_lower_is_serialized(self):
        product = self.new_product(is_serialized=False)
        created = self.client.post(
            POLICIES, {"product": product.pk, "method": "serial", "dealer_months": 6},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        product.refresh_from_db()
        self.assertTrue(product.is_serialized)

        deleted = self.client.delete(f"{POLICIES}{created.data['id']}/", **self.headers())
        self.assertEqual(deleted.status_code, 204, deleted.content)
        self.assertFalse(WarrantyPolicy.objects.filter(product=product).exists())
        product.refresh_from_db()
        self.assertTrue(product.is_serialized)


# ══════════════════════════════════════════════════════════════════════════
# #233 — معاينة serial-impact: البراندات الشقيقة غير المتتبَّعة وعدد وحدات
# كل منتج غير المرقَّمة الآن (قصّتا المالك 6 و7)
# ══════════════════════════════════════════════════════════════════════════

class WarrantySerialImpactTest(WarrantyPolicyTestBase):
    def test_impact_lists_untracked_siblings_and_the_unnumbered_balance(self):
        family, first = create_product_with_family(
            tenant=self.tenant, name_ar="طابعة ٢٣٣", brand="الأصلي", is_serialized=False,
        )
        second, _ = add_brand_to_family(family=family, brand_name="ثانٍ", tenant=self.tenant)
        already_tracked, _ = add_brand_to_family(
            family=family, brand_name="مرقَّم مسبقاً", tenant=self.tenant,
        )
        Product.objects.filter(pk__in=[first.pk, second.pk]).update(is_serialized=False)
        Product.objects.filter(pk=already_tracked.pk).update(is_serialized=True)
        record_stock_movement(
            product=first, movement_type="IN", quantity=Decimal("4"),
            unit_cost=Decimal("100"), reference_type="OPENING", reference_id=0,
            movement_date="2026-06-01", tenant=self.tenant,
        )

        response = self.client.get(SERIAL_IMPACT, {"product": first.pk}, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        sibling_ids = {row["id"] for row in response.data["sibling_brands"]}
        self.assertEqual(sibling_ids, {second.pk})
        self.assertEqual(response.data["unnumbered_units"][first.pk], 4)

    def test_impact_requires_a_selector(self):
        response = self.client.get(SERIAL_IMPACT, **self.headers())

        self.assertEqual(response.status_code, 400, response.content)

    def test_impact_needs_settings_manage_not_just_warranty_view(self):
        product = self.new_product()
        self.as_user(self.sales_user)

        response = self.client.get(SERIAL_IMPACT, {"product": product.pk}, **self.headers())

        self.assertEqual(response.status_code, 403, response.content)
