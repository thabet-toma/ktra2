"""كلُّ قيمةِ `choices` تسع في عمودها — حارسٌ ضدّ فخٍّ لا تراه اختباراتُنا.

الفخُّ معروفٌ في هذا المستودع وقد لدغ من قبل: قيمةُ `choices` أطولُ من
`max_length` تُقتطَع في MySQL بصمت، فيصير العمودُ يحمل نصفَ القيمة ويسقط القيدُ
المنطقيُّ كلُّه بلا استثناءٍ واحد — **و‏SQLite (وعليها تعمل اختباراتُنا) لا
تعيد إنتاجَ ذلك أبداً** لأنّها لا تفرض `max_length` أصلاً. أي أنّ المجموعةَ
كاملةً تمرّ خضراء على خللٍ لا يظهر إلاّ في الإنتاج.

ولذلك يُقاس الطولُ ساكناً هنا: لا يكفي أن تكون القيمُ الحاليّةُ سليمة، بل يجب
أن يسقط الاختبارُ في اللحظة التي يضيف فيها أحدُهم حالةً أطولَ من عمودها.

الوحدةُ مقصودةٌ بعينها (`platform_ops`) لأنّها أكثرُ ما يُضاف إليه حالاتٌ جديدة
في #210 و#211، وحالاتُ حضور الاجتماع (`excused_accepted` و`excused_rejected`)
هي أطولُ قيمِ `choices` في الوحدة كلِّها.
"""
from django.apps import apps
from django.db import models
from django.test import SimpleTestCase


class PlatformOpsChoicesFitTheirColumnsTest(SimpleTestCase):
    def test_no_choice_value_is_longer_than_its_column(self):
        offenders = []
        for model in apps.get_app_config("platform_ops").get_models():
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
