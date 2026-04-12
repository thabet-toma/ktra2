import datetime
from decimal import Decimal

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django.db.models import Prefetch
from .models import (
    LogisticsDeal, LogisticsDealItem, LogisticsShipment,
    LogisticsClearance, LogisticsExpense, LogisticsShipmentDeal,
    LogisticsPayment, LogisticsClearancePayment,
    PurchaseInvoice, PurchaseInvoiceItem,
)
from .serializers import (
    LogisticsDealSerializer, LogisticsDealItemSerializer,
    LogisticsShipmentSerializer, LogisticsClearanceSerializer,
    LogisticsExpenseSerializer, LogisticsPaymentSerializer,
    LogisticsClearancePaymentSerializer,
    PurchaseInvoiceSerializer, PurchaseInvoiceListSerializer,
)
from accounting.models import Account, TaxRate
from partners.models import Partner
from partners.signals import ensure_partner_linked_account
from tenants.models import Tenant, Currency
from accounting.models import JournalHeader, JournalLine, CashBoxLedgerAccount
from accounting.cashbox import resolve_default_cash_box_account
from accounting.services import create_audit_log, validate_fiscal_period
from core.user_roles import user_can_unpost_logistics_deal_payment
from core.tenant_utils import get_tenant
from .landed_cost import (
    import_invoices_from_clearance,
    preview_landed_import,
    recalculate_landed_for_shipment,
    redistribute_shipment_deal_allocations,
)


class BaseTenantViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        tenant = get_tenant(self.request)
        if tenant:
            return self.queryset.filter(tenant=tenant)
        return self.queryset.none()

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        serializer.save(tenant=tenant)


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

    def perform_create(self, serializer):
        kwargs = {'tenant': get_tenant(self.request)}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user
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

                journal = JournalHeader.objects.create(
                    tenant=deal_locked.tenant,
                    transaction_date=payment_date,
                    description=f"دفعة {payment_locked.title} | صفقة: {deal_locked.ref_number} | المورد: {deal_locked.partner.name}",
                    reference_type='LOGISTICS_PAYMENT',
                    reference_id=payment_locked.id,
                    is_posted=True,
                    currency=deal_currency,
                    exchange_rate=rate,
                )

                JournalLine.objects.create(
                    tenant=deal_locked.tenant,
                    journal=journal,
                    account=deal_locked.partner.linked_account,
                    debit=local_amount,
                    credit=0,
                    partner=deal_locked.partner,
                )

                JournalLine.objects.create(
                    tenant=deal_locked.tenant,
                    journal=journal,
                    account=bank_account,
                    debit=0,
                    credit=local_amount,
                    partner=deal_locked.partner,
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

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

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

                orig.is_posted = False
                orig_desc = (orig.description or "").strip()
                tag = f" [ملغى ترحيل — عكس مرحّل #{rev.id}]"
                if tag.strip() not in orig_desc:
                    orig.description = (orig_desc + tag)[:500]
                orig.save(update_fields=["is_posted", "description"])

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
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
        serializer.save()


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
            deal = LogisticsDeal.objects.get(pk=deal_id)
            LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
            # حالة الشحن تُحدَّد عبر shipping_workflow_status (إشارة sync_deal_workflow_on_shipment_link)
            return Response({'status': 'تم ربط الصفقة بالشحنة بنجاح'}, status=status.HTTP_200_OK)
        except LogisticsDeal.DoesNotExist:
            return Response({'error': 'الصفقة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
                journal = JournalHeader.objects.create(
                    tenant=ship_locked.tenant,
                    transaction_date=payment_date,
                    description=(
                        f"دفعة {payment_locked.title} | شحنة: {ship_locked.shipment_number} "
                        f"| وكيل شحن: {ag.name}"
                    ),
                    reference_type='LOGISTICS_PAYMENT',
                    reference_id=payment_locked.id,
                    is_posted=True,
                    currency=journal_currency,
                    exchange_rate=rate,
                )

                JournalLine.objects.create(
                    tenant=ship_locked.tenant,
                    journal=journal,
                    account=ag.linked_account,
                    debit=local_amount,
                    credit=0,
                    partner=ag,
                )

                JournalLine.objects.create(
                    tenant=ship_locked.tenant,
                    journal=journal,
                    account=bank_account,
                    debit=0,
                    credit=local_amount,
                    partner=ag,
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

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
        from accounting.models import JournalHeader, JournalLine, Account
        import datetime

        shipment = self.get_object()
        shipping_cost = float(request.data.get('shipping_cost', 0))
        if shipping_cost <= 0:
            return Response({'error': 'الرجاء إدخال تكلفة الشحن'}, status=status.HTTP_400_BAD_REQUEST)

        if not shipment.shipping_agent:
            return Response({'error': 'الشحنة لا تملك وكيل شحن محدد'}, status=status.HTTP_400_BAD_REQUEST)

        if not shipment.shipping_agent.linked_account:
            return Response({'error': 'وكيل الشحن لا يملك حساباً محاسبياً مربوطاً'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                tenant = get_tenant(self.request)

                # حساب مصاريف الشحن
                freight_account = (
                    Account.objects.filter(tenant=tenant, name__icontains='شحن').first()
                    or Account.objects.filter(tenant=tenant, account_type='Expense').first()
                )

                if not freight_account:
                    raise Exception("لم يتم العثور على حساب مصاريف شحن")

                journal = JournalHeader.objects.create(
                    tenant=tenant,
                    transaction_date=shipment.departure_date or datetime.date.today(),
                    description=f"تكلفة شحن | شحنة: {shipment.shipment_number} | وكيل: {shipment.shipping_agent.name}",
                    reference_type='LOGISTICS_SHIPMENT',
                    reference_id=shipment.id,
                    is_posted=True
                )

                JournalLine.objects.create(
                    tenant=tenant,
                    journal=journal,
                    account=freight_account,
                    debit=shipping_cost,
                    credit=0,
                    partner=shipment.shipping_agent
                )

                JournalLine.objects.create(
                    tenant=tenant,
                    journal=journal,
                    account=shipment.shipping_agent.linked_account,
                    debit=0,
                    credit=shipping_cost,
                    partner=shipment.shipping_agent
                )

            return Response({
                'status': 'تم ترحيل تكلفة الشحن بنجاح',
                'journal_id': journal.id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
            .prefetch_related(Prefetch("shipment__deals", queryset=deal_mini))
        )

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

        def _notes_mean_shipping_payment(notes_val) -> bool:
            n = str(notes_val or "").lstrip()
            return n.startswith("[شحن]") or n.startswith("شحن")

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
                (p.amount for p in existing_payments if not _notes_mean_shipping_payment(p.notes)),
                start=Decimal("0"),
            )

        def _paid_shipping() -> Decimal:
            return sum(
                (p.amount for p in existing_payments if _notes_mean_shipping_payment(p.notes)),
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

        if kind == "shipping":
            final_notes = ("[شحن] " + notes).strip() if notes else "[شحن]"
        else:
            final_notes = notes

        try:
            with transaction.atomic():
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

                journal = JournalHeader.objects.create(
                    tenant=clearance.tenant,
                    transaction_date=payment_date,
                    description=jdesc,
                    reference_type="LOGISTICS_CLEARANCE_PAYMENT",
                    reference_id=clearance.id,
                    is_posted=False,
                )

                JournalLine.objects.create(
                    tenant=clearance.tenant,
                    journal=journal,
                    account=payee.linked_account,
                    debit=amount,
                    credit=0,
                    partner=payee,
                    description=line_desc,
                )
                JournalLine.objects.create(
                    tenant=clearance.tenant,
                    journal=journal,
                    account=cash_link.account,
                    debit=0,
                    credit=amount,
                    partner=payee,
                    description=f"صرف من الصندوق {cash_link.name}",
                )

                pay_currency = None
                cur_raw = request.data.get('currency_id')
                if cur_raw is not None:
                    try:
                        pay_currency = Currency.objects.get(pk=int(cur_raw))
                    except Exception:
                        pay_currency = None
                if pay_currency is None:
                    pay_currency = Currency.objects.filter(Code__iexact='ILS').first()

                pay = LogisticsClearancePayment.objects.create(
                    tenant=clearance.tenant,
                    clearance=clearance,
                    customs_broker=payee,
                    amount=amount,
                    currency=pay_currency,
                    payment_date=payment_date,
                    cash_box_external_id=ext[:128],
                    notes=final_notes,
                    is_posted=False,
                    journal=journal,
                )
            ser = LogisticsClearancePaymentSerializer(pay)
            return Response(
                {
                    "status": "تم تسجيل الدفع وإنشاء قيد غير مرحّل. رحّل القيد من صفحة القيود.",
                    "journal_id": journal.id,
                    "payment": ser.data,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


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


class PurchaseInvoiceViewSet(viewsets.ModelViewSet):
    queryset = PurchaseInvoice.objects.all().select_related(
        'partner', 'deal', 'shipment', 'clearance', 'currency', 'journal',
    ).prefetch_related('items__product').order_by('-created_at')
    serializer_class = PurchaseInvoiceSerializer

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseInvoiceListSerializer
        return PurchaseInvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
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

    def perform_update(self, serializer):
        serializer.save()

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

    @action(detail=True, methods=['post'], url_path='post-to-accounting')
    def post_to_accounting(self, request, pk=None):
        """
        ترحيل فاتورة الشراء إلى GL مع فصل ضريبي:
          مدين: مخزون/مشتريات (صافي)
          مدين: ضريبة مدخلات     (ضريبة) — إن وجدت
          دائن: ذمم المورد       (إجمالي)
        """
        invoice = self.get_object()
        if invoice.is_posted:
            return Response(
                {'error': 'الفاتورة مرحّلة مسبقاً'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant = invoice.tenant or self._get_tenant()
        partner = invoice.partner

        if not partner.linked_account:
            return Response(
                {'error': 'المورد بلا حساب محاسبي مربوط'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        purchase_account = (
            Account.objects.filter(tenant=tenant, code__startswith="12").first()
            or Account.objects.filter(tenant=tenant, code__startswith="5").first()
            or Account.objects.filter(tenant=tenant, account_type="Asset", name__icontains="مخزون").first()
            or Account.objects.filter(tenant=tenant, account_type="Asset").order_by("code").first()
        )
        if not purchase_account:
            return Response(
                {'error': 'لم يُعثر على حساب مخزون/مشتريات'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        grand = Decimal(str(invoice.grand_total or 0))
        tax_amt = Decimal(str(invoice.tax_amount or 0))
        net_amount = grand - tax_amt

        if grand <= 0:
            return Response(
                {'error': 'مبلغ الفاتورة يجب أن يكون موجباً'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        td = invoice.invoice_date or datetime.date.today()

        tax_account = None
        if tax_amt > 0:
            active_tax = TaxRate.objects.filter(
                tenant=tenant, is_active=True,
            ).select_related('tax_account').first()
            if active_tax and active_tax.tax_account:
                tax_account = active_tax.tax_account
            else:
                tax_account = Account.objects.filter(
                    tenant=tenant, name__icontains="ضريبة مدخلات",
                ).first() or Account.objects.filter(
                    tenant=tenant, name__icontains="ضريبة",
                    account_type="Asset",
                ).first()

        try:
            with transaction.atomic():
                journal = JournalHeader.objects.create(
                    tenant=tenant,
                    transaction_date=td,
                    description=f"فاتورة شراء {invoice.invoice_number} | {partner.name}"[:500],
                    reference_type="PURCHASE_INVOICE",
                    reference_id=invoice.pk,
                    is_posted=True,
                    currency=invoice.currency,
                    exchange_rate=invoice.exchange_rate,
                )

                JournalLine.objects.create(
                    tenant=tenant, journal=journal,
                    account=purchase_account,
                    debit=net_amount, credit=0,
                    partner=partner,
                )

                if tax_amt > 0 and tax_account:
                    JournalLine.objects.create(
                        tenant=tenant, journal=journal,
                        account=tax_account,
                        debit=tax_amt, credit=0,
                        partner=partner,
                    )

                JournalLine.objects.create(
                    tenant=tenant, journal=journal,
                    account=partner.linked_account,
                    debit=0, credit=grand,
                    partner=partner,
                )

                invoice.is_posted = True
                invoice.journal = journal
                invoice.save(update_fields=['is_posted', 'journal'])

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'journal_id': journal.id,
            'message': 'تم الترحيل بنجاح',
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='unpost')
    def unpost(self, request, pk=None):
        invoice = self.get_object()
        if not invoice.is_posted or not invoice.journal:
            return Response(
                {'error': 'الفاتورة غير مرحّلة'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                j = invoice.journal
                JournalLine.objects.filter(journal=j).delete()
                j.delete()
                invoice.is_posted = False
                invoice.journal = None
                invoice.save(update_fields=['is_posted', 'journal'])
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'message': 'تم إلغاء الترحيل'})
