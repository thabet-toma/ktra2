"""#37/#39/#42/#43: حارس بنيوي — `str(product)` وإقحامه النصّي `f"{product}"`
ممنوعان خارج `__str__` نفسها؛ `inventory/services.py` (`product_display_name`)
هي الصيغة الوحيدة.

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

**#43 يُقفل الحدّ الذي وثّقه #42:** الحارس الآن يفحص الإقحام النصّي أيضاً —
`{product}`، `{prod}`، أو مساراً بنقطة مثل `{line.product}`/`{part.product}`/
`{it.product}`، بأي منسّق تحويل (`!r`/`!s`/`!a`) أو تهيئة (`:...`) بعدها. هذا
كان يُبلِّغ فوراً عن إحدى عشرة رسالة خطأ ورسالة سجلٍّ مخزَّنة واحدة —
أُصلحت جميعها في #43 (`accounting/opening_balance.py` ×٣،
`logistics/services.py` ×٢، `sales/services/flow.py` ×٥،
`sales/services/orders.py` ×١، و`after_sales/views.py` (`_log_part`) ×١).

**الحدّ الفاصل بين الإقحام الممنوع والمشروع: أن يبدأ المسار بـ`self.`
حرفياً.** `{self.product}` في `StockMovement.__str__`/`ProductPriceTier.__str__`
(قرار #37) هوية الصفّ للمطوّر لا رسالة للقارئ، فتبقى مسموحة دون أي إدراج في
`ALLOWED` — القاعدة مبنية في الفاحص نفسه لا استثناءً يُدار يدوياً. وأي مسارٍ
آخر، عارياً أو بنقطة (`line.`/`part.`/`it.`/أي اسم سوى `self`)، يُعامَل
كإقحام كائن منتجٍ حقيقي إن لم يكن أصلاً `self.`.

**مطابقاتٌ كاذبة محروسة صراحةً:** `{product_id}` و`{products}` و
`{product_name}` و`{self.product_id}` ليست كائن منتج — التعبير النمطي يشترط
أن ينتهي الاسم بـ`product`/`prod` حرفياً قبل رمز التحويل/التهيئة/القوس
المغلق مباشرة، فـ`_id`/`s`/`_name` تكسر المطابقة قبل الوصول لهذا الشرط.

**ولأن الشكل شكل f-string لا أي حاصرتين معقوفتين:** الفحص يقتصر على الأسطر
التي تحوي بادئة f-string فعلية (`f"` أو `f'`)، فلا يُبلِّغ عن حاصرتين في
نصٍّ عادي أو قاموسٍ حرفي لا علاقة له بالتهيئة.
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: `str(unit.product)`، `str(product)`، أو الاسم المستعار `str(prod)`/`str(x.prod)`
#: — لا `str(product_id)`.
STR_PRODUCT_RE = re.compile(r"str\(\s*((?:\w+\.)*(?:product|prod))\s*\)(\.\w+)?")

#: إقحامٌ نصّي: `{product}`، `{prod}`، أو مسارٌ بنقطة مثل `{line.product}` —
#: بأي منسّق تحويل (`!r`/`!s`/`!a`) أو تهيئة (`:...`) بعدها. لا `{product_id}`
#: ولا `{products}` ولا `{product_name}` (يلزم انتهاء الاسم بـ`product`/`prod`
#: حرفياً قبل `!`/`:`/`}`). المجموعة الأولى هي المسار قبل الاسم (فارغةٌ أو
#: تنتهي بنقطة) — `self.` فيها يعني هوية صفٍّ مشروعة (`__str__`)، لا رسالة.
FSTRING_PRODUCT_RE = re.compile(
    r"\{((?:\w+\.)*)(?:product|prod)(?:![rsa])?(?::[^}]*)?\}"
)

#: مؤشرٌ بسيط على أن السطر يحوي f-string فعلياً — لا حاصرتين في نصٍّ عادي.
FSTRING_PREFIX_RE = re.compile(r"[rR]?[fF]['\"]|[fF][rR]['\"]")

#: خارج الفحص كلياً: الاختبارات، الهجرات، وما ليس كوداً محليّاً (نسخ
#: worktrees في `.claude/` كاملة المستودع — مصدرها يُفحص هناك لا هنا).
SKIP_RE = re.compile(
    r"(^|[\\/])(tests?|migrations)([\\/]|$)|node_modules"
    r"|(^|[\\/])\.claude([\\/]|$)|(^|[\\/])(\.?venv)([\\/]|$)"
)

#: مواضع فيها `str(<...>.product)` أو `f"{...product}"` تُرك عمداً — كلٌّ
#: بسببٍ موثَّق، لا سهواً. (الملف بصيغة posix، ونصّ السطر بعد strip() — لا رقم
#: سطر، فهو ينزاح.)
ALLOWED = {}


def _iter_py_files():
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if SKIP_RE.search(rel):
            continue
        yield path, rel


def _line_offenders(rel: str, line: str) -> list[str]:
    """مطابقات `STR_PRODUCT_RE`/`FSTRING_PRODUCT_RE` الحقيقية في سطرٍ واحد —
    لا تعليقات، لا في `ALLOWED`."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return []  # تعليقٌ يوثّق القاعدة بذكر المثال الممنوع، لا نداءً حقيقياً
    if (rel, stripped) in ALLOWED:
        return []

    offenders = []
    for match in STR_PRODUCT_RE.finditer(line):
        if (match.group(2) or "").lstrip(".") == "isdigit":
            continue  # معاملٌ نصّي من الطلب لا كائن منتج (#39)
        offenders.append(stripped)

    if FSTRING_PREFIX_RE.search(line):
        for match in FSTRING_PRODUCT_RE.finditer(line):
            path_prefix = match.group(1) or ""
            if path_prefix == "self.":
                continue  # هوية الصفّ للمطوّر — `__str__` مشروعة (#37)
            offenders.append(stripped)

    return offenders


class StrProductDisplayGuardTest(SimpleTestCase):
    """كل `str(product)` أو `f"{product}"` جديد (أو اسمٌ مستعار له) خارج
    القائمة البيضاء يُسقط هذا الاختبار."""

    def test_no_new_str_product_calls_outside_allowlist(self):
        offenders = []
        for path, rel in _iter_py_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                for stripped in _line_offenders(rel, line):
                    offenders.append(f"{rel}:{number} → {stripped}")
        self.assertEqual(
            offenders, [],
            "str(product) / f\"{product}\" ممنوعتان — استعمل "
            "`inventory/services.py` (`product_display_name`) بدلاً منهما، أو "
            "أضِفها إلى ALLOWED في هذا الملف مع سببٍ صريح إن كانت متروكةً عمداً:\n  "
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

    # ── #43: الإقحام النصّي صار مكتشَفاً ───────────────────────────────────

    def test_bare_fstring_interpolation_is_detected(self):
        """الشكل الذي وثّقه #42 كحدٍّ أعمى (`f"{product}"`) صار يُكتشف الآن."""
        offenders = _line_offenders(
            "some/display_module.py",
            'raise ValidationError(f"المنتج «{product}» غير موجود.")',
        )
        self.assertEqual(
            offenders, ['raise ValidationError(f"المنتج «{product}» غير موجود.")'],
        )

    def test_dotted_path_fstring_interpolation_is_detected(self):
        """المسار بنقطة (`{line.product}`, `{part.product}`) نفس الحكم."""
        for expr in ("line.product", "part.product", "it.product"):
            with self.subTest(expr=expr):
                offenders = _line_offenders(
                    "some/display_module.py",
                    f'raise ValidationError(f"البند «{{{expr}}}» خدمة.")',
                )
                self.assertEqual(
                    offenders, [f'raise ValidationError(f"البند «{{{expr}}}» خدمة.")'],
                )

    def test_stock_movement_dunder_str_style_stays_allowed(self):
        """`StockMovement.__str__`/`ProductPriceTier.__str__` (قرار #37):
        `f"...{self.product}..."` تبقى خضراء — المسار يبدأ بـ`self.` حرفياً."""
        offenders = _line_offenders(
            "inventory/models.py",
            'return f"{self.get_movement_type_display()} | {self.product} | {self.quantity}"',
        )
        self.assertEqual(offenders, [])

    def test_product_id_fstring_is_not_a_false_positive(self):
        offenders = _line_offenders(
            "some/display_module.py",
            'raise ValidationError(f"المنتج #{product_id} غير متاح في الشركة الحالية")',
        )
        self.assertEqual(offenders, [])

    def test_products_plural_fstring_is_not_a_false_positive(self):
        offenders = _line_offenders(
            "some/display_module.py", 'logger.info(f"loaded {products} rows")',
        )
        self.assertEqual(offenders, [])

    def test_product_name_fstring_is_not_a_false_positive(self):
        offenders = _line_offenders(
            "some/display_module.py", 'raise ValidationError(f"غير صالح: {product_name}")',
        )
        self.assertEqual(offenders, [])

    def test_self_product_id_fstring_is_not_a_false_positive(self):
        offenders = _line_offenders(
            "inventory/models.py", 'return f"{self.product_id}"',
        )
        self.assertEqual(offenders, [])
