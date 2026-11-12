"""أتعابُ مكتب المحاسبة — الاشتراكُ والمسودّاتُ والاعتماد (#282، الجزء أ١).

**ما هنا حسابُ الأتعاب لا مستندُها:** `FeeDraft` مسودّةُ شهرٍ تُحسب من ثلاثة مصادر
وتُعتمد، وفاتورةُ الأتعاب الورقية (الترقيمُ والحقولُ القانونية والإشعارُ الدائن
ورابطُ PDF وشاشةُ «المسودّات») هي **أ٢** — والمعتمدةُ تُنتجها هناك، فلا يُدمج
المفهومان: مسودّةٌ تُحسب، ومستندٌ يُرقَّم ويُطبع.

**ثلاثُ قواعدَ لا رابعة:**
1. **السعرُ بتاريخ سريان** (`subscription_on`): أكبرُ `starts_on` لا يتجاوز آخرَ
   الشهر المطلوب. تغييرُ السعر **يضيف صفّاً** ولا يعدّل ما قبله، فتبقى مسودّةُ
   الشهر الماضي بسعرها — كقاعدة `ClientServiceFrequency` نفسها.
2. **التناسبُ بعدد أيام الشهر الفعليّ — لا بثلاثين**: من بدأ في 16/نيسان
   (ثلاثون يوماً) يدفع نصفَ الشهر تماماً، ومن بدأ في 16/آذار (31 يوماً) يدفع 16/31.
   **والتناسبُ على حدود الاشتراك لا حدود الصفّ**: تغييرُ سعرٍ في منتصف الشهر يحكم
   الشهرَ كلَّه بسعره (الصفُّ السابق يغطّي أوّله فلا تُترك أيامٌ بلا فاتورة)،
   و`ended_on` يُنسب في آخر الشهر بعدد أيامه.
3. **التوليدُ مرّةً في الشهر** بفرادة `(زبون، سنة، شهر)` في القاعدة: مرّتان في
   اليوم نفسه لا تضيفان صفّاً، وما اعتُمد أو أُلغي لا يُلمَس. **والإضافاتُ لا
   تضيع**: لكلٍّ `billed_draft` يُربط بمسودّتها في المعاملة نفسها، فما سُجِّل بعد
   توليد مسودّته يلحق أوّلَ مسودّةٍ تالية، والإلغاءُ يُعيده حرّاً.

**ولا حذف**: `draft → approved` أو `draft → cancelled` قبل الاعتماد، والأصلُ يبقى
أثراً. والاعتمادُ **دورٌ لا مفتاح**: صاحبُ المكتب (`manager`) ومديرُ المكتب
(`office_manager`) وحدهما — والمحاسبُ يكتب الزبون ولا يعتمد أتعابه.

**وكلُّ مبلغٍ يمرّ بالقناع**: `amounts_masked` قرارٌ يُحسب مرّةً، و`subscription_row`
/`draft_row`/`extra_row`/`service_price_row` تقنّع المال — ومن لا يملك
`office.amounts.view` لا يقرؤه ولا يكتبه (الـview يردّ 403 على كتابة مبلغ).
"""
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounting_office import deadlines, services, settings_registry
from accounting_office.models import (
    FEE_CADENCE_CHOICES,
    FEE_CADENCE_LABELS,
    FEE_CADENCE_MONTHLY,
    FEE_DRAFT_STATUS_APPROVED,
    FEE_DRAFT_STATUS_CANCELLED,
    FEE_DRAFT_STATUS_DRAFT,
    FEE_DRAFT_STATUS_LABELS,
    FEE_EXTRA_DESTINATION_CHOICES,
    FEE_EXTRA_DESTINATION_LABELS,
    FEE_EXTRA_DESTINATION_NEXT_MONTH,
    FEE_LINE_SOURCE_EXTRA,
    FEE_LINE_SOURCE_LABELS,
    FEE_LINE_SOURCE_SERVICE,
    FEE_LINE_SOURCE_SUBSCRIPTION,
    OFFICE_ALERT_KIND_FEE_DRAFT_PENDING,
    ClientServicePrice,
    FeeDraft,
    FeeDraftLine,
    FeeExtraService,
    FeeSubscription,
    OfficeAlert,
    OfficeClient,
    assert_fee_amount,
    fee_draft_alert_ref,
)
from core.access import MANAGER_ROLE, OFFICE_MANAGER_ROLE, user_tenant_role
from tenants.models import Currency, UserCompanyMembership

FEE_METHOD_KEY = services.FEE_METHOD_KEY

#: مَن يعتمد مسودّات الأتعاب — **الدورُ لا المفتاح**: مديرُ المكتب يملك مفاتيح
#: المكتب كلَّها، والمحاسبُ يكتب الزبون ولا يعتمد مالَه.
FEE_APPROVER_ROLES: tuple[str, ...] = (MANAGER_ROLE, OFFICE_MANAGER_ROLE)

#: كم يوماً تنتظر المسودّةُ قبل أن تُنبَّه: ثلاثةُ أيامٍ تعطي الموظفَ وقتاً
#: لمراجعة الشهر، ولا تُترك المسودّةُ غيرَ المعتمدة تتراكم بلا تنبيه.
PENDING_ALERT_AFTER_DAYS = 3

AMOUNT_QUANTUM = Decimal("0.01")

#: نصُّ سطر الاشتراك — بلا اسم شهرٍ فيه: الشهرُ في `period_label` على المسودّة،
#: ووجودُه هنا مرّتين يجعل الصفّين يفترقان عند أول تغيير صيغة.
SUBSCRIPTION_LINE_LABEL = "الاشتراك الشهري"
PRORATED_SUFFIX = " — تناسب أيام"


# ── القناع والمبالغ ─────────────────────────────────────────────────────────
def amounts_masked(tenant, user) -> bool:
    """قرارُ القناع **مرّةً واحدة** — تُمرَّر النتيجةُ إلى بانيات الصفوف.

    `can_see_amounts` تقرأ العضويةَ وتجاوزَي الدور والعضو، فسؤالُها لكل صفٍّ في
    قائمةٍ يجعل قراءةَ قائمةٍ عشراتِ الاستعلامات. و`user=None` وحده نداءٌ داخليٌّ
    بلا قناع — كـ`client_books.amounts_masked` و`services.tax_card_payload`.
    """
    return user is not None and not services.can_see_amounts(tenant, user)


def _clean_amount(value, *, field="amount") -> Decimal:
    """مبلغُ مدخلات: عشريٌّ غيرُ سالبٍ بخانتين — أو 400 برسالته.

    القاعدةُ نفسُها في `models.assert_fee_amount` (حارسُ الحفظ)، فلا نسختان من
    «المبلغ بخانتين» تفترقان بين الـAPI والـORM.
    """
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({field: "مبلغٌ غير صالح."}) from None
    assert_fee_amount(amount, field=field)
    return amount.quantize(AMOUNT_QUANTUM)


def _resolve_currency(currency_id):
    """عملةُ الاشتراك — الافتراضُ عملةُ المنصّة الأساسية، والمعرّفُ الغريب 400."""
    if currency_id in (None, ""):
        return Currency.objects.filter(IsBaseCurrency=True).first()
    currency = Currency.objects.filter(pk=currency_id).first()
    if currency is None:
        raise ValidationError({"currency": "عملة غير معروفة."})
    return currency


# ── حسابُ الشهر: السعرُ الساري والتناسب ─────────────────────────────────────
def _month_bounds(day) -> tuple[date, date]:
    """أوّلُ الشهر الذي فيه `day` وآخرُه — تقويمٌ فعليّ لا ثلاثون يوماً."""
    start = day.replace(day=1)
    return start, deadlines.month_start_after(start, 1) - timedelta(days=1)


def _generated_at(day) -> datetime:
    """لحظةُ التوليد ليومٍ صريح — **منتصفُ نهاره** بتوقيت العمل لا ساعةَ النظام.

    `refresh_office` تُمرَّر لها `day` صريحةً ولا ساعةَ في الموديول، فتنبيهُ «بعد
    ثلاثة أيام» يُقاس على تاريخ التوليد نفسه. ووقتُ `auto_now_add` كان يقرأ ساعةَ
    الخادم فيكذب على تشغيلٍ ليومٍ ماضٍ (والاختبارُ يراه صفراً أبداً). والمنتصفُ
    نهاراً لا منتصفُ الليل لأن منتصفَ الليل قد لا يوجد في يوم تغيير الساعة.
    """
    return timezone.make_aware(datetime.combine(day, time(hour=12)))


def _subscription_by_start(rows, month_end):
    """الصفُّ الساري في شهرٍ ينتهي بـ`month_end`: أكبر `starts_on` لا يتجاوزه.

    وهي قاعدةُ `services.frequency_on` نفسُها (أكبر تاريخٍ لا يتجاوز اليوم)،
    والفرقُ أن المقارنةَ هنا بآخر الشهر: سعرٌ يسري في 15/نيسان يحكم نيسان كلَّه.
    """
    eligible = [row for row in rows if row.starts_on <= month_end]
    return max(eligible, key=lambda row: (row.starts_on, row.pk), default=None)


def subscription_on(tenant, client, *, day):
    """اشتراكُ الزبون الساري في شهر `day` — `None` إن لم يكن له اشتراكٌ بعد."""
    _month_start, month_end = _month_bounds(day)
    rows = FeeSubscription.objects.filter(tenant=tenant, client=client)
    return _subscription_by_start(rows, month_end)


def _paused_on(subscription, day) -> bool:
    """هل يقع `day` داخل مدى إيقاف الفوترة؟ (نهايتُه الغائبة = مفتوحٌ)."""
    if subscription.paused_from is None or subscription.paused_from > day:
        return False
    return subscription.paused_to is None or day <= subscription.paused_to


def _paused_month(rows, month_start, month_end) -> bool:
    """هل الشهرُ داخل إيقاف الفوترة؟ — الصفُّ الساري فيه موقوفٌ في أوّله.

    **وهذا حكمُ الشهر لا حكمُ السطر**: شهرٌ موقوفٌ **لا مسودّةَ له أصلاً**، ولا
    تُسقَط إضافاتُه — تبقى بلا `billed_draft` فيلتقطها أوّلُ توليدٍ بعد انتهاء
    الإيقاف (قاعدةُ «الإضافةُ تُربط بمسودّتها»). ولو اقتصر المنعُ على سطر
    الاشتراك لخرجت مسودّةٌ فيها الإضافاتُ وحدها.
    """
    subscription = _subscription_by_start(rows, month_end)
    return subscription is not None and _paused_on(subscription, month_start)


def _covered_before(rows, subscription) -> bool:
    """هل يغطّي صفٌّ آخر اليومَ السابق لبداية هذا الصف؟

    **يُسأل عنه قبل التناسب من البداية**: أوّلُ اشتراكٍ (أو عودةٌ بعد إنهاء)
    لا صفَّ قبله يغطّي ما قبله فيُتناسب من `starts_on`، وأمّا تغييرُ سعرٍ في
    منتصف الشهر فالصفُّ السابق يغطّي أيامَه الأولى — فيُحسب الشهرُ كلُّه بسعر
    الصفّ الساري، ولا تضيع أيامٌ بين الصفّين ولا تُحسب بغير سعرها.

    **والتغطيةُ يحكم بها الصفُّ الساري في اليوم السابق وحده** (قاعدةُ
    `_subscription_by_start` نفسُها) لا أيُّ صفٍّ يغطّيه بحدّه: الصفوفُ إلحاقيّةٌ لا
    تُعدَّل، فالإنهاءُ **صفٌّ** `starts_on = ended_on` ويبقى الصفُّ الأصليُّ
    `ended_on = None` إلى الأبد — فلو عُدّ كلُّ صفٍّ بحدّه لبقيت كلُّ عودةٍ
    بعد إنهاءٍ «مغطّاةً» بصفّه الأوّل وفُوتر شهرُها كاملاً.
    """
    day = subscription.starts_on - timedelta(days=1)
    previous = _subscription_by_start(
        [row for row in rows if row.pk != subscription.pk], day,
    )
    return previous is not None and (
        previous.ended_on is None or previous.ended_on >= day
    )


def _prorated(amount, *, active_days, month_days) -> Decimal:
    """نصيبُ الأيام الفعّالة من مبلغ الشهر — مُقرَّبٌ إلى أغورةٍ واحدة."""
    return (amount * active_days / month_days).quantize(
        AMOUNT_QUANTUM, rounding=ROUND_HALF_UP,
    )


def _subscription_lines(rows, month_start, month_end) -> list[tuple[str, Decimal, str]]:
    """سطرُ الاشتراك لشهرٍ: مبلغُه أو نصيبُ أيامه، أو لا سطر.

    **ولا سطرَ لاشتراكٍ انتهى قبل الشهر. وشهرُ الإيقاف يمنعه النداءُ الأعلى**
    (`_paused_month`) لأن الحكمَ على المسودّة كلِّها لا على سطر الاشتراك وحده —
    فلا نسخةَ ثانية من القاعدة هنا.
    **والتناسبُ على حدود الاشتراك لا على حدود الصفّ**: بدايةُ الصفّ تُنسب إن لم
    يغطِّ صفٌّ آخر اليومَ السابق (`_covered_before`)، وانتهاؤه `ended_on` يُنسب
    في آخر الشهر بعدد أيامه كالبداية: المبلغُ ثمنُ مدة، ومدةٌ أقصرُ بنصفها
    ثمنُها نصفُها.
    """
    subscription = _subscription_by_start(rows, month_end)
    if subscription is None:
        return []
    if subscription.cadence not in dict(FEE_CADENCE_CHOICES):
        return []
    if subscription.ended_on is not None and subscription.ended_on < month_start:
        return []
    start = month_start
    if not _covered_before(rows, subscription):
        start = max(month_start, subscription.starts_on)
    end = month_end if subscription.ended_on is None else min(month_end, subscription.ended_on)
    if start > end:
        return []
    month_days = (month_end - month_start).days + 1
    active_days = (end - start).days + 1
    if active_days >= month_days:
        return [(SUBSCRIPTION_LINE_LABEL, subscription.amount, FEE_LINE_SOURCE_SUBSCRIPTION)]
    return [(
        SUBSCRIPTION_LINE_LABEL + PRORATED_SUFFIX,
        _prorated(subscription.amount, active_days=active_days, month_days=month_days),
        FEE_LINE_SOURCE_SUBSCRIPTION,
    )]


def _service_lines(prices, month_start, month_end) -> list[tuple[str, Decimal, str]]:
    """سطورُ «سعرٌ لكل خدمة»: خدمةٌ **استحقّتْ فترةً تبدأ** في الشهر.

    الفتراتُ من محرّك المواعيد الواحد (`services.client_service_periods`) لا من
    حسابٍ ثانٍ هنا، والبدايةُ الفعّالة هي `max(بداية الفترة, بداية الخدمة, بداية
    مسؤولية المكتب)` — فخدمةٌ بدأت في 16/آذار وحزمتُها التقويمية تبدأ 1/آذار
    تُحسب في آذار (بدايتُها الفعّالة 16/آذار) ولو كان الصفُّ محاذىً للتقويم.
    """
    lines: list[tuple[str, Decimal, str]] = []
    for price in prices:
        client_service = price.client_service
        if client_service.starts_on > month_end:
            continue
        if client_service.ends_on is not None and client_service.ends_on < month_start:
            continue
        periods = services.client_service_periods(
            client_service,
            floor=month_start,
            end=month_end,
            frequencies=list(client_service.frequencies.all()),
        )
        effective_starts = {
            max(period_start, client_service.starts_on, client_service.responsible_from)
            for period_start, _period_end, _frequency in periods
        }
        if not any(month_start <= start <= month_end for start in effective_starts):
            continue
        lines.append((
            client_service.service.name,
            price.amount,
            FEE_LINE_SOURCE_SERVICE,
        ))
    return lines


def _extra_lines(extras) -> list[tuple[str, Decimal, str]]:
    """سطورُ الخدمات الإضافية التي نُفِّذت **قبل هذا الشهر** ولم تُفوتر بعد.

    «الشهر القادم» تُقاس من تاريخ التنفيذ: إضافةٌ نُفِّذت في آذار تدخل مسودّةَ
    نيسان — أو أوّلَ مسودّةٍ بعده إن كان قد سُجِّلت بعد توليدها. والربطُ
    (`FeeExtraService.billed_draft`) هو ما يمنع الحسابَ مرّتين. و«فاتورة لحالها»
    لا تدخل مسودّةً أصلاً — القرارُ في `draft` على الصفّ.
    """
    return [
        (extra.service_name, extra.amount, FEE_LINE_SOURCE_EXTRA)
        for extra in extras
    ]


def _group_by_client(rows) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row.client_id, []).append(row)
    return grouped


def generate_fee_drafts(tenant, *, day) -> dict:
    """يولّد مسودّات **دورة شهر `day`** ويُرجع ما أنشأه هذا النداء وحده.

    - **مسودّةٌ لكل زبونٍ نشط**، بطريقةِ أتعابه: اشتراكُه الساري (منسوباً على
      حدود الاشتراك لا حدود الصفّ)، أو خدماتُه التي استحقّت فتراتُها، **زائدَ**
      إضافاتِ ما قبل الشهر التي لم تُفوتر بعد.
    - **ولا مسودّة** لزبونٍ منتهٍ، ولا لشهرٍ داخل إيقاف الفوترة (**في طريقة
      «اشتراك» وحدها**: الإيقافُ حقلٌ على صفّ الاشتراك، فزبونُ `per_service`
      الموقوفُ قد تُولَّد له مسودّةُ إضافاتٍ وحدها — سلوكٌ مقصود)، ولا لاشتراكٍ
      انتهى قبل الشهر، ولا لزبونٍ بلا سطرٍ واحد.
    - **والتوليدُ مرّةً في الشهر**: مسودّاتُ الشهر تُقرأ `client_id` مرّةً واحدةً
      ويُتخطّى أصحابُها قبل حساب السطور — فلا `savepoint` ولا استعلامَ لمن له
      مسودّة، ولا تُلمَس معتمدةٌ (وهي قد تكون أُنتجت فاتورةً في أ٢ — تعديلُها
      يكسر سندَها). والفرادةُ في القاعدة تحرس ما ينفلت من التخطّي المسبق.
    - ثم تنبيهُ المسودّات التي مرّ عليها ثلاثةُ أيامٍ وما اعتُمدت.

    **والكلفةُ خطّيّةٌ في عدد الزبائن النشطين**: مسحاتٌ واحدةٌ للمستخدمين
    والمبالغ والإضافات والأسعار قبل الحلقة (`resolve_settings_for_clients`
    تمنع استعلامين لكل زبون)، ثم كتابةٌ لمن له سطورٌ ولا مسودّةَ له. ليس ثمّة
    ثابتٌ في الكلفة — وإضافةُ كلّ مسودّةٍ كتابةٌ مستقلة.
    """
    month_start, month_end = _month_bounds(day)
    clients = list(
        OfficeClient.objects
        .filter(tenant=tenant, status=OfficeClient.STATUS_ACTIVE)
        .select_related("responsible")
        .order_by("id"),
    )
    #: أصحابُ مسودّات هذا الشهر — قراءةٌ واحدةٌ تُغني عن سؤالٍ لكل زبون.
    billed_clients = set(
        FeeDraft.objects
        .filter(tenant=tenant, year=month_start.year, month=month_start.month)
        .values_list("client_id", flat=True),
    )
    methods: dict[int, dict] = {}
    subscriptions: dict[int, list] = {}
    prices: dict[int, list] = {}
    extras: dict[int, list] = {}
    if clients:
        methods = services.resolve_settings_for_clients(
            tenant, [FEE_METHOD_KEY], clients,
        )
        subscriptions = _group_by_client(
            FeeSubscription.objects.filter(tenant=tenant, client__in=clients)
            .order_by("starts_on", "id"),
        )
        prices = _group_by_client(
            ClientServicePrice.objects.filter(tenant=tenant, client__in=clients)
            .select_related("client_service__service")
            .prefetch_related("client_service__frequencies")
            .order_by("id"),
        )
        # **كلُّ ما نُفِّذ قبل الشهر ولم يُفوتر**، لا إضافاتُ الشهر السابق وحدها:
        # إضافةٌ سُجِّلت بعد توليد مسودّة شهرها تنتظر أوّلَ مسودّةٍ تالية،
        # و`billed_draft` هو ما يمنع دخولها مسودّتين.
        extras = _group_by_client(
            FeeExtraService.objects.filter(
                tenant=tenant,
                client__in=clients,
                draft=FEE_EXTRA_DESTINATION_NEXT_MONTH,
                billed_draft__isnull=True,
                performed_on__lt=month_start,
            ).order_by("performed_on", "id"),
        )

    created = 0
    for client in clients:
        if client.pk in billed_clients:
            continue
        method = methods.get(client.pk, {}).get(FEE_METHOD_KEY)
        client_extras = extras.get(client.pk, [])
        client_subscriptions = subscriptions.get(client.pk, [])
        if method == settings_registry.FEE_METHOD_PER_SERVICE:
            lines = _service_lines(prices.get(client.pk, []), month_start, month_end)
        elif _paused_month(client_subscriptions, month_start, month_end):
            # الشهرُ موقوف: لا مسودّةَ أصلاً. وإضافاتُه لا تُربط ولا تُسقَط —
            # يلتقطها أوّلُ توليدٍ بعد انتهاء الإيقاف.
            continue
        else:
            lines = _subscription_lines(client_subscriptions, month_start, month_end)
        lines += _extra_lines(client_extras)
        if not lines:
            continue
        subtotal = sum(amount for _label, amount, _source in lines)
        with transaction.atomic():
            draft, was_created = FeeDraft.objects.get_or_create(
                tenant=tenant,
                client=client,
                year=month_start.year,
                month=month_start.month,
                defaults={
                    "subtotal": subtotal,
                    "total": subtotal,
                    "generated_at": _generated_at(day),
                },
            )
            if not was_created:
                continue
            FeeDraftLine.objects.bulk_create([
                FeeDraftLine(
                    tenant=tenant, draft=draft, label=label, amount=amount,
                    source=source,
                )
                for label, amount, source in lines
            ])
            if client_extras:
                # **في المعاملة نفسها**: مسودّةٌ بلا ربطِ إضافاتها كانت تُفوتر
                # الإضافةَ مرّتين في التوليد التالي. **و`billed_draft__isnull=True`
                # هو الحارس**: الإضافاتُ قُرئت حرّةً قبل الحلقة، فتشغيلٌ متزامنٌ
                # لشهرٍ آخر قد يربطها قبلنا — فلا نُعيد ربطَ ما رُبط، وإن لم
                # يُربط كلُّها فمسودّتُنا تحسب ما صار لغيرها فتُتراجع كلُّها
                # (تلتقطها الدورةُ التالية بما بقي حرّاً).
                bound = FeeExtraService.objects.filter(
                    pk__in=[extra.pk for extra in client_extras],
                    billed_draft__isnull=True,
                ).update(billed_draft=draft)
                if bound != len(client_extras):
                    transaction.set_rollback(True)
                    continue
        created += 1
    if created:
        # عدّادُ ترقيم السنة يُهيَّأ **مع أوّل توليدٍ** لا مع أوّل اعتماد: رقمُ
        # الفاتورة يبقى من `00001` بلا فجوة، وأوّلُ اعتمادٍ لا يدفع كلفةَ إنشاء
        # صفٍّ في مسارٍ آخر (وكلفةُ التوليد تبقى ثابتةً كما يقيسها اختبارها).
        _fee_invoices_module().ensure_sequence(tenant, year=month_start.year)
    return {
        "created_drafts": created,
        "created_alerts": _raise_pending_alerts(tenant, day=day),
    }


# ── التنبيه: ثلاثةُ أيامٍ ثم مسودّةٌ تنتظر الاعتماد ──────────────────────────
def draft_period_label(draft) -> str:
    """تسميةُ فترة المسودّة (شهرها) — عامّةٌ لأن كشفَ الحساب يقرأها (#283)."""
    start = date(draft.year, draft.month, 1)
    return deadlines.period_label(
        start, deadlines.month_start_after(start, 1) - timedelta(days=1),
    )


def _approver_ids(tenant) -> set[int]:
    """مستلِمو تنبيه المسودّة: الأعضاءُ النشطون بالدورين الذين يعتمدان."""
    return set(
        UserCompanyMembership.objects
        .filter(tenant=tenant, role__in=FEE_APPROVER_ROLES, user__is_active=True)
        .values_list("user_id", flat=True),
    )


def _raise_pending_alerts(tenant, *, day) -> int:
    """تنبيهٌ **لكل مستلِمٍ ومرجعٍ** بعد ثلاثة أيامٍ من التوليد وما زالت مسودّة.

    والمرجعُ `"fee_draft:<id>"` واحد (`fee_draft_alert_ref`)، والفرادةُ في القاعدة
    تحرس التكرارَ لو نُودِي النداءُ مرّتين — كتنبيهات التذكير. والنصُّ بلا مبلغٍ:
    الجرسُ لا يحمل مالاً (حارسُ المبالغ يمرّ بالحمولات لا بالتنبيهات، لكن القاعدةُ
    واحدة). ويسقط الصفُّ من الجرس باعتماد المسودّة عند القراءة (`services`).
    """
    pending = list(
        FeeDraft.objects.filter(tenant=tenant, status=FEE_DRAFT_STATUS_DRAFT)
        .select_related("client")
        .order_by("id"),
    )
    due = [
        draft for draft in pending
        if day >= timezone.localdate(draft.generated_at) + timedelta(
            days=PENDING_ALERT_AFTER_DAYS,
        )
    ]
    if not due:
        return 0
    recipients = _approver_ids(tenant)
    if not recipients:
        return 0
    refs = {fee_draft_alert_ref(draft.pk) for draft in due}
    existing = set(
        OfficeAlert.objects
        .filter(tenant=tenant, ref_key__in=refs)
        .values_list("recipient_id", "kind", "ref_key"),
    )
    rows: list[OfficeAlert] = []
    for draft in due:
        ref = fee_draft_alert_ref(draft.pk)
        message = (
            f"{draft.client.name} — مسودّة أتعاب {draft_period_label(draft)} "
            f"غير معتمدة بعد {PENDING_ALERT_AFTER_DAYS} أيامٍ من توليدها."
        )
        for recipient_id in sorted(recipients):
            key = (recipient_id, OFFICE_ALERT_KIND_FEE_DRAFT_PENDING, ref)
            if key in existing:
                continue
            existing.add(key)
            rows.append(OfficeAlert(
                tenant=tenant,
                recipient_id=recipient_id,
                kind=OFFICE_ALERT_KIND_FEE_DRAFT_PENDING,
                ref_key=ref,
                client=draft.client,
                message=message,
                day=day,
            ))
    if rows:
        OfficeAlert.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


# ── الاعتماد والإلغاء: دورٌ لا مفتاح ────────────────────────────────────────
def can_approve_fee_drafts(tenant, user) -> bool:
    """هل يعتمد هذا العضو مسودّات الأتعاب؟ صاحبُ المكتب ومديرُ المكتب وحدهما."""
    return user_tenant_role(user, tenant) in FEE_APPROVER_ROLES


def _assert_approver(tenant, actor) -> None:
    """403 برسالته — لا 404: العضوُ يعمل في المكتب ويعرف المسودّة، وليس له دورها."""
    if not can_approve_fee_drafts(tenant, actor):
        raise PermissionDenied(
            "اعتمادُ مسودّات الأتعاب لصاحب المكتب ومدير المكتب وحدهما.",
        )


def _locked_draft(draft):
    """إعادةُ قراءة الصفّ بقفلٍ — قرارُ الاعتماد يُبنى على حالته الآنية لا لقطةٍ قديمة."""
    return (
        FeeDraft.objects
        .select_for_update()
        .select_related("client", "approved_by")
        .get(pk=draft.pk)
    )


def _fee_invoices_module():
    """وحدةُ فاتورة الأتعاب (#282/أ٢) — **استيرادٌ مؤجَّل** يفكّ دورةً حقيقيّة.

    `fee_invoices` يستورد `fees` في أعلاه (القناعُ وحسابُ المبلغ)، فاستيرادُه هنا
    في الأعلى يدير الدورةَ عند أوّل تحميل. والنداءُ وقتَ التوليد والاعتماد فقط.
    """
    from accounting_office import fee_invoices

    return fee_invoices


def approve_fee_draft(draft, *, actor, note=""):
    """`draft → approved` مع مَن اعتمدها ومتى وملاحظتَه — والانتقالُ من المسودّة وحدها.

    **وهنا المكانُ الوحيد الذي تصير فيه المسودّةُ فاتورةً مرقَّمة** (أ٢): تُصدر
    الورقةُ بعد الاعتماد في المعاملة نفسها (`get_or_create` على المسودّة)، فلا
    مسودّةَ معتمدةً بلا مستندِ مطالبةٍ ولا اعتمادٌ يعيد فيجد ورقةً ناقصة.
    """
    _assert_approver(draft.tenant, actor)
    with transaction.atomic():
        draft = _locked_draft(draft)
        if draft.status != FEE_DRAFT_STATUS_DRAFT:
            raise ValidationError({
                "status": "المسودّة معتمدةٌ أو ملغاة — لا تُعتمد مرةً أخرى.",
            })
        draft.status = FEE_DRAFT_STATUS_APPROVED
        draft.approved_by = actor if getattr(actor, "pk", None) else None
        draft.approved_at = timezone.now()
        draft.approved_note = (note or "").strip()
        draft.save(update_fields=[
            "status", "approved_by", "approved_at", "approved_note",
        ])
        _fee_invoices_module().issue_for_draft(draft, actor=actor)
        # #283: الفاتورةُ صارت مستحقّةً — يُستَهلك رصيدُ الزبون الدائنُ عليها
        # بتخصيصٍ جديد، وإلا بقي «له عندنا» لا يُخصَّص أبداً. **بعد الالتزام**:
        # المسودّةُ مقفولةٌ هنا، وقفلُ دفعةِ الزبون ومسودّاتِه تحتها يعاكس ترتيبَ
        # `create_payment` (مسودّاتٌ ثم هذه) فيجمد. والفشلُ بعد الالتزام يُسجَّل
        # ولا يقلب اعتماداً نجح (`robust`)؛ ويلحق الرصيدُ باعتمادٍ لاحق.
        tenant, client = draft.tenant, draft.client
        transaction.on_commit(
            lambda: _payments_module().apply_open_credit(tenant, [client]),
            robust=True,
        )
    return draft


def approve_all_fee_drafts(tenant, *, actor, note="") -> list:
    """«اعتمد الكل»: كلُّ مسودّةٍ منتظرةٍ في المكتب بختمٍ واحد — **والمعتمدةُ لا تُلمَس**.

    والصفوفُ تُقفل قبل القراءة (`select_for_update`) فاعتمادان متزامنان لا يمرّان
    على المسودّة نفسها، والناتجُ هو ما اعتُمد في هذا النداء. **وبنودُ المسودّة
    تُقرأ مع صفوفها** (`prefetch_related`): الردُّ يعرض مسودّاتٍ ببنودها، وقراءةُ
    البنود مسودّةً مسودّة كانت استعلاماً لكل واحدة.
    """
    _assert_approver(tenant, actor)
    with transaction.atomic():
        drafts = list(
            FeeDraft.objects
            .select_for_update()
            .select_related("client")
            .prefetch_related("lines")
            .filter(tenant=tenant, status=FEE_DRAFT_STATUS_DRAFT)
            .order_by("id"),
        )
        now = timezone.now()
        for draft in drafts:
            draft.status = FEE_DRAFT_STATUS_APPROVED
            draft.approved_by = actor if getattr(actor, "pk", None) else None
            draft.approved_at = now
            draft.approved_note = (note or "").strip()
        if drafts:
            FeeDraft.objects.bulk_update(
                drafts, ["status", "approved_by", "approved_at", "approved_note"],
            )
            # #283: أرصدةُ الزبائن الدائنة تُخصَّص على المعتمدة — بمجموعةٍ
            # واحدة، فكلفةُ النداء لا تكبر بعدد المسودّات المعتمدة. **بعد
            # الالتزام** لا داخل معاملةٍ تقفل المسودّات (انظر `approve_fee_draft`).
            clients = [draft.client for draft in drafts]
            transaction.on_commit(
                lambda: _payments_module().apply_open_credit(tenant, clients),
                robust=True,
            )
        # **والصفوفُ كلُّها تُصدِر فاتورتَها هنا أيضاً — في المعاملة نفسها**:
        # «اعتمد الكل» يختم بالقاعدة دفعةً واحدة، فلو لم يُمرّر كلَّ مسودّةٍ على
        # الإصدار لبقيت مسودّاتٌ معتمدةٌ بلا مستندِ مطالبة — وهو نصفُ العمل.
        # والنداءُ **دفعةً** لا واحدةً واحدة: كلفةٌ ثابتةٌ لا تكبر بعدد
        # المسودّات (`issue_for_drafts`)، وفشلُ الإصدار يُسقط الاعتمادَ معه.
        _fee_invoices_module().issue_for_drafts(drafts, actor=actor)
    return drafts


def cancel_fee_draft(draft, *, actor):
    """«أَلغِها» — من المسودّة وحدها، وبالاعتماد نفسِه دوراً.

    المعتمدةُ لا تُلغى لأنها صارت سندَ فاتورةٍ في أ٢؛ وإبطالُها هناك إجراءٌ له
    سندُه (إشعارٌ دائن) لا زرُّ إلغاءٍ يمحو صفّاً.

    **وإضافاتُها تعود حرّةً** (`billed_draft = None`): الإلغاءُ يعني أن الشهرَ
    لم يُفوتر، فتلحق الإضافةُ أوّلَ مسودّةٍ تالية كما لو لم تُولَّد. ولا يُعاد
    توليدُ صفّ الشهر الملغى نفسه (فرادتُه قائمة) — فالملغاةُ تبقى ولا تُستبدل.
    """
    _assert_approver(draft.tenant, actor)
    with transaction.atomic():
        draft = _locked_draft(draft)
        if draft.status != FEE_DRAFT_STATUS_DRAFT:
            raise ValidationError({
                "status": "الإلغاءُ قبل الاعتماد وحده — المسودّةُ معتمدةٌ أو ملغاة.",
            })
        draft.status = FEE_DRAFT_STATUS_CANCELLED
        draft.save(update_fields=["status"])
        FeeExtraService.objects.filter(billed_draft=draft).update(billed_draft=None)
    return draft


def pending_drafts(tenant):
    """المسودّاتُ المنتظرةُ للاعتماد — معلوماتُ «اعتمد الكل» تُبنى عليها."""
    return FeeDraft.objects.filter(tenant=tenant, status=FEE_DRAFT_STATUS_DRAFT)


# ── القراءة: المصدرُ الواحد للرؤية والقناع ───────────────────────────────────
def visible_subscriptions(tenant, user):
    return (
        FeeSubscription.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client", "currency")
    )


def visible_extras(tenant, user):
    return (
        FeeExtraService.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client")
    )


def visible_drafts(tenant, user):
    """مسودّاتُ ما يراه العضو وحدها — ومعتمدةٌ وملغاةٌ تبقى في التاريخ.

    والتفصيلُ والاعتمادُ يُقرآن من هنا أيضاً، فمسودّةُ زبونٍ لا يراه العضو **404**
    في الـview — لا 403 يُثبت وجودها.
    """
    return (
        FeeDraft.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client", "approved_by")
        .prefetch_related("lines")
    )


def visible_service_prices(tenant, user):
    """أسعارُ خدمات ما يراه العضو — عبر `client_service.client` و`visible_clients`."""
    return (
        ClientServicePrice.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user).values("pk"),
        )
        .select_related("client", "client_service__service")
        .order_by("client__name", "client_service__service__name", "id")
    )


def _client_payload(client) -> dict:
    return {"id": client.pk, "name": client.name}


def _currency_payload(currency):
    if currency is None:
        return None
    return {"id": currency.pk, "code": currency.Code, "name": currency.Name or ""}


def _payments_module():
    """استيرادٌ مؤجَّل: `payments` يستورد `fees` — والدورةُ تُفَكّ وقتَ النداء.

    النمطُ نفسُه في `services._appointments_module`: الوحدةُ التي تُبنى فوق هذه
    الطبقة تستوردها هي، ولو استوردت هي الوحدةَ لدارت الدورةُ عند التحميل.
    """
    from accounting_office import payments
    return payments


def subscription_row(row, *, masked) -> dict:
    """سطرُ اشتراك — المبلغُ `None` لمن لا يراه، والشكلُ ثابتٌ في الحالين."""
    data = {
        "id": row.pk,
        "client": _client_payload(row.client),
        "amount": row.amount,
        "currency": _currency_payload(row.currency),
        "cadence": row.cadence,
        "cadence_label": FEE_CADENCE_LABELS.get(row.cadence, ""),
        "starts_on": row.starts_on.isoformat(),
        "paused_from": None if row.paused_from is None else row.paused_from.isoformat(),
        "paused_to": None if row.paused_to is None else row.paused_to.isoformat(),
        "ended_on": None if row.ended_on is None else row.ended_on.isoformat(),
        "created_at": row.created_at.isoformat(),
    }
    return services.mask_amounts(data) if masked else data


def draft_row(draft, *, masked, summaries=None) -> dict:
    """مسودّةٌ ببنودها — **والقناعُ يطال البنودَ أيضاً** لا المبلغَ الأعلى وحده.

    ومصدرُ كل سطرٍ (`source`) وتسميتُه يُرسَلان صريحين: الواجهةُ تشرح «اشتراك /
    خدمة / إضافة» بلا تخمينٍ من نصّ البيان.

    **و`paid_amount`/`remaining`/`state` (#283) من المصدر الواحد**
    (`payments.invoice_summaries`): «اللي عليه» على هذه الفاتورة، وحالتُها
    مشتقّةٌ لا عمودٌ في المسودّة. و`summaries` يُمرَّر من قائمةٍ مجمَّعة
    باستعلامٍ واحد — لا استعلامان لكل سطر.
    """
    payments = _payments_module()
    summary = (summaries or {}).get(draft.pk) or payments.invoice_summary(draft)
    lines = [
        {
            "id": line.pk,
            "label": line.label,
            "amount": line.amount,
            "source": line.source,
            "source_label": FEE_LINE_SOURCE_LABELS.get(line.source, ""),
        }
        for line in draft.lines.all()
    ]
    data = {
        "id": draft.pk,
        "client": _client_payload(draft.client),
        "year": draft.year,
        "month": draft.month,
        "period_label": draft_period_label(draft),
        "subtotal": draft.subtotal,
        "total": draft.total,
        "paid_amount": summary.paid_amount,
        "remaining": summary.remaining,
        "state": summary.state,
        "state_label": summary.state_label,
        "status": draft.status,
        "status_label": FEE_DRAFT_STATUS_LABELS.get(draft.status, ""),
        "generated_at": draft.generated_at.isoformat(),
        "approved_by": (
            None if draft.approved_by_id is None
            else {
                "id": draft.approved_by_id,
                "name": services.user_display_name(draft.approved_by),
            }
        ),
        "approved_at": None if draft.approved_at is None else draft.approved_at.isoformat(),
        "approved_note": draft.approved_note,
        "lines": lines,
    }
    if not masked:
        return data
    data = services.mask_amounts(data)
    data["lines"] = [
        services.mask_amounts(line, services.FEE_AMOUNT_KEYS) for line in lines
    ]
    return data


def extra_row(row, *, masked) -> dict:
    data = {
        "id": row.pk,
        "client": _client_payload(row.client),
        "service_name": row.service_name,
        "amount": row.amount,
        "performed_on": row.performed_on.isoformat(),
        "draft": row.draft,
        "draft_label": FEE_EXTRA_DESTINATION_LABELS.get(row.draft, ""),
        "billed_draft": row.billed_draft_id,
        "created_at": row.created_at.isoformat(),
    }
    return services.mask_amounts(data) if masked else data


def service_price_row(price, *, masked) -> dict:
    """سطرُ سعرِ خدمةٍ لزبون — المبلغُ `None` لمن لا يراه، والشكلُ ثابتٌ في الحالين.

    والخدمةُ تُرسَل بمعرّفها واسمها: الواجهةُ تعرض «الخدمة» بلا استعلامٍ ثانٍ،
    والشكلُ واحدٌ لمن يرى ولمن لا يرى (لا يُحذف مفتاحٌ في القناع).
    """
    data = {
        "id": price.pk,
        "client": _client_payload(price.client),
        "client_service": price.client_service_id,
        "service": {
            "id": price.client_service.service_id,
            "name": price.client_service.service.name,
        },
        "amount": price.amount,
    }
    return services.mask_amounts(data) if masked else data


def subscriptions_payload(tenant, *, user) -> list[dict]:
    masked = amounts_masked(tenant, user)
    return [
        subscription_row(row, masked=masked)
        for row in visible_subscriptions(tenant, user).order_by(
            "client__name", "starts_on", "id",
        )
    ]


def drafts_payload(tenant, *, user) -> list[dict]:
    masked = amounts_masked(tenant, user)
    drafts = list(visible_drafts(tenant, user))
    summaries = _payments_module().invoice_summaries(drafts)
    return [
        draft_row(draft, masked=masked, summaries=summaries)
        for draft in drafts
    ]


def extras_payload(tenant, *, user) -> list[dict]:
    masked = amounts_masked(tenant, user)
    return [
        extra_row(row, masked=masked)
        for row in visible_extras(tenant, user).order_by("performed_on", "id")
    ]


def service_prices_payload(tenant, *, user) -> list[dict]:
    masked = amounts_masked(tenant, user)
    return [
        service_price_row(row, masked=masked)
        for row in visible_service_prices(tenant, user)
    ]


# ── الكتابة ─────────────────────────────────────────────────────────────────
def create_subscription(
    tenant, client, *, amount, starts_on, cadence=None, currency=None,
    paused_from=None, paused_to=None, ended_on=None,
):
    """اشتراكٌ جديد **بتاريخ سريانه** — والتاريخُ المكرَّر يُرفض 400 لا يُضاعف.

    ولا تُعدَّل صفوفُ السابقة: تغييرُ السعر صفٌّ جديدٌ بتاريخٍ لاحق، وهذا هو
    معنى «السعر في شهرٍ ما» — الشهرُ يقرأ السعرَ الذي كان سارياً فيه.
    """
    services.assert_client_of_tenant(tenant, client)
    amount = _clean_amount(amount)
    cadence = cadence or FEE_CADENCE_MONTHLY
    if cadence not in dict(FEE_CADENCE_CHOICES):
        raise ValidationError({"cadence": "دورية اشتراكٍ غير معروفة."})
    if paused_from is not None and paused_to is not None and paused_to < paused_from:
        raise ValidationError({"paused_to": "نهايةُ إيقاف الفوترة قبل بدايته."})
    if ended_on is not None and ended_on < starts_on:
        raise ValidationError({"ended_on": "الإنهاءُ قبل بداية الاشتراك."})
    if FeeSubscription.objects.filter(client=client, starts_on=starts_on).exists():
        raise ValidationError({
            "starts_on": (
                "سعرٌ مسجَّلٌ لهذا التاريخ — التغييرُ يضيف صفّاً بتاريخٍ لاحق."
            ),
        })
    try:
        # القيدُ في القاعدة هو الحكم الأخير: طلبان متزامنان بتاريخٍ واحد يمرّ
        # أوّلُهما، والثاني يُردّ 400 برسالته لا بـ`IntegrityError` (500).
        with transaction.atomic():
            return FeeSubscription.objects.create(
                tenant=tenant,
                client=client,
                amount=amount,
                currency=_resolve_currency(currency),
                cadence=cadence,
                starts_on=starts_on,
                paused_from=paused_from,
                paused_to=paused_to,
                ended_on=ended_on,
            )
    except IntegrityError:
        # القيدُ المخروقُ هو فرادةُ `(client, starts_on)` — وإلا فالعطلُ عطلُ
        # قاعدةٍ لا مدخلات، ويُرفع كما هو (500) كي لا يُقال «تاريخٌ مكرَّر» كذباً.
        if FeeSubscription.objects.filter(client=client, starts_on=starts_on).exists():
            raise ValidationError({
                "starts_on": (
                    "سعرٌ مسجَّلٌ لهذا التاريخ — التغييرُ يضيف صفّاً بتاريخٍ لاحق."
                ),
            }) from None
        raise


def create_extra_service(
    tenant, client, *, service_name, amount, performed_on, draft=None,
):
    """خدمةٌ إضافيةٌ نُفِّذت — **تُسجَّل عند التنفيذ** وتُحسب في مسودّة الشهر القادم."""
    services.assert_client_of_tenant(tenant, client)
    name = (service_name or "").strip()
    if not name:
        raise ValidationError({"service_name": "اسمُ الخدمة مطلوب."})
    if len(name) > 200:
        raise ValidationError({"service_name": "اسمُ الخدمة أطول من 200 حرف."})
    amount = _clean_amount(amount)
    draft = draft or FEE_EXTRA_DESTINATION_NEXT_MONTH
    if draft not in dict(FEE_EXTRA_DESTINATION_CHOICES):
        raise ValidationError({"draft": "وجهةُ الخدمة غير معروفة."})
    return FeeExtraService.objects.create(
        tenant=tenant,
        client=client,
        service_name=name,
        amount=amount,
        performed_on=performed_on,
        draft=draft,
    )


def set_client_service_price(client_service, *, amount):
    """سعرُ خدمةِ زبونٍ في طريقة «سعرٌ لكل خدمة» — صفٌّ واحدٌ يُحدَّث.

    **`OneToOne` على الخدمة**: سعرٌ واحدٌ لها لا صفّان، وإعادةُ التسعير تُحدِّث
    صفَّها — فـ`POST` على `fees/service-prices/` إضافةٌ أوّلَ مرّةٍ وتحديثٌ بعدها
    (ولا `PUT`/`PATCH`: النقطةُ تُسعّر، والتاريخُ في المسودّات اللقطاتِ لا هنا).
    وتُعيد `(الصف, هل أُنشئ)` ليختار الـview 201 أو 200.
    """
    amount = _clean_amount(amount)
    row, created = ClientServicePrice.objects.update_or_create(
        client_service=client_service,
        defaults={
            "tenant": client_service.tenant,
            "client_id": client_service.client_id,
            "amount": amount,
        },
    )
    return row, created
