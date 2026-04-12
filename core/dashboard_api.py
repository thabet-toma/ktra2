"""
Trade Dashboard API — single endpoint returning all business KPIs.
"""
import datetime
from decimal import Decimal

from django.db.models import Sum, Count, Q, F
from rest_framework.decorators import api_view
from rest_framework.response import Response

from tenants.models import Tenant
from core.tenant_utils import get_tenant as _get_tenant
from logistics.models import (
    LogisticsDeal, LogisticsShipment, LogisticsPayment,
    PurchaseInvoice,
)
from inventory.models import Product, StockMovement
from accounting.models import JournalHeader


def _f(val):
    """Decimal/None → float."""
    if val is None:
        return 0.0
    return round(float(val), 2)


@api_view(['GET'])
def trade_dashboard(request):
    tenant = _get_tenant(request)
    today = datetime.date.today()
    month_start = today.replace(day=1)

    # ─── Deals ───────────────────────────────────────────────────
    deals_qs = LogisticsDeal.objects.filter(is_deleted=False)
    total_deals = deals_qs.count()
    open_deals = deals_qs.filter(status='Open').count()
    shipped_deals = deals_qs.filter(status='Shipped').count()
    cleared_deals = deals_qs.filter(status='Cleared').count()
    closed_deals = deals_qs.filter(status='Closed').count()

    open_deals_value = _f(
        deals_qs.filter(status__in=['Open', 'Shipped', 'Cleared'])
        .aggregate(s=Sum('total_amount'))['s']
    )

    deals_this_month = deals_qs.filter(order_date__gte=month_start).count()

    deal_status_dist = list(
        deals_qs.values('status')
        .annotate(count=Count('id'))
        .order_by('status')
    )

    recent_deals = list(
        deals_qs.order_by('-created_at')[:5]
        .values('id', 'ref_number', 'status', 'total_amount', 'order_date',
                partner_name=F('partner__name'))
    )

    # ─── Shipments ───────────────────────────────────────────────
    ship_qs = LogisticsShipment.objects.all()
    total_shipments = ship_qs.count()
    in_transit = ship_qs.filter(status='In-Transit').count()
    arrived = ship_qs.filter(status='Arrived').count()
    clearing = ship_qs.filter(status='Clearing').count()
    cleared_shipments = ship_qs.filter(status='Cleared').count()

    recent_shipments = list(
        ship_qs.order_by('-id')[:5]
        .values('id', 'shipment_number', 'status', 'departure_date',
                'arrival_date', 'total_shipping_cost_usd')
    )

    # ─── Payments ────────────────────────────────────────────────
    pay_qs = LogisticsPayment.objects.filter(is_deleted=False)
    total_payments = pay_qs.count()
    posted_payments = pay_qs.filter(is_posted=True).count()
    total_paid = _f(
        pay_qs.filter(is_posted=True).aggregate(s=Sum('amount'))['s']
    )
    paid_this_month = _f(
        pay_qs.filter(is_posted=True, transfer_date__gte=month_start)
        .aggregate(s=Sum('amount'))['s']
    )

    # ─── Invoices (SQL) ──────────────────────────────────────────
    inv_qs = PurchaseInvoice.objects.all()
    total_invoices = inv_qs.count()
    posted_invoices = inv_qs.filter(is_posted=True).count()
    draft_invoices = inv_qs.filter(status='draft').count()
    invoices_total_value = _f(
        inv_qs.aggregate(s=Sum('grand_total'))['s']
    )

    recent_invoices = list(
        inv_qs.order_by('-created_at')[:5]
        .values('id', 'invoice_number', 'status', 'grand_total',
                'invoice_date', partner_name=F('partner__name'))
    )

    # ─── Inventory ───────────────────────────────────────────────
    products_in_stock = Product.objects.filter(quantity_on_hand__gt=0).count()
    total_products = Product.objects.count()
    inventory_value = _f(
        Product.objects.filter(quantity_on_hand__gt=0)
        .aggregate(
            val=Sum(F('quantity_on_hand') * F('avg_cost'))
        )['val']
    )
    low_stock = Product.objects.filter(
        quantity_on_hand__gt=0,
        min_stock_level__gt=0,
        quantity_on_hand__lte=F('min_stock_level'),
    ).count()
    out_of_stock = Product.objects.filter(
        min_stock_level__gt=0,
        quantity_on_hand__lte=0,
    ).count()

    movements_this_month = StockMovement.objects.filter(
        movement_date__gte=month_start,
    ).count()

    low_stock_items = list(
        Product.objects.filter(
            quantity_on_hand__gt=0,
            min_stock_level__gt=0,
            quantity_on_hand__lte=F('min_stock_level'),
        ).values('id', 'sku', 'name_ar', 'quantity_on_hand', 'min_stock_level')[:10]
    )

    # ─── Accounting ──────────────────────────────────────────────
    journals_this_month = JournalHeader.objects.filter(
        transaction_date__gte=month_start, is_posted=True,
    ).count()

    # ─── Alerts ──────────────────────────────────────────────────
    alerts = []

    if low_stock > 0:
        alerts.append({
            'type': 'warning',
            'title': 'مخزون منخفض',
            'message': f'{low_stock} منتج/أصناف تحت الحد الأدنى',
            'link': 'stock-levels',
        })

    if out_of_stock > 0:
        alerts.append({
            'type': 'danger',
            'title': 'نفاد مخزون',
            'message': f'{out_of_stock} منتج نفذت كميته',
            'link': 'stock-levels',
        })

    if in_transit > 0:
        alerts.append({
            'type': 'info',
            'title': 'شحنات في الطريق',
            'message': f'{in_transit} شحنة قيد النقل',
            'link': 'shipments-management',
        })

    if draft_invoices > 0:
        alerts.append({
            'type': 'info',
            'title': 'فواتير مسودة',
            'message': f'{draft_invoices} فاتورة بحاجة لإكمال',
            'link': 'purchase-invoices',
        })

    unpaid_deals = deals_qs.filter(
        payment_status__in=['Unpaid', 'Partially Paid'],
        status__in=['Open', 'Shipped', 'Cleared'],
    ).count()
    if unpaid_deals > 0:
        alerts.append({
            'type': 'warning',
            'title': 'صفقات غير مسددة',
            'message': f'{unpaid_deals} صفقة بحاجة لدفعات',
            'link': 'deals-management',
        })

    return Response({
        'deals': {
            'total': total_deals,
            'open': open_deals,
            'shipped': shipped_deals,
            'cleared': cleared_deals,
            'closed': closed_deals,
            'open_value': open_deals_value,
            'this_month': deals_this_month,
            'status_distribution': deal_status_dist,
            'recent': recent_deals,
        },
        'shipments': {
            'total': total_shipments,
            'in_transit': in_transit,
            'arrived': arrived,
            'clearing': clearing,
            'cleared': cleared_shipments,
            'recent': recent_shipments,
        },
        'payments': {
            'total': total_payments,
            'posted': posted_payments,
            'total_paid': total_paid,
            'paid_this_month': paid_this_month,
        },
        'invoices': {
            'total': total_invoices,
            'posted': posted_invoices,
            'draft': draft_invoices,
            'total_value': invoices_total_value,
            'recent': recent_invoices,
        },
        'inventory': {
            'total_products': total_products,
            'in_stock': products_in_stock,
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
            'inventory_value': inventory_value,
            'movements_this_month': movements_this_month,
            'low_stock_items': low_stock_items,
        },
        'accounting': {
            'journals_this_month': journals_this_month,
        },
        'alerts': alerts,
    })
