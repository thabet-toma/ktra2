"""P-H-11: TenantBook concurrent number generation — atomic get_next_number."""
from django.db import transaction
from django.test import TestCase

from tenants.models import Tenant, TenantBook


class TenantBookConcurrentTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=170, CompanyName="TB Con Test")

    def test_get_next_number_creates_book_auto(self):
        num = TenantBook.get_next_number(
            tenant_id=self.tenant.TenantID,
            document_type="sales_invoice",
            book_number=1,
        )
        self.assertEqual(num, 1)
        book = TenantBook.objects.get(
            tenant_id=self.tenant.TenantID,
            document_type="sales_invoice",
            book_number=1,
        )
        self.assertEqual(book.last_used_number, 1)

    def test_get_next_number_increments(self):
        TenantBook.get_next_number(self.tenant.TenantID, "purchase_invoice", 1)
        num2 = TenantBook.get_next_number(self.tenant.TenantID, "purchase_invoice", 1)
        self.assertEqual(num2, 2)

    def test_different_document_types_independent(self):
        a = TenantBook.get_next_number(self.tenant.TenantID, "sales_invoice", 0)
        b = TenantBook.get_next_number(self.tenant.TenantID, "purchase_invoice", 0)
        self.assertEqual(a, 1)
        self.assertEqual(b, 1)

    def test_inactive_book_raises(self):
        TenantBook.objects.create(
            tenant=self.tenant,
            document_type="journal_entry",
            book_number=1,
            last_used_number=0,
            is_active=False,
        )
        with self.assertRaises(Exception):
            TenantBook.get_next_number(self.tenant.TenantID, "journal_entry", 1)

    def test_sequential_numbers_in_transaction(self):
        nums = []
        with transaction.atomic():
            nums.append(TenantBook.get_next_number(self.tenant.TenantID, "deal", 0))
        with transaction.atomic():
            nums.append(TenantBook.get_next_number(self.tenant.TenantID, "deal", 0))
        self.assertEqual(nums, [1, 2])
        book = TenantBook.objects.get(
            tenant_id=self.tenant.TenantID,
            document_type="deal",
            book_number=0,
        )
        self.assertEqual(book.last_used_number, 2)
