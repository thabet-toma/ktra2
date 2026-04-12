"""
سقف ترحيل دفعات الصفقة: لا يُسمح بأن يصبح مجموع المبالغ المرحّلة محاسبياً
أكبر من إجمالي الصفقة (total_amount).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Tuple

from django.db.models import Sum


def posting_cap_check(deal, additional_amount) -> Tuple[bool, Optional[str]]:
    """
    يتحقق قبل إنشاء قيد لدفعة جديدة (لم تُرحَّل بعد).

    Returns:
        (True, None) إن كان مسموحاً
        (False, رسالة عربية) إن كان الترحيل سيتجاوز سقف الصفقة
    """
    cap = Decimal(deal.total_amount or 0)
    add = Decimal(additional_amount or 0)
    if add <= 0:
        return True, None

    posted = (
        deal.payments.filter(is_posted=True).aggregate(t=Sum("amount"))["t"]
    )
    posted = Decimal(posted or 0)

    if cap <= 0:
        return (
            False,
            "إجمالي الصفقة غير محدد أو صفر؛ حدّد قيمة الصفقة قبل ترحيل الدفعات.",
        )

    eps = max(Decimal("0.01"), abs(cap) * Decimal("1e-9"))
    if posted + add > cap + eps:
        return (
            False,
            f"لا يمكن الترحيل: مجموع الدفعات المرحّلة يصبح {posted + add} "
            f"بينما إجمالي الصفقة {cap}. احذف دفعة زائدة أو خفّض المبلغ أو زد إجمالي الصفقة.",
        )
    return True, None


def shipment_agent_posting_cap_check(shipment, additional_amount) -> Tuple[bool, Optional[str]]:
    """
    سقف ترحيل دفعات وكيل الشحنة: مجموع المبالغ المرحّلة ≤ total_shipping_cost_usd.
    """
    cap = Decimal(shipment.total_shipping_cost_usd or 0)
    add = Decimal(additional_amount or 0)
    if add <= 0:
        return True, None

    posted = shipment.agent_payments.filter(
        is_posted=True, deal__isnull=True
    ).aggregate(t=Sum("amount"))["t"]
    posted = Decimal(posted or 0)

    # إن لم يُحفظ total_shipping_cost_usd بعد (0) لا نمنع الترحيل — وإلا يفشل «قيد تلقائي» رغم دفع فعلي
    if cap <= 0:
        return True, None

    eps = max(Decimal("0.01"), abs(cap) * Decimal("1e-9"))
    if posted + add > cap + eps:
        return (
            False,
            f"لا يمكن الترحيل: مجموع دفعات الوكيل المرحّلة يصبح {posted + add} "
            f"بينما إجمالي الشحن {cap} USD. راجع المبالغ أو زد إجمالي الشحن.",
        )
    return True, None
