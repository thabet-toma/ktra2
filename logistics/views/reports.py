import datetime
import logging
from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, IntegrityError
from django.db.models import (
    Count, DecimalField, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date
from logistics.models import (
    SupplierQuotation,
    PurchaseOrder,
    LogisticsDeal, LogisticsDealItem, LogisticsShipment,
    LogisticsClearance, LogisticsShipmentDeal,
    LogisticsPayment, LogisticsClearancePayment,
    PurchaseInvoice, PurchaseInvoiceItem, PurchaseInvoiceFee, PurchaseInvoicePayment,
    LocalShipment, LocalShipmentPayment,
)
from sales.models import SupplierPayment
from logistics.serializers import (
    SupplierQuotationSerializer,
    PurchaseOrderSerializer,
    LogisticsDealSerializer, LogisticsDealListSerializer, LogisticsDealItemSerializer,
    LogisticsShipmentSerializer, LogisticsShipmentListSerializer, LogisticsClearanceSerializer,
    LogisticsPaymentSerializer,
    LogisticsClearancePaymentSerializer,
    PurchaseInvoiceSerializer, PurchaseInvoiceListSerializer,
    LocalShipmentSerializer, LocalShipmentPaymentSerializer, SupplierPaymentSerializer,
    PurchaseSettingsSerializer,
    GoodsReceiptSerializer,
    GoodsReceiptListSerializer,
)
from accounting.models import Account, TaxRate
from inventory.models import StockMovement
from partners.models import Partner
from tenants.models import Tenant, Currency
from accounting.models import JournalHeader, JournalLine, CashBoxLedgerAccount
from accounting import api as accounting_api
from accounting.cashbox import resolve_default_cash_box_account
from accounting.services import (
    annotate_partner_posted_balance,
    create_audit_log,
    get_exchange_rate,
    post_journal,
    unpost_document,
    validate_fiscal_period,
    next_document_number,
)
from logistics.accruals import (
    AccrualSkipped, post_clearance_accrual, post_freight_accrual,
    post_local_shipment_accrual,
)
from core.activity import (
    build_activity_changes,
    build_line_changes,
    describe_activity_changes,
    log_activity,
    log_view,
    snapshot_document_lines,
    snapshot_fields,
)
from core.api_defaults import PagePartnerBalanceMixin, POSTED_DOC_WARNING
from core.access import require_perm, requires_perm
from core.user_roles import user_can_unpost_logistics_deal_payment
from core.tenant_utils import get_tenant
from core.mixins import BaseTenantViewSet
from core.plans import enforce_limits
from logistics.landed_cost import (
    import_invoices_from_clearance,
    preview_landed_import,
    recalculate_landed_for_shipment,
    redistribute_shipment_deal_allocations,
    clearance_cost_line_dicts,
    build_import_trace,
)
from logistics.import_journey import build_import_journey_summary
from logistics.domain.shipment_builder import create_shipment_from_deals
from logistics.domain.stages import derive_stage
from logistics.services import (
    annotate_purchase_invoice_payment_summary,
    attach_pi_payment_voucher,
    convert_local_quotation_to_invoice,
    convert_local_quotation_to_order,
    convert_purchase_order_to_invoice,
)

logger = logging.getLogger("logistics.views")


# المرحلة 3: مرجع عبر الوحدات — auth/permission classes مشتركة (كان نفس الملف).
from .invoices import PurchaseInvoiceViewSet


class ImportJourneyViewSet(viewsets.ViewSet):
    """مرشد رحلة الاستيراد — وقائع الرحلات النشطة، يقرأها المرشد في كل الشاشات.

    نقطة واحدة خفيفة بدل أن يستجمع المرشد العام أربع قوائم كاملة (عروض، صفقات،
    شحنات، فواتير) في كل صفحة. قرار «الخطوة التالية» ليس هنا — انظر
    `logistics/import_journey.py`.

      - GET /api/logistics/import-journey/
    """

    authentication_classes = [
        *PurchaseInvoiceViewSet.authentication_classes,
    ]
    permission_classes = [
        *PurchaseInvoiceViewSet.permission_classes,
    ]

    def list(self, request):
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر.'}, status=status.HTTP_400_BAD_REQUEST)
        require_perm(request, 'import.deal.manage', tenant=tenant)
        return Response(build_import_journey_summary(tenant))


class LandedCostReportViewSet(viewsets.ViewSet):
    """تقرير التكلفة المستوردة (Landed Cost) للشحنات.

    يُجمّع بيانات الشحنة → الصفقات → فواتير الشراء → الرسوم → البنود،
    ويُظهر تفصيل:
      - تكلفة البضاعة (merchandise)
      - الشحن الدولي المُخصَّص (allocated shipping)
      - التخليص الجمركي (cost_lines + ClearancePayments)
      - الرسوم الإضافية (PurchaseInvoiceFee)
      - إجمالي التكلفة الحقيقية + تكلفة الوحدة لكل صنف (landed_unit_price_ils)

    الاستدعاءات:
      - GET /api/logistics/reports/landed-cost/                 → قائمة ملخّصة لكل الشحنات
      - GET /api/logistics/reports/landed-cost/?shipment_id=X   → تفصيل شحنة واحدة
    """

    authentication_classes = [
        *PurchaseInvoiceViewSet.authentication_classes,
    ]
    permission_classes = [
        *PurchaseInvoiceViewSet.permission_classes,
    ]

    def list(self, request):
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر.'}, status=status.HTTP_400_BAD_REQUEST)

        shipment_id = request.query_params.get('shipment_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        qs = LogisticsShipment.objects.filter(tenant=tenant, is_deleted=False)
        if shipment_id:
            qs = qs.filter(pk=shipment_id)
        if start_date:
            qs = qs.filter(arrival_date__gte=start_date)
        if end_date:
            qs = qs.filter(arrival_date__lte=end_date)

        # P1-2: `tenant` كان خارج select_related رغم أن باني الملخّص يقرأ
        # `shipment.tenant` أول سطر ⇒ استعلام إضافي لكل شحنة.
        qs = qs.select_related('shipping_agent', 'tenant').prefetch_related(
            'clearance',
            'clearance__payments',
            'deals',
        ).order_by('-arrival_date', '-id')

        # P1-2 (SCALABILITY_AUDIT §2-3): كان البناء يستعلم لكل شحنة على حدة —
        # روابط الصفقات (1) + بنود كل صفقة (1/رابط) + فاتورة الشراء المطابقة
        # بجلبها المسبق (4/رابط) ⇒ ~4,000 استعلام للـ200 شحنة. الآن كل ذلك
        # يُجلَب دفعةً واحدة قبل الحلقة، والحلقة تقرأ من خرائط في الذاكرة.
        shipments = list(qs[:200])  # safety limit
        links_map, pi_map = _prefetch_landed_cost_context(tenant, shipments)

        out = []
        for sh in shipments:
            out.append(_build_landed_cost_summary(
                sh, detailed=bool(shipment_id),
                links_map=links_map, pi_map=pi_map,
            ))

        return Response({
            'shipments': out,
            'count': len(out),
            'summary_only': not bool(shipment_id),
        })


def _prefetch_landed_cost_context(tenant, shipments):
    """P1-2: يجلب روابط الصفقات وفواتير الشراء لكل الشحنات باستعلامات ثابتة العدد.

    يُرجع خريطتين تقرأ منهما حلقة البناء بلا أي استعلام إضافي:
      - ``links_map``: shipment_id → [LogisticsShipmentDeal] (بصفقاتها وبنودها)
      - ``pi_map``: (shipment_id, deal_id) → PurchaseInvoice (ببنودها ورسومها)

    بنود الصفقة تُجلب عبر ``to_attr`` لأن ``deal.items.filter(is_deleted=False)``
    يتجاوز ذاكرة الـprefetch ويعيد الاستعلام لكل صفقة.
    """
    shipment_ids = [sh.id for sh in shipments]
    if not shipment_ids:
        return {}, {}

    links = (
        LogisticsShipmentDeal.objects
        .filter(shipment_id__in=shipment_ids)
        .select_related('deal', 'deal__partner', 'deal__currency')
        .prefetch_related(Prefetch(
            'deal__items',
            queryset=LogisticsDealItem.objects.filter(is_deleted=False)
                                              .select_related('product'),
            to_attr='_landed_active_items',
        ))
    )
    links_map = {}
    for link in links:
        links_map.setdefault(link.shipment_id, []).append(link)

    invoices = (
        PurchaseInvoice.objects
        .filter(tenant=tenant, shipment_id__in=shipment_ids)
        .select_related('currency')
        .prefetch_related('items', 'fees', 'fees__expense_account')
    )
    pi_map = {(pi.shipment_id, pi.deal_id): pi for pi in invoices}

    return links_map, pi_map


def _build_landed_cost_summary(shipment, *, detailed=False, links_map=None, pi_map=None):
    """يبني ملخّص Landed Cost لشحنة واحدة.

    ``links_map``/``pi_map`` اختياريتان: تمرّرهما القائمة بعد جلب جماعي واحد
    (P1-2)، وغيابهما يُبقي المسار المستقل (شحنة واحدة) يستعلم لنفسه.
    """
    from decimal import Decimal

    tenant = shipment.tenant

    # الصفقات المرتبطة
    if links_map is not None:
        links = links_map.get(shipment.id, [])
    else:
        links = LogisticsShipmentDeal.objects.filter(shipment=shipment).select_related(
            'deal', 'deal__partner', 'deal__currency',
        )

    deals_data = []
    total_merchandise = Decimal('0')
    total_allocated_shipping = Decimal('0')

    for link in links:
        deal = link.deal
        # P1-2: البنود مجلوبة مسبقاً في `_landed_active_items` عند المرور الجماعي.
        items = getattr(deal, '_landed_active_items', None)
        if items is None:
            items = deal.items.select_related('product').filter(is_deleted=False) if hasattr(deal, 'items') else []
        deal_merch = sum(
            (Decimal(str(i.quantity or 0)) * Decimal(str(i.unit_price or 0)) for i in items),
            Decimal('0'),
        )
        total_merchandise += deal_merch
        total_allocated_shipping += Decimal(str(link.allocated_shipping_cost or 0))

        # فاتورة الشراء المرتبطة بهذه الصفقة + الشحنة
        if pi_map is not None:
            pi = pi_map.get((shipment.id, deal.id))
        else:
            pi = PurchaseInvoice.objects.filter(
                tenant=tenant, shipment=shipment, deal=deal,
            ).select_related('currency').prefetch_related(
                'items', 'fees', 'fees__expense_account',
            ).first()

        pi_items_rows = []
        pi_fees_rows = []
        pi_capitalized_total = Decimal('0')
        pi_expensed_total = Decimal('0')

        if pi:
            for fee in pi.fees.all():
                amt = Decimal(str(fee.amount or 0))
                row = {
                    'id': fee.id,
                    'description': fee.description,
                    'amount': float(amt),
                    'account_code': fee.expense_account.code if fee.expense_account else None,
                    'account_name': fee.expense_account.name if fee.expense_account else None,
                    'capitalize_to_inventory': fee.capitalize_to_inventory,
                }
                pi_fees_rows.append(row)
                if fee.capitalize_to_inventory:
                    pi_capitalized_total += amt
                else:
                    pi_expensed_total += amt

            for it in pi.items.all():
                pi_items_rows.append({
                    'id': it.id,
                    'product_id': it.product_id,
                    'name': it.name,
                    'quantity': float(it.quantity or 0),
                    'unit_price': float(it.unit_price or 0),
                    'total_price': float(it.total_price or 0),
                    'landed_unit_price_ils': float(it.landed_unit_price_ils or 0) if it.landed_unit_price_ils is not None else None,
                    'landed_line_total_ils': float(it.landed_line_total_ils or 0) if it.landed_line_total_ils is not None else None,
                })

        deals_data.append({
            'deal_id': deal.id,
            'ref_number': deal.ref_number,
            'partner_name': deal.partner.name if deal.partner else None,
            'currency': deal.currency.Code if deal.currency else None,
            'merchandise_total': float(deal_merch),
            'allocated_shipping_cost_usd': float(link.allocated_shipping_cost or 0),
            'extra_costs_usd': float(link.extra_costs or 0),
            'purchase_invoice': {
                'id': pi.id if pi else None,
                'invoice_number': pi.invoice_number if pi else None,
                'currency': pi.currency.Code if pi and pi.currency else None,
                'exchange_rate': float(pi.exchange_rate) if pi and pi.exchange_rate else 1.0,
                'is_posted': bool(pi.is_posted) if pi else False,
                'capitalized_fees_total': float(pi_capitalized_total),
                'expensed_fees_total': float(pi_expensed_total),
                'items': pi_items_rows if detailed else [],
                'fees': pi_fees_rows if detailed else [],
                'items_count': len(pi_items_rows),
                'fees_count': len(pi_fees_rows),
            } if pi else None,
            'items_count': len(items) if hasattr(items, '__len__') else items.count(),
        })

    # بيانات التخليص
    clearance_data = None
    clearance_total = Decimal('0')
    try:
        cl = shipment.clearance
    except Exception:
        cl = None
    if cl:
        cost_lines = []
        if True:
            for ln in clearance_cost_line_dicts(cl):
                if not isinstance(ln, dict):
                    continue
                try:
                    amt = Decimal(str(ln.get('amount') or 0))
                except Exception:
                    amt = Decimal('0')
                cost_lines.append({
                    'label': ln.get('label') or '',
                    'amount': float(amt),
                })
                clearance_total += amt

        posted_payments_total = sum(
            (Decimal(str(p.amount or 0)) for p in cl.payments.all() if p.is_posted),
            Decimal('0'),
        )

        clearance_data = {
            'id': cl.id,
            'declaration_number': cl.declaration_number,
            'clearance_date': cl.clearance_date.isoformat() if cl.clearance_date else None,
            'status': cl.status,
            'cost_lines': cost_lines,
            'cost_lines_total': float(clearance_total),
            'posted_payments_total': float(posted_payments_total),
            'broker_name': cl.customs_broker.name if cl.customs_broker else None,
        }

    # إجمالي Landed Cost = بضاعة + شحن مُخصَّص + تخليص + رسوم مرسملة
    cap_fees_total = sum(
        (Decimal(str(d['purchase_invoice']['capitalized_fees_total'])) if d['purchase_invoice'] else Decimal('0'))
        for d in deals_data
    )
    exp_fees_total = sum(
        (Decimal(str(d['purchase_invoice']['expensed_fees_total'])) if d['purchase_invoice'] else Decimal('0'))
        for d in deals_data
    )

    # محاولة حساب total shipping بـ USD — من total_shipping_cost_usd
    total_shipping = Decimal(str(shipment.total_shipping_cost_usd or 0))

    grand_landed = total_merchandise + total_shipping + clearance_total + cap_fees_total

    return {
        'shipment_id': shipment.id,
        'shipment_number': shipment.shipment_number,
        'status': shipment.status,
        'arrival_date': shipment.arrival_date.isoformat() if shipment.arrival_date else None,
        'shipping_agent': shipment.shipping_agent.name if shipment.shipping_agent else None,
        'shipping_type': shipment.shipping_type,
        'total_merchandise': float(total_merchandise),
        'total_shipping_cost_usd': float(total_shipping),
        'allocated_shipping_total_usd': float(total_allocated_shipping),
        'clearance_total': float(clearance_total),
        'capitalized_fees_total': float(cap_fees_total),
        'expensed_fees_total': float(exp_fees_total),
        'grand_landed_cost_approx': float(grand_landed),
        'deals': deals_data,
        'clearance': clearance_data,
    }


