"""#37/#39: حارس بنيوي — `str(product)` ممنوعة خارج `__str__` نفسها؛
`inventory/services.py` (`product_display_name`) هي الصيغة الوحيدة.

الدرس مدفوعٌ مرّتين: تعليق #22 في `sales/serializers.py` كتب القاعدة صراحةً،
وثلاثة مواضع في **نفس الملف** بقيت على `str(product)` رغم ذلك — الذاكرة لا
تكفي. النظير: `core/tests/test_docs_freshness.py`.

**البساطة شرط بقاء** (نفس سياسة الحارس النظير): يلتقط `str(x.product)` أو
`str(product)` فقط — لا `str(product_id)` (`\\bproduct\\b` لا يطابق الجزء
الأول من `product_id`، فحداً كلمةٍ يفصلهما `_`)، ولا سلسلة تليها
`.isdigit()` (لا كائن Product يملك هذه الدالّة؛ ذاك معاملٌ نصّي من الطلب —
راجع قرار #39 «ليس موضعاً أصلاً»)، ولا الأسطر التي تبدأ بـ`#` (تعليقات توثّق
القاعدة نفسها بذكر `str(product)` كمثالٍ للممنوع، لا استدعاءً حقيقياً).
"""
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: `str(unit.product)` أو `str(product)` — لا `str(product_id)`، ولا `str(prod)`.
STR_PRODUCT_RE = re.compile(r"str\(\s*((?:\w+\.)*product)\s*\)(\.\w+)?")

#: خارج الفحص كلياً: الاختبارات، الهجرات، وما ليس كوداً محليّاً (نسخ
#: worktrees في `.claude/` كاملة المستودع — مصدرها يُفحص هناك لا هنا).
SKIP_RE = re.compile(
    r"(^|[\\/])(tests?|migrations)([\\/]|$)|node_modules"
    r"|(^|[\\/])\.claude([\\/]|$)|(^|[\\/])(\.?venv)([\\/]|$)"
)

#: مواضع فيها `str(<...>.product)` تُرك عمداً — كلٌّ بسببٍ موثَّق، لا سهواً.
#: (الملف بصيغة posix، ونصّ السطر بعد strip() — لا رقم سطر، فهو ينزاح.)
ALLOWED = {
    ("after_sales/services.py", "device_name=str(unit.product),"):
        "بطاقة الكفالة التلقائية عند البيع — خارج جرد #39 (16 موضعاً "
        "المُلزَم)؛ ليست من مواضع هذه التذكرة (#41) فتُترك بلا مساس.",
    ("after_sales/services.py", '"product_name": str(unit.product),'):
        "استجابة البحث عن وحدة بالرقم التسلسلي — خارج جرد #39 بنفس السبب.",
}


def _iter_py_files():
    for path in REPO_ROOT.rglob("*.py"):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if SKIP_RE.search(rel):
            continue
        yield path, rel


class StrProductDisplayGuardTest(SimpleTestCase):
    """كل `str(product)` جديد خارج القائمة البيضاء يُسقط هذا الاختبار."""

    def test_no_new_str_product_calls_outside_allowlist(self):
        offenders = []
        for path, rel in _iter_py_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue  # تعليقٌ يوثّق القاعدة بذكر المثال الممنوع، لا نداءً حقيقياً
                for match in STR_PRODUCT_RE.finditer(line):
                    if (match.group(2) or "").lstrip(".") == "isdigit":
                        continue  # معاملٌ نصّي من الطلب لا كائن منتج (#39)
                    if (rel, stripped) in ALLOWED:
                        continue
                    offenders.append(f"{rel}:{number} → {stripped}")
        self.assertEqual(
            offenders, [],
            "str(product) ممنوعة — استعمل `inventory/services.py` "
            "(`product_display_name`) بدلاً منها، أو أضِفها إلى ALLOWED في "
            "هذا الملف مع سببٍ صريح إن كانت متروكةً عمداً:\n  "
            + "\n  ".join(offenders),
        )
