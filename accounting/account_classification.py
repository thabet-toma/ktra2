"""التصنيف الوظيفي للحساب (`Account.sub_type`) — اشتقاقه مرة واحدة وتخزينه.

`account_type` خمسة أنواع تقود التقارير والطبيعة والحساب الختامي — وهي لا تكفي
لمعرفة **غرض** الحساب: «الصندوق» و«ذمم العملاء» و«المخزون» كلها «أصل». فكانت كل
شاشة تخمّن الصندوق ببادئة الرقم أو باسم الحساب، وثلاث شاشات وصلت إلى ثلاث
إجابات مختلفة لنفس الحقل. الجواب يُخزَّن هنا مرة واحدة، ويُشتقّ بترتيب حجّية
صارم:

1. **الروابط التي ينشئها الخادم نفسه** — `BankAccount.account` و
   `CashBoxLedgerAccount.account` و`Partner.linked_account`. هذه ليست تخميناً:
   الخادم هو من أنشأ الحساب لهذا الغرض بعينه.
2. **سلالة الشجرة المعيارية** — 1101/1110 نقدية، 1102 بنوك، 1103 مدينون،
   1104 مخزون. الأقرب في السلالة يفوز، ولا تُكسر شركةٌ شجرتُها غير معيارية:
   غياب الجذر يعني ببساطة أن هذه الخطوة لا تجيب.
3. **اسم الحساب** — آخر الحلول، ومقصور على الأصول: «عمولات بنكية» مصروف لا بنك.

خطوة لاحقة لا تنقض جواب خطوة سابقة، والكتابة لا تلمس حساباً له تصنيف بالفعل —
فالتصحيح اليدوي من بطاقة الحساب يبقى أقوى من أي اشتقاق، وإعادة التشغيل آمنة.
"""
import re

SUB_TYPE_CASH_BOX = 'cash_box'
SUB_TYPE_BANK = 'bank'
SUB_TYPE_RECEIVABLE = 'receivable'
SUB_TYPE_PAYABLE = 'payable'
SUB_TYPE_INVENTORY = 'inventory'

SUB_TYPE_CHOICES = [
    (SUB_TYPE_CASH_BOX, 'صندوق نقدية'),
    (SUB_TYPE_BANK, 'حساب بنكي'),
    (SUB_TYPE_RECEIVABLE, 'ذمم مدينة'),
    (SUB_TYPE_PAYABLE, 'ذمم دائنة'),
    (SUB_TYPE_INVENTORY, 'مخزون'),
]

# جذور الشجرة المعيارية (tenants/services.py: COA_DATA) — الأطول أولاً عند
# مطابقة البادئة حتى لا يبتلع جذرٌ أقصر ما ليس له.
ROOT_SUB_TYPES = {
    '1101': SUB_TYPE_CASH_BOX,   # النقدية
    '1110': SUB_TYPE_CASH_BOX,   # صناديق النقدية
    '1102': SUB_TYPE_BANK,       # البنوك
    '1103': SUB_TYPE_RECEIVABLE,  # المدينون التجاريون
    '1104': SUB_TYPE_INVENTORY,  # المخزون
    # آباء ذمم الأطراف — نفس الخريطة التي يعمل بها
    # `accounting.api._expected_parent_code_for_partner_type`. بدونها كان
    # التصنيف يأتي من رابط الطرف وحده، فحساب الدائنين نفسه (وأي حساب يُنشأ
    # تحته يدوياً) يبقى بلا تصنيف.
    '2101': SUB_TYPE_PAYABLE,    # الدائنون التجاريون
    '2106': SUB_TYPE_PAYABLE,    # ذمم وكلاء الشحن
    '2107': SUB_TYPE_PAYABLE,    # ذمم المخلصين الجمركيين
    '2108': SUB_TYPE_PAYABLE,    # ذمم النقل المحلي
    '2109': SUB_TYPE_PAYABLE,    # ذمم الناقلين
}
_ROOTS_BY_LENGTH = sorted(ROOT_SUB_TYPES, key=len, reverse=True)

# regex الاسم هو نفسه الذي يعيش اليوم في `isCashAccount`
# (`frontend_v2/utils/accountTree.ts`) مضافاً إليه `till|petty` — انحراف
# `SalesInvoiceEditor` يُستوعَب هنا بدل أن يبقى شرطاً خاصاً في شاشة واحدة.
# «صندوق» تُفحص أولاً: حسابٌ اسمه «صندوق بنك فلسطين» صندوقٌ لا حساب بنكي.
_NAME_PATTERNS = [
    (re.compile(r'صندوق|نقدية|cash|till|petty', re.IGNORECASE), SUB_TYPE_CASH_BOX),
    (re.compile(r'بنك|bank', re.IGNORECASE), SUB_TYPE_BANK),
]

# أنواع الأطراف: العميل ذمّة مدينة، وكل ما عداه (مورد/وكيل شحن/مخلّص/ناقل)
# ذمّة دائنة — هذا هو التقسيم نفسه الذي تعمل به شاشات السندات.
_RECEIVABLE_PARTNER_TYPES = {'Customer'}

# حدّ الأمان في تسلّق السلالة: شجرة الحسابات لا تتجاوز عمقاً معقولاً، والحدّ
# يمنع دورة `parent` معطوبة من تعليق العملية.
_MAX_DEPTH = 64
_CHUNK = 1000


def _models(Account, BankAccount, CashBoxLedgerAccount, Partner):
    """يسمح للـmigration بتمرير الموديلات التاريخية، وللكود الحيّ بألا يمرّر شيئاً."""
    if Account is None or BankAccount is None or CashBoxLedgerAccount is None:
        from .models import (
            Account as LiveAccount, BankAccount as LiveBankAccount,
            CashBoxLedgerAccount as LiveCashBox,
        )
        Account = Account or LiveAccount
        BankAccount = BankAccount or LiveBankAccount
        CashBoxLedgerAccount = CashBoxLedgerAccount or LiveCashBox
    if Partner is None:
        from partners.models import Partner as LivePartner
        Partner = LivePartner
    return Account, BankAccount, CashBoxLedgerAccount, Partner


def _lineage_sub_type(row, by_id):
    """تصنيف الحساب من أقرب جذر معياري في سلالته (أو في بادئة رمزه)."""
    current = row
    for _ in range(_MAX_DEPTH):
        if current is None:
            return None
        code = (current.get('code') or '').strip()
        if code:
            answer = ROOT_SUB_TYPES.get(code)
            if answer:
                return answer
            for root in _ROOTS_BY_LENGTH:
                if code.startswith(root):
                    return ROOT_SUB_TYPES[root]
        current = by_id.get(current.get('parent_id'))
    return None


def _name_sub_type(row):
    """آخر الحلول — ومقصور على الأصول: «مصاريف بنكية» مصروف لا حساب بنكي."""
    if (row.get('account_type') or '').strip().lower() != 'asset':
        return None
    name = row.get('name') or ''
    for pattern, answer in _NAME_PATTERNS:
        if pattern.search(name):
            return answer
    return None


def _parent_in_memory(account):
    """أب الحساب **إن كان محمّلاً أصلاً** — وإلا `None` بلا أي استعلام.

    الاشتقاق يجري داخل `Account.save()`، ومسارٌ يُنشئ عشرات الحسابات (بذر شجرة
    شركة) كان سيدفع استعلاماً لكل حساب لو حمّلنا الأب هنا — استعلام في الحفظ
    مخالفٌ لقانون N+1 في المشروع. من مرّر كائن الأب (وهو الشائع:
    `Account.objects.create(parent=parent)`) يكسب الوراثة مجاناً، ومن مرّر
    `parent_id` وحده يسقط إلى سلالة الكود — وهي تجيب في الشجرة المعيارية لأن
    كود الابن يبدأ بكود أبيه.
    """
    if not getattr(account, 'parent_id', None):
        return None
    cache = getattr(getattr(account, '_state', None), 'fields_cache', None)
    return cache.get('parent') if cache else None


def sub_type_for_account(account):
    """تصنيف حسابٍ واحد عند إنشائه — الوريث الحيّ للـbackfill.

    الـbackfill يصنّف حسابات اليوم مرة واحدة ثم لا يُعاد أبداً؛ لولا هذه الدالة
    لمات الاشتقاق لحظة تطبيق الهجرة: شركة تُبذَر شجرتها غداً تفتح حقل الذمم فلا
    تجد فيه حساباً واحداً، وزبونٌ يُنشأ بعد الهجرة يغيب عن حقلٍ يظهر فيه زبون
    الأمس.

    ترتيب الحجّية هو نفسه ترتيب الـbackfill، مقروءاً من الحساب وحده بلا تحميل
    شجرة الشركة كلها: تصنيف الأب (وهو أثر الرابط الموثوق حين يكون الأب حساب ذمم
    مصنَّفاً) ← أقرب جذر معياري في السلالة ← اسم الحساب. يعود `None` حين لا
    يعرف — والفراغ إجابةٌ صحيحة تعني «حسابٌ عادي يكفيه نوعه».
    """
    if getattr(account, 'sub_type', None):
        return account.sub_type

    current = account
    for depth in range(_MAX_DEPTH):
        if current is None:
            break
        if depth:  # تصنيف الحساب نفسه فارغ أصلاً — نسأل آباءه فقط
            inherited = getattr(current, 'sub_type', None)
            if inherited:
                return inherited
        code = (getattr(current, 'code', '') or '').strip()
        if code:
            answer = ROOT_SUB_TYPES.get(code)
            if answer:
                return answer
            for root in _ROOTS_BY_LENGTH:
                if code.startswith(root):
                    return ROOT_SUB_TYPES[root]
        current = _parent_in_memory(current)

    return _name_sub_type({
        'account_type': getattr(account, 'account_type', None),
        'name': getattr(account, 'name', None),
    })


def sub_type_for_partner(partner_type):
    """تصنيف حساب الطرف من نوعه — الرابط الموثوق، أقوى من السلالة والاسم."""
    if not partner_type:
        return None
    return (SUB_TYPE_RECEIVABLE if partner_type in _RECEIVABLE_PARTNER_TYPES
            else SUB_TYPE_PAYABLE)


def classify_tenant_accounts(tenant_id, *, Account=None, BankAccount=None,
                             CashBoxLedgerAccount=None, Partner=None):
    """يُرجع {account_id: sub_type} لحسابات شركة واحدة — بلا أي كتابة.

    دالة خالصة عمداً: الـmigration والاختبارات والكود الحيّ يستدعونها جميعاً،
    ومن يكتب هو `backfill_account_sub_types` وحده.
    """
    Account, BankAccount, CashBoxLedgerAccount, Partner = _models(
        Account, BankAccount, CashBoxLedgerAccount, Partner)

    rows = list(
        Account.objects.filter(tenant_id=tenant_id)
        .values('id', 'code', 'name', 'parent_id', 'account_type')
    )
    if not rows:
        return {}
    by_id = {row['id']: row for row in rows}
    answers = {}

    def _claim(account_id, sub_type):
        # `setdefault`: الحجّة الأسبق تفوز — الخطوة اللاحقة لا تنقض ما قبلها.
        if account_id in by_id:
            answers.setdefault(account_id, sub_type)

    # (1) الروابط — الأقوى، لأن الخادم أنشأ الحساب لهذا الغرض.
    for account_id in BankAccount.objects.filter(
            tenant_id=tenant_id).values_list('account_id', flat=True):
        _claim(account_id, SUB_TYPE_BANK)
    for account_id in CashBoxLedgerAccount.objects.filter(
            tenant_id=tenant_id).values_list('account_id', flat=True):
        _claim(account_id, SUB_TYPE_CASH_BOX)
    for account_id, partner_type in Partner.objects.filter(
            tenant_id=tenant_id, linked_account_id__isnull=False,
    ).values_list('linked_account_id', 'partner_type'):
        _claim(account_id, SUB_TYPE_RECEIVABLE
               if (partner_type or '') in _RECEIVABLE_PARTNER_TYPES
               else SUB_TYPE_PAYABLE)

    # (2) سلالة الشجرة المعيارية، ثم (3) اسم الحساب.
    for row in rows:
        if row['id'] in answers:
            continue
        answer = _lineage_sub_type(row, by_id) or _name_sub_type(row)
        if answer:
            answers[row['id']] = answer
    return answers


def backfill_account_sub_types(*, Account=None, BankAccount=None,
                               CashBoxLedgerAccount=None, Partner=None,
                               tenant_ids=None):
    """يملأ `sub_type` للحسابات التي بلا تصنيف — لكل الشركات ما لم تُحدَّد.

    idempotent: لا يلمس حساباً له قيمة، فإعادة التشغيل لا تمحو تصحيحاً يدوياً
    أجراه المالك من بطاقة الحساب. يُرجع عدد الصفوف المكتوبة.
    """
    Account, BankAccount, CashBoxLedgerAccount, Partner = _models(
        Account, BankAccount, CashBoxLedgerAccount, Partner)

    if tenant_ids is None:
        tenant_ids = list(
            Account.objects.values_list('tenant_id', flat=True).distinct())
    written = 0
    for tenant_id in tenant_ids:
        answers = classify_tenant_accounts(
            tenant_id, Account=Account, BankAccount=BankAccount,
            CashBoxLedgerAccount=CashBoxLedgerAccount, Partner=Partner)
        if not answers:
            continue
        blanks = set(
            Account.objects.filter(tenant_id=tenant_id, sub_type__isnull=True)
            .values_list('id', flat=True)
        )
        buckets = {}
        for account_id, sub_type in answers.items():
            if account_id in blanks:
                buckets.setdefault(sub_type, []).append(account_id)
        for sub_type, ids in buckets.items():
            # التقطيع يحمي MySQL من قائمة معاملات ضخمة على شركة كبيرة الشجرة.
            for start in range(0, len(ids), _CHUNK):
                written += Account.objects.filter(
                    tenant_id=tenant_id, id__in=ids[start:start + _CHUNK],
                ).update(sub_type=sub_type)
    return written
