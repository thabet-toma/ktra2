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
from accounting.models import Cheque, JournalHeader, JournalLine, CashBoxLedgerAccount
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
    build_document_snapshot_changes,
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
    attach_purchase_payment_voucher,
    convert_local_quotation_to_invoice,
    convert_local_quotation_to_order,
    convert_purchase_order_to_invoice,
    guard_purchase_invoice_payments_before_unpost,
    release_auto_cash_purchase_settlement,
    settle_attached_purchase_intent,
)
from django.utils import timezone

logger = logging.getLogger("logistics.views")



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
    # P0-5: ترقيم إلزامي — الشاشة الرئيسية مُرقَّمة أصلاً (listPage)، وبقية
    # المستهلكين صاروا بسقف 200 صريح (منتقيات ومحرّرات).
    pagination_class = EnforcedPageNumberPagination
    serializer_class = PurchaseInvoiceSerializer
    partner_balance_spec = ("partner_id", True, "supplier_balance")

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseInvoiceListSerializer
        return PurchaseInvoiceSerializer

    def get_queryset(self):
        qs = PurchaseInvoice.objects.all().select_related(
            'partner', 'deal', 'shipment', 'clearance', 'currency', 'journal',
        ).order_by('-created_at', '-id')
        # كما في الصفقات: الرصيد للقائمة يأتي من الـmixin بعد الترقيم.
        if self.action != 'list':
            qs = annotate_partner_posted_balance(
                qs, "partner_id", supplier=True, alias="supplier_balance",
            )
        if self.action == 'list':
            # عدّ البنود باستعلام فرعي لا بـ`Count('items')`: التجميعة تفرض
            # GROUP BY فيمنع جانغو من تقليم التعليقات في استعلام COUNT الخاص
            # بالترقيم، فتُنفَّذ استعلامات ملخّص الدفع الفرعية لكل صفّ — 14 ثانية
            # للعدّ وحده على مستأجرٍ بألف فاتورة، وقطعُ اتصال MySQL عند المهلة.
            # نفس نمط `deals_count`/`payments_count` في قائمة الشحنات.
            items_summary = (
                PurchaseInvoiceItem.objects
                .filter(invoice_id=OuterRef('pk'))
                .values('invoice_id')
                .annotate(row_count=Count('id'))
            )
            qs = qs.annotate(
                items_count=Coalesce(
                    Subquery(
                        items_summary.values('row_count')[:1],
                        output_field=IntegerField(),
                    ),
                    # فاتورة بلا بنود: الاستعلام الفرعي يُرجع NULL بينما
                    # `Count` كانت تُرجع 0 — والسيريالايزر يعرضه رقماً.
                    Value(0),
                ),
            )
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
        elif self.action == 'list' and payment_status == 'overdue':
            # T-DUE: «متأخرة» ليست قيمةً في `payment_status` بل بُعدٌ فوقه —
            # عليها متبقٍّ **و**استحقاقها مضى. بلا تاريخ استحقاق لا تأخّر.
            from django.utils import timezone
            qs = qs.filter(
                due_date__isnull=False,
                due_date__lt=timezone.localdate(),
                list_remaining_balance__gt=0,
            )
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
        # الإنشاء يُسجَّل بمحتواه كاملاً — مرآة فاتورة البيع (sales/views.py).
        changes = build_document_snapshot_changes(
            header=snapshot_fields(invoice, PURCHASE_ACTIVITY_FIELD_LABELS),
            lines=_purchase_item_snapshot(invoice),
            labels=PURCHASE_ACTIVITY_FIELD_LABELS,
            line_labels=PURCHASE_ACTIVITY_ITEM_LABELS,
        )
        details = describe_activity_changes(changes)
        base = 'إنشاء ' + ('مرجع شراء' if invoice.is_return else 'فاتورة شراء')
        log_activity(
            action='create', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number,
            description=f'{base} — {details}' if details else base,
            metadata={'changes': changes} if changes else None,
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
        """FEAT-1: سعر الوحدة المقترح لمنتج حسب استراتيجية إعدادات الشراء.

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
        منتقي المنتجات في الفاتورة بلا نقر. يفوّض لـ core.pricing (المصدر المشترك).
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
        from logistics.services import purchase_item_receipt_quantities
        from inventory.services import product_display_name

        invoice = self.get_object()
        rows = []
        for it in invoice.items.select_related('product').all():
            if not it.product_id:
                continue
            ordered, received, remaining = purchase_item_receipt_quantities(it)
            rows.append({
                'item_id': it.id,
                'product': it.product_id,
                'product_name': product_display_name(it.product),
                'name': it.name,
                'unit_price': str(it.unit_price or 0),
                'quantity': str(ordered),
                'received_quantity': str(received),
                'remaining_quantity': str(remaining),
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
        from logistics.services import receive_purchase_invoice

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
        from logistics.services import create_purchase_return

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
        from logistics.services import returnable_lines_for_invoice

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
    @requires_perm('purchase.payment.create')
    def payment_voucher(self, request, pk=None):
        """غلافٌ قديم فوق `pay/` — يُبقي شكل الطلب السابق (`cash_amount`) عاملاً.

        **ما كان يفعله سابقاً**: يكتب `attached_cash_amount` على الفاتورة وينشئ
        شيكات `Draft`، ولا يقرأ الترحيلُ أياً منهما — أي مالٌ يُسجَّل في الشاشة بلا
        أثرٍ في الدفاتر، ثم يظهر «مدفوعاً» في الملخّص (حتى أُصلح ذلك في T-APPAID).
        مستندٌ ماليّ الشكل عديمُ الأثر أسوأ من غيابه. الآن يمرّ من المنسّق نفسه
        (`pay_purchase_invoice`) فيخرج سند صرف حقيقيّ مرحّل — تماماً كما صار
        `payment-voucher` في البيع غلافاً فوق `collect`.
        """
        # `request.data` غير قابل للتعديل في DRF، فنُمرّر الحمولة المترجَمة عبر
        # سمةٍ يقرأها `pay` — بلا نسخ أيّ منطق دفعٍ ثانٍ.
        request._appay_payload = {
            'cash': request.data.get('cash_amount', 0),
            'cash_account_id': request.data.get('cash_account_id'),
            'cheques': request.data.get('cheques') or [],
            'post_invoice': True,
        }
        return self.pay(request, pk=pk)

    @action(detail=True, methods=['post'], url_path='attach-payment')
    @requires_perm('purchase.payment.create')
    def attach_payment(self, request, pk=None):
        """T-INTENT: يربط نيّة دفع بمسودة فاتورة الشراء — بلا ترحيل ولا سند.

        Body: `{"cash_amount": "100", "cash_account_id": 12, "cheques": [...]}`
        بدلالة الاستبدال: كل نداء يحلّ محلّ ما سبق، و`{0, []}` يمسح النيّة.

        تتجسّد النيّة سندَ صرفٍ واحداً عند ترحيل الفاتورة. مرآة
        `sales/invoices/{id}/payment-voucher/` على جانب الشراء.
        """
        invoice = self.get_object()
        try:
            attach_purchase_payment_voucher(
                invoice,
                cash_amount=request.data.get('cash_amount', 0),
                cash_account_id=request.data.get('cash_account_id'),
                cheques=request.data.get('cheques') or [],
                user=request.user,
            )
        except (ValidationError, DjangoValidationError) as e:
            msg = e.message if hasattr(e, 'message') else '؛ '.join(e.messages)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        invoice.refresh_from_db()
        log_activity(
            action='payment', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number, description='دفعة مرفقة بالمسودة',
            partner_ids=[invoice.partner_id], request=request,
        )
        return Response(
            PurchaseInvoiceSerializer(invoice, context={'request': request}).data
        )

    @action(detail=False, methods=['get'], url_path='next-number')
    def next_number(self, request):
        """T-PSIMPL: رقم الفاتورة التالي قبل الحفظ — مرآة `invoices/next-number/`
        في البيع. كان الترقيم داخلياً بلا نقطة، فالمحرّر يفتح بحقلٍ فارغ ولا
        يعرف المستخدم رقم مستنده إلا بعد أن يحفظه."""
        tenant = self._get_tenant()
        if not tenant:
            return Response(
                {'error': 'الشركة غير محددة.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'invoice_number': self._next_invoice_number(tenant)})

    @action(detail=True, methods=['post'], url_path='duplicate')
    @requires_perm('purchase.invoice.create')
    def duplicate(self, request, pk=None):
        """T-PSIMPL: نسخُ فاتورة شراء إلى مسودّة جديدة — مرآة نظيرتها في البيع.

        يُنسَخ ما يصف **الشراء نفسه** (المورّد والعملة والبنود والرسوم)، ولا
        يُنسَخ ما يخصّ نسخةً بعينها: الترحيل والقيد والاستلام والدفعات والمرفقات
        وارتباطُ مسار الاستيراد. نسخُ أيٍّ من ذلك يعني مستنداً يدّعي أحداثاً لم
        تقع.
        """
        source = self.get_object()
        tenant = source.tenant
        with transaction.atomic():
            clone = PurchaseInvoice.objects.create(
                tenant=tenant,
                invoice_number=self._next_invoice_number(tenant),
                invoice_name=source.invoice_name,
                invoice_date=timezone.localdate(),
                due_date=None,
                payment_terms_days=source.payment_terms_days,
                invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
                partner=source.partner,
                currency=source.currency,
                exchange_rate=source.exchange_rate,
                subtotal=source.subtotal,
                discount_amount=source.discount_amount,
                tax_rate=source.tax_rate,
                tax_amount=source.tax_amount,
                tax_type=source.tax_type,
                shipping_cost=source.shipping_cost,
                shipping_included=source.shipping_included,
                grand_total=source.grand_total,
                payment_type=source.payment_type,
                cash_or_bank_account=source.cash_or_bank_account,
                notes=source.notes,
                status='draft',
                created_by=request.user if request.user.is_authenticated else None,
            )
            for item in source.items.all():
                PurchaseInvoiceItem.objects.create(
                    invoice=clone,
                    product=item.product,
                    name=item.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total_price=item.total_price,
                    # الكمية المستلَمة والأرقام التسلسلية تخصّ الأصل وحده.
                    received_quantity=0,
                    serials=[],
                    expense_account=item.expense_account,
                )
            for fee in source.fees.all():
                PurchaseInvoiceFee.objects.create(
                    tenant=tenant,
                    invoice=clone,
                    description=fee.description,
                    amount=fee.amount,
                    expense_account=fee.expense_account,
                    calculation_type=fee.calculation_type,
                    calculation_value=fee.calculation_value,
                    percentage_basis=fee.percentage_basis,
                    capitalize_to_inventory=fee.capitalize_to_inventory,
                    is_taxable=fee.is_taxable,
                )
        log_activity(
            action='create', entity_type='purchase_invoice', entity_id=clone.id,
            entity_label=clone.invoice_number,
            description=f'نسخ من فاتورة {source.invoice_number}',
            partner_ids=[clone.partner_id], request=request,
        )
        ser = PurchaseInvoiceSerializer(clone, context={'request': request})
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='stock-movements')
    def stock_movements(self, request, pk=None):
        """T-PCTX: أثر هذه الفاتورة على المخزون — مرآة تبويب المبيعات.

        `get_object` هو حارس العزل، والخدمة تُنطَّق فوقه بـ`tenant_id`.
        الحمولة تحمل **سبب الفراغ** لا الصفوف وحدها: مسودّةٌ لم تُرحَّل، أو
        مرحّلةٌ لم تُستلَم بضاعتها بعد — حالتان صحيحتان تُقرآن كعطل إن عُرض لهما
        جدولٌ فارغ بلا تفسير.
        """
        from inventory.services import document_stock_movements
        from logistics.services import PURCHASE_STOCK_REFERENCE_TYPES

        invoice = self.get_object()
        data = document_stock_movements(
            tenant_id=invoice.tenant_id,
            reference_types=PURCHASE_STOCK_REFERENCE_TYPES,
            reference_id=invoice.id,
        )
        data['is_posted'] = invoice.is_posted
        data['receipt_status'] = invoice.receipt_status
        data['receipt_status_display'] = invoice.get_receipt_status_display()
        return Response(data)

    @action(detail=True, methods=['get'], url_path='supplier-ledger')
    def supplier_ledger(self, request, pk=None):
        """T-PCTX: حركة حساب المورّد حول هذه الفاتورة — رصيد قبلها وبعدها.

        **هذه هي الإجابة الصحيحة** عن «رصيد المورّد قبل/بعد»، لا الحقلان
        `supplier_balance_before_invoice`/`after` في السيريالايزر: ذاك تقريبٌ
        يطرح المتبقّي من رصيد **اليوم**، فالفاتورة المسدَّدة بالكامل تُظهر أثراً
        صفرياً وهي دائنةُ ذمم بكامل إجماليها (قيدها يدائن الذمم كلَّها، والدفع
        قيدٌ منفصل). المصدر هنا هو `partner_account_statement` نفسه الذي يبني
        كشف الحساب — المطابقة **بالبناء** لا بالمصادفة. مرآة `customer-ledger`،
        وبها يُغلق الدين الموثَّق في `docs/modules/sales.md`.
        """
        from accounting.services import partner_account_statement

        invoice = self.get_object()
        if not invoice.partner_id:
            return Response({
                'results': [], 'count': 0, 'anchor': None,
                'closing_balance': '0', 'supplier_name': None,
                'reason': 'no_supplier',
            })
        try:
            limit = min(int(request.query_params.get('limit', 20)), 200)
        except (TypeError, ValueError):
            limit = 20
        data = partner_account_statement(
            tenant_id=invoice.tenant_id,
            partner_id=invoice.partner_id,
            is_supplier=True,
            limit=limit,
            anchor_reference_type=(
                'PURCHASE_RETURN' if invoice.is_return else 'PURCHASE_INVOICE'
            ),
            anchor_reference_id=invoice.id,
        )
        data['supplier_name'] = invoice.partner.name if invoice.partner_id else None
        return Response(data)

    # ── T-PCTX: مرفقات فاتورة الشراء ────────────────────────────────────────
    # تُحفظ **فوراً** لا مع حفظ الفاتورة: المرحّلة لا تُعدَّل (`perform_update`
    # يرفض)، وكان الإرفاق معلّقاً بمسار PATCH وحده (`_sync_attachments`) ⇒ لا
    # أحد يُرفق إيصال المورّد بعد الترحيل، وهو أكثر وقت يُحتاج فيه. ولا حذفَ
    # كان أصلاً. مرآة نقاط فاتورة البيع.
    ATTACHMENT_TABLE = 'purchase_invoices'

    @staticmethod
    def _attachment_row(att):
        return {
            'id': att.id,
            'url': att.file_path,
            'file_type': att.file_type or 'Image',
            # الاسم غير مخزَّن في `SystemAttachment` — يُشتقّ من ذيل الرابط.
            'filename': (att.file_path or '').rsplit('/', 1)[-1] or 'مرفق',
            'uploaded_at': att.uploaded_at.isoformat() if att.uploaded_at else None,
        }

    @action(detail=True, methods=['get', 'post'], url_path='attachments')
    def attachments(self, request, pk=None):
        """مرفقات الفاتورة: قراءةً للجميع، وكتابةً بصلاحية التعديل.

        الرفع نفسه يمرّ من `core/media_views.py` (نقطة الاختناق الوحيدة)؛ هذه
        النقطة تربط الرابط الناتج بالفاتورة.
        """
        from core.models import SystemAttachment

        invoice = self.get_object()
        if request.method == 'POST':
            require_perm(request, 'purchase.invoice.edit')
            url = str(request.data.get('url') or '').strip()
            if not url.startswith(('http://', 'https://')):
                return Response(
                    {'error': 'رابط المرفق غير صالح.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            file_type = 'PDF' if url.lower().endswith('.pdf') else 'Image'
            att, _created = SystemAttachment.objects.get_or_create(
                tenant_id=invoice.tenant_id,
                related_table=self.ATTACHMENT_TABLE,
                related_id=invoice.id,
                file_path=url,
                defaults={'file_type': file_type},
            )
            log_activity(
                action='update', entity_type='purchase_invoice', entity_id=invoice.id,
                entity_label=invoice.invoice_number, description='إرفاق ملف بالفاتورة',
                partner_ids=[invoice.partner_id], request=request,
            )
            return Response(self._attachment_row(att), status=status.HTTP_201_CREATED)

        rows = SystemAttachment.objects.filter(
            tenant_id=invoice.tenant_id,
            related_table=self.ATTACHMENT_TABLE,
            related_id=invoice.id,
        ).order_by('id')
        return Response([self._attachment_row(a) for a in rows])

    @action(
        detail=True, methods=['delete'],
        url_path=r'attachments/(?P<attachment_id>[0-9]+)',
    )
    def delete_attachment(self, request, pk=None, attachment_id=None):
        """حذف مرفق واحد — مُنطاقٌ بالفاتورة وشركتها معاً.

        الفلترة بالشركة **وبالفاتورة** لا بالمعرّف وحده: معرّفٌ من فاتورة أخرى
        يعود «غير موجود» بدل أن يُحذف.
        """
        from core.models import SystemAttachment

        invoice = self.get_object()
        require_perm(request, 'purchase.invoice.edit')
        deleted, _ = SystemAttachment.objects.filter(
            id=attachment_id,
            tenant_id=invoice.tenant_id,
            related_table=self.ATTACHMENT_TABLE,
            related_id=invoice.id,
        ).delete()
        if not deleted:
            return Response(
                {'error': 'المرفق غير موجود.'}, status=status.HTTP_404_NOT_FOUND,
            )
        log_activity(
            action='update', entity_type='purchase_invoice', entity_id=invoice.id,
            entity_label=invoice.invoice_number, description='حذف مرفق من الفاتورة',
            partner_ids=[invoice.partner_id], request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='pay')
    @requires_perm('purchase.payment.create')
    def pay(self, request, pk=None):
        """T-APPAY — دفع فاتورة الشراء من داخلها: ترحيل + سند صرف واحد، ذرّياً.

        مرآة `sales/views.py` (`SalesInvoiceViewSet.collect`). كانت الواجهة تنادي
        نقطتين: «رحّل» ثم «سند صرف» — فانقطاعُ الثانية يترك فاتورةً مرحّلة بلا
        سند ومورّداً دائناً، والمستخدم يظنّ أنه دفع. النقطتان هنا نداءٌ واحد داخل
        `transaction.atomic()` واحد: إمّا الاثنان أو لا شيء.

        Body:
            {
                "cash": "60.00",
                "cash_account_id": 12,
                "cheques": [{"cheque_number": "1", "amount": "40",
                             "due_date": "2026-07-01"}],
                "from_on_account": [{"payment_id": 7, "amount": "20"}],
                "post_invoice": true
            }
        """
        from logistics.services import pay_purchase_invoice

        invoice = self.get_object()
        # الغلاف القديم `payment-voucher` يترجم شكل طلبه إلى هذا الشكل.
        payload = getattr(request, '_appay_payload', None) or request.data
        post_invoice = bool(payload.get('post_invoice'))
        if post_invoice and not invoice.is_posted:
            require_perm(request, 'purchase.invoice.post')
        try:
            with transaction.atomic():
                if not invoice.is_posted:
                    if not post_invoice:
                        return Response(
                            {'error': 'الفاتورة غير مرحّلة — رحّلها أولاً أو اطلب '
                                      'الترحيل مع الدفع.'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    # الترحيل يملكه `post_to_accounting` (منطقٌ عريض في الـview لا
                    # في خدمة). ننادي المُعالِج نفسه بدل نسخه — واستخراجُه إلى
                    # خدمة مستقلة تذكرةٌ قائمة بذاتها لا نوسّع بها هذا التغيير.
                    # وسندُ التسوية التلقائي يُكبَت هنا: الدفع الصريح يحلّ محلّه،
                    # وإلّا خطف كاملَ المتبقّي فخرج سندان.
                    self._suppress_auto_settlement = True
                    try:
                        posted = self.post_to_accounting(request, pk=pk)
                    finally:
                        self._suppress_auto_settlement = False
                    if posted.status_code not in (200, 201):
                        raise DjangoValidationError(
                            (posted.data or {}).get('error')
                            or 'تعذّر ترحيل الفاتورة.'
                        )
                    invoice.refresh_from_db()
                payment = pay_purchase_invoice(
                    invoice,
                    cash=payload.get('cash'),
                    cash_account_id=payload.get('cash_account_id'),
                    cheques=payload.get('cheques') or [],
                    from_on_account=payload.get('from_on_account') or [],
                    payment_date=payload.get('payment_date') or None,
                    user=request.user,
                )
        except DjangoValidationError as e:
            msg = e.message if hasattr(e, 'message') else '؛ '.join(e.messages)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as e:
            return Response(
                {'error': e.detail if hasattr(e, 'detail') else str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invoice.refresh_from_db()
        ser = PurchaseInvoiceSerializer(invoice, context={'request': request})
        return Response({
            'invoice': ser.data,
            'payment_id': getattr(payment, 'id', None),
        }, status=status.HTTP_200_OK)

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
            from logistics.services import post_purchase_return
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

        td = invoice.invoice_date or timezone.localdate()

        # ─── GR/IR: الفاتورة المحلية → قيدان منفصلان عبر الحساب الوسيط ──────────
        # بند البضاعة في قيد الفاتورة يدين «الوسيط» بدل المخزون مباشرةً؛ ويُنشأ
        # قيد استلام مستقل (مدين المخزون / دائن الوسيط) + إدخال المخزون فعلياً.
        # المستورد (صفقة/شحنة/تخليص) يبقى كما هو — مخزونه يأتي عبر الشحنة.
        is_local = not (invoice.deal_id or invoice.shipment_id or invoice.clearance_id)
        gr_ir_account = None
        if is_local:
            from logistics.services import _resolve_gr_ir_account
            try:
                gr_ir_account = _resolve_gr_ir_account(tenant)
            except Exception:
                gr_ir_account = None
        use_gr_ir = bool(is_local and gr_ir_account)
        # إعداد «الاستلام مع الترحيل»: معطّلاً يبقى القيد كما هو (البضاعة في
        # الوسيط) وتُستلَم البنود لاحقاً بكمياتها من نافذة الاستلام.
        from logistics.services import get_or_create_purchase_settings
        receive_on_post = get_or_create_purchase_settings(tenant).receive_on_post
        # T-RECVOPT: خيار الفاتورة الواحدة يتقدّم على الإعداد العام.
        #
        # مورّدٌ واحد يوصّل على دفعات كان يُجبر المستخدم على إطفاء الإعداد
        # **لكل الموردين**، فتُفقد الراحة في الحالة الغالبة (البضاعة تصل مع
        # فاتورتها). الخيار لحظةُ ترحيلٍ لا حقلٌ محفوظ: ما بعد الترحيل تقوله
        # `receipt_status` والإرساليات نفسها، فلا داعي لعمودٍ يكرّره.
        override = request.data.get('receive_on_post')
        if override is not None:
            receive_on_post = (
                override if isinstance(override, bool)
                else str(override).strip().lower() in ('1', 'true', 'yes', 'on')
            )

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

                # T-INTENT: نيّة الدفع المرفقة بالمسودة (نقد + شيكات) تتجسّد
                # سندَ صرف واحداً — قبل التسوية التلقائية كي تكمّل هذه ما بقي.
                # الكنس **لا يخضع** لعلم الكبت: ذاك للتسوية التلقائية التي يحلّ
                # الدفعُ الصريح محلّها، أمّا النيّة فمالٌ سجّله المستخدم فعلاً —
                # كبتُها معها كان يتركها عالقةً على فاتورةٍ مرحّلة بلا مرحِّل،
                # وسقفُ `min(intent, remaining)` يمنع أي ازدواج مع سند `pay/`
                # الذي يحسب متبقّيه بعد هذا الكنس.
                _poster = getattr(request, 'user', None)
                settle_attached_purchase_intent(
                    invoice,
                    user=_poster if (_poster is not None and _poster.is_authenticated) else None,
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

        # البنود القابلة للتخزين = ذات منتج، بلا حساب مصروف صريح، وكمية موجبة.
        # التوزيع نفسه يخدم الاستلام المؤجَّل (goods_clearing_unit_costs) — مصدر واحد.
        from logistics.services import goods_clearing_unit_costs
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
        from logistics.services import create_goods_receipt_document
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
        if getattr(self, '_suppress_auto_settlement', False):
            # T-APPAY: الدفع الصريح من نقطة `pay/` يحلّ محلّ التسوية التلقائية —
            # وإلّا خطفت كاملَ المتبقّي قبل أن يوزّع تقسيمُ المستخدم فخرج سندان.
            logger.info(
                "Auto cash settlement suppressed for %s — explicit payment follows.",
                invoice.invoice_number,
            )
            return
        # T-INTENT: النيّة المرفقة سُوّيت قبل سطور بسندها، فهذه تكمّل ما بقي
        # فقط. بدون القصّ يخرج سندان مجموعهما يتجاوز الفاتورة — مرآة الحارس
        # الذي يقف في `_auto_settle_cash_sale` على جانب البيع.
        from logistics.services import purchase_invoice_payment_summary
        invoice._payment_summary_cache = None
        remaining = purchase_invoice_payment_summary(invoice)['remaining_balance']
        amount = min(
            Decimal(str(settle_amount or 0)).quantize(Decimal('0.01')), remaining,
        )
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
            # T-APPAID: التخطّي الصامت كان يترك فاتورةً «نقدية» بلا تسوية والمورد
            # دائناً — ثم يقول الملخّص «مدفوعة بالكامل» لأنها نقدية. الرفض هنا
            # يجعل الشرط ظاهراً للمستخدم بدل أن يتحول إلى رقمٍ كاذب في الشاشة.
            logger.warning(
                "Cash purchase %s cannot be posted: no cash/bank account on the "
                "invoice and no company default.", invoice.invoice_number,
            )
            raise DjangoValidationError(
                "الفاتورة نقدية ولا صندوق محدَّد عليها ولا صندوق افتراضي للشركة — "
                "اختر حساب الصندوق/البنك أو اجعلها فاتورة ذمم (آجلة)."
            )
        user = getattr(request, 'user', None)
        user = user if (user is not None and user.is_authenticated) else None
        from logistics.services import _auto_purchase_settlement_note
        payment = SupplierPayment.objects.create(
            tenant=invoice.tenant,
            partner=invoice.partner,
            purchase_invoice=invoice,
            # T-APINT: العلامة الصريحة تُميّز سند الترحيل عن سند المستخدم، فيُحرَّر
            # مع إلغاء الترحيل بدل أن يبقى مديناً للذمم بلا مقابل.
            auto_settled_invoice=invoice,
            payment_date=invoice.invoice_date or timezone.localdate(),
            amount=amount,
            currency=invoice.currency,
            exchange_rate=invoice.exchange_rate or Decimal('1'),
            cash_or_bank_account_id=cash_account_id,
            notes=_auto_purchase_settlement_note(invoice),
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
        # لقطة ما ستحمله الفاتورة إلى العدم — بعد `destroy` لا يبقى ما يُقرأ منه.
        deleted_changes = build_document_snapshot_changes(
            header=snapshot_fields(instance, PURCHASE_ACTIVITY_FIELD_LABELS),
            lines=_purchase_item_snapshot(instance),
            labels=PURCHASE_ACTIVITY_FIELD_LABELS,
            line_labels=PURCHASE_ACTIVITY_ITEM_LABELS,
            removed=True,
        )
        # T-INTENT: شيكات النيّة تموت مع مستندها — الرابط `SET_NULL` فبدون هذا
        # يترك حذفُ المسودة شيكاتٍ مسودةً يتيمة (مرآة حذف فاتورة البيع).
        Cheque.objects.filter(
            purchase_invoice=instance, status='Draft', supplier_payment__isnull=True,
        ).delete()
        response = super().destroy(request, *args, **kwargs)
        deleted_details = describe_activity_changes(deleted_changes)
        deleted_base = 'حذف ' + ('مرجع شراء' if is_ret else 'فاتورة شراء')
        log_activity(
            action='delete', entity_type='purchase_invoice', entity_id=inv_id,
            entity_label=inv_no,
            description=(
                f'{deleted_base} — {deleted_details}' if deleted_details else deleted_base
            ),
            metadata={'changes': deleted_changes} if deleted_changes else None,
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
                    # T-APINT: سندٌ مرحّل على المستند يمنع حذف قيده — وإلا بقي
                    # قيد السند يدين الذمم بلا مقابل.
                    guard_purchase_invoice_payments_before_unpost(invoice)
                    # الكمية تعود للمخزن ⇒ وحداتها المُرقَّمة تعود معها، وإلا بقي
                    # الرصيد يقول شيئاً وكرت المنتج شيئاً آخر.
                    from inventory.serials import restock_returned_purchase_serials
                    restock_returned_purchase_serials(invoice)
                    result = unpost_document(
                        tenant_id=invoice.tenant_id,
                        reference_id=invoice.pk,
                        journal_reference_types=['PURCHASE_RETURN'],
                        stock_reference_types=['PURCHASE_RETURN'],
                        user=request.user,
                        document_label=f"مرتجع شراء {invoice.invoice_number}",
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
                # T-APINT: سندات الصرف المرحّلة تمنع التراجع (قيدها يدين ذمم
                # المورد، وحذف قيد الفاتورة وحده يتركه بلا مقابل)؛ وسندُ الشراء
                # النقدي التلقائي يُحرَّر بالحذف لأن الترحيل نفسه أنشأه.
                # التحرير **قبل** الحارس — مرآة ترتيب البيع. السند التلقائي صار
                # يحمل توزيعاً (T-INTENT) فيراه الحارس مانعاً لو سبقه، فتمنع
                # الفاتورةُ إلغاءَ ترحيل نفسها بسندٍ هي التي أنشأته.
                release_auto_cash_purchase_settlement(invoice, user=request.user)
                guard_purchase_invoice_payments_before_unpost(invoice)
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

