"""تقاريرُ دفتر الزبون (#288/أ) — تُحسَب من القائم: لا هجرة ولا حقلَ جديد.

**المبدأ: التقاريرُ قراءةٌ محضة.** لا جدولَ ملخّصٍ ولا عمودَ «رصيد» ولا هجرة:
الحركةُ والبنودُ تحمل الحقيقة، والتقريرُ يعيد تجميعَها. وحاجةٌ حقيقيّةٌ إلى حقلٍ
تُبلَّغ ولا تُنفَّذ من هنا.

**والحيُّ وحده يُقرأ.** كلُّ استعلامٍ يبدأ من `client_books._live_entries()` —
الحركةُ المعكوسةُ **وعكسُها** خارجَ كل مجموع، فقيدٌ ثم عكسُه يعطي أصفاراً لا
مجموعاً مضاعفاً. نسخةٌ ثانية من هذا الشرط هنا كانت ستُبقي الزوجَ في الميزان
فيختلّ بلا سببٍ ظاهر.

**وللكتاب المحوَّل عهدان: بسيطٌ ثم مزدوج.** الدفترُ المحوَّلُ حمل في سنواته البسيطة
قيوداً بطرفٍ واحدٍ — مشروعةٌ يومَها ولا تُقابل. فالتقاريرُ المزدوجة (ميزانُ مراجعة،
أرباحٌ وخسائر، ميزانية) لا تبدأ قبل `double_entry_start(book)` — **وهو للمحوَّل
وحده** (1 يناير من سنة `kind_changed_on`، لا `opened_on`)، والميزانيةُ تبدأ منه
دائماً لأنها رصيدٌ لا حركةَ فترة. **والدفترُ الذي لم يتحوّل لا عهدَ له**: لا قصَّ
ولا 400، وميزانيتُه تبدأ من بداية الدفتر (`book_start`). والقصُّ **يُعلَن** في
الحمولة (`clipped` و`period_note`) ولا يُفعل صامتاً؛ و**409 يبقى لخللٍ حقيقيّ** في
البيانات لا لفترةٍ تشمل سنواتِ البسيط.

**والحسابُ في قاعدة البيانات.** التجميعُ `values(…).annotate(Sum(…))` على
`BookEntryLine`، والترشيحُ بالفترة في `WHERE`. بايثون لا يرى إلا صفاً لكل **حساب**
(أو لكل نوع حركة)، ويُجمع ذلك العددُ القليلُ بعدئذٍ. الاستثناءُ الوحيدُ الرصيدُ
الجرّ في كشف الحساب: تراكمٌ تسلسليٌّ على الصفوف المعروضة نفسِها، وليس مسحاً
لتجميعِ مجموع.

**والمبالغُ `Decimal` نصّاً بخانتين** (كـ`client_books._amount`) لا `float`: كشفُ
حسابٍ بآلاف الحركات يخسر هللةً على `float` ولا أحدَ يراها.

**والقناعُ يطال الصفوفَ والمجاميع** — عضوٌ بلا `office.amounts.view` يصله `None`
في كل مفتاحِ مبلغ، وتبقى البنيةُ والتسمياتُ والتواريخُ كما هي.

**ولا `vat` حيّاً في هذا الجدول.** نوعُه (#288/ب-٢) يجمع **الضريبةَ المسجَّلةَ على
بنود الحركات** (`BookEntryLine.tax_base`/`tax_amount`) لا نسبةً تُضرب عند القراءة:
النسبةُ تتغيّر، وإقرارُ شهرٍ مضى لا يتغيّر. **وضريبتان لا ضريبة**: سطرُ الإيراد
مخرجاتٌ وسطرُ مديّنة الطبع مدخلات، والمستحقُّ المخرجاتُ ناقصَ **المدخلات المعترف
بها** (`_recognised_input`) لا مجموعهما ولا المدخلاتِ كاملةً — وهو رقمُ
`vat_from_book` نفسُه.
"""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Count, Min, Sum
from django.utils import timezone

from accounting_office import client_books, services
# `_live_entries` و`_amount` مخصّصتان في `client_books` عمداً: قاعدةُ «الحركة
# الحيّة» وشكلُ المبلغ مصدرُهما الواحد، ونسخةٌ ثانية هنا تفترق عنهما بصمت.
from accounting_office.client_books import _amount as _money, _live_entries
from accounting_office.models import (
    BOOK_ACCOUNT_TYPE_ASSET,
    BOOK_ACCOUNT_TYPE_EQUITY,
    BOOK_ACCOUNT_TYPE_EXPENSE,
    BOOK_ACCOUNT_TYPE_LABELS,
    BOOK_ACCOUNT_TYPE_LIABILITY,
    BOOK_ACCOUNT_TYPE_REVENUE,
    BOOK_ENTRY_KIND_CHOICES,
    BOOK_ENTRY_KIND_LABELS,
    BOOK_KIND_DOUBLE,
    BOOK_KIND_LABELS,
    BOOK_KIND_SIMPLE,
    THRESHOLD_KIND_CHOICES,
    THRESHOLD_KIND_GIFTS_CAP,
    THRESHOLD_KIND_HOSPITALITY_CAP,
    THRESHOLD_KIND_PHONE_CAP,
    BookEntryLine,
    ClientBookAccount,
    TaxThreshold,
)

# ── أنواعُ التقارير: ثوابت لا نصوصٌ مبعثرة ────────────────────────────────
REPORT_CASH = "cash"
REPORT_INCOME = "income"
REPORT_RECEIVABLES = "receivables"
REPORT_TRIAL_BALANCE = "trial_balance"
REPORT_PROFIT_LOSS = "profit_loss"
REPORT_BALANCE_SHEET = "balance_sheet"
REPORT_STATEMENT = "statement"
REPORT_VAT = "vat"

#: التسميةُ العربيةُ لكل تقرير — يقرؤها الفهرسُ وعنوانُ الحمولة (حقلٌ واحد).
REPORT_LABELS: dict[str, str] = {
    REPORT_CASH: "قبض ودفع",
    REPORT_INCOME: "إيرادات ومصاريف",
    REPORT_RECEIVABLES: "ذمم",
    REPORT_TRIAL_BALANCE: "ميزان مراجعة",
    REPORT_PROFIT_LOSS: "أرباح وخسائر",
    REPORT_BALANCE_SHEET: "ميزانية",
    REPORT_STATEMENT: "كشف حساب",
    REPORT_VAT: "ض.ق.م للفترة",
}

#: معاملاتٌ لا يقوم التقريرُ بغيرها — يُرسَل للواجهة كي لا تخمّن.
REPORT_PARAMS: dict[str, tuple[str, ...]] = {
    REPORT_STATEMENT: ("account", "party"),
}

#: الأنواعُ المتاحةُ لكل نوع دفتر — البسيطُ لا يعطي ميزانَ مراجعة، والمزدوجُ لا
#: يعطي قبضاً ودفعاً: التقريرُ يتبع معنى الدفتر لا ذوقَ القائمة. **و`vat` للاثنين**
#: (#288/ب-٢): ضريبةُ الفترة تُقرأ من البنود المسجَّلة لا من شجرةٍ بعينها.
REPORTS_BY_BOOK_KIND: dict[str, tuple[str, ...]] = {
    BOOK_KIND_SIMPLE: (REPORT_CASH, REPORT_INCOME, REPORT_RECEIVABLES, REPORT_VAT),
    BOOK_KIND_DOUBLE: (
        REPORT_TRIAL_BALANCE, REPORT_PROFIT_LOSS, REPORT_BALANCE_SHEET,
        REPORT_STATEMENT, REPORT_VAT,
    ),
}

# ── الأعمدةُ والمجاميع كما تُعرَض (#288/ب-١) ────────────────────────────────
#
# **تعريفُ العمود الواحد هنا لا في المُخرِج ولا في القالب.** الأعمدةُ صفةُ
# التقرير لا صفةُ الملفّ: نسخةٌ في `book_exports` وأخرى في قالب الطباعة تفترق
# عند أوّل عمودٍ يُضاف، فيخرج ملفُّ Excel بعمودٍ لا تعرفه الورقة — والمستخرجُ
# الذي يخالف الشاشة أسوأُ من غيابه. ومُخرِجا (ب) يقرآن هذا الجدولَ وحده.
CELL_TEXT = "text"
CELL_COUNT = "count"
CELL_MONEY = "money"

#: `(مفتاحُ الحمولة، التسمية، نوعُ الخليّة)` — بترتيب العرض.
REPORT_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {
    REPORT_CASH: (
        ("kind_label", "نوع الحركة", CELL_TEXT),
        ("count", "عدد الحركات", CELL_COUNT),
        ("debit", "مدين", CELL_MONEY),
        ("credit", "دائن", CELL_MONEY),
        ("net", "الصافي", CELL_MONEY),
    ),
    REPORT_INCOME: (
        ("account_code", "الكود", CELL_TEXT),
        ("account_name", "الحساب", CELL_TEXT),
        ("account_type_label", "النوع", CELL_TEXT),
        ("amount", "المبلغ", CELL_MONEY),
    ),
    REPORT_RECEIVABLES: (
        ("side_party", "الطرف", CELL_TEXT),
        ("debit", "مدين", CELL_MONEY),
        ("credit", "دائن", CELL_MONEY),
        ("balance", "الرصيد", CELL_MONEY),
    ),
    REPORT_TRIAL_BALANCE: (
        ("account_code", "الكود", CELL_TEXT),
        ("account_name", "الحساب", CELL_TEXT),
        ("debit", "مدين", CELL_MONEY),
        ("credit", "دائن", CELL_MONEY),
        ("balance", "الرصيد", CELL_MONEY),
    ),
    REPORT_PROFIT_LOSS: (
        ("account_code", "الكود", CELL_TEXT),
        ("account_name", "الحساب", CELL_TEXT),
        ("account_type_label", "النوع", CELL_TEXT),
        ("amount", "المبلغ", CELL_MONEY),
    ),
    REPORT_BALANCE_SHEET: (
        ("account_code", "الكود", CELL_TEXT),
        ("account_name", "الحساب", CELL_TEXT),
        ("account_type_label", "النوع", CELL_TEXT),
        ("balance", "الرصيد", CELL_MONEY),
    ),
    REPORT_STATEMENT: (
        ("entry_date", "التاريخ", CELL_TEXT),
        ("number", "الرقم", CELL_COUNT),
        ("kind_label", "نوع الحركة", CELL_TEXT),
        ("memo", "البيان", CELL_TEXT),
        ("side_party", "الطرف", CELL_TEXT),
        ("debit", "مدين", CELL_MONEY),
        ("credit", "دائن", CELL_MONEY),
        ("balance", "الرصيد", CELL_MONEY),
    ),
    REPORT_VAT: (
        ("kind_label", "نوع الحركة", CELL_TEXT),
        ("count", "عدد الحركات", CELL_COUNT),
        ("taxable", "الأساس الخاضع", CELL_MONEY),
        ("output_tax", "ضريبة المخرجات", CELL_MONEY),
        ("input_tax", "ضريبة المدخلات", CELL_MONEY),
        ("recognised_input", "المدخلات المعترف بها", CELL_MONEY),
        ("non_deductible", "غير المخصوم", CELL_MONEY),
        ("tax_due", "المستحقّ", CELL_MONEY),
    ),
}

#: `(مفتاحُ المجموع، تسميتُه)` — بترتيب العرض تحت الجدول.
#: و`balanced` وحده ليس مبلغاً: قيمتُه تُترجَم إلى «نعم/لا».
REPORT_TOTALS: dict[str, tuple[tuple[str, str], ...]] = {
    REPORT_CASH: (
        ("opening_balance", "رصيد افتتاحي"),
        ("debit", "مجموع المدين"),
        ("credit", "مجموع الدائن"),
        ("net", "الصافي"),
        ("closing_balance", "رصيد ختامي"),
    ),
    REPORT_INCOME: (
        ("revenue", "إيرادات"),
        ("expense", "مصاريف"),
        ("profit", "الصافي"),
    ),
    REPORT_RECEIVABLES: (
        ("debit_total", "مجموع المدين"),
        ("credit_total", "مجموع الدائن"),
    ),
    REPORT_TRIAL_BALANCE: (
        ("debit", "مجموع المدين"),
        ("credit", "مجموع الدائن"),
        ("balanced", "متوازن"),
    ),
    REPORT_PROFIT_LOSS: (
        ("revenue", "إيرادات"),
        ("expense", "مصاريف"),
        ("profit", "الصافي"),
    ),
    REPORT_BALANCE_SHEET: (
        ("assets", "الأصول"),
        ("liabilities", "الخصوم"),
        ("equity", "حقوق الملكية"),
        ("profit", "ربح الفترة"),
        ("liabilities_and_equity", "الخصوم وحقوق الملكية"),
        ("difference", "الفرق"),
    ),
    REPORT_STATEMENT: (
        ("opening_balance", "رصيد افتتاحي"),
        ("debit", "مجموع المدين"),
        ("credit", "مجموع الدائن"),
        ("net", "الصافي"),
        ("closing_balance", "رصيد ختامي"),
    ),
    REPORT_VAT: (
        ("taxable", "مجموع الأساس الخاضع"),
        ("output_tax", "ضريبة المخرجات"),
        ("input_tax", "ضريبة المدخلات"),
        ("recognised_input", "المدخلات المعترف بها"),
        ("non_deductible", "غير المخصوم"),
        ("tax_due", "المستحقّ"),
    ),
}

#: ترجمةُ مفتاح المجموع المنطقيّ — لا `True`/`False` على ورقةٍ عربية.
_BOOLEAN_LABELS: dict[bool, str] = {True: "نعم", False: "لا"}

#: العلامةُ المائيةُ على كل استجابة — وهي ما يُطبع على المستخرج في الجزء (ب).
WATERMARK = "نسخة عمل"

#: ملاحظةُ `receivables`: رصيدٌ تراكميّ من بداية الدفتر حتى `to`، فـ`from` ليست ترشيحاً له.
RECEIVABLES_PERIOD_NOTE = (
    "التقريرُ رصيدٌ تراكميٌّ من بداية الدفتر حتى نهاية الفترة — لا يبدأ من بدايتها."
)

#: مفاتيحُ المبالغ في حمولات التقارير — تُقنَّع كلُّها في الصفوف والمجاميع.
#: و`taxable`/`output_tax`/`input_tax`/`recognised_input`/`non_deductible`/`tax_due`
#: (#288/ب-٢) مبالغُ تقرير ض.ق.م: أساسٌ خاضع، وضريبةُ المخرجات، وضريبةُ المدخلات،
#: والمعترفُ به منها، وغيرُ المخصوم، والمستحقُّ (المخرجات − المعترف به).
REPORT_AMOUNT_KEYS: tuple[str, ...] = (
    "debit", "credit", "balance", "amount", "net",
    "debit_total", "credit_total",
    "opening_balance", "closing_balance",
    "revenue", "expense", "profit", "assets", "liabilities", "equity",
    "liabilities_and_equity", "difference", "taxable",
    "output_tax", "input_tax", "recognised_input", "non_deductible", "tax_due",
)

#: أنواعُ الحساب المديّنةُ الطبع — والباقي دائنيّة. القاعدةُ واحدةٌ هنا.
_DEBIT_NATURED = frozenset({BOOK_ACCOUNT_TYPE_ASSET, BOOK_ACCOUNT_TYPE_EXPENSE})
_PROFIT_TYPES = (BOOK_ACCOUNT_TYPE_REVENUE, BOOK_ACCOUNT_TYPE_EXPENSE)
_SHEET_TYPES = (
    BOOK_ACCOUNT_TYPE_ASSET, BOOK_ACCOUNT_TYPE_LIABILITY, BOOK_ACCOUNT_TYPE_EQUITY,
)

#: تقاريرُ العهد المزدوج وكيف تُقرأ بدايتُها — جدولٌ واحدٌ لا ثوابتُ متفرّقة.
#: `clip` تُقصّ إلى العهد المزدوج إن سبقته `from`، و`always` تبدأ منه دائماً (رصيدٌ
#: حتى `to` لا حركةُ فترة) — **ولا عهدَ إلا للمحوَّل** (`double_entry_start` ⇒ `None`
#: لما لم يتحوّل): فهناك لا قصَّ لـ`clip`، وتبدأ `always` من بداية الدفتر
#: (`book_start`). وغيابُ التقرير من الجدول = **لا حدَّ عهدٍ لبدايته**:
#: كشفُ الحساب قائمةُ حركاتٍ على حسابٍ أو طرف، وحركةُ عهدٍ بسيطٍ من تاريخه فلا
#: تُحجب — والتقاريرُ البسيطة لا عهدَ مزدوجَ فيها أصلاً.
_ERA_CLIP = "clip"
_ERA_ALWAYS = "always"
_ERA_STARTS: dict[str, str] = {
    REPORT_TRIAL_BALANCE: _ERA_CLIP,
    REPORT_PROFIT_LOSS: _ERA_CLIP,
    REPORT_BALANCE_SHEET: _ERA_ALWAYS,
}

#: ملاحظةُ فترةٍ لكل نوعٍ لا يبدأ من `from` لسببٍ آخر — جدولٌ لا فرعٌ في الباني.
_PERIOD_NOTES: dict[str, str] = {
    REPORT_RECEIVABLES: RECEIVABLES_PERIOD_NOTE,
}

#: أرصدةٌ تراكميّةٌ **من بداية الدفتر** حتى `to` لا حركةُ فترة، ولا شأنَ لها بالعهد
#: المزدوج (تُعرض للدفتر البسيط وحده): `from` المعروضةُ بدايةُ الدفتر لا `from`
#: المطلوبة، فلا يحمل الرأسُ تاريخاً لا يصف البيانات.
_FROM_BOOK_START = frozenset({REPORT_RECEIVABLES})

_ZERO = Decimal("0")
#: هللةُ تقريبِ الضريبة المعترف بها — إهلاكُ أصلٍ وخصمُ مدخلاتٍ بخانتين كالمبالغ.
_CENT = Decimal("0.01")


class ReportImbalance(Exception):
    """ميزانٌ لا يتوازن — **خطأٌ صريح** لا صفرٌ مصطنع ولا طرحٌ يخفي الخلل.

    الحمولةُ تحمل المجموعين (مقنَّعين إن كان القارئُ لا يرى المبالغ)، لأن الرقمَ
    وحده يقول للمحاسب أين ينظر. والـview يحوّلها **409** لا 400: الطلبُ سليمٌ
    والبياناتُ هي المكسورة.
    """

    def __init__(self, message, *, totals):
        super().__init__(message)
        self.totals = totals


# ── الفترة: مصدرٌ واحد للترشيح ─────────────────────────────────────────────
def _today() -> datetime.date:
    return timezone.localdate()


def _parse_day(raw, field):
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise ValidationError(
            {field: "تاريخٌ غير صالح — الصيغة YYYY-MM-DD."},
        ) from None


def fiscal_year_start(book, end):
    """بدايةُ السنة المالية للدفتر التي تنتهي عند `end` أو تسبقه.

    `fiscal_year_start` على الدفتر «شهر-يوم» (1/1 افتراضاً، #288/ب-٢). فإن وقعت
    البدايةُ في سنة `end` نفسها **بعد** `end` فالسنةُ الماليةُ بدأت في السنة
    السابقة — بدأت في تموز ونحن في حزيران. و`book=None` يعني 1/1: الدالةُ تُرى
    وحدها في الاختبارات وفي نداءٍ بلا دفتر، فلا يلزمها حضورُ كائنٍ ليُعرَف الافتراض.
    """
    if book is None:
        return datetime.date(end.year, 1, 1)
    month, day = client_books.fiscal_year_start_parts(book.fiscal_year_start)
    start = datetime.date(end.year, month, day)
    return start if start <= end else datetime.date(end.year - 1, month, day)


def period_for(raw_from=None, raw_to=None, *, book=None, today=None):
    """`(from, to)` من معاملَي الطلب — والافتراضُ من بداية السنة المالية إلى اليوم.

    الفترةُ الافتراضيةُ **سنةٌ ماليةٌ واحدة** (سنةُ نهاية الفترة، أي الجارية) لا
    تاريخُ الدفتر كلُّه: عرضٌ افتراضيٌّ مضبوطٌ لا مسحُ عمر. وبدايتُها من
    `fiscal_year_start` على الدفتر (#288/ب-٢) لا «1 كانون الثاني» المثبَّت — ولا
    مصدرَ ثانٍ للفترة: هذه الدالةُ وحدها تحلّها، يقرؤها المسارُ المفردُ والمصنَّفُ
    الكامل.

    وحدُّ العهد المزدوج **ليس هنا**: تفرضه `_report_span` على تقارير المزدوج وحدها
    (والميزانيةُ تبدأ منه دائماً)، فلا يُحمَّل هذا المساعدُ قاعدةً ليست له.
    """
    today = today or _today()
    end = _parse_day(raw_to, "to") or today
    start = _parse_day(raw_from, "from") or fiscal_year_start(book, end)
    if start > end:
        raise ValidationError({"from": "بدايةُ الفترة بعد نهايتها — اعكس الطرفين."})
    return start, end


def double_entry_start(book) -> datetime.date | None:
    """بدايةُ العهد المزدوج — **للدفتر المحوَّل وحده**، و`None` لما لم يتحوّل.

    مصدرُ العهد الوحيدُ في النموذج `kind_changed_on`: المحوَّلُ من البسيط صار
    مزدوجاً من **بداية سنته** (`client_books.change_kind` يمنع التغيير في سنة
    الفتح ويشترط سنةً نظيفة)، وما قبلها حركاتُ طرفٍ واحدٍ مشروعة بالتصميم —
    `_assert_balanced` لا تُسأل عنها. فالتقريرُ المزدوج لا يبدأ قبل هذا اليوم:
    وإلا جمع في الميزان قيوداً لا تتوازن فأعلن 409 على بياناتٍ سليمة.

    **و`opened_on` ليست حدَّ عهد**: افتراضُها يومُ إنشاء الدفتر، ولا شيء يمنع قيداً
    بتاريخٍ قبلها — وهو المسارُ العادي لاستقبال زبون (دفترٌ يُفتح في منتصف السنة ثم
    تُدخل حركاتُ يناير). فإدخالُها هنا كان يُخفي قيداً مقبولاً من الميزانية ويردّ
    400 على فترةٍ فيها بياناتٌ. ودفترٌ محوَّلٌ `opened_on` فيه بعد سنة التحويل لا
    يُسقط بها قيوداً مزدوجةً واقعةً بين السنتين.

    والدفترُ **الذي لم يتحوّل** لا حدَّ عهدٍ له (`None`): كلُّ قيوده من تاريخها
    مزدوجة، فلا قصَّ ولا 400 — وميزانيتُه تبدأ من `book_start`.
    """
    changed = book.kind_changed_on
    if changed is None:
        return None
    return datetime.date(changed.year, 1, 1)


def book_start(book) -> datetime.date:
    """بدايةُ الدفتر: `min(opened_on, أوّل حركةٍ حيّة)` — كي يكون `from` المعروضُ صادقاً.

    `opened_on` وحدها تكذب حين تسبقها حركةٌ (دفترٌ فُتح في مارس وفيه قيدُ يناير)،
    والحركةُ الحيّةُ وحدها تُهمل دفتراً فارغاً. والحيّةُ لا غير: زوجٌ معكوسٌ لا
    يُقدّم بداية الدفتر.
    """
    first = _live_entries().filter(client_book=book).aggregate(
        first=Min("entry_date"),
    )["first"]
    return book.opened_on if first is None else min(book.opened_on, first)


# ── خطوطُ الحساب: الحيّةُ وحدها، والتجميعُ في القاعدة ───────────────────────
def _live_lines(book):
    """بنودُ الحركات الحيّة في هذا الدفتر — القاعدةُ في `_live_entries`."""
    live_entries = _live_entries().filter(client_book=book)
    return BookEntryLine.objects.filter(entry__in=live_entries)


def _in_span(lines, span):
    start, end = span
    return lines.filter(
        entry__entry_date__gte=start,
        entry__entry_date__lte=end,
    )


def _period_lines(book, span):
    return _in_span(_live_lines(book), span)


def _cash_lines(book, span=None):
    """بنودُ **الأصول** وحدها — النقدُ والبنك في شجرة البسيط — وفي الفترة إن حُدّدت.

    فرعُ الأصول في الشجرة البسيطة هو الصندوق والبنك وحدهما
    (`accounting_office/migrations/0011_client_books.py`)، فحصرُ المجموع فيه هو
    ما يجعل «القبض/الدفع» رصيداً مصرفياً لا مجموعَ بنود الدفتر كلِّه.
    """
    lines = _live_lines(book).filter(account__account_type=BOOK_ACCOUNT_TYPE_ASSET)
    return lines if span is None else _in_span(lines, span)


def _account_sums(book, span, *, account_types=None):
    """صفٌّ لكل حساب: مجموعُ المدين ومجموعُ الدائن — استعلامٌ واحدٌ لا حلقة."""
    lines = _period_lines(book, span)
    if account_types:
        lines = lines.filter(account__account_type__in=account_types)
    return list(
        lines
        .values("account__code", "account__name", "account__account_type")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code"),
    )


def _zero(value) -> Decimal:
    return value if value is not None else _ZERO


def _natural(account_type, debit, credit) -> Decimal:
    """رصيدُ الحساب بطبيعته: الأصولُ والمصاريفُ مدينيّة، والخصومُ والحقوقُ والإيرادُ دائنيّة."""
    if account_type in _DEBIT_NATURED:
        return debit - credit
    return credit - debit


def _sum_natural(grouped, account_type) -> Decimal:
    total = _ZERO
    for row in grouped:
        if row["account__account_type"] == account_type:
            total += _natural(account_type, _zero(row["debit"]), _zero(row["credit"]))
    return total


def _account_head(row) -> dict:
    account_type = row["account__account_type"]
    return {
        "account_code": row["account__code"],
        "account_name": row["account__name"],
        "account_type": account_type,
        "account_type_label": BOOK_ACCOUNT_TYPE_LABELS.get(account_type, account_type),
    }


def _net_before(book, day) -> Decimal:
    """أرضيةُ القبض/الدفع: صافي **الأصول** قبل الفترة — نقدٌ وبنك فقط."""
    aggregated = _cash_lines(book).filter(entry__entry_date__lt=day).aggregate(
        debit=Sum("debit"), credit=Sum("credit"),
    )
    return _zero(aggregated["debit"]) - _zero(aggregated["credit"])


# ── البسيط ─────────────────────────────────────────────────────────────────
def _cash(book, span, **_):
    """قبضٌ ودفع على **حسابات النقد والبنك وحدها** (أصولُ شجرة البسيط).

    مدينُ الأصول قبضٌ ودائنُها دفع. وجمعُ كل الأنواع كان يُدخل الإيرادَ الدائنَ
    في جهة الدفع والمصروفَ المدينَ في جهة القبض، فيخرج «رصيدٌ» لا يطابق صندوقاً
    ولا بنكاً — والاختبارُ نفسه كان يثبّت −160 وصندوقُ البيانات 180.

    والصفوفُ **خمسةٌ دائماً بترتيب النموذج** وإن خلا نوعٌ من حركة نقدية: جدولٌ
    يتقلّص يُخفي «لا حركة بنكٍ هذا الشهر» ويُوهم بغياب البند. والعدُّ عدُّ حركاتٍ
    **لها بندٌ نقديّ** لا عدُّ حركات. والأرضيةُ (`opening_balance`) صافي الأصول
    قبل الفترة، والختامُ أرضيةٌ + صافيها: السطرُ الأخير يطابق رصيد الصندوق والبنك.
    """
    start, _end = span
    found = {
        row["entry__kind"]: row
        for row in _cash_lines(book, span).values("entry__kind")
        .annotate(
            count=Count("entry_id", distinct=True),
            debit=Sum("debit"),
            credit=Sum("credit"),
        )
        .order_by()
    }
    rows = []
    debit_total = credit_total = _ZERO
    for kind, label in BOOK_ENTRY_KIND_CHOICES:
        row = found.get(kind, {})
        debit = _zero(row.get("debit"))
        credit = _zero(row.get("credit"))
        debit_total += debit
        credit_total += credit
        rows.append({
            "kind": kind,
            "kind_label": label,
            "count": row.get("count", 0),
            "debit": _money(debit),
            "credit": _money(credit),
            "net": _money(debit - credit),
        })
    net = debit_total - credit_total
    opening = _net_before(book, start)
    return rows, {
        "debit": _money(debit_total),
        "credit": _money(credit_total),
        "net": _money(net),
        "opening_balance": _money(opening),
        "closing_balance": _money(opening + net),
    }


def _profit_rows(book, span, **_):
    """إيراداتٌ ومصاريفُ لكل حسابٍ برصيده الطبيعيّ — وأرباحُ وخسائر مجموعُها."""
    grouped = _account_sums(book, span, account_types=_PROFIT_TYPES)
    rows = [
        {
            **_account_head(row),
            "amount": _money(_natural(
                row["account__account_type"], _zero(row["debit"]), _zero(row["credit"]),
            )),
        }
        for row in grouped
    ]
    revenue = _sum_natural(grouped, BOOK_ACCOUNT_TYPE_REVENUE)
    expense = _sum_natural(grouped, BOOK_ACCOUNT_TYPE_EXPENSE)
    return rows, {
        "revenue": _money(revenue),
        "expense": _money(expense),
        "profit": _money(revenue - expense),
    }


def _receivables(book, span, **_):
    """ذمم: رصيدُ كل **طرف** (`side_party`) تراكميّاً **حتى نهاية الفترة**.

    الشجرةُ البسيطة **بلا ذممٍ بالتصميم** — لا `1300` مدينون ولا `2100` دائنون
    (`0011_client_books.py`) — فالصندوقُ والبنك ليسا ذمّة، وعرضُهما هنا كان يعطي
    «مدينين» رصيدَه 180 وهو نقد. والطرفُ المقابل هو ما يحمل الذمّة: اسمٌ مسجَّلٌ
    على البند، لكلٍّ مدينُه ودائنُه ورصيدُه.

    **والحسابُ من منظور الطرف لا من منظور البند**: `side_party` هو الطرفُ
    **المقابل** للبند، فبندٌ مدينٌ على الصندوق من طرف X يعني أنّ X دفع لنا، وبندٌ
    دائنٌ على 4100 يعني أنّا بعنا X. فـ**مدينُ الطرف = Σ`credit`** للبند (ما لنا
    عليه) و**دائنُه = Σ`debit`** (ما دفعه)، والرصيدُ = مدينُه − دائنُه، والموجبُ **لنا
    عليه**: فاتورةُ بيعٍ غيرُ مدفوعةٍ (4100 دائن 300) = +300، وقبضُها (1100 مدين 300)
    يعيده إلى 0. بحساب `debit − credit` الخام كانت الفاتورةُ −300.

    **وهو رصيدٌ لا حركةُ فترة**: يُجمع من بداية الدفتر إلى `to`، و`from` لا يقصّه —
    ذمّةُ سنةٍ سابقة لا تختفي لأنها خارج الشهر المطلوب. ولهذا يُرسَل معه
    `period_note` صريحاً، وتُعرض `from` **بدايةَ الدفتر** (`_report_span`) لا المطلوبة.
    """
    _start, end = span
    grouped = list(
        _live_lines(book)
        .filter(entry__entry_date__lte=end)
        .exclude(side_party="")
        .values("side_party")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("side_party"),
    )
    rows = []
    debit_total = credit_total = _ZERO
    for row in grouped:
        # مقلوبان عمداً: مدينُ الطرف ما سُجّل **دائناً** على البند، ودائنُه المدين.
        party_debit = _zero(row["credit"])
        party_credit = _zero(row["debit"])
        debit_total += party_debit
        credit_total += party_credit
        rows.append({
            "side_party": row["side_party"],
            "debit": _money(party_debit),
            "credit": _money(party_credit),
            "balance": _money(party_debit - party_credit),
        })
    return rows, {
        "debit_total": _money(debit_total),
        "credit_total": _money(credit_total),
    }


# ── المزدوج ────────────────────────────────────────────────────────────────
def _trial_balance(book, span, **_):
    """ميزانُ مراجعة: لكل حسابٍ Σمدين وΣدائن والرصيد (مدينٌ موجباً).

    والتوازنُ **يُفحص ويُصرَّح**: مجموعُ المدين يجب أن يساوي مجموعَ الدائن بالضبط،
    وإلا خرج 409 بمجموعَي الطرفين. ميزانٌ يمرّ صامتاً برقمٍ غير متوازنٍ أسوأ من
    صفحةِ خطأ: يُوقَّع ويُقدَّم.
    """
    grouped = _account_sums(book, span)
    rows = [
        {
            **_account_head(row),
            "debit": _money(_zero(row["debit"])),
            "credit": _money(_zero(row["credit"])),
            "balance": _money(_zero(row["debit"]) - _zero(row["credit"])),
        }
        for row in grouped
    ]
    debit_total = sum((_zero(row["debit"]) for row in grouped), _ZERO)
    credit_total = sum((_zero(row["credit"]) for row in grouped), _ZERO)
    balanced = debit_total == credit_total
    totals = {
        "debit": _money(debit_total),
        "credit": _money(credit_total),
        "balanced": balanced,
    }
    if not balanced:
        raise ReportImbalance(
            "الميزان غير متوازن: مجموع المدين لا يساوي مجموع الدائن في هذه الفترة.",
            totals=totals,
        )
    return rows, totals


def _balance_sheet(book, span, **_):
    """ميزانية: أصولٌ مقابل خصومٍ وحقوقِ ملكية — وربحُ العهد يُقفل في الطرف الثاني.

    **والنطاقُ من بداية العهد المزدوج (للمحوَّل) أو بداية الدفتر (لما لم يتحوّل) إلى
    `to`** لا حركةَ الفترة: ميزانيةُ اليوم ترصيدٌ تراكميّ، وحركةُ سنةٍ واحدة تُسقط
    رأسَ المال وكلَّ نقدٍ سابق وتبقى «متوازنة» بأرقامٍ خاطئة. الـ`report_payload`
    يمرّر هذا النطاق (انظر `double_entry_start` و`book_start`).

    ولا قيودَ إقفالٍ في هذا الدفتر، فالإيراداتُ والمصاريفُ ما زالت في حساباتها؛
    وميزانيةٌ تُقابل الأصولَ بالخصوم والحقوق وحدَهما لا تتوازن في أيّ شركةٍ رابحة.
    فالربحُ (`profit`) تراكميٌّ على النطاق نفسِه ويُجمع إلى الخصوم والحقوق،
    و`difference` يجب أن يكون صفراً — وإلا 409 كالميزان.
    """
    grouped = _account_sums(book, span)
    rows = [
        {
            **_account_head(row),
            "balance": _money(_natural(
                row["account__account_type"], _zero(row["debit"]), _zero(row["credit"]),
            )),
        }
        for row in grouped
        if row["account__account_type"] in _SHEET_TYPES
    ]
    assets = _sum_natural(grouped, BOOK_ACCOUNT_TYPE_ASSET)
    liabilities = _sum_natural(grouped, BOOK_ACCOUNT_TYPE_LIABILITY)
    equity = _sum_natural(grouped, BOOK_ACCOUNT_TYPE_EQUITY)
    profit = (
        _sum_natural(grouped, BOOK_ACCOUNT_TYPE_REVENUE)
        - _sum_natural(grouped, BOOK_ACCOUNT_TYPE_EXPENSE)
    )
    liabilities_and_equity = liabilities + equity + profit
    totals = {
        "assets": _money(assets),
        "liabilities": _money(liabilities),
        "equity": _money(equity),
        "profit": _money(profit),
        "liabilities_and_equity": _money(liabilities_and_equity),
        "difference": _money(assets - liabilities_and_equity),
    }
    if assets != liabilities_and_equity:
        raise ReportImbalance(
            "الميزانية غير متوازنة: الأصول لا تساوي الخصوم وحقوق الملكية.",
            totals=totals,
        )
    return rows, totals


def _statement_filters(book, *, account, party) -> dict:
    """حسابٌ أو طرف — لا الاثنان ولا دونهما، والحسابُ من شجرة الزبون نفسها."""
    account = (account or "").strip()
    party = (party or "").strip()
    if account and party:
        raise ValidationError({"account": "حدِّد حساباً أو طرفاً — لا الاثنين معاً."})
    if account:
        row = ClientBookAccount.objects.filter(client=book.client, code=account).first()
        if row is None:
            raise ValidationError({"account": "لا حسابَ بهذا الكود في شجرة الزبون."})
        return {"account": row}
    if party:
        return {"side_party": party}
    raise ValidationError({
        "account": "كشفُ الحساب يحتاج حساباً أو طرفاً — `account` أو `party`.",
    })


def _statement(book, span, *, account="", party="", **_):
    """كشفُ حسابٍ أو طرفٍ في فترة، برصيدٍ جارٍ يبدأ من أرضية ما قبلها.

    والرصيدُ الجارُّ يُراكم على الصفوف المعروضة نفسِها (تراكمٌ تسلسليّ لا مسحُ
    جدولٍ لتجميعِ مجموع)، ومجموعا المدين والدائن والأرضيةُ تُحسب في القاعدة.
    """
    start, end = span
    lines = _live_lines(book).filter(**_statement_filters(
        book, account=account, party=party,
    ))
    before = lines.filter(entry__entry_date__lt=start).aggregate(
        debit=Sum("debit"), credit=Sum("credit"),
    )
    opening = _zero(before["debit"]) - _zero(before["credit"])
    rows = []
    running = opening
    debit_total = credit_total = _ZERO
    for line in lines.filter(
        entry__entry_date__gte=start, entry__entry_date__lte=end,
    ).select_related("entry").order_by(
        "entry__entry_date", "entry__year", "entry__number", "entry__id", "id",
    ):
        debit = line.debit or _ZERO
        credit = line.credit or _ZERO
        debit_total += debit
        credit_total += credit
        running += debit - credit
        rows.append({
            "entry_id": line.entry_id,
            "entry_date": line.entry.entry_date.isoformat(),
            "year": line.entry.year,
            "number": line.entry.number,
            "kind": line.entry.kind,
            "kind_label": BOOK_ENTRY_KIND_LABELS.get(line.entry.kind, line.entry.kind),
            "memo": line.entry.memo,
            "side_party": line.side_party,
            "debit": _money(debit),
            "credit": _money(credit),
            "balance": _money(running),
        })
    net = debit_total - credit_total
    return rows, {
        "opening_balance": _money(opening),
        "debit": _money(debit_total),
        "credit": _money(credit_total),
        "net": _money(net),
        "closing_balance": _money(opening + net),
    }


#: ضريبتان لا ضريبةٌ واحدة (إصلاحُ #288): سطرُ الإيراد مخرجاتٌ يُدفع، وسطرُ
#: المصروف/الأصل مدخلاتٌ يُخصم — وجمعُهما كان يقول للمحاسب «تدفع 240» وفي الدفتر
#: 80. والمفتاحان يُقرآن في الصفوف والمجاميع معاً.
VAT_OUTPUT = "output"
VAT_INPUT = "input"

#: الحساباتُ التي لضريبتها حكمٌ — الإيرادُ مخرجاتٌ ومديّنةُ الطبع مدخلات.
_VAT_INPUT_TYPES: tuple[str, ...] = tuple(sorted(_DEBIT_NATURED))
_VAT_ACCOUNT_TYPES: tuple[str, ...] = (BOOK_ACCOUNT_TYPE_REVENUE, *_VAT_INPUT_TYPES)


def _tax_bucket(account_type) -> str | None:
    """حكمُ سطرِ الضريبة: **مخرجاتٌ** على الإيراد و**مدخلاتٌ** على مديّنة الطبع.

    و`None` لما ليس منهما (خصومٌ وحقوقُ ملكية): ضريبةٌ على حسابِ التزامٍ ليست
    مخرجاتٍ ولا مدخلات، فتُترك خارج المجموعين لا تُوزَّع على أحدهما.

    **والقاعدةُ واحدةٌ هنا** يقرؤها تقريرُ ض.ق.م (`_vat`) و`vat_from_book` (#287/٤):
    نسخةٌ ثانية منها كانت ستُخرج تقريراً وإقراراً بقاعدتين لدفترٍ واحد.
    """
    if account_type == BOOK_ACCOUNT_TYPE_REVENUE:
        return VAT_OUTPUT
    if account_type in _DEBIT_NATURED:
        return VAT_INPUT
    return None


#: مفتاحُ المدخلات المعترف بها في تجميع `_vat` — حقلٌ ثالثٌ بجانب المخرجات
#: والمدخلات الكاملة، يُملأ سطراً سطراً لا بجمعٍ في القاعدة.
_VAT_RECOGNISED = "recognised"


def _vat_rate_context(book) -> tuple[str, dict]:
    """نظامُ الزبون الضريبيّ ولائحةُ مكتبه — `(system, overrides)` مرّةً للحساب.

    يقرؤها تقريرُ ض.ق.م (`_vat`) و`vat_from_book` معاً: ما يُعترف به من مدخلاتٍ
    يُحسب بالنظام واللائحة نفسِهما في الاثنين.
    """
    from accounting_office import book_rates

    system = services.resolve_setting(
        book.tenant, services.TAX_SYSTEM_KEY, client=book.client,
    )
    return system, book_rates.office_override_map(book.tenant, system)


def _recognised_input(line, *, tenant, system, overrides) -> tuple[Decimal, Decimal, bool]:
    """`(الضريبة، المعترف به منها، راجع؟)` لسطر مدخلاتٍ — **القاعدةُ الوحيدة للطرح**.

    المعترفُ به `الضريبة × نسبة السطر` (`book_rates.recognised_vat_rate`: نسبةُ
    السطر إن كُتبت وإلا نسبةُ حسابه من اللائحة وإلا 100%) **مقرَّباً لهللةٍ على كل
    سطرٍ** لا على المجموع. وتقريرُ ض.ق.م و`vat_from_book` يُنادياها معاً، فلا يخرج
    للدفتر الواحد رقمان: مرّةً طُرحت المدخلاتُ كاملةً هنا والمعترفُ بها هناك فقال
    التقريرُ «المستحقّ 0.00» والالتزامُ 56.67.
    """
    from accounting_office import book_rates

    tax = line.tax_amount or _ZERO
    rate, review = book_rates.recognised_vat_rate(
        line, tenant=tenant, tax_system=system, overrides=overrides,
    )
    return tax, (tax * rate / Decimal("100")).quantize(_CENT), review


class _LineTax:
    """شكلُ السطر الذي تقرؤه `_recognised_input` **قبل أن يُحفظ السطر**.

    `paper_input_tax` تبنيها من الحساب والضريبة وحدهما: بنودُ الورقة تُولَّد
    كقواميس ثم تمرّ بـ`_prepare_lines`، فلا كائنَ `BookEntryLine` بعد. فنسبتُه
    هنا غائبةٌ والنسبةُ من الحساب **وقتَ التوليد** — وهي نفسُها التي يكتبها
    `client_books` على السطر الحامل للضريبة (`paper_input_rate`)، فالسطرُ المحفوظ
    يحمل نسبةَ التوليد ويقرؤها `_recognised_input` منه لا من الحساب بعدها.
    """

    __slots__ = ("tax_amount", "vat_rate", "account")

    def __init__(self, *, tax_amount, vat_rate, account):
        self.tax_amount = tax_amount
        self.vat_rate = vat_rate
        self.account = account


def paper_input_rate(book, *, account, context=None) -> tuple[Decimal, bool]:
    """`(نسبةُ الاعتراف، راجع؟)` لحسابٍ مدين وقتَ توليد حركةٍ من ورقة.

    القاعدةُ نفسُها `book_rates.recognised_vat_rate` التي تقرؤها `_recognised_input`
    — ومنها تُكتب النسبةُ على السطر المولَّد فتُجمَّد، ويُرفض التوليدُ حين تكون
    «راجع» (`(0, True)`) فلا يُجمَّد قرارٌ لم يُتَّخذ. و`context` كما في
    `paper_input_tax`.
    """
    from accounting_office import book_rates

    system, overrides = context if context is not None else _vat_rate_context(book)
    return book_rates.recognised_vat_rate(
        _LineTax(tax_amount=_ZERO, vat_rate=None, account=account),
        tenant=book.tenant, tax_system=system, overrides=overrides,
    )


def paper_input_tax(book, *, account, tax_amount, context=None) -> tuple[Decimal, Decimal]:
    """`(المعترف به، غير المخصوم)` من ضريبة ورقةٍ على حساب مدين — بالقاعدة الواحدة.

    `client_books` يكتب على `2200` المعترفَ به وحده ويزيد سطرَ المصروف/الأصل
    بالباقي (وبالتقرير البسيط يزيد مصروفَ الفترة). وبلا ذلك كان `non_deductible`
    رقماً في تقرير ض.ق.م **لا يصل كلفةَ أيّ حساب**: تقول الورقةُ «1170» ويقول
    الدفترُ «1000 + 170 التزاماً» ولا أحدَ يدفع الـ56.67 كلفةً.

    **ولا نسبةَ ثانية هنا**: `_recognised_input` وحدها تقرأ نسبةَ الاعتراف
    (بسببٍ `_vat_rate_context`)، فبنودُ الحركة وتقريرُ ض.ق.م ومبلغُ الالتزام
    يقولون الرقمَ نفسه.

    و`context` هو `_vat_rate_context(book)` جاهزاً — يُمرَّر لمن يولّد حركةً من
    عدة أوراق (النظامُ واللائحة لا يتغيّران بين أوراق الحركة الواحدة).
    """
    system, overrides = context if context is not None else _vat_rate_context(book)
    _tax, recognised, _review = _recognised_input(
        _LineTax(tax_amount=_zero(tax_amount), vat_rate=None, account=account),
        tenant=book.tenant, system=system, overrides=overrides,
    )
    return recognised, _zero(tax_amount) - recognised


def _vat(book, span, **_):
    """ض.ق.م للفترة: **مخرجاتٌ ومدخلاتٌ منفصلتان، والمستحقُّ = المخرجات − المدخلات المعترف بها**.

    **ولا نسبةَ حيّةً للشركة**: العمودان `tax_base`/`tax_amount` كُتبا مع الحركة
    وقتَ إدخالها وهما ما يُجمع هنا. ضربُ الأساس في نسبة الشركة اليوم كان يُعيد
    حسابَ إقرار شهرٍ مضى بنسبةٍ لم تكن فيه. **أمّا نسبةُ الاعتراف بالمدخلات**
    (`_recognised_input`) فتُقرأ لكل سطرٍ كما يقرؤها `vat_from_book`: المستحقُّ هنا
    هو مبلغُ الالتزام نفسُه، و«غير المخصوم» هو الباقي الذي يبقى كلفةً.

    **والفصلُ حكمُ الحساب لا نوعِ الحركة** (`_tax_bucket`): ضريبةُ سطرِ الإيراد
    مخرجات، وضريبةُ سطرِ المصروف/الأصل مدخلاتٌ تُخصم بنسبتها. والمجموعُ جمعُ
    `tax_amount` كما سُجّلت (≥ 0، ولا منطقَ إشارةٍ في الكود): فمرتجعٌ يُسجَّل مدينَ
    الإيراد لا يُنقص المخرجاتِ بنفسه، و**عكسُ** القيد الأصليّ (انظر أدناه) هو ما
    يُخرج ضريبتَه من المجموع. وصفٌّ لكل نوع حركة كما في القبض/الدفع — صفٌّ يتقلّص
    يُخفي «لا حركةَ بيعٍ هذا الشهر». والعدُّ عدُّ حركاتٍ **لها ضريبةٌ على سطرٍ ذي
    حكم**.

    **والحيّةُ وحدها**: حركةٌ عُكست وضرائبُها خارجَ المجموع (`_live_entries`)، فزوجٌ
    مُلغى يعطي أصفاراً لا ضريبةً مضاعفة.
    """
    classified = _period_lines(book, span).exclude(
        tax_base=0, tax_amount=0,
    ).filter(account__account_type__in=_VAT_ACCOUNT_TYPES)
    #: العدُّ استعلامٌ ثانٍ لمفتاح الحركة وحده: حركةٌ فيها سطرُ إيرادٍ وسطرُ مصروف
    #: تقع في **مجموعتَي مبلغٍ**، وجمعُ عدَّيهما كان يحسبها مرّتين.
    counts = {
        row["entry__kind"]: row["count"]
        for row in classified.values("entry__kind").annotate(
            count=Count("entry_id", distinct=True),
        ).order_by()
    }
    def blank() -> dict:
        return {
            "taxable": _ZERO, VAT_OUTPUT: _ZERO, VAT_INPUT: _ZERO,
            _VAT_RECOGNISED: _ZERO,
        }

    found: dict[str, dict] = {}
    for row in classified.values("entry__kind", "account__account_type").annotate(
        taxable=Sum("tax_base"), tax=Sum("tax_amount"),
    ).order_by():
        current = found.setdefault(row["entry__kind"], blank())
        current["taxable"] += _zero(row["taxable"])
        current[_tax_bucket(row["account__account_type"])] += _zero(row["tax"])
    #: المعترفُ به سطراً سطراً (نسبةُ كل سطرٍ وتقريبُه): مجموعُ الضريبة وحده يكفيه
    #: التجميعُ في القاعدة، ونسبةُ السطر لا تُجمع.
    system, overrides = _vat_rate_context(book)
    for line in classified.filter(
        account__account_type__in=_VAT_INPUT_TYPES,
    ).select_related("account", "entry"):
        _tax, recognised_line, _review = _recognised_input(
            line, tenant=book.tenant, system=system, overrides=overrides,
        )
        found.setdefault(line.entry.kind, blank())[_VAT_RECOGNISED] += recognised_line
    rows = []
    taxable_total = output_total = input_total = recognised_total = _ZERO
    for kind, label in BOOK_ENTRY_KIND_CHOICES:
        row = found.get(kind, {})
        taxable = _zero(row.get("taxable"))
        output = _zero(row.get(VAT_OUTPUT))
        input_tax = _zero(row.get(VAT_INPUT))
        recognised = _zero(row.get(_VAT_RECOGNISED))
        taxable_total += taxable
        output_total += output
        input_total += input_tax
        recognised_total += recognised
        rows.append({
            "kind": kind,
            "kind_label": label,
            "count": counts.get(kind, 0),
            "taxable": _money(taxable),
            "output_tax": _money(output),
            "input_tax": _money(input_tax),
            "recognised_input": _money(recognised),
            "non_deductible": _money(input_tax - recognised),
            "tax_due": _money(output - recognised),
        })
    return rows, {
        "taxable": _money(taxable_total),
        "output_tax": _money(output_total),
        "input_tax": _money(input_total),
        "recognised_input": _money(recognised_total),
        "non_deductible": _money(input_total - recognised_total),
        "tax_due": _money(output_total - recognised_total),
    }


#: باني كل نوعٍ: `(book, span, **params) -> (rows, totals)`.
_BUILDERS = {
    REPORT_CASH: _cash,
    REPORT_INCOME: _profit_rows,
    REPORT_RECEIVABLES: _receivables,
    REPORT_TRIAL_BALANCE: _trial_balance,
    REPORT_PROFIT_LOSS: _profit_rows,
    REPORT_BALANCE_SHEET: _balance_sheet,
    REPORT_STATEMENT: _statement,
    REPORT_VAT: _vat,
}


# ── القناع: الشكلُ يبقى والقيمةُ تصير `None` ────────────────────────────────
def _mask_payload(payload, keys=REPORT_AMOUNT_KEYS):
    """قناعٌ متداخل: `services.mask_amounts` نسخةً ضحلةً، تُدار هنا على الصفوف والمجاميع."""
    if isinstance(payload, dict):
        masked = services.mask_amounts(payload, keys)
        return {
            key: _mask_payload(value, keys) if isinstance(value, (dict, list)) else value
            for key, value in masked.items()
        }
    if isinstance(payload, list):
        return [
            _mask_payload(item, keys) if isinstance(item, (dict, list)) else item
            for item in payload
        ]
    return payload


# ── القراءةُ العامة: ما يراه الـview ────────────────────────────────────────
def _report_span(book, kind, span):
    """النطاقُ الفعليُّ للتقرير — والمزدوجةُ لدفترٍ **محوَّل** تبدأ من عهده المزدوج.

    القصُّ ليس تسامحاً: حركاتُ سنوات الدفتر البسيطة مشروعةٌ **بطرفٍ واحد**، فجمعُها
    في ميزانٍ أو ميزانيةٍ يُنتج خللاً يبدو خللَ بيانات. والقصُّ يُعلَن في الحمولة
    (`clipped` و`period_note`) لا يُفعل صامتاً، ويبقى 409 لخللٍ حقيقيّ.

    و`clipped` **قصٌّ وحده**: الميزانيةُ حين تكون بدايتُها **قبل** `from` لم تُقصَّ
    شيئاً — هي رصيدٌ يبدأ من العهد بطبيعته، ويقول `period_note` ذلك بدل أن يُسمّى
    قصّاً. ونهايةٌ قبل العهد 400: ميزانيةٌ بلا مدى تُعيد صفحةً فارغةً متوازنةً كذباً.

    **ولا عهدَ لدفترٍ لم يتحوّل** (`double_entry_start` ⇒ `None`): لا قصَّ لميزان
    المراجعة ولا للأرباح والخسائر **ولا 400**، وتبدأ ميزانيتُه (ومعها `receivables`)
    من `book_start` — فـ`from` المعروضةُ تصف البيانات. ونهايةٌ قبل بداية الدفتر
    ليست خطأً هناك: صفحةٌ فارغةٌ صادقة (لا شيءَ قبل الدفتر) لا 400.
    """
    start, end = span
    if kind in _FROM_BOOK_START:
        return (min(book_start(book), end), end), False, None
    rule = _ERA_STARTS.get(kind)
    if rule is None:
        return span, False, None
    floor = double_entry_start(book)
    if floor is None:
        if rule == _ERA_CLIP:
            return span, False, None
        origin = book_start(book)
        if origin > end:
            note = (
                f"نهايةُ الفترة تسبق بداية الدفتر في {origin.isoformat()} — "
                "لا بياناتَ قبلها."
            )
        else:
            note = (
                f"التقريرُ يبدأ من بداية الدفتر في {origin.isoformat()} — "
                "رصيدٌ حتى نهاية الفترة لا حركةُ فترة."
            )
        return (min(origin, end), end), False, note
    if rule == _ERA_CLIP and start >= floor:
        return span, False, None
    if floor > end:
        raise ValidationError({
            "to": (
                f"نهايةُ الفترة تسبق بداية العهد المزدوج في سنة {floor.year} — "
                "لا بياناتَ مزدوجة قبلها."
            ),
        })
    clipped = floor > start
    if clipped:
        note = (
            f"قُصّت بدايةُ الفترة إلى بداية العهد المزدوج في سنة {floor.year} — "
            "سنواتُ الدفتر البسيطة لا تدخل تقاريرَ المزدوج."
        )
    else:
        note = (
            f"التقريرُ يبدأ من بداية العهد المزدوج في سنة {floor.year} — "
            "رصيدٌ حتى نهاية الفترة لا حركةُ فترة."
        )
    return (floor, end), clipped, note


def available_reports(book) -> list[dict]:
    """الأنواعُ المتاحةُ لنوع دفترٍ ما — بتسمياتها ومعاملاتها."""
    return [
        {
            "kind": kind,
            "title": REPORT_LABELS[kind],
            "params": list(REPORT_PARAMS.get(kind, ())),
        }
        for kind in REPORTS_BY_BOOK_KIND.get(book.kind, ())
    ]


def is_report_available(book, kind) -> bool:
    return kind in REPORTS_BY_BOOK_KIND.get(book.kind, ())


def accounts_with_movement(book, span) -> list[dict]:
    """الحساباتُ التي لها **حركةٌ حيّة** في النطاق — `[{"code", "name"}]` بالترتيب.

    مصدرُ «أيّ حسابٍ يستحقّ كشفاً» في مستخرج الدفتر كاملاً (#288/هـ): الكشفُ
    يُبنى لكل حسابٍ ظهر في `_account_sums` (أي له بندٌ حيٌّ في الفترة) ولا يُبنى
    لساكن (ورقةٌ بلا صفوف تُقرأ «لا بيانات» فتُوهم بخلل). والتجميعُ في القاعدة
    كسائر التقارير، لا حلقةَ بنودٍ في بايثون.
    """
    return [
        {"code": row["account__code"], "name": row["account__name"]}
        for row in _account_sums(book, span)
    ]


def reports_index_payload(book) -> dict:
    """`GET client-books/<client_id>/reports/` — ما يمكن طلبُه لهذا الدفتر."""
    return {
        "client": book.client.name,
        "book_kind": book.kind,
        "book_kind_label": BOOK_KIND_LABELS.get(book.kind, book.kind),
        "watermark": WATERMARK,
        "reports": available_reports(book),
    }


def _cell(value, cell_kind) -> dict:
    """خليّةُ جدول: القيمةُ ونوعُها وهل هي مقنَّعة.

    **والنصُّ الغائبُ سلسلةٌ فارغة لا `None`**: Django يطبع `None` كلمةً على
    الصفحة، و«None» في خليّة بيانٍ عيبٌ يُرى. والمبلغُ المقنَّعُ يبقى `None`
    ومعه علامةٌ يعرض القالبُ عليها «—» — لا صفراً يكذب.
    """
    if cell_kind == CELL_MONEY:
        return {"value": value, "kind": cell_kind, "masked": value is None}
    return {"value": "" if value is None else value, "kind": cell_kind, "masked": False}


def table_payload(payload) -> dict:
    """التقريرُ جدولاً جاهزاً للإخراج — أعمدةً وصفوفاً ومجاميع، بلا رقمٍ جديد.

    هذا **شكلُ العرض الواحد** لمُخرِجَي (ب): ملفُّ Excel وورقةُ الطباعة يقرآن
    منه الأعمدةَ نفسها، فلا يفترق مستندان لنفس التقرير. والقيمةُ تخرج **خامّةً**
    (نصُّ المبلغ كما أعطته `_money`) ومعه نوعُها: `book_exports` يحوّلها رقماً في
    الخليّة، والقالبُ يُنسّقها بمرشّحه.

    **والمقنَّعُ يُعلَن `masked`** ولا تُترك قيمتُه بلا علامة — انظر `_cell`.
    """
    kind = payload.get("kind")
    columns = REPORT_COLUMNS.get(kind, ())
    totals = payload.get("totals") or {}
    return {
        "kind": kind,
        "title": payload.get("title", ""),
        "client": payload.get("client", ""),
        "from": payload.get("from", ""),
        "to": payload.get("to", ""),
        "watermark": payload.get("watermark") or WATERMARK,
        "period_note": payload.get("period_note") or "",
        "columns": [
            {"key": key, "label": label, "kind": cell_kind}
            for key, label, cell_kind in columns
        ],
        "rows": [
            [_cell(row.get(key), cell_kind) for key, _label, cell_kind in columns]
            for row in payload.get("rows") or []
        ],
        "totals": [
            {
                # `balanced` وحده منطقيٌّ لا مبلغ: يُترجَم «نعم/لا» ولا يُنسَّق.
                "label": label,
                "value": _BOOLEAN_LABELS[totals[key]]
                if key == "balanced" else totals.get(key),
                "kind": CELL_TEXT if key == "balanced" else CELL_MONEY,
                "masked": key != "balanced" and totals.get(key) is None,
            }
            for key, label in REPORT_TOTALS.get(kind, ())
            if key in totals
        ],
    }


def report_payload(
    book, kind, *, raw_from=None, raw_to=None, user, account="", party="",
) -> dict:
    """تقريرٌ واحد: فترةٌ ثم حسابٌ في الخدمة ثم قناعٌ إن لزم.

    و`user` إلزاميٌّ كـ`services.tax_card_payload`: `None` الصريح وحده نداءٌ
    داخليٌّ بلا قناع، ومن نسي المستخدمَ يسقط عند أوّل استدعاء.
    """
    label = REPORT_LABELS.get(kind)
    if label is None:
        raise ValidationError({"kind": "نوع تقرير غير معروف."})
    span, clipped, note = _report_span(
        book, kind, period_for(raw_from, raw_to, book=book),
    )
    note = note or _PERIOD_NOTES.get(kind)
    masked = client_books.amounts_masked(book.tenant, user)
    try:
        rows, totals = _BUILDERS[kind](book, span, account=account, party=party)
    except ReportImbalance as exc:
        if not masked:
            raise
        raise ReportImbalance(
            str(exc), totals=_mask_payload(exc.totals),
        ) from None
    payload = {
        "kind": kind,
        "title": label,
        "client": book.client.name,
        "from": span[0].isoformat(),
        "to": span[1].isoformat(),
        "clipped": clipped,
        "period_note": note,
        "book_kind": book.kind,
        "book_kind_label": BOOK_KIND_LABELS.get(book.kind, book.kind),
        "watermark": WATERMARK,
        "rows": rows,
        "totals": totals,
    }
    return _mask_payload(payload) if masked else payload


# ── نتيجةُ الفترة والإهلاك والسقوف (#287/٣ و٦ و٧) ───────────────────────────
#
# **ثلاثةُ قراءاتٍ لا تقارير**: «نتيجةُ الفترة» سطرٌ يظهر في ملفّ الزبون وفي إشعار
# الدفع، والإهلاكُ مجموعُ كلفةٍ × نسبةِ أصل، والسقوفُ السنويةُ مبالغُ بنودٍ موسومة
# مقابلَ أرقامٍ منشورة. ولا واحدٌ منها نوعُ تقريرٍ جديد: التقريرُ يُصدَّر ويُطبع،
# وهذه تُقرأ في مواضعها — وإضافةُ نوعٍ ثامنٍ كانت تُثقل الفهرس بلا فائدة.
RESULT_TONE_PROFIT = "profit"
RESULT_TONE_LOSS = "loss"
RESULT_TONE_NEUTRAL = "neutral"
RESULT_TONE_LABELS: dict[str, str] = {
    RESULT_TONE_PROFIT: "ربح",
    RESULT_TONE_LOSS: "خسارة",
    RESULT_TONE_NEUTRAL: "قريب من الصفر",
}

#: مفاتيحُ مبالغ نتيجة الفترة — تُقنَّع في الحمولات كسائر مبالغ الموديول.
RESULT_AMOUNT_KEYS: tuple[str, ...] = ("revenue", "expense", "profit")

#: سقوفُ الإقرار السنوي: تصنيفُ الحساب ← نوعُ السقف المنشور (#287/٧).
#: **جدولٌ واحد** يقرؤه النداءُ ولا يُكرَّر في الـview ولا في الواجهة.
CAP_TAGS: dict[str, str] = {
    "hospitality": THRESHOLD_KIND_HOSPITALITY_CAP,
    "gifts": THRESHOLD_KIND_GIFTS_CAP,
    "phone": THRESHOLD_KIND_PHONE_CAP,
}
CAP_LABELS: dict[str, str] = {
    "hospitality": "الضيافة",
    "gifts": "الهدايا",
    "phone": "الهاتف",
}


def period_result_tone(profit, threshold=0) -> str:
    """لونُ نتيجة الفترة — **ربحٌ أخضر وخسارةٌ حمراء وحدُّ الإشعارات رماديّ**.

    القاعدةُ نفسُها في `appointments.payment_notice_tone`: `|المبلغ| ≤ الحدّ`
    رماديّ (لا «ربحٌ صفريٌّ» يصرخ بالأخضر)، وما فوقه بإشارته. والقاعدتان
    تُقرآن معاً في الشاشة الواحدة، فاختلافُ إحداهما عن الأخرى كان يُنتج لونين
    لرقمٍ واحد.
    """
    profit = Decimal(profit or 0)
    threshold = abs(Decimal(threshold or 0))
    if abs(profit) <= threshold:
        return RESULT_TONE_NEUTRAL
    return RESULT_TONE_PROFIT if profit > 0 else RESULT_TONE_LOSS


def period_result(
    book, *, raw_from=None, raw_to=None, threshold=0, masked=False,
) -> dict:
    """**نتيجةُ الفترة** (إيرادات − مصاريف) بلونها — لملفّ الزبون وإشعار الدفع.

    والمصدرُ هو باني «أرباح وخسائر» نفسُه (`_profit_rows`) لا حسابٌ ثانٍ هنا:
    رقمان لنتيجةٍ واحدةٍ في شاشتين يفترقان عند أوّل تعديلٍ لقاعدةٍ من قواعد
    الحساب. والفترةُ الافتراضيةُ سنةُ الدفتر المالية (`period_for`) كما التقارير.

    **وحدُّ الإشعارات** (رماديّ) هو إعدادُ `payment_notice_gray_threshold`
    نفسُه للزبون — ليس إعداداً ثانياً لنفس السؤال.
    """
    span = period_for(raw_from, raw_to, book=book)
    _rows, totals = _profit_rows(book, span)
    tone = period_result_tone(totals["profit"], threshold)
    result = {
        "from": span[0].isoformat(),
        "to": span[1].isoformat(),
        "revenue": totals["revenue"],
        "expense": totals["expense"],
        "profit": totals["profit"],
        "tone": tone,
        "tone_label": RESULT_TONE_LABELS[tone],
        "threshold": _money(threshold or 0),
        "book_kind": book.kind,
        "book_kind_label": BOOK_KIND_LABELS.get(book.kind, book.kind),
        "watermark": WATERMARK,
    }
    return services.mask_amounts(result, RESULT_AMOUNT_KEYS) if masked else result


def depreciation_payload(book, *, raw_to=None, masked=False) -> dict:
    """**الإهلاكُ السنويُّ بالقسط الثابت**: كلفةُ الأصل × نسبته (#287/٣).

    الكلفةُ من **بداية الدفتر إلى نهاية السنة المالية** لا حركةُ الفترة: نسبةُ
    الإهلاك تُطبَّق على كلفة الأصل الأصليّة (ממחיר הקרן / «من كلفة الشراء» في
    لائحة 2005)، وأصلٌ اشتُري سنة 2024 يُهلَك بنسبته سنة 2026 كما كانت.

    والنسبةُ تُقرأ من الحساب ثم من لائحة المنصّة/المكتب بتصنيفه
    (`book_rates.account_rate`). **و«راجع» لا يُهلَّك**: صفٌّ كهذا يخرج
    `depreciation: null` و`needs_review: true`، والمجموعُ يعلن أنه ناقصٌ — ولا
    يُخترَع للصنف صناعةٍ نسبةٌ وسطاً بين 5% و12%.
    """
    from accounting_office import book_rates

    end = _parse_day(raw_to, "to") or _today()
    start = book_start(book)
    system = services.resolve_setting(
        book.tenant, services.TAX_SYSTEM_KEY, client=book.client,
    )
    overrides = book_rates.office_override_map(book.tenant, system)
    grouped = list(
        _live_lines(book)
        .filter(
            entry__entry_date__lte=end,
            account__account_type=BOOK_ACCOUNT_TYPE_ASSET,
        )
        .values("account__code", "account__name", "account__rate_category")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
        .order_by("account__code"),
    )
    accounts = {
        row.code: row
        for row in ClientBookAccount.objects.filter(
            client=book.client, account_type=BOOK_ACCOUNT_TYPE_ASSET,
        ).exclude(rate_category="", depreciation_rate__isnull=True)
    }
    rows = []
    cost_total = depreciation_total = _ZERO
    review_count = 0
    for row in grouped:
        # **ولا يُهلَّك إلا ما أُعلِن أصلاً**: حسابُ صندوقٍ أو بنكٍ من نوع «أصول»
        # وليس أصلاً ثابتاً — إدراجُه هنا كان يُخرج صفَّ نقدٍ «راجعَ الإهلاك»
        # ويعدّ نقصاً ليس بنقص.
        account = accounts.get(row["account__code"])
        if account is None:
            continue
        cost = _zero(row["debit"]) - _zero(row["credit"])
        rates = book_rates.account_rows(
            account, tenant=book.tenant, tax_system=system, overrides=overrides,
        )
        rate = rates.get(book_rates.RATE_KIND_DEPRECIATION) or {}
        usable = bool(rate.get("usable"))
        annual = (cost * Decimal(rate["rate"]) / Decimal("100")).quantize(_CENT) if (
            usable and cost > 0
        ) else None
        if not usable:
            review_count += 1
        cost_total += cost
        if annual is not None:
            depreciation_total += annual
        rows.append({
            "account_code": row["account__code"],
            "account_name": row["account__name"],
            "rate_category": row["account__rate_category"],
            "rate_category_label": rate.get("label", ""),
            "rate": rate.get("rate"),
            "rate_source": rate.get("source", ""),
            "rate_source_label": rate.get("source_label", ""),
            "needs_review": not usable,
            "cost": _money(cost),
            "depreciation": _money(annual) if annual is not None else None,
        })
    payload = {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "tax_system": system,
        "rows": rows,
        "totals": {
            "cost": _money(cost_total),
            "depreciation": _money(depreciation_total),
        },
        "review_count": review_count,
        "watermark": WATERMARK,
    }
    return (
        _mask_payload(payload, ("cost", "depreciation")) if masked else payload
    )


def annual_alerts_payload(book, *, year=None, masked=False) -> dict:
    """**سقوفُ الإقرار السنوي** — تنبيهٌ من مجموع البنود الموسومة (#287/٧).

    كلُّ تصنيفٍ في `CAP_TAGS` (ضيافةٌ وهدايا وهاتف) يُجمع من بنود حركاتٍ حيّةٍ في
    السنة على الحسابات التي تحمل تصنيفَه — **والوسمُ على الحساب لا على السطر**:
    سطرٌ لا يحمل حساباً فما باله تصنيف؟ والوسمُ يُكتب مرّةً واحدةً على الحساب
    فيسري على حركاته كلها بلا إعادة وسمٍ في كل قيد.

    **وتنبيهٌ لا رفض**: الإقرارُ السنويُّ لم يُبنَ في هذه الشريحة، وهذه قراءةٌ
    تُعرض على المحاسب قبل التقديم — تُنبّه ولا تمنع. والسقفُ من
    `TaxThreshold` (بياناتٌ سنوية: سنةٌ بلا صفٍّ تأخذ آخرَ سقفٍ سابق) و`«راجع»`
    فيه يخرج مع التنبيه لا يُسكِت عنه.
    """
    year = year or _today().year
    system = services.resolve_setting(
        book.tenant, services.TAX_SYSTEM_KEY, client=book.client,
    )
    start = datetime.date(year, 1, 1)
    end = datetime.date(year, 12, 31)
    rows = []
    any_exceeded = False
    review_count = 0
    for code, kind in CAP_TAGS.items():
        threshold = (
            TaxThreshold.objects
            .filter(tax_system=system, kind=kind, year__lte=year)
            .order_by("-year")
            .first()
        )
        totals = _live_lines(book).filter(
            entry__entry_date__gte=start,
            entry__entry_date__lte=end,
            account__rate_category=code,
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        total = _zero(totals["debit"]) - _zero(totals["credit"])
        cap = None if threshold is None else threshold.amount
        needs_review = True if threshold is None else threshold.needs_review
        exceeded = cap is not None and total > cap
        any_exceeded = any_exceeded or exceeded
        review_count += 1 if needs_review else 0
        rows.append({
            "code": code,
            "label": CAP_LABELS[code],
            "cap_kind": kind,
            "cap_label": dict(THRESHOLD_KIND_CHOICES)[kind],
            "total": _money(total),
            "cap": None if cap is None else _money(cap),
            "cap_year": None if threshold is None else threshold.year,
            "cap_note": "" if threshold is None else threshold.note,
            "source_url": "" if threshold is None else threshold.source_url,
            "exceeded": exceeded,
            "needs_review": needs_review,
        })
    payload = {
        "year": year,
        "tax_system": system,
        "rows": rows,
        "any_exceeded": any_exceeded,
        "review_count": review_count,
        "watermark": WATERMARK,
    }
    return _mask_payload(payload, ("total", "cap")) if masked else payload


def vat_from_book(book, *, period_start, period_end) -> dict:
    """**ض.ق.م المستحقّةُ من الدفتر** — مبيعاتٌ ناقصَ المدخلات المعترف بها (#287/٤).

    `ضريبةُ المبيعات` مجموعُ `tax_amount` المسجَّلة على بنود حسابات الإيرادات،
    و`المدخلاتُ المعترف بها` مجموعُ ضريبة كل بندِ مصروفٍ/أصلٍ **× نسبته**: نسبةُ
    السطر إن كُتبت، وإلا نسبةُ حسابه من لائحة المنصّة/المكتب، وإلا 100%. والباقي
    **كلفةٌ لا تُخصم** (`non_deductible`) — وهو الرقمُ الذي يبحث عنه المحاسب حين
    يسأل «ليش ما انخصمت كلها؟».

    ولا رقمَ حيٌّ من نسبةٍ ضريبيةٍ للشركة: العمودان `tax_base`/`tax_amount` كُتبا
    مع الحركة، والنسبةُ المعترف بها تقرأ **تصنيفَ الحساب** لا نسبةً عامّة — فتكرارُ
    حسابٍ صفريّ (بنودُ 100% وبنودُ 2/3 في الدفتر نفسه) يخرج صحيحاً.
    """
    system, overrides = _vat_rate_context(book)
    lines = _live_lines(book).filter(
        entry__entry_date__gte=period_start,
        entry__entry_date__lte=period_end,
    ).select_related("account")
    sales_tax = _ZERO
    input_tax = _ZERO
    recognised = _ZERO
    review_lines = 0
    for line in lines:
        tax = line.tax_amount or _ZERO
        if not tax:
            continue
        bucket = _tax_bucket(line.account.account_type)
        if bucket == VAT_OUTPUT:
            sales_tax += tax
            continue
        if bucket != VAT_INPUT:
            continue
        _tax, recognised_line, review = _recognised_input(
            line, tenant=book.tenant, system=system, overrides=overrides,
        )
        input_tax += tax
        review_lines += 1 if review else 0
        recognised += recognised_line
    return {
        "from": period_start.isoformat(),
        "to": period_end.isoformat(),
        "sales_tax": _money(sales_tax),
        "input_tax": _money(input_tax),
        "recognised_input": _money(recognised),
        "non_deductible": _money(input_tax - recognised),
        "vat_due": _money(sales_tax - recognised),
        "review_lines": review_lines,
    }
