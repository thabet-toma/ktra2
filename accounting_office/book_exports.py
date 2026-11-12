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

from django.db.models import Exists, OuterRef
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from accounting_office import book_reports, services
from accounting_office.models import ClientBookReport, REMINDER_DOCUMENTS
from core.access import user_has_perm

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

#: ورقةُ الكشف في مصنَّف الدفتر لما لا حركةَ لأيّ حساب في الفترة: تقول **لماذا**
#: خرجت بلا صفوف، ولا تُخترَع لها أرقام.
STATEMENT_NO_MOVEMENT_NOTE = (
    "لا حركةَ لحسابٍ واحدٍ في هذه الفترة — لا كشفَ حسابٍ للدفتر."
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
    workbook = Workbook()
    workbook.remove(workbook.active)
    for table in whole_book_tables(book, period, user=user):
        _write_sheet(workbook, table)
    return _as_bytes(workbook)


def whole_book_tables(book, period, *, user) -> list[dict]:
    """جداولُ الدفتر كاملاً — **مصدرٌ واحدٌ** لملفّ Excel وورقة الطباعة (#288/هـ).

    لكل تقريرٍ متاحٍ جدولُه، و**لكل حسابٍ له حركةٌ كشفُه** (`statement`): كان
    المصنَّفُ يخرج بورقةِ ملاحظةٍ مكان الكشف («يحتاج تحديدَ حساب») — فمن صدّر
    دفترَه كاملاً لم يرَ حركةَ حسابٍ واحد. والقائمةُ من `book_reports` لا من حلقةٍ
    هنا، فالمستندان يقرآن جدولاً واحداً (`table_payload`) لا نسختين تفترقان.
    """
    raw_from, raw_to = (day.isoformat() for day in period)
    tables = []
    for report in book_reports.available_reports(book):
        if report["params"]:
            tables.extend(
                _statement_tables(book, report, period, raw_from, raw_to, user=user),
            )
        else:
            tables.append(
                _whole_book_table(book, report, raw_from, raw_to, user=user),
            )
    return tables


def _statement_tables(book, report, period, raw_from, raw_to, *, user) -> list[dict]:
    """كشفُ حسابٍ لكل حسابٍ له حركة — والملاحظةُ لمن لا حركةَ لأيّ حساب.

    **والعنوانُ بالكود لا بالاسم** كي يبقى اسمُ الورقة في Excel فريداً وقصيراً
    (31 محرفاً)، والاسمُ في `note` تحته فلا يُفقد.
    """
    accounts = book_reports.accounts_with_movement(book, period)
    if not accounts:
        return [
            _note_table(book, report, raw_from, raw_to, STATEMENT_NO_MOVEMENT_NOTE),
        ]
    tables = []
    for account in accounts:
        table = book_reports.table_payload(book_reports.report_payload(
            book, report["kind"], raw_from=raw_from, raw_to=raw_to,
            user=user, account=account["code"],
        ))
        table["title"] = f"{report['title']} {account['code']}"
        table["note"] = account["name"]
        tables.append(table)
    return tables


def _whole_book_table(book, report, raw_from, raw_to, *, user) -> dict:
    """ورقةُ تقريرٍ في المصنَّف الكامل — أو ورقتُه بملاحظةٍ تشرح لماذا لم تُبنَ.

    **ولا يُسقِط تقريرٌ مكسورٌ الملفَّ كلّه**: ميزانٌ لا يتوازن يُصدَّر ورقةً تحمل
    رسالتَه ومجموعَي طرفيه، بدل 409 يُفقد المستخدمَ بقيةَ دفاتره. والصفحةُ على
    الورق لا تُغلق الباب: المصدرُ يُصحَّح ثم يُعاد التصدير.
    """
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


# ── بندُ «جاهز للإرسال» (#288/هـ) ────────────────────────────────────────────
#
# **الشاشةُ تقول «انسخه وأرسله للزبون» ولا سجلَّ يُذكّر به**: الرابطُ يُنشأ بضغطةٍ
# ويبقى صفّاً في `ClientBookReport`، ثم لا يذكّر به أحد — فيُنسى بعد أسبوع.
# المولّدُ يقرأ الصفوفَ القائمة ويُخرجها بنوداً بنوع `documents`، فتمرّ في حواجز
# `ready_to_send_payload` نفسِها (الإذنُ ويومُ الراحة والعطلةُ والتأجيلُ والسقف)
# بلا محرّكٍ موازٍ — وهو نمطُ `invoice_reminder_candidates` في `fee_invoices`.

#: سقفُ بند رابط التقرير: **رابطٌ أُرسل مرّةً** لا يُعاد إرسالُه من نفسه.
CLIENT_BOOK_REPORT_REMINDER_MAX = 1
#: إيقاعُه — لا يلزم بعد السقف، وقيمةُ 1 تقول «لا تكرارَ يوميّاً» صراحةً.
CLIENT_BOOK_REPORT_REMINDER_INTERVAL_DAYS = 1


def client_book_report_reminder_candidates(
    tenant, clients, *, day, settings_by_client, contacts, by_pair,
    postponed_pairs, reminder_type=None,
) -> list:
    """بندُ كلّ رابطِ تقريرٍ أُنشئ ولم يُرسل — بنوع `documents` (#288/هـ).

    **نوعُه `documents`** لا `balance`: مستندٌ يُسلَّم لا مطالبةٌ بمبلغ (كإشعارٍ
    دائنٍ للأتعاب) — رسالةٌ تُطالب بمبلغٍ على رابط تقريرٍ تكذب على الزبون.
    و`period_text` و`client_book_report` يحملان **اسمَ التقرير وفترتَه**، ونصُّ
    نوعه لا يُقدَّم عليه في `_reminder_message` لأن نصَّ «الأوراق» يتحدّث عن
    أوراقٍ ناقصةٍ ننتظرها من الزبون وهذه ورقةٌ تُسلَّم له.

    **ولا بندَ لرابطٍ ميّت**: التقريرُ الذي لا مشاركةَ حيّةً له (أُبطلت أو انتهت
    مدّتُها) لا يظهر — بندٌ «أرسِله» بلا رابطٍ يخدع من يقرؤه. والشرطُ
    `_live_report_shares` نفسُه الذي يقرؤه مركِّبُ الروابط، في `Exists` واحد.

    **و«أُرسل؟» بطريقة النظام نفسِه**: `by_pair` يعدّ صفوفَ السجلّ الصادرة للمفتاح
    (زبون، نوع، من، إلى) والسقفُ واحد — فبندٌ أُرسل يختفي من نفسه. والمفتاحُ
    **فترةُ التقرير المخزَّنة** (المحلولةُ في `create_report_link`)، فتقاريرُ
    الدفتر الواحد على فتراتٍ مختلفة بنودٌ مستقلة. **وعدّادُه عدّادُه**: المفتاحُ
    نفسُه مفتاحُ تذكير «الأوراق الناقصة»، فيُعدّ هنا صفوفُ التقرير نفسِه وحدها
    (`subject["client_book_report_id"]`) ويستثنيها مولّدُ الأوراق — إرسالُ أحدهما
    لا يستهلك سقفَ الآخر على فترةٍ مشتركة. وتقريران على الفترة نفسها بنوعين
    مختلفين بندان مستقلان بالرقم لا بالمفتاح.

    **والرابطُ لا يُركَّب هنا** بل في `attach_client_book_report_links` بعد الحواجز
    ولمن يرى المبالغ — انظرها.

    و`reminder_type` طلبٌ لغير `documents` يعطي `[]`: لا بندَ لرابط تقريرٍ في
    تصفية «اللي عليه».
    """
    if reminder_type is not None:
        if services._assert_reminder_type(reminder_type) != REMINDER_DOCUMENTS:
            return []
    client_ids = [client.pk for client in clients]
    if not client_ids:
        return []
    reports = (
        ClientBookReport.objects
        .filter(tenant=tenant, client_book__client_id__in=client_ids)
        .filter(Exists(
            _live_report_shares(tenant).filter(doc_id=OuterRef("pk")),
        ))
        .select_related("client_book__client")
        .order_by("created_at", "id")
    )
    candidates = []
    for report in reports:
        client = report.client_book.client
        resolved = settings_by_client.get(client.pk, {})
        enabled = resolved.get(services.REMINDER_TYPES_ENABLED_KEY) or []
        if REMINDER_DOCUMENTS not in enabled:
            continue
        pairs = by_pair.get(
            (client.pk, REMINDER_DOCUMENTS, report.period_from, report.period_to), (),
        )
        count = sum(
            1 for row in pairs
            if row["kind"] in services.REMINDER_COUNTED_KINDS
            and services.reminder_row_report_id(row) == report.pk
        )
        #: البندُ ظاهرٌ من **يوم إنشاء الرابط**: من أنشأه أنشأه ليُرسَل الآن، لا
        #: يومَ نهاية الفترة التي يغطّيها (وقد تكون في المستقبل).
        created_on = timezone.localdate(report.created_at)
        candidates.append(services.ReminderCandidate(
            client=client,
            reminder_type=REMINDER_DOCUMENTS,
            period_start=report.period_from,
            period_end=report.period_to,
            missing=(),
            missing_codes=(),
            count=count,
            maximum=CLIENT_BOOK_REPORT_REMINDER_MAX,
            interval_days=CLIENT_BOOK_REPORT_REMINDER_INTERVAL_DAYS,
            next_due=created_on,
            contact=contacts.get((client.pk, REMINDER_DOCUMENTS)),
            tax_system=resolved.get(services.TAX_SYSTEM_KEY),
            due=day >= created_on,
            exhausted=count >= CLIENT_BOOK_REPORT_REMINDER_MAX,
            postponed=(client.pk, REMINDER_DOCUMENTS) in postponed_pairs,
            render_due=created_on,
            period_text=client_book_report_period_text(report),
            client_book_report=_report_candidate_item(report),
        ))
    return candidates


def client_book_report_period_text(report) -> str:
    """تسميةُ بند الرابط في الرسالة: **اسمُ التقرير ثم فترتُه** — لا «شهر»."""
    return " — ".join([
        book_reports.REPORT_LABELS.get(report.kind, report.kind),
        f"من {report.period_from.isoformat()} إلى {report.period_to.isoformat()}",
    ])


def client_book_report_item(item) -> dict | None:
    """بندُ الرابط في «جاهز للإرسال» — `None` لبندٍ ليس رابطَ تقرير.

    نسخةٌ من القاموس لا هو: `_reminder_item_payload` يبني بنداً لكل رسالة،
    وربطُ الاثنين بالقاموس نفسه يجعل تعديلَ رسالةٍ يغيّر بندَ أخرى.
    """
    return None if item is None else dict(item)


def _report_candidate_item(report) -> dict:
    """بندُ صفِّ `ClientBookReport` كما يُحمَل على المرشّح قبل الحواجز.

    `url` فارغٌ حتى تُركَّبه `attach_client_book_report_links` بعدها، فيبقى شكلُ
    البند ثابتاً لكل قارئ (والقناعُ يقرّر الرابطَ لا وجودَ البند).
    """
    return {
        "id": report.pk,
        "kind": report.kind,
        "title": book_reports.REPORT_LABELS.get(report.kind, report.kind),
        "period_from": report.period_from.isoformat(),
        "period_to": report.period_to.isoformat(),
        "url": "",
    }


def client_book_report_text(report) -> str:
    """سطرُ الرابط في نصّ الرسالة — بعد نصّ نوعه، بلا رمزٍ جديدٍ في القوالب.

    والسطرُ يُكتب بمبلغٍ محذوف: الرابطُ ورقةٌ تُفتح، وذكرُ رقمٍ في الرسالة كان
    يتجاوز القناعَ الذي يحرس الصفحة.
    """
    if report is None:
        return ""
    parts = [report["title"], f"من {report['period_from']} إلى {report['period_to']}"]
    if report.get("url"):
        parts.append(f"الرابط: {report['url']}")
    return "\n".join(parts)


def _live_report_shares(tenant):
    """مشاركاتُ التقارير **الحيّة** في المكتب — الشرطُ الواحدُ لـ«حيّ».

    `doc_type` التقرير، وغيرُ عامّةٍ (`is_public=False`)، ولم تُبطَل، ولم تنتهِ
    مدّتُها. يقرؤها مولّدُ البند (`Exists` على صفّ التقرير) وقارئُ الروابط
    (`_live_report_urls`) معاً: بندٌ يعدّ رابطاً حيّاً بشرطٍ وقارئٌ يجده بشرطٍ آخر
    كان يُخرج «أرسِله» بلا رابط.
    """
    from docshare.models import DOC_CLIENT_BOOK_REPORT, DocumentShare

    return DocumentShare.objects.filter(
        tenant=tenant,
        doc_type=DOC_CLIENT_BOOK_REPORT,
        is_public=False,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    )


def _live_report_urls(tenant, report_ids) -> dict[int, str]:
    """رابطُ التقرير الحيّ لكل صفٍّ في المجموعة — **قراءةٌ لا إنشاء** (#288/هـ).

    بنداءٍ واحدٍ على `doc_id__in` كـ`appointments.payment_notice_urls`، والأحدثُ
    أوّلاً كما في `active_share`. **ولا تُنشَأ مشاركةٌ هنا**: مسارُ قراءةٍ لا
    يُنشئ روابطَ عامّة — إنشاءُ الرابط فعلٌ صريحٌ محروسٌ بمفتاحَي الكتابة والمبالغ.
    """
    from docshare import services as docshare_services

    wanted = {report_id for report_id in report_ids if report_id is not None}
    if not wanted:
        return {}
    live = (
        _live_report_shares(tenant)
        .filter(doc_id__in=list(wanted))
        .order_by("-created_at", "-id")
        .values_list("doc_id", "token")
    )
    urls: dict[int, str] = {}
    for doc_id, token in live:
        urls.setdefault(doc_id, docshare_services.public_url_for_token(token))
    return urls


def attach_client_book_report_links(tenant, candidates, *, user=None):
    """يُركّب رابطَ التقرير على بنوده — **بعد الحواجز كلّها**.

    **ولمن يرى المبالغَ ويكتب**: الصفحةُ العامة تُبنى بـ`user=None` (ورقةُ الزبون
    بلا قناع)، فمن لا يملك `office.amounts.view` لا يُعطى عنواناً يفتح كلَّ رقمٍ
    حُجِب عنه — وهو الشرطُ نفسُه الذي يحرس إنشاءَ الرابط في الـview. والبندُ يبقى
    بلا رابط: عنوانُ التقرير وفترتُه ليسا مبلغاً، ونصُّ نوعه يمضي.
    """
    from dataclasses import replace

    if user is None or not services.can_see_amounts(tenant, user):
        return candidates
    if not user_has_perm(user, tenant, services.OFFICE_CLIENTS_WRITE_KEY):
        return candidates
    urls = _live_report_urls(tenant, [
        candidate.client_book_report["id"]
        for candidate in candidates
        if candidate.client_book_report is not None
        and not candidate.client_book_report.get("url")
    ])
    if not urls:
        return candidates
    attached = list(candidates)
    for index, candidate in enumerate(attached):
        if candidate.client_book_report is None:
            continue
        url = urls.get(candidate.client_book_report["id"])
        if not url:
            continue
        attached[index] = replace(
            candidate,
            client_book_report={**candidate.client_book_report, "url": url},
        )
    return attached
