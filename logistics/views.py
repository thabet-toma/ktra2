from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django.db.models import Prefetch
from .models import (
    LogisticsDeal, LogisticsDealItem, LogisticsShipment,
    LogisticsClearance, LogisticsExpense, LogisticsShipmentDeal,
    LogisticsPayment
)
from .serializers import (
    LogisticsDealSerializer, LogisticsDealItemSerializer,
    LogisticsShipmentSerializer, LogisticsClearanceSerializer,
    LogisticsExpenseSerializer, LogisticsPaymentSerializer
)
from tenants.models import Tenant


class BaseTenantViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        # Look for tenant in headers or session, fallback to first()
        tenant_id = self.request.headers.get('X-Tenant-Id')
        if tenant_id:
            tenant = Tenant.objects.filter(TenantID=tenant_id).first()
        else:
            tenant = Tenant.objects.first()
            
        if tenant:
            return self.queryset.filter(tenant=tenant)
        return self.queryset.none()

    def perform_create(self, serializer):
        tenant_id = self.request.headers.get('X-Tenant-Id')
        if tenant_id:
            tenant = Tenant.objects.filter(TenantID=tenant_id).first()
        else:
            tenant = Tenant.objects.first()
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
        tenant = Tenant.objects.first()
        kwargs = {'tenant': tenant}
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
        ترحيل الصفقة كاملة إلى المحاسبة.
        القيد: مدين حساب المشتريات/المخزون | دائن حساب الموردين
        """
        from accounting.models import JournalHeader, JournalLine, Account

        deal = self.get_object()
        if deal.is_posted:
            return Response({'error': 'هذه الصفقة مرحلة بالفعل'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 1. التحقق من وجود حساب للمورد
                if not deal.partner.linked_account:
                    return Response(
                        {'error': 'المورد لا يملك حساباً محاسبياً مربوطاً. الرجاء ربط حساب للمورد أولاً'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 2. إنشاء رأس القيد
                journal = JournalHeader.objects.create(
                    tenant=deal.tenant,
                    transaction_date=deal.order_date,
                    description=f"شراء بضضاعة: {deal.description or deal.ref_number} | المورد: {deal.partner.name}",
                    reference_type='LOGISTICS_DEAL',
                    reference_id=deal.id,
                    is_posted=True
                )

                # 3. سطر دائن: حسابات الموردين (AP)
                JournalLine.objects.create(
                    tenant=deal.tenant,
                    journal=journal,
                    account=deal.partner.linked_account,
                    debit=0,
                    credit=deal.total_amount,
                    partner=deal.partner
                )

                # 4. سطر مدين: مشتريات أو مخزون
                purchase_account = (
                    Account.objects.filter(tenant=deal.tenant, code__startswith='5').first()
                    or Account.objects.filter(tenant=deal.tenant, code__startswith='12').first()
                    or Account.objects.filter(tenant=deal.tenant, account_type='Expense').first()
                )

                if not purchase_account:
                    raise Exception("لم يتم العثور على حساب مشتريات أو مخزون في شجرة الحسابات")

                JournalLine.objects.create(
                    tenant=deal.tenant,
                    journal=journal,
                    account=purchase_account,
                    debit=deal.total_amount,
                    credit=0,
                    partner=deal.partner
                )

                # 5. تحديث الصفقة
                deal.is_posted = True
                deal.journal = journal
                deal.save()

            return Response({
                'status': 'تم الترحيل بنجاح',
                'journal_id': journal.id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='post_payment/(?P<payment_id>[^/.]+)')
    def post_payment_to_accounting(self, request, pk=None, payment_id=None):
        """
        ترحيل دفعة واحدة إلى المحاسبة.
        القيد: مدين حساب الموردين (AP) | دائن حساب البنك/الصندوق
        هذا يُسجّل أن الشركة دفعت للمورد المبلغ المحدد.
        """
        from accounting.models import JournalHeader, JournalLine, Account
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

        # تحديد حساب البنك/الصندوق
        bank_account_id = request.data.get('bank_account_id')
        if bank_account_id:
            try:
                bank_account = Account.objects.get(pk=bank_account_id, tenant=deal.tenant)
            except Account.DoesNotExist:
                return Response({'error': 'حساب البنك غير موجود'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # البحث عن حساب بنك أو صندوق تلقائياً
            bank_account = (
                Account.objects.filter(tenant=deal.tenant, code__startswith='11').first()
                or Account.objects.filter(tenant=deal.tenant, account_type='Asset', name__icontains='بنك').first()
                or Account.objects.filter(tenant=deal.tenant, account_type='Asset').first()
            )

        if not bank_account:
            return Response({'error': 'لم يتم العثور على حساب بنك. الرجاء تحديد حساب البنك'}, status=status.HTTP_400_BAD_REQUEST)

        if not deal.partner.linked_account:
            return Response({'error': 'المورد لا يملك حساباً محاسبياً مربوطاً'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                payment_date = payment.transfer_date or datetime.date.today()
                amount = payment.amount

                # إنشاء رأس القيد
                journal = JournalHeader.objects.create(
                    tenant=deal.tenant,
                    transaction_date=payment_date,
                    description=f"دفعة {payment.title} | صفقة: {deal.ref_number} | المورد: {deal.partner.name}",
                    reference_type='LOGISTICS_PAYMENT',
                    reference_id=payment.id,
                    is_posted=True
                )

                # سطر مدين: حساب الموردين (تخفيض الالتزام)
                JournalLine.objects.create(
                    tenant=deal.tenant,
                    journal=journal,
                    account=deal.partner.linked_account,
                    debit=amount,
                    credit=0,
                    partner=deal.partner
                )

                # سطر دائن: حساب البنك/الصندوق (خروج نقد)
                JournalLine.objects.create(
                    tenant=deal.tenant,
                    journal=journal,
                    account=bank_account,
                    debit=0,
                    credit=amount,
                    partner=deal.partner
                )

                # تحديث الدفعة
                payment.is_posted = True
                payment.journal = journal
                payment.bank_account = bank_account
                payment.save()

                # تحديث حالة الدفع في الصفقة
                payments = deal.payments.all()
                paid_total = sum(p.amount for p in payments if p.is_posted or p.status in ['Paid', 'Confirmed'])
                if paid_total >= deal.total_amount:
                    deal.payment_status = 'Fully Paid'
                elif paid_total > 0:
                    deal.payment_status = 'Partially Paid'
                deal.save()

            return Response({
                'status': 'تم ترحيل الدفعة بنجاح',
                'journal_id': journal.id,
                'payment_id': payment.id
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LogisticsPaymentViewSet(BaseTenantViewSet):
    """ViewSet مستقل للدفعات للاستعلام وإدارة الفواتير"""
    queryset = LogisticsPayment.objects.all().order_by('-created_at')
    serializer_class = LogisticsPaymentSerializer

    def get_queryset(self):
        # لا نفلتر بالـ tenant هنا مباشرة لأن Payment لا تملك tenant field
        # بل نفلتر من خلال الصفقة
        tenant = Tenant.objects.first()
        if tenant:
            return LogisticsPayment.objects.filter(deal__tenant=tenant).order_by('-created_at')
        return LogisticsPayment.objects.none()

    def perform_create(self, serializer):
        serializer.save()


class LogisticsShipmentViewSet(BaseTenantViewSet):
    queryset = LogisticsShipment.objects.all().order_by('-id')
    serializer_class = LogisticsShipmentSerializer

    @action(detail=True, methods=['post'])
    def add_deal(self, request, pk=None):
        shipment = self.get_object()
        deal_id = request.data.get('deal_id')
        if not deal_id:
            return Response({'error': 'deal_id مطلوب'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            deal = LogisticsDeal.objects.get(pk=deal_id)
            LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
            deal.status = 'Shipped'
            deal.order_status = 'Shipping'
            deal.save()
            return Response({'status': 'تم ربط الصفقة بالشحنة بنجاح'}, status=status.HTTP_200_OK)
        except LogisticsDeal.DoesNotExist:
            return Response({'error': 'الصفقة غير موجودة'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
                tenant = Tenant.objects.first()

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
    queryset = LogisticsClearance.objects.all().order_by('-id')
    serializer_class = LogisticsClearanceSerializer


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
