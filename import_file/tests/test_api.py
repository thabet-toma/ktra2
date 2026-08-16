"""ملف الاستيراد — الـAPI والترخيص والصلاحيات.

ستّ قواعد يثبتها هذا الملف، وكسر أيٍّ منها يظهر عند المستخدم أو يُسرّب بياناً:

1. **الترخيص يسبق الصلاحية** — شركة بلا ترخيص ترى 404 على كل مسار، لا 403.
   403 يُثبت وجود الوحدة، و404 لا يُثبت شيئاً.
2. **الشركة من الحارس لا من الجسم** — لا صفقة ولا بند ولا مستند من شركة أخرى
   يُقرأ أو يُكتب، ولو مُرّر معرّفه صراحةً.
3. **بند الكتالوج لا يُحذف** — يُعلَّم «غير مطلوب» فيخرج من الحساب ويبقى في
   السجل؛ حذفه كان يعني ملفاً يفقد سؤاله لا جوابه.
4. **المرفق يُحذف من مكانين** — الصف وأصل Cloudinary؛ الاكتفاء بالأول يترك
   blobs يتيمة تُدفع فواتيرها.
5. **الاختياري خارج المقام، والصفّ المشتقّ داخله** — ما يُعرض صفّاً يُحسب.
6. **القراءة والكتابة صلاحيتان** — من يملك العرض وحده يقرأ ولا يكتب.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import TenantModule
from import_file.catalog import DEFAULT_CATALOG, ITEM_TASK
from import_file.models import ImportFileDocument, ImportFileItem
from import_file.services import ensure_file_items
from logistics.models import LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal
from partners.models import Partner
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/import-file/"

MODULE_KEY = "import_file"


class ImportFileApiTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="import-file-api", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة ملف الاستيراد", cls.user)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="المصنع الصيني", partner_type="Supplier",
        )
        cls.deal = cls.make_deal("D-API", cls.tenant, cls.supplier)
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-API",
        )
        LogisticsShipmentDeal.objects.create(shipment=cls.shipment, deal=cls.deal)

    @classmethod
    def make_deal(cls, ref, tenant, supplier):
        return LogisticsDeal.objects.create(
            tenant=tenant, ref_number=ref, partner=supplier,
            order_date="2026-07-01", total_amount=1000, currency=cls.usd,
        )

    def setUp(self):
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key=MODULE_KEY, enabled=True,
        )
        self.client.force_authenticate(user=self.user)

    # ── أدوات ─────────────────────────────────────────────────────────────
    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).TenantID)}

    def open_file(self, deal=None, tenant=None):
        target = deal or self.deal
        return self.client.get(f"{BASE}deals/{target.pk}/file/", **self.headers(tenant))

    def item(self, kind, deal=None, shipment=None):
        anchor = (
            {"shipment": shipment} if shipment is not None
            else {"deal": deal or self.deal}
        )
        return ImportFileItem.objects.get(tenant=self.tenant, kind=kind, **anchor)

    def stage_of(self, payload, stage):
        return next(row for row in payload["stages"] if row["stage"] == stage)

    def row_of(self, payload, stage, kind):
        return next(
            row for row in self.stage_of(payload, stage)["items"] if row["kind"] == kind
        )


# ══════════════════════════════════════════════════════════════════════════
# 1. بوابة الترخيص
# ══════════════════════════════════════════════════════════════════════════

class ModuleGateTest(ImportFileApiTestBase):
    def test_every_route_is_404_without_a_licence(self):
        ensure_file_items(self.deal)
        item = self.item("proforma_invoice")
        document = ImportFileDocument.objects.create(
            tenant=self.tenant, item=item, url="https://res.cloudinary.com/pi.pdf",
        )
        self.license.delete()

        calls = [
            ("get", f"{BASE}deals/{self.deal.pk}/file/", None),
            ("post", f"{BASE}items/", {
                "deal": self.deal.pk, "stage": "deal", "label": "بند مهرَّب",
            }),
            ("patch", f"{BASE}items/{item.pk}/", {"note": "تسريب"}),
            ("delete", f"{BASE}items/{item.pk}/", None),
            ("post", f"{BASE}items/{item.pk}/documents/", {
                "url": "https://res.cloudinary.com/leak.pdf",
            }),
            ("delete", f"{BASE}documents/{document.pk}/", None),
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

        # و404 ليست شكلاً: لا كتابة نفذت من خلفها
        item.refresh_from_db()
        self.assertEqual(item.note, "")
        self.assertTrue(ImportFileDocument.objects.filter(pk=document.pk).exists())
        self.assertEqual(ImportFileDocument.objects.filter(item=item).count(), 1)

    def test_a_licensed_company_opens_the_file(self):
        response = self.open_file()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["deal"]["id"], self.deal.pk)

    def test_the_module_key_reaches_the_permissions_payload_and_the_admin_toggle(self):
        mine = self.client.get("/api/permissions/me/", **self.headers())
        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertTrue(mine.data["modules"][MODULE_KEY])
        self.assertIn("importfile.file.view", mine.data["permissions"])

        root = User.objects.create_superuser(
            username="import-file-root", email="root@example.com", password="x",
        )
        self.client.force_authenticate(user=root)
        rows = self.client.get(f"/api/platform/companies/{self.tenant.pk}/modules/")
        self.assertEqual(rows.status_code, 200, rows.content)
        row = next(r for r in rows.data["results"] if r["module_key"] == MODULE_KEY)
        self.assertEqual(row["label"], "ملف الاستيراد")
        self.assertTrue(row["enabled"])

    def test_an_unlicensed_company_sees_no_import_file_permission(self):
        self.license.delete()

        mine = self.client.get("/api/permissions/me/", **self.headers())

        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertFalse(mine.data["modules"][MODULE_KEY])
        self.assertFalse(
            [key for key in mine.data["permissions"] if key.startswith("importfile.")]
        )


# ══════════════════════════════════════════════════════════════════════════
# 2. عزل الشركات
# ══════════════════════════════════════════════════════════════════════════

class TenantIsolationTest(ImportFileApiTestBase):
    def setUp(self):
        super().setUp()
        self.other = create_company("شركة الجارة", self.user)
        TenantModule.objects.create(
            tenant=self.other, module_key=MODULE_KEY, enabled=True,
        )
        other_supplier = Partner.objects.create(
            tenant=self.other, name="مورّد الجارة", partner_type="Supplier",
        )
        self.other_deal = self.make_deal("D-OTHER", self.other, other_supplier)
        ensure_file_items(self.other_deal)
        self.other_item = ImportFileItem.objects.get(
            tenant=self.other, deal=self.other_deal, kind="proforma_invoice",
        )
        self.other_document = ImportFileDocument.objects.create(
            tenant=self.other, item=self.other_item,
            url="https://res.cloudinary.com/theirs.pdf",
        )

    def test_no_route_reaches_another_companys_file(self):
        calls = [
            ("get", f"{BASE}deals/{self.other_deal.pk}/file/", None),
            ("patch", f"{BASE}items/{self.other_item.pk}/", {"note": "تسريب"}),
            ("delete", f"{BASE}items/{self.other_item.pk}/", None),
            ("post", f"{BASE}items/{self.other_item.pk}/documents/", {
                "url": "https://res.cloudinary.com/leak.pdf",
            }),
            ("delete", f"{BASE}documents/{self.other_document.pk}/", None),
        ]
        for method, url, body in calls:
            with self.subTest(method=method, url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 404, response.content)

        self.other_item.refresh_from_db()
        self.assertEqual(self.other_item.note, "")
        self.assertTrue(ImportFileDocument.objects.filter(pk=self.other_document.pk).exists())

    def test_a_custom_item_cannot_be_anchored_on_another_companys_deal(self):
        response = self.client.post(
            f"{BASE}items/",
            {
                "deal": self.other_deal.pk, "stage": "deal",
                "label": "بند مزروع في شركة أخرى",
            },
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(
            ImportFileItem.objects.filter(deal=self.other_deal, label__startswith="بند مزروع").exists()
        )

    def test_a_custom_item_cannot_be_anchored_on_another_companys_shipment(self):
        foreign_shipment = LogisticsShipment.objects.create(
            tenant=self.other, shipment_number="SH-OTHER",
        )

        response = self.client.post(
            f"{BASE}items/",
            {
                "shipment": foreign_shipment.pk, "stage": "shipment",
                "label": "بند على شحنة غريبة",
            },
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(ImportFileItem.objects.filter(shipment=foreign_shipment).exists())


# ══════════════════════════════════════════════════════════════════════════
# 3. بنود الملف
# ══════════════════════════════════════════════════════════════════════════

class ItemCrudTest(ImportFileApiTestBase):
    def setUp(self):
        super().setUp()
        self.open_file()  # التزريع يقع عند الفتح

    def create_custom(self, **overrides):
        body = {
            "deal": self.deal.pk, "stage": "deal", "item_type": "task",
            "label": "اتّصل بالمخلّص قبل الوصول",
        }
        body.update(overrides)
        return self.client.post(f"{BASE}items/", body, format="json", **self.headers())

    def test_a_custom_item_is_created_on_the_active_company_and_marked_custom(self):
        response = self.create_custom()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.data["is_custom"])
        self.assertFalse(response.data["derived"])
        row = ImportFileItem.objects.get(pk=response.data["id"])
        self.assertEqual(row.tenant_id, self.tenant.pk)
        self.assertEqual(row.deal_id, self.deal.pk)
        self.assertEqual(row.created_by_id, self.user.pk)
        self.assertNotIn(row.kind, {entry.kind for entry in DEFAULT_CATALOG})

    def test_an_item_with_no_anchor_or_with_both_is_rejected(self):
        for body in (
            {"stage": "deal", "label": "بلا مرساة"},
            {
                "deal": self.deal.pk, "shipment": self.shipment.pk,
                "stage": "deal", "label": "بمرساتين",
            },
        ):
            with self.subTest(body=body):
                response = self.client.post(
                    f"{BASE}items/", body, format="json", **self.headers(),
                )
                self.assertEqual(response.status_code, 400, response.content)

    def test_a_task_is_marked_done_and_a_document_item_refuses_the_flag(self):
        task = self.item("task_match_datasheet")
        marked = self.client.patch(
            f"{BASE}items/{task.pk}/", {"done": True}, format="json", **self.headers(),
        )
        self.assertEqual(marked.status_code, 200, marked.content)
        self.assertTrue(marked.data["is_done"])

        # بند المستند يكتمل بمرفقه — علامةٌ يدوية عليه تكذب على قارئ الملف
        document_item = self.item("proforma_invoice")
        refused = self.client.patch(
            f"{BASE}items/{document_item.pk}/", {"done": True},
            format="json", **self.headers(),
        )
        self.assertEqual(refused.status_code, 400, refused.content)
        document_item.refresh_from_db()
        self.assertFalse(document_item.done)

    def test_only_a_custom_item_may_be_renamed(self):
        custom = self.create_custom()
        renamed = self.client.patch(
            f"{BASE}items/{custom.data['id']}/", {"label": "اسم جديد"},
            format="json", **self.headers(),
        )
        self.assertEqual(renamed.status_code, 200, renamed.content)
        self.assertEqual(renamed.data["label"], "اسم جديد")

        catalog_item = self.item("proforma_invoice")
        refused = self.client.patch(
            f"{BASE}items/{catalog_item.pk}/", {"label": "الفاتورة المبدئية??"},
            format="json", **self.headers(),
        )
        self.assertEqual(refused.status_code, 400, refused.content)
        catalog_item.refresh_from_db()
        self.assertEqual(catalog_item.label, "الفاتورة المبدئية (PI)")

    def test_note_and_required_are_editable_on_a_catalog_item(self):
        catalog_item = self.item("datasheet")

        response = self.client.patch(
            f"{BASE}items/{catalog_item.pk}/", {"required": False, "note": "المورد أرسلها بالإيميل"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        catalog_item.refresh_from_db()
        self.assertFalse(catalog_item.required)
        self.assertEqual(catalog_item.note, "المورد أرسلها بالإيميل")

    def test_a_custom_item_is_deleted_and_a_catalog_item_never_is(self):
        custom = self.create_custom()
        removed = self.client.delete(
            f"{BASE}items/{custom.data['id']}/", **self.headers(),
        )
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(ImportFileItem.objects.filter(pk=custom.data["id"]).exists())

        catalog_item = self.item("proforma_invoice")
        refused = self.client.delete(
            f"{BASE}items/{catalog_item.pk}/", **self.headers(),
        )
        self.assertEqual(refused.status_code, 400, refused.content)
        self.assertTrue(ImportFileItem.objects.filter(pk=catalog_item.pk).exists())


# ══════════════════════════════════════════════════════════════════════════
# 4. المرفقات
# ══════════════════════════════════════════════════════════════════════════

class DocumentTest(ImportFileApiTestBase):
    def setUp(self):
        super().setUp()
        self.open_file()

    def attach(self, item, url="https://res.cloudinary.com/ktra/pi.pdf"):
        return self.client.post(
            f"{BASE}items/{item.pk}/documents/",
            {
                "url": url, "filename": "pi.pdf",
                "mime_type": "application/pdf", "size_bytes": 2048,
            },
            format="json", **self.headers(),
        )

    def test_attaching_a_document_completes_its_item(self):
        item = self.item("proforma_invoice")

        response = self.attach(item)

        self.assertEqual(response.status_code, 201, response.content)
        document = ImportFileDocument.objects.get(pk=response.data["id"])
        self.assertEqual(document.tenant_id, self.tenant.pk)
        self.assertEqual(document.uploaded_by_id, self.user.pk)
        row = self.row_of(self.open_file().data, "deal", "proforma_invoice")
        self.assertTrue(row["is_done"])
        self.assertEqual(len(row["documents"]), 1)

    def test_an_attachment_without_a_url_is_rejected(self):
        response = self.client.post(
            f"{BASE}items/{self.item('proforma_invoice').pk}/documents/",
            {"filename": "pi.pdf"}, format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_deleting_a_document_destroys_its_cloudinary_asset_too(self):
        item = self.item("proforma_invoice")
        document = ImportFileDocument.objects.get(pk=self.attach(item).data["id"])

        with patch("import_file.views.destroy_cloudinary_asset") as destroy:
            response = self.client.delete(
                f"{BASE}documents/{document.pk}/", **self.headers(),
            )

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(ImportFileDocument.objects.filter(pk=document.pk).exists())
        destroy.assert_called_once_with("https://res.cloudinary.com/ktra/pi.pdf")
        row = self.row_of(self.open_file().data, "deal", "proforma_invoice")
        self.assertFalse(row["is_done"])


# ══════════════════════════════════════════════════════════════════════════
# 5. حمولة الملف — الصفّ المشتقّ ورياضيات الاكتمال
# ══════════════════════════════════════════════════════════════════════════

class FilePayloadTest(ImportFileApiTestBase):
    SHIPMENT_REQUIRED = ["bill_of_lading", "packing_list", "commercial_invoice"]

    def test_opening_the_file_seeds_it_once_and_groups_it_by_stage(self):
        first = self.open_file()
        second = self.open_file()

        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(
            [row["stage"] for row in first.data["stages"]],
            ["offer", "deal", "shipment", "clearance"],
        )
        self.assertEqual(
            ImportFileItem.objects.filter(tenant=self.tenant).count(),
            len(DEFAULT_CATALOG),
            "فتح الملف مرتين ضاعف بنوده",
        )
        self.assertEqual(first.data["progress"], second.data["progress"])
        self.assertEqual(first.data["shipment"]["id"], self.shipment.pk)

    def test_the_freight_rate_row_is_derived_visible_and_counted(self):
        row = self.row_of(self.open_file().data, "shipment", "freight_rate")

        self.assertTrue(row["derived"])
        self.assertIsNone(row["id"])
        self.assertFalse(row["is_done"])
        # الصفّ المشتقّ لا يُخزَّن: يُعرض ولا يُنشئ بنداً
        self.assertFalse(ImportFileItem.objects.filter(kind="freight_rate").exists())

        stage = self.stage_of(self.open_file().data, "shipment")
        self.assertEqual(
            stage["progress"],
            {"done": 0, "total": len(self.SHIPMENT_REQUIRED) + 1},
            "الصفّ المشتقّ يُعرض صفّاً مطلوباً فيجب أن يدخل المقام",
        )

        self.shipment.freight_rate = 12
        self.shipment.save(update_fields=["freight_rate"])
        payload = self.open_file().data
        self.assertTrue(self.row_of(payload, "shipment", "freight_rate")["is_done"])
        self.assertEqual(
            self.stage_of(payload, "shipment")["progress"],
            {"done": 1, "total": len(self.SHIPMENT_REQUIRED) + 1},
        )

    def test_an_unmarked_optional_item_stays_out_of_the_denominator(self):
        self.open_file()  # التزريع يقع عند الفتح
        self.shipment.freight_rate = 12
        self.shipment.save(update_fields=["freight_rate"])
        for kind in self.SHIPMENT_REQUIRED:
            ImportFileDocument.objects.create(
                tenant=self.tenant, item=self.item(kind, shipment=self.shipment),
                url=f"https://res.cloudinary.com/{kind}.pdf",
            )

        stage = self.stage_of(self.open_file().data, "shipment")

        # الاختيارية الثلاث معروضة ولا تُنزل ملفاً مكتمل الأوراق دون ١٠٠٪
        self.assertEqual(len(stage["items"]), 7)
        self.assertEqual(
            stage["progress"],
            {"done": len(self.SHIPMENT_REQUIRED) + 1, "total": len(self.SHIPMENT_REQUIRED) + 1},
        )

        # وحين يعلّمها المستخدم مطلوبة تدخل المقام فوراً
        optional = self.item("certificate_of_origin", shipment=self.shipment)
        self.client.patch(
            f"{BASE}items/{optional.pk}/", {"required": True},
            format="json", **self.headers(),
        )
        self.assertEqual(
            self.stage_of(self.open_file().data, "shipment")["progress"],
            {"done": len(self.SHIPMENT_REQUIRED) + 1, "total": len(self.SHIPMENT_REQUIRED) + 2},
        )

    def test_a_deal_without_a_shipment_shows_neither_shipment_rows_nor_the_derived_row(self):
        solo = self.make_deal("D-SOLO", self.tenant, self.supplier)

        payload = self.open_file(deal=solo).data

        self.assertIsNone(payload["shipment"])
        self.assertEqual([row["stage"] for row in payload["stages"]], ["offer", "deal"])

    def test_the_task_rows_carry_their_type_so_the_screen_can_tell_them_apart(self):
        row = self.row_of(self.open_file().data, "deal", "task_match_datasheet")

        self.assertEqual(row["item_type"], ITEM_TASK)
        self.assertFalse(row["required"])


# ══════════════════════════════════════════════════════════════════════════
# 6. الصلاحيتان
# ══════════════════════════════════════════════════════════════════════════

class PermissionTest(ImportFileApiTestBase):
    def setUp(self):
        super().setUp()
        self.open_file()
        self.reader = User.objects.create_user(username="import-file-reader", password="x")
        UserCompanyMembership.objects.create(
            user=self.reader, tenant=self.tenant, role="accountant",
        )
        self.client.force_authenticate(user=self.reader)

    def test_a_view_only_user_reads_the_file(self):
        response = self.open_file()

        self.assertEqual(response.status_code, 200, response.content)

    def test_a_view_only_user_writes_nothing(self):
        item = self.item("proforma_invoice")
        calls = [
            ("post", f"{BASE}items/", {
                "deal": self.deal.pk, "stage": "deal", "label": "بند بلا صلاحية",
            }),
            ("patch", f"{BASE}items/{item.pk}/", {"note": "بلا صلاحية"}),
            ("delete", f"{BASE}items/{item.pk}/", None),
            ("post", f"{BASE}items/{item.pk}/documents/", {
                "url": "https://res.cloudinary.com/x.pdf",
            }),
        ]
        for method, url, body in calls:
            with self.subTest(method=method, url=url):
                call = getattr(self.client, method)
                response = (
                    call(url, body, format="json", **self.headers())
                    if body is not None else call(url, **self.headers())
                )
                self.assertEqual(response.status_code, 403, response.content)

        item.refresh_from_db()
        self.assertEqual(item.note, "")

    def test_the_procurement_employee_manages_the_file(self):
        buyer = User.objects.create_user(username="import-file-buyer", password="x")
        UserCompanyMembership.objects.create(
            user=buyer, tenant=self.tenant, role="procurement",
        )
        self.client.force_authenticate(user=buyer)

        response = self.client.post(
            f"{BASE}items/",
            {"deal": self.deal.pk, "stage": "deal", "label": "أرسل نسخة للمخلّص"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 201, response.content)
