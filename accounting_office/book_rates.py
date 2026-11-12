"""نسبُ مصاريف دفتر الزبون (#287/١ و٢) — اللائحة، وتجاوزُ المكتب، ونسبةُ الحساب.

**ثلاثُ طبقاتٍ لا واحدة، وكلٌّ لها سببُها:**

1. **لائحةُ المنصّة** (`BookExpenseRate`): صفٌّ لكل قيمة — ض.ق.م وضريبةُ الدخل
   والإهلاك — بمصدره ومستوى دليلِه وتاريخ سريانه وعلامة «راجع». **بياناتٌ لا
   ثوابت**: التشريعان يُعدَّلان، ورقمٌ مكتوبٌ في الكود يكذب في السنة التالية.
2. **تجاوزُ المكتب** (`OfficeBookExpenseRate`): قيمةٌ واحدة تتجاوز اللائحة،
   **بسجلّ إلحاقيّ** (`BookExpenseRateChange`) — لا تعديلَ صامت ولا نسخةَ كاملةٍ
   تفترق بصمت.
3. **نسبةُ الحساب** (`ClientBookAccount`): صريحةٌ إن كتبها المكتب، وإلا المقروءُ
   من الطبقتين. والافتراضُ 100% للنسبتين حين لا تصنيفَ ولا نصّ — نصُّ التذكرة
   («افتراضُهما 100% أو من اللائحة»).

**و«راجع» لا يُستعمل**: صفٌّ `needs_review` أو بلا قيمةٍ يُقرأ `None` في الحساب
ويُعلَن `needs_review` في الحمولة — فلا يُخصم بندٌ بنسبةٍ لم يؤكّدها أحد، ولا
تُملأ خانةٌ بشجاعةِ الصمت. وهذا هو الفرق بين `None` و`0`: الصفرُ نسبةٌ مُثبتة
(ضيافةٌ فلسطينية 0%)، والفراغُ «لا نعلم بعد».
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting_office.models import (
    RATE_EVIDENCE_LABELS,
    RATE_KIND_DEPRECIATION,
    RATE_KIND_INCOME,
    RATE_KIND_LABELS,
    RATE_KIND_VAT,
    BookExpenseRate,
    BookExpenseRateChange,
    ClientBookAccount,
    OfficeBookExpenseRate,
)

#: الافتراضُ حين لا تصنيفَ ولا نصّ — **للنسبتين وحدهما**، لا للإهلاك: أصلٌ بلا
#: فئةٍ لا نسبةَ إهلاكٍ له، و100% إهلاكاً في سنةٍ تُمحيه ثمناً لا سياسة.
DEFAULT_RATE = Decimal("100")

#: مصدرُ القيمة المقروءة — يُرسَل للواجهة فتعرض «من اللائحة» أو «مكتبي».
SOURCE_ACCOUNT = "account"
SOURCE_OFFICE = "office"
SOURCE_PLATFORM = "platform"
SOURCE_DEFAULT = "default"
SOURCE_AVAILABLE: tuple[str, ...] = (
    SOURCE_ACCOUNT, SOURCE_OFFICE, SOURCE_PLATFORM, SOURCE_DEFAULT,
)
SOURCE_LABELS: dict[str, str] = {
    SOURCE_ACCOUNT: "على الحساب",
    SOURCE_OFFICE: "لائحة المكتب",
    SOURCE_PLATFORM: "لائحة المنصّة",
    SOURCE_DEFAULT: "الافتراضي",
}

RATE_QUANTUM = Decimal("0.0001")


def _decimal_rate(value) -> Decimal | None:
    """نسبةٌ بخاناتٍ أربع — أو 400 برسالةٍ تسمّي النسبة."""
    if value in (None, ""):
        return None
    try:
        rate = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        raise ValidationError({"rate": "نسبةٌ غير رقميّة."}) from None
    if not rate.is_finite() or rate < 0 or rate > 100:
        raise ValidationError({"rate": "النسبة بين 0 و100."})
    return rate.quantize(RATE_QUANTUM)


def _text(rate) -> str | None:
    """النسبةُ نصّاً بخاناتٍ أربع — شكلُ الخروج الواحد (كـ`client_books._amount`)."""
    return None if rate is None else str(Decimal(rate).quantize(RATE_QUANTUM))


# ── القراءة: اللائحة ثم التجاوز ─────────────────────────────────────────────
def platform_rows(tax_system) -> list[BookExpenseRate]:
    return list(
        BookExpenseRate.objects
        .filter(tax_system=tax_system)
        .order_by("code", "rate_kind"),
    )


def office_override_map(tenant, tax_system) -> dict[tuple[str, str], OfficeBookExpenseRate]:
    """تجاوزاتُ المكتب مفهرسةً بمفتاحها — استعلامٌ واحد لكل تصنيفات النظام."""
    return {
        (row.code, row.rate_kind): row
        for row in OfficeBookExpenseRate.objects.filter(
            tenant=tenant, tax_system=tax_system,
        )
    }


def effective_row(tenant, tax_system, code, rate_kind, *, overrides=None) -> dict:
    """**القيمةُ السارية** لتصنيفٍ ونوعِ نسبة، ومصدرُها وعلامتُها.

    تُقرأ في استعلامٍ واحد لمجموعة تصنيفات حين يُمرَّر `overrides`
    (`office_override_map`) — قائمةُ اللائحة تحتاج كلَّ صفوفها بلا استعلامٍ لكل صفّ.

    و`usable` هو الحكمُ الوحيد على «هل تُستعمل في حساب»: قيمةٌ موجودةٌ **و** ليست
    «راجع». وما دون ذلك يُعرض ولا يُحسب.
    """
    code = (code or "").strip()
    if not code:
        return _empty_row(rate_kind)
    if overrides is not None:
        own = overrides.get((code, rate_kind))
        platform = BookExpenseRate.objects.filter(
            tax_system=tax_system, code=code, rate_kind=rate_kind,
        ).first()
    else:
        own = OfficeBookExpenseRate.objects.filter(
            tenant=tenant, tax_system=tax_system, code=code, rate_kind=rate_kind,
        ).first()
        platform = BookExpenseRate.objects.filter(
            tax_system=tax_system, code=code, rate_kind=rate_kind,
        ).first()
    if platform is None and own is None:
        return _empty_row(rate_kind)
    base = platform or own
    rate = own.rate if own is not None else platform.rate
    needs_review = (
        own.needs_review if own is not None else platform.needs_review
    )
    return {
        "code": code,
        "rate_kind": rate_kind,
        "rate_kind_label": RATE_KIND_LABELS.get(rate_kind, rate_kind),
        "label": base.label,
        "rate": _text(rate),
        # «راجع» أو قيمةٌ غائبة ⇒ لا تُستعمل: القيمةُ الغائبةُ ليست صفراً.
        "needs_review": bool(needs_review or rate is None),
        "usable": rate is not None and not needs_review,
        "source": SOURCE_OFFICE if own is not None else SOURCE_PLATFORM,
        "source_label": SOURCE_LABELS[SOURCE_OFFICE if own is not None else SOURCE_PLATFORM],
        "evidence": platform.evidence if platform is not None else "",
        "evidence_label": RATE_EVIDENCE_LABELS.get(
            platform.evidence, "",
        ) if platform is not None else "",
        "source_note": platform.source if platform is not None else "",
        "effective_from": (
            platform.effective_from.isoformat() if platform is not None else None
        ),
    }


def _empty_row(rate_kind) -> dict:
    """تصنيفٌ غير معروفٍ أو فراغُه — **شكلٌ ثابتٌ** لا مفتاحٌ غائب."""
    return {
        "code": "",
        "rate_kind": rate_kind,
        "rate_kind_label": RATE_KIND_LABELS.get(rate_kind, rate_kind),
        "label": "",
        "rate": None,
        "needs_review": True,
        "usable": False,
        "source": "",
        "source_label": "",
        "evidence": "",
        "evidence_label": "",
        "source_note": "",
        "effective_from": None,
    }


def rates_payload(tenant, tax_system) -> dict:
    """`GET client-books/rates/` — اللائحةُ كاملةً للنظام المطلوب.

    صفٌّ لكل قيمةٍ مع مصدره ودليله وتاريخ سريانه و«راجع»، وتحته تجاوزُ المكتب إن
    وُجد (`rate` السارية و`source` يقول من أين). والتصنيفُ الواحد ثلاثةُ صفوف —
    نسبةُ ض.ق.م ونسبةُ الضريبة والإهلاك — لأن لكلٍّ نصَّه.
    """
    overrides = office_override_map(tenant, tax_system)
    rows = [
        {
            **effective_row(
                tenant, tax_system, row.code, row.rate_kind, overrides=overrides,
            ),
            "evidence": row.evidence,
            "evidence_label": RATE_EVIDENCE_LABELS.get(row.evidence, row.evidence),
            "source_note": row.source,
            "effective_from": row.effective_from.isoformat(),
        }
        for row in platform_rows(tax_system)
    ]
    return {
        "tax_system": tax_system,
        "rate_kinds": [
            {"value": value, "label": label} for value, label in RATE_KIND_LABELS.items()
        ],
        "rows": rows,
        "review_count": sum(1 for row in rows if row["needs_review"]),
    }


def rates_payload_for_client(tenant, client) -> dict:
    """اللائحةُ بنظام الزبون الفعليّ — لا بمعاملٍ يُخمَّن في الواجهة."""
    from accounting_office import services

    system = services.resolve_setting(tenant, services.TAX_SYSTEM_KEY, client=client)
    return rates_payload(tenant, system)


# ── الكتابة: تجاوزُ المكتب بسجلّ ────────────────────────────────────────────
def _snapshot(rate, needs_review) -> dict:
    return {"rate": _text(rate), "needs_review": bool(needs_review)}


def set_office_rate(
    tenant, *, tax_system, code, rate_kind, rate, needs_review, reason, actor=None,
) -> OfficeBookExpenseRate:
    """تعديلُ المكتب على لائحة المنصّة — **وسببٌ ملزمٌ وسجلٌّ إلحاقيّ**.

    لا `get_or_create` بلا سجلّ: الصفُّ يُكتب واللقطةُ تُضاف في المعاملة نفسها،
    فحالةُ «تغيّرت النسبة» و«لماذا» تُقرآن معاً أو لا تُكتبان. وسببٌ فارغ ⇒ 400:
    تعديلُ نسبةٍ على دفتر زبونٍ بلا سببٍ مكتوبٍ أثرٌ لا يُفسَّر لاحقاً.
    """
    code = (code or "").strip()
    if not code:
        raise ValidationError({"code": "كود التصنيف مطلوب."})
    if rate_kind not in RATE_KIND_LABELS:
        raise ValidationError({"rate_kind": "نوع نسبة غير معروف."})
    platform = BookExpenseRate.objects.filter(
        tax_system=tax_system, code=code, rate_kind=rate_kind,
    ).first()
    if platform is None:
        raise ValidationError({
            "code": "لا تصنيفَ بهذا الكود في لائحة المنصّة لهذا النظام.",
        })
    clean = _decimal_rate(rate)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({
            "reason": "سببُ تعديل النسبة مطلوب — يُسجَّل مع التغيير.",
        })
    with transaction.atomic():
        row, created = OfficeBookExpenseRate.objects.get_or_create(
            tenant=tenant,
            tax_system=tax_system,
            code=code,
            rate_kind=rate_kind,
            defaults={"rate": clean, "needs_review": bool(needs_review)},
        )
        before = _snapshot(
            platform.rate if created else row.rate,
            platform.needs_review if created else row.needs_review,
        )
        if not created:
            row.rate = clean
            row.needs_review = bool(needs_review)
            row.updated_by = actor if getattr(actor, "pk", None) else None
            row.save(update_fields=["rate", "needs_review", "updated_by", "updated_at"])
        else:
            row.updated_by = actor if getattr(actor, "pk", None) else None
            row.save(update_fields=["updated_by", "updated_at"])
        BookExpenseRateChange.objects.create(
            tenant=tenant,
            tax_system=tax_system,
            code=code,
            rate_kind=rate_kind,
            before=before,
            after=_snapshot(clean, needs_review),
            reason=reason[:300],
            changed_by=actor if getattr(actor, "pk", None) else None,
        )
    return row


# ── الحساب: نسبةُ حسابٍ واحد ────────────────────────────────────────────────
def account_rate(account, rate_kind, *, tenant, tax_system, overrides=None) -> dict:
    """القيمةُ السارية لحساب: الصريحةُ عليه، وإلا اللائحة، وإلا الافتراض.

    **والإهلاكُ لا افتراضَ له**: أصلٌ بلا فئةٍ ولا نسبةٍ يُقرأ `None` و«راجع»،
    فلا إهلاكَ مُصطنَعاً بنسبةٍ لم يكتبها أحد.
    """
    explicit = {
        RATE_KIND_VAT: account.vat_rate,
        RATE_KIND_INCOME: account.income_tax_rate,
        RATE_KIND_DEPRECIATION: account.depreciation_rate,
    }.get(rate_kind)
    if explicit is not None:
        return {
            **effective_row(
                tenant, tax_system, account.rate_category or "", rate_kind,
                overrides=overrides,
            ),
            "rate": _text(explicit),
            "needs_review": False,
            "usable": True,
            "source": SOURCE_ACCOUNT,
            "source_label": SOURCE_LABELS[SOURCE_ACCOUNT],
        }
    row = effective_row(
        tenant, tax_system, account.rate_category or "", rate_kind,
        overrides=overrides,
    )
    if row["code"]:
        return row
    if rate_kind == RATE_KIND_DEPRECIATION:
        return {**row, "needs_review": True, "usable": False}
    return {
        **row,
        "rate": _text(DEFAULT_RATE),
        "needs_review": False,
        "usable": True,
        "source": SOURCE_DEFAULT,
        "source_label": SOURCE_LABELS[SOURCE_DEFAULT],
    }


def account_rows(account, *, tenant, tax_system, overrides=None) -> dict[str, dict]:
    """النسبُ الثلاث لحساب — الشكلُ الذي يقرؤه سطرُ الشجرة والحسابات."""
    return {
        kind: account_rate(
            account, kind, tenant=tenant, tax_system=tax_system, overrides=overrides,
        )
        for kind in (RATE_KIND_VAT, RATE_KIND_INCOME, RATE_KIND_DEPRECIATION)
    }


def update_account_rates(
    account, *, tenant, rate_category="", vat_rate=None, income_tax_rate=None,
    depreciation_rate=None, fields=None,
):
    """كتابةُ تصنيفِ الحساب ونسبه — **الحقولُ المذكورةُ وحدها** كـ`update_settings`.

    و`rate_category` يُتحقَّق أنّه كودٌ في لائحة نظام الزبون: كودٌ مخترَعٌ يبقى
    بلا لائحةٍ فيقرأ الحسابُ الافتراضَ صامتاً، وهو عكسُ ما يُراد.
    """
    from accounting_office import services

    system = services.resolve_setting(tenant, services.TAX_SYSTEM_KEY, client=account.client)
    touched = []
    if "rate_category" in (fields or ()):
        code = (rate_category or "").strip()
        if code and not BookExpenseRate.objects.filter(
            tax_system=system, code=code,
        ).exists():
            raise ValidationError({
                "rate_category": "لا تصنيفَ بهذا الكود في لائحة هذا النظام.",
            })
        account.rate_category = code
        touched.append("rate_category")
    for name, value in (
        ("vat_rate", vat_rate),
        ("income_tax_rate", income_tax_rate),
        ("depreciation_rate", depreciation_rate),
    ):
        if name in (fields or ()):
            setattr(account, name, _decimal_rate(value))
            touched.append(name)
    if touched:
        account.save(update_fields=touched)
    return account


def recognised_vat_rate(line, *, tenant, tax_system, overrides=None) -> tuple[Decimal, bool]:
    """نسبةُ ض.ق.م المعترف بها لسطرٍ — `(النسبة، راجع؟)`.

    سطرٌ كتب نصبته صريحةً (`line.vat_rate`) يغلب؛ وإلا نسبةُ حسابه. والمراجَعُ
    يعود `(0, True)`: **لا تُستعمل قيمتُه**، ومجموعُ المدخلات يُحتسب بلا هذا السطر
    ويُعلَن أن العدد ناقصٌ حتى يؤكّد المكتب.
    """
    if line.vat_rate is not None:
        return _decimal_rate(line.vat_rate) or Decimal("0"), False
    row = account_rate(
        line.account, RATE_KIND_VAT, tenant=tenant, tax_system=tax_system,
        overrides=overrides,
    )
    if not row["usable"]:
        return Decimal("0"), True
    return Decimal(row["rate"]), False
