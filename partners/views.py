import json

from django.core.files.storage import default_storage
from rest_framework import viewsets, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.api_defaults import ApiAuthAndUser
from core.tenant_utils import get_tenant
from tenants.models import Tenant
from .models import Partner, PartnerBankAccount
from .serializers import PartnerSerializer


class PartnerViewSet(viewsets.ModelViewSet):
    authentication_classes = ApiAuthAndUser["authentication_classes"]
    permission_classes = ApiAuthAndUser["permission_classes"]
    queryset = Partner.objects.all().order_by('-created_at')
    serializer_class = PartnerSerializer
    search_fields = ['name', 'legal_name', 'email', 'phone', 'tax_number']

    def _get_tenant(self):
        return get_tenant(self.request)

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

