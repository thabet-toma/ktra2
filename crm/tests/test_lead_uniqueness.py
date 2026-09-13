"""فرادةُ رقم الهاتف عبر الوحدة كلّها — قيدُ القاعدة لا حارس بايثون وحده."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from crm.models import Lead, LeadPhone
from crm.services import DuplicateLeadError, create_lead


class LeadUniquenessTest(TestCase):
    def test_the_same_number_in_a_different_field_of_a_different_lead_is_refused(self):
        """واتسابُ عميلٍ = هاتفُ عميلٍ آخر ⇒ مرفوض، والقاعدةُ هي التي ترفض."""
        create_lead(store_name="محل أ", phones=[{"raw": "0501234567", "kind": LeadPhone.Kind.PRIMARY}])
        other_lead = Lead.objects.create(store_name="محل ب")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LeadPhone.objects.create(
                    lead=other_lead, e164="+972501234567", raw="0501234567",
                    kind=LeadPhone.Kind.WHATSAPP,
                )

    def test_two_spellings_of_one_number_are_one_lead(self):
        lead = create_lead(store_name="محل أ", phones=[{"raw": "0501234567", "kind": LeadPhone.Kind.PRIMARY}])

        with self.assertRaises(DuplicateLeadError) as ctx:
            create_lead(store_name="محل ثانٍ بنفس الرقم", phones=[
                {"raw": "+972501234567", "kind": LeadPhone.Kind.PRIMARY},
            ])

        self.assertEqual(ctx.exception.existing_lead.pk, lead.pk)
        self.assertEqual(Lead.objects.count(), 1)
