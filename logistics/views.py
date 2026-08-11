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
from .models import (
    SupplierQuotation,
    PurchaseOrder,
    LogisticsDeal, LogisticsDealItem, LogisticsShipment,
    LogisticsClearance, LogisticsShipmentDeal,
    LogisticsPayment, LogisticsClearancePayment,
    PurchaseInvoice, PurchaseInvoiceItem, PurchaseInvoiceFee, PurchaseInvoicePayment,
    LocalShipment, LocalShipmentPayment,
)
from sales.models import SupplierPayment
from .serializers import (
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
from .accruals import (
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
from .landed_cost import (
    import_invoices_from_clearance,
    preview_landed_import,
    recalculate_landed_for_shipment,
    redistribute_shipment_deal_allocations,
    clearance_cost_line_dicts,
    build_import_trace,
)
from .import_journey import build_import_journey_summary
from .domain.shipment_builder import create_shipment_from_deals
from .domain.stages import derive_stage
from .services import (
    annotate_purchase_invoice_payment_summary,
    attach_pi_payment_voucher,
    convert_local_quotation_to_invoice,
    convert_local_quotation_to_order,
    convert_import_quotation_to_deal,
    convert_purchase_order_to_invoice,
)

logger = logging.getLogger(__name__)


class SupplierQuotationViewSet(BaseTenantViewSet):
    serializer_class = SupplierQuotationSerializer
    queryset = SupplierQuotation.objects.all()

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related('tenant', 'supplier', 'currency', 'created_by')
            .prefetch_related('lines__product')
        )
        scope = str(self.request.query_params.get('scope') or '').strip()
        quote_status = str(self.request.query_params.get('status') or '').strip()
        supplier = str(self.request.query_params.get('supplier') or '').strip()
        search = str(self.request.query_params.get('search') or '').strip()
        if scope:
            qs = qs.filter(scope=scope)
        if quote_status:
            qs = qs.filter(status=quote_status)
        if supplier.isdigit():
            qs = qs.filter(supplier_id=int(supplier))
        if search:
            qs = qs.filter(
                Q(quotation_number__icontains=search)
                | Q(order_name__icontains=search)
                | Q(order_description__icontains=search)
                | Q(supplier__name__icontains=search)
                | Q(supplier__legal_name__icontains=search)
                | Q(supplier_draft_name__icontains=search)
                | Q(lines__name_snapshot__icontains=search)
                | Q(lines__description_line__icontains=search)
                | Q(lines__product__name_ar__icontains=search)
                | Q(lines__product__name_en__icontains=search)
            ).distinct()
        return qs.order_by('-quotation_date', '-id')

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        kwargs = {'tenant': tenant}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user
        number = str(serializer.validated_data.get('quotation_number') or '').strip()
        if not number:
            scope = serializer.validated_data.get('scope', SupplierQuotation.SCOPE_LOCAL)
            prefix = 'IQ' if scope == SupplierQuotation.SCOPE_IMPORT else 'PQ'
            sequence = next_document_number(
                tenant.pk, f'supplier_quotation_{scope}',
            )
            kwargs['quotation_number'] = f'{prefix}-{sequence:04d}'
        quotation = serializer.save(**kwargs)
        log_activity(
            action='create',
            entity_type='supplier_quotation',
            entity_id=quotation.id,
            entity_label=quotation.quotation_number,
            description='إنشاء عرض سعر مورد',
            request=self.request,
            # T-DRAFTPARTY: المورد قد يكون مبدئياً (بلا شريك مسجّل) فلا ربط له.
            partner_ids=[quotation.supplier_id] if quotation.supplier_id else [],
        )

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        quotation = serializer.save()
        # T-IMPOFFER: قرار الملاءمة حدث تجاري لا تحريرٌ عابر — يُسجَّل بسببه كي
        # يُقرأ لاحقاً «لماذا رُفض هذا المورد» من سجل النشاط لا من الذاكرة.
        # T-OFFERSTATE: حالتا الانتظار والمناقشة تُسجَّلان أيضاً — «بانتظار ماذا»
        # سؤالٌ يُسأل بعد أسبوعين، فيجب أن يبقى له أثر لا ذاكرة.
        status_labels = {
            SupplierQuotation.STATUS_ACCEPTED: 'ملائم',
            SupplierQuotation.STATUS_REJECTED: 'غير ملائم',
            SupplierQuotation.STATUS_PENDING_INFO: 'بانتظار معلومات',
            SupplierQuotation.STATUS_UNDER_DISCUSSION: 'قيد المناقشة',
        }
        if quotation.status != previous_status and quotation.status in status_labels:
            label = status_labels[quotation.status]
            logger.info(
                'supplier_quotation.status id=%s scope=%s status=%s reason=%r',
                quotation.pk, quotation.scope, quotation.status,
                quotation.decision_reason,
            )
            log_activity(
                action='update',
                entity_type='supplier_quotation',
                entity_id=quotation.pk,
                entity_label=quotation.quotation_number,
                description=(
                    f'حالة عرض السعر: {label}'
                    + (f' — {quotation.decision_reason}' if quotation.decision_reason else '')
                ),
                request=self.request,
                partner_ids=[quotation.supplier_id] if quotation.supplier_id else [],
                metadata={'status': quotation.status},
            )

    def perform_destroy(self, instance):
        if instance.status == SupplierQuotation.STATUS_CONVERTED:
            raise ValidationError('عرض السعر المحوّل لا يمكن حذفه.')
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'], url_path='convert-to-import-deal')
    def convert_to_import_deal(self, request, pk=None):
        quotation = self.get_object()
        try:
            deal, created = convert_import_quotation_to_deal(
                quotation,
                user=request.user,
            )
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or getattr(
                exc, 'messages', None,
            ) or [str(exc)]
            raise ValidationError(detail)

        if created:
            log_activity(
                action='convert',
                entity_type='supplier_quotation',
                entity_id=quotation.id,
                entity_label=quotation.quotation_number,
                description=f'تحويل عرض السعر إلى طلبية {deal.ref_number}',
                request=request,
                partner_ids=[deal.partner_id],
                metadata={'deal_id': deal.id, 'deal_ref_number': deal.ref_number},
            )
        payload = {
            'status': 'converted',
            'created': created,
            'deal': LogisticsDealSerializer(deal, context={'request': request}).data,
        }
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='convert-to-purchase-order')
    def convert_to_purchase_order(self, request, pk=None):
        quotation = self.get_object()
        try:
            order, created = convert_local_quotation_to_order(
                quotation,
                user=request.user,
            )
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or getattr(
                exc, 'messages', None,
            ) or [str(exc)]
            raise ValidationError(detail)
        if created:
            log_activity(
                action='convert',
                entity_type='supplier_quotation',
                entity_id=quotation.id,
                entity_label=quotation.quotation_number,
                description=f'تحويل عرض السعر إلى طلبية {order.order_number}',
                request=request,
                partner_ids=[order.supplier_id],
                metadata={'purchase_order_id': order.id},
            )
        return Response(
            {
                'status': 'converted',
                'created': created,
                'order': PurchaseOrderSerializer(
                    order, context={'request': request},
                ).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='convert-to-purchase-invoice')
    def convert_to_purchase_invoice(self, request, pk=None):
        """T-PLINEAGE: عرض شراء محلي مقبول → فاتورة شراء مسودة مباشرةً."""
        quotation = self.get_object()
        try:
            invoice, created = convert_local_quotation_to_invoice(
                quotation,
                user=request.user,
            )
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or getattr(
                exc, 'messages', None,
            ) or [str(exc)]
            raise ValidationError(detail)
        if created:
            log_activity(
                action='convert',
                entity_type='supplier_quotation',
                entity_id=quotation.id,
                entity_label=quotation.quotation_number,
                description=f'تحويل عرض السعر إلى فاتورة شراء {invoice.invoice_number}',
                request=request,
                partner_ids=[invoice.partner_id],
                metadata={'purchase_invoice_id': invoice.id},
            )
        return Response(
            {
                'status': 'converted',
                'created': created,
                'invoice': {
                    'id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                },
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PurchaseOrderViewSet(BaseTenantViewSet):
    serializer_class = PurchaseOrderSerializer
    queryset = PurchaseOrder.objects.all()

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related(
                'tenant', 'supplier', 'quotation', 'invoice', 'currency', 'created_by',
            )
            .prefetch_related('lines__product')
        )
        order_status = str(self.request.query_params.get('status') or '').strip()
        supplier = str(self.request.query_params.get('supplier') or '').strip()
        search = str(self.request.query_params.get('search') or '').strip()
        if order_status:
            qs = qs.filter(status=order_status)
        if supplier.isdigit():
            qs = qs.filter(supplier_id=int(supplier))
        if search:
            qs = qs.filter(
                Q(order_number__icontains=search)
                | Q(supplier__name__icontains=search)
                | Q(supplier__legal_name__icontains=search)
                | Q(lines__name_snapshot__icontains=search)
                | Q(lines__product__name_ar__icontains=search)
                | Q(lines__product__name_en__icontains=search)
            ).distinct()
        return qs.order_by('-order_date', '-id')

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        kwargs = {'tenant': tenant}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user
        number = str(serializer.validated_data.get('order_number') or '').strip()
        if not number:
            sequence = next_document_number(tenant.pk, 'purchase_order')
            kwargs['order_number'] = f'PO-{sequence:04d}'
        order = serializer.save(**kwargs)
        log_activity(
            action='create',
            entity_type='purchase_order',
            entity_id=order.id,
            entity_label=order.order_number,
            description='إنشاء طلبية شراء',
            request=self.request,
            partner_ids=[order.supplier_id],
        )

    def perform_destroy(self, instance):
        if instance.status != PurchaseOrder.STATUS_DRAFT:
            raise ValidationError('يمكن حذف طلبية الشراء المسودة فقط.')
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        with transaction.atomic():
            order = PurchaseOrder.objects.select_for_update().get(
                pk=self.get_object().pk,
                tenant=get_tenant(request),
            )
            if order.status == PurchaseOrder.STATUS_CONFIRMED:
                return Response(PurchaseOrderSerializer(
                    order, context={'request': request},
                ).data)
            if order.status != PurchaseOrder.STATUS_DRAFT:
                raise ValidationError('يمكن تأكيد الطلبية المسودة فقط.')
            if not order.lines.exists():
                raise ValidationError('لا يمكن تأكيد طلبية بلا أصناف.')
            order.status = PurchaseOrder.STATUS_CONFIRMED
            order.save(update_fields=['status', 'updated_at'])
        return Response(PurchaseOrderSerializer(
            order, context={'request': request},
        ).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            order = PurchaseOrder.objects.select_for_update().get(
                pk=self.get_object().pk,
                tenant=get_tenant(request),
            )
            if order.status == PurchaseOrder.STATUS_CONVERTED:
                raise ValidationError('الطلبية المحوّلة إلى فاتورة لا يمكن إلغاؤها.')
            if order.status == PurchaseOrder.STATUS_CANCELLED:
                return Response(PurchaseOrderSerializer(
                    order, context={'request': request},
                ).data)
            order.status = PurchaseOrder.STATUS_CANCELLED
            order.cancel_reason = str(request.data.get('reason') or '').strip()
            order.save(update_fields=['status', 'cancel_reason', 'updated_at'])
        return Response(PurchaseOrderSerializer(
            order, context={'request': request},
        ).data)

    @action(detail=True, methods=['post'], url_path='convert-to-invoice')
    def convert_to_invoice(self, request, pk=None):
        try:
            invoice, created = convert_purchase_order_to_invoice(
                self.get_object(),
                user=request.user,
            )
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or getattr(
                exc, 'messages', None,
            ) or [str(exc)]
            raise ValidationError(detail)
        return Response(
            {
                'status': 'converted',
                'created': created,
                'invoice': {
                    'id': invoice.id,
                    'invoice_number': invoice.invoice_number,
                },
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class LogisticsDealViewSet(PagePartnerBalanceMixin, BaseTenantViewSet):
    queryset = LogisticsDeal.objects.all().order_by('-order_date')
    serializer_class = LogisticsDealSerializer
    partner_balance_spec = ("partner_id", True, "supplier_balance")

    def get_serializer_class(self):
        if self.action == 'list':
            return LogisticsDealListSerializer
        return LogisticsDealSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        search = str(self.request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(ref_number__icontains=search)
                | Q(description__icontains=search)
                | Q(short_name__icontains=search)
                | Q(factory_name__icontains=search)
                | Q(original_offer_number__icontains=search)
                | Q(supplier_invoice_number__icontains=search)
                | Q(pi_number__icontains=search)
                | Q(partner__name__icontains=search)
                | Q(partner__legal_name__icontains=search)
                | Q(items__name_snapshot__icontains=search)
                | Q(items__description_line__icontains=search)
                | Q(items__product__name_ar__icontains=search)
                | Q(items__product__name_en__icontains=search)
            ).distinct()
        status_filter = str(self.request.query_params.get('status') or '').strip()
        if status_filter:
            status_filter = {
                'initial': 'Open', 'shipped': 'Shipped', 'completed': 'Closed',
                'cancelled': 'Cancelled',
            }.get(status_filter.lower(), status_filter)
            qs = qs.filter(status__iexact=status_filter)
        date_from = parse_date(str(self.request.query_params.get('date_from') or ''))
        date_to = parse_date(str(self.request.query_params.get('date_to') or ''))
        if date_from:
            qs = qs.filter(order_date__gte=date_from)
        if date_to:
            qs = qs.filter(order_date__lte=date_to)

        qs = qs.select_related('partner', 'currency', 'tenant', 'created_by')
        # القائمة تأخذ الرصيد من `PagePartnerBalanceMixin` باستعلام واحد بعد
        # الترقيم؛ الاستعلام الفرعي هنا للصف الواحد (المستند المفتوح) فقط.
        if self.action != 'list':
            qs = annotate_partner_posted_balance(
                qs, "partner_id", supplier=True, alias="supplier_balance",
            )
        if self.action == 'list':
            return qs.prefetch_related(
                Prefetch(
                    'logisticsshipmentdeal_set',
                    queryset=LogisticsShipmentDeal.objects.select_related('shipment'),
                ),
                # «تحولت إلى فاتورة» — prefetch فواتير الشراء لتفادي N+1 في القائمة
                'purchase_invoices',
            )
        return qs.prefetch_related(
                Prefetch(
                    'items',
                    queryset=LogisticsDealItem.objects.select_related('product', 'deal'),
                ),
                Prefetch(
                    'payments',
                    queryset=LogisticsPayment.objects.select_related('journal'),
                ),
                Prefetch(
                    'logisticsshipmentdeal_set',
                    queryset=LogisticsShipmentDeal.objects.select_related('shipment'),
                ),
            )

    @staticmethod
    def _next_deal_ref(tenant):
        """D-#### تالٍ لكل الشركة — يشمل المحذوف ناعماً لأن قيد الفريدة يشمله."""
        import re
        nums = [0]
        refs = LogisticsDeal.all_objects.filter(tenant=tenant).values_list('ref_number', flat=True)
        for r in refs:
            m = re.match(r'^D-(\d+)$', str(r or ''))
            if m:
                nums.append(int(m.group(1)))
        return f"D-{max(nums) + 1:04d}"

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        kwargs = {'tenant': tenant}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user
        # الترقيم كان client-side فقط (max+1 في المتصفح) — سباق مستخدمين يصطدم
        # بـ unique(tenant, ref_number) ويرجع 500 (T12-B4). الخادم يولّد/يصحّح.
        ref = str(serializer.validated_data.get('ref_number') or '').strip()
        if not ref or LogisticsDeal.all_objects.filter(tenant=tenant, ref_number=ref).exists():
            kwargs['ref_number'] = self._next_deal_ref(tenant)
        deal = serializer.save(**kwargs)
        log_activity(
            action='create', entity_type='deal', entity_id=deal.id,
            entity_label=deal.ref_number, description='إنشاء صفقة', request=self.request,
            partner_ids=[deal.partner_id],
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        obj = self.get_object()
        log_view(entity_type='deal', entity_id=obj.id, entity_label=obj.ref_number, request=request)
        return response

    @action(detail=False, methods=['get'], url_path='ready-to-ship')
    def ready_to_ship(self, request):
        """M1: the candidate list for the «Create Shipment» multi-select panel.

        Only deals that reached «تم الشحن للوكيل» (stage READY_TO_SHIP) and are not
        already on a shipment. Deals still in manufacturing (DRAFT) are excluded —
        goods must be at the agent before they can be consolidated into a shipment.
        Returns a light payload with the CBM/KG measures the builder needs.
        """
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)
        linked = set(
            LogisticsShipmentDeal.objects.filter(deal__tenant=tenant)
            .values_list('deal_id', flat=True)
        )
        rows = []
        for d in self.get_queryset().select_related('partner'):
            if d.id in linked:
                continue
            if derive_stage(d) != LogisticsDeal.STAGE_READY_TO_SHIP:
                continue
            rows.append({
                'id': d.id,
                'ref_number': d.ref_number,
                'short_name': d.short_name or '',
                'description': d.description or '',
                'partner_id': d.partner_id,
                'partner_name': d.partner.name if d.partner_id else '',
                'stage': derive_stage(d),
                'shipping_workflow_status': d.shipping_workflow_status,
                'total_amount': d.total_amount,
                'currency_id': d.currency_id,
                'total_cbm': d.total_cbm,
                'total_weight_kg': d.total_weight_kg if d.total_weight_kg is not None else d.total_weight,
            })
        # Newest deal first (all rows are at the same READY_TO_SHIP stage).
        rows.sort(key=lambda r: -r['id'])
        return Response(rows)

    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        deal = self.get_object()
        data = request.data.copy()
        data['deal'] = deal.id

        serializer = LogisticsDealItemSerializer(data=data)
        if serializer.is_valid():
            serializer.save(deal=deal)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # ── ج8: الدفعة مورد REST مستقل (بدل الكتابة المتداخلة عبر PATCH الصفقة) ──
    # الحقول المقفلة بعد الترحيل: المبلغ وبيانات الصرف مرتبطة بالقيد المحاسبي.
    # التوثيق (سليب/تأكيد المورد/ملاحظات/مرفقات/الحالة) يبقى حراً دائماً.
    PAYMENT_FIELDS_LOCKED_WHEN_POSTED = frozenset({
        'amount', 'amount_local', 'usd_to_ils', 'transfer_cost',
        'percentage', 'payment_number', 'bank_account',
    })
    _PAYMENT_PROTECTED_KEYS = ('id', 'deal', 'shipment', 'is_posted', 'journal')

    def _deal_payments_cap_error(self, deal, new_amount, exclude_payment_pk=None):
        """الدفع الزائد للمورد مسموح — الفائض دفعة مقدمة تجعله مديناً لنا.

        كان يرفض أي مجموع يتجاوز إجمالي الصفقة، فيمنع واقعة محاسبية صحيحة
        (قرار المالك 2026-07-19 — نفس معاملة الوكيل والمخلّص والناقل). نسجّل
        الفائض في اللوج ليبقى ظاهراً للمراجعة، ويعرضه الواجهة كـ«رصيد لصالحك
        عند المورد».
        """
        qs = deal.payments.all()
        if exclude_payment_pk is not None:
            qs = qs.exclude(pk=exclude_payment_pk)
        existing = qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        cap = Decimal(deal.total_amount or 0)
        total = existing + Decimal(new_amount or 0)
        if cap > 0 and total > cap + Decimal('0.01'):
            logger.info(
                'deal %s supplier payments exceed total -> advance: total=%s cap=%s advance=%s',
                deal.pk, total, cap, total - cap,
            )
        return None

    @action(detail=True, methods=['post'], url_path='payments')
    def create_payment(self, request, pk=None):
        """إنشاء دفعة صفقة مباشرة — تعيد المعرّف الحقيقي فوراً (لا tmp-id)."""
        deal = self.get_object()
        data = {
            k: v for k, v in request.data.items()
            if k not in self._PAYMENT_PROTECTED_KEYS
        }
        serializer = LogisticsPaymentSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        cap_err = self._deal_payments_cap_error(
            deal, serializer.validated_data.get('amount') or Decimal('0')
        )
        if cap_err:
            return Response({'error': cap_err}, status=status.HTTP_400_BAD_REQUEST)

        pn = serializer.validated_data.get('payment_number')
        if pn is not None and deal.payments.filter(payment_number=pn).exists():
            return Response(
                {
                    'error': (
                        f'يوجد بالفعل دفعة بنفس رقم القسط ({pn}). '
                        'حدّث الصفحة (F5) وتجنّب حفظاً مكرراً.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = serializer.save(deal=deal, shipment=None)
        log_activity(
            action='create', entity_type='deal', entity_id=deal.id,
            entity_label=deal.ref_number,
            description=f'إضافة دفعة #{payment.payment_number} ({payment.amount})',
            partner_ids=[deal.partner_id],
            request=request,
        )
        return Response(
            LogisticsPaymentSerializer(payment).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['patch'], url_path=r'payments/(?P<payment_id>[^/.]+)')
    def update_payment(self, request, pk=None, payment_id=None):
        """تحديث دفعة صفقة. المرحّلة: حقولها التوثيقية فقط (تأكيد مورد/سليب/ملاحظات)."""
        deal = self.get_object()
        try:
            pid = int(str(payment_id).strip())
        except (TypeError, ValueError):
            return Response(
                {'error': 'معرّف الدفعة غير صالح'}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            payment = LogisticsPayment.objects.get(pk=pid, deal=deal)
        except LogisticsPayment.DoesNotExist:
            return Response({'error': 'الدفعة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            k: v for k, v in request.data.items()
            if k not in self._PAYMENT_PROTECTED_KEYS
        }
        serializer = LogisticsPaymentSerializer(payment, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        if payment.is_posted:
            def _changed(field):
                new_v = serializer.validated_data[field]
                old_v = getattr(payment, field)
                if isinstance(old_v, Decimal) or isinstance(new_v, Decimal):
                    try:
                        return Decimal(str(old_v or 0)) != Decimal(str(new_v or 0))
                    except Exception:
                        return True
                return old_v != new_v

            blocked = [
                f for f in self.PAYMENT_FIELDS_LOCKED_WHEN_POSTED
                if f in serializer.validated_data and _changed(f)
            ]
            if blocked:
                return Response(
                    {
                        'error': (
                            'الدفعة مرحّلة محاسبياً — المبلغ وبيانات الصرف مقفلة '
                            f'({", ".join(sorted(blocked))}). ألغِ الترحيل أولاً ثم عدّل.'
                        ),
                        'can_unpost': True,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        new_amount = serializer.validated_data.get('amount')
        if new_amount is not None:
            cap_err = self._deal_payments_cap_error(
                deal, new_amount, exclude_payment_pk=payment.pk
            )
            if cap_err:
                return Response({'error': cap_err}, status=status.HTTP_400_BAD_REQUEST)

        payment = serializer.save(deal=deal, shipment=None)
        log_activity(
            action='update', entity_type='deal', entity_id=deal.id,
            entity_label=deal.ref_number,
            description=f'تحديث دفعة #{payment.payment_number}',
            partner_ids=[deal.partner_id],
            request=request,
        )
        return Response(LogisticsPaymentSerializer(payment).data)

    def perform_update(self, serializer):
        # الصفقة ليست مستنداً مرحَّلاً؛ الدفعات الفعلية تبقى كما هي عند تعديل البنود.
        # إذا أصبح المدفوع أكبر من الإجمالي فالفرق رصيد للشركة عند المورد.
        with transaction.atomic():
            deal = serializer.save()
            from .signals import recalculate_deal_payment_status
            recalculate_deal_payment_status(deal.pk)
            deal.refresh_from_db(fields=['remaining_amount', 'payment_status'])
            posted = deal.payments.filter(is_posted=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            advance = max(Decimal('0'), Decimal(str(posted)) - Decimal(str(deal.total_amount or 0)))
            if advance > 0:
                logger.info('deal supplier advance recalculated deal=%s amount=%s', deal.pk, advance)
        log_activity(
            action='update', entity_type='deal', entity_id=deal.id,
            entity_label=deal.ref_number, description='تعديل صفقة', request=self.request,
            partner_ids=[deal.partner_id],
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.payments.filter(is_posted=True).exists():
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deal_id, deal_ref, partner_id = instance.id, instance.ref_number, instance.partner_id
        response = super().destroy(request, *args, **kwargs)
        log_activity(
            action='delete', entity_type='deal', entity_id=deal_id,
            entity_label=deal_ref, description='حذف صفقة', request=request,
            partner_ids=[partner_id],
        )
        return response

    @action(detail=True, methods=['post'], url_path='unpost')
    @requires_perm('import.doc.unpost')
    def unpost(self, request, pk=None):
        """تراجع عن ترحيل الصفقة: حذف قيود كل دفعاتها المرحّلة وإرجاعها مسودات."""
        deal = self.get_object()
        posted_payments = list(deal.payments.filter(is_posted=True))
        if not posted_payments:
            return Response(
                {'error': 'لا توجد دفعات مرحّلة على هذه الصفقة.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                total = {'journals_deleted': 0, 'lines_deleted': 0, 'stock_movements_deleted': 0}
                for pay in posted_payments:
                    r = unpost_document(
                        tenant_id=deal.tenant_id,
                        reference_id=pay.id,
                        journal_reference_types=['LOGISTICS_PAYMENT'],
                        user=request.user,
                        document_label=f"دفعة صفقة {deal.ref_number}",
                    )
                    for k in total:
                        total[k] += r[k]
                    pay.is_posted = False
                    pay.journal = None
                    pay.save(update_fields=['is_posted', 'journal'])
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        log_activity(
            action='unpost', entity_type='deal', entity_id=deal.id,
            entity_label=deal.ref_number, description='إلغاء ترحيل دفعات صفقة', request=request,
            partner_ids=[deal.partner_id],
        )
        return Response({'message': 'تم التراجع عن الترحيل وحذف القيود.', 'unpost_result': total})

    @action(detail=True, methods=['post'])
    def post_to_accounting(self, request, pk=None):
        """
        معطّل: قيد المخزون/المورد يُنشأ عند «استلام البضاعة» عبر ترحيل الفاتورة فقط.
        استخدم: POST /api/accounting/purchase-receipts/
        """
        return Response(
            {
                'error': 'لم يعد ترحيل قيد شراء من الصفقة متاحاً. عند إصدار/استلام الفاتورة استخدم ترحيل استلام المخزون.',
                'purchase_receipt_endpoint': '/api/accounting/purchase-receipts/',
                'body_example': {
                    'partner_id': 'معرف المورد',
                    'amount': 'المبلغ',
                    'description': 'استلام بضاعة',
                    'invoice_reference': 'رقم مرجعي اختياري',
                    'transaction_date': 'YYYY-MM-DD',
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(
        detail=True,
        methods=['get'],
        url_path=r'payment-posting-diagnostics/(?P<payment_id>[^/.]+)',
    )
    def payment_posting_diagnostics(self, request, pk=None, payment_id=None):
        """
        لماذا لم يُرحَّل قيد الدفعة تلقائياً؟ (نفس شروط الترحيل التلقائي بعد الحفظ)
        """
        from .payment_posting_diagnostics import build_auto_posting_report

        deal = self.get_object()
        try:
            payment = LogisticsPayment.objects.select_related(
                'journal',
                'deal',
                'deal__partner',
                'deal__partner__linked_account',
                'bank_account',
            ).get(pk=payment_id, deal=deal)
        except LogisticsPayment.DoesNotExist:
            return Response({'error': 'الدفعة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)

        return Response(build_auto_posting_report(payment.deal, payment))

    @action(detail=True, methods=['post'], url_path=r'remove_payment/(?P<payment_id>[^/.]+)')
    def remove_deal_payment(self, request, pk=None, payment_id=None):
        """
        حذف دفعة صفقة من السجل (غير المرحّلة فقط).
        أوثق من PATCH الكامل: قد لا يُحذف الصف إذا بقي is_posted في DB أو تعثرت مطابقة المعرفات.
        """
        deal = self.get_object()
        try:
            pid = int(str(payment_id).strip())
        except (TypeError, ValueError):
            return Response(
                {'error': 'معرّف الدفعة غير صالح'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                deal_locked = LogisticsDeal.objects.select_for_update().get(pk=deal.pk)
                payment_locked = LogisticsPayment.objects.select_for_update().get(
                    pk=pid, deal=deal_locked
                )
                if payment_locked.is_posted:
                    return Response(
                        {
                            'error': 'لا يمكن حذف دفعة مرحّلة محاسبياً. استخدم «إلغاء الترحيل» أولاً ثم أعد المحاولة.',
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                payment_locked.delete()

                from .signals import recalculate_deal_payment_status
                recalculate_deal_payment_status(deal_locked.pk)
        except LogisticsPayment.DoesNotExist:
            return Response(
                {'error': 'الدفعة غير موجودة'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            {'status': 'removed', 'payment_id': pid},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='post_payment/(?P<payment_id>[^/.]+)')
    def post_payment_to_accounting(self, request, pk=None, payment_id=None):
        """
        ترحيل دفعة واحدة إلى المحاسبة.
        القيد: مدين حساب الموردين (AP) | دائن حساب البنك/الصندوق
        هذا يُسجّل أن الشركة دفعت للمورد المبلغ المحدد.
        """
        from accounting.models import JournalHeader, JournalLine, Account, CashBoxLedgerAccount
        import datetime

        deal = self.get_object()

        try:
            payment = LogisticsPayment.objects.get(pk=payment_id, deal=deal)
        except LogisticsPayment.DoesNotExist:
            return Response({'error': 'الدفعة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)

        if payment.is_posted:
            return Response({'error': 'هذه الدفعة مرحلة بالفعل'}, status=status.HTTP_400_BAD_REQUEST)

        if payment.status not in ['Paid', 'Confirmed']:
            return Response(
                {'error': 'يجب أن تكون حالة الدفعة "Paid" أو "Confirmed" قبل الترحيل'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ext_in = (request.data.get('cash_box_external_id') or '').strip()
        if ext_in:
            payment.cash_box_external_id = ext_in[:128]
            payment.save(update_fields=['cash_box_external_id'])

        # تحديد حساب البنك/الصندوق
        bank_account = None
        bank_account_id = request.data.get('bank_account_id')
        ext = (request.data.get('cash_box_external_id') or payment.cash_box_external_id or '').strip()

        if ext:
            link = CashBoxLedgerAccount.objects.filter(
                tenant=deal.tenant, external_id=ext[:128]
            ).select_related('account').first()
            if not link:
                return Response(
                    {
                        'error': 'لا يوجد حساب محاسبي مربوط بهذا الصندوق. أنشئ الربط عبر POST /api/accounting/cash-box-accounts/',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            bank_account = link.account

        if bank_account is None and bank_account_id:
            try:
                bank_account = Account.objects.get(pk=bank_account_id, tenant=deal.tenant)
            except Account.DoesNotExist:
                return Response({'error': 'حساب البنك غير موجود'}, status=status.HTTP_400_BAD_REQUEST)

        if bank_account is None:
            bank_account = resolve_default_cash_box_account(deal.tenant)

        if not bank_account:
            return Response(
                {
                    'error': (
                        'حدد حساب الصندوق: مرّر cash_box_external_id أو bank_account_id، '
                        'أو أنشئ ربط صندوق في المحاسبة وعيّن DEFAULT_CASH_BOX_EXTERNAL_ID '
                        'أو صندوقاً بعملة USD ليُستخدم افتراضياً.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not deal.partner.linked_account:
            return Response({'error': 'المورد لا يملك حساباً محاسبياً مربوطاً'}, status=status.HTTP_400_BAD_REQUEST)

        from .payment_posting_cap import posting_cap_check

        try:
            with transaction.atomic():
                deal_locked = (
                    LogisticsDeal.objects.select_related("partner", "partner__linked_account")
                    .select_for_update()
                    .get(pk=deal.pk)
                )
                payment_locked = LogisticsPayment.objects.select_for_update().get(
                    pk=payment.id, deal=deal_locked
                )
                if payment_locked.is_posted:
                    return Response(
                        {"error": "هذه الدفعة مرحلة بالفعل"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                ok_cap, cap_err = posting_cap_check(deal_locked, payment_locked.amount)
                if not ok_cap:
                    return Response({"error": cap_err}, status=status.HTTP_400_BAD_REQUEST)

                payment_date = payment_locked.transfer_date or datetime.date.today()
                foreign_amount = payment_locked.amount

                deal_currency = deal_locked.currency
                base_currency = Currency.objects.filter(IsBaseCurrency=True).first()
                is_foreign = (
                    deal_currency and base_currency
                    and deal_currency.pk != base_currency.pk
                )

                if is_foreign:
                    rate = payment_locked.usd_to_ils or deal_locked.currency_rate or Decimal('1')
                    local_amount = (foreign_amount * rate).quantize(Decimal('0.01'))
                else:
                    rate = Decimal('1')
                    local_amount = foreign_amount

                _desc = f"دفعة {payment_locked.title} | صفقة: {deal_locked.ref_number}"
                # صندوق الدولار FIFO: إن كان الصندوق المصدر بعملة أجنبية وله طبقات،
                # تُسحب التكلفة بالشيقل FIFO ويُحتسب فرق الصرف المحقّق مقابل سعر الدفع.
                from accounting.fx_fifo import fifo_link_for_box, build_fx_payment_lines
                fifo_link = fifo_link_for_box(bank_account, deal_locked.tenant) if is_foreign else None
                if fifo_link:
                    lines_data = build_fx_payment_lines(
                        fifo_link=fifo_link, foreign_amount=foreign_amount, local_amount=local_amount,
                        debit_account_id=deal_locked.partner.linked_account_id,
                        box_account_id=bank_account.id, partner_id=deal_locked.partner_id,
                        description=_desc, tenant=deal_locked.tenant)
                    journal_currency, journal_rate = base_currency, Decimal('1')
                else:
                    lines_data = [
                        {"account": deal_locked.partner.linked_account_id, "debit": local_amount, "credit": Decimal("0"), "partner": deal_locked.partner_id, "description": _desc},
                        {"account": bank_account.id, "debit": Decimal("0"), "credit": local_amount, "description": _desc},
                    ]
                    journal_currency, journal_rate = deal_currency, rate

                journal = post_journal(
                    tenant_id=deal_locked.tenant_id,
                    transaction_date=payment_date,
                    reference_type='LOGISTICS_PAYMENT',
                    reference_id=payment_locked.id,
                    description=f"دفعة {payment_locked.title} | صفقة: {deal_locked.ref_number} | المورد: {deal_locked.partner.name}",
                    lines_data=lines_data,
                    currency=journal_currency,
                    exchange_rate=journal_rate,
                    # قرار 2026-08-11: الدفعة قابلة لإعادة الترحيل بعد عكسها،
                    # وقيود المرجع السابقة (الأصل وعكسه) تبقى في الدفاتر — البحث
                    # الـidempotent كان يعيد قيد دورة سابقة بدل إنشاء الجديد.
                    # حارس التكرار الفعلي: قفل صف الدفعة + فحص is_posted أعلاه.
                    idempotent=False,
                )

                # تحديث الدفعة
                payment_locked.is_posted = True
                payment_locked.journal = journal
                payment_locked.bank_account = bank_account
                payment_locked.save()

                from .signals import recalculate_deal_payment_status
                recalculate_deal_payment_status(deal_locked.pk)

            return Response({
                'status': 'تم ترحيل الدفعة بنجاح',
                'journal_id': journal.id,
                'payment_id': payment_locked.id
            }, status=status.HTTP_200_OK)

        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("deal post_payment failed pk=%s", pk)
            return Response({'error': 'حدث خطأ غير متوقع أثناء ترحيل الدفعة.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path=r'link_payment_journal/(?P<payment_id>[^/.]+)')
    def link_payment_journal(self, request, pk=None, payment_id=None):
        """
        ربط دفعة صفقة بقيد يومية أُنشئ يدوياً (مثلاً بعد «فتح قيد جديد» من المحاسبة دون ربط تلقائي).
        يضبط journal + is_posted على صف الدفعة حتى يظهر رابط «فتح في المحاسبة» في الواجهة.
        """
        deal = self.get_object()
        try:
            pid = int(str(payment_id).strip())
        except (TypeError, ValueError):
            return Response(
                {'error': 'معرّف الدفعة غير صالح'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        jid_raw = request.data.get('journal_id')
        try:
            jid = int(jid_raw)
        except (TypeError, ValueError):
            return Response(
                {'error': 'أرسل journal_id رقماً (رقم القيد من شاشة اليومية).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = LogisticsPayment.objects.get(pk=pid, deal=deal)
        except LogisticsPayment.DoesNotExist:
            return Response(
                {'error': 'الدفعة غير موجودة'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.journal_id:
            return Response(
                {
                    'error': 'الدفعة مربوطة بقيد مسبقاً. لإعادة الربط استخدم «إلغاء الترحيل» إن لزم.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            journal = JournalHeader.objects.get(pk=jid, tenant_id=deal.tenant_id)
        except JournalHeader.DoesNotExist:
            return Response(
                {'error': 'القيد غير موجود أو لا ينتمي لنفس المستأجر.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not journal.is_posted:
            return Response(
                {
                    'error': 'اربط قيداً مرحّلاً فقط (ترحيل القيد من المحاسبة أولاً).',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            pay_locked = LogisticsPayment.objects.select_for_update().get(
                pk=payment.pk, deal=deal
            )
            if pay_locked.journal_id:
                return Response(
                    {'error': 'الدفعة مربوطة بقيد مسبقاً'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pay_locked.journal = journal
            pay_locked.is_posted = True
            pay_locked.save(update_fields=['journal', 'is_posted'])

        return Response(
            {
                'status': 'linked',
                'journal_id': journal.id,
                'payment_id': pay_locked.id,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='unpost_payment/(?P<payment_id>[^/.]+)')
    def unpost_payment_from_accounting(self, request, pk=None, payment_id=None):
        """
        إلغاء ترحيل دفعة صفقة (احترافي):

        1) إنشاء **قيد عكسي مرحّل** (مدين/دائن معكوسان) في نفس منطق القيود المزدوجة —
           فيُحدَّث ميزان المراجعة ودفتر الأستاذ للحسابات المرحّلة فوراً (صافي الأثر = عكس الدفعة).
        2) جعل القيد **الأصلي غير مرحّل** (`is_posted=False`) مع الإبقاء على أسطره للتدقيق،
           ولعدم احتسابه في التقارير التي تعتمد `journal__is_posted=True`.
        3) فك ارتباط الدفعة و`is_posted=False` لتصحيح بيانات الصفقة (نسب، إلخ).

        مصرّح فقط: Django staff أو superuser.
        """
        u = request.user
        if not u.is_authenticated or not user_can_unpost_logistics_deal_payment(u):
            return Response(
                {
                    "error": "غير مصرّح — إلغاء الترحيل متاح لمدير التطبيق (نفس دور «مدير» بعد تسجيل الدخول) "
                    "أو لحساب Django Staff / Superuser. إن كان دورك «مدير» في الواجهة وما زلت ترى هذه الرسالة، "
                    "تحقق من أن مرآة المستخدم users/<id> تحتوي role=manager أو أنك المستخدم النشط الوحيد.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        deal = self.get_object()
        try:
            payment = LogisticsPayment.objects.select_related("journal").get(
                pk=payment_id, deal=deal
            )
        except LogisticsPayment.DoesNotExist:
            return Response({"error": "الدفعة غير موجودة"}, status=status.HTTP_404_NOT_FOUND)

        if not payment.is_posted:
            return Response(
                {"error": "هذه الدفعة غير مرحّلة أصلاً"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                LogisticsDeal.objects.select_for_update().get(pk=deal.pk)
                pay_row = LogisticsPayment.objects.select_for_update().get(
                    pk=payment.pk, deal_id=deal.pk
                )
                if not pay_row.is_posted:
                    return Response(
                        {"error": "هذه الدفعة غير مرحّلة أصلاً"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                jid_locked = pay_row.journal_id
                if not jid_locked:
                    return Response(
                        {"error": "لا يوجد قيد يومية مرتبط بهذه الدفعة"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                orig = (
                    JournalHeader.objects.select_for_update()
                    .select_related("tenant")
                    .get(pk=jid_locked)
                )
                if not orig.is_posted:
                    return Response(
                        {
                            "error": "القيد المرتبط بالدفعة غير مرحّل — البيانات غير متسقة؛ راجع المحاسبة."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                raw_rev = (request.data.get("reversal_date") or "").strip()
                if raw_rev:
                    try:
                        rev_date = datetime.datetime.strptime(raw_rev[:10], "%Y-%m-%d").date()
                    except ValueError:
                        rev_date = datetime.date.today()
                else:
                    rev_date = datetime.date.today()

                tenant = orig.tenant

                # قرار 2026-08-11 (توحيد نمط العكس — معالجة ديون المرحلة 2):
                # القيد الأصلي يبقى مرحّلاً ويعادله قيد العكس بعملة الأصل وسعره،
                # فصافي الأثر على التقارير المرحّلة (الاسمية والأساسية) صفر،
                # وتقارير الفترة الأصلية لا تتغيّر بأثر رجعي — نفس نمط دفعات
                # التخليص. (النمط القديم كان يلغي ترحيل الأصل فيُظهر أثر العكس
                # وحده بإشارة معكوسة في التقارير المرحّلة.)
                rev = accounting_api.reverse_journal(
                    orig,
                    reference_type="LOGISTICS_PAYMENT_UNPOST",
                    reference_id=int(pay_row.id),
                    transaction_date=rev_date,
                    description=(
                        f"[إلغاء ترحيل دفعة] صفقة {deal.ref_number} — {pay_row.title} — "
                        f"عكس القيد #{orig.id}"
                    ),
                    line_description_prefix=f"عكس قيد #{orig.id}: ",
                    copy_currency=True,
                    copy_project=True,
                )

                LogisticsPayment.objects.filter(pk=pay_row.pk).update(
                    is_posted=False,
                    journal_id=None,
                    status="Pending",
                )

                from .signals import recalculate_deal_payment_status
                recalculate_deal_payment_status(deal.pk)

                try:
                    create_audit_log(
                        tenant=tenant,
                        user=u,
                        action="UPDATE",
                        model_name="LogisticsPayment",
                        object_id=pay_row.id,
                        change_details=(
                            f"إلغاء ترحيل دفعة: قيد عكسي مرحّل #{rev.id} يعادل "
                            f"القيد #{orig.id} (بقي مرحّلاً)، صفقة {deal.ref_number}"
                        )[:2000],
                    )
                except Exception:
                    pass

            return Response(
                {
                    "status": "تم إلغاء ترحيل الدفعة بقيد عكسي مرحّل — القيد الأصلي يبقى مرحّلاً ويعادله قيد العكس فيصير صافي أثر الدفعة صفراً.",
                    "payment_id": int(payment_id),
                    "voided_journal_id": orig.id,
                    "voided_journal_posted": True,
                    "reversal_journal_id": rev.id,
                    "reversal_journal_posted": True,
                    "reversal_date": str(rev_date),
                    "accounting_note": (
                        "القيد الأصلي بقي مرحّلاً للتدقيق وتقارير فترته لم تتغيّر؛ "
                        "قيد العكس يلغي أثره فيصير صافي الدفعة صفراً في الدفاتر."
                    ),
                },
                status=status.HTTP_200_OK,
            )
        except JournalHeader.DoesNotExist:
            return Response(
                {"error": "قيد اليومية المرتبط غير موجود"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("deal unpost_payment failed pk=%s", pk)
            return Response({"error": "حدث خطأ غير متوقع أثناء إلغاء ترحيل الدفعة."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogisticsPaymentViewSet(BaseTenantViewSet):
    """ViewSet مستقل للدفعات للاستعلام وإدارة الفواتير"""
    queryset = LogisticsPayment.objects.all().order_by('-created_at')
    serializer_class = LogisticsPaymentSerializer

    def get_queryset(self):
        from django.db.models import Q
        tenant = get_tenant(self.request)
        if tenant:
            # نشمل دفعات الصفقات ودفعات الشحنات (deal=None) معاً
            # perf: select_related('journal') يقتل N+1 على journal_id_display لكل صف.
            return LogisticsPayment.objects.filter(
                Q(deal__tenant=tenant) | Q(shipment__tenant=tenant)
            ).select_related('journal').order_by('-created_at')
        return LogisticsPayment.objects.none()

    def perform_create(self, serializer):
        # P-H-9: shared cross-payment-type validation. Routes through
        # core.payments to refuse the same set of malformed inputs that
        # customer / clearance / shipment-agent payments refuse.
        from django.db import transaction
        from core.payments import PaymentContext, validate_payment
        from rest_framework.exceptions import ValidationError as DRFValidationError
        with transaction.atomic():
            payment = serializer.save()
            ctx = PaymentContext.from_deal_payment(payment)
            errors = validate_payment(ctx)
            if errors:
                raise DRFValidationError({"payment": errors})


class LogisticsShipmentViewSet(BaseTenantViewSet):
    queryset = LogisticsShipment.objects.all().order_by('-id')
    serializer_class = LogisticsShipmentSerializer

    def get_serializer_class(self):
        if self.action == 'list':
            return LogisticsShipmentListSerializer
        return LogisticsShipmentSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("shipping_agent")
        search = str(self.request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(shipment_number__icontains=search)
                | Q(shipment_name__icontains=search)
                | Q(agent_shipment_number__icontains=search)
                | Q(container_number__icontains=search)
                | Q(bill_of_lading__icontains=search)
                | Q(shipping_agent__name__icontains=search)
            )
        shipping_type = str(self.request.query_params.get('shipping_type') or '').strip().lower()
        if shipping_type in {'air', 'sea'}:
            qs = qs.filter(shipping_type=shipping_type)
        raw_status = str(self.request.query_params.get('status') or '').strip()
        if raw_status and raw_status.lower() not in {
            'draft', 'payment_pending', 'partially_paid', 'paid',
        }:
            status_value = {
                'shipped': 'In-Transit', 'delivered': 'Cleared',
            }.get(raw_status.lower(), raw_status)
            qs = qs.filter(status__iexact=status_value)
        deal_id = str(self.request.query_params.get('deal_id') or '').strip()
        if deal_id.isdigit():
            qs = qs.filter(deals__id=int(deal_id))
        date_from = parse_date(str(self.request.query_params.get('date_from') or ''))
        date_to = parse_date(str(self.request.query_params.get('date_to') or ''))
        if date_from:
            qs = qs.filter(Q(departure_date__gte=date_from) | Q(arrival_date__gte=date_from))
        if date_to:
            qs = qs.filter(Q(departure_date__lte=date_to) | Q(arrival_date__lte=date_to))

        if self.action == 'list':
            payment_summary = (
                LogisticsPayment.objects.filter(shipment_id=OuterRef('pk'))
                .values('shipment_id')
                .annotate(total=Sum('amount'), row_count=Count('id'))
            )
            deal_summary = (
                LogisticsShipmentDeal.objects.filter(shipment_id=OuterRef('pk'))
                .values('shipment_id')
                .annotate(row_count=Count('id'))
            )
            qs = qs.annotate(
                payments_total=Coalesce(
                    Subquery(
                        payment_summary.values('total')[:1],
                        output_field=DecimalField(max_digits=18, decimal_places=2),
                    ),
                    Value(Decimal('0.00')),
                ),
                payments_count=Coalesce(
                    Subquery(
                        payment_summary.values('row_count')[:1], output_field=IntegerField()
                    ),
                    Value(0),
                ),
                deals_count=Coalesce(
                    Subquery(
                        deal_summary.values('row_count')[:1], output_field=IntegerField()
                    ),
                    Value(0),
                ),
            )
            status_key = raw_status.lower()
            if status_key == 'draft':
                qs = qs.filter(payments_count=0)
            elif status_key == 'payment_pending':
                qs = qs.filter(payments_count__gt=0, payments_total=0)
            elif status_key == 'partially_paid':
                qs = qs.filter(
                    payments_total__gt=0,
                    payments_total__lt=F('total_shipping_cost_usd'),
                )
            elif status_key == 'paid':
                qs = qs.filter(
                    total_shipping_cost_usd__gt=0,
                    payments_total__gte=F('total_shipping_cost_usd'),
                )
            return qs

        qs = qs.prefetch_related(
            Prefetch('deals', queryset=LogisticsDeal.objects.select_related('partner')),
        )
        return qs.prefetch_related(
            Prefetch(
                "agent_payments",
                queryset=LogisticsPayment.objects.order_by("payment_number", "id"),
            ),
            Prefetch(
                "logisticsshipmentdeal_set",
                queryset=LogisticsShipmentDeal.objects.select_related("deal"),
            ),
        )

    @staticmethod
    def _next_shipment_number(tenant):
        """SH-#### التالي لكل الشركة — يماثل _next_deal_ref لـLogisticsDeal.

        الواجهة (ImportDocumentScreen) تعرض حقل «رقم الشحنة» للقراءة فقط
        وتتوقّع ترقيماً خادمياً بعد الحفظ (بنفس نمط رقم الصفقة D-####)، لكن
        الخادم كان بلا perform_create مخصّص فيصطدم shipment_number الفارغ
        بقيد blank=False على الموديل — 400 يمنع إنشاء أي شحنة من الواجهة.
        """
        import re
        nums = [0]
        refs = LogisticsShipment.objects.filter(tenant=tenant).values_list(
            'shipment_number', flat=True
        )
        for r in refs:
            m = re.match(r'^SH-(\d+)$', str(r or ''))
            if m:
                nums.append(int(m.group(1)))
        return f"SH-{max(nums) + 1:04d}"

    @staticmethod
    def _activity_partner_ids(shipment):
        partner_ids = set(
            shipment.logisticsshipmentdeal_set.values_list(
                "deal__partner_id", flat=True,
            ),
        )
        if shipment.shipping_agent_id:
            partner_ids.add(shipment.shipping_agent_id)
        return partner_ids

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        kwargs = {'tenant': tenant}
        num = str(serializer.validated_data.get('shipment_number') or '').strip()
        if not num or LogisticsShipment.objects.filter(tenant=tenant, shipment_number=num).exists():
            kwargs['shipment_number'] = self._next_shipment_number(tenant)
            logger.info('Auto-generated shipment number=%s tenant=%s', kwargs['shipment_number'], getattr(tenant, 'pk', None))
        shipment = serializer.save(**kwargs)
        log_activity(
            action='create', entity_type='shipment', entity_id=shipment.id,
            entity_label=shipment.shipment_number, description='إنشاء شحنة',
            partner_ids=self._activity_partner_ids(shipment), request=self.request,
        )

    @action(detail=False, methods=['post'], url_path='create-from-deals')
    def create_from_deals(self, request):
        """M1: create one shipment from many Ready-to-Ship deals (fixes RC-1).

        Body: {deal_ids: [int], chargeable_unit: 'cbm'|'kg', freight_rate: number,
               header: {shipment_name, shipping_agent_id, shipping_type, ...}}
        Atomically links the deals, aggregates CBM+KG, computes total freight =
        rate × Σ(unit), allocates it pro-rata (penny-reconciled), and advances each
        deal to IN_SHIPMENT through the guarded stage machine.
        """
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)
        deal_ids = request.data.get('deal_ids') or []
        chargeable_unit = str(request.data.get('chargeable_unit') or '').strip().lower()
        rate = request.data.get('freight_rate', request.data.get('rate', 0))
        header = request.data.get('header') or {}
        try:
            shipment = create_shipment_from_deals(
                tenant=tenant,
                deal_ids=deal_ids,
                chargeable_unit=chargeable_unit,
                freight_rate=rate,
                header=header,
                user=request.user if request.user.is_authenticated else None,
            )
        except (ValidationError, DjangoValidationError) as e:
            msg = '؛ '.join(e.messages) if hasattr(e, 'messages') else str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('create_from_deals failed')
            return Response(
                {'error': 'حدث خطأ غير متوقع أثناء إنشاء الشحنة من الصفقات.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        log_activity(
            action='create', entity_type='shipment', entity_id=shipment.id,
            entity_label=shipment.shipment_number,
            description=f'إنشاء شحنة من {len(deal_ids)} صفقة', request=request,
            partner_ids=self._activity_partner_ids(shipment),
        )
        ser = self.get_serializer(shipment)
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='freight')
    def set_freight(self, request, pk=None):
        """M2: set the freight chargeable unit + rate, recompute cleanly.

        Body: {chargeable_unit: 'cbm'|'kg', freight_rate: number}. Switching the
        unit recomputes total freight = rate × Σ(unit) and re-runs the pro-rata
        allocation to every deal — no stale figure survives downstream (unposted
        invoices recompute live on read; posted invoices are frozen).
        """
        shipment = self.get_object()
        if getattr(shipment, 'transit_journal_id', None):
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from logistics.domain import allocation as _alloc
        unit = str(request.data.get('chargeable_unit') or shipment.chargeable_unit or '').strip().lower()
        if unit not in (LogisticsShipment.CHARGEABLE_CBM, LogisticsShipment.CHARGEABLE_KG):
            return Response({'error': "وحدة تسعير الشحن يجب أن تكون 'cbm' أو 'kg'."},
                            status=status.HTTP_400_BAD_REQUEST)
        raw_rate = request.data.get('freight_rate', request.data.get('rate', shipment.freight_rate or 0))
        try:
            rate = Decimal(str(raw_rate))
        except Exception:
            return Response({'error': 'سعر شحن غير صالح.'}, status=status.HTTP_400_BAD_REQUEST)
        if rate < 0:
            return Response({'error': 'سعر الشحن لا يمكن أن يكون سالباً.'},
                            status=status.HTTP_400_BAD_REQUEST)

        links = list(
            LogisticsShipmentDeal.objects.filter(shipment=shipment).select_related('deal')
        )
        # Same guard as create: a freight rate on a deal missing its CBM/KG allocates wrong.
        if rate > 0:
            from .domain.shipment_builder import assert_deals_have_measure
            try:
                assert_deals_have_measure([l.deal for l in links], unit)
            except DjangoValidationError as e:
                msg = '؛ '.join(e.messages) if hasattr(e, 'messages') else str(e)
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        total_units = sum((_alloc.deal_unit_measure(l.deal, unit) for l in links), Decimal('0'))
        total_freight = _alloc.freight_total(rate, total_units)

        shipment.chargeable_unit = unit
        shipment.freight_rate = rate
        shipment.price_per_unit = rate
        shipment.pricing_method = 'unit'
        shipment.unit_type = 'weight' if unit == LogisticsShipment.CHARGEABLE_KG else 'cbm'
        shipment.total_shipping_cost_usd = total_freight
        shipment.save(update_fields=[
            'chargeable_unit', 'freight_rate', 'price_per_unit',
            'pricing_method', 'unit_type', 'total_shipping_cost_usd',
        ])
        try:
            redistribute_shipment_deal_allocations(shipment)
        except Exception:
            logger.exception('redistribute after set_freight failed (shipment=%s)', shipment.pk)
        return Response(self.get_serializer(shipment).data)

    @action(detail=True, methods=['post'], url_path='recalculate-distribution')
    def recalculate_distribution(self, request, pk=None):
        """إعادة توزيع تكلفة الشحن الدولي بين الصفقات (حسب CBM أو الوزن) وحفظها في SQL."""
        shipment = self.get_object()
        try:
            n = redistribute_shipment_deal_allocations(shipment)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'updated_links': n})

    @action(detail=True, methods=['post'])
    def add_deal(self, request, pk=None):
        shipment = self.get_object()
        deal_id = request.data.get('deal_id')
        if not deal_id:
            return Response({'error': 'deal_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # نفس tenant الشحنة حصراً — كان الجلب بلا فلتر يسمح بربط صفقة شركة أخرى (T12-B2)
            deal = LogisticsDeal.objects.get(pk=deal_id, tenant=shipment.tenant)
            # Prevent same deal on multiple active shipments
            existing = LogisticsShipmentDeal.objects.filter(deal=deal).first()
            if existing:
                return Response(
                    {'error': f'الصفقة مربوطة بالفعل بالشحنة #{existing.shipment_id}. لا يمكن ربطها بأكثر من شحنة.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
            # توزيع حصص الشحن فوراً — كانت تبقى 0.00 حتى استدعاء يدوي (T12-B1)
            try:
                redistribute_shipment_deal_allocations(shipment)
            except Exception:
                logger.exception('redistribute after add_deal failed (shipment=%s)', shipment.pk)
            # حالة الشحن تُحدَّد عبر shipping_workflow_status (إشارة sync_deal_workflow_on_shipment_link)
            return Response({'status': 'تم ربط الصفقة بالشحنة بنجاح'}, status=status.HTTP_200_OK)
        except LogisticsDeal.DoesNotExist:
            return Response({'error': 'الصفقة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def remove_deal(self, request, pk=None):
        """task6.1 C-5: detach a deal from the shipment.

        Mirror of `add_deal`. Refuses to detach if the shipment has already
        been posted to accounting (transit_journal set) — that would leave
        the GL entry hanging without its source allocation.
        """
        shipment = self.get_object()
        deal_id = request.data.get('deal_id')
        if not deal_id:
            return Response({'error': 'deal_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            deal_pk = int(deal_id)
        except (TypeError, ValueError):
            return Response({'error': 'deal_id يجب أن يكون رقماً'}, status=status.HTTP_400_BAD_REQUEST)

        if getattr(shipment, 'transit_journal_id', None):
            return Response(
                {'error': 'الشحنة مرحَّلة محاسبياً — لا يمكن فك ربط الصفقات قبل عكس قيد التحويل.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        link = LogisticsShipmentDeal.objects.filter(shipment=shipment, deal_id=deal_pk).first()
        if not link:
            return Response({'error': 'الصفقة غير مربوطة بهذه الشحنة'}, status=status.HTTP_404_NOT_FOUND)

        try:
            link.delete()
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # إعادة توزيع الحصص على الصفقات المتبقية (T12-B1)
        try:
            redistribute_shipment_deal_allocations(shipment)
        except Exception:
            logger.exception('redistribute after remove_deal failed (shipment=%s)', shipment.pk)

        return Response({'status': 'تم فك ربط الصفقة بنجاح', 'deal_id': deal_pk}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path=r'post_agent_payment/(?P<payment_id>[^/.]+)',
    )
    def post_agent_payment_to_accounting(self, request, pk=None, payment_id=None):
        """
        ترحيل دفعة وكيل شحن (بدون صفقة) إلى المحاسبة.
        القيد: مدين حساب الوكيل (AP) | دائن حساب البنك/الصندوق — مثل دفعة المورد للصفقة.
        """
        import datetime

        shipment = self.get_object()
        try:
            pid = int(str(payment_id).strip())
        except (TypeError, ValueError):
            return Response(
                {'error': 'معرّف الدفعة غير صالح'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = LogisticsPayment.objects.get(
                pk=pid, shipment=shipment, deal__isnull=True
            )
        except LogisticsPayment.DoesNotExist:
            return Response(
                {'error': 'الدفعة غير موجودة أو لا تنتمي لهذه الشحنة'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.is_posted:
            return Response(
                {'error': 'هذه الدفعة مرحلة بالفعل'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        paid_like = payment.status in ('Paid', 'Confirmed') or bool(
            (payment.bank_swift_image or '').strip()
        )
        if not paid_like:
            return Response(
                {
                    'error': 'يجب تسجيل السليب (أو حالة Paid/Confirmed) قبل ترحيل الدفعة إلى المحاسبة',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not shipment.shipping_agent_id:
            return Response(
                {'error': 'الشحنة لا تملك وكيل شحن محدد'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # نفس إشارة الشريك: إنشاء حساب دائن تلقائياً تحت 2101/2102 إن أمكن
        accounting_api.ensure_partner_account(shipment.shipping_agent)
        agent = Partner.objects.select_related("linked_account").get(
            pk=shipment.shipping_agent_id
        )
        if not agent.linked_account:
            return Response(
                {
                    'error': (
                        "تعذّر ربط وكيل الشحن بحساب محاسبي تلقائياً. "
                        "تحقق من شجرة الحسابات (حسابات أب 2101 أو 2102) أو من مجموعة الشريك في المحاسبة، "
                        "أو عيّن نوع الشريك «FreightForwarder» لوكيل الشحن."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ext_in = (request.data.get('cash_box_external_id') or '').strip()
        if ext_in:
            payment.cash_box_external_id = ext_in[:128]
            payment.save(update_fields=['cash_box_external_id'])

        bank_account = None
        bank_account_id = request.data.get('bank_account_id')
        ext = (request.data.get('cash_box_external_id') or payment.cash_box_external_id or '').strip()

        if ext:
            link = CashBoxLedgerAccount.objects.filter(
                tenant=shipment.tenant, external_id=ext[:128]
            ).select_related('account').first()
            if not link:
                return Response(
                    {
                        'error': 'لا يوجد حساب محاسبي مربوط بهذا الصندوق. أنشئ الربط عبر POST /api/accounting/cash-box-accounts/',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            bank_account = link.account

        if bank_account is None and bank_account_id:
            try:
                bank_account = Account.objects.get(
                    pk=bank_account_id, tenant=shipment.tenant
                )
            except Account.DoesNotExist:
                return Response(
                    {'error': 'حساب البنك غير موجود'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if bank_account is None:
            bank_account = resolve_default_cash_box_account(shipment.tenant)

        if not bank_account:
            return Response(
                {
                    'error': (
                        'حدد حساب الصندوق: مرّر cash_box_external_id أو bank_account_id، '
                        'أو أنشئ ربط صندوق وعيّن DEFAULT_CASH_BOX_EXTERNAL_ID أو صندوق USD افتراضياً.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .payment_posting_cap import shipment_agent_posting_cap_check

        try:
            with transaction.atomic():
                ship_locked = (
                    LogisticsShipment.objects.select_related(
                        'shipping_agent', 'shipping_agent__linked_account', 'tenant'
                    )
                    .select_for_update()
                    .get(pk=shipment.pk)
                )
                payment_locked = LogisticsPayment.objects.select_for_update().get(
                    pk=payment.id,
                    shipment=ship_locked,
                    deal__isnull=True,
                )
                if payment_locked.is_posted:
                    return Response(
                        {'error': 'هذه الدفعة مرحلة بالفعل'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                ok_cap, cap_err = shipment_agent_posting_cap_check(
                    ship_locked, payment_locked.amount
                )
                if not ok_cap:
                    return Response({'error': cap_err}, status=status.HTTP_400_BAD_REQUEST)

                payment_date = payment_locked.transfer_date or datetime.date.today()
                foreign_amount = payment_locked.amount

                usd_currency = Currency.objects.filter(Code__iexact='USD').first()
                base_currency = Currency.objects.filter(IsBaseCurrency=True).first()
                is_foreign_usd = (
                    usd_currency
                    and base_currency
                    and base_currency.pk != usd_currency.pk
                )

                if is_foreign_usd:
                    rate = payment_locked.usd_to_ils or Decimal('1')
                    local_amount = (foreign_amount * rate).quantize(Decimal('0.01'))
                    journal_currency = usd_currency
                else:
                    rate = Decimal('1')
                    local_amount = foreign_amount
                    journal_currency = base_currency or usd_currency

                ag = ship_locked.shipping_agent
                _adesc = f"دفعة {payment_locked.title} | شحنة: {ship_locked.shipment_number}"
                # صندوق الدولار FIFO لدفعات وكيل الشحن (مثل دفعات الصفقة).
                from accounting.fx_fifo import fifo_link_for_box, build_fx_payment_lines
                fifo_link = fifo_link_for_box(bank_account, ship_locked.tenant) if is_foreign_usd else None
                if fifo_link:
                    lines_data = build_fx_payment_lines(
                        fifo_link=fifo_link, foreign_amount=foreign_amount, local_amount=local_amount,
                        debit_account_id=ag.linked_account_id, box_account_id=bank_account.id,
                        partner_id=ag.id, description=_adesc, tenant=ship_locked.tenant)
                    journal_currency, journal_rate = (base_currency or usd_currency), Decimal('1')
                else:
                    lines_data = [
                        {"account": ag.linked_account_id, "debit": local_amount, "credit": Decimal("0"), "partner": ag.id, "description": _adesc},
                        {"account": bank_account.id, "debit": Decimal("0"), "credit": local_amount, "partner": ag.id, "description": _adesc},
                    ]
                    journal_currency, journal_rate = journal_currency, rate

                journal = post_journal(
                    tenant_id=ship_locked.tenant_id,
                    transaction_date=payment_date,
                    reference_type='LOGISTICS_PAYMENT',
                    reference_id=payment_locked.id,
                    description=(
                        f"دفعة {payment_locked.title} | شحنة: {ship_locked.shipment_number} "
                        f"| وكيل شحن: {ag.name}"
                    ),
                    lines_data=lines_data,
                    currency=journal_currency,
                    exchange_rate=journal_rate,
                )

                payment_locked.is_posted = True
                payment_locked.journal = journal
                payment_locked.bank_account = bank_account
                payment_locked.save()

            return Response(
                {
                    'status': 'تم ترحيل دفعة وكيل الشحن بنجاح',
                    'journal_id': journal.id,
                    'payment_id': payment_locked.id,
                },
                status=status.HTTP_200_OK,
            )

        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("shipment post_agent_payment failed pk=%s", pk)
            return Response({'error': 'حدث خطأ غير متوقع أثناء ترحيل دفعة الوكيل.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(
        detail=True,
        methods=['post'],
        url_path=r'link_agent_payment_journal/(?P<payment_id>[^/.]+)',
    )
    def link_agent_payment_journal(self, request, pk=None, payment_id=None):
        """ربط دفعة وكيل شحن بقيد يومية أنشئ يدوياً."""
        shipment = self.get_object()
        try:
            pid = int(str(payment_id).strip())
        except (TypeError, ValueError):
            return Response(
                {'error': 'معرّف الدفعة غير صالح'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        jid_raw = request.data.get('journal_id')
        try:
            jid = int(jid_raw)
        except (TypeError, ValueError):
            return Response(
                {'error': 'أرسل journal_id رقماً (رقم القيد من شاشة اليومية).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = LogisticsPayment.objects.get(
                pk=pid, shipment=shipment, deal__isnull=True
            )
        except LogisticsPayment.DoesNotExist:
            return Response(
                {'error': 'الدفعة غير موجودة'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if payment.journal_id:
            return Response(
                {
                    'error': 'الدفعة مربوطة بقيد مسبقاً.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            journal = JournalHeader.objects.get(pk=jid, tenant_id=shipment.tenant_id)
        except JournalHeader.DoesNotExist:
            return Response(
                {'error': 'القيد غير موجود أو لا ينتمي لنفس المستأجر.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not journal.is_posted:
            return Response(
                {
                    'error': 'اربط قيداً مرحّلاً فقط (ترحيل القيد من المحاسبة أولاً).',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            pay_locked = LogisticsPayment.objects.select_for_update().get(
                pk=payment.pk, shipment=shipment, deal__isnull=True
            )
            if pay_locked.journal_id:
                return Response(
                    {'error': 'الدفعة مربوطة بقيد مسبقاً'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pay_locked.journal = journal
            pay_locked.is_posted = True
            pay_locked.save(update_fields=['journal', 'is_posted'])

        return Response(
            {
                'status': 'linked',
                'journal_id': journal.id,
                'payment_id': pay_locked.id,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def post_to_accounting(self, request, pk=None):
        """
        ترحيل تكلفة الشحن إلى المحاسبة.
        القيد: مدين مصاريف الشحن | دائن حسابات الوكيل (AP)
        """
        import datetime

        shipment = self.get_object()
        tenant = get_tenant(self.request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)

        # Idempotency: handled by post_journal
        shipping_cost = float(request.data.get('shipping_cost', 0))
        if shipping_cost <= 0:
            return Response({'error': 'الرجاء إدخال تكلفة الشحن'}, status=status.HTTP_400_BAD_REQUEST)

        if not shipment.shipping_agent:
            return Response({'error': 'الشحنة لا تملك وكيل شحن محدد'}, status=status.HTTP_400_BAD_REQUEST)

        if not shipment.shipping_agent.linked_account:
            return Response({'error': 'وكيل الشحن لا يملك حساباً محاسبياً مربوطاً'}, status=status.HTTP_400_BAD_REQUEST)

        freight_account = (
            Account.objects.filter(tenant=tenant, name__icontains='شحن').first()
            or Account.objects.filter(tenant=tenant, account_type='Expense').first()
        )
        if not freight_account:
            return Response({'error': 'لم يتم العثور على حساب مصاريف شحن'}, status=status.HTTP_400_BAD_REQUEST)

        shipping_cost_dec = Decimal(str(shipping_cost))
        lines_data = [
            {"account": freight_account.id, "debit": shipping_cost_dec, "credit": Decimal("0"), "partner": shipment.shipping_agent_id},
            {"account": shipment.shipping_agent.linked_account_id, "debit": Decimal("0"), "credit": shipping_cost_dec, "partner": shipment.shipping_agent_id},
        ]

        try:
            journal = post_journal(
                tenant_id=tenant.TenantID,
                transaction_date=shipment.departure_date or datetime.date.today(),
                reference_type='LOGISTICS_SHIPMENT',
                reference_id=shipment.id,
                description=f"تكلفة شحن | شحنة: {shipment.shipment_number} | وكيل: {shipment.shipping_agent.name}",
                lines_data=lines_data,
            )
        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("shipment post_to_accounting failed pk=%s", pk)
            return Response({'error': 'حدث خطأ غير متوقع أثناء ترحيل تكلفة الشحن.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'status': 'تم ترحيل تكلفة الشحن بنجاح',
            'journal_id': journal.id
        }, status=status.HTTP_200_OK)

    def _shipment_is_posted(self, shipment):
        """الشحنة «مرحّلة» إن وُجد قيد شحن أو حركة مخزون استلام تخصّها."""
        return JournalHeader.objects.filter(
            tenant_id=shipment.tenant_id,
            reference_type='LOGISTICS_SHIPMENT',
            reference_id=shipment.id,
        ).exists() or StockMovement.objects.filter(
            tenant_id=shipment.tenant_id,
            reference_type='SHIPMENT',
            reference_id=shipment.id,
        ).exists()

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance is not None and self._shipment_is_posted(instance):
            changed_fields = set(serializer.validated_data.keys())
            if changed_fields - {'agent_payments'}:
                raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        # تغيير تكلفة الشحن بعد الاستحقاق يجعل القيد لا يطابق التكلفة. (سعر الصرف
        # وحالة الترحيل read_only أصلاً — يملكهما مسارا الاستحقاق وحدهما.)
        if (
            instance is not None
            and instance.freight_is_posted
            and 'total_shipping_cost_usd' in serializer.validated_data
            and Decimal(str(serializer.validated_data['total_shipping_cost_usd'] or 0))
            != Decimal(str(instance.total_shipping_cost_usd or 0))
        ):
            raise ValidationError({
                'detail': 'استحقاق شحن الوكيل مُرحّل — ألغِ ترحيل الاستحقاق قبل تعديل تكلفة الشحن.',
                'can_unpost': True,
            })
        # الوكيل هو **الطرف المُدائن** في قيد الاستحقاق. تغييره أو إزالته بعد
        # الترحيل كان مسموحاً، فتظهر الشحنة «بلا وكيل» بينما القيد ما يزال يُدائن
        # الوكيل الأصلي — المستند والأستاذ يتناقضان ولا يعرف المستخدم من دائن.
        if (
            instance is not None
            and instance.freight_is_posted
            and 'shipping_agent' in serializer.validated_data
            and getattr(serializer.validated_data['shipping_agent'], 'pk', None)
            != instance.shipping_agent_id
        ):
            raise ValidationError({
                'detail': (
                    'استحقاق شحن الوكيل مُرحّل باسم الوكيل الحالي — ألغِ ترحيل الاستحقاق '
                    'قبل تغيير الوكيل أو إزالته، وإلا بقي القيد يُدائن وكيلاً غير الظاهر.'
                ),
                'can_unpost': True,
            })
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._shipment_is_posted(instance):
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='unpost')
    @requires_perm('import.doc.unpost')
    def unpost(self, request, pk=None):
        """تراجع عن الترحيل: حذف قيد الشحن وعكس حركات استلام مخزونها."""
        shipment = self.get_object()
        if not self._shipment_is_posted(shipment):
            return Response(
                {'error': 'الشحنة غير مُرحّلة.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                result = unpost_document(
                    tenant_id=shipment.tenant_id,
                    reference_id=shipment.id,
                    journal_reference_types=['LOGISTICS_SHIPMENT'],
                    stock_reference_types=['SHIPMENT'],
                    user=request.user,
                    document_label=f"شحنة {shipment.shipment_number}",
                )
                # توحيد التكلفة (task23): بعد عكس استلام الشحنة يُعاد ضبط
                # avg_cost من المشتريات المرحّلة المتبقية (النموذج الدوري)؛
                # شركات المتوسط المتحرك تُتخطّى مركزياً.
                from inventory.services import apply_purchase_cost_model
                _seen_products = set()
                for deal in shipment.deals.all():
                    for it in deal.items.select_related('product').filter(is_deleted=False):
                        if it.product_id and it.product_id not in _seen_products:
                            _seen_products.add(it.product_id)
                            apply_purchase_cost_model(it.product)
        except Exception as e:
            err = '؛ '.join(e.messages) if hasattr(e, 'messages') else str(e)
            return Response({'error': err}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'تم التراجع عن الترحيل وحذف القيد.', 'unpost_result': result})

    @action(detail=True, methods=['post'], url_path='post-freight-accrual')
    def post_freight_accrual(self, request, pk=None):
        """إثبات استحقاق شحن الوكيل: Dr مصاريف الشحن الدولي / Cr ذمم الوكيل.

        الدفع إجراء مستقل تماماً (pay-agent / سند دفع). قبل هذا لم يكن للوكيل
        دائن أبداً فيظهر مديناً، وكان لا بدّ من تسجيل دفعة لإعطاء النظام سعر
        صرف — الآن سعر الصرف يُدخل هنا مرة واحدة ويحكم تكلفة الشحن.
        """
        shipment = self.get_object()
        raw_rate = request.data.get('freight_exchange_rate', shipment.freight_exchange_rate)
        try:
            with transaction.atomic():
                ship_locked = LogisticsShipment.objects.select_for_update().get(pk=shipment.pk)
                journal = post_freight_accrual(ship_locked, raw_rate, user=request.user)
                if journal is None:
                    return Response(
                        {'error': 'استحقاق شحن الوكيل مُرحّل بالفعل.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        except AccrualSkipped as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (ValidationError, DjangoValidationError) as ve:
            err = '؛ '.join(ve.messages) if hasattr(ve, 'messages') else str(ve)
            return Response({'error': err}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                'status': 'تم إثبات استحقاق شحن الوكيل.',
                'journal_id': journal.pk,
                'amount_ils': str(
                    (Decimal(str(ship_locked.total_shipping_cost_usd or 0))
                     * ship_locked.freight_exchange_rate).quantize(Decimal('0.01'))
                ),
                'freight_exchange_rate': str(ship_locked.freight_exchange_rate),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='unpost-freight-accrual')
    @requires_perm('import.doc.unpost')
    def unpost_freight_accrual(self, request, pk=None):
        """تراجع عن استحقاق شحن الوكيل — لا يمسّ دفعاته المرحّلة."""
        shipment = self.get_object()
        if not shipment.freight_is_posted:
            return Response(
                {'error': 'استحقاق شحن الوكيل غير مُرحّل.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                result = unpost_document(
                    tenant_id=shipment.tenant_id,
                    reference_id=shipment.pk,
                    journal_reference_types=['SHIPMENT_FREIGHT_ACCRUAL'],
                    user=request.user,
                    document_label=f"استحقاق شحن {shipment.shipment_number}",
                )
                shipment.freight_is_posted = False
                shipment.freight_journal = None
                shipment.save(update_fields=['freight_is_posted', 'freight_journal'])
                logger.info('shipment freight accrual unposted shipment=%s', shipment.pk)
        except Exception as e:
            err = '؛ '.join(e.messages) if hasattr(e, 'messages') else str(e)
            return Response({'error': err}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'تم التراجع عن استحقاق شحن الوكيل.', 'unpost_result': result})


class LogisticsClearanceViewSet(BaseTenantViewSet):
    queryset = LogisticsClearance.objects.all().order_by("-id")
    serializer_class = LogisticsClearanceSerializer

    def get_queryset(self):
        deal_mini = LogisticsDeal.objects.only(
            "id", "description", "ref_number", "notes"
        ).order_by("id")
        qs = (
            super()
            .get_queryset()
            .select_related("shipment", "customs_broker", "tenant")
            .prefetch_related(
                Prefetch("shipment__deals", queryset=deal_mini),
                "local_shipments",
                "lines",
                "payments",
            )
        )
        shipment_id = self.request.query_params.get('shipment')
        if shipment_id:
            qs = qs.filter(shipment_id=shipment_id)
        return qs

    def _clearance_is_posted(self, clearance):
        # دفعة المخلّص قيد مستقل (Dr ذمم المخلّص / Cr الصندوق) ولا تقفل مستند
        # الاستحقاق. الذي يقفل بنود التخليص فقط هو قيد الاستحقاق نفسه.
        return bool(clearance.journal_id)

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance is not None and self._clearance_is_posted(instance):
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._clearance_is_posted(instance) or instance.payments.filter(is_posted=True).exists():
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='post-to-accounting')
    def post_to_accounting(self, request, pk=None):
        """إثبات استحقاق التخليص: Dr تكاليف/ضريبة، Cr ذمم المخلّص."""
        clearance = self.get_object()
        try:
            with transaction.atomic():
                journal = post_clearance_accrual(clearance, user=request.user)
                if journal is None:
                    return Response(
                        {'error': 'استحقاق التخليص مُرحّل بالفعل.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        except AccrualSkipped as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception('clearance accrual posting failed pk=%s', clearance.pk)
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        total = sum(
            (Decimal(str(line.credit or 0)) for line in journal.lines.all()), Decimal('0'),
        )
        return Response({
            'journal_id': journal.id,
            'total': str(total),
            'message': 'تم إثبات استحقاق التخليص على ذمم المخلّص. الدفع يبقى إجراءً مستقلاً.',
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='unpost-accrual')
    @requires_perm('import.doc.unpost')
    def unpost_accrual(self, request, pk=None):
        clearance = self.get_object()
        if not clearance.journal_id:
            return Response({'error': 'استحقاق التخليص غير مُرحّل.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                result = unpost_document(
                    tenant_id=clearance.tenant_id,
                    reference_id=clearance.id,
                    journal_reference_types=['LOGISTICS_CLEARANCE'],
                    user=request.user,
                    document_label=f"استحقاق تخليص {clearance.shipment.shipment_number}",
                )
                clearance.journal = None
                clearance.save(update_fields=['journal'])
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'تم التراجع عن إثبات استحقاق التخليص.', 'unpost_result': result})

    @action(detail=True, methods=['post'], url_path='unpost')
    @requires_perm('import.doc.unpost')
    def unpost(self, request, pk=None):
        """تراجع عن ترحيل التخليص: حذف قيود كل دفعاته المرحّلة وإرجاعها مسودات."""
        clearance = self.get_object()
        posted_payments = list(clearance.payments.filter(is_posted=True))
        if not posted_payments:
            return Response(
                {'error': 'لا توجد دفعات تخليص مرحّلة.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                total = {'journals_deleted': 0, 'lines_deleted': 0, 'stock_movements_deleted': 0}
                for pay in posted_payments:
                    r = unpost_document(
                        tenant_id=clearance.tenant_id,
                        reference_id=pay.id,
                        journal_reference_types=['CLEARANCE_PAYMENT', 'LOGISTICS_CLEARANCE_PAYMENT'],
                        user=request.user,
                        document_label=f"دفعة تخليص #{clearance.id}",
                    )
                    for k in total:
                        total[k] += r[k]
                    pay.is_posted = False
                    pay.journal = None
                    pay.save(update_fields=['is_posted', 'journal'])
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'تم التراجع عن الترحيل وحذف القيود.', 'unpost_result': total})

    @action(detail=True, methods=["get"])
    def payments(self, request, pk=None):
        clearance = self.get_object()
        rows = (
            LogisticsClearancePayment.objects.filter(clearance=clearance)
            .select_related("customs_broker", "journal")
            .order_by("-payment_date", "-id")
        )
        ser = LogisticsClearancePaymentSerializer(rows, many=True)
        return Response(ser.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def pay_from_cashbox(self, request, pk=None):
        """
        دفع تخليص أو شحن من الصندوق:
        - clearance (افتراضي): مدين حساب المخلّص المرتبط بالتخليص.
        - shipping: مدين حساب شريك يُختار (ناقل/سائق) عبر payee_partner_id.
        دائن: حساب الصندوق.
        يُنشأ القيد كـ Draft (غير مرحّل).
        """
        clearance = self.get_object()
        SHIPPING_COST_LINE_LABEL = "دفعة الشحن (الناقل)"

        kind = str(request.data.get("payment_kind") or "clearance").strip().lower()
        if kind not in ("clearance", "shipping"):
            kind = "clearance"

        payee = None
        if kind == "shipping":
            pid = request.data.get("payee_partner_id")
            if pid is None or str(pid).strip() == "":
                return Response(
                    {"error": "يرجى اختيار السائق أو الناقل (شريك) لدفعة الشحن."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                payee_pk = int(pid)
            except (TypeError, ValueError):
                return Response(
                    {"error": "معرّف شريك الدفع غير صالح."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            payee = Partner.objects.filter(tenant=clearance.tenant, pk=payee_pk).first()
            if not payee:
                return Response(
                    {"error": "شريك الدفع غير موجود."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not getattr(payee, "linked_account_id", None):
                return Response(
                    {"error": "الشريك غير مربوط بحساب في المحاسبة (linked_account)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            payee = clearance.customs_broker
            if not payee:
                return Response(
                    {"error": "لا يمكن الدفع: لم يتم تحديد المخلّص الجمركي."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not getattr(payee, "linked_account_id", None):
                return Response(
                    {"error": "المخلّص غير مربوط بحساب في المحاسبة (linked_account)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        ext = str(request.data.get("cash_box_external_id") or "").strip()
        if not ext:
            return Response(
                {"error": "حقل cash_box_external_id مطلوب."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cash_link = CashBoxLedgerAccount.objects.filter(
            tenant=clearance.tenant, external_id=ext[:128]
        ).first()
        if not cash_link or not cash_link.account_id:
            return Response(
                {"error": "الصندوق غير مربوط بحساب محاسبي."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = Decimal(str(request.data.get("amount") or "0"))
        except Exception:
            amount = Decimal("0")
        if amount <= 0:
            return Response(
                {"error": "المبلغ يجب أن يكون أكبر من صفر."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pd_raw = request.data.get("payment_date")
        try:
            payment_date = (
                datetime.date.fromisoformat(str(pd_raw)[:10])
                if pd_raw
                else datetime.date.today()
            )
        except Exception:
            payment_date = datetime.date.today()
        notes = str(request.data.get("notes") or "").strip()

        cost_lines = clearance_cost_line_dicts(clearance)
        clearance_budget = sum(
            Decimal(str(row.get("amount", 0) or 0))
            for row in cost_lines
            if str(row.get("label") or "").strip() != SHIPPING_COST_LINE_LABEL
        )
        shipping_budget = sum(
            Decimal(str(row.get("amount", 0) or 0))
            for row in cost_lines
            if str(row.get("label") or "").strip() == SHIPPING_COST_LINE_LABEL
        )
        existing_payments = list(
            LogisticsClearancePayment.objects.filter(clearance=clearance)
        )

        def _paid_clearance() -> Decimal:
            return sum(
                (p.amount for p in existing_payments if p.payment_purpose != 'shipping' and p.is_posted),
                start=Decimal("0"),
            )

        def _paid_shipping() -> Decimal:
            return sum(
                (p.amount for p in existing_payments if p.payment_purpose == 'shipping' and p.is_posted),
                start=Decimal("0"),
            )

        from .payment_posting_cap import clearance_broker_posting_cap_check

        if kind == "clearance":
            clearance_broker_posting_cap_check(
                _paid_clearance(), amount, clearance_budget,
                label=f"clearance {clearance.pk} broker",
            )
        else:
            clearance_broker_posting_cap_check(
                _paid_shipping(), amount, shipping_budget,
                label=f"clearance {clearance.pk} shipping",
            )

        try:
            with transaction.atomic():
                pay_currency = None
                cur_raw = request.data.get('currency_id')
                if cur_raw is not None:
                    try:
                        pay_currency = Currency.objects.get(pk=int(cur_raw))
                    except Exception:
                        pay_currency = None
                if pay_currency is None:
                    pay_currency = Currency.objects.filter(Code__iexact='ILS').first()

                base_cur = Currency.objects.filter(IsBaseCurrency=True).first()
                if pay_currency and base_cur and pay_currency.pk != base_cur.pk:
                    pay_rate = get_exchange_rate(
                        clearance.tenant_id, pay_currency.pk, base_cur.pk, payment_date,
                    )
                else:
                    pay_rate = Decimal("1")

                purpose = 'shipping' if kind == 'shipping' else 'clearance_fee'

                if kind == "shipping":
                    jdesc = (
                        f"[دفع شحن] شحنة {clearance.shipment.shipment_number} — "
                        f"{payee.name} — صندوق {cash_link.name}"
                    )[:500]
                    line_desc = f"دفع شحن — {clearance.shipment.shipment_number}"
                else:
                    jdesc = (
                        f"[تخليص شحنة {clearance.shipment.shipment_number}] "
                        f"دفع للمخلّص {payee.name} من الصندوق {cash_link.name}"
                    )[:500]
                    line_desc = f"دفع تخليص جمركي — {clearance.shipment.shipment_number}"

                pay = LogisticsClearancePayment.objects.create(
                    tenant=clearance.tenant,
                    clearance=clearance,
                    customs_broker=payee,
                    amount=amount,
                    currency=pay_currency,
                    payment_date=payment_date,
                    payment_purpose=purpose,
                    cash_box_external_id=ext[:128],
                    notes=notes,
                    is_posted=False,
                )
                # P-H-9: shared validation gate. Same as customer / deal /
                # shipment-agent payment surfaces. We're inside the
                # transaction.atomic block already, so raising rolls the
                # ClearancePayment row back.
                from core.payments import PaymentContext, validate_payment
                ctx = PaymentContext.from_clearance_payment(pay)
                errors = validate_payment(ctx)
                if errors:
                    raise DjangoValidationError(errors)

                # صندوق الدولار FIFO: عند الدفع من صندوق بعملة أجنبية له طبقات،
                # يُحوَّل القيد للشيقل (amount × سعر الدفع) وتُسحب التكلفة FIFO + فرق صرف محقّق.
                from accounting.fx_fifo import fifo_link_for_box, build_fx_payment_lines
                is_foreign_pay = bool(pay_currency and base_cur and pay_currency.pk != base_cur.pk)
                fifo_link = fifo_link_for_box(cash_link.account, clearance.tenant) if is_foreign_pay else None
                if fifo_link:
                    local_amount = (amount * pay_rate).quantize(Decimal("0.01"))
                    lines_data = build_fx_payment_lines(
                        fifo_link=fifo_link, foreign_amount=amount, local_amount=local_amount,
                        debit_account_id=payee.linked_account_id, box_account_id=cash_link.account_id,
                        partner_id=payee.pk, description=line_desc, tenant=clearance.tenant)
                    jcurrency, jrate = base_cur, Decimal("1")
                else:
                    lines_data = [
                        {
                            "account": payee.linked_account_id,
                            "partner": payee.pk,
                            "debit": amount,
                            "credit": Decimal("0"),
                            "description": line_desc,
                        },
                        {
                            "account": cash_link.account_id,
                            "partner": payee.pk,
                            "debit": Decimal("0"),
                            "credit": amount,
                            "description": f"صرف من الصندوق {cash_link.name}",
                        },
                    ]
                    jcurrency, jrate = pay_currency, pay_rate

                jh = post_journal(
                    tenant_id=clearance.tenant_id,
                    transaction_date=payment_date,
                    reference_type="CLEARANCE_PAYMENT",
                    reference_id=pay.id,
                    description=jdesc,
                    lines_data=lines_data,
                    currency=jcurrency,
                    exchange_rate=jrate,
                    user=request.user if hasattr(request, 'user') else None,
                )

                pay.journal = jh
                pay.is_posted = True
                pay.save(update_fields=["journal", "is_posted"])

            ser = LogisticsClearancePaymentSerializer(pay)
            logger.info(
                'clearance payment posted clearance=%s payment=%s journal=%s amount=%s',
                clearance.pk, pay.pk, jh.pk, amount,
            )
            return Response(
                {
                    "status": "تم ترحيل الدفع بنجاح.",
                    "journal_id": jh.id,
                    "payment": ser.data,
                },
                status=status.HTTP_201_CREATED,
            )
        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("clearance pay_from_cashbox failed")
            return Response({"error": "حدث خطأ غير متوقع أثناء تسجيل الدفع."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='unpost-payment')
    @requires_perm('import.doc.unpost')
    def unpost_payment(self, request, pk=None):
        """إلغاء ترحيل دفعة تخليص جمركي — قيد عكسي."""
        clearance = self.get_object()
        payment_id = request.data.get('payment_id')
        if not payment_id:
            return Response({"error": "payment_id مطلوب."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment_id_int = int(payment_id)
        except (TypeError, ValueError):
            return Response({"error": "payment_id غير صالح."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = LogisticsClearancePayment.objects.select_related('journal').get(
                pk=payment_id_int, clearance=clearance,
            )
        except LogisticsClearancePayment.DoesNotExist:
            return Response({"error": "الدفعة غير موجودة."}, status=status.HTTP_404_NOT_FOUND)

        if not payment.is_posted or not payment.journal:
            return Response({"error": "الدفعة غير مرحّلة."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                orig = payment.journal
                rev_date_raw = request.data.get('reversal_date')
                try:
                    rev_date = (
                        datetime.datetime.strptime(str(rev_date_raw)[:10], "%Y-%m-%d").date()
                        if rev_date_raw
                        else datetime.date.today()
                    )
                except ValueError:
                    rev_date = datetime.date.today()

                # المرحلة 2: القيد العكسي عبر accounting.api (يفحص الفترة
                # والتوازن) مع نسخ عملة الأصل وسعر صرفه — الأصل يبقى مرحّلاً.
                rev = accounting_api.reverse_journal(
                    orig,
                    reference_type="CLEARANCE_PAYMENT_UNPOST",
                    reference_id=payment.id,
                    transaction_date=rev_date,
                    description=(
                        f"[إلغاء ترحيل] دفع تخليص #{payment.id} — "
                        f"عكس القيد #{orig.id}"
                    ),
                    line_description_prefix=f"عكس #{orig.id}: ",
                    copy_currency=True,
                )
                # نُبقي رابط القيد الأصلي للتدقيق (أيّ قيد رحّل هذه الدفعة)؛
                # حارس إعادة الدخول يعتمد is_posted=False لمنع إلغاء ترحيل مزدوج.
                payment.is_posted = False
                payment.save(update_fields=['is_posted'])
        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as ie:
            return Response({"error": str(ie)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("clearance unpost_payment failed")
            return Response(
                {"error": "حدث خطأ غير متوقع أثناء إلغاء ترحيل دفعة التخليص."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "message": "تم إلغاء الترحيل بقيد عكسي.",
            "reversal_journal_id": rev.id,
        })


# تفصيل حركة التعديل في سجل النشاط — نفس عقد فاتورة البيع (core.activity).
PURCHASE_ACTIVITY_FIELD_LABELS = {
    'partner': 'المورد',
    'invoice_name': 'اسم الفاتورة',
    'invoice_date': 'تاريخ الفاتورة',
    'payment_type': 'نوع الدفع',
    'supplier_invoice_number': 'رقم فاتورة المورد',
    'discount_amount': 'خصم الفاتورة',
    'shipping_cost': 'تكلفة الشحن',
    'exchange_rate': 'سعر الصرف',
    'notes': 'الملاحظات',
}
PURCHASE_ACTIVITY_ITEM_LABELS = {
    'name': 'البيان',
    'quantity': 'الكمية',
    'unit_price': 'السعر',
    'discount_amount': 'خصم البند',
}


def _purchase_item_snapshot(invoice):
    """لقطة بنود فاتورة الشراء من القاعدة — لا من ذاكرة prefetch (قديمة بعد الحفظ)."""
    items = PurchaseInvoiceItem.objects.filter(invoice=invoice).select_related('product')
    return snapshot_document_lines(
        items,
        label=lambda item: (
            item.name
            or (item.product and (item.product.name_ar or item.product.name_en or item.product.sku))
            or '—'
        ),
        fields=PURCHASE_ACTIVITY_ITEM_LABELS,
    )


class PurchaseInvoiceViewSet(PagePartnerBalanceMixin, BaseTenantViewSet):
    serializer_class = PurchaseInvoiceSerializer
    partner_balance_spec = ("partner_id", True, "supplier_balance")

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseInvoiceListSerializer
        return PurchaseInvoiceSerializer

    def get_queryset(self):
        qs = PurchaseInvoice.objects.all().select_related(
            'partner', 'deal', 'shipment', 'clearance', 'currency', 'journal',
        ).order_by('-created_at')
        # كما في الصفقات: الرصيد للقائمة يأتي من الـmixin بعد الترقيم.
        if self.action != 'list':
            qs = annotate_partner_posted_balance(
                qs, "partner_id", supplier=True, alias="supplier_balance",
            )
        if self.action == 'list':
            qs = qs.annotate(items_count=Count('items'))
            qs = annotate_purchase_invoice_payment_summary(qs)
        else:
            qs = qs.prefetch_related(
                'items__product', 'fees',
                Prefetch(
                    'payments',
                    queryset=PurchaseInvoicePayment.objects.select_related(
                        'currency', 'cash_or_bank_account', 'journal',
                    ),
                ),
                Prefetch(
                    'supplier_payments',
                    queryset=SupplierPayment.objects.select_related(
                        'currency', 'cash_or_bank_account', 'journal',
                    ),
                ),
            )
        tenant = self._get_tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        params = self.request.query_params
        s = params.get('status')
        if s:
            qs = qs.filter(status=s)
        payment_status = params.get('payment_status')
        if self.action == 'list' and payment_status in ('paid', 'partially_paid', 'unpaid'):
            qs = qs.filter(list_payment_status=payment_status)
        posted = str(params.get('is_posted') or '').lower()
        if posted in ('true', '1', 'false', '0'):
            qs = qs.filter(is_posted=posted in ('true', '1'))
        p = params.get('partner')
        if p:
            qs = qs.filter(partner_id=p)
        d = params.get('deal')
        if d:
            qs = qs.filter(deal_id=d)
        sh = params.get('shipment')
        if sh:
            qs = qs.filter(shipment_id=sh)
        df = params.get('date_from')
        if df:
            qs = qs.filter(invoice_date__gte=df)
        dt = params.get('date_to')
        if dt:
            qs = qs.filter(invoice_date__lte=dt)
        search = params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(invoice_name__icontains=search) |
                Q(partner__name__icontains=search)
            )
        # فصل المحلية/الدولية: فلتر صريح + إخفاء الدولية عمّن لا يملك صلاحية الاستيراد.
        it = params.get('invoice_type')
        if it in (PurchaseInvoice.INVOICE_TYPE_LOCAL, PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL):
            qs = qs.filter(invoice_type=it)
        # فلتر فاتورة/مرجع: is_return=true|false (غياب الباراميتر ⇒ الكل).
        ret = params.get('is_return')
        if ret is not None and str(ret).lower() in ('true', '1', 'false', '0'):
            qs = qs.filter(is_return=str(ret).lower() in ('true', '1'))
        from core.import_access import user_can_access_import
        if tenant and not user_can_access_import(self.request.user, tenant):
            qs = qs.filter(invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL)
        return qs

    def _get_tenant(self):
        return get_tenant(self.request)

    def _next_invoice_number(self, tenant):
        last = (
            PurchaseInvoice.objects
            .filter(tenant=tenant)
            .order_by('-id')
            .values_list('invoice_number', flat=True)
            .first()
        )
        if last and last.startswith('INV-'):
            try:
                num = int(last.split('-')[1]) + 1
                return f"INV-{num:04d}"
            except (ValueError, IndexError):
                pass
        count = PurchaseInvoice.objects.filter(tenant=tenant).count()
        return f"INV-{count + 1:04d}"

    def _sync_attachments(self, invoice):
        """W7c: يحفظ روابط الصور/PDF المرفوعة (quote_images/quote_pdfs) في
        SystemAttachment (idempotent بالرابط، related_table='purchase_invoices') —
        مرآة نمط الموردين/المنتجات. إضافة فقط (لا حذف)؛ غير حاجب — لا يكسر الحفظ."""
        try:
            from core.models import SystemAttachment
            data = self.request.data
            tenant = invoice.tenant

            def _save(url, file_type):
                if not (url and isinstance(url, str) and url.startswith('http')):
                    return
                if not SystemAttachment.objects.filter(
                    tenant=tenant, related_table='purchase_invoices',
                    related_id=invoice.id, file_path=url,
                ).exists():
                    SystemAttachment.objects.create(
                        tenant=tenant, related_table='purchase_invoices',
                        related_id=invoice.id, file_type=file_type, file_path=url,
                    )

            for u in (data.get('quote_images') or []):
                _save(u, 'Image')
            for p in (data.get('quote_pdfs') or []):
                _save(p.get('url') if isinstance(p, dict) else p, 'PDF')
        except Exception:
            logger.exception('purchase-invoice attachment sync failed for invoice=%s', getattr(invoice, 'id', None))

    def perform_create(self, serializer):
        require_perm(self.request, 'purchase.invoice.create')
        tenant = self._get_tenant()
        # T-PLANLIMITS: حدّ الخطة قبل الحفظ — الفاتورة المحفوظة تُحسب ضمن الحدّ.
        enforce_limits(tenant, 'purchase.invoices', 'documents.invoices')
        inv_num = self.request.data.get('invoice_number') or self._next_invoice_number(tenant)
        # نوع الفاتورة: صريح إن مُرّر، وإلا يُشتق من ارتباط مسار الاستيراد.
        vd = serializer.validated_data
        req_type = (self.request.data.get('invoice_type') or '').strip()
        if req_type in (PurchaseInvoice.INVOICE_TYPE_LOCAL, PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL):
            invoice_type = req_type
        elif vd.get('deal') or vd.get('shipment') or vd.get('clearance'):
            invoice_type = PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL
        else:
            invoice_type = PurchaseInvoice.INVOICE_TYPE_LOCAL
        # الفاتورة الدولية (الاستيراد) محجوبة عمّن لا يملك الصلاحية.
        if invoice_type == PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL:
            from core.import_access import user_can_access_import
            from rest_framework.exceptions import PermissionDenied
            if not user_can_access_import(self.request.user, tenant):
                raise PermissionDenied("صلاحية الفاتورة الدولية (الاستيراد) غير متاحة لحسابك.")
        invoice = serializer.save(tenant=tenant, invoice_number=inv_num, invoice_type=invoice_type)
        self._sync_attachments(invoice)
        log_activity(
            action='create', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            description='إنشاء ' + ('مرجع شراء' if invoice.is_return else 'فاتورة شراء'),
            partner_ids=[invoice.partner_id],
            request=self.request,
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        obj = self.get_object()
        log_view(
            entity_type='purchase_invoice', entity_id=obj.id,
            entity_label=obj.invoice_number, request=request,
        )
        return response

    @action(detail=False, methods=['get'], url_path='resolve-price')
    def resolve_price(self, request):
        """FEAT-1: سعر الوحدة المقترح لصنف حسب استراتيجية إعدادات الشراء.

        يفوّض إلى core.pricing (المصدر المشترك مع المبيعات). الاستراتيجية تؤخذ من
        إعدادات الشراء افتراضياً ويمكن تجاوزها بـ ?strategy=.
        """
        from decimal import Decimal

        from core.pricing import resolve_purchase_price
        from logistics.services import get_or_create_purchase_settings

        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'لا يوجد شركة (tenant).'}, status=status.HTTP_400_BAD_REQUEST)
        pid = request.query_params.get('product')
        if not pid or not str(pid).isdigit():
            return Response({'error': 'باراميتر product مطلوب.'}, status=status.HTTP_400_BAD_REQUEST)
        strategy = request.query_params.get('strategy') or get_or_create_purchase_settings(
            tenant
        ).purchase_default_price_strategy
        rate = request.query_params.get('exchange_rate')
        cur = request.query_params.get('currency')
        sup = request.query_params.get('supplier')
        data = resolve_purchase_price(
            tenant_id=tenant.TenantID,
            product_id=int(pid),
            strategy=strategy,
            supplier_id=int(sup) if sup and str(sup).isdigit() else None,
            target_currency_id=int(cur) if cur and str(cur).isdigit() else None,
            target_exchange_rate=Decimal(str(rate)) if rate else Decimal('1'),
        )
        return Response(data)

    @action(detail=False, methods=['get'], url_path='price-list')
    def price_list(self, request):
        """task24: سعر الشراء المقترح لكل المنتجات دفعة واحدة — يُعرض داخل خيارات
        منتقي الأصناف في الفاتورة بلا نقر. يفوّض لـ core.pricing (المصدر المشترك).
        الاستراتيجية من إعدادات الشراء افتراضياً ويمكن تجاوزها بـ ?strategy=.
        و‍`?supplier=` يحصر «آخر شراء» بمورد الفاتورة (يبقى «أقل شراء» عاماً).
        """
        from core.pricing import purchase_price_list
        from logistics.services import get_or_create_purchase_settings

        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'لا يوجد شركة (tenant).'}, status=status.HTTP_400_BAD_REQUEST)
        strategy = request.query_params.get('strategy') or get_or_create_purchase_settings(
            tenant
        ).purchase_default_price_strategy
        sup = request.query_params.get('supplier')
        prices = purchase_price_list(
            tenant_id=tenant.TenantID,
            strategy=strategy,
            supplier_id=int(sup) if sup and str(sup).isdigit() else None,
        )
        rows = [
            {
                "product_id": pid,
                "unit_price": d["unit_price"],
                "source_type": d["source_type"],
                "source_label": d["source_label"],
                "prices": d.get("prices", []),
            }
            for pid, d in prices.items()
        ]
        return Response(rows)

    @action(detail=True, methods=['get'], url_path='receivable-lines')
    def receivable_lines(self, request, pk=None):
        """بنود الفاتورة القابلة للاستلام (المفوتر/المستلَم/المتبقي).

        مصدر واحد يغذّي نافذة «استلام» ومنتقي بنود محرّر الإرسالية معاً، فلا
        تعرض الواجهة بنداً يرفضه الخادم.
        """
        invoice = self.get_object()
        rows = []
        for it in invoice.items.select_related('product').all():
            if not it.product_id:
                continue
            ordered = Decimal(str(it.quantity or 0))
            received = Decimal(str(it.received_quantity or 0))
            rows.append({
                'item_id': it.id,
                'product': it.product_id,
                'product_name': str(it.product),
                'name': it.name,
                'unit_price': str(it.unit_price or 0),
                'quantity': str(ordered),
                'received_quantity': str(received),
                'remaining_quantity': str(max(Decimal('0'), ordered - received)),
            })
        return Response({
            'invoice_number': invoice.invoice_number,
            'partner_name': invoice.partner.name if invoice.partner_id else '',
            'invoice_date': invoice.invoice_date,
            'receipt_status': invoice.receipt_status,
            'receipt_status_display': invoice.get_receipt_status_display(),
            'is_local': not (invoice.deal_id or invoice.shipment_id or invoice.clearance_id),
            'is_posted': invoice.is_posted,
            'lines': rows,
        })

    @action(detail=True, methods=['post'], url_path='receive')
    def receive(self, request, pk=None):
        """استلام بضاعة فاتورة محلية إلى المخزن (انعكاس على المستودع + قيد).

        Body: { "lines": [ { "item_id": int, "quantity": number, "warehouse_id": int }, ... ] }
        حصري للفواتير غير المستوردة (بلا صفقة/شحنة/تخليص).
        """
        from core.tenant_utils import get_branch
        from .services import receive_purchase_invoice

        invoice = self.get_object()
        tenant = self._get_tenant()
        branch = get_branch(request, tenant) if tenant else None
        lines = request.data.get('lines') or []
        if not isinstance(lines, list):
            return Response({'error': 'lines يجب أن تكون قائمة'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = receive_purchase_invoice(
                invoice, lines=lines, branch=branch, user=request.user,
            )
        except DjangoValidationError as ve:
            msg = ve.message if hasattr(ve, 'message') else (ve.messages[0] if getattr(ve, 'messages', None) else str(ve))
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as ve:
            return Response({'error': ve.detail if hasattr(ve, 'detail') else str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('purchase invoice receive failed')
            return Response({'error': 'حدث خطأ غير متوقع أثناء الاستلام.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'receipt_status': result['receipt_status'],
            'journal_id': result['journal'].id if result['journal'] else None,
            'movements_created': len(result['movements']),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='returns')
    def create_return(self, request):
        """مرجع شراء: إنشاء فاتورة إرجاع للمورد وترحيلها (خفض المخزون + قيد عكسي).

        Body: {
          "original_invoice": int (اختياري),
          "supplier": int,
          "return_date": "YYYY-MM-DD",
          "reason": str,
          "lines": [ { "product": int, "quantity": number, "unit_price": number }, ... ]
        }
        """
        from .services import create_purchase_return

        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'لا يوجد شركة (tenant).'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data or {}
        supplier_id = data.get('supplier') or data.get('partner')
        if not supplier_id:
            return Response({'error': 'المورد مطلوب.'}, status=status.HTTP_400_BAD_REQUEST)
        partner = Partner.objects.filter(pk=supplier_id, tenant=tenant).first()
        if not partner:
            return Response({'error': 'المورد غير موجود.'}, status=status.HTTP_400_BAD_REQUEST)

        original = None
        oid = data.get('original_invoice')
        if oid:
            original = PurchaseInvoice.objects.filter(pk=oid, tenant=tenant).first()
            if not original:
                return Response({'error': 'الفاتورة الأصلية غير موجودة.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ret = create_purchase_return(
                tenant,
                original_invoice=original,
                partner=partner,
                return_date=data.get('return_date') or None,
                lines=data.get('lines') or [],
                notes=data.get('reason') or '',
                exchange_rate=(original.exchange_rate if original else None),
                user=request.user,
            )
        except DjangoValidationError as ve:
            msg = ve.message if hasattr(ve, 'message') else (ve.messages[0] if getattr(ve, 'messages', None) else str(ve))
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as ve:
            return Response({'error': ve.detail if hasattr(ve, 'detail') else str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('purchase return failed')
            return Response({'error': 'حدث خطأ غير متوقع أثناء إنشاء مرجع الشراء.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            PurchaseInvoiceSerializer(ret, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'], url_path='returnable-lines')
    def returnable_lines(self, request, pk=None):
        """W6: بنود الفاتورة الأصلية القابلة للإرجاع (المفوتر · المرتجع · المتبقّي) —
        يغذّي منتقي بنود مرجع الشراء في الواجهة بدل نسخ كل الأسطر."""
        from .services import returnable_lines_for_invoice

        tenant = self._get_tenant()
        invoice = PurchaseInvoice.objects.filter(pk=pk, tenant=tenant).first()
        if not invoice:
            return Response({'error': 'الفاتورة غير موجودة.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'original_invoice': invoice.id,
            'invoice_number': invoice.invoice_number,
            'partner': invoice.partner_id,
            'partner_name': invoice.partner.name if invoice.partner_id else None,
            'lines': returnable_lines_for_invoice(invoice),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='preview-clearance-import')
    def preview_clearance_import(self, request):
        """معاينة توزيع التكاليف قبل الاستيراد."""
        tenant = self._get_tenant()
        try:
            cid = int(request.data.get('clearance_id'))
        except (TypeError, ValueError):
            return Response({'error': 'clearance_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        deal_ids = request.data.get('deal_ids') or []
        try:
            deal_ids = [int(x) for x in deal_ids]
        except (TypeError, ValueError):
            return Response({'error': 'deal_ids غير صالحة'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            dr = Decimal(str(request.data.get('deal_remaining_rate', '3.6')))
            sr = Decimal(str(request.data.get('shipment_remaining_rate', '3.6')))
        except Exception:
            return Response({'error': 'سعر صرف غير صالح'}, status=status.HTTP_400_BAD_REQUEST)
        use_cl = bool(request.data.get('use_cost_lines', False))
        try:
            clr = LogisticsClearance.objects.select_related('shipment').get(pk=cid, tenant=tenant)
        except LogisticsClearance.DoesNotExist:
            return Response({'error': 'التخليص غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        prev = preview_landed_import(
            clearance=clr,
            deal_ids=deal_ids,
            deal_remaining_rate=dr,
            shipment_remaining_rate=sr,
            use_cost_lines=use_cl,
        )
        return Response(prev)

    @action(detail=False, methods=['get'], url_path='clearance-import-options')
    def clearance_import_options(self, request):
        tenant = self._get_tenant()
        try:
            clearance_id = int(request.query_params.get('clearance_id'))
        except (TypeError, ValueError):
            return Response({'error': 'clearance_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        clearance = LogisticsClearance.objects.select_related('shipment').filter(
            pk=clearance_id, tenant=tenant,
        ).first()
        if not clearance:
            return Response({'error': 'التخليص غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        links = LogisticsShipmentDeal.objects.filter(
            shipment=clearance.shipment,
        ).select_related('deal').order_by('id')
        invoices = {
            int(invoice.deal_id): invoice
            for invoice in PurchaseInvoice.objects.filter(
                tenant=tenant, shipment=clearance.shipment,
                deal_id__isnull=False, is_return=False,
            ).order_by('id')
        }
        deals = []
        for link in links:
            invoice = invoices.get(int(link.deal_id))
            deals.append({
                'deal_id': link.deal_id,
                'deal_ref': link.deal.ref_number,
                'is_converted': invoice is not None,
                'invoice_id': invoice.id if invoice else None,
                'invoice_number': invoice.invoice_number if invoice else None,
            })
        logger.info(
            'clearance import options clearance=%s shipment=%s pending=%s converted=%s',
            clearance.id, clearance.shipment_id,
            sum(1 for row in deals if not row['is_converted']),
            sum(1 for row in deals if row['is_converted']),
        )
        return Response({
            'clearance_id': clearance.id,
            'shipment_id': clearance.shipment_id,
            'deals': deals,
        })

    @action(detail=False, methods=['post'], url_path='import-from-clearance')
    def import_from_clearance(self, request):
        """إنشاء فواتير شراء من تخليص جمركي (منطق موحّد في الخادم)."""
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            cid = int(request.data.get('clearance_id'))
        except (TypeError, ValueError):
            return Response({'error': 'clearance_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        deal_ids = request.data.get('deal_ids') or []
        try:
            deal_ids = [int(x) for x in deal_ids]
        except (TypeError, ValueError):
            return Response({'error': 'deal_ids غير صالحة'}, status=status.HTTP_400_BAD_REQUEST)
        if not deal_ids:
            return Response({'error': 'اختر صفقة واحدة على الأقل'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            dr = Decimal(str(request.data.get('deal_remaining_rate', '3.6')))
            sr = Decimal(str(request.data.get('shipment_remaining_rate', '3.6')))
        except Exception:
            return Response({'error': 'سعر صرف غير صالح'}, status=status.HTTP_400_BAD_REQUEST)
        use_cl = bool(request.data.get('use_cost_lines', False))
        allow_unpaid_freight = bool(request.data.get('allow_unpaid_freight'))
        if allow_unpaid_freight:
            from core.user_roles import user_is_admin
            if not user_is_admin(request.user):
                return Response(
                    {'error': 'تجاوز شرط «الشحن مدفوع بالكامل» يتطلب صلاحية مدير.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        preview = preview_landed_import(
            clearance=LogisticsClearance.objects.select_related('shipment').get(pk=cid, tenant=tenant),
            deal_ids=deal_ids,
            deal_remaining_rate=dr,
            shipment_remaining_rate=sr,
            use_cost_lines=use_cl,
        )

        def _next():
            return self._next_invoice_number(tenant)

        try:
            created = import_invoices_from_clearance(
                tenant=tenant,
                clearance_id=cid,
                deal_ids=deal_ids,
                deal_remaining_rate=dr,
                shipment_remaining_rate=sr,
                use_cost_lines=use_cl,
                next_invoice_number_cb=_next,
                allow_unpaid_freight=allow_unpaid_freight,
            )
        except LogisticsClearance.DoesNotExist:
            return Response({'error': 'التخليص غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        ser = PurchaseInvoiceSerializer(created, many=True)
        logger.info(
            'clearance invoices imported clearance=%s deal_ids=%s invoice_ids=%s',
            cid, deal_ids, [invoice.id for invoice in created],
        )
        return Response({'preview': preview, 'created': ser.data}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='trace')
    def trace(self, request, pk=None):
        """M5: full backward cost trace for an import invoice —
        Invoice line → Deal → Shipment(freight) → Clearance(customs) → Transport.
        Every cost on every line is traceable to its source (target §4.6)."""
        invoice = self.get_object()
        try:
            data = build_import_trace(invoice)
        except Exception:
            logger.exception('build_import_trace failed pk=%s', pk)
            return Response(
                {'error': 'تعذّر بناء تتبّع التكلفة لهذه الفاتورة.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(data)

    @action(detail=False, methods=['post'], url_path='recalculate-landed-cost')
    def recalculate_landed_cost(self, request):
        """إعادة حساب تكلفة الاستيراد مع حفظ حالة المسودة وإعادة ترحيل المرحّل."""
        tenant = self._get_tenant()
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)
        sid = request.data.get('shipment_id')
        if sid is None:
            cid = request.data.get('clearance_id')
            if cid is not None:
                try:
                    clr = LogisticsClearance.objects.get(pk=int(cid), tenant=tenant)
                    sid = clr.shipment_id
                except (LogisticsClearance.DoesNotExist, TypeError, ValueError):
                    return Response({'error': 'التخليص غير موجود'}, status=status.HTTP_404_NOT_FOUND)
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            return Response({'error': 'shipment_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            dr = (
                Decimal(str(request.data.get('deal_remaining_rate')))
                if request.data.get('deal_remaining_rate') is not None else None
            )
            sr = (
                Decimal(str(request.data.get('shipment_remaining_rate')))
                if request.data.get('shipment_remaining_rate') is not None else None
            )
        except Exception:
            return Response({'error': 'سعر صرف غير صالح'}, status=status.HTTP_400_BAD_REQUEST)
        use_cl = (
            bool(request.data.get('use_cost_lines'))
            if 'use_cost_lines' in request.data else None
        )
        auto_repost = request.data.get('auto_repost') in (True, 1, '1', 'true', 'True')
        posted_ids = list(
            PurchaseInvoice.objects.filter(
                tenant=tenant,
                shipment_id=sid,
                invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
                is_return=False,
                is_posted=True,
            ).values_list('pk', flat=True)
        ) if auto_repost else []

        def call_detail_action(action_name, invoice_id):
            old_kwargs = getattr(self, 'kwargs', {}).copy()
            self.kwargs = {**old_kwargs, 'pk': str(invoice_id)}
            try:
                return getattr(self, action_name)(request, pk=str(invoice_id))
            finally:
                self.kwargs = old_kwargs

        try:
            with transaction.atomic():
                for invoice_id in posted_ids:
                    unpost_response = call_detail_action('unpost', invoice_id)
                    if unpost_response.status_code >= 400:
                        detail = unpost_response.data.get('error') or unpost_response.data.get('detail')
                        raise ValidationError(detail or f'تعذّر إلغاء ترحيل الفاتورة #{invoice_id}')
                result = recalculate_landed_for_shipment(
                    tenant=tenant,
                    shipment_id=sid,
                    deal_remaining_rate=dr,
                    shipment_remaining_rate=sr,
                    use_cost_lines=use_cl,
                )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        reconciliation = {
            'previously_posted': len(posted_ids),
            'reposted': 0,
            'left_draft': 0,
            'warnings': [],
        }
        for invoice_id in posted_ids:
            invoice = PurchaseInvoice.objects.filter(pk=invoice_id, tenant=tenant).first()
            if not invoice:
                continue
            if invoice.payment_type == PurchaseInvoice.PAYMENT_TYPE_CASH:
                reconciliation['left_draft'] += 1
                reconciliation['warnings'].append(
                    f'الفاتورة {invoice.invoice_number} بقيت مسودة لتجنب تكرار تسوية دفع نقدي تلقائية.'
                )
                continue
            post_response = call_detail_action('post_to_accounting', invoice_id)
            if post_response.status_code < 400:
                reconciliation['reposted'] += 1
            else:
                reconciliation['left_draft'] += 1
                detail = post_response.data.get('error') or post_response.data.get('detail')
                reconciliation['warnings'].append(
                    f'الفاتورة {invoice.invoice_number} حُدّثت وبقيت مسودة: {detail or "تعذّر إعادة الترحيل"}'
                )
        result['reconciliation'] = reconciliation
        logger.info(
            'shipment invoice reconciliation shipment=%s updated=%s reposted=%s left_draft=%s',
            sid, result.get('updated'), reconciliation['reposted'], reconciliation['left_draft'],
        )
        return Response(result)

    @action(detail=True, methods=['post'], url_path='payment-voucher')
    def payment_voucher(self, request, pk=None):
        """P-H-1 — Attach the financial voucher (cash + cheques) to a purchase invoice.

        Mirrors sales/views.py SalesInvoiceViewSet.payment_voucher.

        Body:
            {
                "cash_amount": "100.00",
                "cash_account_id": 12,
                "cheques": [
                    {"cheque_number": "12345", "amount": "50", "bank_name": "...",
                     "due_date": "2026-06-01", "issue_date": "2026-05-20", "notes": ""}
                ]
            }
        """
        invoice = self.get_object()
        try:
            attach_pi_payment_voucher(
                invoice,
                cash_amount=request.data.get('cash_amount', 0),
                cash_account_id=request.data.get('cash_account_id'),
                cheques=request.data.get('cheques') or [],
                user=request.user,
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        log_activity(
            action='payment', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number, description='سند دفع', request=request,
            partner_ids=[invoice.partner_id],
        )
        ser = PurchaseInvoiceSerializer(invoice, context={'request': request})
        return Response(ser.data)

    @action(detail=True, methods=['post'], url_path='post-to-accounting')
    @requires_perm('purchase.invoice.post')
    def post_to_accounting(self, request, pk=None):
        """
        ترحيل فاتورة الشراء إلى دفتر اليومية — قيد مزدوج كامل متوازن.

        القيد المُنتَج:
          مدين: مخزون/مشتريات (1104)   = صافي البضاعة (merchandise_net)
          مدين: ضريبة مدخلات (1105)    = tax_amount                    (إن > 0)
          مدين: حساب مصروف لكل رسم     = fee.amount                    (لكل PurchaseInvoiceFee)
             └─ إن كان capitalize_to_inventory=True يُضاف للمخزون بدل المصروف
          دائن: ذمم المورد (partner.linked_account)                    = إجمالي + مجموع الرسوم
          (Section B) ثم تسوية الدفعة النقدية عبر ذمم المورد:
          مدين: ذمم المورد / دائن: صندوق/بنك                            = المبلغ المدفوع نقداً

        القواعد:
          - يُستدعى validate_journal_entry قبل الحفظ — يرفض أي قيد غير متوازن.
          - tax_amount > 0 يتطلب حساب VAT Input (1105) أو TaxRate بـ direction=purchase؛
            وإلا يُرفض الترحيل بدل السكوت عن الفرق.
          - الحساب الدائن دائماً ذمم المورد (subledger)؛ payment_type='cash' (أو
            attached_cash_amount جزئي) يضيف تسوية نقدية تُفرّغ الذمم — لا يتجاوزها.
        """
        invoice = self.get_object()
        if invoice.is_posted:
            return Response(
                {'error': 'الفاتورة مرحّلة مسبقاً'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # مرجع الشراء: ترحيله يعكس الشراء (RETURN_OUT + Dr ذمم المورد / Cr مخزون)
        # عبر مسار مستقل — لا يمرّ بمنطق ترحيل فاتورة الشراء العادي.
        if getattr(invoice, 'is_return', False):
            from .services import post_purchase_return
            try:
                post_purchase_return(invoice, user=request.user)
            except DjangoValidationError as ve:
                msg = ve.message if hasattr(ve, 'message') else (ve.messages[0] if getattr(ve, 'messages', None) else str(ve))
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
            except ValidationError as ve:
                return Response({'error': ve.detail if hasattr(ve, 'detail') else str(ve)}, status=status.HTTP_400_BAD_REQUEST)
            invoice.refresh_from_db()
            log_activity(
                action='post', entity_type='purchase_invoice', entity_id=invoice.id,
                entity_label=invoice.invoice_number, description='ترحيل مرجع شراء', request=request,
                partner_ids=[invoice.partner_id],
            )
            return Response({
                'journal_id': invoice.journal_id,
                'message': 'تم ترحيل مرجع الشراء: خرجت الكمية من المخزن وخُفِّضت ذمم المورد.',
            })

        tenant = invoice.tenant or self._get_tenant()
        partner = invoice.partner

        # نمط «إجباري»: الأرقام شرط الترحيل نفسه لا الاستلام وحده — الاستلام مع
        # الترحيل مشروط (محلية + GR/IR + قيمة موجبة)، وترحيلٌ بلا أرقام يُقفل
        # التعديل فيسدّ الطريق. الحارس قبل أي كتابة.
        from inventory.serials import assert_purchase_serials_declared
        try:
            assert_purchase_serials_declared(invoice)
        except DjangoValidationError as e:
            return Response(
                {'error': e.message if hasattr(e, 'message') else '؛ '.join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ─── 1) الحساب الدائن دائماً = ذمم المورد (subledger) ───────────────────
        # Feature 2: ترحيل الفاتورة يدائن ذمم المورد بالكامل ولا يُسوّي النقدية —
        # الدفع للمورد يُسجَّل كوصل دفع مستقل (SupplierPayment) بعد الترحيل.
        credit_account = partner.linked_account
        if not credit_account:
            return Response(
                {'error': 'المورد بلا حساب محاسبي مربوط. اربط المورد بحساب ذمم (Trade Payables) أولاً.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ─── 2) حساب المخزون/المشتريات — P-H-7: عبر _resolve_line_account ──
        inventory_account = None
        invoice_items = list(invoice.items.select_related('product__category').all())
        if invoice_items:
            # Per-line using product account overrides
            from inventory.services import _resolve_line_account
            line_accounts: dict[int, Decimal] = {}
            for it in invoice_items:
                if it.product_id:
                    try:
                        acc = _resolve_line_account(it.product, 'purchase', tenant_id=tenant.id)
                    except Exception:
                        continue
                    line_accounts.setdefault(acc.id, Decimal('0'))
                    line_total = Decimal(str(it.total_price or it.quantity * it.unit_price or 0))
                    line_accounts[acc.id] += line_total
            if line_accounts:
                # Pick the most-used account for the single-line simplification
                inventory_account = Account.objects.get(pk=max(line_accounts, key=line_accounts.get))

        if not inventory_account:
            inventory_account = (
                Account.objects.filter(tenant=tenant, code="1104").first()
                or Account.objects.filter(
                    tenant=tenant, account_type="Asset", name__icontains="مخزون",
                ).first()
                or Account.objects.filter(
                    tenant=tenant, account_type="Expense", name__icontains="مشتريات",
                ).first()
            )
        if not inventory_account:
            return Response(
                {'error': 'لم يُعثر على حساب المخزون/المشتريات (1104). شغّل seed_professional_coa أولاً.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ─── 3) حساب ضريبة المدخلات (VAT Input) ────────────────────────────────
        grand = Decimal(str(invoice.grand_total or 0))
        tax_amt = Decimal(str(invoice.tax_amount or 0))

        if grand <= 0:
            return Response(
                {'error': 'مبلغ الفاتورة يجب أن يكون موجباً'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vat_input_account = None
        if tax_amt > 0:
            # Priority 1: explicit binding in company settings (SalesSettings.vat_input_account)
            from sales.models import SalesSettings
            ss = SalesSettings.objects.filter(tenant=tenant).first()
            if ss and ss.vat_input_account_id:
                vat_input_account = ss.vat_input_account

            # Priority 2: TaxRate with direction=purchase (explicit accounting configuration)
            if not vat_input_account:
                purchase_tax = TaxRate.objects.filter(
                    tenant=tenant, is_active=True, direction='purchase',
                ).select_related('tax_account').first()
                if (
                    purchase_tax
                    and purchase_tax.tax_account
                    and purchase_tax.tax_account.account_type == 'Asset'
                ):
                    vat_input_account = purchase_tax.tax_account

            # Priority 3: well-known account code 1105 (standard CoA seed)
            if not vat_input_account:
                vat_input_account = Account.objects.filter(tenant=tenant, code="1105").first()

            if not vat_input_account:
                return Response(
                    {
                        'error': (
                            'الفاتورة تحتوي ضريبة مدخلات قيمتها > 0 لكن لا يوجد حساب '
                            '"ضريبة القيمة المضافة - مدخلات" (1105) في شجرة الحسابات. '
                            'شغّل migration 0013 أو أنشئ الحساب يدوياً.'
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if vat_input_account.account_type != 'Asset':
                return Response(
                    {
                        'error': (
                            f'حساب ضريبة المدخلات يجب أن يكون من نوع Asset، '
                            f'لكن الحساب المُعرَّف {vat_input_account.code} من نوع {vat_input_account.account_type}.'
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ─── 4) تجهيز الرسوم (Fees) ─────────────────────────────────────────────
        fees_qs = list(invoice.fees.select_related('expense_account').all())
        fees_total = sum((Decimal(str(f.amount or 0)) for f in fees_qs), Decimal('0'))
        # نفصل: الرسوم المرسملة (capitalize → تُضاف للمخزون) عن غير المرسملة (Expense)
        capitalized_total = sum(
            (Decimal(str(f.amount or 0)) for f in fees_qs if f.capitalize_to_inventory),
            Decimal('0'),
        )

        # grand_total هو إجمالي الفاتورة قبل بنود fees الإضافية. الرسوم تُضاف فوقه:
        # غير المرسملة → حساب مصروف مستقل، المرسملة → تكلفة المخزون.
        merchandise_net = grand - tax_amt
        inventory_debit = merchandise_net + capitalized_total

        items_with_landed = list(invoice.items.all())
        use_landed = False
        if items_with_landed and any(it.landed_line_total_ils for it in items_with_landed if it.landed_line_total_ils is not None):
            landed_sum = sum(
                (Decimal(str(it.landed_line_total_ils or 0)) for it in items_with_landed),
                Decimal('0'),
            )
            if landed_sum > 0:
                # use_landed يحكم توزيع الأسطر على حساباتها فقط. إجمالي مدين البضاعة
                # يبقى (صافي الفاتورة + الرسوم المرسملة) — وهو المتوازن بالبناء مع
                # دائن الذمم. الاستبدال بـ landed_sum كان يُسقط عمولات تحويل دفعات
                # الصفقة: هي داخلة في grand_total لكنها ليست ضمن landed_line_total_ils،
                # فيفشل الترحيل بفارق يساوي العمولة تماماً.
                use_landed = True

        td = invoice.invoice_date or datetime.date.today()

        # ─── GR/IR: الفاتورة المحلية → قيدان منفصلان عبر الحساب الوسيط ──────────
        # بند البضاعة في قيد الفاتورة يدين «الوسيط» بدل المخزون مباشرةً؛ ويُنشأ
        # قيد استلام مستقل (مدين المخزون / دائن الوسيط) + إدخال المخزون فعلياً.
        # المستورد (صفقة/شحنة/تخليص) يبقى كما هو — مخزونه يأتي عبر الشحنة.
        is_local = not (invoice.deal_id or invoice.shipment_id or invoice.clearance_id)
        gr_ir_account = None
        if is_local:
            from .services import _resolve_gr_ir_account
            try:
                gr_ir_account = _resolve_gr_ir_account(tenant)
            except Exception:
                gr_ir_account = None
        use_gr_ir = bool(is_local and gr_ir_account)
        # إعداد «الاستلام مع الترحيل»: معطّلاً يبقى القيد كما هو (البضاعة في
        # الوسيط) وتُستلَم البنود لاحقاً بكمياتها من نافذة الاستلام.
        from .services import get_or_create_purchase_settings
        receive_on_post = get_or_create_purchase_settings(tenant).receive_on_post

        # ─── 5) بناء أسطر القيد ─────────────────────────────────────────────────
        lines_payload: list[dict] = []

        subtotal = sum((Decimal(str(it.total_price or it.quantity * it.unit_price or 0)) for it in items_with_landed), Decimal('0'))
        discount = Decimal(str(invoice.discount_amount or 0))

        mapped_debit = Decimal('0')
        mapped_lines = {}
        for it in items_with_landed:
            if not it.expense_account_id:
                continue
            if use_landed and it.landed_line_total_ils is not None:
                amt = Decimal(str(it.landed_line_total_ils))
            else:
                raw_amt = Decimal(str(it.total_price or it.quantity * it.unit_price or 0))
                # Distribute discount proportionally
                if subtotal > 0 and discount > 0:
                    amt = raw_amt - (raw_amt / subtotal * discount)
                else:
                    amt = raw_amt
                    
            if amt <= 0: continue
            
            mapped_debit += amt
            if it.expense_account_id not in mapped_lines:
                mapped_lines[it.expense_account_id] = {'amount': Decimal('0'), 'desc': []}
            mapped_lines[it.expense_account_id]['amount'] += amt
            if len(mapped_lines[it.expense_account_id]['desc']) < 3:
                mapped_lines[it.expense_account_id]['desc'].append(it.name or '')
        
        inventory_debit -= mapped_debit
        # تجاوز تكلفة الأسطر لصافي الفاتورة يعني انحرافاً حقيقياً في التوزيع؛ لولا هذا
        # الفحص لسقط سطر المخزون السالب أدناه وظهر «قيد غير متوازن» بلا سبب مفهوم.
        if inventory_debit < Decimal('-0.02'):
            logger.error(
                'purchase invoice %s landed allocation exceeds net: mapped=%s '
                'merchandise_net=%s capitalized=%s residual=%s',
                invoice.pk, mapped_debit, merchandise_net, capitalized_total, inventory_debit,
            )
            return Response(
                {
                    'error': (
                        f'تكلفة أسطر الفاتورة ({mapped_debit.quantize(Decimal("0.01"))} ₪) '
                        f'تتجاوز صافي الفاتورة ({(merchandise_net + capitalized_total).quantize(Decimal("0.01"))} ₪). '
                        'اضغط «إعادة حساب التكلفة» ثم أعد الترحيل؛ إن استمر الفرق '
                        'فراجع دفعات الصفقة وحصص الشحن والتخليص.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if Decimal('-0.02') <= inventory_debit < Decimal('0') and mapped_lines:
            # كسور تقريب: نحسمها من أكبر سطر مُوجَّه حتى يبقى المجموع مطابقاً تماماً.
            biggest = max(mapped_lines, key=lambda k: mapped_lines[k]['amount'])
            mapped_lines[biggest]['amount'] += inventory_debit
            inventory_debit = Decimal('0')

        # المبلغ الذي سيمرّ عبر الوسيط ثم يُرحَّل لقيد الاستلام (للفاتورة المحلية).
        goods_clearing_amt = inventory_debit if inventory_debit > 0 else Decimal('0')

        # توجيه الـsubledger: فقط سطر الحساب الرقابي (ذمم المورد) يَحمل الشريك.
        # سطور المخزون/الوسيط/الضريبة/المصروف ليست ذمماً دائنة على المورد، فلو
        # وُسِمت به لَلوّثت كشف حسابه وألغى مدينُها (المخزون) دائنَ الذمم فظهر
        # رصيده صفراً رغم أن المبلغ مستحق فعلاً (partner_posted_balance بلا فلتر حساب).
        if inventory_debit > 0:
            lines_payload.append({
                'account': (gr_ir_account.id if use_gr_ir else inventory_account.id),
                'debit': inventory_debit.quantize(Decimal('0.01')),
                'credit': Decimal('0'),
                'partner': None,
                'description': (
                    f"وسيط استلام (بضاعة لم تُفوتَر) — {invoice.invoice_number}" if use_gr_ir
                    else f"بضاعة/مخزون — {invoice.invoice_number}"
                ),
            })

        for acc_id, data in mapped_lines.items():
            names = "، ".join(data['desc'])
            if len(data['desc']) == 3: names += "..."
            lines_payload.append({
                'account': acc_id,
                'debit': data['amount'].quantize(Decimal('0.01')),
                'credit': Decimal('0'),
                'partner': None,
                'description': f"بند مشتريات: {names} — {invoice.invoice_number}"[:500],
            })

        if tax_amt > 0:
            lines_payload.append({
                'account': vat_input_account.id,
                'debit': tax_amt.quantize(Decimal('0.01')),
                'credit': Decimal('0'),
                'partner': None,
                'description': f"ضريبة مدخلات — {invoice.invoice_number}",
            })

        for fee in fees_qs:
            amt = Decimal(str(fee.amount or 0))
            if amt <= 0 or fee.capitalize_to_inventory:
                continue
            lines_payload.append({
                'account': fee.expense_account_id,
                'debit': amt.quantize(Decimal('0.01')),
                'credit': Decimal('0'),
                'partner': None,
                'description': f"{fee.description} — {invoice.invoice_number}"[:500],
            })

        credit_total = grand + fees_total

        # سطر الذمم (الحساب الرقابي) هو الوحيد الذي يَحمل المورد — جوهر الـsubledger.
        lines_payload.append({
            'account': credit_account.id,
            'debit': Decimal('0'),
            'credit': credit_total.quantize(Decimal('0.01')),
            'partner': partner.id,
            'description': f"ذمم مورد — {invoice.invoice_number}"[:500],
        })

        # ─── Feature 2 (شراء): ترحيل الفاتورة لا يُسوّي النقدية ─────────────────
        # قيد الفاتورة يدين المخزون/الضريبة ويدائن ذمم المورد بالكامل فقط. الدفع
        # النقدي للمورد — حتى للفاتورة النقدية — يصبح «وصل دفع» مستقل
        # (SupplierPayment، Dr ذمم المورد / Cr صندوق) يُسجَّل من الفاتورة نفسها.

        # ─── 6) الترحيل المركزي ─────────────────────────────────────────────────
        # ذرّي: قيد الفاتورة + (للمحلية) قيد الاستلام عبر الوسيط + إدخال المخزون
        # — كله معاً أو لا شيء، فلا تبقى حالة ناقصة.
        receipt = None
        try:
            with transaction.atomic():
                journal = post_journal(
                    tenant_id=tenant.TenantID,
                    transaction_date=td,
                    reference_type="PURCHASE_INVOICE",
                    reference_id=invoice.pk,
                    description=f"فاتورة شراء {invoice.invoice_number} | {partner.name}"[:500],
                    lines_data=lines_payload,
                    currency=invoice.currency,
                    exchange_rate=invoice.exchange_rate,
                )
                invoice.is_posted = True
                invoice.journal = journal
                invoice.save(update_fields=['is_posted', 'journal'])

                # GR/IR: قيد الاستلام المنفصل + إدخال البضاعة للمستودع الافتراضي
                # (الفاتورة المحلية غير المستلَمة بعد فقط — منعاً للازدواج).
                if (receive_on_post and use_gr_ir and goods_clearing_amt > 0
                        and invoice.receipt_status == PurchaseInvoice.RECEIPT_NOT):
                    receipt = self._post_grn_and_receive(
                        invoice=invoice, tenant=tenant,
                        inventory_account=inventory_account, gr_ir_account=gr_ir_account,
                        goods_clearing_amt=goods_clearing_amt, transaction_date=td,
                        request=request,
                    )

                # T-CASH2 (شراء): الشراء النقدي = مدفوع فوراً ⇒ سوِّه بسند صرف
                # مستقل داخل نفس المعاملة (ذرّياً مع الترحيل) فلا يبقى المورد دائناً.
                self._auto_settle_cash_purchase(
                    invoice, settle_amount=credit_total, request=request,
                )

                # توحيد التكلفة (تذكير task23): بعد الترحيل تدخل الفاتورة نموذج
                # «تكلفة المنتجات» (product_cost_breakdown يقدّم landed cost) —
                # يغطي المحلية (GR/IR) والدولية معاً؛ شركات المتوسط المتحرك
                # تُتخطّى مركزياً داخل apply_purchase_cost_model.
                from inventory.services import apply_purchase_cost_model
                _seen_products = set()
                for it in invoice.items.select_related('product'):
                    if it.product_id and not it.expense_account_id and it.product_id not in _seen_products:
                        _seen_products.add(it.product_id)
                        apply_purchase_cost_model(it.product)
        except (ValidationError, DjangoValidationError, IntegrityError) as e:
            msg = e.message if hasattr(e, 'message') else str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("purchase invoice post_to_accounting failed pk=%s", invoice.pk)
            return Response({'error': 'حدث خطأ غير متوقع أثناء ترحيل فاتورة الشراء.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        log_activity(
            action='post', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number, description='ترحيل فاتورة شراء', request=request,
            partner_ids=[invoice.partner_id],
        )
        return Response({
            'journal_id': journal.id,
            'receipt_journal_id': receipt['journal_id'] if receipt else None,
            'movements_created': receipt['movements'] if receipt else 0,
            'lines_count': len(lines_payload),
            'total_debit': str(sum((l['debit'] for l in lines_payload), Decimal('0'))),
            'total_credit': str(sum((l['credit'] for l in lines_payload), Decimal('0'))),
            'message': 'تم الترحيل بنجاح',
        }, status=status.HTTP_201_CREATED)

    def _post_grn_and_receive(self, *, invoice, tenant, inventory_account, gr_ir_account,
                              goods_clearing_amt, transaction_date, request):
        """GR/IR: يُنشئ قيد الاستلام (مدين المخزون / دائن الوسيط) ويُدخِل البضاعة
        فعلياً للمستودع الافتراضي. يُستدعى داخل معاملة الترحيل الذرّية.

        تكلفة كل بند = حصته من goods_clearing_amt (توزيع تناسبي بقيمة السطر) حتى
        يتطابق رصيد حساب المخزون مع قيمة المخزون الفعلية (WAC سليم).
        """
        from inventory.models import Warehouse
        from inventory.services import record_stock_movement
        from core.tenant_utils import get_branch

        warehouse = (
            Warehouse.objects.filter(tenant=tenant, is_active=True)
            .order_by('-is_default', 'name')
            .first()
        )
        if not warehouse:
            raise DjangoValidationError(
                "لا يوجد مستودع نشط لاستلام البضاعة. أنشئ مستودعاً (أو اجعله الافتراضي) أولاً."
            )

        # البنود القابلة للتخزين = ذات صنف، بلا حساب مصروف صريح، وكمية موجبة.
        # التوزيع نفسه يخدم الاستلام المؤجَّل (goods_clearing_unit_costs) — مصدر واحد.
        from .services import goods_clearing_unit_costs
        goods_lines = [
            it for it in invoice.items.all()
            if it.product_id and not it.expense_account_id
            and Decimal(str(it.quantity or 0)) > 0
        ]
        unit_costs = goods_clearing_unit_costs(invoice, goods_clearing_amt)

        branch = get_branch(request, tenant) if tenant else None
        movements = 0
        movements_by_item = {}
        for it in goods_lines:
            qty = Decimal(str(it.quantity or 0))
            unit_cost = unit_costs.get(it.id, (Decimal('0'), Decimal('0')))[0]
            movements_by_item[it.id] = record_stock_movement(
                product=it.product,
                movement_type='IN',
                quantity=qty,
                unit_cost=unit_cost,
                reference_type='PURCHASE_INVOICE',
                reference_id=invoice.id,
                partner=invoice.partner,
                movement_date=transaction_date,
                notes=f"استلام بترحيل فاتورة {invoice.invoice_number} | {warehouse.name}",
                tenant=tenant,
                branch=branch,
                warehouse=warehouse,
            )
            it.received_quantity = qty
            it.warehouse = warehouse.name
            it.save(update_fields=['received_quantity', 'warehouse'])
            movements += 1

        # نفس قاعدة الاستلام المؤجَّل (`receive_purchase_invoice`): الوحدات
        # المُرقَّمة تُنشأ حين تدخل البضاعة المخزن، من مصدر إلزامٍ واحد.
        from inventory.serials import apply_purchase_serials
        apply_purchase_serials(
            tenant=tenant,
            rows=[(it, Decimal(str(it.quantity or 0))) for it in goods_lines],
        )

        # قيد الاستلام: مدين المخزون / دائن الوسيط (يُصفّر الوسيط مع قيد الفاتورة).
        receipt_journal = post_journal(
            tenant_id=tenant.TenantID,
            transaction_date=transaction_date,
            reference_type="PURCHASE_GRN",
            reference_id=invoice.pk,
            description=f"استلام بضاعة فاتورة {invoice.invoice_number} | {invoice.partner.name}"[:500],
            # قيد الاستلام لا يمسّ ذمم المورد — لا المخزون ولا الوسيط حساب رقابي،
            # فكلاهما بلا شريك حتى لا يتلوّث كشف حساب المورد (partner=None).
            lines_data=[
                {'account': inventory_account.id, 'debit': goods_clearing_amt.quantize(Decimal('0.01')),
                 'credit': Decimal('0'), 'partner': None,
                 'description': f"مخزون مستلَم — {invoice.invoice_number}"[:500]},
                {'account': gr_ir_account.id, 'debit': Decimal('0'),
                 'credit': goods_clearing_amt.quantize(Decimal('0.01')), 'partner': None,
                 'description': f"تصفية وسيط الاستلام — {invoice.invoice_number}"[:500]},
            ],
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate,
        )

        fully = all(
            Decimal(str(it.received_quantity or 0)) >= Decimal(str(it.quantity or 0))
            for it in invoice.items.all() if it.product_id
        )
        invoice.receipt_status = (
            PurchaseInvoice.RECEIPT_FULL if fully else PurchaseInvoice.RECEIPT_PARTIAL
        )
        invoice.save(update_fields=['receipt_status'])

        # إرسالية تلقائية بكامل الكمية — الاستلام مع الترحيل مستند موثّق كغيره.
        from .services import create_goods_receipt_document
        create_goods_receipt_document(
            tenant,
            invoice=invoice,
            lines=[{
                'item': it,
                'product_id': it.product_id,
                'quantity': Decimal(str(it.quantity or 0)),
                'warehouse': warehouse,
                'unit_price': unit_costs.get(it.id, (Decimal('0'), Decimal('0')))[0],
                'movement': movements_by_item.get(it.id),
            } for it in goods_lines],
            branch=branch, user=getattr(request, 'user', None),
            receipt_date=transaction_date, auto_created=True, journal=receipt_journal,
            notes='إرسالية تلقائية مع ترحيل الفاتورة',
        )

        logger.info(
            "purchase post+receive (GR/IR): invoice=%s receipt_journal=%s movements=%d clearing=%s",
            invoice.id, receipt_journal.id, movements, goods_clearing_amt,
        )
        return {'journal_id': receipt_journal.id, 'movements': movements}

    def _auto_settle_cash_purchase(self, invoice, *, settle_amount, request=None):
        """T-CASH2 (شراء): فاتورة الشراء النقدية مدفوعة فوراً — تسوية تلقائية فور
        الترحيل عبر «سند صرف» (SupplierPayment) مستقل بكامل قيمة الفاتورة، فيُفرّغ
        ذمم المورد (Dr ذمم / Cr صندوق) ويحوّله من «دائن» إلى «مسدَّد».

        يُكمل تصميم Feature 2 (شراء): قيد الفاتورة يدائن ذمم المورد بالكامل ولا
        يُسوّي النقدية إطلاقاً. كانت أتمتة التسوية غير مربوطة فبقي الشراء النقدي
        دائناً للأبد — تماماً كما كان البيع النقدي مديناً (مرآة `_auto_settle_cash_sale`).
        لا يلمس قيد الفاتورة فالتسوية قيد منفصل يظهر في كشف حساب المورد.

        يقتصر على فواتير الشراء النقدية (payment_type='cash')؛ إن غاب حساب الصندوق
        يُسجَّل تحذير ويُتخطّى دون كسر الترحيل (يبقى المورد دائناً).
        """
        from sales.services import post_supplier_payment
        if invoice.payment_type != PurchaseInvoice.PAYMENT_TYPE_CASH:
            return
        amount = Decimal(str(settle_amount or 0)).quantize(Decimal('0.01'))
        if amount <= 0:
            return
        cash_account_id = invoice.cash_or_bank_account_id
        if not cash_account_id:
            # T-DEFACC: الصندوق الافتراضي للشركة بدل تخطّي التسوية — نفس مصدر
            # فاتورة البيع وسندَي القبض والصرف.
            from accounting.services import resolve_default_cash_account

            default_cash = resolve_default_cash_account(invoice.tenant_id)
            cash_account_id = default_cash.pk if default_cash else None
        if not cash_account_id:
            logger.warning(
                "Cash purchase %s posted without a cash account — supplier left as "
                "creditor (no auto-settlement). Set the invoice cash/bank account.",
                invoice.invoice_number,
            )
            return
        user = getattr(request, 'user', None)
        user = user if (user is not None and user.is_authenticated) else None
        payment = SupplierPayment.objects.create(
            tenant=invoice.tenant,
            partner=invoice.partner,
            purchase_invoice=invoice,
            payment_date=invoice.invoice_date or datetime.date.today(),
            amount=amount,
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate or Decimal('1'),
            cash_or_bank_account_id=cash_account_id,
            notes=f"صرف نقدي تلقائي — فاتورة شراء {invoice.invoice_number}",
        )
        post_supplier_payment(payment, user=user)
        log_activity(
            action='payment', entity_type='supplier_payment', entity_id=payment.id,
            entity_label=f'#{payment.id}', description='سند صرف نقدي تلقائي',
            partner_ids=[payment.partner_id], request=request,
            tenant=invoice.tenant, user=user,
        )
        log_activity(
            action='post', entity_type='supplier_payment', entity_id=payment.id,
            entity_label=f'#{payment.id}', description='ترحيل سند صرف نقدي تلقائي',
            partner_ids=[payment.partner_id], request=request,
            tenant=invoice.tenant, user=user,
        )
        logger.info(
            "Auto-settled cash purchase %s via supplier payment %s (amount %s).",
            invoice.invoice_number, payment.id, amount,
        )

    def perform_update(self, serializer):
        require_perm(self.request, 'purchase.invoice.edit')
        instance = serializer.instance
        if instance is not None and instance.is_posted:
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        before_header = snapshot_fields(instance, PURCHASE_ACTIVITY_FIELD_LABELS)
        before_items = _purchase_item_snapshot(instance)
        invoice = serializer.save()
        self._sync_attachments(invoice)
        changes = build_activity_changes(
            before=before_header,
            after=snapshot_fields(invoice, PURCHASE_ACTIVITY_FIELD_LABELS),
            labels=PURCHASE_ACTIVITY_FIELD_LABELS,
        ) + build_line_changes(
            before=before_items,
            after=_purchase_item_snapshot(invoice),
            labels=PURCHASE_ACTIVITY_ITEM_LABELS,
        )
        details = describe_activity_changes(changes)
        base = 'تعديل ' + ('مرجع شراء' if invoice.is_return else 'فاتورة شراء')
        logger.info(
            "Purchase invoice %s edited by %s with %s change(s).",
            invoice.invoice_number, getattr(self.request.user, 'username', '—'), len(changes),
        )
        log_activity(
            action='update', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            description=f'{base} — {details}' if details else base,
            metadata={'changes': changes} if changes else None,
            partner_ids=[invoice.partner_id],
            request=self.request,
        )

    def destroy(self, request, *args, **kwargs):
        require_perm(request, 'purchase.invoice.delete')
        instance = self.get_object()
        if instance.is_posted:
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        inv_id, inv_no, is_ret, partner_id = (
            instance.id, instance.invoice_number, instance.is_return, instance.partner_id,
        )
        response = super().destroy(request, *args, **kwargs)
        log_activity(
            action='delete', entity_type='purchase_invoice', entity_id=inv_id,
            entity_label=inv_no,
            description='حذف ' + ('مرجع شراء' if is_ret else 'فاتورة شراء'),
            partner_ids=[partner_id],
            request=request,
        )
        return response

    @action(detail=True, methods=['post'], url_path='unpost')
    @requires_perm('purchase.invoice.unpost')
    def unpost(self, request, pk=None):
        """تراجع عن الترحيل: حذف كل قيود الفاتورة وحركات استلامها وإرجاعها مسودة."""
        invoice = self.get_object()

        # مرجع الشراء: التراجع يحذف قيده العكسي ويعيد الكمية للمخزن (عكس RETURN_OUT).
        if getattr(invoice, 'is_return', False):
            if not invoice.is_posted:
                return Response({'error': 'المرجع غير مرحّل'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                with transaction.atomic():
                    # الكمية تعود للمخزن ⇒ وحداتها المُرقَّمة تعود معها، وإلا بقي
                    # الرصيد يقول شيئاً وكرت الصنف شيئاً آخر.
                    from inventory.serials import restock_returned_purchase_serials
                    restock_returned_purchase_serials(invoice)
                    result = unpost_document(
                        tenant_id=invoice.tenant_id,
                        reference_id=invoice.pk,
                        journal_reference_types=['PURCHASE_RETURN'],
                        stock_reference_types=['PURCHASE_RETURN'],
                        user=request.user,
                        document_label=f"مرجع شراء {invoice.invoice_number}",
                        recycle=True,
                    )
                    invoice.is_posted = False
                    invoice.journal = None
                    invoice.status = 'draft'
                    invoice.save(update_fields=['is_posted', 'journal', 'status'])
            except Exception as e:
                err = '؛ '.join(e.messages) if hasattr(e, 'messages') else str(e)
                return Response({'error': err}, status=status.HTTP_400_BAD_REQUEST)
            log_activity(
                action='unpost', entity_type='purchase_invoice', entity_id=invoice.id,
                entity_label=invoice.invoice_number, description='إلغاء ترحيل مرجع شراء',
                partner_ids=[invoice.partner_id],
                request=request,
            )
            return Response({'message': 'تم التراجع عن ترحيل المرجع وإعادة الكمية للمخزن.', 'unpost_result': result})

        if not invoice.is_posted and invoice.receipt_status == PurchaseInvoice.RECEIPT_NOT:
            return Response(
                {'error': 'الفاتورة غير مرحّلة'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                # الوحدات المُرقَّمة تخرج مع مخزونها: حارس يمنع التراجع إن بِيعت
                # إحداها (بجانب حارس اعتمادية المخزون داخل unpost_document، لا بدلاً
                # منه — ذاك يرى الكميات وهذا يرى الوحدة بعينها).
                from inventory.serials import release_purchase_serials
                release_purchase_serials(
                    tenant_id=invoice.tenant_id,
                    quantities_by_item={
                        it.pk: None for it in invoice.items.all() if it.product_id
                    },
                    document_label=f"ترحيل فاتورة الشراء {invoice.invoice_number}",
                )
                result = unpost_document(
                    tenant_id=invoice.tenant_id,
                    reference_id=invoice.pk,
                    journal_reference_types=['PURCHASE_INVOICE', 'PURCHASE_GRN', 'PURCHASE_RECEIPT'],
                    stock_reference_types=['PURCHASE_INVOICE'],
                    user=request.user,
                    document_label=f"فاتورة شراء {invoice.invoice_number}",
                    recycle=True,
                )
                invoice.is_posted = False
                invoice.journal = None
                invoice.receipt_status = PurchaseInvoice.RECEIPT_NOT
                invoice.save(update_fields=['is_posted', 'journal', 'receipt_status'])
                # إعادة كميات الاستلام للصفر (عُكِست حركات المخزون أعلاه)
                invoice.items.update(received_quantity=0)
                # إرساليات الفاتورة توثّق استلاماً عُكِس ⇒ تُحذف معه (تُنشأ من
                # جديد عند إعادة الترحيل/الاستلام).
                invoice.receipts.all().delete()
                # أعد ضبط avg_cost حسب نموذج التكلفة: الدوري يعيده من المشتريات
                # المتبقية؛ والمتوسط المتحرك يترك ما أعاده _recompute_product_stock.
                from inventory.services import apply_purchase_cost_model
                seen = set()
                for it in invoice.items.select_related('product'):
                    if it.product_id and it.product_id not in seen:
                        seen.add(it.product_id)
                        apply_purchase_cost_model(it.product)
        except Exception as e:
            # ValidationError (حارس الاعتمادية مثلاً) يحمل رسالة نظيفة في .messages.
            err = '؛ '.join(e.messages) if hasattr(e, 'messages') else str(e)
            return Response({'error': err}, status=status.HTTP_400_BAD_REQUEST)

        log_activity(
            action='unpost', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number, description='إلغاء ترحيل فاتورة شراء',
            partner_ids=[invoice.partner_id],
            request=request,
        )
        return Response({'message': 'تم التراجع عن الترحيل وحذف القيود.', 'unpost_result': result})


# ── P-H-3: SupplierPayment ──────────────────────────────────────────

class SupplierPaymentViewSet(BaseTenantViewSet):
    serializer_class = SupplierPaymentSerializer

    def get_queryset(self):
        qs = SupplierPayment.objects.all().select_related(
            'partner', 'purchase_invoice', 'currency', 'cash_or_bank_account', 'journal',
        ).prefetch_related('allocations__invoice').order_by('-created_at')
        tenant = get_tenant(self.request)
        if not tenant:
            return qs.none()
        qs = qs.filter(tenant=tenant)
        # بطاقة المورد تجلب سنداته وحدها (لا كل سندات الشركة).
        partner_id = self.request.query_params.get('partner')
        if partner_id:
            try:
                qs = qs.filter(partner_id=int(partner_id))
            except (TypeError, ValueError):
                pass
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        payment = serializer.save(tenant=tenant)
        from logistics.services import _resolve_ap_account
        try:
            _resolve_ap_account(payment.partner)
        except Exception as e:
            payment.delete()
            from rest_framework.exceptions import ValidationError as DRFValidationError
            raise DRFValidationError(str(e))
        log_activity(
            action='payment', entity_type='supplier_payment', entity_id=payment.id,
            entity_label=f'#{payment.id}', description='سند صرف مورد',
            partner_ids=[payment.partner_id], request=self.request,
        )
        # T-AUTOPOST: سند الصرف يُرحَّل فور الحفظ (لا مسودة) ما لم يُطلب خلاف ذلك —
        # نفس مصدر القرار المشترك مع سند القبض (core.payments).
        from core.payments import should_auto_post_payment
        if should_auto_post_payment(tenant, self.request.data):
            try:
                from sales.services import post_supplier_payment
                post_supplier_payment(payment, user=self.request.user)
                log_activity(
                    action='post', entity_type='supplier_payment', entity_id=payment.id,
                    entity_label=f'#{payment.id}', description='ترحيل سند صرف مورد',
                    partner_ids=[payment.partner_id], request=self.request,
                )
            except Exception as e:  # noqa: BLE001
                # الفشل لا يُضيع السند — يبقى مسودة وتُعاد الرسالة مع الاستجابة.
                logger.warning("Auto-post supplier payment %s failed: %s", payment.id, e)
                payment._auto_post_error = str(e)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        instance = serializer.instance
        headers = self.get_success_headers(serializer.data)
        # T-AUTOPOST: نُعيد الحالة بعد الترحيل التلقائي (is_posted/journal).
        data = SupplierPaymentSerializer(instance).data
        if getattr(instance, '_auto_post_error', None):
            data['auto_post_error'] = instance._auto_post_error
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_update(self, serializer):
        payment = serializer.save()
        log_activity(
            action='update', entity_type='supplier_payment', entity_id=payment.id,
            entity_label=f'#{payment.id}', description='تعديل سند صرف مورد',
            partner_ids=[payment.partner_id], request=self.request,
        )

    def destroy(self, request, *args, **kwargs):
        payment = self.get_object()
        payment_id, partner_id = payment.id, payment.partner_id
        response = super().destroy(request, *args, **kwargs)
        log_activity(
            action='delete', entity_type='supplier_payment', entity_id=payment_id,
            entity_label=f'#{payment_id}', description='حذف سند صرف مورد',
            partner_ids=[partner_id], request=request,
        )
        return response

    @action(detail=True, methods=['post'], url_path='allocate')
    def allocate(self, request, pk=None):
        """T-ONACC: توزيع سند صرف على فواتير شراء — يعمل قبل الترحيل وبعده.

        بعد الترحيل التوزيع ربط فقط (لا قيد جديد): ذمم المورد دُينت وقت الترحيل.
        """
        payment = self.get_object()
        try:
            from sales.services import allocate_supplier_payment
            allocate_supplier_payment(
                payment, request.data.get('allocations') or [], user=request.user,
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        log_activity(
            action='update', entity_type='supplier_payment', entity_id=payment.id,
            entity_label=f'#{payment.id}', description='توزيع سند صرف على الفواتير',
            partner_ids=[payment.partner_id], request=request,
        )
        return Response(SupplierPaymentSerializer(payment).data)

    @action(detail=True, methods=['post'], url_path='post')
    @requires_perm('purchase.payment.post')
    def post_to_accounting(self, request, pk=None):
        payment = self.get_object()
        if payment.is_posted:
            return Response({'error': 'سند الصرف مرحّل مسبقاً.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from sales.services import post_supplier_payment
            post_supplier_payment(payment, user=request.user)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        log_activity(
            action='post', entity_type='supplier_payment', entity_id=payment.id,
            entity_label=f'#{payment.id}', description='ترحيل سند صرف مورد',
            partner_ids=[payment.partner_id], request=request,
        )
        ser = SupplierPaymentSerializer(payment, context={'request': request})
        return Response(ser.data)


class LocalShipmentViewSet(BaseTenantViewSet):
    """الشحن المحلي — مرحلة بين التخليص الجمركي وفاتورة المشتريات.

    الدورة:
      1) pending: طلب الشحن (ناقل، سعر، وجهة)
      2) in_transit: غادر
      3) delivered: تم التسليم → يمكن ترحيله محاسبياً
      4) cancelled: ملغي

    الحسابات:
      - Dr حساب مصروف الشحن (افتراضي 5305) — أو إضافته كبند Landed Cost
      - Cr AP الناقل (ائتمان) أو Cr صندوق/بنك (نقدي)

    إجراءات مخصّصة:
      - POST /{id}/post-to-accounting/  — ترحيل القيد المحاسبي
      - POST /{id}/unpost/               — إلغاء الترحيل
      - POST /{id}/import-to-invoice/    — نقل تكلفته إلى فاتورة مشتريات كرسم
    """

    queryset = LocalShipment.objects.all().select_related(
        'carrier', 'clearance', 'shipment', 'currency',
        'expense_account', 'cash_or_bank_account',
        'journal', 'purchase_invoice',
    ).prefetch_related('payments__journal', 'payments__currency')
    serializer_class = LocalShipmentSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        # فلاتر اختيارية عبر query params
        shipment_id = self.request.query_params.get('shipment')
        clearance_id = self.request.query_params.get('clearance')
        carrier_id = self.request.query_params.get('carrier')
        status_f = self.request.query_params.get('status')
        is_posted = self.request.query_params.get('is_posted')
        if shipment_id:
            qs = qs.filter(shipment_id=shipment_id)
        if clearance_id:
            qs = qs.filter(clearance_id=clearance_id)
        if carrier_id:
            qs = qs.filter(carrier_id=carrier_id)
        if status_f:
            qs = qs.filter(status=status_f)
        if is_posted in ('true', 'false'):
            qs = qs.filter(is_posted=(is_posted == 'true'))
        return qs.order_by('-id')

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        payload = serializer.validated_data
        # إن لم تحدَّد العملة نأخذ الافتراضي (ILS أو أول عملة)
        if 'currency' not in payload or payload.get('currency') is None:
            default_ccy = (
                Currency.objects.filter(Code='ILS').first()
                or Currency.objects.first()
            )
            if default_ccy:
                payload['currency'] = default_ccy
        # ربط تلقائي بالشحنة الدولية عند إعطاء clearance
        clearance = payload.get('clearance')
        if clearance and not payload.get('shipment'):
            payload['shipment'] = clearance.shipment

        # الحساب الافتراضي للمصروف — 5305 (الشحن المحلي)
        if not payload.get('expense_account') and tenant:
            default_exp = (
                Account.objects.filter(tenant=tenant, code='5305', is_active=True).first()
                or Account.objects.filter(tenant=tenant, code='5301', is_active=True).first()
            )
            if default_exp:
                payload['expense_account'] = default_exp

        # تأكّد من ensure partner account
        carrier = payload.get('carrier')
        if carrier:
            try:
                accounting_api.ensure_partner_account(carrier)
            except Exception:
                pass

        serializer.save(tenant=tenant)

    @action(detail=True, methods=['post'], url_path='post-to-accounting')
    def post_to_accounting(self, request, pk=None):
        """ترحيل القيد المحاسبي للشحن المحلي.

        إثبات الاستحقاق دائماً: Dr expense_account / Cr AP الناقل.
        الدفع للناقل إجراء مستقل عبر pay_from_cashbox.

        بعد الترحيل لا يُسمح بالتعديل إلا بعد إلغاء الترحيل.
        """
        shipment = self.get_object()
        try:
            with transaction.atomic():
                journal = post_local_shipment_accrual(shipment, user=request.user)
                if journal is None:
                    return Response(
                        {'error': 'الشحنة مُرحَّلة بالفعل.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        except AccrualSkipped as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(LocalShipmentSerializer(shipment).data)

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        shipment = self.get_object()
        rows = shipment.payments.select_related('journal', 'currency').all()
        return Response(LocalShipmentPaymentSerializer(rows, many=True).data)

    @action(detail=True, methods=['post'])
    def pay_from_cashbox(self, request, pk=None):
        """دفع الناقل: Dr ذمم الناقل / Cr الصندوق، بقيد مستقل عن الاستحقاق."""
        shipment = self.get_object()
        try:
            amount = Decimal(str(request.data.get('amount') or '0')).quantize(Decimal('0.01'))
        except Exception:
            amount = Decimal('0')
        if amount <= 0:
            return Response({'error': 'المبلغ يجب أن يكون أكبر من صفر.'}, status=status.HTTP_400_BAD_REQUEST)
        paid = sum(
            (Decimal(str(p.amount or 0)) for p in shipment.payments.filter(is_posted=True)),
            Decimal('0'),
        )
        from .payment_posting_cap import clearance_broker_posting_cap_check
        clearance_broker_posting_cap_check(
            paid, amount, shipment.amount, label=f"local shipment {shipment.pk} carrier",
        )
        if not shipment.carrier.linked_account_id:
            return Response({'error': 'الناقل غير مربوط بحساب ذمم في المحاسبة.'}, status=status.HTTP_400_BAD_REQUEST)
        external_id = str(request.data.get('cash_box_external_id') or '').strip()
        cash_link = CashBoxLedgerAccount.objects.filter(
            tenant=shipment.tenant, external_id=external_id[:128],
        ).select_related('account').first()
        if not cash_link or not cash_link.account_id:
            return Response({'error': 'اختر صندوقاً مربوطاً بحساب محاسبي.'}, status=status.HTTP_400_BAD_REQUEST)
        raw_date = request.data.get('payment_date')
        try:
            payment_date = datetime.date.fromisoformat(str(raw_date)[:10]) if raw_date else datetime.date.today()
        except (TypeError, ValueError):
            payment_date = datetime.date.today()
        currency = shipment.currency or Currency.objects.filter(Code__iexact='ILS').first()
        exchange_rate = Decimal(str(shipment.exchange_rate or 1))
        try:
            with transaction.atomic():
                payment = LocalShipmentPayment.objects.create(
                    tenant=shipment.tenant,
                    local_shipment=shipment,
                    amount=amount,
                    currency=currency,
                    exchange_rate=exchange_rate,
                    payment_date=payment_date,
                    cash_box_external_id=external_id[:128],
                    notes=str(request.data.get('notes') or '').strip(),
                    created_by=request.user if request.user.is_authenticated else None,
                )
                journal = post_journal(
                    tenant_id=shipment.tenant_id,
                    transaction_date=payment_date,
                    reference_type='LOCAL_SHIPMENT_PAYMENT',
                    reference_id=payment.id,
                    description=f"دفع نقل محلي {shipment.shipment_number} | {shipment.carrier.name}"[:500],
                    lines_data=[
                        {
                            'account': shipment.carrier.linked_account_id,
                            'partner': shipment.carrier_id,
                            'debit': amount,
                            'credit': Decimal('0'),
                            'description': f"دفع للناقل — {shipment.shipment_number}",
                        },
                        {
                            'account': cash_link.account_id,
                            'partner': None,
                            'debit': Decimal('0'),
                            'credit': amount,
                            'description': f"صرف من الصندوق {cash_link.name}",
                        },
                    ],
                    currency=currency,
                    exchange_rate=exchange_rate,
                    user=request.user,
                )
                payment.journal = journal
                payment.is_posted = True
                payment.save(update_fields=['journal', 'is_posted'])
        except Exception as exc:
            logger.exception('local shipment payment failed shipment=%s', shipment.pk)
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        logger.info(
            'local shipment payment posted shipment=%s payment=%s journal=%s amount=%s',
            shipment.pk, payment.pk, journal.pk, amount,
        )
        return Response({
            'status': 'تم تسجيل دفعة الناقل وبقيت في شاشة رحلة الاستيراد.',
            'journal_id': journal.id,
            'payment': LocalShipmentPaymentSerializer(payment).data,
        }, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance is not None and getattr(instance, 'is_posted', False):
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if getattr(instance, 'is_posted', False) or instance.payments.filter(is_posted=True).exists():
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='unpost')
    @requires_perm('inventory.doc.unpost')
    def unpost(self, request, pk=None):
        """تراجع عن الترحيل: حذف قيد الشحن المحلي وإرجاعه مسودة."""
        shipment = self.get_object()
        if not shipment.is_posted:
            return Response(
                {'error': 'الشحنة غير مُرحّلة.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                result = unpost_document(
                    tenant_id=shipment.tenant_id,
                    reference_id=shipment.pk,
                    journal_reference_types=['LOCAL_SHIPMENT'],
                    user=request.user,
                    document_label=f"شحن محلي {shipment.shipment_number}",
                )
                shipment.is_posted = False
                shipment.journal = None
                shipment.save(update_fields=['is_posted', 'journal'])
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'تم التراجع عن الترحيل وحذف القيد.', 'unpost_result': result})

    @action(detail=True, methods=['post'], url_path='import-to-invoice')
    def import_to_invoice(self, request, pk=None):
        """معطَّل: تكلفة الناقل تُثبَّت باستحقاق مستقل لا كرسم على الفاتورة.

        كان هذا المسار ينشئ PurchaseInvoiceFee بمبلغ الشحنة، لكن قيد الفاتورة
        يُدائن **مورد الفاتورة** بمجموع الرسوم (credit_total = grand + fees_total)
        بينما الرسم لا يحمل دائناً خاصاً به — فذمّة الناقل لا تُدائن أبداً، ثم
        تأتي دفعته مديناً وحدها فيظهر الناقل مديناً لنا بدل أن نكون مدينين له.

        القاعدة الآن (قرار المالك): الاستحقاق مستقل عبر post-to-accounting
        (Dr مصروف النقل / Cr ذمم الناقل) والدفع مستقل عنه. الرسملة على تكلفة
        المخزون لا تتأثر: landed_cost يقرأ LocalShipment مباشرةً لا عبر رسوم
        الفاتورة.
        """
        return Response(
            {
                'error': (
                    'نقل تكلفة الناقل إلى الفاتورة معطَّل — كان يُدائن مورد الفاتورة '
                    'بدل الناقل فتبقى ذمّته بلا استحقاق. استخدم «إثبات الاستحقاق» '
                    'على سطر النقل المحلي: يدائن الناقل، والدفع يبقى إجراءً مستقلاً. '
                    'التكلفة تُرسمل على المخزون كما هي بلا هذا النقل.'
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


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

        qs = qs.select_related('shipping_agent').prefetch_related(
            'clearance',
            'clearance__payments',
            'deals',
        ).order_by('-arrival_date', '-id')

        out = []
        for sh in qs[:200]:  # safety limit
            out.append(_build_landed_cost_summary(sh, detailed=bool(shipment_id)))

        return Response({
            'shipments': out,
            'count': len(out),
            'summary_only': not bool(shipment_id),
        })


def _build_landed_cost_summary(shipment, *, detailed=False):
    """يبني ملخّص Landed Cost لشحنة واحدة."""
    from decimal import Decimal

    tenant = shipment.tenant

    # الصفقات المرتبطة
    links = LogisticsShipmentDeal.objects.filter(shipment=shipment).select_related(
        'deal', 'deal__partner', 'deal__currency',
    )

    deals_data = []
    total_merchandise = Decimal('0')
    total_allocated_shipping = Decimal('0')

    for link in links:
        deal = link.deal
        items = deal.items.select_related('product').filter(is_deleted=False) if hasattr(deal, 'items') else []
        deal_merch = sum(
            (Decimal(str(i.quantity or 0)) * Decimal(str(i.unit_price or 0)) for i in items),
            Decimal('0'),
        )
        total_merchandise += deal_merch
        total_allocated_shipping += Decimal(str(link.allocated_shipping_cost or 0))

        # فاتورة الشراء المرتبطة بهذه الصفقة + الشحنة
        pi = PurchaseInvoice.objects.filter(
            tenant=tenant, shipment=shipment, deal=deal,
        ).prefetch_related('items', 'fees', 'fees__expense_account').first()

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


class GoodsReceiptViewSet(BaseTenantViewSet):
    """إرساليات الشراء — مستند استلام البضاعة المرتبط بفاتورة.

    الإنشاء **هو** فعل الاستلام: يمرّ عبر `receive_purchase_invoice` نفسه الذي
    يستدعيه زر «استلام» داخل الفاتورة، فلا يوجد مساران لاستلام البضاعة.
    التعديل والحذف ممنوعان — تصحيح الاستلام يكون بالتراجع عن ترحيل الفاتورة.
    """

    serializer_class = GoodsReceiptSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        from logistics.models import GoodsReceipt
        tenant = get_tenant(self.request)
        if not tenant:
            return GoodsReceipt.objects.none()
        qs = (
            GoodsReceipt.objects.filter(tenant=tenant)
            .select_related('invoice', 'invoice__partner', 'partner', 'journal')
            .prefetch_related('lines__item', 'lines__product', 'lines__warehouse')
        )
        invoice_id = self.request.query_params.get('invoice')
        if invoice_id:
            qs = qs.filter(invoice_id=invoice_id)
        kind = self.request.query_params.get('kind')
        if kind == 'linked':
            qs = qs.filter(invoice__isnull=False)
        elif kind == 'standalone':
            qs = qs.filter(invoice__isnull=True)
        search = (self.request.query_params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(receipt_number__icontains=search)
                | Q(supplier_ref__icontains=search)
                | Q(invoice__invoice_number__icontains=search)
                | Q(invoice__partner__name__icontains=search)
                | Q(partner__name__icontains=search)
            )
        return qs.order_by('-receipt_date', '-id')

    def get_serializer_class(self):
        if self.action == 'list':
            return GoodsReceiptListSerializer
        return GoodsReceiptSerializer

    def _apply(self, request, *, existing=None):
        """المسار الموحّد للإنشاء والتعديل — الاستلام فعل واحد مهما كان مدخله.

        Body: { "invoice": int|null, "partner": int, "supplier_ref": str,
                "receipt_date": "YYYY-MM-DD", "notes": str,
                "lines": [ { "item_id"?, "product_id"?, "quantity", "unit_price"?,
                             "warehouse_id" } ] }
        بلا `invoice` ⇒ «سند استلام» مستقل (يتطلب `partner` وسعر وحدة لكل بند).
        """
        from core.tenant_utils import get_branch
        from partners.models import Partner
        from .models import PurchaseInvoice
        from .services import (
            create_standalone_goods_receipt, get_or_create_purchase_settings,
            receive_purchase_invoice, void_goods_receipt,
        )

        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد شركة (tenant).'}, status=status.HTTP_400_BAD_REQUEST)
        settings_obj = get_or_create_purchase_settings(tenant)
        lines = request.data.get('lines') or []
        if not isinstance(lines, list):
            return Response({'error': 'lines يجب أن تكون قائمة'}, status=status.HTTP_400_BAD_REQUEST)

        invoice_id = request.data.get('invoice') or None
        invoice = None
        if invoice_id:
            invoice = PurchaseInvoice.objects.filter(pk=invoice_id, tenant=tenant).first()
            if not invoice:
                return Response(
                    {'error': 'الفاتورة المرتبطة غير موجودة.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif not settings_obj.allow_standalone_receipt:
            return Response(
                {'error': 'اختر الفاتورة المرتبطة — سند الاستلام المستقل معطّل من إعدادات الشراء.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        partner = None
        if request.data.get('partner'):
            partner = Partner.objects.filter(
                pk=request.data.get('partner'), tenant=tenant,
            ).first()
            if partner is None:
                return Response({'error': 'المورد غير موجود.'}, status=status.HTTP_400_BAD_REQUEST)

        branch = get_branch(request, tenant) if tenant else None
        receipt_date = request.data.get('receipt_date') or None
        notes = str(request.data.get('notes') or '')[:500]
        supplier_ref = str(request.data.get('supplier_ref') or '')[:100]

        try:
            with transaction.atomic():
                # التعديل = عكس أثر الإرسالية القديمة ثم تطبيق الجديد ذرّياً،
                # فلا تبقى كمية مزدوجة ولا قيد يتيم عند فشل نصف العملية.
                if existing is not None:
                    void_goods_receipt(existing, user=request.user)
                if invoice is not None:
                    result = receive_purchase_invoice(
                        invoice, lines=lines, branch=branch, user=request.user,
                        receipt_date=receipt_date, notes=notes, supplier_ref=supplier_ref,
                    )
                    receipt = result.get('receipt')
                else:
                    result = create_standalone_goods_receipt(
                        tenant, partner=partner, lines=lines, branch=branch,
                        user=request.user, receipt_date=receipt_date, notes=notes,
                        supplier_ref=supplier_ref,
                    )
                    receipt = result.get('receipt')
        except DjangoValidationError as ve:
            msg = ve.message if hasattr(ve, 'message') else (
                ve.messages[0] if getattr(ve, 'messages', None) else str(ve))
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as ve:
            return Response(
                {'error': ve.detail if hasattr(ve, 'detail') else str(ve)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('goods receipt save failed')
            return Response(
                {'error': 'حدث خطأ غير متوقع أثناء حفظ الإرسالية.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if receipt is None:
            return Response(
                {'error': 'لم تُنشأ إرسالية — تحقق من الكميات.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        log_activity(
            action='update' if existing is not None else 'create',
            entity_type='goods_receipt', entity_id=receipt.id,
            entity_label=receipt.receipt_number,
            description='تعديل إرسالية شراء' if existing is not None else 'إنشاء إرسالية شراء',
            partner_ids=[receipt.partner_id] if receipt.partner_id else [],
            request=request,
        )
        return Response(
            GoodsReceiptSerializer(receipt).data,
            status=status.HTTP_200_OK if existing is not None else status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'], url_path='outstanding')
    def outstanding(self, request):
        """البواقي غير المستلمة عبر كل فواتير الشراء المرحّلة — تقرير قابل للطباعة.

        مصدر واحد للشاشة وللطباعة/PDF، فلا يُحتسب الباقي مرتين بطريقتين.
        """
        from .models import PurchaseInvoice

        tenant = get_tenant(request)
        if not tenant:
            return Response({'rows': []})
        invoices = (
            PurchaseInvoice.objects.filter(
                tenant=tenant, is_posted=True, is_return=False,
                deal__isnull=True, shipment__isnull=True, clearance__isnull=True,
            )
            .exclude(receipt_status=PurchaseInvoice.RECEIPT_FULL)
            .select_related('partner')
            .prefetch_related('items__product')
        )
        rows = []
        for inv in invoices:
            for it in inv.items.all():
                if not it.product_id:
                    continue
                ordered = Decimal(str(it.quantity or 0))
                received = Decimal(str(it.received_quantity or 0))
                remaining = ordered - received
                if remaining <= 0:
                    continue
                rows.append({
                    'invoice': inv.id,
                    'invoice_number': inv.invoice_number,
                    'invoice_date': inv.invoice_date,
                    'partner_name': inv.partner.name if inv.partner_id else '',
                    'product': it.product_id,
                    'product_name': str(it.product),
                    'quantity': str(ordered),
                    'received_quantity': str(received),
                    'remaining_quantity': str(remaining),
                })
        return Response({'count': len(rows), 'rows': rows})

    def create(self, request, *args, **kwargs):
        return self._apply(request)

    def update(self, request, *args, **kwargs):
        """تعديل الإرسالية: عكس أثرها القديم وإعادة تطبيق البنود الجديدة."""
        from .services import get_or_create_purchase_settings

        receipt = self.get_object()
        tenant = get_tenant(request)
        if not get_or_create_purchase_settings(tenant).allow_edit_receipt:
            return Response(
                {'error': 'تعديل الإرسالية معطّل من إعدادات الشراء.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return self._apply(request, existing=receipt)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """إلغاء الإرسالية = عكس حركاتها وقيدها وكمياتها المستلمة."""
        from .services import get_or_create_purchase_settings, void_goods_receipt

        receipt = self.get_object()
        tenant = get_tenant(request)
        if not get_or_create_purchase_settings(tenant).allow_edit_receipt:
            return Response(
                {'error': 'حذف الإرسالية معطّل من إعدادات الشراء.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        number, partner_id = receipt.receipt_number, receipt.partner_id
        try:
            result = void_goods_receipt(receipt, user=request.user)
        except (DjangoValidationError, ValidationError) as ve:
            msg = getattr(ve, 'message', None) or (
                ve.messages[0] if getattr(ve, 'messages', None) else str(ve))
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        log_activity(
            action='delete', entity_type='goods_receipt', entity_id=0,
            entity_label=number, description='إلغاء إرسالية شراء',
            partner_ids=[partner_id] if partner_id else [], request=request,
        )
        return Response({'message': 'تم إلغاء الإرسالية وعكس أثرها.', **result})


class PurchaseSettingsViewSet(BaseTenantViewSet):
    """FEAT-1: نقطة واحدة (GET/PUT/PATCH) لإعدادات الشراء للشركة.

    مرآة SalesSettingsViewSet — استراتيجية التسعير التلقائي لبنود فاتورة الشراء.
    """

    serializer_class = PurchaseSettingsSerializer

    def get_queryset(self):
        from logistics.models import PurchaseSettings
        tenant = get_tenant(self.request)
        if not tenant:
            return PurchaseSettings.objects.none()
        return PurchaseSettings.objects.filter(tenant=tenant)

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='current')
    def current(self, request):
        from logistics.services import get_or_create_purchase_settings
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد شركة (tenant).'}, status=status.HTTP_400_BAD_REQUEST)
        ps = get_or_create_purchase_settings(tenant)
        if request.method == 'GET':
            return Response(PurchaseSettingsSerializer(ps).data)
        require_perm(request, 'purchase.settings.manage', tenant=tenant)
        ser = PurchaseSettingsSerializer(ps, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
