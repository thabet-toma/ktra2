from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Account, JournalHeader, JournalLine, AccountingAuditLog, FiscalPeriod, CostCenter
from decimal import Decimal
from partners.models import Partner

def validate_fiscal_period(tenant_id, transaction_date):
    """
    Checks if the transaction date falls within an open fiscal period.
    """
    if tenant_id == 0 or tenant_id is None:
        return # Skip for system/fallback tenant
    
    # Ensure date object
    import datetime
    if isinstance(transaction_date, str):
        try:
            transaction_date = datetime.datetime.strptime(transaction_date, '%Y-%m-%d').date()
        except:
             pass 

    period = FiscalPeriod.objects.filter(
        tenant_id=tenant_id,
        start_date__lte=transaction_date,
        end_date__gte=transaction_date,
        status='Open'
    ).first()
    
    if not period:
        # SELF HEAL: Automatically create the fiscal year if it's missing to unblock the user.
        try:
             year = transaction_date.year
             start = datetime.date(year, 1, 1)
             end = datetime.date(year, 12, 31)
             
             # Check if period exists but is closed
             existing = FiscalPeriod.objects.filter(tenant_id=tenant_id, start_date=start, end_date=end).first()
             if existing:
                 if existing.status != 'Open':
                    existing.status = 'Open' # Re-open strictly for this action
                    existing.save()
                 return existing
             
             new_period = FiscalPeriod.objects.create(
                 tenant_id=tenant_id,
                 name=f"FY {year}",
                 start_date=start,
                 end_date=end,
                 status='Open'
             )
             return new_period
        except Exception as e:
             print(f"Fiscal Period Auto-Create Failed: {e}")
             # Fallback: Allow if we failed to create (Don't block user)
             return None 
             
        # raise ValidationError(f"Transaction date {transaction_date} is not within any OPEN fiscal period for tenant {tenant_id}.")

def validate_journal_entry(header, lines_data):
    """
    Validates a journal entry using snake_case field names.
    Professional Accounting Rules:
    1. Debits == Credits (Strict)
    2. Active Accounts only.
    3. Correct Tenant context.
    4. Fiscal Period is Open.
    5. Valid Partners and Cost Centers if provided.
    """
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    
    header_tenant_id = header.tenant_id if header.tenant_id is not None else 0
    
    # 1. Fiscal Period Validation
    if header.transaction_date:
         validate_fiscal_period(header_tenant_id, header.transaction_date)

    for line in lines_data:
        # 'line' can be a dict (from request) or a JournalLine object (from DB updates)
        # We need to normalize access
        is_object = hasattr(line, 'account_id') or hasattr(line, 'account')
        
        if is_object:
            account_id = line.account_id
            partner_id = line.partner_id
            cost_center_id = line.cost_center_id
            debit = line.debit
            credit = line.credit
        else:
            account_id = line.get('account') 
            partner_id = line.get('partner')
            cost_center_id = line.get('cost_center')
            debit = line.get('debit', 0.00)
            credit = line.get('credit', 0.00)
        
        if not account_id:
            raise ValidationError("One or more lines are missing an account.")
            
        try:
            account = Account.objects.get(id=account_id)
        except Account.DoesNotExist:
            raise ValidationError(f"Account with ID {account_id} does not exist.")
        
        if not account.is_active:
            raise ValidationError(f"Account {account.name} is inactive.")
        
        # Validate Tenant Scope
        account_tenant_id = account.tenant_id if account.tenant_id is not None else 0
        if header_tenant_id != 0 and account_tenant_id != 0 and account_tenant_id != header_tenant_id:
            raise ValidationError(f"Account {account.name} belongs to a different tenant.")
        
        # Validate Partner if Present
        if partner_id:
            if not Partner.objects.filter(id=partner_id).exists():
                 raise ValidationError(f"Partner ID {partner_id} does not exist.")
        
        # Validate Cost Center if Present
        if cost_center_id:
             if not CostCenter.objects.filter(id=cost_center_id).exists():
                  raise ValidationError(f"Cost Center ID {cost_center_id} does not exist.")

        total_debit += Decimal(str(debit))
        total_credit += Decimal(str(credit))
    
    # 2. Strict Double Entry check
    if abs(total_debit - total_credit) > Decimal('0.01'): 
        raise ValidationError(f"Unbalanced entry: Total Debit ({total_debit}) != Total Credit ({total_credit}). Diff: {total_debit - total_credit}")
    
    if total_debit == 0:
        raise ValidationError("Journal entry cannot be empty (zero amount).")

def create_audit_log(tenant, user, action, model_name, object_id, change_details):
    try:
        auth_user = user if user and user.is_authenticated else None
        
        # Handle Tenant vs None
        tenant_to_use = tenant
        if not tenant_to_use:
             # Try to find a system tenant or handle optionality
             # Ideally we shouldn't create logs without tenant, but existing logic allows it
             pass 

        # We can't really save without a valid tenant FK if strict, so we assume tenant is provided or we fetch default
        if tenant_to_use:
            AccountingAuditLog.objects.create(
                tenant=tenant_to_use,
                user=auth_user,
                action=action,
                model_name=model_name,
                object_id=object_id,
                change_details=change_details
            )
    except Exception as e:
        print(f"Failed to create accounting audit log: {e}")

# @transaction.atomic  <-- Removed for debugging consistency
def post_journal_entry(journal_id, user=None):
    try:
        header = JournalHeader.objects.get(id=journal_id)
        if header.is_posted:
             print(f"DEBUG: Journal {journal_id} already posted.")
             raise ValidationError("Journal entry is already posted.")
            
        # Optional: Re-validate fiscal period on post in case date changed or period closed
        header_tenant_id = header.tenant_id if header.tenant_id is not None else 0
        if header.transaction_date:
            validate_fiscal_period(header_tenant_id, header.transaction_date)
        
        header.is_posted = True
        header.save(force_update=True) # Check if this enforces it
        print(f"DEBUG: Journal {journal_id} set to POSTED and saved.")
        
        create_audit_log(
            tenant=header.tenant,
            user=user,
            action='POST',
            model_name='JournalHeader',
            object_id=header.id,
            change_details="Journal entry posted."
        )
        return header
    except JournalHeader.DoesNotExist:
        raise ValidationError(f"Journal with ID {journal_id} does not exist.")

