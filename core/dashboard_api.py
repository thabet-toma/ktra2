"""Tenant-scoped business dashboard API."""
import calendar
import datetime
import logging

from django.core.cache import cache
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounting.models import JournalHeader, JournalLine
from core.access import user_tenant_role
from core.import_access import user_can_access_import
from core.tenant_utils import get_tenant as _get_tenant
from inventory.models import Product, StockMovement
from logistics.models import LogisticsDeal, LogisticsPayment, LogisticsShipment, PurchaseInvoice
from sales.models import SalesInvoice
from tenants.models import TenantSettings


logger = logging.getLogger(__name__)


def _f(value):
    if value is None:
        return 0.0
    return round(float(value), 2)


DASHBOARD_CACHE_TTL = 60


def _month_anchor(year, month, start_day):
    return datetime.date(
        year,
        month,
        min(start_day, calendar.monthrange(year, month)[1]),
    )


def _dashboard_period(tenant):
    today = timezone.localdate()
    start_day = 1
    if tenant is not None:
        configured_day = (
            TenantSettings.objects.filter(tenant=tenant)
            .values_list("dashboard_month_start_day", flat=True)
            .first()
        )
        if configured_day:
            start_day = configured_day

    period_start = _month_anchor(today.year, today.month, start_day)
    if period_start > today:
        if today.month == 1:
            period_start = _month_anchor(today.year - 1, 12, start_day)
        else:
            period_start = _month_anchor(today.year, today.month - 1, start_day)
    return period_start, today


def _invoice_summary(queryset, *, partner_field, date_field):
    total = queryset.count()
    posted = queryset.filter(status__in=["posted", "completed", "fully_paid"]).count()
    draft = queryset.filter(status__in=["draft", "incomplete"]).count()
    recent = list(
        queryset.order_by(f"-{date_field}", "-id")[:5].values(
            "id",
            "invoice_number",
            "status",
            "grand_total",
            date_field,
            partner_name=F(partner_field),
            currency_code=F("currency__Code"),
        )
    )
    return {
        "total": total,
        "posted": posted,
        "draft": draft,
        "recent": recent,
    }


@api_view(["GET"])
def trade_dashboard(request):
    """Return the active company's general KPIs and optional import KPIs.

    Import tables are deliberately not queried when the company has not enabled
    that module. This keeps the base dashboard relevant and makes the feature
    boundary enforceable at the API layer, not merely hidden in React.
    """
    tenant = _get_tenant(request)
    # T-DASHPERIOD: ملخص الشركة المالي محصور بالمدير نفسه، ولا تفتحه منحة صلاحية
    # قديمة محفوظة لدور أو عضو. بلا شركة محلولة تبقى استجابة الأصفار المعزولة.
    role = user_tenant_role(request.user, tenant) if tenant is not None else ""
    if tenant is not None and role != "manager":
        logger.warning(
            "dashboard access denied tenant=%s user=%s role=%s",
            tenant.TenantID,
            getattr(request.user, "pk", None),
            role,
        )
        raise PermissionDenied("ملخص لوحة الأعمال متاح لمدير الشركة فقط.")
    can_access_import = user_can_access_import(request.user, tenant)
    period_start, period_end = _dashboard_period(tenant)
    tenant_key = tenant.pk if tenant else "none"
    cache_key = (
        f"dashboard:v5:{tenant_key}:{period_start.isoformat()}:"
        f"{period_end.isoformat()}:import-{int(can_access_import)}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    sales_base_qs = (
        SalesInvoice.objects.filter(
            tenant=tenant,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        ).exclude(status=SalesInvoice.STATUS_CANCELLED)
        if tenant
        else SalesInvoice.objects.none()
    )
    purchase_base_qs = (
        PurchaseInvoice.objects.filter(tenant=tenant)
        if tenant
        else PurchaseInvoice.objects.none()
    )
    # An international invoice is part of the import workflow. A company that
    # has not enabled import sees only its ordinary local purchase invoices.
    if not can_access_import:
        purchase_base_qs = purchase_base_qs.filter(
            invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL
        )

    sales_qs = sales_base_qs.filter(
        invoice_date__gte=period_start,
        invoice_date__lte=period_end,
    )
    purchase_qs = purchase_base_qs.filter(
        invoice_date__gte=period_start,
        invoice_date__lte=period_end,
    )

    sales_invoices = _invoice_summary(
        sales_qs, partner_field="customer__name", date_field="invoice_date"
    )
    purchase_invoices = _invoice_summary(
        purchase_qs, partner_field="partner__name", date_field="invoice_date"
    )

    prod_qs = Product.objects.filter(tenant=tenant) if tenant else Product.objects.none()
    total_products = prod_qs.count()
    products_in_stock = prod_qs.filter(quantity_on_hand__gt=0).count()
    inventory_value = _f(
        prod_qs.filter(quantity_on_hand__gt=0).aggregate(
            value=Sum(F("quantity_on_hand") * F("avg_cost"))
        )["value"]
    )
    # T-REORDER: العدّادان من `inventory.stock_status` وحدها. كان «نفذ» يفلتر
    # `min_stock_level__gt=0` قبل العدّ — فمنتجٌ نفد ولا حدّ أدنى له لا يُعدّ
    # نافداً إطلاقاً، وهو معظم الكتالوج. رقمٌ كاذبٌ بالنقصان يقرأه المالك كل صباح.
    from inventory.stock_status import (
        STATUS_LOW, STATUS_OUT_OF_STOCK, filter_by_stock_status,
    )

    reserved_map = {}
    if tenant:
        from sales.services import reserved_quantity_map

        reserved_map = reserved_quantity_map(tenant.TenantID)
    low_stock_qs = filter_by_stock_status(prod_qs, STATUS_LOW, reserved_map=reserved_map)
    low_stock = low_stock_qs.count()
    out_of_stock = filter_by_stock_status(
        prod_qs, STATUS_OUT_OF_STOCK, reserved_map=reserved_map
    ).count()
    movements_qs = (
        StockMovement.objects.filter(tenant=tenant)
        if tenant
        else StockMovement.objects.none()
    )
    low_stock_items = list(
        low_stock_qs.values(
            "id", "sku", "name_ar", "quantity_on_hand", "min_stock_level"
        )[:5]
    )

    posted_lines = (
        JournalLine.objects.filter(
            tenant=tenant,
            journal__tenant=tenant,
            journal__is_posted=True,
            journal__transaction_date__gte=period_start,
            journal__transaction_date__lte=period_end,
        )
        if tenant
        else JournalLine.objects.none()
    )
    financial_totals = posted_lines.aggregate(
        revenue_credit=Sum("base_credit", filter=Q(account__account_type="Revenue")),
        revenue_debit=Sum("base_debit", filter=Q(account__account_type="Revenue")),
        expense_debit=Sum("base_debit", filter=Q(account__account_type="Expense")),
        expense_credit=Sum("base_credit", filter=Q(account__account_type="Expense")),
    )
    revenue = _f(
        (financial_totals["revenue_credit"] or 0)
        - (financial_totals["revenue_debit"] or 0)
    )
    expenses = _f(
        (financial_totals["expense_debit"] or 0)
        - (financial_totals["expense_credit"] or 0)
    )
    journals_qs = (
        JournalHeader.objects.filter(tenant=tenant)
        if tenant
        else JournalHeader.objects.none()
    )

    alerts = []
    if low_stock:
        alerts.append({
            "type": "warning",
            "title": "مخزون منخفض",
            "message": f"{low_stock} منتج تحت الحد الأدنى",
            "link": "stock-levels",
        })
    if out_of_stock:
        alerts.append({
            "type": "danger",
            "title": "منتجات نافدة",
            "message": f"{out_of_stock} منتج يحتاج إلى إعادة طلب",
            "link": "stock-levels",
        })
    if sales_invoices["draft"]:
        alerts.append({
            "type": "info",
            "title": "فواتير بيع غير مكتملة",
            "message": f"{sales_invoices['draft']} فاتورة بانتظار الترحيل",
            "link": "sales-invoices",
        })
    if purchase_invoices["draft"]:
        alerts.append({
            "type": "info",
            "title": "فواتير شراء غير مكتملة",
            "message": f"{purchase_invoices['draft']} فاتورة بحاجة للمراجعة",
            "link": "purchase-invoices",
        })

    payload = {
        "period": {"from": period_start.isoformat(), "to": period_end.isoformat()},
        "is_new_company": not (
            sales_base_qs.exists()
            or purchase_base_qs.exists()
            or prod_qs.exists()
            or journals_qs.exists()
        ),
        "financials": {
            "revenue": revenue,
            "expenses": expenses,
            "net_profit": _f(revenue - expenses),
        },
        "sales_invoices": sales_invoices,
        "purchase_invoices": purchase_invoices,
        "inventory": {
            "total_products": total_products,
            "in_stock": products_in_stock,
            "low_stock": low_stock,
            "out_of_stock": out_of_stock,
            "inventory_value": inventory_value,
            "movements_this_month": movements_qs.filter(
                movement_date__gte=period_start,
                movement_date__lte=period_end,
            ).count(),
            "low_stock_items": low_stock_items,
        },
        "accounting": {
            "journals_this_month": journals_qs.filter(
                transaction_date__gte=period_start,
                transaction_date__lte=period_end,
                is_posted=True,
            ).count(),
        },
        "alerts": alerts,
    }

    if can_access_import:
        deals_qs = LogisticsDeal.objects.filter(
            tenant=tenant, is_deleted=False
        )
        shipments_qs = LogisticsShipment.objects.filter(tenant=tenant)
        # P1-5: كان `Q(deal__tenant) | Q(shipment__tenant)` — ضمّتان وOR على
        # المسار الساخن للداشبورد. الحقل المباشر يغني عن الضمّتين.
        payments_qs = LogisticsPayment.objects.filter(
            is_deleted=False, tenant=tenant,
        )
        payload["import_operations"] = {
            "deals": {
                "open": deals_qs.filter(status="Open").count(),
                "active_value": _f(
                    deals_qs.filter(status__in=["Open", "Shipped", "Cleared"])
                    .aggregate(total=Sum("total_amount"))["total"]
                ),
                "status_distribution": list(
                    deals_qs.values("status")
                    .annotate(count=Count("id"))
                    .order_by("status")
                ),
            },
            "shipments": {
                "in_transit": shipments_qs.filter(status="In-Transit").count(),
                "clearing": shipments_qs.filter(status="Clearing").count(),
            },
            "payments": {
                "paid_this_month": _f(
                    payments_qs.filter(
                        is_posted=True,
                        transfer_date__gte=period_start,
                        transfer_date__lte=period_end,
                    ).aggregate(total=Sum("amount"))["total"]
                ),
            },
        }

    cache.set(cache_key, payload, timeout=DASHBOARD_CACHE_TTL)
    return Response(payload)
