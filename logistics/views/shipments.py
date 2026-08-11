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
            from logistics.domain.shipment_builder import assert_deals_have_measure
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

        from logistics.payment_posting_cap import shipment_agent_posting_cap_check

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


