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
"""
import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.db.models.functions import TruncMonth
from django.utils import timezone

from accounting_office import services
from accounting_office.deadlines import MONTH_LABELS
from accounting_office.models import (
    BOOK_ACCOUNT_TYPE_LABELS,
    BOOK_ENTRY_KIND_LABELS,
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
    ClientBook,
    ClientBookAccount,
    ClientBookSequence,
    ClientService,
    DocumentChecklistItem,
    OfficeBookAccount,
    OfficeClient,
)
from accounting_office.settings_registry import BOOK_ENTRY_METHOD_LABELS

#: مفتاحُ إعداد طريقة الإدخال (د10) — يُقرأ بالمحلّل، والافتراضُ «ورقة ورقة».
ENTRY_METHOD_KEY = "book_entry_method"

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


def book_is_writable(book, day=None) -> bool:
    return bookkeeping_service_on(book.client, day or _today()) is not None


def assert_book_writable(book, day=None) -> None:
    """الكتابةُ على دفتر زبونٍ خدمتُه موقوفة 400 — والدفترُ يبقى للقراءة."""
    if not book_is_writable(book, day):
        raise ValidationError({
            "client": (
                "خدمة مسك الدفاتر موقوفة لهذا الزبون — الدفتر للقراءة فقط."
            ),
        })


def writable_client_ids(tenant, clients, day) -> set[int]:
    """الزبائن الذين خدمتُهم نشطة — **استعلامٌ واحد** لقائمةٍ كاملة.

    بدل `book_is_writable` لكل دفتر: القائمةُ تقرأ من هنا، والمفردُ يسأل الدالة
    المفردة. والقاعدةُ واحدةٌ في الاثنين (`status_on`).
    """
    active: set[int] = set()
    for row in ClientService.objects.filter(
        tenant=tenant,
        service__code=SERVICE_CODE_BOOKKEEPING,
        client__in=clients,
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
        "entry_method": entry_method,
        "entry_method_label": BOOK_ENTRY_METHOD_LABELS.get(entry_method, ""),
        "writable": writable,
    }


def account_row(row) -> dict:
    return {
        "code": row.code,
        "name": row.name,
        "parent_code": row.parent.code if row.parent_id else None,
        "account_type": row.account_type,
        "account_type_label": BOOK_ACCOUNT_TYPE_LABELS.get(
            row.account_type, row.account_type,
        ),
        "is_system": row.is_system,
        "is_active": row.is_active,
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
                "side_party": line.side_party,
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


def accounts_payload(client) -> list[dict]:
    rows = (
        ClientBookAccount.objects
        .filter(client=client)
        .select_related("parent")
        .order_by("code", "id")
    )
    return [account_row(row) for row in rows]


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
        )
        ensure_client_tree(client, kind)
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
def _assert_can_write_amounts(book, actor) -> None:
    """من لا يرى المبالغ لا يكتبها — **403 لا 400**، كعقد الموديول.

    الحركةُ مبلغٌ بيد من يكتبها: عضوٌ بلا `office.amounts.view` لا يكتب رقماً لا
    يراه، ولا يصحّح بحركةٍ عكسية رقماً لا يقرؤه. و`actor=None` نداءٌ داخليّ.
    و`PermissionDenied` تحوّلها DRF إلى 403 كما يفعل `reject_amount_writes` في
    الـviews — 400 كان يقول «حمولتُك فاسدة» عن صلاحيةٍ ناقصة.
    """
    if actor is None or services.can_see_amounts(book.tenant, actor):
        return
    raise PermissionDenied(
        "صلاحية «يرى المبالغ» غير ممنوحة لدورك — لا تكتب مبلغاً لا تراه.",
    )


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


def _prepare_lines(client, lines) -> list[dict]:
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
        if debit < 0 or credit < 0:
            raise ValidationError({"lines": f"{where}: مبلغٌ سالب — اعكس الطرف."})
        if debit == 0 and credit == 0:
            raise ValidationError({"lines": f"{where}: لا مدينَ ولا دائن."})
        if debit and credit:
            raise ValidationError({
                "lines": f"{where}: طرفٌ واحد لكل بند — مدينٌ أو دائن لا الاثنان.",
            })
        prepared.append({
            "account": account,
            "debit": debit,
            "credit": credit,
            "side_party": (raw.get("side_party") or "").strip()[:200],
        })
    return prepared


def _assert_balanced(book, prepared, *, entry_date) -> None:
    """التوازنُ بحسب نوع الدفتر **في تاريخ الحركة** لا في تاريخ اليوم.

    المزدوجُ يتوازن والبسيطُ لا يُسأل — تعريفُ النوعين لا قاعدةً زائدة. وحركةٌ
    بتاريخٍ يسبق الانتقال تُقاس بالبسيط، وإلا رُفضت ورقٌ صحيحة.
    """
    if kind_on(book, entry_date) != BOOK_KIND_DOUBLE:
        return
    debit = sum(line["debit"] for line in prepared)
    credit = sum(line["credit"] for line in prepared)
    if debit != credit:
        raise ValidationError({
            "lines": f"الحركة غير متوازنة: مدين {_amount(debit)} ودائن {_amount(credit)}.",
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
    """حركةٌ جديدة: رقمٌ مقفول، بنودٌ متوازنة، وأوراقٌ لا تُدخل مرّتين."""
    assert_book_writable(book, day)
    _assert_can_write_amounts(book, actor)
    if kind not in BOOK_ENTRY_KIND_LABELS:
        raise ValidationError({"kind": "نوع حركة غير معروف."})
    if not isinstance(entry_date, datetime.date):
        raise ValidationError({"entry_date": "تاريخ الحركة مطلوب بصيغة YYYY-MM-DD."})
    prepared = _prepare_lines(book.client, lines)
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
        lines = [
            {
                "account": line.account,
                "debit": line.credit,
                "credit": line.debit,
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
