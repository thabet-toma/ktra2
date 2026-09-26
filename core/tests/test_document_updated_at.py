"""ختمُ «آخر تعديل» على سبعة نماذج تحرّرها شاشاتٌ بمسودّةٍ محلّيّة.

`useDocumentDraft` (`frontend_v2/hooks/useDocumentDraft.ts`) يقارن ختمَ المستند
لحظةَ بدء المسودّة بختمه الحاليّ ليقول «تغيّر المستند بعد مسودّتك» (#109 §٩).
سبعُ شاشاتٍ كانت تمرّر `docUpdatedAt: null` لأن نماذجها بلا `updated_at` —
فكان الفحصُ معطّلاً عندها بصمت. هذا الملف يحرس الطرف الخادميّ: الحفظ يحرّك
الختم، والمُسلسِل الذي تقرؤه الشاشة يكشفه، وهجرةُ الملء تنسخ `created_at`.
"""
import datetime
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from accounting.models import JournalHeader
from accounting.serializers import JournalHeaderListSerializer, JournalHeaderSerializer
from inventory.models import Product, Stocktake
from inventory.serializers import ProductSerializer, StocktakeSerializer
from logistics.models import GoodsReceipt
from logistics.serializers import GoodsReceiptSerializer
from partners.models import Partner
from partners.serializers import PartnerListSerializer, PartnerSerializer
from sales.models import CreditDebitNote, DeliveryOrder
from sales.serializers import CreditDebitNoteSerializer, DeliveryOrderSerializer
from tenants.models import Currency
from tenants.services import create_company

TODAY = datetime.date(2026, 6, 15)


class DocumentUpdatedAtTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.user = User.objects.create_user(username="stamp-owner", password="x")
        cls.tenant = create_company("شركة الأختام", cls.user)

    def _instances(self):
        partner = Partner.objects.create(
            tenant=self.tenant, name="طرف الختم", partner_type="Customer",
        )
        return {
            "partner": partner,
            "product": Product.objects.create(
                tenant=self.tenant, sku="STAMP-1", name_ar="صنف الختم",
            ),
            "stocktake": Stocktake.objects.create(
                tenant=self.tenant, stocktake_date=TODAY,
            ),
            "goods_receipt": GoodsReceipt.objects.create(
                tenant=self.tenant, receipt_number="GR-STAMP", receipt_date=TODAY,
                partner=partner,
            ),
            "delivery_order": DeliveryOrder.objects.create(
                tenant=self.tenant, delivery_number="DO-STAMP", delivery_date=TODAY,
                partner=partner,
            ),
            "credit_debit_note": CreditDebitNote.objects.create(
                tenant=self.tenant, note_number="CN-STAMP", note_date=TODAY,
                note_type=CreditDebitNote.TYPE_CREDIT, partner=partner,
                amount=Decimal("10"),
            ),
            "journal_header": JournalHeader.objects.create(
                tenant=self.tenant, transaction_date=TODAY, description="قيد الختم",
            ),
        }

    def test_saving_moves_the_stamp_on_all_seven_models(self):
        old = timezone.now() - datetime.timedelta(days=3)
        edits = {
            "partner": ("name", "طرف معدَّل"),
            "product": ("name_ar", "صنف معدَّل"),
            "stocktake": ("notes", "ملاحظة"),
            "goods_receipt": ("notes", "ملاحظة"),
            "delivery_order": ("notes", "ملاحظة"),
            "credit_debit_note": ("reason", "سبب"),
            "journal_header": ("description", "وصف معدَّل"),
        }
        for key, obj in self._instances().items():
            with self.subTest(model=key):
                self.assertIsNotNone(obj.updated_at)
                type(obj).objects.filter(pk=obj.pk).update(updated_at=old)
                obj.refresh_from_db()
                self.assertEqual(obj.updated_at, old)

                field, value = edits[key]
                setattr(obj, field, value)
                obj.save()
                obj.refresh_from_db()
                self.assertGreater(obj.updated_at, old)

    def test_writes_that_bypass_save_still_move_the_stamp(self):
        """`.update()` و`bulk_update` لا يمرّان بـ`auto_now` — الكاتبُ يختم صراحةً."""
        from inventory.models import ProductFamily
        from inventory.services import _push_family_fields_to_siblings

        old = timezone.now() - datetime.timedelta(days=3)
        family = ProductFamily.objects.create(tenant=self.tenant, name_ar="أب")
        sibling = Product.objects.create(
            tenant=self.tenant, sku="SIB-1", name_ar="قديم", family=family,
        )
        edited = Product.objects.create(
            tenant=self.tenant, sku="SIB-2", name_ar="قديم", family=family,
        )
        Product.objects.filter(pk=sibling.pk).update(updated_at=old)
        family.name_ar = "جديد"
        _push_family_fields_to_siblings(family, exclude_id=edited.pk, fields=["name_ar"])
        sibling.refresh_from_db()
        self.assertEqual(sibling.name_ar, "جديد")
        self.assertGreater(sibling.updated_at, old)

        Product.objects.filter(pk=sibling.pk).update(updated_at=old)
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/inventory/products/bulk-set-group/",
            {"product_ids": [sibling.pk], "brand": "براند"},
            content_type="application/json",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )
        self.assertEqual(response.status_code, 200, response.content)
        sibling.refresh_from_db()
        self.assertEqual(sibling.brand, "براند")
        self.assertGreater(sibling.updated_at, old)

    def test_the_serializers_the_screens_read_expose_the_stamp(self):
        objs = self._instances()
        pairs = [
            (PartnerSerializer, objs["partner"]),
            (PartnerListSerializer, objs["partner"]),
            (ProductSerializer, objs["product"]),
            (StocktakeSerializer, objs["stocktake"]),
            (GoodsReceiptSerializer, objs["goods_receipt"]),
            (DeliveryOrderSerializer, objs["delivery_order"]),
            (CreditDebitNoteSerializer, objs["credit_debit_note"]),
            (JournalHeaderSerializer, objs["journal_header"]),
            (JournalHeaderListSerializer, objs["journal_header"]),
        ]
        for serializer_class, obj in pairs:
            with self.subTest(serializer=serializer_class.__name__):
                data = serializer_class(obj).data
                self.assertIn("updated_at", data)
                self.assertTrue(data["updated_at"])
                # ختمٌ يكتبه الخادم وحده — حمولةٌ تحمله لا تُزوِّره.
                self.assertTrue(serializer_class().fields["updated_at"].read_only)

    def test_fill_migrations_copy_created_at_into_existing_rows(self):
        objs = self._instances()
        stamp = timezone.now() + datetime.timedelta(days=5)
        migrations = {
            "sales": ["delivery_order", "credit_debit_note"],
            "logistics": ["goods_receipt"],
            "inventory": ["product", "stocktake"],
            "partners": ["partner"],
        }
        for key in [k for keys in migrations.values() for k in keys]:
            type(objs[key]).objects.filter(pk=objs[key].pk).update(updated_at=stamp)

        for app_label in migrations:
            module = importlib.import_module(MIGRATION_MODULES[app_label])
            module.copy_created_at_into_updated_at(django_apps, None)

        for key in [k for keys in migrations.values() for k in keys]:
            with self.subTest(model=key):
                obj = objs[key]
                obj.refresh_from_db()
                self.assertEqual(obj.updated_at, obj.created_at)


#: هجراتُ الملء — `JournalHeader` خارجها عمداً: لا `created_at` عليه أصلاً،
#: فصفوفه القائمة تبقى بلحظة الهجرة (`accounting/migrations/0045_updated_at_stamp.py`).
MIGRATION_MODULES = {
    "sales": "sales.migrations.0044_updated_at_stamp",
    "logistics": "logistics.migrations.0087_updated_at_stamp",
    "inventory": "inventory.migrations.0036_updated_at_stamp",
    "partners": "partners.migrations.0016_updated_at_stamp",
}
