"""حجم استعمال كل شركة: حركاتها ومستنداتها ومستخدموها النشطون — SA-3.

سؤال المالك: «كم حركةً وكم مستنداً في هذه الشركة؟». الجواب سِجلُّ عدّاداتٍ واحد
(`USAGE_COUNTERS`) يُقرأ بـ`apps.get_model` — فلا يستورد `core` نماذج `sales`
و`logistics` و`inventory` استيراداً مباشراً، ويضاف مستندٌ جديد بسطرٍ هنا.

**الكلفة ثابتة مهما كثرت الشركات:** استعلامٌ مجمَّع واحد لكل عدّاد
(`GROUP BY tenant` يعدّ الكل وهذا الشهر وآخر تاريخ معاً) + استعلامٌ للمستخدمين
النشطين. والنتيجة لكل المنصة في الكاش عشر دقائق (`USAGE_CACHE_SECONDS`) مع وقت
حسابها — لا مجدول مهامّ في المشروع (لا Celery ولا cron)، فلقطةٌ يومية مخزّنة كانت
ستبقى بلا من يحدّثها. الأرقام تُعرض «آخر تحديث: …» ويُعاد حسابها بطلب.

الحركات = قيودٌ مرحّلة + حركات مخزون. المستندات = مجموع الباقي.
"""
from dataclasses import dataclass
from datetime import timedelta

from django.apps import apps
from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.utils import timezone

USAGE_CACHE_KEY = 'platform_usage:v1'
USAGE_CACHE_SECONDS = 600
ACTIVE_USER_DAYS = 30


@dataclass(frozen=True)
class UsageCounter:
    key: str
    label: str
    model: str          # 'app_label.ModelName'
    date_field: str     # حقل تاريخ المستند (DateField) — «هذا الشهر» وآخر تاريخ
    kind: str           # 'movement' | 'document'
    filters: tuple = ()  # أزواج (lookup, value) إضافية


USAGE_COUNTERS = (
    UsageCounter('journal_entries', 'قيود مرحّلة', 'accounting.JournalHeader',
                 'transaction_date', 'movement', (('is_posted', True),)),
    UsageCounter('stock_movements', 'حركات مخزون', 'inventory.StockMovement',
                 'movement_date', 'movement'),
    UsageCounter('sales_invoices', 'فواتير بيع', 'sales.SalesInvoice', 'invoice_date', 'document'),
    UsageCounter('sales_quotations', 'عروض أسعار', 'sales.SalesQuotation', 'quotation_date', 'document'),
    UsageCounter('sales_orders', 'طلبيات بيع', 'sales.SalesOrder', 'order_date', 'document'),
    UsageCounter('credit_debit_notes', 'إشعارات دائن/مدين', 'sales.CreditDebitNote', 'note_date', 'document'),
    UsageCounter('customer_payments', 'سندات قبض', 'sales.CustomerPayment', 'payment_date', 'document'),
    UsageCounter('supplier_payments', 'سندات صرف', 'sales.SupplierPayment', 'payment_date', 'document'),
    UsageCounter('purchase_invoices', 'فواتير شراء', 'logistics.PurchaseInvoice', 'invoice_date', 'document'),
    UsageCounter('import_deals', 'صفقات استيراد', 'logistics.LogisticsDeal', 'order_date', 'document'),
    UsageCounter('shipments', 'شحنات', 'logistics.LogisticsShipment', 'departure_date', 'document'),
)


def counter_catalog():
    return [{'key': c.key, 'label': c.label, 'kind': c.kind} for c in USAGE_COUNTERS]


def _empty_row():
    return {
        'counters': {c.key: {'total': 0, 'month': 0} for c in USAGE_COUNTERS},
        'movements_total': 0, 'movements_month': 0,
        'documents_total': 0, 'documents_month': 0,
        'active_users_30d': 0,
        'last_document_date': None,
    }


def compute_usage(tenant_ids=None) -> dict:
    """{tenant_id: صفّ الاستعمال}. `tenant_ids=None` = كل الشركات."""
    from core.models import ActivityLog
    from tenants.models import Tenant

    ids = list(tenant_ids) if tenant_ids is not None else list(
        Tenant.objects.values_list('TenantID', flat=True))
    rows = {tenant_id: _empty_row() for tenant_id in ids}
    if not ids:
        return rows
    month_start = timezone.localdate().replace(day=1)

    for counter in USAGE_COUNTERS:
        model = apps.get_model(counter.model)
        queryset = model.objects.filter(tenant_id__in=ids, **dict(counter.filters))
        grouped = (
            queryset.order_by().values('tenant_id').annotate(
                total=Count('pk'),
                month=Count('pk', filter=Q(**{f'{counter.date_field}__gte': month_start})),
                last=Max(counter.date_field),
            )
        )
        for item in grouped:
            row = rows.get(item['tenant_id'])
            if row is None:
                continue
            row['counters'][counter.key] = {'total': item['total'], 'month': item['month']}
            prefix = 'movements' if counter.kind == 'movement' else 'documents'
            row[f'{prefix}_total'] += item['total']
            row[f'{prefix}_month'] += item['month']
            if counter.kind == 'document' and item['last'] is not None:
                previous = row['last_document_date']
                row['last_document_date'] = max(previous, item['last']) if previous else item['last']

    since = timezone.now() - timedelta(days=ACTIVE_USER_DAYS)
    active = (
        ActivityLog.objects.filter(tenant_id__in=ids, timestamp__gte=since, user__isnull=False)
        .order_by().values('tenant_id').annotate(users=Count('user_id', distinct=True))
    )
    for item in active:
        if item['tenant_id'] in rows:
            rows[item['tenant_id']]['active_users_30d'] = item['users']
    return rows


def platform_usage(refresh=False) -> dict:
    """استعمال كل الشركات من الكاش أو محسوباً الآن: {computed_at, rows}."""
    if not refresh:
        cached = cache.get(USAGE_CACHE_KEY)
        if cached is not None:
            return cached
    payload = {'computed_at': timezone.now(), 'rows': compute_usage()}
    cache.set(USAGE_CACHE_KEY, payload, USAGE_CACHE_SECONDS)
    return payload
