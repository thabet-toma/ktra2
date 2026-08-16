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
from core.pagination import EnforcedPageNumberPagination
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



class SupplierPaymentViewSet(BaseTenantViewSet):
    # P0-5: ترقيم إلزامي — الشاشة الرئيسية أحدث 200، والمفلتر بمورد بسقف صريح.
    pagination_class = EnforcedPageNumberPagination
    serializer_class = SupplierPaymentSerializer

    def get_queryset(self):
        qs = SupplierPayment.objects.all().select_related(
            'partner', 'purchase_invoice', 'currency', 'cash_or_bank_account', 'journal',
        ).prefetch_related('allocations__invoice').order_by('-created_at', '-id')
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
        # T-ARINT (مرآة المورد): حذف سند مرحّل كان يترك قيوده (مدين ذمم المورد)
        # يتيمة وفواتيره «مدفوعة» بلا صرف. الحذف الآن يتراجع عن الترحيل أولاً —
        # نفس عقد نظيره في sales/views.py (CustomerPayment.destroy).
        if payment.is_posted:
            require_perm(request, 'purchase.payment.unpost')
            try:
                from sales.services import unpost_supplier_payment
                unpost_supplier_payment(payment, user=request.user)
            except DjangoValidationError as e:
                return Response(
                    {'error': '؛ '.join(e.messages)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
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

    @action(detail=True, methods=['post'], url_path='unpost')
    @requires_perm('purchase.payment.unpost')
    def unpost_from_accounting(self, request, pk=None):
        """التراجع عن ترحيل سند صرف: حذف قيوده وإعادة شيكاته إلى مسودة.

        «المدفوع» على فواتير الشراء مشتق من التوزيعات المرحّلة، فتعود الفواتير
        «غير مسدَّدة» تلقائياً — مرآة `/api/sales/payments/{id}/unpost/`.
        """
        payment = self.get_object()
        try:
            from sales.services import unpost_supplier_payment
            result = unpost_supplier_payment(payment, user=request.user)
        except DjangoValidationError as e:
            return Response(
                {'error': '؛ '.join(e.messages)}, status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:  # noqa: BLE001
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        payment.refresh_from_db()
        log_activity(
            action='unpost', entity_type='supplier_payment', entity_id=payment.id,
            entity_label=f'#{payment.id}', description='التراجع عن ترحيل سند صرف مورد',
            partner_ids=[payment.partner_id], request=request,
        )
        ser = SupplierPaymentSerializer(payment, context={'request': request})
        return Response({**ser.data, 'unpost_result': result})


