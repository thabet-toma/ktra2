"""إشعارُ الدفع — ورقةٌ يجمع فيها المكتبُ ما على الزبون في تاريخ استحقاقٍ واحد.

**جمهورُه الزبون**، وحدودُ الملفّ حدودُ تلك الحقيقة: لا يخرج من هنا إلا ما يُقال
للزبون. والتجميعُ **من `accounting_office.appointments` وحده** (`payment_notice`)،
لا نسخةً ثانيةً هنا — الرسالةُ التي تُرسَل والورقةُ التي تُفتح تقرآن تجميعاً واحداً،
فلا يفترق نصُّ واتساب عن الورقة عند أوّل تعديل.

**و`doc_id` التزامٌ لا زبون** (أدنى معرّفٍ في مجموعة التاريخ نفسه): `create_share`
و`resolve_share` يُمرّران `(tenant_id, doc_id)` وحدهما، فما لا يُشتقّ من هذين لا
يُشتقّ أصلاً. ومن الالتزام يُقرأ (الزبون، تاريخُ استحقاقه) فيُبنى الإشعارُ منهما —
**بلا حقلٍ إضافيّ في `DocumentShare` ولا هجرةِ نماذج** (د5: «وإن أمكن الاشتقاق
فلا تُضِف»). والثمنُ المعلومُ أنّ حذفَ الالتزام المرجع يُلغي الرابط (404)، وهو
سلوكُ كلّ نوعٍ في هذا السجلّ.

**والألوانُ لا تحتملها حمولةُ العقد العامة:** اختبارُ القائمة البيضاء يحصر مفاتيح
السطر في عشرة بلا حقلِ نبرة، فنبرةُ السطر تُصيَّر في ورقة هذا النوع وحدها
(`page`) من المصدر نفسه. والبديلُ كان توسيعَ عقدٍ يخدم ثمانيةَ عشرَ نوعاً لقاعدةٍ
تخصّ نوعاً واحداً — ثمنٌ بلا مقابل.

**قيدان معلَنان لا يُخفيان** (#285، قرارُ منسّق):

- **ثمنُ التمديد** (#277): الورقةُ تُبنى من `due_date` أيّ `extended_to or
  actual_deadline`، فالرابطُ الذي أُنشئ ليوم 15/3 يعرض إشعار 15/4 بعد أن يمدّد
  المكتبُ الالتزام — رابطٌ واحدٌ لمستندٍ تغيّر تاريخُه. والتاريخُ ظاهرٌ على الورقة
  فلا خداع، والبديلُ (تجميدُ الحمولة في وقت الإنشاء) كان يُثبّت أرقاماً تموت
  حين يُصحَّح الالتزام.
- **الإشعارُ عربيٌّ دائماً** ولو كانت لغةُ الجهة عبريّة: نصوصُه في
  `appointments` (`PAYMENT_NOTICE_TITLE` والتسميتان) بلا جدولِ لغات، ورسالةُ
  التذكير نفسها تُترجَم. ترجمةُ الإشعار تذكرةٌ لاحقة.

**وثاني النوعين هنا `client_book_report`** (#288/ب-١): تقريرُ دفترِ زبونٍ على
فترةٍ مخزَّنة — ورقتُه جدولُ التقرير نفسِه، و`doc_id` فيه صفُّ `ClientBookReport`
لا مستنداً مالياً (التقريرُ يُحسَب عند الفتح كما يُحسَب الإشعارُ من التزامه).
والأعمدةُ والمجاميعُ تُقرأ من `accounting_office.book_reports` — المصدرِ الذي
يقرأ منه ملفُّ Excel — فلا يفترق مستندان لنفس التقرير.
"""
from django.template.loader import render_to_string

from accounting_office.models import Obligation
from core.terminology import term
from core.terminology import OFFICE_FEE_INVOICE_LABEL
from docshare.documents._contract import (
    AUDIENCE_CUSTOMER,
    AUDIENCE_OFFICE,
    TONE_DANGER,
    TONE_MUTED,
    TONE_OK,
    TONE_WARN,
    VALUE_DATE,
    VALUE_MONEY,
    company_card,
    meta,
    payload,
    total,
)


def _appointments():
    """استيرادٌ كسول: `appointments` يجرّ خدماتِ المكتب ونماذجه، والصفحةُ العامة
    لا تحتاجها في إقلاع التطبيقات — ونفسُ النمط في `inventory_docs._services`."""
    from accounting_office import appointments

    return appointments


def _notice_status(notice) -> tuple[str, str]:
    """تسميةُ شارة الحالة ونبرتُها — **مفاتيحُ النبرة من مصدرها الواحد**.

    مفتاحُ النبرة (`owed`/`refund`/`neutral`) يُقرأ من `appointments` لا يُكتب
    حرفياً هنا: نسخةٌ ثانية تفترق عند أوّل إعادة تسمية، والانحرافُ يظهر
    `KeyError` وقت أوّل زائر لا وقت المراجعة.
    """
    tones = _appointments()
    badge_tone = {
        tones.PAYMENT_NOTICE_TONE_OWED: TONE_DANGER,
        tones.PAYMENT_NOTICE_TONE_REFUND: TONE_OK,
        tones.PAYMENT_NOTICE_TONE_NEUTRAL: TONE_MUTED,
    }[notice["tone"]]
    return notice["direction_label"], badge_tone


def _notice_of(obligation) -> dict:
    """الإشعارُ من مصدره الواحد — لا تجميعَ ثانياً في `docshare`."""
    return _appointments().payment_notice(
        obligation.tenant,
        client_id=obligation.client_id,
        due=obligation.due_date,
    )


def load_payment_notice(tenant_id: int, doc_id: int):
    """الالتزامُ الذي يفتح الإشعار — **بلا فلترة حالة**.

    فلترةُ `pending` هنا كانت تُحوّل رابطاً حيّاً إلى 404 يوم يُقدَّم الالتزام
    (نفسُ حجّة `load_stocktake_count`): الرابطُ كان حيّاً يوماً، والصفحةُ يجب أن
    تقول «لا مبلغ» لا أن تصمت. والحالةُ تحكم **الأسطر** لا وجودَ الورقة.
    """
    return (
        Obligation.objects
        .select_related("client", "tenant")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .only(
            "id", "tenant_id", "client_id", "actual_deadline", "extended_to",
            # `OfficeClient` سجلُّ المكتب لا طرفُ `Partner`: له اسمٌ ورقمُ ملفٍّ
            # ضريبيّ وحدهما — ولا عنوانَ ولا هاتفَ يُعرَض على ورقة الزبون.
            "client__name", "client__tax_file_number",
        )
        .first()
    )


def build_payment_notice(obligation) -> dict:
    """حمولةُ العقد العامّ للورقة — المجموعُ واتجاهُه، بلا أسطرٍ ملوّنة.

    `show_lines=False` عن قصد: جدولُ `share.html` العامّ أعمدةُ كميةٍ وسعرٍ
    وضريبةٍ لا معنى لها على إشعار دفع، وملؤها أصفاراً كذبٌ على الزبون. والأسطرُ
    الملوّنة تُصيَّرها `page_payment_notice`.
    """
    notice = _notice_of(obligation)
    status_label, status_tone = _notice_status(notice)
    return payload(
        kind="payment_notice",
        title=_appointments().PAYMENT_NOTICE_TITLE,
        number="",
        date=notice["date"],
        status_label=status_label,
        status_tone=status_tone,
        party_title="الزبون",
        # اسماً وحده: بطاقةُ الطرف تنتظر حقول `Partner` (عنوانٌ وهاتفٌ ورقمٌ
        # ضريبيّ)، وسجلُّ مكتب المحاسبة لا يحملها. والرقمُ الضريبيّ متاحٌ فيُذكر
        # صفَّ بيانات، وما ليس في السجلّ لا يُخترَع له موضعٌ فارغ.
        party=obligation.client.name,
        currency=None,
        meta_rows=[
            meta("تاريخ الاستحقاق", notice["date"], VALUE_DATE),
            meta("رقم الملف الضريبي", obligation.client.tax_file_number),
        ],
        lines=[],
        show_lines=False,
        show_line_prices=False,
        totals_rows=[total("المجموع", notice["total"], strong=True)],
        grand_total=notice["total"],
    )


def page_payment_notice(obligation, share) -> str:
    """ورقةُ الإشعار المصيَّرة — العنوانُ الثابت، والأسطرُ بألوانها، والمجموع.

    المبلغُ يُعرَض بقيمته المطلقة ومعه كلمتُه («800 إلك») لا بسالبٍ يُقرأ خطأً،
    واللونُ يأتي محسوباً من `payment_notice_tone` — لا قاعدةَ لونٍ ثانية في
    القالب: هو يضع اسمَ الصنف (`pn-owed`/`pn-refund`/`pn-neutral`) ويرسمه.
    """
    notice = _notice_of(obligation)
    return render_to_string(
        "docshare/payment_notice.html",
        {
            "title": _appointments().PAYMENT_NOTICE_TITLE,
            "company": company_card(share.tenant),
            "client_name": obligation.client.name,
            "date": notice["date"],
            "rows": [
                {
                    "label": line["label"],
                    "amount": abs(line["amount"]),
                    "tone": line["tone"],
                    "direction_label": line["direction_label"],
                }
                for line in notice["lines"]
            ],
            "total": abs(notice["total"]),
            "total_tone": notice["tone"],
            "total_direction": notice["direction_label"],
            # #287/٦: نتيجةُ فترة الدفتر لمن عنده دفتر — اللونُ يصل رمزاً
            # (`profit`/`loss`/`neutral`) والقالبُ يضع اسمَ الصنف `pn-<الرمز>`.
            "result": notice.get("result"),
        },
    )


def payment_notice_doc_ids(tenant, user):
    """الالتزاماتُ التي يراها هذا العضو — **نطاقُ النوع في سطح الإدارة** (#285/م٣).

    `doc_id` هنا التزامُ زبون، وحارسُ الرؤية في مكتب المحاسبة واحدٌ
    (`visible_clients`). وصلاحيةُ النوع (`office.clients.write`) تمنح **كتابةَ**
    زبائن المكتب لا رؤيةَ زبائن الزملاء: محاسبٌ فيها بلا `office.clients.all` كان
    يأخذ من `GET ?doc_type=payment_notice` توكنَ كلّ إشعارٍ في الشركة ورابطَه
    العامّ، ويُبطل أيَّها شاء، بمعرّفاتٍ متسلسلةٍ تُخمَّن. فالقائمةُ والقراءةُ
    والإبطالُ تمرّ من هذا النطاق (`docshare/views.py`).

    **والاستيرادُ كسول**: `accounting_office.services` يجرّ خدماتَ المكتب، وهذا
    السجلّ يُستورد في إقلاع التطبيقات.
    """
    from accounting_office import services as office_services

    return Obligation.objects.filter(
        tenant=tenant,
        client_id__in=office_services.visible_clients(tenant, user).values("pk"),
    ).values("pk")


# ── تقريرُ دفتر الزبون (#288/ب-١) ───────────────────────────────────────────
#
# **`doc_id` هنا صفُّ `ClientBookReport`** لا مستنداً مالياً: التقريرُ نفسُه لا
# يُخزَّن (قراءةٌ محضة في `accounting_office.book_reports`)، والصفُّ يقول أيُّ
# تقريرٍ على أيّ فترة. فمنه تُشتقّ الحمولةُ عند كل فتح — كاشتقاق الإشعار من
# التزامه، وبنفس الثمن المعلوم: تصحيحُ الدفتر يغيّر الرقمَ على رابطٍ قائم، وهو
# المقصود — الورقةُ تُصادق على دفتر اليوم لا على لقطةٍ ماتت.
#
# **و`user=None` في `report_payload`**: هذه ورقةُ الزبون صاحبِ الدفتر لا شاشةُ
# موظف. والقناعُ (`office.amounts.view`) قاعدةُ دورٍ داخليّ لا قاعدةُ نشرٍ: مَن
# أنشأ الرابطَ من عضوٍ مقنَّعٍ يفتحه الزبونُ كاملاً. وأمّا **من يملك الإنشاء**
# فمحروسٌ بمفتاح الكتابة في نقطة الـAPI (نمط `can_share_payment_notice`).


def load_client_book_report(tenant_id: int, doc_id: int):
    """صفُّ الرابط **بفلتر الشركة** — و`None` لما ليس لها أو لمكتبٍ آخر (404).

    و`select_related` على الشركة والزبون: الحمولةُ تقرأ `book.client` واسمَه
    و`book.tenant_id` في كل فتح، فتُقرأ مع الصفّ لا باستعلاماتٍ لاحقة.
    """
    from accounting_office.models import ClientBookReport

    return (
        ClientBookReport.objects
        .select_related("tenant", "client_book__client")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .first()
    )


def _book_reports():
    """استيرادٌ كسول كـ`_appointments`: وحدةُ التقارير تجرّ خدماتِ المكتب ونماذجه."""
    from accounting_office import book_reports

    return book_reports


def _report_of(report) -> tuple[dict | None, str]:
    """(حمولةُ التقرير، رسالةُ الخلل) من مصدرها الواحد — **لا حسابَ ثانٍ هنا**."""
    book_reports = _book_reports()
    try:
        return book_reports.report_payload(
            report.client_book,
            report.kind,
            raw_from=report.period_from.isoformat(),
            raw_to=report.period_to.isoformat(),
            user=None,
        ), ""
    except book_reports.ReportImbalance as exc:
        return None, str(exc)


def render_client_book_report(
    report_payload, *, company, problem: str = "", auto_print: bool = False,
) -> str:
    """ورقةُ التقرير المصيَّرة — يستعملها الرابطُ العامُّ ونقطةُ الطباعة معاً.

    **والقالبُ لا يعرف نوعَ التقرير**: الأعمدةُ والصفوفُ والمجاميعُ تصل من
    `book_reports.table_payload` — وهو المصدرُ الذي يقرأ منه ملفُّ Excel نفسُه.
    و`auto_print` لنقطة الطباعة وحدها: صفحةُ الزبون تُفتح للقراءة ويضغط «اطبع»
    إن أراد، ونافذةُ الطباعة تُفتح لتُطبع.
    """
    book_reports = _book_reports()
    return render_to_string(
        "docshare/client_book_report.html",
        {
            "company": company,
            "table": book_reports.table_payload(report_payload)
            if report_payload else None,
            "problem": problem,
            "watermark": book_reports.WATERMARK,
            "auto_print": auto_print,
        },
    )


def page_client_book_report(report, share) -> str:
    """صفحةُ الرابط العامّ: التقريرُ على فترته المخزَّنة، والطباعةُ من المتصفح."""
    report_payload, problem = _report_of(report)
    return render_client_book_report(
        report_payload, company=company_card(share.tenant), problem=problem,
    )


def build_client_book_report(report) -> dict:
    """حمولةُ العقد العامّ لهذا النوع — عقدٌ كاملٌ وإن كان القالبُ لا يصيّرها.

    `resolve_share` يبني الحمولةَ **دائماً** قبل أن يسأل عن `page`، فهذه الدالّةُ
    لا ترمي: ميزانٌ اختلّ بعد إنشاء الرابط يُقال في `notes` ولا يُسقِط الصفحة
    بـ500. والجدولُ الحقيقيُّ يصيَّره `page_client_book_report`.
    """
    data, problem = _report_of(report)
    book_reports = _book_reports()
    period_row = meta(
        "الفترة",
        f"{report.period_from.isoformat()} — {report.period_to.isoformat()}",
    )
    totals = (data or {}).get("totals") or {}
    return payload(
        kind="client_book_report",
        title=(data or {}).get("title") or book_reports.REPORT_LABELS.get(
            report.kind, report.kind,
        ),
        number="",
        date=report.period_to,
        # العلامةُ المائيةُ حالةُ الورقة: «نسخة عمل» — أوضحُ من شارةٍ فارغة.
        status_label=book_reports.WATERMARK,
        status_tone=TONE_WARN,
        party_title="الزبون",
        party=report.client_book.client.name,
        currency=None,
        meta_rows=[period_row, meta("ملاحظة", (data or {}).get("period_note"))],
        show_lines=False,
        totals_rows=[
            total(label, totals[key])
            for key, label in book_reports.REPORT_TOTALS.get(report.kind, ())
            if key in totals and key != "balanced"
        ],
        notes=problem,
    )


def client_book_report_doc_ids(tenant, user):
    """الصفوفُ التي يراها هذا العضو — **نطاقُ النوع في سطح الإدارة**.

    حارسُ الرؤية في مكتب المحاسبة واحدٌ (`visible_clients`) كما في الإشعار:
    صلاحيةُ `office.clients.write` تمنح كتابةَ زبائن المكتب لا رؤيةَ زبائن
    الزملاء. وبلا هذا النطاق يقرأ عضوٌ روابطَ زملائه ويُبطلها بمعرّفاتٍ متسلسلة.
    """
    from accounting_office import services as office_services
    from accounting_office.models import ClientBookReport

    return ClientBookReport.objects.filter(
        tenant=tenant,
        client_book__client_id__in=(
            office_services.visible_clients(tenant, user).values("pk")
        ),
    ).values("pk")


# ── إشعارُ القبض وكشفُ الحساب (#283/ب) ───────────────────────────────────────
#
# **البناءُ في `accounting_office.payments` لا هنا**: الرقمُ والتخصيصُ و«اللي
# عليه» والرصيدُ الجاري أحكامُ مالٍ في الموديول الذي يملكها، ونسخةٌ ثانية منها في
# `docshare` تفترق عن الأولى بأوّل تخصيص. فحدودُ هذا الملفّ — كما في
# `payment_notice` — **الورقة** وحدها: ما يُقرأ من الصفّ، وما يُصيَّر للزبون.
def _payments():
    """استيرادٌ كسول: `payments` يجرّ خدماتِ المكتب ونماذجها (نمط `_appointments`)."""
    from accounting_office import payments as office_payments

    return office_payments


def load_fee_receipt(tenant_id: int, doc_id: int):
    """الدفعةُ التي يفتح الإشعارُ سندَها — أو `None` لمكتبٍ آخر أو صفٍّ ذهب.

    **ولا فلترةَ رؤيةٍ هنا**: الصفحةُ العامة يعرّفها توكنُها لا مستخدمُها،
    والنطاقُ في `fee_receipt_doc_ids` لسطح الإدارة وحده (كما في الإشعار).
    """
    from accounting_office.models import FeePayment

    return (
        FeePayment.objects
        .select_related("client", "tenant")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .first()
    )


def load_fee_statement(tenant_id: int, doc_id: int):
    """صفُّ الكشف الذي يُعنوِن الورقة — فترتُه وحدها تُقرأ منه، والأرقامُ تُحسب."""
    from accounting_office.models import FeeStatement

    return (
        FeeStatement.objects
        .select_related("client", "tenant")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .first()
    )


def _receipt_of(payment) -> dict:
    """بياناتُ الإشعار من مصدرها الواحد — بلا قناعٍ هنا: الورقةُ للزبون."""
    return _payments().receipt_payload(payment.tenant, payment, masked=False)


def _statement_of(statement) -> dict:
    return _payments().statement_payload(
        statement.tenant,
        statement.client,
        period_from=statement.period_from,
        period_to=statement.period_to,
        masked=False,
    )


def build_fee_receipt(payment) -> dict:
    """حمولةُ العقد العامّ للإشعار — المبلغُ المقبوض وما بقي على الزبون.

    `show_lines=False`: جدولُ `share.html` أعمدةُ كميةٍ وسعرٍ وضريبة، وتخصيصاتُ
    الدفعة ليست بنودَ بيع. تفصيلُها في `page_fee_receipt` وحدها.
    """
    receipt = _receipt_of(payment)
    return payload(
        kind="fee_receipt",
        title=receipt["title"],
        number=receipt["number"],
        date=receipt["date"],
        status_label="مدفوع",
        status_tone=TONE_OK,
        party_title="الزبون",
        party=receipt["client"]["name"],
        currency=None,
        meta_rows=[
            meta("رقم الإشعار", receipt["number"]),
            meta("طريقة الدفع", receipt["method_label"]),
            meta("الباقي على الزبون", receipt["due"]),
        ],
        lines=[],
        show_lines=False,
        show_line_prices=False,
        totals_rows=[total("المبلغ المقبوض", receipt["amount"], strong=True)],
        grand_total=receipt["amount"],
        notes=receipt["note"],
    )


def build_fee_statement(statement) -> dict:
    """حمولةُ العقد العامّ للكشف — رصيدُ أول المدة والحركاتُ والرصيدُ الختامي."""
    sheet = _statement_of(statement)
    invoice_label = term(statement.tenant, "doc.sales_invoice")
    return payload(
        kind="fee_statement",
        title=sheet["title"],
        number="",
        date=sheet["to"] or "",
        status_label="كشف حساب",
        status_tone=TONE_MUTED,
        party_title="الزبون",
        party=sheet["client"]["name"],
        currency=None,
        meta_rows=[
            meta("من تاريخ", sheet["from"], VALUE_DATE),
            meta("إلى تاريخ", sheet["to"], VALUE_DATE),
            meta("الباقي على الزبون اليوم", sheet["due"], VALUE_MONEY),
        ],
        lines=[],
        show_lines=False,
        show_line_prices=False,
        totals_rows=[
            total("رصيد أول المدة", sheet["opening_balance"]),
            total(invoice_label, sheet["totals"]["invoices"]),
            total("دفعات", sheet["totals"]["payments"]),
            total("شطوب", sheet["totals"]["write_offs"]),
            total("الرصيد الختامي", sheet["closing_balance"], strong=True),
        ],
        grand_total=sheet["closing_balance"],
    )


def page_fee_receipt(payment, share) -> str:
    """ورقةُ إشعار القبض المصيَّرة — الرقمُ المخزَّن، والطريقةُ، والشيكُ، والباقي."""
    receipt = _receipt_of(payment)
    return render_to_string(
        "docshare/fee_receipt.html",
        {
            "title": receipt["title"],
            "company": company_card(share.tenant),
            "receipt": receipt,
        },
    )


def page_fee_statement(statement, share) -> str:
    """ورقةُ كشف الحساب المصيَّرة — الحركاتُ الثلاث برصيدٍ جارٍ وأرصدةِ الرأس."""
    return render_to_string(
        "docshare/fee_statement.html",
        {
            "title": _payments().STATEMENT_TITLE,
            "company": company_card(share.tenant),
            "sheet": _statement_of(statement),
        },
    )


def _visible_fee_clients(tenant, user):
    """زبائنُ هذا العضو في مكتب المحاسبة — مصدرُ الرؤية الواحد، باستيرادٍ كسول."""
    from accounting_office import services as office_services

    return office_services.visible_clients(tenant, user).values("pk")


def fee_receipt_doc_ids(tenant, user):
    """دفعاتُ زبائنَ يراها العضو — **نطاقُ النوع في سطح الإدارة** (#283/ب).

    بلا هذا النطاق كان محاسبٌ بلا `office.clients.all` يأخذ — من قائمة أنواع
    المستندات — توكنَ إشعار كلّ دفعةٍ في الشركة ويُبطلها، بمعرّفاتٍ متسلسلةٍ
    تُخمَّن. ودفعةُ مكتبٍ آخر **404** من العزل نفسه.
    """
    from accounting_office.models import FeePayment

    return FeePayment.objects.filter(
        tenant=tenant,
        client_id__in=_visible_fee_clients(tenant, user),
    ).values("pk")


def fee_statement_doc_ids(tenant, user):
    """كشوفُ زبائنَ يراها العضو — النطاقُ نفسه، على صفوف `FeeStatement`."""
    from accounting_office.models import FeeStatement

    return FeeStatement.objects.filter(
        tenant=tenant,
        client_id__in=_visible_fee_clients(tenant, user),
    ).values("pk")


# ── فاتورةُ الأتعاب الورقية (#282، أ٢/١) ─────────────────────────────────────
#
# **نوعٌ ثالثٌ في مكتب المحاسبة**: مستندٌ مرقَّمٌ يُصدره المكتبُ لزبونه بعد
# اعتماد مسودّة الشهر. ورقتُه تُصيَّر في `accounting_office.fee_invoices`
# (`render_sheet`) لا هنا: الحقولُ القانونية والنسختان وسطرُ النفي وحسابُ
# الضريبة قراراتٌ تخصّ المكتب، و`docshare` يعرف الرابطَ والحمولةَ العامةَ وحدها.
#
# **وثلاثةُ حرّاسٍ كإشعار الدفع**: وحدةٌ مرخّصة (`"module"`)، ونطاقُ
# `visible_clients` في سطح الإدارة (`"scope"`)، ومنعُ الإنشاء من الباب العامّ
# (`views.create` — 400) لأن السطح يأخذ أيَّ `doc_id` متسلسلٍ يُخمَّن.


def _fee_invoices():
    """استيرادٌ كسول: وحدةُ الفواتير تجرّ خدماتِ المكتب ونماذجه."""
    from accounting_office import fee_invoices

    return fee_invoices


def load_fee_invoice(tenant_id: int, doc_id: int):
    """الفاتورةُ التي يفتحها الرابط — **بلا فلترة حالة** (كالإشعار).

    الفاتورةُ الملغاةُ تُعرض موسومةً «ملغاة» لا تُخفى: رابطٌ حيٌّ يومياً لا يجوز
    أن يصمت بعد إلغاء، والزائرُ يقرأ ما جرى بدل صفحة «غير موجود».
    """
    from accounting_office.models import FeeInvoice

    return (
        FeeInvoice.objects
        .select_related("client", "tenant", "source_draft", "related_invoice")
        .filter(pk=doc_id, tenant_id=tenant_id)
        .first()
    )


def build_fee_invoice(invoice) -> dict:
    """حمولةُ العقد العامّ للفاتورة — من بانِي `fee_invoices` الواحد."""
    return _fee_invoices().share_payload(invoice)


def page_fee_invoice(invoice, share) -> str:
    """ورقةُ الفاتورة المصيَّرة — حقولُها الثمانيةُ المبنيّةُ من التسعة أو السبعة، وسطرُ النفي.

    الصفحةُ **لا تمرّ بحمولة `payload`** (كالإشعار وشهادة الكفالة): الحمولةُ
    تحرس القائمةَ البيضاء لواجهة JSON، والورقةُ لها سياقُها المحسوب في
    `fee_invoices.sheet_context` — وفيه النفيُ الثابتُ الذي لا يُطفأ.
    """
    return _fee_invoices().render_sheet(invoice)


def fee_invoice_doc_ids(tenant, user):
    """الفواتيرُ التي يراها هذا العضو — نطاقُ النوع في سطح الإدارة (#282/أ٢).

    نفسُ حارس إشعار الدفع: صلاحيةُ النوع تمنح كتابةَ زبائن المكتب لا رؤيةَ
    زبائن الزملاء، فمحاسبٌ بلا `office.clients.all` كان يأخذ توكنَ فاتورةِ
    زميلٍ ورابطَها، ويُبطل أيَّها شاء بمعرّفاتٍ متسلسلة.
    """
    from accounting_office.models import FeeInvoice
    from accounting_office import services as office_services

    return FeeInvoice.objects.filter(
        tenant=tenant,
        client_id__in=office_services.visible_clients(tenant, user).values("pk"),
    ).values("pk")


# ── النسخةُ الكاملة وبيانُ الأسماء (#290) ────────────────────────────────────
#
# **نوعان يخصّان المكتبَ نفسَه لا طرفاً من أطرافه**: نسخةُ بياناته الكاملة
# (تسعُ أوراق) وبيانُ أسماء زبائنه للدائرة (م111، فلسطين وحدها). و`doc_id`
# فيهما **معرّفُ المكتب**، لأن موضوعَ الوثيقة هو المكتب — فلا صفَّ موديلٍ ثانٍ
# يُنشأ ويُهجَّر لهذه الحاجة، والقيدُ `(tenant, doc_type, doc_id)` نفسُه يمنع
# خلطَ مكتبين: المُحمِّلُ يرفض `doc_id != tenant_id` فيصير مكتبٌ آخر **404**.
#
# **والبناءُ في `accounting_office.office_exports` وحده**: الجداولُ التسعةُ
# تُقرأ من صفوف المكتب كما يقرؤها ملفُّ Excel — لا نسخةً ثانية من الجداول هنا،
# وإلا اختلف الرابطُ عن الملفّ عند أوّل عمودٍ يُضاف.
OFFICE_DATA_EXPORT_TITLE = "نسخة بيانات المكتب"
OFFICE_CLIENT_NAMES_TITLE = "بيان أسماء زبائن المكتب"
#: ملاحظةُ الورقتين — تقول ما هي وما ليست، فلا تُقدَّم لجهةٍ على أنها إقرار.
OFFICE_DATA_EXPORT_NOTE = (
    "نسخةٌ من بيانات المكتب كما هي في تاريخ التصدير — ليست مستنداً ضريبياً "
    "ولا تُغني عن سجلّات المكتب الرسمية."
)
OFFICE_CLIENT_NAMES_NOTE = (
    "بيانٌ بأسماء زبائن المكتب وعناوينهم وأرقام ملفاتهم الضريبية — للدائرة "
    "الفلسطينية للضريبة (نموذج م111)."
)


def _office_exports():
    """استيرادٌ كسول كـ`_book_reports`: الوحدة تجرّ خدماتِ المكتب ونماذجه."""
    from accounting_office import office_exports

    return office_exports


def _office_of(tenant_id: int, doc_id: int):
    """المكتبُ نفسُه مستنداً — و`None` لما ليس مكتبَه (404).

    الشرطُ `doc_id == tenant_id` ليس تحسيناً بل الحارسَ: بلا هذا تمرّ
    `GET /api/share/<token>` لمكتبٍ آخر بمجرّد تخمين `doc_id`.
    """
    from tenants.models import Tenant

    if doc_id != tenant_id:
        return None
    return Tenant.objects.filter(pk=tenant_id).first()


def load_office_data_export(tenant_id: int, doc_id: int):
    return _office_of(tenant_id, doc_id)


def load_office_client_names(tenant_id: int, doc_id: int):
    return _office_of(tenant_id, doc_id)


def _office_name(office) -> str:
    """اسمُ المكتب كما في ترويسة مستنداته، لا اسمُه المسجَّل وحده."""
    return company_card(office)["company_name_primary"] or office.CompanyName or ""


def build_office_data_export(office) -> dict:
    """حمولةُ العقد العامّ للنسخة — العلامةُ والاسمُ وعددُ صفوف كل ورقة.

    الجداولُ نفسُها تُصيَّرها صفحةُ النوع (`page`)، وهذه الحمولةُ تخدم واجهةَ
    JSON و`resolve_share` الذي يبنيها **دائماً** قبل أن يسأل عن `page`.
    """
    from django.utils import timezone

    office_exports = _office_exports()
    tables = office_exports.full_export_tables(office)
    return payload(
        kind="office_data_export",
        title=OFFICE_DATA_EXPORT_TITLE,
        number="",
        date=timezone.localdate(),
        status_label=_book_reports().WATERMARK,
        status_tone=TONE_WARN,
        party_title="المكتب",
        party=_office_name(office),
        currency=None,
        meta_rows=[
            meta("تاريخ التصدير", timezone.localdate(), VALUE_DATE),
            meta("عدد الزبائن", next(
                (
                    table["count"] for table in tables
                    if table["key"] == office_exports.SHEET_CLIENTS
                ),
                0,
            )),
        ],
        show_lines=False,
        show_line_prices=False,
        notes=OFFICE_DATA_EXPORT_NOTE,
    )


def build_office_client_names(office) -> dict:
    """حمولةُ العقد العامّ لبيان الأسماء — عددُ الزبائن واسمُ المكتب."""
    from django.utils import timezone

    office_exports = _office_exports()
    return payload(
        kind="office_client_names",
        title=OFFICE_CLIENT_NAMES_TITLE,
        number="",
        date=timezone.localdate(),
        # البيانُ سجلُّ الدائرة لا «نسخةَ عمل» — شارتُه محايدةٌ بلا تحذير.
        status_label="لسجلّ الدائرة (م111)",
        status_tone=TONE_MUTED,
        party_title="المكتب",
        party=_office_name(office),
        currency=None,
        meta_rows=[
            meta("تاريخ التصدير", timezone.localdate(), VALUE_DATE),
            meta("عدد الزبائن", len(office_exports.client_names_rows(office))),
        ],
        show_lines=False,
        show_line_prices=False,
        notes=OFFICE_CLIENT_NAMES_NOTE,
    )


def page_office_data_export(office, share) -> str:
    """ورقةُ النسخة الكاملة — **الجداولُ التسعةُ نفسُها** بملخّصٍ عدديّ لكل ورقة."""
    from django.utils import timezone

    office_exports = _office_exports()
    return render_to_string(
        "docshare/office_data_export.html",
        {
            "company": company_card(share.tenant),
            "title": OFFICE_DATA_EXPORT_TITLE,
            "tables": office_exports.full_export_tables(office),
            "watermark": _book_reports().WATERMARK,
            "generated_on": timezone.localdate(),
            "note": OFFICE_DATA_EXPORT_NOTE,
        },
    )


def page_office_client_names(office, share) -> str:
    """ورقةُ بيان الأسماء — جدولٌ واحدٌ يُقدَّم للدائرة، و«PDF» من حوار الطباعة."""
    from django.utils import timezone

    office_exports = _office_exports()
    return render_to_string(
        "docshare/office_client_names.html",
        {
            "company": company_card(share.tenant),
            "title": OFFICE_CLIENT_NAMES_TITLE,
            "rows": office_exports.client_names_rows(office),
            "generated_on": timezone.localdate(),
            "note": OFFICE_CLIENT_NAMES_NOTE,
        },
    )


def _office_export_doc_ids(tenant, user):
    """نطاقُ النوعين في سطح الإدارة: مكتبُ المالك وحده، وما عداه 404 لا 403."""
    return _office_exports().owned_doc_ids(tenant, user)


ACCOUNTING_DOC_TYPES = {
    "payment_notice": {
        "label": "إشعار دفع",
        "loader": load_payment_notice,
        "builder": build_payment_notice,
        #: الصلاحيةُ هي صلاحيةُ إضافة زبائن المكتب وتعديلهم — الإشعارُ وثيقةُ
        #: زبونٍ يفتحها الزبونُ نفسه، ومَن يملك كتابةَ العميل يملك ما يُرسَل إليه.
        "permission": "office.clients.write",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        #: مفتاحٌ اختياريّ: النوعُ يُصيِّر ورقته بنفسه لأن الألوانَ لا تدخل
        #: قائمةَ السطر البيضاء العامة (انظر رأس الملف).
        "page": page_payment_notice,
        #: **الوحدةُ التي يعيش فيها النوع** (#285/م٢): شركةٌ أُطفئ ترخيصُها لا
        #: تُصيَّر لها ورقةٌ تحمل أسماءَ زبائنها ومبالغهم — الرابطُ الحيّ يُسقَط
        #: بـ410 كما تُسقَط شهادةُ ما بعد البيع، ويخرج النوعُ من القائمة ومن
        #: القراءة والإبطال. وأمّا إنشاؤه فممنوعٌ من هذا السطح بـ400 **قبل**
        #: الترخيص (البند التالي)، فلا يُقاس عليه.
        "module": "accounting_office",
        #: **ونطاقُه في سطح الإدارة** (#285/م٣): انظر `payment_notice_doc_ids`.
        "scope": payment_notice_doc_ids,
    },
    "client_book_report": {
        "label": "تقرير دفتر زبون",
        "loader": load_client_book_report,
        "builder": build_client_book_report,
        #: مفتاحُ الكتابة نفسُه الذي يحكم الإشعار: من يوزّع مستخرجَ زبونٍ برابطٍ
        #: عامّ يفعل فعلاً كتابياً، لا قراءة. والـview يحرسه بـ`require_write`.
        "permission": "office.clients.write",
        #: جمهورُه **الزبون** صاحبُ الدفتر — لا مورّدٌ ولا موظفُ مستودع.
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        #: ورقته جدولُ التقرير، فلا يصيّرها القالبُ العامّ.
        "page": page_client_book_report,
        #: وحدةُ المكتب: ترخيصٌ مُطفأ ⇒ الرابطُ الحيّ **410** كما في الإشعار.
        "module": "accounting_office",
        "scope": client_book_report_doc_ids,
    },
    #: #283/ب: إشعارُ قبضِ دفعة — الرقمُ المخزَّن يُقرأ ولا يُولَّد عند العرض.
    "fee_receipt": {
        "label": "إشعار قبض",
        "loader": load_fee_receipt,
        "builder": build_fee_receipt,
        #: صلاحيةُ نوع الإشعار نفسها: ورقةُ زبونٍ يفتحها الزبون، ومَن يكتب
        #: بياناته يملك ما يُرسَل إليه. والإنشاءُ من سطح المكتب وحده (400 هنا).
        "permission": "office.clients.write",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        "page": page_fee_receipt,
        "module": "accounting_office",
        "scope": fee_receipt_doc_ids,
    },
    #: #283/ب: كشفُ حساب زبونٍ لفترة — ورقةٌ مالية كاملةُ الأرصدة.
    "fee_statement": {
        "label": "كشف حساب",
        "loader": load_fee_statement,
        "builder": build_fee_statement,
        "permission": "office.clients.write",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        "page": page_fee_statement,
        "module": "accounting_office",
        "scope": fee_statement_doc_ids,
    },
    "fee_invoice": {
        "label": OFFICE_FEE_INVOICE_LABEL,
        "loader": load_fee_invoice,
        "builder": build_fee_invoice,
        #: صلاحيةُ نوع الإشعار نفسها: ورقةُ زبونٍ يفتحها الزبونُ نفسه، ومن يملك
        #: كتابةَ الزبون يملك ما يُرسَل إليه (وصولُه إلى الفاتورة يبقى محصوراً
        #: بـ`visible_clients` في `"scope"`).
        "permission": "office.clients.write",
        "audience": AUDIENCE_CUSTOMER,
        "decision": None,
        #: ورقةٌ تُصيَّر بنفسها: الحقولُ القانونية والنسختان وسطرُ النفي القاطع
        #: لا تحتملها قائمةُ السطر البيضاء العامة (عشرةُ مفاتيح بلا نفيٍ فيها).
        "page": page_fee_invoice,
        #: **وحدةٌ مرخّصة** كإشعار الدفع: رابطٌ حيٌّ لشركةٍ أُطفئ ترخيصُها 410.
        "module": "accounting_office",
        #: **ونطاقٌ في سطح الإدارة**: `doc_id` فاتورةُ زبونٍ يراه العضو وحده.
        "scope": fee_invoice_doc_ids,
    },
    #: #290: نسخةُ بيانات المكتب الكاملة — ورقةٌ بجداولها التسعة.
    "office_data_export": {
        "label": "نسخة بيانات المكتب",
        "loader": load_office_data_export,
        "builder": build_office_data_export,
        #: **أعلى مفتاحٍ في المكتب** لأن الملفَّ يحمل زبائنَ المكتب كلَّهم
        #: ومبالغَهم: صلاحيةٌ أوسع من `office.clients.write` وحدها. والبابُ
        #: المقصود `POST exports/full-link/`، وهو يزيد الدورَ ورؤيةَ المبالغ؛
        #: فسطحُ المشاركة يبقى حدُّه الأدنى هذا، والنطاقُ أدناه يقيّده للمالك.
        "permission": "office.clients.all",
        #: **جمهورُ المكتب** لا الزبون: أسماءُ كل الزبائن ومبالغُهم ليست ورقةً
        #: يجوز أن تُسلَّم لزبون.
        "audience": AUDIENCE_OFFICE,
        "decision": None,
        "page": page_office_data_export,
        "module": "accounting_office",
        "scope": _office_export_doc_ids,
    },
    #: #290: بيانُ أسماء زبائن المكتب (م111) — فلسطينيّاً وحده، والحارسُ في
    #: `office_exports.assert_client_names_available`.
    "office_client_names": {
        "label": "بيان أسماء زبائن المكتب",
        "loader": load_office_client_names,
        "builder": build_office_client_names,
        "permission": "office.clients.all",
        "audience": AUDIENCE_OFFICE,
        "decision": None,
        "page": page_office_client_names,
        "module": "accounting_office",
        "scope": _office_export_doc_ids,
    },
}
