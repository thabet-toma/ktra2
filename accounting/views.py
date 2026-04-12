import datetime
import logging
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction as db_transaction
from django.db.models import Q
from rest_framework import serializers as drf_serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from core.api_defaults import ApiAuthAndUser
from partners.models import Partner
from tenants.models import Tenant, Currency
from core.tenant_utils import get_tenant

from .cashbox import (
    allocate_cash_box_account_code,
    get_cash_box_capital_account,
    get_cash_box_parent_account,
)
from .models import (
    Account, CashBoxLedgerAccount, JournalHeader, JournalLine, Cheque,
    CostCenter, ExchangeRate, FiscalPeriod, TaxRate,
)
from .serializers import (
    AccountSerializer,
    CashBoxLedgerAccountSerializer,
    JournalHeaderSerializer,
    JournalHeaderListSerializer,
    ChequeSerializer,
    CostCenterSerializer,
    ExchangeRateSerializer,
    FiscalPeriodSerializer,
    TaxRateSerializer,
)
from .services import (
    validate_journal_entry,
    post_journal_entry,
    create_audit_log,
    create_fiscal_year,
)

logger = logging.getLogger(__name__)


class AccountViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

    def _get_tenant_context(self):
        from tenants.models import Tenant
        # Force Single Tenant Mode as requested
        tenant = get_tenant(self.request)
        if tenant:
            return tenant, tenant.TenantID
        # Fallback to Tenant 1 if no tenant in DB (assuming one exists or will be created)
        # Or return None, 1 to force ID 1.
        return None, 1

    def perform_create(self, serializer):
        tenant_obj, tenant_id = self._get_tenant_context()
        if tenant_obj:
            account = serializer.save(tenant=tenant_obj)
        else:
            account = serializer.save(tenant_id=tenant_id)
        
        create_audit_log(
            tenant=account.tenant if account.tenant else tenant_obj,
            user=self.request.user,
            action='CREATE',
            model_name='Account',
            object_id=account.id,
            change_details=f"Account {account.name} created."
        )

class CostCenterViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = CostCenter.objects.all()
    serializer_class = CostCenterSerializer
    
    def perform_create(self, serializer):
        # Auto assign tenant
        # Reuse logic or abstract it
        from tenants.models import Tenant
        tenant = get_tenant(self.request)
        if tenant:
            serializer.save(tenant=tenant)
        else:
            serializer.save(tenant_id=1)

class ChequeViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Cheque.objects.all()
    serializer_class = ChequeSerializer

    def perform_create(self, serializer):
        # Auto assign tenant
        from tenants.models import Tenant
        tenant = get_tenant(self.request)
        if tenant:
            serializer.save(tenant=tenant)
        else:
            serializer.save(tenant_id=1)

class JournalViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = JournalHeader.objects.all()
    serializer_class = JournalHeaderSerializer

    def get_serializer_class(self):
        if getattr(self, "action", None) == "list":
            return JournalHeaderListSerializer
        return JournalHeaderSerializer

    def get_queryset(self):
        qs = JournalHeader.objects.all().order_by("-transaction_date", "-id")
        params = getattr(self.request, "query_params", {})
        rt = (params.get("reference_type") or "").strip()
        if rt:
            qs = qs.filter(reference_type=rt)
        df = (params.get("date_from") or "").strip()
        dt = (params.get("date_to") or "").strip()
        if df:
            qs = qs.filter(transaction_date__gte=df)
        if dt:
            qs = qs.filter(transaction_date__lte=dt)
        sq = (params.get("search") or "").strip()
        if sq:
            try:
                nid = int(sq)
                qs = qs.filter(
                    Q(id=nid) | Q(reference_id=nid) | Q(description__icontains=sq)
                )
            except ValueError:
                from logistics.models import LogisticsPayment

                pay_match = LogisticsPayment.objects.filter(
                    Q(deal__ref_number__icontains=sq)
                    | Q(deal__factory_name__icontains=sq)
                    | Q(title__icontains=sq)
                ).values_list("pk", flat=True)
                qs = qs.filter(
                    Q(description__icontains=sq)
                    | Q(
                        reference_type="LOGISTICS_PAYMENT",
                        reference_id__in=list(pay_match),
                    )
                )
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        pay_ids = list(
            queryset.filter(reference_type="LOGISTICS_PAYMENT")
            .exclude(reference_id__isnull=True)
            .values_list("reference_id", flat=True)
        )
        pay_map = {}
        if pay_ids:
            from logistics.models import LogisticsPayment

            for p in LogisticsPayment.objects.select_related("deal", "deal__partner").filter(
                pk__in=pay_ids
            ):
                pay_map[p.id] = p
        serializer = self.get_serializer(
            queryset,
            many=True,
            context={**self.get_serializer_context(), "logistics_payments": pay_map},
        )
        return Response(serializer.data)

    def _get_tenant_context(self):
        from tenants.models import Tenant
        # Force Single Tenant Mode
        tenant = get_tenant(self.request)
        if tenant:
            return tenant, tenant.TenantID
        return None, 1

    @action(detail=True, methods=['post'], url_path='post')
    def post_entry(self, request, pk=None):
        try:
            post_journal_entry(pk, user=request.user)
            logger.info("Journal %s posted by user %s", pk, request.user.pk)
            return Response({'status': 'Journal posted successfully'})
        except Exception as e:
            logger.warning("Journal post failed id=%s: %s", pk, e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='reverse')
    def reverse_entry(self, request, pk=None):
        """
        قيد عكسي بنفس المبالغ مع تبديل مدين/دائن لكل سطر.
        """
        orig = self.get_object()
        if not orig.is_posted:
            return Response(
                {'error': 'لا يمكن عكس قيد غير مرحّل أو بلا أسطر مرحّلة.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw_date = request.data.get('transaction_date')
        if raw_date:
            try:
                rev_date = datetime.datetime.fromisoformat(str(raw_date).replace('Z', '+00:00')).date()
            except ValueError:
                rev_date = datetime.date.today()
        else:
            rev_date = datetime.date.today()

        lines = list(orig.lines.all())
        if not lines:
            return Response({'error': 'القيد الأصلي بلا أسطر.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with db_transaction.atomic():
                rev = JournalHeader.objects.create(
                    tenant=orig.tenant,
                    transaction_date=rev_date,
                    description=(f"عكس قيد #{orig.id}: {orig.description or ''}")[:500],
                    reference_type='JOURNAL_REVERSAL',
                    reference_id=orig.id,
                    is_posted=True,
                )
                for line in lines:
                    JournalLine.objects.create(
                        tenant=line.tenant,
                        journal=rev,
                        account=line.account,
                        debit=line.credit,
                        credit=line.debit,
                        partner=line.partner,
                        cost_center=line.cost_center,
                        description=line.description,
                        project_id=line.project_id,
                    )
            create_audit_log(
                tenant=orig.tenant,
                user=request.user,
                action='CREATE',
                model_name='JournalHeader',
                object_id=rev.id,
                change_details=f"Reversal of journal {orig.id}",
            )
            return Response(
                {
                    'status': 'تم إنشاء القيد العكسي',
                    'journal_id': rev.id,
                    'reversed_journal_id': orig.id,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("journal reverse failed")
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        tenant_obj, tenant_id = self._get_tenant_context()
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        if instance.is_posted:
             return Response({'error': 'Cannot edit a posted journal entry.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        lines_data = data.get('lines')  # None if not provided (partial-safe)
        
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        try:
            with db_transaction.atomic():
                header = serializer.save()
                # التحقق من التوازن المحاسبي إذا أُرسلت أسطر
                if lines_data is not None:
                    validate_journal_entry(header, lines_data)
            
            header.refresh_from_db()
            
            create_audit_log(
                tenant=header.tenant if header.tenant else tenant_obj,
                user=self.request.user,
                action='UPDATE',
                model_name='JournalHeader',
                object_id=header.id,
                change_details="Journal entry updated."
            )
            
            response_serializer = JournalHeaderSerializer(header)
            return Response(response_serializer.data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def create(self, request, *args, **kwargs):
        tenant_obj, tenant_id = self._get_tenant_context()
        data = request.data
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        
        from django.db import IntegrityError

        try:
            with db_transaction.atomic():
                if tenant_obj:
                    header = serializer.save(tenant=tenant_obj)
                else:
                    header = serializer.save(tenant_id=tenant_id)
                
                # Validation logic (double-entry check, etc.)
                lines_data = data.get('lines', [])
                validate_journal_entry(header, lines_data)
            
            header.refresh_from_db()
            
            create_audit_log(
                tenant=header.tenant if header.tenant else tenant_obj,
                user=self.request.user,
                action='CREATE',
                model_name='JournalHeader',
                object_id=header.id,
                change_details="Journal entry created."
            )
            
            response_serializer = JournalHeaderSerializer(header)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except IntegrityError as ie:
            return Response({'error': f"Database Integrity Error: {ie}"}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as ve:
            return Response({'error': f"Validation Error (DRF): {ve}"}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as dve:
            msg = dve.message if hasattr(dve, 'message') else str(dve)
            return Response({'error': f"Validation Error (Logic): {msg}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f"Operation Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class GeneralLedgerView(viewsets.ViewSet):
    """
    A specialized ViewSet for the General Ledger Report.
    Returns: Opening Balance, Transactions (with running balance), Closing Balance.
    """
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def list(self, request):
        account_id = request.query_params.get('account_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not all([account_id, start_date, end_date]):
            return Response({'error': 'Missing required parameters: account_id, start_date, end_date'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = Account.objects.get(pk=account_id)
        except Account.DoesNotExist:
            return Response({'error': 'Account not found'}, status=status.HTTP_404_NOT_FOUND)

        # Helper to get all sub-accounts (recursive + code based)
        def get_all_child_accounts(acc):
            # 1. Parent-Child Relationship
            children = Account.objects.filter(parent=acc)
            acc_list = {acc.id: acc} # Use dict to avoid duplicates
            for child in children:
                sub_children = get_all_child_accounts(child)
                for sub in sub_children:
                    acc_list[sub.id] = sub
            
            # 2. Code-based Relationship (Fallback for Al-Aseel style)
            # If Assets is '1', find all '1%'
            if acc.code:
                 code_children = Account.objects.filter(code__startswith=acc.code).exclude(id__in=acc_list.keys())
                 for child in code_children:
                     acc_list[child.id] = child

            return list(acc_list.values())

        target_accounts = get_all_child_accounts(account)

        # 1. Calculate Opening Balance
        # Sum of (Debit - Credit) for all Posted entries before start_date
        from django.db.models import Sum, F, Q
        
        opening_data = JournalLine.objects.filter(
            account__in=target_accounts,
            journal__is_posted=True,
            journal__transaction_date__lt=start_date
        ).aggregate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )

        op_debit = opening_data['total_debit'] or 0
        op_credit = opening_data['total_credit'] or 0
        opening_balance = op_debit - op_credit

        # 2. Fetch Transactions within range
        include_unposted = request.query_params.get('include_unposted') == 'true'
        
        query_filters = {
            'account__in': target_accounts,
            'journal__transaction_date__range': [start_date, end_date]
        }
        
        if not include_unposted:
            query_filters['journal__is_posted'] = True

        transactions = JournalLine.objects.filter(**query_filters).select_related('journal', 'account').order_by('journal__transaction_date', 'journal__id')

        # 3. Calculate Running Balance
        results = []
        current_balance = opening_balance

        # Determine nature of account for display purposes (optional, but good for UI)
        # Usually GL shows Debit/Credit/Balance. 
        # If we want a "signed" balance where Dr is positive:
        
        for line in transactions:
            line_debit = line.debit or 0
            line_credit = line.credit or 0
            
            current_balance += (line_debit - line_credit)
            
            results.append({
                'id': line.id,
                'date': line.journal.transaction_date,
                'journal_id': line.journal.id,
                'description': line.journal.description or line.account.name, # Fallback
                'ref_type': line.journal.reference_type,
                'ref_id': line.journal.reference_id,
                'debit': line_debit,
                'credit': line_credit,
                'balance': current_balance
            })

        return Response({
            'account_name': account.name,
            'account_code': account.code,
            'opening_balance': opening_balance,
            'transactions': results,
            'closing_balance': current_balance
        })

class TrialBalanceView(viewsets.ViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def list(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        include_unposted = request.query_params.get('include_unposted') == 'true'

        if not all([start_date, end_date]):
            import datetime
            today = datetime.date.today()
            start_date = f"{today.year}-01-01"
            end_date = f"{today.year}-12-31"

        from django.db.models import Sum
        
        filters = {
            'journal__transaction_date__range': [start_date, end_date]
        }
        if not include_unposted:
            filters['journal__is_posted'] = True

        try:
            from django.db.models import Value, DecimalField as DjDecimal
            from django.db.models.functions import Coalesce

            tenant = get_tenant(request)
            report_data = []

            activity = {}
            qs = JournalLine.objects.filter(**filters).values(
                'account_id'
            ).annotate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            )
            for entry in qs:
                activity[entry['account_id']] = {
                    'dr': float(entry['total_debit'] or 0),
                    'cr': float(entry['total_credit'] or 0),
                }

            all_accounts = Account.objects.filter(
                tenant=tenant, is_active=True
            ).order_by('code')

            show_all = request.query_params.get('show_all', 'true') == 'true'

            for acct in all_accounts:
                data = activity.get(acct.id, {'dr': 0, 'cr': 0})
                dr = round(data['dr'], 2)
                cr = round(data['cr'], 2)
                balance = round(dr - cr, 2)

                if not show_all and dr == 0 and cr == 0:
                    continue

                report_data.append({
                    'id': acct.id,
                    'code': acct.code,
                    'name': acct.name,
                    'total_debit': dr,
                    'total_credit': cr,
                    'balance': balance,
                })

            return Response(report_data)
        except Exception as e:
            logger.exception("trial-balance report failed")
            return Response({'error': str(e)}, status=500)


class CashBoxLedgerViewSet(viewsets.ModelViewSet):
    """
    إنشاء حساب GL لكل صندوق وربطه بـ external_id (مثل معرف مستند Firestore).
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = CashBoxLedgerAccount.objects.all().select_related("account", "tenant")
    serializer_class = CashBoxLedgerAccountSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if tenant:
            return self.queryset.filter(tenant=tenant)
        return CashBoxLedgerAccount.objects.none()

    def create(self, request, *args, **kwargs):
        external_id = (request.data.get("external_id") or "").strip()
        name = (request.data.get("name") or "").strip()
        currency = (request.data.get("currency_code") or "USD").strip()[:3] or "USD"
        if not external_id or not name:
            return Response(
                {"error": "external_id و name مطلوبان"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = get_tenant(self.request)
        if not tenant:
            return Response({"error": "لا يوجد مستأجر في النظام"}, status=status.HTTP_400_BAD_REQUEST)

        if CashBoxLedgerAccount.objects.filter(tenant=tenant, external_id=external_id[:128]).exists():
            return Response(
                {"error": "هذا المعرف مربوط بالفعل بحساب صندوق"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parent = get_cash_box_parent_account(tenant)
        if not parent:
            return Response(
                {
                    "error": "لم يُعثر على حساب أب للصناديق. أنشئ حساباً تحت الأصول أو عيّن CASH_BOX_PARENT_ACCOUNT_CODE في البيئة.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        code = allocate_cash_box_account_code(parent, tenant)
        try:
            with db_transaction.atomic():
                acc = Account.objects.create(
                    tenant=tenant,
                    code=code,
                    name=name[:100],
                    parent=parent,
                    account_type=parent.account_type,
                    is_active=True,
                )
                link = CashBoxLedgerAccount.objects.create(
                    tenant=tenant,
                    external_id=external_id[:128],
                    name=name[:200],
                    currency_code=currency,
                    account=acc,
                )
        except Exception as e:
            logger.exception("cash box ledger create failed")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        create_audit_log(
            tenant=tenant,
            user=request.user,
            action="CREATE",
            model_name="CashBoxLedgerAccount",
            object_id=link.id,
            change_details=f"Cash box GL {external_id} -> account {acc.id}",
        )
        return Response(
            CashBoxLedgerAccountSerializer(link).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="deposit-journal")
    def deposit_journal(self, request):
        """
        إيداع نقد في صندوق مربوط بـ GL: مدين حساب الصندوق | دائن رأس المال/مساهمات.
        يُنشأ القيد مرحّلاً (is_posted=True) ليظهر في ميزان المراجعة والاستاذ العام.
        """
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد مستأجر في النظام"}, status=status.HTTP_400_BAD_REQUEST)

        ext = str(request.data.get("external_id") or "").strip()
        if not ext:
            return Response(
                {"error": "external_id مطلوب (معرّف صندوق Firestore)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = Decimal(str(request.data.get("amount") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            return Response({"error": "amount غير صالح"}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({"error": "المبلغ يجب أن يكون أكبر من صفر."}, status=status.HTTP_400_BAD_REQUEST)

        raw_td = request.data.get("transaction_date")
        try:
            td = (
                datetime.date.fromisoformat(str(raw_td)[:10])
                if raw_td
                else datetime.date.today()
            )
        except ValueError:
            td = datetime.date.today()

        desc = str(request.data.get("description") or "").strip() or "إيداع صندوق"
        fs_tx = str(request.data.get("firestore_transaction_id") or "").strip()
        ref_note = f" | حركة صندوق:{fs_tx}" if fs_tx else ""

        cash_link = CashBoxLedgerAccount.objects.filter(
            tenant=tenant, external_id=ext[:128]
        ).select_related("account").first()
        if not cash_link or not cash_link.account_id:
            return Response(
                {"error": "الصندوق غير مربوط بحساب محاسبي. أنشئ الربط من قائمة الصناديق أولاً."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        capital = get_cash_box_capital_account(tenant)
        if not capital:
            return Response(
                {
                    "error": "لم يُعثر على حساب رأس مال/حقوق ملكية. أنشئ حساباً من نوع Equity أو عيّن "
                    "CASH_BOX_CAPITAL_ACCOUNT_CODE في البيئة."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        jdesc = f"{desc}{ref_note} | صندوق {cash_link.name}"[:500]
        line_cash = f"إيداع نقد — {cash_link.name}"
        line_cap = f"مساهمة / رأس مال — {desc}"[:500]

        try:
            with db_transaction.atomic():
                j = JournalHeader.objects.create(
                    tenant=tenant,
                    transaction_date=td,
                    description=jdesc,
                    reference_type="CASHBOX_FIRESTORE_DEPOSIT",
                    reference_id=None,
                    is_posted=True,
                )
                JournalLine.objects.create(
                    tenant=tenant,
                    journal=j,
                    account=cash_link.account,
                    debit=amount,
                    credit=0,
                    description=line_cash[:500],
                )
                JournalLine.objects.create(
                    tenant=tenant,
                    journal=j,
                    account=capital,
                    debit=0,
                    credit=amount,
                    description=line_cap[:500],
                )
                validate_journal_entry(j, list(j.lines.all()))
        except DjangoValidationError as ve:
            msg = ve.message if hasattr(ve, "message") else str(ve)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("cash box deposit journal failed")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        create_audit_log(
            tenant=tenant,
            user=request.user,
            action="CREATE",
            model_name="JournalHeader",
            object_id=j.id,
            change_details=f"CASHBOX_DEPOSIT ext={ext} amount={amount}",
        )
        return Response({"journal_id": j.id}, status=status.HTTP_201_CREATED)


class PurchaseReceiptViewSet(viewsets.ViewSet):
    """
    قيد استلام المخزون عند الفاتورة: مدين مخزون | دائن حساب المورد (ذمم).
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def create(self, request):
        tenant = get_tenant(self.request)
        if not tenant:
            return Response({"error": "لا يوجد مستأجر"}, status=status.HTTP_400_BAD_REQUEST)

        partner_id = request.data.get("partner_id")
        if not partner_id:
            return Response({"error": "partner_id مطلوب"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(request.data.get("amount")))
        except (InvalidOperation, TypeError, ValueError):
            return Response({"error": "amount غير صالح"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "المبلغ يجب أن يكون موجباً"}, status=status.HTTP_400_BAD_REQUEST)

        description = (request.data.get("description") or "").strip() or "استلام بضاعة / مخزون"
        invoice_ref = request.data.get("invoice_reference")

        try:
            partner = Partner.objects.get(pk=partner_id, tenant=tenant)
        except Partner.DoesNotExist:
            return Response({"error": "المورد غير موجود"}, status=status.HTTP_404_NOT_FOUND)

        if not partner.linked_account:
            return Response(
                {"error": "المورد بلا حساب محاسبي مربوط"},
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
                {"error": "لم يُعثر على حساب مخزون/مشتريات"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_td = request.data.get("transaction_date")
        if raw_td:
            try:
                td = datetime.datetime.fromisoformat(str(raw_td).replace("Z", "+00:00")).date()
            except ValueError:
                td = datetime.date.today()
        else:
            td = datetime.date.today()

        ref_note = f" | مرجع فاتورة: {invoice_ref}" if invoice_ref else ""
        ref_id = None
        if invoice_ref is not None and str(invoice_ref).strip().isdigit():
            ref_id = int(str(invoice_ref).strip())

        try:
            with db_transaction.atomic():
                j = JournalHeader.objects.create(
                    tenant=tenant,
                    transaction_date=td,
                    description=f"{description}{ref_note} | {partner.name}"[:500],
                    reference_type="PURCHASE_RECEIPT",
                    reference_id=ref_id,
                    is_posted=True,
                )
                JournalLine.objects.create(
                    tenant=tenant,
                    journal=j,
                    account=purchase_account,
                    debit=amount,
                    credit=0,
                    partner=partner,
                )
                JournalLine.objects.create(
                    tenant=tenant,
                    journal=j,
                    account=partner.linked_account,
                    debit=0,
                    credit=amount,
                    partner=partner,
                )
        except Exception as e:
            logger.exception("purchase receipt post failed")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        create_audit_log(
            tenant=tenant,
            user=request.user,
            action="CREATE",
            model_name="JournalHeader",
            object_id=j.id,
            change_details=f"Purchase receipt partner={partner_id} amount={amount}",
        )
        return Response({"journal_id": j.id}, status=status.HTTP_201_CREATED)


class ExchangeRateViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = ExchangeRate.objects.all().select_related('from_currency', 'to_currency')
    serializer_class = ExchangeRateSerializer

    def get_queryset(self):
        qs = super().get_queryset().order_by('-effective_date')
        params = self.request.query_params
        fc = params.get('from_currency')
        tc = params.get('to_currency')
        if fc:
            qs = qs.filter(from_currency_id=fc)
        if tc:
            qs = qs.filter(to_currency_id=tc)
        df = params.get('date_from')
        dt = params.get('date_to')
        if df:
            qs = qs.filter(effective_date__gte=df)
        if dt:
            qs = qs.filter(effective_date__lte=dt)
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if tenant:
            serializer.save(tenant=tenant)
        else:
            serializer.save(tenant_id=1)

    @action(detail=False, methods=['get'], url_path='get-rate')
    def get_rate(self, request):
        fc = request.query_params.get('from_currency')
        tc = request.query_params.get('to_currency')
        date = request.query_params.get('date')
        if not all([fc, tc, date]):
            return Response(
                {'error': 'from_currency, to_currency, date مطلوبة'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rate_obj = (
            ExchangeRate.objects
            .filter(from_currency_id=fc, to_currency_id=tc, effective_date__lte=date)
            .order_by('-effective_date')
            .first()
        )
        if not rate_obj:
            return Response(
                {'error': 'لا يوجد سعر صرف لهذا الزوج في هذا التاريخ أو قبله'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(ExchangeRateSerializer(rate_obj).data)


class FiscalPeriodViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = FiscalPeriod.objects.all().order_by('-start_date')
    serializer_class = FiscalPeriodSerializer

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if tenant:
            serializer.save(tenant=tenant)
        else:
            serializer.save(tenant_id=1)

    @action(detail=False, methods=['post'], url_path='create-year')
    def create_year(self, request):
        year = request.data.get('year')
        if not year:
            return Response({'error': 'year مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            year = int(year)
        except (TypeError, ValueError):
            return Response({'error': 'year يجب أن يكون رقماً'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = get_tenant(self.request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)
        period = create_fiscal_year(tenant, year)
        return Response(FiscalPeriodSerializer(period).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close')
    def close_period(self, request, pk=None):
        period = self.get_object()
        if period.is_closed:
            return Response({'error': 'الفترة مغلقة مسبقاً'}, status=status.HTTP_400_BAD_REQUEST)
        period.status = 'Closed'
        period.is_closed = True
        period.save(update_fields=['status', 'is_closed'])
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'], url_path='reopen')
    def reopen_period(self, request, pk=None):
        period = self.get_object()
        if not period.is_closed:
            return Response({'error': 'الفترة مفتوحة أصلاً'}, status=status.HTTP_400_BAD_REQUEST)
        period.status = 'Open'
        period.is_closed = False
        period.save(update_fields=['status', 'is_closed'])
        return Response(FiscalPeriodSerializer(period).data)


class TaxRateViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = TaxRate.objects.all().select_related('tax_account')
    serializer_class = TaxRateSerializer

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if tenant:
            serializer.save(tenant=tenant)
        else:
            serializer.save(tenant_id=1)


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Currency.objects.all().order_by('-IsBaseCurrency', 'Code')

    class CurrencySerializer(drf_serializers.ModelSerializer):
        class Meta:
            model = Currency
            fields = ['CurrencyID', 'Code', 'Name', 'Symbol', 'IsBaseCurrency']

    serializer_class = CurrencySerializer
