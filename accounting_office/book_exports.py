"""مستخرجاتُ دفتر الزبون (#288/ب-١): ملفُّ Excel ورابطُ مشاركة — **بلا حسابٍ هنا**.

**كلُّ رقمٍ من `report_payload`.** هذه الوحدةُ لا تجمع ولا ترشّح ولا تقنّع: تأخذ
حمولةً محسوبةً وتُخرجها ملفّاً، أو تُنشئ صفَّ رابطٍ لتقريرٍ محسوب. ونسخةٌ ثانية من
أيّ قاعدةٍ هنا كانت ستفترق عن `book_reports` عند أوّل تعديل، والانحرافُ يظهر
مستخرجاً يخالف الشاشة — وهو أسوأُ من غياب المستخرج.
والأعمدةُ نفسُها تأتي من `book_reports.REPORT_COLUMNS` عبر `table_payload`، فتقرأ
ورقةُ الطباعة وملفُّ Excel جدولاً واحداً.

**و`openpyxl` اعتماديةٌ جديدة** (سطرُها في `requirements.txt`): التذكرةُ تطلب ملفَّ
Excel حقيقيّ، وCSV — وهو ما اختير في `hr/attendance_api.py` حين كفى — لا يحمل
أعشاراً ولا رقماً رقماً ولا ورقةً لكل تقرير. والاستيرادُ هنا وحده، فلا تجرّها
صفحاتُ `docshare` الخادمية.

**والملفُّ يعلن نفسَه «نسخة عمل»** على كل ورقة، كما يُعلنها كلُّ ردٍّ من الـAPI:
مستخرجٌ بلا علامةٍ يُقدَّم لجهةٍ خارجية على أنه نهائي، والعلامةُ آخرُ ما يُتذكَّر.

**واسمُ التنزيل ASCII**: `Content-Disposition` بترميز آخر مشكلةٌ في متصفحاتٍ
قديمة، والاسمُ الداخليُّ لا يراه المستخدم إلا في شريط التنزيل — فالاسمُ من
المعرّفات لا من النصوص العربية.
"""
import datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from accounting_office import book_reports, services
from accounting_office.models import ClientBookReport

#: سقفُ عنوان الورقة في Excel، والأحرفُ التي يرفضها (`[]:*?/\`).
SHEET_TITLE_MAX = 31
_SHEET_FORBIDDEN = set('[]:*?/\\')
#: تنسيقُ خليّة المبلغ: خانتان عشريتان وفاصلُ آلاف — الشكلُ الذي تعرضه الشاشة.
MONEY_FORMAT = "#,##0.00"
COUNT_FORMAT = "0"
#: عرضُ عمود الاسم (أ) وعرضُ بقية الأعمدة — قراءةُ جدولٍ طويلٍ لا تريدُ تمريراً.
_LABEL_COLUMN_WIDTH = 20
_COLUMN_WIDTH = 22

#: مفتاحُ إعداد «رابط PDF للتقارير» — إطفاؤه يمنع الرابطَ ولا يمنع التصدير.
REPORT_LINK_KEY = "office_report_pdf_link"

REPORT_LINK_DISABLED_MESSAGE = (
    "روابطُ التقارير مُطفأة في إعدادات المكتب — فعّل «رابط PDF للتقارير» "
    "لإنشاء رابطِ مشاركة. والتصديرُ المباشر (Excel والطباعة) يعمل."
)


class ReportLinkDisabled(Exception):
    """رابطُ التقارير مُطفأٌ في إعدادات المكتب — **400** لا 403.

    الإعدادُ ليس صلاحية: مَن يملك كتابةَ الدفتر يملك إنشاءَ رابطه، لكن المكتبَ
    قرّر أن يوزّع مستخرجاته ورقةً لا رابطاً — فالمنعُ حالةُ إعدادٍ تُشرح، لا منعُ
    دورٍ يُسكَت عنه. والرسالةُ تسمّي الإعدادَ ليُفتَح من شاشته.
    """


# ── الملفّ ─────────────────────────────────────────────────────────────────
def excel_bytes(payload) -> bytes:
    """ملفُّ Excel لتقريرٍ واحدٍ من حمولته — ورقةٌ واحدةٌ بلا منطقٍ هنا."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    _write_sheet(workbook, book_reports.table_payload(payload))
    return _as_bytes(workbook)


def whole_book_bytes(book, period, *, user) -> bytes:
    """مصنَّفُ الدفتر كاملاً: ورقةٌ لكل تقريرٍ متاحٍ لنوعه، على فترةٍ واحدة.

    `period` زوجُ `(تاريخ البداية، تاريخ النهاية)` — **محلولاً** في `book_reports`
    (`period_for` ثم `_report_span`) كما في المسار المفرد، فلا تُنسخ قاعدةُ
    الفترة هنا. و`user` إلزاميٌّ صريحاً كـ`report_payload`: القناعُ قرارٌ يُتَّخذ
    لا يُنسى.
    """
    raw_from, raw_to = (day.isoformat() for day in period)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for report in book_reports.available_reports(book):
        _write_sheet(
            workbook,
            _whole_book_table(book, report, raw_from, raw_to, user=user),
        )
    return _as_bytes(workbook)


def _whole_book_table(book, report, raw_from, raw_to, *, user) -> dict:
    """ورقةُ تقريرٍ في المصنَّف الكامل — أو ورقتُه بملاحظةٍ تشرح لماذا لم تُبنَ.

    **ولا يُسقِط تقريرٌ مكسورٌ الملفَّ كلّه**: ميزانٌ لا يتوازن يُصدَّر ورقةً تحمل
    رسالتَه ومجموعَي طرفيه، بدل 409 يُفقد المستخدمَ بقيةَ دفاتره. والصفحةُ على
    الورق لا تُغلق الباب: المصدرُ يُصحَّح ثم يُعاد التصدير.

    و`statement` **يحتاج حساباً أو طرفاً** (`REPORT_PARAMS`) فلا معنى لورقةٍ له
    في مصنَّفٍ بلا مُدخَل: تُكتَب ملاحظتُه ولا تُخترَع له أرقام.
    """
    if report["params"]:
        return _note_table(
            book, report, raw_from, raw_to,
            "كشفُ الحساب يحتاج تحديدَ حسابٍ أو طرف — يُصدَّر من شاشة التقارير.",
        )
    try:
        payload = book_reports.report_payload(
            book, report["kind"], raw_from=raw_from, raw_to=raw_to, user=user,
        )
    except book_reports.ReportImbalance as exc:
        return _note_table(
            book, report, raw_from, raw_to, str(exc), totals=exc.totals,
        )
    return book_reports.table_payload(payload)


def _note_table(book, report, raw_from, raw_to, note, totals=None) -> dict:
    """ورقةٌ بلا صفوف: تقول **لماذا**، ومجاميعُ الميزان المكسور تُنشَر معها.

    تُبنى بـ`table_payload` نفسِه كي تخرج المجاميعُ بالتنسيق والتسمية ذاتيهما.
    """
    table = book_reports.table_payload({
        "kind": report["kind"],
        "title": report["title"],
        "client": book.client.name,
        "from": raw_from,
        "to": raw_to,
        "watermark": book_reports.WATERMARK,
        "rows": [],
        "totals": totals or {},
    })
    table["note"] = note
    return table


def _write_sheet(workbook, table) -> None:
    """ورقةٌ واحدة: ترويسةٌ ثم جدولٌ ثم مجاميع — بالترتيب الذي تُقرأ به."""
    sheet = workbook.create_sheet(title=_sheet_title(table["title"]))
    # الورقةُ عربية: الاتجاهُ يمين↔يسار على الورقة نفسها في Excel.
    sheet.sheet_view.rightToLeft = True

    # الترويسةُ: اسمُ الزبون، الفترة، اسمُ التقرير، ثم **العلامةُ المائية** —
    # بترتيبها في التذكرة، فيرى من يفتح الملفَّ أوّلاً لمن هو وعلى أيّ فترة.
    sheet.append(["الزبون", table["client"]])
    sheet.append(["الفترة", table["from"], table["to"]])
    sheet.append(["التقرير", table["title"]])
    watermark = sheet.cell(row=sheet.max_row + 1, column=1, value=table["watermark"])
    watermark.font = Font(bold=True, color="B91C1C")
    if table["period_note"]:
        sheet.append([table["period_note"]])
    if table.get("note"):
        sheet.append([table["note"]])
    sheet.append([])

    columns = table["columns"]
    sheet.append([column["label"] for column in columns])
    header_row = sheet.max_row
    for cell in sheet[header_row]:
        cell.font = Font(bold=True)
    if columns:
        sheet.freeze_panes = f"A{header_row + 1}"

    for row in table["rows"]:
        sheet.append([_excel_value(cell) for cell in row])
        _format_cells(sheet, sheet.max_row, columns)
    if not table["rows"] and columns:
        sheet.append(["لا بيانات في هذه الفترة."])
    if table["totals"]:
        sheet.append([])
        for total in table["totals"]:
            sheet.append([total["label"], _total_value(total)])
            if total["kind"] == book_reports.CELL_MONEY and not total["masked"]:
                sheet.cell(row=sheet.max_row, column=2).number_format = MONEY_FORMAT

    _set_widths(sheet, columns)


def _excel_value(cell):
    """قيمةُ الخليّة في Excel: مبلغٌ `Decimal` وعدٌّ `int` — **لا نصوصٌ تشبه الأرقام**."""
    if cell["masked"] or cell["value"] in (None, ""):
        return None
    if cell["kind"] == book_reports.CELL_MONEY:
        return Decimal(str(cell["value"]))
    if cell["kind"] == book_reports.CELL_COUNT:
        return int(cell["value"])
    return cell["value"]


def _total_value(total):
    """مجموعٌ في الصفّ السفلي — والفارغُ خليّةٌ فارغة، لا صفرٌ يوهم بقيمة."""
    if total["masked"]:
        return None
    return _excel_value(total)


def _format_cells(sheet, row_index, columns) -> None:
    """تنسيقُ الأرقام على صفٍّ واحد: خانتان للمبلغ، ولا كسرَ للعدّ."""
    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(row=row_index, column=index)
        if column["kind"] == book_reports.CELL_MONEY:
            cell.number_format = MONEY_FORMAT
        elif column["kind"] == book_reports.CELL_COUNT:
            cell.number_format = COUNT_FORMAT


def _set_widths(sheet, columns) -> None:
    sheet.column_dimensions["A"].width = _LABEL_COLUMN_WIDTH
    for index in range(2, max(len(columns), 1) + 2):
        sheet.column_dimensions[get_column_letter(index)].width = _COLUMN_WIDTH


def _sheet_title(title: str) -> str:
    """عنوانُ ورقةٍ يقبله Excel: 31 محرفاً وبلا `[]:*?/\\` — وبلا فراغٍ خالص."""
    cleaned = "".join(char for char in title if char not in _SHEET_FORBIDDEN).strip()
    return (cleaned or "تقرير")[:SHEET_TITLE_MAX]


def _as_bytes(workbook) -> bytes:
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ── الرابط ─────────────────────────────────────────────────────────────────
def create_report_link(book, kind, *, user, raw_from=None, raw_to=None, request=None):
    """يُنشئ — أو يُعيد — رابطَ تقريرٍ محسوب على فترته **المحلولة**.

    **الإعدادُ يُفحص قبل أيّ كتابة**: مكتبٌ أطفأ «رابط PDF للتقارير» لا يُنشأ له
    صفُّ `ClientBookReport` ولا صفُّ مشاركة. والتصديرُ المباشر (Excel والطباعة)
    لا يمرّ من هنا فلا يتأثّر — وهو نصفُ القرار المطلوب.

    **والصفُّ يُعاد استعمالاً على الفترة نفسها**: ضغطتان على «مشاركة» لا تُنشئان
    صفَّين ولا رابطين — وهذا معنى `dedupe` في `create_share` نفسِه. والفترةُ
    المخزَّنةُ **محلولةٌ** (`payload["from"]`/`["to"]`) كما يقرؤها الرابطُ لاحقاً.

    و`ReportImbalance` تصعد كما هي: تقريرٌ لا يتوازن لا يُنشَأ له رابطٌ أصلاً
    (والـview يحوّلها **409** — الطلبُ سليمٌ والبياناتُ مكسورة).
    """
    if not services.resolve_setting(book.tenant, REPORT_LINK_KEY):
        raise ReportLinkDisabled(REPORT_LINK_DISABLED_MESSAGE)
    payload = book_reports.report_payload(
        book, kind, raw_from=raw_from, raw_to=raw_to, user=user,
    )
    report, _created = ClientBookReport.objects.get_or_create(
        tenant=book.tenant,
        client_book=book,
        kind=kind,
        period_from=datetime.date.fromisoformat(payload["from"]),
        period_to=datetime.date.fromisoformat(payload["to"]),
        defaults={"created_by": user if (user and user.is_authenticated) else None},
    )

    # استيرادٌ كسول كـ`appointments.payment_notice_urls`: `docshare.services` يجرّ
    # سجلَّ الأنواع، ووحدةُ النوع هناك تستورد نماذجَ المكتب — فالنداءُ وقتَ الحاجة
    # فقط، لا استيراداً في الأعلى يدير دورةً عند أوّل تحميل.
    from docshare import services as docshare_services
    from docshare.models import DOC_CLIENT_BOOK_REPORT

    share = docshare_services.create_share(
        book.tenant, DOC_CLIENT_BOOK_REPORT, report.pk, user=user, request=request,
    )
    return {
        "url": docshare_services.public_url(share),
        "expires_at": share.expires_at.isoformat(),
    }
