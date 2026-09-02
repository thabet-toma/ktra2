"""#37/#39/#42: حارس بنيوي — `str(product)` ممنوعة خارج `__str__` نفسها؛
`inventory/services.py` (`product_display_name`) هي الصيغة الوحيدة.

الدرس مدفوعٌ مرّتين: تعليق #22 في `sales/serializers.py` كتب القاعدة صراحةً،
وثلاثة مواضع في **نفس الملف** بقيت على `str(product)` رغم ذلك — الذاكرة لا
تكفي. النظير: `core/tests/test_docs_freshness.py`.

**البساطة شرط بقاء** (نفس سياسة الحارس النظير): يلتقط `str(x.product)`،
`str(product)`، أو الاسم المستعار `str(prod)`/`str(x.prod)` — لا
`str(product_id)` (الاسمان `product`/`prod` يجب أن يكونا آخر ما بين القوسين
حرفياً، فحداً يفصلهما `_id`)، ولا سلسلة تليها `.isdigit()` (لا كائن Product
يملك هذه الدالّة؛ ذاك معاملٌ نصّي من الطلب — راجع قرار #39 «ليس موضعاً
أصلاً»)، ولا الأسطر التي تبدأ بـ`#` (تعليقات توثّق القاعدة نفسها بذكر
`str(product)` كمثالٍ للممنوع، لا استدعاءً حقيقياً).

**حدٌّ موثَّق لا مسدود (#42):** الحارس **لا** يفحص الإقحام النصّي
(`f"...{product}..."` أو `f"...{prod}..."`). توسيعه فعلياً كان سيُبلِّغ عن
إحدى عشرة رسالة خطأ **قائمة سابقاً** خارج نطاق هذه التذكرة تماماً (ثلاثٌ في
`accounting/opening_balance.py`، وموضعان في `logistics/services.py`، وخمسةٌ في
`sales/services/flow.py`، وموضعٌ في `sales/services/orders.py`) — فحصها
وإصلاحها قرارٌ لتذكرةٍ لاحقة لا لهذه، وإدراجها في `ALLOWED` بلا تدقيقٍ يُفرغ
القائمة من معناها. الشكل المحمي فعلياً يبقى محصوراً بـ`str(...)`؛
`test_fstring_interpolation_is_a_documented_blind_spot` تثبت هذا الحدّ صراحةً
بدل أن تتركه ضمنياً.

`{self.product}` في `StockMovement.__str__`/`ProductPriceTier.__str__` تبقى
مسموحة بلا حاجة لاستثناءٍ صريح أصلاً — الحدّ أعلاه لا يفحص أيّ إقحامٍ نصّي،
سواءٌ كان بالاسم العاري أو عبر `self.`.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: `str(unit.product)`، `str(product)`، أو الاسم المستعار `str(prod)`/`str(x.prod)`
#: — لا `str(product_id)`. لا يفحص الإقحام النصّي (`f"{product}"`) — انظر
#: الحدّ الموثَّق أعلى الملف.
STR_PRODUCT_RE = re.compile(r"str\(\s*((?:\w+\.)*(?:product|prod))\s*\)(\.\w+)?")

#: خارج الفحص كلياً: الاختبارات، الهجرات، وما ليس كوداً محليّاً (نسخ
#: worktrees في `.claude/` كاملة المستودع — مصدرها يُفحص هناك لا هنا).
SKIP_RE = re.compile(
    r"(^|[\\/])(tests?|migrations)([\\/]|$)|node_modules"
    r"|(^|[\\/])\.claude([\\/]|$)|(^|[\\/])(\.?venv)([\\/]|$)"
)

#: مواضع فيها `str(<...>.product)` تُرك عمداً — كلٌّ بسببٍ موثَّق، لا سهواً.
#: (الملف بصيغة posix، ونصّ السطر بعد strip() — لا رقم سطر، فهو ينزاح.)
ALLOWED = {}


def _iter_py_files():
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if SKIP_RE.search(rel):
            continue
        yield path, rel


def _line_offenders(rel: str, line: str) -> list[str]:
    """مطابقات `STR_PRODUCT_RE` الحقيقية في سطرٍ واحد — لا تعليقات، لا في `ALLOWED`."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return []  # تعليقٌ يوثّق القاعدة بذكر المثال الممنوع، لا نداءً حقيقياً
    offenders = []
    for match in STR_PRODUCT_RE.finditer(line):
        if (match.group(2) or "").lstrip(".") == "isdigit":
            continue  # معاملٌ نصّي من الطلب لا كائن منتج (#39)
        if (rel, stripped) in ALLOWED:
            continue
        offenders.append(stripped)
    return offenders


class StrProductDisplayGuardTest(SimpleTestCase):
    """كل `str(product)` جديد (أو اسمٌ مستعار له) خارج القائمة البيضاء يُسقط هذا الاختبار."""

    def test_no_new_str_product_calls_outside_allowlist(self):
        offenders = []
        for path, rel in _iter_py_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                for stripped in _line_offenders(rel, line):
                    offenders.append(f"{rel}:{number} → {stripped}")
        self.assertEqual(
            offenders, [],
            "str(product) ممنوعة — استعمل `inventory/services.py` "
            "(`product_display_name`) بدلاً منها، أو أضِفها إلى ALLOWED في "
            "هذا الملف مع سببٍ صريح إن كانت متروكةً عمداً:\n  "
            + "\n  ".join(offenders),
        )

    # ── #42 جزء ٣: إثبات الشكلين اللذين وسّعهما الحارس فعلياً ─────────────

    def test_aliased_variable_str_prod_is_detected(self):
        """الشكل الحرفي في `logistics/services.py` قبل إصلاح #42 (`str(prod)`)."""
        offenders = _line_offenders(
            "some/display_module.py",
            "name=getattr(prod, 'name_ar', None) or str(prod),",
        )
        self.assertEqual(
            offenders, ["name=getattr(prod, 'name_ar', None) or str(prod),"],
        )

    def test_str_product_id_is_still_not_a_false_positive(self):
        """`product_id` ليست `product` مقصوصة — لا مطابقة كاذبة (سلوكٌ لم يتغيّر)."""
        offenders = _line_offenders("some/display_module.py", "if str(product_id).isdigit():")
        self.assertEqual(offenders, [])

    # ── #42 جزء ٣: الحدّ الموثَّق — الإقحام النصّي غير مفحوص، وهذا مقصود ─────

    def test_fstring_interpolation_is_a_documented_blind_spot(self):
        """الشكل الذي طلبته #42 (`f"{product}"`) لا يُكتشف — موثَّقٌ أعلى الملف
        لا مسدودٌ ضمنياً. لو وُسِّع الحارس ليكتشفه لأبلغ فوراً عن إحدى عشرة رسالة
        خطأ قائمة سلفاً خارج نطاق هذه التذكرة (انظر توثيق الحدّ في الدوكسترنغ)."""
        offenders = _line_offenders(
            "some/display_module.py",
            'raise ValidationError(f"المنتج «{product}» غير موجود.")',
        )
        self.assertEqual(offenders, [])

    def test_stock_movement_dunder_str_style_stays_allowed(self):
        """`StockMovement.__str__`/`ProductPriceTier.__str__` (قرار #37):
        `f"...{self.product}..."` — GREEN قبل توسيع #42 وبعده على السواء،
        لأن الحدّ لا يفحص أيّ إقحامٍ نصّي إطلاقاً."""
        offenders = _line_offenders(
            "inventory/models.py",
            'return f"{self.get_movement_type_display()} | {self.product} | {self.quantity}"',
        )
        self.assertEqual(offenders, [])
