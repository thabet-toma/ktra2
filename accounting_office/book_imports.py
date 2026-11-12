"""استيرادُ شجرة الدفتر وأرصدته من Excel (#288/ب-٢) — **ملفٌّ يُقرأ ثم خدمةٌ قائمة**.

**ما يفعله وما لا يفعله.** يقرأ `openpyxl` ملفّاً بترويسةٍ معروفة، ويتحقّق منه
كاملاً، ثم يكتب في **معاملةٍ واحدة**: يضيف أكوادَ الشجرة الناقصة، ويُحدِّث القائم
(اسمَه وأباه ونوعَه)، ويكتب **حركةً افتتاحيةً واحدة** ببنود الأرصدة غير الصفرية.
**ولا يرقّم ولا يوازن هنا**: الترقيمُ بالقفل والتوازنُ وحارسُ الدور كلُّها في
`client_books.create_entry` — نسخةٌ ثانية منها هنا كانت ستفترق عند أوّل تعديل.

**والتحقّقُ كلُّه قبل أوّل كتابة**: كودٌ مكرَّرٌ أو صفٌّ بنوعٍ مخترَعٍ يُسقط الطلبَ
بلا أثرٍ في القاعدة، فـ«لا يكتب شيئاً إن فسد صفٌّ واحد» ليس أثراً جانبياً
للمعاملة بل شرطٌ مُفحَص. والمعاملةُ طبقةٌ ثانية: لو فشل إدخالُ الحركة بعد الشجرة
عادت الشجرةُ كما كانت.

**والرصيدُ الموقَّع**: الموجبُ مدينٌ والسالبُ دائن — عمودٌ واحدٌ يُقرأ كما يُكتب في
الحاسبة، ولا عمودَي «مدين» و«دائن» يتنازعان صفّاً واحداً. والمجموعُ يجب أن يكون
صفراً، وإلا رُفض الملفُّ برسالةٍ تسمّي **الفرق** لا الطرفين وحدهما.

**ولا يُستنتج حقلٌ من اسمِ عمود**: الترويسةُ أسماؤها ثابتةٌ في `HEADERS`، وتقرؤها
الواجهةُ من `template_bytes()` نفسِه — فتنزيلُ القالب وقراءةُ الملفّ مصدرٌ واحد.
"""
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from accounting_office import client_books
from accounting_office.models import (
    BOOK_ACCOUNT_TYPE_CHOICES,
    BOOK_ENTRY_KIND_OPENING,
    BookEntryLine,
    ClientBookAccount,
)
# `_amount` مخصّصةٌ في `client_books` عمداً: شكلُ المبلغ مصدرُه الواحد، ونسخةٌ
# ثانيةٌ هنا تفترق عنها بصمت — كما في `book_reports` (`_amount as _money`).
from accounting_office.client_books import _amount as _money

#: أعمدةُ الملفّ — بأسمائها العربية كما يكتبها المكتب في ورقة الحساب.
HEADER_CODE = "الكود"
HEADER_NAME = "الاسم"
HEADER_TYPE = "النوع"
HEADER_PARENT = "الأب"
HEADER_BALANCE = "الرصيد"
HEADERS: tuple[str, ...] = (
    HEADER_CODE, HEADER_NAME, HEADER_TYPE, HEADER_PARENT, HEADER_BALANCE,
)

#: عنوانُ ورقة القالب (لا يقرؤه المُستورِد: الأعمدةُ تُطابَق باسمها لا بموضعها).
SHEET_TITLE = "شجرة الحساب والأرصدة"

#: مبلغُ الرصيد: خانتان عشريتان، والفارغُ صفر.
_QUANTUM = Decimal("0.01")
#: ما يُنزع من الرقم قبل قراءته: فواصلُ الآلاف عربيّةً ولاتينيّةً ومسافات.
_THOUSANDS = str.maketrans("", "", ",٬ ")

#: نوعُ الحساب مقروءاً بالمسمّى العربي أو بالقيمة — جدولٌ واحدٌ لا فروع.
_TYPE_BY_TEXT: dict[str, str] = {
    **{label: value for value, label in BOOK_ACCOUNT_TYPE_CHOICES},
    **{value: value for value, _label in BOOK_ACCOUNT_TYPE_CHOICES},
}

#: حدودُ النموذج — يُرفض الصفُّ قبل أن ترفضه القاعدة بـ500.
CODE_MAX = 20
NAME_MAX = 200


def template_bytes() -> bytes:
    """القالبُ النموذجيّ: ملفُّ xlsx فارغٌ بالترويسة الصحيحة، من اليمين لليسار."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET_TITLE
    sheet.sheet_view.rightToLeft = True
    sheet.append(list(HEADERS))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for index in range(1, len(HEADERS) + 1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = 18
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ── القراءة ────────────────────────────────────────────────────────────────
def _cell(row, index):
    return row[index] if index < len(row) else None


def _is_blank(value) -> bool:
    return value is None or not str(value).strip()


def _code_text(value) -> str:
    """كودُ الحساب نصّاً — وخليةٌ رقميّةٌ (`1100.0`) تصير `1100` لا `1100.0`.

    كودُ الحساب نصٌّ في النموذج، وExcel يُعيد ما يكتبه المكتب رقماً حين يبدو رقماً.
    بلا هذا يصير `1100.0` كوداً جديداً في الشجرة يختلف عن `1100` القائم.
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value).strip()


def _header_at(rows) -> tuple[int, tuple]:
    """أوّلُ صفٍّ غير فارغٍ هو الترويسة — وصفٌّ فارغٌ عابرٌ فوقها لا يُسقِط الملفّ."""
    for offset, row in enumerate(rows):
        if any(not _is_blank(value) for value in row):
            return offset, row
    raise ValidationError({"file": "الملفّ فارغ — نزّل القالبَ واملأه."})


def _sheet_rows(content) -> list[tuple]:
    """كلُّ صفوف الورقة النشطة — والملفُّ الفاسد **400 لا 500**."""
    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 — أيُّ فشلٍ في الفكّ = ملفٌّ ليس xlsx
        raise ValidationError({
            "file": "الملفّ ليس ملفَّ Excel صالحاً (.xlsx) — نزّل القالبَ واملأه.",
        }) from None
    try:
        return list(workbook.active.iter_rows(values_only=True))
    finally:
        workbook.close()


def _header_index(header_row) -> dict[str, int]:
    """موضعُ كل عمودٍ باسمه — والترتيبُ حرّ، والاسمُ الغائبُ 400 يسمّيه."""
    texts = ["" if value is None else str(value).strip() for value in header_row]
    missing = [name for name in HEADERS if name not in texts]
    if missing:
        raise ValidationError({
            "file": (
                "الترويسةُ لا تحوي: " + " · ".join(missing)
                + " — نزّل القالبَ ففيه الترويسةُ الصحيحة."
            ),
        })
    return {name: texts.index(name) for name in HEADERS}


def _account_type(value, row_number, code) -> str:
    text = "" if value is None else str(value).strip()
    account_type = _TYPE_BY_TEXT.get(text)
    if account_type is None:
        accepted = " · ".join(label for _value, label in BOOK_ACCOUNT_TYPE_CHOICES)
        raise ValidationError({
            "file": (
                f"الصفّ {row_number}: نوعُ الحساب {code} غير معروف («{text}») — "
                f"المقبول: {accepted}، أو القيمةُ اللاتينية."
            ),
        })
    return account_type


def _balance(value, row_number, code) -> Decimal:
    """رصيدُ الصفّ ليرةً: موجبٌ مدينٌ وسالبٌ دائن — ولا عمودَين يتنازعان صفّاً."""
    if _is_blank(value):
        return Decimal("0")
    try:
        amount = Decimal(str(value).translate(_THOUSANDS)).quantize(_QUANTUM)
    except (ArithmeticError, ValueError):
        raise ValidationError({
            "file": f"الصفّ {row_number}: رصيدُ الحساب {code} ليس رقماً — «{value}».",
        }) from None
    if not amount.is_finite():
        raise ValidationError({
            "file": f"الصفّ {row_number}: رصيدُ الحساب {code} ليس رقماً منتهياً.",
        })
    return amount


def parse_rows(content) -> list[dict]:
    """الملفُّ صفوفاً مُطبَّعة — **كلُّ رفضٍ هنا قبل أوّل كتابة**."""
    rows = _sheet_rows(content)
    header_at, header_row = _header_at(rows)
    index = _header_index(header_row)
    parsed: list[dict] = []
    for offset, row in enumerate(rows[header_at + 1:], start=header_at + 2):
        if all(_is_blank(_cell(row, i)) for i in index.values()):
            continue
        code = _code_text(_cell(row, index[HEADER_CODE]))
        name = "" if _cell(row, index[HEADER_NAME]) is None else str(
            _cell(row, index[HEADER_NAME]),
        ).strip()
        if not code:
            raise ValidationError({"file": f"الصفّ {offset}: كودُ الحساب مطلوب."})
        if len(code) > CODE_MAX:
            raise ValidationError({
                "file": f"الصفّ {offset}: كودُ الحساب أطول من {CODE_MAX} محرفاً.",
            })
        if not name:
            raise ValidationError({
                "file": f"الصفّ {offset}: اسمُ الحساب {code} مطلوب.",
            })
        if len(name) > NAME_MAX:
            raise ValidationError({
                "file": f"الصفّ {offset}: اسمُ الحساب {code} أطول من {NAME_MAX} محرفاً.",
            })
        parsed.append({
            "line": offset,
            "code": code,
            "name": name,
            "account_type": _account_type(
                _cell(row, index[HEADER_TYPE]), offset, code,
            ),
            "parent_code": _code_text(_cell(row, index[HEADER_PARENT])),
            "balance": _balance(_cell(row, index[HEADER_BALANCE]), offset, code),
        })
    if not parsed:
        raise ValidationError({
            "file": "الملفّ لا يحوي صفوفاً — املأ القالبَ صفاً لكل حساب.",
        })
    return parsed


# ── التحقّق من الشجرة والأرصدة ─────────────────────────────────────────────
def _assert_unique_codes(rows) -> None:
    """كودٌ مكرَّرٌ في الملفّ 400 برسالةٍ تسمّيه — صفٌّ واحدٌ لكل كود."""
    seen: dict[str, int] = {}
    for row in rows:
        if row["code"] in seen:
            raise ValidationError({
                "file": (
                    f"الكود {row['code']} مكرَّرٌ في الملفّ: الصفّان "
                    f"{seen[row['code']]} و{row['line']} — صفٌّ واحد لكل كود."
                ),
            })
        seen[row["code"]] = row["line"]


def _assert_parents(client, rows) -> None:
    """الأبُ إمّا في الملفّ أو في شجرة الزبون القائمة — وإلا 400 يسمّي الصفّ."""
    known = set(ClientBookAccount.objects.filter(client=client).values_list(
        "code", flat=True,
    ))
    known.update(row["code"] for row in rows)
    for row in rows:
        if row["parent_code"] and row["parent_code"] not in known:
            raise ValidationError({
                "file": (
                    f"الصفّ {row['line']}: كودُ الأب {row['parent_code']} غير موجود "
                    f"لا في الملفّ ولا في شجرة الزبون."
                ),
            })


def _assert_acyclic(rows) -> None:
    """أبٌ يدور على نفسه شجرةٌ لا تُقرأ ولا تُجمع — يُرفض قبل الكتابة."""
    parent_of = {row["code"]: row["parent_code"] for row in rows}
    for row in rows:
        walk: set[str] = set()
        code = row["code"]
        while code:
            if code in walk:
                raise ValidationError({
                    "file": (
                        f"الصفّ {row['line']}: الأبُ يدور على نفسه عند الكود "
                        f"{row['code']} — شجرةٌ لا تُدار."
                    ),
                })
            walk.add(code)
            code = parent_of.get(code, "")


def _balance_totals(rows) -> tuple[Decimal, Decimal]:
    zero = Decimal("0")
    debit = sum((row["balance"] for row in rows if row["balance"] > 0), zero)
    credit = sum((-row["balance"] for row in rows if row["balance"] < 0), zero)
    return debit, credit


def assert_balanced(rows) -> None:
    """مجموعُ الأرصدة صفرٌ — والرسالةُ تسمّي المدينَ والدائنَ و**الفرق**."""
    debit, credit = _balance_totals(rows)
    if debit != credit:
        raise ValidationError({
            "file": (
                f"الملفّ غير متوازن: المدين {_money(debit)} "
                f"والدائن {_money(credit)} — "
                f"الفرق {_money(abs(debit - credit))}."
            ),
        })


# ── الكتابة: معاملةٌ واحدة ─────────────────────────────────────────────────
def _apply_tree(client, rows):
    """الشجرةُ صفوفاً: إضافةُ الناقص وتحديثُ القائم — **والأبوان في تمريرةٍ ثانية**.

    **والكودُ القائم يُحدَّث لا يُستنسخ**: الزبونُ القادمُ من محاسبٍ آخر يحمل أسماءَ
    حساباتٍ تختلف عن شجرة المنصّة، والنسخُ كان يُبقي اسمَين لكودٍ واحد. ويُستثنى
    **نوعُ** حسابٍ له بنود: تغييرُه يُعيد تصنيفَ تاريخٍ كامل في التقارير، فالملفُّ
    يُرفض ويُصلحه المكتب صراحةً.
    """
    existing = {
        row.code: row for row in ClientBookAccount.objects.filter(client=client)
    }
    used = set(
        BookEntryLine.objects.filter(account__client=client).values_list(
            "account_id", flat=True,
        ),
    )
    created: set[str] = set()
    touched: set[str] = set()
    for row in rows:
        account = existing.get(row["code"])
        if account is None:
            existing[row["code"]] = ClientBookAccount.objects.create(
                client=client,
                code=row["code"],
                name=row["name"],
                account_type=row["account_type"],
                is_system=False,
            )
            created.add(row["code"])
            continue
        fields = []
        if account.name != row["name"]:
            account.name = row["name"]
            fields.append("name")
        if account.account_type != row["account_type"]:
            if account.pk in used:
                raise ValidationError({
                    "file": (
                        f"الصفّ {row['line']}: الحساب {row['code']} مستعملٌ في "
                        "حركات — لا يُغيَّر نوعُه من ملفّ."
                    ),
                })
            account.account_type = row["account_type"]
            fields.append("account_type")
        if fields:
            account.save(update_fields=fields)
            touched.add(row["code"])
    for row in rows:
        account = existing[row["code"]]
        parent = existing.get(row["parent_code"]) if row["parent_code"] else None
        parent_id = parent.pk if parent is not None else None
        if account.parent_id != parent_id:
            account.parent = parent
            account.save(update_fields=["parent"])
            touched.add(row["code"])
    return len(created), len(touched - created), existing


def _opening_lines(rows, accounts) -> list[dict]:
    """بنودُ الحركة الافتتاحية: صفٌّ لكل رصيدٍ غير صفريّ، طرفٌ واحدٌ فيه."""
    lines = []
    for row in rows:
        balance = row["balance"]
        if balance == 0:
            continue
        lines.append({
            "account": accounts[row["code"]],
            "debit": balance if balance > 0 else None,
            "credit": -balance if balance < 0 else None,
        })
    return lines


def import_tree_and_balances(
    book, *, content, entry_date=None, actor=None, day=None,
) -> dict:
    """`POST client-books/<id>/import/` — يقرأ ويتحقّق ثم يكتب في معاملةٍ واحدة."""
    client_books.assert_book_writable(book, day)
    rows = parse_rows(content)
    _assert_unique_codes(rows)
    _assert_parents(book.client, rows)
    _assert_acyclic(rows)
    assert_balanced(rows)
    with transaction.atomic():
        created, updated, accounts = _apply_tree(book.client, rows)
        lines = _opening_lines(rows, accounts)
        entry = None
        if lines:
            entry = client_books.create_entry(
                book,
                entry_date=entry_date or book.opened_on,
                kind=BOOK_ENTRY_KIND_OPENING,
                lines=lines,
                memo="أرصدةٌ افتتاحية — استيرادٌ من Excel",
                actor=actor,
                day=day,
            )
    masked = client_books.amounts_masked(book.tenant, actor)
    return {
        "accounts_created": created,
        "accounts_updated": updated,
        "opening_entry": (
            client_books.entry_row(entry, masked=masked) if entry is not None else None
        ),
    }
