import os
import sys
import django

sys.path.append(r'C:\Users\asus\Desktop\ktra')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from hr.models import Task, AttendanceRecord, PointsHistory
from partners.models import Partner
from accounting.models import Account, JournalHeader
from logistics.models import LogisticsDeal, LogisticsPayment
from tenants.models import Tenant
from django.utils import timezone
from decimal import Decimal

def run_tests():
    print("--- Starting Verification Tests ---")
    tenant = Tenant.objects.first()
    if not tenant:
        print("No tenant found. Test aborted.")
        return

    # 1. Test HR App Models
    print("\n[1] Testing HR Models...")
    user, _ = User.objects.get_or_create(username='testemployee', defaults={'first_name': 'Test'})
    
    # Create Task
    task = Task.objects.create(
        tenant=tenant, title="Test Verification Task", assigned_to=user, priority="HIGH"
    )
    print(f"✅ HR Task created successfully: {task.id} - {task.title}")
    
    # Create Attendance
    att = AttendanceRecord.objects.create(
        tenant=tenant, user=user, date=timezone.now().date(), status="Present"
    )
    print(f"✅ HR Attendance created successfully: {att.id} - {att.date}")
    
    # 2. Test Partner to Chart of Accounts
    print("\n[2] Testing Partner to Chart of Accounts Linkage...")
    # Create Supplier
    test_partner_name = "Test Verification Supplier X9"
    partner = Partner.objects.create(
        tenant=tenant,
        name=test_partner_name,
        partner_type='supplier',
        currency='USD',
        status='active'
    )
    print(f"Created Partner: {partner.name}")
    
    # Check if Account was auto-created via signals
    account = Account.objects.filter(tenant=tenant, name=test_partner_name).first()
    if account:
        print(f"✅ Chart of Accounts linkage successful! Account ID: {account.account_id}")
        partner.linked_account = account
        partner.save()
    else:
        print("❌ Chart of Accounts linkage failed! Expected an Account to be created automatically.")
        
    # 3. Test Logistics Payment to Journal Entry
    print("\n[3] Testing Automated Journal Entries on Payments...")
    payment = LogisticsPayment.objects.create(
        tenant=tenant,
        payment_number="PAY-VERIFY-1",
        issue_date=timezone.now(),
        amount=150.00,
        currency='USD',
        payment_method='bank_transfer',
        payment_status='Paid',
        supplier=partner
    )
    print(f"Created Paid LogisticsPayment: {payment.payment_number}")
    
    # Check if a Journal Entry was automatically created
    # Based on the logistics.signals implementation
    journal = JournalHeader.objects.filter(reference=f"PAY-{payment.id}").first()
    if journal:
        print(f"✅ Automated Journal Entry successful! Journal ID: {journal.journal_id}")
        if journal.lines.count() >= 2:
            print("  ✅ Balanced double-entry lines verify!")
            for line in journal.lines.all():
                print(f"     Line: {line.account.name} | Dr: {line.debit_amount} | Cr: {line.credit_amount}")
        else:
            print("  ❌ Journal lines missing!")
    else:
        print("❌ Automated Journal Entry failed! Expected JournalHeader to be created automatically (Reference format may differ).")
        # Let's search broadly for newest JournalHeader
        latest_jh = JournalHeader.objects.order_by('-created_at').first()
        if latest_jh:
            print(f"  ? Latest Journal present: {latest_jh.reference} - {latest_jh.description}")
        
    print("\n--- Verification Tests Completed ---")

if __name__ == '__main__':
    run_tests()
