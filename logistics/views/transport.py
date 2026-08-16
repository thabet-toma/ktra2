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
from django.utils import timezone

logger = logging.getLogger("logistics.views")



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
        from logistics.payment_posting_cap import clearance_broker_posting_cap_check
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
            payment_date = datetime.date.fromisoformat(str(raw_date)[:10]) if raw_date else timezone.localdate()
        except (TypeError, ValueError):
            payment_date = timezone.localdate()
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


