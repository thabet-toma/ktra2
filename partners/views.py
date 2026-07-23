import json
import logging

from django.core.files.storage import default_storage
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.tenant_utils import get_tenant
from tenants.models import Tenant
from .models import CustomerNote, Partner, PartnerBankAccount
from .serializers import CustomerNoteSerializer, PartnerListSerializer, PartnerSerializer

logger = logging.getLogger(__name__)


class PartnerViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Partner.objects.all().order_by('-created_at')
    serializer_class = PartnerSerializer
    search_fields = ['name', 'legal_name', 'email', 'phone', 'tax_number']

    def get_serializer_class(self):
        if self.action in {"list", "lookup"}:
            return PartnerListSerializer
        return PartnerSerializer

    def _get_tenant(self):
        return get_tenant(self.request)

    @action(detail=True, methods=["get"], url_path="balance")
    def balance(self, request, pk=None):
        """task18 DEF-C1: رصيد الشريك الحالي من القيود المرحَّلة + الرصيد المتوقع
        بعد عملية مقترحة (?proposed_total=). للعميل: مدين−دائن؛ للمورد: دائن−مدين.
        تُمكِّن شاشتي البيع/الشراء من عرض «الرصيد قبل/بعد» الفاتورة.
        """
        from decimal import Decimal
        from accounting.services import partner_posted_balance
        partner = self.get_object()
        debit, credit = partner_posted_balance(partner.tenant_id, partner.id)
        is_supplier = (partner.partner_type or "").lower() == "supplier"
        open_balance = (credit - debit) if is_supplier else (debit - credit)
        try:
            proposed = Decimal(str(request.query_params.get("proposed_total", "0")))
        except Exception:
            proposed = Decimal("0")
        return Response({
            "partner": partner.id,
            "partner_type": partner.partner_type,
            "debit": str(debit),
            "credit": str(credit),
            "open_balance": str(open_balance),
            "proposed_total": str(proposed),
            "projected_balance": str(open_balance + proposed),
        })

    # ── FEAT-4: Party (customer/supplier) profile ────────────────
    @action(detail=True, methods=["get"], url_path="profile")
    def profile(self, request, pk=None):
        """رأس بطاقة الشريك: الرصيد Dr/Cr + إجمالي المبيعات/المشتريات + المتبقي
        + تاريخ آخر معاملة. تُطابق الأرصدة المصدر القانوني (القيود المرحَّلة)."""
        from decimal import Decimal
        from django.db.models import Sum, Max
        from accounting.services import partner_posted_balance
        from sales.models import SalesInvoice
        from logistics.models import PurchaseInvoice

        partner = self.get_object()
        is_supplier = (partner.partner_type or "").lower() == "supplier"
        debit, credit = partner_posted_balance(partner.tenant_id, partner.id)
        balance = (credit - debit) if is_supplier else (debit - credit)

        sales_agg = SalesInvoice.objects.filter(
            tenant_id=partner.tenant_id, customer_id=partner.id,
            status=SalesInvoice.STATUS_POSTED,
        ).aggregate(total=Sum("grand_total"), last=Max("invoice_date"))
        purch_agg = PurchaseInvoice.objects.filter(
            tenant_id=partner.tenant_id, partner_id=partner.id, is_posted=True,
        ).aggregate(total=Sum("grand_total"), last=Max("invoice_date"))

        last_dates = [d for d in (sales_agg["last"], purch_agg["last"]) if d]
        last_txn = max(last_dates).isoformat() if last_dates else None

        # عميل: رصيد موجب = مدين له علينا (Dr/ذمم مدينة). مورد: رصيد موجب =
        # دائن نحن مدينون له (Cr/ذمم دائنة). الإشارة السالبة تعكس الجهة.
        natural = "Cr" if is_supplier else "Dr"
        opposite = "Dr" if is_supplier else "Cr"
        balance_side = natural if balance >= 0 else opposite

        return Response({
            "id": partner.id,
            "name": partner.name,
            "partner_type": partner.partner_type,
            "phone": partner.phone,
            "email": partner.email,
            "debit": str(debit),
            "credit": str(credit),
            "balance": str(balance),
            "balance_side": balance_side,
            "outstanding_balance": str(abs(balance)),
            "total_sales": str(sales_agg["total"] or Decimal("0")),
            "total_purchases": str(purch_agg["total"] or Decimal("0")),
            "last_transaction_date": last_txn,
        })

    @action(detail=True, methods=["get"], url_path="statement")
    def statement(self, request, pk=None):
        """كشف حساب الشريك (الأستاذ) — Debit/Credit + رصيد جارٍ، مُرقَّم."""
        from accounting.services import partner_account_statement
        partner = self.get_object()
        is_supplier = (partner.partner_type or "").lower() == "supplier"
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (TypeError, ValueError):
            offset = 0
        ordering = request.query_params.get("ordering", "newest")
        return Response(partner_account_statement(
            tenant_id=partner.tenant_id, partner_id=partner.id,
            is_supplier=is_supplier, limit=limit, offset=offset, ordering=ordering))

    @action(detail=True, methods=["get"], url_path="invoices")
    def invoices(self, request, pk=None):
        """فواتير الشريك (بيع للعميل + شراء للمورد) — كلٌّ قابل للنقر."""
        from sales.models import SalesInvoice
        from logistics.models import PurchaseInvoice
        partner = self.get_object()
        out = []
        for inv in SalesInvoice.objects.filter(
            tenant_id=partner.tenant_id, customer_id=partner.id,
        ).order_by("-invoice_date", "-id")[:200]:
            out.append({
                "document_type": "SALES_INVOICE",
                "document_id": inv.id,
                "document_number": inv.invoice_number,
                "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "grand_total": str(inv.grand_total),
                "is_posted": inv.status == SalesInvoice.STATUS_POSTED,
            })
        for inv in PurchaseInvoice.objects.filter(
            tenant_id=partner.tenant_id, partner_id=partner.id,
        ).order_by("-invoice_date", "-id")[:200]:
            out.append({
                "document_type": "PURCHASE_INVOICE",
                "document_id": inv.id,
                "document_number": inv.invoice_number,
                "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "grand_total": str(inv.grand_total),
                "is_posted": bool(inv.is_posted),
            })
        return Response(out)

    def get_queryset(self):
        # task11 M7: القراءة كانت بلا فلترة tenant — موردو/زبائن كل الشركات
        # كانوا يظهرون لأي شركة. .none() عند غياب الشركة حتى لا يتسرب شيء.
        tenant = self._get_tenant()
        if not tenant:
            return Partner.objects.none()
        qs = super().get_queryset().filter(tenant=tenant)
        partner_type = self.request.query_params.get("partner_type")
        if partner_type:
            qs = qs.filter(partner_type=partner_type)
        assigned_price_tier = self.request.query_params.get("assigned_price_tier")
        if assigned_price_tier:
            qs = qs.filter(assigned_price_tier=assigned_price_tier)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(tax_number__icontains=search)
            )
        return qs

    @action(detail=False, methods=["get"], url_path="lookup")
    def lookup(self, request):
        """Bounded raw-array contract for pickers that do not render pages."""
        try:
            limit = int(request.query_params.get("limit", 200))
        except (TypeError, ValueError):
            limit = 200
        limit = min(max(limit, 1), 500)
        rows = self.get_queryset().order_by("name", "id")[:limit]
        return Response(self.get_serializer(rows, many=True).data)

    def _handle_bank_accounts(self, partner, bank_accounts_data, tenant):
        """
        Synchronizes bank accounts for a partner.
        bank_accounts_data can be a JSON string or a list.
        """
        if isinstance(bank_accounts_data, str):
            try:
                if not bank_accounts_data or bank_accounts_data.strip() == "":
                    bank_accounts_data = []
                else:
                    bank_accounts_data = json.loads(bank_accounts_data)
            except (ValueError, TypeError):
                bank_accounts_data = []

        if not isinstance(bank_accounts_data, list):
            bank_accounts_data = []

        # List of IDs provided by frontend for updating/keeping
        provided_ids = [acc.get('id') for acc in bank_accounts_data if acc.get('id')]
        
        # Delete accounts that are no longer present in the list
        partner.bank_accounts.exclude(id__in=provided_ids).delete()

        # Update or Create provided accounts
        for acc_data in bank_accounts_data:
            acc_id = acc_data.get('id')
            
            # Basic validation
            bank_name = acc_data.get('bank_name')
            account_number = acc_data.get('account_number')
            
            if not bank_name or not account_number:
                if len(bank_accounts_data) == 1 and not bank_name and not account_number:
                    # If it's just one empty row, maybe skip instead of erroring
                    continue
                raise ValidationError("اسم البنك ورقم الحساب مطلوبان لكافة الحسابات المضافة.")

            # Handle Currency ID
            curr_id = acc_data.get('currency')
            if curr_id in ("", None, "null"):
                raise ValidationError(f"يجب تحديد العملة للحساب البنكي: {bank_name}")
            
            try:
                curr_id = int(curr_id)
            except (ValueError, TypeError):
                raise ValidationError(f"قيمة العملة غير صالحة للحساب البنكي: {bank_name}")

            defaults = {
                'bank_name': bank_name,
                'account_number': account_number,
                'iban': acc_data.get('iban', ''),
                'swift_code': acc_data.get('swift_code', ''),
                'bank_address': acc_data.get('bank_address', ''),
                'beneficiary_name': acc_data.get('beneficiary_name', ''),
                'currency_id': curr_id,
                'is_active': acc_data.get('is_active', True),
                'tenant': tenant
            }

            try:
                if acc_id:
                    # Update existing record
                    PartnerBankAccount.objects.filter(
                        id=acc_id, 
                        partner=partner
                    ).update(**defaults)
                else:
                    # Create new record
                    PartnerBankAccount.objects.create(partner=partner, **defaults)
            except Exception as e:
                raise ValidationError(f"فشل في حفظ الحساب البنكي {bank_name}: {str(e)}")

    def _handle_attachments(self, partner, data, tenant):
        """
        Saves Cloudinary images and documents to SystemAttachment.
        """
        from core.models import SystemAttachment
        
        # Mapping from frontend keys to file types
        field_map = {
            'image_path': 'Profile Image',
            'image_url': 'Image',
            'document_url': 'Document'
        }

        for field, file_type in field_map.items():
            value = data.get(field)
            if value and isinstance(value, str) and value.startswith('http'):
                # Check if this specific URL is already attached to this partner
                if not SystemAttachment.objects.filter(
                    tenant=tenant,
                    related_table='partners',
                    related_id=partner.id,
                    file_path=value
                ).exists():
                    SystemAttachment.objects.create(
                        tenant=tenant,
                        related_table='partners',
                        related_id=partner.id,
                        file_type=file_type,
                        file_path=value
                    )

    def create(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        
        # Prepare partner data
        partner_data = request.data.copy()

        # Create partner
        serializer = self.get_serializer(data=partner_data)
        serializer.is_valid(raise_exception=True)
        partner = serializer.save(tenant=tenant)

        # Handle bank accounts sync
        bank_accounts_data = request.data.get('bank_accounts', [])
        self._handle_bank_accounts(partner, bank_accounts_data, tenant)

        # Handle attachments (Cloudinary links)
        self._handle_attachments(partner, request.data, tenant)

        return Response(self.get_serializer(partner).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        tenant = self._get_tenant()
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Prepare partner data
        partner_data = request.data.copy()

        # Update partner
        serializer = self.get_serializer(instance, data=partner_data, partial=partial)
        serializer.is_valid(raise_exception=True)
        partner = serializer.save()
                
        # Handle bank accounts sync
        if 'bank_accounts' in request.data:
            bank_accounts_data = request.data.get('bank_accounts', [])
            self._handle_bank_accounts(partner, bank_accounts_data, tenant)

        # Handle attachments (Cloudinary links)
        self._handle_attachments(partner, request.data, tenant)

        return Response(self.get_serializer(partner).data)


class CustomerNoteViewSet(viewsets.ModelViewSet):
    """ملاحظات/تذكيرات بطاقة الزبون (CRM) — CRUD مُنطاق بالشركة.

    قائمة مفلترة بـ ?partner=<id>. تذكيرات مستحقة عبر reminders-due/ لمولّد
    إشعارات الموقع (يُنشئ إشعاراً عند حلول يوم التذكير).
    """
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    serializer_class = CustomerNoteSerializer

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return CustomerNote.objects.none()
        qs = CustomerNote.objects.filter(tenant=tenant).select_related('partner').order_by('-created_at')
        partner_id = self.request.query_params.get('partner')
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        return qs

    def perform_create(self, serializer):
        tenant = get_tenant(self.request)
        if not tenant:
            raise ValidationError({'tenant': 'لا يوجد شركة محددة.'})
        note = serializer.save(
            tenant=tenant,
            created_by=self.request.user if self.request.user.is_authenticated else None,
        )
        logger.info(
            'customer_note.create id=%s partner=%s tenant=%s remind_on=%s',
            note.id, note.partner_id, tenant.TenantID, note.remind_on,
        )

    @action(detail=False, methods=["get"], url_path="reminders-due")
    def reminders_due(self, request):
        """تذكيرات مستحقة اليوم أو قبله وغير منجزة — يستهلكها مولّد الإشعارات."""
        from datetime import date
        tenant = get_tenant(request)
        if not tenant:
            return Response([])
        qs = CustomerNote.objects.filter(
            tenant=tenant, is_done=False,
            remind_on__isnull=False, remind_on__lte=date.today(),
        ).select_related('partner').order_by('remind_on')
        return Response([
            {
                'id': n.id,
                'title': n.title,
                'remind_on': n.remind_on.isoformat(),
                'partner_id': n.partner_id,
                'partner_name': n.partner.name,
            }
            for n in qs
        ])

