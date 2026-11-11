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
"""
from django.template.loader import render_to_string

from accounting_office.models import Obligation
from docshare.documents._contract import (
    AUDIENCE_CUSTOMER,
    TONE_DANGER,
    TONE_MUTED,
    TONE_OK,
    VALUE_DATE,
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
}
