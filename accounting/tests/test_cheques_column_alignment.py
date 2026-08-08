"""T-CHQ3/ح — مواءمة أعمدة `cheques` مع النموذج (هجرة 0032).

بلاغ المالك: `IntegrityError (1048, "Column 'DueDate' cannot be null")` عند حفظ
سند قبض بشيك بلا تاريخ استحقاق. الجدول مُرحَّل من مخطط قديم فبقيت أعمدة
NOT NULL في MySQL بينما يعلنها النموذج `null=True`.

الهجرة نفسها لا تُنفَّذ في الاختبارات (`--nomigrations` وقاعدة SQLite)، فالمُختبَر
هنا: (١) أنها لا تلمس أي قاعدة غير MySQL — وإلا انكسر البناء من الصفر على
SQLite، (٢) وأن النموذج يقبل شيكاً بلا تاريخ استحقاق فلا يبقى للفشل سبب سوى
انحراف المخطط.
"""
from decimal import Decimal
from importlib import import_module
from unittest.mock import MagicMock

from django.contrib.auth.models import User
from django.test import TestCase

from accounting.models import Cheque
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

migration = import_module(
    "accounting.migrations.0032_cheques_align_nullable_columns"
)


class ChequesColumnAlignmentTest(TestCase):
    def test_migration_is_a_no_op_outside_mysql(self):
        """البناء من الصفر على SQLite يجب ألّا يمسّه DDL خاص بـMySQL."""
        schema_editor = MagicMock()
        schema_editor.connection.vendor = "sqlite"
        migration.align_nullable_columns(None, schema_editor)
        schema_editor.connection.cursor.assert_not_called()

    def test_every_model_nullable_column_is_covered(self):
        """أي حقل nullable جديد على الشيك يجب أن يدخل قائمة المواءمة."""
        model_nullable = {
            field.db_column
            for field in Cheque._meta.fields
            if field.null and field.db_column
        }
        self.assertEqual(model_nullable - set(migration.NULLABLE_COLUMNS), set())

    def test_a_cheque_without_a_due_date_is_valid_per_the_model(self):
        user = User.objects.create_user(username="chqcol", password="x")
        ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        tenant = create_company("شركة أعمدة الشيكات", user)
        customer = Partner.objects.create(
            tenant=tenant, name="زبون", partner_type="Customer")
        cheque = Cheque.objects.create(
            tenant=tenant, cheque_number="NO-DUE", amount=Decimal("555.00"),
            currency=ils, partner=customer, direction="Incoming", status="Draft",
        )
        self.assertIsNone(cheque.due_date)
        self.assertIsNone(cheque.issue_date)
