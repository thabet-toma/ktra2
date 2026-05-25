"""P-H-4: Cheque state machine — VALID_TRANSITIONS enforcement."""
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import Cheque, ChequeMovement
from partners.models import Partner
from tenants.models import Currency, Tenant


class ChequeLifecycleTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=120, CompanyName="Chq Life")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="Chq Partner",
            partner_type="Customer",
        )

    def setUp(self):
        self.cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number="CHQ-001",
            amount=1000, currency=self.currency,
            partner=self.partner, status="Draft",
            direction="Incoming",
        )

    def test_draft_to_under_collection_valid(self):
        movement = self.cheque.change_status("Under_Collection")
        self.assertEqual(self.cheque.status, "Under_Collection")
        self.assertIsNotNone(movement)
        self.assertEqual(movement.movement_type, "deposit")

    def test_draft_to_bounced_valid(self):
        movement = self.cheque.change_status("Bounced")
        self.assertEqual(self.cheque.status, "Bounced")
        self.assertEqual(movement.movement_type, "bounce")

    def test_invalid_transition_raises(self):
        with self.assertRaises(ValidationError):
            self.cheque.change_status("Collected")

    def test_draft_to_cancelled_invalid(self):
        with self.assertRaises(ValidationError):
            self.cheque.change_status("Cancelled")

    def test_bounced_to_under_collection_valid(self):
        self.cheque.change_status("Under_Collection")
        self.cheque.change_status("Bounced")
        movement = self.cheque.change_status("Under_Collection")
        self.assertEqual(self.cheque.status, "Under_Collection")
        self.assertIsNotNone(movement)

    def test_returned_terminal_raises_from_draft(self):
        self.cheque.change_status("Returned")
        self.assertEqual(self.cheque.status, "Returned")
        with self.assertRaises(ValidationError):
            self.cheque.change_status("Draft")

    def test_returned_terminal_raises_from_under_collection(self):
        self.cheque.change_status("Under_Collection")
        self.cheque.change_status("Returned")
        with self.assertRaises(ValidationError):
            self.cheque.change_status("Draft")

    def test_same_status_returns_none(self):
        result = self.cheque.change_status("Draft")
        self.assertIsNone(result)

    def test_movement_created_on_status_change(self):
        self.cheque.change_status("Under_Collection")
        self.cheque.change_status("Bounced")
        movements = ChequeMovement.objects.filter(cheque=self.cheque)
        self.assertEqual(movements.count(), 2)
