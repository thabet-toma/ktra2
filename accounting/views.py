import datetime
import logging
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Exists, OuterRef, Prefetch, Q
from rest_framework import serializers as drf_serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from core.access import require_perm, requires_perm
from core.pagination import EnforcedPageNumberPagination
from core.api_defaults import ApiAuthAndUser
from partners.models import Partner
from tenants.models import Tenant, Currency
from core.tenant_utils import get_branch, get_tenant
from django.utils import timezone


def _branch_journal_q(request, tenant, prefix='journal__branch'):
    """task11 M4 — Q filter للفرع النشط (X-Branch-Id) على القيود.

    بدون هيدر → بلا فلترة (مستوى الشركة). الفرع الرئيسي يشمل القيود القديمة
    بلا فرع؛ أي فرع آخر يرى قيوده فقط — أساس P&L/ميزان مستقل لكل فرع.
    """
    from django.db.models import Q
    branch = get_branch(request, tenant)
    if branch is None:
        return Q()
    if branch.is_main:
        return Q(**{prefix: branch}) | Q(**{f'{prefix}__isnull': True})
    return Q(**{prefix: branch})

from .account_classification import SUB_TYPE_CASH_BOX
from .cashbox import (
    allocate_cash_box_account_code,
    get_cash_box_capital_account,
    get_cash_box_parent_account,
)
from .models import (
    Account, CashBoxLedgerAccount, JournalHeader, JournalLine, Cheque,
    CostCenter, ExchangeRate, FiscalPeriod, TaxRate,
    Bank, BankBranch, BankAccount, BankReconciliation, BankReconciliationLine,
)
from .serializers import (
    AccountSerializer,
    BankSerializer,
    BankBranchSerializer,
    BankAccountSerializer,
    BankReconciliationSerializer,
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
    GRANULARITY_MONTHLY,
    assert_no_period_overlap,
    bank_account_statement,
    bank_reconciliation_summary,
    close_bank_reconciliation,
    create_bank_account,
    validate_journal_entry,
    post_journal_entry,
    post_journal,
    create_audit_log,
    create_fiscal_year,
    resolve_import_expense_account,
    year_end_close,
)

logger = logging.getLogger(__name__)


class AccountViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = AccountSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return Account.objects.none()
        qs = Account.objects.filter(tenant=tenant)
        # إخفاء قسم «تكاليف الاستيراد» (الشجرة 53*) عمّن لا يملك صلاحية الاستيراد.
        from core.import_access import user_can_access_import
        if not user_can_access_import(self.request.user, tenant):
            qs = qs.exclude(code__startswith="53")
        return qs.prefetch_related(
            Prefetch(
                "linked_partners",
                queryset=Partner.objects.filter(tenant=tenant).only(
                    "id", "name", "legal_name", "partner_type", "linked_account_id",
                ),
                to_attr="_api_linked_partners",
            )
        # P2-12 (SCALABILITY_AUDIT): شجرة الحسابات كانت بلا ترتيب صريح. `code`
        # فريد لكل شركة (unique_together) فهو ترتيب حتمي بذاته، وهو أيضاً الترتيب
        # الطبيعي للدليل المحاسبي.
        ).order_by("code")

    @action(detail=False, methods=["post"], url_path="resolve-import-expense")
    def resolve_import_expense(self, request):
        """يُرجع حساب مصروف الاستيراد المطابق للاسم أو يُنشئه تحت البند «53».

        تستخدمه رسوم الفواتير الدولية: الكتابة بالاسم تكفي — إن كان موجوداً يُربط،
        وإلا يُضاف للشجرة تحت «مصاريف الاستيراد المباشرة».
        """
        tenant = get_tenant(request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        from core.import_access import user_can_access_import
        if not user_can_access_import(request.user, tenant):
            raise ValidationError({"error": "لا تملك صلاحية الوصول لحسابات الاستيراد."})
        account, created = resolve_import_expense_account(
            tenant.pk, request.data.get("name"),
        )
        if account is None:
            raise ValidationError(
                {"error": "تعذّر تحديد حساب مصاريف الاستيراد — تأكد من الاسم ومن وجود البند «53» في الشجرة."}
            )
        if created:
            create_audit_log(
                tenant=tenant,
                user=request.user,
                action='CREATE',
                model_name='Account',
                object_id=account.id,
                change_details=f"Import expense account {account.code} - {account.name} created from invoice fees.",
            )
        return Response(
            {**AccountSerializer(account).data, "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def perform_create(self, serializer):
        require_perm(self.request, 'accounting.account.manage')
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        account = serializer.save(tenant=tenant)
        create_audit_log(
            tenant=account.tenant,
            user=self.request.user,
            action='CREATE',
            model_name='Account',
            object_id=account.id,
            change_details=f"Account {account.name} created."
        )

    def perform_update(self, serializer):
        require_perm(self.request, 'accounting.account.manage')
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request, 'accounting.account.manage')
        instance.delete()


class CostCenterViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = CostCenter.objects.all()
    serializer_class = CostCenterSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if tenant:
            return CostCenter.objects.filter(tenant=tenant)
        return CostCenter.objects.none()

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)

class ChequeViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Cheque.objects.all()
    serializer_class = ChequeSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if tenant:
            # P2-12 (SCALABILITY_AUDIT): بلا ترتيب صريح يتركه MySQL لخطة التنفيذ،
            # فصفٌّ واحد قد يظهر في صفحتين أو لا يظهر إطلاقاً عند الترقيم. `-id`
            # يكسر التعادل حتماً (مفتاح أساسي).
            return Cheque.objects.filter(tenant=tenant).order_by("-due_date", "-id")
        return Cheque.objects.none()

    def perform_create(self, serializer):
        """T-CHQ3: الورقة تدخل الدفاتر ضمن سندها لا وحدها.

        الشيك في الأنظمة المهنية ليس مستنداً محاسبياً مستقلاً: يُسجَّل داخل سند
        قبض/صرف (أو فاتورة) — بلا توزيع فهو دفعة «على الحساب»، وبتوزيع فهو
        تسوية لفاتورة بعينها. إنشاء شيك سائب هنا كان يخلق ورقة خارج الدفاتر
        لا يُرحَّل لها قيد أبداً (حتى قيد تحصيلها يتخطّاه `transfer_cheque`)،
        فصار مرفوضاً ويُوجَّه للمسار الواحد.
        """
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        data = serializer.validated_data
        linked = (
            data.get("supplier_payment") or data.get("purchase_invoice")
            if data.get("direction") == "Outgoing"
            else data.get("customer_payment") or data.get("sales_invoice")
        )
        if not linked:
            raise ValidationError({"detail": (
                "الشيك يُسجَّل داخل سند قبض/صرف أو من الفاتورة — لا يُنشأ وحده. "
                "من شاشة الشيكات: «شيك وارد» يفتح سند قبض و«شيك صادر» يفتح سند "
                "صرف؛ اتركه بلا توزيع فيُسجَّل دفعةً على الحساب، أو وزّعه على "
                "فاتورة فيُسوّيها."
            )})
        user = self.request.user
        cheque = serializer.save(
            tenant=tenant,
            created_by=user if user and user.is_authenticated else None,
        )
        logger.info(
            "cheque.create id=%s number=%s tenant=%s direction=%s amount=%s",
            cheque.pk, cheque.cheque_number, tenant.TenantID,
            cheque.direction, cheque.amount,
        )

    def update(self, request, *args, **kwargs):
        # task11 R2-A3: تغيير الحالة بـ PATCH خام كان يتجاوز آلة الانتقالات
        # والقيود المحاسبية — الحالة تتغير حصراً عبر transfer/.
        instance = self.get_object()
        new_status = request.data.get("status")
        if new_status and str(new_status) != instance.status:
            return Response(
                {"detail": "تغيير حالة الشيك يتم عبر «تحويل» (POST /cheques/{id}/transfer/) "
                           "حتى يُسجَّل القيد المحاسبي وحركة الشيك."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer(self, request, pk=None):
        """تحويل حالة الشيك مع القيد المحاسبي (collect/bounce/settle/...)."""
        from .services import transfer_cheque
        cheque = self.get_object()
        movement_type = (request.data.get("movement_type") or "").strip()
        if not movement_type:
            raise ValidationError({"movement_type": "نوع الحركة مطلوب."})
        try:
            cheque = transfer_cheque(
                cheque.pk,
                movement_type,
                user=request.user,
                notes=(request.data.get("notes") or "")[:500],
                account_id=request.data.get("account_id"),
                movement_date=request.data.get("movement_date") or None,
                bank_account_id=request.data.get("bank_account") or None,
            )
        except DjangoValidationError as e:
            raise ValidationError(
                {"detail": e.messages if hasattr(e, "messages") else str(e)})
        return Response(ChequeSerializer(cheque).data)

    @action(detail=True, methods=["get"], url_path="movements")
    def movements(self, request, pk=None):
        """T-CHQ2: مسار الشيك كاملاً — كان يُسجَّل في الجدول ولا يُعرض أبداً."""
        from .serializers import ChequeMovementSerializer
        cheque = self.get_object()
        rows = cheque.movements.select_related("created_by").order_by("id")
        return Response(ChequeMovementSerializer(rows, many=True).data)

    @action(detail=False, methods=["get"], url_path="wallet")
    def wallet(self, request):
        """T-CHQ2: محفظة الشيكات — الأوراق التي ما تزال في اليد وآجالها."""
        from .services import cheque_wallet
        tenant = get_tenant(request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        return Response(cheque_wallet(tenant.TenantID))

class JournalViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = JournalHeader.objects.all()
    serializer_class = JournalHeaderSerializer
    # P0-5: ترقيم إلزامي — أكبر جدول محاسبي. المستهلكان: شاشة القيد (تنقّل
    # السجلات صار صفحةً أحدث 200) وDocumentPaymentsTab (بحث مرجعي مصغّر).
    pagination_class = EnforcedPageNumberPagination

    def get_serializer_class(self):
        if getattr(self, "action", None) == "list":
            return JournalHeaderListSerializer
        return JournalHeaderSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        # task11 M7: كان tenant=None → all() — قيود كل الشركات تتسرب
        qs = JournalHeader.objects.none() if tenant is None else JournalHeader.objects.filter(tenant=tenant)
        # صيانة الأداء 2026-07: الـ serializer يقرأ tenant.CompanyName وcurrency.Code
        # لكل صف ⇒ بدون select_related كل قيد = استعلامان إضافيان (N+1).
        qs = qs.select_related("tenant", "currency", "created_by").order_by(
            "-transaction_date", "-id")
        params = getattr(self.request, "query_params", {})
        rt = (params.get("reference_type") or "").strip()
        if rt:
            qs = qs.filter(reference_type=rt)
        # A3: تصفية بالحساب — «أرِني قيود هذا الحساب وحده». استعلام Exists على
        # الأسطر لا join+distinct: الضمّ يكرّر رأس القيد بعدد أسطره على الحساب،
        # وdistinct عليه يفسد الترقيم (count ≠ عدد الصفوف المبثوثة).
        acc = (params.get("account") or "").strip()
        if acc:
            try:
                qs = qs.filter(
                    Exists(JournalLine.objects.filter(
                        journal=OuterRef("pk"), account_id=int(acc)))
                )
            except ValueError:
                qs = qs.none()
        # A3: تصفية بالمستخدم — مَن أنشأ القيد (قيود ما قبل العمود created_by
        # فارغة، فلا تظهر تحت أي مستخدم).
        usr = (params.get("user") or "").strip()
        if usr:
            try:
                qs = qs.filter(created_by_id=int(usr))
            except ValueError:
                qs = qs.none()
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
        # صيانة الأداء 2026-07: كان الـ list اليدوي (لأجل pay_map) يتجاوز ترقيم DRF
        # كلياً فيبثّ كل القيود دفعة واحدة. الآن يحترم ?page= — وpay_map يُبنى من
        # صفوف الصفحة الحالية فقط (لا استعلام values_list إضافياً على الجدول كاملاً).
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        target = page if page is not None else queryset
        pay_ids = [
            j.reference_id for j in target
            if j.reference_type == "LOGISTICS_PAYMENT" and j.reference_id
        ]
        pay_map = {}
        if pay_ids:
            from logistics.models import LogisticsPayment

            for p in LogisticsPayment.objects.select_related("deal", "deal__partner").filter(
                pk__in=pay_ids
            ):
                pay_map[p.id] = p
        # perf: نفس نمط pay_map لفواتير المبيعات وتحصيلات العملاء — يقتل N+1 في
        # build_journal_reference_summary (كان استعلاماً لكل صف من هذين النوعين).
        sales_ids = [
            j.reference_id for j in target
            if j.reference_type == "SALES_INVOICE" and j.reference_id
        ]
        sales_map = {}
        if sales_ids:
            from sales.models import SalesInvoice
            for inv in SalesInvoice.objects.select_related("customer").filter(pk__in=sales_ids):
                sales_map[inv.id] = inv
        cust_ids = [
            j.reference_id for j in target
            if j.reference_type == "CUSTOMER_PAYMENT" and j.reference_id
        ]
        cust_map = {}
        if cust_ids:
            from sales.models import CustomerPayment
            for pay in CustomerPayment.objects.select_related("partner").filter(pk__in=cust_ids):
                cust_map[pay.id] = pay
        serializer = self.get_serializer(
            target,
            many=True,
            context={
                **self.get_serializer_context(),
                "logistics_payments": pay_map,
                "sales_invoices": sales_map,
                "customer_payments": cust_map,
            },
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='users')
    def journal_users(self, request):
        """A3: خيارات فلتر «المستخدم» — مَن أنشأ قيوداً في هذه الشركة وحدها.

        نفس شكل `core/activity_views.py` (`users`) كي يقرأه الفرونت بلا تحويل،
        لكن مصدره القيود نفسها لا سجلّ النشاط.
        """
        from django.contrib.auth.models import User

        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        user_ids = (
            JournalHeader.objects.filter(tenant=tenant, created_by__isnull=False)
            .values_list('created_by_id', flat=True)
            .distinct()
        )
        out = [
            {'id': u.id, 'name': f"{u.first_name} {u.last_name}".strip() or u.username}
            for u in User.objects.filter(id__in=list(user_ids))
        ]
        out.sort(key=lambda x: x['name'])
        return Response(out)

    @action(detail=True, methods=['post'], url_path='post')
    @requires_perm('accounting.journal.post')
    def post_entry(self, request, pk=None):
        try:
            post_journal_entry(pk, user=request.user)
            logger.info("Journal %s posted by user %s", pk, request.user.pk)
            return Response({'status': 'Journal posted successfully'})
        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Journal post failed id=%s", pk)
            return Response({'error': 'حدث خطأ غير متوقع أثناء ترحيل القيد.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='reverse')
    @requires_perm('accounting.journal.unpost')
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

        # Idempotency: reject if already reversed
        # P1-6 (المرحلة 5): فلتر الشركة كان غائباً ⇒ full scan على قيود كل
        # المنصة (الفهرس idx_jh_tenant_ref عموده القائد tenant فلا يعمل بدونه)
        # + خلل وظيفي: تصادم reference_id بين شركتين يمنع عكس قيد مشروع.
        if JournalHeader.objects.filter(
            tenant_id=orig.tenant_id,
            reference_type='JOURNAL_REVERSAL', reference_id=orig.id,
        ).exists():
            return Response(
                {'error': 'تم عكس هذا القيد مسبقاً.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw_date = request.data.get('transaction_date')
        if raw_date:
            try:
                rev_date = datetime.datetime.fromisoformat(str(raw_date).replace('Z', '+00:00')).date()
            except ValueError:
                rev_date = timezone.localdate()
        else:
            rev_date = timezone.localdate()

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
        except (ValidationError, DjangoValidationError, IntegrityError) as e:
            msg = e.message if hasattr(e, 'message') else str(e)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("journal reverse failed id=%s", pk)
            return Response({'error': 'حدث خطأ غير متوقع أثناء عكس القيد.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def update(self, request, *args, **kwargs):
        require_perm(request, 'accounting.journal.create')
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        if instance.is_posted:
            return Response({'error': 'Cannot edit a posted journal entry.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        lines_data = data.get('lines')

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            with db_transaction.atomic():
                header = serializer.save()
                if lines_data is not None:
                    validate_journal_entry(header, lines_data)

            header.refresh_from_db()

            create_audit_log(
                tenant=header.tenant,
                user=self.request.user,
                action='UPDATE',
                model_name='JournalHeader',
                object_id=header.id,
                change_details="Journal entry updated."
            )
            
            response_serializer = JournalHeaderSerializer(header)
            return Response(response_serializer.data)
        except IntegrityError as ie:
            return Response({'error': f"Database Integrity Error: {ie}"}, status=status.HTTP_400_BAD_REQUEST)
        except (ValidationError, DjangoValidationError) as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'error': f"Validation Error: {msg}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected error updating journal %s", instance.pk)
            return Response(
                {'error': 'حدث خطأ غير متوقع أثناء تحديث القيد.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def create(self, request, *args, **kwargs):
        require_perm(request, 'accounting.journal.create')
        tenant = get_tenant(self.request)
        if not tenant:
            return Response({"error": "لا يوجد شركة محددة لهذا الطلب."}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        lines_data = data.get("lines", [])

        mock_hdr = JournalHeader()
        mock_hdr.tenant_id = tenant.TenantID
        mock_hdr.transaction_date = data.get("transaction_date")
        validate_journal_entry(mock_hdr, lines_data)

        try:
            with db_transaction.atomic():
                # A3: صاحب القيد اليدوي — نفس ما يفعله post_journal للقيود الآلية.
                header = serializer.save(tenant=tenant, created_by=self.request.user)

            header.refresh_from_db()

            create_audit_log(
                tenant=header.tenant,
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
        except Exception:
            logger.exception("Unexpected error creating journal entry")
            return Response(
                {'error': 'حدث خطأ غير متوقع أثناء إنشاء القيد.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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

        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = Account.objects.get(pk=account_id, tenant=tenant)
        except Account.DoesNotExist:
            return Response({'error': 'Account not found'}, status=status.HTTP_404_NOT_FOUND)

        # P1-3 (SCALABILITY_AUDIT §2-5): كان التوسّع تعاودياً باستعلامين لكل حساب
        # (أبناء بالـFK ثم أبناء بالكود) ⇒ شجرة من 300 حساب = 600 استعلام قبل أن
        # يبدأ التقرير أصلاً. الشجرة كلها تُجلب الآن باستعلام واحد وتُوسَّع في
        # الذاكرة بنفس الدلالة حرفياً: إغلاق تعاودي على الأب، ولكل عقدة فيه
        # تُضاف الحسابات التي يبدأ كودها بكودها (بلا توسيع هذه الأخيرة).
        all_accounts = list(Account.objects.filter(tenant=tenant))
        children_by_parent = {}
        for acc in all_accounts:
            children_by_parent.setdefault(acc.parent_id, []).append(acc)

        fk_closure = {}
        stack = [account]
        while stack:
            node = stack.pop()
            if node.id in fk_closure:
                continue
            fk_closure[node.id] = node
            stack.extend(children_by_parent.get(node.id, []))

        target_map = dict(fk_closure)
        for node in fk_closure.values():
            if not node.code:
                continue
            for candidate in all_accounts:
                if candidate.id not in target_map and (candidate.code or "").startswith(node.code):
                    target_map[candidate.id] = candidate

        target_accounts = list(target_map.values())

        # 1. Calculate Opening Balance
        # Sum of (Debit - Credit) for all Posted entries before start_date
        from django.db.models import Sum, F, Q

        tenant = get_tenant(request)
        branch_q = _branch_journal_q(request, tenant)
        opening_data = JournalLine.objects.filter(
            account__in=target_accounts,
            journal__is_posted=True,
            journal__transaction_date__lt=start_date,
            **({"tenant": tenant} if tenant else {}),
        ).filter(branch_q).aggregate(
            total_debit=Sum('base_debit'),
            total_credit=Sum('base_credit')
        )

        op_debit = opening_data['total_debit'] or 0
        op_credit = opening_data['total_credit'] or 0
        opening_balance = op_debit - op_credit

        # 2. Fetch Transactions within range
        include_unposted = request.query_params.get('include_unposted') == 'true'

        query_filters = {
            'account__in': target_accounts,
            'journal__transaction_date__range': [start_date, end_date],
        }
        if tenant:
            query_filters['tenant'] = tenant

        if not include_unposted:
            query_filters['journal__is_posted'] = True

        # P1-3: `journal__currency` كان خارج select_related رغم أن كل سطر يقرأ
        # `line.journal.currency.Code` ⇒ استعلام لكل سطر في التقرير.
        transactions = (
            JournalLine.objects.filter(**query_filters)
            .filter(branch_q)
            .select_related('journal', 'journal__currency', 'account')
            .order_by('journal__transaction_date', 'journal__id', 'id')
        )

        # P1-3: التقرير كان بلا أي سقف — دفتر أستاذ حساب الصندوق على سنة كاملة
        # يبني كل أسطره في الذاكرة ويُسلسلها دفعةً واحدة. السقف هنا لا يُخفي شيئاً:
        # `truncated` و`total_count` يُعادان في الاستجابة لتضيّق الواجهة المدى.
        max_rows = 5000
        total_count = transactions.count()
        truncated = total_count > max_rows
        if truncated:
            transactions = transactions[:max_rows]

        # 3. Calculate Running Balance
        results = []
        current_balance = opening_balance

        # Determine nature of account for display purposes (optional, but good for UI)
        # Usually GL shows Debit/Credit/Balance. 
        # If we want a "signed" balance where Dr is positive:
        
        for line in transactions:
            # Use base currency amounts for the running balance
            base_dr = line.base_debit or 0
            base_cr = line.base_credit or 0
            
            current_balance += (base_dr - base_cr)
            
            results.append({
                'id': line.id,
                'date': line.journal.transaction_date,
                'journal_id': line.journal.id,
                'description': line.journal.description or line.account.name, # Fallback
                'ref_type': line.journal.reference_type,
                'ref_id': line.journal.reference_id,
                'debit': base_dr,
                'credit': base_cr,
                'original_debit': line.debit or 0,
                'original_credit': line.credit or 0,
                'currency': line.journal.currency.Code if line.journal.currency_id else None,
                'exchange_rate': float(line.journal.exchange_rate or 1),
                'balance': current_balance
            })

        return Response({
            'account_name': account.name,
            'account_code': account.code,
            'opening_balance': opening_balance,
            'transactions': results,
            'closing_balance': current_balance,
            # P1-3: القصّ معلَن لا صامت — الواجهة تعرض تنبيهاً وتضيّق المدى،
            # والرصيد الختامي أدناه يخصّ الأسطر المُعادة فقط عند القصّ.
            'total_count': total_count,
            'truncated': truncated,
            'max_rows': max_rows,
        })

class TrialBalanceView(viewsets.ViewSet):
    """ميزان مراجعة كامل: افتتاحي + حركة الفترة + ختامي لكل حساب.

    المعاملات:
      - start_date, end_date (YYYY-MM-DD) — اختيارية؛ افتراض: السنة الحالية.
      - include_unposted (bool) — تضمين قيود غير مرحّلة (افتراض: false).
      - show_all (bool) — إظهار حسابات بدون حركة (افتراض: true).

    الاستجابة:
      {
        "start_date": "...", "end_date": "...",
        "rows": [{id, code, name, account_type,
                   opening_debit, opening_credit, opening_balance,
                   period_debit, period_credit,
                   closing_debit, closing_credit, closing_balance}],
        "totals": {period_debit, period_credit,
                   closing_debit, closing_credit,
                   balanced: bool, difference}
      }

    ملاحظة: الرصيد الختامي = الرصيد الافتتاحي + حركة الفترة. يُعرض في عمودين
    (مدين/دائن) بحسب الطبيعة — الموجب للمدينية والسالب للدائنية.
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def list(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        include_unposted = request.query_params.get('include_unposted') == 'true'
        show_all = request.query_params.get('show_all', 'true') == 'true'

        if not all([start_date, end_date]):
            today = timezone.localdate()
            start_date = f"{today.year}-01-01"
            end_date = f"{today.year}-12-31"

        from django.db.models import Sum

        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # --- 1) الرصيد الافتتاحي = مجموع الحركات قبل start_date
            opening_filters = {
                'tenant': tenant,
                'journal__transaction_date__lt': start_date,
            }
            if not include_unposted:
                opening_filters['journal__is_posted'] = True

            branch_q = _branch_journal_q(request, tenant)
            opening_qs = (
                JournalLine.objects
                .filter(**opening_filters)
                .filter(branch_q)
                .values('account_id')
                .annotate(dr=Sum('base_debit'), cr=Sum('base_credit'))
            )
            opening = {
                r['account_id']: (
                    float(r['dr'] or 0),
                    float(r['cr'] or 0),
                )
                for r in opening_qs
            }

            # --- 2) حركة الفترة
            period_filters = {
                'tenant': tenant,
                'journal__transaction_date__range': [start_date, end_date],
            }
            if not include_unposted:
                period_filters['journal__is_posted'] = True

            period_qs = (
                JournalLine.objects
                .filter(**period_filters)
                .filter(branch_q)
                .values('account_id')
                .annotate(dr=Sum('base_debit'), cr=Sum('base_credit'))
            )
            period = {
                r['account_id']: (
                    float(r['dr'] or 0),
                    float(r['cr'] or 0),
                )
                for r in period_qs
            }

            # --- 3) دمج مع كل الحسابات
            accounts = (
                Account.objects
                .filter(tenant=tenant, is_active=True)
                .order_by('code')
            )

            rows = []
            tot_pd = 0.0
            tot_pc = 0.0
            tot_cd = 0.0
            tot_cc = 0.0

            for a in accounts:
                op_dr, op_cr = opening.get(a.id, (0.0, 0.0))
                pd, pc = period.get(a.id, (0.0, 0.0))

                opening_balance = round(op_dr - op_cr, 2)
                period_debit = round(pd, 2)
                period_credit = round(pc, 2)
                closing_net = round(opening_balance + period_debit - period_credit, 2)

                # اعرض فقط العمود المناسب للطبيعة
                opening_debit = opening_balance if opening_balance >= 0 else 0.0
                opening_credit = -opening_balance if opening_balance < 0 else 0.0
                closing_debit = closing_net if closing_net >= 0 else 0.0
                closing_credit = -closing_net if closing_net < 0 else 0.0

                has_activity = bool(op_dr or op_cr or pd or pc)
                if not show_all and not has_activity:
                    continue

                rows.append({
                    'id': a.id,
                    'code': a.code,
                    'name': a.name,
                    'account_type': a.account_type,
                    'opening_debit': round(opening_debit, 2),
                    'opening_credit': round(opening_credit, 2),
                    'opening_balance': opening_balance,
                    'period_debit': period_debit,
                    'period_credit': period_credit,
                    'closing_debit': round(closing_debit, 2),
                    'closing_credit': round(closing_credit, 2),
                    'closing_balance': closing_net,
                })

                tot_pd += period_debit
                tot_pc += period_credit
                tot_cd += closing_debit
                tot_cc += closing_credit

            tot_pd = round(tot_pd, 2)
            tot_pc = round(tot_pc, 2)
            tot_cd = round(tot_cd, 2)
            tot_cc = round(tot_cc, 2)

            totals = {
                'period_debit': tot_pd,
                'period_credit': tot_pc,
                'closing_debit': tot_cd,
                'closing_credit': tot_cc,
                'balanced': abs(tot_pd - tot_pc) < 0.02 and abs(tot_cd - tot_cc) < 0.02,
                'period_difference': round(tot_pd - tot_pc, 2),
                'closing_difference': round(tot_cd - tot_cc, 2),
            }

            return Response({
                'start_date': start_date,
                'end_date': end_date,
                'rows': rows,
                'totals': totals,
            })
        except Exception as e:
            logger.exception("trial-balance report failed")
            return Response({'error': str(e)}, status=500)


class VatReportView(viewsets.ViewSet):
    """تقرير ضريبة القيمة المضافة: مدخلات مقابل مخرجات مع الصافي المستحق.

    يبحث عن حسابات ضريبة:
      - Input (مدخلات): code=1105 أو account_type=Asset واسم يحتوي "ضريبة"
      - Output (مخرجات): code=2104 أو account_type=Liability واسم يحتوي "ضريبة"

    ويجمع حركات JournalLine داخل الفترة لكل نوع.

    الاستجابة:
      {
        "start_date", "end_date",
        "input": {account_id, code, name, total_debit, total_credit, balance, lines_count},
        "output": {...},
        "net_payable": output_balance - input_balance,   // موجب = مستحق للحكومة
        "input_lines": [{date, journal_id, description, debit, credit, partner}],
        "output_lines": [...]
      }
    """

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]

    def list(self, request):
        from django.db.models import Sum, Q as QQ

        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر.'}, status=status.HTTP_400_BAD_REQUEST)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        include_unposted = request.query_params.get('include_unposted') == 'true'
        if not all([start_date, end_date]):
            today = timezone.localdate()
            start_date = f"{today.year}-01-01"
            end_date = f"{today.year}-12-31"

        def _find_accounts(code, acc_type, name_contains):
            q = Account.objects.filter(tenant=tenant, is_active=True)
            # 1) أولوية للكود
            by_code = q.filter(code=code)
            if by_code.exists():
                return list(by_code)
            # 2) fallback بالنوع والاسم
            return list(q.filter(account_type=acc_type).filter(
                QQ(name__icontains=name_contains) | QQ(name__icontains='VAT')
            ))

        input_accounts = _find_accounts('1105', 'Asset', 'ضريبة')
        output_accounts = _find_accounts('2104', 'Liability', 'ضريبة')

        line_filters = {
            'tenant': tenant,
            'journal__transaction_date__range': [start_date, end_date],
        }
        if not include_unposted:
            line_filters['journal__is_posted'] = True

        def _summarize(accounts):
            if not accounts:
                return {
                    'accounts': [],
                    'total_debit': 0.0,
                    'total_credit': 0.0,
                    'balance': 0.0,
                    'lines_count': 0,
                }
            ids = [a.id for a in accounts]
            agg = (
                JournalLine.objects
                .filter(account_id__in=ids, **line_filters)
                .aggregate(dr=Sum('base_debit'), cr=Sum('base_credit'))
            )
            dr = float(agg['dr'] or 0)
            cr = float(agg['cr'] or 0)
            return {
                'accounts': [
                    {'id': a.id, 'code': a.code, 'name': a.name, 'type': a.account_type}
                    for a in accounts
                ],
                'total_debit': round(dr, 2),
                'total_credit': round(cr, 2),
                'balance': round(dr - cr, 2),
            }

        def _lines(accounts):
            if not accounts:
                return []
            ids = [a.id for a in accounts]
            rows = (
                JournalLine.objects
                .filter(account_id__in=ids, **line_filters)
                .select_related('journal', 'partner', 'account')
                .order_by('journal__transaction_date', 'journal_id', 'id')
            )
            out = []
            for r in rows:
                out.append({
                    'date': r.journal.transaction_date.isoformat() if r.journal and r.journal.transaction_date else None,
                    'journal_id': r.journal_id,
                    'reference_type': getattr(r.journal, 'reference_type', None),
                    'reference_id': getattr(r.journal, 'reference_id', None),
                    'account_code': r.account.code if r.account else None,
                    'description': r.description or (getattr(r.journal, 'description', '') or ''),
                    'debit': float(r.base_debit or 0),
                    'credit': float(r.base_credit or 0),
                    'partner': r.partner.name if r.partner else None,
                })
            return out

        input_summary = _summarize(input_accounts)
        output_summary = _summarize(output_accounts)

        # Input VAT: طبيعتها مدينة — الرصيد = Debit - Credit (موجب)
        # Output VAT: طبيعتها دائنة — الرصيد المستحق للدولة = Credit - Debit
        input_balance = input_summary['balance']
        output_balance_payable = round(-output_summary['balance'], 2)
        # net = output المستحق - input (لأن المدخلات تُطرح من المخرجات)
        net_payable = round(output_balance_payable - input_balance, 2)

        return Response({
            'start_date': start_date,
            'end_date': end_date,
            'input': input_summary,
            'output': {
                **output_summary,
                'balance_payable': output_balance_payable,
            },
            'net_payable': net_payable,
            'input_lines': _lines(input_accounts),
            'output_lines': _lines(output_accounts),
        })


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
                    # THA-111: صندوقٌ بحكم إنشائه — التصنيف يُكتب هنا فلا يحتاج
                    # الصندوق الجديد اشتقاقاً لاحقاً من رمزه أو اسمه.
                    sub_type=SUB_TYPE_CASH_BOX,
                )
                link = CashBoxLedgerAccount.objects.create(
                    tenant=tenant,
                    external_id=external_id[:128],
                    name=name[:200],
                    currency_code=currency,
                    account=acc,
                )
        except IntegrityError as ie:
            return Response({"error": f"Database Integrity Error: {ie}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("cash box ledger create failed")
            return Response({"error": "حدث خطأ غير متوقع أثناء إنشاء حساب الصندوق."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

    # ── صندوق العملة الأجنبية: تمويل FIFO + الرصيد (صندوق الدولار) ──
    @staticmethod
    def _fx_date(raw):
        try:
            return datetime.date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            return timezone.localdate()

    @action(detail=True, methods=["get"], url_path="fx-lots")
    def fx_lots(self, request, pk=None):
        """طبقات FIFO + الرصيد بالعملة الأجنبية وقيمته بالشيقل."""
        from .fx_fifo import box_fc_balance, box_ils_value
        box = self.get_object()
        lots = box.fx_lots.all().order_by("lot_date", "id")
        return Response({
            "currency_code": box.currency_code,
            "fc_balance": str(box_fc_balance(box)),
            "ils_value": str(box_ils_value(box)),
            "lots": [{
                "id": l.id, "lot_date": l.lot_date,
                "original_fc": str(l.original_fc), "remaining_fc": str(l.remaining_fc),
                "rate": str(l.rate), "source": l.source, "journal": l.journal_id,
            } for l in lots],
        })

    @action(detail=True, methods=["post"], url_path="fund-capital")
    @requires_perm("finance.cashbox.manage")
    def fund_capital(self, request, pk=None):
        """إيداع عملة أجنبية من رأس المال — ينشئ طبقة FIFO + قيد."""
        from django.core.exceptions import ValidationError as DjangoValidationError
        from .fx_fifo import fund_box_from_capital
        box = self.get_object()
        try:
            lot = fund_box_from_capital(
                box, request.data.get("amount"), request.data.get("rate"),
                date=self._fx_date(request.data.get("date")), user=request.user)
        except DjangoValidationError as e:
            return Response({"error": "; ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"lot_id": lot.id, "remaining_fc": str(lot.remaining_fc), "rate": str(lot.rate)},
            status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="transfer-from-ils")
    @requires_perm("finance.cashbox.manage")
    def transfer_from_ils(self, request, pk=None):
        """تحويل من صندوق الشيقل لصندوق العملة الأجنبية بسعر صرف — ينشئ طبقة FIFO + قيد."""
        from django.core.exceptions import ValidationError as DjangoValidationError
        from .fx_fifo import transfer_ils_to_fx
        box = self.get_object()
        ils_box = CashBoxLedgerAccount.objects.filter(
            tenant=box.tenant, id=request.data.get("ils_box_id")).first()
        if not ils_box:
            return Response({"error": "صندوق الشيقل المصدر غير موجود."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            lot = transfer_ils_to_fx(
                box, ils_box, request.data.get("amount"), request.data.get("rate"),
                date=self._fx_date(request.data.get("date")), user=request.user)
        except DjangoValidationError as e:
            return Response({"error": "; ".join(e.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"lot_id": lot.id, "remaining_fc": str(lot.remaining_fc), "rate": str(lot.rate)},
            status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="deposit-journal")
    @requires_perm("finance.cashbox.manage")
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
                else timezone.localdate()
            )
        except ValueError:
            td = timezone.localdate()

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

        lines_data = [
            {"account": cash_link.account_id, "debit": amount, "credit": Decimal("0"), "description": line_cash[:500]},
            {"account": capital.id, "debit": Decimal("0"), "credit": amount, "description": line_cap},
        ]

        try:
            j = post_journal(
                tenant_id=tenant.TenantID,
                transaction_date=td,
                reference_type="CASHBOX_FIRESTORE_DEPOSIT",
                reference_id=None,
                description=jdesc,
                lines_data=lines_data,
                user=request.user,
                idempotent=False,
            )
        except DjangoValidationError as ve:
            msg = ve.message if hasattr(ve, "message") else str(ve)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as ie:
            return Response({"error": f"Database Integrity Error: {ie}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("cash box deposit journal failed")
            return Response({"error": "حدث خطأ غير متوقع أثناء إنشاء قيد الإيداع."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    قيد استلام البضاعة (نسخة بسيطة من ترحيل فاتورة شراء):
        مدين: مخزون (1104)           = amount - tax_amount
        مدين: ضريبة مدخلات (1105)   = tax_amount (اختياري)
        دائن: ذمم المورد             = amount

    جسم الطلب:
        {
            "partner_id": 123,
            "amount": 1000,                # إجمالي (يشمل الضريبة إن وُجدت)
            "tax_amount": 160,             # اختياري — ضريبة مدخلات (≥ 0)
            "description": "...",
            "invoice_reference": 45,       # اختياري
            "transaction_date": "2026-04-19"
        }
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

        try:
            tax_amount = Decimal(str(request.data.get("tax_amount") or 0))
        except (InvalidOperation, TypeError, ValueError):
            return Response({"error": "tax_amount غير صالح"}, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({"error": "المبلغ يجب أن يكون موجباً"}, status=status.HTTP_400_BAD_REQUEST)
        if tax_amount < 0:
            return Response({"error": "ضريبة المدخلات لا يمكن أن تكون سالبة"}, status=status.HTTP_400_BAD_REQUEST)
        if tax_amount > amount:
            return Response({"error": "ضريبة المدخلات أكبر من الإجمالي"}, status=status.HTTP_400_BAD_REQUEST)

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

        # حساب المخزون — أولوية 1104 ثم مخزون بالاسم ثم مشتريات
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
                {"error": "لم يُعثر على حساب المخزون (1104). شغّل seed_professional_coa أولاً."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # حساب ضريبة المدخلات — مطلوب إن كانت الضريبة > 0
        vat_input_account = None
        if tax_amount > 0:
            vat_input_account = (
                Account.objects.filter(tenant=tenant, code="1105").first()
                or Account.objects.filter(
                    tenant=tenant, account_type="Asset",
                    name__icontains="ضريبة",
                ).first()
            )
            if not vat_input_account or vat_input_account.account_type != 'Asset':
                return Response(
                    {"error": "ضريبة المدخلات > 0 تتطلب حساب '1105 VAT Input' من نوع Asset."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        raw_td = request.data.get("transaction_date")
        if raw_td:
            try:
                td = datetime.datetime.fromisoformat(str(raw_td).replace("Z", "+00:00")).date()
            except ValueError:
                td = timezone.localdate()
        else:
            td = timezone.localdate()

        ref_note = f" | مرجع فاتورة: {invoice_ref}" if invoice_ref else ""
        ref_id = None
        if invoice_ref is not None and str(invoice_ref).strip().isdigit():
            ref_id = int(str(invoice_ref).strip())

        net_amount = amount - tax_amount
        computed_vat_from_lines = Decimal('0')
        vat_lines = []
        if ref_id and tax_amount > 0:
            try:
                from logistics.models import PurchaseInvoice as PI
                pi = PI.objects.prefetch_related('items').get(pk=ref_id)
                items = list(pi.items.all())
                if items and any(getattr(it, 'vat_percent', None) for it in items):
                    for it in items:
                        vp = getattr(it, 'vat_percent', None)
                        if vp:
                            try:
                                line_vat = (Decimal(str(it.quantity or 0)) * Decimal(str(it.unit_price or 0)) * Decimal(str(vp)) / Decimal('100')).quantize(Decimal('0.01'))
                            except Exception:
                                line_vat = Decimal('0')
                            if line_vat > 0:
                                vat_lines.append(('vat_input', line_vat, vp))
                                computed_vat_from_lines += line_vat
                    if computed_vat_from_lines > 0:
                        tax_amount = computed_vat_from_lines
                        net_amount = amount - tax_amount
            except PI.DoesNotExist:
                pass
            except Exception:
                pass

        lines_payload = [
            {'account': inventory_account.id, 'debit': net_amount, 'credit': Decimal('0'), 'partner': partner.id},
        ]
        if tax_amount > 0:
            if vat_lines:
                for vtype, vamt, vpct in vat_lines:
                    lines_payload.append({
                        'account': vat_input_account.id, 'debit': vamt, 'credit': Decimal('0'), 'partner': partner.id,
                    })
            else:
                lines_payload.append({
                    'account': vat_input_account.id, 'debit': tax_amount, 'credit': Decimal('0'), 'partner': partner.id,
                })
        lines_payload.append({
            'account': partner.linked_account.id, 'debit': Decimal('0'), 'credit': amount, 'partner': partner.id,
        })

        try:
            j = post_journal(
                tenant_id=tenant.TenantID,
                transaction_date=td,
                reference_type="PURCHASE_RECEIPT",
                reference_id=ref_id,
                description=f"{description}{ref_note} | {partner.name}"[:500],
                lines_data=lines_payload,
                user=request.user,
            )
        except DjangoValidationError as ve:
            msg = ve.message if hasattr(ve, "message") else str(ve)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as ie:
            return Response({"error": f"Database Integrity Error: {ie}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("purchase receipt post failed")
            return Response({"error": "حدث خطأ غير متوقع أثناء إنشاء قيد الاستلام."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"journal_id": j.id, "net_amount": str(net_amount), "tax_amount": str(tax_amount)}, status=status.HTTP_201_CREATED)


class BankViewSet(viewsets.ModelViewSet):
    """T-BANKS: بنوك الشركة — مظلّة الفروع والحسابات."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Bank.objects.all().prefetch_related('branches', 'accounts')
    serializer_class = BankSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return Bank.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        if str(self.request.query_params.get('active_only', '')).lower() in ('1', 'true'):
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        require_perm(self.request, 'accounting.account.manage')
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)

    def perform_update(self, serializer):
        require_perm(self.request, 'accounting.account.manage')
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request, 'accounting.account.manage')
        if instance.accounts.exists():
            raise ValidationError(
                {"detail": "لا يمكن حذف بنك له حسابات — عطّله بدل حذفه."})
        instance.delete()


class BankBranchViewSet(viewsets.ModelViewSet):
    """فروع البنوك — تُفلتر بـ ?bank=<id>."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = BankBranch.objects.all().select_related('bank')
    serializer_class = BankBranchSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return BankBranch.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        bank_id = self.request.query_params.get('bank')
        if bank_id:
            qs = qs.filter(bank_id=bank_id)
        return qs

    def perform_create(self, serializer):
        require_perm(self.request, 'accounting.account.manage')
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        bank = serializer.validated_data.get('bank')
        if bank is None or bank.tenant_id != tenant.TenantID:
            raise ValidationError({"bank": "البنك غير موجود في هذه الشركة."})
        serializer.save(tenant=tenant)

    def perform_update(self, serializer):
        require_perm(self.request, 'accounting.account.manage')
        serializer.save()

    def perform_destroy(self, instance):
        require_perm(self.request, 'accounting.account.manage')
        if instance.accounts.exists():
            raise ValidationError(
                {"detail": "لا يمكن حذف فرع مرتبط بحسابات بنكية — عطّله بدل حذفه."})
        instance.delete()


class BankAccountViewSet(viewsets.ModelViewSet):
    """حسابات الشركة البنكية — لكل حساب عملته وحسابه في الشجرة (يُنشأ تلقائياً)."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = BankAccount.objects.all().select_related('bank', 'branch', 'currency', 'account')
    serializer_class = BankAccountSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return BankAccount.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        bank_id = self.request.query_params.get('bank')
        if bank_id:
            qs = qs.filter(bank_id=bank_id)
        if str(self.request.query_params.get('active_only', '')).lower() in ('1', 'true'):
            qs = qs.filter(is_active=True)
        return qs

    def create(self, request, *args, **kwargs):
        require_perm(request, 'accounting.account.manage')
        tenant = get_tenant(request)
        if not tenant:
            return Response({"error": "لا يوجد شركة محددة لهذا الطلب."},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        bank = data.get('bank')
        if bank is None or bank.tenant_id != tenant.TenantID:
            raise ValidationError({"bank": "البنك غير موجود في هذه الشركة."})
        branch = data.get('branch')
        if branch is not None and branch.bank_id != bank.pk:
            raise ValidationError({"branch": "الفرع لا يتبع البنك المحدد."})
        try:
            ba = create_bank_account(
                tenant=tenant, bank=bank, name=data.get('name'),
                currency=data.get('currency'), branch=branch,
                account_number=data.get('account_number'), iban=data.get('iban'),
                is_default=data.get('is_default', False), notes=data.get('notes'),
                user=request.user,
            )
        except DjangoValidationError as e:
            raise ValidationError({"detail": e.messages if hasattr(e, 'messages') else str(e)})
        create_audit_log(
            tenant=tenant, user=request.user, action="CREATE",
            model_name="BankAccount", object_id=ba.pk,
            change_details=f"حساب بنكي {ba.name} → حساب {ba.account.code}",
        )
        return Response(self.get_serializer(ba).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        require_perm(self.request, 'accounting.account.manage')
        tenant = get_tenant(self.request)
        instance = serializer.instance
        if serializer.validated_data.get('is_default'):
            BankAccount.objects.filter(tenant=tenant, is_default=True).exclude(
                pk=instance.pk).update(is_default=False)
        ba = serializer.save()
        # اسم الحساب في الشجرة يتبع تسمية الحساب البنكي.
        new_name = f"{ba.bank.name} — {ba.name}"[:100]
        if ba.account_id and ba.account.name != new_name:
            Account.objects.filter(pk=ba.account_id).update(name=new_name)

    def perform_destroy(self, instance):
        require_perm(self.request, 'accounting.account.manage')
        if JournalLine.objects.filter(account_id=instance.account_id).exists():
            raise ValidationError(
                {"detail": "لا يمكن حذف حساب بنكي عليه حركة محاسبية — عطّله بدل حذفه."})
        gl_id = instance.account_id
        instance.delete()
        Account.objects.filter(pk=gl_id).delete()

    @action(detail=True, methods=['get'], url_path='statement')
    def statement(self, request, pk=None):
        """كشف حركة الحساب البنكي من الدفاتر مع حالة المطابقة لكل سطر."""
        require_perm(request, 'accounting.report.view')
        ba = self.get_object()
        data = bank_account_statement(
            ba,
            start_date=request.query_params.get('start_date') or None,
            end_date=request.query_params.get('end_date') or None,
        )
        return Response({
            "bank_account": self.get_serializer(ba).data,
            **data,
        })


class BankReconciliationViewSet(viewsets.ModelViewSet):
    """المطابقة البنكية: كشف البنك مقابل الدفاتر حتى تاريخ."""

    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = BankReconciliation.objects.all().select_related(
        'bank_account', 'bank_account__bank', 'bank_account__currency')
    serializer_class = BankReconciliationSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return BankReconciliation.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        ba = self.request.query_params.get('bank_account')
        if ba:
            qs = qs.filter(bank_account_id=ba)
        return qs

    def perform_create(self, serializer):
        require_perm(self.request, 'accounting.journal.create')
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        ba = serializer.validated_data.get('bank_account')
        if ba is None or ba.tenant_id != tenant.TenantID:
            raise ValidationError({"bank_account": "الحساب البنكي غير موجود في هذه الشركة."})
        if BankReconciliation.objects.filter(
            tenant=tenant, bank_account=ba, status=BankReconciliation.STATUS_OPEN,
        ).exists():
            raise ValidationError(
                {"detail": "توجد مطابقة مفتوحة لهذا الحساب — أقفلها أو احذفها أولاً."})
        serializer.save(tenant=tenant, created_by=self.request.user)

    def perform_destroy(self, instance):
        require_perm(self.request, 'accounting.journal.create')
        if instance.status == BankReconciliation.STATUS_CLOSED:
            raise ValidationError({"detail": "المطابقة مُقفلة — أعِد فتحها قبل الحذف."})
        instance.delete()

    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        rec = self.get_object()
        data = bank_reconciliation_summary(rec)
        return Response({**self.get_serializer(rec).data, **data})

    @action(detail=True, methods=['post'], url_path='toggle-line')
    def toggle_line(self, request, pk=None):
        """تأشير/إلغاء تأشير سطر دفاتر بأنه ظهر في كشف البنك."""
        require_perm(request, 'accounting.journal.create')
        rec = self.get_object()
        if rec.status == BankReconciliation.STATUS_CLOSED:
            raise ValidationError({"detail": "المطابقة مُقفلة — لا يمكن تعديل أسطرها."})
        line_id = request.data.get('journal_line')
        cleared = bool(request.data.get('cleared', True))
        line = JournalLine.objects.filter(
            pk=line_id, tenant_id=rec.tenant_id, account_id=rec.bank_account.account_id,
        ).first()
        if line is None:
            raise ValidationError({"journal_line": "السطر غير موجود في حركة هذا الحساب البنكي."})
        if cleared:
            existing = BankReconciliationLine.objects.filter(journal_line=line).first()
            if existing and existing.reconciliation_id != rec.pk:
                raise ValidationError(
                    {"detail": f"السطر مطابَق مسبقاً في مطابقة #{existing.reconciliation_id}."})
            if not existing:
                BankReconciliationLine.objects.create(reconciliation=rec, journal_line=line)
        else:
            BankReconciliationLine.objects.filter(reconciliation=rec, journal_line=line).delete()
        return Response(bank_reconciliation_summary(rec))

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        require_perm(request, 'accounting.journal.post')
        rec = self.get_object()
        try:
            close_bank_reconciliation(rec, user=request.user)
        except DjangoValidationError as e:
            raise ValidationError({"detail": e.messages if hasattr(e, 'messages') else str(e)})
        return Response(bank_reconciliation_summary(rec))

    @action(detail=True, methods=['post'], url_path='reopen')
    def reopen(self, request, pk=None):
        require_perm(request, 'accounting.journal.unpost')
        rec = self.get_object()
        if rec.status == BankReconciliation.STATUS_OPEN:
            return Response(bank_reconciliation_summary(rec))
        rec.status = BankReconciliation.STATUS_OPEN
        rec.closed_at = None
        rec.save(update_fields=['status', 'closed_at'])
        create_audit_log(
            tenant=rec.tenant, user=request.user, action="UPDATE",
            model_name="BankReconciliation", object_id=rec.pk,
            change_details="إعادة فتح المطابقة البنكية",
        )
        return Response(bank_reconciliation_summary(rec))


class ExchangeRateViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = ExchangeRate.objects.all().select_related('from_currency', 'to_currency')
    serializer_class = ExchangeRateSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return ExchangeRate.objects.none()
        qs = super().get_queryset().filter(tenant=tenant).order_by('-effective_date')
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
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)

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
        tenant = get_tenant(request)
        rate_obj = (
            ExchangeRate.objects
            .filter(from_currency_id=fc, to_currency_id=tc, effective_date__lte=date)
            if tenant is None
            else ExchangeRate.objects.filter(
                tenant=tenant, from_currency_id=fc, to_currency_id=tc, effective_date__lte=date,
            )
        ).order_by('-effective_date').first()
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

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if tenant:
            return FiscalPeriod.objects.filter(tenant=tenant).order_by('-start_date')
        return FiscalPeriod.objects.none()

    def perform_create(self, serializer):
        # THA-197: مسارات CRUD كانت مفتوحة لأي عضو بينما `close/` و`reopen/`
        # محميّتان — فكان القفل يُلتفّ حوله بـPATCH أو DELETE عاديّين.
        require_perm(self.request, 'accounting.period.manage')
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        # THA-185: الفترات لا تتقاطع — الحارس هنا يغطّي الـPOST المباشر، ونظيره
        # داخل `create_fiscal_year` يغطّي إجراء «إنشاء سنة».
        self._guard_overlap(
            tenant, serializer.validated_data['start_date'],
            serializer.validated_data['end_date'],
        )
        serializer.save(tenant=tenant)

    def perform_update(self, serializer):
        require_perm(self.request, 'accounting.period.manage')
        period = serializer.instance
        # THA-197: الفترة المُقفَلة لا تُعدَّل إطلاقاً عبر التحديث — لا حالتها ولا
        # حدودها؛ تحريك `start_date`/`end_date` يفتح أياماً داخل شهر مُقفَل بلا
        # سبب مسجَّل. `reopen/` هو المسار المُعلَن الوحيد.
        if period.is_closed:
            raise ValidationError(
                {"error": "الفترة مغلقة — أعد فتحها بسبب مسجَّل قبل تعديلها."}
            )
        self._guard_overlap(
            period.tenant,
            serializer.validated_data.get('start_date', period.start_date),
            serializer.validated_data.get('end_date', period.end_date),
            exclude_pk=period.pk,
        )
        changed = ", ".join(sorted(serializer.validated_data.keys())) or "—"
        period = serializer.save()
        create_audit_log(
            tenant=period.tenant,
            user=self.request.user,
            action='UPDATE',
            model_name='FiscalPeriod',
            object_id=period.id,
            change_details=f"Period {period.name} updated (fields: {changed})",
        )

    def perform_destroy(self, instance):
        require_perm(self.request, 'accounting.period.manage')
        # THA-197: الحذف ثم إعادة الإنشاء مفتوحاً = إعادة فتح بلا سبب ولا سجل،
        # وواقعة الإقفال نفسها تضيع.
        if instance.is_closed:
            raise ValidationError(
                {"error": "لا يمكن حذف فترة مغلقة — أعد فتحها بسبب مسجَّل أولاً."}
            )
        # وحذف فترة عليها قيود مرحّلة لا يفتح ثغرة بل يشلّ المدى: تواريخ بلا فترة
        # تغطّيها يرفضها الترحيل وإلغاء الترحيل معاً (`validate_fiscal_period`).
        if JournalHeader.objects.filter(
            tenant=instance.tenant,
            transaction_date__gte=instance.start_date,
            transaction_date__lte=instance.end_date,
            is_posted=True,
        ).exists():
            raise ValidationError(
                {"error": (
                    f"لا يمكن حذف الفترة «{instance.name}» — توجد قيود مرحّلة "
                    f"مؤرَّخة داخلها."
                )}
            )
        tenant, period_id, name = instance.tenant, instance.id, instance.name
        instance.delete()
        create_audit_log(
            tenant=tenant,
            user=self.request.user,
            action='DELETE',
            model_name='FiscalPeriod',
            object_id=period_id,
            change_details=f"Period {name} deleted (open, no posted journals)",
        )

    @staticmethod
    def _guard_overlap(tenant, start_date, end_date, exclude_pk=None):
        try:
            assert_no_period_overlap(tenant.pk, start_date, end_date, exclude_pk=exclude_pk)
        except DjangoValidationError as exc:
            raise ValidationError({"error": exc.messages})

    @action(detail=False, methods=['post'], url_path='create-year')
    @requires_perm('accounting.period.manage')
    def create_year(self, request):
        year = request.data.get('year')
        if not year:
            return Response({'error': 'year مطلوب'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            year = int(year)
        except (TypeError, ValueError):
            return Response({'error': 'year يجب أن يكون رقماً'}, status=status.HTTP_400_BAD_REQUEST)
        granularity = request.data.get('granularity') or GRANULARITY_MONTHLY
        tenant = get_tenant(self.request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            periods = create_fiscal_year(tenant, year, granularity=granularity)
        except DjangoValidationError as exc:
            return Response({'error': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            FiscalPeriodSerializer(periods, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='close')
    @requires_perm('accounting.period.manage')
    def close_period(self, request, pk=None):
        period = self.get_object()
        if period.is_closed:
            return Response({'error': 'الفترة مغلقة مسبقاً'}, status=status.HTTP_400_BAD_REQUEST)
        # A2: مسوّدة داخل الفترة تعني رقماً لم يدخل الدفاتر بعد؛ إغلاقها يدفنه.
        # كان تحذيراً في جسم الرد لا يوقف شيئاً — صار حاجزاً يُتجاوَز عمداً
        # بـ force، والتجاوز يُكتب في سجل التدقيق.
        unposted_count = JournalHeader.objects.filter(
            tenant=period.tenant,
            transaction_date__gte=period.start_date,
            transaction_date__lte=period.end_date,
            is_posted=False,
        ).count()
        forced = str(request.data.get('force', '')).lower() in ('true', '1', 'yes')
        if unposted_count > 0 and not forced:
            return Response(
                {
                    'error': (
                        f"يوجد {unposted_count} قيد غير مرحّل في الفترة «{period.name}». "
                        f"رحّلها أو احذفها قبل الإغلاق، أو أغلق رغم ذلك."
                    ),
                    'unposted_count': unposted_count,
                    'requires_force': True,
                },
                status=status.HTTP_409_CONFLICT,
            )
        period.status = 'Closed'
        period.is_closed = True
        period.save(update_fields=['status', 'is_closed'])
        create_audit_log(
            tenant=period.tenant,
            user=request.user,
            action='POST',
            model_name='FiscalPeriod',
            object_id=period.id,
            change_details=(
                f"Period {period.name} closed"
                + (f" (FORCED over {unposted_count} unposted journal(s))" if forced and unposted_count
                   else " (no unposted journals)")
            ),
        )
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=True, methods=['post'], url_path='reopen')
    @requires_perm('accounting.period.manage')
    def reopen_period(self, request, pk=None):
        period = self.get_object()
        if not period.is_closed:
            return Response({'error': 'الفترة مفتوحة أصلاً'}, status=status.HTTP_400_BAD_REQUEST)
        # A2: «صلاحية استثناء مسجَّلة» — إعادة الفتح هي المسار المُعلَن الوحيد
        # للتعديل داخل شهر مُقفَل، فلا تمرّ بلا سبب مكتوب يُحفظ في سجل التدقيق.
        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {'error': 'سبب إعادة الفتح مطلوب — يُحفظ في سجل التدقيق.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        period.status = 'Open'
        period.is_closed = False
        period.save(update_fields=['status', 'is_closed'])
        create_audit_log(
            tenant=period.tenant,
            user=request.user,
            action='UPDATE',
            model_name='FiscalPeriod',
            object_id=period.id,
            change_details=f"Period {period.name} reopened — السبب: {reason[:400]}",
        )
        return Response(FiscalPeriodSerializer(period).data)

    @action(detail=False, methods=['post'], url_path='year-end-close')
    @requires_perm('accounting.period.manage')
    def year_end_close_action(self, request):
        """إغلاق سنوي: ترحيل صافي P&L إلى أرباح محتجزة."""
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'لا يوجد مستأجر'}, status=status.HTTP_400_BAD_REQUEST)

        year = request.data.get('year')
        retained_earnings_account = request.data.get('retained_earnings_account_id')
        if not year or not retained_earnings_account:
            return Response(
                {'error': 'year و retained_earnings_account_id مطلوبان'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            year = int(year)
        except (TypeError, ValueError):
            return Response({'error': 'year يجب أن يكون رقماً'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = year_end_close(
                tenant_id=tenant.TenantID,
                fiscal_year=year,
                retained_earnings_account_id=int(retained_earnings_account),
                user=request.user,
            )
        except DjangoValidationError as ve:
            msg = ve.message if hasattr(ve, 'message') else str(ve)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("year_end_close failed")
            return Response({'error': 'حدث خطأ غير متوقع أثناء الإغلاق السنوي.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(result)


class TaxRateViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = TaxRate.objects.all().select_related("tax_account")
    serializer_class = TaxRateSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return TaxRate.objects.none()
        return (
            super().get_queryset()
            .filter(tenant_id=tenant.TenantID, is_active=True)
            .order_by("code", "id")
        )

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({"error": "لا يوجد شركة محددة لهذا الطلب."})
        serializer.save(tenant=tenant)


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    """قراءة فقط — قائمة العملات للقوائم المنسدلة؛ لا تحتوي على أسرار."""
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = [AllowAny]
    queryset = Currency.objects.all().order_by('-IsBaseCurrency', 'Code')

    class CurrencySerializer(drf_serializers.ModelSerializer):
        class Meta:
            model = Currency
            fields = ['CurrencyID', 'Code', 'Name', 'Symbol', 'IsBaseCurrency']

    serializer_class = CurrencySerializer
