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
النسبةُ تتغيّر، وإقرارُ شهرٍ مضى لا يتغيّر.
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
    BookEntryLine,
    ClientBookAccount,
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
        ("tax", "الضريبة", CELL_MONEY),
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
        ("tax", "مجموع الضريبة"),
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
#: و`taxable`/`tax` (#288/ب-٢) مبلغا تقرير ض.ق.م: أساسٌ خاضعٌ وقيمةُ ضريبة.
REPORT_AMOUNT_KEYS: tuple[str, ...] = (
    "debit", "credit", "balance", "amount", "net",
    "debit_total", "credit_total",
    "opening_balance", "closing_balance",
    "revenue", "expense", "profit", "assets", "liabilities", "equity",
    "liabilities_and_equity", "difference", "taxable", "tax",
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


#: باني كل نوعٍ: `(book, span, **params) -> (rows, totals)`.
def _vat(book, span, **_):
    """ض.ق.م للفترة: **الضريبةُ المسجَّلةُ على بنود الحركات** مجموعاً بنوع الحركة.

    **ولا نسبةَ حيّة**: العمودان `tax_base`/`tax_amount` كُتبا مع الحركة وقتَ
    إدخالها وهما ما يُجمع هنا. ضربُ الأساس في نسبة الشركة اليوم كان يُعيد حسابَ
    إقرار شهرٍ مضى بنسبةٍ لم تكن فيه.

    والصفوفُ **لكل أنواع الحركة** كتقرير القبض/الدفع: صفٌّ يتقلّص يُخفي «لا حركةَ
    بيعٍ هذا الشهر» ويُوهم بغياب البند. والعدُّ عدُّ حركاتٍ **لها ضريبةٌ مسجَّلة**
    (أساسٌ أو قيمة) لا عددُ بنود.

    **والحيّةُ وحدها**: حركةٌ عُكست وضرائبُها خارجَ المجموع (`_live_entries`)، فزوجٌ
    مُلغى يعطي أصفاراً لا ضريبةً مضاعفة.
    """
    logged = _period_lines(book, span).exclude(tax_base=0, tax_amount=0)
    found = {
        row["entry__kind"]: row
        for row in logged.values("entry__kind").annotate(
            count=Count("entry_id", distinct=True),
            taxable=Sum("tax_base"),
            tax=Sum("tax_amount"),
        ).order_by()
    }
    rows = []
    taxable_total = tax_total = _ZERO
    for kind, label in BOOK_ENTRY_KIND_CHOICES:
        row = found.get(kind, {})
        taxable = _zero(row.get("taxable"))
        tax = _zero(row.get("tax"))
        taxable_total += taxable
        tax_total += tax
        rows.append({
            "kind": kind,
            "kind_label": label,
            "count": row.get("count", 0),
            "taxable": _money(taxable),
            "tax": _money(tax),
        })
    return rows, {"taxable": _money(taxable_total), "tax": _money(tax_total)}


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
