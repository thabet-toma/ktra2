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
from django.utils import timezone
from django.utils.dateparse import parse_date
from logistics.models import (
    SupplierQuotation,
    PurchaseRFQ,
    PurchaseRFQLine,
    PurchaseRFQRecipient,
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
    PurchaseRFQSerializer,
    PurchaseRFQRecipientSerializer,
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
from accounting.services import resolve_cash_account
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
    convert_local_quotation_to_invoice,
    convert_local_quotation_to_order,
    convert_purchase_order_to_invoice,
    confirm_purchase_order,
)

logger = logging.getLogger("logistics.views")



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

    # T113-1: «تحويل إلى صفقة» بضغطة حُذف. الصفقة تُنشأ من `POST /api/logistics/deals/`
    # ومعها `source_quotation`، فتطالب بالعرض وتقلبه «محوَّلاً» في المعاملة نفسها
    # (`logistics/views/deals.py` — `LogisticsDealViewSet._save_deal_claiming_quotation`).
    # لا سجل يُخلق قبل ضغطة «حفظ» في المحرّر.

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


# ── ISSUE #112 — الطلبية (طلب عروض أسعار): الأبّ الذي يسبق `SupplierQuotation`

class PurchaseRFQViewSet(BaseTenantViewSet):
    serializer_class = PurchaseRFQSerializer
    queryset = PurchaseRFQ.objects.all()

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related('tenant', 'created_by')
            .prefetch_related(
                'lines__product', 'recipients__supplier', 'recipients__quotation',
            )
        )
        scope = str(self.request.query_params.get('scope') or '').strip()
        rfq_status = str(self.request.query_params.get('status') or '').strip()
        search = str(self.request.query_params.get('search') or '').strip()
        if scope:
            qs = qs.filter(scope=scope)
        if rfq_status:
            qs = qs.filter(status=rfq_status)
        if search:
            qs = qs.filter(
                Q(rfq_number__icontains=search)
                | Q(notes__icontains=search)
                | Q(lines__name_snapshot__icontains=search)
                | Q(lines__product__name_ar__icontains=search)
                | Q(lines__product__name_en__icontains=search)
            ).distinct()
        return qs.order_by('-rfq_date', '-id')

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        kwargs = {'tenant': tenant}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user
        rfq = serializer.save(**kwargs)
        log_activity(
            action='create',
            entity_type='purchase_rfq',
            entity_id=rfq.id,
            entity_label=rfq.rfq_number or f'RFQ-draft-{rfq.id}',
            description='إنشاء طلبية (طلب عروض أسعار)',
            request=self.request,
        )

    def perform_destroy(self, instance):
        if instance.status != PurchaseRFQ.STATUS_DRAFT:
            raise ValidationError('يمكن حذف الطلبية وهي مسودة فقط.')
        super().perform_destroy(instance)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """أوّل إرسال: يقفل البنود، يخصّص الرقم إن لم يكن مخصّصاً، ويحوّل الحالة.

        `supplier_ids` اختياري في جسم الطلب — قائمة موردين يُضافون مستقبِلين
        قبل الإرسال (بديل «إضافة مستقبِل» المنفصلة لمن يعرف موردّيه سلفاً).
        """
        tenant = get_tenant(request)
        with transaction.atomic():
            rfq = PurchaseRFQ.objects.select_for_update().get(
                pk=self.get_object().pk, tenant=tenant,
            )
            if rfq.status != PurchaseRFQ.STATUS_DRAFT:
                raise ValidationError('لا يمكن إرسال طلبية ليست مسودة.')
            if not rfq.lines.exists():
                raise ValidationError('أضف بنداً واحداً على الأقل قبل الإرسال.')

            supplier_ids = request.data.get('supplier_ids') or []
            if not isinstance(supplier_ids, list):
                raise ValidationError({'supplier_ids': 'يجب أن تكون قائمة معرّفات موردين.'})
            for supplier_id in supplier_ids:
                supplier = Partner.objects.filter(
                    pk=supplier_id, tenant=tenant, partner_type='Supplier',
                ).first()
                if supplier is None:
                    raise ValidationError({
                        'supplier_ids': f'المورد {supplier_id} غير موجود أو لا يتبع الشركة الحالية.',
                    })
                PurchaseRFQRecipient.objects.get_or_create(
                    tenant=tenant, rfq=rfq, supplier=supplier,
                )

            now = timezone.now()
            rfq.recipients.filter(sent_at__isnull=True).update(sent_at=now)

            # ISSUE #112 §الترقيم: يُخصَّص هنا فقط — أوّل إرسال، لا عند الإنشاء.
            # `if not rfq.rfq_number` يجعل الفعل idempotent: إعادة استدعائه
            # (لن يحدث فعلياً بعد أن صارت الحالة sent أعلاه) لن يحرق رقماً ثانياً.
            if not rfq.rfq_number:
                sequence = next_document_number(tenant.pk, 'purchase_rfq')
                rfq.rfq_number = f'RFQ-{sequence:04d}'
            rfq.status = PurchaseRFQ.STATUS_SENT
            rfq.save(update_fields=['rfq_number', 'status', 'updated_at'])

        log_activity(
            action='update',
            entity_type='purchase_rfq',
            entity_id=rfq.id,
            entity_label=rfq.rfq_number,
            description='إرسال الطلبية للموردين',
            request=request,
        )
        return Response(PurchaseRFQSerializer(rfq, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        tenant = get_tenant(request)
        with transaction.atomic():
            rfq = PurchaseRFQ.objects.select_for_update().get(
                pk=self.get_object().pk, tenant=tenant,
            )
            if rfq.status not in (PurchaseRFQ.STATUS_DRAFT, PurchaseRFQ.STATUS_SENT):
                raise ValidationError('لا يمكن إلغاء طلبية مُرساة أو ملغاة أصلاً.')
            rfq.status = PurchaseRFQ.STATUS_CANCELLED
            rfq.save(update_fields=['status', 'updated_at'])

        log_activity(
            action='update',
            entity_type='purchase_rfq',
            entity_id=rfq.id,
            entity_label=rfq.rfq_number or f'RFQ-draft-{rfq.id}',
            description='إلغاء الطلبية',
            request=request,
        )
        return Response(PurchaseRFQSerializer(rfq, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def award(self, request, pk=None):
        tenant = get_tenant(request)
        with transaction.atomic():
            rfq = PurchaseRFQ.objects.select_for_update().get(
                pk=self.get_object().pk, tenant=tenant,
            )
            if rfq.status != PurchaseRFQ.STATUS_SENT:
                raise ValidationError('يمكن ترسية الطلبيات المُرسَلة فقط.')
            rfq.status = PurchaseRFQ.STATUS_AWARDED
            rfq.save(update_fields=['status', 'updated_at'])

        log_activity(
            action='update',
            entity_type='purchase_rfq',
            entity_id=rfq.id,
            entity_label=rfq.rfq_number,
            description='ترسية الطلبية',
            request=request,
        )
        return Response(PurchaseRFQSerializer(rfq, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='recipients')
    def add_recipient(self, request, pk=None):
        """المسموح بعد الإرسال (#108 §٧): إضافة مستقبِل — لا يمسّ البنود ولا الحالة."""
        tenant = get_tenant(request)
        rfq = self.get_object()
        if rfq.status in (PurchaseRFQ.STATUS_CANCELLED, PurchaseRFQ.STATUS_AWARDED):
            raise ValidationError('لا يمكن إضافة مستقبِل لطلبية ملغاة أو مُرساة.')
        supplier_id = request.data.get('supplier')
        if not supplier_id:
            raise ValidationError({'supplier': 'اختر مورداً.'})
        supplier = Partner.objects.filter(
            pk=supplier_id, tenant=tenant, partner_type='Supplier',
        ).first()
        if supplier is None:
            raise ValidationError({'supplier': 'المورد غير موجود أو لا يتبع الشركة الحالية.'})
        recipient, created = PurchaseRFQRecipient.objects.get_or_create(
            tenant=tenant, rfq=rfq, supplier=supplier,
            defaults={
                'sent_at': timezone.now() if rfq.status == PurchaseRFQ.STATUS_SENT else None,
            },
        )
        if created:
            log_activity(
                action='update',
                entity_type='purchase_rfq',
                entity_id=rfq.id,
                entity_label=rfq.rfq_number or f'RFQ-draft-{rfq.id}',
                description=f'إضافة مستقبِل: {supplier.name}',
                request=request,
                partner_ids=[supplier.pk],
            )
        return Response(
            PurchaseRFQRecipientSerializer(recipient).data,
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
            # `invoice__items`: تقدّم استلام الفاتورة يُقرأ لكل طلبية (T-RECVIS)،
            # وبلا الجلب المسبق يصير استعلاماً لكل صفّ في القائمة.
            .prefetch_related('lines__product', 'invoice__items')
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
        from logistics.services import get_or_create_purchase_settings

        tenant = get_tenant(self.request)
        # ISSUE #117: المفتاح يحكم الإنشاء لا الرؤية — أمرٌ قائم يبقى مقروءاً
        # ومفتوحاً حتى بعد إطفاء الإعداد؛ الإنشاء وحده يُرفض.
        settings_obj = get_or_create_purchase_settings(tenant)
        if not settings_obj.use_purchase_orders:
            raise ValidationError(
                'خطوة أمر الشراء معطّلة من إعدادات الشراء — التسلسل الافتراضي طلبية ← عروض ← فاتورة.'
            )
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
        # القاعدة في `logistics/services.py` (`confirm_purchase_order`) لا هنا:
        # المورّد صار يقدر أن يقبل الطلبية من رابط المشاركة العام، ونسخُ الشروط
        # في موضعين يعني قاعدتين تنحرفان عند أول تعديل.
        order = confirm_purchase_order(
            PurchaseOrder.objects.get(
                pk=self.get_object().pk, tenant=get_tenant(request),
            )
        )
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


