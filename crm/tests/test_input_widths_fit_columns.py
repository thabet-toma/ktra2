"""كلُّ حقلِ إدخالٍ نصّيٍّ يسع في عموده — نظيرُ `test_choices_fit_columns.py` للمدخلات.

`test_choices_fit_columns.py` يحرس القيمَ التي **نكتبها نحن** في `choices`.
وهذا الملفُّ يحرس القيمَ التي **يكتبها المستخدم**: مُسلسِلٌ بـ`CharField()` بلا
`max_length` يمرّ عبر التحقّق سليماً ثمّ يضرب عموداً أضيقَ منه — فتقتطعه MySQL
بصمتٍ في الوضع المتساهل أو ترفض الطلبَ بخطأ قاعدةٍ غامضٍ في الصارم، وSQLite في
الاختبارات **لا تفرض `max_length` إطلاقاً** فلا تُظهر أيَّ فرق.

والحارسُ يقرأ العرضَ من النموذج لا من رقمٍ مكتوبٍ هنا، فتضييقُ عمودٍ غداً يُسقطه
حتى يُضيَّق المُسلسِلُ معه.
"""
from rest_framework.test import APITestCase

from crm.models import Lead, LeadPhone
from crm.serializers import (
    LeadImportRowSerializer,
    LeadPhoneInputSerializer,
    MAX_IMPORT_ROWS,
)
from crm.services import CrmValidationError, create_lead

from ._helpers import make_manager

#: حقلُ الإدخال ← (النموذج، اسمُ العمود) الذي ينتهي إليه فعلاً.
IMPORT_ROW_COLUMNS = {
    "store_name": (Lead, "store_name"),
    "owner_name": (Lead, "owner_name"),
    "city": (Lead, "city"),
    "address": (Lead, "address"),
    "activity": (Lead, "activity"),
    # `phone` يُخزَّن في `LeadPhone.raw` «كما كُتب» لا في عمودٍ على `Lead`.
    "phone": (LeadPhone, "raw"),
}


class ImportInputWidthsFitTheirColumnsTest(APITestCase):
    def test_every_import_row_field_is_capped_by_its_column(self):
        serializer = LeadImportRowSerializer()
        declared = set(serializer.fields)
        self.assertEqual(
            declared, set(IMPORT_ROW_COLUMNS),
            "حقلُ استيرادٍ أُضيف أو حُذف ولم يُحدَّث هذا الجدول:\n"
            f"  في المُسلسِل ولا في الجدول: {sorted(declared - set(IMPORT_ROW_COLUMNS))}\n"
            f"  في الجدول ولا في المُسلسِل: {sorted(set(IMPORT_ROW_COLUMNS) - declared)}",
        )
        for name, (model, column) in IMPORT_ROW_COLUMNS.items():
            with self.subTest(field=name):
                width = model._meta.get_field(column).max_length
                field_max = serializer.fields[name].max_length
                self.assertIsNotNone(
                    field_max,
                    f"‏`{name}` بلا `max_length` — نصٌّ بلا سقفٍ يضرب "
                    f"{model.__name__}.{column} ({width} محرفاً).",
                )
                self.assertLessEqual(
                    field_max, width,
                    f"‏`{name}` يقبل {field_max} محرفاً والعمودُ "
                    f"{model.__name__}.{column} يسع {width} فقط.",
                )

    def test_the_phone_input_is_capped_by_the_raw_column(self):
        width = LeadPhone._meta.get_field("raw").max_length
        field_max = LeadPhoneInputSerializer().fields["raw"].max_length
        self.assertIsNotNone(field_max, "‏`raw` في إدخال الهاتف بلا سقف.")
        self.assertLessEqual(field_max, width)

    def test_an_over_long_store_name_is_rejected_with_400_not_a_database_error(self):
        """الدليلُ السلوكيّ: الرفضُ تحقُّقٌ مفهومٌ لا انفجارُ قاعدة."""
        self.client.force_authenticate(user=make_manager("width-manager"))
        width = Lead._meta.get_field("store_name").max_length
        res = self.client.post(
            "/api/platform/crm/leads/import/",
            {"rows": [{"store_name": "م" * (width + 1), "phone": "0501234567"}]},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(Lead.objects.count(), 0)

    def test_an_over_long_raw_phone_is_rejected_before_it_reaches_the_column(self):
        self.client.force_authenticate(user=make_manager("width-manager-2"))
        width = LeadPhone._meta.get_field("raw").max_length
        res = self.client.post(
            "/api/platform/crm/leads/",
            {
                "store_name": "محل الرقم الطويل",
                "phones": [{"raw": "0" * (width + 5) + "501234567", "kind": LeadPhone.Kind.PRIMARY}],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(LeadPhone.objects.count(), 0)


class TheServiceGuardsTheWidthByItselfTest(APITestCase):
    """الخدمةُ تحرس الطولَ **بلا** المُسلسِل — يُختبَر بتجاوزه لا عبر الـHTTP.

    بلا هذا الاختبار يكون حارسُ الطول في `_normalize_phone_entries` كوداً لا
    يُشغّله شيء: كلُّ مسارٍ HTTP يمرّ من `LeadPhoneInputSerializer` المسقوف
    أصلاً، فحذفُ الحارسِ من الخدمة يُبقي المجموعةَ كلَّها خضراء — أُثبت ذلك
    بالتخريب. و`create_lead` واجهةٌ عامّةٌ تُنادى مباشرةً (`import_leads`
    وأدواتُ الإدارة)، فالحارسُ فيها ليس تكراراً بل الطبقةُ الوحيدةُ هناك.
    """

    def test_create_lead_refuses_a_raw_phone_wider_than_its_column(self):
        width = LeadPhone._meta.get_field("raw").max_length
        with self.assertRaises(CrmValidationError) as caught:
            create_lead(
                store_name="محل يتجاوز العمود",
                phones=[{"raw": "0" * (width + 5) + "501234567", "kind": LeadPhone.Kind.PRIMARY}],
            )
        self.assertEqual(caught.exception.code, "phone_too_long")
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(LeadPhone.objects.count(), 0)


class ImportBatchIsCappedTest(APITestCase):
    """دفعةٌ بلا سقفٍ تُبقي معاملةً ذرّيّةً مفتوحةً حتى المهلة، لا حتى رسالةٍ مفهومة."""

    def test_a_batch_over_the_cap_is_refused_with_a_message_naming_the_cap(self):
        self.client.force_authenticate(user=make_manager("cap-manager"))
        rows = [{"store_name": f"محل {i}", "phone": f"05{i:08d}"} for i in range(MAX_IMPORT_ROWS + 1)]
        res = self.client.post(
            "/api/platform/crm/leads/import/", {"rows": rows}, format="json",
        )
        self.assertEqual(res.status_code, 400, res.content[:400])
        self.assertIn(str(MAX_IMPORT_ROWS), res.content.decode("utf-8"))
        self.assertEqual(Lead.objects.count(), 0)
