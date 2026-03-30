import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError

from core.api_defaults import ApiAuthAndUser
from .models import Account, JournalHeader, JournalLine, Cheque, CostCenter
from .serializers import AccountSerializer, JournalHeaderSerializer, JournalLineSerializer, ChequeSerializer, CostCenterSerializer
from .services import validate_journal_entry, post_journal_entry, create_audit_log

logger = logging.getLogger(__name__)


class AccountViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Account.objects.all()
    serializer_class = AccountSerializer

    def _get_tenant_context(self):
        from tenants.models import Tenant
        # Force Single Tenant Mode as requested
        tenant = Tenant.objects.first()
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
        tenant = Tenant.objects.first()
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
        tenant = Tenant.objects.first()
        if tenant:
            serializer.save(tenant=tenant)
        else:
            serializer.save(tenant_id=1)

class JournalViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = JournalHeader.objects.all()
    serializer_class = JournalHeaderSerializer

    def _get_tenant_context(self):
        from tenants.models import Tenant
        # Force Single Tenant Mode
        tenant = Tenant.objects.first()
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

    def update(self, request, *args, **kwargs):
        tenant_obj, tenant_id = self._get_tenant_context()
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        if instance.is_posted:
             return Response({'error': 'Cannot edit a posted journal entry.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        lines_data = data.get('lines', [])
        
        # We need to inject the tenant context early if possible, or handle in serializer
        
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        from django.db import transaction
        try:
            with transaction.atomic():
                header = serializer.save()
                # If lines were provided, validate the new state
                # Note: valid_data lines are already saved by serializer.update, 
                # so we can just validate the header and its lines from DB or data
                if lines_data:
                    validate_journal_entry(header, lines_data) # Validate logic after save to ensure IDs exist? 
                    # OR better: validate BEFORE save if possible. 
                    # But ValidateJournal uses model instances usually.
                    # Current service uses dictionaries if passed data, or model objects. 
                    # Let's check service logic.
                elif not partial:
                    pass 
            
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
        
        from django.db import transaction, IntegrityError
        try:
            with transaction.atomic():
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
            # Group by Account
            report_data = []
            
            # We fetch balances for ALL active accounts
            qs = JournalLine.objects.filter(**filters).values(
                'account__id', 'account__code', 'account__name'
            ).annotate(
                total_debit=Sum('debit'),
                total_credit=Sum('credit')
            ).order_by('account__code')
            
            for entry in qs:
                # CAST to float/string to ensure JSON serialization
                dr = float(entry['total_debit'] or 0)
                cr = float(entry['total_credit'] or 0)
                balance = dr - cr
                
                # Show if there is activity
                if dr == 0 and cr == 0:
                    continue
                    
                report_data.append({
                    'id': entry['account__id'],
                    'code': entry['account__code'],
                    'name': entry['account__name'],
                    'total_debit': dr,
                    'total_credit': cr,
                    'balance': balance
                })
                
            return Response(report_data)
        except Exception as e:
            logger.exception("trial-balance report failed")
            return Response({'error': str(e)}, status=500)
