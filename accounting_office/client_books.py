"""خدماتُ دفتر الزبون (#286) — الترقيمُ والقفل، ونسخُ الشجرة، والحركاتُ وعكسُها.

**هذا الملفّ لا يمسّ محرّكَ القيود العام**: لا `post_journal`، ولا
`JournalHeader`/`JournalLine`، ولا استيرادَ من `accounting` أصلاً. دفترُ الزبون
دفترُ **منشأةٍ** يمسك المكتبُ دفاترها خدمةً لها، و`accounting` دفترُ **الشركة
المالكة للمستأجر** — أي المكتب نفسه. الخلطُ بينهما يضع أرصدةَ منشآتٍ غريبة في
ميزانية المكتب وإقراره. القرارُ وسببه والبديلُ المرفوض في
`docs/decisions/client_books.md`، ويحرسه مسحُ `ast` في
`accounting_office/tests/test_client_books.py`.

**ثلاثُ قواعد لا تتزحزح هنا:**
1. **الرقمُ من عدّادٍ مقفول** (`ClientBookSequence`) لا من `MAX+1` ولا `count+1`.
2. **لا حذف**: التصحيحُ حركةٌ عكسية والأصلُ يبقى.
3. **الكتابةُ على دفتر زبونٍ خدمتُه موقوفة 400**، والقراءةُ تبقى.

**ونوعان يُكتبان بيد إنسانٍ لا بورقة، بدورٍ لا بمفتاح (#288/ب-٢):**
`manual` (قيدٌ يدويّ) و`opening` (رصيدٌ افتتاحيّ) — يُقيَّدان بـ`ENTRY_APPROVER_ROLES`
(صاحب المكتب ومديرُ المكتب) كاعتماد مسودّات الأتعاب؛ والمحاسبُ يكتب الحركات
المبنية على الأوراق بمفتاح الكتابة كما كان. والرصيدُ الافتتاحيُّ **واحدٌ لكل دفتر
ولا يُمسّ بعد أوّل حركةٍ لاحقة**: لا إعادةَ كتابةٍ ولا عكساً — لا «إقفالَ» في هذا
الدفتر أصلاً، فأوّلُ حركةٍ هي حدُّه العمليّ.
"""
import datetime
import re
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.db.models.functions import TruncMonth
from django.utils import timezone

from accounting_office import book_rates, services
from accounting_office.deadlines import MONTH_LABELS
from accounting_office.models import (
    BOOK_ACCOUNT_TYPE_LABELS,
    BOOK_ACCOUNT_TYPE_CHOICES,
    BOOK_ENTRY_KIND_BANK_MOVEMENT,
    BOOK_ENTRY_KIND_CHOICES,
    BOOK_ENTRY_KIND_DAILY_REPORT,
    BOOK_ENTRY_KIND_EXPENSE,
    BOOK_ENTRY_KIND_LABELS,
    BOOK_ENTRY_KIND_MANUAL,
    BOOK_ENTRY_KIND_OPENING,
    BOOK_ENTRY_KIND_PURCHASE_INVOICE,
    BOOK_ENTRY_KIND_SALES_INVOICE,
    BOOK_KIND_CHOICES,
    BOOK_KIND_DOUBLE,
    BOOK_KIND_LABELS,
    BOOK_KIND_SIMPLE,
    CLIENT_SERVICE_STATUS_ACTIVE,
    DOCUMENT_STATUS_RECEIVED,
    SERVICE_CODE_BOOKKEEPING,
    TAX_SYSTEM_CHOICES,
    BookAccountTemplate,
    BookEntry,
    BookEntryDocument,
    BookEntryLine,
    BookPeriodLock,
    ClientBook,
    ClientBookAccount,
    ClientBookSequence,
    ClientService,
    DocumentChecklistItem,
    OfficeBookAccount,
    OfficeClient,
)
from accounting_office.settings_registry import BOOK_ENTRY_METHOD_LABELS
from core.access import MANAGER_ROLE, OFFICE_MANAGER_ROLE, user_tenant_role
from tenants.models import Currency

#: مفتاحُ إعداد طريقة الإدخال (د10) — يُقرأ بالمحلّل، والافتراضُ «ورقة ورقة».
ENTRY_METHOD_KEY = "book_entry_method"

#: #287/٥: إعدادُ ««انقدّم» يقفل فترة الدفتر» — المفتاحُ الذي يُقرأ عند التقديم.
CLOSE_ON_SUBMIT_KEY = "book_close_on_submit"
#: #287/٢: إعدادُ السماح بنسبةٍ مخالفةٍ على سطر المستند.
LINE_RATE_KEY = "book_line_rate_override"

#: أدوارُ من يكتب **بيده** قيداً يدوياً أو رصيداً افتتاحياً — دورٌ لا مفتاح، كنمط
#: `fees.FEE_APPROVER_ROLES`: مديرُ المكتب يملك مفاتيحَ المكتب كلَّها، والمحاسبُ
#: يكتب الزبون ولا يكتب رصيدَ استلامٍ يقرؤه المدير.
ENTRY_APPROVER_ROLES: tuple[str, ...] = (MANAGER_ROLE, OFFICE_MANAGER_ROLE)

#: الأنواعُ التي تحتاج ذلك الدور — القائمةُ الواحدةُ التي يقرؤها الحارس.
ENTRY_APPROVER_KINDS: tuple[str, ...] = (
    BOOK_ENTRY_KIND_MANUAL, BOOK_ENTRY_KIND_OPENING,
)

#: شكلُ «شهر-يوم» في `ClientBook.fiscal_year_start` — مزدوجٌ بخانتين.
FISCAL_START_PATTERN = re.compile(r"^(\d{2})-(\d{2})$")
#: شكلُ رمز العملة (ISO 4217): ثلاثةُ أحرفٍ لاتينية كبيرة.
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

#: مفتاحُ كود الحساب في بند الحركة الوارد من الـAPI — البديلُ هو تمرير الكائن.
ACCOUNT_CODE_KEY = "account_code"

#: مفاتيحُ المبالغ في سطر الحركة: الحقلان المسجَّلان في `services.AMOUNT_KEYS`
#: والمجموعان المشتقّان منهما. **تُقنَّع كلُّها** — `total_debit` مبلغٌ ولو لم
#: يكن عموداً في القاعدة، وقنعُ الحقلين وحدَهما يترك الرقم في المجموع.
ENTRY_ROW_AMOUNT_KEYS: tuple[str, ...] = (
    "debit", "credit", "total_debit", "total_credit",
)


def _today() -> datetime.date:
    return timezone.localdate()


def _amount(value) -> str:
    """مبلغٌ كنصٍّ من خانتين — الشكلُ الذي يخرج به كلُّ رقمٍ من الخادم."""
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _decimal(value) -> Decimal:
    """مدخلُ مبلغٍ إلى `Decimal` بخانتين — أو 400 لا 500."""
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (ArithmeticError, TypeError, ValueError):
        raise ValidationError({"lines": "مبلغ غير رقميّ في أحد البنود."}) from None


# ── وجودُ الدفتر: مشتقٌّ من الخدمة لا من حقلٍ ثانٍ (د5) ─────────────────────
def bookkeeping_service_on(client, day):
    """خدمةُ مسك الدفاتر للزبون **بحالة `status_on` القائمة** — لا قاعدةَ ثانية.

    `status_on` هي القاعدةُ نفسها التي يُشتقّ منها `is_active` في
    `services.client_service_row`؛ هذه الدالةُ تسألها ولا تعيد كتابتها، فلا
    تفترق نسختان حين تتغيّر قاعدةُ الإيقاف.
    """
    for row in client.services.filter(service__code=SERVICE_CODE_BOOKKEEPING):
        if row.status_on(day) == CLIENT_SERVICE_STATUS_ACTIVE:
            return row
    return None


def _writable_refusal(book, day=None) -> str:
    """سببُ منع الكتابة **برسالته** — أو نصٌّ فارغ إن كان الدفترُ قابلاً للكتابة.

    **والسببان مفصولان لأن الرسالةَ واحدة**: خدمةٌ موقوفةُ تُصلَح من شاشة الخدمات،
    وزبونٌ منتهٍ يُصلَح بـ«أعِد نشطاً» — ورسالةٌ تسمّي الأوّل عن الثاني ترسل
    المحاسبَ إلى الشاشة الخطأ. والقاعدةُ في موضعٍ واحدٍ يقرؤه البوليانُ والحارس.
    """
    if book.client.status != OfficeClient.STATUS_ACTIVE:
        return "الزبون منتهٍ — دفتره للقراءة فقط. أعِدْه نشطاً للكتابة فيه."
    if bookkeeping_service_on(book.client, day or _today()) is None:
        return "خدمة مسك الدفاتر موقوفة لهذا الزبون — الدفتر للقراءة فقط."
    return ""


def book_is_writable(book, day=None) -> bool:
    """هل يُكتب في هذا الدفتر؟ — **حالتُه وحالةُ خدمته معاً**.

    **والزبونُ المنتهي دفترُه للقراءة** (إصلاحُ #288): «أنهِ الزبون»
    (`services.end_office_client`) يغيّر `status` على `OfficeClient` ولا يمسّ صفَّ
    الخدمة (وهو ما يجب: تاريخُ الخدمة يبقى). فسؤالُ الخدمة وحدها كان يترك دفتر
    زبونٍ صُفّي حسابُه قابلاً للكتابة إلى الأبد — يُدخل فيه المحاسبُ بعد أن سُلّم
    الزبون نسختَه.
    """
    return not _writable_refusal(book, day)


def assert_book_writable(book, day=None) -> None:
    """الكتابةُ على دفتر زبونٍ خدمتُه موقوفةٍ أو منتهٍ 400 — والدفترُ يبقى للقراءة."""
    reason = _writable_refusal(book, day)
    if reason:
        raise ValidationError({"client": reason})


def writable_client_ids(tenant, clients, day) -> set[int]:
    """الزبائن الحيّون ذوو خدمةٍ نشطة — **استعلامٌ واحد** لقائمةٍ كاملة.

    بدل `book_is_writable` لكل دفتر: القائمةُ تقرأ من هنا، والمفردُ يسأل الدالة
    المفردة. والقاعدةُ واحدةٌ في الاثنين (`status_on` + حالةُ الزبون)، والترشيحُ
    على الحالة في `WHERE` لا فلترةً بعد القراءة.
    """
    active: set[int] = set()
    for row in ClientService.objects.filter(
        tenant=tenant,
        service__code=SERVICE_CODE_BOOKKEEPING,
        client__in=clients,
        client__status=OfficeClient.STATUS_ACTIVE,
    ):
        if row.status_on(day) == CLIENT_SERVICE_STATUS_ACTIVE:
            active.add(row.client_id)
    return active


# ── الصفوف كما تخرج (الشكلُ في الخادم وحده) ────────────────────────────────
def book_row(book, *, writable, entry_method) -> dict:
    return {
        "client_id": book.client_id,
        "client_name": book.client.name,
        "kind": book.kind,
        "kind_label": BOOK_KIND_LABELS.get(book.kind, book.kind),
        "opened_on": book.opened_on.isoformat(),
        "kind_changed_on": (
            book.kind_changed_on.isoformat() if book.kind_changed_on else None
        ),
        "fiscal_year_start": book.fiscal_year_start,
        "currency": book.currency,
        "entry_method": entry_method,
        "entry_method_label": BOOK_ENTRY_METHOD_LABELS.get(entry_method, ""),
        "writable": writable,
    }


def account_row(row, *, tenant=None, tax_system="", overrides=None) -> dict:
    """سطرُ حسابٍ — **ونسبُه الثلاث** (#287/٢ و٣) حين يُعرَف مكتبُه.

    النسبُ تُحسب لشجرةٍ كاملةٍ بنداءٍ واحدٍ للمكتب (`overrides`)، لا استعلامين لكل
    حساب: شجرةُ زبونٍ ثلاثون حساباً كانت تُنتج تسعين استعلاماً في فتحةٍ واحدة.
    ونداءٌ بلا `tenant` يعطي السطرَ بلا نسبٍ — للشكل القديم وحده.
    """
    payload = {
        "code": row.code,
        "name": row.name,
        "parent_code": row.parent.code if row.parent_id else None,
        "account_type": row.account_type,
        "account_type_label": BOOK_ACCOUNT_TYPE_LABELS.get(
            row.account_type, row.account_type,
        ),
        "is_system": row.is_system,
        "is_active": row.is_active,
        "rate_category": row.rate_category,
        "rates": None,
    }
    if tenant is not None:
        rates = book_rates.account_rows(
            row, tenant=tenant, tax_system=tax_system, overrides=overrides,
        )
        payload["rates"] = rates
        payload["rate_category_label"] = rates[book_rates.RATE_KIND_VAT].get("label", "")
    return payload


# ── تسمياتُ الأنواع كما تخرج: من النموذج لا من جدولٍ ثانٍ ─────────────────────
def _choice_rows(choices) -> list[dict]:
    """ثنائيّاتُ النموذج (`value`, `label`) بالشكل الذي تستهلكه الواجهة."""
    return [{"value": value, "label": label} for value, label in choices]


def book_kind_choices() -> list[dict]:
    """نوعا الدفتر — `kind` في سطر الدفتر، لا نوعُ الحركة."""
    return _choice_rows(BOOK_KIND_CHOICES)


def entry_kind_choices() -> list[dict]:
    """أنواعُ الحركة — `entry_kinds` في نقطة `choices/` و`entry_kind_choices` في السطر."""
    return _choice_rows(BOOK_ENTRY_KIND_CHOICES)


def account_type_choices() -> list[dict]:
    return _choice_rows(BOOK_ACCOUNT_TYPE_CHOICES)


def choices_payload() -> dict:
    """`GET client-books/choices/` — تسمياتُ الأنواع الثلاثة كما في النموذج.

    **وتسمياتُ نوع الدفتر لا يحملها أيّ ردٍّ آخر**: `kind_label` يسمّي النوع
    الحاليَّ وحده، فمنتقي النوع عند إنشاء الدفتر وزرُّ الانتقال («حوّل إلى مزدوج»)
    يحتاجان القائمة كاملة. واسمُ `entry_kinds` لا `kind_choices`: `kind` في هذا
    الموديول نوعُ **الدفتر**، وخلطُهما هو الخطأُ نفسه الذي جعل زرَّ الانتقال يبحث
    عن `double` في أنواع الحركة.
    """
    return {
        "book_kinds": book_kind_choices(),
        "entry_kinds": entry_kind_choices(),
        "account_types": account_type_choices(),
    }


def amounts_masked(tenant, user) -> bool:
    """قرارُ القناع **مرّةً واحدة** — تُمرَّر النتيجةُ إلى `entry_row` ولا تُسأل فيها.

    `can_see_amounts` تنادي `user_has_perm` التي تقرأ العضوية ثم تجاوزَ الدور ثم
    تجاوزَ العضو: أربعةُ استعلاماتٍ إلى خمسة. سؤالُها **لكل حركة** يجعل قائمةَ ألف
    حركةٍ خمسةَ آلاف استعلام (الخطأ نفسه الذي أُصلح في `packages_payload`).
    و`user=None` الصريح وحده نداءٌ داخليٌّ بلا قناع — كـ`services.tax_card_payload`.
    """
    return user is not None and not services.can_see_amounts(tenant, user)


def _mask_entry_row(row: dict) -> dict:
    """قناعُ المبالغ على سطر حركةٍ وبنودِه — الشكلُ يبقى، القيمةُ تصير `None`."""
    masked = services.mask_amounts(row, ENTRY_ROW_AMOUNT_KEYS)
    masked["lines"] = [
        services.mask_amounts(line, services.BOOK_ENTRY_AMOUNT_KEYS)
        for line in row["lines"]
    ]
    return masked


def entry_row(entry, *, masked) -> dict:
    """سطرُ حركةٍ — **والقناعُ قرارٌ جاهزٌ يُمرَّر** (`amounts_masked`) لا سؤالٌ هنا.

    والقناعُ يطال المدينَ والدائنَ **والمجموعين المشتقّين**: قنعُ الحقلين وحدَهما
    يترك الرقمَ في `total_debit`. و`documents` روابطُ الأوراق التي أُدخلت بها
    الحركة — تُقرأ لا تُشتقّ من عمود.
    """
    lines = list(entry.lines.all())
    # عكسيُّ `OneToOneField` كائنٌ لا مدير، وغيابُه يرمي `RelatedObjectDoesNotExist`
    # (وهي `AttributeError` أيضاً) — فـ`getattr` بافتراضٍ هو «لم تُعكس».
    reversal = getattr(entry, "reversed_by", None)
    row = {
        "id": entry.pk,
        "number": entry.number,
        "year": entry.year,
        "entry_date": entry.entry_date.isoformat(),
        "kind": entry.kind,
        "kind_label": BOOK_ENTRY_KIND_LABELS.get(entry.kind, entry.kind),
        "memo": entry.memo,
        "documents": [link.document_id for link in entry.documents.all()],
        "reverses": entry.reverses_id,
        "reversed_by": reversal.pk if reversal is not None else None,
        "total_debit": _amount(sum(line.debit for line in lines)),
        "total_credit": _amount(sum(line.credit for line in lines)),
        "lines": [
            {
                "account_code": line.account.code,
                "account_name": line.account.name,
                "debit": _amount(line.debit),
                "credit": _amount(line.credit),
                "tax_base": _amount(line.tax_base),
                "tax_amount": _amount(line.tax_amount),
                "side_party": line.side_party,
                # #287/٢: نسبةُ السطر إن كُتبت — بلا سببٍ لا تُكتب (الخدمةُ تفحص)،
                # وهي هنا حدُّ التسوية على نسبة الحساب.
                "vat_rate": (
                    None if line.vat_rate is None
                    else str(Decimal(line.vat_rate).quantize(book_rates.RATE_QUANTUM))
                ),
                "vat_rate_reason": line.vat_rate_reason,
            }
            for line in lines
        ],
    }
    return _mask_entry_row(row) if masked else row


# ── قراءةُ الدفاتر ─────────────────────────────────────────────────────────
def books_payload(tenant, user, *, day=None) -> list[dict]:
    """كلُّ دفترٍ يراه العضو — والحالةُ وطريقةُ الإدخال في استعلاماتٍ ثابتة."""
    day = day or _today()
    books = list(
        ClientBook.objects
        .filter(
            tenant=tenant,
            client__in=services.visible_clients(tenant, user),
        )
        .select_related("client")
        .order_by("client__name", "client_id"),
    )
    if not books:
        return []
    clients = [book.client for book in books]
    active = writable_client_ids(tenant, clients, day)
    methods = services.resolve_setting_for_clients(tenant, ENTRY_METHOD_KEY, clients)
    return [
        book_row(
            book,
            writable=book.client_id in active,
            entry_method=methods.get(book.client_id),
        )
        for book in books
    ]


def accounts_payload(client, *, tenant=None) -> list[dict]:
    """شجرةُ الحساب — ونسبُها حين يُمرَّر المكتب (خريطةُ التجاوزات تُقرأ مرّةً).

    ونظامُ الزبون يُقرأ مرّةً واحدةً هنا لا لكل حساب: `resolve_setting` استعلامان
    أو ثلاثة، فقراءتُه ثلاثين مرّةً تجعل الشجرةَ مئةَ استعلام.
    """
    rows = (
        ClientBookAccount.objects
        .filter(client=client)
        .select_related("parent")
        .order_by("code", "id")
    )
    if tenant is None:
        return [account_row(row) for row in rows]
    tax_system = services.resolve_setting(
        tenant, services.TAX_SYSTEM_KEY, client=client,
    ) or ""
    overrides = (
        book_rates.office_override_map(tenant, tax_system) if tax_system else {}
    )
    return [
        account_row(
            row, tenant=tenant, tax_system=tax_system, overrides=overrides,
        )
        for row in rows
    ]


def entries_payload(book, *, year=None, user) -> list[dict]:
    """حركاتُ الدفتر — والقناعُ يُحسب **مرّةً** لهذه القائمة لا لكل صفّ."""
    rows = (
        book.entries
        .select_related("client")
        .prefetch_related("lines__account", "reversed_by", "documents")
    )
    if year is not None:
        rows = rows.filter(year=year)
    masked = amounts_masked(book.tenant, user)
    return [
        entry_row(row, masked=masked)
        for row in rows.order_by("year", "number", "id")
    ]


# ── إنشاءُ الدفتر ونسخُ الشجرة (د6) ────────────────────────────────────────
def _client_tax_system(client) -> str:
    """النظامُ الضريبي للزبون من المحلّل — لا من حقلٍ ثانٍ في البطاقة."""
    system = services.resolve_setting(client.tenant, services.TAX_SYSTEM_KEY, client=client)
    known = {value for value, _label in TAX_SYSTEM_CHOICES}
    if system not in known:
        raise ValidationError({
            "client": "النظام الضريبي غير مختار — اختره قبل إنشاء الدفتر.",
        })
    return system


def _tree_source(client, kind) -> list[tuple[str, str, str, str, bool]]:
    """مصدرُ الشجرة: نسخةُ المكتب إن وُجدت، وإلا قالبُ المنصّة — لا خلطَ بينهما."""
    tax_system = _client_tax_system(client)
    office_rows = list(
        OfficeBookAccount.objects
        .filter(tenant=client.tenant, tax_system=tax_system, book_kind=kind)
        .order_by("code", "id"),
    )
    if office_rows:
        return [
            (row.code, row.name, row.parent_code, row.account_type, row.is_system)
            for row in office_rows
        ]
    return [
        (row.code, row.name, row.parent_code, row.account_type, row.is_system)
        for row in BookAccountTemplate.objects
        .filter(tax_system=tax_system, book_kind=kind)
        .order_by("code", "id")
    ]


def _create_tree_rows(client, rows, known=None) -> dict[str, ClientBookAccount]:
    """إنشاءُ صفوفِ شجرةٍ ثم ربطُ آبائها — **تمريرتان** لا تمريرة.

    الأبُ قد يأتي بعد ابنه في المصدر، فتمريرةٌ واحدة تُنتج يتيماً صامتاً. و`known`
    صفوفٌ موجودةٌ سابقاً: أبو الحساب المضاف قد يكون في الشجرة القائمة لا في
    الصفوف الجديدة (انتقالُ النوع يضيف ما نقص ولا ينسخ ما وُجد).
    """
    created: dict[str, ClientBookAccount] = {
        code: ClientBookAccount.objects.create(
            client=client,
            code=code,
            name=name,
            account_type=account_type,
            is_system=is_system,
        )
        for code, name, _parent_code, account_type, is_system in rows
    }
    lookup = {**(known or {}), **created}
    for code, _name, parent_code, _account_type, _is_system in rows:
        parent = lookup.get(parent_code) if parent_code else None
        if parent is not None:
            created[code].parent = parent
            created[code].save(update_fields=["parent"])
    return created


def ensure_client_tree(client, kind) -> list[ClientBookAccount]:
    """نسخةُ شجرةٍ واحدة عند إنشاء الدفتر — **بلا مرجعٍ حيّ** إلى القالب."""
    existing = list(ClientBookAccount.objects.filter(client=client))
    if existing:
        return existing
    with transaction.atomic():
        _create_tree_rows(client, _tree_source(client, kind))
    return list(ClientBookAccount.objects.filter(client=client))


def sync_client_tree(client, kind) -> int:
    """يضيف **الأكوادَ الناقصة** من شجرة النوع المطلوب ولا يمسّ القائم.

    انتقالُ الدفتر إلى المزدوج بلا هذا يتركه بلا `2000`/`2100`/`2200`/`3000`/
    `5300`: فأوّلُ بندِ ضريبةٍ أو شراءٍ بالآجل يُرفض 400 «لا حسابَ بهذا الكود»
    حتى تُبنى ستةُ حساباتٍ يدوياً وبترتيب آبائها. يعيد عددَ ما أُضيف.
    """
    existing = {
        row.code: row for row in ClientBookAccount.objects.filter(client=client)
    }
    missing = [row for row in _tree_source(client, kind) if row[0] not in existing]
    if not missing:
        return 0
    _create_tree_rows(client, missing, known=existing)
    return len(missing)


def _base_currency_code() -> str:
    """عملةُ الشركة الافتراضية: رمزُ العملة الأساسية في المنصّة، وإلا فراغ.

    المصدرُ جدولُ `Currency` نفسُه (كـ`fees._resolve_currency`) لا ثابتٌ في الكود:
    المنصّةُ تبدّل عملتها الأساسية، ودفترٌ جديدٌ يتبعها. والفراغُ لا يكسر شيئاً —
    يُعرَض فارغاً حتى يُضبط من شاشة الدفتر.
    """
    base = Currency.objects.filter(IsBaseCurrency=True).order_by("CurrencyID").first()
    return ((base.Code or "").strip().upper()) if base is not None else ""


def create_book(tenant, client, *, kind, opened_on=None, day=None):
    """دفترُ زبونٍ بمسك دفاتر نشط — والنسخةُ من الشجرة في المعاملة نفسها."""
    day = day or _today()
    if kind not in BOOK_KIND_LABELS:
        raise ValidationError({"kind": "نوع دفتر غير معروف."})
    if bookkeeping_service_on(client, day) is None:
        raise ValidationError({
            "client": "لا دفترَ لزبونٍ بلا خدمة مسك دفاتر نشطة.",
        })
    with transaction.atomic():
        # الفحصُ مصدرُ الرسالة العربية لا الحارس: طلبان متزامنان يمرّان به معاً،
        # والحارسُ قيدُ `OneToOne` على `client` — فخاسرُ السباق يلقى `IntegrityError`.
        if ClientBook.objects.filter(client=client).exists():
            raise ValidationError({"client": "لهذا الزبون دفترٌ قائم."})
        book = ClientBook.objects.create(
            tenant=tenant,
            client=client,
            kind=kind,
            opened_on=opened_on or day,
            currency=_base_currency_code(),
        )
        ensure_client_tree(client, kind)
    return book


# ── السنةُ المالية والعملة (#288/ب-٢) ──────────────────────────────────────
def fiscal_year_start_parts(value) -> tuple[int, int]:
    """`(شهر، يوم)` من نصّ «شهر-يوم» — و1/1 لنصٍّ فارغٍ أو فاسد.

    **القراءةُ لا ترفض**: تقريرُ دفترٍ قائمٍ لا يسقط لأن حقلَ إعدادٍ قديمٍ فسد؛
    والرفضُ عند الكتابة (`normalize_fiscal_year_start`).
    """
    match = FISCAL_START_PATTERN.match((value or "").strip())
    if match is None:
        return 1, 1
    month, day = int(match.group(1)), int(match.group(2))
    try:
        datetime.date(2001, month, day)
    except ValueError:
        return 1, 1
    return month, day


def normalize_fiscal_year_start(raw) -> str:
    """«شهر-يوم» مُطبَّعاً أو 400 — و29 شباط مرفوض: لا يتكرّر في كل عام."""
    match = FISCAL_START_PATTERN.match((raw or "").strip())
    if match is None:
        raise ValidationError({
            "fiscal_year_start": "بدايةُ السنة المالية بصيغة «شهر-يوم» — مثال 07-01.",
        })
    month, day = int(match.group(1)), int(match.group(2))
    try:
        # سنةٌ غير كبيسةٍ عمداً: الحقلُ يتكرّر كلَّ عام، فتاريخٌ لا يوجد في بعضها
        # يُسقِط حسابَ الفترة في تلك السنين.
        datetime.date(2001, month, day)
    except ValueError:
        raise ValidationError({
            "fiscal_year_start": "تاريخٌ لا وجودَ له في التقويم — راجع الشهر واليوم.",
        }) from None
    return f"{month:02d}-{day:02d}"


def normalize_currency(raw) -> str:
    """رمزُ ISO 4217 من ثلاثة أحرف — موجوداً في عملات المنصّة، وإلا 400."""
    code = (raw or "").strip().upper()
    if not CURRENCY_PATTERN.match(code):
        raise ValidationError({"currency": "رمزُ العملة ثلاثةُ أحرف — مثال ILS."})
    if not Currency.objects.filter(Code=code).exists():
        raise ValidationError({"currency": "عملةٌ غير معروفة في المنصّة."})
    return code


def update_settings(book, *, fiscal_year_start=None, currency=None, day=None):
    """سنةُ الدفتر المالية وعملتُه — **كتابةً على دفترٍ حيّ** لا على منتهٍ.

    والغيابُ لا يُفرّغ الحقل: ما لم يُرسَل يبقى كما هو، فلا حاجةَ لإرسال الاثنين
    معاً في كل تعديل.
    """
    assert_book_writable(book, day)
    fields = []
    if fiscal_year_start is not None:
        book.fiscal_year_start = normalize_fiscal_year_start(fiscal_year_start)
        fields.append("fiscal_year_start")
    if currency is not None:
        book.currency = normalize_currency(currency)
        fields.append("currency")
    if fields:
        book.save(update_fields=fields)
    return book


# ── شجرةُ الزبون: إضافةُ حساب ──────────────────────────────────────────────
def add_account(client, *, code, name, parent_code="", account_type):
    code = (code or "").strip()
    name = (name or "").strip()
    parent_code = (parent_code or "").strip()
    if not code:
        raise ValidationError({"code": "كود الحساب مطلوب."})
    if not name:
        raise ValidationError({"name": "اسم الحساب مطلوب."})
    if account_type not in BOOK_ACCOUNT_TYPE_LABELS:
        raise ValidationError({"account_type": "نوع حساب غير معروف."})
    if ClientBookAccount.objects.filter(client=client, code=code).exists():
        raise ValidationError({"code": "هذا الكود مستعملٌ في شجرة الزبون."})
    parent = None
    if parent_code:
        parent = ClientBookAccount.objects.filter(
            client=client, code=parent_code,
        ).first()
        if parent is None:
            raise ValidationError({"parent_code": "لا حسابَ أبٍ بهذا الكود."})
    return ClientBookAccount.objects.create(
        client=client,
        code=code,
        name=name,
        parent=parent,
        account_type=account_type,
        is_system=False,
    )


# ── الحركات: الترقيمُ المقفول (د3) والتصحيحُ العكسيّ (د4) ──────────────────
def _assert_tenant_can_write_amounts(tenant, actor) -> None:
    """من لا يرى المبالغ لا يكتبها في هذه الشركة — **403 لا 400**.

    والقاعدةُ في موضعٍ واحدٍ يقرؤه الحركةُ ومبلغُ الورقة: الحركةُ ليست وحدها
    مبلغاً، ومبلغُ الورقة يُولّد بنودَها فيصير مالاً في الدفتر. و`actor=None`
    نداءٌ داخليّ. و`PermissionDenied` تحوّلها DRF إلى 403 كما يفعل
    `reject_amount_writes` في الـviews — 400 كان يقول «حمولتُك فاسدة» عن صلاحيةٍ
    ناقصة.
    """
    if actor is None or services.can_see_amounts(tenant, actor):
        return
    raise PermissionDenied(
        "صلاحية «يرى المبالغ» غير ممنوحة لدورك — لا تكتب مبلغاً لا تراه.",
    )


def _assert_can_write_amounts(book, actor) -> None:
    """حارسُ المبلغ على دفترٍ — الحركةُ مبلغٌ بيد من يكتبها.

    النصُّ والقاعدةُ في `_assert_tenant_can_write_amounts`، وهذا النداءُ يقرأ
    شركةَ الدفتر: نداءٌ برمجيّ يمرّ بالحارس نفسِه الذي يمرّ به الـview.
    """
    _assert_tenant_can_write_amounts(book.tenant, actor)


def kind_on(book, day) -> str:
    """نوعُ الدفتر **في تاريخٍ ما** — الحركةُ تُقاس بنوع عهدها لا بنوع اليوم.

    بعد انتقالٍ مشروعٍ إلى المزدوج، حركاتُ ما قبل الانتقال بقيت بسيطة (طرفٌ واحد
    لكل بند). ولو قيست بالنوع الحالي لصار عكسُها 400 «غير متوازنة»، ولبقيت ورقةٌ
    متأخّرةٌ لسنةٍ كانت بسيطة مُجبَرةً على قيدٍ مزدوج متوازن. `kind_changed_on`
    يُقرأ هنا — لا يُكتب ويُترك بلا قارئ.
    """
    changed = book.kind_changed_on
    if changed is not None and day.year < changed.year:
        return BOOK_KIND_SIMPLE
    return book.kind


def _live_entries():
    """حركةٌ **حيّة**: ليست عكساً ولم تُعكس — وحدها تُعدّ الورقةَ «مُدخلة» (د9)."""
    return BookEntry.objects.filter(reverses__isnull=True, reversed_by__isnull=True)


def opening_is_locked(book) -> bool:
    """هل بدأت حركةُ الدفتر؟ الافتتاحيُّ يُقفل بأوّل حركةٍ **غيرِ افتتاحيةٍ حيّة**.

    **ولا «إقفالَ» في هذا الدفتر** (لا قيودَ إقفالٍ ولا فترةً مقفولة): الحدُّ العمليُّ
    الذي يحفظ المعنى هو أوّلُ حركةٍ لاحقة، لأن رصيدَ بدايةٍ يُكتب بعدها يصير رقماً
    في وسط التاريخ لا بدايةً له. وعكسُ الحركة اللاحقة يرفع القفل — التاريخُ عاد
    إلى ما كان عليه، فلا لزومَ لقفلٍ لا يُرفع.
    """
    return (
        _live_entries()
        .filter(client_book=book)
        .exclude(kind=BOOK_ENTRY_KIND_OPENING)
        .exists()
    )


def live_opening_entry(book):
    """الحركةُ الافتتاحيةُ الحيّةُ للدفتر إن وُجدت — **واحدةٌ على الأكثر**."""
    return _live_entries().filter(
        client_book=book, kind=BOOK_ENTRY_KIND_OPENING,
    ).first()


def _assert_opening_unlocked(book) -> None:
    """لا يُكتب افتتاحيٌّ ولا يُعكس بعد أوّل حركةٍ لاحقة — 400 برسالته."""
    if opening_is_locked(book):
        raise ValidationError({
            "kind": (
                "الرصيدُ الافتتاحيُّ مُقفل: في الدفتر حركةٌ لاحقة. يُدخل الافتتاحيُّ "
                "قبل أوّل حركة، وتُصحَّح الحركةُ اللاحقة (أو عكسُها) لا الافتتاحُ."
            ),
        })


def _assert_no_live_opening(book) -> None:
    """افتتاحيٌّ واحدٌ حيٌّ لكل دفتر — الثاني 400 لأنه تكرارُ بدايةٍ لا تصحيحُها."""
    if live_opening_entry(book) is not None:
        raise ValidationError({
            "kind": "للدفتر رصيدٌ افتتاحيٌّ بالفعل — التصحيحُ حركةٌ عكسية عليه.",
        })


def _assert_entry_writer(book, kind, actor) -> None:
    """القيدُ اليدويُّ والرصيدُ الافتتاحيُّ **بدور** المدير/صاحب المكتب — 403.

    والمفتاحُ لا يكفي: المحاسبُ يملك `office.clients.write` و`office.amounts.view`
    فيمرّ من الحارسين، والمنعُ دورٌ لا صلاحية (نمط `fees._assert_approver`).
    و`actor=None` نداءٌ داخليٌّ كـ`_assert_can_write_amounts`، والـviews تمرّر
    المستخدمَ دائماً.
    """
    if kind not in ENTRY_APPROVER_KINDS or actor is None:
        return
    if user_tenant_role(actor, book.tenant) not in ENTRY_APPROVER_ROLES:
        raise PermissionDenied(
            "لا يكتب القيدَ اليدويَّ ولا الرصيدَ الافتتاحيَّ إلا المديرُ وصاحبُ "
            "المكتب — لا بمفتاح الكتابة.",
        )


def _next_number(client, year) -> int:
    """**الرقمُ من العدّاد المقفول** — لا `MAX(number)+1` ولا `count()+1`.

    `select_for_update` على صفّ العدّاد يُسلسل الكُتّاب، والزيادةُ تُكتب في
    المعاملة نفسها؛ فمن دخل بعد أوّله قرأ القيمةَ الجديدة لا القديمة. والبديلان
    الآخران يقرآن لقطةً قديمة تحت التزامن فيُكرّران رقماً أو يُحدثان فجوة.

    ولا تُنادَ خارج `transaction.atomic()`: القفلُ بلا معاملةٍ لا معنى له.
    """
    sequence, _created = ClientBookSequence.objects.select_for_update().get_or_create(
        client=client,
        year=year,
        defaults={"tenant": client.tenant},
    )
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    return sequence.last_number


def _account_for(client, raw):
    """الحسابُ من كائنٍ (المناداة الداخلية) أو من كودٍ (الـAPI) — كائناً واحداً."""
    account = raw.get("account")
    if account is not None:
        return account
    code = (raw.get(ACCOUNT_CODE_KEY) or "").strip()
    if not code:
        return None
    return ClientBookAccount.objects.filter(client=client, code=code).first()


def _prepare_lines(client, lines, *, allow_rate_override=False) -> list[dict]:
    """بنودُ الحركة: حسابٌ ومدينٌ أو دائن، **ونسبةُ ضريبةٍ على السطر بسببها**.

    نسبةُ السطر (#287/٢) لا تُكتب صامتة: `allow_rate_override` يقرأ إعدادَ
    `book_line_rate_override`، ومعه **سببٌ ملزم** — سطرٌ بنسبةٍ تخالف نسبة حسابه
    بلا تفسيرٍ رقمٌ لا يدافع عن نفسه في مراجعة. والرفضُ 400 برسالةٍ تسمّي البند.
    """
    if not lines:
        raise ValidationError({"lines": "الحركة تحتاج بنداً واحداً على الأقل."})
    prepared = []
    for index, raw in enumerate(lines):
        where = f"بند {index + 1}"
        account = _account_for(client, raw)
        if account is None:
            raise ValidationError({"lines": f"{where}: لا حسابَ بهذا الكود."})
        debit = _decimal(raw.get("debit"))
        credit = _decimal(raw.get("credit"))
        tax_base = _decimal(raw.get("tax_base"))
        tax_amount = _decimal(raw.get("tax_amount"))
        if debit < 0 or credit < 0:
            raise ValidationError({"lines": f"{where}: مبلغٌ سالب — اعكس الطرف."})
        if tax_base < 0 or tax_amount < 0:
            raise ValidationError({"lines": f"{where}: ضريبةٌ سالبة — تصحيحُها بحركة."})
        if debit == 0 and credit == 0:
            raise ValidationError({"lines": f"{where}: لا مدينَ ولا دائن."})
        if debit and credit:
            raise ValidationError({
                "lines": f"{where}: طرفٌ واحد لكل بند — مدينٌ أو دائن لا الاثنان.",
            })
        vat_rate, reason = _line_rate(raw, where=where, allowed=allow_rate_override)
        prepared.append({
            "account": account,
            "debit": debit,
            "credit": credit,
            "tax_base": tax_base,
            "tax_amount": tax_amount,
            "vat_rate": vat_rate,
            "vat_rate_reason": reason,
            "side_party": (raw.get("side_party") or "").strip()[:200],
        })
    return prepared


def _line_rate(raw, *, where, allowed) -> tuple[Decimal | None, str]:
    """نسبةُ السطر إن أُرسلت — بإعدادٍ مفعّلٍ وسببٍ مكتوب، وإلا `(None, "")`."""
    raw_rate = raw.get("vat_rate")
    reason = (raw.get("rate_reason") or raw.get("vat_rate_reason") or "").strip()
    if raw_rate in (None, ""):
        if reason:
            raise ValidationError({
                "lines": f"{where}: سببُ النسبة بلا نسبة.",
            })
        return None, ""
    if not allowed:
        raise ValidationError({
            "lines": (
                f"{where}: تعديلُ نسبة ض.ق.م على سطر المستند غير مفعّل — "
                "فعّل «السماح بتعديل نسبة ض.ق.م على سطر المستند» أو اكتب النسبة "
                "على الحساب."
            ),
        })
    if not reason:
        raise ValidationError({
            "lines": f"{where}: نسبةُ السطر تحتاج سبباً مكتوباً يُحفظ معها.",
        })
    try:
        rate = Decimal(str(raw_rate))
    except (ArithmeticError, TypeError, ValueError):
        raise ValidationError({"lines": f"{where}: نسبةٌ غير رقميّة."}) from None
    if not rate.is_finite() or rate < 0 or rate > 100:
        raise ValidationError({"lines": f"{where}: النسبة بين 0 و100."})
    return rate.quantize(book_rates.RATE_QUANTUM), reason[:300]


def _assert_balanced(book, prepared, *, entry_date) -> None:
    """التوازنُ بحسب نوع الدفتر **في تاريخ الحركة** لا في تاريخ اليوم.

    المزدوجُ يتوازن والبسيطُ لا يُسأل — تعريفُ النوعين لا قاعدةً زائدة. وحركةٌ
    بتاريخٍ يسبق الانتقال تُقاس بالبسيط، وإلا رُفضت ورقٌ صحيحة.

    **والرسالةُ تسمّي الفرق** لا الطرفين وحدهما: «مدين 100 ودائن 90» يجعل
    المحاسبَ يطرح بنفسه، والفرقُ هو ما يبحث عنه.
    """
    if kind_on(book, entry_date) != BOOK_KIND_DOUBLE:
        return
    debit = sum(line["debit"] for line in prepared)
    credit = sum(line["credit"] for line in prepared)
    if debit != credit:
        raise ValidationError({
            "lines": (
                f"الحركة غير متوازنة: مدين {_amount(debit)} ودائن {_amount(credit)} — "
                f"الفرق {_amount(abs(debit - credit))}."
            ),
        })


def _documents_for(book, documents) -> list:
    """أوراقُ الحركة — تُقرأ **مقفولةً** و«حركةٌ حيّة واحدة» تُفرض هنا.

    `select_for_update` على صفوف الأوراق يُسلسل مُدخِلي الورقة نفسها: فحصٌ يقرأ
    ثم يكتب بلا قفلٍ يمرّ مرّتين تحت التزامن فتُدخل الورقةُ في حركتين. وتُستثنى
    الحركاتُ المعكوسة: عكسُ حركةٍ يُعيد أوراقها إلى «للإدخال» (د9).
    """
    wanted: list[int] = []
    for raw in documents or ():
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            raise ValidationError({"documents": "ورقة غير معروفة."}) from None
        if pk in wanted:
            raise ValidationError({"documents": "الورقة مكرَّرة في الطلب."})
        wanted.append(pk)
    if not wanted:
        return []
    rows = list(
        DocumentChecklistItem.objects
        .select_for_update()
        .filter(pk__in=wanted, client=book.client)
        .order_by("pk"),
    )
    if len(rows) != len(wanted):
        raise ValidationError({
            "documents": "لا ورقةَ بهذا المعرّف لهذا الزبون.",
        })
    if BookEntryDocument.objects.filter(
        document__in=rows, entry__in=_live_entries(),
    ).exists():
        raise ValidationError({
            "documents": "ورقةٌ مُدخلةٌ في حركةٍ حيّة — التصحيحُ حركةٌ عكسية.",
        })
    return rows


def create_entry(
    book, *, entry_date, kind, lines, memo="", documents=None,
    reverses=None, actor=None, day=None,
):
    """حركةٌ جديدة: رقمٌ مقفول، بنودٌ متوازنة، وأوراقٌ لا تُدخل مرّتين.

    **والافتتاحيُّ قيدٌ استثنائيّ بنوعِه لا بمسارٍ ثانٍ**: يُكتب من هنا نفسِه
    (ومنه يكتبه الاستيرادُ)، فيمرّ بالترقيم والقفل والتوازن كأيّ حركة، وتُضاف
    قاعدتاه وحدهما: لا ثانيَ له، ولا يُعاد بعد أوّل حركةٍ لاحقة. وعكسُ الافتتاحيّ
    يمرّ بالمسار نفسِه (`reverses` غير `None`) فلا يراه فحصُ «له افتتاحيٌّ بالفعل».
    """
    assert_book_writable(book, day)
    _assert_can_write_amounts(book, actor)
    if kind not in BOOK_ENTRY_KIND_LABELS:
        raise ValidationError({"kind": "نوع حركة غير معروف."})
    if not isinstance(entry_date, datetime.date):
        raise ValidationError({"entry_date": "تاريخ الحركة مطلوب بصيغة YYYY-MM-DD."})
    _assert_entry_writer(book, kind, actor)
    if kind == BOOK_ENTRY_KIND_OPENING:
        _assert_opening_unlocked(book)
        if reverses is None:
            _assert_no_live_opening(book)
    assert_period_open(book, entry_date)
    prepared = _prepare_lines(
        book.client,
        lines,
        # **والعكسُ مستثنى**: بنودُه منسوخةٌ عن الأصل بنسبها وسببها، فإطفاءُ
        # الإعداد بعد الحركة لا يجوز أن يمنع تصحيحَها — وإلا بقي القيدُ الفاسد
        # بلا طريقٍ يُردّ.
        allow_rate_override=bool(
            reverses is not None
            or services.resolve_setting(book.tenant, LINE_RATE_KEY, client=book.client)
        ),
    )
    # والعكسُ **غيرُ معفى**: يُقاس بنوع تاريخه كأيّ حركة. بتاريخ الأصل (الافتراض)
    # يُقاس بنوع عهد الأصل فيمرّ؛ ومؤرَّخاً في سنة المزدوج يُفحص بتوازنها، وإلا
    # كتب بنداً بطرفٍ واحد في سنةٍ مزدوجة فاختلّ ميزانُها.
    _assert_balanced(book, prepared, entry_date=entry_date)
    with transaction.atomic():
        attached = _documents_for(book, documents)
        number = _next_number(book.client, entry_date.year)
        entry = BookEntry.objects.create(
            client_book=book,
            client=book.client,
            year=entry_date.year,
            number=number,
            entry_date=entry_date,
            kind=kind,
            memo=(memo or "").strip()[:300],
            reverses=reverses,
            created_by=actor if getattr(actor, "pk", None) else None,
        )
        BookEntryLine.objects.bulk_create([
            BookEntryLine(
                # `bulk_create` لا يمرّ بـ`save()`، فشركةُ البند تُمرَّر صريحةً.
                tenant=entry.tenant,
                entry=entry,
                account=line["account"],
                debit=line["debit"],
                credit=line["credit"],
                tax_base=line["tax_base"],
                tax_amount=line["tax_amount"],
                vat_rate=line["vat_rate"],
                vat_rate_reason=line["vat_rate_reason"],
                side_party=line["side_party"],
            )
            for line in prepared
        ])
        if attached:
            BookEntryDocument.objects.bulk_create([
                BookEntryDocument(
                    tenant=entry.tenant, entry=entry, document=row,
                )
                for row in attached
            ])
    return entry


def reverse_entry(entry, *, memo="", entry_date=None, actor=None, day=None):
    """**التصحيحُ حركةٌ عكسية**: بنودٌ مدينُها دائنُ الأصل والعكس، والأصلُ يبقى.

    وتاريخُها تاريخُ الأصل افتراضاً: الزوجُ يتقاصّ في الفترة نفسها فلا يبقى أثرٌ
    في سنةٍ لم تقع فيها الحركة. والموظفُ يستطيع تأريخها غيره صراحةً، فتُقاس
    بنوع ذلك التاريخ: عكسُ حركةِ طرفٍ واحد مؤرَّخاً في سنة المزدوج 400.

    **ولا ترث أوراقَ الأصل**: الأصلُ يخرج من «حيّ» فتعود أوراقُه إلى «للإدخال»،
    وهي الحالةُ الصحيحة — قد يُعاد إدخالها بالحركة الصحيحة.

    **والأصلُ يُقفل قبل فحص «لها عكسٌ بالفعل»**: فحصٌ يقرأ ثم يكتب بلا قفلٍ يمرّ
    لطلبين متقاربين معاً فتُكتب حركتان عكسيّتان، ولا حذفَ يُصلحهما. صفُّ الأصل
    المقفول يُسلسل عاكسيه: الثاني ينتظر التزامَ الأوّل ثم يرى عكسَه فيردّ 400.
    والقفلُ أوّلُ قراءةٍ في المعاملة كي لا يُقرأ الفحصُ من لقطةٍ أقدم منه. وفرادةُ
    `reverses` (`OneToOneField`) طبقةٌ ثانية تُساند القفل لا تُبدله.
    """
    book = entry.client_book
    assert_book_writable(book, day)
    with transaction.atomic():
        entry = BookEntry.objects.select_for_update().get(pk=entry.pk)
        if entry.reverses_id is not None:
            raise ValidationError({
                "entry": "حركةٌ عكسية لا تُعكس — التصحيحُ حركةٌ جديدة على الأصل.",
            })
        if BookEntry.objects.filter(reverses=entry).exists():
            raise ValidationError({"entry": "لهذه الحركة حركةٌ عكسية بالفعل."})
        # الافتتاحيُّ يُقفل بأوّل حركةٍ لاحقة، فلا يُعكس بعدها: عكسُه إعادةُ كتابةِ
        # رصيدِ البداية بعد أن بُني عليه تاريخ — والقفلُ مرفوعٌ بعكس الحركة نفسِها.
        if entry.kind == BOOK_ENTRY_KIND_OPENING:
            _assert_opening_unlocked(book)
        lines = [
            {
                "account": line.account,
                "debit": line.credit,
                "credit": line.debit,
                "tax_base": line.tax_base,
                "tax_amount": line.tax_amount,
                # #287/٢: العكسُ يحمل نسبةَ الأصل وسببها — وإلا انقلب أثرُ الضريبة
                # على نسبة حسابٍ قد تكون تغيّرت، فلم يتقاصّ الزوجان.
                "vat_rate": line.vat_rate,
                "vat_rate_reason": line.vat_rate_reason,
                "side_party": line.side_party,
            }
            for line in entry.lines.select_related("account")
        ]
        return create_entry(
            book,
            entry_date=entry_date or entry.entry_date,
            kind=entry.kind,
            lines=lines,
            memo=memo or f"عكس الحركة رقم {entry.number}",
            reverses=entry,
            actor=actor,
            day=day,
        )


# ── توليدُ بنود الحركة من الورقة (#286/ج) ───────────────────────────────────
#
# **القرارُ المحسوم (2026-11-11):** «توليدُ بنود الحركة من مبلغ الورقة وضريبتها
# وطرفها»، والقيدُ اليدويُّ يبقى للتعديل. فالموظّفُ يكتب ما على الورقة — مبلغَها
# وضريبتَها وطرفَها — لا حساباً ولا رقماً، والحركةُ تُبنى هنا ثم تمرّ من
# `create_entry` وحدَه: القفلُ والترقيمُ والتوازنُ وتعليمُ «انأدخلت» في مسارٍ واحد.
#
# **والخريطةُ قرارٌ ثابتٌ لا اختيار**: الحسابُ يتبع نوعَ الورقة لا ذوقَ من يُدخل،
# وإلا قُرئ دفترُ زبونٍ واحد على قاعدتين في شهرٍ واحد فلم يُقارَن بميزان سنته.
ENTRY_KIND_ACCOUNTS: dict[str, tuple[str, str]] = {
    BOOK_ENTRY_KIND_SALES_INVOICE: ("1300", "4100"),    # مدين المدينون · دائن إيرادات المبيعات
    BOOK_ENTRY_KIND_PURCHASE_INVOICE: ("5200", "2100"), # مدين المشتريات · دائن الدائنون
    BOOK_ENTRY_KIND_EXPENSE: ("5100", "1100"),          # مدين مصاريف عامة · دائن الصندوق
    BOOK_ENTRY_KIND_BANK_MOVEMENT: ("1200", "1100"),    # مدين البنك · دائن الصندوق
    BOOK_ENTRY_KIND_DAILY_REPORT: ("1100", "4100"),      # مدين الصندوق · دائن إيرادات المبيعات
}

#: كودُ حساب ض.ق.م في شجرة الزبون — **يُقرأ منها ولا يُصطنع له صفّ**.
VAT_ACCOUNT_CODE = "2200"

#: حسابُ الصندوق في شجرة البسيط — يُكتب عليه سطرُ النقد: مدينٌ قبضاً للتقرير
#: اليومي ودائنٌ دفعاً للمصروف. وهو طرفُ `ENTRY_KIND_ACCOUNTS` لنوعيهما.
CASH_ACCOUNT_CODE = "1100"

#: الحسابان الذمّيان: الطرفُ المقابل يُكتب على سطرهما — اسمُ من عليه المال.
PARTY_ACCOUNT_CODES: frozenset[str] = frozenset({"1300", "2100"})

#: أنواعٌ ضريبتُها **مخرجات** (دائنٌ للضريبة): بيعٌ وتقريرٌ يوميّ. والمشترياتُ
#: والمصروفُ ضريبتُهما **مدخلات** (مدين) — والطرفُ المقابل للاتجاه يقرؤه هذا.
VAT_OUTPUT_KINDS: frozenset[str] = frozenset({
    BOOK_ENTRY_KIND_SALES_INVOICE, BOOK_ENTRY_KIND_DAILY_REPORT,
})

#: حقولُ مبلغ الورقة الأربعة (#286/ج) — ما يُكتب على الورقة قبل توليد بنودها.
#: و**`vat_rate` عليها وصفُ عرضٍ لا نسبةُ سطر**: نسبةُ السطر نسبةُ الخصم المعترف
#: بها (`book_rates.recognised_vat_rate`) وتأتي من الحساب — انظر `generate_entry_lines`.
DOCUMENT_VALUE_FIELDS: tuple[str, ...] = (
    "amount", "tax_amount", "vat_rate", "side_party",
)


def _entry_line(
    account_code, *, debit=0, credit=0, tax_base=0, tax_amount=0,
) -> dict:
    """بندُ حركةٍ بالشكل الذي يقرؤه `_prepare_lines` — **كوداً لا كائناً**.

    الحسابُ يبقى كوداً كي تمرّ الحركةُ كلُّها من `_prepare_lines`: حارسُ «لا
    حسابَ بهذا الكود» ومعه قناعُ المبالغ في موضعٍ واحدٍ، كما في القيد اليدوي.
    ولا نسبةَ على السطر هنا: مولّدُ الورق لا يكتب نسبةً أصلاً.
    """
    return {
        ACCOUNT_CODE_KEY: account_code,
        "debit": debit,
        "credit": credit,
        "tax_base": tax_base,
        "tax_amount": tax_amount,
        "side_party": "",
    }


def _paper_totals(paper) -> tuple[Decimal, Decimal]:
    """`(صافي، ضريبة)` من الورقة — **والمبلغُ الفارغ 400 يسمّي الورقة**.

    والإجماليُّ `amount + tax_amount` قاعدةٌ واحدةٌ تقرؤها هنا وفي الاختبارات،
    فلا يُجمع المبلغُ في موضعٍ ويُطرح في آخر.
    """
    if paper.amount is None:
        raise ValidationError({
            "documents": f"الورقة «{paper.name}» بلا مبلغ — اكتب مبلغها أوّلاً.",
        })
    amount = Decimal(paper.amount).quantize(Decimal("0.01"))
    tax = Decimal(paper.tax_amount or 0).quantize(Decimal("0.01"))
    if amount < 0 or tax < 0:
        raise ValidationError({
            "documents": f"الورقة «{paper.name}» بمبلغٍ سالب — صحّح مبلغها.",
        })
    return amount, tax


def _assert_vat_account(book) -> None:
    """حسابُ الضريبة موجودٌ في شجرة الزبون — وإلا 400 برسالته لا 500.

    الشجرةُ قابلةٌ للتحرير (`add_account`) ودفترٌ بلا `2200` لا يولّد سطرَ ضريبةٍ
    صامتاً: الرقمُ يقع على حسابٍ لا وجودَ له، و`_prepare_lines` وحدها لا تسمّي
    الحلَّ (تُضيف الحسابَ أو تُدخل الحركة يدوياً).
    """
    if ClientBookAccount.objects.filter(
        client=book.client, code=VAT_ACCOUNT_CODE,
    ).exists():
        return
    raise ValidationError({
        "documents": (
            f"لا حسابَ ضريبة ({VAT_ACCOUNT_CODE}) في شجرة الزبون — "
            "أضفه أو أدخل الحركة يدوياً."
        ),
    })


def _paper_tax_split(book, kind, tax, *, context=None) -> tuple[Decimal, Decimal]:
    """`(المعترف به، غير المخصوم)` من ضريبة ورقةٍ — أو صفران لما ليس مدخلات.

    مخرجاتُ الضريبة (بيعٌ وتقريرٌ يوميّ) لا تُخصم أصلاً: تُدفع كاملةً، فلا قسمةَ
    لها. ومدخلاتُها (شراءٌ ومصروف) تُخصم بنسبة الحساب — والقاعدةُ في
    `book_reports.paper_input_tax` وحدها، وليست نسخةً ثانية هنا.
    """
    none = (Decimal("0"), Decimal("0"))
    if not tax or kind in VAT_OUTPUT_KINDS:
        return none
    from accounting_office import book_reports

    debit_code, _credit_code = ENTRY_KIND_ACCOUNTS[kind]
    account = ClientBookAccount.objects.filter(
        tenant=book.tenant, client=book.client, code=debit_code,
    ).first()
    if account is None:
        # لا حسابَ للسطر أصلاً — `_prepare_lines` يردّ 400 قبل أن يُكتب شيء،
        # فلا معنى لقسمةٍ هنا؛ ولا نزيد كلفةً على حسابٍ لا وجودَ له.
        return tax, Decimal("0")
    return book_reports.paper_input_tax(
        book, account=account, tax_amount=tax, context=context,
    )


def _double_paper_lines(paper, kind, *, amount, tax, recognised) -> list[dict]:
    """بنودُ ورقةٍ في الدفتر المزدوج — **والضريبةُ على سطر الوعاء لا على سطرها**.

    مخرجاتُ الضريبة (بيعٌ وتقريرٌ يوميّ) دائنةٌ كالإيراد، فسطرُ الذمم/الصندوق
    يحمل الإجمالي مديناً؛ ومدخلاتُها (شراءٌ ومصروف) مدينةٌ كالمصروف، فيحمل سطرُ
    الذمم/الصندوق الإجمالي دائناً. **و`tax_base`/`tax_amount` على سطر الوعاء** —
    الإيراد للبيع والتقرير اليومي، والمشتريات/المصروف لغيرهما — **وسطرُ `2200`
    يحمل طرفَه وحده**.

    **والمعترفُ به وحده هو ما يُقيَّد على `2200`**: الضريبةُ المدخلةُ تُخصم بنسبة
    الحساب (`book_reports.paper_input_tax`)، والباقي **كلفةُ** الورقة فيزيد سطرُ
    المصروف/الأصل به — وإلا قُرئ «غيرُ مخصومٍ 56.67» في تقرير ض.ق.م ولم يظهر في
    حسابٍ واحد. والقيدُ يبقى متوازناً: مدينُ السطر زاد والدائنُ لم يتغيّر، والضريبةُ
    على `2200` نقصت بالمقدار نفسه. وحين لا يُعترف بشيءٍ لا سطرَ `2200` أصلاً
    (سطرٌ بصفرٍ يردّه `_prepare_lines`).

    والموضعُ هو القاعدةُ لا الذوق: `book_reports.vat_from_book` يجمع `tax_amount`
    من سطور الإيراد (مبيعات) ومن سطور الأصول والمصاريف (مدخلات) **ويتخطّى
    الخصوم**، فسطرُ ضريبةٍ على `2200` يجعل الإقرارَ صفراً أو سالباً. والضريبةُ
    **مرّةً واحدة**: مجموعُ `tax_amount` على السطور هو ضريبةُ الورقة، وتكرارُها
    على سطرين يُضاعف الإقرار.
    """
    debit_code, credit_code = ENTRY_KIND_ACCOUNTS[kind]
    total = amount + tax
    vat_line = None
    if not tax:
        debit_line = _entry_line(debit_code, debit=amount)
        credit_line = _entry_line(credit_code, credit=amount)
    elif kind in VAT_OUTPUT_KINDS:
        debit_line = _entry_line(debit_code, debit=total)
        credit_line = _entry_line(
            credit_code, credit=amount, tax_base=amount, tax_amount=tax,
        )
        vat_line = _entry_line(VAT_ACCOUNT_CODE, credit=tax)
    else:
        non_deductible = tax - recognised
        debit_line = _entry_line(
            debit_code,
            debit=amount + non_deductible,
            tax_base=amount,
            tax_amount=tax,
        )
        credit_line = _entry_line(credit_code, credit=total)
        if recognised:
            vat_line = _entry_line(VAT_ACCOUNT_CODE, debit=recognised)
    # الطرفُ على سطر الذمم إن كان أحد الطرفين ذمّياً، وإلا على سطر الإيراد/
    # المصروف. **ولا يُكتب على سطر الضريبة**: «ضريبةٌ على شركة كذا» قولٌ لا معنى له.
    side_line = credit_line if credit_code in PARTY_ACCOUNT_CODES else debit_line
    side_line["side_party"] = (paper.side_party or "").strip()[:200]
    other_line = debit_line if side_line is credit_line else credit_line
    lines = [side_line, other_line]
    if vat_line is not None:
        lines.append(vat_line)
    return lines


def _simple_paper_lines(kind, *, amount, tax, non_deductible=Decimal("0")) -> list[dict]:
    """الدفترُ البسيط: سطرٌ على **حساب طبيعته** وسطرُ نقدٍ لما قُبض أو دُفع.

    البيعُ والتقريرُ اليومي دائنان على الإيراد (`4100`)، والشراءُ والمصروفُ مدينان
    على مصروفهما (`5200`/`5100`) بصافيهما، والضريبةُ عليهما — لأن
    `book_reports._profit_rows` و`vat_from_book` يقرآن الدفترَ البسيط من حسابات
    الإيراد والمصروف. وسطرٌ على الصندوق **بدل** سطر الحساب كان **يمحو الإيرادَ**
    من الأرباح والخسائر ويقلب ذمّةَ الزبون في `_receivables` (مديناً `−117` لبيعٍ
    نُقد).

    **وسطرُ نقدٍ ثانٍ على `1100` بإجماليّ الورقة** (`amount + tax`): مدينٌ للتقرير
    اليومي (قبض) ودائنٌ للمصروف (دفع) — لأن `book_reports._cash_lines` يقرأ
    **الأصولَ وحدها**، فحركةٌ قبضت أو دفعت بلا سطرِ صندوق تُقرأ صفراً في تقرير
    القبض والدفع. **ولا يجعله مزدوجاً**: `_assert_balanced` لا تسأل البسيط أصلاً،
    فالتوازنُ بحسابين متقابلين تعريفُ المزدوج لا هذا السطر. وهو **بلا `tax_base`
    ولا `tax_amount`** (ضريبةُ السطر صفر فيتخطّاه `vat_from_book`) **وبلا طرفٍ**
    (فلا يدخل `_receivables`).

    **ويبقى طرفُه المقابل ناقصاً بمقدار الضريبة المعترف بها — عن قصد**: الضريبةُ
    هنا بياناتٌ على سطر الطبيعة لا سطرَ `2200` (وشجرةُ البسيط بلا `2200` أصلاً)،
    فبلا نسبةِ خصمٍ (100%) التقريرُ اليومي مدينُه 117 ودائنُه 100، والمصروفُ مدينُه
    200 ودائنُه 234؛ وبنسبة 2/3 يصير المصروفُ 1056.67 مقابل 1170 — والفرقُ في
    الحالين هو **المعترف به** من الضريبة لا خطأَ جمع.
    وسجلُّ البسيط أحاديٌّ لا مزدوج، فلا يُسأل عن التوازن — `_assert_balanced` تعود
    فوراً على غير المزدوج. ولا يُصلَح بسطر ضريبةٍ هنا: ذاك يجعل البسيط مزدوجاً
    باسمٍ آخر.

    **وغيرُ المخصوم من الضريبة يزيد المصروفَ/الأصلَ** (`non_deductible`): لا حسابَ
    التزامٍ في هذه الشجرة يُقيَّد عليه، وتركُه على سطر الطبيعة بلا مبلغه كان يجعل
    نتيجةَ الفترة أعلى من الكلفة الحقيقيّة بالضريبة غير المعترف بها.

    **والفاتورتان بلا سطر نقد**: قد لا تكونان مدفوعتين، فنقدُهما حركةٌ مستقلّة.

    **ولا طرفَ على سطر الحساب**: شجرةُ البسيط بلا حسابٍ ذمّي، فاسمُ طرفٍ على سطرٍ
    واحدٍ لا يعني ديناً — يُنشئ في `_receivables` ذمّةً وهمية على من دفع نقداً.

    وحركةُ البنك وحدها على البنك (`1200`) بإجماليها **بلا `tax_base`/`tax_amount`**:
    الضريبةُ عليها مرفوضةٌ أصلاً، فأساسٌ خاضعٌ عليها يُدخلها تقريرَ ض.ق.م بلا ضريبة.
    """
    debit_code, credit_code = ENTRY_KIND_ACCOUNTS[kind]
    if kind == BOOK_ENTRY_KIND_BANK_MOVEMENT:
        return [_entry_line(debit_code, debit=amount + tax)]
    if kind in VAT_OUTPUT_KINDS:
        natural = _entry_line(
            credit_code, credit=amount, tax_base=amount, tax_amount=tax,
        )
    else:
        natural = _entry_line(
            debit_code,
            debit=amount + non_deductible,
            tax_base=amount,
            tax_amount=tax,
        )
    total = amount + tax
    if kind == BOOK_ENTRY_KIND_DAILY_REPORT:
        return [natural, _entry_line(CASH_ACCOUNT_CODE, debit=total)]
    if kind == BOOK_ENTRY_KIND_EXPENSE:
        return [natural, _entry_line(CASH_ACCOUNT_CODE, credit=total)]
    return [natural]


def generate_entry_lines(book, *, kind, papers, entry_date) -> list[dict]:
    """بنودُ الحركة من أوراقها — **بلا حسابٍ ولا رقمٍ من الموظّف** (#286/ج).

    `papers` صفوفُ `DocumentChecklistItem` **مقروءةً تحت قفل** (يناديها المستدعي
    بعد `_documents_for`)، فيومَ التوليد لا يقرأ إلا ما سُلّم له.

    والنوعُ يقود: `manual` و`opening` ليسا من أنواع الورق — يُكتبان بيد إنسانٍ
    بدورٍ لا بمفتاح، فيُرفضان هنا بدل أن يُولَّد لهما حكمٌ لم يُقصد.

    **ونسبةُ الورقة (`paper.vat_rate`) لا تصل السطر**: حقلُ السطر نسبةُ الخصم
    المعترف بها، ونسبةُ الفاتورة وصفٌ للعرض — نسخُها كان يخصم 17٪ من ضريبة
    المدخلات وحدها فتنقص المستحقّةُ بلا أن يُعلَن ذلك.

    **وضريبةُ المدخلات تُقسم قسمين** (`_paper_tax_split`): المعترفُ به وحده على
    `2200` وغيرُ المخصوم كلفةً على سطر الطبيعة — فما يقوله تقريرُ ض.ق.م «غيرُ
    مخصوم» يظهر في حسابِه، لا رقماً معروضاً بلا أثر.
    """
    if kind not in ENTRY_KIND_ACCOUNTS:
        raise ValidationError({
            "kind": (
                "هذا النوع لا يُولَّد من الأوراق — القيدُ اليدويُّ والرصيدُ "
                "الافتتاحيُّ يُكتبان بأيديهما."
            ),
        })
    papers = list(papers)
    if not papers:
        raise ValidationError({"documents": "اختر ورقةً واحدة على الأقل."})
    double = kind_on(book, entry_date) == BOOK_KIND_DOUBLE
    vat_checked = False
    #: نظامُ الزبون الضريبيُّ ولائحةُ مكتبه — تُقرآن **مرّةً** للحركة ولو جاءت
    #: ثلاثين ورقة: لا يتغيّران بين أوراق الحركة الواحدة.
    split_context = None
    lines: list[dict] = []
    for paper in papers:
        amount, tax = _paper_totals(paper)
        if tax and kind == BOOK_ENTRY_KIND_BANK_MOVEMENT:
            raise ValidationError({
                "documents": "حركةُ بنكٍ بلا ضريبة — الضريبة على فاتورةٍ أو مصروف.",
            })
        if tax and split_context is None and kind not in VAT_OUTPUT_KINDS:
            from accounting_office import book_reports

            split_context = book_reports._vat_rate_context(book)
        if double:
            if tax and not vat_checked:
                _assert_vat_account(book)
                vat_checked = True
            recognised, _non_deductible = _paper_tax_split(
                book, kind, tax, context=split_context,
            )
            lines.extend(
                _double_paper_lines(
                    paper, kind, amount=amount, tax=tax, recognised=recognised,
                ),
            )
        else:
            _recognised, non_deductible = _paper_tax_split(
                book, kind, tax, context=split_context,
            )
            lines.extend(
                _simple_paper_lines(
                    kind, amount=amount, tax=tax, non_deductible=non_deductible,
                ),
            )
    return lines


def _document_live_entry(row):
    """الحركةُ الحيّةُ التي أُدخلت فيها الورقة — واحدةٌ على الأكثر (د9)."""
    return _live_entries().filter(documents__document=row).first()


def _document_amount_value(value, field):
    """مبلغُ ورقةٍ من الـAPI — `None` يُفرّغ، والسالبُ 400 لا صفرٌ صامت."""
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (ArithmeticError, TypeError, ValueError):
        raise ValidationError({field: "مبلغٌ غير رقميّ."}) from None
    if amount < 0:
        raise ValidationError({field: "مبلغٌ سالب — صحّح الورقة."})
    return amount


def _document_rate_value(value):
    """نسبةُ الورقة كما تُكتب — بين 0 و100 كسطر الحركة."""
    if value in (None, ""):
        return None
    try:
        rate = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        raise ValidationError({"vat_rate": "نسبةٌ غير رقميّة."}) from None
    if not rate.is_finite() or rate < 0 or rate > 100:
        raise ValidationError({"vat_rate": "النسبة بين 0 و100."})
    return rate.quantize(book_rates.RATE_QUANTUM)


def set_document_amounts(row, data, *, actor=None) -> DocumentChecklistItem:
    """مبلغُ ورقةٍ وضريبتُها ونسبتُها وطرفُها — **الواردُ منها وحده**.

    والغيابُ لا يُفرّغ: طلبٌ يغيّر الحالةَ وحدها لا يمحو مبلغَ ورقةٍ قُرئت،
    كـ`update_settings`. و`None` الصريحُ يُفرّغ (تصحيحُ قراءةٍ خاطئة).

    **وورقةٌ أُدخلت في حركةٍ حيّة لا تُعدَّل مبالغها**: حركتُها تحمل أرقامَها في
    الدفتر، وتعديلُ الورقة بعدها يترك الدفترَ يقول غيرَ ما تقوله ورقته — والتصحيحُ
    حركةٌ عكسية ثم إعادةُ إدخال. والطرفُ والنسبةُ وصفٌ لا يُغيَّر به رقم.
    """
    sent = {
        key: value for key, value in (data or {}).items()
        if key in DOCUMENT_VALUE_FIELDS
    }
    if not sent:
        return row
    if any(key in services.AMOUNT_KEYS for key in sent):
        _assert_tenant_can_write_amounts(row.tenant, actor)
        if _document_live_entry(row) is not None:
            raise ValidationError({
                "amount": (
                    "ورقةٌ مُدخَلةٌ في حركةٍ حيّة — لا تُعدَّل مبالغها. "
                    "التصحيحُ حركةٌ عكسية ثم إعادةُ الإدخال."
                ),
            })
    fields = []
    for key, value in sent.items():
        if key in ("amount", "tax_amount"):
            value = _document_amount_value(value, key)
        elif key == "vat_rate":
            value = _document_rate_value(value)
        else:
            value = (value or "").strip()[:200]
        setattr(row, key, value)
        fields.append(key)
    row.updated_by = actor if getattr(actor, "pk", None) else None
    row.save(update_fields=[*fields, "updated_by", "updated_at"])
    return row


def document_values_payload(row, *, masked) -> dict:
    """حقولُ مبلغ الورقة كما تخرج — **والقناعُ قرارٌ جاهزٌ يُمرَّر**.

    المبلغان يمرّان بـ`services.mask_amounts` (مفتاحاهما في `AMOUNT_KEYS`)،
    والنسبةُ والطرفُ يبقيان: نسبةٌ واسمٌ لا مال، وإخفاؤهما يترك الحارسَ بلا وجه.
    والفراغُ `None` لا `"0.00"`: ورقةٌ بلا مبلغٍ ليست ورقةً بمبلغ صفر.
    """
    payload = {
        "amount": None if row.amount is None else _amount(row.amount),
        "tax_amount": None if row.tax_amount is None else _amount(row.tax_amount),
        "vat_rate": (
            None if row.vat_rate is None
            else str(Decimal(row.vat_rate).quantize(book_rates.RATE_QUANTUM))
        ),
        "side_party": row.side_party,
    }
    return services.mask_amounts(payload) if masked else payload


def create_entry_from_documents(
    book, *, kind, documents, entry_date=None, memo="", actor=None, day=None,
):
    """حركةٌ من أوراقٍ وصلت: التوليدُ هنا والكتابةُ في `create_entry` وحدَه.

    **حركةٌ واحدةٌ لشهرٍ واحد**: الأوراقُ من أشهرٍ مختلفة تُرفض 400 — إدخالُ
    الشهر شهراً هو ما يقارنه المحاسبُ بإقراره، وحركةٌ تجمع يناير وفبراير تُخرج
    تاريخاً لا يطابق ورقةً واحدة. والتاريخُ افتراضاً `period_end` لذلك الشهر،
    ويجوز صريحاً لمن يُدخل ورقةً متأخّرة.

    والكتابةُ تبقى في `create_entry`: القفلُ والترقيمُ والتوازنُ وتعليمُ «انأدخلت»
    تمرّ من مسارٍ واحد، فلا تفترق نسختان من قواعد الحركة.
    """
    assert_book_writable(book, day)
    _assert_can_write_amounts(book, actor)
    if kind not in ENTRY_KIND_ACCOUNTS:
        raise ValidationError({
            "kind": (
                "هذا النوع لا يُولَّد من الأوراق — القيدُ اليدويُّ والرصيدُ "
                "الافتتاحيُّ يُكتبان بأيديهما."
            ),
        })
    _assert_entry_writer(book, kind, actor)
    with transaction.atomic():
        papers = _documents_for(book, documents)
        if not papers:
            raise ValidationError({"documents": "اختر ورقةً واحدة على الأقل."})
        if len({paper.period_start for paper in papers}) > 1:
            raise ValidationError({
                "documents": "أوراقٌ من أشهرٍ مختلفة — إدخالُ شهرٍ شهراً.",
            })
        entry_date = entry_date or papers[0].period_end
        lines = generate_entry_lines(
            book, kind=kind, papers=papers, entry_date=entry_date,
        )
        return create_entry(
            book,
            entry_date=entry_date,
            kind=kind,
            lines=lines,
            memo=memo,
            documents=[paper.pk for paper in papers],
            actor=actor,
            day=day,
        )


# ── نوعُ الدفتر وانتقالُه (د7) ─────────────────────────────────────────────
def change_kind(book, kind, *, day=None):
    """من البسيط إلى المزدوج **من بداية سنةٍ**: لا في سنة الفتح ولا مع حركاتٍ فيها.

    والرجوعُ مرفوضٌ دائماً: إسقاطُ الطرف المقابل من تاريخٍ كامل ليس تبسيطاً.
    """
    day = day or _today()
    assert_book_writable(book, day)
    if kind not in BOOK_KIND_LABELS:
        raise ValidationError({"kind": "نوع دفتر غير معروف."})
    if kind == book.kind:
        raise ValidationError({"kind": "الدفتر من هذا النوع أصلاً."})
    if book.kind == BOOK_KIND_DOUBLE and kind == BOOK_KIND_SIMPLE:
        raise ValidationError({
            "kind": "الرجوعُ من المزدوج إلى البسيط مرفوض — طرفٌ من كل حركةٍ لا يُمحى.",
        })
    if book.opened_on.year == day.year:
        raise ValidationError({
            "kind": "لا يُغيَّر النوع في سنة فتح الدفتر — يُغيَّر من بداية سنة تالية.",
        })
    if BookEntry.objects.filter(client=book.client, year=day.year).exists():
        raise ValidationError({
            "kind": "في السنة الجارية حركات — يُغيَّر النوع من بداية سنةٍ نظيفة.",
        })
    with transaction.atomic():
        book.kind = kind
        book.kind_changed_on = day
        book.save(update_fields=["kind", "kind_changed_on"])
        # **وتُضاف شجرةُ النوع الجديد في المعاملة نفسها**: بلا هذا يبقى الدفتر
        # المحوَّل بلا 2000/2100/2200/3000/5300، فأوّلُ بندِ ضريبةٍ أو آجل يُرفض.
        sync_client_tree(book.client, kind)
    return book


# ── «للإدخال»: مشتقٌّ لا مخزَّن (د8/د9) ─────────────────────────────────────
def pending_entry_payload(tenant, user, *, day=None) -> dict:
    """أوراقٌ واصلةٌ **بلا حركةٍ حيّة**، مجمَّعةً بالزبون والشهر.

    **عدٌّ باستعلامٍ واحد**: `Exists` على رابط `BookEntryDocument` في `WHERE`،
    والتجميعُ `TruncMonth` على بداية الفترة. ولا عمودَ «انأدخلت» — الورقةُ تخرج
    من القائمة لأن الشرطَ نفسه صار كاذباً، لا لأن أحداً كتب حالة (د9). وتُستثنى
    الحركاتُ المعكوسة: عكسُ حركةٍ يُعيد أوراقها إلى «للإدخال».

    **ودفاترُ الخدمة الموقوفة لا تظهر**: كلُّ إدخالٍ لها 400، فبقاؤها في القائمة
    يعني قائمةً لا تُصفَّر أبداً. و`writable_client_ids` استعلامٌ واحد ثابت لا
    يكبر بعدد الصفوف.

    ولسانُ الحال: الزبائنُ يزدادون والاستعلاماتُ لا — الأسماءُ وطريقةُ الإدخال
    تُقرأ بنداءين ثابتين لا بنداءٍ لكل صفّ.
    """
    day = day or _today()
    active = writable_client_ids(tenant, services.visible_clients(tenant, user), day)
    if not active:
        return {"rows": [], "total": 0}
    booked = ClientBook.objects.filter(tenant=tenant).values("client_id")
    entered = BookEntryDocument.objects.filter(
        document=OuterRef("pk"), entry__in=_live_entries(),
    )
    grouped = list(
        DocumentChecklistItem.objects
        .filter(
            tenant=tenant,
            client_id__in=active,
            status=DOCUMENT_STATUS_RECEIVED,
        )
        .filter(client_id__in=booked)
        .annotate(month=TruncMonth("period_start"))
        .filter(~Exists(entered))
        .values("client_id", "month")
        .annotate(count=Count("id"))
        .order_by("client_id", "month"),
    )
    if not grouped:
        return {"rows": [], "total": 0}
    client_ids = {row["client_id"] for row in grouped}
    client_rows = OfficeClient.objects.filter(pk__in=client_ids)
    names = dict(client_rows.values_list("pk", "name"))
    methods = services.resolve_setting_for_clients(tenant, ENTRY_METHOD_KEY, client_rows)
    rows = [
        {
            "client_id": row["client_id"],
            "client_name": names.get(row["client_id"], ""),
            "month": row["month"].strftime("%Y-%m"),
            "month_label": MONTH_LABELS[row["month"].month - 1],
            "count": row["count"],
            "entry_method": methods.get(row["client_id"]),
            "entry_method_label": BOOK_ENTRY_METHOD_LABELS.get(
                methods.get(row["client_id"]), "",
            ),
        }
        for row in grouped
    ]
    return {"rows": rows, "total": sum(row["count"] for row in rows)}


# ── أقفالُ الفترات (#287/٥) ─────────────────────────────────────────────────
#
# **القفلُ عن الفترة لا عن المستند**: التزامُ ق.م وتزامُنُ التزامٍ آخر في الشهر
# نفسه يُقفلان الفترةَ مرّةً واحدة (`UniqueConstraint` على الدفتر والفترة)، فسؤالُ
# «هل هذا اليوم مقفل؟» استعلامٌ واحدٌ على مدى الفترة.
#
# **ولا يمنع القفلُ القراءةَ**: الحركةُ بتاريخٍ داخل الفترة المفتوحة تُرفض 400
# برسالةٍ مسمّاة، والتقاريرُ والميزانياتُ تقرأ كلَّ شيء. والفتحُ لا يمحو الصفّ:
# يكتب من فتح ومتى ولماذا، فيبقى أثرُ الاستثناء.
def _closed_lock(book, entry_date):
    """قفلٌ سارٍ يغطّي التاريخ — أو `None`.

    الشرطُ `unlocked_on__isnull=True` في `WHERE`: صفٌّ مفتوحٌ لا يمنع شيئاً، ويبقى
    للقراءة في سجلّ الفترات.
    """
    return (
        BookPeriodLock.objects
        .filter(
            client_book=book,
            unlocked_on__isnull=True,
            period_start__lte=entry_date,
            period_end__gte=entry_date,
        )
        .order_by("period_start")
        .first()
    )


def assert_period_open(book, entry_date) -> None:
    """إدخالٌ داخل فترةٍ مقفلة **400 برسالةٍ تسمّي الفترة وطريقَ الفتح**.

    والرسالةُ تقول من يفتح بالسبب: `ENTRY_APPROVER_ROLES` وحدهم — كالقيد اليدويّ.
    """
    lock = _closed_lock(book, entry_date)
    if lock is None:
        return
    raise ValidationError({
        "entry_date": (
            f"فترة الدفتر {lock.period_start.isoformat()} ← "
            f"{lock.period_end.isoformat()} مقفلة — لا يُدخل فيها قيد. "
            "يفتحها المديرُ أو صاحب المكتب بسببٍ مسجَّل."
        ),
    })


def lock_period(book, *, period_start, period_end, actor=None, obligation=None,
                day=None):
    """قفلُ فترةٍ — **قفلٌ نشطٌ واحدٌ للفترة، يُعاد القائمُ منه (لا تكرار)**.

    الفحصُ والكتابةُ في معاملةٍ واحدةٍ تحت `select_for_update` على **الدفتر**:
    تقديمُ التزامين في الشهر نفسه (ق.م ورواتب) يُسلسَل، فلا يُنشأ قفلان نشطان.
    و`unlocked_on__isnull=True` في الفحص: الصفُّ المفتوحُ **سجلُّ أثرٍ لا قفل**،
    وهو الفرقُ الذي جعل `get_or_create` على (الدفتر، البداية، النهاية) يُعيد
    الصفَّ المفتوحَ بعد فتحٍ فلا يعود القفلُ أبداً. والقيدُ الشرطيُّ
    (`UniqueConstraint(condition=…)`) بديلٌ غيرُ مدعومٍ في MySQL 8.4 — الإنتاج —
    فحُذف القيدُ على الثلاثة وبقي الحكمُ هنا (انظر `models.BookPeriodLock`).
    """
    day = day or _today()
    if period_start > period_end:
        raise ValidationError({"period_start": "بدايةُ الفترة بعد نهايتها."})
    with transaction.atomic():
        # أوّلُ قراءةٍ في المعاملة: من سبقنا كتب قبلها، لا لقطةً أقدم منها.
        book = ClientBook.objects.select_for_update().get(
            pk=book.pk, tenant=book.tenant,
        )
        active = (
            book.period_locks
            .filter(
                period_start=period_start,
                period_end=period_end,
                unlocked_on__isnull=True,
            )
            .order_by("pk")
            .first()
        )
        if active is not None:
            return active
        return BookPeriodLock.objects.create(
            client_book=book,
            tenant=book.tenant,
            period_start=period_start,
            period_end=period_end,
            locked_on=day,
            locked_by=actor if getattr(actor, "pk", None) else None,
            obligation=obligation,
        )


def close_period_on_submit(obligation, *, actor=None, day=None):
    """«انقدّم» يقفل فترةَ الدفتر — **حين يكون الإعدادُ مفعّلاً وثمّة دفتر**.

    وغيابُ الدفتر أو إطفاءُ الإعداد لا يُسقط التقديم: القفلُ أثرٌ جانبيّ للقرار لا
    شرطٌ له، وإلا صار تقديمُ التزامٍ يُرفض لأن دفتراً غيرُ مسكوك.
    """
    from accounting_office import services as office_services

    client = obligation.client
    if not office_services.resolve_setting(
        client.tenant, CLOSE_ON_SUBMIT_KEY, client=client,
    ):
        return None
    book = ClientBook.objects.filter(client=client).first()
    if book is None:
        return None
    return lock_period(
        book,
        period_start=obligation.period_start,
        period_end=obligation.period_end,
        actor=actor,
        obligation=obligation,
        day=day,
    )


def reopen_period(lock, *, reason, actor, day=None) -> BookPeriodLock:
    """فتحُ فترةٍ مقفلة — **بدورِ المدير/صاحب المكتب وبسببٍ مكتوب**.

    والفتحُ المتكرّر 400: صفٌّ مفتوحٌ لا معنى لفتحه، والثاني كان يكتب سبباً فوق
    سببٍ محا أثرَ الأوّل.
    """
    if lock.unlocked_on is not None:
        raise ValidationError({"period": "الفترةُ مفتوحةٌ بالفعل."})
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({
            "reason": "سببُ فتح الفترة مطلوب — يُسجَّل مع من فتحها.",
        })
    if actor is not None and user_tenant_role(actor, lock.tenant) not in ENTRY_APPROVER_ROLES:
        raise PermissionDenied(
            "لا يفتح فترةً مقفلةً إلا المديرُ وصاحبُ المكتب — بسببٍ مسجَّل.",
        )
    lock.unlocked_on = day or _today()
    lock.unlocked_by = actor if getattr(actor, "pk", None) else None
    lock.unlock_reason = reason[:300]
    lock.save(update_fields=["unlocked_on", "unlocked_by", "unlock_reason"])
    return lock


def period_row(lock) -> dict:
    return {
        "id": lock.pk,
        "period_start": lock.period_start.isoformat(),
        "period_end": lock.period_end.isoformat(),
        "locked_on": lock.locked_on.isoformat(),
        "locked_by": (
            services.user_display_name(lock.locked_by) if lock.locked_by_id else ""
        ),
        "unlocked_on": (
            None if lock.unlocked_on is None else lock.unlocked_on.isoformat()
        ),
        "unlocked_by": (
            services.user_display_name(lock.unlocked_by) if lock.unlocked_by_id else ""
        ),
        "unlock_reason": lock.unlock_reason,
        "is_open": lock.is_open,
        "obligation": lock.obligation_id,
    }


def periods_payload(book) -> list[dict]:
    """أقفالُ الدفتر — الأحدثُ أوّلاً، والمفتوحُ يبقى في السجلّ بأثره."""
    return [
        period_row(lock)
        for lock in book.period_locks.select_related(
            "locked_by", "unlocked_by",
        ).order_by("-period_end", "-id")
    ]


# ── نسبُ حساب الزبون (#287/٢ و٣) ────────────────────────────────────────────
#: علامةُ «الحقلُ لم يُرسَل» في `set_account_rates`: الوجودُ يُقرأ **بحضور المفتاح**
#: لا بأنّ قيمته ليست `None` — والـ`None` الصريحُ يُفرّغ النسبة.
_NOT_GIVEN = object()


def set_account_rates(account, *, tenant, rate_category=_NOT_GIVEN,
                      vat_rate=_NOT_GIVEN, income_tax_rate=_NOT_GIVEN,
                      depreciation_rate=_NOT_GIVEN):
    """كتابةُ تصنيفِ حسابٍ ونسبه — الحقولُ **المُرسَلة** وحدها (كـ`update_settings`).

    والقيمةُ `None` تُفرّغ النسبةَ الصريحة فيعود الحسابُ إلى اللائحة/الافتراض.
    والشرطُ حضورُ المفتاح لا `if value is not None`: ذاك كان يجعل `{"vat_rate":
    null}` صامتاً فلا طريقَ لإرجاع حسابٍ إلى اللائحة، وهو ما يعد به المُسلسِل.
    """
    touched = []
    kwargs = {}
    for name, value in (
        ("rate_category", rate_category),
        ("vat_rate", vat_rate),
        ("income_tax_rate", income_tax_rate),
        ("depreciation_rate", depreciation_rate),
    ):
        if value is _NOT_GIVEN:
            continue
        touched.append(name)
        kwargs[name] = value
    if not touched:
        return account
    return book_rates.update_account_rates(
        account, tenant=tenant, fields=touched, **kwargs,
    )
