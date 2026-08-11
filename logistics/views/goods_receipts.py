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
    convert_import_quotation_to_deal,
    convert_purchase_order_to_invoice,
)

logger = logging.getLogger("logistics.views")



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
        from logistics.models import PurchaseInvoice
        from logistics.services import (
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
        from logistics.models import PurchaseInvoice

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
        from logistics.services import get_or_create_purchase_settings

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
        from logistics.services import get_or_create_purchase_settings, void_goods_receipt

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


