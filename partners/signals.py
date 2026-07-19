from __future__ import annotations

from typing import Optional

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
import logging
from .models import Partner
from accounting.models import Account, JournalHeader, JournalLine
import datetime

logger = logging.getLogger(__name__)

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
    }.get(partner_type)

@receiver(post_save, sender=Partner)
def manage_partner_account(sender, instance, created, **kwargs):
    """
    Signal to automatically manage the linked accounting account for a partner.
    Handles account creation and opening balance journal entries.
    """
    # 1. Automatic Account Creation
    if not instance.linked_account:
        # Tenant must come from the partner itself — never guess a company.
        tenant = instance.tenant
        if not tenant:
            logger.error(
                "manage_partner_account: partner id=%s has no tenant — skipping account creation",
                instance.id,
            )
            return

        parent_acc = None
        expected_parent_code = _expected_parent_code_for_partner_type(
            instance.partner_type
        )
        
        # 1. Try to get Parent from Partner Group
        if instance.group:
            if instance.partner_type == 'Customer':
                parent_acc = instance.group.account_receivable
            else:  # Supplier, FreightForwarder, CustomsBroker, LocalTransporter
                parent_acc = instance.group.account_payable
        
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
                target_name = _normalize_account_name(instance.name)
                existing_account = None
                if target_name:
                    for acc in Account.objects.filter(tenant=tenant, parent=parent_acc):
                        if _normalize_account_name(acc.name) != target_name:
                            continue
                        if Partner.objects.filter(linked_account=acc).exclude(pk=instance.pk).exists():
                            continue
                        existing_account = acc
                        break

                if existing_account:
                    partner_account = existing_account
                else:
                    # Generate unique code: ParentCode + PartnerID (padded)
                    new_code = f"{parent_acc.code}{str(instance.id).zfill(4)}"

                    # Use get_or_create
                    partner_account, acc_created = Account.objects.get_or_create(
                        tenant=tenant,
                        code=new_code,
                        defaults={
                            'name': instance.name,
                            'account_type': parent_acc.account_type,
                            'parent': parent_acc,
                            'is_active': True
                        }
                    )

                instance.linked_account = partner_account
                instance.save(update_fields=['linked_account'])
            except Exception as e:
                logger.exception(
                    "Error creating account for partner id=%s", instance.id
                )

    # 3. Dynamic Sync: Update account name if partner name changed
    elif instance.linked_account and instance.linked_account.name != instance.name:
        instance.linked_account.name = instance.name
        instance.linked_account.save(update_fields=['name'])

    # 4. Dynamic Sync: Update account parent if partner type changed
    # (Checking if the current parent matches the expected parent based on type)
    if instance.linked_account:
        expected_parent_code = _expected_parent_code_for_partner_type(
            instance.partner_type
        )
        
        if expected_parent_code and (not instance.linked_account.parent or instance.linked_account.parent.code != expected_parent_code):
            try:
                new_parent = Account.objects.get(code=expected_parent_code, tenant=instance.tenant)
                instance.linked_account.parent = new_parent
                instance.linked_account.account_type = new_parent.account_type
                instance.linked_account.save(update_fields=['parent', 'account_type'])
            except Account.DoesNotExist:
                pass

    # 2. Opening Balance Journal Entry
    if instance.opening_balance and instance.opening_balance > 0 and instance.linked_account:
        exists = JournalHeader.objects.filter(
            tenant=instance.tenant,
            reference_type='PARTNER_OPENING',
            reference_id=instance.id
        ).exists()
        
        if not exists:
            create_opening_balance_entry(instance)

def ensure_partner_linked_account(partner: Optional[Partner]) -> Optional[Partner]:
    """
    يضمن وجود حساب محاسبي مربوط بالشريك (مورد / وكيل شحن / …) عبر نفس منطق post_save.
    يُستدعى قبل ترحيل دفعات لوجستيات حتى لا يضطر المستخدم لربط الحساب يدوياً.
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
            "ensure_partner_linked_account failed for partner id=%s", partner.pk
        )
    return partner


def create_opening_balance_entry(partner):
    try:
        tenant = partner.tenant
        if not tenant:
            logger.error(
                "create_opening_balance_entry: partner id=%s has no tenant — skipping",
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

        with transaction.atomic():
            date = partner.opening_balance_date or datetime.date.today()
            
            header = JournalHeader.objects.create(
                tenant=tenant,
                transaction_date=date,
                reference_type='PARTNER_OPENING',
                reference_id=partner.id,
                description=f"Opening Balance for {partner.name}",
                is_posted=True
            )
            
            if partner.partner_type == 'Customer':
                JournalLine.objects.create(tenant=tenant, journal=header, account=partner.linked_account, debit=partner.opening_balance, credit=0, partner_id=partner.id)
                JournalLine.objects.create(tenant=tenant, journal=header, account=opening_offset_account, debit=0, credit=partner.opening_balance)
            else:
                JournalLine.objects.create(tenant=tenant, journal=header, account=opening_offset_account, debit=partner.opening_balance, credit=0)
                JournalLine.objects.create(tenant=tenant, journal=header, account=partner.linked_account, debit=0, credit=partner.opening_balance, partner_id=partner.id)

    except Exception as e:
        logger.exception("Failed to create opening balance for partner id=%s", partner.id)
