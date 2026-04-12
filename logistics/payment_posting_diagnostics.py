"""
تشخيص سبب عدم ترحيل دفعة صفقة تلقائياً (نفس شروط signals.automate_payment_accounting).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.conf import settings

from accounting.models import Account, CashBoxLedgerAccount

from .payment_posting_cap import posting_cap_check


def resolve_bank_account_for_payment(deal, payment) -> Optional[Any]:
    """
    يطابق منطق logistics.signals.automate_payment_accounting لاختيار حساب الدائن (نقد/بنك).
    """
    bank_account = payment.bank_account
    ext = (getattr(payment, "cash_box_external_id", None) or "").strip()
    if not bank_account and ext:
        link = CashBoxLedgerAccount.objects.filter(
            tenant=deal.tenant, external_id=ext[:128]
        ).first()
        if link:
            bank_account = link.account
    if not bank_account:
        bank_account = (
            Account.objects.filter(tenant=deal.tenant, code__startswith="11").first()
            or Account.objects.filter(
                tenant=deal.tenant, account_type="Asset", name__icontains="بنك"
            ).first()
            or Account.objects.filter(tenant=deal.tenant, account_type="Asset").first()
        )
    return bank_account


def collect_auto_posting_blockers(deal, payment) -> List[str]:
    """قائمة أسباب عدم إمكانية الترحيل التلقائي (عربي)."""
    blockers: List[str] = []

    if payment.is_posted:
        return []

    if getattr(settings, "LOGISTICS_DISABLE_AUTO_ACCOUNTING", False):
        blockers.append(
            "الترحيل التلقائي معطّل في إعدادات الخادم (LOGISTICS_DISABLE_AUTO_ACCOUNTING). "
            "يمكن الترحيل يدوياً بعد حفظ التأكيد عبر واجهة الصفقة أو المحاسبة."
        )

    if getattr(settings, "LOGISTICS_PAYMENT_SKIP_AUTO_JOURNAL", False):
        blockers.append(
            "الإعداد LOGISTICS_PAYMENT_SKIP_AUTO_JOURNAL=1 يعطّل إنشاء القيد من إشارة post_save. "
            "أزل التعطيل أو استخدم POST .../post_payment/ أو ربط قيد يدوي."
        )

    if not getattr(payment, "confirmed_by_supplier", False):
        blockers.append(
            "لم يُحفَظ بعد «تأكيد المورد» في السجل (confirmed_by_supplier). أكمل خطوة التأكيد ثم احفظ."
        )

    if payment.status not in ("Paid", "Confirmed"):
        blockers.append(
            f"حالة الدفعة الحالية «{payment.status}»؛ يلزم «Paid» أو «Confirmed» ليُرحَّل القيد تلقائياً."
        )

    if payment.amount is None or payment.amount <= 0:
        blockers.append("مبلغ الدفعة صفر أو غير محدد.")

    partner = getattr(deal, "partner", None)
    if not partner:
        blockers.append("الصفقة بلا مورد مرتبط.")
    elif not getattr(partner, "linked_account_id", None):
        blockers.append(
            "المورد غير مربوط بحساب ذمّة (AP) في المحاسبة. افتح شجرة الحسابات أو بطاقة المورد واربط «حساب المورد»."
        )

    bank_account = resolve_bank_account_for_payment(deal, payment)
    if not bank_account:
        ext = (getattr(payment, "cash_box_external_id", None) or "").strip()
        if ext:
            blockers.append(
                f"معرّف الصندوق «{ext[:40]}…» غير مربوط بحساب GL. أنشئ الربط من المحاسبة (ربط صناديق) أو أزل المعرّف ليُستخدم حساب بنك/صندوق افتراضي."
            )
        else:
            blockers.append(
                "لم يُعثر على حساب بنك/صندوق للدائن: لا يوجد حساب أصول بكود يبدأ 11 أو اسمه يحتوي «بنك»، "
                "ولا صندوق مربوط على الدفعة. أضف حساباً في شجرة الحسابات أو اربط الصندوق."
            )

    ok_cap, cap_err = posting_cap_check(deal, payment.amount)
    if not ok_cap and cap_err:
        blockers.append(cap_err)

    return blockers


def build_auto_posting_report(deal, payment) -> Dict[str, Any]:
    """استجابة JSON لواجهة التشخيص."""
    blockers = collect_auto_posting_blockers(deal, payment)
    posted = bool(payment.is_posted)
    return {
        "payment_id": payment.id,
        "is_posted": posted,
        "journal_id": payment.journal_id,
        "auto_posting_disabled": getattr(
            settings, "LOGISTICS_DISABLE_AUTO_ACCOUNTING", False
        ),
        "blockers": blockers,
        "can_auto_post": (not posted) and len(blockers) == 0,
    }
