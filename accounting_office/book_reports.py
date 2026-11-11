"""تقاريرُ دفتر الزبون (#288/أ) — تُحسَب من القائم: لا هجرة ولا حقلَ جديد.

**المبدأ: التقاريرُ قراءةٌ محضة.** لا جدولَ ملخّصٍ ولا عمودَ «رصيد» ولا هجرة:
الحركةُ والبنودُ تحمل الحقيقة، والتقريرُ يعيد تجميعَها. وحاجةٌ حقيقيّةٌ إلى حقلٍ
تُبلَّغ ولا تُنفَّذ من هنا.

**والحيُّ وحده يُقرأ.** كلُّ استعلامٍ يبدأ من `client_books._live_entries()` —
الحركةُ المعكوسةُ **وعكسُها** خارجَ كل مجموع، فقيدٌ ثم عكسُه يعطي أصفاراً لا
مجموعاً مضاعفاً. نسخةٌ ثانية من هذا الشرط هنا كانت ستُبقي الزوجَ في الميزان
فيختلّ بلا سببٍ ظاهر.

**والحسابُ في قاعدة البيانات.** التجميعُ `values(…).annotate(Sum(…))` على
`BookEntryLine`، والترشيحُ بالفترة في `WHERE`. بايثون لا يرى إلا صفاً لكل **حساب**
(أو لكل نوع حركة)، ويُجمع ذلك العددُ القليلُ بعدئذٍ. الاستثناءُ الوحيدُ الرصيدُ
الجرّ في كشف الحساب: تراكمٌ تسلسليٌّ على الصفوف المعروضة نفسِها، وليس مسحاً
لتجميعِ مجموع.

**والمبالغُ `Decimal` نصّاً بخانتين** (كـ`client_books._amount`) لا `float`: كشفُ
حسابٍ بآلاف الحركات يخسر هللةً على `float` ولا أحدَ يراها.

**والقناعُ يطال الصفوفَ والمجاميع** — عضوٌ بلا `office.amounts.view` يصله `None`
في كل مفتاحِ مبلغ، وتبقى البنيةُ والتسمياتُ والتواريخُ كما هي.

**ولا `vat` في هذا الجزء.** نسبتُه تحتاج قراراً: لا نوعَ حسابٍ ضريبيٍّ في النماذج
اليوم، واستنتاجُه من اسم حسابٍ في الشجرة مخترَعٌ لا قاعدة. تُترك لِتذكرةٍ تُقرّر
مصدرَ النسبة أوّلاً.
"""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
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

#: التسميةُ العربيةُ لكل تقرير — يقرؤها الفهرسُ وعنوانُ الحمولة (حقلٌ واحد).
REPORT_LABELS: dict[str, str] = {
    REPORT_CASH: "قبض ودفع",
    REPORT_INCOME: "إيرادات ومصاريف",
    REPORT_RECEIVABLES: "ذمم",
    REPORT_TRIAL_BALANCE: "ميزان مراجعة",
    REPORT_PROFIT_LOSS: "أرباح وخسائر",
    REPORT_BALANCE_SHEET: "ميزانية",
    REPORT_STATEMENT: "كشف حساب",
}

#: معاملاتٌ لا يقوم التقريرُ بغيرها — يُرسَل للواجهة كي لا تخمّن.
REPORT_PARAMS: dict[str, tuple[str, ...]] = {
    REPORT_STATEMENT: ("account", "party"),
}

#: الأنواعُ المتاحةُ لكل نوع دفتر — البسيطُ لا يعطي ميزانَ مراجعة، والمزدوجُ لا
#: يعطي قبضاً ودفعاً: التقريرُ يتبع معنى الدفتر لا ذوقَ القائمة.
REPORTS_BY_BOOK_KIND: dict[str, tuple[str, ...]] = {
    BOOK_KIND_SIMPLE: (REPORT_CASH, REPORT_INCOME, REPORT_RECEIVABLES),
    BOOK_KIND_DOUBLE: (
        REPORT_TRIAL_BALANCE, REPORT_PROFIT_LOSS, REPORT_BALANCE_SHEET,
        REPORT_STATEMENT,
    ),
}

#: العلامةُ المائيةُ على كل استجابة — وهي ما يُطبع على المستخرج في الجزء (ب).
WATERMARK = "نسخة عمل"

#: مفاتيحُ المبالغ في حمولات التقارير — تُقنَّع كلُّها في الصفوف والمجاميع.
REPORT_AMOUNT_KEYS: tuple[str, ...] = (
    "debit", "credit", "balance", "amount", "net",
    "opening_balance", "closing_balance",
    "revenue", "expense", "profit", "assets", "liabilities", "equity",
    "liabilities_and_equity", "difference",
)

#: أنواعُ الحساب المديّنةُ الطبع — والباقي دائنيّة. القاعدةُ واحدةٌ هنا.
_DEBIT_NATURED = frozenset({BOOK_ACCOUNT_TYPE_ASSET, BOOK_ACCOUNT_TYPE_EXPENSE})
_PROFIT_TYPES = (BOOK_ACCOUNT_TYPE_REVENUE, BOOK_ACCOUNT_TYPE_EXPENSE)
_RECEIVABLE_TYPES = (BOOK_ACCOUNT_TYPE_ASSET, BOOK_ACCOUNT_TYPE_LIABILITY)
_SHEET_TYPES = (
    BOOK_ACCOUNT_TYPE_ASSET, BOOK_ACCOUNT_TYPE_LIABILITY, BOOK_ACCOUNT_TYPE_EQUITY,
)

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


def period_for(raw_from=None, raw_to=None, *, today=None):
    """`(from, to)` من معاملَي الطلب — والافتراضُ من بداية السنة إلى اليوم.

    «بدايةُ سنة الدفتر» هي بدايةُ سنةِ نهاية الفترة (السنةُ الجارية افتراضاً):
    الفترةُ الافتراضيةُ سنةٌ واحدةٌ لا تاريخُ الفتح كلُّه، فالدفترُ المحوَّلُ إلى
    المزدوج يحمل في سنواته البسيطةِ قيوداً بطرفٍ واحدٍ لا يتوازن ميزانُها.
    """
    today = today or _today()
    end = _parse_day(raw_to, "to") or today
    start = _parse_day(raw_from, "from") or datetime.date(end.year, 1, 1)
    if start > end:
        raise ValidationError({"from": "بدايةُ الفترة بعد نهايتها — اعكس الطرفين."})
    return start, end


# ── خطوطُ الحساب: الحيّةُ وحدها، والتجميعُ في القاعدة ───────────────────────
def _live_lines(book):
    """بنودُ الحركات الحيّة في هذا الدفتر — القاعدةُ في `_live_entries`."""
    return BookEntryLine.objects.filter(
        entry__in=_live_entries(),
        entry__client_book=book,
    )


def _period_lines(book, span):
    start, end = span
    return _live_lines(book).filter(
        entry__entry_date__gte=start,
        entry__entry_date__lte=end,
    )


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
    """أرضيةُ الرصيد: صافي ما قبل الفترة من الحركة الحيّة وحدها."""
    aggregated = _live_lines(book).filter(entry__entry_date__lt=day).aggregate(
        debit=Sum("debit"), credit=Sum("credit"),
    )
    return _zero(aggregated["debit"]) - _zero(aggregated["credit"])


# ── البسيط ─────────────────────────────────────────────────────────────────
def _cash(book, span, **_):
    """قبضٌ ودفع: لكل نوع حركةٍ مجموعُ المدين ومجموعُ الدائن والعدّ.

    والصفوفُ **خمسةٌ دائماً بترتيب النموذج** وإن خلا نوعٌ من حركة: جدولٌ يتقلّص
    بتقلّص الشهر يُخفي «لا حركة بنكٍ هذا الشهر» ويُوهم بغياب البند.
    والأرضيةُ (`opening_balance`) صافي ما قبل الفترة، والختامُ أرضيةٌ + صافيها —
    فالسطرُ الأخير في التقرير يطابق رصيدَ الصندوق والبنك فعلياً.
    """
    start, _end = span
    found = {
        row["entry__kind"]: row
        for row in _period_lines(book, span).values("entry__kind")
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
    """ذمم: أرصدةُ حسابات الأصول والخصوم — مدينون مقابل دائنين."""
    grouped = _account_sums(book, span, account_types=_RECEIVABLE_TYPES)
    rows = [
        {
            **_account_head(row),
            "debit": _money(_zero(row["debit"])),
            "credit": _money(_zero(row["credit"])),
            "balance": _money(_natural(
                row["account__account_type"], _zero(row["debit"]), _zero(row["credit"]),
            )),
        }
        for row in grouped
    ]
    assets = _sum_natural(grouped, BOOK_ACCOUNT_TYPE_ASSET)
    liabilities = _sum_natural(grouped, BOOK_ACCOUNT_TYPE_LIABILITY)
    return rows, {
        "assets": _money(assets),
        "liabilities": _money(liabilities),
        "balance": _money(assets - liabilities),
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
    """ميزانية: أصولٌ مقابل خصومٍ وحقوقِ ملكية — وربحُ الفترة يُقفل في الطرف الثاني.

    لا قيودَ إقفالٍ في هذا الدفتر، فالإيراداتُ والمصاريفُ ما زالت في حساباتها؛
    وميزانيةٌ تُقابل الأصولَ بالخصوم والحقوق وحدَهما لا تتوازن في أيّ شركةٍ رابحة.
    فالربحُ (`profit`) يُجمع إلى الخصوم والحقوق، و`difference` يجب أن يكون صفراً —
    وإلا 409 كالميزان.
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
_BUILDERS = {
    REPORT_CASH: _cash,
    REPORT_INCOME: _profit_rows,
    REPORT_RECEIVABLES: _receivables,
    REPORT_TRIAL_BALANCE: _trial_balance,
    REPORT_PROFIT_LOSS: _profit_rows,
    REPORT_BALANCE_SHEET: _balance_sheet,
    REPORT_STATEMENT: _statement,
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
    span = period_for(raw_from, raw_to)
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
        "book_kind": book.kind,
        "book_kind_label": BOOK_KIND_LABELS.get(book.kind, book.kind),
        "watermark": WATERMARK,
        "rows": rows,
        "totals": totals,
    }
    return _mask_payload(payload) if masked else payload
