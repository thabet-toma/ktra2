"""اختبارات كتالوج وحدات الخدمة بنسخٍ مؤرَّخة (التذكرة 210-C، القصص ١٦-١٨).

تغطي:
1. مسودة جديدة بلا بنود، تعديل البنود، ورفض تعديل نسخة مفعّلة أو منتهية.
2. رفض تفعيل كتالوج بلا بنود (القصة ١٨) وبلا سبب.
3. التفعيل يمنع التداخل ويُنهي النسخة السابقة عند تاريخ سريان الجديدة.
4. الاستنساخ إلى مسودة جديدة ينسخ البنود.
5. `get_active_service_unit_catalog` يعكس `effective_state` لا `status` وحده.
6. طول عمود choices جديد يتّسع لأطول مفتاح.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from platform_ops.models import ServiceDocumentType, ServiceUnitCatalog, ServiceUnitCatalogEntry
from platform_ops.services import (
    ServiceUnitCatalogConflict,
    ServiceUnitCatalogError,
    activate_service_unit_catalog,
    clone_service_unit_catalog_to_draft,
    create_service_unit_catalog_draft,
    get_active_service_unit_catalog,
    update_service_unit_catalog_entries,
)

User = get_user_model()


class ServiceUnitCatalogTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="catalog_admin", email="ca@platform.local", password="x")

    def _entries(self, **overrides):
        base = {
            "document_type": ServiceDocumentType.SALES_INVOICE,
            "base_units": Decimal("1.00"),
            "per_line_weight": Decimal("0.50"),
        }
        base.update(overrides)
        return [base]

    def test_draft_created_without_entries(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        self.assertEqual(draft.status, ServiceUnitCatalog.Status.DRAFT)
        self.assertEqual(draft.entries.count(), 0)
        self.assertEqual(draft.version, 1)

    def test_second_draft_gets_next_version(self):
        create_service_unit_catalog_draft(actor=self.admin)
        second = create_service_unit_catalog_draft(actor=self.admin)
        self.assertEqual(second.version, 2)

    def test_update_entries_replaces_batch_and_rejects_duplicates(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        updated = update_service_unit_catalog_entries(
            catalog=draft, entries=self._entries(), actor=self.admin,
        )
        self.assertEqual(updated.entries.count(), 1)
        entry = updated.entries.first()
        self.assertEqual(entry.base_units, Decimal("1.00"))
        self.assertEqual(entry.per_line_weight, Decimal("0.5000"))

        with self.assertRaises(ServiceUnitCatalogError) as ctx:
            update_service_unit_catalog_entries(
                catalog=draft,
                entries=[
                    {"document_type": ServiceDocumentType.SALES_INVOICE},
                    {"document_type": ServiceDocumentType.SALES_INVOICE},
                ],
                actor=self.admin,
            )
        self.assertEqual(ctx.exception.code, "duplicate_document_type")

    def test_update_entries_rejects_invalid_document_type(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        with self.assertRaises(ServiceUnitCatalogError) as ctx:
            update_service_unit_catalog_entries(
                catalog=draft, entries=[{"document_type": "not_a_real_type"}], actor=self.admin,
            )
        self.assertEqual(ctx.exception.code, "invalid_document_type")

    def test_update_entries_rejects_negative_values(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        with self.assertRaises(ServiceUnitCatalogError):
            update_service_unit_catalog_entries(
                catalog=draft,
                entries=self._entries(base_units=Decimal("-1.00")),
                actor=self.admin,
            )

    def test_activate_rejects_empty_catalog(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        with self.assertRaises(ServiceUnitCatalogError) as ctx:
            activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="بدء الـpilot")
        self.assertEqual(ctx.exception.code, "catalog_empty")

    def test_activate_requires_reason(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(catalog=draft, entries=self._entries(), actor=self.admin)
        with self.assertRaises(ServiceUnitCatalogError) as ctx:
            activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="")
        self.assertEqual(ctx.exception.code, "activation_reason_required")

    def test_activate_succeeds_and_is_current(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(catalog=draft, entries=self._entries(), actor=self.admin)
        activated = activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="بدء الـpilot")
        self.assertEqual(activated.status, ServiceUnitCatalog.Status.ACTIVE)
        self.assertEqual(activated.effective_state(), "current")
        self.assertEqual(get_active_service_unit_catalog().pk, activated.pk)

    def test_cannot_activate_twice(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(catalog=draft, entries=self._entries(), actor=self.admin)
        activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="بدء الـpilot")
        with self.assertRaises(ServiceUnitCatalogConflict) as ctx:
            activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="محاولة ثانية")
        self.assertEqual(ctx.exception.code, "catalog_not_draft")

    def test_cannot_update_entries_after_activation(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(catalog=draft, entries=self._entries(), actor=self.admin)
        activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="بدء الـpilot")
        with self.assertRaises(ServiceUnitCatalogConflict) as ctx:
            update_service_unit_catalog_entries(catalog=draft, entries=self._entries(), actor=self.admin)
        self.assertEqual(ctx.exception.code, "catalog_immutable")

    def test_activating_new_version_retires_previous_at_effective_from(self):
        first = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(catalog=first, entries=self._entries(), actor=self.admin)
        activate_service_unit_catalog(catalog=first, actor=self.admin, activation_reason="v1")

        second = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(
            catalog=second, entries=self._entries(base_units=Decimal("2.00")), actor=self.admin,
        )
        later = timezone.now() + timedelta(days=1)
        activate_service_unit_catalog(catalog=second, actor=self.admin, activation_reason="v2", effective_from=later)

        first.refresh_from_db()
        self.assertEqual(first.effective_to, later)
        # النسخة الأولى تبقى «نشطة» بالحالة لكن غير حاليّة بعد تفعيل نسخةٍ لاحقة مجدولة
        self.assertEqual(first.effective_state(later + timedelta(minutes=1)), "retired")
        self.assertEqual(get_active_service_unit_catalog().pk, first.pk)
        self.assertEqual(get_active_service_unit_catalog(at=later + timedelta(minutes=1)).pk, second.pk)

    def test_clone_copies_entries_into_new_draft(self):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(catalog=draft, entries=self._entries(), actor=self.admin)
        activated = activate_service_unit_catalog(catalog=draft, actor=self.admin, activation_reason="v1")

        cloned = clone_service_unit_catalog_to_draft(catalog=activated, actor=self.admin)
        self.assertEqual(cloned.status, ServiceUnitCatalog.Status.DRAFT)
        self.assertEqual(cloned.entries.count(), 1)
        self.assertEqual(cloned.entries.first().base_units, Decimal("1.00"))


class ServiceUnitCatalogChoiceColumnWidthTest(SimpleTestCase):
    """طولُ العمود مقابل أطولِ مفتاحِ رمز — القاعدة الثابتة في هذا المستودع."""

    def test_document_type_column_fits_longest_key(self):
        field = ServiceUnitCatalogEntry._meta.get_field("document_type")
        longest = max(ServiceDocumentType.values, key=len)
        self.assertGreaterEqual(field.max_length, len(longest))
