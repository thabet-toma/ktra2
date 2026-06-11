# task11 M7 — heal at deploy time: أي شركة قائمة ناقصة التأسيس
# (شجرة حسابات فارغة / بلا فرع رئيسي / بلا إعدادات / بلا دفاتر) تُستكمل
# تلقائياً عند تشغيل migrate — نفس منطق أمر heal_company_seed.
from django.db import migrations

# نسخة ثابتة من COA المعياري وقت كتابة المايغريشن (لا تستورد من services
# حتى لا يتغير سلوك المايغريشن مع تطور الكود).
from tenants.services import COA_DATA

BOOK_DOC_TYPES = [
    'sales_invoice', 'purchase_invoice', 'sales_return', 'purchase_return',
    'receipt_voucher', 'payment_voucher', 'multi_receipt', 'multi_payment',
    'credit_note', 'debit_note', 'quotation', 'journal_entry',
    'deal', 'shipment', 'clearance',
]


def heal_all_tenants(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    TenantSettings = apps.get_model('tenants', 'TenantSettings')
    Branch = apps.get_model('tenants', 'Branch')
    TenantBook = apps.get_model('tenants', 'TenantBook')
    Account = apps.get_model('accounting', 'Account')

    for tenant in Tenant.objects.all():
        TenantSettings.objects.get_or_create(
            tenant=tenant, defaults={'company_name_primary': tenant.CompanyName})

        if not Branch.objects.filter(tenant=tenant, is_main=True).exists():
            Branch.objects.create(
                tenant=tenant, name='الفرع الرئيسي', code='MAIN',
                is_main=True, is_active=True)

        if not Account.objects.filter(tenant=tenant).exists():
            account_map = {}
            for code, acc_name, acc_type, parent_code in COA_DATA:
                parent = account_map.get(parent_code) if parent_code else None
                account_map[code] = Account.objects.create(
                    tenant=tenant, code=code, name=acc_name,
                    account_type=acc_type, parent=parent, is_active=True)

        for doc_type in BOOK_DOC_TYPES:
            for book_number in range(1, 11):
                TenantBook.objects.get_or_create(
                    tenant=tenant, branch=None,
                    document_type=doc_type, book_number=book_number,
                    defaults={
                        'name': f'{doc_type} — دفتر {book_number}',
                        'last_used_number': 0, 'is_active': True,
                    })


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0007_branch_alter_tenantbook_unique_together_and_more'),
        ('accounting', '0022_journalheader_branch'),
    ]

    operations = [
        migrations.RunPython(heal_all_tenants, migrations.RunPython.noop),
    ]
