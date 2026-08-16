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
    Count, DecimalField, F, IntegerField, Max, OuterRef, Prefetch, Q, Subquery,
    Sum, Value,
)
from django.db.models.functions import Cast, Coalesce, Substr
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
    quotation_already_claimed_message,
)
from accounting.models import Account, TaxRate
from core.pagination import EnforcedPageNumberPagination
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



class LogisticsDealViewSet(PagePartnerBalanceMixin, BaseTenantViewSet):
    # P0-5: كاسر تعادل -id — ترتيب حتمي شرط مسبق للترقيم المستقر.
    queryset = LogisticsDeal.objects.all().order_by('-order_date', '-id')
    # P0-5: ترقيم إلزامي — كل مستهلكي القائمة في الواجهة صاروا مُرقَّمين
    # (DealManagement عبر listDealsPage، والبقية صفحة أولى بسقف 200، وready-to-ship
    # وnext-ref وcheck-uniqueness نقاط action مستقلة لا يمسّها ترقيم القائمة).
    pagination_class = EnforcedPageNumberPagination
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
        """D-#### تالٍ لكل الشركة — يشمل المحذوف ناعماً لأن قيد الفريدة يشمله.

        P1-15 (SCALABILITY_AUDIT): كانت الدالة تسحب **كل** أرقام صفقات الشركة
        إلى بايثون وتمرّ عليها بـregex لإيجاد الأقصى — آلاف الصفوف عبر الشبكة
        في كل استدعاء، وتُستدعى عند كل فتح لشاشة صفقة جديدة وعند كل إنشاء.
        الأقصى يُحسب الآن في القاعدة ويُعاد صفٌّ واحد.

        `Cast(Substr(...))` لا الترتيب النصّي: الترتيب المعجمي يصحّ ما دام
        الرقم أربع خانات، وينقلب عند تجاوز 9999 (`D-10000` < `D-9999` نصّياً).
        """
        top = (
            LogisticsDeal.all_objects
            .filter(tenant=tenant, ref_number__regex=r'^D-[0-9]+$')
            .annotate(_seq=Cast(Substr('ref_number', 3), IntegerField()))
            .aggregate(top=Max('_seq'))['top']
        )
        return f"D-{(top or 0) + 1:04d}"

    @action(detail=False, methods=['get'], url_path='next-ref')
    def next_ref(self, request):
        """P0-5: معاينة الرقم التالي للواجهة — كانت تسحب **كل** الصفقات وتحسب
        max(D-nnnn) في المتصفح. الرقم النهائي يبقى من perform_create (الخادم
        يولّد/يصحّح عند السباق) — هذه معاينة عرض فقط."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد شركة محددة.'}, status=400)
        return Response({'ref_number': self._next_deal_ref(tenant)})

    @action(detail=False, methods=['get'], url_path='check-uniqueness')
    def check_uniqueness(self, request):
        """P0-5: فحص تفرّد رقم فاتورة المورد/رابط علي بابا باستعلامين مفهرسين —
        كانت الواجهة تسحب كل الصفقات وتفحص التكرار في JS."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد شركة محددة.'}, status=400)
        invoice = (request.query_params.get('invoice') or '').strip()
        link = (request.query_params.get('link') or '').strip()
        exclude = request.query_params.get('exclude')
        qs = LogisticsDeal.objects.filter(tenant=tenant)
        if exclude:
            qs = qs.exclude(pk=exclude)
        if invoice:
            dup = qs.filter(supplier_invoice_number=invoice).only(
                'id', 'ref_number').first()
            if dup:
                return Response({
                    'is_unique': False, 'error_field': 'invoice',
                    'existing_deal_number': dup.ref_number,
                })
        if link:
            dup = qs.filter(alibaba_link=link).only('id', 'ref_number').first()
            if dup:
                return Response({
                    'is_unique': False, 'error_field': 'link',
                    'existing_deal_number': dup.ref_number,
                })
        return Response({'is_unique': True})

    @staticmethod
    def _save_deal_claiming_quotation(serializer, kwargs, quotation):
        """T113-1: الصفقة تطالب بعرضها المصدر — تحقّق وإنشاء وقلبُ حالة في معاملة واحدة.

        لم يعد هناك تحويلٌ بضغطة: العرض يُفتح محرَّراً غير محفوظ، ولحظةُ «حفظ»
        هي وحدها التي تُنشئ الصفقة وتقلب العرض إلى «محوَّل». قفل صف العرض يغلق
        نافذة السباق بين تحقّق الـserializer والحفظ (تبويبان مفتوحان على العرض
        نفسه)، وقيد الـOneToOne في القاعدة هو الضامن الأخير خلفه.
        """
        with transaction.atomic():
            locked = (
                SupplierQuotation.objects.select_for_update()
                .filter(pk=quotation.pk).first()
            )
            if locked is None:
                raise ValidationError({'source_quotation': 'عرض السعر المصدر غير موجود.'})
            claimed = (
                LogisticsDeal.all_objects
                .filter(source_quotation_id=locked.pk).only('id', 'ref_number').first()
            )
            if claimed is not None:
                raise ValidationError({
                    'source_quotation': quotation_already_claimed_message(locked, claimed),
                })
            if locked.status != SupplierQuotation.STATUS_ACCEPTED:
                raise ValidationError({
                    'source_quotation': 'يجب اعتماد عرض الاستيراد قبل تحويله إلى صفقة.',
                })
            try:
                # نقطة حفظ داخلية: انفجار القيد الفريد يتراجع وحده فتبقى المعاملة
                # صالحة لقراءة الصفقة الفائزة وتسمية رقمها في الرسالة.
                with transaction.atomic():
                    deal = serializer.save(**kwargs)
            except IntegrityError:
                claimed = (
                    LogisticsDeal.all_objects
                    .filter(source_quotation_id=locked.pk).only('id', 'ref_number').first()
                )
                if claimed is None:
                    raise
                raise ValidationError({
                    'source_quotation': quotation_already_claimed_message(locked, claimed),
                })
            locked.status = SupplierQuotation.STATUS_CONVERTED
            locked.save(update_fields=['status', 'updated_at'])
        return deal

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
        quotation = serializer.validated_data.get('source_quotation')
        if quotation is None:
            deal = serializer.save(**kwargs)
        else:
            deal = self._save_deal_claiming_quotation(serializer, kwargs, quotation)
        log_activity(
            action='create', entity_type='deal', entity_id=deal.id,
            entity_label=deal.ref_number, description='إنشاء صفقة', request=self.request,
            partner_ids=[deal.partner_id],
        )
        if quotation is not None:
            log_activity(
                action='convert', entity_type='supplier_quotation',
                entity_id=quotation.pk, entity_label=quotation.quotation_number,
                description=f'تحويل عرض السعر إلى صفقة {deal.ref_number}',
                request=self.request, partner_ids=[deal.partner_id],
                metadata={'deal_id': deal.id, 'deal_ref_number': deal.ref_number},
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
            from logistics.signals import recalculate_deal_payment_status
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
                        # يُحذف قيد الدفعة وأي قيود عكسية مرحّلة من دورات إلغاء/إعادة
                        # سابقة (نمط العكس صار يُبقي الأصل مرحّلاً — 3358bf7)؛ بلا
                        # LOGISTICS_PAYMENT_UNPOST يبقى القيد العكسي معلّقاً وحده
                        # فيُحدث أثراً وهمياً. مطابق لـpurge_deals.py.
                        journal_reference_types=['LOGISTICS_PAYMENT', 'LOGISTICS_PAYMENT_UNPOST'],
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
        from logistics.payment_posting_diagnostics import build_auto_posting_report

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

                from logistics.signals import recalculate_deal_payment_status
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

        from logistics.payment_posting_cap import posting_cap_check

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

                payment_date = payment_locked.transfer_date or timezone.localdate()
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

                from logistics.signals import recalculate_deal_payment_status
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
                        rev_date = timezone.localdate()
                else:
                    rev_date = timezone.localdate()

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

                from logistics.signals import recalculate_deal_payment_status
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
    # P0-5: ترقيم إلزامي — الجدول ينمو بلا حد ولا مستهلك واجهة يعتمد على
    # المصفوفة الخام (تحقق grep على frontend_v2 — صفر استدعاءات لقائمته).
    queryset = LogisticsPayment.objects.all().order_by('-created_at', '-id')
    serializer_class = LogisticsPaymentSerializer
    pagination_class = EnforcedPageNumberPagination

    def get_queryset(self):
        from django.db.models import Q
        tenant = get_tenant(self.request)
        if tenant:
            # نشمل دفعات الصفقات ودفعات الشحنات (deal=None) معاً
            # perf: select_related('journal') يقتل N+1 على journal_id_display لكل صف.
            # P1-5: كان العزل بـ`Q(deal__tenant) | Q(shipment__tenant)` — ضمّتان
            # وOR على كل قراءة. الحقل المباشر (يملؤه save من الوثيقة الأم) يطابق
            # النتيجة نفسها بعمود مفهرس واحد.
            return LogisticsPayment.objects.filter(
                tenant=tenant
            ).select_related('journal').order_by('-created_at', '-id')
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


