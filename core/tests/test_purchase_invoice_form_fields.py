"""حارسُ حقول محرِّر فاتورة الشراء — لأنّ `tsc` **لا يحرسها**.

**لماذا يوجد هذا الملف:** في وجه مستند فاتورة الشراء كان سطرُ «المورد ← الاسم»
يعرض «—» في كلّ فاتورة. السببُ أنّ الشاشة تقرأ `formData.supplierName`، و
`supplierName` **حقلٌ لا وجودَ له** على النوع `Invoice`: لا يكتبه
`sqlListToInvoice` ولا `mapPurchaseInvoiceDtoToInvoice`. ومعه حقلان وهميّان
آخران في اللوحة نفسِها كانا صفّين **لا يُرسَمان أبداً**.

**ولماذا مرّ ذلك من البوّابة:** `npx tsc --noEmit` خضراءُ على هذا كلِّه. جُرِّب
بالقياس لا بالظنّ: استُبدل الحقلُ بـ`formData.zzzProbeNoSuchField` فمرّ بـ`rc=0`،
ثمّ وُضع `const zzzT: number = formData;` فمرّ أيضاً — أي أنّ `formData` تعود
**`any`**. والسببُ أنّ `@types/react` **غيرُ مثبَّتة في المستودع أصلاً**
(‏`frontend_v2/node_modules/@types/` لا تحوي `react`)، فـ`useState` وكلُّ ما
يعود منها بلا نوع. فكلُّ قراءةٍ من حالةٍ يحملها hook — في هذا الملفّ وغيره —
خارجَ حراسة المترجم، وحقلٌ وهميٌّ يمرّ كما يمرّ الحقيقيّ.

فالحراسةُ تقع هنا أو لا تقع.

**المقارنةُ بالمصدر لا بقائمةٍ مكتوبةٍ بيد:** الحقولُ تُقرأ من
`frontend_v2/types/invoice.ts` نفسِه، فحقلٌ يُضاف أو يُحذف هناك يسري هنا بلا
تحديثٍ يدويٍّ يُنسى.

السابقة في هذا المستودع: `core/tests/test_domain_consistency.py` و
`platform_ops/tests/test_hiring_portal.py` (`DECLARED_PUBLIC_VIEWS`) —
المستثنى يُعلَن باسمه وسببه المكتوب، ويسقط الحارسُ إن لم يعد الاستثناءُ حقيقيّاً.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

INVOICE_TYPES = REPO_ROOT / "frontend_v2" / "types" / "invoice.ts"
INVOICE_FORM = (
    REPO_ROOT / "frontend_v2" / "components" / "procurement" / "invoices" / "InvoiceForm.tsx"
)

#: قراءاتٌ من `formData` لا يقابلها حقلٌ على `Invoice` **بعد**، كلٌّ بسببه
#: المكتوب. ليست ترخيصاً: الاختبارُ التالي يسقط إن صار أحدُها حقلاً حقيقيّاً
#: فيُشطَب من هنا، وإن اختفت قراءتُه من الشاشة فيُشطَب كذلك.
KNOWN_ABSENT_FIELDS = {
    "exchangeRate": (
        "سعرُ صرف الفاتورة يصل من الخادم في `PurchaseInvoiceDto.exchange_rate` "
        "ولا يُنقَل إلى `Invoice` في أيّ من المُحوِّلَين — الحقلُ المسمّى "
        "`exchangeRate` على النوع يخصّ **دفعةً** (`InvoicePayment`) لا فاتورة. "
        "فصفُّ «سعر الصرف» في وجه المستند لم يُرسَم قطّ. إصلاحُه يضيف حقلاً إلى "
        "نوعٍ مشترَكٍ وإلى المُحوِّل، وهو خارج تذكرة «اسم المورد لا يظهر»: "
        "مرفوعٌ للمالك ولم يُبنَ."
    ),
}


def _invoice_interface_fields() -> set[str]:
    """أسماءُ حقول `interface Invoice` من ملفّ الأنواع نفسِه."""
    source = INVOICE_TYPES.read_text(encoding="utf-8")
    start = source.index("export interface Invoice {")
    depth = 0
    index = start
    while True:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                break
        index += 1
    body = source[start:index]
    # حقولُ المستوى الأوّل وحدَها (أربعُ مسافاتٍ بادئة) — لا حقولُ الكائنات المتداخلة.
    return set(re.findall(r"^\s{4}([A-Za-z_][A-Za-z0-9_]*)\??\s*:", body, re.M))


def _strip_comments(source: str) -> str:
    """يُجرّد التعليقات — **حارسٌ يسقط على تعليقٍ حارسٌ معطوب**.

    وعكسُه أسوأ: لولا التجريدُ لأمكن «إصلاحُ» مخالفةٍ بنقلها إلى تعليق.
    """
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"//[^\n]*", " ", source)


def _form_data_reads() -> set[str]:
    """كلُّ `formData.<حقل>` مقروءٌ في **كود** محرِّر فاتورة الشراء."""
    source = _strip_comments(INVOICE_FORM.read_text(encoding="utf-8"))
    return set(re.findall(r"\bformData\.([A-Za-z_][A-Za-z0-9_]*)", source))


class PurchaseInvoiceFormFieldsTest(SimpleTestCase):
    """كلُّ حقلٍ يقرؤه المحرِّرُ من الحالة موجودٌ فعلاً على النوع."""

    def test_every_form_data_read_exists_on_the_invoice_type(self):
        declared = _invoice_interface_fields()
        self.assertGreater(len(declared), 50, "تعذّر استخراجُ حقول `Invoice` — تغيّر شكلُ الملفّ")

        phantom = sorted(_form_data_reads() - declared - set(KNOWN_ABSENT_FIELDS))
        self.assertEqual(
            phantom,
            [],
            "حقولٌ تُقرأ من `formData` ولا وجودَ لها على `Invoice` "
            f"(فتُعرَض فارغةً أو لا يُرسَم صفُّها): {phantom}. "
            "‏`tsc` لا يمسكها لأنّ `formData` تعود `any` بغياب `@types/react`.",
        )

    def test_declared_absent_fields_are_still_absent_and_still_read(self):
        """المستثنى يُشطَب متى صلُح أو متى اختفى — ولا يبقى يصف ماضياً."""
        declared = _invoice_interface_fields()
        reads = _form_data_reads()
        for field, reason in KNOWN_ABSENT_FIELDS.items():
            self.assertTrue(reason.strip(), f"استثناءٌ بلا سببٍ مكتوب: {field}")
            self.assertNotIn(
                field,
                declared,
                f"`{field}` صار حقلاً حقيقيّاً على `Invoice` — اشطبه من KNOWN_ABSENT_FIELDS",
            )
            self.assertIn(
                field,
                reads,
                f"`formData.{field}` لم تعد تُقرأ — اشطبه من KNOWN_ABSENT_FIELDS",
            )
