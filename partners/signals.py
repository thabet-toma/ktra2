"""إشارات الشركاء — الجانب المحاسبي كله يمرّ عبر واجهة `accounting.api`.

المرحلة 2-ج (accounting facade): منطق إنشاء/ربط حساب الشريك، ومزامنة اسمه
وأبيه، وقيد الرصيد الافتتاحي — انتقل حرفياً إلى `accounting/api.py`
(`sync_partner_accounting` / `ensure_partner_account` /
`create_partner_opening_balance`) بنفس أكواد الآباء المعيارية
(2101/1103/2106-2109 والرصيد الافتتاحي 3300). الـsignal هنا ينادي الواجهة فقط.
"""
from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
import logging

from accounting.api import sync_partner_accounting
from .models import Partner

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Partner)
def manage_partner_account(sender, instance, created, **kwargs):
    """
    Signal to automatically manage the linked accounting account for a partner.
    Handles account creation and opening balance journal entries.
    """
    sync_partner_accounting(instance)
