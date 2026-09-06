"""ISSUE #88 — منتقي المستندات كان يفقد بنود قالب المكتب: القناع يبتلع البادئة.

القناع الحيّ (`tenants/company_templates.py` — `TEMPLATE_HIDDEN_PATH_PREFIXES`)
يخفي `/api/inventory/` **كاملةً** ببادئة المسار (`core/permissions.py` —
`TemplateSurfacePermission` يفحص بادئة المسار لا معاملات الاستعلام). فمنتقي
المستندات — الذي كان يجلب من `/api/inventory/products/?view=lookup`
(`frontend_v2/services/inventoryApi.ts` — `listPickerProducts`) — يستحيل عليه
الوصول إلى خدمات #78 (`4103`-`4106`) لشركة `accounting_firm`، ولو حمل الطلب
معاملاً يطلب عقداً ضيّقاً: القناع لا يرى المعامل أصلاً.

الحلّ (القرار الأول في التذكرة): نقطةٌ مستقلة `/api/lookup/products/` خارج
بادئة `/api/inventory/`، تخدم عقد `lookup` وحده — `ProductLookupViewSet`
(`inventory/views.py`) فرعٌ من `ProductViewSet` يفرض `_is_lookup()`، لا نسخة
ثانية من الفلاتر أو السيريالايزر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from tenants.company_templates import ACCOUNTING_FIRM_SERVICES
from tenants.models import Currency
from tenants.services import create_company

LOOKUP_URL = "/api/lookup/products/"
INVENTORY_PRODUCTS_URL = "/api/inventory/products/"


def _make_tenant(username, *, template="accounting_firm"):
    owner = User.objects.create_user(username=username, password="x")
    ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
        Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
    tenant = create_company(f"مكتب {username}", owner, template=template)
    create_fiscal_year(tenant, 2026)
    return tenant, owner, ils


class ProductLookupEndpointTest(APITestCase):
    """المنتقي المستقل يخدم عقد `lookup` نفسه، حتى حين يُقنَّع `/api/inventory/`."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant, cls.owner, cls.ils = _make_tenant("lookup-firm")
        cls.other_tenant, cls.other_owner, _ = _make_tenant(
            "lookup-firm-other", template="general")

    def _auth(self, tenant=None, user=None):
        self.client.force_authenticate(user=user or self.owner)
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    # ── معيار القبول 1: القناع يبقى يحجب شاشة الأصناف الكاملة ──
    def test_inventory_products_endpoint_stays_masked_for_accounting_firm(self):
        res = self.client.get(INVENTORY_PRODUCTS_URL, **self._auth())
        self.assertEqual(res.status_code, 404, res.content)

    # ── معيار القبول 2: المنتقي المستقل يصل رغم القناع، ويحمل الخدمة المزروعة ──
    def test_lookup_endpoint_bypasses_the_mask_and_lists_seeded_services(self):
        res = self.client.get(LOOKUP_URL, **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        skus = {row["sku"] for row in res.json()}
        self.assertEqual(
            skus, {sku for sku, _name, _code in ACCOUNTING_FIRM_SERVICES},
        )

    def test_lookup_endpoint_row_matches_the_narrow_lookup_contract(self):
        res = self.client.get(LOOKUP_URL, **self._auth())
        row = next(r for r in res.json() if r["sku"] == "SVC-BOOKKEEPING")
        for field in (
            "id", "sku", "name_ar", "stock_status", "is_service",
            "quantity_on_hand", "available_quantity",
        ):
            self.assertIn(field, row)
        # عقدٌ ضيّق عمداً — بلا حقول الكرت الكامل (تحليلات المشتريات/المبيعات).
        self.assertNotIn("purchased_qty", row)
        self.assertNotIn("avg_monthly_sales", row)

    # ── general: صفر تغيير — نفس صفوف `?view=lookup` القديمة حرفياً ──
    def test_lookup_endpoint_matches_old_contract_for_general_template(self):
        Product.objects.create(
            tenant=self.other_tenant, sku="GEN-1", name_ar="منتج عام",
            quantity_on_hand=Decimal("5"), avg_cost=Decimal("10"))
        auth = self._auth(tenant=self.other_tenant, user=self.other_owner)
        old = self.client.get(
            INVENTORY_PRODUCTS_URL, {"view": "lookup"}, **auth).json()
        new = self.client.get(LOOKUP_URL, **auth).json()
        self.assertEqual(
            sorted(old, key=lambda r: r["id"]),
            sorted(new, key=lambda r: r["id"]),
        )

    # ── العزل: منتجات شركةٍ لا تظهر لأخرى ──
    def test_lookup_endpoint_is_tenant_isolated(self):
        res = self.client.get(
            LOOKUP_URL, **self._auth(tenant=self.other_tenant, user=self.other_owner))
        skus = {row["sku"] for row in res.json()}
        self.assertFalse(skus & {sku for sku, _n, _c in ACCOUNTING_FIRM_SERVICES})

    # ── قراءةٌ لا كتابة: لا نقطة كتابة موازية للمخزون هنا ──
    def test_lookup_endpoint_rejects_write_methods(self):
        auth = self._auth()
        for method in (self.client.post, self.client.put, self.client.delete):
            with self.subTest(method=method.__name__):
                res = method(LOOKUP_URL, {}, format="json", **auth)
                self.assertEqual(res.status_code, 405, res.content)


class OfficeBookkeepingServiceInvoiceHttpTest(APITestCase):
    """معيار القبول الأول حرفياً: اختيار «مسك دفاتر شهري» من المنتقي ينجح،
    والترحيل يقع على `4103` — عبر الـHTTP لا عبر الخدمة مباشرة."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant, cls.owner, cls.ils = _make_tenant("lookup-invoice")
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل المكتب", partner_type="Customer")

    def _auth(self):
        self.client.force_authenticate(user=self.owner)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_invoice_editor_journey_selects_service_via_lookup_and_posts_to_4103(self):
        auth = self._auth()

        # الشاشة تفتح المنتقي أولاً — هذا هو المسار الذي كان يردّ 404 قبل #88.
        lookup_res = self.client.get(LOOKUP_URL, **auth)
        self.assertEqual(lookup_res.status_code, 200, lookup_res.content)
        bookkeeping = next(
            row for row in lookup_res.json() if row["sku"] == "SVC-BOOKKEEPING")

        create_res = self.client.post(
            "/api/sales/invoices/",
            {
                "customer": self.customer.pk,
                "currency": self.ils.pk,
                "invoice_date": "2026-06-10",
                "invoice_type": "credit",
                "lines": [{
                    "product": bookkeeping["id"], "quantity": "1",
                    "unit_price": "500.00",
                }],
            },
            format="json", **auth,
        )
        self.assertEqual(create_res.status_code, 201, create_res.content)
        invoice_id = create_res.json()["id"]

        post_res = self.client.post(
            f"/api/sales/invoices/{invoice_id}/post/", {}, format="json", **auth)
        self.assertEqual(post_res.status_code, 200, post_res.content)

        journal_id = post_res.json()["journal"]
        fees_4103 = Account.objects.get(tenant=self.tenant, code="4103")
        credited = JournalLine.objects.filter(
            journal_id=journal_id, account=fees_4103, credit=Decimal("500.00"),
        ).exists()
        self.assertTrue(credited, "القيد لم يُدائن 4103 بمبلغ الخدمة المختارة")


class ProductReferenceImageContractTest(APITestCase):
    """#147 — صورةٌ مرجعيةٌ واحدة للبراند: تصل في عقد المنتقي وتُكتب من العقد الكامل.

    الصورةُ سببُ وجودها المورّدُ الذي يُسعّر على رابط الطلبية العامّ: يقرأ اسماً
    وكميّةً ولا يعرف ما هو الصنف. وصفحةُ الرابط ومحرِّرُ بند الطلبية كلاهما يقرأ
    المنتجات من **عقد المنتقي** لا من العقد الكامل — فغيابُ الحقل هناك يعني
    ميزةً ميّتةً وإن كُتب الحقل في القاعدة.
    """

    @classmethod
    def setUpTestData(cls):
        # قالب `general` لا `accounting_firm`: الأخير يُقنّع `/api/inventory/`
        # كاملةً (وهو سببُ وجود نقطة المنتقي المستقلة أصلاً)، وجولةُ الكتابة
        # أدناه تمرّ من العقد الكامل هناك.
        cls.tenant, cls.owner, cls.ils = _make_tenant(
            "lookup-image", template="general")
        cls.with_image = Product.objects.create(
            tenant=cls.tenant, sku="IMG-1", name_ar="صنفٌ له صورة",
            image_url="https://example.test/a.jpg",
        )
        cls.without_image = Product.objects.create(
            tenant=cls.tenant, sku="IMG-0", name_ar="صنفٌ بلا صورة",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.owner)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _lookup_row(self, product_id):
        res = self.client.get(LOOKUP_URL, **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        return next(row for row in res.json() if row["id"] == product_id)

    def test_picker_contract_carries_the_stored_image(self):
        row = self._lookup_row(self.with_image.pk)
        self.assertEqual(row["image_url"], "https://example.test/a.jpg")

    def test_product_without_image_reports_empty_string_not_missing_and_not_null(self):
        """شكلٌ واحدٌ تتعامل معه الواجهة: `""` لا مفتاحٌ غائبٌ ولا `null`.

        ثلاثةُ أشكالٍ لغيابِ الصورة تعني ثلاثةَ فحوصٍ في كلّ مستهلك، وواحدٌ
        منها سيُنسى.
        """
        row = self._lookup_row(self.without_image.pk)
        self.assertIn("image_url", row)
        self.assertEqual(row["image_url"], "")

    def test_image_round_trips_through_the_full_product_contract(self):
        """كرت الصنف يكتبها والعقد الكامل يعيدها — وإلّا فالرفع بلا حفظ."""
        auth = self._auth()
        res = self.client.patch(
            f"{INVENTORY_PRODUCTS_URL}{self.without_image.pk}/",
            {"image_url": "https://example.test/b.png"}, format="json", **auth,
        )
        self.assertEqual(res.status_code, 200, res.content)

        self.without_image.refresh_from_db()
        self.assertEqual(self.without_image.image_url, "https://example.test/b.png")
        self.assertEqual(self._lookup_row(self.without_image.pk)["image_url"],
                         "https://example.test/b.png")

    def test_another_company_never_sees_this_image(self):
        other_tenant, other_owner, _ = _make_tenant(
            "lookup-image-other", template="general")
        self.client.force_authenticate(user=other_owner)
        res = self.client.get(
            LOOKUP_URL, **{"HTTP_X_TENANT_ID": str(other_tenant.TenantID)})
        self.assertEqual(res.status_code, 200, res.content)
        urls = {row.get("image_url") for row in res.json()}
        self.assertNotIn("https://example.test/a.jpg", urls)
