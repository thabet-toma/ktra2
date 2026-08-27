"""T-SCAN — «ما الذي في يدي؟»: حقلٌ واحد يحلّ كل ما يُمسح.

قلب هذا الملف اختبارٌ واحد هو **معيار المهمة**: مسح IMEI جهازٍ بِعناه يفتح
بطاقته وفيها العميل وتاريخ البيع وحالة الكفالة. وما حوله يحرس القرارات التي
بُني عليها الحلّال:

  1. **الشكل يُرتّب ولا يُصفّي** — رقمٌ يجتاز Luhn يبقى مطابَقاً على الوحدات
     المُرقَّمة، وباركودٌ سليم البنية يبقى مطابَقاً على السيريالات. حلّالٌ
     يقصر البحث على النوع المُستنتَج يقول «غير مسجَّل» عن وحدةٍ في المخزن.
  2. **التطابق التامّ قبل الجزئي** — اليقين لا يُخلط بالترجيح في قائمة واحدة.
  3. **كل مصدرٍ بصلاحيته** — بلا ترخيص `after_sales` تُعاد البطاقة بلا كفالة
     وبلا صيانات، وبلا أي صلاحية يُرفض الحقل كلّه بـ403 لا بردٍّ فارغ.
  4. **عزل الشركات** على كل مصدر.
  5. **عدد الاستعلامات لا يتبع عدد المطابقات.**
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from core.models import TenantModule
from core.scan import guess_kind
from inventory.models import Product, ProductSerial, Warehouse
from inventory.serials import SERIAL_MODE_OPTIONAL
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company


SCAN = "/api/scan/"

PURCHASE_DATE = "2026-06-11"
SALE_DATE = "2026-06-15"

#: IMEI حقيقي البنية — 15 خانة تجتاز Luhn. في متجر الهواتف هذا **هو** الرقم
#: التسلسلي المكتوب على العلبة، فهو ما يدخل `ProductSerial.serial`.
IMEI = "356938035643809"
OTHER_IMEI = "490154203237518"
#: 15 خانة لا تجتاز Luhn — يجب أن يبقى `text` لا `imei`.
NOT_IMEI = "356938035643801"
#: EAN-13 سليم خانةَ التحقّق.
BARCODE = "2000000000015"


# ══════════════════════════════════════════════════════════════════════════
# استنتاج الشكل — دالة صافية بلا قاعدة بيانات
# ══════════════════════════════════════════════════════════════════════════

def test_kind_is_read_from_the_shape_not_from_the_user():
    assert guess_kind(IMEI) == "imei"
    assert guess_kind(BARCODE) == "barcode"
    assert guess_kind(NOT_IMEI) == "text"
    assert guess_kind("SN-A1") == "text"
    assert guess_kind("") == "text"
    assert guess_kind(None) == "text"
    # الفراغ المحيط لا يغيّر الحكم — الماسح والنسخ من الجوال يأتيان به.
    assert guess_kind(f"  {IMEI} ") == "imei"


# ══════════════════════════════════════════════════════════════════════════
# التكامل
# ══════════════════════════════════════════════════════════════════════════

class ScanTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="scanner", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("متجر الهواتف", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الأجهزة", partner_type="Supplier",
            linked_account=Account.objects.get(tenant=cls.tenant, code="2101"),
        )
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-SC", name="ذمم", account_type="Asset",
            is_active=True,
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون الجهاز", partner_type="Customer",
            linked_account=cls.ar, phone="0599111222",
        )
        cogs = Account.objects.create(
            tenant=cls.tenant, code="5101-SC", name="تكلفة", account_type="Expense",
            is_active=True,
        )
        inv_acc = Account.objects.create(
            tenant=cls.tenant, code="1104-SC", name="مخزون", account_type="Asset",
            is_active=True,
        )
        settings = get_or_create_sales_settings(cls.tenant)
        settings.default_cogs_account = cogs
        settings.default_inventory_account = inv_acc
        settings.default_ar_account = cls.ar
        settings.serial_entry_mode = SERIAL_MODE_OPTIONAL
        settings.save(update_fields=[
            "default_cogs_account", "default_inventory_account",
            "default_ar_account", "serial_entry_mode",
        ])
        purchase = get_or_create_purchase_settings(cls.tenant)
        purchase.serial_entry_mode = SERIAL_MODE_OPTIONAL
        purchase.save(update_fields=["serial_entry_mode"])

    def setUp(self):
        # الوحدتان المرخَّصتان مفعَّلتان افتراضياً — الاختبارات التي تقيس الإطفاء
        # تحذف الترخيص صراحةً كي يظهر في نصّها ما تقيسه.
        TenantModule.objects.create(
            tenant=self.tenant, module_key="after_sales", enabled=True,
        )
        TenantModule.objects.create(
            tenant=self.tenant, module_key="sensitive_devices", enabled=True,
        )
        self.phone = Product.objects.create(
            tenant=self.tenant, sku="PH-001", barcode=BARCODE,
            name_ar="هاتف ذكي 128 جيجا", brand="سامسونج", is_serialized=True,
            warranty_months=12, supplier_warranty_months=24,
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
            sale_price=Decimal("2000"),
        )
        self.client.force_authenticate(user=self.user)

    # ── أدوات ──────────────────────────────────────────────────────────
    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def scan(self, term, tenant=None):
        return self.client.get(SCAN, {"q": term}, **self.headers(tenant))

    def stock_units(self, *serials, product=None):
        """يُدخل وحدات للمخزن عبر فاتورة شراء مرحّلة — الطريق الطبيعي الوحيد."""
        product = product or self.phone
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

    def sell_unit(self, serial, product=None):
        product = product or self.phone
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"S-{SalesInvoice.objects.count() + 1:04d}",
            customer=self.customer, currency=self.ils, invoice_date=SALE_DATE,
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=True,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=product,
            quantity=Decimal("1"), unit_price=Decimal("2000"), serials=[serial],
        )
        response = self.client.post(
            f"/api/sales/invoices/{invoice.pk}/post/", {}, format="json",
            **self.headers(),
        )
        assert response.status_code == 200, response.content
        return invoice

    def only_match(self, payload, expected_type):
        matches = [m for m in payload["matches"] if m["type"] == expected_type]
        self.assertEqual(
            len(matches), 1,
            f"توقّعنا مطابقة {expected_type} واحدة، وجاء: {payload['matches']}",
        )
        return matches[0]


# ══════════════════════════════════════════════════════════════════════════
# معيار المهمة
# ══════════════════════════════════════════════════════════════════════════

class ScannedImeiOpensTheUnitCardTest(ScanTestBase):
    def test_scanning_a_sold_imei_returns_customer_sale_date_and_warranty(self):
        """**معيار المهمة**: مسح IMEI جهاز مباع يفتح بطاقته كاملةً بنداءٍ واحد."""
        self.stock_units(IMEI)
        sale = self.sell_unit(IMEI)

        response = self.scan(IMEI)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()

        self.assertEqual(payload["kind"], "imei")
        self.assertFalse(payload["unregistered"])
        unit = self.only_match(payload, "unit")

        # ① العميل — بالاسم وبالمعرّف وبالهاتف: الاسم يسمّي ولا يُثبت.
        self.assertEqual(unit["customer_name"], "زبون الجهاز")
        self.assertEqual(unit["customer"], self.customer.pk)
        self.assertEqual(unit["customer_phone"], "0599111222")

        # ② تاريخ البيع — وهو ما تُحسب منه مدّة الكفالة.
        self.assertEqual(unit["sold_at"], SALE_DATE)
        self.assertEqual(unit["sales_invoice"], sale.pk)
        self.assertEqual(unit["status"], ProductSerial.STATUS_SOLD)

        # ③ حالة الكفالة — سارية، وبطاقتها تنتهي بعد سنة من تاريخ الفاتورة.
        self.assertIsNotNone(unit["warranty"])
        self.assertTrue(unit["warranty"]["covered"])
        card = unit["warranty"]["cards"][0]
        self.assertEqual(card["status"], "active")
        self.assertEqual(card["end_date"], date(2027, 6, 15).isoformat())
        # كفالة المورد جانبٌ مستقل — 24 شهراً من تاريخ فاتورة الشراء.
        self.assertTrue(unit["warranty"]["supplier_covered"])

        # ورحلة القطعة كاملة في الصفّ نفسه: من أين جاءت وبكم.
        self.assertEqual(unit["supplier_name"], "مورد الأجهزة")
        self.assertEqual(unit["purchase_date"], PURCHASE_DATE)
        self.assertEqual(Decimal(unit["purchase_unit_price"]), Decimal("1000"))


# ══════════════════════════════════════════════════════════════════════════
# الشكل يُرتّب ولا يُصفّي
# ══════════════════════════════════════════════════════════════════════════

class ShapeOrdersButNeverFiltersTest(ScanTestBase):
    def test_an_imei_shaped_serial_still_matches_the_stock_unit(self):
        """لو صفّى الحلّال بالشكل لقال «غير مسجَّل» عن وحدةٍ في المخزن."""
        self.stock_units(IMEI)

        payload = self.scan(IMEI).json()
        self.assertEqual(payload["kind"], "imei")
        unit = self.only_match(payload, "unit")
        self.assertEqual(unit["serial"], IMEI)
        self.assertEqual(unit["status"], ProductSerial.STATUS_IN_STOCK)
        self.assertIsNone(unit["customer"])

    def test_a_barcode_shaped_serial_still_matches_the_stock_unit(self):
        """والعكس: رقم وحدةٍ بنيتُه EAN-13 لا يُقصر على المنتجات."""
        self.stock_units(BARCODE)

        payload = self.scan(BARCODE).json()
        self.assertEqual(payload["kind"], "barcode")
        # نفس الرقم باركودُ المنتج **و** رقم وحدةٍ منه: كلاهما يُعرض، ولا يُخمَّن.
        types = [m["type"] for m in payload["matches"]]
        self.assertIn("unit", types)
        self.assertIn("product", types)
        # والوحدة قبل المنتج — الأخصّ أولاً.
        self.assertEqual(types[0], "unit")


# ══════════════════════════════════════════════════════════════════════════
# المنتجات: التامّ قبل الجزئي
# ══════════════════════════════════════════════════════════════════════════

class ProductResolutionOrderTest(ScanTestBase):
    def test_barcode_and_sku_resolve_exactly_and_are_labelled_by_what_matched(self):
        by_barcode = self.only_match(self.scan(BARCODE).json(), "product")
        self.assertEqual(by_barcode["id"], self.phone.pk)
        self.assertEqual(by_barcode["matched_on"], "barcode")

        by_sku = self.only_match(self.scan("PH-001").json(), "product")
        self.assertEqual(by_sku["id"], self.phone.pk)
        self.assertEqual(by_sku["matched_on"], "sku")

    def test_a_name_fragment_returns_partial_matches_marked_as_such(self):
        Product.objects.create(
            tenant=self.tenant, sku="PH-002", name_ar="هاتف ذكي 256 جيجا",
            brand="سامسونج", quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        payload = self.scan("هاتف ذكي").json()
        products = [m for m in payload["matches"] if m["type"] == "product"]
        self.assertEqual(len(products), 2)
        # الترجيح موسومٌ ترجيحاً — كي لا يُقرأ سطرٌ مرجَّح على أنه يقين.
        self.assertTrue(all(p["matched_on"] == "partial" for p in products))
        self.assertEqual(payload["kind"], "text")

    def test_an_exact_sku_is_never_pushed_below_a_partial_name_hit(self):
        """منتجٌ رمزه «PH-001» وآخرُ اسمه يحوي «PH-001» — التامّ أولاً دائماً."""
        Product.objects.create(
            tenant=self.tenant, sku="PH-900", name_ar="حافظة للموديل PH-001",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        products = [
            m for m in self.scan("PH-001").json()["matches"] if m["type"] == "product"
        ]
        self.assertEqual(products[0]["id"], self.phone.pk)
        self.assertEqual(products[0]["matched_on"], "sku")
        self.assertEqual(products[1]["matched_on"], "partial")


# ══════════════════════════════════════════════════════════════════════════
# غير المسجَّل، والأجهزة الحسّاسة
# ══════════════════════════════════════════════════════════════════════════

class UnregisteredAndDeviceRegistryTest(ScanTestBase):
    def test_an_unknown_number_is_reported_unregistered_not_empty(self):
        payload = self.scan(OTHER_IMEI).json()
        self.assertEqual(payload["matches"], [])
        self.assertTrue(payload["unregistered"])
        # والنطاق يصاحب الردّ كي ترسم الواجهة أزرار التسجيل المتاحة فعلاً.
        self.assertTrue(payload["scope"]["devices"])

    def test_an_empty_term_is_not_an_unknown_number(self):
        payload = self.scan("").json()
        self.assertEqual(payload["matches"], [])
        self.assertFalse(payload["unregistered"])

    def test_the_same_number_sold_and_registered_shows_both_sides(self):
        """بِعنا الهاتف ثم استُقبل للتوثيق — حالة مشروعة، والمستخدم يختار."""
        from device_registry.models import SensitiveDevice

        self.stock_units(IMEI)
        self.sell_unit(IMEI)
        SensitiveDevice.objects.create(
            tenant=self.tenant, customer_name="زبون الجهاز",
            customer_phone="0599111222", model_name="هاتف ذكي",
            serial_number="BOX-1", imei=IMEI,
        )

        payload = self.scan(IMEI).json()
        types = [m["type"] for m in payload["matches"]]
        self.assertEqual(types.count("unit"), 1)
        self.assertEqual(types.count("device"), 1)
        device = self.only_match(payload, "device")
        self.assertEqual(device["imei"], IMEI)
        self.assertEqual(device["customer_phone"], "0599111222")


# ══════════════════════════════════════════════════════════════════════════
# سجلّ الصيانات على البطاقة
# ══════════════════════════════════════════════════════════════════════════

class ServiceHistoryOnTheCardTest(ScanTestBase):
    def test_previous_service_orders_ride_along_with_the_scan(self):
        from after_sales.models import ServiceOrder

        self.stock_units(IMEI)
        self.sell_unit(IMEI)
        ServiceOrder.objects.create(
            tenant=self.tenant, order_number="SV-0001", order_date=date(2026, 7, 1),
            serial=IMEI, complaint="الشاشة لا تستجيب", partner=self.customer,
        )

        unit = self.only_match(self.scan(IMEI).json(), "unit")
        self.assertEqual(len(unit["service_orders"]), 1)
        self.assertEqual(unit["service_orders"][0]["order_number"], "SV-0001")
        self.assertEqual(unit["service_orders"][0]["complaint"], "الشاشة لا تستجيب")


# ══════════════════════════════════════════════════════════════════════════
# الترخيص والصلاحية والعزل
# ══════════════════════════════════════════════════════════════════════════

class ScopeAndIsolationTest(ScanTestBase):
    def test_without_the_after_sales_licence_the_card_carries_no_warranty(self):
        TenantModule.objects.filter(
            tenant=self.tenant, module_key="after_sales",
        ).update(enabled=False)
        self.stock_units(IMEI)
        self.sell_unit(IMEI)

        payload = self.scan(IMEI).json()
        unit = self.only_match(payload, "unit")
        # الوحدة نفسها تُعرض — البيع بضاعتنا لا وحدةٌ مرخَّصة. الغائب التغطية.
        self.assertEqual(unit["customer_name"], "زبون الجهاز")
        self.assertIsNone(unit["warranty"])
        self.assertEqual(unit["service_orders"], [])
        self.assertFalse(payload["scope"]["warranty"])

    def test_without_the_devices_licence_the_registry_is_not_searched(self):
        from device_registry.models import SensitiveDevice

        SensitiveDevice.objects.create(
            tenant=self.tenant, customer_name="زبون", customer_phone="0599000111",
            model_name="جهاز", serial_number="BOX-9", imei=OTHER_IMEI,
        )
        TenantModule.objects.filter(
            tenant=self.tenant, module_key="sensitive_devices",
        ).update(enabled=False)

        payload = self.scan(OTHER_IMEI).json()
        self.assertEqual(payload["matches"], [])
        self.assertFalse(payload["scope"]["devices"])

    def test_a_user_with_no_source_permission_is_refused_not_answered_empty(self):
        """403 أصدق من ردٍّ فارغ يُقرأ «الرقم غير مسجَّل» وهو مسجَّل ولا يراه."""
        from tenants.models import RolePermission, UserCompanyMembership

        clerk = User.objects.create_user(username="clerk", password="x")
        UserCompanyMembership.objects.create(
            user=clerk, tenant=self.tenant, role="staff",
        )
        # نزع كل مصدر: المنتجات بالصلاحية، والوحدتان بالترخيص.
        RolePermission.objects.create(
            tenant=self.tenant, role="staff",
            permission_key="inventory.item.view", allowed=False,
        )
        TenantModule.objects.filter(tenant=self.tenant).update(enabled=False)

        self.client.force_authenticate(user=clerk)
        response = self.scan(IMEI)
        self.assertEqual(response.status_code, 403, response.content)

    def test_another_company_never_sees_this_unit(self):
        other_user = User.objects.create_user(username="rival", password="x")
        other = create_company("متجر منافس", other_user)
        self.stock_units(IMEI)
        self.sell_unit(IMEI)

        self.client.force_authenticate(user=other_user)
        payload = self.scan(IMEI, tenant=other).json()
        self.assertEqual(payload["matches"], [])
        self.assertTrue(payload["unregistered"])


# ══════════════════════════════════════════════════════════════════════════
# الأداء — العدد لا يتبع عدد المطابقات
# ══════════════════════════════════════════════════════════════════════════

class ScanQueryCountTest(ScanTestBase):
    def test_query_count_does_not_grow_with_the_number_of_matched_units(self):
        """وحدةٌ مطابقة أم ثلاث — الفرق يجب أن يكون ثابتاً لا مضروباً.

        `unique_together` هو (شركة، منتج، رقم)، فثلاثة منتجات قد تحمل الرقم نفسه.
        لو أُثريت كل وحدة باستعلامها لصار المسح N+1 على أكثر مساراته سخونة.
        """
        self.stock_units(IMEI)
        one = self._measure(IMEI)

        for index in (2, 3):
            twin = Product.objects.create(
                tenant=self.tenant, sku=f"PH-{index:03d}", name_ar=f"هاتف {index}",
                is_serialized=True, quantity_on_hand=Decimal("0"),
                avg_cost=Decimal("0"),
            )
            self.stock_units(IMEI, product=twin)

        self.assertEqual(ProductSerial.objects.filter(serial=IMEI).count(), 3)
        three = self._measure(IMEI)
        self.assertEqual(
            one, three,
            f"عدد الاستعلامات تبع عدد المطابقات: {one} ← {three}",
        )

    def _measure(self, term):
        with CaptureQueriesContext(connection) as captured:
            response = self.scan(term)
            self.assertEqual(response.status_code, 200)
        return len(captured)
