"""فاتورةُ الأتعاب الورقية — الترقيمُ والإلغاءُ والإشعارُ الدائن والورقة (#282، أ٢/١).

**المنطقُ كلُّه هنا**، والـ`views.py` يترجم فقط: قرارُ رقمٍ أو لونٍ أو نصٍّ يعيش في
موضعٍ واحد يُقرأ ويُختبر، لا في نقطة API تُنسخ قاعدتُها عند أول استعمالٍ ثانٍ.

**وهذه الوحدةُ لا تحسب أتعاباً**: مصدرُ المبالغ `FeeDraft` المعتمدة (أ١)، والقناعُ
`fees.amounts_masked`. ما تضيفه هنا **المستند**: رقمٌ من عدّادٍ مقفول، وتاريخ،
وعنوانٌ لقطة، وضريبةٌ مؤرَّخة على الصفّ، وسلسلةٌ ثانيةٌ للإشعار الدائن.

**ثلاثُ قواعدَ لا رابعة:**

1. **الترقيمُ عدّادٌ لا `MAX+1`** (`_next_number`): `select_for_update` على
   `FeeInvoiceSequence` داخل `transaction.atomic`، والفرادةُ `(tenant, number)`
   طبقةٌ ثانية تُساند القفل. وسلسلتان: `أتعاب-{السنة}` للفاتورة والتكميلية،
   و`إشعار-أتعاب-{السنة}` للإشعار الدائن — فإشعارٌ برقمٍ من سلسلة الفواتير يقرأ
   فاتورةً ثانية في كشف الزبون.
2. **لا حذفَ ولا تعديل**: `DELETE`/`PUT`/`PATCH` مُغلقةٌ في الـ`http_method_names`،
   والإلغاءُ `POST` يكتب `cancelled_at` **قبل إنشاء الرابط وحده**: ورقةٌ بيد
   الزبون لا يُقال لها «أُلغيت» بضغطةٍ في الخادم، والتصحيحُ إشعارٌ دائن.
3. **«ليست فاتورة ضريبية» ثابتة**: `is_tax_invoice` خاصيّةٌ `False` في النموذج لا
   حقلاً، وسطرُ النفي يُصيَّر في كل صفحةٍ من `FEE_INVOICE_NOT_TAX_LINES` — لا
   إعدادَ يُطفئه ولا فرعَ قالبٍ يحذفه.

**ومصدرُ الضريبة ومصدرُ العنوان إعدادُ النظام لا اختراع:** `tax_system` من
`settings_registry` يختار حقولَ الورقة (فلسطين: م4/1 التسعة والنسختان، إسرائيل:
`§9א` السبعة)، و«المكتب مشتغل مرخّص» يُقرأ من **رقم المشتغل المرخّص** في ترويسة
الشركة (`tenants.TenantSettings.licensed_dealer_no`): لا إعدادَ مستقلّاً له، وورقةٌ
بلا رقم تسجيلٍ لا تصلح فاتورةً أصلاً. والنسبةُ تُؤرَّخ على الصفّ (`tax_total`)،
فلا تغييرُ نسبةٍ لاحقٌ يعيد كتابة ورقةٍ خرجت.
"""
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounting_office import fees, services
from accounting_office.models import (
    FEE_INVOICE_KIND_CREDIT_NOTE,
    FEE_INVOICE_KIND_INVOICE,
    FEE_INVOICE_KIND_LABELS,
    FEE_INVOICE_KIND_SUPPLEMENTARY,
    FEE_INVOICE_NOT_TAX_LINE_PS,
    FEE_INVOICE_NOT_TAX_LINES,
    FEE_INVOICE_TITLES,
    FEE_LINE_SOURCE_LABELS,
    REMINDER_BALANCE,
    FeeInvoice,
    FeeInvoiceSequence,
    fee_invoice_credit_series,
    fee_invoice_number,
    fee_invoice_series,
)
from core.access import user_has_perm
from tenants.letterhead import company_card

AMOUNT_QUANTUM = Decimal("0.01")

#: **استحقاقُ فاتورة الأتعاب**: سبعةُ أيامٍ من إصدارها. رقمُ منتجٍ لا إعداد: مكتبٌ
#: يمنح سبعةً وآخر ثلاثين، والمرحلةُ الأولى سبعةٌ ثابتةٌ حتى يُطلب إعدادُها.
INVOICE_DUE_DAYS = 7

#: رسالةٌ واحدةٌ للفاتورة: بعد إرسالها (أو تنحيتها) يسقط بندُها من «جاهز للإرسال».
#: ولا عدّادَ «س من ن» لسقفٍ لا إعدادَ له — والسقفُ `1` بنيويّ كتذكير الموعد.
INVOICE_REMINDER_MAX = 1

TAX_SYSTEM_PS = "PS"
TAX_SYSTEM_IL = "IL"

#: وحدةُ الكمية في سطر الفاتورة: فاتورةُ أتعابٍ خدمةٌ واحدةٌ لكل سطر، والعمودُ
#: القانونيّ الرابع في م4/1 يطلب «النوع، الكمية، الوحدة، سعر الوحدة، ونسبة الضريبة».
LINE_QUANTITY = Decimal("1")
LINE_UNIT_PS = "خدمة"
LINE_UNIT_IL = "שירות"

#: الحقولُ التي يقنّعها `mask_amounts` في صفّ الفاتورة — من `AMOUNT_KEYS` العامّ
#: وفيه `tax_total`، والثابتُ المحلّي يسمّي المستعملَ هنا وحده.
INVOICE_AMOUNT_KEYS: tuple[str, ...] = ("total", "tax_total")


# ── العنوان والنظام والترخيص: مصادرُ لا تُخترَع ────────────────────────────────
def tax_system_for(tenant, client) -> str:
    """نظامُ الزبون الضريبيّ — يورث نظامَ المكتب ما لم يُخصَّص (`tax_system`)."""
    value = services.resolve_setting(tenant, "tax_system", client=client)
    return value if value in (TAX_SYSTEM_PS, TAX_SYSTEM_IL) else TAX_SYSTEM_PS


def not_tax_line(tax_system: str) -> str:
    """سطرُ النفي بلغة الورقة — **ثابتٌ لا إعداد**، ويُصيَّر في كل صفحة."""
    return FEE_INVOICE_NOT_TAX_LINES.get(tax_system, FEE_INVOICE_NOT_TAX_LINE_PS)


def office_is_licensed(tenant) -> bool:
    """هل المكتبُ «مشتغلٌ مرخّص»؟ — **رقمُ تسجيله هو الجواب**.

    لا إعدادَ مستقلّاً لسؤال «المكتب مشتغل مرخّص» في سجلّ الإعدادات، وإضافةُ
    مفتاحٍ له تُغيّر شكلَ السجلّ المحروس حرفياً بـ`test_settings.py` وهي قرارُ
    منتجٍ لا قرارُ تنفيذ. والمصدرُ الموجود أصلاً (`TenantSettings.
    licensed_dealer_no`) هو نفسُه «رقمُ تسجيله» الذي يطلبه الحقلُ الأوّل من
    م4/1: مكتبٌ بلا رقم تسجيلٍ لا يطبع فاتورةً رسميةً ولا يُحصّل ضريبة.
    """
    return bool((company_card(tenant).get("licensed_dealer_no") or "").strip())


def archived_rate(tenant) -> Decimal:
    """نسبةُ الضريبة السارية **لحظةَ الإصدار** — تُؤرَّخ على الصفّ في `tax_total`.

    المصدرُ نسبةُ الشركة الافتراضية (`TenantSettings.default_vat_rate`) لأنها
    النسبةُ التي تعرفها المنصّةُ عن هذا المكتب؛ ولا جدولَ نسبٍ مؤرَّخٍ لكل نظامٍ
    في المستودع بعد، فتُخزَّن النتيجةُ على الفاتورة بدل قراءتها وقت العرض.
    """
    tenant_settings = getattr(tenant, "settings", None)
    rate = getattr(tenant_settings, "default_vat_rate", None)
    if rate is None:
        return Decimal("0")
    return Decimal(rate)


def _tax_of(net, *, rate: Decimal) -> Decimal:
    """نصيبُ الضريبة من مبلغٍ قبل الضريبة — بغورةٍ واحدةٍ ونصفٍ للأعلى."""
    if rate <= 0:
        return Decimal("0")
    return (Decimal(net) * rate / 100).quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def _net_of(gross, *, rate: Decimal) -> Decimal:
    """المبلغُ قبل الضريبة من إجماليٍّ شاملٍ لها — عكسُ `_tax_of`."""
    if rate <= 0:
        return Decimal(gross).quantize(AMOUNT_QUANTUM)
    return (Decimal(gross) * 100 / (100 + rate)).quantize(
        AMOUNT_QUANTUM, rounding=ROUND_HALF_UP,
    )


def _local_day(moment) -> date:
    return timezone.localdate(moment)


def _issued_at(day=None) -> datetime:
    """لحظةُ الإصدار: منتصفُ نهار يومٍ صريح، أو ساعتُ النظام.

    والمنتصفُ نهاراً كـ`fees._generated_at`: استحقاقُ سبعة أيامٍ يُقاس بتاريخ
    الإصدار، ويومٌ ماضٍ يُكتب بتاريخه لا بتاريخ اليوم.
    """
    if day is None:
        return timezone.now()
    return timezone.make_aware(datetime.combine(day, time(hour=12)))


# ── الترقيم: عدّادٌ مقفول ─────────────────────────────────────────────────────
def _next_number(tenant, *, year, series) -> str:
    """**الرقمُ من العدّاد المقفول** — لا `MAX(number)+1` ولا `count()+1`.

    `select_for_update` على صفّ العدّاد يُسلسل الكُتّاب، والزيادةُ تُكتب في
    المعاملة نفسها؛ فمن دخل بعد أوّله قرأ القيمةَ الجديدة لا القديمة. ولا تُنادَ
    خارج `transaction.atomic()`: القفلُ بلا معاملةٍ لا معنى له.
    """
    sequence, _created = FeeInvoiceSequence.objects.select_for_update().get_or_create(
        tenant=tenant,
        year=year,
        series=series,
    )
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    return fee_invoice_number(series, sequence.last_number)


# ── الإصدار: بعد الاعتماد، ومرّةً واحدة ───────────────────────────────────────
def issue_for_draft(draft, *, actor=None, day=None) -> FeeInvoice:
    """يُصدر فاتورةَ المسودّة المعتمدة — **متكرِّرةُ الأمان** على المسودّة نفسها.

    `get_or_create` على `OneToOneField(draft)` هو الحارس: نداءٌ ثانٍ (أو اعتمادٌ
    متزامنٌ اجتاز قفلَه) يعيد الصفَّ القائم ولا يُرقّم ثانياً. والرقمُ يُستهلك
    **داخل** المعاملة، فمسودّةٌ تفشل كتابتُها لا تُحرق رقماً من السلسلة.
    """
    tenant = draft.tenant
    with transaction.atomic():
        existing = (
            FeeInvoice.objects
            .select_related("client", "tenant")
            .filter(draft=draft)
            .first()
        )
        if existing is not None:
            return existing
        tax_system = tax_system_for(tenant, draft.client)
        net = Decimal(draft.total)
        rate = archived_rate(tenant) if office_is_licensed(tenant) else Decimal("0")
        tax_total = _tax_of(net, rate=rate)
        issued_at = _issued_at(day)
        series = fee_invoice_series(_local_day(issued_at).year)
        try:
            with transaction.atomic():
                return FeeInvoice.objects.create(
                    tenant=tenant,
                    client=draft.client,
                    draft=draft,
                    kind=FEE_INVOICE_KIND_INVOICE,
                    number=_next_number(
                        tenant, year=_local_day(issued_at).year, series=series,
                    ),
                    title=FEE_INVOICE_TITLES.get(tax_system, FEE_INVOICE_TITLES[TAX_SYSTEM_PS]),
                    total=net + tax_total,
                    tax_total=tax_total,
                    issued_at=issued_at,
                    issued_by=actor if getattr(actor, "pk", None) else None,
                )
        except IntegrityError:
            # سباقٌ على المسودّة نفسها: القيدُ `OneToOne` هو الحكم — يُعاد القائم.
            again = FeeInvoice.objects.filter(draft=draft).first()
            if again is not None:
                return again
            raise


def issue_for_drafts(drafts, *, actor=None, day=None) -> list[FeeInvoice]:
    """يُصدر فواتيرَ مجموعةِ مسودّاتٍ **دفعةً واحدة** — مسارُ «اعتمد الكل».

    الكلفةُ **ثابتةٌ لا تكبر بعدد المسودّات**: قراءةُ الصادر منها استعلامٌ واحد،
    ثم قفلُ العدّاد مرّةً واحدة، و`bulk_create` واحد، وتحديثُ العدّاد مرّةً —
    لا ثلاثُ استعلاماتٍ لكل مسودّة. وهذا شرطُ `test_fees` القائم: «اعتمد الكل»
    لا يقرأ ولا يكتب صفّاً صفّاً.

    والمسودّاتُ التي لها فاتورةٌ تُتخطّى (`get_or_create` في المفرد تبقى للنداء
    الواحد)، فالنداءُ متكرِّرُ الأمان كذلك.
    """
    drafts = [draft for draft in drafts if getattr(draft, "pk", None)]
    if not drafts:
        return []
    tenant = drafts[0].tenant
    already = set(
        FeeInvoice.objects
        .filter(draft_id__in=[draft.pk for draft in drafts])
        .values_list("draft_id", flat=True),
    )
    pending = [draft for draft in drafts if draft.pk not in already]
    if not pending:
        return []
    issued_at = _issued_at(day)
    year = _local_day(issued_at).year
    series = fee_invoice_series(year)
    tax_systems = services.resolve_settings_for_clients(
        tenant, [services.TAX_SYSTEM_KEY], [draft.client for draft in pending],
    )
    rate = archived_rate(tenant) if office_is_licensed(tenant) else Decimal("0")
    issued_by = actor if getattr(actor, "pk", None) else None
    with transaction.atomic():
        sequence, _created = FeeInvoiceSequence.objects.select_for_update().get_or_create(
            tenant=tenant, year=year, series=series,
        )
        rows = []
        for offset, draft in enumerate(pending, start=1):
            tax_system = tax_systems.get(draft.client_id, {}).get(
                services.TAX_SYSTEM_KEY,
            )
            tax_system = tax_system if tax_system in (TAX_SYSTEM_PS, TAX_SYSTEM_IL) else TAX_SYSTEM_PS
            net = Decimal(draft.total)
            tax_total = _tax_of(net, rate=rate)
            rows.append(FeeInvoice(
                tenant=tenant,
                client=draft.client,
                draft=draft,
                kind=FEE_INVOICE_KIND_INVOICE,
                number=fee_invoice_number(series, sequence.last_number + offset),
                title=FEE_INVOICE_TITLES.get(tax_system, FEE_INVOICE_TITLES[TAX_SYSTEM_PS]),
                total=net + tax_total,
                tax_total=tax_total,
                issued_at=issued_at,
                issued_by=issued_by,
            ))
        FeeInvoice.objects.bulk_create(rows)
        sequence.last_number += len(rows)
        sequence.save(update_fields=["last_number"])
    return rows


def ensure_sequence(tenant, *, year) -> FeeInvoiceSequence:
    """يُهيِّئ عدّادَ السنة إن لم يكن — بلا زيادةٍ وبلا فاتورة.

    يُندى من توليد المسودّات: أوّلُ اعتمادٍ في السنة يجد صفَّ العدّاد قائماً فلا
    يدفع كلفةَ إنشاءٍ مفاجئة، والرقمُ يبدأ من `00001` بلا فجوة.
    """
    sequence, _created = FeeInvoiceSequence.objects.get_or_create(
        tenant=tenant, year=int(year), series=fee_invoice_series(year),
    )
    return sequence


def _locked(invoice) -> FeeInvoice:
    """إعادةُ قراءة الصفّ بقفلٍ — قرارُ الإلغاء يُبنى على حالته الآنية لا لقطة."""
    return (
        FeeInvoice.objects
        .select_for_update()
        .select_related("client", "tenant", "issued_by")
        .get(pk=invoice.pk)
    )


def _assert_issuer(invoice, actor) -> None:
    """الإلغاءُ والتصحيحُ إصدارٌ ثانٍ: صلاحيةُ كتابة زبائن المكتب.

    والرؤيةُ قبلها في الـview (`visible_invoices`)، ففاتورةُ زميلٍ **404** لا 403.
    """
    if actor is None or not user_has_perm(actor, invoice.tenant, services.OFFICE_CLIENTS_WRITE_KEY):
        raise PermissionDenied(
            "إلغاءُ فاتورة الأتعاب وتصحيحُها يحتاجان صلاحية كتابة زبائن المكتب.",
        )


def invoice_has_share(invoice) -> bool:
    """هل أُنشئ لهذه الفاتورة رابطٌ عامّ يوماً؟ — سؤالُ الإلغاء الوحيد.

    **كلُّ صفٍّ** لا الحيّ وحده: رابطٌ أُبطل بعد أن خرج إلى واتساب كان ورقةً بيد
    الزبون، وإعادةُ إحياء الإلغاء عليه تكذب على من يحملها.
    """
    from docshare.models import DOC_FEE_INVOICE, DocumentShare

    return DocumentShare.objects.filter(
        tenant_id=invoice.tenant_id,
        doc_type=DOC_FEE_INVOICE,
        doc_id=invoice.pk,
    ).exists()


def cancel_invoice(invoice, *, actor, reason="") -> FeeInvoice:
    """`issued → cancelled` **قبل الإرسال وحده**، والصفُّ يبقى في التاريخ."""
    _assert_issuer(invoice, actor)
    with transaction.atomic():
        invoice = _locked(invoice)
        if invoice.is_cancelled:
            raise ValidationError({"invoice": "الفاتورةُ ملغاةٌ من قبل."})
        if invoice_has_share(invoice):
            raise ValidationError({
                "invoice": (
                    "لا تُلغى فاتورةٌ أُنشئ رابطُها: الرابطُ قد يكون في يد الزبون. "
                    "أصدِر إشعاراً دائناً بدلاً من الإلغاء."
                ),
            })
        invoice.cancelled_at = timezone.now()
        invoice.cancelled_by = actor if getattr(actor, "pk", None) else None
        invoice.cancel_reason = (reason or "").strip()[:300]
        invoice.save(update_fields=["cancelled_at", "cancelled_by", "cancel_reason"])
    return invoice


def _assert_correctable(invoice) -> None:
    if invoice.kind != FEE_INVOICE_KIND_INVOICE:
        raise ValidationError({
            "invoice": "التصحيحُ لإشعارٍ دائنٍ أو تكميليةٍ بفاتورةٍ جديدة، لا بإشعارٍ منها.",
        })
    if invoice.is_cancelled:
        raise ValidationError({"invoice": "الفاتورةُ ملغاة — لا تصحيحَ لها."})


def _clean_correction_amount(invoice, amount) -> Decimal:
    """مبلغُ التصحيح: موجبٌ ولا يتجاوز إجماليَّ الأصل — برسالةٍ عربية.

    والحدُّ الأعلى **إجماليُ الأصل الشامل** لا صافيه: الإشعارُ الدائن يُلغي
    الفاتورةَ كلَّها بإجماليها، ولا يُصحَّح بما لم يُفوَّر قطّ.
    """
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        value = value.quantize(AMOUNT_QUANTUM)
    except (ArithmeticError, TypeError, ValueError):
        raise ValidationError({"amount": "مبلغٌ غير صالح."}) from None
    if value <= 0:
        raise ValidationError({"amount": "مبلغُ التصحيح أكبرُ من صفر."})
    if value > invoice.total:
        raise ValidationError({
            "amount": "مبلغُ التصحيح لا يتجاوز إجماليَّ الفاتورة الأصل.",
        })
    return value


def _issue_correction(
    invoice, *, actor, kind, amount, reason, series_kind, day=None,
) -> FeeInvoice:
    """يُصدر فاتورةَ تصحيحٍ على نظام الأصل نفسِه ونسبتِه المؤرَّخة."""
    _assert_issuer(invoice, actor)
    with transaction.atomic():
        # **القفلُ قبل فحص المبلغ**: الحدُّ الأعلى إجماليُ الأصل، وقراءتُه من
        # لقطةٍ خارج القفل تُجيز مبلغاً فوق الإجمالي في سباقِ تعديلٍ متزامن.
        invoice = _locked(invoice)
        _assert_correctable(invoice)
        amount = _clean_correction_amount(invoice, amount)
        tax_system = tax_system_for(invoice.tenant, invoice.client)
        rate = invoice.tax_percent
        tax_total = amount - _net_of(amount, rate=rate)
        issued_at = _issued_at(day)
        year = _local_day(issued_at).year
        series = (
            fee_invoice_credit_series(year)
            if series_kind == FEE_INVOICE_KIND_CREDIT_NOTE
            else fee_invoice_series(year)
        )
        return FeeInvoice.objects.create(
            tenant=invoice.tenant,
            client=invoice.client,
            #: **لا مسودّةَ لتصحيح**: مسودّةُ الشهر واحدة، والتصحيحُ مستندٌ على
            #: فاتورتها (`related_invoice`) لا فاتورةُ شهرٍ ثانية. والفرادةُ
            #: `OneToOne` على `draft` تبقى على الأصل — فلا مسودّةَ تنتج ورقتين.
            draft=None,
            kind=kind,
            related_invoice=invoice,
            number=_next_number(invoice.tenant, year=year, series=series),
            title=FEE_INVOICE_TITLES.get(tax_system, FEE_INVOICE_TITLES[TAX_SYSTEM_PS]),
            total=amount,
            tax_total=tax_total,
            issued_at=issued_at,
            issued_by=actor if getattr(actor, "pk", None) else None,
            cancel_reason=(reason or "").strip()[:300],
        )


def issue_credit_note(invoice, *, actor, amount, reason, day=None) -> FeeInvoice:
    """إشعارٌ دائنٌ على سلسلةٍ منفصلة — بسببٍ غيرِ فارغٍ ومبلغٍ ≤ الإجمالي."""
    if not (reason or "").strip():
        raise ValidationError({"reason": "سببُ الإشعار الدائن مطلوب."})
    return _issue_correction(
        invoice,
        actor=actor,
        kind=FEE_INVOICE_KIND_CREDIT_NOTE,
        amount=amount,
        reason=reason,
        series_kind=FEE_INVOICE_KIND_CREDIT_NOTE,
        day=day,
    )


def issue_supplementary(invoice, *, actor, amount, reason="", day=None) -> FeeInvoice:
    """فاتورةٌ تكميليةٌ للنقص — على السلسلة الرئيسية وعن الأصل نفسه."""
    return _issue_correction(
        invoice,
        actor=actor,
        kind=FEE_INVOICE_KIND_SUPPLEMENTARY,
        amount=amount,
        reason=reason,
        series_kind=FEE_INVOICE_KIND_SUPPLEMENTARY,
        day=day,
    )


# ── القراءة: الرؤيةُ والقناع ───────────────────────────────────────────────────
def visible_invoices(tenant, user):
    """فواتيرُ ما يراه العضو وحدها — والتفصيلُ والتصحيحُ يُقرآن من هنا أيضاً.

    ومسودّةُ زبونٍ لا يراه العضو **404** في الـview لا 403، كما في المسودّات.
    """
    return (
        FeeInvoice.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client", "draft", "issued_by", "cancelled_by", "related_invoice")
    )


def amounts_masked(tenant, user) -> bool:
    """قرارُ القناع مرّةً — كـ`fees.amounts_masked` نفسه لا نسخةً ثانية."""
    return fees.amounts_masked(tenant, user)


def _tax_system(invoice) -> str:
    """نظامُ الفاتورة الضريبيّ من زبونها — نداءٌ واحدٌ يتكرّر في البنّائين."""
    return tax_system_for(invoice.tenant, invoice.client)


def _client_payload(client) -> dict:
    return {"id": client.pk, "name": client.name}


def _user_payload(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.pk, "name": services.user_display_name(user)}


def _lines_payload(invoice) -> list[dict]:
    """سطورُ الورقة من بنود مسودّتها — لقطةُ التوليد لا حسابٌ جديد.

    والتصحيحُ (إشعارٌ دائنٌ أو تكميلية) لا مسودّةَ له: سطرُه واحدٌ بسببه ومبلغه —
    فالإشعارُ يحمل «كلَّ حقول الفاتورة مع قيمته وسببه» (م.4–م.12 من تعليمات
    25/2025) لا بنودَ الأصل نفسَها.
    """
    if invoice.draft_id is None:
        return [{
            "id": None,
            "label": invoice.cancel_reason or invoice.title,
            "quantity": LINE_QUANTITY,
            "unit": LINE_UNIT_IL if _tax_system(invoice) == TAX_SYSTEM_IL else LINE_UNIT_PS,
            "amount": invoice.net_total,
            "source": None,
            "source_label": "",
        }]
    return [
        {
            "id": line.pk,
            "label": line.label,
            "quantity": LINE_QUANTITY,
            "unit": LINE_UNIT_IL if _tax_system(invoice) == TAX_SYSTEM_IL else LINE_UNIT_PS,
            "amount": line.amount,
            "source": line.source,
            "source_label": FEE_LINE_SOURCE_LABELS.get(line.source, ""),
        }
        for line in invoice.draft.lines.all()
    ]


def invoice_row(invoice, *, masked) -> dict:
    """سطرُ فاتورةٍ كما يخرج — والمبلغُ `None` لمن لا يراه، والشكلُ ثابتٌ دائماً."""
    data = {
        "id": invoice.pk,
        "number": invoice.number,
        "kind": invoice.kind,
        "kind_label": FEE_INVOICE_KIND_LABELS.get(invoice.kind, ""),
        "title": invoice.title,
        "client": _client_payload(invoice.client),
        "draft": invoice.draft_id,
        "related_invoice": invoice.related_invoice_id,
        "total": invoice.total,
        "tax_total": invoice.tax_total,
        "external_number": invoice.external_number,
        "issued_at": invoice.issued_at.isoformat(),
        "issued_by": _user_payload(invoice.issued_by),
        "state": invoice.state,
        "is_tax_invoice": invoice.is_tax_invoice,
        "cancelled_at": (
            None if invoice.cancelled_at is None else invoice.cancelled_at.isoformat()
        ),
        "cancelled_by": _user_payload(invoice.cancelled_by),
        "cancel_reason": invoice.cancel_reason,
        "has_link": invoice_has_share(invoice),
    }
    return services.mask_amounts(data, INVOICE_AMOUNT_KEYS) if masked else data


def invoice_detail(invoice, *, masked) -> dict:
    """تفصيلُ فاتورة: صفُّها وبحورُها ورابطُها الحيّ إن وُجد."""
    data = invoice_row(invoice, masked=masked)
    lines = _lines_payload(invoice)
    data["lines"] = (
        [_masked_line(line) for line in lines] if masked else lines
    )
    data["net_total"] = None if masked else invoice.net_total
    data["tax_percent"] = None if masked else invoice.tax_percent
    data["url"] = live_invoice_url(invoice) or ""
    return data


def _masked_line(line) -> dict:
    """سطرٌ مقنَّع — المفتاحُ يبقى والمبلغُ يصير `None` كسائر صفوف الموديول."""
    return services.mask_amounts(line, services.FEE_AMOUNT_KEYS)


def invoices_payload(tenant, *, user, client=None, kind=None, state=None) -> list[dict]:
    """قائمةُ الفواتير — الفلاترُ تُطبَّق في الاستعلام لا في بايثون.

    `state` قيمتاه `issued`/`cancelled` وحدهما؛ وقيمةٌ غيرُهما تُهمَل (القائمةُ
    كاملةً) لأن الفلترةَ عرضٌ لا حارس: لا خطأَ في طلبِ قائمةٍ بفلترٍ مطبوعٍ خطأً.
    """
    masked = amounts_masked(tenant, user)
    queryset = visible_invoices(tenant, user)
    if client is not None:
        queryset = queryset.filter(client_id=client)
    if kind in FEE_INVOICE_KIND_LABELS:
        queryset = queryset.filter(kind=kind)
    if state == "cancelled":
        queryset = queryset.filter(cancelled_at__isnull=False)
    elif state == "issued":
        queryset = queryset.filter(cancelled_at__isnull=True)
    return [
        invoice_row(invoice, masked=masked)
        for invoice in queryset.order_by("-issued_at", "-id")
    ]


# ── الرابطُ العامّ: ورقةٌ واحدةٌ لكل فاتورة ───────────────────────────────────
def live_invoice_url(invoice) -> str | None:
    """الرابطُ الحيّ القائم إن وُجد — **قراءةٌ فقط، لا إنشاءَ من مسار قراءة**."""
    from docshare import services as docshare_services
    from docshare.models import DOC_FEE_INVOICE, DocumentShare

    share = (
        DocumentShare.objects
        .filter(
            tenant_id=invoice.tenant_id,
            doc_type=DOC_FEE_INVOICE,
            doc_id=invoice.pk,
            is_public=False,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at", "-id")
        .first()
    )
    return None if share is None else docshare_services.public_url(share)


def invoice_urls(tenant, invoice_ids, *, user=None) -> dict[int, str]:
    """رابطُ ورقة الفاتورة لكلّ فاتورةٍ في المجموعة — نمطُ `payment_notice_urls`.

    الرابطُ يُنشَأ أوّلَ مرّةٍ **في مسار القراءة** («جاهز للإرسال») عن قصد: نصُّ
    الرسالة يجب أن يكون نهائياً قبل الإرسال، ورابطٌ يُخلَق بعده لا يكون في
    الورقة التي بيد الزبون. والتكرارُ آمن — الحيّ نفسه يُعاد (`dedupe`).
    """
    from docshare import services as docshare_services
    from docshare.models import DOC_FEE_INVOICE, DocumentShare

    wanted = {invoice_id for invoice_id in invoice_ids if invoice_id is not None}
    if not wanted:
        return {}
    live = (
        DocumentShare.objects
        .filter(
            tenant=tenant,
            doc_type=DOC_FEE_INVOICE,
            doc_id__in=list(wanted),
            is_public=False,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at", "-id")
        .values_list("doc_id", "token")
    )
    urls: dict[int, str] = {}
    for doc_id, token in live:
        urls.setdefault(doc_id, docshare_services.public_url_for_token(token))
    for invoice_id in sorted(wanted - set(urls)):
        try:
            share = docshare_services.create_share(
                tenant, DOC_FEE_INVOICE, invoice_id, user=user,
            )
        except docshare_services.ShareNotFound:
            # الفاتورةُ تغيّرت بين القراءتين: النصُّ يمضي بلا رابطٍ ولا يسقط الطلب.
            continue
        urls[invoice_id] = docshare_services.public_url(share)
    return urls


# ── الورقة: حقولُها بترتيبها ──────────────────────────────────────────────────
def _period_of(invoice) -> tuple[date, date]:
    """فترةُ الفوترة التي تخصّ الفاتورة — شهرُ مسودّتها، أو شهرُ إصدارها لتصحيح."""
    from accounting_office import deadlines

    if invoice.draft_id is None:
        start = _local_day(invoice.issued_at).replace(day=1)
    else:
        start = date(invoice.draft.year, invoice.draft.month, 1)
    return start, deadlines.month_start_after(start, 1) - timedelta(days=1)


def sheet_lines(invoice) -> list[dict]:
    """سطورُ الورقة بأعمدة م4/1: النوعُ والكميةُ والوحدةُ والسعرُ ونسبةُ الضريبة."""
    rate = invoice.tax_percent
    unit = LINE_UNIT_IL if _tax_system(invoice) == TAX_SYSTEM_IL else LINE_UNIT_PS
    return [
        {
            "label": line["label"],
            "quantity": LINE_QUANTITY,
            "unit": unit,
            "unit_price": line["amount"],
            "tax_percent": rate,
            "line_total": line["amount"],
        }
        for line in _lines_payload(invoice)
    ]


#: تسمياتٌ لكل نظام — **نصٌّ واحدٌ لكل مفهوم**، فيقرؤه القالبُ ولا يحمل حرفاً.
LABELS_PS: dict[str, str] = {
    "registration": "رقم المشتغل المرخّص",
    "trade_name": "الاسم التجاري",
    "address": "العنوان",
    "phone": "هاتف العمل",
    "number": "رقم الفاتورة",
    "issued_on": "تاريخ الإصدار",
    "client": "الزبون",
    "client_file": "رقم الملف الضريبي",
    "lines_head": "البيان",
    "quantity": "الكمية",
    "unit": "الوحدة",
    "unit_price": "سعر الوحدة",
    "tax_percent": "الضريبة %",
    "line_total": "الإجمالي",
    #: لا عنوانَ لكتلة المبالغ في فلسطين: «الإجمالي قبل الضريبة» هو العنصرُ
    #: الخامس نفسه، وعنوانٌ ثانٍ فوقه تكرارُ رقمٍ باسمين.
    "consideration": "",
    "net": "الإجمالي قبل الضريبة",
    "tax": "قيمة الضريبة",
    "gross": "الإجمالي شاملاً الضريبة",
    "signature": "توقيع المُصدِر",
    "original": "الأصل",
    "copy": "نسخة",
    "external_number": "رقم الفاتورة الرسمية",
    "kind_credit_note": "إشعار دائن",
    "kind_supplementary": "فاتورة تكميلية",
    "related": "الفاتورة الأصل",
    "cancelled": "ملغاة",
    "cancel_reason": "سبب الإلغاء",
}

LABELS_IL: dict[str, str] = {
    "registration": 'מספר עוסק',
    "trade_name": "שם העסק",
    "address": "כתובת",
    "phone": "טלפון",
    "number": "מספר סידורי",
    "issued_on": "תאריך הוצאה",
    "client": "שם המקבל",
    "client_file": "מספר תיק ניכויים",
    "lines_head": "תיאור הפעולה",
    "quantity": "כמות",
    "unit": "יחידה",
    "unit_price": "מחיר יחידה",
    "tax_percent": 'מע"מ %',
    "line_total": "סכום",
    #: العنصرُ السادس في `§9א` («התמורה») — عنوانٌ على كتلة المبالغ. وفي
    #: فلسطين لا عنوانَ زائداً: العنصرُ الخامس هو «الإجمالي قبل الضريبة» نفسه.
    "consideration": "התמורה",
    "net": 'סכום לפני מע"מ',
    "tax": 'מע"מ',
    "gross": 'סה"כ לתשלום',
    "signature": "חתימת המוציא",
    "original": "",
    "copy": "",
    "external_number": "מספר חשבונית חיצונית",
    "kind_credit_note": "הודעת זיכוי",
    "kind_supplementary": "חשבונית משלימה",
    "related": "חשבונית מקור",
    "cancelled": "מבוטלת",
    "cancel_reason": "סיבת הביטול",
}


def labels_for(tax_system: str) -> dict[str, str]:
    return LABELS_IL if tax_system == TAX_SYSTEM_IL else LABELS_PS


def sheet_context(invoice) -> dict:
    """سياقُ الورقة — **كلُّ ما يُطبع يُمرَّر صريحاً**، والقالبُ لا يحسب مالاً.

    والنسختان في فلسطين وحدها: م4/5 يطلب «نسختين على الأقل، الأصل ثم نسخة»،
    وإسرائيل لا تشترط نسختين لـ`חשבון עסקה`.
    """
    tax_system = tax_system_for(invoice.tenant, invoice.client)
    labels = labels_for(tax_system)
    show_tax = bool(invoice.tax_total)
    #: نسختان في فلسطين («الأصل» ثم «نسخة» — م4/5)، ونسخةٌ واحدةٌ في إسرائيل
    #: (لا تشترط `חשבון עסקה` نسختين). والقائمةُ دائماً غيرُ فارغةٍ فالقسمُ واحد.
    copies = (
        [labels["original"], labels["copy"]]
        if tax_system == TAX_SYSTEM_PS else [""]
    )
    return {
        "title": invoice.title,
        "tax_system": tax_system,
        "not_tax_line": not_tax_line(tax_system),
        "labels": labels,
        "company": company_card(invoice.tenant),
        "client_name": invoice.client.name,
        "client_tax_file": invoice.client.tax_file_number or "",
        "number": invoice.number,
        "external_number": invoice.external_number,
        "date": _local_day(invoice.issued_at),
        "kind_label": (
            labels["kind_credit_note"]
            if invoice.kind == FEE_INVOICE_KIND_CREDIT_NOTE
            else labels["kind_supplementary"]
            if invoice.kind == FEE_INVOICE_KIND_SUPPLEMENTARY
            else invoice.title
        ),
        "related_number": (
            None if invoice.related_invoice_id is None
            else invoice.related_invoice.number
        ),
        "lines": sheet_lines(invoice),
        "net": invoice.net_total,
        "tax_total": invoice.tax_total,
        "total": invoice.total,
        "tax_percent": invoice.tax_percent,
        "show_tax": show_tax,
        "copies": copies,
        "cancelled": invoice.is_cancelled,
        "cancel_reason": invoice.cancel_reason,
    }


def render_sheet(invoice) -> str:
    """ورقةُ الفاتورة HTML — يستدعيها نوعُ مستند `fee_invoice` في `docshare`."""
    from django.template.loader import render_to_string

    return render_to_string("docshare/fee_invoice.html", sheet_context(invoice))


# ── حمولةُ العقد العامّ ───────────────────────────────────────────────────────
def share_payload(invoice) -> dict:
    """حمولةُ `docshare` العامة — من `payload()` و`line_row()` وحدَهما.

    `show_lines=True` و`show_line_prices=True`: الفاتورةُ أسطرٌ وأسعارٌ — بخلاف
    سند القبض الذي يُخفي أعمدة السعر لأنها بلا معنى عليه.
    """
    from docshare.documents._contract import (
        TONE_DANGER,
        TONE_OK,
        VALUE_DATE,
        line_row,
        meta,
        payload,
        total as total_row,
    )

    labels = labels_for(_tax_system(invoice))
    lines = [
        line_row(name=line["label"], unit=line["unit"], quantity=line["quantity"],
                 unit_price=line["unit_price"], tax_percent=line["tax_percent"],
                 line_total=line["line_total"])
        for line in sheet_lines(invoice)
    ]
    totals = [total_row(labels["net"], invoice.net_total)]
    if invoice.tax_total:
        totals.append(total_row(labels["tax"], invoice.tax_total))
    totals.append(total_row(labels["gross"], invoice.total, strong=True))
    return payload(
        kind="fee_invoice",
        title=invoice.title,
        number=invoice.number,
        date=_local_day(invoice.issued_at),
        status_label=(
            labels["cancelled"] if invoice.is_cancelled
            else FEE_INVOICE_KIND_LABELS.get(invoice.kind, "")
        ),
        status_tone=TONE_DANGER if invoice.is_cancelled else TONE_OK,
        party_title="الزبون",
        party=invoice.client.name,
        currency=None,
        meta_rows=[
            meta(labels["issued_on"], _local_day(invoice.issued_at), VALUE_DATE),
            meta(labels["client_file"], invoice.client.tax_file_number),
        ],
        lines=lines,
        totals_rows=totals,
        grand_total=invoice.total,
        show_lines=True,
        show_line_prices=True,
    )


# ── «جاهز للإرسال»: رسالةُ الفاتورة ──────────────────────────────────────────
def _reminder_invoice(invoice, *, due) -> dict:
    """بندُ الفاتورة كما يخرج في الرسالة — مبالغُه نصوصٌ مصيغةٌ لا `Decimal`.

    والمبلغُ مكشوفٌ كما في نصّ الرسالة نفسه: الرسالةُ إلى الزبون عن مبلغٍ عليه،
    وقنعُه عن الموظّف كان يُرسل «—» إلى الزبون بدل مبلغه (قاعدةُ #281).
    """
    return {
        "id": invoice.pk,
        "number": invoice.number,
        "title": invoice.title,
        "kind": invoice.kind,
        "total": f"{invoice.total:.2f}",
        "tax_total": f"{invoice.tax_total:.2f}",
        "issued_on": _local_day(invoice.issued_at).isoformat(),
        "due_on": due.isoformat(),
        "url": "",
    }


def invoice_reminder_candidates(
    tenant, clients, *, day, settings_by_client, contacts, by_pair,
    postponed_pairs, reminder_type=None,
) -> list:
    """بندُ «اللي عليه» لكلّ فاتورةٍ صادرةٍ لم تُلغَ: مبلغُها واستحقاقُها بعد 7 أيام.

    **النوعُ `balance` القائم** لا نوعاً خامساً: «اللي عليه» هو بالضبط ما تقوله
    الفاتورة، وقالبُه ونصُّه في السجلّ منذ #280 بلا مولّدٍ — وهذا مولّدُه الأوّل.
    والرسالةُ واحدةٌ لكل فاتورة (`INVOICE_REMINDER_MAX`) ثم يسقط بندُها.

    ولا فاتورةَ مُلغاةً ولا إشعاراً دائناً (إشعارٌ دائنٌ يُنقص ولا يُطلب)، ولا
    استحقاقَ قبل `issued_at + 7` — والتاريخُ من الإصدار لا من اليوم.
    """
    if reminder_type not in (None, REMINDER_BALANCE):
        return []
    client_ids = [client.pk for client in clients]
    if not client_ids:
        return []
    rows = (
        FeeInvoice.objects
        .filter(
            tenant=tenant,
            client_id__in=client_ids,
            kind__in=(FEE_INVOICE_KIND_INVOICE, FEE_INVOICE_KIND_SUPPLEMENTARY),
            cancelled_at__isnull=True,
        )
        .select_related("client", "draft")
        .order_by("issued_at", "id")
    )
    candidates = []
    for invoice in rows:
        due = _local_day(invoice.issued_at) + timedelta(days=INVOICE_DUE_DAYS)
        period_start, period_end = _period_of(invoice)
        pairs = by_pair.get((invoice.client_id, REMINDER_BALANCE, period_start, period_end), [])
        count = sum(
            1 for row in pairs if row["kind"] in services.REMINDER_COUNTED_KINDS
        )
        resolved = settings_by_client.get(invoice.client_id, {})
        candidates.append(services.ReminderCandidate(
            client=invoice.client,
            reminder_type=REMINDER_BALANCE,
            period_start=period_start,
            period_end=period_end,
            missing=(),
            missing_codes=(),
            count=count,
            maximum=INVOICE_REMINDER_MAX,
            interval_days=INVOICE_DUE_DAYS,
            next_due=due,
            contact=contacts.get((invoice.client_id, REMINDER_BALANCE)),
            tax_system=resolved.get(services.TAX_SYSTEM_KEY),
            due=day >= due,
            exhausted=count >= INVOICE_REMINDER_MAX,
            postponed=(invoice.client_id, REMINDER_BALANCE) in postponed_pairs,
            render_due=due,
            amount=invoice.total,
            invoice=_reminder_invoice(invoice, due=due),
        ))
    return candidates


def attach_invoice_links(tenant, candidates, *, user=None):
    """يُركّب رابطَ الورقة على بنود الفواتير — **بعد الحواجز كلّها**.

    والرابطُ لمن يملك مشاركةَ النوع وحده (`office.clients.write`): يُنشَأ في مسار
    قراءة، فلا يجوز أن يمنح عضوَ قراءةٍ صفَّ مشاركةٍ حيّاً. ومن لا يملكها يقرأ
    الفاتورةَ بلا رابط (والنصُّ يمضي بالمبلغ والاستحقاق).
    """
    from dataclasses import replace

    if user is None or not user_has_perm(
        user, tenant, services.OFFICE_CLIENTS_WRITE_KEY,
    ):
        return candidates
    wanted = [
        candidate.invoice["id"]
        for candidate in candidates
        if candidate.invoice is not None and not candidate.invoice.get("url")
    ]
    if not wanted:
        return candidates
    urls = invoice_urls(tenant, wanted, user=user)
    if not urls:
        return candidates
    attached = list(candidates)
    for index, candidate in enumerate(attached):
        if candidate.invoice is None:
            continue
        url = urls.get(candidate.invoice["id"])
        if url:
            attached[index] = replace(
                candidate,
                invoice={**candidate.invoice, "url": url},
            )
    return attached


def invoice_item(invoice) -> dict | None:
    """بندُ الفاتورة في الصفحة — `None` لبندٍ ليس فاتورة (كأيّ نوعٍ آخر)."""
    return None if invoice is None else dict(invoice)


def invoice_text(invoice) -> str:
    """نصُّ الفاتورة كما يدخل `body` الرسالة — بلا رمزٍ جديدٍ في القوالب."""
    if invoice is None:
        return ""
    parts = [f"{invoice['title']} {invoice['number']}"]
    parts.append(
        f"المبلغ: {invoice['total']} — الاستحقاق: {invoice['due_on']}"
    )
    if invoice.get("url"):
        parts.append(f"الرابط: {invoice['url']}")
    return "\n".join(parts)
