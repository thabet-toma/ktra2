from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
import datetime
from .models import LogisticsDeal, LogisticsPayment, LogisticsShipment, LogisticsExpense
from accounting.models import JournalHeader, JournalLine, Account

@receiver(post_save, sender=LogisticsDeal)
def automate_deal_accounting(sender, instance, created, **kwargs):
    """
    Automate accounting for LogisticsDeal.
    If deal is 'Confirmed/Open' or similar and has not been posted:
    Debit: Purchases/Inventory Account | Credit: Accounts Payable (Partner's linked account)
    """
    if not instance.is_posted and instance.partner and instance.partner.linked_account:
        # Prevent recursion by checking standard conditions
        try:
            with transaction.atomic():
                purchase_account = (
                    Account.objects.filter(tenant=instance.tenant, code__startswith='5').first()
                    or Account.objects.filter(tenant=instance.tenant, code__startswith='12').first()
                    or Account.objects.filter(tenant=instance.tenant, account_type='Expense').first()
                )

                if not purchase_account:
                    return # Account not found, skip automation

                journal = JournalHeader.objects.create(
                    tenant=instance.tenant,
                    transaction_date=instance.order_date or datetime.date.today(),
                    description=f"شراء بضاعة (Auto): {instance.description or instance.ref_number} | المورد: {instance.partner.name}",
                    reference_type='LOGISTICS_DEAL',
                    reference_id=instance.id,
                    is_posted=True
                )

                JournalLine.objects.create(
                    tenant=instance.tenant,
                    journal=journal,
                    account=instance.partner.linked_account,
                    debit=0,
                    credit=instance.total_amount,
                    partner=instance.partner
                )

                JournalLine.objects.create(
                    tenant=instance.tenant,
                    journal=journal,
                    account=purchase_account,
                    debit=instance.total_amount,
                    credit=0,
                    partner=instance.partner
                )

                LogisticsDeal.objects.filter(id=instance.id).update(is_posted=True, journal=journal)
        except Exception as e:
            print(f"Error automating LogisticsDeal {instance.id}: {e}")

@receiver(post_save, sender=LogisticsPayment)
def automate_payment_accounting(sender, instance, created, **kwargs):
    """
    Automate accounting for LogisticsPayment.
    If payment status is 'Paid' or 'Confirmed' and has not been posted:
    Debit: Accounts Payable (Partner's linked account) | Credit: Bank/Cash
    """
    if not instance.is_posted and instance.status in ['Paid', 'Confirmed']:
        try:
            deal = instance.deal
            if not deal.partner or not deal.partner.linked_account:
                return
            
            with transaction.atomic():
                bank_account = instance.bank_account
                if not bank_account:
                    bank_account = (
                        Account.objects.filter(tenant=deal.tenant, code__startswith='11').first()
                        or Account.objects.filter(tenant=deal.tenant, account_type='Asset', name__icontains='بنك').first()
                        or Account.objects.filter(tenant=deal.tenant, account_type='Asset').first()
                    )

                if not bank_account:
                    return # Could not locate bank

                payment_date = instance.transfer_date or datetime.date.today()
                
                journal = JournalHeader.objects.create(
                    tenant=deal.tenant,
                    transaction_date=payment_date,
                    description=f"دفعة (Auto) {instance.title} | صفقة: {deal.ref_number} | المورد: {deal.partner.name}",
                    reference_type='LOGISTICS_PAYMENT',
                    reference_id=instance.id,
                    is_posted=True
                )

                JournalLine.objects.create(
                    tenant=deal.tenant,
                    journal=journal,
                    account=deal.partner.linked_account,
                    debit=instance.amount,
                    credit=0,
                    partner=deal.partner
                )

                JournalLine.objects.create(
                    tenant=deal.tenant,
                    journal=journal,
                    account=bank_account,
                    debit=0,
                    credit=instance.amount,
                    partner=deal.partner
                )

                LogisticsPayment.objects.filter(id=instance.id).update(
                    is_posted=True, 
                    journal=journal, 
                    bank_account=bank_account
                )

                # Update deal payment status
                payments = LogisticsPayment.objects.filter(deal=deal, status__in=['Paid', 'Confirmed'])
                paid_total = sum(p.amount for p in payments)
                
                new_status = 'Unpaid'
                if paid_total >= deal.total_amount:
                    new_status = 'Fully Paid'
                elif paid_total > 0:
                    new_status = 'Partially Paid'
                
                LogisticsDeal.objects.filter(id=deal.id).update(payment_status=new_status)

        except Exception as e:
            print(f"Error automating LogisticsPayment {instance.id}: {e}")

@receiver(post_save, sender=LogisticsExpense)
def automate_expense_accounting(sender, instance, created, **kwargs):
    """
    Automate accounting for LogisticsExpense.
    Debit: Expense Account | Credit: Liability Account
    """
    if not instance.is_posted and instance.expense_account and instance.payable_account:
        try:
            with transaction.atomic():
                journal = JournalHeader.objects.create(
                    tenant=instance.tenant,
                    transaction_date=instance.invoice_date or datetime.date.today(),
                    description=f"مصروف لوجستي (Auto): {instance.description} ({instance.related_type} #{instance.related_id})",
                    reference_type='LOGISTICS_EXPENSE',
                    reference_id=instance.id,
                    is_posted=True
                )

                JournalLine.objects.create(
                    tenant=instance.tenant,
                    journal=journal,
                    account=instance.expense_account,
                    debit=instance.amount,
                    credit=0
                )

                JournalLine.objects.create(
                    tenant=instance.tenant,
                    journal=journal,
                    account=instance.payable_account,
                    debit=0,
                    credit=instance.amount
                )

                LogisticsExpense.objects.filter(id=instance.id).update(is_posted=True, journal=journal)
        except Exception as e:
            print(f"Error automating LogisticsExpense {instance.id}: {e}")
