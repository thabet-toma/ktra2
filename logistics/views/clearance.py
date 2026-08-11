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
                        # يشمل القيد العكسي CLEARANCE_PAYMENT_UNPOST كي لا يبقى
                        # معلّقاً وحده بأثر وهمي (نمط العكس يُبقي الأصل مرحّلاً).
                        journal_reference_types=[
                            'CLEARANCE_PAYMENT', 'LOGISTICS_CLEARANCE_PAYMENT',
                            'CLEARANCE_PAYMENT_UNPOST',
                        ],
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

        from logistics.payment_posting_cap import clearance_broker_posting_cap_check

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
