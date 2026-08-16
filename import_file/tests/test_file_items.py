"""ملف الاستيراد — طبقة البيانات: الكتالوج، التزريع، العزل، المرساة، الاكتمال.

خمس قواعد يثبتها هذا الملف، وكلٌّ منها كسرها يظهر عند المستخدم لا في سجلّ:

1. **التزريع idempotent** — الملف يُزرَع عند كل فتح، ففتحه مرتين يجب ألّا يضاعف
   بنداً واحداً.
2. **عزل الشركات** — صفقة شركة أخرى لا تُرجع بند هذه الشركة أبداً.
3. **المرساة واحدة بالضبط** — القيد يرفض الفارغتين والمملوءتين معاً، في قاعدة
   البيانات لا في نيّة الكود.
4. **بند الشحنة صفّ واحد تتقاسمه صفقات الشحنة** — رفعة B/L واحدة تُكمل ملفَّي
   صفقتين على الشحنة نفسها. تكراره لكل صفقة كان يعني رفعاً مكرراً ونسخاً
   متضاربة لوثيقةٍ واحدة.
5. **الاختياري خارج المقام** — بندٌ لم يعلّمه المستخدم مطلوباً لا يخفض نسبة
   الاكتمال.
"""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase

from import_file.catalog import (
    ANCHOR_DEAL,
    ANCHOR_SHIPMENT,
    DEFAULT_CATALOG,
    ITEM_DOCUMENT,
    ITEM_TASK,
    STAGE_KEYS,
)
from import_file.models import ImportFileDocument, ImportFileItem
from import_file.services import (
    ensure_file_items,
    file_items_for_deal,
    stage_progress,
)
from logistics.models import LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


# ══════════════════════════════════════════════════════════════════════════
# الكتالوج — بيانات صرفة، بلا قاعدة بيانات
# ══════════════════════════════════════════════════════════════════════════

def test_catalog_holds_twelve_documents_and_two_tasks():
    documents = [e for e in DEFAULT_CATALOG if e.item_type == ITEM_DOCUMENT]
    tasks = [e for e in DEFAULT_CATALOG if e.item_type == ITEM_TASK]
    assert len(documents) == 12
    assert len(tasks) == 2
    # المهمّة اقتراحُ عملٍ لا وثيقةٌ تُطلب — إلزامها يجعل الملف ناقصاً بلا سبب.
    assert all(not task.required for task in tasks)


def test_catalog_speaks_the_journey_vocabulary_and_repeats_no_kind():
    kinds = [entry.kind for entry in DEFAULT_CATALOG]
    assert len(kinds) == len(set(kinds)), "تكرار `kind` يجعل التزريع يبلع بنداً"
    assert all(entry.stage in STAGE_KEYS for entry in DEFAULT_CATALOG)
    assert all(entry.anchor in (ANCHOR_DEAL, ANCHOR_SHIPMENT) for entry in DEFAULT_CATALOG)
    assert all(entry.label.strip() for entry in DEFAULT_CATALOG)


# ══════════════════════════════════════════════════════════════════════════
# التزريع والعزل والمرساة والاكتمال — مع قاعدة بيانات
# ══════════════════════════════════════════════════════════════════════════

DEAL_ANCHORED = [e for e in DEFAULT_CATALOG if e.anchor == ANCHOR_DEAL]
SHIPMENT_ANCHORED = [e for e in DEFAULT_CATALOG if e.anchor == ANCHOR_SHIPMENT]


class ImportFileSeedingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="import-file", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة ملف الاستيراد", cls.user)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="المصنع الصيني", partner_type="Supplier",
        )

    def _deal(self, ref, tenant=None, supplier=None):
        return LogisticsDeal.objects.create(
            tenant=tenant or self.tenant, ref_number=ref,
            partner=supplier or self.supplier, order_date="2026-07-01",
            total_amount=1000, currency=self.usd,
        )

    def _shipment(self, number, tenant=None):
        return LogisticsShipment.objects.create(
            tenant=tenant or self.tenant, shipment_number=number,
        )

    # ── 1. التزريع ────────────────────────────────────────────────────────
    def test_seeding_a_deal_without_a_shipment_creates_only_deal_rows(self):
        deal = self._deal("D-SOLO")
        ensure_file_items(deal)
        items = list(file_items_for_deal(deal))
        self.assertEqual(len(items), len(DEAL_ANCHORED))
        self.assertTrue(all(item.shipment_id is None for item in items))
        self.assertEqual(
            {item.kind for item in items}, {e.kind for e in DEAL_ANCHORED},
        )

    def test_seeding_is_idempotent_and_picks_up_a_shipment_joined_later(self):
        deal = self._deal("D-IDEM")
        ensure_file_items(deal)
        ensure_file_items(deal)
        self.assertEqual(file_items_for_deal(deal).count(), len(DEAL_ANCHORED))

        # الصفقة تنضمّ لشحنة بعد أن فُتح ملفها — بنود الشحنة تظهر، ولا تتكرّر
        # بنود الصفقة. تزريعٌ لمرّةٍ عند الإنشاء كان سيترك هذا الملف ناقصاً أبداً.
        shipment = self._shipment("SH-IDEM")
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        ensure_file_items(deal)
        ensure_file_items(deal)
        items = list(file_items_for_deal(deal))
        self.assertEqual(len(items), len(DEFAULT_CATALOG))
        self.assertEqual(len({item.kind for item in items}), len(DEFAULT_CATALOG))

    # ── 2. العزل ──────────────────────────────────────────────────────────
    def test_another_tenants_deal_never_yields_this_tenants_items(self):
        deal = self._deal("D-MINE")
        ensure_file_items(deal)

        other_user = User.objects.create_user(username="import-file-other", password="x")
        other_tenant = create_company("شركة أخرى", other_user)
        other_supplier = Partner.objects.create(
            tenant=other_tenant, name="مورّد آخر", partner_type="Supplier",
        )
        other_deal = self._deal("D-THEIRS", tenant=other_tenant, supplier=other_supplier)
        ensure_file_items(other_deal)

        mine = set(file_items_for_deal(deal).values_list("id", flat=True))
        theirs = set(file_items_for_deal(other_deal).values_list("id", flat=True))
        self.assertTrue(mine and theirs)
        self.assertFalse(mine & theirs)
        self.assertEqual(
            set(
                ImportFileItem.objects.filter(id__in=theirs)
                .values_list("tenant_id", flat=True)
            ),
            {other_tenant.pk},
        )

    def test_a_shipment_of_another_tenant_is_not_read_as_this_deals_shipment(self):
        """الصفقة تحمل شركتها؛ الشحنة تُقرأ مفلترةً بها لا بمعرّف الربط وحده."""
        deal = self._deal("D-XT")
        other_user = User.objects.create_user(username="import-file-xt", password="x")
        other_tenant = create_company("شركة الشحنة الغريبة", other_user)
        foreign_shipment = self._shipment("SH-XT", tenant=other_tenant)
        LogisticsShipmentDeal.objects.create(shipment=foreign_shipment, deal=deal)

        ensure_file_items(deal)
        items = list(file_items_for_deal(deal))
        self.assertEqual(len(items), len(DEAL_ANCHORED))
        self.assertTrue(all(item.shipment_id is None for item in items))

    # ── 3. المرساة الواحدة ────────────────────────────────────────────────
    def test_exactly_one_anchor_is_enforced_by_the_database(self):
        deal = self._deal("D-ANCHOR")
        shipment = self._shipment("SH-ANCHOR")
        base = dict(
            tenant=self.tenant, stage="deal", item_type=ITEM_DOCUMENT,
            kind="anchor_probe", label="بند اختبار", required=True,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ImportFileItem.objects.create(deal=None, shipment=None, **base)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ImportFileItem.objects.create(deal=deal, shipment=shipment, **base)
        # ومرساةٌ واحدة تمرّ — القيد يمنع الخطأ لا الاستعمال الصحيح.
        ImportFileItem.objects.create(deal=deal, shipment=None, **base)

    # ── 4. صفّ الشحنة مشترك ───────────────────────────────────────────────
    def test_one_shipment_row_serves_every_deal_on_that_shipment(self):
        shipment = self._shipment("SH-SHARED")
        first = self._deal("D-A")
        second = self._deal("D-B")
        for deal in (first, second):
            LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
            ensure_file_items(deal)

        bol = ImportFileItem.objects.filter(
            tenant=self.tenant, shipment=shipment, kind="bill_of_lading",
        )
        self.assertEqual(bol.count(), 1, "بوليصة الشحن وثيقة شحنة — صفٌّ واحد لا صفّ لكل صفقة")

        # رفعة واحدة تُكمل البند في ملفَّي الصفقتين معاً
        ImportFileDocument.objects.create(
            tenant=self.tenant, item=bol.get(), url="https://res.cloudinary.com/bl.pdf",
            filename="bl.pdf", mime_type="application/pdf", size_bytes=1024,
        )
        for deal in (first, second):
            row = next(
                item for item in file_items_for_deal(deal)
                if item.kind == "bill_of_lading"
            )
            self.assertTrue(row.is_done)

    # ── 5. رياضيات الاكتمال ───────────────────────────────────────────────
    def test_an_unmarked_optional_item_stays_out_of_the_denominator(self):
        shipment = self._shipment("SH-PROGRESS")
        deal = self._deal("D-PROGRESS")
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        ensure_file_items(deal)

        required_kinds = [
            e.kind for e in SHIPMENT_ANCHORED if e.stage == "shipment" and e.required
        ]
        optional_kinds = [
            e.kind for e in SHIPMENT_ANCHORED if e.stage == "shipment" and not e.required
        ]
        self.assertTrue(required_kinds and optional_kinds)

        for kind in required_kinds:
            item = ImportFileItem.objects.get(
                tenant=self.tenant, shipment=shipment, kind=kind,
            )
            ImportFileDocument.objects.create(
                tenant=self.tenant, item=item, url=f"https://res.cloudinary.com/{kind}.pdf",
                filename=f"{kind}.pdf", mime_type="application/pdf", size_bytes=10,
            )

        progress = stage_progress(file_items_for_deal(deal))
        self.assertEqual(
            progress["shipment"], {"done": len(required_kinds), "total": len(required_kinds)},
            "الاختيارية الثلاث دخلت المقام فأنزلت ملفاً مكتملاً دون ١٠٠٪",
        )

        # وحين يعلّم المستخدم واحداً منها مطلوباً، يدخل المقام فوراً
        ImportFileItem.objects.filter(
            tenant=self.tenant, shipment=shipment, kind=optional_kinds[0],
        ).update(required=True)
        progress = stage_progress(file_items_for_deal(deal))
        self.assertEqual(
            progress["shipment"],
            {"done": len(required_kinds), "total": len(required_kinds) + 1},
        )

    def test_a_task_is_done_by_its_flag_and_a_document_row_by_its_upload(self):
        deal = self._deal("D-TASK")
        ensure_file_items(deal)
        task = ImportFileItem.objects.get(
            tenant=self.tenant, deal=deal, item_type=ITEM_TASK, stage="deal",
        )
        self.assertFalse(task.is_done)
        task.done = True
        task.save(update_fields=["done"])
        self.assertTrue(ImportFileItem.objects.get(pk=task.pk).is_done)

        document_item = ImportFileItem.objects.get(
            tenant=self.tenant, deal=deal, kind="proforma_invoice",
        )
        # علمُ `done` لا يُقرأ لبند مستند — الحقيقة مرفقُه، لا زرٌّ يُضغط.
        document_item.done = True
        document_item.save(update_fields=["done"])
        self.assertFalse(ImportFileItem.objects.get(pk=document_item.pk).is_done)
        ImportFileDocument.objects.create(
            tenant=self.tenant, item=document_item, url="https://res.cloudinary.com/pi.pdf",
            filename="pi.pdf", mime_type="application/pdf", size_bytes=99,
        )
        self.assertTrue(ImportFileItem.objects.get(pk=document_item.pk).is_done)
