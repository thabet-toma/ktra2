import datetime
import logging
from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, IntegrityError
from django.db.models import Prefetch
from .models import (
    LogisticsDeal, LogisticsDealItem, LogisticsShipment,
    LogisticsClearance, LogisticsExpense, LogisticsShipmentDeal,
    LogisticsPayment, LogisticsClearancePayment,
    PurchaseInvoice, PurchaseInvoiceItem, PurchaseInvoiceFee,
    LocalShipment,
)
from sales.models import SupplierPayment
from .serializers import (
    LogisticsDealSerializer, LogisticsDealItemSerializer,
    LogisticsShipmentSerializer, LogisticsClearanceSerializer,
    LogisticsExpenseSerializer, LogisticsPaymentSerializer,
    LogisticsClearancePaymentSerializer,
    PurchaseInvoiceSerializer, PurchaseInvoiceListSerializer,
    LocalShipmentSerializer, SupplierPaymentSerializer,
)
from accounting.models import Account, TaxRate
from inventory.models import StockMovement
from partners.models import Partner
from partners.signals import ensure_partner_linked_account
from tenants.models import Tenant, Currency
from accounting.models import JournalHeader, JournalLine, CashBoxLedgerAccount
from accounting.cashbox import resolve_default_cash_box_account
from accounting.services import create_audit_log, validate_fiscal_period, post_journal, get_exchange_rate, unpost_document
from core.api_defaults import POSTED_DOC_WARNING
from core.user_roles import user_can_unpost_logistics_deal_payment
from core.tenant_utils import get_tenant
from core.mixins import BaseTenantViewSet
from .landed_cost import (
    import_invoices_from_clearance,
    preview_landed_import,
    recalculate_landed_for_shipment,
    redistribute_shipment_deal_allocations,
)
from .services import attach_pi_payment_voucher

logger = logging.getLogger(__name__)


class LogisticsDealViewSet(BaseTenantViewSet):
    queryset = LogisticsDeal.objects.all().order_by('-order_date')
    serializer_class = LogisticsDealSerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related('partner', 'currency', 'tenant', 'created_by')
            .prefetch_related(
                Prefetch(
                    'items',
                    queryset=LogisticsDealItem.objects.select_related('product', 'deal'),
                ),
                'payments',
            )
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
        serializer.save(**kwargs)

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

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance is not None and instance.payments.filter(is_posted=True).exists():
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.payments.filter(is_posted=True).exists():
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='unpost')
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

                lines_data = [
                    {"account": deal_locked.partner.linked_account_id, "debit": local_amount, "credit": Decimal("0"), "partner": deal_locked.partner_id, "description": f"دفعة {payment_locked.title} | صفقة: {deal_locked.ref_number}"},
                    {"account": bank_account.id, "debit": Decimal("0"), "credit": local_amount, "partner": deal_locked.partner_id, "description": f"دفعة {payment_locked.title} | صفقة: {deal_locked.ref_number}"},
                ]

                journal = post_journal(
                    tenant_id=deal_locked.tenant_id,
                    transaction_date=payment_date,
                    reference_type='LOGISTICS_PAYMENT',
                    reference_id=payment_locked.id,
                    description=f"دفعة {payment_locked.title} | صفقة: {deal_locked.ref_number} | المورد: {deal_locked.partner.name}",
                    lines_data=lines_data,
                    currency=deal_currency,
                    exchange_rate=rate,
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
                    .prefetch_related("lines")
                    .get(pk=jid_locked)
                )
                if not orig.is_posted:
                    return Response(
                        {
                            "error": "القيد المرتبط بالدفعة غير مرحّل — البيانات غير متسقة؛ راجع المحاسبة."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                lines = list(orig.lines.all())
                if not lines:
                    return Response(
                        {"error": "القيد الأصلي بلا أسطر — لا يمكن إنشاء عكس آمن."},
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
                tid = getattr(tenant, "pk", None) if tenant is not None else None
                validate_fiscal_period(tid if tid is not None else 0, rev_date)

                sum_dr = sum(Decimal(str(l.debit or 0)) for l in lines)
                sum_cr = sum(Decimal(str(l.credit or 0)) for l in lines)
                if abs(sum_dr - sum_cr) > Decimal("0.02"):
                    return Response(
                        {
                            "error": f"القيد الأصلي غير متوازن (مدين {sum_dr} ≠ دائن {sum_cr}) — راجع القيد #{orig.id}."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                rev = JournalHeader.objects.create(
                    tenant=tenant,
                    transaction_date=rev_date,
                    description=(
                        f"[إلغاء ترحيل دفعة] صفقة {deal.ref_number} — {pay_row.title} — "
                        f"عكس القيد #{orig.id}"
                    )[:500],
                    reference_type="LOGISTICS_PAYMENT_UNPOST",
                    reference_id=int(pay_row.id),
                    is_posted=True,
                )
                for line in lines:
                    JournalLine.objects.create(
                        tenant=line.tenant,
                        journal=rev,
                        account=line.account,
                        debit=line.credit or 0,
                        credit=line.debit or 0,
                        partner=line.partner,
                        cost_center=line.cost_center,
                        description=(f"عكس قيد #{orig.id}: {(line.description or '')}")[:500],
                        project_id=line.project_id,
                    )

                rev_sum_dr = sum(
                    Decimal(str(x.debit or 0))
                    for x in JournalLine.objects.filter(journal=rev)
                )
                rev_sum_cr = sum(
                    Decimal(str(x.credit or 0))
                    for x in JournalLine.objects.filter(journal=rev)
                )
                if abs(rev_sum_dr - rev_sum_cr) > Decimal("0.02"):
                    raise RuntimeError(
                        f"فشل التحقق من توازن القيد العكسي: مدين {rev_sum_dr} دائن {rev_sum_cr}"
                    )

                # I4-02: الغارد يحجب .save() على قيد مرحّل؛ نستخدم .update() الذي يتجاوز الغارد
                # بشكل مقصود — هذا هو الموضع الوحيد المشروع الذي يُخفَّض فيه is_posted.
                orig_desc = (orig.description or "").strip()
                tag = f" [ملغى ترحيل — عكس مرحّل #{rev.id}]"
                new_desc = (orig_desc + tag)[:500] if tag.strip() not in orig_desc else orig_desc
                JournalHeader.objects.filter(pk=orig.pk).update(
                    is_posted=False,
                    description=new_desc,
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
                            f"إلغاء ترحيل دفعة: إلغاء ترحيل القيد #{orig.id}، "
                            f"قيد عكسي مرحّل #{rev.id}، صفقة {deal.ref_number}"
                        )[:2000],
                    )
                except Exception:
                    pass

            return Response(
                {
                    "status": "تم إلغاء ترحيل الدفعة وإنشاء قيد عكسي مرحّل — يُحدَّث ميزان المراجعة ودفتر الأستاذ للقيود المرحّلة.",
                    "payment_id": int(payment_id),
                    "voided_journal_id": orig.id,
                    "voided_journal_posted": False,
                    "reversal_journal_id": rev.id,
                    "reversal_journal_posted": True,
                    "reversal_date": str(rev_date),
                    "accounting_note": (
                        "القيد الأصلي بقي في النظام غير مرحّل للتدقيق؛ "
                        "التقارير المرحّلة تعكس أثر قيد العكس فقط في الفترة الحالية."
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
            return LogisticsPayment.objects.filter(
                Q(deal__tenant=tenant) | Q(shipment__tenant=tenant)
            ).order_by('-created_at')
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

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("shipping_agent")
            .prefetch_related("deals__partner")
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
        ensure_partner_linked_account(shipment.shipping_agent)
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
                lines_data = [
                    {"account": ag.linked_account_id, "debit": local_amount, "credit": Decimal("0"), "partner": ag.id, "description": f"دفعة {payment_locked.title} | شحنة: {ship_locked.shipment_number}"},
                    {"account": bank_account.id, "debit": Decimal("0"), "credit": local_amount, "partner": ag.id, "description": f"دفعة {payment_locked.title} | شحنة: {ship_locked.shipment_number}"},
                ]

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
                    exchange_rate=rate,
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
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
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
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'تم التراجع عن الترحيل وحذف القيد.', 'unpost_result': result})


class LogisticsClearanceViewSet(BaseTenantViewSet):
    queryset = LogisticsClearance.objects.all().order_by("-id")
    serializer_class = LogisticsClearanceSerializer

    def get_queryset(self):
        deal_mini = LogisticsDeal.objects.only(
            "id", "description", "ref_number", "notes"
        ).order_by("id")
        return (
            super()
            .get_queryset()
            .select_related("shipment", "customs_broker", "tenant")
            .prefetch_related(
                Prefetch("shipment__deals", queryset=deal_mini),
                "local_shipments",
                "lines",
            )
        )

    def _clearance_is_posted(self, clearance):
        return clearance.payments.filter(is_posted=True).exists() or bool(clearance.journal_id)

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance is not None and self._clearance_is_posted(instance):
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if self._clearance_is_posted(instance):
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='unpost')
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

        cost_lines = clearance.cost_lines or []
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

        eps = Decimal("0.01")
        if kind == "clearance":
            if clearance_budget > 0:
                if _paid_clearance() + amount > clearance_budget + eps:
                    return Response(
                        {
                            "error": (
                                f"مجموع دفعات التخليص ({_paid_clearance() + amount:.2f}) "
                                f"يتجاوز مجموع بنود التخليص بدون الشحن ({clearance_budget:.2f}). "
                                "خفّض المبلغ أو راجع البنود."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        else:
            if shipping_budget > 0:
                if _paid_shipping() + amount > shipping_budget + eps:
                    return Response(
                        {
                            "error": (
                                f"مجموع دفعات الشحن ({_paid_shipping() + amount:.2f}) "
                                f"يتجاوز مبلغ بند الشحن في البنود ({shipping_budget:.2f}). "
                                "عدّل بند الشحن أو المبلغ."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
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

                jh = post_journal(
                    tenant_id=clearance.tenant_id,
                    transaction_date=payment_date,
                    reference_type="CLEARANCE_PAYMENT",
                    reference_id=pay.id,
                    description=jdesc,
                    lines_data=lines_data,
                    currency=pay_currency,
                    exchange_rate=pay_rate,
                    user=request.user if hasattr(request, 'user') else None,
                )

                pay.journal = jh
                pay.is_posted = True
                pay.save(update_fields=["journal", "is_posted"])

            ser = LogisticsClearancePaymentSerializer(pay)
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
    def unpost_payment(self, request, pk=None):
        """إلغاء ترحيل دفعة تخليص جمركي — قيد عكسي."""
        from accounting.services import validate_fiscal_period

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

                validate_fiscal_period(orig.tenant_id, rev_date)

                rev = JournalHeader.objects.create(
                    tenant=orig.tenant,
                    transaction_date=rev_date,
                    description=(
                        f"[إلغاء ترحيل] دفع تخليص #{payment.id} — "
                        f"عكس القيد #{orig.id}"
                    )[:500],
                    reference_type="CLEARANCE_PAYMENT_UNPOST",
                    reference_id=payment.id,
                    is_posted=True,
                    currency=orig.currency,
                    exchange_rate=orig.exchange_rate,
                )
                for line in orig.lines.all():
                    JournalLine.objects.create(
                        tenant=line.tenant,
                        journal=rev,
                        account=line.account,
                        debit=line.credit or Decimal('0'),
                        credit=line.debit or Decimal('0'),
                        partner=line.partner,
                        cost_center=line.cost_center,
                        description=(f"عكس #{orig.id}: {line.description or ''}")[:500],
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


class LogisticsExpenseViewSet(BaseTenantViewSet):
    queryset = LogisticsExpense.objects.all().order_by('-invoice_date')
    serializer_class = LogisticsExpenseSerializer

    @action(detail=True, methods=['post'])
    def post_to_accounting(self, request, pk=None):
        """
        ترحيل مصروف لوجستي إلى المحاسبة.
        القيد: مدين حساب المصروف | دائن حساب الالتزام
        """
        from accounting.models import JournalHeader, JournalLine
        import datetime

        expense = self.get_object()
        if expense.is_posted:
            return Response({'error': 'هذا المصروف مرحل بالفعل'}, status=status.HTTP_400_BAD_REQUEST)

        if not expense.expense_account or not expense.payable_account:
            return Response(
                {'error': 'يجب تحديد حساب المصروف وحساب الالتزام'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                # إنشاء رأس القيد (صحيح: transaction_date لا date)
                journal = JournalHeader.objects.create(
                    tenant=expense.tenant,
                    transaction_date=expense.invoice_date or datetime.date.today(),
                    description=f"مصروف لوجستي: {expense.description} ({expense.related_type} #{expense.related_id})",
                    reference_type='LOGISTICS_EXPENSE',
                    reference_id=expense.id,
                    is_posted=True
                )

                # سطر مدين: حساب المصروف
                JournalLine.objects.create(
                    tenant=expense.tenant,
                    journal=journal,
                    account=expense.expense_account,
                    debit=expense.amount,
                    credit=0
                )

                # سطر دائن: حساب الالتزام/المستحق
                JournalLine.objects.create(
                    tenant=expense.tenant,
                    journal=journal,
                    account=expense.payable_account,
                    debit=0,
                    credit=expense.amount
                )

                # تحديث المصروف
                expense.is_posted = True
                expense.journal = journal
                expense.save()

            return Response({
                'status': 'تم الترحيل بنجاح',
                'journal_id': journal.id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PurchaseInvoiceViewSet(BaseTenantViewSet):
    serializer_class = PurchaseInvoiceSerializer

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseInvoiceListSerializer
        return PurchaseInvoiceSerializer

    def get_queryset(self):
        qs = PurchaseInvoice.objects.all().select_related(
            'partner', 'deal', 'shipment', 'clearance', 'currency', 'journal',
        ).prefetch_related('items__product').order_by('-created_at')
        tenant = self._get_tenant()
        if tenant:
            qs = qs.filter(tenant=tenant)
        params = self.request.query_params
        s = params.get('status')
        if s:
            qs = qs.filter(status=s)
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

    def perform_create(self, serializer):
        tenant = self._get_tenant()
        inv_num = self.request.data.get('invoice_number') or self._next_invoice_number(tenant)
        serializer.save(tenant=tenant, invoice_number=inv_num)

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
        return Response({'preview': preview, 'created': ser.data}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='recalculate-landed-cost')
    def recalculate_landed_cost(self, request):
        """إعادة حساب تكلفة الرسوم للفواتير غير المرحّلة المرتبطة بشحنة."""
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
            dr = Decimal(str(request.data.get('deal_remaining_rate', '3.6')))
            sr = Decimal(str(request.data.get('shipment_remaining_rate', '3.6')))
        except Exception:
            return Response({'error': 'سعر صرف غير صالح'}, status=status.HTTP_400_BAD_REQUEST)
        use_cl = bool(request.data.get('use_cost_lines', False))
        try:
            result = recalculate_landed_for_shipment(
                tenant=tenant,
                shipment_id=sid,
                deal_remaining_rate=dr,
                shipment_remaining_rate=sr,
                use_cost_lines=use_cl,
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
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
        ser = PurchaseInvoiceSerializer(invoice, context={'request': request})
        return Response(ser.data)

    @action(detail=True, methods=['post'], url_path='post-to-accounting')
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

        tenant = invoice.tenant or self._get_tenant()
        partner = invoice.partner

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

        # صافي المخزون = grand - tax - (الرسوم غير المرسملة)
        # الرسوم المرسملة سنضيفها لبند المخزون مباشرةً (لذلك لا نخصمها من الصافي)
        non_cap_fees_total = fees_total - capitalized_total
        merchandise_net = grand - tax_amt - non_cap_fees_total
        # يسمح هذا الترتيب بأن grand_total = merchandise_net + tax_amt + non_cap_fees
        # (مع رسوم مرسملة مضمَّنة داخل grand إن وُجدت)
        inventory_debit = merchandise_net + capitalized_total

        items_with_landed = list(invoice.items.all())
        use_landed = False
        if items_with_landed and any(it.landed_line_total_ils for it in items_with_landed if it.landed_line_total_ils is not None):
            landed_sum = sum(
                (Decimal(str(it.landed_line_total_ils or 0)) for it in items_with_landed),
                Decimal('0'),
            )
            if landed_sum > 0:
                inventory_debit = landed_sum + capitalized_total
                use_landed = True

        td = invoice.invoice_date or datetime.date.today()

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

        if inventory_debit > 0:
            lines_payload.append({
                'account': inventory_account.id,
                'debit': inventory_debit.quantize(Decimal('0.01')),
                'credit': Decimal('0'),
                'partner': partner.id,
                'description': f"بضاعة/مخزون — {invoice.invoice_number}",
            })
            
        for acc_id, data in mapped_lines.items():
            names = "، ".join(data['desc'])
            if len(data['desc']) == 3: names += "..."
            lines_payload.append({
                'account': acc_id,
                'debit': data['amount'].quantize(Decimal('0.01')),
                'credit': Decimal('0'),
                'partner': partner.id,
                'description': f"بند مشتريات: {names} — {invoice.invoice_number}"[:500],
            })

        if tax_amt > 0:
            lines_payload.append({
                'account': vat_input_account.id,
                'debit': tax_amt.quantize(Decimal('0.01')),
                'credit': Decimal('0'),
                'partner': partner.id,
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
                'partner': partner.id,
                'description': f"{fee.description} — {invoice.invoice_number}"[:500],
            })

        credit_total = grand + fees_total

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
        try:
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
        except (ValidationError, DjangoValidationError, IntegrityError) as e:
            msg = e.message if hasattr(e, 'message') else str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("purchase invoice post_to_accounting failed pk=%s", invoice.pk)
            return Response({'error': 'حدث خطأ غير متوقع أثناء ترحيل فاتورة الشراء.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'journal_id': journal.id,
            'lines_count': len(lines_payload),
            'total_debit': str(sum((l['debit'] for l in lines_payload), Decimal('0'))),
            'total_credit': str(sum((l['credit'] for l in lines_payload), Decimal('0'))),
            'message': 'تم الترحيل بنجاح',
        }, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance is not None and instance.is_posted:
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_posted:
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='unpost')
    def unpost(self, request, pk=None):
        """تراجع عن الترحيل: حذف كل قيود الفاتورة وحركات استلامها وإرجاعها مسودة."""
        invoice = self.get_object()
        if not invoice.is_posted and invoice.receipt_status == PurchaseInvoice.RECEIPT_NOT:
            return Response(
                {'error': 'الفاتورة غير مرحّلة'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                result = unpost_document(
                    tenant_id=invoice.tenant_id,
                    reference_id=invoice.pk,
                    journal_reference_types=['PURCHASE_INVOICE', 'PURCHASE_RECEIPT'],
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
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'تم التراجع عن الترحيل وحذف القيود.', 'unpost_result': result})


# ── P-H-3: SupplierPayment ──────────────────────────────────────────

class SupplierPaymentViewSet(BaseTenantViewSet):
    serializer_class = SupplierPaymentSerializer

    def get_queryset(self):
        qs = SupplierPayment.objects.all().select_related(
            'partner', 'currency', 'cash_or_bank_account', 'journal',
        ).order_by('-created_at')
        tenant = get_tenant(self.request)
        if tenant:
            qs = qs.filter(tenant=tenant)
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

    @action(detail=True, methods=['post'], url_path='post')
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
    )
    serializer_class = LocalShipmentSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        # فلاتر اختيارية عبر query params
        clearance_id = self.request.query_params.get('clearance')
        carrier_id = self.request.query_params.get('carrier')
        status_f = self.request.query_params.get('status')
        is_posted = self.request.query_params.get('is_posted')
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
                ensure_partner_linked_account(carrier)
            except Exception:
                pass

        serializer.save(tenant=tenant)

    @action(detail=True, methods=['post'], url_path='post-to-accounting')
    def post_to_accounting(self, request, pk=None):
        """ترحيل القيد المحاسبي للشحن المحلي.

        الحالات المدعومة:
          1) credit (آجل): Dr expense_account / Cr AP الناقل
          2) cash (نقدي):  Dr expense_account / Cr cash_or_bank_account

        بعد الترحيل لا يُسمح بالتعديل إلا بعد إلغاء الترحيل.
        """
        shipment = self.get_object()
        tenant = shipment.tenant
        if shipment.is_posted:
            return Response(
                {'error': 'الشحنة مُرحَّلة بالفعل.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if shipment.status == 'cancelled':
            return Response(
                {'error': 'لا يمكن ترحيل شحنة ملغاة.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amt = Decimal(str(shipment.amount or 0))
        if amt <= 0:
            return Response(
                {'error': 'مبلغ الشحنة يجب أن يكون أكبر من صفر.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # حساب المصروف (مدين)
        expense_account = shipment.expense_account
        if not expense_account:
            expense_account = (
                Account.objects.filter(tenant=tenant, code='5305', is_active=True).first()
                or Account.objects.filter(tenant=tenant, code='5301', is_active=True).first()
            )
        if not expense_account:
            return Response(
                {'error': 'لا يوجد حساب مصروف للشحن المحلي (5305).'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # حساب الدائن
        if shipment.payment_type == 'cash':
            credit_account = shipment.cash_or_bank_account
            if not credit_account:
                return Response(
                    {'error': 'يجب اختيار حساب صندوق/بنك في الدفع النقدي.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            credit_partner = None
        else:
            # آجل — AP الناقل
            try:
                ensure_partner_linked_account(shipment.carrier)
            except Exception:
                pass
            credit_account = getattr(shipment.carrier, 'linked_account', None)
            if not credit_account:
                return Response(
                    {'error': 'الناقل لا يملك حساب محاسبي مرتبط.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            credit_partner = shipment.carrier

        # T3-03: keep line amounts NOMINAL (transaction currency). The base
        # equivalent is derived once by JournalLine.save() from
        # journal.exchange_rate (C1-05). Pre-multiplying here AND letting
        # save() multiply again caused amount × rate² (m3-09 double-convert).

        td = shipment.delivery_date or shipment.pickup_date or datetime.date.today()

        # التحقق من الفترة المالية
        try:
            validate_fiscal_period(tenant, td)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        lines_payload = [
            {
                'account': expense_account,
                'debit': amt,
                'credit': Decimal('0'),
                'partner': credit_partner,
                'description': f"شحن محلي {shipment.shipment_number} — {shipment.carrier.name}",
            },
            {
                'account': credit_account,
                'debit': Decimal('0'),
                'credit': amt,
                'partner': credit_partner,
                'description': f"شحن محلي {shipment.shipment_number}",
            },
        ]

        try:
            with transaction.atomic():
                journal = JournalHeader.objects.create(
                    tenant=tenant,
                    transaction_date=td,
                    description=(
                        f"شحن محلي {shipment.shipment_number} | {shipment.carrier.name}"
                    )[:500],
                    reference_type='LOCAL_SHIPMENT',
                    reference_id=shipment.pk,
                    is_posted=True,
                    currency=shipment.currency,
                    exchange_rate=shipment.exchange_rate,
                )
                for ln in lines_payload:
                    JournalLine.objects.create(
                        tenant=tenant,
                        journal=journal,
                        account=ln['account'],
                        partner=ln.get('partner'),
                        description=ln.get('description', '')[:255],
                        debit=ln['debit'],
                        credit=ln['credit'],
                        # base_debit/base_credit auto-derived by JournalLine.save()
                        # from journal.exchange_rate (C1-05). No exchange_rate
                        # kwarg — JournalLine has no such field (was a TypeError).
                    )
                shipment.is_posted = True
                shipment.journal = journal
                shipment.save(update_fields=['is_posted', 'journal'])

                create_audit_log(
                    user=request.user,
                    action='local_shipment_posted',
                    target_type='LocalShipment',
                    target_id=shipment.pk,
                    description=(
                        f"ترحيل شحن محلي {shipment.shipment_number} بمبلغ {amt}"
                    ),
                )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(LocalShipmentSerializer(shipment).data)

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance is not None and getattr(instance, 'is_posted', False):
            raise ValidationError({'detail': POSTED_DOC_WARNING, 'can_unpost': True})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if getattr(instance, 'is_posted', False):
            return Response(
                {'detail': POSTED_DOC_WARNING, 'can_unpost': True},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='unpost')
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
        """نقل تكلفة الشحن المحلي إلى فاتورة مشتريات كرسم (Fee).

        المدخلات:
          - invoice_id: رقم فاتورة الشراء الهدف (يجب أن تكون لنفس tenant)

        يُنشئ PurchaseInvoiceFee بمبلغ الشحنة ويربطها بفاتورة المشتريات.
        إذا كانت capitalize_to_inventory=True سيتم رسملتها على Landed Cost
        تلقائياً عند ترحيل الفاتورة.

        ملاحظة: لا يُرحِّل الشحن محاسبياً — الفاتورة هي التي سترحّل.
        """
        shipment = self.get_object()
        tenant = shipment.tenant
        invoice_id = request.data.get('invoice_id')
        if not invoice_id:
            return Response(
                {'error': 'invoice_id مطلوب.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            invoice = PurchaseInvoice.objects.get(pk=invoice_id, tenant=tenant)
        except PurchaseInvoice.DoesNotExist:
            return Response(
                {'error': 'الفاتورة غير موجودة.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if invoice.is_posted:
            return Response(
                {'error': 'الفاتورة مرحّلة — لا يمكن إضافة رسوم.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if shipment.purchase_invoice_id:
            return Response(
                {'error': 'تم استيراد هذه الشحنة بالفعل.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if shipment.is_posted:
            return Response(
                {
                    'error': (
                        'لا يمكن استيراد شحن مُرحَّل محاسبياً — '
                        'سيُسجَّل مرتين. ألغِ الترحيل أولاً.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # الحساب — افتراضياً الـexpense_account الخاص بالشحنة أو 5305
        expense_account = shipment.expense_account
        if not expense_account:
            expense_account = (
                Account.objects.filter(tenant=tenant, code='5305', is_active=True).first()
                or Account.objects.filter(tenant=tenant, code='5301', is_active=True).first()
            )
        if not expense_account:
            return Response(
                {'error': 'لا يوجد حساب مصروف للشحن المحلي.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                PurchaseInvoiceFee.objects.create(
                    tenant=tenant,
                    invoice=invoice,
                    expense_account=expense_account,
                    description=(
                        f"شحن محلي {shipment.shipment_number} — "
                        f"{shipment.carrier.name}"
                    )[:255],
                    amount=shipment.amount,
                    capitalize_to_inventory=shipment.capitalize_to_inventory,
                    is_taxable=False,
                )
                shipment.purchase_invoice = invoice
                shipment.save(update_fields=['purchase_invoice'])
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': 'تم استيراد الشحنة إلى الفاتورة كرسم',
            'invoice_id': invoice.id,
            'invoice_number': invoice.invoice_number,
        })


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
        if isinstance(cl.cost_lines, list):
            for ln in cl.cost_lines:
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
