# ISSUE #112 — يزرع دفاتر ترقيم «طلبية شراء (طلب عروض)» لكل شركة قائمة، على
# نمط 0008_heal_company_seed.py وأمر heal_company_seed تماماً: عشرة دفاتر
# لكل شركة (book_number 1..10)، idempotent عبر get_or_create. الترقيم الفعلي
# يستعمل book_number=0 افتراضياً (`TenantBook.get_next_number`) الذي يُخلق
# ذاتياً عند أوّل إرسال طلبية — هذه الهجرة تسوّي القائم مع القادم فحسب، ولا
# تُنشئ صفاً لشركة لم تُوجد بعد (شركة جديدة تُزرع عبر heal_company_seed نفسه
# الذي يقرأ TenantBook.DOCUMENT_TYPES فيلتقط النوع الجديد تلقائياً).
from django.db import migrations

DOC_TYPE = 'purchase_rfq'
DOC_LABEL = 'طلبية شراء (طلب عروض)'


def seed_purchase_rfq_book(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    TenantBook = apps.get_model('tenants', 'TenantBook')

    for tenant in Tenant.objects.all():
        for book_number in range(1, 11):
            TenantBook.objects.get_or_create(
                tenant=tenant, branch=None,
                document_type=DOC_TYPE, book_number=book_number,
                defaults={
                    'name': f'{DOC_LABEL} — دفتر {book_number}',
                    'last_used_number': 0, 'is_active': True,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0031_alter_tenantbook_document_type'),
    ]

    operations = [
        migrations.RunPython(seed_purchase_rfq_book, migrations.RunPython.noop),
    ]
