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
    PublicSupplierQuoteRequest,
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
    SupplierQuotationLineSerializer,
    PurchaseRFQSerializer,
    PurchaseRFQRecipientSerializer,
    PublicSupplierQuoteRequestSerializer,
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
from core.mixins import BaseTenantViewSet, TenantQuerySetMixin
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
    approve_public_quote_request,
    reject_public_quote_request,
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
        elif self.action == 'list':
            # ISSUE #133 غ٤: بلا `?scope=` صريح **على القائمة** يعود الشراء
            # المحلّي وحده لا النطاقان معاً. مقصورٌ على `list` عمداً — فعلٌ
            # تفصيليّ (`retrieve`/`send`/`award`/…) لا يمرّر `scope` في جسمه
            # أصلاً ولا يجوز أن يُحجب عن مستندٍ استيراديّ بسبب هذا الافتراض.
            #
            # هذه فجوةُ **رؤيةٍ داخل الشركة نفسها** بين شاشتَي الشراء المحلّي
            # والاستيراد — لا تسريبَ بين شركات، فعزل الـtenant عبر
            # `TenantQuerySetMixin` (في `super().get_queryset()` أعلاه) سليمٌ
            # ولا يمسّه هذا التغيير. كل مستدعٍ في الواجهة يرسل `scope` صراحةً
            # على قوائمه اليوم (`listSupplierQuotations` يفرضه معامِلاً
            # إلزامياً)، فالافتراضية هنا حراسةٌ لطلبٍ عارٍ لا مساراً حيّاً.
            # صلاحيةُ قراءةٍ لكل موديول تبقى خارج النطاق عمداً — الحارس العام
            # (`TenantRolePermission`) يمرّر كل قراءة اليوم، وسدُّ ذاك تغييرٌ
            # في نموذج الصلاحيات لا في هذه الشاشة.
            qs = qs.filter(scope=SupplierQuotation.SCOPE_LOCAL)
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

    @action(detail=True, methods=['post'], url_path=r'lines/(?P<line_id>\d+)/internal-note')
    def set_line_internal_note(self, request, pk=None, line_id=None):
        """ISSUE #133 غ٣ (مواصفة #130 §١): كتابةُ تعليقنا الداخليّ على سطر
        عرضٍ من مصفوفة المقارنة — حيث يقرأ المشتري ملاحظة المورّد ويردّ عليها
        فعلياً. تُحدِّث سطراً واحداً بعينه فقط، فلا تمسّ `supplier_note` ولا
        بقية سطور العرض ولا إجمالياته.

        **وليست المسارَ الوحيد**: `SupplierQuotationSerializer` يقبل
        `internal_note` في حمولة الحفظ أيضاً (ويحمله `_line_values` عبر
        حذفِ السطور وإعادةِ إنشائها، مع إبقاء الكاتب والتاريخ إن لم يتغيّر
        النصّ). الفرقُ أنّ هذه النقطة لا تمرّ بذلك الحذف أصلاً — فهي الأسلمُ
        لحقلٍ يُراد له أن يبقى مربوطاً بسطره عبر الزمن، لا الوحيدة. وقولُ
        «الوحيدة» هنا كان يكذب: `supplier_note` وحدَه مقفولٌ بنيوياً
        (`read_only_fields`)، أمّا هذا فمكتوبٌ من مسارين.
        """
        quotation = self.get_object()
        line = quotation.lines.filter(pk=line_id).first()
        if line is None:
            raise ValidationError('السطر غير موجود على هذا العرض.')
        note = str(request.data.get('internal_note') or '').strip()
        if note != line.internal_note:
            line.internal_note = note
            line.internal_note_by = request.user if request.user.is_authenticated else None
            line.internal_note_at = timezone.now()
            line.save(update_fields=['internal_note', 'internal_note_by', 'internal_note_at'])
        return Response(SupplierQuotationLineSerializer(line).data)

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


def _wire_rfq_recipient_shares(tenant, rfq, request):
    """يمنح كلّ مستقبِلٍ بلا رابطٍ خاصٍّ به رابطاً — ISSUE #115.

    استيرادٌ كسول لـ`docshare.services`: نفس نمط `logistics/views/reports.py`
    مع `import_file.services` — لا اعتماديةٌ ثابتة عند إقلاع التطبيقات، والاتجاه
    يبقى `logistics → docshare` لا العكس (`docshare` لا يستورد `logistics` قط).

    **`dedupe=False`**: طلبيةٌ واحدة تخرج لعدّة موردين، وكلٌّ منهم يحتاج
    توكِنه **الخاص** — إعادة استعمال آخر رابطٍ حيّ لنفس (tenant, doc_type, doc_id)
    كانت ستُعطي المورّد الثاني رابط الأوّل نفسه.
    """
    from docshare.models import DOC_PURCHASE_RFQ
    from docshare import services as docshare_services

    for recipient in rfq.recipients.filter(share__isnull=True):
        share = docshare_services.create_share(
            tenant, DOC_PURCHASE_RFQ, rfq.pk,
            user=getattr(request, 'user', None), request=request, dedupe=False,
        )
        recipient.share = share
        recipient.save(update_fields=['share'])


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
            # ISSUE #115: المُسلسِل يبني `share_url` لكل مستقبِل — بلا هذا استعلامٌ
            # لكل صفٍّ في القائمة والتفصيل معاً.
            'recipients__share',
            )
        )
        scope = str(self.request.query_params.get('scope') or '').strip()
        rfq_status = str(self.request.query_params.get('status') or '').strip()
        search = str(self.request.query_params.get('search') or '').strip()
        if scope:
            qs = qs.filter(scope=scope)
        elif self.action == 'list':
            # ISSUE #133 غ٤: مرآةُ نفس الفجوة على `SupplierQuotationViewSet`
            # أعلاه — مقصورٌ على `list` (`send`/`award`/`cancel`/`comparison`/
            # `recipients` كلّها تفعل `self.get_object()` بلا `scope` في
            # جسمها، فتُحجَب عن مستندٍ استيراديّ لو شمَلها هذا الافتراض).
            # نفس التبرير حرفياً: رؤيةٌ داخل الشركة، لا تسريبَ عبرها، وصلاحية
            # القراءة لكل موديول خارج النطاق.
            qs = qs.filter(scope=PurchaseRFQ.SCOPE_LOCAL)
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['public_shares_map'] = self._public_shares_map()
        return context

    def _public_shares_map(self):
        """مواصفة #147 (خريطة #138، البند 27) — «رابطٌ عامٌّ مفتوحٌ ولم يردّ
        عليه أحد» يلزم `PurchaseRFQSerializer` معرفةَ رابطٍ عامٍّ حيٍّ لكلّ
        طلبية. لا علاقة FK تصل الطلبية بمشاركتها العامة (`DocumentShare` عامّ
        بـ`doc_type`/`doc_id` لا مخصَّصٌ بجدولٍ وسيط، خلافاً لـ`recipients__share`
        أعلاه) — فبلا هذه الخريطة كان السيريالايزر سيستعلم عن `DocumentShare`
        مرّةً لكل صفٍّ في القائمة. استعلامٌ واحدٌ للشركة كلّها هنا يكفي: الروابط
        العامة الحيّة نادرة أصلاً (الإلغاء والترسية يُبطلانها تلقائياً).
        """
        if not hasattr(self, '_public_shares_map_cache'):
            tenant = get_tenant(self.request)
            if tenant is None:
                self._public_shares_map_cache = {}
            else:
                from docshare.models import DOC_PURCHASE_RFQ, DocumentShare

                shares = DocumentShare.objects.filter(
                    tenant=tenant, doc_type=DOC_PURCHASE_RFQ, is_public=True,
                    revoked_at__isnull=True, expires_at__gt=timezone.now(),
                )
                self._public_shares_map_cache = {s.doc_id: s for s in shares}
        return self._public_shares_map_cache

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
            #
            # ISSUE #133 غ٣: تسلسلٌ مستقلّ بادئةً ورقماً للاستيراد — كان
            # مشتركاً مع الشراء المحلّي (`purchase_rfq` وحده)، فطلبيةُ استيرادٍ
            # واحدة تُرسَل بين طلبيتين محلّيّتين تُسقط رقم الثانية `0003` بدل
            # `0002`. الشراء المحلّي يبقى على مفتاحه وبادئته القديمين حرفياً —
            # لا إعادة ترقيم لسجلٍّ موجود، والتفرّع في مفتاح العدّاد نفسه لا في
            # قيمة `rfq_number` المخزَّنة سلفاً. مرآةُ `IQ`/`PQ` على العرض
            # (`SupplierQuotation.quotation_number`).
            if not rfq.rfq_number:
                if rfq.scope == PurchaseRFQ.SCOPE_IMPORT:
                    book_key, prefix = 'purchase_rfq_import', 'IRFQ'
                else:
                    book_key, prefix = 'purchase_rfq', 'RFQ'
                sequence = next_document_number(tenant.pk, book_key)
                rfq.rfq_number = f'{prefix}-{sequence:04d}'
            rfq.status = PurchaseRFQ.STATUS_SENT
            rfq.save(update_fields=['rfq_number', 'status', 'updated_at'])

            # ISSUE #115: رابطٌ خاصٌّ لكلّ مستقبِلٍ لا يملك واحداً بعد — يغطّي
            # موردي `supplier_ids` أعلاه وأيّ مستقبِلٍ أُضيف قبل الإرسال (نادر).
            _wire_rfq_recipient_shares(tenant, rfq, request)

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
            # مواصفة #147 (المرحلة 3ب، البند 6ب): إلغاءٌ يُغلق الرابط العامّ
            # تلقائياً — حِزامٌ فوق حمّالة `_rfq_quote_is_open`.
            from logistics.services import revoke_live_public_rfq_share

            revoke_live_public_rfq_share(tenant, rfq, user=request.user, request=request)

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
        """ISSUE #116 (مواصفة #108 §٨) — ترسيةٌ كاملةٌ لموردٍ واحد في هذه
        المرحلة: `supplier` في جسم الطلب يحسم أيّ ردّ (`SupplierQuotation`)
        هو الفائز. عرضُه يُقبَل (`STATUS_ACCEPTED`) دائماً — ثم يتفرّع المسار
        بحسب نطاق الطلبية (ISSUE #133 غ١، قرار المالك 2026-09-04):

        - **شراءٌ محلّي**: يمرّ حرفياً بمسار قبول عرضٍ محلّيّ يدويّ — لا منطق
          ترحيل جديد هنا، تركيبُ خدمات قائمة
          (`convert_local_quotation_to_order`/`_invoice`) وراء مفتاح
          `PurchaseSettings.use_purchase_orders` (#117) وحده يحسم أيّهما.
        - **استيراد**: «بالاستيراد الطلبية والعرض نفس الشي؛ لمّا أُرسي طلبية
          يصير عرض» — الترسية تقبل العرض وتُغلق الطلبية عليه **وتتوقّف هنا**،
          بلا استدعاء أيّ من دالّتَي التحويل (كلتاهما محلّيةٌ فقط بحكم
          `SupplierQuotation.scope`، والمكالمة تُرفض 400 بلا هذا التفريع —
          وهو ما كان يحدث قبل هذه التذكرة: تأكيدٌ يقول «لا رجعة» ثم خطأٌ عن
          «الشراء المحلي»). التحويل إلى صفقة استيراد يمرّ لاحقاً بمسار
          «تحويل إلى صفقة» القائم أصلاً على العرض المقبول — صفقةٌ تحتاج شحناً
          وتخليصاً وتكلفةً مستوردة لا تُولَد من ضغطة واحدة.
        """
        from logistics.services import get_or_create_purchase_settings

        tenant = get_tenant(request)
        with transaction.atomic():
            rfq = PurchaseRFQ.objects.select_for_update().get(
                pk=self.get_object().pk, tenant=tenant,
            )
            if rfq.status != PurchaseRFQ.STATUS_SENT:
                raise ValidationError('يمكن ترسية الطلبيات المُرسَلة فقط.')

            supplier_id = request.data.get('supplier')
            if not supplier_id:
                raise ValidationError({'supplier': 'اختر المورد الذي تُرسى عليه الطلبية.'})

            recipient = rfq.recipients.select_related('quotation', 'supplier').filter(
                supplier_id=supplier_id,
            ).first()
            if recipient is None:
                raise ValidationError({'supplier': 'هذا المورد ليس من مستقبِلي الطلبية.'})
            if recipient.quotation_id is None:
                raise ValidationError({'supplier': 'لم يردّ هذا المورد بعرض سعر بعد.'})

            quotation = SupplierQuotation.objects.select_for_update().get(
                pk=recipient.quotation_id,
            )
            quotation.status = SupplierQuotation.STATUS_ACCEPTED
            quotation.save(update_fields=['status', 'updated_at'])

            document = None
            document_type = None
            document_number = None
            if rfq.scope == PurchaseRFQ.SCOPE_IMPORT:
                # لا تحويل هنا — العرض المقبول هو نهاية المطاف بهذه الشاشة.
                pass
            else:
                settings_obj = get_or_create_purchase_settings(tenant)
                try:
                    if settings_obj.use_purchase_orders:
                        document, _created = convert_local_quotation_to_order(
                            quotation, user=request.user,
                        )
                        document_type = 'purchase_order'
                        document_number = document.order_number
                    else:
                        document, _created = convert_local_quotation_to_invoice(
                            quotation, user=request.user,
                        )
                        document_type = 'purchase_invoice'
                        document_number = document.invoice_number
                except DjangoValidationError as exc:
                    detail = getattr(exc, 'message_dict', None) or getattr(
                        exc, 'messages', None,
                    ) or [str(exc)]
                    raise ValidationError(detail)

            rfq.status = PurchaseRFQ.STATUS_AWARDED
            rfq.save(update_fields=['status', 'updated_at'])
            # مواصفة #147 (المرحلة 3ب، البند 6ب): ترسيةٌ تُغلق الرابط العامّ
            # تلقائياً — نفس منطق `cancel()` أعلاه.
            from logistics.services import revoke_live_public_rfq_share

            revoke_live_public_rfq_share(tenant, rfq, user=request.user, request=request)

        log_activity(
            action='update',
            entity_type='purchase_rfq',
            entity_id=rfq.id,
            entity_label=rfq.rfq_number,
            description=f'ترسية الطلبية على {recipient.supplier.name}',
            request=request,
            partner_ids=[recipient.supplier_id],
        )
        data = PurchaseRFQSerializer(rfq, context={'request': request}).data
        data['awarded_supplier_id'] = recipient.supplier_id
        data['awarded_document'] = (
            {'type': document_type, 'id': document.pk, 'number': document_number}
            if document is not None else None
        )
        return Response(data)

    @action(detail=True, methods=['post'], url_path='public-link')
    def public_link(self, request, pk=None):
        """ينشئ رابطاً **عامّاً** لهذه الطلبية — أو يعيد الحيّ القائم (مواصفة
        #147، المرحلة 3ب). لا صلة بـ`_wire_rfq_recipient_shares`: ذاك رابطٌ
        خاصٌّ لكلّ مستقبِلٍ مسمّى (`is_public=False`، `dedupe=False`)؛ هذا
        رابطٌ واحدٌ لأيّ مجهولٍ يحمله (`is_public=True`، `dedupe=True` ضمن
        جمهوره — `docshare.services.active_share`).

        مدّةُ الصلاحية تتبع مهلة ردّ الطلبية لا الشهر الافتراضي
        (`public_rfq_share_expiry_days`).
        """
        from docshare.models import DOC_PURCHASE_RFQ
        from docshare import services as docshare_services
        from logistics.services import public_rfq_share_expiry_days

        tenant = get_tenant(request)
        rfq = self.get_object()
        share = docshare_services.create_share(
            tenant, DOC_PURCHASE_RFQ, rfq.pk,
            days=public_rfq_share_expiry_days(rfq),
            user=request.user, request=request, is_public=True,
        )
        return Response({
            'share_id': share.pk,
            'public_url': docshare_services.public_url(share),
            'expires_at': share.expires_at,
        })

    @action(detail=True, methods=['post'], url_path='stop-public-link')
    def stop_public_link(self, request, pk=None):
        """«أوقف استقبال العروض» — إبطالٌ يدويٌّ للرابط العامّ الحيّ (مواصفة
        #147، المرحلة 3ب، البند 6ج). الصفّ يبقى — `revoke_live_public_rfq_share`
        لا تحذف أبداً؛ ٤٠٠ صريحة إن لم يكن هناك رابطٌ عامٌّ حيٌّ أصلاً بدل نجاحٍ
        صامت لا يعني شيئاً.
        """
        from logistics.services import revoke_live_public_rfq_share

        tenant = get_tenant(request)
        rfq = self.get_object()
        with transaction.atomic():
            share = revoke_live_public_rfq_share(
                tenant, rfq, user=request.user, request=request,
            )
        if share is None:
            raise ValidationError('لا يوجد رابطٌ عامٌّ نشطٌ لهذه الطلبية.')

        log_activity(
            action='update',
            entity_type='purchase_rfq',
            entity_id=rfq.id,
            entity_label=rfq.rfq_number or f'RFQ-draft-{rfq.id}',
            description='إيقاف استقبال العروض على الرابط العامّ',
            request=request,
        )
        return Response(PurchaseRFQSerializer(rfq, context={'request': request}).data)

    @action(detail=True, methods=['get'])
    def comparison(self, request, pk=None):
        """ISSUE #116 (مواصفة #108 §٨) — مصفوفة الموردين: شاشةٌ مستقلّة عند
        الطلب، صفٌّ لكل بند وعمودٌ لكل موردٍ **ردّ فعلياً** (مورّدٌ لم يردّ
        بعد لا عمود له — فراغٌ لا يُفسَّر خطأً كرفض).

        **خطُّ الأساس هنا التقديريّ لا «أقل سعر»** — خلافاً لعمود العرض
        الواحد (#113): هناك تحاكم المورّد إلى تاريخك، وهنا تحاكم الموردين
        إلى هدفك، ولا يُجمَع العمودان في شاشةٍ واحدة.
        `PurchaseRFQLine.estimated_price` مخزَّنٌ بالعملة الأساسية أصلاً
        (#112 §١) فلا تحويل عليه؛ سعر كلّ موردٍ يُحوَّل هنا بسعر صرف عرضه هو.

        **حساب النسبة المئوية الملوّنة لا يعيش هنا** — الردّ يحمل الأرقام
        الخام فقط (تقديريّ وسعرٌ لكلٍّ بالعملة الأساسية)، والنسبة حسابٌ
        واجهيّ صرف (`computeDeltaPercent`، #113) كي لا تنكتب القاعدة مرّتين
        بلغتين. ثلاثة قيود من المواصفة محروسة هنا:
        - بندٌ بلا سعر تقديريّ ← `estimated_price: None` — لا صفراً.
        - بندٌ لم يُسعّره موردٌ بعينه ← `None` في `prices[]` لذلك المورد، ولا
          يدخل إجماليّ بضاعته (لا يُحتسَب صفراً).
        - `goods_total_base` وحده في الاستجابة — **لا حقل شحنٍ إطلاقاً**
          (قرار المالك 2026-09-03، ناسخاً إجمالي #107 الشامل؛ الشحن باقٍ في
          الصفقة والتكلفة النهائية، الساقط ظهوره في هذه الشاشة وحدها).

        **داخليّةٌ بحتة**: لا `doc_type` مسجَّلاً لها في `docshare.documents`
        — محاولة مشاركتها ترتدّ 400 بنيوياً (`docshare/tests/`).
        """
        from inventory.services import product_display_name

        tenant = get_tenant(request)
        rfq = (
            PurchaseRFQ.objects.select_related('tenant')
            .prefetch_related(
                'lines__product',
                'recipients__supplier',
                'recipients__quotation__currency',
                'recipients__quotation__lines',
                'quotations__currency',
                'quotations__supplier',
                'quotations__lines',
            )
            .get(pk=self.get_object().pk, tenant=tenant)
        )
        lines = list(rfq.lines.all())
        unit_q = Decimal('0.0001')

        def _supplier_quotation_payload(quotation, *, supplier_id, supplier_name, replied_at):
            rate = quotation.exchange_rate if quotation.exchange_rate else Decimal('1')
            # ISSUE #122: المطابقةُ بالنَسَب (`rfq_line`) لا بالترتيب (`seq`).
            # العرضُ الذي يُدخَل من المحرِّر يحتمل حذفَ بندٍ من وسطه فتُرقَّم
            # البقيةُ من جديد — ومطابقةُ `seq` حينها تضع سعر الصنف الثاني تحت
            # الثالث بلا أن يقول شيءٌ في الشاشة. والسقوطُ إلى `seq` مقصورٌ على
            # عرضٍ **لا نَسَبَ في أيّ من سطوره**: عروضُ ما قبل هذه التذكرة،
            # وقد كتبها مسارُ الرابط وحدَه مارّاً على بنود الطلبية بالترتيب.
            quotation_lines = list(quotation.lines.all())
            has_lineage = any(ql.rfq_line_id for ql in quotation_lines)
            if has_lineage:
                lines_by_key = {
                    ql.rfq_line_id: ql for ql in quotation_lines if ql.rfq_line_id
                }
            else:
                lines_by_key = {ql.seq: ql for ql in quotation_lines}

            prices: dict = {}
            notes: dict = {}
            # ISSUE #133 غ٣ (مواصفة #130 §١، مراجعة الجولة الثانية): هذه
            # الشاشة **مصادَقٌ عليها** (لا السطح العام في `docshare`) — فعرضُ
            # تعليقنا الداخليّ هنا ليس تسريباً، بل هو بالضبط مكانه الطبيعيّ:
            # حيث يقرأ المشتري ملاحظة المورّد ويردّ عليها فعلياً. `internal_notes`
            # يحمل النصّ وكاتبه وتاريخه؛ و`quotation_line_ids` يربط بندَ
            # الطلبية بسطر العرض الفعليّ الذي يُكتَب عليه التعليق
            # (`SupplierQuotationViewSet.set_line_internal_note`) — نقطة
            # الكتابة الوحيدة، بديلاً عن محرّر العروض حيث تُحذف السطور وتُعاد
            # عند كل حفظ.
            internal_notes: dict = {}
            quotation_line_ids: dict = {}
            goods_total = Decimal('0')
            for line in lines:
                qline = lines_by_key.get(line.id if has_lineage else line.seq)
                if qline is None:
                    prices[str(line.id)] = None
                    notes[str(line.id)] = None
                    internal_notes[str(line.id)] = None
                    continue
                unit_price_base = (Decimal(qline.unit_price) * rate).quantize(unit_q)
                prices[str(line.id)] = str(unit_price_base)
                # ISSUE #133 غ٣: ملاحظةُ المورّد سببُ وجود المصفوفة نفسه —
                # «هذا ما عندي بدل ما طلبت».
                notes[str(line.id)] = qline.supplier_note or None
                internal_notes[str(line.id)] = {
                    'text': qline.internal_note or '',
                    'by': qline.internal_note_by.get_username() if qline.internal_note_by_id else '',
                    'at': qline.internal_note_at.isoformat() if qline.internal_note_at else None,
                }
                quotation_line_ids[str(line.id)] = qline.id
                goods_total += Decimal(line.quantity) * unit_price_base

            return {
                'supplier_id': supplier_id,
                'supplier_name': supplier_name,
                'quotation_id': quotation.id,
                'quotation_number': quotation.quotation_number,
                'currency_code': quotation.currency.Code,
                'exchange_rate': str(rate),
                # ISSUE #122: سعّره المورّد بنفسه أم أدخلناه عنه — ليسا سواءً
                # في الثقة. شارةٌ عرضيّةٌ صرف، لا حسابَ جديداً في المصفوفة.
                'entry_source': quotation.entry_source,
                'entry_source_display': quotation.get_entry_source_display(),
                'replied_at': replied_at,
                'prices': prices,
                'notes': notes,
                'internal_notes': internal_notes,
                'quotation_line_ids': quotation_line_ids,
                # ISSUE #133 غ٣: ملاحظته العامة على الطلبية كلّها — لا الداخلية.
                'general_note': quotation.general_note or '',
                'goods_total_base': str(goods_total.quantize(Decimal('0.01'))),
            }

        suppliers_payload = []
        for recipient in rfq.recipients.all():
            quotation = recipient.quotation
            if quotation is None:
                continue  # لم يردّ بعد — لا عمود له في المصفوفة
            suppliers_payload.append(_supplier_quotation_payload(
                quotation,
                supplier_id=recipient.supplier_id,
                supplier_name=recipient.supplier.name,
                replied_at=recipient.replied_at,
            ))
        # مواصفة #147 (المرحلة 3أ، قرار #145): عرضٌ وُلد من رابطٍ عامٍّ معتمَد
        # لا يملك `PurchaseRFQRecipient` بتصميمٍ مقصود (#144) — فلا يدخل الحلقة
        # أعلاه. يدخل المصفوفة هنا بنفس الشكل تماماً؛ شارة `entry_source` وحدها
        # تُفرّقه، ولا ترتيبَ خاصاً ولا احتسابَ إضافياً (البند 9، خريطة #138).
        covered_quotation_ids = {
            recipient.quotation_id for recipient in rfq.recipients.all()
            if recipient.quotation_id
        }
        for quotation in rfq.quotations.all():
            if quotation.id in covered_quotation_ids:
                continue
            suppliers_payload.append(_supplier_quotation_payload(
                quotation,
                supplier_id=quotation.supplier_id,
                supplier_name=quotation.supplier.name if quotation.supplier_id
                else (quotation.supplier_draft_name or ''),
                replied_at=quotation.created_at,
            ))

        payload = {
            'rfq_id': rfq.id,
            'rfq_number': rfq.rfq_number,
            'status': rfq.status,
            'lines': [
                {
                    'id': line.id,
                    'seq': line.seq,
                    'product_id': line.product_id,
                    'name': line.name_snapshot or (
                        product_display_name(line.product) if line.product_id else ''
                    ),
                    'quantity': str(line.quantity),
                    'unit_of_measure': line.unit_of_measure,
                    'estimated_price': (
                        str(line.estimated_price) if line.estimated_price is not None else None
                    ),
                }
                for line in lines
            ],
            'suppliers': suppliers_payload,
        }
        return Response(payload)

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
            # ISSUE #115: الطلبية بعد الإرسال مستقبِلوها كلّهم يحملون رابطاً —
            # المستقبِل المضاف الآن ليس استثناءً. قبل الإرسال (نادر) يبقى بلا
            # رابطٍ حتى فعل `send/`، الذي يغطّيه هو أيضاً.
            if rfq.status == PurchaseRFQ.STATUS_SENT:
                _wire_rfq_recipient_shares(tenant, rfq, request)
                recipient.refresh_from_db()
        return Response(
            PurchaseRFQRecipientSerializer(recipient).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """ISSUE #112 (فجوة مُعادة فتحها): «نسخةٌ جديدة» لمن تغيّر احتياجُه
        بعد أوّل إرسال — مواصفة #108 §٧ «ومن أراد التعديل: نسخةٌ جديدة» لم
        تكن منفَّذة، فالبنود مقفلة (`validate` أعلاه) بلا مخرج.

        تُنشئ مسودّةً جديدة: النطاق والملاحظات وكلّ البنود (المنتج،
        `name_snapshot`، المواصفات، الكمية، وحدة القياس، `estimated_price`)
        منسوخةٌ حرفياً. **لا يُنسَخ المستقبِلون ولا الروابط ولا العروض** —
        هؤلاء يخصّون الإرسال الفعلي للأصل، ونسخُهم يعني رابطاً "مُرسلاً" لم
        يُرسَل فعلياً لأحد.

        **لا رقم يُستهلَك هنا** — النسخة مسودّة (`rfq_number=None`) حتى
        `send/` تخصّص لها رقماً بنفس آلية أوّل إرسال (#112 §الترقيم)؛
        `TenantBook.last_used_number` لا يتحرّك بمجرّد النسخ.

        **لا حقل مصدرٍ جديد على النموذج** (لا هجرة لهذه المهمة) — الربط
        بالأصل سطرٌ في الملاحظات يذكر رقمه/معرّفه، لا FK.

        مسموحٌ من أيّ حالة (مسودّة/مُرسَلة/مُرساة/ملغاة): نسخُ مسودّةٍ غير
        ضارّ، ونسخُ طلبيةٍ مُرساة أو ملغاة هو بالضبط الحالة التي تبرّر هذا
        الفعل — احتياجٌ عاد بعد أن أُقفلت الأولى أو أُلغيت.
        """
        tenant = get_tenant(request)
        original = PurchaseRFQ.objects.prefetch_related('lines').get(
            pk=self.get_object().pk, tenant=tenant,
        )

        origin_label = original.rfq_number or f'RFQ-draft-{original.pk}'
        lineage_note = f'نسخة جديدة من الطلبية {origin_label}'
        original_notes = (original.notes or '').strip()
        combined_notes = (
            f'{original_notes}\n{lineage_note}' if original_notes else lineage_note
        )

        with transaction.atomic():
            copy = PurchaseRFQ.objects.create(
                tenant=tenant,
                scope=original.scope,
                rfq_date=timezone.now().date(),
                notes=combined_notes,
                created_by=request.user if request.user.is_authenticated else None,
            )
            PurchaseRFQLine.objects.bulk_create([
                PurchaseRFQLine(
                    tenant=tenant,
                    rfq=copy,
                    product=line.product,
                    seq=line.seq,
                    name_snapshot=line.name_snapshot,
                    specs=line.specs,
                    quantity=line.quantity,
                    unit_of_measure=line.unit_of_measure,
                    estimated_price=line.estimated_price,
                )
                for line in original.lines.all()
            ])

        log_activity(
            action='create',
            entity_type='purchase_rfq',
            entity_id=copy.id,
            entity_label=f'RFQ-draft-{copy.id}',
            description=f'نسخة جديدة من الطلبية {origin_label}',
            request=request,
        )
        return Response(
            PurchaseRFQSerializer(copy, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class PublicSupplierQuoteRequestViewSet(TenantQuerySetMixin, viewsets.ReadOnlyModelViewSet):
    """مساحة انتظار ردود الروابط العامة — مواصفة #147 (المرحلة 3أ).

    للقراءة والاعتماد/الرفض فقط: لا `create`/`update`/`destroy` — الكتابةُ
    الأولى تجيء من سطحٍ عام لاحق (`record_public_quote_request`)، وهذا
    الـViewSet يبني الوجهة الداخلية التي يستقبلها القرار، لا الطريقَ العام.
    """
    serializer_class = PublicSupplierQuoteRequestSerializer
    queryset = PublicSupplierQuoteRequest.objects.all()

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related(
                'tenant', 'rfq', 'share', 'currency',
                'approved_partner', 'approved_quotation', 'decided_by',
            )
            .prefetch_related('lines__rfq_line')
        )
        rfq_id = str(self.request.query_params.get('rfq') or '').strip()
        status_param = str(self.request.query_params.get('status') or '').strip()
        if rfq_id.isdigit():
            qs = qs.filter(rfq_id=int(rfq_id))
        if status_param:
            qs = qs.filter(status=status_param)
        return qs.order_by('-submitted_at', '-id')

    @action(detail=True, methods=['get'])
    def matches(self, request, pk=None):
        """اقتراحاتُ مطابقةٍ لطرفٍ قائم — لا تُلزم ولا تحجب الاعتماد."""
        from partners.serializers import suggest_partner_matches

        row = self.get_object()
        tenant = get_tenant(request)
        results = suggest_partner_matches(
            tenant_id=tenant.pk if tenant else None,
            name=row.supplier_name,
            email=row.supplier_email,
            rfq_id=row.rfq_id,
        )
        return Response(results)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        row = self.get_object()
        tenant = get_tenant(request)
        partner_id = request.data.get('partner')
        partner = None
        if partner_id:
            partner = Partner.objects.filter(
                pk=partner_id, tenant=tenant, partner_type='Supplier',
            ).first()
            if partner is None:
                raise ValidationError({
                    'partner': 'المورد غير موجود أو لا يتبع الشركة الحالية.',
                })
        try:
            quotation = approve_public_quote_request(
                row, partner=partner, user=request.user,
            )
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or getattr(
                exc, 'messages', None,
            ) or [str(exc)]
            raise ValidationError(detail)
        row.refresh_from_db()
        log_activity(
            action='update',
            entity_type='public_supplier_quote_request',
            entity_id=row.pk,
            entity_label=row.supplier_name,
            description=f'اعتماد ردّ مورّدٍ من رابطٍ عام إلى عرض {quotation.quotation_number}',
            request=request,
            partner_ids=[quotation.supplier_id],
            metadata={'quotation_id': quotation.id},
        )
        return Response({
            'status': 'approved',
            'quotation_id': quotation.id,
            'request': PublicSupplierQuoteRequestSerializer(
                row, context={'request': request},
            ).data,
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        row = self.get_object()
        try:
            reject_public_quote_request(row, user=request.user)
        except DjangoValidationError as exc:
            detail = getattr(exc, 'message_dict', None) or getattr(
                exc, 'messages', None,
            ) or [str(exc)]
            raise ValidationError(detail)
        row.refresh_from_db()
        log_activity(
            action='update',
            entity_type='public_supplier_quote_request',
            entity_id=row.pk,
            entity_label=row.supplier_name,
            description='رفض ردّ مورّدٍ من رابطٍ عام',
            request=request,
        )
        return Response(PublicSupplierQuoteRequestSerializer(
            row, context={'request': request},
        ).data)


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


