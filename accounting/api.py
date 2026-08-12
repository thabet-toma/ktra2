"""الواجهة العامة الوحيدة لموديول المحاسبة — accounting facade (المرحلة 2).

كل إنشاء أو عكس قيود، وكل إنشاء/ربط حسابات من خارج `accounting`، يمرّ من هنا.
الـapps الأخرى تستورد من `accounting.api` فقط — لا من `accounting.models`
ولا من داخليات `accounting.services` (القراءات التقريرية القائمة مؤجّلة لواجهة
قراءة لاحقة — انظر docs/DEPENDENCIES.md §5).

هذه الوحدة لا تعيد كتابة منطق الترحيل: `post_document` يفوّض إلى
`services.post_journal`، و`reverse_journal` ينقل نمط «القيد العكسي اليدوي»
الذي كان منسوخاً في logistics إلى موضع واحد داخل accounting **بنفس سلوكه
حرفياً** (المرحلة 2 = صفر تغيير سلوك — انظر docs/REFACTOR_PROMPTS.md).
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Account, JournalHeader, JournalLine
from .services import (
    post_journal,
    unpost_document,
    validate_fiscal_period,
)
from django.utils import timezone

logger = logging.getLogger(__name__)

__all__ = [
    "post_document",
    "reverse_journal",
    "unpost_document",
    "purge_journals",
    "get_account_by_code",
    "ensure_partner_account",
    "sync_partner_accounting",
    "create_partner_opening_balance",
]


# ─────────────────────────────────────────────────────────
#  القيود
# ─────────────────────────────────────────────────────────

def post_document(
    *,
    tenant_id: int,
    transaction_date,
    reference_type: str,
    reference_id: int | None,
    description: str,
    lines_data: list[dict],
    currency=None,
    exchange_rate=Decimal("1"),
    user=None,
    idempotent: bool = True,
    branch_id: int | None = None,
) -> JournalHeader:
    """إنشاء + ترحيل قيد مستند — تفويض مباشر لـ`services.post_journal`.

    الضمانات (تفرضها `post_journal` داخل معاملة ذرّية واحدة):
    - فترة مالية مفتوحة + حرّاس الفترة الضريبية.
    - توازن دقيق (debit == credit بعد quantize('0.01')) ورفض القيد الصفري.
    - كل الأسطر تابعة لنفس الشركة (شريك/مركز تكلفة من شركة أخرى يُرفض).
    - idempotency عبر (tenant, reference_type, reference_id) مع
      `select_for_update` ضد السباق — الاستدعاء الثاني يعيد القيد الموجود.
    - إنفاذ طبيعة الحساب (مدين فقط/دائن فقط).

    lines_data: قائمة dicts بمفاتيح `account` (id) و`debit`/`credit`
    واختيارياً `partner` و`cost_center` و`description`.
    تُرجع JournalHeader مرحّلاً (is_posted=True).
    """
    return post_journal(
        tenant_id=tenant_id,
        transaction_date=transaction_date,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        lines_data=lines_data,
        currency=currency,
        exchange_rate=exchange_rate,
        user=user,
        idempotent=idempotent,
        branch_id=branch_id,
    )


def reverse_journal(
    original: JournalHeader,
    *,
    reference_type: str,
    reference_id: int,
    description: str,
    transaction_date=None,
    line_description_prefix: str | None = None,
    copy_currency: bool = False,
    copy_project: bool = False,
    unpost_original: bool = False,
) -> JournalHeader:
    """إنشاء قيد عكسي مرحّل لقيد مرحّل قائم (قلب مدين/دائن سطراً بسطر).

    ذرّية: كل شيء داخل `transaction.atomic` مع `select_for_update` على القيد
    الأصلي. الدالة **ليست idempotent عمداً** — كل استدعاء ينشئ قيداً عكسياً
    جديداً (المستند قد يُرحَّل ويُعكَس أكثر من مرة، فمرجع العكس يتكرر مشروعاً).
    حارس إعادة الدخول مسؤولية المستدعي (مثل فحص `is_posted` على المستند).

    - `copy_currency=True` ينسخ عملة الأصل وسعر صرفه إلى القيد العكسي؛
      الافتراضي يترك العملة فارغة والسعر 1 (سلوك مسار دفعات الصفقات القائم).
    - `copy_project=True` ينسخ `project_id` لكل سطر.
    - `unpost_original=True` يخفّض `is_posted` على الأصلي عبر `.update()`
      — التجاوز الوحيد المشروع لغارد `JournalHeader.save` الذي يمنع تعديل
      قيد مرحّل — ويذيّل وصفه بوسم `[ملغى ترحيل — عكس مرحّل #{id}]`.

    ترمي `ValidationError` إن كان الأصل غير مرحّل أو بلا أسطر أو غير متوازن
    (سماحية 0.02)، و`RuntimeError` إن فشل توازن العكس بعد الإنشاء.

    قرار 2026-08-11: العكس **معفى عمداً من فحص طبيعة الحساب**
    (debit_only/credit_only) — قلب الأطراف يعني أن حساباً «مدين فقط» سيستقبل
    دائناً في العكس، وفرض الفحص كان سيجعل قيوداً مشروعة غير قابلة للعكس.
    """
    if transaction_date is None:
        transaction_date = timezone.localdate()

    with transaction.atomic():
        orig = (
            JournalHeader.objects.select_for_update()
            .select_related("tenant")
            .prefetch_related("lines")
            .get(pk=original.pk)
        )

        if not orig.is_posted:
            raise ValidationError(
                f"القيد #{orig.id} غير مرحّل — لا يوجد ما يُعكس."
            )

        lines = list(orig.lines.all())
        if not lines:
            raise ValidationError("القيد الأصلي بلا أسطر — لا يمكن إنشاء عكس آمن.")

        tenant = orig.tenant
        tid = getattr(tenant, "pk", None) if tenant is not None else None
        validate_fiscal_period(tid if tid is not None else 0, transaction_date)

        sum_dr = sum(Decimal(str(l.debit or 0)) for l in lines)
        sum_cr = sum(Decimal(str(l.credit or 0)) for l in lines)
        if abs(sum_dr - sum_cr) > Decimal("0.02"):
            raise ValidationError(
                f"القيد الأصلي غير متوازن (مدين {sum_dr} ≠ دائن {sum_cr}) "
                f"— راجع القيد #{orig.id}."
            )

        prefix = (
            line_description_prefix
            if line_description_prefix is not None
            else f"عكس قيد #{orig.id}: "
        )

        header_kwargs = dict(
            tenant=tenant,
            transaction_date=transaction_date,
            description=(description or "")[:500],
            reference_type=reference_type,
            reference_id=reference_id,
            is_posted=True,
        )
        if copy_currency:
            header_kwargs["currency"] = orig.currency
            header_kwargs["exchange_rate"] = orig.exchange_rate
        rev = JournalHeader.objects.create(**header_kwargs)

        for line in lines:
            line_kwargs = dict(
                tenant=line.tenant,
                journal=rev,
                account=line.account,
                debit=line.credit or 0,
                credit=line.debit or 0,
                partner=line.partner,
                cost_center=line.cost_center,
                description=(f"{prefix}{line.description or ''}")[:500],
            )
            if copy_project:
                line_kwargs["project_id"] = line.project_id
            JournalLine.objects.create(**line_kwargs)

        rev_sum_dr = sum(
            Decimal(str(x.debit or 0))
            for x in JournalLine.objects.filter(journal=rev)
        )
        rev_sum_cr = sum(
            Decimal(str(x.credit or 0))
            for x in JournalLine.objects.filter(journal=rev)
        )
        if abs(rev_sum_dr - rev_sum_cr) > Decimal("0.02"):
            raise RuntimeError(
                f"فشل التحقق من توازن القيد العكسي: مدين {rev_sum_dr} دائن {rev_sum_cr}"
            )

        if unpost_original:
            orig_desc = (orig.description or "").strip()
            tag = f" [ملغى ترحيل — عكس مرحّل #{rev.id}]"
            new_desc = (
                (orig_desc + tag)[:500] if tag.strip() not in orig_desc else orig_desc
            )
            JournalHeader.objects.filter(pk=orig.pk).update(
                is_posted=False,
                description=new_desc,
            )

        logger.info(
            "reverse_journal: orig=%s rev=%s type=%s ref_id=%s unpost_original=%s",
            orig.id, rev.id, reference_type, reference_id, unpost_original,
        )

    return rev


def purge_journals(journal_ids) -> int:
    """حذف نهائي لقيود بمعرّفاتها (أسطرها أولاً ثم الرؤوس) — بلا قيود عكسية.

    مخصص لمسارات التطهير الإدارية (مثل `purge_deals`) حيث يُراد محو المستند
    وقيوده كأن لم يكونا — ليس بديلاً عن `unpost_document` (الذي يحصر النطاق
    بمرجع المستند ويعيد حركات المخزون). المستدعي مسؤول عن تصفير أي FKs
    تشير للقيود قبل الحذف.
    """
    ids = set(journal_ids or ())
    if not ids:
        return 0
    JournalLine.objects.filter(journal_id__in=ids).delete()
    cnt, _ = JournalHeader.objects.filter(pk__in=ids).delete()
    return int(cnt)


# ─────────────────────────────────────────────────────────
#  الحسابات
# ─────────────────────────────────────────────────────────

def get_account_by_code(tenant, code: str, *, active_only: bool = False) -> Optional[Account]:
    """حساب الشركة بالكود، أو None — بديل موحّد عن استيراد `Account` مباشرة.

    `tenant` يقبل كائن Tenant أو معرّفه. `active_only=True` يقصر على الفعّالة.
    لا ينشئ شيئاً — الإنشاء له دوال مخصصة (مثل `resolve_import_expense_account`
    في services).
    """
    qs = Account.objects.filter(tenant=tenant, code=code)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.first()


# ─────────────────────────────────────────────────────────
#  حسابات الشركاء والقيد الافتتاحي
#  (منقول حرفياً من partners/signals.py — المرحلة 2-ج؛ صفر تغيير سلوك.
#   أكواد الآباء المعيارية محفوظة بالضبط: 2101/1103/2106-2109 و3300.)
# ─────────────────────────────────────────────────────────

def _normalize_account_name(value: str) -> str:
    """اسم مُطبَّع للمقارنة: بلا فراغات زائدة، بلا حساسية لحالة الأحرف."""
    return " ".join(str(value or "").split()).strip().casefold()


def _expected_parent_code_for_partner_type(partner_type: str) -> str | None:
    # task13 M2: الأكواد القديمة 2102/2103/2104 كانت قروضاً/مستحقات/ضريبة مخرجات
    # في الشجرة المعيارية — حسابات الشركاء صارت تحت آباء ذمم مخصصين.
    return {
        "Supplier": "2101",          # الدائنون التجاريون
        "Customer": "1103",          # المدينون التجاريون
        "FreightForwarder": "2106",  # ذمم وكلاء الشحن
        "CustomsBroker": "2107",     # ذمم المخلصين الجمركيين
        "LocalTransporter": "2108",  # ذمم النقل المحلي
        "Carrier": "2109",           # ذمم الناقلين
    }.get(partner_type)


def sync_partner_accounting(partner) -> None:
    """مزامنة الجانب المحاسبي للشريك بعد حفظه (يستدعيه signal الـpost_save).

    1. إنشاء/ربط حساب الشريك تحت الأب المعياري لنوعه (أو أب مجموعته).
    2. مزامنة اسم الحساب مع اسم الشريك، وأبيه مع نوعه إن تغيّرا.
    3. إنشاء قيد الرصيد الافتتاحي مرة واحدة (مرجع PARTNER_OPENING/partner.id).

    الأخطاء تُسجَّل ولا تُرمى — فشل المحاسبة لا يُسقط حفظ الشريك
    (نفس عقد الـsignal الأصلي).
    """
    from partners.models import Partner

    # 1. Automatic Account Creation
    if not partner.linked_account:
        # Tenant must come from the partner itself — never guess a company.
        tenant = partner.tenant
        if not tenant:
            logger.error(
                "sync_partner_accounting: partner id=%s has no tenant — skipping account creation",
                partner.id,
            )
            return

        parent_acc = None
        expected_parent_code = _expected_parent_code_for_partner_type(
            partner.partner_type
        )

        # 1. Try to get Parent from Partner Group
        if partner.group:
            if partner.partner_type == 'Customer':
                parent_acc = partner.group.account_receivable
            else:  # Supplier, FreightForwarder, CustomsBroker, LocalTransporter
                parent_acc = partner.group.account_payable

        # 2. Enforce canonical parent mapping per partner type
        # This ensures that FreightForwarder/CustomsBroker/LocalTransporter
        # don't accidentally end up under a generic group.account_payable.
        if expected_parent_code:
            try:
                expected_parent = Account.objects.get(
                    code=expected_parent_code, tenant=tenant
                )
                if not parent_acc or getattr(parent_acc, "code", None) != expected_parent_code:
                    parent_acc = expected_parent
            except Account.DoesNotExist:
                # If expected parent doesn't exist yet, we fall back to group.
                pass

        # 3. Final fallback (legacy support): if we still don't have a parent, try to fetch by expected code.
        if not parent_acc and expected_parent_code:
            try:
                parent_acc = Account.objects.get(code=expected_parent_code, tenant=tenant)
            except Account.DoesNotExist:
                parent_acc = None

        if parent_acc:
            try:
                # قد يكون بند الشجرة (مثل مخلّص جمركي أو ناقل محلي) قد أُنشئ يدوياً
                # في الشجرة قبل وجود سجل شريك له — نربطه بدل تكرار حساب جديد.
                target_name = _normalize_account_name(partner.name)
                existing_account = None
                if target_name:
                    for acc in Account.objects.filter(tenant=tenant, parent=parent_acc):
                        if _normalize_account_name(acc.name) != target_name:
                            continue
                        if Partner.objects.filter(linked_account=acc).exclude(pk=partner.pk).exists():
                            continue
                        existing_account = acc
                        break

                if existing_account:
                    partner_account = existing_account
                else:
                    # Generate unique code: ParentCode + PartnerID (padded)
                    new_code = f"{parent_acc.code}{str(partner.id).zfill(4)}"

                    # Use get_or_create
                    partner_account, acc_created = Account.objects.get_or_create(
                        tenant=tenant,
                        code=new_code,
                        defaults={
                            'name': partner.name,
                            'account_type': parent_acc.account_type,
                            'parent': parent_acc,
                            'is_active': True
                        }
                    )

                partner.linked_account = partner_account
                partner.save(update_fields=['linked_account'])
            except Exception:
                logger.exception(
                    "Error creating account for partner id=%s", partner.id
                )

    # 3. Dynamic Sync: Update account name if partner name changed
    elif partner.linked_account and partner.linked_account.name != partner.name:
        partner.linked_account.name = partner.name
        partner.linked_account.save(update_fields=['name'])

    # 4. Dynamic Sync: Update account parent if partner type changed
    # (Checking if the current parent matches the expected parent based on type)
    if partner.linked_account:
        expected_parent_code = _expected_parent_code_for_partner_type(
            partner.partner_type
        )

        if expected_parent_code and (not partner.linked_account.parent or partner.linked_account.parent.code != expected_parent_code):
            try:
                new_parent = Account.objects.get(code=expected_parent_code, tenant=partner.tenant)
                partner.linked_account.parent = new_parent
                partner.linked_account.account_type = new_parent.account_type
                partner.linked_account.save(update_fields=['parent', 'account_type'])
            except Account.DoesNotExist:
                pass

    # 2. Opening Balance Journal Entry
    if partner.opening_balance and partner.opening_balance > 0 and partner.linked_account:
        exists = JournalHeader.objects.filter(
            tenant=partner.tenant,
            reference_type='PARTNER_OPENING',
            reference_id=partner.id
        ).exists()

        if not exists:
            create_partner_opening_balance(partner)


def ensure_partner_account(partner):
    """يضمن وجود حساب محاسبي مربوط بالشريك (مورد / وكيل شحن / …).

    يُستدعى قبل ترحيل دفعات لوجستيات حتى لا يضطر المستخدم لربط الحساب يدوياً.
    التنفيذ عبر `partner.save()` كي يمرّ من نفس مسار post_save الموحّد
    (إنشاء الحساب + المزامنة + القيد الافتتاحي) بلا منطق مكرر.
    """
    if partner is None or partner.pk is None:
        return partner
    if partner.linked_account_id:
        return partner
    try:
        partner.save()
        partner.refresh_from_db()
    except Exception:
        logger.exception(
            "ensure_partner_account failed for partner id=%s", partner.pk
        )
    return partner


def create_partner_opening_balance(partner) -> None:
    """قيد الرصيد الافتتاحي للشريك: طرفه حساب الشريك وقابله «3300 أرصدة افتتاحية».

    عميل ⇒ مدين على حسابه / دائن على 3300؛ غير العميل ⇒ العكس.
    يُنشئ 3300 تحت جذر حقوق الملكية «3» إن لم يوجد.

    قرار 2026-08-11 (معالجة ديون المرحلة 2): يمرّ عبر `post_journal` فيكسب
    فحص الفترة المالية والتوازن وaudit log وidempotency ذرّية على المرجع
    (PARTNER_OPENING, partner.id) — فحص `exists` غير المقفول في الـsignal لم
    يعد الحامي الوحيد من التكرار تحت السباق.
    فشل الترحيل (مثل فترة مقفلة/غائبة عند تاريخ الرصيد) يُسجَّل ولا يُرمى —
    حفظ الشريك لا يسقط بسبب المحاسبة (عقد الـsignal الأصلي)؛ تصحيح التاريخ
    وإعادة حفظ الشريك يعيدان المحاولة.
    """
    try:
        tenant = partner.tenant
        if not tenant:
            logger.error(
                "create_partner_opening_balance: partner id=%s has no tenant — skipping",
                partner.id,
            )
            return

        opening_offset_account = Account.objects.filter(tenant=tenant, code='3300').first()
        if not opening_offset_account:
            equity_root = Account.objects.filter(tenant=tenant, code='3').first()
            if equity_root:
                opening_offset_account = Account.objects.create(
                    tenant=tenant,
                    code='3300',
                    name='أرصدة افتتاحية (Opening Balances)',
                    account_type='Equity',
                    parent=equity_root,
                    is_active=True
                )

        if not opening_offset_account:
            return

        date = partner.opening_balance_date or timezone.localdate()
        amount = Decimal(str(partner.opening_balance))
        description = f"Opening Balance for {partner.name}"
        partner_line = {
            'account': partner.linked_account_id,
            'partner': partner.id,
            'description': description,
        }
        offset_line = {'account': opening_offset_account.id, 'description': description}
        if partner.partner_type == 'Customer':
            partner_line.update(debit=amount, credit=Decimal('0'))
            offset_line.update(debit=Decimal('0'), credit=amount)
            lines_data = [partner_line, offset_line]
        else:
            offset_line.update(debit=amount, credit=Decimal('0'))
            partner_line.update(debit=Decimal('0'), credit=amount)
            lines_data = [offset_line, partner_line]

        post_journal(
            tenant_id=tenant.pk,
            transaction_date=date,
            reference_type='PARTNER_OPENING',
            reference_id=partner.id,
            description=description,
            lines_data=lines_data,
        )

    except Exception:
        logger.exception("Failed to create opening balance for partner id=%s", partner.id)
