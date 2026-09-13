"""كلُّ قيمةِ `choices` تسع في عمودها — على نمط
`platform_ops/tests/test_choices_fit_columns.py`: قيمةٌ أطولُ من `max_length`
تُقتطَع في MySQL بصمت، ولا تكشفه SQLite (لا تفرض `max_length` أصلاً)."""
from django.apps import apps
from django.db import models
from django.test import SimpleTestCase


class CrmChoicesFitTheirColumnsTest(SimpleTestCase):
    def test_no_choice_value_is_longer_than_its_column(self):
        offenders = []
        for model in apps.get_app_config("crm").get_models():
            for field in model._meta.get_fields():
                if not isinstance(field, models.CharField) or not field.choices:
                    continue
                max_length = field.max_length or 0
                for value, _label in field.flatchoices:
                    if isinstance(value, str) and len(value) > max_length:
                        offenders.append(
                            f"{model.__name__}.{field.name}: "
                            f"«{value}» طولُها {len(value)} والعمودُ {max_length}"
                        )
        self.assertEqual(
            offenders, [],
            "قيمةُ choices أطولُ من عمودها — تُقتطَع في MySQL بصمتٍ فيسقط القيد، "
            f"ولا تكشفه SQLite: {offenders}",
        )
