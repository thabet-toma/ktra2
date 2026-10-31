"""حارس المبالغ — #272.

**القاعدة الملزِمة:** كلُّ مبلغٍ في هذا الموديول يمرّ بـ`can_see_amounts` و
`mask_amounts` في `accounting_office/services.py`، وكلُّ مفتاحِ مبلغٍ مُعلَنٌ في
`AMOUNT_KEYS`. مبلغٌ جديدٌ يُضاف إلى مُسلسِلٍ أو نموذجٍ أو حمولةٍ بلا تسجيلٍ هنا
يعني ردّاً يُظهر المبلغ لعضوٍ لا يملك `office.amounts.view` — ويُكتشَف عند العميل
لا عندنا.

**والمسحُ ثلاثة لا واحد** (كلُّها تُسقط الحارس على مبلغٍ غير مسجَّل):
1. حقولُ `serializers.DecimalField` المعلَنة في `accounting_office/serializers.py`.
2. حقولُ `DecimalField` في **نماذج** الموديول (`apps.get_app_config(...).get_models()`) —
   فمبلغٌ يُخزَّن ولا يمرّ بمُسلسِلٍ اليوم قد يُضاف إلى حمولةٍ غداً.
3. مفاتيحُ الحمولات الفعلية التي تحمل قيمةً عشريّة (`tax_card_payload`) — مفتاحٌ
   جديدٌ فيها بلا تسجيلٍ يفشل ولو لم يكن له حقلٌ صريح.

**ولذلك مسحُ المصدر لا اختبارُ سلوك:** السلوكُ اليوم سليم؛ الخطرُ في تذكرةٍ لاحقة
تضيف `service_fees` إلى البطاقة وتنسى القناع. الحارسُ يمنع الكتابة من أصلها.

والحارسُ **يثبت أنه يسقط**: التمثيلاتُ المزروعة في هذا الملف تفشل لو صار المسح
أعمى — نصّاً ونموذجاً مزروعين في الذاكرة لا ملفاً تحت المستودع، فلا يُلوّث الشجرة
ولا يتسابق عمّالُ xdist.
"""
import pathlib
import re
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.contrib.auth.models import User
from django.db import models as django_models
from django.test import SimpleTestCase, TestCase

from accounting_office import services
from accounting_office.models import OfficeClient, TaxCard
from accounting_office.services import set_office_setting
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

APP_DIR = pathlib.Path(__file__).resolve().parent.parent

#: حقولُ مبلغٍ في النماذج معفاةٌ من الحارس **بسببٍ مكتوب** — بمفتاحٍ مؤهَّل
#: `النموذج.الحقل` كي لا يُعفى أيُّ حقلٍ آخر يُسمّى `amount` في الموديول.
#:
#: `TaxThreshold.amount` (#273): سقفٌ ضريبيّ **منشور** في `source_url` — بياناتُ
#: منصّةٍ واحدةٌ لكل المكاتب (بلا `tenant`)، وليس مبلغَ زبونٍ فيمرّ بالقناع. ولو
#: قُنِّع لاختفى أساسُ الاقتراح من كل شاشة، وهو رقمٌ عامٌّ في التشريع لا سرّ عميل.
MODEL_AMOUNT_EXEMPTIONS: frozenset[str] = frozenset({"TaxThreshold.amount"})


def declared_amount_fields(source: str) -> list[str]:
    """أسماءُ حقول `serializers.DecimalField` المعلَنة في نصّ مُسلسِل — نواةُ المسح."""
    return re.findall(r"^\s*(\w+)\s*=\s*serializers\.DecimalField\(", source, re.MULTILINE)


def unregistered_amount_fields(source: str, registered) -> list[str]:
    """حقولُ مبلغٍ في نصٍّ ما ليست في ثابت المبالغ — أيُّها يُسقِط الحارس."""
    return [name for name in declared_amount_fields(source) if name not in registered]


def model_amount_fields(models) -> list[str]:
    """حقولُ `DecimalField` في مجموعة نماذج — مؤهَّلةً بـ`النموذج.الحقل`."""
    return sorted(
        f"{getattr(model, '__name__', type(model).__name__)}.{field.name}"
        for model in models
        for field in model._meta.get_fields()
        if isinstance(field, django_models.DecimalField)
    )


def unregistered_model_amount_fields(registered, exemptions=MODEL_AMOUNT_EXEMPTIONS) -> list[str]:
    """حقولُ المبالغ في نماذج الموديول غير المسجَّلة — أيُّها يُسقِط الحارس.

    المقارنةُ **باسم النموذج والحقل معاً** للإعفاء، وباسم الحقل وحده للثابت
    (`AMOUNT_KEYS` مفاتيحُ حمولةٍ لا مساراتُ نماذج).
    """
    configured = apps.get_app_config("accounting_office")
    return [
        name for name in model_amount_fields(configured.get_models())
        if name.split(".")[-1] not in registered and name not in exemptions
    ]


def fake_amount_model(field_name: str):
    """نموذجٌ مزروعٌ في الذاكرة — يُثبت أن مسحَ النماذج يسقط فعلاً."""
    class _FakeMeta:
        def __init__(self, fields):
            self._fields = fields

        def get_fields(self):
            return self._fields

    class _FakeModel:
        # اسمُ نموذجٍ صريحٌ كي يُقارَن مفتاحُ الإعفاء المؤهَّل (`FakeModel.service_fee`).
        __name__ = "FakeModel"

        def __init__(self, fields):
            self._meta = _FakeMeta(fields)

    field = django_models.DecimalField(max_digits=14, decimal_places=2)
    field.set_attributes_from_name(field_name)
    return _FakeModel([field])


def decimal_payload_keys(payload, prefix: str = "") -> list[str]:
    """مفاتيحُ حمولةٍ تحمل قيمةً عشريّة (أي مبلغٍ) — ولو كانت متداخلةً في قائمة."""
    keys: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, Decimal):
                keys.append(path)
            else:
                keys.extend(decimal_payload_keys(value, path))
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            keys.extend(decimal_payload_keys(item, f"{prefix}[{index}]"))
    return keys


class AmountKeysGuardTest(SimpleTestCase):
    def test_every_declared_decimal_field_is_a_registered_amount_key(self):
        offenders = unregistered_amount_fields(
            (APP_DIR / "serializers.py").read_text(encoding="utf-8"),
            services.AMOUNT_KEYS,
        )
        self.assertEqual(
            offenders, [],
            "حقلُ مبلغٍ في `accounting_office/serializers.py` غير مسجَّلٍ في "
            "`accounting_office/services.py` (`AMOUNT_KEYS`) — أضِفه هناك كي "
            f"يمرّ بالقناع: {offenders}",
        )

    def test_decimal_fields_map_to_the_amount_keys(self):
        """أي تغييرٍ في الثابت يجب أن يُرى هنا — وإلا كان المسح زينة."""
        self.assertEqual(
            declared_amount_fields((APP_DIR / "serializers.py").read_text(encoding="utf-8")),
            ["annual_sales", "suggested_price"],
        )
        self.assertEqual(
            unregistered_amount_fields(
                "class X(serializers.Serializer):\n"
                "    annual_sales = serializers.DecimalField(max_digits=14, decimal_places=2)\n",
                services.AMOUNT_KEYS,
            ),
            [],
        )
        self.assertEqual(
            unregistered_amount_fields(
                "class X(serializers.Serializer):\n"
                "    service_fee = serializers.DecimalField(max_digits=14, decimal_places=2)\n",
                services.AMOUNT_KEYS,
            ),
            ["service_fee"],
        )


class ModelAmountGuardTest(SimpleTestCase):
    """نماذجُ الموديول أيضاً: مبلغٌ يُخزَّن بلا تسجيلٍ مبلغٌ سيتسرّب بحمولةٍ لاحقة."""

    def test_every_decimal_field_on_a_model_is_a_registered_amount_key(self):
        offenders = unregistered_model_amount_fields(services.AMOUNT_KEYS)
        self.assertEqual(
            offenders, [],
            "حقلُ مبلغٍ في نماذج `accounting_office` غير مسجَّلٍ في "
            "`accounting_office/services.py` (`AMOUNT_KEYS`): أضِفه هناك كي يمرّ "
            f"بالقناع، أو أعلِن إعفاءً في `MODEL_AMOUNT_EXEMPTIONS` بسببٍ مكتوب: {offenders}",
        )

    def test_the_model_scan_finds_the_known_amounts(self):
        """أضيقُ من التسجيل: يُثبت أن المسح يقرأ النماذج فعلاً لا قائمةً فارغة."""
        self.assertEqual(
            model_amount_fields(apps.get_app_config("accounting_office").get_models()),
            [
                "ServicePackage.suggested_price",
                "TaxCard.annual_sales",
                "TaxThreshold.amount",
            ],
        )

    def test_the_guard_falls_on_a_synthetic_model(self):
        """لو صار مسحُ النماذج أعمى (نمطٌ خاطئ أو قائمةٌ فارغة) يسقط هذا الاختبار."""
        with mock.patch("django.apps.apps.get_app_config") as get_config:
            get_config.return_value.get_models.return_value = [fake_amount_model("service_fee")]
            self.assertEqual(
                unregistered_model_amount_fields(services.AMOUNT_KEYS),
                ["FakeModel.service_fee"],
            )
        # ومبلغٌ مسجَّلٌ لا يُسقطه — وإلا كان الإعفاءُ العامَّ هو الحارس.
        with mock.patch("django.apps.apps.get_app_config") as get_config:
            get_config.return_value.get_models.return_value = [fake_amount_model("annual_sales")]
            self.assertEqual(unregistered_model_amount_fields(services.AMOUNT_KEYS), [])
        # وإعفاءٌ مؤهَّلٌ لا يُعفى به حقلٌ آخر بالاسم نفسه في نموذجٍ آخر.
        with mock.patch("django.apps.apps.get_app_config") as get_config:
            get_config.return_value.get_models.return_value = [fake_amount_model("amount")]
            self.assertEqual(
                unregistered_model_amount_fields(services.AMOUNT_KEYS),
                ["FakeModel.amount"],
            )


class AmountPayloadGuardTest(TestCase):
    """الحمولات الفعلية: مفتاحٌ عشريٌّ في ردٍّ معناه مبلغٌ لم يمرّ بالثابت."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.owner = User.objects.create_user(username="guard_amounts_owner", password="x")
        cls.tenant = create_company(
            "مكتب حارس المبالغ", cls.owner, template="accounting_office",
        )
        set_office_setting(cls.tenant, "tax_system", "PS")
        set_office_setting(cls.tenant, "office_size", "small")
        cls.client_row = OfficeClient.objects.create(
            tenant=cls.tenant, name="زبون الحارس", responsible=cls.owner,
        )
        TaxCard.objects.create(
            client=cls.client_row, annual_sales=Decimal("4321.00"),
        )

    def test_the_tax_card_payload_carries_no_unregistered_decimal(self):
        keys = decimal_payload_keys(
            services.tax_card_payload(self.client_row, user=None),
        )
        self.assertEqual(
            [key for key in keys if key not in services.AMOUNT_KEYS], [],
            f"مبلغٌ في حمولة البطاقة بلا تسجيل في `AMOUNT_KEYS`: {keys}",
        )
        self.assertIn("annual_sales", keys)

    def test_every_card_amount_key_is_masked_for_a_member_without_the_key(self):
        """سلوكٌ لا مطابقةُ ثوابت: كلُّ مفتاحٍ مسجَّلٍ يُقنَّع عن العضو ويصل المالك."""
        member = User.objects.create_user(username="guard_amounts_behavior", password="x")
        UserCompanyMembership.objects.create(
            user=member, tenant=self.tenant, role="accountant",
        )
        self.assertTrue(services.TAX_CARD_AMOUNT_KEYS)
        # قيمةٌ غير صفريةٍ لكل مفتاح — وإلا نجح «None» على صفرٍ فارغٍ بلا قناع.
        TaxCard.objects.filter(client=self.client_row).update(
            **{key: Decimal("4321.00") for key in services.TAX_CARD_AMOUNT_KEYS},
        )
        fresh = OfficeClient.objects.get(pk=self.client_row.pk)
        masked = services.tax_card_payload(fresh, user=member)
        full = services.tax_card_payload(fresh, user=self.owner)
        for key in services.TAX_CARD_AMOUNT_KEYS:
            self.assertIsNone(masked[key], key)
            self.assertIsNotNone(full[key], key)

    def test_the_masked_payload_hides_every_registered_amount(self):
        member = User.objects.create_user(username="guard_amounts_member", password="x")
        UserCompanyMembership.objects.create(
            user=member, tenant=self.tenant, role="accountant",
        )
        masked = services.tax_card_payload(self.client_row, user=member)
        for key in services.TAX_CARD_AMOUNT_KEYS:
            self.assertIsNone(masked[key], key)
        # و`user=None` الصريح (نداءٌ داخليّ) لا قناع — الحمولة كاملة.
        self.assertEqual(
            decimal_payload_keys(services.tax_card_payload(self.client_row, user=None)),
            ["annual_sales"],
        )
