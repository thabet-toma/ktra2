"""ربط صناديق النقدية الخارجية (مثل Firestore) بحسابات الأصول في الشجرة."""

from django.conf import settings

from .models import Account, CashBoxLedgerAccount


def get_cash_box_parent_account(tenant):
    code = str(getattr(settings, "CASH_BOX_PARENT_ACCOUNT_CODE", None) or "1110").strip()
    acc = Account.objects.filter(tenant=tenant, code=code).first()
    if acc:
        return acc
    return (
        Account.objects.filter(tenant=tenant, account_type="Asset", code__startswith="111")
        .order_by("code")
        .first()
        or Account.objects.filter(tenant=tenant, account_type="Asset").order_by("code").first()
    )


def get_cash_box_capital_account(tenant):
    """
    حساب حقوق الملكية / رأس المال المقابل لإيداع نقد في صندوق (دائن القيد).
    يُحدَّد بـ CASH_BOX_CAPITAL_ACCOUNT_CODE أو أول حساب Equity للمستأجر.
    """
    code = str(getattr(settings, "CASH_BOX_CAPITAL_ACCOUNT_CODE", None) or "").strip()
    if code:
        acc = Account.objects.filter(tenant=tenant, code=code).first()
        if acc:
            return acc
    return (
        Account.objects.filter(tenant=tenant, account_type="Equity")
        .order_by("code", "id")
        .first()
    )


def resolve_default_cash_box_account(tenant):
    """
    حساب الصندوق الافتراضي لترحيل دفعات لوجستية عند عدم تمرير cash_box_external_id.

    الترتيب:
    1) DEFAULT_CASH_BOX_EXTERNAL_ID من الإعدادات → CashBoxLedgerAccount
    2) أول ربط صندوق بعملة USD للمستأجر
    3) أي أول ربط صندوق للمستأجر

    لا يُرجع «أول أصل» في الشجرة (كان يسبب قيوداً على أصول متداولة عامة بالخطأ).
    """
    ext = str(getattr(settings, "DEFAULT_CASH_BOX_EXTERNAL_ID", None) or "").strip()
    if ext:
        link = (
            CashBoxLedgerAccount.objects.filter(tenant=tenant, external_id=ext[:128])
            .select_related("account")
            .first()
        )
        if link and link.account_id:
            return link.account
    link_usd = (
        CashBoxLedgerAccount.objects.filter(tenant=tenant, currency_code__iexact="USD")
        .select_related("account")
        .order_by("id")
        .first()
    )
    if link_usd and link_usd.account_id:
        return link_usd.account
    link_any = (
        CashBoxLedgerAccount.objects.filter(tenant=tenant)
        .select_related("account")
        .order_by("id")
        .first()
    )
    if link_any and link_any.account_id:
        return link_any.account
    return None


def allocate_cash_box_account_code(parent: Account, tenant) -> str:
    raw = (parent.code or "111").replace("-", "").strip() or "111"
    prefix = raw[:10]
    i = CashBoxLedgerAccount.objects.filter(tenant=tenant).count() + 1
    for _ in range(8000):
        cand = f"{prefix}B{i:04d}"
        if len(cand) > 20:
            cand = cand[:20]
        if not Account.objects.filter(tenant=tenant, code=cand).exists():
            return cand
        i += 1
    import random

    return f"{prefix[:12]}{random.randint(10000, 99999)}"[:20]
