from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounting.models import JournalHeader
from accounting.services import post_journal
from core.hooks import register_tax_period_guard, run_tax_period_guards


class TaxPeriodHookRegistryTest(TestCase):
    def test_empty_registry_is_a_zero_query_noop(self):
        with patch("core.hooks._tax_period_guards", []):
            with self.assertNumQueries(0):
                run_tax_period_guards(7, "2026-08-01")

    def test_registration_is_idempotent(self):
        calls = []

        def guard(tenant_id, transaction_date):
            calls.append((tenant_id, transaction_date))

        with patch("core.hooks._tax_period_guards", []):
            register_tax_period_guard(guard)
            register_tax_period_guard(guard)
            run_tax_period_guards(7, "2026-08-01")

        self.assertEqual(calls, [(7, "2026-08-01")])

    def test_post_journal_runs_guard_before_creating_a_journal(self):
        with patch("accounting.services.validate_fiscal_period"), patch(
            "accounting.services.run_tax_period_guards",
            side_effect=ValidationError("الفترة مقفلة"),
        ) as guard:
            with self.assertRaisesMessage(ValidationError, "الفترة مقفلة"):
                post_journal(
                    tenant_id=77,
                    transaction_date="2026-08-01",
                    reference_type="TEST",
                    reference_id=1,
                    description="اختبار الحارس",
                    lines_data=[],
                )

        guard.assert_called_once_with(77, "2026-08-01")
        self.assertFalse(JournalHeader.objects.exists())
