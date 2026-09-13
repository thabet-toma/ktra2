"""تطبيعُ الهاتف — مفتاحُ الفرادة المخزَّن في القاعدة. راجع `crm/phone.py`."""
from django.test import SimpleTestCase

from crm.phone import PhoneNormalizationError, normalize_phone


class PhoneNormalizationGoldenTableTest(SimpleTestCase):
    def test_the_golden_table(self):
        cases = [
            ("0501234567", "+972501234567"),
            ("+972501234567", "+972501234567"),
            ("00972501234567", "+972501234567"),
            ("972-50-123-4567", "+972501234567"),
            ("050 123 4567", "+972501234567"),
            ("٠٥٠١٢٣٤٥٦٧", "+972501234567"),
            ("۰۵۰۱۲۳۴۵۶۷", "+972501234567"),
            ("(050) 123-4567", "+972501234567"),
            ("0501234567 ", "+972501234567"),
            (" 0501234567", "+972501234567"),
            ("0521234567", "+972521234567"),
            ("0591234567", "+972591234567"),
            ("00970591234567", "+970591234567"),
            ("+970591234567", "+970591234567"),
            ("970-59-123-4567", "+970591234567"),
            ("0592345678", "+972592345678"),
            ("592345678", "+972592345678"),
            ("522345678", "+972522345678"),
            ("00 972 50 123 4567", "+972501234567"),
            ("+972 50 123 4567", "+972501234567"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), expected)


class PhoneNormalizationGarbageTest(SimpleTestCase):
    def test_garbage_is_rejected_not_guessed(self):
        garbage = ["", None, "abc", "12", "+0501234567", "+", "0000000000000000"]
        for raw in garbage:
            with self.subTest(raw=raw):
                with self.assertRaises(PhoneNormalizationError):
                    normalize_phone(raw)
