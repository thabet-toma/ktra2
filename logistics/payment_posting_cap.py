"""
سقف ترحيل الدفعات: **الدفع الزائد مسموح لكل الأطراف** — المورد ووكيل الشحن
والمخلّص والناقل. الفائض دفعة مقدمة مشروعة تجعل الطرف مديناً لنا وتُسوّى على
مستند لاحق؛ الحظر كان يمنع واقعة محاسبية صحيحة. الدوال هنا تسجّل الفائض في
اللوج فقط (قرار المالك 2026-07-19).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional, Tuple

from django.db.models import Sum

logger = logging.getLogger(__name__)


def posting_cap_check(deal, additional_amount) -> Tuple[bool, Optional[str]]:
    """
    دفعات المورد: الدفع الزائد مسموح — يصبح **دفعة مقدمة** لدى المورد.

    قيد الدفع (Dr ذمم المورد / Cr الصندوق) ينقل رصيده للجانب المدين، أي أن
    المورد يصبح مديناً لنا بالفائض وتُسوّى على صفقة لاحقة. يبقى شرط واحد:
    إجمالي صفقة غير محدد يعني لا أساس للتكلفة أصلاً.
    """
    cap = Decimal(deal.total_amount or 0)
    add = Decimal(additional_amount or 0)
    if add <= 0:
        return True, None

    if cap <= 0:
        return (
            False,
            "إجمالي الصفقة غير محدد أو صفر؛ حدّد قيمة الصفقة قبل ترحيل الدفعات.",
        )

    posted = (
        deal.payments.filter(is_posted=True).aggregate(t=Sum("amount"))["t"]
    )
    posted = Decimal(posted or 0)
    eps = max(Decimal("0.01"), abs(cap) * Decimal("1e-9"))
    if posted + add > cap + eps:
        logger.info(
            "deal %s supplier overpayment -> advance: posted=%s add=%s cap=%s advance=%s",
            getattr(deal, "pk", None), posted, add, cap, posted + add - cap,
        )
    return True, None


def shipment_agent_posting_cap_check(shipment, additional_amount) -> Tuple[bool, Optional[str]]:
    """
    دفعات وكيل الشحن: الدفع الزائد مسموح — يصبح **دفعة مقدمة** لدى الوكيل.

    محاسبياً لا يوجد ما يمنع دفع أكثر من قيمة الشحنة: قيد الدفع (Dr ذمم الوكيل /
    Cr الصندوق) ينقل رصيده إلى الجانب المدين، أي أن الوكيل يصبح مديناً لنا بالفائض
    ويُسوّى على شحنة لاحقة. الحظر السابق كان يفرض قاعدة تشغيلية على قيد صحيح.
    نكتفي بتسجيل الفائض في اللوج ليبقى ظاهراً للمراجعة.
    """
    cap = Decimal(shipment.total_shipping_cost_usd or 0)
    add = Decimal(additional_amount or 0)
    if add <= 0:
        return True, None

    if cap > 0:
        posted = shipment.agent_payments.filter(
            is_posted=True, deal__isnull=True
        ).aggregate(t=Sum("amount"))["t"]
        posted = Decimal(posted or 0)
        eps = max(Decimal("0.01"), abs(cap) * Decimal("1e-9"))
        if posted + add > cap + eps:
            logger.info(
                "shipment %s agent overpayment → advance: posted=%s add=%s cap=%s advance=%s USD",
                getattr(shipment, "pk", None), posted, add, cap, posted + add - cap,
            )
    return True, None


def clearance_broker_posting_cap_check(paid, additional_amount, budget, label="clearance broker") -> Tuple[bool, Optional[str]]:
    """
    دفعات المخلّص الجمركي/الناقل المحلي: نفس معاملة وكيل الشحن أعلاه — الدفع الزائد
    عن استحقاق التخليص/الشحن مسموح ويصبح دفعة مقدمة لدى الطرف الآخر (نصير دائنين له)
    بدل رفض العملية. نسجّل الفائض في اللوج فقط لبقائه ظاهراً للمراجعة.
    """
    add = Decimal(additional_amount or 0)
    if add <= 0:
        return True, None
    cap = Decimal(budget or 0)
    posted = Decimal(paid or 0)
    if cap > 0:
        eps = max(Decimal("0.01"), abs(cap) * Decimal("1e-9"))
        if posted + add > cap + eps:
            logger.info(
                "%s overpayment → advance: posted=%s add=%s cap=%s advance=%s",
                label, posted, add, cap, posted + add - cap,
            )
    return True, None
