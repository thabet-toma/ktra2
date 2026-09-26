"""بنود التخليص من إعدادات الشركة (`ClearanceItemType`) — بذرتُها وقراءتُها.

البنود الستّة القياسية تُبذَر مرّةً عند أوّل قراءةٍ لشركةٍ بلا بنود، بحساباتها
الافتراضية (`accruals.CLEARANCE_DEFAULT_ACCOUNT_CODES`) — فشركةٌ قديمة ترى بنودها
المعهودة، ثم تضيف المتكرّر منها بدل «أخرى».
"""
from __future__ import annotations

import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

#: (الاسم، النوع) — الأسماء نفسها التي يطابقها `LABEL_TO_LINE_TYPE` في السيريالايزر.
DEFAULT_CLEARANCE_ITEMS = (
    ('ضريبة القيمة المضافة', 'vat'),
    ('رسوم البيان الجمركي', 'declaration_fee'),
    ('محطة الشحن', 'terminal'),
    ('معالجة التصاريح', 'permits'),
    ('عمولة المخلص', 'broker_commission'),
    ('نظام الجمارك «الجيل الجديد»', 'customs_system'),
)


def ensure_clearance_item_types(tenant) -> None:
    """يبذر البنود القياسية لشركةٍ بلا بنود. آمنٌ للتكرار والتزامن."""
    from accounting.api import get_accounts_by_codes
    from logistics.accruals import CLEARANCE_DEFAULT_ACCOUNT_CODES
    from logistics.models import ClearanceItemType

    if ClearanceItemType.objects.filter(tenant=tenant).exists():
        return
    accounts = {
        acc.code: acc for acc in get_accounts_by_codes(
            tenant, set(CLEARANCE_DEFAULT_ACCOUNT_CODES.values())).filter(is_active=True)
    }
    try:
        with transaction.atomic():
            for order, (name, legacy_type) in enumerate(DEFAULT_CLEARANCE_ITEMS, start=1):
                ClearanceItemType.objects.create(
                    tenant=tenant, name=name, legacy_type=legacy_type, sort_order=order,
                    account=accounts.get(CLEARANCE_DEFAULT_ACCOUNT_CODES[legacy_type]),
                )
    except IntegrityError:
        # طلبٌ متزامن بذرها قبلنا.
        return
    logger.info('clearance item types seeded tenant=%s', tenant.pk)
