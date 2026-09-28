"""#235 — كفالة المصنع من سطر الشراء.

يثبت (كله عبر الـAPI):
  1. بيعٌ يستهلك وحداتٍ من دفعتَي شراء بكفالتين مختلفتين ⇒ بطاقتان بطبقتَي
     مصنعٍ مختلفتين (وطبقة المورّد من السطر إن وُجدت، وإلا من السياسة).
  2. التحقّق (جهةٌ مؤرشفة · مدةٌ بلا جهة · جهةٌ بلا مدة · مدة > 600) ⇒ 400
     باسم السطر، ولا فاتورة تُحفظ (ذرّية).
  3. الوحدة مطفأة ⇒ الحمولة تُهمَل ولا تُقرأ، و`PATCH` ⇒ 404.
  4. تصحيح فاتورةٍ مرحَّلة بـ`PATCH` لا يمسّ بطاقةً صدرت؛ والمسودّة 400؛
     وغير المدير 403.
  5. الأولوية: بطاقةٌ سابقة للوحدة > سطر الشراء > السياسة.
  6. عزل الشركات على النقطة.
  7. `lookup/` مقروءةٌ لمحرّر فاتورة الشراء (اختبارها في
     `test_manufacturer_warrantors_and_settings.py`).
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User

from after_sales.models import (
    ManufacturerWarrantor, PurchaseLineWarranty, WarrantyPolicy,
)
from core.models import TenantModule
from logistics.models import PurchaseInvoice
from tenants.models import MemberPermission, UserCompanyMembership
from tenants.services import create_company

from .test_warranty import PURCHASE_DATE
from .test_warranty_lifecycle import WarrantyReturnTestBase
from .test_warranty_policies import WarrantyPolicyTestBase

PURCHASES = "/api/logistics/purchase-invoices/"
PATCH_URL = "/api/after-sales/purchase-line-warranties/"
EXT = "manufacturer_warranty"


class PurchaseLineWarrantyBase(WarrantyPolicyTestBase):
    sales_return = WarrantyReturnTestBase.sales_return

    def setUp(self):
        super().setUp()
        self.warrantor_b = ManufacturerWarrantor.objects.create(
            tenant=self.tenant, name="جهة كفالة ثانية",
        )
        self.procurement_user = User.objects.create_user(username="procurement-235", password="x")
        UserCompanyMembership.objects.create(
            user=self.procurement_user, tenant=self.tenant, role="procurement",
        )

    def line(self, serials, *, product=None, ext=None):
        product = product or self.product
        item = {
            "product": product.pk,
            "name": product.name_ar,
            "quantity": str(len(serials)),
            "unit_price": "1000",
            "total_price": str(1000 * len(serials)),
            "serials": list(serials),
        }
        if ext is not None:
            item["extensions"] = {EXT: ext}
        return item

    def purchase_payload(self, lines):
        total = sum(Decimal(item["total_price"]) for item in lines)
        return {
            "partner": self.supplier.pk,
            "invoice_date": PURCHASE_DATE,
            "currency": self.ils.Code,
            "exchange_rate": "1",
            "subtotal": str(total),
            "grand_total": str(total),
            "items": lines,
        }

    def create_purchase(self, lines):
        return self.client.post(
            PURCHASES, self.purchase_payload(lines), format="json", **self.headers(),
        )

    def create_posted(self, lines):
        response = self.create_purchase(lines)
        self.assertEqual(response.status_code, 201, response.content)
        posted = self.client.post(
            f"{PURCHASES}{response.data['id']}/post-to-accounting/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(posted.status_code, 201, posted.content)
        return response.data

    def detail(self, invoice_id):
        return self.client.get(f"{PURCHASES}{invoice_id}/", **self.headers())

    def patch_lines(self, invoice_id, lines):
        return self.client.patch(
            PATCH_URL, {"invoice": invoice_id, "lines": lines},
            format="json", **self.headers(),
        )

    def ext(self, warrantor=None, months=0, supplier=None):
        return {
            "manufacturer_warrantor": warrantor.pk if warrantor else None,
            "manufacturer_months": months,
            "supplier_months": supplier,
        }


class PurchaseLineLayersAtSaleTest(PurchaseLineWarrantyBase):
    def test_a_sale_from_two_batches_gets_two_different_manufacturer_layers(self):
        first = self.create_posted([
            self.line(["SN-A1"], ext=self.ext(self.warrantor, 24, supplier=6)),
        ])
        second = self.create_posted([
            self.line(["SN-B1"], ext=self.ext(self.warrantor_b, 36, supplier=None)),
        ])
        self.assertEqual(
            self.detail(first["id"]).data["items"][0]["extensions"][EXT]["manufacturer_months"], 24,
        )

        sale = self.sales_invoice(serials=["SN-A1", "SN-B1"], qty="2")
        self.assertEqual(self.post_sale(sale).status_code, 200)

        card_a = self.cards(serial="SN-A1").get()
        card_b = self.cards(serial="SN-B1").get()
        self.assertEqual(card_a.manufacturer_warrantor_id, self.warrantor.pk)
        self.assertEqual(card_a.manufacturer_duration_months, 24)
        self.assertEqual(card_a.manufacturer_end_date, date(2028, 6, 15))
        self.assertEqual(card_b.manufacturer_warrantor_id, self.warrantor_b.pk)
        self.assertEqual(card_b.manufacturer_duration_months, 36)
        self.assertEqual(card_b.manufacturer_end_date, date(2029, 6, 15))
        # المورّد: السطر الأول يحدّد ٦ أشهر من تاريخ الشراء، والثاني بلا قيمة
        # فيأخذ ٢٤ من السياسة.
        self.assertEqual(card_a.supplier_warranty_end_date, date(2026, 12, 11))
        self.assertEqual(card_b.supplier_warranty_end_date, date(2028, 6, 11))
        self.assertEqual(second["items"][0]["product"], self.product.pk)

    def test_a_line_with_no_warrantor_overrides_a_policy_that_has_one(self):
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=self.warrantor, manufacturer_months=12,
        )
        self.create_posted([self.line(["SN-N1"], ext=self.ext(None, 0))])
        self.create_posted([self.line(["SN-N2"])])  # بلا صفّ ⇒ السياسة

        sale = self.sales_invoice(serials=["SN-N1", "SN-N2"], qty="2")
        self.assertEqual(self.post_sale(sale).status_code, 200)

        self.assertIsNone(self.cards(serial="SN-N1").get().manufacturer_warrantor_id)
        card_policy = self.cards(serial="SN-N2").get()
        self.assertEqual(card_policy.manufacturer_warrantor_id, self.warrantor.pk)
        self.assertEqual(card_policy.manufacturer_duration_months, 12)

    def test_priority_is_previous_card_then_purchase_line_then_policy(self):
        WarrantyPolicy.objects.filter(product=self.product).update(
            manufacturer_warrantor=self.warrantor_b, manufacturer_months=6,
        )
        invoice = self.create_posted([
            self.line(["SN-P1"], ext=self.ext(self.warrantor, 24)),
        ])
        sale = self.sales_invoice(serials=["SN-P1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        first = self.cards(serial="SN-P1").get()
        self.assertEqual(first.manufacturer_warrantor_id, self.warrantor.pk)  # السطر > السياسة

        # تصحيح السطر بعد البيع، ثم إعادة بيع الوحدة: البطاقة السابقة تغلب السطر.
        item_id = invoice["items"][0]["id"]
        patched = self.patch_lines(invoice["id"], [
            {"item": item_id, **self.ext(self.warrantor_b, 36)},
        ])
        self.assertEqual(patched.status_code, 200, patched.content)
        return_invoice = self.sales_return(sale, serials=["SN-P1"])
        self.assertEqual(self.post_sale(return_invoice).status_code, 200)

        from partners.models import Partner
        from sales.models import SalesInvoice, SalesInvoiceLine

        buyer = Partner.objects.create(
            tenant=self.tenant, name="مشترٍ ثانٍ", partner_type="Customer",
            linked_account=self.ar,
        )
        resale = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="S-PRIO-1", customer=buyer,
            currency=self.ils, invoice_date="2026-08-01",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=resale, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=["SN-P1"],
        )
        self.assertEqual(self.warrantor_b.pk, WarrantyPolicy.objects.get(product=self.product).manufacturer_warrantor_id)
        self.assertEqual(self.post_sale(resale).status_code, 200)

        second = self.cards(serial="SN-P1").order_by("id").last()
        self.assertNotEqual(second.pk, first.pk)
        self.assertEqual(second.manufacturer_warrantor_id, self.warrantor.pk)
        self.assertEqual(second.manufacturer_duration_months, 24)
        self.assertEqual(second.manufacturer_start_date, first.manufacturer_start_date)


class PurchaseLineValidationTest(PurchaseLineWarrantyBase):
    def assert_rejected(self, ext, fragment="السطر 1"):
        before = PurchaseInvoice.objects.filter(tenant=self.tenant).count()
        response = self.create_purchase([self.line(["SN-V1"], ext=ext)])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(fragment, str(response.data))
        # ذرّية: لا فاتورة ولا صفّ كفالة بقي.
        self.assertEqual(PurchaseInvoice.objects.filter(tenant=self.tenant).count(), before)
        self.assertEqual(PurchaseLineWarranty.objects.filter(tenant=self.tenant).count(), 0)

    def test_an_archived_warrantor_is_refused_naming_the_line(self):
        ManufacturerWarrantor.objects.filter(pk=self.warrantor.pk).update(is_active=False)
        self.assert_rejected(self.ext(self.warrantor, 12))

    def test_months_without_a_warrantor_are_refused(self):
        self.assert_rejected(self.ext(None, 12))

    def test_a_warrantor_without_months_is_refused(self):
        self.assert_rejected(self.ext(self.warrantor, 0))

    def test_months_above_600_are_refused(self):
        self.assert_rejected(self.ext(self.warrantor, 601))

    def test_a_warrantor_of_another_company_is_refused(self):
        other = create_company("شركة أخرى", self.user)
        foreign = ManufacturerWarrantor.objects.create(tenant=other, name="جهة غريبة")
        self.assert_rejected(self.ext(foreign, 12))

    def test_a_bad_second_line_rolls_back_the_valid_first_one(self):
        response = self.create_purchase([
            self.line(["SN-R1"], ext=self.ext(self.warrantor, 12)),
            self.line(["SN-R2"], ext=self.ext(None, 12)),
        ])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("السطر 2", str(response.data))
        self.assertFalse(PurchaseInvoice.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(PurchaseLineWarranty.objects.filter(tenant=self.tenant).exists())

    def test_a_draft_edit_can_change_the_line_and_a_bad_edit_leaves_it_untouched(self):
        created = self.create_purchase([
            self.line(["SN-E1"], ext=self.ext(self.warrantor, 12)),
        ])
        self.assertEqual(created.status_code, 201, created.content)
        item = created.data["items"][0]
        body = self.purchase_payload([{**self.line(["SN-E1"]), "id": item["id"]}])
        body["items"][0]["extensions"] = {EXT: self.ext(self.warrantor_b, 30)}
        ok = self.client.put(f"{PURCHASES}{created.data['id']}/", body, format="json", **self.headers())
        self.assertEqual(ok.status_code, 200, ok.content)
        row = PurchaseLineWarranty.objects.get(purchase_item_id=item["id"])
        self.assertEqual((row.manufacturer_warrantor_id, row.manufacturer_months), (self.warrantor_b.pk, 30))

        body["items"][0]["extensions"] = {EXT: self.ext(None, 5)}
        bad = self.client.put(f"{PURCHASES}{created.data['id']}/", body, format="json", **self.headers())
        self.assertEqual(bad.status_code, 400, bad.content)
        row.refresh_from_db()
        self.assertEqual((row.manufacturer_warrantor_id, row.manufacturer_months), (self.warrantor_b.pk, 30))


class PurchaseLineModuleGateTest(PurchaseLineWarrantyBase):
    def test_with_the_module_off_the_payload_is_ignored_and_the_endpoint_is_404(self):
        on = self.create_posted([
            self.line(["SN-O0"], ext=self.ext(self.warrantor, 24)),
        ])
        on_item = on["items"][0]["id"]
        self.assertEqual(PurchaseLineWarranty.objects.get(purchase_item_id=on_item).manufacturer_months, 24)

        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(enabled=False)

        created = self.create_purchase([
            self.line(["SN-O1"], ext=self.ext(self.warrantor, 24)),
        ])
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(PurchaseLineWarranty.objects.filter(tenant=self.tenant).count(), 1)
        item = self.detail(created.data["id"]).data["items"][0]
        self.assertNotIn(EXT, item.get("extensions") or {})

        response = self.patch_lines(on["id"], [
            {"item": on_item, **self.ext(self.warrantor, 12)},
        ])
        self.assertEqual(response.status_code, 404)
        self.assertEqual(PurchaseLineWarranty.objects.get(purchase_item_id=on_item).manufacturer_months, 24)

    def test_the_module_off_hides_rows_written_while_it_was_on(self):
        created = self.create_purchase([
            self.line(["SN-O2"], ext=self.ext(self.warrantor, 24)),
        ])
        self.assertEqual(created.status_code, 201, created.content)
        shown = self.detail(created.data["id"]).data["items"][0]
        self.assertEqual(shown["extensions"][EXT]["manufacturer_months"], 24)
        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(enabled=False)
        item = self.detail(created.data["id"]).data["items"][0]
        self.assertNotIn(EXT, item.get("extensions") or {})


class PurchaseLineCorrectionTest(PurchaseLineWarrantyBase):
    def test_patching_a_posted_invoice_updates_the_row_but_not_issued_cards(self):
        invoice = self.create_posted([
            self.line(["SN-C1"], ext=self.ext(self.warrantor, 24, supplier=6)),
        ])
        sale = self.sales_invoice(serials=["SN-C1"])
        self.assertEqual(self.post_sale(sale).status_code, 200)
        card = self.cards().get()
        snapshot = (
            card.manufacturer_warrantor_id, card.manufacturer_duration_months,
            card.manufacturer_end_date, card.supplier_warranty_end_date,
        )

        item_id = invoice["items"][0]["id"]
        response = self.patch_lines(invoice["id"], [
            {"item": item_id, **self.ext(self.warrantor_b, 60, supplier=12)},
        ])

        self.assertEqual(response.status_code, 200, response.content)
        row = PurchaseLineWarranty.objects.get(purchase_item_id=item_id)
        self.assertEqual((row.manufacturer_warrantor_id, row.manufacturer_months, row.supplier_months),
                         (self.warrantor_b.pk, 60, 12))
        self.assertEqual(row.updated_by_id, self.user.pk)
        card.refresh_from_db()
        self.assertEqual(snapshot, (
            card.manufacturer_warrantor_id, card.manufacturer_duration_months,
            card.manufacturer_end_date, card.supplier_warranty_end_date,
        ))

    def test_patching_a_draft_is_refused_and_writes_nothing(self):
        created = self.create_purchase([self.line(["SN-D1"], ext=self.ext(self.warrantor, 12))])
        self.assertEqual(created.status_code, 201, created.content)
        item_id = created.data["items"][0]["id"]

        response = self.patch_lines(created.data["id"], [
            {"item": item_id, **self.ext(self.warrantor_b, 60)},
        ])

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PurchaseLineWarranty.objects.get(purchase_item_id=item_id).manufacturer_months, 12)

    def test_an_invalid_batch_is_all_or_nothing(self):
        invoice = self.create_posted([
            self.line(["SN-AB1"], ext=self.ext(self.warrantor, 12)),
            self.line(["SN-AB2"], ext=self.ext(self.warrantor, 12)),
        ])
        first, second = (item["id"] for item in invoice["items"])

        response = self.patch_lines(invoice["id"], [
            {"item": first, **self.ext(self.warrantor_b, 48)},
            {"item": second, **self.ext(None, 5)},
        ])

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PurchaseLineWarranty.objects.get(purchase_item_id=first).manufacturer_months, 12)

    def test_an_item_of_another_invoice_is_refused(self):
        one = self.create_posted([self.line(["SN-X1"], ext=self.ext(self.warrantor, 12))])
        two = self.create_posted([self.line(["SN-X2"], ext=self.ext(self.warrantor, 12))])

        response = self.patch_lines(one["id"], [
            {"item": two["items"][0]["id"], **self.ext(self.warrantor_b, 48)},
        ])

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            PurchaseLineWarranty.objects.get(purchase_item_id=two["items"][0]["id"]).manufacturer_months, 12,
        )

    def test_a_user_without_warranty_manage_gets_403(self):
        invoice = self.create_posted([self.line(["SN-F1"], ext=self.ext(self.warrantor, 12))])

        response = self.as_user(self.procurement_user).patch_lines(invoice["id"], [
            {"item": invoice["items"][0]["id"], **self.ext(self.warrantor_b, 48)},
        ])

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            PurchaseLineWarranty.objects.get(purchase_item_id=invoice["items"][0]["id"]).manufacturer_months, 12,
        )


class PurchaseLineTenantIsolationTest(PurchaseLineWarrantyBase):
    def test_a_foreign_companys_invoice_is_404_and_its_rows_stay_untouched(self):
        invoice = self.create_posted([self.line(["SN-T1"], ext=self.ext(self.warrantor, 12))])
        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)

        response = self.client.patch(
            PATCH_URL,
            {"invoice": invoice["id"], "lines": [
                {"item": invoice["items"][0]["id"], **self.ext(None, 0)},
            ]},
            format="json", **self.headers(other),
        )

        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(
            PurchaseLineWarranty.objects.get(purchase_item_id=invoice["items"][0]["id"]).manufacturer_months, 12,
        )
        foreign_read = self.client.get(f"{PURCHASES}{invoice['id']}/", **self.headers(other))
        self.assertEqual(foreign_read.status_code, 404)


class LastPurchaseHintTest(PurchaseLineWarrantyBase):
    """«آخر شراء» على شاشة السياسات: أحدث سطرٍ مرحَّل لكل منتج، باستعلامٍ واحد."""

    POLICIES = "/api/after-sales/warranty-policies/"

    def policy_rows(self, **params):
        response = self.client.get(self.POLICIES, params, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        data = response.data
        return data["results"] if isinstance(data, dict) else data

    def hint_for(self, product):
        rows = [row for row in self.policy_rows() if row["product"] == product.pk]
        self.assertEqual(len(rows), 1)
        return rows[0]["last_purchase"]

    def test_the_hint_is_the_latest_posted_line_of_the_product(self):
        self.assertIsNone(self.hint_for(self.product))
        self.create_posted([self.line(["SN-L1"], ext=self.ext(self.warrantor, 12, supplier=3))])
        newer = self.create_posted([
            self.line(["SN-L2"], ext=self.ext(self.warrantor_b, 30, supplier=9)),
        ])

        hint = self.hint_for(self.product)

        self.assertEqual(hint["manufacturer_warrantor"], self.warrantor_b.pk)
        self.assertEqual(hint["manufacturer_warrantor_name"], self.warrantor_b.name)
        self.assertEqual(hint["manufacturer_months"], 30)
        self.assertEqual(hint["supplier_months"], 9)
        self.assertEqual(hint["invoice_number"], newer["invoice_number"])
        self.assertEqual(str(hint["invoice_date"]), PURCHASE_DATE)

    def test_a_draft_invoice_is_not_a_purchase_yet(self):
        self.create_posted([self.line(["SN-D1"], ext=self.ext(self.warrantor, 12))])
        draft = self.create_purchase([
            self.line(["SN-D2"], ext=self.ext(self.warrantor_b, 60)),
        ])
        self.assertEqual(draft.status_code, 201, draft.content)

        self.assertEqual(self.hint_for(self.product)["manufacturer_months"], 12)

    def test_a_line_without_a_row_gives_no_hint(self):
        self.create_posted([self.line(["SN-R1"])])

        self.assertIsNone(self.hint_for(self.product))

    def test_the_list_costs_the_same_queries_for_one_product_or_many(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        WarrantyPolicy.objects.exclude(product=self.product).delete()
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(len(self.policy_rows()), 1)

        for index in range(4):
            product = self.new_product()
            WarrantyPolicy.objects.create(
                tenant=self.tenant, product=product, method="serial", dealer_months=6,
            )
            self.create_posted([
                self.line([f"SN-Q{index}"], product=product, ext=self.ext(self.warrantor, 12 + index)),
            ])
        with CaptureQueriesContext(connection) as many:
            rows = self.policy_rows()
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(1 for row in rows if row["last_purchase"]), 4)

        self.assertEqual(len(many), len(one))

    def test_another_companys_purchase_never_shows_as_the_hint(self):
        from after_sales.services import latest_purchase_line_warranties

        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        self.create_posted([self.line(["SN-F1"], ext=self.ext(self.warrantor, 12))])

        response = self.client.get(self.POLICIES, **self.headers(other))

        self.assertEqual(response.status_code, 200, response.content)
        data = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(data, [])
        self.assertEqual(latest_purchase_line_warranties(other.pk, [self.product.pk]), {})
        self.assertIn(
            self.product.pk, latest_purchase_line_warranties(self.tenant.pk, [self.product.pk]),
        )


class PolicyBatchForPurchaseLinesTest(PurchaseLineWarrantyBase):
    """قراءة سياسات منتجات الفاتورة دفعةً واحدة لمحرّر فاتورة الشراء (#235)."""

    BATCH = "/api/after-sales/warranty-policies/for-products/"

    def setUp(self):
        super().setUp()
        self.second = self.new_product()
        WarrantyPolicy.objects.create(
            tenant=self.tenant, product=self.second, method="serial", dealer_months=6,
        )
        # مشتريات بصلاحية تحرير الفاتورة وحدها: دور المشتريات يملك القراءة افتراضياً،
        # فيُسحب منه `aftersales.warranty.view` بتجاوز عضو ليبقى المفتاح الواحد.
        self.clerk = User.objects.create_user(username="clerk-235", password="x")
        membership = UserCompanyMembership.objects.create(
            user=self.clerk, tenant=self.tenant, role="procurement",
        )
        MemberPermission.objects.create(
            membership=membership, permission_key="aftersales.warranty.view", allowed=False,
        )

    def batch(self, *products, tenant=None):
        ids = ",".join(str(product.pk) for product in products)
        return self.client.get(self.BATCH, {"products": ids}, **self.headers(tenant))

    def test_a_clerk_with_only_purchase_invoice_edit_reads_the_methods_in_one_call(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.as_user(self.clerk)

        with CaptureQueriesContext(connection) as queries:
            response = self.batch(self.product, self.second)

        self.assertEqual(response.status_code, 200, response.content)
        by_product = {row["product"]: row for row in response.data}
        self.assertEqual(set(by_product), {self.product.pk, self.second.pk})
        self.assertEqual(by_product[self.second.pk]["method"], "serial")
        self.assertNotIn("last_purchase", by_product[self.second.pk])
        self.assertLess(len(queries), 12)

    def test_the_clerk_cannot_read_the_full_policy_list(self):
        self.as_user(self.clerk)

        response = self.client.get(
            "/api/after-sales/warranty-policies/", **self.headers(),
        )

        self.assertEqual(response.status_code, 403, response.content)

    def test_the_warranty_view_permission_reads_it_too(self):
        self.as_user(self.sales_user)

        self.assertEqual(self.batch(self.product).status_code, 200)

    def test_a_user_with_neither_permission_gets_403(self):
        self.as_user(self.ess_user)

        self.assertEqual(self.batch(self.product).status_code, 403)

    def test_with_the_module_off_it_is_404_even_for_the_clerk(self):
        self.as_user(self.clerk)
        TenantModule.objects.filter(tenant=self.tenant, module_key="after_sales").update(enabled=False)

        self.assertEqual(self.batch(self.product).status_code, 404)

    def test_a_foreign_companys_product_is_not_returned(self):
        from inventory.models import Product

        other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(tenant=other, module_key="after_sales", enabled=True)
        foreign = Product.objects.create(
            tenant=other, sku="FOREIGN-1", name_ar="منتج غريب", is_serialized=True,
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        WarrantyPolicy.objects.create(
            tenant=other, product=foreign, method="serial", dealer_months=6,
        )

        response = self.batch(self.product, foreign)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({row["product"] for row in response.data}, {self.product.pk})
        from_other = self.batch(self.product, tenant=other)
        self.assertEqual({row["product"] for row in from_other.data}, set())

    def test_a_non_numeric_id_is_ignored_and_none_gives_an_empty_list(self):
        response = self.client.get(self.BATCH, {"products": "abc,,"}, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data, [])