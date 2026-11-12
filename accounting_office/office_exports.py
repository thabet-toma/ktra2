"""تصديرُ بيانات المكتب الكامل (#290/أ) — تسعُ أوراقٍ، ورابطُ PDF للنسخة نفسها.

**لا حسابَ هنا.** الأرقامُ تُقرأ كما هي من صفوفها، والمجاميعُ جمعٌ لما قُرئ — ولا
قاعدةَ مالية تُعاد كتابتها (لا `remaining` مشتقّاً هنا ولا مرتبةً من جديد): نسخةٌ
ثانية من أيّ قاعدةٍ تفترق عن الشاشة عند أوّل تعديل، وتظهر في **نسخة احتياطية**
يقول عنها صاحبُها إنها نسخةٌ كاملة. فوظيفةُ هذه الوحدة: قراءةٌ محصورةٌ بالمكتب،
وترتيبٌ في جداولَ ثابتةِ الأعمدة، وكتابةٌ إلى `xlsx` أو إلى ورقة `docshare`.

**والحدودُ حدودُ المكتب**: كلُّ استعلامٍ مبدوءٌ بـ`tenant=tenant`، ولا يُقرأ صفٌّ
بالانتشار عبر علاقةٍ بلا فلتر — يحرسه `test_office_exports` بمكتبين.

**والمبالغُ للمالك وحده**: البوّابةُ في الـview (`assert_owner`) وهي تشترط
`office.amounts.view` مع الدور والمفتاح، فما يُبنى هنا يُبنى لمن يراه. ولا قناعَ
داخل الجداول — قناعُ مالكٍ لمكتبه كذبٌ على نفسه.

**و`openpyxl` مستعملةٌ هنا بنمط `book_exports`**: نفسُ ثوابت التنسيق
(`MONEY_FORMAT`/`COUNT_FORMAT`) ونفسُ اتجاه الورقة (يمين↔يسار) ونفسُ ترويسةٍ
عريضةٍ مجمَّدة — كاتبٌ ثانٍ بتنسيقٍ آخر يجعل ملفَّين من منتجٍ واحد يبدوان
لمنتجَين.
"""
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from accounting_office import book_exports, services
from accounting_office.models import (
    BOOK_ENTRY_KIND_LABELS,
    BOOK_KIND_LABELS,
    DOCUMENT_CADENCE_LABELS,
    DOCUMENT_CHANNEL_LABELS,
    DOCUMENT_STATUS_LABELS,
    FEE_INVOICE_KIND_LABELS,
    FEE_PAYMENT_METHOD_LABELS,
    FREQUENCY_LABELS,
    OBLIGATION_DIRECTION_LABELS,
    OBLIGATION_ORIGIN_LABELS,
    OBLIGATION_STATUS_LABELS,
    REMINDER_KIND_LABELS,
    BookEntryLine,
    ClientService,
    DocumentChecklistItem,
    FeeInvoice,
    FeePayment,
    Obligation,
    OfficeClient,
    OfficeService,
    ReminderLog,
    TaxCard,
)
from accounting_office.settings_registry import REMINDER_TYPE_LABELS

# ── أنواعُ الخليّة في الجداول ────────────────────────────────────────────────
#: الجدولُ يحمل نوعَ كلِّ خليّةٍ معها، فيُنسَّق الرقمُ رقماً في Excel ويُعرض
#: مبلغاً في الورقة — بلا تخمينٍ من النصّ (تاريخٌ يبدو رقماً، ومبلغٌ يبدو نصّاً).
CELL_TEXT = "text"
CELL_DATE = "date"
CELL_MONEY = "money"
CELL_COUNT = "count"

#: مفاتيحُ الأوراق التسع بترتيبها المحسوم — تسميةُ الورقة نفسها من هنا.
SHEET_CLIENTS = "clients"
SHEET_CARDS = "cards"
SHEET_SERVICES = "services"
SHEET_OBLIGATIONS = "obligations"
SHEET_DOCUMENTS = "documents"
SHEET_REMINDERS = "reminders"
SHEET_INVOICES = "invoices"
SHEET_PAYMENTS = "payments"
SHEET_BOOKS = "books"

#: نظامُ فلسطين — القيدُ الوحيد على «بيان أسماء الزبائن» (م111).
PALESTINE_TAX_SYSTEM = "PS"

CLIENT_NAMES_DISABLED_MESSAGE = (
    "بيانُ أسماء الزبائن لمكتبٍ نظامُه فلسطينيٌّ (م111) وحده — "
    "هذا المكتب على نظامٍ آخر، فلا نصَّ يُقدَّم عنه للدائرة."
)

#: رأسُ كل رفض: يسمّي الطلبَ ثم يسمّي الناقص — قراءةُ 403 بلا سبب تُلزم مكالمةً.
OWNER_ONLY_HEADER = "التصديرُ الكامل للمالك — صلاحيةٌ ناقصة"
ROLE_MISSING = "دورُك ليس صاحبَ المكتب ولا مديرَه."
CLIENTS_ALL_MISSING = (
    "مفتاحُ `office.clients.all` («يرى زبائن غيره») غيرُ ممنوحٍ لدورك — "
    "والتصديرُ يحوي كلَّ زبائن المكتب."
)
AMOUNTS_MISSING = (
    "صلاحيةُ «يرى المبالغ» غيرُ ممنوحةٍ لدورك — والنسخةُ تحمل مبالغَ كلّ زبائن "
    "المكتب."
)


def _refusal(reason: str) -> PermissionDenied:
    return PermissionDenied(f"{OWNER_ONLY_HEADER}: {reason}")


# ── البوّابة ────────────────────────────────────────────────────────────────
def missing_owner_permissions(tenant, user) -> list[str]:
    """ما ينقص هذا العضو ليكون «مالكاً» بهذا المعنى — قائمةُ أسباب، لا بوليان.

    **الثلاثةُ معاً**: دورٌ في `ENTRY_APPROVER_ROLES` (المدير أو مدير المكتب)،
    ومفتاحُ `office.clients.all`، ورؤيةُ المبالغ. وكلٌّ منها قد يُنزَع وحده —
    فقائمةٌ تسمّي الناقصَ أنفع من «ممنوع» تُلزم تخميناً.
    """
    from accounting_office.client_books import ENTRY_APPROVER_ROLES
    from core.access import user_has_perm, user_tenant_role

    reasons = []
    if user_tenant_role(user, tenant) not in ENTRY_APPROVER_ROLES:
        reasons.append(ROLE_MISSING)
    if not user_has_perm(user, tenant, services.OFFICE_CLIENTS_ALL_KEY):
        reasons.append(CLIENTS_ALL_MISSING)
    if not services.can_see_amounts(tenant, user):
        reasons.append(AMOUNTS_MISSING)
    return reasons


def assert_owner(tenant, user) -> None:
    """**403 لا 400** لمن نقصه أحدُ الثلاثة — الطلبُ سليمٌ والدورُ ناقص."""
    reasons = missing_owner_permissions(tenant, user)
    if reasons:
        raise _refusal(" ".join(reasons))


# ── بناءُ الجداول ───────────────────────────────────────────────────────────
def _cell(value, kind: str = CELL_TEXT) -> dict:
    """خليّةٌ بنوعها — والقيمةُ فارغةٌ تبقى `None` فيُكتب فراغٌ لا صفر."""
    if value is None or value == "":
        return {"kind": kind, "value": None}
    if kind == CELL_DATE and hasattr(value, "isoformat"):
        return {"kind": kind, "value": value.isoformat()}
    return {"kind": kind, "value": value}


def _text(value) -> dict:
    return _cell("" if value is None else str(value))


def _money(value) -> dict:
    return _cell(None if value is None else Decimal(str(value)), CELL_MONEY)


def _count(value) -> dict:
    return _cell(int(value), CELL_COUNT)


def _flag(value, *, yes="نعم", no="لا") -> dict:
    return _text(yes if value else no)


def _label(mapping, key) -> dict:
    return _text(mapping.get(key, key or ""))


def _table(key, title, columns, rows, *, totals=(), note="") -> dict:
    """ورقةٌ واحدة: عنوانٌ وأعمدةٌ ثابتةٌ وصفوفٌ ومجاميعُ عددية.

    **الأعمدةُ قائمةٌ ثابتة لا `dict` متغيّرَ المفاتيح لكل صف**: صفٌّ ينقصه مفتاح
    كان سينزلق عموداً فيُكتب مبلغُ الضريبة في خانة الرقم — والقالبان (Excel
    والورقة) يقرآن التعريفَ نفسه فيخرج جدولٌ واحد بشكلين.
    """
    return {
        "key": key,
        "title": title,
        "columns": columns,
        "rows": rows,
        "count": len(rows),
        "totals": list(totals),
        "note": note,
    }


def _column(label, kind=CELL_TEXT) -> dict:
    return {"label": label, "kind": kind}


def _money_totals(table) -> list[dict]:
    """مجاميعُ أعمدة المبالغ في ورقة — جمعُ ما قُرئ، لا استعلامَ ثانٍ يفترق عنه."""
    totals = []
    for index, column in enumerate(table["columns"]):
        if column["kind"] != CELL_MONEY:
            continue
        total = sum(
            (
                row[index]["value"] or Decimal("0")
                for row in table["rows"]
                if row[index]["kind"] == CELL_MONEY
            ),
            Decimal("0"),
        )
        totals.append({
            "label": f"مجموع {column['label']}",
            "kind": CELL_MONEY,
            "value": total,
        })
    return totals


# ── الأوراق التسع ───────────────────────────────────────────────────────────
def _clients_table(tenant) -> dict:
    rows = [
        [
            _text(client.name),
            _text(client.tax_file_number),
            _text(client.get_status_display()),
            _text(services.user_display_name(client.responsible)),
            _cell(client.delivered_on, CELL_DATE),
            _cell(client.ended_on, CELL_DATE),
            _cell(client.created_at.date(), CELL_DATE),
            _text(client.notes),
        ]
        for client in OfficeClient.objects.filter(tenant=tenant)
        .select_related("responsible")
        .order_by("name", "id")
    ]
    return _table(
        SHEET_CLIENTS,
        "الزباين",
        [
            _column("الاسم"), _column("رقم الملف الضريبي"), _column("الحالة"),
            _column("المسؤول"), _column("تم التسليم", CELL_DATE),
            _column("تاريخ الإنهاء", CELL_DATE), _column("تاريخ الإنشاء", CELL_DATE),
            _column("ملاحظات"),
        ],
        rows,
    )


def _cards_table(tenant) -> dict:
    rows = [
        [
            _text(card.client.name),
            _text(card.get_entity_type_display()),
            _text(card.get_vat_classification_display()),
            _money(card.annual_sales),
            _flag(card.has_employees),
            _count(card.employees_count or 0),
            _flag(card.is_self_employed),
        ]
        for card in TaxCard.objects.filter(client__tenant=tenant)
        .select_related("client")
        .order_by("client__name", "id")
    ]
    return _table(
        SHEET_CARDS,
        "البطاقات",
        [
            _column("الزبون"), _column("نوع المنشأة"), _column("التصنيف الضريبي"),
            _column("المبيعات السنوية", CELL_MONEY), _column("له موظفون"),
            _column("عدد العاملين", CELL_COUNT), _column("صاحبُ العمل نفسه"),
        ],
        rows,
    )


def _service_frequency(row, *, day) -> str:
    """دوريةُ خدمة الزبون في يوم التصدير — من القاعدة الواحدة `services.frequency_on`."""
    frequency = services.frequency_on(row, day, rows=row.frequencies.all())
    return FREQUENCY_LABELS.get(frequency or "", "")


def _services_table(tenant) -> dict:
    day = timezone.localdate()
    rows = [
        [
            _text("كتالوج"),
            _text(service.name),
            _text(""),
            _text(""),
            _text(""),
            _flag(service.is_active),
            _text(""),
            _text(""),
            _text(""),
        ]
        for service in OfficeService.objects.filter(tenant=tenant).order_by(
            "position", "name", "id",
        )
    ]
    rows.extend(
        [
            _text("خدمة زبون"),
            _text(row.service.name),
            _text(row.client.name),
            _cell(row.starts_on, CELL_DATE),
            _cell(row.ends_on, CELL_DATE),
            _flag(row.ends_on is None),
            _text(_service_frequency(row, day=day)),
            _cell(row.responsible_from, CELL_DATE),
            _flag(row.last_period_ours, yes="علينا", no="ليست علينا"),
        ]
        for row in ClientService.objects.filter(tenant=tenant)
        .select_related("client", "service")
        .prefetch_related("frequencies")
        .order_by("client__name", "id")
    )
    return _table(
        SHEET_SERVICES,
        "الخدمات",
        [
            _column("النوع"), _column("الخدمة"), _column("الزبون"),
            _column("من تاريخ", CELL_DATE), _column("إلى تاريخ", CELL_DATE),
            _column("نشطة"), _column("الدورية"), _column("المسؤول من", CELL_DATE),
            _column("آخر فترة علينا"),
        ],
        rows,
    )


def _obligations_table(tenant) -> dict:
    rows = [
        [
            _text(row.client.name),
            _text(row.rule_code),
            _text(row.name),
            _label(OBLIGATION_ORIGIN_LABELS, row.origin),
            _cell(row.period_start, CELL_DATE),
            _cell(row.period_end, CELL_DATE),
            _cell(row.actual_deadline, CELL_DATE),
            _cell(row.extended_to, CELL_DATE),
            _label(OBLIGATION_STATUS_LABELS, row.status),
            _cell(row.submitted_on, CELL_DATE),
            _money(row.amount),
            _label(OBLIGATION_DIRECTION_LABELS, row.direction),
            _flag(row.client_paid),
        ]
        for row in Obligation.objects.filter(tenant=tenant)
        .select_related("client")
        .order_by("client__name", "-period_end", "id")
    ]
    return _table(
        SHEET_OBLIGATIONS,
        "الالتزامات",
        [
            _column("الزبون"), _column("كود القاعدة"), _column("الالتزام"),
            _column("المصدر"), _column("بداية الفترة", CELL_DATE),
            _column("نهاية الفترة", CELL_DATE), _column("الموعد الرسمي", CELL_DATE),
            _column("مُمدَّد إلى", CELL_DATE), _column("الحالة"),
            _column("تاريخ التقديم", CELL_DATE), _column("المبلغ", CELL_MONEY),
            _column("الاتجاه"), _column("دفعه الزبون"),
        ],
        rows,
    )


def _documents_table(tenant) -> dict:
    rows = [
        [
            _text(row.client.name),
            _text(row.item_code),
            _text(row.name),
            _label(DOCUMENT_CADENCE_LABELS, row.cadence),
            _cell(row.period_start, CELL_DATE),
            _cell(row.period_end, CELL_DATE),
            _label(DOCUMENT_STATUS_LABELS, row.status),
            _cell(row.received_on, CELL_DATE),
            _label(DOCUMENT_CHANNEL_LABELS, row.channel),
        ]
        for row in DocumentChecklistItem.objects.filter(tenant=tenant)
        .select_related("client")
        .order_by("client__name", "-period_start", "id")
    ]
    return _table(
        SHEET_DOCUMENTS,
        "الأوراق",
        [
            _column("الزبون"), _column("الكود"), _column("البند"),
            _column("الدورية"), _column("بداية الفترة", CELL_DATE),
            _column("نهاية الفترة", CELL_DATE), _column("الحالة"),
            _column("تاريخ الاستلام", CELL_DATE), _column("القناة"),
        ],
        rows,
    )


def _reminders_table(tenant) -> dict:
    rows = [
        [
            _text(row.client.name),
            _cell(row.created_at.date(), CELL_DATE),
            _label(REMINDER_TYPE_LABELS, row.reminder_type),
            _label(REMINDER_KIND_LABELS, row.kind),
            _label(DOCUMENT_CHANNEL_LABELS, row.channel),
            _text(row.recipient_name),
            _text(row.recipient_phone),
            _cell(row.period_start, CELL_DATE),
            _cell(row.period_end, CELL_DATE),
            _text(row.body),
        ]
        for row in ReminderLog.objects.filter(tenant=tenant)
        .select_related("client")
        .order_by("-created_at", "-id")
    ]
    return _table(
        SHEET_REMINDERS,
        "سجل التذكيرات",
        [
            _column("الزبون"), _column("التاريخ", CELL_DATE), _column("نوع التذكير"),
            _column("الصفّ"), _column("القناة"), _column("المستلم"),
            _column("الهاتف"), _column("الفترة من", CELL_DATE),
            _column("الفترة إلى", CELL_DATE), _column("النصّ"),
        ],
        rows,
    )


def _invoices_table(tenant) -> dict:
    rows = [
        [
            _text(row.number),
            _text(row.title),
            _label(FEE_INVOICE_KIND_LABELS, row.kind),
            _text(row.client.name),
            _text(row.tax_system),
            _money(row.total),
            _money(row.tax_total),
            _text(row.tax_percent),
            _cell(row.issued_at.date(), CELL_DATE),
            _cell(row.cancelled_at.date() if row.cancelled_at else None, CELL_DATE),
        ]
        for row in FeeInvoice.objects.filter(tenant=tenant)
        .select_related("client")
        .order_by("-issued_at", "-id")
    ]
    return _table(
        SHEET_INVOICES,
        "الفواتير",
        [
            _column("الرقم"), _column("العنوان"), _column("النوع"),
            _column("الزبون"), _column("النظام"), _column("الإجمالي", CELL_MONEY),
            _column("الضريبة", CELL_MONEY), _column("النسبة"), _column("تاريخ الإصدار", CELL_DATE),
            _column("تاريخ الإلغاء", CELL_DATE),
        ],
        rows,
    )


def _payments_table(tenant) -> dict:
    rows = [
        [
            _text(row.receipt_number),
            _cell(row.paid_at, CELL_DATE),
            _text(row.client.name),
            _label(FEE_PAYMENT_METHOD_LABELS, row.method),
            _money(row.amount),
            _text(row.note),
            _text(services.user_display_name(row.created_by)),
        ]
        for row in FeePayment.objects.filter(tenant=tenant)
        .select_related("client", "created_by")
        .order_by("-paid_at", "-id")
    ]
    return _table(
        SHEET_PAYMENTS,
        "الدفعات",
        [
            _column("رقم الإشعار"), _column("التاريخ", CELL_DATE), _column("الزبون"),
            _column("الطريقة"), _column("المبلغ", CELL_MONEY), _column("ملاحظة"),
            _column("سجّلها"),
        ],
        rows,
    )


def _books_table(tenant) -> dict:
    """ورقةُ «الدفاتر» — **الحركةُ وبنودُها في أعمدةٍ متسلسلة** (#290/أ).

    صفٌّ لكل بندٍ لأن البندَ هو ما يُقرأ محاسبياً (حسابٌ ومدينٌ ودائن)؛ وحركةٌ
    بلا بنودٍ لا تُسقَط لكنها تخرج صفّاً بلا حساب — والقائمةُ تُقرأ من الحركة
    لا من البند، فلا يختفي تاريخُ رأسٍ بلا سطور.
    """
    rows = []
    entries = (
        BookEntryLine.objects.filter(tenant=tenant)
        .select_related(
            "entry", "entry__client_book", "entry__client", "account",
        )
        .order_by(
            "entry__client__name", "entry__entry_date", "entry__year",
            "entry__number", "id",
        )
    )
    for line in entries:
        entry = line.entry
        rows.append([
            _text(entry.client.name),
            _label(BOOK_KIND_LABELS, entry.client_book.kind),
            _text(entry.number),
            _cell(entry.entry_date, CELL_DATE),
            _label(BOOK_ENTRY_KIND_LABELS, entry.kind),
            _text(f"{line.account.code} — {line.account.name}"),
            _money(line.debit),
            _money(line.credit),
            _money(line.tax_amount),
            _text(line.side_party),
            _text(entry.memo),
        ])
    return _table(
        SHEET_BOOKS,
        "الدفاتر",
        [
            _column("الزبون"), _column("الدفتر"), _column("رقم الحركة"),
            _column("التاريخ", CELL_DATE), _column("النوع"), _column("الحساب"),
            _column("مدين", CELL_MONEY), _column("دائن", CELL_MONEY),
            _column("الضريبة", CELL_MONEY), _column("الطرف"), _column("ملاحظة"),
        ],
        rows,
    )


#: بواني الأوراق التسع بترتيبها — مصدرٌ واحد لملف Excel ولورقة الرابط.
_TABLE_BUILDERS = (
    _clients_table,
    _cards_table,
    _services_table,
    _obligations_table,
    _documents_table,
    _reminders_table,
    _invoices_table,
    _payments_table,
    _books_table,
)


def full_export_tables(tenant, user=None) -> list[dict]:
    """الجداولُ التسعةُ كاملةً — من صفوف المكتب وحدها، والمجاميعُ جمعُ ما قُرئ.

    `user` غيرُ مستعملٍ في الحساب: البوّابةُ (`assert_owner`) في الـview، وهذه
    الدالّةُ تُنادى من صفحة الرابط العامّ أيضاً حيث لا مستخدم. ويبقى في التوقيع
    لأن النداءَ من نقطةٍ مستقبليةٍ بمستخدمٍ لا يغيّر العنوان.
    """
    tables = [builder(tenant) for builder in _TABLE_BUILDERS]
    for table in tables:
        table["totals"] = _money_totals(table)
    return tables


# ── الملفّ ──────────────────────────────────────────────────────────────────
def _sheet_title(title: str) -> str:
    """عنوانُ ورقةٍ يقبله Excel: 31 محرفاً وبلا `[]:*?/\\` — كقاعدة `book_exports`."""
    forbidden = set('[]:*?/\\')
    cleaned = "".join(char for char in title if char not in forbidden).strip()
    return (cleaned or "ورقة")[:book_exports.SHEET_TITLE_MAX]


def _write_sheet(workbook, table) -> None:
    """ورقةٌ واحدةٌ: ترويسةٌ عربيةٌ ثم الصفوف ثم مجاميعُ المبالغ.

    التنسيقُ من `book_exports` نفسه (`MONEY_FORMAT`/`COUNT_FORMAT`): ملفّان من
    منتجٍ واحد بخانتين مختلفتين لرقمٍ واحد يُقرآن كأنّ أحدهما مكسور.
    """
    sheet = workbook.create_sheet(title=_sheet_title(table["title"]))
    sheet.sheet_view.rightToLeft = True

    sheet.append([column["label"] for column in table["columns"]])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    if table["columns"]:
        sheet.freeze_panes = "A2"

    for row in table["rows"]:
        sheet.append([
            None if cell["value"] is None else cell["value"] for cell in row
        ])
        for index, column in enumerate(table["columns"], start=1):
            target = sheet.cell(row=sheet.max_row, column=index)
            if column["kind"] == CELL_MONEY:
                target.number_format = book_exports.MONEY_FORMAT
            elif column["kind"] == CELL_COUNT:
                target.number_format = book_exports.COUNT_FORMAT
    if not table["rows"] and table["columns"]:
        sheet.append(["لا بيانات."])

    if table["totals"]:
        sheet.append([])
        for total in table["totals"]:
            sheet.append([total["label"], total["value"]])
            sheet.cell(
                row=sheet.max_row, column=2,
            ).number_format = book_exports.MONEY_FORMAT

    sheet.column_dimensions["A"].width = 20
    for index in range(2, max(len(table["columns"]), 1) + 1):
        sheet.column_dimensions[get_column_letter(index)].width = 22


def full_export_bytes(tenant, user=None) -> bytes:
    """مصنَّفُ النسخة الكاملة — تسعُ أوراقٍ بترتيبها المحسوم."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for table in full_export_tables(tenant, user):
        _write_sheet(workbook, table)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _as_bytes(workbook) -> bytes:  # pragma: no cover - بقيّةُ كتابةٍ عامّة
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ── الروابط ────────────────────────────────────────────────────────────────
def _link(tenant, doc_type, *, user=None, request=None) -> dict:
    """صفُّ مشاركةٍ للنسخة — بلا جدولٍ جديد: `doc_id` هو معرّفُ المكتب نفسه.

    **ومعرّفُ المكتب هو المستند**: موضوعُ الوثيقتين المكتبُ لا صفٌّ من صفوفه،
    و`(tenant, doc_type, doc_id)` قيدُ `DocumentShare` نفسِه يمنع خلطَ مكتبين —
    فمحمولُ التحميل يُتحقَّق من `doc_id == tenant_id` في المُحمِّل (لا صفَّ
    موديلٍ ثانٍ يُنشأ ويُهجَّر لهذه الحاجة حسب قرار التذكرة).
    """
    from docshare import services as docshare_services

    share = docshare_services.create_share(
        tenant, doc_type, tenant.pk, user=user, request=request,
    )
    return {
        "url": docshare_services.public_url(share),
        "expires_at": share.expires_at.isoformat(),
    }


def create_full_export_link(tenant, *, user=None, request=None) -> dict:
    """رابطُ PDF للنسخة الكاملة — بإعداد `office_report_pdf_link` نفسه.

    الإعدادُ يُفحص **قبل أيّ كتابة**: مكتبٌ أطفأ روابط التقارير لا يُنشأ له صفُّ
    مشاركة، ويبقى تصديرُ Excel عاملاً — وهو نصفُ القرار المطلوب.
    """
    if not services.resolve_setting(tenant, book_exports.REPORT_LINK_KEY):
        raise book_exports.ReportLinkDisabled(
            book_exports.REPORT_LINK_DISABLED_MESSAGE,
        )
    from docshare.models import DOC_OFFICE_DATA_EXPORT

    return _link(tenant, DOC_OFFICE_DATA_EXPORT, user=user, request=request)


def office_tax_system(tenant):
    return services.resolve_setting(tenant, services.TAX_SYSTEM_KEY)


def assert_client_names_available(tenant) -> None:
    """«بيانُ الأسماء» لمكتبٍ فلسطينيّ وحده — وإلا **400** برسالته.

    القاعدةُ ليست صلاحيةً بل نصّاً: م111 تعليماتُ الدائرة الفلسطينية، ولا نظيرَ
    لها في نظامٍ إسرائيليّ — فورقةٌ تُصيَّر هناك تُقدَّم لجهةٍ لا تطلبها.
    """
    if office_tax_system(tenant) != PALESTINE_TAX_SYSTEM:
        raise ValidationError({"tax_system": CLIENT_NAMES_DISABLED_MESSAGE})


def client_names_rows(tenant) -> list[dict]:
    """زبائنُ المكتب النشطون بأسمائهم وعناوينهم وأرقام ملفاتهم.

    **العنوانُ من طرف الزبون** (`OfficeClient.partner`) لأنه الموضعُ الوحيد الذي
    يحمل عنواناً في هذا المستودع — سجلُّ المكتب نفسُه بلا حقلِ عنوان. ومن لم
    يُربط طرفُه يخرج سطرُه بلا عنوان (فراغاً) لا بعنوانٍ مخترَع.

    **والنشطون وحدهم**: البيانُ يقول «زبائنُ المكتب» اليوم، ومن انتهى عنده خرج
    من قائمته — ويبقى في التصدير الكامل بتاريخ إنهائه.
    """
    rows = []
    for client in (
        OfficeClient.objects.filter(tenant=tenant, status=OfficeClient.STATUS_ACTIVE)
        .select_related("partner")
        .order_by("name", "id")
    ):
        partner = client.partner
        address = ", ".join(
            part for part in (
                (partner.street_address if partner else "") or "",
                (partner.city if partner else "") or "",
            ) if part
        )
        rows.append({
            "name": client.name,
            "tax_file_number": client.tax_file_number,
            "address": address,
        })
    return rows


def create_client_names_link(tenant, *, user=None, request=None) -> dict:
    """رابطُ «بيان أسماء الزبائن» (م111) — نفسُ إعداد الرابط وحارسِ المالك."""
    assert_client_names_available(tenant)
    if not services.resolve_setting(tenant, book_exports.REPORT_LINK_KEY):
        raise book_exports.ReportLinkDisabled(
            book_exports.REPORT_LINK_DISABLED_MESSAGE,
        )
    from docshare.models import DOC_OFFICE_CLIENT_NAMES

    return _link(tenant, DOC_OFFICE_CLIENT_NAMES, user=user, request=request)


# ── نطاقُ النوعين في سطح مشاركة المستندات ───────────────────────────────────
# `doc_id` هنا معرّفُ المكتب، فالنطاقُ يُرجع معرّفَ مكتب العضو المالك وحده —
# ورابطُ زميلٍ غيرِ مالكٍ **404** لا 403 (نمط `payment_notice_doc_ids`). وهذا
# الحارسُ يكملُ حارسَ المفتاح: مفتاحُ `office.clients.all` وحده لا يجعل كلَّ عضوٍ
# مالكاً، والدورُ يُقرأ هنا كما يُقرأ في الـview.
def owned_doc_ids(tenant, user):
    """مكتبُ العضو إن كان مالكاً بهذا المعنى — وإلا مجموعةٌ فارغة (404)."""
    from tenants.models import Tenant

    if missing_owner_permissions(tenant, user):
        return Tenant.objects.none().values("pk")
    return Tenant.objects.filter(pk=tenant.pk).values("pk")
