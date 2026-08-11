"""THA-24 م1 — محرّك الكفالة: الدورة التلقائية، البوابة، العزل، واشتقاق الحالة.

يثبت:
  1. ترحيل فاتورة بيع لوحدة متسلسلة بصنفٍ ذي كفالة ⇒ بطاقة بدايتها **تاريخ
     الفاتورة**، ونهايتها بداية + المدة، وجانب المورد من نسب الوحدة الشرائي.
  2. إلغاء الترحيل يحذف البطاقة التلقائية ويُبقي اليدوية، وإعادة الترحيل تعيدها.
  3. كل نقطة API ترد 404 لشركة بلا ترخيص الوحدة — ولا أثر للترحيل أصلاً عندها.
  4. عزل الشركات على كل نقطة.
  5. بند غير متسلسل ⇒ لا بطاقة تلقائية.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from after_sales.models import WarrantyCard, add_months
from core.models import TenantModule
from inventory.models import Product, ProductSerial, Warehouse
from inventory.serials import SERIAL_MODE_OPTIONAL
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company


BASE = "/api/after-sales/warranties/"

PURCHASE_DATE = "2026-06-11"
SALE_DATE = "2026-06-15"


# ══════════════════════════════════════════════════════════════════════════
# حساب المدة — دالة صافية بلا قاعدة بيانات
# ══════════════════════════════════════════════════════════════════════════

def test_add_months_walks_the_calendar_not_thirty_day_blocks():
    assert add_months(date(2026, 6, 15), 12) == date(2027, 6, 15)
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 12, 5), 3) == date(2027, 3, 5)
    assert add_months(date(2026, 6, 15), 0) == date(2026, 6, 15)


def test_warranty_status_is_derived_from_end_date_never_stored():
    card = WarrantyCard(
        start_date=date(2026, 1, 1), end_date=date(2026, 6, 30), duration_months=6,
    )
    assert card.status_on(date(2026, 6, 30)) == "active"
    assert card.days_remaining(date(2026, 6, 30)) == 0
    assert card.status_on(date(2026, 7, 1)) == "expired"
    assert card.days_remaining(date(2026, 7, 1)) == -1
    # لا عمود حالة على النموذج — الحالة سؤالٌ يُسأل عن يوم، لا قيمة تُحفظ.
    assert not any(f.name == "status" for f in WarrantyCard._meta.get_fields())


# ══════════════════════════════════════════════════════════════════════════
# التكامل
# ══════════════════════════════════════════════════════════════════════════

class WarrantyTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="aftersales", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة ما بعد البيع", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الأجهزة", partner_type="Supplier",
            linked_account=Account.objects.get(tenant=cls.tenant, code="2101"),
        )
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-AS", name="ذمم", account_type="Asset",
            is_active=True,
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون الكفالة", partner_type="Customer",
            linked_account=cls.ar, phone="0599111222",
        )
        cogs = Account.objects.create(
            tenant=cls.tenant, code="5101-AS", name="تكلفة", account_type="Expense",
            is_active=True,
        )
        inv_acc = Account.objects.create(
            tenant=cls.tenant, code="1104-AS", name="مخزون", account_type="Asset",
            is_active=True,
        )
        ss = get_or_create_sales_settings(cls.tenant)
        ss.default_cogs_account = cogs
        ss.default_inventory_account = inv_acc
        ss.default_ar_account = cls.ar
        # تتبّع الأرقام التسلسلية مفعَّل على الجانبين: الشراء يُنشئ الوحدات
        # والبيع يستهلكها — وبلا استهلاك لا وحدة مُباعة تُعلَّق عليها كفالة.
        ss.serial_entry_mode = SERIAL_MODE_OPTIONAL
        ss.save(update_fields=[
            "default_cogs_account", "default_inventory_account", "default_ar_account",
            "serial_entry_mode",
        ])
        ps = get_or_create_purchase_settings(cls.tenant)
        ps.serial_entry_mode = SERIAL_MODE_OPTIONAL
        ps.save(update_fields=["serial_entry_mode"])

    def setUp(self):
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="after_sales", enabled=True,
        )
        self.product = Product.objects.create(
            tenant=self.tenant, sku=f"WR-{Product.objects.count() + 1}",
            name_ar="لابتوب مكفول", is_serialized=True,
            warranty_months=12, supplier_warranty_months=24,
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        self.plain = Product.objects.create(
            tenant=self.tenant, sku=f"PL-{Product.objects.count() + 1}",
            name_ar="كرتون ورق", is_serialized=False, warranty_months=12,
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        self.client.force_authenticate(user=self.user)

    # ── أدوات ──────────────────────────────────────────────────────────
    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def stock_units(self, *serials, product=None):
        """يُدخل وحدات للمخزن عبر فاتورة شراء مرحّلة — الطريق الطبيعي الوحيد."""
        product = product or self.product
        qty = Decimal(len(serials))
        grand = qty * Decimal("1000")
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"P-{PurchaseInvoice.objects.count() + 1:04d}",
            partner=self.supplier, currency=self.ils, invoice_date=PURCHASE_DATE,
            exchange_rate=Decimal("1"), grand_total=grand,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=invoice, product=product, name=product.name_ar,
            quantity=qty, unit_price=Decimal("1000"), total_price=grand,
            serials=list(serials),
        )
        response = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self.headers(),
        )
        assert response.status_code == 201, response.content
        return invoice

    def sales_invoice(self, *, serials=None, product=None, qty="1"):
        product = product or self.product
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"S-{SalesInvoice.objects.count() + 1:04d}",
            customer=self.customer, currency=self.ils, invoice_date=SALE_DATE,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=product,
            quantity=Decimal(qty), unit_price=Decimal("2000"),
            serials=list(serials or []),
        )
        return invoice

    def post_sale(self, invoice):
        return self.client.post(
            f"/api/sales/invoices/{invoice.pk}/post/", {}, format="json",
            **self.headers(),
        )

    def unpost_sale(self, invoice):
        return self.client.post(
            f"/api/sales/invoices/{invoice.pk}/unpost/", {}, format="json",
            **self.headers(),
        )

    def cards(self, **filters):
        return WarrantyCard.objects.filter(tenant=self.tenant, **filters)


class AutoWarrantyLifecycleTest(WarrantyTestBase):
    def test_posting_a_serialized_sale_writes_a_card_dated_by_the_invoice(self):
        self.stock_units("SN-A1")
        invoice = self.sales_invoice(serials=["SN-A1"])

        response = self.post_sale(invoice)
        self.assertEqual(response.status_code, 200, response.content)

        card = self.cards().get()
        self.assertEqual(card.source, WarrantyCard.SOURCE_AUTO_SALE)
        self.assertEqual(card.serial, "SN-A1")
        self.assertEqual(card.product_id, self.product.pk)
        # البداية تاريخ الفاتورة لا تاريخ الترحيل ولا التسليم.
        self.assertEqual(card.start_date, date(2026, 6, 15))
        self.assertEqual(card.duration_months, 12)
        self.assertEqual(card.end_date, date(2027, 6, 15))
        # جانب المورد من نسب الوحدة: تاريخ فاتورة الشراء + كفالة المورد.
        self.assertEqual(card.supplier_id, self.supplier.pk)
        self.assertEqual(card.supplier_warranty_end_date, date(2028, 6, 11))
        # لقطة الزبون محفوظة على البطاقة نفسها.
        self.assertEqual(card.partner_id, self.customer.pk)
        self.assertEqual(card.customer_name, "زبون الكفالة")
        self.assertEqual(card.customer_phone, "0599111222")
        self.assertEqual(card.product_serial.serial, "SN-A1")

    def test_unpost_removes_the_auto_card_keeps_the_manual_one_repost_restores(self):
        self.stock_units("SN-B1")
        invoice = self.sales_invoice(serials=["SN-B1"])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        manual = WarrantyCard.objects.create(
            tenant=self.tenant, device_name="جهاز زبون خارجي", serial="EXT-9",
            start_date=date(2026, 1, 1), duration_months=6,
            end_date=date(2026, 7, 1), source=WarrantyCard.SOURCE_MANUAL,
        )
        self.assertEqual(self.cards(source=WarrantyCard.SOURCE_AUTO_SALE).count(), 1)

        response = self.unpost_sale(invoice)
        self.assertEqual(response.status_code, 200, response.content)

        self.assertEqual(self.cards(source=WarrantyCard.SOURCE_AUTO_SALE).count(), 0)
        self.assertTrue(self.cards(pk=manual.pk).exists())

        self.assertEqual(self.post_sale(invoice).status_code, 200)
        restored = self.cards(source=WarrantyCard.SOURCE_AUTO_SALE).get()
        self.assertEqual(restored.serial, "SN-B1")
        self.assertEqual(restored.end_date, date(2027, 6, 15))

    def test_a_second_posting_never_doubles_the_card_for_one_unit(self):
        self.stock_units("SN-C1")
        invoice = self.sales_invoice(serials=["SN-C1"])
        self.assertEqual(self.post_sale(invoice).status_code, 200)

        # إعادة الترحيل بعد التراجع لا تُنتج بطاقتين لوحدة واحدة.
        self.assertEqual(self.unpost_sale(invoice).status_code, 200)
        self.assertEqual(self.post_sale(invoice).status_code, 200)

        self.assertEqual(self.cards(serial="SN-C1").count(), 1)

    def test_non_serialized_line_gets_no_automatic_card(self):
        invoice = self.sales_invoice(product=self.plain, qty="5")
        # بضاعة للصنف غير المتسلسل كي يمرّ خصم المخزون.
        Product.objects.filter(pk=self.plain.pk).update(
            quantity_on_hand=Decimal("10"), avg_cost=Decimal("5"),
        )

        self.assertEqual(self.post_sale(invoice).status_code, 200, )

        self.assertEqual(self.cards().count(), 0)

    def test_product_without_a_warranty_policy_gets_no_card(self):
        Product.objects.filter(pk=self.product.pk).update(warranty_months=None)
        self.stock_units("SN-D1")
        invoice = self.sales_invoice(serials=["SN-D1"])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        self.assertEqual(self.cards().count(), 0)

    def test_unlicensed_company_gets_no_card_at_all_zero_footprint(self):
        self.license.delete()
        self.stock_units("SN-E1")
        invoice = self.sales_invoice(serials=["SN-E1"])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        self.assertEqual(WarrantyCard.objects.count(), 0)
        # ولا أثر على الوحدة نفسها: البيع تمّ كما كان قبل الوحدة.
        self.assertEqual(
            ProductSerial.objects.filter(
                tenant=self.tenant, serial="SN-E1", status=ProductSerial.STATUS_SOLD,
            ).count(),
            1,
        )

    def test_unit_without_purchase_lineage_gets_a_card_without_a_supplier_side(self):
        """مخزون سابق للتتبّع: بطاقة بلا جانب مورد أصدق من تاريخٍ مُشتقّ."""
        self.stock_units("SN-F1")
        unit = ProductSerial.objects.get(tenant=self.tenant, serial="SN-F1")
        ProductSerial.objects.filter(pk=unit.pk).update(purchase_item=None)
        invoice = self.sales_invoice(serials=["SN-F1"])

        self.assertEqual(self.post_sale(invoice).status_code, 200)

        card = self.cards().get()
        self.assertIsNone(card.supplier_id)
        self.assertIsNone(card.supplier_warranty_end_date)
        self.assertEqual(card.end_date, date(2027, 6, 15))


class WarrantyApiTest(WarrantyTestBase):
    def manual_payload(self, **overrides):
        data = {
            "device_name": "هاتف زبون",
            "serial": "MAN-1",
            "start_date": "2026-06-01",
            "duration_months": 6,
            "customer_name": "سامي",
        }
        data.update(overrides)
        return data

    def test_manual_card_derives_its_end_date_once_and_reports_derived_status(self):
        response = self.client.post(
            BASE, self.manual_payload(), format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["end_date"], "2026-12-01")
        self.assertEqual(response.data["source"], "manual")
        self.assertIn(response.data["status"], ("active", "expired"))

    def test_manual_card_without_any_identity_is_rejected(self):
        response = self.client.post(
            BASE, self.manual_payload(serial="", device_name=""), format="json",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("serial", response.data)

    def test_end_date_before_start_is_rejected(self):
        response = self.client.post(
            BASE, self.manual_payload(end_date="2026-05-01"), format="json",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("end_date", response.data)

    def test_extend_pushes_the_end_date_and_records_it_in_the_notes(self):
        created = self.client.post(
            BASE, self.manual_payload(), format="json", **self.headers(),
        ).data

        response = self.client.post(
            f"{BASE}{created['id']}/extend/", {"months": 3, "reason": "مجاملة"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["end_date"], "2027-03-01")
        self.assertIn("تمديد الكفالة", response.data["notes"])
        self.assertIn("مجاملة", response.data["notes"])

    def test_extend_needs_a_target(self):
        created = self.client.post(
            BASE, self.manual_payload(), format="json", **self.headers(),
        ).data

        response = self.client.post(
            f"{BASE}{created['id']}/extend/", {}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_auto_card_accepts_an_extension_but_refuses_a_rewritten_lineage(self):
        self.stock_units("SN-G1")
        invoice = self.sales_invoice(serials=["SN-G1"])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        card = self.cards().get()

        rewrite = self.client.patch(
            f"{BASE}{card.pk}/", {"serial": "OTHER"}, format="json", **self.headers(),
        )
        self.assertEqual(rewrite.status_code, 400, rewrite.content)

        goodwill = self.client.patch(
            f"{BASE}{card.pk}/", {"end_date": "2027-12-31"}, format="json",
            **self.headers(),
        )
        self.assertEqual(goodwill.status_code, 200, goodwill.content)
        card.refresh_from_db()
        self.assertEqual(card.end_date, date(2027, 12, 31))

    def test_auto_card_cannot_be_deleted_directly_but_a_manual_one_can(self):
        self.stock_units("SN-H1")
        invoice = self.sales_invoice(serials=["SN-H1"])
        self.assertEqual(self.post_sale(invoice).status_code, 200)
        auto = self.cards().get()
        manual = self.client.post(
            BASE, self.manual_payload(), format="json", **self.headers(),
        ).data

        blocked = self.client.delete(f"{BASE}{auto.pk}/", **self.headers())
        self.assertEqual(blocked.status_code, 400, blocked.content)

        removed = self.client.delete(f"{BASE}{manual['id']}/", **self.headers())
        self.assertEqual(removed.status_code, 204, removed.content)

    def test_check_reads_the_card_and_falls_back_to_the_unit_lineage(self):
        self.stock_units("SN-I1", "SN-I2")
        invoice = self.sales_invoice(serials=["SN-I1"])
        self.assertEqual(self.post_sale(invoice).status_code, 200)

        covered = self.client.get(f"{BASE}check/?serial=SN-I1", **self.headers()).data
        self.assertTrue(covered["covered"])
        self.assertEqual(len(covered["cards"]), 1)
        self.assertEqual(covered["cards"][0]["end_date"], date(2027, 6, 15))
        self.assertEqual(covered["unit"]["sales_invoice"], invoice.pk)
        self.assertEqual(covered["unit"]["customer_name"], "زبون الكفالة")

        # وحدة في المخزن لم تُبَع بعد: لا بطاقة، لكن نسبها معروف.
        unsold = self.client.get(f"{BASE}check/?serial=SN-I2", **self.headers()).data
        self.assertFalse(unsold["covered"])
        self.assertEqual(unsold["cards"], [])
        self.assertEqual(unsold["unit"]["status"], ProductSerial.STATUS_IN_STOCK)
        self.assertEqual(unsold["unit"]["warranty_months"], 12)

        unknown = self.client.get(f"{BASE}check/?serial=NOPE", **self.headers()).data
        self.assertFalse(unknown["covered"])
        self.assertIsNone(unknown["unit"])

    def test_list_filters_by_search_term_and_derived_status(self):
        self.client.post(
            BASE, self.manual_payload(serial="LIVE-1", start_date="2026-01-01",
                                      end_date="2999-01-01"),
            format="json", **self.headers(),
        )
        self.client.post(
            BASE, self.manual_payload(serial="DEAD-1", start_date="2020-01-01",
                                      end_date="2020-06-01"),
            format="json", **self.headers(),
        )

        active = self.client.get(f"{BASE}?status=active", **self.headers()).data
        expired = self.client.get(f"{BASE}?status=expired", **self.headers()).data
        searched = self.client.get(f"{BASE}?q=DEAD", **self.headers()).data

        self.assertEqual([row["serial"] for row in active], ["LIVE-1"])
        self.assertEqual([row["serial"] for row in expired], ["DEAD-1"])
        self.assertEqual([row["serial"] for row in searched], ["DEAD-1"])


class ModuleGateTest(WarrantyTestBase):
    def test_every_endpoint_is_404_without_a_module_license(self):
        card = WarrantyCard.objects.create(
            tenant=self.tenant, serial="GATE-1", start_date=date(2026, 1, 1),
            duration_months=12, end_date=date(2027, 1, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        self.license.delete()

        calls = [
            ("get", BASE, None),
            ("post", BASE, {"serial": "X", "start_date": "2026-01-01", "duration_months": 1}),
            ("get", f"{BASE}{card.pk}/", None),
            ("patch", f"{BASE}{card.pk}/", {"notes": "x"}),
            ("delete", f"{BASE}{card.pk}/", None),
            ("post", f"{BASE}{card.pk}/extend/", {"months": 1}),
            ("get", f"{BASE}check/?serial=GATE-1", None),
        ]
        for method, url, body in calls:
            with self.subTest(method=method, url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(
                    response.status_code, 404, f"{method} {url} → {response.status_code}",
                )

    def test_licensed_company_reaches_the_list(self):
        response = self.client.get(BASE, **self.headers())

        self.assertEqual(response.status_code, 200, response.content)


class TenantIsolationTest(WarrantyTestBase):
    def setUp(self):
        super().setUp()
        self.other = create_company("شركة أخرى", self.user)
        TenantModule.objects.create(
            tenant=self.other, module_key="after_sales", enabled=True,
        )
        self.other_card = WarrantyCard.objects.create(
            tenant=self.other, serial="OTHER-1", start_date=date(2026, 1, 1),
            duration_months=12, end_date=date(2027, 1, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )
        self.mine = WarrantyCard.objects.create(
            tenant=self.tenant, serial="MINE-1", start_date=date(2026, 1, 1),
            duration_months=12, end_date=date(2027, 1, 1),
            source=WarrantyCard.SOURCE_MANUAL,
        )

    def test_list_shows_only_the_active_company_cards(self):
        response = self.client.get(BASE, **self.headers())

        self.assertEqual(
            [row["serial"] for row in response.data], ["MINE-1"],
        )

    def test_every_detail_endpoint_hides_another_company_card(self):
        calls = [
            ("get", f"{BASE}{self.other_card.pk}/", None),
            ("patch", f"{BASE}{self.other_card.pk}/", {"notes": "تسريب"}),
            ("delete", f"{BASE}{self.other_card.pk}/", None),
            ("post", f"{BASE}{self.other_card.pk}/extend/", {"months": 1}),
        ]
        for method, url, body in calls:
            with self.subTest(method=method):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 404, response.content)

        self.other_card.refresh_from_db()
        self.assertEqual(self.other_card.notes, "")

    def test_check_never_reaches_across_companies(self):
        response = self.client.get(f"{BASE}check/?serial=OTHER-1", **self.headers())

        self.assertEqual(response.data["cards"], [])
        self.assertFalse(response.data["covered"])

    def test_a_card_cannot_be_created_pointing_at_another_company_partner(self):
        outsider = Partner.objects.create(
            tenant=self.other, name="زبون الغير", partner_type="Customer",
        )

        response = self.client.post(
            BASE,
            {"serial": "X-1", "start_date": "2026-01-01", "duration_months": 6,
             "partner": outsider.pk},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("partner", response.data)
